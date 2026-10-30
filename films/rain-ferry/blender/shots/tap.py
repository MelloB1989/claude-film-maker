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

from lib import cinema, vrm  # noqa: E402
from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "tap"}

# the camera: low in front of her left side, past the post's crown (cinema.frame_on on the middle of her face and the
# crown, the two filling the frame's height by SHARE; its bearing degrees from -y toward +x): the knock in the
# foreground, her face over it looking down at it, and behind her, soft, him standing with his fist on his hilt and
# the hut's red lantern. It creeps in
FRAME = dict(height=0.62, bearing=50.0, rise=-0.06, third=0.25)
SHARE, LENS, FSTOP = (0.8, 0.88), 40.0, 3.2
TAPS = (0.25, 0.62)          # s into the shot: the bowl strikes the post (pipe_tap's two knocks, from 42.05 s)
STRIKE = (0.07, 0.12)        # each knock: down this long, back up this long (s)
LIFT = 0.07                  # the bowl's height over the post between knocks (m)
LOWER = (0.95, 1.8)          # the pipe down to her knee
EYES_UP = (1.5, 2.3)         # her eyes off the post and out over the river
SMILE = (2.2, 3.4)
BLINKS = (1.35, 3.9, 5.7)
ASH = 7                      # flecks of ash knocked out at each knock
# her fist through the knocks, from the bowl at rest over the post (her frame: out at her left side, back from the
# bowl and a little above it: the stem runs forward from it onto the post, her forearm low, not across her face),
# and how much of the bowl's drop it shares
# (the kiseru's bowl is ~0.21 m on from the fist: rf/vroid_tsuru.py's KISERU less the 0.09 behind it)
KNOCK_FIST, FLICK = np.array((-0.15, 0.13, 0.05)), 0.3


def build(ctx):
    st = jt.stage(ctx, ink=0.0)     # the set out of focus behind her: no lines over it
    jt.compose_faces(st)
    lines = st.line("L07")
    post = jt.post_top(st)
    perform(st, lines, post)
    st.say("tsuru", "L07", "kawaoni nara, mou shinda yo", energy=0.7)
    st.say("shinza", "L06", "soitsu wo kitte, ore ga tenkaichi ni naru", energy=1.1)   # his boast still going on
    st.blinks("tsuru", BLINKS)
    st.blinks("shinza", (2.4, 4.9))
    st.bake()
    ash(st, post)
    ch = st.cast["tsuru"]["vrm"]
    mid = (st.head_at("tsuru", ctx.f0) + post) / 2
    (c0, a0), (c1, a1) = (cinema.frame_on(mid, share=k, lens=LENS, **FRAME) for k in SHARE)
    # the focus on the bowl through the knocks, racked to her face as the pipe goes down
    st.film([cinema.Setup("knock", 0.0, cinema.line(c0, c1, a0, a1),
                          lens=LENS, fstop=FSTOP, focus=tuple(post), racks=(cinema.Rack(LOWER[0], (ch, "head"), 0.6),),
                          shake=cinema.Shake(breath=0.05))])
    jt.outline(st)
    # the wisp off the bowl until the first knock puts it out
    jt.bake_smoke(st, jt.pipe_smoke(st, emit=((0.0, st.start + TAPS[0]),)), until=TAPS[0] + 2.9)
    jt.key_light(st, "tsuru", (0.7, -0.8, 0.7))
    jt.key_light(st, "shinza", (0.7, -0.8, 0.7))
    st.composite(lambda f: dict(rims=[((-0.8, 0.6), (0.6, 0.68, 0.85), 0.35, 0.0035, 0.9),
                                      ((-1.0, 0.1), (1.0, 0.5, 0.18), 0.15, 0.003, 0.9)],
                                para_from=(0.6, 0.95), para_to=(0.3, 0.05)))


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
    rest_bowl = jt.local(ch, bowl_path(-1.0, post))
    for f in st.frames():
        t = st.t(f)
        low = jt.ramp(t, *LOWER)
        up = jt.ramp(t, *EYES_UP)
        # the pipe: from her fist toward the post, its bowl knocked on it; then down to rest by her knee
        # the knock is the wrist's: her fist held in front of her, the stem out across to the post, and the bowl
        # flicked down onto it about the fist (which gives only a little of the drop), not the whole arm pumping
        bowl = jt.local(ch, bowl_path(t, post))
        rest = rest_bowl
        fist_knock = rest + KNOCK_FIST + (bowl - rest) * FLICK
        along_knock = bowl - fist_knock
        lap, lap_along = jt.TS_PIPE_LAP
        # down to her knee in an arc (out and down, the bowl leading, the fist following), not straight through
        fist = (fist_knock * (1 - low) + np.asarray(lap) * low
                + np.array((0.03, -0.05, 0.03)) * math.sin(math.pi * low))
        along = along_knock / np.linalg.norm(along_knock) * (1 - low) + np.asarray(lap_along) / np.linalg.norm(lap_along) * low
        knock = sum(math.exp(-((t - a) / 0.05) ** 2) for a in TAPS)
        body = jt.tsuru_sit(t, turn=-14.0 * (1 - up) + 4.0 * up, down=10.0 * (1 - up) - 6.0 * up + 1.5 * knock,
                            eyes=(18.0 * (1 - up) - 2.0 * up, -6.0 * (1 - up)), lean=6.0 * (1 - low))
        # the fist is close in by her shoulder at the post: start the elbow folded so the IK bends it out and down,
        # not up behind her
        # (and the upper arm started hanging by her side, not from the T-pose: so the IK folds the elbow down and
        # back, not up behind her)
        fold = {"leftLowerArm": vrm.fold("leftLowerArm", 80.0 * (1 - low) + 20.0), "leftUpperArm": (0.0, 70.0, 0.0)}
        st.pose("tsuru", f, {**body, **fold, **jt.pipe_fingers(st), **jt.knee_fingers()},
                hips=jt.tsuru_hips(st, t))
        (p0, q0), (p1, q1) = np.asarray(jt.PIPE_ARM["knock"], float), np.asarray(jt.PIPE_ARM["lap"], float)
        jt.hold_pipe(st, f, fist, along, palm_turn=(p0 + (p1 - p0) * low, q0 + (q1 - q0) * low))
        jt.knee_hand(st, f)
        smile = jt.ramp(t, *SMILE)
        st.face("tsuru", f, {"s4-calm": 1.0, "s4-smile": 0.8 * smile})
        jt.shinza_hold(st, f, t)


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
