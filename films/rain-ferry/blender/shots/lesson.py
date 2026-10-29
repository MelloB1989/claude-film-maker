"""Shot 22, the lesson: Tsuru walks away to the boat, her pole on her shoulder, not looking back, while Shinza stays on
his knees in the rain where he went down. "Strength..." / "...isn't how many you've cut down." (L12)

Low behind Shinza's left shoulder, his bowed back a dark mass on the left third, the wet planks running away past
him to the moored boat; Tsuru small and upright beyond him on the right, walking out of the shot's depth. The camera
eases in after her and a little up; it holds her in focus while she speaks, then, as the line lands, the focus comes
back to him (his head sinking).

The stage is rf/ending.py's (where he knelt, the broken blade, the cut headband); the weather and light are the look
schedule's. RF_S7_CAST=none builds the shot without its cast (the set, the weather and the camera alone).
"""
from __future__ import annotations

import math
import os

SHOT = {"scene": "lesson"}

LINE = (85.9, 90.1)       # L12 (film s)
# the camera (world m): from, to (eased over the shot), its aim, lens, f-stop
CAM = ((0.95, -2.35, 0.62), (1.35, -1.95, 0.7))
AIM = ((5.6, 1.15, 0.72), (5.6, 1.3, 0.78))
LENS, FSTOP = 32.0, 2.4
RACK = (88.7, 89.7)       # film s: the focus from her back to him
WALK_FROM, WALK_TO = 0.1, 5.2   # s into the shot: she walks the whole way, easing in and out
HEAD_SINK = (88.9, 90.4, 9.0)   # his head sinks this many degrees more as the line lands


def build(ctx):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import toon3d
    from rf import ending as E

    st = E.stage(ctx)
    t0 = ctx.time(ctx.f0)
    actors = None
    shinza_at = (*E.SHINZA_AT, 0.95)
    tsuru_at = lambda t: (*E.path_at(E.TSURU_WALK, distance(t))[0], 1.3)   # noqa: E731
    length = E.path_length(E.TSURU_WALK)

    def distance(t):
        return length * E.smooth((t - WALK_FROM) / (WALK_TO - WALK_FROM)) * 0.98

    E.headband("shinza-headband", E.band_material(st.look), st.world["near"], E.HEADBAND_AT[:2], E.HEADBAND_AT[2])

    if os.environ.get("RF_S7_CAST", "vroid") != "none":
        from lib import vrm
        from rf import vroid_tsuru as T

        actors = E.cast(st, {"shinza": dict(kasa=None, sword="broken", headband=False), "tsuru": dict(pole="shoulder")})
        sh, ts = actors["shinza"], actors["tsuru"]
        # Shinza: on his knees, what is left of his sword slack across his lap, its other half standing in the planks
        # ahead of him
        E.place(sh, E.SHINZA_AT, E.SHINZA_FACING)
        E.kneel(sh)
        E.hold_blade(sh, at=(-0.12, -0.3, 0.4), d=(1.0, -0.25, -0.08), cradle=0.26, up=(0.0, 0.1, 1.0))
        for f in range(ctx.f0 - 1, ctx.f1 + 1):
            t = ctx.time(f)
            breath = math.sin(2 * math.pi * 0.42 * (t - t0))
            sink = HEAD_SINK[2] * E.ease((t - HEAD_SINK[0]) / (HEAD_SINK[1] - HEAD_SINK[0]))
            sag = dict(E.SAG)
            sag["spine"] = (E.SAG["spine"][0] + 1.5 * breath, 0.0, 0.0)
            sag["head"] = (E.SAG["head"][0] + sink, 0.0, -3.0)
            E.kneel(sh, sag=sag, hips_dz=0.004 * breath, frame=f, legs=False)
            vrm.express(sh["vrm"], {"sad": 0.3}, frame=f)
        # Tsuru: the pole on her shoulder, walking to the boat; her head level and a little down, never turning back
        E.place(ts, E.TSURU_WALK[0], 0.0)
        pose = {**T.TS_POSE, **vrm.grip_pose("right", 0.95), "head": (-46.0, 0.0, 0.0)}
        E.walk(ctx, ts, E.TSURU_WALK, distance, pose=pose, hips=T.TS_HIPS)
        for f in range(ctx.f0 - 1, ctx.f1 + 1):
            vrm.express(ts["vrm"], ts["face"](), frame=f)
        # their keys: from the front left of each (the sky over the river, beyond them), so the camera sees their
        # backs in the 1st shade with a lit edge
        toon3d.aim(sh["key"], (0.6, 1.0, 0.7))
        toon3d.aim(ts["key"], (0.2, 1.0, 0.8))

    def setup(t):
        k = E.ease(t * ctx.fps / (ctx.f1 - ctx.f0))
        dx, dy, dz = E.drift(t, 0.012)
        at = E.lerp(CAM[0], CAM[1], k)
        at = (at[0] + dx, at[1] + dy, at[2] + dz)
        rack = E.ease((t0 + t - RACK[0]) / (RACK[1] - RACK[0]))
        focus = E.lerp(tsuru_at(t), shinza_at, rack)
        return at, E.lerp(AIM[0], AIM[1], k), LENS, FSTOP, focus

    E.camera(ctx, setup)

    def look(f, s):
        L = s.light
        return dict(rims=[((0.6, 1.0), L.rim, 0.3, 0.003, 0.8)], para_from=(0.5, 0.75), para_to=(0.3, 0.05))

    E.finish(ctx, st, look, actors, lambda f: LENS)
