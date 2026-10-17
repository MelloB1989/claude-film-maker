"""Timeless v2 Blender elements for the EffectCraft edit: RGBA 1920x1080 image sequences on a transparent film.

    blender -b --factory-startup -P blender/amv2/elements.py -- --element timeless3d|rift|shockwave|all
        [--res-scale 1.0] [--frames 802-826] [--samples N] [--device CPU|OPTIX|CUDA] [--out DIR]
        [--blend-dir out/timeless/amv2/blender] [--alpha premul|straight] [--depth 8|16] [--no-render] [--no-blend]

Elements (comp frames, 30 fps; the file name is the comp frame, `<out>/<element>/NNNN.png`):

  timeless3d  802-826  chrome 3D TIMELESS: slams in from behind the camera on the 802 hit, rotates into place, settles with
                       a light-sweep glint, floats, holds through the 819 panel shatter, breaks apart 819-826 (826 = gone).
  rift        244-262  the multiverse rift opening in Tobey's left iris (901, 390), filling the frame by 252, dissolving
                       from the centre outward by 260 (260-262 are empty).
  shockwave   480-489  the drop's ring blast from the lens centre (1110, 443), past the frame edges by 489.

Pixel format: the PNGs hold PREMULTIPLIED colour (rgb already multiplied by alpha, display-referred sRGB) with an alpha
channel, 8-bit by default. `--alpha straight` writes ordinary straight-alpha PNGs instead. Additive elements
(shockwave, sparks and glows) therefore also work in Add / Screen modes without a matte.

Everything is keyed in the .blend (scene frame = comp frame), so the saved file plays and renders by itself too.
The script renders through Cycles to a temporary float EXR and writes its own PNG (premultiply, sRGB, dither).
"""
from __future__ import annotations

import argparse
import math
import os
import random
import struct
import sys
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

import bpy  # noqa: E402
from mathutils import Euler, Vector  # noqa: E402

W, H = 1920, 1080
FPS = 30
PX = 100.0                       # px per Blender unit on the z = 0 plane (perspective cameras: 50 mm lens at z = 26.667)
CAM_Z = 26.6667

ELEMENTS = {
    "timeless3d": dict(f0=802, f1=826, blend="titles3d.blend", samples=96),
    "rift": dict(f0=244, f1=262, blend="rift.blend", samples=40),
    "shockwave": dict(f0=480, f1=489, blend="shockwave.blend", samples=40),
}

HDRI_DIR = REPO / "blender" / "amv" / "titles" / "hdri"
FONT_CANDIDATES = [REPO / "films/timeless/fonts/Anton-Regular.ttf", REPO / "fonts/src/Anton-Regular.ttf",
                   Path("/usr/share/fonts/truetype/anton/Anton-Regular.ttf")]


# ---------------------------------------------------------------------------------------------------------------------
# small helpers: easing, colour, node expression builder
# ---------------------------------------------------------------------------------------------------------------------

def clamp01(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, t):
    return a + (b - a) * t


def keys(table, f):
    """Piecewise linear interpolation of [[frame, value], ...]."""
    if f <= table[0][0]:
        return table[0][1]
    for (a, va), (b, vb) in zip(table, table[1:]):
        if f <= b:
            return lerp(va, vb, (f - a) / float(b - a))
    return table[-1][1]


def spring(t, wn=0.95, zeta=0.34):
    """Damped spring step response, 0 -> 1 with overshoot (t in frames)."""
    if t <= 0:
        return 0.0
    wd = wn * math.sqrt(1 - zeta ** 2)
    return 1 - math.exp(-zeta * wn * t) * (math.cos(wd * t) + zeta * wn / wd * math.sin(wd * t))


def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexlin(h, a=1.0):
    h = h.lstrip("#")
    return tuple(srgb_to_lin(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4)) + (a,)


class NB:
    """Node-expression builder: `X` wraps a float socket, python operators create Math nodes."""
    nt = None


class X:
    def __init__(self, sock):
        self.s = sock

    @staticmethod
    def _set(node, i, v):
        if isinstance(v, X):
            NB.nt.links.new(v.s, node.inputs[i])
        else:
            node.inputs[i].default_value = float(v)

    @staticmethod
    def op(name, a, b=None, c=None, clamp=False):
        n = NB.nt.nodes.new("ShaderNodeMath")
        n.operation = name
        n.use_clamp = clamp
        for i, v in enumerate((a, b, c)):
            if v is not None:
                X._set(n, i, v)
        return X(n.outputs[0])

    def __add__(s, o): return X.op("ADD", s, o)
    def __radd__(s, o): return X.op("ADD", o, s)
    def __sub__(s, o): return X.op("SUBTRACT", s, o)
    def __rsub__(s, o): return X.op("SUBTRACT", o, s)
    def __mul__(s, o): return X.op("MULTIPLY", s, o)
    def __rmul__(s, o): return X.op("MULTIPLY", o, s)
    def __truediv__(s, o): return X.op("DIVIDE", s, o)
    def __rtruediv__(s, o): return X.op("DIVIDE", o, s)
    def __pow__(s, o): return X.op("POWER", s, o)
    def __neg__(s): return X.op("MULTIPLY", s, -1.0)


def val(v=0.0, name=None):
    n = NB.nt.nodes.new("ShaderNodeValue")
    n.outputs[0].default_value = v
    if name:
        n.label = n.name = name
    return X(n.outputs[0]), n


def fn(name, a, b=None, c=None, clamp=False):
    return X.op(name, a, b, c, clamp)


def sin(a): return fn("SINE", a)
def cos(a): return fn("COSINE", a)
def fract(a): return fn("FRACT", a)
def floor(a): return fn("FLOOR", a)
def absv(a): return fn("ABSOLUTE", a)
def vmin(a, b): return fn("MINIMUM", a, b)
def vmax(a, b): return fn("MAXIMUM", a, b)
def sqrt(a): return fn("SQRT", a)
def atan2(y, x): return fn("ARCTAN2", y, x)
def clamp(a): return fn("ADD", a, 0.0, clamp=True)


def mix(a, b, t):
    return a + (b - a) * t


def sstep(x, e0, e1):
    """GLSL smoothstep via Map Range (smoothstep interpolation, clamped); e0 > e1 inverts."""
    n = NB.nt.nodes.new("ShaderNodeMapRange")
    n.data_type = "FLOAT"
    n.interpolation_type = "SMOOTHSTEP"
    n.clamp = True
    for name, v in (("Value", x), ("From Min", e0), ("From Max", e1)):
        _set_named(n, name, v)
    n.inputs["To Min"].default_value = 0.0
    n.inputs["To Max"].default_value = 1.0
    return X(n.outputs["Result"])


def _set_named(node, name, v):
    if isinstance(v, X):
        NB.nt.links.new(v.s, node.inputs[name])
    else:
        node.inputs[name].default_value = float(v)


def sep_xyz(vec):
    n = NB.nt.nodes.new("ShaderNodeSeparateXYZ")
    NB.nt.links.new(vec, n.inputs[0])
    return X(n.outputs[0]), X(n.outputs[1]), X(n.outputs[2])


def comb_xyz(x, y, z):
    n = NB.nt.nodes.new("ShaderNodeCombineXYZ")
    for nm, v in (("X", x), ("Y", y), ("Z", z)):
        _set_named(n, nm, v)
    return n.outputs[0]


def comb_rgb(r, g, b):
    n = NB.nt.nodes.new("ShaderNodeCombineColor")
    n.mode = "RGB"
    for nm, v in (("Red", r), ("Green", g), ("Blue", b)):
        _set_named(n, nm, v)
    return n.outputs[0]


def keyframe_value(node, frames, fnc):
    """Key a Value node at every frame in `frames` with `fnc(frame)`."""
    for f in frames:
        node.outputs[0].default_value = float(fnc(f))
        node.outputs[0].keyframe_insert("default_value", frame=f)


# ---------------------------------------------------------------------------------------------------------------------
# scene plumbing
# ---------------------------------------------------------------------------------------------------------------------

class Shim:
    """What blender/amv/titles/common.Compositor needs from a TitleScene."""

    def __init__(self, scene):
        self.bpy = bpy
        self.scene = scene


def setup_scene(args, name, f0, f1, motion_blur=True, shutter=0.5):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    s = bpy.context.scene
    s.name = name
    s.frame_start, s.frame_end = f0, f1
    r = s.render
    r.fps = FPS
    r.resolution_x = max(2, int(round(W * args.res_scale)))
    r.resolution_y = max(2, int(round(H * args.res_scale)))
    r.resolution_percentage = 100
    r.film_transparent = True
    r.use_compositing = True
    r.compositor_device = "CPU"
    r.use_motion_blur = motion_blur
    r.motion_blur_shutter = shutter
    s.view_settings.view_transform = "Standard"
    s.view_settings.look = "None"
    s.display_settings.display_device = "sRGB"
    r.image_settings.file_format = "OPEN_EXR"
    r.image_settings.color_mode = "RGBA"
    r.image_settings.color_depth = "32"
    r.image_settings.exr_codec = "ZIP"
    s.render.engine = "CYCLES"
    c = s.cycles
    c.samples = args.samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.01
    c.use_denoising = True
    try:
        c.denoiser = "OPTIX" if args.device.upper() == "OPTIX" else "OPENIMAGEDENOISE"
    except TypeError:
        pass
    c.max_bounces = 8
    c.glossy_bounces = 6
    c.diffuse_bounces = 2
    c.transmission_bounces = 2
    c.transparent_max_bounces = 16
    c.sample_clamp_indirect = 12.0
    c.filter_width = 1.1
    set_device(s, args.device)
    return s


def set_device(scene, device):
    device = device.upper()
    scene.cycles.device = "CPU"
    if device == "CPU":
        return
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = device
        prefs.get_devices()
        used = 0
        for d in prefs.devices:
            d.use = d.type != "CPU"
            used += int(d.use)
        if used:
            scene.cycles.device = "GPU"
            print(f"[elements] cycles device {device}: {used} GPU(s)")
        else:
            print(f"[elements] no {device} device found, rendering on CPU")
    except Exception as e:   # noqa: BLE001
        print(f"[elements] could not enable {device}: {e}; rendering on CPU")


def perspective_camera(scene, shift_px=(0.0, 0.0), z=CAM_Z, lens=50.0):
    cam = bpy.data.cameras.new("cam")
    cam.lens = lens
    cam.sensor_width = 36.0
    cam.sensor_fit = "HORIZONTAL"
    cam.shift_x = shift_px[0] / W
    cam.shift_y = shift_px[1] / W
    cam.clip_start, cam.clip_end = 0.05, 2000.0
    ob = bpy.data.objects.new("cam", cam)
    scene.collection.objects.link(ob)
    ob.location = (0, 0, z)
    scene.camera = ob
    return ob


def ortho_camera(scene):
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    cam.ortho_scale = float(W)         # 1 unit = 1 px
    cam.clip_start, cam.clip_end = 0.1, 1000.0
    ob = bpy.data.objects.new("cam", cam)
    scene.collection.objects.link(ob)
    ob.location = (0, 0, 100)
    scene.camera = ob
    return ob


def set_world(scene, hdri=None, strength=1.0, color=(0, 0, 0, 1), rot=(0, 0, 0), gradient=0.0):
    w = bpy.data.worlds.new("world")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    if hdri and Path(hdri).exists():
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        for i in range(3):
            mp.inputs["Rotation"].default_value[i] = math.radians(rot[i])
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(str(hdri))
        nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
        col = env.outputs["Color"]
        if gradient:
            # a vertical sky gradient added to the HDRI so a mirror never reflects pure black
            sep = nt.nodes.new("ShaderNodeSeparateXYZ")
            nt.links.new(tc.outputs["Generated"], sep.inputs[0])
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
            el = ramp.color_ramp.elements
            el[0].position, el[0].color = 0.35, (0.012, 0.018, 0.03, 1)
            el[1].position, el[1].color = 0.75, (0.55, 0.62, 0.78, 1)
            mx = nt.nodes.new("ShaderNodeMix")
            mx.data_type = "RGBA"
            mx.blend_type = "ADD"
            mx.inputs["Factor"].default_value = gradient
            nt.links.new(col, mx.inputs["A"])
            nt.links.new(ramp.outputs["Color"], mx.inputs["B"])
            col = mx.outputs["Result"]
        nt.links.new(col, bg.inputs["Color"])
    else:
        bg.inputs["Color"].default_value = color
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    scene.world = w


def link(scene, ob):
    scene.collection.objects.link(ob)
    return ob


def empty(scene, name):
    return link(scene, bpy.data.objects.new(name, None))


def area_light(scene, name, loc, target, color, energy, size=4.0, shape="RECTANGLE", size_y=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.color = color
    ld.shape = shape
    ld.size = size
    if shape == "RECTANGLE":
        ld.size_y = size_y or size
    ob = link(scene, bpy.data.objects.new(name, ld))
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def emission_material(name, color=(1, 1, 1, 1), strength=1.0, use_object_color=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    if use_object_color:
        oi = nt.nodes.new("ShaderNodeObjectInfo")
        nt.links.new(oi.outputs["Color"], em.inputs["Color"])
    else:
        em.inputs["Color"].default_value = color
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def set_key(ob, frame, loc=None, rot=None, scale=None, hide=None):
    if loc is not None:
        ob.location = loc
        ob.keyframe_insert("location", frame=frame)
    if rot is not None:
        ob.rotation_euler = rot
        ob.keyframe_insert("rotation_euler", frame=frame)
    if scale is not None:
        ob.scale = scale
        ob.keyframe_insert("scale", frame=frame)
    if hide is not None:
        ob.hide_render = hide
        ob.keyframe_insert("hide_render", frame=frame)


def glow_compositor(scene, glows):
    from blender.amv.titles import common as C
    glow_objs = [C.Glow(**g) for g in glows]
    return C.Compositor(Shim(scene), glow_objs, None, False, None)


# ---------------------------------------------------------------------------------------------------------------------
# PNG output: float EXR (premultiplied, scene linear) -> premultiplied sRGB 8/16-bit PNG written here
# ---------------------------------------------------------------------------------------------------------------------

def _png_chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path, rgba8_or16, depth):
    import numpy as np
    a = rgba8_or16
    h, w = a.shape[:2]
    if depth == 16:
        raw = a.astype(">u2").tobytes()
        bpp = 8
    else:
        raw = a.astype(np.uint8).tobytes()
        bpp = 4
    rows = np.frombuffer(raw, dtype=np.uint8).reshape(h, w * bpp)
    # filter type 1 (Sub): subtract the pixel to the left; much better deflate ratio on glows
    filt = rows.copy()
    filt[:, bpp:] = (rows[:, bpp:].astype(np.int16) - rows[:, :-bpp].astype(np.int16)).astype(np.uint8)
    out = np.empty((h, w * bpp + 1), dtype=np.uint8)
    out[:, 0] = 1
    out[:, 1:] = filt
    ihdr = struct.pack(">IIBBBBB", w, h, depth, 6, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(out.tobytes(), 6)) \
        + _png_chunk(b"IEND", b"")
    Path(path).write_bytes(data)


def exr_to_png(exr_path, png_path, alpha_mode, depth, seed=0):
    import numpy as np
    img = bpy.data.images.load(str(exr_path))
    try:
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    px = px.reshape(h, w, 4)[::-1]            # Blender rows start at the bottom
    rgb = px[..., :3]
    a = np.clip(px[..., 3:4], 0.0, 1.0)
    # the EXR is premultiplied scene-linear: un-premultiply, sRGB-encode, then premultiply again in display space
    straight = np.where(a > 1e-5, rgb / np.maximum(a, 1e-5), 0.0)
    straight = np.clip(straight, 0.0, 1.0)
    enc = np.where(straight <= 0.0031308, straight * 12.92, 1.055 * np.power(straight, 1 / 2.4) - 0.055)
    out_rgb = enc if alpha_mode == "straight" else enc * a
    out = np.concatenate([out_rgb, a], axis=-1)
    rng = np.random.default_rng(seed)
    scale = 65535.0 if depth == 16 else 255.0
    dither = (rng.random(out.shape, dtype=np.float32) + rng.random(out.shape, dtype=np.float32) - 1.0) * (0.5 if depth == 8 else 0.0)
    q = np.clip(np.rint(out * scale + dither), 0, scale)
    write_png(png_path, q.astype(np.uint16 if depth == 16 else np.uint8), depth)
    return float(a.mean())


# =====================================================================================================================
# 1. TIMELESS 3D  (comp 802-826)
# =====================================================================================================================

T_F0, T_F1 = 802, 826
T_HOLD_END = 819            # the panel shatter hit: the title breaks from here, 826 is empty
T_WIDTH_PX = 1500.0         # width of the word on screen when it holds
T_CENTER = (960.0, 548.0)   # screen centre of the word (px)
T_WIDE = 1.10               # horizontal stretch of the face (Anton is condensed; "wide" per the brief)


def find_font():
    for p in FONT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("Anton-Regular.ttf not found; checked " + ", ".join(map(str, FONT_CANDIDATES)))


def text_object(scene, body, font, extrude, bevel, name):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = font
    cu.size = 1.0
    cu.align_x = "LEFT"
    cu.align_y = "BOTTOM_BASELINE"
    cu.extrude = extrude
    cu.bevel_depth = bevel
    cu.bevel_resolution = 5
    cu.resolution_u = 12
    cu.offset_x = 0.0
    return link(scene, bpy.data.objects.new(name, cu))


def eval_bounds(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    bpy.data.meshes.remove(me)
    return min(xs), max(xs), min(ys), max(ys)


def chrome_material(name="chrome"):
    """Mirror chrome face, dark bevel/side, a red (left) / blue (right) Spider-Verse rim and a travelling glint band."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    NB.nt = nt
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")

    chrome = nt.nodes.new("ShaderNodeBsdfPrincipled")
    chrome.inputs["Base Color"].default_value = (0.93, 0.95, 1.0, 1)
    chrome.inputs["Metallic"].default_value = 1.0
    chrome.inputs["Roughness"].default_value = 0.035
    dark = nt.nodes.new("ShaderNodeBsdfPrincipled")
    dark.inputs["Base Color"].default_value = (0.012, 0.014, 0.022, 1)
    dark.inputs["Metallic"].default_value = 0.75
    dark.inputs["Roughness"].default_value = 0.28

    tc = nt.nodes.new("ShaderNodeTexCoord")
    _, _, nz = sep_xyz(tc.outputs["Normal"])           # object-space normal: +z = the face, ~0 = the sides
    face = sstep(absv(nz), 0.70, 0.93)                 # 1 on the flat face, 0 on the bevel and sides
    mixs = nt.nodes.new("ShaderNodeMixShader")
    NB.nt.links.new(face.s, mixs.inputs[0])
    nt.links.new(dark.outputs["BSDF"], mixs.inputs[1])
    nt.links.new(chrome.outputs["BSDF"], mixs.inputs[2])

    # red / blue rim: red on the left half of the word, blue on the right, strongest on the bevel and grazing angles
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    wx, wy, _ = sep_xyz(geo.outputs["Position"])
    side = sstep(wx, -2.0, 2.0)                         # 0 left .. 1 right
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    graze = lw.outputs["Facing"]
    rim = (X(graze) ** 3.0) * 0.9 + (1.0 - face) * 0.55
    red = (1.0, 0.07, 0.14)
    blue = (0.06, 0.28, 1.0)
    r = mix(red[0], blue[0], side)
    g = mix(red[1], blue[1], side)
    b = mix(red[2], blue[2], side)
    rim_col = comb_rgb(r * rim, g * rim, b * rim)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 2.2
    nt.links.new(rim_col, em.inputs["Color"])

    # light-sweep glint: a diagonal band in world space, position keyed per frame
    cen, cen_node = val(-20.0, "glint_pos")
    wid, _ = val(0.55, "glint_width")
    amp, amp_node = val(0.0, "glint_amp")
    d = (wx * 0.94 + wy * 0.34) - cen
    band = fn("EXPONENT", -(d * d) / (wid * wid))
    core = fn("EXPONENT", -(d * d) / (wid * wid * 0.12))
    glint = (band * 0.45 + core * 1.2) * amp
    gem = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(comb_rgb(glint * 1.0, glint * 0.97, glint * 0.92), gem.inputs["Color"])

    add1 = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(mixs.outputs["Shader"], add1.inputs[0])
    nt.links.new(em.outputs["Emission"], add1.inputs[1])
    add2 = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(add1.outputs["Shader"], add2.inputs[0])
    nt.links.new(gem.outputs["Emission"], add2.inputs[1])
    nt.links.new(add2.outputs["Shader"], out.inputs["Surface"])
    return m, cen_node, amp_node


def build_timeless(args):
    s = setup_scene(args, "timeless3d", T_F0, T_F1, motion_blur=True, shutter=0.55)
    perspective_camera(s)
    set_world(s, HDRI_DIR / "studio_small_08_1k.hdr", strength=1.6, rot=(90, 0, 160), gradient=0.8)
    mat, cen_node, amp_node = chrome_material()
    font = bpy.data.fonts.load(str(find_font()))

    text = "TIMELESS"
    EXT, BEV = 0.085, 0.020
    # measure the glyph boxes: the right edge of each prefix is the right edge of its last letter
    probe = text_object(s, text, font, EXT, BEV, "probe")
    bpy.context.view_layer.update()
    full = eval_bounds(probe)
    bpy.data.objects.remove(probe)
    boxes = []
    for i, ch in enumerate(text):
        po = text_object(s, text[:i + 1], font, EXT, BEV, "pp")
        so = text_object(s, ch, font, EXT, BEV, "ps")
        bpy.context.view_layer.update()
        px1 = eval_bounds(po)[1]
        sx0, sx1, sy0, sy1 = eval_bounds(so)
        bpy.data.objects.remove(po)
        bpy.data.objects.remove(so)
        left = px1 - (sx1 - sx0)
        boxes.append((left, left + (sx1 - sx0), sy0, sy1))
    x0, x1 = boxes[0][0], boxes[-1][1]
    cap0 = min(b[2] for b in boxes)
    cap1 = max(b[3] for b in boxes)
    ycen = 0.5 * (cap0 + cap1)
    xcen = 0.5 * (x0 + x1)
    base = (T_WIDTH_PX / PX) / ((x1 - x0) * T_WIDE)           # blender units per text unit
    print(f"[timeless3d] word width {x1 - x0:.3f} em x {cap1 - cap0:.3f} em; scale {base:.3f}; "
          f"on screen {(x1 - x0) * T_WIDE * base * PX:.0f} x {(cap1 - cap0) * base * PX:.0f} px")

    title = empty(s, "TITLE")
    pivots = []
    for i, ch in enumerate(text):
        left, right, y0, y1 = boxes[i]
        cx = 0.5 * (left + right)
        piv = empty(s, f"L{i}_{ch}")
        piv.parent = title
        home = Vector(((cx - xcen) * T_WIDE, 0.0, 0.0))
        piv.location = home
        ob = text_object(s, ch, font, EXT, BEV, f"glyph{i}")
        ob.data.materials.append(mat)
        ob.parent = piv
        ob.scale = (T_WIDE, 1.0, 1.0)
        # a lone letter's curve starts at x = 0 and its box spans [sl, sr]: put the box centre on the pivot
        sl, sr = _single_box(s, font, ch, EXT, BEV)
        ob.location = (-0.5 * (sl + sr) * T_WIDE, -ycen, 0.0)
        pivots.append((piv, home, cx))

    # lights: the red / blue Spider-Verse rim comes from two coloured strips behind and beside the word
    area_light(s, "rimR", (-9.0, 3.5, -4.0), (0, 0, 0), (1.0, 0.1, 0.18), 5200, size=3.0, size_y=10.0)
    area_light(s, "rimB", (9.0, -2.0, -4.0), (0, 0, 0), (0.1, 0.3, 1.0), 5200, size=3.0, size_y=10.0)
    area_light(s, "key", (0.0, 9.0, 14.0), (0, 0, 0), (1.0, 0.97, 0.93), 2400, size=10.0, size_y=3.0)

    animate_timeless(s, title, pivots, cen_node, amp_node, base, ycen)
    s.frame_set(T_F0)
    glow_compositor(s, [dict(threshold=0.9, size=0.55, strength=0.35, tint="#BFD2FF"),
                        dict(threshold=1.3, size=0.25, strength=0.30, tint="#FFFFFF")])
    return s


def _single_box(scene, font, ch, ext, bev):
    """x extent (text units) of a lone letter's box."""
    o = text_object(scene, ch, font, ext, bev, "pl")
    bpy.context.view_layer.update()
    x0, x1, _, _ = eval_bounds(o)
    bpy.data.objects.remove(o)
    return x0, x1


def animate_timeless(s, title, pivots, cen_node, amp_node, base, ycen):
    rnd = random.Random(7)
    frames = list(range(T_F0, T_F1 + 1))
    cx_screen = (T_CENTER[0] - W / 2) / PX
    cy_screen = (H / 2 - T_CENTER[1]) / PX
    # camera sits at z = CAM_Z; "behind the camera" means z > CAM_Z, so the word flies in from z ~ CAM_Z + 4

    def slam(f):
        """(z offset, scale mult, yaw, pitch, roll) of the whole word, f = comp frame"""
        k = f - T_F0
        # the 802 hit: the word arrives from behind the camera (z above CAM_Z) and slams down to z = 0, overshoots
        # behind (receding), springs back. k=0 is already right at the lens: huge and blurred.
        z_key = [[0, 24.5], [1, 9.0], [2, 2.6], [3, -1.0], [4, -0.6], [5, 0.15]]
        z = keys(z_key, k) if k <= 5 else 0.28 * math.exp(-0.45 * (k - 5)) * math.cos(0.85 * (k - 5))
        sp = spring(k - 1.0, wn=0.82, zeta=0.30)
        yaw = math.radians(78.0 * (1 - sp))
        pitch = math.radians(-24.0 * (1 - sp))
        roll = math.radians(9.0 * (1 - spring(k - 0.5, wn=0.9, zeta=0.35)))
        return z, yaw, pitch, roll

    def floaty(f):
        k = f - T_F0
        fade = smooth((k - 6) / 6.0)
        t = k / FPS
        return (fade * 0.035 * math.sin(2 * math.pi * t * 0.85),
                fade * math.radians(1.1) * math.sin(2 * math.pi * t * 0.55 + 0.6),
                fade * math.radians(1.4) * math.sin(2 * math.pi * t * 0.65),
                fade * math.radians(0.5) * math.sin(2 * math.pi * t * 0.7 + 1.1))

    for f in frames:
        z, yaw, pitch, roll = slam(f)
        by, fy, fx, fz = floaty(f)
        set_key(title, f, loc=(cx_screen, cy_screen + by, z),
                rot=Euler((pitch + fx, yaw + fy, roll + fz), "XYZ"), scale=(base, base, base))

    # light-sweep glint across the letters: f 808..817, a bright pass at the centre of the word
    for f in frames:
        k = f - T_F0
        c = lerp(-9.5, 9.5, smooth((k - 6) / 11.0))
        keyframe_value(cen_node, [f], lambda _f: c)
        a = 1.0 if 6 <= k <= 18 else 0.0
        keyframe_value(amp_node, [f], lambda _f: a)

    # break: letter i leaves from the hold at 819 (k = 17), gone at 826 (k = 24)
    n = len(pivots)
    for i, (piv, home, cx) in enumerate(pivots):
        dirx = (home.x / (0.5 * 15.0)) * 1.0 + rnd.uniform(-0.25, 0.25)
        diry = rnd.uniform(-0.8, 0.9)
        delay = [0.0, 0.7, 0.2, 1.0, 0.5, 0.15, 0.85, 0.35][i % 8]
        spin = (rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))
        for f in frames:
            k = f - T_F0
            t = (f - T_HOLD_END - delay)
            if t <= 0:
                set_key(piv, f, loc=home, rot=Euler((0, 0, 0)), scale=(1, 1, 1), hide=False)
                continue
            e = t * t
            loc = Vector((home.x + dirx * 1.5 * e, home.y + diry * 0.9 * e, home.z + 0.9 * e))
            ang = 0.045 * e
            rot = Euler((spin[0] * ang * 2.2, spin[1] * ang * 2.6, spin[2] * ang * 3.4), "XYZ")
            sc = max(0.0001, 1.0 - smooth((f - (T_F1 - 2.5)) / 2.5)) if f >= T_F1 - 2 else 1.0
            gone = f >= T_F1
            set_key(piv, f, loc=loc, rot=rot, scale=(sc, sc, sc), hide=gone)

    # chrome debris that flies out of the word during the break
    shard_mesh = bpy.data.meshes.new("shard")
    shard_mesh.from_pydata([(0.0, 0.5, 0.03), (-0.17, -0.5, 0.03), (0.17, -0.5, 0.03),
                            (0.0, 0.5, -0.03), (-0.17, -0.5, -0.03), (0.17, -0.5, -0.03)], [],
                           [(0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)])
    for p in shard_mesh.polygons:
        p.use_smooth = False
    mat = bpy.data.materials["chrome"]
    shard_mesh.materials.append(mat)
    for j in range(44):
        ob = link(s, bpy.data.objects.new(f"debris{j}", shard_mesh))
        ob.parent = title
        a = rnd.uniform(-1, 1)
        home = Vector((a * 7.4, rnd.uniform(-1.0, 1.0), rnd.uniform(-0.2, 0.2)))
        d = Vector((a * 0.9 + rnd.uniform(-0.3, 0.3), rnd.uniform(-1, 1), rnd.uniform(0.2, 1.6))).normalized()
        sz = rnd.uniform(0.25, 0.8)
        t0 = T_HOLD_END + rnd.uniform(0.0, 1.5)
        spin = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)))
        for f in frames:
            t = f - t0
            if t <= 0:
                set_key(ob, f, loc=home, rot=Euler((0, 0, 0)), scale=(0.001,) * 3, hide=True)
                continue
            dist = 1.6 * t ** 1.55
            sc = sz * min(1.0, t / 1.2) * (1.0 - smooth((f - (T_F1 - 2.5)) / 2.5))
            set_key(ob, f, loc=home + d * dist,
                    rot=Euler((spin.x * 0.35 * t * 2, spin.y * 0.35 * t * 2, spin.z * 0.35 * t * 2)),
                    scale=(max(sc, 0.001),) * 3, hide=(f >= T_F1) or sc < 0.01)


# =====================================================================================================================
# 2. RIFT  (comp 244-262)
# =====================================================================================================================

R_F0, R_FOPEN, R_FDONE, R_F1 = 244, 252, 260, 262
R_CENTER = (901.0, 390.0)

# mask radius (px, full-res) of the opening, the dissolve hole radius and the dissolve threshold
R_RADIUS = [[244, 4], [245, 12], [246, 38], [247, 100], [248, 215], [249, 400], [250, 680], [251, 1010], [252, 1420],
            [253, 1500], [262, 1500]]
R_HOLE = [[252, 0], [253, 60], [254, 190], [255, 420], [256, 720], [257, 1040], [258, 1350], [259, 1600], [260, 1900],
          [262, 1900]]
R_DISS = [[252, -0.05], [254, 0.05], [256, 0.28], [258, 0.62], [259, 0.85], [260, 1.15], [262, 1.2]]


def build_rift(args):
    s = setup_scene(args, "rift", R_F0, R_F1, motion_blur=True, shutter=0.5)
    # perspective camera whose optical axis passes through the rift centre: the tunnel axis is the vanishing point
    perspective_camera(s, shift_px=(W / 2 - R_CENTER[0], R_CENTER[1] - H / 2))
    set_world(s, color=(0, 0, 0, 1))
    frames = list(range(R_F0, R_F1 + 1))

    # ---- the tunnel: an open cylinder along -z, shaded procedurally, masked in screen space ----------------------
    L, RAD = 300.0, 14.0
    segs = 96
    verts, faces = [], []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        verts.append((RAD * math.cos(a), RAD * math.sin(a), 0.0))
        verts.append((RAD * math.cos(a), RAD * math.sin(a), -L))
    for i in range(segs):
        j = (i + 1) % segs
        faces.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
    me = bpy.data.meshes.new("tunnel")
    me.from_pydata(verts, [], faces)
    tun = link(s, bpy.data.objects.new("tunnel", me))
    tun.data.materials.append(rift_material(frames))

    # ---- shards, halftone dots and web filaments that burst out of the rift ------------------------------------
    build_rift_particles(s, frames)

    s.frame_set(R_F0)
    glow_compositor(s, [dict(threshold=0.55, size=0.30, strength=0.55, tint="#FFFFFF"),
                        dict(threshold=0.9, size=0.62, strength=0.30, tint="#7FA6FF")])
    return s


def rift_material(frames):
    m = bpy.data.materials.new("rift")
    m.use_nodes = True
    nt = m.node_tree
    NB.nt = nt
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")

    # controls (keyed per frame)
    rad, rad_n = val(0, "radius")
    hole, hole_n = val(0, "hole")
    diss, diss_n = val(0, "dissolve")
    phase, phase_n = val(0, "phase")
    gain, gain_n = val(1, "gain")
    keyframe_value(rad_n, frames, lambda f: keys(R_RADIUS, f))
    keyframe_value(hole_n, frames, lambda f: keys(R_HOLE, f))
    keyframe_value(diss_n, frames, lambda f: keys(R_DISS, f))
    # the flight through the tunnel accelerates: phase = integral of speed
    ph = {}
    acc = 0.0
    for f in range(R_F0, R_F1 + 1):
        acc += 0.25 + 0.9 * smooth((f - R_F0) / 8.0) + 2.4 * smooth((f - 250) / 10.0)
        ph[f] = acc
    keyframe_value(phase_n, frames, lambda f: ph[f])
    # exposure: a white-hot flash as it tears open (f244-247), settles, then fades with the dissolve
    keyframe_value(gain_n, frames, lambda f: keys([[244, 1.9], [246, 2.2], [248, 1.5], [252, 1.15], [258, 1.0], [262, 1.0]], f))

    tc = nt.nodes.new("ShaderNodeTexCoord")
    ox, oy, oz = sep_xyz(tc.outputs["Object"])
    wx, wy, _ = sep_xyz(tc.outputs["Window"])

    # ---- screen-space geometry of the opening -----------------------------------------------------------------
    dx = wx * float(W) - R_CENTER[0]
    dy = (1.0 - wy) * float(H) - R_CENTER[1]
    dist = sqrt(dx * dx + dy * dy)
    nn1 = nt.nodes.new("ShaderNodeTexNoise")
    nn1.noise_dimensions = "3D"
    nn1.inputs["Scale"].default_value = 5.0
    nn1.inputs["Detail"].default_value = 3.0
    nn1.inputs["Roughness"].default_value = 0.55
    ang_dir = comb_xyz(dx / vmax(dist, 1.0) * 1.7, dy / vmax(dist, 1.0) * 1.7, phase * 0.05)
    nt.links.new(ang_dir, nn1.inputs["Vector"])
    nn2 = nt.nodes.new("ShaderNodeTexNoise")
    nn2.noise_dimensions = "3D"
    nn2.inputs["Scale"].default_value = 1.0
    nn2.inputs["Detail"].default_value = 2.0
    nt.links.new(comb_xyz(dx / 55.0, dy / 55.0, phase * 0.12), nn2.inputs["Vector"])
    n1 = X(nn1.outputs["Fac"]) - 0.5
    n2 = X(nn2.outputs["Fac"]) - 0.5
    # torn, glitchy edge: radius jitter grows with the radius, clamped so the tiny first frames stay round
    jit = (n1 * 0.55 + n2 * 0.30) * (vmin(rad, 240.0) * 0.55 + 6.0)
    dj = dist + jit
    soft = 2.5 + rad * 0.012
    inside = sstep(dj, rad + soft, rad - soft)                     # 1 inside the opening, soft alpha edge
    # the dissolve hole grows from the centre out
    hsoft = 40.0 + hole * 0.05
    hjit = (n1 * 0.9 + n2 * 0.4) * (hsoft * 1.6)
    outside_hole = sstep(dist + hjit, hole - hsoft, hole + hsoft)
    # plus a noise-threshold dissolve (torn comic chunks) driven by blocky noise
    nn3 = nt.nodes.new("ShaderNodeTexNoise")
    nn3.noise_dimensions = "3D"
    nn3.inputs["Scale"].default_value = 3.0
    nn3.inputs["Detail"].default_value = 4.0
    nt.links.new(comb_xyz(dx / 170.0, dy / 170.0, 3.1), nn3.inputs["Vector"])
    keep = sstep(X(nn3.outputs["Fac"]), diss, diss + 0.12)
    vis = inside * outside_hole * keep

    # chromatic edge lines on the outer rim (red outside, blue inside) and on the hole edge (reverse)
    def edge_line(d, r, w):
        return fn("EXPONENT", -((d - r) / w) * ((d - r) / w))

    ow = 3.0 + rad * 0.008
    o_red = edge_line(dj, rad + ow * 1.3, ow) * sstep(rad, 3.0, 12.0)
    o_blue = edge_line(dj, rad - ow * 1.1, ow) * sstep(rad, 3.0, 12.0)
    h_blue = edge_line(dist + hjit, hole - hsoft * 0.2, hsoft * 0.2) * sstep(hole, 1.0, 40.0)
    h_red = edge_line(dist + hjit, hole + hsoft * 0.2, hsoft * 0.2) * sstep(hole, 1.0, 40.0)
    # the rim lines die with the dissolve so nothing lingers
    live = (1.0 - sstep(diss, 0.7, 1.05)) * keep

    # ---- the vortex tunnel pattern ---------------------------------------------------------------------------------
    depth = -oz                                            # 0 at the mouth .. 300 at the far end
    turn = atan2(oy, ox) / (2.0 * math.pi)                 # -0.5 .. 0.5
    e = depth / 6.0 + phase * 0.55                          # scrolling coordinate along the tunnel
    # glitch slices: blocks along the tunnel get an angular offset and a bigger colour split
    wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "1D"
    _set_named(wn, "W", floor(depth / 7.0) + floor(phase * 0.8))
    wv = X(wn.outputs["Value"])
    slice_on = sstep(wv, 0.82, 0.86)
    twist = depth * 0.012 + phase * 0.012
    u = turn + twist + slice_on * (wv - 0.8) * 3.0
    N_ARMS = 7.0
    split = 0.055 + slice_on * 0.09

    def arm(s_):
        f = fract(s_)
        return sstep(f, 0.0, 0.07) * (1.0 - sstep(f, 0.07, 0.62))

    s0 = u * N_ARMS
    pr = arm(s0 + split)
    pg = arm(s0)
    pb = arm(s0 - split)
    parity = fn("FLOORED_MODULO", floor(s0), 2.0)           # 0 -> red arms, 1 -> blue arms
    tr = mix(1.0, 0.22, parity)
    tg = mix(0.28, 0.5, parity)
    tb = mix(0.40, 1.0, parity)
    fall = 1.0 - sstep(depth, 40.0, 230.0)                  # pattern fades into the far glow

    # halftone dots in (angle, depth) space; dot radius shrinks along the arm tail
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.voronoi_dimensions = "2D"
    vor.feature = "F1"
    vor.inputs["Scale"].default_value = 1.0
    vor.inputs["Randomness"].default_value = 0.0
    nt.links.new(comb_xyz(u * 42.0, e * 3.2, 0.0), vor.inputs["Vector"])
    fr = fract(s0)
    dot_r = (1.0 - fr) * 0.46
    dots = sstep(X(vor.outputs["Distance"]), dot_r, dot_r - 0.07) * sstep(fr, 0.07, 0.16) * (1.0 - parity * 0.0)

    # web: twisting spokes with scalloped rings between them
    uw = turn + twist * 0.5
    sp = absv(fract(uw * 16.0) - 0.5) * 2.0                 # 1 on a spoke
    spoke = sstep(sp, 0.955, 0.985)
    scal = e * 0.5 + absv(sin(uw * 16.0 * math.pi)) * 0.35
    rg = absv(fract(scal) - 0.5) * 2.0
    ring = sstep(rg, 0.93, 0.975)
    web = vmax(spoke, ring * 0.85) * fall

    far = sstep(depth, 110.0, 270.0)
    core = far * far * 2.6

    base_r = (pr * tr * 1.25 + dots * 0.55 * tr) * fall
    base_g = (pg * tg * 1.25 + dots * 0.45 * tg) * fall
    base_b = (pb * tb * 1.25 + dots * 0.65 * tb) * fall
    # white-hot centres of the arms
    hot = (pg ** 3.0) * 0.6 * fall
    # a faint ink-dark base so the tunnel is not transparent between the arms
    shade = 0.045
    cr = (base_r + hot + web * 0.55 + core + shade * 0.9) * gain
    cg = (base_g + hot + web * 0.95 + core + shade * 0.5) * gain
    cb = (base_b + hot + web * 1.0 + core * 1.0 + shade * 1.4) * gain
    # edge lines (premultiplied additive on top of the opening)
    rim_red = (o_red + h_red) * live
    rim_blue = (o_blue + h_blue) * live
    cr = cr * vis + rim_red * 1.6 + rim_blue * 0.35
    cg = cg * vis + rim_red * 0.30 + rim_blue * 0.65
    cb = cb * vis + rim_red * 0.40 + rim_blue * 1.7

    # alpha: the opening, plus the rim lines; colour is emitted as straight colour so the premultiplied result is exact
    alpha = clamp(vis + rim_red + rim_blue)
    inv = 1.0 / vmax(alpha, 0.002)
    emit = comb_rgb(clamp(cr * inv) * 1.0, clamp(cg * inv), clamp(cb * inv))
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(emit, em.inputs["Color"])
    tr_ = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(alpha.s, mx.inputs[0])
    nt.links.new(tr_.outputs["BSDF"], mx.inputs[1])
    nt.links.new(em.outputs["Emission"], mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    return m


def build_rift_particles(s, frames):
    rnd = random.Random(244)
    cols = {"red": (1.0, 0.10, 0.18, 1), "blue": (0.12, 0.38, 1.0, 1), "white": (1.0, 1.0, 1.0, 1),
            "cyan": (0.55, 0.92, 1.0, 1), "mag": (1.0, 0.2, 0.75, 1)}
    names = ["red", "blue", "white", "cyan", "red", "blue", "white", "mag"]
    mat = emission_material("shard", strength=1.4, use_object_color=True)
    # shard shapes: slivers and jagged quads
    sliver = bpy.data.meshes.new("sliver")
    sliver.from_pydata([(0, 0.5, 0), (-0.14, -0.5, 0), (0.14, -0.35, 0)], [], [(0, 1, 2)])
    quad = bpy.data.meshes.new("quadshard")
    quad.from_pydata([(-0.5, -0.3, 0), (0.45, -0.5, 0), (0.5, 0.25, 0), (-0.2, 0.5, 0)], [], [(0, 1, 2, 3)])
    disc = bpy.data.meshes.new("dot")
    disc.from_pydata([(math.cos(a * math.pi / 8) * 0.5, math.sin(a * math.pi / 8) * 0.5, 0) for a in range(16)], [],
                     [tuple(range(16))])
    for me in (sliver, quad, disc):
        me.materials.append(mat)

    def anim_particle(ob, tb, a0, rho0, v, spin_w, size, z, tumble, fadeout=(257.0, 260.5)):
        for f in frames:
            t = f - tb
            alive = t >= 0 and f < R_F1 - 0.5
            if not alive:
                set_key(ob, f, loc=(0, 0, z), rot=Euler((0, 0, 0)), scale=(0.001,) * 3, hide=True)
                continue
            rho = rho0 + v * (t ** 1.45)
            a = a0 + spin_w * t
            x, y = rho * math.cos(a) / PX, rho * math.sin(a) / PX
            fade = 1.0 - smooth((f - fadeout[0]) / (fadeout[1] - fadeout[0]))
            pop = smooth(t / 1.5)
            sc = max(0.001, size * pop * fade)
            rot = Euler((tumble[0] * t, tumble[1] * t, a + math.pi / 2 + tumble[2] * t), "XYZ")
            set_key(ob, f, loc=(x, y, z), rot=rot, scale=(sc * rnd_aspect(ob), sc, sc), hide=sc < 0.01)

    aspects = {}

    def rnd_aspect(ob):
        return aspects.get(ob.name, 1.0)

    # glitch shards: the main burst
    for j in range(150):
        ob = link(s, bpy.data.objects.new(f"shard{j}", sliver if j % 3 else quad))
        ob.color = cols[rnd.choice(names)]
        aspects[ob.name] = rnd.uniform(0.7, 1.5)
        tb = R_F0 + rnd.choice([0, 0, 1, 1, 2, 3, 4, 5, 6, 7]) + rnd.random() * 0.5
        a0 = rnd.uniform(0, 2 * math.pi)
        anim_particle(ob, tb, a0, rnd.uniform(0, 30), rnd.uniform(26, 110), rnd.uniform(-0.045, 0.085),
                      rnd.uniform(0.35, 2.4) * (1.4 if j % 11 == 0 else 1.0), rnd.uniform(-4, 9),
                      (rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), rnd.uniform(-0.06, 0.06)))
    # halftone comic dots drifting outward (CMY-ish)
    dcols = ["cyan", "mag", "white", "red", "blue"]
    for j in range(110):
        ob = link(s, bpy.data.objects.new(f"dot{j}", disc))
        ob.color = cols[rnd.choice(dcols)]
        tb = R_F0 + rnd.random() * 8
        anim_particle(ob, tb, rnd.uniform(0, 2 * math.pi), rnd.uniform(10, 120), rnd.uniform(16, 70),
                      rnd.uniform(-0.03, 0.05), rnd.uniform(0.07, 0.32), rnd.uniform(-3, 4), (0, 0, 0))

    # web filaments: spiral arcs that grow out of the centre and keep swirling
    fil_mat = emission_material("filament", strength=2.2, use_object_color=True)
    for j in range(34):
        cu = bpy.data.curves.new(f"fil{j}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = rnd.choice([0.010, 0.014, 0.020])
        cu.bevel_resolution = 1
        sp = cu.splines.new("POLY")
        npts = 40
        sp.points.add(npts - 1)
        turns = rnd.uniform(0.45, 1.35) * rnd.choice([-1, 1])
        rmax = rnd.uniform(5.0, 22.0)
        a0 = rnd.uniform(0, 2 * math.pi)
        for i in range(npts):
            u = i / (npts - 1)
            r = rmax * (u ** 1.35)
            a = a0 + turns * 2 * math.pi * u
            wob = 0.18 * math.sin(u * 17 + j)
            sp.points[i].co = (r * math.cos(a) * (1 + wob * 0.2), r * math.sin(a) * (1 + wob * 0.2), -2.0 + wob * 2.0, 1.0)
        cu.materials.append(fil_mat)
        ob = link(s, bpy.data.objects.new(f"fil{j}", cu))
        ob.color = cols[rnd.choice(["white", "cyan", "cyan", "red", "blue", "white"])]
        tb = R_F0 + rnd.uniform(0, 6)
        tw = rnd.uniform(0.04, 0.12) * rnd.choice([-1, 1])
        for f in frames:
            t = f - tb
            g = clamp01(t / 4.0)
            fade = 1.0 - smooth((f - 256.5) / 3.5)
            cu.bevel_factor_start = 0.0
            cu.bevel_factor_end = max(0.0001, g)
            cu.keyframe_insert("bevel_factor_end", frame=f)
            cu.bevel_factor_start = clamp01(1.0 - fade) * max(g, 0.0) * 0.98
            cu.keyframe_insert("bevel_factor_start", frame=f)
            set_key(ob, f, loc=(0, 0, rnd.uniform(-1, 1) * 0.0), rot=Euler((0, 0, tw * max(t, 0) * 1.0), "XYZ"),
                    scale=(1.0 + 0.9 * clamp01(t / 8.0), 1.0 + 0.9 * clamp01(t / 8.0), 1.0), hide=(t < 0 or fade <= 0.0))


# =====================================================================================================================
# 3. SHOCKWAVE  (comp 480-489)
# =====================================================================================================================

S_F0, S_F1 = 480, 489
S_CENTER = (1110.0, 443.0)
S_RADIUS = [[480, 45], [481, 210], [482, 430], [483, 655], [484, 880], [485, 1085], [486, 1260], [487, 1400], [488, 1500],
            [489, 1620]]
S_WIDTH = [[480, 55], [481, 70], [482, 85], [483, 100], [484, 112], [485, 122], [486, 130], [487, 138], [488, 145],
           [489, 150]]
S_BRIGHT = [[480, 2.4], [481, 2.0], [482, 1.6], [483, 1.35], [484, 1.1], [485, 0.9], [486, 0.7], [487, 0.5], [488, 0.28],
            [489, 0.0]]


def build_shockwave(args):
    s = setup_scene(args, "shockwave", S_F0, S_F1, motion_blur=False)
    ortho_camera(s)
    set_world(s, color=(0, 0, 0, 1))
    frames = list(range(S_F0, S_F1 + 1))
    me = bpy.data.meshes.new("wave")
    hw, hh = W / 2 + 4, H / 2 + 4
    me.from_pydata([(-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0)], [], [(0, 1, 2, 3)])
    ob = link(s, bpy.data.objects.new("wave", me))
    ob.data.materials.append(shockwave_material(frames))
    build_sparks(s, frames)
    s.frame_set(S_F0)
    glow_compositor(s, [dict(threshold=0.8, size=0.35, strength=0.35, tint="#FFFFFF"),
                        dict(threshold=1.2, size=0.7, strength=0.22, tint="#9CC0FF")])
    return s


def shockwave_material(frames):
    m = bpy.data.materials.new("shockwave")
    m.use_nodes = True
    nt = m.node_tree
    NB.nt = nt
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    rad, rad_n = val(0, "radius")
    wid, wid_n = val(0, "width")
    bri, bri_n = val(0, "bright")
    tm, tm_n = val(0, "time")
    keyframe_value(rad_n, frames, lambda f: keys(S_RADIUS, f))
    keyframe_value(wid_n, frames, lambda f: keys(S_WIDTH, f))
    keyframe_value(bri_n, frames, lambda f: keys(S_BRIGHT, f))
    keyframe_value(tm_n, frames, lambda f: f - S_F0)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    wx, wy, _ = sep_xyz(tc.outputs["Window"])
    dx = wx * float(W) - S_CENTER[0]
    dy = (1.0 - wy) * float(H) - S_CENTER[1]
    dist = sqrt(dx * dx + dy * dy)
    inv = 1.0 / vmax(dist, 1.0)
    # an uneven blast front: low-frequency radius wobble that changes per frame
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.noise_dimensions = "3D"
    nz.inputs["Scale"].default_value = 2.2
    nz.inputs["Detail"].default_value = 4.0
    nt.links.new(comb_xyz(dx * inv * 2.0, dy * inv * 2.0, tm * 0.7), nz.inputs["Vector"])
    nz2 = nt.nodes.new("ShaderNodeTexNoise")
    nz2.noise_dimensions = "3D"
    nz2.inputs["Scale"].default_value = 11.0
    nz2.inputs["Detail"].default_value = 2.0
    nt.links.new(comb_xyz(dx * inv * 5.0, dy * inv * 5.0, tm * 1.3 + 9.0), nz2.inputs["Vector"])
    wob = (X(nz.outputs["Fac"]) - 0.5) * (0.07 * rad + 4.0) + (X(nz2.outputs["Fac"]) - 0.5) * (0.018 * rad + 2.0)
    d = dist + wob
    # chromatic split of the blast front: R rides the front, B lags (dispersion)
    sp = wid * 0.075

    def ring(r_off):
        """signed distance from the front in units of the rim width, behind the front negative"""
        return (d - rad + r_off) / vmax(wid, 1.0)

    def profile(sd):
        # white-hot line right at the front, a bright lens-like gradient behind it (refraction band),
        # a thin dark-less caustic edge in front of it
        line = fn("EXPONENT", -(sd * sd) / 0.012)
        behind = sstep(sd, -1.0, -0.02) * (1.0 - sstep(sd, -0.02, 0.0)) * 0.0
        band = sstep(sd, -1.0, 0.0) * (1.0 - sstep(sd, 0.0, 0.10))
        band = band * (0.28 + 0.72 * sstep(sd, -1.0, -0.0)) ** 1.6
        edge = fn("EXPONENT", -((sd - 0.14) * (sd - 0.14)) / 0.004) * 0.55
        return line * 1.4 + band * 0.62 + edge + behind

    pr = profile(ring(-sp))
    pg = profile(ring(0.0))
    pb = profile(ring(sp))
    # concentric caustic ripples inside the band (the "refracted" streaks)
    rip = absv(sin(d * 0.26 - tm * 2.0)) * sstep(ring(0.0), -0.95, -0.1) * (1.0 - sstep(ring(0.0), -0.1, 0.02))
    rip = rip * (X(nz2.outputs["Fac"]) * 1.0) * 0.30
    # the opening flash and core
    core = fn("EXPONENT", -(dist * dist) / (rad * 0.9 + 30.0) ** 2.0 * 6.0) * sstep(tm, 4.0, 0.0)
    cr = (pr + rip * 0.8 + core * 1.3) * bri
    cg = (pg + rip * 0.9 + core * 1.2) * bri
    cb = (pb + rip * 1.0 + core * 1.1) * bri
    # blue-white, with a warm orange edge from the red channel's lead
    cr = cr * 1.0
    cg = cg * 0.92
    cb = cb * 1.0
    alpha = clamp(vmax(vmax(cr, cg), cb))
    invv = 1.0 / vmax(alpha, 0.002)
    emit = comb_rgb(clamp(cr * invv), clamp(cg * invv), clamp(cb * invv))
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(emit, em.inputs["Color"])
    tr_ = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(alpha.s, mx.inputs[0])
    nt.links.new(tr_.outputs["BSDF"], mx.inputs[1])
    nt.links.new(em.outputs["Emission"], mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    return m


def build_sparks(s, frames):
    rnd = random.Random(480)
    mat = emission_material("spark", strength=1.0, use_object_color=True)
    quad = bpy.data.meshes.new("spark")
    quad.from_pydata([(0.0, -0.5, 0), (1.0, -0.5, 0), (1.0, 0.5, 0), (0.0, 0.5, 0)], [], [(0, 1, 2, 3)])
    quad.materials.append(mat)
    cw, cy = S_CENTER[0] - W / 2, H / 2 - S_CENTER[1]
    warm = [(1.0, 0.85, 0.55, 1), (1.0, 0.62, 0.30, 1), (1.0, 1.0, 1.0, 1), (0.75, 0.88, 1.0, 1), (1.0, 0.45, 0.25, 1)]

    def front(f):
        return keys(S_RADIUS, f)

    for j in range(320):
        ob = link(s, bpy.data.objects.new(f"spark{j}", quad))
        ob.color = rnd.choice(warm)
        ang = rnd.uniform(0, 2 * math.pi)
        lag = rnd.uniform(0.35, 1.12)                  # fraction of the front radius
        drift = rnd.uniform(0.0, 0.5)
        life = rnd.uniform(3.0, 9.5)
        t0 = S_F0 + rnd.choice([0, 0, 0, 1, 1, 2, 3]) + rnd.random() * 0.4
        width = rnd.uniform(1.2, 3.8)
        for f in frames:
            t = f - t0
            if t < 0 or t > life:
                set_key(ob, f, loc=(0, 0, 1), rot=Euler((0, 0, 0)), scale=(0.01, 0.01, 1), hide=True)
                continue
            rho = front(f) * (lag + drift * smooth(t / life) * 0.25) + 6.0 * t
            rho_prev = front(f - 1) * (lag + drift * smooth((t - 1) / life) * 0.25) + 6.0 * (t - 1)
            length = max(6.0, (rho - rho_prev) * rnd.uniform(0.9, 1.4))
            fade = (1.0 - smooth((t - life * 0.45) / (life * 0.55))) * smooth(t / 0.6)
            ln = max(0.01, length * (0.4 + 0.6 * fade))
            wd = max(0.01, width * fade)
            x = cw + (rho - ln) * math.cos(ang)
            y = cy + (rho - ln) * math.sin(ang)
            set_key(ob, f, loc=(x, y, 1), rot=Euler((0, 0, ang)), scale=(ln, wd, 1), hide=fade < 0.02)


# =====================================================================================================================
# driver
# =====================================================================================================================

def parse(argv):
    ap = argparse.ArgumentParser(prog="elements.py")
    ap.add_argument("--element", default="all", help="timeless3d | rift | shockwave | all")
    ap.add_argument("--res-scale", type=float, default=1.0)
    ap.add_argument("--frames", help="comp frames: a-b ranges and single frames, comma separated (default: the element's range)")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--samples", type=int, default=0, help="Cycles samples (0 = the element's default)")
    ap.add_argument("--device", default="CPU", help="CPU | OPTIX | CUDA")
    ap.add_argument("--out", help="frames folder (default $AMV2_DATA/blender, else out/amv2/blender_frames)")
    ap.add_argument("--blend-dir", default="out/timeless/amv2/blender")
    ap.add_argument("--alpha", default="premul", choices=["premul", "straight"])
    ap.add_argument("--depth", type=int, default=8, choices=[8, 16])
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-blend", action="store_true")
    return ap.parse_args(argv)


def parse_frames(spec, f0, f1):
    if not spec:
        return list(range(f0, f1 + 1))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def main(argv):
    args = parse(argv)
    names = list(ELEMENTS) if args.element == "all" else [args.element]
    base_out = Path(args.out) if args.out else (Path(os.environ["AMV2_DATA"]) / "blender" if os.environ.get("AMV2_DATA")
                                                   else REPO / "out/amv2/blender_frames")
    builders = {"timeless3d": build_timeless, "rift": build_rift, "shockwave": build_shockwave}
    for name in names:
        info = ELEMENTS[name]
        a = argparse.Namespace(**vars(args))
        a.samples = args.samples or info["samples"]
        t0 = time.time()
        scene = builders[name](a)
        print(f"[{name}] scene built in {time.time() - t0:.1f}s")
        if not args.no_blend:
            bd = Path(args.blend_dir)
            bd.mkdir(parents=True, exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=str((bd / info["blend"]).resolve()), compress=True)
            print(f"[{name}] saved {bd / info['blend']}")
        if args.no_render:
            continue
        frames = parse_frames(args.frames, info["f0"], info["f1"])[::max(1, args.every)]
        out_dir = base_out / name
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp = out_dir / "_tmp.exr"
        times = []
        for f in frames:
            t1 = time.time()
            scene.frame_set(f)
            scene.render.filepath = str(tmp)
            bpy.ops.render.render(write_still=True)
            cover = exr_to_png(tmp, out_dir / f"{f:04d}.png", args.alpha, args.depth, seed=f)
            dt = time.time() - t1
            times.append(dt)
            print(f"[{name}] frame {f}: {dt:.1f}s  mean alpha {cover:.4f}", flush=True)
        if tmp.exists():
            tmp.unlink()
        if times:
            print(f"[{name}] {len(times)} frames, mean {sum(times) / len(times):.1f}s/frame at "
                  f"{scene.render.resolution_x}x{scene.render.resolution_y}, {a.samples} spp, device {args.device}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(argv)
