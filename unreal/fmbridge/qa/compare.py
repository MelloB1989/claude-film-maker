"""A frame against another: a reference, the same frame from yesterday's version, the next frame across a cut.
PSNR (dB) on RGB, SSIM on luma (8x8 windows, stride 4, the usual constants), an SSIM map on a grid (where it
differs), per-cell colour shift, and a heatmap of the difference. Both are compared at analysis size."""
from __future__ import annotations

import math

from . import image as _im
from .image import Image, fit, luma8, resize, rgb
from .issues import issue

C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
WIN, STRIDE = 8, 4


def _same(a: Image, b: Image, width: int) -> tuple:
    a = rgb(fit(a, width))
    if (b.w, b.h) != (a.w, a.h):
        if abs(b.w / b.h - a.w / a.h) > 0.02:
            raise ValueError(f"cannot compare a {a.w}x{a.h} frame with a {b.w}x{b.h} one: different aspect ratios")
        b = resize(rgb(b), a.w, a.h)
    return a, rgb(b)


def psnr(a: Image, b: Image) -> float:
    """Peak signal-to-noise ratio in dB over RGB (inf for identical images). > 40 dB: indistinguishable; 30-40: close
    (noise, AA); < 25: visibly different."""
    NP = _im.NP
    if NP is not None:
        d = a.array().astype(NP.float64) - b.array().astype(NP.float64)
        mse = float((d * d).mean())
    else:
        mse = sum((x - y) ** 2 for x, y in zip(a.data, b.data)) / max(1, len(a.data))
    return float("inf") if mse == 0 else round(10 * math.log10(255 ** 2 / mse), 3)


def _windows(w: int, h: int):
    for y in range(0, max(1, h - WIN + 1), STRIDE):
        for x in range(0, max(1, w - WIN + 1), STRIDE):
            yield x, y


def ssim_windows(a: Image, b: Image) -> list:
    """SSIM per window: [(x, y, ssim)] with (x, y) the window's top-left pixel."""
    w, h = a.w, a.h
    ya, yb = luma8(a), luma8(b)
    NP = _im.NP
    if NP is not None:
        A = NP.frombuffer(bytes(ya), NP.uint8).reshape(h, w).astype(NP.float64)
        B = NP.frombuffer(bytes(yb), NP.uint8).reshape(h, w).astype(NP.float64)
        win = min(WIN, w, h)
        ys = NP.arange(0, max(1, h - win + 1), STRIDE)
        xs = NP.arange(0, max(1, w - win + 1), STRIDE)

        def box(M):  # window sums by integral image
            S = NP.zeros((h + 1, w + 1))
            S[1:, 1:] = M.cumsum(0).cumsum(1)
            return (S[ys[:, None] + win, xs[None, :] + win] - S[ys[:, None], xs[None, :] + win]
                    - S[ys[:, None] + win, xs[None, :]] + S[ys[:, None], xs[None, :]]) / (win * win)

        ma, mb = box(A), box(B)
        va, vb, cov = box(A * A) - ma * ma, box(B * B) - mb * mb, box(A * B) - ma * mb
        s = ((2 * ma * mb + C1) * (2 * cov + C2)) / ((ma * ma + mb * mb + C1) * (va + vb + C2))
        return [(int(x), int(y), float(s[j, i])) for j, y in enumerate(ys) for i, x in enumerate(xs)]
    out = []
    win = min(WIN, w, h)
    n = win * win
    for x, y in _windows(w, h):
        sa = sb = saa = sbb = sab = 0
        for yy in range(y, y + win):
            o = yy * w + x
            for i in range(o, o + win):
                p, q = ya[i], yb[i]
                sa += p
                sb += q
                saa += p * p
                sbb += q * q
                sab += p * q
        ma, mb = sa / n, sb / n
        va, vb, cv = saa / n - ma * ma, sbb / n - mb * mb, sab / n - ma * mb
        out.append((x, y, ((2 * ma * mb + C1) * (2 * cv + C2)) / ((ma * ma + mb * mb + C1) * (va + vb + C2))))
    return out


def ssim(a: Image, b: Image) -> float:
    """Mean structural similarity, 1.0 identical; > 0.95 the same picture; 0.8-0.95 the same shot with changes;
    < 0.6 a different picture."""
    win = ssim_windows(a, b)
    return round(sum(s for _, _, s in win) / max(1, len(win)), 4)


def ssim_grid(a: Image, b: Image, cols: int = 4, rows: int = 3) -> list:
    """SSIM averaged over a cols x rows grid: rows of values, top to bottom (where the frames differ)."""
    acc = [[[0.0, 0] for _ in range(cols)] for _ in range(rows)]
    for x, y, s in ssim_windows(a, b):
        c = min(cols - 1, int((x + WIN / 2) * cols / a.w))
        r = min(rows - 1, int((y + WIN / 2) * rows / a.h))
        acc[r][c][0] += s
        acc[r][c][1] += 1
    return [[round(t / n, 4) if n else 1.0 for t, n in row] for row in acc]


def diff_image(a: Image, b: Image, gain: float = 4.0) -> Image:
    """A heatmap of |a - b| (max over channels, times `gain`) over a dimmed copy of a: changes glow red-yellow."""
    out = Image(a.w, a.h, 3)
    NP = _im.NP
    if NP is not None:
        A, B = a.array().astype(NP.int16), b.array().astype(NP.int16)
        d = NP.clip(NP.abs(A - B).max(2) * gain, 0, 255)
        base = A.mean(2) * 0.35
        r = NP.clip(base + d, 0, 255)
        g = NP.clip(base + NP.maximum(d - 128, 0) * 2, 0, 255)
        bl = NP.clip(base * (1 - d / 255), 0, 255)
        return Image.from_array(NP.stack([r, g, bl], 2))
    for i in range(a.w * a.h):
        o = 3 * i
        d = min(255, max(abs(a.data[o + k] - b.data[o + k]) for k in range(3)) * gain)
        base = (a.data[o] + a.data[o + 1] + a.data[o + 2]) / 3 * 0.35
        out.data[o] = int(min(255, base + d))
        out.data[o + 1] = int(min(255, base + max(d - 128, 0) * 2))
        out.data[o + 2] = int(max(0, min(255, base * (1 - d / 255))))
    return out


def compare(a: Image, b: Image, width: int = 480, cols: int = 4, rows: int = 3, thresholds: dict | None = None) -> dict:
    """How b differs from a: {"psnr", "ssim", "grid" (SSIM per cell), "changed" (cells under the threshold, with
    boxes), "mean_shift" (mean RGB b - a), "verdict": same | close | changed | different, "issues"}.
    thresholds: {"same": 0.98, "close": 0.9, "different": 0.6} on SSIM, {"cell": 0.85} per cell."""
    t = {"same": 0.98, "close": 0.90, "different": 0.60, "cell": 0.85, **(thresholds or {})}
    A, B = _same(a, b, width)
    s = ssim(A, B)
    p = psnr(A, B)
    grid = ssim_grid(A, B, cols, rows)
    changed = [{"cell": [c, r], "box": [c / cols, r / rows, (c + 1) / cols, (r + 1) / rows], "ssim": v}
               for r, row in enumerate(grid) for c, v in enumerate(row) if v < t["cell"]]
    ma, mb = _im.mean_rgb(A), _im.mean_rgb(B)
    shift = [round(y - x, 2) for x, y in zip(ma, mb)]
    verdict = "same" if s >= t["same"] else "close" if s >= t["close"] else "changed" if s >= t["different"] else "different"
    return {"psnr": p, "ssim": s, "grid": grid, "changed": changed, "mean_shift": shift, "verdict": verdict,
            "size": [A.w, A.h]}


def against_reference(img: Image, ref: Image, name: str = "frame", min_ssim: float = 0.9, **kw) -> dict:
    """compare() plus issues: a frame that should match its reference (a regression test of a look)."""
    r = compare(ref, img, **kw)
    issues = []
    if r["ssim"] < min_ssim:
        issues.append(issue("compare.differs", "fail" if r["verdict"] == "different" else "warn",
                            f"{name} differs from its reference: SSIM {r['ssim']:.3f} (< {min_ssim}), PSNR {r['psnr']} dB, "
                            f"{len(r['changed'])} of {len(r['grid']) * len(r['grid'][0])} cells changed",
                            "look at the diff image; if the change is intended, replace the reference",
                            value=r["ssim"], expected=min_ssim))
        for c in r["changed"][:6]:
            issues.append(issue("compare.region_changed", "info", f"cell {c['cell']} SSIM {c['ssim']:.2f}",
                                box=c["box"], value=c["ssim"]))
    shift = max(abs(v) for v in r["mean_shift"])
    if shift > 12:
        issues.append(issue("compare.color_shift", "warn", f"mean colour moved by {r['mean_shift']} (RGB, 0..255) "
                            "from the reference", "check exposure, light intensity and post-process changes",
                            value=r["mean_shift"]))
    r["issues"] = issues
    return r
