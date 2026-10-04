"""A three-strand plait of diff threads (B08, the braid), and threads that move along their own length.

The plait. Three threads of radius R plaited flat: strand k's centre sits off the plait's axis by
  x = A sin 2pi(phase + k/3)   (across the plait's face)
  y = B sin 4pi(phase + k/3)   (out of its face: over and under)
so each strand traces a figure of eight in the cross-section as the plait runs on, crossing over one neighbour and
under the other in turn (the left strand over the middle, then the right over the middle). The phase is fixed in the
plait's material: phase = phase0 + b / period, b the plait's material length from its head. A plait that is pulled
along its axis carries its pattern with it; where it is made (the braiding point) the strands dance round each other
in their figures of eight as new plait forms. PLAIT's numbers make neighbours just touch (centres 2 R apart at the
closest; test_braid.py), a plait 2A + 2R wide and 2B + 2R deep.

Threads that move along their length. A thread pulled along a path carries its lay with its material: its twist is a
function of the material coordinate u, not of where the material happens to be. `tubes_along` lays the diff thread's
five tubes (lib/thread.py diff_tubes: the bone plies, the blood and moss strands in their grooves) round a centreline
sampled at material coordinates, in a rotation-minimising frame, so the stripes run along the path at the material's
speed and Cycles blurs them as they go. `fuzz_along` stands seeded fuzz fibres on it, rooted in the material.

numpy only (tested under the tools project).
"""
from __future__ import annotations

import math

import numpy as np

from . import thread

PLAIT = {"A": 2.2, "B": 1.5, "period": 16.0}  # thread radii: strands of radius 1 just touch


def plait_offset(phase, k: int, A: float, B: float) -> np.ndarray:
    """Strand k's centre in the plait's cross-section at `phase` (turns): (..., 2), x across the face, y out of it."""
    t = 2 * np.pi * (np.asarray(phase, float) + k / 3)
    return np.stack([A * np.sin(t), B * np.sin(2 * t)], axis=-1)


class Plait:
    """A three-strand plait of threads of radius R (world units), its pattern fixed in its material.

    b is the plait's material length from its head (world units, along its axis); strand k's offset at b is
    plait_offset(phase0 + b / period, k) in units of R. `arc(k, b)` is the length of strand k's centreline from the head
    to b (it weaves, so it is longer than b by the plait's stretch), and `b_of_arc` inverts it."""

    def __init__(self, R: float, A: float = PLAIT["A"], B: float = PLAIT["B"], period: float = PLAIT["period"],
                 phase0: float = 0.0, samples_per_period: int = 512):
        self.R, self.A, self.B, self.period, self.phase0 = float(R), float(A), float(B), float(period), float(phase0)
        P = self.period * self.R
        # strand 0's arc length over one period of the pattern (the others are it, shifted by a third)
        n = samples_per_period
        b = np.linspace(0.0, P, n + 1)
        dx = np.gradient(self.offset(0, b - self.phase0 * P) * self.R, b, axis=0)  # d(offset)/db, world units
        speed = np.sqrt(1.0 + np.sum(dx * dx, axis=1))
        self._grid = b
        self._S = np.concatenate([[0.0], np.cumsum(0.5 * (speed[1:] + speed[:-1]) * np.diff(b))])
        self.stretch = float(self._S[-1] / P)

    def offset(self, k: int, b) -> np.ndarray:
        """Strand k's offset (x, y) in units of R at material b (world units from the head): (..., 2)."""
        return plait_offset(self.phase0 + np.asarray(b, float) / (self.period * self.R), k, self.A, self.B)

    def _S0(self, x) -> np.ndarray:
        """Strand 0's arc length from material 0 (phase0 = 0) to x, any x: whole periods plus the table."""
        P = self.period * self.R
        x = np.asarray(x, float)
        q = np.floor(x / P)
        return q * self._S[-1] + np.interp(x - q * P, self._grid, self._S)

    def arc(self, k: int, b) -> np.ndarray:
        """The length of strand k's centreline from the head (b = 0) to material b (world units)."""
        P = self.period * self.R
        x0 = (self.phase0 + k / 3) * P
        return self._S0(np.asarray(b, float) + x0) - self._S0(x0)

    def b_of_arc(self, k: int, s, b_max: float) -> np.ndarray:
        """Material b where strand k's arc length from the head is s (inverse of arc), for b in [0, b_max]."""
        bs = np.linspace(0.0, b_max, max(8, int(b_max / (self.R * 0.05)) + 1))
        return np.interp(np.asarray(s, float), self.arc(k, bs), bs)

    def frame_points(self, k: int, b, axial) -> np.ndarray:
        """Strand k's centre in the plait's own frame (x across, y out of the face, z along the axis), world units:
        material b at axial position `axial` (each a number or one per point)."""
        o = self.offset(k, b) * self.R
        z = np.broadcast_to(np.asarray(axial, float), o.shape[:-1])
        return np.concatenate([o, z[..., None]], axis=-1)


def min_gap(plait: Plait, periods: float = 2.0, n: int = 1600) -> float:
    """The closest any two strands' centrelines come (world units), over `periods` of a straight plait."""
    P = plait.period * plait.R
    b = np.linspace(0.0, periods * P, n)
    pts = [plait.frame_points(k, b, -b) for k in range(3)]
    best = math.inf
    for i in range(3):
        for j in range(i + 1, 3):
            d = np.linalg.norm(pts[i][:, None, :] - pts[j][None, ::2, :], axis=-1)
            best = min(best, float(d.min()))
    return best


# ------------------------------------------------------------------------------------------ threads along their length

def frames_along(X: np.ndarray, n0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rotation-minimising frames (T, N, B) along a polyline X (m, 3), the normal starting as n0 (made square to the
    first tangent; any square vector if n0 lies along it)."""
    X = np.asarray(X, float)
    t0 = X[1] - X[0]
    t0 = t0 / max(np.linalg.norm(t0), 1e-12)
    n0 = np.asarray(n0, float)
    if abs(float(t0 @ n0)) > 0.99 * max(np.linalg.norm(n0), 1e-12):
        n0 = np.array([0.0, 1.0, 0.0]) if abs(t0[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    return thread.rmf(X, n0)


def tubes_along(X, u, radius: float, n0, preset: dict = thread.DIFF_THREAD, *, strand_scale: float | None = None):
    """The diff thread's five tubes round a centreline X (m, 3) whose points sit at material coordinates u (m,):
    [(tube (thread.diff_tubes), points (m, 3), tube radius)], bone plies first. Each tube winds at its offset and phase
    plus the lay's turns over u (thread.diff_twist), so the twist belongs to the material: a thread pulled along its path
    carries its stripes with it. The frame is rotation-minimising along X from n0 at X[0]. With u the arc length from
    X[0] this is thread.diff_thread_paths' own layout (test_braid.py)."""
    X = np.asarray(X, float)
    u = np.asarray(u, float)
    twist = thread.diff_twist(radius, preset)
    _, N, B = frames_along(X, n0)
    out = []
    for tube in thread.diff_tubes(preset["strand_scale"] if strand_scale is None else strand_scale):
        th = (2 * np.pi * (twist * u + tube["phase"]))[:, None]
        out.append((tube, X + tube["d"] * radius * (np.cos(th) * N + np.sin(th) * B), tube["r"] * radius))
    return out


class FuzzTable:
    """Seeded fuzz fibres for a thread of material length U and radius R: each rooted at material u and an angle round
    the thread, standing off it at a lift, leaning along it, `pts` points long."""

    def __init__(self, U: float, R: float, per_R: float = 1.6, seed: int = 1, pts: int = 4,
                 length: tuple[float, float] = (0.35, 1.3), u_min: float = 0.0):
        rng = np.random.default_rng(seed)
        n = max(1, int(per_R * (U - u_min) / R))
        self.R, self.pts = float(R), int(pts)
        self.u = rng.uniform(u_min, U, n)
        self.phi = rng.uniform(0, 2 * np.pi, n)
        self.len = R * np.exp(rng.uniform(np.log(length[0]), np.log(length[1]), n))
        self.lift = rng.uniform(0.25, 0.85, n)
        self.lean = rng.uniform(-0.9, 0.9, n)
        self.curl = rng.normal(0.0, 0.25, n)
        self.radius = R * rng.uniform(0.016, 0.03, n)
        self.n = n


def fuzz_along(table: FuzzTable, X, u, T, N, B) -> tuple[np.ndarray, np.ndarray]:
    """The table's fibres on a thread whose centreline X (m, 3) sits at material u (m, increasing) with frames T, N, B:
    (points (n, pts, 3), radii (n, pts)). A fibre's root rides its material; one whose material is not on the thread
    (outside u's range) collapses to a point at the nearest end with radius 0."""
    u = np.asarray(u, float)
    order = np.argsort(u)
    us = u[order]
    inside = (table.u >= us[0]) & (table.u <= us[-1])
    idx = np.clip(np.searchsorted(us, table.u), 1, len(us) - 1)
    i0, i1 = order[idx - 1], order[idx]
    f = np.clip((table.u - us[idx - 1]) / np.maximum(us[idx] - us[idx - 1], 1e-12), 0, 1)[:, None]
    P = X[i0] * (1 - f) + X[i1] * f
    t = T[i0] * (1 - f) + T[i1] * f
    n = N[i0] * (1 - f) + N[i1] * f
    b = B[i0] * (1 - f) + B[i1] * f
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    out = np.cos(table.phi)[:, None] * n + np.sin(table.phi)[:, None] * b
    root = P + out * table.R * 0.92
    d = out * table.lift[:, None] + t * table.lean[:, None]
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    side = np.cross(d, out)
    side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-12)
    k = np.linspace(0.0, 1.0, table.pts)[None, :, None]
    L = table.len[:, None, None]
    pts = root[:, None, :] + d[:, None, :] * L * k + side[:, None, :] * (table.curl[:, None, None] * L) * k ** 2
    rad = table.radius[:, None] * np.linspace(1.0, 0.45, table.pts)[None, :]
    rad = np.where(inside[:, None], rad, 0.0)
    pts = np.where(inside[:, None, None], pts, P[:, None, :])
    return pts, rad


# ------------------------------------------------------------------------------------------ paths

def polyline_arc(P) -> np.ndarray:
    """Cumulative arc length along a polyline (m, 3), from 0."""
    P = np.asarray(P, float)
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])


def at_arc(P, s_cum, s) -> np.ndarray:
    """Points at arc lengths s along a polyline P with cumulative arc s_cum; past either end, straight on along the end
    segment (so material beyond a path's start waits on its extension)."""
    P = np.asarray(P, float)
    s = np.asarray(s, float)
    out = np.column_stack([np.interp(s, s_cum, P[:, j]) for j in range(3)])
    lo, hi = s < s_cum[0], s > s_cum[-1]
    if lo.any():
        d = P[1] - P[0]
        d /= max(np.linalg.norm(d), 1e-12)
        out[lo] = P[0] + d * (s[lo] - s_cum[0])[:, None]
    if hi.any():
        d = P[-1] - P[-2]
        d /= max(np.linalg.norm(d), 1e-12)
        out[hi] = P[-1] + d * (s[hi] - s_cum[-1])[:, None]
    return out


def round_corner(X: np.ndarray, s: np.ndarray, s_corner: float, r: float) -> np.ndarray:
    """X (m, 3) sampled at arc lengths s, with its corner at s_corner rounded: the points within r of it (by s) moved
    onto the quadratic Bezier from the point r before it, through the corner as control point, to the point r after."""
    X = np.array(X, float)
    s = np.asarray(s, float)
    if r <= 0:
        return X
    order = np.argsort(s)
    ss, XX = s[order], X[order]
    a = at_arc(XX, ss, np.array([s_corner - r]))[0]
    c = at_arc(XX, ss, np.array([s_corner]))[0]
    e = at_arc(XX, ss, np.array([s_corner + r]))[0]
    m = (s > s_corner - r) & (s < s_corner + r)
    w = ((s[m] - (s_corner - r)) / (2 * r))[:, None]
    X[m] = (1 - w) ** 2 * a + 2 * (1 - w) * w * c + w ** 2 * e
    return X
