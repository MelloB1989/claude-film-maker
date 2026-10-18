"""xfx-B shared 3D FX kit: glass fracture, shard meshes, glass/plate/emission materials, lightning bolts, rings, motion.

Used by lens_shatter, lightning, dome_shards and triptych (blender/amv3/xfx/). Not a transition module itself.
Conventions (EDIT.md "Card space"): a card is 1.92 x 1.08 m, 1 px = 1 mm, centred on its object origin, picture in local
XY (x right, y up), facing local +Z (the camera looks along -Z). Card pixel (px, py) has y down.
Everything is deterministic: every random draw comes from a seeded random.Random.
"""
import math
import os
import random

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

PX = 0.001  # metres per card pixel
W, H = 1920, 1080


# ------------------------------------------------------------------------------------------------ card space helpers
def px2local(px, py, z=0.0):
    return Vector(((px - W / 2) * PX, -(py - H / 2) * PX, z))


def local2uv(x, y):
    return (x / PX + W / 2) / W, 1.0 - (-y / PX + H / 2) / H


def safe_center(cx, cy, s, r):
    """Clamp the card pixel at frame centre so the (rolled) frame stays inside the card: no card edge in a hold."""
    a = math.radians(abs(r) % 180.0)
    hx = (W / 2 * abs(math.cos(a)) + H / 2 * abs(math.sin(a))) / s
    hy = (W / 2 * abs(math.sin(a)) + H / 2 * abs(math.cos(a))) / s
    mx, my = max(W / 2 - hx, 0.0), max(H / 2 - hy, 0.0)
    return W / 2 + min(max(cx - W / 2, -mx), mx), H / 2 + min(max(cy - H / 2, -my), my)


def unit_matrix(M):
    loc, rot, _ = M.decompose()
    return Matrix.LocRotScale(loc, rot, None)


def pose_matrix(ctx, card, st):
    loc, rot = ctx.pose(card, st)
    return Matrix.LocRotScale(Vector(loc), Quaternion(rot), None)


def lerp(a, b, t):
    return a + (b - a) * t


def clamp01(t):
    return min(max(t, 0.0), 1.0)


def smooth(t):
    t = clamp01(t)
    return t * t * (3 - 2 * t)


def ramp(L0, m0, L1, m1, T):
    """Monotone-acceleration curve f on [0, T] with f(0)=L0, f'(0)=m0, f(T)=L1, f'(T)=m1 (rates per frame).

    f = a + b t + c e^(k t): the rate changes in one direction only (an expo-in push or an expo-out landing), which a
    cubic Hermite cannot guarantee for zoom rates that differ 10x. Falls back to Hermite when the average rate is not
    between the end rates. Returns (f, df).
    """
    D = L1 - L0
    lo, hi = sorted((m0 * T, m1 * T))
    if abs(m1 - m0) < 1e-9 or not (lo + 1e-9 < D < hi - 1e-9):
        def f(t):
            u = clamp01(t / T)
            h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
            return h00 * L0 + h10 * m0 * T + h01 * L1 + h11 * m1 * T

        def df(t):
            u = clamp01(t / T)
            return ((6 * u * u - 6 * u) * L0 + (3 * u * u - 4 * u + 1) * m0 * T + (-6 * u * u + 6 * u) * L1
                    + (3 * u * u - 2 * u) * m1 * T) / T
        return f, df

    def g(k):
        E = math.expm1(k * T)
        return m0 * T - (m1 - m0) * T / E + (m1 - m0) / k - D

    a_, b_ = -80.0 / T, 80.0 / T
    ga = g(a_)
    for _ in range(200):
        k = 0.5 * (a_ + b_)
        if abs(k) < 1e-7:
            k = 1e-7
        gk = g(k)
        if (gk > 0) == (ga > 0):
            a_, ga = k, gk
        else:
            b_ = k
    k = 0.5 * (a_ + b_) or 1e-7
    c = (m1 - m0) / (k * math.expm1(k * T))
    b = m0 - c * k
    a = L0 - c
    return (lambda t: a + b * t + c * math.exp(k * t)), (lambda t: b + c * k * math.exp(k * t))


def attack(L0, m0, m1, T, floor, grow=2.0, decay=0.8):
    """The reference A attack (REFS.md): rate(u) = floor + a decay^u + b grow^(u - T), rate(0) = m0 (the incoming
    drift/landing still decaying at k = decay), rate(T) = m1 (the speed at the cut, ~2x per frame over the last 3-4
    frames). Returns (f, df) with f(0) = L0; the level at T follows from the rates."""
    ld, lg = math.log(decay), math.log(grow)
    gT, dT = grow ** -T, decay ** T
    # m0 = floor + a + b gT ; m1 = floor + a dT + b
    det = 1.0 - gT * dT
    a = ((m0 - floor) - gT * (m1 - floor)) / det
    b = ((m1 - floor) - dT * (m0 - floor)) / det

    def df(u):
        return floor + a * decay ** u + b * grow ** (u - T)

    def f(u):
        return L0 + floor * u + a * (decay ** u - 1.0) / ld + b * (grow ** (u - T) - gT) / lg
    return f, df


def landing(L1, m0, floor, T, decay=0.8):
    """The reference B landing: rate(u) = floor + (m0 - floor) decay^u (k = 0.75-0.85 per frame), ending at level L1 at
    u = T. Returns (f, df); f(0) is the landing level implied by the speed it lands at."""
    lam = -math.log(decay)
    a = m0 - floor

    def df(u):
        return floor + a * decay ** u

    def f(u):
        return L1 - floor * (T - u) - a / lam * (decay ** u - decay ** T)
    return f, df


# ------------------------------------------------------------------------------------------------ fracture
def _clip(poly, m, n):
    """Keep the part of convex poly with (x - m) . n <= 0."""
    out = []
    L = len(poly)
    for i in range(L):
        p, q = poly[i], poly[(i + 1) % L]
        dp = (p[0] - m[0]) * n[0] + (p[1] - m[1]) * n[1]
        dq = (q[0] - m[0]) * n[0] + (q[1] - m[1]) * n[1]
        if dp <= 0:
            out.append(p)
        if (dp < 0) != (dq < 0) and dp != dq:
            t = dp / (dp - dq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def voronoi(seeds, bounds):
    """Clipped Voronoi cells of 2D seeds inside the convex polygon bounds (CCW). Returns [(seed_index, poly)]."""
    cells = []
    for i, s in enumerate(seeds):
        poly = list(bounds)
        others = sorted(range(len(seeds)), key=lambda j: (seeds[j][0] - s[0]) ** 2 + (seeds[j][1] - s[1]) ** 2)
        for j in others[1:]:
            t = seeds[j]
            d2 = (t[0] - s[0]) ** 2 + (t[1] - s[1]) ** 2
            rmax = max((p[0] - s[0]) ** 2 + (p[1] - s[1]) ** 2 for p in poly) if poly else 0
            if d2 > 4 * rmax + 1e-12:
                break
            poly = _clip(poly, ((s[0] + t[0]) / 2, (s[1] + t[1]) / 2), (t[0] - s[0], t[1] - s[1]))
            if len(poly) < 3:
                break
        if len(poly) >= 3 and abs(area(poly)) > 1e-10:
            cells.append((i, poly))
    return cells


def area(poly):
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                     for i in range(len(poly)))


def centroid(poly):
    A = area(poly)
    cx = cy = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        cr = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cr
        cy += (y0 + y1) * cr
    return cx / (6 * A), cy / (6 * A)


def disc(cx, cy, r, n=48):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def impact_seeds(rng, c, r0, r1, rings, sectors, jitter=0.35, swirl=0.0):
    """Radial-and-concentric glass fracture: rings of seeds, geometric radii r0..r1 around c, small shards at the hit."""
    seeds = [tuple(c)]
    for k in range(rings):
        r = r0 * (r1 / r0) ** (k / max(rings - 1, 1))
        n = max(5, int(round(sectors * (0.55 + 0.45 * k / max(rings - 1, 1)))))
        off = rng.random() * 2 * math.pi
        for i in range(n):
            a = off + 2 * math.pi * (i + rng.uniform(-jitter, jitter) * 0.5) / n + swirl * k
            rr = r * (1 + rng.uniform(-jitter, jitter) * 0.4)
            seeds.append((c[0] + rr * math.cos(a), c[1] + rr * math.sin(a)))
    return seeds


def uniform_seeds(rng, n, x0, y0, x1, y1, min_d=0.0):
    seeds = []
    tries = 0
    while len(seeds) < n and tries < n * 50:
        tries += 1
        p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 >= min_d * min_d for q in seeds):
            seeds.append(p)
    return seeds


def cell_edges(cells, tol=1e-6):
    """Unique edges of a cell set (the crack network), as ((x0, y0), (x1, y1))."""
    seen = {}
    for _, poly in cells:
        for i in range(len(poly)):
            p, q = poly[i], poly[(i + 1) % len(poly)]
            k = tuple(sorted(((round(p[0] / tol), round(p[1] / tol)), (round(q[0] / tol), round(q[1] / tol)))))
            seen.setdefault(k, (p, q))
    return list(seen.values())


# ------------------------------------------------------------------------------------------------ meshes
def shard_mesh(name, poly, thick, uv_fn=None):
    """A glass shard: poly (local metres, any winding) extruded +-thick/2, origin at the centroid.

    Faces: front (+Z) and back use material 0 (the picture, UV = uv_fn(x, y) in poly space); the rim uses material 1.
    Returns (mesh, centroid Vector in poly space).
    """
    if area(poly) < 0:
        poly = poly[::-1]
    cx, cy = centroid(poly)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    top = [bm.verts.new((x - cx, y - cy, thick / 2)) for x, y in poly]
    bot = [bm.verts.new((x - cx, y - cy, -thick / 2)) for x, y in poly]
    faces = [(bm.faces.new(top), 0), (bm.faces.new(bot[::-1]), 0)]
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        faces.append((bm.faces.new((bot[i], bot[j], top[j], top[i])), 1))
    for f, mi in faces:
        f.material_index = mi
        for lp in f.loops:
            x, y = lp.vert.co.x + cx, lp.vert.co.y + cy
            lp[uvl].uv = uv_fn(x, y) if uv_fn else (0.5, 0.5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me, Vector((cx, cy, 0.0))


def bevel(ob, width, segments=2, rim_index=1):
    m = ob.modifiers.new("bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.material = rim_index
    m.harden_normals = False
    return m


def torus_mesh(name, R=1.0, r=0.02, nu=128, nv=8):
    bm = bmesh.new()
    rings = []
    for i in range(nu):
        a = 2 * math.pi * i / nu
        ring = []
        for j in range(nv):
            b = 2 * math.pi * j / nv
            rr = R + r * math.cos(b)
            ring.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), r * math.sin(b))))
        rings.append(ring)
    for i in range(nu):
        for j in range(nv):
            a, b = rings[i], rings[(i + 1) % nu]
            bm.faces.new((a[j], b[j], b[(j + 1) % nv], a[(j + 1) % nv]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def quad_mesh(name, w, h, uv=((0, 0), (1, 1))):
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    vs = [bm.verts.new(v) for v in ((-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0))]
    f = bm.faces.new(vs)
    (u0, v0), (u1, v1) = uv
    for lp, t in zip(f.loops, ((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
        lp[uvl].uv = t
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def poly_curve(name, splines, depth, mat, caps=True):
    """splines: [[(Vector, radius), ...], ...] -> a bevelled POLY curve object (radius scales the bevel)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = depth
    cu.bevel_resolution = 1
    cu.use_fill_caps = caps
    for pts in splines:
        if len(pts) < 2:
            continue
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for p, (co, rad) in zip(sp.points, pts):
            p.co = (co[0], co[1], co[2], 1.0)
            p.radius = rad
    if mat:
        cu.materials.append(mat)
    return bpy.data.objects.new(name, cu)


def no_blur(ob):
    """Instantaneous light (a bolt lives for half a frame): no motion blur, so it stays a crisp filament."""
    try:
        ob.cycles.use_motion_blur = False
    except Exception:
        pass
    return ob


def ride_camera(ob, cam_fn, M_world, t_ref, t0, t1, prev=None):
    """Key ob to follow the camera over [t0, t1] (half frames) so it sits at M_world as seen from the camera at t_ref.
    Camera motion blur then does not smear it: for instantaneous light (bolts, arcs) that must stay crisp filaments."""
    C = cam_fn(t_ref).inverted() @ M_world
    for t in frames_half(t0, t1):
        key_matrix(ob, t, cam_fn(t) @ C, prev if prev is not None else {})


def link(ob, coll):
    coll.objects.link(ob)
    return ob


# ------------------------------------------------------------------------------------------------ materials
def _nt(mat):
    try:
        mat.use_nodes = True
    except Exception:
        pass
    return mat.node_tree


def _out(nt):
    outs = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"]
    for n in outs:
        if n.is_active_output:
            return n
    return outs[0]


def lin(c):
    """sRGB (0..1) -> linear."""
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c[:3])


def emission_mat(name, color, strength=1.0, additive=False):
    """Emission material; its strength is the input of node 'glow' (key it with key_glow).
    additive: emission + transparent, so the object adds light and never occludes (strength 0 = invisible)."""
    m = bpy.data.materials.new(name)
    nt = _nt(m)
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.name = "glow"
    em.inputs["Color"].default_value = (*color[:3], 1.0)
    em.inputs["Strength"].default_value = strength
    if additive:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(em.outputs[0], add.inputs[0])
        nt.links.new(tr.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def crack_material(name, color, imp):
    """Emission masked to object-space distance < R (node 'R', keyed): the cracks race out from the impact."""
    m = emission_mat(name, color, 0.0)
    nt = m.node_tree
    out = _out(nt)
    em = nt.nodes["glow"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    dist = nt.nodes.new("ShaderNodeVectorMath")
    dist.operation = "DISTANCE"
    dist.inputs[1].default_value = (imp.x, imp.y, 0.0)
    nt.links.new(tc.outputs["Object"], dist.inputs[0])
    r = nt.nodes.new("ShaderNodeValue")
    r.name = "R"
    lt = nt.nodes.new("ShaderNodeMath")
    lt.operation = "LESS_THAN"
    nt.links.new(dist.outputs["Value"], lt.inputs[0])
    nt.links.new(r.outputs[0], lt.inputs[1])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lt.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def key_crack(mat, f, radius, strength):
    r = mat.node_tree.nodes["R"].outputs[0]
    r.default_value = radius
    r.keyframe_insert("default_value", frame=f)
    key_glow(mat, f, strength)


def key_glow(mat, f, strength, node="glow"):
    s = mat.node_tree.nodes[node].inputs["Strength"]
    s.default_value = strength
    s.keyframe_insert("default_value", frame=f)


def principled(nt, **kw):
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    names = {"base": "Base Color", "rough": "Roughness", "ior": "IOR", "trans": "Transmission Weight",
             "emc": "Emission Color", "ems": "Emission Strength", "spec": "Specular IOR Level", "coat": "Coat Weight",
             "metal": "Metallic", "alpha": "Alpha"}
    for k, v in kw.items():
        sock = p.inputs[names[k]]
        sock.default_value = (*v[:3], 1.0) if isinstance(v, (tuple, list)) else v
    return p


def glass_mat(name, tint=(1, 1, 1), emit=(0.5, 0.8, 1.0), emit_strength=0.0, rough=0.02, ior=1.5):
    """Clear refractive glass with an optional emissive tint (rim light); 'glass' node Emission Strength is keyable."""
    m = bpy.data.materials.new(name)
    nt = _nt(m)
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    p = principled(nt, base=tint, rough=rough, ior=ior, trans=1.0, emc=emit, ems=emit_strength)
    p.name = "glass"
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return m


def key_glass_glow(mat, f, strength):
    s = mat.node_tree.nodes["glass"].inputs["Emission Strength"]
    s.default_value = strength
    s.keyframe_insert("default_value", frame=f)


def picture_glass_mat(src, name, gloss_rough=0.07, gloss=1.0, dim=1.0):
    """Copy of a plate (picture) material with a glossy clear-coat added: the shard face keeps the picture and catches
    specular glints from the lights as it turns."""
    m = src.copy()
    m.name = name
    nt = m.node_tree
    out = _out(nt)
    if not out.inputs["Surface"].links:
        return m
    s = out.inputs["Surface"].links[0].from_socket
    p = principled(nt, base=(0, 0, 0), rough=gloss_rough, ior=1.5, spec=gloss)
    add = nt.nodes.new("ShaderNodeAddShader")
    if dim != 1.0:
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = 1.0 - dim
        blk = nt.nodes.new("ShaderNodeEmission")
        blk.inputs["Strength"].default_value = 0.0
        nt.links.new(s, mix.inputs[1])
        nt.links.new(blk.outputs[0], mix.inputs[2])
        s = mix.outputs[0]
    nt.links.new(s, add.inputs[0])
    nt.links.new(p.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return m


def plate_image_mat(name, plate_dir, f0, f1, strength=1.0):
    """Fallback picture material (emission of an image sequence f_NNNNN.jpg, NNNNN = comp frame, held outside)."""
    m = bpy.data.materials.new(name)
    nt = _nt(m)
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    path = os.path.join(plate_dir, "f_%05d.jpg" % f0)
    img = bpy.data.images.load(path, check_existing=True)
    img.source = "SEQUENCE"
    tex.image = img
    iu = tex.image_user
    iu.frame_start = f0
    iu.frame_offset = f0 - 1
    iu.frame_duration = f1 - f0
    iu.use_auto_refresh = True
    iu.use_cyclic = False
    tex.extension = "EXTEND"
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


_PLATE_MATS = {}


def plate_mat(ctx, sid):
    """The picture material of a shot/panel plate, as the stage's cards use it (make_card), cached."""
    if sid in _PLATE_MATS:
        return _PLATE_MATS[sid]
    m = None
    try:
        far = Matrix.Translation((0, 0, -5000.0 - 10 * len(_PLATE_MATS)))
        try:
            card = ctx.make_card(sid, "xfxB_src_" + sid, matrix=far, collection="plate", frames=(0, 1))
        except TypeError:
            card = ctx.make_card(sid, "xfxB_src_" + sid, matrix=far, collection="plate")
        m = card.active_material  # the card itself sits 5 km below everything, out of every view
    except Exception as e:  # panels may not be cards in the core: read the plate folder
        ctx.log("xfxB: make_card(%s) failed (%s), using the plate folder" % (sid, e))
    if m is None:
        d = os.path.join(ctx.data, "plates", sid)
        fs = sorted(int(n[2:7]) for n in os.listdir(d) if n.startswith("f_"))
        m = plate_image_mat("plate_" + sid, d, fs[0], fs[-1] + 1)
    _PLATE_MATS[sid] = m
    return m


# ------------------------------------------------------------------------------------------------ animation
def set_linear_keys():
    try:
        bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    except Exception:
        pass


def key_matrix(ob, f, M, prev=None):
    """Key loc/rot(quaternion)/scale of ob at frame f to world matrix M (ob has no parent)."""
    loc, rot, sc = M.decompose()
    ob.rotation_mode = "QUATERNION"
    q = prev.get(ob.name) if prev is not None else None
    if q is not None and q.dot(rot) < 0:
        rot = -rot
    if prev is not None:
        prev[ob.name] = rot.copy()
    ob.location = loc
    ob.rotation_quaternion = rot
    ob.scale = sc
    ob.keyframe_insert("location", frame=f)
    ob.keyframe_insert("rotation_quaternion", frame=f)
    ob.keyframe_insert("scale", frame=f)


def act_id(ctx, f):
    a = ctx.act_at(f)
    return a["id"] if isinstance(a, dict) else a


def dof(ctx, f, focus, fstop):
    """Rack focus key through the stage (ctx.key_dof); the bare camera when the ctx has none."""
    if hasattr(ctx, "key_dof"):
        ctx.key_dof(f, max(focus, 0.01), fstop)
    else:
        key_defocus(bpy.context.scene.camera, f, focus, fstop)


def key_defocus(cam, f, focus, fstop):
    """Rack focus (real camera DOF): focus distance (m) and f-stop keyed at frame f on the stage camera."""
    d = cam.data.dof
    d.use_dof = True
    d.focus_distance = max(focus, 0.01)
    d.aperture_fstop = fstop
    d.keyframe_insert("focus_distance", frame=f)
    d.keyframe_insert("aperture_fstop", frame=f)


def key_visible(ob, f_on, f_off=None):
    """Visible (render) from f_on until f_off (half frames recommended), hidden elsewhere."""
    ob.hide_render = True
    ob.keyframe_insert("hide_render", frame=f_on - 1)
    ob.hide_render = False
    ob.keyframe_insert("hide_render", frame=f_on)
    if f_off is not None:
        ob.hide_render = True
        ob.keyframe_insert("hide_render", frame=f_off)


def frames_half(f0, f1):
    """Every frame and half frame in [f0, f1]."""
    out = []
    t = f0
    while t <= f1 + 1e-9:
        out.append(round(t, 3))
        t += 0.5
    return out


def rand_axis(rng):
    while True:
        v = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if 0.05 < v.length <= 1:
            return v.normalized()


def rot_m(axis, deg):
    return Quaternion(axis, math.radians(deg)).to_matrix().to_4x4()


# ------------------------------------------------------------------------------------------------ lightning
def bolt_path(rng, a, b, levels, jag, normal=None, zjag=0.25):
    """Midpoint-displacement lightning path a -> b (Vectors). Displacement mostly in the plane with normal `normal`."""
    pts = [a.copy(), b.copy()]
    for lev in range(levels):
        new = [pts[0]]
        for p, q in zip(pts, pts[1:]):
            d = q - p
            L = d.length
            if normal is not None:
                side = d.cross(normal)
                side = side.normalized() if side.length > 1e-9 else rand_axis(rng)
                off = side * rng.gauss(0, jag * L) + normal * rng.gauss(0, jag * L * zjag)
            else:
                off = d.cross(rand_axis(rng))
                off = (off.normalized() if off.length > 1e-9 else Vector()) * rng.gauss(0, jag * L)
            new += [(p + q) / 2 + off, q]
        pts = new
    return pts


def bolt_tree(rng, a, b, levels=6, jag=0.2, branches=7, sub=2, normal=None, r0=1.0, r1=0.35):
    """A branching bolt: [[(co, radius), ...] per spline]. Radii taper r0 -> r1 on the trunk, thinner on branches."""
    trunk = bolt_path(rng, a, b, levels, jag, normal)
    n = len(trunk)
    out = [[(p, lerp(r0, r1, i / (n - 1))) for i, p in enumerate(trunk)]]

    def grow(pts, rad, count, depth):
        m = len(pts)
        for _ in range(count):
            i = rng.randrange(max(1, m // 8), max(2, m - 2))
            p0 = pts[i]
            d = (pts[min(i + 2, m - 1)] - pts[i])
            if d.length < 1e-9:
                continue
            d.normalize()
            ax = d.cross(normal) if normal is not None else rand_axis(rng)
            if ax.length < 1e-9:
                ax = rand_axis(rng)
            d = Quaternion(ax.normalized(), math.radians(rng.choice((-1, 1)) * rng.uniform(18, 55))) @ d
            L = (b - a).length * rng.uniform(0.12, 0.38) * (0.6 ** depth)
            br = bolt_path(rng, p0, p0 + d * L, max(2, levels - 1 - depth), jag * 1.1, normal)
            k = len(br)
            rr = rad * rng.uniform(0.45, 0.7)
            out.append([(p, lerp(rr, rr * 0.15, j / (k - 1))) for j, p in enumerate(br)])
            if depth < 1:
                grow(br, rr, sub, depth + 1)

    grow(trunk, r0, branches, 0)
    return out


# ------------------------------------------------------------------------------------------------ shard field
class Shard:
    """One rigid shard: its object, the rest matrix and per-shard random parameters."""

    def __init__(self, ob, rest, size, rng):
        self.ob = ob
        self.rest = rest
        self.size = size
        self.axis = rand_axis(rng)
        self.spin = rng.uniform(0.6, 1.4)
        self.jit = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
        self.speed = rng.uniform(0.75, 1.3)
        self.delay = rng.uniform(0.0, 1.0)


def build_shards(cells, M_base, thick, mats, coll, name, rng, uv_fn=None, bevel_w=None, min_area=0.0):
    """Shard objects for 2D cells (poly in the base frame's local XY, metres). Returns [Shard]."""
    out = []
    for k, (i, poly) in enumerate(cells):
        a = abs(area(poly))
        if a < min_area:
            continue
        me, c = shard_mesh("%s_%03d" % (name, k), poly, thick, uv_fn)
        for m in mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(me.name, me)
        if bevel_w:
            bevel(ob, min(bevel_w, 0.25 * math.sqrt(a)))
        rest = M_base @ Matrix.Translation(c)
        ob.matrix_world = rest
        coll.objects.link(ob)
        out.append(Shard(ob, rest, math.sqrt(a), rng))
    return out
