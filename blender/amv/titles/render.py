"""The titles CLI: render every title of a film's plan as an RGBA PNG sequence.

    blender -b --factory-startup -P blender/amv/titles/render.py -- --film films/timeless \
        [--ids T05_black_lens.0 ..] [--res-scale 0.5] [--samples 32] [--out out/timeless/amv/titles] \
        [--frames 0,5,10] [--engine CYCLES] [--fonts DIR] [--set key=value ..]

Each title of the plan (`jobs.jobs_from_plan`) is dispatched by its `style` to `blender/amv/titles/<style>.py`
`render(spec, out_dir, opts)`, which writes `<out>/<title_id>/<k:04d>.png` (see docs/PIPELINE-AMV.md, titles).
`--list` prints the jobs and exits (no bpy needed: `python3 render.py --list --film ...` works too).
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (str(REPO / "blender"), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

from amv.titles import jobs as J  # noqa: E402
from amv.titles.common import TitleOpts  # noqa: E402

STYLES = ("novax", "chrome", "gold", "neon", "sub", "spring", "extended", "tag", "watermark")


def style_module(style: str):
    """`blender/amv/titles/<style>.py` imported on demand (a style someone has not written yet is a clear error)."""
    if style not in STYLES:
        raise KeyError(f"unknown title style {style!r}; known: {STYLES}")
    try:
        return importlib.import_module(f"amv.titles.{style}")
    except ModuleNotFoundError as e:
        if e.name == f"amv.titles.{style}":
            raise NotImplementedError(f"title style {style!r} has no module blender/amv/titles/{style}.py yet") from e
        raise


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="render.py", description=__doc__.split("\n")[0])
    ap.add_argument("--film", required=True, help="film folder (films/<id>)")
    ap.add_argument("--ids", nargs="*", help="title ids to render (default: all)")
    ap.add_argument("--styles", nargs="*", help="only these styles")
    ap.add_argument("--out", help="titles folder (default out/<film id>/amv/titles under the repo)")
    ap.add_argument("--res-scale", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--engine", default="CYCLES")
    ap.add_argument("--fonts", help="extra fonts folder, searched first")
    ap.add_argument("--frames", help="title frames k to render, e.g. 0,5,10 or 0-30 (default: all)")
    ap.add_argument("--set", action="append", default=[], metavar="K=V", help="style-specific option (opts.extra)")
    ap.add_argument("--list", action="store_true", help="print the title jobs and exit")
    return ap.parse_args(argv)


def parse_frames(s):
    if not s:
        return None
    ks = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            ks += range(int(a), int(b) + 1)
        elif part:
            ks.append(int(part))
    return ks


def main(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    a = parse_args(argv)
    from filmtools.amv import plan as P
    film = Path(a.film).resolve()
    plan = P.load(film)
    jobs = J.select(J.jobs_from_plan(plan), a.ids, a.styles)
    out = Path(a.out) if a.out else REPO / "out" / film.name / "amv" / "titles"
    if a.list:
        for j in jobs:
            print(f"{j.id:28s} {j.style:9s} f_in {j.f_in:4d} dur {j.dur:3d}  -> {j.out_dir(out)}")
        return 0
    extra = dict(kv.split("=", 1) for kv in a.set)
    opts = TitleOpts(res_scale=a.res_scale, samples=a.samples, fonts_dir=Path(a.fonts) if a.fonts else None,
                     engine=a.engine, frames=parse_frames(a.frames), film_dir=film, extra=extra)
    failed = []
    for j in jobs:
        t0 = time.time()
        try:
            mod = style_module(j.style)
            od = j.out_dir(out)
            od.mkdir(parents=True, exist_ok=True)
            mod.render(dict(j.spec), od, opts)
            print(f"[titles] {j.id} ({j.style}) done in {time.time() - t0:.0f}s -> {od}", flush=True)
        except Exception:
            traceback.print_exc()
            failed.append(j.id)
    if failed:
        print(f"[titles] FAILED: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    rc = main()
    if "bpy" in sys.modules:   # leave Blender with the right exit code
        sys.exit(rc)
    sys.exit(rc)
