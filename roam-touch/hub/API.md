# ROAM Touch hub — client contract

Version `1.3.0`, protocol `1`. This document is the contract the Android client is
built against. If the code and this file disagree, that is a bug in one of them —
say so rather than guessing.

**Model.** A *channel* is one tmux pane running an agent, keyed on the tmux **pane
id** (`%3`). The hub holds the state; the client is a view. An outcome can land
minutes after the prompt was sent, while the wearer is looking at another channel
or has the lid shut, so every message, receipt and outcome is stored before it is
pushed. A client that was asleep catches up by id — it never has to poll.

---

## 1. Connecting

| | |
|---|---|
| Base URL | `http://talos:8787` (Tailscale MagicDNS) or `http://100.67.237.109:8787` |
| WebSocket | the same base URL, path `/ws` — see the note below before hard-coding a scheme |
| Auth | `Authorization: Bearer <token>` on **every** request except `GET /health` |
| Content type | `application/json` in and out; UTF-8 |
| Transport | Plaintext HTTP. The socket is bound to the Tailscale address only, and Tailscale (WireGuard) is already the encryption layer. Do not expose it anywhere else. |

The token is a shared secret in `hub-token.txt` on talos (mode 0600, gitignored).
Copy it into the client's config; it does not rotate on its own.

**Errors** are always `{"detail": "<human readable>"}` with an HTTP status:

| status | meaning |
|---|---|
| 400 | malformed pane id |
| 401 | missing/incorrect bearer token (`WWW-Authenticate: Bearer`) |
| 404 | unknown channel, or a pane that is no longer live |
| 422 | request body failed validation (e.g. empty `text`) |
| 502 | tmux refused the send — nothing was typed |
| 503 | tmux is unavailable on the host |

### Pane ids in URLs

Pane ids start with `%`, the URL escape character. The hub accepts **either** form,
and rejects anything that is not a tmux pane id:

```
GET /channels/3/history        ← recommended: strip the leading '%'
GET /channels/%253/history     ← equivalent: percent-encoded '%3'
```

`pane_id` in every JSON body is always the canonical `%3` form. Strip the `%` when
building a URL and you never have to think about encoding.

**One channel is not a pane: `@host`.** It collects `notice` events from things
that have no `$TMUX_PANE` — an agent under launchd, a cron job, a script over
ssh. Its id is that exact literal (a tmux pane id is always `%<n>`, so they can
never collide) and it appears in `GET /channels` like any other channel, with
`live: true`, `status: "idle"` and `idle_s: null` — it has no screen to
fingerprint and calling it *dead* would claim the box was gone. Its history is
readable at `GET /channels/@host/history`; `/send`, `/interrupt` and `/capture`
answer `404`, because there is nothing to type into. Treat `pane_id` as an
opaque string — as §5 already says — and nothing needs to special-case it.

---

## 2. Objects

### ★ Summary first, details on demand

Every event carries **both** a short `summary` and the full `body`. This is the
house rule, not an outcome-only special case:

* `summary` is what you **show in the notification / on the strip and hand to
  Piper**. Always present, always safe to speak, ≤280 characters.
* `body` is the full text, kept whole. Nothing is ever destroyed to make a
  summary — expanding is always possible.
* Bulk payloads (history, `/events`, WebSocket frames) carry the body trimmed to
  **4096 characters** with `body_truncated: true` and the real length in
  `body_chars`. `GET /events/{id}` returns the event untrimmed. So a long answer
  is never a wall of text you must scroll and never a snippet you cannot open.

Do not re-derive the summary client-side: one implementation, one behaviour, and
the TTS and the panel say the same thing.

### Event

```json
{
  "id": 412,
  "pane_id": "%0",
  "kind": "outcome",
  "body": "Tailscale beats the BLE permission wall — it just worked from here with\nno pairing.\n\nOne thing worth knowing: `roam-msg` returned nothing at all…",
  "summary": "Tailscale beats the BLE permission wall — it just worked from here with no pairing. One thing worth knowing: roam-msg returned nothing at all…",
  "body_chars": 319,
  "body_truncated": false,
  "coverage": {"known": true, "covered": false, "by": [], "last_input": "app"},
  "meta": {"source": "claude-hook", "session_id": "44c6d5f1"},
  "ts": 1786511500.066308,
  "archived": false
}
```

* `id` — monotonically increasing, never reused, unique across all channels. This
  is the client's catch-up cursor.
* `body` — the full text. For an `outcome` this is **the assistant's actual
  answer**, pulled out of the session transcript; markdown intact. Trimmed only in
  bulk payloads (see above).
* `summary` — markdown scaffolding removed, code blocks and tables reduced to
  `[code, 12 lines]` / `[table, 4 rows]`, decorative symbols and emoji dropped
  (Piper says nothing for them), cut at a sentence boundary within 280 chars.
* `body_chars` — the true length of the full body, whatever `body` you were sent.
* `body_truncated` — `true` when this payload's `body` was trimmed for bulk
  delivery. Fetch `GET /events/{id}` to expand.
* `coverage` — whether this needed a notification when it landed. See above.
* `ts` — epoch seconds, UTC, float.
* `meta` — free-form JSON object; may be `{}`. Never `null`. On a hook-posted
  outcome it carries `session_id`, `prompt_id`, `transcript_path` and:
  * `answer_source` — `hook_payload` (the answer Claude Code handed the hook;
    the normal case) or `transcript` (read from the session file).
  * `transcript_settled` — present when `answer_source` is `transcript`. **`false`
    means the answer had not reached disk before the wait expired, so the body
    may be an earlier block of the same turn.** Show such an outcome with a
    caveat rather than reading it out as the answer.
  * `truncated_from` — only for a pathological reply beyond the **256 KiB storage
    rail**; the stored body then ends with `… [truncated]`.
  * `echo_of` — **receipts only.** See below.
* `archived` — soft-deleted. Only ever `true` in responses you explicitly asked
  for with `include_archived=true`.

**Kinds.** Treat this list as open — render an unknown kind as a plain note
rather than dropping it.

| kind | meaning |
|---|---|
| `sent` | the wearer sent this text to the channel (`body` = the text) |
| `receipt` | a prompt was submitted (`body` = the prompt, when the hook knows it). `meta.echo_of` marks the ones that are your own `sent` coming back — see below |
| `outcome` | the agent finished (`body` = **what it said**, not "finished") |
| `notice` | a tool said something to the wearer (`POST /notify`; `body` = the message). Not part of the conversation: it never makes a channel `working` and never moves `last_input_source`. |
| `opened` | the hub first saw this pane (`body` = its label) |
| `closed` | the pane went away; the channel is dead |
| `note` | free-form note |
| `control` | an interrupt was issued (`body` = `escape` \| `interrupt`) |
| `error` | a send failed (`meta.attempted` = what was not typed) |

### ★ `meta.echo_of`: one thing he said, one entry

`POST /channels/{pane}/send` types the text into the tmux pane, and typing into
the pane is exactly what fires `UserPromptSubmit`. So every message sent from
ROAM comes back a moment later as a `receipt` with the same body — the same
sentence, twice, one second apart.

The hub recognises that echo (a `sent` on this pane with matching text, inside
`ROAM_HUB_ECHO_WINDOW_S`, default 60 s) and stamps the receipt with the id of
the `sent` it duplicates:

```json
{"id": 341, "kind": "receipt", "body": "Not done yet.",
 "meta": {"source": "claude-hook", "echo_of": 340}}
```

* **`echo_of` present** — this is not a new message. It is the confirmation
  that event `echo_of` reached the pane. Render the `sent` **once**, moved to a
  delivered state; do not draw a second row. `echo_of` always names a `sent` on
  the same channel, and always an id lower than this event's.
* **`echo_of` absent** — he typed this at the keyboard. ⚠️ The receipt is then
  the *only* record that the message exists, so it must render as a message in
  its own right. **Never suppress receipts as a class.**

If the referenced `sent` is not in the thread you hold (a window that starts
after it), fall back to rendering the receipt on its own — a message shown
twice is a nuisance, a message shown zero times is a lie.

The same mark keeps the search index honest: an echo is the sentence the ledger
already stores as a `sent`, so it is indexed once.

### Channel

```json
{
  "pane_id": "%0",
  "label": "◑ Roam Touch rebuild discussion",
  "session": "main",
  "window": 1,
  "index": 1,
  "command": "claude.exe",
  "live": true,
  "status": "idle",
  "archived": false,
  "first_seen": 1786511486.69,
  "last_seen": 1786511488.84,
  "last_output_at": 1786511500.31,
  "idle_s": 2.4,
  "last_input_source": "app",
  "last_input_at": 1786511490.0,
  "event_count": 7,
  "last_event": { "...Event, or null..." }
}
```

* `label` — what to show as the channel name. It is the tmux pane title, which
  for a Claude pane is the session summary. Falls back to `session:window.pane`
  when no title is set.
* `live` — the pane exists on the host right now. `window`, `index` and `command`
  are `null` when it does not.
* `last_input_source` — `tmux` | `app` | null: where this channel's conversation
  is happening, and therefore where its next answer will be delivered.
* `status` — `"idle"` | `"working"` | `"dead"`:
  * `dead` — the pane is gone. History is still readable; sending returns 404.
  * `working` — the last event was a `sent` or `receipt`; the agent owes an
    outcome.
  * `idle` — anything else.
* A channel whose pane has died **stays in the list** with its history and its
  last known label. That is deliberate: the outcome you are waiting for may be
  the last thing that pane ever said.

### ★ Liveness: `last_output_at` and `idle_s`

`status` alone cannot answer the question that actually gets asked — *is it stuck,
should I kill it?* A session thinking hard and a session wedged are both
`working`. So every live channel also reports when its **visible output last
changed**:

* `last_output_at` — epoch seconds, or `null` if the hub has not sampled it yet.
  A dead channel keeps its last reading (that is when it last spoke).
* `idle_s` — seconds since then, computed server-side at response time. `null`
  when the pane is dead or unsampled — never a fake zero.

Render it live: "active 2s ago" versus "active 4m ago" next to `working` is the
whole signal. Age `idle_s` locally between updates using `server_time`, and let
the `activity` frame reset it.

**What it does and does not mean.** The hub fingerprints each live pane's visible
screen every 2 s. An agent that is working repaints a spinner and an elapsed
counter, so its screen changes and `idle_s` stays near zero; a wedged one goes
quiet and `idle_s` climbs. It measures *"this pane is producing output"*, not
*"this process is healthy"* — a build that legitimately prints nothing for four
minutes reads as idle, and a `tail -f` reads as busy forever. Treat a climbing
`idle_s` as "nothing is coming out", which is exactly the input to "should I kill
it?", and never as proof of death.

### ★ Where a reply goes: `coverage`

**Reply where the last message came from.** Every event carries the answer,
stamped by the hub when the event happened:

```json
"coverage": {"known": true, "covered": true, "by": ["tmux-input"], "last_input": "tmux"}
```

* `covered: true` — the conversation is already somewhere he can see it, so this
  should **not** raise a notification. He typed the prompt in tmux, so he is
  reading the answer in tmux.
* `covered: false` — he sent the message from ROAM, so ROAM is where the answer
  belongs. **Notify.**
* `known: false` — nothing recorded (a fresh pane, an agent that spoke first).
  ⚠️ **Treat as notify.** A missed message is worse than a redundant one.
* `by` — what covered it: `tmux-input`, or the id of a reported presence source.
* `last_input` — `tmux` | `app` | null, the channel's conversation location at
  the time.

Switching is just sending from the other place: send from the app and the channel
moves to `app`; type in tmux and it moves back. Nothing infers where he is.

⚠️ **Coverage governs notification only.** A covered event is stored, returned by
history, and shown in the thread exactly like any other — it simply never buzzes.

The stamp is frozen at event time on purpose: by the time a sleeping client
reconnects, live state answers a different question. That is what makes a backlog
answerable — push the ones he genuinely missed, pass over the ones he watched
arrive, however many there are.

### Presence (optional, reported)

The one thing the last-input rule cannot express: he is **looking** at the panel
without having sent anything. A client may report that, and it only ever adds
coverage.

```json
{"present": true, "covers_all": true, "covered_panes": [],
 "sources": [{"id": "roam-app", "kind": "app", "panes": [], "covers_all": true,
              "since": 1786516400.1, "last_seen": 1786516490.0, "idle_s": 1.2,
              "expires_in_s": 4.8, "detail": {"device": "pixel"}}],
 "server_time": 1786516491.2}
```

Sources expire; whoever owns one refreshes it. The hub observes nothing here —
earlier versions watched tmux clients and `HIDIdleTime`; both are deleted, the
first because the last-input rule answers the question directly and the second
because it read 13.2 hours idle while he was actively typing over SSH.

---

## 3. HTTP endpoints

### `GET /health` — no auth

```json
{"ok": true, "service": "roam-hub", "version": "1.3.0", "protocol": 1,
 "uptime_s": 2.15,
 "build": {"version": "1.3.0", "protocol": 1, "commit": "6229cdb", "schema": 5,
           "code_mtime": 1786520867.4}}
```

`build` says what code is **actually running** — the deployed commit, the database
schema version, and when the file on disk was last written. A stale service once
served `coverage: null` for two commits while its test suite was green, and no
client could tell. Compare `build.commit` (or `schema`) against what your client
expects and warn loudly rather than silently losing a field.

### `GET /status`

```json
{"ok": true, "version": "1.0.0", "protocol": 1, "uptime_s": 3600.0,
 "tmux_ok": true, "live_channels": 3, "known_channels": 9,
 "latest_event_id": 412, "pending_events": 0, "subscribers": 1,
 "db_path": "/Users/talos/.../hub.sqlite"}
```

`pending_events` — events written straight into the ledger while this process
was **not running**, and not yet adopted. See `POST /notify`. In steady state
it is `0`; anything else means the hub was stopped while something was trying
to tell the wearer about itself. Surface it rather than hiding it.

### `GET /channels`

Query: `include_archived` (bool, default `false`).

```json
{"channels": [ Channel, ... ], "latest_event_id": 412, "server_time": 1786511500.1}
```

Ordering: live channels first, then most recent activity first. Use
`latest_event_id` as the cursor when you then open the WebSocket.

### `GET /channels/{pane}`

`{"channel": Channel}` — 404 if the hub has never heard of that pane.

### `POST /channels/{pane}/send`

```json
{"text": "run the test suite", "enter": true, "origin": "client"}
```

* `text` — required, non-empty. Sent **literally**: a transcript containing the
  words "Enter" or "C-c" is typed, not executed. Multi-line text is delivered as
  one bracketed paste, so it arrives as a single message rather than N prompts.
* `enter` — default `true`. `false` types the text and leaves it unsubmitted.
* `origin` — free-form tag stored in `meta.origin` (`client`, `cli`, …).

Response `200`:

```json
{"event": Event, "channel": Channel}
```

`404` if the pane is not live (nothing was typed). `502` if tmux refused; an
`error` event is recorded and pushed so the failure shows up in the thread.

### `POST /channels/{pane}/interrupt`

Stop what the channel is doing. Sends a **key press**, and records that an
interrupt was issued — not a message.

```json
{"action": "escape", "origin": "client"}
```

* `action` — `escape` (default; stops an agent mid-response) or `interrupt`
  (`C-c` to the foreground process). Anything else is `400`; this is an
  allow-list, not a keystroke passthrough.
* Body may be omitted entirely; it defaults to `escape`.
* Returns `{"event": Event, "channel": Channel}` where the event is
  `kind: "control"`, `body: "escape"`, `meta.key: "Escape"`.
* `404` if the pane is not live, `502` if tmux refused.
* An interrupt does **not** move the conversation: `last_input_source` is
  unchanged, because stopping a run is not answering it.

⚠️ **Do not fire control characters through `/send`.** It used to work — `/send`
types literally — but it stored a `sent` event whose body was a raw control byte,
which reads in the thread as if the user typed it and pollutes the search index.
`/send` now rejects C0 control characters with `400` and points here. Newline,
carriage return and tab are still accepted (multi-line messages).

### `GET /channels/{pane}/history`

Query: `limit` (1–2000, default 200), `since` (event id, **exclusive**),
`include_archived` (default `false`).

```json
{"pane_id": "%0", "events": [ Event, ... ], "latest_event_id": 412}
```

Events are **oldest first**. Without `since` you get the most recent `limit`
events, still oldest first, so the panel can append them in order.

### `DELETE /channels/{pane}/history`

Soft-clear. Rows are flagged, never deleted; they remain readable with
`include_archived=true`.

```json
{"pane_id": "%0", "archived": 12, "deleted": 0}
```

### `POST /channels/{pane}/archive`

Body `{"archived": true}` (or `false` to restore; body may be omitted, defaults to
`true`). Hides a channel from `GET /channels` — for dead panes you are done with.
History is kept. Returns `{"channel": Channel}`.

### `GET /channels/{pane}/capture`

Query: `lines` (1–5000, default 200). Raw recent output of the pane, for read-back
on the panel.

```json
{"pane_id": "%0", "lines": 200, "text": "…"}
```

`404` if the pane is not live. This is the only endpoint that reads the terminal
itself; everything else reads the hub's own history.

### `POST /events` — receipts and outcomes

Where the tmux/Claude hooks POST. Also usable by any tool that wants to drop
something into a channel thread.

```json
{"pane": "%3", "kind": "outcome", "body": "The suite is green — 122 tests.",
 "meta": {"source": "claude-hook", "session_id": "44c6d5f1"}}
```

* `pane` and `pane_id` are accepted interchangeably (`$TMUX_PANE` is called
  `pane` in the shell).
* `kind` — required. Any string; use the table above.
* `body` — for an `outcome`, send the assistant's answer text. The hub computes
  `summary` and applies the 16 KiB cap itself; do not send a `summary`.
* Returns `201` with `{"event": Event}` and pushes it to every WebSocket client.
* If the pane is unknown to the hub, the channel is created first.
* A `receipt` that matches a recent `send` on this pane is the hub's own typing
  coming back; the stored event carries `meta.echo_of` (see *Event*). Post the
  prompt text and let the hub decide — do not try to filter echoes yourself.

### ★ `POST /notify` — "tell the wearer this"

Where a tool sends a status message. `tools/roam-msg` is the client; it is what
every agent and hook on this box calls, and it does nothing but this.

```json
{"text": "build finished — 122 tests green", "pane": "%3",
 "source": "roam-msg", "meta": {"host": "talos"}}
```

* `text` — required, non-empty. What to tell him.
* `pane` — the channel this is about, normally `$TMUX_PANE`. **Omit it when
  there is none** (launchd, cron, ssh) and it is filed on `@host`. Do not
  borrow another pane's id: the message would inherit that conversation's
  coverage and be silenced for a conversation it was never part of.
* `source` / `meta` — free-form; stored on the event as `meta.source` and
  merged into `meta`.

Response `201`:

```json
{"event": Event, "push": true, "reason": "not covered (last input: app)",
 "pending": 0}
```

* `push` — whether the bridge will deliver this to the phone, decided by the
  same `coverage` rule as any other event and stamped on the event itself.
  `true` means *queued*, not *delivered*: the bridge does that, rate-limited.
* `reason` — human-readable, for the CLI to print. `covered by tmux-input`,
  `covered by roam-app`, `nothing recorded -- unknown means push`.
* `pending` — how many events are still waiting to be adopted (below). Normally
  `0`; a client that gets a non-zero should say so.

**When the hub is not running.** The hub, the agents, `roam-msg` and the bridge
are all one box, so an unreachable hub is a stopped *process*, never a network
partition — and a stopped hub means a deaf bridge, so nothing could deliver
anyway. `roam-msg` therefore writes the notice **straight into `hub.sqlite`**
(same file, WAL, `store.py`) with an internal `pending` flag and
`meta.offline: true`. On its next poll the hub claims those rows, publishes
them as ordinary `event` frames and clears the flag, so they take the normal
push path a few seconds late instead of being lost. Read-and-clear happens in
one transaction: an adopted event can never buzz twice. There is no
dead-letter file and no second store of record.

⚠️ **This is the only way in.** Notifications used to be posted straight to the
device with `adb ... cmd notification post`, which meant the hub's policy
governed outcomes and nothing else, and the phone rang while he sat at the
keyboard reading the very pane it was about. Owner: *"what's the point of a
'hub' if all traffic doesn't go through it..."* A status line is now judged by
exactly the rule that judges the answer it is about, and lands in the ledger on
the way past (`memsearch --source ledger`). The one remaining program that
speaks to the device is `tools/roam-push`, and only the bridge runs it.

A notice is deliberately **not** an `outcome`: an outcome is what an agent
answered, and a channel whose last event is a `sent`/`receipt` is `working`.
Filing "I am still going" as an outcome would answer a prompt that is still
open. It is not a `note` either — `note` is not pushed, and this is the kind
that exists to be pushed.

### `GET /presence`

The snapshot above. Cheap; safe to call on resume.

### `POST /presence`

Register or refresh a source. **This is how the client says "I am foregrounded,
stop notifying me"** — first-class, not a later special case.

```json
{"source": "roam-app", "kind": "app", "covers_all": true, "ttl_s": 60,
 "detail": {"device": "pixel"}}
```

* `source` — a stable id you own.
* `panes` — cover specific channels instead of everything (bare `3` or `%3`).
* `ttl_s` — 1–3600. Re-post to stay present; stop posting (or `DELETE`) to lapse.
  Pick a TTL a few times your refresh interval so a crash lapses quickly.
* Returns `{"source": …, "presence": <snapshot>}` and pushes a `presence` frame.

**Recommended client behaviour**: `POST` with **`panes: [<the channel actually on
screen>]`** on foreground, again whenever that changes, and every ~30 s while
foregrounded; `DELETE /presence/{source}` on background. Sending a message already
moves that channel to `app`, so this is only for the case where he is watching
without typing.

> ⚠️⚠️ **Do not send `covers_all: true` from a client with a screen.** This section
> recommended exactly that, and ROAM Touch followed it: the app claimed it covered
> every channel at once, the hub correctly concluded nothing was worth interrupting
> the wearer for, and **his arm went silent for a day**. The buzz path was never
> broken — it was never asked to run, and the only symptom was an absence, which is
> the hardest kind of bug to notice.
>
> `covers_all` means *"I am showing the wearer everything, all of it, right now."*
> Almost nothing is. A client showing one channel covers **one** channel; a client
> on a list or a settings screen covers **none**. The owner's rule: *"haptic and buzz
> when I'm actually on that device, and I'm not in the active channel at the time."*

### `DELETE /presence/{source}`

`{"removed": true, "presence": <snapshot>}`.

### `GET /events`

Query: `since` (default 0), `limit` (1–2000, default 500). Every event after
`since`, across all channels, oldest first. This is the poll-once-on-wake path for
a client that would rather not hold a socket:

```json
{"events": [ Event, ... ], "latest_event_id": 412}
```

Bodies here are trimmed to 4096 chars (`body_truncated`).

### `GET /events/{id}`

One event, **never trimmed** — this is "expand the details" behind a summary.

```json
{"event": Event}
```

`404` if there is no such event.

### Files — browsing `~/Collab`, and handing one to Claude

A read-only window onto two shared folders, so a part can be looked at from the
arm instead of from the desk. Roots are named, not paths: `CAD` and `Photos`.
A **browse path** is `<root>/<relative>` — `CAD/roam-touch/bracer.stl`.

⚠️ **These endpoints also accept `?token=`**, exactly as `/ws` does, because a
browser cannot put an `Authorization` header on `<img src>` or a navigation. The
pages send `Referrer-Policy: no-referrer` so the token in the URL cannot leak
onward. Prefer the header wherever you can set one.

#### `GET /files`

Query: `path` (default `""`, which lists the roots).

```json
{"path": "CAD/roam-touch", "parent": "CAD", "entries": [
  {"name": "archive", "path": "CAD/roam-touch/archive", "kind": "dir",
   "size": 0, "mtime": 1786760296.9},
  {"name": "bracer.step", "path": "CAD/roam-touch/bracer.step", "kind": "cad",
   "size": 963991, "mtime": 1786762523.9,
   "mesh_path": "CAD/roam-touch/bracer.stl"}
]}
```

`kind` is `dir` | `image` | `mesh` (STL) | `cad` (STEP and friends) | `file`.
Dot-files are never listed. **`mesh_path`** appears on a `cad` entry when the
build pipeline has dropped an `.stl` beside it — that is the thing a client can
actually render.

`400` for a path that tries to leave the shared folders, `404` for one that is
simply not there.

#### `GET /files/raw` · `GET /files/thumb`

Query: `path`; `thumb` also takes `size` (48–1024, default 320). `raw` is the
bytes, served inline. `thumb` is a cached JPEG, **falling back to the original**
if it cannot be made — so a client can always just use it.

#### `POST /share`

```json
{"path": "CAD/roam-touch/bracer.stl"}
```

Copies the file into `~/.claude/dropzone/inbox/`. Never moves it: the shared
folders are his.

```json
{"ok": true, "path": "CAD/…/bracer.stl", "name": "bracer.stl",
 "inbox": "/Users/talos/.claude/dropzone/inbox/bracer.stl",
 "note": "reaches Claude on the next prompt, via the dropzone hook"}
```

★ **"Shared" means "will be in front of Claude on his next prompt"**, not "is on
disk". Claude does not watch the filesystem; the `UserPromptSubmit` hook moves
the inbox into the dropzone and *names* each file, and the naming is what makes
it visible. Same door the Google Photos album comes through — one delivery
route, one place for it to break. Tell the user that honestly; do not report
"sent" as if it had already been read.

#### `GET /browse` · `GET /view/stl` — HTML

For a phone browser, not for the app. `/view/stl` takes `path` and answers
**`415` for anything but `.stl`** — a `.step` is a b-rep needing an OCCT-class
kernel, which is not something to attempt on the client. Point it at the
`mesh_path` instead.

⚠️ **The client is Chrome 74 (2019) on a Pixel 1 and cannot be updated** — it is
signature-pinned with no Play Store on the device. Anything served to it must
avoid `?.`, `??`, class fields, `:has()` and flexbox `gap`; three.js is pinned at
r112 for the same reason. If you touch `web/`, read the header comment in
`web/browse.html` and run the suite — `tests/test_files_api.py` fails on modern
syntax rather than letting the wrist find out.

### Radio — streams he can actually play

No music lives on the device and no account is signed in on it, so the answer to
"play something" is **internet radio in a bare `<audio>` element**. Stations come
from the open [radio-browser.info](https://www.radio-browser.info/) directory —
no key, no account — fetched **by the hub**, never by the client.

#### `GET /radio/stations`

Query: `q` (≤64 chars). Empty `q` is the curated favourites; anything else is a
name search, most-played first.

```json
{"kind": "favourites", "query": "", "source": "live", "fetched_at": 1786763001.4,
 "stations": [
   {"uuid": "960cf833-0601-11e8-ae97-52543be04c81", "name": "SomaFM Groove Salad",
    "url": "https://ice5.somafm.com/groovesalad-128-mp3",
    "codec": "MP3", "bitrate": 128, "tags": "ambient, downtempo"}
 ]}
```

★ **Every station in that list is playable by a plain `<audio>` tag.** HLS,
`.pls`/`.m3u` playlists, non-HTTP schemes and any codec outside MP3/AAC are
filtered out server-side, because a station that lists and then plays silence is
indistinguishable from a broken radio at arm's length. **Do not add a station
from another source without applying the same filter** (`radio.playable`).

`source` is `live` | `cache` | `stale` | `builtin`. The last two mean the
directory was unreachable and this is the last good answer, or the baked-in
favourites — **say so in the UI**; some of those URLs may have rotted. `502` is
a search with nothing cached behind it; the hub is fine, the directory is not.

#### `GET /radio` — HTML

The player page, for a phone browser: two columns (now-playing left, list
right), 44px+ targets, one `<audio>` element and no library. Same Chrome 74
rules as above — `tests/test_radio_api.py` and `tests/test_files_api.py` hold
the line.

★★ **It keeps both halves of Nexus's audio contract**, which the app defined
before this page existed (`channels/audio/WebViewPlayback.kt`):

* it defines `window.RoamRadio = {play(volume), pause(), setVolume(volume)}`, the
  hook the app prefers over poking `<audio>` elements itself. `pause()` **hangs
  up** (drops `src`) rather than pausing — this is live radio, and a resumed
  buffer leaves him permanently behind the broadcast — and `play()` re-opens the
  stream, but only if he had asked for music in the first place;
* it calls `RoamAudio.onPlay()` / `.onPause()` **for his actions only**, so the
  app knows whether music is wanted and whether a PTT press has anything to put
  back afterwards. Reporting the app's own resume would loop.

⚠️ The app takes **no Android media focus** for this page — the WebView's own
Chromium already holds it, and a second request from the same process revoked it
and paused the station a heartbeat after starting it. Calls and prompts interrupt
Chromium, which suspends and resumes the element itself.

⚠️ `audio.volume` is ignored on Android — the hardware keys are the only volume
there is. A duck therefore arrives as pause-and-return, not as "quieter".

⚠️ Most stream URLs are plain `http://`. Harmless while the hub is plain HTTP
over Tailscale; **if the hub ever gets TLS, mixed content silently kills every
one of them.**

---

## 4. WebSocket

**⚠️ Build the URL from the HTTP base; do not hard-code a `ws://` string.** Several
HTTP clients (OkHttp's `HttpUrl` among them) reject any scheme but `http`/`https`
and throw when handed `ws://…` — on Android that surfaced as a crash inside a
coroutine and a restart loop. The upgrade to WebSocket is negotiated by the
`Upgrade: websocket` handshake, not by the scheme in the string:

```
http://talos:8787/ws?since=<last_event_id>     ← give clients this
ws://talos:8787/ws?since=<last_event_id>       ← equivalent on the wire; only use it
                                                 if your library demands it
```

Both reach the same endpoint. Take the base URL you already use for REST, append
`/ws`, and let the library perform the upgrade — OkHttp does exactly that for
`Request.Builder().url("http://…/ws")` passed to `newWebSocket`.

Auth: `Authorization: Bearer <token>` header (preferred), or `?token=<token>` when
the client cannot set headers. `since` is optional; omit it on a first connection.

On a bad token the hub accepts the handshake, sends
`{"type":"error","detail":"unauthorised"}` and closes with code **4401**.

Every frame is a JSON object with a `type`. Ignore unknown types.

### Server → client

| type | payload | notes |
|---|---|---|
| `hello` | `{protocol, version, server_time, latest_event_id, channels: [Channel], presence}` | always the first frame |
| `backlog` | `{since, events: [Event]}` | only when `?since=` was given; oldest first; sent once, right after `hello` |
| `event` | `{event: Event}` | one new event, live |
| `channels` | `{channels: [Channel], server_time}` | the pane set or a pane title changed — replace your list |
| `channel` | `{channel: Channel}` | one channel changed (archive/restore) |
| `activity` | `{panes: {"%0": 1786511500.3}, server_time}` | those panes' output just moved — update `last_output_at`, reset `idle_s` to ~0. At most one per 2 s poll, and none at all while everything is quiet. |
| `history_cleared` | `{pane_id, archived}` | someone soft-cleared a thread |
| `presence` | the presence snapshot, inline | where he is changed — update suppression. Emitted only on real change, not per poll. |
| `ping` | `{t}` | app-level heartbeat, every 30 s of silence. No reply needed. |
| `pong` | `{t}` | reply to a client `ping` |
| `desync` | `{latest_event_id}` | the client fell too far behind; the hub closes with 1011 — reconnect with `?since=` |

Events in `backlog` are never repeated as `event` frames.

### Client → server

| type | payload | notes |
|---|---|---|
| `ping` | `{"type": "ping"}` | answered with `pong` |

There is no `send` frame: sending goes over `POST /channels/{pane}/send` so there
is exactly one write path with one place to report failure. The resulting `sent`
event arrives on the socket like any other.

Send only JSON objects. A non-JSON frame ends the connection.

### Client algorithm

1. `GET /channels` → paint the list, remember `latest_event_id` as `cursor`.
2. Connect to `<base>/ws?since=<cursor>` (keep the http(s) base — see §4).
3. `hello` → replace the channel list (authoritative).
4. `backlog` → append in order; `cursor = max(cursor, last id)`.
5. `event` → append to that channel's thread; `cursor = event.id`. Show
   `summary`; keep `body` for the expanded view.
6. `channels` / `channel` → replace list / patch one entry. `activity` → update
   `last_output_at` for those panes and re-render the live indicator. `presence`
   → replace your presence view.
7. When the user expands an event whose `body_truncated` is `true` →
   `GET /events/{id}`.
8. On `desync`, on close, or on any error → reconnect with `?since=<cursor>`,
   backing off (1 s, 2 s, 4 s … 30 s). Nothing is lost: the store replays it.
9. Never poll `GET /channels` on a timer. That is what the socket is for.

**The app is a normal Android app**, not a kiosk — the notification shade,
Settings and recents stay, so the client will be backgrounded, doze-throttled and
killed like any other app. Design for the socket dropping: reconnect with
`?since=<cursor>` on resume, or `GET /events?since=` once on wake. Nothing on the
hub assumes the panel is the only thing on screen or that a client is connected.

---

## 5. What the hub does not do (yet)

* **No STT/TTS.** Whisper (`talos:10300`) and Piper (`talos:10200`) are separate
  Wyoming services the client talks to directly. The hub never sees audio.
* **No confirmation state.** "send «transcript» to «channel»?" is entirely
  client-side; the hub only ever sees the confirmed send.
* **One host.** Every channel is a pane on talos. A multi-box hub would federate
  by prefixing pane ids with a host — the client should treat `pane_id` as an
  opaque string so that change does not break it.
* **One token, no users.** There is no per-device identity and no rotation
  endpoint.
