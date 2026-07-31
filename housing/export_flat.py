#!/usr/bin/env python3
"""Export flat wrist-mounted Roam housing — mini, max, and max-mini variants.

Usage:
    source housing/.venv/bin/activate
    python housing/export_flat.py [mini|max|max_mini|mini_lid|max_lid|max_mini_lid]

Orientation: X=forearm (X-=wrist), Y=across arm (Y+=outer), Z=up from skin
Components:
    mini          — small screen (1.3" SH1106) + small battery (502535)
    max           — big screen (2.42" SSD1309) + big battery
    max_mini      — big case + small screen (1.3" SH1106)
    mini_lid      — matching lid for mini case
    max_lid       — matching lid for max case
    max_mini_lid  — matching lid for max-mini case

Internal layout (side view, Z):
    ┌──── top wall (2mm) ─────── screen window + button holes ──┐
    │  screen PCB (~1.5mm)                                      │
    │  air / wires (~3mm)                                       │
    │  battery (6mm) + XIAO (3mm) side by side                  │
    └──── base (lid, 2mm) ──────────────────────────────────────┘

Button layout (top view):
    [B1]─[B2]─[B3]─[B4]     10mm c-c main row along X, on top face

    Scroll buttons on right (X+/elbow) side wall:
        [S1]  Y=+5, Z=cz/2     (outer)
        [S2]  Y=-5, Z=cz/2     (inner)
"""

import sys, math
from pathlib import Path
from build123d import *

STEP_DIR = Path(__file__).parent / "step"

# ── Ports & switch (on wrist edge, X-) ──
usbc_w = 9.0           # USB-C opening width
usbc_h = 3.5           # USB-C opening height
usbc_z = 6.0           # center Z (XIAO on floor + standoff)
switch_w = 4.0         # slide switch slot width
switch_h = 2.0         # slide switch slot height
switch_y = 12.0        # Y offset from center on wrist edge

# ── Button wells through top wall ──
main_well_dia = 7.0    # main button hole (6mm switch + 1mm clearance)
scroll_well_dia = 5.5  # scroll button hole (smaller switches)
btn_cc = 10.0          # center-to-center, main row
stem_gap = 0.8         # per-side clearance, stem to hole wall

# ── Fasteners ──
m2_thru_dia = 2.2      # M2 through-hole
m2_head_dia = 3.8      # button head diameter
m2_head_depth = 1.0    # countersink depth
m2_insert_dia = 3.2    # heat-set insert hole
m2_insert_depth = 4.0  # insert depth

# ── Screw bosses (inside case, hanging from top wall ceiling) ──
boss_od = 6.0           # boss outer diameter
boss_h = 6.0            # boss height

# ── OLED ceiling posts (hanging from top wall, board screws up into them) ──
oled_post_od = 5.0      # post outer diameter
oled_post_h = 3.0       # post height (sets board distance from ceiling)
oled_pilot_dia = 1.6    # M2 pilot hole (screw taps into plastic)
oled_pilot_depth = 2.5  # pilot hole depth

# ── Lid ──
lid_thick = 2.0
lip_h = 1.5
lip_gap = 0.15         # clearance per side for press fit

# ── Attachment ring (squared loop on top wall Y+ edge) ──
ring_w = 12.0           # outer width (Y direction, across arm)
ring_h = 10.0           # outer height above top wall (Z)
ring_t = 4.0            # depth (X direction, along arm)
ring_wall = 2.5         # frame wall thickness (chunky for strength)

# ── Embossed text ──
emboss_depth = 1.0      # text recess depth into top wall

# ── Velcro & vents ──
velcro_recess_depth = 1.0
vent_w = 1.0
vent_l = 8.0
vent_spacing = 3.0
n_vents = 4

# ── Variant configs ──
# Layout rule: board_bottom > button_top + 2mm clearance
# Boss rule: boss inner X edge > board X edge + 2mm
#
# Mini: 1.3" SH1106 (board 33×33, vis 30×15) + 502535 battery (25×39×6)
# Internal: 52×46×12, external: 56×50×16
MINI = dict(
    case=(56, 50, 16),
    wall=2.0,
    corner_r=3.0,
    screen_vis=(30, 15),     # visible window dimensions
    screen_r=2.0,            # window corner radius
    screen_cy=6,             # window center Y (moved down to clear board from buttons)
    btn_row_y=-18,           # main button row center Y (moved for board clearance)
    # OLED mounting (SH1106 board: 33×33, holes at 27×27 c-c, +2mm X for fit)
    oled_holes_cc=(31, 27),
    oled_board_cy_off=-1.0,  # board center Y offset from screen vis center
    screw_inset=5,           # case screw distance from edge
    velcro=(40, 30),         # velcro patch X, Y
)

# Max: 2.42" SSD1309 (board 70×48, vis 55×29) + large battery (34×55×6)
# Internal: 88×62×12, external: 92×66×16
MAX = dict(
    case=(92, 66, 16),
    wall=2.0,
    corner_r=4.0,
    screen_vis=(55, 29),
    screen_r=3.0,
    screen_cy=8,             # window center Y (moved down to clear board from buttons)
    btn_row_y=-25,           # main button row center Y (moved for board clearance)
    # OLED mounting (SSD1309 board: 70×48, holes at 64×42 c-c, +2mm X for fit)
    oled_holes_cc=(66, 42),
    oled_board_cy_off=-2.5,
    screw_inset=6,           # case screw distance from edge
    velcro=(60, 40),         # velcro patch X, Y
)

# Max-Mini: large case body + small screen (1.3" SH1106)
# Same external as Max, small screen window and mount points
MAX_MINI = dict(
    case=(92, 66, 16),
    wall=2.0,
    corner_r=4.0,
    screen_vis=(30, 15),     # small screen visible area
    screen_r=2.0,            # small screen corner radius
    screen_cy=8,             # same Y position as Max
    btn_row_y=-25,           # same button layout as Max
    # OLED mounting (SH1106 board: 33×33, holes at 27×27 c-c, +2mm X for fit)
    oled_holes_cc=(31, 27),
    oled_board_cy_off=-1.0,  # small board offset
    screw_inset=6,           # same as Max
    velcro=(60, 40),         # same as Max
)

VARIANTS = {'mini': MINI, 'max': MAX, 'max_mini': MAX_MINI}


def _btn_positions(v):
    """Compute button positions.

    Returns (main_positions, scroll_positions).
    Main: 4 buttons on top face, row along X at 10mm c-c.
    Scroll: 2 buttons on right (X+) side wall, 10mm c-c along Y.
    """
    ry = v['btn_row_y']
    cz = v['case'][2]
    main = [
        (-15, ry),   # B1 — wrist end (pinky)
        ( -5, ry),   # B2
        (  5, ry),   # B3
        ( 15, ry),   # B4 — elbow end (index)
    ]
    # Scroll buttons on X+ side wall: (y, z) positions
    scroll = [
        ( 5, cz / 2),   # S1 — outer (Y+)
        (-5, cz / 2),   # S2 — inner (Y-)
    ]
    return main, scroll


def _screw_positions(v):
    """4 corner screw positions (x, y) for case assembly."""
    cx, cy, _ = v['case']
    si = v['screw_inset']
    return [
        ( cx / 2 - si,  cy / 2 - si),
        (-cx / 2 + si,  cy / 2 - si),
        ( cx / 2 - si, -cy / 2 + si),
        (-cx / 2 + si, -cy / 2 + si),
    ]


def _oled_hole_positions(v):
    """OLED mounting hole positions, skipping any too close to lid edge."""
    hx, hy = v['oled_holes_cc']
    cx, cy, _ = v['case']
    board_cy = v['screen_cy'] + v['oled_board_cy_off']
    min_edge = 2.0  # minimum material around hole edge

    positions = []
    for dx in [-1, 1]:
        for dy in [-1, 1]:
            ox = dx * hx / 2
            oy = board_cy + dy * hy / 2
            if (abs(ox) + m2_thru_dia / 2 + min_edge > cx / 2 or
                    abs(oy) + m2_thru_dia / 2 + min_edge > cy / 2):
                continue
            positions.append((ox, oy))
    return positions


def make_case(v):
    """Build case shell with screen window, button holes, port cutouts, and screw bosses."""
    cx, cy, cz = v['case']
    w = v['wall']
    cr = v['corner_r']

    # ── 1. Rounded rectangle box → shell open bottom ──
    with BuildPart() as bp:
        with BuildSketch():
            RectangleRounded(cx, cy, cr)
        extrude(amount=cz)
        bottom = bp.faces().sort_by(Axis.Z)[0]
        offset(amount=-w, openings=[bottom])
    case = bp.part

    # ── 2. Screen window through top wall (rounded corners) ──
    svw, svh = v['screen_vis']
    sr = v['screen_r']
    scy = v['screen_cy']
    screen_cut = Pos(0, scy, cz - w - 0.5) * extrude(
        RectangleRounded(svw, svh, sr), amount=w + 1)
    case -= screen_cut

    # ── 3. Main button holes through top wall ──
    main_btns, scroll_btns = _btn_positions(v)
    for bx, by in main_btns:
        case -= Pos(bx, by, cz - w - 0.5) * Cylinder(
            radius=main_well_dia / 2, height=w + 1,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

    # ── 4. Scroll button holes through right (X+) side wall ──
    for sy, sz in scroll_btns:
        case -= (Pos(cx / 2 + 0.5, sy, sz) *
                 Rot(0, -90, 0) *
                 Cylinder(radius=scroll_well_dia / 2, height=w + 1,
                          align=(Align.CENTER, Align.CENTER, Align.MIN)))

    # ── 5. USB-C slot on wrist (X-) wall ──
    case -= Pos(-cx / 2, 0, usbc_z) * Box(w + 2, usbc_w, usbc_h)

    # ── 6. Switch slot on wrist (X-) wall ──
    case -= Pos(-cx / 2, switch_y, usbc_z) * Box(w + 2, switch_w, switch_h)

    # ── 7. Screw bosses (hang from ceiling at corners, for heat-set inserts) ──
    for sx, sy in _screw_positions(v):
        # Boss: cylinder from ceiling downward, overlaps 0.1mm into top wall
        boss = Pos(sx, sy, cz - w + 0.1) * Cylinder(
            radius=boss_od / 2, height=boss_h + 0.1,
            align=(Align.CENTER, Align.CENTER, Align.MAX))
        case = case.fuse(boss)
        # Heat-set insert hole from below
        case -= Pos(sx, sy, cz - w - boss_h - 0.1) * Cylinder(
            radius=m2_insert_dia / 2, height=m2_insert_depth + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

    # ── 8. OLED ceiling posts (hang from top wall, board screws up into them) ──
    for ox, oy in _oled_hole_positions(v):
        post = Pos(ox, oy, cz - w + 0.1) * Cylinder(
            radius=oled_post_od / 2, height=oled_post_h + 0.1,
            align=(Align.CENTER, Align.CENTER, Align.MAX))
        case = case.fuse(post)
        # Pilot hole from below (M2 self-taps into plastic)
        case -= Pos(ox, oy, cz - w - oled_post_h - 0.1) * Cylinder(
            radius=oled_pilot_dia / 2, height=oled_pilot_depth + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

    # ── 9. Attachment ring (flat loop extending Y+ from top wall edge) ──
    # Outer frame: extends from Y+ case edge outward, sits on top face
    outer_y0 = cy / 2 - 0.5               # overlap into case wall
    outer_y1 = cy / 2 + ring_h            # extends outward
    outer_cy = (outer_y0 + outer_y1) / 2
    outer_dy = outer_y1 - outer_y0
    outer = Pos(0, outer_cy, cz - 0.5) * Box(
        ring_w, outer_dy, ring_t + 0.5,
        align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Inner cutout: closed loop hole through Z (chain threads through)
    inner_y0 = cy / 2 + ring_wall         # wall on case side
    inner_y1 = cy / 2 + ring_h - ring_wall  # wall on far end
    inner_cy = (inner_y0 + inner_y1) / 2
    inner_dy = inner_y1 - inner_y0
    inner = Pos(0, inner_cy, cz - 1) * Box(
        ring_w - 2 * ring_wall, inner_dy, ring_t + 2,
        align=(Align.CENTER, Align.CENTER, Align.MIN))
    case = case.fuse(outer - inner)

    # ── 10. Embossed "ROAM" on top face, above screen ──
    svw, svh = v['screen_vis']
    text_y = scy + svh / 2 + 4  # 4mm above screen window top edge
    text_shapes = Pos(0, text_y, cz + 0.1) * Text(
        "ROAM", font_size=6, font="Arial",
        align=(Align.CENTER, Align.CENTER, Align.MIN))
    case -= extrude(text_shapes, amount=-(emboss_depth + 0.1))

    # ── 10. Print-in-place spring buttons ──
    buttons = []

    # Main buttons through top wall (axis Z, cap protrudes above Z=cz)
    for bx, by in main_btns:
        btn = _flat_spring_button(main_well_dia, stem_gap, w)
        # Rot(180,0,0) flips Z so button Z+ points into case (-Z model)
        buttons.append(Pos(bx, by, cz) * Rot(180, 0, 0) * btn)

    # Scroll buttons through X+ side wall (axis X, cap protrudes past X=cx/2)
    for sy, sz in scroll_btns:
        btn = _flat_spring_button(scroll_well_dia, stem_gap, w)
        # Rot(0,-90,0) maps button Z axis to -X (through wall into case)
        buttons.append(Pos(cx / 2, sy, sz) * Rot(0, -90, 0) * btn)

    case_solid = case.solids().sort_by(SortBy.VOLUME)[-1]
    return Compound(children=[case_solid] + buttons)


def make_lid(v):
    """Bottom lid with registration lip, screw holes, vents, velcro."""
    cx, cy, _ = v['case']
    w = v['wall']
    cr = v['corner_r']
    total_h = lid_thick + lip_h  # full lid height for through-holes

    # ── Outer plate ──
    plate = extrude(RectangleRounded(cx, cy, cr), amount=lid_thick)

    # ── Registration lip ──
    lip_x = cx - w * 2 - lip_gap * 2
    lip_y = cy - w * 2 - lip_gap * 2
    lip_r = max(cr - w / 2, 1)
    lip_sk = Pos(0, 0, lid_thick) * RectangleRounded(lip_x, lip_y, lip_r)
    lip = extrude(lip_sk, amount=lip_h)
    plate = plate.fuse(lip).solid()

    # ── Case screw holes (countersunk from bottom, into ceiling bosses) ──
    for sx, sy in _screw_positions(v):
        plate -= Pos(sx, sy, -0.1) * Cylinder(
            radius=m2_thru_dia / 2, height=total_h + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        plate -= Pos(sx, sy, -0.1) * Cylinder(
            radius=m2_head_dia / 2, height=m2_head_depth + 0.1,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

    # ── Velcro recess (bottom face, centered) ──
    vx, vy = v['velcro']
    plate -= extrude(
        RectangleRounded(vx, vy, 2), amount=velcro_recess_depth + 0.1)

    # ── Vent slots (through lid, two rows at ±cy/5) ──
    for i in range(n_vents):
        slot_x = -(n_vents - 1) * (vent_l + vent_spacing) / 2 + \
                 i * (vent_l + vent_spacing)
        for sy_sign in [1, -1]:
            slot_y = sy_sign * (cy / 5)
            plate -= Pos(slot_x, slot_y, -0.1) * Box(
                vent_l, vent_w, total_h + 0.2)

    return plate


def _flat_spring_button(hole_dia, stem_gap, wt):
    """Print-in-place spring button for straight (non-tapered) wall hole.

    Same mechanism as dome spring button, adapted for constant-diameter bore.
    Oriented along Z axis (caller rotates to match wall orientation):
        Z < 0:      cap (wider than hole — outer retention)
        Z = 0..wt:  stem (through hole, stem_gap clearance per side)
        Z > wt:     hub + 4 cross bridges + C-ring (spring + inner retention)

    Cross-section:
        Z<0:  [    cap    ]     ← wider than hole, retains from outside
        Z=0:  ----wall----
        Z>0:  |   stem    |    ← fits through hole with clearance
              ----wall----
              [hub]+bridges    ← spring mechanism
              [  C-ring   ]    ← wider than hole, retains from inside
    """
    pip_gap = 0.8               # air gap between button parts and wall faces
    cap_protrude = 2.0          # thicker cap for better feel
    cap_overhang = 1.0          # cap extends past hole edge per side
    cap_dia = hole_dia + 2 * cap_overhang
    cap_fillet_r = min(cap_protrude * 0.6, cap_dia / 6)  # dome fillet
    stem_dia = hole_dia - 2 * stem_gap
    plate_thick = 1.5

    # Spring ring (C-shaped, anchored against inner wall)
    ring_od = hole_dia + 4
    ring_width = 1.5
    ring_id = ring_od - 2 * ring_width
    ring_gap_deg = 30           # opening angle in C-ring

    hub_dia = max(stem_dia * 0.6, 3.0)
    bridge_width = 1.0

    # Z layout: cap and spring offset from wall faces by pip_gap
    #   cap:    Z = -(cap_protrude + pip_gap) .. -pip_gap
    #   stem:   Z = 0 .. wt  (inside hole, radial gap only)
    #   spring: Z = wt + pip_gap .. wt + pip_gap + plate_thick
    spring_z = wt + pip_gap

    parts = []

    # ── Cap (convex dome, wider than hole for retention) ──
    with BuildPart() as cap_bp:
        with BuildSketch():
            Circle(cap_dia / 2)
        extrude(amount=cap_protrude)
        # Fillet top edge for convex dome
        fillet(cap_bp.edges().sort_by(Axis.Z)[-1], radius=cap_fillet_r)
    # Flip so dome faces outward (Z-), flat side toward wall
    parts.append(
        Pos(0, 0, -pip_gap) * Rot(180, 0, 0) * cap_bp.part)

    # ── Stem (through hole — bridges across pip_gap on both sides) ──
    parts.append(
        Pos(0, 0, -pip_gap) *
        Cylinder(radius=stem_dia / 2, height=wt + 2 * pip_gap,
                 align=(Align.CENTER, Align.CENTER, Align.MIN)))

    # ── Hub (inner side, connects stem to bridges) ──
    parts.append(
        Pos(0, 0, spring_z) *
        Cylinder(radius=hub_dia / 2, height=plate_thick,
                 align=(Align.CENTER, Align.CENTER, Align.MIN)))

    # ── C-ring (spring element, anchored against inner wall) ──
    with BuildPart() as ring_bp:
        with BuildSketch(Plane.XY.offset(spring_z)):
            with BuildLine():
                arc_start = ring_gap_deg / 2
                arc_end = 360 - ring_gap_deg / 2
                c1 = CenterArc((0, 0), ring_od / 2,
                                arc_start, arc_end - arc_start)
                c2 = CenterArc((0, 0), ring_id / 2,
                                arc_end, -(arc_end - arc_start))
                Line(c1 @ 0, c2 @ 1)
                Line(c2 @ 0, c1 @ 1)
            make_face()
        extrude(amount=plate_thick)
    parts.append(ring_bp.part)

    # ── Cross bridges (4 arms at 90°, hub → ring) ──
    bridge_ir = hub_dia / 2
    bridge_or = ring_id / 2
    bridge_len = bridge_or - bridge_ir
    for angle in [0, 90, 180, 270]:
        rad = math.radians(angle)
        mid_r = (bridge_ir + bridge_or) / 2
        bx = mid_r * math.cos(rad)
        by = mid_r * math.sin(rad)
        parts.append(
            Pos(bx, by, spring_z + plate_thick / 2) *
            Rot(0, 0, angle) *
            Box(bridge_len, bridge_width, plate_thick))

    return Compound(children=parts)


def make_button_test():
    """Print-in-place spring button clearance test — vertical wall panel.

    A 2mm vertical wall on a stable base, with full spring buttons
    (cap + stem + hub + C-ring + bridges) through the wall at varying
    stem-to-hole clearances. Tests the exact mechanism used in the housing.

    Print upright (base on bed, wall vertical). Buttons press horizontally.

    Layout (front view, Y across, Z up):
        Row 1 (Z≈20):  7.0mm holes — main buttons     (6 clearances)
        Row 2 (Z≈35):  5.5mm holes — scroll buttons    (6 clearances)

    Stem-to-hole gap per side: 0.8  1.0  1.2  1.4  1.7  2.0 mm
    (Vertical print w/ 0.4mm layers needs large gaps — layer deformation)
    """
    wt = 2.0                         # wall thickness (matches case)
    gaps = [0.80, 1.00, 1.20, 1.40, 1.70, 2.00]
    n = len(gaps)
    spacing = 14.0                    # Y spacing between buttons
    main_hole = main_well_dia         # 7.0mm
    scroll_hole = scroll_well_dia     # 5.5mm

    row1_z = 18.0                     # main row center Z above base top
    row2_z = 33.0                     # scroll row center Z above base top

    wall_h = row2_z + 12              # wall height above base
    wall_y = (n - 1) * spacing + 24   # wall Y extent
    base_thick = 2.0
    base_behind = 18.0                # base extends behind wall (X+)
    base_front = 4.0                  # base extends in front (X-)

    # ── Base plate (wide footprint for stability) ──
    base_cx = (base_behind - base_front) / 2
    base = Pos(base_cx, 0, 0) * Box(
        base_behind + base_front + wt, wall_y, base_thick,
        align=(Align.CENTER, Align.CENTER, Align.MIN))

    # ── Vertical wall (centered at X=0, front face X=-wt/2) ──
    wall = Pos(0, 0, base_thick) * Box(
        wt, wall_y, wall_h,
        align=(Align.CENTER, Align.CENTER, Align.MIN))

    panel = base.fuse(wall).solid()

    buttons = []

    for hole_dia, row_z in [(main_hole, row1_z), (scroll_hole, row2_z)]:
        for i, gap in enumerate(gaps):
            by = -((n - 1) * spacing) / 2 + i * spacing
            bz = base_thick + row_z

            # ── Cut hole through wall (cylinder along X) ──
            panel -= (Pos(0, by, bz) *
                      Rot(0, 90, 0) *
                      Cylinder(radius=hole_dia / 2, height=wt + 1,
                               align=(Align.CENTER, Align.CENTER,
                                      Align.CENTER)))

            # ── Spring button (rotate Z-axis → X-axis, place at wall) ──
            btn = _flat_spring_button(hole_dia, gap, wt)
            buttons.append(
                Pos(-wt / 2, by, bz) * Rot(0, 90, 0) * btn)

    return Compound(children=[panel] + buttons)


COMPONENTS = {
    'mini':         ('roam_mini.step',         lambda: make_case(MINI)),
    'max':          ('roam_max.step',          lambda: make_case(MAX)),
    'max_mini':     ('roam_max_mini.step',     lambda: make_case(MAX_MINI)),
    'mini_lid':     ('roam_mini_lid.step',     lambda: make_lid(MINI)),
    'max_lid':      ('roam_max_lid.step',      lambda: make_lid(MAX)),
    'max_mini_lid': ('roam_max_mini_lid.step', lambda: make_lid(MAX_MINI)),
    'button_test':  ('flat_button_test.step',  make_button_test),
}


def main():
    STEP_DIR.mkdir(exist_ok=True)
    targets = sys.argv[1:] or list(COMPONENTS.keys())
    for name in targets:
        if name not in COMPONENTS:
            print(f"Unknown: {name}  (choose from {', '.join(COMPONENTS.keys())})")
            sys.exit(1)
        fname, builder = COMPONENTS[name]
        print(f"Building {name}...")
        part = builder()
        out = STEP_DIR / fname
        export_step(part, str(out))
        print(f"  → {out}")
    print("Done.")


if __name__ == "__main__":
    main()
