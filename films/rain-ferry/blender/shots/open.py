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


def ease_in(u: float) -> float:
    """A move that starts from rest and keeps going (the push carries on into the cut)."""
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u) * 0.35 + u * 0.65


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import rig, toon
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
    world = valley.build(scene, cam=tuple(start))

    cam = rig.engine_camera("camera", fstop=8.0, size=ctx.size)
    cam.data.lens = LENS
    cam.data.clip_start, cam.data.clip_end = 0.5, 20000.0
    cam.data.dof.use_dof = False    # all of the valley sharp: an establishing view
    scene.camera = cam
    target = bpy.data.objects.new("aim", None)
    scene.collection.objects.link(target)
    tc = cam.constraints.new("TRACK_TO")
    tc.target, tc.track_axis, tc.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"

    # the black: a card filling the lens, lifting
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    black = bpy.context.active_object
    black.name = "fade"
    black.parent = cam
    black.location = (0.0, 0.0, -0.6)
    black.scale = (3.0, 3.0, 1.0)
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
    black.data.materials.append(mat)
    black.visible_shadow = False
    fade = mx.inputs["Fac"]

    # the rain in the air before the lens: a box carried along with the camera (its drops fall in the world's down)
    s0 = ctx.look_at(ctx.f0)
    r = s0.rain
    carrier = bpy.data.objects.new("rain-carrier", None)
    scene.collection.objects.link(carrier)
    rain = toon.rain("rain", (-14.0, 2.0, -12.0), (14.0, 40.0, 10.0), count=max(1, int(r.drops * 1.6)), speed=r.speed,
                     wind=r.wind, length=r.length * 1.6, width=r.width * 1.3, color=r.color, alpha=r.alpha, seed=3,
                     near=6.0, clear=1.5)
    rain.parent = carrier
    carrier.rotation_euler = (0.0, 0.0, math.atan2(-flat.x, flat.y))

    strikes = ctx.look.lightning or (3.3,)
    flash = toon.lightning(scene, list(strikes), range(ctx.f0 - 1, ctx.f1 + 1), ctx.fps, ctx.f0)
    n = ctx.f1 - ctx.f0
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = ctx.time(f) - ctx.time(ctx.f0)
        u = (f - ctx.f0) / max(1, n - 1)
        k = ease_in(u)
        at = start + fwd * PUSH[0] * k + Vector((0, 0, PUSH[1] * k)) + right * DRIFT * ease(u)
        cam.location = at
        cam.keyframe_insert("location", frame=f)
        aim = aim0 + right * DRIFT * ease(u) + Vector((0, 0, math.tan(math.radians(TILT)) * (aim0 - start).length * ease(u)))
        target.location = aim
        target.keyframe_insert("location", frame=f)
        carrier.location = at
        carrier.keyframe_insert("location", frame=f)
        fade.default_value = 1.0 - ease((t - FADE[0]) / (FADE[1] - FADE[0]))
        fade.keyframe_insert("default_value", frame=f)
        # far off: the lightning only lights the clouds, and the drops near the lens a little
        fl = flash.get(f, 0.0)
        scene[toon.FLASH] = 0.35 * fl
        scene.keyframe_insert(f'["{toon.FLASH}"]', frame=f)
        valley.key(scene, f, ctx.look_at(f), sun=0.0, flash=fl)
