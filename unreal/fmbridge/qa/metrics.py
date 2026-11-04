"""Numbers about a frame: histogram, exposure (clipping, percentiles, stops from mid grey), colour per region
(mean, saturation, hue, cast), sharpness, flat-frame detection. `analyze` runs them all and turns what is off into
issues. Measure at analysis size (fit the frame to ~480 px first): the answers barely change and it is fast.

Regions are named cells of a 3x3 grid ("top-left" .. "bottom-right", "center"), "full", or boxes as fractions of
the frame [x0, y0, x1, y1] (a subject's screen box from framing.project)."""
from __future__ import annotations

import math

from . import image as _im
from .image import Image, crop_frac, hsv, hue_name, luma8, luminance, rgb
from .issues import issue

GRID3 = {f"{v}-{u}" if (u, v) != ("center", "center") else "center": [i / 3, j / 3, (i + 1) / 3, (j + 1) / 3]
         for j, v in enumerate(("top", "center", "bottom")) for i, u in enumerate(("left", "center", "right"))}
REGIONS = {"full": [0, 0, 1, 1], **GRID3}

# thresholds a review uses; every one can be overridden per call (`limits=`)
LIMITS = {
    "clip_high_pct": 2.0,     # % of pixels at (or within 2 of) 255 in luma: highlights blown
    "clip_low_pct": 5.0,      # % at or below 2: shadows crushed
    "stops_low": -2.5,        # mean luminance this many stops under 18% grey: underexposed
    "stops_high": 1.5,        # ... over: overexposed
    "flat_std": 2.0,          # luma standard deviation below this: a flat frame (black, white, one colour)
    "cast": 0.12,             # a neutral-weighted channel imbalance over this: a colour cast
    "soft_ratio": 0.25,       # a subject's detail (Laplacian variance) under this fraction of the frame's: soft
}


def histogram(img: Image, channel: str = "luma", bins: int = 256) -> list:
    """Counts per value (0..255 folded into `bins`), for "luma", "r", "g" or "b"."""
    if channel == "luma":
        vals = luma8(img)
    else:
        r = rgb(img)
        vals = r.data["rgb".index(channel)::3]
    if _im.NP is not None:
        h = _im.NP.bincount(_im.NP.frombuffer(bytes(vals), _im.NP.uint8), minlength=256)
        counts = [int(x) for x in h]
    else:
        counts = [0] * 256
        for v in vals:
            counts[v] += 1
    if bins == 256:
        return counts
    per = 256 / bins
    out = [0] * bins
    for v, n in enumerate(counts):
        out[min(bins - 1, int(v / per))] += n
    return out


def _percentile(counts: list, total: int, q: float) -> int:
    want, run = q / 100 * total, 0
    for v, n in enumerate(counts):
        run += n
        if run >= want and n:
            return v
    return 255


def exposure(img: Image, limits: dict | None = None) -> dict:
    """Exposure in numbers: luma mean/median/percentiles (0..255, display), clipped highlights and crushed shadows
    (% of pixels), mean scene luminance (linear), `stops` = log2(mean luminance / 0.18) (0 = averages to mid grey;
    a dark mood sits at -1..-2), contrast (luma std), and a verdict: ok | under | over | flat | clipped."""
    L = {**LIMITS, **(limits or {})}
    counts = histogram(img)
    total = max(1, sum(counts))
    mean = sum(v * n for v, n in enumerate(counts)) / total
    var = sum(n * (v - mean) ** 2 for v, n in enumerate(counts)) / total
    lum = luminance(img)
    if _im.NP is not None:
        mean_lin = float(lum.mean()) if len(lum) else 0.0
    else:
        mean_lin = sum(lum) / max(1, len(lum))
    hi = 100 * sum(counts[253:]) / total
    lo = 100 * sum(counts[:3]) / total
    stops = math.log2(max(mean_lin, 1e-6) / 0.18)
    std = math.sqrt(var)
    if std < L["flat_std"]:
        verdict = "flat"
    elif hi > L["clip_high_pct"] * 4 and stops > 0:
        verdict = "over"
    elif stops < L["stops_low"]:
        verdict = "under"
    elif stops > L["stops_high"]:
        verdict = "over"
    elif hi > L["clip_high_pct"] or lo > L["clip_low_pct"]:
        verdict = "clipped"
    else:
        verdict = "ok"
    return {"mean": round(mean, 2), "median": _percentile(counts, total, 50), "std": round(std, 2),
            "p1": _percentile(counts, total, 1), "p5": _percentile(counts, total, 5),
            "p95": _percentile(counts, total, 95), "p99": _percentile(counts, total, 99),
            "clipped_high_pct": round(hi, 3), "clipped_low_pct": round(lo, 3), "mean_luminance": round(mean_lin, 5),
            "stops": round(stops, 2), "verdict": verdict}


def color(img: Image) -> dict:
    """Colour of an image (or a region of one): mean display RGB (0..255), mean saturation and value, the
    saturation-weighted mean hue (degrees) and its name, and the cast: how far the mean of the near-neutral pixels
    leans from grey, per channel (-1..1; {"r": 0.15} = 15% red cast), with the dominant direction named."""
    r = rgb(img)
    n = max(1, r.w * r.h)
    NP = _im.NP
    if NP is not None:
        a = r.array().reshape(-1, 3).astype(NP.float64) / 255
        mean = a.mean(0)
        mx, mn = a.max(1), a.min(1)
        sat = NP.where(mx > 1e-6, (mx - mn) / NP.maximum(mx, 1e-6), 0)
        # hue per pixel (vectorised hsv)
        d = NP.maximum(mx - mn, 1e-9)
        R, G, B = a[:, 0], a[:, 1], a[:, 2]
        hue = NP.where(mx == R, 60 * (((G - B) / d) % 6), NP.where(mx == G, 60 * ((B - R) / d + 2), 60 * ((R - G) / d + 4)))
        wgt = sat * mx
        sx, sy = float((wgt * NP.cos(NP.radians(hue))).sum()), float((wgt * NP.sin(NP.radians(hue))).sum())
        neutral = sat < 0.25
        nm = a[neutral].mean(0) if neutral.any() else mean
        sat_mean, val_mean = float(sat.mean()), float(mx.mean())
        mean = [float(x) for x in mean]
        nm = [float(x) for x in nm]
    else:
        d3 = r.data
        sr = sg = sb = ss = sv = sx = sy = 0.0
        nr = ng = nb = 0.0
        nn = 0
        for i in range(0, len(d3), 3):
            R, G, B = d3[i] / 255, d3[i + 1] / 255, d3[i + 2] / 255
            h, s, v = hsv(R, G, B)
            sr += R
            sg += G
            sb += B
            ss += s
            sv += v
            sx += s * v * math.cos(math.radians(h))
            sy += s * v * math.sin(math.radians(h))
            if s < 0.25:
                nr += R
                ng += G
                nb += B
                nn += 1
        mean = [sr / n, sg / n, sb / n]
        nm = [nr / nn, ng / nn, nb / nn] if nn else mean
        sat_mean, val_mean = ss / n, sv / n
    hue = (math.degrees(math.atan2(sy, sx)) + 360) % 360
    hue_strength = math.hypot(sx, sy) / n
    g = sum(nm) / 3
    cast = {k: round((nm[i] - g) / max(g, 1e-3), 3) for i, k in enumerate("rgb")}
    lean = max(cast, key=lambda k: abs(cast[k]))
    word = {("r", 1): "red/warm", ("r", -1): "cyan", ("g", 1): "green", ("g", -1): "magenta",
            ("b", 1): "blue/cool", ("b", -1): "yellow/warm"}[(lean, 1 if cast[lean] >= 0 else -1)]
    return {"mean_rgb": [round(255 * x, 1) for x in mean], "saturation": round(sat_mean, 3), "value": round(val_mean, 3),
            "hue": round(hue, 1), "hue_strength": round(hue_strength, 3),
            "name": hue_name(hue, sat_mean, val_mean), "cast": cast, "cast_toward": word,
            "cast_amount": round(abs(cast[lean]), 3)}


def sharpness(img: Image) -> float:
    """Variance of the Laplacian of the luma (8-bit units): high = crisp detail, low = soft or out of focus. Only
    comparable between crops of similar content and size (use it to compare a subject against the background, or a
    frame against its reference)."""
    w, h = img.w, img.h
    if w < 3 or h < 3:
        return 0.0
    y = luma8(img)
    NP = _im.NP
    if NP is not None:
        a = NP.frombuffer(bytes(y), NP.uint8).reshape(h, w).astype(NP.float32)
        lap = a[1:-1, :-2] + a[1:-1, 2:] + a[:-2, 1:-1] + a[2:, 1:-1] - 4 * a[1:-1, 1:-1]
        return round(float(lap.var()), 3)
    vals = []
    for yy in range(1, h - 1):
        for xx in range(1, w - 1):
            i = yy * w + xx
            vals.append(y[i - 1] + y[i + 1] + y[i - w] + y[i + w] - 4 * y[i])
    m = sum(vals) / len(vals)
    return round(sum((v - m) ** 2 for v in vals) / len(vals), 3)


def region_box(region) -> list:
    if isinstance(region, str):
        if region not in REGIONS:
            raise ValueError(f"region {region!r}: one of {sorted(REGIONS)} or a box [x0, y0, x1, y1] (0..1)")
        return REGIONS[region]
    box = [float(v) for v in region]
    if len(box) != 4 or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise ValueError(f"box {region}: [x0, y0, x1, y1] fractions of the frame with x0 < x1, y0 < y1")
    return box


def regions(img: Image, which=None) -> dict:
    """Exposure, colour and sharpness per region: `which` is a list of names/boxes, or a dict name -> box; None
    gives the 3x3 grid."""
    if which is None:
        which = GRID3
    if isinstance(which, (list, tuple)):
        which = {(w if isinstance(w, str) else ",".join(f"{v:.2f}" for v in w)): w for w in which}
    out = {}
    for name, reg in which.items():
        box = region_box(reg)
        sub = crop_frac(img, box)
        e = exposure(sub)
        out[name] = {"box": box, "mean": e["mean"], "stops": e["stops"], "clipped_high_pct": e["clipped_high_pct"],
                     "clipped_low_pct": e["clipped_low_pct"], "color": color(sub), "sharpness": sharpness(sub)}
    return out


def analyze(img: Image, subjects: dict | None = None, limits: dict | None = None, width: int = 480,
            expect: dict | None = None) -> dict:
    """Everything about a frame and the issues in it. `subjects` {name: box} adds per-subject exposure, colour and
    sharpness (a soft subject on a sharp background is a focus miss). `expect` states intent so a dark mood is not
    flagged: {"stops": [-3, -1]} (a range for the mean), {"cast": "warm"|"cool"|"neutral"}.
    Returns {"size", "exposure", "color", "regions", "subjects", "issues"}."""
    L = {**LIMITS, **(limits or {})}
    small = _im.fit(img, width)
    ex = exposure(small, L)
    col = color(small)
    regs = regions(small)
    subs = regions(small, subjects) if subjects else {}
    issues = []
    expect = expect or {}
    if ex["verdict"] == "flat":
        issues.append(issue("image.flat", "fail", f"the frame is one flat {col['name']} (luma std {ex['std']}): "
                            "nothing rendered, a camera inside a mesh, or a light/exposure far off",
                            "check the camera with qa.framing and the level's lights; look.still the same camera"))
    else:
        lo, hi = expect.get("stops", (L["stops_low"], L["stops_high"]))
        if ex["stops"] < lo:
            issues.append(issue("exposure.under", "warn", f"underexposed: mean {ex['stops']:+.1f} stops from mid grey "
                                f"(expected {lo:+.1f}..{hi:+.1f})", "raise the key light or exposure compensation "
                                "(look.post settings auto_exposure_bias)", value=ex["stops"], expected=[lo, hi]))
        elif ex["stops"] > hi:
            issues.append(issue("exposure.over", "warn", f"overexposed: mean {ex['stops']:+.1f} stops from mid grey "
                                f"(expected {lo:+.1f}..{hi:+.1f})", "lower the key light or exposure compensation",
                                value=ex["stops"], expected=[lo, hi]))
        if ex["clipped_high_pct"] > L["clip_high_pct"]:
            where = max(regs, key=lambda k: regs[k]["clipped_high_pct"])
            issues.append(issue("exposure.clipped_highlights", "warn", f"{ex['clipped_high_pct']:.1f}% of the frame "
                                f"is blown out (most in {where})", "lower that light, or exposure; check emissive "
                                "materials", value=ex["clipped_high_pct"], region=where, box=regs[where]["box"]))
        if ex["clipped_low_pct"] > L["clip_low_pct"] and not expect.get("stops"):
            where = max(regs, key=lambda k: regs[k]["clipped_low_pct"])
            issues.append(issue("exposure.crushed_shadows", "info", f"{ex['clipped_low_pct']:.1f}% of the frame is "
                                f"pure black (most in {where})", "add fill or bounce if detail should read there",
                                value=ex["clipped_low_pct"], region=where, box=regs[where]["box"]))
        want = expect.get("cast")
        if col["cast_amount"] > L["cast"] and want in (None, "neutral"):
            issues.append(issue("color.cast", "info" if want is None else "warn",
                                f"neutrals lean {col['cast_toward']} by {100 * col['cast_amount']:.0f}%",
                                "check light temperatures and white balance (look.post white_temp)",
                                value=col["cast"]))
        elif want in ("warm", "cool"):
            r, b = col["cast"]["r"], col["cast"]["b"]
            ok = (r - b > 0.02) if want == "warm" else (b - r > 0.02)
            if not ok:
                issues.append(issue("color.cast_expected", "warn", f"expected a {want} image, neutrals lean "
                                    f"{col['cast_toward']} (r {r:+.2f}, b {b:+.2f})", "adjust light temperature",
                                    value=col["cast"]))
    if subs:
        bg_sharp = sharpness(small)
        for name, s in subs.items():
            if bg_sharp > 20 and s["sharpness"] < L["soft_ratio"] * bg_sharp:
                # a plain, untextured subject also reads "soft": only a big gap is a likely focus miss
                sev = "warn" if s["sharpness"] < 0.4 * L["soft_ratio"] * bg_sharp else "info"
                issues.append(issue("focus.subject_soft", sev, f"{name} is soft (detail {s['sharpness']:.0f}) while "
                                    f"the frame is sharper ({bg_sharp:.0f}): focus missed?", "set focus on the subject "
                                    "(look.focus_track or the camera's manual_focus_distance)", subject=name,
                                    box=s["box"], value=s["sharpness"]))
            if s["stops"] < ex["stops"] - 1.5 and ex["verdict"] != "flat":
                issues.append(issue("exposure.subject_dark", "warn", f"{name} is {ex['stops'] - s['stops']:.1f} stops "
                                    "darker than the frame: the subject sinks into the background",
                                    "add key or fill on the subject", subject=name, box=s["box"], value=s["stops"]))
    return {"size": [img.w, img.h], "exposure": ex, "color": col, "regions": regs, "subjects": subs, "issues": issues}
