# 'A hundred and twelve steps. Every morning. Every night.' Inside the tower: a spiral stair round a column, the keeper
# climbing with a lantern. A tall still (the engine pans up through it).
DRAW = {"scene": "stairs", "fps": 0, "res": [2560, 3840]}


def build(ctx):
    import math
    import random
    import _a
    from lib.toon import Person, D2R
    t = ctx.toon
    WALL, WALL_D, MORTAR = "#a99f8c", "#968c7a", "#8a8070"
    t.world(WALL)
    rnd = random.Random(4)
    # the curved wall behind
    t.group("wall", 26.0)
    t.card("wall", t.rect(9, 30, 0, 5), 0.0, WALL, loc=(0, 4.2, 0))
    for sx in (-1, 1):
        t.card(f"wall edge{sx}", t.rect(1.3, 30, sx * 3.85, 5), 0.0, WALL_D, c=t.plain, loc=(0, 4.15, 0))
    for r in range(-4, 17):
        z = r * 0.9
        x = -4.0 + rnd.uniform(0, 0.8)
        while x < 4.0:
            L = rnd.uniform(0.9, 1.6)
            t.line(f"c{r}_{x:.1f}", [(x, 4.1, z), (min(x + L, 4.2), 4.1, z)], width=0.018, col=MORTAR, c=t.plain, poly=True, taper=False)
            x += L + rnd.uniform(0.15, 0.5)
    for i, (wz, wx) in enumerate([(1.0, -2.3), (7.2, 2.3), (13.0, -2.3)]):
        arch = [(-0.5, 0.0), (0.5, 0.0)] + t.ring(0, 1.0, 0.5, 0.5, 18, 0, math.pi)
        t.card(f"win{i}", arch, 0.1, "sky", loc=(wx, 4.0, wz))
        t.box(f"sill{i}", (wx, 3.95, wz - 0.07), (1.3, 0.3, 0.14), "stone")
    # the stair: wedge steps round a column
    t.group("stairs")
    R0, R1, RISE, N = 0.95, 3.1, 0.5, 12
    ia, ib = -10, 32
    for i in range(ia, ib):
        a = math.radians(-90 + (i - 13) * 360 / N)
        h = math.radians(180 / N) + 0.012
        pts = [(R0 * math.cos(a - h), R0 * math.sin(a - h)), (R1 * math.cos(a - h), R1 * math.sin(a - h)),
               (R1 * math.cos(a + h), R1 * math.sin(a + h)), (R0 * math.cos(a + h), R0 * math.sin(a + h))]
        pts = [(x, -y) for x, y in pts]
        t.card(f"step{i}", pts, 0.62, "stone" if i % 2 else "stone_dark", loc=(0, 0, i * RISE - 0.62), rot=(D2R(90), 0, 0))
    t.cyl("column", (0, 0, 7), R0 - 0.02, 40, "stone", seg=48)
    for r in range(-6, 24):
        t.line(f"col course{r}", [(-0.93 * math.sin(a), -0.93 * math.cos(a), r * 0.6 + 0.3) for a in [x * 0.15 for x in range(-10, 11)]],
               width=0.012, col=MORTAR, c=t.plain, poly=True, taper=False)
    # the keeper, a step up, lantern in the near hand
    t.group("people")
    i0 = 12
    a0 = math.radians(-90 + (i0 - 13) * 360 / N)
    a1 = math.radians(-90 + (i0 + 1 - 13) * 360 / N)
    r = 2.1
    p0 = (r * math.cos(a0), r * math.sin(a0))
    p1 = (r * math.cos(a1), r * math.sin(a1))
    mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    z0 = i0 * RISE
    spec = {**t.cast["keeper"], "legs": True}
    k = Person(t, spec, "keeper", loc=(mid[0], mid[1], z0), rot=(0, 0, D2R(62)), hands=("hook", "rest"), expression="content")
    k.head_pose(turn=0, tilt=0, nod=6)
    _a.ik_leg(k, -1, (-0.2, 0.45, 0.06))            # the near (right) leg trails on the lower step
    _a.ik_leg(k, 1, (0.2, -0.5, RISE + 0.06))        # the far leg is up on the next
    # the lantern carried by its handle, hooked in the near hand, held a little forward; it hangs from the grip
    k.reach(-1, (-0.5, -0.66, 1.42), palm=(1, 0, 0), fingers=(0, -0.6, -1))
    k.arm(1, (0.6, 0.12, 1.55), (0.64, 0.22, 1.0))
    pivot = t.empty("lantern pivot", (0, 0, 0))
    k.hold(-1, pivot, at="grip")
    lant = _a.lantern(t, "lantern", pivot, 1.3)
    lant.location = (0, 0, -0.09 * 1.3)          # the top of the handle's arc in the grip
    _a.hang(k, -1, pivot)
    t.update()
    lp = lant.matrix_world.translation
    t.group("glow")
    t.card("glow", t.ring(0, 0, 1.7, 1.7, 48), 0.0, "glow", c=t.plain, loc=(lp.x, lp.y + 1.2, lp.z - 0.4), alpha=0.22)
    t.card("glow2", t.ring(0, 0, 0.9, 0.9, 48), 0.0, "glow", c=t.plain, loc=(lp.x, lp.y + 1.1, lp.z - 0.4), alpha=0.3)
    t.camera("cam", (0, -24, 6.2), (0.0, 0, 6.2), lens=105)
