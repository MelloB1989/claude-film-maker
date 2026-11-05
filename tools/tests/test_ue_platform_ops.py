"""WP1's ops on the fake engine: editor.describe/cvar/console/idle/wait_compile/gc, bridge.health, jobs.*."""
from __future__ import annotations

import pytest

from fakeunreal import drive, run_op


def _err(fn):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        fn()
    return e.value


def test_cvar_reads_sets_and_reports_change(fmb, ue):
    assert run_op("editor.cvar", name="t.MaxFPS") == {"name": "t.MaxFPS", "value": "0", "before": "0", "changed": False}
    r = run_op("editor.cvar", name="t.MaxFPS", value=30)
    assert r["value"] == "30" and r["changed"] and "t.MaxFPS 30" in ue.console
    assert run_op("editor.cvar", name="t.MaxFPS", value=30)["changed"] is False  # idempotent
    assert run_op("editor.cvar", name="r.RayTracing", value=False)["value"] == "0"
    e = _err(lambda: run_op("editor.cvar", name="r.Nope", value=1))
    assert e.code == "not_found"
    assert _err(lambda: run_op("editor.cvar", name="two words")).code == "bad_args"


def test_console_runs_but_refuses_what_would_lose_the_sign_in_or_the_editor(fmb, ue):
    assert run_op("editor.console", command="stat unit") == {"command": "stat unit", "ran": True}
    assert "stat unit" in ue.console
    assert _err(lambda: run_op("editor.console", command="Fab.Logout")).code == "conflict"
    assert _err(lambda: run_op("editor.console", command="fab.setenvironment prod")).code == "conflict"
    assert _err(lambda: run_op("editor.console", command="quit")).code == "conflict"
    assert "Fab.Logout" not in ue.console


def test_idle_caps_the_frame_rate_and_viewport(fmb, ue):
    r = run_op("editor.idle", fps=10)
    assert r == {"fps": 10, "realtime": False, "changed": True} and ue.cvars["t.MaxFPS"] == "10"
    assert run_op("editor.idle", fps=10)["changed"] is False


def test_describe_reports_state_and_unsaved_packages(fmb, ue):
    ue.dirty["maps"].append("/Game/Maps/Studio")
    d = run_op("editor.describe")
    assert d["engine"] and d["dirty"] == {"maps": ["/Game/Maps/Studio"], "content": []}
    assert d["max_fps"] == "0" and d["jobs"] == {"queued": 0, "running": 0}
    for k in ("platform", "python", "rhi", "level", "shader_workers", "rss_mb", "uptime_s"):
        assert k in d


def test_wait_compile_ticks_until_the_workers_are_gone_then_finishes(fmb, ue, monkeypatch):
    from fmbridge.ops import editor
    counts = iter([3, 2, 0, 0, 0, 0, 0, 0])
    monkeypatch.setattr(editor, "_workers", lambda: next(counts))
    clock = {"t": 0.0}
    monkeypatch.setattr(editor.time, "time", lambda: clock["t"])
    gen = fmb.call("editor.wait_compile", settle_s=4)  # the generator itself, stepped here
    steps = []
    try:
        while True:
            steps.append(next(gen))
            clock["t"] += 2.0
    except StopIteration as stop:
        res = stop.value
    assert res["workers_max"] == 3 and res["finished"] is True
    assert ue.called("AutomationLibrary.finish_loading_before_screenshot")
    assert any("3 shader workers" in s.get("message", "") for s in steps)


def test_wait_compile_times_out_with_a_hint(fmb, ue, monkeypatch):
    from fmbridge.ops import editor
    monkeypatch.setattr(editor, "_workers", lambda: 5)
    clock = {"t": 0.0}

    def now():
        clock["t"] += 10.0
        return clock["t"]
    monkeypatch.setattr(editor.time, "time", now)
    e = _err(lambda: run_op("editor.wait_compile", timeout_s=30))
    assert e.code == "timeout" and "wait_compile again" in e.hint


def test_wait_compile_without_a_worker_count_still_finishes(fmb, ue, monkeypatch):
    from fmbridge.ops import editor
    monkeypatch.setattr(editor, "_workers", lambda: None)
    res, ticks = drive(fmb.call("editor.wait_compile"))
    assert ticks == 1
    assert res["finished"] and res["workers_max"] == 0


def test_gc_and_bridge_health(fmb, ue):
    r = run_op("editor.gc")
    assert set(r) == {"rss_mb_before", "rss_mb_after"} and ue.called("SystemLibrary.collect_garbage") is not None
    h = run_op("bridge.health")
    assert h["ok"] and h["bridge"] == 2 and "last_tick_s" in h


def test_jobs_ops_list_get_cancel(fmb, ue, tmp_path, monkeypatch):
    from fmbridge import jobs, server
    reg = jobs.Registry(server._run, server._jsonable, str(tmp_path), failure=server._failure_detail)
    monkeypatch.setitem(server._state, "registry", reg)
    j = reg.submit("exec", {"code": "def g():\n    while True:\n        yield\nresult = g()"})
    reg.tick()
    assert [x["id"] for x in run_op("jobs.list", state="running")] == [j.id]
    assert run_op("jobs.get", id=j.id)["state"] == "running"
    assert run_op("jobs.cancel", id=j.id)["changed"] is True
    reg.tick()
    assert run_op("jobs.get", id=j.id)["state"] == "cancelled"
    assert _err(lambda: run_op("jobs.get", id="nope")).code == "not_found"
    assert _err(lambda: run_op("jobs.list", state="sleeping")).code == "bad_args"
    assert _err(lambda: run_op("jobs.cancel", id="nope")).code == "not_found"


def test_workers_counts_processes_on_linux(fmb, monkeypatch, tmp_path):
    import sys
    if not sys.platform.startswith("linux"):
        pytest.skip("linux /proc")
    from fmbridge.ops import editor
    assert isinstance(editor._workers(), int)
