"""smalls2_combo — the revised small shelf props together on a light-oak shelf, at real scale.

Builds the three glazed vases, the coin on its walnut stand and the pickaxe display exactly as
their own scripts do (nothing is exported here), stands them in a row against a plaster wall
and renders smalls2_combo.png (1800 x 1000) from the studio's shelf-camera direction: from about
+125 cm X, +40 cm Y, +15 cm Z relative to the props, looking at them.

    blender -b --factory-startup -P films/host-studio/props/smalls2_combo.py -- --out films/host-studio/props/out
"""
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402
import bitcoin_coin  # noqa: E402
import pickaxe  # noqa: E402
import vase_black  # noqa: E402
import vase_speckle  # noqa: E402
import vase_white  # noqa: E402

WALL_X = -0.12      # the wall plane; the shelf runs along Y
CAMERA = Vector((1.25, 0.40, 0.15))


def make(mod, name, origin=None, post=None, sharp=45):
    parts = mod.build()
    ob = M.bake(parts[0]) if len(parts) == 1 else S.join(name, parts)
    ob.name = name
    lo, hi = S.bbox(ob)
    S.set_origin(ob, origin if origin is not None else ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    S.tidy(ob, sharp)
    if post:
        post(ob)
    return ob


def place(ob, y, gap=0.015):
    """Stand the object on z = 0 centred at y, its back `gap` off the wall."""
    lo, hi = S.bbox(ob)
    ob.data.transform(Matrix.Translation((WALL_X + gap - lo.x, y - (lo.y + hi.y) / 2, -lo.z)))
    ob.data.update()


def main():
    args = S.parse_args(__file__)
    S.reset_scene()
    row = [
        (make(vase_speckle, "vase_speckle", sharp=60), -0.345, 0.02),
        (make(vase_white, "vase_white", sharp=60), -0.215, 0.025),
        (make(vase_black, "vase_black", sharp=60), -0.055, 0.015),
        (make(bitcoin_coin, "bitcoin_coin", origin=(0, 0, 0), post=bitcoin_coin.flat_normals, sharp=55), 0.105, 0.05),
        (make(pickaxe, "pickaxe", origin=(0, 0, 0), sharp=45), 0.255, 0.04),
    ]
    for ob, y, gap in row:
        place(ob, y, gap)
    obs = [r[0] for r in row]
    lo = Vector((min(S.bbox(o)[0].x for o in obs), min(S.bbox(o)[0].y for o in obs), 0.0))
    hi = Vector((max(S.bbox(o)[1].x for o in obs), max(S.bbox(o)[1].y for o in obs),
                 max(S.bbox(o)[1].z for o in obs)))
    M.glossy_stage(lo, hi, wall_gap=lo.x - WALL_X + 0.0003, light_scale=0.5)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 1800, 1000
    target = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0.085))
    cam = bpy.data.objects.new("_cam", bpy.data.cameras.new("_cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = target + CAMERA
    cam.rotation_euler = (-CAMERA).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 58
    cam.data.clip_start = 0.02
    sc.eevee.taa_render_samples = args.samples
    os.makedirs(args.out, exist_ok=True)
    sc.render.filepath = os.path.join(args.out, "smalls2_combo.png")
    bpy.ops.render.render(write_still=True)


main()
