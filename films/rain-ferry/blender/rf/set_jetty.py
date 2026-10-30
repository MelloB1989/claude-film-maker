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
# the hut's parts (lib/minka.py) -> the set's materials
HUT_MATERIALS = {"wall": "wall", "thatch": "thatch", "door": "door", "post": "hut_beam", "plaster": "plaster",
                 "thatch_edge": "thatch_edge", "ridge": "hut_ridge", "lattice": "lattice", "stone": "rock",
                 "dark": "hut_dark", "wood": "wood", "straw": "hut_straw", "rope": "rope", "lath": "lattice",
                 "glass": "puddle"}
# the lantern's light: colour, power (W), size, specular: warm on the boards under it; the lit windows' on the ground
LANTERN_LIGHT = ((1.0, 0.42, 0.18), 45.0, 0.12, 0.5)
WINDOW_LIGHT = ((1.0, 0.6, 0.3), 14.0, 0.6, 0.0)
LANTERN_AIM = (0.45, -0.45, -1.0)    # down and out from the hut's corner: its walls stay out of the cone
SMOKE = dict(height=2.6, width=(0.12, 1.1), density=0.35, lean=(-0.4, 0.4))   # the hearth's, from the back gap
BANK_PUDDLES = [(-7.4, 0.9, 0.55), (-8.6, -1.4, 0.4), (-5.9, 1.9, 0.3), (-8.0, 5.8, 0.6)]   # (x, y, radius)


def build(m: dict, near, weather, *, seed: int = 7, look=None) -> dict:
    """The jetty, the hut and its lantern, the moored boat and its rope, the puddles. `m`: the set's materials (plank,
    post, rope, wall, thatch, door, lantern, hull, wood, bamboo, stave, puddle). Returns the pieces and anchors."""
    import bpy

    from lib import boat, landscape, minka, props, shapes, toon, water, wayside
    from lib import weather as rain_fx

    from . import set_valley

    wz = sets.WATER_Z
    near_fx = toon.collection("set-near-fx")       # the hut's drips and its lantern's light: not inked
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
    # the hut (lib/minka.py): on the bank's edge, its door and porch toward the river, its red chochin hung under the
    # eave at the door side's corner, water dripping off its eaves, the lantern's light warm on the wet boards
    hut = minka.hut({k: m[v] for k, v in HUT_MATERIALS.items()}, near, sets.HUT, ground=set_valley.ground,
                    seed=seed - 2)
    ex, ey, ez = hut["eave"]
    lantern, _ = minka.chochin("lantern", {"lantern": m["lantern"], "cap": m["hut_dark"], "rib": m["lantern_rib"],
                                           "rope": m["rope"]}, near, (ex, ey, ez - 0.45), cord_top=ez + 0.1)
    for k, (a, b) in enumerate(hut["eave_edges"]):
        rain_fx.drips(f"hut-eave{k}", rain_fx.edge(a, b, 18 if k < 2 else 10), period=0.9, fall=2.6,
                      seed=seed + k, coll=near_fx)
    # their light: a soft cone down from the lantern onto the porch and the boards (not up on the eave), and one out
    # of each lit window onto the ground under it, unshadowed (cheap)
    from mathutils import Vector

    for name, parent, at, aim, (color, energy, size, spec) in (
            [("lantern-light", lantern, (0.0, 0.0, -0.25), LANTERN_AIM, LANTERN_LIGHT)]
            + [(f"hut-window-light{k}", None, p, (d[0], d[1], -0.9), WINDOW_LIGHT)
               for k, (p, d) in enumerate(hut["windows"])]):
        lamp = bpy.data.lights.new(name, "SPOT")
        lamp.color, lamp.energy, lamp.shadow_soft_size = color, energy, size
        lamp.spot_size, lamp.spot_blend = math.radians(100.0), 1.0
        lamp.use_custom_distance, lamp.cutoff_distance = True, 6.0
        lamp.use_shadow = False
        lamp.specular_factor = spec                # no hot glints in the puddles: a warm wash, not a spotlight
        ob = bpy.data.objects.new(name, lamp)
        near_fx.objects.link(ob)
        ob.parent = parent
        ob.location = at
        ob.rotation_euler = Vector(aim).to_track_quat("-Z", "Y").to_euler()
    # the hearth's smoke, thin, out of the back end's smoke gap and away on the wind
    sx, sy, sz = hut["smoke"][0]
    minka.smoke("hut-smoke", near_fx, (sx - 0.12, sy, sz - 0.4), look=look, seed=seed, **SMOKE)
    # the ferry, moored along the jetty on its +y side
    bx, by = BOAT["location"]
    ferry = boat.river_boat({"hull": m["hull"], "wood": m["wood"], "rope": m["rope"], "bamboo": m["bamboo"]}, near,
                            length=BOAT["length"], beam=BOAT["beam"], location=(bx, by, wz), heading=0.0, awning=True)
    # the mooring rope: from the mooring post's binding, sagging, to the ring at the boat's bow
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
                     spread=0.18, bare=0.38, smooth=True)
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
        "hut_door": hut["door"],
    }
    return {"deck": deck, "posts": posts, "hut": hut, "lantern": lantern, "boat": ferry, "mooring": mooring,
            "puddles": puddles, "anchors": anchors}
