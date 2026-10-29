"""Wayside pieces from code for anime shots: a weathered wooden signpost with characters painted down its face, and
a thick mooring post of bound staves (a jetty's end post, for a rope and for knocking out a pipe on). Each is built
round an empty (`root`) at its foot, turned to face `facing` (radians from +x: the side its sign or its rope faces),
and returns its root, its objects and anchors (empties a shot can read or parent to: where a bird perches, where a
pipe is tapped).

World axes as the shots use them: z up. `stave_layout` is numpy only and tested without Blender.
"""
from __future__ import annotations

import math

import numpy as np

from . import shapes


def _root(name: str, coll, base, facing: float):
    import bpy

    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.2
    coll.objects.link(e)
    e.location = base
    e.rotation_euler = (0.0, 0.0, facing)
    return e


def _anchor(name: str, coll, root, location):
    import bpy

    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.08
    coll.objects.link(e)
    e.parent = root
    e.location = location
    return e


def stave_layout(radius: float, count: int, height: float, *, seed: int = 1, ragged: float = 0.05) -> list[tuple]:
    """[(angle, width, top), ...]: `count` staves round a post of `radius`, each a little narrower than its share of
    the round (a dark seam between), its top cut at its own height within `ragged` of `height` (a weathered, uneven
    crown)."""
    rng = np.random.default_rng(seed)
    share = 2 * math.pi * radius / count
    return [(2 * math.pi * k / count + rng.uniform(-0.04, 0.04), share * rng.uniform(0.8, 0.92),
             height - rng.uniform(0.0, ragged)) for k in range(count)]


def staved_post(name: str, m: dict, coll, base, *, height: float = 0.9, radius: float = 0.13, staves: int = 9,
                bindings=((0.12, 4), (0.62, 3)), sink: float = 1.2, facing: float = 0.0, seed: int = 1) -> dict:
    """A thick post of staves round a dark core, standing `height` above `base` (and `sink` below it, down into the
    water), bound with turns of rope (`bindings`: (height fraction, turns)). `m`: post, stave (the staves' wood;
    default post), rope. Anchors: top (the middle of its crown), rim (the crown's edge on its `facing` side, where a
    pipe is knocked out)."""
    root = _root(f"{name}-root", coll, base, facing)
    wood = m.get("stave", m["post"])
    obs = [shapes.cylinder(f"{name}-core", (0, 0, -sink), (0, 0, height - 0.012), radius * 0.9, material=m["post"],
                           coll=coll, n=12)]
    for k, (a, w, top) in enumerate(stave_layout(radius, staves, height, seed=seed)):
        c = (math.cos(a) * radius * 0.93, math.sin(a) * radius * 0.93)
        obs.append(shapes.box(f"{name}-stave{k}", (c[0], c[1], (top - sink) / 2), (radius * 0.2, w, top + sink),
                              material=wood, coll=coll, rot_z=a))
    for j, (fz, turns) in enumerate(bindings):
        for t in range(turns):
            z = height * fz + t * 0.03
            obs.append(shapes.cylinder(f"{name}-rope{j}{t}", (0, 0, z - 0.014), (0, 0, z + 0.014), radius + 0.018,
                                       material=m["rope"], coll=coll, n=14))
    for ob in obs:
        ob.parent = root
    anchors = {"top": _anchor(f"{name}-at-top", coll, root, (0, 0, height)),
               "rim": _anchor(f"{name}-at-rim", coll, root, (radius * 0.8, 0, height))}
    return {"root": root, "objects": obs, "anchors": anchors}


def signpost(name: str, m: dict, coll, base, text: str, *, font=None, height: float = 1.9, width: float = 0.2,
             sink: float = 0.4, char: float = 0.15, lean: float = 0.03, facing: float = 0.0, seed: int = 1) -> dict:
    """A weathered signpost: a squared post `width` wide standing `height` (leaning by `lean` rad) with a little gabled
    cap, `text` painted down its face one character under another (the face toward `facing`), `char` m a
    character, in `font` (a path to a .ttf/.otf with the glyphs; Blender's own font has no kanji). `m`: post, cap
    (default post), paint. Anchors: top (the cap's ridge, where a bird perches), face (the middle of the writing)."""
    import bpy

    rng = np.random.default_rng(seed)
    root = _root(f"{name}-root", coll, base, facing)
    tilt = shapes.rot_y(lean) @ shapes.rot_x(rng.uniform(-0.5, 0.5) * lean)
    h = height + sink
    post = shapes.box(f"{name}-post", (0, 0, h / 2 - sink), (width, width * 0.9, h), material=m["post"], coll=coll, rot=tilt)
    # the post's corners worn round: a bevel
    bev = post.modifiers.new("worn", "BEVEL")
    bev.width = width * 0.12
    bev.segments = 2
    cap = shapes.box(f"{name}-cap", (0, 0, height + 0.03), (width * 1.5, width * 1.3, 0.05), material=m.get("cap", m["post"]),
                     coll=coll, rot=tilt @ shapes.rot_z(rng.uniform(-0.05, 0.05)))
    obs = [post, cap]
    fnt = bpy.data.fonts.load(str(font), check_existing=True) if font else None
    top = height - 0.22
    face_x = width / 2 + 0.004
    for k, ch in enumerate(text):
        cu = bpy.data.curves.new(f"{name}-char{k}", "FONT")
        cu.body = ch
        if fnt:
            cu.font = fnt
        cu.size = char
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        cu.materials.append(m["paint"])
        ob = bpy.data.objects.new(f"{name}-char{k}", cu)
        coll.objects.link(ob)
        z = top - k * char * 1.05
        # on the face (+x), upright, with the post's lean
        p = tilt @ np.array([face_x, rng.uniform(-0.006, 0.006), z])
        ob.location = tuple(p)
        ob.rotation_euler = (math.pi / 2, -lean, math.pi / 2)
        obs.append(ob)
    for ob in obs:
        ob.parent = root
    anchors = {"top": _anchor(f"{name}-at-top", coll, root, tuple(tilt @ np.array([0, 0, height + 0.055]))),
               "face": _anchor(f"{name}-at-face", coll, root,
                               tuple(tilt @ np.array([face_x, 0, top - (len(text) - 1) * char * 0.525])))}
    return {"root": root, "objects": obs, "anchors": anchors}
