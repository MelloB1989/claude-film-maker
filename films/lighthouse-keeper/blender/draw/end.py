# 'you light the lamp.' Night, calm: the lighthouse under the stars, its beam turning slowly over the sea; the title
# comes up over it in the engine.
DRAW = {"scene": "end", "fps": 12}


def build(ctx):
    import _sets as S
    from lib.toon import D2R
    t = ctx.toon
    pal = S.NIGHT
    n = ctx.count
    S.sky(t, "night_sky", "#2b3a5c", horizon=0.0, far=400, height=40, bands=3)
    S.stars(t, n=90, y=380, spread=(-260, 260), zr=(30, 200), seed=9)
    t.group("far")
    t.card("moon", t.ring(0, 0, 9, 9, 64), 0.05, "moon", loc=(-70, 360, 120))
    t.card("moonbite", t.ring(0, 0, 8.5, 8.5, 64), 0.05, "night_sky", c=t.plain, loc=(-65.5, 359, 123))
    S.sea(t, pal, marks=70, seed=16, near=-25, far=110, spread=45, width=0.03)
    t.group("island")
    S.island(t, pal, loc=(4.5, 8, 0), r=6.5, h=1.6, seed=4)
    lh = S.lighthouse(t, pal, loc=(5.5, 8.5, 1.7), h=7.0)
    S.cottage(t, pal, loc=(1.6, 7.0, 1.55), rot=-12)
    t.blob("glow", tuple(lh["lamp"] + Vector((0, -1.2, 0))), (1.7, 0.05, 1.7), "glow", c=t.plain, alpha=0.4)
    beams = [S.beam(t, lh["lamp"], yaw=y, length=90, spread=6, alpha=0.34, name=f"beam{i}") for i, y in enumerate((-100, 80))]
    for b, y0 in zip(beams, (-100, 80)):
        for f, y in ((1, y0), (n, y0 + 55)):
            b.rotation_euler.z = D2R(y)
            b.keyframe_insert("rotation_euler", index=2, frame=f)
    t.camera("cam", (0, -28, 3.6), (1.8, 8, 6.4), lens=40)


from mathutils import Vector  # noqa: E402
