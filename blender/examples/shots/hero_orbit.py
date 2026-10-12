"""Hero orbit: a product-style hero shot. A glossy object turns slowly under three-point light while the camera orbits
it, close and shallow-focused, over a dark studio floor. An example: copy it into a film as
films/<id>/blender/shots/hero_orbit.py (blender/examples/README.md) and render it with
  blender -b -P blender/render.py -- --film <id> --shot hero_orbit --mode preview

The hero is a (2, 3) torus knot, a smooth tube in a clear-coated finish (materials.gloss) of the theme's fg, standing
over a floor of bg2 that catches its reflection; a thin ring glows in the theme's accent around its waist (only the
accents glow), lighting the knot's underside. lights.studio sets the key, the rim and the fill, and the world is the
theme's bg, so the plate's background is the film's own. Every colour is a palette role: the shot takes on any theme.

The camera is the engine's (rig.engine_camera: a 20.25 mm gate fit vertically, so `fov` is a vertical fov in any
format), slightly above the hero, at the distance that fits the hero in the film's frame whatever its aspect
(`fit_distance`), focused on the hero's centre. Over the shot it orbits `orbitDeg` at a constant rate on a pivot at the
hero's centre (a true arc, at every motion-blur step; the plate cuts with the engine scene mid-move), and the hero
turns `spinDeg` the other way.

Two empties are tracked for the engine (films/<id>/data/track/hero_orbit.json, in the film's logical px):
  hero      the hero's centre: a title or a glow can sit on it;
  callout   a point on the knot's outer rim, turning with it: the end of a label's leader line.

The shot's span is the engine's scene "hero" (SHOT["scene"]: change it to the scene the plate composites into, or give
explicit "frames": [f0, f1]). Its look can be tuned from films/<id>/data/look/hero_orbit.json (ctx.spec, shared with the
engine scene), every key optional:
  {"orbitDeg": 30, "spinDeg": -20, "fov": 24, "fstop": 2.8, "elevationDeg": 14, "color": "fg", "glow": "accent",
   "glowStrength": 4.0}

The geometry and the framing are numpy only (blender/tests/test_examples.py); build() needs Blender.
"""
from __future__ import annotations

import math

import numpy as np

SHOT = {"scene": "hero", "track": ["hero", "callout"]}

LOOK = {"orbitDeg": 30.0, "spinDeg": -20.0, "fov": 24.0, "fstop": 2.8, "elevationDeg": 14.0, "color": "fg",
        "glow": "accent", "glowStrength": 4.0}
KNOT = {"p": 2, "q": 3, "R": 0.5, "r": 0.22, "tube": 0.1}  # metres: about 1.6 m across
HEIGHT = 1.05  # the hero's centre above the floor (m)
MARGIN = 1.35  # the frame's half-height (or half-width) over the hero's radius


# ------------------------------------------------------------------------------------------------- the geometry

def torus_knot(p: int = KNOT["p"], q: int = KNOT["q"], R: float = KNOT["R"], r: float = KNOT["r"],
               n: int = 480) -> tuple[np.ndarray, np.ndarray]:
    """A (p, q) torus knot round the z axis: its centreline (n, 3), a closed loop (the point after the last is the
    first), and at each point the outward direction from the torus's core circle (n, 3), a normal that closes with
    it."""
    t = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    ring = np.column_stack([np.cos(p * t), np.sin(p * t), np.zeros_like(t)])
    out = np.cos(q * t)[:, None] * ring + np.sin(q * t)[:, None] * np.array([0.0, 0.0, 1.0])
    return R * ring + r * out, out


def closed_tube(c: np.ndarray, ref: np.ndarray, radius: float, seg: int = 24) -> tuple[np.ndarray, list]:
    """A round tube along a closed centreline c (n, 3): vertices (n * seg, 3) and quad faces, ring i joined to ring
    i + 1 and the last ring to the first, so the mesh is watertight. Each ring starts from `ref` (n, 3) made square to
    the tangent: a reference that closes with the loop gives a tube with no seam."""
    c = np.asarray(c, float)
    T = np.roll(c, -1, axis=0) - np.roll(c, 1, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    U = ref - T * np.sum(ref * T, axis=1, keepdims=True)
    U /= np.linalg.norm(U, axis=1, keepdims=True)
    V = np.cross(T, U)
    a = np.linspace(0.0, 2 * np.pi, seg, endpoint=False)
    rings = c[:, None] + radius * (np.cos(a)[None, :, None] * U[:, None] + np.sin(a)[None, :, None] * V[:, None])
    n = len(c)
    faces = [(i * seg + j, i * seg + (j + 1) % seg, ((i + 1) % n) * seg + (j + 1) % seg, ((i + 1) % n) * seg + j)
             for i in range(n) for j in range(seg)]
    return rings.reshape(-1, 3), faces


def hero_radius(knot: dict = KNOT) -> float:
    """The radius of the sphere round the hero's centre that holds all of it."""
    return knot["R"] + knot["r"] + knot["tube"]


# --------------------------------------------------------------------------------------------------- the camera

def fit_distance(radius: float, fov: float, aspect: float, margin: float = MARGIN) -> float:
    """How far from its centre a camera with vertical fov `fov` (degrees) on a frame of `aspect` (width / height) must
    stand so a sphere of `radius` fills at most 1 / margin of the frame's narrower half-extent."""
    ty = math.tan(math.radians(fov) / 2)
    half = ty * min(1.0, aspect)  # the narrower half-extent, as a tangent
    return margin * radius / math.sin(math.atan(half))


def orbit_position(angle: float, elevation: float, distance: float, target=(0.0, 0.0, HEIGHT)) -> np.ndarray:
    """The camera's place in Blender's coordinates (z up) on an orbit round `target`: `distance` from it, `elevation`
    degrees above its horizon, at `angle` degrees round z from the front (-y)."""
    a, e = math.radians(angle), math.radians(elevation)
    return np.asarray(target, float) + distance * np.array([math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e),
                                                            math.sin(e)])


def callout_point(knot: dict = KNOT) -> np.ndarray:
    """The callout's place on the knot, in its own frame: on the tube's outer surface at the knot's first point."""
    c, _ = torus_knot(knot["p"], knot["q"], knot["R"], knot["r"], n=8)
    radial = np.array([c[0, 0], c[0, 1], 0.0]) / np.hypot(c[0, 0], c[0, 1])
    return c[0] + knot["tube"] * radial


# ------------------------------------------------------------------------------------------------- the shot

def build(ctx):
    import bpy
    from mathutils import Vector

    from lib import lights, materials, rig

    look = {**LOOK, **(ctx.spec or {})}
    scene, coll = ctx.scene, ctx.scene.collection
    first, last = ctx.f0 - 1, ctx.f1  # keys a frame beyond each end: the motion blur at the ends is the middle's

    # the hero: the knot in a clear-coated finish, turning slowly about its own axis
    verts, faces = closed_tube(*torus_knot(), KNOT["tube"])
    me = bpy.data.meshes.new("hero_knot")
    me.from_pydata(verts.tolist(), [], faces)
    me.shade_smooth()
    me.materials.append(materials.gloss(look["color"], roughness=0.22, name="hero_finish"))
    knot = bpy.data.objects.new("hero_knot", me)
    knot.location = (0.0, 0.0, HEIGHT)
    coll.objects.link(knot)
    for f, deg in ((first, 0.0), (last, look["spinDeg"])):
        knot.rotation_euler = (0.0, 0.0, math.radians(deg))
        knot.keyframe_insert("rotation_euler", frame=f)

    # the glow: a thin ring in the accent round the knot's waist (it lights the knot's underside and the floor)
    t = np.linspace(0.0, 2 * np.pi, 256, endpoint=False)
    ring_c = (hero_radius() + 0.08) * np.column_stack([np.cos(t), np.sin(t), np.zeros_like(t)])
    rv, rf = closed_tube(ring_c, np.tile([0.0, 0.0, 1.0], (len(t), 1)), 0.008, seg=12)
    rme = bpy.data.meshes.new("hero_glow")
    rme.from_pydata(rv.tolist(), [], rf)
    rme.shade_smooth()
    rme.materials.append(materials.emission(look["glow"], look["glowStrength"], name="hero_glow"))
    ring = bpy.data.objects.new("hero_glow", rme)
    ring.location = (0.0, 0.0, HEIGHT - 0.1)
    coll.objects.link(ring)

    # the floor: a studio floor in bg2 with a little gloss to catch the hero, wide enough that its edge is never seen
    fme = bpy.data.meshes.new("floor")
    s = 250.0
    fme.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    fme.materials.append(materials.satin("bg2", roughness=0.3, coat=0.4, sheen=0.0, name="floor"))
    floor = bpy.data.objects.new("floor", fme)
    coll.objects.link(floor)

    # the anchors the engine tracks
    centre = bpy.data.objects.new("hero", None)
    centre.empty_display_size = 0.2
    centre.location = (0.0, 0.0, HEIGHT)
    coll.objects.link(centre)
    callout = bpy.data.objects.new("callout", None)
    callout.empty_display_size = 0.1
    callout.parent = knot
    callout.location = tuple(callout_point())
    coll.objects.link(callout)

    # the camera: the engine's gate, framed to fit the hero in this film's aspect, on a pivot at the hero's centre that
    # turns at a constant rate (the camera's place at pivot angle a is orbit_position(a))
    distance = fit_distance(hero_radius(), look["fov"], ctx.size[0] / ctx.size[1])
    pivot = bpy.data.objects.new("orbit", None)
    pivot.location = (0.0, 0.0, HEIGHT)
    coll.objects.link(pivot)
    for f, deg in ((first, -look["orbitDeg"] / 2), (last, look["orbitDeg"] / 2)):
        pivot.rotation_euler = (0.0, 0.0, math.radians(deg))
        pivot.keyframe_insert("rotation_euler", frame=f)
    cam = rig.engine_camera("camera", fstop=look["fstop"], size=ctx.size)
    cam.data.lens = rig.lens_mm(look["fov"])
    cam.data.dof.focus_object = centre
    cam.data.clip_end = 2 * s
    cam.parent = pivot
    cam.location = Vector(orbit_position(0.0, look["elevationDeg"], distance, target=(0.0, 0.0, 0.0)).tolist())
    cam.rotation_euler = (-cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    for ob in (knot, pivot):
        _linear(ob)

    # three-point light round the hero, scaled to its size; the world is the theme's background
    lights.studio(key=260.0, rim=700.0, fill=45.0, target=(0.0, 0.0, HEIGHT), scale=1.6)


def _linear(ob) -> None:
    """Linear interpolation on every key of the object's action: a constant rate (Blender 5 keeps F-curves in layers,
    strips and channel bags)."""
    act = ob.animation_data.action
    curves = []
    if getattr(act, "layers", None):
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves.extend(bag.fcurves)
    elif hasattr(act, "fcurves"):
        curves.extend(act.fcurves)
    for fc in curves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
