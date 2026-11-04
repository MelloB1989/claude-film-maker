"""WP9's selftest (unreal/fmbridge/selftest/render.py) run end to end on the fake engine with a tiny stand-in for
WP11's T recorder: it must reach the end with no exception, cover every render op, and its checks that do not need
real pixels must pass. The real run is on the GPU box (film-ue selftest render)."""
from __future__ import annotations

import importlib
import inspect

import pytest

from fakeunreal import drive


class T:
    def __init__(self, fmb):
        self.fmb, self.results, self.covered, self.metrics, self.notes = fmb, [], set(), {}, []
        self.prefix, self.scratch = "ST_render_", "/Game/_Selftest/render"

    def op(self, name, /, **args):
        self.covered.add(name)
        return self.fmb.call(name, **args)

    def check(self, name, got, want, tol=1e-3):
        import json
        ok = json.loads(json.dumps(got, default=str)) == json.loads(json.dumps(want, default=str))
        self.results.append((name, ok, got, want))
        return ok

    def ok(self, name, cond, detail=""):
        self.results.append((name, bool(cond), detail, True))
        return bool(cond)

    def raises(self, name, op, code=None, **args):
        from fmbridge.errors import OpError
        try:
            r = self.op(op, **args)
            if inspect.isgenerator(r):
                drive(r)
        except OpError as e:
            return self.ok(name, code is None or e.code == code)
        return self.ok(name, False)

    def metric(self, name, value, unit=""):
        self.metrics[name] = value

    def note(self, text):
        self.notes.append(text)

    def artifact(self, path):
        pass


def test_selftest_runs_through_on_the_fake(ue, fmb, monkeypatch, tmp_path):
    monkeypatch.setattr(fmb.seq, "cuts", lambda path: [["ST_render_CamA", 0, 24], ["ST_render_CamB", 24, 48]])
    monkeypatch.setattr(fmb.seq, "camera_cuts", lambda path, cuts: [[c, s, 48 if i else 24] for i, (c, s) in enumerate(cuts)])
    monkeypatch.setattr(fmb.seq, "new", lambda **k: ue.add_sequence(k["path"], k["start"], k["end"], k["fps"]) and {})
    monkeypatch.setitem(fmb._OPS, "seq.cuts", fmb.seq.cuts)
    for n in ("level.spawn", "look.light", "look.camera", "level.save"):
        monkeypatch.setitem(fmb._OPS, n, lambda **k: "ok")
    monkeypatch.setattr(fmb.render, "gpu_info", lambda max_age_s=2.0: {"name": "L4", "total_gb": 24.0, "used_gb": 4.0,
                                                                       "free_gb": 20.0, "util_pct": 1})
    ue.add_asset("/Game/_Selftest/render/L_Render", "World")
    st = importlib.import_module("fmbridge.selftest.render")
    monkeypatch.setattr(st, "_out_root", lambda: str(tmp_path / "out"))
    monkeypatch.setattr(st, "_psnr", lambda a, b: 50.0)
    monkeypatch.setattr(st, "_build", lambda t, root, prefix: {
        "seq": (ue.add_sequence(root + "/SEQ_Render", 0, 48, 24,
                                cuts=[["ST_render_CamA", 0, 24], ["ST_render_CamB", 24, 48]]) and root + "/SEQ_Render"),
        "level": "/Game/_Selftest/render/L_Render", "cams": ["ST_render_CamA", "ST_render_CamB"]})
    monkeypatch.setattr(fmb.render, "_write_manifest", lambda q, path: (open(path, "w").write("m") and path)
                        if __import__("os").makedirs(__import__("os").path.dirname(path), exist_ok=True) is None else path)
    monkeypatch.setattr(fmb.render.subprocess, "Popen", _FakeProc)
    t = T(fmb)
    drive(st.run(t), max_ticks=200000)
    failed = [r for r in t.results if not r[1]]
    # the cmdline render and pixel checks need a real engine; everything else must pass on the fake
    allowed = {"command-line render (one process, no editor)"}  # its process is a stub here
    assert [r for r in failed if r[0] not in allowed] == []
    ops = {n for n in fmb._OPS if n.startswith("render.")} - {"render.mrq", "render.progress", "render.concat"}
    if "no ffmpeg" in " ".join(t.notes):
        ops.discard("render.encode")
    print("failed on the fake (expected):", [r[0] for r in failed])
    assert ops <= t.covered, ops - t.covered


class _FakeProc:
    pid = 4242
    returncode = 0

    def __init__(self, argv, **kw):
        self.argv = argv

    def poll(self):
        return 0
