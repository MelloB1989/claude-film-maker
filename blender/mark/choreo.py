"""The weave's choreography (shot B15), bpy-free: every time from the data, the speed ramp, each thread's window, the
mark's turn, the camera and the light, as functions of the film frame.

Times, in song seconds straight from the data (data/vo.json and data/audio.json, as app/src/scenes/weave.ts timesOf
reads them), never from frame numbers:
  the scene     `weave`, [start, end); its plate covers the film frames [f0, f1) the engine shows it on
                (lib.timing.scene_frames), but the animation's clock starts at the cut, whatever frame is first
  the lock      the first downbeat after the scene's own opening one (the cut lands on a downbeat, the score's big
                hit); it falls on "forget." in "I don't forget."
  back to 1x    the next beat after the lock
  the settle    the scene's last downbeat
Animation time `tau` runs through `speed_ramp` (motion.ts speedRamp, ported exactly): real time, easing to 0.5x
just before the lock, holding through it, snapping back to real time on the next beat. Everything in the plate runs on
tau, so the whole picture slows round the lock.

The threads (strands.py) arrive in the weave's order, each over the one that must already be there for its colour
change to stay hidden: the stem, then the G's thread (moss bar, under the stem, the G), then the vertical's (under the
moss bar, the loop), then the hook's (under the loop, the crossbar over the stem): its leaf lands on the lock.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

FPS = 30


def speed_ramp(t: float, keys) -> float:
    """motion.ts speedRamp: the integral of a speed curve through [time, speed] keys (inOutCubic between them, held
    outside, two keys at one time an instant change), from local time 0 to t."""
    if not keys:
        return t
    pts = sorted(keys, key=lambda k: k[0])

    def ramp_area(u):
        return u ** 4 if u <= 0.5 else u - 0.5 + (1 - u) ** 4

    def area(x):
        t0, s0 = pts[0]
        if x <= t0:
            return s0 * (x - t0)
        a = 0.0
        for i in range(1, len(pts)):
            p, sp = pts[i - 1]
            k, sk = pts[i]
            if x >= k:
                a += (k - p) * (sp + sk) / 2
                continue
            u = (x - p) / (k - p)
            return a + (k - p) * (sp * u + (sk - sp) * ramp_area(u))
        tn, sn = pts[-1]
        return a + sn * (x - tn)

    return area(t) - area(0)


@dataclass(frozen=True)
class Times:
    f0: int  # the plate's first film frame
    f1: int  # and the one after its last
    start: float  # the scene's start, the cut (s)
    end: float  # its end (s)
    lock: float  # the lock (s)
    real: float  # back to real time (s)
    l30: float  # "GitLoom."
    settle: float  # the last downbeat

    @property
    def lock_frame(self) -> int:
        return round(self.lock * FPS)


AFTER = 0.05  # s: a downbeat or beat this soon after an event is that event's own (the engine's timesOf uses it too)


def times(tm) -> Times:
    """The weave's times from a lib.timing.Timing, in seconds from the data."""
    f0, f1 = tm.scene_frames("weave")
    start, end = tm.scene("weave")
    downs = [d for d in tm.audio["downbeats"] if start + AFTER < d < end]  # after the cut's own downbeat
    if not downs:
        raise ValueError("weave: no downbeat after the scene's first")
    lock = downs[0]
    beats = [b for b in tm.audio["beats"] if lock + AFTER < b < end]
    if not beats:
        raise ValueError("weave: no beat after the lock")
    return Times(f0=f0, f1=f1, start=start, end=end, lock=lock, real=beats[0], l30=tm.word("L30", 0).start,
                 settle=downs[-1])


# the ramp: real time, easing to half speed over EASE seconds ending LEAD before the lock, held to the next beat
SLOW = 0.5
EASE = 0.3
LEAD = 0.15


def ramp_keys(T: Times):
    lk, rl = T.lock - T.start, T.real - T.start
    return [(0.0, 1.0), (lk - LEAD - EASE, 1.0), (lk - LEAD, SLOW), (rl, SLOW), (rl, 1.0)]


def tau(T: Times, f: float) -> float:
    """Animation time (s from the scene's start) at film frame f (fractional for motion-blur steps)."""
    return speed_ramp(f / FPS - T.start, ramp_keys(T))


def tau_at(T: Times, t: float) -> float:
    return speed_ramp(t - T.start, ramp_keys(T))


# ------------------------------------------------------------------------------------------------ the threads

@dataclass(frozen=True)
class Flight:
    """A thread's flight, in tau. Its head runs along the approach at a steady speed, reaches the mark at `enter` and
    eases (out-cubic) to rest at its end at `land`, the speed matching at `enter`. With `via` (a crossing), the head
    passes that crossing at the lock instead and `enter` follows from the speed. The tail stays out in the dark (the
    whole arc drawn) until `zip`, then runs in to the ribbon's start over ZIP."""
    enter: float | None
    land: float | str
    zip: float | str
    via: str | None = None


FLIGHTS = {
    "stem": Flight(0.30, 0.86, 1.02),
    "gbar": Flight(0.46, 1.36, 1.48),
    "vloop": Flight(0.92, 1.74, 1.86),
    "xhook": Flight(None, "real-0.02", "lock+0.02", via="B"),
}
ZIP = 0.3  # tau: a tail's run in, eased
HEAD_TAPER = 10.0  # MU: a running thread's end, rounded (about the ribbon's half-width)
TAIL_TAPER = 10.0
FORM = 26.0  # MU: a terminal forms over the last this much of its way in
CINCH = 0.4  # the weave's lift before the lock, above its rest (40% looser), pulled tight on the lock


def _t(T: Times, v) -> float:
    """A tau: a number, or 'lock' / 'real' (the times of the lock and of the return to real time) +- seconds."""
    if isinstance(v, str):
        base, off = (v[:4], v[4:])
        at = T.lock if base == "lock" else T.real
        return tau_at(T, at) + (float(off) if off else 0.0)
    return v


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def spring(t: float, freq: float = 5.0, damping: float = 0.6) -> float:
    """motion.ts spring: a damped step response, 0 before t = 0."""
    if t <= 0:
        return 0.0
    w = 2 * math.pi * freq
    a = damping * w
    if a * t > 40:
        return 1.0
    b = w * math.sqrt(1 - damping * damping)
    return 1 - math.exp(-a * t) * (math.cos(b * t) + (a / b) * math.sin(b * t))


def head(T: Times, name: str, st, ta: float) -> float:
    """Where thread `name`'s head is (arc length) at tau ta."""
    fl = FLIGHTS[name]
    land = _t(T, fl.land)
    if fl.via:
        sv = next(sc for cn, sc, _ in st.crossings if cn == fl.via)
        tv = tau_at(T, T.lock)
        v = 3 * (st.length - sv) / (land - tv)  # the out-cubic's speed as it leaves the crossing
        if ta < tv:
            return sv - v * (tv - ta)
        u = min(1.0, (ta - tv) / (land - tv))
        return sv + (st.length - sv) * (1 - (1 - u) ** 3)
    v = 3 * (st.length - st.s_band) / (land - fl.enter)
    if ta < fl.enter:
        return st.s_band - v * (fl.enter - ta)
    u = min(1.0, (ta - fl.enter) / (land - fl.enter))
    return st.s_band + (st.length - st.s_band) * (1 - (1 - u) ** 3)


def window(T: Times, name: str, st, ta: float) -> dict:
    """The window inputs of thread `name` (a strands.Strand) at animation time ta."""
    fl = FLIGHTS[name]
    s1 = max(head(T, name, st, ta), -HEAD_TAPER)
    z0 = _t(T, fl.zip)
    u = min(1.0, max(0.0, (ta - z0) / ZIP))
    e = 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2
    s0 = min(st.s_band * e, max(s1, 0.0))
    head_left, tail_left = st.length - s1, st.s_band - s0
    bh, bt = 1 - _smooth(head_left / FORM), 1 - _smooth(tail_left / FORM)
    lock = tau_at(T, T.lock)
    cinch = 1 + CINCH * (1 - spring(ta - (lock - 0.02), freq=4.5, damping=0.55))
    return {"s0": s0, "s1": s1, "head": HEAD_TAPER * (1 - bh), "tail": TAIL_TAPER * (1 - bt), "bh": bh, "bt": bt,
            "cinch": cinch}


def ribbon_glow(T: Times, ta: float) -> float:
    """The blood and moss ribbons' edge light: low as they weave, a flare on the lock settling to the film's glow."""
    lk = tau_at(T, T.lock)
    base = 0.45 + 0.3 * _smooth((ta - lk + 0.4) / 0.4)
    flare = 1.6 * math.exp(-max(0.0, ta - lk) / 0.35) if ta >= lk else 0.0
    return base + flare


# ------------------------------------------------------------------------------------------------ the picture

def _keys(x: float, ks) -> float:
    """util.ts keys(): piecewise inOutCubic through (time, value) keys, held outside."""
    if x <= ks[0][0]:
        return ks[0][1]
    for (a, va), (b, vb) in zip(ks, ks[1:]):
        if x <= b:
            u = (x - a) / (b - a)
            e = 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2
            return va + (vb - va) * e
    return ks[-1][1]


def mark_pose(T: Times, ta: float) -> dict:
    """The mark's turn (degrees: yaw about its vertical, pitch about its horizontal) and scale: turned away as the
    threads arrive, settling to face the camera by the last downbeat."""
    lk, st = tau_at(T, T.lock), tau_at(T, T.settle)
    yaw = _keys(ta, [(0.0, -30.0), (lk, -11.0), (st + 0.4, 0.0)])
    pitch = _keys(ta, [(0.0, 13.0), (lk, 4.5), (st + 0.4, 0.0)])
    breath = 1 + 0.012 * (1 - spring(ta - (lk - 0.02), freq=4.5, damping=0.55)) if ta < lk + 1 else 1.0
    return {"yaw": yaw, "pitch": pitch, "scale": breath}


# The final frame: the mark's centre this far right of the camera's axis (m, the camera trucks there), the camera
# this far back (m) with an 85 mm lens: the mark about 540 px tall, its centre at x ~ 560 px.
FINAL_X = 0.177
FINAL_D = 2.0


def camera(T: Times, ta: float) -> dict:
    """The camera: a slow push-in and a truck right (the mark slides left, making room for the type)."""
    lk, st = tau_at(T, T.lock), tau_at(T, T.settle)
    end = tau_at(T, T.end)
    d = _keys(ta, [(0.0, 2.62), (lk, 2.26), (st + 0.4, FINAL_D), (end, FINAL_D - 0.018)])
    x = _keys(ta, [(0.0, 0.03), (lk - 0.35, FINAL_X * 0.92), (st + 0.4, FINAL_X)])
    fstop = _keys(ta, [(0.0, 2.4), (lk, 3.2), (st, 5.6)])
    return {"x": x, "d": d, "z": 0.0, "fstop": fstop}


SWEEP_LEVEL = 11.0  # the sweep strip's emission at its middle


def light(T: Times, ta: float) -> dict:
    """The rim's gain (a hit on the cut, a pulse on the lock) and the raking sweep's progress 0..1 (None when off)."""
    lk = tau_at(T, T.lock)
    rim = 1 + 0.9 * math.exp(-max(0.0, ta) / 0.25) + 0.5 * (math.exp(-(ta - lk) / 0.3) if ta >= lk else 0.0)
    a, b = lk + 0.05, lk + 1.55
    sweep = (ta - a) / (b - a) if a <= ta <= b else None
    return {"rim": rim, "sweep": sweep}
