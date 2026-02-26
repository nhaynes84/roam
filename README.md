# Roam

Wrist-mounted tactile controller for hands-free AI interaction. Four buttons, OLED display, haptic feedback — strapped to your forearm, operated by the opposite hand.

**Hardware**: Raspberry Pi Pico 2 W, 1.3" OLED (SH1106), 4x tactile buttons, vibration motor, LED, 502535 LiPo battery.

**Firmware**: MicroPython running on the Pico 2 W.

**Housing**: 3D-printed case designed in OpenSCAD — ergonomic half-moon dome shape.

## Project Structure

```
roam/
├── firmware/          # MicroPython source (flashed to Pico)
│   ├── main.py        # Entry point
│   ├── buttons.py     # Button input + debounce
│   ├── display.py     # OLED rendering
│   ├── haptics.py     # Vibration motor control
│   └── config.py      # Pin assignments, settings
├── housing/           # OpenSCAD parametric case design
│   ├── common.scad    # Shared dimensions
│   ├── roam_case.scad # Top shell (dome)
│   ├── roam_lid.scad  # Bottom lid
│   └── render.sh      # STL render script
├── hardware/          # Wiring docs
│   ├── schematic.md   # Full wiring diagram
│   └── pinout.md      # GPIO allocation table
├── tests/             # Test scripts
├── Makefile           # Flash/reset/repl shortcuts
└── CLAUDE.md          # Claude Code project instructions
```

## Prerequisites

- **MicroPython**: Install the Pico 2 W MicroPython UF2 firmware
  - Download from [micropython.org](https://micropython.org/download/RPI_PICO2_W/)
  - Hold BOOTSEL, plug USB, drag UF2 to the mounted drive
- **mpremote**: `pip install mpremote`
- **OpenSCAD** (optional, for housing edits): `brew install openscad`

## Flash Firmware

```bash
# Copy all firmware files to Pico
make flash

# Or manually:
mpremote cp -r firmware/ :

# Reset the board
make reset
```

## Development

```bash
# Open REPL
make repl

# Flash + reset in one step
make deploy

# Render housing STLs
make render
```

## Wiring

See [hardware/schematic.md](hardware/schematic.md) for full wiring diagram and [hardware/pinout.md](hardware/pinout.md) for GPIO allocation.

Key connections:
- **I2C0** (GP4/GP5) → OLED display
- **GP10-13** → 4 tactile buttons (active low, internal pull-ups)
- **GP15** → Vibration motor via NPN transistor
- **GP16** → Status LED via 100Ω resistor
- **VSYS** ← TP4056 battery charger output

## 3D Printing

The housing is designed for FDM printing:
- **Case (dome)**: Print upside-down, 0.2mm layers, 3-wall, 20% infill
- **Lid**: Print flat-side down, 0.2mm layers
- **TPU pads**: Print the pad zones from roam_lid in TPU for forearm comfort

Render STLs:
```bash
cd housing
chmod +x render.sh
./render.sh          # full quality
./render.sh --fast   # quick preview
```
