# Roam P1 — Wiring Diagram

Complete point-to-point wiring for the Pimoroni Pico Plus 2 W build.

## Board Pinout Reference

```
                        ┌───USB-C───┐
                  GP0  ─┤ 1      40 ├─ VBUS
                  GP1  ─┤ 2      39 ├─ VSYS ◄── TP4056 OUT+ (via switch)
                  GND  ─┤ 3      38 ├─ GND
                  GP2  ─┤ 4      37 ├─ 3V3_EN
                  GP3  ─┤ 5      36 ├─ 3V3 OUT
         SDA ◄── GP4  ─┤ 6      35 ├─ ADC_VREF
         SCL ◄── GP5  ─┤ 7      34 ├─ GP28 (ADC2)
                  GND  ─┤ 8      33 ├─ GND / AGND
                  GP6  ─┤ 9      32 ├─ GP27 (ADC1)
                  GP7  ─┤10      31 ├─ GP26 (ADC0)
                  GP8  ─┤11      30 ├─ RUN
                  GP9  ─┤12      29 ├─ GP22
                  GND  ─┤13      28 ├─ GND
  Btn Dictate ◄── GP10 ─┤14      27 ├─ GP21
     Btn Mode ◄── GP11 ─┤15      26 ├─ GP20
      Btn Yes ◄── GP12 ─┤16      25 ├─ GP19
       Btn No ◄── GP13 ─┤17      24 ├─ GP18
                  GND  ─┤18      23 ├─ GND
                  GP14 ─┤19      22 ├─ GP17
       Motor ◄── GP15 ─┤20      21 ├─ GP16 ──► LED
                        └──────────┘
```

## Circuit Diagram

```
 ╔══════════════════════════════════════════════════════════════════════╗
 ║  POWER                                                              ║
 ║                                                                     ║
 ║   LiPo 3.7V 400mAh          TP4056 Module         Slide Switch     ║
 ║   ┌──────────┐           ┌──────────────┐         ┌─────┐          ║
 ║   │  502535   │    B+ ───┤ BAT+    OUT+ ├─────────┤ ○ ○ ├──► VSYS  ║
 ║   │  + ─── ──│──────────┤ BAT-    OUT- ├──┐      └─────┘          ║
 ║   │  - ─── ──│──────────┤ GND          │  └────────────────► GND   ║
 ║   └──────────┘           └──────┬───────┘                           ║
 ║                                 │ USB-C                             ║
 ║                              (charge in)                            ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  OLED DISPLAY — SH1106 128×64 1.3"                                 ║
 ║                                                                     ║
 ║       VBUS (5V) ──────────────────────── VCC                        ║
 ║          GP4 (SDA) ─────────────────── SDA (or SDK/SCK label)       ║
 ║          GP5 (SCL) ─────────────────── SCL (or SCK label)           ║
 ║          GND ─────────────────────────── GND                        ║
 ║                                                                     ║
 ║   CRITICAL: VCC must be 5V (+ pad / VBUS), NOT 3.3V (3E pad).      ║
 ║   At 3.3V the I2C bus responds (device found at 0x3C) but the      ║
 ║   OLED panel doesn't light up — charge pump needs higher voltage.   ║
 ║   I2C data lines remain 3.3V logic via the Pico's GPIO.            ║
 ║                                                                     ║
 ║   Screen pin labels vary by brand: may say VOC/VCC, SCK/SCL.       ║
 ║   Pin order: GND, VCC, SCL, SDA (verify on your module).           ║
 ║   No external pull-ups needed — modules have onboard pull-ups.      ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  BUTTONS — Tactile switches, active low                             ║
 ║                                                                     ║
 ║   Internal pull-ups enabled in firmware (no external resistors)     ║
 ║                                                                     ║
 ║          GP10 ──────┤ ○  ○ ├────── GND      Index  (Dictation)     ║
 ║          GP11 ──────┤ ○  ○ ├────── GND      Middle (Mode)          ║
 ║          GP12 ──────┤ ○  ○ ├────── GND      Ring   (Yes/Approve)   ║
 ║          GP13 ──────┤ ○  ○ ├────── GND      Pinky  (No/Escape)    ║
 ║                                                                     ║
 ║   Physical layout (left hand on right forearm, buttons face up):    ║
 ║                                                                     ║
 ║        ┌─── elbow side ───┐                                         ║
 ║        │                  │                                         ║
 ║        │  [Index] [Middle]│     Index  = GP10 (short: dictation,    ║
 ║        │                  │                    long:  tmux pane)    ║
 ║        │  [Ring]  [Pinky] │     Middle = GP11 (short: cycle mode,   ║
 ║        │                  │                    long:  BLE switch)   ║
 ║        │                  │     Ring   = GP12 (short: y + Enter,    ║
 ║        └─── wrist side ──┘                    long:  Tab + Enter,  ║
 ║                                               double: Enter only)  ║
 ║                                  Pinky  = GP13 (short: Escape,      ║
 ║                                                 long:  Ctrl+C)     ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  VIBRATION MOTOR — NPN transistor driver                            ║
 ║                                                                     ║
 ║         VBUS (5V) ─────┬──────────── Motor (+, red)                 ║
 ║                        │                │                           ║
 ║                   ┌──┤◄├──┐        Motor (-, blue)                  ║
 ║                   │ 1N4148 │            │                           ║
 ║                   │(flyback)│           │                           ║
 ║                   └────────┘     ┌──────┘                           ║
 ║                                  │  C                               ║
 ║                                ┌─┴─┐                                ║
 ║          GP15 ──── 1kΩ ───── B│NPN │ 2N2222                        ║
 ║                                └─┬─┘                                ║
 ║                                  │  E                               ║
 ║                                 GND                                 ║
 ║                                                                     ║
 ║   Motor positive → + pad (VBUS/5V), NOT 3E (3.3V).                 ║
 ║   Coin motors rated 3V won't spin at 3.3V through transistor.      ║
 ║   Flyback diode: cathode (band) toward VBUS side.                  ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  STATUS LED                                                         ║
 ║                                                                     ║
 ║          GP16 ──── 220Ω ──── LED (+) ──── LED (-) ──── GND         ║
 ║                                 ▲                                   ║
 ║                            5mm red                                  ║
 ║                          (diffused)                                 ║
 ║                                                                     ║
 ║   ~7mA at 3.3V. Solid when BLE connected, blink when advertising.  ║
 ║   NOTE: Do NOT use "fast flashing RGB" LEDs — they have a          ║
 ║   built-in IC that cycles colors automatically. Use plain LEDs.     ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  BATTERY MONITORING (firmware, no extra wiring)                     ║
 ║                                                                     ║
 ║   GP29 (ADC3) reads VSYS/3 via onboard voltage divider.            ║
 ║   No external components needed — this is built into the Pico.      ║
 ║                                                                     ║
 ║   WARNING: Do NOT toggle GP25 — it's shared with CYW43 wireless    ║
 ║   SPI. Driving it as GPIO kills BLE. Battery reads work without     ║
 ║   GP25 coordination; slight ADC noise is acceptable.                ║
 ╚══════════════════════════════════════════════════════════════════════╝

## Bill of Materials

| Qty | Component                    | Value/Spec            | Notes                           |
|-----|------------------------------|-----------------------|---------------------------------|
| 1   | Pimoroni Pico Plus 2 W       | RP2350 + CYW43439     | Main MCU + BLE                  |
| 1   | SH1106 OLED module           | 128×64, 1.3", I2C     | 4-pin (VCC/GND/SCL/SDA)        |
| 4   | Tactile switch               | 6×6mm                 | Through-hole or panel mount     |
| 1   | Vibration motor              | 3V coin type          | Powered from VBUS (5V)          |
| 1   | 2N2222 NPN transistor        | or equivalent          | Motor driver                    |
| 1   | 1N4148 diode                 | Signal diode           | Flyback protection              |
| 1   | LED                          | 5mm red diffused       | Plain single-color, NOT RGB     |
| 1   | TP4056 module                | USB-C, DW01 protection| LiPo charger                    |
| 1   | LiPo battery                 | 502535, 3.7V 400mAh   |                                 |
| 1   | Slide switch                 | MSK-12C02 style        | Power on/off                    |
| 1   | Resistor                     | 220Ω (red-red-brown)  | LED current limit               |
| 1   | Resistor                     | 1kΩ                   | NPN base                        |
| 2   | Resistor (optional)          | 4.7kΩ                 | I2C pull-ups (if not on module) |

## Wire Color Convention (suggested)

| Color  | Signal     |
|--------|------------|
| Red    | 5V / VSYS  |
| Black  | GND        |
| Blue   | SDA        |
| Yellow | SCL        |
| White  | Button wires |
| Green  | Motor / LED |
