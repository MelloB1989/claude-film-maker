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
OFFSET = (25.0, 20.0, -6.0)       # the camera's place from the opening's (m): a little lower and to the right
PUSH = (60.0, 9.0)                 # how far it moves along its view over the shot, and up (m)
SUN_OPEN = (0.1, 0.25, 3.2)        # the clouds' opening: from this much, starting at, wide open by (s)
BEAMS = 9                          # shafts of light
BEAM_IN = (0.6, 2.8)               # they brighten over these (s)
# the crow: where it flies, in metres from the camera (right, ahead, up), by time (s)
CROW = [(0.3, (-14.0, 10.0, -3.0)), (1.4, (-6.0, 22.0, 0.5)), (2.4, (3.0, 38.0, 4.0)), (3.6, (10.0, 62.0, 8.0)),
        (5.2, (16.0, 95.0, 13.0))]
CROW_SCALE = 1.25


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def beam_material(name: str, scene, seed: float):
    """A shaft of sunlight on a card: the scene's gold (`rf_gold`), added to what is behind it, soft at its sides and
    fading in from the cloud at its top and out into the mist at its foot, its brightness the material's "beam" value
    (keyed) times the clouds' opening (`rf_sun`), stirred by slow noise."""
    import bpy

    from rf import valley

    mat, n = valley._material(name)
    tc = n.N.new("ShaderNodeTexCoord")
    sep = n.new("ShaderNodeSeparateXYZ")
    n.set(sep.inputs[0], tc.outputs["Generated"])
    side = n.math("SUBTRACT", 1.0, n.math("ABSOLUTE", n.math("MULTIPLY_ADD", sep.outputs["X"], 2.0, -1.0)))
    across = n.math("POWER", n.math("MAXIMUM", side, 0.0), 1.6)
    along = n.math("MULTIPLY", n.ramp(sep.outputs["Y"], 0.0, 0.45), n.ramp(sep.outputs["Y"], 1.0, 0.7))
    t = n.clock(scene, 0.05)
    v = n.new("ShaderNodeCombineXYZ")
    n.set(v.inputs["X"], n.math("MULTIPLY", sep.outputs["X"], 3.0))
    n.set(v.inputs["Y"], n.math("MULTIPLY", sep.outputs["Y"], 0.6))
    n.set(v.inputs["Z"], n.math("ADD", t, seed))
    stir = n.ramp(n.noise(v.outputs[0], 2.5, 3.0, 0.5), 0.3, 0.75, to=(0.45, 1.0))
    val = n.N.new("ShaderNodeValue")
    val.name = val.label = "beam"
    val.outputs[0].default_value = 0.0
    k = n.math("MULTIPLY", n.math("MULTIPLY", n.math("MULTIPLY", across, along), stir), n.math("MULTIPLY", val.outputs[0],
                                                                                              n.prop("rf_sun")))
    em = n.new("ShaderNodeEmission")
    n.set(em.inputs["Color"], n.mix(1.0, n.prop("rf_gold", True), (1.4, 1.25, 1.0), "MULTIPLY"))
    n.set(em.inputs["Strength"], k)
    tr = n.new("ShaderNodeBsdfTransparent")
    add = n.new("ShaderNodeAddShader")
    n.L.new(tr.outputs[0], add.inputs[0])
    n.L.new(em.outputs[0], add.inputs[1])
    n.out(add.outputs[0])
    mat.surface_render_method = "BLENDED"
    return mat, val.outputs[0]


def beams(scene, cam, coll, *, count: int = BEAMS, seed: int = 3):
    """Shafts of sunlight from the opening in the cloud (toward the sun, high and far) down onto the valley's floor
    and the river beyond the camera, each a card square to the camera's view. Returns [(object, its strength)]."""
    import bpy
    import numpy as np
    from mathutils import Vector

    from rf import valley

    rng = np.random.default_rng(seed)
    cam = Vector(cam)
    sun = Vector(valley.SUN).normalized()
    top = cam + sun * 5200.0
    out = []
    for i in range(count):
        y = rng.uniform(700.0, 3200.0)
        x = float(valley.river_x(y)) + rng.uniform(-420.0, 520.0)
        foot = Vector((x, y, max(float(valley.height(x, y)), 0.0) + 10.0))
        tip = top + Vector((rng.uniform(-260, 260), 0.0, rng.uniform(-140, 140)))
        along = tip - foot
        mid = (tip + foot) / 2
        across = along.cross(mid - cam).normalized()
        w0, w1 = rng.uniform(40.0, 120.0), rng.uniform(140.0, 340.0)        # at the foot, at the top
        verts = [foot - across * w0, foot + across * w0, tip + across * w1, tip - across * w1]
        me = bpy.data.meshes.new(f"beam{i}")
        me.from_pydata([tuple(v) for v in verts], [], [(0, 1, 2, 3)])
        me.uv_layers.new()
        me.update()
        ob = bpy.data.objects.new(f"beam{i}", me)
        coll.objects.link(ob)
        mat, strength = beam_material(f"beam{i}", scene, float(rng.uniform(0, 50)))
        me.materials.append(mat)
        ob.visible_shadow = False
        out.append((ob, strength, rng.uniform(0.45, 1.0)))
    return out


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    import numpy as np
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import bird, rig, toon
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
    aim0 = aim0 + right * 240.0 + Vector((0, 0, 120.0))
    world = valley.build(scene, cam=tuple(start))

    cam = rig.engine_camera("camera", fstop=8.0, size=ctx.size)
    cam.data.lens = LENS
    cam.data.clip_start, cam.data.clip_end = 0.5, 20000.0
    cam.data.dof.use_dof = False
    scene.camera = cam
    target = bpy.data.objects.new("aim", None)
    scene.collection.objects.link(target)
    tc = cam.constraints.new("TRACK_TO")
    tc.target, tc.track_axis, tc.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"

    shafts = beams(scene, start, world["coll"])

    # the crow: out from over the camera's shoulder, away toward the sun
    s0 = ctx.look_at(ctx.f1 - 1)
    crow = bird.build("crow", look=toon.Look(fog=tuple(s0.light.fog), fog_near=30.0, fog_far=3000.0, fog_max=0.85),
                      scale=CROW_SCALE, beads=0, seed=9)
    toon.ink("ink-crow", crow.coll, radius=0.012, crease=130)
    fps = ctx.fps
    times = [k for k, _ in CROW]
    pts = [start + right * p[0] + flat * p[1] + Vector((0, 0, p[2])) for _, p in CROW]
    n = ctx.f1 - ctx.f0 + 2
    span = (times[-1] - times[0])
    flight = bird.path([tuple(p) for p in pts], max(2, round(span * fps) + 1), bank=0.8)

    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = ctx.time(f) - ctx.time(ctx.f0)
        u = (f - ctx.f0) / max(1, n - 3)
        k = ease(u) * 0.4 + u * 0.6
        at = start + fwd * PUSH[0] * k + Vector((0, 0, PUSH[1] * k))
        cam.location = at
        cam.keyframe_insert("location", frame=f)
        target.location = aim0 + Vector((0, 0, 60.0 * ease(u)))
        target.keyframe_insert("location", frame=f)
        lo, k0, k1 = SUN_OPEN
        sun = lo + (1 - lo) * ease((t - k0) / (k1 - k0))
        valley.key(scene, f, ctx.look_at(f), sun=sun)
        for ob, strength, gain in shafts:
            strength.default_value = 2.2 * gain * ease((t - BEAM_IN[0]) / (BEAM_IN[1] - BEAM_IN[0]))
            strength.keyframe_insert("default_value", frame=f)
        # the crow: flapping out of the frame's edge, then gliding on into the light
        i = int(round((t - times[0]) * fps))
        i = min(max(i, 0), len(flight) - 1)
        p = flight[i]
        crow.place(f, p.location, p.heading, p.pitch * 0.5, p.bank)
        flapping = t < 2.7 or 3.5 < t < 4.1
        pose = bird.flap(bird.beat(t, 3.6), amp=1.0) if flapping else bird.lerp(bird.GLIDE, bird.flap(0.15), 0.2)
        crow.key(f, pose)
    crow.hold()
