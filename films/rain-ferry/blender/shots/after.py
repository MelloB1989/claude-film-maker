"""After the flash: they stand back to back on the jetty, past each other, Shinza held in his follow-through facing
out over the end of the jetty, Tsuru a few paces nearer the bank facing it, her blade still a hand's breadth out of
its pole. The rain, hung in the air since the freeze, begins to fall again. Half his blade comes spinning down out
of the sky and sticks in the planks between them with a thunk (77.3 s: THUNK into the shot); the focus pulls to it as
it quivers. Then she slides her blade home, and her pole is whole.

The camera is low on the river side of the jetty, side on, as the reference stages it (Tsuru left, Shinza right),
creeping in. rf/duel.py has the world, the cast and the posing; the cast's variants are his sword "broken" (the half a
prop, parts["half"]) and her pole in hand (its handle parts at the cord: parts["handle"]).
"""
from __future__ import annotations

import math

SHOT = {"scene": "after"}

MID = 2.1             # x between them (rf/duel.py END)
CAM = [(0.0, (MID - 0.13, -4.05, 0.42), (MID, 0.0, 0.95)), (4.5, (MID - 0.05, -3.6, 0.38), (MID + 0.01, 0.0, 0.9))]
LENS, FSTOP = 35.0, 2.2
THUNK = 1.2           # s into the shot: the half blade lands (data/mix.json blade_thunk at 77.3)
DROP = 0.9            # s it falls before
SPIN = 2.6            # its turns a second as it falls
LAND = (MID - 0.07, -0.55)  # where its point goes in (x, y)
LEAN = 18.0           # degrees it leans from upright, toward the camera's right
QUIVER = (3.5, 13.0, 3.2)   # degrees, a second, how fast it dies away
RACK = (THUNK + 0.05, 0.45)  # the focus pulls to it: from, over (s)
SHEATH = (0.3, 2.3, 3.3)    # her blade out this far (m), slid home from, to (s)
# Shinza's follow-through (his frame: front -y): the stub out in front at chest height, a little up
FOLLOW = dict(pommel=(0.03, -0.3, 1.1), hilt=(0.04, -0.95, 0.28))
SH_FOLLOW = {"hips": (0.0, 0.0, 6.0), "spine": (6.0, 0.0, -3.0), "chest": (4.0, 0.0, -2.0), "neck": (-4.0, 0.0, 0.0),
             "head": (-4.0, 0.0, 0.0), "leftShoulder": (0.0, 6.0, -4.0), "rightShoulder": (0.0, -6.0, 4.0)}
SH_FEET = {"right": ((-0.13, -0.42, 0.095), (-0.15, -1.2, 0.5), (0.0, 0.0, -8.0)),
           "left": ((0.14, 0.38, 0.13), (0.3, -0.8, 0.5), (20.0, 0.0, 20.0))}
SH_HIPS = (0.0, -0.03, -0.1)
SKY_RIM = (0.6, 0.68, 0.85)


def build(ctx):
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rf import duel, vroid_tsuru

    fps = ctx.fps
    w = duel.world(ctx)
    # the rain falls again: its clock from the schedule's speed (hung at first, up to full by 1.4 s)
    full = 9.5
    duel.rain_clock(ctx, [w["rain"], *w["splashes"]], lambda t: ctx.look.at(t).rain.speed / full)
    actors = duel.cast(ctx, w, {"shinza": {"sword": "broken"}, "tsuru": {"pole": "hand"}})
    if actors.get("rain") is not None:
        pass   # the copy shares the rain's node group, and so its clock
    sh, ts = actors["shinza"], actors["tsuru"]

    # ---- where they stand: back to back
    hands, fingers = duel.shinza_sword(sh["vrm"], FOLLOW["pommel"], FOLLOW["hilt"])
    follow = duel.Pose(at=duel.END["shinza"], yaw=0.0, hips=SH_HIPS, turns=SH_FOLLOW, hands=hands, feet=SH_FEET)
    duel.apply(sh, follow, fingers=fingers)
    ts["root"].location = (*duel.END["tsuru"], 0.0)
    ts["root"].rotation_euler = (0.0, 0.0, math.pi)
    bpy.context.view_layer.update()

    # ---- her blade slid home: the handle (its blade with it) down the pole, her left hand on it
    handle = ts["parts"]["handle"][0]
    rest = handle.location.copy()
    up = Vector((0.0, 0.0, 1.0))
    if handle.parent is not None:
        up = (handle.parent.matrix_world.to_3x3().inverted() @ up).normalized()
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / fps
        out = SHEATH[0] * (1.0 - duel.ease((t - SHEATH[1]) / (SHEATH[2] - SHEATH[1])) ** 0.7)
        handle.location = rest + up * out
        handle.keyframe_insert("location", frame=f)
    # (the last stretch is a click: no ease into it)
    tch = ts["vrm"]
    if "leftHand-target" in tch.handles:
        tgt = tch.handles["leftHand-target"]
        px, py = vroid_tsuru.POLE
        base = tgt.location.copy()
        for f in range(ctx.f0 - 1, ctx.f1 + 1):
            t = (f - ctx.f0) / fps
            out = SHEATH[0] * (1.0 - duel.ease((t - SHEATH[1]) / (SHEATH[2] - SHEATH[1])) ** 0.7)
            on = duel.ease((t - (SHEATH[1] - 0.8)) / 0.6) * (1.0 - duel.ease((t - SHEATH[2] - 0.2) / 0.6))
            grip = tch.to_armature((px + 0.03, py - 0.02, vroid_tsuru.SPLIT + 0.06 + out))
            tgt.location = base.lerp(grip, on)
            tgt.keyframe_insert("location", frame=f)

    # ---- the half blade: out of the sky, spinning, into the planks; it quivers
    half = sh["parts"]["half"][0]
    bpy.context.view_layer.update()
    co = np.array([half.matrix_world @ v.co for v in half.data.vertices])
    rings = co.reshape(-1, 4, 3).mean(axis=1)
    tip = rings[np.argmin(rings[:, 2])]
    root_ = rings[np.argmax(rings[:, 2])]
    length = float(np.linalg.norm(root_ - tip))
    half.parent = None
    # stuck: point 4 cm in at LAND, leaning LEAN toward +x and a little toward the camera
    lean = math.radians(LEAN)
    axis_up = Vector((math.sin(lean), -0.25 * math.sin(lean), math.cos(lean))).normalized()
    have = Vector(root_ - tip).normalized()
    rot = have.rotation_difference(axis_up).to_matrix().to_4x4()
    goal = Vector((LAND[0], LAND[1], -0.04))
    half.matrix_world = Matrix.Translation(goal) @ rot @ Matrix.Translation(-Vector(tip)) @ half.matrix_world
    quiver = bpy.data.objects.new("half-quiver", None)
    ctx.scene.collection.objects.link(quiver)
    quiver.location = goal
    flight = bpy.data.objects.new("half-flight", None)
    ctx.scene.collection.objects.link(flight)
    centre = goal + axis_up * (length / 2)
    flight.location = centre
    bpy.context.view_layer.update()
    quiver.parent = flight
    quiver.matrix_parent_inverse = flight.matrix_world.inverted()
    mw = half.matrix_world.copy()
    half.parent = quiver
    half.matrix_parent_inverse = quiver.matrix_world.inverted()
    half.matrix_world = mw
    side = axis_up.cross(Vector((0.0, -1.0, 0.0))).normalized()     # it quivers across the camera's view
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / fps
        dt = THUNK - t
        if dt > 0:
            # falling: from above the frame, drifting in from the left, turning end over end in the camera's plane
            flight.location = centre + Vector((-0.5 * dt, 0.0, 0.5 * 9.8 * dt * dt * (DROP / max(DROP, 1e-6))))
            flight.rotation_euler = (0.0, -2 * math.pi * SPIN * dt, 0.0)
            quiver.rotation_euler = (0.0, 0.0, 0.0)
        else:
            flight.location = centre
            flight.rotation_euler = (0.0, 0.0, 0.0)
            a = math.radians(QUIVER[0]) * math.exp(-QUIVER[2] * -dt) * math.sin(2 * math.pi * QUIVER[1] * -dt)
            quiver.rotation_euler = (a * side.x, a * side.y, 0.0)
        hidden = dt > DROP
        half.hide_render = half.hide_viewport = hidden
        for ob, path in ((flight, "location"), (flight, "rotation_euler"), (quiver, "rotation_euler"),
                         (half, "hide_render"), (half, "hide_viewport")):
            ob.keyframe_insert(path, frame=f)
    duel.hold_constant(half)

    # ---- the camera: low, side on, creeping in; the focus on them, then pulled to the blade
    cam, aim = duel.camera(ctx, fstop=FSTOP)
    cam.data.lens = LENS
    fo = duel.focus(ctx, cam)
    figures = Vector((MID, 0.0, 1.2))
    cams = {}
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / fps
        c = duel.keys_at([(k, v) for k, v, _ in CAM], t)
        a = duel.keys_at([(k, v) for k, _, v in CAM], t)
        cam.location, aim.location = c, a
        cam.keyframe_insert("location", frame=f)
        aim.keyframe_insert("location", frame=f)
        k = duel.ease((t - RACK[0]) / RACK[1])
        fo.location = figures.lerp(goal + axis_up * 0.25, k)
        fo.keyframe_insert("location", frame=f)
        cams[f] = c
    duel.outlines(ctx, {"shinza": sh, "tsuru": ts}, lambda f: cams[f], lambda f: LENS)

    # the sky's rim on them from above, the bank's side in shade
    duel.composite(ctx, actors, lambda f: dict(rims=[((0.2, 1.0), SKY_RIM, 0.22, 0.002, 0.8)],
                                                para_from=(0.5, 0.75), para_to=(0.5, 0.15)))
