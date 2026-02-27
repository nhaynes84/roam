// roam_dome.scad — Dome shell for Roam wrist-mount controller
// Shell, button wells, screw bosses, USB-C port, and power switch cutout.
// All interior mounting (OLED, vents, standoffs) left for manual design.

include <common.scad>

// ── Dome asymmetry ──
ridge_height = body_height;

// ── USB-C position ──
// Wrist end (-X), centered on Y. Z based on SHIM+Pico stack height.
usbc_z = pico_standoff_height + shim_height + pico_height / 2;

// ── Power switch (MSK-12C02 slide switch) ──
// Inner side wall (-Y), near wrist end.
// Actuator slot: 4mm wide (2mm travel + clearance) × 2mm tall
switch_slot_width  = 4.0;
switch_slot_height = 2.0;
switch_slot_radius = 0.5;
switch_x_offset    = -body_length/4;   // toward wrist end
switch_z_offset    = 5.0;              // low on wall, accessible from bottom

// ════════════════════════════════════════════════════════════
// Modules
// ════════════════════════════════════════════════════════════

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

module button_well(x, y) {
    translate([x, y, 0]) {
        translate([0, 0, body_height - button_well_depth - 3])
            cylinder(d = button_well_dia, h = button_well_depth + 15);
        translate([0, 0, -1])
            cylinder(d = button_diameter + print_tolerance * 2, h = body_height + 5);
    }
}

module button_cluster() {
    for (pos = button_positions)
        button_well(pos[0], button_zone_y + pos[1]);
}

// Screw bosses at dome rim — connected to walls via ribs
module dome_screw_bosses() {
    boss_od = 6.2;
    boss_height = 6;
    rib_width = 2;

    for (pos = screw_positions) {
        translate([pos[0], pos[1], 0])
            difference() {
                cylinder(d = boss_od, h = boss_height);
                translate([0, 0, -0.1])
                    cylinder(d = m2_insert_dia, h = m2_insert_depth + 0.1);
            }

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


// USB-C port cutout — wrist end wall, centered
module usbc_cutout() {
    translate([-body_length/2 - 1, 0, usbc_z])
        rotate([0, 90, 0])
            hull() {
                for (sx = [1, -1])
                    translate([0, sx * (usbc_width/2 - usbc_radius), 0])
                        cylinder(r = usbc_radius, h = wall_thickness + 2);
            }
}

// Power switch slot — inner side wall (-Y), near wrist end
module switch_cutout() {
    translate([switch_x_offset, -(body_width/2 + 1), switch_z_offset])
        rotate([-90, 0, 0])
            hull() {
                for (sx = [1, -1])
                    translate([sx * (switch_slot_width/2 - switch_slot_radius), 0, 0])
                        for (sz = [1, -1])
                            translate([0, 0, sz * (switch_slot_height/2 - switch_slot_radius)])
                                cylinder(r = switch_slot_radius, h = wall_thickness + 2);
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
            dome_screw_bosses();
        }

        button_cluster();
        usbc_cutout();
        switch_cutout();

        // Trim flat bottom at z=0 (dome rim)
        translate([0, 0, -50])
            cube([200, 200, 100], center = true);
    }
}

roam_dome();
