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
HULL_HW, TEN_D, HULL_BELT = 40.0, 2.3, -3.0
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
CAP_D = 10.0

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
    ("elbow end open for insertion", (0, 1.0, FLOOR + 4), False),
    ("no hull above the belt line",  (39.0, 60.0, 6.0), False),

    # ------------------------------------------------------------ outer hull
    # ⚠️ Depths are asymmetric: TILT drops the +X side, so the same feature
    # sits at very different Z on each side. Probed, not assumed.
    ("hull skin, deep flank",        (39.0, 60.0, -10.0), True),
    ("outside the deep flank",       (42.0, 60.0, -10.0), False),
    ("hull cavity, deep side",       (34.0, 60.0, -12.0), False),
    ("hull cavity, over the arm",    (0.0, 60.0, -3.0), False),
    ("arm-face skin under cavity",   (0.0, 60.0, -6.5), True),
    ("arm void below the skin",      (0.0, 60.0, -9.5), False),
    ("cavity open at the nose",      (0.0, 14.0, -4.0), False),

    # ------------------------------------------------------- cap tenon
    # The nose steps IN by TEN_D below the belt so the cap's collar lands
    # flush. If the step is missing the cap stands proud again; if it is too
    # deep the collar rattles. Probed either side of the tenon's flank face.
    ("tenon flank, deep side",       (37.2, 3.0, -8.0), True),
    ("collar space outside tenon",   (39.0, 3.0, -8.0), False),
    ("snap dimple in tenon flank",   (37.4, 7.0, -8.84), False),
    ("full section above the belt",  (39.0, 3.0, -1.0), True),

    # ------------------------------------------------------- card slots
    ("card channel, mid",            (0.0, 40.0, -1.0), False),
    ("card channel at the nose",     (0.0, 2.0, -1.0), False),
    ("card rail web, deep side",     (29.5, 40.0, -1.0), True),
    ("card rail web, shallow side",  (-29.5, 40.0, -1.0), True),
    ("card back stop",               (0.0, 87.5, -1.0), True),
    ("floor above the card channel", (0.0, 40.0, 1.0), True),
    ("thick arm band under strap",   (0.0, 34.0, -4.0), True),
    ("exhaust louvre is open",       (39.0, 56.0, -8.8), False),
    ("flank between two louvres",    (39.0, 61.0, -8.8), True),
    # Strap runs in a channel under the hull instead of through side flanges,
    # so the device is tray-width. The bars bridge that channel.
    ("strap channel is open, +X",    (14.0, 34, -13.7), False),
    ("retaining bar fills it, +X",   (20.0, 34, -18.8), True),
    ("strap channel is open, -X",    (-14.0, 34, -4.2), False),
    ("retaining bar fills it, -X",   (-20.0, 34, -4.4), True),
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
    "standing on hand end":    trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]),
    "standing on elbow end":   trimesh.transformations.rotation_matrix(math.pi/2, [1, 0, 0]),
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

raise SystemExit(1 if bad else 0)
