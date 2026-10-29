"""Landscape from code for anime and ink-wash shots: mountain ridges as layered silhouettes, pines, a sloping bank with
grass along its edge, a river, a sky card and banks of mist between the ridges.

An ink-wash distance is ridge after ridge of flat silhouettes, each paler than the one before; with toon materials
(toon.cel / toon.flat) the fog does the paling, so every ridge can be the same dark ink. World axes as the shots use
them: z up, a camera at -y looking toward +y across the land.

`ridge_profile` (the heights) and `bank_height` are numpy only and tested without Blender; the builders need it.
"""
from __future__ import annotations

import math

import numpy as np

from . import shapes


def ridge_profile(xs: np.ndarray, distance: float, height: float, seed: int, *, trees: float = 0.0,
                  sharp: float = 0.0) -> np.ndarray:
    """The crest's height (m) at each x of a ridge `distance` away: rolling summits about `height`, one higher peak,
    with `sharp` pointed peaks rising up to that share of `height` over them (an ink painting's crags), and with
    `trees` (m) a fringe of tree tips along it. Deterministic in `seed`."""
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 100)
    k = 2 * math.pi / (distance * 0.9)
    h = 0.55 * np.sin(xs * k * 0.7 + ph) + 0.3 * np.sin(xs * k * 1.9 + 2 * ph) + 0.15 * np.sin(xs * k * 4.3 + 3 * ph)
    h = height * (0.55 + 0.45 * h) + height * 0.25 * np.exp(-((xs - rng.uniform(-0.5, 0.5) * distance) / (0.25 * distance)) ** 2)
    if sharp:
        h = h + sharp * height * (1 - np.abs(np.sin(xs * k * 1.35 + 4 * ph))) ** 3 * (0.6 + 0.4 * np.sin(xs * k * 0.5 + ph))
    if trees:
        h = h + trees * np.abs(np.sin(xs * 7.3 / max(trees, 1e-3))) * rng.uniform(0.6, 1.0, len(xs))
    return h


def ridge(name: str, material, coll, distance: float, height: float, *, seed: int = 1, width: float = 1.6, trees: float = 0.0,
          base_z: float = -2.0, n: int = 240, sharp: float = 0.0):
    """A ridge's silhouette across the view at y = `distance`, `width` times as wide as it is far, as a curtain down to
    `base_z`."""
    xs = np.linspace(-width * distance, width * distance, n)
    h = ridge_profile(xs, distance, height, seed, trees=trees, sharp=sharp)
    verts = [(x, distance + 0.02 * distance * math.sin(x * 0.01), z) for x, z in zip(xs, h)]
    verts += [(x, distance, base_z) for x in xs]
    faces = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    return shapes.mesh_object(name, verts, faces, material, coll, smooth=False)


def pine(name: str, base, height: float, *, trunk, needles, coll, seed: int = 1, clumps: int = 7) -> list:
    """A pine as ink paintings draw one: a leaning trunk, branches reaching out from it, and on each a flat cloud of
    needles (an uneven, flattened clump), the top clump crowning the trunk."""
    rng = np.random.default_rng(seed)
    bx, by, bz = base
    lean = np.array([rng.normal(0, 0.12), rng.normal(0, 0.06), 1.0])
    top = np.array([bx, by, bz]) + lean / np.linalg.norm(lean) * height
    obs = [shapes.cylinder(f"{name}-trunk", (bx, by, bz - 0.5), tuple(top), 0.17 * height / 8, material=trunk, coll=coll, n=8, r2=0.05)]
    for c in range(clumps):
        f = 0.35 + 0.6 * c / max(1, clumps - 1)
        at = np.array([bx, by, bz]) + (top - np.array([bx, by, bz])) * f
        ang = rng.uniform(0, 2 * math.pi)
        reach = height * (0.3 - 0.22 * f) * rng.uniform(0.7, 1.2)
        tip = at + np.array([math.cos(ang) * reach, math.sin(ang) * reach * 0.6, reach * 0.15])
        if c < clumps - 1:
            obs.append(shapes.cylinder(f"{name}-branch{c}", tuple(at), tuple(tip), 0.05 * height / 8, material=trunk, coll=coll, n=6, r2=0.015))
        else:
            tip = top + np.array([0, 0, height * 0.03])
        r = height * (0.16 - 0.08 * f) * rng.uniform(0.8, 1.2)
        obs.append(shapes.ellipsoid(f"{name}-clump{c}", tuple(tip), (r * 1.25, r * rng.uniform(0.7, 1.0), r * 0.38), material=needles, coll=coll, n=10,
                                    squash=lambda v, s=c: v * (1 + 0.12 * np.sin(v[:, :1] * 7 + s) * np.cos(v[:, 1:2] * 5))))
    return obs


def bank_edge(y: float, edge: float) -> float:
    """Where the bank meets the water at depth y: a shoreline wandering about x = `edge`."""
    return edge + 0.8 * math.sin(y * 0.35) + 0.4 * math.sin(y * 0.9 + 1)


def bank_height(x: float, y: float, edge: float, water_z: float, rise: float = 0.85, slope: float = 2.6) -> float:
    """The bank's height at (x, y): the water's level at its edge, rising `rise` over `slope` metres inland (toward -x),
    rolling a little."""
    h = float(np.clip((bank_edge(y, edge) - x) / slope, 0, 1))
    return water_z - 0.05 + rise * h + 0.25 * h * math.sin(x * 0.7 + y * 0.3)


def bank(name: str, *, ground, grass, coll, edge: float, water_z: float, x0: float = -26.0, y_range=(-9.0, 40.0), tufts: int = 260,
         seed: int = 1) -> list:
    """A muddy bank rising out of the water along x < `edge`, tufts of grass along it."""
    rng = np.random.default_rng(seed)
    xs = np.linspace(x0, edge + 0.4, 30)
    ys = np.linspace(*y_range, 30)
    verts = [(x, y, bank_height(x, y, edge, water_z)) for y in ys for x in xs]
    n = len(xs)
    faces = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i) for j in range(len(ys) - 1) for i in range(n - 1)]
    obs = [shapes.mesh_object(name, verts, faces, ground, coll, smooth=True)]
    roots, tips, widths = [], [], []
    for _ in range(tufts):
        y = rng.uniform(y_range[0] + 1, min(y_range[1], 22))
        x = bank_edge(y, edge) - rng.uniform(0.2, 3.5)
        r0 = np.array([x, y, bank_height(x, y, edge, water_z) - 0.02])
        roots.append(r0)
        tips.append(r0 + np.array([rng.normal(0.05, 0.1), rng.normal(0, 0.08), rng.uniform(0.25, 0.6)]))
        widths.append(rng.uniform(0.02, 0.04))
    obs.append(shapes.spikes(f"{name}-grass", roots, tips, widths, material=grass, coll=coll, sides=3))
    return obs


def river(name: str, material, coll, *, z: float, size=(1600.0, 700.0), center_y: float = 300.0):
    """The water: one big plane at height z."""
    import bpy

    from . import toon

    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, center_y, z))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], 1)
    ob.data.materials.append(material)
    ob.visible_shadow = False
    return toon.move_to(ob, coll)


def sky(name: str, coll, *, horizon, zenith, distance: float = 1200.0, size=(5000.0, 900.0), z: float = 250.0,
        flash=(0.9, 0.93, 1.0), flash_amount: float = 0.9):
    """A far card of sky in its own colour (no fog): `horizon` at its foot to `zenith` at its top, whitening toward
    `flash` with the scene's lightning (toon.FLASH; None: it never flashes)."""
    import bpy

    from . import toon

    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, distance, z), rotation=(math.pi / 2, 0, 0))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], 1)
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (*horizon, 1)
    mix.inputs["B"].default_value = (*zenith, 1)
    nt.links.new(sep.outputs["Y"], mix.inputs["Factor"])
    col = mix.outputs["Result"] if flash is None else toon.flashed(nt, mix.outputs["Result"], flash, flash_amount)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    ob.data.materials.append(mat)
    ob.visible_shadow = False
    return toon.move_to(ob, coll)


def mist_layers(coll, color, layers, *, base_z: float = 0.0, density: float = 0.75) -> list:
    """Banks of mist between ridges: `layers` is [(distance, height, width), ...]; each drifts at its own speed."""
    from . import toon

    obs = []
    for k, (d, h, w) in enumerate(layers):
        card = toon.mist_card(f"mist{k}", (0, d, base_z + h * 0.35), (w, h), color, density=density, drift=0.8 + 0.3 * k, seed=k * 3.1)
        obs.append(toon.move_to(card, coll))
    return obs


# ---- terrain, forests and valleys: the wider world round a set ----

def grid_faces(nx: int, ny: int) -> list[tuple[int, int, int, int]]:
    """The quads of an nx-by-ny grid of points numbered row by row (x fastest), facing +z when x and y increase."""
    return [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]


def heightfield(name: str, height, x_range, y_range, *, material, coll, step: float = 1.0, smooth: bool = True):
    """Ground from a height function: `height(X, Y)` (numpy arrays in, heights out) sampled every `step` metres over
    the ranges, as one mesh."""
    xs = np.arange(x_range[0], x_range[1] + step * 0.5, step)
    ys = np.arange(y_range[0], y_range[1] + step * 0.5, step)
    X, Y = np.meshgrid(xs, ys)
    Z = np.asarray(height(X, Y), float)
    verts = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    ob = shapes.mesh_object(name, verts, grid_faces(len(xs), len(ys)), material, coll, smooth=smooth)
    return ob


def fbm(X, Y, *, seed: int = 1, octaves: int = 4, scale: float = 50.0) -> np.ndarray:
    """Rolling value noise (-1..1 roughly) over x, y in metres, features about `scale` across: sums of sines at
    seeded angles and phases, each octave half the size and half the height. Deterministic in `seed`."""
    rng = np.random.default_rng(seed)
    X, Y = np.asarray(X, float), np.asarray(Y, float)
    out = np.zeros(np.broadcast(X, Y).shape)
    amp, k, norm = 1.0, 2 * math.pi / scale, 0.0
    for _ in range(octaves):
        for _ in range(3):
            a = rng.uniform(0, math.pi)
            out = out + amp / 3 * np.sin(k * (X * math.cos(a) + Y * math.sin(a)) + rng.uniform(0, 2 * math.pi))
        norm += amp
        amp *= 0.5
        k *= 2.03
    return out / norm


def conifer_mesh(base, height: float, *, seed: int = 1, tiers: int = 5, sides: int = 7, spread: float = 0.28,
                 lean: float = 0.04) -> tuple[np.ndarray, list]:
    """(verts, faces) of a conifer as ink paintings stack one (a cedar or a fir): a thin trunk, then `tiers` skirts of
    needles, each a low cone drooping from the trunk with a ragged hem, wider below (`spread` of the height across at
    the widest), up to a spire. Few faces: a forest is thousands of these in one mesh."""
    rng = np.random.default_rng(seed)
    bx, by, bz = base
    lx, ly = rng.normal(0, lean, 2)
    verts, faces = [], []

    def axis(z):
        f = (z - bz) / height
        return bx + lx * height * f, by + ly * height * f

    # trunk: a thin square prism up to where the skirts begin
    t0 = 0.16 * height
    r = 0.012 * height
    for z in (bz - 0.3, bz + t0 + 0.05 * height):
        ax, ay = axis(z)
        verts += [(ax + r * math.cos(a), ay + r * math.sin(a), z) for a in (0.0, math.pi / 2, math.pi, 1.5 * math.pi)]
    faces += [(i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i) for i in range(4)]
    for t in range(tiers):
        f = t / max(1, tiers - 1)
        z_hem = bz + t0 + (height - t0) * 0.7 * f
        z_top = bz + height if t == tiers - 1 else z_hem + (height - t0) * (0.42 - 0.12 * f)
        w = spread * height * (1.0 - 0.8 * f) * rng.uniform(0.85, 1.15)
        ax, ay = axis(z_top)
        tip = len(verts)
        verts.append((ax, ay, z_top))
        hx, hy = axis(z_hem)
        ring = len(verts)
        ph = rng.uniform(0, 2 * math.pi)
        for s in range(sides):
            a = ph + 2 * math.pi * s / sides
            rr = w * rng.uniform(0.75, 1.1)
            verts.append((hx + rr * math.cos(a), hy + rr * math.sin(a), z_hem - rng.uniform(0.0, 0.06) * height))
        for s in range(sides):
            faces.append((tip, ring + s, ring + (s + 1) % sides))
        faces.append(tuple(ring + s for s in range(sides - 1, -1, -1)))
    return np.array(verts, float), faces


def cedar_mesh(base, height: float, *, seed: int = 1, clumps: int = 12, sides: int = 8, spread: float = 0.2,
               bare: float = 0.32, lean: float = 0.03) -> tuple[np.ndarray, list]:
    """(verts, faces) of a Japanese cedar (sugi) as an ink painting draws one: a tall straight trunk bare for its
    lowest `bare` of the height, then a narrow crown of `clumps` flat, ragged clouds of needles stacked up it (each
    off the trunk to one side or the other, their edges drooping), smaller as they climb to a thin spire. Low in
    faces: a forest is thousands of them in one mesh."""
    rng = np.random.default_rng(seed)
    bx, by, bz = base
    lx, ly = rng.normal(0, lean, 2)
    verts, faces = [], []

    def axis(z):
        f = (z - bz) / height
        return bx + lx * height * f, by + ly * height * f

    r = 0.011 * height
    for z, rr in ((bz - 0.3, r), (bz + height * 0.97, r * 0.3)):
        ax, ay = axis(z)
        verts += [(ax + rr * math.cos(a), ay + rr * math.sin(a), z) for a in (0.0, math.pi / 2, math.pi, 1.5 * math.pi)]
    faces += [(i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i) for i in range(4)]
    for c in range(clumps):
        f = c / max(1, clumps - 1)
        zc = bz + height * (bare + (0.95 - bare) * f ** 0.85) + rng.normal(0, 0.012 * height)
        w = spread * height * (1.0 - 0.8 * f) * rng.uniform(0.7, 1.25)
        th = w * rng.uniform(0.5, 0.75)                   # thick enough that the sprays overlap: one ragged mass
        ax, ay = axis(zc)
        ang = rng.uniform(0, 2 * math.pi)
        off = w * 0.25 * (1 - f)
        cx, cy = ax + off * math.cos(ang), ay + off * math.sin(ang)
        top = len(verts)
        verts.append((cx, cy, zc + th * 0.7))
        ph = rng.uniform(0, 2 * math.pi)
        for ring, (rk, dz) in enumerate(((0.6, th * 0.25), (1.0, -th * 0.3))):
            for s in range(sides):
                a = ph + 2 * math.pi * (s + 0.5 * ring) / sides
                # the outer ring's points alternate long and short (the sprays' tips), drooping as they reach out
                rr = w * rk * (rng.uniform(0.85, 1.3) if (s + ring) % 2 == 0 else rng.uniform(0.5, 0.8))
                verts.append((cx + rr * math.cos(a), cy + rr * math.sin(a), zc + dz - (rr / w) ** 2 * th * 0.6 * ring))
        bot = len(verts)
        verts.append((cx, cy, zc - th * 0.5))
        r0, r1 = top + 1, top + 1 + sides
        for s in range(sides):
            t = (s + 1) % sides
            faces.append((top, r0 + s, r0 + t))
            faces.append((r0 + s, r1 + s, r0 + t))
            faces.append((r0 + t, r1 + s, r1 + t))
            faces.append((bot, r1 + t, r1 + s))
    ax, ay = axis(bz + height)
    tip = len(verts)
    verts.append((ax, ay, bz + height))
    zt = bz + height * 0.9
    tx, ty = axis(zt)
    for k in range(3):
        a = 2 * math.pi * k / 3
        verts.append((tx + 0.02 * height * math.cos(a), ty + 0.02 * height * math.sin(a), zt))
    faces += [(tip, tip + 1 + k, tip + 1 + (k + 1) % 3) for k in range(3)]
    return np.array(verts, float), faces


def forest(name: str, bases, heights, *, material, coll, seed: int = 1, kind: str = "cedar", **tree):
    """Trees at `bases` [(x, y, z), ...] of `heights`, merged into one object: cedars (`cedar_mesh`) or, `kind`
    "fir", tiered conifers (`conifer_mesh`); `tree` goes to each (clumps, sides, spread, ...)."""
    make = cedar_mesh if kind == "cedar" else conifer_mesh
    verts, faces, off = [], [], 0
    for k, (b, h) in enumerate(zip(bases, heights)):
        v, f = make(b, float(h), seed=seed * 7919 + k, **tree)
        verts.append(v)
        faces += [tuple(i + off for i in face) for face in f]
        off += len(v)
    if not verts:
        return None
    return shapes.mesh_object(name, np.concatenate(verts), faces, material, coll, smooth=False)


def scatter(n: int, x_range, y_range, *, seed: int = 1, min_gap: float = 0.0, keep=None, tries: int = 30) -> np.ndarray:
    """(m, 2) points scattered over the ranges, at least `min_gap` apart (dart throwing over a grid), and only where
    `keep(X, Y)` (arrays in, a boolean array out) says so when given: at most n of them."""
    rng = np.random.default_rng(seed)
    cand = np.c_[rng.uniform(*x_range, n * tries), rng.uniform(*y_range, n * tries)]
    if keep is not None:
        cand = cand[np.asarray(keep(cand[:, 0], cand[:, 1]), bool)]
    if min_gap <= 0:
        return cand[:n]
    cell = min_gap / math.sqrt(2)
    grid: dict = {}
    pts = []
    for x, y in cand:
        if len(pts) >= n:
            break
        i, j = int(x // cell), int(y // cell)
        ok = True
        for di in (-2, -1, 0, 1, 2):
            for dj in (-2, -1, 0, 1, 2):
                q = grid.get((i + di, j + dj))
                if q is not None and (q[0] - x) ** 2 + (q[1] - y) ** 2 < min_gap * min_gap:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            grid[(i, j)] = (x, y)
            pts.append((x, y))
    return np.asarray(pts, float).reshape(-1, 2)


def ridge_line(name: str, material, coll, a, b, height: float, *, seed: int = 1, trees: float = 0.0, base_z: float = -2.0,
               n: int = 200, scale: float | None = None):
    """A ridge's silhouette as a curtain standing on the line from `a` to `b` ((x, y) each) instead of straight
    across the view (`ridge`): a valley's flank receding into the distance. Its summits are as wide as `scale` m
    (default a third of its length)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    L = float(np.linalg.norm(b - a))
    s = np.linspace(0.0, L, n)
    h = ridge_profile(s - L / 2, scale or L / 3, height, seed, trees=trees)
    taper = np.clip(np.minimum(s, L - s) / (0.08 * L), 0.0, 1.0) ** 0.5      # its ends fall away
    h = base_z + (h - base_z) * taper
    pts = a + np.outer(s / L, b - a)
    verts = [(x, y, z) for (x, y), z in zip(pts, h)] + [(x, y, base_z) for x, y in pts]
    faces = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    return shapes.mesh_object(name, verts, faces, material, coll, smooth=False)


def grass(name: str, roots, *, material, coll, seed: int = 1, blades: int = 5, height=(0.25, 0.6), lean: float = 0.12,
          width=(0.018, 0.035)):
    """Tufts of grass: at each root (x, y, z) a clump of `blades` thin spikes fanning out, merged into one mesh."""
    rng = np.random.default_rng(seed)
    r0s, tips, ws = [], [], []
    for r in np.asarray(roots, float):
        hk = rng.uniform(*height)
        for _ in range(blades):
            a = rng.uniform(0, 2 * math.pi)
            ln = hk * rng.uniform(0.6, 1.0)
            r0 = r + np.array([rng.normal(0, 0.03), rng.normal(0, 0.03), -0.02])
            r0s.append(r0)
            tips.append(r0 + np.array([math.cos(a) * lean * ln * 2, math.sin(a) * lean * ln * 2, ln]))
            ws.append(rng.uniform(*width))
    if not r0s:
        return None
    return shapes.spikes(name, r0s, tips, ws, material=material, coll=coll, sides=3)
