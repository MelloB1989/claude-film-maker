"""The charge: Shinza breaks from the standoff and runs at her down the jetty, his sword swept up over his head,
roaring (line 11, the whole shot), three long splashing strides on the cues (73.35, 73.85, 74.35 s: STEPS), the water
flying from his feet, then the last stride planted and the sword thrown back to its height (the whoosh at 74.95 s)
and coming over: cut on its fall.

The camera runs ahead of him low on the river side, a wide lens close in, so he comes on fast and big through the
rain; it rumbles with his strides and is jolted by each, motion-blurred; pale focus lines converge on him on twos,
thickening as he closes.
"""
from __future__ import annotations

import math

SHOT = {"scene": "charge"}

START, END_X = 1.6, 3.9         # his x: from (rf/clash.py STANDOFF), to (when the cut falls: CLASH less his reach)
LAUNCH = 0.1                    # s before he moves
TOP_SPEED_AT = 0.5              # s: at full speed
STEPS = {"left": (0.25, 1.25), "right": (0.75, 1.75)}   # s: each foot's contacts (data/mix.json step_puddle cues)
STRIDE = 1.0                    # s a foot's cycle takes
SWING = (1.55, 1.82, 2.0)       # s: the sword thrown back from, at its height, coming over
CAM = [(0.0, (START + 2.1, -2.45, 0.55)), (1.0, (START + 2.75, -1.75, 0.62)), (2.0, (END_X + 0.85, -0.95, 0.78))]
LENS, FSTOP = 24.0, 2.8
SHUTTER = 0.5
RUMBLE, JOLT = 0.004, 0.012
# his frame: front -y, left +x, up z (rf/vroid_shinza.py; lib/vrm.py's turns)
GUARD = dict(pommel=(0.01, -0.16, 0.96), hilt=(0.0, -0.91, -0.45))
SWORDS = [(0.0, (0.01, -0.16, 0.96), (0.0, -0.91, -0.45)),        # the guard
          (0.32, (0.04, -0.12, 1.58), (0.05, 0.35, 0.94)),        # swept up over his head (jodan)
          (SWING[0], (0.04, -0.12, 1.58), (0.05, 0.35, 0.94)),
          (SWING[1], (0.04, -0.02, 1.62), (0.05, 0.8, 0.6)),      # thrown back
          (SWING[2], (0.03, -0.32, 1.45), (0.0, -0.45, 0.89))]    # coming over
FOOT = {   # a foot's cycle from its contact (s after it): (y, z, heel up degrees)
    "keys": [(0.0, (-0.32, 0.09, 0.0)), (0.27, (0.3, 0.14, 38.0)), (0.5, (0.05, 0.4, 10.0)), (0.78, (-0.46, 0.24, -18.0)),
             (1.0, (-0.32, 0.09, 0.0))]}
SIDE_X = {"left": 0.13, "right": -0.13}
GUARD_FEET = {"right": ((-0.12, -0.36, 0.095), (0.0, 0.0, -8.0)), "left": ((0.15, 0.4, 0.16), (32.0, 0.0, 30.0))}
RUN_POSE = {"hips": (0.0, 0.0, 0.0), "spine": (14.0, 0.0, 0.0), "chest": (8.0, 0.0, 0.0), "upperChest": (2.0, 0.0, 0.0),
            "neck": (-8.0, 0.0, 0.0), "head": (-14.0, 0.0, 0.0),
            "leftShoulder": (0.0, -6.0, -6.0), "rightShoulder": (0.0, 6.0, 6.0)}
TWIST = 7.0                     # degrees the hips and chest turn against each other with the strides
CRY = {"angry": 0.9, "aa": 1.0}
SKY_RIM, LANTERN_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18)


def x_at(t: float) -> float:
    """His x at t: still, then accelerating to full speed by TOP_SPEED_AT, reaching END_X at 2 s."""
    ramp = TOP_SPEED_AT - LAUNCH

    def dist(t):
        if t <= LAUNCH:
            return 0.0
        if t <= TOP_SPEED_AT:
            return (t - LAUNCH) ** 2 / (2 * ramp)
        return ramp / 2 + (t - TOP_SPEED_AT)
    return START + (END_X - START) * dist(t) / dist(2.0)


def foot_at(side: str, t: float):
    """(ankle (his frame), heel-up degrees) of a foot at t: the guard's until it moves, then its stride cycle."""
    from rf import clash

    first = STEPS[side][0]
    cyc = [(k, v) for k, v in FOOT["keys"]]
    if side == "left":
        # the back foot pushes off and comes through at once: the launch step is the cycle's swing, quickened
        if t < first:
            u = t / first
            g, heel0 = GUARD_FEET["left"]
            y = g[1] + (cyc[-1][1][0] - g[1]) * clash.ease(u)
            z = g[2] + 0.3 * math.sin(math.pi * u)
            return (SIDE_X[side], y, z), heel0[0] * (1 - u)
    else:
        if t < first - STRIDE:
            pass
        if t < first:
            # the front foot stays planted (sliding back under him as he goes) until it leaves on its swing
            u = (t - (first - STRIDE)) / STRIDE
            if t < 0.3:
                g = GUARD_FEET["right"][0]
                k = clash.ease(t / 0.3)
                y = g[1] + (cyc[1][1][0] - g[1]) * k
                return (SIDE_X[side], y, 0.09 + 0.05 * k), 38.0 * k
            u = (t - 0.3) / (first - 0.3)
            y, z, heel = clash.keys_at([(0.0, cyc[1][1]), (0.45, cyc[2][1]), (1.0, cyc[0][1])], u)
            return (SIDE_X[side], y, z), heel
    # the stride cycle from the last contact
    last = max([c for c in STEPS[side] if c <= t] or [STEPS[side][0]])
    y, z, heel = clash.keys_at(cyc, (t - last) / STRIDE)
    return (SIDE_X[side], y, z), heel


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    import numpy as np
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import fx_impact as fx, toon, vrm
    from rf import clash

    scene = ctx.scene
    fps = ctx.fps
    n = ctx.f1 - ctx.f0
    w = clash.world(ctx, motion_blur=SHUTTER, clear=0.7, near=2.5)
    actors = clash.cast(ctx, w, {"shinza": {"sword": "hand"}, "tsuru": {"pole": "hand"}})
    sh, ts = actors["shinza"], actors["tsuru"]
    ch = sh["vrm"]
    # she waits at the far end, out of focus beyond him
    ts["root"].location = (clash.STANDOFF["tsuru"][0], clash.STANDOFF["tsuru"][1], 0.0)
    ts["root"].rotation_euler = (0.0, 0.0, math.pi)
    _, fingers = clash.shinza_sword(ch, GUARD["pommel"], GUARD["hilt"])

    def pose_at(t: float) -> clash.Pose:
        pommel = clash.keys_at([(k, p) for k, p, _ in SWORDS], t)
        hilt = clash.keys_at([(k, h) for k, _, h in SWORDS], t)
        hands, _ = clash.shinza_sword(ch, pommel, hilt, poles={"left": (0.6, 0.3, 1.2), "right": (-0.6, 0.2, 1.2)})
        feet = {}
        for side in ("left", "right"):
            (x, y, z), heel = foot_at(side, t)
            feet[side] = ((x, y, z), (SIDE_X[side] * 1.5, -1.2, 0.55), (heel, 0.0, 0.0))
        # the body: dropping into the launch, then bouncing with the strides (lowest just after a contact), leaning in,
        # hips and chest twisting against each other
        run = clash.ease(t / 0.3)
        phase = 2 * math.pi * (t - STEPS["left"][0]) / (STRIDE / 2)
        bounce = -0.13 - 0.035 * math.cos(phase - 0.6)
        hips = (0.0, -0.04 - 0.04 * run, -0.15 + (bounce + 0.15) * run)
        tw = TWIST * math.sin(2 * math.pi * (t - STEPS["left"][0]) / STRIDE) * run
        turns = {**{k: tuple(v * run for v in val) for k, val in RUN_POSE.items()},
                 "hips": (6.0 * run, 0.0, tw), "chest": (8.0 * run, 0.0, -tw), "head": (-14.0 * run, 0.0, 0.0)}
        if t > SWING[0]:
            # the last stride: the trunk rears back as the sword goes up, then drives over
            k = clash.ease((t - SWING[0]) / (SWING[1] - SWING[0])) - 1.6 * clash.ease((t - SWING[1]) / (SWING[2] - SWING[1]))
            turns["spine"] = (14.0 - 14.0 * k, 0.0, 0.0)
            turns["chest"] = (8.0 - 10.0 * k, 0.0, -tw)
        return clash.Pose(at=(x_at(t), 0.0), hips=hips, turns=turns, hands=hands, feet=feet)

    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / fps
        clash.apply(sh, pose_at(t), fingers=fingers)
        cry = clash.ease((t - 0.02) / 0.12) * (1.0 - 0.3 * clash.ease((t - 1.76) / 0.15))
        clash.key(sh, f)
        try:
            vrm.express(ch, {k: v * cry for k, v in CRY.items()}, frame=f)
        except KeyError:
            vrm.express(ch, sh["face"](1.0), frame=f)

    # ---- the water from his feet: a burst at each contact (and off the back foot as it pushes)
    coll = toon.collection("fx")
    water = fx.unlit("thrown-water", tuple(w["state"].rain.color), alpha=0.55, strength=1.1)
    for side, contacts in STEPS.items():
        for i, tc in enumerate(contacts):
            scene.frame_set(ctx.f0 + round(tc * fps))
            at = ch.handles[f"{side}Foot-target"].matrix_world.translation.copy()
            at.z = 0.01
            for f in range(ctx.f0 + round(tc * fps), min(ctx.f1, ctx.f0 + round((tc + 0.5) * fps))):
                dt = (f - ctx.f0) / fps - tc
                p, v = fx.burst(70, dt + 0.5 / fps, origin=tuple(at), up=(1.0, 2.8), out=(0.4, 1.8), seed=40 + i * 2 +
                                (side == "left"))
                if not len(p):
                    continue
                ob = fx.droplets(f"splash-{side}{i}-{f}", p, v, water, size=0.01, stretch=0.01, coll=coll)
                fx.show(ob, [f], ctx.f0 - 1, ctx.f1)

    # ---- the camera: running ahead of him, low, jolted by his strides
    cam, aim = clash.camera(ctx, fstop=FSTOP)
    cam.data.lens = LENS
    fo = clash.focus(ctx, cam)
    cams, chest = {}, {}
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / fps
        x = x_at(t)
        c = clash.keys_at(CAM, t, interp=lambda u: u)
        body = Vector((x + 0.25, 0.0, 1.18))
        cam.location, aim.location, fo.location = c, body + Vector((0.12, 0.0, 0.08)), Vector((x, 0.0, 1.3))
        for ob in (cam, aim, fo):
            ob.keyframe_insert("location", frame=f)
        cams[f], chest[f] = c, Vector((x, 0.0, 1.25))
    env = np.full(n + 2, RUMBLE)
    for contacts in STEPS.values():
        for tc in contacts:
            env += fx.jolt(n + 2, round(tc * fps) + 1, JOLT, decay=9.0)
    fx.shake_camera(cam, fx.shake(env, freq=8.0, seed=5), ctx.f0 - 1)
    clash.outlines(ctx, actors, lambda f: cams[f], lambda f: LENS)

    # ---- focus lines on him, on twos, pale as the rain, thickening as he closes
    aspect = ctx.size[0] / ctx.size[1]
    pale = fx.unlit("speed-pale", (0.82, 0.85, 0.9), alpha=0.28)
    strong = fx.unlit("speed-strong", (0.86, 0.89, 0.94), alpha=0.5)
    for i, f in enumerate(range(ctx.f0 + round(0.3 * fps), ctx.f1, 2)):
        scene.frame_set(f)
        uv = world_to_camera_view(scene, cam, chest[f])
        centre = ((uv.x - 0.5) * aspect, uv.y - 0.5)
        late = (f - ctx.f0) / fps > 1.3
        tris = fx.focus_lines(90 if late else 60, center=centre, inner=0.42 if late else 0.5, ellipse=(1.0, 1.25),
                              jitter=0.7, width=(0.003, 0.014) if late else (0.002, 0.008), seed=100 + i)
        # just in front of where the lens is focused: drawn over him, and sharp
        depth = 0.8 * (Vector(cams[f]) - chest[f]).length
        ob = fx.overlay(f"focus{i}", cam, tris, strong if late else pale, depth=depth, coll=coll)
        fx.show(ob, [f, f + 1], ctx.f0 - 1, ctx.f1)

    # the storm's light: the sky's rim from above and the river, the lantern far behind him at the left
    clash.composite(ctx, actors, lambda f: dict(rims=[((-1.0, 0.3), LANTERN_RIM, 0.35, 0.003, 0.9),
                                                     ((0.4, 1.0), SKY_RIM, 0.28, 0.003, 0.9)],
                                                para_from=(0.6, 0.85), para_to=(0.4, 0.1)))
