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

ARM_R is nominal, NOT critical, and that is deliberate. Every rib face is cut
FOAM (4 mm) proud of where skin would be, for closed-cell foam or stick-on TPU.
A forearm is not a cylinder -- it tapers, and its cross-section reconfigures as
you pronate, because the radius crosses the ulna. A shell fitted rigidly to one
arm position binds in another. So: rigid only under the phone, where the screen
must stay flat; compliant at the skin, where the shape moves. The pad absorbs
several mm of error, which is why nobody has to measure anything precisely.
If you do want it closer: ARM_R = forearm circumference / (2*pi).
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

ARM_R = 45.0         # nominal forearm radius, mm (90 mm dia)
GAP = 4.0            # air gap between arm and tray underside, at the crown
FOAM = 4.0           # compliant pad thickness on EVERY rib face -- see below
RIB_W = 62.0         # rib span across the arm
RIB_T = 14.0         # rib thickness along the arm
RIB_Y = (34.0, 112.0)  # rib centres, from the elbow (open) end

WING = 8.0           # strap-anchor flange, each side
WING_T = 4.0
SLOT_L, SLOT_W = 26.0, 3.6   # for 25 mm webbing

JACK_W = 22.0        # 3.5 mm jack notch (sailfish jack is on the TOP edge)

# ------------------------------------------------- phone face features
# Taken from the scale drawing File:Pixel_(2016).svg on Wikimedia Commons,
# which is authored at 1 SVG unit = 1 mm and whose outline matches the spec
# body exactly (69.5 x 143.8). Its internal features are traced, so treat
# them as +/-1 mm and check against the real phone once a print exists.
# SVG origin is the top-left of the FACE, y increasing toward the USB-C end.
FEAT_TOL = 0.6       # opening margin, absorbs the tracing error
SCREEN_SVG = (3.32, 14.30, 66.12, 127.77)   # x0,y0,x1,y1 -- black display area
EARPIECE_SVG = (27.10, 5.44, 40.78, 6.51)
PROX_SVG = (31.49, 10.70, 36.38, 12.65)     # proximity + ambient light
CAM_SVG = (11.22, 5.78, 1.50)               # cx, cy, r -- front camera
PWR_SVG = (37.11, 46.01)                    # power button, y range, right edge
VOL_SVG = (55.16, 72.91)                    # volume rocker, y range, right edge
VENT_R = 6.0
EPS = 0.1

# --------------------------------------------------------------- derived
POCK_L = PH_L + 2 * CLR
POCK_W = PH_W + 2 * CLR
POCK_D = PH_T + 0.3

OUT_W = POCK_W + 2 * WALL          # tray outer width
OUT_L = POCK_L + WALL              # closed at the hand end, open at the elbow
OUT_H = FLOOR + POCK_D + LIP_H

# The rib faces are carved by a cylinder FOAM larger than the arm, about an
# axis dropped by the same amount -- so every rib face stands FOAM proud of
# where skin would be, uniformly, while the crown still clears by GAP.
# That gap is for closed-cell foam or stick-on TPU, and it is what makes
# ARM_R approximate rather than critical: ~4 mm of squish absorbs the error,
# and a forearm changes cross-section as it pronates anyway.
ARM_CUT_R = ARM_R + FOAM
ARM_AXIS_Z = -(ARM_R + GAP + FOAM)

# how far the ribs hang below the tray at their outer tips
SAG = -(ARM_AXIS_Z + math.sqrt(ARM_CUT_R ** 2 - (RIB_W / 2) ** 2))

WING_X0 = OUT_W / 2                # wings run from the tray wall outward
WING_X1 = OUT_W / 2 + WING

# --------------------------------------- SVG face coords -> model coords
# The phone sits with its TOP edge (headphone jack) at the hand end.
PHONE_TOP_Y = POCK_L - CLR         # Y of the phone's top edge in the tray
def fx(x):  return x - PH_W / 2    # SVG x -> model X (centred)
def fy(y):  return PHONE_TOP_Y - y  # SVG y -> model Y (elbow = 0)

# Screen aperture: the housing bezel closes down to the black display area,
# opened by FEAT_TOL so a tracing error can never clip live pixels.
_sx0, _sy0, _sx1, _sy1 = SCREEN_SVG
WIN_X = max(abs(fx(_sx0)), abs(fx(_sx1))) + FEAT_TOL
WIN_Y0, WIN_Y1 = fy(_sy1) - FEAT_TOL, fy(_sy0) + FEAT_TOL


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

# Carve the forearm (plus the foam allowance) out of the ribs.
arm = Pos(0, OUT_L / 2, ARM_AXIS_Z) * Rot(90, 0, 0) * Cylinder(
    ARM_CUT_R, OUT_L + 60
)
part -= arm

# Phone pocket -- runs out the elbow end so the phone slides in
part -= bbox(-POCK_W / 2, POCK_W / 2, -10, POCK_L, FLOOR, FLOOR + POCK_D)

# Screen aperture. This is the bezel: the face closes down to the display
# instead of exposing the phone's own bezel, so the housing reads as the
# device rather than as a tray with a phone in it.
part -= bbox(-WIN_X, WIN_X, WIN_Y0, WIN_Y1, FLOOR + POCK_D, OUT_H + 10)

# Sensor apertures through the top bezel -- earpiece, front camera and the
# proximity/ambient window. Covering any of these breaks the phone: no
# proximity means the screen stays lit against your face and eats battery.
_ex0, _ey0, _ex1, _ey1 = EARPIECE_SVG
part -= bbox(fx(_ex0) - FEAT_TOL, fx(_ex1) + FEAT_TOL,
             fy(_ey1) - FEAT_TOL, fy(_ey0) + FEAT_TOL,
             FLOOR + POCK_D, OUT_H + 10)

_px0, _py0, _px1, _py1 = PROX_SVG
part -= bbox(fx(_px0) - FEAT_TOL, fx(_px1) + FEAT_TOL,
             fy(_py1) - FEAT_TOL, fy(_py0) + FEAT_TOL,
             FLOOR + POCK_D, OUT_H + 10)

_cx, _cy, _cr = CAM_SVG
part -= Pos(fx(_cx), fy(_cy), FLOOR + POCK_D) * Cylinder(
    _cr + FEAT_TOL, (OUT_H + 10), align=(Align.CENTER, Align.CENTER, Align.MIN)
)

# Button apertures, right edge (+X): power ABOVE volume on this phone.
# Two placed openings rather than one 55 mm slot -- the slot worked but it
# left the phone's own edge on show, which is the "tray with a phone in it"
# look. Sized for a finger now; a print-in-place actuator is a separate pass.
for (_b0, _b1) in (PWR_SVG, VOL_SVG):
    part -= bbox(
        POCK_W / 2 - 1.0, OUT_W / 2 + EPS,
        fy(_b1) - FEAT_TOL, fy(_b0) + FEAT_TOL,
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
