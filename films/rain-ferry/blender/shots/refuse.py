"""Shot 8, refuse (32.0-36.0 s): Tsuru in profile, close, facing into the right of the frame; behind her, soft, the
jetty's end post, the moored boat and the river white with rain. Shinza stands just out of the frame at the left, at
her back. She takes the pipe from her lips and lowers it as she lets the smoke out in a long breath the rain tears
apart, and says, not looking at him, "I don't cross on rainy days." (line 4); then the pipe goes back up to her lips,
as if that settled it (demand finds her smoking). Its bowl's thread curls up through the space she looks into. The
camera creeps in.

The scene is rf/jetty_talk.py's (the camera on the river side of the line between them, beside his mark); her breath
of smoke is rf/jetty_arrive.py's.

    blender -b -P blender/render.py -- --film rain-ferry --shot refuse --mode look --engine eevee \\
        --frames 768,790,820,860 --res 960x540
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rf import jetty_arrive as ja  # noqa: E402
from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "refuse"}

# the camera off her right side (metres out, along her facing, up from her eyes), its aim ahead of her face (her
# lead room) and a little down; easing in
SIDE = [(0.0, (2.0, 0.35, 0.0)), (4.0, (1.8, 0.32, 0.01))]
LEAD, DROP = 0.3, 0.05
LENS = [(0.0, 65.0), (4.0, 68.0)]
FSTOP = [(0.0, 2.0)]
LOWER = (0.1, 0.75)         # s: the pipe from her lips down to her lap
EXHALE = (0.05, 0.85)       # ... the smoke let out as it comes down
WORDS = (0.95, 1.35)        # ... and the last of it on her first words
LIFT = (3.0, 3.8)           # s: the pipe back up to her lips
CHIN = (0.8, 1.1, 2.9, 3.4)   # her chin lifts a touch on the line and settles
BLINKS = (2.95,)
SKY_RIM, LANTERN_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18)


def build(ctx):
    st = jt.stage(ctx, who=("tsuru",), rain_box=((3.0, -4.0, -0.6), (12.0, 5.0, 4.0)), clear=1.3, near=5.0)
    jt.compose_faces(st)
    line = st.line("L04")["L04"]
    perform(st, line)
    head = st.head_at("tsuru", ctx.f0)
    fw = np.array((math.cos(math.radians(jt.TSURU_FACING)), math.sin(math.radians(jt.TSURU_FACING)), 0.0))
    right = np.array((fw[1], -fw[0], 0.0))

    def keyed(keys, t):
        return np.array(jt.keys_at(keys, t))

    path = []
    for k in (0.0, 4.0):
        out, along, up = keyed(SIDE, k)
        cam = head + right * out + fw * along + np.array((0.0, 0.0, up))
        aim = head + fw * LEAD - np.array((0.0, 0.0, DROP))
        path.append((k, tuple(cam), tuple(aim)))
    shot = jt.Shot(path, LENS, FSTOP, breath=0.0025)
    st.camera(shot, st.tracked_focus("tsuru", every=3))
    jt.outline(st, shot)
    # her key from beyond her and above, so the cheek toward the lens falls into the 1st shade
    jt.key_light(st, "tsuru", tuple(fw - right * 0.35 + np.array((0.0, 0.0, 0.75))))
    st.composite(lambda f: dict(rims=[((1.0, 0.45), SKY_RIM, 0.35, 0.0035, 0.9),
                                      ((-1.0, 0.2), LANTERN_RIM, 0.15, 0.003, 0.9)],
                                para=(0.5, 0.53, 0.7), para_from=(0.85, 0.9), para_to=(0.15, 0.1), para_amount=0.4,
                                wrap=0.3, wrap_width=0.02))
    jt.pipe_smoke(st, seed=11).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
    pose = {**jt.tsuru_sit(0.0), **jt.fingers("left", 0.85)}
    ja.breath(st, [(EXHALE[0] - 0.3, EXHALE[1]), WORDS], ja.lips_source(st, pose, jt.tsuru_hips(st, 0.0)),
              push=0.35, seed=12).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)


def perform(st, line):
    for f in st.frames():
        t = st.t(f)
        chin = jt.ramp(t, CHIN[0], CHIN[1]) - 0.6 * jt.ramp(t, CHIN[2], CHIN[3])
        exhale = jt.ramp(t, EXHALE[0], EXHALE[0] + 0.25) - jt.ramp(t, EXHALE[1] - 0.2, EXHALE[1] + 0.2)
        sit = dict(down=-4.0 * chin - 3.0 * exhale)
        pose = {**jt.tsuru_sit(t, **sit), **jt.fingers("left", 0.85), **jt.fingers("right", 0.35)}
        hips = jt.tsuru_hips(st, t)
        at_lips = jt.pipe_at_lips(st, pose, hips)
        k = 1.0 - jt.ramp(t, *LOWER) + jt.ramp(t, *LIFT)
        point = np.array(jt.TS_PIPE_LAP[0]) + (np.array(at_lips[0]) - jt.TS_PIPE_LAP[0]) * k
        point = point + np.array((0.03, -0.07, 0.0)) * math.sin(math.pi * k)    # out in front of her, not through her chin
        along = np.array(jt.TS_PIPE_LAP[1]) + (np.array(at_lips[1]) - jt.TS_PIPE_LAP[1]) * k
        st.pose("tsuru", f, pose, hips=hips)
        jt.hold_pipe(st, f, point, along)
        jt.knee_hand(st, f)
        st.face("tsuru", f, {"s4-calm": 1.0, "blink": jt.blink(t, BLINKS), **jt.mouth_weights(t, [line], seed=9)})
