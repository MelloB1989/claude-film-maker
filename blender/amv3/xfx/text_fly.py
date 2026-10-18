"""Timeless v3 transition `text_fly`: the camera flies through the 3D title into the next shot (owner: text3d).

C10 (AMAZING, exit "dive", 327-345, cut 336) and C25 (SPIDER-MAN, exit "through", 648-662, cut 656).

REFS.md recipe (text_fly): attack expo-in through the letters, +59 %/f on the last A frame, B keeps the zoom sign
(push +8.6 %/f -> 0, k 0.85), 4 smear frames, B rack-defocused for its first frames. Gate: acceleration x1.35-1.7/f
over the last 4 A frames, deceleration x1.15-1.27/f with a long tail, cut peak >= 160 px/f.

Channels (each a velocity profile, so velocity is continuous at w0 and w1 and the screen direction carries the cut):
- zoom (ln s): A accelerates geometrically (x `attack` per frame) from the hold drift to `peak_ds`; B keeps pushing,
  from `land_ds` decaying x `decay` per frame to B's hold drift. B lands at `land`; B's exit scale follows from it.
- pan (card point at frame centre): A drifts onto the title (`aim`); B starts with the same screen speed (clamped so
  the frame stays on the card) and settles on B's centre.
- roll: accelerates through the cut and keeps its sign in B (decay x0.75/f, the roll-whip recipe).
- pitch (dive, A side only): the camera tips down into the letters over the last frames (at ~3x zoom there is margin;
  at B's landing scale there is none, so B carries the dive as upward picture motion through the pan).
The letters' own flight (they leave their places behind the card plane, rush at the lens, one passes ~4 cm from it,
two more in B's set through the teleport copy) is text3d.Title.exit_fly_through; it runs after the camera is keyed.
"""
import math

from mathutils import Quaternion

from camlib import State

PRESET = {
    "dive": dict(sA=1.22, dsA=0.02, attack=1.5, peak_ds=0.45, land=1.06, land_ds=0.10, dsB=0.015, decay=0.83,
                 aim=(905, 430), roll_peak=2.4, drB=0.3, roll_decay=0.75, pitch_peak=-4.0, pitch_lead=4.5,
                 rack_px=24, rack_f=7),
    "through": dict(sA=1.30, dsA=0.02, attack=1.5, peak_ds=0.45, land=1.06, land_ds=0.10, dsB=0.015, decay=0.83,
                    aim=(760, 620), roll_peak=3.0, drB=0.3, roll_decay=0.75, pitch_peak=0.0, pitch_lead=0.0,
                    rack_px=26, rack_f=8),
}


def _preset(T):
    return PRESET.get(T["p"].get("exit", "through"), PRESET["through"])


def _focus(shot):
    f = shot.get("focus")
    return (float(f[0]), float(f[1])) if f else (960.0, 540.0)


def safe_c(s, cx, cy, roll_deg=0.0, margin=1.03):
    """clamp the card point at frame centre so the frame (rotated by roll) stays inside the card at scale s"""
    r = math.radians(abs(roll_deg))
    hw = (960.0 * math.cos(r) + 540.0 * math.sin(r)) / s * margin
    hh = (540.0 * math.cos(r) + 960.0 * math.sin(r)) / s * margin
    lo_x, hi_x = min(hw, 960.0), max(1920.0 - hw, 960.0)
    lo_y, hi_y = min(hh, 540.0), max(1080.0 - hh, 540.0)
    return min(max(cx, lo_x), hi_x), min(max(cy, lo_y), hi_y)


# ---- velocity profiles ------------------------------------------------------------------------------------------------
def attack_disp(vA, vp, T, g, tau):
    """A side: v(tau) = vA + (vp - vA) (g^(tau - T) - g^-T) / (1 - g^-T), from vA at 0 to vp at T, x g per frame near
    the end. Returns the displacement over [0, tau]."""
    if T <= 0:
        return 0.0
    lg, gT = math.log(g), g ** (-T)
    return vA * tau + (vp - vA) / (1.0 - gT) * ((g ** (tau - T) - gT) / lg - gT * tau)


def decay_rem(vq, vB, T, k, tau):
    """B side: v(tau) = vB + (vq - vB) (k^tau - k^T) / (1 - k^T), from vq at 0 to vB at T (x k per frame).
    Returns the displacement still to come over [tau, T]."""
    kT, lk = k ** T, -math.log(k)
    return vB * (T - tau) + (vq - vB) / (1.0 - kT) * ((k ** tau - kT) / lk - kT * (T - tau))


class Chan:
    """One channel: A side [w0, th] (optionally flat until `start`, then the geometric attack), B side [th, w1]."""

    def __init__(self, w0, th, w1, xA, vA, vp, g, xB, vB, vq, k, start=None, cubic=False):
        self.w0, self.th, self.w1 = w0, th, w1
        self.s0 = w0 if start is None else max(w0, start)
        self.xA, self.vA, self.vp, self.g = xA, vA, vp, g
        self.xB, self.vB, self.vq, self.k = xB, vB, vq, k
        self.cubic = cubic

    def a(self, t):
        if self.cubic:  # v = vp u^2 (gentle drift onto a point: displacement vp T / 3)
            Ta = self.th - self.w0
            return self.xA + self.vp * Ta / 3.0 * min(1.0, max(0.0, (t - self.w0) / Ta)) ** 3
        pre = self.vA * (min(t, self.s0) - self.w0)
        return self.xA + pre + attack_disp(self.vA, self.vp, self.th - self.s0, self.g, max(0.0, t - self.s0))

    def b(self, t):
        return self.xB - decay_rem(self.vq, self.vB, self.w1 - self.th, self.k, t - self.th)


def plan(T, ctx=None):
    P = _preset(T)
    w0, w1, cut = float(T["w0"]), float(T["w1"]), float(T["f"])
    th = cut - 0.5
    Ta, Tb = th - w0, w1 - th
    lB = math.log(P["land"]) + decay_rem(P["land_ds"], P["dsB"], Tb, P["decay"], 0.0)
    ax, ay = safe_c(P["sA"], *_focus(T["a"]))
    zoom = Chan(w0, th, w1, math.log(P["sA"]), P["dsA"], P["peak_ds"], P["attack"], lB, P["dsB"], P["land_ds"],
                P["decay"])
    s_peak = math.exp(zoom.a(th))
    vps = [3.0 * (P["aim"][i] - a0) / Ta for i, a0 in enumerate((ax, ay))]
    F = decay_rem(1.0, 0.0, Tb, P["decay"], 0.0)       # displacement of a unit-speed decay over B
    bc = (960.0, 540.0)
    want = [bc[i] - vps[i] * s_peak / P["land"] * F for i in range(2)]
    start = safe_c(P["land"], want[0], want[1], 0.0)
    cx, cy = (Chan(w0, th, w1, (ax, ay)[i], 0.0, vps[i], 1.0, bc[i], 0.0, (bc[i] - start[i]) / F, P["decay"],
                   cubic=True) for i in range(2))
    # roll: B starts level at the landing (no margin there) and keeps turning the same way; it ends at rB
    rB = decay_rem(P["roll_peak"], P["drB"], Tb, P["roll_decay"], 0.0)
    roll = Chan(w0, th, w1, 0.0, 0.0, P["roll_peak"], 1.6, rB, P["drB"], P["roll_peak"], P["roll_decay"])
    pitch = None
    if P["pitch_peak"]:
        pitch = Chan(w0, th, w1, 0.0, 0.0, P["pitch_peak"], 1.6, 0.0, 0.0, 0.0, 0.8, start=th - P["pitch_lead"])
    return dict(zoom=zoom, cx=cx, cy=cy, roll=roll, pitch=pitch, th=th, s_peak=s_peak, s_land=P["land"],
                sB=math.exp(lB), A=(ax, ay), rB=rB)


def bounds(T, ctx):
    P = _preset(T)
    pl = plan(T, ctx)
    ax, ay = pl["A"]
    A = State(P["sA"], ax, ay, 0.0, ds=P["dsA"], dcx=0.0, dcy=0.0, dr=0.0)
    B = State(pl["sB"], 960.0, 540.0, pl["rB"], ds=P["dsB"], dcx=0.0, dcy=0.0, dr=P["drB"])
    return {"A": A, "B": B}


def state_at(pl, t):
    side = "a" if t < pl["th"] else "b"
    g = lambda p: getattr(p, side)(t)
    eps = 0.01
    gd = lambda p: (getattr(p, side)(t + eps) - getattr(p, side)(t - eps)) / (2 * eps)
    st = State(math.exp(g(pl["zoom"])), g(pl["cx"]), g(pl["cy"]), g(pl["roll"]),
               ds=gd(pl["zoom"]), dcx=gd(pl["cx"]), dcy=gd(pl["cy"]), dr=gd(pl["roll"]))
    ph = pl["pitch"].a(t) if (pl["pitch"] and side == "a") else 0.0
    return side, st, ph


def build(T, ctx):
    P = _preset(T)
    pl = plan(T, ctx)
    ca, cb = ctx.card(T["a"]["id"]), ctx.card(T["b"]["id"])
    w0, w1, th = float(T["w0"]), float(T["w1"]), pl["th"]
    ctx.log(f"text_fly {T['id']}: A x{P['sA']:.2f} -> peak x{pl['s_peak']:.2f} (+{P['peak_ds'] * 100:.0f} %/f) at {th}; "
            f"B lands x{pl['s_land']:.2f} pushing +{P['land_ds'] * 100:.0f} %/f, x{P['decay']}/f -> x{pl['sB']:.2f}")
    ctx.teleport(th)

    def fn(t):
        side, st, ph = state_at(pl, t)
        loc, rot = ctx.pose(ca if side == "a" else cb, st)
        if ph:
            rot = rot @ Quaternion((1.0, 0.0, 0.0), math.radians(ph))
        return loc, rot

    ctx.key_path(fn, w0, w1, 0.5)
    try:
        import flow
        flow.rack(ctx, th, lambda t: state_at(pl, t)[1], w1, px=P["rack_px"], frames=P["rack_f"])
    except Exception as e:  # noqa: BLE001  (a core without rack / key_dof)
        ctx.log(f"text_fly {T['id']}: no rack defocus ({e})")
