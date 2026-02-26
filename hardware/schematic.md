# Roam — Wiring Schematic

## Power Circuit

```
                  ┌──────────┐
  LiPo 3.7V ──── │ TP4056   │ ──── Slide Switch ──── VSYS (Pico)
  (502535)   ──── │ Charger  │                         GND  (Pico)
                  └────┬─────┘
                       │
                   USB-C IN
                 (charge only)
```

- **Battery**: 502535 LiPo, 3.7V 400mAh
- **TP4056**: Micro/USB-C charging module with DW01 protection
- **Slide switch**: MSK-12C02 style, between TP4056 OUT+ and Pico VSYS. Side-mounted in housing with red/green indicator recesses visible through the shell
- **Pico VSYS**: Accepts 1.8–5.5V, has onboard 3.3V regulator

## I2C Bus — OLED Display

```
  Pico GP4 (SDA) ────┬──── OLED SDA
                      ├──── 4.7kΩ ──── 3V3
  Pico GP5 (SCL) ────┬──── OLED SCL
                      ├──── 4.7kΩ ──── 3V3
  3V3 ─────────────────── OLED VCC
  GND ─────────────────── OLED GND
```

- I2C0 on GP4/GP5 (default I2C0 pins)
- 4.7kΩ pull-ups to 3V3 (some OLED modules include onboard pull-ups — check before adding)
- Bus speed: 400kHz

## Buttons (Active Low)

```
  GP10 ──── Button 1 (Dictation) ──── GND
  GP11 ──── Button 2 (Mode)      ──── GND
  GP12 ──── Button 3 (Yes)       ──── GND
  GP13 ──── Button 4 (No)        ──── GND
```

- Internal pull-ups enabled in firmware (`Pin.PULL_UP`)
- Active LOW: pressed = GND, released = 3V3
- Software debounce: 50ms
- Layout (left hand reaching to right forearm):
  - Top row (elbow end): Dictation (index), Mode (middle)
  - Bottom row (wrist end): Yes (ring), No (pinky)

## Vibration Motor (PWM via NPN)

```
  3V3 ──── Vibration Motor (+) ──┬── Motor (-) ──── NPN Collector
                                 │
                           1N4148 Diode
                           (flyback, cathode to 3V3)
                                 │
                                 └── NPN Collector
                                     NPN Base ──── 1kΩ ──── GP15
                                     NPN Emitter ──── GND
```

- **NPN transistor**: 2N2222 or equivalent
- **1kΩ base resistor**: limits current from GPIO
- **1N4148 flyback diode**: across motor terminals, cathode to 3V3 side
- PWM on GP15 for variable intensity

## Status LED

```
  GP16 ──── 100Ω ──── LED (+) ──── LED (-) ──── GND
```

- Standard 3mm LED (green or white)
- 100Ω resistor for ~10mA at 3.3V
- PWM capable for breathing/pulsing effects

## Full Connection Summary

```
                    ┌─────────────────────────┐
                    │      Pico 2 W            │
                    │                          │
          USB-C ◄───│ USB                      │
                    │                          │
     OLED SDA  ◄───│ GP4  (I2C0 SDA)         │
     OLED SCL  ◄───│ GP5  (I2C0 SCL)         │
                    │                          │
     Button 1  ◄───│ GP10                     │
     Button 2  ◄───│ GP11                     │
     Button 3  ◄───│ GP12                     │
     Button 4  ◄───│ GP13                     │
                    │                          │
     Motor NPN ◄───│ GP15 (PWM)              │
     LED       ◄───│ GP16 (PWM)              │
                    │                          │
     TP4056 OUT ───│ VSYS                     │
     GND ──────────│ GND                      │
     3V3 OUT ◄─────│ 3V3                      │
                    └─────────────────────────┘
```
