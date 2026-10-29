"""Shot 6, ferry (21.5-27.0 s): the crossing in the rain, wide. From up the muddy bank, the whole place of the duel:
the thatched hut at the left with its red lantern, the 「渡し」 signpost, the jetty running out into the river, the
covered boat moored alongside, and at the jetty's end, small, a caped figure sitting on a crate and smoking, her smoke
a pale thread the rain keeps knocking down; ridge after ridge of mountains fading into the mist beyond. Shinza comes
into the bottom of the frame, his back to us under his kasa, and walks on down the path to the jetty's foot. The
camera eases in and down a little, as if it took a step after him.

The scene is rf/jetty_talk.py's (Tsuru on her mark at the jetty's end), the set rf/set_world.py's (its "ferry"
view), its camera and weather lib/cinema.py's and lib/weather.py's; his walk is rf/jetty_arrive.py's.

    blender -b -P blender/render.py -- --film rain-ferry --shot ferry --mode look --engine eevee \\
        --frames 516,560,600,640 --res 960x540
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import cinema  # noqa: E402
from rf import jetty_arrive as ja  # noqa: E402
from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "ferry"}

# the camera: rf/set_world.py's "ferry" view, easing in and down a step over the shot
CAM = ((-15.5, -11.5, 3.6), (-14.6, -10.7, 3.3), (2.0, 4.0, 0.0), (2.4, 3.7, 0.15))   # camera from, to; aim from, to
LENS = (26.0, 27.0)
FSTOP = 8.0
FOCUS = 22.0                # m: deep focus on the whole crossing
# Shinza down the last of the path to the jetty's foot: how far back along the path he starts (m), and when he
# would stand still at its end (s into the shot: after the cut, so he is walking all through it)
WALK_BACK, WALK_END = 8.0, 6.6
# her smoke, made larger than life so a thread reads from this far (she is ~25 m off)
WISP = dict(width=(0.01, 0.16), life=3.4, rise=0.3, curl=0.12, rate=24.0, opacity=0.45)
EXHALE = (2.6, 3.4)          # s into the shot: she lets out a breath of smoke


def build(ctx):
    from lib import smoke
    from rf import set_approach, set_valley

    st = jt.stage(ctx, ink=0.006, variant={"shinza": {"kasa": "on"}}, place={"shinza": None})
    jt.compose_faces(st)
    # Shinza down the last of the path, still walking at the cut
    P = set_approach.path_xy()
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    path = P[d >= d[-1] - WALK_BACK]
    way = path[-1] - path[-2]
    sh, _ = ja.arrives(st, path, WALK_END, end_yaw=float(np.degrees(np.arctan2(way[1], way[0]))),
                       ground=lambda x, y: float(set_valley.ground(x, y)))
    sh.look(ctx.f0, None)
    sh.express(ctx.f0, {"glare": 0.6})
    sh.blinks(mean=3.4)
    sh.breathe(rate=0.3, depth=1.3)
    sh.secondary(wind=(0.4, 1.2, 0.0))
    # Tsuru smoking at the jetty's end; her head back a little as she lets a breath of smoke out
    for f in st.frames():
        t = st.t(f)
        out = jt.ramp(t, EXHALE[0] - 0.25, EXHALE[0]) - jt.ramp(t, EXHALE[1], EXHALE[1] + 0.4)
        ja.smoking(st, f, t, down=-4.0 * out)
    st.bake()

    st.film([cinema.Setup("ferry", 0.0, cinema.drift(cinema.line(*CAM), 0.03), lens=LENS, fstop=FSTOP, focus=FOCUS,
                          shake=cinema.Shake(breath=0.04))])
    jt.outline(st)
    jt.key_light(st, "tsuru", (-0.4, -1.0, 0.8))
    jt.key_light(st, "shinza", (0.5, -1.0, 0.8))
    st.composite(lambda f: dict(rims=[((-0.2, 1.0), (0.6, 0.68, 0.85), 0.2, 0.0015, 0.8)], para=(0.52, 0.55, 0.7),
                                para_from=(0.5, 0.7), para_to=(0.5, 0.05), para_amount=0.25, wrap=0.08,
                                wrap_width=0.003, haze_amount=0.06))

    s = ctx.look_at(ctx.f0)
    bowl = st.cast["tsuru"]["parts"]["pipe"][-1]
    co = np.array([v.co for v in bowl.data.vertices])
    top = co[co[:, 2] >= co[:, 2].max() - 0.002].mean(axis=0)
    wisp = smoke.Wisp(rain=min(1.0, s.rain.density), wind=(0.12, 0.05, 0.0), seed=3, **WISP)
    smoke.ribbon("pipe-smoke", wisp, source=bowl, offset=tuple(top), coll=st.crossing["near"], also=(st.cast_coll,),
                 color=tuple(np.array(s.light.fog) * ja.SMOKE)).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
    pose = {**jt.tsuru_sit(0.0), **jt.fingers("left", 0.85)}
    ja.breath(st, [EXHALE], ja.lips_source(st, pose, jt.tsuru_hips(st, 0.0)), push=0.35, width=(0.02, 0.22),
              opacity=0.4).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
