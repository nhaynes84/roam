"""
ROAM Touch -- LANDSCAPE MASSING STUDY.  Not a finished part.

★ WHAT THIS IS FOR.  bracer.py mounts the phone PORTRAIT: 147 mm along the
forearm, 96 across it.  The owner floated landscape -- "a more reasonable use
of a forearm" -- which turns those two numbers over.  This file puts a real
number on it instead of an opinion, at the same wall thicknesses, the same 4 mm
FOAM relief, the same 15 mm guard and the same payload as the real part, so the
mass and the envelope are comparable to within a few grams.  There is no
low-poly tessellation, no end cap and no print-in-place buttons here -- it is a
massing solid and the report says so.

★★ THE FINDING, which is why the study was worth doing at all.
A rigid 85.6 x 54 mm pack cannot lie flat under a PORTRAIT tray without lifting
it.  The arm's crown eats the middle of the span: at GAP 8 the widest flat band
with 12 mm of depth under it is ~28 mm, and the pack needs 54.  That is what
forced GAP from 8 to 23 and put the device 51 mm off the arm.

Landscape does not have that problem, because THE TRAY IS WIDER THAN THE ARM.
The phone is 143.8 long; the forearm plus its pad is 98 across.  So ~24 mm of
each end of the phone hangs off the limb entirely, and under those wings the
arm has already fallen 12 mm or more away from the tray floor.  The pack goes
there, hung off the tray floor on rails exactly as the cards are, and GAP stays
at 10.5 instead of 23.  The cards then fit in the band under the tray at full
width, because with no tilt that band is clear from wing to wing.

    portrait, whole payload under the phone   GAP 23.0   standoff 51.2 mm
    portrait, pack in a strap module          GAP 11.6   standoff 39.8 mm
    landscape, pack in the wing               GAP 10.5   standoff 42.9 mm

★ So landscape carries the ENTIRE payload on the body for 3 mm more standoff
than portrait manages only by taking the pack off it -- and it cuts the length
along the forearm from 147 mm to 90.  It pays for that with width: 147 across
against portrait's 96, on a limb that is 90.

⚠️ AND THE WINGS ARE THE COST AS WELL AS THE ANSWER.  Those same 24 mm per side
are unsupported slab hanging off a 90 mm limb: mass out at a ~60 mm lever arm
from the strap, and nothing with a sleeve goes over it.  The report prints the
overhang explicitly rather than burying it inside a bounding box.

FRAME -- deliberately different letters from bracer.py so nothing gets carried
across by eye:
    X = ACROSS the arm.  The phone's 143.8 mm length runs along it, X = 0 is
        the arm's centre line.
    Y = ALONG the arm.  The phone's 69.5 mm width runs along it, Y = 0 is the
        wrist end.
    Z = up, out of the screen.  Z = 0 is the UNDERSIDE of the tray floor.
The arm is a cylinder along Y.  TILT stays 0: in portrait a 25 deg roll aims the
screen inboard for free, but in landscape the tray is 147 mm across, so 25 deg
would drop one wing 31 mm into the arm and lift the other 31 into the air.
Landscape buys its eyeline by being wide, and gives up the 4.2 mm of standoff
that the portrait tilt earns back.
"""

from build123d import *
import math
import os

# ------------------------------------------------------------------ phone
PH_L, PH_W, PH_T = 143.8, 69.5, 8.5          # Pixel (sailfish), as bracer.py
SCREEN_W, SCREEN_H = 62.8, 113.5             # black display area, off SCREEN_SVG

# ------------------------------------------------------ shared with bracer.py
CLR, WALL, FLOOR, LIP_H, LIP_SIDE = 0.4, 2.4, 2.2, 2.4, 2.5
ARM_R, FOAM = 45.0, 4.0
WALL_OUT, WALL_ARM, CUFF_T = 2.0, 2.0, 3.0
GUARD_H, GUARD_W = 15.0, 5.0
STRAP_W, STRAP_D = 26.0, 2.2
CARD_L, CARD_W, CARD_T = 85.60, 53.98, 0.76
CARD_N, CARD_CLR, CARD_LEDGE = 2, 0.35, 1.4
PACK_L, PACK_W, PACK_T = 85.6, 54.0, 10.0
PACK_CLR, PACK_LEDGE = 0.6, 1.4

# ------------------------------------------------------------- the envelope
POCK_L, POCK_W, POCK_D = PH_L + 2 * CLR, PH_W + 2 * CLR, PH_T + 0.3
OUT_X = POCK_L + WALL              # 147.0 across; open at one end like the tray
OUT_H = FLOOR + POCK_D + LIP_H     # 13.4
TRAY_Y = POCK_W + 2 * WALL         # 75.1 along the arm
HW = OUT_X / 2

# ★ THE ONE DIMENSION LANDSCAPE ADDS.  The body has to be 90 mm along the arm,
# not 75.1, because the payload is 85.6 long and in this orientation that length
# runs ALONG the limb.  The 7.4 mm of apron either side of the tray is not
# waste -- the two strap bands land in it.
BODY_Y = 90.0
TRAY_Y0 = (BODY_Y - TRAY_Y) / 2.0

GAP = 10.5                         # tray floor to the FOAM surface, at the crown
ARM_CUT_R = ARM_R + FOAM           # 49 -- every arm face stands FOAM proud
ARM_CZ = -GAP - ARM_CUT_R
R_CUFF = ARM_CUT_R + CUFF_T
WRAP = 40.0                        # degrees of arm the cuff holds, each side
EPS = 0.1


def arm_z(x, r=ARM_CUT_R):
    """Z of the arm cut at X, or None where the cylinder does not reach."""
    d = r * r - x * x
    return ARM_CZ + math.sqrt(d) if d > 0 else None


def x_clear(z, r=ARM_CUT_R):
    """Smallest |X| at which the arm cut has fallen to or below z."""
    d = r * r - (z - ARM_CZ) ** 2
    return math.sqrt(d) if d > 0 else 0.0


# ---- payload, both hung off the tray floor on rails ------------------------
PACK_Z1 = -0.6
PACK_Z0 = PACK_Z1 - (PACK_T + 2 * PACK_CLR)
PACK_FLOOR = PACK_Z0 - PACK_LEDGE                    # outer skin line, pack wing
CARD_Z1 = -0.6
CARD_Z0 = CARD_Z1 - (CARD_N * CARD_T + 0.30)
CARD_FLOOR = CARD_Z0 - CARD_LEDGE

PACK_SW, CARD_SW = PACK_W + 2 * PACK_CLR, CARD_W + 2 * CARD_CLR
# the pack starts where the arm has fallen past the pack's own skin line
PACK_X_IN = x_clear(PACK_FLOOR)
PACK_X_OUT = PACK_X_IN + PACK_SW
# the cards go in the clear band under the tray, pushed off centre so they miss
# the pack.  With no tilt that band runs the full width, so this is free.
CARD_X_IN = -PACK_X_IN + 2.0
CARD_X_OUT = CARD_X_IN + CARD_SW
assert PACK_X_OUT <= HW - WALL_OUT, (
    f"pack does not fit the wing: needs |x| {PACK_X_IN:.1f}..{PACK_X_OUT:.1f}, "
    f"tray edge is {HW - WALL_OUT:.1f}.  Raise GAP or widen the body.")
assert CARD_X_OUT <= HW - WALL_OUT, "cards run off the far wing"
assert arm_z(CARD_X_IN, ARM_CUT_R + STRAP_D) < CARD_FLOOR - 1.0, \
    "the strap channel comes up through the card channel"


def bbox(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(
        x1 - x0, y1 - y0, z1 - z0)


def arm_cyl(r, length=None, yc=None):
    length = BODY_Y + 60 if length is None else length
    yc = BODY_Y / 2 if yc is None else yc
    return Pos(0, yc, ARM_CZ) * Rot(90, 0, 0) * Cylinder(r, length)


# ------------------------------------------------------------------- massing
# Built as blocks rather than a lofted section, because the point of the file is
# the ENVELOPE and the MASS, not the surface.  Read it wing tip to wing tip:
#   * the PACK wing is a slab exactly as deep as the pack and no deeper;
#   * the middle is the arm -- no keel over it, the rule bracer.py follows;
#   * the CARD side carries 1.8 mm of card in the band that is clear anyway, so
#     it is tray plus a closing skin and nothing else.
body = bbox(-HW, HW, TRAY_Y0, TRAY_Y0 + TRAY_Y, 0.0, OUT_H)      # the tray
body += bbox(-HW, -PACK_X_IN + 3.0, 0.0, BODY_Y, PACK_FLOOR, 0.0)  # pack wing
body += bbox(-PACK_X_IN + 3.0, HW, 0.0, BODY_Y,
             CARD_FLOOR - WALL_OUT, 0.0)                          # card side
body += arm_cyl(R_CUFF) & bbox(-HW, HW, 0.0, BODY_Y, -80.0, 0.0)  # the cuff
body -= bbox(-HW - 1, HW + 1, -1, BODY_Y + 1, -80.0,
             ARM_CZ + R_CUFF * math.cos(math.radians(WRAP)))       # wrap stops

# ---- hollow the wing and the card side ------------------------------------
body -= bbox(-HW + WALL_OUT, -PACK_X_IN + 1.0, WALL_OUT, BODY_Y - WALL_OUT,
             PACK_FLOOR + WALL_OUT, -WALL_OUT)
body -= bbox(-PACK_X_IN + 5.0, HW - WALL_OUT, WALL_OUT, BODY_Y - WALL_OUT,
             CARD_FLOOR - WALL_OUT + 1.0, -WALL_OUT)

# ---- the payload pockets themselves ---------------------------------------
body -= bbox(-PACK_X_OUT, -PACK_X_IN, (BODY_Y - PACK_L) / 2 - 0.5,
             (BODY_Y + PACK_L) / 2 + 0.5, PACK_Z0, PACK_Z1)
body -= bbox(CARD_X_IN, CARD_X_OUT, (BODY_Y - CARD_L) / 2 - 0.5,
             (BODY_Y + CARD_L) / 2 + 0.5, CARD_Z0, CARD_Z1)

# ------------------------------------------------------- the frozen housing
body -= bbox(-POCK_L / 2, POCK_L / 2, TRAY_Y0 + WALL, TRAY_Y0 + WALL + POCK_W,
             FLOOR, OUT_H + 1)                                    # pocket
# screen aperture: the phone lies with its LENGTH along X, so the display's
# 113.5 mm runs across the arm and its 62.8 along it.
body -= bbox(-SCREEN_H / 2, SCREEN_H / 2,
             BODY_Y / 2 - SCREEN_W / 2, BODY_Y / 2 + SCREEN_W / 2,
             FLOOR + POCK_D - EPS, OUT_H + GUARD_H + 1)
for _y0, _y1 in ((TRAY_Y0 + WALL, TRAY_Y0 + WALL + LIP_SIDE),
                 (TRAY_Y0 + WALL + POCK_W - LIP_SIDE,
                  TRAY_Y0 + WALL + POCK_W)):                      # retaining lip
    body += bbox(-POCK_L / 2, POCK_L / 2, _y0, _y1, FLOOR + POCK_D, OUT_H)

# ------------------------------------------------------------------- guard
# Three sides, open on the INBOARD long edge where his eye is -- the same rule
# as portrait, rotated with the phone.
GH = OUT_H + GUARD_H
body += bbox(-HW, HW, 0.0, GUARD_W, OUT_H, GH)                  # outboard edge
body += bbox(-HW, -HW + GUARD_W, 0.0, BODY_Y, OUT_H, GH)        # the two ends
body += bbox(HW - GUARD_W, HW, 0.0, BODY_Y, OUT_H, GH)

# --------------------------------------------------------------- strap bands
for _yc in (13.5, BODY_Y - 13.5):
    body -= arm_cyl(ARM_CUT_R + STRAP_D, STRAP_W, _yc)

body -= arm_cyl(ARM_CUT_R)          # the arm itself, FOAM proud, cut last

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(out, exist_ok=True)
export_step(body, os.path.join(out, "landscape.step"))
export_stl(body, os.path.join(out, "landscape.stl"))
export_stl(Pos(0, 0, BODY_Y) * Rot(-90, 0, 0) * body,
           os.path.join(out, "landscape_print.stl"))

bb = body.bounding_box()
standoff = OUT_H + GUARD_H + GAP + FOAM
print(f"envelope   {bb.size.X:.1f} across x {bb.size.Y:.1f} along x "
      f"{bb.size.Z:.1f} tall")
print(f"standoff   {standoff:.1f} mm skin to crest  (GAP {GAP}, TILT 0 -- no "
      f"tilt credit)")
print(f"overhang   {(bb.size.X - 2 * ARM_CUT_R) / 2:.1f} mm of slab off EACH "
      f"side of a {2 * ARM_CUT_R:.0f} mm arm")
print(f"pack wing  |x| {PACK_X_IN:.1f}..{PACK_X_OUT:.1f}   cards x "
      f"{CARD_X_IN:.1f}..{CARD_X_OUT:.1f}   tray edge {HW:.1f}")
print(f"volume     {body.volume / 1000:.1f} cm3  ~= "
      f"{body.volume / 1000 * 1.27:.0f} g PETG   (massing only: no "
      f"tessellation, cap or plungers)")
