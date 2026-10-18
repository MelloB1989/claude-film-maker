"""triptych (C32, window 777-819 + the shatter running into the outro to ~835): three Spider-Men as 3D comic panels.

Private set. Frame 777 is still S32 (M14's head raise, pushing in); at 777.5 the camera teleports into the triptych set
where M14 continues as a dimming backdrop card placed so the view is identical (a scaled ghost of S32's card), and the
panels slam out of the depth in front of it: P1 Tobey (lands 778.5), P2 Andrew (785), P3 Tom (794), each flying in
tilted, overshooting and settling, with a camera kick and an ink-rim flash on landing. Panels are bevelled slabs: the
plate (cropped portrait) printed with a black ink border, a white paper lip and halftone dots that grow toward the
edges; glossy so they glint as the camera orbits. The camera pulls back with each slam and orbits a few degrees, holds a
slow push while TIMELESS (text3d) lands at 802 in front of the panels (anchor empty TRIPTYCH_TITLE), then accelerates
in to +10 %/f with a clockwise roll: on 819 the panel rims ignite, on 819.5 every panel shatters into Voronoi slabs that
burst radially from the screen centre (empty TRIPTYCH_BURST) and fly past the camera while it keeps pushing (decaying,
k 0.85) through them. From 820 the film is transparent (ctx.transparent_from) so the outro shows behind the shards.
Contract with text3d (agent-02) and the outro (agent-08): burst at 819.5, radial 0.10-0.18 m/f per metre + toward the
camera 0.12-0.25 m/f, x1.25/f for 3 f then constant, spin 15-40 deg/f; camera +10 %/f, roll +1 deg/f at 819.
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
from camlib import State, FILL_DIST  # noqa: E402

PW, PH, PT = 0.66, 0.98, 0.024          # panel width, height, slab thickness (m)
CROP_W = 1080 * PW / PH                  # plate pixels across a panel (portrait crop, full plate height)
SLOTS = [  # id, x, y, crop centre px, yaw deg (inward), roll deg, z
    ("P1", -0.735, 0.012, 900, 7.0, -1.6, 0.05),
    ("P2", 0.0, 0.025, 1000, 0.0, 1.1, 0.0),
    ("P3", 0.735, -0.008, 920, -7.0, -0.8, 0.05),
]
BURST = 819.5
D812 = 2.80     # camera distance when the attack into the burst starts
END = 835


def _teleport(T):
    """The jump into the triptych set: just before the cut when the window has room (pre > 0, then P1 slams on the
    hit), else just after it (pre = 0: frame w0 must still show A for the entry contract)."""
    return T["f"] - 0.5 if T["w0"] < T["f"] else T["w0"] + 0.5


def _hermite_track(knots):
    """C1 piecewise-cubic through (t, value[, slope]) knots; missing slopes from Catmull-Rom. Holds the ends."""
    ts = [k[0] for k in knots]
    vs = [k[1] for k in knots]
    ms = []
    for i, k in enumerate(knots):
        if len(k) > 2 and k[2] is not None:
            ms.append(k[2])
        elif 0 < i < len(knots) - 1:
            ms.append((vs[i + 1] - vs[i - 1]) / (ts[i + 1] - ts[i - 1]))
        elif i == 0:
            ms.append((vs[1] - vs[0]) / (ts[1] - ts[0]))
        else:
            ms.append((vs[-1] - vs[-2]) / (ts[-1] - ts[-2]))

    def f(t):
        if t <= ts[0]:
            return vs[0] + ms[0] * (t - ts[0])
        if t >= ts[-1]:
            return vs[-1] + ms[-1] * (t - ts[-1])
        i = max(j for j in range(len(ts) - 1) if ts[j] <= t)
        h = ts[i + 1] - ts[i]
        u = (t - ts[i]) / h
        return ((2 * u ** 3 - 3 * u ** 2 + 1) * vs[i] + (u ** 3 - 2 * u ** 2 + u) * h * ms[i]
                + (-2 * u ** 3 + 3 * u ** 2) * vs[i + 1] + (u ** 3 - u ** 2) * h * ms[i + 1])
    return f


class Cam:
    """The triptych camera in set-local coordinates: look-at target, distance, orbit yaw, elevation, roll."""

    def __init__(self, T, A, lands):
        f0 = _teleport(T)
        l1, l2, l3 = lands
        self.A = A
        # distance: push in on P1 (decaying the S32 push), pull back on each slam, slow push under the title, then the
        # attack into the burst (ln D rates: -0.10 at 819.5) and the decaying push through the shards to 835
        self.dist = _hermite_track([(f0, 2.30, -0.07), (l1 + 1.5, 2.05, -0.02), (l2 - 1.0, 2.08, 0.03),
                                    (l2 + 2.0, 2.32, 0.05), (l3 - 1.0, 2.55, 0.03), (l3 + 2.0, 2.86, 0.05),
                                    (l3 + 7.0, 3.02, 0.0), (812.0, D812, -0.04)])
        # zoom (-d ln D) into the burst: from the slow push at 812 (0.04 m/f at D812) to +10 %/f, then decaying k 0.85
        self.zA = fx.attack(0.0, 0.04 / D812, 0.10, BURST - 812.0, 0.012, 1.4, 0.85)[0]
        self.zB = fx.landing(0.0, 0.10, 0.02, END - BURST, 0.85)[0]
        self.lnDb = math.log(D812) - self.zA(BURST - 812.0)
        self.tx = _hermite_track([(f0, -0.735), (l1 + 2.0, -0.70), (l2 - 1.0, -0.52), (l2 + 3.0, -0.33),
                                  (l3 - 1.0, -0.16), (l3 + 4.0, 0.02), (812.0, 0.0, 0.0)])
        self.ty = _hermite_track([(f0, 0.0), (l3 + 4.0, 0.03), (812.0, 0.02, 0.0)])
        self.yaw = _hermite_track([(f0, -12.0), (l2, -6.0), (l3, 0.0), (812.0, 6.0, 0.3)])
        self.el = _hermite_track([(f0, 0.03), (l3, -0.02), (812.0, 0.04, 0.0)])
        self.roll = _hermite_track([(f0, A.r, A.dr), (l1 + 4.0, 0.6), (l3, -0.4), (812.0, 0.0, 0.05),
                                    (BURST, 1.0, 1.0)])

    def D(self, t):
        if t <= 812.0:
            return self.dist(t)
        if t <= BURST:
            return math.exp(math.log(D812) - self.zA(t - 812.0))
        return math.exp(self.lnDb - (self.zB(t - BURST) - self.zB(0.0)))

    def r(self, t):
        if t <= BURST:
            return self.roll(t)
        return 1.0 + 1.0 * (t - BURST) * math.exp(-0.06 * (t - BURST))

    def matrix(self, t):
        tgt = Vector((self.tx(t), self.ty(t), 0.0))
        yaw = math.radians(self.yaw(t) + (0.25 * (t - 812.0) if t > 812.0 else 0.0))
        d = self.D(t)
        off = Vector((math.sin(yaw) * d, self.el(t) * d, math.cos(yaw) * d))
        loc = tgt + off
        rot = fx.look_at(loc, tgt) @ Quaternion((0, 0, 1), math.radians(self.r(t)))
        return Matrix.LocRotScale(loc, rot, None)


def bounds(T, ctx):
    A = ctx.entry_state(T)
    A = A.with_(ds=max(A.ds, 0.022))  # S32 pushes in (drift in) into the cut
    A = ctx.settle_entry(T, A) if hasattr(ctx, "settle_entry") else A
    return {"A": A}


def build(T, ctx):
    fx.set_linear_keys()
    f, w0 = T["f"], T["w0"]
    A = bounds(T, ctx)["A"]
    sa = T["a"]["id"]
    cardA = ctx.card(sa)
    O = ctx.new_set("triptych")
    MO = Matrix.Translation(O)
    rng = random.Random(7770)
    plate, light = ctx.coll("plate"), ctx.coll("light")
    tp = _teleport(T)
    lands = [tp + 1.0, 785.0, 794.0]
    cam = Cam(T, A, lands)
    pals = [ctx.palette(ctx.act_of(p[0]) if hasattr(ctx, "act_of") else a)
            for p, a in zip(SLOTS, ("tobey", "andrew", "tom"))]

    def shake(t):
        rot, loc = Quaternion(), Vector()
        for i, lt in enumerate(lands):
            dt = t - lt
            if 0 < dt < 10:
                env = math.exp(-3.0 * dt / 6.0) * fx.smooth(dt / 0.6)
                a = (1.0, 0.7, 0.8)[i]
                loc += Vector((0.006 * math.sin(7.1 * dt + i), 0.008 * math.sin(9.3 * dt + 2 * i), 0.03 * env)) * env * a
                rot = rot @ Quaternion((1, 0, 0), math.radians(0.5 * a * env * math.sin(8.3 * dt + i)))
        return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()

    def cam_world(t):
        return MO @ cam.matrix(t) @ shake(t)

    # ---- camera: S32 (home) until the teleport, the triptych set after, through the shatter to END
    def fn(t):
        if t < tp:
            return ctx.pose(cardA, A.at(t - w0))
        loc, rot, _ = cam_world(t).decompose()
        return loc, rot
    ctx.teleport(tp)
    ctx.key_path(fn, w0, END + 1, 0.25)
    if hasattr(ctx, "transparent_from"):
        ctx.transparent_from(int(math.ceil(BURST)))
    else:
        bpy.context.scene["amv3_transparent_from"] = int(math.ceil(BURST))
    fx.dof(ctx, tp - 0.01, 5.0, 128.0)
    fx.dof(ctx, tp + 0.01, cam.D(tp) * 0.75, 2.8)       # a short rack on the first slam
    fx.dof(ctx, lands[0] + 1.0, cam.D(lands[0] + 1.0), 4.0)
    fx.dof(ctx, lands[0] + 3.0, cam.D(lands[0] + 3.0), 32.0)
    fx.dof(ctx, lands[0] + 5.0, cam.D(lands[0] + 5.0), 128.0)

    # ---- M14 continues as a backdrop: a scaled ghost of S32's card that the camera sees exactly as before the jump
    Mh = fx.pose_matrix(ctx, cardA, A.at(tp - w0))
    Mt = cam_world(tp + 0.01)
    v = (cam_world(tp + 0.25).translation - cam_world(tp).translation).length * 4.0
    d_ghost = min(max(v / max(A.ds, 0.012), 2.8), 7.0)
    g = d_ghost / (FILL_DIST / A.at(tp - w0).s)
    Mg = Mt @ Matrix.Scale(g, 4) @ Mh.inverted() @ fx.unit_matrix(cardA.matrix_world)
    try:
        ghost = ctx.make_card(sa, "tp_backdrop_" + sa, matrix=Mg, frames=(w0, int(lands[1])), tile=3)
    except TypeError:
        ghost = ctx.make_card(sa, "tp_backdrop_" + sa, matrix=Mg)
    # M14 sinks into the act's void as the panels take over (gone by the second slam)
    vo = _veil(Mg, plate, [(tp, 0.0), (tp + 2.0, 0.45), (lands[1] - 2.0, 0.85), (lands[1] - 0.5, 1.0)], lands[1])
    ctx.log("triptych debug: ghost at %s, veil at %s, cam(800) at %s, ghost scale %s" % (
        tuple(round(x, 2) for x in Mg.translation), tuple(round(x, 2) for x in vo.matrix_world.translation),
        tuple(round(x, 2) for x in cam_world(800).translation), tuple(round(x, 2) for x in Mg.to_scale())))
    if hasattr(ctx, "env"):
        try:
            ctx.env(O, "tom", frames=(w0, int(BURST) + 1))
        except TypeError:
            ctx.env(O, "tom")

    # ---- the panels
    panels = []
    for i, (pid, x, y, cxp, yaw, roll, z) in enumerate(SLOTS):
        pal = pals[i]
        face, side = _panel_materials(ctx, pid, cxp, pal, i)
        poly = fx.rect(-PW / 2, -PH / 2, PW / 2, PH / 2)
        uv = lambda px, py: (px / PW + 0.5, py / PH + 0.5)  # noqa: E731
        me, _ = fx.shard_mesh("tp_%s" % pid, poly, PT, uv)
        me.materials.append(face)
        me.materials.append(side)
        ob = bpy.data.objects.new(me.name, me)
        fx.bevel(ob, 0.005, 3)
        fx.link(ob, plate)
        slot = MO @ Matrix.Translation((x, y, z)) @ Quaternion((0, 1, 0), math.radians(yaw)).to_matrix().to_4x4() \
            @ Quaternion((0, 0, 1), math.radians(roll)).to_matrix().to_4x4()
        lt = lands[i]
        t0 = lt - (1.0 if i == 0 else 1.5)
        prev = {}
        ax = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)).normalized()
        sgn = (-1, 1, 1)[i]
        for t in fx.frames_half(min(t0, tp), BURST):
            u = (t - t0) / (lt - t0)
            if u < 1.0:   # flying in from depth, tilted, accelerating (it slams)
                e = fx.clamp01(u) ** 2.2
                dz = -(4.2 if i else 1.1) * (1 - e)
                tilt = (1 - e) * 28.0
                off = Vector((sgn * 0.5 * (1 - e), 0.25 * (1 - e), dz))
            else:         # overshoot toward the camera and settle (damped spring), a wobble that dies in ~6 f
                d = t - lt
                k = math.exp(-0.75 * d)
                off = Vector((0, 0, 0.06 * k * math.sin(1.9 * d + 0.3)))
                tilt = 4.0 * k * math.sin(1.6 * d)
            M = slot @ Matrix.Translation(off) @ Quaternion(ax, math.radians(tilt)).to_matrix().to_4x4()
            fx.key_matrix(ob, t, M, prev)
        fx.key_visible(ob, t0, BURST)
        for t, gl in ((lt - 0.5, 0.0), (lt, 9.0), (lt + 1, 4.0), (lt + 4, 0.6), (BURST - 1.0, 0.6), (BURST - 0.5, 3.5),
                      (BURST, 4.0), (BURST + 3, 1.5), (BURST + 8, 0.8)):
            fx.key_glass_glow(side, t, gl)
        panels.append((pid, ob, slot, face, side, pal))

    # ---- anchors for text3d: the title in front of the panels, the burst centre
    ttl = bpy.data.objects.new("TRIPTYCH_TITLE", None)
    ttl.matrix_world = MO @ Matrix.Translation((0.0, -0.04, 0.45))
    ttl["width"] = 1.5
    ttl["gap"] = 0.45
    bpy.context.scene.collection.objects.link(ttl)
    Cb = cam_world(BURST)
    p_cam, fwd = Cb.translation, (Cb.to_quaternion() @ Vector((0, 0, -1)))
    s_hit = (O.z - p_cam.z) / fwd.z if abs(fwd.z) > 1e-6 else 3.0
    burst = p_cam + fwd * s_hit
    bob = bpy.data.objects.new("TRIPTYCH_BURST", None)
    bob.matrix_world = Matrix.LocRotScale(burst, fx.look_at(burst, burst + fwd), None)  # +Z toward the camera
    bob["f"] = BURST
    bpy.context.scene.collection.objects.link(bob)

    # ---- the shatter
    n_sh = 0
    for pid, ob, slot, face, side, pal in panels:
        Mi = slot.inverted()
        bl = Mi @ burst
        seeds = fx.impact_seeds(rng, (max(min(bl.x, PW / 2 - 0.02), -PW / 2 + 0.02),
                                      max(min(bl.y, PH / 2 - 0.02), -PH / 2 + 0.02)), 0.05, 0.6, rings=3, sectors=7,
                                jitter=0.6, swirl=0.5)
        seeds = [s for s in seeds if abs(s[0]) < PW / 2 and abs(s[1]) < PH / 2]
        seeds += fx.uniform_seeds(rng, 12, -PW / 2, -PH / 2, PW / 2, PH / 2, min_d=0.12)
        cells = fx.voronoi(seeds, fx.rect(-PW / 2, -PH / 2, PW / 2, PH / 2))
        shards = fx.build_shards(cells, slot, PT, [face, side], plate, "tp_%s_sh" % pid, rng,
                                 uv_fn=lambda px, py: (px / PW + 0.5, py / PH + 0.5), bevel_w=0.003)
        n_sh += len(shards)
        prev = {}
        for sh in shards:
            c = sh.rest.translation
            rad = c - burst
            toward = (Cb.translation - c).normalized()
            rad = rad - toward * rad.dot(toward)
            dist = rad.length
            rdir = rad.normalized() if dist > 1e-6 else Vector((1, 0, 0))
            v_r = rdir * dist * rng.uniform(0.10, 0.18)
            v_c = toward * rng.uniform(0.12, 0.25)
            spin = rng.uniform(15, 40) * (1 if sh.jit.x > 0 else -1)
            q0 = sh.rest.to_quaternion()
            for t in fx.frames_half(BURST, END + 1):
                u = t - BURST
                s_u = (1.25 ** min(u, 3.0) - 1) / math.log(1.25) + (1.25 ** 3) * max(0.0, u - 3.0)
                pos = c + (v_r + v_c) * s_u + Vector((0, 0, 0))
                M = Matrix.LocRotScale(pos, Quaternion(sh.axis, math.radians(spin * u)) @ q0, None)
                fx.key_matrix(sh.ob, t, M, prev)
            fx.key_visible(sh.ob, BURST, END + 1)

    # ---- light: key from the upper left, act-coloured rims from the sides (glints on the slabs as the camera orbits)
    for name, p_l, col, watts in (("tp_key", Vector((-1.6, 1.4, 2.6)), (1.0, 0.92, 0.85), 260.0),
                                  ("tp_rim_l", Vector((-2.4, -0.4, 0.6)), pals[0]["key"], 160.0),
                                  ("tp_rim_r", Vector((2.4, 0.3, 0.8)), pals[2]["key"], 160.0)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.color = col[:3]
        ld.energy = watts
        ld.size = 1.2
        lo = bpy.data.objects.new(name, ld)
        lo.visible_camera = False
        lo.matrix_world = MO @ Matrix.LocRotScale(p_l, (Vector((0, 0, 0)) - p_l).to_track_quat("-Z", "Y"), None)
        bpy.context.scene.collection.objects.link(lo)
        fx.key_visible(lo, w0, END + 1)
    st = lambda t: (cam.D(t + 0.5) / cam.D(t - 0.5))  # noqa: E731
    ctx.log("triptych: lands %s, backdrop ghost %.2f m (g %.2f), %d shards, burst at %s; zoom 818 %.3f 819 %.3f"
            % (lands, d_ghost, g, n_sh, tuple(round(x, 2) for x in burst), -math.log(st(818)), -math.log(st(819))))


def _veil(Mcard, coll, keys, off):
    """A darkening veil in front of the backdrop (mix of transparent and a dim warm-black), keyed by (t, amount)."""
    m = bpy.data.materials.new("tp_veil")
    nt = fx._nt(m)
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.03, 0.012, 0.01, 1.0)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    me = fx.quad_mesh("tp_veil", 1.92 * 3.05, 1.08 * 3.05)
    me.materials.append(m)
    ob = bpy.data.objects.new("tp_veil", me)
    ob.matrix_world = Mcard @ Matrix.Translation((0, 0, 0.004))
    coll.objects.link(ob)
    for t, a in keys:
        mix.inputs[0].default_value = a
        mix.inputs[0].keyframe_insert("default_value", frame=t)
    fx.key_visible(ob, keys[0][0], off)
    return ob


def _panel_materials(ctx, pid, cxp, pal, i):
    """Face: the plate cropped to a portrait panel, printed: white paper lip, black ink border, halftone dots that grow
    toward the edges, a glossy coat. Side: black ink slab with an act-coloured emissive rim ('glass' node, keyed)."""
    src = fx.plate_mat(ctx, pid)
    img_node = next(n for n in src.node_tree.nodes if n.type == "TEX_IMAGE")
    m = bpy.data.materials.new("tp_face_" + pid)
    nt = fx._nt(m)
    nt.nodes.clear()
    N = nt.nodes.new
    L = nt.links.new
    out = N("ShaderNodeOutputMaterial")
    tc = N("ShaderNodeTexCoord")
    mp = N("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (CROP_W / 1920.0, 1.0, 1.0)
    mp.inputs["Location"].default_value = (cxp / 1920.0 - 0.5 * CROP_W / 1920.0, 0.0, 0.0)
    L(tc.outputs["UV"], mp.inputs["Vector"])
    tex = N("ShaderNodeTexImage")
    tex.image = img_node.image
    tex.extension = "EXTEND"
    for k in ("frame_start", "frame_duration", "frame_offset", "use_cyclic", "use_auto_refresh"):
        setattr(tex.image_user, k, getattr(img_node.image_user, k))
    L(mp.outputs["Vector"], tex.inputs["Vector"])
    sep = N("ShaderNodeSeparateXYZ")
    L(tc.outputs["UV"], sep.inputs[0])

    def math_node(op, a, b=None):
        n = N("ShaderNodeMath")
        n.operation = op
        for k, x in enumerate((a, b)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                n.inputs[k].default_value = x
            else:
                L(x, n.inputs[k])
        return n.outputs[0]
    u, v = sep.outputs[0], sep.outputs[1]
    ex = math_node("MULTIPLY", math_node("MINIMUM", u, math_node("SUBTRACT", 1.0, u)), PW)
    ey = math_node("MULTIPLY", math_node("MINIMUM", v, math_node("SUBTRACT", 1.0, v)), PH)
    e = math_node("MINIMUM", ex, ey)                                   # metres to the panel edge
    paper = math_node("LESS_THAN", e, 0.011)
    ink = math_node("LESS_THAN", e, 0.027)
    # halftone: a dot screen (8 mm pitch, 15 deg) whose dots grow from nothing at 13 cm in to big at the border
    ca, sa = math.cos(math.radians(15)), math.sin(math.radians(15))
    k = 2 * math.pi / 0.008
    xu = math_node("MULTIPLY", u, PW * k)
    yv = math_node("MULTIPLY", v, PH * k)
    a1 = math_node("ADD", math_node("MULTIPLY", xu, ca), math_node("MULTIPLY", yv, sa))
    a2 = math_node("SUBTRACT", math_node("MULTIPLY", yv, ca), math_node("MULTIPLY", xu, sa))
    dots = math_node("MULTIPLY", math_node("SINE", a1), math_node("SINE", a2))       # -1..1
    grow = math_node("MAXIMUM", math_node("SUBTRACT", 1.0, math_node("DIVIDE", math_node("SUBTRACT", e, 0.027), 0.11)),
                     0.0)                                                            # 1 at the border, 0 13 cm in
    thr = math_node("SUBTRACT", 1.0, math_node("MULTIPLY", grow, 1.25))
    dot = math_node("MULTIPLY", math_node("GREATER_THAN", dots, thr), math_node("GREATER_THAN", grow, 0.001))
    tint = N("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.blend_type = "MULTIPLY"
    L(dot, tint.inputs["Factor"])
    L(tex.outputs["Color"], tint.inputs[6])
    tint.inputs[7].default_value = (*[0.18 + 0.25 * c for c in pal["key"]], 1.0)
    inked = N("ShaderNodeMix")
    inked.data_type = "RGBA"
    L(ink, inked.inputs["Factor"])
    L(tint.outputs[2], inked.inputs[6])
    inked.inputs[7].default_value = (0.008, 0.008, 0.01, 1.0)
    papered = N("ShaderNodeMix")
    papered.data_type = "RGBA"
    L(paper, papered.inputs["Factor"])
    L(inked.outputs[2], papered.inputs[6])
    papered.inputs[7].default_value = (0.86, 0.84, 0.8, 1.0)
    em = N("ShaderNodeEmission")
    L(papered.outputs[2], em.inputs["Color"])
    coat = fx.principled(nt, base=(0, 0, 0), rough=0.18, ior=1.5, spec=0.6)
    add = N("ShaderNodeAddShader")
    L(em.outputs[0], add.inputs[0])
    L(coat.outputs[0], add.inputs[1])
    L(add.outputs[0], out.inputs["Surface"])
    side = bpy.data.materials.new("tp_side_" + pid)
    snt = fx._nt(side)
    snt.nodes.clear()
    so = snt.nodes.new("ShaderNodeOutputMaterial")
    p = fx.principled(snt, base=(0.01, 0.01, 0.012), rough=0.22, ior=1.5, emc=pal["key"], ems=0.6)
    p.name = "glass"
    snt.links.new(p.outputs[0], so.inputs["Surface"])
    return m, side
