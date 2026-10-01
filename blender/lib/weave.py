"""The loom (B05): plain weave on four warp lanes, the shed, and the weaving clock that puts a pick on every beat.

Coordinates are the loom's own, in units of one length L (a shot scales them to metres): x across the loom, y along the
warps (the woven cloth toward -y, the open warps and the back beam toward +y), z up. The fell, the edge where the newest
weft row is beaten in, is fixed at y = 0, and the cloth is taken up toward -y by one pick on every beat, the way a loom's
cloth beam winds it in: so the fabric grows toward a camera on the cloth side.

  - `layout`: the warp lanes side by side (each a tape of its own), centred on x = 0.
  - `warp_crimp`, `weft_crimp`: the over/under of plain weave. Row r (an integer, in weaving order) lies at y = p (r - n)
    where n is the picks taken up so far, so a point's row coordinate is rho = n + y / p; warp j crosses over row r when
    j + r is even, and the weft of row r passes under it there.
  - `shed_profile`: how far the open warps stand from the cloth's plane beyond the fell (0 at the fell, 1 at the heddles,
    back to 0 at the back beam).
  - `WeaveClock`: from the beats, the picks: pass k flies while the shed is open after beat k - 1 and lands on beat k,
    where its row is beaten in, the cloth is taken up one pick and the shed changes over. Pure functions of t.
  - `ply_offsets`: three plies wound round a centreline that lies in a plane (a warp in the y-z plane, a weft in the x-z
    plane), framed by that plane's normal, without the per-point transport loop a general path needs.

numpy only: tested under the tools project (blender/tests/test_weave.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


# ------------------------------------------------------------------------------------------------------ the lanes

@dataclass(frozen=True)
class Lane:
    """One warp lane (a tier): its name and its warps' x, left to right; `first` is the index of its first warp in the
    loom (warps are numbered left to right across all lanes)."""
    name: str
    xs: tuple
    first: int

    @property
    def x0(self) -> float:
        return float(self.xs[0])

    @property
    def x1(self) -> float:
        return float(self.xs[-1])

    @property
    def centre(self) -> float:
        return 0.5 * (self.x0 + self.x1)

    @property
    def count(self) -> int:
        return len(self.xs)

    def warps(self) -> range:
        """The loom indices of its warps."""
        return range(self.first, self.first + self.count)


def layout(names, counts, pitch: float, gap: float) -> list[Lane]:
    """Lanes side by side, centred on x = 0: lane i has counts[i] warps `pitch` apart, and `gap` more than a pitch lies
    between the last warp of one lane and the first of the next."""
    if len(names) != len(counts) or not names:
        raise ValueError("one warp count per lane")
    xs, x, first = [], 0.0, 0
    for c in counts:
        if c < 1:
            raise ValueError("a lane needs a warp")
        xs.append([x + i * pitch for i in range(c)])
        x += (c - 1) * pitch + pitch + gap
    mid = 0.5 * (xs[0][0] + xs[-1][-1])
    lanes = []
    for name, row in zip(names, xs):
        lanes.append(Lane(name, tuple(v - mid for v in row), first))
        first += len(row)
    return lanes


# ------------------------------------------------------------------------------------------------------ the weave

def warp_crimp(rho, j: int, amp: float):
    """Warp j's height at row coordinate rho (rho = n + y / p): `amp` over row r where j + r is even, under it where it
    is odd, a cosine between the rows."""
    return amp * (-1.0) ** j * np.cos(np.pi * np.asarray(rho, float))


def weft_crimp(c, r: int, amp: float):
    """Row r's weft height at warp coordinate c ((x - lane.x0) / pitch, so c = i at the lane's warp i, whose loom index
    has the parity of i when the lane starts on an even warp): under warp i where i + r is even (that warp is over it),
    over it where odd."""
    return -amp * (-1.0) ** r * np.cos(np.pi * np.asarray(c, float))


def shed_profile(y, heddle: float, beam: float):
    """0..1: how far an open warp stands from the cloth's plane at y beyond the fell: rising from the fell (y = 0) to the
    heddles (1 at y = heddle) with no kink there (a quarter sine), and easing back to the back beam (0 at y = beam,
    a half cosine); 0 on the cloth's side."""
    y = np.asarray(y, float)
    up = np.sin(0.5 * np.pi * np.clip(y / heddle, 0.0, 1.0))
    down = 0.5 + 0.5 * np.cos(np.pi * np.clip((y - heddle) / (beam - heddle), 0.0, 1.0))
    return np.where(y <= 0, 0.0, np.where(y <= heddle, up, down))


# ------------------------------------------------------------------------------------------------------ easing

def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def out_cubic(x):
    x = np.clip(x, 0.0, 1.0)
    return 1 - (1 - x) ** 3


def in_out_cubic(x):
    x = np.clip(np.asarray(x, float), 0.0, 1.0)
    return np.where(x < 0.5, 4 * x ** 3, 1 - (-2 * x + 2) ** 3 / 2)


# ------------------------------------------------------------------------------------------------------ the clock

@dataclass(frozen=True)
class Pass:
    """One pick: pass k flies from `depart` to `land` (beat k), laying row k + 1 from side `start` (-1 left, +1 right)
    to the other side; the row is beaten in on `land`."""
    k: int
    depart: float
    land: float
    start: int

    @property
    def row(self) -> int:
        return self.k + 1


class WeaveClock:
    """The weaving, beat by beat (song seconds).

    `beats` are the beats a pass lands on, in order; `before` is the beat before the first (row 0 was beaten in on it).
    Around each landing the reed's work runs over [land - lead, land + settle]: the row in flight is beaten in and the
    cloth is taken up one pick. The shed changes over round every beat (`before` too): over `shed` seconds centred
    `cross` after the beat, the warps that were up go down and those that were down come up, crossing (the shed closed)
    at the centre. Pass k departs once the shed is open again, `open_` after beat k - 1, and lands on beat k. Pass 0
    flies left to right, and the passes alternate."""

    def __init__(self, beats, before: float, *, lead: float = 0.03, settle: float = 0.12, shed: float = 0.2,
                 cross: float = 0.05, open_: float = 0.17):
        self.beats = [float(b) for b in beats]
        if not self.beats or any(b1 <= b0 for b0, b1 in zip([before] + self.beats, self.beats)):
            raise ValueError("beats must follow `before` and each other")
        if open_ < cross + shed / 2:
            raise ValueError("a pass must not depart before the shed is open")
        self.before = float(before)
        self.lead, self.settle, self.shed_dur, self.cross, self.open = lead, settle, shed, cross, open_
        prev = [self.before] + self.beats[:-1]
        self.passes = [Pass(k, p + open_, b, -1 if k % 2 == 0 else 1) for k, (p, b) in enumerate(zip(prev, self.beats))]

    # the reed: beat-up and take-up
    def beat_up(self, t: float, land: float) -> float:
        """0..1: a row beaten in on `land`, from the race to the fell (a fast out-cubic over the reed's stroke)."""
        return float(out_cubic((t - (land - self.lead)) / (self.lead + self.settle)))

    def taken(self, t: float) -> float:
        """Picks taken up by t (continuous): k + 1 once pass k's row is in, eased with its beat-up; 0 before the first."""
        n = 0.0
        for p in self.passes:
            if t < p.land - self.lead:
                break
            n = p.k + self.beat_up(t, p.land)
        return n

    def current(self, t: float) -> Pass | None:
        """The pass in the air or about to be (from the beat before it to its own beat-up's end), else None after the
        last."""
        for p in self.passes:
            if t < p.land + self.settle:
                return p
        return None

    # the shed
    def shed_row(self, t: float) -> tuple[int, float]:
        """(r, u): the shed is changing over (or has changed) into row r's config, u of the way (0..1); r = 0 before the
        first change-over. The change into row r is round the beat before the pass that lays it (`before` for row 1)."""
        times = [self.before] + self.beats
        r = 0
        for i, b in enumerate(times):
            if t >= b + self.cross - 0.5 * self.shed_dur:
                r = i + 1
            else:
                break
        if r == 0:
            return 0, 1.0
        c = times[r - 1] + self.cross
        return r, float(in_out_cubic((t - (c - 0.5 * self.shed_dur)) / self.shed_dur))

    def shed(self, t: float, j: int) -> float:
        """Warp j's place in the shed, -1 (down) .. 1 (up): open for row r, warp j is up when j + r is even."""
        r, u = self.shed_row(t)
        up = 1.0 if (j + r) % 2 == 0 else -1.0
        return up if r == 0 else -up + 2 * up * u

    # the shuttle
    def flight(self, t: float, p: Pass) -> float:
        """0..1: how far across pass p is at t (0 at its start side until it departs, 1 on landing)."""
        return float(in_out_cubic((t - p.depart) / (p.land - p.depart)))


# ------------------------------------------------------------------------------------------------------ plies

def arc_length(c: np.ndarray) -> np.ndarray:
    """Cumulative length along a polyline (m, 3), 0 at its first point."""
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])


def ply_offsets(c: np.ndarray, normal, offset: float, turns_per_len: float, phase: float = 0.0, plies: int = 3,
                s=None) -> list[np.ndarray]:
    """The ply centrelines of a thread whose centreline c (m, 3) lies in the plane square to `normal`: each ply `offset`
    from it, wound at `turns_per_len` turns per unit of `s` (default: the arc length along c) from `phase` turns, plies
    evenly spaced. The frame is (N, B) with N the plane's normal and B = T x N, so a thread that stays in its plane
    never twists of its own accord."""
    c = np.asarray(c, float)
    s = arc_length(c) if s is None else np.asarray(s, float)
    T = np.gradient(c, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    N = np.broadcast_to(np.asarray(normal, float), c.shape)
    N = N - T * np.sum(N * T, axis=1, keepdims=True)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    B = np.cross(T, N)
    out = []
    for k in range(plies):
        th = (2 * np.pi * (phase + k / plies + turns_per_len * s))[:, None]
        out.append(c + offset * (np.cos(th) * N + np.sin(th) * B))
    return out


def lay_turns(lay_deg: float, offset: float) -> float:
    """Turns per unit length of a helix at radius `offset` lying `lay_deg` degrees off its axis (thread.lay_turns)."""
    return math.tan(math.radians(lay_deg)) / (2 * math.pi * offset)
