// roam_case.scad — Main parametric enclosure for Roam wrist-mount controller
// Asymmetric dome: ridge offset toward inner (body) edge of forearm.
// Gentle outer slope holds OLED screen (visible while pronated).
// Buttons on outer slope along forearm axis, fingers approach from outer edge.
//
// Orientation: X = forearm axis (positive = toward elbow)
//              Y = across forearm (positive = outer / away from body)
//              Z = up from forearm surface
//              Origin at center-bottom of case
//
// Mounting: velcro on lid bottom attaches to neoprene forearm band.
// No strap slots or bridge loops needed.

include <common.scad>

// ── Dome asymmetry ──
ridge_y_offset = -8;   // ridge toward inner edge (toward body)
ridge_height   = body_height;

// ── Layout offsets ──
pico_x_offset = 0;
pico_z_offset = wall_thickness + 1;

battery_x_offset = 0;
battery_z_offset = wall_thickness + 0.5;

// OLED on outer slope, readable while pronated
oled_x_offset  = -10;
oled_y_offset  = 10;   // outer slope
oled_z_offset  = body_height * 0.6;
oled_tilt      = 25;   // tilt outward to face user

// Buttons along X axis on outer slope
button_zone_y = ridge_y_offset + 8;  // outer side of ridge

button_positions = [
    [ 24,  0],   // Index:  elbow end
    [  8,  2],   // Middle: tallest finger, reaches furthest over ridge
    [ -8,  2],   // Ring:   similar reach
    [-24, -1],   // Pinky:  wrist end, shortest
];

// Slide switch — elbow end wall
switch_x_offset = body_length/2;
switch_y_offset = 0;
switch_z_offset = body_height * 0.3;

// Screw posts — 4 corners, inset. Heights clamped to dome interior.
screw_inset = 8;
screw_positions = [
    [ body_length/2 - screw_inset,  body_width/2 - screw_inset],
    [ body_length/2 - screw_inset, -body_width/2 + screw_inset],
    [-body_length/2 + screw_inset,  body_width/2 - screw_inset],
    [-body_length/2 + screw_inset, -body_width/2 + screw_inset],
];

// Max screw post height — must stay inside the dome at corner positions.
// The dome is lowest at the inner-edge corners (negative Y).
screw_post_height_outer = inner_height * 0.55;  // outer corners (taller dome)
screw_post_height_inner = inner_height * 0.30;  // inner corners (shorter dome)


// ════════════════════════════════════════════════════════════
// Modules
// ════════════════════════════════════════════════════════════

// Asymmetric dome — ridge along X, offset toward inner edge
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

        // Ridge line — peak offset toward inner edge
        for (sx = [1, -1, 0])
            translate([
                sx * (body_length/3),
                ridge_y_offset,
                ridge_height - corner_radius
            ])
                scale([1, 0.6, 1])
                    sphere(r = corner_radius * 1.8);

        // Outer slope control — gentle slope, screen side
        for (sx = [1, -1])
            translate([
                sx * (body_length/3),
                body_width/2 - corner_radius * 2,
                body_height * 0.45
            ])
                sphere(r = corner_radius * 1.2);

        // Inner slope control — steeper drop to inner edge
        for (sx = [1, -1])
            translate([
                sx * (body_length/3),
                -body_width/2 + corner_radius * 2,
                body_height * 0.35
            ])
                sphere(r = corner_radius);
    }
}

// Inner cavity
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

            for (sx = [1, -1, 0])
                translate([
                    sx * (body_length/3),
                    ridge_y_offset,
                    ridge_height - wall_thickness - corner_radius * 2
                ])
                    scale([1, 0.6, 1])
                        sphere(r = corner_radius * 1.0);

            for (sx = [1, -1])
                translate([
                    sx * (body_length/3),
                    body_width/2 - corner_radius * 2 - wall_thickness,
                    body_height * 0.4
                ])
                    sphere(r = corner_radius * 0.8);

            for (sx = [1, -1])
                translate([
                    sx * (body_length/3),
                    -body_width/2 + corner_radius * 2 + wall_thickness,
                    body_height * 0.3
                ])
                    sphere(r = corner_radius - 0.5);
        }
}

// Button well
module button_well(x, y) {
    translate([x, y, 0]) {
        translate([0, 0, body_height - button_well_depth - 3])
            cylinder(d = button_well_dia, h = button_well_depth + 15);
        translate([0, 0, wall_thickness - 0.1])
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

// OLED standoffs with ribs to floor
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

            hull() {
                translate([ox, oy, oz])
                    cylinder(d = post_d, h = 0.5);
                translate([ox, oy, wall_thickness])
                    cylinder(d = post_d + 1, h = 0.5);
            }
        }
}

// USB-C port — wrist end
module usbc_cutout() {
    translate([-body_length/2 - 1, 0, wall_thickness + pico_height/2 + 2])
        rotate([0, 90, 0])
            hull() {
                for (sx = [1, -1])
                    translate([0, sx * (usbc_width/2 - usbc_radius), 0])
                        cylinder(r = usbc_radius, h = wall_thickness + 2);
            }
}

// Pico standoffs
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

// Battery compartment
module battery_compartment() {
    translate([battery_x_offset, 0, wall_thickness - 0.1])
        cube([battery_length + battery_clearance * 2,
              battery_width + battery_clearance * 2,
              battery_height + battery_clearance], center = true);
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

// Screw posts — height varies by position (shorter on inner side)
module screw_posts() {
    for (pos = screw_positions) {
        // Use shorter posts for inner-edge corners where dome is lower
        post_h = (pos[1] < 0) ? screw_post_height_inner : screw_post_height_outer;

        translate([pos[0], pos[1], wall_thickness])
            difference() {
                cylinder(d = m2_insert_dia + 3, h = post_h);
                translate([0, 0, post_h - m2_insert_depth])
                    cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
            }
    }
}

// Slide switch — elbow end wall
module switch_cutout() {
    translate([switch_x_offset, switch_y_offset, switch_z_offset]) {
        rotate([0, 90, 0])
            translate([0, 0, -wall_thickness - 1])
                cube([switch_slot_height, switch_slot_length, wall_thickness + 2],
                     center = true);

        rotate([0, 90, 0])
            translate([0, 0, -wall_thickness/2])
                cube([switch_body_height + 1,
                      switch_body_length + 1,
                      switch_body_width + 1],
                     center = true);

        translate([0, -(switch_slot_length/2 + switch_indicator_dia/2 + 0.5), 0])
            rotate([0, 90, 0])
                translate([0, 0, -0.1])
                    cylinder(d = switch_indicator_dia, h = switch_indicator_depth + 0.1);

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
            difference() {
                dome_outer();
                dome_inner();
            }

            pico_standoffs();
            oled_standoffs();
            screw_posts();
        }

        button_cluster();
        oled_cutout();
        usbc_cutout();
        switch_cutout();
        vent_slots();

        // Trim flat bottom
        translate([0, 0, -50])
            cube([200, 200, 100], center = true);
    }
}

roam_case();
