// switch_slot.scad — Slide switch actuator slot cutout
// Solved component: rounded rectangle through wall for MSK-12C02 style switch.
//
// Usage:
//   include <common.scad>
//   use <lib/switch_slot.scad>
//   switch_slot(cx, cz, face);
//
// Parameters:
//   cx, cz   — center position on the wall
//   face     — "inner" (Y-) or "outer" (Y+) wall
//
// Default dimensions match MSK-12C02: 4mm wide × 2mm tall, 0.5mm corner radius

include <common.scad>

module switch_slot(cx=0, cz=0, face="inner",
                   slot_w=4.0, slot_h=2.0, slot_r=0.5) {
    // Determine wall Y position and rotation
    wy = (face == "inner") ? wall_inner : wall_outer;
    dir = (face == "inner") ? -1 : 1;

    translate([cx, wy - dir * EPS, cz])
        rotate([-90 * dir, 0, 0])
            hull() {
                for (sx = [1, -1])
                    translate([sx * (slot_w/2 - slot_r), 0, 0])
                        for (sz = [1, -1])
                            translate([0, 0, sz * (slot_h/2 - slot_r)])
                                cylinder(r = slot_r, h = wall_thickness + 2 * EPS);
            }
}
