// m2_boss.scad — M2 screw boss and heat-set insert pocket
// Solved component: cylindrical boss with insert hole and optional wall rib.
//
// Usage:
//   include <common.scad>
//   use <lib/m2_boss.scad>
//   m2_boss(x, y, height);
//   m2_boss_with_rib(x, y, height, rib_to_y);
//
// The insert hole opens at Z=0 (bottom of boss).
// Boss sits at Z=0 and grows upward.
//
// Dimensions from common.scad: m2_insert_dia, m2_insert_depth

include <common.scad>

module m2_boss(x=0, y=0, height=6, od=0) {
    boss_od = (od > 0) ? od : m2_insert_dia + 3;
    translate([x, y, 0])
        difference() {
            cylinder(d = boss_od, h = height);
            translate([0, 0, -EPS])
                cylinder(d = m2_insert_dia, h = m2_insert_depth + EPS);
        }
}

// Boss with a rib connecting to a wall (for structural support)
module m2_boss_with_rib(x=0, y=0, height=6, rib_to_y=0, rib_width=2) {
    boss_od = m2_insert_dia + 3;
    m2_boss(x, y, height, boss_od);

    // Rib from boss center to wall
    hull() {
        translate([x, y, 0])
            cylinder(d = rib_width, h = height);
        translate([x, rib_to_y, 0])
            cylinder(d = rib_width, h = height);
    }
}
