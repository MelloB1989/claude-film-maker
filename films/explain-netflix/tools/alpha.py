"""Straight-alpha PNGs from a black pass and a grey pass of the same frames (the films explain-netflix-black and explain-netflix-grey).

    python3 alpha.py <black_dir> <grey_dir> <out_dir> [grey_level=90]

Over black a pixel shows its premultiplied colour B; over grey (level k/255) it shows B + (1 - a) * k, so coverage
a = 1 - (G - B) / k (mean of the channels). Light added by the glow and the bloom has no coverage of its own; it is kept
as coverage max(a, max(B)), which composites close to the 'add' it was drawn with. The colour is B / a (straight).
Files pair by sorted name.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

bdir, gdir, odir = map(Path, sys.argv[1:4])
k = (int(sys.argv[4]) if len(sys.argv) > 4 else 90) / 255.0
odir.mkdir(parents=True, exist_ok=True)
bs, gs = sorted(bdir.glob('*.png')), sorted(gdir.glob('*.png'))
assert len(bs) == len(gs) and bs, f'{len(bs)} black vs {len(gs)} grey frames'
for i, (bp, gp) in enumerate(zip(bs, gs)):
    B = np.asarray(Image.open(bp).convert('RGB'), dtype=np.float32) / 255.0
    G = np.asarray(Image.open(gp).convert('RGB'), dtype=np.float32) / 255.0
    a = 1.0 - (G - B).mean(axis=2) / k
    a = np.clip(np.maximum(a, B.max(axis=2)), 0.0, 1.0)
    a[a < 2.0 / 255.0] = 0.0
    rgb = np.where(a[..., None] > 0, B / np.maximum(a[..., None], 1e-6), 0.0)
    out = np.dstack([np.clip(rgb, 0, 1), a])
    Image.fromarray((out * 255.0 + 0.5).astype(np.uint8), 'RGBA').save(odir / f'{i:05d}.png')
print(f'{len(bs)} frames -> {odir}')
