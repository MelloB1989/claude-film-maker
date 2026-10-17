"""Shared pieces of the "basic" AMV title styles (sub, spring, extended, tag, watermark).

The After Effects builders (`text_lib.jsx`) are the spec. Every title is a pure function of the frame `k` (0 = the title's
`f_in`): it returns a `Frame`, a list of `Group`s (bottom to top) of flat 2D elements in screen px (y down, as AE and
`filmtools.amv.plan`). This module is bpy-free and numpy-free so the timing and the layout are unit-tested without
Blender; `blender/amv/titles/bl.py` turns a `Frame` into geometry, lights nothing (emission only) and runs the
compositor for shadows and glows, one view layer per `Group`.

What lives here:

- font metrics read straight from the TTF/OTF (advances, cap height): Blender's text objects have no tracking, and the
  line must be laid out ONCE (the "subtitle jumping" bug of the AE era came from re-centring while words appeared), so
  every glyph is placed by us, one Blender object per glyph;
- `line_layout`: AE point text, centre justified, `tracking` in 1/1000 em;
- AE key helpers: linear keys and `ease_keys` (linear keys with `easeKey`'s influence/speed-0 ease on some keys);
- the elements and the per-frame builders of each style: `sub_frame`, `spring_frame`, `extended_frame`, `tag_frame`,
  `watermark_frame`.
"""
from __future__ import annotations

import math
import os
import random
import struct
from dataclasses import dataclass, field, replace
from pathlib import Path

W, H = 1920, 1080
FPS = 30

# ---------------------------------------------------------------------------------------------------------------------
# fonts: metrics straight from the file


def font_dirs():
    here = Path(__file__).resolve()
    dirs = [Path(p) for p in os.environ.get("AMV_FONTS", "").split(os.pathsep) if p]
    for up in here.parents:
        d = up / "films" / "timeless" / "fonts"
        if d.is_dir():
            dirs.append(d)
            break
    dirs.append(Path("/home/nikhil/code/film-making/handover/amv_handover/fonts"))
    return dirs


# AE postscript-ish name -> file stem candidates (lowercased, spaces kept as in the handover)
FONT_FILES = {
    "Orbitron-Bold": ["Orbitron-Bold.ttf"],
    "Montserrat-Light": ["Montserrat-Light.ttf"],
    "Exo2-BlackItalic": ["Exo2-BlackItalic.ttf"],
    "ChineseRocksRg-Regular": ["chinese rocks rg.otf", "ChineseRocksRg-Regular.otf"],
    "BebasNeue-Regular": ["BebasNeue-Regular.ttf"],
}


EXTRA_FONT_DIRS = []   # searched first (TitleOpts.font_dirs(), set by bl.run_params)


def font_path(name, extra_dirs=()):
    for d in [*map(Path, extra_dirs), *map(Path, EXTRA_FONT_DIRS), *font_dirs()]:
        for fn in FONT_FILES.get(name, [name]):
            if (d / fn).is_file():
                return d / fn
    raise FileNotFoundError(f"font {name}: not in {[str(d) for d in font_dirs()]}")


class FontMetrics:
    """Advance widths, cap height, ascent/descent of a TTF/OTF in em fractions (cmap 4/12, hmtx, hhea, OS/2)."""

    def __init__(self, path):
        data = Path(path).read_bytes()
        self.path = str(path)
        if data[:4] == b"ttcf":
            raise ValueError("font collections are not supported")
        n = struct.unpack(">H", data[4:6])[0]
        tabs = {}
        for i in range(n):
            tag, _, off, ln = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
            tabs[tag.decode("latin1")] = (off, ln)

        def tab(t):
            o, ln = tabs[t]
            return data[o:o + ln]

        head, hhea, maxp = tab("head"), tab("hhea"), tab("maxp")
        self.upm = struct.unpack(">H", head[18:20])[0]
        self.ascent, self.descent = struct.unpack(">hh", hhea[4:8])
        nh = struct.unpack(">H", hhea[34:36])[0]
        hmtx = tab("hmtx")
        self._adv = [struct.unpack(">H", hmtx[4 * i:4 * i + 2])[0] for i in range(nh)]
        self.cap = 0.7
        if "OS/2" in tabs:
            os2 = tab("OS/2")
            ver = struct.unpack(">H", os2[:2])[0]
            if ver >= 2 and len(os2) >= 90:
                ch = struct.unpack(">h", os2[88:90])[0]
                if ch > 0:
                    self.cap = ch / self.upm
        self._cmap = self._read_cmap(tab("cmap"))

    @staticmethod
    def _read_cmap(c):
        n = struct.unpack(">H", c[2:4])[0]
        subs = []
        for i in range(n):
            pid, eid, off = struct.unpack(">HHI", c[4 + 8 * i:12 + 8 * i])
            subs.append((pid, eid, off))
        best = {}
        for pid, eid, off in sorted(subs, key=lambda s: (s[0] != 3 or s[1] not in (1, 10), s[2])):
            fmt = struct.unpack(">H", c[off:off + 2])[0]
            if fmt == 4 and "4" not in best:
                best["4"] = off
            if fmt == 12 and "12" not in best:
                best["12"] = off
        m = {}
        if "4" in best:
            o = best["4"]
            segx2 = struct.unpack(">H", c[o + 6:o + 8])[0]
            sc = segx2 // 2
            end = struct.unpack(f">{sc}H", c[o + 14:o + 14 + segx2])
            st = struct.unpack(f">{sc}H", c[o + 16 + segx2:o + 16 + 2 * segx2])
            dl = struct.unpack(f">{sc}h", c[o + 16 + 2 * segx2:o + 16 + 3 * segx2])
            ro_at = o + 16 + 3 * segx2
            ro = struct.unpack(f">{sc}H", c[ro_at:ro_at + segx2])
            for s in range(sc):
                for cc in range(st[s], end[s] + 1):
                    if cc == 0xFFFF:
                        continue
                    if ro[s] == 0:
                        g = (cc + dl[s]) & 0xFFFF
                    else:
                        p = ro_at + 2 * s + ro[s] + 2 * (cc - st[s])
                        g = struct.unpack(">H", c[p:p + 2])[0]
                        if g:
                            g = (g + dl[s]) & 0xFFFF
                    if g:
                        m[cc] = g
        if "12" in best:
            o = best["12"]
            ng = struct.unpack(">I", c[o + 12:o + 16])[0]
            for i in range(ng):
                a, b, g0 = struct.unpack(">III", c[o + 16 + 12 * i:o + 28 + 12 * i])
                for cc in range(a, b + 1):
                    m[cc] = g0 + cc - a
        return m

    def advance(self, ch):
        g = self._cmap.get(ord(ch), 0)
        return self._adv[min(g, len(self._adv) - 1)] / self.upm

    def has(self, ch):
        return ord(ch) in self._cmap


_FM = {}


def metrics(font):
    """FontMetrics of an AE font name (cached)."""
    if font not in _FM:
        _FM[font] = FontMetrics(font_path(font))
    return _FM[font]


# ---------------------------------------------------------------------------------------------------------------------
# text layout (AE point text, centre justified)


@dataclass(frozen=True)
class Placed:
    ch: str
    x: float      # glyph origin (left, on the baseline), px, relative to the line centre
    adv: float    # advance px (without tracking)


def line_layout(text, font, size, tracking=0.0, hscale=1.0):
    """Glyph origins of `text` centred on x = 0, baseline y = 0. `tracking` is AE's 1/1000 em added after each character;
    the trailing one counts in the centring, as in AE. Returns (list[Placed], width)."""
    fm = metrics(font)
    out, x = [], 0.0
    for ch in text:
        a = fm.advance(ch) * size * hscale
        out.append(Placed(ch, x, a))
        x += a + tracking / 1000.0 * size * hscale
    # AE centres the box including the trailing tracking (measured: the AE sub sits 2.8 px left of the ink centre)
    return [Placed(p.ch, p.x - x / 2, p.adv) for p in out], x


def cap_height(font, size):
    return metrics(font).cap * size


# ---------------------------------------------------------------------------------------------------------------------
# AE keys


def lin(keys, f):
    """AE linear keys `[[frame, value], ...]`: held outside the keys, linear inside; values numbers or tuples."""
    ks = sorted(keys, key=lambda k: k[0])
    if f <= ks[0][0]:
        return ks[0][1]
    if f >= ks[-1][0]:
        return ks[-1][1]
    for (f0, v0), (f1, v1) in zip(ks, ks[1:]):
        if f0 <= f <= f1:
            u = (f - f0) / (f1 - f0) if f1 > f0 else 1.0
            if isinstance(v0, (list, tuple)):
                return tuple(a + (b - a) * u for a, b in zip(v0, v1))
            return v0 + (v1 - v0) * u
    return ks[-1][1]


def _bez_y(u, y0, y1, y2, y3):
    return (1 - u) ** 3 * y0 + 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3 * y3


def _seg_ease(t, out_inf, in_inf):
    """Normalised progress at time fraction t of one key segment whose start key has temporal ease (speed 0, out
    influence `out_inf`, or None = linear side) and whose end key has `in_inf` (or None). AE's bezier: x handles at the
    influence fractions, y handles flat at a speed-0 end and along the chord on a linear side (1/3)."""
    x1 = out_inf if out_inf is not None else 1 / 3
    y1 = 0.0 if out_inf is not None else 1 / 3
    x2 = 1 - (in_inf if in_inf is not None else 1 / 3)
    y2 = 1.0 if in_inf is not None else 2 / 3
    lo, hi = 0.0, 1.0
    for _ in range(40):
        u = (lo + hi) / 2
        if _bez_y(u, 0, x1, x2, 1) < t:
            lo = u
        else:
            hi = u
    return _bez_y((lo + hi) / 2, 0, y1, y2, 1)


def ease_keys(keys, f, ease=None):
    """`lin` with `easeKey(prop, k, in%, out%)` on some keys. `ease` = {1-based key index: (in_influence %, out_influence %)}
    (speed 0, as `lib_ae.easeKey` sets it). Segments touching an eased key use AE's bezier; the rest stay linear."""
    ks = sorted(keys, key=lambda k: k[0])
    if not ease or f <= ks[0][0] or f >= ks[-1][0]:
        return lin(ks, f)
    for i, ((f0, v0), (f1, v1)) in enumerate(zip(ks, ks[1:])):
        if f0 <= f <= f1:
            e0, e1 = ease.get(i + 1), ease.get(i + 2)
            out_inf = e0[1] / 100 if e0 else None
            in_inf = e1[0] / 100 if e1 else None
            u = (f - f0) / (f1 - f0)
            if out_inf is None and in_inf is None:
                p = u
            else:
                p = _seg_ease(u, out_inf, in_inf)
            if isinstance(v0, (list, tuple)):
                return tuple(a + (b - a) * p for a, b in zip(v0, v1))
            return v0 + (v1 - v0) * p
    return ks[-1][1]


# ---------------------------------------------------------------------------------------------------------------------
# colours


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lerp_rgb(a, b, u):
    return tuple(x + (y - x) * u for x, y in zip(a, b))


# text_lib.jsx TPAL: ramp top -> bottom, mid tint, extrusion, glow
TPAL = {
    "chrome": dict(top="#F4F4F2", mid="#D3CDC0", bot="#7E848D", ext="#2A2E35", glow="#FFFFFF"),
    "gold": dict(top="#FCF8EA", mid="#EDC466", bot="#B4782F", ext="#8E561D", glow="#FFC86A"),
    "ice": dict(top="#F1F6F8", mid="#AAD1ED", bot="#335E86", ext="#152C47", glow="#7FC8FF"),
    "red": dict(top="#FFF0EC", mid="#E8323C", bot="#7A0E12", ext="#3A0507", glow="#FF2A3A"),
    "violet": dict(top="#F4ECFF", mid="#B675FF", bot="#4A1F8A", ext="#1E0B3A", glow="#9E59FF"),
    "green": dict(top="#F2FFEC", mid="#98FF75", bot="#2F7A1C", ext="#0F2A08", glow="#57FF1F"),
}


def ramp_stops(pal, n=9):
    """The colour stops of AE's `_gradFill`: an Ramp top -> bottom, then Tint (black -> bot, white -> mid) at 35 %.
    Returns [(t, (r, g, b))] with t = 0 at the top of the text, 1 at the bottom, colours in sRGB 0..1."""
    top, mid, bot = hex_rgb(pal["top"]), hex_rgb(pal["mid"]), hex_rgb(pal["bot"])
    out = []
    for i in range(n):
        t = i / (n - 1)
        c = lerp_rgb(top, bot, t)
        lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
        tinted = lerp_rgb(bot, mid, lum)
        out.append((t, lerp_rgb(c, tinted, 0.35)))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# elements


@dataclass(frozen=True)
class Solid:
    rgb: tuple


@dataclass(frozen=True)
class Ramp:
    """Vertical colour ramp in screen px: y0 (top) -> y1 (bottom), stops [(t, rgb)]."""
    y0: float
    y1: float
    stops: tuple


@dataclass(frozen=True)
class GlyphEl:
    """One glyph. (x, y) is its origin (baseline, left) on screen BEFORE the element transform; the element is scaled
    by (sx, sy) and rotated `rot` degrees clockwise about the pivot (px, py), then shifted by (dx, dy)."""
    ch: str
    font: str
    size: float
    x: float
    y: float
    fill: object
    opacity: float = 1.0
    sx: float = 1.0
    sy: float = 1.0
    rot: float = 0.0
    px: float = 0.0
    py: float = 0.0
    dx: float = 0.0
    dy: float = 0.0
    shear: float = 0.0          # faux italic (tan of the slant)
    stroke: tuple = None        # (rgb, width px): the outline, centred on the glyph edge
    stroke_only: bool = False   # outline only (no fill)
    depth: float = 0.0          # extrusion px (the subtle 3D)
    bevel: float = 0.0          # bevel px
    z: float = 0.0              # draw order inside a group (higher = in front)


@dataclass(frozen=True)
class PolyEl:
    """A filled polygon (convex or not) in screen px: used for bars, brackets, rings."""
    pts: tuple
    fill: object
    opacity: float = 1.0
    z: float = 0.0


@dataclass(frozen=True)
class Shadow:
    opacity: float      # 0..1
    dx: float
    dy: float
    soft: float         # blur radius px


@dataclass(frozen=True)
class Glow:
    rgb: tuple
    radius: float       # px (outer blur radius)
    intensity: float


@dataclass
class Group:
    name: str
    elems: list
    shadow: Shadow = None
    glows: tuple = ()
    smear: tuple = None     # (length px along x, along y): directional motion blur
    cut: tuple = None       # polygon (px) subtracted from the group's alpha before its glow (AE subtract mask)


@dataclass
class Frame:
    groups: list


def ae_shadow(opacity_pct, dist, soft, direction=135.0):
    """AE Drop Shadow -> Shadow: direction in AE degrees (0 = up, clockwise), so 135 is down-right."""
    a = math.radians(direction)
    return Shadow(opacity_pct / 100.0, dist * math.sin(a), -dist * math.cos(a), soft)


def polyline_poly(pts, width, closed=False):
    """Stroke a polyline as a list of quads (each a PolyEl point tuple) of constant width."""
    quads = []
    n = len(pts)
    segs = list(zip(pts, pts[1:] + ([pts[0]] if closed else [])))
    for (x0, y0), (x1, y1) in segs:
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln * width / 2, dx / ln * width / 2
        ex, ey = dx / ln * width / 2, dy / ln * width / 2
        quads.append(((x0 - ex + nx, y0 - ey + ny), (x1 + ex + nx, y1 + ey + ny),
                      (x1 + ex - nx, y1 + ey - ny), (x0 - ex - nx, y0 - ey - ny)))
    return quads


# ---------------------------------------------------------------------------------------------------------------------
# transforms of whole groups of elements (AE: a null / precomp layer with scale + position about an anchor)


def xform_elems(elems, center, scale=1.0, shift=(0.0, 0.0)):
    """Scale `elems` about `center` and shift them: how a parent null scales a title (AE scale about the anchor)."""
    cx, cy = center
    out = []
    for e in elems:
        if isinstance(e, GlyphEl):
            out.append(replace(e, x=cx + (e.x - cx) * scale + shift[0], y=cy + (e.y - cy) * scale + shift[1],
                               px=cx + (e.px - cx) * scale + shift[0], py=cy + (e.py - cy) * scale + shift[1],
                               size=e.size * scale, sx=e.sx, sy=e.sy, dx=e.dx * scale, dy=e.dy * scale,
                               depth=e.depth * scale, bevel=e.bevel * scale,
                               stroke=(e.stroke[0], e.stroke[1] * scale) if e.stroke else None,
                               fill=_scale_fill(e.fill, cy, scale, shift[1])))
        else:
            out.append(replace(e, pts=tuple((cx + (x - cx) * scale + shift[0], cy + (y - cy) * scale + shift[1])
                                            for x, y in e.pts), fill=_scale_fill(e.fill, cy, scale, shift[1])))
    return out


def _scale_fill(fill, cy, scale, sy):
    if isinstance(fill, Ramp):
        return replace(fill, y0=cy + (fill.y0 - cy) * scale + sy, y1=cy + (fill.y1 - cy) * scale + sy)
    return fill


def line_glyphs(text, font, size, fill, cx, cy_center, tracking=0.0, hscale=1.0, shear=0.0, **kw):
    """The glyphs of a centred line whose cap-height middle sits at `cy_center` (AE places the layer anchor on the text
    box middle; the cap middle is the visual centre of an all-caps line)."""
    pl, width = line_layout(text, font, size, tracking, hscale)
    base = cy_center + cap_height(font, size) / 2
    gl = [GlyphEl(p.ch, font, size, cx + p.x, base, fill, sx=hscale, px=cx + p.x + p.adv / 2, py=base, shear=shear, **kw)
          for p in pl if p.ch != " "]
    return gl, width


def with_opacity(elems, o):
    return [replace(e, opacity=e.opacity * o) for e in elems]


def fade_out(k, dur, n=4):
    """Opacity 100 -> 0 over frames dur-n .. dur-1 (text_lib's `_fadeOut` / keysLin)."""
    return lin([[dur - n, 1.0], [dur - 1, 0.0]], k)


ITALIC = 0.21   # AE faux italic slant (tan ~ 12 deg)


# ---------------------------------------------------------------------------------------------------------------------
# the brush bar (AE `_brushBar`: a black rough-edged bar, Roughen Edges, soft shadow, wiped in from the left)


def rough_bar(cx, cy, w, h, reveal, seed, amp=None, step=14.0):
    """Polygon of a black bar centred at (cx, cy) whose edges are roughened (low-frequency value noise, like AE Roughen
    Edges' fractal border), revealed from the left up to `reveal` (0..1). Returns the point tuple or None when empty.
    The noise is anchored to the bar so a growing reveal does not shimmer."""
    if reveal <= 0.002:
        return None
    amp = amp if amp is not None else max(2.0, h * 0.09)
    rnd = random.Random(seed)
    x0, x1 = cx - w / 2, cx - w / 2 + w * min(1.0, reveal)
    ny = max(2, int(h / step))
    nx = max(2, int(w / step))

    def noise(n):
        v = [rnd.uniform(-1, 1) for _ in range(n + 2)]
        return lambda t: _smooth(v, t * n)

    top, bot, left, right = noise(nx), noise(nx), noise(ny), noise(ny)
    xs = [x0 + (x1 - x0) * i / nx for i in range(nx + 1)]
    pts = []
    for x in xs:
        t = (x - (cx - w / 2)) / w
        pts.append((x, cy - h / 2 + amp * top(t)))
    for j in range(1, ny):
        t = j / ny
        pts.append((x1 + amp * 0.8 * right(t), cy - h / 2 + h * t))
    for x in reversed(xs):
        t = (x - (cx - w / 2)) / w
        pts.append((x, cy + h / 2 + amp * bot(t)))
    for j in range(ny - 1, 0, -1):
        t = j / ny
        pts.append((x0 + amp * 0.8 * left(t), cy - h / 2 + h * t))
    return tuple(pts)


def _smooth(v, t):
    i = int(math.floor(t))
    u = t - i
    u = u * u * (3 - 2 * u)
    return v[i] * (1 - u) + v[i + 1] * u


def wipe_progress(keys_f0, f, f1=None, dur_frames=5):
    """AE Linear Wipe completion 100 -> 0 over `dur_frames` from `keys_f0`: the revealed fraction at frame `f`."""
    return lin([[keys_f0, 0.0], [keys_f0 + dur_frames, 1.0]], f)


# ---------------------------------------------------------------------------------------------------------------------
# 1. SUB: word-by-word voice subtitle


def word_spans(text, words):
    """Character index after each word, as T_sub finds them: `full.indexOf(w, pos)`, falling back to `pos`.
    Returns [(frame, end_index)]."""
    pos, out = 0, []
    for fr, w in words:
        idx = text.find(w, pos)
        if idx < 0:
            idx = pos
        pos = idx + len(w)
        out.append((fr, pos))
    return out


def visible_chars(text, words, k):
    """How many leading characters are revealed at frame k (a hold key per spoken word: AE's range selector start)."""
    n = 0
    for fr, end in word_spans(text, words):
        if k >= fr:
            n = end
    return n


def sub_bar_reveal(text, words, k):
    """Revealed fraction of the bar: AE's Linear Wipe keys (frame-1 and frame+2 of each word hold the same completion,
    so between words it ramps linearly): completion = 100 - 100 pos/n - 4, starting at 100 (hidden)."""
    n = len(text)
    keys = [[0, 100.0]]
    for fr, end in word_spans(text, words):
        c = max(0.0, 100.0 - 100.0 * end / n - 4)
        keys.append([max(0, fr - 1), c])
        keys.append([fr + 2, c])
    keys.sort(key=lambda kv: kv[0])
    # AE keeps the last write at the same time: dedupe by time keeping the first of equal frames (setValueAtKey order)
    ded = []
    for fr, c in keys:
        if ded and ded[-1][0] == fr:
            ded[-1] = [fr, c]
        else:
            ded.append([fr, c])
    return 1.0 - lin(ded, k) / 100.0


def sub_frame(spec, k):
    """T_sub: the whole sentence is laid out ONCE (so nothing shifts as words appear); a word's glyphs exist from its
    frame on. White variant: rough black bar at 72 %; yellow variant: yellow with an orange halo, no bar."""
    dur = spec["dur"]
    yellow = spec.get("variant") == "yellow"
    font = "Orbitron-Bold"
    size = spec.get("size") or (50 if yellow else 46)
    pos = spec.get("pos") or [W / 2, H * (0.83 if yellow else 0.86)]
    text = spec["text"]
    words = spec.get("words") or [[0, text]]
    col = hex_rgb("#FBEA39" if yellow else "#FFFFFF")
    gl, width = line_glyphs(text, font, size, Solid(col), pos[0], pos[1], tracking=160 if yellow else 120,
                            shear=ITALIC)
    # glyph index in `text` (spaces are not glyphs)
    idx = [i for i, c in enumerate(text) if c != " "]
    nvis = visible_chars(text, words, k)
    shown = [g for g, i in zip(gl, idx) if i < nvis]
    o = fade_out(k, dur)
    groups = []
    if not yellow:
        # AE's wipe keys start opening the bar one frame before the first word, but nothing of it shows on the AE
        # render before the word (it is the same dark as the plate): keep the bar closed until the first word
        reveal = sub_bar_reveal(text, words, k) if k >= words[0][0] else 0.0
        bar_w, bar_h = width + 90, size * 1.25
        poly = rough_bar(pos[0], pos[1] + 1, bar_w, bar_h, reveal, seed=7)
        if poly:
            groups.append(Group("bar", [PolyEl(poly, Solid((0, 0, 0)), 0.72 * o)], shadow=ae_shadow(50, 12, 11)))
    glows = (Glow(hex_rgb("#FF9A1A"), 8.0, 1.0),) if yellow else ()
    groups.append(Group("text", with_opacity(shown, o), shadow=ae_shadow(85, 3, 6), glows=glows))
    return Frame(groups)


# ---------------------------------------------------------------------------------------------------------------------
# sub line under a hero title (T_subline)


def subline_group(text, pos, f0, dur, k, font="Orbitron-Bold", size=40):
    """T_subline: white italic, tracking 380 settling from +900 over 7 f (eased), fade in 3 f, out at dur-4."""
    tr = 380 + ease_keys([[f0, 900.0], [f0 + 7, 0.0]], k, {2: (80, 10)})
    o = lin([[f0, 0.0], [f0 + 3, 1.0]], k) * fade_out(k, dur)
    if o <= 0:
        return None
    gl, _ = line_glyphs(text, font, size, Solid((1, 1, 1)), pos[0], pos[1], tracking=tr, shear=ITALIC)
    return Group("subline", with_opacity(gl, o), shadow=ae_shadow(80, 3, 6))


# ---------------------------------------------------------------------------------------------------------------------
# 2. SPRING letters


def spring_amount(i, k):
    """The expressible selector of T_spring: 100 until letter i's turn (0.045 s per letter), then a damped cosine."""
    t = k / FPS - 0.045 * i
    if t < 0:
        return 100.0
    return 100.0 * math.cos(1.3 * t * 2 * math.pi) / math.exp(6 * t)


def spring_letter(g, amount):
    """The animator properties at selector amount (%): position +120 y, scale -100 (flip), rotation 35, opacity 0."""
    s = amount / 100.0
    sc = 1.0 + (-1.0 - 1.0) * s                  # 100 % at 0, -100 % at amount 100
    return replace(g, dy=g.dy + 120.0 * s, rot=g.rot + 35.0 * s, sx=g.sx * sc, sy=g.sy * sc,
                   opacity=g.opacity * max(0.0, min(1.0, 1.0 - s)))


def spring_frame(spec, k):
    dur = spec["dur"]
    pal = TPAL[spec.get("palette", "red")]
    font = "ChineseRocksRg-Regular"
    S = spec.get("size") or 330
    P = spec.get("pos") or [W / 2, H / 2]
    text = spec["text"]
    cap = cap_height(font, S)
    pl, width = line_layout(text, font, S, 25)
    base = P[1] + cap / 2
    top, bot = base - cap, base
    # AE's face reads as a pale tint of the palette (near-white pink for red), not the saturated mid colour
    ptop, pmid = hex_rgb(pal["top"]), hex_rgb(pal["mid"])
    ramp = Ramp(top, bot, ((0.0, lerp_rgb(ptop, pmid, 0.30)), (1.0, lerp_rgb(ptop, pmid, 0.45))))
    letters = [(i, p) for i, p in enumerate(pl) if p.ch != " "]   # AE's textIndex counts spaces
    o = lin([[dur - 5, 1.0], [dur - 1, 0.0]], k)

    def build(fill, **kw):
        out = []
        for i, p in letters:
            g = GlyphEl(p.ch, font, S, P[0] + p.x, base, fill, sx=1.0, shear=ITALIC,
                        px=P[0] + p.x + p.adv / 2, py=base, **kw)
            # AE animators rotate/scale about the character anchor: the middle of the baseline
            out.append(spring_letter(g, spring_amount(i, k)))
        return out

    shadow = build(Solid(hex_rgb("#570E0E")), dx=10.0, dy=12.0)
    face = build(ramp, depth=S * 0.03, bevel=S * 0.012)
    edge = build(Solid(hex_rgb(pal["top"])), stroke=(hex_rgb(pal["top"]), 1.6), stroke_only=True, z=1)
    scale = lin([[0, 100.0], [dur - 1, 107.0]], k) / 100.0
    c = (P[0], P[1])
    groups = [Group("shadow", with_opacity(xform_elems(shadow, c, scale), o)),
              Group("face", with_opacity(xform_elems(face, c, scale), o)),
              Group("edge", with_opacity(xform_elems(edge, c, scale), o),
                    glows=(Glow(hex_rgb(pal["glow"]), 18.0, 0.4),))]
    if spec.get("sub"):
        sg = subline_group(spec["sub"], [P[0], P[1] + S * 0.6], 10, dur, k)
        if sg:
            groups.append(sg)
    return Frame(groups)


# ---------------------------------------------------------------------------------------------------------------------
# 3. EXTENDED


def extended_frame(spec, k):
    dur = spec["dur"]
    pal = TPAL[spec.get("palette", "ice")]
    font = "Exo2-BlackItalic"
    S = spec.get("size") or 170
    P = spec.get("pos") or [W / 2, H / 2]
    text = spec["text"]
    # the parent null: layer position keys (relative to the comp centre, AE compensates the parenting at creation)
    off = ease_keys([[0, (W / 2 - 520, H / 2)], [6, (W / 2, H / 2)], [dur - 1, (W / 2 + 40, H / 2)]], k, {2: (85, 10)})
    shift = (off[0] - W / 2, off[1] - H / 2)
    cap = cap_height(font, S)
    gl, width = line_glyphs(text, font, S, Solid((1, 1, 1)), P[0], P[1], tracking=30, hscale=1.25)
    base = P[1] + cap / 2
    ramp = Ramp(base - cap, base, tuple(ramp_stops(pal)))
    face = [replace(g, fill=ramp, stroke=(hex_rgb("#101418"), 2.0), depth=S * 0.035, bevel=S * 0.012,
                    sx=g.sx) for g in gl]
    # diagonal slash cut: a thin subtract mask through the word
    sx = P[0] + width * 0.12
    slash = ((sx - 10, P[1] - S), (sx + 4, P[1] - S), (sx - 46, P[1] + S), (sx - 60, P[1] + S))
    o = lin([[0, 0.0], [2, 1.0], [dur - 4, 1.0], [dur - 1, 0.0]], k)
    face = [replace(g, opacity=o) for g in xform_elems(face, (P[0], P[1]), 1.0, shift)]
    sm = lin([[0, 120.0], [3, 50.0], [6, 0.0]], k)
    groups = []
    ring = hud_ring(P, S, k, dur)
    if ring:
        groups.append(Group("hud", ring))
    groups.append(Group("face", face, glows=(Glow(hex_rgb(pal["glow"]), 25.0, 0.8),),
                        smear=(sm, 0.0) if sm > 0.5 else None,
                        cut=tuple((x + shift[0], y + shift[1]) for x, y in slash)))
    if spec.get("sub"):
        sub_size = round(S * 0.33)
        sub, sw = line_glyphs(spec["sub"], "Montserrat-Light", sub_size, Solid((1, 1, 1)), P[0], P[1] + S * 0.62,
                              tracking=600)
        so = lin([[5, 0.0], [8, 1.0], [dur - 4, 1.0], [dur - 1, 0.0]], k)
        bw, bh = sw + 140, S * 0.42
        poly = rough_bar(P[0], P[1] + S * 0.62, bw, bh, wipe_progress(4, k), seed=11)
        if poly:
            groups.append(Group("bar", [PolyEl(poly, Solid((0, 0, 0)), fade_out(k, dur))], shadow=ae_shadow(50, 12, 11)))
        groups.append(Group("sub", with_opacity(sub, so)))
    return Frame(groups)


def hud_ring(P, S, k, dur):
    """The 'hud circle' of T_extended (white 2 px ring, diameter S*2.3, spins 25 deg/s, scale 60 -> 100 -> 110, opacity
    0 -> 45 % in 6 f). AE's was a plain ring, whose spin is invisible: ticks and gaps make the rotation read."""
    o = lin([[0, 0.0], [6, 0.45], [dur - 4, 0.45], [dur - 1, 0.0]], k)
    if o <= 0:
        return []
    sc = lin([[0, 60.0], [10, 100.0], [dur - 1, 110.0]], k) / 100.0
    r = S * 2.3 / 2 * sc
    rot = math.radians(25.0 * k / FPS)
    quads = []
    n = 72
    for i in range(n):
        if i % 12 in (5, 6):      # gaps
            continue
        a0, a1 = rot + 2 * math.pi * i / n, rot + 2 * math.pi * (i + 1.05) / n
        pts = [(P[0] + r * math.cos(a0 + t * (a1 - a0)), P[1] + r * math.sin(a0 + t * (a1 - a0))) for t in (0, 1)]
        quads += polyline_poly(pts, 2.0 * max(sc, 0.8))
    for i in range(12):           # ticks
        a = rot + 2 * math.pi * i / 12
        pts = [(P[0] + (r - 14) * math.cos(a), P[1] + (r - 14) * math.sin(a)),
               (P[0] + (r + 2) * math.cos(a), P[1] + (r + 2) * math.sin(a))]
        quads += polyline_poly(pts, 2.0)
    return [PolyEl(q, Solid((1, 1, 1)), o) for q in quads]


# ---------------------------------------------------------------------------------------------------------------------
# 4. TAG (tracked name tag + brackets)


def brackets(cx, cy, w, h, k, dur, L=26.0):
    """T_brackets: four 2.5 px white corner brackets, flicker-on, scaling 112 -> 100 about the box centre."""
    o = lin([[2, 0.0], [4, 0.9], [5, 0.3], [6, 0.9], [dur - 4, 0.9], [dur - 1, 0.0]], k)
    if o <= 0:
        return None
    sc = lin([[2, 112.0], [9, 100.0], [dur - 1, 103.0]], k) / 100.0
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    corners = [[(x0, y0 + L), (x0, y0), (x0 + L, y0)], [(x1 - L, y0), (x1, y0), (x1, y0 + L)],
               [(x0, y1 - L), (x0, y1), (x0 + L, y1)], [(x1 - L, y1), (x1, y1), (x1, y1 - L)]]
    out = []
    for c in corners:
        c = [(cx + (x - cx) * sc, cy + (y - cy) * sc) for x, y in c]
        out += [PolyEl(q, Solid((1, 1, 1)), o) for q in polyline_poly(c, 2.5)]
    return out


def tag_frame(spec, k):
    dur = spec["dur"]
    font = "Montserrat-Light"
    S = spec.get("size") or 64
    P = spec.get("pos") or [W / 2, H * 0.82]
    text = spec["text"]

    def tr(kk):
        return 350 + ease_keys([[0, 1150.0], [7, 0.0], [dur - 1, 60.0]], kk, {2: (80, 10)})

    o = lin([[0, 0.0], [3, 1.0], [dur - 4, 1.0], [dur - 1, 0.0]], k)
    gl, width = line_glyphs(text, font, S, Solid((1, 1, 1)), P[0], P[1], tracking=tr(k))
    _, w8 = line_layout(text, font, S, tr(8))
    groups = []
    bar_w = w8 * 1.25 + 120
    poly = rough_bar(P[0], P[1] + 2, bar_w, S * 1.05, wipe_progress(0, k), seed=3)
    if poly:
        groups.append(Group("bar", [PolyEl(poly, Solid((0, 0, 0)), fade_out(k, dur))], shadow=ae_shadow(50, 12, 11)))
    groups.append(Group("text", with_opacity(gl, o)))
    if spec.get("sub"):
        s2 = round(S * 0.45)
        so = lin([[4, 0.0], [8, 1.0], [dur - 4, 1.0], [dur - 1, 0.0]], k)
        sg, _ = line_glyphs(spec["sub"], "Orbitron-Bold", s2, Solid((1, 1, 1)), P[0], P[1] - S * 1.15, tracking=400,
                            shear=ITALIC)
        groups.append(Group("sub", with_opacity(sg, so), shadow=ae_shadow(95, 2, 10),
                            glows=(Glow((0, 0, 0), 4.0, 0.2),)))
    br = brackets(P[0], P[1], w8 * 1.25 + 180, S * 2.4, k, dur)
    if br:
        groups.append(Group("brackets", br))
    return Frame(groups)


# ---------------------------------------------------------------------------------------------------------------------
# 5. WATERMARK


def watermark_frame(spec=None, k=0):
    """build.jsx 214-225: SAU_EDITZ, 30 px white, tracking, drop shadow (opacity 70, distance 2, softness 4), centred on
    x = 960 with the BASELINE at y = 1050 (AE never re-anchored that text layer, so its position is the baseline).
    Full opacity: the scene stage keys the 62 % and the fades.

    AE had Bahnschrift SemiBold (a DIN-like, narrow, medium weight; measured on the AE render: cap height 21 px, ink
    width 208 px, stems ~3 px). Not on Linux, and Orbitron Bold is much wider and heavier, so this uses Montserrat Light
    emboldened by a 1.4 px outline, with the tracking set to land on the AE ink width."""
    spec = spec or {}
    font, size = spec.get("font", "Montserrat-Light"), spec.get("size", 30)
    x, y = spec.get("pos", (964.0, 1050.0))   # +4 px: measured, AE centres the ink at x = 961
    gl, _ = line_glyphs(spec.get("text", "SAU_EDITZ"), font, size, Solid((1, 1, 1)), x, y - cap_height(font, size) / 2,
                        tracking=spec.get("tracking", 180), stroke=((1, 1, 1), spec.get("embolden", 1.4)))
    return Frame([Group("text", gl, shadow=ae_shadow(70, 2, 4))])


STYLES = {"sub": sub_frame, "spring": spring_frame, "extended": extended_frame, "tag": tag_frame}


# ---------------------------------------------------------------------------------------------------------------------
# entry helpers shared by the style modules (render(spec, out_dir, opts) is what render.py dispatches to)


def unwrap(spec):
    """The title's spec dict, whether the caller passes the plan entry (`{style, f_in, spec}`) or the spec itself."""
    return spec["spec"] if isinstance(spec.get("spec"), dict) else spec


def frame_list(spec, opts=None, step=1):
    """The k values to render: `opts.frames` (an iterable of k, or "a:b[:s]") when given, else every `step`-th of 0..dur-1."""
    fr = getattr(opts, "frames", None)
    dur = spec.get("dur", 1)
    if isinstance(fr, str):      # "a:b:s,c,d:e" : ranges (b exclusive) and single frames, comma separated
        out = []
        for part in fr.split(","):
            p = [int(x) if x else None for x in part.split(":")]
            if len(p) == 1:
                out.append(p[0])
            else:
                a, b, st = (p + [None, None])[:3]
                out += range(a or 0, min(b if b is not None else dur, dur), st or 1)
        return [k for k in out if 0 <= k < dur]
    if fr is not None:
        return [k for k in fr if 0 <= k < dur]
    return list(range(0, dur, step))


def find_title(plan, title_id):
    """(style, spec dict) of a plan title id: `screen.<i>`, `<shot>.<i>`, or `watermark`."""
    if title_id == "watermark":
        return "watermark", {}
    name, _, i = title_id.rpartition(".")
    if name == "screen":
        t = plan["titles"][int(i)]
    else:
        shot = next(s for s in plan["shots"] if s["name"] == name)
        t = shot["titles"][int(i)]
    return t["style"], t["spec"]


def cli(argv=None):
    """`blender -b --factory-startup -P <style>.py -- --plan plan.json --title screen.0 --out DIR [--scale S] [--samples N]
    [--frames a:b:s]`: render one title standalone (what render.py does for the whole plan)."""
    import argparse
    import importlib
    import json
    import sys
    argv = list(sys.argv[sys.argv.index("--") + 1:]) if argv is None and "--" in sys.argv else (argv or [])
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--frames", default=None)
    a = ap.parse_args(argv)
    style, spec = find_title(json.loads(Path(a.plan).read_text()), a.title)
    opts = type("Opts", (), dict(scale=a.scale, samples=a.samples, frames=a.frames))()
    importlib.import_module(f"amv.titles.{style}").render(spec, Path(a.out), opts)
