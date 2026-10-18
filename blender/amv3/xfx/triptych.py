"""triptych (C32, window 777-819 + the shatter running into the outro to ~835): a 3D COMIC PAGE of three Spider-Men.

Private set. Frame 777 is still S32 (M14 pushing in); at the teleport the camera keeps the same view of S32 (a scaled
ghost of its card) and S32 falls away behind (drops, tilts back, darkens) while the comic PAGE slams in from depth with
motion blur: a bevelled paper slab with three tall panels separated by tilted gutters, thick ink borders and halftone
printed on the panels, ~90 % of the frame wide. P1 (Tobey) arrives printed on it; the P2 / P3 frames are empty (dark
halftone) until Andrew and Tom slam down onto the page from the camera side on 785 / 794 (camera kicks, rim flashes).
Each panel plays its plate. The camera moves all the time: it starts close on P1, pulls back with each slam, then keeps
a slow push (~1.7 %/f) with an orbit and a roll drift, kicked on 802 (TIMELESS slam, text3d, anchor TRIPTYCH_TITLE) and
807, and accelerates to +10 %/f into the 819.5 burst: the page, its panels and TIMELESS shatter into slabs flying
radially from the screen centre (TRIPTYCH_BURST) and past the camera; transparent film from 820 (outro behind).
Behind the page: a dark multiverse void (no flat env): a deep red-black glow, light shafts in the three act colours,
soft bokeh, web strands and far dim cards of all three eras drifting in depth.
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

PAGE = (2.24, 1.32, 0.012)               # paper slab w, h, thickness (m)
PT = 0.010                               # panel slab thickness (raised off the paper)
INK = 0.030                              # ink border width printed on each panel
GW = 0.050                               # gutter width
G1, G2 = (-0.34, -0.40), (0.42, 0.32)    # gutter centre lines: x at the top, x at the bottom (tilted)
Y0, Y1, X0, X1 = -0.60, 0.60, -1.06, 1.06
PANELS = [  # id, act, crop centre px, polygon (CCW, page metres)
    ("P1", "tobey", 900, [(X0, Y0), (G1[1] - GW / 2, Y0), (G1[0] - GW / 2, Y1), (X0, Y1)]),
    ("P2", "andrew", 1000, [(G1[1] + GW / 2, Y0), (G2[1] - GW / 2, Y0), (G2[0] - GW / 2, Y1), (G1[0] + GW / 2, Y1)]),
    ("P3", "tom", 920, [(G2[1] + GW / 2, Y0), (X1, Y0), (X1, Y1), (G2[0] + GW / 2, Y1)]),
]
BURST = 819.5
D812 = 2.10      # camera distance when the attack into the burst starts
END = 835
KICKS = (802.0, 807.0)


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
    """The camera in set-local coordinates: look-at target, distance, orbit yaw, elevation, roll (eased tracks)."""

    def __init__(self, T, A, lands):
        f0 = _teleport(T)
        l1, l2, l3 = lands
        self.A = A
        self.dist = _hermite_track([(f0, 2.15, -0.07), (l1 + 1.5, 1.92, -0.03), (l2 - 1.0, 1.80, -0.01),
                                    (l2 + 2.0, 2.02, 0.07), (l3 - 1.0, 2.18, 0.03), (l3 + 2.0, 2.50, 0.08),
                                    (l3 + 4.5, 2.62, -0.04), (812.0, D812, -0.036)])
        self.zA = fx.attack(0.0, 0.036 / D812, 0.10, BURST - 812.0, 0.015, 1.4, 0.85)[0]
        self.zB = fx.landing(0.0, 0.10, 0.02, END - BURST, 0.85)[0]
        self.lnDb = math.log(D812) - self.zA(BURST - 812.0)
        self.tx = _hermite_track([(f0, -0.70), (l1 + 2.0, -0.68), (l2 - 1.0, -0.55), (l2 + 3.0, -0.30),
                                  (l3 - 1.0, -0.12), (l3 + 4.0, 0.0), (812.0, 0.02, 0.0)])
        self.ty = _hermite_track([(f0, 0.02), (l3 + 4.0, 0.0), (812.0, -0.01, 0.0)])
        self.yaw = _hermite_track([(f0, -14.0), (l2, -9.0), (l3, -4.0), (812.0, 5.0, 0.55)])
        self.el = _hermite_track([(f0, 0.05), (l3, -0.03), (812.0, 0.03, 0.0)])
        self.roll = _hermite_track([(f0, A.r, A.dr), (l1 + 4.0, -2.5), (l2 + 3.0, 1.5), (l3 + 3.0, -1.0),
                                    (812.0, 2.0, 0.3), (BURST, 1.0, 1.0)])

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
        yaw = math.radians(self.yaw(t) + (0.3 * (t - 812.0) if t > 812.0 else 0.0))
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


def _bbox(poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


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
    pals = {a: ctx.palette(a) for a in ("tobey", "andrew", "tom")}

    def kick(t):
        loc, rot = Vector(), Quaternion()
        for i, lt in enumerate(list(lands) + list(KICKS)):
            dt = t - lt
            if 0 < dt < 10:
                env = math.exp(-3.0 * dt / 6.0) * fx.smooth(dt / 0.6)
                a = (1.0, 0.8, 0.9, 0.6, 0.45)[i]
                loc += Vector((0.008 * math.sin(7.1 * dt + i), 0.010 * math.sin(9.3 * dt + 2 * i), 0.05)) * env * a
                rot = rot @ Quaternion((1, 0, 0), math.radians(0.7 * a * env * math.sin(8.3 * dt + i))) \
                    @ Quaternion((0, 0, 1), math.radians(0.9 * a * env * math.sin(6.1 * dt + 3 * i)))
        return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()

    def cam_world(t):
        return MO @ cam.matrix(t) @ kick(t)

    # ---- camera: S32 (home) until the teleport, the page set after, through the shatter to END
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
    fx.dof(ctx, tp + 0.01, cam.D(tp) * 0.8, 2.8)
    fx.dof(ctx, lands[0] + 1.0, cam.D(lands[0] + 1.0), 5.0)
    fx.dof(ctx, lands[0] + 3.0, cam.D(lands[0] + 3.0), 40.0)
    fx.dof(ctx, lands[0] + 5.0, cam.D(lands[0] + 5.0), 128.0)

    # ---- S32 falls away: a ghost of its card (same view across the jump) that drops, tilts back and darkens
    Mh = fx.pose_matrix(ctx, cardA, A.at(tp - w0))
    Mt = cam_world(tp + 0.01)
    v = (cam_world(tp + 0.25).translation - cam_world(tp).translation).length * 4.0
    d_ghost = min(max(v / max(A.ds, 0.012), 2.0), 5.0)
    g = d_ghost / (FILL_DIST / A.at(tp - w0).s)
    Mg = Mt @ Matrix.Scale(g, 4) @ Mh.inverted() @ fx.unit_matrix(cardA.matrix_world)
    t_fall = 3.5
    try:
        ghost = ctx.make_card(sa, "tp_backdrop_" + sa, matrix=Mg, frames=(w0, int(tp + t_fall) + 1), tile=3)
    except TypeError:
        ghost = ctx.make_card(sa, "tp_backdrop_" + sa, matrix=Mg)
    vo = _veil(Mg, plate, [(tp, 0.0), (tp + 1.0, 0.35), (tp + 2.5, 0.85), (tp + t_fall, 1.0)], tp + t_fall)
    prev, prev2 = {}, {}
    for t in fx.frames_half(tp, tp + t_fall):
        e = fx.clamp01((t - tp) / t_fall) ** 1.6
        M = MO @ Matrix.Translation((0.0, -1.4 * e, -2.2 * e)) @ MO.inverted() @ Mg
        piv = Mg.translation
        R = Matrix.Translation(piv) @ Quaternion((1, 0, 0), math.radians(-38.0 * e)).to_matrix().to_4x4() \
            @ Matrix.Translation(-piv)
        fx.key_matrix(ghost, t, R @ M, prev)
        fx.key_matrix(vo, t, R @ M @ Matrix.Translation((0, 0, 0.004 / max(g, 1e-6) * g)), prev2)

    # ---- the void behind the page
    _void(ctx, O, MO, rng, tp, BURST, pals)

    # ---- the page: paper slab + panel slabs (printed), slamming in from depth on lands[0]
    paper = _paper_material()
    pw, ph, pth = PAGE
    me, _ = fx.shard_mesh("tp_page", fx.rect(-pw / 2, -ph / 2, pw / 2, ph / 2), pth, lambda x, y: (x / pw + 0.5, y / ph + 0.5))
    side = fx.emission_mat("tp_page_side", (0.55, 0.52, 0.47), 0.6)
    me.materials.append(paper)
    me.materials.append(side)
    page = bpy.data.objects.new("tp_page", me)
    fx.bevel(page, 0.004, 2)
    fx.link(page, plate)
    page_rest = Matrix.Translation((0, 0, -0.010))
    l1 = lands[0]
    t_in = tp - 0.5

    def page_motion(t):
        """Group transform of the page: from depth, tilted, accelerating; overshoot and settle."""
        u = (t - t_in) / (l1 - t_in)
        if u < 1.0:
            e = fx.clamp01(u) ** 2.4
            return Matrix.Translation((0.25 * (1 - e), -0.10 * (1 - e), -4.5 * (1 - e))) \
                @ Quaternion((0, 1, 0), math.radians(24.0 * (1 - e))).to_matrix().to_4x4() \
                @ Quaternion((1, 0, 0), math.radians(-10.0 * (1 - e))).to_matrix().to_4x4()
        d = t - l1
        k = math.exp(-0.7 * d)
        return Matrix.Translation((0, 0, 0.07 * k * math.sin(1.9 * d + 0.3))) \
            @ Quaternion((0, 1, 0), math.radians(2.5 * k * math.sin(1.6 * d))).to_matrix().to_4x4()
    prev = {}
    for t in fx.frames_half(t_in, BURST):
        fx.key_matrix(page, t, MO @ page_motion(t) @ page_rest, prev)
    fx.key_visible(page, t_in, BURST)

    slabs = []
    for i, (pid, act, cxp, poly) in enumerate(PANELS):
        pal = pals[act]
        bb = _bbox(poly)
        uvf = (lambda bb: (lambda x, y: ((x - bb[0]) / (bb[2] - bb[0]), (y - bb[1]) / (bb[3] - bb[1]))))(bb)
        face, sidem = _panel_materials(ctx, pid, cxp, pal, poly, bb, empty=False)
        mats = [face, sidem]
        me, c = fx.shard_mesh("tp_%s" % pid, poly, PT, uvf)
        for m in mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(me.name, me)
        fx.bevel(ob, 0.003, 2)
        fx.link(ob, plate)
        rest = Matrix.Translation((c.x, c.y, PT / 2 + 0.002))
        lt = lands[i]
        prev = {}
        if i == 0:   # printed on the page from the start
            for t in fx.frames_half(t_in, BURST):
                fx.key_matrix(ob, t, MO @ page_motion(t) @ rest, prev)
            fx.key_visible(ob, t_in, BURST)
        else:        # an empty frame on the page until the picture slams down onto it from the camera side
            emp_face, emp_side = _panel_materials(ctx, pid, cxp, pal, poly, bb, empty=True)
            me2, _ = fx.shard_mesh("tp_%s_empty" % pid, poly, PT * 0.6, uvf)
            me2.materials.append(emp_face)
            me2.materials.append(emp_side)
            emp = bpy.data.objects.new(me2.name, me2)
            fx.bevel(emp, 0.002, 2)
            fx.link(emp, plate)
            pe = {}
            for t in fx.frames_half(t_in, lt):
                fx.key_matrix(emp, t, MO @ page_motion(t) @ Matrix.Translation((c.x, c.y, PT * 0.3 + 0.002)), pe)
            fx.key_visible(emp, t_in, lt + 0.5)
            t0 = lt - 1.5
            ax = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)).normalized()
            for t in fx.frames_half(t0, BURST):
                u = (t - t0) / (lt - t0)
                if u < 1.0:
                    e = fx.clamp01(u) ** 2.0
                    off = Vector((0.15 * (1 - e) * (1 if i == 2 else -1), 0.12 * (1 - e), 1.35 * (1 - e)))
                    tilt = 32.0 * (1 - e)
                else:
                    d = t - lt
                    k = math.exp(-0.8 * d)
                    off = Vector((0, 0, 0.03 * k * abs(math.sin(2.2 * d))))
                    tilt = 3.0 * k * math.sin(1.7 * d)
                M = MO @ page_motion(t) @ rest @ Matrix.Translation(off) \
                    @ Quaternion(ax, math.radians(tilt)).to_matrix().to_4x4()
                fx.key_matrix(ob, t, M, prev)
            fx.key_visible(ob, t0, BURST)
        for t, gl in ((t_in, 0.0), (lt - 0.5, 0.0), (lt, 6.0), (lt + 1, 2.5), (lt + 4, 0.4), (BURST - 1.0, 0.4),
                      (BURST - 0.5, 3.5), (BURST, 4.0), (BURST + 3, 1.5), (BURST + 8, 0.6)):
            fx.key_glass_glow(sidem, t, gl)
        slabs.append((pid, ob, rest, face, sidem, pal, poly, uvf))

    # ---- anchors for text3d: the title in front of the page, the burst centre
    ttl = bpy.data.objects.new("TRIPTYCH_TITLE", None)
    ttl.matrix_world = MO @ Matrix.Translation((0.0, -0.02, 0.45))
    ttl["width"] = 1.35   # fits the frame until the slam-in into the burst (~815)
    ttl["gap"] = 0.45
    bpy.context.scene.collection.objects.link(ttl)
    Cb = cam_world(BURST)
    p_cam, fwd = Cb.translation, (Cb.to_quaternion() @ Vector((0, 0, -1)))
    s_hit = (O.z - p_cam.z) / fwd.z if abs(fwd.z) > 1e-6 else 2.0
    burst = p_cam + fwd * s_hit
    bob = bpy.data.objects.new("TRIPTYCH_BURST", None)
    bob.matrix_world = Matrix.LocRotScale(burst, fx.look_at(burst, burst + fwd), None)  # +Z toward the camera
    bob["f"] = BURST
    bpy.context.scene.collection.objects.link(bob)

    # ---- the shatter: the page and every panel break into slabs that burst out from the screen centre
    n_sh = 0
    pieces = [(None, paper, side, fx.rect(-pw / 2, -ph / 2, pw / 2, ph / 2), pth, page_rest,
               lambda x, y: (x / pw + 0.5, y / ph + 0.5), 26)]
    for pid, ob, rest, face, sidem, pal, poly, uvf in slabs:
        pieces.append((pid, face, sidem, [(x - rest.translation.x, y - rest.translation.y) for x, y in poly], PT, rest,
                       (lambda rx, ry, uvf: (lambda x, y: uvf(x + rx, y + ry)))(rest.translation.x, rest.translation.y,
                                                                                 uvf), 18))
    Mpage = MO @ page_motion(BURST)
    for pid, fm, sm, poly, th, rest, uvf, nseed in pieces:
        base = Mpage @ rest
        bl = base.inverted() @ burst
        bb = _bbox(poly)
        seeds = fx.impact_seeds(rng, (min(max(bl.x, bb[0] + 0.02), bb[2] - 0.02), min(max(bl.y, bb[1] + 0.02), bb[3] - 0.02)),
                                0.05, 0.7, rings=3, sectors=7, jitter=0.6, swirl=0.5)
        seeds = [q for q in seeds if bb[0] < q[0] < bb[2] and bb[1] < q[1] < bb[3]]
        seeds += fx.uniform_seeds(rng, nseed // 2, bb[0], bb[1], bb[2], bb[3], min_d=0.12)
        cells = fx.voronoi(seeds, poly if area_ccw(poly) else poly[::-1])
        shards = fx.build_shards(cells, base, th, [fm, sm], plate, "tp_%s_sh" % (pid or "page"), rng,
                                 uv_fn=uvf, bevel_w=0.002)
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
            v_c = toward * rng.uniform(0.12, 0.25) * (0.7 if pid is None else 1.0)
            spin = rng.uniform(15, 40) * (1 if sh.jit.x > 0 else -1)
            q0 = sh.rest.to_quaternion()
            for t in fx.frames_half(BURST, END + 1):
                u = t - BURST
                s_u = (1.25 ** min(u, 3.0) - 1) / math.log(1.25) + (1.25 ** 3) * max(0.0, u - 3.0)
                M = Matrix.LocRotScale(c + (v_r + v_c) * s_u, Quaternion(sh.axis, math.radians(spin * u)) @ q0, None)
                fx.key_matrix(sh.ob, t, M, prev)
            fx.key_visible(sh.ob, BURST, END + 1)

    # ---- light: key from the upper left, act-coloured rims from the sides, all behind the camera
    for name, p_l, col, watts in (("tp_key", Vector((-1.6, 1.4, 4.6)), (1.0, 0.92, 0.85), 70.0),
                                  ("tp_rim_l", Vector((-2.6, -0.4, 4.2)), pals["tobey"]["key"], 45.0),
                                  ("tp_rim_r", Vector((2.6, 0.3, 4.2)), pals["tom"]["key"], 45.0)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.color = col[:3]
        ld.energy = watts
        ld.size = 1.2
        lo = bpy.data.objects.new(name, ld)
        lo.visible_camera = False
        lo.matrix_world = MO @ Matrix.LocRotScale(p_l, fx.look_at(p_l, Vector((0, 0, 0))), None)
        bpy.context.scene.collection.objects.link(lo)
        fx.key_visible(lo, w0, END + 1)
    st = lambda t: (cam.D(t + 0.5) / cam.D(t - 0.5))  # noqa: E731
    ctx.log("triptych page: lands %s, ghost %.2f m, %d shards, burst %s; zoom 800 %.3f 810 %.3f 818 %.3f 819 %.3f"
            % (lands, d_ghost, n_sh, tuple(round(x, 2) for x in burst), -math.log(st(800)), -math.log(st(810)),
               -math.log(st(818)), -math.log(st(819))))


def area_ccw(poly):
    return fx.area(poly) > 0


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


def _paper_material():
    """Comic paper: warm off-white with a faint CMY dot screen and a soft gloss (lit by the set's lights)."""
    m = bpy.data.materials.new("tp_paper")
    nt = fx._nt(m)
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    tc = N("ShaderNodeTexCoord")
    vt = N("ShaderNodeTexVoronoi")
    vt.feature = "F1"
    vt.inputs["Scale"].default_value = 260.0
    L(tc.outputs["UV"], vt.inputs["Vector"])
    ramp = N("ShaderNodeMapRange")
    L(vt.outputs["Distance"], ramp.inputs["Value"])
    ramp.inputs["From Min"].default_value = 0.18
    ramp.inputs["From Max"].default_value = 0.30
    mix = N("ShaderNodeMix")
    mix.data_type = "RGBA"
    L(ramp.outputs["Result"], mix.inputs["Factor"])
    mix.inputs[6].default_value = (0.62, 0.66, 0.74, 1.0)
    mix.inputs[7].default_value = (0.80, 0.77, 0.70, 1.0)
    em = N("ShaderNodeEmission")
    L(mix.outputs[2], em.inputs["Color"])
    em.inputs["Strength"].default_value = 0.55
    coat = fx.principled(nt, base=(0, 0, 0), rough=0.6, ior=1.45, spec=0.15)
    add = N("ShaderNodeAddShader")
    L(em.outputs[0], add.inputs[0])
    L(coat.outputs[0], add.inputs[1])
    L(add.outputs[0], out.inputs["Surface"])
    return m


def _panel_materials(ctx, pid, cxp, pal, poly, bb, empty=False):
    """Face: the plate cropped to the panel's box, printed: a thick black ink border along the panel's own (tilted)
    edges and halftone dots that grow toward them, a glossy coat. empty=True: the frame before the picture lands
    (border + dense dark halftone). Side: black ink slab with an act-coloured emissive rim ('glass' node, keyed)."""
    src = fx.plate_mat(ctx, pid)
    img_node = next(n for n in src.node_tree.nodes if n.type == "TEX_IMAGE")
    m = bpy.data.materials.new("tp_face_%s%s" % (pid, "_empty" if empty else ""))
    nt = fx._nt(m)
    nt.nodes.clear()
    N = nt.nodes.new
    L = nt.links.new
    out = N("ShaderNodeOutputMaterial")
    tc = N("ShaderNodeTexCoord")
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    crop_w = 1080.0 * bw / bh
    mp = N("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (crop_w / 1920.0, 1.0, 1.0)
    mp.inputs["Location"].default_value = (cxp / 1920.0 - 0.5 * crop_w / 1920.0, 0.0, 0.0)
    L(tc.outputs["UV"], mp.inputs["Vector"])
    tex = N("ShaderNodeTexImage")
    tex.image = img_node.image
    tex.extension = "EXTEND"
    for k in ("frame_start", "frame_duration", "frame_offset", "use_cyclic", "use_auto_refresh"):
        setattr(tex.image_user, k, getattr(img_node.image_user, k))
    L(mp.outputs["Vector"], tex.inputs["Vector"])
    sep = N("ShaderNodeSeparateXYZ")
    L(tc.outputs["UV"], sep.inputs[0])

    def mn(op, a, b=None):
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
    x = mn("ADD", mn("MULTIPLY", sep.outputs[0], bw), bb[0])     # page metres from the panel UV
    y = mn("ADD", mn("MULTIPLY", sep.outputs[1], bh), bb[1])
    e = None
    pts = poly if fx.area(poly) > 0 else poly[::-1]
    for i in range(len(pts)):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % len(pts)]
        ex, ey = x1 - x0, y1 - y0
        ln = math.hypot(ex, ey)
        nx, ny = -ey / ln, ex / ln                                   # inward normal of a CCW edge
        dist = mn("ADD", mn("ADD", mn("MULTIPLY", x, nx), mn("MULTIPLY", y, ny)), -(x0 * nx + y0 * ny))
        e = dist if e is None else mn("MINIMUM", e, dist)
    ink = mn("LESS_THAN", e, INK)
    ca, sa = math.cos(math.radians(15)), math.sin(math.radians(15))
    k = 2 * math.pi / 0.0085
    xu, yv = mn("MULTIPLY", x, k), mn("MULTIPLY", y, k)
    a1 = mn("ADD", mn("MULTIPLY", xu, ca), mn("MULTIPLY", yv, sa))
    a2 = mn("SUBTRACT", mn("MULTIPLY", yv, ca), mn("MULTIPLY", xu, sa))
    dots = mn("MULTIPLY", mn("SINE", a1), mn("SINE", a2))
    reach = 0.55 if empty else 0.13
    grow = mn("MAXIMUM", mn("SUBTRACT", 1.0, mn("DIVIDE", mn("SUBTRACT", e, INK), reach)), 0.0)
    if empty:
        grow = mn("ADD", mn("MULTIPLY", grow, 0.4), 0.55)
    thr = mn("SUBTRACT", 1.0, mn("MULTIPLY", grow, 1.25))
    dot = mn("MULTIPLY", mn("GREATER_THAN", dots, thr), mn("GREATER_THAN", grow, 0.001))
    tint = N("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.blend_type = "MULTIPLY"
    L(dot, tint.inputs["Factor"])
    if empty:
        tint.inputs[6].default_value = (*[0.05 + 0.12 * c for c in pal["key"]], 1.0)
    else:
        L(tex.outputs["Color"], tint.inputs[6])
    tint.inputs[7].default_value = (*[0.15 + 0.25 * c for c in pal["key"]], 1.0)
    inked = N("ShaderNodeMix")
    inked.data_type = "RGBA"
    L(ink, inked.inputs["Factor"])
    L(tint.outputs[2], inked.inputs[6])
    inked.inputs[7].default_value = (0.006, 0.006, 0.008, 1.0)
    em = N("ShaderNodeEmission")
    L(inked.outputs[2], em.inputs["Color"])
    coat = fx.principled(nt, base=(0, 0, 0), rough=0.45, ior=1.5, spec=0.18)
    add = N("ShaderNodeAddShader")
    L(em.outputs[0], add.inputs[0])
    L(coat.outputs[0], add.inputs[1])
    L(add.outputs[0], out.inputs["Surface"])
    side = bpy.data.materials.new("tp_side_%s%s" % (pid, "_empty" if empty else ""))
    snt = fx._nt(side)
    snt.nodes.clear()
    so = snt.nodes.new("ShaderNodeOutputMaterial")
    p = fx.principled(snt, base=(0.01, 0.01, 0.012), rough=0.22, ior=1.5, emc=pal["key"], ems=0.4)
    p.name = "glass"
    snt.links.new(p.outputs[0], so.inputs["Surface"])
    return m, side


def _soft_disc_mat(name, color, strength):
    """Additive soft disc (bokeh / glow sprite): emission falling off radially from the quad centre."""
    m = bpy.data.materials.new(name)
    nt = fx._nt(m)
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    tc = N("ShaderNodeTexCoord")
    gr = N("ShaderNodeTexGradient")
    gr.gradient_type = "SPHERICAL"
    mp = N("ShaderNodeMapping")
    mp.inputs["Location"].default_value = (-0.5, -0.5, 0.0)
    mp.inputs["Scale"].default_value = (2.0, 2.0, 1.0)
    L(tc.outputs["UV"], mp.inputs["Vector"])
    vm = N("ShaderNodeVectorMath")
    vm.operation = "SUBTRACT"
    L(tc.outputs["UV"], vm.inputs[0])
    vm.inputs[1].default_value = (0.5, 0.5, 0.0)
    sc = N("ShaderNodeVectorMath")
    sc.operation = "SCALE"
    L(vm.outputs[0], sc.inputs[0])
    sc.inputs["Scale"].default_value = 2.0
    L(sc.outputs[0], gr.inputs["Vector"])
    pw = N("ShaderNodeMath")
    pw.operation = "POWER"
    L(gr.outputs["Fac"], pw.inputs[0])
    pw.inputs[1].default_value = 1.6
    em = N("ShaderNodeEmission")
    em.name = "glow"
    em.inputs["Color"].default_value = (*color[:3], 1.0)
    st = N("ShaderNodeMath")
    st.operation = "MULTIPLY"
    L(pw.outputs[0], st.inputs[0])
    st.inputs[1].default_value = strength
    L(st.outputs[0], em.inputs["Strength"])
    tr = N("ShaderNodeBsdfTransparent")
    add = N("ShaderNodeAddShader")
    L(em.outputs[0], add.inputs[0])
    L(tr.outputs[0], add.inputs[1])
    L(add.outputs[0], out.inputs["Surface"])
    return m


def _void(ctx, O, MO, rng, t0, t1, pals):
    """The dark multiverse behind the page: a deep glow, act-coloured light shafts, soft bokeh, web strands and far
    dim cards of all three eras drifting in depth (everything hidden from the burst on: the outro shows there)."""
    plate, light = ctx.coll("plate"), ctx.coll("light")
    objs = []
    # deep backdrop: near-black with a red-black glow behind the page
    bg = bpy.data.objects.new("tp_void_bg", fx.quad_mesh("tp_void_bg", 60.0, 34.0))
    bg.data.materials.append(_soft_disc_mat("tp_void_glow", (0.30, 0.04, 0.03), 0.9))
    bg.matrix_world = MO @ Matrix.Translation((0, 0, -16.0))
    fx.link(bg, plate)
    objs.append(bg)
    dark = bpy.data.objects.new("tp_void_dark", fx.quad_mesh("tp_void_dark", 80.0, 45.0))
    dark.data.materials.append(fx.emission_mat("tp_void_dark", (0.006, 0.007, 0.012), 1.0))
    dark.matrix_world = MO @ Matrix.Translation((0, 0, -16.5))
    fx.link(dark, plate)
    objs.append(dark)
    cols = [pals["tobey"]["key"], pals["andrew"]["key"], pals["tom"]["key"]]
    # light shafts: long soft beams fanning out from behind the page, slowly turning
    for i in range(7):
        me = fx.quad_mesh("tp_shaft_%d" % i, 0.9, 14.0)
        me.materials.append(_soft_disc_mat("tp_shaft_%d" % i, cols[i % 3], rng.uniform(0.25, 0.5)))
        ob = bpy.data.objects.new(me.name, me)
        fx.link(ob, plate)
        ang0 = rng.uniform(-70, 70) + (180 if i % 2 else 0)
        z = rng.uniform(-9.0, -4.0)
        prev = {}
        for t in (t0 - 1, t1 + 1):
            a = math.radians(ang0 + 0.35 * (t - t0) * (1 if i % 2 else -1))
            M = MO @ Matrix.Translation((0, 0, z)) @ Quaternion((0, 0, 1), a).to_matrix().to_4x4() \
                @ Matrix.Translation((0, 6.5, 0))
            fx.key_matrix(ob, t, M, prev)
        objs.append(ob)
    # bokeh
    for i in range(70):
        sz = rng.uniform(0.06, 0.45)
        me = fx.quad_mesh("tp_bokeh_%02d" % i, sz, sz)
        me.materials.append(_soft_disc_mat("tp_bokeh_%02d" % i, cols[rng.randrange(3)], rng.uniform(0.6, 2.2)))
        ob = bpy.data.objects.new(me.name, me)
        fx.link(ob, light)
        p0 = Vector((rng.uniform(-7, 7), rng.uniform(-4, 4), rng.uniform(-12, -2.0)))
        dv = Vector((rng.gauss(0, 0.006), rng.uniform(0.002, 0.01), 0))
        prev = {}
        for t in (t0 - 1, t1 + 1):
            fx.key_matrix(ob, t, MO @ Matrix.Translation(p0 + dv * (t - t0)), prev)
        objs.append(ob)
    # web strands: radials and a few rings around a vanishing point far behind the page
    vp = Vector((0.4, 0.3, -11.0))
    spl = []
    for i in range(14):
        a = 2 * math.pi * (i + rng.uniform(-0.2, 0.2)) / 14
        spl.append([(vp, 1.0), (vp + Vector((math.cos(a) * 14, math.sin(a) * 9, 7.0)), 1.6)])
    for rr in (2.2, 4.5, 7.5):
        ring = []
        for i in range(15):
            a = 2 * math.pi * i / 14
            ring.append((vp + Vector((math.cos(a) * rr * 1.5, math.sin(a) * rr, rr * 0.5)), 1.0))
        spl.append(ring)
    web = fx.poly_curve("tp_web", spl, 0.006, fx.emission_mat("tp_web", (0.55, 0.62, 0.8), 0.35), caps=False)
    web.matrix_world = MO
    fx.link(web, light)
    objs.append(web)
    # far cards of the three eras, dim, drifting and turning in depth
    for i, sid in enumerate(("S01", "S05", "S09", "S12", "S19", "S25", "S28", "S03")):
        try:
            z = rng.uniform(-10.0, -5.0)
            p0 = Vector((rng.uniform(-5.5, 5.5), rng.uniform(-3.0, 3.0), z))
            if abs(p0.x) < 2.0 and abs(p0.y) < 1.4:
                p0.x += 3.0 * (1 if p0.x >= 0 else -1)
            sc = rng.uniform(0.45, 0.8)
            q = Quaternion(fx.rand_axis(rng), math.radians(rng.uniform(15, 40)))
            card = ctx.make_card(sid, "tp_far_%s" % sid, matrix=MO @ Matrix.LocRotScale(p0, q, Vector((sc, sc, sc))),
                                 frames=(int(t0) - 1, int(t1) + 1))
            veil = bpy.data.objects.new("tp_far_veil_%s" % sid, fx.quad_mesh("tp_far_veil_%s" % sid, 1.96, 1.12))
            vm = bpy.data.materials.new("tp_far_veil_%s" % sid)
            vnt = fx._nt(vm)
            vnt.nodes.clear()
            o = vnt.nodes.new("ShaderNodeOutputMaterial")
            tr = vnt.nodes.new("ShaderNodeBsdfTransparent")
            e2 = vnt.nodes.new("ShaderNodeEmission")
            e2.inputs["Color"].default_value = (0.01, 0.01, 0.02, 1.0)
            mx = vnt.nodes.new("ShaderNodeMixShader")
            mx.inputs[0].default_value = 0.72
            vnt.links.new(tr.outputs[0], mx.inputs[1])
            vnt.links.new(e2.outputs[0], mx.inputs[2])
            vnt.links.new(mx.outputs[0], o.inputs["Surface"])
            veil.data.materials.append(vm)
            veil.parent = card
            veil.matrix_parent_inverse = Matrix()
            veil.location = (0, 0, 0.003)
            fx.link(veil, plate)
            objs.append(veil)
            drift = Vector((rng.gauss(0, 0.004), rng.gauss(0, 0.004), 0.0))
            prev = {}
            for t in (t0 - 1, t1 + 1):
                qq = Quaternion((0, 0, 1), math.radians(0.25 * (t - t0))) @ q
                fx.key_matrix(card, t, MO @ Matrix.LocRotScale(p0 + drift * (t - t0), qq, Vector((sc, sc, sc))), prev)
        except Exception as e:  # noqa: BLE001
            ctx.log("triptych void: far card %s skipped (%s)" % (sid, e))
    for ob in objs:
        fx.key_visible(ob, t0 - 1, t1)
