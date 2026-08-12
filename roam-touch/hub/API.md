# ROAM Touch hub — client contract

Version `1.0.0`, protocol `1`. This document is the contract the Android client is
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
| WebSocket | `ws://talos:8787/ws` |
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

---

## 2. Objects

### Event

```json
{
  "id": 412,
  "pane_id": "%0",
  "kind": "outcome",
  "body": "Tailscale beats the BLE permission wall — it just worked from here with\nno pairing.\n\nOne thing worth knowing: `roam-msg` returned nothing at all…",
  "summary": "Tailscale beats the BLE permission wall — it just worked from here with no pairing. One thing worth knowing: roam-msg returned nothing at all…",
  "meta": {"source": "claude-hook", "session_id": "44c6d5f1"},
  "ts": 1786511500.066308,
  "archived": false
}
```

* `id` — monotonically increasing, never reused, unique across all channels. This
  is the client's catch-up cursor.
* `body` — the full text. For an `outcome` this is **the assistant's actual
  answer**, pulled out of the session transcript; markdown intact.
* `summary` — always present, always safe to speak and to glance at: markdown
  scaffolding removed, code blocks and tables reduced to `[code, 12 lines]` /
  `[table, 4 rows]`, decorative symbols and emoji dropped (Piper says nothing for
  them), cut at a sentence boundary within **280 characters**. **Show `summary` on
  the strip and hand it to Piper; show `body` in the thread.** Never re-derive it
  client-side — one implementation, one behaviour.
* `ts` — epoch seconds, UTC, float.
* `meta` — free-form JSON object; may be `{}`. Never `null`.
  `meta.truncated_from` appears when the body exceeded the **16 KiB** storage cap
  and holds the original character count; the body then ends with `… [truncated]`
  and the untruncated text is still available from `/capture` and the transcript.
* `archived` — soft-deleted. Only ever `true` in responses you explicitly asked
  for with `include_archived=true`.

**Kinds.** Treat this list as open — render an unknown kind as a plain note
rather than dropping it.

| kind | meaning |
|---|---|
| `sent` | the wearer sent this text to the channel (`body` = the text) |
| `receipt` | a prompt was submitted (`body` = the prompt, when the hook knows it) |
| `outcome` | the agent finished (`body` = **what it said**, not "finished") |
| `opened` | the hub first saw this pane (`body` = its label) |
| `closed` | the pane went away; the channel is dead |
| `note` | free-form note |
| `error` | a send failed (`meta.attempted` = what was not typed) |

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
  "event_count": 7,
  "last_event": { "...Event, or null..." }
}
```

* `label` — what to show as the channel name. It is the tmux pane title, which
  for a Claude pane is the session summary. Falls back to `session:window.pane`
  when no title is set.
* `live` — the pane exists on the host right now. `window`, `index` and `command`
  are `null` when it does not.
* `status` — `"idle"` | `"working"` | `"dead"`:
  * `dead` — the pane is gone. History is still readable; sending returns 404.
  * `working` — the last event was a `sent` or `receipt`; the agent owes an
    outcome.
  * `idle` — anything else.
* A channel whose pane has died **stays in the list** with its history and its
  last known label. That is deliberate: the outcome you are waiting for may be
  the last thing that pane ever said.

---

## 3. HTTP endpoints

### `GET /health` — no auth

```json
{"ok": true, "service": "roam-hub", "version": "1.0.0", "protocol": 1, "uptime_s": 2.15}
```

### `GET /status`

```json
{"ok": true, "version": "1.0.0", "protocol": 1, "uptime_s": 3600.0,
 "tmux_ok": true, "live_channels": 3, "known_channels": 9,
 "latest_event_id": 412, "subscribers": 1, "db_path": "/Users/talos/.../hub.sqlite"}
```

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

### `GET /events`

Query: `since` (default 0), `limit` (1–2000, default 500). Every event after
`since`, across all channels, oldest first. This is the poll-once-on-wake path for
a client that would rather not hold a socket:

```json
{"events": [ Event, ... ], "latest_event_id": 412}
```

---

## 4. WebSocket

```
ws://talos:8787/ws?since=<last_event_id>
```

Auth: `Authorization: Bearer <token>` header (preferred), or `?token=<token>` when
the client cannot set headers. `since` is optional; omit it on a first connection.

On a bad token the hub accepts the handshake, sends
`{"type":"error","detail":"unauthorised"}` and closes with code **4401**.

Every frame is a JSON object with a `type`. Ignore unknown types.

### Server → client

| type | payload | notes |
|---|---|---|
| `hello` | `{protocol, version, server_time, latest_event_id, channels: [Channel]}` | always the first frame |
| `backlog` | `{since, events: [Event]}` | only when `?since=` was given; oldest first; sent once, right after `hello` |
| `event` | `{event: Event}` | one new event, live |
| `channels` | `{channels: [Channel], server_time}` | the pane set or a pane title changed — replace your list |
| `channel` | `{channel: Channel}` | one channel changed (archive/restore) |
| `history_cleared` | `{pane_id, archived}` | someone soft-cleared a thread |
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
2. Connect `ws://…/ws?since=<cursor>`.
3. `hello` → replace the channel list (authoritative).
4. `backlog` → append in order; `cursor = max(cursor, last id)`.
5. `event` → append to that channel's thread; `cursor = event.id`.
6. `channels` / `channel` → replace list / patch one entry.
7. On `desync`, on close, or on any error → reconnect with `?since=<cursor>`,
   backing off (1 s, 2 s, 4 s … 30 s). Nothing is lost: the store replays it.
8. Never poll `GET /channels` on a timer. That is what the socket is for.

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
