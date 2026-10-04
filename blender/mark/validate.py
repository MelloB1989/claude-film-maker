"""The mark's acceptance: an orthographic front render of the woven mark's silhouette against mark.png's.

  /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/mark/validate.py [-- --out out/look/mark]

Builds the finished mark exactly as the shot does (build.mark: the four threads at rest), frames mark.png's 256 px
square with an orthographic camera looking straight at it, renders alpha at 5x (1280 px, a sharp pixel filter),
averages each 5x5 block to one reference pixel, thresholds at 0.5 and compares with the reference silhouette
(geometry.reference: alpha > 0.5, the mark's own region). Prints the IoU (acceptance: >= 0.90) and writes the
silhouette diff (grey both, red render only, blue reference only) and a front beauty still to --out.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from lib import export, lights, setup  # noqa: E402
from mark import build, geometry as G  # noqa: E402
from mark.png import read_png  # noqa: E402

SS = 5


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(export.REPO / "out" / "look" / "mark"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    res = G.SIZE * SS
    scene = setup.new_scene((res, res), samples=16, motion_blur=0, transparent=True)
    scene.cycles.filter_width = 0.01
    scene.cycles.use_denoising = False
    root = bpy.data.objects.new("mark", None)
    root.scale = (build.MU,) * 3
    scene.collection.objects.link(root)
    obs = build.mark(parent=root)

    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = G.SIZE * build.MU
    cam.location = (0.0, -1.0, 0.0)
    cam.rotation_euler = (np.pi / 2, 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    lights.studio(key=60.0, rim=None, fill=10.0, world=None, scale=0.4)

    bpy.ops.render.render()
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "sil.png"
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.image_settings.color_depth = "16"
        bpy.data.images["Render Result"].save_render(str(png), scene=scene)
        img = bpy.data.images.load(str(png))
        px = np.empty(res * res * 4, np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(res, res, 4)[::-1]
    alpha = px[..., 3]
    cov = alpha.reshape(G.SIZE, SS, G.SIZE, SS).mean(axis=(1, 3))
    ref = G.reference()
    iou = G.iou(cov, ref)
    m = cov > 0.5
    diff = np.zeros((G.SIZE, G.SIZE, 4), np.uint8)
    diff[..., 3] = 255
    diff[m & ref, :3] = 200
    diff[m & ~ref, :3] = (255, 40, 40)
    diff[~m & ref, :3] = (40, 120, 255)
    export.write_png(out / "silhouette_diff.png", np.repeat(np.repeat(diff, 4, 0), 4, 1))
    beauty = np.clip(px[..., :3], 0, 1)
    export.write_png(out / "front_ortho.png", np.concatenate(
        [export.srgb8(beauty), np.round(np.clip(alpha, 0, 1) * 255).astype(np.uint8)[..., None]], axis=2))
    print(f"[mark] 2D model IoU {G.iou(G.silhouette(), ref):.4f}")
    print(f"[mark] front orthographic silhouette vs mark.png: IoU {iou:.4f} "
          f"(render only {int((m & ~ref).sum())} px, reference only {int((~m & ref).sum())} px, "
          f"reference {int(ref.sum())} px) -> {out / 'silhouette_diff.png'}")
    print(f"[mark] {'PASS' if iou >= 0.90 else 'FAIL'}: IoU {iou:.4f} (acceptance >= 0.90)")
    return iou


if __name__ == "__main__":
    import traceback

    try:
        main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    except BaseException:
        traceback.print_exc()
        sys.exit(1)
