// roam_base.scad — Base plate for Roam wrist-mount controller
// Just the plate, screw holes, and velcro recess.
// All interior mounting (pedestals, standoffs, lip) left for manual design.

include <common.scad>


// ════════════════════════════════════════════════════════════
// Modules
// ════════════════════════════════════════════════════════════

// Base plate — 2.5mm thick rounded rectangle (90x50mm)
module base_plate() {
    linear_extrude(height = base_plate_thick)
        offset(r = corner_radius)
            offset(delta = -corner_radius)
                square([body_length, body_width], center = true);
}

// Screw holes — 4 countersunk M2 through-holes from bottom
module screw_holes() {
    for (pos = screw_positions)
        translate([pos[0], pos[1], -0.1]) {
            cylinder(d = m2_screw_dia, h = base_plate_thick + 0.2);
            cylinder(d = m2_head_dia, h = m2_head_depth + 0.1);
        }
}

// Velcro recess — 70x38mm, 1mm deep on bottom face
module velcro_recess() {
    translate([0, 0, -0.1])
        linear_extrude(height = velcro_recess_depth + 0.1)
            offset(r = 2)
                offset(delta = -2)
                    square([velcro_patch_length, velcro_patch_width], center = true);
}


// ════════════════════════════════════════════════════════════
// Assembly
// ════════════════════════════════════════════════════════════

module roam_base() {
    difference() {
        base_plate();
        screw_holes();
        velcro_recess();
    }
}

roam_base();
