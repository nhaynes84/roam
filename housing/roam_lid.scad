// roam_lid.scad — Bottom lid for Roam wrist-mount controller
// Flat with slight concavity to match forearm curve.
// Velcro recess on bottom for attachment to neoprene forearm band.
// Mounts to case via M2 button head screws into heat-set inserts.

include <common.scad>

// ── Lid parameters ──
lid_thickness = 2.5;
lid_concavity_radius = 200;  // large radius for subtle forearm curve
lip_height    = 1.5;         // registration lip into case opening
lip_clearance = 0.15;        // per-side clearance for lip fit

// Screw positions — must match roam_case.scad
screw_inset = 8;
screw_positions = [
    [ body_length/2 - screw_inset,  body_width/2 - screw_inset],
    [ body_length/2 - screw_inset, -body_width/2 + screw_inset],
    [-body_length/2 + screw_inset,  body_width/2 - screw_inset],
    [-body_length/2 + screw_inset, -body_width/2 + screw_inset],
];


// ════════════════════════════════════════════════════════════
// Modules
// ════════════════════════════════════════════════════════════

// Base lid outline — rounded rectangle matching case footprint
module lid_outline_2d() {
    offset(r = corner_radius)
        offset(delta = -corner_radius)
            square([body_length, body_width], center = true);
}

// Registration lip — nests into case opening
module lip_outline_2d() {
    offset(r = corner_radius - wall_thickness/2)
        offset(delta = -(corner_radius - wall_thickness/2))
            square([body_length - wall_thickness * 2 - lip_clearance * 2,
                    body_width  - wall_thickness * 2 - lip_clearance * 2],
                   center = true);
}

// Concave bottom surface
module concave_bottom() {
    translate([0, 0, -lid_concavity_radius + lid_thickness * 0.3])
        sphere(r = lid_concavity_radius);
}

// Screw clearance holes with countersink for button head M2
module screw_holes() {
    for (pos = screw_positions) {
        translate([pos[0], pos[1], -0.1]) {
            cylinder(d = m2_screw_dia, h = lid_thickness + lip_height + 0.2);
            cylinder(d = m2_head_dia, h = m2_head_depth + 0.1);
        }
    }
}

// Velcro recess on bottom — rectangular pocket for adhesive velcro strip
// Hook velcro sits flush in this recess, grips loop velcro on neoprene band
module velcro_recess() {
    translate([0, 0, -0.1])
        linear_extrude(height = velcro_recess_depth + 0.1)
            offset(r = 2)
                offset(delta = -2)
                    square([velcro_patch_length, velcro_patch_width], center = true);
}

// Ventilation slots on lid
module lid_vent_slots() {
    num_vents = 4;
    start_x = -(num_vents - 1) * (vent_slot_length + vent_slot_spacing) / 2;

    for (i = [0 : num_vents - 1])
        for (sy = [1, -1])
            translate([
                start_x + i * (vent_slot_length + vent_slot_spacing),
                sy * (body_width/5),
                -0.1
            ])
                cube([vent_slot_length, vent_slot_width, lid_thickness + 0.2], center = true);
}


// ════════════════════════════════════════════════════════════
// Assembly
// ════════════════════════════════════════════════════════════

module roam_lid() {
    difference() {
        union() {
            // Main lid plate
            linear_extrude(height = lid_thickness)
                lid_outline_2d();

            // Registration lip on top
            translate([0, 0, lid_thickness - 0.01])
                linear_extrude(height = lip_height)
                    lip_outline_2d();
        }

        // Subtract features
        screw_holes();
        velcro_recess();
        lid_vent_slots();
    }
}

roam_lid();
