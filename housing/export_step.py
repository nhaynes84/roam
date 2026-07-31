#!/usr/bin/env python3
"""Export Roam housing components as STEP files for Shapr3D import.

Usage:
    source housing/.venv/bin/activate
    python housing/export_step.py [component ...]

Components:
    box         — Simple reference box
    base        — Base plate with screw holes and velcro recess
    button_cap  — Single button cap
    dome        — Cylindrical grip dome with screen shelf

Output goes to housing/step/ directory.
"""

import sys, math
from pathlib import Path
from build123d import *

# ── Dimensions from common.scad (keep in sync) ──
body_length = 110
body_width = 100
body_height = 60
wall_thickness = 4.0
corner_radius = 5
base_plate_thick = 4.0

# Grip cylinder
grip_r = 30
grip_cy = -grip_r   # Y center = -30
grip_cz = grip_r    # Z center = 30

# Screen shelf
shelf_z = 20
shelf_start_y = 3
shelf_end_y = 42
shelf_drop_z = 5

# OLED large (2.42" SSD1309)
oled_lg_board_w = 70
oled_lg_board_h = 48
oled_lg_vis_w = 55
oled_lg_vis_h = 29
oled_lg_vis_top = 7      # visible area starts 7mm from top board edge
oled_lg_vis_side = 7
oled_lg_hole_sp_w = 64   # mounting hole spacing X (70 - 3mm inset each side)
oled_lg_hole_sp_h = 42   # mounting hole spacing Y (48 - 3mm inset each side)
oled_board_thick = 10    # board + wires underneath
oled_hole_dia = 2.0      # M2 through-hole

# OLED small (1.3" SH1106)
oled_sm_board_w = 33
oled_sm_board_h = 33
oled_sm_vis_w = 30
oled_sm_vis_h = 15
oled_sm_vis_top = 8      # visible area starts 8mm from top board edge
oled_sm_vis_side = 3
oled_sm_hole_sp = 27     # 33 - 3mm inset each side = 27mm c-c (both axes)

# Fasteners
m2_screw_dia = 2.2
m2_head_dia = 3.8
m2_head_depth = 1.0
m2_insert_dia = 3.2
m2_insert_depth = 4.0

# Button
button_well_dia = 9
button_well_depth = 3
button_diameter = 6
button_outer_dia = 8.5
button_inner_dia = 10.8
button_wall_thick = 3.25
button_cap_dia = button_well_dia - 0.6
button_cap_height = button_well_depth - 0.5
button_cap_stem_dia = button_diameter - 0.2
button_cap_stem_h = 2.0
button_cap_dish = 0.4

button_positions = [
    (40, 52), (10, 32), (-10, 32), (-30, 47),
]

# Thumb buttons (half-size, on elbow-side flat wall)
thumb_outer_dia = button_outer_dia / 2
thumb_inner_dia = button_inner_dia / 2
thumb_positions = [
    (-35, 15),  # Lower thumb [Y, Z]
    (-35, 25),  # Upper thumb
]

# USB-C / switch
usbc_width = 9.0
usbc_height = 3.5
pico_standoff_height = 3
shim_height = 7.0
pico_height = 3.7
usbc_z = pico_standoff_height + shim_height + pico_height / 2
switch_slot_width = 4.0
switch_slot_height = 2.0
switch_y_offset = 12

# Taper & contour
taper_wrist_ymax = 28       # Y+ at wrist end (full=50, saves 22mm)
taper_elbow_ymax = 33       # Y+ at elbow end (full=50, saves 17mm)
contour_depth = 6           # Y- indent at Z=0 center (forearm curve)
contour_depth_end = 2       # Y- indent at Z=0 wrist/elbow ends
contour_fade_z = 15         # Z where contour fades to full grip extent

# Velcro
velcro_patch_length = 70
velcro_patch_width = 80
velcro_recess_depth = 1.0

# Screw positions
screw_positions = [
    ( body_length/2 - 10,  body_width/2 - 8),
    (-body_length/2 + 10,  body_width/2 - 8),
    ( body_length/2 - 10, -body_width/2 + 8),
    (-body_length/2 + 10, -body_width/2 + 8),
]

STEP_DIR = Path(__file__).parent / "step"

# Taper body station data: (x, y_min_at_z0, y_max)
_taper_stations = [
    (-55, -50 + contour_depth_end, taper_wrist_ymax),   # wrist
    (-45, -50 + contour_depth,     48),                  # wrist_mid
    (  0, -50 + contour_depth,     50),                  # center
    ( 45, -50 + contour_depth,     48),                  # elbow_mid
    ( 55, -50 + contour_depth_end, taper_elbow_ymax),    # elbow
]


def make_reference_box():
    return Box(body_length, body_width, body_height)


def _base_plate_outline(clearance, thick):
    """Lofted base plate outline matching tapered inner cavity at Z=0.

    Uses the same station data as the taper body, inset by wall_thickness + clearance.
    Returns extruded plate solid.
    """
    wt = wall_thickness
    inset = wt + clearance

    # At Z=0, the taper body Y extents define the inner cavity after shelling.
    # Inner cavity at Z=0: Y_min = station_y_min + wt, Y_max = station_y_max - wt
    # Plate = inner cavity - clearance
    sections = []
    for x, y_min_z0, y_max in _taper_stations:
        inner_ymin = y_min_z0 + inset
        inner_ymax = y_max - inset
        with BuildSketch(Plane.YZ) as sk:
            with BuildLine():
                Polyline(
                    (inner_ymin, 0),
                    (inner_ymin, thick),
                    (inner_ymax, thick),
                    (inner_ymax, 0),
                    close=True,
                )
            make_face()
        sections.append(Pos(x, 0, 0) * sk.sketch)

    return loft(sections)


def make_base_plate():
    """Flush-mount base plate — slides inside tapered dome cavity from below.

    Features:
    - Outline matches tapered dome inner cavity at Z=0, with print clearance
    - 4 case screw through-holes (countersunk, into dome heat-set bosses)
    - 4 OLED through-holes (countersunk, screen mounted from dome shelf)
    - Velcro recess on bottom face
    - Vent slots
    """
    clearance = 0.3  # per side, for slide fit
    thick = base_plate_thick  # 4.0
    wt = wall_thickness       # 4.0

    # ── Plate outline (tapered loft matching dome inner cavity) ──
    plate = _base_plate_outline(clearance, thick)

    # ── Screw through-holes (countersunk from bottom) ──
    for sx, sy in screw_positions:
        plate -= Pos(sx, sy) * Cylinder(
            radius=m2_screw_dia / 2, height=thick + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        plate -= Pos(sx, sy) * Cylinder(
            radius=m2_head_dia / 2, height=m2_head_depth + 0.1,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

    # ── Velcro recess (bottom face) ──
    plate -= extrude(
        RectangleRounded(velcro_patch_length, velcro_patch_width, 2),
        amount=velcro_recess_depth + 0.1)

    # ── OLED mounting standoffs ──
    # Board oriented with 70mm along X, 48mm along Y.
    # Visible area center in dome coords:
    screen_cy = shelf_start_y + oled_lg_vis_side + oled_lg_vis_h / 2  # 24.5
    # Board center offset: vis starts 7mm from top edge, vis center 21.5mm
    # from top, board center 24mm from top → board_cy = vis_cy - 2.5
    board_cy = screen_cy - 2.5  # 22.0

    oled_holes = [
        ( oled_lg_hole_sp_w / 2,  oled_lg_hole_sp_h / 2),   # (32, 21)
        (-oled_lg_hole_sp_w / 2,  oled_lg_hole_sp_h / 2),   # (-32, 21)
        ( oled_lg_hole_sp_w / 2, -oled_lg_hole_sp_h / 2),   # (32, -21)
        (-oled_lg_hole_sp_w / 2, -oled_lg_hole_sp_h / 2),   # (-32, -21)
    ]

    # All 4 OLED holes: flush M2 through-holes with countersinks on bottom.
    # Screen mounting handled from dome shelf side.
    for hx, hy in oled_holes:
        ox = hx
        oy = board_cy + hy
        # M2 through-hole
        plate -= Pos(ox, oy, -0.1) * Cylinder(
            radius=m2_screw_dia / 2, height=thick + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        # 3.5mm × 2mm countersink on bottom face
        plate -= Pos(ox, oy, -0.1) * Cylinder(
            radius=m2_head_dia / 2, height=m2_head_depth + 0.1,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

    # ── Vent slots ──
    vent_w = 1.0
    vent_l = 8.0
    vent_sp = 3.0
    num_vents = 4
    for i in range(num_vents):
        vx = -(num_vents - 1) * (vent_l + vent_sp) / 2 + i * (vent_l + vent_sp)
        for sy in [1, -1]:
            vy = sy * (body_width / 5)
            plate -= Pos(vx, vy, -0.1) * Box(vent_l, vent_w, thick + 0.2)

    return plate


def make_button_cap():
    cap = Cylinder(radius=button_cap_dia / 2, height=button_cap_height,
                   align=(Align.CENTER, Align.CENTER, Align.MIN))
    stem = Pos(0, 0, -button_cap_stem_h) * Cylinder(
        radius=button_cap_stem_dia / 2, height=button_cap_stem_h + 0.5,
        align=(Align.CENTER, Align.CENTER, Align.MIN))
    body = cap.fuse(stem)
    cap_r = button_cap_dia / 2
    sphere_r = (cap_r**2 + button_cap_dish**2) / (2 * button_cap_dish)
    center_z = button_cap_height + sphere_r - button_cap_dish
    dish = Pos(0, 0, center_z) * Sphere(radius=sphere_r)
    return body.cut(dish).solid()


def _station_polygon(y_min_z0, y_max):
    """Build a closed polygon on YZ plane for one taper station.

    5 vertices:
      (y_min_z0, 0) → (-65, contour_fade_z) → (-65, 65) → (y_max, 65) → (y_max, 0)
    """
    pts = [
        (y_min_z0, 0),
        (-65, contour_fade_z),
        (-65, 65),
        (y_max, 65),
        (y_max, 0),
    ]
    with BuildSketch(Plane.YZ) as sk:
        with BuildLine():
            Polyline(*pts, close=True)
        make_face()
    return sk.sketch


def _build_taper_body():
    """Build taper body as a 5-station loft along X."""
    sections = []
    for x, y_min_z0, y_max in _taper_stations:
        face = _station_polygon(y_min_z0, y_max)
        moved = Pos(x, 0, 0) * face
        sections.append(moved)

    return loft(sections)


def make_dome():
    """Cylindrical grip dome with organic taper + forearm contour.

    Flow: extrude solid → intersect taper body → shell → fillet → boolean cuts.
    """
    wt = wall_thickness

    # ── 1. Build outer solid: profile on YZ plane, extrude along X ──
    with BuildPart() as p:
        with BuildSketch(Plane.YZ):
            with BuildLine():
                Line((-50, 0), (grip_cy - grip_r, grip_cz))
                ThreePointArc((grip_cy - grip_r, grip_cz),
                              (grip_cy, grip_cz + grip_r),
                              (grip_cy + grip_r, grip_cz))
                Line((grip_cy + grip_r, grip_cz), (shelf_start_y, shelf_z))
                Line((shelf_start_y, shelf_z), (shelf_end_y, shelf_z - 2))
                Line((shelf_end_y, shelf_z - 2), (50, 0))
                Line((50, 0), (-50, 0))
            make_face()
        extrude(amount=body_length / 2, both=True)
    solid_dome = p.part

    # ── 2. Build taper body and intersect ──
    taper = _build_taper_body()
    solid_dome = solid_dome.intersect(taper).solid()

    # ── 3. Shell — hollow with open bottom face ──
    with BuildPart() as shelled:
        add(solid_dome)
        bottom = shelled.faces().sort_by(Axis.Z)[0]
        offset(amount=-wt, openings=[bottom])
    dome = shelled.part

    # ── 4. Fillets on outer edges ──
    # Apply conservatively — try/except per edge group since some may fail
    try:
        # Get edges roughly aligned with Z (vertical edges on end faces)
        z_edges = dome.edges().filter_by(Axis.Z)
        if z_edges:
            dome = fillet(z_edges, radius=3)
    except Exception:
        pass  # thin geometry may reject some fillets

    try:
        # Top taper transition edges on Y+ side — edges near the shelf/taper junction
        top_edges = [e for e in dome.edges()
                     if e.center().Z > shelf_z - 5
                     and e.center().Y > shelf_end_y - 10
                     and abs(e.center().X) > body_length / 2 - 20]
        if top_edges:
            dome = fillet(top_edges, radius=5)
    except Exception:
        pass

    # ── 5. Button wells (radial bores into grip cylinder) ──
    for bx, bz in button_positions:
        dz = bz - grip_cz
        y_surface = grip_cy + math.sqrt(grip_r**2 - dz**2)
        theta = math.degrees(math.atan2(dz, y_surface - grip_cy))
        overshoot = 1
        taper_rate = (button_inner_dia - button_outer_dia) / wt
        d_start = button_outer_dia - taper_rate * overshoot
        d_end = button_inner_dia + taper_rate * overshoot
        bore_depth = wt + 2 * overshoot
        cone = (Pos(bx, grip_cy, grip_cz) *
                Rot(theta, 0, 0) *
                Pos(0, grip_r + overshoot, 0) *
                Rot(90, 0, 0) *
                Cone(bottom_radius=d_start / 2,
                     top_radius=d_end / 2,
                     height=bore_depth,
                     align=(Align.CENTER, Align.CENTER, Align.MIN)))
        dome -= cone

    # ── 6. Thumb button wells (bore along -X into elbow-side wall) ──
    for ty, tz in thumb_positions:
        overshoot = 1
        taper_rate = (thumb_inner_dia - thumb_outer_dia) / wt
        d_start = thumb_outer_dia - taper_rate * overshoot
        d_end = thumb_inner_dia + taper_rate * overshoot
        bore_depth = wt + 2 * overshoot
        cone = (Pos(body_length / 2 + overshoot, ty, tz) *
                Rot(0, -90, 0) *
                Cone(bottom_radius=d_start / 2,
                     top_radius=d_end / 2,
                     height=bore_depth,
                     align=(Align.CENTER, Align.CENTER, Align.MIN)))
        dome -= cone

    # ── 7. Screen window ──
    screen_y = shelf_start_y + oled_lg_vis_side + oled_lg_vis_h / 2
    dome -= Pos(0, screen_y, shelf_z) * Box(oled_lg_vis_w, oled_lg_vis_h, wt * 3)

    # ── 8. USB-C cutout on wrist wall ──
    dome -= Pos(-body_length / 2, 0, usbc_z) * Box(wt + 4, usbc_width, usbc_height)

    # ── 9. Switch slot on wrist wall ──
    dome -= Pos(-body_length / 2, switch_y_offset, usbc_z) * Box(
        wt + 4, switch_slot_width, switch_slot_height)

    # Pick largest solid (boolean cuts may leave slivers)
    solids = dome.solids().sort_by(SortBy.VOLUME)
    return solids[-1]


def _spring_button(outer_dia, inner_dia, wt):
    """Single print-in-place spring button assembly, built along Z axis.

    Z=0 = outer wall surface (finger side)
    Z+ = inward through wall to housing interior

    Cross-section (side):
        Z<0:  [  cap  ]         ← finger presses here
        Z=0:  ---wall---
        Z>0:  | stem  |         ← passes through tapered hole
              ---wall---
              [hub]+[bridges]   ← spring mechanism
              [ C-ring ]        ← anchored flange

    Top view of spring (inner wall side):
              ┌─bridge─┐
         ─ring─ [hub] ─ring─    (4 bridges at 90°, C-ring around outside)
              └─bridge─┘
    """
    cap_protrude = 1.0
    cap_dia = outer_dia - 0.4
    stem_dia = outer_dia - 1.0
    plate_thick = 1.5

    # Spring ring (C-shaped) — anchored against inner wall
    ring_od = inner_dia + 4
    ring_width = 1.5  # radial wall of the ring
    ring_id = ring_od - 2 * ring_width
    ring_gap = 30  # degrees of opening in C-ring

    # Hub — center disc connected to stem
    hub_dia = max(stem_dia * 0.6, 3.0)

    # Cross bridges — 4 arms connecting hub to ring
    bridge_width = 1.0

    parts = []

    # ── Cap (finger side, protrudes past outer wall) ──
    parts.append(
        Pos(0, 0, -cap_protrude) *
        Cylinder(radius=cap_dia / 2, height=cap_protrude,
                 align=(Align.CENTER, Align.CENTER, Align.MIN)))

    # ── Stem (through the tapered hole) ──
    parts.append(
        Cylinder(radius=stem_dia / 2, height=wt,
                 align=(Align.CENTER, Align.CENTER, Align.MIN)))

    # ── Hub (inner wall side) ──
    parts.append(
        Pos(0, 0, wt) *
        Cylinder(radius=hub_dia / 2, height=plate_thick,
                 align=(Align.CENTER, Align.CENTER, Align.MIN)))

    # ── C-ring (spring element, anchored against inner wall) ──
    # Full ring minus a gap
    with BuildPart() as ring_bp:
        with BuildSketch(Plane.XY.offset(wt)):
            with BuildLine():
                # Outer arc (full circle minus gap)
                arc_start = ring_gap / 2
                arc_end = 360 - ring_gap / 2
                c1 = CenterArc((0, 0), ring_od / 2, arc_start, arc_end - arc_start)
                # Inner arc (reverse direction to close the shape)
                c2 = CenterArc((0, 0), ring_id / 2, arc_end, -(arc_end - arc_start))
                # Close the ends
                Line(c1 @ 0, c2 @ 1)
                Line(c2 @ 0, c1 @ 1)
            make_face()
        extrude(amount=plate_thick)
    parts.append(ring_bp.part)

    # ── Cross bridges (4 arms at 90°, connecting hub to ring) ──
    bridge_ir = hub_dia / 2
    bridge_or = ring_id / 2
    bridge_len = bridge_or - bridge_ir
    for angle in [0, 90, 180, 270]:
        rad = math.radians(angle)
        mid_r = (bridge_ir + bridge_or) / 2
        cx = mid_r * math.cos(rad)
        cy = mid_r * math.sin(rad)
        parts.append(
            Pos(cx, cy, wt + plate_thick / 2) *
            Rot(0, 0, angle) *
            Box(bridge_len, bridge_width, plate_thick))

    return Compound(children=parts)


def make_buttons():
    """All 6 spring button assemblies positioned in dome coordinates."""
    wt = wall_thickness
    parts = []

    # ── Finger buttons (radial on grip cylinder) ──
    for bx, bz in button_positions:
        dz = bz - grip_cz
        y_surface = grip_cy + math.sqrt(grip_r**2 - dz**2)
        theta = math.degrees(math.atan2(dz, y_surface - grip_cy))

        btn = _spring_button(button_outer_dia, button_inner_dia, wt)
        # Orient: Z+ axis → radial inward (-Y in dome coords after rotation)
        # Same transform as the bore holes
        placed = (Pos(bx, grip_cy, grip_cz) *
                  Rot(theta, 0, 0) *
                  Pos(0, grip_r, 0) *
                  Rot(90, 0, 0) *
                  btn)
        parts.append(placed)

    # ── Thumb buttons (flat wall, bore along -X) ──
    for ty, tz in thumb_positions:
        btn = _spring_button(thumb_outer_dia, thumb_inner_dia, wt)
        placed = (Pos(body_length / 2, ty, tz) *
                  Rot(0, -90, 0) *
                  btn)
        parts.append(placed)

    return Compound(children=parts)


def _lid_outline_loft(thickness):
    """Loft lid outline matching tapered dome footprint at Z=0."""
    sections = []
    for x, y_min_z0, y_max in _taper_stations:
        with BuildSketch(Plane.YZ) as sk:
            with BuildLine():
                Polyline(
                    (y_min_z0, 0),
                    (y_min_z0, thickness),
                    (y_max, thickness),
                    (y_max, 0),
                    close=True,
                )
            make_face()
        sections.append(Pos(x, 0, 0) * sk.sketch)
    return loft(sections)


def _lid_lip_loft(lid_thickness, lip_height, lip_clearance):
    """Loft registration lip matching tapered inner cavity."""
    wt = wall_thickness
    inset = wt + lip_clearance
    sections = []
    for x, y_min_z0, y_max in _taper_stations:
        inner_ymin = y_min_z0 + inset
        inner_ymax = y_max - inset
        with BuildSketch(Plane.YZ) as sk:
            with BuildLine():
                Polyline(
                    (inner_ymin, lid_thickness),
                    (inner_ymin, lid_thickness + lip_height),
                    (inner_ymax, lid_thickness + lip_height),
                    (inner_ymax, lid_thickness),
                    close=True,
                )
            make_face()
        sections.append(Pos(x, 0, 0) * sk.sketch)
    return loft(sections)


def make_lid():
    """Bottom lid with registration lip, screw holes, velcro recess, and vents."""
    lid_thickness = 2.5
    lip_height = 1.5
    lip_clearance = 0.15
    wt = wall_thickness

    # Main plate — tapered outline
    plate = _lid_outline_loft(lid_thickness)

    # Registration lip on top — tapered to match inner cavity
    lip = _lid_lip_loft(lid_thickness, lip_height, lip_clearance)
    plate = plate.fuse(lip).solid()

    # Screw clearance holes + countersink
    for x, y in screw_positions:
        plate -= Pos(x, y) * Cylinder(
            radius=m2_screw_dia / 2,
            height=lid_thickness + lip_height + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        plate -= Pos(x, y) * Cylinder(
            radius=m2_head_dia / 2,
            height=m2_head_depth + 0.1,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

    # Velcro recess on bottom
    plate -= extrude(
        RectangleRounded(velcro_patch_length, velcro_patch_width, 2),
        amount=velcro_recess_depth + 0.1)

    # Vent slots
    vent_w = 1.0
    vent_l = 8.0
    vent_sp = 3.0
    num_vents = 4
    for i in range(num_vents):
        vx = -(num_vents - 1) * (vent_l + vent_sp) / 2 + i * (vent_l + vent_sp)
        for sy in [1, -1]:
            vy = sy * (body_width / 5)
            plate -= Pos(vx, vy, 0) * Box(vent_l, vent_w, lid_thickness + 0.2)

    return plate


def make_screen_adapter():
    """Bezel that sits flush in the big case's 55x29mm screen window.

    Reduces the opening for the small 1.3" SH1106. Glued in place.
    4 standoffs on the back (2mm tall) with M2 holes to mount the small screen.
    """
    bezel_w = oled_lg_vis_w         # 55mm — matches window cutout
    bezel_h = oled_lg_vis_h         # 29mm
    bezel_thick = 2.0

    # Window for small screen visible area (+1mm tolerance)
    window_w = oled_sm_vis_w + 1    # 31mm
    window_h = oled_sm_vis_h + 1    # 16mm
    # Vis area offset from board center: -(33/2) + 8 + 15/2 = -1mm
    window_offset_y = -(oled_sm_board_h / 2) + oled_sm_vis_top + oled_sm_vis_h / 2

    standoff_h = 2.0
    standoff_dia = 5.0              # wall around M2

    # ── Bezel plate ──
    plate = extrude(
        RectangleRounded(bezel_w, bezel_h, 1.5),
        amount=bezel_thick)

    # ── Window cutout ──
    plate -= Pos(0, window_offset_y, -0.1) * extrude(
        RectangleRounded(window_w, window_h, 1),
        amount=bezel_thick + 0.2)

    # ── 4 standoffs on back face with M2 through-holes ──
    for dx in [-1, 1]:
        for dy in [-1, 1]:
            sx = dx * oled_sm_hole_sp / 2   # ±13.5
            sy = dy * oled_sm_hole_sp / 2   # ±13.5
            plate += Pos(sx, sy, bezel_thick) * Cylinder(
                radius=standoff_dia / 2, height=standoff_h,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
            plate -= Pos(sx, sy, -0.1) * Cylinder(
                radius=m2_screw_dia / 2, height=bezel_thick + standoff_h + 0.2,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

    return plate


COMPONENTS = {
    "box": ("reference_box.step", make_reference_box),
    "base": ("base_plate.step", make_base_plate),
    "lid": ("roam_lid.step", make_lid),
    "button_cap": ("button_cap.step", make_button_cap),
    "dome": ("roam_dome.step", make_dome),
    "buttons": ("roam_buttons.step", make_buttons),
    "adapter": ("screen_adapter.step", make_screen_adapter),
}


def main():
    STEP_DIR.mkdir(exist_ok=True)
    targets = sys.argv[1:] if len(sys.argv) > 1 else COMPONENTS.keys()
    for name in targets:
        if name not in COMPONENTS:
            print(f"Unknown component: {name}")
            print(f"Available: {', '.join(COMPONENTS.keys())}")
            sys.exit(1)
        filename, builder = COMPONENTS[name]
        print(f"Building {name}...")
        part = builder()
        out_path = STEP_DIR / filename
        export_step(part, str(out_path))
        print(f"  → {out_path}")
    print("Done.")


if __name__ == "__main__":
    main()
