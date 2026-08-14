# Roam — Claude Code Instructions

## Project Overview

Wrist-mounted 4-button BLE HID controller for hands-free AI interaction. Two prototypes:
- **P1**: Pimoroni Pico Plus 2 W — btstack BLE, single-host
- **P2**: Seeed XIAO nRF52840 Sense — Bluefruit BLE, multi-host, built-in battery charging

For hardware gotchas and debug history, load fragment: `memory/roam.md`
For CAD conventions and housing details, load fragment: `memory/roam-cad.md`

## Tech Stack

- **P1 firmware**: Arduino-pico (C++) in `arduino/` — `KeyboardBLE` (btstack)
- **P2 firmware**: Adafruit nRF52 (C++) in `p2/` — `BLEHidAdafruit` (Bluefruit)
- **Shared code**: `common/` — buttons, haptic, LED, display (symlinked into each sketch)
- **Housing**: OpenSCAD (parametric) + build123d (STEP export) in `housing/`
- **Toolchain**: `arduino-cli`
- **P1 FQBN**: `rp2040:rp2040:pimoroni_pico_plus_2w:ipbtstack=ipv4btcble`
- **P2 FQBN**: `Seeeduino:nrf52:xiaonRF52840Sense`

## Key Commands

```bash
make arduino-build    # P1 compile
make arduino-flash    # P1 flash
make p2-build         # P2 compile
make p2-flash         # P2 flash via normal Arduino upload
make p2-flash-sealed  # P2 flash when reset button is inaccessible
make render           # OpenSCAD → STL
make step             # build123d → STEP (for Shapr3D)
```

## Code Conventions

### Shared Code (`common/`)
- Symlinked into each sketch's `src/` — arduino-cli follows symlinks
- `#include "config.h"` resolves to board-specific config in sketch root
- `DISPLAY_TYPE` macro selects U8g2 constructor per board
- Arduino-standard APIs only: `digitalRead`, `analogWrite`, `millis()`, `Wire`, `U8g2`

### P1 Critical Rules
- Pin assignments in `arduino/config.h` — don't hardcode GPIO numbers
- GP25 off-limits (CYW43 SPI). Must forget+re-pair on macOS after flash.
- Motor/OLED need VBUS (5V). Power-cycle OLED if I2C stuck after flash.

### P2 Critical Rules
- Pin assignments in `p2/config.h`
- **TWIM1 only** — softdevice claims TWIM0, Wire library hangs. See `p2/display.cpp`.
- Current wearable is sealed; Nick can power-cycle it but cannot double-tap reset. Do not ask him to be the reset-button operator.
- For sealed-case flashing, use `make p2-flash-sealed`. The working 2026-07-30 path is `adafruit-nrfutil --touch 1200`, wait for Seeed bootloader PID `0x0045`, then upload the DFU zip to that bootloader port without another touch. Normal app PID is `0x8045`.

### Housing (OpenSCAD)
- Orientation: X+=elbow, X-=wrist, Y+=outer, Y-=inner, Z+=up, Z=0=rim
- Named walls: `wall_wrist`, `wall_elbow`, `wall_outer`, `wall_inner`
- EPS (0.1mm) for difference() overlap. Component library in `housing/lib/`.
- `make step` exports STEP for Shapr3D via build123d (`housing/.venv/`)

## File Structure

```
common/      Shared firmware (buttons, haptic, led, display)
arduino/     P1 firmware (board-specific + symlinks to common/)
p2/          P2 firmware (board-specific, display.cpp is standalone)
housing/     OpenSCAD + build123d + STL/STEP renders
housing/lib/ Component library (reusable modules + spring button)
hardware/    Wiring docs, pinout tables
tools/       Utilities (roam-msg — network push to ROAM Touch over Tailscale)
tests/       Test sketches
```

## ROAM — Push Messages

The user wears ROAM so they don't have to sit at the computer. **You must push key messages so the user can follow along remotely.**

```bash
~/Projects/roam/tools/roam-msg "your message here"
```

⚠️ **BLE is retired (2026-08-11), and `roam-msg` no longer touches the device (2026-08-12).** It posts to the **hub** (`POST /notify`), which decides whether the message is worth interrupting him for; the **bridge** is the only thing that speaks to the phone. Say what happened and let the hub judge — it applies "reply where the last message came from", so a status line about a pane he is typing in will not buzz him. That is correct, not a failure.

★ **Everything goes through the hub.** Do not call `adb` to notify, and do not add a second path — `tools/roam-push` is the bridge's transport and yours to leave alone. If `roam-msg` reports **NOT DELIVERED**, the hub process is down (same box, so the bridge is too); the message is recorded in the ledger and pushed when the hub returns. `roam-send` (Swift/CoreBluetooth) and the 127-byte chunking are gone — see git history.

Override the target with `ROAM_DEV=<host:port>`; default is the Pixel's tailnet address. `--pane N` tags per tmux pane so panes don't overwrite each other.

**When to send:**
- When you ask a question or need user input — send the question
- When you finish a task — send a short summary of what was done
- When you hit an error or blocker — send what went wrong
- When starting a long multi-step task — send what you're about to do

**Keep messages concise** — 1-2 short sentences. The old 128x64 / ~21-char limit no longer applies (the phone renders a full notification with `bigtext`), but a glanceable message is still the point. Don't send routine tool calls or intermediate steps.

**This is critical** — without these messages, the user has no idea what you're doing or asking. The automatic "Sent"/"Ready" hooks only signal that a prompt was submitted and a response finished, not what was said.

## Android Emulator — etiquette (talos)

`roam-touch/nexus/tools/roam-emu` is the ONLY sanctioned way to start the QA emulator.
Never run a raw `emulator -avd`. Two rules, both learned the expensive way:

1. ★ **Always headless (`-no-window`).** Over SSH the only reliable renderer is
   `-gpu swiftshader_indirect`, and with a window it composites in software forever.
   Measured 2026-08-14: **915% CPU with a COMPLETELY IDLE guest** (0% user inside
   Android, everything at 0.0%), holding talos at load ~10 for two days. Headless is
   ~8-10% and boots in under 7s. Nothing is lost — install, `am start`, screencap and
   logcat all work headless.
2. ★ **`./tools/roam-emu stop` when you are done.** Nothing reaps it: no launchd agent,
   no timeout. It runs until someone kills it or the box reboots. That is how one
   survived two days.

Diagnosing "talos feels slow": check `uptime`, then look for a stray emulator. **Host
process hot while the guest is idle means the emulator's rendering, never the app under
test** — from inside Android nothing looks wrong at all, which is why it hides.

⛔ **Never install to the Pixel over network adb** (`100.95.196.87:5555`). It is the
owner's worn device showing real notifications, and a 12-year-old sailfish. The emulator
is the default target; the Pixel is for final confirmation by the owner, not for agents.
`adb disconnect 100.95.196.87:5555` if it appears in `adb devices`.

Environment note: `ANDROID_HOME` is unset in interactive shells and the SDK is at
`/opt/homebrew/share/android-commandlinetools`, not `~/Library/Android/sdk`. `roam-emu`
sets it; a bare `emulator` on PATH will not work.

## Git Workflow
- Commit directly to main. Use worktrees for parallel Claude sessions.
