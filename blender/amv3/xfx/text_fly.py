"""Timeless v3 transition `text_fly`: the camera flies through the 3D title into the next shot (owner: text3d).

C10 (AMAZING, exit "dive", 327-345, cut 336) and C25 (SPIDER-MAN, exit "through", 648-662, cut 656).

The camera move is a zoom-through with one more axis (pitch, for the dive). Each channel follows a velocity
profile: from the entry rate at w0, v accelerates as u^k to the peak rate at the half frame before the cut (expo-in).
After the teleport into B's home set, v decays from the matched peak as (1-u)^k to the exit rate at w1 (expo-out).
So velocity is continuous at w0 and at w1, and its magnitude carries through the cut (REFS.md numbers). Channels: ln s
(zoom; A pushes in, B lands zoomed in and pulls out at the same speed, as in the zt convention), the card point at frame centre (screen speed matched across the cut), roll
(keeps its sign through the cut) and pitch (dive: A tips down into the letters, B arrives looking above S11's card
and keeps tipping down onto it, so the freefall comes up from below).

The letters' own flight (they leave their places behind the card plane, rush at the lens, one passes ~4 cm from it,
and continue into B's set) is in text3d.Title.exit_fly_through. It runs after this camera is keyed and aims at it.
"""
import math

from mathutils import Quaternion

from camlib import State

KDECAY = 0.8  # B side: speed x0.8 per frame (REFS: k = 0.75-0.85, 10 % of peak after 7-12 f)

# per exit kind. A: entry scale/rate at w0; attack exponents (u^k: zoom ~doubles per frame over the last 3-4 A frames,
# REFS: +1, +4, +9, +20..30 %/f); peak zoom rate at the cut. B: exit state at w1; B lands at the SAME speed magnitude
# (zoom flips to a pull-out behind the smear, pan/roll/pitch keep their screen direction) and decays x0.8/f.
# aim: card pixel the A camera drifts to (the title); pitch: dive (deg/f peak, lead frames before the cut).
PRESET = {
    "dive": dict(sA=1.22, dsA=0.02, peak_ds=0.27, flip=True, sB=1.18, dsB=0.015, drB=-0.15,
                 aim=(905, 420), roll_peak=2.4, pitch_peak=-4.0, pitch_lead=4.5, k_zoom=7.0, k_pan=3.0, k_roll=4.0,
                 defocus=dict(frames=8, near=0.45, fstop=2.0)),
    "through": dict(sA=1.30, dsA=0.02, peak_ds=0.30, flip=True, sB=1.25, dsB=-0.015, drB=0.0,
                    aim=(760, 620), roll_peak=3.0, pitch_peak=0.0, pitch_lead=0.0, k_zoom=7.0, k_pan=3.0, k_roll=4.0,
                    defocus=dict(frames=7, near=0.45, fstop=2.0)),
}


def _preset(T):
    return PRESET.get(T["p"].get("exit", "through"), PRESET["through"])


def _focus(shot):
    f = shot.get("focus")
    return (float(f[0]), float(f[1])) if f else (960.0, 540.0)


def safe_c(s, cx, cy, roll_deg=0.0, margin=1.04):
    """clamp the card point at frame centre so the frame (rotated by roll) stays inside the card at scale s"""
    r = math.radians(abs(roll_deg))
    hw = (960.0 * math.cos(r) + 540.0 * math.sin(r)) / s * margin
    hh = (540.0 * math.cos(r) + 960.0 * math.sin(r)) / s * margin
    return min(max(cx, hw), 1920.0 - hw), min(max(cy, hh), 1080.0 - hh)


def bounds(T, ctx):
    P = _preset(T)
    ax, ay = safe_c(P["sA"], *_focus(T["a"]))
    A = State(P["sA"], ax, ay, 0.0, ds=P["dsA"], dcx=0.0, dcy=0.0, dr=0.0)
    B = State(P["sB"], 960.0, 540.0, 0.0, ds=P["dsB"], dcx=0.0, dcy=0.0, dr=P["drB"])
    return {"A": A, "B": B}


class Prof:
    """One channel. A side [s0, th]: v = vA + (vp - vA) u^ka (expo-like attack); before s0 (lead) v = vA.
    B side [th, w1]: v = vB + (vq - vB) (k^tau - k^Tb) / (1 - k^Tb): starts at vq, decays ~x k per frame, ends exactly
    at vB, so the hold that follows starts C1."""

    def __init__(self, w0, th, w1, xA, vA, vp, xB, vB, vq, ka=3.0, start=None, k=KDECAY):
        self.w0, self.th, self.w1 = w0, th, w1
        self.s0 = w0 if start is None else max(w0, start)
        self.xA, self.vA, self.vp, self.xB, self.vB, self.vq = xA, vA, vp, xB, vB, vq
        self.ka, self.k = ka, k
        self.kT = k ** (w1 - th)

    def a(self, t):
        Ta = self.th - self.s0
        u = min(1.0, max(0.0, t - self.s0) / Ta) if Ta > 0 else 1.0
        return self.xA + self.vA * (t - self.w0) + (self.vp - self.vA) * Ta * u ** (self.ka + 1) / (self.ka + 1)

    def a_disp(self):
        return self.a(self.th) - self.xA

    def rem(self, t):
        """integral of v from t to w1 (B side)"""
        Tb, tau = self.w1 - self.th, t - self.th
        k, kT = self.k, self.kT
        expo = (k ** tau - kT) / (-math.log(k)) - kT * (Tb - tau)
        return self.vB * (Tb - tau) + (self.vq - self.vB) / (1.0 - kT) * expo

    def b(self, t):
        return self.xB - self.rem(t)


def plan(T, ctx):
    P = _preset(T)
    bd = bounds(T, ctx)
    A, B = bd["A"], bd["B"]
    w0, w1, cut = float(T["w0"]), float(T["w1"]), float(T["f"])
    th = cut - 0.5
    Ta = th - w0
    zq = -P["peak_ds"] if P["flip"] else P["peak_ds"]
    zoom = Prof(w0, th, w1, math.log(A.s), A.ds, P["peak_ds"], math.log(B.s), B.ds, zq, ka=P["k_zoom"])
    s_peak = math.exp(zoom.a(th))
    s_land = math.exp(zoom.b(th))
    ch = []
    for i, (a0, b0) in enumerate(((A.cx, B.cx), (A.cy, B.cy))):
        d = P["aim"][i] - a0
        kk = P["k_pan"]
        vp = (kk + 1) * d / Ta                        # reaches the aim point at the cut with this end rate
        vq = vp * s_peak / s_land                     # same screen speed (px/f on screen = card px/f * s)
        ch.append(Prof(w0, th, w1, a0, 0.0, vp, b0, 0.0, vq, ka=kk))
    roll = Prof(w0, th, w1, A.r, A.dr, P["roll_peak"], B.r, B.dr, P["roll_peak"], ka=P["k_roll"])
    pitch = Prof(w0, th, w1, 0.0, 0.0, P["pitch_peak"], 0.0, 0.0, P["pitch_peak"], ka=2.0,
                 start=th - P["pitch_lead"]) if P["pitch_peak"] else None
    return dict(zoom=zoom, cx=ch[0], cy=ch[1], roll=roll, pitch=pitch, th=th, s_peak=s_peak, s_land=s_land)


def state_at(pl, t):
    side = "a" if t < pl["th"] else "b"
    g = lambda p: getattr(p, side)(t)
    eps = 0.01
    gd = lambda p: (getattr(p, side)(t + eps) - getattr(p, side)(t - eps)) / (2 * eps)
    st = State(math.exp(g(pl["zoom"])), g(pl["cx"]), g(pl["cy"]), g(pl["roll"]),
               ds=gd(pl["zoom"]), dcx=gd(pl["cx"]), dcy=gd(pl["cy"]), dr=gd(pl["roll"]))
    ph = g(pl["pitch"]) if pl["pitch"] else 0.0
    return side, st, ph


def key_defocus(T, ctx, pl):
    """REFS: the first 2-4 B frames are rack-defocused (lens blur), fading over 6-10 f: real camera DOF, focus pulled
    from `near` x the card distance back onto the card. DOF is on only for [cut, cut + frames]."""
    D = _preset(T).get("defocus")
    cam = getattr(ctx, "cam", None)
    if not D or cam is None:
        return
    import camlib
    cd = cam.data
    cut = float(T["f"])
    n = D["frames"]
    cd.dof.aperture_fstop = D["fstop"]
    cd.dof.use_dof = False
    cd.keyframe_insert("dof.use_dof", frame=cut - 1)
    for j in range(n + 1):
        f = cut + j
        _, st, _ = state_at(pl, f)
        dist = camlib.FILL_DIST / st.s
        u = j / float(n)
        e = 1.0 - (1.0 - u) ** 3
        cd.dof.use_dof = j < n
        cd.dof.focus_distance = dist * (D["near"] + (1.0 - D["near"]) * e)
        cd.keyframe_insert("dof.use_dof", frame=f)
        cd.keyframe_insert("dof.focus_distance", frame=f)


def build(T, ctx):
    pl = plan(T, ctx)
    ca, cb = ctx.card(T["a"]["id"]), ctx.card(T["b"]["id"])
    w0, w1, th = float(T["w0"]), float(T["w1"]), pl["th"]
    ctx.log(f"text_fly {T['id']}: peak x{pl['s_peak']:.2f} at {th}, B lands x{pl['s_land']:.2f} "
            f"(zoom rate {pl['zoom'].vp:+.3f} -> {pl['zoom'].vq:+.3f}/f, decay x{KDECAY}/f)")
    ts = []
    t = w0
    while t < w1 - 1e-6:
        if abs(t - th) > 1e-6:
            ts.append(t)
        t += 0.5
    eps = getattr(ctx, "EPS", 0.02)
    ts += [th - eps, th + eps]
    for t in sorted(ts):
        side, st, ph = state_at(pl, t)
        loc, rot = ctx.pose(ca if side == "a" else cb, st)
        if ph:
            rot = rot @ Quaternion((1.0, 0.0, 0.0), math.radians(ph))
        ctx.key_cam(t, loc, rot)
    ctx.teleport(th)
    key_defocus(T, ctx, pl)
