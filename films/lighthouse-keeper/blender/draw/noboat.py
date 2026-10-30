# 'If the sea is rough, it doesn't come at all.' The keeper on the gallery with a telescope over an empty rough sea.
import math
import random

DRAW = {"scene": "noboat", "fps": 0}


def build(ctx):
    import _sets as S
    from lib.toon import Person, D2R
    t = ctx.toon
    pal = {**S.DAY, "sea": "storm_sea", "line": "storm_line"}
    G = 12.0                                     # the gallery floor's height above the sea
    S.sky(t, "#8f9aa9", "sky", horizon=0.0, bands=5, height=60)
    t.group("far")
    S.cloud(t, "c1", (-60, 250, 40), w=60, h=12, col="#a9b2bf", seed=2)
    S.cloud(t, "c2", (55, 250, 55), w=50, h=10, col="#9ba5b3", seed=6)
    S.cloud(t, "c3", (0, 250, 25), w=34, h=6, col="#b4bcc8", seed=11)
    S.sea(t, pal, marks=110, seed=5, near=-4, far=110, spread=50, width=0.09)
    # white caps: short scalloped strokes on the water
    rnd = random.Random(8)
    for i in range(70):
        y = rnd.uniform(-2, 90) ** 1.0
        x = rnd.uniform(-1, 1) * (12 + y * 0.9)
        L = 0.9 + y * 0.05
        pts = [(x + L * k / 6, y, 0.03 + 0.05 * math.sin(k * math.pi / 3) * (1 + y / 30)) for k in range(7)]
        t.line(f"cap{i}", pts, width=0.06 * (1 + y / 22), col="foam", taper=True)
    # the gallery
    t.group("gallery", distance=7)
    t.box("floor", (0, 0.5, G - 0.15), (14, 5, 0.3), "iron")
    t.box("rail top", (0, 1.9, G + 1.05), (14, 0.09, 0.09), "iron")
    t.box("rail mid", (0, 1.9, G + 0.55), (14, 0.05, 0.05), "iron")
    for i in range(15):
        t.box(f"post{i}", (-6.5 + i * 13 / 14, 1.9, G + 0.5), (0.06, 0.06, 1.0), "iron")
    t.group("people", distance=9.6)
    k = Person(t, {**t.cast["keeper"], "skin": "skin"}, "keeper", loc=(-0.4, 0.4, G), rot=(0, 0, D2R(62)), hands=("grip", "grip"))
    k.expression("tired")
    k.head_pose(turn=-8, nod=-4)
    tele = t.empty("tele", (0, 0, 0), parent=k.root)
    tele.location = (0.02, -0.28, 1.93)
    tele.rotation_euler = (D2R(86), 0, 0)
    t.cyl("tele1", (0, 0, 0.5), 0.07, 1.0, "brass", parent=tele, r2=0.075)
    t.cyl("tele2", (0, 0, 1.15), 0.09, 0.5, "brass", parent=tele, r2=0.10)
    t.cyl("tele eye", (0, 0, -0.04), 0.05, 0.08, "capband", parent=tele)
    t.cyl("tele lens", (0, 0, 1.42), 0.115, 0.06, "capband", parent=tele)
    # both hands round the tube from either side, their fingers curled over the top: the far one by the eyepiece
    ax = (0, -math.sin(D2R(86)), math.cos(D2R(86)))

    def on_tube(s_):
        return tuple(tele.location[i] + ax[i] * s_ for i in range(3))
    short = k.reach(1, on_tube(0.2), palm=(-1, 0, 0.15), fingers=(0, 0.1, 1))
    short += k.reach(-1, on_tube(0.54), palm=(1, 0, 0.15), fingers=(0, 0.1, 1))
    if short > 1e-3:
        print(f"noboat: the hands fall {short:.3f} short of the telescope")
    t.camera("cam", (2.0, -9.0, G + 2.9), (0.8, 4, G + 1.9), lens=50)
