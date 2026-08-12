"""
Numeric verification for the bracer. Per cad-tooling: never trust a render to
prove geometry -- probe it with trimesh.contains().

Three passes:
  1. solid/empty probes at points that discriminate every feature
  2. mesh integrity + mass
  3. print-orientation study: measured unsupported-face area per orientation,
     rather than guessing which way up it should go
"""
import numpy as np
import trimesh
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
m = trimesh.load(os.path.join(HERE, "out", "bracer.stl"))
m.fix_normals()

# geometry constants, mirrored from bracer.py
FLOOR, POCK_D, LIP_H = 2.2, 8.8, 2.4
OUT_W, OUT_L, OUT_H = 75.1, 147.0, 13.4
POCK_W, WING_T = 70.3, 4.0
GAP, SAG = 4.0, 15.05
WING_X0 = OUT_W / 2

Z_FACE = FLOOR + POCK_D          # phone front face
probes = [
    # (label, point, expect_solid)
    ("phone pocket interior",        (0, 70, FLOOR + 4), False),
    ("tray floor under phone",       (0, 34, 1.0), True),
    ("pocket wall, left",            (-36.3, 70, FLOOR + 4), True),
    # The plungers fill their bores, so these read SOLID. That they are not
    # fused to the wall is asserted by the body count below, not by a probe --
    # the running clearance is 0.35 mm and probing a gap that thin is a
    # coin toss, which is worse than no test at all.
    ("volume plunger in its bore",   (36.3, 80.0, FLOOR + 4), True),
    ("power plunger in its bore",    (36.3, 102.0, FLOOR + 4), True),
    ("cap snap dimple, right wall",  (37.3, 6.5, OUT_H / 2), False),
    ("wall between the two buttons", (36.3, 94.0, FLOOR + 4), True),
    ("wall below volume opening",    (36.3, 60.0, FLOOR + 4), True),
    ("floor vent",                   (0, 73, 1.0), False),
    ("rib material at centre",       (0, 34, -2.0), True),
    ("arm void under rib",           (0, 34, -8.0), False),
    ("open span between ribs",       (0, 73, -2.0), False),
    ("strap slot",                   (WING_X0 + 4.0, 34, 2.0), False),
    ("wing beside strap slot",       (WING_X0 + 0.9, 34, 2.0), True),
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
    ("hand-end wall",                (25.0, 145.8, FLOOR + 4), True),
    ("headphone jack notch",         (0, 145.8, FLOOR + 4), False),
    ("elbow end open for insertion", (0, 1.0, FLOOR + 4), False),
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
# 3 bodies = shell + 2 free-floating button plungers. If this drops to 1 the
# plungers have fused to the wall and the buttons are decorative.
_bodies = len(m.split(only_watertight=False))
_body_ok = _bodies == 3
bad += not _body_ok
print(f"  bodies          {_bodies}  {'ok (shell + 2 plungers)' if _body_ok else 'FAIL — plungers fused?'}")
print(f"  volume          {m.volume/1000:.1f} cm3")
print(f"  PETG mass       {m.volume/1000*1.27:.0f} g   (+143 g phone "
      f"= {m.volume/1000*1.27+143:.0f} g on the arm)")
bb = m.bounds
print(f"  bbox            {bb[1][0]-bb[0][0]:.1f} x {bb[1][1]-bb[0][1]:.1f} "
      f"x {bb[1][2]-bb[0][2]:.1f} mm")

print("\n=== print orientation study (45 deg support threshold) ===")
orients = {
    "pocket up (as modelled)": np.eye(4),
    "pocket down":             trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]),
    "standing on elbow end":   trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]),
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
