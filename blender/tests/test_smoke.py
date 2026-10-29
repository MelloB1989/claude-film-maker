import numpy as np
import pytest

from lib import smoke


def still(times):
    return np.zeros((len(times), 3))


def test_chain_starts_at_the_source_now_and_keeps_its_puffs_on_a_fixed_grid():
    w = smoke.Wisp(rate=24.0, life=1.0)
    te, a = w.ages(2.51)
    assert te[0] == pytest.approx(2.51) and a[0] == 0.0
    assert np.all(np.diff(te) < 0) and len(te) == w.count()
    # the puffs (all but the head) sit on the 1/rate grid of the film's time, whatever the frame
    assert np.allclose(np.round(te[1:] * 24.0), te[1:] * 24.0)
    te2, _ = w.ages(2.0)        # t on the grid: the head is that puff, never doubled
    assert te2[0] > te2[1]


def test_wisp_rises_and_spreads_and_fades_out_over_its_life():
    w = smoke.Wisp(rain=0.0, wind=(0.0, 0.0, 0.0))
    P, a, alpha, width = w.points(5.0, still)
    young, old = a < 0.2, (a > 1.2) & (a < w.lifetime)
    assert P[old, 2].mean() > P[young, 2].mean() + 0.05
    # the thread over the bowl stays narrow and straight; it sways once it curls
    assert np.abs(P[young, :2]).max() < 0.01
    assert np.abs(P[old, :2]).max() > 0.02
    assert width[0] == pytest.approx(w.width[0]) and width[old].mean() > 5 * width[0]
    assert alpha[0] == 0.0 and alpha[a > w.lifetime].max(initial=0.0) == 0.0
    assert alpha.max() <= w.opacity + 1e-9


def test_rain_beats_the_wisp_down_tears_it_and_ends_it_sooner():
    dry, wet = smoke.Wisp(rain=0.0), smoke.Wisp(rain=1.0)
    assert wet.lifetime < dry.lifetime
    te = np.full(40, 3.0)
    age = np.linspace(0.0, 1.4, 40)
    assert wet.offsets(te, age)[-1, 2] < dry.offsets(te, age)[-1, 2]
    _, a, alpha, _ = wet.points(7.3, still)
    _, a0, alpha0, _ = dry.points(7.3, still)
    mid = (a > 0.5) & (a < 1.0)
    assert alpha[mid].min() < 0.5 * alpha0[(a0 > 0.5) & (a0 < 1.0)].min()


def test_the_chain_bends_smoothly_and_follows_where_the_source_was():
    w = smoke.Wisp(rain=0.6)
    moving = lambda times: np.c_[np.asarray(times) * 0.5, np.zeros(len(times)), np.zeros(len(times))]  # noqa: E731
    P, a, _, _ = w.points(4.0, moving)
    assert P[0, 0] == pytest.approx(2.0)
    # an older puff left from further back along the source's path
    assert P[-1, 0] < P[0, 0] - 0.4
    step = np.linalg.norm(np.diff(P, axis=0), axis=1)
    assert step.max() < 0.08   # no jumps between neighbouring puffs


def test_emit_windows_clear_the_puffs_left_outside_them():
    w = smoke.Wisp(emit=((1.0, 1.5),), push=(0.3, 0.0, 0.0))
    assert w.emitting(np.array([0.5, 1.25, 2.0])) == pytest.approx([0.0, 1.0, 0.0])
    _, a, alpha, _ = w.points(1.9, still)
    te = 1.9 - a
    assert alpha[(te < 0.8) | (te > 1.7)].max() == 0.0
    assert alpha[(te > 1.1) & (te < 1.4)].max() > 0.2
    # a breath leaves with a push and moves out before it rises
    off = w.offsets(np.array([1.2]), np.array([0.3]))[0]
    assert off[0] > 0.05


def test_ribbon_faces_the_camera_and_is_as_wide_as_asked():
    P = np.array([(0.0, 0.0, z) for z in np.linspace(0.0, 1.0, 5)])
    width = np.full(5, 0.1)
    V = smoke.ribbon_verts(P, width, cam=(0.0, -5.0, 0.5))
    left, right = V[0::2], V[1::2]
    assert np.linalg.norm(right - left, axis=1) == pytest.approx(width)
    # across the strip runs along x, square to both the chain (z) and the view (y)
    assert np.abs((right - left)[:, 1:]).max() < 1e-9
    assert smoke.strip_faces(3) == [(0, 1, 3, 2), (2, 3, 5, 4)]
