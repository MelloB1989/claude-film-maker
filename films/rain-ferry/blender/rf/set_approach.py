"""The Rain Ferry's approach (2 crow, 3 step, 4 walk, 5 eyes): the muddy path that comes up the river along the
near bank, between the slope's pines and the reeds by the water, out of the mist to the ferry; puddles along it to
step in (and for the rain to ring), grass and rocks either side, and at its end by the jetty's foot the weathered
ferry signpost painted 「渡し」, its cap where the crow perches.

The path's line (`PATH`, `path_xy`) is numpy only. Its ground is rf/set_valley.py's.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from . import set_valley, sets

# the path's middle, from far down the valley (-y) to the jetty's foot: (y, metres inland from the waterline)
PATH = [(-80.0, 5.5), (-62.0, 6.5), (-46.0, 4.8), (-32.0, 5.6), (-20.0, 4.6), (-10.0, 3.6), (-4.0, 2.4), (-0.4, 1.2)]
WIDTH = 1.5                          # the path's width (m)
SIGN = (-8.75, -2.4)                 # the signpost (x, y), on the path's slope side where it reaches the jetty
SIGN_TEXT = "渡し"
FONT = Path(__file__).resolve().parents[2] / "fonts" / "ShipporiMincho-SemiBold.ttf"


def path_xy(n: int = 400) -> np.ndarray:
    """(n, 2) points along the path's middle, from its far end to the jetty's foot."""
    from lib import boat

    ys = [boat.path_point([(y, d) for y, d in PATH], u) for u in np.linspace(0, 1, n)]
    return np.array([(float(set_valley.near_edge(y)) - d, y) for y, d in ys])


def build(m: dict, near, weather, *, seed: int = 11) -> dict:
    """The path, its puddles, grass, rocks and trees, and the signpost. `m`: mud, grass, needles, post, sign, paint,
    rock, puddle. Returns the pieces and anchors."""
    from lib import landscape, shapes, toon, water, wayside

    rng = np.random.default_rng(seed)
    P = path_xy()
    ground = set_valley.ground
    # the path: a strip of mud laid on the ground, worn into two ruts by feet and carts, lumpy, ragged at its edges
    tang = np.gradient(P, axis=0)
    tang /= np.linalg.norm(tang, axis=1)[:, None]
    side = np.c_[-tang[:, 1], tang[:, 0]]
    cols = 13
    verts = []
    for i, (p, s) in enumerate(zip(P, side)):
        for j in range(cols):
            f = j / (cols - 1) - 0.5
            edge = j in (0, cols - 1)
            w = WIDTH * (1 + (0.3 * rng.uniform(-1, 1) if edge else 0))
            x, y = p + s * f * w
            rut = -0.035 * math.exp(-((abs(f) - 0.22) / 0.07) ** 2)
            lump = 0.025 * math.sin(x * 3.1 + y * 1.7) * math.sin(y * 2.3 - x) + rng.normal(0, 0.006)
            verts.append((x, y, float(ground(x, y)) + (0.0 if edge else 0.03 + rut + lump)))
    path = shapes.mesh_object("path", verts, landscape.grid_faces(cols, len(P)), m["mud"], near, smooth=True)
    path.lineart.usage = "OCCLUSION_ONLY"
    # puddles along it (rutted where feet go), each lying level just over the mud
    puddles = []
    for k, i in enumerate(sorted(rng.choice(np.arange(6, len(P) - 3), 14, replace=False))):
        x, y = P[i] + side[i] * rng.uniform(-0.35, 0.35)
        r = rng.uniform(0.22, 0.5)
        puddles.append(water.puddle(f"path-puddle{k}", m["puddle"], near, (x, y), r, float(ground(x, y)) + 0.035,
                                    seed=seed + k, stretch=rng.uniform(1.2, 2.0),
                                    angle=math.atan2(tang[i, 1], tang[i, 0])))
    # the shot's own puddle (3 step): on the path's middle a few metres from the jetty's foot
    step_i = int(len(P) * 0.88)
    sx, sy = P[step_i]
    puddles.append(water.puddle("step-puddle", m["puddle"], near, (sx, sy), 0.42, float(ground(sx, sy)) + 0.04, seed=seed + 99,
                                stretch=1.5, angle=math.atan2(tang[step_i, 1], tang[step_i, 0])))
    # grass both sides of the path and along the bank, thick by the water; none on the path
    def from_path(x, y):
        return np.min(np.hypot(P[:, 0] - x[:, None], P[:, 1] - y[:, None]), axis=1)

    def bank(x, y):
        d = set_valley.inland(x, y)
        hx, hy, _ = sets.HUT
        return (0.3 < d) & (d < 14) & (from_path(x, y) > WIDTH * 0.75) & ~((-7.0 < x) & (x < -3.0) & (-1.6 < y) & (y < 1.6)) \
            & ~((abs(x - hx) < 1.9) & (abs(y - hy) < 1.6))

    roots = landscape.scatter(2600, (-30.0, -2.0), (-82.0, 20.0), seed=seed, min_gap=0.32, keep=bank)
    tufts = [(x, y, float(ground(x, y))) for x, y in roots]
    grass = landscape.grass("approach-grass", tufts, material=m["grass"], coll=near, seed=seed, blades=7, height=(0.3, 0.8))
    grass.lineart.usage = "EXCLUDE"     # too fine to ink: painted
    # rocks half sunk in the mud by the path
    rocks = []
    for k in range(26):
        i = rng.integers(0, len(P))
        s = rng.choice((-1, 1))
        x, y = P[i] + side[i] * s * (WIDTH * 0.6 + rng.uniform(0.1, 1.6))
        r = rng.uniform(0.18, 0.6)
        rocks.append(shapes.ellipsoid(f"rock{k}", (x, y, float(ground(x, y)) - r * 0.3), (r * 1.3, r, r * 0.65),
                                      material=m["rock"], coll=near, n=8,
                                      squash=lambda v, s_=k: v * (1 + 0.18 * np.sin(v[:, :1] * 5 + s_) * np.cos(v[:, 1:2] * 4))))
    # the slope's pines close by: tall dark trunks either side of the far path, thinning toward the ferry
    def wood(x, y):
        d = set_valley.inland(x, y)
        return (from_path(x, y) > 2.2) & (y < -16) & ((d > 8.0) | ((d > 2.0) & (rng.uniform(size=len(x)) < 0.25)))

    pts = landscape.scatter(150, (-46.0, -4.0), (-82.0, -6.0), seed=seed + 1, min_gap=3.2, keep=wood)
    hs = rng.uniform(14.0, 24.0, len(pts))
    trees = landscape.forest("approach-forest", [(x, y, float(ground(x, y))) for x, y in pts], hs, material=m["needles"],
                             coll=near, seed=seed, clumps=10, sides=7, spread=0.17, bare=0.4)
    # the mist the path comes out of: banks across it, deeper and paler the further down the valley
    mist = []
    for k, y in enumerate((-18.0, -26.0, -35.0, -46.0, -58.0, -72.0)):
        x = float(set_valley.near_edge(y)) - 8.0
        card = toon.mist_card(f"path-mist{k}", (x, y, float(ground(x, y)) + 2.6 + 0.3 * k), (46.0, 9.0 + k), weather.sky,
                              density=min(0.95, (0.35 + 0.1 * k) * weather.mist), drift=0.4 + 0.1 * k, seed=11.3 + k)
        card.lineart.usage = "EXCLUDE"
        mist.append(toon.move_to(card, near))
    # the signpost, its face to the path coming up from down the valley
    sz = float(ground(*SIGN))
    sign = wayside.signpost("signpost", {"post": m["sign"], "paint": m["paint"]}, near, (SIGN[0], SIGN[1], sz), SIGN_TEXT,
                            font=FONT if FONT.exists() else None, height=1.85, width=0.2, char=0.17, lean=0.05,
                            facing=-math.pi / 2 - 0.35, seed=seed)
    anchors = {
        "path_far": (float(P[0, 0]), float(P[0, 1]), float(ground(*P[0]))),
        "path_mid": (float(P[len(P) // 2, 0]), float(P[len(P) // 2, 1]), float(ground(*P[len(P) // 2]))),
        "path_end": (float(P[-1, 0]), float(P[-1, 1]), float(ground(*P[-1]))),
        "step_puddle": (float(sx), float(sy), float(ground(sx, sy)) + 0.04),
        "sign_top": sign["anchors"]["top"],
        "sign_face": sign["anchors"]["face"],
    }
    return {"path": path, "path_points": P, "puddles": puddles, "grass": grass, "rocks": rocks, "trees": trees, "mist": mist,
            "sign": sign, "anchors": anchors}
