"""Shot 3, step (10-12.5 s): at the level of the ground, a straw sandal comes down into a puddle on the path. The
splash (on the sound, 10.2 s) throws water up round it, rings run out across the puddle and break the sky and the
hakama's hem mirrored in it; the weight comes onto the foot, the heel rises and the foot peels up out of the water,
dripping, and goes on past us, the other leg sweeping by the lens out of focus. The rings settle, the rain goes on
ringing the water. Low, close and tactile: the lens a hand's height off the water, looking up the path into the mist.

The path, the walk, the sandals and the water are rf/approach.py's (stand-ins until the sets, anim, cast and cinema
agents' are merged).
"""
from __future__ import annotations

import math

SHOT = {"scene": "step"}

STRIKE = 0.2                   # s into the shot: the right foot lands in the puddle (the splash's sound at 10.2 s)
# the lens, in his frame from where the foot lands (ahead of him, to his right, up off the ground), easing in; the aim,
# a little behind the foot and up (back down the path into the mist)
CAM = ((0.82, -0.3, 0.14), (0.74, -0.27, 0.13))   # (ahead, left, up) m: high enough to see into the water
LOOK = (-0.12, 0.02, 0.085)
LENS, FSTOP = 40.0, 2.8
SHAKE = (0.0035, 0.18)         # the lens shaken by the footfall: metres at its peak, dying over seconds
KEY = (-0.5, -0.7, 0.9)        # his key: overcast from above our shoulder
RIMS = [((0.4, 1.0), (0.6, 0.68, 0.85), 0.35, 0.0035, 0.9), ((1.0, 0.1), (0.5, 0.55, 0.65), 0.15, 0.003, 0.9)]


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    import numpy as np
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import rig, satsuei, toon, vrm
    from rf import approach, set_approach, set_valley, set_world

    # the puddle he steps in (the set's); his right foot's footfall on it, the path's way there
    puddle = np.array(set_world.views()["step"][1]) - np.array([0.0, 0.0, 0.05])
    P = set_approach.path_xy(240)
    probe = approach.Gait(line=P, ground=set_valley.ground)
    s_hit = probe.nearest(puddle[:2])
    _, fwd = probe.at(s_hit)
    left = approach.Gait.left_of(fwd)

    def place(v):
        """A point of the shot's frame ((ahead, left, up) from the puddle) in the world."""
        xy = puddle[:2] + fwd * v[0] + left * v[1]
        return (float(xy[0]), float(xy[1]), float(set_valley.ground(*xy)) + v[2])

    lo = np.minimum(puddle[:2] - 3.0, puddle[:2] - fwd * 12)
    hi = np.maximum(puddle[:2] + 3.0, puddle[:2] - fwd * 12)
    st = approach.stage(ctx, rain_box=((lo[0], lo[1], puddle[2] - 0.2), (hi[0], hi[1], puddle[2] + 3.0)),
                        rain_near=3.0, rain_clear=0.6, key_toward=KEY)
    ch = st.shinza["vrm"]
    t0 = ctx.time(ctx.f0)
    t_strike = t0 + STRIKE
    # his right foot comes down in the puddle: his line runs its foot's width left of it, the ankle a little behind
    # the middle (the ball, not the heel, over the deepest water)
    gait = approach.Gait(line=P, ground=set_valley.ground, s0=s_hit + 0.06, t0=t_strike)
    _, _, land, _ = gait.footfall(0)
    off = puddle[:2] - land
    gait = approach.Gait(line=P + off - fwd * (off @ fwd), ground=set_valley.ground, s0=s_hit + 0.06, t0=t_strike)
    frames = list(range(ctx.f0 - 1, ctx.f1 + 1))
    approach.key_walk(ch, gait, frames, ctx.fps)
    vrm.express(ch, st.shinza["face"](1.0))

    # the water: the splash and its rings as the foot lands, smaller rings and drips from the sole as it lifts out
    _, _, land, _ = gait.footfall(0)
    ankle = float(ch.rest("rightFoot")[2])
    ball = abs(float((ch.rest("rightToes") - ch.rest("rightFoot"))[1])) if ch.has("rightToes") else 0.12
    hit = (*(land + fwd * 0.05), float(puddle[2]))
    approach.splash("splash", hit, t_strike, ctx.fps, coll=st.cast, frames=frames, count=140, speed=(0.45, 1.3),
                    size=0.0032, alpha=0.5, seed=3)
    approach.ripples("rings", hit, t_strike, ctx.fps, coll=st.world["near"], frames=frames, rings=4, squash=0.95)
    lift = t_strike + gait.stance * 2 * gait.step
    toe = (*(land + fwd * ball), float(puddle[2]))
    approach.ripples("rings-lift", toe, lift - 0.05, ctx.fps, coll=st.world["near"], frames=frames, rings=2, speed=0.22,
                     alpha=0.4)

    def sole(t):
        a, _ = gait.foot("right", t, ankle, ball)
        return [tuple(np.array([*(a[:2] + fwd * ah + left * al), a[2] - ankle + 0.004]))
                for ah, al in ((0.1, 0.02), (0.05, -0.03), (-0.05, 0.0), (0.0, 0.025))]

    approach.drips("sole-drips", None, lift - 0.1, lift + 0.6, ctx.fps, coll=st.cast, frames=frames,
                   every=(0.12, 0.3), fall=0.4, size=0.0035, carry=sole, seed=11)
    # drops landing on the path behind the foot (none between it and the lens: a crown that near is a smear)
    for i, (near_, far_, n_, size_) in enumerate(((0.35, 3.0, 160, 0.03), (3.0, 12.0, 260, 0.05))):
        ends = np.array([puddle[:2] - fwd * near_, puddle[:2] - fwd * far_])
        lo_, hi_ = ends.min(axis=0) - 1.2, ends.max(axis=0) + 1.2
        toon.splashes(f"splash-path{i}", (lo_[0], lo_[1], puddle[2] - 0.02), (hi_[0], hi_[1], puddle[2] - 0.02),
                      count=n_, size=size_, alpha=0.4, seed=5 + i)

    cam = rig.engine_camera("camera", fstop=FSTOP, size=ctx.size)
    cam.data.lens = LENS
    cam.data.clip_start = 0.01
    cam.data.clip_end = 3000.0
    ctx.scene.camera = cam
    aim = bpy.data.objects.new("aim", None)
    ctx.scene.collection.objects.link(aim)
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"
    focus = bpy.data.objects.new("focus", None)
    ctx.scene.collection.objects.link(focus)
    focus.location = (hit[0], hit[1], hit[2] + 0.05)
    cam.data.dof.focus_object = focus
    rng = np.random.default_rng(2)
    jitter = rng.normal(0, 1, (len(frames), 3))
    target = Vector(place(LOOK))
    comp = satsuei.setup(ctx.scene, st.cast)
    for i, f in enumerate(frames):
        u = ctx.time(f) - t0
        k = ease(u / (ctx.f1 - ctx.f0) * ctx.fps)
        at = Vector(place(tuple(a + (b - a) * k for a, b in zip(*CAM))))
        dt = ctx.time(f) - t_strike
        shake = SHAKE[0] * math.exp(-dt / SHAKE[1]) if dt >= 0 else 0.0
        cam.location = at + Vector(tuple(jitter[i] * shake * np.array([0.4, 0.4, 1.0])))
        aim.location = target
        cam.keyframe_insert("location", frame=f)
        aim.keyframe_insert("location", frame=f)
        s = ctx.look_at(f)
        comp.key(f, s.look(rims=[satsuei.Rim(*r) for r in RIMS], para_from=(0.5, 1.0), para_to=(0.5, 0.3)))
    comp.hold()
    print(f"step: foot lands at {tuple(round(v, 3) for v in hit)} at {t_strike:.2f} s, lifts at {lift:.2f} s")
