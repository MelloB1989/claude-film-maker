"""The selftest harness (unreal/fmbridge/selftest) against the fake engine: discovery, the T recorder, REQUIRES,
timeouts, coverage, the scratch level and its cleanup, the report file; and WP11's own selftest run end to end."""
import json
import sys
import types

import pytest

from fakeunreal import drive, run_op


def _module(name, run, **consts):
    m = types.ModuleType(f"fmbridge.selftest.{name}")
    m.__doc__ = f"The {name} test. Takes 1 s. Needs: nothing."
    m.run = run
    for k, v in consts.items():
        setattr(m, k, v)
    sys.modules[m.__name__] = m
    return m


@pytest.fixture
def st(fmb):
    import fmbridge.selftest as st
    yield st
    for k in [k for k in sys.modules if k.startswith("fmbridge.selftest.zz")]:
        del sys.modules[k]


def test_selftest_list_finds_dx(fmb):
    res = run_op("selftest.list")
    assert "dx" in res["areas"] and res["areas"]["dx"]["has_run"]
    assert set(res["capabilities"]) >= {"gpu", "display", "linux", "windows", "epic_login"}


def test_recorder_and_report(st, tmp_path, ue):
    def run(t):
        t.check("eq", 1.0004, 1.0)
        t.check("list", [1, 2, 3.0001], [1, 2, 3])
        t.check("dict subset", {"a": 1, "b": 2}, {"a": 1})
        t.check("wrong", 2, 3)
        t.ok("cond", True)
        t.near("near", 105, 100, rel=0.1)
        t.raises("unknown op", "level.nosuch", code="not_found")
        t.raises("does not fail", "ops.broken")
        t.op("level.spawn", label=t.prefix + "A", shape="cube")
        t.metric("n", 3, "things")
        t.note("hello")
        yield
        return {"x": 1}

    _module("zzrec", run, AREAS=["level"])
    rep, _ = drive(st.run("zzrec", str(tmp_path), keep=False))
    by = {c["name"]: c["ok"] for c in rep["checks"]}
    assert by == {"eq": True, "list": True, "dict subset": True, "wrong": False, "cond": True, "near": True,
                  "unknown op": True, "does not fail": False}
    assert rep["status"] == "done" and not rep["ok"] and rep["passed"] == 6 and rep["failed"] == 2
    assert "level.spawn" in rep["ops_covered"] and "level.move" in rep["ops_missed"]
    assert rep["extra"] == {"x": 1} and rep["metrics"]["n"] == {"value": 3, "unit": "things"}
    on_disk = json.loads((tmp_path / "zzrec.json").read_text())
    assert on_disk["failed"] == 2 and on_disk["area"] == "zzrec"
    assert ue.dialogs == []


def test_requires_unmet_is_skipped(st, tmp_path, monkeypatch):
    _module("zzreq", lambda t: t.ok("never", False), REQUIRES=["gpu"])
    monkeypatch.setattr(st, "capabilities", lambda: {"gpu": False})
    rep, _ = drive(st.run("zzreq", str(tmp_path)))
    assert rep["status"] == "skipped" and rep["ok"] and "gpu" in rep["skipped"] and rep["checks"] == []


def test_skip_and_exception(st, tmp_path):
    _module("zzskip", lambda t: t.skip("no Epic login here"))
    rep, _ = drive(st.run("zzskip", str(tmp_path)))
    assert rep["status"] == "skipped" and rep["skipped"] == "no Epic login here"

    def boom(t):
        t.ok("first", True)
        raise RuntimeError("kaput")
    _module("zzboom", boom)
    rep, _ = drive(st.run("zzboom", str(tmp_path)))
    assert rep["status"] == "error" and not rep["ok"] and "kaput" in rep["errors"][0]["error"]
    assert rep["passed"] == 1  # what ran before the failure is kept


def test_timeout(st, tmp_path, monkeypatch):
    def forever(t):
        while True:
            yield
    _module("zzslow", forever, TIMEOUT=0.0)
    rep, _ = drive(st.run("zzslow", str(tmp_path)), max_ticks=1000)
    assert rep["status"] == "error" and "TIMEOUT" in rep["errors"][0]["error"]


def test_scratch_level_and_cleanup(st, tmp_path, ue):
    seen = {}

    def run(t):
        seen["level"] = st._current_level()
        t.op("level.spawn", label=t.prefix + "A", shape="cube")
    _module("zzlvl", run)
    rep, _ = drive(st.run("zzlvl", str(tmp_path)))
    assert seen["level"] == "/Game/_Selftest/zzlvl/L_zzlvl"
    assert rep["cleaned"] == "/Game/_Selftest/zzlvl"
    assert not st._current_level().startswith("/Game/_Selftest/zzlvl")


def test_missing_area_is_actionable(fmb):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("selftest.run", area="dxx")
    assert e.value.code == "not_found" and "dx" in e.value.candidates


def test_dx_selftest_passes_on_the_fake(fmb, tmp_path, ue, monkeypatch):
    def still(camera_label, path, width=1920, height=1080, timeout=60.0):  # the fake has no renderer
        """A fake still."""
        yield
        open(path, "wb").write(b"\x89PNG fake")
        return path
    monkeypatch.setitem(fmb._OPS, "look.still", still)
    rep = run_op("selftest.run", area="dx", out_dir=str(tmp_path))
    failed = [c for c in rep["checks"] if not c["ok"]]
    assert failed == [] and rep["errors"] == [], (failed, rep["errors"])
    assert rep["status"] == "done" and rep["ok"] and "ops.schema" in rep["ops_covered"]
    assert rep["stills"] == [f"{tmp_path}/stills/dx_box.png".replace("\\", "/")]


def test_selftests_are_311_and_documented():
    """Every selftest module says what it proves, how long it takes and what it needs (CONVENTIONS §10)."""
    import ast
    from pathlib import Path
    d = Path(__file__).resolve().parents[2] / "unreal" / "fmbridge" / "selftest"
    for p in d.glob("*.py"):
        tree = ast.parse(p.read_text(), feature_version=(3, 11))
        if p.stem == "__init__":
            continue
        doc = ast.get_docstring(tree) or ""
        assert "Takes" in doc and "Needs" in doc, f"{p.name}: say 'Takes ~N s/min. Needs: ...' in the docstring"
        assert any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body), f"{p.name}: def run(t)"


def test_op_name_argument_passes_through(st, tmp_path, fmb, monkeypatch):
    def named(*, name: str) -> dict:
        """An op with its own `name` argument."""
        return {"name": name, "changed": False}
    monkeypatch.setitem(fmb._OPS, "zz.named", named)

    def run(t):
        t.check("op", t.op("zz.named", name="a")["name"], "a")
        t.check("call", t.call("zz.named", name="b")["name"], "b")
        t.idempotent("idempotent", "zz.named", name="c")
        t.raises("raises", "zz.named", code="bad_args", name="d", extra=1)
    _module("zzname", run, NEEDS_LEVEL=False)
    rep, _ = drive(st.run("zzname", str(tmp_path)))
    assert rep["errors"] == [] and rep["failed"] == 0, rep["checks"]


def test_still_checks_its_baseline(st, tmp_path, fmb, monkeypatch):
    def still(camera_label, path, width=1920, height=1080, timeout=60.0):
        """A fake still."""
        yield
        open(path, "wb").write(b"png")
        return path
    monkeypatch.setitem(fmb._OPS, "look.still", still)
    monkeypatch.delitem(fmb._OPS, "view.still", raising=False)
    seen = []
    bl = types.ModuleType("fmbridge.qa.baseline")
    bl.check = lambda root, suite, name, path, mode, diff_out, meta: (
        seen.append((suite, name, mode)) or {"status": "different" if name == "b" else "match", "ssim": 0.5,
                                             "thresholds": {"min_ssim": 0.75}})
    import fmbridge.ops.qa as opsqa
    monkeypatch.setitem(sys.modules, "fmbridge.qa.baseline", bl)
    import fmbridge.qa as qa_pkg
    monkeypatch.setattr(qa_pkg, "baseline", bl, raising=False)
    monkeypatch.setattr(opsqa, "baseline_root", lambda: str(tmp_path / "bl"), raising=False)

    def run(t):
        yield from t.still("a", camera="Cam")
        yield from t.still("b", camera="Cam")
    _module("zzbl", run, NEEDS_LEVEL=False)
    rep, _ = drive(st.run("zzbl", str(tmp_path), baseline="compare"))
    by = {c["name"]: c["ok"] for c in rep["checks"]}
    assert by == {"still a": True, "baseline a": True, "still b": True, "baseline b": False}
    assert seen == [("selftest/zzbl", "a", "compare"), ("selftest/zzbl", "b", "compare")]
    assert [b["status"] for b in rep["baselines"]] == ["match", "different"]
