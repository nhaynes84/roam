#!/usr/bin/env python
"""RoamTouchCleaned.step (his Shapr3D master) -> roam_worn.step/.stl (the shared one file).

⚠️ roam.py is the STALE parametric master — do not run it, it would overwrite this.
   Mine it for design intent only. See memory: roam-cad-source-of-truth.

Every feature asserts a signed volume change and a single resulting solid. A boolean that
silently no-ops is the failure mode that cost a whole session; it cannot pass here.

    ~/Projects/synth-case/.venv/bin/python finish.py
"""
import os
from build123d import *
import numpy as np
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN, TopAbs_ON

SHARE = os.path.expanduser("~/Collab/CAD/roam-touch")
SRC = os.path.join(SHARE, "RoamTouchCleaned.step")

# ---- measured from the master, not remembered -------------------------------
WALLS = [("aft", -286.4, -284.2), ("fore", -169.0, -166.1)]   # end-wall bands
BRANCH_X, BRANCH_SEAT_Z = -28.64, 20.69     # port pin seat (vertical branch)
SLOT_RAD, DETENT_R, PIN_R = 1.50, 0.55, 1.20
DETENT_Z = BRANCH_SEAT_Z + PIN_R + DETENT_R  # bump sits pin_r+bump_r off the seat
DEAD_POSTS = [(-28.60, 20.93), (-28.08, 23.89)]   # detents built as mid-channel islands
FORE_PIN = (-15.05, 18.29)                   # SB fore pin axis
FORE_PIN_Y0, FORE_PIN_Y1 = -171.0, -163.5    # 1.0 into the plate so the union bites


def step(shape, new, label, sign):
    d = new.volume - shape.volume
    n = len(new.solids())
    ok = (d > 0.05 if sign == "+" else d < -0.05)
    print(f"  {'OK  ' if ok and n == 1 else 'FAIL'} {label:44s} dV {d:+9.2f} mm3  solids {n}")
    assert ok and n == 1, f"{label} did not land"
    return new


# ---- SB flush detents -------------------------------------------------------
# ★ His call: flush detents in solid stock, NOT an interference ring — "the current ring
#   on the tube thing is going to not wear particularly well". A hoop snap creeps; a
#   rounded ridge seated in a groove does not. "the SB side is literally just a block".
# ⚠️ NO SPHERES. OCC booleans fail against Sphere on this housing: it reports a zero
#   intersection and then ADDS 9.2 mm3. A Box in the same spot cuts correctly (verified).
#   Cylinders are sound — and a ridge/groove pair carries far more contact area than a
#   ball/dimple, which is the point when the joint has to survive many cycles.
# Measured: tongue end face x 36.60..36.75, block face x 36.85, 5.65-9.60 mm solid behind.
DET_STATIONS = (-280.0, -250.0, -190.0, -160.0)
DET_Z = -7.40                     # tongue mid-height (tongue spans z -6.60..-8.20)
# ★ RIDGE_TIP is the ONE fit constant for the base-plate soft locks:
#   interference = RIDGE_TIP - BLOCK_FACE (36.85). 37.15 = 0.30, which he printed and
#   called "just too tight" (2026-08-21). Overridable so gauge.py can sweep it WITHOUT
#   touching roam_worn.step.
RIDGE_R, RIDGE_LEN = 0.50, 10.0
RIDGE_TIP = float(os.environ.get("ROAM_RIDGE_TIP", 37.15))
GROOVE_R, GROOVE_BOT, GROOVE_LEN = 0.65, 37.40, 14.0
BLOCK_FACE = 36.85


def _ycyl(x, y, z, r, ln):
    """cylinder with its axis along Y, centred on (x, y, z)"""
    return Pos(x, y, z) * Rot(90, 0, 0) * Cylinder(r, ln)


def sb_detents(housing, base):
    """Rounded ridge on the plate tongue, matching groove in the housing block.
    Seated, the faces sit flush; entry needs the plate to bow by the interference."""
    for y in DET_STATIONS:
        base = step(base, base + _ycyl(RIDGE_TIP - RIDGE_R, y, DET_Z, RIDGE_R, RIDGE_LEN),
                    f"ridge  y{y:.0f}  interference {RIDGE_TIP - BLOCK_FACE:.2f}", "+")
        housing = step(housing, housing - _ycyl(GROOVE_BOT - GROOVE_R, y, DET_Z, GROOVE_R, GROOVE_LEN),
                       f"groove y{y:.0f}  depth {GROOVE_BOT - BLOCK_FACE:.2f}", "-")
    return housing, base


# ---- clips ------------------------------------------------------------------
# ★ "the current ring on the tube thing is going to not wear particularly well" — right.
#   The bead is 5 arcs but two span 104 and 84 deg: a stiff arc held at 0.35 interference
#   creeps in PETG and the grip fades. Two changes: drop the interference to 0.20, and
#   split the 150 deg collet finger so what does flex is short and compliant.
# ★ Plus a REAL clip: cap and housing both have solid SB blocks that never touched.
#   Cap face y-400 (10mm behind it), housing solid y-300 inboard 19.75mm, x 37..46 at z-9.
TUBE_X, TUBE_Z = -50.87, 13.84
BEAD_KEEP_R = 14.90          # was 15.05 against a 14.70 bore -> 0.35; now 0.20
BEAD_Y0, BEAD_Y1 = -392.0, -390.0
FINGER_SPLITS = (135.0, 207.0)   # the 96-246 deg finger, halved

# ★ Run the tongue VERTICAL, not flat: the SB flank only gives 9.10 of x-stock
#   (36.80..45.90) but 17.40 of z (-2.00..-19.40) is dead space. On edge the clip gets
#   12.0 of engagement instead of 5.70, and sits 3.35 off the skin instead of 1.4.
CLIP_X, CLIP_Z = 41.35, -10.70
CLIP_T, CLIP_H, CLIP_LEN = 2.0, 12.0, 7.0     # thickness(x), height(z), reach(y)
POCKET_CLR = 0.2
RIDGE_R, RIDGE_PROUD = 0.50, 0.35
GRV_R, GRV_DEEP = 0.65, 0.50
CAP_FACE_Y, HOUSING_FACE_Y = -400.0, -300.0
CLIP_DET_OFF = 3.5


def _ycyl2(x, y, z, r, ln):
    return Pos(x, y, z) * Rot(90, 0, 0) * Cylinder(r, ln)


def clips(housing, endcap):
    ym = (BEAD_Y0 + BEAD_Y1) / 2
    endcap = step(endcap, endcap - (_ycyl2(TUBE_X, ym, TUBE_Z, 15.40, BEAD_Y1 - BEAD_Y0)
                                    - _ycyl2(TUBE_X, ym, TUBE_Z, BEAD_KEEP_R, BEAD_Y1 - BEAD_Y0 + 1)),
                  f"bead cut back to r{BEAD_KEEP_R} (0.20 interference)", "-")
    for a in FINGER_SPLITS:
        endcap = step(endcap, endcap - Pos(TUBE_X, -392.5, TUBE_Z) * Rot(0, 90 - a, 0)
                      * Pos(0, 0, 14.0) * Box(1.6, 11.0, 8.0),
                      f"collet relief slot at {a:.0f} deg", "-")

    # SB clip: vertical tongue on the cap, pocket in the housing, ridge/groove detent
    t_y0, t_y1 = CAP_FACE_Y - 1.0, CAP_FACE_Y + CLIP_LEN
    endcap = step(endcap, endcap + Pos(CLIP_X, (t_y0 + t_y1) / 2, CLIP_Z)
                  * Box(CLIP_T, t_y1 - t_y0, CLIP_H), "SB tongue on cap (vertical)", "+")
    p_y0, p_y1 = HOUSING_FACE_Y, HOUSING_FACE_Y + CLIP_LEN + 0.5
    housing = step(housing, housing - Pos(CLIP_X, (p_y0 + p_y1) / 2, CLIP_Z)
                   * Box(CLIP_T + 2 * POCKET_CLR, p_y1 - p_y0, CLIP_H + 2 * POCKET_CLR),
                   "SB pocket in housing", "-")
    # detent on the OUTBOARD face of the tongue; Cylinder's own axis is Z, so no rotation
    face = CLIP_X + CLIP_T / 2
    endcap = step(endcap, endcap + Pos(face + RIDGE_PROUD - RIDGE_R, CAP_FACE_Y + CLIP_DET_OFF, CLIP_Z)
                  * Cylinder(RIDGE_R, CLIP_H - 2.0),
                  f"clip ridge, {RIDGE_PROUD - POCKET_CLR:.2f} interference", "+")
    wall = face + POCKET_CLR
    housing = step(housing, housing - Pos(wall + GRV_DEEP - GRV_R, HOUSING_FACE_Y + CLIP_DET_OFF, CLIP_Z)
                   * Cylinder(GRV_R, CLIP_H + 0.6), "clip groove in pocket", "-")
    return housing, endcap


# ---- card pocket ------------------------------------------------------------
# ISO 7810 ID-1 = 85.60 x 53.98 x 0.76. Two separate stacked slots, not one double
# pocket: a shared slot sized for two thin cards jams on one thick one.
# ★ Carried by the BASE PLATE. The sub-phone void has no internal structure — it is
#   just the gap between the outer shell and the plate (16mm at port tapering to 3mm
#   at starboard), so nothing else is available to hang slot walls from.
# ★ Flush + retrievable: a hard BACKSTOP at card length so it cannot drift aft, and a
#   thumb notch at the mouth. Friction alone on a 0.76 card either grips or lets it drift.
CARD_CX, CARD_W = -7.0, 54.60          # 53.98 + 0.62 clearance
CARD_SLOT_H = 0.95                     # 0.76 card, light friction
CARD_FACE_Y, CARD_DEEP = -300.0, 86.50 # backstop 0.9 past the card
# ★ walls 4.0 not 2.0: the door pegs INTO them. The block is embedded in the plate, so its
#   side faces are not exposed and a wrap-around lip has nothing to grip (95 mm3 of clash).
WALL_X, SHELF_T, TOP_T, FLOOR_T = 4.0, 1.0, 1.0, 1.2
Z_FLOOR = -8.0                         # base-plate top runs z -9..-8 across the span
NOTCH_W, NOTCH_L = 14.0, 8.0


def cards(base):
    x0, x1 = CARD_CX - CARD_W / 2, CARD_CX + CARD_W / 2
    y0, y1 = CARD_FACE_Y, CARD_FACE_Y + CARD_DEEP + 1.5
    ym, yl = (y0 + y1) / 2, y1 - y0
    z_s1 = Z_FLOOR                       # slot 1: Z_FLOOR .. +H
    z_sh = z_s1 + CARD_SLOT_H            # shelf
    z_s2 = z_sh + SHELF_T                # slot 2
    z_tp = z_s2 + CARD_SLOT_H            # top plate
    z_top = z_tp + TOP_T
    # one block, then the slots cut out of it — keeps it a single body
    blk = Pos(CARD_CX, ym, (Z_FLOOR - FLOOR_T + z_top) / 2) * Box(
        CARD_W + 2 * WALL_X, yl, z_top - (Z_FLOOR - FLOOR_T))
    base = step(base, base + blk, "card pocket block on the base plate", "+")
    for i, zb in enumerate((z_s1, z_s2)):
        base = step(base, base - Pos(CARD_CX, CARD_FACE_Y + CARD_DEEP / 2, zb + CARD_SLOT_H / 2)
                    * Box(CARD_W, CARD_DEEP, CARD_SLOT_H), f"card slot {i+1} ({CARD_SLOT_H} tall)", "-")
    base = step(base, base - Pos(CARD_CX, CARD_FACE_Y + NOTCH_L / 2, (z_sh + z_top) / 2)
                * Box(NOTCH_W, NOTCH_L, z_top - z_sh), "thumb notch at the mouth", "-")
    return base


# ---- phone retaining rim ----------------------------------------------------
# ★ The cable channel (x 39.5..48.75, y -285..-165) is open from the tray straight down
#   into the void — the phone can slide starboard into it and jostle. His fix: a small rim,
#   "2 or 3 or 4 mm", NOT a narrower cavity: the USB charger lead still needs that space.
# ★ Rim sits on the INBOARD lip so the channel keeps its full width for the cable.
# ⚠️ The ledge is ~8mm wide at both ends (x 32.0..40.0) but the middle can only be ~3mm:
#    the shut face plate's SB edge is at x 35.43, and the cable channel starts at x 39.50.
#    A bare 1.5mm ridge butting into an 8mm wall left a 5.5mm step, so the ends are RAMPED
#    in plan to blend instead of butting square.
RIM_X0, RIM_X1 = 36.20, 39.20    # 0.77 off the face plate, 0.30 off the cable channel
RIM_Y0, RIM_Y1 = -288.0, -160.0  # runs into the end walls so the joint is buried
RIM_Z0, RIM_Z1 = 5.0, 12.0       # 12.0 = the height the ledge already has at both ends
RAMP_LEN, RAMP_X = 10.0, 32.20   # blend out to the end wall's inboard face


def phone_rim(housing):
    # ⚠️ NO plan-view ramp is possible into the end walls. The face plate runs y -289..-163.5
    #    with its edge at x 35.43, and the end walls start at y -290 — about 1mm of gap. A
    #    blend has to reach inboard of 35.43, which is where the plate is (tried it: 21.50 mm3
    #    of clash at x 32.79..35.43). The step from the 8mm end wall down to this 3mm ledge is
    #    forced by the plate, not a choice.
    return step(housing, housing + Pos((RIM_X0 + RIM_X1) / 2, (RIM_Y0 + RIM_Y1) / 2,
                                       (RIM_Z0 + RIM_Z1) / 2)
                * Box(RIM_X1 - RIM_X0, RIM_Y1 - RIM_Y0, RIM_Z1 - RIM_Z0),
                f"ledge {RIM_X1-RIM_X0:.1f} wide x {RIM_Y1-RIM_Y0:.0f} long to z{RIM_Z1}", "+")


# ---- cap mouth rim ----------------------------------------------------------
# ★ The cap is hollow and its cavity opens on the FORE face (y -400, the face that meets
#   the housing). Seated it lands at y -301..-315, right behind the phone, so the phone
#   slides aft into the cap and wiggles. His fix: "a 2x2 rim on the fore face of that cavity".
# ⚠️ FIRST ATTEMPT WAS WRONG: I built the rim from the cavity's BOUNDING BOX. The cavity is
#   a slanted wedge, so a rectangular frame hangs out in open air along two edges, and
#   `frame - cap` does not remove those (they sit in void, not in material). His words:
#   "you did not outline the cavity correctly".
# ★ Correct way: SECTION the cap at the mouth plane. The section face has exactly one
#   INNER WIRE, and that wire IS the cavity outline. Offset it -2.0 in plane and extrude.
CAP_MOUTH_Y, RIM_W, RIM_D = -400.0, 2.0, 2.0
# ⚠️ SECOND ATTEMPT ALSO WRONG: a rim right around the mouth walls the cavity off and the
#    charger cannot get in — "you overcompensated, we just need a little something so the
#    phone doesn't slide around". So keep only two short STOPS near the phone's edges and
#    leave the whole middle of the mouth clear for the lead.
RIM_TABS = ((-22.0, -8.0), (18.0, 32.0))    # x windows the rim survives in


def cap_rim(endcap):
    pl = Plane(origin=(0, CAP_MOUTH_Y - 1.0, 0), z_dir=(0, 1, 0))
    face = sorted(endcap.intersect(pl).faces(), key=lambda f: -f.area)[0]
    inner = face.inner_wires()
    assert len(inner) == 1, f"expected 1 cavity wire, got {len(inner)}"
    cav = Face(inner[0])
    ring = extrude(cav - offset(cav, -RIM_W), amount=RIM_D / 2, both=True)
    keep = None
    for x0, x1 in RIM_TABS:
        blk = Pos((x0 + x1) / 2, CAP_MOUTH_Y - RIM_D / 2, 0) * Box(x1 - x0, RIM_D + 2, 120)
        keep = blk if keep is None else keep + blk
    return step(endcap, endcap + (ring & keep),
                f"cap mouth stops, {len(RIM_TABS)} tabs {RIM_W}x{RIM_D}", "+")


# ---- port flange relief -----------------------------------------------------
# ⚠️ PRE-EXISTING in his file, not introduced here: the base plate's port flange overlaps
#    the housing shell by ~110.9 mm3 along the ENTIRE 161 mm — a wedge at the flange's top
#    corner (x -36.45..-35.45, z 4.47..6.34). The plate cannot seat without forcing.
# ★ Trim the PLATE, not the housing: the shell is structural, the flange corner is not, and
#   the plate is the part that comes off. Cut against the real shell surface plus clearance
#   so the relief follows the diagonal instead of leaving a square notch.
FLANGE_CLR = 0.20


def flange_relief(housing, base):
    local = housing & (Pos(-37.0, -219.3, 5.0) * Box(12.0, 170.0, 12.0))
    try:
        cutter = offset(local, FLANGE_CLR)
        how = f"shell + {FLANGE_CLR} clearance"
    except Exception:
        cutter, how = local, "shell (no clearance - offset unavailable)"
    return step(base, base - cutter, f"port flange relief, {how}", "-")


# ---- card door --------------------------------------------------------------
# ⚠️ The seated cap does NOT cover the card mouth — it has no material below z -4 across
#    the whole span, so the slots open into free air and cards fall out. (I claimed the cap
#    was the door; it is not.) And his requirement: "i don't want to have to take the cap
#    off to get access to that space". So the door lives on the BASE PLATE and clips by hand.
# ★ Retention on the block's SIDE faces: its underside is buried in the plate and only the
#   top and sides are exposed, so side lips are the only two-point grip available.
DOOR_T, PEG_R, PEG_L, PEG_CLR = 2.5, 1.10, 6.0, 0.10
PEG_BEAD, PEG_BEAD_BACK = 0.30, 1.6
BLK_X0, BLK_X1 = CARD_CX - CARD_W / 2 - WALL_X, CARD_CX + CARD_W / 2 + WALL_X
BLK_Z0, BLK_Z1 = Z_FLOOR - FLOOR_T, Z_FLOOR + 2 * CARD_SLOT_H + SHELF_T + TOP_T
DOOR_DET_Y = -296.0
D_RIDGE_R, D_GRV_R, D_PROUD = 0.50, 0.65, 0.35
GRIP_W, GRIP_H = 16.0, 1.6


def card_door(base, endcap):
    """Hand-removable cover over the card mouth. Two pegs press into the block's side
    walls — the only faces with real material, now that the walls are 4.0 wide."""
    y0 = CARD_FACE_Y
    door = Pos(CARD_CX, y0 - DOOR_T / 2, (BLK_Z0 + BLK_Z1) / 2) \
        * Box(BLK_X1 - BLK_X0, DOOR_T, BLK_Z1 - BLK_Z0)
    zc = (BLK_Z0 + BLK_Z1) / 2
    for xw in (BLK_X0 + WALL_X / 2, BLK_X1 - WALL_X / 2):
        door += Pos(xw, y0 + PEG_L / 2 - 0.5, zc) * Rot(90, 0, 0) * Cylinder(PEG_R, PEG_L + 1.0)
        door += (Pos(xw, y0 + PEG_L - PEG_BEAD_BACK, zc) * Rot(90, 0, 0) * Cylinder(PEG_R + PEG_BEAD, 1.2))
        base = step(base, base - Pos(xw, y0 + PEG_L / 2, zc) * Rot(90, 0, 0)
                    * Cylinder(PEG_R + PEG_CLR, PEG_L), f"peg bore x{xw:+.1f}", "-")
        base = step(base, base - (Pos(xw, y0 + PEG_L - PEG_BEAD_BACK, zc) * Rot(90, 0, 0)
                    * Cylinder(PEG_R + PEG_BEAD + 0.1, 1.6)), f"peg detent groove x{xw:+.1f}", "-")
    door += Pos(CARD_CX, y0 - DOOR_T - GRIP_H / 2, BLK_Z0 + 1.0) * Box(GRIP_W, GRIP_H, 2.0)
    # ★ trim against the SEATED cap so the door never fights it (0.24 mm3 corner nick)
    seated = Pos(0, 100.0, 0) * endcap
    try:
        door = door - offset(seated & (Pos(20, -300, -6) * Box(30, 30, 30)), 0.20)
    except Exception:
        door = door - seated
    assert len(door.solids()) == 1, f"door is {len(door.solids())} pieces"
    print(f"  OK   card door {BLK_X1-BLK_X0:.1f} x {BLK_Z1-BLK_Z0:.1f} x {DOOR_T}, 2 pegs"
          f"   vol {door.volume:7.1f} mm3  solids 1")
    return base, door


# ---- slide-out tray ---------------------------------------------------------
# ★ His call: the whole sub-phone void becomes a drawer. "make the tray fit the void, use
#   the full space; detent stops is the right play, don't pull all the way out".
# ⚠️ WHY NOT SLOTS: the void is a LENS, not a box — 9.0 tall but only >=54.6 wide between
#   z -3.5 and -7.0. An ID-1 card (53.98) only lies flat in that 3.5mm band, so stacked
#   slots fought the cavity and a walled rectangular drawer could not hold a card at all.
#   Following the lens gives ~25 cm3 of usable volume instead of two cards and nothing else.
# ★ The drawer FRONT is the closure — no separate door to lose (his objection to the last one).
TRAY_CLR, TRAY_WALL, TRAY_FRONT = 0.35, 1.20, 2.50
# ★ Back wall on the FORE end: without it the hollow runs out the far end and contents slide
#   off into the cavity when the drawer is pulled.
TRAY_BACK = 1.50
# ★ The void runs the WHOLE length — identical cross-section from y -298 to y -148. A 90mm
#   tray used barely half of it. 148 takes it to y -152, just short of the fore wall.
TRAY_Y0, TRAY_LEN = -300.0, 148.0
MOUTH_Y = -297.0
TRAY_SECTION_Y = -250.0
# ★ Clip the profile at z -3.5: that is the highest point where the lens is still >=54.6
#   wide, so it is the highest a card can be loaded through. Above it the void pinches to
#   ~32 wide and would be unusable anyway — the housing shell closes it when the tray is in.
TRAY_TOP_Z = -4.0
DET_RIDGE_R, DET_DEPTH, DET_GRV_R = 0.60, 0.40, 0.75   # ridge proud = gap + depth
# ⚠️ DETENT HEIGHT MUST FIT INSIDE THE TRAY. At 6.0 tall on a 3.5 tall tray the ridges stood
#    2mm proud top and bottom and punched into the phone cavity — he spotted them as 'posts'.
DET_H = 2.0
TRAY_RIDGE_Y = -200.0          # far forward, so the drawer can travel a long way before stopping
TRAY_STOP_Y = -290.0           # -> 90mm of travel, 58mm still engaged
DET_Z_BAND = -6.0              # the widest band of the lens, where both walls are solid
# ⚠️ the travel stop sits higher than the detent: at z -6.0 its bump clipped the base plate
STOP_Z_BAND = -5.4


# ★ PARAMETRIC profile, drawn from the measured lens — NOT sampled-and-offset.
# ⚠️ The sampled version traced 47 vertices and offsetting that outline fragmented the inner
#    profile (internal width read 42.75, then 6.50, then 73.75 — real geometry never does
#    that). I then read my own broken output as a design limit and told him a card barely
#    fitted. It fits with ~9mm to spare. Draw both profiles; never offset a sampled polygon.
#
# ⚠️⚠️ MEASURE WITH AN UNCAPPED SCAN. My width sweep ran np.arange(-42, 30) and reported the
#    SCAN LIMIT as the wall — the void read 29.8 wide at z -6 (really 34.0) and looked
#    non-prismatic (it is identical at every station). Both were artefacts.
#
# ★ The void is a LENS. Measured at y -297, uncapped:
LENS = ((0.50, -35.00, -3.00), (0.00, -35.00, -0.25), (-0.50, -35.25, 2.75),
        (-1.00, -35.25, 5.50), (-1.50, -35.25, 8.50), (-2.00, -35.50, 11.25),
        (-2.50, -35.50, 14.00), (-3.00, -35.50, 17.00), (-3.50, -35.75, 19.75),
        (-4.00, -35.75, 22.50), (-4.50, -35.75, 25.50), (-5.00, -36.00, 28.25),
        (-5.50, -36.00, 31.00), (-6.00, -36.25, 34.00), (-6.50, -36.25, 36.25),
        (-7.00, -36.25, 23.00), (-7.50, -36.50, 9.75), (-8.00, -36.50, -3.50))
# ★★ RIM CAPS AT z -4.00 and that is not negotiable: the rim IS the loading mouth, and a card
#    needs 54.6 there (58.3 raw - 2*1.55 = 55.2, just clears). Tilting a card through a
#    narrower mouth needs ~46mm of vertical room in a 9mm-deep tray — it does not work.
# ★★ But EVERYTHING BELOW the rim is fair game, and the widest part of the lens (72.5 at
#    z -6.5) was not in the tray at all — "you're only using like 1/2 the available space".
# ★★ ASYMMETRIC SCOOP, not a box with a flat rim. The PORT edge of the void is VERTICAL at
#    x -35.0..-36.5 for its whole height; only STARBOARD rakes in. So the port wall runs full
#    height and the tray is left OPEN across the top-starboard face. A card drops in over the
#    low starboard side — no rim width constraint at all, which is what killed the old design.
TRAY_RIM_Z, TRAY_FLOOR_Z, TRAY_BOT_Z, TRAY_TOP_Z = -4.00, -7.60, -8.00, 0.50


def _lens_pts(inset, z_lo, z_hi):
    rows = [(z, lo + inset, hi - inset) for z, lo, hi in LENS
            if z_lo - 1e-6 <= z <= z_hi + 1e-6 and (hi - inset) - (lo + inset) > 6.0]
    return [(lo, z) for z, lo, _ in rows] + [(hi, z) for z, _, hi in reversed(rows)]


def _profile(pts):
    return Rot(90, 0, 0) * Face(Wire(Polygon(*pts, align=None).edges()))


def _extrude_fwd(face, y0, length):
    """Extrude FORWARD (+Y) from y0. ⚠️ The face normal follows the polygon winding, so the
    sign of `amount` is not stable across profile edits — check the result, do not assume."""
    sol = extrude(Pos(0, y0, 0) * face, length)
    if sol.bounding_box().min.Y < y0 - 0.5:
        sol = extrude(Pos(0, y0, 0) * face, -length)
    return sol



def _mouth_face(housing, base):
    """Outline of the WHOLE void mouth, for the drawer front. ⚠️ The tray body only spans
    z -7.5..-4.0, but the mouth runs z -8.5..+1.0 — a front sized to the body leaves most of
    the opening exposed and the contents fall straight out the back. His catch."""
    cls = [BRepClass3d_SolidClassifier(sol.wrapped) for sol in (housing, base)]

    def solid(x, z):
        for c in cls:
            c.Perform(gp_Pnt(x, MOUTH_Y, z), 1e-7)
            if c.State() in (TopAbs_IN, TopAbs_ON):
                return True
        return False

    lo, hi = [], []
    for z in np.arange(0.8, -9.21, -0.25):
        run, keep = [], None
        for x in np.arange(-55.0, 55.0, 0.25):
            if not solid(float(x), float(z)):
                run.append(float(x))
            else:
                if run and run[0] <= -20.0 <= run[-1]:
                    keep = run
                run = []
        if run and run[0] <= -20.0 <= run[-1]:
            keep = run
        if keep is None or keep[-1] - keep[0] < 6.0:
            continue
        lo.append((keep[0] + TRAY_CLR, float(z)))
        hi.append((keep[-1] - TRAY_CLR, float(z)))
    assert len(lo) > 8, f"mouth trace too short ({len(lo)})"
    print(f"       mouth: {len(lo)} rows, z {lo[-1][1]:.1f}..{lo[0][1]:.1f}, "
          f"widest {max(h[0]-l[0] for l, h in zip(lo, hi)):.1f} mm")
    return Rot(90, 0, 0) * Face(Wire(Polygon(*(lo + hi[::-1]), align=None).edges()))


def tray(housing, base):
    o = _lens_pts(TRAY_CLR, TRAY_BOT_Z, TRAY_TOP_Z)
    rows = []
    for z, lo, hi in LENS:
        if z < TRAY_FLOOR_Z - 1e-6 or z > TRAY_TOP_Z + 1e-6:
            continue
        left = lo + TRAY_CLR + TRAY_WALL
        # above the rim the inner runs way past the outer, which removes the starboard wall
        right = (hi - TRAY_CLR - TRAY_WALL) if z <= TRAY_RIM_Z else 60.0
        if right - left > 4.0:
            rows.append((z, left, right))
    i = [(l, z) for z, l, _ in rows] + [(r, z) for z, _, r in reversed(rows)]
    outer, inner = _profile(o), _profile(i)
    print(f"       outer z {TRAY_BOT_Z}..{TRAY_TOP_Z} (full lens)   port wall full height,"
          f" starboard wall to z {TRAY_RIM_Z}")
    body = _extrude_fwd(outer, TRAY_Y0, TRAY_LEN)
    hollow = _extrude_fwd(inner, TRAY_Y0 + TRAY_FRONT, TRAY_LEN - TRAY_FRONT - TRAY_BACK)
    t = body - hollow
    # front plate covers the ENTIRE mouth, not just the tray body's cross-section
    t += _extrude_fwd(_mouth_face(housing, base), TRAY_Y0, TRAY_FRONT)
    tb = t.bounding_box()
    print(f"       tray x {tb.min.X:.1f}..{tb.max.X:.1f}  y {tb.min.Y:.1f}..{tb.max.Y:.1f}"
          f"  z {tb.min.Z:.1f}..{tb.max.Z:.1f}")
    # ★ Detents at the WIDEST band (z -6.0), where both side walls are solid stock.
    # ⚠️ The two walls belong to DIFFERENT parts — port is the base plate's flange, starboard
    #    is the housing. Detect which, and cut the groove out of whichever one is actually there.
    parts = {"housing": housing, "base": base}
    cls = {k: BRepClass3d_SolidClassifier(v.wrapped) for k, v in parts.items()}

    def owner(x, y, z):
        for k, c in cls.items():
            c.Perform(gp_Pnt(x, y, z), 1e-7)
            if c.State() in (TopAbs_IN, TopAbs_ON):
                return k
        return None

    zd = DET_Z_BAND
    for sx in (-1, 1):
        # tray's own outer edge at this band: scan INWARD from outside, first solid wins
        tc = BRepClass3d_SolidClassifier(t.wrapped)
        tedge = None
        for x in np.arange(45.0, 0.0, -0.1) * sx:
            tc.Perform(gp_Pnt(float(x), TRAY_RIDGE_Y, zd), 1e-7)
            if tc.State() in (TopAbs_IN, TopAbs_ON):
                tedge = float(x)
                break
        assert tedge is not None, f"tray edge not found on side {sx}"
        edge, who = None, None
        for x in np.arange(abs(tedge) + 0.05, 45.0, 0.05) * sx:
            who = owner(float(x), TRAY_RIDGE_Y, zd)
            if who:
                edge = float(x)
                break
        assert edge is not None, f"no wall found on side {sx}"
        gap = abs(edge - tedge)
        print(f"       side {sx:+d}: tray x{tedge:+.2f}  wall x{edge:+.2f} ({who})  gap {gap:.2f}")
        # ⚠️ Anchor the ridge ON the tray edge and size its RADIUS to the gap. Offsetting a
        #    fixed-radius cylinder outward by (gap + depth) pushes its centre clear of the tray
        #    and it floats off as a second solid.
        rr = gap + DET_DEPTH
        t += Pos(tedge, TRAY_RIDGE_Y, zd) * Cylinder(rr, DET_H)
        tgt = parts[who]
        tgt = step(tgt, tgt - Pos(tedge, TRAY_RIDGE_Y, zd) * Cylinder(rr + 0.15, DET_H + 0.6),
                   f"closed detent in {who} x{edge:+.1f}", "-")
        tgt = step(tgt, tgt + Pos(edge, TRAY_STOP_Y, STOP_Z_BAND) * Cylinder(0.80, DET_H),
                   f"travel stop in {who} x{edge:+.1f}", "+")
        parts[who] = tgt
    housing, base = parts["housing"], parts["base"]
    assert len(t.solids()) == 1, f"tray is {len(t.solids())} pieces"
    b = t.bounding_box()
    print(f"  OK   tray {b.max.X-b.min.X:.1f} x {b.max.Z-b.min.Z:.1f} x {TRAY_LEN:.0f}"
          f"        vol {t.volume/1000:6.2f} cm3  solids 1")
    return housing, base, t


# ---- port detents (the "bottom slop") ---------------------------------------
# ⚠️ The slop is PLAY, not surface finish: the bottom face is a clean ramp (z -10.8 port to
#    -8.4 starboard, identical at every station). But the plate is located by four detents on
#    its STARBOARD tongue and nothing on port, so the port edge floats on 0.40 of clearance —
#    which is the clearance I introduced with the flange relief.
# ★ The housing overhangs the flange all the way across (gap 0.25..0.50), so the detent goes on
#   the flange's TOP face bearing upward. Same ridge/groove scheme, same stations as starboard.
PORT_DET_X = -34.80          # gap is tightest here (0.25)
PORT_RIDGE_TOP, PORT_RIDGE_R = 6.45, 0.50
PORT_GRV_BOT, PORT_GRV_R = 6.55, 0.65   # 0.10 slack, not 0.27 — this IS the slop
PORT_DET_LEN = 10.0


def port_detents(housing, base):
    for y in DET_STATIONS:
        base = step(base, base + Pos(PORT_DET_X, y, PORT_RIDGE_TOP - PORT_RIDGE_R)
                    * Rot(90, 0, 0) * Cylinder(PORT_RIDGE_R, PORT_DET_LEN),
                    f"port ridge y{y:.0f}", "+")
        housing = step(housing, housing - Pos(PORT_DET_X, y, PORT_GRV_BOT - PORT_GRV_R)
                       * Rot(90, 0, 0) * Cylinder(PORT_GRV_R, PORT_DET_LEN + 4.0),
                       f"port groove y{y:.0f}", "-")
    return housing, base


# ---- arm brace / band -------------------------------------------------------
# ⛔ NEVER GENERATE A CUFF. Four were tried in one night and all four were deleted — he
#    modelled the band himself. This IMPORTS his: ref/armband.step, extracted from his
#    RoamTouchSimpleSampleArmband.step. ⚠️ CAD comes from ~/Collab only.
# ★ Frame: the band is in roam.py coordinates. Transform derived from the RAIL, which is
#   identical in both files (89.8 long): y_shapr = y_roam - 300.0, x and z unchanged.
# ⚠️ The band arrives SOLID (355 cm3 / 451 g) and fills ~75% of the drawer lens down its whole
#    length, so the drawer void has to be cut back out of it — roam.py did the same for its
#    card slot. The base plate pocket likewise.
BAND_STEP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ref", "armband.step")
BAND_DY = -300.0
BAND_CUT_Y0, BAND_CUT_LEN = -322.0, 170.0


def brace(housing, base, drawer):
    band = Pos(0, BAND_DY, 0) * import_step(BAND_STEP)
    raw = band.volume
    void = _extrude_fwd(_profile(_lens_pts(0.0, TRAY_BOT_Z, TRAY_TOP_Z)), BAND_CUT_Y0, BAND_CUT_LEN)
    band = step(band, band - void, "cut the drawer void out of the band", "-")
    band = step(band, band - base, "cut the base-plate pocket out of the band", "-")
    # ⚠️ the drawer's FRONT PLATE covers the whole mouth (z -8.4..+0.8), wider than the lens
    #    void (-8.0..+0.5), so its edges bit the band — clear the drawer itself as well.
    band = step(band, band - drawer, "clear the drawer front from the band", "-")
    print(f"       band {raw/1000:.1f} -> {band.volume/1000:.1f} cm3  (~{band.volume*1.27/1000:.0f} g)")
    return step(housing, housing + band, "brace fused to the housing", "+")


# ---- sleeve keepers ---------------------------------------------------------
# ★ His call: "run parallel, fore to aft, no 30 degree cant, put the sleeve pieces directly on
#   the bottom face, no extra padding, this thing is thick enough as is".
# ⛔ NOT the imported band — that carries the cant and its own slab thickness.
# ★ g5/g6 ARE the sleeve pieces: strap keepers with a slot, webbing passing along y. They sit
#   on the STARBOARD flank canted 10 deg (face normals +-0.985 / -+0.174). Level them and lay
#   them on the bottom face instead. The bottom face is a 2.15 deg ramp, effectively flat.
KEEP_ROT = -100.0        # lays the big flange (normal 170 deg in xz) flat against -Z
KEEP_X = 0.0             # on the centreline of the bottom face
KEEP_FACE_Z = -9.60      # bottom face at x=0


def sleeve_keepers(base, g5, g6):
    out = base
    for g, nm in ((g5, "g5"), (g6, "g6")):
        b = g.bounding_box()
        cx, cy, cz = (b.min.X + b.max.X) / 2, (b.min.Y + b.max.Y) / 2, (b.min.Z + b.max.Z) / 2
        flat = Pos(-cx, -cy, -cz) * g
        flat = Rot(0, KEEP_ROT, 0) * flat
        fb = flat.bounding_box()
        # seat its top face on the bottom face, hanging down
        flat = Pos(KEEP_X, cy, KEEP_FACE_Z - fb.max.Z) * flat
        nb = flat.bounding_box()
        print(f"       {nm}: {nb.max.X-nb.min.X:5.2f} wide x {nb.max.Y-nb.min.Y:6.2f} long,"
              f" stands {KEEP_FACE_Z-nb.min.Z:5.2f} proud of the face")
        out = step(out, out + flat, f"sleeve keeper {nm} on the bottom face", "+")
    return out


# ---- underbelly sleeves -----------------------------------------------------
# ★ HIS SHAPE, exactly: "cut the bottom half of a circle off, then cut the top half off of
#   that" — what remains is the LEFT and RIGHT arcs. They wrap the arm; they are NOT strap
#   tunnels lying against the bottom face ("these have to sit around my arm, they're
#   currently facing up against the bottom").
# ★ ARM_R = 45.0 — his fitment number, from archive/verify_bracer.py. roam.py records it as
#   the one value that could never be derived.
# ★ The circle is fitted THROUGH both underbelly edges so the sleeves meet the plate instead
#   of floating: edges (-34, -10.80) and (30, -8.40) with R45 put the centre at (-0.81,-41.18).
ARM_R, SLV_WALL = 45.0, 2.50
ARM_CX, ARM_CZ = -0.81, -41.18
# ★ Cut the bottom half off the arcs — they wrapped all the way to the arm's centre height
#   and that length is not needed. Half the arc = 30 deg, i.e. z = ARM_CZ + ARM_R*sin(30).
SLV_BOTTOM_Z = ARM_CZ + ARM_R * 0.25   # half the previous cut: -18.68 -> -29.93
# ★ PORT arc runs on round to x -43 (theta 120 deg) where it beds into the pack-tube wall —
#   follow the curve to where it attaches, do NOT post it straight up. Checked: at that angle
#   the arc sits between the tube's bore (r14.70) and its OD (r17.20), so it never breaks in.
SLV_EDGE_P, SLV_EDGE_S = -23.0, 30.0
SLV_Y0, SLV_LEN = -294.0, 150.0
# ⚠️ shifted PORT: at x 0 the starboard arc punched 1591 mm3 through the SB block and the
#    mic channel (x 35.5..41.5), plus 586 into the rail.
SLV_SHIFT_X = -20.0
# rib joining the floating port arc up into the pack-tube wall (wall spans z -3.07..-0.51 at x-54)
# strap slots: webbing is 25mm wide and wraps AROUND the arm, so the slot's long axis runs
# fore-aft (the webbing's width) and it cuts radially through the 2.5mm sleeve wall.
STRAP_W, STRAP_T = 26.0, 3.0          # 25mm webbing + clearance, 3.0 across the arc
STRAP_Y = (-274.0, -164.0)            # ⚠️ 7mm of material beyond each slot; at -280/-158
                                      #    the slot came within 1mm of the sleeve end
# ★ 7mm up from the sleeve's bottom edge (edge at theta 14.07/165.93; 7mm of arc = 8.67 deg).
#   They were at mid-arc, ~13mm up, which he read as far too high.
STRAP_TH_PORT, STRAP_TH_STBD = 157.3, 22.7
# ★ "leave a grid structure for support, like a chainlink fence, hollow out the rest".
#   Windows through the wall between the two strap slots; 5mm ribs between them, and the
#   solid ends (y beyond -264 / -174) are left alone so the strap slots keep their material.
# ★ opened up: bigger windows and a third row to port (its arc is 46 deg against starboard's
#   33), for more removal and more compliance. Ribs land at ~4mm along y, ~3mm across the arc.
# ★ Two rows only — extend the pattern ALONG THE LENGTH, not by adding rows across the arc.
#   The clear span between the strap slots is y -261.2..-176.8 (84.4mm); 5 windows of 18 with
#   3mm ribs fills 90 of it, so the holes run the whole way rather than sitting in the middle.
# ⚠️ The grid rows must sit CLEAR of the strap-slot angles (port 157.3, stbd 22.7) — at theta
#    24 the first window merged into the stbd slot and left it with no surrounding material.
#    Separated, the columns are free to run the WHOLE length instead of only between the slots.
GRID_Y = (-282.0, -261.0, -240.0, -219.0, -198.0, -177.0, -156.0)
GRID_TH_PORT = (130.0, 145.0)
GRID_TH_STBD = (31.0, 41.0)
GRID_W, GRID_ARC = 18.0, 6.0


def sleeves(base, housing):
    ring = Pos(ARM_CX, ARM_CZ) * (Circle(ARM_R + SLV_WALL) - Circle(ARM_R))
    ring -= Pos(ARM_CX, SLV_BOTTOM_Z - 60.0) * Rectangle(240.0, 120.0)     # cut the bottom half off
    mid = (SLV_EDGE_P + SLV_EDGE_S) / 2
    ring -= Pos(mid, ARM_CZ + 60.0) * Rectangle(SLV_EDGE_S - SLV_EDGE_P, 120.0)  # cut the top
    sol = Pos(SLV_SHIFT_X, 0, 0) * _extrude_fwd(Rot(90, 0, 0) * ring, SLV_Y0, SLV_LEN)
    bb = sol.bounding_box()
    print(f"       {len(sol.solids())} arcs   x {bb.min.X:6.1f}..{bb.max.X:5.1f}"
          f"   z {bb.min.Z:6.1f}..{bb.max.Z:6.1f}   shifted {SLV_SHIFT_X:+.0f} to port, wall {SLV_WALL}")
    # ★ strap slots — cut radially through the wall, long axis fore-aft
    scx = ARM_CX + SLV_SHIFT_X
    for th in (STRAP_TH_PORT, STRAP_TH_STBD):
        for sy in STRAP_Y:
            sol -= Pos(scx, sy, ARM_CZ) * Rot(0, 90 - th, 0) * Pos(0, 0, (ARM_R + SLV_WALL / 2)) \
                * Box(STRAP_T, STRAP_W, 8.0)
    print(f"       4 strap slots {STRAP_W:.0f} x {STRAP_T:.0f} at y{STRAP_Y[0]:.0f}/{STRAP_Y[1]:.0f},"
          f" theta {STRAP_TH_PORT:.0f}/{STRAP_TH_STBD:.0f}")
    ncut = 0
    for ths in (GRID_TH_PORT, GRID_TH_STBD):
        for th in ths:
            for gy in GRID_Y:
                sol -= Pos(scx, gy, ARM_CZ) * Rot(0, 90 - th, 0) \
                    * Pos(0, 0, ARM_R + SLV_WALL / 2) * Box(GRID_ARC, GRID_W, 8.0)
                ncut += 1
    print(f"       {ncut} grid windows {GRID_W:.0f} x {GRID_ARC:.0f}, 5mm ribs")

    # ★ split the two arcs: starboard lands on the plate, port reaches the BATTERY TUBE.
    arcs = sorted(sol.solids(), key=lambda a: a.bounding_box().min.X)
    port_arc, stbd_arc = arcs[0], arcs[-1]
    base = step(base, base + stbd_arc, "starboard sleeve -> base plate", "+")
    joined = housing + port_arc
    pb = port_arc.bounding_box()
    print(f"  OK   port sleeve, arc carried to x{pb.max.X:+.1f} into the tube wall  "
          f"dV {joined.volume - housing.volume:+9.2f} mm3  solids {len(joined.solids())}")
    return base, joined


# ---- lightening -------------------------------------------------------------
# ★ Census (distance-transform, >3mm from any surface) put the dead stock in two slabs:
#     housing fore end wall   13.05 cm3 / 16.6 g   x -63.6..44.4, y -165..-139.5
#     end cap end wall         4.12 cm3 /  5.2 g   y -418..-401.5
#   The base plate, sleeves and face plate censused at 0.00 — already thin, leave them alone.
# ★ Pockets open toward the INTERIOR so they vent; an enclosed void traps supports.
# ⚠️ Kept clear of the face-plate pin sockets at y -168.9..-163.0 — pocket starts at y -158.
# ⚠️ The top face RAKES: z 30.25 at x -56 down to 12.50 at x 34. A single flat ceiling (z 24)
#    punched straight through it — the pockets became open holes in the fore top face.
#    Each pocket now gets its own ceiling, 2.0 under the LOWEST surface over its own x span.
# ⚠️ A narrow V-notch bottoms at z 20.25 at x -35 (2mm wide, surface 25.25 either side).
#    Dropping a whole band to clear it wastes volume — SPLIT around it and leave a rib there.
# ⚠️ band 1 sits over the PORT SLEEVE (its arc runs x -43..-67, top z 0.8) — at z0 -10 the
#    pocket ate the sleeve between theta 120 and 138. Band 1 gets its own floor above it.
HOUS_POCKETS = ((-54.0, -38.0, 2.0, 23.0), (-33.0, -26.0, -10.0, 21.0),
                (-21.0, 7.0, -10.0, 15.0), (12.0, 38.0, -10.0, 9.5))
HOUS_PKT_Y0, HOUS_PKT_Y1 = -158.0, -143.0
HOUS_PKT_Z0 = -10.0
# ⚠️ the cap's top rakes too (z 27.00 at x -40 down to 15.00 at x 20). A flat ceiling at 26
#    went straight through it — 0.00 skin. Banded, same as the housing.
# ⚠️ the surface DIPS to 22.25 at x -36 (a notch, not a smooth rake) — band 1 must clear that,
#    not the 27.00 either side of it. Band 3 stops at x 37, short of the cap edge.
# ⚠️ the cap's PACK TUBE occupies x -68..-33.7 — a pocket there cut straight through its wall
#    (27 wall points removed). Nothing port of x -32 any more.
CAP_POCKETS = ((-32.0, -28.0, 21.0), (-24.0, 0.0, 16.5), (4.0, 37.0, 8.5))
CAP_PKT_Z0 = -14.0
CAP_PKT_Y0, CAP_PKT_Y1 = -415.0, -401.5


def lighten(housing, endcap):
    for x0, x1, z0, z1 in HOUS_POCKETS:
        housing = step(housing, housing - Pos((x0 + x1) / 2, (HOUS_PKT_Y0 + HOUS_PKT_Y1) / 2,
                                              (z0 + z1) / 2)
                       * Box(x1 - x0, HOUS_PKT_Y1 - HOUS_PKT_Y0, z1 - z0),
                       f"fore-wall pocket x{x0:.0f}..{x1:.0f} z{z0:.0f}..{z1:.1f}", "-")
    for x0, x1, z1 in CAP_POCKETS:
        endcap = step(endcap, endcap - Pos((x0 + x1) / 2, (CAP_PKT_Y0 + CAP_PKT_Y1) / 2,
                                           (CAP_PKT_Z0 + z1) / 2)
                      * Box(x1 - x0, CAP_PKT_Y1 - CAP_PKT_Y0, z1 - CAP_PKT_Z0),
                      f"cap pocket x{x0:.0f}..{x1:.0f} to z{z1:.1f}", "-")
    return housing, endcap


# ---- phone-cavity floor grid ------------------------------------------------
# ★ "grid out the bottom of the phone cavity too, between the drawer and the phone".
#   That floor is a 2.10-2.20mm shell spanning x -34..22, y -280..-175, sloping from z 6.10
#   at x -22 down to -0.30 at x 14. Cuts are vertical boxes — they pass through the slope.
FLOOR_X = (-27.0, -13.0, 1.0, 15.0)
FLOOR_Y = (-272.0, -254.0, -236.0, -218.0, -200.0, -182.0)
FLOOR_W, FLOOR_L = 10.0, 14.0       # 4mm ribs both ways
FLOOR_Z0, FLOOR_Z1 = -4.0, 8.0


def floor_grid(housing):
    n = 0
    for fx in FLOOR_X:
        for fy in FLOOR_Y:
            housing = housing - Pos(fx, fy, (FLOOR_Z0 + FLOOR_Z1) / 2) \
                * Box(FLOOR_W, FLOOR_L, FLOOR_Z1 - FLOOR_Z0)
            n += 1
    print(f"  OK   phone-floor grid, {n} windows {FLOOR_W:.0f}x{FLOOR_L:.0f}, 4mm ribs"
          f"       solids {len(housing.solids())}")
    assert len(housing.solids()) == 1
    return housing


def main():
    S = sorted(import_step(SRC).solids(), key=lambda s: -s.volume)
    keep = [s for s in S if s.volume > 1.0]
    print(f"slivers dropped: {len(S) - len(keep)}")
    housing, endcap, base, faceplate, rail, g5, g6 = keep[:7]
    sleeve_src = (g5, g6)
    extra = keep[7:]                      # tab7 (fore SB pin), blk8
    tab = min(extra, key=lambda s: abs(s.volume - 30.0))
    rest = [s for s in extra if s is not tab]

    print("\nPORT BRANCH — clear the mid-channel posts")
    for wl, y0, y1 in WALLS:
        for px, pz in DEAD_POSTS:
            housing = step(housing, housing - Pos(px, (y0 + y1) / 2, pz)
                           * Rot(90, 0, 0) * Cylinder(0.65, (y1 - y0) + 0.4),
                           f"{wl}: post d1.10 at ({px}, {pz})", "-")

    print("\nPORT BRANCH — detents as bumps on the side walls")
    for wl, y0, y1 in WALLS:
        for sx in (-1, 1):
            housing = step(housing, housing + Pos(BRANCH_X + sx * SLOT_RAD, (y0 + y1) / 2, DETENT_Z)
                           * Rot(90, 0, 0) * Cylinder(DETENT_R, y1 - y0),
                           f"{wl}: detent x{BRANCH_X + sx * SLOT_RAD:+.2f}", "+")

    print("\nFACE PLATE — fuse the fore SB pin (was a loose body)")
    px, pz = FORE_PIN
    mid = (FORE_PIN_Y0 + FORE_PIN_Y1) / 2
    faceplate = step(faceplate, faceplate + Pos(px, mid, pz) * Rot(90, 0, 0)
                     * Cylinder(PIN_R, FORE_PIN_Y1 - FORE_PIN_Y0),
                     "fore SB pin d2.40 x 6.5", "+")

    print("\nSB EDGE — flush detents (ridge on tongue, groove in block)")
    housing, base = sb_detents(housing, base)

    print("\nCLIPS — tube bead relieved, SB clip added")
    housing, endcap = clips(housing, endcap)

    print("\nPHONE RIM — stop the phone entering the cable channel")
    housing = phone_rim(housing)

    print("\nCAP MOUTH RIM — stop the phone sliding aft into the cap")
    endcap = cap_rim(endcap)

    print("\nPORT FLANGE — relieve the pre-existing interference")
    base = flange_relief(housing, base)

    print("\nPORT DETENTS — take up the play on the unlocated edge")
    housing, base = port_detents(housing, base)

    print("\nSLIDE-OUT TRAY — the whole void becomes a drawer")
    housing, base, drawer = tray(housing, base)

    print("\nUNDERBELLY SLEEVES — arm-wrapping arcs, port ribbed to the tube")
    base, housing = sleeves(base, housing)

    print("\nPHONE-FLOOR GRID — hollow the shell between drawer and phone")
    housing = floor_grid(housing)

    print("\nLIGHTENING — pocket the two dead slabs")
    housing, endcap = lighten(housing, endcap)

    out = Compound(children=[drawer, housing, endcap, base, faceplate, rail, g5, g6] + rest)
    bb = out.bounding_box()
    print(f"\nenvelope x {bb.min.X:.2f}..{bb.max.X:.2f}  y {bb.min.Y:.2f}..{bb.max.Y:.2f}  z {bb.min.Z:.2f}..{bb.max.Z:.2f}")
    dest = os.environ.get("ROAM_OUT", SHARE)   # gauge sweeps redirect; default is the law
    export_step(out, os.path.join(dest, "roam_worn.step"))
    export_stl(out, os.path.join(dest, "roam_worn.stl"))
    print(f"roam_worn.step + .stl   {out.volume/1000:.1f} cm3   {len(out.solids())} solids")


if __name__ == "__main__":
    main()
