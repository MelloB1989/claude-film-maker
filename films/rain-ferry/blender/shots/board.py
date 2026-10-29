"""Shot 24, the board: the turn of the film. Tsuru has stepped down into the ferry; she settles at its stern, her pole
upright in her hand, and says "Get in." (L14) without looking round at him. Then she stops, and looks up: the rain is
giving out. The drops thin to nothing, the rings go off the water, and as the last of it falls she says "The rain has
stopped." (L15); the light begins to warm on her lifted face, and a faint smile.

Low on the jetty in front of her, as she stands at the stern turned to it (to him): the open river behind her running
down the valley, the awning at the frame's right, the sky over her. The camera breathes in toward her; as she lifts her face it sinks a little
so the sky opens over her.

The rain's density, the water's rings, the sheen and the key's warmth are the look schedule's (data/look.json
"board"). RF_S7_CAST=none builds the shot without its cast.
"""
from __future__ import annotations

import math
import os

SHOT = {"scene": "board"}

LINES = {"get_in": (95.2, 95.85), "stopped": (97.2, 98.83)}   # L14, L15 (film s)
SETTLE = (94.6, 95.15, 0.07)      # film s: her weight coming down into the boat from this much higher
LOOK_UP = (96.15, 96.95, 30.0)    # film s: her face lifting to the sky, this many degrees
SMILE = (98.9, 99.7)              # film s: the faint smile after it
# the camera, low on the jetty in front of her, the awning off to the right (in the boat's frame from its stern anchor:
# x toward the bow, -y toward the jetty): from, to; lower once she looks up
CAM = ((-0.45, -2.75, 0.98), (-0.3, -2.25, 0.9))
FACING = -90.0                    # degrees in the boat's frame: she faces the jetty (him), her back to the river
SINK = 0.18
LENS, FSTOP = (36.0, 42.0), 2.8


def build(ctx):
    import sys
    from pathlib import Path

    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, toon3d
    from rf import ending as E

    st = E.stage(ctx)
    stern = st.world["anchors"]["boat_stern"]
    actors = None

    if os.environ.get("RF_S7_CAST", "vroid") != "none":
        from lib import vrm
        from rf import vroid_tsuru as T

        actors = E.cast(st, {"tsuru": dict(pole="hand")})
        ts = actors["tsuru"]
        # Tsuru at the stern, riding the boat, turned to the jetty (to him, toward us)
        ts["root"].parent = stern
        ts["root"].matrix_parent_inverse.identity()
        ts["root"].location = (0.0, 0.0, 0.0)
        ts["root"].rotation_euler = (0.0, 0.0, math.radians(FACING))
        ch = ts["vrm"]
        fingers = vrm.grip_pose("right", 0.95)
        for f in range(ctx.f0 - 1, ctx.f1 + 1):
            t = ctx.time(f)
            settle = SETTLE[2] * (1.0 - E.ease((t - SETTLE[0]) / (SETTLE[1] - SETTLE[0])))
            up = LOOK_UP[2] * E.ease((t - LOOK_UP[0]) / (LOOK_UP[1] - LOOK_UP[0]))
            breath = math.sin(2 * math.pi * 0.3 * t)
            pose = dict(T.TS_POSE, **fingers)
            sx, sy, sz = pose["upperChest"]
            pose["upperChest"] = (sx - up * 0.25 + 0.8 * breath, sy, sz)
            hx, hy, hz = pose["head"]
            pose["head"] = (hx - up * 0.75, hy, hz)
            pose["leftEye"] = pose["rightEye"] = (-up * 0.4, 0.0, 0.0)
            hips = T.TS_HIPS
            vrm.pose(ch, pose, hips=(hips[0], hips[1], hips[2] + settle * 0.6), frame=f)
            smile = E.ease((t - SMILE[0]) / (SMILE[1] - SMILE[0]))
            speak = E.mouth(t, list(LINES.values()), rate=6.0)
            vrm.express(ch, {**ts["face"](), "aa": 0.6 * speak, "happy": 0.12 * smile}, frame=f)
        # her key from the sky over the river behind the camera, high: her lifted face lit
        toon3d.aim(ts["key"], (0.3, 0.8, 1.0))

    # the camera in the boat's frame at the start (the boat bobs a little under it: a camera on the water)
    import bpy

    bpy.context.view_layer.update()
    M = np.array(stern.matrix_world)

    def world(p):
        return tuple((M @ np.append(np.asarray(p, float), 1.0))[:3])

    face = world((0.0, 0.0, 1.32))
    c0, c1 = world(CAM[0]), world(CAM[1])
    a0 = (face[0], face[1], face[2] - 0.18)
    a1 = (face[0], face[1], face[2] - 0.05)
    focus = E.head_of(actors["tsuru"]) if actors else face
    rig = cinema.film(ctx, [
        cinema.Setup("board", 0.0, cinema.drift(cinema.path([c0, c1, (c1[0], c1[1], c1[2] - SINK)], [a0, a1, a1]),
                                                0.02),
                     lens=LENS, fstop=FSTOP, focus=focus, shake=cinema.Shake(breath=0.07, seed=24)),
    ])
    E.weather(ctx, st, rig)

    def look(f, s):
        L = s.light
        return dict(rims=[((0.4, 1.0), L.rim, 0.3 + 0.25 * s.warm, 0.003, 0.9)], para_from=(0.5, 0.9),
                    para_to=(0.5, 0.1))

    E.finish(ctx, st, look, actors, lambda f: LENS[0] + (LENS[1] - LENS[0]) * (f - ctx.f0) / (ctx.f1 - ctx.f0))
