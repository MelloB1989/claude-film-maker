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


def ridge_profile(xs: np.ndarray, distance: float, height: float, seed: int, *, trees: float = 0.0) -> np.ndarray:
    """The crest's height (m) at each x of a ridge `distance` away: rolling summits about `height`, one higher peak,
    and with `trees` (m) a fringe of tree tips along it. Deterministic in `seed`."""
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 100)
    k = 2 * math.pi / (distance * 0.9)
    h = 0.55 * np.sin(xs * k * 0.7 + ph) + 0.3 * np.sin(xs * k * 1.9 + 2 * ph) + 0.15 * np.sin(xs * k * 4.3 + 3 * ph)
    h = height * (0.55 + 0.45 * h) + height * 0.25 * np.exp(-((xs - rng.uniform(-0.5, 0.5) * distance) / (0.25 * distance)) ** 2)
    if trees:
        h = h + trees * np.abs(np.sin(xs * 7.3 / max(trees, 1e-3))) * rng.uniform(0.6, 1.0, len(xs))
    return h


def ridge(name: str, material, coll, distance: float, height: float, *, seed: int = 1, width: float = 1.6, trees: float = 0.0,
          base_z: float = -2.0, n: int = 240):
    """A ridge's silhouette across the view at y = `distance`, `width` times as wide as it is far, as a curtain down to
    `base_z`."""
    xs = np.linspace(-width * distance, width * distance, n)
    h = ridge_profile(xs, distance, height, seed, trees=trees)
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
