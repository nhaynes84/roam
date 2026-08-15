"""
ROAM Touch — the functional build of his concept. STEP 1: the phone housing.

★★ THE DEVICE IS A BOAT — his convention, the same one that stopped the eStack
orientation errors. Two anchors, everything else falls out of them:

    STERN      Y = 0        the USB / cap end          -> points at the WRIST
    BOW        Y = OUT_L    the jack end               -> points at the ELBOW
    STARBOARD  +X           buttons, rail, mic pod     -> toward the body midline
    PORT       -X           the pack tube              -> outboard, away from him
    UP         +Z           out of the screen, away from the arm

⚠️ It is self-consistent, not just a naming: facing the bow (+Y) with +Z up, the
right-hand rule puts starboard at +X — which is where the buttons already are. So
"USB is stern, buttons are starboard" fixes every other direction with no room to
argue. WORN ON THE RIGHT FOREARM, ON TOP, so starboard is the inboard flank and
his eye is over it; port is the deep outboard flank the pack tube hangs off.

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
# ⚠️⚠️ THE BEZEL IS AN ANGLE, NOT AN OFFSET — and 30°, not 58°. From the first
# rough print: *"the screen bezel can't be a 45, it's too steep, it needs to be
# like 30 degrees instead so i can 'slide' down the tray and use the edges of
# the screen correctly."* It was 1.5 out over 2.4 up = 58° from horizontal,
# which his thumb hits as a wall rather than a ramp. 30° needs 4.157 of run.
BEZEL_ANGLE = 30.0   # from HORIZONTAL — a ramp onto the glass, not a chamfer

# ⚠️ THE JACK END CANNOT BE 30° AND KEEP THE PROX RIB. There is 1.45 mm of lip
# between the screen aperture and the proximity window, so a 4.157 run eats it
# and stops 0.44 mm short of the prox's far edge, leaving a sliver. Running it
# the full 4.60 instead ABSORBS the prox into the bezel recess: one tapered
# opening rather than a hole with a knife-edge rib beside it. The prox sees out
# better, not worse, and the lip still grips the phone at face level.
# ★ It is one number — set BEZEL_RUN_JACK to 0.30 to keep the rib instead.
BEZEL_RUN_JACK = 4.60

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
# ⚠️⚠️ This USED to be spelled out as PH_L + 2*CLR + JACK_CAV + WALL with the
# comment "= OUT_L". It stopped being equal the moment the retained end wall
# added 2.4 mm to OUT_L, and the tube quietly ended 2.4 mm short of the housing
# for every build since — a step at the jack end that no probe was looking for.
# ★ Derive it, never restate it. TUBE_LEN is set to OUT_L in the derived block.
TUBE_LEN = None

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
# ★★ MEASURED OFF HIS MODEL — `RoamTouchLatestDemo.step`, 2026-08-13, "i fixed
# it". He did not reshape anything: he took 9.2 cm3 out of the rail and nothing
# else, dropping its top from 4.2 all the way to −0.8 (what had been only the
# mic's local dip) and letting the existing 0.92 ramps run further to reach it.
# The dip is therefore GONE — the whole rail sits at the dip's level now, which
# is why the buttons have 5.25 mm of clearance instead of 0.25.
RAIL_TOP = 0.1        # ⚠️ his cleanup: was −0.8
RAMP_SLOPE = 0.92     # rise per mm of Y — 42.6°, unchanged from mine
RAIL_FLAT_Y0 = 15.30  # where the USB-end ramp lands on the flat
RAIL_FLAT_Y1 = 134.63 # where the jack-end ramp leaves it
# ⚠️ NOT symmetric, and deliberately his: the USB ramp's apex falls 0.14 mm off
# the end of the part while the jack end keeps 11.34 mm of flat. Owner: *"the
# bottom right isn't perfectly symmetric because we also don't have the base
# plate yet so I'm just guestimating."* Leave it until the plate exists.
# ★★ Owner: *"the way you have the ramp on that top side, you should mirror it
# on the botom, even if it doesn't do anything functional."*
#
# ⚠️⚠️ I read "top / bottom" as the rail's two FACES and dropped its underside by
# 9.2 mm. Wrong axis entirely. He meant the two ENDS — and said so plainly when
# I got it back to him: *"you have a ramp down to a rail that runs to a mic and
# then keeps going past and just terminates, it doesn't ramp back up on the
# other side."* The rail rose to full height at the jack end and simply stopped
# square at the USB end. So the ramp is mirrored END TO END, and the whole
# profile is now symmetric about MIC_Y — which is also OUT_L/2.

# ★ It hangs BELOW the base plane, like the tube does on −X, and that is what
# buys the channel its height. At |X| 38–51 the arm (r ~49) has already fallen
# ~30 mm away, so there is nothing down there to foul — the same argument that
# let the tube drop. A flat base at the +X edge would be flatness for its own
# sake, and it would cost the channel 6 mm it has nowhere else to find.
# ★ −12.0, and it costs nothing: the tube already hangs to −12.4, so the
# bounding box does not move. Owner: *"we need more room for the mic, it can't
# just be a flat rail."* This is the free half of that room — 2 mm of chamber
# height for no size at all, and it lands the two spines at the same depth.
RAIL_Z0 = -12.0

# ⚠️ 4.0, and it moved inboard. At 4.5 centred, the outboard LAND was 3.0 mm —
# an M2 pilot down the middle of that leaves 0.65 mm of wall each side, which
# splits the first time it is driven. The groove gives up 0.5 mm it does not
# need (a lav lead is 2–3 mm) so the screws get 1.25 mm of wall instead.
CH_W = 4.0            # cable channel, generous for a 2–3 mm lav lead
# ⚠️⚠️ THE CHANNEL WAS OPEN. Its roof was at +2.0, which was under the old
# 4.2 rail top and is 2.8 mm ABOVE the new one — so lowering the rail turned the
# groove into a slot straight through the part, open at the top and opened at
# the bottom by the plate rebate. Owner: *"it just needs the channel closed."*
# Roof is now GRILLE_FACE thick, so the skin over the cable and the skin the
# grille bars are cut through are the same 1.5 mm.  CH_Z0 is PLATE_TOP.

# ⚠️ The channel is open at the BOTTOM for its whole length, not a blind bore.
# Threading a lead down 70 mm of buried tunnel is a job nobody does twice; laying
# it into an open groove and screwing a plate over it is a job you do once.
PLATE_T = 2.0         # the removable service plate
PLATE_CLR = 0.25

# The mic blister: centred on the side, sitting entirely below the button line.
# ★★ THE MIC CHAMBER. A d6.4 x 4.1 pocket was all a flat 9.5 mm rail could hold
# — fine for a bare 6 mm electret, useless for an actual lav head. The rail now
# SWELLS at the mic: outboard to 52.0 with 42.6° tapers, the same angle as the
# end ramps, and ⚠️ **the top stays dead flat at RAIL_TOP.** All the growth is
# outboard and downward, because up is where the volume rocker's approach is —
# that is what killed the old blister and it has not stopped being true.
MIC_SWELL_X1 = 52.0
MIC_SWELL_HALF = 10.0     # flat span either side of the mic
MIC_SWELL_BITE = 1.0      # ⚠️ starts inside the rail's face, never on it
# ★ The chamber reaches inboard to CH_X0 — it and the cable groove are one void,
# which is how the lead gets to the capsule without a separate connecting cut.
MIC_CH_X1 = 50.90
MIC_CH_L = 19.0

# ★ Owner: *"i might even put a little bit of black screen on the underside too
# for vibes."* A pocket in the chamber's CEILING, so the mesh sits right against
# the back of the slots and reads as black through them instead of showing the
# capsule. ⚠️ It must be SMALLER than the chamber, not larger — a pocket wider
# than the chamber is an undercut you cannot get the mesh through.
MESH_T = 0.5
MESH_W, MESH_L = 10.0, 17.0

# ★★ GRILLE LINES, not a hole pattern. Owner: *"i do want grille lines though
# regardless."* Slots, tapering to a circle — which is his concept's round
# grille, and the one element on this thing that says it is not a phone in a box.
#
# ⚠️ Lines over a d7 pocket would go blind at their ends, so there is a PLENUM
# behind the face: the slots all open into one CHAMBER, so none of them
# necks down to the capsule. Every line is through-air for its whole length.
# ⚠️⚠️ It faces UP, not outboard. Owner: *"it faces forward, not up, i'll be
# looking down at this thing, my voice will be coming basically straight down."*
#
# ★★ STRAIGHT EQUAL SLOTS ACROSS THE SWELL — his, chosen against my elliptical
# tapering version: *"i had 1mm slot widths, 1.5 between, i would even put one
# more on each end; i like the aesthitic better too."*
#
# He is right and the reason is consistency: every other cut on this object is a
# straight line at a fixed angle — the end ramps, the swell's tapers, the tray.
# The ellipse and its bezel were the only curves on the part besides the battery
# tube, so they read as imported from a different design. Same mix he called out
# on the fillets. THE BEZEL IS GONE with them.
#
# ⚠️ Slots run along X (across the rail), NOT along Y. At 9 mm they are 6 mm
# shorter than the old bars, so they are stiffer and print without drooping.
# ⚠️ Ingress is a non-issue by his ruling: *"not worried about shit getting into
# it, i can clean it, the bottom comes off."* Do not add a lip to solve it.
GRILLE_FACE = 1.5     # face the slots are cut through
GRILLE_W = 1.0        # slot width — his number
GRILLE_GAP = 1.5      # web between — his number
# ★★ MEASURED OFF `RoamTouchBetterGrille.step` — his, and better than my version
# in three ways at once, all of which I had missed:
#
# 1. THE SLOTS TAPER. Not the field, the slots: each one's INBOARD end pulls
#    back as you go out from the middle, so the set reads as a lens while every
#    cut stays dead straight. That is the taper I lost when I dropped the
#    ellipse — recovered without a single curve in the grille itself.
# 2. THEY BREAK OUT THROUGH THE OUTBOARD FACE. They do not stop in the top
#    face; they run over the corner and open on the side, so the grille reads
#    from the side as well as from above. That is the vintage-mic wrap.
# 3. The corner they wrap is CHAMFERED — ⚠️ **chamfered, not rounded.** I fitted
#    a radius to it and got told: *"i didn't round, i chamfered the corner, which
#    we're going to do in a lot of places later so it will read consistent."*
#    Measured off his: dx/dz = −1.000 the whole way, i.e. exactly 45°, exactly
#    1.0 x 1.0, from (51.00, −0.80) to (52.00, −1.80). ★ CHAM_45 is the house
#    chamfer from here on — every edge that gets softened gets this one, so they
#    read as a set rather than as one-off decisions.
#
# ⚠️ The inboard ends are HIS NUMBERS, not a curve I refitted. I tried: they are
# not a circle (0.5–0.65 mm off) and not an ellipse either. He drew it by eye.
SLOT_X_IN = (45.00, 42.60, 41.00, 39.80, 39.80, 41.00, 42.60, 45.00)
SLOT_X_OUT = 54.0     # past the face — the slots vent out the side

# ⚠️⚠️ THE SLOTS ARE FULL HEIGHT, not a cut through the 1.5 mm face. Owner:
# *"you're having trouble cutting through the side wall."* Mine stopped at the
# face's underside, which left the outboard wall intact — from the side you saw
# a solid band with the slots barely nicking its top edge. His run from the top
# face all the way down to Z −10.6, so the outboard wall survives only as seven
# ribs (the webs) tied by a 1.4 mm rail along the bottom. That is why his reads
# as a grille from the side and mine read as a slotted lid.
# ⚠️⚠️ AND THEY TAPER ON THE BOTTOM TOO. Owner: *"not all the way down, the cuts
# taper on bottom to mirror the depth taper on the top face."* Each slot's DEPTH
# tracks its length, so the openings in the side wall form the same lens the
# slots form on the top face — the grille reads as one shape from both views.
#
# ⚠️ My error was method, not arithmetic: I bisected slot 4's bottom, found
# −10.6, and generalised from ONE sample. Measure every one, every time — his
# numbers are drawn by eye and are not a formula (the bottom steps are 4.40 /
# 2.60 / 1.30 against the top's 5.20 / 2.80 / 1.20; close, deliberately not equal).
SLOT_Z_BOT = (-6.20, -8.00, -9.30, -10.60, -10.60, -9.30, -8.00, -6.20)
CHAM_45 = 1.0         # ★ the house chamfer — 45°, used everywhere from now on
GRILLE_LINES = len(SLOT_X_IN)
GRILLE_PITCH = GRILLE_W + GRILLE_GAP

# --------------------------------------------- STEP 5: the glare surround
# ★★ MEASURED OFF `RoamTouchSurroundStep1.step`. He answered a question about
# this with geometry instead of words, which is the fastest either of us has
# communicated all night.
#
# Walls on THREE sides — the tube side and both ends — and the button/mic side
# stays open. That is the side his thumb comes in on and where the buttons,
# grille and rail all live, so a wall there would be in the way of everything.
#
# ★ The footprint is exactly the flat lip the 30° bezel leaves behind, so each
# wall's inner face springs straight off the TOP of the ramp — no ledge, no
# second edge. Ramp and wall are one surface turning a corner.
#
# ⚠️ 11.0 above the lip puts the top at 24.40, which is 2.4 ABOVE the tube's
# crown. The surround is the tallest thing on the object, not the tube.
# ⚠️ 5.0, not 11.0 — his cleanup. At 11 the walls stood 2.4 ABOVE the tube's
# crown and the surround was the tallest thing on the object. At 5 the tube
# takes the silhouette back and the well is still deep enough to shade the
# glass at the angles that matter.
SURROUND_H = 5.0

# ----------------------------------------------- STEP 6: the flush end cap
# ★ It closes the USB end (Y = 0), which is where BOTH the phone and the pack
# load and where BOTH their ports face. Owner: *"flush cap has to have space to
# connect the charger usb to the phone in it"* — so the cap is not a lid, it is
# a room: the phone's USB-C plug, the pack's lead and the jumper between them
# all live inside it.
#
# ⚠️ It sits at NEGATIVE Y, Y −CAP_L … 0. That is deliberate: every measured
# number in this file is referenced to Y = 0 at the USB end, and growing the
# model in −Y leaves all of them untouched. Overall length grows by CAP_L.
#
# ⚠️ FLUSH means no wrap-over — he dislikes the lip on the Basic. So the cap is
# a prism of the housing's own section at Y = 0 and retention moves INSIDE:
# a spigot into the pack bore locates it, two screws hold it.
CAP_L = 18.0
CAP_WALL = 2.4        # the closed end face
CAP_CLR = 0.25        # fit clearance on the spigot
CAP_SPIG_L = 12.0     # how far the spigot reaches into the pack bore
CAP_SPIG_WALL = 1.8
CAP_LEAD_W = 7.0      # slot in the spigot for the pack's lead to pass
CAP_SCREW_X = 20.0    # ★ into the SURROUND's end block — the only place at this
CAP_SCREW_D = 8.0     # end with real depth of material behind it

# ⚠️⚠️ The cap's bore is NARROWER than the housing's, and it has to be. The
# spigot's wall sits at TUBE_BORE_R − CAP_CLR − CAP_SPIG_WALL; if the cap's own
# bore is cut at TUBE_BORE_R it removes exactly the ring the spigot springs
# from, and the spigot comes out as two loose arcs floating in space. The model
# still exports, still looks right in a render, and is three separate solids.
# ★ The step this leaves at Y = 0 is useful anyway: it is the pack's stop.
CAP_BORE_R = TUBE_BORE_R - CAP_CLR - CAP_SPIG_WALL

# ------------------------------------------------- his cleanup: the jack end
# ★ A 45° chamfer around the WHOLE jack end — top, sides and underside — the
# same house angle as everything else. Measured off his file: the tube's crown
# starts falling at Y 154.3 and the cone's radius drops 1:1 with Y.
# ⚠️ NOT applied in this model, deliberately. OCCT refuses it above ~2 mm on
# this end, and that refusal is diagnostic rather than a tool limitation: 7.1
# is wider than the 9.5 mm rail and nearly 3x the 2.5 mm tube wall, so the cut
# has nothing to land on. It is also exactly why his file has holes. The jack
# end stays HIS to shape; this constant records what he used.
END_CHAM = 7.1

# ⚠️⚠️ AND THIS IS WHY THE TUBE HAD HOLES IN IT. Owner: *"fill in the holes i
# made in the tube."* The tube wall is 2.5 mm; a 7 mm chamfer on the end goes
# straight through it and opens the pack bore, so his file is missing wall from
# Y 146 to 161, spreading from the underside round to the crown. The fix is not
# to patch the holes — it is to STOP THE BORE SHORT so the chamfer never
# reaches it. 145 leaves the bore 38 mm longer than the pack needs.
BORE_END_Y = 145.0     # end with real depth of material behind it

# --------------------------------------------------------------- derived
POCK_L = PH_L + 2 * CLR
POCK_W = PH_W + 2 * CLR
POCK_D = PH_T + 0.3

OUT_W = POCK_W + 2 * WALL          # 75.1 — tray outer width
OUT_L = POCK_L + WALL + JACK_CAV + WALL   # pocket, its wall, plug cavity, end
OUT_H = FLOOR + POCK_D + LIP_H     # 13.4
TUBE_Z = OUT_H - TUBE_AXIS_BELOW_FACE
TUBE_BULGE = TUBE_Z + TUBE_R - OUT_H        # crown standing above the face

TUBE_LEN = OUT_L                        # ★ derived, not restated — see above

PHONE_TOP_Y = POCK_L - CLR
SURROUND_TOP = OUT_H + SURROUND_H
CAP_CAV = CAP_L - CAP_WALL              # the room inside it
CAP_SCREW_Z = OUT_H + SURROUND_H / 2    # mid-height of the surround block

# The USB-end ramp, placed so the low run is symmetric about the housing centre.
RAIL_TOP_Y0 = RAIL_TOP + RAIL_FLAT_Y0 * RAMP_SLOPE      # the rail's top at Y=0
RAIL_APEX_Y = RAIL_FLAT_Y1 + (OUT_H - RAIL_TOP) / RAMP_SLOPE

RAIL_X0 = OUT_W / 2
RAIL_X1 = RAIL_X0 + RAIL_W
CH_X0 = RAIL_X0 + 1.3               # ⚠️ NOT centred — biased inboard so the
                                    # outboard land can carry the screws
CH_X1 = CH_X0 + CH_W

MIC_Y = OUT_L / 2                   # "centered on the right side"
MIC_X = (RAIL_X0 + MIC_SWELL_X1) / 2   # ★ centred on the SWELL, which is what
                                       # the eye reads as the mic housing
MIC_SWELL_TAPER = (MIC_SWELL_X1 - RAIL_X1 + MIC_SWELL_BITE) / RAMP_SLOPE
GR_Z = RAIL_TOP                     # the grille is flush in the rail's top
CH_Z1 = RAIL_TOP - GRILLE_FACE      # ★ the roof that closes the channel
MIC_CH_TOP = CH_Z1                  # the chamber's ceiling is that same skin

# ⚠️ Ends at 152.5 so the riser clears the plate's top screw at Y 154 — at 154
# the screw was drilling into the cable riser and had no land at all.
EXIT_Y0, EXIT_Y1 = 147.0, 152.5     # the hole in the top right
EXIT_Z0, EXIT_Z1 = 3.5, 8.5         # inside the plug cavity's 2.2 – 10.7
CH_Y1 = EXIT_Y1 - 2.0
# ⚠️ The blister reaches 1 mm INTO the tray wall and the bezel sinks 0.2 into the
# blister. Both were landing exactly on their neighbour's face, and a union
# across coincident planes tessellates to a non-watertight seam — `watertight
# False` with every probe still passing, which is the quiet kind of broken.

# ★ With the underside flat again the plate runs the WHOLE groove, so the cable
# is laid into an open channel end to end rather than fished down a tunnel.
# ⚠️ Back to −15, which is where his plate sits. I had moved it to −18 when the
# chamber was 21 long and the first screw's pilot broke into it; his chamber is
# 19, so −15 clears again by 0.65 mm. Chamber length and plate datum are coupled
# — change one and re-probe the other.
PL_Y0, PL_Y1 = MIC_Y - 15.0, 156.0
# ⚠️ Wider than the groove needs, because the run's screws cannot sit on the
# groove's centreline — there is no material there. They move to the outboard
# land, and the plate has to reach them.
PL_X0, PL_X1 = RAIL_X0 + 1.0, RAIL_X1 - 0.55
PL_HEAD_X1 = MIC_SWELL_X1 - 1.0     # it widens under the swell to free the mic
PL_HEAD_L = 2 * MIC_SWELL_HALF - 2.0
PLATE_TOP = RAIL_Z0 + PLATE_T
CH_Z0 = PLATE_TOP - 0.5             # ⚠️ overlaps the rebate, never kisses it
_SX = (CH_X1 + RAIL_X1) / 2         # ★ centred on the outboard LAND, not the
                                    # groove and not the plate — the groove's
                                    # centreline has no material in it at all.
SCREWS = [(_SX, PL_Y0 + 4.0 + i * (PL_Y1 - PL_Y0 - 8.0) / 3) for i in range(4)]


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
    # ⚠️ Up through the SURROUND, not just the lip. The earpiece and camera sit
    # under the jack-end wall, so a cut that stops at the lip leaves them buried.
    h = SURROUND_TOP - z0 + EPS
    cut = Part()

    # ★ The screen bezel — a RAMP at BEZEL_ANGLE, run per side so the jack end
    # can differ from the other three. Lofted between two rectangles that are
    # not concentric, which is the whole reason this is a loft and not an offset.
    # ⚠️ Anchored at the PHONE FACE and run off the true rise. Padding the loft
    # with EPS at both ends made it 32.0° instead of 30.0 and opened the glass
    # aperture 0.21 mm a side — the pad changes the angle, because the angle is
    # rise-over-run and EPS is part of the rise.
    sx0, sy0, sx1, sy1 = face_rect(SCREEN_SVG)
    zf = FLOOR + POCK_D                    # the phone's face — aperture is exact here
    t = math.tan(math.radians(BEZEL_ANGLE))
    lo, hi = -0.3, LIP_H + EPS             # lo dips into the pocket, which is void
    kj = BEZEL_RUN_JACK / (LIP_H / t)       # the jack end's own, shallower rate

    def rect_at(dz):
        r_, rj = dz / t, dz / t * kj
        return (Plane.XY.offset(zf + dz) *
                (Pos((sx0 + sx1) / 2, (sy0 - r_ + sy1 + rj) / 2) *
                 Rectangle(sx1 - sx0 + 2 * r_, sy1 - sy0 + r_ + rj)))

    cut += loft([rect_at(lo), rect_at(hi)])

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
    swell_pts = [
        (RAIL_X1 - MIC_SWELL_BITE, MIC_Y - MIC_SWELL_HALF - MIC_SWELL_TAPER),
        (MIC_SWELL_X1, MIC_Y - MIC_SWELL_HALF),
        (MIC_SWELL_X1, MIC_Y + MIC_SWELL_HALF),
        (RAIL_X1 - MIC_SWELL_BITE, MIC_Y + MIC_SWELL_HALF + MIC_SWELL_TAPER),
    ]
    swell = Pos(0, 0, RAIL_Z0) * extrude(
        Plane.XY * make_face(Polyline(*swell_pts, close=True)), RAIL_TOP - RAIL_Z0)

    prof = [(0, RAIL_Z0), (0, RAIL_TOP_Y0),
            (RAIL_FLAT_Y0, RAIL_TOP), (RAIL_FLAT_Y1, RAIL_TOP),
            (RAIL_APEX_Y, OUT_H), (OUT_L, OUT_H), (OUT_L, RAIL_Z0)]
    rail = Pos(RAIL_X0, 0, 0) * extrude(
        Plane.YZ * make_face(Polyline(*prof, close=True)), RAIL_W)

    return rail + swell


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

    # ★ One CHAMBER, floor to ceiling: it is the capsule's room and the grille's
    # plenum at once. ⚠️ Its floor is PLATE_TOP, so the capsule drops in from
    # below and the plate is what holds it up against the grille.
    cut += Pos((CH_X0 + MIC_CH_X1) / 2, MIC_Y, PLATE_TOP) * extrude(
        Plane.XY * RectangleRounded(MIC_CH_X1 - CH_X0, MIC_CH_L, 3.0),
        MIC_CH_TOP - PLATE_TOP)

    # ★★ The slots — straight, but each one shorter than the last, and running
    # out past the face so they wrap the rounded corner. See SLOT_X_IN.
    # ⚠️ Each slot is extruded from ITS OWN bottom, so they cannot share one
    # sketch — the depth taper is per-slot.
    for i, x_in in enumerate(SLOT_X_IN):
        dy = (i - (GRILLE_LINES - 1) / 2) * GRILLE_PITCH
        z_bot = SLOT_Z_BOT[i]
        # ⚠️ SQUARE ends, not SlotOverall. His are square, and a rounded end
        # domes visibly when you look down a slot — it was the giveaway in his
        # screenshot of my version. Everything else here is a hard edge too.
        bar = Pos((x_in + SLOT_X_OUT) / 2, MIC_Y + dy) * Rectangle(
            SLOT_X_OUT - x_in, GRILLE_W)
        cut += Pos(0, 0, z_bot) * extrude(Plane.XY * bar, GR_Z - z_bot + EPS)

    # ★ The mesh pocket, up into the ceiling — see MESH_*.
    cut += Pos(MIC_X, MIC_Y, MIC_CH_TOP) * extrude(
        Plane.XY * RectangleRounded(MESH_W, MESH_L, 2.0), MESH_T)

    # ★ The 45° chamfer the slots turn over. Built as a big right triangle whose
    # hypotenuse IS the 45° line through (MIC_SWELL_X1 − CHAM_45, RAIL_TOP), so
    # the angle is exact by construction rather than by fitting two legs.
    tri = [(MIC_SWELL_X1 - CHAM_45, RAIL_TOP),
           (MIC_SWELL_X1 + 6.0, RAIL_TOP),
           (MIC_SWELL_X1 + 6.0, RAIL_TOP - CHAM_45 - 6.0)]
    cut += Pos(0, MIC_Y, 0) * extrude(
        Plane.XZ * make_face(Polyline(*tri, close=True)),
        MIC_SWELL_HALF + EPS, both=True)
    return cut


def _plate_profile(clr: float):
    """A strip down the groove, widening to a head under the mic swell."""
    run = Pos((PL_X0 + PL_X1) / 2, (PL_Y0 + PL_Y1) / 2) * Rectangle(
        PL_X1 - PL_X0 - 2 * clr, PL_Y1 - PL_Y0 - 2 * clr)
    head = Pos((PL_X0 + PL_HEAD_X1) / 2, MIC_Y) * RectangleRounded(
        PL_HEAD_X1 - PL_X0 - 2 * clr, PL_HEAD_L - 2 * clr, 3.0)
    return run + head


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


def glare_surround() -> Part:
    """The three-sided wall around the screen — his, see SURROUND_H."""
    sx0, sy0, sx1, sy1 = face_rect(SCREEN_SVG)
    run = LIP_H / math.tan(math.radians(BEZEL_ANGLE))

    # The whole top face...
    ring = Pos(0, OUT_L / 2) * Rectangle(OUT_W, OUT_L)
    # ...less everything from the bezel's top edge outboard on +X. One cut does
    # both jobs: it opens the bezel AND leaves the button side wall-free.
    ring -= Pos((sx0 - run + OUT_W / 2) / 2, (sy0 - run + sy1 + BEZEL_RUN_JACK) / 2) * \
        Rectangle(OUT_W / 2 - sx0 + run, sy1 + BEZEL_RUN_JACK - sy0 + run)
    return Pos(0, 0, OUT_H - EPS) * extrude(
        Plane.XY * ring, SURROUND_H + EPS)


def cap_screw_pilots() -> Part:
    """Pilots in the housing's end face — cut into the HOUSING, not the cap."""
    cut = Part()
    for sx in (-CAP_SCREW_X, CAP_SCREW_X):
        cut += Pos(sx, -EPS, CAP_SCREW_Z) * Rot(-90, 0, 0) * Cylinder(
            1.25, CAP_SCREW_D + EPS, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return cut


def end_cap() -> Part:
    """The flush cap — a prism of the housing's own section at Y = 0."""
    y0 = -CAP_L
    p = Box(OUT_W, CAP_L, OUT_H, align=(Align.CENTER, Align.MIN, Align.MIN))
    p += Pos(0, 0, OUT_H) * Box(OUT_W, CAP_L, SURROUND_H,
                                align=(Align.CENTER, Align.MIN, Align.MIN))
    p += Pos(RAIL_X0, 0, RAIL_Z0) * Box(RAIL_W, CAP_L, OUT_H - RAIL_Z0,
                                        align=(Align.MIN, Align.MIN, Align.MIN))
    p += Pos(TUBE_X, 0, TUBE_Z) * Rot(-90, 0, 0) * Cylinder(
        TUBE_R, CAP_L, align=(Align.CENTER, Align.CENTER, Align.MIN))
    p += Pos(TUBE_X, 0, 0) * Box(abs(TUBE_X) - POCK_W / 2 - WALL, CAP_L, OUT_H,
                                 align=(Align.MIN, Align.MIN, Align.MIN))
    p = Pos(0, y0, 0) * p

    # ★ ONE room, not two. The phone's plug pocket and the pack's bore are
    # joined by a slot at plug height, so the jumper crosses between them
    # instead of needing a hole drilled through the tray wall later.
    cav = Pos(0, y0 + CAP_WALL, FLOOR) * Box(
        POCK_W, CAP_CAV + EPS, POCK_D, align=(Align.CENTER, Align.MIN, Align.MIN))
    cav += Pos(TUBE_X, y0 + CAP_WALL, TUBE_Z) * Rot(-90, 0, 0) * Cylinder(
        CAP_BORE_R, CAP_CAV + EPS, align=(Align.CENTER, Align.CENTER, Align.MIN))
    cav += Pos(TUBE_X, y0 + CAP_WALL, FLOOR + PH_T / 2) * Box(
        abs(TUBE_X) - POCK_W / 2, CAP_CAV + EPS, CAP_LEAD_W,
        align=(Align.MIN, Align.MIN, Align.CENTER))
    p -= cav

    # The spigot: reaches +Y into the pack bore to locate the cap, slotted so
    # the pack's own lead still gets past it.
    spig = Pos(TUBE_X, 0, TUBE_Z) * Rot(-90, 0, 0) * Cylinder(
        TUBE_BORE_R - CAP_CLR, CAP_SPIG_L, align=(Align.CENTER, Align.CENTER, Align.MIN))
    spig -= Pos(TUBE_X, -EPS, TUBE_Z) * Rot(-90, 0, 0) * Cylinder(
        CAP_BORE_R, CAP_SPIG_L + 2 * EPS,
        align=(Align.CENTER, Align.CENTER, Align.MIN))
    spig -= Pos(TUBE_X, -EPS, TUBE_Z) * Box(
        CAP_LEAD_W, CAP_SPIG_L + 2 * EPS, 2 * TUBE_BORE_R,
        align=(Align.CENTER, Align.MIN, Align.CENTER))
    p += spig

    for sx in (-CAP_SCREW_X, CAP_SCREW_X):
        p -= Pos(sx, y0 - EPS, CAP_SCREW_Z) * Rot(-90, 0, 0) * Cylinder(
            1.7, CAP_L + 2 * EPS, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return p


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
        TUBE_BORE_R, BORE_END_Y + EPS,
        align=(Align.CENTER, Align.CENTER, Align.MIN))


# ================================================================ THE SLEEVE
# ★★ STEP 7, his spec: a FLUSH-MOUNTED HALF-CIRCLE SLEEVE — **not ribs** — with slots
# at both ends for two velcro straps. He adds the comfort layer under the velcro.
# This is what kills the ~1 inch of stack (ribs + velcro + strap) and the roll: the
# housing base becomes a flat mounting face and the arm-conforming job leaves the
# housing entirely.
#
# ★ THE KEY MOVE: the arm's crown sits AT the housing's mounting plane, so the sleeve
# adds ZERO standoff. Its inner cylinder is therefore centred ARM_R below that plane
# and the shell only exists where the housing is not — which is why it is cut against
# the REAL housing solid rather than against my idea of the underside. The tube dives
# to Z −12.2 on −X and the rail sits at −0.4 on +X; conforming to that by hand would
# be three assumptions I would get wrong.
#
# ⚠️ ARM_R IS THE ONE NUMBER I CANNOT DERIVE. 45.0 is bracer.py's nominal, and it says
# so itself: "nominal, NOT critical, and that is deliberate". That was fine for a
# shallow saddle. A half-circle that WRAPS and takes strap tension is sized by the
# real limb — measure the forearm's circumference at the strap stations and set
# ARM_R = circumference / (2*pi). Everything below follows from it.
# ★ the mounting plane IS the rail top — the flat band the probe found running
# X −36..+34 at this Z, which is the only continuous flat on the underside.
MOUNT_Z = RAIL_TOP
# ★★ THE SLEEVE IS A TILTED CONE, NOT A CYLINDER. His call: *"i don't want something
# too tight and arms naturally taper"*. A constant radius binds at the elbow end and
# gaps at the wrist, and over 144 mm of forearm the taper is real — several mm of radius.
# ⚠️ AND THE AXIS HAS TO SLOPE. The arm's crown stays against the mounting plane for the
# whole length (that is what buys zero standoff), so as the radius grows toward the elbow
# the arm's CENTRE drops further below that plane. Axis from (MOUNT_Z − R_WRIST) at Y0 to
# (MOUNT_Z − R_ELBOW) at Y1. A horizontal axis would lift the crown off the plane at one
# end and bury it at the other.
# ⚠️⚠️ THESE TWO NUMBERS ARE PLACEHOLDERS — deliberately generous, not measured. Owner:
# *"that's a fitment dance we can do later."* They are the ONLY things to change when it
# happens; everything below is derived. Sized loose on purpose: include the comfort layer
# he adds under the velcro, and err large — a sleeve that is slightly loose is strapped
# down, one that is tight is a reprint.
ARM_R_WRIST = 40.0            # Y0 end — points at the WRIST (USB/cap end)
ARM_R_ELBOW = 50.0            # Y1 end — points at the ELBOW (jack end)
ARM_R = ARM_R_WRIST           # kept for anything that wants one number
SLEEVE_WALL = 3.0
SLEEVE_Y0, SLEEVE_Y1 = 8.0, 152.0
SLEEVE_Z_C = MOUNT_Z - ARM_R_WRIST   # crown on the mounting plane at the wrist end
STRAP_W, STRAP_T = 26.0, 4.0  # 25 mm webbing through a 26 x 4 slot
STRAP_Y = (24.0, 128.0)       # two straps, one near each end
# ★★ HOW FAR ROUND THE SLEEVE WRAPS — the one real shape decision, exposed as a number.
# The inner cone is TANGENT to the mounting plane (that is what gives zero standoff), so
# where you cut decides everything:
# ⚠️ IT KEEPS THE TOP HALF — it is a HOOD OVER the arm, not a trough under it. The arm
# comes UP into it from below and the straps close underneath. I built it the other way
# first and then could not explain why the part floated 40 mm below the housing held by
# nothing: keeping the lower half puts the material where the arm has to pass.
#   0.0  cut at the crown -> nothing left
#   1.0  cut at the axis  -> a true 180° hood, meeting the housing along the crown
# Anything less than 1.0 is a partial hood that grips further round the arm.
SLEEVE_OPEN = 1.0
STRAP_FRAC = 0.35             # slot height above the axis, as a fraction of the local radius


def sleeve() -> Part:
    """★ Half-circle arm sleeve, cut against the housing so it mates flush."""
    # ★ axis defined by its two END POINTS, so the crown rides the mounting plane the
    # whole way — same technique as the eStack drum's angled anchor, for the same reason:
    # a rotation I have to derive is a rotation I get wrong.
    a = Vector(0, SLEEVE_Y0, MOUNT_Z - ARM_R_WRIST)
    b = Vector(0, SLEEVE_Y1, MOUNT_Z - ARM_R_ELBOW)
    axis = (b - a).normalized()
    ln = (b - a).length
    pl = Plane(origin=a, z_dir=axis)
    shell = pl * Cone(ARM_R_WRIST + SLEEVE_WALL, ARM_R_ELBOW + SLEEVE_WALL, ln,
                      align=(Align.CENTER, Align.CENTER, Align.MIN))
    shell -= (Plane(origin=a - axis * EPS, z_dir=axis)
              * Cone(ARM_R_WRIST, ARM_R_ELBOW, ln + 2 * EPS,
                     align=(Align.CENTER, Align.CENTER, Align.MIN)))
    # ★ open the sleeve to SLEEVE_OPEN. ⚠️ The box must span Y generously: once the axis
    # slopes, the cone reaches past SLEEVE_Y1, and a box sized to the nominal length left
    # a 0.0 cm³ sliver stranded above the plane — two solids, and invisible in a volume.
    # ★ take the BOTTOM off, not the top: everything below the cut line goes, so what is
    # left hangs from the housing and is open underneath for the arm.
    cut_z = MOUNT_Z - SLEEVE_OPEN * ARM_R_WRIST
    shell -= Pos(0, SLEEVE_Y0 - 60, cut_z - 200) * Box(
        400, (SLEEVE_Y1 - SLEEVE_Y0) + 160, 200, align=(Align.CENTER, Align.MIN, Align.MIN))
    # and the wall still pokes above the crown, where the housing lives
    shell -= Pos(0, SLEEVE_Y0 - 60, MOUNT_Z) * Box(
        400, (SLEEVE_Y1 - SLEEVE_Y0) + 160, 200, align=(Align.CENTER, Align.MIN, Align.MIN))
    # ★★ cut against the REAL housing — the sleeve conforms to the tube and the rail
    # wherever they intrude, instead of me assuming a flat underside that is not there.
    shell -= build()
    # ★ TWO SLOTS PER STRAP, one at each side edge — the webbing goes out one slot,
    # around the arm, in the other, and velcros to itself. ⚠️ NOT an annular cut: a band
    # taken right round removes the whole wall and severs the sleeve into three pieces,
    # which is exactly what the first attempt did.
    # ⚠️ Slots must follow the SLOPED axis and the LOCAL radius. Placed off the wrist
    # radius alone they miss the wall entirely at the elbow end, where the axis has
    # already dropped 10 mm and the wall moved 10 mm outboard.
    for sy in STRAP_Y:
        t = (sy - SLEEVE_Y0) / (SLEEVE_Y1 - SLEEVE_Y0)
        rl = ARM_R_WRIST + t * (ARM_R_ELBOW - ARM_R_WRIST)
        zc = MOUNT_Z - rl
        zs = zc + STRAP_FRAC * rl
        xw = math.sqrt(max(0.0, rl * rl - (zs - zc) ** 2))   # wall's X at that height
        for sx in (-1, 1):
            shell -= Pos(sx * xw, sy, zs) * Box(
                2 * SLEEVE_WALL + 10, STRAP_W, STRAP_T,
                align=(Align.CENTER, Align.CENTER, Align.CENTER))
    return shell


def build() -> Part:
    p = tray()
    p += pack_tube()
    p += side_rail()
    p += glare_surround()
    p -= cable_route()
    p -= plate_rebate()
    p -= pack_bore()      # ★ last, so nothing can intrude — see pack_bore()
    p -= face_openings()
    p -= port_openings()
    p -= button_bores()
    p -= cap_screw_pilots()
    return p


if __name__ == "__main__":
    import os
    part = build()
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "out")
    os.makedirs(out, exist_ok=True)
    plate = service_plate()
    cap = end_cap()
    slv = sleeve()
    export_step(part, os.path.join(out, "roam_step3.step"))
    export_stl(part, os.path.join(out, "roam_step3.stl"))
    export_step(plate, os.path.join(out, "roam_plate.step"))
    export_stl(plate, os.path.join(out, "roam_plate.stl"))
    export_step(cap, os.path.join(out, "roam_cap.step"))
    export_stl(cap, os.path.join(out, "roam_cap.stl"))
    export_step(slv, os.path.join(out, "roam_sleeve.step"))
    export_stl(slv, os.path.join(out, "roam_sleeve.stl"))
    export_step(Compound(children=[part, plate, cap, slv]),
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
    _run = LIP_H / math.tan(math.radians(BEZEL_ANGLE))
    print(f"  surround   {SURROUND_H:.1f} mm walls to Z {SURROUND_TOP:.1f} — tube side "
          f"+ both ends, button side OPEN ({SURROUND_TOP - (TUBE_Z + TUBE_R):.1f} above "
          f"the tube crown)")
    print(f"  bezel      {BEZEL_ANGLE:.0f} deg ramp — {_run:.2f} mm of run over "
          f"{LIP_H:.1f} of rise, on three sides")
    print(f"             jack end runs {BEZEL_RUN_JACK:.2f} at "
          f"{math.degrees(math.atan(LIP_H / BEZEL_RUN_JACK)):.1f} deg — it ABSORBS "
          f"the prox window rather than leave a 0.44 sliver")
    print(f"             flat lip left: {sx0 + OUT_W / 2 - _run:.2f} / "
          f"{OUT_W / 2 - sx1 - _run:.2f} mm on the long sides")
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
    print(f"  side rail  +{RAIL_W:.1f} mm on +X, top {RAIL_TOP:.1f} — "
          f"{FLOOR + PH_T / 2 - BTN_BORE_H / 2 - RAIL_TOP:.2f} mm "
          f"of clear approach under the buttons (his geometry)")
    print(f"             flat Y {RAIL_FLAT_Y0:.2f}-{RAIL_FLAT_Y1:.2f}, ramps at "
          f"{math.degrees(math.atan(RAMP_SLOPE)):.1f} deg, "
          f"{OUT_L - RAIL_APEX_Y:.2f} mm of flat at the jack end")
    print(f"             hangs {abs(RAIL_Z0):.1f} below the base plane")
    print(f"  cable      exit {EXIT_Y1 - EXIT_Y0:.0f} x {EXIT_Z1 - EXIT_Z0:.0f} at "
          f"Y {EXIT_Y0:.0f}-{EXIT_Y1:.0f}, riser, then {CH_W:.1f} x "
          f"{CH_Z1 - CH_Z0:.1f} channel down to the mic")
    print(f"             CLOSED — {RAIL_TOP - CH_Z1:.1f} mm roof over the cable, "
          f"same skin the grille bars cut through")
    print(f"  mic        rail SWELLS to X {MIC_SWELL_X1:.1f} over Y "
          f"{MIC_Y - MIC_SWELL_HALF:.1f}-{MIC_Y + MIC_SWELL_HALF:.1f}, "
          f"tapers {MIC_SWELL_TAPER:.2f} mm at {math.degrees(math.atan(RAMP_SLOPE)):.1f} deg "
          f"— top stays flat")
    _cw = MIC_CH_X1 - CH_X0
    print(f"             chamber {_cw:.2f} x {MIC_CH_L:.1f} x "
          f"{MIC_CH_TOP - PLATE_TOP:.1f} = "
          f"{_cw * MIC_CH_L * (MIC_CH_TOP - PLATE_TOP) / 1000:.2f} cm3, "
          f"outboard wall {MIC_SWELL_X1 - MIC_CH_X1:.2f} mm")
    _span = (GRILLE_LINES - 1) * GRILLE_PITCH + GRILLE_W
    print(f"  grille     {GRILLE_LINES} straight slots, {GRILLE_W:.1f} wide on a "
          f"{GRILLE_GAP:.1f} web — HIS, tapering inboard "
          f"{min(SLOT_X_IN):.1f} -> {max(SLOT_X_IN):.1f}")
    print(f"             they BREAK OUT the side over a "
          f"{CHAM_45:.1f}x{CHAM_45:.1f} 45 deg chamfer, "
          f"lengths {' '.join(f'{MIC_SWELL_X1 - x:.1f}' for x in SLOT_X_IN[:4])} ...")
    print(f"             depths taper too — {' '.join(f'{GR_Z - z:.1f}' for z in SLOT_Z_BOT[:4])} "
          f"... (bottoms {min(SLOT_Z_BOT):.1f} to {max(SLOT_Z_BOT):.1f}), so the side "
          f"reads as the same lens the top does")
    print(f"             spans {_span:.1f} mm in a {MIC_CH_L:.1f} chamber "
          f"({(MIC_CH_L - _span) / 2:.2f} mm clear at each end), no bezel")
    print(f"             mesh pocket {MESH_W:.1f} x {MESH_L:.1f} x {MESH_T:.1f} in the "
          f"ceiling, {GRILLE_FACE - MESH_T:.1f} mm of face left over it")
    print(f"  end cap    {CAP_L:.1f} long at Y {-CAP_L:.1f}..0 — cavity "
          f"{CAP_CAV:.1f} deep, {POCK_W:.1f} x {POCK_D:.1f} at plug height")
    print(f"             joined to the pack bore by a {CAP_LEAD_W:.1f} mm slot, so "
          f"phone plug + pack lead + jumper share ONE room")
    print(f"             spigot d{2 * (TUBE_BORE_R - CAP_CLR):.1f} x {CAP_SPIG_L:.0f} "
          f"into the bore, slotted for the lead; 2 x M3 into the surround")
    print(f"             cap bore d{2 * CAP_BORE_R:.1f} — narrower than the housing's "
          f"d{2 * TUBE_BORE_R:.1f}, so the step at Y 0 is the pack's stop")
    print(f"             ⚠️ overall length {OUT_L:.1f} -> {OUT_L + CAP_L:.1f}")
    print(f"  plate      {PL_Y1 - PL_Y0:.0f} mm long, {PLATE_T:.1f} thick, "
          f"{len(SCREWS)} x M2 — plate volume {plate.volume / 1000:.2f} cm3")
    _sb = slv.bounding_box()
    print(f"  SLEEVE     {_sb.size.X:.1f} wide x {_sb.size.Y:.1f} long x {_sb.size.Z:.1f} deep, "
          f"{slv.volume/1000:.0f} cm3 ~= {slv.volume/1000*1.27:.0f} g PETG")
    print(f"             arm r{ARM_R:.1f} inside, crown AT the mounting plane Z {MOUNT_Z:.1f} "
          f"-> ZERO standoff, which is the whole point")
    print(f"             {2*len(STRAP_Y)} strap slots {STRAP_W:.0f} x {STRAP_T:.0f} at Y {STRAP_Y}")
    print(f"             ⚠️ ARM_R IS A GUESS (bracer.py nominal) — measure the forearm")
    print(f"  screen ap. {sx1 - sx0:.1f} x {sy1 - sy0:.1f} "
          f"(margins L/R {fx(SCREEN_SVG[0]) + PH_W / 2:.2f} / "
          f"{PH_W / 2 - fx(SCREEN_SVG[2]):.2f})")
