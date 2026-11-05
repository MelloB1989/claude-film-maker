"""Ink drawn onto a person's skin (lib/human.py): age lines, crow's feet, a scar, a tattoo's outline. Each stroke is
a polyline in the face's own plane, projected onto the skin from in front and laid on it as a thin tapering strip, bound
to a bone.

Strokes are given in eye units round the eyes' midpoint, so one set of marks fits any face: x across (toward the
person's left, +x), z up, both in multiples of the distance between the eyes' centres. `mirror` draws each on both
sides. `face_frame` (the midpoint and the unit) is numpy only and tested without Blender.
"""
from __future__ import annotations

import numpy as np

from . import human


def face_frame(eye_l, eye_r) -> tuple[np.ndarray, float]:
    """The eyes' midpoint and the distance between them (the unit strokes are drawn in)."""
    a, b = np.asarray(eye_l, float), np.asarray(eye_r, float)
    return (a + b) / 2, float(np.linalg.norm(a - b))


def strokes(person, name: str, lines, *, material, width: float = 0.0012, taper: float = 0.6, lift: float = 0.0008,
            mirror: bool = True, bone: str = "head", samples: int = 10):
    """Strokes on the person's face: `lines` [[(x, z), ...], ...] in eye units round the eyes' midpoint (x toward the
    person's left), each projected onto the skin from the front (-y) and laid on it `width` wide (tapering to `taper`
    of that at both ends), `lift` off it. `mirror` adds each line's mirror image. One object, bound to `bone`."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    from . import shapes

    eyes = person.parts["eyes"]
    cs = [np.mean([v.co[:] for v in e.data.vertices], axis=0) for e in eyes]
    left, right = (cs[0], cs[1]) if cs[0][0] > cs[1][0] else (cs[1], cs[0])
    mid, unit = face_frame(left, right)
    bvh = BVHTree.FromObject(person.body, bpy.context.evaluated_depsgraph_get(), deform=False)
    todo = [np.asarray(l, float) for l in lines]
    if mirror:
        todo += [np.asarray(l, float) * [-1.0, 1.0] for l in lines]
    verts, faces = [], []
    for line in todo:
        # resample along the polyline
        seg = np.linalg.norm(np.diff(line, axis=0), axis=1)
        t = np.concatenate([[0], np.cumsum(seg)])
        u = np.linspace(0, t[-1], samples)
        pts2 = np.column_stack([np.interp(u, t, line[:, 0]), np.interp(u, t, line[:, 1])])
        pts, nrm = [], []
        for x, z in pts2:
            o = Vector((mid[0] + x * unit, mid[1] - 0.3, mid[2] + z * unit))
            hit = bvh.ray_cast(o, Vector((0.0, 1.0, 0.0)), 0.6)
            if hit[0] is None:
                continue
            pts.append(np.array(hit[0][:]))
            nrm.append(np.array(hit[1][:]))
        if len(pts) < 2:
            continue
        pts, nrm = np.array(pts), np.array(nrm)
        k = len(pts)
        f = np.linspace(0, 1, k)
        w = width * (taper + (1 - taper) * np.sin(np.pi * f))
        tang = np.gradient(pts, axis=0)
        tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
        across = np.cross(nrm, tang)
        across /= np.maximum(np.linalg.norm(across, axis=1, keepdims=True), 1e-9)
        base = pts + nrm * lift
        b = len(verts)
        verts += (base - across * w[:, None] / 2).tolist() + (base + across * w[:, None] / 2).tolist()
        faces += [(b + i, b + i + 1, b + k + i + 1, b + k + i) for i in range(k - 1)]
    ob = shapes.mesh_object(name, verts, faces, material, person.coll, smooth=False)
    human.bind(ob, person.rig, bone)
    person.parts[name] = ob
    return ob
