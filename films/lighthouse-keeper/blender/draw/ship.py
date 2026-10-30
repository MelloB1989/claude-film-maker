# 'Then you see it. A ship, far too close to the rocks.' A schooner heeling in the storm, jagged rocks in front of it,
# lightning, the beam overhead.
DRAW = {"scene": "ship", "fps": 0}


def build(ctx):
    import math
    import random
    import _sets as S
    from lib.toon import D2R
    t = ctx.toon
    pal = S.STORM
    S.sky(t, "night_sky", "storm_sky", horizon=0.0, far=400, height=40, bands=3)
    t.group("far")
    for i, (x, z, w) in enumerate([(-80, 46, 90), (30, 60, 100), (110, 38, 70)]):
        S.cloud(t, f"cloud{i}", (x, 380 - i, z), w=w, h=18, col="storm_cloud", seed=50 + i)
    bolt = [(0, 0), (3, -9), (-1, -10), (4, -22), (-3, -9), (1, -8), (-2, 0)]
    t.card("bolt", [(x * 3.2, z * 3.2) for x, z in bolt], 0.0, "lightning", loc=(-70, 300, 104))
    S.sea(t, pal, marks=90, seed=12, near=-15, far=140, spread=50, width=0.045)
    S.beam(t, (26, 30, 11), yaw=-97, length=70, spread=6, alpha=0.32, name="beam")
    t.group("ship")
    S.schooner(t, "hull_night", "sail_night", loc=(-3.0, 12, -0.2), scale=0.9, heel=-13, name="ship")
    t.group("waves")
    rnd = random.Random(8)
    for i in range(8):
        x, y = rnd.uniform(-16, 14), rnd.uniform(2, 16)
        S.swell(t, f"wave{i}", (x, y, -0.3 + rnd.uniform(0, 0.5)), w=rnd.uniform(2.5, 4.0), seed=i)
    t.group("rocks")
    for i, (x, y, h, w) in enumerate([(5.5, 1.0, 3.6, 1.5), (7.6, 2.2, 2.4, 1.2), (3.7, 2.6, 1.8, 1.0), (9.5, 0.2, 1.5, 1.3)]):
        t.blob(f"crag{i}", (x, y, 0.2), (w, w * 0.8, h), "rock_night", rot=(D2R(180), 0, D2R(20 * i)),
               shape=lambda v, s=i: tuple(Vector(t.teardrop(1.2)(v)) * (1 + 0.12 * math.sin(5 * v.x + s))))
    S.rain(t, 1, area=(-20, 20, -8, 30, 0, 16), n=150, seed=17, col="rain", slant=0.3, length=1.3, width=0.02)
    t.camera("cam", (0, -20, 3.0), (-0.5, 10, 3.6), lens=38, roll=3)


from mathutils import Vector  # noqa: E402
