"""agent-01's r7/arm_track.py for either presenter (agent-13): the arm/hand/finger track per frame, offline, from
gesturekit on a body read, joints at 0.1 mm (0.01 cm reads a live drift as frozen). His skeleton never leaves the box,
so on box T, after his body step (agent-01's r7-body head):

    cp <agent-13 tree>/films/host-studio/explainers/r7/{arm_track_who,naturalness}.py <r7-body tree>/films/host-studio/explainers/r7/
    cd <r7-body tree>/films/host-studio/explainers
    python3 r7/arm_track_who.py --who him --read <his body_read.json> --out /tmp/him_arm_track.json
    python3 r7/naturalness.py /tmp/him_arm_track.json --json him_rows.json
    python3 r7/naturalness.py /tmp/him_arm_track.json --span 0-179 --span 422-480 --json him_rows_test.json   # SEQUENCE frames, 24 fps

Only the numbers (joint positions, no mesh, no face) go into the rows; the dump itself stays on the box.
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

def track_of(w: str, src: Path, every: int = 1) -> dict:
    """the track gesturekit.build would write for w on the body read src (a dict: {who, read, **G.track_doc})."""
    d = json.loads(src.read_text())
    p = PF.perform_params(w)
    sy = replace(PF.STYLE[w], **PF.PERFORM_STYLE)
    sk = S.Skeleton.from_read(d)
    # as gesturekit.build builds it on the box (agent-01): his gated torso (the open rest, the outfit line), his close
    #   held alive, the mic cams, the fallback's rest ranges; without them his track was another performance
    plan = G.plan_from_sheet(p["sheet"], p["cues"], p["tilts"], timing=p["timing"], on_cam=p["on_cam"],
                             close_alive=PF.length_s(w) if p.get("close_alive") else None,
                             mic_cams=p.get("mic_cams"), rest_only=p.get("rest_only"))
    st = PF.set_of(w)
    se, _ = S.autotune(sk, st, sy)
    perf = G.Performer(sk, st, se.sy, plan, torso=G.Torso(**p["torso"]) if p.get("torso") else None)
    const = {b: d["local"][b] for b in d["tracks"] if b in d["local"]}
    fps, n = 30, int(round(PF.length_s(w) * 30)) + 1
    # G.track_frame as her arm_track.py: the joint heads, hand_q and the FINGERTIPS (agent-04: without them his
    #   finger_claw / dip_pip / thumb_stiff read n/a and rest_contact saw only the tented heel, never a hover)
    frames = [G.track_frame(perf, plan, perf.fk({**const, **perf.pose(i / fps)}), i, i / fps) for i in range(0, n, every)]
    return {"who": w, "read": str(src), **G.track_doc(plan, fps, frames)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", choices=("her", "him"), required=True)
    ap.add_argument("--read", help="the body read json (default: skeletons/<who>_body_read.json, else OUT/<who>/body_read.json)")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    w = a.who
    cands = [Path(a.read)] if a.read else [HERE / "skeletons" / f"{w}_body_read.json", PF.OUT / w / "body_read.json"]
    src = next((c for c in cands if c.exists()), None)
    if src is None:
        sys.exit(f"no body read for {w}: tried {', '.join(map(str, cands))}")
    doc = track_of(w, src, a.every)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc))
    print(out, len(doc["frames"]), "frames from", src)


if __name__ == "__main__":
    main()
