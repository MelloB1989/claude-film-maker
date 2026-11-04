"""End to end on the fake engine: the SDK over a transport that runs ops and exec'd code inside fakeunreal the way
the bridge does, so the spec kinds' editor-side snippets, plan/apply convergence and `film-ue selftest` (bridge phase,
client phase, merged report) are exercised with no box."""
import inspect
import json
import subprocess
import uuid

import pytest

from fakeunreal import drive, run_op
from filmtools.unreal import selftest as client_selftest, spec
from filmtools.unreal.sdk import Unreal


class FakeBridge:
    """What fmbridge.server does with /op, /exec and /job, in-process against the fake engine."""

    def __init__(self, fmb):
        self.fmb, self.jobs = fmb, {}

    def _answer(self, fn):
        from fmbridge.errors import OpError
        try:
            res, _ = drive(fn())
            return {"ok": True, "result": json.loads(json.dumps(res, default=str)), "stdout": ""}
        except OpError as e:
            return {"ok": False, **e.to_json(), "error": f"OpError: {e}"}
        except Exception as e:
            import traceback
            return {"ok": False, "error": traceback.format_exc()}

    def __call__(self, kind, payload, timeout):
        if kind == "op":
            r = self._answer(lambda: self.fmb.call(payload["name"], **payload["args"]))
            if payload.get("async"):
                jid = uuid.uuid4().hex[:8]
                self.jobs[jid] = {"done": True, "state": "done" if r["ok"] else "failed", **r}
                return {"ok": True, "job": jid}
            return r
        if kind == "exec":
            def go():
                import unreal
                ns = {"unreal": unreal, "result": None}
                exec(payload["code"], ns)
                return ns["result"]
            return self._answer(go)
        if kind == "job":
            return self.jobs[payload["id"]]
        raise AssertionError(kind)


@pytest.fixture
def ue_sdk(fmb, ue):
    return Unreal(transport=FakeBridge(fmb))


DOCS = [
    {"kind": "level", "version": 1, "path": "/Game/T/L_T"},
    {"kind": "actor", "version": 1, "name": "Floor", "shape": "plane", "size": [1000, 1000, 100]},
    {"kind": "actor", "version": 1, "name": "Box", "shape": "cube", "loc": [0, 0, 50], "rot": {"yaw": 30}},
    {"kind": "actor", "version": 1, "name": "Key", "cls": "PointLight", "loc": [200, 100, 300], "look_at": [0, 0, 50]},
]


def _docs():
    return [spec.jsonschema_lite.defaults(d, spec.kinds()[d["kind"]].schema_doc()) for d in DOCS]


def test_apply_on_the_fake_engine_converges(ue_sdk, ue):
    res = spec.apply(_docs(), ue_sdk)
    assert res["ok"] and res["converged"], json.dumps(res, indent=1, default=str)[:3000]
    assert ue.actor("Key").get_class().get_name() == "PointLight"
    assert round(ue.actor("Box").get_actor_rotation().yaw, 3) == 30.0
    assert spec.pending(spec.plan(_docs(), ue_sdk)) == []
    assert ue.dialogs == []


def test_drift_is_fixed_with_one_move(ue_sdk, ue):
    spec.apply(_docs(), ue_sdk)
    ue_sdk.level.move(label="Box", loc=[30, 0, 50])
    steps = spec.pending(spec.plan(_docs(), ue_sdk))
    assert [(s["op"], s["args"]["label"]) for s in steps] == [("level.move", "Box")]
    spec.apply(_docs(), ue_sdk)
    assert ue.actor("Box").get_actor_location().x == 0


def test_film_ue_selftest_dx_end_to_end(ue_sdk, fmb, tmp_path, monkeypatch):
    def still(camera_label, path, width=1920, height=1080, timeout=60.0):
        """A fake still."""
        yield
        open(path, "wb").write(b"png")
        return path
    monkeypatch.setitem(fmb._OPS, "look.still", still)

    class Done:  # the client phase's CLI calls: answered as the CLI would, from the same fake
        def __init__(self, args):
            if args[-1] == "--json" and "actors" in args:
                self.stdout = json.dumps({"ok": True, "result": ue_sdk.level.actors(contains=args[args.index("--contains") + 1])})
            else:
                self.stdout = json.dumps({"ok": False, "error": {"code": "not_found", "hint": "film-ue level actors"}})
            self.stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: Done(args))
    monkeypatch.setattr(client_selftest, "_pull", lambda paths, dest, log: [str(dest / p.rsplit("/", 1)[-1]) for p in paths])
    s = client_selftest.run_all(ue_sdk, ["dx"], tmp_path / "rep", log=lambda m: None)
    a = s["areas"]["dx"]
    assert s["ok"], json.dumps(s["failures"], indent=1, default=str)[:3000]
    assert a["status"] == "done" and a["failed"] == 0 and a["passed"] >= 20
    assert (tmp_path / "rep" / "summary.md").read_text().startswith("# Selftest report")
    rep = json.loads((tmp_path / "rep" / "dx.json").read_text())
    assert rep["client"]["ok"] and any(c["name"] == "second plan is empty" for c in rep["client"]["checks"])


def test_selftest_unknown_area_says_what_exists(ue_sdk, tmp_path):
    with pytest.raises(SystemExit) as e:
        client_selftest.run_all(ue_sdk, ["dxx"], tmp_path, log=lambda m: None)
    assert "did you mean dx" in str(e.value)
