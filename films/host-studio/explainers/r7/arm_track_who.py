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

BONES = [f"{b}_{s}" for s in "lr" for b in ("clavicle", "upperarm", "lowerarm", "hand")] + \
        [f"{f}_{j}_{s}" for s in "lr" for f in ("thumb", "index", "middle", "ring", "pinky") for j in ("01", "02", "03")] + \
        ["spine_03", "spine_05", "neck_01", "head"]


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
    frames = []
    for i in range(0, n, a.every):
        t = i / fps
        F = perf.fk({**const, **perf.pose(t)})
        frames.append({"f": i, "t": round(t, 4), "speak_w": round(plan.speak_w(t), 3),
                       "gesture_w": {s: round(perf.gesture_w(s, t), 3) for s in "lr"},
                       "p": {b: [round(x, 4) for x in perf.actor(F[b][0])] for b in BONES if b in F}})
    ev = [{"hand": e.hand, "kind": e.kind, "prep": e.prep, "stroke": e.stroke, "hold": e.hold,
           "line": getattr(e, "line", "")} for e in plan.events]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"who": w, "fps": fps, "frame": "actor: x fwd, y the actor's right, z up, cm",
                               "read": str(src), "on_cam": plan.on_cam, "events": ev, "frames": frames}))
    print(out, len(frames), "frames from", src)


if __name__ == "__main__":
    main()
