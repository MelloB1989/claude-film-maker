"""Her eye, calm: an extreme close-up of Tsuru's left eye in the 2.39 band, the heavy lid half down over it, the lines
of seventy years round it, a grey strand of wet hair across the frame's edge, a drop running from her brow down the
creases. The heartbeat thumps at +0.15 s (the mix's) and the camera breathes in on it; she does not move. Only at the
end does the lid lift, a little: she is ready (rf/eye_closeup.py).

    blender -b -P blender/render.py -- --film rain-ferry --shot eye-t --mode look --engine eevee \\
        --frames 1587,1610,1634 --res 960x540
"""
from __future__ import annotations

import sys
from pathlib import Path

SHOT = {"scene": "eye-t"}
OPEN = (1.35, 1.75, 0.68)    # s: her lid lifts from, to; how far (rf/vroid_tsuru.py's face: 0.55 calm .. 1 the glare)


def build(ctx):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rf import duel_motion as dm
    from rf import eye_closeup as xcu


    def face(t, hb):
        k = min(1.0, max(0.0, (0.55 + (OPEN[2] - 0.55) * dm.span(t, OPEN[0], OPEN[1]) - 0.55) / 0.45))
        return {"tsuru-calm": 1.0 - k, "tsuru-glare": k}

    xcu.build(ctx, xcu.Closeup(
        who="tsuru", bearing=28.0, height=0.03, lens=100.0, fstop=5.0, lift=0.004, side=0.006,
        dz=-0.003, beats=(0.15,), pulse=0.035, face=face, breath=(0.2, 0.7),
        drops=[xcu.Drop([(0.3, 0.98), (0.31, 0.78), (0.28, 0.6), (0.27, 0.38), (0.3, 0.15), (0.31, 0.0)],
                        start=0.2, length=1.7, size=0.0015)],
        key=(-1.0, 0.35, 0.75), wind=(0.0, 1.0, 0.0),
        look=dict(rims=[((1.0, 0.4), (0.6, 0.68, 0.85), 0.35, 0.0035, 0.9), ((-1.0, 0.2), (0.95, 0.58, 0.26), 0.2, 0.003, 0.9)],
                  para_from=(0.3, 0.85), para_to=(0.8, 0.12), para_amount=0.4, wrap=0.3, wrap_width=0.02)))
