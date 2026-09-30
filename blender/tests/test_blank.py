"""The black-frame guard (lib/blank.py): what counts as blank or bad, the retry loop, the shot's opt-out and the hook.

Expected values are worked out by hand from the rules: a frame is blank when its brightest RGB value is at most 1e-4 in
the linear EXR, or one code value (1/255) in the 8-bit proxy. NaNs are not blank, but a NaN or an infinity anywhere in
RGB makes the frame bad, and so does a black tile in a frame that is otherwise lit.
"""
import warnings
from pathlib import Path

import numpy as np
import pytest

from lib import blank, timing

# ----------------------------------------------------------------------------------------------------- is_blank


def test_an_all_zero_frame_is_blank():
    assert blank.is_blank(np.zeros((4, 6, 4), np.float32)) is True


def test_one_lit_pixel_makes_the_frame_not_blank():
    px = np.zeros((4, 6, 4), np.float32)
    px[2, 3] = (0.02, 0.0, 0.0, 1.0)
    assert blank.is_blank(px) is False


def test_a_very_dark_legitimate_frame_is_not_blank():
    # ink under no light reads about 0.006 on the real plates; here an even dimmer frame, brightest value 0.003
    px = np.zeros((4, 6, 4), np.float32)
    px[..., :3] = np.linspace(0.0, 0.003, 6, dtype=np.float32)[None, :, None]
    px[..., 3] = 1.0
    assert px[..., :3].max() == pytest.approx(0.003)
    assert blank.is_blank(px) is False


def test_the_limit_is_1e_4_and_a_value_at_it_is_still_blank():
    assert blank.BLANK_LINEAR == 1e-4
    at = np.zeros((2, 2, 3))
    at[0, 0, 1] = 1e-4
    assert blank.is_blank(at) is True
    over = np.zeros((2, 2, 3))
    over[0, 0, 1] = 1.01e-4
    assert blank.is_blank(over) is False


def test_a_frame_under_the_limit_is_blank_whatever_its_alpha():
    px = np.zeros((2, 2, 4), np.float32)
    px[..., :3] = 5e-5
    px[..., 3] = 1.0  # a render's alpha is 1 everywhere: it says nothing about whether anything is lit
    assert blank.is_blank(px) is True


@pytest.mark.parametrize("channel", [0, 1, 2])
def test_any_single_rgb_channel_is_enough_to_be_lit(channel):
    px = np.zeros((2, 2, 4), np.float32)
    px[1, 1, channel] = 0.5
    assert blank.is_blank(px) is False


def test_three_channels_are_enough_without_alpha():
    assert blank.is_blank(np.zeros((2, 2, 3), np.float32)) is True


def test_a_frame_with_nans_is_not_blank():
    # not blank: a bad frame is not an empty one (fault() below says what is wrong with it)
    px = np.zeros((4, 6, 4), np.float32)
    px[0, 0, 0] = np.nan
    assert blank.is_blank(px) is False
    assert blank.is_blank(np.full((2, 2, 3), np.nan, np.float32)) is False


def test_infinity_is_bright_not_blank():
    px = np.zeros((2, 2, 3), np.float32)
    px[0, 0, 0] = np.inf
    assert blank.is_blank(px) is False


def test_a_frame_with_no_positive_value_is_blank():
    # the rule is "the brightest value is at most the limit": negatives do not make a lit frame
    assert blank.is_blank(np.full((2, 2, 3), -0.5, np.float32)) is True


def test_an_empty_frame_is_blank():
    assert blank.is_blank(np.zeros((0, 0, 4), np.float32)) is True


def test_an_8_bit_proxy_is_blank_up_to_one_code_value():
    px = np.zeros((2, 2, 4), np.uint8)
    px[..., 3] = 255
    assert blank.is_blank(px) is True
    px[0, 0, 0] = 1  # 1/255
    assert blank.is_blank(px) is True
    px[0, 0, 0] = 2
    assert blank.is_blank(px) is False


def test_an_explicit_limit_replaces_the_default():
    px = np.zeros((2, 2, 3), np.float32)
    px[0, 0, 0] = 0.005
    assert blank.is_blank(px) is False
    assert blank.is_blank(px, limit=0.01) is True


def test_the_pixels_must_be_an_image_with_rgb():
    with pytest.raises(ValueError):
        blank.is_blank(np.zeros((4, 6)))
    with pytest.raises(ValueError):
        blank.is_blank(np.zeros((4, 6, 2)))


def test_peak_is_the_brightest_rgb_value_and_does_not_look_at_alpha():
    px = np.zeros((2, 2, 4), np.float32)
    px[0, 1] = (0.25, 0.75, 0.5, 9.0)
    assert blank.peak(px) == 0.75


def test_peak_steps_over_nans():
    px = np.zeros((2, 2, 3), np.float32)
    px[0, 0, 0] = np.nan
    px[1, 1, 2] = 0.3
    assert blank.peak(px) == pytest.approx(0.3)


def test_peak_of_a_frame_of_nans_is_nan_without_a_warning_and_of_an_empty_frame_minus_infinity():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert np.isnan(blank.peak(np.full((2, 2, 3), np.nan, np.float32)))
    assert blank.peak(np.zeros((0, 0, 3), np.float32)) == -np.inf


# -------------------------------------------------------------------------------------------------------- fault


def ink(h=6, w=10):
    """A frame lit only by the ink world, about 0.006 linear everywhere: dark, but lit."""
    px = np.full((h, w, 4), 0.006, np.float32)
    px[..., 3] = 1.0
    return px


def test_a_dark_lit_frame_of_finite_values_has_no_fault():
    assert blank.fault(ink()) is None
    assert blank.fault(ink(), tile=4) is None


def test_a_frame_with_nans_or_infs_is_bad_and_says_how_many():
    px = ink(4, 6)
    px[0, 0, 0] = np.nan
    px[3, 5, 2] = np.nan
    px[2, 2, 1] = np.inf
    px[1, 1, 3] = np.nan  # alpha is not looked at: not counted
    f = blank.fault(px)
    assert f.kind == "nonfinite"
    for part in ("3 of 72", "2 NaN", "1 inf"):  # among the 4 x 6 x 3 RGB values
        assert part in f.detail


def test_minus_infinity_is_bad_too():
    px = ink()
    px[1, 1, 1] = -np.inf
    assert blank.fault(px).kind == "nonfinite"


def test_a_blank_frame_is_a_blank_fault():
    f = blank.fault(np.zeros((2, 2, 4), np.float32))
    assert f.kind == "blank" and "brightest RGB value 0" in f.detail


def test_a_proxy_is_judged_in_its_own_code_values():
    px = np.zeros((2, 2, 4), np.uint8)
    px[..., 3] = 255
    assert blank.fault(px).kind == "blank"
    px[0, 0, 0] = 2
    assert blank.fault(px) is None


# A 10 x 6 frame in tiles of 4 px. Cycles lays its tiles from the image's bottom-left corner (Blender's first row):
# columns 0-4, 4-8, 8-10 and, counted from the top as the pixels are stored here, rows 2-6 and 0-2. The grid laid
# from the top-left has rows 0-4 and 4-6. A tile that failed is black while the rest of the frame is lit, so the
# frame's brightest value is fine and only the tile shows it.


def test_a_black_tile_is_a_fault_though_the_rest_of_the_frame_is_lit():
    px = ink()
    px[2:6, 4:8, :3] = 0.0  # the middle tile of the bottom row
    f = blank.fault(px, tile=4)
    assert f.kind == "tile"
    assert "x 4-8, y 2-6" in f.detail  # px from the top-left, ends exclusive


def test_the_thin_tiles_at_the_frames_far_edges_are_checked():
    px = ink()
    px[0:2, 8:10, :3] = 0.0  # the top-right tile of Cycles' grid: 2 x 2 px
    assert "x 8-10, y 0-2" in blank.fault(px, tile=4).detail


def test_a_black_tile_on_a_grid_laid_from_the_top_left_is_a_fault_too():
    px = ink()
    px[4:6, 0:4, :3] = 0.0  # inside Cycles' tile at rows 2-6, which stays lit, but a whole tile of the top-left grid
    assert "x 0-4, y 4-6" in blank.fault(px, tile=4).detail


def test_a_black_patch_smaller_than_a_tile_is_not_a_fault():
    px = ink()
    px[2:6, 4:6, :3] = 0.0  # half a tile: a dark object, not a lost tile
    assert blank.fault(px, tile=4) is None


def test_a_frame_that_fits_in_one_tile_is_judged_whole():
    px = ink()
    px[:, :5, :3] = 0.0  # half the frame black, but at the default 2048-px tile this 10 x 6 frame is one tile, lit
    assert blank.fault(px) is None


# ------------------------------------------------------------------------------------------ render_checked

PATH = Path("/repo/out/plates/b07_test/0012.exr")


def lit():
    px = np.zeros((2, 2, 4), np.float32)
    px[0, 0] = (0.8, 0.7, 0.6, 1.0)
    return px


def black():
    return np.zeros((2, 2, 4), np.float32)


class Rig:
    """A render_once that serves a script of frames (the last repeats) and records attempts, pauses and log lines."""

    def __init__(self, *frames):
        self.frames = list(frames)
        self.attempts, self.sleeps, self.lines = [], [], []

    def render_once(self, attempt):
        self.attempts.append(attempt)
        return self.frames[min(len(self.attempts), len(self.frames)) - 1]

    def run(self, **kw):
        return blank.render_checked(self.render_once, shot="b07_test", film_frame=312, path=PATH,
                                    log=self.lines.append, sleep=self.sleeps.append, **kw)


def test_a_lit_frame_is_rendered_once_and_quietly():
    px = lit()
    rig = Rig(px)
    assert rig.run() is px
    assert rig.attempts == [1]
    assert rig.sleeps == []
    assert rig.lines == []


def test_a_blank_frame_is_rendered_again_and_each_attempt_is_logged():
    good = lit()
    rig = Rig(black(), good)
    assert rig.run() is good
    assert rig.attempts == [1, 2]
    assert rig.sleeps == [blank.RETRY_PAUSE]
    assert len(rig.lines) == 2
    first, second = rig.lines
    for part in ("b07_test", "312", "attempt 1 of 3", "blank", str(PATH), "again"):
        assert part in first
    assert "attempt 2 of 3" in second and "lit" in second and "b07_test" in second and "312" in second


def test_the_second_retry_waits_longer_and_can_be_the_one_that_works():
    good = lit()
    rig = Rig(black(), black(), good)
    assert rig.run() is good
    assert rig.attempts == [1, 2, 3]
    assert rig.sleeps == [blank.RETRY_PAUSE, 2 * blank.RETRY_PAUSE]
    assert len(rig.lines) == 3
    assert "attempt 2 of 3" in rig.lines[1] and "blank" in rig.lines[1] and "again" in rig.lines[1]
    assert "attempt 3 of 3" in rig.lines[2] and "lit" in rig.lines[2]


def test_a_frame_that_stays_blank_fails_after_the_first_attempt_and_two_retries():
    rig = Rig(black())
    with pytest.raises(blank.BadFrameError) as err:
        rig.run()
    assert rig.attempts == [1, 2, 3]
    e = err.value
    assert (e.shot, e.film_frame, e.path, e.attempts) == ("b07_test", 312, PATH, 3)
    msg = str(e)
    for part in ("b07_test", "312", str(PATH), "3 attempts"):
        assert part in msg
    assert len(rig.lines) == 3  # every attempt is logged, the last one as the failure
    assert all("blank" in line and "again" in line for line in rig.lines[:2])
    assert "attempt 3 of 3" in rig.lines[2] and "blank" in rig.lines[2] and "giving up" in rig.lines[2]
    assert "again" not in rig.lines[2]


def test_two_retries_is_the_default():
    assert blank.MAX_RETRIES == 2
    assert blank.RETRY_PAUSE > 0  # a spell of GPU contention is not over in a blink


def test_no_retries_fails_on_the_first_blank_frame():
    rig = Rig(black())
    with pytest.raises(blank.BadFrameError) as err:
        rig.run(retries=0)
    assert rig.attempts == [1]
    assert "1 attempt" in str(err.value) and "1 attempts" not in str(err.value)


def test_a_zero_pause_does_not_sleep():
    rig = Rig(black(), lit())
    rig.run(pause=0)
    assert rig.attempts == [1, 2]
    assert rig.sleeps == []


def test_a_declared_black_frame_is_neither_checked_nor_retried():
    px = black()
    rig = Rig(px)
    assert rig.run(black_ok=True) is px
    assert rig.attempts == [1]
    assert rig.sleeps == [] and rig.lines == []


def with_nan():
    px = lit()
    px[1, 1, 0] = np.nan  # a NaN from the denoiser: it would bloom into a black or garbage block in the film
    return px


def with_inf():
    px = lit()
    px[1, 0, 2] = np.inf  # a half-float overflow
    return px


def test_a_frame_with_nans_or_infs_is_retried_and_fails_if_it_stays_bad():
    rig = Rig(with_nan(), with_inf())
    with pytest.raises(blank.BadFrameError) as err:
        rig.run()
    assert rig.attempts == [1, 2, 3]
    e = err.value
    assert (e.shot, e.film_frame, e.path, e.attempts) == ("b07_test", 312, PATH, 3)
    for part in ("b07_test", "312", str(PATH), "3 attempts", "not finite", "inf"):
        assert part in str(e)
    assert "NaN" in rig.lines[0] and "again" in rig.lines[0] and "b07_test" in rig.lines[0] and "312" in rig.lines[0]
    assert "inf" in rig.lines[1] and "again" in rig.lines[1]
    assert "giving up" in rig.lines[2]


def test_a_bad_frame_that_comes_out_clean_on_a_retry_is_kept():
    good = lit()
    rig = Rig(with_nan(), good)
    assert rig.run() is good
    assert rig.attempts == [1, 2]
    assert "NaN" in rig.lines[0] and "again" in rig.lines[0]
    assert "attempt 2 of 3" in rig.lines[1] and "kept" in rig.lines[1]


def test_a_frame_with_a_black_tile_is_retried_and_fails_if_it_stays_bad():
    px = ink()
    px[2:6, 4:8, :3] = 0.0
    rig = Rig(px)
    with pytest.raises(blank.BadFrameError) as err:
        rig.run(tile=4)
    assert rig.attempts == [1, 2, 3]
    assert "black tile" in str(err.value) and "x 4-8, y 2-6" in str(err.value)
    assert "black tile" in rig.lines[0] and "again" in rig.lines[0]


def test_a_declared_black_frame_is_still_bad_with_nans():
    # black_ok says the frame may be black, not that it may hold NaNs: they would bloom in the film all the same
    nan_black = black()
    nan_black[0, 1, 1] = np.nan
    clean_black = black()
    rig = Rig(nan_black, clean_black)
    assert rig.run(black_ok=True) is clean_black
    assert rig.attempts == [1, 2]
    assert "NaN" in rig.lines[0] and "again" in rig.lines[0]


# ------------------------------------------------------------------------------------------------- black_ok


def test_a_shot_without_black_ok_has_no_black_frames():
    ok = blank.black_ok({"scene": "x", "frames": "scene"})
    assert [f for f in range(50) if ok(f)] == []


def test_black_ok_takes_the_frame_spec_that_look_takes():
    ok = blank.black_ok({"black_ok": "0-2, 10,12-13"})
    assert [f for f in range(20) if ok(f)] == [0, 1, 2, 10, 12, 13]


def test_black_ok_takes_a_list_or_a_range_of_film_frames():
    assert [f for f in range(20) if blank.black_ok({"black_ok": [3, 5]})(f)] == [3, 5]
    assert [f for f in range(20) if blank.black_ok({"black_ok": range(4, 8)})(f)] == [4, 5, 6, 7]


def test_black_ok_takes_a_function_of_the_film_frame():
    ok = blank.black_ok({"black_ok": lambda f: f % 10 == 0})
    assert [f for f in range(25) if ok(f)] == [0, 10, 20]
    assert ok(10) is True and ok(11) is False  # always a bool


def test_an_empty_black_ok_is_no_frames():
    for empty in ("", [], range(0), None):
        assert blank.black_ok({"black_ok": empty})(0) is False


def test_a_bad_black_ok_spec_fails_naming_black_ok():
    with pytest.raises(ValueError, match="black_ok"):
        blank.black_ok({"black_ok": "3-1"})
    with pytest.raises(ValueError, match="black_ok"):
        blank.black_ok({"black_ok": "zero"})


# ------------------------------------------------------------------------------------------------ frames_spec


def test_frames_spec_writes_film_frames_the_way_frames_reads_them():
    assert blank.frames_spec([41]) == "41"
    assert blank.frames_spec([41, 42, 43, 50]) == "41-43,50"
    assert blank.frames_spec([1, 3, 5]) == "1,3,5"
    assert blank.frames_spec([7, 8]) == "7-8"
    assert blank.frames_spec([50, 41, 43, 42, 41]) == "41-43,50"  # sorted, each frame once
    assert blank.frames_spec([]) == ""


def test_frames_spec_round_trips_through_parse_frames():
    frames = [2, 3, 9, 10, 11, 40, 100, 101]
    assert timing.parse_frames(blank.frames_spec(frames)) == frames


# -------------------------------------------------------------------------------------- the test hook's env


def test_the_hook_does_nothing_unless_its_variable_is_set():
    assert blank.FORCE_ENV == "GITLOOM_FORCE_BLANK"
    assert blank.parse_force_blank(None) == {}
    assert blank.parse_force_blank("") == {}
    assert blank.parse_force_blank("   ") == {}


def test_the_hook_names_film_frames_and_how_many_attempts_to_blank():
    assert blank.parse_force_blank("41") == {41: 1}  # the first attempt only
    assert blank.parse_force_blank("41:2") == {41: 2}
    assert blank.parse_force_blank(" 41:2 , 43 ") == {41: 2, 43: 1}


@pytest.mark.parametrize("bad", ["x", "41:", "41:0", "41:x", "-3", "41:2:1", "41,,43", "4.5"])
def test_a_mistyped_hook_value_fails_loudly_instead_of_doing_nothing(bad):
    with pytest.raises(ValueError, match="GITLOOM_FORCE_BLANK"):
        blank.parse_force_blank(bad)
