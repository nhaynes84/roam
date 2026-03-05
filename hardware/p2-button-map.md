# Roam P2 — Button Command Map

## Button Layout

```
            ┌──────────────── elbow side ────────────────┐
            │                                            │
            │   [Index]  [Middle]  [Ring]  [Pinky]       │  ◄── top face
            │     D0       D1       D2      D3           │
            │                                            │
  USB-C ◄───│                              [Scroll Fwd]  │
  Switch ◄──│                               D8           │  ◄── right side
            │                              [Scroll Back] │
            │                               D9           │
            │                                            │
            └──────────────── wrist side ────────────────┘
```

## Command Map

| Button | Pin | Short Press | Long Press | Double Tap |
|--------|-----|-------------|------------|------------|
| Index  | D0  | Dictation (macOS 0x00CF) | Tmux pane (Ctrl+B, o) | Scroll Fwd* |
| Middle | D1  | Cycle Mode (Shift+Tab) | BLE Switch (disconnect + re-advertise) | Scroll Back* |
| Ring   | D2  | Approve (y + Enter) | Always (Tab + Enter) | Enter |
| Pinky  | D3  | Escape | Kill (Ctrl+C) | — |
| Scroll Fwd | D8 | Next message | Next message | — |
| Scroll Back | D9 | Prev message | Prev message | — |

*Index/Middle double-tap scroll is a fallback for P1 testing (no dedicated scroll buttons).
On P2, use the dedicated D8/D9 thumb buttons instead.

## Action Details

### Index — D0
| Gesture | Action | HID Output | Use Case |
|---------|--------|------------|----------|
| Short | Dictation | Consumer key 0x00CF | Start/stop macOS dictation |
| Long | Tmux Pane | Ctrl+B then 'o' | Switch tmux pane |

### Middle — D1
| Gesture | Action | HID Output | Use Case |
|---------|--------|------------|----------|
| Short | Cycle Mode | Shift+Tab | Cycle through UI modes |
| Long | BLE Switch | (internal) | Disconnect current host, re-advertise for next |

### Ring — D2
| Gesture | Action | HID Output | Use Case |
|---------|--------|------------|----------|
| Short | Approve | 'y' then Enter | Accept Claude Code prompt |
| Long | Always | Tab then Enter | Select "Always allow" option |
| Double | Enter | Enter | Confirm without 'y' prefix |

### Pinky — D3
| Gesture | Action | HID Output | Use Case |
|---------|--------|------------|----------|
| Short | Escape | Escape | Cancel / dismiss |
| Long | Kill | Ctrl+C | Kill running process |

### Scroll — D8 / D9
| Button | Action | HID Output | Use Case |
|--------|--------|------------|----------|
| D8 (Fwd) | Scroll Fwd | (local) | View newer BLE text message |
| D9 (Back) | Scroll Back | (local) | View older BLE text message |

Scroll buttons are local-only — they navigate the on-screen message ring buffer,
no BLE HID output. Short haptic buzz (40ms) on scroll.

## Timing

| Parameter | Value | Notes |
|-----------|-------|-------|
| Debounce | 50ms | Ignore presses shorter than this |
| Long press | 600ms | Fires while still held |
| Double tap window | 300ms | Max gap between taps |
| Action fade | 3000ms | Action name on screen duration |
| Screen dim | 10s | Dim after inactivity |
| Screen off | 30s | Power off after inactivity |

## Haptic Feedback

| Event | Motor pulse | Pattern |
|-------|------------|---------|
| Button action (HID) | 80ms | Single buzz |
| Scroll | 40ms | Short buzz |
| BLE text received | 60-80-60ms | Double buzz |
