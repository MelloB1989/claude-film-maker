"""Shot 5, eyes (18-21.5 s): under the brim of his kasa, his eyes. The cut lands on the low drum (18.0 s) with his
head still down, the brim over his eyes; his head comes up and the eyes come out from under it into the light, on
us. His inner voice (line 2, "Stronger than anyone.", 18.5-20.11 s); as it ends his eyes narrow to a glare. An extreme
close-up on a long lens, pushing in slowly, the brim's edge dark across the top of the frame with the rain dripping
off it, the mist and the path behind him gone soft.

The stage is rf/approach.py's; he acts through blender/lib/vrm_anim.py (a Performance, baked).
"""
from __future__ import annotations

import math

SHOT = {"scene": "eyes"}

# he stands where the walk leaves him (shots/walk.py), facing the way he walked
LENS, FSTOP = 100.0, 4.0
# framed from the brim down, as the push ends: the brim's front edge (much nearer the lens than his eyes: it is
# projected, not measured flat) just under the frame's top (BRIM_V), the point of his nose near its foot (NOSE_V); the
# push starts PUSH times as far out
BRIM_V, NOSE_V, NOSE = 0.92, 0.1, 0.05     # (frame heights from the bottom; his nose this far under his eyes, m)
PUSH = 1.25
BEARING = 14.0                 # degrees round from straight in front of him toward his left (our right)
DZ = -0.06                     # the lens this far below his eyes: looking up under the brim
THIRD = 0.012                  # ... and this far to his right (our left): room on the side he looks past
HEAD = ((0.12, 0.8), (13.0, -2.0))   # his head comes up: (from s, over s), (degrees down at the cut, at the end)
EYES = ((0.25, 0.5), (14.0, -1.0))   # his eyes lift (from, over), (degrees down, at the end: up a hair, on us)
GLARE = (2.0, 0.35, 0.9)       # the glare hardens as the line ends: from s, over s, to (vroid_shinza face's narrow)
BLINK = 2.75                   # s: one slow blink, after the line
KEY = (0.2, -1.0, 1.25)        # his key: the grey sky ahead of him and above, so the brim shades his brow
RIMS = [((0.8, 0.9), (0.6, 0.68, 0.85), 0.3, 0.003, 0.9), ((-1.0, -0.3), (0.42, 0.45, 0.52), 0.15, 0.003, 0.9)]
BRIM_DRIPS = 6
PARA = 0.7                     # how deep the brim's shade over his brow goes (the compositor's para)                 # how many places along the brim's front water drips from


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, satsuei, vrm, vrm_anim as va
    from rf import approach

    import importlib.util

    spec = importlib.util.spec_from_file_location("shots.walk", Path(__file__).with_name("walk.py"))
    walk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(walk)
    gait, _, _ = walk.staging(ctx.fps, ctx.time(ctx.f0) - 5.5, ctx.time(ctx.f0))
    at, fwd = gait.root(ctx.time(ctx.f0))
    x, y = at
    z = gait.z(at)
    st = approach.stage(ctx, key_toward=KEY)
    ch = st.shinza["vrm"]
    t0 = ctx.time(ctx.f0)
    frames = list(range(ctx.f0 - 1, ctx.f1 + 1))
    fps = ctx.fps

    def at_s(u):
        return ctx.f0 + u * fps

    def carriage(head, eyes):
        return {"neck": (head * 0.35, 0.0, 0.0), "head": (head * 0.65, 0.0, 1.5), "leftEye": (eyes, 0.0, 0.0),
                "rightEye": (eyes, 0.0, 0.0)}

    # standing where the walk left him, his head down under the brim at the cut; on the drum it comes up and his eyes
    # lift out from under it onto us; the glare hardens as the line ends; one slow blink after
    p = va.Performance(ch, fps=fps, seed=5)
    p.root(frames[0], (x, y, z), yaw=math.degrees(math.atan2(fwd[1], fwd[0])))
    p.plant_feet(frames[0])
    p.pose(frames[0], {**st.shinza["stand"], "spine": (4.0, 0.0, 0.0), "chest": (2.0, 0.0, 0.0),
                       **carriage(HEAD[1][0], EYES[1][0])}, hips=(0.0, 0.0, -0.01))
    p.hold(at_s(min(HEAD[0][0], EYES[0][0])))
    p.pose(at_s(HEAD[0][0] + HEAD[0][1]), {k: v for k, v in carriage(HEAD[1][1], 0.0).items() if "Eye" not in k},
           ease="out", full=False)
    p.pose(at_s(EYES[0][0] + EYES[0][1]), {k: v for k, v in carriage(0.0, EYES[1][1]).items() if "Eye" in k},
           ease="out", full=False)
    p.breathe(rate=0.28, depth=1.0)
    face = st.shinza["face"]
    p.express(frames[0], {**face(1.0), "narrow": 0.0})
    p.express(at_s(GLARE[0]), {**face(1.0), "narrow": 0.0})
    p.express(at_s(GLARE[0] + GLARE[1]), {**face(1.0), "narrow": GLARE[2]})
    p.blink_at(at_s(BLINK))
    p.secondary(wind=(0.4, 0.0, 0.0))
    p.bake(frames[0], frames[-1] + 1)

    # framed on his eyes as they end up (head up), the push eased over the shot
    ctx.scene.frame_set(ctx.f1 - 1)
    eye = Vector(ch.face())
    b = math.radians(BEARING)
    lft = approach.Gait.left_of(fwd)
    toward = Vector((*(fwd * math.cos(b) + lft * math.sin(b)), 0.0))   # from his face toward the lens
    right = Vector((-toward.y, toward.x, 0.0))                  # the camera's right
    # the eye nearer the lens is the one in focus; the push eased over the shot, jolted a hair by the drum on the cut
    near = min(("leftEye", "rightEye"), key=lambda e: (Vector(ch.point(e)) - eye - toward).length)
    hat = st.shinza["kasa"][0]
    mw = hat.matrix_world
    front = max((mw @ v for v in approach.brim(hat)), key=lambda p: (p - eye).dot(toward))
    zb, zn, cz = front.z, eye.z - NOSE, eye.z + DZ
    ahead = (front - eye).dot(toward)                          # how much nearer the lens the brim's edge is (m)
    k = cinema.GATE_H / LENS                                   # frame heights per unit of slope

    def spread(d):
        """How far apart (frame heights) the brim and his nose land with the lens d from his eyes."""
        return ((zb - cz) / (d - ahead) - (zn - cz) / (d - 0.02)) / k

    lo_d, hi_d = ahead + 0.05, 4.0
    for _ in range(60):                                        # spread falls as the lens backs off
        mid = (lo_d + hi_d) / 2
        lo_d, hi_d = (mid, hi_d) if spread(mid) > BRIM_V - NOSE_V else (lo_d, mid)
    d = (lo_d + hi_d) / 2
    tilt = (zn - cz) / (d - 0.02) - (NOSE_V - 0.5) * k        # the view's slope up from level
    cam1 = eye + toward * d + Vector((0.0, 0.0, DZ)) - right * THIRD
    aim = cam1 - toward + Vector((0.0, 0.0, tilt))
    cam0 = eye + toward * (d * PUSH) + Vector((0.0, 0.0, DZ)) - right * THIRD
    h = d * k
    # sharp on the near eye's surface (its bone is inside the eyeball), carried by his head
    focus = bpy.data.objects.new("eye-focus", None)
    ctx.scene.collection.objects.link(focus)
    focus.location = Vector(ch.point(near)) + toward * 0.012
    vrm.attach(focus, ch, "head")
    rig = cinema.film(ctx, [cinema.Setup("eyes", 0.0, cinema.line(tuple(cam0), tuple(cam1), tuple(aim),
                                                                  tuple(aim + (cam0 - cam1))),
                                         lens=LENS, fstop=FSTOP, focus=focus,
                                         shake=cinema.Shake(breath=0.03, hits=((0.0, 0.2),)))])
    v = rig.pose(ctx.f1 - 1).screen(tuple(front))[1]
    approach.storm(ctx, rig, st, ground=z)
    # water dripping off the brim's front edge, carried with his head as it comes up
    approach.brim_drips("brim", hat, front=cam0, n=BRIM_DRIPS, period=0.9, hang=0.6, fall=0.9,
                        size=0.004, coll=st.cast)

    comp = satsuei.setup(ctx.scene, st.cast)
    for f in rig.frames:
        s = ctx.look_at(f)
        # the brim's shade over his brow and down to his eyes (the eyes, unshaded, stay lit in it)
        comp.key(f, s.look(rims=[satsuei.Rim(*r) for r in RIMS], para_from=(0.5, 0.42), para_to=(0.5, 0.8),
                           para_amount=PARA, wrap_width=0.03))
    comp.hold()
    ctx.scene.frame_set(ctx.f0)
    print(f"eyes: his eyes at {tuple(round(v, 3) for v in eye)}, the brim's front {front.z - eye.z:+.3f} m over them; "
          f"{ahead:.3f} m nearer the lens (on screen at {v:.2f}); the frame {h:.3f} m high at his eyes, the lens "
          f"{d * PUSH:.2f} -> {d:.2f} m out")
