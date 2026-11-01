"""her_outfit's cloth maps, tileable, as albedo (sRGB), normal (OpenGL, +Y up) and mask (R roughness, G metallic) for
Unreal's Pbr material; the garments' UVs are in metres (her_outfit.py), so tiling = 100 / tile size in cm.

  T_HerRib_*    the top: a fine 1x1 rib knit in cream, 2 cm square. The wales (raised columns of knit V's) run
                along V (up the body, along the sleeves), the purl columns sunk between them. 8 ribs a tile: 2.5 mm a rib.
  T_HerWool_*   the trousers: a worsted wool suiting, 2/2 twill in a charcoal melange, 1 cm square, 36 ends a tile.

    python3 her_outfit_maps.py --out out/   (numpy + Pillow; no Blender)
"""
import argparse
import os

import numpy as np
from PIL import Image

N = 1024
CREAM = np.array((236, 229, 214)) / 255.0      # sRGB: a warm off-white
CHARCOAL = np.array((44, 44, 48)) / 255.0


def smooth(h, k=3):
    w = np.ones(k) / k
    for ax in (0, 1):
        h = np.apply_along_axis(lambda r: np.convolve(np.r_[r[-(k // 2):], r, r[:k // 2]], w, "valid"), ax, h)
    return h


def normal_map(h, tile_mm, amp_mm):
    px = tile_mm / N
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * amp_mm / (2 * px)
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * amp_mm / (2 * px)
    n = np.stack([-gx, gy, np.ones_like(h)], -1)        # image rows run down: +V is up
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return Image.fromarray(((n * 0.5 + 0.5) * 255).round().astype(np.uint8))


def srgb_image(lin):
    return Image.fromarray((np.clip(lin, 0, 1) ** (1 / 2.2) * 255).round().astype(np.uint8))


def mask_image(r):
    return Image.fromarray((np.stack([r, np.zeros_like(r), np.zeros_like(r)], -1) * 255).round().astype(np.uint8))


def rib(out, rng):
    """1x1 rib: per rib a knit wale (two legs of a V per course, standing proud) and a purl column (sunk, the
    loops' heads seen as small bumps)."""
    RIBS, COURSES = 8, 16                       # per tile (20 mm): a rib 2.5 mm, a course 1.25 mm
    y, x = np.mgrid[0:N, 0:N] / N
    u, v = x * RIBS, (1 - y) * COURSES          # v up
    i, fu = np.floor(u).astype(int), u - np.floor(u)
    j, fv = np.floor(v).astype(int), v - np.floor(v)
    # the knit wale takes 62 % of the rib (the knit stretches over the purl, as worn)
    kw = 0.62
    in_knit = fu < kw
    s = np.where(in_knit, fu / kw, (fu - kw) / (1 - kw))          # 0..1 across the column
    # knit: a V each course, two yarn legs from the column's edges at the top of the course to its centre at the
    # bottom, so a wale reads as a chain of V's; the column rounds down into the purl at its edges
    yarn = lambda d, w: np.sqrt(np.clip(1 - (d / w) ** 2, 0, 1))
    sl, sr = 0.5 - 0.40 * fv, 0.5 + 0.40 * fv
    legs = np.maximum(yarn(s - sl, 0.2), yarn(s - sr, 0.2)) * (0.35 + 0.65 * np.sin(np.pi * fv) ** 0.6)
    knit_h = 0.1 + (0.5 + 0.4 * legs) * np.sin(np.pi * s) ** 0.5
    # purl: the column sunk, little loop heads across it each course
    head = np.clip(1 - ((fv - 0.5) / 0.32) ** 2, 0, 1) * np.sin(np.pi * s) ** 0.7
    purl_h = 0.06 + 0.2 * head
    h = np.where(in_knit, knit_h, purl_h)
    # yarn variation: each wale's tension a touch different, a faint fibre fuzz
    h *= 1 + 0.05 * rng.standard_normal(RIBS + 1)[i % RIBS]
    h += 0.03 * smooth(rng.standard_normal((N, N)), 3)
    h = smooth(h, 3)
    normal_map(h, 20.0, 0.32).save(os.path.join(out, "T_HerRib_N.png"))
    lin = CREAM ** 2.2
    shade = 0.74 + 0.30 * (h - h.min()) / np.ptp(h)
    tone = 1 + 0.025 * rng.standard_normal(RIBS + 1)[i % RIBS]
    srgb_image(lin * (shade * tone)[..., None]).save(os.path.join(out, "T_HerRib_A.png"))
    mask_image(0.88 - 0.06 * (h - h.min()) / np.ptp(h)).save(os.path.join(out, "T_HerRib_M.png"))


def wool(out, rng):
    """2/2 twill, the twill line rising to the right; a melange (fibres of a few greys) in the yarns."""
    ENDS = 36                                   # warp and weft per 10 mm tile
    y, x = np.mgrid[0:N, 0:N] / N
    ui, vi = x * ENDS, (1 - y) * ENDS
    i, fu = np.floor(ui).astype(int), ui - np.floor(ui)
    j, fv = np.floor(vi).astype(int), vi - np.floor(vi)
    warp_up = ((i + j) % 4) < 2
    yarn = lambda t: np.sqrt(np.clip(1 - (2 * t - 1) ** 2, 0, 1))
    t = ((((i + j) % 4) + fv) / 2.0)
    warp_h = yarn(fu) ** 0.8 * np.sin(np.pi * np.clip(t, 0, 1)) ** 0.4
    weft_h = yarn(fv) ** 0.8 * np.sin(np.pi * fu) ** 0.4
    h = np.where(warp_up, 0.35 + 0.65 * warp_h, 0.1 + 0.45 * weft_h)
    # twist: fine diagonal streaks along each yarn
    tw = np.sin((np.where(warp_up, fv, fu) * 6 + np.where(warp_up, fu, fv) * 1.5) * 2 * np.pi)
    h += 0.05 * tw
    h = smooth(h, 3)
    normal_map(h, 10.0, 0.09).save(os.path.join(out, "T_HerWool_N.png"))
    # melange: per-fibre greys, streaked along the yarns
    fib = smooth(rng.standard_normal((N, N)), 3)
    streak = np.where(warp_up, np.repeat(fib[:, ::8], 8, axis=1)[:, :N], np.repeat(fib[::8], 8, axis=0)[:N])
    lin = CHARCOAL ** 2.2
    shade = 0.82 + 0.26 * (h - h.min()) / np.ptp(h)
    mel = 1 + 0.16 * np.clip(streak, -2, 2)
    srgb_image(lin * (shade * mel)[..., None] * np.array((1.0, 1.0, 1.04))).save(os.path.join(out, "T_HerWool_A.png"))
    # worsted has a low sheen on the crowns
    mask_image(0.74 - 0.12 * (h - h.min()) / np.ptp(h)).save(os.path.join(out, "T_HerWool_M.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(11)
    rib(a.out, rng)
    wool(a.out, rng)
    print("her_outfit maps: written to", a.out)


if __name__ == "__main__":
    main()
