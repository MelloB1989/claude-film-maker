"""The After Effects effects the AMV edit puts on a shot layer, as pure numpy / OpenCV functions.

`build.jsx` stacks these on each shot (balance -> titles -> matte cutout -> hole mask -> motion tile -> radial blur ->
directional blur -> optics compensation). The Blender scene can't do them (they warp or blur the *layer*, before its
transform), so `bake.py` runs them per frame with the functions here and the scene shows the result as a texture.

Conventions (AE's 8-bit project, as `plan.py`):
- images are float32 `H x W x C` (C = 3 RGB or 4 RGBA), values 0..1 in sRGB, alpha straight (not premultiplied);
- coordinates passed to the effects are *continuous* pixel coordinates: pixel i spans [i, i+1), so the centre of a
  1920x1080 layer is (960, 540). OpenCV's remap/warp use integer pixel centres, hence the 0.5 shifts below;
- anything that blurs, warps or mirrors works on premultiplied colour (what AE does on a layer with alpha) and hands
  back straight alpha, so a feathered edge never grows a dark or bright fringe;
- the functions that move pixels around a point take that point in the array's own pixel space: `bake.py` adds the
  canvas offset (and the --scale) to the plan's layer-space values before calling.

What is exact and what is calibrated against the AE render is spelled out per function; the calibration run is in
`bake_calibrate.py`'s output (docs/PIPELINE-AMV.md "bake").
"""
from __future__ import annotations

import math

import cv2
import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)

# --- calibrated constants (see the module docstring); each is a single place to retune ----------------------------
RFB_LENGTH = 0.12        # CC Radial Fast Blur: ray length as a fraction of the distance to the centre, per amount/100
RFB_PASSES = 9           # 2**9 = 512 geometric samples along the ray: spacing under ~2 px at the far corner
OPTICS_MODEL = "fisheye"  # see optics_compensation


# ---------------------------------------------------------------------------------------------------------------
# colour helpers
# ---------------------------------------------------------------------------------------------------------------

def srgb_to_linear(x):
    x = np.asarray(x, np.float32)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(x):
    x = np.clip(np.asarray(x, np.float32), 0.0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


def premultiply(img):
    """Straight RGBA -> premultiplied RGBA (RGB passes through unchanged)."""
    if img.shape[2] < 4:
        return img
    out = img.copy()
    out[..., :3] *= img[..., 3:4]
    return out


def unpremultiply(img):
    if img.shape[2] < 4:
        return img
    a = img[..., 3:4]
    out = img.copy()
    out[..., :3] = np.where(a > 1e-6, img[..., :3] / np.maximum(a, 1e-6), 0.0)
    return np.clip(out, 0.0, 1.0)


def luma(rgb):
    return rgb[..., :3] @ LUMA


def over(top, bottom):
    """Straight-alpha RGBA `top` over `bottom` (RGB or RGBA); returns the same channel count as `bottom`."""
    ta = top[..., 3:4]
    if bottom.shape[2] == 3:
        return (top[..., :3] * ta + bottom * (1 - ta)).astype(np.float32)
    ba = bottom[..., 3:4]
    oa = ta + ba * (1 - ta)
    rgb = np.where(oa > 1e-6, (top[..., :3] * ta + bottom[..., :3] * ba * (1 - ta)) / np.maximum(oa, 1e-6), 0.0)
    return np.concatenate([rgb, oa], axis=2).astype(np.float32)


def _with_alpha_split(img):
    """(rgb, alpha or None)"""
    return (img[..., :3], img[..., 3:4]) if img.shape[2] == 4 else (img, None)


def _join(rgb, a):
    return rgb if a is None else np.concatenate([rgb, a], axis=2)


# ---------------------------------------------------------------------------------------------------------------
# balance
# ---------------------------------------------------------------------------------------------------------------

def exposure(img, ev):
    """AE Exposure (channel Master, offset 0, gamma 1): the effect always works in linear light, whatever the project
    setting, so: decode sRGB, multiply by 2^ev, encode. Alpha is untouched; values clip at 1 (8-bit)."""
    if ev == 0:
        return img
    rgb, a = _with_alpha_split(img)
    out = linear_to_srgb(srgb_to_linear(rgb) * (2.0 ** ev))
    return _join(np.clip(out, 0.0, 1.0), a)


def hue_sat_master(img, sat):
    """AE Hue/Saturation, Master Saturation `sat` (-100 .. 100): HSL saturation scaled, lightness (max+min)/2 and hue
    kept. Negative: S * (1 + sat/100) (-100 = grey). Positive: the missing saturation is made up by sat/100
    (+100 = fully saturated), which is how AE's colour wheel treats the upper half (the plan only uses -12)."""
    if sat == 0:
        return img
    rgb, a = _with_alpha_split(img)
    mx, mn = rgb.max(axis=2, keepdims=True), rgb.min(axis=2, keepdims=True)
    L = (mx + mn) * 0.5
    d = mx - mn
    s = np.where(d > 1e-6, d / np.maximum(1.0 - np.abs(2.0 * L - 1.0), 1e-6), 0.0)
    k = sat / 100.0
    s2 = s * (1.0 + k) if k < 0 else s + (1.0 - s) * k
    gain = np.where(s > 1e-6, s2 / np.maximum(s, 1e-6), 1.0)
    out = L + (rgb - L) * gain
    # a pure grey has no hue to saturate: it stays grey
    return _join(np.clip(out, 0.0, 1.0).astype(np.float32), a)


def defocus(img, blurriness):
    """AE Gaussian Blur (Blurriness `b` is the Gaussian's sigma x 2 in px... AE's own definition is the kernel
    'radius'; sigma = b / 2 matches its box-filter approximation within a few per cent). Unused by the timeless plan."""
    if blurriness <= 0:
        return img
    pm = premultiply(img)
    out = cv2.GaussianBlur(pm, (0, 0), blurriness / 2.0, borderType=cv2.BORDER_REFLECT)
    return unpremultiply(out)


# ---------------------------------------------------------------------------------------------------------------
# glow
# ---------------------------------------------------------------------------------------------------------------

def glow(img, threshold_pct, radius, intensity):
    """AE Glow (Glo2, based on colour channels, operation Add, original colours): the parts of the picture brighter than
    the threshold are blurred with a few radii (a tight halo plus a wide bloom, weights 0.5/0.3/0.2) and added back
    on top, scaled by `intensity`. A pixel counts in proportion to how far it is above the threshold:
    clip((luma - t) / (1 - t)). Approximate: AE does not publish its kernel; check `bake_calibrate.py` stills.
    The rim of the matte cutout (threshold 55, radius 18, intensity 0.6) is its only user here."""
    rgb, a = _with_alpha_split(img)
    t = threshold_pct / 100.0
    w = np.clip((luma(rgb) - t) / max(1.0 - t, 1e-3), 0.0, 1.0)[..., None]
    bright = rgb * w
    acc = np.zeros_like(rgb)
    for sigma, wt in ((radius * 0.5, 0.5), (radius * 1.0, 0.3), (radius * 2.0, 0.2)):
        acc += wt * cv2.GaussianBlur(bright, (0, 0), max(sigma, 0.3), borderType=cv2.BORDER_REFLECT)
    return _join(np.clip(rgb + intensity * acc, 0.0, 1.0).astype(np.float32), a)


# ---------------------------------------------------------------------------------------------------------------
# canvas: motion tile
# ---------------------------------------------------------------------------------------------------------------

def tile_canvas(w, h, out_w_pct, out_h_pct):
    """(canvas w, h, ox, oy) of a `w` x `h` layer under Motion Tile `out_*_pct`: even sizes, layer pixel (x, y) at canvas
    (x + ox, y + oy). The same rule as `Shot.canvas` (kept in step by a test)."""
    cw = int(round(w * out_w_pct / 100.0 / 2.0)) * 2
    ch = int(round(h * out_h_pct / 100.0 / 2.0)) * 2
    return cw, ch, (cw - w) // 2, (ch - h) // 2


def motion_tile(img, out_w_pct, out_h_pct):
    """AE Motion Tile: tile size 100 % (one cell = the layer), Mirror Edges on, output size `out_*_pct` % of the layer.
    The cell stays centred, and the canvas grows to `tile_canvas`; neighbouring cells are mirrored copies, so the
    seam repeats the edge pixel (cv2.BORDER_REFLECT). Straight or premultiplied alike: it only moves pixels."""
    h, w = img.shape[:2]
    cw, ch, ox, oy = tile_canvas(w, h, out_w_pct, out_h_pct)
    if (cw, ch) == (w, h):
        return img
    ox_r, oy_r = cw - w - ox, ch - h - oy
    if ox < 0 or oy < 0 or ox_r < 0 or oy_r < 0:   # output smaller than the layer: Motion Tile crops around the centre
        x0, y0 = max(-ox, 0), max(-oy, 0)
        img = img[y0:h - max(-oy_r, 0), x0:w - max(-ox_r, 0)]
        ox, oy, ox_r, oy_r = max(ox, 0), max(oy, 0), max(ox_r, 0), max(oy_r, 0)
    return _reflect_pad(img, oy, oy_r, ox, ox_r)


def _reflect_pad(img, top, bottom, left, right):
    """copyMakeBorder with mirrored edges, however large the margins (OpenCV folds repeatedly)."""
    if not (top or bottom or left or right):
        return img
    return cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_REFLECT)


# ---------------------------------------------------------------------------------------------------------------
# radial fast blur
# ---------------------------------------------------------------------------------------------------------------

def _zoom_about(img, scale, cx, cy):
    """`img` sampled at c + (p - c) * scale for every output pixel p (so scale < 1 pulls content from nearer the centre,
    smearing it outward); outside the source is transparent/black. (cx, cy) continuous pixel coordinates."""
    h, w = img.shape[:2]
    # output pixel centre (j + .5) <- source continuous c + (j + .5 - c) * scale  =>  cv2 coords minus .5
    m = np.array([[scale, 0.0, (cx - cx * scale) + 0.5 * scale - 0.5],
                  [0.0, scale, (cy - cy * scale) + 0.5 * scale - 0.5]], np.float64)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def radial_fast_blur(img, amount, center, mode="brightest"):
    """AE CC Radial Fast Blur, Type Zoom. Every pixel gathers samples along the ray towards `center`
    (c + (p - c) * s, s from 1 down to 1 - L, L = RFB_LENGTH * amount / 100), so the blur grows with the distance
    from the centre and streaks run radially. `mode`: 'standard' averages the samples, 'brightest' keeps the per-channel
    maximum (hot highlights streak without dimming the plate), 'darkest' the minimum.

    The samples are not looped one by one (a 60 blur is hundreds of px long) but built the way the effect itself is
    fast: `RFB_PASSES` doublings, pass i merging the image with a copy zoomed by (1-L)^(2^i / 2^n); the composed zooms
    cover s = (1-L)^(k / 2^n), k = 0 .. 2^n - 1, geometrically spaced, so no stepped ghosts, and the cost is n warps.
    `center` is (cx, cy) in the array's pixel space. Premultiplied internally."""
    if amount <= 1e-6:
        return img
    L = min(RFB_LENGTH * amount / 100.0, 0.98)
    pm = premultiply(img)
    op = {"standard": lambda a, b: (a + b) * 0.5, "brightest": np.maximum, "darkest": np.minimum}[mode.lower()]
    n = RFB_PASSES
    cur = pm
    for i in range(n):
        z = (1.0 - L) ** ((2 ** i) / float(2 ** n))
        cur = op(cur, _zoom_about(cur, z, center[0], center[1]))
    return unpremultiply(cur)


# ---------------------------------------------------------------------------------------------------------------
# directional blur
# ---------------------------------------------------------------------------------------------------------------

def _line_kernel(length, angle_rad):
    """A normalised anti-aliased line kernel of `length` px through the centre at `angle_rad` (0 = +x, y down)."""
    half = max(int(math.ceil(length / 2.0)), 1)
    size = 2 * half + 1
    # sample the segment densely and splat bilinearly: exact box-along-the-line weights
    n = max(int(length * 8), 8)
    t = (np.arange(n) + 0.5) / n - 0.5
    xs = half + t * length * math.cos(angle_rad)
    ys = half + t * length * math.sin(angle_rad)
    k = np.zeros((size, size), np.float32)
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    fx, fy = xs - x0, ys - y0
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        np.add.at(k, (np.clip(y0 + dy, 0, size - 1), np.clip(x0 + dx, 0, size - 1)), wt)
    return k / k.sum()


def directional_blur(img, direction_deg, length):
    """AE Directional Blur (the `ADBE Motion Blur` effect): a box average over `length` px along `direction_deg`, centred
    on the pixel (AE's dial: 0 = vertical, 90 = horizontal, clockwise). Samples outside the layer count as transparent,
    as in AE. Horizontal and vertical take the separable path."""
    if length <= 1e-6:
        return img
    pm = premultiply(img)
    d = direction_deg % 180.0
    if d in (0.0, 90.0):
        r = int(math.ceil(length / 2.0))
        k = np.clip(length / 2.0 - np.abs(np.arange(-r, r + 1)) + 0.5, 0.0, 1.0).astype(np.float32)
        k /= k.sum()
        kx, ky = (k.reshape(1, -1), np.ones((1, 1), np.float32))
        if d == 0.0:
            kx, ky = ky, k.reshape(-1, 1)
        out = cv2.sepFilter2D(pm, -1, kx.ravel(), ky.ravel(), borderType=cv2.BORDER_CONSTANT)
    else:
        # AE angle: 0 = up, 90 = right (clockwise): the blur axis in image coordinates is (sin, -cos)
        a = math.radians(direction_deg)
        out = cv2.filter2D(pm, -1, _line_kernel(length, math.atan2(-math.cos(a), math.sin(a))),
                           borderType=cv2.BORDER_CONSTANT)
    return unpremultiply(out)


# ---------------------------------------------------------------------------------------------------------------
# optics compensation
# ---------------------------------------------------------------------------------------------------------------

def _fov_dim(w, h, orientation):
    """The image dimension the FOV spans: 1 horizontal, 2 vertical, 3 diagonal (AE's FOV Orientation menu)."""
    return {1: float(w), 2: float(h), 3: math.hypot(w, h)}[int(orientation)]


def optics_source_radius(r, fov_deg, dim, reverse=True):
    """For a point at radius `r` px from the view centre in the *output*, the radius in the source it samples.

    Model: a rectilinear picture of focal length f = (dim / 2) / tan(fov / 2) px (the FOV spans `dim`) against a
    fisheye (equidistant) of the same f. Reverse Lens Distortion (the plan's setting) takes the output radius as the
    rectilinear one and samples the fisheye position r_src = f * atan(r / f): the source is *pulled outward* with the
    radius, the centre keeps its scale and the outskirts are magnified, a bulge that crops the frame's corners away.
    Forward (reverse=False) is the inverse, r_src = f * tan(r / f): the picture shrinks and the corners go empty.
    Calibrated on the AE render (T04 f135, fov 30): measured edge displacement +2.5 / +7.7 / +17.7 px at
    r = 317 / 453 / 609 (half-res screen px), this model predicts +2.3 / +6.9 / +17.1."""
    f = (dim / 2.0) / math.tan(math.radians(fov_deg) / 2.0)
    if reverse:
        return f * np.arctan(r / f)
    return f * np.tan(np.minimum(r / f, 1.5))


def optics_compensation(img, fov, reverse=True, orientation=2, center=(960.0, 540.0), dim_size=None):
    """AE Optics Compensation. `fov` in degrees (0 = identity), `center` the view centre in the array's pixel space,
    `dim_size` the (w, h) the FOV is measured against (default: the array; the bake passes the 1920x1080 layer size,
    scaled, because the effect is defined on the layer, not on the tile-grown canvas). Always returns RGBA: pixels that would
    sample outside the array are transparent. Premultiplied internally; bilinear (INTER_LINEAR)."""
    if fov <= 1e-6:
        return img
    h, w = img.shape[:2]
    dw, dh = dim_size or (w, h)
    dim = _fov_dim(dw, dh, orientation)
    cx, cy = center
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xs + 0.5 - cx, ys + 0.5 - cy
    r = np.sqrt(dx * dx + dy * dy)
    rs = optics_source_radius(r, fov, dim, reverse).astype(np.float32)
    k = np.where(r > 1e-6, rs / np.maximum(r, 1e-6), 1.0).astype(np.float32)
    mapx = (cx + dx * k - 0.5).astype(np.float32)
    mapy = (cy + dy * k - 0.5).astype(np.float32)
    pm = premultiply(img if img.shape[2] == 4 else np.concatenate([img, np.ones((h, w, 1), np.float32)], axis=2))
    out = cv2.remap(pm, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return unpremultiply(out)


# ---------------------------------------------------------------------------------------------------------------
# mask
# ---------------------------------------------------------------------------------------------------------------

def ellipse_distance(shape, cx, cy, rx, ry):
    """Approximate signed distance in px from the ellipse (negative inside) at every pixel centre: f / |grad f| with
    f = sqrt((x/rx)^2 + (y/ry)^2) - 1, exact for a circle and within a fraction of a px near the edge of the ellipses used."""
    h, w = shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xs + 0.5 - cx, ys + 0.5 - cy
    g = np.sqrt((dx / rx) ** 2 + (dy / ry) ** 2)
    gs = np.maximum(g, 1e-6)
    gx, gy = dx / (rx * rx) / gs, dy / (ry * ry) / gs
    grad = np.maximum(np.sqrt(gx * gx + gy * gy), 1e-9)
    d = (g - 1.0) / grad
    # at the centre the gradient direction is undefined: fall back to the smaller radius
    return np.where(g < 1e-4, -min(rx, ry), d).astype(np.float32)


def hole_mask(alpha, cx, cy, rx, ry, feather, expansion):
    """`alpha` (H x W, straight) with an AE Subtract ellipse mask cut out: the ellipse (centre `cx, cy`, radii `rx, ry` in
    the array's pixel space) grown by Mask Expansion `expansion` px, edge feathered over `feather` px. The coverage ramps
    smoothly from 0 at feather/2 outside the expanded edge to 1 at feather/2 inside it (AE's feather straddles the
    path); a smoothstep stands in for AE's Gaussian-ish profile. Returns alpha * (1 - coverage)."""
    d = ellipse_distance(alpha.shape[:2], cx, cy, rx, ry) - expansion
    if feather <= 1e-6:
        cover = (d < 0).astype(np.float32)
    else:
        u = np.clip(0.5 - d / feather, 0.0, 1.0)
        cover = u * u * (3.0 - 2.0 * u)
    return (alpha * (1.0 - cover)).astype(np.float32)
