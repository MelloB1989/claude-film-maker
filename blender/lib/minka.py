"""Traditional Japanese buildings from code (Edo period, rural): a thatched riverside hut whole, frame and all, and its
red paper lantern (chochin). Built for an anime background: every part a clean solid the line art draws (boards,
posts, beams, lattice), each material a part (toon or painted materials, so the bands and the ink do the rest), detail
where a camera comes close (the door, the lantern, the eave) and plain where it doesn't.

    hut = minka.hut(m, coll, (x, y, z), ground=lambda x, y: ...)    # z: its floor
    hut["eave"], hut["door"], hut["eave_edges"]                      # where the lantern hangs, the door, drip lines
    lantern = minka.chochin("lantern", m, coll, center)

World axes: z up. The hut's door is on its +x side (`facing` turns it about z); its ridge runs along x.
"""
from __future__ import annotations

import math

import numpy as np

from . import shapes

# the windows: (wall axis 0: along x / 1: along y, its side -1/+1, from, to along it, sill, lintel height, a blind)
WINDOWS = ((0, -1, -0.45, 0.45, 1.06, 1.7, True), (1, -1, -0.95, -0.35, 1.1, 1.62, False))

# the parts' material keys, and what each falls back to when a set doesn't give it
FALLBACK = {"post": "wall", "plaster": "wall", "thatch_edge": "thatch", "ridge": "thatch", "lattice": "post",
            "stone": "post", "dark": "wall", "wood": "post", "straw": "thatch", "rope": "post", "lath": "post",
            "glass": "door", "cap": "post", "rib": "cap"}


def material(m: dict, key: str):
    """`m[key]`, or what it falls back to (FALLBACK) when the set has none."""
    while key not in m:
        key = FALLBACK[key]
    return m[key]


class Parts:
    """Geometry gathered per material and emitted as one object each (a few objects for a whole building: quick to
    build and to draw). Points are in the building's own frame; `emit` places them."""

    def __init__(self):
        self.v: dict[str, list] = {}
        self.f: dict[str, list] = {}

    def poly(self, key: str, verts, faces) -> None:
        vs, fs = self.v.setdefault(key, []), self.f.setdefault(key, [])
        base = len(vs)
        vs.extend(np.asarray(verts, float).tolist())
        fs.extend(tuple(base + i for i in face) for face in faces)

    def box(self, key: str, center, size, *, rot_z: float = 0.0, rot=None) -> None:
        sx, sy, sz = (s / 2 for s in size)
        v = np.array([(x, y, z) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)])
        R = np.asarray(rot, float) if rot is not None else shapes.rot_z(rot_z)
        self.poly(key, v @ R.T + np.asarray(center, float),
                  [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])

    def beam(self, key: str, a, b, w: float, h: float | None = None, *, up=(0.0, 0.0, 1.0)) -> None:
        """A square beam from a to b, `w` wide and `h` deep."""
        a, b = np.asarray(a, float), np.asarray(b, float)
        d = b - a
        L = np.linalg.norm(d)
        d /= L
        u = np.cross(up, d)
        if np.linalg.norm(u) < 1e-6:
            u = np.cross((1.0, 0.0, 0.0), d)
        u /= np.linalg.norm(u)
        v = np.cross(d, u)
        self.box(key, (a + b) / 2, (L, w, h or w), rot=np.column_stack([d, u, v]))

    def cyl(self, key: str, a, b, r: float, *, n: int = 8, r2: float | None = None) -> None:
        rings = shapes.loft_points(np.array([a, b], float), [r, r if r2 is None else r2], n=n,
                                   up=(0, 1, 0) if abs(np.subtract(b, a)[2]) > 0.9 * np.linalg.norm(np.subtract(b, a))
                                   else (0, 0, 1))
        self.poly(key, rings.reshape(-1, 3), shapes.tube_faces(2, n, True))

    def emit(self, prefix: str, m: dict, coll, xform) -> list:
        obs = []
        for key, vs in self.v.items():
            obs.append(shapes.mesh_object(f"{prefix}-{key}", xform(np.asarray(vs)), self.f[key], material(m, key), coll,
                                          smooth=False))
        return obs


def hip_gable_roof(X: float, Y: float, ze: float, zt: float, *, gable: float = 0.45) -> tuple[list, list, dict]:
    """A hip-and-gable (irimoya) roof's top surface over the eave rectangle +-X, +-Y at height ze, its ridge along x
    at zt: hipped below, a small upright gable (the smoke gap) under each end of the ridge, `gable` of the way down
    the slope. Returns (verts, faces, points): faces as (the two slopes, the two hips, the two gables)."""
    yg = gable * Y
    zg = zt - (zt - ze) * gable
    xr = X - (1 - gable) * Y                       # the hips as steep as the slopes
    E = {(sx, sy): (sx * X, sy * Y, ze) for sx in (-1, 1) for sy in (-1, 1)}
    G = {(sx, sy): (sx * xr, sy * yg, zg) for sx in (-1, 1) for sy in (-1, 1)}
    R = {sx: (sx * xr, 0.0, zt) for sx in (-1, 1)}
    verts = [E[k] for k in sorted(E)] + [G[k] for k in sorted(G)] + [R[-1], R[1]]
    ie = {k: i for i, k in enumerate(sorted(E))}
    ig = {k: 4 + i for i, k in enumerate(sorted(G))}
    ir = {-1: 8, 1: 9}
    slopes = [(ie[-1, -1], ie[1, -1], ig[1, -1], ir[1], ir[-1], ig[-1, -1]),
              (ie[1, 1], ie[-1, 1], ig[-1, 1], ir[-1], ir[1], ig[1, 1])]
    hips = [(ie[1, -1], ie[1, 1], ig[1, 1], ig[1, -1]), (ie[-1, 1], ie[-1, -1], ig[-1, -1], ig[-1, 1])]
    gables = [(ig[1, -1], ig[1, 1], ir[1]), (ig[-1, 1], ig[-1, -1], ir[-1])]
    return verts, slopes + hips + gables, {"xr": xr, "yg": yg, "zg": zg}


def hut(m: dict, coll, center, *, size=(3.2, 2.6, 2.0), overhang: float = 0.62, peak: float = 1.5, facing: float = 0.0,
        door=(-0.45, 0.78, 1.72), windows=WINDOWS, ground=None, porch: float = 0.55, clutter: bool = True,
        prefix: str = "hut", seed: int = 5) -> dict:
    """A thatched riverside hut with its floor at `center`, `size` (along x, along y, the walls' height), its door on
    the +x side (turned by `facing`): a post-and-beam frame on footing stones (on short stilts where `ground`, a
    function of world x, y, falls away), dark vertical boards below a rail and earthen plaster above it (one panel
    fallen to its bamboo lath), the wall plates' and tie beams' ends standing out at the corners; a deep hip-and-gable
    thatch, thick, banded in courses, its cut edge in two steps ragged at its foot, its underside on bamboo rafters, a
    ridge capped and saddled, a smoke gap under each gable; a sliding shoji door (`door`: its middle along y, width,
    height) and barred windows (`windows`, WINDOWS) glowing warm through their paper, a rolled straw blind over those
    that have one; a plank porch along the door side; and, with `clutter`, a firewood stack, a rain barrel, a straw
    cape and a hat hung by the door, oars leaning on the wall, a net drying on a bamboo rack off the back end.

    `m`: wall, thatch, door (the lit paper: an emitting material), and as it has them (else see FALLBACK) post,
    plaster, thatch_edge, ridge, lattice, stone, dark, wood, straw, rope, lath, glass (the barrel's water).
    Returns {"objects", "eave": under the eave at the door side's -y corner (where a lantern hangs), "door": the
    doorway's foot (world), "eave_edges": [(a, b), ...] each eave's drip line (world), "windows": [(where, outward),
    ...] a light outside each lit window (world), "smoke": the gaps' tops}."""
    rng = np.random.default_rng(seed)
    C = np.asarray(center, float)
    W, D, H = size
    hw, hd = W / 2, D / 2
    Rf = shapes.rot_z(facing)

    def world(p):
        return np.asarray(p, float) @ Rf.T + C

    def local_ground(x, y):
        if ground is None:
            return -0.3
        wx, wy, _ = world((x, y, 0.0))
        return float(ground(wx, wy)) - C[2]

    P = Parts()
    lights = []                                 # (where, outward): a lit window's light spilling out
    sill = 0.15
    pw = 0.14                                   # the posts' width
    # the posts: the corners, the bays along each side, the door's jambs
    xs = np.linspace(-hw, hw, 4)
    dy0, dw, dh = door
    posts = {(x, s * hd) for x in xs for s in (-1, 1)}
    posts |= {(-hw, 0.0), (hw, dy0 - dw / 2 - pw / 2), (hw, dy0 + dw / 2 + pw / 2)}
    posts = sorted(posts)
    for x, y in posts:
        P.box("post", (x, y, H / 2 - 0.08), (pw, pw, H - 0.16))
    # footings: a stone under each post, and short stilts where the bank falls away under the hut
    for x, y in posts + [(x, 0.0) for x in xs[1:-1]]:
        g = local_ground(x, y)
        top = max(g + 0.16, -sill - 0.55)
        if top < -sill - 0.02:
            P.box("post", (x, y, (top - sill) / 2), (0.12, 0.12, -sill - top))
        r = rng.uniform(0.15, 0.2)
        P.box("stone", (x, y, (g - 0.1 + top) / 2 + 0.0), (2 * r, 1.7 * r, top - g + 0.1),
              rot_z=rng.uniform(0, math.pi))
    # the sill (dodai) round the floor, and the floor's edge boards
    for s in (-1, 1):
        P.box("post", (0.0, s * hd, -sill / 2), (W + pw, pw, sill))
        P.box("post", (s * hw, 0.0, -sill / 2), (pw, D, sill))
    # the wall plates along x and the tie beams across them, their ends standing out past the corners
    for s in (-1, 1):
        P.box("post", (0.0, s * hd, H - 0.08), (W + 0.55, 0.16, 0.17))
    for x in xs:
        P.box("post", (x, 0.0, H - 0.27), (0.13, D + 0.5, 0.15))
    # the rail (nuki) round the walls between the boards below and the plaster above
    RAIL = 0.95
    for s in (-1, 1):
        P.box("post", (0.0, s * (hd + 0.035), RAIL), (W, 0.04, 0.08))
        P.box("post", (s * (hw + 0.035), 0.0, RAIL), (0.04, D, 0.08))

    # the walls: each bay between two posts. Boards: vertical, a little uneven, a batten on every other joint
    def boards(axis: int, side: int, a0: float, a1: float, z0: float, z1: float) -> None:
        a = a0
        k = 0
        while a < a1 - 0.03:
            w = min(rng.uniform(0.15, 0.2), a1 - a)
            out = side * (hd if axis == 0 else hw) + side * rng.uniform(0.0, 0.012)
            zt = z1 - rng.uniform(0.0, 0.02) if z1 < H - 0.3 else z1
            c = (a + w / 2, out, (z0 + zt) / 2) if axis == 0 else (out, a + w / 2, (z0 + zt) / 2)
            sz = (w - 0.006, 0.03, zt - z0) if axis == 0 else (0.03, w - 0.006, zt - z0)
            P.box("wall", c, sz)
            if k % 2 and a + w < a1 - 0.03:
                o = side * ((hd if axis == 0 else hw) + 0.025)
                c = (a + w, o, (z0 + z1) / 2) if axis == 0 else (o, a + w, (z0 + z1) / 2)
                P.box("wall", c, (0.035, 0.025, z1 - z0) if axis == 0 else (0.025, 0.035, z1 - z0))
            a += w
            k += 1

    def on_wall(axis: int, side: int, a: float, out: float, z: float) -> tuple:
        """A point on a wall (`axis` 0: along x at y = side * hd; 1: along y at x = side * hw), `out` outward."""
        return (a, side * (hd + out), z) if axis == 0 else (side * (hw + out), a, z)

    def wall_box(key: str, axis: int, side: int, a0: float, a1: float, out: float, z0: float, z1: float,
                 thick: float) -> None:
        c = on_wall(axis, side, (a0 + a1) / 2, out, (z0 + z1) / 2)
        P.box(key, c, (a1 - a0, thick, z1 - z0) if axis == 0 else (thick, a1 - a0, z1 - z0))

    def plaster(axis: int, side: int, a0: float, a1: float, z0: float, z1: float) -> None:
        holes = [w for w in windows if w[0] == axis and w[1] == side and a0 < (w[2] + w[3]) / 2 < a1]
        if not holes:
            wall_box("plaster", axis, side, a0, a1, 0.0, z0, z1, 0.06)
            return
        _, _, b0, b1, c0, c1, _ = holes[0]
        for p0, p1, q0, q1 in ((a0, b0, z0, z1), (b1, a1, z0, z1), (b0, b1, z0, c0), (b0, b1, c1, z1)):
            if p1 - p0 > 0.01 and q1 - q0 > 0.01:
                wall_box("plaster", axis, side, p0, p1, 0.0, q0, q1, 0.06)

    top = H - 0.17
    for s in (-1, 1):                                          # the long walls (along x)
        for a0, a1 in zip(xs[:-1], xs[1:]):
            a0, a1 = a0 + pw / 2, a1 - pw / 2
            boards(0, s, a0, a1, 0.0, RAIL - 0.04)
            plaster(0, s, a0, a1, RAIL + 0.04, top)
    ys = [y for x, y in posts if x == -hw]
    for a0, a1 in zip(ys[:-1], ys[1:]):                        # the back end (-x)
        boards(1, -1, a0 + pw / 2, a1 - pw / 2, 0.0, RAIL - 0.04)
        plaster(1, -1, a0 + pw / 2, a1 - pw / 2, RAIL + 0.04, top)
    ys = [y for x, y in posts if x == hw]
    for a0, a1 in zip(ys[:-1], ys[1:]):                        # the door's end (+x): boards and plaster round the door
        a0, a1 = a0 + pw / 2, a1 - pw / 2
        if a0 < dy0 < a1:
            plaster(1, 1, a0, a1, dh + 0.1, top)
            continue
        boards(1, 1, a0, a1, 0.0, RAIL - 0.04)
        plaster(1, 1, a0, a1, RAIL + 0.04, top)
    # the plaster weathered: in the front wall's left bay a patch fallen away to the bamboo lath under it
    lx, lz = (xs[0] + xs[1]) / 2 + 0.12, RAIL + 0.42
    ring = [(lx + 0.28 * math.cos(t) * rng.uniform(0.75, 1.15), lz + 0.2 * math.sin(t) * rng.uniform(0.7, 1.2))
            for t in np.linspace(0, math.tau, 9)[:-1]]
    yl = -hd - 0.033
    P.poly("lath", [(x, yl, z) for x, z in ring], [tuple(range(len(ring) - 1, -1, -1))])
    for k in range(5):
        P.box("rope", (lx - 0.2 + 0.1 * k, yl - 0.01, lz), (0.014, 0.012, 0.36))
    for k in range(3):
        P.box("rope", (lx, yl - 0.016, lz - 0.12 + 0.12 * k), (0.5, 0.012, 0.014))

    # the windows: barred with bamboo (renji), their paper glowing behind, a sill and a lintel, a rolled blind over
    # the ones that have one
    for axis, side, a0, a1, z0, z1, blind in windows:
        am = (a0 + a1) / 2
        wall_box("door", axis, side, a0, a1, -0.02, z0, z1, 0.01)
        wall_box("dark", axis, side, a0 - 0.02, a1 + 0.02, -0.035, z0 - 0.02, z1 + 0.02, 0.01)
        wall_box("post", axis, side, a0 - 0.08, a1 + 0.08, 0.04, z0 - 0.055, z0 - 0.005, 0.1)
        wall_box("post", axis, side, a0 - 0.08, a1 + 0.08, 0.035, z1, z1 + 0.06, 0.08)
        for a in (a0, a1):
            wall_box("post", axis, side, a - 0.025, a + 0.025, 0.01, z0, z1, 0.06)
        n = max(int((a1 - a0) / 0.085), 3)
        for k in range(1, n):
            a = a0 + (a1 - a0) * k / n
            P.cyl("lattice", on_wall(axis, side, a, 0.015, z0), on_wall(axis, side, a, 0.015, z1), 0.013, n=6)
        if blind:
            P.cyl("straw", on_wall(axis, side, a0 - 0.1, 0.1, z1 + 0.13), on_wall(axis, side, a1 + 0.1, 0.1, z1 + 0.13),
                  0.06, n=10)
            wall_box("straw", axis, side, a0 - 0.1, a1 + 0.1, 0.065, z1 - 0.02, z1 + 0.14, 0.012)
            for a in (a0 + 0.05, a1 - 0.05):
                P.cyl("rope", on_wall(axis, side, a, 0.165, z1 + 0.06), on_wall(axis, side, a, 0.165, z1 + 0.24),
                      0.008, n=5)
        lights.append((world(on_wall(axis, side, am, 0.25, (z0 + z1) / 2)),
                       world(on_wall(axis, side, am, 1.0, 0.0)) - world(on_wall(axis, side, am, 0.0, 0.0))))

    # the door: a sliding shoji in its frame, slid a hand's width open on the dark inside, lit through its paper
    xd = hw
    ya, yb = dy0 - dw / 2, dy0 + dw / 2
    P.box("post", (xd + 0.02, dy0, dh + 0.05), (0.1, dw + 0.3, 0.1))         # the lintel (kamoi)
    P.box("post", (xd + 0.03, dy0, 0.02), (0.12, dw + 0.1, 0.04))            # the threshold (shikii)
    gap = 0.12
    P.box("dark", (xd - 0.35, ya + gap / 2, dh / 2), (0.02, gap + 0.04, dh))
    P.box("door", (xd - 0.6, ya + gap / 2, dh * 0.45), (0.02, gap + 0.1, dh * 0.6))   # the hearth's light inside
    sa, sb = ya + gap, yb
    xs_ = xd - 0.02
    P.box("door", (xs_, (sa + sb) / 2, (dh + 0.3) / 2 + 0.02), (0.012, sb - sa, dh - 0.32))
    P.box("lattice", (xs_ + 0.005, (sa + sb) / 2, 0.17), (0.035, sb - sa, 0.3))         # its wooden foot (koshi)
    for y in (sa + 0.02, sb - 0.02):
        P.box("lattice", (xs_ + 0.01, y, dh / 2 + 0.02), (0.04, 0.04, dh - 0.02))
    P.box("lattice", (xs_ + 0.01, (sa + sb) / 2, dh - 0.01), (0.04, sb - sa, 0.04))
    for k in range(1, 4):
        y = sa + (sb - sa) * k / 4
        P.box("lattice", (xs_ + 0.01, y, (dh + 0.32) / 2), (0.022, 0.014, dh - 0.34))
    for k in range(1, 6):
        z = 0.32 + (dh - 0.34) * k / 6
        P.box("lattice", (xs_ + 0.01, (sa + sb) / 2, z), (0.022, sb - sa, 0.014))

    # the porch (along the door side): planks across on two bearers, on stilts down to stones on the bank
    if porch:
        px0, px1 = hw + 0.08, hw + 0.08 + porch
        for s in (-1, 1):
            P.box("wood", ((px0 + px1) / 2, s * (hd + 0.05), -0.12), (porch + 0.06, 0.1, 0.1))
        y = -hd - 0.1
        while y < hd + 0.1:
            w = rng.uniform(0.16, 0.2)
            P.box("wood", ((px0 + px1) / 2 + rng.uniform(-0.015, 0.015), y + w / 2, -0.04), (porch, w - 0.02, 0.05),
                  rot_z=rng.uniform(-0.015, 0.015))
            y += w
        for y in (-hd, 0.0, hd):
            g = local_ground(px1 - 0.06, y)
            P.box("post", (px1 - 0.06, y, (g - 0.17) / 2), (0.1, 0.1, -0.17 - g))
            P.box("stone", (px1 - 0.06, y, g + 0.03), (0.28, 0.24, 0.16), rot_z=rng.uniform(0, math.pi))
        # a step down at its -y end, toward the jetty's foot
        g = local_ground(px0 + porch / 2, -hd - 0.5)
        P.box("stone", (px0 + porch / 2, -hd - 0.42, (g + min(-0.22, g + 0.25)) / 2),
              (0.5, 0.36, max(min(-0.22, g + 0.25) - g, 0.08)), rot_z=0.08)

    # the roof: a hip-and-gable thatch, thick, with a stepped cut edge
    X, Y = hw + overhang, hd + overhang
    ze = H + 0.14
    zt = H + peak
    verts, faces, rp = hip_gable_roof(X, Y, ze, zt)
    P.poly("thatch", verts, faces[:4])
    # courses: each a step in the thatch where one layer of straw ends over the next, its foot ragged
    slope = (zt - ze) / Y
    for f in (0.3, 0.56):
        u = f / (1 - 0.45)
        zc = ze + f * (zt - ze)
        xc, yc = X - u * (X - rp["xr"]), Y * (1 - f)
        ring = [np.array((sx * xc, sy * yc, zc)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        for a, b in zip(ring, ring[1:] + ring[:1]):
            mid = (a + b) / 2
            out = np.array((mid[0], mid[1], 0.0))
            out = out / np.linalg.norm(out)
            n = out * slope + np.array((0.0, 0.0, 1.0))         # the face's normal (slope and hip alike)
            n /= np.linalg.norm(n)
            down = out - np.array((0.0, 0.0, slope))             # down the slope
            down /= np.linalg.norm(down)
            k = max(int(np.linalg.norm(b - a) / 0.08), 2)
            vs = []
            for j in range(k + 1):
                p = a + (b - a) * j / k
                drop = 0.08 + 0.07 * rng.uniform() ** 2 if 0 < j < k else 0.08
                vs += [p + 0.004 * n, p + 0.05 * n, p + 0.05 * n + drop * down, p + 0.004 * n + drop * 1.15 * down]
            fs = []
            for j in range(k):
                i0, i1 = 4 * j, 4 * (j + 1)
                fs += [(i0 + 2, i1 + 2, i1 + 1, i0 + 1), (i0 + 3, i1 + 3, i1 + 2, i0 + 2)]
            P.poly("thatch_edge", vs, fs)
    # the gables: dark smoke gaps, a few slats across each
    for sx in (-1, 1):
        g = [verts[i] for i in faces[4 + (0 if sx > 0 else 1)]]
        g = [(p[0] - sx * 0.12, p[1], p[2]) for p in g]
        P.poly("dark", g, [(0, 1, 2)])
        xr, yg, zg = rp["xr"] - 0.1, rp["yg"], rp["zg"]
        for k in range(-3, 4):
            yk = yg * k / 4
            zk = zg + (zt - zg) * (1 - abs(k) / 4) - 0.05
            P.box("lattice", (sx * xr, yk, (zg + zk) / 2), (0.03, 0.04, max(zk - zg, 0.04)))
        P.box("post", (sx * xr, 0.0, zg - 0.02), (0.06, 2 * yg + 0.1, 0.06))
    # its eave: rounded over from the slope into a thick cut edge, then a second layer set back under it, its foot
    # ragged where the straw ends hang unevenly
    def rings(key: str, chain, ragged: float = 0.0) -> None:
        """Rings round the eave, each (inset, z), top to bottom, joined in a band; the last ragged."""
        corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        loops = [[] for _ in chain]
        for (sx, sy), (tx, ty) in zip(corners, corners[1:] + corners[:1]):
            n = max(int(max(abs(tx - sx) * X, abs(ty - sy) * Y) / 0.09), 1) if ragged else 1
            for j in range(n):
                f = j / n
                cx, cy = sx + (tx - sx) * f, sy + (ty - sy) * f
                for r, (inset, z) in enumerate(chain):
                    drop = ragged * (rng.uniform(0.0, 1.0) ** 2 if j else 0.6) if r == len(chain) - 1 else 0.0
                    loops[r].append((cx * (X - inset), cy * (Y - inset), z - drop))
        k = len(loops[0])
        vs = [p for loop in loops for p in loop]
        fs = [tuple(reversed((r * k + i, r * k + (i + 1) % k, (r + 1) * k + (i + 1) % k, (r + 1) * k + i)))
              for r in range(len(chain) - 1) for i in range(k)]
        P.poly(key, vs, fs)
    lip = 0.2
    rings("thatch", [(lip, ze + lip * slope + 0.03), (0.07, ze + 0.07 * slope + 0.05), (-0.02, ze - 0.02)])
    rings("thatch_edge", [(-0.02, ze - 0.02), (-0.025, ze - 0.12), (0.0, ze - 0.24), (0.08, ze - 0.26),
                          (0.13, ze - 0.44)], ragged=0.07)
    # under the eaves: the thatch's underside, rising from the cut edge to the walls, bamboo rafters along it
    zu = ze - 0.42
    zs_t = zt - 0.6
    sv, sf, _ = hip_gable_roof(X - 0.14, Y - 0.14, zu, zs_t)
    P.poly("thatch", sv, [tuple(reversed(f)) for f in sf[:4]])

    def soffit(d):                       # its height `d` in from the cut edge
        return zu + d * (zs_t - zu) / (Y - 0.14) - 0.035

    for s in (-1, 1):
        for x in np.arange(-X + 0.35, X - 0.3, 0.32):
            P.cyl("lattice", (x, s * (hd - 0.1), soffit(Y - hd - 0.04)), (x, s * (Y - 0.2), soffit(0.06)), 0.02, n=6)
        for y in np.arange(-Y + 0.45, Y - 0.4, 0.32):
            P.cyl("lattice", (s * (hw - 0.1), y, soffit(X - hw - 0.04)), (s * (X - 0.2), y, soffit(0.06)), 0.02, n=6)
    # the ridge: a rounded bundle of straw capped in bark along its length, a bamboo pole on it, saddled by crossed
    # pieces, ending just past the gables
    rl = 2 * rp["xr"] + 0.12
    P.cyl("ridge", (-rl / 2, 0.0, zt - 0.04), (rl / 2, 0.0, zt - 0.04), 0.14, n=10)
    P.cyl("lattice", (-rl / 2 - 0.05, 0.0, zt + 0.11), (rl / 2 + 0.05, 0.0, zt + 0.11), 0.03, n=6)
    for k in range(7):
        x = -rl / 2 + 0.2 + (rl - 0.4) * k / 6
        for s in (-1, 1):
            P.beam("post", (x, s * 0.03, zt + 0.16), (x, s * 0.26, zt - 0.12), 0.05)

    # the lived-in clutter, as `clutter` asks
    if clutter:
        # firewood: split logs stacked under the front eave, in the bay left of the window, on two rails
        fx0, fx1 = xs[0] + 0.15, xs[1] - 0.12
        P.box("wood", ((fx0 + fx1) / 2, -hd - 0.25, 0.03), (fx1 - fx0 + 0.1, 0.38, 0.06))
        for row in range(5):
            n = 7 - (row % 2)
            for k in range(n):
                r = rng.uniform(0.055, 0.07)
                x = fx0 + (fx1 - fx0) * (k + 0.5 + 0.5 * (row % 2)) / 7.5
                z = 0.12 + row * 0.12
                P.cyl("wood", (x + rng.uniform(-0.02, 0.02), -hd - 0.06, z),
                      (x, -hd - 0.46 + rng.uniform(-0.03, 0.03), z), r, n=6)
        # the rain barrel by the porch's far end, under the eave's corner, brimming
        bx, by = hw - 0.25, hd + 0.42
        gb = max(local_ground(bx, by), -0.6)
        prof = [(0.0, 0.0), (0.24, 0.0), (0.27, 0.25), (0.25, 0.52), (0.235, 0.52), (0.255, 0.25), (0.22, 0.04),
                (0.0, 0.04)]
        ring = 12
        vs = [(r * math.cos(math.tau * j / ring) + bx, r * math.sin(math.tau * j / ring) + by, z + gb)
              for r, z in prof for j in range(ring)]
        P.poly("wood", vs, shapes.tube_faces(len(prof), ring, cap=False))
        for z in (0.1, 0.42):
            P.cyl("rope", (bx, by, gb + z - 0.02), (bx, by, gb + z + 0.02), 0.265, n=12)
        P.cyl("glass", (bx, by, gb + 0.46), (bx, by, gb + 0.47), 0.235, n=12)
        P.cyl("wood", (bx + 0.05, by - 0.05, gb + 0.48), (bx + 0.32, by - 0.25, gb + 0.6), 0.012, n=5)
        # oars leaning on the front wall by the door's corner
        for k, (x, lean) in enumerate(((xs[2] + 0.2, 0.18), (xs[2] + 0.45, 0.26))):
            g = local_ground(x, -hd - 0.4)
            a = np.array((x, -hd - 0.08 - lean, max(g, -0.15)))
            b = np.array((x - 0.12 * (k + 1), -hd - 0.06, H - 0.1))
            P.cyl("wood", a + 0.18 * (b - a), b, 0.022, n=6)
            P.beam("wood", a, a + 0.25 * (b - a), 0.1, 0.02, up=(0.0, 1.0, 0.0))
        # a fishing net drying on a bamboo rack off the back end, sagging between its poles
        nx, ny0, ny1, top_ = -hw - 0.55, 0.15, 1.45, 1.75
        for y in (ny0, ny1):
            g = local_ground(nx, y)
            P.cyl("lattice", (nx, y, g - 0.1), (nx, y, top_ + 0.08), 0.025, n=6)
        P.cyl("lattice", (nx, ny0 - 0.12, top_), (nx, ny1 + 0.12, top_), 0.02, n=6)
        g = max(local_ground(nx, (ny0 + ny1) / 2), -0.4)

        def net(y, z):                          # the net's drape: sagging between the poles, its foot swaying out
            f = (y - ny0) / (ny1 - ny0)
            h = (top_ - z) / (top_ - g - 0.35)
            return (nx + 0.06 * h * h + 0.02 * math.sin(7 * f), y, z - 0.12 * math.sin(math.pi * f) * (1 - h))

        ys_ = np.linspace(ny0 + 0.05, ny1 - 0.05, 12)
        zs_ = np.linspace(top_ - 0.02, g + 0.35, 9)
        for y in ys_:
            for z0_, z1_ in zip(zs_[:-1], zs_[1:]):
                P.cyl("rope", net(y, z0_), net(y, z1_), 0.006, n=4)
        for z in zs_[1:]:
            for y0_, y1_ in zip(ys_[:-1], ys_[1:]):
                P.cyl("rope", net(y0_, z), net(y1_, z), 0.006, n=4)
        for y in ys_[::2]:                      # its floats along the hem
            P.cyl("wood", net(y, zs_[-1] - 0.02), net(y, zs_[-1] + 0.04), 0.03, n=6)
        # a straw cape (mino) and a spare hat hung on pegs by the door
        mx, my = hw + 0.05, yb + 0.42
        P.cyl("post", (mx - 0.05, my, 1.62), (mx + 0.12, my, 1.62), 0.015, n=5)
        for tier in range(3):                  # three layers of straw, each overlapping the one below
            z0, z1 = 1.6 - 0.24 * tier, 1.6 - 0.24 * tier - 0.36
            r0, r1 = 0.12 + 0.08 * tier, 0.2 + 0.09 * tier
            n = 14
            vs = []
            for j in range(n + 1):
                a = math.pi * (j / n - 0.5)
                vs.append((mx + 0.04 + 0.4 * r0 * math.cos(a) + 0.02 * tier, my + r0 * math.sin(a), z0))
            for j in range(n + 1):
                a = math.pi * (j / n - 0.5)
                vs.append((mx + 0.04 + 0.45 * r1 * math.cos(a) + 0.02 * tier, my + r1 * math.sin(a),
                           z1 + (0.05 if j % 2 else 0.0) + rng.uniform(-0.02, 0.02)))
            P.poly("straw", vs, [(j, j + 1, n + 2 + j, n + 1 + j) for j in range(n)])
            # the straw's ends hanging past each tier's hem, uneven
            ends = [np.asarray(vs[n + 1 + j]) for j in range(0, n + 1, 1)]
            _spikes(P, "straw", [e + (0.004, 0.0, 0.03) for e in ends],
                    [e + (0.01 + 0.02 * tier, rng.uniform(-0.02, 0.02), -rng.uniform(0.05, 0.14)) for e in ends],
                    [0.022] * len(ends))
        hx_, hy_ = hw + 0.06, yb + 0.95
        prof = [(0.0, 0.14), (0.08, 0.11), (0.2, 0.05), (0.3, 0.0), (0.3, -0.01), (0.0, 0.12)]
        kv = []
        for r, z in prof:
            for j in range(16):
                a = math.tau * j / 16
                kv.append((hx_ + 0.04 + z, hy_ + r * math.cos(a), 1.45 + r * math.sin(a)))
        P.poly("straw", kv, shapes.tube_faces(len(prof), 16, cap=False))

    obs = P.emit(prefix, m, coll, world)
    eave = world((hw + 0.35, -hd - 0.1, H))
    edges = []
    for (ax, ay), (bx_, by_) in (((-X, -Y), (X, -Y)), ((X, -Y), (X, Y)), ((-X, Y), (X, Y)), ((-X, -Y), (-X, Y))):
        a = world((ax + 0.08 * np.sign(bx_ - ax), ay + 0.08 * np.sign(by_ - ay), zu - 0.01))
        b = world((bx_ - 0.08 * np.sign(bx_ - ax), by_ - 0.08 * np.sign(by_ - ay), zu - 0.01))
        edges.append((tuple(a), tuple(b)))
    return {"objects": obs, "eave": tuple(eave), "door": tuple(world((hw + 0.02, dy0, 0.0))), "eave_edges": edges,
            "windows": [(tuple(p), tuple(d / np.linalg.norm(d))) for p, d in lights],
            "smoke": [tuple(world((s * rp["xr"], 0.0, zt))) for s in (-1, 1)]}


def _spikes(P: Parts, key: str, roots, tips, widths, sides: int = 3) -> None:
    for r0, t0, w in zip(np.asarray(roots, float), np.asarray(tips, float), widths):
        d = t0 - r0
        d /= np.linalg.norm(d)
        a = np.cross(d, (0, 0, 1))
        if np.linalg.norm(a) < 1e-6:
            a = np.cross(d, (1, 0, 0))
        a /= np.linalg.norm(a)
        b = np.cross(d, a)
        vs = [r0 + w * (math.cos(math.tau * j / sides) * a + 0.5 * math.sin(math.tau * j / sides) * b)
              for j in range(sides)] + [t0]
        P.poly(key, vs, [(j, (j + 1) % sides, sides) for j in range(sides)])


def chochin_profile(radius: float, height: float, ribs: int) -> list:
    """A round chochin's body, [(radius, z), ...] bottom to top about its middle: a squashed sphere between its caps'
    openings, pinched a little at each of its `ribs` bamboo hoops."""
    h = height / 2
    out = []
    for k in range(ribs * 2 + 1):
        t = -1 + k / ribs                       # -1 .. 1, even k on a hoop
        z = h * t
        r = radius * math.sqrt(max(1 - (0.92 * t) ** 2, 0.0)) * 0.94 + radius * 0.06
        out.append((r * (1.0 if k % 2 else 0.975), z))
    return out


def chochin(name: str, m: dict, coll, center, *, radius: float = 0.16, height: float = 0.44, ribs: int = 13,
            cord_top: float | None = None) -> tuple:
    """A red paper lantern (chochin) at `center`: its paper body on bamboo hoops (`ribs` of them, a darker line round
    it at each), black lacquered caps top and bottom, a bail over the top cap and a cord up to `cord_top` when given.
    `m`: lantern (the paper: an emitting material), as it has them cap, rib (else FALLBACK), rope (the cord). Its
    origin is at its middle (a swing's pivot, a focus target). Returns (body, [every object])."""
    import bpy

    prof = chochin_profile(radius, height, ribs)
    body = shapes.lathe(name, prof, material=material(m, "lantern"), coll=coll, n=20)
    body.location = center
    h = height / 2
    P = Parts()
    for k in range(0, len(prof), 2):
        r, z = prof[k]
        if r < radius * 0.5:
            continue
        P.cyl("rib", (0, 0, z - 0.0035), (0, 0, z + 0.0035), r + 0.003, n=20)
    rc = radius * 0.6
    for s in (-1, 1):
        z = s * (h - 0.01)
        P.cyl("cap", (0, 0, z - 0.03), (0, 0, z + 0.03), rc, n=16)
        P.cyl("cap", (0, 0, z + s * 0.03), (0, 0, z + s * 0.045), rc * 0.8, n=16)
    # the bail: a thin arc over the top cap
    arc = [(rc * 0.7 * math.cos(t), 0.0, h + 0.035 + 0.06 * math.sin(t)) for t in np.linspace(0, math.pi, 7)]
    for a, b in zip(arc[:-1], arc[1:]):
        P.beam("cap", a, b, 0.008)
    obs = [body]
    for ob in P.emit(name, m, coll, lambda V: V):
        ob.parent = body
        obs.append(ob)
    if cord_top is not None:
        cord = shapes.cylinder(f"{name}-cord", (0, 0, h + 0.09), (0, 0, cord_top - center[2]), 0.006,
                               material=material(m, "rope"), coll=coll, n=6)
        cord.parent = body
        obs.append(cord)
    sub = body.modifiers.new("round", "SUBSURF")
    sub.levels = sub.render_levels = 1
    bpy.context.view_layer.update()
    return body, obs


def paper_glow(name: str, color, *, look=None, strength: float = 1.0, core: float = 1.6, edge: float = 0.45,
               height: float = 0.44, fog: bool = True):
    """Lit paper (a lantern's): `color` glowing at `strength`, hotter at its middle (`core` times) and dimmer toward
    its top and bottom (`edge` times), by height in the object's own frame over `height`. Faded to the fog."""
    import bpy

    from . import toon

    look = look or toon.Look()
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    ab = nt.nodes.new("ShaderNodeMath")
    ab.operation = "ABSOLUTE"
    nt.links.new(sep.outputs["Z"], ab.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.interpolation_type = "SMOOTHSTEP"
    mr.inputs["From Min"].default_value = 0.0
    mr.inputs["From Max"].default_value = height / 2
    mr.inputs["To Min"].default_value = core
    mr.inputs["To Max"].default_value = edge
    nt.links.new(ab.outputs[0], mr.inputs["Value"])
    rgb = nt.nodes.new("ShaderNodeRGB")
    rgb.outputs[0].default_value = (*color, 1.0)
    col = toon._fog_mix(nt, rgb.outputs[0], look) if fog else rgb.outputs[0]
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = strength
    nt.links.new(mr.outputs["Result"], gain.inputs[0])
    nt.links.new(gain.outputs[0], em.inputs["Strength"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def smoke(name: str, coll, base, *, height: float = 2.6, width=(0.12, 1.1), color=(0.62, 0.64, 0.68),
          density: float = 0.4, rise: float = 0.35, sway: float = 0.35, lean=(0.25, 0.0), look=None, scene=None,
          seed: float = 0.0):
    """Thin hearth smoke from a smoke gap at `base`: two crossed cards `height` tall (seen from any side), a wisp
    widening from width[0] to width[1] as it climbs, swaying, broken by noise rising `rise` m/s, fading in above the
    gap and out at its top, leaning `lean` (m at its top, x and y) with the wind. Driven by the scene's clock (a
    shader: no bake). Returns the objects."""
    import bpy

    from . import toon

    scene = scene or bpy.context.scene
    look = look or toon.Look()
    w = width[1] / 2
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    N, L = nt.nodes, nt.links

    def math_(op, a, b=None):
        m = N.new("ShaderNodeMath")
        m.operation = op
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = v
            else:
                L.new(v, m.inputs[i])
        return m.outputs[0]

    def ramp(v, a, b):
        m = N.new("ShaderNodeMapRange")
        m.interpolation_type = "SMOOTHSTEP"
        m.inputs["From Min"].default_value, m.inputs["From Max"].default_value = a, b
        L.new(v, m.inputs["Value"])
        return m.outputs["Result"]

    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Object"], sep.inputs[0])
    t = toon.frame_value(nt, scene)
    u, z = sep.outputs["X"], sep.outputs["Z"]
    zn = math_("DIVIDE", z, height)
    # the wisp's middle sways more the higher it gets; its half-width grows
    wave = math_("SINE", math_("ADD", math_("MULTIPLY", zn, 5.0), math_("MULTIPLY", t, 0.9)))
    wave2 = math_("SINE", math_("ADD", math_("MULTIPLY", zn, 11.0), math_("MULTIPLY", t, -1.7)))
    mid = math_("MULTIPLY", math_("MULTIPLY", zn, sway), math_("ADD", wave, math_("MULTIPLY", wave2, 0.35)))
    lean_x = N.new("ShaderNodeAttribute")          # the card's own lean across it (its "smoke_lean")
    lean_x.attribute_type = "OBJECT"
    lean_x.attribute_name = "smoke_lean"
    mid = math_("ADD", mid, math_("MULTIPLY", lean_x.outputs["Fac"], math_("MULTIPLY", zn, zn)))
    half = math_("ADD", width[0] / 2, math_("MULTIPLY", zn, w - width[0] / 2))
    across = math_("ABSOLUTE", math_("DIVIDE", math_("SUBTRACT", u, mid), half))
    prof = math_("SUBTRACT", 1.0, ramp(across, 0.25, 1.0))
    # torn by noise drifting up with it
    comb = N.new("ShaderNodeCombineXYZ")
    L.new(math_("MULTIPLY", u, 2.5), comb.inputs["X"])
    L.new(math_("SUBTRACT", math_("MULTIPLY", z, 1.4), math_("MULTIPLY", t, rise * 1.4)), comb.inputs["Y"])
    L.new(math_("ADD", math_("MULTIPLY", t, 0.08), seed), comb.inputs["Z"])
    noise = N.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.6
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.55
    L.new(comb.outputs[0], noise.inputs["Vector"])
    torn = ramp(noise.outputs["Fac"], 0.4, 0.68)
    fade = math_("MULTIPLY", ramp(zn, 0.0, 0.12), math_("SUBTRACT", 1.0, ramp(zn, 0.45, 1.0)))
    a = math_("MULTIPLY", math_("MULTIPLY", math_("MULTIPLY", prof, torn), fade), density)
    rgb = N.new("ShaderNodeRGB")
    rgb.outputs[0].default_value = (*color, 1.0)
    em = N.new("ShaderNodeEmission")
    L.new(toon.flashed(nt, toon._fog_mix(nt, rgb.outputs[0], look), (1.0, 1.0, 1.0), 0.6), em.inputs["Color"])
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    L.new(a, mx.inputs["Fac"])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    out = N.new("ShaderNodeOutputMaterial")
    L.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    obs = []
    lx, ly = lean
    for k, turn in enumerate((0.0, math.pi / 2)):
        # each card turned as an object, so the shader's x (its own frame's) runs across the wisp on both
        llx, lly, _ = shapes.rot_z(-turn) @ np.array((lx, ly, 0.0))
        rows = 8
        vs = []
        for i in range(rows + 1):
            f = i / rows
            for x in (-w * 1.2, w * 1.2):
                vs.append((x + llx * f * f, lly * f * f, f * height))
        fs = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(rows)]
        ob = shapes.mesh_object(f"{name}{k}", vs, fs, mat, coll, smooth=False)
        ob.location = base
        ob.rotation_euler = (0.0, 0.0, turn)
        ob["smoke_lean"] = float(llx)
        ob.visible_shadow = False
        obs.append(ob)
    return obs
