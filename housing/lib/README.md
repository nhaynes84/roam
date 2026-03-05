# Housing Component Library

Reusable OpenSCAD modules for solved mechanical features. Each file is self-contained with `include <common.scad>` and can be used via `use <lib/filename.scad>`.

## Components

| File | Module | Description |
|------|--------|-------------|
| `usbc_cutout.scad` | `usbc_port()` | Stadium-shape USB-C port cutout through any wall face |
| `m2_boss.scad` | `m2_boss()`, `m2_boss_with_rib()` | Heat-set insert boss with optional wall rib |
| `button_well.scad` | `button_well()`, `button_cluster()` | Recessed tactile switch well + stem hole |
| `switch_slot.scad` | `switch_slot()` | Slide switch actuator slot (MSK-12C02) |
| `velcro_recess.scad` | `velcro_recess()` | Flush pocket for adhesive velcro patch |

## Conventions

- All dimensions come from `common.scad` — don't hardcode numbers
- Use named wall positions (`wall_wrist`, `wall_elbow`, `wall_outer`, `wall_inner`) instead of raw ±body_length/2
- Use `EPS` (0.1mm) for difference() overlap instead of magic numbers like `-1` or `0.1`
- See orientation header in `common.scad` for axis definitions

## Adding Components

1. One module per file, named after the feature
2. Include `common.scad` for shared dimensions
3. Document parameters and which wall/face it applies to
4. Default parameter values should use common.scad dimensions where possible
