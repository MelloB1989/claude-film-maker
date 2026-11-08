"""Where a presenter's head drift enters the chain (agent-04, 09 Nov: his head.drift_deg 2.697 against the 1.5 line).

Read-only, nothing played: perform.py's HEADAXES reads the head bone of each stage's animation (seat, body after sync,
the face's follow, gaze) at every on-camera frame, and head.py's drift measure (the median spread of the 0.25 s-smoothed
head over 2 s windows, yaw + pitch) runs on each. Only the summary is printed and kept; the per-frame head angles never
leave this process.

    python3 head_stages.py CUE --who him [--anims seat,body,follow,gaze] [--out out/explainers/head/<who>/stages.json]

The first stage whose median passes 1.5 owns the drift: seat/body = the body's carry (agent-01), follow/gaze = the
face's head plan or the gaze (agent-04). The placed number is head.py judge's own.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import head as H  # noqa: E402

LINE = 1.5


def windows(t: np.ndarray, yaw: np.ndarray, pitch: np.ndarray, seen: list, fps: float) -> dict:
    """head.py life_metrics' windows (0.25 s smoothing, 2 s windows at 1 s steps), reported per axis too."""
    rows = []
    for a, b in seen:
        m = (t >= a / fps) & (t < b / fps)
        if m.sum() < fps:
            continue
        tt = t[m]
        y, p = H._smooth(yaw[m], int(0.25 * fps)), H._smooth(pitch[m], int(0.25 * fps))
        w = int(2 * fps)
        for i in range(0, len(y) - w + 1, w // 2):
            py, pp = float(np.ptp(y[i:i + w])), float(np.ptp(p[i:i + w]))
            rows.append((math.hypot(py, pp), py, pp, int(round(tt[i] * fps))))
    if not rows:
        return {"windows": 0}
    s = np.array([r[0] for r in rows])
    worst = sorted(rows, reverse=True)[:5]
    return {"windows": len(rows),
            "drift_med": round(float(np.median(s)), 3),
            "yaw_med": round(float(np.median([r[1] for r in rows])), 3),
            "pitch_med": round(float(np.median([r[2] for r in rows])), 3),
            "p25": round(float(np.percentile(s, 25)), 3), "p75": round(float(np.percentile(s, 75)), 3),
            "share_over_line": round(float((s > LINE).mean()), 3),
            "worst": [{"f": r[3], "spread": round(r[0], 2), "yaw_ptp": round(r[1], 2), "pitch_ptp": round(r[2], 2)}
                      for r in worst]}


def stages(cue: dict, who: str, anims: list, run=None, out: Path | None = None) -> dict:
    import perform as PF
    run = run or PF.run
    fps = float(cue["fps"])
    s0 = cue["start"]
    seen = [[a, b] for a, b, _ in H.on_cam_frames(cue)]
    frames = [f for a, b in seen for f in range(a, b)]
    times = [round(max(0.0, (f - s0) / fps), 4) for f in frames]
    bc = PF.OUT / who / "body_check.json"
    fr = (json.loads(bc.read_text()).get("frame") if bc.exists() else None) or {"fwd": [0.0, 1.0, 0.0],
                                                                                 "right": [-1.0, 0.0, 0.0]}
    res = {"who": who, "line": LINE, "spans": len(seen), "frames": len(frames), "stages": {}}
    for k in anims:
        a = f"{PF.ANIM}/AS_exp_{who}_{k}"
        r = run(PF.HEADAXES, {"anims": [a], "times": times, "fwd": fr["fwd"], "right": fr["right"]}, 1800)
        rows = (r or {}).get(a)
        if not rows:
            res["stages"][k] = {"missing": a}
            continue
        yaw = np.array([rows[str(x)]["abs_yaw_right"] for x in times])
        pitch = np.array([rows[str(x)]["pitch_up"] for x in times])
        res["stages"][k] = windows(np.array(frames) / fps, yaw, pitch, seen, fps)
    first = next((k for k in anims if res["stages"].get(k, {}).get("drift_med", 0) > LINE), None)
    res["first_over_line"] = first
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, indent=1))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cue")
    ap.add_argument("--who", default="him", choices=["him", "her"])
    ap.add_argument("--anims", default="seat,body,follow,gaze")
    ap.add_argument("--edl")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--out")
    a = ap.parse_args()
    cue = H.load_cue(a.cue, a.edl, a.start)
    out = Path(a.out) if a.out else Path("out/explainers/head") / a.who / "stages.json"
    print(json.dumps(stages(cue, a.who, a.anims.split(","), out=out), indent=1))


if __name__ == "__main__":
    main()
