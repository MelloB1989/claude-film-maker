"""Rows on a SOLVED take (docs/MOCAP_PILOT.md): the imported mocap AnimSequence on a stock MetaHuman, sampled by
`seq.sample` on the Linux box (bones' world positions, cm, Z up), judged before the constraint layers touch it.

- the body rows we already gate on (filmtools.unreal.qa_perf.body_rows: onsets/s, hands above the desk, wrist travel)
- fingers: are they alive? per finger the curl range (p95 - p5, deg), the share of frames a finger moves at all, and
  the curl's jitter (frame-to-frame second difference, deg/frame^2, p95): a solve that froze or buzzes the fingers
  shows here, and agent-08's finger layer is the fallback
- wrists: jitter (second difference, cm/frame^2, p95) and speed p95 (cm/s): the mono solve's depth noise
- what the constraint layers will have to fix, measured on the raw take with our set's numbers: wrists under the
  desk top (a take shot without a desk), the closest fingertip to the face (FACE_C/FACE_R from gesturekit's shell),
  and frames where a hand leaves the camera's picture (that is the frame check's, not here)

    uv run python -m filmtools.mocap.rows SAMPLES.json --desk-z 71 [--speaking SPANS.json] [--fps 24] [--forward 1,0,0] [--out rows.json]

Bones sampled (seq.sample bones=[...]): ROWS_BONES below.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from filmtools.unreal import qa_perf

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
ROWS_BONES = (["head", "neck_01", "spine_05", "hand_l", "hand_r", "lowerarm_l", "lowerarm_r"]
              + [f"{f}_0{i}_{s}" for f in FINGERS for i in (1, 2, 3) for s in "lr"])
FACE_UP_CM, FACE_FWD_CM, FACE_R_CM = 4.0, 7.0, 11.0  # gesturekit FACE_C/FACE_R: the face shell off the head joint
FINGER_MOVES_DEG = 1.5  # a finger 'moves' on a frame when its curl changes more than this
WANT = {  # first-guess lines for the pilot verdict; the operator's eye decides, these only point at frames
    "fingers.curl_range_deg_p50": (">=", 15.0),
    "fingers.moving_frac": (">=", 0.25),
    "fingers.curl_jitter_deg_p95": ("<=", 4.0),
    "wrist.jitter_cm_p95": ("<=", 0.6),
}


def _pct(xs: list, q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _angle(a, b, c) -> float:
    """The bend at b (deg, 0 = straight) of the chain a -> b -> c."""
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - b[i] for i in range(3)]
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu < 1e-6 or nv < 1e-6:
        return 0.0
    d = max(-1.0, min(1.0, sum(u[i] * v[i] for i in range(3)) / (nu * nv)))
    return math.degrees(math.acos(d))


def curl(P: dict, finger: str, s: str, i: int) -> float | None:
    """A finger's total curl at frame i: the bends at joints 01 and 02 (hand -> 01 -> 02 -> 03)."""
    names = ("hand_" + s, f"{finger}_01_{s}", f"{finger}_02_{s}", f"{finger}_03_{s}")
    if any(n not in P for n in names):
        return None
    p = [P[n][i][:3] for n in names]
    return _angle(p[0], p[1], p[2]) + _angle(p[1], p[2], p[3])


def _second_diff(xs: list) -> list:
    return [abs(xs[k + 1] - 2 * xs[k] + xs[k - 1]) for k in range(1, len(xs) - 1)]


def finger_rows(samples: dict) -> dict:
    P, n = samples["bones"], len(samples["frames"])
    ranges, moving, jit = [], [], []
    per = {}
    for s in "lr":
        for f in FINGERS:
            c = [curl(P, f, s, i) for i in range(n)]
            if any(x is None for x in c) or n < 3:
                continue
            r = _pct(c, 0.95) - _pct(c, 0.05)
            mv = sum(1 for k in range(1, n) if abs(c[k] - c[k - 1]) > FINGER_MOVES_DEG) / (n - 1)
            j = _pct(_second_diff(c), 0.95)
            per[f"{f}_{s}"] = {"range_deg": round(r, 1), "moving_frac": round(mv, 3), "jitter_deg_p95": round(j, 2)}
            ranges.append(r)
            moving.append(mv)
            jit.append(j)
    if not per:
        return {"fingers.error": "no finger bones in the samples (sample ROWS_BONES)"}
    return {"fingers.curl_range_deg_p50": round(_pct(ranges, 0.5), 1),
            "fingers.moving_frac": round(sum(moving) / len(moving), 3),
            "fingers.curl_jitter_deg_p95": round(_pct(jit, 0.95), 2), "fingers.per_finger": per}


def wrist_rows(samples: dict, fps: float, desk_z: float) -> dict:
    P, n = samples["bones"], len(samples["frames"])
    jit, speed, below = [], [], 0
    for s in "lr":
        h = "hand_" + s
        if h not in P:
            continue
        for k in range(1, n - 1):
            a, b, c = P[h][k - 1][:3], P[h][k][:3], P[h][k + 1][:3]
            jit.append(math.dist([0, 0, 0], [a[i] - 2 * b[i] + c[i] for i in range(3)]))
            speed.append(math.dist(a, b) * fps)
        below += sum(1 for k in range(n) if P[h][k][2] < desk_z)
    return {"wrist.jitter_cm_p95": round(_pct(jit, 0.95), 3), "wrist.speed_cm_s_p95": round(_pct(speed, 0.95), 1),
            "wrist.below_desk_top_frac": round(below / max(1, 2 * n), 3)}


def face_rows(samples: dict, forward=(1.0, 0.0, 0.0)) -> dict:
    """The closest fingertip to the face shell, cm (negative = inside it): what the face-avoid layer will move.
    `forward`: the performer's facing in world (a unit vector; the head bone's own axes are not 'forward')."""
    P, n = samples["bones"], len(samples["frames"])
    if "head" not in P:
        return {}
    best, at = 1e9, None
    for k in range(n):
        hx, hy, hz = P["head"][k][:3]
        fwd = forward
        c = [hx + fwd[0] * FACE_FWD_CM, hy + fwd[1] * FACE_FWD_CM, hz + fwd[2] * FACE_FWD_CM + FACE_UP_CM]
        for s in "lr":
            for f in FINGERS:
                b = f"{f}_03_{s}"
                if b in P:
                    d = math.dist(c, P[b][k][:3]) - FACE_R_CM
                    if d < best:
                        best, at = d, f"{b}@{samples['frames'][k]}"
    return {"face.fingertip_clear_cm_min": round(best, 1), "face.at": at}


def verdict(rows: dict) -> dict:
    out = {}
    for k, (op, line) in WANT.items():
        v = rows.get(k)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out[k] = "n/a"
        else:
            out[k] = "ok" if (v >= line if op == ">=" else v <= line) else f"look ({op} {line})"
    return out


def rows(samples: dict, fps: float, desk_z: float, spans: list | None = None, forward=(1.0, 0.0, 0.0)) -> dict:
    spans = spans or [[samples["frames"][0], samples["frames"][-1] + 1]]
    r = {**qa_perf.body_rows(samples, fps, spans, desk_z), **finger_rows(samples), **wrist_rows(samples, fps, desk_z),
         **face_rows(samples, forward)}
    r["verdict"] = verdict(r)
    return r


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("samples")
    ap.add_argument("--desk-z", type=float, required=True)
    ap.add_argument("--speaking")
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--forward", default="1,0,0", help="the performer's facing in world, x,y,z")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    fw = [float(x) for x in a.forward.split(",")]
    fw = [x / math.hypot(*fw) for x in fw]
    samples = json.loads(Path(a.samples).read_text())
    spans = json.loads(Path(a.speaking).read_text()) if a.speaking else None
    r = rows(samples, a.fps, a.desk_z, spans, fw)
    text = json.dumps(r, indent=1)
    if a.out:
        Path(a.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
