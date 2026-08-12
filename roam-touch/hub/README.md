# ROAM Touch hub

The always-on service on **talos** that holds channel state for the arm-mounted
client. A *channel* is one tmux pane running an agent, keyed on the tmux pane id
(`%3`). The hub sends messages to panes, stores everything that happens on them,
and pushes new events to clients over a WebSocket.

**The hub holds the state; the panel is only a view.** An outcome can land minutes
after the prompt was sent, while the wearer is looking somewhere else or has the
lid shut — so it is written to SQLite first and pushed second, and a client that
was asleep catches up by event id.

Client contract: **[API.md](API.md)**. Read that before writing any client.

```
channels.py    tmux: discover panes, send keys, capture output, who's watching
store.py       SQLite event log, per channel, never hard-deleted
transcript.py  pull the assistant's answer out of a session transcript;
               summarise it for Piper and for a glance
hub.py         FastAPI service + WebSocket + the tmux poller
bridge.py      hub events -> phone notifications, via roam-msg
roam-hub-hook  the Claude Code hook that posts receipts and outcomes
tests/         pytest; tmux faked at channels._run, network at urlopen
```

**Summary first, details on demand.** Every event carries a short, speakable
`summary` (≤280 chars, markdown and emoji stripped, code and tables noted rather
than read out) *and* the full `body`. Bulk payloads trim the body to 4 KiB and say
so (`body_truncated`, `body_chars`); `GET /events/{id}` returns it whole. Nothing
is destroyed to make a summary. A 256 KiB storage rail bounds a pathological reply
and records `meta.truncated_from` when it bites.

**Liveness.** Every live channel reports `last_output_at` / `idle_s`, sampled by
fingerprinting each pane's visible screen every poll. `working` plus a climbing
`idle_s` is the "is it stuck?" answer a bare status can never give — it measures
"this pane is producing output", not process health. Set
`ROAM_HUB_ACTIVITY_POLLING=false` to switch the sampling off.

## Running it

```bash
# one-time
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# foreground, loopback only (development)
./.venv/bin/python hub.py

# the suite
./.venv/bin/python -m pytest
```

### Always-on (launchd)

```bash
cp com.talos.roam-hub.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.talos.roam-hub.plist

launchctl kickstart -k gui/$(id -u)/com.talos.roam-hub   # restart (after a code change)
launchctl print gui/$(id -u)/com.talos.roam-hub | head   # state, pid, last exit
launchctl bootout gui/$(id -u)/com.talos.roam-hub        # stop and unload

tail -f ~/Library/Logs/roam-hub.log                      # uvicorn access + hub log
tail -f ~/Library/Logs/roam-hub.err
```

Health check (no auth):

```bash
curl -s http://100.67.237.109:8787/health
```

## The bridge (hub → phone)

Until the Channels app exists, nothing subscribes to the hub, so from across the
room it is a database. `bridge.py` is a WebSocket client that forwards the events
worth interrupting someone for to ROAM Touch by **shelling out to
`~/Projects/roam/tools/roam-msg`** — one push path, never a second implementation.

```bash
cp com.talos.roam-bridge.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.talos.roam-bridge.plist
launchctl kickstart -k gui/$(id -u)/com.talos.roam-bridge   # restart
launchctl bootout   gui/$(id -u)/com.talos.roam-bridge      # stop
tail -f ~/Library/Logs/roam-bridge.log
```

* **What gets pushed**: `PUSH_KINDS` in `bridge.py` — currently `outcome` and
  `error`. `receipt` is deliberately excluded: he typed it seconds ago, and
  echoing it back to his arm is noise. It is a constant with a comment because it
  will get tuned.
* **What it says**: the channel **label** then the event summary —
  `✳ Augment things: the suite is green — 122 tests`. The label is the point: which
  session is talking, without unlocking anything. `roam-msg --pane` tags each
  channel separately so two sessions don't overwrite each other.
* **What it will not do**: buzz about something he is already looking at. The bridge
  does not work that out itself — **the hub owns presence** (see below) and the
  bridge is one more consumer of it, which is why the Android app saying "I am
  foregrounded" needs no bridge change at all. `ROAM_BRIDGE_SUPPRESS_WHEN_PRESENT=false`
  pushes regardless.
* **What it will not do either**: dump a backlog on him. If it reconnects more than
  `BACKLOG_PUSH_LIMIT` (15) pushable events behind, it catches up **silently** —
  being that far behind is itself evidence he was working elsewhere and has already
  seen it. The events are in the hub and the channel history, which is where he
  will look.
* **Rate**: at most one notification per `ROAM_BRIDGE_MIN_INTERVAL_S` (default 5 s).
  Events arriving inside the window are coalesced per channel — newest wins, with
  `(+N more)` — so a burst cannot machine-gun the phone.
* **Cursor**: `bridge-state.json` holds the last event id, written atomically. A
  restart resumes exactly where it stopped; a *first* run starts from the hub's
  current latest id, because nobody wants a week of old outcomes on their arm at
  startup.

## Presence — where he is

`presence.py`. The hub tracks where the user is interacting so nothing notifies
him about a screen he is already reading. Sources are named, carry a TTL, and
combine by union; new ones need no new logic, just a `POST /presence`.

| source | kind | how | covers |
|---|---|---|---|
| `tmux:/dev/ttys000` | observed | a tmux client that has taken input within `ROAM_HUB_PRESENCE_GRACE_S` (120 s); `who(1)` supplies where that login came from | the pane on its screen |
| `roam-app` | reported | the client POSTs while foregrounded | everything (`covers_all`) |

* ⚠️ **No sources means push.** A missed message is worse than a redundant one, so
  an empty registry is "we do not know", never "he must be here". `Presence.should_push`
  returns True for anything uncovered, and a hub restart forgets everything — failing
  towards notifying.
* ⚠️ **Only what talos can observe.** macOS window focus and "is he in the room" are
  not knowable from here and are absent by choice. `HIDIdleTime` *was* tried and
  rejected: it read **13.2 hours idle while he was actively typing**, because he
  works over SSH and it measures this machine's keyboard, not his. A signal that
  wrong is worse than no signal.
* A source with no panes and no `covers_all` is still presence (it shows on
  `/presence`) but suppresses nothing: evidence he is at *a* keyboard is not
  evidence he can see *this* channel.

## Auth and binding

* **Bound to the Tailscale address `100.67.237.109` only** (`ROAM_HUB_HOST` in the
  plist). Not `0.0.0.0`, not the LAN address. A machine on the house Wi-Fi — or on
  whatever coffee-shop network the laptop is on — cannot open a socket to it at
  all; only tailnet peers can. The code's own default is `127.0.0.1`, so an
  accidental run is never exposed.
* **Shared bearer token**, defence in depth behind that: the tailnet has other
  devices on it, and a stolen device or a shared node should not be able to type
  into a live Claude session. Every endpoint except `GET /health` requires
  `Authorization: Bearer <token>`.
* The token lives in `hub-token.txt` (gitignored, mode 0600). It is generated on
  first run — 32 bytes of `secrets.token_urlsafe`. Copy it to the client:

  ```bash
  cat hub-token.txt
  ```

* Traffic is plain HTTP. Tailscale is WireGuard; adding TLS on top would mean a
  cert for a MagicDNS name and a trust store on the client for no additional
  protection. **If the hub ever binds anything other than a tailnet address, that
  reasoning is void** — put TLS in front of it first.

Configuration is environment-driven (`pydantic-settings`), prefix `ROAM_HUB_`:
`HOST`, `PORT`, `DB_PATH`, `TOKEN_FILE`, `TOKEN`, `POLL_INTERVAL`, `CAPTURE_LINES`,
`HISTORY_LIMIT`, `LOG_LEVEL`.

## Data

`hub.sqlite` (WAL) next to this file: `events` and `channels`. **Nothing is ever
hard-deleted** — clearing a thread or removing a channel sets `archived = 1`, and
both come back with `include_archived=true`. Back it up by copying the file; it is
small and the client can be rebuilt from it entirely.

## Remaining step: the receipt/outcome hooks

The hub's `POST /events` endpoint is live and tested, but **nothing is posting to
it yet**. The "Sent"/"Ready" signals are a Claude Code hook pair (`UserPromptSubmit`
and `Stop`); wiring them is a deliberate, separate step because it edits the live
`~/.claude/settings.json` of a session that is in use.

Add to `~/.claude/settings.json` (merging with the existing `UserPromptSubmit`
entry, not replacing it):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "/Users/talos/Projects/roam/roam-touch/hub/roam-hub-hook receipt"}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command", "command": "/Users/talos/Projects/roam/roam-touch/hub/roam-hub-hook outcome"}]}
    ]
  }
}
```

`roam-hub-hook` is in this directory. It reads Claude Code's hook JSON on stdin and
POSTs to `/events` tagged with `$TMUX_PANE`:

* **outcome** — sends the assistant's **actual answer**. "The response finished" on
  its own is useless; the point of the device is not walking back to the computer to
  read the answer. The answer comes from the hook payload's `last_assistant_message`
  (Claude Code hands `Stop` the finished text — verified by capturing a real payload
  from a live turn, `ROAM_HUB_HOOK_DUMP=<file>` does that). If a version ever stops
  providing it, `transcript.py` reads the session file instead and **waits** for this
  turn's record to be flushed — see the race note below. Thinking blocks are never
  included, and the hub adds the speakable `summary`.
* **receipt** — sends the submitted prompt, so a channel shows real activity even
  when the wearer typed at the desk.

It exits 0 and posts nothing when `$TMUX_PANE` is unset, the token is missing, the
transcript is unreadable or the hub is unreachable — a hook must never be able to
break the session it is reporting on.

### ⚠️ The flush race (fixed 2026-08-11, keep this in mind)

The first live outcome stored the wrong text: the turn's opening line instead of its
answer. The final assistant record carried a timestamp **143 ms before** the hook's
POST and still was not readable when the hook fired. It did not fail loudly — it
returned real, plausible prose from the same turn, and on any turn that ends with
tool calls after a preamble the user would have been read the preamble with nothing
to indicate anything was wrong. Worse than an empty body, which announces itself.

Two defences, both live:

1. The **hook payload is the authority** — `last_assistant_message` is the finished
   answer, in memory, before anything is flushed. No disk, no race.
2. The transcript fallback **waits**: if the newest turn on disk has not spoken yet,
   poll every 50 ms until it does (hard cap 2 s, early exit once the file goes
   quiet). If the wait expires it still posts, with `meta.transcript_settled: false`
   so a wrong block is *detectable*.

Reproduce either behaviour on a real turn with `ROAM_HUB_ANSWER_SOURCE=transcript`
and `ROAM_HUB_SETTLE_MS=0`.

Verify by hand before installing it:

```bash
./roam-hub-hook receipt && ./roam-hub-hook outcome   # from inside a tmux pane
curl -s -H "Authorization: Bearer $(cat hub-token.txt)" \
     "http://100.67.237.109:8787/channels/${TMUX_PANE#%}/history" | python3 -m json.tool
```

Until that is wired, channels still work — `sent` events are recorded by the hub
itself, and `status` returns to `idle` only when something posts an `outcome`.
