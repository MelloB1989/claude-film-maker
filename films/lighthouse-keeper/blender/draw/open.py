# 'It's 1891. You are a lighthouse keeper.' Dusk: the lighthouse on its rock, the lamp just lit, gulls, a low sun.
DRAW = {"scene": "open", "fps": 0}


def build(ctx):
    import _sets as S
    t = ctx.toon
    pal = S.DUSK
    S.sky(t, "dusk_sky", "dusk_sky2", horizon=0.0)
    t.group("far")
    S.sun(t, (-30, 300, 2.0), r=10, col="sun")
    S.cloud(t, "cloud1", (-70, 250, 46), w=46, h=10, col="dusk_cloud", seed=3)
    S.cloud(t, "cloud2", (60, 250, 70), w=34, h=8, col="dusk_cloud", seed=5)
    S.sea(t, pal, marks=70, seed=2, near=-25, far=110, spread=45)
    t.group("island")
    S.island(t, pal, loc=(4.5, 8, 0), r=6.5, h=1.6, seed=4)
    lh = S.lighthouse(t, pal, loc=(5.5, 8.5, 1.7), h=7.0)
    S.cottage(t, pal, loc=(1.6, 7.0, 1.55), rot=-12)
    t.group("birds")
    S.gulls(t, (-5.5, -4, 8.2), n=3, span=3.0, size=0.6, seed=7)
    t.camera("cam", (0, -26, 4.2), (1.2, 8, 5.2), lens=42)
