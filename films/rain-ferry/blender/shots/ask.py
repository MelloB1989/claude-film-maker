"""Shot 7, ask (27.0-32.0 s): Tsuru close at the right of the frame on her crate at the jetty's end, three-quarters
to us, taking a draw on her pipe and lowering it to her knee, its smoke going up past her, beaten down by the rain; down the jetty behind
her, small and soft at first at the left, Shinza comes on under his kasa with his heavy stride, his footfalls on the
wet planks, and stops behind her right shoulder. The focus leaves her and finds him as he stops; a held breath; his
glare hardens and he speaks down to her (line 3, "Old woman. Take me across."). She lets her smoke out as he comes and
does not turn.

The scene is rf/jetty_talk.py's (shared with demand, tap, look and draw: every camera on the river side of the line
between them, him at the left and her at the right), its camera and weather lib/cinema.py's and lib/weather.py's; his
walk and her breath of smoke are rf/jetty_arrive.py's.

    blender -b -P blender/render.py -- --film rain-ferry --shot ask --mode look --engine eevee \\
        --frames 650,672,696,712,740,766 --res 960x540
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import cinema  # noqa: E402
from rf import jetty_arrive as ja  # noqa: E402
from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "ask"}

# the camera low over the water off her left front, looking up the jetty past her; it eases in a little
CAM = ((9.14, -2.4, 1.0), (4.0, 0.5, 1.1))
PUSH = 0.35                 # m in over the shot
LENS = (40.0, 42.0)
FSTOP = 2.8
RACK = (1.45, 0.75)         # s: the focus pulls from her to him as he stops (when, over)
STOP = 2.1                  # s: he is already walking when the shot opens and stands still on his mark here
GLARE = 2.05                # s: his glare hardens as he stops to speak
TEXT = "baasan. mukougishi e, watashite kure."   # line 3 as it is spoken (data/dialogue.json L03)
DRAW = (0.08, 0.55)         # s: the end of a draw: the pipe from her lips down to her knee as he comes ...
EXHALE = (0.35, 1.2)        # ... and she lets the smoke out
SHIFT = 0.55                # s after he stops: his weight settles onto his back (left) foot
SKY_RIM, LANTERN_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18)


def build(ctx):
    st = jt.stage(ctx, variant={"shinza": {"kasa": "on"}}, place={"shinza": None})
    jt.compose_faces(st)
    ts, sh_ch = st.cast["tsuru"]["vrm"], st.cast["shinza"]["vrm"]

    # Shinza: up the jetty to his mark, stopping on the beat; a look down to her, his line
    sh, stop = ja.arrives(st, [ja.ASK_FROM, jt.SHINZA_AT], STOP)
    sh.look(ctx.f0, None)
    sh.look(stop + round(0.1 * ctx.fps), lambda f: st.perf["tsuru"].face_at(f), lag=1.3)
    sh.settle(stop, 0.5)
    sh.shift(stop + round(SHIFT * ctx.fps), "left", amount=0.7)
    sh.express(ctx.f0, {"glare": 0.7})
    sh.express(ctx.f0 + round(GLARE * ctx.fps), {"glare": 1.0})
    sh.blinks(mean=3.4)
    sh.blink_at(stop + round(0.15 * ctx.fps))
    sh.breathe(rate=0.3, depth=1.3)
    st.say("shinza", "L03", TEXT, energy=0.9)
    sh.secondary(wind=(0.4, 1.2, 0.0))
    # Tsuru: a draw on her pipe, then it comes down to her knee (from here her arm at her lips would hide her face);
    # her head goes back a little as she lets the smoke out
    for f in st.frames():
        t = st.t(f)
        out = jt.ramp(t, EXHALE[0] - 0.25, EXHALE[0]) - jt.ramp(t, EXHALE[1], EXHALE[1] + 0.4)
        ja.smoking(st, f, t, at_lips=1.0 - jt.ramp(t, *DRAW), down=-4.0 * out)
    st.blinks("tsuru", (1.6, 3.9))
    st.bake()

    st.film([cinema.Setup("ask", 0.0, cinema.drift(cinema.push(*CAM, PUSH), 0.01), lens=LENS, fstop=FSTOP,
                          focus=(ts, "head"), racks=(cinema.Rack(RACK[0], (sh_ch, "head"), RACK[1]),),
                          shake=cinema.Shake(breath=0.05))])
    jt.outline(st)
    # her key from up the river beyond her (her back edge lit, her face in the 1st shade); his from the river side
    jt.key_light(st, "tsuru", (0.6, 0.7, 0.8))
    jt.key_light(st, "shinza", (0.8, -0.9, 0.8))
    st.composite(lambda f: dict(rims=[((0.5, 1.0), SKY_RIM, 0.3, 0.003, 0.9),
                                      ((-1.0, 0.2), LANTERN_RIM, 0.2, 0.0025, 0.9)],
                                para=(0.5, 0.53, 0.7), para_from=(0.8, 0.95), para_to=(0.3, 0.05), para_amount=0.35))
    # last, once everything is keyed: her pipe's thread and the breath she lets out
    ja.bowl_smoke(st, seed=7).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
    pose = {**jt.tsuru_sit(0.0), **jt.fingers("left", 0.85)}
    ja.breath(st, [EXHALE], ja.lips_source(st, pose, jt.tsuru_hips(st, 0.0))).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
