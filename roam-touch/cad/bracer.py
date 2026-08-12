"""
ROAM Touch -- forearm bracer cradle for a Google Pixel (sailfish, 2016).

V1 form factor: a flat tray that holds the phone, carried on two transverse
saddle ribs that conform to the forearm, with an open span between them for
airflow. Strap anchors are slots in flat wings either side.

Print orientation: STANDING ON THE ELBOW END. Measured, not guessed --
verify_bracer.py compares four orientations by unsupported face area:

    standing on elbow end    13.3 cm2 support   8.4 cm2 bed   147 mm tall  <-- use
    on its side              36.4 cm2           5.9 cm2        91 mm
    pocket down              88.5 cm2          16.2 cm2        30 mm
    pocket up               105.9 cm2           0.6 cm2        30 mm

Pocket-up is the intuitive choice and the worst one: the part ends up balanced
on four thin rib-tip edges, so the slicer supports nearly the whole underside.
Standing it on end makes every wall vertical. Use a brim -- it is 147 mm tall
on a small footprint. Layer lines then run across the arm axis, which is the
weak direction in bending; the strap carries that load, not the tray, but do
not stand on it.

Geometry note -- the constraint that drives the shape:
a ~75 mm wide flat tray on a 90 mm diameter forearm has ~20 mm of sagitta.
That wedge is unavoidable for a rigid slab; the ribs carry it instead of a
solid block, which saves the weight and gives the phone a cooling gap.

ARM_R is the tuning knob. Measure the forearm circumference where you'll wear
it and set ARM_R = circumference / (2*pi).
"""

from build123d import *
import math
import os

# ------------------------------------------------------------------ phone
# Google Pixel (sailfish, 2016). Verified against spec sheets.
# The back tapers from 8.5 mm at the top edge to ~7.3 mm at the USB-C end;
# the pocket is cut to the max, so the thin end sits slightly proud of the
# floor. The front lip holds it. A strip of foam tape squares it up if it
# rattles.
PH_L, PH_W, PH_T = 143.8, 69.5, 8.5

# ------------------------------------------------------------- parameters
CLR = 0.4            # per-side clearance around the phone
WALL = 2.4           # pocket side wall
FLOOR = 2.2          # tray floor under the phone
LIP_SIDE = 2.5       # front lip over the long bezels
LIP_END = 4.0        # front lip at the hand end
LIP_H = 2.4          # lip height above the phone face (also screen standoff)

ARM_R = 45.0         # forearm radius, mm (90 mm dia) -- THE tuning knob
GAP = 4.0            # air gap between arm and tray underside
RIB_W = 62.0         # rib span across the arm
RIB_T = 14.0         # rib thickness along the arm
RIB_Y = (34.0, 112.0)  # rib centres, from the elbow (open) end

WING = 8.0           # strap-anchor flange, each side
WING_T = 4.0
SLOT_L, SLOT_W = 26.0, 3.6   # for 25 mm webbing

BTN_Y0, BTN_Y1 = 25.0, 80.0  # side relief for power + volume, from hand end
JACK_W = 22.0        # 3.5 mm jack notch (sailfish jack is on the TOP edge)
VENT_R = 6.0
EPS = 0.1

# --------------------------------------------------------------- derived
POCK_L = PH_L + 2 * CLR
POCK_W = PH_W + 2 * CLR
POCK_D = PH_T + 0.3

OUT_W = POCK_W + 2 * WALL          # tray outer width
OUT_L = POCK_L + WALL              # closed at the hand end, open at the elbow
OUT_H = FLOOR + POCK_D + LIP_H

# how far the ribs hang below the tray at their outer tips
SAG = GAP + ARM_R - math.sqrt(ARM_R ** 2 - (RIB_W / 2) ** 2)

WING_X0 = OUT_W / 2                # wings run from the tray wall outward
WING_X1 = OUT_W / 2 + WING


def bbox(x0, x1, y0, y1, z0, z1):
    """Axis-aligned box by bounds -- far less error-prone than align juggling."""
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(
        x1 - x0, y1 - y0, z1 - z0
    )


# ------------------------------------------------------------------ build
# Tray body: Y = 0 at the elbow (open) end, Y = OUT_L at the hand end.
part = bbox(-OUT_W / 2, OUT_W / 2, 0, OUT_L, 0, OUT_H)

# Strap wings, both sides, full length
part += bbox(-WING_X1, -WING_X0, 0, OUT_L, 0, WING_T)
part += bbox(WING_X0, WING_X1, 0, OUT_L, 0, WING_T)

# Saddle ribs
for y in RIB_Y:
    part += bbox(-RIB_W / 2, RIB_W / 2, y - RIB_T / 2, y + RIB_T / 2, -SAG, 0)

# Carve the forearm out of the ribs. Cylinder axis along Y, tangent at z = -GAP.
arm = Pos(0, OUT_L / 2, -(ARM_R + GAP)) * Rot(90, 0, 0) * Cylinder(
    ARM_R, OUT_L + 60
)
part -= arm

# Phone pocket -- runs out the elbow end so the phone slides in
part -= bbox(-POCK_W / 2, POCK_W / 2, -10, POCK_L, FLOOR, FLOOR + POCK_D)

# Screen window: inset from the pocket, leaving the retaining lip
part -= bbox(
    -(POCK_W / 2 - LIP_SIDE), POCK_W / 2 - LIP_SIDE,
    -10, POCK_L - LIP_END,
    FLOOR + POCK_D, OUT_H + 10,
)

# Side relief for power + volume (right side, viewed from the front = +X).
# One generous window rather than two guessed cutouts -- exact button
# positions weren't measurable, and this cannot miss.
part -= bbox(
    POCK_W / 2 - 1.0, OUT_W / 2 + EPS,
    OUT_L - BTN_Y1, OUT_L - BTN_Y0,
    FLOOR + 0.8, OUT_H + 10,
)

# 3.5 mm headphone jack notch, hand end
part -= bbox(
    -JACK_W / 2, JACK_W / 2,
    OUT_L - WALL - EPS, OUT_L + 10,
    FLOOR + 0.8, OUT_H + 10,
)

# Floor vents (cooling + weight), clear of the ribs
for (yc, ln) in ((73.0, 50.0), (135.0, 18.0)):
    vent = extrude(RectangleRounded(52.0, ln, VENT_R), amount=FLOOR + 4)
    part -= Pos(0, yc, -2) * vent

# Strap slots, one pair per rib
for y in RIB_Y:
    for sx in (-1, 1):
        cx = sx * (WING_X0 + WING / 2)
        part -= bbox(
            cx - SLOT_W / 2, cx + SLOT_W / 2,
            y - SLOT_L / 2, y + SLOT_L / 2,
            -2, WING_T + 2,
        )

# ----------------------------------------------------------------- export
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(out, exist_ok=True)
export_step(part, os.path.join(out, "bracer.step"))
export_stl(part, os.path.join(out, "bracer.stl"))

print(f"outer      {OUT_W + 2*WING:.1f} W x {OUT_L:.1f} L x {OUT_H + SAG:.1f} H mm")
print(f"tray       {OUT_W:.1f} x {OUT_L:.1f} x {OUT_H:.1f}")
print(f"pocket     {POCK_W:.1f} x {POCK_L:.1f} x {POCK_D:.1f}")
print(f"rib drop   {SAG:.2f} mm  (ARM_R={ARM_R}, GAP={GAP}, RIB_W={RIB_W})")
print(f"volume     {part.volume/1000:.1f} cm3  ~= {part.volume/1000*1.27:.0f} g PETG")
