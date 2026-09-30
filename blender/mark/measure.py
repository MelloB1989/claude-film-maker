"""Plate exposure check: per-material brightness of a B15 plate (linear EXR), as the engine will see it.

  /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/mark/measure.py -- out/plates/b15_weave/0201.exr

Classifies pixels by chroma and hue (bone: low chroma; blood: red; moss: green) and prints each class's median and
95th percentile per channel, and its brightest channel's 99th percentile: bone should sit near its albedo (about 0.8
at its brightest, never past 1), blood and moss near their palette values where lit.
"""
import sys

import bpy
import numpy as np

path = sys.argv[sys.argv.index("--") + 1]
img = bpy.data.images.load(path)
w, h = img.size
px = np.empty(w * h * 4, np.float32)
img.pixels.foreach_get(px)
px = px.reshape(-1, 4)
rgb, a = px[:, :3], px[:, 3]
mx, mn = rgb.max(1), rgb.min(1)
ch = (mx - mn) / np.maximum(mx, 1e-5)
lit = mx > 0.05
classes = {
    "bone": lit & (ch < 0.3),
    "blood": lit & (ch >= 0.5) & (rgb[:, 0] >= mx - 1e-6),
    "moss": lit & (ch >= 0.4) & (rgb[:, 1] >= mx - 1e-6),
}
for k, m in classes.items():
    if m.sum() == 0:
        print(f"[measure] {k}: none")
        continue
    v = rgb[m]
    print(f"[measure] {k}: {int(m.sum())} px, median {np.round(np.median(v, 0), 3)}, p95 {np.round(np.percentile(v, 95, 0), 3)}, "
          f"max-channel p99 {np.percentile(v.max(1), 99):.3f}")
