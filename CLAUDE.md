# Roam — Claude Code Instructions

## Project Overview

Roam is a wrist-mounted tactile controller for hands-free AI interaction. It runs MicroPython on a Raspberry Pi Pico 2 W with a 1.3" OLED display, 4 buttons, vibration motor, and LED.

## Tech Stack

- **Firmware**: MicroPython on Pico 2 W
- **Housing CAD**: OpenSCAD (parametric, `housing/` directory)
- **Flash tool**: `mpremote` (install via pip)
- **Build**: `make flash`, `make reset`, `make repl`, `make deploy`

## Key Commands

```bash
make flash       # Copy firmware/ to Pico via mpremote
make reset       # Soft-reset the Pico
make repl        # Open interactive MicroPython REPL
make deploy      # Flash + reset
make render      # Render OpenSCAD housing to STL
```

## Code Conventions

### Firmware (MicroPython)
- Target: MicroPython on RP2350 (Pico 2 W)
- Use `machine.Pin`, `machine.I2C`, `machine.PWM` — standard MicroPython APIs
- Pin assignments live in `firmware/config.py` — don't hardcode GPIO numbers elsewhere
- Async where needed via `uasyncio`
- Keep memory footprint minimal — Pico 2 has 520KB SRAM but MicroPython overhead is significant

### Housing (OpenSCAD)
- All shared dimensions in `housing/common.scad`
- Case and lid are separate files that `include <common.scad>`
- Use `$fn = 60` for production renders, lower for previews
- Parametric: change dimensions in common.scad, everything updates
- All units in millimeters

## Hardware Reference

- **Pinout**: `hardware/pinout.md`
- **Wiring**: `hardware/schematic.md`
- GPIO assignments: I2C0 on GP4/5, buttons on GP10-13, motor PWM on GP15, LED on GP16

## File Structure

```
firmware/    — MicroPython source (copied to Pico root)
housing/     — OpenSCAD designs + render script
hardware/    — Wiring docs and pinout tables
tests/       — Test scripts
```

## Git Workflow

- Commit directly to main for single-contributor work
- Use worktrees for parallel Claude Code sessions
