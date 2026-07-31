# Roam Android Relay

Native Android relay for the Roam phone-owned mode.

Flow:

```
Roam/XIAO BLE -> Android foreground service -> TCP over Wi-Fi -> Mac receiver
```

The app scans for `Roam`/`Roam2`, connects to service `FF00`, subscribes to:

- `FF02` action/status notifications
- `FF03` audio notifications

It writes `FF04` control commands back to Roam. For the first vertical slice, pressing the Roam Android dictation action toggles mic streaming by sending `start audio` / `stop audio`.

The Mac receiver listens on TCP port `8765` by default:

```bash
node scripts/roam-relay-receiver.mjs
```

For the current tmux assistant workflow, run the durable receiver from the repo:

```bash
scripts/start-roam-relay-tmux.sh 8765
```

This starts a `roam-relay` tmux session, transcribes Roam PTT audio with local
`mlx_whisper`, and injects transcripts into the configured tmux target with
`ROAM_RELAY_INJECT_MODE=tmux-submit`. The default `ROAM_TMUX_TARGET` is `0:0`;
set it explicitly when the assistant lives in another tmux window.

Status feedback goes back to Roam through the same socket. The receiver sends
frame type `3` text to Android; Android chunks it into `FF01` writes for the
wrist display. In `tmux-submit` mode the message is already submitted when Roam
shows `Sent`. In draft mode (`ROAM_RELAY_INJECT_MODE=tmux`) Roam shows `Ready`;
press Middle short/action `10` to submit after that.

Long receiver feedback is split into numbered one-screen pages before it is
broadcast. The receiver sends the final page first and page `1/N` last, so
Roam's newest-message view starts at the beginning and the older/down scroll
button moves through the rest of the reply.

The relay service source also waits 300 ms after each `FF01` text write before
draining the next GATT operation. This protects the current firmware path where
text writes are consumed by the main loop instead of acknowledged at the
application layer.

Manual updates can be pushed through the relay without taking over BLE:

```bash
scripts/roam-relay-notify.mjs "Build complete"
```

For today's work Mac, set the Android app host to this Mac's LAN IP. On the
2026-07-30 workbench that was `192.168.86.63`.

When the Mac mini becomes the always-on business proxy, install the receiver
there and point the Android app at the Mac mini's reserved LAN IP:

```bash
scripts/install-roam-relay-launchd.sh
```

That installs `~/Library/LaunchAgents/com.roam.relay-receiver.plist`, keeps the
receiver alive, and writes logs to `~/Library/Logs/Roam/relay.out.log` and
`~/Library/Logs/Roam/relay.err.log`. The rolling WAV capture is
`~/Library/Logs/Roam/roam-relay-latest.wav`.

Per-session WAVs are under `~/Library/Logs/Roam/sessions/`. Transcript and
injection audit records are appended to `~/Library/Logs/Roam/transcripts.jsonl`.

To capture decoded relay audio for inspection:

```bash
node scripts/roam-relay-receiver.mjs --wav /tmp/roam-relay.wav
```

The receiver frame format is `[type:1][length:2 big-endian][payload]`; type `1`
is event JSON and type `2` is the binary `FF03` audio packet.

The current debug APK is built at:

```bash
android-relay/app/build/outputs/apk/debug/app-debug.apk
```

For bench testing over ADB on current Android builds, start through the visible
Activity path. This avoids foreground-service launch denial while the phone is
locked or dreaming:

```bash
adb shell input keyevent KEYCODE_WAKEUP
adb shell wm dismiss-keyguard
adb shell am start -S -W --user 0 -n io.roam.relay/.MainActivity --es host 192.168.86.63 --ei port 8765 --ez autoStart true
```

The protected broadcast receiver exists for controlled starts when Android
allows them:

```bash
adb shell am broadcast -n io.roam.relay/.RelayControlReceiver -a io.roam.relay.START --es host 192.168.86.63 --ei port 8765
```

Stop it with:

```bash
adb shell am broadcast -n io.roam.relay/.RelayControlReceiver -a io.roam.relay.STOP
```

Build notes:

- Open `android-relay/` in Android Studio.
- The local machine currently has Android SDK/ADB but no `gradle` CLI in PATH.
- Android 12+ requires Bluetooth runtime permissions.
- Android 13+ requires notification permission for the foreground-service notification.
- Android 14+ requires `foregroundServiceType="connectedDevice"` plus the matching permission.
