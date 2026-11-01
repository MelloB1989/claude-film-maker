"""Eevee previews of him in his trousers and the default garment's tee (its shorts cut out, as in Unreal), the cloth
maps on (his_outfit_maps.py), in the props' preview convention: his_outfit.png (3/4 from front-right-above),
his_outfit_front.png, his_outfit_close.png (the waist, where the tee lies over the waistband), 1200x1200; also side,
back and the knee and hem. After agent-02's his_outfit_preview.py.
    blender -b --factory-startup -P his_outfit_preview.py -- --src <dir: his_trousers.fbx> --body <body.fbx>
        --face <face.fbx> --garment <garment.fbx> --maps <dir with T_His*> --out <dir>
His frame as exported: his left +X, his front -Y, up +Z; previews look at his front."""
import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
for k in ("--src", "--body", "--face", "--garment", "--maps", "--out"):
    ap.add_argument(k)
ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--cull", action="store_true", help="cull back faces as the engine does (shows flipped winding)")
ap.add_argument("--only", default="", help="comma-separated preview names")
A = ap.parse_args(argv)
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)


def load(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.type == "MESH":
            for m in list(o.modifiers):
                o.modifiers.remove(m)
            mw = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = mw
    meshes = [o for o in new if o.type == "MESH"]
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o)
    return meshes


def cloth(name, maps, tile_cm, roughness_scale=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = A.cull
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (100.0 / tile_cm, 100.0 / tile_cm, 1)
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])

    def img(k, non_color):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(os.path.join(A.maps, f"{maps}_{k}.png"))
        if non_color:
            t.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t
    nt.links.new(img("A", False).outputs["Color"], b.inputs["Base Color"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(img("N", True).outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(img("M", True).outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Red"], b.inputs["Roughness"])
    b.inputs["Sheen Weight"].default_value = 0.12
    return m


def plain(name, rgb, rough, metal=0.0, sss=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    m.use_backface_culling = A.cull
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
    return m


skin = plain("Skin", (0.36, 0.2, 0.13), 0.5, sss=0.15)
tee = plain("Tee", (0.032, 0.034, 0.038), 0.85)
tee.node_tree.nodes["Principled BSDF"].inputs["Sheen Weight"].default_value = 0.25
mats = {"M_Trousers": cloth("M_Trousers", "T_HisTwill", 1.0)}
for p in (A.body, A.face):
    for o in load(p):
        o.data.materials.clear()
        o.data.materials.append(skin)
for o in load(A.garment):  # the tee kept, the shorts cut out (their faces deleted)
    import bmesh
    short = {i for i, s_ in enumerate(o.material_slots) if s_.material and "short" in s_.material.name.lower()}
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in short], context="FACES")
    bm.to_mesh(o.data)
    bm.free()
    o.data.materials.clear()
    o.data.materials.append(tee)
for o in load(os.path.join(A.src, "his_trousers.fbx")):
    for i, s_ in enumerate(o.material_slots):
        base = s_.material.name.split(".")[0] if s_.material else ""
        if base in mats:
            o.material_slots[i].material = mats[base]
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = A.samples
sc.render.resolution_x = sc.render.resolution_y = 1200
sc.view_settings.view_transform = "AgX"
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.3, 0.28, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
sc.world = w
for name, loc, energy, size in (("key", (1.6, -2.2, 2.4), 150, 1.6), ("fill", (-2.2, -1.6, 1.6), 45, 2.5),
                                ("rim", (0.6, 2.2, 2.2), 120, 1.0)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.size = energy, size
    lo = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (Vector((0, 0, 1.1)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
cd = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
os.makedirs(A.out, exist_ok=True)
for name, d, at, lens, dist in (("his_outfit", (0.55, 1, -0.28), (0, 0, 0.92), 50, 4.6),
                                ("his_outfit_front", (0, 1, 0), (0, 0, 0.92), 50, 4.6),
                                ("his_outfit_close", (0.35, 1, -0.05), (0, -0.02, 1.0), 85, 1.6),
                                ("his_outfit_side", (1, 0, 0), (0, 0, 0.92), 50, 4.6),
                                ("his_outfit_back", (0, -1, 0), (0, 0, 0.92), 50, 4.6),
                                ("his_outfit_knee", (0.45, 1, -0.05), (0.1, 0.0, 0.5), 85, 1.6),
                                ("his_outfit_hem", (0.4, 1, -0.25), (0.1, 0.0, 0.14), 85, 1.4)):
    if A.only and name not in A.only.split(","):
        continue
    d = Vector(d).normalized()
    cd.lens = lens
    cam.location = Vector(at) - d * dist
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(A.out, name + ".png")
    bpy.ops.render.render(write_still=True)
print("preview done")
