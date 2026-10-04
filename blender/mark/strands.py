"""The weave's four threads: each lays one line of the mark's hash and changes colour where it passes under. bpy-free.

The mark (geometry.py) is a woven hash. Each of its lines is one thread here, drawn on from its start terminal to its
end, and every colour change happens under a crossing, so it never shows (the diff happens inside the weave):

  stem   bone               from the stem's foot, up: under the crossbar (B), over the moss bar (A)
  gbar   moss -> bone        from the moss bar's leaf, left: over the blood vertical (C), under the stem (A), then the
                             G's bar, the bowl and the top bar to the G's leaf
  vloop  blood -> moss       from the vertical's cap, down: under the moss bar (C), over the crossbar (D), round the
                             bottom left, along the bottom, under the hook (E)
  xhook  moss -> blood       from the hook's foot, up: over the loop (E), round the top right, left: under the loop (D),
                             then the blood crossbar over the stem (B) to its leaf: the last pass, the lock

Space: mark px (MU) in the mark's frame, X right, Y away from the viewer, Z up, the mark's centre (image 128, 128) at
the origin; the ribbons lie in Y = 0 and "over" is toward the viewer (-Y). A thread arrives along its approach, a long
arc out of the dark that runs into its start terminal on the band's own line.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import geometry as G
from .sweep import Rings, rmf

# the ribbon's section (MU): half its thickness (the band is 0.15 of its width deep) and its edges' radius
H = 1.85
RC = 1.6
# the weave: how far over and under a crossing a ribbon sits (its middle, MU), and how much of it runs level either
# side (the other ribbon's half-width plus this)
LIFT = 1.85
LEVEL = 0.3
# the thread: its radius (MU) on the approach, its lay (MU a turn), and where it flattens into the ribbon (MU before
# the band starts)
ROPE_R = 7.5
LAY = 40.0
MORPH = 26.0
STEP_BAND = 0.5
STEP_ROPE = 1.5

STRANDS = {
    "stem": {"pieces": [("stem", True)], "colours": ["bone"]},
    "gbar": {"pieces": [("bar", True), ("g", True)], "colours": ["moss", "bone"]},
    "vloop": {"pieces": [("vert", False), ("loop", False)], "colours": ["blood", "moss"]},
    "xhook": {"pieces": [("hook", True), ("cross", True)], "colours": ["moss", "blood"]},
}
ORDER = ["stem", "gbar", "vloop", "xhook"]

# The approaches (MU, mark space), far to near. Each ends on the band's line a little before its start terminal, so
# the thread runs straight into the ribbon.
APPROACH = {
    # from the far left, low and in front, along under the mark, curling up into the stem's foot
    "stem": [(-1050, -160, -60), (-560, -130, -195), (-230, -70, -232), (-40, -15, -225)],
    # from the far left behind it, over the top, down the right and back left into the moss bar's leaf
    "gbar": [(-1000, 260, 120), (-470, 210, 205), (60, 150, 222), (360, 70, 160), (400, 20, 30)],
    # from the far right, low and in front, up the right side and over, down into the blood vertical's cap
    "vloop": [(1050, -330, -210), (640, -230, -120), (470, -130, 110), (290, -50, 240), (95, -5, 250)],
    # from the far right behind it, along the bottom, curling up into the hook's foot
    "xhook": [(1080, 150, -150), (600, 90, -235), (250, 40, -250), (120, 8, -225)],
}
LEAD_IN = 70.0  # MU of straight run into the start terminal


@dataclass
class Strand:
    name: str
    rings: Rings
    blood: np.ndarray  # (n,) colour weights per ring
    moss: np.ndarray
    zoff: np.ndarray  # (n,) the weave's lift (MU, toward the viewer)
    s_band: float  # where the ribbon starts: the tail's rest
    length: float  # the head's rest
    crossings: list = field(default_factory=list)  # (name, s, over)
    changes: list = field(default_factory=list)  # s of each hidden colour change


def to_mark(p2):
    """Image px (x right, y down) to mark space (X, Z) about the centre."""
    p2 = np.asarray(p2, float)
    return np.column_stack([p2[:, 0] - G.SIZE / 2, G.SIZE / 2 - p2[:, 1]])


def _piece_run(pc: G.Piece, reverse: bool, step: float):
    """A piece sampled for a strand: points (image px), offsets per side, and its ends' terminal cuts per side, in the
    strand's direction (a reversed piece swaps its ends and its sides)."""
    s = pc.samples(step)
    p, t = pc.at(s)
    offa, offb = pc.hw(s, "a"), pc.hw(s, "b")
    ra, rb = pc.sides(s)
    L = pc.length
    # the cut per side, split by end: the start's within its corner radii of s = 0, the end's of s = L
    near0 = s <= L / 2
    cut_a, cut_b = offa - ra, offb - rb
    run = {"p": p, "offa": offa, "offb": offb,
           "c0a": np.where(near0, cut_a, 0.0), "c0b": np.where(near0, cut_b, 0.0),
           "c1a": np.where(~near0, cut_a, 0.0), "c1b": np.where(~near0, cut_b, 0.0)}
    if reverse:
        run = {"p": p[::-1], "offa": offb[::-1], "offb": offa[::-1],
               "c0a": run["c1b"][::-1], "c0b": run["c1a"][::-1], "c1a": run["c0b"][::-1], "c1b": run["c0a"][::-1]}
    return run


MIN_GAP = 0.03  # MU: samples closer than this to the one before are one ring (coincident rings make bad normals)


def _spaced(p: np.ndarray, gap: float) -> np.ndarray:
    """Indices of points at least `gap` along from the previous one kept (the first and the last always kept)."""
    d = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    keep, last = [0], 0.0
    for i in range(1, len(p) - 1):
        if d[i] - last >= gap:
            keep.append(i)
            last = d[i]
    if d[-1] - last < gap and len(keep) > 1:
        keep.pop()
    keep.append(len(p) - 1)
    return np.array(keep)


def _hermite(p0, t0, p1, t1, n):
    u = np.linspace(0, 1, n)[:, None]
    h00, h10, h01, h11 = 2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u, -2 * u**3 + 3 * u**2, u**3 - u**2
    d = np.linalg.norm(p1 - p0)
    return h00 * p0 + h10 * t0 * d + h01 * p1 + h11 * t1 * d


def mark_path(name: str, p: dict | None = None, step: float = STEP_BAND, joint: float = 9.0):
    """A strand's run through the mark: image-px points and per-point offsets, terminal cuts and colour index, with its
    pieces joined under their crossing (a smooth Hermite joint `joint` MU either side, hidden there)."""
    p = G.load_params() if p is None else p
    pcs = G.pieces(p)
    spec = STRANDS[name]
    runs = [_piece_run(pcs[n], rev, step) for n, rev in spec["pieces"]]
    out = {k: [] for k in ("p", "offa", "offb", "c0a", "c0b", "c1a", "c1b", "col")}
    for i, run in enumerate(runs):
        seg = {k: v.copy() for k, v in run.items()}
        sl = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(seg["p"], axis=0), axis=1))])
        keep = np.ones(len(sl), bool)
        if i > 0:
            keep &= sl >= joint
        if i < len(runs) - 1:
            keep &= sl <= sl[-1] - joint
        for k in seg:
            seg[k] = seg[k][keep]
        if i > 0:  # the joint from the previous run's end to this run's start
            a, b = out["p"][-1][-1], seg["p"][0]
            ta = out["p"][-1][-1] - out["p"][-1][-2]
            tb = seg["p"][1] - seg["p"][0]
            n = max(3, math.ceil(np.linalg.norm(b - a) / step))
            jp = _hermite(a, ta / np.linalg.norm(ta), b, tb / np.linalg.norm(tb), n + 1)[1:-1]
            f = np.linspace(0, 1, n + 1)[1:-1]
            out["p"].append(jp)
            for k in ("offa", "offb"):
                out[k].append(out[k][-1][-1] * (1 - f) + seg[k][0] * f)
            for k in ("c0a", "c0b", "c1a", "c1b"):
                out[k].append(np.zeros(len(f)))
            out["col"].append(np.where(f < 0.5, i - 1, i).astype(float))
        for k in ("p", "offa", "offb", "c0a", "c0b", "c1a", "c1b"):
            out[k].append(seg[k])
        out["col"].append(np.full(len(seg["p"]), float(i)))
    res = {k: np.concatenate(v) for k, v in out.items()}
    keep = _spaced(res["p"], MIN_GAP)
    res = {k: v[keep] for k, v in res.items()}
    # only the strand's own ends keep their terminal cuts (a joined piece's hidden end is not an end any more)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(res["p"], axis=0), axis=1))])
    first, last = s < s[-1] / 2, s >= s[-1] / 2
    res["c0a"], res["c0b"] = np.where(first, res["c0a"], 0.0), np.where(first, res["c0b"], 0.0)
    res["c1a"], res["c1b"] = np.where(last, res["c1a"], 0.0), np.where(last, res["c1b"], 0.0)
    res["s"] = s
    return res


def crossings_of(name: str, path: dict, p: dict | None = None):
    """(crossing, s along the strand's mark path, over?) for each crossing the strand passes, in order."""
    p = G.load_params() if p is None else p
    pts = G.crossing_points(p)
    mine = {n: rev for n, rev in STRANDS[name]["pieces"]}
    out = []
    for cname, cr in G.CROSSINGS.items():
        over = cr["over"] in mine
        under = any(u in mine for u in cr["under"])
        if not (over or under):
            continue
        d = np.linalg.norm(path["p"] - np.asarray(pts[cname]), axis=1)
        i = int(np.argmin(d))
        if d[i] > 3.0:
            continue
        out.append((cname, float(path["s"][i]), over))
    return sorted(out, key=lambda x: x[1])


def lift(s: np.ndarray, crossings, level_half: dict, length: float) -> np.ndarray:
    """The weave's lift along a strand: level at +-LIFT across each crossing (its half-width `level_half[name]`), easing
    (smoothstep) between neighbours and to 0 at a free end; an end under a crossing stays down."""
    keys = []
    for cname, sc, over in crossings:
        w = level_half[cname]
        z = LIFT if over else -LIFT
        keys += [(sc - w, z), (sc + w, z)]
    if not keys:
        return np.zeros_like(s)
    if keys[0][0] > 0:
        keys.insert(0, (0.0, 0.0))
    if keys[-1][0] < length:
        keys.append((length, 0.0))
    ks, kz = np.array([k[0] for k in keys]), np.array([k[1] for k in keys])
    z = np.interp(s, ks, kz)
    for i in range(len(ks) - 1):  # smoothstep between keys instead of straight
        a, b = ks[i], ks[i + 1]
        m = (s > a) & (s < b)
        if b > a and m.any():
            u = (s[m] - a) / (b - a)
            z[m] = kz[i] + (kz[i + 1] - kz[i]) * u * u * (3 - 2 * u)
    return z


def _catmull(points, step):
    """A centripetal Catmull-Rom through 3D points, sampled about `step` apart."""
    P = np.asarray(points, float)
    ext = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = [P[:1]]
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = ext[i:i + 4]

        def kn(a, b):
            return max(np.linalg.norm(b - a) ** 0.5, 1e-9)

        t0, t1 = 0.0, kn(p0, p1)
        t2, t3 = t1 + kn(p1, p2), t1 + kn(p1, p2) + kn(p2, p3)
        n = max(2, math.ceil(np.linalg.norm(p2 - p1) / step))
        t = np.linspace(t1, t2, n + 1)[1:, None]
        a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
        a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
        a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
        b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
        b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
        out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    return np.vstack(out)


def _resample(c, step):
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
    n = max(2, math.ceil(s[-1] / step))
    at = np.linspace(0, s[-1], n + 1)
    return np.column_stack([np.interp(at, s, c[:, k]) for k in range(3)])


def build(name: str, p: dict | None = None, approach=None) -> Strand:
    """One thread: its approach and its run through the mark, as rings for the sweep."""
    p = G.load_params() if p is None else p
    mp = mark_path(name, p)
    cr = crossings_of(name, mp, p)
    pcs = G.pieces(p)
    # the other ribbon's half-width where it crosses (the level run either side of the crossing), plus a little
    xp = G.crossing_points(p)

    def hw_at(piece, q):
        pc = pcs[piece]
        i = int(np.argmin(np.linalg.norm(pc.path - np.asarray(q), axis=1)))
        return float(max(pc.hw(pc.s[i], "a"), pc.hw(pc.s[i], "b")))

    level_half = {}
    for cname, sc, over in cr:
        c = G.CROSSINGS[cname]
        others = c["under"] if over else (c["over"],)
        level_half[cname] = max(hw_at(o, xp[cname]) for o in others) + LEVEL
    Lm = float(mp["s"][-1])
    z = lift(mp["s"], cr, level_half, Lm)

    # the run through the mark in 3D: X, Z from the picture, Y the lift (toward the viewer is -Y)
    xz = to_mark(mp["p"])
    band = np.column_stack([xz[:, 0], -z, xz[:, 1]])
    t2 = np.gradient(mp["p"], axis=0)
    t2 /= np.linalg.norm(t2, axis=1, keepdims=True)
    n3 = np.column_stack([-t2[:, 1], np.zeros(len(t2)), -t2[:, 0]])  # side A in the plane: image (-ty, tx)

    # the approach: control points, then a straight lead-in along the band's first direction
    d0 = band[1] - band[0]
    d0 /= np.linalg.norm(d0)
    pts = [np.asarray(q, float) for q in (approach or APPROACH[name])]
    pts += [band[0] - d0 * LEAD_IN, band[0] - d0 * STEP_BAND]
    ap = _resample(_catmull(pts, STEP_ROPE / 2), STEP_ROPE)  # ends half a step before the band's first point
    c = np.vstack([ap, band])
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
    na = len(ap)
    s_band = float(s[na])

    T = np.gradient(c, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    # N: in the band's plane on the run (square to T), carried back along the approach with no twist of its own
    Nb = n3 - T[na:] * np.sum(n3 * T[na:], axis=1, keepdims=True)
    Nb /= np.linalg.norm(Nb, axis=1, keepdims=True)
    Ta, Na = rmf(np.vstack([ap, band[:1]]), Nb[0])
    N = np.vstack([Na[:-1], Nb])

    n = len(c)
    offa = np.concatenate([np.full(na, mp["offa"][0]), mp["offa"]])
    offb = np.concatenate([np.full(na, mp["offb"][0]), mp["offb"]])
    zeros = np.zeros(na)
    red0a, red0b = np.concatenate([zeros, mp["c0a"]]), np.concatenate([zeros, mp["c0b"]])
    red1a, red1b = np.concatenate([zeros, mp["c1a"]]), np.concatenate([zeros, mp["c1b"]])
    u = np.clip((s - (s_band - MORPH)) / MORPH, 0, 1)
    m = u * u * (3 - 2 * u)
    rings = Rings(s=s, c=c, T=T, N=N, offa=offa, offb=offb, red0a=red0a, red0b=red0b, red1a=red1a, red1b=red1b,
                  m=m, radius=np.full(n, ROPE_R), phase=2 * math.pi * s / LAY)

    # colour: the run's pieces in order, changing at the middle of each joint (under its crossing)
    cols = STRANDS[name]["colours"]
    ci = np.concatenate([np.zeros(na), mp["col"]]).astype(int)
    blood = np.array([cols[i] == "blood" for i in ci], float)
    moss = np.array([cols[i] == "moss" for i in ci], float)
    changes = [float(s[na + i]) for i in range(1, len(mp["col"])) if mp["col"][i] != mp["col"][i - 1]]
    zo = np.concatenate([zeros, z])
    return Strand(name, rings, blood, moss, zo, s_band, float(s[-1]),
                  crossings=[(cn, s_band + sc, ov) for cn, sc, ov in cr], changes=changes)


def all_strands(p: dict | None = None) -> dict[str, Strand]:
    p = G.load_params() if p is None else p
    return {n: build(n, p) for n in ORDER}
