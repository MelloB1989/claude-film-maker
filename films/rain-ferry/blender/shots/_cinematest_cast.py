"""A test of the camera and the weather kits with the 3D cast in frame (blender/lib/cinema.py, weather.py), not a shot
of the film: the standoff's 4.5 s of downpour (its lightning at 2.1 s) at the talk's marks on the jetty's end (Tsuru on
her crate, Shinza behind her shoulder: rf/jetty_talk.py's stage). A wide from the river side, pushing in on the two of
them, then a cut to an 85 mm close-up on Shinza's face, Tsuru soft in the foreground; the lightning jolts it. The rain
falls in the cast's compositing layer as well (weather.storm(cast=...)), so the drops between the lens and a face stay
in front of it; the mist's banks stand back for the long lens.

    blender -b -P blender/render.py -- --film rain-ferry --shot _cinematest_cast --mode look --engine eevee \\
        --frames 1432,1470,1480,1482,1490,1530 --res 960x540
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import cinema, weather  # noqa: E402
from rf import jetty_talk as jt  # noqa: E402
from rf import sets  # noqa: E402

SHOT = {"scene": "standoff"}

CUT = 1.9          # s: the wide, then his close-up
STRIKE = 2.1       # the look schedule's lightning in this scene
SKY_RIM = (0.6, 0.68, 0.85)


def build(ctx):
    st = jt.stage(ctx, ink=0.0035)
    jt.compose_faces(st)
    for k, who in enumerate(st.cast):
        p = st.perf[who]
        p.breathe(rate=0.28 if who == "shinza" else 0.2, depth=1.3 if who == "shinza" else 0.8)
        p.blinks(seed=5 + k)
    st.perf["shinza"].look(ctx.f0, st.perf["tsuru"].face_at)     # his glare on her all through
    st.bake()
    sh, ts = st.head_at("shinza", ctx.f0), st.head_at("tsuru", ctx.f0)
    mid = (sh + ts) / 2

    wide_cam = (mid[0] - 1.6, mid[1] - 4.6, 1.2)
    close_cam, close_aim = cinema.frame_on(tuple(sh), 0.24, share=0.42, lens=85, bearing=58, rise=0.02, third=-1,
                                           headroom=0.1)
    ch = st.cast["shinza"]["vrm"]
    rig = cinema.film(ctx, [
        cinema.Setup("wide", 0.0, cinema.drift(cinema.push(wide_cam, tuple(mid - (0, 0, 0.35)), 1.2), 0.02),
                     lens=35, fstop=4.0, focus=tuple(mid), shake=cinema.Shake(breath=0.08)),
        cinema.Setup("mcu", CUT, cinema.push(close_cam, close_aim, 0.12), lens=85, fstop=2.2, focus=(ch, "head"),
                     shake=cinema.Shake(breath=0.05, hits=((STRIKE, 0.9),), seed=9)),
    ], clip=(0.02, 4000.0))
    st.rig = rig
    deck = ((sets.SPAN[0], -sets.HALF + 0.05, 0.004), (sets.SPAN[1], sets.HALF - 0.05, 0.004))
    weather.storm(ctx, rig, splashes=[deck], waters=st.crossing["waters"], floor=sets.WATER_Z, ground=sets.WATER_Z,
                  lights=[st.crossing["key"]], cast=st.cast_coll)
    jt.outline(st)

    def setup(f):
        if rig.setup_at(f) == "wide":
            return {"rims": [((0.2, 1.0), SKY_RIM, 0.2, 0.002, 0.8)]}
        return {"rims": [((0.6, 1.0), SKY_RIM, 0.3, 0.003, 0.9)], "para_from": (0.7, 0.85), "para_to": (0.2, 0.12)}

    st.composite(setup)
    print(f"_cinematest_cast: cuts {rig.cuts}; shinza's eyes {np.round(sh, 2)}, tsuru's {np.round(ts, 2)}")
