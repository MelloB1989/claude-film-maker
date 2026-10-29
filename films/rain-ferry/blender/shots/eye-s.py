"""His eye: an extreme close-up of Shinza's right eye in the 2.39 band, the vermilion headband across the top of the
frame, a wet lock of hair hanging past it, rain beading on his brow and running down past the eye's outer corner.
The heartbeat thumps at +0.15 s (the mix's): the camera breathes in on it and his glare tightens; his eye flicks
once to her and holds (rf/eye_closeup.py).

    blender -b -P blender/render.py -- --film rain-ferry --shot eye-s --mode look --engine eevee \\
        --frames 1539,1560,1586 --res 960x540
"""
from __future__ import annotations

import sys
from pathlib import Path

SHOT = {"scene": "eye-s"}


def build(ctx):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rf import duel_motion as dm
    from rf import eye_closeup as xcu

    def face(t, hb):
        # a hard glare narrowing on the thump and through the shot
        eyes = 1.0 - 0.12 * dm.ease(t / 2.0) - 0.15 * hb
        return {"glare": 1.0, "narrow": min(1.0, max(0.0, (1.0 - eyes) / 0.25))}

    xcu.build(ctx, xcu.Closeup(
        who="shinza", bearing=32.0, height=0.03, lens=100.0, fstop=5.0, lift=0.005, side=-0.006,
        dz=-0.004, beats=(0.15,), face=face, saccades=[(0.55, (0.0, 2.5)), (0.62, (0.0, 1.2))], breath=(0.45, 1.6),
        drops=[xcu.Drop([(0.66, 0.97), (0.65, 0.8), (0.63, 0.62), (0.66, 0.4), (0.68, 0.18), (0.69, 0.0)],
                        start=0.0, length=1.8, size=0.0017),
               xcu.Drop([(0.2, 0.9), (0.19, 0.7), (0.21, 0.45), (0.2, 0.2)], start=0.7, length=1.2, size=0.0012)],
        key=(1.0, 0.95, 0.6), wind=(0.0, -1.0, 0.0),
        look=dict(rims=[((-1.0, 0.3), (1.0, 0.5, 0.18), 0.45, 0.0035, 0.9), ((0.4, 1.0), (0.6, 0.68, 0.85), 0.25, 0.003, 0.9)],
                  para_from=(0.7, 0.85), para_to=(0.2, 0.12), para_amount=0.45, wrap=0.3, wrap_width=0.02)))
