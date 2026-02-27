// roam_dome.scad — Dome shell for Roam wrist-mount controller
// Just the shell, button wells, and screw bosses at rim.
// All interior mounting (OLED, USB-C, vents) left for manual design.

include <common.scad>

// ── Dome asymmetry ──
ridge_height = body_height;

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

        // Trim flat bottom at z=0 (dome rim)
        translate([0, 0, -50])
            cube([200, 200, 100], center = true);
    }
}

roam_dome();
