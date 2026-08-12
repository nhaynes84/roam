"""
ROAM Touch -- forearm bracer cradle for a Google Pixel (sailfish, 2016).

Form: the phone housing (pocket, screen aperture, sensor holes, print-in-place
buttons, jack notch) is a frozen tray. Around and under it sits a FACETED OUTER
HULL that encloses the tilt wedge -- one low-poly prism running the length of
the arm, flush with the tray sides at the belt line and flaring out below it,
hollowed to a 2 mm skin with the arm saddle cut through its underside. V1 left
that wedge open on two ribs and read as a tray on stilts.

The END CAP is part of the same body, not a collar bolted to it: the hull's
nose steps in by the cap's wall thickness below the belt line, so the cap's
outer surface IS the hull's section and the joint has no step in it.

The hollow under the tray carries TWO ID-1 CARDS (a bank card and a licence),
in a channel formed by two C-rails hung from the tray floor. They load from
the elbow end and the cap is what retains them.

★ Every hull facet is a plane PARALLEL TO THE ARM AXIS. That is what makes the
low-poly styling free: stood on end, the entire outer body is vertical, so it
needs no support and there is nothing curved to tessellate.

Print orientation: STANDING ON THE HAND END, on a brim. Measured, not guessed --
verify_bracer.py scores five orientations by unsupported face area, and the
hand end wins on both support and bed contact because the hull's closed end is
down there and the cavity opens upward at the nose. (⚠️ the two end-on rotations
were labelled backwards until 2026-08-12; -pi/2 about X is the HAND end.)

Geometry note -- the constraint that drives the shape:
a ~75 mm wide flat tray on a 90 mm diameter forearm has ~20 mm of sagitta, and
the 20 deg tilt adds its own. That wedge is unavoidable for a rigid slab. What
is optional is whether it is solid: as a 2 mm shell it costs about what the two
open ribs did, and the void inside is the duct the floor vents exhaust into.

ARM_R is nominal, NOT critical, and that is deliberate. Every arm face is cut
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

# ★ Screen tilt. Worn flat on the forearm the display points at the ceiling,
# so you have to rotate your whole arm to read it. Tilting the tray relative
# to the arm puts it in your eyeline at rest.
# Implemented by tilting the ARM CUT rather than the tray: the tray, pocket
# and every aperture stay in a clean axis-aligned frame, and only the rib
# profile changes. Rotating the tray instead would drag every feature with it.
# ⚠️ HANDED. Positive drops the +X (button) side, so the screen faces across
# the body -- correct for one arm and wrong for the other. Flip the sign for
# the other forearm.
TILT = 20.0          # degrees

ARM_R = 45.0         # nominal forearm radius, mm (90 mm dia)
GAP = 8.0            # air gap between arm and tray underside, at the crown
FOAM = 4.0           # compliant pad thickness on EVERY arm face -- see below
STRAP_Y = (34.0, 112.0)  # strap channel centres, from the elbow (open) end

# ------------------------------------------------------------------- hull
# ★ The outer body. V1 carried the tray on two open saddle ribs; the tilt
# wedge was left as exposed structure and it read as a tray on stilts. This
# is the same wedge, enclosed: one faceted prism running the length of the
# arm, flush with the tray sides at the belt line and flaring out below it.
#
# LOW POLY IS NOT ONLY STYLING. Every facet is a plane parallel to the arm
# axis, so the whole skin is vertical in the print orientation below -- no
# overhang anywhere on the outer body, and nothing to tessellate.
#
# The section is HANDED, like TILT: the arm falls away from the +X (button)
# side, so that flank is deep and mostly dead volume, while the -X flank
# meets the arm within ~13 mm. All of it is derived from arm_z() so TILT
# stays a real knob -- change it and the section follows.
HULL_HW = 40.0       # hull half width at the widest -- 2.4 mm proud of the tray
HULL_SHOULDER = 2.0  # Z where the flank leaves the tray wall and rakes out
HULL_BELT = -3.0     # Z of the shoulder crease
HULL_KEEL = 24.0     # |X| where the keel facet turns up into the deep chine
HULL_CHINE = 11.0    # how far up the deep flank that chine lands
WALL_OUT = 2.0       # outer skin thickness
# ⚠️ Two arm-face wall thicknesses, not one. A single generous value leaves the
# shallow flank almost solid -- that flank is only 5-13 mm deep, so 4.5 mm of
# wall eats most of it. A thin skin everywhere plus a thick band under each
# strap channel gets the weight back and still leaves 2.4 mm of floor beneath
# the webbing. The step between them is a plane, so it cannot feather.
# ⚠️ 2.0, not 2.4. At 2.4 the cavity floor rises to within 0.97 mm of the
# card channel at the arm crown and leaves a membrane between them that the
# wall check sat right on the limit of. 2.0 opens that to ~1.4 mm.
WALL_ARM = 2.0       # arm-face skin over the open span
WALL_ARM_STRAP = 4.4  # under the strap channels -- 2.2 of it is the channel
STRAP_BAND = 3.0     # how far the thick band runs past the channel
WALL_END = 3.0       # closing wall at the hand end
CAV_Y1 = 3.0         # cavity stops this far short of the hand end
LOUVER_W = 4.0       # exhaust slots in the deep (+X) flank
LOUVER_Y = (56.0, 66.0, 76.0, 132.0, 142.0)

CAP_D = 10.0         # end-cap slip depth
CAP_W = 2.0          # cap side wall
# ⚠️ 6 mm, not 2.4. The full-face trough is lofted into this plate, so a thin
# plate makes the trough meet the outer face at a feather edge at the corners.
# The answer is material, not a slicer setting: a thicker plate gives the scoop
# real depth, a proper rim, and a gentler taper that prints cleanly. It also
# suits the chunky retro-futurist read.
CAP_T = 6.0          # cap end plate
CAP_CLR = 0.30       # slip fit over the tenon
# Strap runs in a channel on the UNDERSIDE of each rib, not on side flanges.
# Flanges made the device 91 mm wide for no structural reason and were also
# what the end cap collided with. This keeps the whole thing tray-width.
STRAP_W = 26.0       # channel width along the arm, for 25 mm webbing
STRAP_D = 2.2        # channel depth into the rib's arm face
BAR_X = 20.0         # retaining bars, either side of centre
BAR_W = 6.0

# 3.5 mm jack: on the TOP edge and NOT centred -- it sits in the right-hand
# (button-side) quartile. Owner measured this off the phone; the Wikimedia SVG
# only draws the face, so the earlier centred notch was a guess and was wrong.
JACK_W = 20.0
JACK_X = 22.0        # notch centre, +X = button side

# print-in-place button plungers (see the build section)
BTN_BORE_H = 4.0     # outer bore height, Z
BTN_CB_H = 7.0       # counterbore height, Z -- the flange lives here
BTN_CB_D = 1.2       # counterbore depth into the 2.4 mm wall
BTN_CB_EXT = 3.0     # counterbore is this much longer than the button, Y
BTN_CLR = 0.35       # all-round clearance so it comes off the bed loose
BTN_PROUD = 0.6      # cap stands this far out from the shell, to find by feel
# ⚠️ Flange sits FLUSH with the pocket wall, not proud of it. The Pixel's own
# buttons protrude ~0.4 mm past the body -- about all the per-side clearance
# there is -- so a flange poking into the pocket would foul them on insertion.
# Flush means the phone's button does the reaching; travel comes from BTN_CLR.
BTN_PRESS = 0.0

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
# ⚠️ 46, not 60. The card rails hang from this same ceiling at |X| >= 24.3;
# a wider vent cuts their webs off the ceiling and leaves them floating.
VENT_W = 46.0
EPS = 0.1
# ★ Owner's finishing pass, measured off RoamTouchModded.step: 1.5 mm chamfer
# on every exterior edge. Do not lose this on the next regeneration -- it is
# most of what makes the thing read as a designed object rather than a blank.
CHAMFER = 1.5

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

# The arm cut is a cylinder rotated by TILT about (0, -(GAP+FOAM)) on the tray
# centre line. Closed form for its axis, and for the height of its surface at
# any X -- the hull section is built off this so TILT stays parametric.
_T = math.radians(TILT)
ARM_CX = -ARM_R * math.sin(_T)
ARM_CZ = -(GAP + FOAM) - ARM_R * math.cos(_T)


def arm_z(x, r=None):
    """Z of the arm-cut surface at X, or None where the cylinder does not
    reach. Material lives ABOVE this line."""
    r = ARM_CUT_R if r is None else r
    d = r ** 2 - (x - ARM_CX) ** 2
    return ARM_CZ + math.sqrt(d) if d > 0 else None


# Deep (+X) flank: the arm has fallen away entirely by the time it gets out
# there, so the depth is set by the tilt, not by the cylinder.
HULL_Z_DEEP = -(GAP + FOAM) - HULL_HW * math.sin(abs(_T))
# Shallow (-X) flank: run it just past where the arm cut will form the edge,
# so the cylinder makes that chine rather than a stray sliver of blank.
_shallow = arm_z(-HULL_HW if TILT >= 0 else HULL_HW)
HULL_Z_SHAL = (_shallow - 1.5) if _shallow is not None else HULL_Z_DEEP
SAG = -HULL_Z_DEEP    # how far the hull hangs below the tray


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


def inset(pts, d):
    """Mitred inward offset of a simple polygon by d.

    Hand-rolled rather than a 2D offset op because a mitre keeps every corner
    SHARP -- an arc-filleted offset would round the inside of the shell and
    make the wall thicker than d at every crease, which is exactly where a
    minimum-wall check needs to be able to trust the number. Every facet ends
    up exactly d thick, measured perpendicular to itself.
    """
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
               for i in range(n)) / 2.0
    s = 1.0 if area > 0 else -1.0          # interior is left of each edge if CCW
    lines = []
    for i in range(n):
        (x0, z0), (x1, z1) = pts[i], pts[(i + 1) % n]
        ex, ez = x1 - x0, z1 - z0
        ln = math.hypot(ex, ez)
        nx, nz = -ez / ln * s, ex / ln * s
        lines.append((x0 + nx * d, z0 + nz * d, ex, ez))
    out = []
    for i in range(n):
        px, pz, ex, ez = lines[i - 1]
        qx, qz, fx_, fz_ = lines[i]
        den = ex * fz_ - ez * fx_
        if abs(den) < 1e-9:
            out.append((qx, qz))
            continue
        t = ((qx - px) * fz_ - (qz - pz) * fx_) / den
        out.append((px + ex * t, pz + ez * t))
    return out


def prism(pts, y0, y1):
    """Extrude an (X, Z) polygon along +Y. Plane.XZ maps local u,v -> X,Z and
    its normal is -Y, so the extrude amount is negated to travel +Y."""
    return Pos(0, y0, 0) * extrude(Plane.XZ * Polygon(*pts, align=None),
                                   amount=-(y1 - y0))


# ------------------------------------------------------------------ build
# Tray body: Y = 0 at the elbow (open) end, Y = OUT_L at the hand end.
part = bbox(-OUT_W / 2, OUT_W / 2, 0, OUT_L, 0, OUT_H)


# ------------------------------------------------------------------- hull
# The faceted outer body. SD is the deep side -- the flank the arm falls away
# from, which is +X for a positive TILT and swaps with it.
SD = 1.0 if TILT >= 0 else -1.0
HULL_SEC = [
    (-SD * OUT_W / 2,  HULL_SHOULDER),   # leaves the tray wall here
    (-SD * HULL_HW,    HULL_BELT),       # shallow shoulder crease
    (-SD * HULL_HW,    HULL_Z_SHAL),     # shallow flank, ends at the arm
    (-SD * 8.0,        HULL_Z_DEEP),     # underbody rake
    ( SD * HULL_KEEL,  HULL_Z_DEEP),     # keel
    ( SD * HULL_HW,    HULL_Z_DEEP + HULL_CHINE),  # deep lower chine
    ( SD * HULL_HW,    HULL_BELT),       # deep flank
    ( SD * OUT_W / 2,  HULL_SHOULDER),
]

# ★★ The nose is a TENON, not a stub. V1 stopped the hull 13 mm short so the
# old rectangular cap could collar the bare tray -- which left the cap reading
# as a different object bolted onto a faceted body, with an open step at the
# joint. Now the hull runs the whole length and the last CAP_D of it is stepped
# IN by the cap's wall thickness, below the belt line only. The cap's collar
# fills that step, so its outer surface is the hull's own section, continuous.
#
# ⚠️ Below the belt only. Above it the section is flush with the tray wall,
# and the tray wall is 2.4 mm of frozen pocket -- there is nothing there to
# rebate. So the belt crease IS the cap's top edge, which is why the joint
# disappears: the surface turns inward at exactly the line where the cap ends.
TEN_D = CAP_W + CAP_CLR              # how far the tenon steps in
_above = bbox(-80, 80, -1, CAP_D + 1, HULL_BELT, 80)
_below = bbox(-80, 80, -1, CAP_D + 1, -80, HULL_BELT)

hull = prism(HULL_SEC, CAP_D, OUT_L)
hull += prism(HULL_SEC, 0, CAP_D) & _above
hull += prism(inset(HULL_SEC, TEN_D), 0, CAP_D) & _below

part += hull

# Carve the forearm (plus the foam allowance) out of the hull.
_pivot = -(GAP + FOAM)          # crown contact, on the tray centre line
_tilt = Pos(0, 0, _pivot) * Rot(0, TILT, 0) * Pos(0, 0, -_pivot)
arm = _tilt * (Pos(0, OUT_L / 2, ARM_AXIS_Z) * Rot(90, 0, 0) * Cylinder(
    ARM_CUT_R, OUT_L + 60
))
part -= arm

# Strap channel: a second, larger cylinder over just a band of the arm face
# carves a transverse groove. The webbing lies in there, between hull and arm,
# and wraps the forearm -- no flanges, no threading. On the deep side the arm
# has already fallen below the keel by X ~= 25, so the strap walks out into
# open air under the hull rather than needing a slot cut for it.
for y in STRAP_Y:
    part -= _tilt * (Pos(0, y, ARM_AXIS_Z) * Rot(90, 0, 0) * Cylinder(
        ARM_CUT_R + STRAP_D, STRAP_W))

# Retaining bars across the channel so the strap cannot fall out when it is
# off your arm. Trimmed back to the arm surface by re-cutting the arm after.
for y in STRAP_Y:
    for sx in (-1, 1):
        part += bbox(sx * BAR_X - BAR_W / 2, sx * BAR_X + BAR_W / 2,
                     y - STRAP_W / 2, y + STRAP_W / 2,
                     -SAG - 1, 0)
part -= arm

# ------------------------------------------------------------------- shell
# ★ The wedge is dead volume, so hollow it. The cavity is the same faceted
# section inset by WALL_OUT, bounded away from the arm face by WALL_ARM (which
# leaves 2.8 mm under the strap channel) and left OPEN at the nose -- a closed
# cavity would put an unsupported roof across the whole section at the top of
# the print, and an open one is also the intake for the floor vents.
cav = prism(inset(HULL_SEC, WALL_OUT), CAP_D, OUT_L - CAV_Y1)
# Over the tenon the skin has to be measured off the STEPPED-IN face, or the
# cavity would sit outside it and the tenon wall would come out negative.
cav += prism(inset(HULL_SEC, WALL_OUT), -1.0, CAP_D) & _above
cav += prism(inset(HULL_SEC, TEN_D + WALL_OUT), -1.0, CAP_D) & _below
cav -= _tilt * (Pos(0, OUT_L / 2, ARM_AXIS_Z) * Rot(90, 0, 0) * Cylinder(
    ARM_CUT_R + WALL_ARM, OUT_L + 60))
for y in STRAP_Y:
    cav -= _tilt * (Pos(0, y, ARM_AXIS_Z) * Rot(90, 0, 0) * Cylinder(
        ARM_CUT_R + WALL_ARM_STRAP, STRAP_W + 2 * STRAP_BAND))

# ------------------------------------------------------------- card slots
# ★ ID-1 cards (ISO/IEC 7810: 85.60 x 53.98 x 0.76) in the dead volume.
# A card is 54 mm across and the ONLY place in this section with 54 mm of
# clear span is the slab directly under the tray floor: above Z ~= -2.9 the
# arm cut has fallen away entirely, so the cavity runs the full width there.
# Everywhere else -- the deep flank void, the chine, the keel -- the section
# is under 26 mm and no orientation of a card fits. So: one channel, flat,
# under the floor, holding two cards.
#
# The channel is a pair of C-rails hung from the cavity ceiling rather than a
# closed pocket. A pocket would need a floor spanning 54 mm and that floor is
# 5 cm3 of PETG for no structural return; the rails only need to catch the
# card's two long edges. They are prismatic along Y, so they cost nothing in
# the print orientation.
CARD_L, CARD_W, CARD_T = 85.60, 53.98, 0.76
CARD_N = 2                 # cards carried
CARD_CLR = 0.35            # per side around the card
CARD_RAIL = 5.0            # web outboard of the card edge
CARD_ENG = 2.5             # how far the ledge reaches under the card
CARD_LEDGE = 1.4           # ledge thickness -- this is what carries the card
CARD_STOP = 2.0            # back stop so a card cannot vanish up the cavity
# ⚠️ The channel height is NOT free. Over each strap band the floor of this
# channel is also the roof of the strap channel, and the crown of the arm cut
# sits 3.09 mm below the tray floor there -- so every mm of card channel comes
# straight off that membrane. 0.30 of slack leaves it 1.27 mm; more slack and
# the wall check fails. Two flat ID-1 cards fit; an EMBOSSED bank card is
# thicker than 0.76 at the digits and will only go in on its own.
CARD_SLACK = 0.30          # total, over the whole stack
CARD_SW = CARD_W + 2 * CARD_CLR
CARD_SH = CARD_N * CARD_T + CARD_SLACK
CARD_X0, CARD_X1 = -CARD_SW / 2, CARD_SW / 2
CARD_Y1 = CARD_L + 1.0
_card_z0 = -(CARD_SH + CARD_LEDGE)

# keep these solid -- subtract them from the cavity before the cavity is cut
for _xa, _xb in ((CARD_X0 - CARD_RAIL, CARD_X0 + CARD_ENG),
                 (CARD_X1 - CARD_ENG, CARD_X1 + CARD_RAIL)):
    cav -= bbox(_xa, _xb, -1.0, CARD_Y1 + CARD_STOP, _card_z0, 0.0)
cav -= bbox(CARD_X0, CARD_X1, CARD_Y1, CARD_Y1 + CARD_STOP, _card_z0, 0.0)

part -= cav
part -= bbox(CARD_X0, CARD_X1, -10.0, CARD_Y1, -CARD_SH, 0.0)

# Exhaust louvres in the deep flank -- the only way out for the air the floor
# vents dump into the cavity, and the facet that keeps the flank from reading
# as a slab. Raked, and clear of the strap bands and the button bay.
_lv_z0, _lv_z1 = HULL_Z_DEEP + HULL_CHINE, HULL_BELT   # the deep flank's span
for _ly in LOUVER_Y:
    part -= Pos(SD * HULL_HW, _ly, (_lv_z0 + _lv_z1) / 2) * Rot(-18, 0, 0) \
        * Box(30.0, LOUVER_W, (_lv_z1 - _lv_z0) - 5.0)

# Phone pocket -- runs out the elbow end so the phone slides in
part -= bbox(-POCK_W / 2, POCK_W / 2, -10, POCK_L, FLOOR, FLOOR + POCK_D)

# Screen aperture. This is the bezel: the face closes down to the display
# instead of exposing the phone's own bezel, so the housing reads as the
# device rather than as a tray with a phone in it.
# Lofted, not a straight cut: the aperture is BEZEL_CHAM wider at the top face
# and closes down to the display, so the bezel slopes into the screen instead
# of standing over it as a lip. Owner's change, brought back into the source.
BEZEL_CHAM = 1.5
part -= loft([
    Plane(origin=(0, (WIN_Y0 + WIN_Y1) / 2, FLOOR + POCK_D))
    * Rectangle(2 * WIN_X, WIN_Y1 - WIN_Y0),
    Plane(origin=(0, (WIN_Y0 + WIN_Y1) / 2, OUT_H))
    * Rectangle(2 * (WIN_X + BEZEL_CHAM), (WIN_Y1 - WIN_Y0) + 2 * BEZEL_CHAM),
])
part -= bbox(-(WIN_X + BEZEL_CHAM), WIN_X + BEZEL_CHAM,
             WIN_Y0 - BEZEL_CHAM, WIN_Y1 + BEZEL_CHAM, OUT_H - EPS, OUT_H + 10)

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

# ---------------------------------------------- print-in-place buttons
# Power (upper) and volume (lower) on the right edge (+X).
#
# A captured PLUNGER, not a flexure. A cantilever hinge would fatigue and,
# worse, its layer lines land perpendicular to the bending axis in most
# orientations -- that is the delamination direction and it would snap. A
# plunger has no hinge to fatigue and does not care which way the part is
# printed. It prints loose inside its bore and stays captive:
#   * outward -- the flange is larger than the outer bore, it cannot pass
#   * inward  -- the phone's own edge stops it
# The flange IS the pad that presses the phone's button; no separate stem.
# Needs support under the counterbore shoulder. That is fine: print
# orientation should not get to dictate the mechanism.
X_POCK = POCK_W / 2                # pocket wall, inner face
X_OUT = OUT_W / 2                  # pocket wall, outer face
Z_BTN = FLOOR + POCK_D / 2         # button centre line, mid phone thickness

for (_b0, _b1) in (PWR_SVG, VOL_SVG):
    y0, y1 = fy(_b1), fy(_b0)      # SVG runs top-down, model runs bottom-up
    yc, ylen = (y0 + y1) / 2, (y1 - y0)

    # outer bore (stem passes through) and inner counterbore (holds flange)
    part -= bbox(X_POCK + BTN_CB_D, X_OUT + EPS,
                 yc - ylen / 2, yc + ylen / 2,
                 Z_BTN - BTN_BORE_H / 2, Z_BTN + BTN_BORE_H / 2)
    part -= bbox(X_POCK - EPS, X_POCK + BTN_CB_D,
                 yc - (ylen + BTN_CB_EXT) / 2, yc + (ylen + BTN_CB_EXT) / 2,
                 Z_BTN - BTN_CB_H / 2, Z_BTN + BTN_CB_H / 2)

    # the plunger itself, floating in that void with BTN_CLR all round
    c = BTN_CLR
    flange = bbox(X_POCK - BTN_PRESS, X_POCK + BTN_CB_D - c,
                  yc - (ylen + BTN_CB_EXT) / 2 + c, yc + (ylen + BTN_CB_EXT) / 2 - c,
                  Z_BTN - BTN_CB_H / 2 + c, Z_BTN + BTN_CB_H / 2 - c)
    stem = bbox(X_POCK + BTN_CB_D - c, X_OUT + BTN_PROUD,
                yc - ylen / 2 + c, yc + ylen / 2 - c,
                Z_BTN - BTN_BORE_H / 2 + c, Z_BTN + BTN_BORE_H / 2 - c)
    part += flange + stem

# 3.5 mm headphone jack notch, hand end
part -= bbox(
    JACK_X - JACK_W / 2, JACK_X + JACK_W / 2,
    OUT_L - WALL - EPS, OUT_L + 10,
    FLOOR + 0.8, OUT_H + 10,
)

# Floor vents (cooling + weight). They now open into the hull cavity, which is
# open at the nose -- so the floor under the phone breathes into a duct that
# exhausts through the flank louvres instead of into a blind box.
for (yc, ln, vw) in ((24.0, 26.0, VENT_W), (73.0, 50.0, VENT_W),
                     (135.0, 18.0, 60.0)):   # aft of the card rails
    vent = extrude(RectangleRounded(vw, ln, VENT_R), amount=FLOOR + 4)
    # ⚠️ The vent starts just BELOW the cavity ceiling, not 2 mm below it. The
    # old -2.0 was reaching into open air; now there is a hull under here and
    # the extra 1.6 mm was being taken out of the arm-face skin. Under a strap
    # band that left 1.05 mm of wall over the channel -- found by the minimum
    # wall check, not visible in any render.
    part -= Pos(0, yc, -0.4) * vent


# ------------------------------------------------------- elbow end cap
# The phone slides in at the elbow end, so without this it can slide out --
# the strap is otherwise the only thing stopping it. REMOVABLE, not glued:
# it is the service access. A U-section that slips over the outside of the
# tray and snaps into two dimples, so nothing intrudes into the pocket
# (there is only 0.4 mm per side in there) and no tool is needed.
#
# ⚠️ USB-C is on this same end, so the cap carries a cable aperture. Without
# it you would unclip the cap every time you charged, which is how a
# removable part becomes a lost part.
CAP_BUMP_R = 1.6     # snap dome radius
CAP_DIMPLE_D = 0.7   # how deep the dome sinks into the tenon flank
CAP_BUMP_Y = 7.0     # dome centre, out near the collar's free end
CAP_SLOT_W = 1.4     # relief slot freeing the deep flank from the chine fold
CAP_SLOT_ROOT = 2.5  # slot stops this far from the plate, leaving the root
CAP_RAKE = 8.0       # plan-view rake across the plate's CAP_T of depth
# USB-C plug shell is 8.34 x 2.56 mm with fully rounded ends. Cut that SHAPE
# with ~1 mm of clearance, not a generic rectangle -- the taper does the work
# of accommodating fat overmoulds, so the opening itself can be tight.
USB_W, USB_H = 9.4, 3.6
USB_Z = FLOOR + PH_T / 2   # port sits mid phone thickness, NOT near the floor
# ★ Flare the cable aperture out on the OUTER face and taper it down to size.
# The end plate is only CAP_T thick, so a plain rectangular hole means only a
# slim cable head ever reaches the port -- a funnel lets fat overmoulds seat,
# and it reads as a designed feature instead of a punched hole.
USB_FLARE = 5.0            # per side, so a ~10 mm spread down to the opening
# ⚠️ The trough must stop SHORT of the plate's inner face, not run out to it.
# Landing the taper exactly on the far face makes the scoop meet the slot
# asymptotically -- a feather edge, measured at 0.01 mm by the wall check.
# This leaves a straight land at the throat, so the taper ends on material.
USB_LAND = 2.0             # straight throat before the plate breaks through
# Speaker and mic sit either side of the USB port on the bottom edge. Blocking
# them with a solid plate would muffle the one output the device has.
SPK_W, SPK_H = 13.0, 2.6
SPK_X = 17.0               # centre offset either side of the port
# ★ Retro-futurist: the flare is not an oval around the port, it is a trough
# spanning the whole face with the port at its centre. The loft tapers to
# nothing at the edges, so it never breaches the 2.4 mm plate -- it reads as a
# machined scoop rather than a punched hole with a chamfer round it.
# ⚠️ The mouth is centred on the FACE, the port is not: the cap face spans
# Z -CAP_CLR..OUT_H+CAP_CLR+CAP_W (centre 7.7) while USB_Z is 6.45. Centring
# the mouth on the port left 3.75 mm at the top and 1.25 at the bottom, which
# reads as a mistake. Lofting a face-centred mouth to a port-centred throat
# skews it slightly, which is the intent.
TROUGH_INSET = 0.8         # margin left all round -- near edge to edge

# ---------------------------------------------------- the cap's section
# ★★ The cap's OUTER SURFACE IS THE HULL'S SECTION. V1's cap was a rectangular
# collar sized to the bare tray, butted against a faceted body with a belt
# line, chines and a raked nose -- it read as a different object bolted on, and
# there was an open step at the joint. Now:
#   * below the belt the hull steps in by TEN_D and the collar fills that step,
#     so the outer surface runs straight through the joint with no change of
#     width and no ledge;
#   * the belt crease is the collar's top edge -- the surface turns inward at
#     exactly the line where the cap stops, so the seam lands on a feature
#     instead of in the middle of a flat face;
#   * above the belt the cap is end plate only, flush with the tray's own walls
#     and its top face. V1's collar stood 2.3 mm proud of the screen; it does
#     not any more, because there is nothing to rebate in a 2.4 mm pocket wall.
# ⚠️ The collar is a C, open on the arm side, cut by the SAME arm cylinder as
# the hull. So it takes nothing out of the 4 mm compliant-pad relief -- its
# arm-side edges lie exactly on the hull's own saddle.
CAP_SEC_IN = inset(HULL_SEC, CAP_W)      # bore; TEN_D - CAP_W = CAP_CLR clear
_cap_below = bbox(-80, 80, -CAP_T - 1, CAP_D + 1, -80, HULL_BELT)

# Flank Z spans, per side. ⚠️ HANDED -- the shallow flank is ~9 mm tall and the
# deep one ~12, so the snap features are placed per flank, never mirrored.
_sh_bot = arm_z(-SD * HULL_HW)
if _sh_bot is None:
    _sh_bot = HULL_Z_SHAL
FLANKS = ((-SD, (HULL_BELT + _sh_bot) / 2),
          (SD, (HULL_BELT + HULL_Z_DEEP + HULL_CHINE) / 2))

# Dimples in the TENON's flanks now, not the tray's. TRUNCATED CONES, not
# cylinders and not spheres: a cylinder presents a sharp edge square to the
# travel direction and will not go on at all, while a sphere rams a curved
# surface into a flat one and OCCT emits a non-manifold shell there (verified
# -- removing the spheres took both parts from 378 broken faces to zero).
for _sd, _zc in FLANKS:
    _sx = 1 if _sd > 0 else -1
    part -= Pos(_sx * (HULL_HW - TEN_D + 0.2), CAP_BUMP_Y, _zc) \
        * Rot(0, -90 * _sx, 0) \
        * Cone(1.8, 1.0, CAP_DIMPLE_D + 0.2,
               align=(Align.CENTER, Align.CENTER, Align.MIN))

# Collar: the wall between the tenon and the full section, below the belt.
cap = (prism(HULL_SEC, 0.0, CAP_D) & _cap_below) \
    - prism(CAP_SEC_IN, -EPS, CAP_D + EPS)
# End plate: the whole face -- hull section below, tray section above.
cap += prism(HULL_SEC, -CAP_T, 0.0)
cap += bbox(-OUT_W / 2, OUT_W / 2, -CAP_T, 0.0, 0.0, OUT_H)
# ⚠️ The saddle runs through the cap too. Without this the plate would close
# off the elbow end of the arm channel and sit on the forearm.
cap -= arm

# Plan-view rake on the nose corners, carried over from the hull's nose (the
# hull no longer has one -- the cap IS the nose now). A cut plane containing Z
# has no Z in its normal, so it costs nothing in the print orientation, and it
# is sized to finish exactly at Y=0 so it never reaches the collar and cannot
# skin the corner off a 2 mm wall.
for _sx in (-1, 1):
    _n = Vector(_sx * CAP_T, -CAP_RAKE, 0).normalized()
    _p0 = Vector(_sx * (HULL_HW - CAP_RAKE), -CAP_T, 0)
    cap -= Pos(_p0 + _n * 100.0) \
        * Rot(0, 0, math.degrees(math.atan2(_n.Y, _n.X))) * Box(200, 200, 200)

# Cable aperture: a USB-C-shaped slot through the plate, flared on the outside
# and tapered down to it so any head can find the port behind the plate.
cap -= Pos(0, -CAP_T - EPS, USB_Z) * Rot(-90, 0, 0) * extrude(
    RectangleRounded(USB_W, USB_H, USB_H / 2 - 0.01),
    amount=CAP_T + CAP_D + 2 * EPS)
# ⚠️ x_dir is pinned. Without it the plane picks its own axes and the flare
# comes out rotated 90 deg -- wide where the cap is thin, and it eats the plate.
# ⚠️ Built as a LOFT, not extrude(taper=). OCCT's extrude_taper throws
# Standard_TypeMismatch on a rounded profile at this angle (~64 deg).
# The trough now spans the TRAY's part of the face rather than the whole of it:
# the face is 39 mm tall in the new section and most of the lower half is hull
# wedge that the saddle cuts away, so a full-face scoop would run off the edge.
# Over the tray it is very nearly centred on the port, which also retires the
# deliberate skew the old rectangular face needed.
_trough_hw = OUT_W / 2 - TROUGH_INSET
_trough_h = OUT_H - 2 * TROUGH_INSET
cap -= loft([
    Plane(origin=(0, -CAP_T - EPS, OUT_H / 2), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
    * RectangleRounded(2 * _trough_hw, _trough_h, 2.0),
    Plane(origin=(0, -USB_LAND, USB_Z), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
    * RectangleRounded(USB_W, USB_H, USB_H / 2 - 0.01),
])
# Speaker / mic apertures either side of the port, through the plate.
for _sx in (-1, 1):
    cap -= Pos(_sx * SPK_X, -CAP_T - EPS, USB_Z) * Rot(-90, 0, 0) * extrude(
        RectangleRounded(SPK_W, SPK_H, SPK_H / 2 - 0.01), amount=CAP_T + 2 * EPS)

# ★ No relief slots on the shallow side, and no tongues. The collar is a C, so
# each flank is ALREADY a cantilever: bounded by the belt above, by the saddle
# below, free at the open end, and rooted only in the end plate. V1 needed
# tongues because its collar was a closed rectangle braced on four sides.
# The deep side does need one slot -- there the collar wraps flank, chine and
# keel into a folded section stiff enough to resist the 0.3 mm the dome has to
# ride, so this frees the flank from the fold.
cap -= bbox(SD * (HULL_HW - CAP_W) - 0.2 if SD > 0 else SD * HULL_HW - 0.2,
            SD * HULL_HW + 0.2 if SD > 0 else SD * (HULL_HW - CAP_W) + 0.2,
            CAP_SLOT_ROOT, CAP_D + EPS,
            HULL_Z_DEEP + HULL_CHINE + 1.28,
            HULL_Z_DEEP + HULL_CHINE + 1.28 + CAP_SLOT_W)

# Snap noses: cones rooted inside the wall (never coplanar with a face) and
# protruding 0.6 mm past the inner surface, so they stand 0.3 mm proud of the
# tenon and seat into its dimples. Sat near the free end so the cantilever is
# as long as the collar allows -- the strain at the root goes as 1/L^2.
for _sd, _zc in FLANKS:
    _sx = 1 if _sd > 0 else -1
    cap += Pos(_sx * (HULL_HW - CAP_W / 2), CAP_BUMP_Y, _zc) \
        * Rot(0, -90 * _sx, 0) \
        * Cone(1.8, 0.9, CAP_W / 2 + 0.6,
               align=(Align.CENTER, Align.CENTER, Align.MIN))

# ------------------------------------------------------- edge treatment
# Chamfer the outer envelope only: edges lying on the side walls, the top
# face or the underside. Feature edges (pocket, apertures, channel, plungers)
# are deliberately left sharp -- chamfering those would eat clearances.
# ⚠️ The hull creases are NOT rounded -- a chamfer on a facet crease is just a
# third facet, so the low-poly read survives, but a fillet would not. They get
# a smaller chamfer than the tray rim so the crease still reads as a crease.
CREASE = 1.0


def _is_crease(e):
    """A long Y-running edge sitting on one of the hull section's corners."""
    c = e.center()
    if e.length < 30 or c.Z > HULL_SHOULDER - 0.5:
        return False
    return any(abs(c.X - vx) < 0.3 and abs(c.Z - vz) < 0.3 for vx, vz in HULL_SEC)


# OCCT refuses the whole envelope in one operation (ValueError), so chamfer in
# groups. Each group is attempted independently so one awkward set cannot lose
# the others.
_groups = [
    # Only the OUTER boundary of the top face. Filtering on Z alone also
    # catches the screen aperture and button openings, and OCCT refuses the
    # mixed set outright.
    ("tray top rim", CHAMFER,
     lambda e: abs(e.center().Z - OUT_H) < 0.02 and (
         abs(abs(e.center().X) - OUT_W / 2) < 0.02
         or abs(e.center().Y - OUT_L) < 0.02)),
    ("hull creases", CREASE, _is_crease),
]
for _name, _len, _pred in _groups:
    _es = ShapeList([e for e in part.edges() if _pred(e)])
    if not _es:
        print(f"chamfer    no edges matched ({_name})")
        continue
    try:
        part = chamfer(_es, length=_len)
        print(f"chamfer    {_len} mm on {len(_es):3d} edges  ({_name})")
    except Exception:
        # OCCT refuses mixed sets with no useful message. Retry edge by edge so
        # one awkward crease costs one crease, not the whole group. Re-select
        # each time -- chamfering changes the topology under us.
        _done = 0
        for _ in range(len(_es)):
            _cands = ShapeList([e for e in part.edges() if _pred(e)])
            _hit = False
            for _e in _cands:
                try:
                    part = chamfer(ShapeList([_e]), length=_len)
                    _done += 1
                    _hit = True
                    break
                except Exception:
                    continue
            if not _hit:
                break
        print(f"chamfer    {_len} mm on {_done:3d} edges  ({_name}, one at a time)")

# ----------------------------------------------------------------- export
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(out, exist_ok=True)
export_step(part, os.path.join(out, "bracer.step"))
export_stl(part, os.path.join(out, "bracer.stl"))
export_step(cap, os.path.join(out, "bracer_endcap.step"))
export_stl(cap, os.path.join(out, "bracer_endcap.stl"))

# ★ Also export both parts ROTATED INTO PRINT ORIENTATION, bed at Z=0. Renders
# taken off these are the ones worth looking at -- printability is judged in
# the orientation it prints in, not the one it was modelled in.
# ⚠️ Rot(-90,0,0) sends +Y to -Z, so the hand end goes to the bed. Verified
# against the bounding box below rather than assumed.
_pp = Pos(0, 0, OUT_L) * Rot(-90, 0, 0) * part
_pc = Pos(0, 0, CAP_T) * Rot(90, 0, 0) * cap
export_stl(_pp, os.path.join(out, "bracer_print.stl"))
export_stl(_pc, os.path.join(out, "bracer_endcap_print.stl"))
assert abs(_pp.bounding_box().min.Z) < 0.01, "bracer not sitting on the bed"
assert abs(_pc.bounding_box().min.Z) < 0.01, "cap not sitting on the bed"
_cbb = cap.bounding_box()
print(f"end cap    {_cbb.size.X:.1f} W x {_cbb.size.Y:.1f} L x {_cbb.size.Z:.1f} H mm"
      f"  ~= {cap.volume/1000*1.27:.0f} g")

_bb = part.bounding_box()
print(f"outer      {_bb.size.X:.1f} W x {_bb.size.Y:.1f} L x {_bb.size.Z:.1f} H mm")
print(f"tray       {OUT_W:.1f} x {OUT_L:.1f} x {OUT_H:.1f}")
print(f"pocket     {POCK_W:.1f} x {POCK_L:.1f} x {POCK_D:.1f}")
print(f"hull drop  {SAG:.2f} mm deep side, {-HULL_Z_SHAL:.2f} shallow "
      f"(TILT={TILT}, ARM_R={ARM_R}, GAP={GAP})")
print(f"volume     {part.volume/1000:.1f} cm3  ~= {part.volume/1000*1.27:.0f} g PETG")
