// roam_case.scad — Main parametric enclosure for Roam wrist-mount controller
// Half-moon / climbing-hold ergonomic dome shape
// Flat bottom (against forearm), convex top for finger rest
//
// Orientation: X = forearm axis (length), Y = across forearm (width)
//              Z = up from forearm surface
//              Origin at center-bottom of case

include <common.scad>

// ── Layout offsets ──
// Pico sits centered lengthwise, slightly toward elbow end
pico_x_offset = 5;
pico_z_offset = wall_thickness + 1;  // raised on standoffs

// Battery sits below Pico toward bottom
battery_x_offset = pico_x_offset;
battery_z_offset = wall_thickness + 0.5;

// OLED positioned between buttons and wrist end, angled 15°
oled_x_offset  = -15;  // toward wrist
oled_z_offset  = body_height - wall_thickness - 2;
oled_tilt      = 15;   // degrees toward user line-of-sight

// Buttons: 2x2 grid on top surface, positioned for left hand reaching
// to right forearm. Top row = elbow end (index+middle), bottom = wrist (ring+pinky)
button_cluster_x = 18;  // toward elbow end
button_cluster_y = 0;   // centered across width

// Band slot positions (along X axis)
band_elbow_x =  (body_length/2 - band_width/2 - 3);
band_wrist_x = -(body_length/2 - band_width/2 - 3);

// Slide switch position — side of case, elbow end, accessible with thumb
switch_y_offset = body_width/2;  // on the right side wall
switch_x_offset = body_length/4; // toward elbow end
switch_z_offset = body_height * 0.3;  // lower third of side wall

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

// Outer dome shape — hull of spheres creating the climbing-hold profile
module dome_outer() {
    hull() {
        // Four base corners — flattened spheres at bottom plane
        for (sx = [1, -1])
            for (sy = [1, -1])
                translate([
                    sx * (body_length/2 - corner_radius),
                    sy * (body_width/2 - corner_radius),
                    corner_radius
                ])
                    sphere(r = corner_radius);

        // Central dome peak — ellipsoidal apex
        translate([0, 0, body_height - corner_radius])
            scale([1, 0.85, 1])
                sphere(r = corner_radius * 2);

        // Two mid-height ridges along length for ergonomic shape
        for (sx = [1, -1])
            translate([
                sx * (body_length/3),
                0,
                body_height * 0.8
            ])
                sphere(r = corner_radius * 1.5);

        // Edge ridges — lower profile toward sides for finger wrap
        for (sx = [1, -1])
            for (sy = [1, -1])
                translate([
                    sx * (body_length/2 - corner_radius * 2),
                    sy * (body_width/2 - corner_radius),
                    body_height * 0.4
                ])
                    sphere(r = corner_radius);
    }
}

// Inner cavity — offset inward from outer dome
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

            translate([0, 0, body_height - wall_thickness - corner_radius * 1.5])
                scale([1, 0.85, 1])
                    sphere(r = corner_radius * 1.2);

            for (sx = [1, -1])
                translate([
                    sx * (body_length/3),
                    0,
                    body_height * 0.75
                ])
                    sphere(r = corner_radius);

            for (sx = [1, -1])
                for (sy = [1, -1])
                    translate([
                        sx * (body_length/2 - corner_radius * 2 - wall_thickness),
                        sy * (body_width/2 - corner_radius - wall_thickness),
                        body_height * 0.35
                    ])
                        sphere(r = corner_radius - 0.5);
        }
}

// Button well — recessed cylindrical well in dome surface
module button_well(x, y) {
    translate([x, y, 0]) {
        // Well recess — cuts from dome surface inward (~3mm deep)
        // Starts at body_height - well_depth, extends well past dome peak
        translate([0, 0, body_height - button_well_depth])
            cylinder(d = button_well_dia, h = button_well_depth + 10);
        // Through-hole for switch stem / button cap — full height
        translate([0, 0, wall_thickness - 0.1])
            cylinder(d = button_diameter + print_tolerance * 2, h = body_height + 5);
    }
}

// 2x2 button cluster
module button_cluster() {
    half_sp = button_spacing / 2;

    // Top row (elbow end): Dictation (index), Mode (middle)
    button_well(button_cluster_x + half_sp,  button_cluster_y + half_sp);
    button_well(button_cluster_x + half_sp,  button_cluster_y - half_sp);

    // Bottom row (wrist end): Yes (ring), No (pinky)
    button_well(button_cluster_x - half_sp,  button_cluster_y + half_sp);
    button_well(button_cluster_x - half_sp,  button_cluster_y - half_sp);
}

// OLED window cutout + recessed ledge
module oled_cutout() {
    translate([oled_x_offset, 0, oled_z_offset])
        rotate([oled_tilt, 0, 0]) {
            // Visible window — through the shell
            translate([0, 0, -1])
                cube([oled_visible_width + 1, oled_visible_height + 1, wall_thickness + 2], center = true);

            // Recessed ledge for PCB to sit in
            translate([0, 0, -(wall_thickness + 0.5)])
                cube([oled_board_width + print_tolerance * 2,
                      oled_board_height + print_tolerance * 2,
                      oled_board_thick + 0.5], center = true);
        }
}

// OLED mounting standoffs (inside case) with support ribs to floor
module oled_standoffs() {
    standoff_h = 4;
    post_d = m2_insert_dia + 2;

    for (sx = [1, -1])
        for (sy = [1, -1]) {
            // Calculate the tilted standoff position
            ox = oled_x_offset + sx * oled_hole_spacing_w/2;
            // After 15° tilt: y shifts, z shifts
            oy = sy * oled_hole_spacing_h/2 * cos(oled_tilt);
            oz = wall_thickness + sy * oled_hole_spacing_h/2 * sin(oled_tilt);

            // Standoff at tilted position
            translate([ox, oy, oz])
                rotate([oled_tilt, 0, 0])
                    difference() {
                        cylinder(d = post_d, h = standoff_h);
                        translate([0, 0, standoff_h - m2_insert_depth])
                            cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
                    }

            // Support rib from standoff base down to floor
            hull() {
                // Base of standoff
                translate([ox, oy, oz])
                    cylinder(d = post_d, h = 0.5);
                // Floor anchor
                translate([ox, oy, wall_thickness])
                    cylinder(d = post_d + 1, h = 0.5);
            }
        }
}

// USB-C port cutout on wrist end
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

// Band slot — bridge loop for strap to thread through
module band_slot(x_pos) {
    slot_h = band_thickness + band_slot_clearance * 2;
    slot_total_w = band_width + band_slot_clearance * 2;
    bridge_thick = wall_thickness;

    translate([x_pos, 0, 0]) {
        // Slot through the bottom wall
        translate([0, 0, -0.1])
            cube([bridge_thick + 2, slot_total_w, slot_h + wall_thickness], center = true);

        // Bridge opening on each side of the case floor
        for (sy = [1, -1])
            translate([0, sy * (body_width/2), slot_h/2 + wall_thickness/2])
                rotate([0, 90, 0])
                    cylinder(d = slot_h, h = bridge_thick + 4, center = true);
    }
}

// Ventilation slots on bottom surface
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


// Slide switch cutout — slot in side wall + internal pocket + indicator recesses
module switch_cutout() {
    translate([switch_x_offset, switch_y_offset, switch_z_offset]) {
        // Slider slot through shell (for nub to poke through)
        rotate([90, 0, 0])
            translate([0, 0, -wall_thickness - 1])
                cube([switch_slot_length, switch_slot_height, wall_thickness + 2],
                     center = true);

        // Internal cavity for switch body
        rotate([90, 0, 0])
            translate([0, 0, wall_thickness/2])
                cube([switch_body_length + 1,
                      switch_body_height + 1,
                      switch_body_width + 1],
                     center = true);

        // Indicator recesses on outer surface — one on each side of the slot
        // Left recess (ON / green side)
        translate([-(switch_slot_length/2 + switch_indicator_dia/2 + 0.5), 0, 0])
            rotate([90, 0, 0])
                translate([0, 0, -0.1])
                    cylinder(d = switch_indicator_dia, h = switch_indicator_depth + 0.1);

        // Right recess (OFF / red side)
        translate([(switch_slot_length/2 + switch_indicator_dia/2 + 0.5), 0, 0])
            rotate([90, 0, 0])
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

        // Trim flat bottom (remove anything below Z=0)
        translate([0, 0, -50])
            cube([200, 200, 100], center = true);
    }
}

roam_case();
