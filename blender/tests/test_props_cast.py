import math

import numpy as np
import pytest

from lib import props, vrm, vrm_rig


def test_kasa_profile_is_a_closed_section_from_the_apex_round_the_brim():
    prof = props.kasa_profile(0.3, 0.12, thickness=0.007, n=10)
    under, over = prof[:10], prof[11:]
    # out along the underside to the brim, back up the top to the apex
    assert np.all(np.diff(under[:, 0]) > 0) and np.all(np.diff(over[:, 0]) < 0)
    assert over[-1][1] == pytest.approx(0.12 * (1 - 0.012 / 0.3) ** 0.8)
    assert under[-1] == pytest.approx((0.3, -0.007))
    # the top always `thickness` over the underside, the brim's edge past both
    assert over[::-1][:, 1] - under[:, 1] == pytest.approx(np.full(10, 0.007))
    assert prof[10][0] > 0.3


def test_kasa_seat_rests_where_the_underside_meets_the_head():
    seat = props.kasa_seat(0.3, 0.12, 0.09)
    assert seat == pytest.approx(0.12 * 0.7 ** 0.8 - 0.007)
    # a wider head sits lower in it; one wider than the hat sits on the brim
    assert props.kasa_seat(0.3, 0.12, 0.11) < seat
    assert props.kasa_seat(0.3, 0.12, 0.5) == pytest.approx(-0.007)


def test_blade_path_runs_from_the_guard_bowed_away_from_its_edge():
    fs = np.linspace(0, 1, 5)
    p = props.blade_path((0, 0, 1.0), (0, -1, 0), 0.3, 0.9, 0.02, (1, 0, 0), fs)
    assert p[0] == pytest.approx((0, -0.3, 1.0))
    assert p[-1] == pytest.approx((0, -1.2, 1.0))
    # the edge below (a blade held level): the middle bowed down by the sori
    assert p[2][2] == pytest.approx(1.0 - 0.02)
    # a straight blade is straight
    q = props.blade_path((0, 0, 0), (0, 0, 1), 0.3, 0.9, 0.0, (1, 0, 0), fs)
    assert q[:, :2] == pytest.approx(np.zeros((5, 2)))


def test_turn_of_undoes_local_rotation():
    rng = np.random.default_rng(3)
    frame = vrm.body_frame((0.1, 0.02, 0.9), (-0.1, 0.0, 0.9))
    for _ in range(5):
        q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        rest = q * np.sign(np.linalg.det(q))
        turn = rng.uniform(-80, 80, 3)
        local = vrm.local_rotation(rest, frame, turn)
        assert vrm_rig.turn_of(rest, frame, local) == pytest.approx(vrm.euler(turn), abs=1e-9)
