"""The AMV grade as a compositor node group: `build_group(params)` -> the node tree "AMV Grade".

It is the node-graph twin of `tools/filmtools/amv/grade_np.py` (read its docstring for the chain and why each op is
what it is): the same arithmetic, node for node, so the two agree to ~2/255. The film's fitted values live in
`films/<id>/amv/grade.json` (`load_params`); `build_group()` without arguments uses the Premium Glow preset's own.

Sockets: one Image in, one Image out (RGBA; alpha is passed through, colour is treated as opaque). `params["io"]`:
`"linear"` (default) takes and returns scene-linear Blender data and converts to display sRGB inside, because the After
Effects project graded 8-bit display values; `"srgb"` takes and returns display-encoded values (the caller converts).
`params["res_scale"]` scales the blur sizes for a render below 1920 wide (1 = full size).

Everything is Vector Math / Math / Blur / Convert Colorspace nodes working on RGB as a 3-vector, built by the small
`_B` helper (operands are sockets or python numbers / 3-sequences, which become node defaults). Runs headless in `blender -b`.
Importable without bpy (for `load_params` and the numpy comparison) until `build_group` is called.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "tools"))
from filmtools.amv import grade_np as G  # noqa: E402  (the numpy twin: constants and parameters are shared)

GROUP_NAME = "AMV Grade"


def load_params(path):
    """The `fitted` parameters of a grade.json (or the file's top level when it has no `fitted` key)."""
    d = json.loads(Path(path).read_text())
    return d.get("fitted", d)


class _B:
    """Node builder: vector ops on RGB (`vm`), scalar ops (`m`), blur, colour-space conversion."""

    def __init__(self, tree):
        self.t = tree
        self.n = 0

    def _set(self, sock, v):
        if hasattr(v, "node"):
            self.t.links.new(v, sock)
        elif sock.bl_idname == "NodeSocketVector":
            sock.default_value = tuple(v) if hasattr(v, "__len__") else (float(v),) * 3
        else:
            sock.default_value = float(v)

    def vm(self, op, a, b=None, c=None, scale=None, out="Vector"):
        node = self.t.nodes.new("ShaderNodeVectorMath")
        node.operation = op
        node.location = (200 * (self.n % 40), -150 * (self.n // 40))
        self.n += 1
        for sock, v in zip(node.inputs[:3], (a, b, c)):
            if v is not None:
                self._set(sock, v)
        if scale is not None:
            self._set(node.inputs[3], scale)
        return node.outputs[out]

    def m(self, op, a, b=None, c=None, clamp=False):
        node = self.t.nodes.new("ShaderNodeMath")
        node.operation = op
        node.use_clamp = clamp
        node.location = (200 * (self.n % 40), -150 * (self.n // 40))
        self.n += 1
        for sock, v in zip(node.inputs, (a, b, c)):
            if v is not None:
                self._set(sock, v)
        return node.outputs[0]

    # vector shorthands
    def add(self, a, b):
        return self.vm("ADD", a, b)

    def sub(self, a, b):
        return self.vm("SUBTRACT", a, b)

    def mul(self, a, b):
        return self.vm("MULTIPLY", a, b)

    def mulc(self, a, k):
        return self.vm("MULTIPLY", a, (k, k, k))

    def clip01(self, a):
        return self.vm("MINIMUM", self.vm("MAXIMUM", a, (0, 0, 0)), (1, 1, 1))

    def luma(self, a):
        return self.vm("DOT_PRODUCT", a, G.LUMA, out="Value")

    def spread(self, s):
        """A scalar as a grey 3-vector."""
        return self.vm("SCALE", (1, 1, 1), scale=s)

    def blur(self, col, size):
        node = self.t.nodes.new("CompositorNodeBlur")
        self.t.links.new(col, node.inputs["Image"])
        node.inputs["Size"].default_value = (float(size), float(size))
        node.inputs["Type"].default_value = "Gaussian"
        return node.outputs["Image"]

    def convert(self, col, a, b):
        node = self.t.nodes.new("CompositorNodeConvertColorSpace")
        node.from_color_space, node.to_color_space = a, b
        self.t.links.new(col, node.inputs["Image"])
        return node.outputs["Image"]


# ---- the chain, one function per op of grade_np ----

def _rolloff(b, x, strength, power, sep):
    """grade_np.rolloff_in: m = max channel; x/m^2 + (1 - 1/m) for m > 1, mixed with the plain clip by `strength`."""
    clipped = b.clip01(x)
    if strength == 0:
        return clipped
    m = b.m("MAXIMUM", b.m("MAXIMUM", sep.outputs["Red"], sep.outputs["Green"]), b.m("MAXIMUM", sep.outputs["Blue"], 1.0))
    m = b.m("MAXIMUM", m, 1.0)
    inv = b.m("DIVIDE", 1.0, m)
    ip = b.m("POWER", inv, power)
    roll = b.add(b.vm("SCALE", x, scale=b.m("MULTIPLY", inv, ip)), b.spread(b.m("SUBTRACT", 1.0, ip)))
    return b.clip01(b.add(clipped, b.mulc(b.sub(roll, clipped), strength)))


def _sharpen(b, x, amount, size):
    if size < 1 or amount == 0:
        return x
    return b.clip01(b.add(x, b.mulc(b.sub(x, b.blur(x, size)), amount)))


def _colorista(b, x, strength):
    l = b.luma(x)
    om = b.m("SUBTRACT", 1.0, l)
    ws = b.m("MULTIPLY", om, om)
    wm = b.m("MULTIPLY", b.m("MULTIPLY", l, om), 4.0)
    sh = tuple(v - 1 for v in G.COLORISTA_SHADOWS)
    mi = tuple(v - 1 for v in G.COLORISTA_MIDS)
    d = b.add(b.vm("SCALE", sh, scale=ws), b.vm("SCALE", mi, scale=wm))
    gain = b.add(b.mulc(d, strength), (1, 1, 1))
    return b.clip01(b.mul(x, gain))


def _vignette(b, x, amount, size):
    coords = b.t.nodes.new("CompositorNodeImageCoordinates")
    b.t.links.new(x, coords.inputs["Image"])
    d = b.mul(b.sub(coords.outputs["Normalized"], (0.5, 0.5, 0.0)), (math.sqrt(2), math.sqrt(2), 0.0))
    rho = b.vm("LENGTH", d, out="Value")
    t = b.m("MULTIPLY", b.m("SUBTRACT", rho, size), 1.0 / (1.0 - size), clamp=True)
    gain = b.m("ADD", b.m("MULTIPLY", b.m("MULTIPLY", t, t), -amount), 1.0)
    return b.clip01(b.vm("SCALE", x, scale=gain))


def _lumetri(b, x, p):
    s_sh, s_hi, s_wh = p["shadows"] / 100, p["highlights"] / 100, p["whites"] / 100
    s_bl, s_c = p["blacks"] / 100, p["contrast"] / 100
    omx = b.vm("SUBTRACT", (1, 1, 1), x)
    xx = b.mul(x, x)
    t1 = b.mulc(b.mul(b.mul(x, omx), omx), G.K_SH * s_sh * 6.75)
    t2 = b.mulc(b.mul(xx, omx), G.K_HI * s_hi * 6.75)
    t3 = b.mulc(b.mul(xx, x), G.K_WH * s_wh)
    t4 = b.mulc(b.mul(b.mul(omx, omx), omx), G.K_BL * s_bl)
    y = b.clip01(b.add(b.add(b.add(x, t1), b.add(t2, t3)), t4))
    smooth = b.mul(b.mul(y, y), b.vm("MULTIPLY_ADD", y, (-2, -2, -2), (3, 3, 3)))
    return b.clip01(b.add(y, b.mulc(b.sub(smooth, y), G.K_CON * s_c)))


def _saturate(b, x, sat):
    l = b.spread(b.luma(x))
    return b.clip01(b.add(l, b.mulc(b.sub(x, l), sat / 100.0)))


def _hi_desat(b, x, amount):
    if amount == 0:
        return x
    l = b.luma(x)
    t = b.m("MULTIPLY_ADD", l, 4.0, -3.0, clamp=True)            # clip((l - 0.75) / 0.25)
    t2 = b.m("MULTIPLY", t, t)
    w = b.m("MULTIPLY", t2, b.m("MULTIPLY_ADD", t, -2.0, 3.0))   # t^2 (3 - 2t)
    return b.clip01(b.add(x, b.vm("SCALE", b.sub(b.spread(l), x), scale=b.m("MULTIPLY", w, amount))))


def _curve(b, x, c1, c2, c3):
    if c1 == c2 == c3 == 0:
        return x
    u = b.mul(x, b.vm("SUBTRACT", (1, 1, 1), x))
    w = b.vm("MULTIPLY_ADD", x, (-2, -2, -2), (1, 1, 1))
    inner = b.add(b.mulc(w, c3), (c2, c2, c2))              # c2 + w c3
    inner = b.add(b.mul(w, inner), (c1, c1, c1))            # c1 + w (c2 + w c3)
    return b.clip01(b.add(x, b.mul(u, inner)))


def _bc(b, x, brightness, contrast):
    omx = b.vm("SUBTRACT", (1, 1, 1), x)
    y = b.clip01(b.add(x, b.mulc(b.mul(x, omx), G.K_BRIGHT * brightness / 100 * 4)))
    return b.clip01(b.add(b.mulc(b.sub(y, (0.5, 0.5, 0.5)), 1 + G.K_BC_CON * contrast / 100), (0.5, 0.5, 0.5)))


def _color_balance(b, x, cb):
    l = b.luma(x)
    a, c = 0.25, 0.333
    ws = b.m("MULTIPLY_ADD", l, -1 / a, c / a + 0.5, clamp=True)
    wh = b.m("MULTIPLY_ADD", l, 1 / a, (c - 1) / a + 0.5, clamp=True)
    wm = b.m("MULTIPLY", b.m("MULTIPLY_ADD", l, 1 / a, -c / a + 0.5, clamp=True),
             b.m("MULTIPLY_ADD", l, -1 / a, (1 - c) / a + 0.5, clamp=True))
    v = [tuple(float(cb[3 * r + k]) * G.K_CB / 100.0 for k in range(3)) for r in range(3)]
    d = b.add(b.add(b.vm("SCALE", v[0], scale=ws), b.vm("SCALE", v[1], scale=wm)), b.vm("SCALE", v[2], scale=wh))
    y = b.clip01(b.add(x, d))
    ratio = b.m("DIVIDE", l, b.m("MAXIMUM", b.luma(y), 1e-4))
    return b.clip01(b.vm("SCALE", y, scale=ratio))


def _glow(b, x, threshold, size, intensity):
    bright = b.mulc(b.vm("MAXIMUM", b.sub(x, (threshold,) * 3), (0, 0, 0)), 1.0 / (1.0 - threshold))
    g = b.blur(bright, size) if size >= 1 else bright
    return b.clip01(b.add(x, b.mulc(g, G.K_GLOW * intensity)))


def build_group(params=None):
    """The node group "AMV Grade" (a new tree, or the existing one rebuilt): Image in -> Image out."""
    import bpy
    p = G.params(params)
    opts = params or {}
    io = opts.get("io", "linear")
    res = float(opts.get("res_scale", 1.0))
    sc = lambda n: max(0, int(round(n * res)))

    old = bpy.data.node_groups.get(GROUP_NAME)
    if old is not None:
        bpy.data.node_groups.remove(old)
    tree = bpy.data.node_groups.new(GROUP_NAME, "CompositorNodeTree")
    tree.interface.new_socket("Image", in_out="INPUT", socket_type="NodeSocketColor")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    gin, gout = tree.nodes.new("NodeGroupInput"), tree.nodes.new("NodeGroupOutput")
    gin.location, gout.location = (-400, 0), (6000, 0)
    b = _B(tree)

    col = gin.outputs[0]
    sep = tree.nodes.new("CompositorNodeSeparateColor")
    tree.links.new(col, sep.inputs[0])
    alpha = sep.outputs["Alpha"]
    if io == "linear":
        col = b.convert(b.vm("MAXIMUM", col, (0, 0, 0)), "Linear Rec.709", "sRGB")
    col = b.vm("MAXIMUM", col, (0, 0, 0))
    sep2 = tree.nodes.new("CompositorNodeSeparateColor")
    tree.links.new(col, sep2.inputs[0])
    x = _rolloff(b, col, p["rolloff"], p["rolloff_power"], sep2)

    x = _sharpen(b, x, p["sharpen_amount"], sc(p["sharpen_size"]))
    x = _colorista(b, x, p["colorista"])
    x = _vignette(b, x, p["vig_amount"], p["vig_size"])
    x = _lumetri(b, x, p)
    x = _saturate(b, x, p["saturation"])
    x = _hi_desat(b, x, p["hi_desat"])
    x = _bc(b, x, p["bc_brightness"], p["bc_contrast"])
    x = _color_balance(b, x, p["cb"])
    x = _curve(b, x, p["curve1"], p["curve2"], p["curve3"])
    x = _glow(b, x, p["glow_threshold"], sc(p["glow_size"]), p["glow_intensity"])

    if io == "linear":
        x = b.convert(x, "sRGB", "Linear Rec.709")
    sa = tree.nodes.new("CompositorNodeSetAlpha")
    tree.links.new(x, sa.inputs["Image"])
    tree.links.new(alpha, sa.inputs["Alpha"])
    tree.links.new(sa.outputs["Image"], gout.inputs[0])
    return tree
