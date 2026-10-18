"""Timeless v3 stage: the core flow transitions (open, zt, whip, cube, flip, slam), same interface as an xfx module:
bounds(T, ctx) -> {"A": State at w0, "B": State at w1} and build(T, ctx) (keys the camera on [w0, w1), adds objects).

Motion model (EDIT.md "motion rules"): A accelerates into the cut with a normalised exponential ease (expo_in, end slope
~k), B decelerates out of it with the mirrored ease; the ease constants are solved so the camera speed (d ln s, roll rate,
angular rate) is the same on both sides of the cut, peaks at the cut, and every window edge meets the hold's rate
exactly (C1). Peak speeds give 2-4 smeared frames with the 0.75-1.0 shutter; the B ease is steep so the landing is sharp
3-4 frames after the cut.
"""
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

import camlib as cl
import cards

TYPES = ("open", "zt", "whip", "cube", "flip", "slam")


# ---- shared curve helpers ----------------------------------------------------------------------------------------------
def ramp_in(v0, d0, v1, T, k, tau):
    """Accelerating segment: value v0 with rate d0 at tau = 0, reaches v1 at tau = T. -> (value, rate)."""
    X = v1 - v0 - d0 * T
    u = tau / T
    return v0 + d0 * tau + X * cl.expo_in(u, k), d0 + X * cl.expo_in_d(u, k) / T


def ramp_in_end_rate(v0, d0, v1, T, k):
    return d0 + (v1 - v0 - d0 * T) * cl.expo_in_d(1.0, k) / T


def ramp_out(vs, v1, d1, T, k, taup):
    """Decelerating segment, mirrored: value vs at the start (taup = T), ends at v1 with rate d1 (taup = 0); taup = time
    left to the end. -> (value, rate)."""
    D = vs - v1 + d1 * T
    u = taup / T
    return v1 - d1 * taup + D * cl.expo_in(u, k), d1 - D * cl.expo_in_d(u, k) / T


def k_for_start_rate(vs, v1, d1, T, target, kmax=40.0):
    """The ease k of a ramp_out whose start rate is `target`."""
    D = vs - v1 + d1 * T
    if abs(D) < 1e-6:
        return 4.0
    slope = (d1 - target) * T / D
    return min(kmax, cl.expo_k_for_slope(slope))


def roll_split(A_dr, B_dr, R, TA, TB, kA, kB):
    """Split R degrees of window roll so the roll rate is equal on both sides of the cut. -> (XA, XB): the eased parts."""
    a = cl.expo_in_d(1.0, kA) / TA
    b = cl.expo_in_d(1.0, kB) / TB
    Rp = R - A_dr * TA - B_dr * TB
    XA = (B_dr - A_dr + Rp * b) / (a + b)
    return XA, Rp - XA


def fin(st):
    st.cx, st.cy = cl.clamp_center(st.s, st.cx, st.cy, st.r, 0.004)
    return st


def focus_of(T, which):
    p = T.get("p", {})
    f = p.get(f"focus_{which}") or (T[which] or {}).get("focus") or [960, 540]
    return [float(f[0]), float(f[1])]


def rot_about(P, axis, ang):
    """World matrix rotating by ang (rad) about the line through P along axis."""
    return Matrix.Translation(P) @ Matrix.Rotation(ang, 4, Vector(axis)) @ Matrix.Translation(-P)


def local_matrix(st):
    (x, y, z), roll = cl.local_pose(st)
    return Matrix.Translation((x, y, z)) @ Matrix.Rotation(roll, 4, "Z")


def mat_pose(M):
    loc, rot, _ = M.decompose()
    return loc, rot


def act_for(T, ctx):
    return ctx.act_at(T["f"])


# ---- turn profile (whip / cube): accelerate into the cut, decelerate out, optional overshoot ------------------------------
class Turn:
    """theta(t) from 0 at w0 to total at w1, peak rate at the cut f, zero rate at both ends, `over` = overshoot fraction."""

    def __init__(self, total, w0, f, w1, kA=4.0, kB=4.0, over=0.0):
        self.total, self.w0, self.f, self.w1 = total, w0, f, w1
        self.pre, self.post = float(f - w0), float(w1 - f)
        self.kA, self.kB = kA, kB
        a = cl.expo_in_d(1.0, kA)
        o = 0.0
        tc = total / 2
        for _ in range(4):
            b = 2 + kB + o
            tc = total * (b / self.post) / (a / self.pre + b / self.post)
            want = over * abs(total) / max(1e-6, abs(total - tc))
            o = self._o_for(want) if over > 0 else 0.0
        self.o, self.tc, self.a, self.b = o, tc, a, 2 + kB + o

    def _G(self, u, o):
        return (1 - u) ** 2 * (math.exp(-self.kB * u) - o * u)

    def _o_for(self, want):
        lo, hi = 0.0, 5.0
        for _ in range(40):
            mid = (lo + hi) / 2
            mn = min(self._G(i / 100, mid) for i in range(101))
            if -mn < want:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def __call__(self, t):
        if t <= self.w0:
            return 0.0
        if t >= self.w1:
            return self.total
        if t <= self.f:
            return self.tc * cl.expo_in((t - self.w0) / self.pre, self.kA)
        return self.total + (self.tc - self.total) * self._G((t - self.f) / self.post, self.o)


def window_blend(A, B, w0, w1, t):
    """The card-space state during a whip/cube: A's drift extrapolated, crossfaded (smootherstep, C1) into B's."""
    u = (t - w0) / float(w1 - w0)
    w = cl.smootherstep(u)
    h = 1e-3
    dw = (cl.smootherstep(u + h) - cl.smootherstep(u - h)) / (2 * h) / float(w1 - w0)
    return cl.blend_state(A.at(t - w0), B.at(t - w1), w, dw)


# ======================================================================================================================
def bounds(T, ctx):
    typ = T["type"]
    out = {}
    if T.get("a"):
        out["A"] = ctx.entry_state(T)
    if T.get("b"):
        B = ctx.exit_state(T)
        if typ == "zt" and T["p"].get("mode") == "push":
            land = float(T["p"].get("land", 1.12))
            # B keeps pushing: it must end above the landing scale, still pushing in
            B = B.with_(s=max(B.s, land * 1.07), ds=max(B.ds, 0.012))
        if typ == "open":
            B = B
        out["B"] = B
    return out


def build(T, ctx):
    {"open": build_open, "zt": build_zt, "whip": build_turn, "cube": build_turn, "flip": build_flip,
     "slam": build_slam}[T["type"]](T, ctx)


# ---- zt: zoom-through ---------------------------------------------------------------------------------------------------
def zt_curves(T, ctx, A, B, peak, land, R, push=False, kA=5.0, match=1.0):
    """The zoom-through state functions: (stateA(t) for t < t_h, stateB(t) for t > t_h, info)."""
    w0, w1, f = T["w0"], T["w1"], T["f"]
    th = f - 0.5
    TA, TB = th - w0, w1 - th
    fa, fb = focus_of(T, "a"), focus_of(T, "b")
    LA0, Lp = math.log(A.s), math.log(peak)
    RA = ramp_in_end_rate(LA0, A.ds, Lp, TA, kA)
    LB1, Ll = math.log(B.s), math.log(land)
    target = (RA if push else -RA) * match
    kB = k_for_start_rate(Ll, LB1, B.ds, TB, target)
    XA, XB = roll_split(A.dr, B.dr, R, TA, TB, kA, kB)
    rA_end = A.r + A.dr * TA + XA
    rB_start = B.r - B.dr * TB - XB

    def stA(t):
        tau = t - w0
        L, dL = ramp_in(LA0, A.ds, Lp, TA, kA, tau)
        cx, dcx = ramp_in(A.cx, A.dcx, fa[0], TA, kA, tau)
        cy, dcy = ramp_in(A.cy, A.dcy, fa[1], TA, kA, tau)
        r, dr = ramp_in(A.r, A.dr, rA_end, TA, kA, tau)
        return fin(cl.State(math.exp(L), cx, cy, r, dL, dcx, dcy, dr))

    def stB(t):
        tp = w1 - t
        L, dL = ramp_out(Ll, LB1, B.ds, TB, kB, tp)
        cx, dcx = ramp_out(fb[0], B.cx, B.dcx, TB, kB, tp)
        cy, dcy = ramp_out(fb[1], B.cy, B.dcy, TB, kB, tp)
        r, dr = ramp_out(rB_start, B.r, B.dr, TB, kB, tp)
        return fin(cl.State(math.exp(L), cx, cy, r, dL, dcx, dcy, dr))
    return stA, stB, dict(kA=kA, kB=kB, RA=RA, RB=ramp_out(Ll, LB1, B.ds, TB, kB, TB)[1])


def build_zt(T, ctx):
    p = T["p"]
    A, B = ctx.bounds[T["id"]]["A"], ctx.bounds[T["id"]]["B"]
    push = p.get("mode") == "push"
    stA, stB, info = zt_curves(T, ctx, A, B, float(p.get("peak", 3.0)), float(p.get("land", 2.4)),
                               float(p.get("roll", 0.0)), push, float(p.get("kA", 5.0)))
    th = T["f"] - 0.5
    ctx.teleport(th)
    ca, cb = ctx.card(T["a"]["id"]), ctx.card(T["b"]["id"])

    def fn(t):
        return ctx.pose(ca, stA(t)) if t < th else ctx.pose(cb, stB(t))
    ctx.key_path(fn, T["w0"], T["w1"], 0.25)
    ctx.log(f"  zt {T['id']}: kA {info['kA']:.1f} kB {info['kB']:.1f} peak rate {info['RA']:+.3f} | {info['RB']:+.3f} "
            f"d ln s/f{' push' if push else ''}")


# ---- open: out of black onto S01 ------------------------------------------------------------------------------------------
def build_open(T, ctx):
    p = T["p"]
    B = ctx.bounds[T["id"]]["B"]
    sid = T["b"]["id"]
    w0, w1 = T["w0"], T["w1"]
    TB = float(w1 - w0)
    s0 = float(p.get("from_scale", 1.9))
    fb = focus_of(T, "b")
    k = 3.0
    card = ctx.card(sid)
    r0 = B.r - B.dr * TB + 4.0

    def st(t):
        tp = w1 - t
        L, dL = ramp_out(math.log(s0), math.log(B.s), B.ds, TB, k, tp)
        cx, dcx = ramp_out(fb[0], B.cx, B.dcx, TB, k, tp)
        cy, dcy = ramp_out(fb[1], B.cy, B.dcy, TB, k, tp)
        r, dr = ramp_out(r0, B.r, B.dr, TB, k, tp)
        return fin(cl.State(math.exp(L), cx, cy, r, dL, dcx, dcy, dr))
    ctx.key_path(lambda t: ctx.pose(card, st(t)), w0, w1, 0.5)
    # fade up from black + a light sweep across the picture
    plate = ctx._sequence("plates", sid, "jpg")
    mat = cards.card_material(f"m_open_{sid}", plate, sweep=True)
    card.data.materials.clear()
    card.data.materials.append(mat)
    nt = mat.node_tree
    em = nt.nodes["Emission"].inputs[1]
    sw = nt.nodes["Sweep"].outputs[0]
    amt = nt.nodes["SweepAmt"].outputs[0]
    for f in range(w0, w1 + 1):
        em.default_value = cl.smoothstep((f - w0) / 12.0) ** 1.5
        em.keyframe_insert("default_value", frame=f)
        u = (f - (w0 + 4)) / 18.0
        sw.default_value = -0.25 + 1.5 * cl.ease_in_out_cubic(u)
        sw.keyframe_insert("default_value", frame=f)
        amt.default_value = 0.45 * math.sin(math.pi * cl.clamp01(u))
        amt.keyframe_insert("default_value", frame=f)


# ---- whip / cube: a turn on a private set ----------------------------------------------------------------------------------
WHIP_AXES = {"R": ((0, 1, 0), -1), "L": ((0, 1, 0), 1), "U": ((1, 0, 0), 1), "D": ((1, 0, 0), -1)}


def build_turn(T, ctx):
    p = T["p"]
    typ = T["type"]
    A, B = ctx.bounds[T["id"]]["A"], ctx.bounds[T["id"]]["B"]
    w0, w1, f = T["w0"], T["w1"], T["f"]
    d = p.get("dir", "R" if typ == "whip" else "L")
    act = act_for(T, ctx)
    pal = ctx.palette(act)
    o = ctx.new_set(f"{typ}_{T['id']}")
    FA = Matrix.Translation(o)
    vis = (w0 - 1, w1 + 1)
    axis, sgn = WHIP_AXES[d]
    if typ == "whip":
        ang = math.radians(float(p.get("angle", 70))) * sgn
        mid = window_blend(A, B, w0, w1, f)
        P = FA @ Vector(cl.local_pose(mid)[0])
        turn = Turn(ang, w0, f, w1, 4.0, 4.0, over=0.025)
    else:
        # cube: dir = the way the cube turns; the camera orbits the other way round the box centre
        cube_sgn = {"L": 1, "R": -1, "U": 1, "D": -1}[d]
        axis = (0, 1, 0) if d in "LR" else (1, 0, 0)
        ang = math.radians(90.0) * cube_sgn
        hd = (cl.CARD_W if d in "LR" else cl.CARD_H) / 2
        P = o + Vector((0, 0, -hd))
        turn = Turn(ang, w0, f, w1, 3.5, 3.5, over=0.0)
    FB = rot_about(P, axis, ang) @ FA
    ca = ctx.make_card(T["a"]["id"], f"{typ}_{T['id']}_A", FA, frames=vis)
    cb = ctx.make_card(T["b"]["id"], f"{typ}_{T['id']}_B", FB, frames=vis)
    ctx.env(o, act, frames=vis)
    pb = math.log(float(p.get("pullback", 1.75))) if typ == "cube" else 0.0

    if typ == "whip":
        # light between the cards: haze sheets on the arc, so the smear is light, never black
        for i, (fr, dist, sc) in enumerate(((0.5, 2.6, 1.0), (0.3, 3.4, 1.3), (0.72, 3.2, 1.2))):
            M = rot_about(P, axis, ang * fr) @ Matrix.Translation(P + Vector((0, 0, -dist)))
            h = cards.haze_card(f"whip_{T['id']}_haze{i}", pal["leak"] if i != 1 else pal["rim"], 1.8, 0.55,
                                ctx.coll("plate"), M, (3.6 * sc, 2.4 * sc))
            ctx.show(h, *vis)
    else:
        box_and_glints(T, ctx, o, P, axis, d, hd, pal, vis, turn)

    ctx.teleport(w0 - 0.5)
    ctx.teleport(w1 - 0.5)

    def fn(t):
        st = window_blend(A, B, w0, w1, t)
        if pb:
            u = (t - w0) / float(w1 - w0)
            st = st.with_(s=st.s * math.exp(-pb * math.sin(math.pi * u) ** 2))
        else:
            st = fin(st)
        M = rot_about(P, axis, turn(t)) @ FA @ local_matrix(st)
        return mat_pose(M)
    ctx.key_path(fn, w0, w1, 0.25)
    ctx.log(f"  {typ} {T['id']} dir {d}: turn {math.degrees(ang):+.0f} deg, peak at f{f}, overshoot o={turn.o:.2f}")


def box_and_glints(T, ctx, o, C, axis, d, hd, pal, vis, turn):
    """The cube's body (dark glossy, inset 3 mm under the two picture faces) and emissive glints on the face edges."""
    sx, sy, sz = cl.CARD_W / 2 - 0.003, cl.CARD_H / 2 - 0.003, hd - 0.003
    me = bpy.data.meshes.new(f"cube_{T['id']}_body")
    v = [(x, y, z) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]
    fcs = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me.from_pydata(v, [], fcs)
    m = bpy.data.materials.new(f"cube_{T['id']}_body")
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*[x * 0.08 for x in pal["fog"]], 1)
    bsdf.inputs["Roughness"].default_value = 0.25
    em_in = bsdf.inputs.get("Emission Color")
    if em_in is not None:
        em_in.default_value = (*[x * 4 for x in pal["fog"]], 1)
        bsdf.inputs["Emission Strength"].default_value = 1.0
    me.materials.append(m)
    body = bpy.data.objects.new(f"cube_{T['id']}_body", me)
    body.location = C
    ctx.coll("plate").objects.link(body)
    cards.no_shadow(body)
    ctx.show(body, *vis)
    # glints: thin emissive bars on the 4 edges of the front face and the 4 edges of the B face, brightest at the cut
    gm = cards.emission_material(f"cube_{T['id']}_glint", tuple(min(1.0, x * 0.6 + 0.4) for x in pal["key"]), 0.0)
    em = gm.node_tree.nodes["Emission"].inputs["Strength"]
    for fr in range(T["w0"] - 1, T["w1"] + 2):
        x = (fr - T["f"]) / 4.0
        em.default_value = 9.0 * math.exp(-x * x)
        em.keyframe_insert("default_value", frame=fr)
    th = 0.007
    bars = []
    W, H = cl.CARD_W, cl.CARD_H
    for (cx, cy, lx, ly) in ((0, H / 2, W, th), (0, -H / 2, W, th), (W / 2, 0, th, H), (-W / 2, 0, th, H)):
        bars.append(((cx, cy, 0.002), (lx, ly, th)))
    FB = rot_about(C, axis, turn.total)
    for k, ((x, y, z), (lx, ly, lz)) in enumerate(bars * 2):
        bm = bpy.data.meshes.new(f"glint{k}")
        hx, hy, hz = lx / 2, ly / 2, lz / 2
        vv = [(a, b, c) for a in (-hx, hx) for b in (-hy, hy) for c in (-hz, hz)]
        bm.from_pydata(vv, [], fcs)
        bm.materials.append(gm)
        ob = bpy.data.objects.new(f"cube_{T['id']}_glint{k}", bm)
        M = Matrix.Translation(o + Vector((x, y, z)))
        ob.matrix_world = M if k < 4 else FB @ M
        ctx.coll("light").objects.link(ob)
        cards.no_shadow(ob)
        ctx.show(ob, *vis)


# ---- flip: A swings open like a door (away from the camera) revealing B; the camera pushes through ----------------------
def build_flip(T, ctx):
    p = T["p"]
    A, B = ctx.bounds[T["id"]]["A"], ctx.bounds[T["id"]]["B"]
    w0, w1, f = T["w0"], T["w1"], T["f"]
    hinge = p.get("hinge", "L")
    act = act_for(T, ctx)
    pal = ctx.palette(act)
    o = ctx.new_set(f"flip_{T['id']}")
    g, kb = float(p.get("gap", 2.2)), float(p.get("b_scale", 0.8))
    vis = (w0 - 1, w1 + 1)
    MB = Matrix.Translation(o) @ Matrix.Scale(kb, 4)
    cb = ctx.make_card(T["b"]["id"], f"flip_{T['id']}_B", MB, frames=vis)
    hx = -cl.CARD_W / 2 if hinge == "L" else cl.CARD_W / 2
    piv = bpy.data.objects.new(f"flip_{T['id']}_hinge", None)
    piv.location = o + Vector((hx, 0, g))
    piv.rotation_mode = "XYZ"
    ctx.coll("plate").objects.link(piv)
    ca = ctx.make_card(T["a"]["id"], f"flip_{T['id']}_A", Matrix.Translation(o + Vector((0, 0, g))), frames=vis,
                       backface=tuple(x * 0.15 for x in pal["key"]))
    ca.parent = piv
    ca.matrix_parent_inverse = Matrix.Translation(piv.location).inverted()
    ctx.env(o, act, frames=vis)
    sg = 1 if hinge == "L" else -1
    phimax = math.radians(float(p.get("angle", 105)))
    for fr2 in range(2 * (w0 - 1), 2 * (w1 + 1) + 1):
        t = fr2 / 2.0
        u = (t - w0) / float(w1 - w0)
        piv.rotation_euler = (0, sg * phimax * cl.smootherstep(u / 0.7), 0)
        piv.keyframe_insert("rotation_euler", frame=t)
    # A's state re-expressed against the (scaled) B card: one C1 Hermite push from A's framing to B's
    xA, yA, zA = cl.local_pose(A)[0]
    zw = g + zA
    sAp = cl.FILL_DIST * kb / zw
    cxA, cyA = cl.local_to_px(xA / kb, yA / kb)
    dz = -cl.FILL_DIST / A.s * A.ds
    Ap = cl.State(sAp, cxA, cyA, A.r, -dz / zw, A.dcx / kb, A.dcy / kb, A.dr)
    ctx.teleport(w0 - 0.5)
    ctx.teleport(w1 - 0.5)

    def fn(t):
        return ctx.pose(cb, cl.hermite_state(Ap, B, w0, w1, t))
    ctx.key_path(fn, w0, w1, 0.25)
    ctx.log(f"  flip {T['id']} hinge {hinge}: B at {g} m behind, scale {kb}, push s_eff {sAp:.2f} -> {B.s:.2f}")


# ---- slam: superhero landing ---------------------------------------------------------------------------------------------
def build_slam(T, ctx):
    p = T["p"]
    A, B = ctx.bounds[T["id"]]["A"], ctx.bounds[T["id"]]["B"]
    w0, w1, f = T["w0"], T["w1"], T["f"]
    th = f - 0.5
    TA = th - w0
    kA = 5.0
    peak = float(p.get("peak", 2.6))
    kick = float(p.get("kick", 1.35))
    sc0 = float(p.get("start", 1.03))
    LA0, Lp = math.log(A.s), math.log(peak)
    RA = ramp_in_end_rate(LA0, A.ds, Lp, TA, kA)
    fa = focus_of(T, "a")
    Tk = float(p.get("stop", 3.0))
    te = th + Tk
    re = -0.006  # already easing back out at the stop: the camera never freezes
    kB = k_for_start_rate(math.log(sc0), math.log(kick), re, Tk, RA)
    Bst = B.at(te - w1)
    K = cl.State(kick, Bst.cx, Bst.cy, Bst.r, re, Bst.dcx, Bst.dcy, Bst.dr)
    ctx.teleport(th)
    ca, cb = ctx.card(T["a"]["id"]), ctx.card(T["b"]["id"])

    def fn(t):
        if t < th:
            tau = t - w0
            L, dL = ramp_in(LA0, A.ds, Lp, TA, kA, tau)
            cx, dcx = ramp_in(A.cx, A.dcx, fa[0], TA, kA, tau)
            cy, dcy = ramp_in(A.cy, A.dcy, fa[1], TA, kA, tau)
            st = cl.State(math.exp(L), cx, cy, A.r + A.dr * tau, dL, dcx, dcy, A.dr)
            return ctx.pose(ca, fin(st))
        if t < te:
            L, dL = ramp_out(math.log(sc0), math.log(kick), re, Tk, kB, te - t)
            b = B.at(t - w1)
            st = cl.State(math.exp(L), b.cx, b.cy, b.r, dL, b.dcx, b.dcy, b.dr)
        else:
            st = cl.hermite_state(K, B, te, w1, t)
        return ctx.pose(cb, fin(st))
    ctx.key_path(fn, w0, w1, 0.25)
    shockwave(T, ctx, cb, f)
    ctx.log(f"  slam {T['id']}: peak rate {RA:+.3f}, stop k {kB:.1f} at {kick}x")


def shockwave(T, ctx, card, f):
    """A dust shockwave ring expanding over the landing (lies on the ground in perspective)."""
    pal = ctx.palette(ctx.act_at(f))
    dust = tuple(0.55 + 0.45 * x for x in pal["key"])
    m = bpy.data.materials.new(f"shock_{T['id']}")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vm = nt.nodes.new("ShaderNodeVectorMath"); vm.operation = "SUBTRACT"; vm.inputs[1].default_value = (0.5, 0.5, 0)
    nt.links.new(tc.outputs["UV"], vm.inputs[0])
    ln = nt.nodes.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; nt.links.new(vm.outputs[0], ln.inputs[0])
    band = nt.nodes.new("ShaderNodeMath"); band.operation = "SUBTRACT"; band.inputs[1].default_value = 0.42
    nt.links.new(ln.outputs["Value"], band.inputs[0])
    ab = nt.nodes.new("ShaderNodeMath"); ab.operation = "ABSOLUTE"; nt.links.new(band.outputs[0], ab.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.interpolation_type = "SMOOTHSTEP"
    mr.inputs["From Min"].default_value = 0.07; mr.inputs["From Max"].default_value = 0.0
    nt.links.new(ab.outputs[0], mr.inputs["Value"])
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 9.0; nz.inputs["Detail"].default_value = 5
    nt.links.new(tc.outputs["UV"], nz.inputs["Vector"])
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
    nt.links.new(mr.outputs["Result"], mul.inputs[0]); nt.links.new(nz.outputs["Fac"], mul.inputs[1])
    al = nt.nodes.new("ShaderNodeMath"); al.operation = "MULTIPLY"; al.name = "Alpha"; al.inputs[1].default_value = 1.0
    nt.links.new(mul.outputs[0], al.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*dust, 1); em.inputs[1].default_value = 1.6
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(al.outputs[0], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    me = cards.card_mesh(f"shock_{T['id']}", 1, 1, 1.0, 1.0)
    me.materials.append(m)
    ob = bpy.data.objects.new(f"shock_{T['id']}", me)
    base = card.matrix_world @ Matrix.Translation((0.0, -0.28, 0.06)) @ Matrix.Rotation(math.radians(-72), 4, "X")
    ob.matrix_world = base
    ctx.coll("plate").objects.link(ob)
    cards.no_shadow(ob)
    a = al.inputs[1]
    for fr in range(f - 1, f + 14):
        u = cl.clamp01((fr - f + 0.5) / 12.0)
        sc = 0.15 + 3.2 * cl.ease_out_expo(u * 0.9)
        ob.scale = (sc, sc, 1)
        ob.keyframe_insert("scale", frame=fr)
        a.default_value = (1 - u) ** 1.5 * cl.smoothstep((fr - f + 1) / 1.5)
        a.keyframe_insert("default_value", frame=fr)
    ctx.show(ob, f - 1, f + 14)
