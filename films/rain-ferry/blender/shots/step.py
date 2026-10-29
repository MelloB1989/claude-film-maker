"""Shot 3, step (10-12.5 s): at the level of the ground, a straw sandal comes down into a puddle on the path. The
splash (on the sound, 10.2 s) throws water up round it, rings run out across the puddle and break the sky and the
hakama's hem mirrored in it; the weight comes onto the foot, the heel rises and the foot peels up out of the water,
dripping, and goes on past us, the other leg sweeping by the lens out of focus. The rings settle, the rain goes on
ringing the water. Low, close and tactile: the lens a hand's height off the water, looking up the path into the mist.

The path, the walk, the sandals and the water are rf/approach.py's (stand-ins until the sets, anim, cast and cinema
agents' are merged).
"""
from __future__ import annotations

import math

SHOT = {"scene": "step"}

STRIKE = 0.2                   # s into the shot: the right foot lands in the puddle (the splash's sound at 10.2 s)
CAM = ((-0.62, -1.02, 0.075), (-0.57, -0.94, 0.072))   # the lens, a hand off the water to his right, easing in
LOOK = (0.05, 0.25, 0.16)      # the aim, from where the foot lands: a little beyond it and up the path
LENS, FSTOP = 32.0, 2.0
SHAKE = (0.0035, 0.18)         # the lens shaken by the footfall: metres at its peak, dying over seconds
KEY = (-0.5, -0.7, 0.9)        # his key: overcast from above our shoulder
RIMS = [((0.4, 1.0), (0.6, 0.68, 0.85), 0.35, 0.0035, 0.9), ((1.0, 0.1), (0.5, 0.55, 0.65), 0.15, 0.003, 0.9)]


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    import numpy as np
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import rig, satsuei, toon
    from rf import approach

    px, py, _, _, _ = approach.PUDDLES[0]
    st = approach.stage(ctx, rain_box=((px - 3.0, py - 1.6, -0.1), (px + 3.0, py + 12.0, 3.0)), rain_near=1.5,
                        rain_clear=0.25, key_toward=KEY, fog=(5.0, 160.0, 0.92, 0.55))
    ch = st.shinza["vrm"]
    t0 = ctx.time(ctx.f0)
    t_strike = t0 + STRIKE
    # his right foot's line runs through the puddle's middle: the footfall lands a little behind it (the ball, not the
    # heel, over the deepest water)
    gait = approach.Gait(origin=(px + 0.1, py + 0.06), dir=(0.0, -1.0), t0=t_strike, step=0.62, stride=0.7)
    frames = list(range(ctx.f0 - 1, ctx.f1 + 1))
    approach.key_walk(ch, gait, frames, ctx.fps)
    vrm_face = st.shinza["face"](1.0)
    from lib import vrm
    vrm.express(ch, vrm_face)

    # the water: the splash and its rings as the foot lands, smaller rings and drips from the sole as it lifts out
    _, _, land = gait.footfall(0)
    ankle = float(ch.rest("rightFoot")[2])
    ball = abs(float((ch.rest("rightToes") - ch.rest("rightFoot"))[1])) if ch.has("rightToes") else 0.12
    hit = (land[0], land[1] - 0.05, 0.004)
    approach.splash("splash", hit, t_strike, ctx.fps, coll=st.cast, frames=frames, count=90, seed=3)
    approach.ripples("rings", hit, t_strike, ctx.fps, coll=st.set["near"], frames=frames, rings=4, squash=0.95)
    lift = t_strike + gait.stance * 2 * gait.step
    toe = (land[0], land[1] - ball, 0.004)
    approach.ripples("rings-lift", toe, lift - 0.05, ctx.fps, coll=st.set["near"], frames=frames, rings=2, speed=0.22,
                     alpha=0.4)

    def sole(t):
        a, _ = gait.foot("right", t, ankle, ball)
        return [(a[0] + dx, a[1] + dy, a[2] - ankle + 0.004) for dx, dy in ((-0.03, -0.1), (0.03, -0.05), (0.0, 0.05),
                                                                           (-0.025, 0.0))]

    approach.drips("sole-drips", None, lift - 0.1, lift + 0.6, ctx.fps, coll=st.cast, frames=frames,
                   every=(0.12, 0.3), fall=0.4, size=0.0035, carry=sole, seed=11)
    toon.splashes("splash-path", (px - 2.0, py - 1.2, 0.006), (px + 2.0, py + 8.0, 0.006), count=320, size=0.05,
                  seed=5)
    toon.splashes("splash-puddle", (px - 0.35, py - 0.25, 0.005), (px + 0.35, py + 0.25, 0.005), count=14, size=0.035,
                  alpha=0.45, seed=6)

    cam = rig.engine_camera("camera", fstop=FSTOP, size=ctx.size)
    cam.data.lens = LENS
    cam.data.clip_start = 0.01
    cam.data.clip_end = 3000.0
    ctx.scene.camera = cam
    aim = bpy.data.objects.new("aim", None)
    ctx.scene.collection.objects.link(aim)
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"
    focus = bpy.data.objects.new("focus", None)
    ctx.scene.collection.objects.link(focus)
    focus.location = (hit[0], hit[1], 0.05)
    cam.data.dof.focus_object = focus
    rng = np.random.default_rng(2)
    jitter = rng.normal(0, 1, (len(frames), 3))
    target = Vector((hit[0] + LOOK[0], hit[1] + LOOK[1], LOOK[2]))
    comp = satsuei.setup(ctx.scene, st.cast)
    for i, f in enumerate(frames):
        u = ctx.time(f) - t0
        k = ease(u / (ctx.f1 - ctx.f0) * ctx.fps)
        at = Vector(tuple(a + (b - a) * k for a, b in zip(*CAM)))
        dt = ctx.time(f) - t_strike
        shake = SHAKE[0] * math.exp(-dt / SHAKE[1]) if dt >= 0 else 0.0
        cam.location = at + Vector(tuple(jitter[i] * shake * np.array([0.4, 0.4, 1.0])))
        aim.location = target
        cam.keyframe_insert("location", frame=f)
        aim.keyframe_insert("location", frame=f)
        s = ctx.look_at(f)
        comp.key(f, s.look(rims=[satsuei.Rim(*r) for r in RIMS], para_from=(0.5, 1.0), para_to=(0.5, 0.3)))
    comp.hold()
    print(f"step: foot lands at {tuple(round(v, 3) for v in hit)} at {t_strike:.2f} s, lifts at {lift:.2f} s")
