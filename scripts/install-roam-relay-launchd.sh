#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_BIN="$(command -v node)"
PLIST="$HOME/Library/LaunchAgents/com.roam.relay-receiver.plist"
LOG_DIR="$HOME/Library/Logs/Roam"
PORT="${1:-8765}"
INJECT_MODE="${ROAM_RELAY_INJECT_MODE:-tmux-submit}"
TMUX_TARGET="${ROAM_TMUX_TARGET:-0:0}"
STT_MODEL="${ROAM_RELAY_STT_MODEL:-mlx-community/whisper-large-v3-turbo}"
STT_COMMAND="${ROAM_RELAY_STT_COMMAND:-$(command -v mlx_whisper || true)}"
STT_COMMAND="${STT_COMMAND:-/opt/homebrew/bin/mlx_whisper}"

mkdir -p "$LOG_DIR"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.roam.relay-receiver</string>
  <key>ProgramArguments</key>
  <array>
    <string>${NODE_BIN}</string>
    <string>${ROOT}/scripts/roam-relay-receiver.mjs</string>
    <string>--host</string>
    <string>0.0.0.0</string>
    <string>--port</string>
    <string>${PORT}</string>
    <string>--wav</string>
    <string>${LOG_DIR}/roam-relay-latest.wav</string>
    <string>--transcribe</string>
    <string>--stt-command</string>
    <string>${STT_COMMAND}</string>
    <string>--stt-model</string>
    <string>${STT_MODEL}</string>
    <string>--inject</string>
    <string>${INJECT_MODE}</string>
    <string>--commands</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/relay.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/relay.err.log</string>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>ROAM_TMUX_TARGET</key>
    <string>${TMUX_TARGET}</string>
  </dict>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"
echo "Installed Roam relay receiver on port ${PORT}: ${PLIST}"
echo "Logs: ${LOG_DIR}/relay.out.log and ${LOG_DIR}/relay.err.log"
echo "Latest WAV capture: ${LOG_DIR}/roam-relay-latest.wav"
echo "Transcripts: ${LOG_DIR}/transcripts.jsonl"
echo "Inject mode: ${INJECT_MODE}"
echo "tmux target: ${TMUX_TARGET}"
echo "STT command: ${STT_COMMAND}"
