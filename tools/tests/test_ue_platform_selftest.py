"""WP1's selftest (unreal/fmbridge/selftest/platform.py) run on the fake engine with a small stand-in for the
harness's `t` (WP11's real harness runs it the same way on the box): every check the fake can judge passes."""
from __future__ import annotations

import importlib
import inspect

import pytest


class T:
    """Enough of WP11's selftest T: op/check/ok/raises/idempotent/metric/note/skip."""

    def __init__(self, ops):
        self.ops, self.checks, self.metrics, self.notes, self.covered = ops, [], {}, [], set()

    def op(self, name, /, **args):
        self.covered.add(name)
        res = self.ops.call(name, **args)
        if inspect.isgenerator(res):
            return self._gen(res)
        return res

    @staticmethod
    def _gen(g):
        return (yield from g)

    def _rec(self, name, ok, got=None, want=None, detail=""):
        self.checks.append({"name": name, "ok": bool(ok), "got": got, "want": want, "detail": detail})

    def ok(self, name, cond, detail=""):
        self._rec(name, cond, detail=detail)

    def check(self, name, got, want, tol=1e-3):
        self._rec(name, got == want, got, want)

    def raises(self, name, op, /, code=None, **args):
        from fmbridge.errors import OpError
        try:
            self.op(op, **args)
        except OpError as e:
            self._rec(name, code is None or e.code == code, e.code, code)
            return
        self._rec(name, False, "no error", code)

    def idempotent(self, name, op, /, **args):
        self.op(op, **args)
        r = self.op(op, **args)
        self._rec(name, isinstance(r, dict) and r.get("changed") is False, r)

    def metric(self, name, value, unit=""):
        self.metrics[name] = value

    def note(self, text):
        self.notes.append(text)

    def skip(self, reason):
        pytest.skip(reason)


def test_platform_selftest_passes_on_the_fake(fmb, ue, tmp_path, monkeypatch):
    from fmbridge import jobs, server
    from fmbridge.ops import editor
    reg = jobs.Registry(server._run, server._jsonable, str(tmp_path / "journal"), failure=server._failure_detail)
    monkeypatch.setitem(server._state, "registry", reg)
    monkeypatch.setattr(server, "JOURNAL", str(tmp_path / "journal"))
    monkeypatch.setitem(server._state, "throttle_off", True)
    monkeypatch.setitem(server._state, "engine", ue.engine_version)  # server.start() sets it on a box
    monkeypatch.setattr(editor, "_workers", lambda: 0)

    class Clock:  # wait_compile's settle time passes in a few ticks here
        t = 0.0

        @classmethod
        def time(cls):
            cls.t += 1.0
            return cls.t
    monkeypatch.setattr(editor, "time", Clock)
    monkeypatch.setattr(editor, "_rhi_from_log", lambda: "Vulkan RHI ShaderPlatform for SM6: VULKAN_SM6.")
    st = importlib.import_module("fmbridge.selftest.platform")
    t = T(fmb)
    gen = st.run(t)
    extra = None
    for _ in range(100000):  # the harness: one game-thread tick per yield, and the bridge's jobs tick too
        try:
            next(gen)
        except StopIteration as e:
            extra = e.value
            break
        reg.tick()
    failed = [c for c in t.checks if not c["ok"]]
    assert not failed, failed
    assert len(t.checks) >= 25 and extra["engine"] and "wait_compile_s" in t.metrics, [c["name"] for c in t.checks]
    assert {"bridge.health", "editor.describe", "editor.cvar", "editor.console", "editor.idle", "editor.wait_compile",
            "editor.gc", "jobs.list", "jobs.get", "jobs.cancel"} <= t.covered


def test_the_selftest_says_how_long_and_what_it_needs():
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "unreal" / "fmbridge" / "selftest" / "platform.py").read_text()
    doc = ast.get_docstring(ast.parse(src))
    assert "Takes ~" in doc and "Needs:" in doc
