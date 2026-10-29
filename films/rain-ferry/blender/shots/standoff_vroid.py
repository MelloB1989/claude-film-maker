"""The standoff with the 3D cast (the film's standoff; shots/standoff.py keeps the drawn cast's version): the wide
two-shot of Shinza and Tsuru ten paces apart on the jetty in the downpour, the river and its ridges fading into the
mist behind them, the hut's red lantern swinging at the left, the covered boat at the right. The music has gone out;
the letterbox slides in over the first 1.4 s (the engine's: compose for the 2.39 band). The camera creeps in low
over the water past two old mooring stakes, out of focus in the foreground. He breathes hard behind his low guard,
settling his weight; she is still, breathing slow. A gust (the mix's at +1.6 s) throws the rain, his hair and
headband tails, her cape's straw and both hems; lightning whitens everything at +2.1 s (the thunder follows at
+2.2 s); after it she turns her head to him a little.

    blender -b -P blender/render.py -- --film rain-ferry --shot standoff_vroid --mode look --engine eevee \\
        --frames 1431,1478,1500,1538 --res 960x540
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

SHOT = {"scene": "standoff"}

# the camera, from the duel's middle (rf/duel.py MID): low over the water on the -y side, turned a little toward the
# land so the hut's lantern hangs behind him at the left of the frame, creeping in
CAM_FROM, CAM_TO = (1.3, -7.8, 0.75), (1.12, -6.4, 0.88)
AIM_FROM, AIM_TO = (-1.0, 1.5, 1.2), (-0.95, 1.5, 1.1)
LENS = (24.0, 25.5)
FSTOP = 5.6
GUST = (1.6, 1.5, 1.4)          # s into the shot, length, strength: the mix's wind_gust
HER_LOOK = (2.5, 3.4, 4.0)      # s: her head turns to him from, to (degrees)
# two old mooring stakes standing in the water near the lens, framing the shot (x, y, top, radius)
STAKES = [(-1.6, -5.4, 0.62, 0.075), (3.3, -5.7, 0.34, 0.065)]        # from MID
BAND = (0.128, 0.872)           # the 2.39 letterbox's band (frame heights)
# the compositing's setup on the look schedule's base (data/look.json): more of the rain's air between the lens and
# small figures, the para darkening the deck, the sky's rim from above and the lantern's on his back
LOOK = dict(haze_amount=0.05, para_amount=0.3, wrap_width=0.004, para_from=(0.5, 0.62), para_to=(0.5, 0.25), rims=[((0.2, 1.0), (0.6, 0.68, 0.85), 0.2, 0.002, 0.8),
                                                             ((-1.0, 0.2), (1.0, 0.5, 0.18), 0.12, 0.0018, 0.8)])
KEYS = {"shinza": (1.0, -0.3, 0.8), "tsuru": (-1.0, -0.3, 0.8)}
STRIKE = 2.1                    # s: the look schedule's lightning (the thunder at +2.2 s)
BOLT = ((16.0, 70.0, 34.0), (21.0, 78.0, -1.0))     # the fork: from the sky to the far water, from MID (world m)


def build(ctx):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, satsuei, shapes
    from rf import duel, sets
    from rf import duel_motion as dm

    st = duel.stage(ctx)
    mid = np.array((duel.MID[0], duel.MID[1], 0.0))
    # the camera (lib/cinema.py): one setup, creeping in and down a little, breathing; jolted by the thunderclap
    rig = cinema.film(ctx, [cinema.Setup(
        "wide", 0.0, cinema.line(np.add(CAM_FROM, mid), np.add(CAM_TO, mid), np.add(AIM_FROM, mid), np.add(AIM_TO, mid)),
        lens=LENS, fstop=FSTOP, focus=tuple(mid + (0.0, 0.0, 1.0)), ease="sine",
        shake=cinema.Shake(breath=0.06, hits=((STRIKE + 0.12, 0.25),)))])
    # the weather (lib/weather.py): the schedule's downpour and its lightning (+2.1 s), the fork far out over the river
    duel.weather(st, rig, bolt=(tuple(mid + BOLT[0]), tuple(mid + BOLT[1])))
    post = st.crossing["materials"]["post"]
    for k, (x, y, top, r) in enumerate(STAKES):
        x, y = x + mid[0], y + mid[1]
        shapes.cylinder(f"stake{k}", (x, y, sets.WATER_Z - 1.0), (x, y, top), r, material=post, coll=st.crossing["near"],
                        n=10)
        shapes.cylinder(f"stake{k}-rope", (x, y, top - 0.14), (x, y, top - 0.08), r + 0.012,
                        material=st.crossing["materials"]["rope"], coll=st.crossing["near"], n=10)

    gust = [GUST]
    sh, ts = st.bodies["shinza"], st.bodies["tsuru"]
    comp = satsuei.setup(ctx.scene, st.cast)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        g = dm.gusts(t, gust)

        # Shinza: hard breaths behind his guard, his weight settling forward and down through the shot, the head
        # dropping to a glare; the gust throws his hair and his hakama
        settle = dm.ease(t / 4.0)
        sh.key(f, duel.add(duel.breathing(t, 0.45, 1.8), {"spine": (1.5 * settle, 0.0, 0.0), "head": (2.5 * settle, 0.0, 0.0)}),
               hips=(0.0, -0.02 * settle, -0.015 * settle),
               chains=sh.sway(t, amount=9.0, cloth=4.0, toward=(0.0, -1.0, 0.0), seed=1, at=gust))
        # Tsuru: still; a slow breath; after the strike her head turns to him a little
        look_k = dm.span(t, HER_LOOK[0], HER_LOOK[1])
        ts.key(f, duel.add(duel.breathing(t, 0.2, 0.7, 0.3), {"head": (0.0, 0.0, -HER_LOOK[2] * look_k)}),
               chains=ts.sway(t, amount=5.0, cloth=3.0, toward=(0.0, 1.0, 0.0), seed=7, at=gust))
        duel.key_lines(st, f, *duel.lens_at(rig, f))
        duel.key_light(st, f, KEYS)
        duel.swing_lantern(st, f, t, g)
        comp.key(f, duel.look(st, f, LOOK))
    comp.hold()
