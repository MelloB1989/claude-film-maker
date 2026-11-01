"""slat_panel — floor-to-ceiling walnut slat wall on a black acoustic felt backer.

170 cm wide (Y) x 300 cm tall (Z). A 1.2 cm black felt board (M_Felt) carries 27 solid walnut
slats (M_Walnut), each 4.4 cm wide x 2.2 cm deep, with ~1.9 cm gaps, running the full height and
rounded 1 mm on every edge. Each slat's depth and each gap vary by up to +-0.5 mm (no bowing).
The felt shows 0.9 cm past the outer slats, half a gap, as on real slat panels, so two panels
butt together with an even rhythm. No top cap: the slats run into the ceiling as in the concept.

Origin: bottom centre of the BACK face (the face against the wall); the panel grows towards +X.
UVs: world scale (1 UV unit = 1 m), U along each slat's length (the grain), each slat shifted
by a random offset so no two slats share the same stretch of texture.

    blender -b --factory-startup -P films/host-studio/props/slat_panel.py -- --out films/host-studio/props/out

karma_sign.py imports build() from here for the slat_sign_combo.png preview.
"""
import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

cm = 0.01
mm = 0.001

WIDTH = 170 * cm
HEIGHT = 300 * cm
FELT_T = 1.2 * cm
SLAT_W = 4.4 * cm
SLAT_D = 2.2 * cm
GAP = 1.9 * cm
N_SLATS = 27            # 27 x 4.4 + 26 x 1.9 = 168.2 cm, leaving 0.9 cm of felt each side
EDGE_R = 1.0 * mm
JITTER = 0.5 * mm       # depth and gap variation (+-)
SINK = 0.2 * mm         # slats sit 0.2 mm into the felt: no coplanar faces at the glue line


# --------------------------------------------------------------------------- materials (preview look)

def walnut_material(name="M_Walnut"):
    """Oiled American walnut. Grain from the UVs (stripes along U) so the preview shows UV direction."""
    m = S.material(name, (0.13, 0.058, 0.03), 0.48)
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    uv = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
    # grain runs along U: stretch every feature along the board
    mp.inputs["Scale"].default_value = (0.025, 1.0, 1.0)
    fine = nt.nodes.new("ShaderNodeTexNoise")          # fine, irregular grain lines (~3-8 mm)
    fine.inputs["Scale"].default_value = 160.0
    fine.inputs["Detail"].default_value = 4.0
    fine.inputs["Roughness"].default_value = 0.65
    fine.inputs["Distortion"].default_value = 0.4
    nt.links.new(mp.outputs["Vector"], fine.inputs["Vector"])
    broad = nt.nodes.new("ShaderNodeTexNoise")         # broad colour drift between and along boards
    broad.inputs["Scale"].default_value = 9.0
    broad.inputs["Detail"].default_value = 3.0
    nt.links.new(mp.outputs["Vector"], broad.inputs["Vector"])
    sharpen = nt.nodes.new("ShaderNodeMapRange")
    sharpen.inputs["From Min"].default_value = 0.35
    sharpen.inputs["From Max"].default_value = 0.65
    nt.links.new(fine.outputs["Fac"], sharpen.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY_ADD"
    nt.links.new(sharpen.outputs["Result"], mix.inputs[0])
    mix.inputs[1].default_value = 0.45
    nt.links.new(broad.outputs["Fac"], mix.inputs[2])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (0.040, 0.017, 0.008, 1)
    ramp.color_ramp.elements[1].position = 0.95
    ramp.color_ramp.elements[1].color = (0.135, 0.060, 0.030, 1)
    nt.links.new(mix.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    rr = nt.nodes.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = 0.52
    rr.inputs["To Max"].default_value = 0.40
    nt.links.new(mix.outputs[0], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], bsdf.inputs["Roughness"])
    return m


def felt_material(name="M_Felt"):
    m = S.material(name, (0.011, 0.011, 0.012), 0.95)
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    for key, val in (("Sheen Weight", 0.25), ("Sheen Roughness", 0.7)):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = val
    return m


# --------------------------------------------------------------------------- mesh helpers

def rounded_box_bm(lo, hi, r, segs=3):
    """A box with every edge rounded (radius r)."""
    lo, hi = Vector(lo), Vector(hi)
    bm = bmesh.new()
    from mathutils import Matrix
    m = Matrix.Translation((lo + hi) / 2) @ Matrix.Diagonal((*(hi - lo), 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=r, offset_type="OFFSET",
                          segments=segs, profile=0.5, affect="EDGES", clamp_overlap=True)
    return bm


def box_uv(bm, grain_axis, offset=(0.0, 0.0), layer="UVMap"):
    """World-scale box projection: 1 UV unit = 1 m, U along `grain_axis` (0/1/2) where the face
    plane contains it, else along the face's longer in-plane axis."""
    uvl = bm.loops.layers.uv.get(layer) or bm.loops.layers.uv.new(layer)
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        plane = [i for i in range(3) if i != ax]
        if grain_axis in plane:
            ua = grain_axis
        else:
            ext = [max(v.co[i] for v in f.verts) - min(v.co[i] for v in f.verts) for i in plane]
            ua = plane[0] if ext[0] >= ext[1] else plane[1]
        va = plane[0] if ua == plane[1] else plane[1]
        for lp in f.loops:
            lp[uvl].uv = (lp.vert.co[ua] + offset[0], lp.vert.co[va] + offset[1])


def axis_aligned(f, tol=1e-4):
    return max(abs(c) for c in f.normal) > 1 - tol


def bm_object(bm, name, mat, round_test=lambda f: not axis_aligned(f)):
    """Object from bm; faces for which round_test(f) holds are tagged in a 'round' face attribute
    so shade() can keep the big flat faces flat and the roundings smooth."""
    bm.normal_update()
    tag = bm.faces.layers.int.get("round") or bm.faces.layers.int.new("round")
    for f in bm.faces:
        f[tag] = 1 if round_test(f) else 0
    return S.obj_from_bm(bm, name, mat)


def shade(ob, sharp_angle=40):
    """Smooth shading; sharp edges where a rounding face meets a plain face, and above sharp_angle.
    (Rounding faces are tagged with the 'round' face attribute.)"""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    tag = bm.faces.layers.int.get("round")
    lim = math.radians(sharp_angle)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if not e.is_manifold:
            e.smooth = False
            continue
        a, b = e.link_faces
        if tag is not None and a[tag] != b[tag]:
            e.smooth = False
        else:
            e.smooth = e.calc_face_angle(0.0) <= lim
    print(f"shade {ob.name}: tag={tag is not None} sharp edges {sum(1 for e in bm.edges if not e.smooth)}")
    bm.to_mesh(ob.data)
    bm.free()
    if "round" in ob.data.attributes:
        ob.data.attributes.remove(ob.data.attributes["round"])
    ob.data.update()


def clear_preview():
    """Remove the helper objects render_preview() adds (names starting with '_')."""
    for ob in list(bpy.data.objects):
        if ob.name.startswith("_"):
            bpy.data.objects.remove(ob, do_unlink=True)


# --------------------------------------------------------------------------- build

def build(seed=7):
    """Build the panel's parts (felt, slats) in final position. Returns the list of objects."""
    rnd = random.Random(seed)
    walnut = walnut_material()
    felt_m = felt_material()
    parts = []

    # felt backer: a 1.2 cm board, soft 1 mm rounded edges
    bm = rounded_box_bm((0, -WIDTH / 2, 0), (FELT_T, WIDTH / 2, HEIGHT), 1.0 * mm, segs=2)
    box_uv(bm, grain_axis=2)
    parts.append(bm_object(bm, "felt", felt_m))

    pitch = SLAT_W + GAP
    span = N_SLATS * SLAT_W + (N_SLATS - 1) * GAP
    for i in range(N_SLATS):
        yc = -span / 2 + SLAT_W / 2 + i * pitch
        if 0 < i < N_SLATS - 1:
            yc += rnd.uniform(-JITTER / 2, JITTER / 2)    # gaps vary up to +-0.5 mm
        depth = SLAT_D + rnd.uniform(-JITTER, JITTER)
        x0 = FELT_T - SINK
        bm = rounded_box_bm((x0, yc - SLAT_W / 2, 0), (FELT_T + depth, yc + SLAT_W / 2, HEIGHT),
                                       EDGE_R, segs=3)
        box_uv(bm, grain_axis=2, offset=(rnd.uniform(0, 4), rnd.uniform(0, 2)))
        parts.append(bm_object(bm, f"slat_{i:02d}", walnut))
    return parts


def make_panel(name="slat_panel", seed=7):
    ob = S.join(name, build(seed))
    S.set_origin(ob, (0, 0, 0))
    shade(ob)
    return ob


# --------------------------------------------------------------------------- main

if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    panel = make_panel()
    os.makedirs(args.out, exist_ok=True)
    fbx = os.path.join(args.out, "slat_panel.fbx")
    S.export_fbx(panel, fbx)
    lo, hi = S.bbox(panel)
    print("=" * 60)
    print(f"slat_panel: exported {fbx}")
    print(f"slat_panel: materials {[m.name for m in panel.data.materials]}")
    print(f"slat_panel: triangles {S.tri_count(panel)}")
    print(f"slat_panel: bbox cm  X {lo.x*100:.2f}..{hi.x*100:.2f}  Y {lo.y*100:.2f}..{hi.y*100:.2f}"
          f"  Z {lo.z*100:.2f}..{hi.z*100:.2f}")
    print("=" * 60)
    if not args.no_render:
        S.render_preview(panel, os.path.join(args.out, "slat_panel.png"), (1.0, 0.75, 0.45),
                         args.samples, lens=50)
        clear_preview()
        S.render_preview(panel, os.path.join(args.out, "slat_panel_front.png"), (1.0, 0.0, 0.0),
                         args.samples, lens=50)
        # close-up of the slat edges and gaps at the bottom right corner (quality check)
        clear_preview()
        sc = bpy.context.scene
        cam = bpy.data.objects.new("_cam", bpy.data.cameras.new("_cam"))
        sc.collection.objects.link(cam)
        sc.camera = cam
        cam.data.lens = 50
        target = Vector((0.03, WIDTH / 2 - 0.12, 1.2))
        cam.location = Vector((0.55, WIDTH / 2 + 0.22, 1.42))
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.clip_start = 0.01
        for nm, loc, energy in (("_k1", (1.2, 0.2, 2.2), 120), ("_k2", (0.8, 1.6, 1.0), 40)):
            ld = bpy.data.lights.new(nm, "AREA")
            ld.size = 0.8
            ld.energy = energy
            lo_ = bpy.data.objects.new(nm, ld)
            sc.collection.objects.link(lo_)
            lo_.location = loc
            lo_.rotation_euler = (target - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(args.out, "slat_panel_close.png")
        bpy.ops.render.render(write_still=True)
