"""Timeless v2: the camera moves of every SHOT layer, one key per comp frame. Pure math (stdlib only).

Per shot the layer transform is: anchor = the focus point F (clip pixels, default the frame centre C), and per frame
  scale    s = drift(f) * zoom(f)                        (percent)
  rotation r                                             (degrees, + = clockwise)
  position P = C + (F - C) * (1 - q) + (tx, ty)          (where the anchor sits on screen)
q = how far the zoom has carried F to the frame centre (0 at 100 %, 1 at ZC), so a push on an eye ends with the eye
in the middle of the frame. Every transition is a pair of curves that meet at the cut frame b, and both are fastest
there (A accelerates out, B decelerates in: the cut sits on the fastest, blurriest frame). B's entry is an exponential
settle whose start speed is solved to EQUAL A's exit speed at the cut (`settle`), so the velocity is continuous.
"""
from __future__ import annotations

import math

from .remap import smoothstep

W, H = 1920, 1080
C = (W / 2, H / 2)
ZC = 2.6                       # the zoom at which the focus point is centred
SPECIAL = ("rift", "drop_portal", "panel_slam")   # the SPECIAL lib owns these: drift only, hard cut
ZOOMS = ("zoom_in", "pull_out", "zoom_out")
WHIPS = {"whip_l": (-1, 0), "whip_r": (1, 0), "whip_u": (0, -1), "whip_d": (0, 1),
         "whip_left": (-1, 0), "whip_right": (1, 0), "whip_up": (0, -1), "whip_down": (0, 1)}
SPINS = {"spin_cw": 1, "spin_ccw": -1}
EXIT_N = {"zoom_in": 5, "zoom_out": 5, "whip": 4, "spin": 5}
ENTRY_N = {"pull_out": 9, "zoom_in": 9, "zoom_out": 8, "whip": 8, "spin": 9, "impact": 6, "open_lightsweep": 12}
LAMBDA = 3.0                   # default exponential settle rate (per entry length)


def ease_in(x):
    """0..1 -> 0..1, accelerating (quadratic), extended linearly past 1 with the end speed (the handle)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0 + 2.0 * (x - 1)
    return x * x


def settle_curve(G, n, v0):
    """Value that starts at G with speed -v0 (units/frame) and settles to exactly 0 at x = n (exponential shape).
    v0 is clipped up to 1.05 * G/n (a pure line is the slowest settle). Returns f(x), extended linearly for x < 0."""
    v0 = max(v0, 1.05 * G / n)
    lo, hi = 1e-6, 200.0 / n            # solve v0 = G*lam / (1 - exp(-lam n))
    for _ in range(80):
        lam = 0.5 * (lo + hi)
        v = G * lam / (1 - math.exp(-lam * n))
        if v < v0:
            lo = lam
        else:
            hi = lam
    lam = 0.5 * (lo + hi)
    d = 1 - math.exp(-lam * n)

    def f(x):
        if x <= 0:
            return G + v0 * (-x)
        if x >= n:
            return 0.0
        return G * (math.exp(-lam * x) - math.exp(-lam * n)) / d

    f.v0 = G * lam / d
    return f


def drift_curve(d0, d1, n):
    """Eased slow push/pull d0 -> d1 (percent) over n frames; the ease never reaches zero speed (the camera never stops)."""
    def f(i):
        x = i / n
        e = 0.5 * x + 0.5 * smoothstep(0, 1, x) if 0 <= x <= 1 else x
        return d0 + (d1 - d0) * e
    return f


def _kind(x):
    if x in WHIPS:
        return "whip"
    if x in SPINS:
        return "spin"
    return x


class Move:
    """One channel set at frame offset i relative to the cut: (log-zoom g, rotation deg, tx, ty px). Zero by default."""

    def __init__(self, g=None, rot=None, tx=None, ty=None, tile=False):
        self.g, self.rot, self.tx, self.ty, self.tile = g, rot, tx, ty, tile

    def __call__(self, u):
        z = lambda f: f(u) if f else 0.0
        return z(self.g), z(self.rot), z(self.tx), z(self.ty)


def exit_move(xout, n_shot, focus_zoom=ZC):
    """A's exit curves as functions of frames-before-the-end u = f - b (u in [-N, 0], handles u > 0).
    Returns (Move, exit speeds {'g','rot','t'} at the cut)."""
    k = _kind(xout)
    if xout in ("cut", "impact", "light_sweep", "open_lightsweep") or xout in SPECIAL or k not in EXIT_N:
        return Move(), dict(g=0, rot=0, t=0)
    N = EXIT_N[k]
    prog = lambda u: ease_in((u + N) / N)
    dprog = 2.0 / N                                   # end speed of x^2 over N frames, per frame
    if k == "zoom_in":
        G = math.log(2.6)
        return Move(g=lambda u: G * prog(u), tile=False), dict(g=G * dprog, rot=0, t=0)
    if k == "zoom_out":
        G = math.log(0.55)
        return Move(g=lambda u: G * prog(u), tile=True), dict(g=abs(G) * dprog, rot=0, t=0)
    if k == "whip":
        dx, dy = WHIPS[xout]
        D = 1.3 * (W if dx else H)
        return (Move(tx=(lambda u: dx * D * prog(u)) if dx else None, ty=(lambda u: dy * D * prog(u)) if dy else None,
                     tile=True), dict(g=0, rot=0, t=D * dprog))
    if k == "spin":
        s = SPINS[xout]
        G = math.log(1.5)
        return (Move(g=lambda u: G * prog(u), rot=lambda u: s * 50 * prog(u), tile=True),
                dict(g=G * dprog, rot=50 * dprog, t=0))


def entry_move(xin, prev_xout, speeds):
    """B's entry curves as functions of frames-after-the-cut u = f - a (u >= 0; u < 0 = handle, continued linearly).
    `speeds` = A's exit speeds at the cut (the entry settles from the same speed)."""
    k = _kind(xin)
    if k not in ENTRY_N or xin in SPECIAL or xin in ("open_lightsweep",):
        return Move()
    N = ENTRY_N[k]
    if k == "pull_out":
        G = math.log(2.6)
        f = settle_curve(G, N, speeds["g"] or G / N * 3)
        return Move(g=f)
    if k == "zoom_in":                                # continue the push from 100 %, decelerating
        v0 = speeds["g"] or 0.15
        Dg = 0.5 * v0 * N * 0.64
        f = settle_curve(Dg, N, v0)
        return Move(g=lambda u: Dg - f(u) if u >= 0 else v0 * u)
    if k == "zoom_out":                               # starts at 160 %, settles to 100 % (continues the shrink)
        G = math.log(1.6)
        return Move(g=settle_curve(G, N, speeds["g"] or G / N * 3), tile=True)
    if k == "whip":
        dx, dy = WHIPS[xin]
        v0 = speeds["t"] or 0.65 * (W if dx else H)
        D = (W if dx else H)
        # enter from the opposite side of the exit: moving the same way as A, so B's offset starts on the +dir side
        f = settle_curve(1.9 * D, N, v0)
        return Move(tx=(lambda u: -dx * f(u)) if dx else None, ty=(lambda u: -dy * f(u)) if dy else None, tile=True)
    if k == "spin":
        s = SPINS[xin]
        G = math.log(1.5)
        fg = settle_curve(G, N, speeds["g"] or G / N * 3)
        fr = settle_curve(50.0, N, speeds["rot"] or 50 / N * 3)
        return Move(g=fg, rot=lambda u: -s * fr(u), tile=True)
    if k == "impact":                                 # punch 115 -> 100 % over 6 f, expo-out
        G = math.log(1.15)
        return Move(g=settle_curve(G, N, G / N * 4))
    return Move()


def shot_keys(sh, prev, nxt, hin, hout):
    """Per-frame keys for one shot layer: list of dicts (frame, pos [x,y], scale %, rot deg, tile bool, opacity %)
    for comp frames a-hin .. b+hout-1."""
    a, b = sh["a"], sh["b"]
    n = b - a
    d0, d1 = sh["drift"]
    drift = drift_curve(d0, d1, n)
    F = sh["focus"] or list(C)
    ex, sp = exit_move(sh["xout"], n)
    # A's exit speed for the NEXT shot is computed when that shot builds its entry: pass via `speeds` of this shot's exit
    en = entry_move(sh["xin"], prev["xout"] if prev else "cut", exit_speeds(prev) if prev else dict(g=0, rot=0, t=0))
    out = []
    for f in range(a - hin, b + hout):
        eg, er, etx, ety = ex(f - b) if f > b - EXIT_N.get(_kind(sh["xout"]), 0) - 1 else (0, 0, 0, 0)
        ng, nr, ntx, nty = en(f - a) if f < a + ENTRY_N.get(_kind(sh["xin"]), 0) + 1 else (0, 0, 0, 0)
        g = eg + ng
        s = drift(f - a) * math.exp(g)
        q = min(1.0, max(0.0, math.log(max(s, 1e-6) / 100.0) / math.log(ZC)))
        px = C[0] + (F[0] - C[0]) * (1 - q) + etx + ntx
        py = C[1] + (F[1] - C[1]) * (1 - q) + ety + nty
        op = 100.0
        if sh["xin"] == "open_lightsweep":
            op = 100.0 * smoothstep(0, 1, (f - a) / ENTRY_N["open_lightsweep"])
        out.append(dict(f=f, pos=[round(px, 3), round(py, 3)], scale=round(s, 4), rot=round(er + nr, 4),
                        opacity=op, F=F))
    for k in out:
        k["need"] = tile_need(k)
    for i, k in enumerate(out):      # pad with the neighbours: the motion-blur samples reach +-0.4 frame
        nb = [out[j]["need"] for j in (i - 1, i, i + 1) if 0 <= j < len(out)]
        w, h = max(x[0] for x in nb), max(x[1] for x in nb)
        k["tile"] = [round(w), round(h)] if (w > 100.5 or h > 100.5) else None
    for k in out:
        del k["need"], k["F"]
    return out


def tile_need(k):
    """Motion Tile output size (percent of the layer, per axis) that keeps the frame covered: the screen corners mapped
    back into layer space (anchor F, position pos, scale %, rotation), extent measured from the layer centre."""
    r = math.radians(k["rot"])
    c, sn = math.cos(r), math.sin(r)
    sc = k["scale"] / 100.0
    px, py = k["pos"]
    Fx, Fy = k["F"]
    mx = my = 0.0
    for X, Y in ((0, 0), (W, 0), (W, H), (0, H)):
        dx, dy = (X - px), (Y - py)
        lx = (c * dx + sn * dy) / sc + Fx          # inverse rotation (AE rotation is clockwise on screen)
        ly = (-sn * dx + c * dy) / sc + Fy
        mx = max(mx, abs(lx - W / 2))
        my = max(my, abs(ly - H / 2))
    def need(m, size):
        raw = 2 * m / size * 100
        return 100.0 if raw <= 100.5 else raw * 1.06 + 2
    return (need(mx, W), need(my, H))


def exit_speeds(sh):
    return exit_move(sh["xout"], sh["b"] - sh["a"])[1]
