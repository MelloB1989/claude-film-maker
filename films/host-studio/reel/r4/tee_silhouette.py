"""Round 4 (agent-02): his tee's screen silhouette, per frame, vs a reference pass (the orchestrator's gate after the
neckline term ballooned it: within ~2% of the pre-check's in S15/S17/S18). Reads two clip_pass.py dirs' depth layers
(<shot>_<frame>_depth.bin, the 'tee' layer alone): pixels his tee covers at the same frame and camera. Off the editor.
    python3 tee_silhouette.py <reference dir> <dir> [--limit 0.02] [--shots Reel_S15,Reel_S17,Reel_S18]
Prints JSON {frames: {shot@frame: {ref_px, px, growth}}, worst, pass}; exit 0 on pass, 1 on fail.
"""
import argparse
import array
import glob
import json
import os
import sys

EMPTY = 1.0e7


def tee_px(path):
    with open(path, "rb") as fh:
        n = int.from_bytes(fh.read(4), "little")
        head = json.loads(fh.read(n))
        for name in head["layers"]:
            x = array.array("f")
            x.fromfile(fh, head["w"] * head["h"])
            if name == "tee":
                return sum(1 for v in x if v < EMPTY)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("dir")
    ap.add_argument("--limit", type=float, default=0.02)
    ap.add_argument("--shots", default="Reel_S15,Reel_S17,Reel_S18")
    a = ap.parse_args()
    shots = set(a.shots.split(","))
    out, worst = {}, (0.0, None)
    for p in sorted(glob.glob(os.path.join(a.dir, "*_depth.bin"))):
        base = os.path.basename(p)[:-len("_depth.bin")]
        shot, f = base.rsplit("_", 1)
        r = os.path.join(a.ref, base + "_depth.bin")
        if shot not in shots or not os.path.exists(r):
            continue
        rp, pp = tee_px(r), tee_px(p)
        g = (pp - rp) / max(1, rp)
        out[f"{shot}@{int(f)}"] = {"ref_px": rp, "px": pp, "growth": round(g, 4)}
        if abs(g) >= abs(worst[0]):
            worst = (g, f"{shot}@{int(f)}")
    rep = {"frames": out, "worst": {"growth": round(worst[0], 4), "at": worst[1]}, "limit": a.limit,
           "pass": bool(out) and abs(worst[0]) <= a.limit}
    print(json.dumps(rep, indent=1))
    sys.exit(0 if rep["pass"] else 1)


if __name__ == "__main__":
    main()
