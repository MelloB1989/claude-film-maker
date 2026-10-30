# 'Some nights, the storm is so loud you can't hear yourself think.' Night storm: heaving waves round the rock, rain,
# the beam sweeping through the dark.
DRAW = {"scene": "storm", "fps": 12}


def build(ctx):
    import math
    import random
    import _sets as S
    from lib.toon import D2R
    t = ctx.toon
    pal = S.STORM
    n = ctx.count
    S.sky(t, "night_sky", "storm_sky", horizon=0.0, far=400, height=40, bands=3)
    t.group("far")
    for i, (x, z, w) in enumerate([(-70, 40, 80), (40, 52, 90), (-10, 70, 110), (90, 30, 60)]):
        S.cloud(t, f"cloud{i}", (x, 380 - i, z), w=w, h=16, col="storm_cloud", seed=40 + i)
    S.sea(t, pal, marks=80, seed=9, near=-20, far=120, spread=50, width=0.04)
    t.group("island")
    S.island(t, pal, loc=(3.0, 8, 0), r=6.5, h=1.6, seed=4, foam=False)
    lh = S.lighthouse(t, pal, loc=(4.0, 8.5, 1.7), h=7.0)
    S.cottage(t, pal, loc=(0.1, 7.0, 1.55), rot=-12)
    t.blob("glow", tuple(lh["lamp"] + Vector((0, -1.2, 0))), (1.6, 0.05, 1.6), "glow", c=t.plain, alpha=0.35)
    beam = S.beam(t, lh["lamp"], yaw=-70, length=80, spread=7, alpha=0.38, name="beam")
    for f, yaw in ((1, -78), (n, -18)):
        beam.rotation_euler.z = D2R(yaw)
        beam.keyframe_insert("rotation_euler", index=2, frame=f)
    # heaving waves: dark swells with foam caps, bobbing out of step
    t.group("waves")
    rnd = random.Random(5)
    waves = []
    for i in range(9):
        x = rnd.uniform(-16, 18)
        y = rnd.uniform(-6, 5) + (6 if abs(x - 3) < 7 else 0)
        g = S.swell(t, f"wave{i}", (x, y, 0), w=rnd.uniform(2.5, 4.5), seed=i)
        waves.append((g, rnd.uniform(0, 2 * math.pi), rnd.uniform(0.45, 0.8)))
    for f in range(1, n + 1):
        tt = (f - 1) / ctx.fps
        for g, ph, amp in waves:
            g.location.z = -0.35 + amp * math.sin(2 * math.pi * tt / 2.2 + ph)
            g.keyframe_insert("location", index=2, frame=f)
    # spray bursting on the rock, in two beats
    for k, (f0, f1, x) in enumerate(((ctx.frame(0.6), ctx.frame(1.5), 0.8), (ctx.frame(2.6), ctx.frame(3.5), 6.4))):
        sp = S.splash(t, f"spray{k}", (x, 3.2, 1.0), size=2.2 - 0.4 * k, seed=k + 3)
        t.show(sp, on=[f0], off=[1, f1])
    S.rain(t, n, area=(-24, 24, -12, 30, 0, 18), n=170, seed=13, col="rain", slant=0.3, length=1.3, width=0.02)
    t.camera("cam", (0, -24, 3.6), (1.5, 8, 5.0), lens=40, roll=-4)


from mathutils import Vector  # noqa: E402
