"""Period props from code for anime shots (feudal Japan, rural): a wooden pier plank by plank, a thatched hut with
its eaves fringed in straw, a covered ferry boat, a paper lantern, a straw rain cape, a katana, a bamboo ferry pole.
Each takes its materials by part (toon materials, so the line art draws their boards, posts and straw) and its size and
place, and returns its objects.

World axes as the shots use them: z up; a pier runs along x with its deck's top at `deck_z`.
"""
from __future__ import annotations

import math

import numpy as np

from . import shapes


def pier(m: dict, coll, *, span=(-6.5, 7.6), half: float = 1.0, deck_z: float = 0.0, water_z: float = -0.45, post_xs=(-5, -2.5, 0, 2.5, 5, 7.4),
         seed: int = 1, prefix: str = "pier") -> list:
    """A pier along x over `span`, `2 half` wide: boards laid across it with gaps and a little wear, two stringers
    under them, posts down into the water on both sides each bound near its top with three turns of rope.
    `m`: plank, post, rope."""
    rng = np.random.default_rng(seed)
    obs = []
    x, i = span[0], 0
    while x < span[1]:
        w = 0.24 + rng.uniform(-0.02, 0.02)
        obs.append(shapes.box(f"{prefix}-plank{i}", (x + w / 2, rng.uniform(-0.03, 0.03), deck_z - 0.035 + rng.uniform(-0.01, 0.006)),
                              (w, 2 * half + rng.uniform(-0.06, 0.06), 0.07), material=m["plank"], coll=coll, rot_z=rng.uniform(-0.025, 0.025)))
        x += w + 0.028
        i += 1
    for s in (-1, 1):
        obs.append(shapes.box(f"{prefix}-stringer{s}", ((span[0] + span[1]) / 2, s * 0.82 * half, deck_z - 0.13), (span[1] - span[0], 0.12, 0.12),
                              material=m["post"], coll=coll))
    for k, px in enumerate(post_xs):
        for s in (-1, 1):
            top = deck_z + 0.42 + rng.uniform(-0.08, 0.25) + (0.25 if k == len(post_xs) - 1 else 0.0)
            c = (px + rng.uniform(-0.05, 0.05), s * (half + 0.08))
            obs.append(shapes.cylinder(f"{prefix}-post{k}{s}", (c[0], c[1], water_z - 1.0), (c[0], c[1], top), 0.09 + rng.uniform(-0.01, 0.015),
                                       material=m["post"], coll=coll, n=10))
            for j in range(3):
                z = top - 0.1 - 0.05 * j
                obs.append(shapes.cylinder(f"{prefix}-rope{k}{s}{j}", (c[0], c[1], z - 0.017), (c[0], c[1], z + 0.017), 0.105,
                                           material=m["rope"], coll=coll, n=12))
    return obs


def paper_lantern(name: str, material, coll, center, *, radius: float = 0.16, height: float = 0.44, cord=None, cord_top: float | None = None):
    """A round paper lantern (lathe) at `center`, hanging on a cord up to `cord_top` when given."""
    cx, cy, cz = center
    h = height / 2
    lantern = shapes.lathe(name, [(0.0, -h), (radius * 0.75, -h * 0.82), (radius, 0.0), (radius * 0.75, h * 0.82), (0.0, h)],
                           material=material, coll=coll, n=16, center=center)
    obs = [lantern]
    if cord is not None and cord_top is not None:
        obs.append(shapes.cylinder(f"{name}-cord", (cx, cy, cz + h), (cx, cy, cord_top), 0.006, material=cord, coll=coll, n=6))
    return lantern, obs


def thatched_hut(m: dict, coll, center, *, size=(3.2, 2.6, 2.0), overhang: float = 0.55, peak: float = 1.35, door_side: str = "+x",
                 prefix: str = "hut", seed: int = 5) -> dict:
    """A small hut at `center` (its floor), walls of dark boards (battens on the door side), a deep gabled roof of thatch
    with straw hanging from its eaves, a lit doorway on `door_side`. `m`: wall, thatch, door (an emitting glow)."""
    rng = np.random.default_rng(seed)
    cx, cy, cz = center
    W, D, Hh = size
    sgn = 1 if door_side == "+x" else -1
    obs = [shapes.box(f"{prefix}-walls", (cx, cy, cz + Hh / 2), (W, D, Hh), material=m["wall"], coll=coll)]
    for k in range(9):
        obs.append(shapes.box(f"{prefix}-batten{k}", (cx + sgn * (W / 2 + 0.01), cy - D / 2 + 0.15 + k * (D - 0.3) / 8, cz + Hh / 2),
                              (0.02, 0.04, Hh), material=m["wall"], coll=coll))
    obs.append(shapes.box(f"{prefix}-door", (cx + sgn * (W / 2 + 0.02), cy - 0.45, cz + 0.8), (0.02, 0.7, 1.5), material=m["door"], coll=coll))
    for s in (-1, 1):
        a = math.atan2(peak, D / 2 + overhang)
        L = math.hypot(peak, D / 2 + overhang)
        obs.append(shapes.box(f"{prefix}-roof{s}", (cx, cy + s * (D / 2 + overhang) / 2, cz + Hh + peak / 2), (W + 2 * overhang, L, 0.22),
                              material=m["thatch"], coll=coll, rot=shapes.rot_x(-s * a)))
    roots, dirs, lens, wid = [], [], [], []
    for s in (-1, 1):
        for k in range(70):
            roots.append((cx - W / 2 - overhang + (W + 2 * overhang) * k / 69, cy + s * (D / 2 + overhang), cz + Hh - 0.05))
            dirs.append((0, s * 0.3, -1))
            lens.append(rng.uniform(0.15, 0.3))
            wid.append(0.07)
    obs.append(shapes.strips(f"{prefix}-eaves", roots, dirs, lens, wid, material=m["thatch"], coll=coll, segs=2))
    obs.append(shapes.box(f"{prefix}-ridge", (cx, cy, cz + Hh + peak), (W + 2 * overhang + 0.1, 0.25, 0.18), material=m["thatch"], coll=coll))
    eave = (cx + sgn * (W / 2 + 0.35), cy - D / 2 - 0.1, cz + Hh)
    return {"objects": obs, "eave": eave}


def covered_boat(m: dict, coll, *, x0: float, y: float, water_z: float, length: float = 5.0, beam: float = 1.36, prefix: str = "boat",
                 seed: int = 9) -> dict:
    """A covered ferry boat along x from `x0`, its keel line at `y`: a lofted hull (blunt ends rising a little), four
    poles holding a thatched roof with a straw fringe. `m`: hull, post, thatch."""
    rng = np.random.default_rng(seed)
    xs = np.linspace(x0, x0 + length, 9)
    f = np.linspace(-1, 1, 9)
    widths = beam / 2 * np.sqrt(np.clip(1 - f ** 4, 0.05, 1))
    depth = 0.42 * np.sqrt(np.clip(1 - f ** 6, 0.25, 1))
    path = [(x, y, water_z + 0.12 + 0.18 * fi ** 4) for x, fi in zip(xs, f)]
    hull = shapes.loft(f"{prefix}-hull", path, widths, depth, material=m["hull"], coll=coll, n=16, power=3.0, offset=[(0, 0.18 * d) for d in depth])
    obs = [hull]
    rz = water_z + 0.2
    for k, (px, py) in enumerate([(x0 + 1.2, y - 0.5), (x0 + 1.2, y + 0.5), (x0 + 3.6, y - 0.5), (x0 + 3.6, y + 0.5)]):
        obs.append(shapes.cylinder(f"{prefix}-pole{k}", (px, py, rz), (px, py, rz + 1.25), 0.03, material=m["post"], coll=coll, n=8))
    obs.append(shapes.box(f"{prefix}-roof", (x0 + 2.4, y, rz + 1.32), (3.0, 1.35, 0.12), material=m["thatch"], coll=coll))
    roots, dirs, lens, wid = [], [], [], []
    for s in (-1, 1):
        for k in range(40):
            roots.append((x0 + 0.9 + 3.0 * k / 39, y + s * 0.68, rz + 1.28))
            dirs.append((0, s * 0.2, -1))
            lens.append(rng.uniform(0.1, 0.2))
            wid.append(0.08)
    obs.append(shapes.strips(f"{prefix}-fringe", roots, dirs, lens, wid, material=m["thatch"], coll=coll, segs=2))
    return {"objects": obs, "hull": hull, "bow": (x0 + length - 0.2, y - 0.3, rz + 0.25)}


def straw_cape(name: str, material, coll, *, center, radii, top_z: float, hem_z: float, front_gap: float = 30.0,
               flare: float = 0.3, layers=((1.0, 220, (0.012, 0.022)), (0.4, 140, (0.014, 0.026))), lift: float = 0.07,
               seed: int = 3, segs: int = 4, tiers=None, tip_material=None, alt_material=None, rope_material=None,
               ink: bool = True, droop: float = 0.05, hug=None, gap: float = 0.012, layer: float = 0.01,
               taper: float = 0.88, front_hem: float = 0.0, clump: int = 1, ragged=(0.82, 1.12),
               shag: float = 0.0) -> object:
    """A mino, the shaggy straw rain cape: straw hanging from a ring round the shoulders (`center` (x, y) its middle,
    `radii` (front-back, side) its half sizes, at `top_z`), flaring out by `flare` as it falls and drooping by
    `droop`, open `front_gap` degrees either side of the front (+x, the wearer facing +x).

    `tiers` [(root, length, count, (min width, max width)[, flare[, ring]])] builds it as thatch: each tier's straw
    tied on at `root` (0 at the ring to 1 at the hem, as a fraction of `top_z - hem_z`; below 0 above the ring: a collar
    gathered at the neck) and hanging `length` (a fraction of the same), each upper tier over the one below, a tier
    flaring by its own `flare` from a ring `ring` times the cape's; every fibre tapers by `taper` (0.88: to a ragged
    point), their lengths spread over `ragged` (times the tier's) and the front edges hang `front_hem` of the drop
    shorter than the back. `tip_material` colours the last part
    of each fibre (the bleached ends), `alt_material` one fibre in four (a second straw), `rope_material` binds each
    tier's top with a cord and ties the neck with a rope knotted at the front (children of the cape). Without `tiers`,
    the older `layers` [(length fraction, count, widths)]: a long layer to the hem and a short collar lifted `lift`.

    `hug(z, angle)` drapes it over the wearer: how near the axis the straw may come at height z in the direction
    `angle` (radians from +x toward +y; lib/vrm_skin.py's Drape of the posed body's girth). Each tier's straw is tied
    on round the body there and pushed out to `gap` (plus `layer` for each tier under it) over it all the way down: it
    lies on the shoulders and falls straight from the widest of the back. `clump` > 1 gathers the fibres in wet clumps
    of about that many, their tips drawn together; `shag` (metres) lets each tip wander that far aside and out (a
    shaggy cape, not a combed one).

    `ink` False keeps the fibres out of the line art (fine straw inks solid at a distance; they still hide what is
    behind them). Built where it hangs (attach it to the wearer, human.attach); its "flutter" vertex group runs from
    0 at each fibre's root to 1 at its tip, so toon.flutter stirs the straw and holds the collar."""
    rng = np.random.default_rng(seed)
    cx, cy = center
    rx, ry = radii
    drop = top_z - hem_z
    if tiers is None:
        tiers = [(-lift / drop if frac < 1.0 else 0.0, frac + (lift / drop if frac < 1.0 else 0.0), count, wr) for frac, count, wr in layers]
    gap_a = math.radians(front_gap)
    verts, faces, mats, weights = [], [], [], []
    rings = []
    for ti, tier in enumerate(sorted(tiers, key=lambda t: -t[0])):
        # lower tiers first: each upper tier's straw lies over the roots of the one below
        root, length, count, (w0, w1) = tier[:4]
        tflare = tier[4] if len(tier) > 4 else flare
        scale = tier[5] if len(tier) > 5 else 1.0
        z0 = top_z - root * drop
        grow = max(root, 0.0) * drop * flare - (0.008 if root > 0 else 0.0)
        rings.append((z0, rx * scale + grow, ry * scale + grow))
        tgap = gap + layer * ti
        # wet straw in clumps: each clump's fibres share a direction and their tips meet
        n_clumps = max(1, count // max(1, clump))
        if clump > 1:
            clump_a = -math.pi + 2 * math.pi * (np.arange(n_clumps) + rng.uniform(-0.3, 0.3, n_clumps)) / n_clumps
        for i in range(count):
            a = -math.pi + 2 * math.pi * (i + rng.uniform(-0.5, 0.5)) / count
            if abs(a) < gap_a:
                continue
            ca = clump_a[int((a + math.pi) / (2 * math.pi) * n_clumps) % n_clumps] if clump > 1 else a
            out = np.array([math.cos(a), math.sin(a), 0.0])
            r0 = np.array([cx + (rx * scale + grow) * math.cos(a), cy + (ry * scale + grow) * math.sin(a), z0 - rng.uniform(0.0, 0.025)])
            if hug is not None:
                reach = max(math.hypot(r0[0] - cx, r0[1] - cy), hug(r0[2], a) + tgap)
                r0[:2] = (cx + reach * math.cos(a), cy + reach * math.sin(a))
            d = out * tflare * rng.uniform(0.75, 1.25) + np.array([0.0, 0.0, -1.0]) + rng.normal(0, 0.03, 3)
            d /= np.linalg.norm(d)
            L = length * drop * rng.uniform(*ragged) * (1.0 - front_hem * max(0.0, math.cos(a)) ** 2)
            w = rng.uniform(w0, w1)
            side = np.cross(d, (0.0, 0.0, 1.0))
            side /= max(np.linalg.norm(side), 1e-9)
            bend = out * droop * 0.3 * rng.uniform(0.3, 1.2) + np.array([0.0, 0.0, -droop * rng.uniform(0.6, 1.3)])
            rag = side * rng.normal(0, w * 0.8) + np.array([0.0, 0.0, rng.uniform(-0.02, 0.02)])
            if clump > 1:
                # drawn toward the clump's middle at the tip
                rag = rag * 0.4 + (np.array([math.cos(ca), math.sin(ca), 0.0]) - out) * math.hypot(r0[0] - cx, r0[1] - cy) * 0.6
            if shag > 0:
                rag = rag + side * rng.normal(0, shag) + out * abs(rng.normal(0, shag * 0.6))
            alt = alt_material is not None and rng.uniform() < 0.25
            base = len(verts)
            for sgi in range(segs + 1):
                f = sgi / segs
                fa = f ** 1.4 if hug is not None else f    # draped: closer steps near the root, round the shoulders
                p = r0 + d * L * fa + bend * fa * fa + rag * fa ** 3
                if hug is not None:
                    q = p[:2] - (cx, cy)
                    rad = math.hypot(q[0], q[1])
                    need = hug(p[2], math.atan2(q[1], q[0])) + tgap
                    if rad < need:
                        p[:2] = (cx, cy) + q / max(rad, 1e-9) * need
                ww = w * (1.0 - taper * fa ** 1.2)
                verts += [p - side * ww / 2, p + side * ww / 2]
                weights += [f ** 1.5, f ** 1.5]
            for sgi in range(segs):
                q = base + 2 * sgi
                faces.append((q, q + 1, q + 3, q + 2))
                tip = tip_material is not None and sgi >= segs - max(1, segs // 3)
                mats.append(1 if tip else (2 if alt else 0))
    cape = shapes.mesh_object(name, verts, faces, material, coll, smooth=False)
    for extra in (tip_material, alt_material):
        if extra is not None:
            cape.data.materials.append(extra)
    if tip_material is None and alt_material is not None:
        mats = [0 if m == 1 else 1 for m in mats]
    elif tip_material is None:
        mats = [0] * len(mats)
    elif alt_material is None:
        mats = [min(m, 1) for m in mats]
    for poly, m in zip(cape.data.polygons, mats):
        poly.material_index = m
    g = cape.vertex_groups.new(name="flutter")
    for vi, wgt in enumerate(weights):
        g.add([vi], wgt, "REPLACE")
    if not ink:
        cape.lineart.usage = "OCCLUSION_ONLY"
    if rope_material is not None:
        kids = []
        # a cord along the top of each tier, across the back and round the sides (not over the open front)
        for k, (z0, ax, ay) in enumerate(sorted(rings)[:-1]):
            ang = np.linspace(gap_a, 2 * math.pi - gap_a, 40)
            path = [(cx + (ax + 0.004) * math.cos(t), cy + (ay + 0.004) * math.sin(t), z0 - 0.004) for t in ang]
            kids.append(shapes.loft(f"{name}-cord{k}", path, 0.0045, material=rope_material, coll=coll, n=6, subsurf=0, cap=True))
        # the neck rope round the highest ring, right round and knotted at the front, its two ends hanging
        z0, ax, ay = max(rings, key=lambda r: r[0])
        ang = np.linspace(0, 2 * math.pi, 49)
        path = [(cx + (ax + 0.002) * math.cos(t), cy + (ay + 0.002) * math.sin(t), z0 - 0.006) for t in ang]
        kids.append(shapes.loft(f"{name}-rope", path, 0.007, material=rope_material, coll=coll, n=6, subsurf=0, cap=False))
        knot = np.array([cx + ax - 0.004, cy, z0 + 0.008])
        kids.append(shapes.ellipsoid(f"{name}-knot", tuple(knot), (0.014, 0.017, 0.013), material=rope_material, coll=coll, n=10))
        for k, s_ in enumerate((-1, 1)):
            end = [knot, knot + np.array([0.01, s_ * 0.012, -0.05]), knot + np.array([0.012, s_ * 0.02, -0.11])]
            kids.append(shapes.loft(f"{name}-rope-end{k}", end, [0.006, 0.0055, 0.004], material=rope_material, coll=coll, n=6,
                                    subsurf=0))
        for kid in kids:
            kid.parent = cape
            kid["outline"] = False   # thin cords: an outline hull (lib/outline.py) turns them into dark tabs
    return cape


def katana(name: str, m: dict, pommel, hilt_dir, *, hilt: float = 0.27, blade: float = 0.72, sori: float = 0.017,
           side=(1.0, 0.0, 0.0), coll=None) -> list:
    """A katana from its pommel along `hilt_dir` (the hilt, then the blade carrying on): a blade with a gentle curve
    (`sori`; its edge on the side away from up, its flat facing `side`), the collar, an oval guard `hilt` metres from
    the pommel, a wrapped hilt and its cap. `m`: steel, brass, lacquer, wrap. Returns [blade, collar, guard, hilt,
    cap]."""
    pommel = np.asarray(pommel, float)
    d = np.asarray(hilt_dir, float)
    d = d / np.linalg.norm(d)
    side = np.asarray(side, float)
    guard = pommel + d * hilt
    edge = np.cross(d, side)
    if edge[2] > 0:
        edge = -edge                                    # the edge below
    fs = np.linspace(0, 1, 16)
    path = [guard + d * blade * f + edge * sori * math.sin(math.pi * f) for f in fs]
    width = np.where(fs < 0.97, 0.016 - 0.004 * fs, 0.002)
    thick = np.where(fs < 0.97, 0.0036 - 0.0012 * fs, 0.0008)
    obs = [shapes.loft(f"{name}-blade", path, width, thick, material=m["steel"], coll=coll, n=4, power=1.0, subsurf=0,
                       up=tuple(side))]
    obs.append(shapes.loft(f"{name}-habaki", [guard, guard + d * 0.03], 0.019, 0.007, material=m["brass"], coll=coll, n=8,
                           subsurf=0, up=tuple(side)))
    obs.append(shapes.loft(f"{name}-tsuba", [guard - d * 0.004, guard + d * 0.004], 0.04, 0.034, material=m["lacquer"],
                           coll=coll, n=20, subsurf=0, up=tuple(edge)))
    obs.append(shapes.loft(f"{name}-tsuka", [pommel, pommel + d * 0.5 * hilt, guard - d * 0.006], [0.015, 0.0135, 0.0145],
                           [0.012, 0.011, 0.0118], material=m["wrap"], coll=coll, n=12, subsurf=0, up=tuple(edge)))
    obs.append(shapes.loft(f"{name}-kashira", [pommel - d * 0.012, pommel + d * 0.004], 0.0155, 0.0125,
                           material=m["lacquer"], coll=coll, n=12, subsurf=0, up=tuple(edge)))
    return obs


def ferry_pole(name: str, m: dict, coll, foot, top: float, *, radius: float = 0.022, nodes_every: float = 0.34,
               grip=(1.62, 1.78), turns: int = 6) -> list:
    """A tall bamboo ferry pole standing upright from `foot` (x, y, z) to height `top`: its nodes every `nodes_every`
    metres and a cord wound round it where it is held (`grip`: from, to; None for none). `m`: bamboo, cord. Returns
    [pole, nodes..., cord turns...]."""
    x, y, z0 = (float(v) for v in foot)
    obs = [shapes.cylinder(f"{name}-pole", (x, y, z0), (x, y, top), radius, material=m["bamboo"], coll=coll, n=12)]
    for k, z in enumerate(np.arange(z0 + 0.32, top - 0.1, nodes_every)):
        obs.append(shapes.cylinder(f"{name}-node{k}", (x, y, z - 0.01), (x, y, z + 0.01), radius + 0.004,
                                   material=m["bamboo"], coll=coll, n=12))
    if grip is not None:
        for k, z in enumerate(np.linspace(grip[0], grip[1], turns)):
            obs.append(shapes.cylinder(f"{name}-cord{k}", (x, y, z - 0.008), (x, y, z + 0.008), radius + 0.005,
                                       material=m["cord"], coll=coll, n=12))
    return obs
