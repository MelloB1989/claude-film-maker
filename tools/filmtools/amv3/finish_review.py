"""Timeless v3 finishing review: frame strips and per-frame numbers (luma, black level, clipping, edge chroma).

    python -m filmtools.amv3.finish_review strip --out S.png --frames 46,48,49,50 --row "plate=DIR" --row "v3=DIR" [--w 400]
    python -m filmtools.amv3.finish_review refstrip --out S.png --ref a:332,334 --ref c:319,320 [--h 240]
    python -m filmtools.amv3.finish_review stats --dir DIR [--frames A-B] [--base DIR] [--json OUT]
    python -m filmtools.amv3.finish_review render --project P.ecproj --frames 46,48 --out DIR [--scale 0.5]   # local render-frame

A row DIR holds f_NNNNN.png. `stats` needs numpy (the VM python, or Blender's bundled python here). Numbers per frame:
mean luma, p1 / p50 / p99 luma (0..1, Rec.709 on the gamma-encoded values), % pixels with a channel >= 250/255 (clipped),
and with --base the luma lift against the base frame (mean ratio - 1).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import ecrender as R

REFS = {"a": "/home/nikhil/code/film-making/work/refs_v3/a/iXZkJuUqOS8.mp4",
        "b": "/home/nikhil/code/film-making/work/refs_v3/b/N3TshMrwhGk.mp4",
        "c": "/home/nikhil/code/film-making/work/refs_v3/c/GKI0-Xw4f4w.mp4"}
ACTS = (("tobey", 0, 252), ("andrew", 252, 480), ("tom", 480, 819), ("outro", 819, 900))


def frames_arg(s):
    if "-" in s and "," not in s:
        a, b = (int(x) for x in s.split("-"))
        return list(range(a, b + 1))
    out = []
    for x in s.split(","):
        if "-" in x:
            a, b = map(int, x.split("-"))
            out += range(a, b + 1)
        elif x:
            out.append(int(x))
    return out


def strip(out, frames, rows, w=400):
    """rows = [(label, dir)]: one row per dir, one column per frame (missing frames are grey)."""
    ins, fc, n = [], "", 0
    h = w * 9 // 16
    for r, (label, d) in enumerate(rows):
        for c, f in enumerate(frames):
            p = Path(d) / f"f_{f:05d}.png"
            if p.exists():
                ins += ["-i", str(p)]
            else:
                ins += ["-f", "lavfi", "-i", f"color=gray:s={w}x{h}"]
            txt = f"{label} {f}".replace(":", " ")
            fc += f"[{n}:v]scale={w}:{h},drawtext=text='{txt}':x=6:y=6:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.6[v{n}];"
            n += 1
    cols = len(frames)
    for r in range(len(rows)):
        fc += "".join(f"[v{r * cols + c}]" for c in range(cols)) + (f"hstack={cols}" if cols > 1 else "null") + f"[r{r}];"
    fc += "".join(f"[r{r}]" for r in range(len(rows))) + (f"vstack={len(rows)}" if len(rows) > 1 else "null")
    r = subprocess.run([R.FFMPEG, "-y", "-v", "error"] + ins + ["-filter_complex", fc, "-frames:v", "1", str(out)],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-800:])
    return out


def refstrip(out, refs, h=240):
    rows = []
    for spec in refs:
        k, fr = spec.split(":")
        sel = "+".join(f"eq(n\\,{int(f)})" for f in fr.split(","))
        p = Path(str(out) + f".{k}.png")
        r = subprocess.run([R.FFMPEG, "-y", "-v", "error", "-i", REFS[k], "-vf",
                            f"select='{sel}',scale=-2:{h},tile={len(fr.split(','))}x1", "-frames:v", "1", str(p)],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(r.stderr[-500:])
        rows.append(p)
    ins = sum((["-i", str(p)] for p in rows), [])
    fc = "".join(f"[{i}:v]pad=iw:ih+4[p{i}];" for i in range(len(rows)))
    fc += "".join(f"[p{i}]" for i in range(len(rows))) + f"xstack=inputs={len(rows)}:layout=" + \
        "|".join("0_" + ("+".join(f"h{j}" for j in range(i)) if i else "0") for i in range(len(rows))) + ":fill=black"
    if len(rows) == 1:
        fc = "[0:v]null"
    subprocess.run([R.FFMPEG, "-y", "-v", "error"] + ins + ["-filter_complex", fc, "-frames:v", "1", str(out)], check=True)
    return out


# Acceptance pairs: a v3 CUTS window next to the reference transition it is built after (REFS.md frames).
PAIRS = [
    ("C01 zt 50", [46, 47, 48, 49, 50, 51, 52, 53], "c", [376, 377, 378, 379, 380, 381, 382, 383]),
    ("C06 whip 201", [197, 198, 199, 200, 201, 202, 203, 204], "c", [416, 417, 418, 419, 420, 421, 422, 423]),
    ("C09 zt 300", [296, 297, 298, 299, 300, 301, 302, 303], "a", [297, 298, 299, 300, 301, 302, 303, 304]),
    ("C17 drop 480", [476, 477, 478, 479, 480, 481, 482, 483], "b", [622, 623, 624, 625, 626, 627, 628, 629]),
    ("C20 sling 620", [612, 614, 616, 618, 619, 620, 621, 622], "a", [168, 170, 172, 174, 175, 176, 177, 178]),
    ("C25 text_fly 656", [652, 653, 654, 655, 656, 657, 658, 659], "c", [316, 317, 318, 319, 320, 321, 322, 323]),
]


def pairs(out_dir, v3dir, w=300):
    """One PNG per pair: v3 frames on top, the reference frames below (both rows the same width)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for label, fr, ref, rfr in PAIRS:
        tag = label.split()[0]
        top = strip(out_dir / f"_{tag}_v3.png", fr, [(f"v3 {tag}", v3dir)], w)
        sel = "+".join(f"eq(n\\,{f})" for f in rfr)
        rw = w * len(fr) // len(rfr)
        bot = out_dir / f"_{tag}_ref.png"
        subprocess.run([R.FFMPEG, "-y", "-v", "error", "-i", REFS[ref], "-vf",
                        f"select='{sel}',scale={rw}:{w * 9 // 16}:force_original_aspect_ratio=decrease,"
                        f"pad={rw}:{w * 9 // 16}:(ow-iw)/2:(oh-ih)/2,drawtext=text='ref {ref} {rfr[0]}-{rfr[-1]}':x=6:y=6:fontsize=16:"
                        f"fontcolor=yellow:box=1:boxcolor=black@0.6,tile={len(rfr)}x1", "-frames:v", "1", str(bot)], check=True)
        out = out_dir / f"pair_{tag}.png"
        subprocess.run([R.FFMPEG, "-y", "-v", "error", "-i", str(top), "-i", str(bot), "-filter_complex",
                        "[1:v]scale=w=iw:h=-2[b];[0:v][b]vstack=2", str(out)], check=True)
        made.append(str(out))
    return made


def _read(p, w=480):
    import numpy as np
    r = subprocess.run([R.FFMPEG, "-v", "error", "-i", str(p), "-vf", f"scale={w}:-2:flags=area", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, np.uint8)
    return a.reshape(-1, w, 3)


def frame_stats(p, base=None):
    import numpy as np
    a = _read(p).astype(np.float32)
    y = (a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722) / 255.0
    q = np.percentile(y, [1, 50, 99])
    s = dict(mean=round(float(y.mean()), 4), p1=round(float(q[0]), 4), p50=round(float(q[1]), 4), p99=round(float(q[2]), 4),
             clip=round(float((a.max(-1) >= 242).mean() * 100), 2))   # >= 0.95: the limiter caps white at 0.975
    mx, mn = a.max(-1), a.min(-1)
    ok = mx > 25
    s["sat"] = round(float(((mx - mn) / np.maximum(mx, 1))[ok].mean()) if ok.any() else 0.0, 4)
    if base is not None and Path(base).exists():
        b = _read(base).astype(np.float32)
        yb = (b[..., 0] * 0.2126 + b[..., 1] * 0.7152 + b[..., 2] * 0.0722) / 255.0
        s["lift"] = round(float(y.mean() / max(yb.mean(), 1e-4) - 1) * 100, 1)
    return s


def stats(d, frames, base=None):
    out = {}
    for f in frames:
        p = Path(d) / f"f_{f:05d}.png"
        if p.exists():
            out[f] = frame_stats(p, Path(base) / f"f_{f:05d}.png" if base else None)
    acts = {}
    for name, a, b in ACTS:
        v = [s for f, s in out.items() if a <= f < b]
        if v:
            acts[name] = {k: round(sum(x[k] for x in v) / len(v), 4) for k in ("mean", "p1", "p50", "p99", "clip", "sat")}
            acts[name]["p1_min"] = min(x["p1"] for x in v)
            acts[name]["clip_max"] = max(x["clip"] for x in v)
            acts[name]["frames"] = len(v)
    return dict(frames=out, acts=acts)


def render_local(project, frames, out, scale=0.5, comp="FINISH"):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for f in frames:
        r = subprocess.run([R.local_cli(), "--project", str(project), "render-frame", "--comp", comp, "--frame", str(f),
                            "--scale", str(scale), "--out", str(out / f"f_{f:05d}.png")], capture_output=True, text=True)
        print(f, (r.stdout + r.stderr).strip().splitlines()[-1:] if r.returncode == 0 else r.stderr[-300:], flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("strip", "refstrip", "stats", "render", "pairs"))
    ap.add_argument("--out")
    ap.add_argument("--frames", default="")
    ap.add_argument("--row", action="append", default=[])
    ap.add_argument("--ref", action="append", default=[])
    ap.add_argument("--w", type=int, default=400)
    ap.add_argument("--h", type=int, default=240)
    ap.add_argument("--dir")
    ap.add_argument("--base")
    ap.add_argument("--json")
    ap.add_argument("--project")
    ap.add_argument("--scale", type=float, default=0.5)
    a = ap.parse_args(argv)
    fr = frames_arg(a.frames) if a.frames else []
    if a.cmd == "strip":
        strip(a.out, fr, [tuple(r.split("=", 1)) for r in a.row], a.w)
    elif a.cmd == "refstrip":
        refstrip(a.out, a.ref, a.h)
    elif a.cmd == "pairs":
        print("\n".join(pairs(a.out, a.dir, a.w)))
    elif a.cmd == "render":
        render_local(a.project, fr, a.out, a.scale)
    else:
        fr = fr or sorted(int(p.stem[2:]) for p in Path(a.dir).glob("f_*.png"))
        s = stats(a.dir, fr, a.base)
        if a.json:
            Path(a.json).write_text(json.dumps(s, indent=1))
        print(json.dumps(s["acts"], indent=1))
        if len(fr) <= 40:
            for f, v in s["frames"].items():
                print(f, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
