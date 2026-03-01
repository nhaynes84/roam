# Roam P2 — Wiring Diagram (Build 2A: SH1106 Screen)

Complete point-to-point wiring for the Seeed XIAO nRF52840 Sense build.

## Board Pinout Reference

```
                      ┌───USB-C───┐
                D0  ──┤  [RST]    ├── 5V (VUSB)
                D1  ──┤           ├── GND
                D2  ──┤           ├── 3V3
                D3  ──┤           ├── D10
       SDA ◄── D4  ──┤           ├── D9 ──► Scroll Back
       SCL ◄── D5  ──┤           ├── D8 ──► Scroll Fwd
     Motor ◄── D6  ──┤           ├── D7 ──► LED
                      ├───────────┤
                      │  BAT(JST) │
                      └───────────┘
```

## Circuit Diagram

```
 ╔══════════════════════════════════════════════════════════════════════╗
 ║  POWER                                                              ║
 ║                                                                     ║
 ║   Built-in: XIAO has onboard USB-C charging + JST battery port     ║
 ║   No external TP4056 or power switch needed.                        ║
 ║                                                                     ║
 ║   LiPo 3.7V ──► JST connector (underside of XIAO)                  ║
 ║   USB-C ──► charges battery automatically                           ║
 ║                                                                     ║
 ║   5V (VUSB): only available when USB is plugged in                  ║
 ║   3V3: always available (from onboard regulator)                    ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  OLED DISPLAY — SH1106 128×64 1.3" (Build 2A)                      ║
 ║                                                                     ║
 ║       5V (VUSB) ──────────────────────── VCC                        ║
 ║          D4 (SDA) ──────────────────── SDA                          ║
 ║          D5 (SCL) ──────────────────── SCL                          ║
 ║          GND ───────────────────────── GND                          ║
 ║                                                                     ║
 ║   CRITICAL: VCC must be 5V (VUSB pad), NOT 3V3.                    ║
 ║   At 3.3V the I2C bus responds (device at 0x3C) but the OLED       ║
 ║   panel won't light — charge pump needs higher voltage.             ║
 ║                                                                     ║
 ║   Firmware uses TWIM1 (not Wire library, not TWIM0).               ║
 ║   TWIM0 conflicts with BLE softdevice — data writes hang.          ║
 ║   No external pull-ups needed — module has onboard pull-ups.        ║
 ║                                                                     ║
 ║   Pin order on module (verify yours): GND, VCC, SCL, SDA           ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  BUTTONS — Tactile switches, active low                             ║
 ║                                                                     ║
 ║   Internal pull-ups enabled in firmware (no external resistors)     ║
 ║                                                                     ║
 ║          D0 ───────┤ ○  ○ ├────── GND      Index  (Dictation)      ║
 ║          D1 ───────┤ ○  ○ ├────── GND      Middle (Mode)           ║
 ║          D2 ───────┤ ○  ○ ├────── GND      Ring   (Yes/Approve)    ║
 ║          D3 ───────┤ ○  ○ ├────── GND      Pinky  (No/Escape)     ║
 ║                                                                     ║
 ║          D8 ───────┤ ○  ○ ├────── GND      Scroll Forward (thumb)  ║
 ║          D9 ───────┤ ○  ○ ├────── GND      Scroll Back (thumb)     ║
 ║                                                                     ║
 ║   Physical layout (left hand on right forearm, buttons face up):    ║
 ║                                                                     ║
 ║        ┌─── elbow side ───┐                                         ║
 ║        │                  │                                         ║
 ║        │  [Index] [Middle]│     Index  = D0 (short: dictation,      ║
 ║        │                  │                  long:  tmux pane)      ║
 ║        │  [Ring]  [Pinky] │     Middle = D1 (short: cycle mode,     ║
 ║        │                  │                  long:  BLE switch)     ║
 ║        │                  │     Ring   = D2 (short: y + Enter,      ║
 ║        └─── wrist side ──┘                  long:  Tab + Enter,    ║
 ║                                             double: Enter only)    ║
 ║                                  Pinky  = D3 (short: Escape,        ║
 ║                                               long:  Ctrl+C)      ║
 ║                                                                     ║
 ║   Scroll buttons (thumb, side of housing):                          ║
 ║     Scroll Fwd  = D8 (next message / next line)                     ║
 ║     Scroll Back = D9 (prev message / prev line)                     ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  VIBRATION MOTOR — NPN transistor driver                            ║
 ║                                                                     ║
 ║       5V (VUSB) ──────┬──────────── Motor (+, red)                  ║
 ║                        │                │                           ║
 ║                   ┌──┤◄├──┐        Motor (-, blue)                  ║
 ║                   │ 1N4148 │            │                           ║
 ║                   │(flyback)│           │                           ║
 ║                   └────────┘     ┌──────┘                           ║
 ║                                  │  C                               ║
 ║                                ┌─┴─┐                                ║
 ║            D6 ──── 1kΩ ───── B│NPN │ 2N2222                        ║
 ║                                └─┬─┘                                ║
 ║                                  │  E                               ║
 ║                                 GND                                 ║
 ║                                                                     ║
 ║   Motor positive → 5V (VUSB), NOT 3V3.                             ║
 ║   Coin motors rated 3V won't spin at 3.3V through transistor.      ║
 ║   Flyback diode: cathode (band) toward VUSB side.                  ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  STATUS LED                                                         ║
 ║                                                                     ║
 ║            D7 ──── 100Ω ──── LED (+) ──── LED (-) ──── GND         ║
 ║                                 ▲                                   ║
 ║                            5mm red                                  ║
 ║                          (diffused)                                 ║
 ║                                                                     ║
 ║   ~15mA at 3.3V with 100Ω. Solid when BLE connected,              ║
 ║   blink when advertising.                                           ║
 ║                                                                     ║
 ║   NOTE: LED_BUILTIN (red, next to USB-C) is also available.        ║
 ║   Active LOW — use for debug diagnostics without external LED.      ║
 ╚══════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════╗
 ║  BATTERY MONITORING (firmware, no extra wiring)                     ║
 ║                                                                     ║
 ║   PIN_VBAT reads battery voltage via nRF52's internal ADC.          ║
 ║   No external voltage divider needed — built into the board.        ║
 ║                                                                     ║
 ║   USB power detection available via checking VUSB pin state.        ║
 ╚══════════════════════════════════════════════════════════════════════╝

## Bill of Materials

| Qty | Component                    | Value/Spec            | Notes                           |
|-----|------------------------------|-----------------------|---------------------------------|
| 1   | Seeed XIAO nRF52840 Sense    | nRF52840 + BLE 5.0    | Main MCU + BLE                  |
| 1   | SH1106 OLED module           | 128×64, 1.3", I2C     | 4-pin (GND/VCC/SCL/SDA)        |
| 4   | Tactile switch               | 6×6mm                 | Main buttons (D0-D3)            |
| 2   | Tactile switch               | 6×6mm                 | Scroll buttons (D8-D9)          |
| 1   | Vibration motor              | 3V coin type          | Powered from VUSB (5V)          |
| 1   | 2N2222 NPN transistor        | or equivalent          | Motor driver                    |
| 1   | 1N4148 diode                 | Signal diode           | Flyback protection              |
| 1   | LED                          | 5mm red diffused       | Status indicator                |
| 1   | LiPo battery                 | 3.7V 400-600mAh       | JST SH 1.0mm connector         |
| 1   | Resistor                     | 100Ω                  | LED current limit               |
| 1   | Resistor                     | 1kΩ                   | NPN base                        |

No external charger, power switch, or I2C pull-ups needed — all built into the
XIAO board or OLED module.

## Wire Color Convention (suggested)

| Color  | Signal     |
|--------|------------|
| Red    | 5V / VUSB  |
| Black  | GND        |
| Blue   | SDA        |
| Yellow | SCL        |
| White  | Button wires |
| Green  | Motor / LED |
