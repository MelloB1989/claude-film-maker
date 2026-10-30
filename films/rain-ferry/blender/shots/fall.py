"""The fall: Shinza's medium close-up, still held in his follow-through, the rain running down his face, his eyes
gone wide. His headband, cut through at the knot in the flash, gives (CUT) and slips off his head, down past his
cheek and shoulder, and drops to the planks (it lands at BAND_DOWN, the vermilion the last colour in the frame). His
arms come down (ARMS), the stub of his blade hanging from his right hand, and his knees give: he drops to them, and
they hit the wood on the cue (83.8 s: KNEES into the shot); the camera sinks with his head, jolted on the impact, and
he stays there, slumped, in the rain.

The camera is in front of him and to his right, the hut and its lantern far behind him at the left of the frame.
"""
from __future__ import annotations

import math

SHOT = {"scene": "fall"}

AT = (7.2, 0.08)              # where he stands and kneels (rf/clash.py END, FALL)
CUT, BAND_OFF, BAND_DOWN = 0.45, 1.7, 2.25    # s: the knot gives; the band is off his head; it lands on the planks
KNEES = 3.2                   # s: his knees hit the planks (data/mix.json kneel at 83.8)
DROP = 0.55                   # s the drop takes
LENS, FSTOP = 50.0, 2.0
CAM_BEARING = 38.0            # degrees round from his front toward his right (the camera's side)
CAM_DIST = (1.25, 2.1)        # m from his face: the close-up, easing back to a medium as he lands (the band in frame)
CAM_DZ = (-0.04, 0.02)        # m the lens sits off his eyes' height: start, end
DOWN = 0.2                    # m the aim sinks from his eyes once he is down
JOLT = (1.4, 6.0)             # the knees' jolt: degrees, decay a second
# kneeling: the hips down on his heels' height, the shins flat behind the knees, slumped, the head bowed
KNEEL_HIPS = (0.0, 0.12, -0.42)
KNEEL = {"hips": (8.0, 0.0, 0.0), "spine": (14.0, 0.0, 0.0), "chest": (10.0, 0.0, 0.0), "upperChest": (6.0, 0.0, 0.0),
         "neck": (4.0, 0.0, 0.0), "head": (-4.0, 0.0, 6.0),   # staring ahead at nothing
         "leftShoulder": (0.0, 2.0, -4.0), "rightShoulder": (0.0, -2.0, 4.0)}
KNEEL_FEET = {"right": ((-0.13, 0.34, 0.07), (-0.15, -1.0, 0.1), (-75.0, 0.0, 0.0)),
              "left": ((0.13, 0.36, 0.07), (0.15, -1.0, 0.1), (-75.0, 0.0, 0.0))}
# his hands come to rest where his arms reach kneeling, the elbows soft: the right fist by his right knee, the stub's
# broken end on the planks before it; the left hand dropped onto the front of his thigh, fingers hanging over it
KNEEL_STUB = dict(pommel=(-0.168, -0.084, 0.673), hilt=(-0.2, -0.6, -0.77))
# (the left hand's turn from the T-pose: fingers down, palm back onto the thigh)
KNEEL_LEFT = ((0.12, -0.03, 0.62), (0.6, 0.2, 0.6), ((0.0, 1.0, 0.0), (0.0, 0.0, -1.0), (-1.0, 0.0, 0.0)))
# as the knees hit, the hands are a beat behind the body: still up as he lands, through their rest, back to it (m)
HANDS_LAG = ((0.0, 0.06), (0.12, -0.03), (0.35, 0.0))
WIDE = {"surprised": 0.7}     # his eyes gone wide
SKY_RIM, LANTERN_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18)


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    import numpy as np
    from mathutils import Euler, Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, vrm
    from rf import clash

    fps = ctx.fps
    n = ctx.f1 - ctx.f0
    w = clash.world(ctx)
    actors = clash.cast(ctx, w, {"shinza": {"sword": "broken"}})
    sh = actors["shinza"]
    ch = sh["vrm"]
    sh["parts"]["half"][0].hide_render = True     # it is in the planks behind him, out of this shot

    def place(t: float, kneel: bool, lag: float = 0.0):
        if kneel:
            up = np.array((0.0, 0.0, lag))
            hands, fingers = clash.arms(ch, {"pommel": tuple(np.add(KNEEL_STUB["pommel"], up)), "hilt": KNEEL_STUB["hilt"]},
                                        (tuple(np.add(KNEEL_LEFT[0], up)), *KNEEL_LEFT[1:]))
            fingers.update(vrm.grip_pose("left", 0.3, 0.2))
            p = clash.Pose(at=AT, hips=KNEEL_HIPS, turns=KNEEL, hands=hands, feet=KNEEL_FEET)
        else:
            p, fingers = clash.standing(sh, low=True)
        clash.apply(sh, p, fingers=fingers)
        clash.key(sh, ctx.f0 + round(t * fps))

    # standing as the after left him, his arms down, then the knees giving (the hips' fall eased in: he drops)
    place(-0.05, False)
    face0 = sh["face"](1.0)
    band = clash.loose_headband(sh)
    place(KNEES - DROP, False)
    for dt, lag in HANDS_LAG:
        place(KNEES + dt, True, lag)
    place(n / fps + 0.05, True)
    # the drop accelerates into the knees: no ease out of the fall
    from lib import toon

    knees_f = ctx.f0 + round(KNEES * fps)
    for owner in [ch.armature, *ch.handles.values(), sh["root"]]:
        a = getattr(owner, "animation_data", None)
        if a is None or a.action is None:
            continue
        for fc in toon._fcurves(a.action):
            for kp in fc.keyframe_points:
                if abs(kp.co.x - (knees_f - round(DROP * fps))) < 0.5:
                    kp.interpolation = "QUAD"
                    kp.easing = "EASE_IN"
    # his face: wide eyes from the start, then a flinch at the knees
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / fps
        k = 1.0 - 0.5 * clash.ease((t - KNEES) / 0.4)
        weights = dict(face0)
        try:
            vrm.express(ch, {**{e: v * 0.3 for e, v in weights.items()}, **{e: v * k for e, v in WIDE.items()}}, frame=f)
        except KeyError:
            vrm.express(ch, weights, frame=f)

    # ---- the headband: the knot gives, it slides back and down off his head, past his cheek, and drops
    bpy.context.view_layer.update()
    start = band.matrix_world.copy()
    p0 = start.translation.copy()
    r0 = start.to_euler()
    yaw = sh["root"].rotation_euler.z
    fwd = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    side = Vector((-math.sin(yaw), math.cos(yaw), 0.0))     # his left
    land = Vector((*clash.FALL["headband"], 0.012))
    path = [(0.0, p0, (0.0, 0.0, 0.0)),
            (CUT, p0, (0.0, 0.0, 0.0)),
            (CUT + 0.45, p0 - fwd * 0.03 - side * 0.04 + Vector((0, 0, -0.06)), (0.0, -0.35, 0.1)),
            (BAND_OFF, p0 + fwd * 0.04 - side * 0.16 + Vector((0, 0, -0.32)), (0.5, -1.1, 0.5)),
            (BAND_DOWN, land, (1.45, -1.45, 1.1))]
    bend = band.modifiers.new("curl", "SIMPLE_DEFORM")
    bend.deform_method = "BEND"
    bend.deform_axis = "Z"
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / fps
        if t < BAND_OFF:
            loc = clash.keys_at([(k, tuple(v)) for k, v, _ in path], t)
            rot = clash.keys_at([(k, v) for k, _, v in path], t)
        else:
            # falling free: gravity's arc from where it left him to the planks
            u = min(1.0, (t - BAND_OFF) / (BAND_DOWN - BAND_OFF))
            a, b = path[-2], path[-1]
            loc = tuple(Vector(a[1]).lerp(b[1], u) + Vector((0.0, 0.0, 0.0)))
            loc = (loc[0], loc[1], a[1].z + (b[1].z - a[1].z) * u * u)
            rot = clash.lerp(a[2], b[2], u)
        band.location = loc
        band.rotation_euler = Euler((r0.x + rot[0], r0.y + rot[1], r0.z + rot[2]))
        band.keyframe_insert("location", frame=f)
        band.keyframe_insert("rotation_euler", frame=f)
        # it loosens from the round of his head and curls as it falls, flattening on the planks
        bend.angle = math.radians(70.0) * clash.ease((t - CUT) / 0.6) * (1.0 - clash.ease((t - BAND_DOWN + 0.1) / 0.3))
        bend.keyframe_insert("angle", frame=f)

    # ---- the camera: on his face, sinking with it (a little behind it: an operator, not a lock), jolted when his
    # knees hit
    bear = yaw - math.radians(CAM_BEARING)
    toward = Vector((math.cos(bear), math.sin(bear), 0.0))
    fs = list(range(ctx.f0 - 1, ctx.f1 + 1))
    # where his face is, read every sixth frame (each frame_set re-evaluates the whole posed cast) and in between
    sample = sorted({*fs[::6], fs[-1], ctx.f0 + round((KNEES - DROP) * fps), ctx.f0 + round(KNEES * fps)})
    seen = []
    for f in sample:
        ctx.scene.frame_set(f)
        seen.append(tuple(ch.face()))
    seen = np.array(seen)
    faces = [Vector([float(np.interp(f, sample, seen[:, i])) for i in range(3)]) for f in fs]
    lag = [faces[0].z]
    for v in faces[1:]:
        lag.append(lag[-1] + (v.z - lag[-1]) * 0.45)
    cams, aims = [], []
    for f, face, z in zip(fs, faces, lag):
        t = (f - ctx.f0) / fps
        k = clash.ease((t - (KNEES - DROP)) / (DROP + 0.6))
        eye = Vector((face.x, face.y, z))
        c = eye + toward * (CAM_DIST[0] + (CAM_DIST[1] - CAM_DIST[0]) * k) + \
            Vector((0.0, 0.0, CAM_DZ[0] + (CAM_DZ[1] - CAM_DZ[0]) * k))
        # the face in the left third, room on the side he looks to; a little head room
        right = (eye - c).cross(Vector((0.0, 0.0, 1.0))).normalized()
        cams.append(tuple(c))
        # once down the frame comes off his face to take him in, his knees on the planks and the band by them
        aims.append(tuple(eye + right * 0.09 + Vector((0.0, 0.0, -0.06 - DOWN * k))))
    rig = cinema.film(ctx, [cinema.Setup("mcu", -1.0 / fps, cinema.path(cams, aims), ease="linear", lens=LENS,
                                         fstop=FSTOP, focus=(ch, "head"),
                                         shake=cinema.Shake(breath=0.08, hits=((KNEES, JOLT[0]),), decay=JOLT[1]))])
    clash.outlines(ctx, {"shinza": sh}, lambda f: rig.pose(f).position, lambda f: LENS)
    clash.weather(ctx, rig, w, actors)

    # the storm's light on him: the sky's rim from above and beyond, the lantern's far behind at the left
    clash.composite(ctx, actors, lambda f: dict(rims=[((-1.0, 0.3), LANTERN_RIM, 0.3, 0.003, 0.9),
                                                     ((0.4, 1.0), SKY_RIM, 0.25, 0.003, 0.9)],
                                                para_from=(0.7, 0.85), para_to=(0.2, 0.12)))
