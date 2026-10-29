"""Shot 26, the cross: the wide the film has been waiting for. The ferry out on the shining river in the evening's gold,
Tsuru standing at its stern poling it on, Shinza sitting in it, small under the far ridges; and close in front of us
the cut red headband turning slowly on the water, drifting away downstream. The theme resolves.

Low over the water off the jetty's end, looking down the valley into the light (where 25 light broke the clouds), the
low sun over the ferry and its glitter on the water coming toward us: the jetty coming in from the left, the ferry
pulling away from it across the middle of the frame. The focus
starts on the headband and goes out to the boat as the camera rises slowly, as if lifting its eyes after it.

The world is the after-rain one (the look schedule's "cross": warm 1, no rain); the ferry is poled out along
set_world.CROSS_PATH (`push_off`). RF_S7_CAST=none builds the shot without its cast.
"""
from __future__ import annotations

import math
import os

SHOT = {"scene": "cross"}

PUSH = (-2.0, 22.0)          # s (into the shot): the ferry's push along CROSS_PATH, just under way
CAM = ((8.0, -12.0, 0.72), (8.2, -11.6, 1.28))     # from, to (eased): low over the water, rising
AIM = ((14.3, 27.5, 2.2), (14.5, 28.0, 3.6))
LENS, FSTOP = 28.0, 2.8
RACK = (1.6, 3.6)            # s: the focus from the headband out to the boat
BAND = ((7.55, -6.95), (8.3, -5.45))   # the headband's drift on the water (x, y), from and to over the shot
POLE = dict(period=3.4, push=0.62, tilt=(-8.0, 32.0), grip=((-0.2, -0.18, 1.12), (-0.2, 0.2, 0.82)))


def build(ctx):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import bpy

    from lib import cinema, toon3d
    from rf import ending as E
    from rf import set_world, sets

    st = E.stage(ctx)
    set_world.push_off(st.world, ctx, t0=PUSH[0], t1=PUSH[1])
    n = (ctx.f1 - ctx.f0) / ctx.fps

    # the headband on the water: floating on an empty that drifts, turns and rides the swell (his own, cut loose, once
    # the cast is built; a drawn strip without it)
    drift = bpy.data.objects.new("headband-drift", None)
    st.world["near"].objects.link(drift)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        k = t / n
        x, y = E.lerp(*BAND, k)
        drift.location = (x, y, sets.WATER_Z + 0.006 + 0.008 * math.sin(2 * math.pi * 0.4 * t))
        drift.rotation_euler = (0.03 * math.sin(2 * math.pi * 0.4 * t + 1.0), 0.03 * math.sin(2 * math.pi * 0.31 * t),
                                math.radians(-20.0 + 14.0 * k))
        drift.keyframe_insert("location", frame=f)
        drift.keyframe_insert("rotation_euler", frame=f)

    actors = None
    band = None
    if os.environ.get("RF_S7_CAST", "vroid") != "none":
        from lib import vrm
        from rf import vroid_tsuru as T

        actors = E.cast(st, {"tsuru": dict(pole="hand", wet=0.3),
                             "shinza": dict(kasa="back", sword="back", headband=True, wet=0.3)})
        ts, sh = actors["tsuru"], actors["shinza"]
        band = [E.cut_headband(sh, afloat=True)]
        anchors = st.world["anchors"]
        for built, at in ((ts, "boat_stern"), (sh, "boat_middle")):
            built["root"].parent = anchors[at]
            built["root"].matrix_parent_inverse.identity()
            built["root"].location = (0.0, 0.0, 0.0)
            built["root"].rotation_euler = (0.0, 0.0, 0.0)
        # Shinza on his knees in the boat's middle, his hands on his thighs, his head up now, looking ahead
        legs = E.kneel(sh, sag=dict(E.SAG, spine=(4.0, 0.0, 0.0), neck=(4.0, 0.0, 0.0), head=(0.0, 0.0, 0.0)))
        E.hands_rest(sh, legs)
        E.kneel(sh, sag=dict(E.SAG, spine=(4.0, 0.0, 0.0), neck=(4.0, 0.0, 0.0), head=(0.0, 0.0, 0.0)), legs=False)
        # Tsuru poling: each stroke the pole goes in ahead of her and she walks her hands back down it, leaning on
        # it, then lifts it and swings it forward again
        ch = ts["vrm"]
        P = POLE
        fingers = vrm.grip_pose("right", 0.95)
        for f in range(ctx.f0 - 1, ctx.f1 + 2, 2):    # keyed every other frame, eased between (the build's cost)
            t = (f - ctx.f0) / ctx.fps
            u = (t / P["period"]) % 1.0
            if u < P["push"]:
                k = E.ease(u / P["push"])
            else:
                k = 1.0 - E.ease((u - P["push"]) / (1.0 - P["push"]))
            a = math.radians(P["tilt"][0] + (P["tilt"][1] - P["tilt"][0]) * k)
            grip = E.lerp(*P["grip"], k)
            vrm.grasp(ch, "right", grip, (0.0, -math.sin(a), math.cos(a)), (1.0, 0.0, 0.0), pole=(-0.5, 0.4, 0.6),
                      amount=0.95, bend=70.0)
            E.key_handles(ts, f, keys=("rightHand-target", "rightHand-pole", "rightHand-hold"))
            pose = dict(T.TS_POSE, **fingers)
            sx, sy, sz = pose["spine"]
            pose["spine"] = (sx + 10.0 * k, sy, sz)
            vrm.pose(ch, pose, hips=(T.TS_HIPS[0], T.TS_HIPS[1] + 0.03 * k, T.TS_HIPS[2] - 0.02 * k), frame=f)
            vrm.express(ch, ts["face"](), frame=f)
        # the evening sun low down the valley behind them: their keys from there, their faces in the 1st shade
        toon3d.aim(ts["key"], (0.5, 1.0, 0.35))
        toon3d.aim(sh["key"], (0.5, 1.0, 0.35))

    if band is None:
        band = E.headband("shinza-headband", E.band_material(st.look, wet=1.0), st.world["near"], (0.0, 0.0), 0.0,
                          z=0.0, curl=0.2, seed=5)
    bpy.context.view_layer.update()
    for ob in band:
        rot = ob.matrix_world.to_3x3()
        ob.parent = drift
        ob.matrix_parent_inverse.identity()
        ob.matrix_basis = rot.to_4x4()
        ob.location = (0.0, 0.0, 0.0)

    # the camera: low over the water, rising slowly after the boat; sharp on the headband, then out to the boat
    boat = st.world["anchors"]["boat_middle"]
    rig = cinema.film(ctx, [cinema.Setup(
        "cross", 0.0, cinema.drift(cinema.line(CAM[0], CAM[1], AIM[0], AIM[1]), 0.03), lens=LENS, fstop=FSTOP,
        focus=drift, racks=(cinema.Rack(RACK[0], boat, RACK[1] - RACK[0]),), shake=cinema.Shake(breath=0.05, seed=26))],
        clip=(0.02, 4000.0))
    E.weather(ctx, st, rig, deck=False, river=False)

    def look(f, s):
        L = s.light
        return dict(rims=[((0.6, 0.6), L.warm, 0.5, 0.003, 0.9)], para_from=(0.6, 0.8), para_to=(0.3, 0.1))

    E.finish(ctx, st, look, actors, lambda f: LENS)
