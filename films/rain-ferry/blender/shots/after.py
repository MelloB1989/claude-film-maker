"""After the flash: they stand back to back on the jetty, past each other, Shinza held in his follow-through facing
out over the end of the jetty, Tsuru a few paces nearer the bank facing it. The rain, hung in the air since the freeze, begins to fall again. Half his blade comes spinning down out
of the sky and sticks in the planks between them with a thunk (77.3 s: THUNK into the shot); the focus pulls to it as
it quivers. Her blade is already home: her pole stands whole beside her, and she does not move.

The camera is low on the river side of the jetty, side on, as the reference stages it (Tsuru left, Shinza right),
creeping in. rf/clash.py has the world, the cast and the posing; the cast's variants are his sword "broken" (the half a
prop, parts["half"]) and her pole in hand, whole.
"""
from __future__ import annotations

import math

SHOT = {"scene": "after"}

MID = 5.8             # x between them (rf/clash.py END)
CAM = [(0.0, (MID - 0.13, -4.05, 0.42), (MID, 0.0, 0.95)), (4.5, (MID - 0.05, -3.6, 0.38), (MID + 0.01, 0.0, 0.9))]
LENS, FSTOP = 35.0, 2.2
THUNK = 1.2           # s into the shot: the half blade lands (data/mix.json blade_thunk at 77.3)
DROP = 0.9            # s it falls before
SPIN = 2.6            # its turns a second as it falls
LAND = (5.73, -0.55)  # where its point goes in (x, y): rf/clash.py FALL["half"]
LEAN = 18.0           # degrees it leans from upright, toward the camera's right
QUIVER = (3.5, 13.0, 3.2)   # degrees, a second, how fast it dies away
RACK = (THUNK + 0.05, 0.45)  # the focus pulls to it: from, over (s)
# Shinza's follow-through (his frame: front -y): the stub out in front at chest height, a little up
FOLLOW = dict(pommel=(0.03, -0.3, 1.1), hilt=(0.04, -0.95, 0.28))
SH_FOLLOW = {"hips": (0.0, 0.0, 6.0), "spine": (6.0, 0.0, -3.0), "chest": (4.0, 0.0, -2.0), "neck": (-4.0, 0.0, 0.0),
             "head": (-4.0, 0.0, 0.0), "leftShoulder": (0.0, 6.0, -4.0), "rightShoulder": (0.0, -6.0, 4.0)}
SH_FEET = {"right": ((-0.13, -0.42, 0.095), (-0.15, -1.2, 0.5), (0.0, 0.0, -8.0)),
           "left": ((0.14, 0.38, 0.13), (0.3, -0.8, 0.5), (20.0, 0.0, 20.0))}
SH_HIPS = (0.0, -0.03, -0.1)
SKY_RIM = (0.6, 0.68, 0.85)


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema
    from rf import clash

    fps = ctx.fps
    w = clash.world(ctx)
    actors = clash.cast(ctx, w, {"shinza": {"sword": "broken"}, "tsuru": {"pole": "hand"}})
    sh, ts = actors["shinza"], actors["tsuru"]

    # ---- where they stand: back to back
    hands, fingers = clash.shinza_sword(sh["vrm"], FOLLOW["pommel"], FOLLOW["hilt"])
    follow = clash.Pose(at=clash.END["shinza"][0], yaw=clash.END["shinza"][1], hips=SH_HIPS, turns=SH_FOLLOW, hands=hands, feet=SH_FEET)
    clash.apply(sh, follow, fingers=fingers)
    ts["root"].location = (*clash.END["tsuru"][0], 0.0)
    ts["root"].rotation_euler = (0.0, 0.0, clash.END["tsuru"][1])
    bpy.context.view_layer.update()

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
    clash.hold_constant(half)

    # ---- the camera: low, side on, creeping in; the focus on them, then pulled to the blade as it lands
    figures = (MID, 0.0, 1.2)
    rig = cinema.film(ctx, [cinema.Setup("side", 0.0, cinema.line(CAM[0][1], CAM[1][1], CAM[0][2], CAM[1][2]),
                                         lens=LENS, fstop=FSTOP, focus=figures,
                                         racks=(cinema.Rack(RACK[0], tuple(goal + axis_up * 0.25), RACK[1]),),
                                         shake=cinema.Shake(breath=0.05, hits=((THUNK, 0.35),)))])
    clash.outlines(ctx, {"shinza": sh, "tsuru": ts}, lambda f: rig.pose(f).position, lambda f: LENS)
    # the rain falls again (the look schedule's speed: hanging, then falling by 1.4 s)
    clash.weather(ctx, rig, w, actors)

    # the sky's rim on them from above, the bank's side in shade
    clash.composite(ctx, actors, lambda f: dict(rims=[((0.2, 1.0), SKY_RIM, 0.22, 0.002, 0.8)],
                                                para_from=(0.5, 0.75), para_to=(0.5, 0.15)))
