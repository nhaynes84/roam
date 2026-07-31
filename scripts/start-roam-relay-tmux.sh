#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_BIN="$(command -v node)"
LOG_DIR="$HOME/Library/Logs/Roam"
PORT="${1:-8765}"
SESSION="${ROAM_RELAY_TMUX_SESSION:-roam-relay}"
INJECT_MODE="${ROAM_RELAY_INJECT_MODE:-tmux-submit}"
TMUX_TARGET="${ROAM_TMUX_TARGET:-}"
STT_MODEL="${ROAM_RELAY_STT_MODEL:-mlx-community/whisper-large-v3-turbo}"
STT_COMMAND="${ROAM_RELAY_STT_COMMAND:-$(command -v mlx_whisper || true)}"
STT_COMMAND="${STT_COMMAND:-/opt/homebrew/bin/mlx_whisper}"
PLIST="$HOME/Library/LaunchAgents/com.roam.relay-receiver.plist"

if [ -z "$TMUX_TARGET" ] && [ -n "${TMUX:-}" ]; then
  TMUX_TARGET="$(tmux display-message -p '#{session_name}:#{window_index}' 2>/dev/null || true)"
fi
TMUX_TARGET="${TMUX_TARGET:-0:0}"

mkdir -p "$LOG_DIR"
launchctl unload "$PLIST" >/dev/null 2>&1 || true

if tmux has-session -t "$SESSION" >/dev/null 2>&1; then
  tmux kill-session -t "$SESSION"
fi

q() {
  printf "%q" "$1"
}

PATH_VALUE="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
CMD="export PATH=$(q "$PATH_VALUE"); "
CMD+="export ROAM_TMUX_TARGET=$(q "$TMUX_TARGET"); "
CMD+="exec $(q "$NODE_BIN") $(q "$ROOT/scripts/roam-relay-receiver.mjs") "
CMD+="--host 0.0.0.0 "
CMD+="--port $(q "$PORT") "
CMD+="--wav $(q "$LOG_DIR/roam-relay-latest.wav") "
CMD+="--transcribe "
CMD+="--stt-command $(q "$STT_COMMAND") "
CMD+="--stt-model $(q "$STT_MODEL") "
CMD+="--inject $(q "$INJECT_MODE") "
CMD+="--commands "
CMD+=">> $(q "$LOG_DIR/relay.out.log") "
CMD+="2>> $(q "$LOG_DIR/relay.err.log")"

tmux new-session -d -s "$SESSION" -c "$ROOT" "$CMD"

echo "Started Roam relay receiver in tmux session ${SESSION} on port ${PORT}"
echo "Logs: ${LOG_DIR}/relay.out.log and ${LOG_DIR}/relay.err.log"
echo "Transcripts: ${LOG_DIR}/transcripts.jsonl"
echo "Inject mode: ${INJECT_MODE}"
echo "tmux target: ${TMUX_TARGET}"
echo "STT command: ${STT_COMMAND}"
