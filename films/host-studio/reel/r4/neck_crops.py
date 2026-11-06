"""Round 4 (agent-02): close-up crops of his neck and upper chest at given frames, side by side: the pre-check render,
the ballooned cast_op5 render and the new state (a clip_pass.py dir's <shot>_<frame>_final.png). The crop box comes
from the new pass's tee layer (its top 45%, widened): every column is the same camera, so the same normalized box.
On the box only (face rule):
    ~/.local/bin/uv run -q --with pillow python neck_crops.py --pre <dir of NNNN.jpeg> --mid <dir of NNNN.jpeg> \
        --new <clip_pass dir> --frames Reel_S15:1130,Reel_S17:1410 --out <jpg>
"""
import argparse
import array
import json
import os

from PIL import Image, ImageDraw

EMPTY = 1.0e7
CELL = 520


def tee_box(path):
    with open(path, "rb") as fh:
        n = int.from_bytes(fh.read(4), "little")
        head = json.loads(fh.read(n))
        W, H = head["w"], head["h"]
        for name in head["layers"]:
            x = array.array("f")
            x.fromfile(fh, W * H)
            if name == "tee":
                pts = [(i % W, i // W) for i, v in enumerate(x) if v < EMPTY]
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
                h = y1 - y0
                top = y0 + 0.45 * h
                cx, half = (x0 + x1) / 2, max(x1 - x0, top - y0) * 0.55
                y_a = y0 - 0.15 * h
                return ((cx - half) / W, y_a / H, (cx + half) / W, (y_a + 2 * half) / H)
    raise RuntimeError(f"no tee layer in {path}")


def crop(path, box):
    if not path or not os.path.exists(path):
        return Image.new("RGB", (CELL, CELL), (40, 40, 40))
    im = Image.open(path).convert("RGB")
    w, h = im.size
    x0, y0, x1, y1 = box
    s = max((x1 - x0) * w, (y1 - y0) * h)
    cx, cy = (x0 + x1) / 2 * w, (y0 + y1) / 2 * h
    a = (max(0, cx - s / 2), max(0, cy - s / 2), min(w, cx + s / 2), min(h, cy + s / 2))
    return im.crop(tuple(int(v) for v in a)).resize((CELL, CELL), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", required=True)
    ap.add_argument("--mid", default="")
    ap.add_argument("--new", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = [(s.split(":")[0], int(s.split(":")[1])) for s in a.frames.split(",")]
    cols = [("pre-check", a.pre), ("cast_op5 (ballooned)", a.mid), ("new", a.new)]
    head = 24
    sheet = Image.new("RGB", (len(cols) * CELL + 150, head + len(rows) * (CELL + 4)), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    for i, (t, _) in enumerate(cols):
        d.text((150 + i * CELL + 8, 6), t, fill=(230, 230, 230))
    for r, (shot, f) in enumerate(rows):
        y = head + r * (CELL + 4)
        base = os.path.join(a.new, f"{shot}_{f:04d}")
        box = tee_box(base + "_depth.bin")
        d.text((8, y + 8), f"{shot}\nf{f}", fill=(230, 230, 230))
        paths = [os.path.join(a.pre, f"{f:04d}.jpeg"), os.path.join(a.mid, f"{f:04d}.jpeg") if a.mid else "",
                 base + "_final.png"]
        for k, p in enumerate(paths):
            sheet.paste(crop(p, box), (150 + k * CELL, y))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sheet.save(a.out, "JPEG", quality=88)
    print(json.dumps({"out": a.out, "bytes": os.path.getsize(a.out), "rows": len(rows)}))


if __name__ == "__main__":
    main()
