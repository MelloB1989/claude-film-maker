"""Shot 8, refuse: Tsuru in profile, close, facing into the right of the frame where the river lies white with rain;
behind her, far and soft, the jetty and the hut's red lantern, where Shinza stands waiting, out of the frame. She has
just taken the pipe from her lips: she lets the smoke out in a long breath that the rain tears apart, says, not
looking at him, "I don't cross on rainy days." (line 4), and lifts the pipe back to her mouth as if that settled it.
Its bowl's thread curls up through the space she looks into. The camera creeps in.

The set, the cast and the compositing are rf/jetty_end.py's.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

SHOT = {"scene": "refuse"}

# the camera off her right side (metres out, along her facing, up), its aim ahead of her face (her lead room), the
# lens; easing in over the shot
SIDE = ((2.0, 0.35, 0.0), (1.82, 0.32, 0.01))
LEAD = 0.32
LENS = (65.0, 68.0)
FSTOP = 2.0
LINE = (0.9, 2.89)          # line 4 (data/dialogue_timing.json L04), s into the shot
EXHALE = (0.0, 0.75)        # s: the breath of smoke she lets out before she speaks
WORDS = (0.95, 1.4)         # ... and the last of it on her first words
LIFT = (2.95, 3.95)         # s: the pipe back up toward her lips (the cut comes on the move)
LIFT_TO = 0.85              # how far it gets by the cut
SKY_RIM, LANTERN_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18)
LOOK = dict(para=(0.5, 0.53, 0.7), para_from=(0.85, 0.9), para_to=(0.15, 0.1), para_amount=0.4,
            rims=[((1.0, 0.45), SKY_RIM, 0.35, 0.0035, 0.9), ((-1.0, 0.2), LANTERN_RIM, 0.18, 0.003, 0.9)],
            wrap=0.3, wrap_width=0.02, haze_amount=0.02)


def build(ctx):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import smoke, toon

    from rf import jetty_end as je
    from rf import sets
    from rf.vroid_common import to_frame

    f = je.heading_vec(je.SEAT["heading"])
    r = np.array((f[1], -f[0], 0.0))       # her right
    w = je.world(ctx, rain_box=((-2.0, -3.0, -0.6), (10.0, 7.0, 4.5)), clear=1.4, near=5.0,
                 river_splashes=((2.0, 1.3, sets.WATER_Z + 0.002), (14.0, 9.0, sets.WATER_Z + 0.002)))
    # her key from beyond her and above, so the cheek toward the lens falls into the 1st shade
    key_from = tuple(f * 1.0 - r * 0.35 + np.array((0.0, 0.0, 0.75)))
    tsuru = je.cast_member(w, "tsuru", at=je.SEAT["at"], heading=je.SEAT["heading"], key_from=key_from,
                           pipe="hand", pole="boat", seated=True)
    je.rain_in_cast(w)
    je.pole_in_boat(tsuru)
    ch = tsuru["vrm"]
    head = np.array(ch.face())

    cam, target = je.camera(ctx, LENS[0], FSTOP)
    n = (ctx.f1 - ctx.f0) / ctx.fps

    def at(t):
        k = je.ease(t / n)
        d, fw, up = je.lerp(*SIDE, k)
        loc = head + r * d + f * fw + np.array((0.0, 0.0, up))
        aim = head + f * LEAD - np.array((0.0, 0.0, 0.05))
        return tuple(loc), tuple(aim), LENS[0] + (LENS[1] - LENS[0]) * k, FSTOP

    where = je.key_camera(ctx, cam, target, at, focus=lambda t: tuple(head))
    je.outlines(ctx, {"tsuru": tsuru}, where)

    # her face: calm, the mouth moving through her line; the chin up a touch as she speaks, eyes ahead throughout
    for fr in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (fr - ctx.f0) / ctx.fps
        je.talk(ch, tsuru["face"](0.55), t, [LINE], fr, amount=0.55)
    je.breathe(ctx, ch, rate=0.25, depth=1.2,
               extra=lambda t: {"head": (-3.0 * je.ease((t - LINE[0] + 0.2) / 0.4) * (1 - 0.5 * je.ease((t - LINE[1]) / 0.6))
                                         + 2.0 * je.ease((t - EXHALE[0]) / 0.3) * (1 - je.ease((t - EXHALE[1]) / 0.3)),
                                         0.0, 0.0)})

    # the pipe back up toward her lips: the left hand's IK target carried toward where the mouthpiece meets them
    target_h = ch.handles["leftHand-target"]
    base = np.array(target_h.location)
    pipe = tsuru["parts"]["pipe"]
    piece = pipe[1]                                          # the brass mouthpiece
    from mathutils import Vector

    tip = np.array(sum((piece.matrix_world @ Vector(c) for c in piece.bound_box), Vector()) / 8)
    lips = je.mouth(tsuru, forward=0.075, down=0.065)(ctx.f0)
    shift_cf = to_frame(ch, lips) - to_frame(ch, tip)
    shift_arm = np.array(ch.to_armature(shift_cf))
    for fr in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (fr - ctx.f0) / ctx.fps
        k = LIFT_TO * je.ease((t - LIFT[0]) / (LIFT[1] - LIFT[0]))
        target_h.location = Vector(base + shift_arm * k)
        target_h.keyframe_insert("location", frame=fr)

    je.composite(ctx, w, lambda t: LOOK)

    rain = w["state"].rain.density
    t0 = ctx.f0 / ctx.fps
    bowl, top = je.bowl(tsuru)
    wisp = smoke.Wisp(rain=rain, wind=(0.05, 0.03, 0.0), width=(0.003, 0.07), seed=11)
    rb = smoke.ribbon("pipe-smoke", wisp, source=bowl, offset=top, coll=toon.collection("smoke"), also=(w["cast"],),
                      color=je.SMOKE)
    breath = smoke.Wisp(rain=rain, wind=(0.05, 0.03, 0.0), push=tuple(f * 0.35 + np.array((0.0, 0.0, 0.03))),
                        width=(0.012, 0.14), life=2.2, rise=0.1, curl=0.07, opacity=0.8, rate=48.0,
                        emit=((t0 + EXHALE[0] - 0.3, t0 + EXHALE[1]), (t0 + WORDS[0], t0 + WORDS[1])), seed=12)
    rb2 = smoke.ribbon("breath", breath, source=je.mouth(tsuru), coll=toon.collection("smoke"), also=(w["cast"],),
                       color=je.SMOKE)
    rb.bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
    rb2.bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
