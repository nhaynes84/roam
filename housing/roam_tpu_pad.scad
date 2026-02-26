// roam_tpu_pad.scad — TPU comfort pads for Roam lid (forearm side)
// Print in TPU (Shore 95A), glue into recessed markers on lid bottom
//
// Three pads: one central, two smaller near band slots
// Print all three in one go — they're laid out flat on the build plate

include <common.scad>

// Match the marker dimensions from roam_lid.scad
tpu_pad_length = 30;
tpu_pad_width  = 20;
tpu_thickness  = 1.2;  // slightly proud of the 0.4mm recess for cushion
tpu_small_length = 15;

// Central pad
module central_pad() {
    linear_extrude(height = tpu_thickness)
        offset(r = 2)
            offset(delta = -2)
                square([tpu_pad_length, tpu_pad_width], center = true);
}

// Smaller pad (near band slots)
module side_pad() {
    linear_extrude(height = tpu_thickness)
        offset(r = 1.5)
            offset(delta = -1.5)
                square([tpu_small_length, tpu_pad_width], center = true);
}

// All three pads laid out for printing
translate([0, 0, 0]) central_pad();
translate([-(tpu_pad_length/2 + tpu_small_length/2 + 5), 0, 0]) side_pad();
translate([ (tpu_pad_length/2 + tpu_small_length/2 + 5), 0, 0]) side_pad();
