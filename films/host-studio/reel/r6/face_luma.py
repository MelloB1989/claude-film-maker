"""Round 6 (agent-06): shot.face_luma_ratio, his face-box mean luma in a frame over the same frame in reference dirs
(round 4's r3/final_d, round 5b's final). Runs on the box (face rule: it reads presenter frames; it prints numbers
only). The box comes from the CURRENT editor pose (cam.project of his eyes through the shot camera): a square
centred just below the eyes, 2.4 inter-eye distances wide, so it holds the face, not hair or collar.

    cd tools && uv run --with pillow python ../films/host-studio/reel/r6/face_luma.py --shot S15 --frames 1128 \
        --img /srv/ue/reel/r5/stills/r6s1 --ref r4=/srv/ue/reel/r3/final_d --ref r5b=/srv/ue/reel/r5/final
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cast_gate import CAST, SEQ  # noqa: E402

EYES = ("FACIAL_L_Eye", "FACIAL_R_Eye")


def face_box(pts: dict, w: int, h: int) -> list:
    (lu, lv), (ru, rv) = ((pts[e]["u"] * w, pts[e]["v"] * h) for e in EYES)
    d = max(8.0, ((lu - ru) ** 2 + (lv - rv) ** 2) ** 0.5)
    cx, cy, half = (lu + ru) / 2, (lv + rv) / 2 + 0.6 * d, 1.2 * d
    return [int(max(0, cx - half)), int(max(0, cy - half)), int(min(w, cx + half)), int(min(h, cy + half))]


def luma(im, box) -> float:
    c = im.convert("RGB").crop(box)
    px = list(c.getdata())
    return sum(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in px) / max(1, len(px))


def main(argv=None) -> int:
    from PIL import Image
    from filmtools.unreal import client
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--who", default="him", choices=sorted(CAST))
    ap.add_argument("--img", required=True, help="dir of the frames to judge (NNNN.png)")
    ap.add_argument("--ref", action="append", default=[], help="name=dir, repeatable")
    a = ap.parse_args(argv)
    lab, rows = CAST[a.who], []
    refs = dict(r.split("=", 1) for r in a.ref)
    for f in (int(x) for x in a.frames.split(",")):
        client.op("seq.scrub", path=SEQ, frame=f + 1)
        client.op("seq.scrub", path=SEQ, frame=f)
        p = client.op("cam.project", camera=f"Reel_{a.shot}", points={e: f"{lab}:Face:{e}" for e in EYES})
        if not p.get("ok"):
            raise SystemExit(f"cam.project Reel_{a.shot} f{f}: {p}")
        im = Image.open(Path(a.img) / f"{f:04d}.png")
        box = face_box(p["result"]["points"], *im.size)
        row = {"shot": a.shot, "frame": f, "box_px": box, "luma": round(luma(im, box), 2)}
        for n, d in refs.items():
            q = Path(d) / f"{f:04d}.png"
            if q.exists():
                r = Image.open(q)
                r = r.resize(im.size) if r.size != im.size else r
                row[f"luma_{n}"] = round(luma(r, box), 2)
                row[f"ratio_vs_{n}"] = round(row["luma"] / max(1e-6, row[f"luma_{n}"]), 3)
        rows.append(row)
    print(json.dumps(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
