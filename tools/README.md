# Roam Tools — pushing a message to the wrist

The user wears ROAM Touch so he does not have to sit at the computer. These are
the tools that put something on it.

⚠️ **BLE is retired (2026-08-11).** `roam-send` (Swift/CoreBluetooth) and the
127-byte chunking are history — see git log if you ever need them. ROAM Touch is
a phone on the tailnet, reached over the network from anywhere.

## The one rule

```
agent / hook / script          the hub                     the bridge          the phone
   roam-msg  ──POST /notify──▶  decides: push or not  ──WS──▶  roam-push  ──adb──▶  📱
```

**`roam-msg` is the only thing you call. It never touches the device.**

The hub owns the notification policy — *reply where the last message came from*:
a prompt typed in tmux means he is at the keyboard, so its outcome (and every
status line about it) stays quiet; a message sent from ROAM means the answer
belongs on ROAM. That rule lives in exactly one place, `hub/hub.py`
(`_coverage_for`), and everything that wants the wrist obeys it by going through
the hub.

It was not always so. `roam-msg` used to shell straight to `adb`, so the policy
governed outcomes and nothing else and the phone rang all day while he sat two
feet from the screen it was about. Owner: *"what's the point of a 'hub' if all
traffic doesn't go through it..."*

## `roam-msg` — the client

```bash
~/Projects/roam/tools/roam-msg "Build complete. 0 errors."
~/Projects/roam/tools/roam-msg --pane 3 "needs your input"
```

* Attributes the message to `$TMUX_PANE` automatically, which is what lets the
  hub apply "he is typing in that pane". `--pane N` overrides it. With no pane
  at all (launchd, cron, ssh) it claims nothing and the hub files it on the
  `@host` channel, where nothing covers it, so it pushes.
* Prints what the hub decided — `%3 — no push (covered by tmux-input)` — so a
  silent send is never indistinguishable from a broken one.
* Lands in the ledger either way. `memsearch "…" --source ledger` finds it later.
* **If the hub process is not running the message goes into the ledger**, not to
  the device and not to a file. Everything here is one box, so an unreachable
  hub is a stopped process — and a stopped hub is a deaf bridge, so nothing
  could deliver anyway; an adb push at that moment would be the only thing
  still arriving on his wrist, reading as a healthy pipeline while every real
  outcome is stalled. The row lands in `hub.sqlite` flagged `pending`
  (`meta.offline: true`), and the hub adopts and pushes it on its next poll. So
  the message arrives late rather than never, from one store of record.
  Bounded: past `MAX_PENDING` (200) waiting messages it is dropped and says so.
* Env: `ROAM_HUB`, `ROAM_HUB_TOKEN_FILE`, `ROAM_HUB_TIMEOUT`.

## `roam-notify` — fire and forget

`roam-msg` backgrounded with output discarded. For hooks that must not block or
print.

## `roam-push` — ⚠️ the device transport, not for you

The only program that speaks to the phone (`adb ... cmd notification post`). It
holds no policy: told to post, it posts. **Only the bridge
(`com.talos.roam-bridge`) runs it.** Calling it by hand bypasses every rule
above and rings his phone while he is reading the pane it is about — which is
the exact bug the split exists to fix.

It makes a **sound**, and cannot be silenced from here: `cmd notification post`
hardcodes channel `shellcmd` at `IMPORTANCE_DEFAULT`, and Android 10 (SDK 29, on
the device) has no `cmd notification` subcommand for importance. The fix is for
Nexus to post these itself on an `IMPORTANCE_LOW` channel — it already runs a
foreground service with one and already holds the hub socket — after which the
adb path retires entirely. Failing that, one long-press → *Silent* on a ROAM
notification locks the channel down for good.

## Tests

`roam-msg` is a hub client, so its tests live with the hub:

```bash
cd ~/Projects/roam/roam-touch/hub && .venv/bin/python -m pytest -q
```

`tests/test_roam_msg.py` asserts the architecture, not just the behaviour: the
client cannot reach the device, does not second-guess the hub, and the bridge
does not shell out to the client (which would notify itself in a loop).
