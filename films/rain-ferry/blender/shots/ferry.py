"""Shot 6, the ferry: the crossing in the rain, wide. From up the muddy bank, the whole place of the duel: the
thatched hut at the left with its red lantern, the jetty running out from under it across the frame into the river,
the covered boat moored alongside, and at the jetty's end, small, a caped figure sitting on a crate and smoking, her
smoke a pale thread the rain keeps knocking down; ridge after ridge of mountains fading into the mist beyond. Shinza
comes into the bottom left, his back to us under his kasa, and walks on down the bank toward the jetty. The camera
eases in and down a little, as if it walked a step after him.

The set, the cast and the compositing are rf/jetty_end.py's (the staging shared by the shots at the jetty's end).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

SHOT = {"scene": "ferry"}

# the camera: from up the bank, easing in (s: the push takes the whole shot)
CAM = ((-10.5, -8.0, 2.6), (-9.7, -7.15, 2.38))
AIM = ((0.5, 2.6, 0.4), (1.1, 2.5, 0.42))
LENS = (24.0, 25.0)
FSTOP = 8.0
# Shinza down the bank toward the jetty's root: from, to (x, y), the time he walks (s into the shot)
WALK = ((-10.2, -4.9), (-7.3, -1.0), -0.6, 6.2)
# her smoke, made larger than life so a thread reads from this far (she is ~17 m off)
WISP = dict(width=(0.012, 0.2), life=3.6, rise=0.3, curl=0.12, rate=24.0)
EXHALE = (2.6, 3.3)          # s into the shot: she lets out a breath of smoke
LOOK = dict(para=(0.52, 0.55, 0.7), para_from=(0.5, 0.7), para_to=(0.5, 0.05), para_amount=0.25,
            rims=[((-0.2, 1.0), (0.6, 0.68, 0.85), 0.2, 0.0015, 0.8)], wrap=0.08, wrap_width=0.003, haze_amount=0.06)


def build(ctx):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import smoke, toon

    from rf import jetty_end as je
    from rf import sets

    w = je.world(ctx, rain_box=((-14.0, -9.0, -0.6), (9.0, 6.0, 6.0)), clear=1.5, near=4.0,
                 deck_splashes=((sets.SPAN[0], -sets.HALF + 0.05, 0.004), (sets.SPAN[1], sets.HALF - 0.05, 0.004)),
                 river_splashes=((-5.0, -4.0, sets.WATER_Z + 0.002), (12.0, 8.0, sets.WATER_Z + 0.002)))
    tsuru = je.cast_member(w, "tsuru", at=je.SEAT["at"], heading=je.SEAT["heading"], key_from=(-0.6, -1.0, 0.8),
                           pipe="mouth", pole="boat", seated=True)
    shinza = je.cast_member(w, "shinza", at=WALK[0], heading=0.0, key_from=(0.4, -1.0, 0.8), kasa="on", sword="back")
    je.rain_in_cast(w)
    je.pole_in_boat(tsuru)

    cam, target = je.camera(ctx, LENS[0], FSTOP)

    def at(t):
        k = je.ease(t / ((ctx.f1 - ctx.f0) / ctx.fps))
        return je.lerp(*CAM, k), je.lerp(*AIM, k), LENS[0] + (LENS[1] - LENS[0]) * k, FSTOP

    where = je.key_camera(ctx, cam, target, at, focus=lambda t: (4.5, 0.4, 0.8))
    je.outlines(ctx, {"tsuru": tsuru, "shinza": shinza}, where)

    je.walk(ctx, shinza, WALK[0], WALK[1], WALK[2], WALK[3])
    je.breathe(ctx, tsuru["vrm"], extra=lambda t: {"head": (-2.0 * je.ease((t - EXHALE[0] + 0.5) / 0.6)
                                                           * (1 - je.ease((t - EXHALE[1]) / 0.8)), 0.0, 0.0)})

    # the hut's lantern swings in the wind
    lantern = w["crossing"]["lantern"]
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        lantern.rotation_euler = (math.radians(4) * math.sin(2 * math.pi * 0.6 * t),
                                  math.radians(2) * math.sin(2 * math.pi * 0.45 * t + 1), 0)
        lantern.keyframe_insert("rotation_euler", frame=f)

    je.composite(ctx, w, lambda t: LOOK)

    rain = w["state"].rain.density
    t0 = ctx.f0 / ctx.fps
    bowl, top = je.bowl(tsuru)
    wisp = smoke.Wisp(rain=rain, wind=(0.12, 0.05, 0.0), seed=3, **WISP)
    rb = smoke.ribbon("pipe-smoke", wisp, source=bowl, offset=top, coll=toon.collection("smoke"),
                      also=(w["cast"],), color=je.SMOKE)
    breath = smoke.Wisp(rain=rain, wind=(0.12, 0.05, 0.0), push=(0.25, 0.25, 0.05), width=(0.03, 0.3), life=2.2,
                        rise=0.2, curl=0.1, rate=24.0, opacity=0.8, emit=((t0 + EXHALE[0], t0 + EXHALE[1]),), seed=4)
    rb2 = smoke.ribbon("breath", breath, source=je.mouth(tsuru), coll=toon.collection("smoke"), also=(w["cast"],),
                       color=je.SMOKE)
    rb.bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
    rb2.bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)

