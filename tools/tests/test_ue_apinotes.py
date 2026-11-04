"""B40: the API_NOTES coverage report runs and finds what it should (it reports; the morning report quotes it)."""
from filmtools.unreal import apinotes


def test_report_finds_uses_and_coverage(tmp_path):
    (tmp_path / "unreal" / "fmbridge").mkdir(parents=True)
    (tmp_path / "docs" / "unreal").mkdir(parents=True)
    (tmp_path / "unreal" / "fmbridge" / "x.py").write_text(
        "import unreal\nunreal.EditorActorSubsystem\nunreal.SystemLibrary.line_trace_single\nunreal.Foo.bar_baz\n")
    (tmp_path / "docs" / "unreal" / "x.md").write_text("| EditorActorSubsystem | LineTraceSingle | SystemLibrary |")
    r = apinotes.report(tmp_path)
    assert set(r["missing"]) == {"Foo", "Foo.bar_baz"}
    assert r["missing"]["Foo.bar_baz"] == ["unreal/fmbridge/x.py:4"]


def test_report_runs_on_the_repo():
    r = apinotes.report()
    assert r["used"] > 50 and 0 <= r["covered"] <= r["used"]
