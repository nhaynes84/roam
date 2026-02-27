// roam_case.scad — Main parametric enclosure for Roam wrist-mount controller
// Asymmetric dome, open bottom (closed by lid with M2 screws).
// Ridge offset toward inner (body) edge of forearm.
// Buttons on outer slope along forearm axis, OLED on outer slope.
//
// Orientation: X = forearm axis (positive = toward elbow)
//              Y = across forearm (positive = outer / away from body)
//              Z = up from forearm surface
//              Origin at center-bottom of case
//
// Mounting: velcro on lid bottom attaches to neoprene forearm band.
// Power: LiPo SHIM has built-in power button — no separate switch needed.

include <common.scad>

// ── Dome asymmetry ──
ridge_y_offset = -8;   // ridge toward inner edge (toward body)
ridge_height   = body_height;

// ── Layout offsets ──
// Pico+SHIM stack sits low in the cavity, raised just enough for wiring
pico_x_offset = 0;
pico_z_offset = 2;  // clearance above the open bottom for lid lip

battery_x_offset = 0;

// OLED on outer slope, readable while pronated
oled_x_offset  = -10;
oled_y_offset  = 10;   // outer slope
oled_z_offset  = body_height * 0.6;
oled_tilt      = 25;   // tilt outward to face user

// Buttons along X axis on outer slope
button_zone_y = ridge_y_offset + 8;

button_positions = [
    [ 24,  0],   // Index:  elbow end
    [  8,  2],   // Middle: tallest finger
    [ -8,  2],   // Ring:   similar reach
    [-24, -1],   // Pinky:  wrist end, shortest
];

// Screw posts — 4 corners. Posts go from bottom opening upward into dome.
// Heat-set inserts at the BOTTOM of each post (accessible from open bottom).
// Lid screws go up through lid into inserts.
screw_inset = 8;
screw_positions = [
    [ body_length/2 - screw_inset,  body_width/2 - screw_inset],
    [ body_length/2 - screw_inset, -body_width/2 + screw_inset],
    [-body_length/2 + screw_inset,  body_width/2 - screw_inset],
    [-body_length/2 + screw_inset, -body_width/2 + screw_inset],
];

// Post heights — shorter on inner side where dome is lower
screw_post_height_outer = 10;
screw_post_height_inner = 6;


// ════════════════════════════════════════════════════════════
// Modules
// ════════════════════════════════════════════════════════════

// Asymmetric dome — ridge along X, offset toward inner edge
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

// Inner cavity — extends below z=0 to ensure open bottom
module dome_inner() {
    translate([0, 0, -1])  // extend below bottom plane
        hull() {
            // Bottom opening — wide enough to access everything
            for (sx = [1, -1])
                for (sy = [1, -1])
                    translate([
                        sx * (body_length/2 - corner_radius - wall_thickness),
                        sy * (body_width/2 - corner_radius - wall_thickness),
                        0
                    ])
                        sphere(r = corner_radius - 0.5);

            // Upper cavity following dome shape
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

// Button well
module button_well(x, y) {
    translate([x, y, 0]) {
        translate([0, 0, body_height - button_well_depth - 3])
            cylinder(d = button_well_dia, h = button_well_depth + 15);
        translate([0, 0, -1])
            cylinder(d = button_diameter + print_tolerance * 2, h = body_height + 5);
    }
}

// Button line along forearm axis
module button_cluster() {
    for (pos = button_positions)
        button_well(pos[0], button_zone_y + pos[1]);
}

// OLED window cutout + recessed ledge
module oled_cutout() {
    translate([oled_x_offset, oled_y_offset, oled_z_offset])
        rotate([oled_tilt, 0, 0]) {
            translate([0, 0, -1])
                cube([oled_visible_width + 1, oled_visible_height + 1, wall_thickness + 2], center = true);
            translate([0, 0, -(wall_thickness + 0.5)])
                cube([oled_board_width + print_tolerance * 2,
                      oled_board_height + print_tolerance * 2,
                      oled_board_thick + 0.5], center = true);
        }
}

// OLED standoffs with ribs to nearest wall
module oled_standoffs() {
    standoff_h = 4;
    post_d = m2_insert_dia + 2;

    for (sx = [1, -1])
        for (sy = [1, -1]) {
            ox = oled_x_offset + sx * oled_hole_spacing_w/2;
            oy = oled_y_offset + sy * oled_hole_spacing_h/2 * cos(oled_tilt);
            oz = 1 + sy * oled_hole_spacing_h/2 * sin(oled_tilt);

            // Only create standoff if it's at a reasonable height
            if (oz > 0) {
                translate([ox, oy, oz])
                    rotate([oled_tilt, 0, 0])
                        difference() {
                            cylinder(d = post_d, h = standoff_h);
                            translate([0, 0, standoff_h - m2_insert_depth])
                                cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
                        }

                // Rib to wall
                hull() {
                    translate([ox, oy, oz])
                        cylinder(d = post_d, h = 0.5);
                    translate([ox, oy, 0.5])
                        cylinder(d = post_d + 1, h = 0.5);
                }
            }
        }
}

// USB-C port — wrist end, height accounts for SHIM+Pico stack
module usbc_cutout() {
    // USB-C is on top of the Pico, which sits on top of the SHIM
    usbc_z = pico_z_offset + shim_height + pico_height/2;
    translate([-body_length/2 - 1, 0, usbc_z])
        rotate([0, 90, 0])
            hull() {
                for (sx = [1, -1])
                    translate([0, sx * (usbc_width/2 - usbc_radius), 0])
                        cylinder(r = usbc_radius, h = wall_thickness + 2);
            }
}

// Pico+SHIM mounting standoffs — accommodate combined stack height
module pico_standoffs() {
    // Standoffs raise the SHIM to pico_z_offset above the bottom opening
    standoff_h = pico_z_offset;
    translate([pico_x_offset, 0, 0])
        for (sx = [1, -1])
            for (sy = [1, -1])
                translate([sx * pico_hole_spacing_l/2, sy * pico_hole_spacing_w/2, 0])
                    difference() {
                        cylinder(d = m2_insert_dia + 2.5, h = standoff_h);
                        // Insert from bottom (accessible from open bottom)
                        cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
                    }
}

// Screw posts — grow upward from bottom opening, inserts face downward
module screw_posts() {
    for (pos = screw_positions) {
        post_h = (pos[1] < 0) ? screw_post_height_inner : screw_post_height_outer;

        translate([pos[0], pos[1], 0])
            difference() {
                cylinder(d = m2_insert_dia + 3, h = post_h);
                // Heat-set insert at the BOTTOM — accessible from open bottom
                cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
            }
    }
}

// Ventilation slots in dome walls (sides, not bottom since bottom is open)
module vent_slots() {
    // Side vents near the base on outer edge
    num_vents = 4;
    for (i = [0 : num_vents - 1]) {
        vx = -((num_vents-1)/2 - i) * (vent_slot_length + vent_slot_spacing * 2);
        // Outer side vents
        translate([vx, body_width/2 - wall_thickness/2, 2])
            cube([vent_slot_length, wall_thickness + 0.2, vent_slot_width], center = true);
        // Inner side vents
        translate([vx, -(body_width/2 - wall_thickness/2), 2])
            cube([vent_slot_length, wall_thickness + 0.2, vent_slot_width], center = true);
    }
}


// ════════════════════════════════════════════════════════════
// Assembly
// ════════════════════════════════════════════════════════════

module roam_case() {
    difference() {
        union() {
            // Main shell (open bottom)
            difference() {
                dome_outer();
                dome_inner();
            }

            // Internal structure
            pico_standoffs();
            oled_standoffs();
            screw_posts();
        }

        // Cutouts
        button_cluster();
        oled_cutout();
        usbc_cutout();
        vent_slots();

        // Trim flat bottom (z=0 plane)
        translate([0, 0, -50])
            cube([200, 200, 100], center = true);
    }
}

roam_case();
