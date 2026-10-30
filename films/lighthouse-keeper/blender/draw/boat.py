# 'Once a month, a boat brings supplies.' Day: a rowing boat laden with crates and sacks pulls towards the island.
DRAW = {"scene": "boat", "fps": 0}


def build(ctx):
    import math
    import _sets as S
    from lib.toon import Person, D2R
    t = ctx.toon
    pal = S.DAY
    S.sky(t, "sky", "#e3f4f6", horizon=0.0, far=500, height=40)
    t.group("far")
    S.cloud(t, "cloud1", (-60, 480, 40), w=60, h=14, col="cloud", seed=31)
    S.cloud(t, "cloud2", (90, 480, 58), w=44, h=10, col="cloud", seed=32)
    S.sea(t, pal, marks=110, seed=8, near=-12, far=200, spread=70, width=0.035)
    t.group("island")
    S.island(t, pal, loc=(-22, 70, 0), r=6.5, h=1.6, seed=4)
    S.lighthouse(t, pal, loc=(-21, 70.5, 1.7), h=7.0)
    S.cottage(t, pal, loc=(-24.9, 69, 1.55), rot=-12)
    # the boat, side on, bow towards the island (screen left)
    t.group("boat")
    g = t.empty("boat", (2.2, 0, 0), rot=(0, D2R(-3), D2R(-8)))
    hull = [(-3.0, 0.75), (2.6, 0.75), (2.0, 0.05), (1.2, -0.35), (-1.6, -0.35), (-2.6, 0.1)]
    t.card("hull", hull, 1.5, "wood", parent=g, loc=(0, -0.75, 0))
    t.card("gunwale", [(-3.05, 0.7), (2.65, 0.7), (2.6, 0.88), (-3.0, 0.88)], 1.5, "wood_dark", parent=g, loc=(0, -0.77, 0))
    t.line("plank1", [(-2.45, -0.77, 0.36), (0, -0.77, 0.33), (2.1, -0.77, 0.38)], g, width=0.03)
    t.box("crate1", (-2.0, 0.1, 1.1), (0.8, 0.8, 0.7), "wood_light", parent=g, rot=(0, 0, D2R(8)))
    t.box("crate2", (-1.95, -0.05, 1.7), (0.55, 0.55, 0.5), "wood_light", parent=g, rot=(0, 0, D2R(-10)))
    t.blob("sack", (2.05, 0.1, 1.05), (0.42, 0.38, 0.48), "#e6d3a8", parent=g, n=2.3)
    t.cyl("barrel", (1.45, 0.3, 1.1), 0.32, 0.75, "wood", parent=g, r2=0.32)
    # the boatman rowing, facing the stern (screen right), oars back
    t.group("people")
    b = Person(t, {**t.cast["boatman"], "hand": {"detail": "mitten"}}, "boatman", loc=(-0.3, 0.1, 0.62), rot=(0, 0, D2R(50)), scale=0.66,
               hands=("grip", "grip"), expression="stern")
    b.root.parent = g
    b.head_pose(turn=-20, tilt=4)
    # his fists round the oars' handles, knuckles up (each hand's grip runs along its oar)
    to_person = (Matrix.Translation(b.root.location) @ Matrix.Rotation(D2R(50), 4, "Z") @ Matrix.Scale(0.66, 4)).inverted()
    for s, (x0, y0) in ((-1, (-0.3, -0.9)), (1, (-0.3, 0.9))):
        oar = t.cyl(f"oar{s}", (0, 0, 0), 0.05, 4.4, "wood_dark", parent=g, seg=12)
        p0 = Vector((x0, y0 * 0.95, 1.2))
        p1 = Vector((x0 + 2.3, y0 * 2.3, -0.4))
        oar.location = (p0 + p1) / 2
        oar.rotation_euler = (p1 - p0).to_track_quat("Z", "Y").to_euler()
        t.card(f"blade{s}", t.rect(0.32, 0.9), 0.04, "wood_dark", parent=oar, loc=(0, 0, 1.9))
        u = (to_person.to_3x3() @ (p1 - p0)).normalized()
        palm = Vector((0, 0, -1))
        palm = (palm - u * palm.dot(u)).normalized()
        fingers = u.cross(palm)
        if fingers.y > 0:
            fingers = -fingers
        short = b.reach(s, to_person @ (p0 + (p1 - p0).normalized() * 0.18), palm, fingers, at="grip")
        if short > 1e-3:
            print(f"boat: the boatman's hand {s} falls {short:.3f} short of its oar")
    t.use(t.face)
    for i, (x, w) in enumerate([(-4.5, 1.6), (-3.6, 1.2), (5.2, 1.3)]):
        t.line(f"wake{i}", [(x + 2.2, -1.2 + 0.4 * i, 0.03), (x + 2.2 + w * 0.5, -1.2 + 0.4 * i, 0.12), (x + 2.2 + w, -1.2 + 0.4 * i, 0.03)],
               width=0.05, col="foam")
    t.camera("cam", (0.8, -16, 2.6), (-1.5, 10, 1.6), lens=40)


from mathutils import Matrix, Vector  # noqa: E402
