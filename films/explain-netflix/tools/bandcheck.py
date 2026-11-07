"""The caption-band gate: no graphic in the bottom 15 % of the frame.

    python3 bandcheck.py <out.json> <shot>=<dir> [<shot>=<dir> ...]

Each dir holds PNG frames of a shot rendered over black (VITE_NF_MATTE=black: no studio, the diagram alone, laid out
flat). A frame passes when no pixel in rows y >= LIMIT is brighter than THR (a faint bloom spill is allowed). LIMIT is
900, not 918 (0.85 x 1080): the full-frame shots play on a 3D stage whose camera dollies in by up to 2.6 %, which moves
a point at y 900 to about 909 on screen. Writes {"gate": {"gfx.caption_band_clear": {"value": 0|1, "where": ...}},
"shots": {shot: {"frames": n, "fail": [names], "max": v}}}.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

LIMIT, THR = 900, 40
out = Path(sys.argv[1])
res, bad = {}, []
for arg in sys.argv[2:]:
    shot, d = arg.split('=', 1)
    fails, mx, n = [], 0, 0
    for p in sorted(Path(d).glob('*.png')):
        a = np.asarray(Image.open(p).convert('RGB'))
        band = a[LIMIT * a.shape[0] // 1080:, :, :]
        m = int(band.max())
        mx, n = max(mx, m), n + 1
        if m > THR:
            fails.append(p.name)
    res[shot] = {'frames': n, 'fail': fails, 'max': mx}
    if fails or n == 0:
        bad.append(shot)
gate = {'value': 0 if bad else 1,
        'where': f'films/explain-netflix: frames over black, rows y >= {LIMIT}/1080 max <= {THR}/255' + (f'; FAIL: {", ".join(bad)}' if bad else '')}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({'gate': {'gfx.caption_band_clear': gate}, 'shots': res}, indent=2) + '\n')
print(json.dumps(gate))
