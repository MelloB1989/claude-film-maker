"""headphones — large over-ear headphones hanging on a matte black stand, cups facing sideways (along Y).

Stand: round weighted base 12 cm across, a 27 cm post and a curved saddle the headband cushion rests on (the
cushion is pressed into it a little). Headphones: black matte headband and cups, leather ear pads and headband
cushion, metal sliders and yokes. No logos. Total height ~32.5 cm.
Origin: bottom centre of the stand base.

    blender -b --factory-startup -P films/host-studio/props/headphones.py -- --out films/host-studio/props/out
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


# --------------------------------------------------------------------------- local helpers

def bake(ob):
    """Apply an object's modifiers in place."""
    if ob.modifiers:
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        old = ob.data
        ob.modifiers.clear()
        ob.data = me
        bpy.data.meshes.remove(old)
    return ob


def uv_layer(me):
    return me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")


def uv_box(ob, grain=None):
    """World-scale box projection, 1 UV unit = 1 m. U runs along axis `grain` (0, 1, 2) wherever the face
    plane contains it (default: the part's longest dimension), so wood grain follows the board."""
    bake(ob)
    me = ob.data
    uvl = uv_layer(me)
    mw = ob.matrix_world
    cos = [mw @ v.co for v in me.vertices]
    ext = [max(c[i] for c in cos) - min(c[i] for c in cos) for i in range(3)]
    if grain is None:
        grain = max(range(3), key=lambda i: ext[i])
    rot = mw.to_3x3()
    for p in me.polygons:
        n = rot @ p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        plane = [i for i in range(3) if i != ax]
        u = grain if grain in plane else max(plane, key=lambda i: ext[i])
        v = plane[0] if plane[1] == u else plane[1]
        for li in p.loop_indices:
            c = cos[me.loops[li].vertex_index]
            uvl.data[li].uv = (c[u], c[v])
    return ob


def uv_planar(ob, origin, uax, vax, size_u, size_v, slot=None):
    """Planar projection: `origin` maps to UV (0.5, 0.5), size_u x size_v metres span 0..1.
    With `slot`, only faces of that material index are mapped."""
    bake(ob)
    me = ob.data
    uvl = uv_layer(me)
    mw = ob.matrix_world
    o, ua, va = Vector(origin), Vector(uax).normalized(), Vector(vax).normalized()
    for p in me.polygons:
        if slot is not None and p.material_index != slot:
            continue
        for li in p.loop_indices:
            c = mw @ me.vertices[me.loops[li].vertex_index].co - o
            uvl.data[li].uv = (c.dot(ua) / size_u + 0.5, c.dot(va) / size_v + 0.5)
    return ob


def weighted_normals(ob):
    """Face-area weighted custom normals: big flat faces stay flat next to their bevels."""
    m = ob.modifiers.new("WN", "WEIGHTED_NORMAL")
    m.mode = "FACE_AREA"
    m.weight = 50
    m.keep_sharp = True
    bake(ob)


def flatten_panels(ob, min_area=1.5e-4, tol=0.5):
    """Pin the normals of flat panels (coplanar face groups of at least `min_area` m2) to their plane, so a cap
    split into thin triangles shades flat instead of picking up its rounded edges."""
    me = ob.data
    loop_n = [Vector(c.vector) for c in me.corner_normals]
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    cos_tol = math.cos(math.radians(tol))
    seen = set()
    for f in bm.faces:
        if f.index in seen:
            continue
        group, stack = [], [f]
        seen.add(f.index)
        while stack:
            g = stack.pop()
            group.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen and h.normal.dot(f.normal) > cos_tol:
                        seen.add(h.index)
                        stack.append(h)
        if sum(g.calc_area() for g in group) < min_area:
            continue
        for g in group:
            for li in me.polygons[g.index].loop_indices:
                loop_n[li] = f.normal.copy()
    bm.free()
    me.normals_split_custom_set(loop_n)


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def wood_preview(mat, dark, light, rings=110.0):
    """Preview-only walnut grain driven by the UVs (streaks run along U), so the grain direction is checkable."""
    nt = mat.node_tree
    bsdf = principled(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (4.0, rings, 1.0)
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.3
    nz.inputs["Detail"].default_value = 9.0
    nz.inputs["Roughness"].default_value = 0.62
    nz.inputs["Distortion"].default_value = 0.35
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.36
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].position = 0.66
    ramp.color_ramp.elements[1].color = (*light, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])


GLYPHS = {
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
}


def uv_test_image(name="_uv_test", n=512):
    """Preview-only UV test card: grid, red border, blue arrow and the word UP, green bottom-left corner."""
    import numpy as np
    a = np.ones((n, n, 4), dtype=np.float32) * np.array([0.86, 0.84, 0.78, 1.0], dtype=np.float32)
    a[::32, :, :3] = 0.6
    a[:, ::32, :3] = 0.6
    b = n // 40
    a[:b, :, :3] = a[-b:, :, :3] = a[:, :b, :3] = a[:, -b:, :3] = (0.75, 0.05, 0.05)
    a[b:b + n // 8, b:b + n // 8, :3] = (0.1, 0.6, 0.15)          # bottom-left (UV 0, 0)
    blue = (0.08, 0.2, 0.75)
    cx = n // 2
    a[int(n * 0.18):int(n * 0.55), cx - n // 28:cx + n // 28, :3] = blue      # shaft
    for y in range(int(n * 0.55), int(n * 0.78)):                            # head
        half = int((n * 0.78 - y) * 0.55)
        a[y, cx - half:cx + half, :3] = blue
    px = n // 40
    x0 = cx - 11 * px // 2 * 1
    for gi, ch in enumerate("UP"):
        for r, row in enumerate(GLYPHS[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    y = int(n * 0.92) - r * px
                    x = x0 + gi * 6 * px + c * px
                    a[y - px:y, x:x + px, :3] = (0.05, 0.05, 0.05)
    img = bpy.data.images.new(name, n, n, alpha=False)
    img.pixels.foreach_set(a.ravel())
    img.pack()
    return img


def label_preview(mat):
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.get("_uv_test") or uv_test_image()
    nt.links.new(tex.outputs["Color"], principled(mat).inputs["Base Color"])


def clear_preview():
    for o in list(bpy.data.objects):
        if o.name.startswith("_"):
            bpy.data.objects.remove(o, do_unlink=True)


def lathe_at(name, profile, mats, centre, segs=64, mat_split=None, axis=None):
    """S.lathe with the axis through `centre` (local Z = world Z unless `axis` = (p0, p1))."""
    if axis is None:
        m = Matrix.Translation(Vector(centre))
    else:
        m, _ = S.frame_to(*axis)
    return S.lathe(name, [(r * cm, z * cm) for r, z in profile], mats, segs=segs, matrix=m, mat_split=mat_split)


def add_slot(ob, mat):
    ob.data.materials.append(mat)
    return len(ob.data.materials) - 1

# --------------------------------------------------------------------------- finish: join, origin, normals, export, previews


def finish(name, parts, sharp_angle=40):
    ob = S.join(name, parts)
    S.set_origin(ob, (0, 0, 0))
    S.tidy(ob, sharp_angle)
    weighted_normals(ob)
    flatten_panels(ob)
    os.makedirs(args.out, exist_ok=True)
    fbx = os.path.join(args.out, name + ".fbx")
    S.export_fbx(ob, fbx)
    lo, hi = S.bbox(ob)
    print("=" * 60)
    print(f"{name}: exported {fbx}")
    print(f"{name}: materials {[m.name for m in ob.data.materials]}")
    print(f"{name}: triangles {S.tri_count(ob)}")
    print(f"{name}: bbox cm  X {lo.x*100:.1f}..{hi.x*100:.1f}  Y {lo.y*100:.1f}..{hi.y*100:.1f}"
          f"  Z {lo.z*100:.1f}..{hi.z*100:.1f}")
    print("=" * 60)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(args.out, name + ".blend"), compress=True)
    return ob


def sweep_var(name, points, profile_at, mat, hint=(1, 0, 0), caps=True):
    """S.sweep with a per-point profile: profile_at(i) -> [(u, v)] (same length for every i)."""
    pts = [Vector(p) for p in points]
    n = len(pts)
    tans = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    nrm = Vector(hint) - Vector(hint).dot(tans[0]) * tans[0]
    nrm.normalize()
    bm = bmesh.new()
    rings = []
    for i in range(n):
        t = tans[i]
        nrm = (nrm - nrm.dot(t) * t).normalized()
        b = t.cross(nrm)
        rings.append([bm.verts.new(pts[i] + u * nrm + v * b) for u, v in profile_at(i)])
    m = len(rings[0])
    for i in range(n - 1):
        a, c = rings[i], rings[i + 1]
        for k in range(m):
            k2 = (k + 1) % m
            bm.faces.new((a[k], a[k2], c[k2], c[k]))
    if caps:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    return S.obj_from_bm(bm, name, mat)


def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def pillow(w, t, n=24, pu=0.55, pv=0.75):
    """Closed puffy cross-section, half-width w, thickness t, from v = 0 (top) to v = t (bottom)."""
    out = []
    for k in range(n):
        a = 2 * math.pi * k / n
        c, s = math.cos(a), math.sin(a)
        out.append((w * math.copysign(abs(c) ** pu, c), t / 2 - t / 2 * math.copysign(abs(s) ** pv, s)))
    return out


# --------------------------------------------------------------------------- materials

STAND = S.material("M_StandMetal", (0.022, 0.022, 0.023), 0.55, metallic=0.4)    # matte black powder coat
HP = S.material("M_HPBlack", (0.020, 0.020, 0.021), 0.62)                         # matte plastic
LEATHER = S.material("M_HPLeather", (0.016, 0.015, 0.015), 0.42)                  # protein leather
HPMETAL = S.material("M_HPMetal", (0.55, 0.55, 0.56), 0.30, metallic=1.0)         # brushed steel


def leather_preview(mat):
    nt = mat.node_tree
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 900.0
    nz.inputs["Detail"].default_value = 3.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    bump.inputs["Distance"].default_value = 0.0002
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], principled(mat).inputs["Normal"])


leather_preview(LEATHER)
parts = []

# --------------------------------------------------------------------------- headband geometry (cm), in the YZ plane
ZB = 32.2           # band centreline at the top
H_ARC = 8.4         # band drop from the top to where it enters the sliders
A = 8.8             # half-width of the band = y of the cup pivots
ZS = ZB - H_ARC     # slider housings' top
EXP = 2.5           # superellipse exponent (squarer than a semicircle)
BAND_T, BAND_W = 0.75, 3.2
CUSH_T, CUSH_W = 1.7, 2.9
CUSH_Y = 6.2        # cushion runs |y| < CUSH_Y


def band_pt(th):
    s, c = math.sin(th), math.cos(th)
    return Vector((0.0, A * math.copysign(abs(s) ** (2 / EXP), s), ZS + H_ARC * abs(c) ** (2 / EXP)))


NB = 90
ths = [-math.pi / 2 + math.pi * i / NB for i in range(NB + 1)]
band_line = [band_pt(t) for t in ths]
band_line = [band_line[0] - Vector((0, 0, 0.7))] + band_line + [band_line[-1] - Vector((0, 0, 0.7))]
band = S.sweep("band", [p * cm for p in band_line],
               [(u * cm, v * cm) for u, v in S.rounded_rect(BAND_W, BAND_T, 0.26, segs=3)], HP, hint=(1, 0, 0))
parts.append(uv_box(band))

# cushion: under the band (sweep v > 0 is towards the inside of the arc), thickest at the top
cush_ths = [t for t in ths if abs(band_pt(t).y) < CUSH_Y]


def cush_t(i):
    y = band_pt(cush_ths[i]).y
    return 0.35 + (CUSH_T - 0.35) * smoothstep(CUSH_Y, CUSH_Y - 2.2, abs(y))


def cush_profile(i):
    t = cush_t(i)
    w = CUSH_W / 2 * (0.82 + 0.18 * smoothstep(0.35, CUSH_T, t))
    return [(u * cm, (BAND_T / 2 - 0.02 + v) * cm) for u, v in pillow(w, t)]


cushion = sweep_var("cushion", [band_pt(t) * cm for t in cush_ths], cush_profile, LEATHER, hint=(1, 0, 0))

# inner surface of the cushion at x = 0, sampled along the arc (for the stand's saddle)
inner = []
for i, th in enumerate(cush_ths):
    p = band_pt(th)
    q = band_pt(min(th + 1e-4, math.pi / 2))
    t = (q - p).normalized()
    b = t.cross(Vector((1, 0, 0)))
    inner.append((p + b * (BAND_T / 2 - 0.02 + cush_t(i)), b))

COMP = 0.28                     # how far the saddle presses into the cushion at the top
SAD_Y = 4.9


def comp(y):
    return COMP * (1 - (y / 4.4) ** 2)


saddle_top = [(p - b * comp(p.y), b) for p, b in inner if abs(p.y) <= SAD_Y]
SAD_T, SAD_W = 0.9, 2.4


def sad_profile(i):
    y = saddle_top[i][0].y
    k = 1.0 - 0.3 * smoothstep(3.5, SAD_Y, abs(y))
    return [(u * k * cm, (v * k + SAD_T / 2) * cm) for u, v in S.rounded_rect(SAD_W, SAD_T, 0.38, segs=4)]


saddle = sweep_var("saddle", [p * cm for p, b in saddle_top], sad_profile, STAND, hint=(1, 0, 0))
S.bevel(saddle, 0.12 * cm, segments=2, angle=40)
parts.append(uv_box(saddle))

# press the cushion onto the saddle: lift what is inside it, bulge it sideways a little
sy = [p.y for p, b in saddle_top]
sz = [p.z for p, b in saddle_top]


def saddle_z(y):
    for k in range(len(sy) - 1):
        if sy[k] <= y <= sy[k + 1]:
            f = (y - sy[k]) / (sy[k + 1] - sy[k])
            return sz[k] + f * (sz[k + 1] - sz[k])
    return None


R_EDGE = 0.38
for v in cushion.data.vertices:
    x, y, z = v.co.x / cm, v.co.y / cm, v.co.z / cm
    zt = saddle_z(y)
    if zt is None or comp(y) <= 0:
        continue
    ax = abs(x)
    flat = SAD_W / 2 - R_EDGE
    if ax < flat:
        drop = 0.0
    elif ax < SAD_W / 2:
        drop = R_EDGE - math.sqrt(max(0.0, R_EDGE ** 2 - (ax - flat) ** 2))
    else:
        drop = None
    zt += 0.02
    if drop is not None and z < zt - drop:
        lift = zt - drop - z
        v.co.z = (zt - drop) * cm
        v.co.x = x * (1 + 0.10 * lift / COMP) * cm
    elif drop is None and z < zt:
        v.co.x = x * (1 + 0.06 * smoothstep(0, 1, comp(y) / COMP)) * cm
parts.append(uv_box(cushion))

# --------------------------------------------------------------------------- stand: weighted base, post, neck under the saddle
BASE_R, BASE_H = 6.0, 1.8
base_profile = [(0, 0.12), (5.3, 0.12), (5.45, 0.0), (5.85, 0.0), (5.97, 0.08), (6.0, 0.22), (6.0, 1.12),
                (5.96, 1.32), (5.84, 1.48), (5.62, 1.58), (4.0, 1.68), (2.0, 1.76), (1.15, 1.80), (0, 1.80)]
parts.append(uv_box(lathe_at("base", base_profile, [STAND], (0, 0, 0), segs=96)))
POST_R = 0.85
post_top = saddle_top[len(saddle_top) // 2][0].z - SAD_T + 0.3
collar = [(0, 1.7), (1.25, 1.7), (1.22, 1.92), (1.08, 2.1), (0.94, 2.3), (POST_R, 2.55), (POST_R, post_top - 0.9),
          (0.92, post_top - 0.55), (1.08, post_top - 0.2), (1.15, post_top), (0, post_top)]
parts.append(uv_box(lathe_at("post", collar, [STAND], (0, 0, 0), segs=40)))

# --------------------------------------------------------------------------- per side: slider housing, slider, yoke, cup
PAD_IN = 5.2                 # pad faces at y = +-5.2
PAD_D = 2.4
SHELL_R = 5.0
Y_RAD = SHELL_R + 0.5        # yoke centreline radius
HOUSE_Z0 = ZS - 1.9
YOKE_TOP = HOUSE_Z0 - 1.5
CZ = YOKE_TOP - Y_RAD        # cup centre height

PADK = SHELL_R / 4.75
pad_profile = [  # (r, y from the pad face), outer back -> face -> inner back
    (4.45, PAD_D + 0.02), (4.62, PAD_D - 0.25), (4.74, PAD_D - 0.8), (4.76, 1.2), (4.70, 0.75), (4.55, 0.42),
    (4.32, 0.18), (4.0, 0.05), (3.6, 0.0), (3.2, 0.0), (2.85, 0.06), (2.6, 0.22), (2.45, 0.5), (2.38, 0.9),
    (2.36, 1.4), (2.40, PAD_D - 0.5), (2.5, PAD_D - 0.2), (2.62, PAD_D + 0.02),
    (4.45, PAD_D + 0.02),                                    # closed back (inside the shell)
]
pad_profile = [(2.4 + (r - 2.4) * PADK if r > 2.4 else r, y) for r, y in pad_profile]
shell_profile = [  # (r, y from the pad face): baffle, shell side, metal bezel, outer plate
    (0, PAD_D - 0.35), (2.7, PAD_D - 0.35), (2.7, PAD_D - 0.05), (4.55, PAD_D - 0.05),
    (4.66, PAD_D + 0.15), (SHELL_R, PAD_D + 0.6), (SHELL_R, PAD_D + 1.15), (4.68, PAD_D + 1.6), (4.5, PAD_D + 1.95),
    (4.22, PAD_D + 2.18), (3.98, PAD_D + 2.3),
    (3.94, PAD_D + 2.38), (3.78, PAD_D + 2.42), (3.62, PAD_D + 2.38),            # bezel ring
    (3.55, PAD_D + 2.34), (2.5, PAD_D + 2.4), (0, PAD_D + 2.44),
]


shell_profile = [(r if r <= 2.7 or r == SHELL_R else 2.7 + (r - 2.7) * PADK, y) for r, y in shell_profile]


def shell_slot(i):
    if i <= 2:
        return 0            # baffle cloth: plastic slot (dark)
    return 1 if 10 <= i <= 13 else 0


def lathe_y(name, profile, mats, side, segs=72, mat_split=None):
    """Lathe around the cup axis (along Y); profile y is measured outward from the pad face."""
    y0 = side * PAD_IN
    prof = [(r, y - 1.0) for r, y in profile]
    return lathe_at(name, prof, mats, None, segs=segs, mat_split=mat_split,
                    axis=((0, (y0) * cm, CZ * cm), (0, (y0 + 2 * side) * cm, CZ * cm)))


for side in (-1, 1):
    tag = "L" if side < 0 else "R"
    ys = side * A
    # slider housing at the band end
    house = S.prism(f"house_{tag}", S.rounded_rect(3.5 * cm, 1.25 * cm, 0.45 * cm, segs=4),
                    (0, ys * cm, HOUSE_Z0 * cm), (0, ys * cm, (ZS + 0.35) * cm), HP, up=(1, 0, 0))
    S.bevel(house, 0.12 * cm, segments=3, angle=30)
    parts.append(uv_box(house))
    # slider bar
    bar = S.prism(f"slider_{tag}", S.rounded_rect(1.0 * cm, 0.26 * cm, 0.1 * cm, segs=2),
                  (0, ys * cm, (YOKE_TOP + 0.3) * cm), (0, ys * cm, (HOUSE_Z0 + 0.4) * cm), HPMETAL, up=(1, 0, 0))
    parts.append(uv_box(bar))
    # yoke: an arc over the cup in the XZ plane, pivots front and back
    yoke_pts = [(Y_RAD * math.cos(a) * cm, ys * cm, (CZ + Y_RAD * math.sin(a)) * cm)
                for a in (math.pi * k / 48 for k in range(49))]
    yoke = S.sweep(f"yoke_{tag}", yoke_pts, [(u * cm, v * cm) for u, v in S.rounded_rect(0.85, 0.42, 0.16, segs=2)],
                   HPMETAL, hint=(0, 1, 0))
    parts.append(uv_box(yoke))
    parts.append(uv_box(lathe_at(f"yoke_hub_{tag}", [(0, -0.3), (0.5, -0.3), (0.58, -0.2), (0.58, 0.55),
                                                      (0.5, 0.65), (0, 0.65)], [HPMETAL], (0, ys * cm, YOKE_TOP * cm),
                                 segs=24)))
    for sx in (-1, 1):
        parts.append(uv_box(lathe_at(f"pivot_{tag}{sx}", [(0, -0.4), (0.52, -0.4), (0.6, -0.3), (0.6, 0.3),
                                                           (0.52, 0.4), (0, 0.4)], [HPMETAL], None, segs=24,
                                     axis=((sx * (SHELL_R - 0.25) * cm, ys * cm, CZ * cm),
                                           (sx * (Y_RAD + 0.35) * cm, ys * cm, CZ * cm)))))
    # cup: ear pad (leather) and shell (plastic + metal bezel)
    pad = lathe_y(f"pad_{tag}", pad_profile, [LEATHER], side, segs=168)
    # soft pleats where the leather gathers round the inner rim and the front face
    for v in pad.data.vertices:
        x, y, z = v.co.x / cm, v.co.y / cm, v.co.z / cm - CZ
        r = math.hypot(x, z)
        depth = abs(y) - PAD_IN
        w = smoothstep(3.9, 2.6, r) * smoothstep(PAD_D, 0.6, depth)
        if w <= 0:
            continue
        dr = 0.045 * w * math.sin(28 * math.atan2(z, x))
        v.co.x, v.co.z = (x * (1 + dr / r)) * cm, (z * (1 + dr / r) + CZ) * cm
    parts.append(uv_box(pad))
    shell = lathe_y(f"shell_{tag}", shell_profile, [HP, HPMETAL], side, segs=80, mat_split=shell_slot)
    parts.append(uv_box(shell))

# 3.5 mm socket under the left cup
sock_y = -(PAD_IN + PAD_D + 1.0)
parts.append(uv_box(lathe_at("socket", [(0, -0.05), (0.42, -0.05), (0.42, 0.25), (0.25, 0.3), (0.18, 0.3),
                                        (0.18, 0.2), (0, 0.2)], [HPMETAL], None, segs=20,
                             axis=((0, sock_y * cm, (CZ - SHELL_R + 0.45) * cm),
                                   (0, sock_y * cm, (CZ - SHELL_R - 0.05) * cm)))))

ob = finish("headphones", parts)

if not args.no_render:
    S.render_preview(ob, os.path.join(args.out, "headphones.png"), (1.0, 0.85, 0.75), args.samples, lens=60)
    clear_preview()
    S.render_preview(ob, os.path.join(args.out, "headphones_front.png"), (1.0, 0.0, 0.12), args.samples, lens=70)
