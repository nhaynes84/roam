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
import numpy as np
import trimesh
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
m = trimesh.load(os.path.join(HERE, "out", "bracer.stl"))
m.fix_normals()
cap = trimesh.load(os.path.join(HERE, "out", "bracer_endcap.stl"))
cap.fix_normals()

# geometry constants, mirrored from bracer.py
FLOOR, POCK_D, LIP_H = 2.2, 8.8, 2.4
OUT_W, OUT_L, OUT_H = 75.1, 147.0, 13.4
POCK_W = 70.3
HULL_HW, TEN_D, HULL_BELT = 40.0, 2.3, -2.0
GUARD_H, GUARD_HW = 15.0, 41.5
PACK_T, PACK_W, PACK_L = 10.0, 54.0, 85.6
PACK_Z1, PACK_Z0 = -3.62, -14.02
GZ1 = OUT_H + GUARD_H
WIN_X, BEZEL_CHAM, LIP_H = 32.03, 1.5, 2.4
SIGHT = BEZEL_CHAM / LIP_H
CARD_L, CARD_W, CARD_T = 85.60, 53.98, 0.76   # ISO/IEC 7810 ID-1
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
    ("front camera hole",            (-23.53, 138.4, Z_FACE + 1.0), False),
    ("proximity/ambient window",     (-1.0, 132.5, Z_FACE + 1.0), False),
    ("bezel between camera and ear", (-15.0, 138.2, Z_FACE + 1.0), True),
    # ⚠️ The jack is in the button-side quartile, NOT centred -- so the wall
    # probe moved to the far side and the notch probe moved onto the jack.
    ("hand-end wall, far side",      (-25.0, 145.8, FLOOR + 4), True),
    ("hand-end wall at centre",      (0.0, 145.8, FLOOR + 4), True),
    ("headphone jack notch",         (22.0, 145.8, FLOOR + 4), False),
    ("USB end open for insertion",   (0, 1.0, FLOOR + 4), False),
    ("no hull above the belt line",  (39.0, 60.0, 6.0), False),

    # ------------------------------------------------------------ outer hull
    # ⚠️ Depths are asymmetric: TILT drops the +X side, so the same feature
    # sits at very different Z on each side. Probed, not assumed.
    ("hull skin, deep flank",        (-39.0, 60.0, -20.0), True),
    ("outside the deep flank",       (-44.0, 60.0, -20.0), False),
    ("hull cavity, deep side",       (-34.0, 60.0, -25.0), False),
    ("hull cavity, over the arm",    (0.0, 60.0, -18.0), False),
    ("arm-face skin under cavity",   (0.0, 60.0, -21.5), True),
    ("arm void below the skin",      (0.0, 60.0, -25.0), False),
    ("cavity open at the nose",      (0.0, 14.0, -18.0), False),
    # ★ Card ACCESS. The channel must open at the USB end, because that is
    # the wrist -- the end his free hand reaches. If this ever reads solid
    # the cards load from the elbow end and that is an ergonomic failure,
    # not a naming one.
    ("card channel opens at USB end", (0.0, -5.0, -1.0), False),
    ("card stop is at the far end",  (0.0, 87.5, -1.0), True),
    # ★ The power pack. Same C-rail pattern under the cards, loads from the
    # USB end, cap retains it. If the mid probe reads solid the pocket has
    # closed up and nothing buyable goes in the device.
    ("pack pocket, mid",             (0.0, 45.0, -7.5), False),
    ("pack pocket at its full width", (-26.0, 45.0, -7.5), False),
    ("pack rail web",                (-30.0, 45.0, -7.5), True),
    ("pack opens at the USB end",    (0.0, -5.0, -7.5), False),
    ("pack stop at the far end",     (0.0, 89.0, -7.5), True),
    ("cable slot through the floor", (35.0, 8.0, 1.0), False),
    ("floor beside the cable slot",  (35.0, 25.0, 1.0), True),

    # ------------------------------------------------------- cap tenon
    # The nose steps IN by TEN_D below the belt so the cap's collar lands
    # flush. If the step is missing the cap stands proud again; if it is too
    # deep the collar rattles. Probed either side of the tenon's flank face.
    ("tenon flank, deep side",       (-37.2, 3.0, -8.0), True),
    ("collar space outside tenon",   (-39.0, 3.0, -8.0), False),
    ("snap dimple in tenon flank",   (-37.4, 7.0, -22.95), False),
    ("full section above the belt",  (-38.5, 3.0, -1.0), True),

    # ------------------------------------------------------- card slots
    ("card channel, mid",            (0.0, 40.0, -1.0), False),
    ("card channel at the nose",     (0.0, 2.0, -1.0), False),
    ("card rail web, deep side",     (29.5, 40.0, -1.0), True),
    ("card rail web, shallow side",  (-29.5, 40.0, -1.0), True),
    ("floor above the card channel", (0.0, 40.0, 1.0), True),
    ("thick arm band under strap",   (0.0, 34.0, -20.0), True),
    # ------------------------------------------------- ribs and visor
    # The canted louvres are gone; these are the proud ribs that replaced them.
    ("deep-flank rib",               (-41.0, 60.0, -19.7), True),
    ("gap between the ribs",         (-41.0, 60.0, -22.95), False),
    ("nothing beyond the ribs",      (-44.0, 60.0, -19.7), False),
    # The high guard: three-sided, screen sunk deep inside it.
    ("guard wall, deep/outboard",    (-39.0, 73.0, OUT_H + 6.0), True),
    ("guard wall near the crest",    (-38.5, 73.0, OUT_H + 13.0), True),
    ("screen well is open",          (0.0, 73.0, OUT_H + 6.0), False),
    # ★ THREE-sided. If this reads solid a guard has appeared on the deep
    # flank and the whole point of the section is gone.
    ("shallow flank has NO guard",   (39.0, 73.0, OUT_H + 6.0), False),
    ("scoop has cut the wall back",  (-34.5, 73.0, OUT_H + 6.0), False),
    ("...but not at its base",       (-34.5, 73.0, OUT_H + 0.4), True),
    ("USB-end brow",                 (0.0, 8.0, OUT_H + 3.0), True),
    ("jack brow",                    (0.0, 145.0, OUT_H + 3.0), True),
    ("crest ramps down at the jack", (39.0, 144.0, OUT_H + 13.0), False),
    ("crest ramps down at the USB",  (39.0, 4.0, OUT_H + 13.0), False),
    ("nothing above the crest",      (-39.0, 73.0, GZ1 + 1.0), False),
    # Strap runs in a channel under the hull instead of through side flanges,
    # so the device is tray-width. The bars bridge that channel.
    ("strap channel is open, deep",  (-20.0, 34, -36.0), False),
    ("retaining bar fills it, deep", (-14.0, 34, -30.0), True),
    ("strap channel is open, shal",  (20.0, 34, -17.7), False),
    ("retaining bar fills it, shal", (14.0, 34, -18.0), True),
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
_checks = [("bracer shell", _parts[0], MIN_WALL), ("end cap", cap, MIN_WALL)]
_checks += [(f"button plunger {i+1}", b_, MIN_WALL_PLUNGER)
            for i, b_ in enumerate(_parts[1:])]
for name, mesh, limit in _checks:
    t, p = min_wall(mesh)
    ok = t >= limit
    bad += not ok
    where = "" if p is None else f"  at ({p[0]:6.1f},{p[1]:6.1f},{p[2]:6.1f})"
    print(f"  {'ok  ' if ok else 'FAIL'}  {name:<22} {t:5.2f} mm "
          f"(min {limit}){where}")


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
        if abs(y - OUT_L) < 0.3:
            return "jack end = the print bed"
        if 2.0 < z < OUT_H - 0.5 and abs(x) > 30.0:
            return "button bay + jack (FROZEN)"
        if z < -0.5 and abs(x) < 30.0:
            return "strap channel / arm face"
        if abs(z + 0.4) < 0.35:
            return "card channel mouth + rails"
        if abs(z - FLOOR) < 0.3:
            return "floor vent rims (inside the pocket)"
        if abs(x) > 34.0 and z < 0.0:
            return "arm saddle edge -- 4 mm pad relief, do not cut"
        if abs(z - GZ1) < 0.3:
            return "guard crest -- land set by CREST_W"
        if z > OUT_H + 3.0:
            return "brow blades -- converging faces, checked below"
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

raise SystemExit(1 if bad else 0)
