"""The AMV Grade node group against its numpy twin: a synthetic ramp + colour chart through `blender -b`.

Run by pytest (spawns Blender; skipped when there is none) and, inside Blender, as the driver:
    blender -b --factory-startup -P blender/tests/test_amv_grade_blender.py -- <out.npy> <io> <res_scale> [params.json [images.npy]]
The driver renders the image through build_group() with the compositor on the CPU and saves the display-sRGB result.
With images.npy (N, H, W, 3 display-sRGB floats) it renders each of them instead (the contact sheets use this).
Blender needs libSM/libGL/libEGL; where the system lacks them point LD_LIBRARY_PATH at a directory that has them.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from filmtools.amv import grade_np as G  # noqa: E402

BLENDER = os.environ.get("BLENDER") or shutil.which("blender") or "/home/nikhil/code/film-making/bin/blender"
W, H = 480, 270


def make_test_image():
    """Display-sRGB test image: grey ramp, saturated and skin-tone patches, dark/bright patches, a few hard edges."""
    img = np.zeros((H, W, 3), np.float32)
    ramp = np.linspace(0, 1, W, dtype=np.float32)
    img[:60] = ramp[None, :, None]
    for c in range(3):   # R, G, B ramps in the next rows
        img[60 + 13 * c:60 + 13 * c + 13, :, c] = ramp[None, :]
    chart = [(0.9, 0.2, 0.15), (0.15, 0.7, 0.2), (0.2, 0.25, 0.9), (0.95, 0.85, 0.1), (0.1, 0.8, 0.85), (0.85, 0.2, 0.8),
             (0.76, 0.55, 0.45), (0.55, 0.38, 0.3), (0.06, 0.06, 0.08), (0.25, 0.25, 0.27), (0.6, 0.6, 0.62), (0.97, 0.97, 0.95)]
    pw = W // 6
    for i, c in enumerate(chart):
        r, k = divmod(i, 6)
        img[100 + 50 * r:100 + 50 * r + 50, k * pw:(k + 1) * pw] = c
    for x0 in range(0, W, 60):   # hard vertical edges of varying contrast in the bottom strip
        img[200:, x0:x0 + 30] = 0.1 + 0.8 * ((x0 // 60) % 2)
        img[200:, x0 + 30:x0 + 60] = (0.9, 0.35, 0.2) if (x0 // 60) % 3 == 0 else (0.2, 0.45, 0.8)
    img = np.clip(img, 0, 1)
    img[H - 20:, :60] = (3.7, 1.9, 0.37)   # an overexposed (flash) patch: scene-linear values above 1 as display floats
    return img


def render_group(img_display, io="linear", params=None, res_scale=0.25):
    """Inside Blender: `img_display` through build_group(); returns display-sRGB float RGB (H, W, 3)."""
    import bpy
    sys.path.insert(0, str(ROOT / "blender"))
    from amv import grade
    h, w, _ = img_display.shape
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.view_settings.view_transform = "Standard"
    sc.render.compositor_device = "CPU"
    sc.render.image_settings.file_format, sc.render.image_settings.color_depth = "OPEN_EXR", "32"
    data = img_display if io == "srgb" else G.srgb_to_linear(img_display)   # (values > 1 allowed)
    im = bpy.data.images.new("grade_in", w, h, alpha=True, float_buffer=True)
    im.colorspace_settings.name = "Linear Rec.709"
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = data
    im.pixels.foreach_set(rgba.ravel())
    im.update()
    group = grade.build_group(dict(params or {}, io=io, res_scale=res_scale))
    comp = bpy.data.node_groups.new("comp", "CompositorNodeTree")
    sc.compositing_node_group = comp
    n_img, n_grp = comp.nodes.new("CompositorNodeImage"), comp.nodes.new("CompositorNodeGroup")
    n_img.image, n_grp.node_tree = im, group
    comp.links.new(n_img.outputs[0], n_grp.inputs[0])
    comp.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    comp.links.new(n_grp.outputs[0], comp.nodes.new("NodeGroupOutput").inputs[0])
    out = Path(tempfile.mkdtemp()) / "out.exr"
    sc.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    res = bpy.data.images.load(str(out))
    res.colorspace_settings.name = "Linear Rec.709"
    a = np.empty(w * h * 4, np.float32)
    res.pixels.foreach_get(a)
    x = a.reshape(h, w, 4)[..., :3]
    return x if io == "srgb" else G.linear_to_srgb(x)


def _driver():
    args = sys.argv[sys.argv.index("--") + 1:]
    out, io, res = args[0], args[1], float(args[2])
    params = json.loads(Path(args[3]).read_text()) if len(args) > 3 else None
    params = params.get("fitted", params) if params else None
    if len(args) > 4:
        imgs = np.load(args[4]).astype(np.float32)
        np.save(out, np.array([render_group(i, io, params, res) for i in imgs]))
    else:
        np.save(out, render_group(make_test_image(), io, params, res))


def _run_blender(io, params=None, res=0.25):
    tmp = Path(tempfile.mkdtemp())
    cmd = [BLENDER, "-b", "--factory-startup", "-P", str(Path(__file__)), "--", str(tmp / "o.npy"), io, str(res)]
    if params:
        (tmp / "p.json").write_text(json.dumps(params))
        cmd.append(str(tmp / "p.json"))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if not (tmp / "o.npy").exists():
        raise RuntimeError("blender failed:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    return np.load(tmp / "o.npy")


def _need_blender():
    import pytest
    if not (Path(BLENDER).exists() or shutil.which(BLENDER)):
        pytest.skip("no blender")


def _check(io, params=None):
    _need_blender()
    img = make_test_image()
    got = _run_blender(io, params)
    want = G.grade(img, params, 0.25)
    err = np.abs(got - want) * 255
    assert err.max() <= 3.0, f"max err {err.max():.2f}/255 at {np.unravel_index(err.argmax(), err.shape)}, mean {err.mean():.3f}"


def test_group_matches_numpy_srgb_io():
    _check("srgb")


def test_group_matches_numpy_linear_io():
    _need_blender()
    img = make_test_image()
    got = _run_blender("linear")
    want = G.linear_to_srgb(G.grade_linear(G.srgb_to_linear(img), None, 0.25))
    assert (np.abs(got - want) * 255).max() <= 3.0


def test_group_with_fitted_style_params():
    _check("srgb", {"saturation": 120.0, "contrast": 10.0, "glow_intensity": 0.5, "vig_amount": 0.5, "hi_desat": 0.6, "rolloff_power": 2.5, "curve1": -0.05, "curve2": 0.08, "curve3": -0.04,
                    "cb": [5, -4, 8, 0, 3, -2, -6, 4, 9]})


if __name__ == "__main__" or "bpy" in sys.modules:
    try:
        import bpy  # noqa: F401
        if "--" in sys.argv:
            _driver()
    except ImportError:
        pass
