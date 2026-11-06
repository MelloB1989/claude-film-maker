r"""Round 5 (T3b, agent-08): write the cloth items of agent-09's gate v2 file from the GPU session's outputs.

Runs ON THE BOX (face rule: the frames and masks never leave it), from the box tree, with plain Python 3.11+:

    python films/host-studio/reel/r5/cloth_gate.py \
        --qa /srv/ue/reel/r5/cloth/qa \                     # qa.cloth JSONs: <shot>_<start>-<end>.json (film-ue --json output)
        --r5 '/srv/ue/reel/r5/final/{frame:04d}.png' \     # round-5 1080p frames
        --r4 '/srv/ue/reel/r4/final_d/{frame:04d}.png' \   # round-4 finals, same frames
        --mask '/srv/ue/reel/r5/garment/clip/Reel_{shot}_{frame:04d}_tee.png' \   # agent-02 qa.clip layer_masks=true
        --frames S13:1030,1050 S15:1100,1150 \
        --out /srv/ue/reel/r5/cloth/gate_cloth.json

Items (fmbridge/qa/cloth.py gate_numbers):
- garment.cloth_alive >= 0.30 cm: the smallest hem motion over the qa.cloth runs (round 4: 0.0, no clothing data);
- garment.cloth_sound == 1: no explosion, NaN, spike, cold start or missing sim in any run (round 4: 0);
- garment.cloth_detail_ratio >= 1.25: min over frames of fold_detail(r5) / fold_detail(r4) on his tee's chest band,
  the SAME r5 mask for both (same frame and camera; the round-4 tee was within 2% of its silhouette). Round 4 = 1.0.
The mask (480x270, 255 = tee alone) is scaled to the frame by nearest neighbour.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.environ.get("FM_TREE") or os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))   # the box tree (core merged)
sys.path.insert(0, os.path.join(TREE, "unreal", "fmbridge"))
from qa import cloth as qcloth  # noqa: E402
from qa import image as qimage  # noqa: E402


def scaled_mask(mask_img, w: int, h: int) -> list:
    g = qimage.luma8(mask_img)
    mw, mh = mask_img.w, mask_img.h
    return [1 if g[(y * mh // h) * mw + (x * mw // w)] > 127 else 0 for y in range(h) for x in range(w)]


def detail(frame_png: str, mask: list) -> float | None:
    if not os.path.exists(frame_png):
        return None
    img = qimage.read(frame_png)
    lum = list(qimage.luminance(img))
    r = qcloth.fold_detail(lum, mask, img.w, img.h)
    return r["detail"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qa", required=True, help="dir of qa.cloth JSON results (one per shot range)")
    ap.add_argument("--r5", required=True, help="round-5 frame path pattern with {frame}")
    ap.add_argument("--r4", required=True, help="round-4 frame path pattern with {frame}")
    ap.add_argument("--mask", required=True, help="tee mask pattern with {shot} and {frame}")
    ap.add_argument("--frames", nargs="+", required=True, help="SHOT:f1,f2,... (shot id without the Reel_ prefix)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    cloth = {}
    for p in sorted(glob.glob(os.path.join(a.qa, "*.json"))):
        with open(p) as f:
            r = json.load(f)
        cloth[os.path.splitext(os.path.basename(p))[0]] = r.get("result", r)
    pairs = {}
    for spec in a.frames:
        shot, fs = spec.split(":")
        for fr in (int(x) for x in fs.split(",")):
            where = f"{shot} f{fr}"
            mp = a.mask.format(shot=shot, frame=fr)
            r5 = a.r5.format(frame=fr, shot=shot)
            if not os.path.exists(mp) or not os.path.exists(r5):
                pairs[where] = (None, None)
                continue
            img = qimage.read(r5)
            m = scaled_mask(qimage.read(mp), img.w, img.h)
            pairs[where] = (detail(r5, m), detail(a.r4.format(frame=fr, shot=shot), m))
    out = qcloth.gate_numbers(cloth, pairs)
    out["detail_pairs"] = {k: list(v) for k, v in pairs.items()}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out["gate"], indent=1))
    return 0 if all("error" not in v for v in out["gate"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
