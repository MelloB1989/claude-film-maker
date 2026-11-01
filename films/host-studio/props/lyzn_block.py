"""lyzn_block — a 10 cm frosted acrylic cube with "lyzn" engraved into its front, like an LED desk block.

The cube is 10 x 10 x 10 cm with polished, rounded 1.6 mm edges (their own slot, M_AcrylicPolish, so the
bevels can be glossier than the satin-frosted faces, M_Acrylic). The word "lyzn" (Geist, the font of the
spines and the old decal) is cut 0.7 mm into the front (+X) face as real geometry: the letters' floors and
walls are M_AcrylicEngrave, the frosted white of a CNC/laser engraving, which is what catches the light (and
the block's inner glow) in a real one. The letters span 62 mm, centred on the face.

Origin: bottom centre. Slots: M_Acrylic, M_AcrylicPolish, M_AcrylicEngrave. UVs: world-scale box projection
(1 UV = 1 m) everywhere; on the front face (and the engraving) U runs to screen-right (+Y), V up (+Z).
Unreal side (unreal/studio.py): an opaque subsurface acrylic with a faint warm glow rising from the base.

    blender -b --factory-startup -P films/host-studio/props/lyzn_block.py -- --out films/host-studio/props/out
"""
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402

NAME = "lyzn_block"
CM, MM = M.CM, M.MM
SIZE = 10.0 * CM
R = 1.6 * MM            # the polished round-over on every edge
DEPTH = 0.7 * MM        # the engraving's depth
TEXT_W = 62.0 * MM      # the word's width on the face
TEXT = "lyzn"
WEIGHT = 0.018          # outline offset (em) that thickens Geist Regular's strokes
FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "fonts", "src", "Geist[wght].ttf")
WARM = (1.0, 0.78, 0.52)


# --------------------------------------------------------------------------- preview materials

def acrylic_material(name, roughness, glow, white=0.93, transmission=0.0):
    """Frosted acrylic for the Eevee preview: subsurface-scattering white, plus an inner LED glow that is
    brightest at the base and fades upwards (the Unreal material does the same with the pivot height)."""
    m = S.material(name, (white, white * 0.99, white * 0.97), roughness)
    b = M.principled(m)
    M.set_input(b, ["Subsurface Weight", "Subsurface"], 1.0)
    M.set_input(b, "Subsurface Radius", Vector((1.0, 0.85, 0.7)))
    M.set_input(b, "Subsurface Scale", 0.03)
    M.set_input(b, "IOR", 1.49)
    if transmission:  # frosted see-through depth (Eevee's raytraced refraction blurs it by the roughness)
        M.set_input(b, ["Transmission Weight", "Transmission"], transmission)
        for attr, val in (("use_raytrace_refraction", True), ("thickness_mode", "SLAB")):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    M.set_input(b, ["Coat Weight", "Clearcoat"], 0.0)
    if glow > 0:
        nt = m.node_tree
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Position"], sep.inputs[0])
        fade = nt.nodes.new("ShaderNodeMapRange")       # z 0 -> 1, z 10 cm -> 0.25
        fade.inputs["From Min"].default_value = 0.0
        fade.inputs["From Max"].default_value = SIZE
        fade.inputs["To Min"].default_value = 1.0
        fade.inputs["To Max"].default_value = 0.25
        nt.links.new(sep.outputs["Z"], fade.inputs["Value"])
        k = nt.nodes.new("ShaderNodeMath")
        k.operation = "MULTIPLY"
        k.inputs[1].default_value = glow
        nt.links.new(fade.outputs["Result"], k.inputs[0])
        M.set_input(b, ["Emission Color", "Emission"], (*WARM, 1.0))
        nt.links.new(k.outputs[0], b.inputs["Emission Strength"])
    return m


# --------------------------------------------------------------------------- geometry

def cube():
    """The rounded cube; the round-over faces carry slot 1 (polished)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=SIZE, matrix=Matrix.Translation((0, 0, SIZE / 2)))
    res = bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=R, offset_type="OFFSET",
                          segments=4, profile=0.5, affect="EDGES", clamp_overlap=True)
    for f in res["faces"]:
        f.material_index = 1
    return bm


def word():
    """The engraving cutter: the word as a solid from 0.7 mm under the front face to 1 mm in front of it,
    laid on the +X face (text X -> +Y, text Y -> +Z), centred, TEXT_W wide."""
    cu = bpy.data.curves.new("lyzn_text", "FONT")
    cu.body = TEXT
    cu.font = bpy.data.fonts.load(os.path.abspath(FONT))
    cu.size = 1.0
    cu.resolution_u = 10
    cu.align_x = "CENTER"
    cu.fill_mode = "BOTH"
    cu.offset = WEIGHT  # embolden the regular cut toward a medium: the engraving reads from across the room
    ob = bpy.data.objects.new("lyzn_text", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob, do_unlink=True)
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    k = TEXT_W / (max(xs) - min(xs))
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2  # the ink's box, so x-height letters sit centred
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.triangulate(bm, faces=bm.faces)  # the glyph faces may be concave ngons: triangles extrude cleanly
    front = SIZE / 2 + 1.0 * MM
    floor = SIZE / 2 - DEPTH
    # glyph plane (x, y) -> (front, (x - cx) k, SIZE/2 + (y - cy) k), then extrude back to the floor
    for v in bm.verts:
        v.co = Vector((front, (v.co.x - cx) * k, SIZE / 2 + (v.co.y - cy) * k))
    ext = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
    for v in [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]:
        v.co.x = floor
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.material_index = 0
    return bm, k


def build():
    acrylic = acrylic_material("M_Acrylic", 0.46, 0.22, white=0.90, transmission=0.7)
    polish = acrylic_material("M_AcrylicPolish", 0.05, 0.22, white=0.90, transmission=0.7)
    engrave = acrylic_material("M_AcrylicEngrave", 0.8, 2.2, white=0.97)

    block = M.obj(cube(), "block", [acrylic, polish, engrave])
    bm, _ = word()
    cutter = M.obj(bm, "cutter", [engrave])
    mod = block.modifiers.new("engrave", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    try:
        mod.material_mode = "TRANSFER"  # the cut faces take the cutter's material: M_AcrylicEngrave
    except Exception:
        pass
    block = M.bake(block)
    bpy.data.objects.remove(cutter, do_unlink=True)

    bm = bmesh.new()
    bm.from_mesh(block.data)
    names = [m.name for m in block.data.materials]
    eng = names.index("M_AcrylicEngrave")
    # belt and braces: whatever lies below the front face inside the word is engraving
    for f in bm.faces:
        c = f.calc_center_median()
        if c.x < SIZE / 2 - 0.05 * MM and c.x > SIZE / 2 - DEPTH - 0.05 * MM and abs(c.y) < TEXT_W / 2 + MM \
                and abs(c.z - SIZE / 2) < SIZE / 2 - 2 * R:
            f.material_index = eng
    M.box_uv(bm, scale=1.0, grain=1)
    bm.to_mesh(block.data)
    bm.free()
    block.data.update()
    return [block]


def face_front(ob):
    """Kept for smalls_combo.py (it passes this as `post`): the engraving is geometry now, nothing to flip."""
    return ob


def lyzn_light(ob):
    """The preview: a warm under-shelf strip above, as on the shelf."""
    lo, hi = S.bbox(ob)
    light = bpy.data.lights.new("_strip", "AREA")
    light.shape = "RECTANGLE"
    light.size, light.size_y = 0.6, 0.012
    light.energy = 18
    light.color = (1.0, 0.75, 0.5)
    lo_ = bpy.data.objects.new("_strip", light)
    bpy.context.scene.collection.objects.link(lo_)
    lo_.location = (hi.x + 0.04, 0, hi.z + 0.30)
    lo_.rotation_euler = (0.0, 0.25, 0.0)


VIEWS = [("", (1.0, -0.75, 0.55), 70, 1.25), ("_front", (1.0, 0.0, 0.08), 70, 1.2),
         ("_close", (1.0, -0.35, 0.25), 100, 1.3,
          (Vector((SIZE / 2 - DEPTH, -TEXT_W / 2, SIZE / 2 - 0.016)), Vector((SIZE / 2, TEXT_W / 2, SIZE / 2 + 0.016))))]

if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, origin=(0, 0, 0), sharp_angle=40, views=VIEWS, extras=lyzn_light)
