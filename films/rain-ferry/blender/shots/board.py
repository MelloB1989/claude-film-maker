"""Shot 24, the board: the turn of the film. Tsuru has stepped down into the ferry; she settles, her pole upright in her
hand, and says "Get in." (L14) without looking round at him. Then she stops, and looks up: the rain is giving out.
The drops thin to nothing, the rings go off the water, and as the last of it falls she says "The rain has stopped."
(L15); the light begins to warm on her lifted face.

From the jetty's far end looking back along it: the boat moored at the right with her standing at its stern, facing
us; the jetty running away to the left to the hut and its lantern on the bank; Shinza small on his knees halfway along
it, where he went down. The camera breathes in toward her, and as she lifts her face it sinks a little so the sky
opens over her.

The rain's density, the water's rings, the sheen and the key's warmth are the look schedule's (data/look.json
"board"). RF_S7_CAST=none builds the shot without its cast.
"""
from __future__ import annotations

import math
import os

SHOT = {"scene": "board"}

LINES = {"get_in": (95.2, 95.85), "stopped": (97.2, 98.83)}    # L14, L15 (film s)
SETTLE = (94.6, 95.15, 0.07)      # film s: her weight coming down into the boat from this much higher
LOOK_UP = (96.15, 96.95, 30.0)    # film s: her face lifting to the sky, this many degrees
SMILE = (98.9, 99.7)              # film s: the faint smile after it
# the camera: from the jetty's end looking back along it (world m), easing in; lower as she looks up
CAM = ((9.3, -0.35, 1.32), (8.25, -0.05, 1.18))
SINK = 0.16                       # how much lower it ends after she looks up (m)
LENS, FSTOP = (34.0, 38.0), 2.8


def build(ctx):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mathutils import Vector

    from lib import toon3d
    from rf import ending as E
    from rf import set_world

    st = E.stage(ctx)
    E.headband("shinza-headband", E.band_material(st.look), st.world["near"], E.HEADBAND_AT[:2], E.HEADBAND_AT[2])
    stern = st.world["anchors"]["boat_stern"]
    actors = None
    n = (ctx.f1 - ctx.f0) / ctx.fps

    if os.environ.get("RF_S7_CAST", "vroid") != "none":
        from lib import vrm
        from rf import vroid_tsuru as T

        actors = E.cast(st, {"tsuru": dict(pole="hand"),
                             "shinza": dict(kasa=None, sword="broken", headband=False)})
        ts, sh = actors["tsuru"], actors["shinza"]
        # Shinza where he knelt, the blade across his lap
        E.place(sh, E.SHINZA_AT, E.SHINZA_FACING)
        E.kneel(sh)
        E.hold_blade(sh)
        for f in range(ctx.f0 - 1, ctx.f1 + 1, 4):
            breath = math.sin(2 * math.pi * 0.42 * ctx.time(f))
            sag = dict(E.SAG, spine=(E.SAG["spine"][0] + 1.5 * breath, 0.0, 0.0))
            E.kneel(sh, sag=sag, frame=f, legs=False)
        # Tsuru at the stern, riding the boat, facing its bow (toward us)
        ts["root"].parent = stern
        ts["root"].matrix_parent_inverse.identity()
        ts["root"].location = (0.0, 0.0, 0.0)
        ts["root"].rotation_euler = (0.0, 0.0, 0.0)
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
            face = ts["face"]()
            face = {k: v * (1.0 - 0.6 * smile) for k, v in face.items()}
            vrm.express(ch, {**face, "aa": 0.6 * speak, "happy": 0.25 * smile}, frame=f)
        # her key from above the river behind her, warming with the schedule's light; his from beyond him
        toon3d.aim(ts["key"], (0.6, 0.9, 1.0))
        toon3d.aim(sh["key"], (0.4, 1.0, 0.7))

    def tsuru_face():
        return set_world.anchor(st.world, "boat_stern") + Vector((0.0, 0.0, 1.3))

    def setup(t):
        k = E.ease(t / n)
        tt = ctx.time(ctx.f0) + t
        sink = SINK * E.ease((tt - LOOK_UP[0]) / (LOOK_UP[1] - LOOK_UP[0] + 1.2))
        at = E.lerp(CAM[0], CAM[1], k)
        dx, dy, dz = E.drift(t, 0.01, seed=5)
        at = (at[0] + dx, at[1] + dy, at[2] + dz - sink)
        face = tsuru_face()
        aim = (face.x - 0.2, face.y - 0.15, face.z - 0.25 + 0.12 * E.ease((tt - LOOK_UP[0]) / 2.0))
        lens = LENS[0] + (LENS[1] - LENS[0]) * k
        return at, aim, lens, FSTOP, tuple(face)

    E.camera(ctx, setup)

    def look(f, s):
        L = s.light
        return dict(rims=[((0.4, 1.0), L.rim, 0.3 + 0.2 * s.warm, 0.003, 0.9)], para_from=(0.5, 0.9), para_to=(0.5, 0.1))

    E.finish(ctx, st, look, actors, lambda f: LENS[0])
