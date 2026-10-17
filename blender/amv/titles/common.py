"""Shared helpers of the AMV title styles: options, fonts, palettes, easing, and the Blender scene for one title.

Every style module `blender/amv/titles/<style>.py` exposes `render(spec: dict, out_dir: Path, opts: TitleOpts) -> None`
and writes `out_dir/<k:04d>.png` (1920x1080 RGBA, straight alpha, k = 0 .. spec['dur']-1) through `render_sequence`,
so the scene setup, resolution scale, frame selection and file naming are the same for all of them.

The first half of this file (options, fonts, colours, easing) imports no bpy and is unit-tested under plain Python; the
second half (scene, text, glow compositor) imports bpy lazily and runs inside `blender -b`.

Coordinates: titles are authored in After Effects comp pixels (x right, y down, 1920x1080, `pos` = the centre of the
word). The Blender camera is orthographic, looking down -Z at exactly that frame, 1 unit = 100 px, so screen px (x, y)
is world (x/100 - 9.6, 5.4 - y/100) - the same mapping the main scene uses (docs/PIPELINE-AMV.md, scene).
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

W, H = 1920, 1080
PX = 100.0   # screen px per Blender unit

REPO = Path(__file__).resolve().parents[3]
HANDOVER_FONTS = Path("/home/nikhil/code/film-making/handover/amv_handover/fonts")


@dataclass
class TitleOpts:
    """What a style needs besides the spec. Stable interface: styles are written by several agents against it."""
    res_scale: float = 1.0           # render at W*res_scale x H*res_scale (the PNGs are that size; 1.0 = 1920x1080)
    samples: int = 32                # Cycles samples per pixel (denoised); EEVEE: TAA samples
    fonts_dir: Path | None = None    # a folder searched first for font files (then the film's fonts, then the handover's)
    engine: str = "CYCLES"           # CYCLES | EEVEE (EEVEE needs a GL context: not available headless on CPU boxes)
    frames: list[int] | None = None  # title frames k to render (None = all); lets a test render 2 frames, a farm split
    film_dir: Path | None = None     # the film folder (fonts/, hdri/ lookups)
    seed: int = 0
    extra: dict = field(default_factory=dict)   # style-specific knobs from the CLI (`--set key=value`)

    @property
    def size(self) -> tuple[int, int]:
        return (max(2, int(round(W * self.res_scale))), max(2, int(round(H * self.res_scale))))

    def font_dirs(self) -> list[Path]:
        dirs = []
        if self.fonts_dir:
            dirs.append(Path(self.fonts_dir))
        if self.film_dir:
            dirs.append(Path(self.film_dir) / "fonts")
        dirs.append(REPO / "fonts")
        dirs.append(HANDOVER_FONTS)
        return [d for d in dirs if d.is_dir()]


# ---- fonts -------------------------------------------------------------------------------------------------------

# role -> candidate file names (first found wins). AE's pickFont lists, same order of preference.
FONT_FILES = {
    "chinese_rocks": ["chinese rocks rg.otf", "ChineseRocksRg-Regular.otf"],
    "anton": ["Anton-Regular.ttf"],
    "bebas": ["BebasNeue-Regular.ttf"],
    "barlow_black_italic": ["BarlowCondensed-BlackItalic.ttf"],
    "exo2_black_italic": ["Exo2-BlackItalic.ttf"],
    "orbitron": ["Orbitron-Bold.ttf"],
    "montserrat_light": ["Montserrat-Light.ttf"],
    "spider_man": ["Spider-Man.otf.ttf", "Spider-Man.otf"],
}


def find_font(role: str, opts: TitleOpts) -> Path:
    """The font file for `role` (a key of FONT_FILES, or a file name) in the options' font folders."""
    names = FONT_FILES.get(role, [role])
    for d in opts.font_dirs():
        for n in names:
            if (d / n).is_file():
                return d / n
        for p in d.iterdir():   # case-insensitive fallback
            if p.name.lower() in {n.lower() for n in names}:
                return p
    raise FileNotFoundError(f"font {role!r} ({names}) not found in {[str(d) for d in opts.font_dirs()]}")


# ---- colour ------------------------------------------------------------------------------------------------------

def hex_rgb(h: str) -> tuple[float, float, float]:
    """'#RRGGBB' -> sRGB floats 0..1."""
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(h: str, a: float = 1.0) -> tuple[float, float, float, float]:
    """'#RRGGBB' as a linear RGBA tuple (what Blender socket defaults take)."""
    r, g, b = hex_rgb(h)
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), a)


def mix_hex(a: str, b: str, u: float) -> str:
    """Blend two hex colours in sRGB (u = 0 -> a)."""
    ra, rb = hex_rgb(a), hex_rgb(b)
    return "#" + "".join(f"{int(round((x + (y - x) * u) * 255)):02X}" for x, y in zip(ra, rb))


# Gradient ramps (top -> bottom) + glow colours of text_lib.jsx's TPAL, and Novax's palettes (novax_lib.jsx).
TPAL = {
    "chrome": {"top": "#F4F4F2", "mid": "#D3CDC0", "bot": "#7E848D", "ext": "#2A2E35", "glow": "#FFFFFF"},
    "gold": {"top": "#FCF8EA", "mid": "#EDC466", "bot": "#B4782F", "ext": "#8E561D", "glow": "#FFC86A"},
    "ice": {"top": "#F1F6F8", "mid": "#AAD1ED", "bot": "#335E86", "ext": "#152C47", "glow": "#7FC8FF"},
    "red": {"top": "#FFF0EC", "mid": "#E8323C", "bot": "#7A0E12", "ext": "#3A0507", "glow": "#FF2A3A"},
    "violet": {"top": "#F4ECFF", "mid": "#B675FF", "bot": "#4A1F8A", "ext": "#1E0B3A", "glow": "#9E59FF"},
    "green": {"top": "#F2FFEC", "mid": "#98FF75", "bot": "#2F7A1C", "ext": "#0F2A08", "glow": "#57FF1F"},
}

NOVAX_PALETTES = {
    "icy_blue": {"fill": "#75CDFF", "stroke": "#59CBFF", "glowA": "#DBF2FF", "glowB": "#1FADFF", "deep": "#225573"},
    "blood_red": {"fill": "#FF4D5A", "stroke": "#FF3350", "glowA": "#FFDBDE", "glowB": "#E0001A", "deep": "#5A0F16"},
    "toxic_green": {"fill": "#98FF75", "stroke": "#8BFF59", "glowA": "#E4FFDB", "glowB": "#57FF1F", "deep": "#377322"},
    "gold": {"fill": "#FFD675", "stroke": "#FFC559", "glowA": "#FFF4DB", "glowB": "#FFBC1F", "deep": "#735B22"},
    "violet": {"fill": "#B675FF", "stroke": "#9E59FF", "glowA": "#ECDBFF", "glowB": "#871FFF", "deep": "#482273"},
    "hot_pink": {"fill": "#FF75CD", "stroke": "#FF59CB", "glowA": "#FFDBF2", "glowB": "#FF1FAD", "deep": "#732255"},
    "ember_orange": {"fill": "#FFA875", "stroke": "#FF8E59", "glowA": "#FFE8DB", "glowB": "#FF711F", "deep": "#734022"},
    "white_chrome": {"fill": "#CEDDEB", "stroke": "#F5FAFF", "glowA": "#FFFFFF", "glowB": "#98B8D9", "deep": "#525C66"},
}


# ---- easing / keys -----------------------------------------------------------------------------------------------

def clamp01(u: float) -> float:
    return 0.0 if u < 0.0 else 1.0 if u > 1.0 else u


def ease_out_expo(u: float) -> float:
    u = clamp01(u)
    return 1.0 if u >= 1.0 else 1.0 - 2.0 ** (-10.0 * u)


def ease_in_out(u: float) -> float:
    u = clamp01(u)
    return u * u * (3.0 - 2.0 * u)


def lin_keys(keys, f: float):
    """AE linear keys `[[frame, value], ...]` at (title) frame `f`: held outside, linear inside; values may be lists.
    (Same semantics as `filmtools.amv.plan.keys_lin`, repeated here so a style runs with no tools/ on the path.)"""
    ks = sorted(keys, key=lambda k: k[0])
    if f <= ks[0][0]:
        return ks[0][1]
    if f >= ks[-1][0]:
        return ks[-1][1]
    for (f0, v0), (f1, v1) in zip(ks, ks[1:]):
        if f0 <= f <= f1:
            u = 0.0 if f1 == f0 else (f - f0) / (f1 - f0)
            if isinstance(v0, (list, tuple)):
                return [x + (y - x) * u for x, y in zip(v0, v1)]
            return v0 + (v1 - v0) * u
    return ks[-1][1]


def ae_to_world(x: float, y: float) -> tuple[float, float]:
    """AE comp px (x right, y down) -> Blender world (x, y) of the title camera."""
    return (x / PX - W / PX / 2.0, H / PX / 2.0 - y / PX)


# =====================================================================================================================
# Blender side (imports bpy lazily: everything below runs inside `blender -b`)
# =====================================================================================================================

def _bpy():
    import bpy
    return bpy


def _mathutils():
    import mathutils
    return mathutils


@dataclass
class Glow:
    """One bloom layer of the compositor: AE Glow (threshold/radius/intensity) rebuilt on Blender's Glare node.

    `size` is Glare's 0..1 size (bloom radius relative to the image), `strength` its gain, `tint` the glow colour
    (multiplied on the glare-only output, so a white core with a red halo is two Glow entries)."""
    threshold: float = 0.8
    size: float = 0.5
    strength: float = 1.0
    tint: str = "#FFFFFF"
    kind: str = "Bloom"          # Bloom | Fog Glow | Streaks | ... (Glare node types)
    quality: str = "High"


class TitleScene:
    """A transparent 1920x1080 (x res_scale) title render: orthographic camera, world lighting, glow compositor.

    Typical use inside a style::

        sc = TitleScene(opts)                       # fresh empty scene (read_factory_settings(use_empty=True))
        sc.set_environment(hdri="studio", strength=1.0)
        ... build objects ...
        sc.build_compositor(glows=[Glow(...), ...], shadow=...)
        render_sequence(sc, spec, out_dir, opts, pose)   # pose(k) is called before each frame
    """

    def __init__(self, opts: TitleOpts):
        bpy = _bpy()
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.bpy = bpy
        self.opts = opts
        self.scene = bpy.context.scene
        self.fonts: dict = {}
        self.comp = None
        s = self.scene
        w, h = opts.size
        r = s.render
        r.resolution_x, r.resolution_y, r.resolution_percentage = w, h, 100
        r.film_transparent = True
        r.image_settings.file_format = "PNG"
        r.image_settings.color_mode = "RGBA"
        r.image_settings.color_depth = "8"
        r.image_settings.compression = 15
        r.use_compositing = True
        r.compositor_device = "CPU"                  # headless boxes have no GL context; also deterministic
        s.view_settings.view_transform = "Standard"   # an emission plane keeps its sRGB values (same as the main scene)
        s.view_settings.look = "None"
        s.display_settings.display_device = "sRGB"
        s.render.fps = 30
        self._engine(opts)
        self._camera()

    # -- engine / camera / world ------------------------------------------------------------------------------------
    def _engine(self, opts: TitleOpts):
        s = self.scene
        if opts.engine.upper().startswith("EEVEE"):
            s.render.engine = "BLENDER_EEVEE"
            s.eevee.taa_render_samples = opts.samples
            return
        s.render.engine = "CYCLES"
        c = s.cycles
        c.device = "CPU"
        c.samples = opts.samples
        c.use_adaptive_sampling = True
        c.adaptive_threshold = 0.02
        c.use_denoising = True
        try:
            c.denoiser = "OPENIMAGEDENOISE"
        except TypeError:
            pass
        c.max_bounces = 6
        c.glossy_bounces = 4
        c.diffuse_bounces = 2
        c.transmission_bounces = 2
        c.transparent_max_bounces = 8
        c.sample_clamp_indirect = 10.0
        c.filter_width = 1.2
        s.render.use_motion_blur = False
        s.render.threads_mode = "AUTO"

    def _camera(self):
        bpy = self.bpy
        cam = bpy.data.cameras.new("title_cam")
        cam.type = "ORTHO"
        cam.ortho_scale = W / PX                       # 19.2 units across 1920 px
        cam.clip_start, cam.clip_end = 0.1, 200.0
        ob = bpy.data.objects.new("title_cam", cam)
        self.scene.collection.objects.link(ob)
        ob.location = (0.0, 0.0, 20.0)                 # looking down -Z
        self.scene.camera = ob
        self.camera = ob

    def set_environment(self, hdri: str | Path | None = None, color: str = "#000000", strength: float = 1.0,
                        rotation=(0.0, 0.0, 0.0), tint: str | None = None):
        """World lighting for reflections. `hdri` = path of an .hdr/.exr (Poly Haven CC0, see hdri/README.md) or None
        for a flat colour. The film is transparent, so the world never shows - it only lights and reflects."""
        bpy = self.bpy
        w = bpy.data.worlds.new("title_world")
        w.use_nodes = True
        nt = w.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputWorld")
        bg = nt.nodes.new("ShaderNodeBackground")
        bg.inputs["Strength"].default_value = strength
        if hdri:
            tc = nt.nodes.new("ShaderNodeTexCoord")
            mp = nt.nodes.new("ShaderNodeMapping")
            rot = self.env_rot(rotation)
            for i in range(3):
                mp.inputs["Rotation"].default_value[i] = rot[i]
            env = nt.nodes.new("ShaderNodeTexEnvironment")
            env.image = bpy.data.images.load(str(hdri))
            nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
            nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
            if tint:
                mx = nt.nodes.new("ShaderNodeMix")
                mx.data_type = "RGBA"
                mx.blend_type = "MULTIPLY"
                mx.inputs["Factor"].default_value = 1.0
                mx.inputs["B"].default_value = lin(tint)
                nt.links.new(env.outputs["Color"], mx.inputs["A"])
                nt.links.new(mx.outputs["Result"], bg.inputs["Color"])
            else:
                nt.links.new(env.outputs["Color"], bg.inputs["Color"])
        else:
            bg.inputs["Color"].default_value = lin(color)
        nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
        self.scene.world = w
        return w

    def env_rot(self, default_deg=(0.0, 0.0, 0.0)):
        """Environment rotation in radians: `default_deg` (a style's choice, degrees) unless `--set env_rot=rx,ry,rz`."""
        if isinstance(default_deg, (int, float)):
            default_deg = (0.0, 0.0, float(default_deg))
        v = self.opts.extra.get("env_rot")
        deg = [float(x) for x in v.split(",")] if v else list(default_deg)
        return [math.radians(d) for d in deg]

    # -- fonts / text ---------------------------------------------------------------------------------------------
    def font(self, role: str):
        """The bpy font datablock for a FONT_FILES role (or file name), cached."""
        if role not in self.fonts:
            self.fonts[role] = self.bpy.data.fonts.load(str(find_font(role, self.opts)), check_existing=True)
        return self.fonts[role]

    def font_k(self, role: str) -> float:
        """Blender text `size` per em for this font (Blender's size 1 is not 1 em): measured as the extra width of
        'HH' over 'H' against the advance of H read from the font file, so it is exact and bearing-free."""
        key = ("k", role)
        if key in self.fonts:
            return self.fonts[key]
        from . import fontmetrics
        fm = fontmetrics.read_metrics(find_font(role, self.opts))
        bpy = self.bpy
        dims = []
        for body in ("H", "HH"):
            c = bpy.data.curves.new("k_" + body, "FONT")
            c.body, c.font, c.size = body, self.font(role), 1.0
            ob = bpy.data.objects.new("k_" + body, c)
            self.scene.collection.objects.link(ob)
            bpy.context.view_layer.update()
            dims.append(ob.dimensions.x)
            bpy.data.objects.remove(ob)
            bpy.data.curves.remove(c)
        k = (dims[1] - dims[0]) / fm.advance("H")   # blender units per em at size 1
        self.fonts[key] = k
        return k

    def metrics(self, role: str):
        from . import fontmetrics
        return fontmetrics.read_metrics(find_font(role, self.opts))

    def new_collection_object(self, name: str, data=None):
        ob = self.bpy.data.objects.new(name, data)
        self.scene.collection.objects.link(ob)
        return ob

    def empty(self, name: str):
        return self.new_collection_object(name, None)

    # -- compositor -------------------------------------------------------------------------------------------------
    def build_compositor(self, glows=(), shadow: dict | None = None, hblur: bool = False, mask_blur_index: int | None = None):
        """Render layers -> [horizontal slam blur] -> glow layers added on top (rgb and alpha) -> [drop shadow] -> out.

        The image stays premultiplied, as Cycles renders it, so glow in the transparent area raises alpha as well and
        the PNG's straight alpha un-premultiplies correctly. Returns a `Compositor` whose `set()` changes per-frame
        values (glow strengths, blur length, shadow opacity)."""
        self.comp = Compositor(self, list(glows), shadow, hblur, mask_blur_index)
        return self.comp

    def set_frame_path(self, path: Path):
        self.scene.render.filepath = str(path)


class Compositor:
    """The glow/blur/shadow node chain of a title (a compositor node group on the scene)."""

    def __init__(self, sc: TitleScene, glows, shadow, hblur, mask_blur_index):
        bpy = sc.bpy
        ng = bpy.data.node_groups.new("title_comp", "CompositorNodeTree")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        sc.scene.compositing_node_group = ng
        self.ng, self.nodes, self.links = ng, ng.nodes, ng.links
        self.glows = glows
        self.glow_nodes = []
        N = self.nodes
        rl = N.new("CompositorNodeRLayers")
        rl.scene = sc.scene
        cur = rl.outputs["Image"]
        self.blur = None
        if hblur:
            self.blur = N.new("CompositorNodeBlur")
            self.blur.inputs["Type"].default_value = "Gaussian"
            self.links.new(cur, self.blur.inputs["Image"])
            cur = self.blur.outputs["Image"]
        base = cur
        # glow-only layers, tinted, summed
        total = None
        for g in glows:
            gl = N.new("CompositorNodeGlare")
            gl.inputs["Type"].default_value = g.kind
            gl.inputs["Quality"].default_value = g.quality
            gl.inputs["Threshold"].default_value = g.threshold
            gl.inputs["Size"].default_value = g.size
            gl.inputs["Strength"].default_value = g.strength
            self.links.new(base, gl.inputs["Image"])
            glow = gl.outputs["Glare"]
            if g.tint.upper() != "#FFFFFF":
                mx = N.new("ShaderNodeMix")
                mx.data_type = "RGBA"
                mx.blend_type = "MULTIPLY"
                mx.inputs["Factor"].default_value = 1.0
                mx.inputs["B"].default_value = lin(g.tint)
                self.links.new(glow, mx.inputs["A"])
                glow = mx.outputs["Result"]
            self.glow_nodes.append(gl)
            if total is None:
                total = glow
            else:
                add = N.new("ShaderNodeMix")
                add.data_type = "RGBA"
                add.blend_type = "ADD"
                add.inputs["Factor"].default_value = 1.0
                self.links.new(total, add.inputs["A"])
                self.links.new(glow, add.inputs["B"])
                total = add.outputs["Result"]
        if total is not None:
            cur = self._add_light(base, total)
        if shadow:
            cur = self._shadow(cur, shadow)
        out = N.new("NodeGroupOutput")
        self.links.new(cur, out.inputs[0])

    def _add_light(self, base, glow):
        """base + glow on rgb; alpha = min(1, base.a + max(glow.rgb))."""
        N, L = self.nodes, self.links
        sb = N.new("CompositorNodeSeparateColor")
        sg = N.new("CompositorNodeSeparateColor")
        L.new(base, sb.inputs["Image"])
        L.new(glow, sg.inputs["Image"])
        rgb = N.new("ShaderNodeMix")
        rgb.data_type = "RGBA"
        rgb.blend_type = "ADD"
        rgb.inputs["Factor"].default_value = 1.0
        L.new(base, rgb.inputs["A"])
        L.new(glow, rgb.inputs["B"])
        m1 = N.new("ShaderNodeMath")
        m1.operation = "MAXIMUM"
        L.new(sg.outputs["Red"], m1.inputs[0])
        L.new(sg.outputs["Green"], m1.inputs[1])
        m2 = N.new("ShaderNodeMath")
        m2.operation = "MAXIMUM"
        L.new(m1.outputs[0], m2.inputs[0])
        L.new(sg.outputs["Blue"], m2.inputs[1])
        m3 = N.new("ShaderNodeMath")
        m3.operation = "ADD"
        m3.use_clamp = True
        L.new(sb.outputs["Alpha"], m3.inputs[0])
        L.new(m2.outputs[0], m3.inputs[1])
        sr = N.new("CompositorNodeSeparateColor")
        L.new(rgb.outputs["Result"], sr.inputs["Image"])
        cb = N.new("CompositorNodeCombineColor")
        L.new(sr.outputs["Red"], cb.inputs["Red"])
        L.new(sr.outputs["Green"], cb.inputs["Green"])
        L.new(sr.outputs["Blue"], cb.inputs["Blue"])
        L.new(m3.outputs[0], cb.inputs["Alpha"])
        return cb.outputs["Image"]

    def _shadow(self, cur, sh):
        """Soft black drop shadow under the image (AE Drop Shadow: opacity, distance along `direction`, softness)."""
        N, L = self.nodes, self.links
        dx = sh["dist"] * math.cos(math.radians(sh.get("direction", 135) - 90.0)) * -1.0
        dy = sh["dist"] * math.sin(math.radians(sh.get("direction", 135) - 90.0)) * -1.0
        tr = N.new("CompositorNodeTranslate")
        tr.inputs["X"].default_value = dx
        tr.inputs["Y"].default_value = dy
        L.new(cur, tr.inputs["Image"])
        bl = N.new("CompositorNodeBlur")
        bl.inputs["Type"].default_value = "Gaussian"
        bl.inputs["Size"].default_value = (sh.get("soft", 8), sh.get("soft", 8))
        L.new(tr.outputs["Image"], bl.inputs["Image"])
        sa = N.new("CompositorNodeSetAlpha")
        sa.inputs["Image"].default_value = (0, 0, 0, 1)
        sep = N.new("CompositorNodeSeparateColor")
        L.new(bl.outputs["Image"], sep.inputs["Image"])
        mul = N.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = sh.get("opacity", 0.5)
        L.new(sep.outputs["Alpha"], mul.inputs[0])
        cb = N.new("CompositorNodeCombineColor")
        cb.inputs["Red"].default_value = 0.0
        cb.inputs["Green"].default_value = 0.0
        cb.inputs["Blue"].default_value = 0.0
        L.new(mul.outputs[0], cb.inputs["Alpha"])
        self.shadow_mul = mul
        ov = N.new("CompositorNodeAlphaOver")
        L.new(cb.outputs["Image"], ov.inputs["Background"])
        L.new(cur, ov.inputs["Foreground"])
        return ov.outputs["Image"]

    def set_glow(self, i: int, strength: float | None = None, size: float | None = None, threshold: float | None = None):
        n = self.glow_nodes[i]
        if strength is not None:
            n.inputs["Strength"].default_value = max(0.0, strength)
        if size is not None:
            n.inputs["Size"].default_value = size
        if threshold is not None:
            n.inputs["Threshold"].default_value = threshold

    def set_hblur(self, px: float):
        """Horizontal box-ish blur of total length `px` (AE Motion Blur / Directional Blur length at direction 0)."""
        if self.blur is not None:
            self.blur.inputs["Size"].default_value = (max(0.0, px) / 2.0, 0.0)

    def set_shadow_opacity(self, op: float):
        self.shadow_mul.inputs[1].default_value = op


def render_sequence(sc: TitleScene, spec: dict, out_dir: Path, opts: TitleOpts, pose) -> list[Path]:
    """Render the title frames: `pose(k)` poses the scene for title frame k, then `out_dir/<k:04d>.png` is written.

    Honours `opts.frames` (a subset of k); returns the written paths. A frame already on disk is kept only if
    `opts.extra['skip_existing']` is set (farm resume), never silently."""
    dur = int(spec["dur"])
    ks = [k for k in range(dur) if opts.frames is None or k in set(opts.frames)]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for k in ks:
        p = out_dir / f"{k:04d}.png"
        if opts.extra.get("skip_existing") and p.exists():
            continue
        pose(k)
        sc.scene.frame_set(k)
        sc.scene.render.filepath = str(p)
        sc.bpy.ops.render.render(write_still=True)
        written.append(p)
    return written


# ---- materials ---------------------------------------------------------------------------------------------------

class Mat:
    """A node material with named control values, so a style can animate it per frame without keyframes.

        m = Mat("fill")                      # Principled BSDF -> Material Output
        fade = m.value("fade", 1.0)          # a Value node; m.set("fade", 0.5) changes it before a frame
        m.bsdf.inputs["Alpha"] ...           # wire as you like with m.link(a, b)
    """

    def __init__(self, name: str, bpy=None):
        self.bpy = bpy or _bpy()
        self.mat = self.bpy.data.materials.new(name)
        self.mat.use_nodes = True
        self.nt = self.mat.node_tree
        self.nt.nodes.clear()
        self.out = self.nt.nodes.new("ShaderNodeOutputMaterial")
        self.bsdf = self.nt.nodes.new("ShaderNodeBsdfPrincipled")
        self.nt.links.new(self.bsdf.outputs["BSDF"], self.out.inputs["Surface"])
        self.values: dict = {}

    def node(self, idname: str, **kw):
        n = self.nt.nodes.new(idname)
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def value(self, name: str, v: float = 0.0):
        n = self.nt.nodes.new("ShaderNodeValue")
        n.label = name
        n.outputs[0].default_value = v
        self.values[name] = n
        return n.outputs[0]

    def set(self, name: str, v: float):
        self.values[name].outputs[0].default_value = v

    def math(self, op: str, a=None, b=None, c=None, clamp: bool = False):
        n = self.nt.nodes.new("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        for i, x in enumerate((a, b, c)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = x
            else:
                self.link(x, n.inputs[i])
        return n.outputs[0]

    def mix(self, a, b, fac, blend="MIX"):
        """RGBA mix node; a/b are sockets or colour tuples; returns the result socket."""
        n = self.nt.nodes.new("ShaderNodeMix")
        n.data_type = "RGBA"
        n.blend_type = blend
        for key, x in (("A", a), ("B", b)):
            if isinstance(x, (tuple, list)):
                n.inputs[key].default_value = x
            else:
                self.link(x, n.inputs[key])
        if isinstance(fac, (int, float)):
            n.inputs["Factor"].default_value = fac
        else:
            self.link(fac, n.inputs["Factor"])
        return n.outputs["Result"]

    def object_xyz(self, obj):
        """The shader's position in `obj`'s space (x, y, z sockets): a gradient/sweep that stays glued to the word
        however the word is scaled or sheared, because Object coordinates undo the object's matrix."""
        tc = self.nt.nodes.new("ShaderNodeTexCoord")
        tc.object = obj
        sep = self.nt.nodes.new("ShaderNodeSeparateXYZ")
        self.link(tc.outputs["Object"], sep.inputs["Vector"])
        return sep.outputs["X"], sep.outputs["Y"], sep.outputs["Z"]

    def ramp(self, fac, stops):
        """Colour ramp node (stops = [(pos, '#RRGGBB'), ...]) driven by `fac`; returns the colour socket."""
        n = self.nt.nodes.new("ShaderNodeValToRGB")
        cr = n.color_ramp
        cr.interpolation = "LINEAR"
        while len(cr.elements) > len(stops):
            cr.elements.remove(cr.elements[-1])
        while len(cr.elements) < len(stops):
            cr.elements.new(0.5)
        for el, (p, c) in zip(cr.elements, stops):
            el.position = p
            el.color = lin(c)
        self.link(fac, n.inputs["Fac"])
        return n.outputs["Color"]

    def emission_only(self, color, strength=1.0, alpha=None):
        """Replace the Principled with an Emission shader (flat glow colour); `alpha` = value socket or None."""
        em = self.nt.nodes.new("ShaderNodeEmission")
        if isinstance(color, (tuple, list)):
            em.inputs["Color"].default_value = color
        else:
            self.link(color, em.inputs["Color"])
        if isinstance(strength, (int, float)):
            em.inputs["Strength"].default_value = strength
        else:
            self.link(strength, em.inputs["Strength"])
        surf = em.outputs["Emission"]
        if alpha is not None:
            tr = self.nt.nodes.new("ShaderNodeBsdfTransparent")
            mx = self.nt.nodes.new("ShaderNodeMixShader")
            self.link(alpha, mx.inputs["Fac"])
            self.link(tr.outputs["BSDF"], mx.inputs[1])
            self.link(surf, mx.inputs[2])
            surf = mx.outputs["Shader"]
        self.link(surf, self.out.inputs["Surface"])
        return surf


# ---- words: one text object per letter, tracked and sheared like After Effects text ---------------------------------

class Word:
    """A line of text as one FONT curve object per letter under a root empty.

    Why per letter: AE tracking is additive per character, Blender's `space_character` is multiplicative; the Novax
    hero opens from tracking -26 to +48 and must keep its centre. `layout(tracking)` re-places the letters from the font's
    own advances. The root's matrix carries position, scale, rotation and the shear: `shear` is the faux-italic slant
    (x += y * shear) and `oblique=(dx_px, dy_px)` slants the extrusion so a straight-on camera sees it run down-right
    like AE's stacked copies (back face displaced by dx, dy screen px).

    The root's origin is the middle of the cap height, centred horizontally on the ink, so `pos` = the AE layer
    position of a centred caps title."""

    def __init__(self, sc: TitleScene, text: str, role: str, size_px: float, tracking: float = 0.0, *, name: str = "word",
                 extrude_px: float = 0.0, bevel_px: float = 0.0, bevel_res: int = 3, outline_px: float = 0.0,
                 offset_px: float = 0.0, material=None, resolution: int = 12):
        bpy = sc.bpy
        self.sc, self.text, self.role, self.size_px = sc, text, role, float(size_px)
        self.fm = sc.metrics(role)
        self.k = sc.font_k(role)
        self.base = sc.empty(name + "_base")    # carries the parent link; the root's matrix lives in its parent inverse
        self.root = sc.empty(name)
        self.root.parent = self.base
        self.letters = []
        self.extrude_px = extrude_px
        font = sc.font(role)
        for i, ch in enumerate(text):
            if ch == " ":
                self.letters.append(None)
                continue
            c = bpy.data.curves.new(f"{name}_{i}", "FONT")
            c.body, c.font = ch, font
            c.size = size_px / PX / self.k
            c.resolution_u = resolution
            c.extrude = extrude_px / PX / 2.0
            c.bevel_depth = (bevel_px if not outline_px else outline_px / 2.0) / PX
            c.bevel_resolution = bevel_res
            c.offset = offset_px / PX
            if outline_px:
                c.fill_mode = "NONE"       # outlines only: with a bevel depth they become round tubes (neon / stroke)
            if material is not None:
                c.materials.append(material)
            ob = sc.new_collection_object(f"{name}_{i}", c)
            ob.parent = self.root
            self.letters.append(ob)
        self.layout(tracking)

    def advances_px(self, tracking: float) -> list[float]:
        return [a * self.size_px for a in self.fm.text_advances(self.text, tracking)]

    def width_px(self, tracking: float) -> float:
        adv = self.advances_px(tracking)
        return sum(adv) - (tracking / 1000.0 * self.size_px if adv else 0.0)

    @property
    def cap_px(self) -> float:
        return self.fm.cap * self.size_px

    def layout(self, tracking: float):
        """(Re)place the letters for AE tracking `tracking` (1/1000 em), centred on the word's ink."""
        adv = self.advances_px(tracking)
        total = self.width_px(tracking)
        x = -total / 2.0
        y = -self.cap_px / 2.0
        for ob, a in zip(self.letters, adv):
            if ob is not None:
                ob.location = (x / PX, y / PX, 0.0)
            x += a

    def pose(self, pos_px=(960.0, 540.0), scale=(1.0, 1.0), rot_deg: float = 0.0, shear: float = 0.0,
             oblique=(0.0, 0.0), z: float = 0.0):
        """Root transform: translate(pos) . rotate(rot, clockwise on screen) . scale . shear(italic, oblique extrusion)."""
        mu = _mathutils()
        wx, wy = ae_to_world(*pos_px)
        sh = mu.Matrix.Identity(4)
        sh[0][1] = shear
        d = max(self.extrude_px, 1e-6) / PX / 2.0
        sh[0][2] = -(oblique[0] / PX) / d if self.extrude_px else 0.0
        sh[1][2] = (oblique[1] / PX) / d if self.extrude_px else 0.0
        m = (mu.Matrix.Translation((wx, wy, z)) @ mu.Matrix.Rotation(-math.radians(rot_deg), 4, "Z")
             @ mu.Matrix.Diagonal((scale[0], scale[1], 1.0, 1.0)) @ sh)
        # matrix_basis would be decomposed into loc/rot/scale and lose the shear: keep the full affine matrix in the
        # parent inverse, which Blender uses verbatim.
        self.root.matrix_parent_inverse = m

    def attach(self, parent):
        """Parent the word (its base empty) to `parent`, e.g. the title's layer empty."""
        self.base.parent = parent

    def set_material(self, mat):
        for ob in self.letters:
            if ob is not None:
                ob.data.materials.clear()
                ob.data.materials.append(mat)


HDRI_DIR = Path(__file__).resolve().parent / "hdri"


def hdri_path(name: str) -> Path | None:
    """`hdri/<name>_1k.hdr` of this package (CC0 Poly Haven, see hdri/README.md), or None if not there."""
    for suffix in ("_1k.hdr", ".hdr", ".exr"):
        p = HDRI_DIR / f"{name}{suffix}"
        if p.is_file():
            return p
    return None


def expo(u: float, rate: float = 6.5) -> float:
    """Normalised exponential ease-out 0 -> 1 over u in 0..1 (AE: expo-out; ~90 % open at u = 0.5 with rate 6.5)."""
    u = clamp01(u)
    return (1.0 - 2.0 ** (-rate * u)) / (1.0 - 2.0 ** (-rate))


def brush_bar(sc: TitleScene, w_px: float, h_px: float, *, name: str = "bar", border: float = 0.9, stretch: float = 6.0,
              seed: float = 0.0, opacity: float = 1.0, color: str = "#000000"):
    """The rough dry-brush bar of the Novax tag (AE: black rect + Roughen Edges border ~0.9 h, stretch 39, complexity 7).

    A plane with a procedural alpha: the rectangle's edges are pushed by stretched noise, so the long edges ragged out
    in streaks along x like a dry brush. Returns (object, Mat); animate with `mat.set('alpha', v)`. The plane is
    `w_px` x `h_px` (before the ragged edge eats into it), unit-scaled, centred on its origin."""
    bpy = sc.bpy
    me = bpy.data.meshes.new(name)
    hw, hh = w_px / PX / 2.0, h_px / PX / 2.0
    me.from_pydata([(-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0)], [], [(0, 1, 2, 3)])
    ob = sc.new_collection_object(name, me)
    m = Mat(name)
    m.nt.nodes.remove(m.bsdf)
    x, y, _ = m.object_xyz(ob)
    r = border * h_px / PX * 0.5

    def noise(sx, sy, off):
        vx = m.math("MULTIPLY", x, sx)
        vy = m.math("MULTIPLY", y, sy)
        comb = m.node("ShaderNodeCombineXYZ")
        m.link(vx, comb.inputs["X"])
        m.link(vy, comb.inputs["Y"])
        comb.inputs["Z"].default_value = off + seed
        nz = m.node("ShaderNodeTexNoise", noise_dimensions="3D")
        nz.inputs["Scale"].default_value = 1.0
        nz.inputs["Detail"].default_value = 5.0
        nz.inputs["Roughness"].default_value = 0.6
        m.link(comb.outputs["Vector"], nz.inputs["Vector"])
        return m.math("MULTIPLY", m.math("SUBTRACT", nz.outputs["Fac"], 0.5), r * 2.0)

    ny = noise(1.0 / (stretch * h_px / PX) * 3.0, 1.0 / (h_px / PX) * 2.0, 0.0)     # long streaks along x
    nx = noise(1.0 / (h_px / PX) * 1.2, 1.0 / (stretch * h_px / PX) * 3.0, 7.3)
    ay = m.math("MULTIPLY", m.math("SUBTRACT", hh, m.math("ABSOLUTE", m.math("ADD", y, ny))), 90.0, clamp=True)
    ax = m.math("MULTIPLY", m.math("SUBTRACT", hw, m.math("ABSOLUTE", m.math("ADD", x, nx))), 90.0, clamp=True)
    alpha = m.math("MULTIPLY", m.math("MULTIPLY", ay, ax), m.value("alpha", opacity))
    m.emission_only(lin(color), 1.0, alpha=alpha)
    me.materials.append(m.mat)
    return ob, m


# ---- shared look builders ----------------------------------------------------------------------------------------

def flat_word(sc: TitleScene, text: str, role: str, size_px: float, tracking: float = 0.0, *, name: str = "flat",
              color: str = "#FFFFFF", strength: float = 1.0, extrude_px: float = 0.0):
    """A flat emissive word (tags, sub lines): returns (Word, Mat); `mat.set('alpha', v)` fades it."""
    m = Mat(name)
    m.nt.nodes.remove(m.bsdf)
    a = m.value("alpha", 1.0)
    m.emission_only(lin(color), strength, alpha=a)
    w = Word(sc, text, role, size_px, tracking, name=name, extrude_px=extrude_px, material=m.mat)
    return w, m


def sweep_mask(m: Mat, x, y, pos_value, width: float, lean: float = 0.0):
    """A slanted bar of `width` (word units, 1/100 px) centred where x + lean*y = pos_value, soft-edged, 0..1."""
    slant = m.math("ADD", x, m.math("MULTIPLY", y, lean)) if lean else x
    d = m.math("ABSOLUTE", m.math("SUBTRACT", slant, pos_value))
    return m.math("SUBTRACT", 1.0, m.math("DIVIDE", d, width * 0.5), clamp=True)


def metal_material(name: str, word_root, cap_px: float, ramp, *, metallic: float = 1.0, roughness: float = 0.18,
                   emission: float = 0.0, sweep_w_px: float = 0.0, lean: float = 0.0, sweep_strength: float = 4.0,
                   sweep_color: str = "#FFFFFF", height_fade=None):
    """PBR metal tinted by a vertical colour ramp (baseline 0 -> cap line 1, stops = [(pos, hex)]), optional light sweep.

    Controls (`m.set`): alpha, sweep_x (word units; far away = off), em (extra emission strength). The ramp tints the
    metal's reflection, so the HDRI's softbox bands still read as chrome/gold while the palette's top-to-bottom
    gradient of the AE title is kept."""
    m = Mat(name)
    x, y, _ = m.object_xyz(word_root)
    t = m.math("MULTIPLY_ADD", y, PX / cap_px, 0.5, clamp=True)
    col = m.ramp(t, ramp)
    b = m.bsdf
    m.link(col, b.inputs["Base Color"])
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = roughness
    em_col = col
    em_str = m.value("em", emission)
    if sweep_w_px:
        sw = sweep_mask(m, x, y, m.value("sweep_x", 99.0), sweep_w_px / PX, lean)
        em_col = m.mix(col, lin(sweep_color), sw)
        em_str = m.math("ADD", em_str, m.math("MULTIPLY", sw, sweep_strength))
    m.link(em_col, b.inputs["Emission Color"])
    m.link(em_str, b.inputs["Emission Strength"])
    alpha = m.value("alpha", 1.0)
    if height_fade:   # alpha scaled from height_fade[0] at the baseline to height_fade[1] at the cap line (floor reflection)
        a0, a1 = height_fade
        alpha = m.math("MULTIPLY", alpha, m.math("MULTIPLY_ADD", t, a1 - a0, a0))
    m.link(alpha, b.inputs["Alpha"])
    return m


class SubLine:
    """T_subline of text_lib.jsx: a small white italic Orbitron line whose tracking springs from +900 to 0 (on top of
    380) over 7 f from `f0`, fading in over 3 f and out over the last 4 f. `center` is the offset in px from the title
    layer's origin (the title position)."""

    def __init__(self, sc: TitleScene, text: str, parent, center, f0: int, dur: int, *, size: float = 40.0,
                 tracking: float = 380.0, span: float = 900.0, role: str = "orbitron", italic: float = 0.2,
                 color: str = "#FFFFFF"):
        self.word, self.mat = flat_word(sc, text, role, size, tracking, name="sub", color=color)
        self.word.attach(parent)
        self.center, self.f0, self.dur, self.base, self.span, self.italic = center, f0, dur, tracking, span, italic

    def update(self, k: int, master: float = 1.0):
        u = (k - self.f0) / 7.0
        self.word.layout(self.base + self.span * (1.0 - expo(u, 5.0)))
        self.word.pose((W / 2 + self.center[0], H / 2 + self.center[1]), shear=self.italic)
        a = lin_keys([[self.f0, 0.0], [self.f0 + 3, 1.0], [self.dur - 4, 1.0], [self.dur - 1, 0.0]], k)
        self.mat.set("alpha", a * master)


def set_layer(layer, pos_px, scale: float = 1.0, scale_xy=None):
    """Place a title's layer empty at AE `pos_px` with uniform `scale` (or (sx, sy)): children use pose((W/2+dx, H/2+dy))."""
    mu = _mathutils()
    sx, sy = scale_xy if scale_xy else (scale, scale)
    wx, wy = ae_to_world(*pos_px)
    layer.matrix_basis = mu.Matrix.Translation((wx, wy, 0.0)) @ mu.Matrix.Diagonal((sx, sy, 1.0, 1.0))
