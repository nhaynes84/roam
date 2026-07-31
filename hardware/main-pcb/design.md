# Roam Main Board — Design Spec

Custom PCB replacing the XIAO nRF52840 Sense and all hand-wired connections.
Integrates BLE+Wi-Fi module, charger, regulator, IMU, and motor driver on one board.
JST plug-in connectors for every peripheral — zero solder assembly.

## Why

P2 prototype uses 12+ hand-soldered wires between XIAO and peripherals. Fragile,
tedious, unreproducible. This board consolidates everything into a single PCB with
keyed connectors. Plug in battery, buttons, motor, LED, display, switch — done.
Path to a sellable product.

**ESP32-C6 upgrade** (from nRF52840): Adds Wi-Fi 6 as an opt-in fallback alongside
BLE 5.0. Wi-Fi disabled by default for power savings — enable via BLE command or
button combo for OTA updates, HTTP push notifications, or future features.

## Board Dimensions

- **Width**: 45mm (X)
- **Height**: 35mm (Y)
- **Thickness**: 1.6mm (standard 2-layer)
- **Mounting**: 4× M2 holes at corners (39mm × 29mm spacing, 3mm inset from edges)
- **Target fit**: alongside 502535 LiPo battery in Roam housing

## Connectors

| Ref | Type | Pins | Pitch | Connects To |
|-----|------|------|-------|-------------|
| J1 | USB-C receptacle | 16 | — | Host (charge + program) |
| J2 | JST-SH 1.0mm | 5 | 1.0mm | Finger buttons (4 sig + GND) |
| J3 | JST-SH 1.0mm | 3 | 1.0mm | Scroll buttons (2 sig + GND) |
| J4 | JST-SH 1.0mm | 2 | 1.0mm | Motor (leads only, driver on-board) |
| J6 | JST-SH 1.0mm | 4 | 1.0mm | Display (VCC, GND, SDA, SCL) |
| J7 | JST-SH 1.0mm | 3 | 1.0mm | Power switch (off-board MSK-12C02) |
| J8 | JST-PH 2.0mm | 2 | 2.0mm | LiPo battery (industry standard) |
| J9 | 1×4 pin header | 4 | 2.54mm | UART debug (hand-solder) |

All JST-SH connectors are horizontal/right-angle SMD (SM0xB-SRSS-TB series).
J8 uses JST-PH (S2B-PH-K-S) — the standard LiPo battery connector.
J9 is a through-hole 2.54mm header for UART debug during firmware bring-up.

**Status LED (D3)** is mounted directly on the PCB (0603 SMD). Housing needs a
light pipe, window, or edge-positioned LED to be visible from outside.

### Connector Pin Assignments

**J1 — USB-C** (USB 2.0, ESP32-C6 full-speed via built-in USB Serial/JTAG):
```
A1/B1/A12/B12: GND (shield)
A4/B4/A9/B9:   VBUS (5V)
A5:             CC1 → R8 (5.1K) → GND
B5:             CC2 → R9 (5.1K) → GND
A6:             D+ → U4 (ESD) → ESP32-C6 GPIO13
A7:             D- → U4 (ESD) → ESP32-C6 GPIO12
```

**J2 — Finger Buttons** (active low, internal pull-ups):
```
Pin 1: Index   → GPIO0
Pin 2: Middle  → GPIO1
Pin 3: Ring    → GPIO2
Pin 4: Pinky   → GPIO4
Pin 5: GND
```

**J3 — Scroll Buttons** (active low, internal pull-ups):
```
Pin 1: Scroll Fwd  → GPIO5
Pin 2: Scroll Back  → GPIO14
Pin 3: GND
```

**J4 — Motor**:
```
Pin 1: Motor+  → 3V3_SYS (from on-board MOSFET drain)
Pin 2: Motor-  → GND (switched by MOSFET)
```
Note: Connector carries switched current. Motor+ goes to Q1 drain via
on-board trace, Motor- is direct GND. Max ~120mA for coin motor.

**J6 — Display** (I2C, compatible with SH1106/SSD1309 modules):
```
Pin 1: VCC  → 3V3_SYS
Pin 2: GND
Pin 3: SDA  → I2C bus (GPIO6)
Pin 4: SCL  → I2C bus (GPIO7)
```

**J7 — Power Switch** (off-board MSK-12C02 SPDT):
```
Pin 1: VBAT      → from battery/charger node
Pin 2: VBAT_SW   → switched battery, returns to LDO input
Pin 3: NC        → switch OFF position (not connected on PCB)
```
Wire: Pin 1 → switch common (center), Pin 2 → switch ON throw,
Pin 3 → switch OFF throw. Switch breaks the power path between
battery and LDO — device fully off when switch is in OFF position.

**J8 — LiPo Battery** (JST-PH 2.0mm, standard polarity):
```
Pin 1: BAT+  → VBAT node
Pin 2: BAT-  → GND
```

**J9 — UART Debug** (2.54mm, hand-solder):
```
Pin 1: 3V3   → 3V3_SYS (logic analyzer reference)
Pin 2: TX    → GPIO16 (UART0 TX)
Pin 3: RX    → GPIO17 (UART0 RX)
Pin 4: GND
```

## Schematic — Signal Path

### Power — Charging (USB → Battery)

```
USB VBUS (5V) ──┬── C9 (10uF) ── GND          ← VBUS bulk cap
                │
                ├── U4 pin 5 (VBUS)             ← ESD reference
                │
                └── U2 (MCP73831T) VDD (pin 4)
                    │
                    ├── C1 (4.7uF) ── GND       ← input bypass
                    │
                    ├── STAT (pin 1) ── D2 (LED cathode)
                    │                   D2 anode ── R2 (1K) ── VBUS
                    │
                    ├── PROG (pin 5) ── R1 (2K) ── GND
                    │                   ↑ sets charge current: 1000V/2K = 500mA
                    │
                    ├── VSS (pin 2) ── GND
                    │
                    └── VBAT (pin 3) ──┬── C2 (4.7uF) ── GND    ← output bypass
                                       │
                                       └── VBAT node ──┬── J8 pin 1 (battery+)
                                                       └── J7 pin 1 (to switch)
```

MCP73831T-2ACI/OT: 4.20V regulation, ±0.75% accuracy.
STAT is open-drain: LOW = charging, HIGH-Z = done. D2 lights during charge.
R1 = 2kΩ programs 500mA charge current (IREG = 1000/RPROG).

**Charge path is independent of the power switch** — battery charges via USB
whether the device is on or off. Normal usage: plug in USB, device runs from
battery while simultaneously charging (same as any phone or Adafruit Feather).
Switch OFF + USB plugged in: battery charges, MCU stays off.

### Power — System Rail (Battery → 3.3V)

```
VBAT node ── J7 pin 1 ──→ [off-board switch] ──→ J7 pin 2 ── VBAT_SW
                                                                 │
                                                    U3 (AP2112K-3.3) VIN (pin 1)
                                                                 │
                                                    ├── C3 (1uF) ── GND      ← input bypass
                                                    ├── EN (pin 3) ── VIN     ← always enabled
                                                    ├── GND (pin 2) ── GND
                                                    ├── BP (pin 4) ── NC
                                                    │
                                                    └── VOUT (pin 5) ── 3V3_SYS
                                                                          │
                                                         C4 (1uF) ──┤── GND    ← output bypass
                                                                     │
                                                         ┌───────────┼──────────────────────┐
                                                         │           │                      │
                                                    U1 3V3      U5 VDD/VDDIO          System loads
                                                  (ESP32-C6)  (LSM6DS3TR-C)     (I2C pull-ups,
                                                                                  display via J6,
                                                                                  motor via Q1,
                                                                                  LED via R3)
```

AP2112K-3.3: 600mA max output, 250mV dropout at full load.
LiPo range 3.0–4.2V → 3.3V out (dropout OK above ~3.55V).
EN tied to VIN — regulator active whenever switch is ON.

### Full Power Tree

```
USB 5V ──→ MCP73831T ──→ LiPo battery (charging path, always connected)

LiPo VBAT ──→ Power switch (off-board, J7) ──→ AP2112K LDO ──→ 3V3_SYS
                                                                   │
                                     ┌─────────────────────────────┤
                                     │           │           │     │
                                  ESP32-C6   LSM6DS3TR-C   R4/R5  J6 VCC
                                (BLE+WiFi+    (IMU)       (I2C)  (Display)
                                  USB)
                                     │
                              ┌──────┼──────┐
                              │      │      │
                           Motor   LED    R6/R7
                          (via Q1) (via R3) (VBAT divider)
```

Battery voltage divider on VBAT_SW (after switch):

```
VBAT_SW ── R6 (1M) ──┬── R7 (1M) ── GND
                      │
                      └── GPIO3 (ADC1_CH3, ESP32-C6)
```

Divider ratio: 0.5 → 4.2V battery reads as 2.1V (within ESP32-C6 ADC range).
Software: `voltage = adc_reading * 2 * 3.3 / 4096` (12-bit ADC, ~3.3V ref with attenuation).

### USB (Data Path)

```
J1 (USB-C) ──── D+ (A6) ──── U4 pin 3 (I/O2) ── U4 pin 4 (I/O2) ──── ESP32-C6 GPIO13
             ── D- (A7) ──── U4 pin 1 (I/O1) ── U4 pin 6 (I/O1) ──── ESP32-C6 GPIO12
             ── VBUS ─────── U4 pin 5 (VBUS)

CC1 (A5) ── R8 (5.1K) ── GND      ← identifies as USB sink/UFP
CC2 (B5) ── R9 (5.1K) ── GND
```

USBLC6-2SC6 pinout (SOT-23-6):
```
Pin 1: I/O1    ← USB D- from connector
Pin 2: GND
Pin 3: I/O2    ← USB D+ from connector
Pin 4: I/O2    → USB D+ to ESP32-C6 GPIO13
Pin 5: VBUS    ← reference voltage
Pin 6: I/O1    → USB D- to ESP32-C6 GPIO12
```

ESP32-C6 has built-in USB Serial/JTAG controller on GPIO12/13. No external
USB-to-serial chip needed. Provides serial console + JTAG debug over one cable.
No VBUS sense trace to module needed — ESP32-C6 detects USB internally.

### Wireless Module (ESP32-C6-MINI-1-N4)

Pre-certified ESP32-C6 module (FCC/CE). RISC-V single-core @ 160MHz.
BLE 5.0 + Wi-Fi 6 (802.11ax, 2.4GHz). 4MB flash, 320KB SRAM.
Internal: 40MHz crystal, antenna, RF matching, flash.
External requirements: 3V3 bypass, EN circuit, GPIO8 strapping pull-up.

```
3V3_SYS ──┬── ESP32-C6-MINI-1 3V3 pin ──┬── C5 (100nF) ── GND    ← close bypass
           │                              └── C6 (10uF) ── GND     ← bulk bypass
           │
           ├── R10 (10K) ──┬── EN pin ──── SW1 ── GND
           │                └── C10 (1uF) ── GND           ← RC delay (τ=10ms)
           │
           └── R11 (10K) ── GPIO8                          ← strapping pull-up

ESP32-C6 GPIO12 ── U4 pin 6 (protected USB D-)
ESP32-C6 GPIO13 ── U4 pin 4 (protected USB D+)
ESP32-C6 GPIO9  ────────────── SW2 ── GND                 (BOOT button)
ESP32-C6 GPIO16 ── J9 pin 2 (UART TX)
ESP32-C6 GPIO17 ── J9 pin 3 (UART RX)
```

**EN pin**: Chip enable, active HIGH. R10 (10K) pull-up + C10 (1uF) RC delay
provides clean power-on reset sequencing and noise rejection. SW1 pulls EN LOW
to reset the chip.

**GPIO8 strapping**: Must be HIGH when GPIO9 is LOW (download mode). R11 (10K)
pull-up ensures valid boot mode entry. After boot, GPIO8 is used for LED output —
the pull-up is negligible against the LED load current. At boot (before firmware
configures GPIO8 as output), the pin is floating input — 10K pull-up drives only
~0.13mA through LED, essentially invisible.

**GPIO9 (BOOT)**: Internal pull-up. HIGH = normal SPI flash boot. Hold SW2
(GPIO9 LOW) + press SW1 (EN LOW → HIGH) = enter download mode for flashing.
Same user gesture as the old DFU entry (hold BOOT + press RESET).

GPIO connections:

| ESP32-C6 GPIO | Function | Route To |
|--------------|----------|----------|
| GPIO0 | Button Index | J2 pin 1 |
| GPIO1 | Button Middle | J2 pin 2 |
| GPIO2 | Button Ring | J2 pin 3 |
| GPIO3 | Battery ADC | R6/R7 divider midpoint |
| GPIO4 | Button Pinky | J2 pin 4 |
| GPIO5 | Scroll Forward | J3 pin 1 |
| GPIO6 | I2C SDA | R5 pull-up + J6 pin 3 + U5 SDA |
| GPIO7 | I2C SCL | R4 pull-up + J6 pin 4 + U5 SCL |
| GPIO8 | LED drive | R3 (100Ω) → J5 pin 1 |
| GPIO9 | BOOT button | SW2 → GND |
| GPIO12 | USB D- | U4 → J1 (USB-C) |
| GPIO13 | USB D+ | U4 → J1 (USB-C) |
| GPIO14 | Scroll Back | J3 pin 2 |
| GPIO15 | Motor gate | Q1 gate |
| GPIO16 | UART TX | J9 pin 2 |
| GPIO17 | UART RX | J9 pin 3 |

**Strapping pin notes**: GPIO4 (MTMS) and GPIO5 (MTDI) are SDIO strapping pins —
irrelevant since we have no SDIO. Internal pull-ups ensure safe boot state.
GPIO8 has external 10K pull-up (R11). GPIO15 is JTAG source select — irrelevant
since we use USB JTAG.

**Pad assignments**: Reference the Espressif ESP32-C6-MINI-1 datasheet v1.4 or
later for physical pad positions. Verify GPIO numbers match module pin numbers
before PCB layout.

### IMU (LSM6DS3TR-C, LGA-14)

Same chip as XIAO nRF52840 Sense. On ESP32-C6, uses standard Wire library
(no TWIM1 workaround needed — no softdevice conflict).

```
3V3_SYS ──┬── U5 VDD (pin 9) ──── C7 (100nF) ── GND
           └── U5 VDDIO (pin 5) ── C8 (100nF) ── GND

U5 pin connections:
  1:  SDO/SA0 ── GND               ← I2C address = 0x6A
  2:  SDX     ── NC                 ← aux SPI (unused)
  3:  SCX     ── NC                 ← aux SPI (unused)
  4:  INT1    ── NC (or route to spare GPIO for wake-on-motion later)
  5:  VDDIO   ── 3V3_SYS + C8
  6:  GND     ── GND
  7:  GND     ── GND
  8:  GND     ── GND (also center pad)
  9:  VDD     ── 3V3_SYS + C7
  10: NC      ── GND
  11: CS      ── 3V3_SYS           ← forces I2C mode (disable SPI)
  12: SCL     ── I2C SCL bus (GPIO7)
  13: SDA     ── I2C SDA bus (GPIO6)
  14: INT2    ── NC
```

I2C address 0x6A (SA0 = GND). Same as XIAO Sense default.
CS tied to VDD to disable SPI and enable I2C.

### I2C Bus

Shared bus: ESP32-C6 (GPIO6/GPIO7) ↔ LSM6DS3TR-C (U5) ↔ Display (J6).

```
3V3_SYS ── R4 (4.7K) ──┬── SCL ── ESP32-C6 GPIO7
                        ├── U5 pin 12 (SCL)
                        └── J6 pin 4 (display SCL)

3V3_SYS ── R5 (4.7K) ──┬── SDA ── ESP32-C6 GPIO6
                        ├── U5 pin 13 (SDA)
                        └── J6 pin 3 (display SDA)
```

ESP32-C6 uses standard Wire library — no TWIM1 workaround needed. The nRF52840's
softdevice I2C conflict does not exist on ESP32-C6. GPIO6/GPIO7 map to the
LP_I2C (low-power I2C) peripheral for optimal power efficiency.

If the display module has its own I2C pull-ups, the parallel resistance
(4.7K ∥ 4.7K = 2.35K) is still safe for 100kHz I2C at 3.3V.

### Motor Driver

```
3V3_SYS ──┬──────────────── J4 pin 1 (Motor +)
           │                      │
      ┌──┤◄├──┐            J4 pin 2 (Motor -)
      │  SS14  │                  │
      │  (D1)  │                  │  Drain
      └────────┘            ┌─────┘
                            │
GPIO15 ───────────── Gate ──┤ Q1 (2N7002)
                            │
                            └── Source ── GND
```

2N7002 N-MOSFET: VGS(th) typ 1.5V, fully enhanced at 3.3V.
No gate resistor needed — gate capacitance ~50pF, slow switching OK.
SS14 flyback diode: cathode toward 3V3_SYS, protects MOSFET from
inductive kick when motor turns off.

Motor current: ~80–100mA typical, ~120mA stall.
2N7002 rated 300mA continuous — comfortable margin.

### Status LED (On-Board, Addressable RGB)

```
GPIO8 ── D3 DIN (SK6812-MINI-E)
3V3_SYS ── D3 VDD
GND ── D3 GND
D3 DOUT ── NC
```

D3 is an SK6812-MINI-E (3.2×2.8mm) addressable RGB LED mounted directly on
the PCB. Single data pin — any color selectable in firmware via NeoPixel or
FastLED library. Eliminates the external LED cable and J5 connector.

Position D3 near the board edge so light is visible through a housing window
or light pipe. Add C11 (100nF) bypass cap close to D3 VDD pin.

Current draw: ~1mA idle (data line quiescent), up to ~20mA at full white.
Run at low brightness for status indicator — typically 3–5mA.

R3 (100Ω series resistor) is no longer needed — SK6812 has built-in constant
current drivers. GPIO8 connects directly to D3 DIN.

Note: GPIO8 has R11 (10K) pull-up for boot strapping. At boot (pin floating),
pull-up provides a weak HIGH on DIN — SK6812 ignores invalid data and stays
off until firmware sends a valid NeoPixel frame.

### Buttons (External, via J2 and J3)

All buttons are simple switches to GND. ESP32-C6 internal pull-ups
enabled in firmware (INPUT_PULLUP) — no external pull-up resistors needed.

```
J2 pin 1 (Index)   ── GPIO0     ┐
J2 pin 2 (Middle)  ── GPIO1     │  Buttons switch
J2 pin 3 (Ring)    ── GPIO2     │  signal to GND
J2 pin 4 (Pinky)   ── GPIO4     │  via J2/J3 GND pin
J2 pin 5           ── GND       ┘

J3 pin 1 (Scroll Fwd)  ── GPIO5   ┐
J3 pin 2 (Scroll Back)  ── GPIO14  │
J3 pin 3                ── GND     ┘
```

### BOOT and Reset Buttons (On-Board)

```
              R10 (10K)
3V3_SYS ────────┬──── EN (ESP32-C6) ──── SW1 ── GND
                │
                └── C10 (1uF) ── GND    ← RC delay (τ=10ms)

              R11 (10K)
3V3_SYS ────────── GPIO8               ← strapping pull-up

GPIO9 (internal pull-up) ────────────── SW2 ── GND
```

SW1 = Reset. Press to reset MCU (pulls EN LOW). RC delay (R10+C10) prevents
noise from causing spurious resets.

SW2 = BOOT. Hold SW2 (GPIO9 LOW) + press SW1 to enter download mode.
GPIO8 must be HIGH during download — guaranteed by R11 pull-up.

Both switches are SMD tactile (3×6×2.5mm), low-profile for housing fit.

## GPIO Mapping (Complete)

| ESP32-C6 GPIO | Function | Direction | Connector | Notes |
|--------------|----------|-----------|-----------|-------|
| GPIO0 | Button Index | Input | J2 pin 1 | Internal pull-up |
| GPIO1 | Button Middle | Input | J2 pin 2 | Internal pull-up |
| GPIO2 | Button Ring | Input | J2 pin 3 | Internal pull-up |
| GPIO3 | Battery ADC | Input | On-board divider | ADC1_CH3, 1M+1M divider |
| GPIO4 | Button Pinky | Input | J2 pin 4 | Internal pull-up, MTMS strapping (safe) |
| GPIO5 | Scroll Forward | Input | J3 pin 1 | Internal pull-up, MTDI strapping (safe) |
| GPIO6 | I2C SDA | Bidir | J6 + U5 | 4.7K ext. pull-up, LP_I2C_SDA |
| GPIO7 | I2C SCL | Bidir | J6 + U5 | 4.7K ext. pull-up, LP_I2C_SCL |
| GPIO8 | LED data | Output | On-board D3 (SK6812) | Strapping pin — R11 (10K) pull-up required |
| GPIO9 | BOOT button | Input | On-board SW2 | Internal pull-up, LOW = download mode |
| GPIO12 | USB D- | Bidir | J1 via U4 | Dedicated USB Serial/JTAG |
| GPIO13 | USB D+ | Bidir | J1 via U4 | Dedicated USB Serial/JTAG |
| GPIO14 | Scroll Back | Input | J3 pin 2 | Internal pull-up |
| GPIO15 | Motor gate | Output | On-board Q1 | JTAG strapping (irrelevant) |
| GPIO16 | UART TX | Output | J9 pin 2 | Debug console |
| GPIO17 | UART RX | Input | J9 pin 3 | Debug console |
| EN | Chip Enable | Input | SW1 + R10 + C10 | Active HIGH, RC reset |

**Firmware impact**: Requires new Arduino core (`arduino-esp32` v3.x) and BLE
stack (NimBLE instead of Bluefruit). I2C uses standard Wire library — no TWIM1
workaround needed. Pin definitions in a new `config.h` using ESP32-C6 GPIO
numbers. FQBN: `esp32:esp32:esp32c6`.

## Power Budget

| Load | Typical | Peak | Notes |
|------|---------|------|-------|
| ESP32-C6 (BLE active) | 20mA | 130mA | Advertising + connected |
| ESP32-C6 (CPU active) | 12mA | 15mA | RISC-V @ 160MHz |
| ESP32-C6 (Wi-Fi TX) | 60mA | 350mA | OFF by default, opt-in only |
| LSM6DS3TR-C | 0.9mA | 0.9mA | Normal mode, accel+gyro |
| Display (SH1106) | 15mA | 20mA | Typical OLED draw |
| I2C pull-ups | 0.7mA | 0.7mA | 3.3V / 4.7K × 2 |
| Motor (coin vibration) | 80mA | 120mA | Intermittent, <500ms bursts |
| LED (status) | 0mA | 13mA | Intermittent |
| Battery divider | 0.002mA | 0.002mA | 3.3V / 2M |
| **BLE mode (no motor/LED)** | **~49mA** | **~167mA** | |
| **BLE mode (all active)** | **~129mA** | **~300mA** | |
| **Wi-Fi mode (all active)** | **~189mA** | **~520mA** | Unlikely simultaneous peak |

**AP2112K headroom**: 600mA max — BLE peak 300mA (50% of capacity), Wi-Fi peak
520mA (87%) is tight but within spec. Wi-Fi TX + motor stall simultaneously is
extremely brief and unlikely. Internal current limiting and thermal shutdown
protect the LDO gracefully.

**Battery life estimate** (1250mAh LiPo, BLE mode):
- Idle BLE + display: ~49mA → ~25 hours
- Active use (BLE + display + occasional motor): ~65mA → ~19 hours
- Wi-Fi active: ~130mA → ~9 hours (opt-in scenarios only)

**Tradeoff vs nRF52840**: ~2x higher idle current in BLE mode. The 1250mAh
battery provides adequate multi-day runtime. Wi-Fi capability is the payoff.

## PCB Layout Notes

- **2-layer board**, components on top, GND pour on both layers
- **Antenna keep-out zone**: ESP32-C6-MINI-1 antenna is at the **top edge** of
  the module (opposite the GPIO pads). NO copper (traces, pours, planes) within
  15mm of the antenna area per Espressif guidelines. Position module so antenna
  protrudes past the baseboard edge for maximum range.
- **USB-C connector** at one board edge (short side), accessible through housing
- **JST connectors** along remaining edges — J8 (battery) near charger IC,
  J6 (display) and J2/J3 (buttons) on the edge facing the housing exterior
- **MCP73831 + bypass caps** close to USB-C and J8 (short thermal/current loops)
- **AP2112K + bypass caps** close to power switch return (J7)
- **ESP32-C6-MINI-1** near center, antenna end at board edge
- **LSM6DS3TR-C** near ESP32-C6 (short I2C traces), away from motor vibration
  if possible (doesn't affect accel readings significantly)
- **Q1 (MOSFET) + D1 (Schottky)** close together, near J4
- **Bypass caps** within 3mm of their IC power pins
- **GND pour** on bottom layer — continuous, unbroken under ICs
- **Via stitching** around ESP32-C6 ground pads for solid RF ground reference
- **Trace widths**: 0.25mm (10mil) for signals, 0.5mm (20mil) for power,
  0.3mm for USB differential pair (90Ω impedance not critical at full-speed
  12Mbps, but match lengths within 2mm)

## Key Design Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Wireless module | ESP32-C6-MINI-1-N4 | FCC/CE pre-certified, BLE 5.0 + Wi-Fi 6, $2.83 on LCSC |
| 2 | Charger | MCP73831T-2ACI/OT | Proven (Adafruit Feather), single-cell, programmable current, SOT-23-5 |
| 3 | LDO | AP2112K-3.3 | 600mA (vs XC6206's 200mA), handles motor + radio peaks, low dropout |
| 4 | Motor driver | 2N7002 MOSFET | Voltage-driven (no base resistor), fully enhanced at 3.3V, SMT SOT-23 |
| 5 | IMU on-board | LSM6DS3TR-C | Same as XIAO Sense — proven I2C device, no extra cable needed |
| 6 | Switch off-board | JST-SH 3-pin (J7) | Must mount in housing wall for user access, cable allows flexible placement |
| 7 | Display connector | I2C JST-SH 4-pin (J6) | Works with SH1106 module now, custom OLED carrier PCB later |
| 8 | Battery connector | JST-PH 2.0mm (J8) | Industry standard — compatible with all hobby LiPo packs |
| 9 | USB ESD | USBLC6-2SC6 | Industry standard USB2.0 protection, low capacitance (3.5pF) |
| 10 | 2-layer PCB | Yes | Sufficient complexity for ~40 components, $2/board at JLCPCB |
| 11 | Charge path bypasses switch | Yes | MCP73831 wired directly to VBUS/VBAT — charges while off |
| 12 | Wi-Fi opt-in | Software-gated | Wi-Fi disabled by default for power savings. Enable via BLE command or button combo. |

## Manufacturing

- **Fab + assembly**: JLCPCB (jlcpcb.com)
- **Layers**: 2
- **Min trace/space**: 6mil/6mil (0.15mm)
- **Min via**: 0.3mm drill, 0.6mm pad
- **Surface finish**: HASL (cheapest) or ENIG (if fine-pitch pads needed)
- **BOM**: see `bom.csv` — all parts from LCSC except J9 (hand-solder)
- **Assembly**: top-side SMT only
- **Hand-solder**: J9 (UART header, 2.54mm through-hole)
- **ESP32-C6-MINI-1-N4**: LCSC C5736265 (check availability — may be extended
  library with one-time setup fee). Alternatively source from DigiKey/Mouser
  and provide as consignment.
- **Stencil**: order with boards for paste application

## Verification Checklist

Before ordering:

- [ ] Cross-check ESP32-C6-MINI-1-N4 pad assignments against Espressif datasheet v1.4
- [ ] Verify GPIO8 has 10K pull-up (R11) to 3V3
- [ ] Verify EN pin has 10K pull-up (R10) + 1uF cap (C10) + SW1 to GND
- [ ] Verify GPIO9 connects to SW2 (BOOT button) to GND
- [ ] Verify all LCSC part numbers are in stock on JLCPCB parts library
- [ ] Confirm antenna keep-out zone matches module datasheet antenna position
- [ ] Run DRC in EasyEDA (6mil min, 0.3mm via)
- [ ] Check USB-C footprint matches C165948 (TYPE-C-31-M-12) datasheet
- [ ] Verify power budget: BLE peak 300mA < 600mA AP2112K max
- [ ] Verify Wi-Fi peak 520mA < 600mA (marginal but within spec)
- [ ] Confirm I2C address: LSM6DS3TR-C at 0x6A (SA0=GND)
- [ ] Measure board outline fits housing (45×35mm target)
- [ ] Verify UART header (J9) pin order: 3V3/TX/RX/GND
- [ ] Export BOM + CPL files from EasyEDA for JLCPCB assembly

## Design Tool

Use **EasyEDA** (easyeda.com) — free, web-based, integrates directly with
JLCPCB parts library. Import BOM part numbers, place components, route traces,
export Gerber + BOM + CPL in one click.

Workflow:
1. Create new project, set board outline to 45×35mm
2. Import each LCSC part number → auto-loads footprint + 3D model
3. Place components per layout notes above
4. Route power traces first (0.5mm), then signals (0.25mm)
5. Add GND pour on both layers
6. Run DRC, fix violations
7. Generate Gerber + BOM + CPL → upload to JLCPCB

## Firmware Migration Notes

Moving from nRF52840 (Adafruit Bluefruit) to ESP32-C6 requires a firmware rewrite:

- **BLE stack**: Bluefruit → NimBLE. Use `ESP32-NimBLE-Keyboard` library for HID.
  Consumer control reports (dictation, recents) require manual HID descriptor setup.
- **I2C**: Standard `Wire.begin(GPIO6, GPIO7)` — no TWIM1 workaround needed.
  The nRF52840 softdevice I2C conflict does not exist on ESP32-C6.
- **IMU**: Same LSM6DS3TR-C at 0x6A. Use Wire library directly instead of raw
  TWIM1 register access. Bus conditioning errata workaround not needed on ESP32.
- **Display**: Same U8g2 library, standard HW_I2C constructor. No custom byte callback.
- **Wi-Fi**: Available via `WiFi.h` in arduino-esp32 v3.x. Disabled by default.
  Potential uses: OTA firmware updates, HTTP push notifications, MQTT.
- **ADC**: 12-bit (vs nRF52840's 10-bit). Update battery voltage formula.
- **USB**: Built-in USB Serial/JTAG. Serial.begin() works over USB automatically.
- **Arduino FQBN**: `esp32:esp32:esp32c6`
- **Bond management**: NimBLE stores bonds in NVS (flash). Survives power cycles
  (unlike P2 RAM-only MAC learning). Bond removal via NVS API.
