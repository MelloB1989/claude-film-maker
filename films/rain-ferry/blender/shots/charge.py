"""The charge: Shinza, released from the freeze mid-stride, runs on at her down the jetty, his sword up over his head,
roaring (line 11, the whole shot), long splashing strides about every half second (the step_puddle cues at 73.35,
73.85, 74.35 s), the water flying from his feet, then the sword thrown back to its height (the whoosh at 74.95 s) and
coming over: cut on its fall.

The camera runs ahead of him low on the river side, a wide lens close in, so he comes on fast and big through the
rain; it rumbles with his strides and is jolted by each (no shutter blur: drawn animation has none, and it
re-evaluates the whole cast per step); pale focus lines converge on him on twos,
thickening as he closes. His run is the animation core's charge gait (blender/lib/vrm_anim.py), his hands on the hilt
keyed through it.
"""
from __future__ import annotations

import math

SHOT = {"scene": "charge"}

START, END_X = 2.75, 5.45       # his x: from (where shots/freeze.py holds him, a stride on from his mark), to
                                # about where the cut falls (CLASH less his reach)
GAIT = dict(stride=0.8, speed=1.6, first=0.7)     # the core's "charge", a stride every half second (the cues),
                                                   # the gap (2.7 m) run in the shot
SWING = (1.5, 1.8, 2.0)         # s: the sword thrown back from, at its height, coming over
CAM = [(0.0, (START + 2.0, -2.45, 0.55)), (1.0, (START + 2.6, -1.8, 0.62)), (2.0, (END_X + 0.85, -0.95, 0.78))]
LENS, FSTOP = 24.0, 2.8
JOLT, STEP = 1.2, 0.5          # the camera's jolt on a stride (degrees), the strides' beat (s)
FIRST_STEP = 0.25               # s: the first stride lands (data/mix.json step_puddle at 73.35)
# his frame: front -y, left +x, up z (rf/vroid_shinza.py; lib/vrm.py's turns): where the hilt is
# where the hilt is: its pommel, its way (pommel to blade), the elbows' poles, how it arrives (lib/vrm_anim.py EASES).
# The arms stay bent through it all (VRoid's arms are 0.47 m: a fist much past 0.4 m from its shoulder locks the
# elbow straight), the elbows out to the sides; the sword goes up and back over his head in an arc and comes over in
# one, the wrists cocking with the hilt. (The charge's gait carries him crouched, his shoulders some 0.15 m lower than
# standing: the fists are placed for that.)
OUT, HIGH, DOWN = ((0.55, -0.1, 1.35), (-0.55, -0.1, 1.35)), ((0.5, -0.3, 1.6), (-0.5, -0.3, 1.6)), \
    ((0.42, 0.0, 1.1), (-0.42, 0.0, 1.1))
SWORDS = [(0.0, (-0.14, -0.26, 1.36), (0.1, 0.38, 0.92), OUT, "out"),      # hasso over his right shoulder (the freeze's)
          (0.3, (0.02, -0.23, 1.5), (0.03, 0.55, 0.83), OUT, "overshoot"),  # up over his head (jodan), a fist off it
          (SWING[0], (0.02, -0.22, 1.51), (0.03, 0.55, 0.83), OUT, "inout"),
          (1.66, (0.02, -0.16, 1.61), (0.03, 0.85, 0.53), HIGH, "in"),      # winding up: up and back ...
          (SWING[1], (0.0, -0.07, 1.66), (0.0, 0.86, -0.5), HIGH, "out"),   # ... thrown back, the blade down his back
          (1.9, (0.02, -0.24, 1.58), (0.0, 0.2, 0.98), HIGH, "in"),         # coming over, upright ...
          (SWING[2], (0.03, -0.32, 1.3), (0.0, -0.45, 0.89), DOWN, "linear")]   # ... and on down at her, arms out
# the fists ride a beat behind his strides (each landing sinks them, m)
BOB, BOB_LAG = 0.025, 0.1
TS_LEFT = ((-0.23, -0.22, 1.13), (0.55, -0.2, 0.9))     # her left hand on the pole (shots/freeze.py TS_LEFT)
REAR = {"spine": (2.0, 0.0, 0.0), "chest": (-6.0, 0.0, 0.0)}      # the trunk rearing back as the sword goes up
DRIVE = {"spine": (22.0, 0.0, 0.0), "chest": (12.0, 0.0, 0.0)}    # ... and driving over
CRY = {"angry": 0.9, "aa": 1.0}
SKY_RIM, LANTERN_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18)


def build(ctx):
    import sys
    from pathlib import Path

    import numpy as np
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, fx_impact as fx, toon, vrm, vrm_anim as va
    from rf import clash

    fps = ctx.fps
    clash.tick("start")
    w = clash.world(ctx)
    clash.tick("world")
    actors = clash.cast(ctx, w, {"shinza": {"sword": "hand"}, "tsuru": {"pole": "hand"}})
    clash.tick("cast")
    sh, ts = actors["shinza"], actors["tsuru"]
    ch = sh["vrm"]
    # she waits at her mark beyond him, turned a little to the lens, her left hand come to the pole above her right
    # (as shots/freeze.py holds her)
    ts["root"].location = (clash.STANDOFF["tsuru"][0], clash.STANDOFF["tsuru"][1], 0.0)
    ts["root"].rotation_euler = (0.0, 0.0, math.pi + 0.3)
    vrm.grasp(ts["vrm"], "left", TS_LEFT[0], (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0), pole=TS_LEFT[1], amount=0.9)
    sh["root"].location = (START, 0.0, 0.0)

    def fr(t):
        return ctx.f0 + t * fps

    p = va.Performance(ch, fps=fps, seed=11)
    p.root(fr(0.0), (START, 0.0, 0.0), yaw=0.0)
    p.walk([(START, 0.0), (END_X + 4.0, 0.0)], fr(0.0), gait=va.GAITS["charge"].but(**GAIT), lead="left",
           swing=(0.0, 0.0))
    keys = list(SWORDS)
    # between the jodan and the wind-up the fists sink a little after each stride lands and lift between
    for k, tc in enumerate(np.arange(FIRST_STEP + BOB_LAG, SWING[0], STEP / 2)):
        if tc > SWORDS[1][0]:
            _, pommel, hilt, poles, _ = SWORDS[1]
            keys.append((tc, np.add(pommel, (0.0, 0.0, -BOB if k % 2 == 0 else 0.0)), hilt, poles, "inout"))
    for t, pommel, hilt, poles, how in sorted(keys, key=lambda k: k[0]):
        hands, _ = clash.shinza_sword(ch, pommel, hilt, poles=dict(zip(("left", "right"), poles)))
        for side, (_, point, along, palm, pole) in hands.items():
            p.grasp(fr(t), side, point, along, palm, pole=pole, ease=how)
    p.pose(fr(SWING[0]), {"spine": (14.0, 0.0, 0.0), "chest": (8.0, 0.0, 0.0)}, full=False)
    p.pose(fr(SWING[1]), REAR, full=False, ease="out")
    p.pose(fr(SWING[2]), DRIVE, full=False, ease="in")
    p.express(fr(0.0), {k: 0.0 for k in CRY})
    p.express(fr(0.12), CRY, ease="out")
    p.express(fr(1.76), {k: v * 0.7 for k, v in CRY.items()})
    clash.tick("performance keyed")
    p.bake(ctx.f0 - 1, ctx.f1 + 1)
    clash.tick("bake")

    def x_at(f):
        root, _ = p.root_at(f)
        return float(root[0])

    # ---- the water from his feet: a burst each half second from the first stride, where his feet are
    coll = toon.collection("fx")
    water = fx.unlit("thrown-water", tuple(w["state"].rain.color), alpha=0.55, strength=1.1)
    beats = np.arange(FIRST_STEP, 2.0, STEP)
    for i, tc in enumerate(beats):
        fc = round(fr(tc))
        # the foot that is down, from the performance (no stepping the scene: each step re-evaluates the cast)
        feet = [Vector(p.point_at(fc, f"{side}Foot")) for side in ("left", "right")]
        at = min(feet, key=lambda v: v.z).copy()
        at.z = 0.01
        for f in range(fc, min(ctx.f1, fc + round(0.5 * fps))):
            dt = (f - fc) / fps
            pts, vel = fx.burst(70, dt + 0.5 / fps, origin=tuple(at), up=(1.0, 2.8), out=(0.4, 1.8), seed=40 + i)
            if not len(pts):
                continue
            ob = fx.droplets(f"splash{i}-{f}", pts, vel, water, size=0.01, stretch=0.01, coll=coll)
            fx.show(ob, [f], ctx.f0 - 1, ctx.f1)

    clash.tick("splashes")
    # ---- the camera: running ahead of him, low, its aim on his chest, rumbling and jolted by his strides
    fs = list(range(ctx.f0 - 1, ctx.f1 + 1))
    chest = {f: Vector((x_at(f), 0.0, 1.25)) for f in fs}
    cams = [clash.keys_at(CAM, (f - ctx.f0) / fps, interp=lambda u: u) for f in fs]
    aims = [tuple(chest[f] + Vector((0.37, 0.0, 0.01))) for f in fs]
    rig = cinema.film(ctx, [cinema.Setup("run", -1.0 / fps, cinema.path(cams, aims), ease="linear", lens=LENS,
                                         fstop=FSTOP, focus=(ch, "chest"),
                                         shake=cinema.Shake(breath=0.35, freq=1.6, hits=tuple((tc, JOLT) for tc in beats),
                                                            decay=9.0, seed=5))])
    cam = rig.camera
    clash.tick("camera")
    clash.outlines(ctx, actors, lambda f: rig.pose(f).position, lambda f: LENS)
    clash.tick("outlines")
    clash.weather(ctx, rig, w, actors)
    clash.tick("weather")

    # ---- focus lines on him, on twos, pale as the rain, thickening as he closes; just in front of the focus
    aspect = ctx.size[0] / ctx.size[1]
    pale = fx.unlit("speed-pale", (0.82, 0.85, 0.9), alpha=0.28)
    strong = fx.unlit("speed-strong", (0.86, 0.89, 0.94), alpha=0.5)
    for i, f in enumerate(range(ctx.f0 + round(0.3 * fps), ctx.f1, 2)):
        u, v = rig.pose(f).screen(chest[f])
        centre = ((u - 0.5) * aspect, v - 0.5)
        late = (f - ctx.f0) / fps > 1.3
        tris = fx.focus_lines(90 if late else 60, center=centre, inner=0.42 if late else 0.5, ellipse=(1.0, 1.25),
                              jitter=0.7, width=(0.003, 0.014) if late else (0.002, 0.008), seed=100 + i)
        depth = 0.8 * rig.pose(f).depth(chest[f])
        ob = fx.overlay(f"focus{i}", cam, tris, strong if late else pale, depth=depth, coll=coll)
        fx.show(ob, [f, f + 1], ctx.f0 - 1, ctx.f1)

    clash.tick("speed lines")
    # the storm's light: the sky's rim from above and the river, the lantern far behind him at the left
    clash.composite(ctx, actors, lambda f: dict(rims=[((-1.0, 0.3), LANTERN_RIM, 0.35, 0.003, 0.9),
                                                      ((0.4, 1.0), SKY_RIM, 0.28, 0.003, 0.9)],
                                                para_from=(0.6, 0.85), para_to=(0.4, 0.1)))
    clash.tick("composite")
