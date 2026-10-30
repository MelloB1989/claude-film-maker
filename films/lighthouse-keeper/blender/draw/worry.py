# 'You keep the light turning. And you wait.' Night, lamplit close-up: the keeper at a rain-streaked window, storm outside.
DRAW = {"scene": "worry", "fps": 6}


def build(ctx):
    import math
    import random
    import _sets as S
    from lib.toon import Person, D2R
    t = ctx.toon
    t.world("storm_sky")
    # the storm outside: sea and clouds on flat cards far behind the window
    t.group("outside", 14.0)
    t.card("sea", t.rect(80, 12, 0, -4.4), 0.0, "storm_sea", c=t.plain, loc=(0, 14, 0))
    for i, (x, z, w) in enumerate([(-6, 5.0, 9), (4, 6.0, 11), (11, 4.3, 7)]):
        S.cloud(t, f"cloud{i}", (x, 13.8, z - 1.2), w=w, h=2.2, col="storm_cloud", seed=i + 3, c=t.plain)
    rnd = random.Random(5)
    for i in range(22):
        x, z = rnd.uniform(-9, 9), rnd.uniform(-1.6, 1.7) 
        L = rnd.uniform(0.6, 1.1)
        t.line(f"wave{i}", [(x + L * k / 6, 13.5, z + 0.05 * math.sin(k * math.pi / 2)) for k in range(7)],
               width=0.03, col="storm_line", c=t.plain)
    # the room: a warm wall with the window cut out of it (four slabs), the frame, the glass
    t.group("room")
    X0, X1, Z0, Z1, Y = 0.55, 3.6, 0.7, 3.55, 1.5
    wall = "wall_warm"
    t.box("wl", ((X0 - 8) / 1, Y + 0.1, 2), (16 - 0.0, 0.2, 14), wall) if False else None
    t.box("wallL", ((X0 - 9) / 1, Y, 2), (18, 0.2, 14), wall)
    t.box("wallR", ((X1 + 9), Y, 2), (18, 0.2, 14), wall)
    t.box("wallB", ((X0 + X1) / 2, Y, (Z0 - 7)), (X1 - X0 + 0.02, 0.2, 14), wall)
    t.box("wallT", ((X0 + X1) / 2, Y, (Z1 + 7)), (X1 - X0 + 0.02, 0.2, 14), wall)
    fw = 0.16
    cx, cz = (X0 + X1) / 2, (Z0 + Z1) / 2
    t.box("sill", (cx, Y - 0.12, Z0 - 0.04), (X1 - X0 + 0.5, 0.45, 0.12), "wood")
    t.box("fL", (X0 + fw / 2, Y - 0.1, cz), (fw, 0.22, Z1 - Z0), "wood_dark")
    t.box("fR", (X1 - fw / 2, Y - 0.1, cz), (fw, 0.22, Z1 - Z0), "wood_dark")
    t.box("fT", (cx, Y - 0.1, Z1 - fw / 2), (X1 - X0, 0.22, fw), "wood_dark")
    t.box("fB", (cx, Y - 0.1, Z0 + fw / 2), (X1 - X0, 0.22, fw), "wood_dark")
    t.box("mullV", (cx, Y - 0.1, cz), (0.1, 0.2, Z1 - Z0), "wood_dark")
    t.box("mullH", (cx, Y - 0.1, cz + 0.2), (X1 - X0, 0.2, 0.1), "wood_dark")
    t.group("glass")
    t.card("pane", t.rect(X1 - X0, Z1 - Z0, cx, cz), 0.0, "glass", c=t.plain, loc=(0, Y - 0.25, 0), alpha=0.14)
    # rain on the glass: slanted streaks, a few long runs
    for i in range(24):
        x, z = rnd.uniform(X0 + 0.15, X1 - 0.15), rnd.uniform(Z0 + 0.3, Z1 - 0.1)
        L = rnd.uniform(0.25, 0.7)
        t.line(f"run{i}", [(x, Y - 0.27, z), (x + 0.03 * L, Y - 0.27, z - L)], width=0.008, col="rain", c=t.plain, poly=True, taper=False)
    S.rain(t, ctx.count, area=(X0 + 0.1, X1 - 0.1, Y - 0.27, Y - 0.27, Z0 + 0.2, Z1 - 0.1), n=30, seed=3, length=0.4, slant=0.18, width=0.008)
    # lamp glow on the left wall
    t.group("glows")
    t.card("glow", t.ring(0, 0, 2.4, 2.0, 48), 0.0, "glow", c=t.plain, loc=(-1.7, 1.4, 1.9), alpha=0.28)
    # the keeper, lamplit, turned a little towards the window
    t.group("people")
    spec = {**t.cast["keeper"], "skin": "skin_warm", "coat": "coat_warm", "collar": "coat_warm",
            "beard": {"color": "beard_warm"}, "moustache": {"color": "beard_warm"}, "hair": {"style": "sides", "color": "beard_warm"}}
    k = Person(t, spec, "keeper", loc=(-0.25, 0, 0.0), hands=("point", "rest"), expression="worried")
    k.head_pose(turn=-22, tilt=0, nod=-3)
    # thinking: the right hand up, its index finger along the cheek, the back of the hand to us
    k.arm(-1, (-0.62, -0.45, 0.55), (-0.27, -0.84, 1.02), palm=(0.4, 0.9, 0.1), fingers=(0.2, 0.12, 1.0))
    k.arm(1, (0.58, 0.02, 0.5), (0.62, -0.06, -0.1))
    # two worried taps of the finger on the chin
    tap = {"base": "point", "fingers": [(2, 16, 22, 8), (-2, 86, 100, 56), (-4, 90, 100, 56), (-6, 94, 100, 56)]}
    k.hand(-1, "point", ctx.frame(0))
    for t0 in (0.85, 2.0):
        k.hand(-1, tap, ctx.frame(t0))
        k.hand(-1, "point", ctx.frame(t0 + 0.17))
    k.eyes("open", ctx.frame(0))
    k.blink(ctx.frame(1.6))
    k.look(0.05, 0.0, ctx.frame(0))
    t.camera("cam", (0, -7.0, 2.0), (0.75, 0, 1.55), lens=48)
