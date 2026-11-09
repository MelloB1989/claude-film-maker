"""The karma studio's label textures: everything in the room that carries words or a picture, drawn exactly.

The props give each of these faces its own material slot with UVs 0..1 over the face (see props/), so every image
here is drawn at the face's real proportions, upright as seen from the front. Alongside an albedo, a face that is not
flat paint gets `_M` (R roughness, G metallic) and `_N` (DirectX normal) maps. Writes PNGs to
out/host-studio/textures/, where build.py picks them up.

    cd tools && uv run python ../films/host-studio/labels.py
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "out" / "host-studio" / "textures"
FONTS = ROOT / "fonts" / "src"
SANS = str(FONTS / "Geist[wght].ttf")
MONO = str(FONTS / "JetBrainsMono[wght].ttf")
GROTESK = str(FONTS / "BricolageGrotesque[opsz,wdth,wght].ttf")
HAND = "/System/Library/Fonts/Noteworthy.ttc"  # index 1 is the bold cut

# The seven product books, left to right on the shelf
SPINES = ["Socify", "Noobsverse", "Lyzn", "Avidia", "Respawn", "Noobspaces", "Noobs Learning"]
ARTISTS = ["SEEDHE MAUT", "KR$NA", "RAFTAAR", "KARMA", "BELLA"]


# --------------------------------------------------------------------------------------------- helpers

def font(path: str, size: int, wght: int | None = None, index: int = 0, **axes) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(path, size, index=index)
    if wght is not None or axes:
        names = {a["name"].decode() if isinstance(a["name"], bytes) else a["name"]: a for a in f.get_variation_axes()}
        vals = []
        for name, a in names.items():
            want = {"Weight": wght}.get(name, axes.get(name.lower()[:4]))
            vals.append(a["default"] if want is None else max(a["minimum"], min(a["maximum"], want)))
        f.set_variation_by_axes(vals)
    return f


def noise(w: int, h: int, scale: float, seed: int, octaves: int = 4) -> np.ndarray:
    """Smooth periodic fractal noise in 0..1, `scale` px per feature at the first octave."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        s = max(scale / 2 ** o, 1.0)
        gw, gh = max(int(w / s), 2), max(int(h / s), 2)
        g = Image.fromarray((rng.random((gh, gw)) * 255).astype(np.uint8))
        out += np.asarray(g.resize((w, h), Image.BICUBIC), np.float32) / 255 * amp
        total += amp
        amp *= 0.5
    out /= total
    return (out - out.min()) / max(np.ptp(out), 1e-6)


def grain(w: int, h: int, seed: int, amount: float = 0.04) -> np.ndarray:
    return 1.0 + (np.random.default_rng(seed).random((h, w), np.float32) - 0.5) * 2 * amount


def to_img(a: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def normal_from_height(h: np.ndarray, strength: float) -> Image.Image:
    """A DirectX (green-down) tangent-space normal map from a height field in 0..1."""
    dy, dx = np.gradient(h.astype(np.float32))
    n = np.dstack([-dx * strength, -dy * strength, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return to_img((n * 0.5 + 0.5) * 255)


def mask_map(rough: np.ndarray, metal: np.ndarray) -> Image.Image:
    return to_img(np.dstack([rough * 255, metal * 255, np.zeros_like(rough)]))


def paper(w: int, h: int, rgb, seed: int, fibre: float = 0.035) -> np.ndarray:
    base = np.array(rgb, np.float32)
    n = noise(w, h, max(w, h) / 6, seed, 5) - 0.5
    f = noise(w, h, 6, seed + 1, 2) - 0.5
    shade = 1 + n * 0.05 + f * fibre
    return base[None, None, :] * shade[..., None] * grain(w, h, seed + 2, 0.015)[..., None]


def text_layer(size, text, fnt, xy, anchor="la", spacing=0) -> np.ndarray:
    """A 0..1 coverage mask of `text`; `spacing` adds tracking in px between letters."""
    im = Image.new("L", size, 0)
    d = ImageDraw.Draw(im)
    if not spacing:
        d.text(xy, text, font=fnt, fill=255, anchor=anchor)
    else:
        widths = [d.textlength(c, font=fnt) for c in text]
        total = sum(widths) + spacing * (len(text) - 1)
        x = xy[0] - (total / 2 if anchor[0] == "m" else 0)
        for c, cw in zip(text, widths):
            d.text((x, xy[1]), c, font=fnt, fill=255, anchor="l" + anchor[1])
            x += cw + spacing
    return np.asarray(im, np.float32) / 255


def ink(base: np.ndarray, cover: np.ndarray, rgb, seed: int, breakup: float = 0.0) -> np.ndarray:
    """Print `cover` onto `base` in `rgb`; `breakup` eats into the ink like worn foil or a dry pen."""
    if breakup:
        cover = cover * np.clip((noise(cover.shape[1], cover.shape[0], 3, seed, 2) - breakup) * 4, 0, 1)
    c = cover[..., None]
    return base * (1 - c) + np.array(rgb, np.float32)[None, None, :] * c


def save(im: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / f"{name}.png")
    print(OUT / f"{name}.png", im.size)


# --------------------------------------------------------------------------------------------- the labels

def spines(px_cm: int = 100) -> None:
    """Dark green book cloth with the title in gold foil, reading bottom to top, and gold rules at head and tail."""
    w, h = int(3.6 * px_cm), int(24.0 * px_cm)
    probe = font(SANS, 200, 560)
    longest = max(probe.getbbox(t)[2] - probe.getbbox(t)[0] for t in SPINES)
    size = int(200 * min(15.5 * px_cm / longest, 1.25 * px_cm / (probe.getbbox("H")[3] - probe.getbbox("H")[1])))
    f = font(SANS, size, 560)
    for i, title in enumerate(SPINES, 1):
        seed = 100 + i
        weave = (np.sin(np.arange(w)[None, :] * math.pi / 2.2) * np.sin(np.arange(h)[:, None] * math.pi / 2.2))
        cloth = paper(w, h, (33, 60, 46), seed, fibre=0.07) * (1 + weave[..., None] * 0.035)
        edge = np.minimum(np.arange(w), np.arange(w)[::-1])[None, :] / (0.35 * px_cm)
        cloth *= (1 + 0.12 * np.exp(-edge) * noise(w, h, 40, seed + 9))[..., None]  # rubbed spine hinges
        # the title, laid out along the spine, then turned to read bottom to top
        line = Image.new("L", (h, w), 0)
        d = ImageDraw.Draw(line)
        d.text((h / 2, w / 2 + size * 0.06), title, font=f, fill=255, anchor="mm")
        foil = np.asarray(line.rotate(90, expand=True), np.float32) / 255
        rules = np.zeros((h, w), np.float32)
        for top in (1.6, h / px_cm - 1.6 - 0.25):
            for off in (0.0, 0.17):
                y0 = int((top + off) * px_cm)
                rules[y0:y0 + max(int(0.06 * px_cm), 2), int(0.35 * px_cm):w - int(0.35 * px_cm)] = 1
        cover = np.clip(foil + rules, 0, 1)
        cover = cover * np.clip((noise(w, h, 2.5, seed + 3, 2) - 0.06) * 6, 0, 1)  # foil breakup
        gold = np.array((214, 178, 104), np.float32) * (0.85 + 0.3 * noise(w, h, 30, seed + 4))[..., None]
        alb = cloth * (1 - cover[..., None]) + gold * cover[..., None]
        save(to_img(alb), f"T_Label_Spine{i}")
        save(mask_map(0.86 - 0.58 * cover, cover * 0.95), f"T_Label_Spine{i}_M")
        height = 0.5 + 0.15 * weave * 0.5 - 0.35 * np.asarray(Image.fromarray((cover * 255).astype(np.uint8))
                                                             .filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
        save(normal_from_height(height, 2.5), f"T_Label_Spine{i}_N")


def sleeve(n: int = 2048) -> None:
    """The crate's front LP sleeve: a plain typographic list of artists on worn cream board."""
    alb = paper(n, n, (236, 228, 209), 21, fibre=0.05)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) / n
    r = np.hypot(xx - 0.5, yy - 0.5)
    ring = np.exp(-((r - 0.455) / 0.012) ** 2) * noise(n, n, 60, 22)  # the record's ring wear
    edge = np.minimum(np.minimum(xx, 1 - xx), np.minimum(yy, 1 - yy))
    alb *= (1 - 0.05 * ring[..., None])
    alb = alb + (np.exp(-edge / 0.006) * noise(n, n, 12, 23) * 40)[..., None]  # scuffed edges
    # the crate's front board hides the sleeve's lower ~40% (props/record_crate.py): the list lives in the top 58%
    f = font(GROTESK, int(n * 0.074), 720, wdth=88, opsz=60)
    cover = np.zeros((n, n), np.float32)
    for k, name in enumerate(ARTISTS):
        cover = np.maximum(cover, text_layer((n, n), name, f, (n * 0.08, n * (0.075 + k * 0.1)), "lt"))
    alb = ink(alb, cover * 0.96, (24, 23, 22), 24, breakup=0.04)
    save(to_img(alb), "T_Label_SleeveFront")


def calendar(px_cm: int = 100) -> None:
    w, h = int(10 * px_cm), int(12 * px_cm)
    alb = paper(w, h, (247, 246, 241), 31, fibre=0.02)
    # the wire's holes are cut in the card itself (props/desk_calendar.py): none drawn here
    day = text_layer((w, h), "27", font(SANS, int(5.6 * px_cm), 640), (w / 2, h * 0.47), "mm")
    month = text_layer((w, h), "NOV", font(SANS, int(1.55 * px_cm), 560), (w / 2, h * 0.80), "mm",
                       spacing=int(0.22 * px_cm))
    alb = ink(alb, day, (20, 20, 22), 32)
    alb = ink(alb, month, (20, 20, 22), 33)
    save(to_img(alb), "T_Label_Calendar")


def _stroke(d: ImageDraw.ImageDraw, pts, width: float, fill) -> None:
    """A felt-tip stroke through `pts`: overlapping dabs whose size breathes a little."""
    rnd = random.Random(len(pts))
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        steps = max(int(math.hypot(x1 - x0, y1 - y0) / 1.5), 1)
        for s in range(steps):
            t = s / steps
            r = width / 2 * (0.9 + 0.2 * rnd.random())
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def _bezier(p0, p1, p2, p3, n=40):
    return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * e
                  for a, b, c, e in zip(p0, p1, p2, p3)) for t in (i / n for i in range(n + 1))]


def polaroid(px_cm: int = 200) -> None:
    """The instant print: the lake at dusk, and on its chin a handwritten "V" and a small red heart."""
    w, h = int(8.8 * px_cm), int(10.7 * px_cm)
    alb = paper(w, h, (243, 241, 234), 41, fibre=0.03)
    x0, y0, side = int(0.45 * px_cm), int(0.55 * px_cm), int(7.9 * px_cm)
    photo = Image.open(HERE / "labels" / "polaroid_photo.jpg").convert("RGB").resize((side, side), Image.LANCZOS)
    p = np.asarray(photo, np.float32) / 255
    p = 0.06 + p * 0.9  # lifted blacks
    p = p * np.array([1.04, 0.99, 0.93])  # warm, faded
    yy, xx = np.mgrid[0:side, 0:side].astype(np.float32) / side
    p *= (1 - 0.28 * (np.hypot(xx - 0.5, yy - 0.5) / 0.7) ** 2)[..., None]  # the lens falls off
    p = p * grain(side, side, 42, 0.035)[..., None]
    alb[y0:y0 + side, x0:x0 + side] = np.clip(p, 0, 1) * 255
    alb[y0 - 2:y0, x0:x0 + side] *= 0.9  # the print's inner edge
    alb[y0:y0 + side, x0 - 2:x0] *= 0.9
    # the handwriting on the chin, in felt tip
    pen = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(pen)
    cx, cy, s = 2.75 * px_cm, 9.5 * px_cm, 0.95 * px_cm  # big enough to read across the room
    _stroke(d, _bezier((cx - s * 0.62, cy - s * 0.7), (cx - s * 0.42, cy - s * 0.1), (cx - s * 0.18, cy + s * 0.45),
                       (cx - s * 0.02, cy + s * 0.62)), 0.13 * px_cm, 255)
    _stroke(d, _bezier((cx - s * 0.02, cy + s * 0.62), (cx + s * 0.18, cy + s * 0.15), (cx + s * 0.4, cy - s * 0.45),
                       (cx + s * 0.66, cy - s * 0.78)), 0.125 * px_cm, 255)
    black = np.asarray(pen.filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255
    heart = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(heart)
    hx, hy, hs = cx + 1.5 * s * 1.5, cy + 0.04 * px_cm, 0.56 * px_cm
    outline = (_bezier((hx, hy + hs * 0.95), (hx - hs * 1.25, hy + hs * 0.1), (hx - hs * 1.05, hy - hs * 0.95),
                       (hx - hs * 0.05, hy - hs * 0.4))
               + _bezier((hx - hs * 0.05, hy - hs * 0.4), (hx + hs * 0.95, hy - hs * 1.0), (hx + hs * 1.3, hy + hs * 0.05),
                         (hx, hy + hs * 0.95)))
    d.polygon(outline, fill=255)
    _stroke(d, outline, 0.045 * px_cm, 255)
    red = np.asarray(heart.filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255
    alb = ink(alb, black * 0.92, (28, 28, 34), 43, breakup=0.03)
    alb = ink(alb, red * 0.95, (196, 32, 44), 44, breakup=0.012)
    save(to_img(alb), "T_Label_Polaroid")


def sticky(n: int = 1216) -> None:
    alb = paper(n, n, (251, 226, 98), 51, fibre=0.03)
    alb[: int(n * 0.2)] *= np.array([0.985, 0.97, 0.9])  # the adhesive band is a touch deeper
    f = font(HAND, int(n * 0.2), index=1)
    cover = np.maximum(text_layer((n, n), "hello,", f, (n * 0.17, n * 0.42), "ls"),
                       text_layer((n, n), "friend.", f, (n * 0.24, n * 0.72), "ls"))
    cover = np.asarray(Image.fromarray((cover * 255).astype(np.uint8)).rotate(4, Image.BICUBIC, center=(n / 2, n / 2)),
                       np.float32) / 255
    alb = ink(alb, cover * 0.93, (26, 26, 30), 52, breakup=0.02)
    save(to_img(alb), "T_Label_Sticky")


def terminal(px_cm: int = 100) -> None:
    """The little display's screen: a root prompt and a block cursor, green on black."""
    w, h = int(21 * px_cm), int(4.5 * px_cm)
    alb = np.full((h, w, 3), 4.0, np.float32)
    f = font(MONO, int(1.5 * px_cm), 520)
    prompt = "root@mellob:~# "
    cover = text_layer((w, h), prompt, f, (0.9 * px_cm, h / 2), "lm")
    x1 = 0.9 * px_cm + ImageDraw.Draw(Image.new("L", (1, 1))).textlength(prompt, font=f)
    bb = f.getbbox("M", anchor="lm")
    cover[int(h / 2 + bb[1]):int(h / 2 + bb[3]), int(x1):int(x1 + (bb[2] - bb[0]))] = 1.0  # the cursor
    glow = np.asarray(Image.fromarray((cover * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)), np.float32) / 255
    green = np.array((96, 255, 128), np.float32)
    alb = alb + green[None, None, :] * (cover * 0.95 + glow * 0.25)[..., None]
    rows = (np.arange(h) % 3 == 0)[:, None, None]  # the LCD's faint row structure
    alb = np.where(rows, alb * 0.82, alb)
    save(to_img(alb), "T_Label_Terminal")


def lyzn(n: int = 1024) -> None:
    """The engraving in the acrylic block: a frosted "lyzn" (white, alpha = where the surface was cut)."""
    cover = text_layer((n, n), "lyzn", font(SANS, int(n * 0.3), 430), (n / 2, n * 0.5), "mm")
    cover = cover * (0.75 + 0.25 * noise(n, n, 4, 61, 2))
    rgba = np.dstack([np.full((n, n), 246.0), np.full((n, n), 247.0), np.full((n, n), 250.0), cover * 255])
    save(Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA"), "T_Label_Lyzn")


def walnut_face(w: int, h: int, seed: int) -> np.ndarray:
    """Walnut for a small face: a crop of the studio's walnut texture (surfaces/), else a drawn stand-in."""
    src = HERE / "surfaces" / "T_Walnut_A.png"
    if src.exists():
        im = Image.open(src).convert("RGB")
        cw = int(im.width * 0.12)  # the texture covers 100 cm: the 12 cm face
        return np.asarray(im.crop((im.width // 3, im.height // 3, im.width // 3 + cw, im.height // 3 + int(cw * h / w)))
                          .resize((w, h), Image.LANCZOS), np.float32)
    y = np.arange(h, dtype=np.float32)[:, None]
    warp = noise(w, h, w / 3, seed, 3) * 40 + noise(w, h, 40, seed + 1, 2) * 6
    rings = 0.5 + 0.5 * np.sin((y + warp) / h * 2 * math.pi * 7)
    base = np.array((92, 58, 38), np.float32)
    hi = np.array((142, 96, 62), np.float32)
    t = (rings ** 3 * 0.55 + noise(w, h, w / 2, seed + 2, 3) * 0.45)[..., None]
    pores = (np.random.default_rng(seed).random((h, w)) < 0.004)[..., None]
    return (base * (1 - t) + hi * t) * np.where(pores, 0.7, 1.0) * grain(w, h, seed + 3, 0.03)[..., None]


def nameplate(px_cm: int = 100) -> None:
    """The walnut desk block with "MelloB" cut into it: the cuts show paler, rougher wood."""
    w, h = int(12 * px_cm), int(4.2 * px_cm)
    alb = walnut_face(w, h, 71)
    cover = text_layer((w, h), "MelloB", font(SANS, int(2.3 * px_cm), 600), (w / 2, h / 2 + 0.05 * px_cm), "mm")
    cut = np.array((205, 172, 132), np.float32)
    shade = np.asarray(Image.fromarray((cover * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3)), np.float32) / 255
    alb = alb * (1 - cover[..., None]) + cut * (0.8 + 0.2 * shade)[..., None] * cover[..., None]
    save(to_img(alb), "T_Label_Name")
    save(mask_map(0.42 + 0.4 * cover, np.zeros_like(cover)), "T_Label_Name_M")
    height = 1 - np.asarray(Image.fromarray((cover * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5)),
                            np.float32) / 255 * 0.6
    save(normal_from_height(height, 6.0), "T_Label_Name_N")


def print_art(px_cm: int = 100) -> None:
    """The framed print beside the root prompt: an original Mr. Robot-inspired picture (a hooded hacker at a glowing
    terminal under a red sun; generated, no stills, logos or likeness from the show), cropped to the 13 x 18 window."""
    w, h = int(13 * px_cm), int(18 * px_cm)
    im = Image.open(HERE / "labels" / "mrrobot_print.jpg").convert("RGB")
    ch = int(im.width * h / w)
    im = im.crop((0, (im.height - ch) // 2, im.width, (im.height - ch) // 2 + ch)) if ch <= im.height else im
    save(im.resize((w, h), Image.LANCZOS), "T_Label_Print")


def abstract_print(px_cm: int = 100) -> None:
    """A small abstract print: an arch, a sun and a line, in the room's palette (the first print, unused)."""
    w, h = int(13 * px_cm), int(18 * px_cm)
    alb = paper(w, h, (241, 236, 225), 81, fibre=0.03)
    layer = Image.new("L", (w, h), 0)
    shapes = []
    for rgb, draw in (((191, 112, 80), lambda d: (d.rectangle((0.16 * w, 0.52 * h, 0.62 * w, 0.88 * h), fill=255),
                                                   d.ellipse((0.16 * w, 0.36 * h, 0.62 * w, 0.68 * h), fill=255))),
                      ((154, 168, 140), lambda d: d.ellipse((0.5 * w, 0.14 * h, 0.84 * w, 0.38 * h), fill=255)),
                      ((214, 168, 92), lambda d: d.ellipse((0.68 * w, 0.66 * h, 0.76 * w, 0.72 * h), fill=255))):
        im = layer.copy()
        draw(ImageDraw.Draw(im))
        shapes.append((rgb, np.asarray(im, np.float32) / 255))
    for k, (rgb, cover) in enumerate(shapes):
        alb = ink(alb, cover * 0.94, rgb, 82 + k, breakup=0.05)  # risograph grain
    arc = Image.new("L", (w, h), 0)
    ImageDraw.Draw(arc).arc((0.08 * w, 0.1 * h, 0.95 * w, 0.95 * h), 200, 330, fill=255, width=int(0.07 * px_cm))
    alb = ink(alb, np.asarray(arc, np.float32) / 255, (44, 42, 40), 89)
    save(to_img(alb), "T_Label_Print")


def record_label(n: int = 1024) -> None:
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) / n
    r = np.hypot(xx - 0.5, yy - 0.5) * 2  # 1.0 at the label's edge
    alb = paper(n, n, (122, 36, 38), 91, fibre=0.03)
    for rr in (0.62, 0.66, 0.9):
        alb *= (1 - 0.25 * np.exp(-((r - rr) / 0.006) ** 2))[..., None]
    alb[r < 0.075] = (12, 12, 12)
    alb[r > 1.0] = (10, 10, 10)
    save(to_img(alb), "T_Label_Record")


def outside() -> None:
    """The garden through the window, behind the sheers (soft, out-of-focus photos): by day and at night."""
    for src, name in (("outside.jpg", "T_Outside"), ("outside_night.jpg", "T_OutsideNight")):
        save(Image.open(HERE / "labels" / src).convert("RGB").resize((1024, 2048), Image.LANCZOS), name)


def watch_face(n: int = 512) -> None:
    """Her smartwatch's screen: the time, white on black, with a thin activity ring."""
    im = Image.new("RGB", (n, n), (2, 2, 3))
    d = ImageDraw.Draw(im)
    d.arc((n * 0.12, n * 0.12, n * 0.88, n * 0.88), 140, 400, fill=(60, 200, 120), width=int(n * 0.022))
    d.text((n / 2, n * 0.5), "10:09", font=font(SANS, int(n * 0.24), 420), fill=(240, 240, 240), anchor="mm")
    d.text((n / 2, n * 0.7), "SUN 1", font=font(SANS, int(n * 0.07), 500), fill=(150, 150, 150), anchor="mm")
    save(im, "T_Label_WatchFace")


def main() -> None:
    spines()
    sleeve()
    calendar()
    polaroid()
    sticky()
    terminal()
    lyzn()
    nameplate()
    print_art()
    record_label()
    outside()
    watch_face()


if __name__ == "__main__":
    main()
