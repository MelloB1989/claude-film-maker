"""lens_shatter (C17, the DROP, 469-494, cut 480): the camera slams into Andrew's lens, the lens glass cracks and
shatters into 3D shards that blow past the camera with a shockwave ring, and Tom's lens pulls out behind them.

A side (A's home set, w0 .. cut-0.5): an expo-in push from the C16 landing into the A09 lens (track tracks/S17.json),
rolling clockwise; from cut-3.5 a crack network (the same Voronoi cells the shards are cut from) races out from the
lens centre, glowing cyan (light pass), over a thin 3D glass disc that catches a moving glint.
Teleport at cut-0.5 into B's home set. There the shards are laid out so the camera sees exactly the picture it saw at
cut-0.5 (the A card region, now in pieces, floating between the camera and B's card): a "ghost" of A's card placed by
M_ghost = M_camB(cut-0.5) @ inv(M_camA(cut-0.5)) @ M_cardA. The shards keep approaching the camera at the A push rate
(so the zoom-in continues on screen through the cut), burst radially, spin and fly past the camera by ~cut+6, with a
white-cyan-orange shockwave ring (emissive, light pass) and a refractive glass ring that bends B behind it, a 1-2 frame
flash from inside the crack (finishing adds the white bloom), glass chips and sparks. Meanwhile the camera lands on
Tom's lens (track tracks/S18.json) at `land` x and decelerates out (expo-out) to the S18 hold, still rolling clockwise
and settling. Motion: ln s and roll are monotone-acceleration ramps (_fx3d.ramp) that start/end on the bounds rates.
"""
import json
import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fx3d as fx  # noqa: E402

try:
    from camlib import State, FILL_DIST
except ImportError:  # harness without the core
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_harness"))
    from camlib import State, FILL_DIST


def _track(ctx, sid, f, default):
    p = os.path.join(ctx.data, "tracks", "%s.json" % sid)
    if not os.path.exists(p):
        return list(default)
    fr = json.load(open(p)).get("frames", {})
    if not fr:
        return list(default)
    k = min(fr, key=lambda x: abs(float(x) - f))
    return list(fr[k])


def _params(T, ctx):
    p = T["p"]
    f = T["f"]
    P = dict(
        s_in=p.get("s_in", 1.12), ds_in=p.get("ds_in", 0.10),        # the C16 push landing, still decaying
        ds_peak=p.get("ds_peak", 0.30),                                # REFS: +20..30 %/f on the last A frame
        dr_peak=p.get("dr_peak", 2.2),                                 # clockwise into the hit (deg/f)
        ds_land=-p.get("ds_peak", 0.30) * 0.85, dr_land=2.0,           # B lands at A's speed (pull-out), same roll sense
        s_out=p.get("s_out", 1.30), ds_out=-0.018, dr_out=0.0,         # hold drift >= 1.5 %/f
        decay=p.get("decay", 0.8), floor_in=0.03,
        crack0=f - 3.5, fh=f - 0.5,
    )
    la = p.get("lens_a", T["a"]["focus"] or [960, 540])
    lb = p.get("lens_b", T["b"]["focus"] or [960, 540])
    P["lens_a"] = lambda t: _track(ctx, T["a"]["id"], t, la)
    P["lens_b"] = lambda t: _track(ctx, T["b"]["id"], t, lb)
    return P


def _curves(T, P):
    w0, w1, fh = T["w0"], T["w1"], P["fh"]
    TA, TB = fh - w0, w1 - fh
    lsA, dlsA = fx.attack(math.log(P["s_in"]), P["ds_in"], P["ds_peak"], TA, P["floor_in"], 2.0, P["decay"])
    rA, drA = fx.attack(0.0, 0.0, P["dr_peak"], TA, 0.0, 2.0, P["decay"])
    lsB, dlsB = fx.landing(math.log(P["s_out"]), P["ds_land"], P["ds_out"], TB, P["decay"])
    rB, drB = fx.landing(0.0, P["dr_land"], P["dr_out"], TB, P["decay"])
    P["s_peak"], P["s_land"], P["r_peak"], P["r_land"] = math.exp(lsA(TA)), math.exp(lsB(0)), rA(TA), rB(0)
    c_in = fx.safe_center(*P["lens_a"](w0), P["s_in"], 0.0)

    def cA(t):  # eases from the (still) entry framing onto the tracked lens: no pan jump at w0
        u = t - w0
        c = fx.safe_center(*P["lens_a"](t), math.exp(lsA(u)), rA(u))
        k = fx.smooth(u / 6.0)
        return c_in[0] + (c[0] - c_in[0]) * k, c_in[1] + (c[1] - c_in[1]) * k

    def cB(t):
        u = t - fh
        return fx.safe_center(*P["lens_b"](t), math.exp(lsB(u)), rB(u))

    def stA(t):
        u = t - w0
        c, c0, c1 = cA(t), cA(t - 0.25), cA(t + 0.25)
        return State(math.exp(lsA(u)), c[0], c[1], rA(u), dlsA(u), 2 * (c1[0] - c0[0]), 2 * (c1[1] - c0[1]), drA(u))

    def stB(t):
        u = t - fh
        c, c0, c1 = cB(t), cB(t - 0.25), cB(t + 0.25)
        return State(math.exp(lsB(u)), c[0], c[1], rB(u), dlsB(u), 2 * (c1[0] - c0[0]), 2 * (c1[1] - c0[1]), drB(u))
    return stA, stB


def bounds(T, ctx):
    P = _params(T, ctx)
    stA, stB = _curves(T, P)
    return {"A": stA(T["w0"]), "B": stB(T["w1"])}


def build(T, ctx):
    fx.set_linear_keys()
    P = _params(T, ctx)
    stA, stB = _curves(T, P)
    f, w0, w1, fh = T["f"], T["w0"], T["w1"], P["fh"]
    sa, sb = T["a"]["id"], T["b"]["id"]
    cardA, cardB = ctx.card(sa), ctx.card(sb)
    MA, MB = fx.unit_matrix(cardA.matrix_world), fx.unit_matrix(cardB.matrix_world)
    rng = random.Random(4800 + f)
    light, plate = ctx.coll("light"), ctx.coll("plate")
    palA, palB = ctx.palette(ctx.act_at(f - 1)["id"]), ctx.palette(ctx.act_at(f)["id"])

    # ---- camera
    for t in fx.frames_half(w0, fh - 0.5):
        ctx.key_cam(t, *ctx.pose(cardA, stA(t)))
    ctx.key_cam(fh - 0.01, *ctx.pose(cardA, stA(fh)))
    ctx.teleport(fh)
    ctx.key_cam(fh + 0.01, *ctx.pose(cardB, stB(fh)))
    for t in fx.frames_half(f, w1 - 0.5):
        ctx.key_cam(t, *ctx.pose(cardB, stB(t)))
    # rack defocus on the landing (REFS: the first 2-4 B frames are lens-blurred, clearing over 6-10 f): the focus sits
    # on the near shards at the hit and pulls back onto Tom's lens
    cam = bpy.context.scene.camera
    fx.key_defocus(cam, w0, 5.0, 64.0)
    fx.key_defocus(cam, fh - 0.01, 5.0, 64.0)
    for t, fr, fs in ((fh + 0.01, 0.5, 2.2), (f + 1, 0.55, 2.4), (f + 2, 0.7, 3.0), (f + 4, 0.88, 5.0), (f + 7, 1.0, 11.0),
                      (f + 10, 1.0, 32.0), (w1 - 0.5, 1.0, 64.0)):
        fx.key_defocus(cam, t, FILL_DIST / stB(t).s * fr, fs)

    # ---- the fracture, in A-card pixels around the lens at the hit
    sp = stA(fh)
    lc = (sp.cx, sp.cy)
    R = 0.62 * math.hypot(960, 540) / sp.s + 40          # covers the whole view at the peak, plus margin (px)
    seeds = fx.impact_seeds(rng, (0, 0), 9.0, R * 1.05, rings=7, sectors=12, jitter=0.7, swirl=0.37)
    cells_px = fx.voronoi(seeds, fx.disc(0, 0, R, 64))
    to_m = lambda q: ((lc[0] - 960 + q[0]) * fx.PX, -(lc[1] - 540 + q[1]) * fx.PX)   # px offset -> A card metres
    cells = [(i, [to_m(q) for q in poly]) for i, poly in cells_px]
    imp = fx.px2local(*lc)

    # ---- A side: crack network racing out from the lens centre, glass disc with a glint
    crack_mat = fx.crack_material("ls_crack", _mix(palA["key"], (1, 1, 1), 0.5), imp)
    splines = []
    for (p, q) in fx.cell_edges(cells):
        a, b = Vector((p[0], p[1], 0.0006)), Vector((q[0], q[1], 0.0006))
        mid, e = (a + b) / 2 - imp, b - a
        radial = mid.length < 1e-6 or abs(e.normalized().dot(mid.normalized())) > 0.55
        if not radial and rng.random() < 0.6:   # glass cracks are mostly radial; keep some rings
            continue
        pts = fx.bolt_path(rng, a, b, 3, 0.07, normal=Vector((0, 0, 1)), zjag=0.0)
        d = min((a - imp).length, (b - imp).length) / (R * fx.PX)
        splines.append([(v, 1.0 - 0.6 * d) for v in pts])
    cr = fx.poly_curve("ls_cracks", splines, 0.0002, crack_mat)
    cr.matrix_world = MA
    fx.link(cr, light)
    fx.key_visible(cr, P["crack0"], fh)
    nodes = crack_mat.node_tree.nodes
    for t, rr, g in ((P["crack0"], 0.0, 0.0), (f - 3, 0.05, 5.0), (f - 2, 0.30, 7.0), (f - 1, 0.75, 9.0),
                     (fh, 1.2, 12.0)):
        nodes["R"].outputs[0].default_value = rr * R * fx.PX
        nodes["R"].outputs[0].keyframe_insert("default_value", frame=t)
        fx.key_glow(crack_mat, t, g)
    disc_mat = fx.glass_mat("ls_lensglass", tint=(0.92, 0.97, 1.0), emit=palA["key"], emit_strength=0.0, rough=0.03,
                            ior=1.25)
    me, c = fx.shard_mesh("ls_lensdisc", fx.disc(imp.x, imp.y, R * fx.PX * 1.4, 64), 0.0008, None)
    me.materials.append(disc_mat)
    me.materials.append(disc_mat)
    dsk = bpy.data.objects.new("ls_lensdisc", me)
    dsk.matrix_world = MA @ Matrix.Translation(c + Vector((0, 0, 0.0012)))
    fx.link(dsk, plate)
    fx.key_visible(dsk, w0 - 0.5, fh)
    gl = _light(MA, imp + Vector((0.25, 0.18, 0.45)), palA["key"], 1.5, "ls_glintA", w0 - 0.5, fh, size=0.02, target=imp)
    gl.data.shape = "DISK"
    for t in (w0, fh):  # the glint slides across the lens glass as the camera closes in
        u = (t - w0) / (fh - w0)
        gl.location = MA @ (imp + Vector((0.30 - 0.55 * u, 0.20 - 0.25 * u, 0.45)))
        gl.keyframe_insert("location", frame=t)

    # ---- B side: the ghost of A's view, cut into shards, between the camera and Tom's lens
    MCa = fx.pose_matrix(ctx, cardA, stA(fh))
    MCb = fx.pose_matrix(ctx, cardB, stB(fh))
    camB0 = FILL_DIST / stB(fh).s
    g = 0.5 * camB0 / (FILL_DIST / sp.s)          # ghost scale: a smaller copy, closer, looks identical from the camera
    Mg = MCb @ Matrix.Scale(g, 4) @ MCa.inverted() @ MA
    K = MCb
    Ki = K.inverted()
    face = fx.picture_glass_mat(fx.plate_mat(ctx, sa), "ls_face", gloss_rough=0.05, gloss=0.8)
    rim = fx.glass_mat("ls_rim", tint=(0.9, 0.97, 1.0), emit=palA["key"], emit_strength=1.5, rough=0.01, ior=1.5)
    shards = fx.build_shards(cells, Mg, 0.0026, [face, rim], plate, "ls_shard", rng,
                             uv_fn=lambda x, y: fx.local2uv(x, y), bevel_w=0.0007)
    depth0 = g * FILL_DIST / sp.s                # the ghost plane's distance from the camera at the hit
    impK = Ki @ (Mg @ imp)                        # impact in the camera-at-hit frame (~ (0, 0, -depth0))
    edge_mat = fx.emission_mat("ls_edge", _mix(palA["key"], (1, 1, 1), 0.4), 3.0, additive=True)
    prev = {}
    t_end = f + 8
    for sh in shards:
        q0 = Ki @ sh.rest
        p0 = q0.translation.copy()
        rot0 = q0.to_quaternion()
        off = Vector((p0.x - impK.x, p0.y - impK.y, 0.0))
        rn = min(off.length / (g * R * fx.PX), 1.0)  # 0 at the hit .. 1 at the rim
        delay = 0.35 * rn                            # the break races outward
        vz0 = depth0 * P["ds_peak"]                  # keeps the A zoom rate through the cut
        kr = (0.06 + 0.06 * sh.speed) * (1.2 - 0.5 * rn)
        tang = Vector((-off.y, off.x, 0)).normalized() if off.length > 1e-6 else Vector()
        spin = sh.spin * (14 + 30 * (1 - rn)) * (1.0 if sh.jit.x > 0 else -1.0)
        for t in fx.frames_half(fh, t_end):
            u = max(0.0, t - fh - delay)
            cam_back = camB0 * (math.exp(-(math.log(stB(min(t, w1)).s) - math.log(stB(fh).s))) - 1.0) if t <= w1 else 0
            z = p0.z + cam_back + vz0 * (1.0 - 0.8 ** u) / 0.2231 * sh.speed + 0.002 * g * sh.jit.z * u
            grow = u * (1.0 + 0.35 * u)
            xy = off * (kr * grow) + tang * (0.004 * g * sh.jit.y * grow)
            pos = Vector((p0.x + xy.x, p0.y + xy.y, z))
            ang = spin * u * u / (u + 1.2)
            M = K @ Matrix.LocRotScale(pos, Quaternion(sh.axis, math.radians(ang)) @ rot0, Vector((g, g, g)))
            fx.key_matrix(sh.ob, t, M, prev)
        fx.key_visible(sh.ob, fh, t_end + 0.5)
        if sh.size > 0.012 and rng.random() < 0.55:
            eo = _edge_outline(sh, edge_mat, light)
            if eo:
                fx.key_visible(eo, fh, t_end + 0.5)
    for t, gw in ((fh, 3.0), (f, 2.5), (f + 1, 1.6), (f + 3, 0.8), (f + 6, 0.4)):
        fx.key_glass_glow(rim, t, gw)
        fx.key_glow(edge_mat, t, gw * 1.4)

    # ---- shockwave rings (emissive + refractive), flash from inside, sparks
    _shockwave(K, impK, depth0, fh, f, palA, palB, light, plate, rng)
    _flash(K, impK, camB0, fh, f, palB, light)
    _chips(K, impK, depth0, fh, f, palA, palB, light, plate, rng, face)
    _close_shards(K, impK, depth0, fh, f, palA, plate, rng)
    _light(K, Vector((-0.35, 0.3, 0.1)), palB["key"], 12.0, "ls_keyB", fh, t_end + 1, size=0.25, target=impK)
    _light(K, Vector((0.4, -0.25, -0.05)), palA["key"], 10.0, "ls_rimB", fh, t_end + 1, size=0.2, target=impK)
    ctx.log("lens_shatter: %d shards, R=%.0f px, ghost depth %.3f m, B dist %.3f m" % (len(shards), R, depth0, camB0))


# ------------------------------------------------------------------------------------------------ pieces
def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _edge_outline(sh, mat, coll):
    me = sh.ob.data
    zs = max(v.co.z for v in me.vertices)
    top = [v.co.copy() for v in me.vertices if abs(v.co.z - zs) < 1e-6]
    if len(top) < 3:
        return
    ang = sorted(top, key=lambda v: math.atan2(v.y, v.x))
    pts = [(Vector((v.x, v.y, v.z + 0.0002)), 1.0) for v in ang] + [(Vector((ang[0].x, ang[0].y, ang[0].z + 0.0002)), 1.0)]
    ob = fx.poly_curve(sh.ob.name + "_edge", [pts], 0.00035, mat, caps=False)
    ob.parent = sh.ob
    fx.link(ob, coll)
    return ob


def _light(M, p_local, color, watts, name, f_on, f_off, size=0.3, target=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.color = color[:3]
    ld.energy = watts
    ld.size = size
    ob = bpy.data.objects.new(name, ld)
    ob.visible_camera = False
    tgt = target if target is not None else Vector()
    d = (tgt - p_local)
    rot = d.to_track_quat("-Z", "Y")
    ob.matrix_world = M @ Matrix.LocRotScale(p_local, rot, None)
    bpy.context.scene.collection.objects.link(ob)
    fx.key_visible(ob, f_on, f_off)
    return ob


def _shockwave(K, impK, depth0, fh, f, palA, palB, light, plate, rng):
    """A refractive shock ring (a flattened glass torus that bends B behind it, falling off inward) with a thin bright
    leading edge split cyan-outside / warm-inside (a chromatic fringe), expanding fast and tilted so it sweeps by."""
    tq = Quaternion(Vector((1.0, 0.35, 0.0)).normalized(), math.radians(22.0))
    speed = 0.085

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
    me.materials.append(fx.glass_mat("ls_ring_glass", tint=(1, 1, 1), emit=(1, 1, 1), rough=0.0, ior=1.22))
    ob = bpy.data.objects.new("ls_ring_glass", me)
    fx.link(ob, plate)
    place(ob, 0.9, -0.004, 0.22, {})
    for name, col, sr, g0 in (("ls_edge_cyan", _mix(palA["key"], (1, 1, 1), 0.3), 1.012, 9.0),
                              ("ls_edge_warm", _mix(palB["key"], (1, 0.8, 0.3), 0.3), 0.992, 6.0)):
        me = fx.torus_mesh(name, 1.0, 0.0022, 192, 6)
        mat = fx.emission_mat(name, col, g0, additive=True)
        me.materials.append(mat)
        o = bpy.data.objects.new(name, me)
        fx.link(o, light)
        place(o, sr, 0.0, 1.0, {})
        for t, g in ((fh, 0.0), (f, g0), (f + 1.5, g0 * 0.5), (f + 3, g0 * 0.15), (f + 4.5, 0.0)):
            fx.key_glow(mat, t, g)


def _close_shards(K, impK, depth0, fh, f, palA, plate, rng):
    """A few big clear glass shards that tumble right past the lens (481-484): they refract and reflect B, bevel glints."""
    mat = fx.glass_mat("ls_big", tint=(0.96, 0.99, 1.0), emit=palA["key"], emit_strength=0.15, rough=0.0, ior=1.5)
    prev = {}
    for i in range(6):
        n = rng.choice((4, 5, 6))
        L = rng.uniform(0.025, 0.05)
        poly = [(L * math.cos(2 * math.pi * k / n + rng.uniform(-0.3, 0.3)) * rng.uniform(0.5, 1.4),
                 L * math.sin(2 * math.pi * k / n + rng.uniform(-0.3, 0.3)) * rng.uniform(0.5, 1.4)) for k in range(n)]
        hull = sorted(poly, key=lambda q: math.atan2(q[1], q[0]))
        me, _ = fx.shard_mesh("ls_big_%d" % i, hull, 0.003, None)
        me.materials.append(mat)
        me.materials.append(mat)
        ob = bpy.data.objects.new(me.name, me)
        fx.bevel(ob, 0.0009)
        fx.link(ob, plate)
        a = 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / 6
        start = Vector((math.cos(a) * 0.012, math.sin(a) * 0.008, impK.z * 0.55))
        end = Vector((math.cos(a) * 0.09, math.sin(a) * 0.06, -0.02))
        ax = fx.rand_axis(rng)
        t0 = f + 0.5 + 0.4 * i / 6
        for t in fx.frames_half(fh, f + 6):
            u = fx.clamp01((t - t0) / 3.0)
            pos = start.lerp(end, u ** 1.6)
            q = Quaternion(ax, math.radians(rng.uniform(55, 80) * 0 + 70 * u)) @ Quaternion((1, 0, 0), math.radians(25))
            fx.key_matrix(ob, t, K @ Matrix.LocRotScale(pos, q, None), prev)
        fx.key_visible(ob, round(t0 * 2) / 2, f + 4.5)


def _flash(K, impK, camB0, fh, f, pal, light):
    import bmesh
    me = bpy.data.meshes.new("ls_flash")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    mat = fx.emission_mat("ls_flash", _mix(pal["key"], (1, 1, 1), 0.75), 0.0, additive=True)
    me.materials.append(mat)
    ob = bpy.data.objects.new("ls_flash", me)
    p = Vector((impK.x, impK.y, impK.z - 0.6 * (camB0 - (-impK.z))))
    ob.matrix_world = K @ Matrix.LocRotScale(p, Quaternion(), Vector((0.018, 0.018, 0.018)))
    fx.link(ob, light)
    for t, g in ((fh, 0.0), (f, 30.0), (f + 1, 9.0)):
        fx.key_glow(mat, t, g)
    fx.key_visible(ob, fh, f + 1.5)
    ld = bpy.data.lights.new("ls_flash_pt", "POINT")
    ld.color = _mix(pal["key"], (1, 1, 1), 0.6)
    ld.shadow_soft_size = 0.02
    lo = bpy.data.objects.new("ls_flash_pt", ld)
    lo.visible_camera = False
    lo.matrix_world = K @ Matrix.Translation(p)
    bpy.context.scene.collection.objects.link(lo)
    for t, e in ((fh, 0.0), (f, 60.0), (f + 1, 20.0), (f + 2, 5.0), (f + 4, 0.0)):
        ld.energy = e
        ld.keyframe_insert("energy", frame=t)


def _chips(K, impK, depth0, fh, f, palA, palB, light, plate, rng, face):
    """Glass chips (glints when they turn to the lights) and a few sparks of varied size, life and heat."""
    glass = fx.glass_mat("ls_chip", tint=(0.95, 0.98, 1.0), emit=palA["key"], emit_strength=0.4, rough=0.02)
    sparks = []
    for k in range(4):
        m = fx.emission_mat("ls_spark_%d" % k, _mix(palA["key"] if k % 2 else palB["key"], (1, 1, 1), 0.35 + 0.1 * k),
                            0.0, additive=True)
        g0 = (16.0, 9.0, 5.0, 2.5)[k]
        life = (2.5, 3.5, 4.5, 5.5)[k]
        for t, g in ((fh, g0), (f + life * 0.5, g0 * 0.6), (f + life, 0.0)):
            fx.key_glow(m, t, g)
        sparks.append(m)
    prev = {}
    for i in range(70):
        is_spark = i % 3 == 0
        sz = rng.uniform(0.0006, 0.0035) if not is_spark else rng.uniform(0.0002, 0.0007)
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
        v = Vector((math.cos(a) * el, math.sin(a) * el, rng.uniform(0.4, 1.4))) * rng.uniform(0.008, 0.05)
        ax = fx.rand_axis(rng)
        spin = rng.uniform(20, 70)
        t0 = fh + rng.uniform(0.0, 1.5)
        for t in fx.frames_half(fh, f + 7):
            u = max(0.0, t - t0)
            pos = Vector((impK.x, impK.y, impK.z - 0.01)) + v * u * (1.0 + 0.15 * u)
            M = K @ Matrix.LocRotScale(pos, Quaternion(ax, math.radians(spin * u)), None)
            fx.key_matrix(ob, t, M, prev)
        fx.key_visible(ob, round(t0 * 2) / 2, f + 6.5)
