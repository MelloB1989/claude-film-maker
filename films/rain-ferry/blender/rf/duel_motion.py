"""The duel's motion as functions of time (shots rise, standoff_vroid, eye_s, eye_t, freeze; rf/duel.py keys them in
Blender): easing, a breath, the wind and its gusts, a heartbeat, a line's mouth shapes, and the ferry pole lifted out
of the boat and planted. Pure numpy: tested without Blender in blender/tests/test_rf_duel_motion.py.

Times are seconds into a shot; angles degrees; points metres (world, or a character's frame where it says so).
"""
from __future__ import annotations

import math

import numpy as np


def ease(u: float) -> float:
    """0 to 1 over u 0..1, slow at both ends (clamped outside)."""
    u = min(1.0, max(0.0, float(u)))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def ease_out(u: float) -> float:
    """0 to 1, fast then settling (a cubic out)."""
    u = min(1.0, max(0.0, float(u)))
    return 1.0 - (1.0 - u) ** 3


def ease_in(u: float) -> float:
    u = min(1.0, max(0.0, float(u)))
    return u ** 3


def span(t: float, a: float, b: float, curve=ease) -> float:
    """How far through [a, b] time t is, shaped by `curve` (0 before a, 1 after b)."""
    if b <= a:
        return 1.0 if t >= b else 0.0
    return curve((t - a) / (b - a))


def envelope(t: float, a: float, b: float, c: float, d: float) -> float:
    """0 before a, up to 1 by b, held to c, back to 0 by d (eased both ways)."""
    return span(t, a, b) * (1.0 - span(t, c, d))


def lerp(a, b, k: float):
    return tuple(float(x) + (float(y) - float(x)) * k for x, y in zip(a, b))


def breath(t: float, rate: float, phase: float = 0.0) -> float:
    """A breath's depth, 0 (out) to 1 (in), `rate` breaths a second: in over the first 40% of each, out over the
    rest (an exhale is the longer half)."""
    u = (t * rate + phase) % 1.0
    if u < 0.4:
        return ease(u / 0.4)
    return 1.0 - ease((u - 0.4) / 0.6)


def gusts(t: float, at) -> float:
    """The wind's gusts at time t: each (start, length, strength) rises fast over its first quarter and dies away."""
    v = 0.0
    for t0, length, strength in at:
        x = (t - t0) / max(length, 1e-6)
        if 0.0 <= x <= 1.0:
            v += strength * (ease(x / 0.25) if x < 0.25 else 1.0 - ease((x - 0.25) / 0.75))
    return v


def wind(t: float, seed: int = 0, *, base: float = 1.0, at=()) -> float:
    """A wind's push at time t, about `base` (+ gusts): three incommensurate swells, so nothing repeats in a shot.
    Different seeds give the same character of wind out of step (a strand, a tail, a hem each its own)."""
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0.0, 2.0 * math.pi, 3)
    v = (0.55 * math.sin(2 * math.pi * 0.31 * t + ph[0]) + 0.3 * math.sin(2 * math.pi * 0.73 * t + ph[1])
         + 0.15 * math.sin(2 * math.pi * 1.9 * t + ph[2]))
    return base * (1.0 + 0.35 * v) + gusts(t, at)


def sway(t: float, k: float, seed: int = 0, *, freq: float = 0.9, lag: float = 0.35, at=()) -> float:
    """The swing of a point `k` (0 root .. 1 tip) down a strand of hair or a hanging cloth in the wind: a travelling
    wave whose tip lags behind its root by `lag` of a cycle, its size following the wind (`at`: gusts)."""
    rng = np.random.default_rng(seed + 17)
    ph = rng.uniform(0.0, 2.0 * math.pi)
    w = wind(t - lag * k / freq, seed, at=at)
    return w * math.sin(2 * math.pi * freq * t - 2 * math.pi * lag * k + ph)


def heartbeat(t: float, beats, *, dub: float = 0.28, decay: float = 10.0) -> float:
    """A heartbeat's thump at time t, 0..1: each beat at a time in `beats` a strong pulse (lub) and a smaller one
    `dub` s later, each a sharp rise and an exponential fall."""
    rise = 60.0
    peak = math.log((rise + decay) / decay) / rise              # where a pulse is highest: scaled to its size there
    norm = (1.0 - math.exp(-rise * peak)) * math.exp(-decay * peak)
    v = 0.0
    for b in beats:
        for at, size in ((b, 1.0), (b + dub, 0.55)):
            x = t - at
            if x >= 0:
                v += size * (1.0 - math.exp(-x * rise)) * math.exp(-x * decay) / norm
    return min(1.0, v)


def clock(speeds, fps: float, speed0: float) -> list:
    """A clock for something that moves by time (toon.rain's drops) slowed frame by frame: for its speed on each
    frame, the seconds of motion at `speed0` it has had by then, so it decelerates to a stop rather than jumping."""
    out, c = [], 0.0
    for v in speeds:
        out.append(c)
        c += max(0.0, float(v)) / speed0 / fps
    return out


# the vowels a line's syllables open the mouth to, as VRM's mouth presets
VOWELS = ("aa", "ih", "ou", "ee", "oh")


def mouth(t: float, syllables, *, attack: float = 0.05, release: float = 0.08) -> dict:
    """The mouth's shapes at time t for a line spoken as `syllables` [(start, end, vowel, openness)]: each vowel up
    over `attack`, held, closed over `release` at its end; consonants are the dips between. {vowel: weight}."""
    out = {v: 0.0 for v in VOWELS}
    for start, end, vowel, amount in syllables:
        if vowel not in out:
            raise ValueError(f"mouth: {vowel!r} is not a vowel shape ({', '.join(VOWELS)})")
        w = span(t, start, start + attack) * (1.0 - span(t, end - release, end))
        out[vowel] = max(out[vowel], amount * w)
    return out


def syllables(start: float, end: float, vowels, *, hold_last: float = 1.6, openness: float = 0.7) -> list:
    """A line's syllables spread over [start, end]: `vowels` (each a VOWELS shape, or (shape, openness)), the last
    held `hold_last` times as long as the others (a drawn-out ending, as in わかいねぇ)."""
    vs = [(v, openness) if isinstance(v, str) else tuple(v) for v in vowels]
    weights = [1.0] * (len(vs) - 1) + [hold_last]
    unit = (end - start) / sum(weights)
    out, t = [], start
    for (v, a), w in zip(vs, weights):
        out.append((t, t + unit * w, v, a))
        t += unit * w
    return out


# ---------------------------------------------------------------------------------------------------- the pole

def _unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def slerp_dir(a, b, k: float) -> np.ndarray:
    """The direction k of the way from a to b, turning on the great circle between them."""
    a, b = _unit(a), _unit(b)
    c = float(np.clip(a @ b, -1.0, 1.0))
    ang = math.acos(c)
    if ang < 1e-6:
        return a
    return (math.sin((1 - k) * ang) * a + math.sin(k * ang) * b) / math.sin(ang)


def pole_at(k: float, grip0, dir0, grip1, dir1, *, below: float, lift: float = 0.0) -> tuple:
    """A pole carried by one hand from (grip0, dir0) to (grip1, dir1), k 0..1 of the way: the hand's hole on a path
    between the two grips raised by `lift` in its middle (an arc, so the foot clears what it lay on), the pole's
    direction (foot to top) turning between the two, its foot `below` m down it from the grip. (grip, dir, foot)."""
    g0, g1 = np.asarray(grip0, float), np.asarray(grip1, float)
    g = g0 + (g1 - g0) * k + np.array([0.0, 0.0, lift * math.sin(math.pi * k)])
    d = slerp_dir(dir0, dir1, k)
    return g, d, g - d * below
