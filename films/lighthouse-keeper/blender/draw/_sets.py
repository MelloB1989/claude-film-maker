"""Set pieces shared by this film's drawings (blender/draw.py loads a drawing with this folder on sys.path).

Every colour is a name in data/look/toon.json; each piece takes a `pal` dict mapping its parts to colour names, so
one lighthouse serves day, dusk, storm and night. Units are metres-ish; the sea is the plane z = 0.
"""
import math
import random

from mathutils import Vector

from lib.toon import D2R

DAY = {"tower": "tower", "red": "tower_red", "glass": "glass", "dome": "dome", "iron": "iron", "door": "door",
       "cottage": "cottage", "roof": "roof", "rock": "rock", "rock_dark": "rock_dark", "grass": "grass",
       "sea": "sea", "line": "sea_line", "foam": "foam", "window": "glass"}
DUSK = {**DAY, "grass": "grass_dusk", "sea": "dusk_sea", "line": "dusk_line", "glass": "glass_lit", "window": "glass_lit"}
NIGHT = {**DAY, "tower": "tower_night", "red": "tower_red_night", "glass": "glass_lit", "cottage": "cottage_night",
         "roof": "roof_night", "rock": "rock_night", "rock_dark": "rock_night", "grass": "rock_night", "sea": "night_sea",
         "line": "night_line", "foam": "night_line", "door": "hull_night", "window": "glass_lit", "dome": "capband",
         "iron": "capband"}
STORM = {**NIGHT, "sea": "storm_sea", "line": "storm_line", "foam": "storm_foam"}
DAWN = {**DAY, "sea": "dawn_sea", "line": "dawn_line"}


def _mix(t, a, b, k):
    ha, hb = t.hex(a).lstrip("#"), t.hex(b).lstrip("#")
    ca = [int(ha[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(hb[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * k):02x}" for x, y in zip(ca, cb))


def sky(t, top, low=None, horizon=0.0, far=400.0, bands=4, height=36.0):
    """The sky: the world colour, and optionally flat bands stepping down to `low` at the horizon (a posterised
    gradient, flat and never inked)."""
    t.world(top)
    if low:
        for i in range(bands):
            k = (i + 1) / bands
            ztop = horizon + height * (1 - i / bands)
            t.card(f"sky band{i}", [(-1200, horizon - 8), (1200, horizon - 8), (1200, ztop), (-1200, ztop)], 0.0,
                   _mix(t, top, low, k), c=t.plain, loc=(0, far - i * 2, 0))


def sea(t, pal, size=600.0, marks=60, seed=1, near=-30.0, far=120.0, spread=60.0, width=0.03):
    """The sea plane (its far edge draws the horizon line) and wave marks: short '~' strokes in the line colour."""
    g = t.use(t.group("sea"))
    t.occluder(t.card("sea", t.rect(2 * size, 2 * size), 0.0, pal["sea"], loc=(0, size * 0.2, 0), rot=(D2R(-90), 0, 0)))
    sea_marks(t, pal, marks, seed, near, far, spread, width)
    return g


def sea_marks(t, pal, marks=40, seed=1, near=-30.0, far=120.0, spread=60.0, width=0.03, z=0.0, tag="wave"):
    """Wave marks: short '~' strokes in the sea's line colour, denser near the camera's side of the range."""
    rnd = random.Random(seed)
    for i in range(marks):
        y = near + (far - near) * rnd.random() ** 1.6
        x = rnd.uniform(-spread, spread) * (0.4 + (y - near) / (far - near))
        L = rnd.uniform(0.8, 1.6) * (1 + (y - near) / 40)
        pts = [(x + L * k / 8, y, z + 0.02 + 0.06 * math.sin(k * math.pi / 2) * (1 + (y - near) / 60)) for k in range(9)]
        t.line(f"{tag}{seed}_{i}", pts, width=width * (1 + (y - near) / 50), col=pal["line"], taper=True)


def island(t, pal, loc=(0, 0, 0), r=5.0, h=1.4, seed=2, grass=True, foam=True, boulders=3):
    """A rock island: a lumpy flattened rock, a grass cap, a few boulders, a ring of foam on the water."""
    x, y, z = loc
    t.blob("island", (x, y, z - 0.2), (r, r * 0.8, h), pal["rock"], shape=t.lumpy(0.18, seed=seed), seg=96)
    if grass:
        t.blob("grass", (x + 0.2, y + 0.2, z + h * 0.62), (r * 0.72, r * 0.56, h * 0.45), pal["grass"],
               shape=t.lumpy(0.12, seed=seed + 7), seg=64)
    rnd = random.Random(seed)
    for i in range(boulders):
        a = rnd.uniform(0, 2 * math.pi)
        rr = r * rnd.uniform(0.95, 1.15)
        s = rnd.uniform(0.7, 1.1)
        t.blob(f"boulder{i}", (x + rr * math.cos(a), y + rr * 0.8 * math.sin(a), z + 0.25 * s), (s * 1.3, s, s * 0.75),
               pal["rock_dark"], shape=t.lumpy(0.2, seed=seed + i))
    if foam:
        pts = [((r * 1.25 + 0.35 * math.sin(7 * a + seed)) * math.cos(a), (r * 0.95 + 0.3 * math.sin(5 * a)) * math.sin(a))
               for a in [2 * math.pi * k / 72 for k in range(72)]]
        t.card("foam", pts, 0.0, pal["foam"], c=t.plain, loc=(x, y, 0.01), rot=(D2R(-90), 0, 0))


def lighthouse(t, pal, loc=(0, 0, 0), h=6.0, r0=1.05, r1=0.72, bands=5, lit=False):
    """A banded tower with a door and windows, a gallery with a railing, the lantern room and its dome.
    Returns {"lamp": world point of the light, "gallery": its height, "top": the top}."""
    x, y, z = loc
    n = bands
    for i in range(n):
        za, zb = z + h * i / n, z + h * (i + 1) / n
        ra, rb = r0 + (r1 - r0) * i / n, r0 + (r1 - r0) * (i + 1) / n
        t.cyl(f"band{i}", (x, y, (za + zb) / 2), ra, zb - za, pal["red"] if i % 2 else pal["tower"], r2=rb, seg=72)
    tower = [o for o in t.cur.objects if o.name.startswith("band0")][0]
    p, nrm = t.onto(tower, (x, y, z + 0.55), (0, 1, 0), lift=0.0)
    t.card("door", t.ring(0, 0.25, 0.28, 0.22, 24, 0, math.pi) + [(-0.28, -0.55), (0.28, -0.55)],
           0.03, pal["door"], loc=p, rot=t.facing(nrm))
    for i, zz in enumerate((0.42, 0.7)):
        band = [o for o in t.cur.objects if o.name.startswith(f"band{int(zz * n)}")][0]
        p, nrm = t.onto(band, (x + 0.12, y, z + h * zz), (0, 1, 0), lift=0.0)
        t.card(f"window{i}", t.rect(0.22, 0.34), 0.03, pal["window"], loc=p, rot=t.facing(nrm))
    gz = z + h
    t.cyl("gallery", (x, y, gz + 0.06), r1 + 0.42, 0.12, pal["iron"], seg=72)
    t.torus("rail", (x, y, gz + 0.62), r1 + 0.38, 0.035, pal["iron"])
    for i in range(16):
        a = 2 * math.pi * i / 16
        t.cyl(f"post{i}", (x + (r1 + 0.38) * math.cos(a), y + (r1 + 0.38) * math.sin(a), gz + 0.36), 0.025, 0.56, pal["iron"], seg=12)
    lr = r1 * 0.78
    glass = t.cyl("lantern", (x, y, gz + 0.62), lr, 0.9, pal["glass"], seg=72)
    for i in range(7):
        a = -math.pi / 2 + (i - 3) * 0.32
        t.line(f"mullion{i}", [(x + (lr + 0.012) * math.cos(a), y + (lr + 0.012) * math.sin(a), gz + 0.18 + 0.88 * k / 2) for k in range(3)],
               width=0.022, taper=False, poly=True)
    t.cyl("lantern base", (x, y, gz + 0.2), lr + 0.06, 0.16, pal["iron"], seg=72)
    t.blob("dome", (x, y, gz + 1.07), (lr + 0.1, lr + 0.1, 0.55), pal["dome"], shape=t.flat_bottom(0.0))
    t.blob("vent", (x, y, gz + 1.68), (0.13, 0.13, 0.13), pal["dome"])
    t.cyl("rod", (x, y, gz + 1.95), 0.018, 0.5, pal["iron"], seg=8)
    return {"lamp": Vector((x, y, gz + 0.62)), "gallery": gz, "top": gz + 2.2}


def cottage(t, pal, loc=(0, 0, 0), rot=0.0, w=2.6, d=1.8, h=1.4, lit=False):
    """A keeper's cottage: whitewashed walls, a pitched roof, a chimney, a door and a window."""
    x, y, z = loc
    g = t.empty("cottage", loc, rot=(0, 0, D2R(rot)))
    t.box("walls", (0, 0, h / 2), (w, d, h), pal["cottage"], parent=g)
    roof = [(-w / 2 - 0.15, 0), (w / 2 + 0.15, 0), (0, 0.95)]
    t.card("roof", roof, d + 0.3, pal["roof"], parent=g, loc=(0, -d / 2 - 0.15, h))
    t.box("chimney", (w * 0.28, 0.2, h + 0.85), (0.32, 0.32, 0.8), pal["cottage"], parent=g)
    t.card("cdoor", t.rect(0.42, 0.8, 0, 0.4), 0.02, pal["door"], parent=g, loc=(-w * 0.22, -d / 2 - 0.02, 0))
    t.card("cwin", t.rect(0.5, 0.42, 0, 0), 0.02, pal["window"], parent=g, loc=(w * 0.22, -d / 2 - 0.02, h * 0.55))
    return g


def cloud(t, name, loc, w=6.0, h=1.6, col="cloud", seed=1, c=None):
    """A flat cloud facing the camera (-Y): the top a run of round scallops (the upper hull of a few circles),
    the bottom flat."""
    rnd = random.Random(seed)
    k = rnd.randint(4, 6)
    circ = []
    for i in range(k):
        cx = -w / 2 + w * (i + 0.5) / k + rnd.uniform(-0.12, 0.12) * w / k
        rr = (w / k) * rnd.uniform(0.62, 0.95)
        cz = h * 0.15 + h * 0.35 * (1 - abs(cx) / (w / 2)) * rnd.uniform(0.7, 1.0)
        circ.append((cx, cz, rr))
    left = min(cx - rr for cx, cz, rr in circ)
    right = max(cx + rr for cx, cz, rr in circ)
    pts = []
    n = 140
    for j in range(n + 1):
        x = left + (right - left) * j / n
        z = max((cz + math.sqrt(max(rr * rr - (x - cx) ** 2, 0)) for cx, cz, rr in circ if abs(x - cx) <= rr), default=0.0)
        pts.append((x, max(z, 0.0)))
    pts += [(right, 0.0), (left, 0.0)]
    return t.card(name, pts, 0.05, col, c=c, loc=loc)


def gulls(t, centre, n=3, span=4.0, size=0.5, seed=4, col="ink"):
    rnd = random.Random(seed)
    for i in range(n):
        x = centre[0] + rnd.uniform(-span, span)
        z = centre[2] + rnd.uniform(-span * 0.3, span * 0.3)
        s = size * rnd.uniform(0.7, 1.2)
        pts = [(x - s, centre[1], z + 0.25 * s), (x - s * 0.5, centre[1], z + 0.4 * s), (x, centre[1], z),
               (x + s * 0.5, centre[1], z + 0.4 * s), (x + s, centre[1], z + 0.25 * s)]
        t.line(f"gull{i}", pts, width=0.045 * s / 0.5, col=col)


def sun(t, loc, r=2.0, col="sun"):
    return t.card("sun", t.ring(0, 0, r, r, 64), 0.05, col, loc=loc)


def stars(t, n=60, y=300.0, spread=(-160, 160), zr=(18, 110), seed=9, col="star"):
    rnd = random.Random(seed)
    for i in range(n):
        s = rnd.uniform(0.25, 0.7)
        pts = []
        for j in range(8):
            a = math.pi * j / 4
            rr = s if j % 2 == 0 else s * 0.3
            pts.append((rr * math.cos(a), rr * math.sin(a)))
        t.card(f"star{i}", pts, 0.0, col, c=t.plain, loc=(rnd.uniform(*spread), y, rnd.uniform(*zr)))


def beam(t, origin, yaw, length=60.0, spread=7.0, col="beam", alpha=0.4, name="beam"):
    """A lighthouse beam: a long flat-shaded transparent wedge from origin, pointing at `yaw` degrees (0 = towards
    -Y, the camera), never inked. Returns its pivot (rotate .rotation_euler.z to sweep)."""
    piv = t.empty(name, tuple(origin))
    piv.rotation_euler.z = D2R(yaw)
    half = math.radians(spread / 2)
    w = length * math.tan(half)
    o = t.cyl(f"{name} cone", (0, -length / 2, 0), 0.12, length, col, c=t.plain, parent=piv, r2=w,
              rot=(D2R(90), 0, 0), seg=48, caps=False, alpha=alpha)
    o.scale = (1, 0.35, 1)
    return piv


def rain(t, frame_count, area=(-30, 30, -20, 40, 0, 25), n=260, seed=11, col="rain", slant=0.25, length=1.6, width=0.025):
    """Rain: thin slanted strokes, re-scattered every frame (shown on one frame each), never inked."""
    rnd = random.Random(seed)
    x0, x1, y0, y1, z0, z1 = area
    sets = min(frame_count, 4)
    groups = []
    for sidx in range(sets):
        objs = []
        for i in range(n):
            x, y, z = rnd.uniform(x0, x1), rnd.uniform(y0, y1), rnd.uniform(z0, z1)
            objs.append(t.line(f"rain{sidx}_{i}", [(x, y, z), (x + slant * length, y, z - length)], width=width * (1 + max(0, y) / 30),
                               col=col, c=t.plain, poly=True, taper=False))
        groups.append(objs)
    for f in range(1, frame_count + 1):
        for sidx, objs in enumerate(groups):
            on = (f - 1) % sets == sidx
            for o in objs:
                o.hide_render = not on
                o.keyframe_insert("hide_render", frame=f)
    return groups


def schooner(t, pal_hull="hull", pal_sail="sail", loc=(0, 0, 0), scale=1.0, heel=0.0, name="ship"):
    """A two-masted schooner in profile (facing -Y): hull, masts, sails, a pennant. Returns its root."""
    g = t.empty(name, loc, rot=(0, D2R(heel), 0), scale=(scale,) * 3)
    hull = [(-4.2, 0.9), (4.6, 0.9), (3.8, -0.2), (3.0, -0.6), (-3.0, -0.6), (-3.8, -0.1)]
    t.card(f"{name} hull", hull, 1.2, pal_hull, parent=g, loc=(0, -0.6, 0))
    t.card(f"{name} rail", [(-4.2, 0.9), (4.6, 0.9), (4.5, 1.05), (-4.1, 1.05)], 1.2, pal_hull, parent=g, loc=(0, -0.62, 0))
    for i, mx in enumerate((-1.4, 1.6)):
        t.cyl(f"{name} mast{i}", (mx, 0, 4.6), 0.08, 7.4, "iron", parent=g, seg=12)
        sail = [(mx + 0.15, 1.5), (mx + 2.6 if i else mx + 2.4, 1.6), (mx + 0.2, 7.6)]
        t.card(f"{name} sail{i}", sail, 0.04, pal_sail, parent=g, loc=(0, -0.1, 0))
        t.card(f"{name} gaff{i}", [(mx - 2.0, 1.5), (mx - 0.15, 1.5), (mx - 0.2, 6.6)], 0.04, pal_sail, parent=g, loc=(0, -0.12, 0))
    t.card(f"{name} jib", [(2.0, 1.5), (5.8, 1.2), (2.0, 7.0)], 0.04, pal_sail, parent=g, loc=(0, -0.08, 0))
    t.card(f"{name} flag", [(1.6, 8.3), (2.6, 8.05), (1.6, 7.8)], 0.02, "tower_red", parent=g, loc=(0, -0.1, 0))
    return g


def swell(t, name, loc, w=3.0, h=0.95, col="storm_sea", foam="storm_foam", seed=1, parent=None):
    """A storm swell: a dark rounded hump with a foam crest line along its top and a curl at one end. Returns its root
    (bob it with .location.z)."""
    g = t.empty(name, loc, parent=parent)
    t.blob(f"{name} body", (0, 0, 0), (w, 0.9, h), col, parent=g)
    rnd = random.Random(seed)
    crest = [(w * 0.92 * math.cos(a), -0.35, h * 0.98 * math.sin(a) + 0.04 + 0.03 * math.sin(7 * a + seed))
             for a in [math.pi * (0.12 + 0.76 * k / 18) for k in range(19)]]
    t.line(f"{name} crest", crest, g, width=0.085, col=foam)
    a0 = math.pi * rnd.choice((0.2, 0.8))
    cx, cz = w * 0.8 * math.cos(a0), h * 0.8 * math.sin(a0) + 0.1
    curl = [(cx + 0.35 * math.cos(b), -0.6, cz + 0.3 * math.sin(b)) for b in [math.pi * (0.1 + 1.4 * k / 8) for k in range(9)]]
    t.line(f"{name} curl", curl, g, width=0.06, col=foam)
    return g


def splash(t, name, loc, size=1.5, col="storm_foam", seed=1, c=None):
    """A cartoon splash: a flat white burst (rounded lobes and spikes over a flat base) facing the camera."""
    rnd = random.Random(seed)
    pts = []
    n = 9
    for i in range(n + 1):
        a = math.pi * i / n
        r = size * (1.0 if i % 2 else 0.55) * rnd.uniform(0.85, 1.15)
        pts.append((r * math.cos(a) * 1.2, r * math.sin(a)))
    return t.card(name, pts[::-1], 0.05, col, c=c, loc=loc)
