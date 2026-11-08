"""him_flank's pure parts: the medial need against an arm tube, the blended push field, the frame list."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import him_flank as H  # noqa: E402

A = (0.0, 0.0, -1.0)   # the arm hangs along -z
U = (1.0, 0.0, 0.0)    # the spine is toward +x


def test_medial_need_clear_point_needs_nothing():
    assert H.medial_need((6.0, 0.0, 0.0), U, A, R=4.0, margin=0.5) == 0.0      # medial of the tube, 1.5 cm clear
    assert H.medial_need((0.0, 5.0, 0.0), U, A, R=4.0, margin=0.5) == 0.0      # beside it (front), past R + margin


def test_medial_need_past_the_axis_moves_medially():
    # the cloth 2 cm on the LATERAL side of the axis (8 cm deep from the medial edge): it must reach x = 4.5
    assert math.isclose(H.medial_need((-2.0, 0.0, 3.0), U, A, R=4.0, margin=0.5), 6.5)
    # inside, 1 cm medial, 3 cm forward: sqrt(4.5^2 - 9) - 1
    assert math.isclose(H.medial_need((1.0, 3.0, 0.0), U, A, R=4.0, margin=0.5), math.sqrt(4.5 ** 2 - 9) - 1)


def test_field_is_capped_blended_and_local():
    zone = {i: (float(i), 0.0, 0.0) for i in range(20)}       # a 1 cm spaced line
    needs = {0: (6.0, (1.0, 0.0, 0.0))}
    F = H.field(zone, needs, cap=4.0, core=1.5, fall=7.0)
    assert F[0][0] == 4.0 and F[1][0] == 4.0                   # capped, the core flat
    mags = [F[i][0] for i in range(2, 9)]
    assert all(a >= b for a, b in zip(mags, mags[1:]))          # falls off monotonically
    assert 9 not in F and 19 not in F                           # nothing past core + fall
    assert F[3][1] == (1.0, 0.0, 0.0)


def test_parse_frames():
    assert H.parse_frames("0-12:6,84-90:6,422") == [0, 6, 12, 84, 90, 422]
    assert H.parse_frames("0-7:6") == [0, 6, 7]
