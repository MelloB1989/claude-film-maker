# lib/rig.py: the engine's CameraRig in Python, the camera a Blender shot shares with the scene that composites it. It
# is B03's port made shared, so it must frame exactly as B03's does (and B03's as three does: test_b03_reform.py).
import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

from lib import rig, timing

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("b03_reform", REPO / "blender" / "shots" / "b03_reform.py")
b03 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b03)


def test_the_engine_to_blender_turn_is_b03s_proper_rotation():
    assert np.allclose(rig.ENGINE_TO_BLENDER, b03.ENGINE_TO_BLENDER)
    assert np.isclose(np.linalg.det(rig.ENGINE_TO_BLENDER), 1.0)
    assert np.allclose(rig.to_blender([0, 1, 0]), [0, 0, 1])
    assert np.allclose(rig.to_blender([[1, 2, 3], [0, 0, 1]]), [[1, -3, 2], [0, -1, 0]])


def test_the_lens_is_the_engines_gate():
    # B03: 10.125 / tan(fov / 2) on a 20.25 mm-tall gate
    for fov in (13.58, 24.0, 32.0):
        assert rig.lens_mm(fov) == pytest.approx(10.125 / math.tan(math.radians(fov) / 2))


def test_poses_frame_and_project_as_b03s_port_does():
    for args in (([0, 0, 5], [0, 0, 0], 30, 0), ([-0.1, 0.08, 0.4], [0.0, 0.02, 0.0], 24, -4.4), ([1, 2, 3], [0, 1, 0], 18, 7)):
        a, b = rig.Pose(*args), b03.Pose(*args)
        assert np.allclose(a.basis(), b.basis())
        p = np.array([0.03, -0.02, 0.1])
        assert a.project(p) == pytest.approx(b.project(p))
        assert a.depth(p) == pytest.approx(b.depth(p))
        assert a.project_many(p[None])[0] == pytest.approx(a.project(p))
    behind = rig.Pose([0, 0, 1], [0, 0, 0], 24).project_many(np.array([[0, 0, 2.0]]))
    assert np.isnan(behind).all()  # a point behind the camera has no place on the frame


def test_the_rig_is_b03s_rig_on_b03s_keys():
    C = b03.Cues(timing.film())
    old = b03.Rig(C)
    keys = [{"t": k["t"], "pos": k["pos"], "target": k["target"], "fov": k["fov"], "roll": k["roll"],
             "ease": next(n for n, f in rig.EASE.items() if f is k["ease"] or f(0.3) == k["ease"](0.3))} for k in old.keys]
    new = rig.Rig(keys)
    for t in np.linspace(C.start - 0.2, C.down + 0.2, 23):
        a, b = new.at(t), old.at(t)
        assert np.allclose(a.pos, b.pos) and np.allclose(a.target, b.target)
        assert a.fov == pytest.approx(b.fov) and a.roll == pytest.approx(b.roll)


def test_a_key_needs_a_fov_first_and_carries_it_and_the_roll_on():
    with pytest.raises(ValueError):
        rig.Rig([{"t": 0, "pos": [0, 0, 1], "target": [0, 0, 0]}])
    r = rig.Rig([{"t": 0, "pos": [0, 0, 1], "target": [0, 0, 0], "fov": 20, "roll": 3},
                 {"t": 1, "pos": [0, 0, 2], "target": [0, 0, 0]}])
    assert r.at(1).fov == 20 and r.at(1).roll == 3
    assert r.at(-1).pos == pytest.approx([0, 0, 1]) and r.at(5).pos == pytest.approx([0, 0, 2])
    with pytest.raises(KeyError):
        rig.Rig([{"t": 0, "pos": [0, 0, 1], "target": [0, 0, 0], "fov": 20, "ease": "bouncy"}])


def test_the_blender_matrix_puts_the_camera_where_the_engine_has_it():
    p = rig.Pose([-0.1, 0.08, 0.4], [0.0, 0.02, 0.0], 24, 2)
    M = np.array(p.blender_matrix())
    assert np.allclose(M[:3, 3], rig.to_blender(p.pos))
    # Blender's camera looks down its own -z: that is the engine camera's view direction, turned
    view = -M[:3, 2]
    assert np.allclose(view, rig.to_blender(-p.basis()[:, 2]))
    assert np.isclose(np.linalg.det(M[:3, :3]), 1.0)


def test_every_ease_a_key_can_name_is_one_the_engine_has_with_its_curve():
    src = (REPO / "app" / "src" / "engine" / "util.ts").read_text()
    body = src[src.index("export const ease = {"):]
    body = body[:body.index("};")]
    for name in rig.EASE:
        assert f"  {name}:" in body, f"util.ts ease has no {name}"
    # spot-check the curves against util.ts's formulas
    assert rig.EASE["inOutCubic"](0.25) == pytest.approx(4 * 0.25 ** 3)
    assert rig.EASE["inOutQuad"](0.75) == pytest.approx(1 - (-2 * 0.75 + 2) ** 2 / 2)
    assert rig.EASE["outExpo"](0.3) == pytest.approx(1 - 2 ** (-3))
