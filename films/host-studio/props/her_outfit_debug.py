"""Debug: wireframe close-ups of an exported garment (her_outfit), for checking edges.
    blender -b --factory-startup -P her_outfit_debug.py -- <fbx> <out prefix> <cx,cy,cz cm> <dir x,y,z> <ortho cm> ..."""
import sys
import bpy
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
bpy.ops.import_scene.fbx(filepath=a[0])
me = [o for o in bpy.data.objects if o.type == "MESH"][0]
for m in list(me.modifiers):
    me.modifiers.remove(m)
mw = me.matrix_world.copy(); me.parent = None; me.matrix_world = mw
w = me.copy(); w.data = me.data.copy(); bpy.context.scene.collection.objects.link(w)
mod = w.modifiers.new("w", "WIREFRAME"); mod.thickness = 0.0004; mod.use_replace = True
me.color = (0.9, 0.88, 0.82, 1); w.color = (0.1, 0.1, 0.3, 1)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "OBJECT"
sc.render.resolution_x = sc.render.resolution_y = 900
cd = bpy.data.cameras.new("c"); cd.type = "ORTHO"; cam = bpy.data.objects.new("c", cd)
sc.collection.objects.link(cam); sc.camera = cam
k = 2
while k + 2 < len(a):
    c = Vector([float(x) / 100 for x in a[k].split(",")]); d = Vector([float(x) for x in a[k + 1].split(",")]).normalized()
    cd.ortho_scale = float(a[k + 2]) / 100
    cam.location = c - d * 2; cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = f"{a[1]}_{(k - 2) // 3}.png"
    bpy.ops.render.render(write_still=True)
    k += 3
