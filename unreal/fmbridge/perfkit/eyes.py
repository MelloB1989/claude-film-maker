"""The eyes in the head: eye-in-head angles from the gaze and the composed head, fixational life, and the face rig's
eye-look curves.

- The eyes hold the gaze while the head moves (vestibulo-ocular reflex): eye = gaze - head, so head micro-motion,
  nods and settle never drag the gaze off its target.
- Holding a fixation, real eyes are never still: micro-saccades (0.2-0.8 deg every 0.4-1.6 s) and slow drift;
  on a person's face the eyes wander between the two eyes and the mouth (`scan="face"`); on a lens they stay put.
- Near targets converge the eyes (vergence: each eye turns in by atan(3.1 cm / distance)).
- The eyes cannot go past their range (about 35 deg sideways, 25 up, 30 down): what is left over is reported.

Curves: eyeLook{Left,Right,Up,Down}{L,R} = angle / gain (rig.HeadSigns.eye_deg), clipped to 0..1. Whether
"Left" means the character's left is measured by perf.calibrate (`HeadSigns.eye_flip`); the default assumes it does.
"""
from __future__ import annotations

import math
import random

from . import curves as C
from .gaze import EYE_RANGE
from .rig import HeadSigns, eye_look

HALF_IPD_CM = 3.1


def fixation_offsets(plan, times: list, micro_deg: float = 0.35, seed: int = 0) -> list:
    """Per-sample (yaw, pitch) offsets from the target while fixating: micro-saccades (step-like, ~40 ms), slow
    drift, and face scanning for shifts with scan="face" (between the two eyes and the mouth of a face at the
    shift's distance). Each offset jump is a tiny saccade; the jumps never fall in the first 0.25 s of a shift."""
    rnd = random.Random(seed)
    drift_y, drift_p = C.Noise(seed + 101, base_hz=0.5, octaves=2), C.Noise(seed + 102, base_hz=0.5, octaves=2)
    # build a step plan: (t, yaw_off, pitch_off)
    steps = [(-1e9, 0.0, 0.0)]
    shifts = list(plan.shifts) if plan else []
    t_end = times[-1] if times else 0.0
    for i, s in enumerate(shifts):
        t = s.t + 0.25
        stop = shifts[i + 1].t if i + 1 < len(shifts) else t_end
        steps.append((s.t, 0.0, 0.0))
        if s.scan == "face":
            d = max(30.0, s.dist_cm)
            eye_off = math.degrees(math.atan(3.2 / d))
            mouth = -math.degrees(math.atan(7.0 / d))
            spots = [(eye_off, 0.3 * eye_off), (-eye_off, 0.3 * eye_off), (0.0, mouth)]
            cur = rnd.randrange(2)
            while t < stop:
                cur = rnd.choice([k for k in range(3) if k != cur]) if rnd.random() < 0.85 else cur
                y, p = spots[cur]
                steps.append((t, y + rnd.gauss(0, 0.15), p + rnd.gauss(0, 0.15)))
                t += rnd.uniform(0.45, 1.5)
        elif s.scan != "still":
            k = 0.5 if s.scan == "lens" else 1.0
            while t < stop:
                if rnd.random() < 0.7:
                    steps.append((t, rnd.gauss(0, micro_deg * k), rnd.gauss(0, micro_deg * 0.6 * k)))
                else:
                    steps.append((t, 0.0, 0.0))  # back on target
                t += rnd.uniform(0.4, 1.6)
    out = []
    j = 0
    prev = cur = (0.0, 0.0)
    for t in times:
        while j + 1 < len(steps) and steps[j + 1][0] <= t:
            j += 1
            prev = cur  # where the eye was when this micro-saccade set off
        ts, y, p = steps[j]
        u = C.smoothstep((t - ts) / 0.04)  # a micro-saccade lasts ~40 ms
        cur = (prev[0] + (y - prev[0]) * u, prev[1] + (p - prev[1]) * u)
        out.append((cur[0] + 0.08 * drift_y.at(t), cur[1] + 0.08 * drift_p.at(t)))
    return out


def solve(plan, head: dict, micro_deg: float = 0.35, vergence: bool = True, seed: int = 0) -> dict:
    """Eye-in-head angles per eye on `head`'s time grid: {"times", "L": [(yaw, pitch)], "R": [...], "clipped_deg":
    the worst gaze error left by the eyes' range once the head has had 0.6 s to follow (during a big shift the eyes
    saturate for a moment, as real ones do)}. `plan` is the gaze.GazePlan the head came from."""
    times = head["times"]
    fix = fixation_offsets(plan, times, micro_deg, seed)
    L, R, worst = [], [], 0.0
    for i, t in enumerate(times):
        gy, gp = plan.gaze(t) if plan else (0.0, 0.0)
        ey = gy + fix[i][0] - head["yaw"][i]
        ep = gp + fix[i][1] - head["pitch"][i]
        s = plan.shift_at(t) if plan else None
        verg = math.degrees(math.atan(HALF_IPD_CM / max(20.0, s.dist_cm))) if (vergence and s) else 0.0
        for eye, out, inward in (("L", L, -verg), ("R", R, verg)):  # the left eye turns in toward their right
            y = max(-EYE_RANGE["yaw"], min(EYE_RANGE["yaw"], ey + inward))
            p = max(-EYE_RANGE["down"], min(EYE_RANGE["up"], ep))
            if s is None or t - s.t > 0.6:
                worst = max(worst, abs(y - (ey + inward)), abs(p - ep))
            out.append((y, p))
    return {"times": times, "L": L, "R": R, "clipped_deg": round(worst, 2)}


def to_rig(eyes: dict, signs: HeadSigns | None = None, tol: float = 0.003, lid_follow: float = 0.0) -> dict:
    """Eye angles as eyeLook* curves {name: (times, values)} (each 0..1), keys reduced to `tol`. `lid_follow` adds
    that much eyeBlink per 30 deg of looking down (most MetaHuman rigs already follow; leave it 0 unless the lids
    float above a downward look)."""
    s = signs or HeadSigns()
    flip = -1.0 if getattr(s, "eye_flip", False) else 1.0
    times = eyes["times"]
    out = {}
    lids = {}
    for side in ("L", "R"):
        cols = {"Left": [], "Right": [], "Up": [], "Down": []}
        for y, p in eyes[side]:
            if s.eye_table and side in s.eye_table:  # measured per eye and direction (perf.calibrate, r4)
                for d, v in s.eye_curves(side, y, p).items():
                    cols[d].append(v)
                continue
            y *= flip
            cols["Left"].append(min(1.0, max(0.0, y / s.eye_deg["Left"])))
            cols["Right"].append(min(1.0, max(0.0, -y / s.eye_deg["Right"])))
            cols["Up"].append(min(1.0, max(0.0, p / s.eye_deg["Up"])))
            cols["Down"].append(min(1.0, max(0.0, -p / s.eye_deg["Down"])))
        for d, v in cols.items():
            out[eye_look(d, side)] = C.reduce(times, v, tol)
        if lid_follow:
            lids[side] = [lid_follow * min(1.0, max(0.0, -p / 30.0)) for _, p in eyes[side]]
    for side, v in lids.items():
        out[f"lidfollow:{side}"] = (times, v)  # merged into eyeBlink by the caller (blinks.merge_lids)
    return out


def angles_from_rig(curves: dict, signs: HeadSigns | None = None) -> dict:
    """The inverse of to_rig: eye angles per side from eyeLook curves {name: (times, values)} on the first curve's
    times. For metrics and for reading back a solver's eyes."""
    s = signs or HeadSigns()
    flip = -1.0 if getattr(s, "eye_flip", False) else 1.0
    key = next((k for k in curves if "eyeLook" in k), None)
    if key is None:
        return {"times": [], "L": [], "R": []}
    times = sorted({t for k, (ts, _) in curves.items() if "eyeLook" in k for t in ts})
    out = {"times": times}
    for side in ("L", "R"):
        def v(d):
            ts, vs = curves.get(eye_look(d, side), ([0.0], [0.0]))
            return [C.at(ts, vs, t) for t in times]
        lf, rt, up, dn = v("Left"), v("Right"), v("Up"), v("Down")
        if s.eye_table and side in s.eye_table:
            ea = s.eye_angle
            out[side] = [(ea(side, "Left", a) + ea(side, "Right", b), ea(side, "Up", c) + ea(side, "Down", d))
                         for a, b, c, d in zip(lf, rt, up, dn)]
            continue
        out[side] = [(flip * (a * s.eye_deg["Left"] - b * s.eye_deg["Right"]), c * s.eye_deg["Up"] - d * s.eye_deg["Down"])
                     for a, b, c, d in zip(lf, rt, up, dn)]
    return out
