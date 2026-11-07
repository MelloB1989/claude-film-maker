"""Why does a blink read as a nod? Offline, from what perf.py head saved (qa/head_<who>.json: the head bone's samples
and blink curve) and the plan (perf.py events/planned_head): for the worst blinks, the measured pitch/yaw around the
blink against perfkit's planned head, and every planned event (gaze shift, nod, tilt) within 0.6 s. Numbers only.

    cd tools && uv run python ../films/host-studio/reel/r6/blink_why.py --who her [--top 3] [--frames 1295,1315]

Round 6: her S16 blink_nod 0.0 (r5b) -> 0.466 (K2c, f1303-1307); the orchestrator wants the cause before S16 is ever
re-rendered.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import perf as P  # noqa: E402
from filmtools.unreal import qa_head as QH  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--who", default="her")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--frames", help="f0,f1: also print this master-frame range")
    ap.add_argument("--file", help="default OUT/qa/head_<who>.json")
    ap.add_argument("--every", type=int, default=1, help="print every n-th frame of the tables")
    a = ap.parse_args()
    path = a.file or str(P.OUT / "qa" / f"head_{a.who}.json")
    seen = P.seen_frames(a.who)
    j = QH.samples(path, seen_frames=seen)
    d = json.loads(Path(path).read_text())["samples"]
    ST = QH.stability()
    h = ST.from_bones(d["frames"], d["fps"], d["bone"], d["forward"])
    f0, fps = d["frames"][0], d["fps"]
    fr = d["frames"]
    e = P.events(a.who)
    s0 = P.START[a.who]
    planned = [("gaze", round(s0 + g["t"] * fps), g) for g in e.get("gaze", [])] + \
              [("nod", round(s0 + n["t"] * fps), n) for n in e.get("nods", [])] + \
              [("tilt", round(s0 + t["t"] * fps), t) for t in e.get("tilts", [])] + \
              [("expr", round(s0 + x["t"] * fps), x) for x in e.get("expressions", [])]
    try:
        mine = json.loads((P.OUT / f"blinks_{a.who}.json").read_text())
    except OSError:
        mine = []
    worst = sorted(j["blinks"], key=lambda b: -abs(b["nod_deg"]))[:a.top]
    ranges = [(int(f0 + b["t"] * fps) - 8, int(f0 + b.get("end", b["t"] + 0.3) * fps) + 10, b) for b in worst]
    if a.frames:
        x, y = (int(v) for v in a.frames.split(","))
        ranges.append((x, y, None))
    print(json.dumps({"file": path, "metrics": j["metrics"], "failed": j["failed"], "n_blinks": len(j["blinks"]),
                      "seen": seen}))
    for x, y, b in ranges:
        print(f"\n== f{x}-{y}" + (f"  blink t={b['t']} nod_deg={b['nod_deg']}" if b else ""))
        print("   planned events near:", [(k, f, {kk: v for kk, v in ev.items() if kk != "t"}) for k, f, ev in planned
                                         if x - 15 <= f <= y + 15])
        print("   planned blinks near:", [[round(p, 1), round(q, 1)] for p, q in mine if x - 15 <= p <= y + 15])
        print("   f      pitch    yaw    roll | plan_yaw plan_pitch | closure")
        for i, f in enumerate(fr):
            if x <= f <= y and (f - x) % a.every == 0:
                (py, pp), _ = P.planned_head(a.who, f)
                c = d["closure"][i] if d.get("closure") else None
                print(f"   {f:5d} {h['pitch'][i]:7.3f} {h['yaw'][i]:7.3f} {h['roll'][i]:7.3f} | {py:7.2f} {pp:7.2f} |"
                      f" {'' if c is None else round(c, 2)}")


if __name__ == "__main__":
    main()
