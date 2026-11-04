"""film-ue plan/apply: the spec loader, the generic diff and the built-in kinds against an in-memory editor."""
import json

import pytest

from filmtools.unreal import kinds, spec
from filmtools.unreal.kinds import F, Kind, core, same
from filmtools.unreal.sdk import Unreal


class FakeEditor:
    """Enough of an editor for the core kinds: actors by label, sequences, the open level; answers the kinds' exec
    snippets by running their bound inputs and computing the result here."""

    def __init__(self):
        self.actors, self.seqs, self.level, self.levels, self.calls = {}, {}, "", set(), []

    def transport(self, kind, payload, timeout):
        if kind == "exec":
            return {"ok": True, "result": self._exec(payload["code"])}
        name, a = payload["name"], payload["args"]
        self.calls.append((name, a))
        fn = getattr(self, "op_" + name.replace(".", "_"))
        return {"ok": True, "result": fn(**a)}

    def _exec(self, src):
        ns: dict = {}
        exec("\n".join(line for line in src.splitlines() if line.startswith(("import json", *[f"{k} =" for k in (
            "LABELS", "OWNED", "TAG", "LABEL", "PATH", "PATHS")]))), ns)
        if core.READ_ACTORS in src:
            return {k: dict(v) for k, v in self.actors.items()
                    if k in ns["LABELS"] or (ns["OWNED"] and core.TAG in v["tags"])}
        if core.TAG_ACTOR in src:
            self.actors[ns["LABEL"]]["tags"].append(ns["TAG"])
            return True
        if core.READ_LEVEL in src:
            return {"current": self.level, "exists": ns["PATH"] in self.levels}
        if core.READ_SEQS in src:
            return {p: dict(self.seqs[p]) for p in ns["PATHS"] if p in self.seqs}
        raise AssertionError("unexpected exec")

    def op_level_spawn(self, label, replace=True, shape="", asset="", cls="", loc=(0, 0, 0), rot_=None, scale=None, **_):
        self.actors[label] = {"cls": cls or "StaticMeshActor", "loc": list(loc),
                              "rot": rot_ or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                              "scale": list(scale or [1.0, 1.0, 1.0]), "tags": []}
        return label

    def op_level_move(self, label, loc=None, rot_=None, scale=None, **_):
        a = self.actors[label]
        if loc is not None:
            a["loc"] = list(loc)
        if rot_ is not None:
            a["rot"] = dict(rot_)
        if scale is not None:
            a["scale"] = list(scale)
        return a["loc"]

    def op_level_delete(self, labels):
        return sum(1 for lab in labels if self.actors.pop(lab, None))

    def op_level_new(self, path):
        self.levels.add(path)
        self.level = path
        return path

    def op_level_open(self, path):
        self.level = path
        return path

    def op_seq_new(self, path, start=0, end=120, fps=24, replace=False):
        if path not in self.seqs or replace:
            self.seqs[path] = {"cls": "LevelSequence", "fps": float(fps)}
        self.seqs[path].update(start=start, end=end)
        return {"sequence": path}

    def op_look_fog(self, **a):
        return a


@pytest.fixture
def ed():
    return FakeEditor()


@pytest.fixture
def ue(ed):
    return Unreal(transport=ed.transport)


def write(tmp_path, doc, name="s.json"):
    p = tmp_path / name
    p.write_text(json.dumps(doc))
    return p


SPEC = {"version": 1, "vars": {"root": "/Game/Demo", "fps": 24},
        "level": {"path": "${root}/L_Demo"},
        "actors": [{"name": "Floor", "shape": "plane", "size": [2000, 2000, 100]},
                   {"name": "Key", "cls": "RectLight", "loc": [300, 0, 250], "look_at": [0, 0, 100]}],
        "sequences": [{"path": "${root}/Seq", "end": 96, "fps": "${fps}"}],
        "steps": [{"name": "haze", "op": "look.fog", "args": {"density": 0.02}}]}


def test_same_tolerances():
    assert same([0, 0, 0.4], [0, 0, 0], 0.5) and not same([0, 0, 0.6], [0, 0, 0], 0.5)
    assert same({"yaw": 359.99}, {"yaw": -0.01}, "angle:0.05")
    assert not same(True, 1, 0) and same("a", "a", None)


def test_load_sections_vars_and_types(tmp_path):
    s = spec.load(write(tmp_path, SPEC))
    kinds_ = [r["kind"] for r in s["resources"]]
    assert kinds_ == ["level", "actor", "actor", "sequence", "op"]
    assert s["resources"][0]["path"] == "/Game/Demo/L_Demo"
    assert s["resources"][3]["fps"] == 24  # "${fps}" alone keeps the variable's type
    key = s["resources"][2]
    assert key["rot"]["yaw"] == pytest.approx(180.0) and key["rot"]["pitch"] < 0
    assert s["resources"][1]["scale"] == [20.0, 20.0, 1.0]


def test_load_override_and_include(tmp_path):
    write(tmp_path, {"vars": {"fps": 24}, "sequences": [{"path": "/Game/S", "end": 10, "fps": "${fps}"}]}, "base.json")
    p = write(tmp_path, {"include": ["base.json"], "actors": [{"name": "B", "shape": "cube"}]})
    s = spec.load(p, ["fps=30"])
    assert [r["kind"] for r in s["resources"]] == ["sequence", "actor"] and s["resources"][0]["fps"] == 30


@pytest.mark.parametrize("doc,needle", [
    ({"actorz": []}, "unknown section 'actorz'"),
    ({"actors": [{"name": "A", "shape": "cube", "locc": [0, 0, 0]}]}, "unknown field 'locc'"),
    ({"actors": [{"name": "A", "shape": "cub"}]}, "is not one of"),
    ({"actors": [{"name": "A"}]}, "exactly one of shape, asset, cls"),
    ({"actors": [{"name": "A", "shape": "cube"}, {"name": "A", "shape": "cube"}]}, "named twice"),
    ({"actors": [{"name": "A", "shape": "cube", "loc": "${nope}"}]}, "no variable 'nope'"),
    ({"resources": [{"kind": "actr", "name": "A"}]}, "unknown kind 'actr'"),
])
def test_load_errors_are_actionable(tmp_path, doc, needle):
    with pytest.raises(spec.SpecError) as e:
        spec.load(write(tmp_path, doc))
    assert any(needle in p.message for p in e.value.problems), [p.message for p in e.value.problems]


def test_plan_then_apply_converges_then_noop(tmp_path, ed, ue):
    s = spec.load(write(tmp_path, SPEC))
    acts = spec.plan(s, ue)
    assert [(a.kind, a.action) for a in acts] == [("level", "create"), ("actor", "create"), ("actor", "create"),
                                                  ("sequence", "create"), ("op", "apply")]
    res = spec.apply(s, ue)
    assert res["ok"] and res["converged"], res
    assert ed.level == "/Game/Demo/L_Demo" and ed.actors["Key"]["cls"] == "RectLight"
    assert [a.action for a in spec.plan(s, ue)] == ["noop", "noop", "noop", "noop", "apply"]


def test_update_moves_only_what_changed(tmp_path, ed, ue):
    s = spec.load(write(tmp_path, SPEC))
    spec.apply(s, ue)
    ed.actors["Floor"]["loc"] = [0, 0, 10]
    ed.calls.clear()
    acts = spec.plan(s, ue)
    floor = next(a for a in acts if a.key == "Floor")
    assert floor.action == "update" and floor.changes == [{"field": "loc", "have": [0, 0, 10], "want": [0, 0, 0]}]
    spec.apply(s, ue)
    assert ("level.move", {"label": "Floor", "loc": [0, 0, 0]}) in ed.calls
    assert not any(c[0] == "level.spawn" for c in ed.calls)


def test_class_change_respawns(tmp_path, ed, ue):
    s = spec.load(write(tmp_path, SPEC))
    spec.apply(s, ue)
    ed.actors["Key"]["cls"] = "SpotLight"
    a = next(a for a in spec.plan(s, ue) if a.key == "Key")
    assert a.changes[0]["field"] == "cls" and a.changes[0]["respawn"]


def test_prune_deletes_only_tagged(tmp_path, ed, ue):
    s = spec.load(write(tmp_path, SPEC))
    spec.apply(s, ue)
    ed.op_level_spawn("Hand", cls="PointLight")  # someone else's: no tag
    s2 = spec.load(write(tmp_path, {**SPEC, "actors": SPEC["actors"][:1]}, "s2.json"))
    acts = spec.plan(s2, ue, prune=True)
    assert [(a.kind, a.key) for a in acts if a.action == "delete"] == [("actor", "Key")]
    spec.apply(s2, ue, prune=True)
    assert "Key" not in ed.actors and "Hand" in ed.actors


def test_sequence_fps_change_needs_replace(tmp_path, ed, ue):
    s = spec.load(write(tmp_path, SPEC))
    spec.apply(s, ue)
    s2 = spec.load(write(tmp_path, SPEC, "s3.json"), ["fps=30"])
    a = next(a for a in spec.plan(s2, ue) if a.kind == "sequence")
    assert a.action == "update" and "replace: true" in a.note
    res = spec.apply(s2, ue)
    assert not res["ok"] and any(x.get("error") for x in res["actions"])


def test_a_failing_read_is_reported_not_raised(tmp_path, ue):
    class Broken(Kind):
        name, section = "broken", "brokens"
        fields = {"name": F(str, required=True)}

        def read(self, ue, items):
            raise RuntimeError("no such op")

    reg = kinds.registry([Broken])
    s = spec.load(write(tmp_path, {"brokens": [{"name": "x"}]}), registry=reg)
    (a,) = spec.plan(s, ue, registry=reg)
    assert a.action == "error" and "no such op" in a.error["message"]


def test_plan_text_lists_changes(tmp_path, ue):
    s = spec.load(write(tmp_path, SPEC))
    txt = spec.plan_text(spec.plan(s, ue))
    assert "+ actor        Key" in txt and "5" not in txt.splitlines()[-1] or "create" in txt


def test_every_registered_kind_describes_itself():
    for name in kinds.registry().names():
        d = kinds.registry().get(name).describe()
        assert d["kind"] == name and d["doc"], name
