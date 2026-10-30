"""The Rain Ferry's world, whole: one set every shot places its camera in. The valley's ground, river, forests,
ridges, mist and sky (rf/set_valley.py), the path down to the ferry with its puddles and the 「渡し」 signpost
(rf/set_approach.py), and the jetty, the hut and its lantern, and the moored ferry (rf/set_jetty.py), in rf/sets.py's
axes (the jetty along x from the near bank at -x, its deck's top at z 0; the river runs along y, its far bank at
x ≈ 70; down the valley is +y), lit and painted for a weather (rf/set_weather.py).

    from rf import set_world
    world = set_world.build(ctx)                       # the weather from the look schedule at the shot's start
    world = set_world.build(ctx, weather="after")      # ... or a named one: "rain", "thinning", "after"
    cam_at, aim_at, lens = set_world.VIEWS["ferry"]    # a starting framing per location (`views`)
    world["anchors"]["boat_seat"]                      # where things are: an empty (it moves with the boat) or a point
    set_world.anchor(world, "tap_post")                # ... as a world position (mathutils.Vector)
    set_world.push_off(world, ctx, t0=1.0, t1=6.5)     # 26 cross: the ferry poled out across the river
    set_weather.key(world, ctx)                        # the rain thinning on the water, over a shot (24 board)

It returns {"near": the collection to ink (toon.ink), "far": the distance the fog takes, "look": the toon.Look its
materials fade with, "key": the key sun, "anchors", the pieces (boat, lantern, sign, posts, mooring, ...),
"materials", "waters" (every water material: the rain's rings are keyed on these), "wet" (the planks' and mud's
sheen), "weather"}. The ferry bobs at its rope on every frame of the shot (keyed when built); `push_off` re-keys it.
"""
from __future__ import annotations

import math

from . import set_approach, set_jetty, set_valley, set_weather, sets

# what the set adds to rf/sets.py's palette: (lit, shade), linear
COLORS = {
    **sets.COLORS,
    "wood": ((0.1, 0.092, 0.084), (0.022, 0.021, 0.021)),     # the boat's seats and boards, worn paler than its hull
    "post": ((0.07, 0.06, 0.05), (0.016, 0.015, 0.014)),      # the deck's posts: old wood, browner than the standoff's
    "stave": ((0.065, 0.06, 0.056), (0.014, 0.014, 0.015)),
    "bamboo": ((0.13, 0.125, 0.1), (0.03, 0.03, 0.027)),
    "sign": ((0.16, 0.155, 0.15), (0.04, 0.04, 0.042)),      # the signpost: grey, bleached by years of weather
    "paint": ((0.012, 0.012, 0.014), (0.006, 0.006, 0.007)),  # its characters, ink
    "rock": ((0.07, 0.072, 0.075), (0.016, 0.017, 0.019)),
    "slope": ((0.045, 0.05, 0.052), (0.02, 0.022, 0.025)),    # the valley's far ground (the fog pales it)
    **sets.HUT_COLORS,
}
# the thatch's straw: (mottle, its patch size m, how dark its strands, their width m, how long against wide)
STRAW = {"thatch": (0.15, 1.5, 0.75, 0.14, 10.0), "thatch_edge": (0.12, 1.0, 0.85, 0.08, 16.0)}
PLASTER_STAIN = (0.06, 0.052, 0.045)    # the plaster darkened by the splash and the damp up from its foot
PLASTER_STAIN_Z = (1.25, 1.62)          # ... from its foot (world z) to where it's gone
PAPER = (1.0, 0.62, 0.3)                # the hut's lit shoji paper, the only warmth but the lantern's
LANTERN_RIB = (0.32, 0.05, 0.02)        # the lantern's bamboo hoops, dark through its paper
# what the rain leaves shining, and how much (of the weather's sheen) and how sharply (roughness)
WET = {"plank": (1.0, 0.14), "hull": (0.6, 0.22), "wood": (0.6, 0.22),
       "thatch": (0.12, 0.6), "wall": (0.5, 0.2), "hut_beam": (0.5, 0.2),
       "sign": (0.4, 0.3), "rock": (0.6, 0.25), "mud": (0.5, 0.32)}
# the painted ones: (mottle, its patch size m, dry brush, its direction)
PAINTED = {"mud": (0.6, 0.35, 0.45, "y"), "grass": (0.35, 1.5, 0.25, "z"), "rock": (0.3, 0.4, 0.35, "z"),
           "sign": (0.25, 0.15, 0.5, "z"), "plank": (0.2, 0.5, 0.35, "x"),
           "post": (0.3, 0.3, 0.5, "z"), "stave": (0.3, 0.3, 0.5, "z"),
           "wall": (0.25, 0.4, 0.45, "z"), "hut_beam": (0.25, 0.3, 0.4, "x"),
           "hut_ridge": (0.3, 0.3, 0.4, "x"), "lattice": (0.15, 0.3, 0.3, "z")}

# a starting framing for each location: (camera, aim, lens mm); the approach keeps its trees off these cameras
# (set_approach.CLEAR). Shots move from these as they need
VIEWS = {
    # 1 open: high on the near slope, down the valley: the river winding off below, ridge after ridge beyond
    "open": None,
    # 25 light: from the near bank's slope over the jetty down the river
    "valley": None,
    # 2 crow: behind the signpost, the hut and the jetty beyond
    "crow": ((-10.6, -5.6, 1.75), (-4.5, 3.0, 1.0), 35.0),
    # 3 step: at the mud, at the puddle
    "step": None,
    # 4 walk: down the path toward the mist he comes out of
    "walk": None,
    # 6 ferry: the crossing wide, from up the bank
    "ferry": ((-15.5, -11.5, 3.6), (2.0, 4.0, 0.0), 26.0),
    # the jetty from a low angle off its side, and from overhead
    "jetty_low": ((1.5, -3.6, 0.25), (6.0, 1.2, 0.7), 24.0),
    "jetty_top": ((3.0, -2.5, 9.0), (3.5, 1.0, 0.0), 30.0),
    # 10 tap: the post, the river behind
    "tap": ((6.25, -2.35, 0.95), (7.5, -0.95, 0.6), 50.0),
    # 26 cross: from the jetty's foot out across the river (the boat's path)
    "cross": ((-8.0, -6.0, 2.2), (40.0, 14.0, 0.0), 30.0),
    # 26 out on the river (the boat pushed off to CROSS_PATH's end): over her shoulder toward the far bank, from
    # the water beside her looking down the valley, and from the jetty's end watching her go
    "crossing": ((33.0, 16.5, 2.6), (60.0, 30.0, 1.0), 30.0),
    "crossing_side": ((44.0, 9.0, 0.5), (39.0, 23.0, 0.9), 35.0),
    "crossing_jetty": ((7.8, 0.3, 1.6), (40.0, 21.0, 0.2), 45.0),
}


def views() -> dict:
    """VIEWS with the path's views worked out on the path itself."""
    P = set_approach.path_xy()
    out = dict(VIEWS)
    g = set_valley.ground
    out["open"] = ((-38.0, -70.0, float(g(-38.0, -70.0)) + 46.0), (25.0, 200.0, 55.0), 24.0)
    out["valley"] = ((-13.0, -9.0, float(g(-13.0, -9.0)) + 4.5), (30.0, 110.0, 6.0), 24.0)
    sx, sy, sz = _step()
    out["step"] = ((sx - 0.9, sy - 1.6, sz + 0.55), (sx + 0.2, sy + 0.3, sz), 28.0)
    i = int(len(P) * 0.55)
    x, y = P[i]
    x2, y2 = P[i - 50]
    z = float(set_valley.ground(x, y))
    out["walk"] = ((float(x), float(y), z + 1.35), (float(x2), float(y2), float(set_valley.ground(x2, y2)) + 1.1), 40.0)
    return out


def _step():
    P = set_approach.path_xy()
    sx, sy = P[int(len(P) * 0.88)]
    return float(sx), float(sy), float(set_valley.ground(sx, sy)) + 0.04


def materials(look, weather) -> dict:
    """The set's materials in `weather`'s palette, faded with `look`."""
    from lib import minka, paint, toon, water

    w = set_weather.weather(weather)
    pal = set_weather.palette(w, COLORS)
    m = {}
    for k, (lit, shade) in pal.items():
        if k == "plaster":
            # earthen plaster, mottled, stained dark up from its foot
            m[k] = paint.wash(f"set-{k}", lit, shade, look=look, cut=0.38, mottle=0.55, mottle_scale=0.25, brush=0.3,
                              brush_scale=0.2, brush_dir="z", mist=PLASTER_STAIN, mist_z=PLASTER_STAIN_Z)
        elif k in STRAW:
            mot, size, br, width, stretch = STRAW[k]
            m[k] = paint.wash(f"set-{k}", lit, shade, look=look, cut=0.38, mottle=mot, mottle_scale=size, brush=br,
                              brush_scale=width, brush_dir="z", brush_stretch=stretch)
        elif k in PAINTED:
            mot, size, br, axis = PAINTED[k]
            m[k] = paint.wash(f"set-{k}", lit, shade, look=look, cut=0.38, mottle=mot, mottle_scale=size, brush=br,
                              brush_scale=size, brush_dir=axis)
        elif k == "needles":
            # the near cedars: one ink, barely banded (a cel cut across their ragged clumps reads as facets)
            soft = tuple(0.55 * a + 0.45 * b for a, b in zip(lit, shade))
            m[k] = paint.wash(f"set-{k}", lit, soft, look=look, cut=0.2, soft=0.15, flash=0.0, mottle=0.3,
                              mottle_scale=1.5)
        else:
            m[k] = toon.cel(f"set-{k}", lit, shade, look=look, cut=0.38, flash=0.0 if k in ("ridge", "needles") else None)
    for k, (amount, rough) in WET.items():
        water.wet(m[k], w.wet, roughness=rough, tint=(amount,) * 3)
    m.update(set_valley.materials(look, w, pal))
    m["lantern"] = minka.paper_glow("set-lantern", sets.LANTERN, look=look, strength=w.lantern * 0.8, core=1.5, edge=0.4)
    m["lantern_rib"] = toon.flat("set-lantern-rib", LANTERN_RIB, look=look, strength=w.lantern * 0.5)
    m["door"] = toon.flat("set-door-glow", PAPER, look=look, strength=0.65)
    m["water"] = water.surface("set-river", w.river[0], w.river[1], look=look, rain=w.rain, mirror=w.mirror,
                               shine=w.shine, shine_color=w.shine_color, flow=(0.0, 0.35), roughness=0.03,
                               sun=tuple(-c for c in w.key), sky=w.fog or w.sky)
    m["puddle"] = water.surface("set-puddle", tuple(c * 0.6 for c in w.river[0]), w.river[1], look=look, rain=w.rain,
                                mirror=w.puddle_mirror, scale=0.35, streaks=0.0, roughness=0.02, ripple=0.35,
                                sky=w.fog or w.sky)
    m["foam"] = water.foam("set-foam", tuple(min(1.0, c * 2.0) for c in w.river[1]),
                           look=look, amount=0.55 + 0.45 * w.rain)
    return m


def build(ctx=None, *, weather=None, scene=None, look=None, seed: int = 7) -> dict:
    """The world for a shot (`ctx`, render.py's): lit for `weather` (a name, a Weather, or by default the look
    schedule at the shot's first frame), the scene staged for it (set_weather.stage), the ferry bobbing over the
    shot's frames. Without ctx, `scene` and `weather` are needed (a still, a test)."""
    import bpy

    from lib import boat, toon

    scene = scene or ctx.scene
    if weather is None:
        weather = ctx.look_at(ctx.f0) if ctx is not None and getattr(ctx, "look", None) is not None else "rain"
    w = set_weather.weather(weather)
    staged_look, key = set_weather.stage(scene, w)
    look = look or staged_look
    near = toon.collection("set-near")
    far = toon.collection("set-far")
    m = materials(look, w)
    valley = set_valley.build(m, near, far, w, seed=seed)
    approach = set_approach.build(m, near, w, seed=seed + 4)
    jetty = set_jetty.build(m, near, w, seed=seed)
    _collars(m, near, jetty, w)
    world = {"scene": scene, "near": near, "far": far, "look": look, "key": key, "key_base": key.data.energy / w.key_gain,
             "weather": w, "materials": m, "river_material": m["water"], "waters": [m["water"], m["puddle"], m["foam"]],
             "wet": [m[k] for k in WET], "valley": valley, "approach": approach, "jetty": jetty,
             "boat": jetty["boat"], "lantern": jetty["lantern"], "sign": approach["sign"], "mooring": jetty["mooring"],
             "anchors": {**approach["anchors"], **jetty["anchors"]}}
    fps = scene.render.fps / scene.render.fps_base
    f0, f1 = (ctx.f0, ctx.f1) if ctx is not None else (scene.frame_start, scene.frame_end + 1)
    bx, by = set_jetty.BOAT["location"]
    boat.animate(jetty["boat"]["root"], range(f0 - 1, f1 + 1), fps, base=(bx, by, sets.WATER_Z, 0.0),
                 bob={"calm": 1.0 - 0.6 * w.warm})
    bpy.context.view_layer.update()
    return world


def _collars(m: dict, near, jetty: dict, w) -> None:
    """Foam and ripple collars where the jetty's posts and piles and the ferry's hull stand in the river."""
    from lib import water

    stand = [ob for ob in near.all_objects if ob.name.startswith(("pier-post", "pier-pile"))]
    stand += [[ob for ob in near.all_objects if ob.name.startswith(f"post-{name}")] for name in jetty["posts"]]
    water.collar("post-foam", stand, sets.WATER_Z, m["foam"], near, width=0.3)
    root = jetty["boat"]["root"]
    hull = [ob for ob in root.children_recursive if ob.type == "MESH"]
    water.collar("hull-foam", [hull], sets.WATER_Z, m["foam"], near, width=0.45, n=48, follow=root)


def anchor(world: dict, name: str):
    """Where anchor `name` is now, in the world (a Vector)."""
    from mathutils import Vector

    a = world["anchors"][name]
    return a.matrix_world.translation.copy() if hasattr(a, "matrix_world") else Vector(a)


# 26 cross: the ferry poled out from the jetty, across and down the river, toward the far bank
CROSS_PATH = [(4.7, 2.3), (9.0, 4.2), (17.0, 9.0), (28.0, 15.0), (40.0, 21.0)]
POLE_STROKE = 3.4            # s: her poling's stroke (shots/cross.py's POLE period) ...
POLE_IN = (-1.9, -0.9)       # ... and where the pole goes in, in the boat's axes (bow +x): beside the stern


def push_off(world: dict, ctx, *, t0: float, t1: float, path=None) -> None:
    """Key the ferry from its mooring out along `path` (default CROSS_PATH) from t0 to t1 (s into the shot), its
    rope cast off (hidden), bobbing as it goes, its wake behind it as strong as it is fast and rings spreading where
    the pole goes in."""
    from lib import boat, water

    root = world["boat"]["root"]
    root.animation_data_clear()
    fps = ctx.fps
    bx, by = set_jetty.BOAT["location"]
    boat.animate(root, range(ctx.f0 - 1, ctx.f1 + 1), fps, base=(bx, by, sets.WATER_Z, 0.0), f0=ctx.f0,
                 path=path or CROSS_PATH, push=(t0, t1), bob={"calm": 1.0 - 0.6 * world["weather"].warm})
    world["mooring"].hide_render = True
    world["mooring"].hide_viewport = True
    # its wake, as strong as it is fast
    w = world["weather"]
    # (paler than the water's own light, which after the rain is the gold sky's)
    foam_color = tuple(min(1.0, 0.5 * c + 0.55) for c in w.sky)
    foam = water.foam("set-wake", foam_color, look=world["look"], amount=0.0,
                      reach=0.55, ripples=0.8)
    water.key(foam, water.RAIN, [(ctx.f0, 0.0)])
    water.wake("ferry-wake", root, foam, world["near"], sets.WATER_Z, length=set_jetty.BOAT["length"])
    path = path or CROSS_PATH
    frames = range(ctx.f0 - 1, ctx.f1 + 1)
    at = [boat.drift_pose((f - ctx.f0) / fps, path, t0, t1)[:2] for f in frames]
    for f, a, b in zip(frames, at, at[1:] + at[-1:]):
        speed = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 * fps
        water.key(foam, water.FOAM, [(f, min(1.0, speed / 1.4))])
    # rings where the pole goes in at each stroke (shots/cross.py's: on the stroke's beat from the shot's start),
    # beside the stern
    events = []
    for k in range(int((ctx.f1 - ctx.f0) / fps / POLE_STROKE) + 1):
        t = k * POLE_STROKE
        x, y, h = boat.drift_pose(t, path, t0, t1)
        lx, ly = POLE_IN
        events.append((x + lx * math.cos(h) - ly * math.sin(h), y + lx * math.sin(h) + ly * math.cos(h),
                       ctx.f0 + round(t * fps)))
    water.strike_rings("pole-rings", events, sets.WATER_Z, world["near"], color=foam_color, look=world["look"], fps=fps)

