"""Shot 23, the kneel: Shinza on his knees in the rain, his broken sword across his hands, staring at it. "...Then what
is it?" (L13)

From his front right and above him, so the rain falls past the lens onto him and he is small under it: the blade's
broken end catching the light across the frame, his head hung over it, the hut and its red lantern far behind him,
soft. The camera creeps in from a medium shot toward his face. His grip tightens on the hilt before he speaks; he
asks it of the blade, low; after it his eyes lift a little, toward where she went.

RF_S7_CAST=none builds the shot without its cast.
"""
from __future__ import annotations

import math
import os

SHOT = {"scene": "kneel"}

LINE = (92.0, 93.73)        # L13 (film s)
BEARING = -30.0             # degrees from his front toward his right: where the camera looks at him from
DIST = (2.35, 1.55)         # m from his face, from and to
HEIGHT = (0.62, 0.42)       # m over his eyes
LENS, FSTOP = 50.0, 2.0
GRIP = (91.45, 91.9)        # film s: his grip tightening, the blade lifting a little
LIFT = (93.95, 94.55, 7.0)  # after the line: his head lifts this many degrees (and his eyes with it)


def build(ctx):
    import sys
    from pathlib import Path

    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import toon3d
    from rf import ending as E

    st = E.stage(ctx, near=4.0, clear=1.0)
    m = E._mats(st.look, "ending")
    E.blade_tip("shinza-blade", m, st.crossing["near"])
    E.headband("shinza-headband", m["band"], st.crossing["near"], E.HEADBAND_AT[:2], E.HEADBAND_AT[2])
    actors = None
    eyes = np.array([E.SHINZA_AT[0], E.SHINZA_AT[1], 0.98])

    if os.environ.get("RF_S7_CAST", "vroid") != "none":
        from lib import vrm

        actors = E.cast(st, ("shinza",))
        sh = actors["shinza"]
        ch = sh["vrm"]
        E.place(sh, E.SHINZA_AT, E.SHINZA_FACING)
        E.hide([ob for ob in sh["props"]] + [ob for ob in sh["root"].children_recursive if "-band" in ob.name])
        E.kneel(sh)
        E.hold_blade(sh, m, st.cast)
        eyes = np.array(ch.face())
        hand = {side: ch.handles[f"{side}Hand-target"] for side in ("left", "right")}
        rest = {side: np.array(h.location) for side, h in hand.items()}
        up = np.array(ch.to_armature((0.0, 0.0, 1.0))) - np.array(ch.to_armature((0.0, 0.0, 0.0)))
        for f in range(ctx.f0 - 1, ctx.f1 + 1):
            t = ctx.time(f)
            breath = math.sin(2 * math.pi * 0.5 * t)
            grip = E.ease((t - GRIP[0]) / (GRIP[1] - GRIP[0]))
            lift = E.ease((t - LIFT[0]) / (LIFT[1] - LIFT[0])) * LIFT[2]
            shake = 0.0025 * grip * math.sin(2 * math.pi * 9.0 * t)       # the blade trembling in his hands
            sag = dict(E.SAG)
            sag["spine"] = (E.SAG["spine"][0] + 1.5 * breath, 0.0, 0.0)
            sag["chest"] = (E.SAG["chest"][0] - 2.0 * grip, 0.0, 0.0)      # his shoulders set as he grips
            sag["head"] = (E.SAG["head"][0] + 4.0 - lift, 0.0, -2.0)
            sag["leftEye"] = sag["rightEye"] = (14.0 - 1.4 * lift, 0.0, 0.0)
            E.kneel(sh, sag=sag, hips_dz=0.004 * breath, frame=f, legs=False)
            for side, h in hand.items():
                h.location = rest[side] + up * (0.03 * grip + shake) / ch.scale
                h.keyframe_insert("location", frame=f)
            vrm.express(ch, {"sad": 0.35, "aa": 0.8 * E.mouth(t, [LINE])}, frame=f)
        # his key from beyond him on his left, high: the camera sees his face in the 1st shade, his hair and shoulders
        # edged, the blade's flat lit
        toon3d.aim(sh["key"], (-0.5, 0.9, 1.0))

    b = math.radians(math.degrees(E.SHINZA_FACING) + BEARING)
    toward = np.array([math.cos(b), math.sin(b), 0.0])
    n = (ctx.f1 - ctx.f0) / ctx.fps

    def setup(t):
        k = E.ease(t / n)
        d = DIST[0] + (DIST[1] - DIST[0]) * k
        at = eyes + toward * d + np.array([0.0, 0.0, HEIGHT[0] + (HEIGHT[1] - HEIGHT[0]) * k])
        at = at + np.array(E.drift(t, 0.008, seed=3))
        aim = eyes + np.array([0.0, 0.0, -0.28 + 0.12 * k])
        return tuple(at), tuple(aim), LENS, FSTOP, tuple(eyes)

    E.camera(ctx, setup)

    def look(f, s):
        L = s.light
        return dict(rims=[((-0.7, 1.0), L.rim, 0.35, 0.003, 0.9), ((-1.0, 0.2), L.accent, 0.12, 0.003, 0.9)],
                    para_from=(0.5, 0.9), para_to=(0.5, 0.0))

    E.finish(ctx, st, look, actors, lambda f: LENS)
