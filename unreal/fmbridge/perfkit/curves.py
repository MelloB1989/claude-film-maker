"""Curves: sampled signals over time, easing, organic moves and smooth noise.

A curve is a pair of lists (times in seconds, values). `Signal` builds one by adding layers on a fixed sample grid;
`reduce` drops keys a linear interpolation would reproduce within a tolerance, so writes stay small.

Why these shapes: robotic motion is linear (constant velocity), symmetric (eases in exactly as it eases out), lands
dead on its target and then freezes. Living motion accelerates faster than it brakes (`skew` < 0.5), carries a little
past the target and settles back (`overshoot`), and never holds perfectly still (`noise`).
"""
from __future__ import annotations

import bisect
import math
import random


# --- easing -----------------------------------------------------------------------------------------------------

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def min_jerk(u: float) -> float:
    """The minimum-jerk profile 0..1 (10u^3 - 15u^4 + 6u^5): how a hand or a head moves between two rests (zero
    velocity and acceleration at both ends, bell-shaped speed)."""
    u = clamp(u)
    return u * u * u * (10.0 + u * (-15.0 + 6.0 * u))


def skewed(u: float, skew: float = 0.5) -> float:
    """Warp time so a min-jerk move peaks in speed at `skew` (0..1) of its duration instead of half way: 0.35-0.45 is
    a quick start and a long brake, the asymmetry of a natural head turn."""
    u = clamp(u)
    skew = clamp(skew, 0.05, 0.95)
    if abs(skew - 0.5) < 1e-6:
        return min_jerk(u)
    p = math.log(0.5) / math.log(skew)  # u**p maps skew -> 0.5
    return min_jerk(u ** p)


def smoothstep(u: float) -> float:
    u = clamp(u)
    return u * u * (3.0 - 2.0 * u)


def settle(s: float, duration: float, damping: float = 0.55) -> float:
    """What is left of an overshoot `s` seconds after it peaked: 1 at s=0 with zero slope, decaying to 0 over about
    `duration` with one small undershoot (an under-damped spring's step response, inverted)."""
    if s <= 0:
        return 1.0
    if duration <= 0 or s >= 2.5 * duration:
        return 0.0
    w = 2.0 * math.pi / (duration * 1.3)  # one swing within the duration
    zeta = clamp(damping, 0.05, 0.95)
    wn = w / math.sqrt(1 - zeta * zeta)
    k = zeta * wn
    return math.exp(-k * s) * (math.cos(w * s) + (k / w) * math.sin(w * s))


def move(t: float, t0: float, duration: float, a: float, b: float, skew: float = 0.42, overshoot: float = 0.0,
         settle_s: float = 0.0) -> float:
    """The value at time `t` of a move from `a` (before `t0`) to `b`, taking `duration` seconds with a skewed
    min-jerk profile, carrying `overshoot` (a fraction of the distance) past `b` and settling back over `settle_s`.
    Continuous in value and velocity."""
    if t <= t0:
        return a
    d = b - a
    peak = b + overshoot * d
    if t <= t0 + duration or duration <= 0:
        return a + (peak - a) * skewed((t - t0) / duration if duration > 0 else 1.0, skew)
    if overshoot == 0.0 or settle_s <= 0:
        return peak
    return b + (peak - b) * settle(t - t0 - duration, settle_s)


# --- smooth noise -----------------------------------------------------------------------------------------------

class Noise:
    """Smooth, deterministic, roughly 1/f noise: octaves of cubic-interpolated value noise. `at(t)` is in -1..1
    (about +-0.5 typical). `base_hz` is the lowest octave's rate; each octave doubles the rate and halves the
    amplitude (`gain`)."""

    def __init__(self, seed: int = 0, base_hz: float = 0.25, octaves: int = 3, gain: float = 0.5):
        self.seed, self.base_hz, self.octaves, self.gain = seed, base_hz, octaves, gain
        self._lat: dict = {}
        norm = sum(gain ** i for i in range(octaves))
        self._norm = 1.0 / norm if norm else 1.0

    def _v(self, octave: int, i: int) -> float:
        key = (octave, i)
        v = self._lat.get(key)
        if v is None:
            v = random.Random(hash((self.seed, octave, i)) & 0xFFFFFFFF).uniform(-1.0, 1.0)
            self._lat[key] = v
        return v

    def at(self, t: float) -> float:
        out, amp, hz = 0.0, 1.0, self.base_hz
        for o in range(self.octaves):
            x = t * hz
            i = math.floor(x)
            u = x - i
            p0, p1, p2, p3 = (self._v(o, i + k) for k in (-1, 0, 1, 2))
            # Catmull-Rom through the lattice: smooth (C1) and passes through the points
            out += amp * 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u +
                                (-p0 + 3 * p1 - 3 * p2 + p3) * u * u * u)
            amp *= self.gain
            hz *= 2.0
        return out * self._norm


# --- sampled signals --------------------------------------------------------------------------------------------

def grid(t0: float, t1: float, rate: float) -> list:
    """Sample times from t0 to t1 inclusive at `rate` Hz."""
    n = max(1, int(math.ceil((t1 - t0) * rate - 1e-9)))
    return [t0 + (t1 - t0) * i / n for i in range(n + 1)]


def at(times: list, values: list, t: float) -> float:
    """Linear interpolation of a keyed curve, holding the end values outside it."""
    if not times:
        return 0.0
    if t <= times[0]:
        return values[0]
    if t >= times[-1]:
        return values[-1]
    i = bisect.bisect_right(times, t)
    t0, t1 = times[i - 1], times[i]
    u = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
    return values[i - 1] + (values[i] - values[i - 1]) * u


class Signal:
    """Values on a fixed grid that layers add into: `s.add(fn)` adds fn(t) at every sample."""

    def __init__(self, t0: float, t1: float, rate: float = 60.0, value: float = 0.0):
        self.times = grid(t0, t1, rate)
        self.values = [value] * len(self.times)
        self.rate = rate

    def add(self, fn) -> "Signal":
        self.values = [v + fn(t) for t, v in zip(self.times, self.values)]
        return self

    def mul(self, fn) -> "Signal":
        self.values = [v * fn(t) for t, v in zip(self.times, self.values)]
        return self

    def map(self, fn) -> "Signal":
        self.values = [fn(v) for v in self.values]
        return self

    def at(self, t: float) -> float:
        return at(self.times, self.values, t)

    def pair(self) -> tuple:
        return list(self.times), list(self.values)


def reduce(times: list, values: list, tol: float) -> tuple:
    """Ramer-Douglas-Peucker on a 1-D curve: the fewest keys whose linear interpolation stays within `tol` of every
    sample (always keeping the ends). Iterative, so long curves do not hit the recursion limit."""
    n = len(times)
    if n <= 2 or tol <= 0:
        return list(times), list(values)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        t0, v0, t1, v1 = times[i0], values[i0], times[i1], values[i1]
        worst, wi = -1.0, -1
        for i in range(i0 + 1, i1):
            u = (times[i] - t0) / (t1 - t0) if t1 > t0 else 0.0
            e = abs(values[i] - (v0 + (v1 - v0) * u))
            if e > worst:
                worst, wi = e, i
        if worst > tol and wi > 0:
            keep[wi] = True
            stack.append((i0, wi))
            stack.append((wi, i1))
    return [t for t, k in zip(times, keep) if k], [v for v, k in zip(values, keep) if k]


def resample(times: list, values: list, new_times: list) -> list:
    return [at(times, values, t) for t in new_times]


def combine(curves: list, new_times: list, how: str = "add") -> list:
    """Merge several (times, values) curves on `new_times`: "add", "max", "mul" or "replace" (the last wins)."""
    out = None
    for times, values in curves:
        v = resample(times, values, new_times)
        if out is None:
            out = v
        elif how == "add":
            out = [a + b for a, b in zip(out, v)]
        elif how == "max":
            out = [max(a, b) for a, b in zip(out, v)]
        elif how == "mul":
            out = [a * b for a, b in zip(out, v)]
        elif how == "replace":
            out = v
        else:
            raise ValueError(f"unknown combine mode {how!r} (add, max, mul, replace)")
    return out if out is not None else [0.0] * len(new_times)


def lowpass(values: list, rate: float, cutoff_hz: float, passes: int = 2) -> list:
    """A zero-phase low-pass: a one-pole filter run forward and back (`passes` times each way), so it smooths without
    delaying. Used to take the buzz out of a solver's head curves."""
    if cutoff_hz <= 0 or len(values) < 3:
        return list(values)
    a = 1.0 - math.exp(-2.0 * math.pi * cutoff_hz / rate)
    out = list(values)
    for _ in range(passes):
        y = out[0]
        for i in range(len(out)):
            y += a * (out[i] - y)
            out[i] = y
        y = out[-1]
        for i in range(len(out) - 1, -1, -1):
            y += a * (out[i] - y)
            out[i] = y
    return out


def derivative(times: list, values: list) -> list:
    """Central differences (per second), one per sample."""
    n = len(times)
    if n < 2:
        return [0.0] * n
    d = []
    for i in range(n):
        j0, j1 = max(0, i - 1), min(n - 1, i + 1)
        dt = times[j1] - times[j0]
        d.append((values[j1] - values[j0]) / dt if dt > 0 else 0.0)
    return d
