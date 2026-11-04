"""WP2's selftest (unreal/fmbridge/selftest/assets.py) end to end on the fake engine through WP11's harness: it
reaches the end, covers every assets/mat/fab op but the two it says it skips, and every check passes (the fake
reads the OBJ/glTF it writes for sizes, records sources and derives references, so the checks are real)."""
from __future__ import annotations

from fakeunreal import drive


def test_assets_selftest_runs_clean(fmb, ue, tmp_path, monkeypatch):
    import fmbridge.selftest as st
    monkeypatch.setattr(st, "capabilities", lambda: {"gpu": True, "display": False, "linux": True, "windows": False,
                                                    "epic_login": False})

    class FabBrowserApi(ue.Object):  # a Fab plugin with no sign-in
        def call_method(self, name, args=(), kwargs=None):
            return "" if name == "GetAuthToken" else None
    ue.FabBrowserApi = FabBrowserApi
    rep, _ = drive(st.run("assets", str(tmp_path / "out")), max_ticks=100000)
    bad = [c for c in rep["checks"] if not c["ok"]]
    assert rep["status"] == "done" and not rep["errors"], rep["errors"]
    assert bad == [], bad
    assert rep["passed"] >= 55
    assert set(rep["ops_missed"]) <= {"assets.save_all", "fab.add", "fab.login", "fab.library"}  # no sign-in here
    assert ue.dialogs == []
