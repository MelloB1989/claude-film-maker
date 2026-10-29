"""A test of the weather kit after the rain (blender/lib/weather.py), not a shot of the film: 25 light's 5 s on the
jetty, the camera low by the bank looking out across the river with the low sun off to its left, shafts of it breaking through the lifting
mist (weather.sun_beams) and a warm volumetric haze in the air (weather.haze) that the light scatters in, the beams
brightening in as the cloud opens.

    blender -b -P blender/render.py -- --film rain-ferry --shot _cinematest_light --mode look --engine eevee \\
        --frames 2404,2440,2476,2520 --res 960x540
"""
from __future__ import annotations

SHOT = {"scene": "light"}

SUN = (-0.25, -0.9, -0.35)        # rf/set_weather.py "after": the key sun's travel
BEAMS_FROM = (14.0, 72.0, 30.0)   # where the light breaks through, low over the river down the valley
WARM = (1.0, 0.8, 0.55)


def build(ctx):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, toon, weather
    from rf import set_world, sets

    scene = ctx.scene
    world = set_world.build(ctx, weather="after")
    toon.ink("ink-near", world["near"], radius=0.0042, crease=150)
    rig = cinema.film(ctx, [
        cinema.Setup("down-river", 0.0, cinema.drift(cinema.push((-6.0, -4.5, 1.6), (30.0, 19.5, 5.0), 1.4), 0.03),
                     lens=28, fstop=5.6, focus=(1.5, 2.0, 0.6), shake=cinema.Shake(breath=0.05)),
    ], clip=(0.02, 4000.0))
    weather.storm(ctx, rig, rain=0.0, mist=0.7, ground=sets.WATER_Z)
    weather.haze(ctx, rig, density=0.012, color=(0.95, 0.85, 0.7), anisotropy=0.55)
    weather.sun_beams("beams", BEAMS_FROM, SUN, spread=(34.0, 12.0), length=95.0, count=9, width=(2.0, 7.0),
                      color=WARM, strength=0.55)
    for f, v in ((ctx.f0, 0.25), (ctx.f0 + round(2.5 * ctx.fps), 1.0)):    # the cloud opening
        scene["beams"] = v
        scene.keyframe_insert('["beams"]', frame=f)
    print(f"_cinematest_light: key {world['key'].data.energy:.2f}, haze, beams from {BEAMS_FROM}")
