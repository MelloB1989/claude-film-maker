"""Render a film's toon drawing (headless) as PNG frames the engine plays as `src: 'frames/<name>'`.

  blender -b -P blender/draw.py -- [--film <id>] --shot <name> [--frames all|a-b,c] [--res WxH] [--taa N]
                                   [--out DIR] [--save-blend]

A drawing is films/<id>/blender/draw/<name>.py (or --shot path/to/file.py, named by its stem). It defines
  DRAW = {"scene": "<scene id>",  the window it is drawn for (data/timeline.json, else data/vo.json): its length
          "fps": 12,              frames per second of the drawing (12: on twos at 24; 6 for snap-only acting);
                                  0: a still, one frame
          "pad": 0.5,             seconds drawn past the window's end (room for a transition)
          "res": [W, H],          default: 2x the logical frame for a still (room to push in), 4/3 for a sequence
          "taa": 4}               EEVEE samples (the ink anti-aliases itself; mesh edges are under ink)
  build(ctx)
ctx: scene, film (lib/film.py), toon (lib/toon.Toon with the film's style), style (data/look/toon.json), fps, count,
duration, res, shot, frame(t) (the drawing's frame for time t into the shot; frames are 1-based in Blender).
build() makes the shapes, the camera (scene.camera), the faces and poses (keyed at ctx.frame(t)), then calls nothing
else: draw.py inks the groups (toon.ink) and renders.

Writes out/<id>/media/<name>/0000.png, 0001.png, ... and meta.json {fps, count, width, height, ext: "png", src}; a
still is count 1 (fps 1). --frames renders only those frames (1-based), for looking; meta.json is written only by a
full render. --out DIR writes the PNGs there instead (drafts that leave the film's frames alone). The style comes from the film: nothing here names one (docs/CONVENTIONS.md).
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402

from lib import film as filmlib  # noqa: E402
from lib import timing as timinglib  # noqa: E402
from lib.toon import Toon  # noqa: E402

KEYS = {"scene", "fps", "pad", "res", "taa", "duration"}


def args(argv):
    a = argv[argv.index("--") + 1:] if "--" in argv else []
    o = {"film": None, "shot": None, "frames": "all", "res": None, "taa": None, "out": None, "save_blend": False}
    i = 0
    while i < len(a):
        k = a[i]
        if k == "--save-blend":
            o["save_blend"] = True
            i += 1
            continue
        if k not in ("--film", "--shot", "--frames", "--res", "--taa", "--out") or i + 1 >= len(a):
            raise SystemExit(f"draw.py: unknown or incomplete option {k!r} (see the header)")
        o[k[2:]] = a[i + 1]
        i += 2
    if not o["shot"]:
        raise SystemExit("draw.py: --shot <name> is required")
    return o


class Ctx:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def frame(self, t: float) -> int:
        return 1 + int(round(t * max(self.fps, 1)))


def main():
    o = args(sys.argv)
    film = filmlib.load(o["film"])
    p = Path(o["shot"])
    path = p if p.suffix == ".py" else film.root / "blender" / "draw" / f"{o['shot']}.py"
    if not path.exists():
        raise SystemExit(f"draw.py: no drawing {path}")
    name = path.stem
    sys.path.insert(0, str(path.parent))      # a film's drawings may share helpers that sit beside them
    spec = importlib.util.spec_from_file_location(f"draw_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    D = dict(getattr(mod, "DRAW", {}))
    bad = set(D) - KEYS
    if bad:
        raise SystemExit(f"draw.py: {name}: unknown DRAW keys {sorted(bad)} (known: {sorted(KEYS)})")
    fps = float(D.get("fps", 0))
    if "duration" in D:
        dur = float(D["duration"])
    elif D.get("scene"):
        tm = timinglib.for_film(film)
        s0, s1 = tm.scene(D["scene"])
        dur = s1 - s0 + float(D.get("pad", 0.5))
    else:
        dur = 0.0
    count = 1 if fps <= 0 else max(1, int(math.ceil(dur * fps)) + 1)
    W, H = film.width, film.height
    res = tuple(int(x) for x in o["res"].lower().split("x")) if o["res"] else tuple(D.get("res") or ((2 * W, 2 * H) if fps <= 0 else (W * 4 // 3, H * 4 // 3)))
    style_path = film.root / "data" / "look" / "toon.json"
    style = json.loads(style_path.read_text()) if style_path.exists() else {}

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 24
    sc.frame_start, sc.frame_end = 1, count
    toon = Toon(sc, style)
    ctx = Ctx(scene=sc, film=film, toon=toon, style=style, fps=fps, count=count, duration=dur, res=res, shot=name)
    t0 = time.time()
    mod.build(ctx)
    if sc.camera is None:
        raise SystemExit(f"draw.py: {name}: build() made no camera")
    made = toon.ink(sc.camera)
    toon.render_settings(res, int(o["taa"] or D.get("taa", 4)))
    print(f"draw {name}: built in {time.time() - t0:.1f}s, {count} frame(s) at {res[0]}x{res[1]}, ink {made}", flush=True)

    out = Path(o["out"]) if o["out"] else film.out / "media" / name
    out.mkdir(parents=True, exist_ok=True)
    frames = list(range(1, count + 1)) if o["frames"] == "all" else [f for f in timinglib.parse_frames(o["frames"]) if 1 <= f <= count]
    if o["save_blend"]:
        (film.out / "blender").mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(film.out / "blender" / f"draw-{name}.blend"))
    for f in frames:
        t1 = time.time()
        sc.frame_set(f)
        sc.render.filepath = str(out / f"{f - 1:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"draw {name}: frame {f}/{count} in {time.time() - t1:.1f}s", flush=True)
    if o["frames"] == "all" and not o["out"]:
        for stale in sorted(out.glob("*.png"))[count:]:
            stale.unlink()
        meta = {"fps": fps if fps > 0 else 1, "count": count, "width": res[0], "height": res[1], "ext": "png",
                "src": str(path.relative_to(film.root)) if path.is_relative_to(film.root) else str(path)}
        (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"draw {name}: done in {time.time() - t0:.1f}s -> {out}", flush=True)


if __name__ == "__main__":
    main()
