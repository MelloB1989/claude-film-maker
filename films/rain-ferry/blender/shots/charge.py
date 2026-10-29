"""The charge: Shinza breaks from the standoff and runs at her down the jetty, his sword swept up over his head,
roaring (line 11, the whole shot), long splashing strides about every half second (the step_puddle cues at 73.35,
73.85, 74.35 s), the water flying from his feet, then the sword thrown back to its height (the whoosh at 74.95 s) and
coming over: cut on its fall.

The camera runs ahead of him low on the river side, a wide lens close in, so he comes on fast and big through the
rain; it rumbles with his strides and is jolted by each, motion-blurred; pale focus lines converge on him on twos,
thickening as he closes. His run is the animation core's charge gait (blender/lib/vrm_anim.py), his hands on the hilt
keyed through it.
"""
from __future__ import annotations

import math

SHOT = {"scene": "charge"}

START, END_X = 1.6, 4.6         # his x: from (rf/clash.py STANDOFF), to about where the cut falls (CLASH less his reach)
LAUNCH = 0.06                   # s before he moves
GAIT = dict(stride=1.0, speed=2.0, first=0.55)    # the core's "charge", a stride every half second (the cues)
SWING = (1.5, 1.8, 2.0)         # s: the sword thrown back from, at its height, coming over
CAM = [(0.0, (START + 2.0, -2.45, 0.55)), (1.0, (START + 2.6, -1.8, 0.62)), (2.0, (END_X + 0.85, -0.95, 0.78))]
LENS, FSTOP = 24.0, 2.8
SHUTTER = 0.5
RUMBLE, JOLT, STEP = 0.004, 0.012, 0.5     # the camera's rumble, its jolt on a stride, the strides' beat (s)
FIRST_STEP = 0.25               # s: the first stride lands (data/mix.json step_puddle at 73.35)
# his frame: front -y, left +x, up z (rf/vroid_shinza.py; lib/vrm.py's turns): where the hilt is
SWORDS = [(0.0, (0.01, -0.16, 0.96), (0.0, -0.91, -0.45)),        # the guard
          (0.3, (0.04, -0.12, 1.58), (0.05, 0.35, 0.94)),         # swept up over his head (jodan)
          (SWING[0], (0.04, -0.12, 1.58), (0.05, 0.35, 0.94)),
          (SWING[1], (0.04, -0.02, 1.62), (0.05, 0.8, 0.6)),      # thrown back
          (SWING[2], (0.03, -0.32, 1.45), (0.0, -0.45, 0.89))]    # coming over
POLES = {"left": (0.6, 0.3, 1.2), "right": (-0.6, 0.2, 1.2)}
REAR = {"spine": (2.0, 0.0, 0.0), "chest": (-6.0, 0.0, 0.0)}      # the trunk rearing back as the sword goes up
DRIVE = {"spine": (22.0, 0.0, 0.0), "chest": (12.0, 0.0, 0.0)}    # ... and driving over
CRY = {"angry": 0.9, "aa": 1.0}
SKY_RIM, LANTERN_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18)


def build(ctx):
    import sys
    from pathlib import Path

    import numpy as np
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import fx_impact as fx, toon, vrm_anim as va
    from rf import clash

    scene = ctx.scene
    fps = ctx.fps
    n = ctx.f1 - ctx.f0
    w = clash.world(ctx, motion_blur=SHUTTER, clear=0.7, near=2.5)
    actors = clash.cast(ctx, w, {"shinza": {"sword": "hand"}, "tsuru": {"pole": "hand"}})
    sh, ts = actors["shinza"], actors["tsuru"]
    ch = sh["vrm"]
    # she waits at her mark, beyond him
    ts["root"].location = (clash.STANDOFF["tsuru"][0], clash.STANDOFF["tsuru"][1], 0.0)
    ts["root"].rotation_euler = (0.0, 0.0, math.pi)
    sh["root"].location = (START, 0.0, 0.0)

    def fr(t):
        return ctx.f0 + t * fps

    p = va.Performance(ch, fps=fps, seed=11)
    p.root(fr(0.0), (START, 0.0, 0.0), yaw=0.0)
    p.walk([(START, 0.0), (END_X + 4.0, 0.0)], fr(LAUNCH), gait=va.GAITS["charge"].but(**GAIT), lead="left",
           swing=(0.0, 0.0))
    for t, pommel, hilt in SWORDS:
        hands, _ = clash.shinza_sword(ch, pommel, hilt, poles=POLES)
        for side, (_, point, along, palm, pole) in hands.items():
            p.grasp(fr(t), side, point, along, palm, pole=pole, ease="out" if t <= SWING[0] else "in")
    p.pose(fr(SWING[0]), {"spine": (14.0, 0.0, 0.0), "chest": (8.0, 0.0, 0.0)}, full=False)
    p.pose(fr(SWING[1]), REAR, full=False, ease="out")
    p.pose(fr(SWING[2]), DRIVE, full=False, ease="in")
    p.express(fr(0.0), {k: 0.0 for k in CRY})
    p.express(fr(0.12), CRY, ease="out")
    p.express(fr(1.76), {k: v * 0.7 for k, v in CRY.items()})
    p.bake(ctx.f0 - 1, ctx.f1 + 1)

    def x_at(f):
        root, _ = p.root_at(f)
        return float(root[0])

    # ---- the water from his feet: a burst each half second from the first stride, where his feet are
    coll = toon.collection("fx")
    water = fx.unlit("thrown-water", tuple(w["state"].rain.color), alpha=0.55, strength=1.1)
    beats = np.arange(FIRST_STEP, 2.0, STEP)
    for i, tc in enumerate(beats):
        fc = round(fr(tc))
        scene.frame_set(fc)
        feet = [ch.point(f"{s}Foot") for s in ("left", "right")]
        at = min(feet, key=lambda v: v.z).copy()     # the foot that is down
        at.z = 0.01
        for f in range(fc, min(ctx.f1, fc + round(0.5 * fps))):
            dt = (f - fc) / fps
            pts, vel = fx.burst(70, dt + 0.5 / fps, origin=tuple(at), up=(1.0, 2.8), out=(0.4, 1.8), seed=40 + i)
            if not len(pts):
                continue
            ob = fx.droplets(f"splash{i}-{f}", pts, vel, water, size=0.01, stretch=0.01, coll=coll)
            fx.show(ob, [f], ctx.f0 - 1, ctx.f1)

    # ---- the camera: running ahead of him, low, jolted by his strides
    cam, aim = clash.camera(ctx, fstop=FSTOP)
    cam.data.lens = LENS
    fo = clash.focus(ctx, cam)
    cams, chest = {}, {}
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / fps
        x = x_at(f)
        c = clash.keys_at(CAM, t, interp=lambda u: u)
        body = Vector((x + 0.25, 0.0, 1.18))
        cam.location, aim.location, fo.location = c, body + Vector((0.12, 0.0, 0.08)), Vector((x, 0.0, 1.3))
        for ob in (cam, aim, fo):
            ob.keyframe_insert("location", frame=f)
        cams[f], chest[f] = c, Vector((x, 0.0, 1.25))
    env = np.full(n + 2, RUMBLE)
    for tc in beats:
        env += fx.jolt(n + 2, round(tc * fps) + 1, JOLT, decay=9.0)
    fx.shake_camera(cam, fx.shake(env, freq=8.0, seed=5), ctx.f0 - 1)
    clash.outlines(ctx, actors, lambda f: cams[f], lambda f: LENS)

    # ---- focus lines on him, on twos, pale as the rain, thickening as he closes; just in front of the focus
    aspect = ctx.size[0] / ctx.size[1]
    pale = fx.unlit("speed-pale", (0.82, 0.85, 0.9), alpha=0.28)
    strong = fx.unlit("speed-strong", (0.86, 0.89, 0.94), alpha=0.5)
    for i, f in enumerate(range(ctx.f0 + round(0.3 * fps), ctx.f1, 2)):
        scene.frame_set(f)
        uv = world_to_camera_view(scene, cam, chest[f])
        centre = ((uv.x - 0.5) * aspect, uv.y - 0.5)
        late = (f - ctx.f0) / fps > 1.3
        tris = fx.focus_lines(90 if late else 60, center=centre, inner=0.42 if late else 0.5, ellipse=(1.0, 1.25),
                              jitter=0.7, width=(0.003, 0.014) if late else (0.002, 0.008), seed=100 + i)
        depth = 0.8 * (Vector(cams[f]) - chest[f]).length
        ob = fx.overlay(f"focus{i}", cam, tris, strong if late else pale, depth=depth, coll=coll)
        fx.show(ob, [f, f + 1], ctx.f0 - 1, ctx.f1)

    # the storm's light: the sky's rim from above and the river, the lantern far behind him at the left
    clash.composite(ctx, actors, lambda f: dict(rims=[((-1.0, 0.3), LANTERN_RIM, 0.35, 0.003, 0.9),
                                                      ((0.4, 1.0), SKY_RIM, 0.28, 0.003, 0.9)],
                                                para_from=(0.6, 0.85), para_to=(0.4, 0.1)))
