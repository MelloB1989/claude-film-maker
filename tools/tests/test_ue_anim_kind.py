"""WP4: the `performance` spec kind on the client: the examples validate, plan offline against a state, and every
step names a real op with real arguments; a typo is a schema error."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from filmtools.unreal import spec

EX = Path(__file__).resolve().parents[2] / "examples" / "unreal" / "performance"
STATE = {"fps": 24, "sequence": {"exists": False},
         "actor": {"loc": [0, 0, 0], "yaw": 0, "head_z_cm": 165, "face_mesh": "/Game/MH/Face/FaceMesh"},
         "targets": {"camera": [400, 0, 160], "guest": [150, 220, 160], "desk": [320, 140, 0], "host": [0, 300, 165]},
         "clips": {}, "audio": {"l1": {"duration_s": 3.2, "emphasis": [[1.1, 1.0]], "phrase_ends": []},
                                "l2": {"duration_s": 4.5, "emphasis": [[0.9, 0.8], [2.6, 1.0]], "phrase_ends": [2.0]}},
         "solves": {}, "face": {}}


def test_kind_is_registered_with_its_schema():
    k = spec.kinds()["performance"]
    s = k.schema_doc()
    assert s["additionalProperties"] is False and k.order == 65
    for name, v in s["properties"].items():
        assert name in ("kind", "version", "name", "description") or v.get("description"), name


def test_examples_validate_and_plan_offline():
    docs = spec.load(sorted(EX.glob("*.yaml")))
    assert {d["name"] for d in docs} == {"presenter_intro", "guest_listens"}
    items = spec.plan(docs, state={"performance": {"presenter_intro": STATE, "guest_listens": STATE}})
    assert [i.error for i in items] == [None, None]
    by = {i.name: [s["op"] for s in i.steps] for i in items}
    assert by["presenter_intro"] == ["perf.solve", "perf.solve", "perf.compose"]
    assert by["guest_listens"] == ["perf.compose"]


def test_without_state_it_converges_on_the_bridge():
    docs = spec.load([EX / "listener.yaml"])
    items = spec.plan(docs, state={})
    assert [s["op"] for s in items[0].steps] == ["perf.apply"]


def test_a_typo_is_a_schema_error(tmp_path):
    doc = json.loads(json.dumps(spec.read_docs(EX / "listener.yaml")[0]))
    doc["lines"][0]["gaz"] = []
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(spec.SpecError, match="gaz"):
        spec.load([p])
    doc["lines"][0].pop("gaz")
    doc["lines"][0]["nods"] = [{"at_s": 1, "kind": True}]  # what YAML makes of a bare `yes`
    p.write_text(json.dumps(doc))
    with pytest.raises(spec.SpecError, match="nod"):
        spec.load([p])
