"""The Rain Ferry's jetty and hut (6 ferry to 24 board, and the start of 26 cross), built to be seen from anywhere:
rf/sets.py's layout (the jetty along x from the bank at -x, its deck's top at z 0; the hut at sets.HUT with its red
lantern; the boat moored on the jetty's +y side), but every piece whole: the deck's posts braced under it, the end
posts thick and bound with rope (Tsuru knocks out her pipe on the -y one, rf/jetty_talk.py; the boat is tied to the
other), puddles lying on the planks, the planks wet, and the ferry a low flat-bottomed river boat (lib/boat.py) with a
seat at its stern, bobbing at its rope.
"""
from __future__ import annotations

import math

import numpy as np

from . import sets

POSTS = (-5.0, -2.5, 0.0, 2.5, 5.0)     # the deck's posts along x (the end's are the staved posts)
# (x, y): the -y one is where Tsuru knocks out her pipe (rf/jetty_talk.py), the boat's (+y) one holds its rope
END_POSTS = {"tap": (7.42, -sets.HALF - 0.1), "mooring": (7.42, sets.HALF + 0.1)}
FACING = {"tap": math.radians(130.0), "mooring": math.pi / 2}   # their rims: the tap's toward her seat on the deck
END_HEIGHT = 0.62                        # the end posts stand this high over the deck (the tap at an old woman's waist)
BOAT = dict(location=(4.7, 2.3), length=5.6, beam=1.32)   # the ferry moored along the jetty, bow toward +x
DECK_PUDDLES = [(-4.2, -0.35, 0.32, 1.8), (-1.6, 0.4, 0.22, 1.4), (1.1, -0.5, 0.3, 2.2), (3.4, 0.15, 0.18, 1.0),
                (5.8, -0.2, 0.26, 1.6), (6.9, 0.55, 0.16, 1.0)]    # (x, y, radius, stretch along the planks)
BANK_PUDDLES = [(-7.4, 0.9, 0.55), (-8.6, -1.4, 0.4), (-5.9, 1.9, 0.3), (-8.0, 5.8, 0.6)]   # (x, y, radius)


def build(m: dict, near, weather, *, seed: int = 7) -> dict:
    """The jetty, the hut and its lantern, the moored boat and its rope, the puddles. `m`: the set's materials (plank,
    post, rope, wall, thatch, door, lantern, hull, wood, bamboo, stave, puddle). Returns the pieces and anchors."""
    from lib import boat, landscape, props, shapes, water, wayside

    from . import set_valley

    wz = sets.WATER_Z
    deck = props.pier(m, near, span=sets.SPAN, half=sets.HALF, water_z=wz, post_xs=POSTS, seed=seed)
    # under the deck, seen from a low angle or from the boat: a cap beam across each pair of posts and a brace
    # crossing between them, the posts going on down into the river bed
    rng = np.random.default_rng(seed)
    for k, x in enumerate(POSTS):
        deck.append(shapes.box(f"pier-cap{k}", (x, 0.0, -0.21), (0.14, 2 * sets.HALF + 0.3, 0.12), material=m["post"],
                               coll=near, rot_z=rng.uniform(-0.02, 0.02)))
        for s in (-1, 1):
            deck.append(shapes.cylinder(f"pier-pile{k}{s}", (x, s * (sets.HALF + 0.08), wz - 1.6), (x, s * (sets.HALF + 0.08), -0.2),
                                        0.1, material=m["post"], coll=near, n=10))
        if k < len(POSTS) - 1:
            x2 = POSTS[k + 1]
            for s in (-1, 1):
                y = s * (sets.HALF + 0.17)
                deck.append(shapes.cylinder(f"pier-brace{k}{s}", (x + 0.1, y, -0.25), (x2 - 0.1, y, wz + 0.05), 0.04,
                                            material=m["post"], coll=near, n=6))
    posts = {}
    for name, (x, y) in END_POSTS.items():
        posts[name] = wayside.staved_post(f"post-{name}", m, near, (x, y, 0.0), height=END_HEIGHT, radius=0.14,
                                          sink=1.4, facing=FACING[name],
                                          seed=seed + len(name))
    # the hut, its lantern swinging a little under the eave, its lit doorway
    hut = props.thatched_hut({"wall": m["wall"], "thatch": m["thatch"], "door": m["door"]}, near, sets.HUT)
    ex, ey, ez = hut["eave"]
    lantern, _ = props.paper_lantern("lantern", m["lantern"], near, (ex, ey, ez - 0.45), cord=m["post"], cord_top=ez + 0.1)
    sub = lantern.modifiers.new("round", "SUBSURF")
    sub.levels = sub.render_levels = 2
    # its origin at its middle (the lathe builds it round the world's): a focus target, a swing's pivot
    from mathutils import Matrix, Vector

    mid = sum((v.co for v in lantern.data.vertices), Vector()) / len(lantern.data.vertices)
    lantern.data.transform(Matrix.Translation(-mid))
    lantern.location = mid
    # the ferry, moored along the jetty on its +y side
    bx, by = BOAT["location"]
    ferry = boat.river_boat({"hull": m["hull"], "wood": m["wood"], "rope": m["rope"], "bamboo": m["bamboo"]}, near,
                            length=BOAT["length"], beam=BOAT["beam"], location=(bx, by, wz), heading=0.0, awning=True)
    # the mooring rope: from the mooring post's binding, sagging, to the ring at the boat's bow
    import bpy

    bpy.context.view_layer.update()
    ring = np.array(ferry["anchors"]["ring"].matrix_world.translation)
    px, py = END_POSTS["mooring"]
    a = np.array([px, py + 0.12, END_HEIGHT * 0.62])
    path = [a, (a + ring) / 2 + np.array([0.0, 0.0, -0.32]), ring]
    mooring = shapes.loft("mooring", [tuple(p) for p in path], [0.016] * 3, material=m["rope"], coll=near, n=6, subsurf=0)
    curve = mooring.modifiers.new("sag", "SUBSURF")
    curve.levels = curve.render_levels = 2
    # puddles: on the planks (long along them) and on the bank by the jetty's foot and the hut
    puddles = []
    for k, (x, y, r, st) in enumerate(DECK_PUDDLES):
        puddles.append(water.puddle(f"deck-puddle{k}", m["puddle"], near, (x, y), r, 0.012, seed=seed + k, stretch=st))
    for k, (x, y, r) in enumerate(BANK_PUDDLES):
        z = float(set_valley.ground(x, y)) + 0.04
        puddles.append(water.puddle(f"bank-puddle{k}", m["puddle"], near, (x, y), r, z, seed=seed + 20 + k, stretch=1.4,
                                    angle=rng.uniform(0, math.pi)))
    # the old trees behind the hut, where rf/sets.py's pines stand: cedars, as on the slopes
    landscape.forest("hut-cedars", [(x, y, float(set_valley.ground(x, y))) for x, y, _ in sets.PINES],
                     [h * 1.6 for *_, h in sets.PINES], material=m["needles"], coll=near, seed=seed, clumps=14, sides=8,
                     spread=0.18, bare=0.38)
    anchors = {
        "jetty_foot": (sets.SPAN[0] + 0.3, 0.0, 0.0),
        "jetty_end": (sets.SPAN[1] - 0.4, 0.0, 0.0),
        "jetty_end_seat": (sets.SPAN[1] - 0.55, sets.HALF - 0.05, 0.0),   # sitting on the deck's edge by the boat
        "tap_post": posts["tap"]["anchors"]["rim"],
        "tap_post_top": posts["tap"]["anchors"]["top"],
        "boat_seat": ferry["anchors"]["seat"],
        "boat_stern": ferry["anchors"]["stern"],
        "boat_middle": ferry["anchors"]["middle"],
        "boat_bow": ferry["anchors"]["bow"],
        "lantern": lantern,
        "hut_door": (sets.HUT[0] + 1.62, sets.HUT[1] - 0.45, sets.HUT[2]),
    }
    return {"deck": deck, "posts": posts, "hut": hut, "lantern": lantern, "boat": ferry, "mooring": mooring,
            "puddles": puddles, "anchors": anchors}
