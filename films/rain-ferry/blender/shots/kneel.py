"""Shot 23, the kneel: Shinza on his knees in the rain, staring at his broken sword. "...Then what is it?" (L13)

From in front of him and a little above, the rain falling past the lens onto him, the jetty running
away behind him to the hut and its red lantern, soft. He starts as the lesson leaves him (shot 21's kneel, rf/clash.py's
FALL: the stub's broken end on the planks); then he lifts it in both hands and stares at where it broke. His grip
tightens before he speaks; he asks it of the blade, low; after it his eyes lift a little, toward where she went. The
camera creeps in from a medium shot toward his face.

RF_S7_CAST=none builds the shot without its cast.
"""
from __future__ import annotations

import math
import os

SHOT = {"scene": "kneel"}

LINE = (92.0, 93.73)        # L13 (film s)
BEARING = -24.0             # degrees from his front toward his right: where the camera looks at him from
DIST = (2.45, 1.85)         # m from his face, from and to
HEIGHT = (0.32, 0.2)        # m over his eyes
LENS, FSTOP = 50.0, 2.0
LIFT = (90.95, 91.85)       # film s: the stub lifted from the planks into both hands
STUB = ((-0.06, -0.24, 0.7), (0.38, -0.5, 0.78))   # (pommel, hilt direction) held up before him (his frame)
GRIP = (91.55, 91.95)       # film s: his grip tightening
EYES_UP = (93.95, 94.55, 7.0)   # after the line: his head lifts this many degrees (and his eyes with it)


def build(ctx):
    import sys
    from pathlib import Path

    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, toon3d
    from rf import ending as E

    st = E.stage(ctx)
    actors = None
    eyes = np.array([E.SHINZA_AT[0], E.SHINZA_AT[1], 0.95])

    if os.environ.get("RF_S7_CAST", "vroid") != "none":
        from rf import clash

        actors = E.cast(st, {"shinza": dict(kasa=None, sword="broken", headband=True)})
        sh = actors["shinza"]
        ch = sh["vrm"]
        E.stick_half(sh)
        E.cut_headband(sh)
        fall = E.shot_module("fall")
        for f in range(ctx.f0 - 1, ctx.f1 + 2, 2):
            t = ctx.time(f)
            breath = math.sin(2 * math.pi * 0.5 * t)
            lift = E.ease((t - LIFT[0]) / (LIFT[1] - LIFT[0]))
            grip = E.ease((t - GRIP[0]) / (GRIP[1] - GRIP[0]))
            up = E.ease((t - EYES_UP[0]) / (EYES_UP[1] - EYES_UP[0])) * EYES_UP[2]
            shake = 0.004 * grip * math.sin(2 * math.pi * 7.0 * t)        # the blade trembling in his hands
            turns = {k: v for k, v in fall.KNEEL.items()}
            sx, sy, sz = turns["spine"]
            turns["spine"] = (sx + 2.0 * breath - 4.0 * lift, sy, sz)
            cx, cy, cz = turns["chest"]
            turns["chest"] = (cx - 2.0 * grip, cy, cz)                   # his shoulders set as he grips
            hx, hy, hz = turns["head"]
            turns["head"] = (hx - 12.0 * lift - up, hy, hz * (1 - lift) + 6.0 * lift)
            turns["leftEye"] = turns["rightEye"] = (12.0 * lift - 1.5 * up, 0.0, 6.0 * lift)
            if LIFT[0] < t < LIFT[1]:
                continue                     # the lift: tweened between the fall's pose and the held stub
            pommel, hilt = STUB
            stub = (tuple(np.add(pommel, (0.0, 0.0, shake))), hilt) if lift >= 1.0 else None
            p, fingers = E.fallen(sh, turns=turns, stub=stub)
            p.hips = (p.hips[0], p.hips[1], p.hips[2] + 0.004 * breath)
            clash.apply(sh, p, fingers=fingers)
            clash.key(sh, f)
        _face(ctx, ch, LINE)
        eyes = np.array(ch.face())
        # his key from beyond him on his left, high: the camera sees his face in the 1st shade, his hair and shoulders
        # edged, the blade's flat lit
        toon3d.aim(sh["key"], (-0.5, 0.9, 1.0))

    b = math.radians(math.degrees(E.SHINZA_FACING) + BEARING)
    toward = np.array([math.cos(b), math.sin(b), 0.0])

    def at(k):
        d = DIST[0] + (DIST[1] - DIST[0]) * k
        return (eyes + toward * d + np.array([0.0, 0.0, HEIGHT[0] + (HEIGHT[1] - HEIGHT[0]) * k]),
                eyes + np.array([0.0, 0.0, -0.22 + 0.1 * k]))

    (c0, a0), (c1, a1) = at(0.0), at(1.0)
    focus = E.head_of(actors["shinza"]) if actors else tuple(eyes)
    rig = cinema.film(ctx, [cinema.Setup("kneel", 0.0, cinema.drift(cinema.line(c0, c1, a0, a1), 0.015), lens=LENS,
                                         fstop=FSTOP, focus=focus, shake=cinema.Shake(breath=0.06, seed=23))])
    E.weather(ctx, st, rig)

    def look(f, s):
        L = s.light
        return dict(rims=[((-0.7, 1.0), L.rim, 0.35, 0.003, 0.9), ((-1.0, 0.2), L.accent, 0.12, 0.003, 0.9)],
                    para_from=(0.5, 0.9), para_to=(0.5, 0.0))

    E.finish(ctx, st, look, actors, lambda f: LENS)


def _face(ctx, ch, line) -> None:
    """His face keyed every frame: a grieving set, the mouth flapping through the line."""
    from lib import vrm
    from rf import ending as E

    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = ctx.time(f)
        vrm.express(ch, {"sad": 0.45, "aa": 0.7 * E.mouth(t, [line])}, frame=f)
