"""gpu_frame — an older dual-fan graphics card mounted like a trophy in a slim black shadow-box frame.

Generic look-alike: no logos, brand names or printed text. Frame 32 cm (Y) x 20 cm (Z) outer, 6 cm deep,
glass front toward +X, standing upright and leaning 5 degrees back against the wall.
Origin: bottom centre of the frame's back edge (the edge it stands on).

    blender -b --factory-startup -P films/host-studio/props/gpu_frame.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

args = S.parse_args(__file__)
S.reset_scene()


# ---------------------------------------------------------------- mesh helpers (this prop only)

def add_box(bm, lo, hi, m=None):
    lo, hi = Vector(lo), Vector(hi)
    mat = Matrix.Translation((lo + hi) / 2) @ Matrix.Diagonal((*(hi - lo), 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=(m @ mat) if m else mat)


def add_cyl(bm, p0, p1, r, segs=16, r2=None, m=None):
    f, length = S.frame_to(p0, p1)
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r,
                          radius2=r if r2 is None else r2, depth=length, matrix=(m @ f) if m else f)


def add_poly(bm, outline, z0, z1, m=None):
    """Extrude a simple 2D outline (convex or not) along local Z."""
    m = m or Matrix()
    a = [bm.verts.new(m @ Vector((x, y, z0))) for x, y in outline]
    b = [bm.verts.new(m @ Vector((x, y, z1))) for x, y in outline]
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(a)))
    bm.faces.new(b)


def add_lathe(bm, prof, m=None, segs=24, closed=False, slots=None):
    """Revolve (r, z) points around local Z (r == 0 is a pole); `slots(i)` = material of band i."""
    m = m or Matrix()
    rings = []
    for r, z in prof:
        if r <= 1e-9:
            rings.append([bm.verts.new(m @ Vector((0, 0, z)))])
        else:
            rings.append([bm.verts.new(m @ Vector((r * math.cos(2 * math.pi * k / segs),
                                                   r * math.sin(2 * math.pi * k / segs), z)))
                          for k in range(segs)])
    n = len(rings)
    for i in range(n if closed else n - 1):
        a, b = rings[i], rings[(i + 1) % n]
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                vs = (a[0], b[k2], b[k])
            elif len(b) == 1:
                vs = (a[k], a[k2], b[0])
            else:
                vs = (a[k], a[k2], b[k2], b[k])
            f = bm.faces.new(vs)
            if slots:
                f.material_index = slots(i)


def add_tube(bm, pts, r, sides=10):
    """Round tube along a polyline (rotation-minimising frames), capped."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tans = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    nrm = tans[0].orthogonal().normalized()
    rings = []
    for i in range(n):
        t = tans[i]
        nrm = (nrm - nrm.dot(t) * t).normalized()
        b = t.cross(nrm)
        rings.append([bm.verts.new(pts[i] + r * (math.cos(2 * math.pi * k / sides) * nrm
                                                 + math.sin(2 * math.pi * k / sides) * b))
                      for k in range(sides)])
    for i in range(n - 1):
        a, c = rings[i], rings[i + 1]
        for k in range(sides):
            k2 = (k + 1) % sides
            bm.faces.new((a[k], a[k2], c[k2], c[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def mk(name, bm, mats, bevel=None, segs=2, angle=35, cut=None, weight=False):
    """Object from a bmesh, with an optional boolean cut and bevel, modifiers applied (local space)."""
    if not isinstance(mats, (list, tuple)):
        mats = [mats]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for mt in mats:
        me.materials.append(mt)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    cutter = None
    if cut is not None:
        bmesh.ops.recalc_face_normals(cut, faces=cut.faces)
        cme = bpy.data.meshes.new(name + "_cut")
        cut.to_mesh(cme)
        cut.free()
        cme.materials.append(mats[0])      # cut faces take the part's own material, no empty slot
        cutter = bpy.data.objects.new(name + "_cut", cme)
        bpy.context.scene.collection.objects.link(cutter)
        cutter.hide_render = True
        mod = ob.modifiers.new("cut", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.use_self = True            # cutters may overlap each other
        mod.use_hole_tolerant = True
        mod.object = cutter
    if bevel:
        mod = ob.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = segs
        if weight:
            mod.limit_method = "WEIGHT"
        else:
            mod.limit_method = "ANGLE"
            mod.angle_limit = math.radians(angle)
    if ob.modifiers:
        dg = bpy.context.evaluated_depsgraph_get()
        new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.clear()
        old = ob.data
        ob.data = new
        bpy.data.meshes.remove(old)
        new.name = name
    if cutter is not None:
        cme = cutter.data
        bpy.data.objects.remove(cutter, do_unlink=True)
        bpy.data.meshes.remove(cme)
    return ob


def place(objs, m):
    for o in objs:
        o.matrix_world = m @ o.matrix_world


def box_uv(bm, grain=None):
    """World-scale box projection, 1 UV unit = 1 m; U runs along `grain` (0/1/2 = X/Y/Z) where it can."""
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        k = max(range(3), key=lambda i: abs(n[i]))
        a, b = [i for i in range(3) if i != k]
        if grain is not None and grain == b:
            a, b = b, a
        for loop in f.loops:
            co = loop.vert.co
            loop[uv].uv = (co[a], co[b])


def finalize(ob, grain=None):
    """Bake the object transform into the mesh, triangulate n-gons, add UVs."""
    me = ob.data
    me.transform(ob.matrix_world)
    ob.matrix_world = Matrix.Identity(4)
    bm = bmesh.new()
    bm.from_mesh(me)
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    box_uv(bm, grain)
    bm.to_mesh(me)
    bm.free()
    return ob



def glass_mat(name):
    m = S.material(name, (0.9, 0.93, 0.92), 0.03, specular=0.35)
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Alpha"].default_value = 0.05
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND"),
                      ("use_transparency_overlap", False), ("show_transparent_back", False)):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    return m


# ---------------------------------------------------------------- materials
FRAME = S.material("M_FrameBlack", (0.018, 0.018, 0.019), 0.42)
GLASS = glass_mat("M_Glass")
BACKING = S.material("M_FrameBacking", (0.40, 0.36, 0.30), 0.92)
SHROUD = S.material("M_Shroud", (0.022, 0.022, 0.024), 0.38)
FAN = S.material("M_FanBlack", (0.016, 0.016, 0.017), 0.45)
METAL = S.material("M_Metal", (0.80, 0.62, 0.34), 0.32, metallic=1.0)      # brass-toned bracket, as in the concept
GOLD = S.material("M_Gold", (1.0, 0.74, 0.36), 0.2, metallic=1.0)
ACCENT = S.material("M_AccentGold", (0.92, 0.64, 0.26), 0.28, metallic=1.0)
PCB = S.material("M_PcbBlack", (0.02, 0.024, 0.022), 0.33)
SINK = S.material("M_Heatsink", (0.78, 0.78, 0.80), 0.35, metallic=1.0)
COPPER = S.material("M_Copper", (0.93, 0.48, 0.30), 0.3, metallic=1.0)
PORT = S.material("M_PortMetal", (0.78, 0.78, 0.79), 0.26, metallic=1.0)
PLASTIC = S.material("M_PlasticBlack", (0.02, 0.02, 0.022), 0.5)

cm = 0.01

# ---------------------------------------------------------------- shadow-box frame (cm, upright)
FW, FH, FD = 32.0, 20.0, 6.0
# moulding profile: (w inward from the outer face, d back from the front face); glass groove and back rabbet
PROFILE = [(0.0, 0.0), (1.6, 0.0), (1.6, 0.6), (1.3, 0.6), (1.3, 0.8), (1.6, 0.8), (1.6, 5.4), (1.3, 5.4),
           (1.3, FD), (0.0, FD)]


def member(c, a, i, length):
    """One mitred moulding member: outer-face centre line c, along a, inward i."""
    bm = bmesh.new()
    a, i, c = Vector(a), Vector(i), Vector(c)
    ends = []
    for s in (-1, 1):
        ends.append([bm.verts.new(c + a * s * (length / 2 - w - 0.004) + i * w + Vector((FD - d, 0, 0)))
                     for w, d in PROFILE])
    n = len(PROFILE)
    for k in range(n):
        k2 = (k + 1) % n
        bm.faces.new((ends[0][k], ends[0][k2], ends[1][k2], ends[1][k]))
    bm.faces.new(list(reversed(ends[0])))
    bm.faces.new(ends[1])
    return mk("frame_member", bm, FRAME, bevel=0.07, segs=2)


frame = [member((0, 0, FH), (0, 1, 0), (0, 0, -1), FW), member((0, 0, 0), (0, 1, 0), (0, 0, 1), FW),
         member((0, -FW / 2, FH / 2), (0, 0, 1), (0, 1, 0), FH),
         member((0, FW / 2, FH / 2), (0, 0, 1), (0, -1, 0), FH)]
frame_grain = [1, 1, 2, 2]

bm = bmesh.new()
add_box(bm, (FD - 0.78, -FW / 2 + 1.35, 1.35), (FD - 0.62, FW / 2 - 1.35, FH - 1.35))
glass = mk("glass", bm, GLASS, bevel=0.03, segs=1)
bm = bmesh.new()
add_box(bm, (FD - 5.94, -FW / 2 + 1.35, 1.35), (FD - 5.41, FW / 2 - 1.35, FH - 1.35))
backing = mk("backing", bm, BACKING, bevel=0.05, segs=1)
BACK_FACE = FD - 5.41            # x of the backing board's front (linen) face

# ---------------------------------------------------------------- the card (cm, flat: u along, v up, w out)
CL = 27.0
FAN_C = [(6.4, 6.3), (18.6, 6.3)]
card = []

# backplate, PCB with the x16 finger tab, gold contacts
bm = bmesh.new()
add_box(bm, (2.5, 1.0, 0.0), (26.9, 11.1, 0.25))
card.append(mk("backplate", bm, SHROUD, bevel=0.08, segs=2))
outline = [(2.5, 0.75), (16.6, 0.75), (16.6, 0.0), (23.7, 0.0), (23.7, 0.6), (23.89, 0.6), (23.89, 0.0),
           (25.06, 0.0), (25.06, 0.75), (26.9, 0.75), (26.9, 11.1), (2.5, 11.1)]
bm = bmesh.new()
add_poly(bm, outline, 0.35, 0.51)
card.append(mk("pcb", bm, PCB, bevel=0.02, segs=1))
bm = bmesh.new()
for u0, u1 in ((16.6, 23.7), (23.89, 25.06)):
    k = int((u1 - u0 - 0.03) / 0.1)
    for j in range(k):
        uc = u0 + 0.065 + j * 0.1
        for w0, w1 in ((0.49, 0.54), (0.32, 0.37)):
            add_box(bm, (uc - 0.035, 0.06, w0), (uc + 0.035, 0.66, w1))
card.append(mk("fingers", bm, GOLD))

# heatsink: base plate, fin stack, heat pipes
bm = bmesh.new()
add_box(bm, (6.0, 1.4, 0.55), (24.2, 10.5, 0.76))
card.append(mk("sink_base", bm, SINK, bevel=0.03, segs=1))
bm = bmesh.new()
u = 6.2
while u < 24.0:
    add_box(bm, (u, 1.45, 0.75), (u + 0.035, 10.45, 2.95))
    u += 0.2
card.append(mk("fins", bm, SINK))
bm = bmesh.new()
for k, w in enumerate((1.0, 1.6, 2.2)):
    for ua, ub in ((13.0 - 0.3 * k, 7.0 + 0.0 * k), (14.0 + 0.3 * k, 22.5)):
        pts = [(ua, 4.5), (ua, 9.6), (ua, 10.55), (ua + (ub - ua) * 0.08, 10.85), ((ua + ub) / 2, 10.88),
               (ub - (ub - ua) * 0.08, 10.85), (ub, 10.55), (ub, 9.6), (ub, 4.5)]
        add_tube(bm, S.catmull_rom([(x, y, w) for x, y in pts], 6), 0.3, sides=14)
card.append(mk("heatpipes", bm, COPPER))

# power connector on the top edge, a few chokes and capacitors at the rear end
bm = bmesh.new()
add_box(bm, (3.9, 9.6, 0.5), (5.9, 11.15, 1.85))
cut = bmesh.new()
for i in range(3):
    for j in range(2):
        uc, wc = 4.3 + i * 0.42, 0.85 + j * 0.62
        add_box(cut, (uc - 0.17, 10.3, wc - 0.2), (uc + 0.17, 11.5, wc + 0.2))
card.append(mk("power_conn", bm, PLASTIC, bevel=0.05, segs=1, cut=cut))
bm = bmesh.new()
for vc in (2.4, 3.6, 4.8, 6.0, 7.2):
    add_box(bm, (2.9, vc - 0.45, 0.5), (3.8, vc + 0.45, 1.15))
card.append(mk("chokes", bm, PLASTIC, bevel=0.06, segs=1))
bm = bmesh.new()
for vc in (2.4, 3.6, 4.8, 6.0, 7.2):
    add_lathe(bm, [(0, 0.5), (0.3, 0.5), (0.3, 1.1), (0.26, 1.18), (0, 1.18)],
              Matrix.Translation((4.6, vc, 0)), segs=16)
card.append(mk("caps", bm, PORT))

# shroud: front plate with two fan openings, rim lips, end walls, fan bezels, centre boss, accent stripe
bm = bmesh.new()
add_poly(bm, [(x + CL / 2 - 0.075, y + 6.3) for x, y in S.rounded_rect(26.85, 10.8, 0.8, 5)], 3.2, 3.5)
cut = bmesh.new()
for uc, vc in FAN_C:
    add_cyl(cut, (uc, vc, 3.0), (uc, vc, 3.8), 4.55, 64)
card.append(mk("shroud_front", bm, SHROUD, bevel=0.1, segs=3, cut=cut))
bm = bmesh.new()
add_box(bm, (0.35, 11.38, 2.45), (26.5, 11.62, 3.25))
add_box(bm, (0.35, 0.98, 2.45), (26.5, 1.22, 3.25))
add_box(bm, (0.05, 1.0, 0.85), (0.35, 11.6, 3.25))
add_box(bm, (26.5, 1.0, 1.95), (26.8, 11.6, 3.25))
card.append(mk("shroud_walls", bm, SHROUD, bevel=0.04, segs=1))
bm = bmesh.new()
for uc, vc in FAN_C:
    add_lathe(bm, [(4.58, 2.3), (4.78, 2.3), (4.78, 3.24), (4.58, 3.24)], Matrix.Translation((uc, vc, 0)),
              segs=64, closed=True)
    add_lathe(bm, [(4.52, 3.45), (5.0, 3.45), (5.0, 3.55), (4.9, 3.62), (4.62, 3.62), (4.52, 3.55)],
              Matrix.Translation((uc, vc, 0)), segs=64, closed=True)
card.append(mk("fan_ducts", bm, SHROUD))
bm = bmesh.new()
bc = ((FAN_C[0][0] + FAN_C[1][0]) / 2, 6.3)
add_lathe(bm, [(0, 3.86), (0.62, 3.86), (0.66, 3.84), (0.7, 3.84), (0.98, 3.84), (1.02, 3.82),
               (1.2, 3.74), (1.33, 3.6), (1.36, 3.45), (0, 3.45)],
          Matrix.Translation((bc[0], bc[1], 0)), segs=48, slots=lambda i: {0: 1, 1: 1, 3: 2}.get(i, 0))
card.append(mk("boss", bm, [SHROUD, METAL, ACCENT]))
bm = bmesh.new()
add_box(bm, (1.2, 11.42, 3.49), (25.6, 11.54, 3.53))
card.append(mk("accent", bm, ACCENT))
bm = bmesh.new()
for uc, vc in ((0.75, 1.75), (0.75, 10.85), (25.95, 1.75), (25.95, 10.85), (bc[0], 1.55), (bc[0], 11.05)):
    add_lathe(bm, [(0, 3.6), (0.12, 3.59), (0.19, 3.55), (0.22, 3.48), (0, 3.48)],
              Matrix.Translation((uc, vc, 0)), segs=16)
card.append(mk("screws", bm, METAL))


# fans: hub with a gold cap, 13 swept blades, three struts
def add_blade(bm, m, a0, n_r=9, n_c=7):
    r0, r1 = 1.6, 4.38
    front, back = [], []
    for i in range(n_r):
        t = i / (n_r - 1)
        r = r0 + (r1 - r0) * t
        ac = a0 + 0.5 * t ** 1.4
        cw = (1.0 + 0.6 * t) / r
        h = 0.6 * (1 - 0.35 * t)
        rf, rb = [], []
        for j in range(n_c):
            s = j / (n_c - 1) - 0.5
            a = ac + s * cw
            z = 2.95 - s * h + 0.06 * (1 - 4 * s * s)
            th = 0.008 + 0.02 * (1 - abs(2 * s))
            rf.append(bm.verts.new(m @ Vector((r * math.cos(a), r * math.sin(a), z + th))))
            rb.append(bm.verts.new(m @ Vector((r * math.cos(a), r * math.sin(a), z - th))))
        front.append(rf)
        back.append(rb)
    for i in range(n_r - 1):
        for j in range(n_c - 1):
            bm.faces.new((front[i][j], front[i + 1][j], front[i + 1][j + 1], front[i][j + 1]))
            bm.faces.new((back[i][j + 1], back[i + 1][j + 1], back[i + 1][j], back[i][j]))
    for i in range(n_r - 1):
        for j in (0, n_c - 1):
            bm.faces.new((front[i][j], back[i][j], back[i + 1][j], front[i + 1][j]))
    for j in range(n_c - 1):
        for i in (0, n_r - 1):
            bm.faces.new((front[i][j], front[i][j + 1], back[i][j + 1], back[i][j]))


for f, (uc, vc) in enumerate(FAN_C):
    m = Matrix.Translation((uc, vc, 0)) @ Matrix.Rotation(0.3 * f, 4, "Z")
    bm = bmesh.new()
    for k in range(13):
        add_blade(bm, m, 2 * math.pi * k / 13)
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.5
        rot = m @ Matrix.Rotation(a, 4, "Z")
        add_box(bm, (1.5, -0.14, 2.3), (4.65, 0.14, 2.44), m=rot)
    card.append(mk("fan_blades", bm, FAN))
    bm = bmesh.new()
    add_lathe(bm, [(0, 3.43), (0.62, 3.43), (0.68, 3.43), (1.3, 3.42), (1.55, 3.38), (1.7, 3.3), (1.75, 3.15),
                   (1.75, 2.3), (0, 2.3)], m, segs=48, slots=lambda i: 1 if i == 0 else 0)
    card.append(mk("fan_hub", bm, [FAN, ACCENT]))

# I/O bracket: plate with vents and port openings, bottom tab, top flange with a screw slot
PORTS = [("dp", 1.45, 3.05, 0.62, 1.18), ("hdmi", 3.6, 5.1, 0.62, 1.15), ("dvi", 5.85, 9.65, 0.58, 1.66)]
bm = bmesh.new()
add_box(bm, (26.95, 0.5, -0.15), (27.05, 11.9, 3.6))
add_box(bm, (26.95, -0.8, 0.75), (27.05, 0.6, 1.75))
add_box(bm, (26.95, 11.8, -0.15), (27.95, 11.9, 3.6))
cut = bmesh.new()
for _, v0, v1, w0, w1 in PORTS:
    add_box(cut, (26.5, v0, w0), (27.5, v1, w1))
for i in range(8):
    for j in range(4):
        vc, wc = 1.45 + i * 1.25, 2.2 + j * 0.36
        add_box(cut, (26.5, vc - 0.5, wc - 0.075), (27.5, vc + 0.5, wc + 0.075))
add_box(cut, (27.45, 11.6, 1.55), (28.2, 12.1, 1.95))
card.append(mk("bracket", bm, METAL, bevel=0.03, segs=1, cut=cut))
bm = bmesh.new()
cut = bmesh.new()
for name, v0, v1, w0, w1 in PORTS:
    add_box(bm, (25.3, v0 + 0.01, w0 + 0.01), (27.1, v1 - 0.01, w1 - 0.01))
    add_box(cut, (26.6, v0 + 0.1, w0 + 0.09), (27.4, v1 - 0.1, w1 - 0.09))
card.append(mk("ports", bm, PORT, bevel=0.02, segs=1, cut=cut))
bm = bmesh.new()
cut = bmesh.new()
for name, v0, v1, w0, w1 in PORTS:
    if name == "dvi":
        add_box(bm, (26.5, v0 + 0.2, w0 + 0.18), (26.75, v1 - 0.2, w1 - 0.18))
        for i in range(8):
            for j in range(3):
                vc, wc = v0 + 0.55 + i * 0.38, w0 + 0.38 + j * 0.27
                add_box(cut, (26.6, vc - 0.06, wc - 0.06), (27.0, vc + 0.06, wc + 0.06))
    else:
        add_box(bm, (26.4, v0 + 0.3, (w0 + w1) / 2 - 0.06), (26.95, v1 - 0.3, (w0 + w1) / 2 + 0.06))
card.append(mk("port_inserts", bm, PLASTIC, cut=cut))
bm = bmesh.new()
for vc in (PORTS[2][1] - 0.45, PORTS[2][2] + 0.45):
    add_cyl(bm, (27.04, vc, 1.12), (27.42, vc, 1.12), 0.25, 6)
card.append(mk("jackposts", bm, METAL, bevel=0.02, segs=1))

# standoffs from the backing board to the backplate
bm = bmesh.new()
for uc, vc in ((3.5, 2.0), (3.5, 10.1), (25.6, 2.0), (25.6, 10.1)):
    add_cyl(bm, (uc, vc, -0.5), (uc, vc, 0.02), 0.32, 6)
    add_lathe(bm, [(0, 0.24), (0.16, 0.24), (0.24, 0.29), (0.26, 0.34), (0, 0.34)],
              Matrix.Translation((uc, vc, 0)), segs=12)
card.append(mk("standoffs", bm, METAL, bevel=0.02, segs=1))

# card into the frame: u -> Y, v -> Z, w -> X (out of the backing toward the glass)
CARD_M = Matrix(((0, 0, 1, BACK_FACE + 0.5), (1, 0, 0, -13.75), (0, 1, 0, 4.45), (0, 0, 0, 1)))
place(card, CARD_M)

# ---------------------------------------------------------------- lean 5 degrees back, to metres
LEAN = Matrix.Rotation(math.radians(-5.0), 4, "Y") @ Matrix.Scale(cm, 4)
parts = []
for o, g in zip(frame, frame_grain):
    place([o], LEAN)
    parts.append(finalize(o, grain=g))
for o in [glass, backing] + card:
    place([o], LEAN)
    parts.append(finalize(o))

# a wall behind for the previews (not exported): the frame's top back edge rests on it
if not args.no_render:
    top_back = LEAN @ Vector((0, 0, FH))
    wm = S.material("_PreviewWall", (0.55, 0.50, 0.43), 0.9)
    bmw = bmesh.new()
    add_box(bmw, (top_back.x - 0.02, -0.6, -0.01), (top_back.x - 0.0002, 0.6, 0.8))
    wall = S.obj_from_bm(bmw, "_wall", wm)

ob = S.finish("gpu_frame", parts, origin=(0, 0, 0), view_dir=(1.0, -0.75, 0.45), args=args,
              sharp_angle=40, lens=60)


# ---------------------------------------------------------------- extra previews
def shoot(path, view_dir=None, lens=60, margin=1.08, loc=None, target=None):
    sc = bpy.context.scene
    cam = sc.camera
    cam.data.lens = lens
    if loc is not None:
        cam.location = Vector(loc)
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    else:
        v = Vector(view_dir).normalized()
        lo, hi = S.bbox(ob)
        centre = (lo + hi) / 2
        cam.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
        corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        dg = bpy.context.evaluated_depsgraph_get()
        co, _ = cam.camera_fit_coords(dg, [c for p in corners for c in p])
        cam.location = centre + (Vector(co) - centre) * margin
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


if not args.no_render:
    shoot(os.path.join(args.out, "gpu_frame_front.png"), view_dir=(1.0, 0.0, 0.06), lens=60)
    target = LEAN @ Vector((FD / 2, 0, FH / 2))
    shoot(os.path.join(args.out, "gpu_frame_close.png"), lens=50,
          loc=target + Vector((1.0, -0.3, 0.12)).normalized() * 0.5, target=target)
    if os.environ.get("DBG"):
        for k, (uc, vc, dv) in enumerate(((6.4, 6.3, (1.0, -0.4, 0.5)), (24.0, 6.3, (1.0, 0.7, 0.35)),
                                         (13.0, 11.0, (0.6, -0.2, 1.0)))):
            c = LEAN @ (CARD_M @ Vector((uc, vc, 3.0)))
            shoot(os.path.join(args.out, f"dbg_gpu{k}.png"), lens=50, loc=c + Vector(dv).normalized() * 0.2,
                  target=c)
