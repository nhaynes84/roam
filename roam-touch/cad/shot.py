"""Beauty renders for the bracer -- headless Blender, hard key light.

★ WHY NOT stlshot. stlshot's world lighting is near-white and its material is
flat, so a faceted surface comes back looking smooth: every facet returns
almost the same value and the creases vanish. This part is now a LOW-POLY
SCULPT, and the whole point of that surface is that adjacent facets take the
light differently -- so the render has to have a directional key and a dark
background or it is not showing the thing being judged.

    ~/Projects/synth-case/.venv/bin/python shot.py            # all views
    ~/Projects/synth-case/.venv/bin/python shot.py --only print
"""
import argparse
import os
import subprocess
import sys
import tempfile

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
HERE = os.path.dirname(os.path.abspath(__file__))

# name -> (model, elev, azim). azim 0 looks down -Y.
# ⚠️ The two PRINT views are of the *_print.stl, which is the part rotated onto
# the bed -- see feedback-nick-sees-geometry: geometry gets judged in the
# orientation it prints in.
VIEWS = [
    # ★ STEP 1 of the functional build — the phone housing on a flat base.
    # Steps, not one grand go: this is fit only, and it gets its own views so
    # the thing being judged is the thing that changed.
    ("roam1_iso",   "roam_step1.stl", 28, 32),
    ("roam1_top",   "roam_step1.stl", 88, 0),
    ("roam1_usb",   "roam_step1.stl", 8, 0),
    ("roam1_jack",  "roam_step1.stl", 8, 180),
    ("roam1_btn",   "roam_step1.stl", 12, 270),
    # STEP 2 — the pack tube. The end-on view is the one that matters: it shows
    # whether the cylinder READS as a cylinder or has been swallowed by a boss.
    ("roam2_iso",   "roam_step2.stl", 26, 34),
    ("roam2_end",   "roam_step2.stl", 4, 0),
    ("roam2_top",   "roam_step2.stl", 88, 0),
    ("roam2_worn",  "roam_step2.stl", 14, 60),
    # STEP 3 — the visor. End-on is the judgement view: does the tube still read
    # under it, or has the plate swallowed the cylinder?
    ("roam3_end",   "roam_step3.stl", 4, 0),
    ("roam3_iso",   "roam_step3.stl", 26, 34),
    ("roam3_worn",  "roam_step3.stl", 14, 60),
    ("print_iso",   "bracer_print.stl", 26, 34),
    ("print_side",  "bracer_print.stl", 8, 96),
    ("print_back",  "bracer_print.stl", 22, 208),
    # ★ The three the owner had to ask for twice: the TOP, and each END square
    # on. The low-poly pass before this one tessellated the flanks only, and
    # from every view except a flank it was still a slab -- but no render in
    # this file was pointed at the surfaces that were still flat. A view of
    # every face you have claimed to treat is part of the claim.
    ("top",         "bracer.stl", 88, 0),
    ("end_elbow",   "bracer.stl", 6, 180),
    ("end_elbow_q", "bracer.stl", 20, 150),
    ("end_wrist",   "bracer_endcap.stl", 6, 0),
    ("guard_side",  "bracer.stl", 16, 272),
    ("worn_iso",    "bracer.stl", 28, 128),
    ("worn_iso2",   "bracer.stl", 24, 300),
    ("worn_end",    "bracer.stl", 4, 182),
    ("worn_under",  "bracer.stl", -38, 250),
    ("cap",         "bracer_endcap.stl", 24, 140),
    # ★ The pack module -- where the battery went. Two views: the pocket it
    # carries, and the saddle + strap channels that hold it to the arm.
    ("pack_iso",    "bracer_pack.stl", 26, 130),
    ("pack_saddle", "bracer_pack.stl", -34, 40),
]

SCRIPT = r'''
import bpy, sys, math, mathutils
a = sys.argv[sys.argv.index("--")+1:]
path, outfile, elev, azim, res = a[0], a[1], float(a[2]), float(a[3]), int(a[4])

bpy.ops.wm.read_factory_settings(use_empty=True)
try: bpy.ops.wm.stl_import(filepath=path)
except AttributeError: bpy.ops.import_mesh.stl(filepath=path)
obj = bpy.context.selected_objects[0]
bpy.ops.object.shade_flat()
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
obj.location = (0, 0, 0)
dim = max(obj.dimensions)

mat = bpy.data.materials.new("m"); mat.use_nodes = True
n = mat.node_tree.nodes["Principled BSDF"]
n.inputs["Base Color"].default_value = (0.44, 0.47, 0.52, 1)
n.inputs["Roughness"].default_value = 0.42
if "Metallic" in n.inputs: n.inputs["Metallic"].default_value = 0.25
obj.data.materials.append(mat)

# dark ground so the silhouette reads. read_factory_settings(use_empty=True)
# leaves the scene with NO world at all, so make one.
w = bpy.context.scene.world
if w is None:
    w = bpy.data.worlds.new("w"); bpy.context.scene.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.04, 0.045, 0.05, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0

e, z = math.radians(elev), math.radians(azim)
d = dim * 2.6
cloc = mathutils.Vector((d*math.cos(e)*math.sin(z), -d*math.cos(e)*math.cos(z),
                         d*math.sin(e)))
cam_data = bpy.data.cameras.new("c"); cam_data.type = 'ORTHO'
cam_data.ortho_scale = dim * 1.18
cam = bpy.data.objects.new("c", cam_data); bpy.context.scene.collection.objects.link(cam)
cam.location = cloc
cam.rotation_mode = 'QUATERNION'
cam.rotation_quaternion = cloc.to_track_quat('Z', 'Y')
bpy.context.scene.camera = cam

# ★ Hard key up-and-left of camera, soft fill opposite, rim behind. A single
# ambient dome is exactly what hides facets.
def lamp(name, loc, energy, size, kind='AREA'):
    ld = bpy.data.lights.new(name, kind); ld.energy = energy
    if kind == 'AREA': ld.size = size
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_quaternion = mathutils.Vector(loc).to_track_quat('Z', 'Y')
    ob.rotation_mode = 'QUATERNION'
    return ob

# ⚠️ Lights are placed in the CAMERA's frame, not the world's. Keyed off world
# +Z, any view from below (the underside/cuff shots) puts the key behind the
# part and the render comes back black.
side = cloc.normalized().cross(mathutils.Vector((0, 0, 1))).normalized()
up = side.cross(cloc.normalized()).normalized()
# ⚠️ Blender units are the STL's millimetres, so the inverse-square falloff is
# over hundreds of units and the wattage has to scale with dim^2 or the part
# renders black. Positions are normalised to a fixed radius for the same reason.
LD = dim * 2.4
def place(v):
    return v.normalized() * LD
lamp("key",  place(cloc.normalized()*1.3 - side*1.0 + up*1.3), dim*dim*260, dim*0.55)
lamp("fill", place(cloc.normalized()*1.2 + side*1.7 - up*0.1), dim*dim*70,  dim*1.7)
lamp("rim",  place(-cloc.normalized()*1.5 + up*1.1),           dim*dim*130, dim*0.5)

s = bpy.context.scene
for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES'):
    try:
        s.render.engine = eng
        break
    except TypeError:
        continue
s.render.resolution_x = s.render.resolution_y = res
s.render.film_transparent = False
try:
    s.view_settings.look = 'AgX - Medium High Contrast'
except TypeError:
    pass
s.render.filepath = outfile
bpy.ops.render.render(write_still=True)
print("BLENDER_DONE")
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--res", type=int, default=1200)
    ap.add_argument("--outdir", default=os.path.join(HERE, "out"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "s.py")
        open(sp, "w").write(SCRIPT)
        for name, model, elev, azim in VIEWS:
            if args.only and args.only not in name:
                continue
            src = os.path.join(HERE, "out", model)
            if not os.path.exists(src):
                continue
            dst = os.path.join(args.outdir, f"view_{name}.png")
            r = subprocess.run([BLENDER, "--background", "--python", sp, "--",
                                src, dst, str(elev), str(azim), str(args.res)],
                               capture_output=True, text=True)
            if "BLENDER_DONE" not in r.stdout:
                print(r.stdout[-1200:], file=sys.stderr)
                sys.exit(f"blender failed on {name}")
            print("wrote", dst)


if __name__ == "__main__":
    main()
