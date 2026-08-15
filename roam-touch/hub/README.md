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
channels.py    tmux: discover panes, send keys, capture output
store.py       SQLite event log, per channel, never hard-deleted
transcript.py  pull the assistant's answer out of a session transcript;
               summarise it for Piper and for a glance
hub.py         FastAPI service + WebSocket + the tmux poller
bridge.py      hub events -> phone notifications, via tools/roam-push
files.py       ~/Collab browsing, path safety, share-to-Claude, thumbnails
photo_bridge.py  a Google Photos shared album -> ~/.claude/dropzone/inbox
web/           browse.html + stl.html, and a vendored three.js r112
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

Health check (no auth) — `build` tells you which commit is actually serving:

```bash
curl -s http://100.67.237.109:8787/health
```

⚠️ **`launchctl kickstart` after every deploy.** A green test suite says nothing
about the running process: the service once served `coverage: null` for two commits
because nobody restarted it, and the client built against `API.md` could not use the
feature at all. `build.commit` in `/health` is there so that is visible instead of
silent.

## The bridge (hub → phone)

Until the Channels app exists, nothing subscribes to the hub, so from across the
room it is a database. `bridge.py` is a WebSocket client that forwards the events
worth interrupting someone for to ROAM Touch by **shelling out to
`~/Projects/roam/tools/roam-push`** — one push path, never a second implementation.

⚠️ `roam-push`, **not `roam-msg`**. They were the same program until the split:
`roam-msg` is the client every agent calls and it now posts a `notice` to
`POST /notify`, so a bridge that delivered through it would turn each
notification into a new notice and feed itself forever. `roam-push` is the
device transport, holds no policy, and nothing but the bridge runs it.

```bash
cp com.talos.roam-bridge.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.talos.roam-bridge.plist
launchctl kickstart -k gui/$(id -u)/com.talos.roam-bridge   # restart
launchctl bootout   gui/$(id -u)/com.talos.roam-bridge      # stop
tail -f ~/Library/Logs/roam-bridge.log
```

* **What gets pushed**: `PUSH_KINDS` in `bridge.py` — currently `outcome`,
  `error` and `notice` (a tool talking to him: `roam-msg "build finished"`).
  `receipt` is deliberately excluded: he typed it seconds ago, and
  echoing it back to his arm is noise. It is a constant with a comment because it
  will get tuned.
* **What it says**: the channel **label** then the event summary —
  `✳ Augment things: the suite is green — 122 tests`. The label is the point: which
  session is talking, without unlocking anything. `roam-push --tag` tags each
  channel separately so two sessions don't overwrite each other.
* **What it will not do**: push an event the hub stamped as covered — an answer to
  something he typed at the keyboard. The bridge holds no opinion and asks nothing;
  it reads the stamp. `ROAM_BRIDGE_SUPPRESS_WHEN_COVERED=false` pushes regardless.
* **Catching up**: every event decides for itself from its own stamp, so three
  missed answers still buzz and thirty he watched arrive do not.
  `BACKLOG_FLOOD_LIMIT` (50) is only a circuit breaker against a pathological
  replay, not the rule.
* **Rate**: at most one notification per `ROAM_BRIDGE_MIN_INTERVAL_S` (default 5 s).
  Events arriving inside the window are coalesced per channel — newest wins, with
  `(+N more)` — so a burst cannot machine-gun the phone.
* **Cursor**: `bridge-state.json` holds the last event id, written atomically. A
  restart resumes exactly where it stopped; a *first* run starts from the hub's
  current latest id, because nobody wants a week of old outcomes on their arm at
  startup.

## The photo bridge (shared album → Claude)

`photo_bridge.py` turns **one Google Photos shared album into Claude's inbox**.
Put the share link in `photo-album.txt` (gitignored; see `photo-album.txt.example`)
and anything added to that album lands in `~/.claude/dropzone/inbox/`. The album
*is* the permission boundary — no per-photo decision, no upload step, and no
Google account anywhere near this machine.

```bash
./.venv/bin/python photo_bridge.py --verbose     # one pass, logs to stderr too
cp com.talos.roam-photos.plist ~/Library/LaunchAgents/   # every 5 min, NOT loaded yet
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.talos.roam-photos.plist
```

* **Not the Library API.** Google revoked the library-read scopes in March 2025;
  an OAuth app can only see media it created itself. The public share page needs
  no credentials at all, which is the whole point. Do not "fix" this back.
* **How it reads the page**: the item list is in the initial HTML, inside
  Google's own `AF_initDataCallback({... data:[...] ...})` hydration payload.
  Plain HTTP and a string-aware bracket scan — no browser, no JS engine.
* ⚠️ **Never follow the `photos.app.goo.gl` link with a browser User-Agent.** It
  is a Firebase Dynamic Links interstitial and answers a desktop UA with a 200
  JS shell that does not contain the destination anywhere. A **HEAD with
  redirects disabled** answers a clean 302 whose `Location` is the real album.
* **First run marks only.** Otherwise switching this on drags the whole album
  into the inbox. An *empty* album is a normal state and still primes; a login
  wall or an error page is not, and leaves the mark untouched so the next real
  photo is not skipped.
* **Dedupe on the media id**, not the URL — the base URLs look rotatable.
  Full resolution is the base URL plus `=d`.
* **A file in the dropzone is not context.** The `clip-fetch` prompt hook is
  what moves `inbox/` into `dropzone/` and names the files to Claude.
* ⚠️ **EXIF, including GPS and the device model, arrives intact.** Nothing here
  strips it — that is the owner's call, not a silent default.

## The file browser (`~/Collab` → the wrist → Claude)

`GET /browse` is a small HTML file browser over `~/Collab/CAD` and
`~/Collab/Photos`, so a part can be looked at from the arm instead of from the
desk. Read-only; `POST /share` copies a file *out*, into the dropzone inbox, so
it reaches Claude by the same door a shared-album photo does.

```
files.py     path resolution, listing, share, sips thumbnails
web/         browse.html, stl.html, and a vendored three.js r112
```

* **All the safety is `files.resolve`.** A browse path is `<root>/<relative>`
  and a request that does not land strictly inside a declared root is refused —
  `..` in either slash direction, an absolute path, a nul byte, a sibling
  directory whose name merely *starts* with a root's, and (the one lexical
  checks always miss) **a symlink inside a shared folder pointing elsewhere**.
  Containment is checked after `realpath`, on path components, never on strings.
* **`?token=` is accepted** on these endpoints, exactly as `/ws` already does it:
  a browser cannot put a header on `<img src>`. The pages send
  `Referrer-Policy: no-referrer` so it cannot leak onward.
* **STL only.** The CAD folders are mostly `.step` — b-rep, needs an OCCT-class
  kernel — so `/view/stl` answers 415 for one and the listing advertises the
  `.stl` the build pipeline drops beside it (`mesh_path`).
* ⚠️ **The client is Chrome 74 (2019) on a Pixel 1 and cannot ever be updated**
  (signature-pinned, no Play Store on the device). No `?.`, no `??`, no class
  fields, no `:has()`, and **no flexbox `gap`** — that one is Chrome 84 and is
  silently ignored before it, so the layout just collapses. three.js is pinned
  at **r112** because the modern builds are ES2020 modules that engine cannot
  parse at all. `tests/test_files_api.py` fails on modern syntax, and — where
  `node` is installed — really parses the pages at `ecmaVersion: 2019` and runs
  the viewer's whole data path against the vendored three.

### The inbox contract (for anything that wants to hand Claude a file)

`~/.claude/dropzone/inbox/` is a **queue, not an archive**. The `UserPromptSubmit`
hook at `~/.claude/hooks/clip-fetch.sh` (wired in `~/.claude/settings.json`, and
*not* in this repo) moves everything in it up into `~/.claude/dropzone/` and names
each file in its `additionalContext`. That naming is the whole point: **a file
that merely appears in the dropzone is invisible** — only the `fetched` list makes
it exist as far as Claude is concerned.

So, to hand Claude a file: write it into `inbox/` and stop. Two rules for
producers, both of which `photo_bridge.py` and `POST /share` follow:

* **Write `name.ext.part` and rename.** The hook skips `*.part`, and a rename
  within a filesystem is atomic, so a half-written file can never be picked up
  mid-write.
* **Expect it to be moved out from under you.** The move is the high-water
  mark; there is no second bookkeeping file to get out of sync.

⚠️ When globbing that directory, match on the **basename**. A `case "$f" in */.*)`
against the full path matches the `/.claude/` in it and silently skips every file.

## Where a reply goes

**Reply where the last message came from.** Per channel, exactly like any
messaging app:

* he typed the prompt in tmux (the `UserPromptSubmit` hook says so) → he is
  reading the answer there → **no push**;
* he sent it from ROAM (`POST /channels/{pane}/send`) → that is where the
  conversation is → **push**.

The hub stamps that decision onto every event as `coverage` when the event
happens, so a backlog is still answerable days later: push what he genuinely
missed, pass over what he watched arrive. Coverage governs **notification only**
— every event is stored and shown in the thread regardless.

Sending from the app types into the pane, which fires the same hook, so the hub
recognises that echo (same text, inside `ROAM_HUB_ECHO_WINDOW_S`) and does not
let it flip the channel back to the keyboard. It also **says so on the event**:
the receipt carries `meta.echo_of` = the id of the `sent` it duplicates, so the
thread draws one entry for one thing he said and the search index embeds the
sentence once. ⚠️ A receipt *without* that mark is a prompt he typed at the
keyboard and the only record it exists — receipts are never suppressed as a
class.

⚠️ **No recorded source means notify.** A fresh pane, an agent that speaks first,
a failed lookup — a missed message is worse than a redundant one.

`POST /presence` remains for the one case this cannot express: he is *looking* at
the panel without having sent anything. It only ever adds coverage. The hub
observes nothing itself — the tmux-client watching and `HIDIdleTime` that earlier
versions used are both deleted (the latter read 13.2 hours idle while he was
actively typing over SSH).

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
