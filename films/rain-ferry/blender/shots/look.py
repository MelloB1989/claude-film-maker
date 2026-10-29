"""Shot 11, look (47.8-51.8 s): her eyes are the shot. A close-up of Tsuru, her face still turned out to the river and
down, as tap left it; her eyes come up first, then her head comes round over her right shoulder to him, through the
lens's side, until she is looking up at him past the camera (screen left, where he stands). "...Forty years ago."
(48.8 s), with the faint smile; the drone comes in under it (data/score.json). Then a held breath on her eyes, the
heavy lids lifting a little: the River Demon looks out of them. The camera creeps in from a close-up to a tight one.

    blender -b -P blender/render.py -- --film rain-ferry --shot look --mode look --engine eevee \\
        --frames 1150,1172,1200,1240 --res 960x540
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "look"}

EYES_UP = (0.3, 0.62)        # her eyes lift (s into the shot) ...
TURN = (0.45, 1.35)          # ... then her head comes round to him
LIDS = (2.95, 3.4)           # the lids lift: the old swordsman looks out
SMILE = (1.0, 2.0)
BLINKS = (2.85,)
# how far round she turns (degrees to her right: the rest of the way to his face is her eyes'), and up
TURN_BODY, TURN_EYES = -80.0, -16.0
UP_HEAD, UP_EYES = -22.0, -10.0
# the camera, from her face: its bearing (degrees from +x) and distance, start and end; the lens; how far the aim sits
# left of her face (m, room on the side she looks to) and how far below it the lens is
BEARING, DIST, LENS = 226.0, (1.3, 0.98), [(0.0, 68.0), (4.0, 80.0)]
LEAD, DROP = 0.045, 0.03


def build(ctx):
    st = jt.stage(ctx, who=("tsuru",), rain_box=((4.0, -4.0, -0.6), (10.0, 6.0, 3.6)), clear=0.6, near=2.2)
    jt.compose_faces(st)
    perform(st, st.line("L08"))
    face = st.head_at("tsuru", ctx.f0)
    b = np.radians(BEARING)
    out = np.array((np.cos(b), np.sin(b), 0.0))
    left = np.array((-out[1], out[0], 0.0)) * -1.0      # screen left, seen from out there
    path = [(0.0, tuple(face + out * DIST[0] - (0, 0, DROP)), tuple(face + left * LEAD * 0.4)),
            (4.0, tuple(face + out * DIST[1] - (0, 0, DROP)), tuple(face + left * LEAD + (0, 0, 0.01)))]
    shot = jt.Shot(path, LENS, [(0.0, 2.2), (4.0, 2.0)], breath=0.0022)
    st.camera(shot, st.tracked_focus("tsuru", every=4))
    jt.outline(st, shot)
    jt.key_light(st, "tsuru", (-0.9, -0.6, 0.65))
    st.composite(lambda f: dict(rims=[((1.0, 0.5), (0.6, 0.68, 0.85), 0.4, 0.0035, 0.9),
                                      ((-0.6, 1.0), (0.6, 0.68, 0.85), 0.15, 0.003, 0.9)],
                                para_from=(0.7, 0.95), para_to=(0.2, 0.05)))


def perform(st, lines):
    speak = [lines["L08"]]
    lap, lap_along = jt.TS_PIPE_LAP
    for f in st.frames():
        t = st.t(f)
        up, turn, lids = jt.ramp(t, *EYES_UP), jt.ramp(t, *TURN), jt.ramp(t, *LIDS)
        body = jt.tsuru_sit(t, turn=4.0 * (1 - turn) + TURN_BODY * turn, down=10.0 * (1 - turn) + UP_HEAD * turn,
                            eyes=(16.0 * (1 - up) + UP_EYES * up, -4.0 * (1 - up) + TURN_EYES * up))
        st.pose("tsuru", f, {**body, **jt.fingers("left", 0.85), **jt.fingers("right", 0.35)}, hips=jt.tsuru_hips(st, t))
        jt.hold_pipe(st, f, lap, lap_along)
        jt.knee_hand(st, f)
        st.face("tsuru", f, {"s4-calm": 1.0 - 0.45 * lids, "s4-smile": 0.35 + 0.45 * jt.ramp(t, *SMILE),
                             "blink": jt.blink(t, BLINKS), **jt.mouth_weights(t, speak, seed=11, scale=0.4)})
