"""The flash: one second, the cut, drawn as the best anime draw an impact. A white-out on the clash, then the clash
itself frozen side on (Shinza lunging in from the left, Tsuru's drawn blade meeting his from the right), not painted
but inked: the picture thresholded to stark ink and paper (blender/lib/fx_impact.py ink_panel), flipped negative and
back a few frames at a time (BEATS), focus lines converging on the blades redrawn on twos, splinters of steel and
water bursting out, the camera jolted and pushing in. On the last negative the one glint line of the cut draws
across the frame from the blades, holds, flares, and the frame burns out to white into the after.

The world is lit as a lightning strike lights it (toon.FLASH at 1: the lit bands white, the shades dark), which is
what the threshold turns into ink. Everything drawn over it (lines, shards, the glint) is drawn dark, so it inks
black on the paper beats and white on the negatives; the glint shows only on negatives.
"""
from __future__ import annotations

import math

SHOT = {"scene": "flash"}

CLASH = 1.4                 # x where the blades meet (rf/duel.py CLASH)

# the beats, frame by frame (24 frames): white-out, negative, positive, negative, positive, the long negative the
# glint draws across, and the burn to white
BEATS = [("white", 2), ("neg", 3), ("pos", 2), ("neg", 2), ("pos", 3), ("neg", 10), ("white", 2)]
GLINT = (12, 3, 19, 2)      # frames: starts drawing, frames to cross, flares from, frames of the flare
CAM = ((CLASH - 0.08, -2.75, 0.98), (CLASH - 0.04, -2.35, 0.98))      # from, to (a push in over the second)
AIM = ((CLASH, 0.0, 1.12), (CLASH, 0.0, 1.12))
LENS = (32.0, 36.0)
JOLT = (2, 0.035, 5.5)      # the jolt: on frame, amplitude (frame heights), decay a second
THRESHOLD = 0.24
# the clash (his frame: front -y): a lunge, the blade out level at shoulder height, driving down a little at hers
SH_AT = CLASH - 0.95
SH_POSE = {"hips": (0.0, 0.0, 14.0), "spine": (16.0, 0.0, -6.0), "chest": (8.0, 0.0, -4.0), "upperChest": (4.0, 0.0, 0.0),
           "neck": (-14.0, 0.0, 0.0), "head": (-12.0, 0.0, 0.0),
           "leftShoulder": (0.0, 8.0, -8.0), "rightShoulder": (0.0, -8.0, 8.0)}
SH_HIPS = (0.0, -0.12, -0.2)
SH_FEET = {"right": ((-0.13, -0.66, 0.095), (-0.15, -1.4, 0.5), (0.0, 0.0, -6.0)),
           "left": ((0.15, 0.62, 0.15), (0.35, -0.6, 0.5), (34.0, 0.0, 26.0))}
SH_SWORD = dict(pommel=(0.02, -0.34, 1.12), hilt=(0.0, -0.97, 0.08))
TS_AT = CLASH + 0.62


def build(ctx, only: str | None = None):
    """The shot; `only` keys one beat on every frame (shots/flash_color.py: the picture under the panel)."""
    import bpy
    import numpy as np
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import fx_impact as fx, toon
    from rf import duel

    scene = ctx.scene
    fps = ctx.fps
    n = ctx.f1 - ctx.f0
    w = duel.world(ctx, splashes=False)
    actors = duel.cast(ctx, w, {"shinza": {"sword": "hand"}, "tsuru": {"pole": "drawn"}})
    sh, ts = actors["shinza"], actors["tsuru"]
    hands, fingers = duel.shinza_sword(sh["vrm"], SH_SWORD["pommel"], SH_SWORD["hilt"])
    duel.apply(sh, duel.Pose(at=(SH_AT, 0.0), hips=SH_HIPS, turns=SH_POSE, hands=hands, feet=SH_FEET), fingers=fingers)
    for name, faces in (("shinza", ({"angry": 1.0, "aa": 0.8}, {"glare": 1.0})),):
        ch = actors[name]["vrm"]
        for f_ in faces:
            try:
                from lib import vrm

                vrm.express(ch, f_)
                break
            except KeyError:
                continue
    ts["root"].location = (TS_AT, 0.05, 0.0)
    ts["root"].rotation_euler = (0.0, 0.0, math.pi)
    bpy.context.view_layer.update()

    # lit as a strike lights it, every frame: the threshold's light
    scene[toon.FLASH] = 1.0

    cam, aim = duel.camera(ctx, fstop=4.0)
    cam.data.dof.use_dof = False          # a drawn panel: everything sharp, the lines and splinters over it too
    fo = duel.focus(ctx, cam)
    fo.location = (CLASH, 0.0, 1.1)
    shake = fx.shake(fx.jolt(n + 2, JOLT[0] + 1, JOLT[1], decay=JOLT[2]), freq=11.0, seed=7)
    for i, f in enumerate(range(ctx.f0 - 1, ctx.f1 + 1)):
        k = duel.ease(i / (n + 1)) ** 0.6
        cam.location = duel.lerp(*CAM, k)
        aim.location = duel.lerp(*AIM, k)
        cam.data.lens = LENS[0] + (LENS[1] - LENS[0]) * k
        for ob, path in ((cam, "location"), (aim, "location"), (cam.data, "lens")):
            ob.keyframe_insert(path, frame=f)
    fx.shake_camera(cam, shake, ctx.f0 - 1)
    duel.outlines(ctx, actors, lambda f: cam.location, lambda f: LENS[1])

    # where the blades meet, on screen (frame heights from the centre)
    scene.frame_set(ctx.f0)
    bpy.context.view_layer.update()
    hit = Vector((CLASH, 0.0, 1.12))
    uv = world_to_camera_view(scene, cam, hit)
    aspect = ctx.size[0] / ctx.size[1]
    centre = ((uv.x - 0.5) * aspect, uv.y - 0.5)

    ink = (0.0, 0.0, 0.0)
    coll = toon.collection("fx")
    depth = 0.6
    # focus lines on the blades, three drawings on twos
    lines = [fx.overlay(f"focus{i}", cam, fx.focus_lines(110, center=centre, inner=0.2, ellipse=(1.6, 1.0),
                                                         jitter=0.9, width=(0.004, 0.02), seed=20 + i),
                        fx.unlit(f"focus{i}", ink), depth=depth, coll=coll) for i in range(3)]
    beats = fx.beats(BEATS, n)
    lined = [ctx.f0 + i for i, b in enumerate(beats) if b in ("pos", "neg")]
    fx.alternate(lines, lined)
    # the splinters, a drawing a frame
    shard_mat = fx.unlit("shards", ink)
    for i, f in enumerate(range(ctx.f0, ctx.f1)):
        if beats[i] not in ("pos", "neg"):
            continue
        t = (i - 1) / fps + 0.04
        tris = np.concatenate([fx.shards(26, t, center=centre, speed=(0.6, 2.2), size=(0.008, 0.03), seed=3),
                               fx.shards(40, t, center=centre, speed=(0.3, 1.3), size=(0.004, 0.012), elongate=(1.0, 2.0),
                                         gravity=0.6, seed=4)])
        ob = fx.overlay(f"shards{i}", cam, tris, shard_mat, depth=depth * 0.99, coll=coll)
        fx.show(ob, [f], ctx.f0 - 1, ctx.f1)
    # the glint: the cut's line from the blades out across the frame, drawn, held, flared
    g0, g_n, g_flare, g_fn = GLINT
    a = np.array(centre) + np.array((-1.4, -0.42))
    b = np.array(centre) + np.array((1.4, 0.42))
    glint_mat = fx.unlit("glint", ink)
    for i in range(g0, n):
        if beats[i] != "neg":
            continue
        draw = min(1.0, (i - g0 + 1) / g_n)
        width = 0.006 + (0.03 * min(1.0, (i - g_flare + 1) / g_fn) if i >= g_flare else 0.0)
        tris = fx.glint(a, b, width, draw=draw)
        if draw >= 1.0:
            tris = np.concatenate([tris, fx.star(centre, 0.05 + 4 * width, rays=4, thin=0.05, turn=0.3)])
        ob = fx.overlay(f"glint{i}", cam, tris, glint_mat, depth=depth * 0.98, coll=coll)
        fx.show(ob, [ctx.f0 + i], ctx.f0 - 1, ctx.f1)

    panel = fx.ink_panel(scene, threshold=THRESHOLD, soft=0.025, edges=1.0)
    for i, f in enumerate(range(ctx.f0, ctx.f1)):
        panel.key(f, only or beats[i])
