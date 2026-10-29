"""Shot 9, demand (36.0-41.8 s): a low angle on Shinza from beside the seated ferrywoman, the hut's red lantern behind
his shoulder and the storm over him. He says it down to her ("They say the River Demon lives on the other side."),
his eyes going out across the river on "the other side" and back; on "I'll cut it down, and be the strongest under
heaven." his right hand rises over his shoulder to the hilt of the nodachi on his back and closes on it, and his eyes
narrow. The camera creeps in and up under him the whole shot; the gust at 37.5 s (data/mix.json) breathes through it.
Her straw cape is the soft dark shape at the right edge of the frame.

The scene (rf/jetty_talk.py) is shared with tap, look and draw: this shot's last pose is draw's first.

    blender -b -P blender/render.py -- --film rain-ferry --shot demand --mode look --engine eevee \\
        --frames 870,940,985,1000 --res 960x540
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import cinema  # noqa: E402
from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "demand"}

# the camera: low by her right shoulder, looking up at him (cinema.frame_on: his face, head to belt filling the frame's
# height by `share`, from `bearing` degrees, `rise` metres off his eyes, in the left third: room on the side he looks
# to), creeping in over the shot
FRAME = dict(height=1.05, bearing=66.0, rise=-0.92, third=-1.0, headroom=0.12)
SHARE, LENS, FSTOP = (0.86, 0.98), 28.0, 2.8
GUST = 1.5             # s into the shot: the gust's peak (data/mix.json wind_gust at 37.5 s)
# his right hand to the hilt: when it starts up, passes his chest, clears his shoulder and closes on the hilt (s)
RISE = (3.95, 4.35, 4.72, 4.92, 5.08)
LOOK_OUT = (2.3, 2.75, 3.3, 3.75)   # his eyes out to the far shore on "the other side", then back to her
BLINKS = (1.05, 3.68, 5.45)
LANTERN_RIM = (1.0, 0.5, 0.18)


def build(ctx):
    st = jt.stage(ctx)
    jt.compose_faces(st)
    lines = st.line("L05", "L06")
    perform(st, lines)
    st.say("shinza", "L05", "mukougishi ni kawaoni ga iru to kiita", energy=0.9)
    st.say("shinza", "L06", "soitsu wo kitte, ore ga tenkaichi ni naru", energy=1.1)
    st.blinks("shinza", BLINKS)
    st.blinks("tsuru", (0.8, 3.2))
    st.perf["shinza"].secondary(wind=(0.0, 0.8, 0.0))
    st.bake()
    ch = st.cast["shinza"]["vrm"]
    face = st.head_at("shinza", ctx.f0)
    (c0, a0), (c1, a1) = (cinema.frame_on(face, share=k, lens=LENS, **FRAME) for k in SHARE)
    st.film([cinema.Setup("low", 0.0, cinema.line(c0, c1, a0, a1), lens=LENS, fstop=FSTOP, focus=(ch, "head"),
                          shake=cinema.Shake(breath=0.08))])
    jt.outline(st)
    jt.pipe_smoke(st).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)     # her pipe at the frame's edge, still lit
    jt.key_light(st, "shinza", (0.7, -0.9, 0.75))
    jt.key_light(st, "tsuru", (0.3, -1.0, 0.8))
    # the lantern behind his left shoulder warms that edge; the sky's cold light rims his head
    st.composite(lambda f: dict(rims=[((-1.0, 0.25), LANTERN_RIM, 0.4, 0.004, 0.9),
                                      ((0.3, 1.0), (0.6, 0.68, 0.85), 0.3, 0.003, 0.9)],
                                para_from=(0.5, 0.95), para_to=(0.5, 0.05)))


def perform(st, lines):
    from lib import vrm

    ch = st.cast["shinza"]["vrm"]
    # the hilt where it is once his chest has turned into the reach (it rides on his back)
    vrm.pose(ch, jt.shinza_stand(RISE[3], reach=1.0), hips=jt.shinza_hips(RISE[3]))
    hang_r, hang_l = jt.HANG["right"], jt.HANG["left"]
    grip_wrist, grip_turn = jt.hilt_grip(st)
    hang_turn_r = jt.hand_turn(ch, "right", (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    up_turn = jt.hand_turn(ch, "right", (0.0, 0.2, 1.0), (0.9, -0.3, 0.0))
    wrists = [(RISE[0], hang_r), (RISE[1], (-0.25, -0.24, 1.18)), (RISE[2], (-0.29, -0.12, 1.5)),
              (RISE[3], tuple(grip_wrist + (0.0, -0.02, 0.03))), (RISE[4], tuple(grip_wrist))]
    turns = [(RISE[0], hang_turn_r), (RISE[2], up_turn), (RISE[3], grip_turn)]
    poles = [(RISE[0], (-0.3, 0.5, 1.2)), (RISE[1], (-0.6, -0.1, 1.2)), (RISE[3], (-0.6, -0.25, 1.75))]
    for f in st.frames():
        t = st.t(f)
        out = jt.ramp(t, LOOK_OUT[0], LOOK_OUT[1]) - jt.ramp(t, LOOK_OUT[2], LOOK_OUT[3])
        rise = jt.ramp(t, RISE[0], RISE[3])
        gust = math.exp(-((t - GUST) / 0.6) ** 2)
        body = jt.shinza_stand(t, look_out=out, reach=rise, gust=gust)
        # the hand: open as it rises, a fist on the hilt
        curl = 0.25 - 0.2 * jt.ramp(t, RISE[0], RISE[2]) + 0.95 * jt.ramp(t, RISE[3], RISE[4] + 0.04)
        st.pose("shinza", f, {**body, **jt.fingers("right", curl), **jt.fingers("left", 0.3)},
                hips=jt.shinza_hips(t))
        st.hand("shinza", "right", f, jt.keys_at(wrists, t), jt.turn_keys(turns, t), jt.keys_at(poles, t))
        st.hand("shinza", "left", f, hang_l, jt.hand_turn(ch, "left", (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
                (0.3, 0.5, 1.2))
        narrow = 0.6 * jt.ramp(t, RISE[3], RISE[4] + 0.3)
        st.face("shinza", f, {"glare": 1.0, "narrow": narrow})
        if "tsuru" in st.cast:
            jt.tsuru_rest(st, f, t, smoking=True)     # still smoking, as refuse leaves her
