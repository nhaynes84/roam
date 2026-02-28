# Roam — Claude Code Instructions

## Project Overview

Roam is a wrist-mounted tactile controller for hands-free AI interaction. Two prototypes:

- **P1**: Pimoroni Pico Plus 2 W (RP2350 + CYW43439) — btstack BLE, single-host
- **P2**: Seeed XIAO nRF52840 Sense — Bluefruit BLE, multi-host, smaller, built-in battery charging

## Tech Stack

- **P1 firmware**: Arduino-pico (C++) in `arduino/` — BLE HID via `KeyboardBLE` (btstack)
- **P2 firmware**: Adafruit nRF52 (C++) in `p2/` — BLE HID via `BLEHidAdafruit` (Bluefruit)
- **Shared code**: `common/` — buttons, haptic, LED, display (symlinked into each sketch)
- **Legacy firmware**: MicroPython in `firmware/` — BLE pairing broken, kept as reference
- **Housing CAD**: OpenSCAD (parametric, `housing/` directory)
- **Toolchain**: `arduino-cli`
- **P1 FQBN**: `rp2040:rp2040:pimoroni_pico_plus_2w:ipbtstack=ipv4btcble`
- **P2 FQBN**: `Seeeduino:nrf52:xiaonRF52840Sense`

## Key Commands

```bash
# P1 (Pico Plus 2 W)
make arduino-build   # Compile P1 firmware
make arduino-flash   # Flash P1 via USB
make arduino-monitor # P1 serial monitor (115200 baud)

# P2 (XIAO nRF52840)
make p2-setup        # Install Seeed board core + libraries
make p2-build        # Compile P2 firmware
make p2-flash        # Flash P2 via USB (double-tap reset)
make p2-monitor      # P2 serial monitor

make render          # Render OpenSCAD housing to STL
```

## Code Conventions

### Shared Code (`common/`)
- Symlinked into each sketch directory — Arduino-cli follows symlinks
- Each file `#include "config.h"` which resolves to the sketch's board-specific config
- `DISPLAY_TYPE` macro in config.h selects the U8g2 constructor (SH1106 for P1, SSD1306 for P2)
- Only uses Arduino-standard APIs: `digitalRead`, `analogWrite`, `millis()`, `Wire`, `U8g2`

### P1 Firmware (Arduino-pico C++)
- Single-core build — BLE + buttons + actions + display all on core 0
- Pin assignments in `arduino/config.h` — don't hardcode GPIO numbers elsewhere
- Button events: short press, long press, double-tap
- All timing via `millis()` — no blocking except brief keystroke delays
- Motor and OLED VCC wired to + pad (VBUS/5V), not 3E (3.3V)
- Display uses U8g2 HW_I2C (Wire library) — works alongside btstack BLE at 5V
- **GP25 is off-limits** — shared with CYW43 wireless SPI, toggling it kills BLE
- After every firmware flash: must "Forget This Device" on macOS and re-pair
- After flashing, power-cycle the OLED if I2C scan fails (BOOTSEL can leave bus stuck)

### P2 Firmware (Adafruit nRF52)
- Pin assignments in `p2/config.h`
- BLE via Bluefruit: `BLEHidAdafruit` for HID, `BLEService`/`BLECharacteristic` for custom GATT
- Built-in JST battery connector — no LiPo SHIM needed
- OLED needs 3.3V-compatible display (no 5V on battery)
- Double-tap reset to enter bootloader (no BOOTSEL button)

### Housing (OpenSCAD)
- All shared dimensions in `housing/common.scad`
- Case and lid are separate files that `include <common.scad>`
- Use `$fn = 60` for production renders, lower for previews
- Parametric: change dimensions in common.scad, everything updates
- All units in millimeters

## Hardware Reference

- **Pinout**: `hardware/pinout.md` (includes board silkscreen labels and gotchas)
- **Wiring**: `hardware/wiring-diagram.md`
- GPIO assignments: I2C0 on GP4/5, buttons on GP10-13, motor on GP15, LED on GP16

## File Structure

```
common/      — Shared firmware (buttons, haptic, led, display)
arduino/     — P1 firmware (Pico Plus 2 W, board-specific + symlinks to common/)
p2/          — P2 firmware (XIAO nRF52840, board-specific + symlinks to common/)
firmware/    — Legacy MicroPython source (reference only)
housing/     — OpenSCAD designs + STL renders
hardware/    — Wiring docs, pinout tables, gotchas
tools/       — Utilities (roam-send Swift BLE tool)
tests/       — Test scripts
```

## Git Workflow

- Commit directly to main for single-contributor work
- Use worktrees for parallel Claude Code sessions
