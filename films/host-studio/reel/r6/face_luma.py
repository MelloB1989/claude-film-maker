"""Round 6 (agent-06): shot.face_luma_ratio, his face-box mean luma in a frame over the same frame in reference dirs
(round 4's r3/final_d, round 5b's final). Runs on the box (face rule: it reads presenter frames; it prints numbers
only). Each image gets its OWN face box (agent-09: a ratio must move only with light, not with pose): the CURRENT
editor pose (cam.project of the eyes through the shot camera) gives a search window, mediapipe's face landmarker finds
the face in each image inside it (the one nearest the projected eyes), and the box is its landmarks' bounding box
shrunk 15 % (skin, not hair or background). No face found (e.g. a face too dark to detect) -> the projected box,
"detected": false. Needs `uv run --with pillow --with mediapipe==0.10.21`.

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


def detect_box(lm, im, near: list) -> list | None:
    """The face landmarker's box (px) for the face nearest the centre of `near`, searched in `near` grown 2x."""
    import mediapipe as mp
    import numpy as np
    W, H = im.size
    cx, cy = (near[0] + near[2]) / 2, (near[1] + near[3]) / 2
    half = max(near[2] - near[0], near[3] - near[1])
    win = [int(max(0, cx - half)), int(max(0, cy - half)), int(min(W, cx + half)), int(min(H, cy + half))]
    crop = im.convert("RGB").crop(win)
    res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(crop)))
    best = None
    for face in res.face_landmarks or []:
        xs = [win[0] + q.x * crop.width for q in face]
        ys = [win[1] + q.y * crop.height for q in face]
        b = [min(xs), min(ys), max(xs), max(ys)]
        d = ((b[0] + b[2]) / 2 - cx) ** 2 + ((b[1] + b[3]) / 2 - cy) ** 2
        if best is None or d < best[0]:
            best = (d, b)
    if best is None:
        return None
    b = best[1]
    sx, sy = 0.15 * (b[2] - b[0]), 0.15 * (b[3] - b[1])
    return [int(b[0] + sx), int(b[1] + sy), int(b[2] - sx), int(b[3] - sy)]


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
    from mediapipe.tasks.python import BaseOptions, vision
    from filmtools.unreal.qa_head import _model_path
    lab, rows = CAST[a.who], []
    refs = dict(r.split("=", 1) for r in a.ref)
    lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=_model_path()), num_faces=2))
    for f in (int(x) for x in a.frames.split(",")):
        client.op("seq.scrub", path=SEQ, frame=f + 1)
        client.op("seq.scrub", path=SEQ, frame=f)
        p = client.op("cam.project", camera=f"Reel_{a.shot}", points={e: f"{lab}:Face:{e}" for e in EYES})
        if not p.get("ok"):
            raise SystemExit(f"cam.project Reel_{a.shot} f{f}: {p}")
        im = Image.open(Path(a.img) / f"{f:04d}.png")
        near = face_box(p["result"]["points"], *im.size)
        box = detect_box(lm, im, near)
        row = {"shot": a.shot, "frame": f, "box_px": box or near, "detected": box is not None,
               "luma": round(luma(im, box or near), 2)}
        for n, d in refs.items():
            q = Path(d) / f"{f:04d}.png"
            if q.exists():
                r = Image.open(q)
                r = r.resize(im.size) if r.size != im.size else r
                rb = detect_box(lm, r, near)
                row[f"box_{n}"], row[f"detected_{n}"] = rb or near, rb is not None
                row[f"luma_{n}"] = round(luma(r, rb or near), 2)
                row[f"ratio_vs_{n}"] = round(row["luma"] / max(1e-6, row[f"luma_{n}"]), 3)
        rows.append(row)
    print(json.dumps(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
