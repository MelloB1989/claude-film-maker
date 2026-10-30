# 'So you eat what you stored. Salted fish. Hard bread. Tea, again.' The keeper at his small table; the sigh at 'Tea, again'.
import math

DRAW = {"scene": "meal", "fps": 6}


def build(ctx):
    from lib.toon import Person, D2R
    from mathutils import Quaternion, Vector
    t = ctx.toon
    F = ctx.frame
    t.world("wall_warm")
    t.group("room", distance=7.0)
    t.card("wall", t.rect(30, 14, 0, 1.5), 0.05, "wall_warm", loc=(0, 3.2, 0))
    t.card("floor", t.rect(30, 3), 0.05, "floor", loc=(0, 3.1, -1.3))
    # window (right)
    t.card("win frame", t.rect(1.2, 1.4, 0, 0), 0.06, "wood_dark", loc=(2.6, 3.0, 1.9))
    t.card("win glass", t.rect(1.0, 1.2, 0, 0), 0.02, "sky", loc=(2.6, 2.94, 1.9))
    t.card("win bar v", t.rect(0.06, 1.2, 0, 0), 0.03, "wood_dark", loc=(2.6, 2.9, 1.9))
    t.card("win bar h", t.rect(1.0, 0.06, 0, 0), 0.03, "wood_dark", loc=(2.6, 2.9, 1.9))
    # shelf of jars (left)
    t.box("shelf", (-2.5, 2.7, 1.95), (1.9, 0.5, 0.08), "wood")
    for i, (jx, h, c) in enumerate(((-3.05, 0.42, "jar"), (-2.65, 0.3, "jar2"), (-2.28, 0.46, "jar"), (-1.92, 0.34, "jar2"))):
        t.cyl(f"jar{i}", (jx, 2.7, 1.99 + h / 2), 0.14, h, c, r2=0.14)
        t.cyl(f"lid{i}", (jx, 2.7, 1.99 + h + 0.03), 0.105, 0.06, "wood_dark")
    t.box("shelf2", (-2.5, 2.7, 1.1), (1.9, 0.5, 0.08), "wood")
    t.cyl("pot", (-2.9, 2.7, 1.3), 0.2, 0.3, "stone_dark", r2=0.16)
    t.cyl("pot2", (-2.3, 2.7, 1.28), 0.15, 0.26, "jar2", r2=0.12)
    # table
    t.group("table", distance=6.0)
    TZ = 0.62
    t.box("top", (0, -0.9, TZ - 0.05), (3.4, 1.7, 0.1), "wood_light")
    t.box("apron", (0, -1.7, TZ - 0.35), (3.4, 0.08, 0.6), "wood")
    for sx in (-1, 1):
        t.box(f"leg{sx}", (1.55 * sx, -1.7, -0.4), (0.12, 0.12, 1.6), "wood_dark")
    # plate, fish, bread
    PX, PY, PZ = 1.02, -1.0, TZ + 0.02
    t.cyl("plate", (PX, PY, PZ), 0.5, 0.04, "plate", r2=0.5)
    t.cyl("plate dip", (PX, PY, PZ + 0.022), 0.36, 0.01, "plate")
    fish_pts = ([(-0.30, 0.0), (-0.2, 0.09), (0.0, 0.12), (0.2, 0.08), (0.3, 0.02), (0.44, 0.1), (0.4, 0.0), (0.44, -0.1),
                 (0.3, -0.02), (0.2, -0.08), (0.0, -0.12), (-0.2, -0.09)])
    fish = t.card("fish", fish_pts, 0.012, "fish", loc=(PX - 0.06, PY, PZ + 0.04), rot=(D2R(-90), 0, 0))
    z = PZ + 0.07
    t.line("spine", [(PX - 0.06 - 0.22 + 0.5 * k / 6 * 1.0, PY, z) for k in range(7)], width=0.007, poly=True, taper=False)
    for j in range(5):
        x = PX - 0.06 - 0.12 + j * 0.095
        for s in (-1, 1):
            t.line(f"rib{j}{s}", [(x, PY, z), (x + 0.03, PY + s * 0.07, z)], width=0.006, poly=True, taper=False)
    eye = t.blob("fish eye", (PX - 0.06 - 0.22, PY, z), (0.016, 0.016, 0.006), "ink", c=t.face)
    BX, BY = -0.05, -1.0
    t.blob("loaf", (BX, BY, TZ + 0.1), (0.36, 0.2, 0.13), "bread", n=2.6)
    loaf = t.cur.objects[-1] if t.cur.objects else None
    MX, MY = -0.72, -0.86
    t.cyl("tea saucer", (MX, MY, TZ + 0.015), 0.24, 0.03, "plate")
    t.group("people", distance=6.5)
    sp = {**t.cast["keeper"], "skin": "skin_warm", "coat": "coat_warm", "collar": "coat_warm"}
    k = Person(t, sp, "keeper", loc=(0, 0, 0), hands=("fist", "table"))
    k.expression("tired")
    # score lines on the loaf
    for j in range(3):
        x = BX - 0.16 + j * 0.16
        t.mark_on(f"score{j}", loaf, [(x - 0.05, BY + 0.1, TZ + 0.4), (x + 0.05, BY - 0.1, TZ + 0.4)], None, d=(0, 0, -1),
                  width=0.016, n=4)
    # the mug, held by its handle: the fingers curled through the loop, the body beside the fist
    mug = t.empty("mug", (0, 0, 0))
    MR, REACH = 0.115, 0.235            # mug radius; from the mug's axis to the handle's grip
    t.cyl("mug body", (0, 0, 0), MR, 0.25, "mug", parent=mug, r2=0.105)
    t.cyl("tea", (0, 0, 0.121), 0.095, 0.012, "tea", parent=mug, c=t.plain)
    t.torus("mug handle", (0, MR + 0.05, 0.0), 0.072, 0.016, "mug", parent=mug, rot=(0, D2R(90), 0))
    MZ = TZ + 0.03 + 0.125
    k.hand(-1, "fist", F(0))
    k.hold(-1, mug, offset=(0, -REACH, 0), rot=(0, D2R(-90), 0))

    def mug_at(c, palm, fingers):
        p = Vector(palm).normalized()
        return dict(target=tuple(Vector(c) - p * REACH), palm=palm, fingers=fingers)
    down = mug_at((MX, MY, MZ), (1, 0, 0), (0, -1, 0))
    up = mug_at((-0.22, -0.8, 1.36), (1, 0.12, 0), (0, -0.86, 0.5))
    for ts, pose in ((0.0, down), (3.9, down), (4.4, up), (5.25, up), (5.8, down), (6.9, down)):
        k.reach(-1, frame=F(ts), **pose)
    # the left hand flat on the table; at 'Hard bread' a fist knocks twice on the loaf
    flat = dict(target=(0.46, -0.66, TZ + 0.005), palm=(0, 0.1, -1), fingers=(-0.25, -1, 0), at="palm")
    k.hand(1, "table", F(0))
    k.reach(1, frame=F(0.0), **flat)
    k.reach(1, frame=F(2.5), **flat)
    knock = dict(palm=(-1, 0, 0), fingers=(0, -1, -0.15), at="grip")
    for ts, z in ((2.67, 0.2), (2.83, 0.0), (3.0, 0.2), (3.17, 0.0), (3.33, 0.18)):
        k.hand(1, "fist", F(ts))
        k.reach(1, target=(BX + 0.08, BY + 0.05, TZ + 0.27 + z), frame=F(ts), **knock)
    k.hand(1, "table", F(3.67))
    k.reach(1, frame=F(3.67), **flat)
    k.reach(1, frame=F(6.9), **flat)
    # face: looks at the fish, then the bread, blinks, the sigh
    k.head_pose(0, 0, 0, F(0.0))
    k.head_pose(0, 0, 9, F(1.6))
    k.head_pose(-8, 0, 9, F(2.8))
    k.head_pose(0, 0, 3, F(3.7))
    k.head_pose(0, 0, 6, F(4.2))
    k.head_pose(0, 0, -3, F(4.55))
    k.head_pose(0, 0, 5, F(5.3))
    k.head_pose(0, 0, 0, F(6.1))
    for tb in (0.9, 2.2, 3.4, 6.2):
        k.blink(F(tb))
    k.eyes("open", F(0.0))
    k.eyes("closed", F(4.25))
    k.eyes("open", F(4.8))
    k.expression("tired", F(0.0))
    k.expression("sad", F(4.25))
    k.expression("tired", F(5.1))
    t.camera("cam", (0, -6.4, 3.0), (0, 0, 1.2), lens=44)
