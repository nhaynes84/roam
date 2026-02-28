# Roam P2 — XIAO nRF52840 Sense GPIO Allocation

## Pin Assignment Table

| Pin  | Function       | Direction | Notes                          |
|------|----------------|-----------|--------------------------------|
| D0   | Button 1       | Input     | Index (Dictation) — internal pull-up |
| D1   | Button 2       | Input     | Middle (Mode) — internal pull-up     |
| D2   | Button 3       | Input     | Ring (Yes) — internal pull-up        |
| D3   | Button 4       | Input     | Pinky (No) — internal pull-up        |
| D4   | I2C SDA        | Bidir     | OLED display                   |
| D5   | I2C SCL        | Bidir     | OLED display                   |
| D6   | Motor PWM      | Output    | NPN base via 1kΩ               |
| D7   | Status LED     | Output    | Via 100Ω resistor              |
| 3V3  | Power output   | Power     | From onboard regulator         |
| GND  | Ground         | Power     | Common ground                  |
| VBUS | USB 5V         | Power     | Only available when USB connected |
| BAT  | Battery        | Power     | JST SH 1.0mm connector (built-in charging) |

## Board Layout

```
              ┌───USB-C───┐
        D0  ──┤           ├── 5V
        D1  ──┤           ├── GND
        D2  ──┤           ├── 3V3
        D3  ──┤           ├── D10
        D4  ──┤  (SDA)    ├── D9
        D5  ──┤  (SCL)    ├── D8
        D6  ──┤           ├── D7
              ├───────────┤
              │  BAT(JST) │
              └───────────┘
```

## OLED Display — SSD1309 2.42" 128×64

**Driver**: SSD1309 (register-compatible with SSD1306)
**Voltage**: 3.3V — works on battery, no boost needed
**I2C address**: 0x3C (DC pin → GND)
**Module size**: 61.5 × 39.5mm
**Visible area**: 55.0 × 27.5mm

### I2C Mode Configuration (ships as SPI by default)

On the back of the board, locate resistor pads R3, R4, R5:

1. **Move the 0Ω resistor from R4 → R3**
2. **Add a 0Ω resistor (or solder bridge) on R5**

That switches the board from 4-wire SPI to I2C mode.

### OLED Wiring (I2C mode, 7-pin header)

| OLED Pin | Connect to    | Notes                              |
|----------|---------------|------------------------------------|
| VCC      | 3V3           | 3.3V is fine for SSD1309           |
| GND      | GND           |                                    |
| SCL      | D5 (SCL)      |                                    |
| SDA      | D4 (SDA)      |                                    |
| RES      | 3V3           | Tie high (or use a GPIO for reset) |
| DC       | GND           | Sets I2C address to 0x3C           |
| CS       | GND           | Not used in I2C, tie low           |

### U8g2 Constructor

```cpp
#define DISPLAY_TYPE U8G2_SSD1306_128X64_NONAME_F_HW_I2C
```

SSD1309 is register-compatible with SSD1306 — this constructor works.
If quirks arise, use `U8G2_SSD1309_128X64_NONAME0_F_HW_I2C` instead.

## Battery

- Built-in JST SH 1.0mm connector — plug in LiPo, no SHIM needed
- Charging via USB-C (onboard charging circuit)
- Battery voltage readable via internal ADC (`PIN_VBAT` defined by board core)
- No GP25 / CYW43 complications like P1

## Available GPIOs

| Pin  | Status     | Notes                              |
|------|------------|------------------------------------|
| D8   | Available  | General purpose                    |
| D9   | Available  | General purpose                    |
| D10  | Available  | General purpose                    |

## Built-in Sensors (XIAO nRF52840 Sense)

- **IMU**: LSM6DS3 (6-axis accel + gyro) — available if needed
- **Mic**: PDM microphone — available if needed

## Hardware Gotchas

- **No 5V on battery**: Only 3.3V available when running on battery. OLED must be 3.3V-compatible (SSD1309 is fine, SH1106 from P1 is not).
- **Double-tap reset**: No BOOTSEL button. Double-tap the tiny reset button to enter UF2 bootloader.
- **Bootloader**: Adafruit nRF52 bootloader — shows as USB mass storage device when in bootloader mode.
