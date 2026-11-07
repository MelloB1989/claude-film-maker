"""Re-judge a qa.clip out_dir's depth layers (<shot>_<frame>_depth.bin) with the current fmqa rules and print the neck
numbers per frame: the old rim rule (neck_px) and the round-6 visible rule (neck_visible: islands + tongues) for
several tongue_cm, plus the largest tongue. Numbers only (the depth files hold his face: run it ON THE BOX).

    cd <tree>/tools && uv run python -m filmtools.unreal.neckscan /srv/ue/reel/r6/garment/clipr6c1 \
        /srv/ue/reel/r6/garment/clipr6c3 --tongue 2,3,4,5,6
"""
from __future__ import annotations

import argparse
import array
import json
import re
import sys
from pathlib import Path

from .qa_local import qa


def read_depth(path: Path) -> tuple:
    """(w, h, fov, {layer: list}) from qa.clip's _depth.bin (ops/garment.py write_depth's format)."""
    with open(path, "rb") as fh:
        n = int.from_bytes(fh.read(4), "little")
        head = json.loads(fh.read(n))
        out = {}
        for name in head["layers"]:
            x = array.array("f")
            x.fromfile(fh, head["w"] * head["h"])
            out[name] = list(x)
    return head["w"], head["h"], head["fov"], out


def scan(d: Path, tongues: list) -> dict:
    qa()
    clip = sys.modules["fmqa.clip"]
    rows = {}
    for p in sorted(d.glob("*_depth.bin")):
        m = re.match(r"(.+)_(\d+)_depth\.bin$", p.name)
        if not m:
            continue
        w, h, fov, L = read_depth(p)
        row = {}
        for t in tongues:
            fr = clip.judge_frame(L, w, h, fov, tongue_cm=t)
            nv, np_ = fr.get("neck_visible"), fr.get("neck_px")
            if nv is None:
                continue
            row.setdefault("neck_px", np_["px"])
            row.setdefault("face_tee_px", (fr.get("Face>tee") or {}).get("px"))
            row.setdefault("islands", [nv["islands"], nv["island_px"]])
            row.setdefault("max_tongue_cm", nv["max_tongue_cm"])
            row[f"visible@{t:g}"] = nv["px"]
            if nv["clusters"]:
                row.setdefault("first_cluster", nv["clusters"][0])
        rows[f"{m.group(1)}@{int(m.group(2))}"] = row
    worst = {}
    for k, r in rows.items():
        for key, v in r.items():
            if isinstance(v, (int, float)) and (key not in worst or v > worst[key][0]):
                worst[key] = (v, k)
    return {"dir": str(d), "frames": len(rows), "worst": worst, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--tongue", default="2,3,4,5,6", help="tongue_cm values to try")
    ap.add_argument("--rows", action="store_true", help="print every frame, not only the worst")
    a = ap.parse_args(argv)
    tongues = [float(x) for x in a.tongue.split(",")]
    for d in a.dirs:
        r = scan(Path(d), tongues)
        if not a.rows:
            r.pop("rows")
        print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
