# The Rain Ferry's ending (films/rain-ferry/blender/rf/ending.py): its pure helpers, the walk's feet, the kneel's legs,
# the mouth's flaps, eased keys and paths, without Blender.
import importlib.util
import math
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "films" / "rain-ferry" / "blender" / "rf" / "ending.py"


@pytest.fixture(scope="module")
def E():
    if not SRC.exists():
        pytest.skip("the rain-ferry film is not in this checkout")
    spec = importlib.util.spec_from_file_location("rf_ending", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_kneel_puts_the_knee_ahead_on_the_floor_and_the_hips_over_the_heels(E):
    shin, thigh = 0.42, 0.44
    knee, hip = E.kneel_legs(shin, thigh, 0.075, 0.065, 0.3)
    assert math.hypot(knee, 0.065 - 0.075) == pytest.approx(shin)
    assert math.hypot(knee - hip, 0.3 - 0.065) == pytest.approx(thigh)
    assert knee > 0.35 and abs(hip) < 0.1        # the knee well ahead, the hip joint back over the ankles


def test_the_mouth_moves_only_through_its_lines(E):
    lines = [(1.0, 2.0)]
    assert E.mouth(0.5, lines) == 0.0 and E.mouth(2.5, lines) == 0.0
    flaps = [E.mouth(1.0 + k / 100, lines) for k in range(101)]
    assert max(flaps) > 0.4 and min(flaps) == pytest.approx(0.0, abs=1e-6)
    assert all(0.0 <= v <= 1.0 for v in flaps)


def test_keys_ease_between_and_hold_beyond(E):
    keys = [(1.0, 0.0), (3.0, 10.0)]
    assert E.keys_at(keys, 0.0) == 0.0 and E.keys_at(keys, 9.0) == 10.0
    assert E.keys_at(keys, 2.0) == pytest.approx(5.0)
    assert E.keys_at([(0.0, (0.0, 1.0)), (1.0, (1.0, 0.0))], 0.5) == pytest.approx((0.5, 0.5))


def test_a_path_is_walked_by_length(E):
    path = [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0)]
    assert E.path_length(path) == pytest.approx(3.0)
    (x, y), h = E.path_at(path, 1.0)
    assert (x, y) == pytest.approx((1.0, 0.0)) and h == pytest.approx(0.0)
    (x, y), h = E.path_at(path, 2.5)
    assert (x, y) == pytest.approx((2.0, 0.5)) and h == pytest.approx(math.pi / 2)
    assert E.path_at(path, 9.0)[0] == pytest.approx((2.0, 1.0))

