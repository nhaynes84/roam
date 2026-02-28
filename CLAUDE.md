# Roam — Claude Code Instructions

## Project Overview

Roam is a wrist-mounted tactile controller for hands-free AI interaction. Pimoroni Pico Plus 2 W (RP2350 + CYW43439) with BLE HID, 4 buttons, vibration motor, LED, and planned OLED display.

## Tech Stack

- **Active firmware**: Arduino-pico (C++) in `arduino/` — BLE HID via `KeyboardBLE`
- **Legacy firmware**: MicroPython in `firmware/` — BLE pairing broken, kept as reference
- **Housing CAD**: OpenSCAD (parametric, `housing/` directory)
- **Toolchain**: `arduino-cli` with rp2040:rp2040 board core
- **FQBN**: `rp2040:rp2040:pimoroni_pico_plus_2w:ipbtstack=ipv4btcble`

## Key Commands

```bash
make arduino-build   # Compile Arduino firmware
make arduino-flash   # Flash via USB
make arduino-monitor # Serial monitor (115200 baud)
make render          # Render OpenSCAD housing to STL
```

## Code Conventions

### Firmware (Arduino-pico C++)
- Currently single-core minimal build (dual-core display/battery disabled until OLED wired)
- Pin assignments in `arduino/config.h` — don't hardcode GPIO numbers elsewhere
- Button events: short press, long press, double-tap
- All timing via `millis()` — no blocking except brief keystroke delays
- Motor wired to + pad (VBUS/5V), not 3E (3.3V)
- **GP25 is off-limits** — shared with CYW43 wireless SPI, toggling it kills BLE
- After every firmware flash: must "Forget This Device" on macOS and re-pair

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
arduino/     — Active firmware (Arduino-pico C++)
firmware/    — Legacy MicroPython source (reference only)
housing/     — OpenSCAD designs + STL renders
hardware/    — Wiring docs, pinout tables, gotchas
tests/       — Test scripts
```

## Git Workflow

- Commit directly to main for single-contributor work
- Use worktrees for parallel Claude Code sessions
