"""Body life: the small motions that keep a standing body from reading as a mannequin, as bone offsets over time.

- Breathing: on each inhale the upper spine extends a little and the clavicles lift (rate by mood: calm ~12/min,
  talking ~15, nervous ~22); exhales are longer than inhales.
- Weight shifts: every 6-14 s the pelvis drifts a centimetre or two toward one leg and tilts a degree; the spine
  bends back the other way so the head stays over the feet.
- Torso follow: when the head turns far, the chest follows a little (10-20% of the head's yaw, a beat later), the
  share spread up the spine.

Offsets are ANATOMICAL, not bone axes: per bone {"flex": forward bend, "side": bend to the character's left,
"twist": turn to the character's left} in degrees, and the pelvis's lateral shift in cm. `perf.calibrate_body`
measures which local axis and sign each of those is on the real skeleton; anim.body_life then writes them as an
additive animation (local space, based on its first frame) that rides on any idle.
"""
from __future__ import annotations

import math
import random

from . import curves as C

SPINE = ("spine_01", "spine_02", "spine_03", "spine_04", "spine_05")
BREATH_SHARE = {"spine_03": 0.25, "spine_04": 0.35, "spine_05": 0.4}
FOLLOW_SHARE = {"spine_02": 0.15, "spine_03": 0.25, "spine_04": 0.3, "spine_05": 0.3}
COUNTER_SHARE = {"spine_01": 0.4, "spine_02": 0.35, "spine_03": 0.25}
BREATHS_PER_MIN = {"calm": 12.0, "rest": 13.0, "listen": 13.0, "talk": 15.0, "focus": 12.0, "nervous": 22.0}


def breath_wave(t: float, hz: float, phase: float) -> float:
    """0..1 lung fill: a quicker inhale (40% of the cycle) and a longer exhale."""
    u = (t * hz + phase) % 1.0
    if u < 0.4:
        return C.smoothstep(u / 0.4)
    return 1.0 - C.smoothstep((u - 0.4) / 0.6)


def plan(t0: float, t1: float, state: str = "rest", breath_deg: float = 0.6, clavicle_deg: float = 1.0,
         shift_cm: float = 1.5, shift_every_s=(6.0, 14.0), follow: float = 0.15, head_yaw=None, seed: int = 0,
         rate: float = 30.0) -> dict:
    """Body life from t0 to t1: {"times", "bones": {bone: {"flex", "side", "twist"}: [deg per sample]},
    "pelvis_shift_cm": [cm per sample, + = toward the character's left], "breaths_per_min"}.
    `head_yaw`: t -> the head's yaw (deg, character frame) for torso follow (None: no follow)."""
    rnd = random.Random(seed)
    times = C.grid(t0, t1, rate)
    hz = BREATHS_PER_MIN.get(state, 13.0) / 60.0 * rnd.uniform(0.92, 1.08)
    phase = rnd.random()
    # weight shifts: a target that moves every few seconds, eased
    shifts, t, side = [], t0, rnd.choice((-1.0, 1.0))
    while t < t1:
        dur = rnd.uniform(1.2, 2.2)
        shifts.append((t, dur, side * shift_cm * rnd.uniform(0.6, 1.0)))
        side = -side
        t += rnd.uniform(*shift_every_s)

    def shift_at(x):  # each shift starts where the last one landed (they are seconds apart)
        v, prev = 0.0, 0.0
        for st, dur, target in shifts:
            if x <= st:
                break
            v = prev + (target - prev) * C.skewed((x - st) / dur, 0.45)
            prev = target
        return v
    lag = 0.25
    sway = C.Noise(seed + 41, base_hz=0.08, octaves=2)
    bones = {b: {"flex": [], "side": [], "twist": []} for b in SPINE + ("clavicle_l", "clavicle_r", "pelvis")}
    pelvis = []
    for x in times:
        br = breath_wave(x, hz, phase)
        s = shift_at(x) + 0.25 * shift_cm * sway.at(x)
        pelvis.append(s)
        tilt = -0.7 * s  # the pelvis drops on the unloaded side: degrees per cm
        yaw = (head_yaw(x - lag) if head_yaw else 0.0) * follow
        for b in SPINE:
            flex = -breath_deg * br * BREATH_SHARE.get(b, 0.0)  # extension on the inhale
            side_b = -tilt * COUNTER_SHARE.get(b, 0.0)  # bend back over the feet
            twist = yaw * FOLLOW_SHARE.get(b, 0.0)
            bones[b]["flex"].append(flex)
            bones[b]["side"].append(side_b)
            bones[b]["twist"].append(twist)
        for c in ("clavicle_l", "clavicle_r"):
            bones[c]["flex"].append(0.0)
            bones[c]["side"].append(clavicle_deg * br * (1 if c.endswith("l") else -1))  # both lift (mirrored axes)
            bones[c]["twist"].append(0.0)
        bones["pelvis"]["flex"].append(0.0)
        bones["pelvis"]["side"].append(tilt)
        bones["pelvis"]["twist"].append(0.0)
    return {"times": times, "bones": bones, "pelvis_shift_cm": pelvis, "breaths_per_min": round(hz * 60.0, 2),
            "shifts": [{"t": round(a, 3), "dur_s": round(d, 3), "cm": round(c, 3)} for a, d, c in shifts]}


def to_local(life: dict, axes: dict) -> dict:
    """Anatomical offsets to local-axis rotations per bone: `axes` {bone: {"flex": [axis, sign], "side": [...],
    "twist": [...]}} with axis "x"|"y"|"z" (perf.calibrate_body measures it). Returns {bone: {"x": [deg], "y": [deg],
    "z": [deg]}} for the bones that have axes."""
    out = {}
    for b, comps in life["bones"].items():
        ax = axes.get(b)
        if not ax:
            continue
        n = len(life["times"])
        rot = {"x": [0.0] * n, "y": [0.0] * n, "z": [0.0] * n}
        for comp, vals in comps.items():
            a, sign = ax[comp]
            for i, v in enumerate(vals):
                rot[a][i] += sign * v
        out[b] = rot
    return out


def quat_from_euler_xyz(x_deg: float, y_deg: float, z_deg: float) -> list:
    """A quaternion [x, y, z, w] for small rotations about the local X, then Y, then Z axes (degrees)."""
    hx, hy, hz = (math.radians(a) / 2 for a in (x_deg, y_deg, z_deg))
    qx = [math.sin(hx), 0.0, 0.0, math.cos(hx)]
    qy = [0.0, math.sin(hy), 0.0, math.cos(hy)]
    qz = [0.0, 0.0, math.sin(hz), math.cos(hz)]
    return qmul(qz, qmul(qy, qx))


def qmul(a: list, b: list) -> list:
    """Hamilton product a*b of [x, y, z, w] quaternions."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz]
