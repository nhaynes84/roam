// roam_lid.scad — Bottom lid for Roam wrist-mount controller
// Flat with slight concavity to match forearm curve
// Mounts via M2 screws into heat-set inserts in case

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

// Band slot positions — must match roam_case.scad
band_elbow_x =  (body_length/2 - band_width/2 - 3);
band_wrist_x = -(body_length/2 - band_width/2 - 3);

// TPU pad zone dimensions (for marking)
tpu_pad_length = 30;
tpu_pad_width  = 20;


// ════════════════════════════════════════════════════════════
// Modules
// ════════════════════════════════════════════════════════════

// Base lid outline — rounded rectangle matching case footprint
module lid_outline_2d() {
    offset(r = corner_radius)
        offset(delta = -corner_radius)
            square([body_length, body_width], center = true);
}

// Registration lip — smaller outline that nests into case opening
module lip_outline_2d() {
    offset(r = corner_radius - wall_thickness/2)
        offset(delta = -(corner_radius - wall_thickness/2))
            square([body_length - wall_thickness * 2 - lip_clearance * 2,
                    body_width  - wall_thickness * 2 - lip_clearance * 2],
                   center = true);
}

// Concave bottom surface — intersection with inverted sphere
module concave_bottom() {
    translate([0, 0, -lid_concavity_radius + lid_thickness * 0.3])
        sphere(r = lid_concavity_radius);
}

// Screw clearance holes with countersink
module screw_holes() {
    for (pos = screw_positions) {
        translate([pos[0], pos[1], -0.1]) {
            // Through-hole
            cylinder(d = m2_screw_dia, h = lid_thickness + lip_height + 0.2);
            // Countersink on bottom
            cylinder(d = m2_head_dia, h = m2_head_depth + 0.1);
        }
    }
}

// Band slot pass-through — matching case band slots
module lid_band_slot(x_pos) {
    slot_total_w = band_width + band_slot_clearance * 2;
    translate([x_pos, 0, -0.1])
        cube([wall_thickness + 2,
              slot_total_w,
              lid_thickness + lip_height + 0.2],
             center = true);
}

// TPU pad zone markers — shallow engraved rectangles on bottom
// Print these zones separately in TPU for comfort
module tpu_pad_markers() {
    marker_depth = 0.4;

    // Central pad
    translate([0, 0, -0.1])
        linear_extrude(height = marker_depth)
            offset(r = 2)
                offset(delta = -2)
                    square([tpu_pad_length, tpu_pad_width], center = true);

    // Two smaller pads near band slots
    for (sx = [1, -1])
        translate([sx * 28, 0, -0.1])
            linear_extrude(height = marker_depth)
                offset(r = 1.5)
                    offset(delta = -1.5)
                        square([15, tpu_pad_width], center = true);
}

// Ventilation slots on lid (matching case)
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
            // Main lid plate with concave bottom
            intersection() {
                linear_extrude(height = lid_thickness)
                    lid_outline_2d();
                concave_bottom();
            }

            // Flat fill to full lid thickness (connects to lip above)
            linear_extrude(height = lid_thickness)
                lid_outline_2d();

            // Registration lip on top
            translate([0, 0, lid_thickness - 0.01])
                linear_extrude(height = lip_height)
                    lip_outline_2d();
        }

        // Subtract features
        screw_holes();
        lid_band_slot(band_elbow_x);
        lid_band_slot(band_wrist_x);
        tpu_pad_markers();
        lid_vent_slots();
    }
}

roam_lid();
