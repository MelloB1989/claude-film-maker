# 'By morning, the sea is calm. The ship is gone. Safe.' Sunrise over a flat sea; the schooner small on the horizon,
# sailing away; the lighthouse on its rock, its lamp out.
DRAW = {"scene": "dawn", "fps": 0}


def build(ctx):
    import _sets as S
    t = ctx.toon
    pal = S.DAWN
    S.sky(t, "dawn_sky2", "dawn_sky", horizon=0.0, far=400, height=46, bands=4)
    t.group("far")
    S.sun(t, (40, 300, 3.0), r=11, col="dawn_sun")
    S.cloud(t, "cloud1", (-60, 280, 40), w=52, h=11, col="#fff3e6", seed=61)
    S.cloud(t, "cloud2", (85, 280, 56), w=38, h=9, col="#fff3e6", seed=62)
    S.schooner(t, "hull", "sail", loc=(26, 150, -0.2), scale=0.9, heel=0, name="ship")
    S.sea(t, pal, marks=60, seed=14, near=-25, far=110, spread=45, width=0.03)
    for i in range(7):   # the sun's glitter path on the water
        y = 20 + i * 14
        x = 40 * (y + 26) / (300 + 26) - 0.5
        t.line(f"glint{i}", [(x - 1.2 - i * 0.6, y, 0.03), (x + 1.2 + i * 0.6, y, 0.03)], width=0.06 + 0.02 * i, col="#fff6dc", taper=True)
    t.group("island")
    S.island(t, pal, loc=(-9.5, 10, 0), r=6.5, h=1.6, seed=4)
    S.lighthouse(t, pal, loc=(-8.5, 10.5, 1.7), h=7.0)
    S.cottage(t, pal, loc=(-12.4, 9.0, 1.55), rot=-12)
    t.group("birds")
    S.gulls(t, (6, -4, 8.5), n=2, span=2.5, size=0.55, seed=23)
    t.camera("cam", (0, -26, 3.6), (0.5, 8, 4.4), lens=38)
