"""Period props from code for anime shots (feudal Japan, rural): a wooden pier plank by plank (a whole thatched hut
and its chochin are lib/minka.py's), a covered ferry boat, a paper lantern, a straw rain cape, a katana (whole or broken) and
its scabbard, a straw kasa hat, a kiseru pipe, a bamboo ferry pole (one that hides a blade).
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


def _unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def _square(d, up) -> np.ndarray:
    """A unit direction square to `d`, as near `up` as it can be (another when `up` runs along `d`)."""
    d, up = _unit(d), np.asarray(up, float)
    s = up - d * np.dot(up, d)
    if np.linalg.norm(s) < 1e-6:
        s = np.array((1.0, 0.0, 0.0)) - d * d[0]
    return _unit(s)


def _carry(parent, kids) -> None:
    """Parent `kids` to `parent` (all built in place, none moved yet), so moving it moves them."""
    for kid in kids:
        kid.parent = parent


def blade_path(pommel, hilt_dir, hilt: float, blade: float, sori: float, side, fs) -> np.ndarray:
    """Points along a curved blade at fractions `fs` of its length from the guard: from `hilt` metres along `hilt_dir`
    past the pommel, bowed by `sori` away from its edge (the edge on the side away from up, the flat facing `side`)."""
    pommel, d, side = np.asarray(pommel, float), _unit(hilt_dir), np.asarray(side, float)
    edge = np.cross(d, side)
    if edge[2] > 0:
        edge = -edge                                    # the edge below
    guard = pommel + d * hilt
    fs = np.asarray(fs, float)
    return guard + np.outer(fs * blade, d) + np.outer(sori * np.sin(np.pi * fs), edge)


def katana(name: str, m: dict, pommel, hilt_dir, *, hilt: float = 0.27, blade: float = 0.72, sori: float = 0.017,
           side=(1.0, 0.0, 0.0), coll=None, broken: float | None = None) -> list:
    """A katana from its pommel along `hilt_dir` (the hilt, then the blade carrying on): a blade with a gentle curve
    (`sori`; its edge on the side away from up, its flat facing `side`), the collar, an oval guard `hilt` metres from
    the pommel, a wrapped hilt and its cap; a nodachi is one with a longer hilt and blade. `m`: steel, brass, lacquer,
    wrap. Returns [blade, collar, guard, hilt, cap]; `broken` (a fraction of the blade from the guard) snaps it there,
    the blade ending in a ragged break and its point a separate object, last: [..., cap, point]."""
    pommel = np.asarray(pommel, float)
    d = _unit(hilt_dir)
    side = np.asarray(side, float)
    guard = pommel + d * hilt
    edge = np.cross(d, side)
    if edge[2] > 0:
        edge = -edge

    def piece(label, f0, f1, end_width):
        fs = np.linspace(f0, f1, max(3, int(16 * (f1 - f0)) + 2))
        path = blade_path(pommel, d, hilt, blade, sori, side, fs)
        width = np.where(fs < 0.97, 0.016 - 0.004 * fs, 0.002)
        thick = np.where(fs < 0.97, 0.0036 - 0.0012 * fs, 0.0008)
        width[-1] *= end_width
        return shapes.loft(f"{name}-{label}", path, width, thick, material=m["steel"], coll=coll, n=4, power=1.0,
                           subsurf=0, up=tuple(side))

    obs = [piece("blade", 0.0, broken if broken else 1.0, 0.55 if broken else 1.0)]
    obs.append(shapes.loft(f"{name}-habaki", [guard, guard + d * 0.03], 0.019, 0.007, material=m["brass"], coll=coll, n=8,
                           subsurf=0, up=tuple(side)))
    obs.append(shapes.loft(f"{name}-tsuba", [guard - d * 0.004, guard + d * 0.004], 0.04, 0.034, material=m["lacquer"],
                           coll=coll, n=20, subsurf=0, up=tuple(edge)))
    obs.append(shapes.loft(f"{name}-tsuka", [pommel, pommel + d * 0.5 * hilt, guard - d * 0.006], [0.015, 0.0135, 0.0145],
                           [0.012, 0.011, 0.0118], material=m["wrap"], coll=coll, n=12, subsurf=0, up=tuple(edge)))
    obs.append(shapes.loft(f"{name}-kashira", [pommel - d * 0.012, pommel + d * 0.004], 0.0155, 0.0125,
                           material=m["lacquer"], coll=coll, n=12, subsurf=0, up=tuple(edge)))
    if broken:
        # the snapped-off half: from a ragged break (a little short of the hilt's piece's, so the two never overlap)
        tip = piece("point", broken + 0.004, 1.0, 1.0)
        rings = np.array([v.co[:] for v in tip.data.vertices]).reshape(-1, 4, 3)
        rings[0] += np.array([d * 0.006 * s for s in (0.0, 1.0, 0.3, 1.0)])     # a jagged end, not a clean cut
        tip.data.vertices.foreach_set("co", rings.reshape(-1).astype(np.float32))
        tip.data.update()
        obs.append(tip)
    return obs


def saya(name: str, m: dict, coll, mouth, direction, length: float, *, sori: float = 0.02, edge=(0.0, 0.0, -1.0),
         width: float = 0.019, thickness: float = 0.013) -> list:
    """A plain scabbard from its mouth at `mouth` along `direction`, `length` long, bowed by `sori` (its curve away
    from `edge`, the side its blade's edge lies), a horn collar round the mouth and a cap at the end. `m`: lacquer,
    wrap. Returns [scabbard, collar, cap], the last two carried by the scabbard."""
    mouth, d = np.asarray(mouth, float), _unit(direction)
    e = _square(d, edge)
    fs = np.linspace(0.0, 1.0, 10)
    path = mouth + np.outer(fs * length, d) - np.outer(sori * np.sin(np.pi * fs), e)
    up = tuple(np.cross(d, e))
    sheath = shapes.loft(f"{name}-saya", path, width - 0.002 * fs, thickness - 0.0015 * fs, material=m["lacquer"],
                         coll=coll, n=12, power=2.2, subsurf=0, up=up)
    collar = shapes.loft(f"{name}-koiguchi", [mouth - d * 0.002, mouth + d * 0.022], width + 0.0012,
                         thickness + 0.0012, material=m["wrap"], coll=coll, n=12, power=2.2, subsurf=0, up=up)
    end = path[-1]
    cap = shapes.loft(f"{name}-kojiri", [end - d * 0.03, end + d * 0.004], width - 0.0012, thickness - 0.0005,
                      material=m["wrap"], coll=coll, n=12, power=2.2, subsurf=0, up=up)
    _carry(sheath, [collar, cap])
    return [sheath, collar, cap]


def kasa_profile(radius: float, height: float, *, thickness: float = 0.007, bulge: float = 0.8, apex: float = 0.012,
                 n: int = 12) -> np.ndarray:
    """A kasa's cross-section [(r, z)] as a closed loop for shapes.lathe: its underside from near the apex out to the
    brim, round the brim's edge, its top back up to the apex. The top falls from `height` at the middle to 0 at the
    brim (`bulge` < 1: a shallow dome to a cone), the underside `thickness` under it."""
    us = np.linspace(apex / radius, 1.0, n)
    top = height * (1.0 - us) ** bulge
    under = [(u * radius, z - thickness) for u, z in zip(us, top)]
    over = [(u * radius, z) for u, z in zip(us[::-1], top[::-1])]
    return np.array(under + [(radius + thickness * 0.4, -thickness * 0.5)] + over)


def kasa_seat(radius: float, height: float, head: float, *, thickness: float = 0.007, bulge: float = 0.8) -> float:
    """How far above its brim a kasa (kasa_profile) rests on a head `head` metres in radius where its underside meets
    the head's sides: put the brim that far under the head's widest point near the crown."""
    u = min(head / radius, 1.0)
    return height * (1.0 - u) ** bulge - thickness


def kasa(name: str, m: dict, coll, *, radius: float = 0.3, height: float = 0.12, thickness: float = 0.007,
         bulge: float = 0.8, spokes: int = 24, n: int = 96) -> list:
    """A wide straw kasa, a rain hat, at the origin: its brim's middle at 0, its apex up +z. Its woven straw shows as
    `spokes` thin ribs of a darker straw running from the apex to the brim (of `n` sectors round it) and the brim's
    edge bound in it, a knob at the apex. `m`: straw, straw_dark (straw_tip for the binding when given). Returns
    [hat, knob], the knob carried by the hat: place it by the hat (its matrix_world) after."""
    prof = kasa_profile(radius, height, thickness=thickness, bulge=bulge)
    hat = shapes.lathe(name, prof, material=m["straw"], coll=coll, n=n)
    hat.data.materials.append(m.get("straw_dark", m["straw"]))
    k = len(prof)
    half = (k - 1) // 2
    every = max(1, n // max(spokes, 1))
    idx = []
    for poly in hat.data.polygons:
        vs = sorted(poly.vertices)
        ring, seg = vs[0] // n, vs[0] % n
        top = ring > half
        idx.append(1 if (top and seg % every == 0) or ring in (half - 1, half) else 0)
    hat.data.polygons.foreach_set("material_index", idx)
    knob = shapes.ellipsoid(f"{name}-knob", (0.0, 0.0, height), (0.014, 0.014, 0.01), material=m["straw"], coll=coll,
                            n=10)
    _carry(hat, [knob])
    return [hat, knob]


def kiseru(name: str, m: dict, coll, mouth, direction, *, length: float = 0.3, up=(0.0, 0.0, 1.0)) -> list:
    """A kiseru, the long thin pipe: a brass mouthpiece at `mouth`, a dark bamboo stem along `direction`, a brass neck
    curving `up` at the far end into a small bowl. `m`: brass, stem (or lacquer). Returns [stem, mouthpiece, neck,
    bowl], carried by the stem; the bowl's mouth is the last point of the neck plus a little `up` (for smoke)."""
    mouth, d = np.asarray(mouth, float), _unit(direction)
    u = _square(d, up)
    stem_mat = m.get("stem", m.get("lacquer"))
    a, b = mouth + d * 0.055, mouth + d * (length - 0.05)
    piece = shapes.loft(f"{name}-suikuchi", [mouth, a + d * 0.004], [0.0032, 0.0048], material=m["brass"], coll=coll,
                        n=8, subsurf=0)
    stem = shapes.loft(f"{name}-rao", [a, b], 0.0043, material=stem_mat, coll=coll, n=8, subsurf=0)
    neck_path = [b - d * 0.004, b + d * 0.025, b + d * 0.042 + u * 0.006, b + d * 0.05 + u * 0.016]
    neck = shapes.loft(f"{name}-gankubi", neck_path, [0.0048, 0.0042, 0.004, 0.0045], material=m["brass"], coll=coll,
                       n=8, subsurf=0)
    top = neck_path[-1]
    bowl = shapes.loft(f"{name}-hizara", [top - u * 0.004, top + u * 0.006], [0.0055, 0.0075], material=m["brass"],
                       coll=coll, n=10, subsurf=0)
    _carry(stem, [piece, neck, bowl])
    return [stem, piece, neck, bowl]


def ferry_pole(name: str, m: dict, coll, foot, top: float, *, radius: float = 0.022, nodes_every: float = 0.34,
               grip=(1.62, 1.78), turns: int = 6, axis=None, split: float | None = None,
               blade: float | None = None) -> list:
    """A tall bamboo ferry pole from `foot` (x, y, z) up to height `top`: its nodes every `nodes_every` metres and a
    cord wound round it where it is held (`grip`: from, to, heights on the upright pole; None for none). `axis` leans
    it (the same length along that direction: a pole on a shoulder, laid in a boat). `m`: bamboo, cord (steel for a
    blade). Returns [pole, nodes..., cord turns...], the rest carried by the pole.

    A sword-cane (`split`: the height where it parts, at the cord's lower end) is two: the shaft (foot to split) and
    the handle above it with the cord, and with `blade` a thin straight blade that long from the split down inside
    the shaft, carried by the handle: pull the handle away and it is drawn. Returns [shaft, handle, nodes..., cord
    turns..., blade]."""
    foot = np.asarray(foot, float)
    d = np.array((0.0, 0.0, 1.0)) if axis is None else _unit(axis)
    z0 = float(foot[2])
    length = top - z0
    at = lambda h: foot + d * (h - z0)        # noqa: E731  a height on the upright pole, wherever it leans
    if split is None:
        obs = [shapes.cylinder(f"{name}-pole", tuple(at(z0)), tuple(at(top)), radius, material=m["bamboo"], coll=coll,
                               n=12)]
        sections = [(obs[0], z0, top)]
    else:
        shaft = shapes.cylinder(f"{name}-pole", tuple(at(z0)), tuple(at(split)), radius, material=m["bamboo"],
                                coll=coll, n=12)
        handle = shapes.cylinder(f"{name}-handle", tuple(at(split)), tuple(at(top)), radius, material=m["bamboo"],
                                 coll=coll, n=12)
        obs = [shaft, handle]
        sections = [(shaft, z0, split), (handle, split, top)]

    def owner(z):
        return next(s for s, lo, hi in sections if lo <= z <= hi + 1e-6)

    kids = []
    for k, z in enumerate(np.arange(z0 + 0.32, z0 + length - 0.1, nodes_every)):
        if split is not None and abs(z - split) < 0.03:
            continue
        kids.append((shapes.cylinder(f"{name}-node{k}", tuple(at(z - 0.01)), tuple(at(z + 0.01)), radius + 0.004,
                                     material=m["bamboo"], coll=coll, n=12), z))
    if grip is not None:
        for k, z in enumerate(np.linspace(grip[0], grip[1], turns)):
            kids.append((shapes.cylinder(f"{name}-cord{k}", tuple(at(z - 0.008)), tuple(at(z + 0.008)), radius + 0.005,
                                         material=m["cord"], coll=coll, n=12), z + 0.0081))
    if split is not None and blade:
        side = _square(d, (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0))
        fs = np.linspace(0.0, 1.0, 8)
        path = [at(split + 0.01) - d * blade * f for f in fs]
        width = np.where(fs < 0.93, 0.0075 - 0.0015 * fs, 0.0012)
        kids.append((shapes.loft(f"{name}-blade", path, width, 0.0018, material=m["steel"], coll=coll, n=4, power=1.0,
                                 subsurf=0, up=tuple(side)), split + 0.01))
    for ob, z in kids:
        ob.parent = owner(z)
    return obs + [ob for ob, _ in kids]
