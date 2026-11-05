"""A test of the camera and the weather kits (blender/lib/cinema.py, weather.py) in the jetty set, not a shot of the
film: the board's 5.5 s (the rain thinning out) filmed as two setups. A wide down the jetty toward the hut, its lantern
the one warm point, the camera breathing and pushing in; then a cut to a long lens low on the tap post at the jetty's
end, sharp on its wet top, racking out to the lantern across the deck as the rain gives out to a few last drops, mist
lying over the river and water dripping off the hut's eave.

    blender -b -P blender/render.py -- --film rain-ferry --shot _cinematest --mode look --engine eevee \\
        --frames 2270,2320,2335,2372,2400 --res 960x540
"""
from __future__ import annotations

SHOT = {"scene": "board"}

CUT = 2.6       # s: the wide, then the post
RACK = 3.7      # s: the focus leaves the post for the lantern
RAIN = [(0.0, 1.0), (1.8, 0.85), (4.6, 0.12)]   # heavy, thinning to a last few drops


def build(ctx):
    import sys
    from pathlib import Path

    import bpy

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, toon, weather
    from rf import set_world, sets

    scene = ctx.scene
    world = set_world.build(ctx)
    toon.ink("ink-near", world["near"], radius=0.0042, crease=150)
    # the lantern's mesh is built where it hangs (its origin at the world's): focus on the middle of it
    lantern = cinema.marker(world["lantern"])
    bpy.context.view_layer.update()
    lz = lantern.matrix_world.translation
    post = set_world.anchor(world, "tap_post_top")

    wide_cam, wide_aim = (6.6, -3.0, 1.35), (-5.6, 2.2, 1.25)
    close_cam, close_aim = cinema.frame_on(tuple(post), 0.5, share=0.34, lens=85, bearing=74, rise=0.15, third=1, headroom=-0.12)
    rig = cinema.film(ctx, [
        cinema.Setup("wide", 0.0, cinema.drift(cinema.push(wide_cam, wide_aim, 1.6), 0.03), lens="wide", fstop=4.0,
                     focus=lantern, shake=cinema.Shake(breath=0.12)),
        cinema.Setup("post", CUT, cinema.push(close_cam, close_aim, 0.18), lens=85, fstop=2.0, focus=tuple(post),
                     racks=(cinema.Rack(RACK, lantern, 0.8),), shake=cinema.Shake(breath=0.06, seed=7)),
    ], clip=(0.02, 4000.0))

    deck = ((sets.SPAN[0], -sets.HALF + 0.05, 0.004), (sets.SPAN[1], sets.HALF - 0.05, 0.004))
    river = ((-8.0, -8.0, sets.WATER_Z + 0.002), (12.0, -1.15, sets.WATER_Z + 0.002))
    weather.storm(ctx, rig, rain=RAIN, splashes=[deck, river], waters=world["waters"], floor=sets.WATER_Z,
                  ground=sets.WATER_Z, strikes=[])
    # water running off the hut's eave, either side of the lantern
    weather.drips("eave", weather.edge((lz.x - 1.6, lz.y - 0.15, lz.z + 0.5), (lz.x + 1.6, lz.y - 0.15, lz.z + 0.5), 14),
                  fall=2.4)
    scene.render.use_motion_blur = False
    print(f"_cinematest: cuts {rig.cuts}, post at {tuple(round(v, 2) for v in post)}, lantern at "
          f"{tuple(round(v, 2) for v in lz)}")
