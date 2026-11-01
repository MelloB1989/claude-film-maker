"""his_outfit's cloth maps, tileable, as albedo (sRGB), normal (OpenGL, +Y up) and mask (R roughness, G metallic) for
Unreal's Pbr material; the trousers' UVs are in metres (his_outfit.py), so tiling = 100 / tile size in cm.
After agent-02's her_outfit_maps.py.

  T_HisTwill_*  the trousers: a fine cotton-wool suiting twill (2/1, the twill line rising to the right) in a charcoal
                melange, 1 cm square, 40 ends a tile, with a soft brushed fuzz over it.
  T_HisHidden   a 4x4 fully transparent map: the default garment's shorts are cut out with it (PbrMasked).

    python3 his_outfit_maps.py --out out/   (numpy + Pillow; no Blender)
"""
import argparse
import os

import numpy as np
from PIL import Image

N = 1024
CHARCOAL = np.array((46, 47, 51)) / 255.0      # sRGB: a cool charcoal, a touch lighter than his tee


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


def twill(out, rng):
    """2/1 twill: each warp end floats over two picks and under one, stepping one pick each end, so the warp floats
    line up in diagonals; a melange of greys in the yarns, a brushed fuzz."""
    ENDS = 40                                   # warp and weft per 10 mm tile
    y, x = np.mgrid[0:N, 0:N] / N
    ui, vi = x * ENDS, (1 - y) * ENDS
    i, fu = np.floor(ui).astype(int), ui - np.floor(ui)
    j, fv = np.floor(vi).astype(int), vi - np.floor(vi)
    warp_up = ((j - i) % 3) < 2
    yarn = lambda t: np.sqrt(np.clip(1 - (2 * t - 1) ** 2, 0, 1))
    t = ((((j - i) % 3) + fv) / 2.0)            # along a float of two picks
    warp_h = yarn(fu) ** 0.8 * np.sin(np.pi * np.clip(t, 0, 1)) ** 0.4
    weft_h = yarn(fv) ** 0.8 * np.sin(np.pi * fu) ** 0.4
    h = np.where(warp_up, 0.35 + 0.65 * warp_h, 0.1 + 0.4 * weft_h)
    # twist: fine diagonal streaks along each yarn
    tw = np.sin((np.where(warp_up, fv, fu) * 5 + np.where(warp_up, fu, fv) * 1.5) * 2 * np.pi)
    h += 0.05 * tw
    fuzz = smooth(rng.standard_normal((N, N)), 5)
    h += 0.06 * fuzz
    h = smooth(h, 3)
    normal_map(h, 10.0, 0.08).save(os.path.join(out, "T_HisTwill_N.png"))
    fib = smooth(rng.standard_normal((N, N)), 3)
    streak = np.where(warp_up, np.repeat(fib[:, ::8], 8, axis=1)[:, :N], np.repeat(fib[::8], 8, axis=0)[:N])
    lin = CHARCOAL ** 2.2
    shade = 0.84 + 0.24 * (h - h.min()) / np.ptp(h)
    mel = 1 + 0.13 * np.clip(streak, -2, 2)
    srgb_image(lin * (shade * mel)[..., None] * np.array((1.0, 1.0, 1.03))).save(os.path.join(out, "T_HisTwill_A.png"))
    # matte cotton-wool, a faint sheen on the crowns
    mask_image(0.8 - 0.1 * (h - h.min()) / np.ptp(h)).save(os.path.join(out, "T_HisTwill_M.png"))


def hidden(out):
    Image.fromarray(np.zeros((4, 4, 4), np.uint8), "RGBA").save(os.path.join(out, "T_HisHidden.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    twill(a.out, np.random.default_rng(17))
    hidden(a.out)
    print("his_outfit maps: written to", a.out)


if __name__ == "__main__":
    main()
