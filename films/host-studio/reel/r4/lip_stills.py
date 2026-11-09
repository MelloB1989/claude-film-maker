"""Round 4 (agent-09): gate a's lips on stills before a re-render. Per spoken line, WIN consecutive frames on the line and
WIN in the speaker's longest silence in that shot (LIPS_EDGE clear of their lines), through the shot's Reel_ camera, one
dir per shot ({frame:04d}.png). cast_gate.py frames reads any frame dir, so the same measure (and the same 2.0 line)
scores them. With Host_Op on the level the stills are box-only; only the JSON numbers leave.

    render (the editor; agent-06):
      cd tools && uv run python ../films/host-studio/reel/r4/lip_stills.py --out /srv/ue/reel/r4/lips [--mode mrq]
    then, as in the gate (mouth re-projects the lips on the current animation):
      uv run python ../films/host-studio/reel/cast_gate.py mouth --out /srv/ue/reel/r4/lips/mouth.json
      uv run --with pillow --with numpy python ../films/host-studio/reel/cast_gate.py frames /srv/ue/reel/r4/lips \\
          --mouth /srv/ue/reel/r4/lips/mouth.json --out /srv/ue/reel/r4/lips/_score

--mode stills (default): seq.stills, the viewport (seconds a frame); --mode mrq: view.still mrq per frame (the render's
look, slower). --dry-run prints the windows only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cast_gate as G  # noqa: E402
from shots import SHOTS  # noqa: E402

SEQ = G.SEQ
WIN = 24


def windows(win: int = WIN) -> dict:
    """{shot: {"frames": sorted frames, "lines": {line: [a, b]}, "silence": {who: [a, b]}}}."""
    out = {}
    for sid, who in G.speakers():
        s = next(x for x in SHOTS if x.id == sid)
        near = {f for _, a, b in G.windows(who) for f in range(a - G.LIPS_EDGE, b + G.LIPS_EDGE)}
        run, best = [], []
        for f in range(s.start + 1, s.end):
            run = run + [f] if f not in near else []
            if len(run) > len(best):
                best = list(run)
        d = out.setdefault(sid, {"frames": set(), "lines": {}, "silence": {}})
        if best:
            mid = len(best) // 2
            sl = best[max(0, mid - win // 2): max(0, mid - win // 2) + win]
            d["silence"][who] = [sl[0], sl[-1] + 1]
            d["frames"] |= set(range(sl[0] - 1, sl[-1] + 1))  # f-1 too: the measure is frame to frame
        for k, a, b in G.windows(who):
            a, b = max(a, s.start + 1), min(b, s.end)
            if a >= b:
                continue
            lo = a + max(0, (b - a - win) // 2)
            hi = min(b, lo + win)
            d["lines"][k] = [lo, hi]
            d["frames"] |= set(range(lo - 1, hi))
    for d in out.values():
        d["frames"] = sorted(d["frames"])
    return out


def render(out: str, mode: str, w: dict) -> dict:
    from filmtools.unreal import client

    def ok(res):
        if not res.get("ok"):
            raise SystemExit(res.get("stdout", "") + res.get("error", ""))
        return res.get("result")
    rep = {}
    for sid, d in w.items():
        cam, od = f"Reel_{sid}", f"{out}/{sid}"
        if mode == "mrq":
            for f in d["frames"]:
                ok(client.op("view.still", out=f"{od}/{f:04d}.png", sequence=SEQ, frame=f, camera=cam,
                             width_px=960, height_px=540, mode="mrq", level="/Game/Studio/Studio"))
        else:
            ok(client.op("seq.stills", path=SEQ, frames=d["frames"], camera=cam, out_dir=od, width=960, height=540))
        rep[sid] = {"n": len(d["frames"]), "lines": d["lines"], "silence": d["silence"]}
        print(sid, len(d["frames"]), flush=True)
    return rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="stills", choices=["stills", "mrq"])
    ap.add_argument("--win", type=int, default=WIN)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    w = windows(a.win)
    if a.dry_run:
        print(json.dumps({k: {**v, "frames": len(v["frames"])} for k, v in w.items()}, indent=1))
        return
    print(json.dumps(render(a.out, a.mode, w), indent=1))


if __name__ == "__main__":
    main()
