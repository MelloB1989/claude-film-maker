"""Shot 8, refuse (32.0-36.0 s): Tsuru in profile, close, facing into the right of the frame; behind her, soft, the
jetty's end post, the moored boat and the river white with rain. Shinza stands just out of the frame at the left, at
her back. Her pipe rests over her knee below the frame, its thread of smoke curling up past her face through the space
she looks into, the rain beating it down. She says, not looking at him, "I don't cross on rainy days." (line 4); then
the pipe comes up to her lips, as if that settled it (demand finds her smoking). The camera creeps in.

The scene is rf/jetty_talk.py's (the camera on the river side of the line between them, beside his mark), its camera
and weather lib/cinema.py's and lib/weather.py's; her pipe's hold and smoke rf/jetty_arrive.py's.

    blender -b -P blender/render.py -- --film rain-ferry --shot refuse --mode look --engine eevee \\
        --frames 770,792,816,840,862 --res 960x540
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import cinema, weather  # noqa: E402
from rf import jetty_arrive as ja  # noqa: E402
from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "refuse"}

# the camera off her right side (metres out, along her facing, up from her eyes), its aim ahead of her face (her
# lead room) and a little down; easing in
SIDE = ((2.0, 0.35, 0.0), (1.8, 0.32, 0.01))
LEAD, DROP = 0.3, 0.05
LENS = (65.0, 68.0)
FSTOP = 2.8
LIFT = (2.7, 3.85)          # s: the pipe up from her knee to her lips (the far side of her face from here): there at
                            # the cut, as demand finds her (its background: still smoking)
CHIN = (0.8, 1.1, 2.9, 3.4)   # her chin lifts a touch on the line and settles
BLINKS = (2.95,)            # s: her one blink, after the line
TEXT = "ame no hi wa, watasanai yo."    # line 4 as it is spoken (data/dialogue.json L04)
SKY_RIM, LANTERN_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18)
# her close-up's rain, in metres from the lens: a few fine drops between it and her face, and the body of it in a band
# just behind her where the depth of field still draws streaks (the kit's lens-adapted layers sit all in the blur
# behind a close-up at f/2: no rain to see); the far curtain as the kit has it. (near, far, count, length, width,
# alpha, shrink, clear: weather.Layer)
RAIN = {"near": (1.25, 1.85, 90, 0.2, 0.0035, 0.14, 1.9, 1.2), "mid": (2.25, 7.0, 1600, 0.26, 0.0032, 0.22, 0.0, 0.0)}
# her pipe's thread from her knee below the frame up past her face: rising, long-lived and fine
SMOKE = dict(rise=0.32, life=3.6, curl=0.07, width=(0.002, 0.03), opacity=0.55)


def build(ctx):
    ja.clock("refuse", "build")
    st = jt.stage(ctx, who=("tsuru",), ink=0.0)
    ja.clock("refuse", "staged")
    jt.compose_faces(st)
    ts = st.cast["tsuru"]["vrm"]
    perform(st)
    st.say("tsuru", "L04", TEXT, energy=0.75)
    st.blinks("tsuru", BLINKS)
    ja.clock("refuse", "performed")
    st.bake()
    ja.clock("refuse", "baked")

    head = st.head_at("tsuru", ctx.f0)
    fw = np.array((math.cos(math.radians(jt.TSURU_FACING)), math.sin(math.radians(jt.TSURU_FACING)), 0.0))
    right = np.array((fw[1], -fw[0], 0.0))
    (out0, along0, up0), (out1, along1, up1) = SIDE
    cam0 = head + right * out0 + fw * along0 + np.array((0.0, 0.0, up0))
    cam1 = head + right * out1 + fw * along1 + np.array((0.0, 0.0, up1))
    aim = head + fw * LEAD - np.array((0.0, 0.0, DROP))
    # (the kit pushes every layer out by lens / its wide's: these are given at their place for a wide, so they land
    # where RAIN has them)
    k = weather.REF_LENS / LENS[0]
    layers = {n: weather.Layer(near * k, far * k, count, length, width, alpha, shrink * k, clear)
              for n, (near, far, count, length, width, alpha, shrink, clear) in RAIN.items()}
    layers["far"] = weather.LAYERS["far"]
    st.film([cinema.Setup("refuse", 0.0, cinema.line(cam0, cam1, aim), lens=LENS, fstop=FSTOP, focus=(ts, "head"),
                          shake=cinema.Shake(breath=0.03))], layers=layers)
    jt.outline(st)
    ja.clock("refuse", "filmed")
    # her key from beyond her and above, so the cheek toward the lens falls into the 1st shade
    jt.key_light(st, "tsuru", tuple(fw - right * 0.35 + np.array((0.0, 0.0, 0.75))))
    st.composite(lambda f: dict(rims=[((1.0, 0.45), SKY_RIM, 0.35, 0.0035, 0.9),
                                      ((-1.0, 0.2), LANTERN_RIM, 0.15, 0.003, 0.9)],
                                para=(0.5, 0.53, 0.7), para_from=(0.85, 0.9), para_to=(0.15, 0.1), para_amount=0.4,
                                wrap=0.3, wrap_width=0.02))
    ja.bowl_smoke(st, seed=11, **SMOKE).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps, step=12)
    ja.clock("refuse", "smoke baked")


def perform(st):
    """Her pipe over her knee, its smoke rising through the frame, still through her line; then up to her lips."""
    for f in st.frames():
        t = st.t(f)
        chin = jt.ramp(t, CHIN[0], CHIN[1]) - 0.6 * jt.ramp(t, CHIN[2], CHIN[3])
        ja.smoking(st, f, t, at_lips=jt.ramp(t, *LIFT), down=-4.0 * chin)
