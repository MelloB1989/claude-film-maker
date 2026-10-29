"""1 open: black, then the valley in the rain. Out of the dark the view from high on the slope opens up the valley
(rf/valley.py): ridge after ridge of pine-fringed mountains closing on the river far below, mist lying between them,
the ferry's hut a speck by the water with its red lantern the one warm point in the cold; rain streaks the air between
us and it. The camera pushes slowly in and down toward the river as the rain swells; far up the valley lightning
lights the clouds from inside (the thunder comes later, from far away, at 3.55 s in the mix).

The fade from black is in the plate (a black card before the lens). Its colours, the rain and the mist come from the
look schedule (data/look.json: the cold end of the arc).
"""
from __future__ import annotations

import math

SHOT = {"scene": "open", "look": "0,30,72,100,143", "black_ok": lambda f: f <= 1}

LENS = 30.0
PUSH = (95.0, -14.0)       # how far the camera moves along its view over the shot, and down (m)
DRIFT = 10.0               # ... and to the right (m): a slow crane round toward the river
FADE = (0.0, 1.8)          # s: the black lifts over these
TILT = -1.2                # degrees the aim sinks over the shot (toward the hut, as the push ends)


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, toon, weather
    from rf import valley

    scene = ctx.scene
    scene.render.use_motion_blur = False
    scene.view_settings.view_transform = "Standard"
    scene.eevee.use_raytracing = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 0.0, 0.0, 1)

    start = Vector(valley.camera_location())
    aim0 = Vector(valley.AIM)
    fwd = (aim0 - start).normalized()
    flat = Vector((fwd.x, fwd.y, 0.0)).normalized()
    right = flat.cross(Vector((0, 0, 1)))
    world = valley.build(ctx, cam=tuple(start), aim=tuple(aim0))

    end = start + fwd * PUSH[0] + Vector((0, 0, PUSH[1])) + right * DRIFT
    aim1 = aim0 + right * DRIFT + Vector((0, 0, math.tan(math.radians(TILT)) * (aim0 - start).length))
    rig = cinema.film(ctx, [cinema.Setup("vista", 0.0, cinema.drift(cinema.line(start, end, aim0, aim1), 0.35, cycles=0.4),
                                         lens=LENS, fstop=11.0, focus=1500.0, ease="linear",
                                         shake=cinema.Shake(breath=0.025))], clip=(0.5, 20000.0))
    cam = rig.camera

    # the black: a card filling the lens, lifting
    mat = bpy.data.materials.new("fade")
    nt = toon.nodes(mat)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0, 0, 0, 1)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    black = valley.card("fade", scene.collection, (0.0, 0.0, -0.6), (3.0, 3.0), mat)
    black.parent = cam
    fade = mx.inputs["Fac"]

    # the rain before the lens: the film's (lib/weather.py), as heavy as the schedule says; the far lightning is
    # this shot's own (below: it lights the clouds, barely the land)
    weather.storm(ctx, rig, mist=0, strikes=[])

    strikes = ctx.look.lightning or (3.3,)
    flash = toon.lightning(scene, list(strikes), range(ctx.f0 - 1, ctx.f1 + 1), ctx.fps, ctx.f0)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = ctx.time(f) - ctx.time(ctx.f0)
        fade.default_value = 1.0 - ease((t - FADE[0]) / (FADE[1] - FADE[0]))
        fade.keyframe_insert("default_value", frame=f)
        # far off: the lightning only lights the clouds, and the drops near the lens a little
        fl = flash.get(f, 0.0)
        scene[toon.FLASH] = 0.35 * fl
        scene.keyframe_insert(f'["{toon.FLASH}"]', frame=f)
        valley.key(scene, f, ctx.look_at(f), sun=0.0, flash=fl)
