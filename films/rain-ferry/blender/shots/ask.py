"""Shot 7, ask (27.0-32.0 s): Tsuru close at the right of the frame on her crate at the jetty's end, three-quarters
to us, her pipe at her lips and its smoke going up past her white bun, beaten down by the rain; down the jetty behind
her, small and soft at first at the left, Shinza comes on under his kasa, his footfalls on the wet planks, and stops
behind her right shoulder. The focus leaves her and finds him as he stops; a held breath; he lifts his chin out of
the hat's shadow and speaks down to her (line 3, "Old woman. Take me across."). She lets her smoke out as he comes
and does not turn.

The scene is rf/jetty_talk.py's (shared with demand, tap, look and draw: every camera on the river side of the line
between them, him at the left and her at the right); his walk and her breath of smoke are rf/jetty_arrive.py's.

    blender -b -P blender/render.py -- --film rain-ferry --shot ask --mode look --engine eevee \\
        --frames 648,690,720,760 --res 960x540
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rf import jetty_arrive as ja  # noqa: E402
from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "ask"}

# the camera low over the water off her left front, looking up the jetty past her; it eases in a little
CAM = [(0.0, (9.14, -2.4, 1.0), (4.0, 0.5, 1.1)),
       (5.0, (8.85, -2.18, 1.02), (4.2, 0.35, 1.14))]
LENS = [(0.0, 40.0), (5.0, 42.0)]
FSTOP = [(0.0, 2.8)]
RACK = (1.45, 2.2)          # s: the focus pulls from her to him as he stops
WALK = (-0.9, 2.1)          # s: he is already walking when the shot opens; he stops on his mark
CHIN = (2.05, 2.4)          # his chin up out of the hat's shadow to speak
EXHALE = (0.55, 1.35)       # s: she lets the smoke out round the pipe's stem as he comes
BLINKS_SH = (2.25, 4.75)
SKY_RIM, LANTERN_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18)


def build(ctx):
    st = jt.stage(ctx, rain_box=((0.0, -4.5, -0.6), (10.5, 3.5, 4.6)), clear=1.0, near=3.0,
                  variant={"shinza": {"kasa": "on"}}, place={"shinza": None})
    jt.compose_faces(st)
    line = st.line("L03")["L03"]
    walk = ja.Walk(st, ja.ASK_FROM, jt.SHINZA_AT, *WALK)
    perform(st, walk, line)
    shot = jt.Shot(CAM, LENS, FSTOP, breath=0.004)
    her, him = st.tracked_focus("tsuru"), st.tracked_focus("shinza", every=3)
    st.camera(shot, lambda f: her(f) + (him(f) - her(f)) * jt.ramp(st.t(f), *RACK))
    jt.outline(st, shot)
    # her key from up the river beyond her (her back edge lit, her face in the 1st shade); his from the river side
    jt.key_light(st, "tsuru", (0.6, 0.7, 0.8))
    jt.key_light(st, "shinza", (0.8, -0.9, 0.8))
    st.composite(lambda f: dict(rims=[((0.5, 1.0), SKY_RIM, 0.3, 0.003, 0.9),
                                      ((-1.0, 0.2), LANTERN_RIM, 0.2, 0.0025, 0.9)],
                                para=(0.5, 0.53, 0.7), para_from=(0.8, 0.95), para_to=(0.3, 0.05), para_amount=0.35))
    # last, once everything is keyed: her pipe's thread and the breath she lets out
    jt.pipe_smoke(st, seed=7).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
    pose = {**jt.tsuru_sit(0.0), **jt.fingers("left", 0.85)}
    ja.breath(st, [EXHALE], ja.lips_source(st, pose, jt.tsuru_hips(st, 0.0))).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)


def perform(st, walk, line):
    ch = st.cast["shinza"]["vrm"]
    hang_r, hang_l = np.array(jt.HANG["right"]), np.array(jt.HANG["left"])
    turn_r = jt.hand_turn(ch, "right", (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    turn_l = jt.hand_turn(ch, "left", (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))
    for f in st.frames():
        t = st.t(f)
        walk.key(f, t)
        go, sw = walk.going(t), walk.swing(t)
        chin = jt.ramp(t, *CHIN)
        # walking: his head down under the hat, leaning into it; stopped: he lifts his chin to her
        body = jt.shinza_stand(t, chin=chin)
        body["head"] = (body["head"][0] + 6.0 * go, body["head"][1], body["head"][2])
        body["spine"] = (body["spine"][0] + ja.LEAN * go, body["spine"][1], body["spine"][2])
        st.pose("shinza", f, {**body, **jt.fingers("right", 0.3), **jt.fingers("left", 0.3)},
                hips=tuple(np.array(jt.shinza_hips(t)) * (1.0 - go)))
        # the arms swing against the legs (his front is -y)
        st.hand("shinza", "right", f, hang_r + (0.0, -0.13 * sw, 0.02 * abs(sw)), turn_r, (-0.3, 0.5, 1.2))
        st.hand("shinza", "left", f, hang_l + (0.0, 0.13 * sw, 0.02 * abs(sw)), turn_l, (0.3, 0.5, 1.2))
        st.face("shinza", f, {"glare": 1.0, "blink": jt.blink(t, BLINKS_SH), **jt.mouth_weights(t, [line], seed=3)})
        # she smokes, the pipe at her lips; her head goes back a little as she lets the smoke out
        out = jt.ramp(t, EXHALE[0] - 0.25, EXHALE[0]) - jt.ramp(t, EXHALE[1], EXHALE[1] + 0.4)
        jt.tsuru_rest(st, f, t, smoking=True, down=-4.0 * out)
