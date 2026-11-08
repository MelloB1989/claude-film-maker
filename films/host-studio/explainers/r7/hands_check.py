"""R7 hands (agent-08): her whole take built offline as the box builds it (gesturekit.build on her committed stock
skeleton, perform.py's own params), then the hand-shape numbers from its arm track: per finger MCP/PIP/DIP (the
handshape measure), the claw (agent-13's finger_claw: MCP < 20, PIP > 15, DIP >= PIP; and handshape.claw_score > 0),
the DIP/PIP ratio out of 0.5-0.85 (PIP >= 20), a fold at the joint's limit (PIP >= 95), a broken cascade at rest, and
a sample of frames (default her WIDE 00:08: t 44.0-45.3). Her only: his skeleton never leaves the box.

    kbuild python3 films/host-studio/explainers/r7/hands_check.py [--span 44.0:45.3] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import gesturekit as G  # noqa: E402
import handshape as HS  # noqa: E402
import perform as PF  # noqa: E402
import seatkit as S  # noqa: E402


def frame_angles(perf, F) -> dict:
    P = {b: v[0] for b, v in F.items()}
    Q = {b: v[1] for b, v in F.items()}
    return {s: HS.hand_angles(P, Q, s) for s in "lr"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--span", default="44.0:45.3")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--out", default=str(PF.OUT / "her" / "hands_check.json"))
    a = ap.parse_args()
    who = "her"
    data = json.loads((HERE / "skeletons" / "her_body_read.json").read_text())
    bp = PF.body_params(who)
    bp["style"].update(PF.PERFORM_STYLE)
    pp = PF.perform_params(who)
    doc, summ = G.build(data, S.Set(**bp["set"]), S.Style(**bp["style"]), pp["sheet"], pp["cues"], pp["tilts"],
                        PF.length_s(who), 30, timing=pp.get("timing"), on_cam=pp.get("on_cam"),
                        **({"frame_want": pp["frame_want"]} if pp.get("frame_want") else {}),
                        **({"mic_cams": pp["mic_cams"]} if pp.get("mic_cams") else {}))
    # the angles over the take, from the performer itself (the same poses the build keyed)
    sk = S.Skeleton.from_read(data)
    plan = G.plan_from_sheet(pp["sheet"], pp["cues"], pp["tilts"], timing=pp.get("timing"), on_cam=pp.get("on_cam"))
    se, _ = S.autotune(sk, S.Set(**bp["set"]), S.Style(**bp["style"]))
    perf = G.Performer(sk, S.Set(**bp["set"]), se.sy, plan)
    const = {b: data["local"][b] for b in data["tracks"] if b in data["local"]}
    t0, t1 = (float(x) for x in a.span.split(":"))
    n = int(round(PF.length_s(who) * 30)) + 1
    cnt = {"frames": 0, "claw": 0, "claw_score": 0, "ratio_bad": 0, "ratio_n": 0, "fold_limit": 0, "cascade_broken": 0,
           "rest_frames": 0}
    worst = {"claw_score": -1e9}
    sample = []
    for i in range(0, n, a.every):
        t = i / 30.0
        F = perf.fk({**const, **perf.pose(t)})
        ang = frame_angles(perf, F)
        cnt["frames"] += 1
        for s in "lr":
            hit = False
            for f in HS.FINGERS4:
                m, p, d = ang[s][f]
                if m < 20.0 and p > 15.0 and d >= p:
                    hit = True
                sc = HS.claw_score(m, p, d)
                if sc > worst["claw_score"]:
                    worst = {"claw_score": round(sc, 1), "t": round(t, 2), "hand": s, "finger": f,
                             "mcp_pip_dip": [round(m), round(p), round(d)]}
                cnt["claw_score"] += sc > 0.0
                if p >= 20.0:
                    cnt["ratio_n"] += 1
                    cnt["ratio_bad"] += not (0.5 <= d / p <= 0.85)
                cnt["fold_limit"] += p >= 95.0
            cnt["claw"] += hit
            if perf.gesture_w(s, t) < 0.1:
                cnt["rest_frames"] += 1
                c = [ang[s][f][0] + ang[s][f][1] for f in HS.FINGERS4]
                cnt["cascade_broken"] += any(c[k + 1] < c[k] - 5.0 for k in range(3))
        if t0 <= t <= t1:
            sample.append({"t": round(t, 2), **{s: {f: [round(x) for x in ang[s][f]] for f in HS.FINGERS4 + ("thumb",)}
                                                for s in "lr"}})
    out = {"who": who, "build": {"pass": summ["pass"], "n_issues": summ["n_issues"], "issues": summ["issues"][:10],
                                  "clear": {k: v for k, v in summ["rows"].items() if "clear" in k}},
           "counts": cnt, "dip_pip_ratio_bad_frac": round(cnt["ratio_bad"] / max(1, cnt["ratio_n"]), 3),
           "cascade_broken_frac": round(cnt["cascade_broken"] / max(1, cnt["rest_frames"]), 3),
           "worst_claw_score": worst, "sample": sample}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "sample"}, indent=1))
    for r in sample[:: max(1, len(sample) // 8)]:
        print(r["t"], "R", r["r"], "L", r["l"])


if __name__ == "__main__":
    main()
