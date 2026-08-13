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
JACK_W, JACK_X = 20.0, 22.0   # ⚠️ NOT centred — button-side quartile of the top
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

# --------------------------------------------------------------- derived
POCK_L = PH_L + 2 * CLR
POCK_W = PH_W + 2 * CLR
POCK_D = PH_T + 0.3

OUT_W = POCK_W + 2 * WALL          # 75.1 — tray outer width
OUT_L = POCK_L + WALL              # 147.0 — closed at the jack end
OUT_H = FLOOR + POCK_D + LIP_H     # 13.4

PHONE_TOP_Y = POCK_L - CLR


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

    for svg in (SCREEN_SVG, EARPIECE_SVG, PROX_SVG):
        x0, y0, x1, y1 = face_rect(svg)
        cut += Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * Box(
            x1 - x0, y1 - y0, h, align=(Align.CENTER, Align.CENTER, Align.MIN))

    cx, cy, r = CAM_SVG
    cut += Pos(fx(cx), fy(cy), z0) * Cylinder(
        r + FEAT_TOL, h, align=(Align.CENTER, Align.CENTER, Align.MIN))

    return cut


def port_openings() -> Part:
    """The jack notch, the USB mouth and the two speakers."""
    cut = Part()

    # ⚠️ The jack is in the button-side quartile of the top edge, not centred.
    # The BASIC print has it centred and that is why it does not line up.
    cut += Pos(JACK_X, OUT_L - WALL / 2, FLOOR + POCK_D / 2) * Box(
        JACK_W, WALL + 2 * EPS, POCK_D + LIP_H,
        align=(Align.CENTER, Align.CENTER, Align.CENTER))

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


def build() -> Part:
    p = tray()
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
    export_step(part, os.path.join(out, "roam_step1.step"))
    export_stl(part, os.path.join(out, "roam_step1.stl"))

    bb = part.bounding_box()
    print(f"STEP 1 — phone housing, flat base")
    print(f"  outer      {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm")
    print(f"  pocket     {POCK_W:.1f} x {POCK_L:.1f} x {POCK_D:.1f}")
    print(f"  volume     {part.volume / 1000:.1f} cm3  ~= "
          f"{part.volume / 1000 * 1.27:.0f} g PETG")
    print("  face webs (min wall %.2f):" % MIN_WALL)
    for label, g in gaps():
        flag = "  <-- TOO THIN" if g < MIN_WALL else ""
        print(f"    {label:22s} {g:6.2f} mm{flag}")
    sx0, sy0, sx1, sy1 = face_rect(SCREEN_SVG)
    print(f"  screen ap. {sx1 - sx0:.1f} x {sy1 - sy0:.1f} "
          f"(margins L/R {fx(SCREEN_SVG[0]) + PH_W / 2:.2f} / "
          f"{PH_W / 2 - fx(SCREEN_SVG[2]):.2f})")
