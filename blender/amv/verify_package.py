"""Verify a packaged .blend: run from the delivery copy.

    blender -b --factory-startup <copy>/project/<id>.blend -P blender/amv/verify_package.py -- \
        --frames 100,640 --res-scale 0.25 --out <dir> --report report.json

Reports every image's stored filepath, the files that do not exist, and renders each frame (checking it for Blender's
missing-texture magenta and for a blank picture). It never fails on its own: filmtools.amv.package.verdict() decides.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--frames", required=True)
ap.add_argument("--res-scale", type=float, default=0.25)
ap.add_argument("--out", required=True)
ap.add_argument("--report", required=True)
ap.add_argument("--samples", type=int, default=16)
a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])

scene = bpy.context.scene
report = {"image_paths": [], "missing": [], "frames": []}
for img in bpy.data.images:
    if img.source not in ("FILE", "SEQUENCE", "MOVIE") or not img.filepath:
        continue
    report["image_paths"].append(img.filepath)
    if not Path(bpy.path.abspath(img.filepath)).exists():
        report["missing"].append(img.filepath)

scene.render.resolution_percentage = int(round(a.res_scale * 100))
if scene.render.engine == "CYCLES":
    scene.cycles.samples = a.samples
    scene.cycles.use_denoising = False
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
for f in [int(x) for x in a.frames.split(",")]:
    for ob in bpy.data.objects:        # as build.py's hide_for_frame: render only the planes live on this frame
        if "amv_range" in ob:
            lo, hi = ob["amv_range"]
            ob.hide_render = not (lo <= f <= hi)
    scene.frame_set(f)
    path = out / f"verify_{f:04d}.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(str(path), check_existing=False)
    w, h = im.size
    px = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    px = px.reshape(h, w, 4)[..., :3] * 255.0
    magenta = float(((px[..., 0] > 240) & (px[..., 1] < 24) & (px[..., 2] > 240)).mean())
    std, mean = float(px.std()), float(px.mean())
    report["frames"].append({"frame": f, "file": path.name, "magenta": magenta, "std": std, "mean": mean,
                             "blank": std < 3.0 or mean < 2.0})
Path(a.report).write_text(json.dumps(report, indent=1))
