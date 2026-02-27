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

## Board Silkscreen Labels (Pimoroni Pico Plus 2 W)

USB port at top. Labels printed on PCB next to castellated pads.

```
  Left edge (top to bottom):       Right edge (top to bottom):
   0                                VB
   1                                VS
   -  (GND)                         -  (GND)
   2                                3E
   3                                +  (3V3)
   4  ◄ SDA                         VA
   5  ◄ SCL                         28
   -  (GND)                         -  (GND)
   6                                27
   7                                26
   8                                RU
   9                                22
   -  (GND)                         -  (GND)
  10  ◄ Btn Index (Dictation)       21
  11  ◄ Btn Middle (Mode)           20
  12  ◄ Btn Ring (Yes)              19
  13  ◄ Btn Pinky (No)              18
   -  (GND) ◄ shared button GND     -  (GND)
  14                                17
  15  ◄ Motor PWM                   16 ◄ LED PWM
```

**Button wiring: 5 solder joints on the left edge, bottom cluster.**
Pads 10, 11, 12, 13 each get a wire to one side of a switch.
The `-` (GND) pad between 13 and 14 is shared ground for all four switches.

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
