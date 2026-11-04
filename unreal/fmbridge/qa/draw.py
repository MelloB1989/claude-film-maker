"""Drawing on an Image without PIL: filled and outlined rectangles (with alpha), lines, crosses, circles, and text in
a built-in 5x7 pixel font (upper case; lower case is drawn upper case), scaled by whole pixels. Enough to label a
contact sheet and mark what a check found."""
from __future__ import annotations

from . import image as _im
from .image import Image, _pad

COLORS = {  # named colours for overlays and statuses (display RGB)
    "ok": (60, 200, 90), "info": (80, 160, 255), "warn": (255, 190, 40), "fail": (240, 60, 50),
    "white": (255, 255, 255), "black": (0, 0, 0), "grey": (128, 128, 128), "guide": (255, 255, 255),
    "safe": (0, 220, 255), "title": (255, 220, 0), "subject": (255, 80, 200), "mask": (0, 0, 0),
}

_F = {  # 5x7 glyphs, one 5-bit row each (HD44780-style)
    " ": (0, 0, 0, 0, 0, 0, 0), "!": (4, 4, 4, 4, 0, 0, 4), '"': (10, 10, 10, 0, 0, 0, 0),
    "#": (10, 10, 31, 10, 31, 10, 10), "%": (24, 25, 2, 4, 8, 19, 3), "&": (12, 18, 20, 8, 21, 18, 13),
    "'": (12, 4, 8, 0, 0, 0, 0), "(": (2, 4, 8, 8, 8, 4, 2), ")": (8, 4, 2, 2, 2, 4, 8),
    "*": (0, 4, 21, 14, 21, 4, 0), "+": (0, 4, 4, 31, 4, 4, 0), ",": (0, 0, 0, 0, 12, 4, 8),
    "-": (0, 0, 0, 31, 0, 0, 0), ".": (0, 0, 0, 0, 0, 12, 12), "/": (0, 1, 2, 4, 8, 16, 0),
    "0": (14, 17, 19, 21, 25, 17, 14), "1": (4, 12, 4, 4, 4, 4, 14), "2": (14, 17, 1, 2, 4, 8, 31),
    "3": (31, 2, 4, 2, 1, 17, 14), "4": (2, 6, 10, 18, 31, 2, 2), "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (6, 8, 16, 30, 17, 17, 14), "7": (31, 1, 2, 4, 8, 8, 8), "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 2, 12), ":": (0, 12, 12, 0, 12, 12, 0), ";": (0, 12, 12, 0, 12, 4, 8),
    "<": (2, 4, 8, 16, 8, 4, 2), "=": (0, 0, 31, 0, 31, 0, 0), ">": (8, 4, 2, 1, 2, 4, 8),
    "?": (14, 17, 1, 2, 4, 0, 4), "@": (14, 17, 1, 13, 21, 21, 14), "A": (14, 17, 17, 17, 31, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30), "C": (14, 17, 16, 16, 16, 17, 14), "D": (28, 18, 17, 17, 17, 18, 28),
    "E": (31, 16, 16, 30, 16, 16, 31), "F": (31, 16, 16, 30, 16, 16, 16), "G": (14, 17, 16, 23, 17, 17, 15),
    "H": (17, 17, 17, 31, 17, 17, 17), "I": (14, 4, 4, 4, 4, 4, 14), "J": (7, 2, 2, 2, 2, 18, 12),
    "K": (17, 18, 20, 24, 20, 18, 17), "L": (16, 16, 16, 16, 16, 16, 31), "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 17, 25, 21, 19, 17, 17), "O": (14, 17, 17, 17, 17, 17, 14), "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13), "R": (30, 17, 17, 30, 20, 18, 17), "S": (15, 16, 16, 14, 1, 1, 30),
    "T": (31, 4, 4, 4, 4, 4, 4), "U": (17, 17, 17, 17, 17, 17, 14), "V": (17, 17, 17, 17, 17, 10, 4),
    "W": (17, 17, 17, 21, 21, 21, 10), "X": (17, 17, 10, 4, 10, 17, 17), "Y": (17, 17, 17, 10, 4, 4, 4),
    "Z": (31, 1, 2, 4, 8, 16, 31), "[": (14, 8, 8, 8, 8, 8, 14), "]": (14, 2, 2, 2, 2, 2, 14),
    "_": (0, 0, 0, 0, 0, 0, 31), "|": (4, 4, 4, 4, 4, 4, 4), "\\": (0, 16, 8, 4, 2, 1, 0),
    "^": (4, 10, 17, 0, 0, 0, 0), "~": (0, 0, 8, 21, 2, 0, 0), "$": (4, 15, 20, 14, 5, 30, 4),
}
GLYPH_W, GLYPH_H = 6, 8  # advance and line height in font pixels (5x7 plus a gap)


def _col(color, c: int) -> list:
    if isinstance(color, str):
        color = COLORS[color]
    return _pad(color, c)


def fill(img: Image, x0: int, y0: int, x1: int, y1: int, color, alpha: float = 1.0) -> None:
    """Fill [x0, x1) x [y0, y1) (clipped) with a colour, blended by alpha."""
    x0, x1 = max(0, int(x0)), min(img.w, int(x1))
    y0, y1 = max(0, int(y0)), min(img.h, int(y1))
    if x1 <= x0 or y1 <= y0:
        return
    col = _col(color, img.c)
    if alpha >= 1.0:
        row = bytes(col) * (x1 - x0)
        for y in range(y0, y1):
            i = (y * img.w + x0) * img.c
            img.data[i:i + len(row)] = row
        return
    NP = _im.NP
    if NP is not None:
        a = NP.frombuffer(img.data, NP.uint8).reshape(img.h, img.w, img.c)  # a writable view on the bytearray
        reg = a[y0:y1, x0:x1].astype(NP.float32)
        a[y0:y1, x0:x1] = NP.clip(NP.rint(reg * (1 - alpha) + NP.array(col, NP.float32) * alpha), 0, 255).astype(NP.uint8)
        return
    for y in range(y0, y1):
        for x in range(x0, x1):
            i = (y * img.w + x) * img.c
            for k in range(img.c):
                img.data[i + k] = round(img.data[i + k] * (1 - alpha) + col[k] * alpha)


def rect(img: Image, x0: int, y0: int, x1: int, y1: int, color, width: int = 2) -> None:
    """An outlined rectangle; the line is drawn inside [x0, x1) x [y0, y1)."""
    fill(img, x0, y0, x1, y0 + width, color)
    fill(img, x0, y1 - width, x1, y1, color)
    fill(img, x0, y0, x0 + width, y1, color)
    fill(img, x1 - width, y0, x1, y1, color)


def line(img: Image, x0: float, y0: float, x1: float, y1: float, color, width: int = 1, dash: int = 0) -> None:
    """A straight line (Bresenham, square pen of `width`); `dash` > 0 draws dash-length on/off segments."""
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    col = _col(color, img.c)
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err, n, r = dx + dy, 0, width // 2
    while True:
        if not dash or (n // dash) % 2 == 0:
            if width <= 1:
                img.put(x0, y0, col)
            else:
                fill(img, x0 - r, y0 - r, x0 - r + width, y0 - r + width, col)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
        n += 1


def cross(img: Image, x: float, y: float, size: int, color, width: int = 2) -> None:
    line(img, x - size, y, x + size, y, color, width)
    line(img, x, y - size, x, y + size, color, width)


def circle(img: Image, cx: float, cy: float, r: float, color, width: int = 2) -> None:
    """An outlined circle (midpoint algorithm)."""
    import math
    steps = max(16, int(2 * math.pi * r))
    pts = [(cx + r * math.cos(2 * math.pi * k / steps), cy + r * math.sin(2 * math.pi * k / steps)) for k in range(steps + 1)]
    for (a, b), (c, d) in zip(pts, pts[1:]):
        line(img, a, b, c, d, color, width)


def text_size(s: str, scale: int = 2) -> tuple:
    lines = str(s).split("\n")
    return max(len(t) for t in lines) * GLYPH_W * scale, len(lines) * GLYPH_H * scale


def text(img: Image, x: int, y: int, s: str, color="white", scale: int = 2, bg=None, pad: int = 2,
         bg_alpha: float = 0.7) -> tuple:
    """Draw text with its top-left at (x, y); `bg` puts a box behind it (alpha `bg_alpha`). Returns the box
    (x0, y0, x1, y1) it covered."""
    tw, th = text_size(s, scale)
    if bg is not None:
        fill(img, x - pad, y - pad, x + tw + pad, y + th + pad, bg, bg_alpha)
    col = _col(color, img.c)
    for li, t in enumerate(str(s).split("\n")):
        for ci, ch in enumerate(t):
            g = _F.get(ch.upper(), _F["?"])
            ox, oy = x + ci * GLYPH_W * scale, y + li * GLYPH_H * scale
            for ry, bits in enumerate(g):
                for rx in range(5):
                    if bits & (16 >> rx):
                        fill(img, ox + rx * scale, oy + ry * scale, ox + (rx + 1) * scale, oy + (ry + 1) * scale, col)
    return x - pad, y - pad, x + tw + pad, y + th + pad


def wrap(s: str, width_px: int, scale: int = 2) -> str:
    """Word-wrap text to a pixel width."""
    per = max(1, width_px // (GLYPH_W * scale))
    out = []
    for para in str(s).split("\n"):
        cur = ""
        for word in para.split(" "):
            while len(word) > per:
                if cur:
                    out.append(cur)
                    cur = ""
                out.append(word[:per])
                word = word[per:]
            if len(cur) + len(word) + (1 if cur else 0) > per:
                out.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}" if cur else word
        out.append(cur)
    return "\n".join(out)
