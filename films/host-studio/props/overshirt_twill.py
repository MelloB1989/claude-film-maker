"""The overshirt's cloth: a tileable olive cotton twill (2/1, the wale rising to the left as on a right-hand twill),
2 cm square, as albedo (sRGB), normal (OpenGL, +Y up) and mask (R roughness, G metallic) maps for Unreal's Pbr
material.

    python3 overshirt_twill.py --out out/   (numpy + Pillow; no Blender)
"""
import argparse
import os

import numpy as np
from PIL import Image

N = 1024            # pixels across the tile
TILE_MM = 20.0      # the tile's size
WARP = 25           # warp yarns across the tile (0.8 mm apart)
WEFT = 25           # weft yarns down the tile
OLIVE = np.array((86, 92, 58)) / 255.0    # sRGB, from the concept photo's mid-tone


def yarn(t):
    """A yarn's cross profile over one period (0..1): a rounded bump."""
    return np.sqrt(np.clip(1 - (2 * t - 1) ** 2, 0, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(3)
    y, x = np.mgrid[0:N, 0:N] / N
    ui, vi = x * WARP, y * WEFT                    # yarn coordinates
    i, j = np.floor(ui).astype(int), np.floor(vi).astype(int)
    fu, fv = ui - i, vi - j
    # 2/1 twill: the warp floats over two wefts and under one, stepping one weft each warp
    warp_up = ((j - i) % 3) != 2
    # per-yarn variation (slub, twist) so it is cloth, not a pattern
    wthk = 1 + 0.12 * rng.standard_normal(WARP + 1)[i % WARP]
    fthk = 1 + 0.12 * rng.standard_normal(WEFT + 1)[j % WEFT]
    # a warp float runs over two wefts as one long capsule; it dips where it goes under
    t = (((j - i) % 3) + fv) / 2.0
    warp_h = yarn(fu) ** 0.8 * wthk * np.sin(np.pi * np.clip(t, 0, 1)) ** 0.45
    weft_h = yarn(fv) ** 0.8 * fthk * np.sin(np.pi * fu) ** 0.45
    h = np.where(warp_up, 0.35 + 0.65 * warp_h, 0.05 + 0.35 * weft_h)   # the twill line: deep between floats
    # fibre: fine streaks along each yarn
    streak_w = rng.standard_normal((N, N // 4)).repeat(4, axis=1)
    noise = 0.04 * np.where(warp_up, np.roll(streak_w, 0, 0).T[:N, :N], streak_w[:N, :N])
    h = h + noise
    # smooth a touch (2 px box) so the normals are not aliased
    k = np.ones(3) / 3
    for ax in (0, 1):
        h = np.apply_along_axis(lambda r: np.convolve(np.r_[r[-1], r, r[0]], k, "valid"), ax, h)
    # normal (OpenGL): the yarns are ~0.25 mm proud
    px_mm = TILE_MM / N
    amp = 0.18
    gy, gx = np.gradient(h * amp, px_mm)
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * amp / (2 * px_mm)
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * amp / (2 * px_mm)
    n = np.stack([-gx, gy, np.ones_like(h)], -1)   # image rows run down: +V is up
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    Image.fromarray(((n * 0.5 + 0.5) * 255).round().astype(np.uint8)).save(os.path.join(a.out, "T_OvershirtTwill_N.png"))
    # albedo: olive, the yarn crowns a touch lighter, the hollows darker, a slight heather between yarns
    lin = OLIVE ** 2.2
    shade = 0.68 + 0.42 * (h - h.min()) / (h.max() - h.min())
    tone = 1 + 0.05 * np.where(warp_up, rng.standard_normal(WARP + 1)[i % WARP], rng.standard_normal(WEFT + 1)[j % WEFT])
    warmth = np.where(warp_up, 1.0, 0.97)[..., None] * np.array((1.0, 1.0, 0.94))
    col = lin * (shade * tone)[..., None] * warmth
    srgb = np.clip(col, 0, 1) ** (1 / 2.2)
    Image.fromarray((srgb * 255).round().astype(np.uint8)).save(os.path.join(a.out, "T_OvershirtTwill_A.png"))
    # mask: R roughness (crowns slightly smoother from wear), G metallic 0
    r = 0.92 - 0.12 * (h - h.min()) / (h.max() - h.min())
    m = np.stack([r, np.zeros_like(r), np.zeros_like(r)], -1)
    Image.fromarray((m * 255).round().astype(np.uint8)).save(os.path.join(a.out, "T_OvershirtTwill_M.png"))
    print("twill: written to", a.out)


if __name__ == "__main__":
    main()
