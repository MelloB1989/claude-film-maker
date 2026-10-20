"""The AMV scene's geometry without Blender: screen -> world, and the per-frame plane keys must put every layer corner
where the plan's `Shot.matrix(f)` (After Effects' transform) puts it."""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "blender"))
sys.path.insert(0, str(ROOT / "tools"))

from amv import scene as S  # noqa: E402
from filmtools.amv import plan as amv_plan  # noqa: E402

PLAN = ROOT / "films" / "timeless"


def test_screen_world_mapping():
    assert S.screen_to_world(0, 0) == (-9.6, 5.4)
    assert S.screen_to_world(1920, 1080) == pytest.approx((9.6, -5.4))
    assert S.screen_to_world(960, 540) == pytest.approx((0, 0))
    for x, y in ((12.5, 700.0), (1900, 3)):
        assert S.world_to_screen(*S.screen_to_world(x, y)) == pytest.approx((x, y))


def fake_plan():
    n = 12
    shot = {"name": "X", "a": 5, "b": 10, "end": 12, "src": "c", "tile": [130, 160],
            "px": [960 + 40 * i for i in range(n)], "py": [540 - 15 * i for i in range(n)],
            "s": [100 + 30 * i for i in range(n)], "rz": [-7 * i for i in range(n)], "remap": [0] * n}
    return amv_plan.Plan(raw={"dur": 20, "fps": 30, "shots": [shot]}, root=Path("."), shots=[amv_plan.Shot(0, shot)])


def check_shot(shot, frames):
    canvas = shot.canvas
    for f in frames:
        m = shot.matrix(f)
        pose = S.plane_pose(*shot.transform(f))
        for lx, ly in ((0, 0), (1920, 0), (1920, 1080), (0, 1080), (960, 540), (333.3, 801.7)):
            want = (m[0][0] * lx + m[0][1] * ly + m[0][2], m[1][0] * lx + m[1][1] * ly + m[1][2])
            got = S.layer_point_to_screen(pose, canvas, lx, ly)
            assert got == pytest.approx(want, abs=1e-6), (shot.name, f, lx, ly)


def test_keys_reproduce_the_matrix_synthetic():
    plan = fake_plan()
    check_shot(plan.shots[0], S.key_frames(plan.shots[0]))


@pytest.mark.skipif(not (PLAN / "amv" / "plan.json").exists(), reason="no timeless plan")
def test_keys_reproduce_the_matrix_timeless():
    plan = amv_plan.load(PLAN)
    for shot in plan.shots:
        check_shot(shot, S.key_frames(shot)[::3] + [shot.end])


def test_canvas_corners_are_relative_to_the_anchor():
    c = (2496, 1728, 288, 324)
    corners = S.canvas_corners(c)
    assert corners[0] == pytest.approx((-(960 + 288) / 100, (540 + 324) / 100))
    assert corners[2] == pytest.approx(((2496 - 1248) / 100, -(1728 - 864) / 100))


def test_opacity_keys_are_zero_outside_the_shot():
    plan = fake_plan()
    s = plan.shots[0]
    keys = dict(S.opacity_keys(s))
    assert keys[s.a - 1] == 0 and keys[s.end] == 0 and keys[s.a] == 1.0 and keys[s.end - 1] == 1.0


def test_wm_keys_fade_under_titles():
    plan = amv_plan.Plan(raw={"wm_hide": [[77, 104]]}, root=Path("."))
    k = dict(S.wm_keys(plan))
    assert k[0] == 62 and k[77] == 0 and k[104] == 0 and k[107] == 62 and k[74] == 62


def test_star_polygon_has_tips_up_first():
    pts = S.star_polygon(40, 4, 0)
    assert len(pts) == 8 and pts[0] == pytest.approx((0, -40)) and math.hypot(*pts[1]) == pytest.approx(4)


def test_parse_frames():
    assert S.parse_frames("3-5,9") == [3, 4, 5, 9]


def test_magenta_fraction_and_absolute_paths(tmp_path, monkeypatch):
    import numpy as np
    px = np.zeros((10, 10, 4), np.uint8)
    px[:3] = (255, 0, 255, 255)
    assert S.magenta_fraction(px) == pytest.approx(0.3) and S.magenta_fraction(px) > S.MAGENTA_LIMIT
    assert S.magenta_fraction(np.full((4, 4, 3), 128, np.uint8)) == 0.0
    monkeypatch.chdir(tmp_path)
    assert S.absolute("out/layers") == str((tmp_path / "out" / "layers").resolve())
    assert S.absolute(None) is None
