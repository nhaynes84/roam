#!/usr/bin/env python3
"""Generate KiCad 9 schematic for Roam Main Board with full netlist.

All components connected via global labels per design.md.
All coordinates snapped to 2.54mm grid for proper ERC.

Usage: python3 gen_schematic.py  ->  roam_main.kicad_sch
"""

import uuid as _uuid

def uid():
    return str(_uuid.uuid4())

GRID = 2.54  # KiCad schematic grid

def snap(v):
    """Snap a value to the 2.54mm grid."""
    return round(v / GRID) * GRID

# ---------------------------------------------------------------------------
# S-expression generators
# ---------------------------------------------------------------------------

def make_pin(name, number, x, y, length, direction="left", ptype="passive"):
    angle = {"right": 0, "left": 180, "up": 90, "down": 270}[direction]
    return (f'      (pin {ptype} line (at {x:.2f} {y:.2f} {angle}) (length {length:.2f})\n'
            f'        (name "{name}" (effects (font (size 1.27 1.27))))\n'
            f'        (number "{number}" (effects (font (size 1.27 1.27)))))')

def make_rect_sym(lib_id, pins_left, pins_right, width=10.16):
    """Rectangular symbol. Pin tips are at ±(width/2 + pin_len) from center.
    Width and pin_len chosen so tips are multiples of 2.54mm from center."""
    n = max(len(pins_left), len(pins_right), 1)
    h = n * GRID + GRID  # height = (n+1) * 2.54
    top = h / 2
    w2 = width / 2
    plen = GRID  # 2.54mm pin length → tips at w2 + 2.54 from center
    lines = [f'    (symbol "{lib_id}_0_1"',
             f'      (rectangle (start {-w2:.2f} {top:.2f}) (end {w2:.2f} {-top:.2f})',
             f'        (stroke (width 0.254) (type default))',
             f'        (fill (type background)))']
    for i, (name, num, pt) in enumerate(pins_left):
        y = top - GRID * (i + 1)
        lines.append(make_pin(name, num, -w2 - plen, y, plen, "right", pt))
    for i, (name, num, pt) in enumerate(pins_right):
        y = top - GRID * (i + 1)
        lines.append(make_pin(name, num, w2 + plen, y, plen, "left", pt))
    lines.append('    )')
    return "\n".join(lines)

def make_two_pin(lib_id, p1="1", p2="2", t1="passive", t2="passive"):
    """2-pin horizontal symbol. Body 2.54 wide, pin_len 2.54 → tips at ±5.08."""
    bw = 1.27  # half body width
    plen = GRID + bw  # 3.81mm so tip is at 1.27+3.81 = 5.08 = 2*GRID
    tip = bw + plen  # 5.08
    return (f'    (symbol "{lib_id}_0_1"\n'
            f'      (rectangle (start {-bw:.2f} {bw:.2f}) (end {bw:.2f} {-bw:.2f})\n'
            f'        (stroke (width 0.254) (type default))\n'
            f'        (fill (type background)))\n'
            f'      (pin {t1} line (at {-tip:.2f} 0 0) (length {plen:.2f})\n'
            f'        (name "{p1}" (effects (font (size 1.27 1.27))))\n'
            f'        (number "1" (effects (font (size 1.27 1.27)))))\n'
            f'      (pin {t2} line (at {tip:.2f} 0 180) (length {plen:.2f})\n'
            f'        (name "{p2}" (effects (font (size 1.27 1.27))))\n'
            f'        (number "2" (effects (font (size 1.27 1.27)))))\n'
            f'    )')

def sym_wrap(lib_id, prefix, body):
    return (f'  (symbol "{lib_id}" (in_bom yes) (on_board yes)\n'
            f'    (property "Reference" "{prefix}" (at 0 {GRID:.2f} 0)\n'
            f'      (effects (font (size 1.27 1.27))))\n'
            f'    (property "Value" "{lib_id}" (at 0 {-GRID:.2f} 0)\n'
            f'      (effects (font (size 1.27 1.27))))\n'
            f'    (property "Footprint" "" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'{body}\n'
            f'  )')

_instances = []  # collects (uuid, ref, unit, value, fp) for symbol_instances

def inst(lib_id, ref, value, x, y, rot=0, fp=""):
    u = uid()
    _instances.append((u, ref, 1, value, fp))
    return (f'  (symbol (lib_id "{lib_id}") (at {x:.2f} {y:.2f} {rot}) (unit 1)\n'
            f'    (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid "{u}")\n'
            f'    (property "Reference" "{ref}" (at {x:.2f} {y - GRID:.2f} 0)\n'
            f'      (effects (font (size 1.27 1.27))))\n'
            f'    (property "Value" "{value}" (at {x:.2f} {y + GRID:.2f} 0)\n'
            f'      (effects (font (size 1.27 1.27))))\n'
            f'    (property "Footprint" "{fp}" (at {x:.2f} {y:.2f} 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'  )')

def glabel(name, x, y, rot=0):
    """Global label. rot=0 for right-side pins, rot=180 for left-side pins."""
    just = "left" if rot == 0 else "right"
    return (f'  (global_label "{name}" (shape passive) (at {x:.2f} {y:.2f} {rot})\n'
            f'    (effects (font (size 1.27 1.27)) (justify {just}))\n'
            f'    (uuid "{uid()}")\n'
            f'    (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'  )')

# ---------------------------------------------------------------------------
# Pin position calculator — all positions on 2.54mm grid
# ---------------------------------------------------------------------------

def rect_pins(cx, cy, width, left_defs, right_defs):
    """Pin endpoints for a rectangular symbol placed at (cx, cy).
    Returns dict: pin_number_str -> (x, y, side) where side is 'L' or 'R'."""
    w2 = width / 2
    plen = GRID
    n = max(len(left_defs), len(right_defs), 1)
    h = n * GRID + GRID
    top = h / 2
    pins = {}
    for i, (_, num, _) in enumerate(left_defs):
        sy = top - GRID * (i + 1)
        pins[num] = (cx - w2 - plen, cy - sy, 'L')
    for i, (_, num, _) in enumerate(right_defs):
        sy = top - GRID * (i + 1)
        pins[num] = (cx + w2 + plen, cy - sy, 'R')
    return pins

def two_pins(cx, cy):
    tip = 5.08  # 1.27 + 3.81
    return {"1": (cx - tip, cy, 'L'), "2": (cx + tip, cy, 'R')}

def conn_pins(cx, cy, n_pins):
    """Connector: all pins on left side."""
    defs = [(str(i), str(i), "passive") for i in range(1, n_pins + 1)]
    return rect_pins(cx, cy, 7.62, defs, [])

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build():
    syms = []
    parts = []
    labels = []

    # === Symbol definitions ===

    esp_L = [("GPIO0","1","bidirectional"),("GPIO1","2","bidirectional"),
             ("GPIO2","3","bidirectional"),("GPIO3","4","bidirectional"),
             ("GPIO4","5","bidirectional"),("GPIO5","6","bidirectional"),
             ("GPIO6","7","bidirectional"),("GPIO7","8","bidirectional"),
             ("GPIO8","9","bidirectional"),("GPIO9","10","bidirectional")]
    esp_R = [("3V3","11","power_in"),("GND","12","power_in"),("EN","13","input"),
             ("GPIO12","14","bidirectional"),("GPIO13","15","bidirectional"),
             ("GPIO14","16","bidirectional"),("GPIO15","17","bidirectional"),
             ("GPIO16","18","bidirectional"),("GPIO17","19","bidirectional")]
    syms.append(sym_wrap("roam_ESP32C6","U", make_rect_sym("roam_ESP32C6", esp_L, esp_R, 15.24)))

    u2L = [("VDD","4","power_in"),("VBAT","3","power_out"),("VSS","2","power_in")]
    u2R = [("STAT","1","open_collector"),("PROG","5","passive")]
    syms.append(sym_wrap("roam_MCP73831T","U", make_rect_sym("roam_MCP73831T", u2L, u2R)))

    u3L = [("VIN","1","power_in"),("GND","2","power_in"),("EN","3","input")]
    u3R = [("VOUT","5","power_out"),("BP","4","passive")]
    syms.append(sym_wrap("roam_AP2112K","U", make_rect_sym("roam_AP2112K", u3L, u3R)))

    u4L = [("IO1_IN","1","passive"),("GND","2","power_in"),("IO2_IN","3","passive")]
    u4R = [("IO2_OUT","4","passive"),("VBUS","5","power_in"),("IO1_OUT","6","passive")]
    syms.append(sym_wrap("roam_USBLC6","U", make_rect_sym("roam_USBLC6", u4L, u4R)))

    u5L = [("SDO_SA0","1","input"),("SDX","2","passive"),("SCX","3","passive"),
           ("INT1","4","output"),("VDDIO","5","power_in"),("GND1","6","power_in"),
           ("GND2","7","power_in")]
    u5R = [("GND3","8","power_in"),("VDD","9","power_in"),("NC","10","passive"),
           ("CS","11","input"),("SCL","12","input"),("SDA","13","bidirectional"),
           ("INT2","14","output")]
    syms.append(sym_wrap("roam_LSM6DS3","U", make_rect_sym("roam_LSM6DS3", u5L, u5R, 12.70)))

    syms.append(sym_wrap("roam_R","R", make_two_pin("roam_R")))
    syms.append(sym_wrap("roam_C","C", make_two_pin("roam_C")))

    q1L = [("G","1","input")]
    q1R = [("D","2","passive"),("S","3","passive")]
    syms.append(sym_wrap("roam_NMOS","Q", make_rect_sym("roam_NMOS", q1L, q1R, 7.62)))

    syms.append(sym_wrap("roam_D","D", make_two_pin("roam_D","A","K")))

    skL = [("DIN","1","input"),("GND","2","power_in")]
    skR = [("VDD","3","power_in"),("DOUT","4","output")]
    syms.append(sym_wrap("roam_SK6812","D", make_rect_sym("roam_SK6812", skL, skR, 7.62)))

    for n in [2, 3, 4, 5, 6]:
        cpins = [(str(i), str(i), "passive") for i in range(1, n+1)]
        syms.append(sym_wrap(f"roam_Conn{n}","J", make_rect_sym(f"roam_Conn{n}", cpins, [], 7.62)))

    syms.append(sym_wrap("roam_SW","SW", make_two_pin("roam_SW")))

    # =================================================================
    # Place components — all positions on 2.54mm grid
    # =================================================================

    G = GRID  # shorthand

    # Footprint assignments (KiCad 9 standard libraries)
    FP_R = 'Resistor_SMD:R_0402_1005Metric'
    FP_C4 = 'Capacitor_SMD:C_0402_1005Metric'
    FP_C8 = 'Capacitor_SMD:C_0805_2012Metric'
    FP_SW = 'Button_Switch_SMD:SW_Tactile_SPST_NO_Straight_CK_PTS636Sx25SMTRLFS'
    FP_SH = {
        2: 'Connector_JST:JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal',
        3: 'Connector_JST:JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal',
        4: 'Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal',
        5: 'Connector_JST:JST_SH_SM05B-SRSS-TB_1x05-1MP_P1.00mm_Horizontal',
    }

    def P(lib, ref, val, gx, gy, rot=0, fp=""):
        """Place component at grid position (gx*2.54, gy*2.54)."""
        parts.append(inst(lib, ref, val, gx * G, gy * G, rot, fp))

    # --- Charger (top-left) ---
    P("roam_MCP73831T","U2","MCP73831T",  22, 18, fp='Package_TO_SOT_SMD:SOT-23-5')
    u2p = rect_pins(22*G, 18*G, 10.16, u2L, u2R)

    P("roam_C","C9","10uF",    10, 14, fp=FP_C8); c9p  = two_pins(10*G, 14*G)
    P("roam_C","C1","4.7uF",   15, 14, fp=FP_C8); c1p  = two_pins(15*G, 14*G)
    P("roam_C","C2","4.7uF",   30, 14, fp=FP_C8); c2p  = two_pins(30*G, 14*G)
    P("roam_R","R1","2K",       30, 20, fp=FP_R);  r1p  = two_pins(30*G, 20*G)
    P("roam_R","R2","1K",       35, 15, fp=FP_R);  r2p  = two_pins(35*G, 15*G)
    P("roam_D","D2","LED",      35, 18, fp='LED_SMD:LED_0603_1608Metric'); d2p = two_pins(35*G, 18*G)

    # --- LDO ---
    P("roam_AP2112K","U3","AP2112K-3.3",  22, 32, fp='Package_TO_SOT_SMD:SOT-23-5')
    u3p = rect_pins(22*G, 32*G, 10.16, u3L, u3R)

    P("roam_C","C3","1uF",  15, 30, fp=FP_C4); c3p = two_pins(15*G, 30*G)
    P("roam_C","C4","1uF",  30, 30, fp=FP_C4); c4p = two_pins(30*G, 30*G)

    # --- USB (left-center) ---
    P("roam_Conn6","J1","USB-C", 10, 52, fp='Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12')
    j1p = conn_pins(10*G, 52*G, 6)

    P("roam_USBLC6","U4","USBLC6-2SC6", 24, 54, fp='Package_TO_SOT_SMD:SOT-23-6')
    u4p = rect_pins(24*G, 54*G, 10.16, u4L, u4R)

    P("roam_R","R8","5.1K",  15, 60, fp=FP_R); r8p = two_pins(15*G, 60*G)
    P("roam_R","R9","5.1K",  15, 63, fp=FP_R); r9p = two_pins(15*G, 63*G)

    # --- ESP32-C6 (center) ---
    P("roam_ESP32C6","U1","ESP32-C6-MINI-1-N4",  64, 24, fp='RF_Module:ESP32-C6-MINI-1')
    u1p = rect_pins(64*G, 24*G, 15.24, esp_L, esp_R)

    P("roam_C","C5","100nF",    74, 16, fp=FP_C4); c5p  = two_pins(74*G, 16*G)
    P("roam_C","C6","10uF",     80, 16, fp=FP_C8); c6p  = two_pins(80*G, 16*G)
    P("roam_R","R10","10K",     76, 20, fp=FP_R);  r10p = two_pins(76*G, 20*G)
    P("roam_C","C10","1uF",     80, 20, fp=FP_C4); c10p = two_pins(80*G, 20*G)
    P("roam_SW","SW1","RESET",  84, 22, fp=FP_SW); sw1p = two_pins(84*G, 22*G)
    P("roam_R","R11","10K",     54, 28, fp=FP_R);  r11p = two_pins(54*G, 28*G)
    P("roam_SW","SW2","BOOT",   54, 32, fp=FP_SW); sw2p = two_pins(54*G, 32*G)

    # --- IMU (center-bottom) ---
    P("roam_LSM6DS3","U5","LSM6DS3TR-C",  64, 48, fp='Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y')
    u5p = rect_pins(64*G, 48*G, 12.70, u5L, u5R)

    P("roam_C","C7","100nF",  74, 44, fp=FP_C4); c7p = two_pins(74*G, 44*G)
    P("roam_C","C8","100nF",  74, 48, fp=FP_C4); c8p = two_pins(74*G, 48*G)
    P("roam_R","R4","4.7K",   54, 44, fp=FP_R);  r4p = two_pins(54*G, 44*G)
    P("roam_R","R5","4.7K",   54, 48, fp=FP_R);  r5p = two_pins(54*G, 48*G)

    # --- Motor (right) ---
    P("roam_NMOS","Q1","2N7002",   92, 20, fp='Package_TO_SOT_SMD:SOT-23')
    q1p = rect_pins(92*G, 20*G, 7.62, q1L, q1R)

    P("roam_D","D1","SS14",        98, 19, fp='Diode_SMD:D_SMA');  d1p = two_pins(98*G, 19*G)
    P("roam_Conn2","J4","Motor",  106, 20, fp=FP_SH[2]); j4p = conn_pins(106*G, 20*G, 2)

    # --- LED (right) ---
    P("roam_SK6812","D3","SK6812-MINI-E",  92, 33, fp='LED_SMD:LED_SK6812MINI_PLCC4_3.5x3.5mm_P1.75mm')
    d3p = rect_pins(92*G, 33*G, 7.62, skL, skR)

    P("roam_C","C11","100nF",  100, 32, fp=FP_C4); c11p = two_pins(100*G, 32*G)

    # --- Battery divider ---
    P("roam_R","R6","1M",  92, 40, fp=FP_R); r6p = two_pins(92*G, 40*G)
    P("roam_R","R7","1M",  100, 40, fp=FP_R); r7p = two_pins(100*G, 40*G)

    # --- External connectors (bottom row) ---
    P("roam_Conn5","J2","Buttons",      16, 76, fp=FP_SH[5]); j2p = conn_pins(16*G, 76*G, 5)
    P("roam_Conn3","J3","Scroll",       32, 76, fp=FP_SH[3]); j3p = conn_pins(32*G, 76*G, 3)
    P("roam_Conn4","J6","Display",      48, 76, fp=FP_SH[4]); j6p = conn_pins(48*G, 76*G, 4)
    P("roam_Conn3","J7","PwrSwitch",    64, 76, fp=FP_SH[3]); j7p = conn_pins(64*G, 76*G, 3)
    P("roam_Conn2","J8","Battery",      80, 76, fp='Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical'); j8p = conn_pins(80*G, 76*G, 2)
    P("roam_Conn4","J9","UART",         96, 76, fp='Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical'); j9p = conn_pins(96*G, 76*G, 4)

    # =================================================================
    # Net labels — global labels at every pin endpoint
    # =================================================================

    def net(name, pin_list):
        for x, y, side in pin_list:
            rot = 180 if side == 'L' else 0
            labels.append(glabel(name, x, y, rot))

    # --- 3V3_SYS ---
    net("3V3_SYS", [
        u1p["11"], u3p["5"],            # ESP32 3V3, LDO VOUT
        u5p["9"], u5p["5"], u5p["11"],  # IMU VDD, VDDIO, CS=VDD
        r4p["1"], r5p["1"],             # I2C pull-ups
        r10p["1"],                      # EN pull-up
        r11p["1"],                      # GPIO8 strapping pull-up
        d3p["3"],                       # SK6812 VDD
        d1p["2"],                       # SS14 cathode (flyback)
        c4p["1"], c5p["1"], c6p["1"],   # Bypass caps
        c7p["1"], c8p["1"], c11p["1"],
        j4p["1"],                       # Motor+
        j6p["1"],                       # Display VCC
        j9p["1"],                       # UART 3V3
    ])

    # --- GND ---
    net("GND", [
        u1p["12"], u2p["2"], u3p["2"], u4p["2"],
        u5p["6"], u5p["7"], u5p["8"],
        u5p["1"], u5p["10"],
        r1p["2"], r7p["2"], r8p["2"], r9p["2"],
        c1p["2"], c2p["2"], c3p["2"], c4p["2"],
        c5p["2"], c6p["2"], c7p["2"], c8p["2"],
        c9p["2"], c10p["2"], c11p["2"],
        q1p["3"],
        d3p["2"],
        j1p["4"], j2p["5"], j3p["3"],
        j6p["2"], j8p["2"], j9p["4"],
        sw1p["2"], sw2p["2"],
    ])

    # --- VBUS ---
    net("VBUS", [
        j1p["1"], u2p["4"], u4p["5"],
        c1p["1"], c9p["1"],
        r2p["1"],
    ])

    # --- VBAT ---
    net("VBAT", [u2p["3"], c2p["1"], j7p["1"], j8p["1"]])

    # --- VBAT_SW ---
    net("VBAT_SW", [j7p["2"], u3p["1"], u3p["3"], c3p["1"], r6p["1"]])

    # --- USB data ---
    net("USB_DP",   [j1p["2"], u4p["3"]])
    net("USB_DM",   [j1p["3"], u4p["1"]])
    net("USB_DP_P", [u4p["4"], u1p["15"]])
    net("USB_DM_P", [u4p["6"], u1p["14"]])
    net("CC1",      [j1p["5"], r8p["1"]])
    net("CC2",      [j1p["6"], r9p["1"]])

    # --- I2C bus ---
    net("SDA", [u1p["7"],  r5p["2"], u5p["13"], j6p["3"]])
    net("SCL", [u1p["8"],  r4p["2"], u5p["12"], j6p["4"]])

    # --- Buttons ---
    net("BTN_IDX", [u1p["1"],  j2p["1"]])
    net("BTN_MID", [u1p["2"],  j2p["2"]])
    net("BTN_RNG", [u1p["3"],  j2p["3"]])
    net("BTN_PNK", [u1p["5"],  j2p["4"]])
    net("SCR_FWD", [u1p["6"],  j3p["1"]])
    net("SCR_BCK", [u1p["16"], j3p["2"]])

    # --- Analog ---
    net("BAT_ADC", [u1p["4"], r6p["2"], r7p["1"]])

    # --- LED ---
    net("LED_DATA", [u1p["9"], r11p["2"], d3p["1"]])

    # --- Motor ---
    net("MTR_GATE", [u1p["17"], q1p["1"]])
    net("MTR_SW",   [q1p["2"],  d1p["1"], j4p["2"]])

    # --- EN / BOOT ---
    net("EN",   [u1p["13"], r10p["2"], c10p["1"], sw1p["1"]])
    net("BOOT", [u1p["10"], sw2p["1"]])

    # --- UART ---
    net("UART_TX", [u1p["18"], j9p["2"]])
    net("UART_RX", [u1p["19"], j9p["3"]])

    # --- Charge indicator ---
    net("CHG_STAT", [u2p["1"], d2p["2"]])
    net("CHG_LED",  [d2p["1"], r2p["2"]])
    net("PROG",     [u2p["5"], r1p["1"]])

    # =================================================================
    # Assemble
    # =================================================================

    header = f"""(kicad_sch (version 20230121) (generator "roam_gen")
  (uuid "{uid()}")
  (paper "A3")

  (title_block
    (title "Roam Main Board")
    (date "2026-03-13")
    (rev "2.0")
    (comment 1 "ESP32-C6-MINI-1-N4 / BLE 5.0 + WiFi 6")
    (comment 2 "Full netlist — generated from design spec")
  )

  (lib_symbols
{chr(10).join(syms)}
  )
"""

    # Build symbol_instances section
    si_lines = ['  (symbol_instances']
    for u, ref, unit, val, fp in _instances:
        si_lines.append(f'    (path "/{u}" (reference "{ref}") (unit {unit}) (value "{val}") (footprint "{fp}"))')
    si_lines.append('  )')

    footer = f"""
{chr(10).join(si_lines)}

  (sheet_instances
    (path "/" (page "1"))
  )
)
"""

    _instances.clear()  # reset for repeated calls
    out = [header]
    out.extend(parts)
    out.extend(labels)
    out.append(footer)
    return "\n".join(out)


if __name__ == "__main__":
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roam_main.kicad_sch")
    with open(path, "w") as f:
        f.write(build())
    content = open(path).read()
    n_comp = content.count('(symbol (lib_id')
    n_label = content.count('(global_label ')
    print(f"Wrote {path}")
    print(f"  {n_comp} components, {n_label} global labels")
    print(f"  {len(content.splitlines())} lines")
