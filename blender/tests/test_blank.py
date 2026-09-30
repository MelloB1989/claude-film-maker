"""The black-frame guard (lib/blank.py): what counts as blank, the retry loop, the shot's opt-out and the test hook.

Expected values are worked out by hand from the rule: a frame is blank when its brightest RGB value is at most 1e-4 in
the linear EXR, or one code value (1/255) in the 8-bit proxy. NaNs are not blank.
"""
import logging
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


def test_a_frame_with_nans_is_not_blank_and_its_nans_are_logged():
    px = np.zeros((4, 6, 4), np.float32)
    px[0, 0, 0] = np.nan
    px[3, 5, 2] = np.nan
    px[1, 1, 3] = np.nan  # alpha is not looked at: not counted
    logged = []
    assert blank.is_blank(px, log=logged.append) is False
    assert len(logged) == 1
    assert "NaN" in logged[0] and "2 of 72" in logged[0]  # 2 NaNs among the 4 x 6 x 3 RGB values


def test_a_frame_of_nothing_but_nans_is_not_blank():
    logged = []
    assert blank.is_blank(np.full((2, 2, 3), np.nan, np.float32), log=logged.append) is False
    assert "12 of 12" in logged[0]


def test_nans_go_to_the_logging_module_when_no_log_is_given(caplog):
    px = np.zeros((2, 2, 3), np.float32)
    px[0, 0, 0] = np.nan
    with caplog.at_level(logging.WARNING):
        assert blank.is_blank(px) is False
    assert any("NaN" in r.getMessage() for r in caplog.records)


def test_a_clean_frame_logs_nothing(caplog):
    with caplog.at_level(logging.DEBUG):
        blank.is_blank(np.zeros((2, 2, 3), np.float32))
        blank.is_blank(np.ones((2, 2, 3), np.float32))
    assert caplog.records == []


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
    with pytest.raises(blank.BlankFrameError) as err:
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
    with pytest.raises(blank.BlankFrameError) as err:
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


def test_a_frame_with_nans_is_not_retried_but_its_nans_are_logged_with_the_frame():
    px = black()
    px[0, 0, 0] = np.nan
    rig = Rig(px)
    assert rig.run() is px
    assert rig.attempts == [1]
    assert len(rig.lines) == 1
    assert "NaN" in rig.lines[0] and "b07_test" in rig.lines[0] and "312" in rig.lines[0]


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
