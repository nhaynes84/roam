// roam_dome.scad — Ergonomic dome shell for Roam wrist-mount controller
// Asymmetric dome with button wells, OLED window, and screw bosses at rim.
// Prints rim-down, minimal/zero supports needed.
// Replaces roam_case.scad in the base-as-chassis architecture.

include <common.scad>

// ── Dome asymmetry ──
ridge_height = body_height;

// ── OLED on outer slope ──
oled_x_offset  = -10;
oled_y_offset  = 10;
oled_z_offset  = 15;
oled_tilt      = 25;


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

// OLED window cutout through dome wall — deep cut to fully penetrate curved surface
module oled_cutout() {
    translate([oled_x_offset, oled_y_offset, oled_z_offset])
        rotate([oled_tilt, 0, 0])
            cube([oled_visible_width + 1, oled_visible_height + 1, 20], center = true);
}

// OLED mount — 4 corner bosses anchored to dome wall via intersection,
// with press-fit pegs protruding inward for board mounting.
// Everything clipped to dome_outer envelope to prevent protrusion above dome surface.
module oled_mount() {
    intersection() {
        dome_outer();
        union() {
            // Boss pads — tall cylinders spanning through dome wall at corner positions
            translate([oled_x_offset, oled_y_offset, oled_z_offset])
                rotate([oled_tilt, 0, 0])
                    for (sx = [1, -1])
                        for (sy = [1, -1])
                            translate([sx * oled_hole_spacing_w/2,
                                       sy * oled_hole_spacing_h/2, -12])
                                cylinder(d = 7, h = 16);

            // Press-fit pegs — protrude inward from boss pads
            translate([oled_x_offset, oled_y_offset, oled_z_offset])
                rotate([oled_tilt, 0, 0])
                    for (sx = [1, -1])
                        for (sy = [1, -1])
                            translate([sx * oled_hole_spacing_w/2,
                                       sy * oled_hole_spacing_h/2,
                                       -(wall_thickness + 1.5)])
                                cylinder(d = oled_hole_dia - 0.3, h = 1.5 + oled_board_thick);
        }
    }
}

// --- USB-C ---

// USB-C port cutout at wrist end — z position based on Pico stack height.
// NOTE: dome is only ~10mm tall at wrist end (x=-45). With pico_standoff_height=3
// the port center is at z≈11.9 which may exceed dome height there.
// Extended cutout reaches from z=0 upward to catch available wall material.
module usbc_cutout() {
    usbc_z = pico_standoff_height + shim_height + pico_height/2;
    // Standard port-shaped cutout at calculated height
    translate([-body_length/2 - 1, pico_y_offset, usbc_z])
        rotate([0, 90, 0])
            hull() {
                for (sx = [1, -1])
                    translate([0, sx * (usbc_width/2 - usbc_radius), 0])
                        cylinder(r = usbc_radius, h = wall_thickness + 2);
            }
    // Extended vertical slot to ensure opening reaches dome edge
    translate([-body_length/2 - 1, pico_y_offset - usbc_width/2, 0])
        cube([wall_thickness + 2, usbc_width, usbc_z + usbc_radius]);
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
// Each boss has a connecting rib to the nearest dome wall (y-direction)
// to ensure solid structural connection to the shell.
module dome_screw_bosses() {
    boss_od = 6.2;
    boss_height = 6;
    rib_width = 2;

    for (pos = screw_positions) {
        // Boss cylinder with heat-set insert hole
        translate([pos[0], pos[1], 0])
            difference() {
                cylinder(d = boss_od, h = boss_height);
                translate([0, 0, -0.1])
                    cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
            }

        // Connecting rib from boss to nearest dome wall (shortest path in y)
        y_wall = (pos[1] > 0)
            ? (body_width/2 - wall_thickness/2)
            : -(body_width/2 - wall_thickness/2);
        hull() {
            translate([pos[0], pos[1], 0])
                cylinder(d = rib_width, h = boss_height);
            translate([pos[0], y_wall, 0])
                cylinder(d = rib_width, h = boss_height);
        }
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
