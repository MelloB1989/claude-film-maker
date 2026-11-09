"""Round 6 (agent-02): WHERE in a screen box the dark pixels are, and which layer is nearest there. Plain python3, no
editor, no deps; run ON THE BOX (the files hold face data; numbers only come out):

    python3 strip_cols.py /srv/ue/reel/r6/explain_her/strip_id29/CAM_MCU_0029 1040 600 1075 830

Reads <base>_depth.bin (qa.clip layers, w x h) and <base>_final.png (2w x 2h). The box is in FINAL pixels (1080p
when width_px=960). Per final-pixel column: the luma (mean, p10) of the final picture, and the share of pixels whose
NEAREST layer is each part (from the depth layers at the matching depth pixel), plus for pixels where the Top
(OVER) is nearest, the median depth gap to the next layer behind it (the stand-off, cm). A dark run of columns that
is OVER-nearest with a small stand-off = the garment's own edge/albedo; Face/Body-nearest dark columns next to the
edge = a contact shadow on the skin (the stand-off casts it)."""
import array
import json
import struct
import sys
import zlib

EMPTY = 1e9


def read_depth(path):
    with open(path, "rb") as fh:
        n = int.from_bytes(fh.read(4), "little")
        head = json.loads(fh.read(n))
        out = {}
        for name in head["layers"]:
            x = array.array("f")
            x.fromfile(fh, head["w"] * head["h"])
            out[name] = x
    return head["w"], head["h"], out


def read_png(path):
    """8-bit grey/RGB/RGBA, non-interlaced: (w, h, channels, rows of bytes)."""
    data = open(path, "rb").read()
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body)
            if depth != 8 or inter:
                raise SystemExit(f"png: depth {depth} interlace {inter} not handled")
            ch = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
        elif typ == b"IDAT":
            idat += body
        pos += 12 + ln
    raw, stride, rows, prev = zlib.decompress(idat), w * ch, [], bytearray(w * ch)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - ch] if i >= ch else 0
            b = prev[i]
            c = prev[i - ch] if i >= ch else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, ch, rows


base, x0, y0, x1, y1 = sys.argv[1], *map(int, sys.argv[2:6])
OVER = sys.argv[6] if len(sys.argv) > 6 else "Top"
dw, dh, L = read_depth(base + "_depth.bin")
fw, fh, ch, rows = read_png(base + "_final.png")
sx, sy = dw / fw, dh / fh
cols = []
for x in range(x0, x1 + 1):
    lum, near, gaps = [], {}, []
    for y in range(y0, y1 + 1):
        px = rows[y][x * ch:(x + 1) * ch]
        lum.append(px[0] if ch < 3 else 0.2126 * px[0] + 0.7152 * px[1] + 0.0722 * px[2])
        i = int(y * sy) * dw + int(x * sx)
        zs = sorted((L[k][i], k) for k in L if L[k][i] < EMPTY)
        k = zs[0][1] if zs else "-"
        near[k] = near.get(k, 0) + 1
        if k == OVER and len(zs) > 1:
            gaps.append(zs[1][0] - zs[0][0])
    lum.sort()
    gaps.sort()
    n = len(lum)
    cols.append({"x": x, "luma": round(sum(lum) / n), "luma_p10": round(lum[n // 10]),
                 "nearest": {k: round(v / n, 2) for k, v in sorted(near.items(), key=lambda kv: -kv[1])},
                 "standoff_cm": round(gaps[len(gaps) // 2], 2) if gaps else None})
print(json.dumps({"base": base.rsplit("/", 1)[-1], "box": [x0, y0, x1, y1], "over": OVER, "cols": cols}))
