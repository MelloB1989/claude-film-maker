"""Shot 22, the lesson: Tsuru walks away to the boat, her pole on her shoulder, not looking back, while Shinza stays on
his knees in the rain where he went down. "Strength..." / "...isn't how many you've cut down." (L12)

From past the jetty's end, a little above him, looking back along it toward the bank: Shinza on his knees in the left foreground as
shot 21 left him (rf/clash.py's FALL: slumped, the stub in his right hand, its broken end on the planks), his head
hung; behind him the wet planks run away to the hut and its red lantern, and Tsuru walks away along the moored boat
toward its stern, small and upright, her pole on her shoulder. The camera eases in a little and up; it holds her in
focus while she speaks, then, as the line lands, the focus comes back to him and his head sinks.

The marks are rf/clash.py's (END, FALL), the stage rf/ending.py's; the weather and light the look schedule's.
RF_S7_CAST=none builds the shot without its cast.
"""
from __future__ import annotations

import math
import os

SHOT = {"scene": "lesson"}

LINE = (85.9, 90.1)       # L12 (film s)
# the camera (world m): from, to (eased over the shot), its aim, lens, f-stop
CAM = ((9.7, 1.05, 1.42), (9.35, 1.0, 1.52))
AIM = ((0.0, -0.5, 0.45), (0.0, -0.5, 0.62))
LENS, FSTOP = 35.0, 2.4
RACK = (88.7, 89.7)       # film s: the focus from her back to him
SETS_OFF = 0.35           # s into the shot: she turns away and walks
HEAD_SINK = (88.9, 90.4, 9.0)   # his head sinks this many degrees more as the line lands


def build(ctx):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, toon3d
    from rf import ending as E

    st = E.stage(ctx)
    t0 = ctx.time(ctx.f0)
    actors = None
    shinza_eyes = (*E.SHINZA_AT, 0.95)

    if os.environ.get("RF_S7_CAST", "vroid") != "none":
        from lib import vrm, vrm_anim as va
        from rf import clash, vroid_tsuru as T

        actors = E.cast(st, {"shinza": dict(kasa="back", sword="broken", headband=True), "tsuru": dict(pole="shoulder")})
        sh, ts = actors["shinza"], actors["tsuru"]
        # Shinza: as the fall left him; breathing hard, his head sinking as the line lands
        E.stick_half(sh)
        E.cut_headband(sh)
        fall = E.shot_module("fall")
        sx, sy, sz = fall.KNEEL["spine"]
        hx, hy, hz = fall.KNEEL["head"]
        for f in range(ctx.f0 - 1, ctx.f1 + 2, 2):
            t = ctx.time(f)
            breath = math.sin(2 * math.pi * 0.42 * (t - t0))
            sink = HEAD_SINK[2] * E.ease((t - HEAD_SINK[0]) / (HEAD_SINK[1] - HEAD_SINK[0]))
            p, fingers = E.fallen(sh, turns={"spine": (sx + 2.0 * breath, sy, sz), "head": (hx + sink, hy, hz)})
            p.hips = (p.hips[0], p.hips[1], p.hips[2] + 0.004 * breath)
            clash.apply(sh, p, fingers=fingers)
            clash.key(sh, f, face={"sad": 0.3})
        # Tsuru: from her END mark, the pole on her shoulder, walking away to the ferry's stern; never turning back
        (x, y), yaw = clash.END["tsuru"]
        E.place(ts, (x, y), yaw)
        perf = va.Performance(ts["vrm"], fps=ctx.fps, seed=22)
        carriage = {**T.TS_POSE, **vrm.grip_pose("right", 0.95), "head": (-46.0, 0.0, 0.0)}
        perf.pose(ctx.f0 - 1, carriage)
        perf.walk(E.TSURU_WALK, ctx.f0 + round(SETS_OFF * ctx.fps), gait="old", pose=carriage, end_pose=carriage,
                  swing=(0.5, 0.0))
        perf.breathe(rate=0.22, depth=0.6)
        perf.blinks(seed=22)
        perf.bake(ctx.f0 - 1, ctx.f1 + 1)
        # their keys from beyond the boat (the open sky over the river): his face and front in the 1st shade toward
        # the lens, her back edged
        toon3d.aim(sh["key"], (-0.3, 1.0, 0.8))
        toon3d.aim(ts["key"], (0.2, 1.0, 0.8))

    her = E.head_of(actors["tsuru"]) if actors else E.point_focus("tsuru-at", (*E.TSURU_WALK[-1], 1.3))
    him = E.head_of(actors["shinza"]) if actors else E.point_focus("shinza-at", shinza_eyes)
    rig = cinema.film(ctx, [cinema.Setup(
        "lesson", 0.0, cinema.drift(cinema.line(CAM[0], CAM[1], AIM[0], AIM[1]), 0.02), ease="sine", lens=LENS,
        fstop=FSTOP, focus=her, racks=(cinema.Rack(RACK[0] - t0, him, RACK[1] - RACK[0]),),
        shake=cinema.Shake(breath=0.08))])
    E.weather(ctx, st, rig)

    def look(f, s):
        L = s.light
        return dict(rims=[((0.6, 1.0), L.rim, 0.3, 0.003, 0.8), ((-0.8, 0.3), L.accent, 0.1, 0.003, 0.9)],
                    para_from=(0.5, 0.75), para_to=(0.3, 0.05))

    E.finish(ctx, st, look, actors, lambda f: LENS)
