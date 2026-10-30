# 'You wake at four, before the sun, because the lamp needs you.' Pre-dawn bedroom, the keeper in bed, eyes opening.
DRAW = {"scene": "wake", "fps": 6}


def build(ctx):
    import math
    import random
    from lib.toon import Hand, Person, D2R
    from mathutils import Vector
    t = ctx.toon
    t.world("wall_night")
    t.group("room")
    t.card("wall", t.rect(40, 14, 0, 3), 0.05, "wall_night", loc=(0, 2.6, 0))
    t.box("floor", (0, 0.5, -0.45), (40, 6, 0.9), "wood_dark")
    # window: frame, night sky, stars, crescent moon
    wx, wz, ww, wh = 0.5, 3.1, 1.4, 1.1
    t.box("wframe", (wx, 2.45, wz), (ww + 0.24, 0.12, wh + 0.24), "wood_dark")
    t.card("sky", t.rect(ww, wh, wx, wz), 0.0, "night_sky", c=t.plain, loc=(0, 2.37, 0))
    rnd = random.Random(2)
    for i, (dx, dz, s) in enumerate([(-0.55, 0.45, 0.07), (0.1, 0.5, 0.05), (0.5, 0.2, 0.07), (-0.2, -0.1, 0.05), (0.2, -0.45, 0.06), (-0.6, -0.4, 0.05)]):
        pts = [((s if j % 2 == 0 else s * 0.35) * math.cos(math.pi * j / 4), (s if j % 2 == 0 else s * 0.35) * math.sin(math.pi * j / 4)) for j in range(8)]
        t.card(f"star{i}", pts, 0.0, "star", c=t.plain, loc=(wx + dx, 2.35, wz + dz))
    R = 0.24
    outer = t.ring(0, 0, R, R, 30, math.radians(70), math.radians(290))
    inner = t.ring(0.11, 0.03, R * 0.85, R * 0.85, 30, math.radians(290), math.radians(70) + 0)  # placeholder, replaced below
    a0, a1 = math.radians(60), math.radians(300)
    outer = [(R * math.cos(a0 + (a1 - a0) * i / 24), R * math.sin(a0 + (a1 - a0) * i / 24)) for i in range(25)]
    inner = [(0.12 + 0.85 * R * math.cos(a1 - (a1 - a0) * i / 24 + 0.0), 0.0 + 0.85 * R * math.sin(a1 - (a1 - a0) * i / 24)) for i in range(25)]
    # crescent = the disc minus a shifted disc: the outer arc, then back along the shifted inner arc
    cres = [(R * math.cos(math.radians(a)), R * math.sin(math.radians(a))) for a in range(80, 281, 8)]
    cres += [(0.13 + 0.78 * R * math.cos(math.radians(a)), 0.78 * R * math.sin(math.radians(a))) for a in range(260, 99, -8)]
    t.card("moon", cres, 0.0, "moon", c=t.plain, loc=(wx - 0.3, 2.34, wz + 0.2))
    t.box("wmull", (wx, 2.4, wz), (0.07, 0.1, wh), "wood_dark")
    t.box("wsill", (wx, 2.3, wz - wh / 2 - 0.15), (ww + 0.5, 0.3, 0.1), "wood_dark")
    # bed
    t.group("bed")
    t.box("bframe", (0.9, 0.3, 0.4), (8.4, 2.1, 0.5), "wood_dark")
    t.box("mattress", (0.9, 0.3, 0.85), (8.0, 1.9, 0.4), "sheet_night")
    t.box("headboard", (-3.3, 0.3, 1.5), (0.3, 2.1, 2.6), "wood_dark")
    t.blob("pillow", (-1.7, 0.0, 1.3), (1.05, 0.85, 0.4), "pillow_night", n=3.0)
    t.group("people")
    spec = {**t.cast["keeper"], "skin": "#cdb4bf", "coat": "coat_night", "collar": "coat_night", "cap": None,
            "beard": {"color": "#e6e8f4"}, "moustache": {"color": "#e6e8f4"},
            "hair": {"style": "sides", "color": "#e6e8f4"}}
    hx = -1.7
    k = Person(t, spec, "keeper", loc=(hx + 1.57, 0, 1.45), rot=(0, D2R(-90), 0), hands=("rest", "rest"), expression="tired")
    k.head_pose(18, 70, 0)
    import _a
    _a.nightcap(t, k, flop=-1)
    k.eyes("closed", ctx.frame(0))
    k.eyes("open", ctx.frame(0.5))
    k.blink(ctx.frame(2.6))
    for o in k.root.children_recursive:      # his arms are under the quilt
        if any(w in o.name for w in ("upper", "fore", "elbowball", "wrist", "hand")):
            o.hide_render = True
    t.group("quilt")
    t.blob("quilt", (1.15, -0.1, 1.5), (2.45, 0.8, 0.72), "blanket_night", n=3.0)
    t.blob("quilt fold", (-1.2, -0.1, 1.5), (0.35, 0.8, 0.72), "blanket_night", n=3.0)
    t.blob("quilt hang", (1.15, -0.78, 1.15), (2.45, 0.14, 0.55), "blanket_night", n=3.0)
    # his hand clutching the quilt's edge: the fingers hooked over it towards us, the rest of the hand behind it
    hand_at = Vector((-0.78, -0.6, 2.1))
    R = Person.hand_frame(-1, palm=(0, -1, 0.1), fingers=(0.1, 0.05, 1))
    he = t.empty("quilt hand", (0, 0, 0), rot=R.to_euler())
    qh = Hand(t, -1, he, spec["skin"], size=0.75, pose="hook", name="quilt hand")
    he.location = hand_at - R @ qh.anchor("grip")
    # nightstand with a small clock reading 4:00
    t.group("stand")
    nx = -3.4
    t.box("stand", (nx - 0.9, 0.5, 0.85), (1.1, 0.9, 1.0), "wood")
    t.box("stand top", (nx - 0.9, 0.5, 1.4), (1.3, 1.05, 0.1), "wood_light")
    cx, cz = nx - 0.9, 1.78
    t.cyl("clock", (cx, 0.45, cz), 0.3, 0.16, "brass", rot=(D2R(90), 0, 0))
    t.cyl("clock face", (cx, 0.36, cz), 0.23, 0.02, "paper", rot=(D2R(90), 0, 0))
    t.line("clock minute", [(cx, 0.33, cz), (cx, 0.33, cz + 0.17)], width=0.012, poly=True, taper=False)
    t.line("clock hour", [(cx, 0.33, cz), (cx + 0.147, 0.33, cz - 0.085)], width=0.016, poly=True, taper=False)
    for h in range(12):
        a = math.pi * 2 * h / 12
        t.line(f"tick{h}", [(cx + 0.2 * math.sin(a), 0.33, cz + 0.2 * math.cos(a)), (cx + 0.225 * math.sin(a), 0.33, cz + 0.225 * math.cos(a))], width=0.006, poly=True, taper=False)
    t.camera("cam", (0, -4.0, 2.45), (-1.25, 0, 2.0), lens=34)
