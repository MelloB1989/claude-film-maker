# 'But tonight, like every night,' ...a match brought to the lamp's wick; it catches, the glow blooms.
DRAW = {"scene": "light", "fps": 12}


def build(ctx):
    import math
    from lib.toon import Person, D2R
    from mathutils import Vector
    t = ctx.toon
    F = ctx.frame
    t.world("wall_night")
    LX = -0.9                                    # the lamp's x
    t.group("far")
    # the glow: two discs behind the lamp, bloom at 1.2 s
    glows = []
    for i, (r, a) in enumerate(((1.3, 0.42), (0.85, 0.5))):
        g = t.card(f"glow{i}", t.ring(0, 0, r, r, 64), 0.0, "#f6cf8e", c=t.plain, loc=(LX, 1.6, 0.95), alpha=a)
        glows.append(g)
    t.group("lamp", distance=4.0)
    t.box("table", (-0.6, 0.3, -0.3), (9, 1.9, 0.6), "wood")
    t.box("table edge", (-0.6, -0.66, -0.06), (9, 0.04, 0.12), "wood_light")
    # oil lamp
    t.cyl("foot", (LX, 0, 0.04), 0.34, 0.08, "brass", r2=0.28)
    t.cyl("stem", (LX, 0, 0.17), 0.09, 0.2, "brass")
    t.blob("font", (LX, 0, 0.38), (0.3, 0.3, 0.17), "brass")
    t.cyl("collar", (LX, 0, 0.55), 0.13, 0.1, "brass", r2=0.17)
    t.cyl("burner", (LX, 0, 0.64), 0.07, 0.1, "brass")
    t.line("wick", [(LX, 0, 0.66), (LX, 0, 0.74)], width=0.012, col="ink", c=t.face, taper=False, poly=True)
    t.blob("bulb", (LX, 0, 0.9), (0.27, 0.27, 0.27), "lamp_glass", alpha=0.35)
    t.cyl("chimney", (LX, 0, 1.38), 0.14, 0.5, "lamp_glass", r2=0.12, alpha=0.35)
    # flame on the wick (appears at 1.2 s)
    fl = t.card("lamp flame", t.leaf(0.075, 0.26), 0.0, "flame", c=t.plain, loc=(LX, -0.28, 0.74))
    fc = t.card("lamp flame core", t.leaf(0.04, 0.15), 0.0, "flame_core", c=t.plain, loc=(LX, -0.285, 0.75))
    catch = F(1.2)
    for o in (fl, fc):
        t.show(o, on=[catch], off=[1])
        for i, f in enumerate(range(catch, ctx.count + 1)):
            k = 1.0 + (0.1 if i % 3 == 1 else 0.0) * (1 if i > 1 else 0)
            gr = min(1.0, 0.25 + 0.25 * i) if i < 4 else 1.0
            o.scale = (k * gr, gr * (1.05 if i % 2 else 0.97), 1)
            o.keyframe_insert("scale", frame=f)
    for g in glows:
        t.show(g, on=[catch], off=[1])
        for i, f in enumerate(range(catch, ctx.count + 1)):
            s = min(1.0, 0.25 + 0.2 * i) if i < 5 else 1.0 + 0.012 * (i % 2)
            g.scale = (s, 1, s)
            g.keyframe_insert("scale", frame=f)
    # the keeper's left arm reaching in from the frame's left (he stands off it), a lit match pinched between thumb and
    # index, palm down, the thumb towards us; the match head goes to the wick
    t.group("people", distance=4.0)
    SC = 1.5
    RX, RY, RZ = LX - 3.0, 0.1, -0.85
    sp = {**t.cast["keeper"], "skin": "skin_warm", "coat": "coat_warm", "collar": "coat_warm", "hand": {"subdiv": 3}}
    k = Person(t, sp, "keeper", loc=(RX, RY, RZ), rot=(0, 0, 0), hands=("rest", "pinch"), scale=SC)
    k.expression("tired")
    k.head_pose(turn=-12, nod=10)
    k.arm(-1, (-0.58, 0.0, 0.5), (-0.5, -0.1, 0.0))
    ML = 0.42                                    # a long lamp match
    match = t.cyl("match", (0, 0, 0), 0.011, ML, "match", c=t.cur, parent=None)
    t.blob("match head", (0, 0, -ML / 2 - 0.01), (0.026, 0.026, 0.034), "match_head", parent=match)
    # the flame stands up off the head whichever way the match points (its rotation copied from the world's)
    upright = t.empty("upright", (0, 0, 0))
    # struck at 0.35 s (the match_strike cue): it flares, then settles
    strike = F(0.35)
    for nm, (w, h), col, dy in (("match flame", (0.05, 0.17), "flame", -0.04), ("match flame core", (0.025, 0.1), "flame_core", -0.045)):
        fl = t.card(nm, t.leaf(w, h), 0.0, col, c=t.plain, parent=match, loc=(0, dy, -ML / 2 - 0.03))
        cr = fl.constraints.new("COPY_ROTATION")
        cr.target = upright
        t.show(fl, on=[strike], off=[1])
        for i, k_ in enumerate((1.6, 1.25, 1.0)):
            fl.scale = (k_, k_, k_)
            fl.keyframe_insert("scale", frame=strike + i)
    # held by its end, pointing on from the fingers and a little down
    tilt = D2R(10)
    off = Vector((0, -0.01, -ML / 2 + 0.03))
    k.hold(1, match, tuple(off), (tilt, 0, 0), at="pinch")
    head = k.hands[1].anchor("pinch") + off + Vector((0, math.sin(tilt), -math.cos(tilt))) * (ML / 2 + 0.01)
    palm, fingers = (0, 0.25, -1), (1, 0, -0.12)

    path = [(0.0, (LX - 1.5, -0.4, 0.5)), (0.7, (LX - 0.55, -0.3, 0.72)), (1.1, (LX - 0.02, -0.03, 0.74)),
            (1.3, (LX - 0.02, -0.03, 0.74)), (1.75, (LX - 0.75, -0.3, 0.62)), ((ctx.count - 1) / ctx.fps, (LX - 1.5, -0.4, 0.5))]

    def along(ts):
        """The match head's place at ts: eased from key to key (every frame keyed, so the hand never swings)."""
        for (t0, a), (t1, b) in zip(path, path[1:]):
            if ts <= t1:
                u = min(1.0, max(0.0, (ts - t0) / (t1 - t0)))
                u = u * u * (3 - 2 * u)
                return Vector(a).lerp(Vector(b), u)
        return Vector(path[-1][1])
    for f in range(1, ctx.count + 1):
        tp = (along((f - 1) / ctx.fps) - Vector((RX, RY, RZ))) / SC
        short = k.reach(1, tp, palm, fingers, at=head, frame=f)
        if short > 1e-3:
            print(f"light: the match falls {short:.3f} short at frame {f}")
    t.camera("cam", (LX - 0.55, -4.0, 0.95), (LX - 0.55, 0, 0.95), lens=44)
