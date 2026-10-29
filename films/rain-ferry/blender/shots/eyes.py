"""Shot 5, eyes (18-21.5 s): under the brim of his kasa, his eyes. The cut lands on the low drum (18.0 s) with his
head still down, the brim over his eyes; his head comes up and the eyes come out from under it into the light, on
us. His inner voice (line 2, "Stronger than anyone.", 18.5-20.11 s); as it ends his eyes narrow to a glare. An extreme
close-up on a long lens, pushing in slowly, the brim's edge dark across the top of the frame with the rain dripping
off it, the mist and the path behind him gone soft.

The stage is rf/approach.py's (stand-ins until the sets and cast agents' are merged).
"""
from __future__ import annotations

import math

SHOT = {"scene": "eyes"}

AT = (0.0, 2.0)                # where he stands on the path
LENS, FSTOP = 100.0, 2.0
DIST = (0.78, 0.6)             # m from his eyes: the slow push
BEARING = 14.0                 # degrees round from straight in front of him toward his left (our right)
DZ = -0.06                     # the lens this far below his eyes: looking up under the brim
LIFT = 0.006                   # the aim this far over his eyes (they sit a little above the frame's middle)
THIRD = 0.012                  # ... and this far to his right (our left): room on the side he looks past
HEAD = ((0.12, 0.8), (13.0, -2.0))   # his head comes up: (from s, over s), (degrees down at the cut, at the end)
EYES = ((0.25, 0.5), (14.0, -1.0))   # his eyes lift (from, over), (degrees down, at the end: up a hair, on us)
GLARE = (2.0, 0.35, 0.9)       # the glare hardens as the line ends: from s, over s, to (vroid_shinza face's narrow)
BLINK = 2.75                   # s: one slow blink, after the line
KEY = (0.2, -1.0, 1.25)        # his key: the grey sky ahead of him and above, so the brim shades his brow
RIMS = [((0.8, 0.9), (0.6, 0.68, 0.85), 0.3, 0.003, 0.9), ((-1.0, -0.3), (0.42, 0.45, 0.52), 0.15, 0.003, 0.9)]
BRIM_DRIPS = 6                 # how many places along the brim's front water drips from


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import rig, satsuei, vrm
    from rf import approach

    x, y = AT
    st = approach.stage(ctx, rain_box=((x - 2.0, y - 1.2, -0.2), (x + 2.0, y + 9.0, 3.5)), rain_near=1.4,
                        rain_clear=0.3, key_toward=KEY, fog=(6.0, 200.0, 0.92, 0.55))
    ch = st.shinza["vrm"]
    root = ch.root
    root.location = (x, y, 0.0)
    root.rotation_euler = (0.0, 0.0, -math.pi / 2)    # facing down the path, at us
    t0 = ctx.time(ctx.f0)
    frames = list(range(ctx.f0 - 1, ctx.f1 + 1))
    face_of = st.shinza["face"]
    for f in frames:
        u = ctx.time(f) - t0
        head = HEAD[1][0] + (HEAD[1][1] - HEAD[1][0]) * ease((u - HEAD[0][0]) / HEAD[0][1])
        eyes = EYES[1][0] + (EYES[1][1] - EYES[1][0]) * ease((u - EYES[0][0]) / EYES[0][1])
        breath = math.sin(2 * math.pi * 0.28 * u)
        pose = {**vrm.RELAXED, "spine": (4.0, 0.0, 0.0), "chest": (2.0 + 0.8 * breath, 0.0, 0.0),
                "neck": (head * 0.35, 0.0, 0.0), "head": (head * 0.65, 0.0, 1.5),
                "leftEye": (eyes, 0.0, 0.0), "rightEye": (eyes, 0.0, 0.0)}
        vrm.pose(ch, pose, hips=(0.0, 0.0, -0.01), frame=f)
        glare = GLARE[2] * ease((u - GLARE[0]) / GLARE[1])
        w = dict(face_of(1.0))
        w["narrow"] = glare
        blink = max(0.0, 1.0 - abs(u - BLINK) / 0.09)
        if blink > 0:
            w["blink"] = blink
        vrm.express(ch, w, frame=f)

    # framed on his eyes as they end up (head up), the push eased over the shot
    ctx.scene.frame_set(ctx.f1 - 1)
    eye = Vector(ch.face())
    b = math.radians(BEARING)
    toward = Vector((math.sin(b), -math.cos(b), 0.0))          # from his face toward the lens
    right = Vector((-toward.y, toward.x, 0.0))                  # the camera's right
    cam = rig.engine_camera("camera", fstop=FSTOP, size=ctx.size)
    cam.data.lens = LENS
    cam.data.clip_end = 3000.0
    ctx.scene.camera = cam
    aim = bpy.data.objects.new("aim", None)
    ctx.scene.collection.objects.link(aim)
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"
    focus = bpy.data.objects.new("focus", None)
    ctx.scene.collection.objects.link(focus)
    cam.data.dof.focus_object = focus
    # the eye nearer the lens is the one in focus
    near_eye = min((Vector(ch.point(e)) for e in ("leftEye", "rightEye")), key=lambda p: (p - eye - toward).length)
    for f in frames:
        k = ease((f - ctx.f0) / (ctx.f1 - ctx.f0))
        d = DIST[0] + (DIST[1] - DIST[0]) * k
        cam.location = eye + toward * d + Vector((0.0, 0.0, DZ)) - right * THIRD
        aim.location = eye + Vector((0.0, 0.0, LIFT)) - right * THIRD
        cam.keyframe_insert("location", frame=f)
        aim.keyframe_insert("location", frame=f)
    focus.location = near_eye + toward * 0.01

    # water dripping off the brim's front edge, carried with his head as it comes up
    hat = st.shinza["kasa"][0]
    lip = [v.co.copy() for v in hat.data.vertices[:48]]
    brim = {}
    for f in frames:
        ctx.scene.frame_set(f)
        mw = hat.matrix_world
        pts = [mw @ v for v in lip]
        brim[f] = pts
    cam_at = Vector(cam.location)
    front = sorted(range(48), key=lambda i: (brim[ctx.f1 - 1][i] - cam_at).length)[:BRIM_DRIPS * 3:3]

    def carry(t):
        f = min(max(round(t * ctx.fps), frames[0]), frames[-1])
        return [tuple(brim[f][i]) for i in front]

    approach.drips("brim-drips", None, t0 - 0.3, ctx.time(ctx.f1), ctx.fps, coll=st.cast, frames=frames,
                   every=(0.45, 1.1), fall=0.9, size=0.0028, carry=carry, seed=7)

    comp = satsuei.setup(ctx.scene, st.cast)
    for f in frames:
        s = ctx.look_at(f)
        comp.key(f, s.look(rims=[satsuei.Rim(*r) for r in RIMS], para_from=(0.5, 1.0), para_to=(0.5, 0.55),
                           wrap_width=0.03))
    comp.hold()
    ctx.scene.frame_set(ctx.f0)
    print(f"eyes: his eyes at {tuple(round(v, 3) for v in eye)}, brim drips from {len(front)} points")
