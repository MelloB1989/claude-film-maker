"""A tiny PNG reader/writer and canvas (stdlib only: zlib, struct), so contact sheets and frame overlays are made in
the editor's Python and in tests without Pillow.

    img = read("still.png")                  # Image: width, height, rgb bytearray
    img.line(0, y, img.w - 1, y, (255, 255, 0))
    img.text(8, 8, "S2 MCU 50MM", (255, 255, 255), scale=2)
    sheet = contact_sheet([img, ...], cols=4, cell_w=480, labels=[...])
    write("sheet.png", sheet)

Reads 8-bit greyscale, RGB, RGBA, grey+alpha and palette images, non-interlaced (what the engine writes); 16-bit
is reduced to 8.
"""
from __future__ import annotations

import struct
import zlib


class Image:
    def __init__(self, w: int, h: int, fill=(0, 0, 0)):
        self.w, self.h = int(w), int(h)
        self.px = bytearray(bytes(fill) * (self.w * self.h))

    def get(self, x: int, y: int) -> tuple:
        i = (y * self.w + x) * 3
        return self.px[i], self.px[i + 1], self.px[i + 2]

    def set(self, x: int, y: int, c) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(c[:3])

    def blend(self, x: int, y: int, c, a: float) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            for k in range(3):
                self.px[i + k] = int(self.px[i + k] * (1 - a) + c[k] * a)

    def rect(self, x0: int, y0: int, x1: int, y1: int, c, fill: bool = False, alpha: float = 1.0) -> None:
        x0, x1 = sorted((int(x0), int(x1)))
        y0, y1 = sorted((int(y0), int(y1)))
        if fill:
            for y in range(max(0, y0), min(self.h, y1 + 1)):
                for x in range(max(0, x0), min(self.w, x1 + 1)):
                    self.blend(x, y, c, alpha) if alpha < 1 else self.set(x, y, c)
            return
        self.line(x0, y0, x1, y0, c, alpha)
        self.line(x0, y1, x1, y1, c, alpha)
        self.line(x0, y0, x0, y1, c, alpha)
        self.line(x1, y0, x1, y1, c, alpha)

    def line(self, x0, y0, x1, y1, c, alpha: float = 1.0, dash: int = 0) -> None:
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err, n = dx + dy, 0
        while True:
            if not dash or (n // dash) % 2 == 0:
                self.blend(x0, y0, c, alpha) if alpha < 1 else self.set(x0, y0, c)
            n += 1
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def cross(self, x, y, c, r: int = 6) -> None:
        self.line(x - r, y, x + r, y, c)
        self.line(x, y - r, x, y + r, c)

    def paste(self, src: "Image", x0: int, y0: int) -> None:
        for y in range(src.h):
            ty = y0 + y
            if not 0 <= ty < self.h:
                continue
            xa, xb = max(0, x0), min(self.w, x0 + src.w)
            if xb <= xa:
                continue
            s = (y * src.w + (xa - x0)) * 3
            d = (ty * self.w + xa) * 3
            self.px[d:d + (xb - xa) * 3] = src.px[s:s + (xb - xa) * 3]

    def scaled(self, w: int, h: int | None = None) -> "Image":
        """A box-filtered resize (good for shrinking stills into a sheet)."""
        h = h or max(1, round(self.h * w / self.w))
        out = Image(w, h)
        fx, fy = self.w / w, self.h / h
        for y in range(h):
            ya, yb = int(y * fy), max(int(y * fy) + 1, int((y + 1) * fy))
            for x in range(w):
                xa, xb = int(x * fx), max(int(x * fx) + 1, int((x + 1) * fx))
                r = g = b = n = 0
                step = max(1, (xb - xa) // 4)  # sample a 4x4 grid at most: fast enough in pure Python
                for yy in range(ya, min(yb, self.h), max(1, (yb - ya) // 4)):
                    row = yy * self.w
                    for xx in range(xa, min(xb, self.w), step):
                        i = (row + xx) * 3
                        r += self.px[i]
                        g += self.px[i + 1]
                        b += self.px[i + 2]
                        n += 1
                i = (y * w + x) * 3
                out.px[i:i + 3] = bytes((r // n, g // n, b // n)) if n else b"\0\0\0"
        return out

    def text(self, x: int, y: int, s: str, c=(255, 255, 255), scale: int = 1, bg=None) -> int:
        """Draw text in a 5x7 pixel font (A-Z 0-9 and a little punctuation; lower case drawn as upper); returns the
        width drawn."""
        s = str(s).upper()
        if bg is not None:
            self.rect(x - scale, y - scale, x + len(s) * 6 * scale, y + 8 * scale, bg, fill=True, alpha=0.6)
        cx = x
        for ch in s:
            g = FONT.get(ch, FONT["?"])
            for row, bits in enumerate(g):
                for col in range(5):
                    if bits >> (4 - col) & 1:
                        for dy in range(scale):
                            for dx in range(scale):
                                self.set(cx + col * scale + dx, y + row * scale + dy, c)
            cx += 6 * scale
        return cx - x


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def read(path: str) -> Image:
    with open(path, "rb") as f:
        return decode(f.read())


def decode(data: bytes) -> Image:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, plte = 8, [], None
    w = h = depth = ctype = interlace = None
    while pos < len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat.append(body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"IEND":
            break
    if interlace:
        raise ValueError("interlaced PNGs are not supported")
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, chans * depth // 8)
    stride = (w * chans * depth + 7) // 8
    raw = zlib.decompress(b"".join(idat))
    prev = bytearray(stride)
    img = Image(w, h)
    i = 0
    for y in range(h):
        ft = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if ft == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif ft == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif ft == 3:
            for x in range(stride):
                line[x] = (line[x] + ((line[x - bpp] if x >= bpp else 0) + prev[x]) // 2) & 255
        elif ft == 4:
            for x in range(stride):
                line[x] = (line[x] + _paeth(line[x - bpp] if x >= bpp else 0, prev[x],
                                            prev[x - bpp] if x >= bpp else 0)) & 255
        prev = line
        o = y * w * 3
        if depth == 16:
            line = line[0::2]
        elif depth < 8:
            if ctype != 3 and ctype != 0:
                raise ValueError(f"bit depth {depth} with colour type {ctype} is not supported")
            bits = []
            for byte in line:
                for k in range(8 // depth):
                    bits.append(byte >> (8 - depth * (k + 1)) & ((1 << depth) - 1))
            line = bytearray(bits[:w]) if ctype == 3 else bytearray(v * 255 // ((1 << depth) - 1) for v in bits[:w])
        if ctype == 2:
            img.px[o:o + w * 3] = line[:w * 3]
        elif ctype == 6:
            px = img.px
            for x in range(w):
                px[o + 3 * x:o + 3 * x + 3] = line[4 * x:4 * x + 3]
        elif ctype == 0:
            for x in range(w):
                img.px[o + 3 * x:o + 3 * x + 3] = bytes((line[x],) * 3)
        elif ctype == 4:
            for x in range(w):
                img.px[o + 3 * x:o + 3 * x + 3] = bytes((line[2 * x],) * 3)
        elif ctype == 3:
            for x in range(w):
                k = line[x] * 3
                img.px[o + 3 * x:o + 3 * x + 3] = plte[k:k + 3]
    return img


def encode(img: Image) -> bytes:
    raw = bytearray()
    row = img.w * 3
    for y in range(img.h):
        raw.append(0)
        raw += img.px[y * row:(y + 1) * row]

    def chunk(t: bytes, b: bytes) -> bytes:
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", img.w, img.h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def write(path: str, img: Image) -> dict:
    import os
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(encode(img))
    return {"path": path, "width": img.w, "height": img.h}


# --- overlays and sheets ------------------------------------------------------------------------------------------

YELLOW, CYAN, RED, WHITE, GREEN = (255, 220, 0), (0, 220, 255), (255, 60, 60), (255, 255, 255), (80, 255, 120)


def guides(img: Image, thirds: bool = True, safe: bool = True, center: bool = True) -> Image:
    """Draw the thirds, the action-safe (93%) and title-safe (90%) frames and the centre on an image, in place."""
    w, h = img.w, img.h
    if thirds:
        for k in (1, 2):
            img.line(w * k / 3, 0, w * k / 3, h - 1, WHITE, 0.5, dash=6)
            img.line(0, h * k / 3, w - 1, h * k / 3, WHITE, 0.5, dash=6)
    if safe:
        for frac, c in ((0.93, CYAN), (0.90, YELLOW)):
            mx, my = w * (1 - frac) / 2, h * (1 - frac) / 2
            img.rect(mx, my, w - 1 - mx, h - 1 - my, c, alpha=0.6)
    if center:
        img.cross(w // 2, h // 2, WHITE, r=max(4, w // 80))
    return img


def marks(img: Image, points: dict, color=GREEN) -> Image:
    """Mark named points given as [u, v] (0..1 of the frame): what the solver predicted, drawn on what the engine
    rendered, so a mismatch shows."""
    for name, uv in points.items():
        if uv is None or uv[0] is None:
            continue
        x, y = uv[0] * (img.w - 1), uv[1] * (img.h - 1)
        img.cross(int(x), int(y), color, r=max(3, img.w // 120))
        img.text(int(x) + 5, int(y) + 3, name, color, scale=1)
    return img


def contact_sheet(images: list, cols: int = 4, cell_w: int = 480, labels=None, title: str = "",
                  pad: int = 6, bg=(24, 24, 24)) -> Image:
    """Images in a grid of `cols`, each scaled to `cell_w` wide, with a label under each and a title on top."""
    if not images:
        raise ValueError("contact_sheet needs at least one image")
    scaled = [im.scaled(cell_w) if im.w != cell_w else im for im in images]
    ch = max(s.h for s in scaled)
    lab_h = 14 if labels else 0
    top = 22 if title else 0
    rows = (len(scaled) + cols - 1) // cols
    sheet = Image(cols * (cell_w + pad) + pad, top + rows * (ch + lab_h + pad) + pad, bg)
    if title:
        sheet.text(pad, 6, title, WHITE, scale=2)
    for k, s in enumerate(scaled):
        r, c = divmod(k, cols)
        x, y = pad + c * (cell_w + pad), top + pad + r * (ch + lab_h + pad)
        sheet.paste(s, x, y)
        if labels:
            sheet.text(x, y + ch + 3, str(labels[k])[: cell_w // 6], WHITE)
    return sheet


# 5x7 glyphs, one int per row, bit 4 = leftmost column
FONT = {
    " ": (0, 0, 0, 0, 0, 0, 0), "?": (14, 17, 1, 2, 4, 0, 4), "!": (4, 4, 4, 4, 4, 0, 4),
    ".": (0, 0, 0, 0, 0, 12, 12), ",": (0, 0, 0, 0, 12, 4, 8), ":": (0, 12, 12, 0, 12, 12, 0),
    "-": (0, 0, 0, 31, 0, 0, 0), "_": (0, 0, 0, 0, 0, 0, 31), "+": (0, 4, 4, 31, 4, 4, 0),
    "/": (1, 1, 2, 4, 8, 16, 16), "(": (2, 4, 8, 8, 8, 4, 2), ")": (8, 4, 2, 2, 2, 4, 8),
    "%": (24, 25, 2, 4, 8, 19, 3), "=": (0, 0, 31, 0, 31, 0, 0), "#": (10, 10, 31, 10, 31, 10, 10),
    "'": (4, 4, 8, 0, 0, 0, 0), "[": (14, 8, 8, 8, 8, 8, 14), "]": (14, 2, 2, 2, 2, 2, 14),
    ">": (8, 4, 2, 1, 2, 4, 8), "<": (2, 4, 8, 16, 8, 4, 2), "*": (0, 4, 21, 14, 21, 4, 0),
    "0": (14, 17, 19, 21, 25, 17, 14), "1": (4, 12, 4, 4, 4, 4, 14), "2": (14, 17, 1, 2, 4, 8, 31),
    "3": (31, 2, 4, 2, 1, 17, 14), "4": (2, 6, 10, 18, 31, 2, 2), "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (6, 8, 16, 30, 17, 17, 14), "7": (31, 1, 2, 4, 8, 8, 8), "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 2, 12),
    "A": (14, 17, 17, 31, 17, 17, 17), "B": (30, 17, 17, 30, 17, 17, 30), "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (28, 18, 17, 17, 17, 18, 28), "E": (31, 16, 16, 30, 16, 16, 31), "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 15), "H": (17, 17, 17, 31, 17, 17, 17), "I": (14, 4, 4, 4, 4, 4, 14),
    "J": (7, 2, 2, 2, 2, 18, 12), "K": (17, 18, 20, 24, 20, 18, 17), "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17), "N": (17, 17, 25, 21, 19, 17, 17), "O": (14, 17, 17, 17, 17, 17, 14),
    "P": (30, 17, 17, 30, 16, 16, 16), "Q": (14, 17, 17, 17, 21, 18, 13), "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30), "T": (31, 4, 4, 4, 4, 4, 4), "U": (17, 17, 17, 17, 17, 17, 14),
    "V": (17, 17, 17, 17, 17, 10, 4), "W": (17, 17, 17, 21, 21, 21, 10), "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4), "Z": (31, 1, 2, 4, 8, 16, 31),
}
