"""The caption-band gate: no graphic in the bottom 15 % of the frame.

    python3 bandcheck.py <out.json> <shot>=<dir>[@<limit>] ...

(@918 for a panel shot, which plays flat: its frosted card ends at y 915.)

Each dir holds PNG frames of a shot rendered over black (the film explain-netflix-black: no studio, the diagram alone, laid out
flat). A frame passes when nothing in rows y >= LIMIT stands out of its surroundings by more than THR: the test is on
the high-passed brightness (the brightest channel minus its 41 px box blur), so a mark, an edge or a letter fails it
while the smooth haze the bloom and halation lay over the whole frame (up to ~90/255 in red under a bright bar) does not. LIMIT is
900, not 918 (0.85 x 1080): the full-frame shots play on a 3D stage whose camera dollies in by up to 2.6 %, which moves
a point at y 900 to about 909 on screen. Writes {"gate": {"gfx.caption_band_clear": {"value": 0|1, "where": ...}},
"shots": {shot: {"frames": n, "fail": [names], "max": v}}}.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

LIMIT, THR = 900, 24
R = 20


def highpass(L: np.ndarray) -> np.ndarray:
    """L minus its (2R+1)^2 box blur (edges clamped), via an integral image."""
    P = np.pad(L, R + 1, mode='edge').astype(np.float64)
    S = P.cumsum(0).cumsum(1)
    h, w = L.shape
    k = 2 * R + 1
    box = (S[k:k + h, k:k + w] - S[:h, k:k + w] - S[k:k + h, :w] + S[:h, :w]) / (k * k)
    return L - box
out = Path(sys.argv[1])
res, bad = {}, []
for arg in sys.argv[2:]:
    shot, d = arg.split('=', 1)
    d, _, lim = d.partition('@')
    lim = int(lim or LIMIT)
    fails, mx, n = [], 0, 0
    for p in sorted(Path(d).glob('*.png')):
        a = np.asarray(Image.open(p).convert('RGB')).astype(np.float64)
        y0 = lim * a.shape[0] // 1080
        L = a[max(0, y0 - 2 * R):].max(axis=2)
        m = int(max(0.0, highpass(L)[y0 - max(0, y0 - 2 * R):].max()))  # brighter than around it: a mark in the band
        mx, n = max(mx, m), n + 1
        if m > THR:
            fails.append(p.name)
    res[shot] = {'frames': n, 'fail': fails, 'max': mx, 'limit_y': lim}
    if fails or n == 0:
        bad.append(shot)
gate = {'value': 0 if bad else 1,
        'where': f'films/explain-netflix: every 3rd frame over black, rows y >= {LIMIT}/1080 (918 for panels): high-passed brightness <= {THR}/255' + (f'; FAIL: {", ".join(bad)}' if bad else '')}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({'gate': {'gfx.caption_band_clear': gate}, 'shots': res}, indent=2) + '\n')
print(json.dumps(gate))
