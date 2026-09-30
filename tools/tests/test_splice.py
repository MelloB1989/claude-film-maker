import numpy as np
import pytest

from gitloom_film.splice import bar_edges, parse_map, splice

SR = 1000  # 1 kHz keeps the arrays small; bars of 1 s


def bars(values, ch=None):
    y = np.concatenate([np.full(SR, v, np.float32) for v in values])
    return np.stack([y, -y], axis=1) if ch == 2 else y


EDGES = [0.0, 1.0, 2.0, 3.0, 4.0]


def test_parse_map_expands_ranges():
    assert parse_map("0-2,5,3-4") == [0, 1, 2, 5, 3, 4]
    with pytest.raises(ValueError):
        parse_map("3-1")


def test_identity_map_returns_the_source():
    y = bars([0.1, 0.2, 0.3, 0.4])
    assert np.array_equal(splice(y, SR, EDGES, [0, 1, 2, 3]), y)


def test_reorder_keeps_length_and_bar_contents_away_from_joins():
    y = bars([0.1, 0.2, 0.3, 0.4])
    out = splice(y, SR, EDGES, [0, 2, 1, 3], xfade=0.01)
    assert len(out) == len(y)
    assert out[500] == pytest.approx(0.1) and out[1500] == pytest.approx(0.3)
    assert out[2500] == pytest.approx(0.2) and out[3500] == pytest.approx(0.4)


def test_joins_are_crossfaded_not_cut():
    t = np.arange(4 * SR) / SR
    y = (0.5 * np.sin(2 * np.pi * 7.3 * t)).astype(np.float32)  # phase jumps at any reordered join
    out = splice(y, SR, EDGES, [0, 2, 1, 3], xfade=0.02)
    # A hard cut at the first join jumps 0.78 here (0.482 → −0.294). The equal-power fade's worst step is ≈0.09.
    assert np.max(np.abs(np.diff(out))) < 0.15


def test_stereo_and_pre_and_post_roll_are_kept():
    y = np.concatenate([np.full(300, 0.9, np.float32), bars([0.1, 0.2]), np.full(200, 0.7, np.float32)])
    y2 = np.stack([y, -y], axis=1)
    out = splice(y2, SR, [0.3, 1.3, 2.3], [1, 0, 1], xfade=0.01)
    assert out.shape == (300 + 3 * SR + 200, 2)
    assert out[0, 0] == pytest.approx(0.9) and out[-1, 0] == pytest.approx(0.7)  # the last mapped bar is the last source bar
    assert out[300 + 500, 0] == pytest.approx(0.2) and out[300 + 500, 1] == pytest.approx(-0.2)


def test_post_roll_dropped_when_the_map_does_not_end_on_the_last_bar():
    y = np.concatenate([bars([0.1, 0.2]), np.full(200, 0.7, np.float32)])
    out = splice(y, SR, [0.0, 1.0, 2.0], [1, 0], xfade=0.01)
    assert len(out) == 2 * SR


def test_bar_edges_close_a_final_bar_the_grid_overshoots_by_a_few_ms():
    assert bar_edges([0.0, 2.4], 2.4, 7.2) == pytest.approx([0.0, 2.4, 4.8, 7.2])
    assert bar_edges([0.0, 2.4], 2.4, 7.187) == pytest.approx([0.0, 2.4, 4.8, 7.2])  # 13 ms short, as seed 11's is
    assert bar_edges([0.0, 2.4], 2.4, 7.1) == pytest.approx([0.0, 2.4, 4.8])  # 100 ms short is a fragment, not a bar


def test_a_map_can_end_on_a_final_bar_the_file_cuts_a_few_ms_short():
    y = bars([0.1, 0.2, 0.3])[:-10]  # the file ends 10 ms before the third bar's grid line
    edges = bar_edges([0.0, 1.0, 2.0], 1.0, len(y) / SR)
    out = splice(y, SR, edges, [1, 0, 2], xfade=0.01)
    assert len(out) == len(y)
    assert out[500] == pytest.approx(0.2) and out[1500] == pytest.approx(0.1) and out[-1] == pytest.approx(0.3)


def test_a_short_final_bar_can_only_end_the_map():
    y = bars([0.1, 0.2, 0.3])[:-10]
    edges = bar_edges([0.0, 1.0, 2.0], 1.0, len(y) / SR)
    assert len(edges) == 4  # the short bar still counts as a bar
    with pytest.raises(ValueError, match="only end the map"):
        splice(y, SR, edges, [2, 0, 1])  # mid-map it would shift every join after it by the shortfall
