// velcro_recess.scad — Flush velcro patch recess
// Solved component: shallow rounded rectangular pocket on bottom face.
//
// Usage:
//   include <common.scad>
//   use <lib/velcro_recess.scad>
//   velcro_recess();
//
// Cut at Z=0 facing downward. Recess depth from common.scad.
// Dimensions from common.scad: velcro_patch_length, velcro_patch_width, velcro_recess_depth

include <common.scad>

module velcro_recess(length=0, width=0, depth=0, rounding=2) {
    l = (length > 0) ? length : velcro_patch_length;
    w = (width > 0)  ? width  : velcro_patch_width;
    d = (depth > 0)  ? depth  : velcro_recess_depth;

    translate([0, 0, -EPS])
        linear_extrude(height = d + EPS)
            offset(r = rounding)
                offset(delta = -rounding)
                    square([l, w], center = true);
}
