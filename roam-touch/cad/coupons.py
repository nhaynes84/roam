#!/usr/bin/env python
"""Test coupons — one printable pair per joint, cut straight out of roam_worn.step.

★ The point is to print ~20 minutes of plastic and find every interference number by hand
  before committing to a 16-hour build. Each coupon is the REAL geometry, extracted, not a
  re-model — so what you feel is what the assembly will do.

    ~/Projects/synth-case/.venv/bin/python coupons.py   ->  ~/Collab/CAD/roam-touch/roam_coupons.step/.stl
"""
import os
from build123d import *

SHARE = os.path.expanduser("~/Collab/CAD/roam-touch")
SRC = os.path.join(SHARE, "roam_worn.step")
# face plate open -> shut, and cap parked -> seated, so the joints line up
SHUT = Pos(33.99, 0, 9.64) * Rot(0, -30, 0) * Pos(15.05, 0, -18.29)
SEAT = Pos(0, 100.0, 0)
GAP, PITCH_X, PITCH_Y = 6.0, 70.0, 60.0


def box(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def main():
    S = sorted(import_step(SRC).solids(), key=lambda s: -s.volume)
    housing = S[0]
    base = [s for s in S if 30000 < s.volume < 60000 and s.bounding_box().max.Z < 10][0]
    cap = SEAT * [s for s in S if s.bounding_box().min.Y < -380][0]
    face = SHUT * [s for s in S if s.bounding_box().max.Z > 60][0]
    drawer = [s for s in S if 5000 < s.volume < 8000][0]

    JOINTS = [
        ("1 faceplate SB pin",  housing, face,   box(18, 46, -300, -276, -2, 20)),
        ("2 faceplate PORT pin", housing, face,  box(-42, -12, -300, -276, 8, 32)),
        ("3 base SB detent",    housing, base,   box(29, 47, -290, -270, -15, 1)),
        ("4 base PORT detent",  housing, base,   box(-43, -27, -290, -270, -2, 14)),
        ("5 cap tube collet",   housing, cap,    box(-70, -31, -300, -284, -5, 18)),
        ("6 cap SB clip",       housing, cap,    box(33, 49, -304, -288, -21, 1)),
        ("7 drawer detent",     housing, drawer, box(22, 42, -216, -186, -14, 4)),
        ("8 strap slot gauge",  base,    None,   box(12, 32, -292, -256, -32, -14)),
        ("9 card mouth gauge",  drawer,  None,   box(-40, 28, -301, -288, -11, 3)),
    ]
    parts, report = [], []
    for i, (name, A, B, bx) in enumerate(JOINTS):
        gx, gy = (i % 3) * PITCH_X, (i // 3) * PITCH_Y
        pieces = []
        for src, tag in ((A, "A"), (B, "B")):
            if src is None:
                continue
            p = src & bx
            if p is None or p.volume < 20:
                report.append(f"  {name:22s} {tag}: EMPTY")
                continue
            pieces.append((p, tag, p.volume))
        for j, (p, tag, vol) in enumerate(pieces):
            b = p.bounding_box()
            p = Pos(gx - (b.min.X + b.max.X) / 2,
                    gy - (b.min.Y + b.max.Y) / 2 + j * (GAP + (b.max.Y - b.min.Y)),
                    -b.min.Z) * p
            parts.append(p)
        v = " + ".join(f"{tag} {vol/1000:.2f}cm3" for _, tag, vol in pieces)
        # ★ the joint must actually be represented: A and B have to interfere IN PLACE by the
        #   detent amount. Zero means the coupon caught a blank slab and tests nothing.
        fit = ""
        if B is not None:
            ai, bi = (A & bx), (B & bx)
            if ai is not None and bi is not None:
                cl = ai & bi
                fit = f"   in-place interference {0.0 if cl is None else cl.volume:6.2f} mm3"
        report.append(f"  {name:22s} {len(pieces)} piece(s)   {v}{fit}")
    print("COUPONS")
    for r in report:
        print(r)
    out = Compound(children=parts)
    bb = out.bounding_box()
    print(f"\nplate {bb.max.X-bb.min.X:.0f} x {bb.max.Y-bb.min.Y:.0f} mm, "
          f"{out.volume/1000:.1f} cm3 (~{out.volume*1.27/1000:.0f} g), {len(out.solids())} solids")
    export_step(out, os.path.join(SHARE, "roam_coupons.step"))
    export_stl(out, os.path.join(SHARE, "roam_coupons.stl"))
    print("wrote roam_coupons.step + .stl")


if __name__ == "__main__":
    main()
