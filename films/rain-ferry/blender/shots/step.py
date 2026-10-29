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
CAM = ((0.66, -0.34, 0.11), (0.6, -0.31, 0.105))   # (ahead, left, up) m: high enough to see into the water
LOOK = (0.0, 0.0, 0.07)
LENS, FSTOP = 45.0, 2.8
SINK = 0.045                   # m his feet go down into the mud: the sole under the puddle's water, not on it
SHAKE = 0.35                   # degrees the footfall jolts the lens (cinema.Shake's hit)
KEY = (-0.5, -0.7, 0.9)        # his key: overcast from above our shoulder
RIMS = [((0.4, 1.0), (0.6, 0.68, 0.85), 0.35, 0.0035, 0.9), ((1.0, 0.1), (0.5, 0.55, 0.65), 0.15, 0.003, 0.9)]


def build(ctx):
    import sys
    from pathlib import Path

    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, satsuei, vrm_anim as va
    from rf import approach, set_approach, set_valley, set_world

    # the puddle he steps in (the set's); his right foot's footfall on it, the path's way there
    puddle = np.array(set_world.views()["step"][1]) - np.array([0.0, 0.0, 0.05])
    P = set_approach.path_xy(240)
    probe = approach.Gait(line=P)
    s_hit = probe.nearest(puddle[:2])
    _, fwd = probe.at(s_hit)
    left = approach.Gait.left_of(fwd)

    def place(v):
        """A point of the shot's frame ((ahead, left, up) from the puddle) in the world."""
        xy = puddle[:2] + fwd * v[0] + left * v[1]
        return (float(xy[0]), float(xy[1]), float(set_valley.ground(*xy)) + v[2])

    st = approach.stage(ctx, key_toward=KEY)
    ch = st.shinza["vrm"]
    t0 = ctx.time(ctx.f0)
    t_strike = t0 + STRIKE
    # his right foot comes down in the puddle, mid-stride (lib/vrm_anim.py's heavy walk, laid so), his feet going
    # down into the mud and water
    p = va.Performance(ch, fps=ctx.fps, seed=3)
    w = approach.walk_through(p, P, side="right", at=puddle[:2], t=t_strike, before=2.5, after=2.5,
                              ground=lambda x, y: float(set_valley.ground(x, y)) - SINK)
    p.express(ctx.f0 - 1, st.shinza["face"](1.0))
    p.blinks(mean=3.5)
    p.secondary(wind=(0.4, 0.0, 0.0))
    p.bake(ctx.f0 - 1, ctx.f1 + 1)
    frames = list(range(ctx.f0 - 1, ctx.f1 + 1))
    plan, i = w["plan"], w["index"]
    nxt = next((k for k in range(i + 1, len(plan)) if plan[k].side == "right"), None)
    lift = (w["start"] + plan[nxt].t0 * ctx.fps) / ctx.fps if nxt is not None else t_strike + 0.75

    # the water: the splash and its rings as the foot lands, smaller rings and drips from the sole as it lifts out
    ankle = float(ch.rest("rightFoot")[2])
    ball = abs(float((ch.rest("rightToes") - ch.rest("rightFoot"))[1])) if ch.has("rightToes") else 0.12
    land = puddle[:2]
    hit = (*(land + fwd * 0.05), float(puddle[2]))
    approach.splash("splash", hit, t_strike, ctx.fps, coll=st.cast, frames=frames, count=110, speed=(0.5, 1.4),
                    size=0.0024, alpha=0.4, spread=0.12, seed=3)
    approach.ripples("rings", hit, t_strike, ctx.fps, coll=st.world["near"], frames=frames, rings=4, squash=0.95,
                     alpha=0.32, color=(0.42, 0.46, 0.52))
    toe = (*(land + fwd * ball), float(puddle[2]))
    approach.ripples("rings-lift", toe, lift - 0.05, ctx.fps, coll=st.world["near"], frames=frames, rings=2, speed=0.22,
                     alpha=0.25, color=(0.42, 0.46, 0.52))
    # where the sole is, frame by frame, as baked
    soles = {}
    for f in frames:
        ctx.scene.frame_set(f)
        a = np.array(ch.point("rightFoot"))
        soles[f] = a - np.array([0.0, 0.0, ankle - 0.004])
    ctx.scene.frame_set(ctx.f0)

    def sole(t):
        a = soles[min(max(round(t * ctx.fps), frames[0]), frames[-1])]
        return [tuple(a + np.array([*(fwd * ah + left * al), 0.0]))
                for ah, al in ((0.1, 0.02), (0.05, -0.03), (-0.05, 0.0), (0.0, 0.025))]

    approach.drips("sole-drips", None, lift - 0.1, lift + 0.6, ctx.fps, coll=st.cast, frames=frames,
                   every=(0.12, 0.3), fall=0.4, size=0.0035, carry=sole, seed=11)
    # the lens a hand off the water ahead of him, easing in; shaken by the footfall
    rig = cinema.film(ctx, [cinema.Setup("step", 0.0, cinema.line(place(CAM[0]), place(CAM[1]), place(LOOK)), lens=LENS,
                                         fstop=FSTOP, focus=(hit[0], hit[1], hit[2] + 0.05),
                                         shake=cinema.Shake(breath=0.04, hits=((STRIKE, SHAKE),)))])
    # the rain round it, and its drops landing on the path behind the foot (none between it and the lens: a crown
    # that near is a smear)
    ends = np.array([puddle[:2] - fwd * 0.35, puddle[:2] - fwd * 12.0])
    lo_, hi_ = ends.min(axis=0) - 1.2, ends.max(axis=0) + 1.2
    approach.storm(ctx, rig, st, splashes=[((lo_[0], lo_[1], puddle[2] - 0.02), (hi_[0], hi_[1], puddle[2] - 0.02))],
                   floor=float(puddle[2]) - 0.05, ground=float(puddle[2]))

    comp = satsuei.setup(ctx.scene, st.cast)
    for f in rig.frames:
        s = ctx.look_at(f)
        comp.key(f, s.look(rims=[satsuei.Rim(*r) for r in RIMS], para_from=(0.5, 1.0), para_to=(0.5, 0.3)))
    comp.hold()
    print(f"step: foot lands at {tuple(round(v, 3) for v in hit)} at {t_strike:.2f} s, lifts at {lift:.2f} s")
