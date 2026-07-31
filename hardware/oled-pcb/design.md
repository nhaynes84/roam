# Roam OLED Carrier PCB — Design Spec

Custom carrier board for 2.42" 128x64 SSD1309 OLED panel.
I2C interface, 4-pin plug-and-play connection to XIAO nRF52840.

## Why

Every cheap 2.42" I2C OLED module (HiLetgo, YELUFT, etc.) uses the same broken
PCB design: missing reset pull-up, questionable BS pin configuration, mystery
D1/D2 pads. Two modules tested — neither responds to I2C. Custom PCB controls
the full signal chain from FPC connector to header pin.

## Board Dimensions

- **Width**: 70mm (X)
- **Height**: 48mm (Y)
- **Thickness**: 1.6mm (standard 2-layer)
- **Mounting holes**: 4x M2, 64mm x 42mm spacing (3mm inset from edges)
- **OLED visible area**: 55mm x 29mm, centered, 7mm inset from edges

## Interface

4-pin 2.54mm header (P1): GND, VCC (3.3-5V), SCL, SDA

- **VCC input range**: 3.3V - 5.5V (XC6206 LDO regulates to 3.3V)
- **I2C address**: 0x3C (SA0 tied LOW) — change R_SA0 for 0x3D
- **I2C pull-ups**: 4.7K to VCC3.3 (on-board)

## Schematic — Signal Path

### Power

```
VCC (header) ──┬── XC6206 (U1) ──── VCC3.3 (logic, 3.3V)
               │
               └── SX1308 (U2) ──── VPP (OLED drive, ~12V)
```

### OLED Panel (24-pin FPC, J1)

```
Pin  Signal    Connection
───  ────────  ──────────────────────────────
1    NC(GND)   GND
2    VLSS      GND
3    VSS       GND
4    NC        GND
5    VDD       VCC3.3
6    BS1       VCC3.3          ← FORCES I2C MODE
7    BS2       GND             ← FORCES I2C MODE
8    CS#       GND             (always selected)
9    RES#      RESET net       (R4 pull-up + C8/D2 RC reset)
10   D/C#      GND             (SA0=0 → addr 0x3C)
11   R/W#      GND             (I2C mode: tie low)
12   E/RD#     GND             (I2C mode: tie low)
13   D0        SCL             (I2C clock)
14   D1        SDA             (I2C data)
15   D2        GND             (unused in I2C)
16   D3        GND
17   D4        GND
18   D5        GND
19   D6        GND
20   D7        GND
21   IREF      R1 (910K) → GND
22   VCOMH     C6 (100nF) → GND
23   VCC       VPP (from boost)
24   NC(GND)   GND
```

### Reset Circuit

```
VCC3.3 ── R4 (10K) ──┬── RES# (pin 9)
                      │
              C8 ─────┤
              (100nF)  │
              │        D2 (1N4148WT, cathode toward C8)
              GND      │
                       C8 node
```

Power-on sequence:
1. VCC applied → C8 discharged → RES# pulled LOW through D2/C8
2. C8 charges through R4 (τ = 10K × 100nF = 1ms)
3. RES# rises to VCC3.3 → chip exits reset
4. Power off → D2 discharges C8 rapidly → ready for next boot

### Boost Converter (SX1308)

```
VCC ── L1 (4.7uH) ── SW (U2 pin 1)
                      │
                      D1 (SS14) ── VPP
                                    │
                                    C2 (4.7uF/25V)
                                    │
                                    GND

U2 pin connections:
  1: SW    ← L1/D1 junction
  2: GND
  3: FB    ← R6/R1 divider (200K/910K → ~12V out)
  4: EN    ← R5 (10K) to VCC (always on)
  5: IN    ← VCC
  6: NC
```

### I2C

```
VCC3.3 ── R2 (4.7K) ── SCL ── P1 pin 3
VCC3.3 ── R3 (4.7K) ── SDA ── P1 pin 4
```

## PCB Layout Notes

- **2-layer board**, components on top, GND pour on bottom
- FPC connector at top edge (OLED panel folds over or extends upward)
- 4-pin header at bottom edge
- Keep boost converter (U2, L1, D1, C7) away from I2C traces
- GND pour under SSD1309 FPC area for noise shielding
- All bypass caps close to their IC pins
- Mounting holes match housing: 64mm x 42mm, M2

## Key Design Decisions

1. **BS1=VCC3.3, BS2=GND**: Forces I2C mode regardless of panel default
2. **D/C#=GND**: Sets I2C address to 0x3C (most common)
3. **CS#=GND**: Always selected (required for I2C)
4. **External boost**: SSD1309 needs external VCC unlike SSD1306
5. **Reset circuit WITH D2**: Ensures clean POR on every power cycle

## OLED Panel Sourcing

The bare 2.42" OLED panel uses a 24-pin 0.5mm FPC ribbon cable.
You can either:
- **Desolder** the panel from existing HiLetgo modules (FPC + glass)
- **Buy bare panels** from AliExpress: search "2.42 inch OLED panel 24pin"

Verify the FPC is bottom-contact (contacts face the PCB) before ordering
the connector. If top-contact, use LCSC C262292 instead.

## Manufacturing

- **Fab + assembly**: JLCPCB (jlcpcb.com)
- **Layers**: 2
- **Min trace/space**: 6mil/6mil
- **BOM**: see bom.csv (all parts from LCSC basic/preferred library)
- **Assembly**: top-side SMT only
- **Header P1**: hand-solder (through-hole)

## Design Tool

Use **EasyEDA** (easyeda.com) — free, web-based, integrates directly with
JLCPCB parts library. Import BOM part numbers, place components, route traces,
export Gerber + BOM + CPL in one click.
