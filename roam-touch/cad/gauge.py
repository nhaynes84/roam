#!/usr/bin/env python
"""Base-plate soft-lock GAUGE — the real joint at five interferences, one print.

He printed coupon 3 at 0.30 and called the soft locks "just too tight" (2026-08-21).
Rather than guess a number and have him print twice, this sweeps the ONE constant that
sets the fit and emboss-labels each pair, so a single ~20 minute print settles it.

    interference = RIDGE_TIP - BLOCK_FACE(36.85)

Each variant is a FULL rebuild of finish.py at that RIDGE_TIP, then the real coupon-3
region is sliced out of it — same principle as coupons.py: what he feels is what the
assembly will do. The variants live in the scratchpad; roam_worn.step is never touched.

  1. build the variants (14s each):
       for t in 10:36.95 15:37.00 20:37.05 25:37.10 30:37.15; do ...
       env ROAM_RIDGE_TIP=$v ROAM_OUT=$SCRATCH/t$n python finish.py
  2. ~/Projects/synth-case/.venv/bin/python gauge.py
       -> ~/Collab/CAD/roam-touch/roam_gauge.step / .stl

★ 30 is the CONTROL — it is exactly what he already printed and rejected. It is there so
  the four candidates are judged against a known feel, not against memory.
"""
import os
from build123d import *

SHARE = os.path.expanduser("~/Collab/CAD/roam-touch")
VARDIR = os.path.expanduser(
    "/private/tmp/claude-501/-Users-talos/cb44b3e0-b67c-4a38-ae46-6ce62ced7d9c/scratchpad/gauge")

# (label, interference) — label is hundredths of a mm, big enough to read on the print
VARIANTS = ((10, 0.10), (15, 0.15), (20, 0.20), (25, 0.25), (30, 0.30))

# the coupon-3 region, verbatim from coupons.py — "3 base SB detent"
BOX = (29, 47, -290, -270, -15, 1)
PITCH_X, GAP = 44.0, 6.0

TEXT_H, TEXT_PROUD = 6.0, 0.8
# tab fused to the bottom slab: wide enough for two digits, laps 3.0 into the block
TAB_W, TAB_D, TAB_T, TAB_LAP = 13.0, 18.0, 2.0, 3.0


def box(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def emboss(piece, txt):
    """Fuse a flat labelled tab to the block's BOTTOM slab.

    ⚠️⚠️ The obvious place — the block's top face — is a TRAP. The bounding box is 18 mm
      wide but the material at the top is a 2.45 mm FIN (measured x 35.86..38.31); a 7 mm
      label centred on the bbox is almost entirely unsupported and prints as spaghetti.
      ★ `+` still fuses it into one solid with positive dV, so the single-solid assert does
      NOT catch this. Bounding boxes are not faces — section the solid and look.
    ★ The bottom slab is the broad part (9.66 mm wide over the full 20 mm of y, constant
      from z -15 up to -8), and after placement it is the BED face, so a tab there prints
      flat and fully supported with the digits facing up.
    """
    b = piece.bounding_box()
    tab = Pos(b.min.X + TAB_W / 2 - TAB_LAP, b.center().Y, TAB_T / 2) * \
        Box(TAB_W, TAB_D, TAB_T)
    sk = Pos(b.min.X + TAB_W / 2 - TAB_LAP, b.center().Y, TAB_T) * \
        Text(str(txt), font_size=TEXT_H)
    lab = extrude(sk, TEXT_PROUD)
    out = piece + tab + lab
    n = len(out.solids())
    d = out.volume - piece.volume
    print(f"    label {txt:<3} +{d:7.2f} mm3  solids {n}", end="")
    if n != 1 or d < 100.0:
        print("   FAIL — label did not fuse")
        raise SystemExit(f"label {txt} floated off (solids {n}, dV {d:.2f})")
    print("   OK")
    return out


def main():
    parts, report = [], []
    for i, (lab, inter) in enumerate(VARIANTS):
        src = os.path.join(VARDIR, f"t{lab}", "roam_worn.step")
        if not os.path.exists(src):
            raise SystemExit(f"missing variant build: {src}")
        S = sorted(import_step(src).solids(), key=lambda s: -s.volume)
        housing = S[0]
        base = [s for s in S if 30000 < s.volume < 60000
                and s.bounding_box().max.Z < 10][0]

        print(f"  {lab}  interference {inter:.2f}")
        pieces = []
        for solid, tag in ((housing, "block"), (base, "plate")):
            p = solid & box(*BOX)
            if p is None or p.volume < 20:
                raise SystemExit(f"variant {lab} {tag}: EMPTY slice")
            # ⚠️ The plate slice comes back as the tongue PLUS a 0.58 mm3 sliver — the
            #    boolean-sliver trap from [[cad-tooling]]. coupons.py only volume-checked
            #    the compound, so it shipped slivers too. Keep the largest solid; a
            #    discarded piece over 5 mm3 means the slice box is wrong, not dirty.
            sol = sorted(p.solids(), key=lambda s: -s.volume)
            for junk in sol[1:]:
                if junk.volume > 5.0:
                    raise SystemExit(
                        f"variant {lab} {tag}: slice split into a real {junk.volume:.1f} mm3 "
                        f"second solid — the box is cutting the wrong region")
            if len(sol) > 1:
                print(f"    {tag:<10} dropped {len(sol) - 1} sliver(s), "
                      f"largest {sol[1].volume:.2f} mm3")
            pieces.append((sol[0], tag))

        gx = i * PITCH_X
        for j, (p, tag) in enumerate(pieces):
            b = p.bounding_box()
            p = Pos(gx - (b.min.X + b.max.X) / 2,
                    -(b.min.Y + b.max.Y) / 2 + j * (GAP + (b.max.Y - b.min.Y)),
                    -b.min.Z) * p
            if tag == "block":
                p = emboss(p, lab)
            else:
                print(f"    plate      {p.volume:8.2f} mm3")
            parts.append(p)
            report.append((lab, inter, tag, p.volume))

    out = Compound(children=parts)
    bb = out.bounding_box()
    export_step(out, os.path.join(SHARE, "roam_gauge.step"))
    export_stl(out, os.path.join(SHARE, "roam_gauge.stl"))

    print("\nGAUGE — base-plate soft lock")
    print(f"  {'label':<6}{'interf':<9}{'block mm3':>11}{'plate mm3':>11}")
    for lab, inter in VARIANTS:
        v = {t: vol for l, it, t, vol in report if l == lab}
        print(f"  {lab:<6}{inter:<9.2f}{v.get('block', 0):11.1f}{v.get('plate', 0):11.1f}")
    print(f"\n  plate {bb.size.X:.0f} x {bb.size.Y:.0f} mm, {len(out.solids())} solids, "
          f"{out.volume / 1000:.1f} cm3  (~{out.volume / 1000 * 1.27:.0f} g PETG)")
    print("  roam_gauge.step + .stl")


if __name__ == "__main__":
    main()
