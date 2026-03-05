// roam_dome.scad — Dome shell for Roam wrist-mount controller
//
// ORIENTATION: see common.scad header
//   Dome sits with open bottom at Z=0, grip peak at Z=body_height (44mm).
//
// SHAPE: Two zones in Y-Z cross-section:
//   Y- side: Cylindrical grip (R=22, center at Y=-22, Z=22).
//            Hand wraps around this. Buttons on vertical front face (Y≈0).
//   Y+ side: Flat screen shelf at Z≈20, steep drop to outer rim.
//            OLED mounts here with window cutout for visible area.
//
//   USB-C and switch cutouts on wrist wall (X-).

include <common.scad>

// ── USB-C position ──
usbc_z = pico_standoff_height + shim_height + pico_height / 2;

// ── Grip arc helper ──
// Returns [Y, Z] point on the upper half of the grip cylinder at angle a.
// a=180° → leftmost (Y = grip_cy - grip_r), a=0° → equator (Y = grip_cy + grip_r)
function grip_pt(a) = [
    grip_cy + grip_r * cos(a),
    grip_cz + grip_r * sin(a)
];

// ── Cross-section polygon (Y-Z plane) ──
// Extruded along X to form the dome shape.
//
//   Z=44    ╭╮           ← grip peak
//          ╱  ╲
//   Z=22  │    •buttons  ← vertical face (Y=0)
//         │     ╲___________
//         │      shelf      ╲
//   Z=0  ─┘                  └─
//       Y=-50       0        Y=50

module dome_profile_2d(inset = 0) {
    // inset > 0 creates the inner profile (for shell subtraction)
    r = grip_r - inset;
    cy = grip_cy;
    cz = grip_cz;
    ir = wall_inner + inset;  // inner rim Y
    or_y = wall_outer - inset; // outer rim Y
    sz = shelf_z - inset * 0.5; // shelf height (less inset for floor)

    // Arc points for upper grip cylinder (180° to 0°)
    arc = [for (a = [180 : -5 : 0]) [cy + r * cos(a), cz + r * sin(a)]];

    pts = concat(
        [[ir, 0]],              // inner rim
        [[cy - r, cz]],        // inner wall meets cylinder tangent
        arc,                     // grip arc (upper half)
        [[shelf_start_y - inset, sz]],       // transition to shelf
        [[shelf_end_y - inset, sz - 2]],     // flat screen area
        [[(or_y + shelf_end_y - inset) / 2, shelf_drop_z]],  // steep drop mid
        [[or_y, 0]]             // outer rim
    );

    polygon(pts);
}


// ════════════════════════════════════════════════════════════
// Modules
// ════════════════════════════════════════════════════════════

// Extrude profile along X axis using rotate trick:
// polygon in X-Y plane (x=Y_model, y=Z_model), extrude along Z,
// then rotate([90,0,0]) rotate([0,90,0]) to get (Z_ext→X, x→Y, y→Z).
module dome_shell(inset, length) {
    rotate([90, 0, 0])
        rotate([0, 90, 0])
            linear_extrude(height = length, center = true)
                dome_profile_2d(inset);
}

module dome_outer() {
    intersection() {
        // Clip to body footprint with rounded corners in X
        hull()
            for (sx = [1, -1])
                translate([sx * (body_length/2 - corner_radius), 0, body_height/2])
                    cube([corner_radius * 2, body_width + 1, body_height + 1], center = true);

        dome_shell(inset = 0, length = body_length);
    }
}

module dome_inner() {
    dome_shell(inset = wall_thickness, length = body_length + 1);
}


// ── Radial button well (bores perpendicular to cylinder surface) ──
// x: position along forearm axis
// z_btn: height on grip cylinder (must be >= grip_cz, on the arc)
//
// Tapered hole: 8.5mm at outer wall, 10.8mm at inner wall.
// Bore is radial — perpendicular to cylinder surface — so it cuts
// exactly wall_thickness of material. Cone d1/d2 are extended by
// the overshoot so spec diameters land at the actual wall faces.
module button_well(x, z_btn) {
    dz = z_btn - grip_cz;
    y_surface = grip_cy + sqrt(grip_r * grip_r - dz * dz);
    theta = atan2(dz, y_surface - grip_cy);

    // Extend cone past both surfaces to avoid coincident faces
    overshoot = 1;  // mm each side
    taper_rate = (button_inner_dia - button_outer_dia) / wall_thickness;
    d_start = button_outer_dia - taper_rate * overshoot;  // at 1mm outside
    d_end   = button_inner_dia + taper_rate * overshoot;  // at 1mm past inner
    bore_depth = wall_thickness + 2 * overshoot;

    translate([x, grip_cy, grip_cz])
        rotate([theta, 0, 0])
            translate([0, grip_r + overshoot, 0])
                rotate([90, 0, 0])
                    cylinder(d1 = d_start, d2 = d_end,
                             h = bore_depth, $fn = 40);
}

module button_cluster() {
    for (pos = button_positions)
        button_well(pos[0], pos[1]);
}


// ── Thumb button well (bores along -X into elbow-side flat wall) ──
// Half-size tapered holes, same cone design as finger buttons.
module thumb_well(y, z) {
    overshoot = 1;
    taper_rate = (thumb_inner_dia - thumb_outer_dia) / wall_thickness;
    d_start = thumb_outer_dia - taper_rate * overshoot;
    d_end   = thumb_inner_dia + taper_rate * overshoot;
    bore_depth = wall_thickness + 2 * overshoot;

    // Bore along -X into the flat elbow wall
    translate([wall_elbow + overshoot, y, z])
        rotate([0, -90, 0])
            cylinder(d1 = d_start, d2 = d_end,
                     h = bore_depth, $fn = 30);
}

module thumb_cluster() {
    for (pos = thumb_positions)
        thumb_well(pos[0], pos[1]);
}


// ── Screen window cutout ──
// Rectangular hole through the shelf for OLED visible area.
// Uses large screen dimensions; swap to oled_sm_* for small screen.
module screen_window() {
    // Window position: centered on X, on the shelf surface
    // Visible area is inset from board edges
    vis_w = oled_lg_vis_w;   // 55mm along X
    vis_h = oled_lg_vis_h;   // 29mm along Y (on shelf)
    // Center of visible area on shelf
    screen_y = shelf_start_y + oled_lg_vis_side + vis_h / 2;
    screen_z = shelf_z;

    // Cut generously through full shelf thickness (outer surface + inner offset)
    translate([0, screen_y, screen_z])
        cube([vis_w, vis_h, wall_thickness * 3], center = true);
}


// ── Screw bosses at dome rim ──
module dome_screw_bosses() {
    boss_od = 6.2;
    boss_height = 8;
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


// ── USB-C port cutout — wrist wall (X-) ──
module usbc_cutout() {
    translate([wall_wrist - EPS, 0, usbc_z])
        rotate([0, 90, 0])
            hull() {
                for (sy = [1, -1])
                    translate([0, sy * (usbc_width/2 - usbc_radius), 0])
                        cylinder(r = usbc_radius, h = wall_thickness + 2);
            }
}

// ── Power switch slot — wrist wall (X-), offset from USB-C ──
module switch_cutout() {
    translate([wall_wrist - EPS, switch_y_offset, usbc_z])
        rotate([0, 90, 0])
            hull() {
                for (sy = [1, -1])
                    translate([0, sy * (switch_slot_width/2 - switch_slot_radius), 0])
                        for (sz = [1, -1])
                            translate([sz * (switch_slot_height/2 - switch_slot_radius), 0, 0])
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
        thumb_cluster();
        screen_window();
        usbc_cutout();
        switch_cutout();

        // Trim flat bottom at z=0 (dome rim)
        translate([0, 0, -50])
            cube([200, 200, 100], center = true);
    }
}

roam_dome();
