"""The woven mark (blender/mark) and the weave's choreography: geometry, weave and timing, bpy-free.

  uv run --project tools pytest blender/tests
"""
import math

import numpy as np
import pytest

from lib import timing
from mark import choreo as C, geometry as G, strands as S
from mark.png import read_png

HAVE_REF = G.REFERENCE.exists()


@pytest.fixture(scope="module")
def strands():
    return S.all_strands()


@pytest.mark.skipif(not HAVE_REF, reason="needs the site's mark.png")
def test_the_traced_mark_matches_the_reference_silhouette():
    a = read_png(G.REFERENCE)
    assert a.shape == (256, 256, 4)
    ref = G.reference()
    assert 22000 < ref.sum() < 23000  # the mark's own region, the dust specks gone
    assert G.iou(G.silhouette(), ref) >= 0.97  # acceptance is 0.90 (the Blender render: validate.py)


def test_silhouette_coverage_never_ties_at_the_threshold():
    # 5x5 samples: a pixel's coverage is k/25, never exactly 0.5, so an edge through sample centres cannot flip a column
    cov = G.silhouette()
    assert not np.any(np.isclose(cov, 0.5))


def test_fill_is_exact_for_an_axis_aligned_square():
    sq = np.array([[10.0, 10.0], [20.0, 10.0], [20.0, 20.0], [10.0, 20.0]])
    cov = G.coverage([sq], size=32, ss=5)
    assert cov.sum() == pytest.approx(100.0)
    assert cov[15, 15] == 1.0 and cov[5, 5] == 0.0


def test_every_hidden_colour_change_sits_under_its_crossing(strands):
    p = G.load_params()
    pcs = G.pieces(p)
    for st in strands.values():
        for s_change in st.changes:
            # the change is at a crossing the strand passes under, well inside the over ribbon's half-width
            unders = [(cn, sc) for cn, sc, over in st.crossings if not over]
            cn, sc = min(unders, key=lambda x: abs(x[1] - s_change))
            over = pcs[G.CROSSINGS[cn]["over"]]
            hw = float(min(over.hw(over.s, "a").min(), over.hw(over.s, "b").min()))
            assert abs(s_change - sc) < 0.5 * hw, (st.name, cn, s_change, sc)


def test_over_and_under_lift_apart_at_every_crossing(strands):
    lifts = {}
    for st in strands.values():
        for cn, sc, over in st.crossings:
            i = int(np.argmin(np.abs(st.rings.s - sc)))
            lifts.setdefault(cn, []).append((over, st.zoff[i]))
    assert set(lifts) == set(G.CROSSINGS)
    for cn, ls in lifts.items():
        ups = [z for o, z in ls if o]
        downs = [z for o, z in ls if not o]
        assert ups and downs, cn
        # the two ribbons' faces clear each other: the over one's back is in front of the under one's front
        assert min(ups) - max(downs) >= 2 * S.H, (cn, ls)


def test_rings_never_coincide(strands):
    for st in strands.values():
        assert np.diff(st.rings.s).min() >= S.MIN_GAP * 0.999, st.name


def test_speed_ramp_matches_motion_ts():
    snap = [(0, 1), (1, 1), (1.2, 0.25), (3, 0.25), (3.2, 1)]
    for t in (0, 0.3, 0.8):
        assert C.speed_ramp(t, snap) == pytest.approx(t, abs=1e-12)
    assert C.speed_ramp(3, snap) - C.speed_ramp(1.2, snap) == pytest.approx(0.25 * 1.8, abs=1e-12)
    assert C.speed_ramp(5, snap) - C.speed_ramp(4, snap) == pytest.approx(1, abs=1e-12)
    inst = [(0, 1), (1, 1), (1, 0.25), (2, 0.25), (2, 1)]
    assert C.speed_ramp(2, inst) == pytest.approx(1.25, abs=1e-12)
    assert C.speed_ramp(3, inst) == pytest.approx(2.25, abs=1e-12)


def test_times_come_from_the_data():
    tm = timing.film()
    T = C.times(tm)
    f0, f1 = tm.scene_frames("weave")
    assert (T.f0, T.f1) == (f0, f1)
    downs = tm.downbeats_in(f0, f1)
    assert downs[0] == f0  # the cut is on a downbeat
    assert T.lock_frame == downs[1]  # the lock is the next one
    assert T.l30 < T.lock < T.real < T.settle < T.end
    # the ramp: real time until just before the lock, half speed through it, real time again from the next beat
    lk = C.tau_at(T, T.lock)
    assert C.tau_at(T, T.real) - lk == pytest.approx(C.SLOW * (T.real - T.lock), abs=1e-9)
    assert C.tau_at(T, T.real + 1) - C.tau_at(T, T.real) == pytest.approx(1.0, abs=1e-9)


def test_the_last_pass_crosses_the_stem_on_the_lock_and_everything_rests(strands):
    T = C.times(timing.film())
    lk = C.tau_at(T, T.lock)
    xh = strands["xhook"]
    sb = next(sc for cn, sc, _ in xh.crossings if cn == "B")
    assert C.head(T, "xhook", xh, lk) == pytest.approx(sb, abs=1e-6)
    # every thread is woven in and at rest by the time the picture is back in real time
    for name, st in strands.items():
        w = C.window(T, name, st, C.tau_at(T, T.real + 0.2))
        assert w["s0"] == pytest.approx(st.s_band) and w["s1"] == pytest.approx(st.length), name
        assert w["bt"] == 1.0 and w["bh"] == 1.0 and w["head"] == 0.0 and w["tail"] == 0.0, name


def test_heads_only_move_forward(strands):
    T = C.times(timing.film())
    taus = np.linspace(-1, C.tau_at(T, T.end), 800)
    for name, st in strands.items():
        s1 = np.array([C.head(T, name, st, ta) for ta in taus])
        assert np.all(np.diff(s1) >= -1e-9), name
        assert s1[-1] == pytest.approx(st.length)


def test_the_mark_settles_square_to_the_camera():
    T = C.times(timing.film())
    pose = C.mark_pose(T, C.tau_at(T, T.end))
    assert pose["yaw"] == 0.0 and pose["pitch"] == 0.0 and pose["scale"] == 1.0
    assert math.isclose(C.camera(T, C.tau_at(T, T.settle + 0.5))["x"], C.FINAL_X, abs_tol=1e-3)
