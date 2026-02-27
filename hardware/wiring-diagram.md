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
 ║          3V3 ─────────────────┬───────────┬──── VCC                 ║
 ║                               │           │                         ║
 ║                             4.7kΩ       4.7kΩ                       ║
 ║                               │           │                         ║
 ║          GP4 (SDA) ──────────┴────────── SDA                        ║
 ║          GP5 (SCL) ──────────────────┴── SCL                        ║
 ║          GND ─────────────────────────── GND                        ║
 ║                                                                     ║
 ║   Note: Some OLED modules have onboard pull-ups.                    ║
 ║   Check before adding external 4.7kΩ resistors.                     ║
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
 ║        └─── wrist side ──┘                    long:  Tab + Enter)  ║
 ║                                  Pinky  = GP13 (short: Escape,      ║
 ║                                                 long:  Ctrl+C)     ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  VIBRATION MOTOR — NPN transistor driver                            ║
 ║                                                                     ║
 ║          3V3 ──────────┬──────────── Motor (+)                      ║
 ║                        │                │                           ║
 ║                   ┌──┤◄├──┐        Motor (-)                        ║
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
 ║   Flyback diode: cathode (band) toward 3V3                         ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  STATUS LED                                                         ║
 ║                                                                     ║
 ║          GP16 ──── 100Ω ──── LED (+) ──── LED (-) ──── GND         ║
 ║                                 ▲                                   ║
 ║                            3mm green                                ║
 ║                            or white                                 ║
 ║                                                                     ║
 ║   ~10mA at 3.3V. PWM driven for blink/pulse patterns.              ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  BATTERY MONITORING (firmware, no extra wiring)                     ║
 ║                                                                     ║
 ║   GP29 (ADC3) reads VSYS/3 via onboard voltage divider.            ║
 ║   GP25 is driven HIGH during reads to avoid CYW43 SPI contention.  ║
 ║   No external components needed — this is built into the Pico.      ║
 ╚══════════════════════════════════════════════════════════════════════╝

## Bill of Materials

| Qty | Component                    | Value/Spec            | Notes                           |
|-----|------------------------------|-----------------------|---------------------------------|
| 1   | Pimoroni Pico Plus 2 W       | RP2350 + CYW43439     | Main MCU + BLE                  |
| 1   | SH1106 OLED module           | 128×64, 1.3", I2C     | 4-pin (VCC/GND/SCL/SDA)        |
| 4   | Tactile switch               | 6×6mm                 | Through-hole or panel mount     |
| 1   | Vibration motor              | 3V coin/cylinder      | ~80mA max                       |
| 1   | 2N2222 NPN transistor        | or equivalent          | Motor driver                    |
| 1   | 1N4148 diode                 | Signal diode           | Flyback protection              |
| 1   | LED                          | 3mm green or white     | Status indicator                |
| 1   | TP4056 module                | USB-C, DW01 protection| LiPo charger                    |
| 1   | LiPo battery                 | 502535, 3.7V 400mAh   |                                 |
| 1   | Slide switch                 | MSK-12C02 style        | Power on/off                    |
| 1   | Resistor                     | 100Ω                  | LED current limit               |
| 1   | Resistor                     | 1kΩ                   | NPN base                        |
| 2   | Resistor (optional)          | 4.7kΩ                 | I2C pull-ups (if not on module) |

## Wire Color Convention (suggested)

| Color  | Signal     |
|--------|------------|
| Red    | 3V3 / VSYS |
| Black  | GND        |
| Blue   | SDA        |
| Yellow | SCL        |
| White  | Button wires |
| Green  | Motor / LED |
