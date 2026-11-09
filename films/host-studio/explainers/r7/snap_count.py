"""R7 hands (agent-08): a quick whole-take finger-snap count on her offline performer, after agent-13's
move.finger_snap (a fingertip >= 90 cm/s while the wrist has stopped dead: under 10 cm/s, having moved > 20 cm/s within
the 2 frames before). Prints the times per hand; agent-13's row is the number of record.

    kbuild python3 films/host-studio/explainers/r7/snap_count.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import gesturekit as G  # noqa: E402
import perform as PF  # noqa: E402
import seatkit as S  # noqa: E402

d = json.loads((HERE / "skeletons" / "her_body_read.json").read_text())
bp = PF.body_params("her")
bp["style"].update(PF.PERFORM_STYLE)
pp = PF.perform_params("her")
sk = S.Skeleton.from_read(d)
plan = G.plan_from_sheet(pp["sheet"], pp["cues"], pp["tilts"], timing=pp.get("timing"), on_cam=pp.get("on_cam"))
st = S.Set(**bp["set"])
se, _ = S.autotune(sk, st, S.Style(**bp["style"]))
perf = G.Performer(sk, st, se.sy, plan)
const = {b: d["local"][b] for b in d["tracks"] if b in d["local"]}
n = int(round(PF.length_s("her") * 30)) + 1
hist = {s: [] for s in "lr"}
snaps = {s: [] for s in "lr"}
prev = None
for i in range(n):
    t = i / 30.0
    F = perf.fk({**const, **perf.pose(t)})
    tips = G.finger_tips(perf, F)
    cur = {s: {"wrist": perf.actor(F[f"hand_{s}"][0]), **{k: v for k, v in tips.items() if k.endswith("_" + s)}}
           for s in "lr"}
    if prev:
        for s in "lr":
            v = {k: S.norm(S.sub(cur[s][k], prev[s][k])) * 30.0 for k in cur[s]}
            hist[s].append(v["wrist"])
            tip = max(x for k, x in v.items() if k != "wrist")
            if tip >= 90.0 and v["wrist"] < 10.0 and max(hist[s][-3:-1] or [0.0]) > 20.0:
                if not snaps[s] or t - snaps[s][-1][0] > 0.2:
                    snaps[s].append((round(t, 2), round(tip)))
    prev = cur
L = PF.length_s("her")
print(json.dumps({"snaps": snaps, "per_min": round(60.0 * sum(len(x) for x in snaps.values()) / L, 2)}))
