"""Build the whole AMV edit as ONE editable .blend, and optionally render frames of it (docs/PIPELINE-AMV.md "scene").

    blender -b --factory-startup -P blender/amv/build.py -- --film films/timeless --layers out/timeless/amv/layers \
        [--overlays out/timeless/amv] [--res-scale 0.25] [--samples 16] [--frames 240-260,480-500] \
        [--engine cycles|eevee] [--save out/timeless/amv/timeless.blend] [--render out/timeless/amv/frames]

--render writes `<dir>/<f:04d>.png` for --frames (default: every frame) with the blank-frame guard of lib/blank.py: a
frame that comes out blank or bad is rendered again (the plan's `black` strobe frames may be black), and a frame that
stays so stops the run. It logs s/frame. --cpu allows Cycles on the CPU (the default here; pass --require-gpu on the
pod to refuse it).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

import bpy  # noqa: E402

from amv import compositor, scene as S  # noqa: E402
from lib import blank  # noqa: E402


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="blender -b --factory-startup -P blender/amv/build.py --", description=__doc__)
    ap.add_argument("--film", required=True, help="films/<id>/ (plan, film.json)")
    ap.add_argument("--layers", required=True, help="the bake's layer frames: <layers>/<shot>/<f:04d>.png")
    ap.add_argument("--overlays", help="titles/ and outro/ frames (default: none, skipped with a warning)")
    ap.add_argument("--res-scale", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--frames", help="comp frames to render: a-b (inclusive), comma-separated")
    ap.add_argument("--engine", choices=["cycles", "eevee"], default="cycles")
    ap.add_argument("--save", help="save the .blend here")
    ap.add_argument("--render", help="render the frames to this folder")
    ap.add_argument("--require-gpu", action="store_true", help="fail rather than render Cycles on the CPU")
    return ap.parse_args(argv)


def read_back(path: Path):
    """The frame as written (8-bit display values) as a uint8 (h, w, 4) array, top row last as Blender holds it."""
    import numpy as np
    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    return np.rint(px.reshape(h, w, 4) * 255.0).astype(np.uint8)


def render_frames(built, frames, out: Path, log=print) -> float:
    """Render comp frames to out/<f:04d>.png, each checked by the blank guard. Returns s/frame."""
    import numpy as np
    scene = built.scene
    black = set(built.plan.raw.get("black") or [])
    # the outro stage's plates fade in from black: legitimately black, still checked for non-finite values
    black |= set(range(built.plan.raw["outro"]["f"], built.plan.dur))
    out.mkdir(parents=True, exist_ok=True)
    tile = 2048 if scene.render.engine == "CYCLES" else None
    t0 = time.time()
    for n, f in enumerate(frames):
        path = out / f"{f:04d}.png"
        scene.render.filepath = str(path)

        def once(attempt, f=f):
            scene.frame_set(f)
            S.hide_for_frame(built, f)
            bpy.ops.render.render(write_still=True)
            px = read_back(path)
            bad = S.magenta_fraction(px)
            if bad > S.MAGENTA_LIMIT:   # Blender paints a missing image (1, 0, 1): stop rather than render a film of it
                raise SystemExit(f"frame {f}: {bad:.0%} of it is missing-texture magenta; check the image paths")
            return px

        t1 = time.time()
        blank.render_checked(once, shot="amv", film_frame=f, path=path, black_ok=f in black, tile=tile, log=log)
        log(f"frame {f}: {time.time() - t1:.1f} s ({n + 1}/{len(frames)})")
    per = (time.time() - t0) / max(1, len(frames))
    log(f"rendered {len(frames)} frames in {time.time() - t0:.1f} s: {per:.2f} s/frame")
    return per


def main(argv=None):
    argv = sys.argv[sys.argv.index("--") + 1:] if argv is None and "--" in sys.argv else (argv or [])
    a = parse_args(argv)
    # absolute while building, so nothing depends on the cwd; --save then writes them relative to the .blend ('//...')
    a.film, a.layers, a.overlays = S.absolute(a.film), S.absolute(a.layers), S.absolute(a.overlays)
    t0 = time.time()
    built = S.build_scene(a.film, a.layers, res_scale=a.res_scale, samples=a.samples, engine=a.engine,
                          allow_cpu=not a.require_gpu)
    compositor.build(built, a.overlays, a.res_scale)
    print(f"build: {time.time() - t0:.1f} s", flush=True)
    if a.save:
        Path(a.save).parent.mkdir(parents=True, exist_ok=True)
        # saved with every plane shown: the keyed alpha is the truth, parking is a render-time optimisation
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.save).resolve()), relative_remap=True)
        print(f"saved {a.save}: {Path(a.save).stat().st_size / 1e6:.1f} MB", flush=True)
    if a.render:
        frames = S.parse_frames(a.frames) if a.frames else list(range(built.plan.dur))
        render_frames(built, frames, Path(a.render))


if __name__ == "__main__":
    main()
