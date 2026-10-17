"""Glyph advances and cap height read straight from a TrueType/OpenType file (pure Python, no fontTools, no bpy).

Why: After Effects' *tracking* is an additive per-character advance (1/1000 em), but Blender's text object only has a
multiplicative `space_character`. To track the Novax hero open (-26 -> +48) exactly, each letter is its own text object
and is placed at the advances computed here. Only what is needed is parsed: head (unitsPerEm), hhea + hmtx (advances),
cmap formats 4 and 12 (char -> glyph), OS/2 (cap height). Kerning is ignored (AE applies pair kerning; for the
all-caps titles of this edit the difference is a few px and is noted in the style docs).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FontMetrics:
    units_per_em: int
    advances: dict          # char -> advance in font units
    default_advance: int
    cap_height: int         # font units (OS/2 sCapHeight; falls back to 0.7 em)

    def advance(self, ch: str) -> float:
        """Advance of `ch` in em (1.0 = the font size)."""
        return self.advances.get(ch, self.default_advance) / self.units_per_em

    @property
    def cap(self) -> float:
        """Cap height in em."""
        return self.cap_height / self.units_per_em

    def text_advances(self, text: str, tracking: float = 0.0) -> list:
        """Per-letter advance in em with AE tracking (1/1000 em) added to every letter."""
        return [self.advance(c) + tracking / 1000.0 for c in text]


def _tables(data: bytes) -> dict:
    off = 0
    if data[:4] == b"ttcf":
        off = struct.unpack(">I", data[12:16])[0]
    n = struct.unpack(">H", data[off + 4:off + 6])[0]
    out = {}
    for i in range(n):
        tag, _, o, ln = struct.unpack(">4sIII", data[off + 12 + 16 * i:off + 28 + 16 * i])
        out[tag.decode("latin1")] = (o, ln)
    return out


def _cmap(data: bytes, t: dict) -> dict:
    """char code -> glyph id from the best Unicode subtable (format 12, else 4)."""
    base, _ = t["cmap"]
    n = struct.unpack(">H", data[base + 2:base + 4])[0]
    subs = []
    for i in range(n):
        pid, eid, o = struct.unpack(">HHI", data[base + 4 + 8 * i:base + 12 + 8 * i])
        if pid == 0 or (pid == 3 and eid in (1, 10)):
            subs.append((struct.unpack(">H", data[base + o:base + o + 2])[0], base + o))
    subs.sort(key=lambda s: 0 if s[0] == 12 else 1)
    for fmt, p in subs:
        m = {}
        if fmt == 12:
            ng = struct.unpack(">I", data[p + 12:p + 16])[0]
            for g in range(ng):
                s, e, gid = struct.unpack(">III", data[p + 16 + 12 * g:p + 28 + 12 * g])
                for c in range(s, min(e, s + 0x3000) + 1):
                    m[c] = gid + (c - s)
            return m
        if fmt == 4:
            segx2 = struct.unpack(">H", data[p + 6:p + 8])[0]
            seg = segx2 // 2
            ends = struct.unpack(f">{seg}H", data[p + 14:p + 14 + segx2])
            q = p + 16 + segx2
            starts = struct.unpack(f">{seg}H", data[q:q + segx2])
            q += segx2
            deltas = struct.unpack(f">{seg}h", data[q:q + segx2])
            q += segx2
            ro_pos = q
            ros = struct.unpack(f">{seg}H", data[q:q + segx2])
            for i in range(seg):
                for c in range(starts[i], ends[i] + 1):
                    if c == 0xFFFF:
                        continue
                    if ros[i] == 0:
                        g = (c + deltas[i]) & 0xFFFF
                    else:
                        gp = ro_pos + 2 * i + ros[i] + 2 * (c - starts[i])
                        g = struct.unpack(">H", data[gp:gp + 2])[0]
                        if g:
                            g = (g + deltas[i]) & 0xFFFF
                    if g:
                        m[c] = g
            return m
    return {}


def read_metrics(path) -> FontMetrics:
    data = Path(path).read_bytes()
    t = _tables(data)
    upm = struct.unpack(">H", data[t["head"][0] + 18:t["head"][0] + 20])[0]
    nh = struct.unpack(">H", data[t["hhea"][0] + 34:t["hhea"][0] + 36])[0]
    hm = t["hmtx"][0]
    adv = [struct.unpack(">H", data[hm + 4 * i:hm + 4 * i + 2])[0] for i in range(nh)]
    cmap = _cmap(data, t)
    advances = {chr(c): adv[min(g, nh - 1)] for c, g in cmap.items() if g < 0xFFFF}
    cap = 0
    if "OS/2" in t:
        o, ln = t["OS/2"]
        ver = struct.unpack(">H", data[o:o + 2])[0]
        if ver >= 2 and ln >= 90:
            cap = struct.unpack(">h", data[o + 88:o + 90])[0]
    if cap <= 0:   # fall back on the glyph box of "H" is not available without outlines: 0.7 em is the usual cap
        cap = int(0.7 * upm)
    return FontMetrics(upm, advances, advances.get(" ", adv[0]), cap)
