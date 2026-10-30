# 'Your whole world is one rock, one tower, and one light that must never go out.' Day, from high above: the island
# small in an endless sea.
DRAW = {"scene": "rock", "fps": 0}


def build(ctx):
    import _sets as S
    t = ctx.toon
    pal = S.DAY
    S.sky(t, "sky", "#e3f4f6", horizon=0.0, far=700, height=60)
    t.group("far")
    S.cloud(t, "cloud1", (-120, 640, 70), w=90, h=20, col="cloud", seed=11)
    S.cloud(t, "cloud2", (150, 640, 95), w=70, h=16, col="cloud", seed=12)
    S.sea(t, pal, marks=90, seed=5, near=-25, far=260, spread=110, width=0.06)
    S.sea_marks(t, pal, marks=40, seed=6, near=-22, far=40, spread=30, width=0.05)
    t.group("island")
    S.island(t, pal, loc=(0, 0, 0), r=6.5, h=1.6, seed=4)
    S.lighthouse(t, pal, loc=(1.0, 0.5, 1.7), h=7.0)
    S.cottage(t, pal, loc=(-2.9, -1.0, 1.55), rot=-12)
    t.group("birds")
    S.gulls(t, (-10, -14, 14), n=3, span=3.5, size=0.8, seed=21)
    t.camera("cam", (0, -54, 25), (0, 12, 2.0), lens=46)
