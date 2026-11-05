"""Blinks that read as alive: irregular timing, a fast close and a slower open, partial and double blinks, a blink
with most big gaze shifts, and blinks drawn to the ends of phrases.

Numbers (from the eye-movement literature, rounded): spontaneous blink rate ~17/min at rest, ~22-26/min talking,
far fewer when concentrating; intervals are skewed (log-normal, coefficient of variation ~0.5-0.8: never a metronome);
a blink lasts 250-400 ms, the lid closes in ~80-100 ms and reopens in ~150-250 ms; gaze shifts over ~25 deg come with
a blink most of the time, starting with the saccade; ~10% of blinks come in pairs; some never fully close.
"""
from __future__ import annotations

import math
import random

from . import curves as C
from .rig import blink as blink_curve

RATE_PER_MIN = {"rest": 17.0, "listen": 17.0, "talk": 23.0, "focus": 9.0, "nervous": 32.0, "calm": 12.0}


class Blink:
    """One blink at `t` (the start of the close): `close_s`, `hold_s` (fully closed), `open_s`, `peak` (1 = fully
    shut), per-side lag (`lag_s`: the second eye trails by a few ms) and peak difference."""

    __slots__ = ("t", "close_s", "hold_s", "open_s", "peak", "lag_s", "side_peak", "cause")

    def __init__(self, t, close_s=0.09, hold_s=0.03, open_s=0.19, peak=1.0, lag_s=0.0, side_peak=0.0, cause="spont"):
        self.t, self.close_s, self.hold_s, self.open_s = float(t), close_s, hold_s, open_s
        self.peak, self.lag_s, self.side_peak, self.cause = peak, lag_s, side_peak, cause

    def end(self) -> float:
        return self.t + self.close_s + self.hold_s + self.open_s + abs(self.lag_s)

    def at(self, t: float, side: str = "L") -> float:
        """The lid closure (0 open .. 1 shut) on one side."""
        lag = self.lag_s if side == "R" else 0.0
        peak = self.peak * (1.0 - (self.side_peak if side == "R" else 0.0))
        u = t - self.t - lag
        if u <= 0:
            return 0.0
        if u < self.close_s:  # closing: accelerates into the shut lid (ease-in, quick)
            return peak * C.skewed(u / self.close_s, 0.62)
        u -= self.close_s
        if u < self.hold_s:
            return peak
        u -= self.hold_s
        if u < self.open_s:  # opening: fast off the bottom, a long ease to open
            return peak * (1.0 - C.skewed(u / self.open_s, 0.3))
        return 0.0

    def to_json(self) -> dict:
        return {"t": round(self.t, 3), "peak": round(self.peak, 2), "dur_s": round(self.end() - self.t, 3),
                "cause": self.cause}


def _make(rnd, t, cause, partial_p=0.12, speed=1.0):
    peak = rnd.uniform(0.55, 0.85) if rnd.random() < partial_p else rnd.uniform(0.95, 1.0)
    return Blink(t, close_s=rnd.uniform(0.075, 0.105) / speed, hold_s=rnd.uniform(0.0, 0.05) / speed,
                 open_s=rnd.uniform(0.15, 0.24) / speed, peak=peak, lag_s=rnd.uniform(-0.012, 0.012),
                 side_peak=rnd.uniform(0.0, 0.05), cause=cause)


def plan(t0: float, t1: float, state: str | dict = "talk", gaze_events: list = (), phrase_ends: list = (),
         emphasis: list = (), seed: int = 0, double_p: float = 0.1, partial_p: float = 0.12,
         gaze_threshold_deg: float = 20.0, refractory_s: float = 0.7, rate_per_min: float | None = None,
         avoid: list = ()) -> list:
    """Blinks between t0 and t1. `state` names a rate (RATE_PER_MIN: rest, talk, focus, nervous, calm, listen) or a
    list of {"t0", "t1", "state"} spans; `gaze_events` are gaze.GazePlan.events (a blink goes with most shifts over
    `gaze_threshold_deg`, certain past 35 deg); `phrase_ends` [t] attract a blink 0.05-0.3 s after (60%);
    `emphasis` [t] or [(t, k)] attract one now and then (15%). Spontaneous blinks fill the rest with log-normal
    intervals; no two blinks closer than `refractory_s`; none inside an `avoid` span [(t0, t1)] (another face's
    blinks)."""
    rnd = random.Random(seed)
    spans = state if isinstance(state, list) else [{"t0": t0, "t1": t1, "state": state}]

    def rate(t):
        if rate_per_min:
            return rate_per_min
        for sp in spans:
            if sp["t0"] <= t < sp["t1"]:
                return RATE_PER_MIN.get(sp["state"], 17.0)
        return RATE_PER_MIN.get(spans[-1]["state"], 17.0) if spans else 17.0

    forced = []
    for ev in gaze_events:
        a = ev.get("amplitude_deg", 0.0)
        if a >= gaze_threshold_deg:
            p = 0.65 + 0.35 * C.clamp((a - gaze_threshold_deg) / 15.0)
            if rnd.random() < p:
                forced.append(_make(rnd, ev.get("t_eye", ev["t"]) - rnd.uniform(0.0, 0.03), "gaze", 0.0, 1.15))
    for t in phrase_ends:
        if rnd.random() < 0.6:
            forced.append(_make(rnd, t + rnd.uniform(0.05, 0.3), "phrase", partial_p))
    for e in emphasis:
        t = e if isinstance(e, (int, float)) else e[0]
        if rnd.random() < 0.15:
            forced.append(_make(rnd, t - rnd.uniform(0.0, 0.08), "emphasis", partial_p))
    forced.sort(key=lambda b: b.t)
    kept = []
    for b in forced:  # a forced blink too close to an earlier one is dropped
        if t0 <= b.t <= t1 and (not kept or b.t - kept[-1].t >= refractory_s * 0.7):
            kept.append(b)

    out = list(kept)
    t = t0 + rnd.uniform(0.2, 1.5)
    while t < t1:
        mean = 60.0 / rate(t)
        sigma = 0.55
        mu = math.log(mean) - sigma * sigma / 2  # log-normal with that mean
        gap = max(refractory_s, rnd.lognormvariate(mu, sigma))
        if all(abs(t - b.t) >= refractory_s for b in out):
            b = _make(rnd, t, "spont", partial_p)
            out.append(b)
            if rnd.random() < double_p:  # a double blink: the second follows the first's opening
                out.append(_make(rnd, b.end() + rnd.uniform(0.02, 0.08), "double", partial_p))
        t += gap
    out.sort(key=lambda b: b.t)
    return _clear(_irregular(out, rnd, t0, t1, refractory_s), avoid, t0, t1, refractory_s)


def _clear(out: list, avoid: list, t0: float, t1: float, refractory_s: float, pad: float = 0.08) -> list:
    """No blink inside an `avoid` span [(a, b) s] (another face's blinks: two people blinking on the same frame reads
    as a glitch in a two-shot, round 3): each one that falls in one moves by up to 0.9 s, keeping the refractory
    spacing, or is dropped. Reseeding could not do it (8 seeds left 4 clashes on the box)."""
    if not avoid:
        return out
    spans = [(float(a) - pad, float(b) + pad) for a, b in avoid]
    hit = lambda s0, s1: any(s0 < b and a < s1 for a, b in spans)  # noqa: E731
    kept = []
    for b in sorted(out, key=lambda x: x.t):
        d = b.end() - b.t
        if not hit(b.t, b.t + d):
            kept.append(b)
            continue
        for off in (0.25, -0.25, 0.45, -0.45, 0.65, -0.65, 0.9, -0.9):
            t = b.t + off
            if t0 <= t and t + d <= t1 and not hit(t, t + d) and all(abs(t - k.t) >= refractory_s * 0.7 for k in kept
                                                                      if k.cause != "double" and b.cause != "double"):
                b.t = t
                kept.append(b)
                break
    kept.sort(key=lambda x: x.t)
    return kept


def _cv(ts: list) -> float:
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    if len(gaps) < 2:
        return 1.0
    m = sum(gaps) / len(gaps)
    return math.sqrt(sum((g - m) ** 2 for g in gaps) / len(gaps)) / m if m > 0 else 1.0


def _irregular(out: list, rnd, t0: float, t1: float, refractory_s: float, cv_min: float = 0.3,
               tries: int = 60) -> list:
    """People do not blink on a beat: while the intervals vary by less than `cv_min` (std/mean; under 0.25 reads as a
    metronome), move a spontaneous blink by up to half its gaps, keeping the refractory spacing. Day 1: a 10 s face
    with even phrase ends came out at 0.24."""
    for _ in range(tries):
        if _cv([b.t for b in out]) >= cv_min:
            break
        idx = [i for i, b in enumerate(out)  # a spontaneous blink, not one with its double right after
               if b.cause == "spont" and not (i + 1 < len(out) and out[i + 1].cause == "double")]
        if not idx:
            break
        i = rnd.choice(idx)
        lo = out[i - 1].t if i > 0 else t0
        hi = out[i + 1].t if i + 1 < len(out) else t1
        t = out[i].t + rnd.uniform(-0.5, 0.5) * (hi - lo) / 2
        if t0 <= t <= t1 and all(abs(t - b.t) >= refractory_s for j, b in enumerate(out) if j != i):
            out[i].t = t
            out.sort(key=lambda b: b.t)
    return out


def to_curves(blinks: list, t0: float, t1: float, rate: float = 60.0, tol: float = 0.004) -> dict:
    """eyeBlinkL/R curves {name: (times, values)} for the blinks, sampled densely only around each blink (the rest
    is 0, so a curve is a few keys per blink)."""
    out = {}
    for side in ("L", "R"):
        ts, vs = [t0], [0.0]
        for b in sorted(blinks, key=lambda b: b.t):
            a, e = max(t0, b.t - 0.02), min(t1, b.end() + 0.02)
            if e <= a:
                continue
            for t in C.grid(a, e, rate * 2):
                if t > ts[-1] + 1e-6:
                    ts.append(t)
                    vs.append(max(0.0, min(1.0, b.at(t, side))))
        if ts[-1] < t1:
            ts.append(t1)
            vs.append(0.0)
        out[blink_curve(side)] = C.reduce(ts, vs, tol)
    return out


def detect(times: list, values: list, threshold: float = 0.5) -> list:
    """Blinks found in an eyeBlink curve: [(t_start, t_end, peak)] where it crosses `threshold` (for metrics and to
    see what a solver produced)."""
    out, start, peak = [], None, 0.0
    for t, v in zip(times, values):
        if v >= threshold and start is None:
            start, peak = t, v
        elif start is not None:
            peak = max(peak, v)
            if v < threshold:
                out.append((start, t, peak))
                start = None
    if start is not None:
        out.append((start, times[-1], peak))
    return out


def merge(base: dict, ours: dict, mode: str = "replace") -> dict:
    """Combine blink curves with an animation's own: "replace" (ours only), "keep" (theirs only), "max" (both)."""
    if mode == "keep":
        return {k: base[k] for k in ours if k in base}
    if mode == "replace":
        return dict(ours)
    if mode == "max":
        out = {}
        for k, (t, v) in ours.items():
            if k in base:
                tt = sorted(set(t) | set(base[k][0]))
                out[k] = (tt, C.combine([base[k], (t, v)], tt, "max"))
            else:
                out[k] = (t, v)
        return out
    raise ValueError(f"blink mode {mode!r}: replace, keep or max")
