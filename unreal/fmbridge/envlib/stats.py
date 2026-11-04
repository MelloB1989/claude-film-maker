"""Numbers from pixels, so Claude can check a look without seeing it: luminance statistics of a frame, colour cast,
clipping, contrast in stops, and checks against targets with hints on what to change.

Two kinds of input:
- scene-referred (`scene_stats`): linear HDR RGB in Unreal's scene units (cd/m2 with the 5.x default luminance range),
  e.g. a SceneCapture2D in SceneColorHDR read back raw. It meters the scene: the EV100 a camera would need.
- display-referred (`display_stats`): 0-1 values after exposure and tone mapping, e.g. a PNG still. It judges the
  image: how bright it reads, what clips, what is crushed.
`read_png` decodes an 8-bit PNG in pure Python (no numpy or PIL inside the editor).
"""
from __future__ import annotations

import math
import struct
import zlib

from . import photometry as ph


def _pct(sorted_vals, q: float) -> float:
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def _pixels(px):
    """Accepts [(r, g, b), ...], [(r, g, b, a), ...], or a flat [r, g, b, r, g, b, ...] with step 3."""
    if px and isinstance(px[0], (int, float)):
        return [px[i:i + 3] for i in range(0, len(px) - 2, 3)]
    return px


def scene_stats(px, exposure_ev100: float = None) -> dict:
    """Metering of linear scene pixels (cd/m2): mean, log-average (the scene key), median and percentiles of luminance,
    the EV100 a reflected meter would choose (log-average treated as middle grey), the dynamic range in stops between
    the 2nd and 98th percentiles, the average colour (normalised) and, with `exposure_ev100`, how far the scene sits
    from what that exposure expects (positive = the scene is brighter than the exposure: it will look over)."""
    px = _pixels(px)
    lum = sorted(max(0.0, ph.luma(p)) for p in px)
    n = len(lum)
    if not n:
        raise ValueError("scene_stats: no pixels")
    eps = 1e-6
    log_avg = math.exp(sum(math.log(x + eps) for x in lum) / n)
    mean = sum(lum) / n
    sr = sum(p[0] for p in px) / n
    sg = sum(p[1] for p in px) / n
    sb = sum(p[2] for p in px) / n
    m = max(sr, sg, sb, eps)
    p02, p98 = _pct(lum, 0.02), _pct(lum, 0.98)
    out = {
        "pixels": n, "mean": mean, "log_average": log_avg, "median": _pct(lum, 0.5), "p02": p02, "p98": p98,
        "max": lum[-1], "min": lum[0],
        "metered_ev100": round(ph.ev100_from_luminance(log_avg), 3),  # a reflected meter reading the whole frame
        "range_stops": round(math.log2((p98 + eps) / (p02 + eps)), 3),
        "average_rgb": [round(sr / m, 4), round(sg / m, 4), round(sb / m, 4)],
        "cast": _cast(sr, sg, sb),
    }
    if exposure_ev100 is not None:
        out["stops_over"] = round(out["metered_ev100"] - exposure_ev100, 3)
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in out.items()}


def _cast(r: float, g: float, b: float) -> dict:
    """A colour cast as warm/cool (b vs r) and green/magenta (g vs r,b) in log2 units (0 = neutral, 0.1 is visible)."""
    eps = 1e-6
    warm = math.log2((r + eps) / (b + eps))
    green = math.log2((g + eps) / (math.sqrt((r + eps) * (b + eps))))
    return {"warm": round(warm, 4), "green": round(green, 4), "magnitude": round(math.hypot(warm, green), 4)}


def display_stats(px, clip: float = 0.996, crush: float = 0.004, bins: int = 16) -> dict:
    """An image after tone mapping (0-1 per channel, sRGB-encoded as in a PNG): mean luma (display), median, the
    fraction of pixels clipped (any channel >= `clip`) and crushed (luma <= `crush`), a histogram of luma with `bins`
    bins, the colour cast of the linearised image, and the mean in linear terms."""
    px = _pixels(px)
    n = len(px)
    if not n:
        raise ValueError("display_stats: no pixels")
    lin = [[ph.srgb_to_linear(c) for c in p[:3]] for p in px]
    y = sorted(ph.linear_to_srgb(ph.luma(p)) for p in lin)
    clipped = sum(1 for p in px if max(p[:3]) >= clip) / n
    crushed = sum(1 for v in y if v <= crush) / n
    hist = [0] * bins
    for v in y:
        hist[min(bins - 1, int(v * bins))] += 1
    sr, sg, sb = (sum(p[i] for p in lin) / n for i in range(3))
    return {"pixels": n, "mean": round(sum(y) / n, 5), "median": round(_pct(y, 0.5), 5), "p05": round(_pct(y, 0.05), 5),
            "p95": round(_pct(y, 0.95), 5), "clipped": round(clipped, 6), "crushed": round(crushed, 6),
            "histogram": [round(h / n, 5) for h in hist], "linear_mean": round(ph.luma((sr, sg, sb)), 6),
            "cast": _cast(sr, sg, sb)}


# --------------------------------------------------------------------------------------------------- checks

DEFAULT_TARGETS = {
    # a well exposed, natural frame: mid-grey-ish mean, little clipping, little crush, no strong cast
    "mean": [0.28, 0.6], "clipped_max": 0.02, "crushed_max": 0.08, "cast_max": 0.25,
}


def check(stats: dict, targets: dict = None) -> list:
    """Compare stats (display_stats, scene_stats, or both merged as {"display": ..., "scene": ...}) with `targets`
    and return one result per target: {"check", "ok", "got", "want", "hint"}. Targets:
    mean [lo, hi] (display luma), median [lo, hi], clipped_max, crushed_max, cast_max (log2 units), warm [lo, hi],
    ev100 [lo, hi] (the metered scene), range_stops_max, stops_over [lo, hi]."""
    t = dict(DEFAULT_TARGETS if targets is None else targets)
    disp = stats.get("display", stats if "clipped" in stats else None)
    scene = stats.get("scene", stats if "metered_ev100" in stats else None)
    out = []

    def res(name, ok, got, want, hint=""):
        out.append({"check": name, "ok": bool(ok), "got": got, "want": want, "hint": "" if ok else hint})

    if disp:
        for key in ("mean", "median"):
            if key in t:
                lo, hi = t[key]
                v = disp[key]
                stops = math.log2(max(v, 1e-4) / (lo if v < lo else hi)) if not lo <= v <= hi else 0.0
                res(key, lo <= v <= hi, v, [lo, hi],
                    f"{'too dark' if v < lo else 'too bright'} by ~{abs(stops):.2f} stops (display): "
                    f"{'lower' if v < lo else 'raise'} env exposure ev100 by {abs(stops):.2f} "
                    f"or scale the lights by x{2 ** -stops:.2f}")
        if "clipped_max" in t:
            res("clipped", disp["clipped"] <= t["clipped_max"], disp["clipped"], f"<= {t['clipped_max']}",
                "highlights clip: lower the exposure, dim the brightest light/emissive, or raise film_white_clip")
        if "crushed_max" in t:
            res("crushed", disp["crushed"] <= t["crushed_max"], disp["crushed"], f"<= {t['crushed_max']}",
                "shadows crush to black: add fill (a lower rig ratio), raise the sky light, or lift color_offset")
        if "cast_max" in t:
            c = disp["cast"]
            res("cast", c["magnitude"] <= t["cast_max"], c, f"magnitude <= {t['cast_max']}",
                f"colour cast ({'warm' if c['warm'] > 0 else 'cool'} {abs(c['warm']):.2f}, "
                f"{'green' if c['green'] > 0 else 'magenta'} {abs(c['green']):.2f}): set grade white_balance "
                f"{'lower' if c['warm'] < 0 else 'higher'} than now, or the light temperatures")
        if "warm" in t:
            lo, hi = t["warm"]
            w = disp["cast"]["warm"]
            res("warm", lo <= w <= hi, w, [lo, hi], "warmer: lower light temperatures / raise white_balance"
                if w < lo else "cooler: raise light temperatures / lower white_balance")
    if scene:
        if "ev100" in t:
            lo, hi = t["ev100"]
            v = scene["metered_ev100"]
            res("ev100", lo <= v <= hi, v, [lo, hi], f"the scene meters EV100 {v:.2f}: "
                + ("brighten the lights/sun" if v < lo else "dim the lights/sun"))
        if "range_stops_max" in t:
            res("range_stops", scene["range_stops"] <= t["range_stops_max"], scene["range_stops"],
                f"<= {t['range_stops_max']}", "too much contrast for the frame: add fill or sky light, lower the key")
        if "stops_over" in t and "stops_over" in scene:
            lo, hi = t["stops_over"]
            v = scene["stops_over"]
            res("stops_over", lo <= v <= hi, v, [lo, hi], f"exposure is {v:+.2f} stops off the metered scene: "
                f"set env exposure ev100 to {scene['metered_ev100']:.2f}")
    return out


# --------------------------------------------------------------------------------------------------- PNG

def read_png(data: bytes, step: int = 1):
    """Decode an 8- or 16-bit, non-interlaced PNG (grey, grey+alpha, RGB, RGBA) to (width, height, pixels), pixels
    as [(r, g, b), ...] in 0-1, keeping every `step`-th pixel of every `step`-th row (a 4K still at step 4 is 0.5 M px)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, hdr = 8, [], None
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat.append(body)
        elif typ == b"IEND":
            break
        pos += 12 + ln
    w, h, depth, ctype, _, _, interlace = hdr
    if interlace or depth not in (8, 16) or ctype not in (0, 2, 4, 6):
        raise ValueError(f"unsupported PNG (depth {depth}, colour type {ctype}, interlace {interlace})")
    ch = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    bpp = ch * depth // 8
    stride = w * bpp
    raw = zlib.decompress(b"".join(idat))
    prev = bytearray(stride)
    out = []
    scale = 255.0 if depth == 8 else 65535.0
    i = 0
    for row in range(h):
        f = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                line[x] = (line[x] + (((line[x - bpp] if x >= bpp else 0) + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if row % step:
            continue
        for x in range(0, w, step):
            o = x * bpp
            if depth == 8:
                vals = line[o:o + ch]
            else:
                vals = [line[o + 2 * k] << 8 | line[o + 2 * k + 1] for k in range(ch)]
            if ch <= 2:
                out.append((vals[0] / scale,) * 3)
            else:
                out.append((vals[0] / scale, vals[1] / scale, vals[2] / scale))
    return w, h, out


def write_png(path: str, w: int, h: int, px) -> None:
    """Write [(r, g, b), ...] 0-1 as an 8-bit RGB PNG (for tests and small debug images)."""
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            rows.extend(int(round(max(0.0, min(1.0, c)) * 255)) for c in px[y * w + x][:3])

    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b""))
