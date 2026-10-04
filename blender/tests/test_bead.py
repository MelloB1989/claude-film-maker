# lib/bead.py: the commit bead in Blender, the engine's bead (app/src/engine/bead.ts) mirrored.
import math

import numpy as np
import pytest

from lib import bead


def test_the_profile_is_bead_ts_sphere_chamfer_and_bore():
    r, bore, ch = 1.0, 0.2, 0.09
    P = bead.bead_profile(r, bore, ch)
    lip = bore + ch
    h_lip = math.sqrt(r * r - lip * lip)
    assert P[0] == pytest.approx([lip, -h_lip])  # the bottom lip
    assert P[-1] == pytest.approx([lip, -h_lip])  # and back to it: closed
    sphere = P[:-3]
    assert np.allclose(np.hypot(sphere[:, 0], sphere[:, 1]), r)
    assert P[-3] == pytest.approx([bore, h_lip - ch]) and P[-2] == pytest.approx([bore, -(h_lip - ch)])  # the bore
    # the lip never opens past 0.9 r
    assert bead.bead_profile(1.0, 0.85, 0.3)[0][0] == pytest.approx(0.9)


def test_the_lathe_is_watertight_and_its_faces_turn_outward():
    verts, faces = bead.lathe(bead.bead_profile(1.0, 0.2, 0.09), 48)
    edges = {}
    for f in faces:
        for i in range(4):
            e = tuple(sorted((f[i], f[(i + 1) % 4])))
            edges[e] = edges.get(e, 0) + 1
    assert set(edges.values()) == {2}
    # the bore runs along x: every vertex's distance from the x axis is a profile radius
    out = 0
    for f in faces:
        v = verts[list(f)]
        n = np.cross(v[1] - v[0], v[3] - v[0])
        c = v.mean(axis=0)
        if np.linalg.norm(c) > 0.98 and np.linalg.norm(n) > 1e-9:  # on the sphere
            out += np.sign(n @ c)
    assert abs(out) > 0.9 * sum(1 for f in faces if np.linalg.norm(verts[list(f)].mean(axis=0)) > 0.98)


def test_the_engraving_wraps_onto_the_face_keeping_its_proportions():
    r = 2.0
    p = bead.wrap_to_sphere(np.array([[0.0, 0.0], [0.3, 0.0], [0.0, 0.2], [-0.5, -0.1]]), r)
    assert np.allclose(np.linalg.norm(p, axis=1), r)
    assert p[0] == pytest.approx([0, 0, r])  # the centre of the band is the face (+z)
    # arc lengths along and up the sphere are the flat ones
    assert r * math.acos(p[1] @ p[0] / r ** 2) == pytest.approx(0.3)
    assert r * math.acos(p[2] @ p[0] / r ** 2) == pytest.approx(0.2)
    assert p[1][0] > 0 and p[2][1] > 0  # +x toward the bore's +x end, +y up


def test_a_bead_turns_its_bore_onto_the_thread_and_its_face_to_the_camera():
    M = bead.bead_basis([0.0, 0.2, 1.0], [1.0, 0.0, 0.3])
    assert np.allclose(M.T @ M, np.eye(3)) and np.isclose(np.linalg.det(M), 1.0)
    assert np.allclose(M[:, 0], np.array([0.0, 0.2, 1.0]) / np.linalg.norm([0.0, 0.2, 1.0]))
    assert M[:, 2] @ np.array([1.0, 0.0, 0.3]) > 0
