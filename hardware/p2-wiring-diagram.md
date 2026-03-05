# Roam P2 — Wiring Diagram (Build 2A: SH1106 Screen)

Complete point-to-point wiring for the Seeed XIAO nRF52840 Sense build.
Small screen (1.3" SH1106) + 502535 LiPo battery + slide switch.

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

## Power Circuit

```
 ╔══════════════════════════════════════════════════════════════════════╗
 ║  POWER — Battery + switch on positive rail                         ║
 ║                                                                    ║
 ║                        MSK-12C02                                   ║
 ║                      ┌───┤├───┐                                    ║
 ║   LiPo BAT+ ────────┤ 1  2  3├                                    ║
 ║     (red)            └───┬────┘                                    ║
 ║                          │                                         ║
 ║                      SWITCHED +V ──┬── OLED VCC                    ║
 ║                                    ├── Motor (+)                   ║
 ║                                    └── (any 5V loads)              ║
 ║                                                                    ║
 ║   LiPo BAT- ──── GND rail ──┬── XIAO GND pad                     ║
 ║     (black)                  ├── OLED GND                          ║
 ║                              ├── Motor (-) via NPN                 ║
 ║                              ├── LED (-)                           ║
 ║                              └── All button commons                ║
 ║                                                                    ║
 ║   Switch wiring (3-pin SPDT, MSK-12C02):                          ║
 ║     Pin 1 (common/center) ── BAT+                                  ║
 ║     Pin 2 (one side)      ── SWITCHED +V                           ║
 ║     Pin 3 (other side)    ── (not connected)                       ║
 ║                                                                    ║
 ║   XIAO battery: connect via JST connector on underside,            ║
 ║   OR solder BAT+/BAT- pads directly. BAT- = GND (same net).       ║
 ║                                                                    ║
 ║   USB-C: charges battery when plugged in (onboard charger).        ║
 ║   VUSB pad: NOT wired — not needed for battery operation.          ║
 ╚══════════════════════════════════════════════════════════════════════╝
```

## OLED Display

```
 ╔══════════════════════════════════════════════════════════════════════╗
 ║  OLED DISPLAY — SH1106 128×64 1.3" I2C                            ║
 ║                                                                    ║
 ║       SWITCHED +V ───────────────────── VCC                        ║
 ║          D4 (SDA) ───────────────────── SDA                        ║
 ║          D5 (SCL) ───────────────────── SCL                        ║
 ║          GND ────────────────────────── GND                        ║
 ║                                                                    ║
 ║   VCC is battery voltage through the switch (~3.7–4.2V).           ║
 ║   SH1106 charge pump works at LiPo voltages — confirmed working.  ║
 ║                                                                    ║
 ║   Firmware uses TWIM1 (not Wire library, not TWIM0).               ║
 ║   TWIM0 conflicts with BLE softdevice — data writes hang.          ║
 ║   No external pull-ups needed — module has onboard pull-ups.       ║
 ║                                                                    ║
 ║   Pin order on module (verify yours): GND, VCC, SCL, SDA          ║
 ╚══════════════════════════════════════════════════════════════════════╝
```

## Buttons

```
 ╔══════════════════════════════════════════════════════════════════════╗
 ║  BUTTONS — Tactile switches, active low                            ║
 ║                                                                    ║
 ║   Internal pull-ups enabled in firmware (no external resistors)    ║
 ║                                                                    ║
 ║          D0 ───────┤ ○  ○ ├────── GND      Index  (Dictation)     ║
 ║          D1 ───────┤ ○  ○ ├────── GND      Middle (Mode)          ║
 ║          D2 ───────┤ ○  ○ ├────── GND      Ring   (Yes/Approve)   ║
 ║          D3 ───────┤ ○  ○ ├────── GND      Pinky  (No/Escape)    ║
 ║                                                                    ║
 ║          D8 ───────┤ ○  ○ ├────── GND      Scroll Forward (thumb) ║
 ║          D9 ───────┤ ○  ○ ├────── GND      Scroll Back (thumb)    ║
 ║                                                                    ║
 ║   Physical layout (top face, left hand on right forearm):          ║
 ║                                                                    ║
 ║        ┌──────── elbow side ────────┐                              ║
 ║        │                            │                              ║
 ║        │  [Index] [Middle] [Ring] [Pinky]   ◄── top face           ║
 ║        │                            │                              ║
 ║        │                 [Scrl Fwd] │   ◄── right side wall        ║
 ║        │                [Scrl Back] │                              ║
 ║        │                            │                              ║
 ║        └──────── wrist side ────────┘                              ║
 ║                                                                    ║
 ║   Button actions:                                                  ║
 ║     Index  = D0  short: Dictation    long: Tmux pane               ║
 ║     Middle = D1  short: Cycle mode   long: BLE switch              ║
 ║     Ring   = D2  short: y + Enter    long: Tab + Enter             ║
 ║                  double: Enter only                                ║
 ║     Pinky  = D3  short: Escape       long: Ctrl+C                 ║
 ║     Scroll Fwd  = D8  short/long: next message                    ║
 ║     Scroll Back = D9  short/long: prev message                    ║
 ╚══════════════════════════════════════════════════════════════════════╝
```

## Motor

```
 ╔══════════════════════════════════════════════════════════════════════╗
 ║  VIBRATION MOTOR — NPN transistor driver                           ║
 ║                                                                    ║
 ║   SWITCHED +V ──────┬──────────── Motor (+, red)                   ║
 ║                      │                │                            ║
 ║                 ┌──┤◄├──┐        Motor (-, blue)                   ║
 ║                 │ 1N4148 │            │                            ║
 ║                 │(flyback)│           │                            ║
 ║                 └────────┘     ┌──────┘                            ║
 ║                                │  C                                ║
 ║                              ┌─┴─┐                                 ║
 ║          D6 ──── 1kΩ ───── B│NPN │ 2N2222                         ║
 ║                              └─┬─┘                                 ║
 ║                                │  E                                ║
 ║                               GND                                  ║
 ║                                                                    ║
 ║   Motor powered from switched battery voltage (~3.7–4.2V).        ║
 ║   Flyback diode: cathode (band) toward positive rail.             ║
 ╚══════════════════════════════════════════════════════════════════════╝
```

## LED

```
 ╔══════════════════════════════════════════════════════════════════════╗
 ║  STATUS LED                                                        ║
 ║                                                                    ║
 ║          D7 ──── 100Ω ──── LED (+) ──── LED (-) ──── GND          ║
 ║                               ▲                                    ║
 ║                          5mm red                                   ║
 ║                        (diffused)                                  ║
 ║                                                                    ║
 ║   LED driven from 3.3V GPIO — no switched power needed.            ║
 ║   ~15mA at 3.3V with 100Ω.                                        ║
 ║                                                                    ║
 ║   NOTE: LED_BUILTIN (red, next to USB-C) is active LOW.           ║
 ║   Currently used for BLE status blink in firmware.                 ║
 ║   ROAM_LED_PIN (D7) initialized but not yet driven in loop.       ║
 ╚══════════════════════════════════════════════════════════════════════╝
```

## Battery Monitoring

```
 ╔══════════════════════════════════════════════════════════════════════╗
 ║  BATTERY MONITORING (firmware, no extra wiring)                    ║
 ║                                                                    ║
 ║   PIN_VBAT reads battery voltage via nRF52's internal ADC.         ║
 ║   No external voltage divider needed — built into the board.       ║
 ║                                                                    ║
 ║   LiPo discharge curve: 4.2V=100%, 3.7V=50%, 3.3V=10%, 3.0V=0%  ║
 ║   Sampled every 60 seconds, displayed in status bar.               ║
 ╚══════════════════════════════════════════════════════════════════════╝
```

## Bill of Materials

| Qty | Component                    | Value/Spec            | Notes                           |
|-----|------------------------------|-----------------------|---------------------------------|
| 1   | Seeed XIAO nRF52840 Sense    | nRF52840 + BLE 5.0    | Main MCU + BLE                  |
| 1   | SH1106 OLED module           | 128×64, 1.3", I2C     | 4-pin (GND/VCC/SCL/SDA)        |
| 4   | Tactile switch               | 6×6mm                 | Main buttons (D0-D3)            |
| 2   | Tactile switch               | 6×6mm                 | Scroll buttons (D8-D9)          |
| 1   | Vibration motor              | 3V coin type          | Powered from switched BAT+      |
| 1   | 2N2222 NPN transistor        | or equivalent          | Motor driver                    |
| 1   | 1N4148 diode                 | Signal diode           | Flyback protection              |
| 1   | LED                          | 5mm red diffused       | Status indicator                |
| 1   | LiPo battery                 | 3.7V 502535 (400mAh)  | JST SH 1.0mm connector         |
| 1   | Slide switch                 | MSK-12C02 SPDT        | Power on/off                    |
| 1   | Resistor                     | 100Ω                  | LED current limit               |
| 1   | Resistor                     | 1kΩ                   | NPN base                        |

## Wire Color Convention (suggested)

| Color  | Signal       |
|--------|--------------|
| Red    | BAT+ / +V    |
| Black  | GND          |
| Blue   | SDA          |
| Yellow | SCL          |
| White  | Button wires |
| Green  | Motor / LED  |

## Flashing

The XIAO is enclosed in the housing — reset button is not accessible.
Use 1200-baud touch to enter DFU bootloader over USB:

```bash
python3 -c "import serial, time; s = serial.Serial('PORT', 1200); time.sleep(0.5); s.close()"
# Wait 3 seconds, then flash:
make p2-flash
```

Port name varies between flashes (`usbmodem101`, `usbmodem1101`, `usbmodem2101`).
Always check `arduino-cli board list` first.

## Hardware Gotchas

- **TWIM0 conflicts with Bluefruit**: BLE softdevice uses the same peripheral group.
  Display MUST use TWIM1 with direct register access. See `display.cpp`.
- **Wire library has no timeouts**: Seeed BSP spins forever on stuck I2C.
  Firmware uses raw TWIM1 registers with timeout loop.
- **SH1106 works on LiPo voltage**: Charge pump runs fine at 3.7–4.2V.
  Previous assumption that 5V was required was wrong.
- **LED_BUILTIN is active LOW**: `LOW` = on, `HIGH` = off.
- **Port flapping**: Serial port name changes between flashes. Always check
  `arduino-cli board list` before flashing.
- **Switch on positive rail**: MSK-12C02 between BAT+ and all loads (OLED, motor).
  XIAO itself always powered via JST — switch only controls peripherals.
