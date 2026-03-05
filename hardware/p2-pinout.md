# Roam P2 — XIAO nRF52840 Sense GPIO Allocation

## Pin Assignment Table

| Pin  | nRF GPIO | Function       | Direction | Notes                          |
|------|----------|----------------|-----------|--------------------------------|
| D0   | P0.02    | Button 1       | Input     | Index (Dictation) — internal pull-up |
| D1   | P0.03    | Button 2       | Input     | Middle (Mode) — internal pull-up     |
| D2   | P0.28    | Button 3       | Input     | Ring (Yes) — internal pull-up        |
| D3   | P0.29    | Button 4       | Input     | Pinky (No) — internal pull-up        |
| D4   | P0.04    | I2C SDA        | Bidir     | OLED display (TWIM1)           |
| D5   | P0.05    | I2C SCL        | Bidir     | OLED display (TWIM1)           |
| D6   | P1.11    | Motor PWM      | Output    | NPN base via 1kΩ               |
| D7   | P1.12    | Status LED     | Output    | Via 100Ω resistor              |
| D8   | P1.13    | Scroll Fwd     | Input     | Thumb button — internal pull-up|
| D9   | P1.14    | Scroll Back    | Input     | Thumb button — internal pull-up|
| D10  | P1.15    | (Available)    | —         | Reserved for future use        |
| VBAT | —        | Battery ADC    | Input     | Built-in, nRF52 internal ADC   |

## Board Layout

```
              ┌───USB-C───┐
        D0  ──┤  [RST]    ├── 5V (VUSB)
        D1  ──┤           ├── GND
        D2  ──┤           ├── 3V3
        D3  ──┤           ├── D10
        D4  ──┤  (SDA)    ├── D9
        D5  ──┤  (SCL)    ├── D8
        D6  ──┤           ├── D7
              ├───────────┤
              │  BAT(JST) │
              └───────────┘

  [RST] = tiny tactile switch next to USB-C (top side)
  Double-click RST to enter UF2 bootloader
```

## I2C Configuration

| Bus   | Peripheral | Pins     | Speed  | Devices               |
|-------|-----------|----------|--------|-----------------------|
| TWIM1 | NRF_TWIM1 | D4, D5   | 100kHz | OLED display          |

**CRITICAL: Must use TWIM1, not TWIM0.** The Bluefruit softdevice claims TWIM0
and its shared IRQ (`SPIM0_SPIS0_TWIM0_TWIS0_SPI0_TWI0`). Using TWIM0 with
Bluefruit causes I2C data writes to timeout. The firmware uses direct TWIM1
register access (not the Wire library) with proper timeouts.

**Do NOT use the Seeed BSP Wire library** — it has infinite spin loops
(`while(!EVENTS_STOPPED)`) with no timeout. A stuck I2C bus will lock the MCU.

## Display Options

### Option A: SH1106 1.3" 128×64 (Build 2A — current)

The same small screen used on P1. Proven reliable on I2C.

- **VCC from battery through switch** — charge pump works at LiPo voltages (3.7–4.2V)
- **No reset pin** on the 4-pin module (`PIN_DISPLAY_RST = U8X8_PIN_NONE`)
- **Column offset of 2** — SH1106 has 132-column RAM for a 128-column display

**Wiring (4-pin module):**

| OLED Pin | Connect to    | Notes                              |
|----------|---------------|------------------------------------|
| GND      | GND           |                                    |
| VCC      | Switched BAT+ | Through power switch               |
| SCL      | D5            |                                    |
| SDA      | D4            |                                    |

**U8g2 constructor:**
```cpp
#define DISPLAY_TYPE U8G2_SH1106_128X64_NONAME_F_HW_I2C
```

### Option B: SSD1309 2.42" 128×64 (Build 2B — pending)

Larger screen, 3.3V native (works on battery). Ships in SPI mode — needs
resistor mod for I2C. **Not yet proven working on I2C.**

- **3.3V compatible** — works on battery power
- **Requires resistor modification** for I2C mode (see below)
- **Reset pin**: connect RES to a GPIO or tie to 3V3
- **No column offset** (unlike SH1106)

**I2C resistor mod (back of module, under ribbon cable):**
Locate pads R9, R10, R11, R12 (may be hidden under the flex cable):
- Bridge R9 (3-pad selector — bridge middle pad to R9 side, not R8 side)
- Bridge R10, R11, R12
- Remove any existing bridges on R1–R4 (visible side)

The BS[2:1:0] pins set the interface: `010` = I2C mode.

**Wiring (7-pin header, I2C mode):**

| OLED Pin | Connect to    | Notes                              |
|----------|---------------|------------------------------------|
| GND      | GND           |                                    |
| VCC      | 3V3           | 3.3V native                        |
| SCL      | D5            |                                    |
| SDA      | D4            |                                    |
| RES      | D10 (or 3V3)  | Reset — tie high or use GPIO       |
| DC       | GND           | I2C address select: GND = 0x3C     |
| CS       | GND           | Not used in I2C, tie low           |

**U8g2 constructor:**
```cpp
#define DISPLAY_TYPE U8G2_SSD1309_128X64_NONAME0_F_HW_I2C
```

**Status**: Commands (control byte 0x00) work but data writes (control byte 0x40)
timeout — the resistor mod may not have fully switched from SPI to I2C mode.
Needs a pre-configured I2C module or verified mod procedure.

## Battery

- Built-in JST SH 1.0mm connector — plug in LiPo, no external charger needed
- Charging via USB-C (onboard charging circuit)
- Battery voltage readable via `PIN_VBAT` (nRF52 internal ADC)
- No GP25 / CYW43 complications like P1

## Built-in Sensors (XIAO nRF52840 Sense)

- **IMU**: LSM6DS3 (6-axis accel + gyro) — future: wake on wrist supination
- **Mic**: PDM microphone — available if needed

## Hardware Gotchas

- **TWIM0 conflicts with Bluefruit**: The BLE softdevice uses the same peripheral
  group. I2C display MUST use TWIM1 with direct register access. See `display.cpp`.
- **Wire library has no timeouts**: Seeed BSP's `Wire_nRF52.cpp` spins forever
  waiting for TWIM events. A stuck bus = bricked firmware. Use raw TWIM registers.
- **SH1106 works on LiPo voltage**: Charge pump runs fine at 3.7–4.2V through switch.
- **LED_BUILTIN is active LOW**: `LOW` = on, `HIGH` = off. Red LED on P0.26.
- **Reset button**: Tiny switch next to USB-C. Double-click for UF2 bootloader
  (shows as "XIAO-SENSE" USB drive on Mac).
- **No USB serial without firmware**: If firmware doesn't call `Bluefruit.begin()`
  or `Serial.begin()`, USB CDC won't enumerate. Double-click reset to recover.
- **Port flapping**: Serial port alternates between `/dev/cu.usbmodem101` and
  `/dev/cu.usbmodem1101` between flashes. Always check `arduino-cli board list`.
