"""Organic head motion: the gaze-driven turns of `gaze.GazePlan`, plus nods, tilts, speech beats, breathing and the
micro-motion that keeps a held head alive; and `naturalize`, which calms a speech solver's robotic head curves.

What reads as robotic, and what this does instead:
- constant-speed turns that stop dead -> skewed min-jerk moves with overshoot and settle (gaze.py);
- a frozen head between moves -> 1/f micro-motion (~0.3-0.6 deg) and a breathing pitch (~0.25 Hz);
- yes-nods as symmetric sine waves -> a fast drop, a slower return that rebounds a little past level and settles;
  repeated nods shrink;
- the head on a pivot -> pitch dips in big turns, roll leans into the turn, an at-rest tilt of the character's own;
- solver jitter -> a zero-phase low-pass and a gain (`naturalize`).

Units: degrees, seconds, the character's frame (yaw + = their left, pitch + = up, roll + = top of head to their
left). `to_rig` maps to the HeadYaw/HeadPitch/HeadRoll curves with measured signs (rig.HeadSigns).
"""
from __future__ import annotations

import math
import random

from . import curves as C
from .rig import HeadSigns


class Nod:
    """A nod at `t`: kind "nod" (down then up, `count` times, each smaller), "beat" (one small quick drop on a
    stressed word), "up" (a chin lift: "oh!" / a phrase start), "shake" (a yaw shake). `depth_deg` the first swing.
    ("yes"/"no" are accepted for nod/shake, but YAML reads a bare yes/no as true/false: write nod/shake.)"""

    KINDS = ("nod", "beat", "up", "shake")
    ALIASES = {"yes": "nod", "no": "shake"}
    __slots__ = ("t", "kind", "depth_deg", "count", "speed")

    def __init__(self, t: float, kind: str = "nod", depth_deg: float | None = None, count: int = 1, speed: float = 1.0):
        kind = self.ALIASES.get(kind, kind)
        if kind not in self.KINDS:
            raise ValueError(f"nod kind {kind!r}: one of {', '.join(self.KINDS)} (YAML reads a bare yes/no as a "
                             "boolean)")
        default = {"nod": 5.0, "beat": 2.2, "up": 3.0, "shake": 6.0}[kind]
        self.t, self.kind, self.count, self.speed = float(t), kind, max(1, int(count)), max(0.3, float(speed))
        self.depth_deg = float(default if depth_deg is None else depth_deg)

    def axis(self) -> str:
        return "yaw" if self.kind == "shake" else "pitch"

    def at(self, t: float) -> float:
        """This nod's offset on its axis at `t` (0 outside it)."""
        if t <= self.t:
            return 0.0
        s = (t - self.t) * self.speed
        if self.kind == "up":  # lift quickly, hold a beat, come back down slowly
            return self.depth_deg * (C.skewed(s / 0.16, 0.4) - C.skewed((s - 0.3) / 0.45, 0.5))
        down = {"nod": 0.16, "beat": 0.11, "shake": 0.18}[self.kind]
        back = {"nod": 0.24, "beat": 0.18, "shake": 0.22}[self.kind]
        rebound = {"nod": 0.25, "beat": 0.3, "shake": 0.12}[self.kind]
        v, depth, start = 0.0, self.depth_deg, 0.0
        sign = -1.0  # pitch drops first; a shake turns to one side first
        for _ in range(self.count):
            u = s - start
            if u <= 0:
                break
            if u <= down:  # the drop: fast
                v += sign * depth * C.skewed(u / down, 0.4)
            elif u <= down + back:  # the return: slower, carrying past level by `rebound`
                v += sign * depth * (1.0 - (1.0 + rebound) * C.skewed((u - down) / back, 0.45))
            else:  # the rebound settles home
                v += -sign * rebound * depth * C.settle(u - down - back, 0.35)
            start += down + back * 0.8
            depth *= 0.7
            if self.kind == "shake":
                sign = -sign
        return v

    def end(self) -> float:
        return self.t + (0.5 * self.count + 0.9) / self.speed


class Tilt:
    """A held head tilt (roll, and optionally pitch/yaw offsets): eases in at `t` over `ease_s`, holds until `until`,
    eases out. A curious or sympathetic listener tilts 4-8 deg."""

    __slots__ = ("t", "until", "roll_deg", "pitch_deg", "yaw_deg", "ease_s")

    def __init__(self, t: float, until: float, roll_deg: float = 5.0, pitch_deg: float = 0.0, yaw_deg: float = 0.0,
                 ease_s: float = 0.5):
        self.t, self.until, self.roll_deg, self.pitch_deg, self.yaw_deg, self.ease_s = (
            float(t), float(until), float(roll_deg), float(pitch_deg), float(yaw_deg), max(0.05, float(ease_s)))

    def weight(self, t: float) -> float:
        return C.skewed((t - self.t) / self.ease_s, 0.45) * (1.0 - C.skewed((t - self.until) / (self.ease_s * 1.3), 0.5))


class Style:
    """A head's personality: how much it moves (`gain`), its resting tilt and pitch, micro-motion amplitude in degrees,
    breathing, how far roll leans into turns, and how much speech loudness animates it."""

    def __init__(self, gain: float = 1.0, rest_roll_deg: float = 0.0, rest_pitch_deg: float = 0.0,
                 micro_deg: float = 0.45, breath_deg: float = 0.25, breath_hz: float = 0.24, lean: float = 0.12,
                 speech_gain: float = 1.0, seed: int = 0):
        self.gain, self.rest_roll_deg, self.rest_pitch_deg = gain, rest_roll_deg, rest_pitch_deg
        self.micro_deg, self.breath_deg, self.breath_hz, self.lean = micro_deg, breath_deg, breath_hz, lean
        self.speech_gain, self.seed = speech_gain, seed

    @classmethod
    def from_json(cls, d: dict | None) -> "Style":
        return cls(**(d or {}))


def compose(t0: float, t1: float, plan=None, nods: list = (), tilts: list = (), style: Style | None = None,
            speech=None, rate: float = 60.0) -> dict:
    """The head's (yaw, pitch, roll) in the character's frame from t0 to t1 at `rate` Hz: the gaze plan's turns
    (gaze.GazePlan or None), nods, tilts, the style's rest pose, breathing and micro-motion, and with `speech` (a
    function t -> loudness 0..1, e.g. audio.Envelope.at) livelier micro-motion while talking.
    Returns {"times", "yaw", "pitch", "roll"}."""
    style = style or Style()
    times = C.grid(t0, t1, rate)
    ny, np_, nr = (C.Noise(style.seed * 3 + k, base_hz=0.22, octaves=3) for k in (1, 2, 3))
    fast = C.Noise(style.seed * 3 + 7, base_hz=1.4, octaves=2)
    phase = random.Random(style.seed).uniform(0, 2 * math.pi)
    yaw, pitch, roll = [], [], []
    prev_y = None
    for t in times:
        by, bp = plan.head_base(t) if plan else (0.0, 0.0)
        y, p, r = by, bp + style.rest_pitch_deg, style.rest_roll_deg
        # lean into turns: roll follows yaw velocity a little, with a lasting share of the yaw
        if prev_y is not None:
            vel = (by - prev_y) * rate
            r += style.lean * 0.08 * max(-60.0, min(60.0, vel))
        prev_y = by
        r += 0.04 * by
        for n in nods:
            off = n.at(t)
            if off:
                if n.axis() == "yaw":
                    y += off
                else:
                    p += off
        for tl in tilts:
            w = tl.weight(t)
            if w:
                r += w * tl.roll_deg
                p += w * tl.pitch_deg
                y += w * tl.yaw_deg
        loud = max(0.0, min(1.0, speech(t))) if speech else 0.0
        m = style.micro_deg * (1.0 + 0.8 * style.speech_gain * loud)
        y += m * 1.2 * ny.at(t)
        p += m * np_.at(t) + style.breath_deg * math.sin(2 * math.pi * style.breath_hz * t + phase)
        r += m * 0.7 * nr.at(t)
        if loud:  # quick small activity while speaking: the head rides the voice
            p += 0.6 * style.speech_gain * loud * fast.at(t)
            y += 0.4 * style.speech_gain * loud * fast.at(t + 17.0)
        yaw.append(y)
        pitch.append(p)
        roll.append(r)
    return {"times": times, "yaw": yaw, "pitch": pitch, "roll": roll}


def beats_from_emphasis(emphasis: list, depth_deg: float = 2.2, seed: int = 0, every: int = 1) -> list:
    """Beat nods on stressed words: `emphasis` is [t] or [(t, strength 0..1)]; each beat's depth scales with its
    strength and jitters a little so no two are alike. `every` keeps 1 in n (a calmer delivery)."""
    rnd = random.Random(seed)
    out = []
    for i, e in enumerate(emphasis):
        if i % max(1, every):
            continue
        t, k = (e, 1.0) if isinstance(e, (int, float)) else (e[0], e[1])
        out.append(Nod(t - rnd.uniform(0.04, 0.1), "beat", depth_deg * (0.6 + 0.4 * k) * rnd.uniform(0.8, 1.2)))
    return out


def naturalize(times: list, values: list, cutoff_hz: float = 2.0, gain: float = 0.7, rate: float = 60.0) -> tuple:
    """Calm a solver's head curve: resample on a regular grid, low-pass it without delay (removes the buzz that
    reads as robotic), scale it around its mean by `gain`. Returns (times, values)."""
    if not times:
        return [], []
    grid = C.grid(times[0], times[-1], rate)
    v = C.resample(times, values, grid)
    v = C.lowpass(v, rate, cutoff_hz)
    mean = sum(v) / len(v)
    return grid, [mean + (x - mean) * gain for x in v]


def to_rig(head: dict, signs: HeadSigns | None = None, tol_deg: float = 0.02, switch: bool = True) -> dict:
    """The composed head as the face rig's curves {"HeadYaw": (times, values), ...} in the rig's signs and curve
    assignment (signs.curves: which curve turns, nods, tilts), keys reduced
    to `tol_deg`; with `switch` HeadControlSwitch = 1 across (so the face rig turns the head)."""
    s = signs or HeadSigns()
    t = head["times"]
    out = {}
    for name, key, sign in s.axes():
        out[name] = C.reduce(t, [sign * v for v in head[key]], tol_deg)
    if switch:
        out["HeadControlSwitch"] = ([t[0], t[-1]], [1.0, 1.0])
    return out


def from_rig(curves: dict, signs: HeadSigns | None = None) -> dict:
    """The inverse of to_rig for reading a solver's head: {"yaw": (t, v), ...} in the character's frame."""
    s = signs or HeadSigns()
    out = {}
    for name, key, sign in s.axes():
        if name in curves:
            t, v = curves[name]
            out[key] = (list(t), [sign * x for x in v])
    return out


# A head turn carried by the neck as well as the head (a real neck turns along its length).
NECK_SHARE = {"neck_01": 0.3, "neck_02": 0.3, "head": 0.4}


def axis_quat(axis: str, deg: float) -> list:
    """A quaternion [x, y, z, w] for `deg` about the local axis "x", "y" or "z"."""
    h = math.radians(deg) / 2
    q = [0.0, 0.0, 0.0, math.cos(h)]
    q["xyz".index(axis)] = math.sin(h)
    return q


def turn_bones(own: dict, yaw_deg: list, axes: dict, shares: dict | None = None) -> dict:
    """The neck and head bones' local rotations with a head turn added: `own` {bone: [q per key]} as the animation
    has them, `yaw_deg` the turn per key (the character's frame: + = their left), `axes` {bone: [axis, sign]} the
    local axis that turns each bone left (perf.calibrate: yaw_bone), each bone taking its NECK_SHARE.
    -> {bone: [q per key]}."""
    from .bodylife import qmul
    sh = shares or NECK_SHARE
    return {b: [qmul(q, axis_quat(axes[b][0], axes[b][1] * sh[b] * y)) for q, y in zip(qs, yaw_deg)]
            for b, qs in own.items() if b in sh and b in axes}
