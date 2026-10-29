"""Shot 4, walk (12.5-18 s): Shinza walks down the mountain path out of the mist toward us, the kasa low over his
face, the rain sheeting off its rim. On a long lens from low on the path: the rain between us and him compressed into
a curtain, his silhouette grey in the mist at first and resolving as he comes, the pines either side. A heavy,
purposeful walk; his inner voice (line 1, "I want to be strong.", 14.1-16.91 s) over it, his right hand closing into a
fist as he says it, and at the end his head coming up, the brim lifting off his eyes: the cut to them.

The path, the walk and his kasa are rf/approach.py's (stand-ins until the sets, anim and cast agents' are merged).
"""
from __future__ import annotations

import math

SHOT = {"scene": "walk"}

LENS = (150.0, 165.0)          # mm: a slow creep in over the shot as the camera dollies
CAM_AT = 0.55                  # where the camera stands along the path (of its length: rf/set_world.views' walk)
CAM_SIDE, CAM_Z = 0.35, 0.95   # ... to the side of its middle (toward the river), and how high off the ground
DOLLY = 1.4                    # m the camera comes in toward him over the shot
END = 22.0                     # m short of the camera he is when the shot cuts
FSTOP = 2.8
AIM_Z = 1.15                   # the camera aims at his chest, trailing him a little (an operator's follow)
FOLLOW = 0.35                  # s: how far behind him the aim lags
FIRST_STEP = 0.2               # s into the shot his first footfall lands (the steps' sound at 12.7 s)
FIST = (1.6, 0.6)              # s into the shot: his right hand closes on "I want to be strong" (from, over)
HEAD_UP = (4.5, 0.9, -9.0)     # ... and his head comes up at its end (from, over, degrees down to up)
# the air between the lens and him: thick in the mist at the far end of the path, thinning as he comes
HAZE = ((28.0, 0.55), (21.0, 0.12))   # (his distance from the lens, the satsuei's haze) at its far and near ends
RIMS = [((0.3, 1.0), (0.6, 0.68, 0.85), 0.3, 0.003, 0.9), ((-1.0, 0.2), (0.6, 0.68, 0.85), 0.18, 0.0025, 0.9)]
KEY = (0.6, -0.5, 0.8)         # his key: overcast, from above, a little from our side


def staging(fps: float, t_shot: float, t_end: float):
    """(gait, camera's start, its way along the path toward him) for the shot: his walk laid on the path so he is END
    short of the camera at the cut."""
    from rf import approach, set_approach, set_valley

    P = set_approach.path_xy(240)
    s_cam = approach.arc(P)[int(len(P) * CAM_AT)]
    probe = approach.Gait(line=P, ground=set_valley.ground)
    c, d = probe.at(s_cam)
    t0 = t_shot + FIRST_STEP
    u_end = (t_end - t0) / probe.step
    s0 = s_cam - END - probe.stride * (u_end - 0.5)
    gait = approach.Gait(line=P, ground=set_valley.ground, s0=s0, t0=t0)
    side = -approach.Gait.left_of(d) * CAM_SIDE          # his right as he comes: the river's side
    cam = (c[0] + side[0], c[1] + side[1], float(set_valley.ground(*c)) + CAM_Z)
    return gait, cam, (-d[0], -d[1])


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    import numpy as np
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, satsuei, vrm, vrm_anim as va
    from rf import approach

    t_shot = ctx.time(ctx.f0)
    gait, cam0, back = staging(ctx.fps, t_shot, ctx.time(ctx.f1))
    p0, p1 = gait.root(t_shot)[0], gait.root(ctx.time(ctx.f1))[0]
    st = approach.stage(ctx, key_toward=KEY, ink=0.004)
    ch = st.shinza["vrm"]

    # mid-stride down the path at the cut (lib/vrm_anim.py's heavy walk), his head low under the kasa; his right
    # hand closing into a fist on the line, his head coming up at its end
    from rf import set_approach, set_valley

    p = va.Performance(ch, fps=ctx.fps, seed=1)
    t1 = ctx.time(ctx.f1)
    carriage = {**va.STAND, **approach.LEAN}
    approach.walk_through(p, set_approach.path_xy(240), side="right", at=p1, t=t1, before=7.0, after=2.0,
                          ground=set_valley.ground, pose=carriage)

    def at_s(u):
        return ctx.f0 + u * ctx.fps

    relaxed = {k: v for k, v in va.STAND.items() if any(f in k for f in ("Index", "Middle", "Ring", "Little", "Thumb"))
               and k.startswith("right")}
    p.pose(at_s(FIST[0]), relaxed, full=False)
    p.pose(at_s(FIST[0] + FIST[1]), vrm.grip_pose("right", 1.0, 0.8), full=False, ease="out")
    lean = {k: approach.LEAN[k] for k in ("neck", "head")}
    p.pose(at_s(HEAD_UP[0]), lean, full=False)
    p.pose(at_s(HEAD_UP[0] + HEAD_UP[1]), {"neck": (lean["neck"][0] + HEAD_UP[2] * 0.4, 0.0, 0.0),
                                          "head": (lean["head"][0] + HEAD_UP[2], 0.0, 0.0)}, full=False, ease="out")
    p.express(ctx.f0 - 1, st.shinza["face"](1.0))
    p.blinks(mean=4.0)
    p.secondary(wind=(0.6, 0.0, 0.0))
    p.bake(ctx.f0 - 1, ctx.f1 + 1)

    # a long lens low on the path, dollying in toward him as he comes, its aim trailing him (an operator's follow)
    ts = np.linspace(t_shot, t1, 12)
    aims = [tuple(p.root_at((t - FOLLOW) * ctx.fps)[0] + np.array([0.0, 0.0, AIM_Z])) for t in ts]
    cam1 = np.array(cam0) + np.array([*back, 0.0]) * DOLLY
    cams = [tuple(np.array(cam0) + (cam1 - np.array(cam0)) * k) for k in np.linspace(0, 1, 12)]
    rig = cinema.film(ctx, [cinema.Setup("walk", 0.0, cinema.path(cams, aims), ease="linear", lens=LENS, fstop=FSTOP,
                                         focus=(ch, "chest"), shake=cinema.Shake(breath=0.02))])
    sky = approach.storm(ctx, rig, st, ground=float(gait.z(p0)))
    hat = st.shinza["kasa"][0]
    approach.brim_drips("brim", hat, n=14, period=0.45, hang=0.25, fall=1.6, size=0.01, coll=st.cast)

    comp = satsuei.setup(ctx.scene, st.cast)
    for f in rig.frames:
        at = Vector(tuple(rig.pose(f).position))
        r = p.root_at(f)[0]
        # the mist thinning off him as he comes
        d = (Vector((r[0], r[1], r[2] + 1.2)) - at).length
        (d0, h0), (d1, h1) = HAZE
        haze = h1 + (h0 - h1) * min(1.0, max(0.0, (d - d1) / (d0 - d1)))
        s = ctx.look_at(f)
        comp.key(f, s.look(rims=[satsuei.Rim(*r_) for r_ in RIMS], haze_amount=haze, para_from=(0.5, 0.9),
                           para_to=(0.5, 0.05)))
    comp.hold()
    print(f"walk: he walks {tuple(p0.round(2))} -> {tuple(p1.round(2))}, the camera at {tuple(round(v, 2) for v in cam0)}"
          f", rain {'on' if sky.rain else 'off'}")
