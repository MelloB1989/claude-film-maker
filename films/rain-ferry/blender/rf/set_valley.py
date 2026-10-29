"""The Rain Ferry's river valley: the ground every location stands on and the distance they all look into. A wide
river runs along y between two banks; the near bank (x < about -5.6, the jetty's) is a strip of mud and grass, flat
enough for the path down to the ferry, then the slope climbs steeply into forested mountains; the far bank (x past
FAR_EDGE) the same, mirrored. Down the valley (+y) ridge after ridge of ink-wash mountains fade into the mist.

The ground is a height function (`ground`, numpy only, tested), sampled twice: coarsely over the whole valley and
finely round the ferry, where the cameras come close (the coarse one sinks under the fine one there). Its world is
rf/sets.py's: the jetty along x from the bank, its deck at z 0, the water at sets.WATER_Z.
"""
from __future__ import annotations

import math

import numpy as np

from . import sets

FAR_EDGE = 70.0                    # the far bank's waterline, x
VALLEY = ((-260.0, 330.0), (-260.0, 330.0))    # the coarse ground's x and y ranges
FINE = ((-48.0, -2.0), (-82.0, 24.0))          # ... and the fine ground's round the ferry and its path
FLAT = 9.0                          # m inland the bank stays low before the slope climbs
SLOPE = 0.38                        # the slope's steepness (it climbs SLOPE * d ** 1.32)
TREELINE = 150.0                    # no trees above this
RIDGES = [(270, 95, 3.0), (360, 125, 2.5), (470, 150, 0.0), (620, 175, 0.0), (800, 200, 0.0)]  # (y, height, tree fringe)
MIST = [(90, 10, 260), (170, 22, 420), (250, 40, 620), (330, 60, 900), (430, 80, 1200)]          # (y, height, width)


def near_edge(y):
    """The near bank's waterline at y: rf/sets.py's shore by the jetty, bending away down the valley."""
    y = np.asarray(y, float)
    bend = 14.0 * (1 - np.cos(np.clip(y, -300, 400) * 0.0075))
    return sets.BANK_EDGE + 0.8 * np.sin(y * 0.35) + 0.4 * np.sin(y * 0.9 + 1) + bend * np.sign(y) * 0.6


def far_edge(y):
    """The far bank's waterline at y."""
    y = np.asarray(y, float)
    return FAR_EDGE + 3.0 * np.sin(y * 0.05 + 0.7) + 1.5 * np.sin(y * 0.13) + 10.0 * (1 - np.cos(np.clip(y, -300, 400) * 0.006))


def _bank(d, X, Y, seed: int, water_z: float):
    """The height of a bank `d` m inland from its waterline (negative: under the water)."""
    from lib import landscape

    low = water_z - 0.05 + 0.85 * np.clip(d / 2.6, 0, 1) + 0.25 * np.clip(d / 2.6, 0, 1) * np.sin(X * 0.7 + Y * 0.3)
    rough = landscape.fbm(X, Y, seed=seed, octaves=4, scale=90.0)
    climb = np.clip(d - FLAT, 0, None)
    hill = SLOPE * climb ** 1.32 * (1.0 + 0.35 * rough) + 6.0 * rough * np.clip(climb / 30, 0, 1)
    under = water_z - 0.05 + np.clip(d, -4, 0) * 0.5
    return np.where(d >= 0, low + hill, under)


def ground(X, Y, water_z: float = sets.WATER_Z):
    """The valley's ground height at X, Y (arrays): both banks and the river bed between them."""
    X, Y = np.asarray(X, float), np.asarray(Y, float)
    near = _bank(near_edge(Y) - X, X, Y, 3, water_z)
    far = _bank(X - far_edge(Y), X, Y, 5, water_z)
    return np.maximum(near, far)


def inland(x, y):
    """How far (m) inland from the near bank's waterline (x, y) is (numbers or arrays)."""
    return near_edge(y) - np.asarray(x, float)


def fine_mask(X, Y, margin: float = 6.0):
    """1 well inside the fine ground's area, 0 outside it (the coarse ground sinks under the fine one by this)."""
    (x0, x1), (y0, y1) = FINE
    X, Y = np.asarray(X, float), np.asarray(Y, float)
    dx = np.minimum(X - x0, x1 - X)
    dy = np.minimum(Y - y0, y1 - Y)
    return np.clip(np.minimum(dx, dy) / margin, 0, 1)


def build(m: dict, near, far, weather, *, seed: int = 7) -> dict:
    """The valley: the coarse ground (and the fine one round the ferry, in `near`), its forests, the river, the
    ridges and the mist down the valley, and the sky. `m`: the set's materials (slope, grass, needles, ridge, water).
    Returns the objects shots may want."""
    from lib import landscape, toon

    wz = sets.WATER_Z
    coarse = landscape.heightfield("valley-ground", lambda X, Y: ground(X, Y) - 1.2 * fine_mask(X, Y),
                                   *VALLEY, material=m["slope"], coll=far, step=4.0)
    fine = landscape.heightfield("bank-ground", ground, *FINE, material=m["grass"], coll=near, step=0.5)
    # the forests on the slopes: dense from where the slope starts up to the treeline, thinning as they climb; the
    # trees near the ferry are in their own (inked) object
    def on_slope(x, y):
        z = ground(x, y)
        d = np.maximum(inland(x, y), x - far_edge(y))
        return (d > FLAT + 2) & (z < TREELINE) & (z > 1.5)

    pts = landscape.scatter(5200, VALLEY[0], VALLEY[1], seed=seed, min_gap=4.2, keep=on_slope)
    zs = ground(pts[:, 0], pts[:, 1])
    rng = np.random.default_rng(seed)
    hs = rng.uniform(9.0, 17.0, len(pts)) * (1.0 - 0.35 * np.clip(zs / TREELINE, 0, 1))
    (fx0, fx1), (fy0, fy1) = FINE
    close = (pts[:, 0] > fx0 - 10) & (pts[:, 0] < fx1 + 10) & (pts[:, 1] > fy0 - 10) & (pts[:, 1] < fy1 + 10)
    landscape.forest("valley-forest", [(x, y, z - 0.2) for (x, y), z in zip(pts[~close], zs[~close])], hs[~close],
                     material=m["needles"], coll=far, seed=seed, tiers=4, sides=6)
    river = landscape.river("river", m["water"], far, z=wz, size=(1400.0, 1400.0), center_y=100.0)
    for k, (d, h, trees) in enumerate(RIDGES):
        landscape.ridge(f"ridge{k}", m["ridge"], far, d, h, seed=seed * 10 + k, trees=trees, base_z=wz - 2, width=1.3)
    mist = landscape.mist_layers(far, weather.sky, MIST, base_z=wz, density=0.75 * weather.mist)
    # low mist lying on the river, and banks of it drifting along the slopes (seen across the river too)
    for k, (y, w) in enumerate(((25, 140), (55, 200))):
        mist.append(toon.move_to(toon.mist_card(f"river-mist{k}", (FAR_EDGE * 0.5, y, wz + 2.5), (w, 7.0), weather.sky,
                                                density=0.5 * weather.mist, drift=0.5, seed=7.3 + k), far))
    for k, (x, y, z, w, h) in enumerate(((FAR_EDGE + 25, 20, 18, 240, 26), (FAR_EDGE + 60, 60, 45, 320, 40),
                                         (-60, 60, 30, 260, 34))):
        card = toon.mist_card(f"slope-mist{k}", (x, y, z), (w, h), weather.sky, density=0.55 * weather.mist, drift=0.7,
                              seed=3.7 * k + 1, rotation=(math.pi / 2, 0, math.pi / 2))
        mist.append(toon.move_to(card, far))
    sky = landscape.sky("sky", far, horizon=weather.sky, zenith=weather.zenith, distance=1400.0, size=(6000.0, 1100.0),
                        z=300.0)
    return {"ground": fine, "valley_ground": coarse, "river": river, "mist": mist, "sky": sky}
