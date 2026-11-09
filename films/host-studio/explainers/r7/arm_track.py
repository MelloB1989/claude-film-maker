"""Her arm and hand track over the take, offline, from gesturekit on her committed stock skeleton
(skeletons/her_body_read.json): per frame, in the actor frame (x forward, y her right, z up, cm), the shoulder, elbow,
wrist and finger joints of both arms, each hand's rotation (component quaternion), the gesture weight and the speak
weight. For agent-13's naturalness rows (wrist angles, forearm elevation, arcs, velocity profiles, joint lag,
asymmetry). Her only: his skeleton never leaves the box.

    cd tools && uv run python ../films/host-studio/explainers/r7/arm_track.py [--every 1] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import gesturekit as G  # noqa: E402
import perform as PF  # noqa: E402
import seatkit as S  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--out", default=str(PF.OUT / "her" / "arm_track.json"))
    a = ap.parse_args()
    d = json.loads((HERE / "skeletons" / "her_body_read.json").read_text())
    p = PF.perform_params("her")
    sy = replace(PF.STYLE["her"], **PF.PERFORM_STYLE)
    sk = S.Skeleton.from_read(d)
    G.hand_profile(None)  # her finals' hands (the default)
    plan = G.plan_from_sheet(p["sheet"], p["cues"], p["tilts"], timing=p["timing"], on_cam=p["on_cam"])
    st = PF.set_of("her")
    se, _ = S.autotune(sk, st, sy)
    perf = G.Performer(sk, st, se.sy, plan)
    const = {b: d["local"][b] for b in d["tracks"] if b in d["local"]}
    fps, n = 30, int(round(PF.length_s("her") * 30)) + 1
    frames = []
    for i in range(0, n, a.every):
        t = i / fps
        frames.append(G.track_frame(perf, plan, perf.fk({**const, **perf.pose(t)}), i, t))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"who": "her", **G.track_doc(plan, fps, frames)}))
    print(out, len(frames), "frames")


if __name__ == "__main__":
    main()
