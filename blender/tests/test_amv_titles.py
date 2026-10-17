"""The bpy-free parts of the AMV titles stage: plan -> title jobs, ids, frame ranges, options, palettes, easing."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "blender"))
sys.path.insert(0, str(REPO / "tools"))

from amv.titles import common as C  # noqa: E402
from amv.titles import jobs as J  # noqa: E402
from filmtools.amv import plan as P  # noqa: E402

FILM = REPO / "films" / "timeless"
HERO = {"T05_black_lens.0": ("novax", 139, 31), "T06_bully_smirk.0": ("chrome", 172, 31),
        "A03_sunset_mask.0": ("neon", 338, 31), "M08_shuriken.0": ("gold", 624, 34)}


@pytest.fixture(scope="module")
def jobs():
    return J.jobs_from_plan(P.load(FILM))


def test_ids_are_unique_and_shaped(jobs):
    ids = [j.id for j in jobs]
    assert len(ids) == len(set(ids))
    assert all(j.id.startswith("screen.") == j.screen for j in jobs)
    assert [j.id for j in jobs if j.screen] == [f"screen.{i}" for i in range(sum(j.screen for j in jobs))]


def test_hero_titles(jobs):
    by = {j.id: j for j in jobs}
    for tid, (style, f_in, dur) in HERO.items():
        j = by[tid]
        assert (j.style, j.f_in, j.dur) == (style, f_in, dur)
        assert j.frames() == list(range(dur))
        assert j.shot == tid.split(".")[0]
        assert j.comp_frame(0) == f_in and j.comp_frame(dur - 1) == f_in + dur - 1
    assert by["T05_black_lens.0"].spec["tag"] == "THREE GENERATIONS"
    assert by["A03_sunset_mask.0"].spec["sub"] == "ANDREW GARFIELD"


def test_titles_stay_inside_the_edit(jobs):
    dur = P.load(FILM).dur
    assert all(0 <= j.f_in and j.f_in + j.dur <= dur + 10 for j in jobs)


def test_frames_subset_and_names():
    j = J.TitleJob("x.0", "novax", {}, 10, 5)
    assert j.frames([3, 1, 99]) == [1, 3]
    assert j.frame_name(7) == "0007.png"
    assert j.out_dir("/o") == Path("/o/x.0")


def test_select_rejects_unknown_ids(jobs):
    assert [j.id for j in J.select(jobs, ["M08_shuriken.0"])] == ["M08_shuriken.0"]
    assert {j.style for j in J.select(jobs, styles=["sub"])} == {"sub"}
    with pytest.raises(KeyError):
        J.select(jobs, ["nope.0"])


def test_bad_duration_is_an_error():
    class S:
        name = "s"
        titles = [{"style": "novax", "f_in": 0, "spec": {"text": "x"}}]

    class Pl:
        shots = [S()]
        raw = {}

    with pytest.raises(ValueError):
        J.jobs_from_plan(Pl())


def test_opts_size_and_fonts():
    assert C.TitleOpts().size == (1920, 1080)
    assert C.TitleOpts(res_scale=0.5).size == (960, 540)
    o = C.TitleOpts(film_dir=FILM)
    assert C.find_font("anton", o).name == "Anton-Regular.ttf"
    with pytest.raises(FileNotFoundError):
        C.find_font("no-such-font.ttf", o)


def test_colour_and_easing():
    assert C.hex_rgb("#FF8000") == (1.0, pytest.approx(128 / 255), 0.0)
    assert C.lin("#FFFFFF") == (1.0, 1.0, 1.0, 1.0)
    assert C.mix_hex("#000000", "#FFFFFF", 0.5) == "#808080"
    assert C.ease_out_expo(0) == 0 and C.ease_out_expo(1) == 1 and C.ease_out_expo(0.5) > 0.9
    assert C.lin_keys([[0, 10], [10, 20]], 5) == 15 and C.lin_keys([[0, 10], [10, 20]], 99) == 20
    assert C.lin_keys([[0, [0, 0]], [2, [2, 4]]], 1) == [1, 2]
    assert C.ae_to_world(960, 540) == (0.0, 0.0)
    assert set(C.NOVAX_PALETTES) >= {"white_chrome", "blood_red"} and set(C.TPAL) >= {"chrome", "gold", "red"}
