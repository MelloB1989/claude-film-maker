"""R7 framing (agent-01): body.hands_out_of_frame for a grid of focal / pitch on CAM_MCU, CAM_MCU_L and CAM_CU (a hand
partly in counts there, its line 0.1), counted the way
the body build counts it (every 6th frame at 30 fps while speaking, speak_w > 0.5, in the camera cut in), from an
arm track (r7/arm_track_who.py). His skeleton never leaves the box, so run it there; it prints only fractions and
the head's height in the picture, no positions.

    python3 r7/arm_track_who.py --who him --read <his body_read.json> --out /tmp/him_arm_track.json
    python3 r7/cam_sweep.py --who him /tmp/him_arm_track.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import gesturekit as G  # noqa: E402
import perform as PF  # noqa: E402
import seatkit as S  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("track")
    ap.add_argument("--who", choices=("her", "him"), required=True)
    ap.add_argument("--every", type=int, default=6, help="the build's check_every")
    ap.add_argument("--focal", default="", help="focal lengths, comma separated (default: the set's, -3, -5)")
    ap.add_argument("--pitch", default="0,-0.5,-1,-1.5", help="pitch steps from the set's, deg")
    a = ap.parse_args()
    tr = json.loads(Path(a.track).read_text())
    fps = float(tr.get("fps", 30.0))
    on = PF.perform_params(a.who)["on_cam"]
    rigs = PF.set_of(a.who).rigs
    frames = [f for f in tr["frames"] if int(round(f["t"] * 30.0)) % a.every == 0 and f["speak_w"] > 0.5] \
        if fps == 30.0 else [f for f in tr["frames"] if f["speak_w"] > 0.5]
    for cam in ("CAM_MCU", "CAM_MCU_L", "CAM_CU"):
        fs = [f for f in frames if any(t0 <= f["t"] < t1 and c == cam for t0, t1, c in on)]
        base = rigs[cam]
        focals = [float(x) for x in a.focal.split(",") if x] or [base["focal"], base["focal"] - 3, base["focal"] - 5]
        print(f"{cam} (set: {base['focal']} mm, pitch {base['pitch']}; {len(fs)} speaking frames checked)")
        for fo in focals:
            row = []
            for dp in (float(x) for x in a.pitch.split(",")):
                rig = {**base, "focal": fo, "pitch": base["pitch"] + dp}
                k = sum(G.hands_in_frame(rig, f["p"], partial=cam in G.FRAME_PARTIAL) for f in fs) / max(1, len(fs))
                hv = [S.project(rig, f["p"]["head"]) for f in fs]
                hv = [x[1] for x in hv if x]
                row.append(f"{dp:+.1f}: {k:.3f} (head v {sum(hv) / max(1, len(hv)):.3f})")
            print(f"  {fo:5.1f} mm  " + " | ".join(row))


if __name__ == "__main__":
    main()
