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

The screen sits in a WELL with a raised hood around it -- deep brow at the
elbow, shallower one at the hand, plain walls down the sides, notch through
the hand brow. Taken from the Pip-Boy 3000 in ref/. The deep flank carries
two PROUD RIBS; the cut louvres that used to be there are gone.

WORN ON THE RIGHT FOREARM, ON TOP. TILT is positive for that and the reasoning
is written out at the parameter -- do not flip it back.

Every major crease is bevelled 3 mm, in the SECTION polygons rather than with
OCCT's chamfer(), which refused most of them. verify_bracer.py audits what is
left sharp and classifies it, so the exceptions are on record.

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
BEZEL_CHAM = 1.5     # how far the aperture opens out at the top face

# ★ Screen tilt. Worn flat on the forearm the display points at the ceiling,
# so you have to rotate your whole arm to read it. Tilting the tray relative
# to the arm puts it in your eyeline at rest.
# Implemented by tilting the ARM CUT rather than the tray: the tray, pocket
# and every aperture stay in a clean axis-aligned frame, and only the rib
# profile changes. Rotating the tray instead would drag every feature with it.
# ★★ ARM: RIGHT FOREARM, WORN ON TOP. Decided 2026-08-12; this is no longer a
# placeholder. The sign follows from that and should not be flipped back.
#
# Model frame: +Y runs toward the hand, +Z out of the screen. Right-handed, so
# +X = Y x Z, and with the right arm held out in front, screen up, that puts
#   +X to the WEARER'S RIGHT, away from the body -- and -X toward the midline.
# Positive TILT moves the arm cut's axis to -X, which is the same as rolling
# the device around the arm toward +X. Worn centred, that leaves the screen
# facing up and toward -X: across the body, into the eyeline, which is exactly
# where you look when you glance down at your right forearm.
#
# So: POSITIVE = right arm. Negative would be the left, and everything handed
# in this file (the section, the deep flank, the fins) follows SD below.
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
# ⚠️ Two hard ceilings meet at HULL_SHOULDER, and neither is a style choice:
#   * the button bore runs Z 4.6..8.6 out to the tray wall, so hull material
#     above 4.5 would stand outboard of it and bury the plungers;
#   * the shell cavity is this section inset by WALL_OUT, so a shoulder above
#     WALL_OUT puts the cavity's ceiling above the tray floor and hollows the
#     floor out from underneath -- worth 17 g and a 0.6 mm floor.
# The second is the tighter one. Rake length comes from HULL_BELT instead.
HULL_SHOULDER = 2.0  # Z where the flank leaves the tray wall and rakes out
# ⚠️ It sets the length of the shoulder rake, and the rake has to be long
# enough to carry a 3 mm bevel at its lower end: bevel() caps each set-back at
# 45% of its edge, so sqrt(2.45^2 + (HULL_SHOULDER-HULL_BELT)^2) > 6.7.
HULL_BELT = -5.0     # Z of the widest crease -- also the end cap's top edge
HULL_KEEL = 24.0     # |X| where the keel facet turns up into the deep chine
HULL_CHINE = 3.0     # how far up the deep flank that chine lands
# ★ Raised ribs on the deep flank, replacing the cut louvres. The reference
# object builds its side panels out of PROUD ribs, not slots, and a rib is
# also the honest feature here: it is prismatic along the arm, so it prints
# support-free, and it stiffens the one big blank face on the part.
FIN_N = 2
FIN_H = 3.5          # rib height, Z
FIN_GAP = 3.0        # between ribs
FIN_PROUD = 1.5      # how far it stands off the flank
FIN_CH = 1.0         # 45 deg chamfer on the rib's own outer corners
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

# ------------------------------------------------------------- high guard
# ★★ A HIGH GUARD, not a brow: the screen sits down inside a deep three-sided
# surround. Measured off the owner's RoamTouchHighGuardDemo.step, which is the
# authority for the form; the numbers below are read from it, not invented.
# What his file says, in his geometry:
#   * crest at Z 28.4 -- 15.0 mm above the tray face, where ours was 5.0;
#   * outer face vertical to Z ~22.4, then bevelled in 2.5 mm to the crest;
#   * inner face hard against the aperture mouth at |X| 33.65;
#   * THREE SIDES. The deep (+X) flank has no guard at all -- that is the
#     3.11 cm3 "deep-flank cut": it is not a cut, it is a wall he never built;
#   * the crest RAMPS DOWN at 45 deg into both ends, from Y 134 at the hand
#     end and Y ~10.9 at the elbow. That ramp is what stops the guard reading
#     as an extrusion, and it is the answer to the blocky ends as well.
#
# ★ What he asked for on top of his file: the inner faces CONCAVE -- scooped
# back into the thick surround so the wall thins as it rises and its crest
# meets his outer bevel. Cut with cylinders, so it is one curved face per side
# in the STEP rather than a faceted approximation he has to clean up.
#
# What I did NOT take from his file, and why:
#   ⚠️ his hand brow starts at Y 135.3, which puts 15 mm of material over the
#      front camera and the earpiece. Those are frozen apertures; punching them
#      through a 15 mm brow would tube the camera. Ours starts at Y 141, clear
#      of the camera's outer edge at 140.5, and the brow is correspondingly
#      shorter. That is the one place his form and the housing disagree.
#   ⚠️ his elbow brow's inner face rakes at 49 deg off vertical. Printed
#      standing on the hand end that face points down and needs support; ours
#      is held to 45 deg by construction (see SCOOP_R_BROW).
GUARD_H = 15.0       # crest height above the tray face -- his 28.4 - 13.4
GUARD_HW = 41.5      # outer half width, flush with the ribs
GUARD_BEV_H = 6.0    # his outer bevel: starts this far below the crest...
GUARD_BEV_X = 2.5    # ...and takes this much off the width
GUARD_BASE_CH = 1.0  # bevel where the guard overhangs the tray's side wall
GUARD_LEDGE = 0.3    # well floor left outside the aperture mouth. ⚠️ NOT zero:
                     # landing the scoop exactly on the mouth makes a
                     # coincident face with the aperture cut, and that is what
                     # took the whole solid non-manifold last round.
# ⚠️ CREST_W is set by the min-wall check, not by taste. His outer bevel is
# only 22.6 deg off vertical and the scoop arrives vertical at the crest, so a
# true point is a 22.6 deg wedge -- a feather edge, and the wall check flags it
# (its filter keeps exactly this case). 1.2 mm is three extrusion lines and it
# still reads as a point at 83 mm across.
CREST_W = 1.2        # flat left at the crest
BROW_Y0 = 11.0       # elbow scoop's base, on the well floor
BROW_Y1 = 141.0      # hand scoop's base -- clear of the camera at 140.5
ELBOW_OUT = 0.59     # elbow brow's outer face rakes back at his slope
RAMP_Y0 = 11.0       # crest starts ramping down here, toward the elbow...
RAMP_Y1 = 134.0      # ...and here toward the hand. His numbers.
# 1.1, not his 1.0. The ramp faces point downward when the part stands on its
# hand end, and at 1.0 they land at exactly 45 deg -- on the threshold, not
# under it. 1.1 puts them at 48 deg and is indistinguishable by eye.
RAMP_SLOPE = 1.1     # run per unit rise; >1 is shallower than 45 deg

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
# ★★ Owner's finishing pass, originally measured off RoamTouchModded.step as
# 1.5 mm. Raised to 3.0 on 2026-08-12: "you went from a 3 to a 1.5 on that, it
# makes it look less blocky". Small chamfers read as manufacturing relief; big
# ones are the language of the reference object in ref/. Do not lose this on
# the next regeneration -- it is most of what makes the thing read as a
# designed object rather than a blank.
CHAMFER = 3.0        # major creases
CHAMFER_SM = 1.5     # where a facet is too narrow for the full size

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


# ★ The ray the frozen bezel already casts: the aperture mouth stands
# BEZEL_CHAM proud of the display over LIP_H of rise. The guard's inner wall
# starts on that ray and the concave scoop only ever moves material AWAY from
# it, so the guard cannot shadow a pixel the housing was not already shadowing.
# The harness proves it rather than trusting the arithmetic.
SIGHT = BEZEL_CHAM / LIP_H
GUARD_X0 = WIN_X + BEZEL_CHAM + GUARD_LEDGE     # scoop's base, on the well floor
_GZ0, _GZ1 = OUT_H, OUT_H + GUARD_H
GUARD_XC = GUARD_HW - GUARD_BEV_X - CREST_W     # crest, inboard of the bevel


def scoop_r(run, rise):
    """Radius of the arc that leaves a vertical wall at the crest and has moved
    `run` sideways by the time it reaches `rise` below it."""
    return (run ** 2 + rise ** 2) / (2 * run)


SCOOP_R_SIDE = scoop_r(GUARD_XC - GUARD_X0, GUARD_H)
SCOOP_CX = GUARD_XC - SCOOP_R_SIDE              # axis, out in the well
# ⚠️ The brow scoops' radius is a PRINTABILITY choice, not a styling one. The
# elbow brow's inner face points down when the part stands on its hand end, so
# it must stay inside 45 deg; for this family of arcs the steepest point is at
# the base and the condition is exactly R >= rise * sqrt(2).
SCOOP_R_BROW = GUARD_H * math.sqrt(2) * 1.13
SCOOP_CY0 = BROW_Y0 + math.sqrt(SCOOP_R_BROW ** 2 - GUARD_H ** 2)   # elbow axis
SCOOP_CY1 = BROW_Y1 - math.sqrt(SCOOP_R_BROW ** 2 - GUARD_H ** 2)   # hand axis


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


def bevel(pts, d, skip=()):
    """Chamfer a polygon's corners: replace each vertex with two, set back d
    along each adjacent edge.

    ★ The hull's creases are bevelled HERE, in the section, not with OCCT's
    chamfer() afterwards. Three reasons, in order of how much they cost me:
      * OCCT refuses them. Every belt crease runs into the cap's tenon step at
        one end and the hand-end face at the other, and it would not take a cut
        of any size there -- 1 of 4 creases landed.
      * A section bevel propagates for free to the cap, the tenon, the collar
        bore and the shell cavity, because they are all insets of this polygon.
      * It is exact and parametric. CHAMFER is a number, not a hope.
    Each set-back is capped at 45% of its edge so two bevels can never meet.
    """
    n = len(pts)
    out = []
    for i, v in enumerate(pts):
        if i in skip:
            out.append(v)
            continue
        for w in (pts[(i - 1) % n], pts[(i + 1) % n]):
            ex, ez = w[0] - v[0], w[1] - v[1]
            ln = math.hypot(ex, ez)
            t = min(d, 0.45 * ln) / ln
            out.append((v[0] + ex * t, v[1] + ez * t))
    return out


def prism(pts, y0, y1):
    """Extrude an (X, Z) polygon from y0 to y1.

    ⚠️ SELF-CORRECTING, and it has to be. Polygon takes its face normal from
    the winding and extrude() follows that normal, so a profile listed the
    other way round silently goes to -Y. That has now cost two separate bugs:
    a 294 mm long part, and a lip bevel that cut the elbow brow off. Rather
    than ask every caller to get the winding right, build it, look at where it
    landed, and flip if it went backwards.
    """
    f = Plane.XZ * Polygon(*pts, align=None)
    sol = extrude(f, amount=-(y1 - y0))
    if sol.bounding_box().min.Y < -1e-6:
        sol = extrude(f, amount=(y1 - y0))
    return Pos(0, y0, 0) * sol


def yz_prism(pts, x0, x1):
    """Extrude a (Y, Z) polygon along +X. Plane.YZ maps local u,v -> Y,Z with
    its normal on +X, so the amount is positive. Used for anything whose
    profile lives in the arm-axis plane -- the visor brows, mainly."""
    f = Plane.YZ * Polygon(*pts, align=None)
    sol = extrude(f, amount=(x1 - x0))
    if sol.bounding_box().min.X < -1e-6:     # went the wrong way
        sol = extrude(f, amount=-(x1 - x0))
    return Pos(x0, 0, 0) * sol


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

# ★ Bevel the section before anything is built from it. Skip the two top
# vertices: those are where the hull meets the frozen tray wall, a 167 deg
# crease that is not a crease.
HULL_SEC = bevel(HULL_SEC, CHAMFER, skip=(0, len(HULL_SEC) - 1))

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
# ⚠️ Clamp the ceiling to the tray floor's underside. HULL_SHOULDER is 4.5
# now, so the section's top edge insets to Z=2.5 -- above the pocket floor.
# Unclamped the cavity eats the floor and leaves 0.6 mm of it.
cav &= bbox(-90, 90, -30, OUT_L + 30, -90, 0.0)
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

# ★ Ribs, not louvres. The five canted slots that used to be here are gone.
# They were doing a little real work -- the floor vents ducted into the cavity
# and exhausted through them -- but that duct was already half-dead once the
# card channel moved into it, and they read as damage rather than design.
# ⚠️ Consequence, stated rather than hidden: with the cap on, the shell cavity
# is now a SEALED void. The floor vents still let the phone's heat out of the
# pocket into ~50 cm3 of air and the whole shell's surface area, which is most
# of the benefit, but there is no through-flow. If that ever matters the right
# place for the opening is the cap, which is the removable part.
#
# The ribs run the full length, so they have no ends to overhang, and they are
# added to the CAP as well as the hull -- same X/Z profile, so they read as one
# continuous rib from the nose to the tail.
_fl_z0 = HULL_Z_DEEP + HULL_CHINE + CHAMFER      # flat part of the deep flank
_fl_z1 = HULL_BELT - CHAMFER
_fin_c = (_fl_z0 + _fl_z1) / 2
FIN_Z = [_fin_c + (i - (FIN_N - 1) / 2) * (FIN_H + FIN_GAP) for i in range(FIN_N)]
assert FIN_Z[0] - FIN_H / 2 > _fl_z0 + 0.5 and FIN_Z[-1] + FIN_H / 2 < _fl_z1 - 0.5, \
    "ribs do not fit inside the flat part of the deep flank"


_fin_in = SD * (HULL_HW - 1.0)      # rooted inside the flank
_fin_out = SD * (HULL_HW + FIN_PROUD)


def fins(y0, y1):
    """The deep-flank rib stack, as a solid, over a Y range. Each rib carries
    its own bevel in section, so the ribs are printable, chamfered and on the
    cap without a single OCCT chamfer."""
    out = None
    for zc in FIN_Z:
        z0, z1 = zc - FIN_H / 2, zc + FIN_H / 2
        d = FIN_CH * (1 if _fin_out > _fin_in else -1)
        b = prism([(_fin_in, z0), (_fin_out - d, z0),
                   (_fin_out, z0 + FIN_CH), (_fin_out, z1 - FIN_CH),
                   (_fin_out - d, z1), (_fin_in, z1)], y0, y1)
        out = b if out is None else out + b
    return out


# ⚠️ From CAP_D, not 0. The cap carries the ribs over its own length; running
# them from 0 as well put 131 mm3 of the hull inside the cap.
part += fins(CAP_D, OUT_L)

# ------------------------------------------------------------------ visor
# ★ Built BEFORE the apertures, so the screen loft, the earpiece slot, the
# camera and the proximity window all cut straight through it and nothing has
# to be re-cut or dodged. The frozen opening stays exactly the frozen opening.
#
# Three pieces of the reference worth taking: the display is SUNK (the well
# floor is the old face, at OUT_H); the hood stands proud all round; and the
# hood is not a uniform ring -- deep brow at the elbow, shallower at the hand,
# plain walls down the sides where there are only 6 mm to play with.
# ---- the blank: a slab the full width, bevelled top and base like his ----
GUARD_SEC = [
    (-GUARD_HW + GUARD_BASE_CH, _GZ0 - EPS),
    ( GUARD_HW - GUARD_BASE_CH, _GZ0 - EPS),
    ( GUARD_HW,                 _GZ0 - EPS + GUARD_BASE_CH),
    ( GUARD_HW,                 _GZ1 - GUARD_BEV_H),
    ( GUARD_HW - GUARD_BEV_X,   _GZ1),
    (-GUARD_HW + GUARD_BEV_X,   _GZ1),
    (-GUARD_HW,                 _GZ1 - GUARD_BEV_H),
    (-GUARD_HW,                 _GZ0 - EPS + GUARD_BASE_CH),
]
guard = prism(GUARD_SEC, 0.0, OUT_L)

# ---- hollow it: the well is the intersection of three scooped half-spaces --
# ★ Each scoop is a CYLINDER, so the inner faces come out as single curved
# surfaces in the STEP rather than a faceted approximation.
# ⚠️ A cylinder is NOT a half-space, and assuming it was cost a whole build:
# "inboard of the scoop" is everything inside the cylinder PLUS everything past
# its axis. Without the second half the well closes up again 30 mm from the
# wall and the guard comes out inside out. Each zone below is that union.
# ⚠️ The side zone is why the guard is three-sided and not four: its axis sits
# at X=SCOOP_CX, so the half-space past the axis swallows the whole deep flank
# and no guard is ever built there. That is the "deep-flank cut" in his file --
# a wall he never built, reproduced here as a consequence of the geometry
# rather than as a hole punched afterwards.
# ★★ WHICH SIDE THE GUARD IS ON IS A LIVE QUESTION -- see the report. His file
# puts it on the SHALLOW flank and this reproduces that. But the screen tilts
# toward -X (the body's midline, for a right-arm fit), so the eye sits over the
# shallow flank -- the same side as the guard. The harness measures what that
# costs: 19 deg of viewing cone on the guard side against 37 deg on the open
# deep side. Flipping this one sign puts the guard on the far side and gives
# the eye the open one. One character, if he wants it.
_SHL = -SD                      # the side the guard is on -- shallow flank
_ax = _SHL * SCOOP_CX
_zone_side = (Pos(_ax, OUT_L / 2, _GZ1) * Rot(90, 0, 0)
              * Cylinder(SCOOP_R_SIDE, OUT_L + 300)) \
    + bbox(min(_ax, -_SHL * 90), max(_ax, -_SHL * 90), -60, OUT_L + 60, -90, 200)
_zone_elbow = (Pos(0, SCOOP_CY0, _GZ1) * Rot(0, 90, 0)
               * Cylinder(SCOOP_R_BROW, 400)) \
    + bbox(-90, 90, SCOOP_CY0, OUT_L + 60, -90, 200)
_zone_hand = (Pos(0, SCOOP_CY1, _GZ1) * Rot(0, 90, 0)
              * Cylinder(SCOOP_R_BROW, 400)) \
    + bbox(-90, 90, -60, SCOOP_CY1, -90, 200)
guard -= (_zone_side & _zone_elbow & _zone_hand
          & bbox(-90, 90, -60, OUT_L + 60, _GZ0 - EPS, _GZ1 + 40))

# ---- the elbow brow's outer face rakes back off the cap's top ----
# The guard grows out of the cap's face rather than butting against it. In this
# print orientation that face's normal points toward the elbow, which is UP, so
# the rake is free at any angle.
guard -= yz_prism([
    (0.0,                          _GZ0 - EPS),
    (ELBOW_OUT * (_GZ1 + 30 - _GZ0), _GZ1 + 30),
    (-90.0,                        _GZ1 + 30),
    (-90.0,                        _GZ0 - EPS),
], -90, 90)

# ---- and the crest ramps down at 45 deg into both ends ----
# ★ His signature move, and the answer to "the ends are blocky caps": the guard
# does not stop, it sweeps down into them.
for _sy, _ry in ((-1, RAMP_Y0), (1, RAMP_Y1)):
    guard -= yz_prism([
        (_ry,                                        _GZ1),
        (_ry + _sy * (GUARD_H + 12) * RAMP_SLOPE,    _GZ0 - 12),
        (_ry + _sy * 220,                            _GZ0 - 12),
        (_ry + _sy * 220,                            _GZ1 + 30),
        (_ry,                                        _GZ1 + 30),
    ], -90, 90)

part += guard

# Phone pocket -- runs out the elbow end so the phone slides in
part -= bbox(-POCK_W / 2, POCK_W / 2, -10, POCK_L, FLOOR, FLOOR + POCK_D)

# Screen aperture. This is the bezel: the face closes down to the display
# instead of exposing the phone's own bezel, so the housing reads as the
# device rather than as a tray with a phone in it.
# Lofted, not a straight cut: the aperture is BEZEL_CHAM wider at the top face
# and closes down to the display, so the bezel slopes into the screen instead
# of standing over it as a lip. Owner's change, brought back into the source.
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
# ⚠️ Stops at OUT_H, not OUT_H+10. The notch through the frozen wall is
# unchanged; the overshoot above the face used to cut air and now cuts a
# 20 mm bite out of the hood's hand brow. The plug sits at Z 6.45 and is 6 mm
# across, so it never needed the height.
part -= bbox(
    JACK_X - JACK_W / 2, JACK_X + JACK_W / 2,
    OUT_L - WALL - EPS, OUT_L + 10,
    FLOOR + 0.8, OUT_H,
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
# ⚠️ 1.4, down from 1.8. The shallow flank is only 6.9 mm tall between the
# belt and the arm cut, and 3 mm of that is the belt's bevel -- a 1.8 mm
# dome does not fit in what is left.
CAP_BUMP_R = 1.4     # snap dome radius
CAP_DIMPLE_D = 0.7   # how deep the dome sinks into the tenon flank
CAP_BUMP_Y = 7.0     # dome centre, out near the collar's free end
CAP_SLOT_W = 1.4     # relief slot freeing the deep flank from the chine fold
CAP_SLOT_ROOT = 2.5  # slot stops this far from the plate, leaving the root
CAP_RAKE = 8.0       # plan-view rake across the plate's CAP_T of depth
CAP_CHIN = 4.0       # elevation rake on the cap's face, below the tray
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
# ⚠️ Midpoint of the FLAT flank, not of the whole flank: the belt's 3 mm bevel
# eats the top of it, and a dome centred on the raw midpoint would sit half in
# the bevel face.
FLANKS = ((-SD, (HULL_BELT - CHAMFER + _sh_bot) / 2),
          (SD, (HULL_BELT - CHAMFER + HULL_Z_DEEP + HULL_CHINE + CHAMFER) / 2))

# Dimples in the TENON's flanks now, not the tray's. TRUNCATED CONES, not
# cylinders and not spheres: a cylinder presents a sharp edge square to the
# travel direction and will not go on at all, while a sphere rams a curved
# surface into a flat one and OCCT emits a non-manifold shell there (verified
# -- removing the spheres took both parts from 378 broken faces to zero).
for _sd, _zc in FLANKS:
    _sx = 1 if _sd > 0 else -1
    part -= Pos(_sx * (HULL_HW - TEN_D + 0.2), CAP_BUMP_Y, _zc) \
        * Rot(0, -90 * _sx, 0) \
        * Cone(CAP_BUMP_R, CAP_BUMP_R * 0.55, CAP_DIMPLE_D + 0.2,
               align=(Align.CENTER, Align.CENTER, Align.MIN))

# Collar: the wall between the tenon and the full section, below the belt.
cap = (prism(HULL_SEC, 0.0, CAP_D) & _cap_below) \
    - prism(CAP_SEC_IN, -EPS, CAP_D + EPS)
# End plate: the whole face -- hull section below, tray section above.
cap += prism(HULL_SEC, -CAP_T, 0.0)
cap += bbox(-OUT_W / 2, OUT_W / 2, -CAP_T, 0.0, 0.0, OUT_H)
# ⚠️ NO guard band on the cap any more. The guard's elbow brow rakes back off
# the cap's top face instead of running across it, so the cap tops out at the
# tray face and the guard grows out from behind it. That also retires the
# height mismatch at the joint that his demo file still has.
# ...and the deep-flank ribs, same profile as the hull's so they line through.
cap += fins(-CAP_T, CAP_D)
# ⚠️ The saddle runs through the cap too. Without this the plate would close
# off the elbow end of the arm channel and sit on the forearm.
cap -= arm

# ★ The cap's CHIN rakes back: its face leans away from the elbow as it drops
# through the hull's section, so the nose is a wedge and not a slab. Kept below
# Z=0 so it never touches the USB trough or the speaker mouths, and its normal
# points toward the elbow -- up, in this print orientation -- so it is free.
cap -= yz_prism([
    (-CAP_T,                  0.0),
    (-CAP_T + CAP_CHIN,       HULL_Z_DEEP - 10),
    (-CAP_T - 40,             HULL_Z_DEEP - 10),
    (-CAP_T - 40,             0.0),
], -90, 90)

# Plan-view rake on the nose corners, carried over from the hull's nose (the
# hull no longer has one -- the cap IS the nose now). A cut plane containing Z
# has no Z in its normal, so it costs nothing in the print orientation, and it
# is sized to finish exactly at Y=0 so it never reaches the collar and cannot
# skin the corner off a 2 mm wall.
for _sx in (-1, 1):
    _n = Vector(_sx * CAP_T, -CAP_RAKE, 0).normalized()
    # ⚠️ Off GUARD_HW, not HULL_HW. The hood and the ribs both reach 41.5;
    # raking to 40 by Y=0 cut their corners off and put a step at the joint.
    _p0 = Vector(_sx * (GUARD_HW - CAP_RAKE), -CAP_T, 0)
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
        * Cone(CAP_BUMP_R, CAP_BUMP_R * 0.5, CAP_W / 2 + 0.6,
               align=(Align.CENTER, Align.CENTER, Align.MIN))

# ------------------------------------------------------- edge treatment
# ★★ BIG chamfers, and the same size everywhere they fit. 1.0/1.5 read as
# manufacturing relief; 3 mm reads as a designed bevel, which is the language
# of the reference object in ref/. A chamfer on a facet crease is just a third
# facet, so the low-poly read survives -- a fillet would not, and there are
# none here.
#
# ⚠️ A chamfer cannot be wider than the narrower of the two facets it sits
# between. Where a facet is too small for CHAMFER the group takes a smaller
# value, and that is stated rather than silently dropped:
#   * the tray-to-hull ledge is only 2.45 mm wide (the tray is frozen at 75.1
#     and the hull is 80), so its edges take 1.5;
#   * the visor's inner lip is the hood's own edge and a 3 mm cut there would
#     eat the hood, so it takes 1.2.
# Everything else -- every long hull crease, the visor's outer rim, the whole
# hand-end perimeter -- takes the full 3 mm.
#
# Feature edges (pocket, apertures, strap channel, plungers, card rails) are
# deliberately left sharp: chamfering those would eat clearances. The audit in
# verify_bracer.py lists every sharp exterior crease that survives, so the ones
# left alone are a decision on record rather than an oversight.
_VZ1 = _GZ1


def _near(a, b, t=0.05):
    return abs(a - b) < t


def _is_crease(e):
    """A long arm-axis edge sitting on one of the hull section's corners."""
    c = e.center()
    if e.length < 25 or c.Z > HULL_BELT + 0.5:
        return False
    return any(_near(c.X, vx, 0.3) and _near(c.Z, vz, 0.3) for vx, vz in HULL_SEC)


def _visor_rim(e):
    """The guard's crest. Mostly formed in section now; this catches whatever
    flat is left at the top."""
    c = e.center()
    return _near(c.Z, _VZ1) and abs(c.X) > GUARD_XC - 1.0


def _cap_face(e):
    """The cap's front-face perimeter -- the one crease the audit found that
    was a genuine miss rather than a frozen feature or a joint."""
    c = e.center()
    if not _near(c.Y, -CAP_T):
        return False
    return abs(c.X) > 30.0 or c.Z > OUT_H + 0.5 or c.Z < 0.0


def _visor_base(e):
    """Where the guard overhangs the tray's side wall."""
    c = e.center()
    return _near(c.Z, OUT_H) and _near(abs(c.X), GUARD_HW)


# ⚠️ The hand-end perimeter is DELIBERATELY LEFT SHARP, and this is the one
# place the 3 mm rule is not applied. Two reasons, both hard:
#   * the tray's hand-end wall is 2.4 mm of frozen pocket, so a 3 mm chamfer on
#     its outer edge breaks straight through into the pocket -- it did, and the
#     wall probes caught it;
#   * that face is the bed. A sharp first layer is what you want there.
# The audit lists these creases every run, so the decision stays visible.


# OCCT refuses mixed sets (ValueError) with no useful message, so chamfer in
# groups. Each group is attempted independently so one awkward set cannot lose
# the others, and each falls back to edge-by-edge.
_groups = [
    ("guard crest",    CHAMFER_SM,  _visor_rim),
    ("guard base",     CHAMFER_SM,  _visor_base),
]
_cap_groups = [("cap face rim", CHAMFER, _cap_face)]
def _sig(e):
    c = e.center()
    return (round(c.X, 2), round(c.Y, 2), round(c.Z, 2))


_targets = {"part": part, "cap": cap}
for _tgt, _glist in (("part", _groups), ("cap", _cap_groups)):
    for _name, _len, _pred in _glist:
        _obj = _targets[_tgt]
        _es = ShapeList([e for e in _obj.edges() if _pred(e)])
        if not _es:
            print(f"chamfer    no edges matched ({_name})")
            continue
        try:
            _targets[_tgt] = chamfer(_es, length=_len)
            print(f"chamfer    {_len} mm on {len(_es):3d} edges  ({_name})")
            continue
        except Exception:
            pass
        # OCCT refuses mixed sets with no useful message. Retry edge by edge so
        # one awkward crease costs one crease, not the whole group.
        # ⚠️ The pool is snapshotted by MIDPOINT before the first cut and each
        # one is struck off as it lands. Re-running the predicate instead
        # re-matches the NEW edges a chamfer creates -- at Y=OUT_L a fresh edge
        # is still at Y=OUT_L -- so the loop keeps cutting the same corner and
        # walks the geometry away. That took the part to 129.7 mm wide once.
        _pool = {_sig(e) for e in _es}
        _done = 0
        while _pool:
            _hit = False
            for _e in _targets[_tgt].edges():
                if _sig(_e) not in _pool:
                    continue
                try:
                    _targets[_tgt] = chamfer(ShapeList([_e]), length=_len)
                except Exception:
                    continue
                _pool.discard(_sig(_e))
                _done += 1
                _hit = True
                break
            if not _hit:
                break
        print(f"chamfer    {_len} mm on {_done:3d} of {len(_es):3d} edges  "
              f"({_name}, one at a time, {len(_pool)} refused)")
part, cap = _targets["part"], _targets["cap"]

# ----------------------------------------------------------------- export
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(out, exist_ok=True)
# ★ Check the solids BEFORE writing them. A non-manifold shell makes every
# contains() probe downstream return nonsense, and the failures it produces
# look like feature bugs a long way from the actual cause. Ask here.
for _nm, _sd in (("bracer", part), ("end cap", cap)):
    if not _sd.is_valid:
        raise SystemExit(f"{_nm}: solid is not valid -- coincident faces?")
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
# ⚠️ Loose tolerance on purpose. OCCT's bounding box on a TRANSFORMED solid
# carries a tolerance gap -- it reports ~0.44 mm of slop here that the exported
# mesh does not have. The real bed-contact check is on the mesh, in
# verify_bracer.py, where the number is exact.
assert abs(_pp.bounding_box().min.Z) < 1.0, "bracer not sitting on the bed"
assert abs(_pc.bounding_box().min.Z) < 1.0, "cap not sitting on the bed"
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
