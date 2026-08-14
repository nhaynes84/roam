"""
ROAM Touch — the functional build of his concept. STEP 1: the phone housing.

★ This is a NEW model, not a fork of bracer.py, and the reason is structural.
`bracer.py` makes the housing conform to the arm — the tilted arm cut, the hull
skirt, the belt, the strap slots, the tessellated flanks. **A flush half-circle
sleeve now does that job**, so all of it leaves the housing and the base becomes
a flat mounting face. What survives from `bracer.py` is the only part that has
to be exact: the pocket, the apertures, the buttons and the port cutouts.

⚠️⚠️ The face numbers below were CORRECTED AGAINST A PRINTED PART on 2026-08-12.
They are measurements, not a trace, and they are not to be re-derived:

    "bring the screen bezel in about 2mm left and right, 4mm top and bottom.
     Your camera hole on the top left needs to move right about 4mm and down
     about 3 ... buttons are perfect though man, they feel great, first try"

and, separately, the prox window right 1.5 and down 3. The earpiece is
unchanged and confirmed good. He rates his own eye at ±0.5 mm, which is inside
FEAT_TOL and better than the ±1 mm the source drawing claimed.

Steps, not one grand go — see `feedback-steps-not-one-go`. This file is step 1
only: **fit**. The pack tube, cable routing, flush cap, mic pod and sleeve are
later steps, and the sliding cover is a separate model after those.
"""
import math
from build123d import *

# ------------------------------------------------------------------ phone
# Google Pixel (sailfish, 2016). The back tapers 8.5 → ~7.3 mm toward USB-C;
# the pocket is cut to the max and the front lip holds the thin end down.
PH_L, PH_W, PH_T = 143.8, 69.5, 8.5

# ------------------------------------------------------------- parameters
CLR = 0.4            # per-side clearance around the phone
WALL = 2.4           # pocket side wall
FLOOR = 2.2          # tray floor under the phone
LIP_SIDE = 2.5       # front lip over the long bezels
LIP_END = 4.0        # front lip at the jack end
LIP_H = 2.4          # lip height above the phone face (also screen standoff)
BEZEL_CHAM = 1.5     # how far the aperture opens out at the top face

# ⚠️⚠️ 0.6, and it stays 0.6 until someone measures a reason to change it.
#
# I raised this to 1.0 on my own initiative, reasoning that the phone shifts by
# up to CLR (0.4) and his eye carries ±0.5, so a wider margin would stop an
# opening clipping. It does — and it also leaves a **0.65 mm rib** between the
# proximity window and the top of the screen aperture, against a 1.15 mm
# min-wall. The features are 2.65 mm apart; opening both by 1.0 eats 2.0 of it.
#
# ★ The lesson, not the number: on this face the apertures are close enough
# that tolerance is bounded by the GAPS BETWEEN THEM, not by the shift of the
# phone. `gaps()` below asserts it now, so nobody re-derives this by hand.
FEAT_TOL = 0.6

# ------------------------------------------------- phone face features
# SVG origin is the top-left of the FACE, y increasing toward the USB-C end.
SCREEN_SVG = (5.32, 18.30, 64.12, 123.77)   # x0,y0,x1,y1 — corrected
EARPIECE_SVG = (27.10, 5.44, 40.78, 6.51)   # unchanged, confirmed good
PROX_SVG = (32.99, 13.70, 37.88, 15.65)     # right 1.5, down 3
CAM_SVG = (15.22, 8.78, 1.50)               # cx, cy, r — right 4, down 3
PWR_SVG = (37.11, 46.01)                    # power button, y range, +X side
VOL_SVG = (55.16, 72.91)                    # volume rocker, y range, +X side

# ---------------------------------------------------------- ports, edges
# ★★ THE JACK IS PERMANENTLY OCCUPIED, so the external notch is gone.
# Owner: "i'll route the mic, plug it into the phone and put it in the case, the
# jack is fully occupied all the time." The mic capsule lives behind the grille
# and its TRRS plug never comes out — so a notch in the top edge served nothing
# but a hole, and the edge closes.
#
# ⚠️ But the plug has to go SOMEWHERE. The phone's top edge sits 0.4 mm from the
# end wall, so the old notch was the plug's only escape route. Closing it means
# the pocket has to continue past the phone to hold the plug and its cable bend.
# ⚠️⚠️ **A RIGHT-ANGLE PLUG IS NOW REQUIRED.** A straight one protrudes 15–18 mm
# and would cost 20 mm of length. His call: size it generously.
JACK_CAV = 12.0

# ★★ The ORIGINAL pocket wall stays. Owner: "it should still have the original
# housing wall, but with an opening for the jack port with jack in to clear, so
# the left half of the original wall is safe to leave for good fitment."
#
# ⚠️ I had removed the whole wall to make the cavity, which left the phone
# stopping against nothing — it could slide 12 mm up the housing. The wall is
# what locates it. Only the jack's quartile is cut through; the rest is solid.
# ⚠️ NOT a fitted slot. Owner: *"you can reasonably just leave the left half of
# that top wall, so i have wiggle room with the jack installed."* The wall is a
# locating stop, not a gasket — half of it stops the phone just as well, and the
# open half means the plug body can sit wherever it lands without a clash.
# The jack is in the +X quartile, so +X opens and −X stays solid.
USB_W, USB_H = 14.0, 8.0
SPK_W, SPK_H, SPK_X = 16.0, 3.4, 17.0   # speakers either side of USB-C
VENT_R, VENT_W = 6.0, 46.0

BTN_BORE_H = 4.0
BTN_CB_H = 7.0
BTN_CB_D = 1.2
BTN_CB_EXT = 3.0
BTN_CLR = 0.35
BTN_PROUD = 0.6

CHAMFER, CHAMFER_SM = 3.0, 1.5
EPS = 0.1

# ------------------------------------------------------------- STEP 2: pack
# ★ His cylindrical pack — 4.2 x 1.0 in — and it is the shape that unlocked the
# whole form. A slab pack's short edge is ~67 mm whatever the brand, which was
# forcing a 70 mm wall; a cylinder is 25.4 mm in every direction and its long
# axis runs happily along the forearm, the one direction that is already spent.
#
# ⚠️ It must READ. Owner: "you should see most of the tube shape under the slid
# out visor or stacked on the phone when it's closed." It is silhouette, not a
# hidden cavity — his own concept accidentally closed it over.
PACK_D = 25.4              # 1.0 in
PACK_L = 106.7             # 4.2 in
PACK_CLR = 2.0             # "a couple mil at either side breathing room"
TUBE_WALL = 2.5

TUBE_BORE_R = PACK_D / 2 + PACK_CLR        # 14.70
TUBE_R = TUBE_BORE_R + TUBE_WALL           # 17.20
# ★ FULL LENGTH, his call: "it's not centered, i would just make it full length
# if you're gonna do it this way." A 112 mm stub on a 147 mm housing reads as a
# lump that landed somewhere; running the whole length reads as a spine.
# It also pays for itself — the pack is 106.7, so the spare 40 mm at the cap end
# becomes the cavity the lead and the port live in, rather than dead tube.
TUBE_LEN = PH_L + 2 * CLR + JACK_CAV + WALL   # = OUT_L, defined below

# ⚠️⚠️ NEGATIVE X, and that is not a style choice — it is the only side free.
# The power and volume plungers live in the +X wall and stand BTN_PROUD past it;
# the jack notch is in the +X quartile of the top edge too. A tube on that side
# buries all three. Worn on his RIGHT arm, this also puts the tall element on
# the outboard edge, away from his torso when the arm comes across to read.
#
# ⚠️ Magnitude is set by the pocket, not by looks: the bore may not eat the tray
# wall. Minimum is pocket edge + a real wall + bore radius. This leaves 2.65 mm
# between the phone pocket and the pack bore, and overlaps the tray's outer face
# so the two fuse across a face rather than kissing on a tangent line.
TUBE_X = -52.5

# ★★ The tube hangs BELOW the base plane, but a third of it still stands proud
# of the face. Two corrections, in order:
#
# 1. It was sitting ON the base plane, 21 mm proud, making the whole thing 34 mm
#    tall before the visor started. It can drop because of where it is: at
#    |X| 52.5 it is **outboard of the arm** (radius 45), so the space beneath is
#    beside the forearm, not inside it.
# 2. Then I dropped it flush and killed the look. Owner: "you dropped the tube
#    all the way down, it kills the aesthetic, you need at least 1/3 of it
#    bulging above the face plate."
#
# ★★ The control is where the AXIS sits relative to the top face, not how much
# crown shows — that is the way he describes it and it is the better handle.
# Owner: "from the horizontal center line, the tube sits at most a third below
# it, maybe a quarter, so you get curve coming up off the top face but it's not
# half a cylinder."
#
# ⚠️ Axis ON the face would show exactly half a cylinder. Axis BELOW the face
# shows less — the deeper it sits, the gentler the curve rising off the plane.
# A third of the diameter below leaves 5.7 mm of crown; a quarter leaves 8.6.
# I had it at 5.7 mm below (a third of the RADIUS) which left 11.5 mm proud —
# most of a dome, which is what read wrong.
TUBE_AXIS_BELOW_FACE = 2 * TUBE_R / 4.0    # a quarter of the diameter
# TUBE_Z is derived from OUT_H below — crown flush with the tray face.

# ------------------------------------------------- STEP 4: mic + routing
# ★ The mic's TRRS plug lives in the jack cavity permanently, so its cable has to
# get from the top-right corner down the +X side to a capsule. Owner:
#   "a hole in the top right where the aux cable routes, it's got to come down
#    under the buttons ... a little mic housing centered on the right side, under
#    the buttons there ... leave a channel on the bottom or inner corner to run
#    the cable, and this means the right side has to be a bit thicker there ...
#    but it should go under the buttons so they are accessible"
#
# ⚠️⚠️ **RAIL_TOP is the whole constraint.** The button bores start at
# FLOOR + PH_T/2 - BTN_BORE_H/2 = 4.45, and the plungers stand proud of the +X
# wall. Anything added to that wall ABOVE 4.45 buries them. So the rail is a LOW
# rail — it runs under both buttons and stops short of them — and it only swells
# to full height past Y 112, where the power button has already ended and the
# cable needs the headroom to come out of the plug cavity.
# ⚠️ 10, not 8 — the channel needs a land either side AND the rounding eats the
# bottom-outer corner. At 8 there was nowhere for the service plate to seat.
# ★★ Owner: *"i also slimmed it down, and sat it properly in line with the mic."*
# The blister is GONE. It was the fat part — 14.5 mm of pad bulging 4.5 mm past
# the rail — and deleting it slims the whole right side more than shaving the
# rail ever could. The grille now sits centred in the rail's own width.
#
# ⚠️ 9.5 is close to the floor: the capsule pocket is d6.4 and needs ~1.5 mm of
# wall each side. Slimmer than this and the capsule has to shrink with it.
RAIL_W = 9.5          # how much thicker the +X side gets
# ★ Owner: *"the asymmetry; if youre going to do the right side like that, the
# left needs to match it, at least aesthetically."* They cannot match in MASS —
# the left is a 34 mm battery tube and the right is a 10 mm rail — so they match
# in what they DO: both hang below the base plane and both read as a spine.
#
# ⚠️ I first tried matching the tube by ROLLING the rail's outer edges (r2.5).
# Owner: *"your thing is [too] boxy in a bad way, stick with the unfilited
# angles for now, you have a mix and we'll do finishing touches later."* One
# rolled edge against hard angles everywhere else is worse than either — it
# reads as unfinished rather than soft. Edges stay crisp until a pass that does
# ALL of them. `_roll()` is kept, unused, for that pass.
RAIL_ROUND = 2.5
RAIL_TOP = 4.2        # ⚠️ under the button bores at 4.45 — do not raise
RAIL_STEP_Y = 112.0   # power button ends at 108.6; the rail rises after it
RAIL_RAMP = 10.0      # the step is a ramp, not a shoulder
# ★ Owner: *"the way you have the ramp on that top side, you should mirror it on
# the botom, even if it doesn't do anything functional."* So the bottom drops by
# exactly what the top rises, at the same Y, at the same angle — the jack end
# becomes a symmetric wedge instead of a block with one chamfer. Purely a look;
# dial RAIL_DROP to taste, it is the only number involved.
RAIL_DROP = 9.2       # = OUT_H − RAIL_TOP, i.e. the top ramp, mirrored

# ★ It hangs BELOW the base plane, like the tube does on −X, and that is what
# buys the channel its height. At |X| 38–51 the arm (r ~49) has already fallen
# ~30 mm away, so there is nothing down there to foul — the same argument that
# let the tube drop. A flat base at the +X edge would be flatness for its own
# sake, and it would cost the channel 6 mm it has nowhere else to find.
RAIL_Z0 = -10.0

# ⚠️ 4.0, and it moved inboard. At 4.5 centred, the outboard LAND was 3.0 mm —
# an M2 pilot down the middle of that leaves 0.65 mm of wall each side, which
# splits the first time it is driven. The groove gives up 0.5 mm it does not
# need (a lav lead is 2–3 mm) so the screws get 1.25 mm of wall instead.
CH_W = 4.0            # cable channel, generous for a 2–3 mm lav lead
CH_Z1 = 2.0           # CH_Z0 is PLATE_TOP — the groove's floor IS the plate

# ⚠️ The channel is open at the BOTTOM for its whole length, not a blind bore.
# Threading a lead down 70 mm of buried tunnel is a job nobody does twice; laying
# it into an open groove and screwing a plate over it is a job you do once.
PLATE_T = 2.0         # the removable service plate
PLATE_CLR = 0.25

# The mic blister: centred on the side, sitting entirely below the button line.
# ⚠️ The blister's top is RAIL_TOP and cannot go higher — at Y 80.7 it sits
# directly in front of the volume rocker, so anything above the button line is
# a thumb standing between him and the button he is reaching for.
# ⚠️⚠️ Owner: *"your mic case needs to drop down, it's blocking the buttons."*
# It was not the bezel's 0.6 — it was the whole pad sitting at RAIL_TOP, right
# in the volume rocker's approach and 4.5 mm wider than the rail besides. So the
# grille shelf DROPS to MIC_TOP and the rail's top dips with it, which turns the
# problem into a feature: over the rocker the side is now 4.45 mm lower than the
# bore, so his thumb comes down into a scallop instead of onto a lump.
# ⚠️ −0.8, NOT 0.0. At 0.0 the dipped rail top is exactly coplanar with the
# tray's base plane, and the union across those two coincident planes
# tessellates to a seam — OCCT reports a valid single solid, the STEP is fine,
# and the STL quietly comes out non-watertight. Off-plane by 0.8 and it closes.
MIC_TOP = -0.8
# ⚠️ 15, not 13 — at 13 the RAMPS ate the last 1.4 mm of the rocker at each end,
# so the dip's flat has to cover the whole button, not just its middle.
MIC_DIP_HALF, MIC_DIP_RAMP = 16.0, 5.0
MIC_R = 3.2           # d6.4 pocket — a 6 mm electret with 0.4 of clearance

# ★★ GRILLE LINES, not a hole pattern. Owner: *"i do want grille lines though
# regardless."* Slots, tapering to a circle — which is his concept's round
# grille, and the one element on this thing that says it is not a phone in a box.
#
# ⚠️ Lines over a d7 pocket would go blind at their ends, so there is a PLENUM
# behind the face: the bore opens out to GRILLE_PL_R for GRILLE_PL_D before it
# necks down to the capsule. Every line is through-air for its whole length.
# ⚠️⚠️ It faces UP, not outboard. Owner: *"it faces forward, not up, i'll be
# looking down at this thing, my voice will be coming basically straight down."*
# The grille moves onto the rail's top shelf, which is also the only surface on
# that side that is flat, unobstructed and pointed at his mouth.
#
# ★ And it is a GRILLE, not slots in a wall — his two references (a ribbon mic's
# chrome ring, a 55SH's barred dome) are the same idea twice: **a bold raised
# bezel with long bars tapering to the circle.** That taper is the whole look;
# parallel lines of equal length read as ventilation.
GRILLE_FACE = 1.5     # face the bars are cut through
# ⚠️ Narrow and long, because it has to live inside 9.5 mm of rail now instead
# of a 14.5 mm pad. Three bars, not five — at this width five would mean 0.5 mm
# webs. The taper still carries the look.
GRILLE_A, GRILLE_B = 8.0, 2.6   # grille ellipse — semi-axis along Y, along X
BEZEL_W, BEZEL_PROUD = 1.3, 0.6
GRILLE_PL_D = 1.6     # plenum behind the face, so no bar goes blind
GRILLE_W = 1.1
GRILLE_PITCH = 1.9
GRILLE_LINES = 3

# --------------------------------------------------------------- derived
POCK_L = PH_L + 2 * CLR
POCK_W = PH_W + 2 * CLR
POCK_D = PH_T + 0.3

OUT_W = POCK_W + 2 * WALL          # 75.1 — tray outer width
OUT_L = POCK_L + WALL + JACK_CAV + WALL   # pocket, its wall, plug cavity, end
OUT_H = FLOOR + POCK_D + LIP_H     # 13.4
TUBE_Z = OUT_H - TUBE_AXIS_BELOW_FACE
TUBE_BULGE = TUBE_Z + TUBE_R - OUT_H        # crown standing above the face

PHONE_TOP_Y = POCK_L - CLR

RAIL_Z1 = RAIL_Z0 - RAIL_DROP       # the rail's underside past the ramp

RAIL_X0 = OUT_W / 2
RAIL_X1 = RAIL_X0 + RAIL_W
CH_X0 = RAIL_X0 + 1.3               # ⚠️ NOT centred — biased inboard so the
                                    # outboard land can carry the screws
CH_X1 = CH_X0 + CH_W

MIC_Y = OUT_L / 2                   # "centered on the right side"
MIC_X = RAIL_X0 + RAIL_W / 2        # ★ centred on the rail — "in line"
GR_Z = MIC_TOP                      # the shelf the grille sits in
PLENUM_Z = GR_Z - GRILLE_FACE - GRILLE_PL_D

# ⚠️ Ends at 152.5 so the riser clears the plate's top screw at Y 154 — at 154
# the screw was drilling into the cable riser and had no land at all.
EXIT_Y0, EXIT_Y1 = 147.0, 152.5     # the hole in the top right
EXIT_Z0, EXIT_Z1 = 3.5, 8.5         # inside the plug cavity's 2.2 – 10.7
CH_Y1 = EXIT_Y1 - 2.0
# ⚠️ The blister reaches 1 mm INTO the tray wall and the bezel sinks 0.2 into the
# blister. Both were landing exactly on their neighbour's face, and a union
# across coincident planes tessellates to a non-watertight seam — `watertight
# False` with every probe still passing, which is the quiet kind of broken.
BEZEL_SINK = 0.2                    # ⚠️ overlaps the shelf, never kisses it

# ⚠️ The plate has to STOP at the ramp — past it the rail's underside is 9.2 mm
# lower, so a flat rebate carried on would float inside the solid. Beyond Y 111
# the groove closes into a tunnel, which is fine: it is a straight 40 mm run
# with an open mouth at each end, not something anyone has to fish blind.
PL_Y0, PL_Y1 = MIC_Y - 15.0, RAIL_STEP_Y - 1.0
# ⚠️ Wider than the groove needs, because the run's screws cannot sit on the
# groove's centreline — there is no material there. They move to the outboard
# land, and the plate has to reach them.
PL_X0, PL_X1 = RAIL_X0 + 1.0, RAIL_X1 - 0.55
PLATE_TOP = RAIL_Z0 + PLATE_T
CH_Z0 = PLATE_TOP - 0.5             # ⚠️ overlaps the rebate, never kisses it
_SX = (CH_X1 + RAIL_X1) / 2         # ★ centred on the outboard LAND, not the
                                    # groove and not the plate — the groove's
                                    # centreline has no material in it at all.
SCREWS = [(_SX, PL_Y0 + 4.0 + i * (PL_Y1 - PL_Y0 - 8.0) / 2) for i in range(3)]


def fx(x):
    """SVG x → model X, centred on the phone."""
    return x - PH_W / 2


def fy(y):
    """SVG y → model Y, with the USB-C end at 0."""
    return PHONE_TOP_Y - y


def face_rect(svg, tol=FEAT_TOL):
    """An SVG box as a model-space (x0, y0, x1, y1), opened by `tol` a side."""
    x0, y0, x1, y1 = svg
    return (fx(x0) - tol, fy(y1) - tol, fx(x1) + tol, fy(y0) + tol)


# ---------------------------------------------------------------- build
def tray() -> Part:
    """The phone housing: pocket, lip, apertures, ports — on a flat base.

    ★ The base is FLAT and that is the headline change. Every arm-facing
    feature has moved to the sleeve, which is what removes the ~1 inch of stack
    height he measured: "ribs on the BASIC build, but then i have velcro and a
    strap under that, the whole setup just eats vertical space."
    """
    body = Box(OUT_W, OUT_L, OUT_H, align=(Align.CENTER, Align.MIN, Align.MIN))

    # ★ The pocket runs from the open USB end (y=0) to POCK_L, leaving one WALL
    # of material closing the jack end. It stops at the phone's face — the
    # material above it IS the lip, and the only holes in that lip are the
    # measured apertures. That is what "bring the bezel in" means: the lip
    # reaches inward to the aperture edge rather than to a generic inset.
    body -= Pos(0, -EPS, FLOOR) * Box(
        POCK_W, POCK_L + EPS, POCK_D,
        align=(Align.CENTER, Align.MIN, Align.MIN),
    )

    # ⚠️ The phone slides in under the lip from the USB end, so that end must be
    # open to the full pocket height. Nothing else may be.
    return body


def face_openings() -> Part:
    """★ The apertures, as one cutting tool. Corrected against a printed part."""
    z0 = FLOOR + POCK_D - EPS
    h = LIP_H + 2 * EPS
    cut = Part()

    # ★ The screen aperture is CHAMFERED, like his — it opens out toward the top
    # face by BEZEL_CHAM a side. A square-cut window reads as a hole punched in a
    # slab; the flare reads as an edge that was made.
    sx0, sy0, sx1, sy1 = face_rect(SCREEN_SVG)
    inner = Plane.XY.offset(z0) * Rectangle(sx1 - sx0, sy1 - sy0)
    outer = Plane.XY.offset(z0 + h) * Rectangle(
        sx1 - sx0 + 2 * BEZEL_CHAM, sy1 - sy0 + 2 * BEZEL_CHAM)
    cut += Pos((sx0 + sx1) / 2, (sy0 + sy1) / 2, 0) * loft([inner, outer])

    for svg in (EARPIECE_SVG, PROX_SVG):
        x0, y0, x1, y1 = face_rect(svg)
        cut += Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * Box(
            x1 - x0, y1 - y0, h, align=(Align.CENTER, Align.CENTER, Align.MIN))

    cx, cy, r = CAM_SVG
    cut += Pos(fx(cx), fy(cy), z0) * Cylinder(
        r + FEAT_TOL, h, align=(Align.CENTER, Align.CENTER, Align.MIN))

    return cut


def port_openings() -> Part:
    """The plug cavity, and the two speakers. No jack notch — see JACK_CAV."""
    cut = Part()

    # ★ The plug cavity sits BEYOND the retained pocket wall, and the plug
    # reaches it through a slot in that wall. The wall keeps locating the phone.
    cut += Pos(0, POCK_L + WALL, FLOOR) * Box(
        POCK_W, JACK_CAV, POCK_D,
        align=(Align.CENTER, Align.MIN, Align.MIN))
    cut += Pos(0, POCK_L - EPS, FLOOR) * Box(
        POCK_W / 2, WALL + 2 * EPS, POCK_D,
        align=(Align.MIN, Align.MIN, Align.MIN))

    # The USB end is already open; the speakers sit either side of the port.
    for sx in (-SPK_X, SPK_X):
        cut += Pos(sx, WALL / 2, FLOOR + PH_T / 2) * Box(
            SPK_W, WALL + 2 * EPS, SPK_H,
            align=(Align.CENTER, Align.CENTER, Align.CENTER))

    return cut


def button_bores() -> Part:
    """Bores for the two print-in-place plungers, +X wall.

    ⚠️ Positions untouched. "buttons are perfect though man, they feel great,
    first try" — the drawing was only wrong about the face features.
    """
    cut = Part()
    x = POCK_W / 2 + WALL / 2
    for y0, y1 in (PWR_SVG, VOL_SVG):
        ya, yb = fy(y1), fy(y0)
        cut += Pos(x, (ya + yb) / 2, FLOOR + PH_T / 2) * Box(
            WALL + 2 * EPS, (yb - ya) + BTN_CB_EXT, BTN_BORE_H,
            align=(Align.CENTER, Align.CENTER, Align.CENTER))
    return cut


def _roll(x_outer: float) -> Part:
    """★ The rounded outer face — the rail's answer to the tube's roundness."""
    w = x_outer - RAIL_X0 + 20.0
    h = OUT_H - RAIL_Z0
    sec = RectangleRounded(w, h, RAIL_ROUND)
    # ⚠️ `both=True` on purpose — Plane.XZ's normal points −Y, so a one-sided
    # extrude lands the prism entirely off the end of the part and the
    # intersection comes back EMPTY. It fails at the next `+`, not here, which
    # is a long way from the cause.
    return Pos(x_outer - w / 2, OUT_L / 2, (OUT_H + RAIL_Z0) / 2) * extrude(
        Plane.XZ * sec, (OUT_L + 4) / 2, both=True)


def side_rail() -> Part:
    """The thickened +X side: a low rail under the buttons, rising past them."""
    d0, d1 = MIC_Y - MIC_DIP_HALF, MIC_Y + MIC_DIP_HALF
    prof = [(0, RAIL_Z0), (0, RAIL_TOP),
            (d0, RAIL_TOP), (d0 + MIC_DIP_RAMP, MIC_TOP),      # ★ the scallop
            (d1 - MIC_DIP_RAMP, MIC_TOP), (d1, RAIL_TOP),
            (RAIL_STEP_Y, RAIL_TOP), (RAIL_STEP_Y + RAIL_RAMP, OUT_H),
            (OUT_L, OUT_H), (OUT_L, RAIL_Z1),
            (RAIL_STEP_Y + RAIL_RAMP, RAIL_Z1), (RAIL_STEP_Y, RAIL_Z0)]
    rail = Pos(RAIL_X0, 0, 0) * extrude(
        Plane.YZ * make_face(Polyline(*prof, close=True)), RAIL_W)

    # ★ The bezel — the raised ring off both his references. It is what makes the
    # thing read as a grille instead of a set of holes, and it is 0.6 proud so it
    # never stands between his finger and the volume rocker it sits beside.
    bez = Pos(MIC_X, MIC_Y, GR_Z - BEZEL_SINK) * extrude(
        Plane.XY * (Ellipse(GRILLE_B + BEZEL_W, GRILLE_A + BEZEL_W)
                    - Ellipse(GRILLE_B, GRILLE_A)), BEZEL_PROUD + BEZEL_SINK)
    return rail + bez


def cable_route() -> Part:
    """Exit hole, riser, channel, capsule pocket, grille — one cutting tool."""
    cut = Part()

    # ⚠️ The hole is high, in the tall part of the rail, because that is the only
    # place it can be: it has to meet the plug cavity, whose floor is at 2.2 and
    # which sits well above RAIL_TOP. The riser then drops it to channel height.
    cut += Pos(POCK_W / 2 - EPS, EXIT_Y0, EXIT_Z0) * Box(
        CH_X1 - POCK_W / 2 + EPS, EXIT_Y1 - EXIT_Y0, EXIT_Z1 - EXIT_Z0,
        align=(Align.MIN, Align.MIN, Align.MIN))
    cut += Pos(CH_X0, EXIT_Y0, CH_Z0) * Box(
        CH_W, EXIT_Y1 - EXIT_Y0, EXIT_Z1 - CH_Z0,
        align=(Align.MIN, Align.MIN, Align.MIN))

    # The run down the side. Its floor is CH_Z0 throughout; the plate rebate is
    # what opens it from below, so it is a groove where the plate reaches and a
    # tunnel past that — one cut, no special case.
    cut += Pos(CH_X0, MIC_Y, CH_Z0) * Box(
        CH_W, CH_Y1 - MIC_Y, CH_Z1 - CH_Z0,
        align=(Align.MIN, Align.MIN, Align.MIN))

    # ⚠️ The pocket runs all the way down to PLATE_TOP, deliberately: that is how
    # the capsule gets in from below and what the plate then holds it against.
    cut += Pos(MIC_X, MIC_Y, PLATE_TOP) * Cylinder(
        MIC_R, PLENUM_Z - PLATE_TOP,
        align=(Align.CENTER, Align.CENTER, Align.MIN))

    # ★ The plenum is the SAME ellipse as the grille, so every bar is through-air
    # for its whole length. Over a round pocket the outer bars would go blind.
    cut += Pos(MIC_X, MIC_Y, PLENUM_Z) * extrude(
        Plane.XY * Ellipse(GRILLE_B, GRILLE_A), GRILLE_PL_D)

    # ★★ The bars, tapering to the ellipse — the 55SH move. Equal-length lines
    # read as a vent; lines that shorten toward the rim read as a grille.
    bars = None
    for i in range(GRILLE_LINES):
        dx = (i - (GRILLE_LINES - 1) / 2) * GRILLE_PITCH
        k = 1.0 - (dx / GRILLE_B) ** 2
        if k <= 0:
            continue
        length = 2 * GRILLE_A * math.sqrt(k) - 0.5
        if length <= GRILLE_W:
            continue
        bar = Pos(dx, 0) * SlotOverall(length, GRILLE_W, rotation=90)
        bars = bar if bars is None else bars + bar
    cut += Pos(MIC_X, MIC_Y, GR_Z - GRILLE_FACE - EPS) * extrude(
        Plane.XY * bars, GRILLE_FACE + BEZEL_PROUD + 2 * EPS)
    return cut


def _plate_profile(clr: float):
    """The service plate in plan — a plain strip now the blister is gone."""
    return Pos((PL_X0 + PL_X1) / 2, (PL_Y0 + PL_Y1) / 2) * Rectangle(
        PL_X1 - PL_X0 - 2 * clr, PL_Y1 - PL_Y0 - 2 * clr)


def plate_rebate() -> Part:
    """The recess it sits in, plus the pilot holes."""
    cut = Pos(0, 0, RAIL_Z0 - EPS) * extrude(
        Plane.XY * _plate_profile(0.0), PLATE_T + EPS)
    for sx, sy in SCREWS:
        cut += Pos(sx, sy, PLATE_TOP) * Cylinder(
            0.85, 5.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return cut


def service_plate() -> Part:
    """★ Owner: "give the housing a bottom plate under the mic i can take off to
    easily get it in / out; it can take screws or snap in out, don't care."
    Screws — a snap in a 2 mm wall on this side would be a one-time snap.
    """
    plate = Pos(0, 0, RAIL_Z0) * extrude(
        Plane.XY * _plate_profile(PLATE_CLR), PLATE_T)
    for sx, sy in SCREWS:
        plate -= Pos(sx, sy, RAIL_Z0 - EPS) * Cylinder(
            1.2, PLATE_T + 2 * EPS, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return plate


def gaps():
    """★ The webs between apertures — the thing that actually bounds FEAT_TOL.

    Returns (label, mm) for every neighbouring pair on the face that shares an
    X span. ⚠️ Anything under MIN_WALL is a rib too thin to print, and it is
    invisible in a render: the hole looks right and the material between two
    holes is what fails.
    """
    def span(svg):
        x0, y0, x1, y1 = face_rect(svg)
        return (x0, x1), (y0, y1)

    cx, cy, r = CAM_SVG
    cam = ((fx(cx) - r - FEAT_TOL, fx(cx) + r + FEAT_TOL),
           (fy(cy) - r - FEAT_TOL, fy(cy) + r + FEAT_TOL))
    feats = [("earpiece", span(EARPIECE_SVG)), ("camera", cam),
             ("prox", span(PROX_SVG)), ("screen", span(SCREEN_SVG))]

    out = []
    for i in range(len(feats) - 1):
        for j in range(i + 1, len(feats)):
            (na, (ax, ay)), (nb, (bx, by)) = feats[i], feats[j]
            if min(ax[1], bx[1]) <= max(ax[0], bx[0]):
                continue                      # no shared X — cannot form a rib
            gap = max(ay[0], by[0]) - min(ay[1], by[1])
            out.append((f"{na} <-> {nb}", gap))
    return out


MIN_WALL = 1.15


def pack_tube() -> Part:
    """The battery tube, running along the arm beside the tray.

    ★ Loads from the SAME end as the phone — the USB end, y=0 — so the pack's
    port and the phone's port land in one cap cavity and the lead between them
    is a short jumper rather than a cable running the length of the housing.
    """
    tube = Pos(TUBE_X, 0, TUBE_Z) * Rot(-90, 0, 0) * Cylinder(
        TUBE_R, TUBE_LEN, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # ⚠️ The tube's surface is only outboard of the tray's wall between
    # z 8.7 and 25.7 — a 4.7 mm band where the two solids actually overlap.
    # Below that the cylinder curves away and leaves a valley, so the join was
    # a 4.7 mm web carrying a battery. This fills the valley up to the tangent.
    #
    # ★ It fills UP TO the tangent and no further, deliberately. Filling to the
    # tray's full height would bury the cylinder in a boss, and the tube has to
    # read: "you should see most of the tube shape". Its upper two thirds stay
    # a bare cylinder; only the dead space underneath becomes structure — which
    # the flat base wanted anyway, for the sleeve to mount to.
    # The flank between tray wall and tube fills to the tray face and stops —
    # so the bulge above the face stays bare cylinder rather than being absorbed
    # into a boss, which is the whole point of the third standing proud.
    web = Pos(TUBE_X, 0, 0) * Box(
        abs(TUBE_X) - POCK_W / 2 - WALL, TUBE_LEN, OUT_H,
        align=(Align.MIN, Align.MIN, Align.MIN))
    return tube + web


def pack_bore() -> Part:
    """★ Cut LAST, in build(), so nothing added later can intrude into it.

    ⚠️ The visor did exactly that: VISOR_SINK was 4 mm against a 2.5 mm tube
    wall, so the plate pushed 1.5 mm into the cavity and the pack would not have
    gone in. The bore was being cut before the visor was unioned, so no check
    could see it. Cutting the void last makes that class of mistake impossible.
    """
    return Pos(TUBE_X, -EPS, TUBE_Z) * Rot(-90, 0, 0) * Cylinder(
        TUBE_BORE_R, TUBE_LEN - TUBE_WALL + EPS,
        align=(Align.CENTER, Align.CENTER, Align.MIN))


def build() -> Part:
    p = tray()
    p += pack_tube()
    p += side_rail()
    p -= cable_route()
    p -= plate_rebate()
    p -= pack_bore()      # ★ last, so nothing can intrude — see pack_bore()
    p -= face_openings()
    p -= port_openings()
    p -= button_bores()
    return p


if __name__ == "__main__":
    import os
    part = build()
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "out")
    os.makedirs(out, exist_ok=True)
    plate = service_plate()
    export_step(part, os.path.join(out, "roam_step3.step"))
    export_stl(part, os.path.join(out, "roam_step3.stl"))
    export_step(plate, os.path.join(out, "roam_plate.step"))
    export_stl(plate, os.path.join(out, "roam_plate.stl"))
    export_step(Compound(children=[part, plate]),
                os.path.join(out, "roam_assembly.step"))

    bb = part.bounding_box()
    print(f"STEP 3 — housing + pack tube")
    print(f"  outer      {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm")
    print(f"  pocket     {POCK_W:.1f} x {POCK_L:.1f} x {POCK_D:.1f}")
    print(f"  volume     {part.volume / 1000:.1f} cm3  ~= "
          f"{part.volume / 1000 * 1.27:.0f} g PETG")
    print("  face webs (min wall %.2f):" % MIN_WALL)
    for label, g in gaps():
        flag = "  <-- TOO THIN" if g < MIN_WALL else ""
        print(f"    {label:22s} {g:6.2f} mm{flag}")
    sx0, sy0, sx1, sy1 = face_rect(SCREEN_SVG)
    print(f"  end wall   -X half RETAINED as the phone's stop "
          f"({POCK_W / 2:.1f} mm of it); +X half open for the plug")
    print(f"  plug cav.  {JACK_CAV:.1f} mm beyond that wall — right-angle plug")
    print(f"  screen     chamfered {BEZEL_CHAM:.1f} mm a side, opening outward")
    print(f"  pack tube  bore d{2 * TUBE_BORE_R:.1f} x {TUBE_LEN:.1f} long, "
          f"OD {2 * TUBE_R:.1f}, centre X {TUBE_X:.1f}")
    print(f"             pocket wall to bore  "
          f"{abs(TUBE_X) - TUBE_BORE_R - POCK_W / 2:.2f} mm  (tube on -X, "
          f"opposite the buttons)")
    import math as _mm
    _chord = 2 * _mm.sqrt(max(0.0, TUBE_R**2 - TUBE_AXIS_BELOW_FACE**2))
    print(f"             axis {TUBE_AXIS_BELOW_FACE:.1f} mm below the face "
          f"({100 * TUBE_AXIS_BELOW_FACE / (2 * TUBE_R):.0f}% of dia)")
    print(f"             crown {TUBE_BULGE:.1f} mm proud, over a {_chord:.1f} mm chord "
          f"— a curve, not a half cylinder")
    print(f"             hangs {abs(TUBE_Z - TUBE_R):.1f} mm below the base plane")
    print(f"  side rail  +{RAIL_W:.1f} mm on +X, top {RAIL_TOP:.1f} "
          f"(bores start {FLOOR + PH_T / 2 - BTN_BORE_H / 2:.2f}) — "
          f"{FLOOR + PH_T / 2 - BTN_BORE_H / 2 - RAIL_TOP:.2f} mm under the buttons")
    print(f"             rises to full height past Y {RAIL_STEP_Y:.0f}, "
          f"hangs {abs(RAIL_Z0):.1f} below the base plane, "
          f"{abs(RAIL_Z1):.1f} past the ramp (mirrored)")
    print(f"             dips to {MIC_TOP:.1f} over Y "
          f"{MIC_Y - MIC_DIP_HALF:.0f}-{MIC_Y + MIC_DIP_HALF:.0f} — "
          f"{FLOOR + PH_T / 2 - BTN_BORE_H / 2 - MIC_TOP - BEZEL_PROUD:.2f} mm "
          f"of clear approach under the rocker")
    print(f"  cable      exit {EXIT_Y1 - EXIT_Y0:.0f} x {EXIT_Z1 - EXIT_Z0:.0f} at "
          f"Y {EXIT_Y0:.0f}-{EXIT_Y1:.0f}, riser, then {CH_W:.1f} x "
          f"{CH_Z1 - CH_Z0:.1f} channel down to the mic")
    print(f"  mic        in the rail at X {MIC_X:.2f} (rail centre), Y {MIC_Y:.1f} "
          f"— no blister; capsule d{2 * MIC_R:.1f} x "
          f"{PLENUM_Z - PLATE_TOP:.1f} deep")
    print(f"             wall to the capsule  {RAIL_W / 2 - MIC_R:.2f} mm each side")
    print(f"             grille faces UP — {2 * GRILLE_B:.1f} x {2 * GRILLE_A:.0f} "
          f"ellipse, {GRILLE_LINES} tapering bars, bezel {BEZEL_PROUD:.1f} proud")
    print(f"  plate      {PL_Y1 - PL_Y0:.0f} mm long, {PLATE_T:.1f} thick, "
          f"{len(SCREWS)} x M2 — plate volume {plate.volume / 1000:.2f} cm3")
    print(f"  screen ap. {sx1 - sx0:.1f} x {sy1 - sy0:.1f} "
          f"(margins L/R {fx(SCREEN_SVG[0]) + PH_W / 2:.2f} / "
          f"{PH_W / 2 - fx(SCREEN_SVG[2]):.2f})")
