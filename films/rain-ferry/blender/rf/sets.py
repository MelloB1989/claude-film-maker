"""The Rain Ferry's crossing as a composition: where its pieces stand and what colours they are. A wooden jetty
out over a wide river, the muddy bank with the ferrywoman's thatched hut and its red lantern, the covered ferry boat
moored alongside, pines behind the hut, and ridge after ridge of mountains fading into the mist across the water.
The pieces are the core's (blender/lib/props.py, landscape.py); only this world's layout lives here.

World axes: the jetty runs along x (the bank at -x, its end at +x), its deck's top at z 0; the river lies behind it
toward +y; a camera at -y looks across it. `crossing(look)` builds it and returns its collections (`near`: what the
line art draws; `far`: the distance, left to the fog) and the pieces shots move (the lantern, the boat).
"""
from __future__ import annotations

from lib import landscape, props, shapes, toon

WATER_Z = -0.45
SPAN = (-6.5, 7.6)          # the jetty along x
HALF = 1.0                  # half its width
BANK_EDGE = -5.6            # where the bank meets the water
SKY = (0.5, 0.53, 0.58)     # the fog and the sky at the horizon (linear)
ZENITH = (0.3, 0.32, 0.36)

COLORS = {
    "plank": ((0.075, 0.07, 0.066), (0.016, 0.016, 0.017)),
    "post": ((0.05, 0.047, 0.045), (0.011, 0.011, 0.012)),
    "rope": ((0.3, 0.25, 0.16), (0.08, 0.066, 0.045)),
    "mud": ((0.08, 0.072, 0.062), (0.022, 0.02, 0.018)),
    "grass": ((0.1, 0.115, 0.09), (0.025, 0.028, 0.024)),
    "wall": ((0.06, 0.05, 0.042), (0.014, 0.012, 0.011)),
    "thatch": ((0.2, 0.17, 0.11), (0.045, 0.038, 0.028)),
    "hull": ((0.07, 0.06, 0.05), (0.016, 0.014, 0.012)),
    "needles": ((0.04, 0.05, 0.047), (0.012, 0.015, 0.015)),
    "ridge": ((0.035, 0.04, 0.048), (0.035, 0.04, 0.048)),
}
# the hut's lantern and doorway, the only warm light in the cold
LANTERN = (0.95, 0.22, 0.07)
DOOR = (0.55, 0.25, 0.09)
RIVER = ((0.03, 0.035, 0.045), (0.16, 0.175, 0.2))   # (water, the light of its streaks and rings)

BOAT_LANTERN = (5.0, 3.0)    # where the ferry's lantern hangs (x, y): off the boat's far side, over its roof
HUT = (-6.7, 3.4, 0.25)     # the hut's floor: far enough right that its lantern hangs inside a wide shot from the jetty
PINES = [(-11.5, 9.5, 9.5), (-14.6, 7.0, 8.0), (-10.0, 13.5, 11.0), (-16.5, 11.5, 9.0), (-13.8, 15.5, 10.5), (-18.5, 8.5, 8.5)]
RIDGES = [(70, 22, 1.6), (125, 48, 1.2), (200, 85, 0.0), (300, 120, 0.0), (440, 150, 0.0)]   # (distance, height, tree fringe)
MIST = [(45, 18, 260), (100, 35, 420), (165, 55, 620), (250, 80, 900)]                        # (distance, height, width)


def materials(look) -> dict:
    # the distance (ridges and pines) stands dark against a lightning sky
    m = {k: toon.cel(f"set-{k}", lit, shade, look=look, cut=0.38, flash=0.0 if k in ("ridge", "needles") else None)
         for k, (lit, shade) in COLORS.items()}
    m["lantern"] = toon.flat("set-lantern", LANTERN, look=look, strength=3.0)
    m["door"] = toon.flat("set-door-glow", DOOR, look=look, strength=0.45)
    # the ferry's lantern: a softer amber, a warm accent behind her close-up rather than a hot red one
    m["boat_lantern"] = toon.flat("set-boat-lantern", (0.85, 0.42, 0.16), look=look, strength=0.55)
    m["water"] = toon.water("set-river", RIVER[0], RIVER[1], look=look, rings=1.0, reflect=0.3)
    return m


def crossing(look, *, seed: int = 7) -> dict:
    near = toon.collection("set-near")
    far = toon.collection("set-far")
    m = materials(look)

    props.pier(m, near, span=SPAN, half=HALF, water_z=WATER_Z, seed=seed)
    landscape.bank("bank", ground=m["mud"], grass=m["grass"], coll=near, edge=BANK_EDGE, water_z=WATER_Z, seed=seed)
    hut = props.thatched_hut({"wall": m["wall"], "thatch": m["thatch"], "door": m["door"]}, near, HUT)
    ex, ey, ez = hut["eave"]
    lantern, _ = props.paper_lantern("lantern", m["lantern"], near, (ex, ey, ez - 0.45), cord=m["post"], cord_top=ez + 0.1)
    # rounded: out of focus behind a close-up the lathe's facets read as an octagon
    sub = lantern.modifiers.new("round", "SUBSURF")
    sub.levels = sub.render_levels = 2
    boat = props.covered_boat({"hull": m["hull"], "post": m["post"], "thatch": m["thatch"]}, near, x0=3.1, y=2.25, water_z=WATER_Z)
    bx, by, bz = boat["bow"]
    # the ferry's own light: a small lantern hung from a bamboo pole standing on the boat's far side over its roof, a
    # warm point at the far end of the jetty from the hut's
    px, py = BOAT_LANTERN
    shapes.cylinder("boat-lantern-pole", (px, py - 0.14, WATER_Z + 0.25), (px, py - 0.14, 1.9), 0.018, material=m["post"],
                    coll=near, n=8)
    shapes.cylinder("boat-lantern-arm", (px, py - 0.14, 1.86), (px, py, 1.86), 0.012, material=m["post"], coll=near, n=6)
    boat_lantern, _ = props.paper_lantern("boat-lantern", m["boat_lantern"], near, (px, py, 1.62), radius=0.075,
                                          height=0.22, cord=m["post"], cord_top=1.86)
    sub = boat_lantern.modifiers.new("round", "SUBSURF")
    sub.levels = sub.render_levels = 2
    shapes.loft("mooring", [(bx, by, bz), (bx - 0.4, by - 0.6, WATER_Z + 0.25), (7.4, HALF + 0.08, 0.35)], [0.015] * 3,
                material=m["rope"], coll=near, n=6, subsurf=0)
    for k, (x, y, h) in enumerate(PINES):
        landscape.pine(f"pine{k}", (x, y, 0.25), h, trunk=m["post"], needles=m["needles"], coll=far, seed=seed + k)
    landscape.river("river", m["water"], far, z=WATER_Z)
    for k, (d, h, trees) in enumerate(RIDGES):
        landscape.ridge(f"ridge{k}", m["ridge"], far, d, h, seed=seed * 10 + k, trees=trees, base_z=WATER_Z - 2)
    landscape.mist_layers(far, SKY, MIST, base_z=WATER_Z)
    landscape.sky("sky", far, horizon=SKY, zenith=ZENITH)
    return {"near": near, "far": far, "lantern": lantern, "boat_lantern": boat_lantern, "boat": boat["hull"],
            "materials": m}
