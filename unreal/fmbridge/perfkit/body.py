"""The body's part of a performance, planned in seconds and frames: idles that never loop visibly, gestures whose
stroke lands on the stressed word, and walk-to / turn-to moves with matched play rates.

Sequencer blends overlapping full-body sections by weight (normalised: two sections at full weight average), so a
gesture over an idle is made by splitting the idle around it with matching ease: idle -> (cross-fade) -> gesture ->
(cross-fade) -> idle. An ADDITIVE gesture (anim.additive) rides on top instead, without splitting.

Sections come out in the shape `seq.anim` takes: {"anim", "start", "end", "offset" (s into the clip), "blend_in",
"blend_out" (frames), "rate", "loop", "row", "weight"}.
"""
from __future__ import annotations

import math
import random

from . import curves as C


def frames(t: float, fps: float) -> int:
    return int(round(t * fps))


class Clip:
    """An animation the planner can use: its path, length (s), and for gestures where the stroke (the meaningful
    instant: the hand's beat, the palm's reveal) falls inside it; for walks the speed it covers at rate 1 (cm/s).
    `additive` says it is an additive animation (rides on top)."""

    __slots__ = ("anim", "length_s", "stroke_s", "speed_cm_s", "additive", "tags")

    def __init__(self, anim: str, length_s: float, stroke_s: float | None = None, speed_cm_s: float = 0.0,
                 additive: bool = False, tags=()):
        self.anim, self.length_s = anim, float(length_s)
        self.stroke_s = float(stroke_s) if stroke_s is not None else 0.4 * float(length_s)
        self.speed_cm_s, self.additive, self.tags = float(speed_cm_s), bool(additive), list(tags)

    @classmethod
    def from_json(cls, d) -> "Clip":
        if isinstance(d, Clip):
            return d
        return cls(d["anim"], d.get("length_s", 2.0), d.get("stroke_s"), d.get("speed_cm_s", 0.0),
                   d.get("additive", False), d.get("tags", ()))


def place_gestures(gestures: list, library: dict, fps: float, min_gap_s: float = 0.3, lead_s: float = 0.08) -> tuple:
    """Gesture sections whose strokes land `lead_s` before their beat (a gesture's stroke leads the stressed
    syllable slightly). `gestures` [{"name" | "anim", "at_s", "hold_s" (0), "intensity" (weight, 1)}];
    `library` {name: Clip | dict}. Overlapping gestures: the later one moves after the earlier (if it can still
    land within 0.4 s of its beat), else it is dropped. Returns (sections, notes)."""
    placed, notes = [], []
    last_end = -1e9
    for g in sorted(gestures, key=lambda g: g["at_s"]):
        key = g.get("name") or g.get("anim")
        if key in library:
            clip = Clip.from_json(library[key])
        elif g.get("anim"):
            clip = Clip(g["anim"], g.get("length_s", 2.0), g.get("stroke_s"), additive=g.get("additive", False))
        else:
            notes.append({"dropped": key, "why": f"no gesture {key!r} in the library ({', '.join(sorted(library))})"})
            continue
        start = g["at_s"] - lead_s - clip.stroke_s
        hold = float(g.get("hold_s", 0.0))
        end = start + clip.length_s + hold
        if not clip.additive and start < last_end + min_gap_s:
            late = last_end + min_gap_s - start
            if late > 0.4:
                notes.append({"dropped": key, "at_s": g["at_s"], "why": f"overlaps the previous gesture by {late:.2f} s"})
                continue
            start += late
            end += late
            notes.append({"moved": key, "by_s": round(late, 3)})
        blend = min(0.35, clip.length_s * 0.25)
        sec = {"anim": clip.anim, "start": frames(start, fps), "end": frames(end, fps), "offset": 0.0,
               "blend_in": frames(blend, fps), "blend_out": frames(blend * 1.3, fps), "loop": False,
               "weight": float(g.get("intensity", 1.0)), "kind": "gesture", "additive": clip.additive,
               "stroke_frame": frames(start + clip.stroke_s, fps)}
        if start < 0:  # starts before the line: play in from the right offset
            sec["offset"] = -start
            sec["start"] = 0
        placed.append(sec)
        if not clip.additive:
            last_end = end
    return placed, notes


def idles(t0: float, t1: float, clips: list, fps: float, gaps: list = (), seed: int = 0, segment_s=(4.0, 9.0),
          blend_s: float = 0.8) -> list:
    """Idle sections from t0 to t1 that never repeat visibly: segments of a few seconds, each from a random clip at a
    random offset and a play rate of 0.92-1.08, cross-fading `blend_s` into the next; split around `gaps` [(a, b)]
    (the full-body gestures), easing out into each and back in after. `clips` [Clip | dict] (at least one)."""
    if not clips:
        return []
    rnd = random.Random(seed)
    cl = [Clip.from_json(c) for c in clips]
    spans, t = [], t0
    for a, b in sorted(gaps):
        if a > t:
            spans.append((t, a, True))
        t = max(t, b)
    if t < t1:
        spans.append((t, t1, False))
    out = []
    for a, b, before_gap in spans:
        s = a
        while s < b - 0.05:
            seg = rnd.uniform(*segment_s)
            e = min(b, s + seg)
            if b - e < segment_s[0] * 0.5:  # do not leave a sliver
                e = b
            c = rnd.choice(cl)
            rate = rnd.uniform(0.92, 1.08)
            off = rnd.uniform(0.0, max(0.0, c.length_s - 0.5))
            first, last = s == a, e >= b
            sec = {"anim": c.anim, "start": frames(s - (0 if first else blend_s), fps),
                   "end": frames(e + (blend_s if last and before_gap else 0.0), fps), "offset": round(off, 3),
                   "rate": round(rate, 3), "loop": True, "kind": "idle",
                   "blend_in": frames(blend_s, fps) if (not first or a > t0) else 0,
                   "blend_out": frames(blend_s, fps) if (not last or before_gap) else 0}
            sec["start"] = max(frames(t0, fps), sec["start"])
            out.append(sec)
            s = e
    return out


def heading_deg(a, b, offset_deg: float = 0.0) -> float:
    """The yaw (degrees, Unreal's: 0 = +X, 90 = +Y) from point a to b, plus the actor's facing offset."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) + offset_deg


def unwrap(prev: float, yaw: float) -> float:
    """`yaw` moved by whole turns to be within 180 deg of `prev` (keys must not spin the long way round)."""
    while yaw - prev > 180:
        yaw -= 360
    while yaw - prev < -180:
        yaw += 360
    return yaw


def turn(t0: float, yaw0: float, yaw1: float, fps: float, speed: float = 1.0) -> tuple:
    """A turn in place from yaw0 to yaw1 starting at t0: duration grows with the angle (0.45 s + 0.5 s per 90 deg,
    / speed), skewed min-jerk. Returns (keys [(frame, yaw)], end time)."""
    yaw1 = unwrap(yaw0, yaw1)
    dur = (0.45 + 0.5 * abs(yaw1 - yaw0) / 90.0) / max(0.2, speed)
    n = max(2, int(dur * fps / 3))
    keys = [(frames(t0 + dur * i / n, fps), yaw0 + (yaw1 - yaw0) * C.skewed(i / n, 0.42)) for i in range(n + 1)]
    return keys, t0 + dur


def walk(t0: float, start: list, path: list, fps: float, speed_cm_s: float = 140.0, yaw0: float | None = None,
         facing_offset_deg: float = 0.0, accel_s: float = 0.6, decel_s: float = 0.8, turn_first_deg: float = 45.0,
         end_yaw: float | None = None, z: float | None = None) -> dict:
    """Walk an actor from `start` through `path` points ([x, y, z] cm) at `speed_cm_s`: it turns in place first when
    the first leg is more than `turn_first_deg` off its facing, accelerates over `accel_s`, rounds corners (its yaw
    leads the path by ~0.3 s), decelerates over `decel_s`, and optionally turns to `end_yaw` at the end.
    Returns {"keys": [[frame, [x, y, z], {"yaw"}]], "walk": (t_start, t_stop), "end_s", "distance_cm", "yaw_end"}
    (key_transform's shape) with keys every 3 frames."""
    pts = [list(map(float, start))] + [list(map(float, p)) for p in path]
    if z is not None:
        pts = [[p[0], p[1], z] for p in pts]
    legs = [math.dist(pts[i][:2], pts[i + 1][:2]) for i in range(len(pts) - 1)]
    total = sum(legs)
    keys = []
    yaw = yaw0 if yaw0 is not None else heading_deg(pts[0], pts[1], facing_offset_deg)
    t = t0
    first = heading_deg(pts[0], pts[1], facing_offset_deg) if total > 0 else yaw
    if total > 0 and abs(unwrap(yaw, first) - yaw) > turn_first_deg:
        tk, t = turn(t, yaw, first, fps)
        keys += [[f, pts[0], {"yaw": y}] for f, y in tk]
        yaw = unwrap(yaw, first)
    if total <= 0:
        return {"keys": keys or [[frames(t0, fps), pts[0], {"yaw": yaw}]], "walk": None, "end_s": t,
                "distance_cm": 0.0, "yaw_end": yaw}
    # distance over time: accelerate, cruise, decelerate (trapezoid speed with smoothed corners)
    v = speed_cm_s
    accel_s = min(accel_s, total / v)
    decel_s = min(decel_s, total / v)
    cruise_s = max(0.0, (total - v * (accel_s + decel_s) / 2) / v)
    dur = accel_s + cruise_s + decel_s

    def dist(u):  # cm covered u seconds into the walk
        if u <= 0:
            return 0.0
        if u < accel_s:
            return v * accel_s * _ease_dist(u / accel_s)
        if u < accel_s + cruise_s:
            return v * accel_s / 2 + v * (u - accel_s)
        w = min(1.0, (u - accel_s - cruise_s) / decel_s) if decel_s > 0 else 1.0
        return v * accel_s / 2 + v * cruise_s + v * decel_s * _brake_dist(w)

    def point(d):
        for i, L in enumerate(legs):
            if d <= L or i == len(legs) - 1:
                u = min(1.0, d / L) if L > 0 else 1.0
                a, b = pts[i], pts[i + 1]
                return [a[k] + (b[k] - a[k]) * u for k in range(3)], i
            d -= L
        return pts[-1], len(legs) - 1

    scale = total / max(1e-6, dist(dur))  # land exactly on the end point
    step = 3.0 / fps
    u = 0.0
    walk_start = t
    while u <= dur + 1e-9:
        d = dist(u) * scale
        p, i = point(d)
        ahead, _ = point(min(total, d + speed_cm_s * 0.3))
        hd = heading_deg(p, ahead, facing_offset_deg) if math.dist(p[:2], ahead[:2]) > 1.0 else yaw
        yaw = unwrap(yaw, hd)
        keys.append([frames(t + u, fps), [round(x, 2) for x in p], {"yaw": round(yaw, 2)}])
        u += step
    if keys[-1][1] != [round(x, 2) for x in pts[-1]]:
        keys.append([frames(t + dur, fps), [round(x, 2) for x in pts[-1]], {"yaw": round(yaw, 2)}])
    t_end = t + dur
    if end_yaw is not None and abs(unwrap(yaw, end_yaw) - yaw) > 2:
        tk, t_end = turn(t_end, yaw, end_yaw, fps)
        keys += [[f, [round(x, 2) for x in pts[-1]], {"yaw": round(y, 2)}] for f, y in tk[1:]]
        yaw = unwrap(yaw, end_yaw)
    return {"keys": keys, "walk": (walk_start, walk_start + dur), "end_s": t_end, "distance_cm": round(total, 2),
            "yaw_end": round(yaw, 2), "accel_s": accel_s, "decel_s": decel_s}


def _ease_dist(w: float) -> float:
    """Distance covered (in units of v * duration) while speed ramps 0 -> v smoothly over w in 0..1."""
    w = C.clamp(w)
    # integral of smoothstep(x) from 0 to w: w^3 - w^4 / 2
    return w ** 3 - 0.5 * w ** 4


def _brake_dist(w: float) -> float:
    """Distance (in units of v * duration) while speed ramps v -> 0 smoothly over w in 0..1."""
    w = C.clamp(w)
    return w - _ease_dist(w)


def walk_sections(walk_plan: dict, walk_clip, idle_clip, fps: float, speed_cm_s: float, blend_s: float = 0.35) -> tuple:
    """The animation sections of a walk plan: the walk loop over the moving span at the play rate that matches the
    clip's own speed (no foot slide at cruise), cross-fading from and back to the idle. Returns (sections, check)
    where check reports the expected foot slide."""
    if not walk_plan.get("walk"):
        return [], {"slide_cm_s": 0.0}
    c = Clip.from_json(walk_clip)
    a, b = walk_plan["walk"]
    rate = speed_cm_s / c.speed_cm_s if c.speed_cm_s > 0 else 1.0
    secs = [{"anim": c.anim, "start": frames(a - blend_s * 0.5, fps), "end": frames(b + blend_s, fps),
             "rate": round(rate, 3), "loop": True, "blend_in": frames(blend_s, fps), "blend_out": frames(blend_s, fps),
             "kind": "walk", "offset": 0.0}]
    # while accelerating and braking the loop plays at cruise rate: that is the slide we accept
    slide = speed_cm_s * 0.5  # mean mismatch over the ramps
    ramp_share = (walk_plan.get("accel_s", 0) + walk_plan.get("decel_s", 0)) / max(1e-6, b - a)
    return secs, {"rate": round(rate, 3), "slide_cm_s_ramps": round(slide, 1), "ramp_share": round(ramp_share, 2),
                  "clip_speed_cm_s": c.speed_cm_s, "why": "the loop is matched at cruise; on the ramps the feet slide "
                  "unless walk start/stop clips are given"}
