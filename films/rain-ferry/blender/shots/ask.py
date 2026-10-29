"""Shot 7, ask: behind Tsuru. Her straw cape fills the right of the frame, her pipe at her lips, its smoke going up
past her white bun and beaten down by the rain; out on the jetty, small at first and soft, Shinza comes on toward
her under his kasa, his footfalls on the wet planks, and stops a couple of paces behind her, at the left third, the
hut's red lantern far off between them. The focus leaves her and finds him as he stops; a held breath; he lifts his
chin and speaks (line 3, "Old woman. Take me across."). She lets out her smoke as he comes and does not turn.

The set, the cast and the compositing are rf/jetty_end.py's.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

SHOT = {"scene": "ask"}

# the camera, low behind her right shoulder, easing in a little over the shot
CAM = ((7.6, -0.9, 1.2), (7.38, -0.78, 1.17))
AIM = ((3.0, 0.9, 0.9), (3.15, 0.82, 0.98))
LENS = (35.0, 37.0)
FSTOP = 2.8
RACK = (1.5, 2.3)            # s: the focus pulls from her to him as he stops
# Shinza up the jetty to his mark: from (x, y), the time he walks (s into the shot; already walking when it opens)
WALK_FROM = (-0.6, -0.3)
WALK = (-0.8, 2.15)
LINE = (2.4, 4.56)           # line 3 (data/dialogue_timing.json L03), s into the shot
CHIN = 2.2                   # he lifts his chin to speak
EXHALE = (0.5, 1.2)          # s: she lets out her smoke as he comes
SKY_RIM, LANTERN_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18)
LOOK = dict(para=(0.5, 0.53, 0.7), para_from=(0.8, 0.9), para_to=(0.3, 0.05), para_amount=0.35,
            rims=[((-0.6, 0.8), SKY_RIM, 0.3, 0.003, 0.9), ((-1.0, 0.1), LANTERN_RIM, 0.15, 0.0025, 0.9)],
            wrap=0.2, wrap_width=0.012, haze_amount=0.035)


def build(ctx):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import smoke, toon

    from rf import jetty_end as je
    from rf import sets

    w = je.world(ctx, rain_box=((-6.0, -3.0, -0.6), (9.5, 6.0, 5.0)), clear=1.2, near=3.5,
                 deck_splashes=((sets.SPAN[0], -sets.HALF + 0.05, 0.004), (sets.SPAN[1], sets.HALF - 0.05, 0.004)),
                 river_splashes=((-6.0, 1.2, sets.WATER_Z + 0.002), (9.5, 7.0, sets.WATER_Z + 0.002)))
    tsuru = je.cast_member(w, "tsuru", at=je.SEAT["at"], heading=je.SEAT["heading"], key_from=(0.3, 1.0, 0.8),
                           pipe="mouth", pole="boat", seated=True)
    shinza = je.cast_member(w, "shinza", at=WALK_FROM, heading=0.0, key_from=(1.0, -0.4, 0.8), kasa="on",
                            sword="back")
    je.rain_in_cast(w)
    je.pole_in_boat(tsuru)

    cam, target = je.camera(ctx, LENS[0], FSTOP)
    n = (ctx.f1 - ctx.f0) / ctx.fps

    def at(t):
        k = je.ease(t / n)
        return je.lerp(*CAM, k), je.lerp(*AIM, k), LENS[0] + (LENS[1] - LENS[0]) * k, FSTOP

    her = (je.SEAT["at"][0], je.SEAT["at"][1], 1.0)
    him = (je.MARK["at"][0], je.MARK["at"][1], 1.55)
    where = je.key_camera(ctx, cam, target, at,
                          focus=lambda t: je.lerp(her, him, je.ease((t - RACK[0]) / (RACK[1] - RACK[0]))))
    je.outlines(ctx, {"tsuru": tsuru, "shinza": shinza}, where)

    je.walk(ctx, shinza, WALK_FROM, je.MARK["at"], *WALK)
    sh = shinza["vrm"]
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        je.talk(sh, shinza["face"](1.0), t, [LINE], f, amount=0.6)
    # his chin up to speak, held; a settle of the shoulders as he stops
    je.breathe(ctx, sh, rate=0.3, depth=1.0,
               extra=lambda t: {"head": (-6.0 * je.ease((t - CHIN) / 0.35), 0.0, 0.0),
                                "neck": (-2.0 * je.ease((t - CHIN) / 0.35), 0.0, 0.0)})
    # her breath out of the smoke, the head easing back a little as she lets it go
    je.breathe(ctx, tsuru["vrm"], extra=lambda t: {"head": (-3.0 * je.ease((t - EXHALE[0] + 0.3) / 0.4)
                                                           * (1 - je.ease((t - EXHALE[1]) / 0.8)), 0.0, 0.0)})

    lantern = w["crossing"]["lantern"]
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        lantern.rotation_euler = (math.radians(4) * math.sin(2 * math.pi * 0.6 * t + 2.0),
                                  math.radians(2) * math.sin(2 * math.pi * 0.45 * t + 3), 0)
        lantern.keyframe_insert("rotation_euler", frame=f)

    je.composite(ctx, w, lambda t: LOOK)

    rain = w["state"].rain.density
    t0 = ctx.f0 / ctx.fps
    bowl, top = je.bowl(tsuru)
    wisp = smoke.Wisp(rain=rain, wind=(0.06, 0.03, 0.0), seed=7)
    rb = smoke.ribbon("pipe-smoke", wisp, source=bowl, offset=top, coll=toon.collection("smoke"), also=(w["cast"],),
                      color=je.SMOKE)
    f = je.heading_vec(je.SEAT["heading"])
    breath = smoke.Wisp(rain=rain, wind=(0.06, 0.03, 0.0), push=tuple(f * 0.3 + (0.0, 0.0, 0.04)), width=(0.012, 0.12),
                        life=2.0, rise=0.12, curl=0.06, opacity=0.75, emit=((t0 + EXHALE[0], t0 + EXHALE[1]),), seed=8)
    rb2 = smoke.ribbon("breath", breath, source=je.mouth(tsuru), coll=toon.collection("smoke"), also=(w["cast"],),
                       color=je.SMOKE)
    rb.bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
    rb2.bake(ctx.scene, ctx.f0, ctx.f1, ctx.fps)
