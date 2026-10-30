# 'Nobody will ever thank you...' Sunset: the keeper alone on the rocks with a mug of tea, small, seen from behind.
DRAW = {"scene": "alone", "fps": 0}


def build(ctx):
    import _sets as S
    from lib.toon import Person, D2R
    t = ctx.toon
    pal = S.DUSK
    S.sky(t, "dusk_sky", "dusk_sky2", horizon=0.0)
    t.group("far")
    S.sun(t, (34, 300, 3.0), r=11, col="sun")
    S.cloud(t, "cloud1", (-70, 250, 50), w=50, h=10, col="dusk_cloud", seed=3)
    S.cloud(t, "cloud2", (50, 250, 72), w=36, h=8, col="dusk_cloud", seed=5)
    S.cloud(t, "cloud3", (10, 250, 30), w=26, h=5, col="dusk_cloud", seed=8)
    S.sea(t, pal, marks=80, seed=3, near=-25, far=110, spread=45)
    t.group("lighthouse")
    S.island(t, pal, loc=(29, 40, 0), r=9, h=2.2, seed=4)
    S.lighthouse(t, pal, loc=(30, 40.5, 2.0), h=9.5)
    t.group("birds")
    S.gulls(t, (-12, -4, 14), n=3, span=5.0, size=0.9, seed=7)
    # the rocks the keeper sits on (near the camera)
    t.group("rocks", distance=14)
    t.blob("rock big", (5.0, -12.6, -0.6), (9.0, 5.2, 2.4), pal["rock"], shape=t.lumpy(0.12, seed=5), seg=64)
    t.blob("rock seat", (1.4, -14.4, 1.2), (1.1, 0.9, 0.62), pal["rock_dark"], shape=t.lumpy(0.1, seed=9), seg=48)
    t.blob("rock side", (-4.0, -13.0, 0.0), (2.4, 1.8, 1.3), pal["rock_dark"], shape=t.lumpy(0.2, seed=2), seg=48)
    t.group("people")
    S_ = 0.62
    spec = {**t.cast["keeper"], "legs": True, "skin": "skin_warm", "hand": {"detail": "mitten"}}
    k = Person(t, spec, "keeper", loc=(1.4, -14.4, 1.72 - 0.8 * S_), rot=(0, 0, D2R(158)), hands=("wrap", "table"), scale=S_)
    t.blob("backhair", (0, 0.2, k.HC + 0.0), (0.58, 0.4, 0.46), "beard", parent=k.head)
    k.expression("content")
    # a mug of tea in the near hand, the other on his knee
    k.reach(1, (0.24, -0.5, 1.02), palm=(0, 0, -1), fingers=(0, -1, -0.25), at="palm")
    k.leg(-1, (-0.2, -0.5, 0.95), (-0.2, -0.55, 0.45))
    k.leg(1, (0.2, -0.5, 0.95), (0.2, -0.55, 0.45))
    k.head_pose(turn=-8, tilt=0, nod=4)
    mug = t.cyl("mug", (0, 0, 0), 0.095, 0.2, "mug", parent=None)
    t.cyl("tea", (0, 0, 0.095), 0.08, 0.02, "tea", parent=mug)
    k.reach(-1, (-0.3, -0.62, 1.72), palm=(1, 0, 0), fingers=(0, -1, 0))
    k.hold(-1, mug, rot=(0, D2R(-90), 0))
    t.camera("cam", (0, -26, 4.2), (4, 8, 3.2), lens=42)
