"""
ROAM Touch -- forearm bracer cradle for a Google Pixel (sailfish, 2016).

★★★ HOW IT IS WORN. Read this before touching any sign in this file. Three
separate analyses have been wrong because this was assumed instead of stated.

    RIGHT FOREARM, ON TOP OF THE ARM.
    Y = 0  is the USB END: cap, USB-C, speakers, card slot mouth.  It points
           at the WRIST.
    Y = OUT_L is the JACK END: 3.5 mm notch, closed tray wall.  It points at
           the ELBOW.
    +Z is out of the screen, away from the arm.
    +X is therefore Y x Z = toward the wearer's LEFT = TOWARD THE MIDLINE,
           because the device is on the RIGHT arm.  -X is outboard.
    The screen tilts TOWARD +X so it faces him at rest, which makes +X the
           SHALLOW flank (the edge that rolls down toward the arm) and -X the
           DEEP one.  His eye is over the shallow, inboard flank.
    The GUARD therefore stands on the DEEP, OUTBOARD (-X) flank, away from
           the eye: it shades instead of clipping.

★ WHY the USB end is at the wrist, which is the part that gets re-derived and
lost: it is where his free hand reaches. Cap off, card out, cable in -- all
service happens at the end nearest the hand. Reaching across the forearm
toward the elbow to wiggle a cap off and pull a card out one-handed is awkward
before you even try it. It is an ergonomic decision, not an axis convention.
Consequences that fall out of it and are checked in verify_bracer.py: the card
channel loads from the USB end, so cards are reachable; and charging while
worn pulls at the wrist rather than across the elbow.

Form: the phone housing (pocket, screen aperture, sensor holes, print-in-place
buttons, jack notch) is a frozen tray. Around and under it sits a LOW-POLY
TESSELLATED HULL: a rounded, chunky body approximated by planar facets.

★★ 2026-08-12 -- WHAT "LOW POLY" MEANS, because this file had it wrong from the
start and the owner finally said so: "we didn't even hit low poly, I just
stopped saying it." It had been read here as "few large flat faces, no curves",
which is a PRINTABILITY constraint, and the result was a chamfered box with two
big flat flanks -- "we still have hard cuts sides". The references in
ref/lowpoly-*.png (a printed hand, polygon owls, a faceted bulb) settle it:

    LOW POLY IS A SCULPTURAL STYLE. A rounded form approximated by MANY visible
    planar facets of varying size and angle, each catching the light
    differently. Sharp creases, no chamfers, deliberately irregular.

So the form gets ROUNDER and is then chorded into flats -- the opposite of
rounding the corners of a slab. And it is how the two references stop fighting:
★ THE PIP-BOY GIVES THE BONES (proportion, chunk, the sunken visor, a cuff on
the forearm); LOW POLY GIVES THE SURFACE. A wrist device with Pip-Boy bones,
rendered in facets. Nothing is split down the middle.

★★ ROUND TWO, same day: EVERY SURFACE, NOT THE SIDES. The pass above
tessellated the flanks and the cuff, because the flanks were what had been
complained about, and left everything a section loft cannot reach exactly as
built -- the deck round the screen, the guard's outer wall, the tray's own side
walls, the guard's two crest ramps and BOTH END FACES. Single planes, the
largest of them 2883 mm2. Owner, looking at the result: "still looking at a
flat top wall". The facet census in verify_bracer.py reported green throughout,
because it had been scoped to the surface it had already fixed.
Those surfaces are now carved by FACETED PANELS (see facet_shave): a jittered
point cloud over a flat panel, each point pushed in by a depth its own budget
allows, Delaunay-triangulated, and the volume in front of the result
subtracted. Subtraction only -- it cannot grow the envelope, bury a plunger or
eat into the 4 mm FOAM relief. The census now covers the WHOLE EXTERIOR SKIN of
both solids with a named exclusion list, and the largest facet anywhere is
311 mm2 against a 500 limit.
⚠️ There is NO exempt face. The elbow end was argued for as "the print bed, it
has to stay flat"; the owner rejected that outright -- "don't let print
orientation delegate design", "i can get creative or just use trees, if the
design comes first, that's the main thing". Supports are acceptable. The print
study still measures and prints unsupported area; it no longer FAILS on it, and
nothing in this file is shaped to move that number.

How the shell is built, and why this construction rather than a mesh:
  * ONE section polygon, stated as ARCS (the flanks bow FLANK_BULGE proud, the
    chine bows, the cuff follows the forearm) and delivered as chords -- facet
    angle is (arc angle / chords), ~22 deg here, so it is a number you set;
  * swept through STATION_N stations, each a UNIFORM SCALE of that section plus
    an offset, walked rather than jittered independently;
  * ruled-lofted between consecutive stations.
★ Uniform-scale-plus-offset is the whole trick: for an edge (A,B), the quad
(s0*A, s0*B, s1*B, s1*A) is planar exactly when s1*(B-A) is parallel to
s0*(B-A). Any other per-station change makes the lateral faces ruled surfaces,
which are not flat and are not low poly. So every hull face is a PLANE, and it
exports as a plane in the STEP.
★★ And it is why it still prints. Standing on the jack end maps model +Y to
print -Z, so a facet's ny IS its downward component; ny ~ dR/dY, and with the
station amplitude an order of magnitude under the station spacing the worst
facet is a few degrees off vertical. verify_bracer.py measures it.

★★ THE UNDERBELLY IS A CUFF (2026-08-12). Owner: "a weird underbelly", it is
"cut off flat beneath it". It was: the deep flank wrapped the arm to 40 deg and
closed on a chine, while the SHALLOW flank simply ran into the cylinder wherever
the two happened to cross -- 25.3 deg -- and terminated on a zero-thickness
razor. Sliced on one side, wrapped on the other. Now both sides leave the arm at
the SAME wrap angle and close on a radial HEM CUFF_T thick, so the shell
embraces the forearm symmetrically even though the tray on top of it is tilted
25 deg. It costs width (80 -> 96 mm) and no height. Over each strap band the
cuff is slotted right through, so the webbing leaves through a slot instead of
under a 0.8 mm flap -- which also breaks the cuff into three plates.

The ribs and the louvres that used to decorate the chine are both gone. There
is no blank facet left for them to fix.

The END CAP is part of the same body, not a collar bolted to it: the hull's
nose steps in by the cap's wall thickness below the belt line, so the cap's
outer surface IS the hull's section and the joint has no step in it.

The hollow under the tray carries TWO ID-1 CARDS (a bank card and a licence),
in a channel formed by two C-rails hung from the tray floor. They load from
the USB end and the cap is what retains them.

The screen sits in a WELL with a raised hood around it -- a 15 mm wall on the
deep flank, a matched pair of ramped brows at the two ends, nothing on the
shallow flank where his eye is. Taken from the Pip-Boy 3000 in ref/. The CHINE
carries two PROUD RIBS; the cut louvres that used to be there are gone, and so
is the blank keel they moved off.

WORN ON THE RIGHT FOREARM, ON TOP. TILT is positive for that and the reasoning
is written out at the parameter -- do not flip it back.

⚠️ The section bevel is GONE. Chamfering a facet crease is exactly what made
this read as a chamfered box, and the low-poly references have no chamfers
anywhere -- the creases between facets ARE the surface. CHAMFER survives only on
the visor rim and the cap's face, where it is relief on a frozen feature.
verify_bracer.py audits every sharp exterior crease and classifies it, and its
FACET CENSUS is the regression test: no facet on the exterior skin of EITHER
solid may exceed 500 mm2 (the old flank was ~2900, the elbow end 2883).

★ Every facet is a PLANE and exports as one in the STEP -- the loft's because
uniform-scale-plus-offset makes them planar, the panels' because they are
literally triangles. There is nothing curved on the exterior for the mesher to
approximate except the arm saddle and the guard's scoops.

Printing: it is 147 mm long and it will want support somewhere whichever way it
goes up. Standing on the ELBOW end is still the best of the five orientations
the harness scores, and it is what out/bracer_print.stl is rotated into, but
the end is faceted now so the bed contact is a few cm2 of scattered facet tips
rather than a flat land -- it wants a brim, and probably trees. That is a
slicer decision and it is deliberately NOT a design input; see the note in the
print study. (⚠️ -pi/2 about X sends +Y to -Z, which stands it on the JACK end
= the elbow. That label has been wrong in both directions before now.)

Geometry note -- the constraint that drives the shape:
a ~75 mm wide flat tray on a 90 mm diameter forearm has ~20 mm of sagitta, and
the 25 deg tilt adds its own. That wedge is unavoidable for a rigid slab. What
is optional is whether it is enclosed -- and outboard of the payload and the
arm, it is not.

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
from scipy.spatial import Delaunay
import numpy as np
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
LIP_END = 4.0        # front lip at the jack end
LIP_H = 2.4          # lip height above the phone face (also screen standoff)
BEZEL_CHAM = 1.5     # how far the aperture opens out at the top face

# ★ Screen tilt. Worn flat on the forearm the display points at the ceiling,
# so you have to rotate your whole arm to read it. Tilting the tray relative
# to the arm puts it in your eyeline at rest.
# Implemented by tilting the ARM CUT rather than the tray: the tray, pocket
# and every aperture stay in a clean axis-aligned frame, and only the rib
# profile changes. Rotating the tray instead would drag every feature with it.
# ★★ SIGN DERIVED, NOT CHOSEN. See the orientation block at the top of the file
# for the frame; the chain is:
#   * the arm cut is ROTATED by TILT, which is the same as rotating the tray by
#     -TILT relative to the arm. So the screen's normal, in the arm's frame, is
#     (-sin TILT, 0, cos TILT).
#   * for the screen to face +X -- the midline, where his eye is -- that needs
#     -sin TILT > 0, so TILT must be NEGATIVE.
#   * negative TILT puts the arm cut's axis at +X, so the +X edge rolls down
#     toward the arm (SHALLOW) and -X lifts away (DEEP). Screen faces the
#     shallow flank; the eye is over the shallow flank; the deep flank is the
#     far side. That is the invariant, and it holds for either sign.
# ⚠️ It was +20 until 2026-08-12, which pointed the screen OUTBOARD, away from
# him. The error was not the sign in isolation -- it was reading Y=0 as the
# elbow. Getting the end right flips X, and flipping X flips this.
TILT = -25.0         # degrees

ARM_R = 45.0         # nominal forearm radius, mm (90 mm dia)
# ------------------------------------------------------------ the payload
# ★★ DECLARED BEFORE THE HULL, ON PURPOSE. The outer body is derived from this
# stack, not the other way round: whatever is actually carried under the tray
# sets how deep the body goes, and nothing else does. Written the other way
# round -- hull first, contents fitted into it afterwards -- is what produced
# the blank corner the owner spotted on 2026-08-12 ("you added a corner and a
# bunch of material at the bottom where nothing sits").
CARD_L, CARD_W, CARD_T = 85.60, 53.98, 0.76   # ISO/IEC 7810 ID-1
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
# ★ A COMMERCIAL card-format bank, not a cell: 85.6 x 54 x 10, the ID-1
# footprint the card channel already uses, just far thicker.
PACK_L, PACK_W, PACK_T = 85.6, 54.0, 10.0
PACK_CLR = 0.6
PACK_RAIL, PACK_ENG, PACK_LEDGE = 3.0, 3.0, 1.6
# ⚠️ 1.8 mm of divider between the card channel and the pack, not 0.6. The
# rails are where the two channels share a floor and 0.6 read as 0.60 mm of
# wall. That 1.2 mm is what took GAP from 20 to 21.
CARD_SH = CARD_N * CARD_T + CARD_SLACK
PACK_Z1 = -CARD_SH - 1.8                 # just clear of the cards above
PACK_Z0 = PACK_Z1 - (PACK_T + 0.4)
# ★ THE ONE NUMBER THE HULL IS DERIVED FROM: the underside of the deepest
# thing carried under the tray. Below this line the body houses nothing.
PAYLOAD_Z = PACK_Z0 - PACK_LEDGE

# ★★ GAP IS THE VOLUME KNOB, TILT IS THE ERGONOMIC ONE. They were conflated
# for a round and the arithmetic settles it. The cavity's ceiling is the tray
# floor and its floor is the arm cut offset by WALL_ARM, so the deepest thing
# that fits under the card channel is set by the CROWN of the arm:
#     Z_crown  = ARM_R*(1 - cos TILT) + WALL_ARM - GAP
#     standoff = OUT_H + GUARD_H + GAP + FOAM - ARM_R*(1 - cos TILT)
# Put the first at the depth a payload needs and substitute into the second and
# the ARM_R term cancels: STANDOFF IS 46.7 mm FOR EVERY TILT. Tilting further
# buys exactly zero volume at constant thickness on the arm -- all it does is
# force GAP up by the same amount it lowers the crown. So tilt for the eyeline
# and nothing else, and buy volume with GAP.
# The stack that has to clear the crown is cards 1.8 + divider 1.8 + pack 10.4
# = 14.0 mm, plus margin. 23.0 gives it 1.8 mm of air and puts the whole
# assembly 51 mm off the arm's skin. That is the price of the pack, and it is
# a GAP price, not a TILT one. See the report.
# ⚠️ AND IT IS NOT WHAT MADE THE BODY BLOCKY. Cutting the section back to the
# payload took the part from 72.1 mm tall to 58.0 with GAP untouched, because
# the extra 14 mm was never the pack -- it was the wedge being enclosed out to
# the flank. Standoff is still 51 mm and that IS the pack; height is not.
GAP = 23.0           # air gap between arm and tray underside, at the crown
FOAM = 4.0           # compliant pad thickness on EVERY arm face -- see below
STRAP_Y = (34.0, 112.0)  # strap channel centres, from the USB (open) end

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
# The section is HANDED, like TILT: the arm falls away from the deep flank,
# while the shallow one meets the arm within ~13 mm. All of it is derived from
# arm_z() so TILT stays a real knob -- change it and the section follows.
#
# ★★ 2026-08-12 -- THE SECTION FOLLOWS THE CONTENTS, NOT THE WEDGE.
# It used to run the deep flank all the way down to where the tilt plane met
# it (Z -43.9) and close it with a keel. That put a 26 mm tall curtain and a
# corner around a volume with NOTHING in it: the pack stops at Z -15.6 and the
# arm cut has left the section entirely by X -30. The owner read it straight
# off the model -- "a corner and a bunch of material at the bottom where
# nothing sits", "cantilevered over the edge for no reason" -- and he is right;
# it was 30 cm3 of enclosed air in a 2 mm skin, which is the same wrong
# silhouette as a solid one. So now:
#   * the deep flank stops one wall below the payload (PAYLOAD_Z), and
#   * a single CHINE facet runs from there down to the arm, meeting it where
#     the arm's own surface has turned through DEEP_WRAP.
# The tilt wedge is a CONSEQUENCE of angling a flat tray on a round arm. It is
# not a volume that has to be enclosed.
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
# ★★ How far round the arm the shell stays with it on the deep side, measured
# from the arm's own crown. Past 45 deg the shell is hanging off the SIDE of
# the arm rather than sitting on top of it: it carries no payload out there,
# it bears no load out there, and every mm of it is the cantilever the owner
# objected to. So the shell leaves the arm at 45 deg and closes back up to the
# flank on one straight chine. The shallow flank needs no equivalent -- the arm
# is only ~21 mm below the belt on that side and the flank reaches it directly.
DEEP_WRAP = 40.0     # degrees from the arm crown, deep side
# ★★ ...AND THE SAME ON THE SHALLOW SIDE, since 2026-08-12. Until then the
# shallow flank simply ran into the arm cylinder wherever the two happened to
# cross -- 25.3 deg of wrap against the deep side's 40 -- so the shell was
# sliced off by the arm on one side and wrapped round it on the other. Owner:
# "a weird underbelly", "it's cut off flat beneath it". EQUAL WRAP is what
# makes the underside read as a CUFF: both edges of the arm opening leave the
# arm at the same angle from its crown, so the shell embraces the forearm
# symmetrically even though the tray on top of it is tilted 25 deg. It costs
# width and nothing else -- the height is unchanged, because the deep toe was
# already the deepest point on the part.
SHAL_WRAP = DEEP_WRAP
# ★ The cuff: below the flanks the outer surface is CONCENTRIC with the arm,
# CUFF_T thick, and its end face is RADIAL -- so the arm opening is bounded by
# a CUFF_T-thick hem on each side instead of the zero-thickness razor the flank
# used to leave where it happened to cross the cylinder.
# ⚠️ CUFF_T must stay under WALL_OUT + WALL_ARM = 4.0 or the shell cavity
# reappears inside the cuff as a sliver: the cavity is this section inset by
# WALL_OUT and then cut by the arm + WALL_ARM, and at 3.0 the inset lands at
# R 50 while the cut clears everything under R 51. The cuff comes out solid,
# with 1 mm of margin rather than a coincident face.
CUFF_T = 3.0

# ------------------------------------------------------------- ★★ LOW POLY
# ⚠️⚠️ WHAT LOW POLY ACTUALLY MEANS -- and it is not what this file assumed
# until 2026-08-12. It was read as "few large flat faces, no curves", which is
# a printability constraint, and the result was a chamfered box. Owner:
# "we didn't even hit low poly, I just stopped saying it." The references in
# ref/lowpoly-*.png settle it:
#
#   LOW POLY IS A SCULPTURAL STYLE -- a rounded form approximated by MANY
#   visible planar facets of varying size and angle, each catching the light
#   differently. Sharp facet creases, no chamfers, deliberately irregular.
#
# So the form has to get ROUNDER first and then be tessellated. That is also
# how it stops fighting the Pip-Boy reference rather than splitting the
# difference: ★ THE PIP-BOY GIVES THE BONES -- proportion, chunk, the sunken
# visor, the cuff on the forearm. LOW POLY GIVES THE SURFACE. A wrist device
# with Pip-Boy bones, rendered in facets.
#
# How it is built, and why this construction and not a mesh:
#   * ONE irregular section polygon, generated by rounding the corners of a
#     coarse outline into arcs and then chording those arcs -- so the facet
#     sizes and angles vary by construction instead of by noise;
#   * swept along the arm through STATION_N stations, each an affine copy of
#     that section (UNIFORM scale about a fixed centre, plus an offset);
#   * lofted ruled between consecutive stations.
# ★ Uniform-scale-plus-offset is the whole trick. For any edge (A,B) of the
# section, the quad (s0*A, s0*B, s1*B, s1*A) is PLANAR exactly when s1*(B-A)
# is parallel to s0*(B-A) -- i.e. when the two stations differ by a uniform
# scale and a translation. Any other per-station shape change makes the lateral
# faces ruled (bilinear) surfaces, which are not flat and are not low poly.
# So every face on this hull is a plane, it exports as a plane in the STEP, and
# nothing has to be tessellated by the exporter.
# ★★ AND IT IS WHY IT STILL PRINTS. A facet's normal is (nx, ny, nz); standing
# on the jack end maps model +Y to print -Z, so ny IS the downward component.
# A prismatic hull has ny = 0 everywhere. Here ny ~ dR/dY, so the overhang
# angle is set by (scale change x radius) / (station spacing). With SEC_JIT
# at 1.2 % over ~14 mm of station the worst facet is ~4 deg off vertical --
# an order of magnitude inside the 45 deg limit, and verify_bracer.py measures
# it rather than trusting this note.
SEC_JIT = 0.42       # how much the arc chording is skewed, 0 = even chords
STATION_N = 6        # sections along the arm
# ⚠️ These two are bounded from BOTH sides and neither bound is taste.
#   * too small and the body is a prism with a texture -- the first attempt at
#     this ran 1.2 % and the render came back looking smooth;
#   * too large and two things break. The facet's downward component is
#     (scale change x radius + offset) / station spacing, which has to stay
#     inside 45 deg -- at 2.2 % over ~13 mm the worst facet is ~21 deg, and the
#     harness measures it. And the section's top must stay INSIDE the frozen
#     tray wall at every station or the hull starts standing outboard of the
#     button bores at Z 4.6 and buries the plungers. P_TOP_* is placed so the
#     surface crosses X = OUT_W/2 at Z ~ 3.1 even at the widest station.
STATION_AMP = 0.030  # +/- uniform scale, cumulative (random walk)
STATION_OFF = 1.5    # +/- mm of section offset, cumulative
SEED = 20260812      # the tessellation is RANDOM but REPEATABLE. Do not drop
                     # this: an unseeded shell would differ on every run and no
                     # probe in the harness could ever be trusted again.
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
WALL_END = 3.0       # closing wall at the jack end
CAV_Y1 = 3.0         # cavity stops this far short of the jack end

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
#     end and Y ~10.9 at the USB end. That ramp is what stops the guard reading
#     as an extrusion, and it is the answer to the blocky ends as well.
#
# ★ What he asked for on top of his file: the inner faces CONCAVE -- scooped
# back into the thick surround so the wall thins as it rises and its crest
# meets his outer bevel. Cut with cylinders, so it is one curved face per side
# in the STEP rather than a faceted approximation he has to clean up.
#
# What I did NOT take from his file, and why:
#   ⚠️ his jack brow starts at Y 135.3, which puts 15 mm of material over the
#      front camera and the earpiece. Those are frozen apertures; punching them
#      through a 15 mm brow would tube the camera. Ours starts at Y 141, clear
#      of the camera's outer edge at 140.5, and the brow is correspondingly
#      shorter. That is the one place his form and the housing disagree.
#   ⚠️ his USB-end brow's inner face rakes at 49 deg off vertical. Printed
#      standing on the jack end that face points down and needs support; ours
#      is held to 45 deg by construction (see SCOOP_R_BROW).
GUARD_H = 15.0       # crest height above the tray face -- his 28.4 - 13.4
# ⚠️ 40.0, not 41.5. At 41.5 the guard stood 1.5 mm outboard of the hull's own
# belt line and 4 mm outboard of the tray wall it sits on -- a 15 mm tall wall
# cantilevered past the body, which is the same fault as the keel corner and
# it is the widest thing on the part. Flush with the belt, the guard's outer
# face and the hull flank are ONE plane from the crest to the chine.
GUARD_HW = HULL_HW   # outer half width -- the hull's belt line, not past it
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
BROW_Y0 = 11.0       # USB-end scoop's base, on the well floor
BROW_Y1 = 141.0      # hand scoop's base -- clear of the camera at 140.5
USB_BROW_OUT = 0.59  # USB-end brow's outer face rakes back at his slope
# ★★ ONE RULE FOR BOTH ENDS, and it was only being applied at one of them.
# The crest starts dropping BROW_RAMP before it reaches a brow's base, so each
# brow is already part way down its ramp by the time its wall begins. His file
# does that at the jack end (ramp 134, brow base 141) and NOT at the USB end
# (ramp 11, brow base 11) -- so the wrist-end brow kept the full crest and came
# out 8.4 mm above the tray face and 11 mm deep, against 5.0 mm and 6 mm at the
# elbow end. Owner, 2026-08-12: "the side guards aren't even the same height,
# the top side is better, the bottom is massive." The top of the SCREEN is the
# elbow end, so the massive one is the wrist brow. Measured, then equalised
# here rather than by eye: both brows now peak at the same 5.0 mm.
# ⚠️ Derive both from it. Hard-coding 11 and 134 is how they drifted apart.
BROW_RAMP = 7.0      # crest starts dropping this far INSIDE each brow's base
RAMP_Y0 = BROW_Y0 + BROW_RAMP    # ...toward the USB (wrist) end
RAMP_Y1 = BROW_Y1 - BROW_RAMP    # ...and toward the jack (elbow) end = his 134
# 1.1, not his 1.0. The ramp faces point downward when the part stands on its
# jack end, and at 1.0 they land at exactly 45 deg -- on the threshold, not
# under it. 1.1 puts them at 48 deg and is indistinguishable by eye.
RAMP_SLOPE = 1.1     # run per unit rise; >1 is shallower than 45 deg

# ★ Internal cable: a flat USB-C lead from the phone's port to the pack. The
# plate is deep enough for a right-angle head to sit in a pocket, turn, and run
# out sideways into the cavity past the card rails.
CABLE_W, CABLE_H = 14.0, 4.5    # pocket in the plate, for the head + turn
# ⚠️⚠️ THE OUTBOARD END OF THE CABLE RUN IS A HARD LIMIT, not a width about a
# centre, and getting that wrong is what put a square hole in the end cap.
# It was written `CABLE_X + CABLE_W/2` = X 42 on a cap whose own half width is
# 37.55, so the channel ran straight out through the shallow flank and left a
# 5.5 x 10.7 mm square window in the nose -- open sideways, open at the back.
# Owner, 2026-08-12: "the cap has a square hole in it for no reason there."
# There was no reason: it was a boolean over-run, not a feature. The channel
# now stops where the floor slot it feeds stops, and the flank stays closed.
# CABLE_X1 -- the run's outboard limit -- is derived below, off the floor slot.
CABLE_SLOT_W = 4.4         # ⚠️ the drop slot is narrow because the pack and
                           # the cards already use the full 54 mm width. The
                           # flat lead runs through it ON EDGE, not flat.
PLUG_D = 6.0               # depth the right-angle head needs off the phone

CAP_D = 10.0         # end-cap slip depth
CAP_W = 2.0          # cap side wall
# ⚠️ 6 mm, not 2.4. The full-face trough is lofted into this plate, so a thin
# plate makes the trough meet the outer face at a feather edge at the corners.
# The answer is material, not a slicer setting: a thicker plate gives the scoop
# real depth, a proper rim, and a gentler taper that prints cleanly. It also
# suits the chunky retro-futurist read.
CAP_T = 12.0         # cap end plate -- now houses the plug and the cable turn
CAP_CLR = 0.30       # slip fit over the tenon
# Strap runs in a channel on the UNDERSIDE of each rib, not on side flanges.
# Flanges made the device 91 mm wide for no structural reason and were also
# what the end cap collided with. This keeps the whole thing tray-width.
STRAP_W = 26.0       # channel width along the arm, for 25 mm webbing
STRAP_D = 2.2        # channel depth into the rib's arm face
# ⚠️ 14, not 20. The bar is trimmed by the arm cut, so its tip is a wedge
# whose angle is the local slope of the arm face -- and at 25 deg of tilt a
# bar 39 mm from the crown came out at 31 deg, under the crest limit. Closer
# in, the face is flatter and the tip is blunt.
# ⚠️ Measured from the ARM'S CROWN, not from the tray's centre line. The strap
# groove is coaxial with the arm and the crown sits at X = ARM_CX (19 mm off
# centre at 25 deg of tilt), so bars placed symmetrically about X=0 are 5 mm
# and 33 mm from the crown -- one blunt, one out on the steep part of the face
# and, once the section was cut back to the payload, one of them hanging past
# the chine entirely. Symmetric about the crown, both tips are blunt.
BAR_X = 14.0         # retaining bars, either side of the arm's crown
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
OUT_L = POCK_L + WALL              # closed at the jack end, open at the USB end
OUT_H = FLOOR + POCK_D + LIP_H

# The floor slot the internal lead drops through, and therefore the outboard
# limit of the run across the cap's inner face. ⚠️ It runs 0.5 mm INTO the
# pocket wall on purpose -- stopping short leaves a 0.75 mm rib of floor
# between slot and wall, which is a rib you could snap with a fingernail.
CABLE_X1 = POCK_W / 2 + 0.5

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


# SD is the sign of the DEEP side in model X. Needed here, before the section.
SD = 1.0 if TILT >= 0 else -1.0

R_CUFF = ARM_CUT_R + CUFF_T          # the cuff's outer surface
R_INNER = ARM_CUT_R - 6.0            # the closing chord, safely inside the arm


def cuff_pt(theta, r=None):
    """Point on a circle concentric with the arm cut, `theta` degrees round
    from the ARM'S OWN CROWN. Positive theta runs toward the DEEP flank, so the
    sign follows TILT the same way SD does and the section stays handed."""
    r = R_CUFF if r is None else r
    t = math.radians(theta)
    return (ARM_CX + SD * r * math.sin(t), ARM_CZ + r * math.cos(t))


# ★ Deep flank: it stops one wall below the payload. Nothing is carried below
# PAYLOAD_Z, so nothing is enclosed below it either.
HULL_Z_DEEP = PAYLOAD_Z - WALL_OUT
# The shallow flank runs down until it meets the cuff's own circle; from there
# the cuff carries it round to SHAL_WRAP. Solved, not guessed, so TILT stays a
# real knob.
SHAL_FOOT_TH = math.degrees(math.asin((-SD * HULL_HW - ARM_CX) / (SD * R_CUFF)))
HULL_Z_SHAL = cuff_pt(SHAL_FOOT_TH)[1]
TOE_X, TOE_Z = cuff_pt(DEEP_WRAP)    # outer corner of the deep hem
# ★ The deepest point that SURVIVES is where the hem meets the arm, not the
# closing chord (which is inside the cylinder and gets carved away).
SAG = -(ARM_CZ + ARM_CUT_R * math.cos(math.radians(max(DEEP_WRAP, SHAL_WRAP))))


# --------------------------------------- SVG face coords -> model coords
# The phone sits with its TOP edge (headphone jack) at the JACK end, Y=OUT_L.
PHONE_TOP_Y = POCK_L - CLR         # Y of the phone's top edge in the tray
def fx(x):  return x - PH_W / 2    # SVG x -> model X (centred)
def fy(y):  return PHONE_TOP_Y - y  # SVG y -> model Y (USB end = 0)

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
# USB-end brow's inner face points down when the part stands on its jack end, so
# it must stay inside 45 deg; for this family of arcs the steepest point is at
# the base and the condition is exactly R >= rise * sqrt(2).
SCOOP_R_BROW = GUARD_H * math.sqrt(2) * 1.13
SCOOP_CY0 = BROW_Y0 + math.sqrt(SCOOP_R_BROW ** 2 - GUARD_H ** 2)   # USB-end axis
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
        one end and the jack-end face at the other, and it would not take a cut
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


def arc_chords(p0, p1, bulge, n, rng, include_first=True):
    """★ THE TESSELLATOR. A circular arc from p0 to p1, bulging `bulge` mm
    proud of the chord, delivered as `n` STRAIGHT CHORDS of irregular length.

    This is the whole low-poly construction and it is deliberately the other way
    round from the last attempt. Rounding the corners of a slab gave a slab with
    rounded corners; what the references (ref/lowpoly-*.png) show is a ROUNDED
    FORM chorded into flats. So the form is stated as arcs -- the flanks bulge,
    the chine bows, the cuff follows the arm -- and every arc is then replaced by
    a handful of planes. Facet angle comes out as (arc angle / n), so it is a
    number you set rather than a hope: ~13 deg per crease on the flanks here.

    ⚠️ The chord lengths are JITTERED. Even chords on a circular arc give a
    regular fan and a regular fan reads as a badly-rendered fillet, not as a
    sculpt -- every reference is irregular everywhere. `rng` is seeded (SEED)
    so the irregularity is fixed geometry, not noise that moves between runs.
    """
    x0, z0 = p0
    x1, z1 = p1
    dx, dz = x1 - x0, z1 - z0
    L = math.hypot(dx, dz)
    pts = []
    if abs(bulge) < 1e-6 or n < 2:
        ks = [0.0] + sorted(rng.uniform(0, 1) for _ in range(n - 1)) + [1.0]
        for k in ks[0 if include_first else 1:]:
            pts.append((x0 + dx * k, z0 + dz * k))
        return pts
    # outward normal of the chord; `bulge` is signed along it
    nx, nz = -dz / L, dx / L
    R = (L * L / 4.0 + bulge * bulge) / (2.0 * bulge)
    cx = (x0 + x1) / 2.0 - nx * (R - bulge)
    cz = (z0 + z1) / 2.0 - nz * (R - bulge)
    a0 = math.atan2(z0 - cz, x0 - cx)
    a1 = math.atan2(z1 - cz, x1 - cx)
    while a1 - a0 > math.pi:
        a1 -= 2 * math.pi
    while a0 - a1 > math.pi:
        a1 += 2 * math.pi
    ks = [0.0] + sorted(
        min(0.97, max(0.03, (j + 1) / n + rng.uniform(-SEC_JIT, SEC_JIT) / n))
        for j in range(n - 1)) + [1.0]
    rad = abs(R)
    for k in ks[0 if include_first else 1:]:
        th = a0 + (a1 - a0) * k
        pts.append((cx + rad * math.cos(th), cz + rad * math.sin(th)))
    return pts


def prism(pts, y0, y1):
    """Extrude an (X, Z) polygon from y0 to y1.

    ⚠️ SELF-CORRECTING, and it has to be. Polygon takes its face normal from
    the winding and extrude() follows that normal, so a profile listed the
    other way round silently goes to -Y. That has now cost two separate bugs:
    a 294 mm long part, and a lip bevel that cut the USB-end brow off. Rather
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


# ------------------------------------------------- ★★ THE FACET CARVER
# ⚠️⚠️ 2026-08-12, ROUND TWO. The first low-poly pass tessellated the FLANKS
# and the cuff and stopped there, because the flanks were what the owner had
# complained about. Everything else -- the guard's outer wall, the deck round
# the screen, the tray's own side walls, both end faces -- stayed exactly as
# built: single planes, the biggest of them 2883 mm2. Owner, looking at it:
# "still looking at a flat top wall". He is right, and the census in
# verify_bracer.py said the part was fine because it only ever looked BELOW THE
# BELT. A check scoped to the surface you already fixed is worse than no check.
#
# ★ THE RULE, and it is the whole of it: in ref/lowpoly-*.png EVERY surface of
# the object is faceted. Not the sides. Not the sides and one end. All of it.
# A slab with textured flanks is a decorated box, which is what this was.
#
# HOW. The flanks got their facets from the SECTION -- arcs chorded into planes
# and lofted through stations. That construction cannot reach a face whose
# normal is not perpendicular to the arm axis, which is precisely why the deck
# and the two ends escaped it. So those surfaces are carved instead:
#
#   a flat panel is covered with a jittered point cloud, each point pushed IN
#   by its own depth, Delaunay-triangulated, and the volume in front of the
#   resulting triangle mesh is subtracted from the solid.
#
# Three properties earn it its place:
#   * every facet is a triangle of a plane, so it exports as a plane in the
#     STEP and there is nothing for the mesher to approximate;
#   * it only ever REMOVES material. It cannot grow the envelope, it cannot
#     bury a plunger, it cannot eat into the 4 mm FOAM relief on an arm face,
#     and it cannot invent the dead structure the owner objected to last round;
#   * depth is a FUNCTION OF POSITION, so the frozen housing is respected by
#     construction rather than by hoping. Each panel below carries a budget
#     function that knows what is behind that patch of surface -- 0.9 mm over
#     the phone pocket's 2.4 mm wall, 0.0 mm over a button counterbore, 8 mm
#     over the solid skirt at the elbow -- and the minimum-wall check in the
#     harness is the independent audit of every one of those numbers.
# ⚠️ Its own RNG, seeded off SEED but separate, so adding panels cannot shift
# the hull's station walk and silently move geometry a probe was placed against.
_prng = __import__("random").Random(SEED + 1)


def facet_shave(origin, u, v, n, a0, a1, b0, b1, budget, base=None,
                pitch=11.0, pitch_b=None, reach=90.0, deep=0.42, jit=0.36,
                drop=0.12):
    """The volume in FRONT of a faceted surface laid over a flat panel.

    `origin`, `u`, `v`, `n` define the panel frame: a point on the untouched
    plane, two in-plane unit axes, and the OUTWARD normal. `a`/`b` bounds are
    in u/v. Depth at a point is `base(a, b) + budget(a, b) * random`, measured
    along -n: `base` is surface that is ALREADY set back there and must be
    followed exactly (the guard's outer bevel, the cap's sunken panel), while
    `budget` is what may additionally be carved out of solid material.

    Points sit on a jittered grid rather than at random: a Poisson-ish spray
    makes slivers that OCCT then refuses, and a grid this coarse with this much
    jitter is already irregular enough that no fan of equal facets appears.
    `drop` deletes a fraction of the interior points, which is what gives the
    mix of large and small facets the references have -- an even mesh reads as
    a badly-tessellated fillet, the exact failure the flanks had at 5 chords.

    ⚠️⚠️ SATISFYING THE BUDGET AT THE VERTICES IS NOT ENOUGH, and the first
    build of this proved it by cutting a hole through the elbow end's wall over
    the phone pocket. The depth across a facet is the LINEAR INTERPOLATION of
    its three corners, so a triangle with two corners out in the 8 mm skirt and
    one on the 0.9 mm pocket band carries almost the skirt's depth right across
    the band. The budget map has cliffs in it because the housing behind it
    does, and no grid pitch resolves a cliff.
    ★ So the depth field is RELAXED against the budget: sample each triangle at
    its centroid, its edge midpoints and six interior points, and wherever the
    interpolated depth exceeds what is allowed there, scale that triangle's
    three corners down. Depths only ever decrease, so it converges, and it
    costs depth only next to a cliff instead of everywhere (which is what a
    neighbourhood-minimum would have done -- it blanked the 3 mm deck strip
    outboard of the screen entirely).
    """
    # ⚠️⚠️ FOUR DIVISIONS MINIMUM, and this is not cosmetic. A panel narrower
    # than ~2 pitches gets two rows of points, BOTH on its rim -- and every rim
    # point is faded to zero depth, so the panel carves precisely nothing. That
    # silently happened to the two tray side walls (12.1 mm tall, pitch 10) and
    # the guard's outer wall (14.9 mm, pitch 11): the build ran clean, the
    # renders looked shaved, and 1840 mm2 of flat wall was still sitting there.
    # The census over the whole skin is what caught it.
    # ⚠️ `pitch_b` exists for panels whose BASE has structure across b -- the
    # cap's sunken face. There the rim rows are pinned to zero depth, and if
    # the next row inward is a whole pitch away the relaxation drags it back to
    # the rim's budget and the recess never gets carved: 617 mm2 of flat panel
    # floor survived exactly that way, which is how the census caught it.
    na = max(4, int(round((a1 - a0) / pitch)) + 1)
    nb = max(4, int(round((b1 - b0) / (pitch if pitch_b is None else pitch_b))) + 1)
    P, D = [], []
    for i in range(na):
        for j in range(nb):
            edge = i in (0, na - 1) or j in (0, nb - 1)
            if not edge and _prng.random() < drop:
                continue
            a = a0 + (a1 - a0) * i / (na - 1)
            b = b0 + (b1 - b0) * j / (nb - 1)
            if 0 < i < na - 1:
                a += _prng.uniform(-jit, jit) * (a1 - a0) / (na - 1)
            if 0 < j < nb - 1:
                b += _prng.uniform(-jit, jit) * (b1 - b0) / (nb - 1)
            P.append((a, b))
            D.append((0.0 if base is None else base(a, b))
                     + budget(a, b) * _prng.uniform(deep, 1.0))
    tri = Delaunay(np.array(P))

    # ---- relax the depth field until every sampled point is inside budget ---
    _W = [(1 / 3, 1 / 3, 1 / 3), (.5, .5, 0), (0, .5, .5), (.5, 0, .5),
          (.6, .2, .2), (.2, .6, .2), (.2, .2, .6),
          (.8, .1, .1), (.1, .8, .1), (.1, .1, .8)]
    for _pass in range(10):
        moved = False
        for s in tri.simplices:
            k = (int(s[0]), int(s[1]), int(s[2]))
            for w in _W:
                qa = sum(w[t] * P[k[t]][0] for t in range(3))
                qb = sum(w[t] * P[k[t]][1] for t in range(3))
                dq = sum(w[t] * D[k[t]] for t in range(3))
                cap_ = (0.0 if base is None else base(qa, qb)) + budget(qa, qb)
                if dq > cap_ + 1e-9 and dq > 1e-9:
                    f = cap_ / dq
                    for t in range(3):
                        D[k[t]] *= f
                    moved = True
        if not moved:
            break
    W = [origin + u * P[k][0] + v * P[k][1] - n * D[k] for k in range(len(P))]
    W2 = [w + n * reach for w in W]
    faces, seen = [], {}
    for s in tri.simplices:
        i0, i1, i2 = int(s[0]), int(s[1]), int(s[2])
        faces.append(Face(Wire.make_polygon([W[i0], W[i1], W[i2]], close=True)))
        faces.append(Face(Wire.make_polygon([W2[i2], W2[i1], W2[i0]], close=True)))
        for e in ((i0, i1), (i1, i2), (i2, i0)):
            k = (min(e), max(e))
            seen[k] = seen.get(k, 0) + 1
    # the panel's rim: every edge used by one triangle only
    for (i0, i1), cnt in seen.items():
        if cnt == 1:
            faces.append(Face(Wire.make_polygon(
                [W[i0], W[i1], W2[i1], W2[i0]], close=True)))
    return Solid(Shell(faces))


# ------------------------------------------------------------------ build
# Tray body: Y = 0 at the USB (open) end -- the WRIST -- and Y = OUT_L at the
# jack end -- the ELBOW. See the orientation block at the top of the file.
part = bbox(-OUT_W / 2, OUT_W / 2, 0, OUT_L, 0, OUT_H)


# ------------------------------------------------------------------- hull
# The faceted outer body. SD is the deep side -- the flank the arm falls away
# from, which is +X for a positive TILT and swaps with it.
# ⚠️ The edge from the shallow flank's foot to the deep TOE is a CHORD lying
# inside the arm cylinder, so none of it survives: the arm cut carves the whole
# underside between the two feet and the saddle IS the outer surface there.
# That is deliberate -- the shell has no keel of its own over the arm, because
# a keel there would be a second skin around a surface that is already the
# outside of the part. It only reappears as the chine, outboard of the toe,
# where the cylinder has left the section.
# ★★ THE SECTION, STATED AS ARCS AND THEN CHORDED. Read the arc_chords note
# first. The form is now genuinely ROUND -- the flanks bulge FLANK_BULGE proud
# of the straight line from the shoulder to the cuff, the chine bows, the cuff
# follows the forearm -- and each of those arcs is delivered as a handful of
# planes. That is what makes the sides stop reading as "hard cuts": there is no
# 20 mm flat plane on the flank any more, there are five planes at 13 deg to
# each other, and each one takes the light differently.
#
# ⚠️ THE TOP TWO POINTS ARE BURIED INSIDE THE FROZEN TRAY. The hull is unioned
# with the tray box, so anything the section does inboard of OUT_W/2 above Z=0
# is invisible -- and, far more to the point, cannot reach the pocket, the
# button bores or the plungers. That is how the tessellation is kept off the
# frozen housing: not clipped away afterwards, it never gets there. The station
# scaling is sized so this stays true at every station (see STATION_AMP).
# ⚠️ The bulge is bounded by the DEAD-STRUCTURE check, not by taste: the
# payload is 30.6 mm half width and the harness allows 13 mm of standoff, so a
# flank that bows past ~43.5 is material standing off everything it could hold.
# 4.0 puts the widest point at 42.5. That is the ceiling on this knob.
FLANK_BULGE = 4.0    # how far the flank bows out past shoulder->cuff
CHINE_BULGE = 3.5    # ...and the chine past hem->flank foot
# ★ THREE chords, not five. Facet angle is (arc angle / chords), and at five it
# came out at 13 deg -- adjacent facets differed by so little tone that the
# render came back looking smooth. At three it is ~22 deg and the creases read.
FLANK_CHORDS = 3
CHINE_CHORDS = 3
_rng = __import__("random").Random(SEED)

P_TOP_S = (-SD * (OUT_W / 2 - 9.0), HULL_SHOULDER + 3.0)   # buried in the tray
P_SHO_S = (-SD * (OUT_W / 2 - 0.5), HULL_SHOULDER - 0.5)   # leaves the tray wall
P_CUF_S = cuff_pt(SHAL_FOOT_TH)                            # cuff picks it up
P_HEM_SO = cuff_pt(-SHAL_WRAP)                             # shallow hem, outer
P_HEM_SI = cuff_pt(-SHAL_WRAP, R_INNER)                    # (inside the arm)
P_HEM_DI = cuff_pt(DEEP_WRAP, R_INNER)
P_HEM_DO = (TOE_X, TOE_Z)                                  # deep hem, outer
P_CHI_D = (SD * HULL_HW, HULL_Z_DEEP)                      # deep flank's foot
P_SHO_D = (SD * (OUT_W / 2 - 0.5), HULL_SHOULDER - 0.5)
P_TOP_D = (SD * (OUT_W / 2 - 9.0), HULL_SHOULDER + 3.0)

HULL_SEC = [P_TOP_S]
HULL_SEC += arc_chords(P_TOP_S, P_SHO_S, 0.0, 1, _rng, False)
HULL_SEC += arc_chords(P_SHO_S, P_CUF_S, FLANK_BULGE, FLANK_CHORDS, _rng, False)
# ★★ THE BELLY IS NOT CONCENTRIC (2026-08-12). Owner: "the whole back of this
# thing is a round belly that could be streamlined... those kinds of cuts are
# exactly the things needed to not make this read 'box holding a phone on some
# guy's arm'."
#
# It used to be `cuff_pt()` twice -- points on a circle CONCENTRIC with the arm
# cut, so the outside was just the inside plus CUFF_T. It was a tube because a
# forearm is a tube, and nothing about it was designed. The inner surface still
# has to be that circle (it is the arm, plus FOAM). The OUTER surface does not.
#
# So: one straight plane across the shallow belly. Measured, the straight chord
# between the same two endpoints dips only 0.52 mm inside the wall, so the plane
# is pushed radially out by that deficit plus BELLY_MARGIN and the cuff stays at
# least CUFF_T everywhere. A flat costs half a millimetre and buys a hard crease
# at each end instead of a surface that dissolves into the flanks.
BELLY_MARGIN = 0.2
_b0, _b1 = cuff_pt(SHAL_FOOT_TH), cuff_pt(-SHAL_WRAP)
_bm = ((_b0[0] + _b1[0]) / 2.0, (_b0[1] + _b1[1]) / 2.0)
_bd = math.hypot(_bm[0] - ARM_CX, _bm[1] - ARM_CZ)
_push = max(0.0, (ARM_CUT_R + CUFF_T) - _bd) + BELLY_MARGIN
_bu = ((_bm[0] - ARM_CX) / _bd, (_bm[1] - ARM_CZ) / _bd)      # radial unit
HULL_SEC.append((_bm[0] + _bu[0] * _push, _bm[1] + _bu[1] * _push))
HULL_SEC.append(_b1)
HULL_SEC += [P_HEM_SI, P_HEM_DI, P_HEM_DO]   # hem, closing chord, hem
HULL_SEC += arc_chords(P_HEM_DO, P_CHI_D, CHINE_BULGE, CHINE_CHORDS, _rng, False)
HULL_SEC += arc_chords(P_CHI_D, P_SHO_D, FLANK_BULGE, FLANK_CHORDS, _rng, False)
HULL_SEC += [P_TOP_D]

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

# ★ NO SECTION BEVEL any more, and that is the point. Bevelling a facet crease
# is what turned this into a chamfered box; on a low-poly sculpt the creases
# between facets ARE the surface, and the references have no chamfers anywhere.
# CHAMFER survives only for the visor rim and the cap's face, where it is
# relief on a frozen feature rather than styling.

# The arm, and the concentric cylinders derived from it. Defined here because
# the hull's tenon needs one of them.
_pivot = -(GAP + FOAM)          # crown contact, on the tray centre line
_tilt = Pos(0, 0, _pivot) * Rot(0, TILT, 0) * Pos(0, 0, -_pivot)


def arm_cyl(r, length=None, yc=None):
    """A cylinder coaxial with the forearm, radius r."""
    length = OUT_L + 60 if length is None else length
    yc = OUT_L / 2 if yc is None else yc
    return _tilt * (Pos(0, yc, ARM_AXIS_Z) * Rot(90, 0, 0) * Cylinder(r, length))


arm = arm_cyl(ARM_CUT_R)

# ------------------------------------------------- stations along the arm
# ★ The second direction of the tessellation. Each station is a UNIFORM scale
# of HULL_SEC about SEC_C plus an offset -- see the LOW POLY note for why it
# has to be uniform (any other per-station change makes the lateral faces
# ruled surfaces instead of planes).
# ⚠️ Station 0 sits at Y = CAP_D at scale 1.0 with no offset, because that is
# where the cap's tenon ends: the collar is machined to the BASE section, so
# the body may only start varying once the cap is behind it.
SEC_C = (0.0, -6.0)
STATION_Y = [CAP_D]
_span = OUT_L - CAP_D
for _i in range(1, STATION_N):
    _f = _i / (STATION_N - 1)
    STATION_Y.append(CAP_D + _span * _f
                     + (0.0 if _i in (0, STATION_N - 1)
                        else _rng.uniform(-0.28, 0.28) * _span / (STATION_N - 1)))
# ⚠️ A RANDOM WALK, not white noise, and that is not a detail. Independent
# per-station values make consecutive stations alternate high-low-high, and a
# long body full of alternating stations reads as CORRUGATION -- the first
# render of this looked like the flank had sagged. A walk gives each stretch a
# direction, so the body comes out as a handful of large planes leaning
# different ways, which is what the printed hand in ref/ actually looks like.
STATION_S = [(1.0, 0.0, 0.0)]
_s, _dx, _dz = 1.0, 0.0, 0.0
for _ in range(STATION_N - 1):
    _s = min(1.0 + STATION_AMP, max(1.0 - STATION_AMP,
                                    _s + _rng.uniform(-1.0, 1.0) * STATION_AMP))
    _dx = min(STATION_OFF, max(-STATION_OFF,
                               _dx + _rng.uniform(-1.0, 1.0) * STATION_OFF))
    _dz = min(STATION_OFF, max(-STATION_OFF,
                               _dz + _rng.uniform(-1.0, 1.0) * STATION_OFF * 0.6))
    STATION_S.append((_s, _dx, _dz))


def sec_at(base, i):
    s, dx, dz = STATION_S[i]
    return [((x - SEC_C[0]) * s + SEC_C[0] + dx,
             (z - SEC_C[1]) * s + SEC_C[1] + dz) for x, z in base]


def sec_face(pts, y):
    return Pos(0, y, 0) * (Plane.XZ * Polygon(*pts, align=None))


def tessellated(base):
    """Ruled loft of `base` through every station -- the faceted body."""
    return loft([sec_face(sec_at(base, i), STATION_Y[i])
                 for i in range(STATION_N)], ruled=True)


hull = tessellated(HULL_SEC)
# The nose stays PRISMATIC over the cap's length: the collar is a machined fit
# and a varying section under it would either bind or rattle.
hull += prism(HULL_SEC, 0, CAP_D) & _above
# ⚠️⚠️ NO TENON INSIDE THE CUFF. The cuff is CUFF_T = 3.0 thick and its inner
# face is the arm cylinder, which cannot move -- so stepping it in by TEN_D
# leaves 0.7 mm, well under MIN_WALL, and the wall check would (correctly)
# fail. The cuff therefore runs THROUGH the joint at full section and the cap's
# collar stops on its shoulder. That also reads better than the alternative:
# the cuff is one continuous band from nose to tail and the cap is a collar
# sitting on it, which is exactly how the reference object is assembled.
_cuff_zone = arm_cyl(R_CUFF)
hull += prism(HULL_SEC, 0, CAP_D) & _below & _cuff_zone
hull += (prism(inset(HULL_SEC, TEN_D), 0, CAP_D) & _below) - _cuff_zone

part += hull

# Carve the forearm (plus the foam allowance) out of the hull.
part -= arm

# Strap channel: a second, larger cylinder over just a band of the arm face
# carves a transverse groove. The webbing lies in there, between hull and arm,
# and wraps the forearm -- no flanges, no threading. On the deep side the arm
# has already fallen below the keel by X ~= 25, so the strap walks out into
# open air under the hull rather than needing a slot cut for it.
# ⚠️ CLIPPED on the shallow side. The groove is cut to 51.2 and the shallow
# flank runs nearly TANGENT to that cylinder as it comes down to the cuff, so
# out past ~26 deg the groove was skimming the flank and leaving 0.8 mm of
# skin -- the wall check found it twice, at two different stations. The groove
# now stops at 26 deg and the slot below takes over from 21, so the two overlap
# and neither can leave a feather between them.
def _wedge(t0, t1, r, y0, y1, n=6):
    return prism([(ARM_CX, ARM_CZ)]
                 + [cuff_pt(t0 + (t1 - t0) * k / n, r) for k in range(n + 1)],
                 y0, y1)


for y in STRAP_Y:
    _y0, _y1 = y - STRAP_W / 2, y + STRAP_W / 2
    part -= (arm_cyl(ARM_CUT_R + STRAP_D, STRAP_W, y)
             - _wedge(-26.0, -75.0, 90.0, _y0 - 1, _y1 + 1))
# ⚠️⚠️ ...AND THROUGH THE CUFF, not into it. The groove is cut to
# ARM_CUT_R + STRAP_D = 51.2 and the cuff's outer surface is at 52, so out where
# the shell has become the cuff the groove leaves a 0.8 mm flap -- under
# MIN_WALL, and a flap you could tear off with a fingernail. The webbing has to
# leave the shell somewhere in any case, so it leaves through a SLOT: over each
# strap band the cuff is removed outright between the flank's foot and past the
# hem. That is also what makes the cuff read as three plates with two strap
# slots rather than one extruded band.
_CUFF_SLOT_R = R_CUFF + 0.5
for y in STRAP_Y:
    for _t0, _t1 in ((-21.0, -SHAL_WRAP - 4.0), (DEEP_WRAP - 7.0, DEEP_WRAP + 4.0)):
        part -= _wedge(_t0, _t1, _CUFF_SLOT_R, y - STRAP_W / 2, y + STRAP_W / 2)

# Retaining bars across the channel so the strap cannot fall out when it is
# off your arm. Trimmed back to the arm surface by re-cutting the arm after.
# ⚠️ AND CLIPPED TO THE HULL. A raw box only ever got trimmed from below by the
# arm, which was invisible while the body ran to Z -44 -- the box was buried.
# With the section cut back to the payload the deep bar's tail stuck 1.6 mm out
# through the chine: a spur of material hanging in fresh air off the underside,
# exactly the fault being fixed. `& hull` is a structural guarantee, the same
# trick as the final rounded-prism intersection in the print tenets.
for y in STRAP_Y:
    for sx in (-1, 1):
        _bx = ARM_CX + sx * BAR_X
        part += hull & bbox(_bx - BAR_W / 2, _bx + BAR_W / 2,
                            y - STRAP_W / 2, y + STRAP_W / 2,
                            -SAG - 1, 0)
part -= arm

# ------------------------------------------------ ★★ THE FACETED PANELS
# One entry per flat surface the loft cannot reach. Read facet_shave() first.
# The budget functions are where the frozen housing lives; each number below
# says what is behind that patch of skin and is audited by the minimum-wall
# check, never by eye.
_UX, _UY, _UZ = Vector(1, 0, 0), Vector(0, 1, 0), Vector(0, 0, 1)

# The two button bays, in Y. Nothing may be taken off the shell there: the wall
# between the counterbore at X 36.4 and the outer face at 37.55 is 1.20 mm and
# that is the thinnest thing the FROZEN housing deliberately has.
_BTN_Y = [(fy(_b1) - (BTN_CB_EXT + 2.4) / 2, fy(_b0) + (BTN_CB_EXT + 2.4) / 2)
          for (_b0, _b1) in (PWR_SVG, VOL_SVG)]


def _in_btn(y):
    return any(y0 < y < y1 for y0, y1 in _BTN_Y)


def _fade(*ts):
    """⚠️ EVERY PANEL MUST DIE AT ITS OWN RIM. A shave solid is a prism, so it
    ends in a flat rim face; if that rim lands inside material it leaves a
    WAFER -- a step of the original surface a few tenths thick, with the
    facet cut just past it. The first build left exactly that at Z 13.1 where
    the side-wall panel stopped under the deck panel, and the wall check read
    0.03 mm. Multiplying a budget by _fade(...) brings the depth to zero at
    the rim, so the panel's surface rejoins the surface it started from and
    the rim cuts nothing. Each argument is (distance past the rim / margin)."""
    return max(0.0, min(1.0, min(ts)))


def _bud_end(x, z):
    """ELBOW END. Behind this face: 2.4 mm of frozen pocket wall in the middle
    band, the tray floor and lip outside it, and below Z=0 the shell's closing
    wall -- which is as thick as we care to make it, because the cavity is cut
    back to follow these facets (see the shell section)."""
    # ⚠️ The pocket band runs from BELOW the floor to ABOVE the ceiling. Taking
    # it from FLOOR+0.6 left the wall behind the pocket's own floor corner on
    # the 2.6 mm budget and the wall check read 1.01 mm at Z 2.3.
    if abs(x) < POCK_W / 2 + 0.8 and FLOOR - 0.4 < z < FLOOR + POCK_D + 0.4:
        return 0.9
    if z > OUT_H + 0.8:
        # ⚠️ The guard's tail. Deeper than this and the elbow brow loses the
        # 5.0 mm crest the owner had the two brows equalised to -- that is a
        # decision on record, not spare material.
        return 1.6
    if -0.8 < z:
        return 2.6                      # tray floor, lip band and side walls
    return 8.0                          # the skirt: the cavity follows it back


def _bud_deck(x, y):
    """TOP DECK -- the face the screen sits in. The lip over the phone is only
    LIP_H = 2.4 mm thick, so most of this panel is shallow; the strip outboard
    of the pocket is standing on the tray's side wall and can take more.
    ⚠️ The button test is NOT handed: PWR/VOL are on the phone's right edge,
    which is +X whichever way TILT goes."""
    f = _fade((x + 33.0) / 1.5, (y - 11.0) / 2.5, (140.5 - y) / 2.5)
    if (abs(x) < WIN_X + BEZEL_CHAM + 0.6
            and WIN_Y0 - BEZEL_CHAM - 0.6 < y < WIN_Y1 + BEZEL_CHAM + 0.6):
        return 0.8 * f                  # the aperture's flare must survive
    if abs(x) < POCK_W / 2 + 0.5 and y < POCK_L - 0.5:
        return 1.1 * f
    if x > 30.0 and _in_btn(y):
        return 1.5 * f                  # counterbore ceiling is at Z 10.1
    return 2.2 * f


def _bud_wall(side):
    """TRAY SIDE WALL, above the hull's shoulder. 2.4 mm of frozen pocket wall
    below the lip line and 4.9 mm above it. Zero across the button bays.
    ⚠️ This panel cuts the CAP as well (Y < 0), and behind the cap's +X flank
    at Y in [-6, 0] runs the internal cable channel -- which leaves only 1.9 mm
    of flank there by design. That is the wall the square-hole bug went
    through; it does not get shaved."""
    def f(y, z):
        k = _fade((z - 1.0) / 1.5, (OUT_H - 0.3 - z) / 1.5)
        # ⚠️ The button bay is NOT a zero in this map. It used to be, and the
        # relaxation then dragged every triangle touching it down with it --
        # 1497 mm2 of the +X wall came out untouched. The bay is protected by
        # `_btn_keep`, which is a hard box, so the budget here can stay normal
        # and the bay simply stands proud as a pad. Protection belongs in the
        # boolean, not in a hole in the budget field.
        # ⚠️ The internal cable run reaches CABLE_X1 = 35.65 on BOTH solids --
        # the pocket in the cap's plate (Y -6..0) and the slot through the
        # tray floor (Y -1..17) -- so from there out there is only 1.9 mm of
        # flank. That is the wall the square-hole bug went through, and the
        # wall check read 0.86 mm here before this clause existed.
        if side > 0 and -6.5 < y < 18.0 and -6.0 < z < 10.2:
            return 0.4 * k
        return (1.8 if z > OUT_H - LIP_H + 0.4 else 1.1) * k
    return f


def _guard_in(z):
    """|X| of the guard's scooped inner wall at height z -- the same circle the
    well is cut with, so the budget below tracks the real wall thickness
    instead of a guess that would go stale the moment GUARD_H moved."""
    r2 = SCOOP_R_SIDE ** 2 - (_GZ1 - z) ** 2
    return math.sqrt(max(0.0, r2)) + SCOOP_CX


def _guard_out(z):
    """|X| of the guard's nominal outer surface: vertical to GUARD_BEV_H below
    the crest, then raked in by GUARD_BEV_X. This is the `base` of the guard
    panel -- the facets must FOLLOW the bevel, not cut across it."""
    return GUARD_HW - max(0.0, z - (_GZ1 - GUARD_BEV_H)) * (
        GUARD_BEV_X / GUARD_BEV_H)


def _bud_guard(y, z):
    """GUARD OUTER WALL, vertical face and outer bevel as one panel. Thickness
    runs 6.2 mm at the base to CREST_W at the crest, so the budget tapers with
    it and is forced to zero before the crest: CREST_W is set by the min-wall
    check and a facet that ate into it would make the crest a feather edge --
    which is exactly what the first build did, 0.00 mm at Z 28.4."""
    if z > _GZ1 - 1.6:
        return 0.0
    # ⚠️ capped at 3.0 rather than at the wall: past that the guard's outer face
    # falls INBOARD of the tray wall it stands on (37.55 against 40) and the
    # base turns into an undercut ledge instead of a facet.
    return (min(3.0, max(0.0, _guard_out(z) - _guard_in(z) - 1.7))
            * _fade((z - _GZ0 - 0.4) / 1.2))


# ---- the panels themselves -------------------------------------------------
# ⚠️ SD is the deep side, so the guard's outer wall is at X = SD*GUARD_HW and
# the panel normals are handed off it. Written as SD, never as a literal sign.
SHAVE = {}
SHAVE["elbow end"] = facet_shave(
    Vector(0, OUT_L, 0), _UX, _UZ, _UY, -50.0, 56.0, -34.0, 30.0, _bud_end,
    pitch=12.0)
# The deck, between the two brows -- outboard of them the guard covers it.
# ⚠️ Y bounds are where the WELL FLOOR actually starts and stops. The two end
# brows span the full width of the tray, so a panel that ran past them would
# take its 2.2 mm out of the underside of a brow instead of off the deck -- the
# first build did, and left a 0.10 mm sliver under the USB brow's base.
SHAVE["deck"] = facet_shave(
    Vector(0, 0, OUT_H), _UX, _UY, _UZ,
    min(SD * 33.0, -SD * 44.0), max(SD * 33.0, -SD * 44.0), 11.0, 140.5,
    _bud_deck, pitch=10.0)
# ★ The side walls are subtracted from BOTH solids. The cap's end plate is
# flush with the tray's walls, so one shared cutter is what keeps the facets
# running through the joint instead of stepping at it.
for _nm, _sx in (("+X wall (buttons)", 1), ("-X wall", -1)):
    SHAVE[_nm] = facet_shave(
        Vector(_sx * OUT_W / 2, 0, 0), _UY, _UZ, _UX * _sx,
        -CAP_T - 2.0, OUT_L + 2.0, 1.0, OUT_H - 0.3, _bud_wall(_sx),
        pitch=6.0, pitch_b=3.0)
# ★ ONE panel for the guard's whole outer surface, vertical face AND bevel.
# Two panels meeting on the bevel crease left a 1.5 mm ledge running the length
# of the part, because neither knew what the other had cut. Giving the single
# panel the bevel as its `base` makes the facets ride over the crease.
SHAVE["guard wall"] = facet_shave(
    Vector(SD * GUARD_HW, 0, 0), _UY, _UZ, _UX * SD,
    -2.0, OUT_L + 2.0, _GZ0 + 0.2, _GZ1 + 0.1, _bud_guard,
    base=lambda a, b: GUARD_HW - _guard_out(b), pitch=7.5)
# The two CREST RAMPS -- the guard sweeping down into each end. Each is a
# single plane, 654 and 330 mm2, and they are the most visible surfaces on the
# object after the guard wall itself.
# ⚠️ Standing on the elbow these faces point downward at 48 deg. Faceting moves
# each facet a couple of degrees either side of that, so some will cross 45 and
# want support. That is reported by the harness and deliberately not designed
# around -- see the note on the print study.
for _nm, _ry, _sy in (("usb crest ramp", RAMP_Y0, -1), ("jack crest ramp", RAMP_Y1, 1)):
    SHAVE[_nm] = facet_shave(
        Vector(0, _ry, _GZ1), _UX,
        Vector(0, _sy * RAMP_SLOPE, -1.0).normalized(),
        Vector(0, _sy, RAMP_SLOPE).normalized(),
        -42.0, 42.0, -0.5, 24.0, lambda a, b: 1.2, pitch=8.0)

# The cap's own panels are built down in the cap section, where FACE_* and
# CAP_CHIN are declared -- see "THE CAP'S FACETED PANELS".


# ------------------------------------------------------------------- shell
# ★ The wedge is dead volume, so hollow it. The cavity is the same faceted
# section inset by WALL_OUT, bounded away from the arm face by WALL_ARM (which
# leaves 2.8 mm under the strap channel) and left OPEN at the nose -- a closed
# cavity would put an unsupported roof across the whole section at the top of
# the print, and an open one is also the intake for the floor vents.
# ⚠️ TESSELLATED TOO, through the same stations. The cavity has to breathe with
# the body or the skin thickness would swing by the station amplitude -- inset
# the BASE section and put it through the same affine maps and every facet is
# exactly WALL_OUT thick, measured perpendicular to itself, at every station.
cav = tessellated(inset(HULL_SEC, WALL_OUT)) \
    & bbox(-90, 90, CAP_D - 1, OUT_L - CAV_Y1, -90, 90)
# ★★ ...AND THE CAVITY FOLLOWS THE ELBOW END'S FACETS BACK. Without this the
# closing wall is a flat CAV_Y1 = 3 mm slab and the deepest end facet (8 mm)
# would cut straight into the cavity. Cutting the SAME shave solid out of the
# cavity, pushed back by WALL_END, leaves exactly WALL_END of material behind
# every facet -- so the end can be sculpted as deeply as the form wants
# without adding a gram of dead slug behind it.
cav -= Pos(0, -WALL_END, 0) * SHAVE["elbow end"]
# Over the tenon the skin has to be measured off the STEPPED-IN face, or the
# cavity would sit outside it and the tenon wall would come out negative.
cav += prism(inset(HULL_SEC, WALL_OUT), -1.0, CAP_D) & _above
cav += prism(inset(HULL_SEC, TEN_D + WALL_OUT), -1.0, CAP_D) & _below
# ⚠️ Clamp the ceiling to the tray floor's underside. HULL_SHOULDER is 4.5
# now, so the section's top edge insets to Z=2.5 -- above the pocket floor.
# Unclamped the cavity eats the floor and leaves 0.6 mm of it.
cav &= bbox(-90, 90, -30, OUT_L + 30, -90, 0.0)
cav -= arm_cyl(ARM_CUT_R + WALL_ARM)
# ⚠️⚠️ AND THE CUFF STAYS SOLID. The cavity's arm-face boundary is
# ARM_CUT_R + WALL_ARM = 51 and the cuff's outer surface is at 52, so just above
# the flank's foot -- where the flank is running nearly tangent to the cylinder
# -- the skin between them came out at 0.95 mm, and 0.75 at a station scaled
# down. The wall check found it; no render would have. Clearing the cavity out
# of the cuff's own wedge fixes it at the cause instead of thickening WALL_ARM
# everywhere (which would be ~30 g of arm-face skin and would re-open the
# membrane question under the card channel).
for _t0, _t1 in ((SHAL_FOOT_TH + 6.0, -SHAL_WRAP - 6.0),
                 (DEEP_WRAP - 12.0, DEEP_WRAP + 6.0)):
    _w = [(ARM_CX, ARM_CZ)] + [
        cuff_pt(_t0 + (_t1 - _t0) * k / 5.0, R_CUFF + 3.0) for k in range(6)]
    cav -= prism(_w, -2.0, OUT_L + 2.0)
for y in STRAP_Y:
    cav -= arm_cyl(ARM_CUT_R + WALL_ARM_STRAP, STRAP_W + 2 * STRAP_BAND, y)

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
# (dimensions are declared up with the payload block -- the hull is derived
#  from them, so they cannot live down here any more.)
CARD_SW = CARD_W + 2 * CARD_CLR
CARD_X0, CARD_X1 = -CARD_SW / 2, CARD_SW / 2
CARD_Y1 = CARD_L + 1.0
_card_z0 = -(CARD_SH + CARD_LEDGE)

# keep these solid -- subtract them from the cavity before the cavity is cut
for _xa, _xb in ((CARD_X0 - CARD_RAIL, CARD_X0 + CARD_ENG),
                 (CARD_X1 - CARD_ENG, CARD_X1 + CARD_RAIL)):
    cav -= bbox(_xa, _xb, -1.0, CARD_Y1 + CARD_STOP, _card_z0, 0.0)
# ⚠️ The stop's FAR face is raked 45 deg, not square. Square, it is a 3.7 cm2
# flat ceiling in the middle of the print, inside a cavity no support can
# reach. Raked, it is a bridge the slicer can walk up.
cav -= yz_prism([
    (CARD_Y1, _card_z0),
    (CARD_Y1 + CARD_STOP, _card_z0),
    (CARD_Y1 + CARD_STOP - _card_z0, 0.0),
    (CARD_Y1, 0.0),
], CARD_X0, CARD_X1)

part -= bbox(CARD_X0, CARD_X1, -10.0, CARD_Y1, -CARD_SH, 0.0)

# ---------------------------------------------------------- power pack
# ★ A COMMERCIAL card-format bank, not a cell: 85.6 x 54 x 10, the ID-1
# footprint the card channel already uses, just far thicker. It sits directly
# under the cards in the same C-rails pattern, loads from the USB end, and the
# cap retains it -- so nothing can fall out onto the floor when it is off.
# ⚠️ This is what GAP=20 buys. At GAP=8 there were 0 mm under the cards; the
# arm's crown was right up against the tray floor. See the note on GAP.
# (dimensions up with the payload block; PAYLOAD_Z is derived from them and
#  is what the hull's deep flank is cut to.)
PACK_SW = PACK_W + 2 * PACK_CLR
PACK_X0, PACK_X1 = -PACK_SW / 2, PACK_SW / 2
PACK_Y1 = PACK_L + 1.5
for _xa, _xb in ((PACK_X0 - PACK_RAIL, PACK_X0 + PACK_ENG),
                 (PACK_X1 - PACK_ENG, PACK_X1 + PACK_RAIL)):
    cav -= bbox(_xa, _xb, -1.0, PACK_Y1 + 2.0, PACK_Z0 - PACK_LEDGE, PACK_Z1)
cav -= yz_prism([
    (PACK_Y1, PACK_Z0 - PACK_LEDGE),
    (PACK_Y1 + 2.0, PACK_Z0 - PACK_LEDGE),
    (PACK_Y1 + 2.0 + (PACK_Z1 - PACK_Z0 + PACK_LEDGE), PACK_Z1),
    (PACK_Y1, PACK_Z1),
], PACK_X0, PACK_X1)
part -= cav
part -= bbox(PACK_X0, PACK_X1, -10.0, PACK_Y1, PACK_Z0, PACK_Z1)

# ---- cable route: pocket in the cap, slot through the floor, then the cavity
# ⚠️ Outboard of both the card rails and the pack rails, because those already
# take the full 54 mm. The lead goes through on edge.
# ⚠️ It runs OUT TO the pocket wall and 0.5 mm into it, rather than stopping
# short. Stopping short leaves a 0.75 mm rib of floor between slot and wall,
# which the wall check reads at 0.25 -- and it is a rib nobody wants anyway.
# ⚠️ Its inner edge lands exactly on the card rail's outer face. Anywhere else
# leaves a sliver of rail between the two, and at 1.00 mm the wall check calls
# it -- correctly, it would be a rib you could snap with a fingernail.
part -= bbox(CARD_X1 + CARD_RAIL, CABLE_X1,
             -1.0, 17.0, PACK_Z1 - 2.0, FLOOR + 4.0)   # runs out to the mouth,
             # or a 1 mm rib of floor is left standing between slot and face

# ★★ THE RIBS AND THE LOUVRES ARE BOTH GONE. They were two successive
# attempts to stop the chine reading as one lazy blank face -- first cut
# slots, then proud ribs. The tessellation retires the problem instead of
# decorating it: there IS no 29 mm blank facet any more, because the chine is
# now a chorded knee of five or six planes that each catch the light
# differently. Applique on top of that would fight it.

# ------------------------------------------------------------------ visor
# ★ Built BEFORE the apertures, so the screen loft, the earpiece slot, the
# camera and the proximity window all cut straight through it and nothing has
# to be re-cut or dodged. The frozen opening stays exactly the frozen opening.
#
# Three pieces of the reference worth taking: the display is SUNK (the well
# floor is the old face, at OUT_H); the hood stands proud all round; and the
# hood is not a uniform ring -- deep brow at the USB end, shallower at the jack,
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
# ★★ THE GUARD IS ON THE DEEP FLANK, and that is the answer to the question
# this file carried for a round. The screen faces the shallow flank, so his eye
# is over the shallow flank, so the guard must be on the other one. Measured by
# the harness rather than argued: the viewing cone is wide open on the eye side
# and only the far side is walled.
# ⚠️ In the MODEL this is still -X, exactly where his demo put it. Nothing
# moved. What changed is that -X is now correctly the deep, outboard side
# instead of being mislabelled the shallow, inboard one.
_SHL = SD                       # the side the guard is on -- deep flank
_ax = _SHL * SCOOP_CX
_zone_side = (Pos(_ax, OUT_L / 2, _GZ1) * Rot(90, 0, 0)
              * Cylinder(SCOOP_R_SIDE, OUT_L + 300)) \
    + bbox(min(_ax, -_SHL * 90), max(_ax, -_SHL * 90), -60, OUT_L + 60, -90, 200)
_zone_usb = (Pos(0, SCOOP_CY0, _GZ1) * Rot(0, 90, 0)
               * Cylinder(SCOOP_R_BROW, 400)) \
    + bbox(-90, 90, SCOOP_CY0, OUT_L + 60, -90, 200)
_zone_hand = (Pos(0, SCOOP_CY1, _GZ1) * Rot(0, 90, 0)
              * Cylinder(SCOOP_R_BROW, 400)) \
    + bbox(-90, 90, -60, SCOOP_CY1, -90, 200)
guard -= (_zone_side & _zone_usb & _zone_hand
          & bbox(-90, 90, -60, OUT_L + 60, _GZ0 - EPS, _GZ1 + 40))

# ---- the USB-end brow's outer face rakes back off the cap's top ----
# The guard grows out of the cap's face rather than butting against it. In this
# print orientation that face's normal points toward the USB end, which is UP, so
# the rake is free at any angle.
guard -= yz_prism([
    (0.0,                          _GZ0 - EPS),
    (USB_BROW_OUT * (_GZ1 + 30 - _GZ0), _GZ1 + 30),
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

# Phone pocket -- runs out the USB end so the phone slides in
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

# 3.5 mm headphone jack notch, jack end (Y = OUT_L)
# ⚠️ Stops at OUT_H, not OUT_H+10. The notch through the frozen wall is
# unchanged; the overshoot above the face used to cut air and now cuts a
# 20 mm bite out of the hood's jack brow. The plug sits at Z 6.45 and is 6 mm
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


# ------------------------------------------- ★★ APPLY THE FACETED PANELS
# Last, so every panel carves the finished surface -- guard included -- rather
# than a blank that later features would re-flatten. Subtraction only: nothing
# here can add material, move a frozen aperture or reach an arm face.
# ⚠️ The button bays are protected OUTRIGHT as well as by a zero budget. The
# plungers stand BTN_PROUD past the wall, so a panel whose surface sits exactly
# on the wall would still shear their heads off. Belt and braces, because the
# bay is print-in-place and there is no second chance at it.
_btn_keep = None
for (_b0, _b1) in (PWR_SVG, VOL_SVG):
    _k = bbox(X_POCK, X_OUT + BTN_PROUD + 1.0,
              fy(_b1) - (BTN_CB_EXT + 3.0) / 2, fy(_b0) + (BTN_CB_EXT + 3.0) / 2,
              Z_BTN - BTN_CB_H / 2 - 1.0, Z_BTN + BTN_CB_H / 2 + 1.0)
    _btn_keep = _k if _btn_keep is None else _btn_keep + _k

for _nm, _sh in SHAVE.items():
    part -= (_sh - _btn_keep)
    print(f"facet      carved {_nm}")


# --------------------------------------------------------- USB end cap
# The phone slides in at the USB end, so without this it can slide out --
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
# ★★ NO CABLE APERTURE, and no trough. Charging is uncap-and-plug now, so the
# port never has to be reached through the plate. The flared trough went with
# it: it existed ONLY to funnel a fat cable head down to a port behind a thin
# plate, and with no cable passing through it was a leftover speaking a
# different language from the rest of the body. Deleted, not preserved.
USB_Z = FLOOR + PH_T / 2   # port sits mid phone thickness -- still the datum
                           # the internal cable and the speaker holes work off
# ⚠️ The speaker and the primary mic sit either side of the port on the phone's
# bottom edge, and both stay OPEN. The speaker is the TTS output and the mic is
# the PTT input -- the entire input half of the device. Plain rectangular
# holes, widened now there is no port between them.
SPK_W, SPK_H = 16.0, 3.4
SPK_X = 17.0               # centre offset either side of the port
# ★ The face instead gets a recessed panel: a flat sunken rectangle with the
# two vent slots in it, bevelled at CHAMFER like everything else. Chunky and
# flat, which is the language the body speaks.
FACE_INSET = 5.0           # margin from the face outline to the panel, X
FACE_INSET_Z = 2.2         # ...and Z, where there are only 13.4 mm to play with
FACE_DEPTH = 2.5           # how far the panel sinks


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


def sec_x(z, side):
    """★ Where the SECTION actually is at height z, on `side` (+1 = the +X
    half of the model). Everything about the snap -- dimple, nose, relief slot
    -- used to be written against HULL_HW, which was fine while the flank was a
    flat plane at exactly that X. The flank now BOWS OUT to FLANK_BULGE proud of
    it, so a dome placed at HULL_HW sits buried 2.4 mm inside the wall: the cap
    came out in three pieces and the fit check found 8.85 mm3 of interference.
    Read the flank off the polygon instead."""
    best = None
    n = len(HULL_SEC)
    for i in range(n):
        (x0, z0), (x1, z1) = HULL_SEC[i], HULL_SEC[(i + 1) % n]
        if (z0 - z) * (z1 - z) > 0 or abs(z1 - z0) < 1e-9:
            continue
        x = x0 + (x1 - x0) * (z - z0) / (z1 - z0)
        if x * side <= 0:
            continue
        if best is None or x * side > best * side:
            best = x
    return HULL_HW * side if best is None else best
_cap_below = bbox(-80, 80, -CAP_T - 1, CAP_D + 1, -80, HULL_BELT)

# Flank Z spans, per side. ⚠️ HANDED -- the shallow flank is ~9 mm tall and the
# deep one ~12, so the snap features are placed per flank, never mirrored.
# ⚠️ The shallow flank now ends where it meets the CUFF, not where it happens
# to cross the arm -- and the corner is a chorded knee, so the flat part of the
# flank stops a good few mm above HULL_Z_SHAL. The dome has to sit on the flat.
_sh_bot = HULL_Z_SHAL + 5.0
# ⚠️ Midpoint of the FLAT flank, not of the whole flank: the belt's 3 mm bevel
# eats the top of it, and a dome centred on the raw midpoint would sit half in
# the bevel face.
# ⚠️ ...and on the deep side, of the flank ABOVE the relief slot, because the
# slot is what turns that flank into a cantilever. Below it the collar is stiff.
DEEP_SLOT_Z0 = HULL_Z_DEEP + 6.0          # bottom of the flat deep flank
DEEP_SLOT_Z1 = DEEP_SLOT_Z0 + CAP_SLOT_W
FLANKS = ((-SD, (HULL_BELT - 5.0 + _sh_bot) / 2),
          (SD, (HULL_BELT - 5.0 + DEEP_SLOT_Z1) / 2))

# Dimples in the TENON's flanks now, not the tray's. TRUNCATED CONES, not
# cylinders and not spheres: a cylinder presents a sharp edge square to the
# travel direction and will not go on at all, while a sphere rams a curved
# surface into a flat one and OCCT emits a non-manifold shell there (verified
# -- removing the spheres took both parts from 378 broken faces to zero).
for _sd, _zc in FLANKS:
    _sx = 1 if _sd > 0 else -1
    # ⚠️ Rooted 1.2 mm OUTBOARD of the tenon face, not 0.2. The flank is a
    # bowed curve now, so a cone whose base plane sits just off that curve
    # grazes it tangentially a millimetre up and leaves a feather -- the wall
    # check read 0.04 mm there. Start the cut clear of the surface entirely.
    part -= Pos(sec_x(_zc, _sx) - _sx * (TEN_D - 1.2), CAP_BUMP_Y, _zc) \
        * Rot(0, -90 * _sx, 0) \
        * Cone(CAP_BUMP_R, CAP_BUMP_R * 0.55, CAP_DIMPLE_D + 1.2,
               align=(Align.CENTER, Align.CENTER, Align.MIN))

# Collar: the wall between the tenon and the full section, below the belt.
# ⚠️ ...and the collar STOPS ON THE CUFF, for the same reason the tenon does:
# there is no room for a 2 mm wall plus a 2.3 mm rebate inside a 3 mm cuff. The
# hull carries the cuff straight through the joint and the collar lands on its
# shoulder with CAP_CLR of relief.
cap = ((prism(HULL_SEC, 0.0, CAP_D) & _cap_below) - arm_cyl(R_CUFF + CAP_CLR)) \
    - prism(CAP_SEC_IN, -EPS, CAP_D + EPS)
# End plate: the whole face -- hull section below, tray section above.
cap += prism(HULL_SEC, -CAP_T, 0.0)
cap += bbox(-OUT_W / 2, OUT_W / 2, -CAP_T, 0.0, 0.0, OUT_H)
# ⚠️ NO guard band on the cap any more. The guard's USB-end brow rakes back off
# the cap's top face instead of running across it, so the cap tops out at the
# tray face and the guard grows out from behind it. That also retires the
# height mismatch at the joint that his demo file still has.
# ...and the deep-flank ribs, same profile as the hull's so they line through.
# ⚠️ The saddle runs through the cap too. Without this the plate would close
# off the USB end of the arm channel and sit on the forearm.
cap -= arm

# ★ The cap's CHIN rakes back: its face leans away from the wrist as it drops
# through the hull's section, so the nose is a wedge and not a slab. Kept below
# Z=0 so it never touches the USB trough or the speaker mouths, and its normal
# points toward the USB end -- up, in this print orientation -- so it is free.
# ⚠️ -SAG, not HULL_Z_DEEP. The rake has to run out BELOW the deepest point of
# the section or it stops half way down and the face steps back out under it --
# which is a ledge, an overhang, and (measured) a 0.87 mm wall where the chine
# is thin. HULL_Z_DEEP was the deepest point until the section was cut back.
cap -= yz_prism([
    (-CAP_T,                  0.0),
    (-CAP_T + CAP_CHIN,       -SAG - 10),
    (-CAP_T - 40,             -SAG - 10),
    (-CAP_T - 40,             0.0),
], -90, 90)

# Plan-view rake on the nose corners, carried over from the hull's nose (the
# hull no longer has one -- the cap IS the nose now). A cut plane containing Z
# has no Z in its normal, so it costs nothing in the print orientation, and it
# is sized to finish exactly at Y=0 so it never reaches the collar and cannot
# skin the corner off a 2 mm wall.
for _sx in (-1, 1):
    _n = Vector(_sx * CAP_T, -CAP_RAKE, 0).normalized()
    # ⚠️ Off GUARD_HW. The hood used to reach 41.5 and raking to 40 by Y=0 cut
    # its corners off; GUARD_HW is now the belt line itself, so they agree.
    _p0 = Vector(_sx * (GUARD_HW - CAP_RAKE), -CAP_T, 0)
    cap -= Pos(_p0 + _n * 100.0) \
        * Rot(0, 0, math.degrees(math.atan2(_n.Y, _n.X))) * Box(200, 200, 200)

# ---- the face: a FACETED WELL, not a flat sunken panel ----
# ★★ It used to be a flat rectangle sunk FACE_DEPTH into the plate with a
# bevelled rim. That was the right instinct on a chamfered body and the wrong
# one on a faceted one: its floor came out as 617 mm2 of unbroken plane, the
# single largest facet on either solid, sitting in the middle of the wrist end
# -- the end you look at when the thing is on your arm. Trying to keep the flat
# floor AND facet it fought itself (a stepped `base` either left the floor
# untouched or made a 32 deg wedge at the rim), so the flat is gone: the recess
# is now carved entirely by the face panel, whose budget runs from 1.3 mm at
# the rim to FACE_DEPTH + 1.5 in the middle. Same silhouette, no plane in it.
# FACE_INSET / FACE_INSET_Z still set where the rim is; FACE_DEPTH still sets
# how deep the middle goes.
_fz0, _fz1 = FACE_INSET_Z, OUT_H - FACE_INSET_Z
_fx = OUT_W / 2 - FACE_INSET

# Speaker and primary mic, straight through the plate. No taper, no funnel --
# they are holes, and both have to stay open: the speaker is TTS out, the mic
# is PTT in.
for _sx in (-1, 1):
    cap -= Pos(_sx * SPK_X, -CAP_T - EPS, USB_Z) * Rot(-90, 0, 0) * extrude(
        RectangleRounded(SPK_W, SPK_H, SPK_H / 2 - 0.01), amount=CAP_T + 2 * EPS)

# ---- internal cable route ----
# ⚠️ A pocket in the plate's INNER face, not a hole through it. The phone's
# right-angle head sits in here, the lead turns, and it runs out sideways to
# CABLE_X where a slot through the tray floor drops it into the cavity, past
# the card rails rather than across the cards. Nothing passes through the
# outer face, so the cap still closes the end completely.
cap -= bbox(-CABLE_W / 2, CABLE_W / 2, -PLUG_D, EPS,
            USB_Z - CABLE_H / 2 - 1.0, USB_Z + CABLE_H / 2 + 1.0)
# ⚠️⚠️ CABLE_X1, not "a centre plus half a width". This is the cut that put a
# square hole in the nose -- see the note at CABLE_W. It now stops exactly where
# the floor slot it feeds stops, which leaves OUT_W/2 - CABLE_X1 = 1.9 mm of
# flank standing. The wall check polices that number and the cap-closure check
# below it polices the hole.
cap -= bbox(-CABLE_W / 2, CABLE_X1, -CABLE_H - 1.0, EPS,
            -1.0, USB_Z + CABLE_H / 2 + 1.0)

# ★ No relief slots on the shallow side, and no tongues. The collar is a C, so
# each flank is ALREADY a cantilever: bounded by the belt above, by the saddle
# below, free at the open end, and rooted only in the end plate. V1 needed
# tongues because its collar was a closed rectangle braced on four sides.
# The deep side does need one slot -- there the collar wraps the flank into the
# chine, and that fold is stiff enough to resist the 0.3 mm the dome has to
# ride, so this frees the flank from it. It sits at the foot of the flat flank.
_slot_x = sec_x((DEEP_SLOT_Z0 + DEEP_SLOT_Z1) / 2, SD)
cap -= bbox(min(_slot_x, _slot_x - SD * CAP_W) - 0.4,
            max(_slot_x, _slot_x - SD * CAP_W) + 0.4,
            CAP_SLOT_ROOT, CAP_D + EPS,
            DEEP_SLOT_Z0, DEEP_SLOT_Z1)

# Snap noses: cones rooted inside the wall (never coplanar with a face) and
# protruding 0.6 mm past the inner surface, so they stand 0.3 mm proud of the
# tenon and seat into its dimples. Sat near the free end so the cantilever is
# as long as the collar allows -- the strain at the root goes as 1/L^2.
for _sd, _zc in FLANKS:
    _sx = 1 if _sd > 0 else -1
    cap += Pos(sec_x(_zc, _sx) - _sx * (CAP_W / 2), CAP_BUMP_Y, _zc) \
        * Rot(0, -90 * _sx, 0) \
        * Cone(CAP_BUMP_R, CAP_BUMP_R * 0.5, CAP_W / 2 + 0.6,
               align=(Align.CENTER, Align.CENTER, Align.MIN))

# ------------------------------------------- ★★ THE CAP'S FACETED PANELS
# Its deck, so the top face reads as one treated surface across the joint
# rather than facets that stop dead at Y = 0...
CAP_SHAVE = {}
CAP_SHAVE["cap deck"] = facet_shave(
    Vector(0, 0, OUT_H), _UX, _UY, _UZ, -44.0, 44.0, -CAP_T - 1.0, 1.0,
    lambda a, b: 2.0 * _fade((b + CAP_T) / 3.0), pitch=9.0)
# ...the plate face above Z=0. ⚠️ The two panels either side of Z=0 both taper
# to nothing AT Z=0. They are different planes (the chin rakes, the face does
# not) and two independent faceted surfaces meeting head-on left a 0.12 mm
# knife edge along the join -- the wall check found it. Meeting on the crease
# that is already there costs a 2 mm unfaceted band and is worth it.
# ★ The whole face is ONE graded budget: 1.3 mm at the rim, FACE_DEPTH + 1.5 in
# the middle, transitioning over 3 mm. That IS the sunken panel -- same
# silhouette, same depth, but built out of facets so there is no floor plane in
# it. ⚠️ Behind the middle of this face sits the cable/plug pocket at Y = -6, so
# the deepest the budget may go is CAP_T - PLUG_D - MIN_WALL = 4.8; 4.0 leaves
# 2.0 mm of plate.
def _cap_panel(a, b):
    return _fade((_fx - abs(a)) / 3.0, (b - _fz0) / 3.0, (_fz1 - b) / 3.0)


CAP_SHAVE["cap face"] = facet_shave(
    Vector(0, -CAP_T, 0), _UX, _UZ, _UY * -1, -44.0, 44.0, 0.0, OUT_H,
    lambda a, b: ((1.3 + (FACE_DEPTH + 1.5 - 1.3) * _cap_panel(a, b))
                  * _fade(b / 2.5, (OUT_H - b) / 2.0)),
    pitch=7.0, pitch_b=3.0)
# ...and the CHIN below it, which is the cap's single largest face: the whole
# raked nose, 1424 mm2 of it. ⚠️ Its panel is the RAKE PLANE, not Y = -CAP_T,
# so the facets sit on the surface that is actually there. Carving a raked face
# from a vertical panel would have flattened the rake back out over half its
# height and left a step where the two disagreed.
_chin_v = Vector(0, CAP_CHIN, -(SAG + 10.0)).normalized()
CAP_SHAVE["cap chin"] = facet_shave(
    Vector(0, -CAP_T, 0), _UX, _chin_v,
    Vector(0, -(SAG + 10.0), -CAP_CHIN).normalized(),
    -46.0, 56.0, 0.0, SAG + 8.0,
    lambda a, b: min(1.0, b / 3.0) * 2.2, pitch=11.0)
# ...and the two plan-view rakes on the nose corners, 372 and 303 mm2.
for _sx in (-1, 1):
    _n = Vector(_sx * CAP_T, -CAP_RAKE, 0).normalized()
    # ⚠️ Faded out before B = 14.4, which is where this plane crosses Y = 0.
    # The rake is deliberately sized "to finish exactly at Y=0 so it never
    # reaches the collar"; a facet 1.2 mm past it does reach the collar, and
    # the crest check found the 33 deg wedge it left at (-40, 1.5, -7.3).
    CAP_SHAVE[f"cap nose rake {_sx:+d}"] = facet_shave(
        Vector(_sx * (GUARD_HW - CAP_RAKE), -CAP_T, 0), _UZ,
        Vector(CAP_RAKE * _sx, CAP_T, 0).normalized(), _n,
        -SAG - 6.0, OUT_H + 1.0, -16.0, 14.0,
        lambda a, b: 1.2 * _fade((12.0 - b) / 2.0, (b + 14.0) / 2.0),
        pitch=8.0)

# ★ The two SIDE-WALL panels are the ones off the bracer, not copies. The cap's
# end plate is flush with the tray's own walls, so cutting both solids with the
# SAME solid is what makes the facets run through the joint instead of stepping
# at it -- the same argument as the tenon, applied to the surface treatment.
# ⚠️ Nothing here touches the collar, the bore or the snap noses: every panel
# is above Z = 1.0 or ahead of Y = 0, and the collar lives below the belt at
# Y > 0. The seated/slide-path interference check is the proof, not this note.
for _nm, _sh in list(CAP_SHAVE.items()) + [
        (k, SHAVE[k]) for k in ("+X wall (buttons)", "-X wall")]:
    cap -= _sh
    print(f"facet      carved {_nm} (cap)")


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
# jack-end perimeter -- takes the full 3 mm.
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


# ⚠️ The jack-end perimeter is DELIBERATELY LEFT SHARP, and this is the one
# place the 3 mm rule is not applied. Two reasons, both hard:
#   * the tray's jack-end wall is 2.4 mm of frozen pocket, so a 3 mm chamfer on
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
# ⚠️ Rot(-90,0,0) sends +Y to -Z, so the JACK end (Y=OUT_L) goes to the bed.
# That is the ELBOW end as worn. Verified
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
# ★ The section is now generated, not typed, so print what it came out as --
# verify_bracer.py's probes are placed against these numbers and they have to
# be readable without running a debugger.
print(f"section    {len(HULL_SEC)} facets, widest |X| "
      f"{max(abs(x) for x, _ in HULL_SEC):.2f}, "
      f"deep {min(x for x, _ in HULL_SEC):.2f}, shallow "
      f"{max(x for x, _ in HULL_SEC):.2f}")
print(f"           shallow foot {SHAL_FOOT_TH:.1f} deg at "
      f"({P_CUF_S[0]:.1f},{P_CUF_S[1]:.1f})  deep hem "
      f"({TOE_X:.1f},{TOE_Z:.1f})  chine top ({P_CHI_D[0]:.1f},{P_CHI_D[1]:.1f})")
for _z in (-8.0, -11.0, -14.0, -17.0):
    print(f"           flank X at Z {_z:6.1f}:  deep {sec_x(_z, SD):7.2f}   "
          f"shallow {sec_x(_z, -SD):7.2f}")
print(f"hull drop  {SAG:.2f} mm deep side, {-HULL_Z_SHAL:.2f} shallow "
      f"(TILT={TILT}, ARM_R={ARM_R}, GAP={GAP})")
print(f"volume     {part.volume/1000:.1f} cm3  ~= {part.volume/1000*1.27:.0f} g PETG")
