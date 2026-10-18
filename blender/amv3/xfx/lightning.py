"""lightning (C14, 430-445, cut 436; A = S14 water tower leap, B = S15 Electro): Electro's 3D lightning strikes across
A, cracks the picture into big shards lit from inside, and the camera flies through the falling shards into S15.

Private set (ctx.new_set). The camera starts on A's home card at w0 and teleports at w0+0.5 to the same view of the
private set, where A is not a card but a full Voronoi fracture of A's picture (big shards, smaller round the strike),
lying flat and seamless until the break. B is a scaled copy of S15's card behind it (a k x card at k x the distance looks
the same as the real card, so the camera can travel a long way in depth). Timeline (cut f):
  f-4.5   a thin leader bolt flickers in from the top right          (light pass, 3D curves in front of the picture)
  f-3     a second branching bolt from the top left
  f-1.5   the main strike: three trunks converge on the strike point, dense branches, flickering variants every half
          frame, a point light flashing with them; cracks race out from the strike point (light pass)
  f-0.5   the break: shards burst outward from the camera axis, fall and spin, their bevelled glass rims glowing
          electric cyan from inside; short arcs crawl between them for 3 f
  f-0.5.. the camera keeps pushing (REFS: zoom sign kept, push -> push), flies through the opening and lands on
          S15 decelerating (k 0.83/f), rolling the same way, with a 2-4 f rack defocus
  w1-0.5  teleport to S15's home card, same view.
The attack is expo-in (x1.6/f into the cut), the landing decays at k = 0.83/f into the S15 hold drift.
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


def _params(T):
    p = T["p"]
    f = T["f"]
    return dict(
        s_in=p.get("s_in", 1.10), ds_in=p.get("ds_in", 0.02),        # the S14 hold drift (push) at w0
        ds_peak=p.get("ds_peak", 0.24), grow=1.6, decay=p.get("decay", 0.83), floor_in=0.015, drop=1.55,
        dr_peak=p.get("dr_peak", -1.8), dr_floor=-0.3,               # counter-clockwise, kept through the cut
        s_exit=p.get("s_exit", 1.6), ds_floor=0.025,
        impact=p.get("impact", [1105, 400]),                          # A pixels: Spider-Man's chest at the strike
        fh=f - 0.5, tp0=T["w0"] + 0.5, tp1=T["w1"] - 0.5,
    )


class Path:
    """The camera through the window, in the private set's frame: distance z from the A plane along +Z, roll r.

    A: expo-in attack on A's zoom. B is placed (depth D behind A, scale k) so that the SAME camera motion lands B at
    A's zoom rate / DROP and decays it at k = decay per frame (REFS): B's screen rate is the design input, the camera's
    depth path and B's placement follow from it (d_B(u) = d0 exp(-integral of ds_B)). B is a mirror-tiled card, so the
    first landing frames (B under 1x, behind the flying shards) never show a card edge."""

    def __init__(self, T, P):
        self.T, self.P = T, P
        w0, fh, w1 = T["w0"], P["fh"], T["w1"]
        TA, TB = fh - w0, w1 - fh
        self.lsA, self.dlsA = fx.attack(math.log(P["s_in"]), P["ds_in"], P["ds_peak"], TA, P["floor_in"], P["grow"],
                                        P["decay"])
        self.rA, self.drA = fx.attack(0.0, 0.0, P["dr_peak"], TA, 0.0, P["grow"], P["decay"])
        self.z_cut = FILL_DIST / math.exp(self.lsA(TA))
        self.v_cut = self.z_cut * self.dlsA(TA)                     # m/f toward the picture at the cut
        self.lam = -math.log(P["decay"])
        self.b0 = P["ds_peak"] / P["drop"]                           # B's zoom rate on landing
        self.d0 = self.v_cut / self.b0                               # B's distance at the cut
        self.D = self.d0 - self.z_cut
        self.k = P["s_exit"] * self._d(TB) / FILL_DIST
        self.r_cut = self.rA(TA)

    def _dsB(self, u):
        f = self.P["ds_floor"]
        return f + (self.b0 - f) * math.exp(-self.lam * u)

    def _LB(self, u):
        f = self.P["ds_floor"]
        return f * u + (self.b0 - f) * (1 - math.exp(-self.lam * u)) / self.lam

    def _d(self, u):
        return self.d0 * math.exp(-self._LB(u))

    def _zB(self, u):
        return self._d(u) - self.D

    def _rB(self, u):
        P = self.P
        a = P["dr_peak"] - P["dr_floor"]
        return self.r_cut + P["dr_floor"] * u + a * (1 - math.exp(-self.lam * u)) / self.lam

    def _drB(self, u):
        P = self.P
        return P["dr_floor"] + (P["dr_peak"] - P["dr_floor"]) * math.exp(-self.lam * u)

    def stateA(self, t):
        u = t - self.T["w0"]
        return State(math.exp(self.lsA(u)), 960.0, 540.0, self.rA(u), self.dlsA(u), 0.0, 0.0, self.drA(u))

    def z(self, t):
        fh = self.P["fh"]
        return FILL_DIST / math.exp(self.lsA(t - self.T["w0"])) if t <= fh else self._zB(t - fh)

    def r(self, t):
        fh = self.P["fh"]
        return self.rA(t - self.T["w0"]) if t <= fh else self._rB(t - fh)

    def stateB(self, t):
        """The view of B (the k-scaled copy at -D) as a state on an unscaled card: what B's home card must show."""
        u = t - self.P["fh"]
        return State(self.k * FILL_DIST / self._d(u), 960.0, 540.0, self._rB(u), self._dsB(u), 0.0, 0.0, self._drB(u))


def bounds(T, ctx):
    P = _params(T)
    pa = Path(T, P)
    return {"A": pa.stateA(T["w0"]), "B": pa.stateB(T["w1"])}


def build(T, ctx):
    fx.set_linear_keys()
    P = _params(T)
    pa = Path(T, P)
    f, w0, w1, fh = T["f"], T["w0"], T["w1"], P["fh"]
    sa, sb = T["a"]["id"], T["b"]["id"]
    cardA, cardB = ctx.card(sa), ctx.card(sb)
    O = ctx.new_set("lightning_%s" % T["id"])
    MO = Matrix.Translation(O)
    rng = random.Random(4360 + f)
    light, plate = ctx.coll("light"), ctx.coll("plate")
    act = fx.act_id(ctx, f)
    pal = ctx.palette(act)
    ctx.env(O, act, frames=(w0, w1 + 1))
    electric = (0.62, 0.86, 1.0)
    hot = (0.9, 0.97, 1.0)

    # ---- camera: home A -> (tp0) private set -> (tp1) home B
    def cam_private(t):
        return MO @ Matrix.LocRotScale(Vector((0, 0, pa.z(t))), Quaternion((0, 0, 1), math.radians(pa.r(t))), None)

    ctx.key_cam(w0, *ctx.pose(cardA, pa.stateA(w0)))
    ctx.key_cam(P["tp0"] - 0.01, *ctx.pose(cardA, pa.stateA(P["tp0"] - 0.01)))
    ctx.teleport(P["tp0"])
    for t in [P["tp0"] + 0.01] + fx.frames_half(w0 + 1, P["tp1"] - 0.5) + [P["tp1"] - 0.01]:
        loc, rot, _ = cam_private(t).decompose()
        ctx.key_cam(t, loc, rot)
    ctx.teleport(P["tp1"])
    ctx.key_cam(P["tp1"] + 0.01, *ctx.pose(cardB, pa.stateB(P["tp1"] + 0.01)))
    fx.dof(ctx, fh, pa.z(fh), 128.0)
    for t, fr, fs in ((f, 0.55, 2.4), (f + 1, 0.7, 3.2), (f + 2, 0.85, 5.0), (f + 4, 1.0, 12.0), (w1 - 1, 1.0, 128.0)):
        fx.dof(ctx, t, (pa.z(t) + pa.D) * fr, fs)

    # ---- the fractured picture (A), seamless until the break
    imp_px = P["impact"]
    imp = fx.px2local(*imp_px)
    seeds = fx.impact_seeds(rng, (imp.x, imp.y), 0.035, 0.42, rings=4, sectors=8, jitter=0.6, swirl=0.4)
    for s in fx.uniform_seeds(rng, 16, -0.96, -0.54, 0.96, 0.54, min_d=0.26):
        if (Vector((s[0], s[1], 0)) - imp).length > 0.42:
            seeds.append(s)
    cells = fx.voronoi(seeds, fx.rect(-0.96, -0.54, 0.96, 0.54))
    face = fx.picture_glass_mat(fx.plate_mat(ctx, sa), "lt_face", gloss_rough=0.06, gloss=0.7)
    rim = fx.glass_mat("lt_rim", tint=(0.88, 0.96, 1.0), emit=electric, emit_strength=0.0, rough=0.02, ior=1.5)
    shards = fx.build_shards(cells, MO, 0.008, [face, rim], plate, "lt_shard", rng, uv_fn=fx.local2uv,
                             bevel_w=0.0025)
    prev = {}
    for sh in shards:
        sh.track = {}
        c = (MO.inverted() @ sh.rest).translation
        out = Vector((c.x, c.y, 0))
        out = out.normalized() if out.length > 1e-6 else Vector((1, 0, 0))
        di = Vector((c.x - imp.x, c.y - imp.y, 0))
        near = max(0.0, 1.0 - di.length / 0.6)
        v = out * (0.012 + 0.022 * sh.speed) + (di.normalized() if di.length > 1e-6 else out) * 0.03 * near
        v.z = 0.02 * sh.jit.z + 0.025 * near
        if sh.delay < 0.3:          # a third of the pieces come at the lens and pass it (436-439): depth, glints
            v = v * 0.4
            v.z = 0.08 + 0.10 * sh.speed
        spin = sh.spin * (6 + 14 * near) * (1 if sh.jit.x > 0 else -1)
        for t in fx.frames_half(P["tp0"], P["tp1"]):
            u = max(0.0, t - fh)
            pos = c + v * u * (1 + 0.15 * u) + Vector((0, -0.004 * u * u, 0))
            if fh - 1.0 <= t < fh:     # the picture buzzes with the charge for a frame before it breaks
                pos = pos + Vector((rng.gauss(0, 0.0012), rng.gauss(0, 0.0012), abs(rng.gauss(0, 0.0015))))
            M = MO @ Matrix.LocRotScale(pos, Quaternion(sh.axis, math.radians(spin * u * (1 + 0.1 * u))), None)
            fx.key_matrix(sh.ob, t, M, prev)
            sh.track[t] = pos.copy()
        fx.key_visible(sh.ob, fh, P["tp1"])
    intact = ctx.make_card(sa, "lt_A_" + sa, matrix=MO, frames=(w0, f))  # seamless picture until the break (shard bevels show seams)
    fx.key_visible(intact, P["tp0"], fh)
    for t, g in ((fh - 0.5, 0.0), (fh, 4.0), (f, 3.5), (f + 1, 2.5), (f + 3, 1.2), (f + 6, 0.5)):
        fx.key_glass_glow(rim, t, g)

    # ---- cracks racing out from the strike point (light pass), then the rims take over
    crack = fx.crack_material("lt_crack", hot, imp)
    splines = []
    for (p, q) in fx.cell_edges(cells):
        a, b = Vector((p[0], p[1], 0.0045)), Vector((q[0], q[1], 0.0045))
        if abs(a.x) > 0.959 and abs(b.x) > 0.959 or abs(a.y) > 0.539 and abs(b.y) > 0.539:
            continue  # the card's own border is not a crack
        pts = fx.bolt_path(rng, a, b, 3, 0.05, normal=Vector((0, 0, 1)), zjag=0.0)
        splines.append([(x, 1.0) for x in pts])
    cr = fx.poly_curve("lt_cracks", splines, 0.0006, crack)
    cr.matrix_world = MO
    fx.link(cr, light)
    fx.key_visible(cr, f - 2.0, fh + 0.5)
    for t, rr, g in ((f - 2.0, 0.0, 0.0), (f - 1.5, 0.12, 5.0), (f - 1.0, 0.45, 6.0), (fh, 1.6, 7.0),
                     (fh + 0.5, 2.5, 3.0)):
        fx.key_crack(crack, t, rr, g)

    # ---- the bolts
    tip = imp + Vector((0, 0, 0.01))
    strikes = [  # (frames, [(start, n_branches)], radius): a fresh bolt shape every frame, each lit for that frame only
        ((f - 5, f - 4), [(Vector((0.95, 0.75, 0.10)), 9)], 0.0010),
        ((f - 3,), [(Vector((-1.0, 0.70, 0.08)), 12), (Vector((1.1, -0.2, 0.12)), 8)], 0.0012),
        ((f - 2, f - 1), [(Vector((-1.15, 0.85, 0.14)), 14), (Vector((1.05, 0.80, 0.06)), 14),
                          (Vector((0.10, 1.05, 0.18)), 10), (Vector((-1.1, -0.6, 0.10)), 10),
                          (Vector((1.2, -0.7, 0.15)), 10)], 0.0024),
    ]
    flick = {}
    for frames, trunks, rad in strikes:
        for kf in frames:
            fl = rng.uniform(0.7, 1.4)
            flick[kf] = fl
            spl = []
            for start, nb in trunks:
                spl += fx.bolt_tree(rng, start + Vector((rng.gauss(0, 0.05), rng.gauss(0, 0.05), 0)), tip, levels=7,
                                    jag=0.17, branches=nb, sub=3, normal=Vector((0, 0, 1)), r0=1.0, r1=0.45)
            core = fx.poly_curve("lt_bolt_%d" % kf, spl, rad, fx.emission_mat("lt_bolt_%d" % kf, hot, 9.0 * fl,
                                                                              additive=True))
            halo = fx.poly_curve("lt_halo_%d" % kf, spl, rad * 3.0,
                                 fx.emission_mat("lt_halo_%d" % kf, (0.25, 0.6, 1.0), 0.9 * fl, additive=True))
            for ob in (core, halo):
                # rides with the camera through its frame, so camera motion blur leaves it a crisp filament
                fx.ride_camera(ob, cam_private, MO, kf, kf - 0.5, kf + 0.5)
                fx.link(ob, light)
                fx.key_visible(ob, kf - 0.5, kf + 0.5)
    _arcs(rng, MO, shards, fh, f, hot, electric, light, cam_private)
    _storm(MO, w0, fh, flick, P, plate)

    # ---- light from the strike (glints on the glass, rims)
    ld = bpy.data.lights.new("lt_strike", "POINT")
    ld.color = electric
    ld.shadow_soft_size = 0.05
    lo = bpy.data.objects.new("lt_strike", ld)
    lo.visible_camera = False
    lo.matrix_world = MO @ Matrix.Translation(imp + Vector((0, 0.05, 0.25)))
    bpy.context.scene.collection.objects.link(lo)
    ld.energy = 0.0
    ld.keyframe_insert("energy", frame=w0)
    for t in sorted(flick):
        ld.energy = 60.0 * flick[t]
        ld.keyframe_insert("energy", frame=t)
    for t, e in ((f + 1, 30.0), (f + 3, 8.0), (f + 5, 0.0)):
        ld.energy = e
        ld.keyframe_insert("energy", frame=t)

    # ---- B behind: a k x copy of S15's card at -D
    MB = MO @ Matrix.Translation((0, 0, -pa.D)) @ Matrix.Scale(pa.k, 4)
    try:
        ctx.make_card(sb, "lt_B_" + sb, matrix=MB, frames=(w0, w1 + 1), tile=3)
    except TypeError:
        ctx.make_card(sb, "lt_B_" + sb, matrix=MB)
    ctx.log("lightning: %d shards, z_cut %.3f m (s %.2f), D %.3f m, B k %.2f, B at cut s %.2f ds %.3f, end z %.3f"
            % (len(shards), pa.z_cut, FILL_DIST / pa.z_cut, pa.D, pa.k, pa.stateB(fh).s, pa.stateB(fh).ds,
               pa.z(w1)))


def _arcs(rng, MO, shards, fh, f, hot, electric, light, cam_fn):
    """Short arcs jumping across the opening cracks for 3 frames after the break, fading."""
    mat = fx.emission_mat("lt_arc", hot, 18.0, additive=True)
    big = sorted(shards, key=lambda s: -s.size)[:14]
    k = 0
    for t in fx.frames_half(fh, f + 2.5):
        for _ in range(4):
            a, b = rng.sample(big, 2)
            pa, pb = a.track[t], b.track[t]
            if (pa - pb).length > 0.7:
                continue
            spl = fx.bolt_tree(rng, pa + Vector((0, 0, 0.01)), pb + Vector((0, 0, 0.01)), levels=5, jag=0.22,
                               branches=2, sub=1, normal=Vector((0, 0, 1)), r0=1.0, r1=0.6)
            ob = fx.poly_curve("lt_arc_%03d" % k, spl, 0.0012, mat)
            k += 1
            fx.ride_camera(ob, cam_fn, MO, t, t - 0.5, t + 1.0)
            fx.link(ob, light)
            fx.key_visible(ob, t, t + 0.5)
    for t, g in ((fh, 22.0), (f + 1, 12.0), (f + 2.5, 4.0)):
        fx.key_glow(mat, t, g)


def _storm(MO, w0, fh, flick, P, coll):
    """A dark storm veil just in front of A (transparent mixed with a dim cold teal): the sunny sky darkens as the
    charge arrives, and every strike lights it back up for its frame, so the bolts pop like the reference's lightning
    over a darkened teal plate."""
    m = bpy.data.materials.new("lt_storm")
    nt = fx._nt(m)
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.015, 0.07, 0.11, 1.0)
    em.inputs["Strength"].default_value = 1.0
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.name = "veil"
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    me = fx.quad_mesh("lt_storm", 1.96, 1.12)
    me.materials.append(m)
    ob = bpy.data.objects.new("lt_storm", me)
    ob.matrix_world = MO @ Matrix.Translation((0, 0, 0.0035))
    coll.objects.link(ob)
    fac = mix.inputs[0]

    def key(t, v):
        fac.default_value = v
        fac.keyframe_insert("default_value", frame=t)
    key(P["tp0"], 0.0)
    for t in range(int(P["tp0"] + 0.5), int(fh + 0.5)):    # darker frame by frame; a strong strike lifts it a little
        v = min(0.78, 0.22 * (t - P["tp0"] + 0.5)) - (0.12 if flick.get(t, 0) > 1.2 else 0.0)
        key(t - 0.45, v)
        key(t + 0.45, v)
    key(fh, 0.0)
    fx.key_visible(ob, P["tp0"], fh)
