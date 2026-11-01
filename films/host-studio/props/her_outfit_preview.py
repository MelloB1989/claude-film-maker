"""Eevee previews of her in her outfit, the cloth maps on (her_outfit_maps.py), in the props' preview convention:
her_outfit.png (3/4 from front-right-above), her_outfit_front.png, her_outfit_close.png (waist-up), 1200x1200.
    blender -b --factory-startup -P her_outfit_preview.py -- --src <dir: her_top.fbx, her_trousers.fbx> --body <body.fbx>
        --face <face.fbx> --maps <dir with T_Her*> --out <dir>
Her frame as exported: her left +X, her front -Y, up +Z; previews look at her front."""
import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
for k in ("--src", "--body", "--face", "--maps", "--out"):
    ap.add_argument(k)
ap.add_argument("--samples", type=int, default=48)
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
    b.inputs["Sheen Weight"].default_value = 0.3 if maps == "T_HerRib" else 0.1
    return m


def plain(name, rgb, rough, metal=0.0, sss=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
    return m


skin = plain("Skin", (0.42, 0.24, 0.16), 0.5, sss=0.15)
mats = {"M_Top": cloth("M_Top", "T_HerRib", 2.0), "M_Trousers": cloth("M_Trousers", "T_HerWool", 1.0),
        "M_Hardware": plain("M_Hardware", (0.9, 0.62, 0.28), 0.25, 1.0)}
for p in (A.body, A.face):
    for o in load(p):
        o.data.materials.clear()
        o.data.materials.append(skin)
for f in ("her_top.fbx", "her_trousers.fbx"):
    for o in load(os.path.join(A.src, f)):
        for i, s in enumerate(o.material_slots):
            base = s.material.name.split(".")[0] if s.material else ""
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
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5
sc.world = w
for name, loc, energy, size in (("key", (1.6, -2.2, 2.4), 320, 1.6), ("fill", (-2.2, -1.6, 1.6), 110, 2.5),
                                ("rim", (0.6, 2.2, 2.2), 200, 1.0)):
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
for name, d, at, lens, dist in (("her_outfit", (0.55, 1, -0.28), (0, 0, 0.92), 50, 4.4),
                                ("her_outfit_front", (0, 1, 0), (0, 0, 0.92), 50, 4.4),
                                ("her_outfit_close", (0.3, 1, -0.1), (0, 0, 1.18), 85, 2.6),
                                ("her_outfit_hip", (-0.5, 1, 0), (-0.12, -0.02, 0.92), 85, 1.4),
                                ("her_outfit_sleeve", (0.4, 1, -0.2), (0.2, 0.0, 1.25), 85, 1.0)):
    d = Vector(d).normalized()
    cd.lens = lens
    cam.location = Vector(at) - d * dist
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(A.out, name + ".png")
    bpy.ops.render.render(write_still=True)
print("preview done")
