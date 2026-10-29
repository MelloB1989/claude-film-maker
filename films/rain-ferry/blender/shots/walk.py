"""Shot 4, walk (12.5-18 s): Shinza walks down the mountain path out of the mist toward us, the kasa low over his
face, the rain sheeting off its rim. On a long lens from low on the path: the rain between us and him compressed into
a curtain, his silhouette grey in the mist at first and resolving as he comes, the pines either side. A heavy,
purposeful walk; his inner voice (line 1, "I want to be strong.", 14.1-16.91 s) over it, his right hand closing into a
fist as he says it, and at the end his head coming up, the brim lifting off his eyes: the cut to them.

The path, the walk and his kasa are rf/approach.py's (stand-ins until the sets, anim and cast agents' are merged).
"""
from __future__ import annotations

import math

SHOT = {"scene": "walk"}

LENS = (150.0, 165.0)          # mm: a slow creep in over the shot as the camera dollies
CAM = ((0.3, -4.0, 0.95), (0.25, -2.6, 0.95))   # the camera's dolly, low on the path
FSTOP = 2.8
AIM_Z = 1.15                   # the camera aims at his chest, trailing him a little (an operator's follow)
FOLLOW = 0.35                  # s: how far behind him the aim lags
FIRST_STEP = 0.2               # s into the shot his first footfall lands (the steps' sound at 12.7 s)
START_Y = 25.0                 # where his first footfall is
FIST = (1.6, 0.6)              # s into the shot: his right hand closes on "I want to be strong" (from, over)
HEAD_UP = (4.5, 0.9, -9.0)     # ... and his head comes up at its end (from, over, degrees down to up)
# the air between the lens and him: thick in the mist at the far end of the path, thinning as he comes
HAZE = ((27.0, 0.55), (20.0, 0.12))   # (his distance from the lens, the satsuei's haze) at its far and near ends
RIMS = [((0.3, 1.0), (0.6, 0.68, 0.85), 0.3, 0.003, 0.9), ((-1.0, 0.2), (0.6, 0.68, 0.85), 0.18, 0.0025, 0.9)]
KEY = (-0.35, -0.6, 0.8)       # his key: overcast, from above, a little from our side


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import rig, satsuei, toon, vrm
    from rf import approach

    st = approach.stage(ctx, rain_box=((-4.5, -3.0, -0.2), (4.5, 32.0, 6.5)), rain_near=6.0, rain_clear=1.0,
                        key_toward=KEY, fog=(10.0, 260.0, 0.92, 0.55))
    ch = st.shinza["vrm"]
    t_shot = ctx.time(ctx.f0)
    gait = approach.Gait(origin=(0.0, START_Y), dir=(0.0, -1.0), t0=t_shot + FIRST_STEP, step=0.62, stride=0.7)

    def extra(t):
        u = t - t_shot
        fist = ease((u - FIST[0]) / FIST[1])
        head = HEAD_UP[2] * ease((u - HEAD_UP[0]) / HEAD_UP[1])
        out = {"head": (approach.LEAN["head"][0] + head, 0.0, 0.0), "neck": (approach.LEAN["neck"][0] + head * 0.4, 0.0, 0.0)}
        if fist > 0:
            out.update(vrm.blend({}, vrm.grip_pose("right", 1.0, 0.8), fist))
        return out

    frames = list(range(ctx.f0 - 1, ctx.f1 + 1))
    walked = approach.key_walk(ch, gait, frames, ctx.fps, extra=extra)
    vrm.express(ch, st.shinza["face"](1.0))
    toon.splashes("splash-path", (-1.0, -2.0, 0.006), (1.0, 30.0, 0.006), count=900, size=0.07, seed=5)

    cam = rig.engine_camera("camera", fstop=FSTOP, size=ctx.size)
    cam.data.clip_end = 3000.0
    ctx.scene.camera = cam
    aim = bpy.data.objects.new("aim", None)
    ctx.scene.collection.objects.link(aim)
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"
    focus = bpy.data.objects.new("focus", None)
    ctx.scene.collection.objects.link(focus)
    cam.data.dof.focus_object = focus

    comp = satsuei.setup(ctx.scene, st.cast)
    n = ctx.f1 - ctx.f0
    for f in frames:
        k = ease((f - ctx.f0) / n)
        at = Vector(tuple(a + (b - a) * k for a, b in zip(*CAM)))
        cam.location = at
        cam.data.lens = LENS[0] + (LENS[1] - LENS[0]) * k
        lag = gait.root(f / ctx.fps - FOLLOW)
        aim.location = (lag[0] * 0.6, lag[1], AIM_Z)
        r = walked[f][0]
        focus.location = (r[0], r[1], 1.5)
        for ob, path in ((cam, "location"), (aim, "location"), (focus, "location")):
            ob.keyframe_insert(path, frame=f)
        cam.data.keyframe_insert("lens", frame=f)
        # the mist thinning off him as he comes
        d = (Vector((r[0], r[1], 1.2)) - at).length
        (d0, h0), (d1, h1) = HAZE
        haze = h1 + (h0 - h1) * min(1.0, max(0.0, (d - d1) / (d0 - d1)))
        s = ctx.look_at(f)
        comp.key(f, s.look(rims=[satsuei.Rim(*r_) for r_ in RIMS], haze_amount=haze, para_from=(0.5, 0.9),
                           para_to=(0.5, 0.05)))
    comp.hold()
    print(f"walk: {gait.root(ctx.time(ctx.f0))} -> {gait.root(ctx.time(ctx.f1))}, camera {CAM[0]} -> {CAM[1]}")
