"""Cel sheets: a film's drawn characters (blender/lib/cels.py) rendered flat, at a few moments side by side on one
sheet: the quickest way to judge a drawing and see what a change did.

    blender -b --factory-startup -P blender/celsheet.py -- --film <id> --module rf.shinza_cels --draw closeup
        [--times 0,0.5,1.0] [--res 1000x1000] [--bg "#2b3242"] [--out out/<id>/cels/<draw>.png] [--box x0,y0,x1,y1]

`--module` is a module under films/<id>/blender/ (dotted); `--draw` a function in it taking the time in seconds and
returning a cels.Drawing. Each moment is framed to the drawing's bounds (or `--box`, in drawing units) with an
orthographic camera.
"""
from __future__ import annotations

import argparse
import importlib
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from lib import cels, film as films  # noqa: E402


def args(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", required=True)
    ap.add_argument("--module", required=True)
    ap.add_argument("--draw", required=True)
    ap.add_argument("--times", default="0")
    ap.add_argument("--res", default="1000x1000")
    ap.add_argument("--bg", default="#2b3242")
    ap.add_argument("--box", default="")
    ap.add_argument("--pad", type=float, default=0.06)
    ap.add_argument("--samples", type=int, default=8)
    ap.add_argument("--out")
    return ap.parse_args(argv[argv.index("--") + 1:] if "--" in argv else [])


def main():
    a = args(sys.argv)
    film = films.load(a.film)
    sys.path.insert(0, str(film.root / "blender"))
    mod = importlib.import_module(a.module)
    draw = getattr(mod, a.draw)
    times = [float(t) for t in a.times.split(",")]
    w, h = (int(v) for v in a.res.split("x"))
    out = Path(a.out) if a.out else film.repo / "out" / film.id / "cels" / f"{a.module.split('.')[-1]}-{a.draw}.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    sc.render.engine = "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = a.samples
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    world = sc.world or bpy.data.worlds.new("world")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*cels.linear(a.bg), 1.0)
    bg.inputs[1].default_value = 1.0
    cam = bpy.data.cameras.new("sheet")
    cam.type = "ORTHO"
    co = bpy.data.objects.new("sheet", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    co.rotation_euler = (math.pi / 2, 0, 0)

    tiles = []
    for i, t in enumerate(times):
        d = draw(t)
        ob = cels.build(f"cel{i}", d)
        if a.box:
            x0, y0, x1, y1 = (float(v) for v in a.box.split(","))
        else:
            x0, y0, x1, y1 = d.bounds()
        pw, ph = (x1 - x0) * (1 + 2 * a.pad), (y1 - y0) * (1 + 2 * a.pad)
        # an orthographic camera's scale spans the image's longer side
        cam.ortho_scale = max(pw, ph * w / h) if w >= h else max(ph, pw * h / w)
        co.location = ((x0 + x1) / 2, -10.0, (y0 + y1) / 2)
        path = out.with_name(f"{out.stem}.{i}.png")
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(path))
        px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
        bpy.data.images.remove(img)
        tiles.append(px)
        bpy.data.objects.remove(ob)
        path.unlink()
    sheet = np.concatenate(tiles, axis=1)
    img = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=True)
    img.pixels.foreach_set(sheet.ravel())
    img.filepath_raw = str(out)
    img.file_format = "PNG"
    img.save()
    print(f"celsheet: wrote {out}")


if __name__ == "__main__":
    main()
