"""lens_shatter (C17, the DROP, 469-494, cut 480): a v3.1 NESTED LENS zoom built on the core's nest (ctx.nest), plus
the glass.

The nest owns the layout and the rig: Andrew's A09 (S17) home card stays still with its real lens region
($AMV3_DATA/regions/S17/lens) feathered open from ~8 f before the cut, so Tom's M01 (S18, a static copy D m behind it,
framed on Tom's own lens from regions/S18/lens) already plays inside Andrew's lens; the camera flies into the lens (one
exponential attack), crosses A's plane at 479.5 and decays onto Tom's lens; DOF sits on B through the approach; after
w1 the copy -> home teleport is seamless. This module adds the LENS GLASS over the opening (thin glass with a faint trace
of Andrew's lens, cut from the region's real outline): cracks race across it on 476-477 and, as the camera passes
through the plane, it shatters around the camera's path - the shards stay almost still in the world and part and
tumble while the camera flies past, with a refractive shock ring, a capped flash, chips/sparks and flakes lingering
between the planes. Emissive bits (cracks, edges, sparks, flash) go to the light collection.
"""
import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fx3d as fx  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import camlib as cl  # noqa: E402

REVEAL = (8.0, 5.0)  # Tom shows inside the lens from f-8.5, fully open by f-3.5


def _focus_b(T, ctx):
    """Tom's lens centre on S18 at the cut (the region's centroid), else the EDL's lens_b."""
    sid = T["b"]["id"]
    try:
        import regions
        _, meta = regions.prepare(ctx, sid, "lens", range(T["f"] - 1, T["f"] + 2))
        info = regions.info_at(meta, T["f"])
        if info.get("area", 0.0) > 0:
            return [float(v) for v in info["centroid"]]
    except Exception as e:  # noqa: BLE001
        ctx.log("lens_shatter: S18 lens region failed (%s)" % e)
    return [float(v) for v in (T["p"].get("lens_b") or T["b"].get("focus") or [960, 540])]


def _nest_p(T, ctx):
    p = T["p"]
    return dict(mode="push", region="lens", shot=T["a"]["id"], settle=float(p.get("settle", 2.0)),
                roll=float(p.get("roll", 12.0)), reveal=list(p.get("reveal", REVEAL)), fstop=float(p.get("fstop", 2.0)),
                focus_b=p.get("focus_b") or _focus_b(T, ctx))


def bounds(T, ctx):
    return ctx.nest_bounds(T, **_nest_p(T, ctx))


def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def _region_hull(ctx, n, f):
    """Convex outline (plate px) of the prepared lens mask at frame f (0.5 contour), else the region's bbox ellipse."""
    import numpy as np
    import regions
    path = os.path.join(ctx.out, "_regions", "%s_lens" % n.fsid, "f_%05d.png" % f)
    pts = []
    if os.path.exists(path):
        try:
            m = regions.read_grey(path)
            sy, sx = 1080.0 / m.shape[0], 1920.0 / m.shape[1]
            for j in range(0, m.shape[0], 4):
                xs = np.nonzero(m[j] > 0.5)[0]
                if len(xs):
                    pts += [(float(xs[0]) * sx, j * sy), (float(xs[-1] + 1) * sx, j * sy)]
        except Exception as e:  # noqa: BLE001
            ctx.log("lens_shatter: mask outline failed (%s)" % e)
    if len(pts) < 6:
        x0, y0, x1, y1 = regions.info_at(n.L.meta, f)["bbox"]
        cx, cy, a, b = (x0 + x1) / 2, (y0 + y1) / 2, max(20.0, (x1 - x0) / 2), max(20.0, (y1 - y0) / 2)
        pts = [(cx + a * math.cos(2 * math.pi * k / 64), cy + b * math.sin(2 * math.pi * k / 64)) for k in range(64)]
    hull = _hull([(round(x, 1), round(y, 1)) for x, y in pts])
    # a hair outside the 0.5 contour, so the glass covers the feathered rim
    cx = sum(x for x, _ in hull) / len(hull)
    cy = sum(y for _, y in hull) / len(hull)
    return [(cx + (x - cx) * 1.03, cy + (y - cy) * 1.03) for x, y in hull]


def build(T, ctx):
    fx.set_linear_keys()
    f, w0, w1 = T["f"], T["w0"], T["w1"]
    n = ctx.nest(T, **_nest_p(T, ctx))
    fc = n.t_x                                                 # the camera crosses A's plane (and the glass) here
    th = w1 - 0.5                                              # the nest's copy -> home teleport
    MF = fx.unit_matrix(n.MF)
    rng = random.Random(4800 + f)
    light, plate = ctx.coll("light"), ctx.coll("plate")
    palA, palB = ctx.palette(fx.act_id(ctx, f - 1)), ctx.palette(fx.act_id(ctx, f))
    sa = T["a"]["id"]

    # ---- the lens glass over the opening: Voronoi shards of the real lens outline at the crossing
    hull_px = _region_hull(ctx, n, f - 1)
    hull = [cl.px_to_local(x, y) for x, y in hull_px]
    imp = Vector((*cl.px_to_local(*n.P), 0.0))                  # where the camera passes through A's plane
    R = max(math.hypot(x - imp.x, y - imp.y) for x, y in hull)
    seeds = fx.impact_seeds(rng, (imp.x, imp.y), 0.05 * R, R * 1.05, rings=6, sectors=12, jitter=0.6, swirl=0.33)
    cells = fx.voronoi(seeds, hull)
    face = fx.lens_glass_mat(fx.plate_mat(ctx, sa), "ls_face", pic=0.07)
    rim = fx.glass_mat("ls_rim", tint=(0.9, 0.97, 1.0), emit=palA["key"], emit_strength=0.6, rough=0.01, ior=1.5)
    gz = 0.004
    M_glass = MF @ Matrix.Translation((0, 0, gz))
    shards = fx.build_shards(cells, M_glass, 0.003, [face, rim], plate, "ls_shard", rng, uv_fn=fx.local2uv,
                             bevel_w=0.0008)
    me_i, c_i = fx.shard_mesh("ls_glass_intact", hull, 0.003, fx.local2uv)  # one seamless slab until the break
    me_i.materials.append(face)
    me_i.materials.append(rim)
    glass_i = bpy.data.objects.new("ls_glass_intact", me_i)
    glass_i.matrix_world = M_glass @ Matrix.Translation(c_i)
    fx.link(glass_i, plate)
    fx.key_visible(glass_i, w0 - 0.5, fc - 1.0)
    fx.no_blur(_cheap(glass_i))
    MFi = MF.inverted()
    prev = {}
    for sh in shards:
        c = (MFi @ sh.rest).translation
        off = Vector((c.x - imp.x, c.y - imp.y, 0.0))
        rn = min(off.length / R, 1.0)
        out = off.normalized() if off.length > 1e-6 else Vector((1, 0, 0))
        spin = sh.spin * (4 + 10 * (1 - rn)) * (1 if sh.jit.x > 0 else -1)
        q0 = sh.rest.to_quaternion()
        for t in fx.frames_half(w0, w1):
            u = max(0.0, t - (fc - 0.6) - 0.3 * rn)           # the break runs outward from the camera's path
            # parting round the camera's path (the centre opens first), then an almost-still drift and tumble
            part = out * R * (0.09 * (1 - rn) + 0.016) * (1 - math.exp(-1.2 * u))
            drift = out * 0.01 * R * u + Vector((0, 0, 0.014 * R * sh.jit.z * u)) + Vector((0, -0.0024 * R * u * u, 0))
            M = MF @ Matrix.LocRotScale(Vector((c.x, c.y, gz)) + part + drift,
                                        Quaternion(sh.axis, math.radians(spin * u * u / (u + 2.0))) @ q0, None)
            fx.key_matrix(sh.ob, t, M, prev)
        fx.key_visible(sh.ob, fc - 1.0, th)
        fx.no_blur(_cheap(sh.ob))   # they barely move in the world; object blur of near-lens glass cost ~2 s/f
    for t, gw in ((w0, 0.2), (f - 3, 0.2), (fc - 1.0, 0.08), (f + 6, 0.05)):
        fx.key_glass_glow(rim, t, gw)

    # ---- in focus for the hit: stop the nest's f/2 down to a pinhole over 475.5-477 (Tom inside the lens keeps the soft
    # look until then), so the cracks, the shards and the ring read as crisp glass, not bokeh
    t = f - 5.0
    while t < th - 0.25:
        if t in ctx.dof:
            foc, N0 = ctx.dof[t]
            s = cl.smoothstep((t - (f - 4.5)) / 1.5)
            ctx.key_dof(t, foc, 1.0 / (1.0 / N0 + (1.0 / cl.FSTOP_SHARP - 1.0 / N0) * s))
        t = round(t + 0.25, 4)

    # ---- cracks: thin crisp bright lines racing out from the camera's path across the glass on 477-479
    crack0 = f - 3.5
    crack_mat = fx.crack_material("ls_crack", _mix(palA["key"], (1, 1, 1), 0.7), imp)
    splines = []
    for (p, q) in fx.cell_edges(cells):
        a, b = Vector((p[0], p[1], gz + 0.0018)), Vector((q[0], q[1], gz + 0.0018))
        mid, e = (a + b) / 2 - imp, b - a
        radial = mid.length < 1e-6 or abs(e.normalized().dot(mid.normalized())) > 0.55
        if not radial and rng.random() < 0.45:
            continue
        pts = fx.bolt_path(rng, a, b, 2, 0.02, normal=Vector((0, 0, 1)), zjag=0.0)
        splines.append([(v, 1.0) for v in pts])
    cr = fx.poly_curve("ls_cracks", splines, 0.0004, crack_mat, caps=False)
    cr.matrix_world = MF
    fx.link(cr, light)
    fx.no_blur(cr)   # the rig rolls and rushes in at shutter 1.0: blurred, each line smeared into a grainy fan
    fx.key_visible(cr, crack0, fc + 0.25)
    # ~1.6 px wide on screen whatever the camera's distance to the glass (1 px = 1 mm at the home distance)
    home = cl.LENS_MM / cl.SENSOR_MM * 1.92
    t = crack0
    while t <= fc + 0.25:
        cr.data.bevel_depth = max(0.00004, 0.8e-3 * max(abs(n.z(t)), 0.02) / home)
        cr.data.keyframe_insert("bevel_depth", frame=t)
        t += 0.25
    for t, rr, g in ((crack0, 0.0, 0.0), (crack0 + 0.25, 0.06, 7.0), (crack0 + 1.0, 0.4, 7.0), (f - 1.5, 0.85, 6.0),
                     (fc - 0.5, 1.05, 5.0), (fc, 1.05, 3.0), (fc + 0.25, 1.05, 0.0)):
        fx.key_crack(crack_mat, t, rr * R, g)

    # ---- the hit (480): the glass bursts toward and past the camera, a refractive shock ring sweeps over B, a short
    # bloom; flakes linger between the planes. Burst / ring / bloom ride the camera (their motion is what reads on
    # screen: the camera itself is still flying in at ~0.3 m/f).
    K = MF @ Matrix.Translation((imp.x, imp.y, gz))
    fh = fc - 0.5

    def cam_fn(t):
        loc, rot = n.pose(t)
        return Matrix.LocRotScale(loc, rot, None)
    _burst(ctx, cam_fn, fc, f, sa, palA, plate, light, rng)
    _ring(cam_fn, f, plate)
    _bloom(cam_fn, fc, f, palB, light)
    _debris(K, n.D, fh, f, th, palA, plate, rng, face)
    ctx.denoise(f - 4, f + 8)   # glass at the hit (the parting slab, the burst, the ring)
    # glints only once the glass is broken (a flat intact slab mirrors an area light as a hard square)
    fx.camera_light("ls_keyB", cam_fn, fc - 1.0, th, Vector((-0.45, 0.35, 0.25)), palB["key"], 20.0, 0.4)
    fx.camera_light("ls_rimB", cam_fn, fc - 1.0, th, Vector((0.5, -0.3, 0.2)), palA["key"], 15.0, 0.35)
    ctx.log("lens_shatter (nest): %d shards over the %s lens, R %.3f m, crossing at (%.0f, %.0f) f%.1f, D %.3f k %.3f, "
            "reveal f%.1f, B lens at %s" % (len(shards), sa, R, n.P[0], n.P[1], fc, n.D, n.k, n.t_r,
                                             [round(v) for v in n.fK]))


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _cheap(ob):
    """Glass that only has to be seen and glint: no shadows, not in diffuse rays (f479-484 were 6-10 s/f on the GPU)."""
    ob.visible_shadow = False
    ob.visible_diffuse = False
    return ob


HW = 0.5 * cl.SENSOR_MM / cl.LENS_MM   # frame half-width per metre of depth (half-height = HW * 9 / 16)


def _burst(ctx, cam_fn, fc, f, sa, palA, plate, light, rng):
    """The glass bursting toward and past the camera on the hit: big thin shards (a third carry Andrew's picture, all
    glossy so they glint as they tumble through the camera lights) born ahead of the lens around the middle of the
    frame, flying outward to the frame edges and at the camera over 3-6 f, plus small chips and a few hot sparks.
    Paths are in camera space (they ride the camera), so on screen they spread out over B however fast the rig moves."""
    glass = fx.glass_mat("ls_bglass", tint=(0.93, 0.97, 1.0), emit=palA["key"], emit_strength=0.03, rough=0.01, ior=1.5)
    frost = fx.glass_mat("ls_bfrost", tint=(0.9, 0.94, 0.98), emit=(1, 1, 1), emit_strength=0.0, rough=0.1, ior=1.5)
    pic = fx.picture_glass_mat(fx.plate_mat(ctx, sa), "ls_bpic", gloss_rough=0.02, gloss=1.0, dim=0.7)
    edge = fx.emission_mat("ls_bedge", _mix(palA["key"], (1, 1, 1), 0.6), 0.0, additive=True)
    for t, g in ((fc - 0.5, 0.0), (fc, 2.5), (f + 1.5, 1.5), (f + 4, 0.5), (f + 7, 0.0)):
        fx.key_glow(edge, t, g)
    sparks = []
    for k in range(3):
        m = fx.emission_mat("ls_spark_%d" % k, _mix(palA["key"], (1, 0.9, 0.7), 0.4 + 0.2 * k), 0.0, additive=True)
        for t, g in ((fc - 0.5, 0.0), (fc, (4.0, 3.0, 2.0)[k]), (f + 2 + k, 2.0), (f + 4 + k, 0.0)):
            fx.key_glow(m, t, g)
        sparks.append(m)
    n_big, n_chip, n_spark = 30, 46, 0   # sparks blurred into squiggles (the rig turns between keys)
    for i in range(n_big + n_chip + n_spark):
        kind = 0 if i < n_big else (1 if i < n_big + n_chip else 2)
        # born on the hit (most on 479.5-480.5, a tail to 482), ahead of the lens, away from Tom's lens in the middle
        t_b = round(max(fc - 0.25, fc + abs(rng.gauss(0.0, (0.7, 1.0, 0.5)[kind]))) * 4) / 4
        life = rng.uniform(3.5, 6.5) if kind == 0 else rng.uniform(2.5, 5.0)
        z0 = -rng.uniform(0.35, 1.1) if kind == 0 else -rng.uniform(0.25, 0.9)
        ang = rng.uniform(0, 2 * math.pi)
        rho0 = rng.uniform(0.12, 0.5)
        if kind == 0:
            px = rng.uniform(110, 330) * (0.6 if rho0 < 0.25 else 1.0)   # screen size at birth
            Ls = px / 960.0 * HW * abs(z0)
            nv = rng.choice((3, 4, 4, 5, 5, 6))
            poly = []
            for k in range(nv):
                a = 2 * math.pi * (k + rng.uniform(-0.3, 0.3)) / nv
                poly.append((Ls * math.cos(a) * rng.uniform(0.5, 1.4), Ls * math.sin(a) * rng.uniform(0.3, 0.9)))
            poly = sorted(poly, key=lambda q: math.atan2(q[1], q[0]))
            thick = Ls * 0.04
        else:
            Ls = rng.uniform(10, 40 if kind == 1 else 6) / 960.0 * HW * abs(z0)
            poly = [(Ls * math.cos(2 * math.pi * k / 3 + rng.uniform(-0.5, 0.5)),
                     Ls * math.sin(2 * math.pi * k / 3 + rng.uniform(-0.5, 0.5))) for k in range(3)]
            thick = Ls * (0.3 if kind == 1 else 1.0)
        u0, v0 = rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.7)
        sc_uv = 0.5 / max(Ls, 1e-4) * rng.uniform(0.04, 0.12)
        me, _ = fx.shard_mesh("ls_burst_%03d" % i, poly, thick, lambda x, y, u0=u0, v0=v0, s=sc_uv: (u0 + x * s, v0 + y * s))
        if kind == 2:
            m0 = m1 = sparks[i % 3]
        else:
            r = rng.random()
            m0 = pic if (kind == 0 and r < 0.35) else (frost if r > 0.85 else glass)
            m1 = glass
        me.materials.append(m0)
        me.materials.append(m1)
        ob = bpy.data.objects.new(me.name, me)
        if kind == 0:
            fx.bevel(ob, min(0.0015, thick * 0.4))
        fx.link(ob, light if kind == 2 else plate)
        _cheap(ob)
        ax = fx.rand_axis(rng)
        spin = rng.uniform(12, 35) * (1.0, 2.0, 0.0)[kind]   # a spinning spark blurs into a squiggle
        q0 = Quaternion(fx.rand_axis(rng), rng.uniform(0, math.pi))
        prev = {}
        for t in fx.frames_half(t_b - 0.5, t_b + life + 0.5):
            u = max(0.0, t - t_b) / life
            z = z0 * (1.0 - 0.72 * u)                                    # flying at the lens ...
            rho = rho0 + (1.3 - rho0) * u ** 1.5                         # ... and out past the frame edges
            r = rho * HW * abs(z)
            pos = Vector((math.cos(ang) * r, math.sin(ang) * r * 0.75, z))
            Lm = Matrix.LocRotScale(pos, Quaternion(ax, math.radians(spin * u * life)) @ q0, None)
            fx.key_matrix(ob, t, fx.unit_matrix(cam_fn(t)) @ Lm, prev)
        fx.key_visible(ob, t_b, t_b + life)
        if kind == 0 and rng.random() < 0.5:   # a lit edge on half the big ones (catches the flash)
            pts = [(Vector((x, y, thick / 2 + 0.0002)), 1.0) for x, y in poly] + \
                  [(Vector((poly[0][0], poly[0][1], thick / 2 + 0.0002)), 1.0)]
            eo = fx.poly_curve(ob.name + "_edge", [pts], max(0.0002, Ls * 0.006), edge, caps=False)
            eo.parent = ob
            fx.link(eo, light)
            fx.key_visible(eo, t_b, t_b + life)
    ctx.log("lens_shatter: burst %d shards + %d chips + %d sparks from f%.2f" % (n_big, n_chip, n_spark, fc - 0.25))


def _ring(cam_fn, f, plate, dr=1.6):
    """The refractive shock ring over B (480-484): a plano-convex glass ring lens dr m ahead of the lens, centred on the
    frame (Tom's lens), expanding past the frame edges; it bends B as it sweeps and flattens out (fades) by 484.5. Its
    profile goes to zero thickness at both rims (a torus's steep silhouettes bent rays off the set: an opaque grey
    band). No emissive edge: thin edge tori read as two solid 25 px bands."""
    tq = Quaternion(Vector((1.0, 0.3, 0.0)).normalized(), math.radians(14.0))
    t0, t1 = f - 0.25, f + 4.75

    def place(ob, sr, zsq_fn, prev):
        for t in fx.frames_half(t0 - 0.5, t1):
            u = max(0.0, t - t0)
            rho = 0.04 + 1.4 * (1.0 - math.exp(-u / 2.0))
            rad = rho * HW * dr
            Lm = Matrix.LocRotScale(Vector((0, 0, -dr)), tq, Vector((rad * sr, rad * sr, rad * zsq_fn(u))))
            fx.key_matrix(ob, t, fx.unit_matrix(cam_fn(t)) @ Lm, prev)
        fx.key_visible(ob, t0, t1)
        fx.no_blur(ob)   # it grows ~0.4 frame-widths a frame: blurred, it smeared into wide grey bands

    me = _ring_lens_mesh("ls_ring_glass", 0.8, 1.0, 0.03)
    me.materials.append(fx.glass_mat("ls_ring_glass", tint=(1, 1, 1), emit=(1, 1, 1), rough=0.0, ior=1.33, refract=True))
    ob = bpy.data.objects.new("ls_ring_glass", me)
    fx.link(ob, plate)
    _cheap(ob)
    place(ob, 1.0, lambda u: 1.0 - 0.97 * cl.smoothstep((u - 2.0) / 2.6), {})


def _ring_lens_mesh(name, r0, r1, h, nu=256, nr=10):
    """A closed annular plano-convex lens: flat back (z = 0), front z = h sin^2 across [r0, r1] (zero at both rims)."""
    import bmesh
    bm = bmesh.new()
    top, bot = [], []
    for i in range(nu):
        a = 2 * math.pi * i / nu
        ca, sa = math.cos(a), math.sin(a)
        tt, bb = [], []
        for j in range(nr + 1):
            rr = r0 + (r1 - r0) * j / nr
            v = bm.verts.new((rr * ca, rr * sa, h * math.sin(math.pi * j / nr) ** 2))
            tt.append(v)
            bb.append(v if j in (0, nr) else bm.verts.new((rr * ca, rr * sa, 0.0)))
        top.append(tt)
        bot.append(bb)
    for i in range(nu):
        k = (i + 1) % nu
        for j in range(nr):
            bm.faces.new((top[i][j], top[i][j + 1], top[k][j + 1], top[k][j]))
            bm.faces.new((bot[i][j], bot[k][j], bot[k][j + 1], bot[i][j + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def _bloom(cam_fn, fc, f, pal, light, d=0.12):
    """A short bloom on the hit: a soft additive radial glow over the frame from the centre (the flash itself is added
    in finishing). Rides the camera, no motion blur."""
    hw = HW * d * 1.15
    me = fx.quad_mesh("ls_bloom", 2 * hw, 2 * hw * 9 / 16)
    m = bpy.data.materials.new("ls_bloom")
    nt = fx._nt(m)
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])   # (UV / Generated gave a flat haze over the frame)
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    for k, axis in ((0, "X"), (1, "Y")):   # r = 1 at the frame's left / right edge
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        nt.links.new(sep.outputs[axis], mul.inputs[0])
        mul.inputs[1].default_value = 1.15 / hw
        nt.links.new(mul.outputs[0], comb.inputs[k])
    ln = nt.nodes.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    nt.links.new(comb.outputs[0], ln.inputs[0])
    # falloff: exp(-(r / 0.35)^2)
    g1 = nt.nodes.new("ShaderNodeMath")
    g1.operation = "DIVIDE"
    nt.links.new(ln.outputs["Value"], g1.inputs[0])
    g1.inputs[1].default_value = 0.35
    g2 = nt.nodes.new("ShaderNodeMath")
    g2.operation = "POWER"
    nt.links.new(g1.outputs[0], g2.inputs[0])
    g2.inputs[1].default_value = 2.0
    g3 = nt.nodes.new("ShaderNodeMath")
    g3.operation = "MULTIPLY"
    nt.links.new(g2.outputs[0], g3.inputs[0])
    g3.inputs[1].default_value = -1.0
    g4 = nt.nodes.new("ShaderNodeMath")
    g4.operation = "EXPONENT"
    nt.links.new(g3.outputs[0], g4.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.name = "glow"
    em.inputs["Color"].default_value = (*_mix(pal["key"], (1, 1, 1), 0.65)[:3], 1.0)
    mulg = nt.nodes.new("ShaderNodeMath")
    mulg.operation = "MULTIPLY"
    nt.links.new(g4.outputs[0], mulg.inputs[0])
    val = nt.nodes.new("ShaderNodeValue")
    val.name = "gain"
    nt.links.new(val.outputs[0], mulg.inputs[1])
    nt.links.new(mulg.outputs[0], em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(em.outputs[0], add.inputs[0])
    nt.links.new(tr.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    me.materials.append(m)
    ob = bpy.data.objects.new("ls_bloom", me)
    fx.link(ob, light)
    fx.no_blur(ob)
    t0, t1 = fc - 0.25, f + 2.5
    prev = {}
    for t in fx.frames_half(t0 - 0.5, t1):
        fx.key_matrix(ob, t, fx.unit_matrix(cam_fn(t)) @ Matrix.Translation((0, 0, -d)), prev)
    fx.key_visible(ob, t0, t1)
    gain = val.outputs[0]
    for t, g in ((t0, 0.0), (f, 0.3), (f + 0.5, 0.12), (f + 1.25, 0.04), (f + 2.25, 0.0)):
        gain.default_value = g
        gain.keyframe_insert("default_value", frame=t)


def _debris(K, camB0, fh, f, w1, palA, plate, rng, face):
    """After the burst a few glass flakes keep drifting and tumbling in front of Tom's lens to the end of the window
    (the reference's debris lingers for 6-10 f), twinkling as they turn through the lights."""
    mat = fx.glass_mat("ls_flake", tint=(0.96, 0.98, 1.0), emit=palA["key"], emit_strength=0.25, rough=0.01, ior=1.5)
    prev = {}
    for i in range(110):
        sz = rng.uniform(0.0015, 0.0075) * (1.0 if i % 4 else 1.6)
        n = rng.choice((3, 4, 5))
        poly = sorted([(sz * math.cos(2 * math.pi * k / n + rng.uniform(-0.4, 0.4)) * rng.uniform(0.5, 1.4),
                        sz * math.sin(2 * math.pi * k / n + rng.uniform(-0.4, 0.4)) * rng.uniform(0.5, 1.2))
                       for k in range(n)], key=lambda q: math.atan2(q[1], q[0]))
        me, _ = fx.shard_mesh("ls_flake_%02d" % i, poly, sz * 0.25, None)
        m0 = face if i % 5 < 2 else mat   # 40 % still carry Andrew's picture (blue lens, red mask) like the ref's debris
        me.materials.append(m0)
        me.materials.append(mat)
        if m0 is face:
            u0, v0 = rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.7)
            uvl = me.uv_layers[0]
            for lp in me.loops:
                co = me.vertices[lp.vertex_index].co
                uvl.data[lp.index].uv = (u0 + co.x * 2.0, v0 + co.y * 2.0)
        ob = bpy.data.objects.new(me.name, me)
        fx.link(ob, plate)
        z = -camB0 * rng.uniform(0.25, 0.9)
        half = abs(z) * 0.55
        p0 = Vector((rng.uniform(-1.6, 1.6) * half, rng.uniform(-0.9, 0.9) * half, z))
        v0 = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.uniform(0.5, 2.0))) * 0.006 * abs(z)
        ax = fx.rand_axis(rng)
        spin = rng.uniform(8, 25)
        t0 = f + rng.uniform(0.0, 2.0)
        for t in fx.frames_half(round(t0 * 2) / 2, w1):
            u = t - t0
            pos = p0 + v0 * (u * 4.0 / (u + 4.0)) * 3.0   # thrown out, slowing (drag)
            M = K @ Matrix.LocRotScale(pos, Quaternion(ax, math.radians(spin * u)), None)
            fx.key_matrix(ob, t, M, prev)
        fx.key_visible(ob, round(t0 * 2) / 2, w1)
