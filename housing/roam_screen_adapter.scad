// Roam Screen Adapter — mounts small 1.3" SH1106 in big case's 2.42" screen opening
// Print in PLA, glue into place on the shelf
//
// The big case has:
//   - Screen window cutout: 55mm x 29mm
//   - M2 mounting holes: 64mm x 42mm spacing
//   - Shelf at Z=20mm
//
// The small screen is:
//   - Board: 33mm x 33mm
//   - Visible area: 30mm x 15mm (3mm inset from sides, 8mm from top)
//   - Mounting holes: 27mm x 27mm spacing, M2

include <common.scad>

// Adapter plate dimensions — matches the large screen board footprint
// so it uses the same mounting holes
adapter_w = oled_lg_board_w;    // 70mm
adapter_h = oled_lg_board_h;    // 48mm
adapter_thick = 2.0;            // 2mm thick PLA

// Small screen sits centered on the adapter
// Center the small board on the adapter
sm_offset_x = 0;  // centered in X
sm_offset_y = 0;   // centered in Y

// Visible area window — slightly larger than small screen's visible area
// for tolerance
window_w = oled_sm_vis_w + 1;   // 31mm
window_h = oled_sm_vis_h + 1;   // 16mm

// Window position relative to small board center
// Visible area is 3mm from sides (centered in X), 8mm from top edge
// Board is 33mm tall, vis area starts 8mm from top, is 15mm tall
// Center of vis area from board center: -(33/2) + 8 + 15/2 = -16.5 + 8 + 7.5 = -1
window_offset_y = -(oled_sm_board_h/2) + oled_sm_vis_top + oled_sm_vis_h/2;

// Corner rounding
corner_r = 2;

// Lip to hold the small screen board (raised rim around the board pocket)
pocket_depth = 1.6;  // PCB thickness
pocket_clearance = 0.3;  // per side

module screen_adapter() {
    difference() {
        // Main plate with rounded corners
        linear_extrude(adapter_thick)
            offset(r=corner_r) offset(r=-corner_r)
                square([adapter_w, adapter_h], center=true);

        // Window cutout for small screen visible area
        translate([sm_offset_x, sm_offset_y + window_offset_y, -1])
            linear_extrude(adapter_thick + 2)
                offset(r=1) offset(r=-1)
                    square([window_w, window_h], center=true);

        // Board pocket — recess for the small screen PCB to sit in
        translate([sm_offset_x, sm_offset_y, adapter_thick - pocket_depth])
            linear_extrude(pocket_depth + 1)
                offset(r=1) offset(r=-1)
                    square([oled_sm_board_w + pocket_clearance*2,
                            oled_sm_board_h + pocket_clearance*2], center=true);

        // Large screen mounting holes (M2 clearance, for mounting adapter to case)
        for (dx = [-1, 1], dy = [-1, 1])
            translate([dx * oled_lg_hole_sp_w/2, dy * oled_lg_hole_sp_h/2, -1])
                cylinder(d=m2_screw_dia, h=adapter_thick + 2, $fn=20);

        // Small screen mounting holes (M2, for screwing small screen to adapter)
        for (dx = [-1, 1], dy = [-1, 1])
            translate([sm_offset_x + dx * oled_sm_hole_sp/2,
                       sm_offset_y + dy * oled_sm_hole_sp/2, -1])
                cylinder(d=m2_screw_dia, h=adapter_thick + 2, $fn=20);
    }

    // Alignment posts around the small board pocket corners
    // These help position the small screen during assembly
    post_h = pocket_depth + 1.5;  // stick up above the pocket floor
    post_w = 2;
    for (dx = [-1, 1], dy = [-1, 1]) {
        // Position posts at corners of the board pocket
        px = sm_offset_x + dx * (oled_sm_board_w/2 + pocket_clearance + post_w/2);
        py = sm_offset_y + dy * (oled_sm_board_h/2 + pocket_clearance + post_w/2);
        translate([px, py, 0])
            cylinder(d=post_w, h=adapter_thick + post_h, $fn=16);
    }
}

// Render
screen_adapter();
