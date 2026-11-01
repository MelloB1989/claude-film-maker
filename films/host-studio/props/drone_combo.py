"""drone_combo — preview only: the drone and its remote on a light-oak shelf 26 cm deep against a wall,
seen from slightly above and front-left. Builds both props with the same code as drone.py and
drone_remote.py; exports nothing.

    blender -b --factory-startup -P films/host-studio/props/drone_combo.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _drone_kit as K  # noqa: E402
import drone  # noqa: E402
import drone_remote  # noqa: E402

DEPTH, LENGTH, THICK = 0.26, 1.4, 0.04


def oak():
    """Light oak, grain along world Y (the shelf's length)."""
    m = S.material("_Oak", (0.62, 0.43, 0.25), 0.55)
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 0.025, 1.0)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 110.0
    wave.inputs["Distortion"].default_value = 14.0
    wave.inputs["Detail"].default_value = 4.0
    wave.inputs["Detail Scale"].default_value = 1.5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.50, 0.32, 0.17, 1)
    ramp.color_ramp.elements[1].color = (0.64, 0.45, 0.27, 1)
    ramp.color_ramp.elements[0].position = 0.2
    ramp.color_ramp.elements[1].position = 0.75
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def slab(name, lo, hi, mat, bevel=0.0):
    bm = bmesh.new()
    K.add_box(bm, lo, hi)
    ob = K.mk(name, bm, mat, bevel=bevel or None, segs=3, angle=40)
    return ob


def area(name, loc, target, energy, size, color=(1.0, 0.86, 0.7), shape="RECTANGLE", size_y=None):
    light = bpy.data.lights.new(name, "AREA")
    light.shape = shape
    light.size = size
    if size_y is not None:
        light.size_y = size_y
    light.energy = energy
    light.color = color
    ob = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = Vector(loc)
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def main():
    args = S.parse_args(__file__)
    S.reset_scene()
    d, _ = K.assemble("drone", drone.build())
    r, _ = K.assemble("drone_remote", drone_remote.build())
    d.location = (0.0, -0.06, 0.0)
    r.location = (0.035, 0.265, 0.0)
    r.rotation_euler = (0, 0, math.radians(-16))

    slab("shelf", (-DEPTH / 2, -LENGTH / 2, -THICK), (DEPTH / 2, LENGTH / 2, 0), oak(), bevel=0.002)
    wall = S.material("_Wall", (0.60, 0.53, 0.45), 0.9)
    slab("wall", (-DEPTH / 2 - 0.02, -3.0, -2.0), (-DEPTH / 2, 3.0, 2.0), wall)

    sc = bpy.context.scene
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        bg.inputs["Color"].default_value = (0.32, 0.27, 0.22, 1)
        bg.inputs["Strength"].default_value = 0.25
    area("_key", (0.9, -0.7, 0.9), (0, 0.05, 0), 38, 0.9)
    area("_fill", (0.8, 0.9, 0.35), (0, 0.05, 0.03), 9, 1.2, color=(0.95, 0.9, 0.85))
    area("_strip", (-0.10, 0.0, 0.42), (-0.10, 0.0, 0), 20, 1.4, shape="RECTANGLE", size_y=0.05,
         color=(1.0, 0.78, 0.5))

    cam_data = bpy.data.cameras.new("_cam")
    cam_data.lens = 42
    cam = bpy.data.objects.new("_cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    target = Vector((0.0, 0.045, 0.025))
    cam.location = target + Vector((0.62, -0.45, 0.33))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_data.clip_start = 0.01

    sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [
        e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = args.samples
    for attr in ("use_shadows", "use_raytracing"):
        if hasattr(sc.eevee, attr):
            setattr(sc.eevee, attr, True)
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1067
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    os.makedirs(args.out, exist_ok=True)
    sc.render.filepath = os.path.join(args.out, "drone_combo.png")
    if not args.no_render:
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
