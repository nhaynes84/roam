// usbc_cutout.scad — USB-C port cutout module
// Solved component: stadium-shape (rounded rectangle) through wall.
//
// Usage:
//   include <common.scad>
//   use <lib/usbc_cutout.scad>
//   usbc_port(center_x, center_y, center_z, wall_face);
//
// Parameters:
//   cx, cy, cz  — center of the port on the wall surface
//   face         — which wall: "wrist" (X-), "elbow" (X+), "inner" (Y-), "outer" (Y+)
//
// Dimensions from common.scad: usbc_width, usbc_height, usbc_radius, wall_thickness

include <common.scad>

module usbc_port(cx=0, cy=0, cz=0, face="wrist") {
    // Rotation to cut through the correct wall face
    rot = (face == "wrist")  ? [0, 90, 0] :
          (face == "elbow")  ? [0, 90, 0] :
          (face == "inner")  ? [-90, 0, 0] :
          (face == "outer")  ? [-90, 0, 0] :
          [0, 0, 0];

    // Offset direction to ensure cut penetrates the wall
    dx = (face == "wrist") ? -1 : (face == "elbow") ? 1 : 0;
    dy = (face == "inner") ? -1 : (face == "outer") ? 1 : 0;

    translate([cx + dx * EPS, cy + dy * EPS, cz])
        rotate(rot)
            hull() {
                for (sx = [1, -1])
                    translate([0, sx * (usbc_width/2 - usbc_radius), 0])
                        cylinder(r = usbc_radius, h = wall_thickness + 2 * EPS);
            }
}
