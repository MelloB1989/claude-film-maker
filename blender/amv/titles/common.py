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
