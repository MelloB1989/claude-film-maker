"""Regression: an overlay's alpha-0 pixels must not tint the picture (Blender 5.2 does not premultiply Non-Color images).

Runs `blender -b` on itself: a grey background, an overlay PNG whose left half is gold RGB under alpha 0 and whose
right half is opaque red, composited by compositor.overlay_over. The left half must stay grey, the right turn red.
Skipped without Blender.

    pytest blender/tests/test_amv_scene_overlay.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
BLENDER = os.environ.get("BLENDER") or shutil.which("blender") or "/home/nikhil/code/film-making/bin/blender"


def inside_blender(out):
    import bpy
    import numpy as np
    sys.path.insert(0, str(ROOT / "blender"))
    sys.path.insert(0, str(ROOT / "tools"))
    from amv import compositor as C
    d = Path(out).parent
    w = h = 8
    px = np.zeros((h, w, 4), np.float32)
    px[:, :4] = (1.0, 168 / 255, 61 / 255, 0.0)   # the gold title's colour under alpha 0
    px[:, 4:] = (1.0, 0.0, 0.0, 1.0)
    src = bpy.data.images.new("ov", w, h, alpha=True, float_buffer=False)
    src.colorspace_settings.name = "Non-Color"
    src.alpha_mode = "STRAIGHT"
    src.pixels.foreach_set(px.ravel())
    src.filepath_raw = str(d / "0000.png")
    src.file_format = "PNG"
    src.save()
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cg = bpy.data.node_groups.new("t", "CompositorNodeTree")
    cg.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    sc.compositing_node_group = cg
    sc.render.use_compositing = True
    sc.render.compositor_device = "CPU"   # the GPU compositor needs EGL
    t = C.Tree(cg)
    bg = t.node("CompositorNodeRGB", "bg")
    bg.outputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
    nd = C.seq_node(t, C.sequence_image(d, 0), 0, 0, 1, "ov")
    res = C.overlay_over(t, bg.outputs[0], nd, "over", [(0, 1.0)], 1.0)
    go = t.node("NodeGroupOutput", "out")
    t.link(res, go.inputs[0])
    sc.frame_set(0)
    sc.render.filepath = str(d / "r.png")
    bpy.ops.render.render(write_still=True)
    r = bpy.data.images.load(str(d / "r.png"))
    got = np.empty(w * h * 4, np.float32)
    r.pixels.foreach_get(got)
    np.save(out, got.reshape(h, w, 4))


if "bpy" in sys.modules:
    inside_blender(sys.argv[sys.argv.index("--") + 1])
else:
    def test_alpha_zero_colour_does_not_tint():
        import pytest
        if not (Path(BLENDER).exists() or shutil.which(BLENDER)):
            pytest.skip("no blender")
        import numpy as np
        tmp = Path(tempfile.mkdtemp())
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(HERE), "--", str(tmp / "o.npy")],
                           capture_output=True, text=True, timeout=300)
        if not (tmp / "o.npy").exists():
            raise RuntimeError("blender failed:\n" + r.stdout[-1500:] + r.stderr[-1500:])
        got = np.load(tmp / "o.npy")
        left, right = got[:, :4, :3], got[:, 4:, :3]
        assert np.abs(left - left[0, 0]).max() < 1.5 / 255   # 8-bit output dither; the bug moved it ~50/255
        assert abs(left[0, 0] - left[0, 0, 0]).max() < 1e-3, f"background tinted: {left[0, 0]}"   # still grey
        assert right[0, 0] == pytest.approx((1.0, 0.0, 0.0), abs=0.02)
