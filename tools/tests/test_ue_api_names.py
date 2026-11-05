"""editor.api_names: every unreal.<Name> the bridge uses, checked against the live module (here, the fake)."""
import sys

from fakeunreal import run_op


def test_api_names_lists_what_the_module_lacks(fmb, monkeypatch):
    r = run_op("editor.api_names", only_missing=False)
    assert r["checked"] > 100 and "AutomationLibrary" in r["names"] and r["missing"] == {}
    monkeypatch.setattr(sys.modules["fmbridge.ops.doctor"], "_exposed", lambda n: n != "AutomationLibrary")
    r = run_op("editor.api_names")
    assert list(r["missing"]) == ["AutomationLibrary"] and "ops/editor.py" in r["missing"]["AutomationLibrary"]
    assert "names" not in r
