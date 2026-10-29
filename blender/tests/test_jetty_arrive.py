"""The Rain Ferry's walk up the jetty (films/rain-ferry/blender/rf/jetty_arrive.py): its pure halves."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "films" / "rain-ferry" / "blender"))

from rf import jetty_arrive as ja  # noqa: E402


def test_walk_path_starts_and_stops_on_its_marks_and_never_goes_back():
    ks = [ja.walk_path(t, (0, 0), (4, 0), 0.0, 2.0)[1] for t in [i / 24 for i in range(-5, 60)]]
    assert ks[0] == 0.0 and ks[-1] == 1.0
    assert all(b >= a for a, b in zip(ks, ks[1:]))
    p, _ = ja.walk_path(2.5, (0, 0), (4, 1), 0.0, 2.0)
    assert tuple(p) == pytest.approx((4.0, 1.0))


def test_footfalls_alternate_and_end_with_the_feet_together():
    prints = ja.footfalls(4.6, 0.74, 0.1)
    steps = sorted([(a, "l") for a, _ in prints["left"][1:]] + [(a, "r") for a, _ in prints["right"][1:]])
    assert steps[0][1] == "r"                       # the right foot leads
    assert prints["left"][-1][0] == prints["right"][-1][0] == pytest.approx(4.6)
    assert all(c > 0 for _, c in prints["left"]) and all(c < 0 for _, c in prints["right"])
    gaps = [b[0] - a[0] for a, b in zip(steps, steps[1:]) if b[0] > a[0]]
    assert max(gaps) - min(gaps) < 1e-9 and abs(max(gaps) - 0.74) < 0.74 / 4    # even steps, near the stride


def test_a_foot_is_planted_until_the_body_passes_it_then_swings_up_and_over():
    prints = ja.footfalls(3.0, 0.75, 0.1)["right"]
    assert ja.foot_at(prints, 0.0, 0.75) == (0.0, -0.1, 0.0)
    a0, b0 = prints[0][0], prints[1][0]
    mid = (a0 + b0) / 2
    along, _, h = ja.foot_at(prints, mid, 0.75)
    assert a0 < along < b0 and h == pytest.approx(ja.LIFT)
    assert ja.foot_at(prints, 10.0, 0.75)[2] == 0.0
    # it never moves backwards as the body goes on
    xs = [ja.foot_at(prints, d / 50, 0.75)[0] for d in range(0, 160)]
    assert all(b >= a - 1e-12 for a, b in zip(xs, xs[1:]))
