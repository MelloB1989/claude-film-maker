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
ROLL_CARRY = 0.15  # deg / frame: the least roll speed a rolling zoom-through enters and leaves with (sign kept)
ENTRY = 0.02  # |d ln s| / frame a zoom-through is entered with (at least), in the window's zoom direction
EXIT = 0.02  # |d ln s| / frame a zoom-through landing leaves with (at least), still in the window's direction


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
    return cl.cover(st)


def focus_of(T, which, ctx=None):
    """Zoom focus at the cut: explicit p.focus_a/b, else the shot's track at the cut, else the EDL focus, else centre."""
    p = T.get("p", {})
    f = p.get(f"focus_{which}")
    if not f and ctx is not None and T[which]:
        f = ctx.track(T[which]["id"], T["f"] - (1 if which == "a" else 0))
    f = f or (T[which] or {}).get("focus") or [960, 540]
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
    """theta(t) from 0 at w0 to total at w1: an exponential ease into the cut (x`gA` per frame) and a mirrored one out
    of it (speed / `gB` per frame, a long tail), equal angular speed on both sides of the cut f, zero speed at both
    window ends; `over` adds a soft overshoot bump (fraction of total) that settles by w1."""

    def __init__(self, total, w0, f, w1, gA=1.6, gB=1.25, over=0.0):
        self.total, self.w0, self.f, self.w1 = total, w0, f, w1
        self.pre, self.post = float(f - w0), float(w1 - f)
        self.kA = max(0.5, math.log(gA) * self.pre)
        self.kB = max(0.5, math.log(gB) * self.post)
        a = cl.expo_in_d(1.0, self.kA) / self.pre
        b = cl.expo_in_d(1.0, self.kB) / self.post
        self.tc = total * b / (a + b)
        self.over = over
        self.o = over

    def __call__(self, t):
        if t <= self.w0:
            return 0.0
        if t >= self.w1:
            return self.total
        if t <= self.f:
            return self.tc * cl.expo_in((t - self.w0) / self.pre, self.kA)
        u = (t - self.f) / self.post
        th = self.total - (self.total - self.tc) * cl.expo_in(1 - u, self.kB)
        return th + self.over * self.total * 2 * u * math.sin(math.pi * u) ** 2


def window_blend(A, B, w0, w1, t):
    """The card-space state during a whip/cube: A's drift extrapolated, crossfaded (smootherstep, C1) into B's."""
    u = (t - w0) / float(w1 - w0)
    w = cl.smootherstep(u)
    h = 1e-3
    dw = (cl.smootherstep(u + h) - cl.smootherstep(u - h)) / (2 * h) / float(w1 - w0)
    return cl.blend_state(A.at(t - w0), B.at(t - w1), w, dw)


# ======================================================================================================================
def zt_sign(T):
    """+1 for a push (zoom in through the cut), -1 for a pull (zoom out through the cut). The zoom sign is KEPT across the
    cut (REFS: 22-23 of ~24 cuts). A legacy EDL without a mode is a push."""
    return -1 if T["p"].get("mode") == "pull" else 1


def bounds(T, ctx):
    typ = T["type"]
    p = T.get("p", {})
    out = {}
    sg = zt_sign(T) if typ == "zt" else 1
    if T.get("a"):
        A = ctx.entry_state(T)
        adjacent = any(c["w1"] == T["w0"] and c["id"] != T["id"] for c in ctx.E["cuts"])
        if typ in ("zt", "slam") and not adjacent and prev_hold(T, ctx) >= REVERSAL_MIN:
            # enter the zoom already moving the window's way (a hold of >= 6 f turns round if it has to)
            A = A.with_(ds=max(A.ds, ENTRY) if sg > 0 else min(A.ds, -ENTRY))
        R = float(p.get("roll", 0.0) or 0.0)
        if typ == "zt" and R and not adjacent and prev_hold(T, ctx) >= REVERSAL_MIN:
            A = A.with_(dr=math.copysign(max(abs(A.dr), ROLL_CARRY), R))  # roll keeps its sign into the window
        A = ctx.settle_entry(T, A, fixed_rate=typ in ("zt", "slam"))
        if typ in ("zt", "slam") and not adjacent:
            # a true exponential attack (speed x G_MAX per frame at most) needs a minimum entry speed: the hold
            # accelerates into it (REFS: the acceleration starts 3-5 f before the cut, whatever the window says)
            TA = T["f"] - 0.5 - T["w0"]
            peak = float(p.get("peak", (2.6 if typ == "slam" else 3.0) if sg > 0 else 0.45))
            for _ in range(3):
                need = attack_r0(abs(math.log(peak) - math.log(A.s)), TA, G_MAX)
                if abs(A.ds) >= need or A.ds * sg < 0:
                    break
                A = ctx.settle_entry(T, A.with_(ds=sg * need), fixed_rate=True)
        out["A"] = A
    if T.get("b"):
        B = ctx.exit_state(T)
        if typ == "zt":
            land = float(p.get("land", 1.05 if sg > 0 else 2.4))
            settle = float(p.get("settle", B.s))
            # B keeps the window's zoom sign from `land` to `settle` (push: settle above land; pull: below)
            settle = max(settle, land * 1.15) if sg > 0 else min(settle, land / 1.3)
            B = B.with_(s=max(settle, cl.min_scale(B.cx, B.cy, B.r, 0.01)))
            if next_hold(T, ctx) >= REVERSAL_MIN:
                B = B.with_(ds=max(B.ds, EXIT) if sg > 0 else min(B.ds, -EXIT))
                R = float(p.get("roll", 0.0) or 0.0)
                if R:
                    B = B.with_(dr=math.copysign(max(abs(B.dr), ROLL_CARRY), R))  # ... and out of it
            if sg > 0:
                # a push lands on its focus and keeps pushing towards it
                fb = focus_of(T, "b", ctx)
                cx, cy = cl.clamp_center(B.s, B.cx + 0.7 * (fb[0] - B.cx), B.cy + 0.7 * (fb[1] - B.cy), B.r, 0.01)
                B = B.with_(cx=cx, cy=cy)
        elif typ in ("whip", "cube") and "A" in out and next_hold(T, ctx) >= REVERSAL_MIN:
            # a turn carries the zoom direction it entered with into B's landing (the hold after turns round if needed)
            B = B.with_(ds=math.copysign(max(abs(B.ds), 0.012), out["A"].ds))
        elif typ == "slam":
            # B slams in from below 1x (the mirror tiles smear past) and stops at `kick` x, still creeping in
            B = B.with_(s=max(float(p.get("kick", 1.35)), cl.min_scale(B.cx, B.cy, B.r, 0.01)), ds=max(B.ds, 0.012))
        out["B"] = B
    return out


def build(T, ctx):
    {"open": build_open, "zt": build_zt, "whip": build_turn, "cube": build_turn, "flip": build_flip,
     "slam": build_slam}[T["type"]](T, ctx)


REVERSAL_MIN = 6  # frames a hold needs to turn its zoom round (REFS: 6-10 f)


def next_hold(T, ctx):
    for c in ctx.E["cuts"]:
        if T.get("b") and c.get("a") == T["b"]["id"]:
            return c["w0"] - T["w1"]
    return 99


def prev_hold(T, ctx):
    for c in ctx.E["cuts"]:
        if T.get("a") and c.get("b") == T["a"]["id"]:
            return T["w0"] - c["w1"]
    return 99


# ---- zt: zoom-through ---------------------------------------------------------------------------------------------------
ATTACK = 1.5  # A's zoom speed grows x1.5 per frame into the cut (REFS gate: x1.35-1.7 over the last 4 f)
DECAY_RANGE = (1.12, 1.4)  # B's speed falls x1/1.12 .. x1/1.6 per frame (REFS gate: x1.15-1.27 with a >= 8 f tail)
DECAY = 1.22  # B's default speed decay per frame (REFS k 0.80-0.88 -> x1.14-1.25)
DROP_T = 1.8  # A's speed one frame before the cut / B's one frame after, the target (A's peak gives way first)
DROP_MAX = 2.3  # max ratio of A's speed one frame before the teleport to B's one frame after (REFS: median <= 2.3)
RACK_PX = 26.0  # B's rack defocus at the cut (blur circle, px at 1920): legible by +2, sharp by +4/+5
RACK_F = 5.0


G_MAX = 1.75  # fastest attack growth per frame (REFS gate: x1.35-1.7 median over the last 4 f)
G_MIN = 1.2


def attack_r0(delta, TA, g):
    """Entry speed r0 of a pure exponential attack r(tau) = r0 g^tau that covers `delta` (ln s) in TA frames."""
    return delta * math.log(g) / max(1e-9, g ** TA - 1)


def attack_g(delta, TA, r0):
    """Growth g of the exponential attack from entry speed r0 that covers delta in TA frames."""
    lo, hi = 1.0001, 8.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if r0 * (mid ** TA - 1) / math.log(mid) < delta:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def zt_curves(T, ctx, A, B, peak, land, R, sign=1, attack=ATTACK, decay=None):
    """The zoom-through state functions: (stateA(t) for t < t_h, stateB(t) for t > t_h, info).

    The zoom keeps its sign through the cut. A accelerates (expo-in, x`attack` per frame) from its hold drift to `peak` x
    at the teleport (push: ~3x into its focus; pull: ~0.45x, the mirror-tiled picture around the card shows); B starts
    at `land` x on its focus moving the same way and decelerates (mirrored expo) to its exit state (the EDL `settle`).
    B's ease is solved so B's speed one frame after the teleport is A's speed one frame before it / DROP, within the
    allowed decay range. Roll is split so its rate is the same on both sides of the cut."""
    w0, w1, f = T["w0"], T["w1"], T["f"]
    th = f - 0.5
    TA, TB = th - w0, w1 - th
    fa, fb = focus_of(T, "a", ctx), focus_of(T, "b", ctx)
    decay = decay or DECAY
    LA0, Lp = math.log(A.s), math.log(peak)
    if (Lp - LA0) * sign < 0.2:
        Lp = LA0 + 0.2 * sign
    LB1, Ll = math.log(B.s), math.log(land)

    def vB1(k):
        return abs(ramp_out(Ll, LB1, B.ds, TB, k, max(0.0, TB - 1.0))[1])
    r0 = A.ds * sign
    expo = r0 >= 0.003  # entering already moving the window's way: a pure exponential attack
    if expo:
        g = max(1.05, attack_g(abs(Lp - LA0), TA, r0))
        # speed carries through the cut: A's speed one frame before the teleport is at most DROP_T x B's speed one
        # frame after it with B's natural decay (the EDL peak is pulled in if needed; a push lands slowly by nature)
        V = DROP_T * vB1(math.log(decay) * TB)
        if TA > 1.0 and r0 * g ** (TA - 1) > V:
            g2 = min(g, max(G_MIN, (V / r0) ** (1.0 / (TA - 1))))  # only ever pulls the peak in
            if g2 < g:
                g = g2
                Lp = LA0 + sign * r0 * (g ** TA - 1) / math.log(g)
        kA = max(0.3, math.log(g) * TA)
        vA1 = r0 * g ** max(0.0, TA - 1.0)
    else:
        g = attack
        kA = max(0.3, math.log(attack) * TA)
        vA1 = abs(ramp_in(LA0, A.ds, Lp, TA, kA, max(0.0, TA - 1.0))[1])

    def lnsA(tau):
        if expo:
            return LA0 + sign * r0 * (g ** tau - 1) / math.log(g), sign * r0 * g ** tau
        return ramp_in(LA0, A.ds, Lp, TA, kA, tau)
    # B decays at x DECAY per frame (REFS k 0.80-0.88), steepened (up to x DECAY_RANGE[1]) only as far as needed to keep
    # the speed drop across the cut under DROP_MAX
    lo, hi = math.log(decay) * TB, math.log(DECAY_RANGE[1]) * TB
    want = vA1 / DROP_MAX
    if vB1(hi) <= want:
        kB = hi
    elif vB1(lo) >= want:
        kB = lo
    else:
        for _ in range(50):
            mid = (lo + hi) / 2
            if vB1(mid) < want:
                lo = mid
            else:
                hi = mid
        kB = (lo + hi) / 2
    kAr, kBr = kA * 1.2, min(60.0, kB * 1.2)  # the roll eases a little harder than the zoom
    XA, XB = roll_split(A.dr, B.dr, R, TA, TB, kAr, kBr)
    rA_end = A.r + A.dr * TA + XA
    rB_start = B.r - B.dr * TB - XB
    tiled = sign < 0  # a pull shows the mirror-tiled picture beyond the card: no coverage floor on A's side

    def stA(t):
        tau = t - w0
        L, dL = lnsA(tau)
        cx, dcx = ramp_in(A.cx, A.dcx, fa[0], TA, kA, tau)
        cy, dcy = ramp_in(A.cy, A.dcy, fa[1], TA, kA, tau)
        r, dr = ramp_in(A.r, A.dr, rA_end, TA, kAr, tau)
        st = cl.State(math.exp(L), cx, cy, r, dL, dcx, dcy, dr)
        return cl.cover(st, strength=cl.smoothstep((st.s - 0.95) / 0.5)) if tiled else fin(st)

    def stB(t):
        tp = w1 - t
        L, dL = ramp_out(Ll, LB1, B.ds, TB, kB, tp)
        cx, dcx = ramp_out(fb[0], B.cx, B.dcx, TB, kB, tp)
        cy, dcy = ramp_out(fb[1], B.cy, B.dcy, TB, kB, tp)
        r, dr = ramp_out(rB_start, B.r, B.dr, TB, kBr, tp)
        # the landing's first frames may show the mirror tiles behind the smear; the edge guard fades in over 6 f
        roff = abs(r - (B.r - B.dr * tp))  # roll still to unwind: big rolls show the mirror tiles inside the smear
        k = min(cl.smootherstep((t - th) / 6.0), 1 - cl.smoothstep((roff - 1.0) / 6.0))
        return cl.cover(cl.State(math.exp(L), cx, cy, r, dL, dcx, dcy, dr), strength=k)
    RA = lnsA(TA)[1]
    RB = ramp_out(Ll, LB1, B.ds, TB, kB, TB)[1]
    return stA, stB, dict(kA=kA, kB=kB, RA=RA, RB=RB, vA1=vA1, vB1=vB1(kB), peak=math.exp(Lp),
                          decay=math.exp(kB / TB), g=g if expo else None)


def rack(ctx, th, stB, t1, px=RACK_PX, frames=RACK_F):
    """Rack defocus on B's first frames: real camera DOF, focus pulled in front of the card, fading over `frames`."""
    t = th + ctx.EPS
    last = None
    while t < min(t1, th + frames + 1.0):
        st = stB(t)
        d = cl.FILL_DIST / st.s  # camera-to-card distance (the card faces the camera)
        b = px * (1 - cl.smoothstep((t - th) / frames))
        ctx.key_dof(t, cl.focus_for_blur(d, b), 1.4)
        last = (t, d)
        t = round(t + 0.25, 4) if t > th + 0.1 else th + 0.25
    if last:
        ctx.key_dof(last[0] + 0.25, last[1], cl.FSTOP_SHARP)


def build_zt(T, ctx):
    p = T["p"]
    A, B = ctx.bounds[T["id"]]["A"], ctx.bounds[T["id"]]["B"]
    sign = zt_sign(T)
    stA, stB, info = zt_curves(T, ctx, A, B, float(p.get("peak", 3.0 if sign > 0 else 0.45)),
                               float(p.get("land", 1.05 if sign > 0 else 2.4)), float(p.get("roll", 0.0)), sign,
                               float(p.get("attack", ATTACK)))
    th = T["f"] - 0.5
    ctx.teleport(th)
    ca, cb = ctx.card(T["a"]["id"]), ctx.card(T["b"]["id"])

    def fn(t):
        return ctx.pose(ca, stA(t)) if t < th else ctx.pose(cb, stB(t))
    ctx.key_path(fn, T["w0"], T["w1"], 0.25)
    if p.get("rack", True):
        rack(ctx, th, stB, T["w1"], float(p.get("rack_px", RACK_PX)))
    ctx.log(f"  zt {T['id']} {'push' if sign > 0 else 'pull'}: A {A.s:.2f}->{info['peak']:.2f}x  B {p.get('land')}->{B.s:.2f}x  "
            f"rate at cut {info['RA']:+.3f}|{info['RB']:+.3f}  1f either side {info['vA1']:.3f}|{info['vB1']:.3f} d ln s/f  "
            f"A growth x{(info['g'] or 0):.2f}/f  B decay x{info['decay']:.2f}/f")


# ---- open: out of black onto S01 ------------------------------------------------------------------------------------------
def build_open(T, ctx):
    p = T["p"]
    B = ctx.bounds[T["id"]]["B"]
    sid = T["b"]["id"]
    w0, w1 = T["w0"], T["w1"]
    TB = float(w1 - w0)
    s0 = float(p.get("from_scale", 1.9))
    fb = focus_of(T, "b", ctx)
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
    mat = cards.card_material(f"m_open_{sid}", plate, sweep=True, extension="MIRROR",
                              tile_tint=ctx.palette(ctx.act_of(sid))["leak"])
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
        turn = Turn(ang, w0, f, w1, float(p.get("attack", 2.3)), float(p.get("decay", 2.0)), over=0.02)
    else:
        # cube: dir = the way the cube turns; the camera orbits the other way round the box centre
        cube_sgn = {"L": 1, "R": -1, "U": 1, "D": -1}[d]
        axis = (0, 1, 0) if d in "LR" else (1, 0, 0)
        ang = math.radians(90.0) * cube_sgn
        hd = (cl.CARD_W if d in "LR" else cl.CARD_H) / 2
        P = o + Vector((0, 0, -hd))
        turn = Turn(ang, w0, f, w1, 1.6, 1.3, over=0.0)
    FB = rot_about(P, axis, ang) @ FA
    ca = ctx.make_card(T["a"]["id"], f"{typ}_{T['id']}_A", FA, frames=vis)
    cb = ctx.make_card(T["b"]["id"], f"{typ}_{T['id']}_B", FB, frames=vis)
    ctx.env(o, act, frames=vis)
    pb = math.log(float(p.get("pullback", 1.75))) if typ == "cube" else 0.0

    if typ == "whip":
        whip_streaks(T, ctx, P, axis, ang, d, pal, vis)
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
    ctx.log(f"  {typ} {T['id']} dir {d}: turn {math.degrees(ang):+.0f} deg, peak at f{f}, overshoot {turn.over:.2f}")


def whip_streaks(T, ctx, P, axis, ang, d, pal, vis, n=26):
    """Thin act-coloured light streaks in the gap between A and B (beyond the cards), lying along the whip direction:
    under motion blur they become the light lines of the smear; the pictures themselves carry the rest."""
    import random
    rnd = random.Random(T["f"])
    m1 = cards.emission_material(f"whip_{T['id']}_streakA", pal["leak"], 6.0)
    m2 = cards.emission_material(f"whip_{T['id']}_streakB", pal["rim"], 5.0)
    me1 = cards.card_mesh(f"whip_{T['id']}_streak1", 1, 1, 1.0, 1.0)
    me1.materials.append(m1)
    me2 = cards.card_mesh(f"whip_{T['id']}_streak2", 1, 1, 1.0, 1.0)
    me2.materials.append(m2)
    horiz = d in "LR"
    for i in range(n):
        fr = rnd.uniform(0.2, 0.8)
        dist = rnd.uniform(2.4, 7.0)
        off = rnd.uniform(-0.45, 0.45) * dist
        ln = rnd.uniform(0.15, 0.9) * dist * 0.3
        th = 0.0035 * dist * rnd.uniform(0.6, 1.6)
        local = Vector((0.0, off, -dist)) if horiz else Vector((off, 0.0, -dist))
        ob = bpy.data.objects.new(f"whip_{T['id']}_streak{i}", me1 if i % 3 else me2)
        R = rot_about(P, axis, ang * fr)
        ob.matrix_world = R @ Matrix.Translation(P + local) @ Matrix.Diagonal((ln, th, 1.0, 1.0) if horiz else
                                                                               (th, ln, 1.0, 1.0))
        ctx.coll("light").objects.link(ob)
        cards.no_shadow(ob)
        ctx.show(ob, *vis)


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
    """Superhero landing: A pushes in (exponential attack); B slams in from below 1x (the mirror tiles smear past) at the
    same speed and stops hard at `kick` x (B decays x1.4 per frame), the depth-displaced card gives the 3D-photo
    parallax, the shot's shake@F hits, a dust shockwave ring expands."""
    p = T["p"]
    A, B = ctx.bounds[T["id"]]["A"], ctx.bounds[T["id"]]["B"]
    stA, stB, info = zt_curves(T, ctx, A, B, float(p.get("peak", 2.6)), float(p.get("start", 0.72)), 0.0, 1,
                               decay=float(p.get("decay", 1.4)))
    th = T["f"] - 0.5
    ctx.teleport(th)
    ca, cb = ctx.card(T["a"]["id"]), ctx.card(T["b"]["id"])

    def fn(t):
        return ctx.pose(ca, stA(t)) if t < th else ctx.pose(cb, stB(t))
    ctx.key_path(fn, T["w0"], T["w1"], 0.25)
    rack(ctx, th, stB, T["w1"], 18.0, 4.0)
    shockwave(T, ctx, cb, T["f"])
    ctx.log(f"  slam {T['id']}: A {A.s:.2f}->{info['peak']:.2f}x  B {p.get('start', 0.72)}->{B.s:.2f}x  "
            f"1f either side {info['vA1']:.3f}|{info['vB1']:.3f}  B decay x{info['decay']:.2f}/f")


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
