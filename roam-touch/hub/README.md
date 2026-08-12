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
channels.py   tmux: discover panes, send keys, capture output
store.py      SQLite event log, per channel, never hard-deleted
hub.py        FastAPI service + WebSocket + the tmux poller
tests/        pytest; tmux is faked at channels._run, the one shell-out
```

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

`roam-hub-hook` is in this directory: it reads `$TMUX_PANE`, and POSTs
`{"pane": "$TMUX_PANE", "kind": "receipt|outcome"}` with the bearer token. It exits
0 and silently does nothing when `$TMUX_PANE` is unset or the hub is unreachable —
a hook must never be able to break the session it is reporting on.

Verify by hand before installing it:

```bash
./roam-hub-hook receipt && ./roam-hub-hook outcome   # from inside a tmux pane
curl -s -H "Authorization: Bearer $(cat hub-token.txt)" \
     "http://100.67.237.109:8787/channels/${TMUX_PANE#%}/history" | python3 -m json.tool
```

Until that is wired, channels still work — `sent` events are recorded by the hub
itself, and `status` returns to `idle` only when something posts an `outcome`.
