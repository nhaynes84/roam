"""
ROAM Touch -- forearm bracer cradle for a Google Pixel (sailfish, 2016).

V1 form factor: a flat tray that holds the phone, carried on two transverse
saddle ribs that conform to the forearm, with an open span between them for
airflow. Strap anchors are slots in flat wings either side.

Print orientation: STANDING ON THE ELBOW END. Measured, not guessed --
verify_bracer.py compares four orientations by unsupported face area:

    standing on elbow end    13.3 cm2 support   8.4 cm2 bed   147 mm tall  <-- use
    on its side              36.4 cm2           5.9 cm2        91 mm
    pocket down              88.5 cm2          16.2 cm2        30 mm
    pocket up               105.9 cm2           0.6 cm2        30 mm

Pocket-up is the intuitive choice and the worst one: the part ends up balanced
on four thin rib-tip edges, so the slicer supports nearly the whole underside.
Standing it on end makes every wall vertical. Use a brim -- it is 147 mm tall
on a small footprint. Layer lines then run across the arm axis, which is the
weak direction in bending; the strap carries that load, not the tray, but do
not stand on it.

Geometry note -- the constraint that drives the shape:
a ~75 mm wide flat tray on a 90 mm diameter forearm has ~20 mm of sagitta.
That wedge is unavoidable for a rigid slab; the ribs carry it instead of a
solid block, which saves the weight and gives the phone a cooling gap.

ARM_R is nominal, NOT critical, and that is deliberate. Every rib face is cut
FOAM (4 mm) proud of where skin would be, for closed-cell foam or stick-on TPU.
A forearm is not a cylinder -- it tapers, and its cross-section reconfigures as
you pronate, because the radius crosses the ulna. A shell fitted rigidly to one
arm position binds in another. So: rigid only under the phone, where the screen
must stay flat; compliant at the skin, where the shape moves. The pad absorbs
several mm of error, which is why nobody has to measure anything precisely.
If you do want it closer: ARM_R = forearm circumference / (2*pi).
"""

from build123d import *
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
LIP_END = 4.0        # front lip at the hand end
LIP_H = 2.4          # lip height above the phone face (also screen standoff)

ARM_R = 45.0         # nominal forearm radius, mm (90 mm dia)
GAP = 4.0            # air gap between arm and tray underside, at the crown
FOAM = 4.0           # compliant pad thickness on EVERY rib face -- see below
RIB_W = 62.0         # rib span across the arm
RIB_T = 28.0         # rib thickness along the arm -- wide enough to host the
                     # strap channel, and more contact area is more comfortable
RIB_Y = (34.0, 112.0)  # rib centres, from the elbow (open) end

CAP_D = 10.0         # end-cap slip depth
# Strap runs in a channel on the UNDERSIDE of each rib, not on side flanges.
# Flanges made the device 91 mm wide for no structural reason and were also
# what the end cap collided with. This keeps the whole thing tray-width.
STRAP_W = 26.0       # channel width along the arm, for 25 mm webbing
STRAP_D = 2.2        # channel depth into the rib's arm face
BAR_X = 20.0         # retaining bars, either side of centre
BAR_W = 6.0

JACK_W = 22.0        # 3.5 mm jack notch (sailfish jack is on the TOP edge)

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
EPS = 0.1
# ★ Owner's finishing pass, measured off RoamTouchModded.step: 1.5 mm chamfer
# on every exterior edge. Do not lose this on the next regeneration -- it is
# most of what makes the thing read as a designed object rather than a blank.
CHAMFER = 1.5

# --------------------------------------------------------------- derived
POCK_L = PH_L + 2 * CLR
POCK_W = PH_W + 2 * CLR
POCK_D = PH_T + 0.3

OUT_W = POCK_W + 2 * WALL          # tray outer width
OUT_L = POCK_L + WALL              # closed at the hand end, open at the elbow
OUT_H = FLOOR + POCK_D + LIP_H

# The rib faces are carved by a cylinder FOAM larger than the arm, about an
# axis dropped by the same amount -- so every rib face stands FOAM proud of
# where skin would be, uniformly, while the crown still clears by GAP.
# That gap is for closed-cell foam or stick-on TPU, and it is what makes
# ARM_R approximate rather than critical: ~4 mm of squish absorbs the error,
# and a forearm changes cross-section as it pronates anyway.
ARM_CUT_R = ARM_R + FOAM
ARM_AXIS_Z = -(ARM_R + GAP + FOAM)

# how far the ribs hang below the tray at their outer tips
SAG = -(ARM_AXIS_Z + math.sqrt(ARM_CUT_R ** 2 - (RIB_W / 2) ** 2))


# --------------------------------------- SVG face coords -> model coords
# The phone sits with its TOP edge (headphone jack) at the hand end.
PHONE_TOP_Y = POCK_L - CLR         # Y of the phone's top edge in the tray
def fx(x):  return x - PH_W / 2    # SVG x -> model X (centred)
def fy(y):  return PHONE_TOP_Y - y  # SVG y -> model Y (elbow = 0)

# Screen aperture: the housing bezel closes down to the black display area,
# opened by FEAT_TOL so a tracing error can never clip live pixels.
_sx0, _sy0, _sx1, _sy1 = SCREEN_SVG
WIN_X = max(abs(fx(_sx0)), abs(fx(_sx1))) + FEAT_TOL
WIN_Y0, WIN_Y1 = fy(_sy1) - FEAT_TOL, fy(_sy0) + FEAT_TOL


def bbox(x0, x1, y0, y1, z0, z1):
    """Axis-aligned box by bounds -- far less error-prone than align juggling."""
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(
        x1 - x0, y1 - y0, z1 - z0
    )


# ------------------------------------------------------------------ build
# Tray body: Y = 0 at the elbow (open) end, Y = OUT_L at the hand end.
part = bbox(-OUT_W / 2, OUT_W / 2, 0, OUT_L, 0, OUT_H)


# Saddle ribs
for y in RIB_Y:
    part += bbox(-RIB_W / 2, RIB_W / 2, y - RIB_T / 2, y + RIB_T / 2, -SAG, 0)

# Carve the forearm (plus the foam allowance) out of the ribs.
arm = Pos(0, OUT_L / 2, ARM_AXIS_Z) * Rot(90, 0, 0) * Cylinder(
    ARM_CUT_R, OUT_L + 60
)
part -= arm

# Strap channel: a second, larger cylinder over just the rib's centre band
# carves a groove into each rib's arm-facing face. The webbing lies in there,
# between rib and arm, and wraps the forearm -- no flanges, no threading.
for y in RIB_Y:
    part -= Pos(0, y, ARM_AXIS_Z) * Rot(90, 0, 0) * Cylinder(
        ARM_CUT_R + STRAP_D, STRAP_W)

# Retaining bars across the channel so the strap cannot fall out when it is
# off your arm. Trimmed back to the arm surface by re-cutting the arm after.
for y in RIB_Y:
    for sx in (-1, 1):
        part += bbox(sx * BAR_X - BAR_W / 2, sx * BAR_X + BAR_W / 2,
                     y - STRAP_W / 2, y + STRAP_W / 2,
                     -SAG - 1, 0)
part -= arm

# Phone pocket -- runs out the elbow end so the phone slides in
part -= bbox(-POCK_W / 2, POCK_W / 2, -10, POCK_L, FLOOR, FLOOR + POCK_D)

# Screen aperture. This is the bezel: the face closes down to the display
# instead of exposing the phone's own bezel, so the housing reads as the
# device rather than as a tray with a phone in it.
part -= bbox(-WIN_X, WIN_X, WIN_Y0, WIN_Y1, FLOOR + POCK_D, OUT_H + 10)

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

# 3.5 mm headphone jack notch, hand end
part -= bbox(
    -JACK_W / 2, JACK_W / 2,
    OUT_L - WALL - EPS, OUT_L + 10,
    FLOOR + 0.8, OUT_H + 10,
)

# Floor vents (cooling + weight), clear of the ribs
for (yc, ln) in ((73.0, 50.0), (135.0, 18.0)):
    vent = extrude(RectangleRounded(52.0, ln, VENT_R), amount=FLOOR + 4)
    part -= Pos(0, yc, -2) * vent


# ------------------------------------------------------- elbow end cap
# The phone slides in at the elbow end, so without this it can slide out --
# the strap is otherwise the only thing stopping it. REMOVABLE, not glued:
# it is the service access. A U-section that slips over the outside of the
# tray and snaps into two dimples, so nothing intrudes into the pocket
# (there is only 0.4 mm per side in there) and no tool is needed.
#
# ⚠️ USB-C is on this same end, so the cap carries a cable aperture. Without
# it you would unclip the cap every time you charged, which is how a
# removable part becomes a lost part.
CAP_W = 2.0          # cap side wall
# ⚠️ 6 mm, not 2.4. The full-face trough is lofted into this plate, so a thin
# plate makes the trough meet the outer face at a feather edge at the corners.
# The answer is material, not a slicer setting: a thicker plate gives the scoop
# real depth, a proper rim, and a gentler taper that prints cleanly. It also
# suits the chunky retro-futurist read.
CAP_T = 6.0          # cap end plate
CAP_CLR = 0.30       # slip fit over the tray
CAP_BUMP_R = 1.6     # snap dome radius
CAP_DIMPLE_D = 0.7   # how deep the dome sinks into the tray wall
CAP_BUMP_Y = 5.0     # dome centre. ⚠️ Must sit clear of the slot ends (7.5) --
# a dome overrunning the slot end makes a non-manifold shell there.
# The cap walls are stiff (2 mm PETG, braced by the end plate), so the domes
# have to sit on cantilever TONGUES or nothing can flex and the cap will not
# go on -- which is exactly what the first version got wrong.
CAP_TONGUE_H = 7.0   # tongue height, Z
CAP_SLOT_W = 1.4     # relief slot around it
# USB-C plug shell is 8.34 x 2.56 mm with fully rounded ends. Cut that SHAPE
# with ~1 mm of clearance, not a generic rectangle -- the taper does the work
# of accommodating fat overmoulds, so the opening itself can be tight.
USB_W, USB_H = 9.4, 3.6
USB_Z = FLOOR + PH_T / 2   # port sits mid phone thickness, NOT near the floor
# ★ Flare the cable aperture out on the OUTER face and taper it down to size.
# The end plate is only CAP_T thick, so a plain rectangular hole means only a
# slim cable head ever reaches the port -- a funnel lets fat overmoulds seat,
# and it reads as a designed feature instead of a punched hole.
USB_FLARE = 5.0            # per side, so a ~10 mm spread down to the opening
# ★ Retro-futurist: the flare is not an oval around the port, it is a trough
# spanning the whole face with the port at its centre. The loft tapers to
# nothing at the edges, so it never breaches the 2.4 mm plate -- it reads as a
# machined scoop rather than a punched hole with a chamfer round it.
# ⚠️ The mouth is centred on the FACE, the port is not: the cap face spans
# Z -CAP_CLR..OUT_H+CAP_CLR+CAP_W (centre 7.7) while USB_Z is 6.45. Centring
# the mouth on the port left 3.75 mm at the top and 1.25 at the bottom, which
# reads as a mistake. Lofting a face-centred mouth to a port-centred throat
# skews it slightly, which is the intent.
TROUGH_INSET = 0.8         # margin left all round -- near edge to edge

# Dimples in the tray's outer side walls. TRUNCATED CONES, not cylinders and
# not spheres: a cylinder presents a sharp edge square to the travel direction
# and will not go on at all, while a sphere rams a curved surface into a flat
# one and OCCT emits a non-manifold shell there (verified -- removing the
# spheres took both parts from 378 broken faces to zero). A cone gives the
# same camming ramp out of faces the kernel handles cleanly.
for _sx in (-1, 1):
    part -= Pos(_sx * (OUT_W / 2 + 0.2), CAP_BUMP_Y, OUT_H / 2) \
        * Rot(0, -90 * _sx, 0) \
        * Cone(1.8, 1.0, CAP_DIMPLE_D + 0.2,
               align=(Align.CENTER, Align.CENTER, Align.MIN))

# ★ A full collar, not a U: a bottom plate matching the top one. Four walls
# means the tray slides into a closed rectangular mouth, so loading and
# unloading reads like a magazine change instead of clipping a lid on. It also
# roots the snap tongues at both ends instead of leaving them hanging.
cap = bbox(-(OUT_W / 2 + CAP_CLR + CAP_W), OUT_W / 2 + CAP_CLR + CAP_W,
           -CAP_T, CAP_D,
           -(CAP_CLR + CAP_W), OUT_H + CAP_CLR + CAP_W)
# hollow out the slot the tray slides into
cap -= bbox(-(OUT_W / 2 + CAP_CLR), OUT_W / 2 + CAP_CLR,
            -EPS, CAP_D + EPS, -CAP_CLR, OUT_H + CAP_CLR)
# Cable aperture: a USB-C-shaped slot through the plate, flared on the outside
# and tapered down to it so any head can find the port behind a 2.4 mm plate.
cap -= Pos(0, -CAP_T - EPS, USB_Z) * Rot(-90, 0, 0) * extrude(
    RectangleRounded(USB_W, USB_H, USB_H / 2 - 0.01),
    amount=CAP_T + CAP_D + 2 * EPS)
# ⚠️ x_dir is pinned. Without it the plane picks its own axes and the flare
# comes out rotated 90 deg -- wide where the cap is thin, and it eats the plate.
# ⚠️ Built as a LOFT, not extrude(taper=). OCCT's extrude_taper throws
# Standard_TypeMismatch on a rounded profile at this angle (~64 deg).
_cap_half_w = OUT_W / 2 + CAP_CLR + CAP_W
_face_z0, _face_z1 = -(CAP_CLR + CAP_W), OUT_H + CAP_CLR + CAP_W
_face_zc = (_face_z0 + _face_z1) / 2
_trough_h = (_face_z1 - _face_z0) - 2 * TROUGH_INSET
cap -= loft([
    Plane(origin=(0, -CAP_T - EPS, _face_zc), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
    * RectangleRounded(2 * (_cap_half_w - TROUGH_INSET), _trough_h, 2.0),
    Plane(origin=(0, EPS, USB_Z), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
    * RectangleRounded(USB_W, USB_H, USB_H / 2 - 0.01),
])
# No finger notches. The first attempt put them at the open end on the centre
# line, which is exactly where the tongues root -- they cut the tongues clean
# off and the cap came out as five loose pieces. They are not needed either:
# the snap domes stand proud on the OUTSIDE too, so the grip point and the
# press-here-to-release point are the same feature.
# Relief slots that turn each side wall into a cantilever tongue, rooted at
# the OPEN end so the tip near the end plate is the compliant bit. Without
# these the wall is a plate braced on three sides and cannot open at all.
_tz = CAP_TONGUE_H / 2 + CAP_SLOT_W / 2
for _sx in (-1, 1):
    xw0 = _sx * (OUT_W / 2 + CAP_CLR) if _sx > 0 else _sx * (OUT_W / 2 + CAP_CLR + CAP_W)
    xw1 = _sx * (OUT_W / 2 + CAP_CLR + CAP_W) if _sx > 0 else _sx * (OUT_W / 2 + CAP_CLR)
    for _sz in (-1, 1):                       # slot above and below the tongue
        # ⚠️ starts at Y=0, NOT at the plate face -- running it through the end
        # plate saws the plate into strips and the cap falls into five pieces.
        cap -= bbox(min(xw0, xw1) - EPS, max(xw0, xw1) + EPS,
                    0.0, CAP_D - 2.5,
                    OUT_H / 2 + _sz * _tz - CAP_SLOT_W / 2,
                    OUT_H / 2 + _sz * _tz + CAP_SLOT_W / 2)
    # and free the tongue from the end plate, or it is built in at both ends
    cap -= bbox(min(xw0, xw1) - EPS, max(xw0, xw1) + EPS,
                0.0, CAP_SLOT_W,
                OUT_H / 2 - _tz, OUT_H / 2 + _tz)

# Snap noses on the tongues: cones rooted inside the wall (never coplanar with
# a face) and protruding 0.6 mm past the inner surface, so they stand 0.3 mm
# proud of the tray and seat into its dimples.
for _sx in (-1, 1):
    cap += Pos(_sx * (OUT_W / 2 + CAP_CLR + CAP_W / 2), CAP_BUMP_Y, OUT_H / 2) \
        * Rot(0, -90 * _sx, 0) \
        * Cone(1.8, 0.9, CAP_W / 2 + 0.6,
               align=(Align.CENTER, Align.CENTER, Align.MIN))

# ------------------------------------------------------- edge treatment
# Chamfer the outer envelope only: edges lying on the side walls, the top
# face or the underside. Feature edges (pocket, apertures, channel, plungers)
# are deliberately left sharp -- chamfering those would eat clearances.
def _on_envelope(e):
    c = e.center()
    return (abs(abs(c.X) - OUT_W / 2) < 0.02
            or abs(c.Z) < 0.02
            or abs(c.Z - OUT_H) < 0.02)

# OCCT refuses the whole envelope in one operation (ValueError), so chamfer in
# groups -- vertical corners, then the top rim, then the underside rim. Each
# group is attempted independently so one awkward set cannot lose the others.
_groups = {
    "vertical corners": lambda e: abs(abs(e.center().X) - OUT_W / 2) < 0.02 and e.length > 50,
    # Only the OUTER boundary of the top/bottom faces. Filtering on Z alone
    # also catches the screen aperture and button openings, and OCCT refuses
    # the mixed set outright.
    "top rim":          lambda e: abs(e.center().Z - OUT_H) < 0.02 and (
                            abs(abs(e.center().X) - OUT_W / 2) < 0.02
                            or abs(e.center().Y - OUT_L) < 0.02),
    "underside rim":    lambda e: abs(e.center().Z) < 0.02 and (
                            abs(abs(e.center().X) - OUT_W / 2) < 0.02
                            or abs(e.center().Y - OUT_L) < 0.02),
}
for _name, _pred in _groups.items():
    _es = ShapeList([e for e in part.edges() if _pred(e)])
    if not _es:
        continue
    try:
        part = chamfer(_es, length=CHAMFER)
        print(f"chamfer    {CHAMFER} mm on {len(_es):3d} edges  ({_name})")
    except Exception as exc:
        print(f"chamfer    SKIPPED {_name}: {type(exc).__name__}")

# ----------------------------------------------------------------- export
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(out, exist_ok=True)
export_step(part, os.path.join(out, "bracer.step"))
export_stl(part, os.path.join(out, "bracer.stl"))
export_step(cap, os.path.join(out, "bracer_endcap.step"))
export_stl(cap, os.path.join(out, "bracer_endcap.stl"))
print(f"end cap    {OUT_W + 2*(CAP_CLR+CAP_W):.1f} W x {CAP_D + CAP_T:.1f} L "
      f"x {OUT_H + CAP_CLR + CAP_W:.1f} H mm  ~= {cap.volume/1000*1.27:.0f} g")

print(f"outer      {OUT_W:.1f} W x {OUT_L:.1f} L x {OUT_H + SAG:.1f} H mm")
print(f"tray       {OUT_W:.1f} x {OUT_L:.1f} x {OUT_H:.1f}")
print(f"pocket     {POCK_W:.1f} x {POCK_L:.1f} x {POCK_D:.1f}")
print(f"rib drop   {SAG:.2f} mm  (ARM_R={ARM_R}, GAP={GAP}, RIB_W={RIB_W})")
print(f"volume     {part.volume/1000:.1f} cm3  ~= {part.volume/1000*1.27:.0f} g PETG")
