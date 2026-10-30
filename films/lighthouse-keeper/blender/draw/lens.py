# 'You polish the great lens until it gleams...' The lantern room by day: the great Fresnel lens, the keeper polishing it.
DRAW = {"scene": "lens", "fps": 12}


def build(ctx):
    import math
    import random
    import _sets as S
    from lib.toon import Person, D2R
    t = ctx.toon
    from mathutils import Vector
    rnd = random.Random(8)
    S.sky(t, "sky")
    # beyond the glass: the sea and a few clouds, flat
    t.group("far", 40.0)
    HZ = 2.6
    t.card("sea", t.rect(300, 40, 0, HZ - 20), 0.0, "sea", c=t.plain, loc=(0, 40, 0))
    for i in range(40):
        x, z = rnd.uniform(-45, 45), rnd.uniform(HZ - 12, HZ - 0.4)
        L = rnd.uniform(1.0, 2.2) * (1 + (HZ - z) / 8)
        t.line(f"wave{i}", [(x + L * k / 6, 39.5, z + 0.07 * math.sin(k * math.pi / 3)) for k in range(7)], width=0.05, col="sea_line", c=t.plain)
    S.cloud(t, "cloud1", (-14, 39, 7.5), w=11, h=2.4, c=t.plain)
    S.cloud(t, "cloud2", (13, 39, 9.5), w=9, h=2.0, c=t.plain, seed=4)
    S.gulls(t, (7, 30, 6.0), n=2, span=2.0, size=0.5, seed=3)
    # the glazing: iron mullions, a knee wall, a beam
    t.group("room", 12.0)
    for i, x in enumerate([-7.2, -5.4, -3.6, -1.8, 0.0, 1.8, 3.6, 5.4, 7.2]):
        t.box(f"mull{i}", (x, 3.5, 3.0), (0.13, 0.13, 9), "iron")
    t.box("kneewall", (0, 3.5, 0.5), (18, 0.2, 1.05), "tower")
    t.box("rail", (0, 3.4, 1.1), (18, 0.25, 0.14), "iron")
    t.box("transom", (0, 3.4, 4.7), (18, 0.18, 0.12), "iron")
    t.box("beam", (0, 3.0, 5.7), (18, 0.4, 0.5), "iron")
    for sx in (-1, 1):
        t.box(f"post{sx}", (sx * 4.5, 0.3, 3.0), (0.3, 0.3, 9), "iron")
    t.box("floor", (0, 0.5, -0.05), (24, 8, 0.2), "stone_dark")
    # the Fresnel lens: a pedestal and a beehive of stacked glass rings
    t.group("lens", 9.0)
    lx = 1.7
    t.cyl("ped", (lx, 0.3, 0.55), 1.0, 1.1, "iron", seg=48)
    t.cyl("ped band", (lx, 0.3, 1.12), 1.08, 0.1, "brass", seg=48)
    prof = [1.0, 1.08, 1.02, 1.06, 0.96, 0.98, 0.86, 0.86, 0.7]
    z = 1.2
    for j in range(len(prof) - 1):
        h = 0.4
        t.cyl(f"ring{j}", (lx, 0.3, z + h / 2), prof[j], h, "glass" if j % 2 == 0 else "#b3d6de", r2=prof[j + 1], seg=48)
        # the ring line, the front half of the joint
        zr = z + h
        R = prof[j + 1] + 0.012
        t.line(f"joint{j}", [(lx + R * math.sin(a), 0.3 - R * math.cos(a), zr) for a in [-math.pi / 2 + math.pi * i / 16 for i in range(17)]],
               width=0.012, poly=True, taper=False)
        z += h
    t.cyl("top ring", (lx, 0.3, z + 0.05), 0.74, 0.1, "brass", r2=0.6, seg=48)
    t.blob("top dome", (lx, 0.3, z + 0.1), (0.5, 0.5, 0.36), "brass", shape=t.flat_bottom(0.0))
    # shine marks on the glass
    for dz, off in ((0.7, -0.55), (1.5, -0.45), (2.3, -0.5)):
        t.line(f"shine{dz}", [(lx + off, 0.3 - 0.8, 1.5 + dz), (lx + off + 0.05, 0.3 - 0.8, 1.5 + dz + 0.3)], width=0.014, col="#ffffff", c=t.plain, poly=True, taper=False)
    # the keeper, medium shot, polishing
    t.group("people")
    KX, KY, KR = -0.2, -0.02, 70
    k = Person(t, t.cast["keeper"], "keeper", loc=(KX, KY, 0.85), rot=(0, 0, D2R(KR)), hands=("flat", "rest"), expression="content")
    k.head_pose(turn=0, tilt=0, nod=3)
    k.blink(ctx.frame(3.0))

    def person(v, point=True):
        """A world point (or direction) in the keeper's own space."""
        c, s_ = math.cos(D2R(-KR)), math.sin(D2R(-KR))
        x, y, z = (v[0] - KX, v[1] - KY, v[2] - 0.85) if point else v
        return (c * x - s_ * y, s_ * x + c * y, z)
    # the flat of his hand on the glass at chest height, a cloth under it, rubbing round in circles; the hand turned a
    # little towards us (a drawn cheat: the bunched cloth fills the gap) so we see its back, not its edge
    cloth = t.blob("cloth", (0, 0, 0), (0.27, 0.07, 0.32), "cloth", parent=None, n=2.6, shape=t.lumpy(0.18, seed=4))
    k.hold(-1, cloth, (0.0, -0.06, 0.03), at="palm")
    k.arm(1, (0.58, 0.04, 0.55), (0.6, -0.1, -0.05))
    m = Vector((0.9, 0.44, 0.0)).normalized()             # the glass's inward normal there
    n = Vector((0.62, 0.78, 0.0)).normalized()             # the palm's
    C = Vector((lx, 0.3, 2.02)) - m * (1.03 + 0.09)        # the glass is 1.03 out there; the cloth between
    t1, t2 = Vector((-n.y, n.x, 0)), Vector((0, 0, 1))
    r = 0.1
    for f in range(1, ctx.count + 1):
        ph = 2 * math.pi * (f - 1) / 12.0       # one loop a second at 12 fps
        w = C + (t1 * math.cos(ph) + t2 * math.sin(ph)) * r
        k.reach(-1, person(w), palm=person(n, False), fingers=person(Vector((0.1 * math.cos(ph), 0, 1)) - n * 0.15, False),
                at="palm", frame=f)
    t.camera("cam", (0, -9, 2.6), (-0.1, 0, 3.0), lens=34)
