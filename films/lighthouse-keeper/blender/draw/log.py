# 'Every few hours, you write it all down. The wind. The weather. Every ship that passes.' The logbook by lamplight.
import math
import random

DRAW = {"scene": "log", "fps": 8}

PX0, PX1 = 0.16, 0.78          # where a written row runs across the right page
ROW0 = 0.56                    # y of the first ruled line
DY = 0.1


def build(ctx):
    from lib.toon import D2R, Hand
    from mathutils import Matrix, Quaternion, Vector
    t = ctx.toon
    rnd = random.Random(7)
    t.world("wood")
    t.group("desk", distance=5.0)
    t.box("desk", (0, 0, -0.12), (9, 5.5, 0.24), "wood")
    for i in range(7):
        y = -2.4 + i * 0.8
        t.line(f"grain{i}", [(-4 + 8 * k / 12, y + 0.05 * math.sin(k * 0.9 + i), 0.002) for k in range(13)], width=0.012,
               col="wood_dark", c=t.plain, taper=True)
    t.box("cover", (0, 0, 0.0), (2.4, 1.62, 0.07), "hull")
    t.box("page L", (-0.56, 0.0, 0.06), (1.07, 1.44, 0.05), "paper")
    t.box("page R", (0.56, 0.0, 0.06), (1.07, 1.44, 0.05), "paper")
    ZP = 0.0875
    for side in (-1, 1):
        for i in range(14):
            y = ROW0 + 0.06 - i * DY
            if y < -0.66:
                break
            xa, xb = (0.1, 1.04) if side > 0 else (-1.04, -0.1)
            t.line(f"rule{side}{i}", [(xa, y, ZP), (xb, y, ZP)], width=0.0045, col="rule", poly=True, taper=False)
    t.line("gutter", [(0, 0.7, ZP), (0, -0.7, ZP)], width=0.01, poly=True, taper=False)

    def scribble(x0, x1, y, amp=0.016, seed=0):
        r = random.Random(seed)
        n = max(6, int((x1 - x0) / 0.014))
        ph = r.uniform(0, 6)
        pts = []
        for k in range(n + 1):
            u = k / n
            pts.append((x0 + (x1 - x0) * u, y + 0.014 + amp * math.sin(u * r.uniform(14, 22) + ph) * (0.5 + 0.5 * math.sin(u * 7 + ph)),
                        ZP + 0.002))
        return t.line(f"scr{seed}", pts, width=0.0065, poly=True, taper=False)

    def row_segments(y, x0, x1, n, seed):
        out = []
        r = random.Random(seed)
        a = x0
        for k in range(n):
            w = (x1 - x0 - 0.04 * (n - 1)) / n * r.uniform(0.7, 1.15)
            b = min(a + w, x1)
            out.append((a, b, scribble(a, b, y, seed=seed * 10 + k)))
            a = b + 0.04
        return out

    # old entries (static): left page and the first two rows of the right
    for i in range(1, 11):
        y = ROW0 - i * DY * 0.0 + 0.0 - (i - 1) * DY
        row_segments(y, -0.98, -0.98 + rnd.uniform(0.5, 0.9), rnd.randint(3, 5), 100 + i)
    for i in range(2):
        row_segments(ROW0 - i * DY, PX0, PX0 + rnd.uniform(0.6, 0.85), rnd.randint(3, 5), 200 + i)
    # the new entry
    rows = [  # (row index, start s, end s, segments, doodle)
        (2, 0.1, 2.5, 6, None),
        (4, 2.75, 3.5, 2, "wind"),
        (6, 3.7, 4.4, 2, "cloud"),
        (8, 4.6, 6.1, 4, "ship"),
    ]
    sched = []        # (start_t, end_t, y, x0, x1)
    for ri, ta, tb, n, doodle in rows:
        y = ROW0 - ri * DY
        xe = PX1 if doodle is None else PX0 + 0.5
        segs = row_segments(y, PX0, xe, n, 300 + ri)
        for k, (a, b, o) in enumerate(segs):
            u = ta + (tb - ta) * (a - PX0) / (xe - PX0)
            f = ctx.frame(u)
            t.show(o, on=[f], off=[1]) if f > 1 else None
        sched.append((ta, tb, y, PX0, xe))
        if doodle:
            dx = xe + 0.2
            objs = []
            if doodle == "wind":
                objs.append(t.line("wind1", [(dx - 0.12 + 0.24 * k / 8, y + 0.04 + 0.014 * math.sin(k * 1.5), ZP + 0.002) for k in range(9)], width=0.007, poly=True, taper=False))
                objs.append(t.line("wind2", [(dx + 0.12, y + 0.04, ZP + 0.002), (dx + 0.07, y + 0.07, ZP + 0.002)], width=0.007, poly=True, taper=False))
                objs.append(t.line("wind3", [(dx + 0.12, y + 0.04, ZP + 0.002), (dx + 0.07, y + 0.01, ZP + 0.002)], width=0.007, poly=True, taper=False))
            elif doodle == "cloud":
                pts = []
                for k in range(0, 41):
                    a = math.pi * k / 40
                    pts.append((dx - 0.1 + 0.2 * k / 40, y + 0.015 + 0.05 * abs(math.sin(a * 3)) + 0.01, ZP + 0.002))
                objs.append(t.line("cloud", pts, width=0.007, poly=True, taper=False))
                objs.append(t.line("cloudbase", [(dx - 0.1, y + 0.025, ZP + 0.002), (dx + 0.1, y + 0.025, ZP + 0.002)], width=0.007, poly=True, taper=False))
            else:
                objs.append(t.line("hull", [(dx - 0.13, y + 0.06, ZP + 0.002), (dx - 0.09, y + 0.02, ZP + 0.002), (dx + 0.09, y + 0.02, ZP + 0.002), (dx + 0.14, y + 0.06, ZP + 0.002), (dx - 0.13, y + 0.06, ZP + 0.002)], width=0.007, poly=True, taper=False))
                objs.append(t.line("mast", [(dx, y + 0.06, ZP + 0.002), (dx, y + 0.17, ZP + 0.002)], width=0.007, poly=True, taper=False))
                objs.append(t.line("sail", [(dx + 0.01, y + 0.17, ZP + 0.002), (dx + 0.1, y + 0.08, ZP + 0.002), (dx + 0.01, y + 0.08, ZP + 0.002)], width=0.007, poly=True, taper=False))
                objs.append(t.line("wave", [(dx - 0.15 + 0.3 * k / 10, y + 0.005 + 0.012 * math.sin(k * 1.9), ZP + 0.002) for k in range(11)], width=0.006, poly=True, taper=False))
            f = ctx.frame(tb + 0.05)
            for o in objs:
                t.show(o, on=[f], off=[1])
            sched[-1] = sched[-1] + (dx, y)
    # ink bottle
    t.group("props", distance=4.6)
    t.cyl("bottle", (-1.7, -0.6, 0.2), 0.2, 0.4, "#3b4a6b", r2=0.2, seg=48)
    t.cyl("bottle neck", (-1.7, -0.6, 0.46), 0.1, 0.14, "#3b4a6b", seg=32)
    t.cyl("cork", (-1.7, -0.6, 0.56), 0.075, 0.08, "wood_light", seg=24)
    t.card("bottle label", t.rect(0.22, 0.14, 0, 0), 0.0, "paper", loc=(-1.7, -0.81, 0.2), c=t.plain)
    # lamp at the frame's top left edge
    LX, LY = -1.85, 1.1
    t.cyl("lamp foot", (LX, LY, 0.05), 0.34, 0.1, "brass", r2=0.28)
    t.blob("lamp font", (LX, LY, 0.35), (0.3, 0.3, 0.2), "brass")
    t.cyl("lamp collar", (LX, LY, 0.58), 0.13, 0.1, "brass", r2=0.17)
    t.blob("lamp bulb", (LX, LY, 0.85), (0.27, 0.27, 0.28), "lamp_glass", alpha=0.45)
    t.cyl("lamp chimney", (LX, LY, 1.4), 0.13, 0.85, "lamp_glass", r2=0.12, alpha=0.45)
    t.card("lamp flame", t.leaf(0.07, 0.24), 0.0, "flame", c=t.plain, loc=(LX, LY - 0.3, 0.7))
    t.card("pool", t.ring(0, 0, 2.2, 1.3, 64), 0.0, "glow", c=t.plain, loc=(-1.2, 0.4, 0.004), rot=(D2R(-90), 0, 0), alpha=0.28)

    # ---- the hand and pen, one rigid assembly keyed at the nib ----
    t.group("hand", distance=4.2)
    root = t.empty("nib", (PX0, ROW0 - 2 * DY, ZP))
    pd = Vector((0.5, -0.32, 0.8)).normalized()                   # the pen's direction from the nib
    fd = Vector((0.82, -0.5, 0.28)).normalized()                  # the forearm's direction away from the wrist
    HS = 0.9                                                       # the hand's size (wrist to fingertip, about)
    # his right hand in the writing grip (lib/hand "pen"): the pen through the thumb and index pinch, resting on the
    # web by the index knuckle; turned so the pen runs along pd and the back of the hand faces up (to us)
    hf = t.empty("hand frame", (0, 0, 0), parent=root)
    hand = Hand(t, -1, hf, "skin_warm", size=HS, pose="pen", name="hand", subdiv=3)
    pinch = hand.anchor("pinch")
    u = (Vector((-0.25, -0.03, -0.34)) * HS - pinch).normalized()  # the pen line in the hand's space, nib to back
    nib_h = pinch - u * 0.26 * HS

    def frame(v1, v2):
        b1 = v1.normalized()
        b2 = (v2 - b1 * v2.dot(b1)).normalized()
        return Matrix((b1, b2, b1.cross(b2))).transposed()
    up = Quaternion(pd, D2R(40)) @ Vector((0.25, -0.15, 1.0))
    R = frame(pd, up) @ frame(u, Vector((0, 1, 0))).transposed()
    hf.rotation_euler = R.to_euler()
    hf.location = -(R @ nib_h)
    wrist = Vector(hf.location)
    fa = (R @ Vector((0, 0, 1))).lerp(fd, 0.3).normalized()       # the forearm: nearly straight on from the hand

    def along(o, v):
        o.rotation_euler = Vector((0, 0, 1)).rotation_difference(v).to_euler()
    k = HS / 0.75                                                  # the kit's arm proportions at this hand size
    for o in (t.cyl("wrist", wrist + fa * 0.07 * k, 0.074 * k, 0.14 * k, "skin_warm", parent=root, seg=32),
              t.blob("wrist ball", wrist, (0.074 * k,) * 3, "skin_warm", parent=root, seg=32)):
        o.lineart.usage = "NO_INTERSECTION"
    along(root.children[-2], fa)
    sl = t.sleeve("sleeve", wrist + fa * (0.04 * k + 1.2), 0.122 * k, 2.4, "coat_warm", parent=root, r2=0.13 * k)
    along(sl, fa)
    pen = t.cyl("pen", pd * 0.5, 0.017, 1.0, "pen", parent=root, r2=0.024)
    along(pen, pd)
    nib = t.cyl("pen nib", pd * 0.05, 0.004, 0.1, "brass", parent=root, r2=0.016)
    along(nib, pd)
    # keys
    r2 = random.Random(3)
    nib_base = Vector((PX0, ROW0 - 2 * DY, ZP))
    first_x = {}

    def put(f, p):
        root.location = p
        root.keyframe_insert("location", frame=f)

    for f in range(1, ctx.count + 1):
        tt = (f - 1) / ctx.fps
        pos = None
        for (ta, tb, y, x0, x1, *_) in sched:
            if ta - 0.25 <= tt <= tb + 0.2:
                u = min(max((tt - ta) / (tb - ta), 0.0), 1.0)
                x = x0 + (x1 - x0) * u
                if tt < ta:
                    lift = 0.14 * (ta - tt) / 0.25
                    x = x0 - 0.05 * (ta - tt) / 0.25
                elif tt > tb:
                    lift = 0.14 * (tt - tb) / 0.2
                else:
                    lift = 0.0
                yy = y + 0.014 + 0.012 * math.sin(tt * 23) * (0 if lift else 1)
                pos = Vector((x, yy, ZP + lift))
                break
        if pos is None:
            # travelling between rows / resting at the end
            prev = [s for s in sched if s[1] < tt]
            nxt = [s for s in sched if s[0] > tt]
            if prev and nxt:
                a, b = prev[-1], nxt[0]
                u = (tt - a[1]) / max(b[0] - a[1], 1e-6)
                pa = Vector((a[4], a[2], ZP + 0.14))
                pb = Vector((b[3], b[2], ZP + 0.14))
                pos = pa.lerp(pb, u)
            elif prev:
                a = prev[-1]
                ex = a[5] if len(a) > 5 else a[4]
                pos = Vector((ex - 0.05 + 0.02 * math.sin(tt * 2), a[2] - 0.2, ZP + 0.18))
            else:
                pos = Vector((PX0 - 0.1, ROW0 - 2 * DY, ZP + 0.2 - 0.05 * min(tt / 0.3, 1.0)))
        put(f, pos)
    t.camera("cam", (0.0, -3.35, 3.85), (0.0, 0.3, 0.0), lens=54)
