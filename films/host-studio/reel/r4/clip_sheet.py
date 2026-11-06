"""Round 4: one before/after crop sheet of the clipping clip_pass.py found (for the orchestrator's eye; face data, so
on the box only, then to private/renders/r4/review/ with KMS). Run ON THE BOX:

    uv run --with pillow python films/host-studio/reel/r4/clip_sheet.py \
        /srv/ue/reel/r4/clip/Host_before /srv/ue/reel/r4/clip/Host_after --out /srv/ue/reel/r4/review/clip_host.jpg

One row per place that clipped BEFORE (the biggest cluster of each pair in each shot, then any new one AFTER),
cropped round the cluster from the same shot and frame: before (scene, mask), after (scene, mask), with the numbers.
Mask colours: body red, face orange, tee/top green, trousers blue, shoes yellow, clipping magenta. Kept under ~3 MB.
"""
import argparse
import json
import os

from PIL import Image, ImageDraw

CELL = 300


def load(d):
    return json.load(open(os.path.join(d, "clip.json")))


def places(rep, rows):
    """(shot, frame, pair, cluster) of the biggest cluster per (shot, pair)."""
    best = {}
    for shot, per in rep["shots"].items():
        for f, fr in (per.items() if isinstance(per, dict) else ()):
            for pair, v in fr.items():
                if not isinstance(v, dict) or not v.get("clusters"):
                    continue
                c = v["clusters"][0]
                k = (shot, pair)
                if k not in best or c["px"] > best[k][3]["px"]:
                    best[k] = (shot, f, pair, c)
    return sorted(best.values(), key=lambda p: -p[3]["px"])[:rows]


def crop(path, box, pad=0.06):
    if not os.path.exists(path):
        return Image.new("RGB", (CELL, CELL), (40, 40, 40))
    im = Image.open(path).convert("RGB")
    w, h = im.size
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2 * w, (y0 + y1) / 2 * h
    s = max((x1 - x0) * w, (y1 - y0) * h, 0.12 * h) + 2 * pad * h
    a = (max(0, cx - s / 2), max(0, cy - s / 2), min(w, cx + s / 2), min(h, cy + s / 2))
    return im.crop(tuple(int(v) for v in a)).resize((CELL, CELL), Image.LANCZOS)


def num(rep, shot, f, pair):
    v = rep["shots"].get(shot, {}).get(str(f), {}).get(pair) if isinstance(rep["shots"].get(shot), dict) else None
    return f"{100 * v['fraction']:.2f}% ({v['px']} px)" if isinstance(v, dict) else "-"


def diag(a):
    rep = load(a.before)
    cols = ("final", "mask", "nobody", "nogarment", "albedo_tee", "albedo_Trousers")
    rows = []
    for shot, per in rep["shots"].items():
        for f in (per if isinstance(per, dict) else {}):
            if os.path.exists(os.path.join(a.before, f"{shot}_{int(f):04d}_nobody.png")):
                fr = per[f]
                for pair, v in sorted(((k, v) for k, v in fr.items() if isinstance(v, dict) and v.get("clusters")),
                                      key=lambda kv: -kv[1]["px"]):
                    rows.append((shot, f, pair, v["clusters"][0], v))
    head = 26
    sheet = Image.new("RGB", (len(cols) * CELL + 260, head + len(rows) * (CELL + 4)), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(cols):
        d.text((260 + i * CELL + 8, 6), t, fill=(230, 230, 230))
    for r, (shot, f, pair, c, v) in enumerate(rows):
        y = head + r * (CELL + 4)
        d.text((8, y + 8), f"{shot} f{f}\n{pair}\n{100 * v['fraction']:.2f}% ({v['px']} px)\nworst {c['worst_cm']} cm\n"
               f"box {c['box']}", fill=(230, 230, 230))
        for k, suf in enumerate(cols):
            sheet.paste(crop(os.path.join(a.before, f"{shot}_{int(f):04d}_{suf}.png"), c["box"]), (260 + k * CELL, y))
    return save(sheet, a.out, {"rows": len(rows)})


def save(sheet, out, info):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    q = 85
    while True:
        sheet.save(out, "JPEG", quality=q)
        if os.path.getsize(out) < 3_000_000 or q <= 50:
            break
        q -= 10
    print(json.dumps({"out": out, "bytes": os.path.getsize(out), **info}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after", nargs="?", default="")
    ap.add_argument("--diag", action="store_true", help="one dir: each shot's A/B stills round its worst cluster "
                    "(scene, mask, body+face hidden, garments hidden, the tee's albedo alone)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", type=int, default=12)
    a = ap.parse_args()
    if a.diag:
        return diag(a)
    b, af = load(a.before), load(a.after)
    rows = places(b, a.rows)
    seen = {(s, p) for s, _, p, _ in rows}
    rows += [r for r in places(af, a.rows) if (r[0], r[2]) not in seen][: max(0, a.rows - len(rows))]
    head = 26
    sheet = Image.new("RGB", (4 * CELL + 260, head + len(rows) * (CELL + 4)), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(("before", "before mask", "after", "after mask")):
        d.text((260 + i * CELL + 8, 6), t, fill=(230, 230, 230))
    for r, (shot, f, pair, c) in enumerate(rows):
        y = head + r * (CELL + 4)
        base = f"{shot}_{int(f):04d}"
        d.text((8, y + 8), f"{shot} f{f}\n{pair}\n\nbefore {num(b, shot, f, pair)}\nafter  {num(af, shot, f, pair)}"
               f"\n\nworst {c['worst_cm']} cm", fill=(230, 230, 230))
        for k, (dd, suf) in enumerate(((a.before, "final"), (a.before, "mask"), (a.after, "final"), (a.after, "mask"))):
            sheet.paste(crop(os.path.join(dd, f"{base}_{suf}.png"), c["box"]), (260 + k * CELL, y))
    save(sheet, a.out, {"rows": len(rows), "worst_before": b.get("worst"), "worst_after": af.get("worst")})


if __name__ == "__main__":
    main()
