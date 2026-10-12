"""render.py's bpy-free half (lib/cli.py): the shot's source and contract, its frames, the frames a run renders, the
render sizes, the GPU backends, and the exit codes."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib import blank, cli, film, handlers, timing


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


# --------------------------------------------------------------------------------------------- render sizes


def test_parse_size_reads_width_x_height():
    assert cli.parse_size("1920x1080") == (1920, 1080)
    assert cli.parse_size("1080X1920") == (1080, 1920)


@pytest.mark.parametrize("bad", ["1920", "wide", "0x100", "1920x", "-5x5", "19.2x10"])
def test_parse_size_rejects_what_is_not_a_size(bad):
    with pytest.raises(ValueError):
        cli.parse_size(bad)


def test_a_render_size_must_have_the_films_aspect():
    assert cli.check_res((2560, 1440), (1920, 1080)) == (2560, 1440)
    assert cli.check_res((540, 960), (1080, 1920)) == (540, 960)
    assert cli.check_res((1000, 563), (1920, 1080)) == (1000, 563)  # 562.5: within a px of rounding
    for res, size in (((1920, 1000), (1920, 1080)), ((1920, 1080), (1080, 1920)), ((1080, 1080), (1080, 1350))):
        with pytest.raises(ValueError, match="not the film's aspect"):
            cli.check_res(res, size)


@pytest.mark.parametrize("fmt, look, final", [
    ("landscape", (960, 540), (2560, 1440)),  # half and 4/3 of the logical frame
    ("vertical", (540, 960), (1440, 2560)),
    ("square", (540, 540), (1440, 1440)),
    ("portrait", (540, 675), (1440, 1800)),
    ("cinema", (960, 402), (2560, 1072)),
])
def test_each_modes_size_follows_the_films_format(fmt, look, final):
    size = film.FORMATS[fmt]
    assert cli.mode_res("look", size) == look and cli.mode_res("preview", size) == look
    assert cli.mode_res("final", size) == final
    for res in (look, final):
        cli.check_res(res, size)  # each keeps the aspect


# ------------------------------------------------------------------------------------------- the shot itself


def _shot_file(path: Path, text: str = 'SHOT = {"scene": "hero"}\n\ndef build(ctx):\n    pass\n') -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_a_shot_by_name_is_the_films_and_a_path_is_itself(make_film, tmp_path):
    f = film.load("demo", make_film("demo"))
    _shot_file(f.shot_path("hero_orbit"))
    assert cli.shot_source(f, "hero_orbit") == ("hero_orbit", f.root / "blender/shots/hero_orbit.py")
    loose = _shot_file(tmp_path / "elsewhere" / "smoke_cube.py")
    assert cli.shot_source(f, str(loose)) == ("smoke_cube", loose)
    with pytest.raises(FileNotFoundError, match=r"film 'demo' has: hero_orbit"):
        cli.shot_source(f, "nope")
    with pytest.raises(ValueError, match="shot name"):
        cli.shot_source(f, str(_shot_file(tmp_path / "bad name.py")))


def test_the_shot_contract_is_checked():
    def mod(shot, build=lambda ctx: None):
        return SimpleNamespace(SHOT=shot, build=build)

    assert cli.check_shot(mod({"scene": "hero", "track": ["a", "b"], "look": "1,2"})) == {
        "scene": "hero", "track": ["a", "b"], "look": "1,2"}
    assert cli.check_shot(mod({"frames": [0, 20]}))  # explicit frames need no scene
    with pytest.raises(ValueError, match=r"unknown keys \['trak'\]"):
        cli.check_shot(mod({"scene": "hero", "trak": ["a"]}))  # a misspelt key must not pass for "tracks nothing"
    with pytest.raises(ValueError, match="needs a \"scene\""):
        cli.check_shot(mod({"track": []}))
    with pytest.raises(ValueError, match="list of object names"):
        cli.check_shot(mod({"scene": "hero", "track": "corner"}))
    with pytest.raises(ValueError, match="build"):
        cli.check_shot(mod({"scene": "hero"}, build=None))
    with pytest.raises(ValueError, match="SHOT"):
        cli.check_shot(SimpleNamespace(build=lambda ctx: None))


TIMING = timing.Timing([{"id": "open", "start": 0.0, "end": 6.008}, {"id": "hero", "start": 6.008, "end": 9.5}])


def test_a_scene_shot_spans_the_frames_the_engine_shows_its_scene_on():
    assert cli.shot_frames({"scene": "open", "frames": "scene"}, TIMING) == (0, 181)  # frame 180 (6.000 s) is open's
    assert cli.shot_frames({"scene": "hero"}, TIMING) == (181, 285)  # "scene" is the default
    with pytest.raises(KeyError, match="no scene 'nope'.*open, hero"):
        cli.shot_frames({"scene": "nope"}, TIMING)


def test_a_shot_can_name_its_own_frames():
    assert cli.shot_frames({"scene": "anything", "frames": [40, 60]}, TIMING) == (40, 60)
    assert cli.shot_frames({"frames": [0, 20]}, timing.Timing()) == (0, 20)  # no timeline needed
    with pytest.raises(ValueError, match="f1 must be after f0"):
        cli.shot_frames({"frames": [60, 60]}, TIMING)


# ----------------------------------------------------------------------------------------------- parse_args


def test_mode_is_required_except_for_a_scan(capsys):
    assert cli.parse_args(["--shot", "hero_orbit", "--scan"]).scan is True
    a = cli.parse_args(["--film", "demo", "--shot", "hero_orbit", "--mode", "final", "--res", "1440x2560"])
    assert (a.film, a.mode, a.res) == ("demo", "final", (1440, 2560))
    assert cli.parse_args(["--shot", "hero_orbit", "--mode", "preview"]).film is None  # $FILM, else showcase
    with pytest.raises(SystemExit):
        cli.parse_args(["--shot", "hero_orbit"])
    assert "--mode is required" in capsys.readouterr().err


def test_a_scan_can_demand_one_plate_size():
    assert cli.parse_args(["--shot", "hero_orbit", "--scan", "--expect-res", "3840x2160"]).expect_res == (3840, 2160)
    assert cli.parse_args(["--shot", "hero_orbit", "--scan"]).expect_res is None
    with pytest.raises(SystemExit):
        cli.parse_args(["--shot", "hero_orbit", "--scan", "--expect-res", "wide"])


# ------------------------------------------------------------------------------------------------- the GPU

GPU = ["GPU 0"]


def test_the_gpu_backends_are_tried_in_order_and_film_gpu_pins_them():
    assert cli.gpu_backends(None) == cli.GPU_BACKENDS == ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")
    assert cli.gpu_backends("") == cli.GPU_BACKENDS
    assert cli.gpu_backends("cuda") == ("CUDA",)
    assert cli.gpu_backends("OPTIX, cuda") == ("OPTIX", "CUDA")
    assert cli.gpu_backends("none") == () and cli.gpu_backends("CPU") == ()
    with pytest.raises(ValueError, match="FILM_GPU.*VULKAN"):
        cli.gpu_backends("VULKAN")


def test_a_final_without_a_gpu_fails_unless_the_cpu_is_allowed():
    # on the CPU a final runs many times slower and its noise differs from GPU frames
    final = cli.parse_args(["--shot", "hero_orbit", "--mode", "final"])
    with pytest.raises(cli.NoGpuError, match=r"tried OPTIX, CUDA.*--allow-cpu"):
        cli.cycles_device([], require_gpu=cli.requires_gpu(final))
    allowed = cli.parse_args(["--shot", "hero_orbit", "--mode", "final", "--allow-cpu"])
    assert cli.cycles_device([], require_gpu=cli.requires_gpu(allowed)) == "CPU"
    assert cli.cycles_device(GPU, require_gpu=cli.requires_gpu(final)) == "GPU"


def test_previews_look_frames_and_eevee_may_run_without_a_gpu():
    for argv in (["--mode", "preview"], ["--mode", "look"], ["--mode", "final", "--engine", "eevee"]):
        a = cli.parse_args(["--shot", "hero_orbit", *argv])
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
        return [f"out/demo/plates/hero/{f - 40:04d}.exr"]

    def run(self, frames):
        return cli.render_frames(frames, self.render_one, shot="hero", out=self.out.append, err=self.err.append)


def test_a_run_that_writes_every_frame_exits_0():
    r = Run()
    assert r.run([40, 41, 42]) == 0
    assert r.asked == [40, 41, 42] and r.err == []
    assert any("film frame 42" in line and "out/demo/plates/hero/0002.exr" in line for line in r.out)


def test_a_frame_that_stays_blank_stops_the_run_with_exit_3_and_says_how_to_finish_it():
    r = Run({41: blank.BadFrameError("hero", 41, Path("/x/0001.exr"), 3, blank.Fault("blank", "brightest RGB value 0"))})
    assert r.run([40, 41, 42, 44]) == 3
    assert r.asked == [40, 41]  # nothing after it is rendered
    text = "\n".join(r.err)
    assert "film frame 41 is blank" in text and "--frames 41-42,44" in text


def test_a_failed_frame_change_handler_stops_the_run_with_exit_1_and_says_how_to_finish_it():
    failure = handlers.Failure("frame_change_pre pose", 41.25, "IndexError: list index out of range", "Traceback ...")
    r = Run({41: handlers.HandlerError("[hero] film frame 41", [failure])})
    assert r.run([40, 41, 42]) == 1
    assert r.asked == [40, 41]
    text = "\n".join(r.err)
    assert "IndexError: list index out of range" in text and "--frames 41-42" in text


def test_any_other_error_is_left_to_render_py_which_exits_1_with_its_traceback():
    r = Run({40: RuntimeError("Cycles crashed")})
    with pytest.raises(RuntimeError, match="Cycles crashed"):
        r.run([40])
