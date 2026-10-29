"""25 light: the film's release. The rain has stopped; from the same height over the valley the film opened on
(rf/valley.py), the clouds tear open over the right of it and the sun comes through: beams of gold fall through the
mist onto the river, the water lights up in a path of glitter, the slopes facing the sun take a gold edge, the mist
glows, and the colour comes back into the world (the look schedule warms it over the first two seconds, data/look.json).
The crow crosses the light, flying out from over us toward the sun (its cry at 2.1 s in the mix), small and black
against the gold. The camera rises and pushes slowly in, as the strings and the koto rise.
"""
from __future__ import annotations

import math

SHOT = {"scene": "light", "look": "2412,2440,2462,2490,2520"}

LENS = 28.0
OFFSET = (0.0, 0.0, 0.0)          # the camera's place from the opening's (m): the same view, the film's bookend
PUSH = (60.0, 9.0)                 # how far it moves along its view over the shot, and up (m)
SUN_OPEN = (0.1, 0.25, 3.2)        # the clouds' opening: from this much, starting at, wide open by (s)
BEAMS = 14                         # shafts of light
BEAM_IN = (0.6, 2.8)               # they brighten over these (s)
# the crow: where it flies, in metres from the camera (right, ahead, up), by time (s)
CROW = [(0.3, (-14.0, 10.0, -3.0)), (1.4, (-6.0, 22.0, 0.5)), (2.4, (3.0, 38.0, 4.0)), (3.6, (10.0, 62.0, 8.0)),
        (5.2, (16.0, 95.0, 13.0))]
CROW_SCALE = 1.25


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import bird, cinema, toon, weather
    from rf import valley

    scene = ctx.scene
    scene.render.use_motion_blur = False
    scene.view_settings.view_transform = "Standard"
    scene.eevee.use_raytracing = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 0.0, 0.0, 1)

    base = Vector(valley.camera_location())
    aim0 = Vector(valley.AIM)
    fwd = (aim0 - base).normalized()
    flat = Vector((fwd.x, fwd.y, 0.0)).normalized()
    right = flat.cross(Vector((0, 0, 1)))
    start = base + right * OFFSET[0] + flat * OFFSET[1] + Vector((0, 0, OFFSET[2]))
    # the aim a little toward the sun's side: the opening sits high at the right of the frame
    aim0 = aim0 + right * 60.0 + Vector((0, 0, 40.0))
    world = valley.build(ctx, cam=tuple(start), aim=tuple(aim0))

    end = start + fwd * PUSH[0] + Vector((0, 0, PUSH[1]))
    rig = cinema.film(ctx, [cinema.Setup("vista", 0.0, cinema.drift(cinema.line(start, end, aim0, aim0 + Vector((0, 0, 60.0))),
                                                                    0.3, cycles=0.4),
                                         lens=LENS, fstop=11.0, focus=1500.0, ease="sine",
                                         shake=cinema.Shake(breath=0.02))], clip=(0.5, 20000.0))

    # the beams (lib/weather.py): from where the cloud breaks, high toward the sun, down through the mist onto the
    # river up the valley; scene["beams"] brings them in as it opens
    sun = Vector(valley.SUN).normalized()
    source = start + sun * 2600.0
    floor = Vector((float(valley.river_x(1900.0)), 1900.0, 0.0))
    weather.sun_beams("beams", tuple(source), tuple((floor - source).normalized()), spread=(900.0, 220.0),
                      length=(floor - source).length * 1.05, count=BEAMS, width=(25.0, 160.0),
                      color=tuple(ctx.look_at(ctx.f1 - 1).light.warm), strength=0.2, seed=5, coll=world["coll"])

    # the crow: out from over the camera's shoulder, away toward the sun
    s0 = ctx.look_at(ctx.f1 - 1)
    crow = bird.build("crow", look=toon.Look(fog=tuple(s0.light.fog), fog_near=30.0, fog_far=3000.0, fog_max=0.85),
                      scale=CROW_SCALE, beads=0, seed=9)
    fps = ctx.fps
    times = [k for k, _ in CROW]
    pts = [start + right * p[0] + flat * p[1] + Vector((0, 0, p[2])) for _, p in CROW]
    span = (times[-1] - times[0])
    flight = bird.path([tuple(p) for p in pts], max(2, round(span * fps) + 1), bank=0.8)

    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = ctx.time(f) - ctx.time(ctx.f0)
        lo, k0, k1 = SUN_OPEN
        opening = lo + (1 - lo) * ease((t - k0) / (k1 - k0))
        valley.key(scene, f, ctx.look_at(f), sun=opening)
        scene["beams"] = ease((t - BEAM_IN[0]) / (BEAM_IN[1] - BEAM_IN[0]))
        scene.keyframe_insert('["beams"]', frame=f)
        # the crow: flapping out of the frame's edge, then gliding on into the light
        i = int(round((t - times[0]) * fps))
        i = min(max(i, 0), len(flight) - 1)
        p = flight[i]
        crow.place(f, p.location, p.heading, p.pitch * 0.5, p.bank)
        flapping = t < 2.7 or 3.5 < t < 4.1
        pose = bird.flap(bird.beat(t, 3.6), amp=1.0) if flapping else bird.lerp(bird.GLIDE, bird.flap(0.15), 0.2)
        crow.key(f, pose)
    crow.hold()
