"""The AMV grade in numpy: the user's "Premium Glow CC" chain, rebuilt and fitted to the After Effects render.

The After Effects project was 8-bit and non-linear, so every effect of the grade worked on display sRGB values and clipped
to 0..1 after each step. `grade()` does the same on a float RGB image (display values, 0..1) and is the reference that
`blender/amv/grade.py` (the compositor node group) must match to ~2/255: every operation here is one that a node can
do (add, multiply, clamp, a 1-D polynomial, a Gaussian blur of integer size, a radial gradient), and the blur reproduces
Blender's Gaussian (sigma = size / 3, taps -size..size, edge pixels extended, normalised).

The chain, in the order of build.jsx: Sapphire S_Sharpen (unsharp) -> Magic Bullet Looks (Colorista 3-way faint cool
cast, lens vignette) -> Lumetri (Contrast, Highlights, Shadows, Whites, Blacks, Saturation) -> Brightness & Contrast
(non-legacy) -> Color Balance (preserve luminosity) -> Glow (threshold, blur, add). The preset gives slider values, not
the plug-ins' formulas, so each op here is a plausible model whose slider -> curve gains (the `K_*` constants) are
fixed, and `fit()` moves the slider values (starting from the preset's, `NOMINAL`) to match AE's frames. A
fitted value is "what the model needs", not necessarily what AE's slider says; the nominal values are kept beside them.

`estimate_frame()` / `fit_frames()` / the CLI do the fitting: pre-grade estimates are built from the clip, the
shot's exposure/saturation trim and its camera, and compared with the AE render in Lab, blurred, away from text.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

LUMA = (0.2126, 0.7152, 0.0722)

# slider -> curve gains (fixed; the fit moves the sliders)
K_SH, K_HI, K_WH, K_BL, K_CON = 0.30, 0.30, 0.30, 0.30, 2.0
K_BRIGHT, K_BC_CON = 0.5, 1.0
K_CB, K_GLOW = 0.5, 2.0

NOMINAL = {
    "sharpen_amount": 0.5, "sharpen_size": 4,
    "colorista": 1.0,
    "vig_amount": 0.345, "vig_size": 0.5,
    "hi_desat": 0.0, "curve1": 0.0, "curve2": 0.0, "curve3": 0.0,
    "contrast": 25.0, "highlights": 10.0, "shadows": 45.0, "whites": 20.0, "blacks": -12.0, "saturation": 150.0,
    "bc_brightness": 15.0, "bc_contrast": 20.0,
    "cb": [-10, 7, 10, -2, 4, -3, 12, 5, -12],
    "glow_threshold": 0.84, "glow_size": 90, "glow_intensity": 0.25,
}
COLORISTA_SHADOWS = (0.989, 0.990, 1.007)
COLORISTA_MIDS = (0.998, 0.996, 1.000)

# fit bounds for the scalar parameters
BOUNDS = {
    "colorista": (0, 4), "hi_desat": (0, 1),
    "curve1": (-0.3, 0.3), "curve2": (-0.3, 0.3), "curve3": (-0.3, 0.3), "vig_amount": (0, 0.9), "vig_size": (0.1, 0.9),
    "contrast": (-50, 100), "highlights": (-100, 100), "shadows": (-100, 100), "whites": (-100, 100),
    "blacks": (-100, 100), "saturation": (60, 260), "bc_brightness": (-60, 100), "bc_contrast": (-60, 100),
    "glow_threshold": (0.5, 0.98), "glow_intensity": (0.0, 1.5),
}


def params(p=None):
    """The preset's values with `p` (a dict, partial) on top."""
    out = json.loads(json.dumps(NOMINAL))
    for k, v in (p or {}).items():
        if k in out:
            out[k] = list(v) if k == "cb" else v
    return out


# ---------------------------------------------------------------- colour helpers

def luma(x):
    return x[..., 0] * LUMA[0] + x[..., 1] * LUMA[1] + x[..., 2] * LUMA[2]


def srgb_to_linear(x):
    x = np.asarray(x, np.float32)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(x):
    x = np.asarray(x, np.float32)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.maximum(x, 0) ** (1 / 2.4) - 0.055).astype(np.float32)


def rgb_to_lab(rgb):
    """Display sRGB (0..1) -> CIE Lab (D65)."""
    lin = srgb_to_linear(np.clip(rgb, 0, 1))
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


# ---------------------------------------------------------------- blur (Blender's Gaussian)

def gauss_kernel(size):
    r = int(size)
    if r < 1:
        return np.ones(1, np.float32)
    i = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-0.5 * (i / (r / 3.0)) ** 2)
    return (k / k.sum()).astype(np.float32)


def blur(x, size):
    """Separable Gaussian, `size` px (sigma = size / 3, truncated at +-size), edges extended."""
    k = gauss_kernel(size)
    if len(k) == 1:
        return x
    try:
        import cv2
        return cv2.sepFilter2D(np.ascontiguousarray(x, np.float32), -1, k, k, borderType=cv2.BORDER_REPLICATE)
    except ImportError:
        r = (len(k) - 1) // 2
        out = np.asarray(x, np.float32)
        for ax in (0, 1):
            pad = [(0, 0)] * out.ndim
            pad[ax] = (r, r)
            p = np.pad(out, pad, mode="edge")
            n = out.shape[ax]
            acc = 0
            for j, w in enumerate(k):
                acc = acc + w * np.take(p, np.arange(j, j + n), axis=ax)
            out = acc.astype(np.float32)
        return out


# ---------------------------------------------------------------- the operations

def clip01(x):
    return np.clip(x, 0.0, 1.0)


def sharpen(x, amount, size):
    return clip01(x + amount * (x - blur(x, size)))


def colorista(x, strength):
    l = luma(x)[..., None]
    ws, wm = (1 - l) ** 2, 4 * l * (1 - l)
    sh, mi = np.array(COLORISTA_SHADOWS, np.float32), np.array(COLORISTA_MIDS, np.float32)
    return clip01(x * (1 + strength * ((sh - 1) * ws + (mi - 1) * wm)))


def vignette_gain(h, w, amount, size):
    """1 - amount * t^2, t rising from 0 at radius `size` to 1 in the corners (radius 0 = centre, 1 = corner)."""
    yy = ((np.arange(h, dtype=np.float32) + 0.5) / h - 0.5) * 2
    xx = ((np.arange(w, dtype=np.float32) + 0.5) / w - 0.5) * 2
    rho = np.sqrt(yy[:, None] ** 2 + xx[None, :] ** 2) / math.sqrt(2)
    t = np.clip((rho - size) / (1 - size), 0, 1)
    return (1 - amount * t * t)[..., None].astype(np.float32)


def lumetri_tone(x, p):
    """Contrast / Highlights / Shadows / Whites / Blacks as a per-channel curve (display values)."""
    s_sh, s_hi, s_wh, s_bl, s_c = (p["shadows"] / 100, p["highlights"] / 100, p["whites"] / 100,
                                   p["blacks"] / 100, p["contrast"] / 100)
    y = (x + K_SH * s_sh * 6.75 * x * (1 - x) ** 2 + K_HI * s_hi * 6.75 * x * x * (1 - x)
         + K_WH * s_wh * x ** 3 + K_BL * s_bl * (1 - x) ** 3)
    y = clip01(y)
    smooth = y * y * (3 - 2 * y)
    return clip01(y + K_CON * s_c * (smooth - y))


def saturate(x, sat):
    l = luma(x)[..., None]
    return clip01(l + (x - l) * (sat / 100.0))


def highlight_desaturate(x, amount):
    """Pull near-white pixels toward grey (AE's clipped highlights read white, not tinted): 0 = off, 1 = full."""
    l = luma(x)[..., None]
    t = np.clip((l - 0.75) / 0.25, 0, 1)
    return clip01(x + (l - x) * (amount * t * t * (3 - 2 * t)))


def brightness_contrast(x, brightness, contrast):
    """Non-legacy B&C model: brightness bends the curve (ends fixed), contrast pivots at 0.5."""
    y = clip01(x + K_BRIGHT * brightness / 100 * 4 * x * (1 - x))
    return clip01(0.5 + (y - 0.5) * (1 + K_BC_CON * contrast / 100))


def _cb_weights(l):
    a, b = 0.25, 0.333
    ws = np.clip((l - b) / -a + 0.5, 0, 1)
    wm = np.clip((l - b) / a + 0.5, 0, 1) * np.clip((l + b - 1) / -a + 0.5, 0, 1)
    wh = np.clip((l + b - 1) / a + 0.5, 0, 1)
    return ws, wm, wh


def color_balance(x, cb):
    """AE Color Balance (shadows / midtones / highlights x R,G,B, -100..100), preserve luminosity."""
    l = luma(x)
    ws, wm, wh = (w[..., None] for w in _cb_weights(l))
    v = np.asarray(cb, np.float32).reshape(3, 3) * (K_CB / 100.0)
    y = clip01(x + v[0] * ws + v[1] * wm + v[2] * wh)
    ly = luma(y)[..., None]
    return clip01(y * (l[..., None] / np.maximum(ly, 1e-4)))


def residual_curve(x, c1, c2, c3):
    """What the named sliders cannot say: a small per-channel curve fixed at 0 and 1 (basis u, u(1-2x), u(1-2x)^2, u = x(1-x))."""
    u = x * (1 - x)
    w = 1 - 2 * x
    return clip01(x + u * (c1 + w * (c2 + w * c3)))


def glow(x, threshold, size, intensity):
    bright = np.maximum(x - threshold, 0) / (1 - threshold)
    return clip01(x + K_GLOW * intensity * blur(bright, size))


def grade(img, p=None, res_scale=1.0):
    """The whole chain on display-referred float RGB (H, W, 3), 0..1. `res_scale` scales the blur sizes (1 = 1920 wide)."""
    p = params(p)
    sc = lambda n: max(0, int(round(n * res_scale)))
    x = clip01(np.asarray(img, np.float32)[..., :3])
    h, w = x.shape[:2]
    x = sharpen(x, p["sharpen_amount"], sc(p["sharpen_size"]))
    x = colorista(x, p["colorista"])
    x = clip01(x * vignette_gain(h, w, p["vig_amount"], p["vig_size"]))
    x = lumetri_tone(x, p)
    x = saturate(x, p["saturation"])
    x = highlight_desaturate(x, p["hi_desat"])
    x = brightness_contrast(x, p["bc_brightness"], p["bc_contrast"])
    x = color_balance(x, p["cb"])
    x = residual_curve(x, p["curve1"], p["curve2"], p["curve3"])
    return glow(x, p["glow_threshold"], sc(p["glow_size"]), p["glow_intensity"])


# ---------------------------------------------------------------- pre-grade estimates (the fit's input)

W, H = 1920, 1080
WM_BOX = (0.40, 0.925, 0.60, 1.0)   # the SAU_EDITZ watermark (x0, y0, x1, y1 as screen fractions)


def trim(img, ev, sat):
    """The shot's balance: exposure in linear light, then Hue/Saturation master saturation (display)."""
    x = img
    if abs(ev) > 1e-9:
        x = linear_to_srgb(np.clip(srgb_to_linear(x) * 2.0 ** ev, 0, None))
        x = clip01(x)
    if abs(sat) > 1e-9:
        l = luma(x)[..., None]
        x = clip01(l + (x - l) * (1 + sat / 100.0))
    return x


def clean_frame(plan, f, shot):
    """True when f is a frame the fit can use: a single shot, no flash / strobe / title / blur key / letterbox."""
    from . import plan as P
    r = plan.raw
    for g in range(f - 2, f + 3):
        if abs(plan.flash_ev(g)) > 1e-6 or abs(P.keys_lin(r.get("flash_sat"), g)) > 1e-6 or plan.bars(g) > 0.5:
            return False
    for g in (f - 1, f, f + 1):
        rf = shot.rfb(g)
        if (rf and rf[0] > 1e-3) or shot.bulge(g) or shot.dblur(g):
            return False
    for t in list(r["titles"]) + list(shot.titles):
        if t["f_in"] - 1 <= f < t["f_in"] + t["spec"]["dur"] + 1:
            return False
    if any(abs(f - x) <= 3 for x in list(r.get("halftone") or []) + list(r.get("black") or []) + list(r.get("invert") or [])):
        return False
    if len(plan.visible(f)) != 1 or shot.raw.get("opacity") or shot.hole(f):
        return False
    return not (245 <= f <= 300 or 486 <= f <= 512)


def clip_frame(path, t, cache={}):
    """Nearest 60p frame of the clip at t seconds, RGB uint8 1920x1080."""
    import cv2
    cap = cache.get(path)
    if cap is None:
        cap = cache[path] = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, min(max(int(round(t * 60)), 0), n - 1))
    ok, bgr = cap.read()
    if not ok:
        raise RuntimeError(f"cannot read {path} at {t}s")
    return bgr[..., ::-1]


def estimate_frame(plan, f, scale=0.25):
    """(estimate float RGB, coverage mask) of the pre-grade screen at comp frame f, at `scale` x 1920x1080."""
    import cv2
    shot = plan.visible(f)[-1]
    src = clip_frame(plan.clip(shot), shot.remap(f))
    w, h = int(round(W * scale)), int(round(H * scale))
    k = 1.0 if scale > 0.5 else 0.5     # warp at full size for full-size output, else at half size (faster)
    ww, hh = int(W * k), int(H * k)
    base = src if k == 1.0 else cv2.resize(src, (ww, hh), interpolation=cv2.INTER_AREA)
    x = trim(base.astype(np.float32) / 255, shot.ev(f), shot.sat)
    m = np.array(shot.matrix(f), np.float64)
    m[:, 2] *= k   # source scaled by k -> screen scaled by k: k x -> k (A x + t)
    out = cv2.warpAffine(x, m, (ww, hh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    cov = cv2.warpAffine(np.ones(x.shape[:2], np.float32), m, (ww, hh), flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    if (ww, hh) != (w, h):
        out = cv2.resize(out, (w, h), interpolation=cv2.INTER_AREA)
        cov = cv2.resize(cov, (w, h), interpolation=cv2.INTER_AREA)
    return out, (cov > 0.999)


def fit_mask(cov, f=None):
    """Pixels the fit may use: covered by the warped plate, away from the watermark, and (M01's portal frames) away from
    the small drop-portal ellipse that shows shot A through the lens."""
    h, w = cov.shape
    m = cov.copy()
    if f is not None and 486 <= f <= 507:
        m[int(0.28 * h):int(0.72 * h), int(0.45 * w):int(0.72 * w)] = False
    x0, y0, x1, y1 = WM_BOX
    m[int(y0 * h):, int(x0 * w):int(x1 * w)] = False
    return m


def load_ref(ref_dir, f, size):
    import cv2
    bgr = cv2.imread(str(Path(ref_dir) / f"{f:04d}.png"))
    return cv2.resize(bgr[..., ::-1], size, interpolation=cv2.INTER_AREA).astype(np.float32) / 255


# ---------------------------------------------------------------- the fit

def _flat(p):
    names = [k for k in BOUNDS]
    return names, [p[k] for k in names] + list(p["cb"])


def _unflat(base, names, v):
    p = params(base)
    for k, x in zip(names, v):
        p[k] = float(x)
    p["cb"] = [float(x) for x in v[len(names):]]
    return p


def frame_error(est, ref, mask, p, res_scale, soft=1.0):
    """Per-pixel robust error image: Lab distance of the blurred graded estimate vs the blurred reference."""
    g = grade(est, p, res_scale)
    a, b = rgb_to_lab(blur(g, 1)), rgb_to_lab(blur(ref, 1))
    return np.sqrt(((a - b) ** 2).sum(-1) + soft), mask


def fit_frames(ests, refs, masks, start=None, res_scale=1 / 8, prior=0.02, iters=60, verbose=True):
    """Least-squares fit of the parameters to (est, ref, mask) triples. Returns (params, history)."""
    from scipy.optimize import least_squares
    base = params(start)
    names, v0 = _flat(base)
    lo = [BOUNDS[k][0] for k in names] + [-100] * 9
    hi = [BOUNDS[k][1] for k in names] + [100] * 9
    scale = np.array([(h - l) for l, h in zip(lo, hi)], np.float64) * 0.25
    nominal = np.array(_flat(params())[1], np.float64)
    sub = 2  # residual pixels subsampled for speed

    def resid(v):
        p = _unflat(base, names, v)
        out = []
        for e, r, m in zip(ests, refs, masks):
            g = grade(e, p, res_scale)
            a = rgb_to_lab(blur(g, 1))[::sub, ::sub]
            b = rgb_to_lab(blur(r, 1))[::sub, ::sub]
            d = np.sqrt(((a - b) ** 2).sum(-1) + 1.0)[m[::sub, ::sub]]
            out.append(d * 0.2)
        out.append(prior * (np.asarray(v) - nominal) / scale * 30)
        return np.concatenate(out)

    res = least_squares(resid, np.clip(v0, lo, hi), bounds=(lo, hi), loss="soft_l1", f_scale=2.0, max_nfev=iters,
                        diff_step=1e-2, x_scale="jac", verbose=2 if verbose else 0)
    return _unflat(base, names, res.x), res


def frame_stats(ests, refs, masks, p, res_scale):
    """Per frame: mean and median Lab dE (blurred, masked) and mean abs RGB error in /255."""
    rows = []
    for e, r, m in zip(ests, refs, masks):
        g = grade(e, p, res_scale)
        a, b = rgb_to_lab(blur(g, 1)), rgb_to_lab(blur(r, 1))
        d = np.sqrt(((a - b) ** 2).sum(-1))[m]
        rgb = np.abs(blur(g, 1) - blur(r, 1)).mean(-1)[m] * 255
        rows.append({"de_mean": float(d.mean()), "de_median": float(np.median(d)), "rgb_mae": float(rgb.mean())})
    return rows


def grade_linear(img, p=None, res_scale=1.0):
    """The same grade on scene-linear data (what the node group does by default): to display sRGB, grade, back."""
    x = linear_to_srgb(np.clip(np.asarray(img, np.float32)[..., :3], 0, None))
    return srgb_to_linear(grade(x, p, res_scale))


# ---------------------------------------------------------------- command line

FFMPEG = "/home/nikhil/code/film-making/bin/ffmpeg"


def select_frames(plan, last=600, per_shot=5):
    by = {}
    for f in range(last):
        vs = plan.visible(f)
        if len(vs) == 1 and clean_frame(plan, f, vs[0]):
            by.setdefault(vs[0].name, []).append(f)
    sel = []
    for v in by.values():
        n = min(per_shot, len(v))
        sel += [v[int(i * (len(v) - 1) / max(n - 1, 1))] for i in range(n)]
    return sorted(set(sel))


def cmd_prepare(a):
    import subprocess
    import tempfile
    from . import plan as P
    plan = P.load(a.film)
    frames = [int(f) for f in a.frames.split(",")] if a.frames else select_frames(plan, per_shot=a.per_shot)
    ref_dir = Path(a.ref)
    if ref_dir.is_file():   # an mp4: decode the chosen frames once to PNGs (960 wide, or full size above scale 0.5)
        tmp = Path(tempfile.mkdtemp(prefix="grade_ref_"))
        vf = "scale=960:540:flags=area" if a.scale <= 0.5 else "null"
        sel = "+".join(f"eq(n\\,{f})" for f in frames)
        subprocess.run([FFMPEG, "-v", "error", "-i", str(ref_dir), "-vf", f"select={sel},{vf}", "-fps_mode", "passthrough",
                        "-start_number", "0", str(tmp / "k%04d.png")], check=True)
        for i, f in enumerate(sorted(set(frames))):   # ffmpeg writes the selected frames in video order
            (tmp / f"k{i:04d}.png").rename(tmp / f"{f:04d}.png")
        ref_dir = tmp
    size = (int(W * a.scale), int(H * a.scale))
    ests, refs, masks = [], [], []
    for f in frames:
        e, cov = estimate_frame(plan, f, a.scale)
        ests.append(e)
        refs.append(load_ref(ref_dir, f, size))
        masks.append(fit_mask(cov, f))
    u8 = lambda arr: np.round(np.array(arr) * 255).astype(np.uint8)   # 8-bit like the AE project: a quarter of the size
    if a.append:   # add to an existing cache of the same scale
        old = np.load(a.append)
        keep = [i for i, f in enumerate(old["frames"]) if int(f) not in frames]
        frames = [int(f) for f in old["frames"][keep]] + frames
        ests, refs, masks = (list(old["est"][keep].astype(np.float32) / 255) + ests,
                             list(old["ref"][keep].astype(np.float32) / 255) + refs, list(old["mask"][keep]) + masks)
    np.savez(a.out, frames=frames, est=u8(ests), ref=u8(refs), mask=np.array(masks), scale=a.scale)
    print(f"{len(frames)} frames -> {a.out}")


def cmd_fit(a):
    import cv2
    z = np.load(a.cache)
    d = {k: z[k] for k in z.files}
    for k in ("est", "ref"):
        d[k] = d[k].astype(np.float32) / 255
    s = float(d["scale"])
    fs = a.fit_width / d["est"].shape[2]
    size = (a.fit_width, int(round(d["est"].shape[1] * fs)))
    down = lambda arr: np.array([cv2.resize(x, size, interpolation=cv2.INTER_AREA) for x in arr])
    est, ref = down(d["est"]), down(d["ref"])
    mask = np.array([cv2.resize(m.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0 for m in d["mask"]])
    res_scale = s * fs
    before = frame_stats(est, ref, mask, None, res_scale)
    start = json.loads(Path(a.start).read_text()) if a.start else None
    start = start.get("fitted", start) if start else None
    p, res = fit_frames(est, ref, mask, start=start, res_scale=res_scale, iters=a.iters)
    after = frame_stats(est, ref, mask, p, res_scale)
    # the same stats at the cache's full resolution (what the contact sheets show)
    full_b = frame_stats(d["est"], d["ref"], d["mask"], None, s)
    full_a = frame_stats(d["est"], d["ref"], d["mask"], p, s)
    mean = lambda rows, k: float(np.mean([r[k] for r in rows]))
    doc = {"fitted": p, "nominal": params(),
           "report": {"frames": [int(f) for f in d["frames"]], "before": full_b, "after": full_a,
                      "summary": {k: {"before": mean(full_b, k), "after": mean(full_a, k)} for k in ("de_mean", "de_median", "rgb_mae")},
                      "fit_cost": float(res.cost), "note": "dE = Lab distance of blurred, masked 480x270 frames; rgb_mae in /255"}}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, indent=1))
    print(json.dumps(doc["report"]["summary"], indent=1))


def cmd_refine(a):
    """Full-size refinement of what a 480-wide fit cannot see: the unsharp mask and the glow radius (coordinate search)."""
    z = np.load(a.cache)
    est = z["est"].astype(np.float32) / 255
    ref = z["ref"].astype(np.float32) / 255
    mask = z["mask"]
    s = float(z["scale"])
    doc = json.loads(Path(a.params).read_text())
    p = doc.get("fitted", doc)
    lab_ref = [rgb_to_lab(blur(r, 1)) for r in ref]

    def score(q):
        tot = []
        for e, lr, m in zip(est, lab_ref, mask):
            d = np.sqrt(((rgb_to_lab(blur(grade(e, q, s), 1)) - lr) ** 2).sum(-1))[m]
            tot.append(d.mean())
        return float(np.mean(tot))

    grid = {"sharpen_amount": [0.0, 0.15, 0.3, 0.5, 0.75], "sharpen_size": [2, 3, 4, 6],
            "glow_size": [45, 70, 90, 140, 200], "glow_intensity": [0.05, 0.1, 0.15, 0.25, 0.4]}
    p = dict(p)
    best = score(p)
    print("start", round(best, 3))
    for sweep in range(2):
        for k, vals in grid.items():
            for v in vals:
                q = dict(p, **{k: v})
                sc = score(q)
                if sc < best - 1e-4:
                    best, p = sc, q
                    print("  ", k, "->", v, round(best, 3))
    doc["fitted"] = p
    doc.setdefault("report", {})["refine"] = {"frames": [int(f) for f in z["frames"]], "mean_dE_full_res": best}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, indent=1))


def cmd_sheet(a):
    """Contact sheets: estimate | grade_np | Blender group | AE, 6 frames per image (Blender column optional)."""
    import cv2
    z = np.load(a.cache)
    frames = [int(f) for f in z["frames"]]
    pick = [int(f) for f in a.frames.split(",")]
    idx = [frames.index(f) for f in pick]
    p = json.loads(Path(a.params).read_text())
    p = p.get("fitted", p)
    est = z["est"][idx].astype(np.float32) / 255
    if a.save_estimates:
        np.save(a.save_estimates, est)
    blend = np.load(a.blender) if a.blender else None
    s = float(z["scale"])
    rows = []
    for k, (f, i) in enumerate(zip(pick, idx)):
        tiles = [est[k], grade(est[k], p, s)]
        if blend is not None:
            tiles.append(np.clip(blend[k], 0, 1))
        tiles.append(z["ref"][i].astype(np.float32) / 255)
        row = (np.hstack(tiles)[..., ::-1] * 255).astype(np.uint8).copy()
        cv2.putText(row, f"f{f}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        rows.append(row)
    names = ["estimate", "grade_np"] + (["blender"] if blend is not None else []) + ["AE"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for j in range(0, len(rows), 6):
        sheet = np.vstack(rows[j:j + 6])
        tw = sheet.shape[1] // len(names)
        for c, n in enumerate(names):
            cv2.putText(sheet, n, (c * tw + 8, sheet.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.imwrite(str(out / f"contact_{j // 6 + 1}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if blend is not None:
        err = [float(np.abs(np.clip(blend[k], 0, 1) - grade(est[k], p, s)).max() * 255) for k in range(len(pick))]
        print("max |blender - grade_np| per frame (/255):", [round(e, 2) for e in err])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("prepare", help="build the fit cache: pre-grade estimates + AE reference frames")
    pr.add_argument("--film", default="films/timeless")
    pr.add_argument("--ref", required=True, help="AE render mp4 (or a folder of NNNN.png frames)")
    pr.add_argument("--out", required=True)
    pr.add_argument("--per-shot", type=int, default=5)
    pr.add_argument("--scale", type=float, default=0.25)
    pr.add_argument("--append", help="an existing cache (same scale) to add these frames to")
    pr.add_argument("--frames", help="comma list of comp frames (default: clean frames, --per-shot per shot)")
    pr.set_defaults(fn=cmd_prepare)
    ft = sub.add_parser("fit", help="fit the parameters to the cache, write grade.json")
    ft.add_argument("--cache", required=True)
    ft.add_argument("--out", required=True)
    ft.add_argument("--fit-width", type=int, default=240)
    ft.add_argument("--start", help="a grade.json whose fitted values start the search (default: the preset)")
    ft.add_argument("--iters", type=int, default=25)
    ft.set_defaults(fn=cmd_fit)
    rf = sub.add_parser("refine", help="tune sharpen / glow radius on a full-size cache")
    rf.add_argument("--cache", required=True)
    rf.add_argument("--params", required=True)
    rf.add_argument("--out", required=True)
    rf.set_defaults(fn=cmd_refine)
    sh = sub.add_parser("sheet", help="contact sheets estimate | grade_np | blender | AE")
    sh.add_argument("--cache", required=True)
    sh.add_argument("--params", required=True)
    sh.add_argument("--frames", required=True, help="comma list of comp frames present in the cache")
    sh.add_argument("--out", required=True)
    sh.add_argument("--blender", help="npy of the Blender group's output for the same frames, in order")
    sh.add_argument("--save-estimates", help="write the chosen estimates (for the Blender driver) to this npy")
    sh.set_defaults(fn=cmd_sheet)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
