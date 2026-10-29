"""Shot 10, tap (41.8-47.8 s): Tsuru in three-quarter profile on her crate, the end post in front of her and the river
grey beyond. His boast is still going on off screen ("...and be the strongest under heaven.") when she knocks her pipe
out on the post, tok, tok (data/mix.json pipe_tap at 42.05 s): ash and one last ember drop from the bowl onto the wet
wood and die. She lowers the pipe to her knee, lifts her eyes out over the water, and a faint smile comes as she says
"The River Demon is already dead." The camera drifts slowly along the post toward her.

    blender -b -P blender/render.py -- --film rain-ferry --shot tap --mode look --engine eevee \\
        --frames 1010,1020,1060,1120 --res 960x540
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "tap"}

# the camera: side-on to the line from her face to the post (the river and the far bank behind), her head in the
# frame's left third and the post's crown in its right; it drifts slowly in along that line's normal
CAM_SIDE = -140.0            # degrees: where the camera stands from the middle of her face and the post
CAM_DIST, CAM_Z = (1.75, 1.5), (0.93, 0.95)
LENS = [(0.0, 40.0), (6.0, 42.0)]
FSTOP = [(0.0, 3.2)]
TAPS = (0.25, 0.62)          # s into the shot: the bowl strikes the post (pipe_tap's two knocks, from 42.05 s)
STRIKE = (0.07, 0.12)        # each knock: down this long, back up this long (s)
LIFT = 0.07                  # the bowl's height over the post between knocks (m)
LOWER = (0.95, 1.8)          # the pipe down to her knee
EYES_UP = (1.5, 2.3)         # her eyes off the post and out over the river
SMILE = (2.2, 3.4)
BLINKS = (1.35, 3.9, 5.7)
ASH = 7                      # flecks of ash knocked out at each knock


def build(ctx):
    st = jt.stage(ctx, who=("tsuru",), rain_box=((5.4, -3.0, -0.6), (10.5, 7.0, 3.8)), clear=1.2, near=3.0)
    jt.compose_faces(st)
    lines = st.line("L07")
    post = jt.post_top(st)
    perform(st, lines, post)
    ash(st, post)
    head = st.tracked_focus("tsuru")
    mid = (head(ctx.f0) + post) / 2
    side = np.radians(CAM_SIDE)
    out = np.array((np.cos(side), np.sin(side), 0.0))
    path = [(0.0, (*(mid[:2] + out[:2] * CAM_DIST[0]), CAM_Z[0]), tuple(mid + (0, 0, 0.02))),
            (6.0, (*(mid[:2] + out[:2] * CAM_DIST[1]), CAM_Z[1]), tuple(mid + (0, 0, 0.04)))]
    shot = jt.Shot(path, LENS, FSTOP, breath=0.003)
    # the focus on the bowl through the knocks, racking to her face as the pipe goes down
    st.camera(shot, lambda f: _rack(st, f, post, head))
    jt.outline(st, shot)
    # the wisp off the bowl until the first knock puts it out
    jt.pipe_smoke(st, emit=((0.0, st.start + TAPS[0]),)).bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
    jt.key_light(st, "tsuru", (-0.4, -1.0, 0.7))
    st.composite(lambda f: dict(rims=[((0.8, 0.6), (0.6, 0.68, 0.85), 0.35, 0.0035, 0.9)],
                                para_from=(0.4, 0.95), para_to=(0.7, 0.05)))


def _rack(st, f, post, head):
    k = jt.ramp(st.t(f), LOWER[0], LOWER[0] + 0.6)
    return post * (1 - k) + head(f) * k


def bowl_path(t: float, post) -> np.ndarray:
    """Where the pipe's bowl is (world) at t: hovering over the post's top on her side of it, knocked down onto it at
    each of TAPS."""
    rest = np.asarray(post) + (-0.05, 0.04, 0.02 + LIFT)
    z = LIFT
    for at in TAPS:
        u = t - at
        if -STRIKE[0] <= u < 0:
            z = LIFT * (1 - jt.ease((u + STRIKE[0]) / STRIKE[0]))
        elif 0 <= u < STRIKE[1]:
            z = min(z, LIFT * jt.ease(u / STRIKE[1]))
    return rest - (0.0, 0.0, LIFT - z)


def perform(st, lines, post):
    ch = st.cast["tsuru"]["vrm"]
    speak = [lines["L07"]]
    for f in st.frames():
        t = st.t(f)
        low = jt.ramp(t, *LOWER)
        up = jt.ramp(t, *EYES_UP)
        # the pipe: from her fist toward the post, its bowl knocked on it; then down to rest by her knee
        bowl = jt.local(ch, bowl_path(t, post))
        fist_knock = bowl + np.array((-0.03, 0.19, 0.08))   # the fist 21 cm back up the stem
        along_knock = bowl - fist_knock
        lap, lap_along = jt.TS_PIPE_LAP
        fist = fist_knock * (1 - low) + np.asarray(lap) * low
        along = along_knock / np.linalg.norm(along_knock) * (1 - low) + np.asarray(lap_along) / np.linalg.norm(lap_along) * low
        knock = sum(math.exp(-((t - a) / 0.05) ** 2) for a in TAPS)
        body = jt.tsuru_sit(t, turn=-14.0 * (1 - up) + 4.0 * up, down=10.0 * (1 - up) - 6.0 * up + 1.5 * knock,
                            eyes=(18.0 * (1 - up) - 2.0 * up, -6.0 * (1 - up)), lean=6.0 * (1 - low))
        st.pose("tsuru", f, {**body, **jt.fingers("left", 0.85), **jt.fingers("right", 0.35)}, hips=jt.tsuru_hips(st, t))
        jt.hold_pipe(st, f, fist, along)
        jt.knee_hand(st, f)
        smile = jt.ramp(t, *SMILE)
        st.face("tsuru", f, {"s4-calm": 1.0, "s4-smile": 0.8 * smile, "blink": jt.blink(t, BLINKS),
                             **jt.mouth_weights(t, speak, seed=7, scale=0.45)})


def ash(st, post):
    """What the knocks shake out: flecks of grey ash, and with the first one a last ember (the scene's only warm point
    near her) that drops onto the wet post and goes out."""
    import bpy

    from lib import shapes, toon

    grey = toon.cel("ash", (0.3, 0.3, 0.31), (0.1, 0.1, 0.11), cut=0.4)
    ember = toon.flat("ember", (1.0, 0.32, 0.08), strength=6.0)
    coll = st.crossing["near"]
    rng = np.random.default_rng(3)
    top = post[2] + 0.004
    for k, at in enumerate(TAPS):
        for i in range(ASH + (1 if k == 0 else 0)):
            is_ember = k == 0 and i == ASH
            ob = shapes.ellipsoid(f"ash{k}-{i}", (0, 0, 0), (0.004, 0.004, 0.003) if not is_ember else (0.0035,) * 3,
                                  material=ember if is_ember else grey, coll=coll, n=6)
            start = bowl_path(at, post) + (0.0, 0.0, 0.012)
            v = np.array((rng.normal(0, 0.25), rng.normal(0, 0.25), rng.uniform(0.1, 0.5)))
            ob.hide_render = True
            ob.keyframe_insert("hide_render", frame=st.ctx.f0 - 1)
            f_at = st.ctx.f0 + round(at * st.ctx.fps)
            life = 0.9 if is_ember else 0.5
            for f in range(f_at, f_at + round(life * st.ctx.fps) + 1):
                u = (f - f_at) / st.ctx.fps
                p = start + v * u + np.array((0.0, 0.0, -4.9 * u * u))
                if p[2] < top:      # on the post's top: lying where it fell
                    p[2] = top
                    v[:2] *= 0.0
                ob.location = tuple(p)
                ob.hide_render = False
                ob.keyframe_insert("location", frame=f)
                ob.keyframe_insert("hide_render", frame=f)
                if is_ember:
                    s = max(0.0, 1.0 - u / life)
                    ob.scale = (s, s, s)
                    ob.keyframe_insert("scale", frame=f)
            ob.hide_render = True
            ob.keyframe_insert("hide_render", frame=f_at + round(life * st.ctx.fps) + 1)
            st.held.append(ob)
