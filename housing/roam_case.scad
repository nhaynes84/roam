// roam_case.scad — Main parametric enclosure for Roam wrist-mount controller
// Asymmetric dome: ridge offset toward inner (body) edge of forearm.
// Gentle outer slope holds OLED screen (visible while pronated).
// Steeper inner slope holds buttons in a line along the forearm axis.
//
// Orientation: X = forearm axis (positive = toward elbow)
//              Y = across forearm (positive = outer / away from body)
//              Z = up from forearm surface
//              Origin at center-bottom of case
//
// Wearing: inside of RIGHT forearm, midway up. Left hand makes T-shape
// to reach buttons. User supinates to expose buttons, pronates to read screen.

include <common.scad>

// ── Dome asymmetry ──
// Ridge offset toward inner edge (negative Y = toward body)
ridge_y_offset = -8;   // mm toward inner edge
ridge_height   = body_height;  // peak height at ridge line

// ── Layout offsets ──
// Pico sits centered lengthwise, low in the cavity
pico_x_offset = 0;
pico_z_offset = wall_thickness + 1;

// Battery next to Pico
battery_x_offset = 0;
battery_z_offset = wall_thickness + 0.5;

// OLED on the outer slope (positive Y), toward wrist end for glanceability.
// Readable while pronated — the outer slope faces toward you.
oled_x_offset  = -10;  // slight wrist bias
oled_y_offset  = 10;   // on outer slope, away from ridge/buttons
oled_z_offset  = body_height * 0.6;  // mid-height on outer slope
oled_tilt      = 25;   // tilt outward (around X axis) to face user when pronated

// Buttons in a line along X axis (forearm direction), on the inner slope.
// Left hand fingers drape over ridge, tips land on inner slope.
// Index (elbow) → Pinky (wrist), with finger-length Y curve.
button_zone_y = ridge_y_offset - 6;  // on inner slope, past the ridge

// Button positions: [x_offset, y_adjust] from button_zone center
// X spacing ~16mm along forearm, Y follows finger-length arc
button_positions = [
    [ 24,  0],   // Index:  elbow end, longest reach
    [  8,  2],   // Middle: slight elbow, tallest finger reaches furthest over ridge
    [ -8,  2],   // Ring:   slight wrist, similar reach to middle
    [-24, -1],   // Pinky:  wrist end, shortest — doesn't reach as far over ridge
];

// Band slot positions (along X axis, near ends)
band_elbow_x =  (body_length/2 - band_width/2 - 3);
band_wrist_x = -(body_length/2 - band_width/2 - 3);

// Slide switch — on elbow END wall (accessible, out of the way)
switch_x_offset = body_length/2;   // elbow end face
switch_y_offset = 0;               // centered on end wall
switch_z_offset = body_height * 0.3;

// Case screw post positions (4 corners, inset)
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

// Asymmetric dome — ridge runs along X axis, offset toward inner edge.
// Outer slope (positive Y) is gentle for screen visibility.
// Inner slope (negative Y) is steeper for finger grip.
module dome_outer() {
    hull() {
        // Four base corners
        for (sx = [1, -1])
            for (sy = [1, -1])
                translate([
                    sx * (body_length/2 - corner_radius),
                    sy * (body_width/2 - corner_radius),
                    corner_radius
                ])
                    sphere(r = corner_radius);

        // Ridge line — the peak, offset toward inner edge, runs along X
        for (sx = [1, -1, 0])
            translate([
                sx * (body_length/3),
                ridge_y_offset,
                ridge_height - corner_radius
            ])
                scale([1, 0.6, 1])
                    sphere(r = corner_radius * 1.8);

        // Outer slope control — lower, on the screen side
        for (sx = [1, -1])
            translate([
                sx * (body_length/3),
                body_width/2 - corner_radius * 2,
                body_height * 0.45
            ])
                sphere(r = corner_radius * 1.2);

        // Inner slope control — mid-height, steeper drop to inner edge
        for (sx = [1, -1])
            translate([
                sx * (body_length/3),
                -body_width/2 + corner_radius * 2,
                body_height * 0.35
            ])
                sphere(r = corner_radius);
    }
}

// Inner cavity — follows outer dome shape with wall offset
module dome_inner() {
    translate([0, 0, wall_thickness])
        hull() {
            for (sx = [1, -1])
                for (sy = [1, -1])
                    translate([
                        sx * (body_length/2 - corner_radius - wall_thickness),
                        sy * (body_width/2 - corner_radius - wall_thickness),
                        corner_radius
                    ])
                        sphere(r = corner_radius - 0.5);

            // Inner ridge
            for (sx = [1, -1, 0])
                translate([
                    sx * (body_length/3),
                    ridge_y_offset,
                    ridge_height - wall_thickness - corner_radius * 2
                ])
                    scale([1, 0.6, 1])
                        sphere(r = corner_radius * 1.0);

            // Inner outer-slope
            for (sx = [1, -1])
                translate([
                    sx * (body_length/3),
                    body_width/2 - corner_radius * 2 - wall_thickness,
                    body_height * 0.4
                ])
                    sphere(r = corner_radius * 0.8);

            // Inner inner-slope
            for (sx = [1, -1])
                translate([
                    sx * (body_length/3),
                    -body_width/2 + corner_radius * 2 + wall_thickness,
                    body_height * 0.3
                ])
                    sphere(r = corner_radius - 0.5);
        }
}

// Button well — recessed cylindrical well in dome surface
module button_well(x, y) {
    translate([x, y, 0]) {
        // Well recess — cuts from dome surface inward
        translate([0, 0, body_height - button_well_depth - 3])
            cylinder(d = button_well_dia, h = button_well_depth + 15);
        // Through-hole for switch stem / button cap
        translate([0, 0, wall_thickness - 0.1])
            cylinder(d = button_diameter + print_tolerance * 2, h = body_height + 5);
    }
}

// Button line along forearm axis on inner slope
module button_cluster() {
    for (pos = button_positions)
        button_well(pos[0], button_zone_y + pos[1]);
}

// OLED window cutout + recessed ledge — on outer slope
module oled_cutout() {
    translate([oled_x_offset, oled_y_offset, oled_z_offset])
        rotate([oled_tilt, 0, 0]) {
            // Visible window
            translate([0, 0, -1])
                cube([oled_visible_width + 1, oled_visible_height + 1, wall_thickness + 2], center = true);

            // Recessed ledge for PCB
            translate([0, 0, -(wall_thickness + 0.5)])
                cube([oled_board_width + print_tolerance * 2,
                      oled_board_height + print_tolerance * 2,
                      oled_board_thick + 0.5], center = true);
        }
}

// OLED mounting standoffs with support ribs to floor
module oled_standoffs() {
    standoff_h = 4;
    post_d = m2_insert_dia + 2;

    for (sx = [1, -1])
        for (sy = [1, -1]) {
            ox = oled_x_offset + sx * oled_hole_spacing_w/2;
            oy = oled_y_offset + sy * oled_hole_spacing_h/2 * cos(oled_tilt);
            oz = wall_thickness + sy * oled_hole_spacing_h/2 * sin(oled_tilt);

            translate([ox, oy, oz])
                rotate([oled_tilt, 0, 0])
                    difference() {
                        cylinder(d = post_d, h = standoff_h);
                        translate([0, 0, standoff_h - m2_insert_depth])
                            cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
                    }

            // Support rib to floor
            hull() {
                translate([ox, oy, oz])
                    cylinder(d = post_d, h = 0.5);
                translate([ox, oy, wall_thickness])
                    cylinder(d = post_d + 1, h = 0.5);
            }
        }
}

// USB-C port cutout — wrist end
module usbc_cutout() {
    translate([-body_length/2 - 1, 0, wall_thickness + pico_height/2 + 2])
        rotate([0, 90, 0])
            hull() {
                for (sx = [1, -1])
                    translate([0, sx * (usbc_width/2 - usbc_radius), 0])
                        cylinder(r = usbc_radius, h = wall_thickness + 2);
            }
}

// Pico 2 W mounting standoffs
module pico_standoffs() {
    standoff_h = pico_z_offset - wall_thickness + 0.5;
    translate([pico_x_offset, 0, wall_thickness])
        for (sx = [1, -1])
            for (sy = [1, -1])
                translate([sx * pico_hole_spacing_l/2, sy * pico_hole_spacing_w/2, 0])
                    difference() {
                        cylinder(d = m2_insert_dia + 2.5, h = standoff_h);
                        translate([0, 0, standoff_h - m2_insert_depth])
                            cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
                    }
}

// Battery compartment recess in floor
module battery_compartment() {
    translate([battery_x_offset, 0, wall_thickness - 0.1])
        cube([battery_length + battery_clearance * 2,
              battery_width + battery_clearance * 2,
              battery_height + battery_clearance], center = true);
}

// Band slot — bridge loop for strap
module band_slot(x_pos) {
    slot_h = band_thickness + band_slot_clearance * 2;
    slot_total_w = band_width + band_slot_clearance * 2;
    bridge_thick = wall_thickness;

    translate([x_pos, 0, 0]) {
        translate([0, 0, -0.1])
            cube([bridge_thick + 2, slot_total_w, slot_h + wall_thickness], center = true);

        for (sy = [1, -1])
            translate([0, sy * (body_width/2), slot_h/2 + wall_thickness/2])
                rotate([0, 90, 0])
                    cylinder(d = slot_h, h = bridge_thick + 4, center = true);
    }
}

// Ventilation slots on bottom
module vent_slots() {
    num_vents = 5;
    start_x = -(num_vents - 1) * vent_slot_spacing / 2;

    for (i = [0 : num_vents - 1])
        for (sy = [1, -1])
            translate([
                start_x + i * (vent_slot_length + vent_slot_spacing),
                sy * (body_width/4),
                -0.1
            ])
                cube([vent_slot_length, vent_slot_width, wall_thickness + 0.2], center = true);
}

// Screw posts for lid attachment
module screw_posts() {
    post_h = inner_height * 0.6;
    for (pos = screw_positions)
        translate([pos[0], pos[1], wall_thickness])
            difference() {
                cylinder(d = m2_insert_dia + 3, h = post_h);
                translate([0, 0, post_h - m2_insert_depth])
                    cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
            }
}

// Slide switch cutout — on elbow end wall
module switch_cutout() {
    translate([switch_x_offset, switch_y_offset, switch_z_offset]) {
        // Slider slot through end wall
        rotate([0, 90, 0])
            translate([0, 0, -wall_thickness - 1])
                cube([switch_slot_height, switch_slot_length, wall_thickness + 2],
                     center = true);

        // Internal cavity for switch body
        rotate([0, 90, 0])
            translate([0, 0, -wall_thickness/2])
                cube([switch_body_height + 1,
                      switch_body_length + 1,
                      switch_body_width + 1],
                     center = true);

        // Indicator recesses — above and below the slot on end wall
        // Top recess (ON / green)
        translate([0, -(switch_slot_length/2 + switch_indicator_dia/2 + 0.5), 0])
            rotate([0, 90, 0])
                translate([0, 0, -0.1])
                    cylinder(d = switch_indicator_dia, h = switch_indicator_depth + 0.1);

        // Bottom recess (OFF / red)
        translate([0, (switch_slot_length/2 + switch_indicator_dia/2 + 0.5), 0])
            rotate([0, 90, 0])
                translate([0, 0, -0.1])
                    cylinder(d = switch_indicator_dia, h = switch_indicator_depth + 0.1);
    }
}


// ════════════════════════════════════════════════════════════
// Assembly
// ════════════════════════════════════════════════════════════

module roam_case() {
    difference() {
        union() {
            // Main shell
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
        switch_cutout();
        band_slot(band_elbow_x);
        band_slot(band_wrist_x);
        vent_slots();

        // Trim flat bottom
        translate([0, 0, -50])
            cube([200, 200, 100], center = true);
    }
}

roam_case();
