import pytest

from filmtools.music_plan import build_plan, default_sections, section_bounds, to_chunks

ORDER = ["open", "problem", "turn", "tour1", "tour2", "drop", "lift", "end"]
STARTS = [0.0, 6.2, 15.1, 28.3, 41.2, 64.2, 69.3, 85.0]
GROOVE = ["warm sub bass", "soft round kick"]
MUSIC = {
    "styles": ["minimal electronic", "minor key"],
    "avoid": ["vocals", "choir"],
    "sections": [
        {"name": "intro", "scene": "open", "styles": ["very quiet", "a low drone"], "avoid": ["drums"]},
        {"name": "build", "scene": "problem", "styles": ["rising tension"], "avoid": ["kick"]},
        {"name": "groove", "scene": "turn", "styles": GROOVE + ["sparse groove"]},
        {"name": "tour", "scene": "tour1", "styles": GROOVE + ["full groove"]},
        {"name": "drop", "scene": "drop", "styles": ["everything drops out"], "avoid": ["drums"], "adherence": "low"},
        {"name": "lift", "scene": "lift", "styles": GROOVE + ["the groove slams back"], "adherence": "low"},
        {"name": "outro", "scene": "end", "styles": ["one big hit", "fading out"]},
    ],
}


def vo_fixture(duration=91.0, starts=STARTS):
    return {"duration": duration,
            "scenes": [{"id": s, "start": starts[i], "end": starts[i + 1] if i + 1 < len(starts) else duration}
                       for i, s in enumerate(ORDER)]}


def test_sections_are_whole_bars_starting_on_the_bar_at_or_before_their_scene():
    plan, meta = build_plan(vo_fixture(), 100, MUSIC)
    bar = 2.4
    assert [s["section_name"] for s in plan["sections"]] == ["intro", "build", "groove", "tour", "drop", "lift",
                                                              "outro"]
    for s in plan["sections"]:
        assert 3000 <= s["duration_ms"] <= 120000
        bars = s["duration_ms"] / 1000 / bar
        assert bars == pytest.approx(round(bars), abs=1e-3)
        assert s["lines"] == []
    starts = {m["name"]: m["start"] for m in meta["sections"]}
    scene = dict(zip(ORDER, STARTS))
    for sec in MUSIC["sections"][1:]:
        assert 0 <= scene[sec["scene"]] - starts[sec["name"]] < bar  # never after its scene's cut
    assert starts["build"] == pytest.approx(4.8)  # 6.2 s is 2.58 bars: bar 2, not the nearer bar 3 (7.2 s)
    assert sum(s["duration_ms"] for s in plan["sections"]) / 1000 >= 91.0
    assert plan["positive_global_styles"] == ["minimal electronic", "minor key", "100 BPM"]  # the tempo is added
    assert plan["negative_global_styles"] == ["vocals", "choir"] and meta["bpm"] == 100


def test_short_section_is_stretched_to_two_bars():
    starts = list(STARTS)
    starts[6] = 65.0  # lift starts 0.8 s after the drop
    plan, _ = build_plan(vo_fixture(starts=starts), 100, MUSIC)
    drop = next(s for s in plan["sections"] if s["section_name"] == "drop")
    assert drop["duration_ms"] == 4800


def test_to_chunks_carries_global_and_local_styles():
    plan, _ = build_plan(vo_fixture(), 100, MUSIC)
    ch = to_chunks(plan)["chunks"]
    assert [c["text"] for c in ch] == ["[Intro]", "[Build]", "[Groove]", "[Tour]", "[Drop]", "[Lift]", "[Outro]"]
    assert [c["duration_ms"] for c in ch] == [s["duration_ms"] for s in plan["sections"]]
    assert ch[0]["positive_styles"][:len(plan["positive_global_styles"])] == plan["positive_global_styles"]
    assert "very quiet" in ch[0]["positive_styles"] and "vocals" in ch[0]["negative_styles"]
    assert [c["context_adherence"] for c in ch] == ["high", "high", "high", "high", "low", "low", "high"]
    assert "drums" in ch[0]["negative_styles"] and "soft round kick" in ch[2]["positive_styles"]


def test_without_sections_the_score_is_one_section_over_the_film():
    plan, meta = build_plan(vo_fixture(duration=30.0), 120, {"styles": ["ambient"]})
    assert [s["section_name"] for s in plan["sections"]] == ["score"]
    assert plan["sections"][0]["duration_ms"] == 30000 and meta["sections"] == [
        {"name": "score", "start": 0.0, "end": 30.0}]


def test_a_long_film_without_sections_is_split_within_the_apis_limit():
    secs = default_sections(300.0, 120)  # 150 bars of 2 s: three sections of 50 bars
    assert [s["name"] for s in secs] == ["score 1", "score 2", "score 3"]
    plan, _ = build_plan(vo_fixture(duration=300.0), 120)
    assert all(s["duration_ms"] <= 120000 for s in plan["sections"])
    assert sum(s["duration_ms"] for s in plan["sections"]) == 300000


def test_a_section_may_start_at_a_time_and_beats_per_bar_set_the_bar():
    vo = vo_fixture(duration=20.0)
    b = section_bounds(vo, [{"name": "a"}, {"name": "b", "at": 7.0}], 120, beats_per_bar=3)  # bars of 1.5 s
    assert b == pytest.approx([0.0, 6.0, 21.0])


def test_a_section_naming_a_scene_the_film_lacks_is_an_error():
    music = {"sections": [{"name": "a", "scene": "open"}, {"name": "b", "scene": "nowhere"}]}
    with pytest.raises(SystemExit, match="'nowhere'"):
        build_plan(vo_fixture(), 100, music)
    with pytest.raises(SystemExit, match="distinct names"):
        build_plan(vo_fixture(), 100, {"sections": [{"name": "a"}, {"name": "a", "at": 10}]})
