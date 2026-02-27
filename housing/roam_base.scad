// roam_base.scad — Base plate / electronics chassis for Roam wrist-mount controller
// Flat plate with all mounting features on top. Prints flat, zero supports.
// z=0 = arm-facing bottom (velcro side). Features mount upward from z=base_plate_thick.
// Replaces roam_lid.scad in the base-as-chassis architecture.

include <common.scad>

// ── Lip ──
lip_height    = 1.5;
lip_clearance = 0.15;  // per-side clearance for lip fit
lip_wall      = 1.2;   // wall thickness of registration lip

// ── Switch pedestal ──
pedestal_size      = 10;
switch_pocket_size = 6.2;   // 6mm switch + 0.2mm clearance
switch_pocket_depth = 2;    // press-fit depth


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

// Registration lip — 1.5mm tall perimeter wall on top of base plate
// Inset by wall_thickness to nest inside dome rim opening.
// Notches for USB-C at wrist end (-x) and I2C cable pass-through (+y).
module registration_lip() {
    usbc_notch_w = usbc_width + 4;
    cable_notch_w = 8;

    outer_l = body_length - wall_thickness * 2 - lip_clearance * 2;
    outer_w = body_width  - wall_thickness * 2 - lip_clearance * 2;
    inner_l = outer_l - lip_wall * 2;
    inner_w = outer_w - lip_wall * 2;

    translate([0, 0, base_plate_thick - 0.01])
        linear_extrude(height = lip_height)
            difference() {
                // Outer profile — fits inside dome rim
                offset(r = corner_radius - wall_thickness)
                    offset(delta = -(corner_radius - wall_thickness))
                        square([outer_l, outer_w], center = true);

                // Inner cutout — makes it a thin perimeter wall
                offset(r = corner_radius - wall_thickness - lip_wall)
                    offset(delta = -(corner_radius - wall_thickness - lip_wall))
                        square([inner_l, inner_w], center = true);

                // USB-C cable notch at wrist end (-x)
                translate([-(body_length/2), -usbc_notch_w/2])
                    square([wall_thickness * 2, usbc_notch_w]);

                // I2C cable pass-through notch (toward outer slope, +y)
                translate([-cable_notch_w/2, body_width/2 - wall_thickness * 2 - lip_wall])
                    square([cable_notch_w, lip_wall * 2]);
            }
}

// Pico standoffs — 4 M2 bosses (3mm tall) at Pico hole spacing
// Heat-set inserts on top receive screws through SHIM+Pico mounting holes
module pico_standoffs() {
    translate([pico_x_offset, pico_y_offset, base_plate_thick])
        for (sx = [1, -1])
            for (sy = [1, -1])
                translate([sx * pico_hole_spacing_l/2, sy * pico_hole_spacing_w/2, 0])
                    difference() {
                        cylinder(d = m2_insert_dia + 2.5, h = pico_standoff_height);
                        translate([0, 0, pico_standoff_height - m2_insert_depth])
                            cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
                    }
}

// Switch pedestals — 4 individual 10x10mm blocks, 14mm tall, at button positions
// Each has a 6.2mm pocket on top for press-fitting a 6x6mm tactile switch
module switch_pedestals() {
    translate([0, 0, base_plate_thick])
        for (pos = button_positions)
            translate([pos[0], button_zone_y + pos[1], 0])
                difference() {
                    translate([-pedestal_size/2, -pedestal_size/2, 0])
                        cube([pedestal_size, pedestal_size, switch_pedestal_height]);
                    translate([-switch_pocket_size/2, -switch_pocket_size/2,
                               switch_pedestal_height - switch_pocket_depth])
                        cube([switch_pocket_size, switch_pocket_size,
                              switch_pocket_depth + 0.1]);
                }
}

// Battery: 502535 LiPo (35x25x5mm) secured with foam tape during assembly.
// No cradle — the battery footprint overlaps 3 of 4 switch pedestals at any
// viable position on this plate. Battery sits in the y>0 zone between pedestals
// and dome ceiling, held laterally by surrounding structure.

// Screw holes — 4 countersunk M2 through-holes from bottom
// Hidden by velcro patch on arm-facing side
module screw_holes() {
    for (pos = screw_positions)
        translate([pos[0], pos[1], -0.1]) {
            // Through-hole for M2 screw
            cylinder(d = m2_screw_dia, h = base_plate_thick + 0.2);
            // Countersink for button head (hidden under velcro)
            cylinder(d = m2_head_dia, h = m2_head_depth + 0.1);
        }
}

// Velcro recess — 70x38mm, 1mm deep on bottom face (z=0 side)
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
        union() {
            base_plate();
            registration_lip();
            pico_standoffs();
            switch_pedestals();
        }

        screw_holes();
        velcro_recess();
    }
}

roam_base();
