"""Round 5 (T4): the `film-qa hair` spec for rendered frames, made on the box from the engine's numbers only (no
frame leaves the box: face rule). For each presenter shot pair at a cut, it scrubs to the frames next to the cut,
projects the character's head and upper-chest bones through that shot's camera (cam.project) and writes:
- `anchors`: {frame: [head_v, chest_v]} so reach is in head units (zoom-free);
- `boxes`: {shot: [x0, y0, x1, y1]} the head-and-shoulders region the dark-hair matte is read in.

    cd tools && uv run python ../films/host-studio/reel/r5/hair_spec.py --who her --frames-dir /srv/ue/reel/r3/final_d \
        --cuts S17,S18 --out /srv/ue/reel/r5/hair/her_spec.json
    uv run python -m filmtools.unreal.qa_local hair /srv/ue/reel/r5/hair/her_spec.json --out /srv/ue/reel/r5/hair/her.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cast_gate import CAST, SEQ  # noqa: E402
from shots import SHOTS  # noqa: E402

K = 4          # frames per side of each cut (qa/hair.py THRESHOLDS k)
# cuts whose camera holds (shots.py: S18 is "locked off on the end of S17"): the only ones `film-qa hair`'s cut pop
# reads; across a camera change the head box changes by design and would read as a pop
HELD_CUTS = (("S17", "S18"),)
BONES = ("head", "spine_05")


def box_from(head_v: float, chest_v: float, head_u: float, aspect: float = 16 / 9) -> list:
    """Head-and-shoulders box from the projected bones: a unit = head->chest in frame heights; the hair can fall
    ~2 units below the head and spread ~1.2 units each side (in frame widths: / aspect)."""
    unit = abs(chest_v - head_v)
    half_w = 1.2 * unit / aspect
    return [round(max(0.0, head_u - half_w), 4), round(max(0.0, head_v - 1.0 * unit), 4),
            round(min(1.0, head_u + half_w), 4), round(min(1.0, head_v + 2.2 * unit), 4)]


def build(who: str, frames_dir: str, cut_ids: list, k: int = K) -> dict:
    from filmtools.unreal import client
    lab = CAST[who]
    shots = [s for s in SHOTS if s.id in cut_ids]
    cuts = [[s.id, s.start, s.end] for s in shots]
    anchors, boxes = {}, {}
    for i, s in enumerate(shots):
        frames = []
        if i > 0:
            frames += list(range(s.start, s.start + k))
        if i + 1 < len(shots):
            frames += list(range(s.end - k, s.end))
        for f in frames:
            r = client.op("seq.scrub", path=SEQ, frame=f)
            if not r.get("ok"):
                raise SystemExit(f"seq.scrub {f}: {r}")
            p = client.op("cam.project", camera=f"Reel_{s.id}", points={b: f"{lab}:Body:{b}" for b in BONES})
            if not p.get("ok"):
                raise SystemExit(f"cam.project Reel_{s.id} f{f}: {p}")
            pts = p["result"]["points"]
            if not all(pts[b]["depth"] > 0 for b in BONES):
                continue
            anchors[str(f)] = [pts["head"]["v"], pts["spine_05"]["v"]]
            b = box_from(pts["head"]["v"], pts["spine_05"]["v"], pts["head"]["u"])
            old = boxes.get(s.id)
            boxes[s.id] = b if old is None else [min(old[0], b[0]), min(old[1], b[1]), max(old[2], b[2]),
                                                 max(old[3], b[3])]
    pairs = {(a[0], b[0]) for a, b in zip(cuts, cuts[1:])}
    return {"character": lab, "cuts": cuts, "frames_glob": str(Path(frames_dir) / "*.png"), "boxes": boxes,
            "anchors": anchors, "max_luma": 40.0, "thresholds": {"k": k},
            "pop_cuts": [list(c) for c in HELD_CUTS if c in pairs]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", choices=sorted(CAST), default="her")
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--cuts", default="S17,S18", help="shot ids in order (consecutive shots)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    spec = build(a.who, a.frames_dir, a.cuts.split(","))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec.items() if k != "anchors"}, indent=1))


if __name__ == "__main__":
    main()
