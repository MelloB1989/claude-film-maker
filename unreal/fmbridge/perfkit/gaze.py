"""Eye-head coordination: where the eyes look, how the head follows, and what is left for the eyes in the head.

A gaze shift is a target direction (yaw, pitch in degrees, in the character's frame: yaw + = their left, pitch + =
up) from a time on. People do not turn their head as a camera pans:

- the eyes jump first, in a saccade whose duration grows with its size (the main sequence, about 21 + 2.2 ms per
  degree), and the head starts 20-60 ms later (`lead="eyes"`, the default). With `lead="head"` the head starts first
  and the eyes follow it in (a deliberate, "heavy" look; also what a turn toward a sound does);
- the head takes only part of the shift: almost none of a small one (under ~8 deg the eyes do it alone), most of a
  big one (~85% past 40 deg); pitch shares less than yaw;
- the head accelerates harder than it brakes (skewed min-jerk), carries a few percent past its target and settles
  back, and dips its chin a little in the middle of a big horizontal turn;
- while the head is still moving the eyes counter-rotate (the vestibulo-ocular reflex) so the gaze stays on the
  target: eye-in-head = gaze - head, which this module computes exactly, micro-motion included.
"""
from __future__ import annotations

import math
import random

from . import curves as C

EYE_RANGE = {"yaw": 35.0, "up": 25.0, "down": 30.0}  # comfortable eye-in-head limits, degrees


def saccade_s(amplitude_deg: float) -> float:
    """A saccade's duration from its amplitude (the main sequence): 21 ms + 2.2 ms/deg, capped at 150 ms."""
    return min(0.15, 0.021 + 0.0022 * abs(amplitude_deg))


def head_share(amplitude_deg: float, axis: str = "yaw", gain: float = 1.0) -> float:
    """The fraction of a gaze shift the head takes: 0.15 under ~5 deg, rising smoothly to 0.85 by 40 deg; pitch takes
    60% of that. `gain` scales it (an animated talker 1.2, a still listener 0.7); never above 0.97."""
    f = 0.15 + 0.70 * C.smoothstep((abs(amplitude_deg) - 5.0) / 35.0)
    if axis == "pitch":
        f *= 0.6
    return min(0.97, f * gain)


class Shift:
    """One gaze shift: from `t` (s) the eyes look at (yaw, pitch) degrees; `dist_cm` the target's distance (vergence,
    face scanning); `scan` "face" to wander between a person's eyes and mouth while holding, "lens" to hold dead on
    (a camera), None for an object; `head` overrides the head's share (0..1)."""

    __slots__ = ("t", "yaw", "pitch", "dist_cm", "scan", "head", "label")

    def __init__(self, t: float, yaw: float, pitch: float = 0.0, dist_cm: float = 200.0, scan=None, head=None,
                 label: str = ""):
        self.t, self.yaw, self.pitch, self.dist_cm, self.scan, self.head, self.label = (
            float(t), float(yaw), float(pitch), float(dist_cm), scan, head, label)

    def to_json(self) -> dict:
        return {"t": self.t, "yaw": self.yaw, "pitch": self.pitch, "dist_cm": self.dist_cm, "scan": self.scan,
                "head": self.head, "label": self.label}


class Move:
    """A planned head move on one axis (what head.compose turns into a curve)."""

    __slots__ = ("t0", "dur", "a", "b", "skew", "overshoot", "settle_s")

    def __init__(self, t0, dur, a, b, skew, overshoot, settle_s):
        self.t0, self.dur, self.a, self.b, self.skew, self.overshoot, self.settle_s = t0, dur, a, b, skew, overshoot, settle_s

    def at(self, t: float) -> float:
        return C.move(t, self.t0, self.dur, self.a, self.b, self.skew, self.overshoot, self.settle_s)


class GazePlan:
    """The planned gaze and head moves for a list of shifts. `gaze(t)` and `head_base(t)` give (yaw, pitch); head
    micro-motion, nods and tilts are added by `head.compose`, and `eyes.solve` subtracts the composed head."""

    def __init__(self, shifts: list, start=(0.0, 0.0), lead: str = "eyes", head_gain: float = 1.0,
                 energy: float = 1.0, seed: int = 0, dip: float = 0.06):
        if lead not in ("eyes", "head"):
            raise ValueError(f"lead must be 'eyes' or 'head', not {lead!r}")
        self.shifts = sorted(shifts, key=lambda s: s.t)
        self.lead, self.head_gain, self.energy = lead, head_gain, max(0.2, energy)
        rnd = random.Random(seed)
        gy, gp = float(start[0]), float(start[1])
        hy, hp = gy * head_share(gy, "yaw", head_gain), gp * head_share(gp, "pitch", head_gain)
        self.start_gaze, self.start_head = (gy, gp), (hy, hp)
        self.gaze_moves = {"yaw": [], "pitch": []}
        self.head_moves = {"yaw": [], "pitch": []}
        self.dips = []  # (t0, dur, depth_deg): the chin dip of a big horizontal turn
        self.events = []  # one per shift: what was planned (for blinks and reports)
        for s in self.shifts:
            amp = math.hypot(s.yaw - gy, s.pitch - gp)
            ds = saccade_s(amp)
            head_lag = rnd.uniform(0.02, 0.06)
            dy, dp = s.yaw - hy, s.pitch - hp
            fy = s.head if s.head is not None else head_share(dy, "yaw", head_gain)
            fp = s.head if s.head is not None else head_share(dp, "pitch", head_gain)
            ny, np_ = hy + fy * dy, hp + fp * dp
            hamp = math.hypot(ny - hy, np_ - hp)
            dur = (0.16 + 0.0065 * hamp) / math.sqrt(self.energy) * rnd.uniform(0.9, 1.12)
            if self.lead == "eyes":
                t_eye, t_head = s.t, s.t + head_lag
            else:  # the head sets off first; the eyes jump once it is about a third of the way
                t_head = s.t - 0.35 * dur
                t_eye = s.t
            ov = rnd.uniform(0.04, 0.09) if hamp > 4 else rnd.uniform(0.0, 0.03)
            st = rnd.uniform(0.28, 0.45) / math.sqrt(self.energy)
            skew = rnd.uniform(0.36, 0.45)
            if amp > 0.05:
                self.gaze_moves["yaw"].append(Move(t_eye, ds, gy, s.yaw, 0.45, 0.0, 0.0))
                self.gaze_moves["pitch"].append(Move(t_eye, ds, gp, s.pitch, 0.45, 0.0, 0.0))
            if hamp > 0.05:
                self.head_moves["yaw"].append(Move(t_head, dur, hy, ny, skew, ov, st))
                # pitch overshoots less (gravity damps it)
                self.head_moves["pitch"].append(Move(t_head, dur, hp, np_, skew, ov * 0.5, st))
                if abs(ny - hy) > 12 and dip:
                    self.dips.append((t_head, dur, min(4.0, dip * abs(ny - hy))))
            self.events.append({"t": s.t, "t_eye": t_eye, "t_head": t_head, "amplitude_deg": round(amp, 2),
                                "head_deg": round(hamp, 2), "head_s": round(dur, 3), "saccade_s": round(ds, 3),
                                "label": s.label, "scan": s.scan, "dist_cm": s.dist_cm,
                                "gaze": [s.yaw, s.pitch], "head": [round(ny, 2), round(np_, 2)]})
            gy, gp, hy, hp = s.yaw, s.pitch, ny, np_

    @staticmethod
    def _chain(moves: list, start: float, t: float) -> float:
        """The value of a chain of moves: each move starts from where the previous one aimed, and adds its own offset
        from that; overlapping moves blend because each is a delta."""
        v = start
        for m in moves:
            if t <= m.t0:
                break
            v += m.at(t) - m.a
        return v

    def gaze(self, t: float) -> tuple:
        return (self._chain(self.gaze_moves["yaw"], self.start_gaze[0], t),
                self._chain(self.gaze_moves["pitch"], self.start_gaze[1], t))

    def head_base(self, t: float) -> tuple:
        y = self._chain(self.head_moves["yaw"], self.start_head[0], t)
        p = self._chain(self.head_moves["pitch"], self.start_head[1], t)
        for t0, dur, depth in self.dips:
            if t0 < t < t0 + dur * 1.2:
                p -= depth * math.sin(math.pi * (t - t0) / (dur * 1.2))
        return y, p

    def shift_at(self, t: float):
        """The shift in force at `t` (the last one started), or None before the first."""
        cur = None
        for s in self.shifts:
            if s.t <= t:
                cur = s
            else:
                break
        return cur
