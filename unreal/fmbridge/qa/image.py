"""Images without PIL: an 8-bit Image (grey, RGB or RGBA), PNG in and out with zlib, crop, resize, channel and colour
conversions. The editor's embedded Python has no numpy unless the PythonFoundationPackages plugin installed it, so
everything works on plain bytearrays; with numpy present the heavy loops use it (same results).

Analysis wants few pixels: read a still, `fit(img, 480)`, then measure. PNG decoding in pure Python costs about a
second per megapixel (the Paeth filter is a per-byte loop); PIL is used to decode when it is importable."""
from __future__ import annotations

import math
import os
import struct
import zlib

try:  # optional accelerators: the operator's side has numpy (and often PIL); the editor usually has neither
    import numpy as np
except ImportError:  # pragma: no cover - exercised by forcing NP = None in tests
    np = None

NP = np  # tests set image.NP = None to check the pure path gives the same answers

_SIG = b"\x89PNG\r\n\x1a\n"


class Image:
    """w x h pixels of c channels (1 grey, 3 RGB, 4 RGBA), 8 bits each, row-major in a bytearray. Values are
    display-referred (sRGB encoded), as a PNG or a screenshot holds them."""

    __slots__ = ("w", "h", "c", "data")

    def __init__(self, w: int, h: int, c: int = 3, data=None, fill=0):
        if c not in (1, 3, 4):
            raise ValueError(f"channels {c}: 1, 3 or 4")
        self.w, self.h, self.c = int(w), int(h), int(c)
        n = self.w * self.h * self.c
        if data is None:
            if isinstance(fill, (tuple, list)):
                data = bytearray(bytes(_pad(fill, c)) * (self.w * self.h))
            else:
                data = bytearray([int(fill)]) * n
        self.data = data if isinstance(data, bytearray) else bytearray(data)
        if len(self.data) != n:
            raise ValueError(f"{len(self.data)} bytes for {w}x{h}x{c} ({n} expected)")

    def __repr__(self):
        return f"Image({self.w}x{self.h}x{self.c})"

    @property
    def size(self) -> tuple:
        return self.w, self.h

    def copy(self) -> "Image":
        return Image(self.w, self.h, self.c, bytearray(self.data))

    def px(self, x: int, y: int) -> tuple:
        i = (y * self.w + x) * self.c
        return tuple(self.data[i:i + self.c])

    def put(self, x: int, y: int, color) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * self.c
            self.data[i:i + self.c] = bytes(_pad(color, self.c))

    def array(self):
        """A numpy view (h, w, c) uint8 (numpy required)."""
        return NP.frombuffer(bytes(self.data), dtype=NP.uint8).reshape(self.h, self.w, self.c)

    @classmethod
    def from_array(cls, a) -> "Image":
        a = NP.asarray(a)
        if a.ndim == 2:
            a = a[:, :, None]
        if a.dtype != NP.uint8:
            a = NP.clip(NP.floor(a + 0.5), 0, 255).astype(NP.uint8)  # round half up, as the pure path does
        return cls(a.shape[1], a.shape[0], a.shape[2], bytearray(NP.ascontiguousarray(a).tobytes()))


def _pad(color, c: int) -> list:
    """A colour as c channel values: grey from the RGB mean, alpha 255 unless given."""
    col = [int(v) for v in (color if isinstance(color, (tuple, list)) else (color,))]
    if c == 1:
        return [sum(col[:3]) // len(col[:3])]
    if len(col) == 1:
        col = col * 3
    if c == 3:
        return col[:3]
    return (col + [255])[:4]


# --- PNG ---------------------------------------------------------------------------------------------------------

def read(path: str) -> Image:
    """An image file as an Image: PNG always; JPEG/BMP/TGA/etc. only where PIL is installed (convert them otherwise).
    EXR is not read here: render a PNG (or JPEG) for QA."""
    ext = os.path.splitext(path)[1].lower()
    if not os.path.isfile(path):
        raise FileNotFoundError(f"no image at {path}")
    pil = _pil()
    if pil and ext != ".exr":
        with pil.open(path) as im:
            im.load()
            mode = im.mode
            if mode not in ("L", "RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in mode or "transparency" in im.info else "RGB")
            c = {"L": 1, "RGB": 3, "RGBA": 4}[im.mode]
            return Image(im.width, im.height, c, bytearray(im.tobytes()))
    if ext != ".png":
        raise ValueError(f"{path}: only PNG can be read without PIL (pip install pillow, or render PNG)")
    with open(path, "rb") as f:
        return decode_png(f.read())


def _pil():
    try:
        from PIL import Image as PILImage
        return PILImage
    except ImportError:
        return None


def decode_png(blob: bytes) -> Image:
    """PNG bytes -> Image. 8 or 16 bits (16 keeps the high byte), grey, grey+alpha, RGB, RGBA or palette; not
    interlaced (Unreal never writes interlaced PNGs). Grey+alpha comes back as RGBA."""
    if blob[:8] != _SIG:
        raise ValueError("not a PNG")
    pos, idat, plte, trns, hdr = 8, [], None, None, None
    while pos < len(blob):
        n, kind = struct.unpack(">I4s", blob[pos:pos + 8])
        body = blob[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if not hdr:
        raise ValueError("PNG without IHDR")
    w, h, depth, ctype, _, _, interlace = hdr
    if interlace:
        raise ValueError("interlaced PNG: not supported (re-save it non-interlaced)")
    if depth not in (8, 16) and ctype != 3:
        raise ValueError(f"PNG bit depth {depth}: only 8 and 16 are read")
    spp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = spp * (2 if depth == 16 else 1) if ctype != 3 else 1
    if ctype == 3 and depth != 8:
        raise ValueError(f"palette PNG with {depth}-bit indices: only 8-bit is read")
    raw = zlib.decompress(b"".join(idat))
    stride = w * bpp
    rows = _unfilter(raw, h, stride, bpp)
    if depth == 16:
        rows = rows[0::2]  # big-endian: the high byte of each sample
    if ctype == 3:
        pal = [tuple(plte[i:i + 3]) for i in range(0, len(plte), 3)]
        alpha = list(trns or b"")
        c = 4 if alpha else 3
        out = bytearray(w * h * c)
        for i, k in enumerate(rows):
            out[i * c:i * c + 3] = bytes(pal[k])
            if c == 4:
                out[i * c + 3] = alpha[k] if k < len(alpha) else 255
        return Image(w, h, c, out)
    if ctype == 4:  # grey + alpha -> RGBA
        out = bytearray(w * h * 4)
        out[0::4] = rows[0::2]
        out[1::4] = rows[0::2]
        out[2::4] = rows[0::2]
        out[3::4] = rows[1::2]
        return Image(w, h, 4, out)
    return Image(w, h, spp, rows)


def _unfilter(raw: bytes, h: int, stride: int, bpp: int) -> bytearray:
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        ft = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ft == 1:  # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:  # Up
            if NP is not None:
                line = bytearray(((NP.frombuffer(bytes(line), NP.uint8).astype(NP.uint16)
                                   + NP.frombuffer(bytes(prev), NP.uint8)) & 255).astype(NP.uint8).tobytes())
            else:
                for i in range(stride):
                    line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:  # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:  # Paeth
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        elif ft != 0:
            raise ValueError(f"PNG filter type {ft} on row {y}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def encode_png(img: Image, level: int = 6) -> bytes:
    """Image -> PNG bytes (filter None on every row: simple, and fast enough for annotated QA images)."""
    ctype = {1: 0, 3: 2, 4: 6}[img.c]
    stride = img.w * img.c
    raw = bytearray()
    d = img.data
    for y in range(img.h):
        raw.append(0)
        raw += d[y * stride:(y + 1) * stride]

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", img.w, img.h, 8, ctype, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), level)) + chunk(b"IEND", b""))


def write(img: Image, path: str) -> str:
    """Write a PNG (any other extension is written as PNG bytes all the same: name files .png)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(encode_png(img))
    return path


# --- geometry ----------------------------------------------------------------------------------------------------

def crop(img: Image, x0: int, y0: int, x1: int, y1: int) -> Image:
    """Pixels [x0, x1) x [y0, y1), clamped to the image."""
    x0, x1 = max(0, min(img.w, int(x0))), max(0, min(img.w, int(x1)))
    y0, y1 = max(0, min(img.h, int(y0))), max(0, min(img.h, int(y1)))
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"empty crop {x0},{y0}-{x1},{y1} of {img}")
    c, stride = img.c, img.w * img.c
    out = bytearray()
    for y in range(y0, y1):
        out += img.data[y * stride + x0 * c:y * stride + x1 * c]
    return Image(x1 - x0, y1 - y0, c, out)


def crop_frac(img: Image, box) -> Image:
    """A box given as fractions of the frame [x0, y0, x1, y1] (0..1, y down)."""
    x0, y0, x1, y1 = box
    return crop(img, round(x0 * img.w), round(y0 * img.h), max(round(x1 * img.w), round(x0 * img.w) + 1),
                max(round(y1 * img.h), round(y0 * img.h) + 1))


def resize(img: Image, w: int, h: int) -> Image:
    """Area-averaged when shrinking (no aliasing in the measurements), nearest when growing."""
    w, h = max(1, int(w)), max(1, int(h))
    if (w, h) == (img.w, img.h):
        return img.copy()
    if NP is not None:
        a = img.array().astype(NP.float32)
        ys = (NP.arange(h + 1) * img.h / h)
        xs = (NP.arange(w + 1) * img.w / w)
        if w <= img.w and h <= img.h:
            # integral image: the mean over each destination pixel's source rectangle (integer-snapped edges)
            yi, xi = NP.round(ys).astype(int), NP.round(xs).astype(int)
            yi[1:] = NP.maximum(yi[1:], yi[:-1] + 1)
            xi[1:] = NP.maximum(xi[1:], xi[:-1] + 1)
            yi, xi = NP.minimum(yi, img.h), NP.minimum(xi, img.w)
            s = NP.zeros((img.h + 1, img.w + 1, img.c), NP.float64)
            s[1:, 1:] = a.cumsum(0).cumsum(1)
            tot = s[yi[1:]][:, xi[1:]] - s[yi[:-1]][:, xi[1:]] - s[yi[1:]][:, xi[:-1]] + s[yi[:-1]][:, xi[:-1]]
            area = (yi[1:] - yi[:-1])[:, None, None] * (xi[1:] - xi[:-1])[None, :, None]
            return Image.from_array(tot / NP.maximum(area, 1))
        yy = NP.minimum((NP.arange(h) * img.h / h).astype(int), img.h - 1)
        xx = NP.minimum((NP.arange(w) * img.w / w).astype(int), img.w - 1)
        return Image.from_array(a[yy][:, xx])
    c, src, sw = img.c, img.data, img.w
    out = bytearray(w * h * c)
    shrink = w <= img.w and h <= img.h
    for y in range(h):
        if shrink:
            ya, yb = round(y * img.h / h), max(round((y + 1) * img.h / h), round(y * img.h / h) + 1)
            yb = min(yb, img.h)
        else:
            ya = min(int(y * img.h / h), img.h - 1)
            yb = ya + 1
        for x in range(w):
            if shrink:
                xa, xb = round(x * img.w / w), max(round((x + 1) * img.w / w), round(x * img.w / w) + 1)
                xb = min(xb, img.w)
            else:
                xa = min(int(x * img.w / w), img.w - 1)
                xb = xa + 1
            n = (yb - ya) * (xb - xa)
            o = (y * w + x) * c
            for k in range(c):
                t = 0
                for yy in range(ya, yb):
                    base = (yy * sw) * c + k
                    t += sum(src[base + xa * c:base + xb * c:c])
                out[o + k] = (t + n // 2) // n
    return Image(w, h, c, out)


def fit(img: Image, width: int) -> Image:
    """Shrink to `width` (keeping the aspect); an image already that narrow is returned as it is."""
    if img.w <= width:
        return img
    return resize(img, width, max(1, round(img.h * width / img.w)))


def rgb(img: Image) -> Image:
    """Three channels: grey is repeated, alpha dropped (composited over nothing: QA looks at colour, not matte)."""
    if img.c == 3:
        return img
    if NP is not None:
        a = img.array()
        return Image.from_array(NP.repeat(a, 3, axis=2) if img.c == 1 else a[:, :, :3])
    if img.c == 1:
        out = bytearray(img.w * img.h * 3)
        out[0::3] = img.data
        out[1::3] = img.data
        out[2::3] = img.data
        return Image(img.w, img.h, 3, out)
    out = bytearray(img.w * img.h * 3)
    out[0::3] = img.data[0::4]
    out[1::3] = img.data[1::4]
    out[2::3] = img.data[2::4]
    return Image(img.w, img.h, 3, out)


def paste(dst: Image, src: Image, x: int, y: int) -> None:
    """Copy src into dst with its top-left at (x, y), clipped; channels converted to dst's."""
    if src.c != dst.c:
        src = rgb(src) if dst.c == 3 else _to(src, dst.c)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst.w, x + src.w), min(dst.h, y + src.h)
    if x1 <= x0 or y1 <= y0:
        return
    c = dst.c
    for yy in range(y0, y1):
        sy = yy - y
        si = (sy * src.w + (x0 - x)) * c
        di = (yy * dst.w + x0) * c
        dst.data[di:di + (x1 - x0) * c] = src.data[si:si + (x1 - x0) * c]


def _to(img: Image, c: int) -> Image:
    if c == 3:
        return rgb(img)
    if c == 1:
        return Image(img.w, img.h, 1, luma8(img))
    r = rgb(img)
    out = bytearray(img.w * img.h * 4)
    out[0::4], out[1::4], out[2::4] = r.data[0::3], r.data[1::3], r.data[2::3]
    out[3::4] = b"\xff" * (img.w * img.h)
    return Image(img.w, img.h, 4, out)


# --- colour ------------------------------------------------------------------------------------------------------

def srgb_to_linear(v: float) -> float:
    """An sRGB-encoded value 0..1 to linear light 0..1."""
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def linear_to_srgb(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


LIN = [srgb_to_linear(i / 255) for i in range(256)]  # byte -> linear, for the pure path


def luma8(img: Image) -> bytearray:
    """Display luma per pixel, 0..255 (Rec. 709 weights on the encoded values: what a histogram shows)."""
    if img.c == 1:
        return bytearray(img.data)
    if NP is not None:
        a = img.array().astype(NP.float32)
        y = 0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]
        return bytearray(NP.clip(NP.rint(y), 0, 255).astype(NP.uint8).tobytes())
    d, c = img.data, img.c
    n = img.w * img.h
    out = bytearray(n)
    r, g, b = d[0::c], d[1::c], d[2::c]
    for i in range(n):
        out[i] = min(255, (2126 * r[i] + 7152 * g[i] + 722 * b[i] + 5000) // 10000)
    return out


def luminance(img: Image) -> list:
    """Relative luminance per pixel in linear light (0..1): what exposure is measured in. A list, or a numpy array
    (h*w,) when numpy is present."""
    if NP is not None:
        lut = NP.array(LIN, NP.float32)
        a = img.array()
        if img.c == 1:
            return lut[a[:, :, 0]].ravel()
        return (0.2126 * lut[a[:, :, 0]] + 0.7152 * lut[a[:, :, 1]] + 0.0722 * lut[a[:, :, 2]]).ravel()
    d, c = img.data, img.c
    if c == 1:
        return [LIN[v] for v in d]
    return [0.2126 * LIN[r] + 0.7152 * LIN[g] + 0.0722 * LIN[b] for r, g, b in zip(d[0::c], d[1::c], d[2::c])]


def hsv(r: float, g: float, b: float) -> tuple:
    """(hue degrees 0..360, saturation 0..1, value 0..1) of an RGB 0..1."""
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d <= 1e-9:
        h = 0.0
    elif mx == r:
        h = 60 * (((g - b) / d) % 6)
    elif mx == g:
        h = 60 * ((b - r) / d + 2)
    else:
        h = 60 * ((r - g) / d + 4)
    return h, (0.0 if mx <= 1e-9 else d / mx), mx


def hue_name(h: float, s: float, v: float) -> str:
    """A word for a colour, for messages ("the wall reads orange")."""
    if v < 0.12:
        return "black"
    if s < 0.12:
        return "white" if v > 0.85 else "grey"
    names = [(15, "red"), (45, "orange"), (70, "yellow"), (160, "green"), (200, "cyan"), (255, "blue"),
             (290, "purple"), (335, "magenta"), (361, "red")]
    for lim, n in names:
        if h < lim:
            return n
    return "red"


def solid(w: int, h: int, color, c: int = 3) -> Image:
    return Image(w, h, c, fill=tuple(color) if isinstance(color, (tuple, list)) else color)


def gradient(w: int, h: int) -> Image:
    """A test card: hue across, value down (tests and selftests use it as a known image)."""
    img = Image(w, h, 3)
    for y in range(h):
        for x in range(w):
            hh = 360.0 * x / max(1, w - 1)
            v = 1.0 - y / max(1, h - 1)
            k = lambda n: (n + hh / 60) % 6  # noqa: E731
            f = lambda n: v - v * max(0, min(k(n), 4 - k(n), 1))  # noqa: E731
            img.put(x, y, (round(255 * f(5)), round(255 * f(3)), round(255 * f(1))))
    return img


def mean_rgb(img: Image) -> tuple:
    """Mean display RGB 0..255."""
    if NP is not None:
        a = rgb(img).array().reshape(-1, 3).astype(NP.float64)
        return tuple(float(x) for x in a.mean(0))
    r = rgb(img).data
    n = max(1, img.w * img.h)
    return (sum(r[0::3]) / n, sum(r[1::3]) / n, sum(r[2::3]) / n)


def is_close(a: float, b: float, tol: float = 1e-6) -> bool:
    return math.isclose(a, b, abs_tol=tol)
