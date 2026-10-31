"""The studio's textures, drawn here rather than downloaded: the wall screen's code editor, the neon sign, the print on
the shelf, and walnut grain for the slats. Writes PNGs to out/host-studio/textures/.

    cd tools && uv run python ../films/host-studio/textures.py
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "host-studio" / "textures"
MONO = str(ROOT / "fonts" / "src" / "JetBrainsMono[wght].ttf")
SANS = str(ROOT / "fonts" / "src" / "Geist[wght].ttf")

CODE = '''import torch
from torch import nn


class Attention(nn.Module):
    """Scaled dot-product attention, one head at a time."""

    def __init__(self, dim: int, heads: int = 8):
        super().__init__()
        self.heads, self.scale = heads, (dim // heads) ** -0.5
        self.qkv = nn.Linear(dim, dim * 3, bias=False)
        self.out = nn.Linear(dim, dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, n, d = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        q, k, v = (t.view(b, n, self.heads, -1).transpose(1, 2) for t in (q, k, v))
        weights = (q @ k.transpose(-2, -1) * self.scale).softmax(dim=-1)
        y = (weights @ v).transpose(1, 2).reshape(b, n, d)
        return self.out(y)


# every token looks at every other token, and learns what to look for
layer = Attention(dim=512)
tokens = torch.randn(1, 128, 512)
print(layer(tokens).shape)  # torch.Size([1, 128, 512])
'''

THEME = {"bg": (13, 17, 23), "gutter": (88, 96, 105), "text": (201, 209, 217), "kw": (255, 123, 114),
         "str": (165, 214, 255), "com": (139, 148, 158), "fn": (210, 168, 255), "num": (121, 192, 255),
         "cls": (255, 166, 87), "bar": (22, 27, 34), "sel": (31, 111, 235)}
KEYWORDS = {"import", "from", "class", "def", "return", "for", "in", "self", "super", "False", "True", "None"}


def _token_colour(tok: str, prev: str) -> tuple:
    if tok in KEYWORDS:
        return THEME["kw"]
    if prev in ("def", "class"):
        return THEME["fn"] if prev == "def" else THEME["cls"]
    if tok[:1].isdigit():
        return THEME["num"]
    if tok[:1].isupper():
        return THEME["cls"]
    return THEME["text"]


def code_screen(w: int = 2560, h: int = 1440) -> Image.Image:
    im = Image.new("RGB", (w, h), THEME["bg"])
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(MONO, 34)
    ui = ImageFont.truetype(SANS, 26)
    d.rectangle([0, 0, w, 64], fill=THEME["bar"])
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([28 + i * 40, 20, 52 + i * 40, 44], fill=c)
    d.rectangle([180, 8, 520, 64], fill=THEME["bg"])
    d.text((206, 20), "attention.py", font=ui, fill=THEME["text"])
    d.text((560, 20), "train.py", font=ui, fill=THEME["gutter"])
    y, lh = 96, 50
    for n, line in enumerate(CODE.splitlines(), 1):
        if n == 19:  # the line being talked about
            d.rectangle([0, y - 6, w, y + lh - 10], fill=(25, 42, 66))
        d.text((24, y), f"{n:>3}", font=font, fill=THEME["gutter"])
        x = 140
        stripped = line.lstrip()
        if stripped.startswith("#"):
            d.text((x, y), line, font=font, fill=THEME["com"])
        elif stripped.startswith('"""'):
            d.text((x, y), line, font=font, fill=THEME["str"])
        else:
            prev, word = "", ""
            for ch in line + " ":
                if ch.isalnum() or ch == "_":
                    word += ch
                    continue
                if word:
                    col = _token_colour(word, prev)
                    d.text((x, y), word, font=font, fill=col)
                    x += d.textlength(word, font=font)
                    prev, word = word, ""
                if ch != " " or x > 140:
                    d.text((x, y), ch, font=font, fill=THEME["text"] if ch not in "()[]:,.=@*" else (139, 148, 158))
                x += d.textlength(ch, font=font)
        y += lh
    d.rectangle([140 + 18 * 20.4, y - lh + 4, 140 + 18 * 20.4 + 3, y - 10], fill=THEME["text"])  # the caret
    d.rectangle([0, h - 44, w, h], fill=THEME["sel"])
    d.text((24, h - 38), "main   Python 3.12   Ln 19, Col 42   UTF-8", font=ui, fill=(255, 255, 255))
    return im


def neon(w: int = 2048, h: int = 1024, text: str = "</>") -> Image.Image:
    """Glass tubes on black: a white-hot core in a saturated glow, as a lit tube photographs."""
    font = ImageFont.truetype(SANS, 760)
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    box = d.textbbox((0, 0), text, font=font, stroke_width=0)
    pos = ((w - (box[2] - box[0])) / 2 - box[0], (h - (box[3] - box[1])) / 2 - box[1])
    # a tube: the glyph's outline traced as a stroke, not its fill
    d.text(pos, text, font=font, fill=0, stroke_width=26, stroke_fill=255)
    tube = mask.filter(ImageFilter.GaussianBlur(2))
    hue = np.array([255, 46, 160], np.float32) / 255
    core = np.asarray(tube, np.float32)[..., None] / 255
    glow = np.asarray(tube.filter(ImageFilter.GaussianBlur(28)), np.float32)[..., None] / 255
    halo = np.asarray(tube.filter(ImageFilter.GaussianBlur(90)), np.float32)[..., None] / 255
    rgb = core * (0.55 + 0.45 * hue) + glow * hue * 1.6 + halo * hue * 0.9
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))


def poster(w: int = 1200, h: int = 1600, seed: int = 7) -> Image.Image:
    """A print for the shelf: concentric signal rings on warm paper, original geometry."""
    rnd = random.Random(seed)
    im = Image.new("RGB", (w, h), (232, 224, 208))
    d = ImageDraw.Draw(im)
    cx, cy = w * 0.5, h * 0.42
    cols = [(232, 93, 63), (24, 52, 74), (33, 150, 140), (240, 178, 64)]
    for i in range(14, 0, -1):
        r = i * 34
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=cols[i % 4], width=12 if i % 3 else 22)
    for _ in range(40):
        x = rnd.uniform(80, w - 80)
        d.line([x, h * 0.78, x, h * 0.78 + rnd.uniform(20, 160)], fill=cols[1], width=8)
    d.text((80, h - 150), "SIGNAL / NOISE", font=ImageFont.truetype(SANS, 72), fill=cols[1])
    return im


def walnut(w: int = 1024, h: int = 2048, seed: int = 11) -> Image.Image:
    """Quarter-sawn walnut: long wavy grain along the board (v), fine pores, a warm dark brown."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    warp = sum(np.sin(y / rng.uniform(150, 900) + rng.uniform(0, 6.3)) * rng.uniform(1, 5) for _ in range(5))
    rings = np.sin((x + warp) / rng.uniform(6, 9)) * 0.5 + 0.5
    rings = rings ** 3
    noise = rng.random((h // 8, w // 8)).astype(np.float32)
    noise = np.asarray(Image.fromarray((noise * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
    pores = (rng.random((h, w)) > 0.985).astype(np.float32)
    t = np.clip(0.55 * rings + 0.35 * noise - 0.25 * pores, 0, 1)[..., None]
    dark, light = np.array([38, 22, 14], np.float32), np.array([112, 70, 42], np.float32)
    return Image.fromarray((dark + (light - dark) * t).astype(np.uint8))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, im in (("T_CodeScreen", code_screen()), ("T_Neon", neon()), ("T_Poster", poster()), ("T_Walnut", walnut())):
        im.save(OUT / f"{name}.png")
        print(OUT / f"{name}.png", im.size)


if __name__ == "__main__":
    main()
