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

AT = (7.2, 0.08)              # where he stands (rf/clash.py END)
CUT, BAND_OFF, BAND_DOWN = 0.45, 1.7, 2.25    # s: the knot gives; the band is off his head; it lands on the planks
ARMS = (1.9, 2.7)             # s: his arms come down
KNEES = 3.2                   # s: his knees hit the planks (data/mix.json kneel at 83.8)
DROP = 0.55                   # s the drop takes
LENS, FSTOP = 50.0, 2.0
CAM_BEARING = 38.0            # degrees round from his front toward his right (the camera's side)
CAM_DIST = (1.25, 1.35)       # m from his face: start, end
CAM_DZ = (-0.04, 0.1)         # m the lens sits off his eyes' height: start, end (above him, looking down, once down)
JOLT = (1.4, 6.0)             # the knees' jolt: degrees, decay a second
# his follow-through (shots/after.py), then the kneel (his frame: front -y, left +x)
FOLLOW = dict(pommel=(0.03, -0.3, 1.1), hilt=(0.04, -0.95, 0.28))
SH_FOLLOW = {"hips": (0.0, 0.0, 6.0), "spine": (6.0, 0.0, -3.0), "chest": (4.0, 0.0, -2.0), "neck": (-4.0, 0.0, 0.0),
             "head": (-4.0, 0.0, 0.0), "leftShoulder": (0.0, 6.0, -4.0), "rightShoulder": (0.0, -6.0, 4.0)}
SH_FEET = {"right": ((-0.13, -0.42, 0.095), (-0.15, -1.2, 0.5), (0.0, 0.0, -8.0)),
           "left": ((0.14, 0.38, 0.13), (0.3, -0.8, 0.5), (20.0, 0.0, 20.0))}
SH_HIPS = (0.0, -0.03, -0.1)
# arms down: the stub hanging from the right hand, the left loose at his side
LOW = dict(pommel=(-0.2, -0.16, 0.86), hilt=(0.06, -0.55, -0.83))
LEFT_LOOSE = ((0.22, -0.06, 0.78), (0.6, 0.4, 0.9), (0.0, 10.0, 0.0))
# kneeling: the hips down on his heels' height, the shins flat behind the knees, slumped, the head bowed
KNEEL_HIPS = (0.0, 0.12, -0.42)
KNEEL = {"hips": (8.0, 0.0, 0.0), "spine": (14.0, 0.0, 0.0), "chest": (10.0, 0.0, 0.0), "upperChest": (6.0, 0.0, 0.0),
         "neck": (10.0, 0.0, 0.0), "head": (12.0, 0.0, -4.0),
         "leftShoulder": (0.0, 2.0, -4.0), "rightShoulder": (0.0, -2.0, 4.0)}
KNEEL_FEET = {"right": ((-0.13, 0.34, 0.07), (-0.15, -1.0, 0.1), (-75.0, 0.0, 0.0)),
              "left": ((0.13, 0.36, 0.07), (0.15, -1.0, 0.1), (-75.0, 0.0, 0.0))}
KNEEL_STUB = dict(pommel=(-0.24, -0.2, 0.42), hilt=(0.08, -0.82, -0.56))
KNEEL_LEFT = ((0.2, -0.2, 0.36), (0.6, 0.2, 0.6), (0.0, 20.0, 0.0))
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

    def pose_at(arms: str, kneel: bool):
        if arms == "follow":
            hands, fingers = clash.shinza_sword(ch, FOLLOW["pommel"], FOLLOW["hilt"])
        else:
            stub = KNEEL_STUB if kneel else LOW
            hands, fingers = clash.shinza_sword(ch, stub["pommel"], stub["hilt"])
            left = KNEEL_LEFT if kneel else LEFT_LOOSE
            hands["left"] = ("reach", left[0], left[1], left[2])
            fingers = {k: v for k, v in fingers.items() if not k.startswith("left")}
            fingers.update(vrm.grip_pose("left", 0.35, 0.3))
        return clash.Pose(at=AT, hips=KNEEL_HIPS if kneel else SH_HIPS, turns=KNEEL if kneel else SH_FOLLOW, hands=hands,
                         feet=KNEEL_FEET if kneel else SH_FEET), fingers

    def place(t: float, arms: str, kneel: bool):
        p, fingers = pose_at(arms, kneel)
        clash.apply(sh, p, fingers=fingers)
        clash.key(sh, ctx.f0 + round(t * fps))

    # the follow-through held, the arms coming down, the knees giving (the hips' fall eased in: he drops)
    place(-0.05, "follow", False)
    place(ARMS[0], "follow", False)
    face0 = sh["face"](1.0)
    band = clash.loose_headband(sh)
    place(ARMS[1], "low", False)
    place(KNEES - DROP, "low", False)
    place(KNEES, "low", True)
    place(n / fps + 0.05, "low", True)
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
    faces = []
    for f in fs:
        ctx.scene.frame_set(f)
        faces.append(Vector(ch.face()))
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
        aims.append(tuple(eye + right * 0.09 + Vector((0.0, 0.0, -0.06))))
    rig = cinema.film(ctx, [cinema.Setup("mcu", -1.0 / fps, cinema.path(cams, aims), ease="linear", lens=LENS,
                                         fstop=FSTOP, focus=(ch, "head"),
                                         shake=cinema.Shake(breath=0.08, hits=((KNEES, JOLT[0]),), decay=JOLT[1]))])
    clash.outlines(ctx, {"shinza": sh}, lambda f: rig.pose(f).position, lambda f: LENS)
    clash.weather(ctx, rig, w, actors)

    # the storm's light on him: the sky's rim from above and beyond, the lantern's far behind at the left
    clash.composite(ctx, actors, lambda f: dict(rims=[((-1.0, 0.3), LANTERN_RIM, 0.3, 0.003, 0.9),
                                                     ((0.4, 1.0), SKY_RIM, 0.25, 0.003, 0.9)],
                                                para_from=(0.7, 0.85), para_to=(0.2, 0.12)))
