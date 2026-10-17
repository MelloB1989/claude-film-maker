"""Adversarial review tooling for an integrated Timeless v2 render.

    python review.py FRAMES [--f0 0] [--f1 450] [--out DIR] [--edl PATH] [--fps 30]

FRAMES is a directory of frame images (any name whose LAST integer is the frame number, e.g. 00123.png or f_123.jpg) or a video
file (decoded with ffmpeg to 480x270 PNGs in DIR/_frames). Everything is analysed at 480x270. Writes into DIR:

    cuts/cut_<shot>_f<a>.png      strip a-3 .. a+4 around every EDL cut in range (the frame number is printed on each tile)
    titles/title_<n>_<style>.png  entry / hold / exit strip per title (entry = f+1, hold = middle, exit = f1-2)
    shots.md / shots.csv          per shot: luma p1/p50/p99, clipped %, mean saturation, mean frame-to-frame motion, flags
    flags.md                      black frames, duplicate (frozen) frames, ghost/blend suspects at cuts, flashes, clipped shots
    index.md                      links to everything + the flag summary

Flags (thresholds at the top of the file):
    BLACK    frame mean luma < 0.02 and p99 < 0.06 (expected black is skipped: frame < OPEN_BLACK, and inside the outro)
    DUP      consecutive frames with mean abs difference < 0.0015 (a run of 2+ is a freeze; runs inside a shot are listed)
    GHOST    at a cut, the frame after is closer to the frame before than to the one two frames later (a blend instead of a cut),
             or a cut frame that is a 50/50 mix of both sides
    CLIP     shot with > 0.5 % clipped pixels on frames that are not flash frames (flash = > 30 % clipped)
    JUMP     frame-to-frame difference spike inside a shot, 10+ frames from its cuts (> 4x the shot's median step and > 0.08): a glitch or a stray cut
"""
import argparse
import csv
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TW, TH = 480, 270
OPEN_BLACK = 6                   # frames at the start that may be black (open from black)
BLACK_MEAN, BLACK_P99 = 0.02, 0.06
DUP_DIFF = 0.0015
CLIP_PCT, FLASH_PCT = 0.5, 30.0
JUMP_X, JUMP_MIN = 4.0, 0.08
JUMP_EDGE = 10                   # transitions move fast near a cut: JUMP is only judged this many frames away from both edges


def find_ffmpeg():
    import shutil
    return shutil.which("ffmpeg") or "/home/nikhil/code/film-making/bin/ffmpeg"


def load_frames(src, f0, f1, out):
    """{frame: uint8 HxWx3 at 480x270} for f0 <= frame < f1."""
    import numpy as np
    from PIL import Image
    fr = {}
    if os.path.isfile(src):
        d = os.path.join(out, "_frames")
        os.makedirs(d, exist_ok=True)
        subprocess.run([find_ffmpeg(), "-v", "error", "-y", "-i", src, "-vf", "scale=%d:%d" % (TW, TH), "-start_number", "0",
                        os.path.join(d, "%05d.png")], check=True)
        src = d
    for p in glob.glob(os.path.join(src, "*")):
        if not p.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".exr")):
            continue
        m = re.findall(r"\d+", os.path.basename(p))
        if not m:
            continue
        n = int(m[-1])
        if f0 <= n < f1:
            fr[n] = np.asarray(Image.open(p).convert("RGB").resize((TW, TH), Image.BILINEAR))
    return fr


def luma(a):
    f = a.astype("float32") / 255.0
    return f[..., 0] * 0.2126 + f[..., 1] * 0.7152 + f[..., 2] * 0.0722


def fstats(a):
    import numpy as np
    L = luma(a)
    f = a.astype("float32") / 255.0
    mx, mn = f.max(-1), f.min(-1)
    ok = mx > 0.1
    p = np.percentile(L, [1, 50, 99])
    return {"p1": float(p[0]), "p50": float(p[1]), "p99": float(p[2]), "mean": float(L.mean()),
            "clip": float((mx >= 0.985).mean() * 100),
            "sat": float(((mx - mn) / np.maximum(mx, 1e-6))[ok].mean()) if ok.any() else 0.0}


def mad(a, b):
    import numpy as np
    return float(np.abs(a.astype("float32") - b.astype("float32")).mean() / 255.0)


def tile(a, label, size=(TW, TH)):
    from PIL import Image, ImageDraw
    im = Image.fromarray(a).resize(size)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(label), 15], fill=(0, 0, 0))
    d.text((4, 2), label, fill=(255, 255, 0))
    return im


def strip(tiles, path, cols=4):
    from PIL import Image
    if not tiles:
        return
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    im = Image.new("RGB", (cols * w, rows * h), (20, 20, 20))
    for i, t in enumerate(tiles):
        im.paste(t, ((i % cols) * w, (i // cols) * h))
    im.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("frames")
    ap.add_argument("--f0", type=int, default=0)
    ap.add_argument("--f1", type=int, default=450)
    ap.add_argument("--out", default="review_out")
    ap.add_argument("--edl", default=os.path.join(HERE, "..", "..", "..", "films/timeless/amv2/edl.json"))
    a = ap.parse_args()
    import numpy as np
    E = json.load(open(a.edl))
    out = a.out
    for d in ("cuts", "titles"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    fr = load_frames(a.frames, a.f0, a.f1, out)
    if not fr:
        sys.exit("no frames found in range %d-%d under %s" % (a.f0, a.f1, a.frames))
    have = sorted(fr)
    outro0 = (E.get("outro") or {}).get("f0", 10 ** 9)
    flags, cut_files, title_files = [], [], []
    missing = [f for f in range(a.f0, min(a.f1, max(have) + 1)) if f not in fr]
    if missing:
        flags.append(("MISSING", missing[0], "%d frames missing in range, first %d" % (len(missing), missing[0])))

    # ---- per-frame stats and consecutive differences
    st = {f: fstats(fr[f]) for f in have}
    diff = {f: mad(fr[f - 1], fr[f]) for f in have if f - 1 in fr}

    # ---- black frames
    for f in have:
        s = st[f]
        if f >= OPEN_BLACK and f < outro0 and s["mean"] < BLACK_MEAN and s["p99"] < BLACK_P99:
            flags.append(("BLACK", f, "mean %.3f p99 %.3f" % (s["mean"], s["p99"])))

    # ---- duplicate runs
    run = []
    for f in have:
        if f in diff and diff[f] < DUP_DIFF and f < outro0:
            run.append(f)
        else:
            if len(run) >= 1:
                flags.append(("DUP", run[0] - 1, "frames %d-%d identical (%d frames frozen)" % (run[0] - 1, run[-1], len(run) + 1)))
            run = []
    if run:
        flags.append(("DUP", run[0] - 1, "frames %d-%d identical" % (run[0] - 1, run[-1])))

    # ---- cuts
    shots = [s for s in E["shots"] if s["b"] > a.f0 and s["a"] < a.f1]
    for i, s in enumerate(shots):
        c = s["a"]
        if c <= a.f0:
            continue
        ids = [f for f in range(c - 3, c + 5) if f in fr]
        strip([tile(fr[f], "f%d%s" % (f, " CUT" if f == c else "")) for f in ids], os.path.join(out, "cuts", "cut_%s_f%d.png" % (s["id"], c)))
        cut_files.append((s["id"], c))
        # ghost: a hard cut should show A, A, B, B; a blend shows a frame between the two sides
        if all(f in fr for f in (c - 2, c - 1, c, c + 1, c + 2)):
            dA, dB = mad(fr[c - 1], fr[c]), mad(fr[c], fr[c + 1])
            across = mad(fr[c - 2], fr[c + 2])
            mixed = None
            for f in (c - 1, c, c + 1):
                x = (fr[c - 3].astype("float32") + fr[c + 3].astype("float32")) / 2 if (c - 3 in fr and c + 3 in fr) else None
                if x is not None and across > 0.12 and mad(fr[f], x.astype("uint8")) < 0.04:
                    mixed = f
            if mixed is not None:
                flags.append(("GHOST", mixed, "cut %s @%d: frame %d looks like a 50/50 blend of both sides" % (s["id"], c, mixed)))

    # ---- shots table
    rows = []
    for s in shots:
        fs = [f for f in range(max(s["a"], a.f0), min(s["b"], a.f1)) if f in fr]
        if not fs:
            continue
        pick = fs[:: max(1, len(fs) // 8)]
        S = [st[f] for f in pick]
        flash = [f for f in fs if st[f]["clip"] > FLASH_PCT]
        nonflash = [st[f]["clip"] for f in fs if f not in flash]
        steps = [diff[f] for f in fs if f in diff and f > s["a"]]
        med = float(np.median(steps)) if steps else 0.0
        mot = float(np.mean(steps)) if steps else 0.0
        row = {"shot": s["id"], "clip": s["clip"], "a": s["a"], "b": s["b"],
               "p1": float(np.mean([x["p1"] for x in S])), "p50": float(np.mean([x["p50"] for x in S])),
               "p99": float(np.mean([x["p99"] for x in S])), "clip_pct": float(np.mean(nonflash)) if nonflash else 0.0,
               "max_clip_pct": float(max(nonflash)) if nonflash else 0.0, "sat": float(np.mean([x["sat"] for x in S])),
               "motion": mot, "flash_frames": len(flash)}
        fl = []
        if row["clip_pct"] > CLIP_PCT:
            fl.append("CLIP")
            flags.append(("CLIP", s["a"], "%s mean %.2f %% clipped (max %.2f %%) outside flashes" % (s["id"], row["clip_pct"], row["max_clip_pct"])))
        if row["p50"] < 0.06:
            fl.append("DARK")
        if row["sat"] > 0.65:
            fl.append("NEON")
        for f in fs:
            if f in diff and f > s["a"] + JUMP_EDGE and f < s["b"] - JUMP_EDGE and med > 0 and diff[f] > max(JUMP_MIN, JUMP_X * med):
                fl.append("JUMP@%d" % f)
                flags.append(("JUMP", f, "%s step %.3f vs median %.3f (glitch or stray cut)" % (s["id"], diff[f], med)))
                break
        row["flags"] = " ".join(fl)
        rows.append(row)
    with open(os.path.join(out, "shots.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    md = ["| shot | clip | frames | luma p1 | p50 | p99 | clipped % | sat | motion | flags |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append("| %s | %s | %d-%d | %.3f | %.3f | %.3f | %.2f | %.2f | %.3f | %s |" % (
            r["shot"], r["clip"], r["a"], r["b"], r["p1"], r["p50"], r["p99"], r["clip_pct"], r["sat"], r["motion"], r["flags"]))
    open(os.path.join(out, "shots.md"), "w").write("\n".join(md) + "\n")

    # ---- titles
    for n, t in enumerate(E.get("titles", [])):
        f0, f1 = t["f"], t.get("f1", t["f"] + 30)
        if f1 <= a.f0 or f0 >= a.f1:
            continue
        pts = [("entry", f0 + 1), ("hold", (f0 + f1) // 2), ("exit", f1 - 2)]
        tl = [tile(fr[f], "%s f%d" % (nm, f)) for nm, f in pts if f in fr]
        if tl:
            name = "title_%02d_%s.png" % (n, t["style"])
            strip(tl, os.path.join(out, "titles", name), cols=3)
            title_files.append((name, t["style"], t.get("text", ""), f0, f1))

    # ---- flags + index
    flags.sort(key=lambda x: (x[1], x[0]))
    fl = ["# Flags (frames %d-%d, %d frames analysed)" % (a.f0, a.f1, len(have)), ""]
    fl += ["- **%s** f%d: %s" % x for x in flags] or ["No flags."]
    open(os.path.join(out, "flags.md"), "w").write("\n".join(fl) + "\n")
    ix = ["# Review index", "", "Frames %d-%d from `%s`." % (a.f0, a.f1, a.frames), "",
          "- [flags.md](flags.md): %d flags (%s)" % (len(flags), ", ".join("%s %d" % (k, sum(1 for x in flags if x[0] == k)) for k in sorted(set(x[0] for x in flags))) or "none"),
          "- [shots.md](shots.md) / shots.csv", "", "## Cuts"] + ["- cuts/cut_%s_f%d.png" % c for c in cut_files] + ["", "## Titles"]
    ix += ["- titles/%s: %s '%s' f%d-%d" % t for t in title_files]
    open(os.path.join(out, "index.md"), "w").write("\n".join(ix) + "\n")
    print("wrote %s: %d cut strips, %d title strips, %d shots, %d flags" % (out, len(cut_files), len(title_files), len(rows), len(flags)))


if __name__ == "__main__":
    main()
