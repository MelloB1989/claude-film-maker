# lib/rig.py: the engine's CameraRig in Python, the camera a Blender shot shares with the scene that composites it.
# Expected values are worked by hand from the pinhole model (three's lookAt, a vertical fov), never with rig.py.
import math
from pathlib import Path

import numpy as np
import pytest

from lib import rig

REPO = Path(__file__).resolve().parents[2]


def test_the_engine_to_blender_turn_is_a_proper_rotation():
    assert np.isclose(np.linalg.det(rig.ENGINE_TO_BLENDER), 1.0)
    assert np.allclose(rig.ENGINE_TO_BLENDER @ rig.ENGINE_TO_BLENDER.T, np.eye(3))
    assert np.allclose(rig.to_blender([0, 1, 0]), [0, 0, 1])  # the engine's up is Blender's up
    assert np.allclose(rig.to_blender([[1, 2, 3], [0, 0, 1]]), [[1, -3, 2], [0, -1, 0]])


def test_the_lens_is_the_engines_gate():
    # a vertical fov on a 20.25 mm-tall gate: f = 10.125 / tan(fov / 2)
    for fov in (13.58, 24.0, 32.0):
        assert rig.lens_mm(fov) == pytest.approx(10.125 / math.tan(math.radians(fov) / 2))


def test_the_gate_is_20_25_mm_tall_and_as_wide_as_the_films_aspect():
    assert rig.sensor_mm((1920, 1080)) == pytest.approx((36.0, 20.25))
    assert rig.sensor_mm((1080, 1920)) == pytest.approx((20.25 * 9 / 16, 20.25))
    assert rig.sensor_mm((1080, 1080)) == pytest.approx((20.25, 20.25))


def test_a_camera_looking_down_minus_z_has_the_identity_basis_and_projects_the_target_to_the_centre():
    p = rig.Pose([0, 0, 5], [0, 0, 0], 30)
    assert np.allclose(p.basis(), np.eye(3))
    assert p.project([0, 0, 0]) == pytest.approx((960, 540))
    assert p.depth([0, 0, 0]) == pytest.approx(5)
    assert p.depth([0, 0, 2]) == pytest.approx(3)


def test_project_is_the_pinhole_on_the_films_logical_frame():
    p = rig.Pose([0, 0, 5], [0, 0, 0], 30)
    ty = math.tan(math.radians(15))
    # x: across a half-width of 5 ty (16/9) world units at depth 5; y: up a half-height of 5 ty
    assert p.project([0.4, 0, 0]) == pytest.approx((960 * (1 + 0.4 / (5 * ty * 16 / 9)), 540))
    assert p.project([0, 0.3, 0]) == pytest.approx((960, 540 * (1 - 0.3 / (5 * ty))))
    # a vertical film: the same vertical fov, a narrower frame (aspect 9/16), in its own logical px
    assert p.project([0.1, 0.3, 0], size=(1080, 1920)) == pytest.approx(
        (540 * (1 + 0.1 / (5 * ty * 9 / 16)), 960 * (1 - 0.3 / (5 * ty))))
    pts = np.array([[0.4, 0, 0], [0, 0.3, 0], [0.1, -0.2, 1.0]])
    for size in ((1920, 1080), (1080, 1350)):
        many = p.project_many(pts, size=size)
        for q, m in zip(pts, many):
            assert m == pytest.approx(p.project(q, size=size))
    behind = rig.Pose([0, 0, 1], [0, 0, 0], 24).project_many(np.array([[0, 0, 2.0]]))
    assert np.isnan(behind).all()  # a point behind the camera has no place on the frame


def test_a_roll_turns_the_frame_about_the_view_axis():
    p = rig.Pose([0, 0, 5], [0, 0, 0], 30, roll=90)
    x, y = p.basis()[:, 0], p.basis()[:, 1]
    assert np.allclose(x, [0, 1, 0]) and np.allclose(y, [-1, 0, 0])
    px, py = p.project([0, 0.5, 0])  # world up is the frame's right after a quarter turn
    assert px > 960 and py == pytest.approx(540)


def test_a_rig_between_two_keys_follows_its_ease_and_holds_its_ends():
    r = rig.Rig([{"t": 0, "pos": [0, 0, 4], "target": [0, 0, 0], "fov": 20, "ease": "linear"},
                 {"t": 2, "pos": [2, 0, 4], "target": [1, 0, 0], "fov": 30, "roll": 10, "ease": "linear"}])
    mid = r.at(1.0)  # two keys: the neighbours are mirrored, so the centripetal spline is the straight line
    assert mid.pos == pytest.approx([1, 0, 4]) and mid.target == pytest.approx([0.5, 0, 0])
    assert mid.fov == pytest.approx(25) and mid.roll == pytest.approx(5)
    assert r.at(-1).pos == pytest.approx([0, 0, 4]) and r.at(9).pos == pytest.approx([2, 0, 4])
    eased = rig.Rig([{"t": 0, "pos": [0, 0, 4], "target": [0, 0, 0], "fov": 20},
                     {"t": 2, "pos": [2, 0, 4], "target": [0, 0, 0]}])  # inOutCubic by default
    assert eased.at(0.5).pos[0] == pytest.approx(2 * 4 * 0.25 ** 3)


def test_a_rig_passes_through_every_key_at_its_time():
    keys = [{"t": 0, "pos": [0, 0, 4], "target": [0, 0, 0], "fov": 20},
            {"t": 1, "pos": [1, 0.5, 3.5], "target": [0, 0.2, 0], "fov": 24},
            {"t": 3, "pos": [3, 0, 3], "target": [0, 0, 0], "fov": 18}]
    r = rig.Rig(keys)
    for k in keys:
        p = r.at(k["t"])
        assert p.pos == pytest.approx(k["pos"]) and p.target == pytest.approx(k["target"]) and p.fov == k["fov"]


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


def test_the_eases_are_the_engines_curves():
    assert rig.EASE["inOutCubic"](0.25) == pytest.approx(4 * 0.25 ** 3)
    assert rig.EASE["inOutQuad"](0.75) == pytest.approx(1 - (-2 * 0.75 + 2) ** 2 / 2)
    assert rig.EASE["outExpo"](0.3) == pytest.approx(1 - 2 ** (-3))
    for name, f in rig.EASE.items():
        assert f(0) == pytest.approx(0, abs=1e-12) and f(1) == pytest.approx(1), name


@pytest.mark.skipif(not (REPO / "app/src/engine/util.ts").exists(),
                    reason="the engine's util.ts is not in this checkout")
def test_every_ease_a_key_can_name_is_one_the_engine_has():
    src = (REPO / "app" / "src" / "engine" / "util.ts").read_text()
    body = src[src.index("export const ease = {"):]
    body = body[:body.index("};")]
    for name in rig.EASE:
        assert f"  {name}:" in body, f"util.ts ease has no {name}"
