"""A minimal PNG reader (numpy + zlib) for the mark's reference images: 8-bit RGB or RGBA, non-interlaced.

bpy-free, so the trace, the fit and the silhouette check read `mark.png` the same way in Blender's Python and under
the tools project's (neither has PIL).
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

_CHANNELS = {2: 3, 6: 4}  # colour type -> channels (RGB, RGBA)


def read_png(path: str | Path) -> np.ndarray:
    """(h, w, c) uint8, top row first: c = 3 (RGB) or 4 (RGBA)."""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    i, idat, hdr = 8, [], None
    while i < len(data):
        n, tag = struct.unpack(">I", data[i:i + 4])[0], data[i + 4:i + 8]
        body = data[i + 8:i + 8 + n]
        if tag == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
        i += 12 + n
    if hdr is None:
        raise ValueError(f"{path}: no IHDR")
    w, h, depth, ctype, _, _, interlace = hdr
    if depth != 8 or ctype not in _CHANNELS or interlace:
        raise ValueError(f"{path}: only 8-bit non-interlaced RGB/RGBA is read (depth {depth}, type {ctype})")
    c = _CHANNELS[ctype]
    raw = np.frombuffer(zlib.decompress(b"".join(idat)), np.uint8).reshape(h, 1 + w * c)
    out = np.zeros((h, w * c), np.uint8)
    prev = np.zeros(w * c, np.uint8)
    for y in range(h):
        f, row = raw[y, 0], raw[y, 1:].copy()
        if f == 1:  # sub: add the byte one pixel to the left, running along the row
            for x in range(c, w * c):
                row[x] = (int(row[x]) + int(row[x - c])) & 255
        elif f == 2:  # up
            row = (row.astype(np.uint16) + prev).astype(np.uint8)
        elif f == 3:  # average
            for x in range(w * c):
                left = int(row[x - c]) if x >= c else 0
                row[x] = (int(row[x]) + (left + int(prev[x])) // 2) & 255
        elif f == 4:  # paeth
            for x in range(w * c):
                a = int(row[x - c]) if x >= c else 0
                b = int(prev[x])
                cc = int(prev[x - c]) if x >= c else 0
                p = a + b - cc
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - cc)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else cc)
                row[x] = (int(row[x]) + pr) & 255
        elif f != 0:
            raise ValueError(f"{path}: bad filter {f} on row {y}")
        out[y] = row
        prev = row
    return out.reshape(h, w, c)
