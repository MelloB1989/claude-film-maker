"""film-ue plan/apply: the loader (documents, vars, includes, schemas), the engine (plan, run, converge) and the
generic kinds, against an in-memory editor. Planners are pure, so most of this needs no editor at all."""
import json

import pytest

from filmtools.unreal import jsonschema_lite as js, spec
from filmtools.unreal.kinds import core, same
from filmtools.unreal.sdk import Unreal


class FakeEditor:
    """Enough of an editor for the generic kinds: actors by label and the open level. It answers the kinds' exec
    snippets by evaluating their bound inputs here, and the level ops by changing its own state."""

    def __init__(self):
        self.actors, self.level, self.levels, self.calls = {}, "", set(), []

    def transport(self, kind, payload, timeout):
        if kind == "exec":
            return {"ok": True, "result": self._exec(payload["code"])}
        name, a = payload["name"], payload["args"]
        self.calls.append((name, a))
        fn = getattr(self, "op_" + name.replace(".", "_"), None)
        if fn is None:
            return {"ok": False, "code": "not_found", "message": f"no op {name!r}", "hint": "", "candidates": []}
        return {"ok": True, "result": fn(**a)}

    def _exec(self, src):
        ns: dict = {}
        exec("\n".join(line for line in src.splitlines() if line.startswith(("import json", "LABELS =", "PATH ="))), ns)
        if core.READ_ACTORS in src:
            return {k: json.loads(json.dumps(v)) for k, v in self.actors.items() if k in ns["LABELS"]}
        if core.READ_LEVEL in src:
            return {"current": self.level, "exists": ns["PATH"] in self.levels}
        raise AssertionError("unexpected exec")

    def op_level_spawn(self, label, replace=True, shape="", asset="", cls="", loc=(0, 0, 0), rot_=None, scale=None, **_):
        self.actors[label] = {"cls": cls or "StaticMeshActor", "loc": list(loc),
                              "rot": rot_ or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}, "scale": list(scale or [1, 1, 1])}
        return label

    def op_level_move(self, label, loc=None, rot_=None, scale=None, **_):
        a = self.actors[label]
        a.update({k: v for k, v in (("loc", loc), ("rot", rot_), ("scale", scale)) if v is not None})
        return a["loc"]

    def op_level_new(self, path):
        self.levels.add(path)
        self.level = path

    def op_level_open(self, path):
        self.level = path

    def op_look_fog(self, **a):
        return a


@pytest.fixture
def ed():
    return FakeEditor()


@pytest.fixture
def sdk(ed):
    return Unreal(transport=ed.transport)


YAML = """\
kind: vars
vars: {root: /Game/Demo, height: 250}
---
kind: level
version: 1
name: demo
path: ${root}/L_Demo
---
kind: actor
name: Floor
shape: plane
size: [2000, 2000, 100]
---
kind: actor
name: Key
cls: RectLight
loc: [300, 0, "${height}"]
look_at: [0, 0, 100]
---
kind: op
name: haze
op: look.fog
args: {density: 0.02}
"""


def write(tmp_path, text, name="demo.yaml"):
    p = tmp_path / name
    p.write_text(text if isinstance(text, str) else json.dumps(text))
    return p


# ------------------------------------------------------------------------------------------------- schema / load

def test_jsonschema_lite_basics():
    s = {"type": "object", "required": ["a"], "additionalProperties": False,
         "properties": {"a": {"type": "integer", "minimum": 1}, "b": {"enum": ["x", "y"]},
                        "c": {"$ref": "#/$defs/v"}}, "$defs": {"v": {"type": "array", "items": {"type": "number"}}}}
    assert js.validate({"a": 2, "b": "x", "c": [1, 2.5]}, s) == []
    errs = js.validate({"a": 0, "b": "z", "c": ["q"], "bb": 1}, s)
    msgs = " | ".join(m for _, m, _ in errs)
    assert "should be >= 1" in msgs and "'z' is not one of" in msgs and "should be number" in msgs
    assert ("bb", "unknown field 'bb'", ["b"]) in errs
    assert js.validate({}, s)[0][1] == "needs 'a'"
    assert js.validate(True, {"type": "integer"}) != []  # a bool is not an integer


def test_load_documents_vars_types(tmp_path):
    docs = spec.load(write(tmp_path, YAML))
    assert [(d["kind"], d.get("name") or d.get("path")) for d in docs] == [
        ("level", "demo"), ("actor", "Floor"), ("actor", "Key"), ("op", "haze")]
    assert docs[0]["path"] == "/Game/Demo/L_Demo" and docs[0]["create"] is True  # schema default
    assert docs[2]["loc"] == [300, 0, 250]  # "${height}" alone keeps the int


def test_load_set_and_include(tmp_path):
    write(tmp_path, "kind: actor\nname: A\nshape: cube\nloc: [0, 0, '${z}']\n", "a.yaml")
    p = write(tmp_path, [{"kind": "vars", "vars": {"z": 1}}, {"kind": "include", "files": ["a.yaml"]}], "main.json")
    assert spec.load(p, ["z=7"])[0]["loc"] == [0, 0, 7]


@pytest.mark.parametrize("text,needle", [
    ("kind: actr\nname: A\n", "unknown kind 'actr'"),
    ("kind: actor\nname: A\nshape: cube\nlocc: [0, 0, 0]\n", "unknown field 'locc'"),
    ("kind: actor\nname: A\nshape: cub\n", "is not one of"),
    ("kind: actor\nname: A\n", "exactly one form"),
    ("kind: actor\nname: A\nshape: cube\nloc: [0, 0]\n", "at least 3"),
    ("kind: actor\nname: A\nshape: cube\n---\nkind: actor\nname: A\nshape: cube\n", "again"),
    ("kind: actor\nname: A\nshape: cube\nloc: '${nope}'\n", "no variable 'nope'"),
    ("kind: level\npath: Maps/L\n", "does not match"),
    ("- 1\n", "a mapping with a `kind`"),
])
def test_load_errors_are_actionable(tmp_path, text, needle):
    with pytest.raises(spec.SpecError) as e:
        spec.load(write(tmp_path, text))
    msgs = [p.message for p in e.value.problems]
    assert any(needle in m for m in msgs), msgs
    assert all(p.hint or p.candidates or "again" in p.message or "version" in p.message or "needs" in p.message
               for p in e.value.problems)


def test_misspelt_field_gets_candidate(tmp_path):
    with pytest.raises(spec.SpecError) as e:
        spec.load(write(tmp_path, "kind: actor\nname: A\nshape: cube\nlok_at: [0, 0, 0]\n"))
    assert "look_at" in e.value.problems[0].candidates


# ------------------------------------------------------------------------------------------------- pure planners

def test_plan_actor_pure():
    s = {"name": "K", "cls": "RectLight", "loc": [100, 0, 0], "look_at": [0, 0, 0]}
    (step,) = core.plan_actor(s, None)
    assert step["op"] == "level.spawn" and step["args"]["rot_"]["yaw"] == pytest.approx(180.0)
    have = {"cls": "RectLight", "loc": [100, 0, 0.2], "rot": {"pitch": 0, "yaw": -180.0, "roll": 0}, "scale": [1, 1, 1]}
    assert core.plan_actor(s, have) == []
    have["loc"] = [90, 0, 0]
    (step,) = core.plan_actor(s, have)
    assert step == {"op": "level.move", "args": {"label": "K", "loc": [100.0, 0.0, 0.0]}, "why": "moved: loc"}
    assert core.plan_actor(s, {**have, "cls": "SpotLight"})[0]["op"] == "level.spawn"


def test_plan_level_pure():
    s = {"path": "/Game/L"}
    assert core.plan_level(s, {"current": "/Game/L", "exists": True}) == []
    assert core.plan_level(s, {"current": "/Game/X", "exists": True})[0]["op"] == "level.open"
    assert core.plan_level(s, {"current": "/Game/X", "exists": False})[0]["op"] == "level.new"


def test_same():
    assert same({"yaw": 359.99}, {"yaw": -0.01}, "angle:0.05") and not same(True, 1)
    assert same([0, 0, 0.4], [0, 0, 0], 0.5) and not same([0, 0, 0.6], [0, 0, 0], 0.5)


def test_plan_offline_from_state(tmp_path):
    docs = spec.load(write(tmp_path, YAML))
    st = {"level": {"/Game/Demo/L_Demo": {"current": "/Game/Demo/L_Demo", "exists": True}},
          "actor": {"Floor": {"cls": "StaticMeshActor", "loc": [0, 0, 0], "rot": {}, "scale": [20, 20, 1]}}}
    items = spec.plan(docs, state=st)
    assert [(i.kind, [s["op"] for s in i.steps]) for i in items] == [
        ("level", []), ("actor", []), ("actor", ["level.spawn"]), ("op", ["look.fog"])]


def test_planner_bug_is_caught_at_plan_time(tmp_path, monkeypatch):
    docs = spec.load(write(tmp_path, "kind: actor\nname: A\nshape: cube\n"))
    monkeypatch.setattr(spec.kinds()["actor"], "plan", lambda s, st: [{"op": "level.spawn", "args": {"lable": "A"}}])
    (it,) = spec.plan(docs, state={})
    assert it.error["code"] == "bad_args" and "label" in it.error["candidates"]


# ------------------------------------------------------------------------------------------------- engine

def test_apply_converges_then_plan_is_empty(tmp_path, ed, sdk):
    docs = spec.load(write(tmp_path, YAML))
    res = spec.apply(docs, sdk)
    assert res["ok"] and res["converged"], res
    assert ed.level == "/Game/Demo/L_Demo" and ed.actors["Key"]["cls"] == "RectLight"
    assert ed.actors["Floor"]["scale"] == [20.0, 20.0, 1.0]
    assert spec.pending(spec.plan(docs, sdk)) == []  # the op step is "always": not pending


def test_apply_only_moves_what_drifted(tmp_path, ed, sdk):
    docs = spec.load(write(tmp_path, YAML))
    spec.apply(docs, sdk)
    ed.actors["Floor"]["loc"] = [0, 0, 10]
    ed.calls.clear()
    spec.apply(docs, sdk)
    assert [c for c in ed.calls if c[0].startswith("level.")] == [("level.move", {"label": "Floor", "loc": [0.0, 0.0, 0.0]})]


def test_failing_step_is_reported_with_hint(tmp_path, ed, sdk):
    docs = spec.load(write(tmp_path, "kind: op\nname: x\nop: look.nosuch\n"))
    res = spec.apply(docs, sdk)
    assert not res["ok"] and res["items"][0]["error"]["code"] == "not_found"


def test_failing_describe_marks_items(tmp_path, sdk, monkeypatch):
    def boom(ue, specs):
        raise RuntimeError("bridge says no")
    monkeypatch.setattr(spec.kinds()["actor"], "describe_many", boom)
    docs = spec.load(write(tmp_path, "kind: actor\nname: A\nshape: cube\n"))
    (it,) = spec.plan(docs, sdk)
    assert it.error and "bridge says no" in it.error["message"]


def test_plan_text(tmp_path):
    docs = spec.load(write(tmp_path, YAML))
    txt = spec.plan_text(spec.plan(docs, state={}))
    assert "+ level.new" in txt and "! look.fog" in txt


def test_register_kind_from_a_module_list():
    assert {"level", "actor", "op"} <= set(spec.kinds())
    assert "actor" in spec.kinds_text() and "look_at" in spec.kinds_text("actor")


def test_every_schema_is_valid_json_with_descriptions():
    for p in [spec.SCHEMAS / f"{k}.schema.json" for k in ("level", "actor", "op")]:  # WP11's; others: film-ue dx lint
        s = json.loads(p.read_text())
        assert s.get("additionalProperties") is False, p.name
        for k, v in s.get("properties", {}).items():
            assert k in ("kind", "version", "name", "description") or v.get("description"), f"{p.name}: {k} has no description"


def test_examples_validate():
    ex = spec.SCHEMAS.parents[3] / "examples" / "unreal"
    files = sorted(ex.rglob("*.yaml")) if ex.exists() else []
    for f in files:
        if f.parent.name in ("level", "actor", "op", "demo"):
            spec.load(f)


def test_op_unless_converges():
    s = {"name": "rig", "op": "mh.rig", "args": {"character": "/Game/MH/C"},
         "unless": {"op": "assets.list", "args": {"path": "/Game/MH"}, "has": "0"}}
    assert core.plan_op(s, {"done": True}) == []
    (st,) = core.plan_op(s, {"done": False})
    assert st["op"] == "mh.rig" and not st.get("always")
    assert core.plan_op({"name": "x", "op": "look.fog"}, None)[0]["always"]
    assert core._truthy({"a": [{"b": 1}]}, "a.0.b") and not core._truthy([], "") and not core._truthy({"a": []}, "a")
