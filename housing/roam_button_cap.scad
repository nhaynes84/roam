// roam_button_cap.scad — Printable button cap for Roam tactile switches
// Sits in the button well, contacts switch nub underneath
// Print 4x in PLA or TPU (TPU gives softer click feel)
//
// Orientation: print flat-side down (dish faces up)

include <common.scad>

module button_cap() {
    difference() {
        union() {
            // Main cap body — cylinder that sits in the well
            cylinder(d = button_cap_dia, h = button_cap_height);

            // Stem — narrower cylinder that reaches down to the switch nub
            translate([0, 0, -button_cap_stem_h])
                cylinder(d = button_cap_stem_dia, h = button_cap_stem_h + 0.01);
        }

        // Concave dish on top for finger grip
        translate([0, 0, button_cap_height])
            scale([1, 1, button_cap_dish / (button_cap_dia / 2)])
                sphere(d = button_cap_dia);
    }
}

button_cap();
