#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_BIN="$(command -v node)"
LOG_DIR="$HOME/Library/Logs/Roam"
PORT="${1:-8765}"
PID_FILE="$LOG_DIR/relay-user.pid"
PLIST="$HOME/Library/LaunchAgents/com.roam.relay-receiver.plist"
INJECT_MODE="${ROAM_RELAY_INJECT_MODE:-tmux-submit}"
TMUX_TARGET="${ROAM_TMUX_TARGET:-0:0}"
STT_MODEL="${ROAM_RELAY_STT_MODEL:-mlx-community/whisper-large-v3-turbo}"
STT_COMMAND="${ROAM_RELAY_STT_COMMAND:-$(command -v mlx_whisper || true)}"
STT_COMMAND="${STT_COMMAND:-/opt/homebrew/bin/mlx_whisper}"

mkdir -p "$LOG_DIR"

launchctl unload "$PLIST" >/dev/null 2>&1 || true

if [ -f "$PID_FILE" ]; then
  old_pid="$(cat "$PID_FILE")"
  if [ -n "$old_pid" ] && kill -0 "$old_pid" >/dev/null 2>&1; then
    kill "$old_pid" >/dev/null 2>&1 || true
    sleep 1
  fi
fi

(
  cd "$ROOT"
  export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
  export ROAM_TMUX_TARGET="$TMUX_TARGET"
  nohup "$NODE_BIN" "$ROOT/scripts/roam-relay-receiver.mjs" \
    --host 0.0.0.0 \
    --port "$PORT" \
    --wav "$LOG_DIR/roam-relay-latest.wav" \
    --transcribe \
    --stt-command "$STT_COMMAND" \
    --stt-model "$STT_MODEL" \
    --inject "$INJECT_MODE" \
    --commands \
    >> "$LOG_DIR/relay.out.log" \
    2>> "$LOG_DIR/relay.err.log" &
  echo "$!" > "$PID_FILE"
)

echo "Started user-context Roam relay receiver on port ${PORT}"
echo "PID: $(cat "$PID_FILE")"
echo "Logs: ${LOG_DIR}/relay.out.log and ${LOG_DIR}/relay.err.log"
echo "Transcripts: ${LOG_DIR}/transcripts.jsonl"
echo "Inject mode: ${INJECT_MODE}"
echo "tmux target: ${TMUX_TARGET}"
echo "STT command: ${STT_COMMAND}"
