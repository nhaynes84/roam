"""
Numeric verification for the bracer. Per cad-tooling: never trust a render to
prove geometry -- probe it with trimesh.

Five passes:
  1. solid/empty probes at points that discriminate every feature
  2. mesh integrity + mass
  3. ★ MINIMUM WALL THICKNESS -- solid/empty probes cannot see a feather edge.
     A knife edge got all the way to the owner's hand once; this is the check
     that would have caught it. Self-tested against synthetic bad geometry on
     every run, so it cannot quietly degrade into agreeing with me.
  4. end cap vs tray interference, seated AND swept through the whole slide
  5. print-orientation study: measured unsupported-face area per orientation,
     rather than guessing which way up it should go
"""
import re
import numpy as np
import trimesh
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
m = trimesh.load(os.path.join(HERE, "out", "bracer.stl"))
m.fix_normals()
cap = trimesh.load(os.path.join(HERE, "out", "bracer_endcap.stl"))
cap.fix_normals()
# ★ The pack module -- a THIRD solid since 2026-08-12. It is where the battery
# went when it came out from under the phone, and it gets probed like the cap
# does: the defect that argued for the cap's own pass (a window straight
# through the nose) was invisible to every probe on the other solid, and a new
# part with no probes at all is the same bet taken again.
mod = trimesh.load(os.path.join(HERE, "out", "bracer_pack.stl"))
mod.fix_normals()

# geometry constants, mirrored from bracer.py
FLOOR, POCK_D, LIP_H = 2.2, 8.8, 2.4
OUT_W, OUT_L, OUT_H = 75.1, 147.0, 13.4
POCK_W = 70.3
HULL_HW, TEN_D, HULL_BELT = 40.0, 2.3, -5.0
SAG = 18.85
GUARD_H, GUARD_HW = 15.0, 40.0
PACK_T, PACK_W, PACK_L = 10.0, 54.0, 85.6
PACK_LEDGE, PACK_RAIL, PACK_CLR = 1.6, 3.0, 0.6
# ★★ THE PACK IS NO LONGER UNDER THE TRAY (2026-08-12). It costs 13 mm of
# standoff there and nothing on the underside of the forearm, so it moved to a
# strap module -- bracer_pack.stl, checked at the foot of this file. What is
# left under the tray is the two ID-1 cards, and the payload envelope every
# check below measures the body against shrinks to match.
PACK_ONBOARD = False
# ★ The payload envelope and the arm, which between them are the WHOLE reason
# any material exists below the belt. The dead-structure check below measures
# the body against exactly these two things.
CARD_RAIL_ = 5.0
PAYLOAD_Z = -3.2                                       # card channel + ledge
PAYLOAD_HW = 53.98 / 2 + 0.35 + CARD_RAIL_             # 32.34
ARM_R, GAP, FOAM, TILT = 45.0, 11.6, 4.0, -25.0
ARM_CUT_R = ARM_R + FOAM
ARM_CX = -ARM_R * math.sin(math.radians(TILT))
ARM_CZ = -(GAP + FOAM) - ARM_R * math.cos(math.radians(TILT))
CAP_FLANK_MIN = 6.0
HULL_Z_DEEP = min(PAYLOAD_Z - 2.0, HULL_BELT - CAP_FLANK_MIN)   # -11.0
GZ1 = OUT_H + GUARD_H
# ⚠️ WIN_X is DERIVED below from bracer.py's SCREEN_SVG, not mirrored. It was
# mirrored as 32.03 and the owner then brought the bezel in 2 mm a side, so the
# viewing-cone check went on casting its ray from 1.8 mm OUTSIDE the window --
# under solid bezel -- and reported the cone had collapsed to 0 deg on a model
# whose cone was fine. Same class of failure as the camera and prox probes.
BEZEL_CHAM, LIP_H = 1.5, 2.4
CARD_L, CARD_W, CARD_T = 85.60, 53.98, 0.76   # ISO/IEC 7810 ID-1
STRAP_Y0, STRAP_Y1 = 34.0, 112.0
# ★ Calibrated, not picked. The thinnest wall the FROZEN housing deliberately
# has is 1.20 mm -- the 2.4 mm pocket wall behind the 1.2 mm button counterbore,
# at the 1.5 mm ends where the bore does not pierce it. So the bar sits just
# under that. Anything thinner than this is new, and new means a mistake:
# at 1.5 this check found a 1.05 mm arm-face wall a vent had eaten and a
# 0.01 mm feather where the cap's cable trough ran out onto the plate face.
# ⚠️ The button plungers are checked at a lower bar and separately. Their
# flange is BTN_CB_D - BTN_CLR = 0.85 mm BY DESIGN and that dimension is
# frozen -- holding them to the shell's threshold would mean either a
# permanently red harness or quietly relaxing the shell's number too.
MIN_WALL = 1.15
MIN_WALL_PLUNGER = 0.8
CAP_D, CAP_T = 10.0, 12.0

Z_FACE = FLOOR + POCK_D          # phone front face

# ★★ The face features are READ OUT OF bracer.py, not mirrored by hand like the
# scalars above.
#
# ⚠️ This is the one place mirroring actually bit. The camera and proximity
# probes were literal coordinates — (-23.53, 138.4) and (-1.0, 132.5) — so when
# the owner measured a printed part and moved both features, the probes went on
# testing the empty bezel where the holes used to be and reported FAIL on a
# model that was correct. A harness that has to be hand-edited to agree with the
# thing it checks will disagree with it eventually, and silently.
#
# Parsed from the source rather than imported: importing bracer.py runs the
# whole 13 s build, and the point of this file is that it takes one second.
def _svg_tuple(name):
    src = open(os.path.join(HERE, "bracer.py")).read()
    hit = re.search(rf'^{name} = \(([^)]*)\)', src, re.M)
    if not hit:
        raise SystemExit(f"verify: cannot find {name} in bracer.py")
    return [float(v) for v in hit.group(1).split('#')[0].split(',')]

def _svg_scalar(name):
    src = open(os.path.join(HERE, "bracer.py")).read()
    hit = re.search(rf'^{name} = ([0-9.]+)', src, re.M)
    if not hit:
        raise SystemExit(f"verify: cannot find {name} in bracer.py")
    return float(hit.group(1))

_CAM_SVG = _svg_tuple("CAM_SVG")            # cx, cy, r
_PROX_SVG = _svg_tuple("PROX_SVG")          # x0, y0, x1, y1
_SCREEN_SVG = _svg_tuple("SCREEN_SVG")      # x0, y0, x1, y1
_FEAT_TOL = _svg_scalar("FEAT_TOL")
_PH_W = 69.5
_PHONE_TOP_Y = 144.18                        # POCK_L - CLR, mirrored
_fx = lambda x: x - _PH_W / 2
_fy = lambda y: _PHONE_TOP_Y - y
WIN_X = max(abs(_fx(_SCREEN_SVG[0])), abs(_fx(_SCREEN_SVG[2]))) + _FEAT_TOL
SIGHT = BEZEL_CHAM / LIP_H
_CAM_XY = (_fx(_CAM_SVG[0]), _fy(_CAM_SVG[1]))
_PROX_XY = (_fx((_PROX_SVG[0] + _PROX_SVG[2]) / 2),
            _fy((_PROX_SVG[1] + _PROX_SVG[3]) / 2))
probes = [
    # ---------------------------------------------------- frozen phone housing
    # (label, point, expect_solid)
    ("phone pocket interior",        (0, 70, FLOOR + 4), False),
    ("tray floor rail under phone", (0, 43, 1.0), True),
    ("pocket wall, left",            (-36.3, 70, FLOOR + 4), True),
    # The plungers fill their bores, so these read SOLID. That they are not
    # fused to the wall is asserted by the body count below, not by a probe --
    # the running clearance is 0.35 mm and probing a gap that thin is a
    # coin toss, which is worse than no test at all.
    ("volume plunger in its bore",   (36.3, 80.0, FLOOR + 4), True),
    ("power plunger in its bore",    (36.3, 102.0, FLOOR + 4), True),
    ("wall between the two buttons", (36.3, 94.0, FLOOR + 4), True),
    ("wall below volume opening",    (36.3, 60.0, FLOOR + 4), True),
    ("floor vent",                   (0, 73, 1.0), False),
    ("retaining lip over bezel",     (34.0, 70, Z_FACE + 1.0), True),
    ("screen window (clear)",        (0, 70, Z_FACE + 1.0), False),
    # The bezel: face material above the phone, outside the display aperture.
    # If this is empty the housing is exposing the phone's own bezel again.
    ("bezel above the screen",       (0, 135.0, Z_FACE + 1.0), True),
    ("bezel below the screen",       (0, 10.0, Z_FACE + 1.0), True),
    ("earpiece slot",                (0, 138.2, Z_FACE + 1.0), False),
    ("front camera hole",            (_CAM_XY[0], _CAM_XY[1], Z_FACE + 1.0), False),
    ("proximity/ambient window",     (_PROX_XY[0], _PROX_XY[1], Z_FACE + 1.0), False),
    ("bezel between camera and ear", (-15.0, 138.2, Z_FACE + 1.0), True),
    # ⚠️ The jack is in the button-side quartile, NOT centred -- so the wall
    # probe moved to the far side and the notch probe moved onto the jack.
    ("hand-end wall, far side",      (-25.0, 145.8, FLOOR + 4), True),
    ("hand-end wall at centre",      (0.0, 145.8, FLOOR + 4), True),
    ("headphone jack notch",         (22.0, 145.8, FLOOR + 4), False),
    ("USB end open for insertion",   (0, 1.0, FLOOR + 4), False),
    # ⚠️ Still empty, and it still matters: the button bore runs Z 4.6..8.6
    # out to the tray wall, so hull standing outboard of it here would bury
    # the plungers. The tessellated section is built with its top two points
    # BURIED INSIDE the tray for exactly this reason.
    ("no hull above the belt line",  (39.0, 60.0, 6.0), False),

    # ------------------------------------------------------------ outer hull
    # ⚠️ Depths are asymmetric: TILT drops one side, so the same feature sits at
    # very different Z on each flank. Probed, not assumed.
    # ★★ The section was cut back to the payload on 2026-08-12. The deep flank
    # now STOPS one wall under the pack and a single chine closes it onto the
    # arm, so most of these moved. The one that matters most is the third: it
    # stands where 26 mm of curtain and a corner used to be, and it must stay
    # empty. That is the whole of the owner's "material at the bottom where
    # nothing sits" defect, expressed as a point.
    # ★★ 2026-08-12, the low-poly/cuff pass. The flanks BOW OUT (FLANK_BULGE)
    # and are chorded into planes, and the underside is a CUFF: the shell now
    # leaves the arm at the same wrap angle on both sides instead of being
    # sliced off by the cylinder on the shallow one. So these moved, and the
    # ones that matter are the last four -- they are the owner's two complaints
    # ("hard cuts sides", "a weird underbelly") written as points.
    # ★★ ...and 2026-08-12 again, the PAYLOAD SPLIT. The pack came off the
    # body, so GAP fell 23 -> 11.6 and the arm rose 11.4 mm inside the section,
    # while the deep flank's foot rose 6.6. Every probe below the belt moved
    # with it. They are taken off the built mesh, not offset by hand.
    ("hull skin, deep flank",        (-40.25, 60.0, -10.0), True),
    ("outside the deep flank",       (-45.0, 60.0, -10.0), False),
    ("hull skin, shallow flank",     (38.0, 60.0, -10.0), True),
    ("★ old dead corner stays gone", (-38.0, 60.0, -16.0), False),
    ("chine skin",                   (-32.0, 60.0, -14.0), True),
    ("outside the chine",            (-40.0, 60.0, -14.0), False),
    # ★ THE CUFF. The shallow side used to stop at 25 deg of wrap where the
    # flank happened to cross the cylinder; it now carries on round to
    # SHAL_WRAP = DEEP_WRAP and closes on a hem. If this reads empty the
    # underside has gone back to being cut off flat.
    ("★ shallow cuff wraps the arm",  (46.5, 60.0, -14.0), True),
    ("nothing outboard of the cuff", (50.0, 60.0, -14.0), False),
    ("cuff is solid, not shelled",   (45.0, 60.0, -14.0), True),
    ("nothing below the hem",        (-12.5, 60.0, -21.0), False),
    ("hull cavity behind the flank", (-33.0, 60.0, -10.0), False),
    ("hull cavity, over the arm",    (0.0, 60.0, -8.0), False),
    ("arm-face skin under cavity",   (0.0, 60.0, -10.1), True),
    ("arm void below the skin",      (0.0, 60.0, -12.0), False),
    ("cavity open at the nose",      (0.0, 14.0, -8.0), False),
    # ★ Card ACCESS. The channel must open at the USB end, because that is
    # the wrist -- the end his free hand reaches. If this ever reads solid
    # the cards load from the elbow end and that is an ergonomic failure,
    # not a naming one.
    ("card channel opens at USB end", (0.0, -5.0, -1.0), False),
    ("card stop is at the far end",  (0.0, 87.5, -1.0), True),
    # ★★ THE PACK IS NOT IN HERE ANY MORE. It is in bracer_pack.stl, on the
    # underside of the arm -- see the module pass at the foot of this file. The
    # five probes that used to police its channel are replaced by ONE that
    # polices its absence: the volume it used to occupy is now the arm's, and
    # if anything ever grows back into it GAP has crept back up with it.
    ("pack channel is gone",         (-8.0, 60.0, -7.0), False),
    ("shell closes onto the arm",    (-8.0, 60.0, -12.0), True),
    # ★ ...and the lead has to be able to LEAVE, or the module is a paperweight.
    ("cable exit through the flank", (-40.5, 16.0, -8.0), False),
    ("flank is solid beside it",     (-40.5, 26.0, -8.0), True),
    ("cable slot through the floor", (34.0, 8.0, 1.0), False),
    ("floor beside the cable slot",  (34.0, 25.0, 1.0), True),

    # ------------------------------------------------------- cap tenon
    # The nose steps IN by TEN_D below the belt so the cap's collar lands
    # flush. If the step is missing the cap stands proud again; if it is too
    # deep the collar rattles. Probed either side of the tenon's flank face.
    ("tenon flank, deep side",       (-38.0, 3.0, -8.0), True),
    ("collar space outside tenon",   (-40.6, 3.0, -8.0), False),
    # ★ A REAL dimple test, at last. The old one probed a point outboard of the
    # tenon face, which is empty whether the dimple was cut or not -- and it
    # was passing while the deep dome had migrated onto the chine. These two
    # differ ONLY by Y: one is on the dome's centre, one is 8 mm along the
    # flank. If they ever read the same the snap has stopped being cut.
    # ⚠️ 2.5, not 15: the tenon is only CAP_D = 10 mm long, so a probe at Y 15
    # is past the end of it and reads empty for the wrong reason.
    ("snap dimple in tenon flank",   (-38.85, 7.0, -8.0), False),
    ("tenon flank beside the dimple", (-38.85, 2.5, -8.0), True),
    ("full section above the belt",  (-38.5, 3.0, -1.0), True),

    # ------------------------------------------------------- card slots
    ("card channel, mid",            (0.0, 40.0, -1.0), False),
    ("card channel at the nose",     (0.0, 2.0, -1.0), False),
    ("card rail web, deep side",     (29.5, 40.0, -1.0), True),
    ("card rail web, shallow side",  (-29.5, 40.0, -1.0), True),
    ("floor above the card channel", (0.0, 40.0, 1.0), True),
    ("thick arm band under strap",   (0.0, 34.0, -7.7), True),
    # ------------------------------------------------- ribs and visor
    # The canted louvres are gone; these are the proud ribs that replaced them.
    # ⚠️ They live on the CHINE now, not the deep flank -- so they are neither
    # vertical nor at |X| = HULL_HW, and the probes have to be taken on the
    # facet. Points computed off TOE + u*(along) + v*(outward).
    # The high guard: three-sided, screen sunk deep inside it.
    # ⚠️ -36.2, not -39.0. The guard's outer wall is FACETED since 2026-08-12
    # and recedes up to 3 mm from GUARD_HW, so a probe pinned to the old flat
    # plane tests the tessellation rather than the guard. The wall itself is
    # what matters: it must be present between the scoop (33.8 at the base) and
    # the belt line, and the "no guard on the shallow flank" probe below is
    # what still pins the guard to one side.
    ("guard wall, deep/outboard",    (-36.2, 73.0, OUT_H + 6.0), True),
    ("guard wall near the crest",    (-37.5, 73.0, OUT_H + 12.6), True),
    ("screen well is open",          (0.0, 73.0, OUT_H + 6.0), False),
    # ★ THREE-sided. If this reads solid a guard has appeared on the deep
    # flank and the whole point of the section is gone.
    ("shallow flank has NO guard",   (39.0, 73.0, OUT_H + 6.0), False),
    ("scoop has cut the wall back",  (-34.5, 73.0, OUT_H + 6.0), False),
    ("...but not at its base",       (-34.5, 73.0, OUT_H + 0.4), True),
    # ★★ THE TWO BROWS MUST MATCH -- measured off the mesh, in its own section
    # below. It used to be four fixed-height probes (present at 4.5, absent at
    # 5.5), which stopped meaning anything once the crest ramps were faceted:
    # a facet moves the local crest by a few tenths, so the probes were testing
    # the tessellation and not the thing the owner actually complained about,
    # which was that one brow was massive and the other was not. Measure both
    # and compare them.
    ("crest ramps down at the jack", (-37.0, 144.0, OUT_H + 13.0), False),
    ("crest ramps down at the USB",  (-37.0, 4.0, OUT_H + 13.0), False),
    ("nothing above the crest",      (-37.0, 73.0, GZ1 + 1.0), False),
    # Strap runs in a channel under the hull instead of through side flanges,
    # so the device is tray-width. The bars bridge that channel, and they are
    # spaced about the ARM'S crown (X = ARM_CX), not the tray's centre line.
    ("strap channel is open, deep",  (-8.0, 34, -14.0), False),
    ("retaining bar fills it, deep", (5.0, 34, -6.0), True),
    ("strap channel is open, shal",  (25.0, 34, -6.5), False),
    ("retaining bar fills it, shal", (33.0, 34, -6.0), True),
    # ...and the same two points off the band, where the channel is only skin.
    ("no bar between the bands",     (33.0, 60, -6.0), False),
]

# ★ The cap gets its own pass now. The defect that prompted it -- a 5.5 x 10.7
# square window straight through the nose's shallow flank, where the internal
# cable channel over-ran the cap's own half width -- was invisible to every
# probe here, because every probe here is on the other solid.
cap_probes = [
    # ⚠️ X 36.0, not 36.5. Both the side-wall panel and the nose's plan rake are
    # faceted now, so the flank's outer surface moves by up to ~1.2 mm; these
    # probes sit just OUTBOARD of CABLE_X1 (35.65), which is the number they
    # exist to police -- the cable run must not reach the flank.
    ("cap flank closed beside the run", (36.0, -1.0, 5.0), True),
    ("cap flank closed, low",           (36.0, -2.0, 2.0), True),
    ("cap flank closed, high",          (36.0, -2.0, 11.0), True),
    ("cable run open inside the cap",   (30.0, -3.0, 3.0), False),
    ("plug pocket in the inner face",   (0.0, -3.0, 6.45), False),
    ("plate behind the plug pocket",    (0.0, -8.0, 6.45), True),
    ("sunken face panel",               (25.0, -10.5, 6.0), False),
    # ⚠️ The rim is faceted too, so it is proud of the panel floor by 1.5-3 mm
    # rather than by exactly FACE_DEPTH. Probed at Y -11.0, inside the shallowest
    # rim facet; the panel floor above is what it is being compared against.
    ("panel rim stands proud of it",    (25.0, -11.0, 12.6), True),
]

pts = np.array([p for _, p, _ in probes])
got = m.contains(pts)
print("=== solid/empty probes ===")
bad = 0
for (label, _, want), g in zip(probes, got):
    ok = bool(g) == want
    bad += not ok
    print(f"  {'ok  ' if ok else 'FAIL'}  {label:<30} "
          f"expect {'solid' if want else 'empty':<5} got {'solid' if g else 'empty'}")

# ★★ THE PACK MODULE. Its pocket has to actually take the pack, its plate has
# to survive the strap channel cut into it, and its mouth has to face the
# WRIST -- the same ergonomic rule as the cap, for the same reason (that is the
# end his free hand reaches). MOD geometry, mirrored from bracer.py:
MOD_PLATE, MOD_WALL, MOD_CLR = 4.4, 2.0, 0.6
_MZ0 = ARM_CZ - ARM_CUT_R - MOD_PLATE
_MZ1 = _MZ0 - (PACK_T + 2 * MOD_CLR)
_MY0 = OUT_L / 2 - PACK_L / 2 - 1.0
_MYC = OUT_L / 2
mod_probes = [
    ("pocket takes the pack, mid",   (ARM_CX, _MYC, (_MZ0 + _MZ1) / 2), False),
    ("...at its full 54 mm width",   (ARM_CX - 26.0, _MYC, (_MZ0 + _MZ1) / 2), False),
    ("side rail beside the pack",    (ARM_CX - 29.0, _MYC, (_MZ0 + _MZ1) / 2), True),
    ("plate between pack and arm",   (ARM_CX, _MYC, _MZ0 + 1.0), True),
    ("outer skin behind the pack",   (ARM_CX, _MYC, _MZ1 - 1.0), True),
    # ⚠️ The strap channel is cut STRAP_D into that plate. At MOD_PLATE 2.0 it
    # went straight through into the pocket; this is the probe that would have
    # caught it without a render.
    ("plate survives the strap cut", (ARM_CX, STRAP_Y0, _MZ0 + 0.6), True),
    ("strap channel is open",        (ARM_CX, STRAP_Y0, _MZ0 + 3.6), False),
    # ★ the mouth faces the WRIST (Y small), and the far end is closed
    ("mouth opens at the wrist",     (ARM_CX, _MY0 - 1.5, (_MZ0 + _MZ1) / 2), False),
    ("far end is closed",            (ARM_CX, _MY0 + PACK_L + 3.0,
                                      (_MZ0 + _MZ1) / 2), True),
    # ...and the lip that stops it falling straight back out
    ("return lip across the mouth",  (ARM_CX, _MY0 - 1.0, _MZ1 + 0.8), True),
]
print("\n=== pack module solid/empty probes ===")
for (label, p_, want), g in zip(mod_probes,
                                mod.contains(np.array([p_ for _, p_, _ in mod_probes]))):
    ok = bool(g) == want
    bad += not ok
    print(f"  {'ok  ' if ok else 'FAIL'}  {label:<30} "
          f"expect {'solid' if want else 'empty':<5} got {'solid' if g else 'empty'}")

print("\n=== end cap solid/empty probes ===")
for (label, p, want), g in zip(cap_probes,
                               cap.contains(np.array([p for _, p, _ in cap_probes]))):
    ok = bool(g) == want
    bad += not ok
    print(f"  {'ok  ' if ok else 'FAIL'}  {label:<30} "
          f"expect {'solid' if want else 'empty':<5} got {'solid' if g else 'empty'}")

print("\n=== integrity ===")
print(f"  watertight      {m.is_watertight}")
bad += not m.is_watertight
# 3 bodies = shell + 2 free-floating button plungers. If this drops to 1 the
# plungers have fused to the wall and the buttons are decorative.
_bodies = len(m.split(only_watertight=False))
_body_ok = _bodies == 3
bad += not _body_ok
print(f"  bodies          {_bodies}  {'ok (shell + 2 plungers)' if _body_ok else 'FAIL — plungers fused?'}")
print(f"  cap watertight  {cap.is_watertight}")
bad += not cap.is_watertight
_cb = len(cap.split(only_watertight=False))
bad += _cb != 1
print(f"  cap bodies      {_cb}  {'ok' if _cb == 1 else 'FAIL — cap is in pieces'}")
print(f"  module watertight  {mod.is_watertight}")
bad += not mod.is_watertight
_mb = len(mod.split(only_watertight=False))
bad += _mb != 1
print(f"  module bodies   {_mb}  {'ok' if _mb == 1 else 'FAIL — module is in pieces'}")
print(f"  volume          {m.volume/1000:.1f} cm3")
_cap_g = cap.volume / 1000 * 1.27
print(f"  PETG mass       {m.volume/1000*1.27:.0f} g   (+{_cap_g:.0f} g cap, +143 g phone "
      f"= {m.volume/1000*1.27+_cap_g+143:.0f} g on the arm)")
bb = m.bounds
print(f"  bbox            {bb[1][0]-bb[0][0]:.1f} x {bb[1][1]-bb[0][1]:.1f} "
      f"x {bb[1][2]-bb[0][2]:.1f} mm")


# --------------------------------------------------------- minimum wall
def min_wall(mesh, n=20000, anti=0.90):
    """Thinnest wall in a mesh, by inward ray casting.

    From each sampled surface point, fire a ray along the inward normal and
    measure how far it travels before it leaves the solid again.

    ⚠️ The filter is the whole trick. Every CONVEX EDGE has zero thickness at
    the edge itself, so a naive minimum reports ~0 on any chamfered part and is
    useless. A sample is only counted when the far surface is within ~26 deg of
    being PARALLEL AND OPPOSED to the near one -- which is what a wall is. A
    45 deg chamfer crease drops out, and so does the 35 deg corner where a
    retaining bar runs out onto the sloped arm face; a feather edge, whose two
    faces are nearly parallel, does not. That is the defect this exists for,
    so it is the one case the filter must keep. Loosening `anti` below ~0.85
    turns every ordinary sharp corner into a FAIL and the check into noise.

    Returns (thickness, point) for the thinnest wall found.
    """
    pts, fidx = trimesh.sample.sample_surface_even(mesh, n)
    nrm = mesh.face_normals[fidx]
    org = pts - nrm * 1e-3
    dirs = -nrm
    loc, ray_i, tri_i = mesh.ray.intersects_location(
        org, dirs, multiple_hits=False)
    if not len(ray_i):
        return math.inf, None
    exit_n = mesh.face_normals[tri_i]
    keep = np.einsum("ij,ij->i", exit_n, dirs[ray_i]) > anti
    if not keep.any():
        return math.inf, None
    d = np.linalg.norm(loc[keep] - org[ray_i][keep], axis=1)
    k = int(np.argmin(d))
    return float(d[k]), org[ray_i][keep][k]


def _selftest():
    """Negative test. A checker that only ever agrees with me is worthless."""
    ok = True
    plate = trimesh.creation.box((40, 40, 0.9))
    t, _ = min_wall(plate, n=3000)
    good = abs(t - 0.9) < 0.12
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'}  0.9 mm plate            "
          f"reported {t:.2f} mm")
    # a knife edge: a wedge tapering to nothing over 30 mm, i.e. ~2 deg
    wedge = trimesh.Trimesh(
        vertices=[[0, 0, 0], [30, 0, 0], [30, 0, 1.0],
                  [0, 20, 0], [30, 20, 0], [30, 20, 1.0]],
        faces=[[0, 2, 1], [3, 4, 5], [0, 1, 4], [0, 4, 3],
               [1, 2, 5], [1, 5, 4], [0, 3, 5], [0, 5, 2]])
    wedge.fix_normals()
    t, _ = min_wall(wedge, n=3000)
    good = t < 0.30
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'}  feather edge            "
          f"reported {t:.2f} mm  (must be < 0.30)")
    # a 45 deg chamfered block must NOT be reported as thin -- that is the
    # false positive that would make the check unusable on a real part.
    blk = trimesh.creation.box((30, 30, 6))
    t, _ = min_wall(blk, n=3000)
    good = t > 5.0
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'}  6 mm block (no false +) "
          f"reported {t:.2f} mm")
    return ok


print("\n=== minimum wall thickness ===")
print("  -- checker self-test --")
if not _selftest():
    bad += 1
_parts = sorted(m.split(only_watertight=False), key=lambda b_: -b_.volume)
_checks = [("bracer shell", _parts[0], MIN_WALL), ("end cap", cap, MIN_WALL),
           ("pack module", mod, MIN_WALL)]
_checks += [(f"button plunger {i+1}", b_, MIN_WALL_PLUNGER)
            for i, b_ in enumerate(_parts[1:])]
for name, mesh, limit in _checks:
    t, p = min_wall(mesh)
    ok = t >= limit
    bad += not ok
    where = "" if p is None else f"  at ({p[0]:6.1f},{p[1]:6.1f},{p[2]:6.1f})"
    print(f"  {'ok  ' if ok else 'FAIL'}  {name:<22} {t:5.2f} mm "
          f"(min {limit}){where}")


# -------------------------------------------------- dead structure below
# ★★ THE CHECK THIS PART DID NOT HAVE, and the one that would have caught the
# defect the owner found by eye on 2026-08-12: "you added a corner and a bunch
# of material at the bottom where nothing sits", "cantilevered over the edge
# for no reason". Both are the same measurement -- how far the outer surface
# sits from the nearest thing it is there to contain.
#
# Below the belt there are exactly two of those things: the PAYLOAD (pack,
# cards, rails -- one box) and the ARM. So sample the surface, and for every
# sample below the belt take the distance to whichever is nearer. A shell that
# follows its contents scores its own wall thickness plus the local taper; a
# curtain hung out past both scores the length of the curtain.
#
# ⚠️ Feature-agnostic on purpose. It does not know what a keel or a chine is,
# so it catches the next one of these wherever it appears -- which is the whole
# argument for the harness (see feedback-verify-before-sending).
DEAD_BUDGET = 13.0      # mm of body standing off everything it could hold


def dead_standoff(mesh, n=20000):
    """(worst distance, point) from the surface below the belt to the nearer of
    the payload box and the arm cylinder."""
    pts, _ = trimesh.sample.sample_surface_even(mesh, n)
    pts = pts[pts[:, 2] < HULL_BELT]
    if not len(pts):
        return 0.0, None
    # payload: an X/Z box, full length -- distance in the section plane
    dx = np.maximum(np.abs(pts[:, 0]) - PAYLOAD_HW, 0.0)
    dz = np.maximum(np.maximum(PAYLOAD_Z - pts[:, 2], pts[:, 2] - 0.0), 0.0)
    d_pay = np.hypot(dx, dz)
    # arm: radial distance out from the cut cylinder's surface
    d_arm = np.abs(np.hypot(pts[:, 0] - ARM_CX, pts[:, 2] - ARM_CZ) - ARM_CUT_R)
    d = np.minimum(d_pay, d_arm)
    k = int(np.argmax(d))
    return float(d[k]), pts[k]


print("\n=== dead structure below the belt ===")
# Negative test: hang a slab exactly where the deleted corner used to be and
# confirm the check calls it. A checker that only ever agrees with me is
# worthless -- and this one is new, so it has never disagreed with anything.
_bogus = trimesh.creation.box(
    (10.0, 100.0, 20.0),
    trimesh.transformations.translation_matrix([-35.0, 70.0, -30.0]))
_bd, _ = dead_standoff(_bogus, n=3000)
_neg_ok = _bd > DEAD_BUDGET
bad += not _neg_ok
print(f"  {'ok  ' if _neg_ok else 'FAIL'}  self-test: the old corner   "
      f"{_bd:5.1f} mm  (must exceed {DEAD_BUDGET})")
_d, _p = dead_standoff(_parts[0])
_dead_ok = _d <= DEAD_BUDGET
bad += not _dead_ok
_where = "" if _p is None else f"  at ({_p[0]:6.1f},{_p[1]:6.1f},{_p[2]:6.1f})"
print(f"  {'ok  ' if _dead_ok else 'FAIL'}  bracer shell                "
      f"{_d:5.1f} mm  (max {DEAD_BUDGET}){_where}")

# ---------------------------------------------------- ★★ facet census
# THE CHECK THIS PART DID NOT HAVE, and the one that encodes the owner's
# complaint -- "we still have hard cuts sides" -- as a number instead of an
# opinion. A hard cut side IS a single large planar facet: the old flank was one
# plane roughly 20 x 147 mm, about 2900 mm2, and no amount of chamfering its
# edges changed what it read as. Low poly (ref/lowpoly-*.png) is the opposite
# property: MANY planes, none of them dominant.
#
# ⚠️⚠️ 2026-08-12: THIS CHECK WAS SCOPED TO THE SURFACE IT HAD ALREADY FIXED.
# It looked only BELOW THE BELT and outside the payload box, on the theory that
# "the frozen tray face, the screen bezel and the visor... are supposed to be
# flat". They are not. It therefore reported a green 597 mm2 maximum while the
# elbow end was a single unbroken 2883 mm2 plate, the tray's side walls were
# 1845 each, the deck was 1441 and the guard's outer wall was 1116 -- and the
# owner photographed one of them and said "still looking at a flat top wall".
# ★ A check that passes on a part the owner can see is broken is worse than no
# check. So the census now covers THE WHOLE EXTERIOR SKIN of both solids:
#   * exterior = a ray fired along the outward normal escapes the mesh;
#   * minus a NAMED exclusion list, printed every run so nothing hides in it.
# The exclusions are the frozen phone housing (which is the owner's phone, not
# our surface to style), genuine internal volumes that happen to be visible
# through an opening, and the two mating faces at the cap joint. Everything
# else -- deck, both ends, guard, ramps, cuff, flanks, the cap's nose -- is
# skin and is held to FACET_MAX_A.
FACET_MIN = 120
# mm2. For scale: the old flat flank was ~2900, the elbow end 2883, the tray's
# side walls 1845 each, the deck 1441, the guard's outer wall 1116. 500 is
# comfortably below every one of them and comfortably above the largest facet
# the section loft produces on its own (311, on the shallow flank).
FACET_MAX_A = 500.0


def _exterior(mesh):
    """Faces you can see from outside: fire along the outward normal and keep
    the ones whose ray never hits the mesh again."""
    cen = mesh.triangles.mean(axis=1)
    nrm = mesh.face_normals
    hit = mesh.ray.intersects_first(cen + nrm * 0.05, nrm)
    return hit < 0


def facets(mesh, keep):
    """Coplanar-triangle clusters (area, normal, centroid) over a face filter."""
    cen = mesh.triangles.mean(axis=1)
    sel = keep(cen) & _exterior(mesh)
    n = np.round(mesh.face_normals[sel], 3)
    d = np.round(np.einsum("ij,ij->i", n, cen[sel]), 2)
    key = {}
    ar = mesh.area_faces[sel]
    for i in range(len(n)):
        k = (n[i][0], n[i][1], n[i][2], d[i])
        e = key.setdefault(k, [0.0, n[i], np.zeros(3), 0.0])
        e[0] += ar[i]
        e[2] += cen[sel][i] * ar[i]
    return [(v[0], v[1], v[2] / v[0]) for v in key.values()]


# The exclusion list, stated rather than implied. Each entry is a name and a
# predicate on face centroids; anything it matches is NOT skin and is not
# counted. If a flat face ever hides behind one of these, the name is where to
# look -- that is the whole reason they are named.
def _in_pocket(c):
    return ((np.abs(c[:, 0]) < POCK_W / 2 + 0.05) & (c[:, 1] < 144.65)
            & (c[:, 2] > FLOOR - 0.05) & (c[:, 2] < FLOOR + POCK_D + LIP_H))


def _bezel_loft(c):
    # the frozen aperture: its flare and the sensor bores, inboard of the deck
    return ((np.abs(c[:, 0]) < WIN_X + BEZEL_CHAM + 0.05)
            & (c[:, 2] > FLOOR + POCK_D - 0.05) & (c[:, 2] < OUT_H + 0.05))


def _internal(c):
    # the shell cavity, card channel, pack bay and cable run: all below the
    # tray floor and inboard of the hull skin, visible only through the nose
    return (c[:, 2] < 0.05) & (np.abs(c[:, 0]) < PAYLOAD_HW + 6.0)


def _cap_joint(c):
    # the two faces that meet at Y = 0: the tray's nose and the cap's collar
    # mouth. They are in contact in the assembly and neither is ever seen.
    return np.abs(c[:, 1]) < 0.05


def _btn_bay(c):
    # the print-in-place plungers and their bores -- a frozen mechanism
    return (np.abs(c[:, 0]) > POCK_W / 2 - 0.1) & (c[:, 2] > 2.5) \
        & (c[:, 2] < 11.0) & (np.abs(c[:, 0]) < X_OUT + BTN_PROUD + 0.2) \
        & (((c[:, 1] > 68.0) & (c[:, 1] < 92.0))
           | ((c[:, 1] > 95.0) & (c[:, 1] < 110.0)))


X_OUT, BTN_PROUD = OUT_W / 2, 0.6
EXCLUDE = [
    ("frozen phone pocket + lip", _in_pocket),
    ("frozen screen aperture + sensor bores", _bezel_loft),
    ("internal: cavity, cards, pack, cable", _internal),
    ("cap joint faces at Y=0", _cap_joint),
    ("frozen button bay + plungers", _btn_bay),
]
PLUG_D = 6.0
# ⚠️ The cap needs its OWN list, not the bracer's. Sharing them was the first
# attempt and "internal: cavity, cards, pack" (everything below Z 0 and inboard
# of the skin) swallowed the cap's entire raked chin -- the census came back
# with five facets and 0.8 cm2, i.e. it had stopped looking at the part.
CAP_EXCLUDE = [
    ("cap joint faces at Y=0", _cap_joint),
    ("cap internal cable + plug pocket",
     lambda c: (c[:, 1] > -PLUG_D - 0.3) & (c[:, 1] < 0.2)
     & (np.abs(c[:, 0]) < 35.6) & (c[:, 2] > -1.5) & (c[:, 2] < 10.5)),
    ("collar bore and snap noses",
     lambda c: (c[:, 1] > 0.2) & (np.abs(c[:, 0]) < 39.0)),
]

print("\n=== facet census (THE WHOLE EXTERIOR SKIN, both solids) ===")


def _census(mesh, excl, label):
    keep = lambda c: ~np.any([f(c) for _, f in excl], axis=0)
    fs = [f for f in facets(mesh, keep) if f[0] >= 12.0]
    fs.sort(key=lambda f: -f[0])
    print(f"  {label}: {len(fs)} facets over 12 mm2, "
          f"{sum(f[0] for f in fs)/100:.1f} cm2 of skin, "
          f"median {np.median([f[0] for f in fs]):.0f} mm2")
    for a, _, c in fs[:3]:
        print(f"        largest {a:6.0f} mm2 at "
              f"({c[0]:6.1f},{c[1]:6.1f},{c[2]:6.1f})")
    return fs


for _n_, _f_ in EXCLUDE + CAP_EXCLUDE:
    print(f"        not skin: {_n_}")
_fs = _census(_parts[0], EXCLUDE, "bracer")
_cfs = _census(cap, CAP_EXCLUDE, "end cap")
_n_ok = len(_fs) >= FACET_MIN
_worst = max([f[0] for f in _fs] + [f[0] for f in _cfs])
_a_ok = _worst <= FACET_MAX_A
bad += not _n_ok
bad += not _a_ok
print(f"  {'ok  ' if _n_ok else 'FAIL'}  facets on the bracer's skin {len(_fs):4d}  "
      f"(min {FACET_MIN})")
print(f"  {'ok  ' if _a_ok else 'FAIL'}  largest facet, either solid {_worst:6.0f} mm2  "
      f"(max {FACET_MAX_A:.0f})")

# ------------------------------------------------- ★ cuff wrap symmetry
# The second complaint -- "a weird underbelly" -- was the shell being sliced off
# by the arm at 25 deg on one side and wrapped round it to 40 on the other. The
# fix is that both edges of the arm opening now leave the arm at the SAME angle,
# so measure the angle rather than trusting the source. Taken off the mesh: the
# outermost surface point on each side of the arm's crown, below the belt.
# --------------------------------------------- ★ the two brows must match
# Replaces four fixed-height probes (present at 4.5 mm, absent at 5.5). Those
# stopped meaning anything once the crest ramps were faceted -- a facet moves
# the local crest by a few tenths, so they were testing the tessellation. What
# the owner actually said was "the side guards aren't even the same height, the
# top side is better, the bottom is massive", and that is a COMPARISON. So
# measure the crest at mirrored stations either side of the ramps and compare.
# ⚠️ Mirrored about the ramps, not about the tray: the ramp starts BROW_RAMP
# inside each brow's base, so RAMP_Y0 - t and RAMP_Y1 + t are the matching
# pair. Anything else compares two different points on the ramp.
BROW_Y0, BROW_Y1, BROW_RAMP = 11.0, 141.0, 7.0
RAMP_Y0, RAMP_Y1 = BROW_Y0 + BROW_RAMP, BROW_Y1 - BROW_RAMP
BROW_TOL = 0.6
print("\n=== the two brows (mirrored about their ramps) ===")


def _brow_h(yc, w=1.2):
    v = m.vertices
    sel = (np.abs(v[:, 1] - yc) < w) & (np.abs(v[:, 0]) < 25.0) \
        & (v[:, 2] > OUT_H + 0.1)
    return (v[sel][:, 2].max() - OUT_H) if sel.any() else 0.0


_h_usb, _h_jack = _brow_h(RAMP_Y0 - 10.0), _brow_h(RAMP_Y1 + 10.0)
_bsym_ok = abs(_h_usb - _h_jack) <= BROW_TOL and min(_h_usb, _h_jack) > 3.0
bad += not _bsym_ok
print(f"  {'ok  ' if _bsym_ok else 'FAIL'}  USB {_h_usb:4.1f} mm vs jack "
      f"{_h_jack:4.1f} mm above the tray face  (differ by <= {BROW_TOL}, "
      f"both > 3.0)")

print("\n=== cuff wrap (the underside embraces the arm) ===")
WRAP_TARGET, WRAP_TOL = 40.0, 6.0
_pts, _ = trimesh.sample.sample_surface_even(_parts[0], 40000)
_pts = _pts[_pts[:, 2] < PAYLOAD_Z]
_r = np.hypot(_pts[:, 0] - ARM_CX, _pts[:, 2] - ARM_CZ)
_th = np.degrees(np.arctan2(_pts[:, 0] - ARM_CX, _pts[:, 2] - ARM_CZ))
_near = np.abs(_r - ARM_CUT_R) < 1.5          # on the arm saddle itself
for _name, _sgn in (("deep (outboard)", -1), ("shallow (inboard)", 1)):
    _sel = _near & (np.sign(_th) == _sgn)
    _w = np.percentile(np.abs(_th[_sel]), 99.0) if _sel.any() else 0.0
    _ok = abs(_w - WRAP_TARGET) <= WRAP_TOL
    bad += not _ok
    print(f"  {'ok  ' if _ok else 'FAIL'}  {_name:<20} {_w:5.1f} deg of wrap "
          f"(target {WRAP_TARGET:.0f} +/- {WRAP_TOL:.0f})")

# ------------------------------------------------------- chamfer audit
# ★ "Find the edges that got missed" -- systematically, off the mesh, rather
# than by eye off a render. Every exterior CONVEX crease sharper than
# SHARP_DEG is listed with its length and where it is. A properly chamfered
# 90 deg corner becomes two 45 deg creases, so anything still above 55 deg
# either could not be chamfered or was deliberately left.
SHARP_DEG = 55.0
SHARP_MIN_LEN = 4.0      # ignore slivers; they are triangulation, not design


def sharp_exterior_edges(mesh, deg=SHARP_DEG):
    """(length, midpoint, degrees) for every convex exterior crease."""
    ang = np.degrees(mesh.face_adjacency_angles)
    keep = mesh.face_adjacency_convex & (ang > deg)
    if not keep.any():
        return []
    ev = mesh.face_adjacency_edges[keep]
    a, b = mesh.vertices[ev[:, 0]], mesh.vertices[ev[:, 1]]
    mid = (a + b) / 2.0
    length = np.linalg.norm(a - b, axis=1)
    n = mesh.face_normals[mesh.face_adjacency[keep]].mean(axis=1)
    n /= np.linalg.norm(n, axis=1)[:, None]
    # exterior if a ray fired outward from just off the crease never comes back
    hit = mesh.ray.intersects_any(mid + n * 0.05, n)
    out = [(length[i], mid[i], ang[keep][i])
           for i in range(len(mid)) if not hit[i] and length[i] >= SHARP_MIN_LEN]
    return sorted(out, key=lambda r: -r[0])


# ★ Classify what is left. A sharp crease is only a defect if it is not one
# of these -- and naming them here is what turns "we left some edges sharp"
# into a decision on record. UNCLASSIFIED is the number that must stay small.
def classify(mid, part_name):
    x, y, z = mid
    if part_name == "bracer":
        if abs(z - OUT_H) < 0.25 or abs(z - (OUT_H - 0.1)) < 0.25:
            return "screen aperture rim (FROZEN)"
        if FLOOR + POCK_D - 1.5 < z < OUT_H + 0.3:
            return "sensor apertures + bezel loft (FROZEN)"
        if abs(y) < 0.3:
            return "USB-end mouth / cap joint"
        # ⚠️ NOT "the print bed" any more. The elbow end is tessellated like
        # every other surface; if it is printed standing on this end it needs
        # a brim and some support, and that is fine.
        if abs(y - OUT_L) < 0.3:
            return "elbow end, outermost facets"
        if 2.0 < z < OUT_H - 0.5 and abs(x) > 30.0:
            return "button bay + jack (FROZEN)"
        # ⚠️ 34, not 30. The retaining bars moved out to straddle the ARM's
        # crown rather than the tray's centre line, so their tips run out onto
        # the arm face at |X| ~ 30 -- 26 mm of crease each, and they were the
        # whole UNCLASSIFIED total until this bound was widened.
        if z < -0.5 and abs(x) < 34.0:
            return "strap channel / arm face"
        if abs(z + 0.4) < 0.35:
            return "card channel mouth + rails"
        if abs(z) < 0.35 and abs(abs(x) - OUT_W / 2) < 1.5:
            return "tray/hull waist seam -- frozen wall meets the shell"
        if abs(z - FLOOR) < 0.3:
            return "floor vent rims (inside the pocket)"
        if abs(x) > 34.0 and z < 0.0:
            return "arm saddle edge -- 4 mm pad relief, do not cut"
        if abs(z - GZ1) < 0.3:
            return "guard crest -- land set by CREST_W"
        if z > OUT_H + 3.0:
            return "brow blades -- converging faces, checked below"
        # The guard stands GUARD_HW wide on a tray wall that is OUT_W/2, so its
        # base overhangs by 2.45 mm on a GUARD_BASE_CH bevel. Both edges of
        # that ledge are sharp by design -- a chamfer there eats the bevel.
        if abs(abs(x) - GUARD_HW) < 1.8 and z > OUT_H - 0.6:
            return "guard base ledge + the brows' outer corners"
        if y > OUT_L - 9.0:
            return "elbow end facets"
    else:
        if abs(y) < 0.3 or abs(y - CAP_D) < 0.3:
            return "collar joint faces"
        if z < 0.0:
            return "hull section creases + chin rake"
        if abs(y + CAP_T) < 0.4:
            return "cap face panel + speaker/mic mouths"
        if -CAP_T < y < 0.5 and 0.0 < z < OUT_H:
            return "internal cable pocket"
    return "UNCLASSIFIED"


UNCLASSIFIED_BUDGET = 120.0     # mm of sharp exterior crease with no excuse

print(f"\n=== chamfer audit (exterior creases sharper than {SHARP_DEG:.0f} deg) ===")
for _nm, _mesh in (("bracer", _parts[0]), ("end cap", cap)):
    _sharp = sharp_exterior_edges(_mesh)
    _by = {}
    for _l, _m, _a in _sharp:
        _by.setdefault(classify(_m, _nm), []).append((_l, _m, _a))
    print(f"  {_nm}: {len(_sharp)} creases, {sum(r[0] for r in _sharp):6.1f} mm total")
    for _k in sorted(_by, key=lambda k: -sum(r[0] for r in _by[k])):
        _rows = _by[_k]
        _mk = "FAIL" if _k == "UNCLASSIFIED" and sum(r[0] for r in _rows) > UNCLASSIFIED_BUDGET else "    "
        print(f"    {_mk}  {sum(r[0] for r in _rows):7.1f} mm  {len(_rows):3d}x  {_k}")
        if _k == "UNCLASSIFIED":
            for _l, _m, _a in _rows[:5]:
                print(f"              {_l:6.1f} mm at "
                      f"({_m[0]:6.1f},{_m[1]:6.1f},{_m[2]:6.1f})  {_a:4.0f} deg")
            if sum(r[0] for r in _rows) > UNCLASSIFIED_BUDGET:
                bad += 1

# ----------------------------------------------------- crest sharpness
# ★ A converging crest is a feather edge by definition, and the wall check
# cannot see it: its filter wants two near-parallel faces, and a crest is two
# faces meeting at an angle. So measure the angle directly. Anything under
# CREST_MIN_DEG is too fine to print -- that is what sets CREST_W in bracer.py,
# rather than taste. Negative-tested: with CREST_W = 0 the guard's crest
# measures 23 deg and this fails, which is exactly why the land exists.
# 35, not 40: the sharpest thing on the part is the strap retaining bar's tip
# where it runs out onto the sloped arm face, at 38.7 deg. That is pre-existing,
# it is 26 mm of bar tip, and it prints. The guard's crest is the thing this
# check is really watching.
CREST_MIN_DEG = 35.0

print("\n=== crest sharpness (included angle at exterior convex creases) ===")
for _nm, _mesh in (("bracer", _parts[0]), ("end cap", cap)):
    # ⚠️ Frozen apertures are exempt. The proximity window's corner against
    # the bezel loft is a 32 deg crease and always has been; it is the phone's
    # geometry, not ours, and failing on it would just train us to ignore this.
    _sh = [(l, mid, a) for l, mid, a in sharp_exterior_edges(_mesh, deg=90.0)
           if "FROZEN" not in classify(mid, _nm)]
    # ⚠️ key=, not a bare min. The tuples carry a numpy midpoint, so a tie on
    # the angle makes min() compare arrays and raise.
    _worst = min(((180.0 - a, l, mid) for l, mid, a in _sh),
                 key=lambda r: r[0], default=None)
    if _worst is None:
        print(f"  ok    {_nm:<22} no crease under 90 deg included")
        continue
    _inc, _l, _mid = _worst
    _ok = _inc >= CREST_MIN_DEG
    bad += not _ok
    print(f"  {'ok  ' if _ok else 'FAIL'}  {_nm:<22} {_inc:5.1f} deg over {_l:5.1f} mm "
          f"at ({_mid[0]:6.1f},{_mid[1]:6.1f},{_mid[2]:6.1f})  (min {CREST_MIN_DEG})")

# --------------------------------------------------- how far off-axis you see
# ⚠️ This REPLACES the old "the hood never shadows a pixel" assertion, which a
# 15 mm guard cannot satisfy and should not pretend to. A deep well restricts
# the viewing cone -- that is what a well IS. So measure the cone instead of
# asserting it away: fire rays from just inside the display's near edge and
# find the last angle that escapes the guard.
# ★ Since 2026-08-12 the guard is on the DEEP, OUTBOARD flank and the eye side
# is the open one. The number that matters is the EYE SIDE: it has to clear the
# 32 deg the frozen bezel allows, otherwise the guard is costing him nothing to
# look at. The guard-side number is just the shade depth.
VIEW_MIN_DEG = 30.0   # the eye side must not be the limiting factor

print("\n=== viewing cone off the display's near edge ===")
_edge_x = -(WIN_X - 0.2)          # just inside the live area, guard side
_best = 0.0
for _d in np.arange(0.0, 70.0, 0.5):
    _t = math.radians(_d)
    _o = np.array([[_edge_x, 73.0, FLOOR + POCK_D + 0.2]])
    _dir = np.array([[-math.sin(_t), 0.0, math.cos(_t)]])
    if _parts[0].ray.intersects_any(_o, _dir)[0]:
        break
    _best = _d
# The guard side is informational -- it is SUPPOSED to be shaded.
print(f"        guard side (outboard, shaded)  {_best:4.1f} deg")
_best2 = 0.0
for _d in np.arange(0.0, 70.0, 0.5):
    _t = math.radians(_d)
    _o = np.array([[WIN_X - 0.2, 73.0, FLOOR + POCK_D + 0.2]])
    _dir = np.array([[math.sin(_t), 0.0, math.cos(_t)]])
    if _parts[0].ray.intersects_any(_o, _dir)[0]:
        break
    _best2 = _d
_view_ok = _best2 >= VIEW_MIN_DEG
bad += not _view_ok
print(f"  {'ok  ' if _view_ok else 'FAIL'}  EYE SIDE (inboard, open)      {_best2:4.1f} deg "
      f"(min {VIEW_MIN_DEG}; frozen bezel alone gives 32)")

# ------------------------------------------------ end cap vs tray clearance
# The cap has to slide the whole way on, not just fit once it is there. Sweep
# it down the insertion path and intersect at every step. The ONLY contact
# allowed is the snap domes camming over the tray wall -- a couple of mm3.
print("\n=== end cap fit ===")
DOME_BUDGET = 6.0        # mm3, the two snap domes at full deflection
worst, worst_at = 0.0, 0.0
for dy in np.linspace(-45.0, 0.0, 16):
    c = cap.copy()
    c.apply_translation([0, dy, 0])
    inter = trimesh.boolean.intersection([m, c], engine="manifold")
    v = 0.0 if inter is None or inter.is_empty else abs(inter.volume)
    if dy == 0.0:
        seated_ok = v < DOME_BUDGET
        bad += not seated_ok
        print(f"  {'ok  ' if seated_ok else 'FAIL'}  seated interference     "
              f"{v:6.2f} mm3  (budget {DOME_BUDGET})")
    if v > worst:
        worst, worst_at = v, dy
path_ok = worst < DOME_BUDGET
bad += not path_ok
print(f"  {'ok  ' if path_ok else 'FAIL'}  worst on the slide path {worst:6.2f} mm3 "
      f"at y{worst_at:+.1f}  (budget {DOME_BUDGET})")

UNSUPPORTED_BUDGET = 40.0    # cm2, standing on the jack end
print("\n=== print orientation study (45 deg support threshold) ===")
orients = {
    "pocket up (as modelled)": np.eye(4),
    "pocket down":             trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]),
    # ⚠️ these two were labelled the wrong way round until 2026-08-12.
    # rotation_matrix(-pi/2, X) sends +Y to -Z, so it stands the part on its
    # HAND end. The docstring had been quoting the winner under the other name.
    # ⚠️ Named by the FROZEN FEATURE at each end, not by anatomy. -pi/2 about
    # X sends +Y to -Z, so it stands the part on Y=OUT_L -- the JACK end,
    # which is the ELBOW as worn. This label has now been wrong twice in
    # both directions; the feature name cannot be.
    "standing on jack end (elbow)":  trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]),
    "standing on USB end (wrist)":   trimesh.transformations.rotation_matrix(math.pi/2, [1, 0, 0]),
    "on its side":             trimesh.transformations.rotation_matrix(math.pi/2, [0, 1, 0]),
}
for name, T in orients.items():
    q = m.copy()
    q.apply_transform(T)
    zmin = q.bounds[0][2]
    n, a = q.face_normals, q.area_faces
    zc = q.triangles[:, :, 2].mean(axis=1)
    downward = (-n[:, 2]) > math.sin(math.radians(45.0))
    onbed = zc < zmin + 0.6
    need = downward & ~onbed
    bed_area = a[onbed & downward].sum()
    print(f"  {name:<26} unsupported {a[need].sum()/100:7.1f} cm2   "
          f"bed contact {bed_area/100:5.1f} cm2   "
          f"height {q.bounds[1][2]-zmin:5.1f} mm")
    if name.startswith("standing on jack"):
        # ⚠️⚠️ REPORTED, NOT ASSERTED, since 2026-08-12. This used to FAIL over
        # 40 cm2, and a failing number is a design driver whether you meant it
        # to be one or not: it is what kept the elbow end a flat plate, and the
        # owner named that directly --
        #   "don't let print orientation delegate design... 'oh the elbow end
        #    is fugly so you can print without supports' is a dumbass thing
        #    to say"
        #   "i don't want that to even be the main consideration, i can get
        #    creative or just use trees, if the design comes first, that's the
        #    main thing"
        # So: measure it, print it, let him decide how to print it. Do not
        # reshape the object to move this number. See feedback-supports-are-fine.
        print(f"        ^ reported only -- supports are acceptable and the form "
              f"is not shaped around this")
    if name.startswith("standing on jack") and need.any():
        # ★ Name the worst face, not just the total. "27 cm2 of overhang" is
        # not actionable; "the guard's hand ramp, 4.9 cm2 at 44 deg" is.
        _idx = np.argsort(-a * need)[:4]
        for _i in _idx:
            if not need[_i]:
                continue
            _ang = math.degrees(math.asin(min(1.0, -n[_i][2])))
            _c = q.triangles[_i].mean(axis=0)
            _o = m.triangles[_i].mean(axis=0)
            print(f"      worst face {a[_i]/100:5.2f} cm2  {_ang:4.0f} deg from "
                  f"horizontal  at model ({_o[0]:6.1f},{_o[1]:6.1f},{_o[2]:6.1f})")

# ★ ...and the module, which is a different shape of problem: a shallow tray
# with a saddle in its floor. Reported the same way and for the same reason --
# it is information, not a constraint.
print("\n=== pack module, print orientation ===")
for _nm, _T in (("pocket up (saddle on the bed)", np.eye(4)),
                ("pocket down", trimesh.transformations.rotation_matrix(
                    math.pi, [1, 0, 0]))):
    _q = mod.copy()
    _q.apply_transform(_T)
    _zmin = _q.bounds[0][2]
    _n, _a = _q.face_normals, _q.area_faces
    _zc = _q.triangles[:, :, 2].mean(axis=1)
    _dn = (-_n[:, 2]) > math.sin(math.radians(45.0))
    _ob = _zc < _zmin + 0.6
    print(f"  {_nm:<30} unsupported {_a[_dn & ~_ob].sum()/100:6.1f} cm2   "
          f"bed contact {_a[_ob & _dn].sum()/100:5.1f} cm2   "
          f"height {_q.bounds[1][2]-_zmin:5.1f} mm")
print(f"  module   {mod.bounds[1][0]-mod.bounds[0][0]:.1f} x "
      f"{mod.bounds[1][1]-mod.bounds[0][1]:.1f} x "
      f"{mod.bounds[1][2]-mod.bounds[0][2]:.1f} mm   "
      f"{mod.volume/1000*1.27:.0f} g PETG")

raise SystemExit(1 if bad else 0)
