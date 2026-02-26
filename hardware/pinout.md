# Roam — Pico 2 W GPIO Allocation

## Pin Assignment Table

| GPIO | Pin # | Function       | Direction | Notes                          |
|------|-------|----------------|-----------|--------------------------------|
| GP4  | 6     | I2C0 SDA       | Bidir     | OLED display, 4.7kΩ pull-up   |
| GP5  | 7     | I2C0 SCL       | Bidir     | OLED display, 4.7kΩ pull-up   |
| GP10 | 14    | Button 1       | Input     | Dictation — internal pull-up   |
| GP11 | 15    | Button 2       | Input     | Mode — internal pull-up        |
| GP12 | 16    | Button 3       | Input     | Yes — internal pull-up         |
| GP13 | 17    | Button 4       | Input     | No — internal pull-up          |
| GP15 | 20    | Vibration PWM  | Output    | NPN base via 1kΩ resistor      |
| GP16 | 21    | Status LED     | Output    | Via 100Ω resistor              |
| VSYS | 39    | Power input    | Power     | From TP4056 via slide switch   |
| GND  | 38    | Ground         | Power     | Common ground                  |
| 3V3  | 36    | 3.3V output    | Power     | From onboard regulator         |

## Available GPIOs (Reserved / Unused)

| GPIO   | Status     | Notes                              |
|--------|------------|------------------------------------|
| GP0    | Available  | UART0 TX — future expansion        |
| GP1    | Available  | UART0 RX — future expansion        |
| GP2    | Available  | SPI0 SCK — future expansion        |
| GP3    | Available  | SPI0 TX — future expansion         |
| GP6-9  | Available  | General purpose                    |
| GP14   | Available  | Adjacent to motor pin              |
| GP17-22| Available  | General purpose                    |
| GP23   | Reserved   | Wireless SPI CS (internal)         |
| GP24   | Reserved   | Wireless SPI IRQ (internal)        |
| GP25   | Reserved   | Wireless SPI CS (internal)         |
| GP26-28| Available  | ADC capable — battery monitoring?  |
| GP29   | Reserved   | ADC for VSYS/3 voltage divider     |

## Bus Configuration

| Bus   | Pins       | Speed   | Devices          |
|-------|------------|---------|------------------|
| I2C0  | GP4, GP5   | 400kHz  | SH1106 1.3" OLED |

## ADC Notes

- **GP26 (ADC0)**: Could be used for battery voltage monitoring via voltage divider
- **GP29 (ADC3)**: Connected internally to VSYS/3 — reads system voltage
