"""music_combo — preview of the music corner: turntable (left), headphones on their stand (middle, back) and the
record crate (right) on a light-oak top, to compare with the concept. Render only, no FBX.

Run after turntable.py, headphones.py and record_crate.py (it appends their objects from out/<name>.blend):

    blender -b --factory-startup -P films/host-studio/props/music_combo.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

args = S.parse_args(__file__)
S.reset_scene()
cm = 0.01

# (name, position cm, yaw degrees): front of every prop toward +X, as in the concept
LAYOUT = [("turntable", (1.0, -40.0), 0.0), ("headphones", (-6.0, -6.0), 0.0), ("record_crate", (-2.0, 27.0), -4.0)]
for name, (x, y), yaw in LAYOUT:
    with bpy.data.libraries.load(os.path.join(args.out, name + ".blend")) as (src, dst):
        dst.objects = [name]
    ob = dst.objects[0]
    bpy.context.scene.collection.objects.link(ob)
    ob.matrix_world = Matrix.Translation((x * cm, y * cm, 0)) @ Matrix.Rotation(math.radians(yaw), 4, "Z")

# light-oak top, 130 x 55 cm, 2.5 cm thick, with preview grain along Y
oak = S.material("_Oak", (0.50, 0.34, 0.19), 0.5)
nt = oak.node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
tc = nt.nodes.new("ShaderNodeTexCoord")
mp = nt.nodes.new("ShaderNodeMapping")
mp.inputs["Scale"].default_value = (90.0, 3.0, 1.0)
nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
nz = nt.nodes.new("ShaderNodeTexNoise")
nz.inputs["Scale"].default_value = 1.0
nz.inputs["Detail"].default_value = 8.0
nz.inputs["Distortion"].default_value = 0.3
nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = (0.36, 0.23, 0.12, 1)
ramp.color_ramp.elements[1].color = (0.62, 0.44, 0.27, 1)
ramp.color_ramp.elements[0].position = 0.35
ramp.color_ramp.elements[1].position = 0.7
nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
top = S.box("_top", (-30 * cm, -70 * cm, -2.5 * cm), (25 * cm, 60 * cm, 0), oak)
S.bevel(top, 0.3 * cm, segments=3)
# warm plaster wall behind
wall = S.box("_wall", (-34 * cm, -120 * cm, -80 * cm), (-30 * cm, 120 * cm, 120 * cm),
             S.material("_Wall", (0.62, 0.52, 0.40), 0.9))

sc = bpy.context.scene
world = sc.world or bpy.data.worlds.new("World")
sc.world = world
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.20, 0.16, 0.12, 1)
bg.inputs["Strength"].default_value = 0.35


def area(name, loc, target, energy, size, color):
    light = bpy.data.lights.new(name, "AREA")
    light.shape = "DISK"
    light.size = size
    light.energy = energy
    light.color = color
    lo = bpy.data.objects.new(name, light)
    sc.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


area("_key", (1.2, -1.4, 1.1), (0, -0.1, 0.1), 70, 1.2, (1.0, 0.86, 0.70))      # window light, front left
area("_fill", (1.4, 0.8, 0.5), (0, 0, 0.1), 16, 1.5, (1.0, 0.93, 0.85))
area("_shelf", (0.0, 0.1, 0.75), (0, 0.1, 0.0), 14, 1.0, (1.0, 0.72, 0.45))      # warm shelf strip above

cam_data = bpy.data.cameras.new("_cam")
cam_data.lens = 42
cam = bpy.data.objects.new("_cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam
target = Vector((-0.02, -0.06, 0.11))
cam.location = target + Vector((1.0, -0.32, 0.36)).normalized() * 1.75
cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()

engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
sc.eevee.taa_render_samples = args.samples
for attr in ("use_shadows", "use_raytracing"):
    if hasattr(sc.eevee, attr):
        setattr(sc.eevee, attr, True)
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.render.resolution_x, sc.render.resolution_y = 1600, 1200
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = os.path.join(args.out, "music_combo.png")
if not args.no_render:
    bpy.ops.render.render(write_still=True)
