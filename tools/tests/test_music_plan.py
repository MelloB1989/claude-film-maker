import pytest

from gitloom_film.music_plan import build_plan, to_chunks

ORDER = ["thread", "ex", "her", "repo", "loom", "diff", "cite", "braid", "merkle", "graph", "honest", "proof",
         "connect", "anywhere", "weave"]
STARTS = [0.0, 6.2, 15.1, 22.0, 28.3, 35.0, 41.2, 47.0, 54.1, 59.0, 64.2, 69.3, 75.1, 80.2, 85.0]


def vo_fixture(duration=91.0, starts=STARTS):
    return {"duration": duration,
            "scenes": [{"id": s, "start": starts[i], "end": starts[i + 1] if i + 1 < len(starts) else duration}
                       for i, s in enumerate(ORDER)]}


def test_sections_are_whole_bars_near_their_scenes():
    plan, meta = build_plan(vo_fixture(), bpm=100)
    bar = 2.4
    assert [s["section_name"] for s in plan["sections"]] == [
        "cold open", "the ex", "her", "the tour", "honest", "proof and everywhere", "weave"]
    for s in plan["sections"]:
        assert 3000 <= s["duration_ms"] <= 120000
        bars = s["duration_ms"] / 1000 / bar
        assert bars == pytest.approx(round(bars), abs=1e-3)
        assert s["lines"] == []
    starts = {m["name"]: m["start"] for m in meta["sections"]}
    assert abs(starts["honest"] - 64.2) <= bar / 2 and abs(starts["her"] - 15.1) <= bar / 2
    assert sum(s["duration_ms"] for s in plan["sections"]) / 1000 >= 91.0
    assert "vocals" in plan["negative_global_styles"] and meta["bpm"] == 100


def test_short_section_is_stretched_to_two_bars():
    starts = list(STARTS)
    starts[11] = 65.0  # proof starts 0.8 s after honest
    plan, _ = build_plan(vo_fixture(starts=starts), bpm=100)
    honest = next(s for s in plan["sections"] if s["section_name"] == "honest")
    assert honest["duration_ms"] == 4800


def test_to_chunks_carries_global_and_local_styles():
    plan, _ = build_plan(vo_fixture(), bpm=100)
    ch = to_chunks(plan)["chunks"]
    assert [c["text"] for c in ch] == ["[Cold Open]", "[The Ex]", "[Her]", "[The Tour]", "[Honest]",
                                       "[Proof And Everywhere]", "[Weave]"]
    assert [c["duration_ms"] for c in ch] == [s["duration_ms"] for s in plan["sections"]]
    assert ch[0]["positive_styles"][:len(plan["positive_global_styles"])] == plan["positive_global_styles"]
    assert "very quiet" in ch[0]["positive_styles"] and "vocals" in ch[0]["negative_styles"]
    assert [c["context_adherence"] for c in ch] == ["high", "high", "high", "high", "low", "low", "high"]


def test_groove_kit_only_where_the_groove_plays():
    plan, _ = build_plan(vo_fixture(), bpm=100)
    ch = {c["text"]: c for c in to_chunks(plan)["chunks"]}
    for quiet in ("[Cold Open]", "[The Ex]", "[Honest]", "[Weave]"):
        assert "soft round kick" not in ch[quiet]["positive_styles"]
    for groove in ("[Her]", "[The Tour]", "[Proof And Everywhere]"):
        assert "soft round kick" in ch[groove]["positive_styles"]
    assert "drums" in ch["[Honest]"]["negative_styles"] and "silence" in ch["[Proof And Everywhere]"]["negative_styles"]
