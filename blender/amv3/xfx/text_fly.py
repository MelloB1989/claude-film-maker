"""Timeless v3 transition `text_fly`: the camera flies through the 3D title into the next shot (owner: text3d).

C10 (AMAZING, exit "dive", 327-345, cut 336) and C25 (SPIDER-MAN, exit "through", 648-662, cut 656).

The camera move is a zoom-through with one more axis (pitch, for the dive). Each channel follows a velocity
profile: from the entry rate at w0, v accelerates as u^k to the peak rate at the half frame before the cut (expo-in).
After the teleport into B's home set, v decays from the matched peak as (1-u)^k to the exit rate at w1 (expo-out).
So velocity is continuous at w0, through the cut and at w1. Channels: ln s (zoom; A pushes in, B lands zoomed in and
pulls out, as in the zt convention), the card point at frame centre (screen speed matched across the cut), roll
(keeps its sign through the cut) and pitch (dive: A tips down into the letters, B arrives looking above S11's card
and keeps tipping down onto it, so the freefall comes up from below).

The letters' own flight (they leave their places behind the card plane, rush at the lens, one passes ~4 cm from it,
and continue into B's set) is in text3d.Title.exit_fly_through. It runs after this camera is keyed and aims at it.
"""
import math

from mathutils import Quaternion

from camlib import State

K = 2.0  # profile exponent (u^K): 2 = strong ease-in, peaks at the cut

# per exit kind: A/B states (s, cx, cy, roll, rates), peak zoom rate, B landing scale, roll and pitch peaks (deg/f)
PRESET = {
    "dive": dict(sA=1.22, dsA=0.012, peak_ds=0.27, land=2.1, sB=1.18, dsB=0.006, drB=-0.12,
                 aim=(925, 430), roll_peak=2.6, pitch_peak=-4.5, pitch_lead=4.5),
    "through": dict(sA=1.30, dsA=0.015, peak_ds=0.30, land=2.3, sB=1.25, dsB=-0.012, drB=0.0,
                    aim=(905, 640), roll_peak=3.2, pitch_peak=0.0, pitch_lead=0.0),
}


def _preset(T):
    return PRESET.get(T["p"].get("exit", "through"), PRESET["through"])


def _focus(shot):
    f = shot.get("focus")
    return (float(f[0]), float(f[1])) if f else (960.0, 540.0)


def bounds(T, ctx):
    P = _preset(T)
    ax, ay = _focus(T["a"])
    bx, by = 960.0, 540.0
    A = State(P["sA"], ax, ay, 0.0, ds=P["dsA"], dcx=0.0, dcy=0.0, dr=0.0)
    B = State(P["sB"], bx, by, 0.0, ds=P["dsB"], dcx=0.0, dcy=0.0, dr=P["drB"])
    return {"A": A, "B": B}


class Prof:
    """one channel: A side [w0, th] from (xA, vA) accelerating to vp; B side [th, w1] decaying from vq to (xB, vB)."""

    def __init__(self, w0, th, w1, xA, vA, vp, xB, vB, vq, start=None):
        self.w0, self.th, self.w1 = w0, th, w1
        self.s0 = w0 if start is None else max(w0, start)     # A side starts accelerating here (pitch lead)
        self.xA, self.vA, self.vp, self.xB, self.vB, self.vq = xA, vA, vp, xB, vB, vq

    def a(self, t):
        Ta = self.th - self.s0
        tau = max(0.0, t - self.s0)
        u = min(1.0, tau / Ta) if Ta > 0 else 1.0
        x = self.xA + self.vA * (t - self.w0)
        return x + (self.vp - self.vA) * Ta * u ** (K + 1) / (K + 1)

    def b(self, t):
        Tb = self.w1 - self.th
        u = (t - self.th) / Tb
        rem = self.vB * (self.w1 - t) + (self.vq - self.vB) * Tb * (1.0 - u) ** (K + 1) / (K + 1)
        return self.xB - rem

    def a_end(self):
        return self.a(self.th)

    def b_start(self):
        return self.b(self.th)


def plan(T, ctx):
    P = _preset(T)
    bd = bounds(T, ctx)
    A, B = bd["A"], bd["B"]
    w0, w1, cut = float(T["w0"]), float(T["w1"]), float(T["f"])
    th = cut - 0.5
    Ta, Tb = th - w0, w1 - th
    # zoom (ln s): A pushes to the peak rate; B starts at `land` and must reach ln sB: solve its start rate
    lA, lB, lland = math.log(A.s), math.log(B.s), math.log(P["land"])
    vq_s = B.ds + (K + 1) * (lB - lland - B.ds * Tb) / Tb
    zoom = Prof(w0, th, w1, lA, A.ds, P["peak_ds"], lB, B.ds, vq_s)
    s_peak = math.exp(zoom.a_end())
    # card point at frame centre: A drifts to the aim point (rate solved), B's screen speed matched (px/f * s)
    ch = []
    for i, (a0, b0) in enumerate(((A.cx, B.cx), (A.cy, B.cy))):
        d = P["aim"][i] - a0
        vp = (K + 1) * d / Ta
        vq = vp * s_peak / P["land"]
        ch.append(Prof(w0, th, w1, a0, 0.0, vp, b0, 0.0, vq))
    roll = Prof(w0, th, w1, A.r, A.dr, P["roll_peak"], B.r, B.dr, P["roll_peak"])
    pitch = Prof(w0, th, w1, 0.0, 0.0, P["pitch_peak"], 0.0, 0.0, P["pitch_peak"], start=th - P["pitch_lead"]) \
        if P["pitch_peak"] else None
    return dict(zoom=zoom, cx=ch[0], cy=ch[1], roll=roll, pitch=pitch, th=th, s_peak=s_peak, vq_s=vq_s)


def state_at(pl, t):
    side = "a" if t < pl["th"] else "b"
    g = lambda p: getattr(p, side)(t)
    eps = 0.01
    gd = lambda p: (getattr(p, side)(t + eps) - getattr(p, side)(t - eps)) / (2 * eps)
    st = State(math.exp(g(pl["zoom"])), g(pl["cx"]), g(pl["cy"]), g(pl["roll"]),
               ds=gd(pl["zoom"]), dcx=gd(pl["cx"]), dcy=gd(pl["cy"]), dr=gd(pl["roll"]))
    ph = g(pl["pitch"]) if pl["pitch"] else 0.0
    return side, st, ph


def build(T, ctx):
    pl = plan(T, ctx)
    ca, cb = ctx.card(T["a"]["id"]), ctx.card(T["b"]["id"])
    w0, w1, th = float(T["w0"]), float(T["w1"]), pl["th"]
    ctx.log(f"text_fly {T['id']}: peak x{pl['s_peak']:.2f} at {th}, B lands x{_preset(T)['land']} "
            f"(zoom rate {pl['zoom'].vp:+.3f} -> {pl['vq_s']:+.3f}/f)")
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
