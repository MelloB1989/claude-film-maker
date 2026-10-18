"""web_wipe (C27, S27 tank crouch -> S28 electric mask, window 680-692, cut 686 on the 2.7 hit): webbed and yanked.

Six web strands shoot from behind the camera (tapered tubes, faintly glowing) and splat onto S27 (web splats pop at
each anchor), the card shivers under the tension, and on the hit it is yanked off to screen right: it accelerates
away, swings open like a torn page and curls, the strands whipping after it, revealing S28 behind it, already playing.
The camera keeps pushing in all through (S27 arrives pushing after C26's zt) with a jolt on the hit: a roll kick and a
leftward slide so S28's picture flows the same way the card flew.

Private set: S27 copy at the origin, S28 copy 0.3 m behind (scaled so it lands at s 1.4, edges never shown).
Teleports: home S27 -> private at w0 + 0.5, private -> home S28 at w1 - 1.5 (card and strands gone off screen right).
"""
import math
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.append(_here)
import bpy  # noqa: E402
from mathutils import Euler, Matrix, Quaternion, Vector  # noqa: E402

import _xfxa as X  # noqa: E402
import camlib  # noqa: E402

FILL = X.FILL
_PLAN = {}
DEPTH_B = 0.3


def _plan(T, ctx):
    key = (T["id"], T["w0"], T["w1"], T["f"])
    if key in _PLAN:
        return _PLAN[key]
    w0, w1, cut = T["w0"], T["w1"], T["f"]
    a, b = T["a"]["id"], T["b"]["id"]
    p = T.get("p", {})
    side = -1.0 if p.get("dir", "R") == "L" else 1.0
    P = dict(w0=w0, w1=w1, cut=cut, a=a, b=b, side=side)
    s0, ds0 = float(p.get("s0", 1.25)), float(p.get("ds0", 0.02))
    z0 = FILL / s0
    s_end = 1.4
    ds_end = X.exit_rate(ctx, T, 0.03)
    v_end = ds_end * FILL * 1.0 / s_end * 0.96  # ~ distance to the S28 copy at the exit x its rate
    spd = X.Speed([(w0, z0 * ds0), (w0 + 4, 0.045), (cut - 0.5, 0.07), (cut + 0.5, 0.07), (cut + 2, 0.05),
                   (w1, max(0.018, v_end))], m0=0.002)
    z = lambda t: z0 - spd.x(t)  # noqa: E731
    P["z"], P["spd"] = z, spd
    # jolt on the hit: slide against the yank (picture flows with the card), roll kick, both decaying ~0.8 / f
    lat = X.Speed([(w0, 0.0), (cut - 2.5, 0.0), (cut - 1.0, -0.010 * side), (cut + 0.4, -0.026 * side), (cut + 2, -0.015 * side),
                   (cut + 4, -0.006 * side), (w1, -0.003 * side)], m0=0.0)
    rol = X.Speed([(w0, 0.0), (cut - 2.5, 0.0), (cut - 1.0, 0.6 * side), (cut + 0.3, 1.6 * side), (cut + 2, 0.9 * side), (cut + 4, 0.4 * side),
                   (w1, 0.2 * side)], m0=0.0)
    P["lat"] = lambda t: lat.x(t)  # noqa: E731
    P["roll"] = lambda t: rol.x(t)  # noqa: E731
    O = ctx.new_set("web_wipe")
    P["O"] = O
    P["MA"] = Matrix.Translation(O)
    # S28 copy: centred under the camera's final position, scaled so it ends at s_end
    xe = P["lat"](w1)
    kB = s_end * (z(w1) + DEPTH_B) / FILL
    theta = P["roll"](w1)
    P["MB"] = (Matrix.Translation(O + Vector((xe, 0.0, -DEPTH_B))) @ Quaternion((0, 0, 1), math.radians(theta)).to_matrix().to_4x4()
               @ Matrix.Scale(kB, 4))
    P["kB"], P["theta"] = kB, theta

    def m_set(t):
        loc = O + Vector((P["lat"](t), 0.0, z(t)))
        return Matrix.Translation(loc) @ Quaternion((0, 0, 1), math.radians(P["roll"](t))).to_matrix().to_4x4()

    def a_state(t):
        return (FILL / z(t), 960.0 + 1000.0 * P["lat"](t), 540.0, P["roll"](t))

    def b_state(t):
        s, cx, cy, r, _ = X.state_from_cam(P["MB"], m_set(t), r_hint=P["roll"](t) - theta)
        return (s, cx, cy, r)

    P["m_set"], P["a_state"], P["b_state"] = m_set, a_state, b_state
    _PLAN[key] = P
    return P


def bounds(T, ctx):
    P = _plan(T, ctx)
    return {"A": X.mix_state(P["a_state"], P["w0"]), "B": X.mix_state_back(P["b_state"], P["w1"])}


# ------------------------------------------------------------------------------------------------- card motion
def _yank_x(P, t):
    """Card travel (m) along the yank: an exponential ramp, speed x1.6 per frame from f cut-4 (REFS: acceleration into
    a hit x1.35-1.7 / f over the last 4 f, no single-frame step), off screen by the teleport."""
    g, t0 = 1.6, P["cut"] - 4.0
    if t <= t0:
        return 0.0
    return 0.255 * (g ** (t - P["cut"]) - g ** (t0 - P["cut"]))


def _card_matrix(P, t):
    """The S27 copy: a shiver under tension, then yanked to screen right, swinging open and turning with its travel."""
    cut, side = P["cut"], P["side"]
    sh = 0.010 * X.bump(t, cut - 3.0, cut - 0.6) * math.sin(9.0 * t)
    x = _yank_x(P, t)
    u = min(1.0, x / 1.6)
    zt = 0.25 * u ** 1.3
    ry = side * math.radians(62.0) * u ** 0.9
    rz = -side * math.radians(10.0) * u
    return Matrix.Translation(P["O"] + Vector((side * (sh + x), 0.0, zt))) @ Euler((0.0, ry, rz)).to_matrix().to_4x4()


def _bend(P, t):
    return -P["side"] * math.radians(110.0) * min(1.0, _yank_x(P, t) / 1.3) ** 1.2


# ------------------------------------------------------------------------------------------------- build
def build(T, ctx):
    P = _plan(T, ctx)
    w0, w1, cut, O, side = P["w0"], P["w1"], P["cut"], P["O"], P["side"]
    a, b = P["a"], P["b"]
    plate_c, light_c = ctx.coll("plate"), ctx.coll("light")
    R = X.rng(686)
    cardA = X.copy_card(ctx, a, "XA_web_S27", P["MA"], frames=(w0 - 1, w1 - 1), tile=1)  # one card, real edges
    X.copy_card(ctx, b, "XA_web_S28", P["MB"], frames=(w0 - 1, w1 + 1))
    sub = cardA.modifiers.new("sub", "SUBSURF")
    sub.subdivision_type = "SIMPLE"
    sub.levels = sub.render_levels = 5
    bend = cardA.modifiers.new("bend", "SIMPLE_DEFORM")
    bend.deform_method = "BEND"
    bend.deform_axis = "Y"
    cardA.rotation_mode = "XYZ"
    ts = [w0 - 1 + 0.5 * i for i in range(2 * (w1 - w0 + 2) + 1)]
    for t in ts:
        cardA.matrix_world = _card_matrix(P, t)
        cardA.keyframe_insert("location", frame=t)
        cardA.keyframe_insert("rotation_euler", frame=t)
        bend.angle = _bend(P, t)
        bend.keyframe_insert("angle", frame=t)
    X.set_linear(cardA)

    # strands: from behind the camera (mostly the yank side) to anchors spread over the card
    anchors_px = [(560, 420), (1010, 300), (1420, 520), (760, 760), (1240, 820), (1560, 260)]
    launches = [w0 + 0.0, w0 + 0.6, w0 + 1.2, w0 + 1.8, w0 + 2.4, w0 + 3.0]
    web_m = X.mat_emit("XA_web_strand_m", (0.88, 0.93, 1.0), 1.25, alpha=0.8)
    splat_m = X.mat_emit("XA_web_splat_m", (0.92, 0.96, 1.0), 1.8)
    NP = 9
    for k, (apx, tl) in enumerate(zip(anchors_px, launches)):
        anc_l = X.px2local(*apx) + Vector((0, 0, 0.004))
        org = Vector((side * R.uniform(0.25, 0.85), R.uniform(-0.45, 0.45), P["z"](w0) + R.uniform(0.35, 0.7)))
        sag = Vector((R.uniform(-1, 1), R.uniform(-1, 1), 0.0)).normalized() * R.uniform(0.02, 0.06)
        cv = X.curve_obj(f"XA_web_strand{k}", [org + O] * NP, light_c, bevel=0.0016, res=6,
                         taper=[(0.0, 0.5), (0.3, 1.0), (0.8, 0.7), (1.0, 0.45)])
        cv.data.materials.append(web_m)
        sp = cv.data.splines[0]
        for t in ts:
            tip = X._sstep(tl, tl + 1.5, t)  # tip travels origin -> anchor in 1.5 f
            M = _card_matrix(P, t)
            anc = M @ anc_l
            yank = _yank_x(P, t)
            o = O + org + Vector((side * 1.1 * yank, 0.06 * yank, -0.05 * yank))
            tension = X._sstep(tl + 1.5, cut - 0.6, t)
            for i, pt in enumerate(sp.points):
                u = tip * i / (NP - 1)
                q = o.lerp(anc, u) + sag * math.sin(math.pi * u) * (1.0 - 0.8 * tension)
                pt.co = (q.x, q.y, q.z, 1.0)
                pt.keyframe_insert("co", frame=t)
        X.set_linear(cv.data)
        X.key_hide(cv, [(int(math.floor(tl)), w1 + 2)])
        # web splat at the anchor, riding on the card
        spl = _splat(f"XA_web_splat{k}", light_c, R)
        spl.data.materials.append(splat_m)
        spl.parent = cardA
        spl.matrix_parent_inverse = Matrix.Identity(4)
        spl.location = anc_l
        for t in ts:
            sc = 0.0001 + X._sstep(tl + 1.4, tl + 2.2, t) * R.uniform(0.9, 1.15) if t > tl + 1.3 else 0.0001
            spl.scale = (sc, sc, sc)
            spl.keyframe_insert("scale", frame=t)
        X.set_linear(spl)
    ctx.env(O, ctx.act_at(cut))

    homeA = ctx.card(a).matrix_world.copy()
    homeB = ctx.card(b).matrix_world.copy()
    t_in, t_out = w0 + 0.5, w1 - 1.5
    to_homeA = homeA @ P["MA"].inverted()
    to_homeB = homeB @ P["MB"].inverted()

    def fn(t):
        m = P["m_set"](t)
        if t < t_in:
            return _norm(to_homeA @ m)
        if t > t_out:
            return _norm(to_homeB @ m)
        return m

    def dof(t):
        """S28 is revealed a touch soft and racks in by +4 f (REFS)."""
        d = P["z"](t) + DEPTH_B
        if t > t_out:
            d /= P["kB"]
        u = X._sstep(cut + 0.5, cut + 4.5, t)
        k = X._sstep(cut - 0.5, cut + 0.5, t)
        return d * X.lerp(0.55, 1.0, u), X.lerp(64.0, X.lerp(1.6, 64.0, u), k)

    X.key_path(ctx, w0, w1, fn, teleports=(t_in, t_out), dof_fn=dof)
    ctx.log(f"web_wipe: yank {'right' if side > 0 else 'left'} from f{cut - 4}, S28 copy x{P['kB']:.2f} "
            f"{DEPTH_B} m behind, s at the reveal {P['b_state'](cut)[0]:.2f}")


def _splat(name, coll, R):
    """A small web splat: spokes and two wobbly rings (curves), unit size ~6 cm."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.0012
    cu.bevel_resolution = 1
    n = R.randint(6, 8)
    ang0 = R.uniform(0, math.pi)
    for i in range(n):
        a = ang0 + 2 * math.pi * i / n + R.uniform(-0.2, 0.2)
        L = R.uniform(0.045, 0.085)
        sp = cu.splines.new("POLY")
        sp.points.add(1)
        sp.points[0].co = (0, 0, 0, 1)
        sp.points[1].co = (L * math.cos(a), L * math.sin(a), 0, 1)
    for rr in (0.022, 0.042):
        sp = cu.splines.new("POLY")
        sp.points.add(n)
        for i in range(n + 1):
            a = ang0 + 2 * math.pi * (i % n) / n
            r = rr * R.uniform(0.85, 1.1)
            sp.points[i].co = (r * math.cos(a), r * math.sin(a), 0, 1)
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    return ob


def _norm(m):
    loc, rot, _ = m.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
