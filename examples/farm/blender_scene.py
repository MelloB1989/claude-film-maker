# A small animated, presenter-free Cycles scene for farm tests (film-farm acceptance A): a turntable of shapes under
# an area light, the camera orbiting, 96 frames. Run by the farm's Blender engine as the job's "build" script.
import math

import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 64
sc.cycles.use_denoising = False          # identical frames on every box: no denoiser in the loop
sc.cycles.seed = 7
sc.cycles.use_animated_seed = False
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 960, 540, 100
sc.frame_start, sc.frame_end = 1, 96
sc.render.fps = 24

world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.025, 0.035, 1)
sc.world = world

bpy.ops.mesh.primitive_plane_add(size=30)
floor = bpy.context.object
mf = bpy.data.materials.new("floor")
mf.use_nodes = True
mf.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.3, 0.3, 0.32, 1)
mf.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.35
floor.data.materials.append(mf)

colours = [(0.9, 0.2, 0.15), (0.15, 0.5, 0.9), (0.95, 0.75, 0.2), (0.3, 0.8, 0.4), (0.8, 0.3, 0.8)]
for i, c in enumerate(colours):
    a = i / len(colours) * 2 * math.pi
    (bpy.ops.mesh.primitive_uv_sphere_add if i % 2 else bpy.ops.mesh.primitive_cube_add)(
        location=(3 * math.cos(a), 3 * math.sin(a), 0.8))
    o = bpy.context.object
    m = bpy.data.materials.new(f"m{i}")
    m.use_nodes = True
    bs = m.node_tree.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = (*c, 1)
    bs.inputs["Metallic"].default_value = 0.6 if i % 2 else 0.0
    bs.inputs["Roughness"].default_value = 0.25
    o.data.materials.append(m)
    for f, z, rot in ((1, 0.8, 0), (48, 1.8 + 0.3 * i, math.pi), (96, 0.8, 2 * math.pi)):
        o.location.z = z
        o.rotation_euler = (rot * 0.3, rot * 0.5, rot)
        o.keyframe_insert("location", frame=f)
        o.keyframe_insert("rotation_euler", frame=f)

bpy.ops.object.light_add(type="AREA", location=(0, -4, 7))
L = bpy.context.object
L.data.energy, L.data.size = 1500, 4
L.rotation_euler = (math.radians(30), 0, 0)

bpy.ops.object.empty_add(location=(0, 0, 0.8))
pivot = bpy.context.object
bpy.ops.object.camera_add(location=(0, -10, 4.5))
cam = bpy.context.object
cam.data.lens = 35
cam.parent = pivot
t = cam.constraints.new("TRACK_TO")
t.target = pivot
t.track_axis, t.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
sc.camera = cam
for f, rz in ((1, 0), (96, math.radians(120))):
    pivot.rotation_euler = (0, 0, rz)
    pivot.keyframe_insert("rotation_euler", frame=f)
