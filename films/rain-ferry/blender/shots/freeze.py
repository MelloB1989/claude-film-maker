"""The freeze: the instant Shinza launches himself, time stops. The rain slows in the air and hangs (the look
schedule keys its speed from 9.5 m/s to nothing between +0.1 s and +0.9 s); the streaks shorten into beads. Shinza
is caught mid-stride, his weight thrown forward, the nodachi raised high over his right shoulder, a crown of water
hanging round the foot he pushed off from and drops flung from his hair and his blade frozen along their arcs. Tsuru
has not moved, except that her left hand has come to the pole above her right. The camera glides through the hanging
drops: from in front of him, past his raised blade, along the line between them, turning to her; the near drops
slide by as soft discs of light while the focus travels from him to her. Silence, then a high ring.

The cast is the duel's (rf/duel.py); the rain's clock is remapped here: the scene time its drops fall by is replaced
by a keyed clock, the integral of the schedule's speed, so they decelerate to a stop rather than jump.

    blender -b -P blender/render.py -- --film rain-ferry --shot freeze --mode look --engine eevee \\
        --frames 1635,1665,1700,1754 --res 960x540
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

SHOT = {"scene": "freeze"}

# Shinza mid-launch: a stride on from his mark toward her, his trunk thrown forward, the hilt raised high over his
# right shoulder (his frame), the right foot swinging forward off the deck, the left pushing off on its ball
SH_AT = (0.55, 0.02)               # from his mark (rf/duel.py MARKS): a stride on
POMMEL = (-0.13, -0.08, 1.4)
HILT_UP = (0.12, 0.42, 0.9)        # the hilt's way up, the blade carrying on up and back over his shoulder
ELBOWS = {"left": (0.5, -0.15, 1.0), "right": (-0.6, 0.1, 1.05)}
SH_TURNS = {"spine": (12.0, 0.0, 6.0), "chest": (6.0, 0.0, 4.0), "neck": (-6.0, 0.0, 0.0), "head": (-8.0, 0.0, -4.0)}
SH_HIPS = (0.0, -0.12, -0.06)
SH_FEET = {"rightFoot-target": (0.02, -0.3, 0.16), "leftFoot-target": (0.0, 0.18, 0.04)}
# Tsuru: her left hand come to the pole above her right (her frame)
TS_LEFT = ((-0.23, -0.22, 1.13), (0.55, -0.2, 0.9))
# the camera's glide (world): in front of him, past his blade, along the line, turning to her; what it looks at runs
# from his face to hers; the focus with it
PATH = [(-0.55, -1.45, 1.42), (-0.85, -1.05, 1.52), (-0.25, -0.62, 1.42), (0.7, -0.52, 1.3), (1.05, -0.48, 1.26)]
# (the path from the duel's middle, rf/duel.py MID)
GLIDE = (0.35, 4.7)
LENS = (24.0, 32.0)
FSTOP = 2.0
LOOK = dict(rims=[((0.6, 1.0), (0.6, 0.68, 0.85), 0.3, 0.003, 0.9), ((-1.0, 0.3), (1.0, 0.5, 0.18), 0.2, 0.0025, 0.9)],
            para_from=(0.5, 0.9), para_to=(0.5, 0.05), para_amount=0.3)
KEYS = {"shinza": (1.0, -0.6, 0.8), "tsuru": (-1.0, -0.6, 0.8)}
SPEED0 = 9.5


def build(ctx):
    import bpy
    from mathutils import Matrix, Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import rig, satsuei, vrm
    from rf import duel, vroid_shinza
    from rf import duel_motion as dm
    from rf import eye_closeup

    st = duel.stage(ctx, splashes=False)
    sh, ts = st.bodies["shinza"], st.bodies["tsuru"]
    shc, tsc = st.ch("shinza"), st.ch("tsuru")
    sx, sy = duel.MARKS["shinza"]
    st.actors["shinza"]["root"].location = (sx + SH_AT[0], sy + SH_AT[1], 0.0)
    cam, aim = duel.camera(ctx, lens=LENS[0], fstop=FSTOP)
    duel.rain_input(st.rain, "clear").default_value = 0.25
    duel.rain_input(st.rain, "near").default_value = 2.5

    # the rain's clock: the scene's time swapped for a keyed value; its drops shortened to beads as they stop
    tv = {}
    for ob in (st.rain, st.rain_cast):
        ng = ob.modifiers[0].node_group
        tn = next(n for n in ng.nodes if n.bl_idname == "GeometryNodeInputSceneTime")
        if ng.name not in tv:
            v = ng.nodes.new("ShaderNodeValue")
            for link in list(tn.outputs["Seconds"].links):
                ng.links.new(v.outputs[0], link.to_socket)
            info = next(n for n in ng.nodes if n.bl_idname == "GeometryNodeObjectInfo" and n.inputs["Object"].default_value
                        and n.inputs["Object"].default_value.name.endswith("-drop"))
            info.transform_space = "RELATIVE"     # the drop's keyed scale carried into each instance
            tv[ng.name] = (v, info.inputs["Object"].default_value)

    # Shinza mid-launch: both hands re-closed on the hilt raised high (the sword rides his right hand), the stride
    hilt0 = vroid_shinza.HILT_DIR / np.linalg.norm(vroid_shinza.HILT_DIR)
    up = np.asarray(HILT_UP, float) / np.linalg.norm(HILT_UP)
    R = np.array(Vector(tuple(hilt0)).rotation_difference(Vector(tuple(up))).to_matrix())
    for side, along in vroid_shinza.GRIPS.items():
        palm = np.array((1.0 if side == "right" else -1.0, 0.0, -0.6))
        vrm.grasp(shc, side, np.asarray(POMMEL) + up * along, up, R @ palm, pole=ELBOWS[side])
    vrm.grasp(tsc, "left", TS_LEFT[0], (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0), pole=TS_LEFT[1], amount=0.9)
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
    foot = np.array(shc.point("leftToes"))
    for k in range(46):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.08, 0.26)
        beads.append((foot + np.array([r * math.cos(a), r * math.sin(a) * 0.7, rng.uniform(0.02, 0.32) * (1.2 - r * 2.5)]),
                      rng.uniform(0.004, 0.011)))
    head = np.array(shc.point("head", tail=True))
    for k in range(26):
        beads.append((head + np.array([rng.uniform(-0.45, -0.05), rng.uniform(-0.25, 0.25), rng.uniform(-0.15, 0.2)]),
                      rng.uniform(0.003, 0.007)))
    tip = np.array(shc.world(np.asarray(POMMEL) + up * 1.0))
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

    pts = [np.asarray(p, float) + np.array((duel.MID[0], duel.MID[1], 0.0)) for p in PATH]
    frames = range(ctx.f0 - 1, ctx.f1 + 1)
    speeds = {f: ctx.look_at(f).rain.speed for f in frames}
    clocks = dict(zip(frames, dm.clock([speeds[f] for f in frames], ctx.fps, SPEED0)))
    comp = satsuei.setup(ctx.scene, st.cast)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        speed = max(0.0, speeds[f])
        for v, drop in tv.values():
            v.outputs[0].default_value = clocks[f]
            v.outputs[0].keyframe_insert("default_value", frame=f)
            k = speed / SPEED0                     # streak at full speed, bead at rest
            drop.scale = (1.0 + 0.6 * (1 - k), 1.0, 0.12 + 0.88 * k)
            drop.keyframe_insert("scale", frame=f)
        u = dm.ease(dm.span(t, *GLIDE, curve=lambda x: x))
        cam_at = _along(pts, u, rig) + duel.shake(t, 0.004)
        sh_face, ts_face = np.array(shc.face()), np.array(tsc.face())
        w = dm.span(t, 1.2, 4.4)
        target = sh_face + (ts_face - sh_face) * w
        lens = LENS[0] + (LENS[1] - LENS[0]) * u
        duel.key_camera(cam, aim, f, cam_at, target, lens=lens, fstop=FSTOP)
        duel.key_lines(st, f, cam_at, lens)
        duel.key_light(st, f, KEYS)
        comp.key(f, duel.look(st, f, LOOK))
    comp.hold()
    duel.hold(st.ch("shinza").armature, st.ch("tsuru").armature)
    print(f"freeze: Shinza at {SH_AT}, the glide {GLIDE} s, {len(beads)} hanging drops")


def _along(pts, u: float, rig) -> np.ndarray:
    """The point u (0..1) of the way along a Catmull-Rom path through `pts`."""
    n = len(pts) - 1
    x = min(u * n, n - 1e-9)
    i = int(x)
    p = [pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n)]]
    return np.asarray(rig.catmull_rom(*p, x - i), float)
