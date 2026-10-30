"""The freeze: the instant Shinza launches himself, time stops. The rain slows in the air and hangs (the look
schedule keys its speed from 9.5 m/s to nothing between +0.1 s and +0.9 s); the streaks shorten into beads. Shinza
is caught mid-stride, his weight thrown forward, the nodachi raised high over his right shoulder, a crown of water
hanging round the foot he pushed off from and drops flung from his hair and his blade frozen along their arcs. Tsuru
has not moved, except that her left hand has come to the pole above her right. The camera glides through the hanging
drops: from in front of him, past his raised blade, along the line between them, turning to her; the near drops
slide by as soft discs of light while the focus travels from him to her. Silence, then a high ring.

The cast is the duel's (rf/duel.py), the camera lib/cinema.py's, the rain lib/weather.py's (keyed to the schedule's
speed, so the drops decelerate to a stop and hang rather than jump).

    blender -b -P blender/render.py -- --film rain-ferry --shot freeze --mode look --engine eevee \\
        --frames 1635,1665,1700,1754 --res 960x540
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

SHOT = {"scene": "freeze"}

# Shinza mid-launch, where shots/charge.py takes him on from (its START and SWORDS[0]): a stride on from his mark
# toward her, his trunk thrown forward, the sword raised two-handed over his right shoulder (his frame), the left foot
# swinging forward off the deck (charge's lead), the right pushing off on its ball
SH_AT = (0.55, 0.0)                # from his mark (rf/duel.py MARKS = rf/clash.py STANDOFF): charge's START
# (hasso: the fists before his right shoulder, a fist off it, the elbows bent and out; charge's SWORDS[0])
POMMEL = (-0.14, -0.26, 1.36)
HILT_UP = (0.1, 0.38, 0.92)        # the hilt's way up, the blade carrying on up and back over his shoulder
ELBOWS = {"left": (0.55, -0.1, 1.45), "right": (-0.55, -0.1, 1.45)}     # charge's OUT
SH_TURNS = {"spine": (12.0, 0.0, 6.0), "chest": (6.0, 0.0, 4.0), "neck": (-6.0, 0.0, 0.0), "head": (-8.0, 0.0, -4.0)}
SH_HIPS = (0.0, -0.12, -0.06)
SH_FEET = {"leftFoot-target": (-0.02, -0.3, 0.16), "rightFoot-target": (0.0, 0.18, 0.04)}
# Tsuru: her left hand come to the pole above her right (her frame)
TS_LEFT = ((-0.23, -0.22, 1.13), (0.55, -0.2, 0.9))
# the camera's glide on the river side: from close in front of him, out in an arc through the hanging rain until both
# stand at the frame's edges, and in again to her; what it looks at runs from his face to hers, the focus with it
PATH = [(-0.7, -1.25, 1.5), (-0.45, -2.3, 1.48), (0.1, -3.8, 1.45), (0.65, -2.3, 1.4), (1.05, -1.25, 1.35)]
ALONG = (0.0, 0.15, 0.5, 0.85, 1.0)      # how far from his face to hers each point looks
# (the path from the duel's middle, rf/duel.py MID)
GLIDE = (0.35, 4.7)
LENS = (24.0, 32.0)
FSTOP = 2.0
LOOK = dict(rims=[((0.6, 1.0), (0.6, 0.68, 0.85), 0.3, 0.003, 0.9), ((-1.0, 0.3), (1.0, 0.5, 0.18), 0.2, 0.0025, 0.9)],
            para_from=(0.5, 0.9), para_to=(0.5, 0.05), para_amount=0.3)
KEYS = {"shinza": (1.0, -0.6, 0.8), "tsuru": (-1.0, -0.6, 0.8)}


def build(ctx):
    import bpy
    from mathutils import Matrix, Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, satsuei, vrm
    from rf import clash, duel, vroid_tsuru
    from rf import eye_closeup

    st = duel.stage(ctx)
    sh, ts = st.bodies["shinza"], st.bodies["tsuru"]
    shc, tsc = st.ch("shinza"), st.ch("tsuru")
    sx, sy = duel.MARKS["shinza"]
    st.actors["shinza"]["root"].location = (sx + SH_AT[0], sy + SH_AT[1], 0.0)
    # Shinza mid-launch: both hands on the hilt swept up over his head as charge grips it (the sword rides his right
    # hand), the stride
    up = np.asarray(HILT_UP, float) / np.linalg.norm(HILT_UP)
    hands, fingers = clash.shinza_sword(shc, POMMEL, HILT_UP, poles=ELBOWS)
    for side, (_, point, along, palm, pole) in hands.items():
        vrm.grasp(shc, side, point, along, palm, pole=pole)
    vrm.pose(shc, fingers, reset=False)
    sh.settle(fingers)
    fingers = vrm.grasp(tsc, "left", TS_LEFT[0], (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0), pole=TS_LEFT[1],
                        radius=vroid_tsuru.POLE_R)
    vrm.pose(tsc, fingers, reset=False)
    ts.settle(fingers)
    keep_sh = ("leftHand-target", "leftHand-hold", "rightHand-target", "rightHand-hold", "leftHand-pole", "rightHand-pole")
    keep_ts = ("leftHand-target", "leftHand-hold", "leftHand-pole")
    sh.key(ctx.f0 - 1, SH_TURNS, hips=SH_HIPS, moves=SH_FEET, keep=keep_sh,
           chains=sh.sway(0.0, amount=26.0, cloth=14.0, toward=(0.0, 1.0, 0.0), seed=1))
    ts.key(ctx.f0 - 1, {"head": (-3.0, 0.0, -4.0)}, keep=keep_ts,
           chains=ts.sway(0.0, amount=6.0, cloth=4.0, toward=(0.0, 1.0, 0.0), seed=7))
    vrm.express(shc, {"glare": 1.0, "narrow": 0.6, "aa": 0.55}, frame=ctx.f0 - 1)
    vrm.express(tsc, {"tsuru-calm": 0.4, "tsuru-glare": 0.6}, frame=ctx.f0 - 1)
    bpy.context.view_layer.update()

    # the water he threw up, hanging: a crown round the foot he pushed off from, drops off his hair and his blade
    rng = np.random.default_rng(12)
    beads = []
    foot = np.array(shc.point("rightToes"))
    for k in range(46):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.08, 0.26)
        beads.append((foot + np.array([r * math.cos(a), r * math.sin(a) * 0.7, rng.uniform(0.02, 0.32) * (1.2 - r * 2.5)]),
                      rng.uniform(0.004, 0.011)))
    head = np.array(shc.point("head", tail=True))
    for k in range(26):
        beads.append((head + np.array([rng.uniform(-0.45, -0.05), rng.uniform(-0.25, 0.25), rng.uniform(-0.15, 0.2)]),
                      rng.uniform(0.003, 0.007)))
    tip = np.array(shc.world(np.asarray(POMMEL) + up * 1.35))     # the hilt and the blade on
    for k in range(22):
        s = rng.uniform(0.0, 1.0)
        beads.append((tip + np.array([-0.5 * s - 0.05, rng.uniform(-0.1, 0.1), -0.25 * s + rng.uniform(-0.05, 0.05)]),
                      rng.uniform(0.003, 0.008)))
    me = bpy.data.meshes.new("hung")
    ob = bpy.data.objects.new("hung", me)
    st.cast.objects.link(ob)
    import bmesh

    bm = bmesh.new()
    for p, r in beads:
        bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=r,
                                  matrix=Matrix.Translation(Vector(tuple(p))))
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    me.materials.append(eye_closeup._water("hung", 0.8, 1.3))

    # the camera (lib/cinema.py): the glide along PATH (from MID), its aim travelling from his face to hers, the focus
    # racked from him to her as it goes
    bpy.context.view_layer.update()
    mid = np.array((duel.MID[0], duel.MID[1], 0.0))
    cams = [np.asarray(p, float) + mid for p in PATH]
    sh_face, ts_face = np.array(shc.face()), np.array(tsc.face())
    aims = [sh_face + (ts_face - sh_face) * k for k in ALONG]
    rig = cinema.film(ctx, [cinema.Setup(
        "glide", 0.0, cinema.path(cams, aims), span=GLIDE, ease="sine", lens=LENS, fstop=FSTOP, focus=(shc, "head"),
        racks=(cinema.Rack(1.2, (tsc, "head"), 3.2),), shake=cinema.Shake(breath=0.02, seed=9))])
    # the weather (lib/weather.py): the look schedule slows the rain to a stop by +0.9 s, its drops hanging as beads;
    # nothing splashes once it has stopped
    duel.weather(st, rig)
    comp = satsuei.setup(ctx.scene, st.cast)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        duel.key_lines(st, f, *duel.lens_at(rig, f))
        duel.key_light(st, f, KEYS)
        comp.key(f, duel.look(st, f, LOOK))
    comp.hold()
    duel.hold(st.ch("shinza").armature, st.ch("tsuru").armature)
    print(f"freeze: Shinza at {SH_AT}, the glide {GLIDE} s, {len(beads)} hanging drops")
