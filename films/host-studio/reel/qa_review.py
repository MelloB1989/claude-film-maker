"""Round 3 QA of rendered reel frames (agent-09): contact sheets per shot, frame-to-frame pops, before/after pairs.
Runs anywhere with Pillow and numpy on frames pulled from the box (`film-ue pull-dir`); frames are found recursively
and numbered by the master frame at the end of their name (S13 = 0960..1079, any extension MRQ wrote; -0004..-0001,
the pre-roll before frame 0, are skipped).

    python reel/qa_review.py sheets FRAMES --out DIR [--per 8] [--width 320]     a sheet per shot + reel.jpg
    python reel/qa_review.py pops FRAMES [--shots S17] [--box 0.5,0,1,1] [--k 4]  jumps between frames, per shot
    python reel/qa_review.py pair BEFORE AFTER --out DIR [--frames 1400:1440] [--every 4] [--box ...]

`pops` measures the mean absolute change of each frame from the one before (grey, 1/4 size, inside `--box`, a
fraction of the frame x0,y0,x1,y1) and flags a frame whose change is over `--k` times its shot's median (and over
`--floor` grey levels, so a still shot's noise is not a pop): a groom LOD
switch, a sim reset or a cloth snap shows as one spike in an otherwise smooth camera move. Shot boundaries (cuts) are
not compared. `pair` writes before|after side by side for every `--every`th frame and both pop series, so a fix is
shown on the frames around the problem.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from shots import SHOTS  # noqa: E402

EXTS = {".png", ".jpg", ".jpeg", ".exr", ".bmp"}


def frames(root: str) -> dict:
    """{master frame: path} under root (the last run of 4+ digits in the file name is the frame)."""
    out = {}
    for p in Path(root).rglob("*"):
        m = re.search(r"(-?)(\d{4,})(?!.*\d)", p.stem)
        if p.suffix.lower() in EXTS and m and not m.group(1):  # -0001: a pre-roll frame before the sequence's 0
            out[int(m.group(2))] = p
    return out


def shot_of(f: int):
    return next((s for s in SHOTS if s.start <= f < s.end), None)


def _label(im: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 * len(text) + 8, 16], fill=(0, 0, 0))
    d.text((4, 2), text, fill=(255, 255, 255))
    return im


def _grid(cells: list, cols: int, title: str = "") -> Image.Image:
    w, h = cells[0].size
    rows = (len(cells) + cols - 1) // cols
    top = 22 if title else 0
    sheet = Image.new("RGB", (cols * w + (cols + 1) * 4, rows * h + (rows + 1) * 4 + top), (24, 24, 24))
    if title:
        ImageDraw.Draw(sheet).text((6, 5), title, fill=(230, 230, 230))
    for k, c in enumerate(cells):
        sheet.paste(c, (4 + (k % cols) * (w + 4), top + 4 + (k // cols) * (h + 4)))
    return sheet


def _thumb(p: Path, width: int, text: str) -> Image.Image:
    im = Image.open(p).convert("RGB")
    im = im.resize((width, round(width * im.height / im.width)), Image.LANCZOS)
    return _label(im, text)


def sheets(root: str, out: str, per: int = 8, width: int = 320) -> dict:
    fr, o = frames(root), Path(out)
    o.mkdir(parents=True, exist_ok=True)
    made, overview, missing = {}, [], {}
    for s in SHOTS:
        have = sorted(f for f in fr if s.start <= f < s.end)
        missing[s.id] = (s.end - s.start) - len(have)
        if not have:
            continue
        pick = sorted({have[round(i * (len(have) - 1) / max(1, per - 1))] for i in range(per)})
        cells = [_thumb(fr[f], width, f"{s.id} f{f}") for f in pick]
        p = o / f"{s.id}.jpg"
        _grid(cells, 4, f"{s.id} {s.title}: f{s.start}-{s.end - 1}, {len(have)} frames").save(p, quality=88)
        made[s.id] = str(p)
        overview += [_thumb(fr[f], 240, f"{s.id} f{f}") for f in (have[0], have[len(have) // 2], have[-1])]
    if overview:
        _grid(overview, 6, "reel: first, middle, last frame of each shot").save(o / "reel.jpg", quality=88)
        made["reel"] = str(o / "reel.jpg")
    return {"sheets": made, "missing": {k: v for k, v in missing.items() if v}}


def _grey(p: Path, box) -> np.ndarray:
    im = Image.open(p).convert("L")
    w, h = im.size
    im = im.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)))
    return np.asarray(im.resize((max(1, im.width // 4), max(1, im.height // 4)), Image.BILINEAR), np.float32)


def pops(root: str, shots=None, box=(0, 0, 1, 1), k: float = 4.0, lo: int | None = None, hi: int | None = None,
         floor: float = 1.0) -> dict:
    fr = frames(root)
    res = {}
    for s in SHOTS:
        if shots and s.id not in shots:
            continue
        have = [f for f in sorted(fr) if s.start <= f < s.end and (lo is None or f >= lo) and (hi is None or f < hi)]
        series, prev = [], None
        for f in have:
            g = _grey(fr[f], box)
            if prev is not None and prev[0] == f - 1:
                series.append([f, round(float(np.mean(np.abs(g - prev[1]))), 3)])
            prev = (f, g)
        if not series:
            continue
        med = float(np.median([d for _, d in series])) or 1e-3
        flagged = [[f, d, round(d / med, 1)] for f, d in series if d > max(k * med, floor)]
        res[s.id] = {"frames": len(have), "median": round(med, 3), "max": max(series, key=lambda x: x[1]),
                     "flagged": flagged, "series": series}
    return res


def pair(before: str, after: str, out: str, lo: int, hi: int, every: int = 4, box=(0, 0, 1, 1)) -> dict:
    fb, fa, o = frames(before), frames(after), Path(out)
    o.mkdir(parents=True, exist_ok=True)
    both = [f for f in range(lo, hi) if f in fb and f in fa]
    made = []
    for f in both[::every] + ([both[-1]] if both and (len(both) - 1) % every else []):
        a = _thumb(fb[f], 640, f"BEFORE f{f}")
        b = _thumb(fa[f], 640, f"AFTER f{f}")
        p = o / f"pair_{f:04d}.jpg"
        _grid([a, b], 2).save(p, quality=90)
        made.append(str(p))
    rb = pops(before, box=box, lo=lo, hi=hi)
    ra = pops(after, box=box, lo=lo, hi=hi)
    summary = {"pairs": made, "frames": [both[0], both[-1]] if both else None,
               "before": {s: {k: v for k, v in r.items() if k != "series"} for s, r in rb.items()},
               "after": {s: {k: v for k, v in r.items() if k != "series"} for s, r in ra.items()},
               "series": {"before": {s: r["series"] for s, r in rb.items()},
                          "after": {s: r["series"] for s, r in ra.items()}}}
    (o / "pair.json").write_text(json.dumps(summary, indent=1))
    return {k: v for k, v in summary.items() if k != "series"}


def _box(s: str):
    v = tuple(float(x) for x in s.split(","))
    if len(v) != 4:
        raise SystemExit("--box x0,y0,x1,y1 as fractions of the frame")
    return v


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("sheets")
    a.add_argument("root")
    a.add_argument("--out", required=True)
    a.add_argument("--per", type=int, default=8)
    a.add_argument("--width", type=int, default=320)
    b = sub.add_parser("pops")
    b.add_argument("root")
    b.add_argument("--shots", default="")
    b.add_argument("--box", type=_box, default=(0, 0, 1, 1))
    b.add_argument("--k", type=float, default=4.0)
    b.add_argument("--floor", type=float, default=1.0)
    c = sub.add_parser("pair")
    c.add_argument("before")
    c.add_argument("after")
    c.add_argument("--out", required=True)
    c.add_argument("--frames", default="1400:1440")
    c.add_argument("--every", type=int, default=4)
    c.add_argument("--box", type=_box, default=(0, 0, 1, 1))
    x = ap.parse_args()
    if x.cmd == "sheets":
        r = sheets(x.root, x.out, x.per, x.width)
    elif x.cmd == "pops":
        r = pops(x.root, set(x.shots.split(",")) if x.shots else None, x.box, x.k, floor=x.floor)
        r = {s: {k: v for k, v in d.items() if k != "series"} for s, d in r.items()}
    else:
        lo, hi = (int(v) for v in x.frames.split(":"))
        r = pair(x.before, x.after, x.out, lo, hi, x.every, x.box)
    print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
