#!/usr/bin/env python3
"""Parametric spring button — living hinge cantilever design.

Recreates the dual spring button from the Springbutton_preview STLs as a
fully parametric STEP solid. Two button caps sit on cantilever spring arms
that provide tactile return force.

Usage:
    source housing/.venv/bin/activate
    python housing/lib/spring_button.py [--single] [--cap-width W] [--cap-depth D]

Anatomy (cross-section, Y axis):
    ┌─────────┐  ← button cap (presses down)
    │  cap    │
    ├─────────┤  ← cap base
    │         ├──────────────┐
    │  wall   │  spring arm  │ ← thin cantilever (living hinge)
    │         ├──────────────┘
    └─────────┴──────────────── ← base plate (anchored to frame)

The spring arm deflects when the cap is pressed, providing return force.
Thinner arm = softer press. Print in PETG or nylon for best spring life.

All dimensions in mm. Origin at center of base plate.
"""

import sys
from pathlib import Path

# Add parent to path for shared venv
sys.path.insert(0, str(Path(__file__).parent.parent))

from build123d import *


def make_spring_button(
    # Button cap
    cap_width=12.0,       # X dimension of each cap
    cap_depth=7.0,        # Y dimension of each cap
    cap_height=2.0,       # how far cap protrudes above base
    cap_fillet=0.8,       # top edge fillet
    # Spring arm
    arm_length=8.0,       # Y span of cantilever arm
    arm_thickness=1.0,    # Z thickness of spring arm (controls stiffness)
    arm_width=None,       # X width of arm (defaults to cap_width - 2)
    # Base plate
    base_thickness=0.5,   # Z thickness of base surround
    base_margin=2.0,      # extra material around the outside
    # Dual layout
    dual=True,            # two buttons side by side
    gap=3.0,              # X gap between button caps (dual only)
    # Wall
    wall_thickness=1.5,   # wall connecting cap to arm
):
    """Build a spring button (single or dual) as a Solid."""

    if arm_width is None:
        arm_width = cap_width - 2.0

    total_height = base_thickness + cap_height

    # Total Y: cap_depth + wall + arm_length + base_margin
    total_depth = cap_depth + wall_thickness + arm_length + base_margin

    if dual:
        total_width = cap_width * 2 + gap + base_margin * 2
    else:
        total_width = cap_width + base_margin * 2

    # === Base plate ===
    base = extrude(
        RectangleRounded(total_width, total_depth, radius=1.0),
        amount=base_thickness,
    )

    # Button positions (centered in X for single, offset for dual)
    if dual:
        btn_x_positions = [-(cap_width + gap) / 2, (cap_width + gap) / 2]
    else:
        btn_x_positions = [0]

    # Y layout: cap at -Y side, arm at +Y side
    cap_y_center = -(total_depth / 2) + base_margin + cap_depth / 2
    arm_y_start = cap_y_center + cap_depth / 2
    arm_y_center = arm_y_start + arm_length / 2

    for bx in btn_x_positions:
        # === Button cap (full height block) ===
        cap = Pos(bx, cap_y_center, 0) * extrude(
            RectangleRounded(cap_width, cap_depth, radius=1.0),
            amount=total_height,
        )
        base = base.fuse(cap)

        # === Wall section (connects cap base to arm) ===
        wall = Pos(bx, arm_y_start - wall_thickness / 2, 0) * Box(
            arm_width, wall_thickness, base_thickness + arm_thickness,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        base = base.fuse(wall)

        # === Spring arm (cantilever) ===
        arm = Pos(bx, arm_y_center + wall_thickness / 2, 0) * Box(
            arm_width, arm_length, arm_thickness,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        base = base.fuse(arm)

    # === Fillet the cap top edges for comfort ===
    # Find top face edges for filleting
    try:
        top_edges = base.edges().filter_by(
            lambda e: e.center().Z > total_height - 0.1
        )
        if len(top_edges) > 0:
            base = base.fillet(cap_fillet, top_edges)
    except Exception:
        pass  # Skip fillet if geometry doesn't support it

    return base


def make_spring_button_frame(
    # Must match button dimensions
    cap_width=12.0,
    cap_depth=7.0,
    cap_height=2.0,
    # Frame
    frame_wall=2.0,       # wall thickness around cutout
    frame_height=None,    # defaults to cap_height + base_thickness
    base_thickness=0.5,
    # Dual layout
    dual=True,
    gap=3.0,
    base_margin=2.0,
    wall_thickness=1.5,
    arm_length=8.0,
):
    """Build the frame/housing that the spring button sits in."""

    total_depth = cap_depth + wall_thickness + arm_length + base_margin
    if dual:
        total_width = cap_width * 2 + gap + base_margin * 2
    else:
        total_width = cap_width + base_margin * 2

    if frame_height is None:
        frame_height = cap_height + base_thickness

    # Frame outer dimensions (larger than button piece)
    frame_w = total_width + frame_wall * 2
    frame_d = total_depth + frame_wall * 2

    frame = extrude(
        RectangleRounded(frame_w, frame_d, radius=2.0),
        amount=frame_height,
    )

    # Inner cavity for the button piece
    cavity = Pos(0, 0, -0.1) * extrude(
        RectangleRounded(total_width + 0.4, total_depth + 0.4, radius=1.0),
        amount=frame_height - base_thickness + 0.1,
    )
    frame = frame.cut(cavity)

    # Button cap cutouts (through the top)
    cap_y_center = -(total_depth / 2) + base_margin + cap_depth / 2

    if dual:
        btn_x_positions = [-(cap_width + gap) / 2, (cap_width + gap) / 2]
    else:
        btn_x_positions = [0]

    for bx in btn_x_positions:
        cutout = Pos(bx, cap_y_center, frame_height - cap_height - 0.1) * extrude(
            RectangleRounded(cap_width + 0.4, cap_depth + 0.4, radius=1.0),
            amount=cap_height + 0.2,
        )
        frame = frame.cut(cutout)

    result = frame
    if hasattr(result, 'solid'):
        result = result.solid()
    return result


STEP_DIR = Path(__file__).parent.parent / "step"


def main():
    STEP_DIR.mkdir(exist_ok=True)

    single = "--single" in sys.argv

    # Parse optional dimensions
    kwargs = {}
    for i, arg in enumerate(sys.argv):
        if arg == "--cap-width" and i + 1 < len(sys.argv):
            kwargs["cap_width"] = float(sys.argv[i + 1])
        if arg == "--cap-depth" and i + 1 < len(sys.argv):
            kwargs["cap_depth"] = float(sys.argv[i + 1])
        if arg == "--arm-thickness" and i + 1 < len(sys.argv):
            kwargs["arm_thickness"] = float(sys.argv[i + 1])
        if arg == "--cap-height" and i + 1 < len(sys.argv):
            kwargs["cap_height"] = float(sys.argv[i + 1])

    kwargs["dual"] = not single

    print(f"Building spring button ({'single' if single else 'dual'})...")
    btn = make_spring_button(**kwargs)
    btn_path = STEP_DIR / ("spring_button_single.step" if single else "spring_button_dual.step")
    export_step(btn, str(btn_path))
    print(f"  → {btn_path}")

    print(f"Building frame...")
    frame = make_spring_button_frame(**kwargs)
    frame_path = STEP_DIR / ("spring_frame_single.step" if single else "spring_frame_dual.step")
    export_step(frame, str(frame_path))
    print(f"  → {frame_path}")

    print("Done.")


if __name__ == "__main__":
    main()
