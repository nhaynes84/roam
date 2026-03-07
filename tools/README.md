# Roam Tools — BLE Text Push

Send text messages to the Roam wrist display over BLE. Any process (Claude Code, openclaw, tmux hooks, scripts) can push notifications to the OLED.

## Tools

### `roam-send` — Low-level BLE sender
Compiled Swift binary. Sends a single message (max 127 chars) to the Roam BLE text characteristic (UUID `0xFF01`).

```bash
./roam-send "short message"
./roam-send --clear
```

- Connects to the first discovered Roam device
- Truncates at 127 characters (BLE buffer limit)
- Device buzzes twice on receipt (haptic confirmation)

### `roam-msg` — Chunked message wrapper
Bash script that splits long messages at word boundaries and sends each chunk as a separate message with a 2-second delay between sends.

```bash
./roam-msg "This is a very long message that exceeds the 127 character BLE buffer limit and will be automatically split into multiple messages that you can scroll through on the device"
```

- Each chunk becomes a separate message in the ring buffer (10 message capacity)
- Scroll between chunks using the scroll buttons on the device
- No prefix tags — chunks are clean text

**Use `roam-msg` for all programmatic sends.** It handles the buffer limit transparently.

## Claude Code Integration

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/Projects/roam/tools/roam-msg \"Sent\" 2>/dev/null &"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/Projects/roam/tools/roam-msg \"Ready\" 2>/dev/null &"
          }
        ]
      }
    ]
  }
}
```

- **UserPromptSubmit**: Sends "Sent" when you submit a message (confirmation you hit Enter)
- **Stop**: Sends "Ready" when Claude finishes responding

### Sending from within a Claude session

Claude Code (or any agent) can call `roam-msg` directly via Bash:

```bash
~/Projects/roam/tools/roam-msg "Build complete. 0 errors."
```

Use this for status updates, task completion notices, or any info the user needs on their wrist.

## openclaw Integration

openclaw agents can shell out to `roam-msg`:

```javascript
const { execSync } = require('child_process');
execSync(`~/Projects/roam/tools/roam-msg "Task finished: ${summary}"`);
```

Or add to the agent's tool config as a notification action.

## tmux Integration

Already configured in `~/.tmux.conf`:

```bash
set-hook -g after-select-pane 'run-shell -b "pkill -f roam-send 2>/dev/null; ~/Projects/roam/tools/roam-send \"Pane #{pane_index}: #{pane_title}\" 2>/dev/null &"'
```

Sends pane name to Roam on every pane switch.

## Display Behavior

- Messages stored in a 10-slot ring buffer (oldest evicted when full)
- New messages auto-display and wake the screen
- Scroll up (D8) = advance to next message/page (higher numbers)
- Scroll down (D9) = go back (lower numbers)
- Bottom indicator: `p1/3` for pages within a long message, `m2/5` for message position
- Numbering is chronological: m1 = oldest, mN = newest
- Double haptic pulse on every incoming message
