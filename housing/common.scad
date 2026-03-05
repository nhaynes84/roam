// common.scad — Shared parametric dimensions for Roam wrist-mount housing
// All dimensions in millimeters
//
// ORIENTATION (all files):
//   X+  = toward elbow
//   X-  = toward wrist (USB-C end)
//   Y+  = outer (away from body, button/dome-peak side)
//   Y-  = inner (body-facing, switch side)
//   Z+  = up from forearm surface (dome peak)
//   Z=0 = case rim / base plate top / print bed plane
//   Origin: center of case footprint at rim plane

// ── Manifold epsilon ──
EPS = 0.1;  // prevents coincident faces in difference()

// ── Ergonomic Measurements (caliper) ──
forearm_width     = 100;   // cross-section where band sits
finger_splay      = 105;   // comfortable relaxed splay, pinky-to-index outer edges
// Hand position: pronated (palm down), relaxed — no pinky/thumb squeeze

// ── Body ──
body_length   = 110;   // along forearm axis — finger_splay (105) + margins
body_width    = 100;   // across forearm — matches forearm_width
body_height   = 60;    // dome peak (top of grip cylinder, 2 * grip_r)
wall_thickness = 4.0;   // 4mm shells for structural integrity
corner_radius  = 5;

// ── Grip Cylinder ──
// Cylinder axis along X (forearm direction). Hand wraps around Y- side.
// Buttons on the near-vertical front face at Y ≈ grip_cy + grip_r.
// Battery stands inside the cylinder (34mm tall, 36mm inner diameter).
grip_r  = 30;               // grip radius — 60mm outer diameter
grip_cy = -grip_r;          // Y center: equator (vertical face) at Y=0
grip_cz = grip_r;           // Z center: tangent to Z=0, peak at Z=60

// ── Screen Shelf ──
// Flat area on Y+ side of grip for OLED visibility.
// Gentle slope from grip front, steep drop at outer edge.
shelf_z       = 20;    // shelf height (slightly below grip equator)
shelf_start_y = 3;     // where shelf begins (past grip equator)
shelf_end_y   = 42;    // where steep drop begins
shelf_drop_z  = 5;     // Z at outer edge before rim

// ── Base Plate ──
base_plate_thick = 4.0;   // 4mm — allows 2mm deep M2 head countersink + 2mm remaining

// ── Pimoroni Pico Plus 2 W ──
// Same footprint as standard Pico 2W (USB-C, RP2350, 8MB PSRAM, 16MB flash)
pico_length = 52.3;
pico_width  = 21.0;
pico_height = 3.7;
pico_hole_spacing_l = 47.0;  // mounting hole center-to-center lengthwise
pico_hole_spacing_w = 11.4;  // mounting hole center-to-center widthwise
pico_hole_dia       = 2.1;   // M2 through-hole

// ── Pico Layout ──
pico_x_offset = 0;
pico_y_offset = 0;              // centered (ridge side is too low)
pico_standoff_height = 3;       // standoff boss height on base plate

// ── LiPo SHIM for Pico ──
// Pimoroni PIM557 — sandwiches under Pico on headers.
// Handles LiPo charging via Pico USB-C, has built-in power button + LEDs.
// Replaces TP4056 and slide switch.
shim_width  = 21.0;   // same width as Pico
shim_length = 21.0;
shim_height = 7.0;    // including JST connector height
// Combined stack: SHIM (7mm) + Pico (3.7mm) = ~11mm
pico_stack_height = shim_height + pico_height;  // total height of SHIM+Pico

// ── OLED Small 1.3" (SH1106, Build 2A) — caliper-measured ──
oled_sm_board_w     = 33;
oled_sm_board_h     = 33;
oled_sm_vis_w       = 30;
oled_sm_vis_h       = 15;
oled_sm_vis_top     = 8;      // visible area starts 8mm from top edge
oled_sm_vis_side    = 3;      // visible area starts 3mm from side edges
oled_sm_hole_sp     = 27;     // 33 - 3mm inset each side = 27mm c-c (both axes)

// ── OLED Large 2.42" (SSD1309, Build 2B) — caliper-measured ──
oled_lg_board_w     = 70;
oled_lg_board_h     = 48;
oled_lg_vis_w       = 55;
oled_lg_vis_h       = 29;
oled_lg_vis_top     = 7;      // visible area starts 7mm from top edge
oled_lg_vis_side    = 7;      // visible area starts 7mm from side edges (each side)
oled_lg_hole_sp_w   = 64;     // 70 - 3mm inset each side = 64mm c-c
oled_lg_hole_sp_h   = 42;     // 48 - 3mm inset each side = 42mm c-c

// ── OLED shared mount ──
oled_board_thick    = 10;     // with wires routed underneath
oled_hole_dia       = 2.0;   // M2 through-hole
oled_head_dia       = 3.5;   // M2 button head countersink
oled_head_depth     = 2.0;   // countersink depth in 4mm backing plate

// ── Buttons ──
button_diameter = 6;
button_spacing  = 14;   // center-to-center (legacy, see positions below)
button_travel   = 1.5;
button_well_depth = 3;  // depth of recessed well
button_well_dia   = 9;  // well outer diameter (button + clearance)
// Actual button housing dimensions (measured from button)
button_outer_dia  = 8.5;    // hole on finger-facing (outer) wall
button_inner_dia  = 10.8;   // wider hole on inside wall (retains button)
button_wall_thick = 3.25;   // wall thickness the button is designed for

// ── Thumb Buttons (half-size, on elbow-side flat wall) ──
thumb_outer_dia = button_outer_dia / 2;
thumb_inner_dia = button_inner_dia / 2;
thumb_positions = [
    [-35, 15],   // Lower thumb — [Y_offset_from_center, Z_height]
    [-35, 25],   // Upper thumb
];
// Y=-35: 15mm from inner wall (Y=-50). Bore along -X into flat elbow wall.

// ── Button Layout (on grip face) ──
// Format: [X_along_forearm, Z_height_on_grip]
// Y position is computed from the cylinder surface at each Z.
// Wells bore horizontally (-Y) into the grip face.
// Z follows finger curl arc: outer fingers (index/pinky) higher,
// inner fingers (middle/ring) lower — natural "smile" curve.
button_positions = [
    [ 40, 52],   // Index  — 30mm from middle, +20mm Z
    [ 10, 32],   // Middle — baseline (on cylinder arc, above Z=30 transition)
    [-10, 32],   // Ring   — 20mm from middle, same Z
    [-30, 47],   // Pinky  — 20mm from ring, +15mm Z
];
// X gaps: 30mm (I→M), 20mm (M→R), 20mm (R→P)
// Z: middle/ring at 32 (above cylinder-to-shelf transition at Z=30)
// Index +20, pinky +15 above baseline. All on cylinder arc (Z=30..60).

// ── Switch Slot (MSK-12C02 slide switch, on wrist wall) ──
switch_slot_width  = 4.0;   // actuator slot (2mm travel + clearance)
switch_slot_height = 2.0;
switch_slot_radius = 0.5;
switch_y_offset    = 12;    // Y offset from center on wrist wall
switch_pedestal_height = 14;  // internal pedestal — aligns switch with wrist wall cutout

// ── USB-C ──
usbc_width  = 9.0;
usbc_height = 3.5;
usbc_radius = 1.5;   // corner rounding

// ── Mounting ──
// Velcro attachment to neoprene forearm band.
// Adhesive hook velcro on base bottom, loop velcro on neoprene band.
velcro_patch_length = 70;
velcro_patch_width  = 80;
velcro_recess_depth = 1.0;  // flush recess in base bottom

// ── Battery — caliper-measured ──
// Small: 25 x 39 x 6mm (502535)
// Large: 34 x 55 x 6mm
battery_length = 55;   // using large battery
battery_width  = 34;
battery_height = 6;
battery_clearance = 0.5;
battery_x_offset = 0;       // centered lengthwise
battery_y_offset = -body_width/2 + wall_thickness + battery_height/2 + battery_clearance;
// Standing on 6mm edge against inner wall: 55mm along X, 6mm in Y, 34mm tall in Z

// ── Fasteners (M2 button head) ──
m2_screw_dia    = 2.2;   // clearance hole
m2_insert_dia   = 3.2;   // heat-set insert hole
m2_insert_depth = 4.0;
m2_head_dia     = 3.8;   // button head is ~3.8mm dia
m2_head_depth   = 1.0;   // button head is ~1mm tall

// ── Screw Positions (shared between base and dome) ──
screw_positions = [
    [ body_length/2 - 10,  body_width/2 - 8],
    [-body_length/2 + 10,  body_width/2 - 8],
    [ body_length/2 - 10, -body_width/2 + 8],
    [-body_length/2 + 10, -body_width/2 + 8],
];

// ── Button Caps ──
button_cap_dia      = button_well_dia - 0.6;
button_cap_height   = button_well_depth - 0.5;
button_cap_stem_dia = button_diameter - 0.2;
button_cap_stem_h   = 2.0;
button_cap_dish     = 0.4;

// ── Ventilation ──
vent_slot_width  = 1.0;
vent_slot_length = 8.0;
vent_slot_spacing = 3.0;

// ── Named Wall Positions ──
// Use these instead of raw ±body_length/2 to prevent spatial errors.
// "wall" = outer surface of shell at that edge.
wall_wrist  = -body_length / 2;   // X- face (USB-C end)
wall_elbow  =  body_length / 2;   // X+ face
wall_outer  =  body_width  / 2;   // Y+ face (away from body, dome peak side)
wall_inner  = -body_width  / 2;   // Y- face (body-facing, switch side)
wall_top    =  body_height;       // Z+ (dome peak)
wall_bottom =  0;                 // Z=0 (rim plane / print bed)

// ── Derived ──
inner_length = body_length - 2 * wall_thickness;
inner_width  = body_width  - 2 * wall_thickness;
inner_height = body_height;  // open bottom, full height available

// ── Tolerances ──
print_tolerance = 0.2;  // FDM clearance
$fn = 60;               // global resolution
