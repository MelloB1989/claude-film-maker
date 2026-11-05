"""A test of the water (blender/lib/water.py) in the jetty set in the downpour, not a shot of the film: three setups
over the standoff's window, a low wide over the water toward the jetty and the boat, the crossing from up the bank, and
a close on a pile's foot where the rain rings round it.

    blender -b -P blender/render.py -- --film rain-ferry --shot _water --mode look --engine eevee \\
        --frames 1440,1480,1520 --res 960x540
"""
from __future__ import annotations

SHOT = {"scene": "standoff"}

SETUPS = (("low", 0.0, (-1.5, -7.8, 0.55), (4.0, 1.5, 0.2), 28.0),
          ("high", 1.5, (-15.5, -11.5, 3.6), (2.0, 4.0, 0.0), 26.0),
          ("pile", 3.0, (0.8, -4.2, 0.35), (2.5, -1.1, -0.4), 45.0))


def build(ctx):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, toon, weather
    from rf import set_world, sets

    scene = ctx.scene
    world = set_world.build(ctx)
    toon.ink("ink-near", world["near"], radius=0.0042, crease=150)
    rig = cinema.film(ctx, [cinema.Setup(name, t, cinema.push(cam, aim, 0.0), lens=lens, fstop=8.0, focus=aim)
                            for name, t, cam, aim, lens in SETUPS], clip=(0.02, 4000.0))
    deck = ((sets.SPAN[0], -sets.HALF + 0.05, 0.004), (sets.SPAN[1], sets.HALF - 0.05, 0.004))
    river = ((-8.0, -8.0, sets.WATER_Z + 0.002), (12.0, -1.15, sets.WATER_Z + 0.002))
    weather.storm(ctx, rig, splashes=[deck, river], waters=world["waters"], floor=sets.WATER_Z, ground=sets.WATER_Z,
                  strikes=[])
    scene.render.use_motion_blur = False
