// button_well.scad — Recessed button well with stem hole
// Solved component: cylindrical well for tactile switch cap.
//
// Usage:
//   include <common.scad>
//   use <lib/button_well.scad>
//   button_well(x, y);
//
// Cuts from the top surface downward:
//   - Wide well (button_well_dia) for the cap to sit in
//   - Narrow stem hole (button_diameter) all the way through for the actuator
//
// Dimensions from common.scad:
//   button_well_dia, button_well_depth, button_diameter, print_tolerance

include <common.scad>

module button_well(x=0, y=0) {
    translate([x, y, 0]) {
        // Well recess — starts below dome surface, extends up through
        translate([0, 0, body_height - button_well_depth - 3])
            cylinder(d = button_well_dia, h = button_well_depth + 15);
        // Stem hole — narrow through-hole for switch actuator
        translate([0, 0, -EPS])
            cylinder(d = button_diameter + print_tolerance * 2, h = body_height + 5);
    }
}

// Place all 4 buttons from button_positions array
module button_cluster() {
    for (pos = button_positions)
        button_well(pos[0], button_zone_y + pos[1]);
}
