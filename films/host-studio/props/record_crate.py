"""record_crate — a finger-jointed walnut crate of LPs, 36 cm wide (Y) x 26 cm deep (X) x 24 cm tall at the back,
with a cut-down 14 cm front and sides that sweep down from the back so the sleeves show. Front toward +X.

Inside, 14 LP sleeves (31.5 x 31.5 x 0.3 cm, slightly bowed with worn corners): 13 lean back against the back
board, each a little more than the one behind it; the front-most leans forward on the front board's top edge,
showing its whole front face, which is the label slot M_Label_SleeveFront (UV 0..1, upright from the front).
Origin: bottom centre of the crate.

    blender -b --factory-startup -P films/host-studio/props/record_crate.py -- --out films/host-studio/props/out
"""
import math
import os
import random
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


def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def _offset(poly, d):
    """Miter-offset a simple polygon (list of Vector 2D, counter-clockwise) inward by d."""
    n = len(poly)
    out = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        e1 = (p1 - p0).normalized()
        e2 = (p2 - p1).normalized()
        n1 = Vector((-e1.y, e1.x))
        n2 = Vector((-e2.y, e2.x))
        bis = n1 + n2
        if bis.length < 1e-9:
            out.append(p1 + n1 * d)
            continue
        bis.normalize()
        out.append(p1 + bis * (d / max(0.2, bis.dot(n1))))
    return out


def _fillet(poly, base, radius, segs=4):
    """Round the convex corners of `poly` (classified on `base`, so every inset ring gets the same vertex count)."""
    n = len(poly)
    out = []
    for i in range(n):
        b0, b1, b2 = base[i - 1], base[i], base[(i + 1) % n]
        e1, e2 = (b1 - b0).normalized(), (b2 - b1).normalized()
        turn = e1.x * e2.y - e1.y * e2.x
        if turn <= 0 or e1.dot(e2) > math.cos(math.radians(25)):
            out.append(poly[i])                      # concave or nearly straight: keep the corner
            continue
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        d1, d2 = (p0 - p1).normalized(), (p2 - p1).normalized()
        half = math.acos(max(-1.0, min(1.0, d1.dot(d2)))) / 2
        tdist = radius / math.tan(half)
        c = p1 + (d1 + d2).normalized() * (radius / math.sin(half))
        a0 = p1 + d1 * tdist - c
        a1 = p1 + d2 * tdist - c
        ang0, ang1 = math.atan2(a0.y, a0.x), math.atan2(a1.y, a1.x)
        da = (ang1 - ang0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(segs + 1):
            a = ang0 + da * k / segs
            out.append(c + Vector((math.cos(a), math.sin(a))) * radius)
    return out


def board(name, outline, axis, t0, t1, mat, grain, r=None, corner=0.35, segs=3):
    """A board from a 2D outline (simple polygon, cm) extruded from t0 to t1 along `axis` ('x' or 'y'), with a
    round-over of radius `r` on every edge: the outline's convex corners are filleted (`corner`), and the
    faces are rounded by stacking inset copies of the outline. For axis 'y' the outline is (x, z), for 'x' (y, z).
    (A bevel modifier flips thin triangles at the concave finger corners; this keeps the caps clean.)"""
    r = ROUND if r is None else r
    base = [Vector(p) for p in outline]
    area = sum(base[i - 1].x * base[i].y - base[i].x * base[i - 1].y for i in range(len(base)))
    if area < 0:
        base.reverse()
    prof = [(r * (1 - math.cos(math.pi / 2 * k / segs)), r * (1 - math.sin(math.pi / 2 * k / segs)))
            for k in range(segs + 1)]                              # (depth from the face, inset)
    levels = [(t0 + dz, ins) for dz, ins in prof] + [(t1 - dz, ins) for dz, ins in reversed(prof)]
    bm = bmesh.new()
    rings = []
    for t, ins in levels:
        ring2 = _fillet(_offset(base, ins), base, corner - ins)
        if axis == "y":
            rings.append([bm.verts.new((a * cm, t * cm, b * cm)) for a, b in ring2])
        else:
            rings.append([bm.verts.new((t * cm, a * cm, b * cm)) for a, b in ring2])
    m = len(rings[0])
    for ra, rb in zip(rings, rings[1:]):
        for i in range(m):
            j = (i + 1) % m
            bm.faces.new((ra[i], ra[j], rb[j], rb[i]))
    caps = [bm.faces.new(list(reversed(rings[0]))), bm.faces.new(rings[-1])]
    bmesh.ops.triangulate(bm, faces=caps, quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = S.obj_from_bm(bm, name, mat)
    return uv_box(ob, grain=grain)


def fingers(lo_edge, hi_edge, n, height, mine_even, g):
    """Edge of a finger-jointed board, as (offset, z) points going up: offset = hi_edge on this board's own
    fingers, lo_edge where the other board's fingers sit. `g` keeps 0.1 mm between the boards."""
    pts = []
    step = height / n
    for k in range(n):
        own = (k % 2 == 0) == mine_even
        e = hi_edge if own else lo_edge
        d = g / 2 if own else -g / 2
        z0 = k * step + (d if k > 0 else 0)
        z1 = (k + 1) * step - (d if k < n - 1 else 0)
        pts += [(e, z0), (e, z1)]
    return pts


# --------------------------------------------------------------------------- materials

WALNUT = S.material("M_Walnut", (0.15, 0.065, 0.032), 0.58)
wood_preview(WALNUT, (0.045, 0.018, 0.009), (0.20, 0.085, 0.040))
SLEEVES = [S.material("M_Sleeve1", (0.022, 0.021, 0.021), 0.7),       # black
           S.material("M_Sleeve2", (0.17, 0.035, 0.032), 0.72),       # oxblood
           S.material("M_Sleeve3", (0.48, 0.31, 0.09), 0.72),         # ochre
           S.material("M_Sleeve4", (0.13, 0.155, 0.18), 0.72),        # slate
           S.material("M_Sleeve5", (0.70, 0.65, 0.54), 0.75)]         # cream
LABEL = S.material("M_Label_SleeveFront", (0.70, 0.65, 0.54), 0.75)
label_preview(LABEL)

# --------------------------------------------------------------------------- crate (cm): X -13..13 (back..front), Y -18..18
DX, DY = 26.0, 36.0
T = 1.5                      # board thickness
H_BACK, H_FRONT = 24.0, 14.0
ROUND = 0.15                 # 1.5 mm round-over on every edge
G = 0.01                     # 0.1 mm between boards
XB, XF = -DX / 2, DX / 2     # outer back / front
YS = DY / 2
FLOOR = 1.8                  # top of the bottom board
N_BACK, N_FRONT = 8, 5       # fingers up the back and front corners

parts = []

# sides: own fingers at the even slots at both ends, top sweeping down from the back to the front height
top = []
x_hi, x_lo = XB + 5.0, XF - 7.5
for k in range(17):
    f = k / 16
    s = 0.5 - 0.5 * math.cos(math.pi * f)
    top.append((x_hi + (x_lo - x_hi) * f, H_BACK + (H_FRONT - H_BACK) * s))
back_edge = fingers(XB + T + G / 2, XB, N_BACK, H_BACK, True, G)          # (x, z) going up
front_edge = fingers(XF - T - G / 2, XF, N_FRONT, H_FRONT, True, G)
side_outline = back_edge + top + front_edge[::-1]
for sy in (-1, 1):
    y0, y1 = sorted((sy * YS, sy * (YS - T)))
    parts.append(board(f"side_{sy}", side_outline, "y", y0, y1, WALNUT, grain=0))

# back and front boards: own fingers at the odd slots, tabs out to the crate's outer width
for name, x0, x1, n, h in (("back", XB, XB + T, N_BACK, H_BACK), ("front", XF - T, XF, N_FRONT, H_FRONT)):
    right = fingers(YS - T - G / 2, YS, n, h, False, G)                 # (y, z) going up at +Y
    left = [(-y, z) for y, z in right]
    outline = right + list(reversed(left))
    parts.append(board(name, outline, "x", x0, x1, WALNUT, grain=1))

# bottom board between the four walls, set up 6 mm (as in a dado)
bot = S.box("bottom", ((XB + T + G) * cm, (-YS + T + G) * cm, (FLOOR - 1.2) * cm),
            ((XF - T - G) * cm, (YS - T - G) * cm, FLOOR * cm), WALNUT)
S.bevel(bot, ROUND * cm, segments=2, angle=30)
parts.append(uv_box(bot, grain=1))

# --------------------------------------------------------------------------- sleeves
SW = SH = 31.5
ST = 0.3
NU = NW = 10
EDGE_BULGE = 0.07
rng = random.Random(7)


def sleeve(name, body, front, place_m, bow=0.0, curl=(0.0, 0.0), curl_bottom=0.0, wave=0.0, label=False):
    """One LP sleeve built in local (u across, w up, n thickness: back face n = 0, front n = ST), cm, bottom edge
    centred at the origin; `place_m` (cm units) puts it in the crate. Front face gets `front`'s slot."""
    mats = [body] if front is body else [body, front]
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    ph = rng.uniform(0, 6.28)

    def offset(s, t):
        d = bow * math.sin(math.pi * s) * (0.35 + 0.65 * t)
        d += curl[0] * max(0.0, 1 - math.hypot(s, 1 - t) / 0.16) ** 2
        d += curl[1] * max(0.0, 1 - math.hypot(1 - s, 1 - t) / 0.16) ** 2
        d += curl_bottom * max(0.0, 1 - math.hypot(1 - s, t) / 0.12) ** 2
        d += wave * math.sin(9 * s + ph) * math.sin(math.pi * t)
        return d

    def pos(s, t, n, out=(0.0, 0.0)):
        u = (s - 0.5) * SW
        w = t * SH
        if (s in (0, 1)) and (t in (0, 1)):            # worn, slightly rounded corners
            u -= math.copysign(0.09, s - 0.5)
            w -= math.copysign(0.09, t - 0.5)
        return Vector((u + out[0], w + out[1], n + offset(s, t)))

    grid = {}
    for layer, n in (("b", 0.0), ("f", ST)):
        for i in range(NU + 1):
            for j in range(NW + 1):
                grid[layer, i, j] = bm.verts.new(pos(i / NU, j / NW, n))
    ring = [(i, 0) for i in range(NU)] + [(NU, j) for j in range(NW)] + \
           [(i, NW) for i in range(NU, 0, -1)] + [(0, j) for j in range(NW, 0, -1)]
    mid = []
    for i, j in ring:
        s, t = i / NU, j / NW
        ou = (-1 if i == 0 else 1 if i == NU else 0) * EDGE_BULGE
        ow = (-1 if j == 0 else 1 if j == NW else 0) * EDGE_BULGE
        if ou and ow:
            ou, ow = ou * 0.7, ow * 0.7
        mid.append(bm.verts.new(pos(s, t, ST / 2, (ou, ow))))
    for i in range(NU):
        for j in range(NW):
            f = bm.faces.new((grid["f", i, j], grid["f", i + 1, j], grid["f", i + 1, j + 1], grid["f", i, j + 1]))
            f.material_index = len(mats) - 1
            for lp in f.loops:
                k = [key for key, v in grid.items() if v is lp.vert][0]
                s, t = k[1] / NU, k[2] / NW
                lp[uvl].uv = (s, t) if label else (s * SW * cm, t * SH * cm)
            f = bm.faces.new((grid["b", i, j + 1], grid["b", i + 1, j + 1], grid["b", i + 1, j], grid["b", i, j]))
            for lp in f.loops:
                k = [key for key, v in grid.items() if v is lp.vert][0]
                lp[uvl].uv = ((1 - k[1] / NU) * SW * cm, k[2] / NW * SH * cm)
    m = len(ring)
    for k in range(m):
        k2 = (k + 1) % m
        a, b = ring[k], ring[k2]
        fa, fb = grid["f", a[0], a[1]], grid["f", b[0], b[1]]
        ba, bb = grid["b", a[0], a[1]], grid["b", b[0], b[1]]
        for f, vs in ((bm.faces.new((ba, bb, mid[k2], mid[k])), (0, 1, 1, 0)),
                      (bm.faces.new((mid[k], mid[k2], fb, fa)), (1, 2, 2, 1))):
            for lp, q in zip(f.loops, vs):
                idx = k if lp.vert in (ba, mid[k], fa) else k + 1
                lp[uvl].uv = (idx / m * 4 * SW * cm, q * ST / 2 * cm)
    bm.transform(Matrix.Diagonal((cm, cm, cm, 1)))
    bm.transform(place_m)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for mt in mats:
        me.materials.append(mt)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def placement(origin_xz, up_xz, y_off=0.0, roll=0.0):
    """Matrix taking sleeve local (u, w, n) to world: u -> +Y, w -> up (in XZ), n -> u x w; origin in cm."""
    up = Vector((up_xz[0], 0.0, up_xz[1])).normalized()
    u = Vector((0.0, 1.0, 0.0))
    n = u.cross(up)
    rot = Matrix((u, up, n)).transposed().to_4x4()
    roll_m = Matrix.Rotation(roll, 4, n)
    return Matrix.Translation(Vector((origin_xz[0], y_off, origin_xz[1])) * cm) @ roll_m @ rot


N_STACK = 13
TH0, DTH = math.radians(4.0), math.radians(0.95)
colours = [0, 3, 1, 0, 2, 4, 0, 3, 1, 0, 2, 3, 0]
lift = EDGE_BULGE + 0.02

# the rear-most sleeve rests on the back board's rounded top inner edge
rc = Vector((XB + T - ROUND, H_BACK - ROUND))           # centre of that round-over (x, z)
th = TH0
xb = (ROUND + 0.01 + (rc.y - FLOOR) * math.sin(th)) / math.cos(th) + rc.x
prev = None
for i in range(N_STACK):
    if i > 0:
        th = TH0 + i * DTH
        pth, pxb, pbow = prev
        # previous sleeve's front face: x as a function of z
        fx0 = pxb + ST * math.cos(pth)
        fz0 = FLOOR + lift + ST * math.sin(pth)
        z_top = FLOOR + lift + SH * math.cos(th)
        x_front = fx0 - (z_top - fz0) * math.tan(pth)
        xb = x_front + 0.08 + pbow + SH * math.sin(th)
    bow = rng.uniform(0.05, 0.13)
    curl = (rng.uniform(0.0, 0.3) if rng.random() < 0.5 else 0.0, rng.uniform(0.0, 0.3) if rng.random() < 0.4 else 0.0)
    m = placement((xb, FLOOR + lift), (-math.sin(th), math.cos(th)), y_off=rng.uniform(-0.45, 0.45),
                  roll=math.radians(rng.uniform(-0.35, 0.35)))
    mat = SLEEVES[colours[i]]
    ob = sleeve(f"sleeve_{i}", mat, mat, m, bow=bow, curl=curl, curl_bottom=0.0, wave=0.03)
    # roll can sink a bottom corner: lift the sleeve back onto the floor
    zmin = min(v.co.z for v in ob.data.vertices)
    ob.data.transform(Matrix.Translation((0, 0, FLOOR * cm + 0.0002 - zmin)))
    parts.append(ob)
    prev = (th, xb, max(bow, *curl))
print(f"stack: last sleeve bottom at x {xb:.2f} cm, lean {math.degrees(th):.1f} deg")

# the front sleeve leans forward on the front board's rounded top inner edge, face to the front
PHI = math.radians(9.0)
fc = Vector((XF - T + ROUND, H_FRONT - ROUND))
xf = fc.x - (ROUND + 0.01 + (fc.y - FLOOR - lift) * math.sin(PHI)) / math.cos(PHI)   # front face, bottom
n_f = Vector((math.cos(PHI), -math.sin(PHI)))
origin = Vector((xf, FLOOR + lift)) - n_f * ST
m = placement(origin, (math.sin(PHI), math.cos(PHI)))
front = sleeve("sleeve_front", SLEEVES[4], LABEL, m, bow=0.06, curl=(0.12, 0.0), curl_bottom=0.0, wave=0.015,
               label=True)
parts.append(front)
print(f"front sleeve: bottom of front face at x {xf:.2f} cm, top edge x {xf + SH * math.sin(PHI):.2f} cm")

ob = finish("record_crate", parts)

if not args.no_render:
    S.render_preview(ob, os.path.join(args.out, "record_crate.png"), (1.0, 0.85, 0.75), args.samples, lens=60)
    clear_preview()
    S.render_preview(ob, os.path.join(args.out, "record_crate_front.png"), (1.0, 0.0, 0.12), args.samples, lens=70)
