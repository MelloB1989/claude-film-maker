"""Round 5b (agent-09): 400% neck crops for the orchestrator's eye on garment.neck_px, on the box (face rule: the
crops hold Host_Op; they go to private/renders/r5/review/ only). For each frame, his neck bones are projected through
the shot's camera (cam.project) and the same box is cut from this round's final and round 4's final_d, scaled 4x
(nearest, so no pixel is invented) and put side by side: left round 5, right round 4. Each row also carries the
1:1 crops' SSIM vs round 4 (path iv wears round 4's garment, so a new neckline defect, e.g. a torn skin edge that
neck_px cannot see, lowers it): a number to compare frames and fixes by, not a gate line.

    cd tools && uv run --with pillow python ../films/host-studio/reel/r5/neck_crops.py --shot S15 \
        --frames 1150,1152,1175 --final /srv/ue/reel/r5/final --r4 /srv/ue/reel/r3/final_d \
        --out /srv/ue/reel/r5/review/neck
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cast_gate import CAST, SEQ  # noqa: E402

BONES = ("neck_01", "head", "spine_05")


def name(f: int) -> str:
    return f"{f:04d}.png"


def neck_box(pts: dict, w: int, h: int) -> list:
    """A square around the neck: centred between the neck root and the chin line, half a head->chest unit wide
    each side (the collar and both sides of the neckline in frame)."""
    nu, nv = pts["neck_01"]["u"] * w, pts["neck_01"]["v"] * h
    unit = abs(pts["spine_05"]["v"] - pts["head"]["v"]) * h
    half = max(24, int(0.6 * unit))
    cx, cy = nu, nv + 0.15 * unit
    return [int(max(0, cx - half)), int(max(0, cy - half)), int(min(w, cx + half)), int(min(h, cy + half))]


def _ssim(a, b) -> float:
    """SSIM of the two 1:1 crops (qa/compare.py), a number to compare frames and fixes by: the eye decides."""
    import numpy as np
    from filmtools.unreal import qa_local
    qa_local.qa()
    im, cm = sys.modules["fmqa.image"], sys.modules["fmqa.compare"]
    A, B = (im.Image.from_array(np.asarray(x)) for x in (a, b))
    return round(cm.against_reference(A, B, min_ssim=0.0)["ssim"], 4)


def main(argv=None) -> int:
    from PIL import Image
    from filmtools.unreal import client
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", default="S15")
    ap.add_argument("--frames", default="1150,1152,1175")
    ap.add_argument("--who", default="him", choices=sorted(CAST))
    ap.add_argument("--final", required=True)
    ap.add_argument("--r4", required=True)
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lab, rows = CAST[a.who], []
    for f in (int(x) for x in a.frames.split(",")):
        r = client.op("seq.scrub", path=SEQ, frame=f)
        if not r.get("ok"):
            raise SystemExit(f"seq.scrub {f}: {r}")
        p = client.op("cam.project", camera=f"Reel_{a.shot}", points={b: f"{lab}:Body:{b}" for b in BONES})
        if not p.get("ok"):
            raise SystemExit(f"cam.project Reel_{a.shot} f{f}: {p}")
        pts = p["result"]["points"]
        im5, im4 = Image.open(Path(a.final) / name(f)).convert("RGB"), Image.open(Path(a.r4) / name(f)).convert("RGB")
        if im4.size != im5.size:
            im4 = im4.resize(im5.size, Image.LANCZOS)
        box = neck_box(pts, *im5.size)
        c5, c4 = (im.crop(box) for im in (im5, im4))
        ssim = _ssim(c5, c4)  # same garment as round 4 (path iv): a new defect at the neckline lowers it
        c5, c4 = (c.resize((c.width * a.scale, c.height * a.scale), Image.NEAREST) for c in (c5, c4))
        side = Image.new("RGB", (c5.width * 2 + 8, c5.height), (255, 0, 255))
        side.paste(c5, (0, 0))
        side.paste(c4, (c5.width + 8, 0))
        paths = {}
        for tag, im in (("r5", c5), ("r4", c4), ("r5_vs_r4", side)):
            paths[tag] = str(out / f"{a.shot}_f{f}_neck_{a.scale * 100}pct_{tag}.png")
            im.save(paths[tag])
        rows.append({"frame": f, "box_px": box, "ssim_vs_r4": ssim, **paths})
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
