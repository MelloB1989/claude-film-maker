"""render.py's bpy-free half (lib/cli.py): the shot's frames, the frames a run renders, --res, and the exit codes.

Expected frames are read off data/vo.json by hand (thread: 0.0 .. 6.008 s, so film frames 0 .. 180).
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib import blank, cli, handlers


def args(mode="preview", frames=None):
    return SimpleNamespace(mode=mode, frames=frames)


# ------------------------------------------------------------------------------------------ frames_to_render


def test_frames_to_render_is_every_frame_of_the_shot_and_not_its_end():
    assert cli.frames_to_render(args(), {}, 40, 45) == [40, 41, 42, 43, 44]


def test_frames_to_render_takes_film_frames_inside_the_shot_only():
    assert cli.frames_to_render(args(frames="44,40"), {}, 40, 45) == [40, 44]
    with pytest.raises(ValueError, match=r"\[45\].*\[40, 45\)"):
        cli.frames_to_render(args(frames="44-45"), {}, 40, 45)  # f1 is the next shot's first frame
    with pytest.raises(ValueError, match=r"\[39\]"):
        cli.frames_to_render(args(frames="39"), {}, 40, 45)


def test_frames_to_render_in_look_mode_falls_back_to_the_shots_look_frames():
    shot = {"look": "41,43"}
    assert cli.frames_to_render(args("look"), shot, 40, 45) == [41, 43]
    assert cli.frames_to_render(args("look", "44"), shot, 40, 45) == [44]  # --frames wins
    assert cli.frames_to_render(args("look"), {"look": [44, 41, 44]}, 40, 45) == [41, 44]  # a list: sorted, once
    assert cli.frames_to_render(args("look"), {}, 40, 43) == [40, 41, 42]  # no look frames: all of them
    assert cli.frames_to_render(args("preview"), shot, 40, 43) == [40, 41, 42]  # look frames are look mode's
    with pytest.raises(ValueError, match=r"\[45\]"):
        cli.frames_to_render(args("look"), {"look": "45"}, 40, 45)


def test_an_empty_frames_is_an_error_not_the_whole_shot():
    # a driver that resumes with --frames "$REMAINING" (blank.frames_spec([]) is "") has nothing left to render: it
    # must not render every frame again, nor in look mode overwrite the finals with look-quality plates
    with pytest.raises(ValueError, match="--frames"):
        cli.frames_to_render(args(frames=""), {}, 40, 45)
    with pytest.raises(ValueError, match="--frames"):
        cli.frames_to_render(args("look", ""), {"look": "41"}, 40, 45)


# ------------------------------------------------------------------------------------------------ parse_res


def test_parse_res_reads_width_x_height():
    assert cli.parse_res("1920x1080") == (1920, 1080)
    assert cli.parse_res("2560X1440") == (2560, 1440)


@pytest.mark.parametrize("bad", ["1920x1000", "1080x1920", "1920", "wide"])
def test_parse_res_takes_16_9_sizes_only(bad):
    with pytest.raises(ValueError):
        cli.parse_res(bad)


# ---------------------------------------------------------------------------------------------- shot_frames


def test_a_scene_shot_spans_the_frames_the_engine_shows_its_scene_on():
    assert cli.shot_frames({"scene": "thread", "frames": "scene"}) == (0, 181)
    assert cli.shot_frames({"scene": "thread"}) == (0, 181)  # "scene" is the default


def test_a_shot_can_name_its_own_frames():
    assert cli.shot_frames({"scene": "_cube", "frames": [40, 60]}) == (40, 60)
    with pytest.raises(ValueError, match="f1 must be after f0"):
        cli.shot_frames({"scene": "_cube", "frames": [60, 60]})


# ----------------------------------------------------------------------------------------------- parse_args


def test_mode_is_required_except_for_a_scan(capsys):
    assert cli.parse_args(["--shot", "b01_thread", "--scan"]).scan is True
    assert cli.parse_args(["--shot", "b01_thread", "--mode", "final"]).mode == "final"
    with pytest.raises(SystemExit):
        cli.parse_args(["--shot", "b01_thread"])
    assert "--mode is required" in capsys.readouterr().err


def test_a_scan_can_demand_one_plate_size():
    assert cli.parse_args(["--shot", "b15_weave", "--scan", "--expect-res", "3840x2160"]).expect_res == (3840, 2160)
    assert cli.parse_args(["--shot", "b15_weave", "--scan"]).expect_res is None
    with pytest.raises(SystemExit):
        cli.parse_args(["--shot", "b15_weave", "--scan", "--expect-res", "3840x2000"])  # not 16:9


# ------------------------------------------------------------------------------------------ the Metal GPU

GPU = ["Apple M4 Max"]


def test_a_final_without_a_metal_gpu_fails_unless_the_cpu_is_allowed():
    # on the CPU a final runs many times slower (the night's budget is gone) and its noise differs from the GPU frames
    final = cli.parse_args(["--shot", "b15_weave", "--mode", "final"])
    with pytest.raises(cli.NoGpuError, match="--allow-cpu"):
        cli.cycles_device([], require_gpu=cli.requires_gpu(final))
    allowed = cli.parse_args(["--shot", "b15_weave", "--mode", "final", "--allow-cpu"])
    assert cli.cycles_device([], require_gpu=cli.requires_gpu(allowed)) == "CPU"
    assert cli.cycles_device(GPU, require_gpu=cli.requires_gpu(final)) == "GPU"


def test_previews_look_frames_and_eevee_may_run_without_the_metal_gpu():
    for argv in (["--mode", "preview"], ["--mode", "look"], ["--mode", "final", "--engine", "eevee"]):
        a = cli.parse_args(["--shot", "b15_weave", *argv])
        assert cli.cycles_device([], require_gpu=cli.requires_gpu(a)) == "CPU", argv
        assert cli.cycles_device(GPU, require_gpu=cli.requires_gpu(a)) == "GPU", argv


# -------------------------------------------------------------------------------- render_frames: exit codes


class Run:
    """A render_one that writes film frames, raises on the ones it is told to, and records what it was asked for."""

    def __init__(self, fail=None):
        self.fail, self.asked, self.out, self.err = fail or {}, [], [], []

    def render_one(self, f):
        self.asked.append(f)
        if f in self.fail:
            raise self.fail[f]
        return [f"out/plates/b07_test/{f - 40:04d}.exr"]

    def run(self, frames):
        return cli.render_frames(frames, self.render_one, shot="b07_test", out=self.out.append, err=self.err.append)


def test_a_run_that_writes_every_frame_exits_0():
    r = Run()
    assert r.run([40, 41, 42]) == 0
    assert r.asked == [40, 41, 42] and r.err == []
    assert any("film frame 42" in line and "out/plates/b07_test/0002.exr" in line for line in r.out)


def test_a_frame_that_stays_blank_stops_the_run_with_exit_3_and_says_how_to_finish_it():
    r = Run({41: blank.BadFrameError("b07_test", 41, Path("/x/0001.exr"), 3, blank.Fault("blank", "brightest RGB value 0"))})
    assert r.run([40, 41, 42, 44]) == 3
    assert r.asked == [40, 41]  # nothing after it is rendered
    text = "\n".join(r.err)
    assert "film frame 41 is blank" in text and "--frames 41-42,44" in text


def test_a_failed_frame_change_handler_stops_the_run_with_exit_1_and_says_how_to_finish_it():
    failure = handlers.Failure("frame_change_pre pose", 41.25, "IndexError: list index out of range", "Traceback ...")
    r = Run({41: handlers.HandlerError("[b07_test] film frame 41", [failure])})
    assert r.run([40, 41, 42]) == 1
    assert r.asked == [40, 41]
    text = "\n".join(r.err)
    assert "IndexError: list index out of range" in text and "--frames 41-42" in text


def test_any_other_error_is_left_to_render_py_which_exits_1_with_its_traceback():
    r = Run({40: RuntimeError("Cycles crashed")})
    with pytest.raises(RuntimeError, match="Cycles crashed"):
        r.run([40])
