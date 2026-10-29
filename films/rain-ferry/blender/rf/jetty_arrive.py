"""Before the talk on the jetty: shots 6-8 (ferry, ask, refuse). Tsuru sits smoking where rf/jetty_talk.py seats her
(its stage builds the world, the cast and the compositing for these shots too, so the scene is one from the wide to
the draw); Shinza comes down the bank and up the jetty to his mark behind her, and stops. What these shots add to
that stage is here: his walk (`Walk`: footfalls planted on the planks, the body carried over them) and the smoke she
lets out of her lips (`lips_source`, `breath`).

The pure halves (`walk_path`, `footfalls`, `foot_at`) need no Blender.
"""
from __future__ import annotations

import math

import numpy as np

from . import jetty_talk as jt

# where Shinza walks from in ask (world x, y: up the jetty from its middle) and his mark (jetty_talk's)
ASK_FROM = (1.2, -0.62)
# his walk: stride (m), how high a foot lifts, how far the body drops onto each step, how far he leans into it
STRIDE, LIFT, BOB, LEAN = 0.74, 0.085, 0.022, 5.0
SMOKE = 1.15        # the smoke's colour: the fog's (the look schedule's light) lifted this much


def ease(u: float) -> float:
    return jt.ease(u)


def walk_path(t: float, start, stop, t0: float, t1: float, settle: float = 0.25) -> tuple[np.ndarray, float]:
    """Where a walker is at t going from `start` to `stop` (x, y) between t0 and t1 (s), and how far along (0..1):
    an even pace eased in over the first `settle` of the time and slowing to the stop over the last. Pure."""
    start, stop = np.asarray(start, float), np.asarray(stop, float)
    u = min(1.0, max(0.0, (t - t0) / max(t1 - t0, 1e-6)))
    s = settle

    def ramp(x):
        if x < s:
            return x * x / (2 * s)
        if x > 1 - s:
            return 1 - (1 - x) ** 2 / (2 * s)
        return x - s / 2

    k = ramp(u) / ramp(1.0)
    return start + (stop - start) * k, k


def footfalls(distance: float, stride: float, width: float) -> dict:
    """Where each foot lands along a straight walk `distance` long, (along, across): from feet together the right
    foot leads, each step `stride` long (shortened so the last lands even), the left foot `width` to the left and the
    right to the right, and the other foot brought alongside at the end. Pure."""
    n = max(1, round(distance / stride))
    step = distance / n
    out = {"left": [(0.0, width)], "right": [(0.0, -width)]}
    for i in range(1, n + 1):
        out["right" if i % 2 else "left"].append((min(distance, i * step), width if i % 2 == 0 else -width))
    last = "right" if n % 2 == 0 else "left"
    if out[last][-1][0] < distance:
        out[last].append((distance, out[last][-1][1]))
    return out


def foot_at(prints: list, d: float, stride: float, lift: float = LIFT, swing: float = 0.8) -> tuple[float, float, float]:
    """A foot's (along, across, height) when the body has come `d` along its walk: planted on a footfall until the
    body is past it, swinging to its next over `swing` strides of the body's travel centred between the two. Pure."""
    for (a0, c0), (a1, c1) in zip(prints, prints[1:]):
        mid = (a0 + a1) / 2
        span = min(swing * stride, a1 - a0)
        lo, hi = mid - span / 2, mid + span / 2
        if d < lo:
            return a0, c0, 0.0
        if d <= hi:
            u = (d - lo) / max(hi - lo, 1e-6)
            return a0 + (a1 - a0) * ease(u), c0 + (c1 - c0) * ease(u), lift * math.sin(math.pi * u)
    a, c = prints[-1]
    return a, c, 0.0


def stride_phase(prints: dict, d: float) -> float:
    """-1..1: which leg leads at body travel d (+1 the right foot forward), for the arms' swing. Pure."""
    r = foot_at(prints["right"], d, STRIDE)[0]
    lf = foot_at(prints["left"], d, STRIDE)[0]
    return max(-1.0, min(1.0, (r - lf) / (STRIDE * 0.5)))


# ---------------------------------------------------------------------------------------------------- Blender

class Walk:
    """Shinza's walk from `start` to `stop` (world x, y) between t0 and t1 (s into the shot): keyed on the stage's
    frames by `key(f, t)`, which carries his root and plants his feet; his body's pose and his hands are the shot's
    (`swing(t)` gives how his arms swing, `lean(t)` how far he leans into the walk)."""

    def __init__(self, st, start, stop, t0: float, t1: float, *, end_heading: float | None = None, ground=None):
        self.st, self.t0, self.t1 = st, t0, t1
        self.ground = ground or (lambda x, y: 0.0)
        ch = st.cast["shinza"]["vrm"]
        self.ch, self.root = ch, st.cast["shinza"]["root"]
        self.start, self.stop = np.asarray(start, float), np.asarray(stop, float)
        way = self.stop - self.start
        self.dist = float(np.linalg.norm(way))
        self.heading = math.atan2(way[1], way[0])
        self.fwd = np.array((math.cos(self.heading), math.sin(self.heading)))
        self.left = np.array((-self.fwd[1], self.fwd[0]))
        rest = {s: ch.frame.T @ np.array(ch.handles[f"{s}Foot-target"].location) * ch.scale for s in ("left", "right")}
        self.ankle = {s: float(rest[s][2]) for s in rest}
        self.toe = {s: float(rest[s][1]) for s in rest}        # how far back of the root each ankle stands
        self.prints = footfalls(self.dist, STRIDE, abs(rest["left"][0] - rest["right"][0]) / 2)
        # he ends facing her (jetty_talk's), turning into it over his last steps (or `end_heading`, degrees)
        self.end_heading = math.radians(jt.SHINZA_FACING if end_heading is None else end_heading)

    def at(self, t: float) -> tuple[np.ndarray, float]:
        return walk_path(t, self.start, self.stop, self.t0, self.t1)

    def going(self, t: float) -> float:
        """0 standing .. 1 in full stride."""
        _, k = self.at(t)
        return math.sin(math.pi * k) ** 0.5 if 0.0 < k < 1.0 else 0.0

    def swing(self, t: float) -> float:
        _, k = self.at(t)
        return stride_phase(self.prints, k * self.dist) * self.going(t)

    def key(self, f: int, t: float) -> None:
        from mathutils import Vector

        p, k = self.at(t)
        d = k * self.dist
        go = self.going(t)
        steps = d / (self.dist / max(1, round(self.dist / STRIDE)))
        dz = -BOB * (0.5 - 0.5 * math.cos(2 * math.pi * steps)) * go
        turn = ease((k - 0.75) / 0.25)
        hdg = self.heading + (self.end_heading - self.heading) * turn
        gz = float(self.ground(p[0], p[1]))
        self.root.location = Vector((p[0], p[1], gz + dz))
        self.root.rotation_euler = (0.0, 0.0, hdg)
        self.root.keyframe_insert("location", frame=f)
        self.root.keyframe_insert("rotation_euler", frame=f)
        c, s = math.cos(hdg), math.sin(hdg)
        for side in ("left", "right"):
            a, across, h = foot_at(self.prints[side], d, STRIDE)
            # the footfall as world (x, y), then into his frame as he stands now (his front, -y, along `hdg`)
            wx, wy = self.start + self.fwd * a + self.left * across
            rx, ry = wx - p[0], wy - p[1]
            along_, side_ = rx * c + ry * s, -rx * s + ry * c
            q = np.array((side_, -along_ + self.toe[side],
                          self.ankle[side] + h - dz + float(self.ground(wx, wy)) - gz))
            e = self.ch.handles[f"{side}Foot-target"]
            e.location = self.ch.to_armature(q)
            e.keyframe_insert("location", frame=f)


def lips_source(st, pose: dict, hips):
    """A function of the film frame giving where Tsuru's lips are (world), carried by her head: where
    jetty_talk.pipe_at_lips puts the pipe's mouthpiece, with her head as `pose` holds it. Smoke let out of them."""
    from mathutils import Vector

    ch = st.cast["tsuru"]["vrm"]
    fist, way = jt.pipe_at_lips(st, pose, hips)            # (it poses her so: the head is where `pose` has it)
    lips = np.asarray(fist) - np.asarray(way) * 0.09
    p = Vector(ch.world(lips))
    local = (ch.armature.matrix_world @ ch.bone("head").matrix).inverted() @ p

    def at(_frame):
        return np.array(ch.armature.matrix_world @ ch.bone("head").matrix @ local)
    return at


def breath(st, emit, source, *, push: float = 0.3, seed: int = 8, width=(0.012, 0.13), opacity: float = 0.8):
    """Smoke let out of her lips (`source`: lips_source) in the windows `emit` (s into the shot), pushed out ahead of
    her, the rain beating it down (lib/smoke.py); bake it last."""
    from lib import smoke

    s = st.ctx.look_at(st.ctx.f0)
    f = np.array((math.cos(math.radians(jt.TSURU_FACING)), math.sin(math.radians(jt.TSURU_FACING)), 0.0))
    wisp = smoke.Wisp(rain=min(1.0, s.rain.density), wind=(0.05, 0.03, 0.0), push=tuple(f * push + (0.0, 0.0, 0.03)),
                      width=width, life=2.2, rise=0.11, curl=0.07, opacity=opacity, rate=48.0,
                      emit=tuple((st.start + a, st.start + b) for a, b in emit), seed=seed)
    return smoke.ribbon("breath", wisp, source=source, coll=st.crossing["near"], also=(st.cast_coll,),
                        color=tuple(np.array(s.light.fog) * SMOKE))
