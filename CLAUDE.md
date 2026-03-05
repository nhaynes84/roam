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
make p2-flash         # P2 flash (double-tap reset first)
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
- Double-tap reset for bootloader. Port flaps between usbmodem101/1101.

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
tools/       Utilities (roam-send Swift BLE tool)
tests/       Test sketches
```

## Git Workflow
- Commit directly to main. Use worktrees for parallel Claude sessions.
