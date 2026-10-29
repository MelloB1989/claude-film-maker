# lib/look_schedule.py: a film's look schedule (data/look.json): the colour arc, each shot's place on it, its rain and
# its overrides, keyed over the shot as the engine keys its post. Films are fixtures under tmp_path (conftest make_film).
import json
from pathlib import Path

import pytest

from lib import film, look_schedule as ls, satsuei

ARC = {
    "cold": {"grade": {"saturation": 0.8, "warmth": -0.1}, "light": {"key": [0.8, 0.8, 1.0], "key_strength": 1.0},
             "satsuei": {"gain": [0.9, 0.9, 0.9]}, "mist": {"density": 0.6}},
    "warm": {"grade": {"saturation": 1.0, "warmth": 0.3}, "light": {"key": [1.0, 0.8, 0.5], "key_strength": 2.0},
             "satsuei": {"gain": [1.0, 1.0, 0.9]}, "mist": {"density": 0.2}},
}


def sched(shots=None, base=None, starts=None):
    return ls.Schedule({"arc": ARC, "base": base or {}, "shots": shots or {}}, starts=starts)


def test_a_shot_blends_the_arc_by_its_warmth():
    s = sched({"a": {}, "b": {"warm": 1}, "c": {"warm": 0.5}})
    a, b, c = (s.shot(x).at(0) for x in "abc")
    assert a.warm == 0 and a.grade.saturation == 0.8 and a.light.key == (0.8, 0.8, 1.0)
    assert b.grade.warmth == pytest.approx(0.3) and b.light.key_strength == 2.0 and b.mist.density == pytest.approx(0.2)
    assert c.grade.saturation == pytest.approx(0.9) and c.light.key == pytest.approx((0.9, 0.8, 0.75))


def test_a_shots_own_fields_override_the_blend_and_the_base_lies_under_it():
    s = sched({"a": {"warm": 1, "grade": {"saturation": 0.5}}}, base={"grade": {"vignette": 0.2, "saturation": 9}})
    g = s.shot("a").at(0).grade
    assert g.saturation == 0.5 and g.vignette == 0.2 and g.warmth == pytest.approx(0.3)
    assert g.contrast == 1.0  # nobody set it: the dataclass's default


def test_an_unnamed_scene_gets_the_base_and_the_cold_end():
    st = sched().shot("nowhere").at(3)
    assert st.warm == 0 and st.grade.saturation == 0.8 and st.rain == ls.Rain()


def test_keys_ease_in_out_sine_and_hold_outside_as_the_engines_trackAt():
    keys = [[1, 0.0], [3, 1.0]]
    assert ls.keys_at(keys, 0) == 0 and ls.keys_at(keys, 5) == 1
    assert ls.keys_at(keys, 2) == pytest.approx(0.5)
    assert ls.keys_at(keys, 1.5) == pytest.approx(0.5 - 0.5 * __import__("math").cos(__import__("math").pi * 0.25))
    s = sched({"a": {"warm": [[0, 0], [2, 1]], "rain": {"density": [[0, 1], [4, 0]]}}})
    sh = s.shot("a")
    assert sh.at(1).warm == pytest.approx(0.5) and sh.at(1).grade.saturation == pytest.approx(0.9)
    assert sh.at(2).rain.density == pytest.approx(0.5) and sh.at(9).rain.density == 0
    assert not sh.at(9).rain.falling and sh.at(0).rain.falling


def test_colours_are_hex_srgb_or_linear_lists_and_come_back_linear_also_keyed():
    s = ls.Schedule({"shots": {"a": {"light": {"accent": "#ffffff", "sky": [[0, "#000000"], [1, [1, 1, 1]]]}}}})
    st = s.shot("a").at(0.5)
    assert st.light.accent == pytest.approx((1, 1, 1)) and st.light.sky == pytest.approx((0.5, 0.5, 0.5))
    with pytest.raises(ValueError, match="light.sky .* not a colour"):
        ls.Schedule({"shots": {"a": {"light": {"sky": "grey"}}}})


def test_a_number_alone_is_the_rain_density_and_drops_scale_the_count():
    st = ls.Schedule({"base": {"rain": {"count": 1000}}, "shots": {"a": {"rain": 0.25}}}).shot("a").at(0)
    assert st.rain.density == 0.25 and st.rain.count == 1000 and st.rain.drops == 250
    assert isinstance(st.rain.count, int)


def test_typos_fail_with_where_they_are():
    with pytest.raises(ValueError, match=r"shots.a: grade has no field satur"):
        ls.Schedule({"shots": {"a": {"grade": {"satur": 1}}}})
    with pytest.raises(ValueError, match=r"shots.a has no colour"):
        ls.Schedule({"shots": {"a": {"colour": 1}}})
    with pytest.raises(ValueError, match="no arcs"):
        ls.Schedule({"arcs": {}})
    with pytest.raises(ValueError, match="cold and warm"):
        ls.Schedule({"arc": {"hot": {}}})
    with pytest.raises(ValueError, match="not a number"):
        ls.Schedule({"shots": {"a": {"warm": "yes"}}})
    with pytest.raises(ValueError, match="lightning lists times"):
        ls.Schedule({"shots": {"a": {"lightning": 2}}})
    ls.Schedule({"//": "a comment", "shots": {"a": {"//": "so is this"}}})


def test_the_satsuei_look_takes_the_base_with_a_setups_own_on_top():
    st = sched({"a": {"satsuei": {"haze_amount": 0.05}}}).shot("a").at(0)
    rim = satsuei.Rim((1, 0), (1, 0.5, 0.2), 0.4)
    look = st.look(rims=[rim], para_from=(0.5, 1), para_to=(0.5, 0), gain=(1, 1, 1))
    assert isinstance(look, satsuei.Look) and look.rims == (rim,) and look.gain == (1, 1, 1)
    assert look.haze_amount == 0.05 and look.haze == st.light.fog  # no haze colour: the fog's
    satsuei.values(look, (960, 540))  # a look the compositor takes


def test_keyed_says_what_moves():
    s = sched({"a": {"rain": {"speed": [[0, 9], [1, 0]]}}, "b": {"warm": [[0, 0], [1, 1]]}, "c": {"warm": 1}})
    a, b, c = (s.shot(x) for x in "abc")
    assert a.keyed() and a.keyed("rain") and a.keyed("rain.speed") and not a.keyed("rain.density")
    assert not a.keyed("grade")
    assert b.keyed("grade.saturation") and b.keyed("light") and not b.keyed("rain")  # the arc's ends disagree on them
    assert not c.keyed()


def test_starts_come_from_the_timeline_for_film_times(make_film):
    repo = make_film("demo", fps=24)
    root = Path(repo) / "films" / "demo"
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "timeline.json").write_text(json.dumps({"scenes": [{"id": "a", "start": 2, "end": 4}]}))
    (root / "data" / "look.json").write_text(json.dumps({"shots": {"a": {"rain": [[0, 1], [1, 0]]}, "x": {}}}))
    s = ls.load(film.load("demo", repo))
    assert s.shot("a").start == 2 and s.shot("a").at_film(3).rain.density == 0
    assert s.check(["a", "b"]) == ["films/demo/data/look.json: shots.x is not a scene of the film",
                                   "films/demo/data/look.json: scene b has no entry (it gets the base and the cold end)"]
    with pytest.raises(ValueError, match="start is not known"):
        s.shot("x").at_film(1)


def test_a_film_without_a_schedule_gets_every_default(make_film):
    repo = make_film("demo")
    st = ls.load(film.load("demo", repo)).shot("any").at(0)
    assert st.grade == ls.Grade() and st.satsuei == ls.Satsuei() and st.warm == 0


def test_the_rain_ferry_schedule_names_every_scene_and_grades_the_arc():
    repo = Path(__file__).resolve().parents[2]
    if not (repo / "films" / "rain-ferry" / "data" / "look.json").exists():
        pytest.skip("no rain-ferry in this checkout")
    f = film.load("rain-ferry", repo)
    s = ls.load(f)
    scenes = [x["id"] for x in json.loads((f.root / "data" / "timeline.json").read_text())["scenes"]]
    assert s.check(scenes) == []
    open_, cross = s.shot("open").at(1), s.shot("cross").at(1)
    assert open_.grade.warmth < 0 < cross.grade.warmth and open_.rain.falling and not cross.rain.falling
    board = s.shot("board")
    assert board.at(0).rain.falling and not board.at(5).rain.falling and board.at(5).warm > 0.3
    assert s.shot("freeze").at(1).rain.speed < 0.5
