"""The AMV compositor: what AE did to the whole comp after the shots (build.jsx 153-244), as one node tree.

    Render Layers (scene-linear Cycles result)
      -> Exposure, keyed per frame from `flash_ev`            (AE's Exposure works in linear light)
      -> 1-frame black solids at `black[]`
      -> `invert[]` frames: invert, then tint black #010105 -> white #C7DAE8 (the duotone)
      -> `halftone[]` frames (2 each): a dot grid, each cell a dot of the cell's colour (CC Ball Action, grid 13)
      -> linear -> sRGB: from here on every value is display-referred, as AE's 8-bit project blended
      -> the `AMV Grade` node group (blender/amv/grade.py, else a pass-through), ending at `outro.f`
      -> letterbox bars (`bars[f]` px top and bottom), `accents` lines, screen titles, the glint with its glow and
         bloom, the watermark, and from `outro.f` the outro frames on top
      -> sRGB -> linear, to the Group Output (the view transform Standard re-encodes it exactly).

Overlays are read raw (colour space Non-Color, straight alpha premultiplied on load) so they composite in the sRGB
domain like AE's. Image-sequence nodes are frame-exact: the node's start / offset make file number k appear on the
frame it belongs to, and a keyed Alpha Over factor is 0 outside the window. A missing overlay is skipped with a
warning, so the build works before titles / outro exist.

The grade group's contract (agreed with blender/amv/grade.py): Image in / Image out, display-referred sRGB floats,
`build_group({"io": "srgb"})`.
"""
from __future__ import annotations

import importlib
import math
from pathlib import Path

import bpy

from . import scene as S

GRADE_NAME = "AMV Grade"
INVERT_BLACK, INVERT_WHITE = "#010105", "#C7DAE8"
ACCENT_TINT = "#EEB6BF"
BLOOM_TINT = "#9FD8FF"
WM_OPACITY = 62.0
HALFTONE_GRID = 13
HALFTONE_FRAMES = 2
LINEAR, SRGB = "Linear Rec.709", "sRGB"


def hex_rgb(h: str):
    """'#RRGGBB' -> sRGB-encoded floats (r, g, b): AE colours are display values and the tree works in them here."""
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class Tree:
    """A small builder over a compositor node tree: nodes are laid out left to right as they are made."""

    def __init__(self, tree):
        self.tree = tree
        self.res_scale = 1.0
        self.n = tree.nodes
        self.x = 0

    def node(self, kind, name=None, dx=220, **props):
        nd = self.n.new(kind)
        if name:
            nd.name = nd.label = name
        for k, v in props.items():
            setattr(nd, k, v)
        self.x += dx
        nd.location = (self.x, 0)
        return nd

    def link(self, a, b):
        self.tree.links.new(a, b)

    def mix(self, a, b, fac=None, name=None, blend="MIX"):
        """Mix colour node: a, b are output sockets (or an rgb tuple); fac an output socket, a number, or None (1)."""
        m = self.node("ShaderNodeMix", name, data_type="RGBA", blend_type=blend, clamp_factor=False)
        for i, v in ((6, a), (7, b)):
            if isinstance(v, tuple):
                m.inputs[i].default_value = (*v, 1.0)
            else:
                self.link(v, m.inputs[i])
        if fac is not None and not isinstance(fac, (int, float)):
            self.link(fac, m.inputs[0])
        else:
            m.inputs[0].default_value = 1.0 if fac is None else fac
        return m

    def convert(self, img, src, dst, name=None):
        c = self.node("CompositorNodeConvertColorSpace", name, from_color_space=src, to_color_space=dst)
        self.link(img, c.inputs[0])
        return c.outputs[0]

    def over(self, bg, fg, factor=1.0, name=None):
        o = self.node("CompositorNodeAlphaOver", name)
        self.link(bg, o.inputs[0])
        self.link(fg, o.inputs[1])
        o.inputs[2].default_value = factor
        return o


def grade_group(log=print):
    """The `AMV Grade` node group: grade.build_group if grade.py exists, else a pass-through with the same sockets."""
    old = bpy.data.node_groups.get(GRADE_NAME)
    if old is not None:
        bpy.data.node_groups.remove(old)
    tree = None
    try:
        grade = importlib.import_module("amv.grade")
        try:
            tree = grade.build_group({"io": "srgb"})
        except TypeError:
            tree = grade.build_group()
        tree.name = GRADE_NAME
        log("compositor: grade node group from amv/grade.py")
    except ModuleNotFoundError as e:
        if e.name not in ("amv.grade", "amv"):
            raise
    if tree is None:
        tree = bpy.data.node_groups.new(GRADE_NAME, "CompositorNodeTree")
        tree.interface.new_socket("Image", in_out="INPUT", socket_type="NodeSocketColor")
        tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        gi, go = tree.nodes.new("NodeGroupInput"), tree.nodes.new("NodeGroupOutput")
        go.location = (300, 0)
        tree.links.new(gi.outputs[0], go.inputs[0])
        log("compositor: no amv/grade.py yet, the grade group is a pass-through placeholder")
    return tree


def sequence_image(folder: Path, first: int, ext="png", name=None):
    """An image sequence from files `<k>.png` (k from `first`) read raw (straight alpha, Non-Color), or None."""
    f = Path(folder) / f"{first:04d}.{ext}"
    if not f.exists():
        return None
    img = bpy.data.images.load(str(f), check_existing=True)
    img.source = "SEQUENCE"
    img.alpha_mode = "STRAIGHT"
    img.colorspace_settings.name = "Non-Color"
    return img


def count_files(folder: Path, first: int) -> int:
    n = 0
    while (Path(folder) / f"{first + n:04d}.png").exists():
        n += 1
    return n


def seq_node(t: Tree, img, first_file: int, at_frame: int, count: int, name: str):
    """An Image node showing file `first_file + i` on comp frame `at_frame + i` (i >= 0; held outside)."""
    nd = t.node("CompositorNodeImage", name, dx=0)
    nd.image = img
    nd.frame_start = at_frame
    nd.frame_duration = count
    nd.frame_offset = first_file - 1
    nd.use_cyclic = False
    nd.use_auto_refresh = True
    return nd


def window_keys(a: int, b: int):
    """(frame, 0/1): 1 on [a, b), constant keys."""
    return [(a - 1, 0.0), (a, 1.0), (b, 0.0)]


def build(built, overlays_dir=None, res_scale=1.0, log=print):
    """Build the compositor of `built` (scene.Built) and make it the scene's. Returns the Tree."""
    scene, plan = built.scene, built.plan
    raw = plan.raw
    ov = Path(S.absolute(overlays_dir)) if overlays_dir else None
    cg = bpy.data.node_groups.new("AMV Compositor", "CompositorNodeTree")
    cg.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    scene.compositing_node_group = cg
    scene.render.use_compositing = True
    t = Tree(cg)
    t.res_scale = res_scale
    outro_f = raw["outro"]["f"]
    W, H = S.W, S.H

    # ---- the shots, linear
    rl = t.node("CompositorNodeRLayers", "Render", scene=scene)
    img = rl.outputs["Image"]
    if raw.get("flash_ev"):
        ex = t.node("CompositorNodeExposure", "flash exposure")
        t.link(img, ex.inputs[0])
        S.key_socket(ex, 1, [(f, v) for f, v in raw["flash_ev"]], "LINEAR")
        img = ex.outputs[0]
    if raw.get("black"):
        m = t.mix(img, (0.0, 0.0, 0.0), 0.0, "black strobes")
        S.key_socket(m, 0, [(f + d, 1.0 if d == 0 else 0.0) for f in raw["black"] for d in (-1, 0, 1)], "CONSTANT")
        img = m.outputs[2]
    if raw.get("invert"):
        s = t.convert(img, LINEAR, SRGB, "to sRGB (invert)")
        iv = t.node("CompositorNodeInvert", "invert")
        t.link(s, iv.inputs[0])
        iv.inputs[2].default_value = True     # colour
        iv.inputs[3].default_value = False    # not alpha
        lum = t.node("CompositorNodeRGBToBW", "luma")
        t.link(iv.outputs[0], lum.inputs[0])
        duo = t.mix(hex_rgb(INVERT_BLACK), hex_rgb(INVERT_WHITE), lum.outputs[0], "duotone")
        back = t.convert(duo.outputs[2], SRGB, LINEAR, "to linear (invert)")
        m = t.mix(img, back, 0.0, "invert strobes")
        S.key_socket(m, 0, [(f + d, 1.0 if d == 0 else 0.0) for f in raw["invert"] for d in (-1, 0, 1)], "CONSTANT")
        img = m.outputs[2]
    if raw.get("halftone"):
        img = halftone(t, img, raw["halftone"], scene, res_scale)

    # ---- display-referred from here
    img = t.convert(img, LINEAR, SRGB, "to sRGB")
    grp = t.node("CompositorNodeGroup", "grade")
    grp.node_tree = grade_group(log)
    t.link(img, grp.inputs[0])
    gm = t.mix(img, grp.outputs[0], 1.0, "grade until outro")
    S.key_socket(gm, 0, [(outro_f - 1, 1.0), (outro_f, 0.0)], "CONSTANT")
    img = gm.outputs[2]

    img = bars(t, img, raw, plan)
    for A in raw.get("accents") or []:
        img = accent(t, img, A)
    for i, T in enumerate(raw.get("titles") or []):
        img = screen_title(t, img, ov, i, T, log)
    if built.glints:
        img = glint(t, img, rl, log)
    img = watermark(t, img, ov, plan, log)
    img = outro(t, img, ov, raw["outro"], plan.dur, log)

    out = t.convert(img, SRGB, LINEAR, "to linear")
    go = t.node("NodeGroupOutput", "Output")
    t.link(out, go.inputs[0])
    return t


def halftone(t: Tree, img, frames, scene, res_scale):
    """CC Ball Action grid 13: pixelate to cells and keep a round dot of each cell's colour on black, for 2 frames."""
    import numpy as np
    cell = max(2, round(HALFTONE_GRID * res_scale))
    s = t.convert(img, LINEAR, SRGB, "to sRGB (halftone)")
    px = t.node("CompositorNodePixelate", "cells")
    px.inputs[1].default_value = cell
    t.link(s, px.inputs[0])
    w, h = scene.render.resolution_x, scene.render.resolution_y
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    fx, fy = (xx % cell) - (cell - 1) / 2.0, (yy % cell) - (cell - 1) / 2.0
    r = np.hypot(fx, fy)
    dots = np.clip((cell * 0.46 + 0.5) - r, 0.0, 1.0)
    rgba = np.repeat(dots[..., None], 4, axis=2)
    rgba[..., 3] = 1.0
    im = bpy.data.images.new("halftone dots", w, h, alpha=False, float_buffer=False)
    im.colorspace_settings.name = "Non-Color"
    im.pixels.foreach_set(rgba.ravel())
    im.pack()
    dn = t.node("CompositorNodeImage", "dot grid")
    dn.image = im
    m = t.mix(px.outputs[0], (0.0, 0.0, 0.0), dn.outputs[0], "halftone dots", blend="MIX")
    # colour x dot: a = cell colour, b = black, factor = 1 - dot  -> colour inside the dot, black outside
    inv = t.node("ShaderNodeMath", "1-dot", operation="SUBTRACT")
    inv.inputs[0].default_value = 1.0
    t.link(dn.outputs[0], inv.inputs[1])
    t.link(inv.outputs[0], m.inputs[0])
    back = t.convert(m.outputs[2], SRGB, LINEAR, "to linear (halftone)")
    sel = t.mix(img, back, 0.0, "halftone frames")
    keys = []
    for f in frames:
        keys += [(f - 1, 0.0), (f, 1.0), (f + HALFTONE_FRAMES, 0.0)]
    S.key_socket(sel, 0, keys, "CONSTANT")
    return sel.outputs[2]


def bars(t: Tree, img, raw, plan):
    """Letterbox bars: `bars[f]` px of black at the top and the bottom, keyed every frame (until the outro)."""
    vals = raw.get("bars") or []
    if not any(vals):
        return img
    outro_f = raw["outro"]["f"]
    H = S.H
    frames = range(0, min(len(vals), outro_f + 1))
    top = t.node("CompositorNodeBoxMask", "bar top")
    bot = t.node("CompositorNodeBoxMask", "bar bottom")
    for nd, sign in ((top, +1), (bot, -1)):
        nd.inputs[1].default_value = 0.0          # Mask in
        nd.inputs[2].default_value = 1.0          # Value inside
        nd.inputs[4].default_value = (1.2, 0.0)      # wider than the frame: the first pixel column is inside
    t.link(top.outputs[0], bot.inputs[1])
    # normalised: y up from the bottom; a bar of b px at the top spans y in [1 - b/H, 1], centre 1 - b/2H
    S.key_socket(top, 3, [(f, 1.0 - vals[f] / 2.0 / H) for f in frames], "LINEAR", index=1)
    S.key_socket(top, 4, [(f, vals[f] / H) for f in frames], "LINEAR", index=1)
    S.key_socket(bot, 3, [(f, vals[f] / 2.0 / H) for f in frames], "LINEAR", index=1)
    S.key_socket(bot, 4, [(f, vals[f] / H) for f in frames], "LINEAR", index=1)
    for nd in (top, bot):
        nd.inputs[3].default_value[0] = 0.5
    m = t.mix(img, (0.0, 0.0, 0.0), bot.outputs[0], "letterbox")
    return m.outputs[2]


def accent(t: Tree, img, A):
    """An accent line (build.jsx 205-213): white 9 px at y, width [[f,96],[f+8,1250],[f+n,1700]] centred on x=960,
    tinted to #EEB6BF over n frames, opacity 100 -> 90 -> 0, on [f, f+n)."""
    H, W = S.H, S.W
    f, n, y = A["f"], A["n"], A["y"]
    frames = range(f, f + n)
    wk = [(f, 96.0), (f + 8, 1250.0), (f + n, 1700.0)]

    def width(fr):
        return amv_keys(wk, fr)

    def opac(fr):
        return amv_keys([(f, 100.0), (f + n - 4, 90.0), (f + n, 0.0)], fr)
    b = t.node("CompositorNodeBoxMask", f"accent {f}@{y}")
    b.inputs[1].default_value = 0.0
    b.inputs[3].default_value = (0.5, 1.0 - y / H)
    S.key_socket(b, 4, [(fr, width(fr) / W) for fr in frames], "LINEAR", index=0)
    b.inputs[4].default_value[1] = 9.0 / H
    S.key_socket(b, 2, [(fr, opac(fr) / 100.0) for fr in list(frames) + [f + n]] + [(f - 1, 0.0)], "LINEAR")
    tint = hex_rgb(ACCENT_TINT)
    m = t.mix((1.0, 1.0, 1.0), tint, 0.0, f"accent colour {f}@{y}")
    S.key_socket(m, 0, [(f, 0.0), (f + n, 1.0)], "LINEAR")
    o = t.mix(img, m.outputs[2], b.outputs[0], f"accent over {f}@{y}")
    return o.outputs[2]


def amv_keys(keys, f):
    from filmtools.amv import plan as amv_plan
    return amv_plan.keys_lin(keys, f)


def fit(t: Tree, nd):
    """The overlay's Image output, scaled from its 1920x1080 file to the render size (a no-op at full size)."""
    if abs(t.res_scale - 1.0) < 1e-6:
        return nd.outputs["Image"]
    sc = t.node("CompositorNodeScale", f"{nd.name} to render size")
    sc.inputs["X"].default_value = sc.inputs["Y"].default_value = t.res_scale
    t.link(nd.outputs["Image"], sc.inputs[0])
    return sc.outputs[0]


def overlay_over(t: Tree, img, nd, name, factor_keys, factor=0.0):
    o = t.over(img, fit(t, nd), factor, name)
    S.key_socket(o, 2, factor_keys, "LINEAR" if factor_keys and len(factor_keys) > 4 else "CONSTANT")
    return o.outputs[0]


def screen_title(t: Tree, img, ov, i, T, log):
    """A screen title: `titles/screen.<i>/<k>.png`, k = f - f_in for 0 <= k < dur."""
    if ov is None:
        return img
    folder = ov / "titles" / f"screen.{i}"
    seq = sequence_image(folder, 0)
    if seq is None:
        log(f"WARNING: no screen title frames in {folder}: skipped")
        return img
    f_in, dur = T["f_in"], T["spec"]["dur"]
    nd = seq_node(t, seq, 0, f_in, max(1, min(dur, count_files(folder, 0))), f"screen title {i}")
    return overlay_over(t, img, nd, f"title {i} over", window_keys(f_in, f_in + dur))


def watermark(t: Tree, img, ov, plan, log):
    """The watermark still at 62 % with the wm_hide fades, until the outro."""
    if ov is None:
        return img
    f = ov / "titles" / "watermark" / "0000.png"
    if not f.exists():
        log(f"WARNING: no watermark {f}: skipped")
        return img
    im = bpy.data.images.load(str(f), check_existing=True)
    im.alpha_mode = "STRAIGHT"
    im.colorspace_settings.name = "Non-Color"
    nd = t.node("CompositorNodeImage", "watermark", dx=0)
    nd.image = im
    outro_f = plan.raw["outro"]["f"]
    keys = [(fr, v / 100.0) for fr, v in S.wm_keys(plan) if fr < outro_f] + [(outro_f, 0.0)]
    o = t.over(img, fit(t, nd), 0.0, "watermark over")
    S.key_socket(o, 2, keys, "LINEAR")
    return o.outputs[0]


def outro(t: Tree, img, ov, O, dur, log):
    """The outro frames `outro/<f>.png` (comp frames outro.f .. dur-1) opaque on top."""
    if ov is None:
        return img
    folder = ov / "outro"
    f0 = O["f"]
    seq = sequence_image(folder, f0)
    if seq is None:
        log(f"WARNING: no outro frames in {folder} (from {f0:04d}.png): skipped")
        return img
    nd = seq_node(t, seq, f0, f0, max(1, min(dur - f0, count_files(folder, f0))), "outro")
    return overlay_over(t, img, nd, "outro over", [(f0 - 1, 0.0), (f0, 1.0)])


def glint(t: Tree, img, rl, log):
    """Add the glint AOV with its glow (white, AE glow 20/20/1.2) and bloom (#9FD8FF, 10/60/0.5), additive."""
    try:
        g = rl.outputs["glint"]
    except KeyError:
        log("WARNING: the render has no glint AOV: glint skipped")
        return img
    s = t.convert(g, LINEAR, SRGB, "glint to sRGB")
    out = t.mix(img, s, 1.0, "glint add", blend="ADD").outputs[2]
    for name, ty, size, strength, tint in (("glint glow", "Fog Glow", 7, 1.2, (1.0, 1.0, 1.0)),
                                           ("glint bloom", "Bloom", 8, 0.5, hex_rgb(BLOOM_TINT))):
        gl = t.node("CompositorNodeGlare", name)
        gl.inputs["Type"].default_value = ty
        gl.inputs["Threshold"].default_value = 0.0
        gl.inputs["Size"].default_value = size / 9.0 if ty == "Bloom" else size
        gl.inputs["Strength"].default_value = strength
        t.link(s, gl.inputs[0])
        col = t.mix(gl.outputs["Glare"], tint, 1.0, name + " tint", blend="MULTIPLY")
        out = t.mix(out, col.outputs[2], 1.0, name + " add", blend="ADD").outputs[2]
    return out
