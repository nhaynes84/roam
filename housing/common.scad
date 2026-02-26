// common.scad — Shared parametric dimensions for Roam wrist-mount housing
// All dimensions in millimeters

// ── Body ──
body_length   = 90;    // along forearm axis
body_width    = 50;    // across forearm
body_height   = 25;    // dome peak above flat bottom
wall_thickness = 2.0;
corner_radius  = 5;

// ── Pico 2 W ──
pico_length = 52.3;
pico_width  = 21.0;
pico_height = 3.7;
pico_hole_spacing_l = 47.0;  // mounting hole center-to-center lengthwise
pico_hole_spacing_w = 11.4;  // mounting hole center-to-center widthwise
pico_hole_dia       = 2.1;   // M2 through-hole

// ── OLED 1.3" (SH1106 / SSD1306) ──
oled_board_width   = 35;
oled_board_height  = 34;
oled_board_thick   = 1.6;
oled_visible_width = 30;
oled_visible_height= 15;
oled_hole_spacing_w = 29;   // board mounting holes
oled_hole_spacing_h = 28;
oled_hole_dia       = 2.1;

// ── Buttons ──
button_diameter = 6;
button_spacing  = 14;   // center-to-center
button_travel   = 1.5;
button_well_depth = 3;  // depth of recessed well
button_well_dia   = 9;  // well outer diameter (button + clearance)

// ── USB-C ──
usbc_width  = 9.0;
usbc_height = 3.5;
usbc_radius = 1.5;   // corner rounding

// ── Band / Strap ──
band_width     = 25;
band_thickness = 3;   // silicone strap thickness
band_slot_depth= 3;
band_slot_clearance = 1;  // extra clearance around strap

// ── Battery (502535 LiPo) ──
battery_length = 35;
battery_width  = 25;
battery_height = 5;
battery_clearance = 0.5;

// ── Fasteners (M2) ──
m2_screw_dia    = 2.2;   // clearance hole
m2_insert_dia   = 3.2;   // heat-set insert hole
m2_insert_depth = 4.0;
m2_head_dia     = 4.0;
m2_head_depth   = 1.5;

// ── Ventilation ──
vent_slot_width  = 1.0;
vent_slot_length = 8.0;
vent_slot_spacing = 3.0;

// ── Derived ──
inner_length = body_length - 2 * wall_thickness;
inner_width  = body_width  - 2 * wall_thickness;
inner_height = body_height - wall_thickness;  // bottom wall only

// ── Tolerances ──
print_tolerance = 0.2;  // FDM clearance
$fn = 60;               // global resolution
