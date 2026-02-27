// roam_dome.scad — Ergonomic dome shell for Roam wrist-mount controller
// Asymmetric dome with button wells, OLED window, and screw bosses at rim.
// Prints rim-down, minimal/zero supports needed.
// Replaces roam_case.scad in the base-as-chassis architecture.

include <common.scad>

// ── Dome asymmetry ──
ridge_height = body_height;

// ── OLED on outer slope ──
oled_x_offset  = -10;
oled_y_offset  = 4;
oled_z_offset  = 9;
oled_tilt      = 20;


// ════════════════════════════════════════════════════════════
// Modules
// ════════════════════════════════════════════════════════════

// --- Dome shell ---

module dome_outer() {
    hull() {
        for (sx = [1, -1])
            for (sy = [1, -1])
                translate([
                    sx * (body_length/2 - corner_radius),
                    sy * (body_width/2 - corner_radius),
                    corner_radius
                ])
                    sphere(r = corner_radius);

        for (sx = [1, -1, 0])
            translate([
                sx * (body_length/3),
                ridge_y_offset,
                ridge_height - corner_radius
            ])
                scale([1, 0.6, 1])
                    sphere(r = corner_radius * 1.8);

        for (sx = [1, -1])
            translate([
                sx * (body_length/3),
                body_width/2 - corner_radius * 2,
                body_height * 0.45
            ])
                sphere(r = corner_radius * 1.2);

        for (sx = [1, -1])
            translate([
                sx * (body_length/3),
                -body_width/2 + corner_radius * 2,
                body_height * 0.35
            ])
                sphere(r = corner_radius);
    }
}

module dome_inner() {
    translate([0, 0, -1])
        hull() {
            for (sx = [1, -1])
                for (sy = [1, -1])
                    translate([
                        sx * (body_length/2 - corner_radius - wall_thickness),
                        sy * (body_width/2 - corner_radius - wall_thickness),
                        0
                    ])
                        sphere(r = corner_radius - 0.5);

            for (sx = [1, -1, 0])
                translate([
                    sx * (body_length/3),
                    ridge_y_offset,
                    ridge_height - wall_thickness - corner_radius * 2 + 1
                ])
                    scale([1, 0.6, 1])
                        sphere(r = corner_radius * 1.0);

            for (sx = [1, -1])
                translate([
                    sx * (body_length/3),
                    body_width/2 - corner_radius * 2 - wall_thickness,
                    body_height * 0.4 + 1
                ])
                    sphere(r = corner_radius * 0.8);

            for (sx = [1, -1])
                translate([
                    sx * (body_length/3),
                    -body_width/2 + corner_radius * 2 + wall_thickness,
                    body_height * 0.3 + 1
                ])
                    sphere(r = corner_radius - 0.5);
        }
}

// --- Buttons ---

module button_well(x, y) {
    translate([x, y, 0]) {
        // Well recess at dome surface
        translate([0, 0, body_height - button_well_depth - 3])
            cylinder(d = button_well_dia, h = button_well_depth + 15);
        // Through-hole for switch nub / button cap stem
        translate([0, 0, -1])
            cylinder(d = button_diameter + print_tolerance * 2, h = body_height + 5);
    }
}

module button_cluster() {
    for (pos = button_positions)
        button_well(pos[0], button_zone_y + pos[1]);
}

// --- OLED ---

// OLED window cutout through dome wall
module oled_cutout() {
    translate([oled_x_offset, oled_y_offset, oled_z_offset])
        rotate([oled_tilt, 0, 0])
            translate([0, 0, 3])
                cube([oled_visible_width + 1, oled_visible_height + 1, 10], center = true);
}

// OLED mount — 4 corner bosses with press-fit pegs (29x28mm spacing)
// 1.5mm pads directly against dome interior wall. No X cross-brace.
module oled_mount() {
    translate([oled_x_offset, oled_y_offset, oled_z_offset])
        rotate([oled_tilt, 0, 0])
            for (sx = [1, -1])
                for (sy = [1, -1])
                    translate([sx * oled_hole_spacing_w/2, sy * oled_hole_spacing_h/2,
                               -(wall_thickness + 1.5)]) {
                        // Boss pad
                        cylinder(d = 6, h = 1.5);
                        // Press-fit peg
                        cylinder(d = oled_hole_dia - 0.3, h = 1.5 + oled_board_thick);
                    }
}

// --- USB-C ---

// USB-C port cutout at wrist end — z position based on Pico stack height
module usbc_cutout() {
    usbc_z = pico_standoff_height + shim_height + pico_height/2;
    translate([-body_length/2 - 1, pico_y_offset, usbc_z])
        rotate([0, 90, 0])
            hull() {
                for (sx = [1, -1])
                    translate([0, sx * (usbc_width/2 - usbc_radius), 0])
                        cylinder(r = usbc_radius, h = wall_thickness + 2);
            }
}

// --- Ventilation ---

module vent_slots() {
    num_vents = 4;
    for (i = [0 : num_vents - 1]) {
        vx = -((num_vents-1)/2 - i) * (vent_slot_length + vent_slot_spacing * 2);
        for (sy = [1, -1])
            translate([vx, sy * (body_width/2 - wall_thickness/2), 2])
                cube([vent_slot_length, wall_thickness + 0.2, vent_slot_width], center = true);
    }
}

// --- Screw bosses at dome rim ---

// 4 cylinders (6.2mm OD, 6mm tall) at dome rim positions.
// Heat-set insert holes open at z=0 (rim face, mating with base plate).
// Print on build plate when dome is printed rim-down — no overhang.
module dome_screw_bosses() {
    boss_od = 6.2;
    boss_height = 6;

    for (pos = screw_positions)
        translate([pos[0], pos[1], 0])
            difference() {
                cylinder(d = boss_od, h = boss_height);
                translate([0, 0, -0.1])
                    cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
            }
}


// ════════════════════════════════════════════════════════════
// Assembly
// ════════════════════════════════════════════════════════════

module roam_dome() {
    difference() {
        union() {
            difference() {
                dome_outer();
                dome_inner();
            }
            oled_mount();
            dome_screw_bosses();
        }

        button_cluster();
        oled_cutout();
        usbc_cutout();
        vent_slots();

        // Trim flat bottom at z=0 (dome rim)
        translate([0, 0, -50])
            cube([200, 200, 100], center = true);
    }
}

roam_dome();
