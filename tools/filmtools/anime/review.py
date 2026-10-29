"""film-anime-review: the whole film at a glance: a frame or a few of every shot, rendered small in Blender, tiled with
labels (the shot's number and id, its film time and frame, the plate that made it), the look schedule's grade laid on
as the engine would lay it (approximately: `grade`), and a slate where a shot has no plate yet or its render failed.

    uv run film-anime-review --film <id> [--only a,b] [--n 1|2|3] [--res 480x270] [--samples 8] [--jobs 1]
                             [--from-plates] [--no-grade] [--cols 6] [--out out/<id>/review/review.png]

Each shot renders in look mode (blender/render.py --mode look, EEVEE) at --res, its frames the middle of its window
(--n 2: a third and two thirds in; --n 3: the first, middle and last frames), under $FILM_OUT=out/<id>/review/work so
the film's own plates are never touched. --from-plates renders nothing and tiles the proxies of the plates already
rendered (out/<id>/plates/<plate>/proxy/): instant, after film-anime-render. Shots render one at a time (--jobs N for
more: the fleet hosts are shared). A shot that fails is a slate in the sheet, its log's last lines in the report.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .. import cli, paths
from . import plates as P

TILE_LABEL = 22  # px of label above each tile


# ---------------------------------------------------------------------------------------------------- the grade

def _srgb_to_lin(s):
    return np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def _luma(c):
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def grade(img: np.ndarray, g: dict) -> np.ndarray:
    """An sRGB float image (h, w, 3, 0..1) under the engine's grade (app/src/engine/post.ts): exposure, warmth (white
    balance, luma kept) and saturation in light, the vignette, then contrast (an S-curve about mid-grey) and lift in
    display values. Without bloom, halation, grain or the tone shoulder: a review's approximation, not the film."""
    c = _srgb_to_lin(img) * g.get("exposure", 1.0)
    w = g.get("warmth", 0.0)
    if w:
        l0 = _luma(c)
        c = c * np.array([1 + 0.14 * w, 1 + 0.02 * w, 1 - 0.2 * w])
        c = c * (l0 / np.maximum(_luma(c), 1e-6))[..., None]
    s = g.get("saturation", 1.0)
    if s != 1:
        l = _luma(c)[..., None]
        c = np.maximum(l + (c - l) * s, 0)
    v = g.get("vignette", 0.0)
    if v:
        h, wd = c.shape[:2]
        y, x = np.mgrid[0:h, 0:wd]
        d = np.hypot((x + 0.5) / wd - 0.5, ((y + 0.5) / h - 0.5) * 0.8)
        k = np.clip((d - 0.95) / (0.25 - 0.95), 0, 1)
        c = c * (1 + (k * k * (3 - 2 * k) - 1) * v)[..., None]
    o = _lin_to_srgb(c)
    k = g.get("contrast", 1.0)
    if k != 1:
        a, b = o ** k, (1 - o) ** k
        o = a / np.maximum(a + b, 1e-6)
    lift = g.get("lift", 0.0)
    if lift > 0:
        o = o + lift * (1 - o)
    return np.clip(o, 0, 1)


def grade_at(film: paths.FilmPaths, scene: str, t: float) -> dict:
    """The look schedule's grade of `scene` at t s into it (blender/lib/look_schedule.py, which this imports)."""
    lib = Path(__file__).resolve().parents[3] / "blender"  # the code, wherever the film is
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    from lib import look_schedule  # noqa: E402 (bpy-free)

    p = film.data / "look.json"
    s = look_schedule.Schedule(json.loads(p.read_text()) if p.exists() else {})
    return s.shot(scene).at(t).grade.post()


# ---------------------------------------------------------------------------------------------------- the sheet

def _font(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def slate(size: tuple[int, int], lines: list[str]):
    """A hatched grey tile saying why there is no picture."""
    from PIL import Image, ImageDraw

    w, h = size
    im = Image.new("RGB", size, (58, 61, 66))
    d = ImageDraw.Draw(im)
    for x in range(-h, w, 24):
        d.line([(x, h), (x + h, 0)], fill=(66, 69, 74), width=6)
    f1, f2 = _font(max(12, h // 9)), _font(max(10, h // 16))
    y = h * 0.36
    for i, line in enumerate(lines):
        f = f1 if i == 0 else f2
        tw = d.textlength(line, font=f)
        d.text(((w - tw) / 2, y), line, fill=(242, 239, 232) if i == 0 else (224, 86, 63) if i == 1 else (184, 180, 171), font=f)
        y += (h // 7) if i == 0 else (h // 11)
    return im


def tile(items: list[dict], out: Path, cols: int = 6, size: tuple[int, int] = (480, 270), title: str = "") -> Path:
    """A labelled grid: each item {"label", "image" (a path, or a PIL image, or None), "slate" (lines when no image)}."""
    from PIL import Image, ImageDraw

    pad = 6
    head = 30 if title else 0
    rows = max(1, math.ceil(len(items) / cols))
    W = cols * (size[0] + pad) + pad
    H = head + rows * (size[1] + TILE_LABEL + pad) + pad
    sheet = Image.new("RGB", (W, H), (24, 24, 26))
    d = ImageDraw.Draw(sheet)
    if title:
        d.text((pad, 8), title, fill=(230, 230, 230), font=_font(16))
    f = _font(13)
    for i, it in enumerate(items):
        x = pad + (i % cols) * (size[0] + pad)
        y = head + pad + (i // cols) * (size[1] + TILE_LABEL + pad)
        im = it.get("image")
        if isinstance(im, (str, Path)):
            im = Image.open(im).convert("RGB")
        if im is None:
            im = slate(size, it.get("slate") or ["?"])
        sheet.paste(im.resize(size, Image.LANCZOS), (x, y + TILE_LABEL))
        d.text((x + 2, y + 4), it["label"], fill=(221, 221, 221), font=f)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def frames_of(sc: P.Scene, n: int) -> list[int]:
    """The film frames a review shows of a scene: its middle (n 1), a third and two thirds in (2), first, middle, last (3)."""
    last = sc.f1 - 1
    if n <= 1:
        return [(sc.f0 + last) // 2]
    if n == 2:
        return sorted({sc.f0 + (sc.f1 - sc.f0) // 3, sc.f0 + 2 * (sc.f1 - sc.f0) // 3})
    return sorted({sc.f0, (sc.f0 + last) // 2, last})


def label(i: int, sc: P.Scene, f: int, fps: float) -> str:
    plate = f" [{sc.plate}]" if sc.plate != sc.id else ""
    return f"{i:02d} {sc.id}{plate}  {f / fps:.2f}s  f{f}"


# ---------------------------------------------------------------------------------------------------- rendering

def render_look(film: paths.FilmPaths, sc: P.Scene, frames: list[int], res: str, samples: int, work: Path) -> tuple[int, str]:
    """Render a scene's review frames in look mode under `work` ($FILM_OUT). (exit code, the log's tail)."""
    settings = {"mode": "look", "engine": "eevee", "samples": samples, "res": res}
    cmd = P.render_cmd(film.id, sc.plate, settings, ",".join(map(str, frames)))
    env = {**os.environ, "FILM_OUT": str(work)}
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    log = (r.stdout + r.stderr)[-1500:] + f"\n[exit {r.returncode}]"
    (work / "logs").mkdir(parents=True, exist_ok=True)
    (work / "logs" / f"{sc.plate}.log").write_text(r.stdout + r.stderr + f"\n[exit {r.returncode}]"
                                                   + (" (killed: out of memory?)" if r.returncode < 0 else "") + "\n")
    return r.returncode, log


def review(film: paths.FilmPaths, only: list[str] | None = None, n: int = 1, res: str = "480x270", samples: int = 8,
           jobs: int = 1, from_plates: bool = False, graded: bool = True, cols: int = 6, out: Path | None = None) -> dict:
    scs = P.scenes(film)
    fps = P.fps_of(film)
    work = film.out / "review" / "work"
    todo = [s for s in scs if (not only or s.id in only) and s.exists]
    results: dict[str, tuple[int, str]] = {}
    if not from_plates and todo:
        def run(sc):
            print(f"[review] {sc.id}: rendering {frames_of(sc, n)} at {res}", flush=True)
            return sc.id, render_look(film, sc, frames_of(sc, n), res, samples, work)

        with ThreadPoolExecutor(max(1, jobs)) as ex:
            for sid, rc in ex.map(run, todo):
                results[sid] = rc
                print(f"[review] {sid}: {'ok' if rc[0] == 0 else f'FAILED (exit {rc[0]})'}", flush=True)
    size = tuple(int(v) for v in res.split("x"))
    items, report = [], {"sheet": None, "shots": {}}
    for i, sc in enumerate(scs, 1):
        if only and sc.id not in only:
            continue
        for f in frames_of(sc, n):
            it = {"label": label(i, sc, f, fps)}
            status = "ok"
            if not sc.exists:
                status, it["slate"] = "no shot", [sc.id, "no shot file", f"blender/shots/{sc.plate}.py"]
            elif not from_plates and results.get(sc.id, (1,))[0] != 0:
                status, it["slate"] = "failed", [sc.id, "render failed", f"see {work.relative_to(paths.ROOT) if work.is_relative_to(paths.ROOT) else work}/logs/{sc.plate}.log"]
            else:
                src = (P.plates_dir(film, sc.plate) / "proxy" / f"{f - sc.f0:04d}.png") if from_plates else \
                    (work / film.id / "look" / sc.plate / f"{f:04d}.png")
                if not src.exists():
                    status, it["slate"] = "not rendered", [sc.id, "not rendered", src.name]
                else:
                    from PIL import Image

                    im = Image.open(src).convert("RGB")
                    if graded:
                        a = np.asarray(im, dtype=np.float64) / 255.0
                        im = Image.fromarray((grade(a, grade_at(film, sc.id, f / fps - sc.start)) * 255 + 0.5).astype(np.uint8))
                    it["image"] = im
            items.append(it)
            report["shots"].setdefault(sc.id, {"status": status, "frames": []})["frames"].append(f)
            if status == "failed":
                report["shots"][sc.id]["log"] = results[sc.id][1]
    out = out or film.out / "review" / ("review-plates.png" if from_plates else "review.png")
    title = f"{film.id}  ·  {'plates' if from_plates else f'look {res}'}  ·  {'graded (approx.)' if graded else 'ungraded'}"
    report["sheet"] = str(tile(items, out, cols, size, title))
    return report


def main(argv: list[str] | None = None) -> None:
    ap = cli.parser(description="Review the whole film at a glance: a few small frames of every shot, tiled with labels.")
    ap.add_argument("--only", help="scene ids, comma separated")
    ap.add_argument("--n", type=int, default=1, choices=(1, 2, 3), help="frames per shot")
    ap.add_argument("--res", default="480x270")
    ap.add_argument("--samples", type=int, default=8)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--from-plates", action="store_true", help="tile the rendered plates' proxies, render nothing")
    ap.add_argument("--no-grade", action="store_true")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--out", type=Path)
    a = cli.parse(ap, argv)
    film = paths.current()
    rep = review(film, a.only.split(",") if a.only else None, a.n, a.res, a.samples, a.jobs, a.from_plates,
                 not a.no_grade, a.cols, a.out)
    bad = {k: v["status"] for k, v in rep["shots"].items() if v["status"] != "ok"}
    print(json.dumps({"sheet": rep["sheet"], "not ok": bad}, indent=1))
    for k, v in rep["shots"].items():
        if v.get("log"):
            print(f"--- {k} ---\n{v['log']}", file=sys.stderr)
