# Roam Phone Relay v1

Goal: keep Roam on the tiny XIAO nRF52840 Sense and make the phone the long-range relay. Roam connects to Android over BLE; Android relays control events and audio to the Mac over Wi-Fi.

## Topology

```
Roam/XIAO -> BLE GATT -> Android relay -> Wi-Fi/TCP -> Mac receiver -> assistant input
```

Roam should not dual-connect to Mac and Android for this mode. Android owns the BLE connection. Mac receives everything from Android over the LAN.

Current deployment shape:

- Now: Android relay points at the work Mac receiver.
- Later: Android relay points at the Mac mini, which becomes the always-on business proxy.
- BOX-3/Warble-style hardware remains a possible room/base-station client, but it should speak to the same Mac mini receiver instead of replacing the wrist path.

## BLE Service

Use the existing custom service so old Mac text push remains compatible.

| UUID | Direction | Purpose |
|---|---|---|
| `FF00` | service | Roam text/control/audio relay service |
| `FF01` | central -> Roam | Display text push, existing behavior |
| `FF02` | Roam -> central notify | Button/action/status event packets |
| `FF03` | Roam -> central notify | Audio packets |
| `FF04` | central -> Roam | Relay control packets |

Mac-to-Roam display updates in phone-relay mode must go through Android. Do not
use direct Mac BLE while Android owns Roam. The Mac receiver sends socket frame
type `3` text payloads to Android; Android chunks those into `FF01` writes.
`FF01` is limited to 128 bytes on the firmware side, so Android uses 120-byte
UTF-8 chunks.

The useful OLED display budget is smaller than the BLE budget. Receiver
feedback splits longer responses into numbered one-screen pages and sends them
last-page-first so Roam's newest-message view lands on page `1/N`. The
scroll-back/older button then walks through `2/N`, `3/N`, etc. If a response is
too long for the configured page cap, the final page says `Ask continue for
more.` instead of pointing Nick back to the laptop.

Do not blast page frames. The 2026-07-30 live test showed skipped pages
because Roam firmware had a single incoming text slot and message haptics can
hold the main loop for about 200 ms. The Mac receiver now spaces feedback
frames by 350 ms, Android settles 300 ms after `FF01` writes, and P2 firmware
queues 16 incoming text writes.

Mac socket broadcast is not the same thing as wrist display delivery. A
closeout notification was missed during a reconnect/status window after the P2
flash. The receiver now caches recent manual notices from
`scripts/roam-relay-notify.mjs` and replays them once after a non-local Android
client reconnects or Roam sends a ready/status event within the replay window.

## Event Packets (`FF02`)

Fixed 8-byte little-endian packet:

| Byte | Field |
|---:|---|
| 0 | version, currently `1` |
| 1 | event type |
| 2 | action id, or `0` |
| 3 | profile id |
| 4-7 | `millis()` timestamp, uint32 little-endian |

Event types:

| Value | Meaning |
|---:|---|
| `1` | action fired |
| `2` | push-to-talk start |
| `3` | push-to-talk stop |
| `4` | relay status |

## Control Packets (`FF04`)

Minimum 2-byte packet:

| Byte | Field |
|---:|---|
| 0 | version, currently `1` |
| 1 | command |

Commands:

| Value | Meaning |
|---:|---|
| `1` | start audio stream |
| `2` | stop audio stream |
| `3` | ping/status request |

## Audio Packets (`FF03`)

Packet format is stream-friendly, sequence-numbered, and carries enough ADPCM state for the receiver to recover after a dropped packet:

| Byte | Field |
|---:|---|
| 0 | version, currently `1` |
| 1 | codec id |
| 2-3 | sequence, uint16 little-endian |
| 4-7 | `millis()` timestamp, uint32 little-endian |
| 8-9 | ADPCM predictor, int16 little-endian; `0` for stateless codecs |
| 10 | ADPCM step index; `0` for stateless codecs |
| 11 | flags, currently `0` |
| 12..N | audio payload |

Codec ids:

| Value | Codec |
|---:|---|
| `0` | reserved |
| `1` | PCM16 mono, 16 kHz, little-endian |
| `2` | IMA ADPCM mono, 16 kHz |

The current firmware uses IMA ADPCM at 16 kHz mono to keep BLE throughput practical. PCM remains defined for bench diagnostics.

## Android Relay

Android app requirements:

- Use `CompanionDeviceManager` association for Roam.
- Maintain the BLE connection from a foreground service with `connectedDevice` type.
- Subscribe to `FF02` and `FF03`; write display/status/control to `FF01`/`FF04`.
- Relay to Mac with a persistent TCP socket.
- Show a persistent notification while active so Android does not silently stop the relay.
- Bench ADB starts need a visible activity on current Android builds; a background broadcast can be denied from starting the foreground service while the phone is locked/dreaming.
- If Android discovers `FF00` but audio is absent, check for `FF03` in the discovered GATT table. A stale 2026-07-30 firmware exposed `FF01`, `FF02`, and `FF04`, but not `FF03`; reflashing with current P2 firmware fixed that live.
- Live 2026-07-30 verification: Android subscribed `FF02` and `FF03`, relayed multiple PTT sessions over Wi-Fi to the Mac receiver, and the WAV capture grew from real Roam audio frames.

## Mac Receiver

Mac receiver requirements:

- Listen on a LAN TCP socket.
- Accept JSON event frames and binary audio frames from Android.
- Log packet loss from audio sequence numbers. Sequence tracking resets on each PTT start event because firmware starts each audio session at sequence `0`.
- Optionally write decoded 16 kHz mono PCM as a WAV capture.
- Keep the WAV header current while running so `roam-relay-latest.wav` remains inspectable without stopping the daemon.
- Transcribe PTT sessions with local `mlx_whisper` and inject the transcript into the active assistant workflow.
- For interactive/tmux use, start the receiver in a durable tmux session with `scripts/start-roam-relay-tmux.sh 8765`. It defaults to `ROAM_RELAY_INJECT_MODE=tmux-submit` and `ROAM_TMUX_TARGET=0:0`; override `ROAM_TMUX_TARGET` when the assistant lives in another tmux session/window.
- `tmux-submit` mode auto-submits after STT injection. The wrist status sequence is `Listening` -> `Transcribing` -> `Sent`. When `Sent` appears, the message has already been submitted.
- `tmux` mode drafts but does not submit. The wrist status sequence is `Listening` -> `Transcribing` -> `Ready`; after `Ready`, press Middle short/action `10` to submit.
- Manual agent/process updates can be pushed without taking BLE away from Android using `scripts/roam-relay-notify.mjs "message"`.
- Long manual updates are paged by the Mac receiver before broadcast. The
  receiver currently uses about 58 display characters per page and up to 8
  pages, with a 350 ms gap between downstream frames.
- For always-on launchd use on a Mac, install with `scripts/install-roam-relay-launchd.sh`. GUI paste/submit modes use AppleScript and may need macOS Accessibility approval; tmux modes do not need AppleScript.
- LaunchAgent logs are `~/Library/Logs/Roam/relay.out.log` and `~/Library/Logs/Roam/relay.err.log`; its rolling WAV capture is `~/Library/Logs/Roam/roam-relay-latest.wav`.
- Per-session WAVs are written to `~/Library/Logs/Roam/sessions/`; transcripts and injection audit are in `~/Library/Logs/Roam/transcripts.jsonl`.

Current phone-relay button command mapping:

| Roam action | Button gesture | Mac receiver behavior |
|---:|---|---|
| `2` | Index short | Toggle PTT audio; receiver transcribes on stop and injects with the configured mode |
| `3` | Index long | tmux next pane, using native `tmux select-pane` when available |
| `4` | Pinky short | Shift+Tab / cycle mode |
| `6` | Middle long | `y` then Enter |
| `7` | Middle double | Tab then Enter |
| `8` | Ring short | Escape |
| `9` | Ring long | Ctrl+C |
| `10` | Middle short | Enter |

Receiver behavior for local-only display actions:

- Actions `13`-`17` are local to Roam display/control and are ignored by the Mac command dispatcher.
- This matters for scroll buttons: if the receiver pushes feedback for action `15`/`16`, the new feedback message resets the OLED to newest and makes scrolling appear broken.

Live 2026-07-30 verification:

- Roam -> Android -> Mac PTT produced correct transcription and `tmux-submit` injection for "Are you down with OPP?"
- Roam action `10` arrived over Android -> Wi-Fi and dispatched as tmux Enter.
- Roam action `3` arrived over Android -> Wi-Fi and dispatched through the tmux backend; Nick confirmed the pane switch worked visibly.
- Paged reply broadcast was verified with a live receiver capture: a long test
  message emitted pages `6/6` through `1/6` in socket order, leaving `1/6` as
  the current OLED page and older/down scroll available for the rest.
- Follow-up skipped-page test reproduced missing pages on the wrist when frames
  were sent too quickly. After adding receiver pacing, a seven-page capture
  emitted every page `7/7` through `1/7` at about 350 ms intervals. Nick then
  confirmed the paced multi-page wrist message was coherent and readable, with
  every page visible page-by-page. A longer follow-up dictated from Roam also
  relayed and submitted cleanly, confirming longer inbound voice messages work
  through the current audio/STT/tmux path.
- Android GATT pacing APK was installed with `adb install -r`, relaunched
  against `192.168.86.63:8765`, and reconnected to Roam. P2 queued-text
  firmware was flashed with `make p2-flash-sealed`; Roam rebooted as normal PID
  `0x8045`, sent a fresh status event, and Nick confirmed the post-flash page
  test was good.
- Follow-up notification test: Nick missed the final closeout message around a
  reconnect/status event. A short ping delivered successfully, then the receiver
  replay guard was added and the durable receiver was restarted. Nick confirmed
  the fresh post-restart notification arrived.
- Good PTT sessions may still show occasional one-frame BLE audio gaps. A short range/case-placement issue produced a poor 1.13s transcript; the stronger 2.96s test transcribed correctly.

## Hardware Notes

- The XIAO Sense onboard PDM mic must have an acoustic opening. If the case muffles it, move to a small offboard PDM/I2S MEMS mic near a sound port.
- This path prioritizes a slimmer wearable. ESP32-S3 stays useful as a bench fallback for direct Wi-Fi audio, not as the preferred wrist build.
