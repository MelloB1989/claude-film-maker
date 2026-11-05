import numpy as np
import pytest

from lib import brushtext


def test_axis_writes_across_left_to_right_and_down_top_to_bottom():
    across = [(x, y) for x in np.linspace(-1, 1, 9) for y in (-0.1, 0.1)]
    o, d, length = brushtext.axis(across)
    assert d == pytest.approx([1.0, 0.0], abs=1e-6) and o[0] == pytest.approx(-1.0) and length == pytest.approx(2.0)
    down = [(x, y) for y in np.linspace(0, 3, 9) for x in (0.0, 0.2)]
    o, d, length = brushtext.axis(down)
    assert d == pytest.approx([0.0, -1.0], abs=1e-6) and o[1] == pytest.approx(3.0) and length == pytest.approx(3.0)
    # a single point: nowhere to go
    assert brushtext.axis([(1, 1)])[2] == 0.0


def test_order_goes_top_first_then_left_to_right():
    top_right = np.array([(1.0, 1.0), (1.2, 0.9)])
    top_left = np.array([(-1.0, 0.98), (-0.8, 0.9)])
    bottom = np.array([(0.0, -1.0), (0.1, -0.9)])
    assert brushtext.order([bottom, top_right, top_left]) == [2, 1, 0]
    assert brushtext.order([]) == []


def test_schedule_fills_the_window_in_turn_by_length():
    times = brushtext.schedule([1.0, 2.0, 1.0], 0.0, 5.0, gap=0.5)
    assert times[0][0] == 0.0
    assert times[-1][0] + times[-1][1] == pytest.approx(5.0)
    assert times[1][1] == pytest.approx(2 * times[0][1])
    for (a, da), (b, _) in zip(times, times[1:]):
        assert b > a + da
    # a dot gets at least a fifth of an average stroke
    dot = brushtext.schedule([0.0, 1.0], 0.0, 1.0, gap=0.0)
    assert dot[0][1] > 0
    # a character's end pauses longer
    plain = brushtext.schedule([1, 1, 1], 0, 3, gap=0.2)
    paused = brushtext.schedule([1, 1, 1], 0, 3, gap=0.2, breaks=[0], break_gap=1.0)
    assert paused[1][0] - (paused[0][0] + paused[0][1]) > plain[1][0] - (plain[0][0] + plain[0][1])
    assert paused[-1][0] + paused[-1][1] == pytest.approx(3.0)
    with pytest.raises(ValueError):
        brushtext.schedule([1], 2.0, 1.0)
