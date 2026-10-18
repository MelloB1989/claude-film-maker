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
    for t, gw in ((w0, 0.2), (f - 3, 0.3), (fc - 0.5, 0.3), (fc, 0.25), (f + 2, 0.2), (f + 6, 0.1)):
        fx.key_glass_glow(rim, t, gw)

    # ---- cracks racing across the glass before the camera reaches it
    crack0 = f - 4.5
    crack_mat = fx.crack_material("ls_crack", _mix(palA["key"], (1, 1, 1), 0.5), imp)
    splines = []
    for (p, q) in fx.cell_edges(cells):
        a, b = Vector((p[0], p[1], gz + 0.0018)), Vector((q[0], q[1], gz + 0.0018))
        mid, e = (a + b) / 2 - imp, b - a
        radial = mid.length < 1e-6 or abs(e.normalized().dot(mid.normalized())) > 0.55
        if not radial and rng.random() < 0.6:
            continue
        pts = fx.bolt_path(rng, a, b, 3, 0.07, normal=Vector((0, 0, 1)), zjag=0.0)
        splines.append([(v, 1.0) for v in pts])
    cr = fx.poly_curve("ls_cracks", splines, 0.00045, crack_mat)
    cr.matrix_world = MF
    fx.link(cr, light)
    # dim: this close to the lens at f/2 every crack is a wide bokeh streak
    fx.key_visible(cr, crack0, f - 2.5)
    for t, rr, g in ((crack0, 0.0, 0.0), (f - 4, 0.1, 0.4), (f - 3, 0.5, 0.25), (f - 2.6, 0.7, 0.0)):
        fx.key_crack(crack_mat, t, rr * R, g)

    # ---- the hit: shock ring in the glass plane, flash between the planes, sparks and chips, lingering flakes
    K = MF @ Matrix.Translation((imp.x, imp.y, gz))
    impK = Vector((0, 0, 0))
    fh = fc - 0.5
    _shockwave(K, impK, 0.32 * R, 0.34 * R, fh, f, palA, palB, light, plate, rng)
    _flash(K, impK, n.D * 0.5, fh, f, palB, light, 0.35)
    _chips(K, impK, 0.32 * R, fh, f, palA, palB, light, plate, rng, face, 4.0 * R)
    _debris(K, n.D, fh, f, th, palA, plate, rng, face)

    def cam_fn(t):
        loc, rot = n.pose(t)
        return Matrix.LocRotScale(loc, rot, None)
    # glints only once the glass is broken (a flat intact slab mirrors an area light as a hard square)
    fx.camera_light("ls_keyB", cam_fn, fc - 1.0, th, Vector((-0.45, 0.35, 0.25)), palB["key"], 10.0, 0.4)
    fx.camera_light("ls_rimB", cam_fn, fc - 1.0, th, Vector((0.5, -0.3, 0.2)), palA["key"], 8.0, 0.35)
    ctx.log("lens_shatter (nest): %d shards over the %s lens, R %.3f m, crossing at (%.0f, %.0f) f%.1f, D %.3f k %.3f, "
            "reveal f%.1f, B lens at %s" % (len(shards), sa, R, n.P[0], n.P[1], fc, n.D, n.k, n.t_r,
                                             [round(v) for v in n.fK]))


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _shockwave(K, impK, depth0, speed, fh, f, palA, palB, light, plate, rng):
    """A refractive shock ring (a flattened glass torus that bends B behind it, falling off inward) with a thin bright
    leading edge split cyan-outside / warm-inside (a chromatic fringe), expanding fast and tilted so it sweeps by."""
    tq = Quaternion(Vector((1.0, 0.35, 0.0)).normalized(), math.radians(22.0))

    def place(ob, scale_r, dz, zsq, prev):
        for t in fx.frames_half(fh, f + 6):
            u = max(0.0, t - fh)
            rad = 0.004 + speed * u * (1.0 - 0.05 * u)
            z = impK.z + depth0 * 0.22 * u + dz
            M = K @ Matrix.LocRotScale(Vector((impK.x, impK.y, z)), tq, Vector((rad * scale_r, rad * scale_r,
                                                                                  rad * zsq)))
            fx.key_matrix(ob, t, M, prev)
        fx.key_visible(ob, fh, f + 5)

    me = fx.torus_mesh("ls_ring_glass", 1.0, 0.11, 192, 16)
    me.materials.append(fx.glass_mat("ls_ring_glass", tint=(1, 1, 1), emit=(1, 1, 1), rough=0.0, ior=1.22, refract=True))
    ob = bpy.data.objects.new("ls_ring_glass", me)
    fx.link(ob, plate)
    place(ob, 0.9, -0.004, 0.22, {})
    for name, col, sr, g0 in (("ls_edge_cyan", _mix(palA["key"], (1, 1, 1), 0.3), 1.012, 2.5),
                              ("ls_edge_warm", _mix(palB["key"], (1, 0.8, 0.3), 0.3), 0.992, 1.8)):
        me = fx.torus_mesh(name, 1.0, 0.0022, 192, 6)
        mat = fx.emission_mat(name, col, g0, additive=True)
        me.materials.append(mat)
        o = bpy.data.objects.new(name, me)
        fx.link(o, light)
        place(o, sr, 0.0, 1.0, {})
        for t, g in ((fh, 0.0), (f, g0), (f + 1.5, g0 * 0.5), (f + 3, g0 * 0.15), (f + 4.5, 0.0)):
            fx.key_glow(mat, t, g)


def _flash(K, impK, camB0, fh, f, pal, light, gain=1.0):
    """A point light between the planes on the break (glints on the shards and flakes; no visible flash body)."""
    p = Vector((impK.x, impK.y, impK.z - 0.6 * (camB0 - (-impK.z))))
    ld = bpy.data.lights.new("ls_flash_pt", "POINT")
    ld.color = _mix(pal["key"], (1, 1, 1), 0.6)
    ld.shadow_soft_size = 0.02
    lo = bpy.data.objects.new("ls_flash_pt", ld)
    lo.visible_camera = False
    lo.matrix_world = K @ Matrix.Translation(p)
    bpy.context.scene.collection.objects.link(lo)
    for t, e in ((fh, 0.0), (f, 60.0 * gain), (f + 1, 20.0 * gain), (f + 2, 5.0 * gain), (f + 4, 0.0)):
        ld.energy = e
        ld.keyframe_insert("energy", frame=t)


def _chips(K, impK, depth0, fh, f, palA, palB, light, plate, rng, face, sc=1.0):
    """Glass chips (glints when they turn to the lights) and a few sparks of varied size, life and heat."""
    glass = fx.glass_mat("ls_chip", tint=(0.95, 0.98, 1.0), emit=palA["key"], emit_strength=0.4, rough=0.02)
    sparks = []
    for k in range(4):
        m = fx.emission_mat("ls_spark_%d" % k, _mix(palA["key"] if k % 2 else palB["key"], (1, 1, 1), 0.35 + 0.1 * k),
                            0.0, additive=True)
        g0 = (6.0, 4.0, 2.5, 1.5)[k]
        life = (2.5, 3.5, 4.5, 5.5)[k]
        for t, g in ((fh, g0), (f + life * 0.5, g0 * 0.6), (f + life, 0.0)):
            fx.key_glow(m, t, g)
        sparks.append(m)
    prev = {}
    for i in range(70):
        is_spark = i % 3 == 0
        sz = (rng.uniform(0.0006, 0.0035) if not is_spark else rng.uniform(0.0002, 0.0007)) * sc
        n = rng.choice((3, 4, 5))
        poly = [(sz * math.cos(2 * math.pi * k / n + rng.uniform(-0.4, 0.4)) * rng.uniform(0.6, 1.3),
                 sz * math.sin(2 * math.pi * k / n + rng.uniform(-0.4, 0.4)) * rng.uniform(0.6, 1.3)) for k in range(n)]
        me, _ = fx.shard_mesh("ls_chip_%03d" % i, poly, sz * 0.4 if not is_spark else sz, None)
        m = sparks[rng.randrange(4)] if is_spark else glass
        me.materials.append(m)
        me.materials.append(m)
        ob = bpy.data.objects.new(me.name, me)
        fx.link(ob, light if is_spark else plate)
        a = rng.uniform(0, 2 * math.pi)
        el = rng.uniform(0.15, 1.0)
        v = Vector((math.cos(a) * el, math.sin(a) * el, -rng.uniform(0.4, 1.4))) * rng.uniform(0.008, 0.05) * sc
        ax = fx.rand_axis(rng)
        spin = rng.uniform(20, 70)
        t0 = fh + 0.5 + rng.uniform(0.0, 1.5)
        for t in fx.frames_half(fh, f + 7):
            u = max(0.0, t - t0)
            pos = Vector((impK.x, impK.y, impK.z - 0.01)) + v * u * (1.0 + 0.15 * u)
            M = K @ Matrix.LocRotScale(pos, Quaternion(ax, math.radians(spin * u)), None)
            fx.key_matrix(ob, t, M, prev)
        fx.key_visible(ob, round(t0 * 2) / 2, f + 6.5)


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
