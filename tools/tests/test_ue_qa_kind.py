"""The qa spec kind: pure planning, the schema, the example."""
import json
from pathlib import Path

import pytest
import yaml

from filmtools.unreal import qa_kinds

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "tools/filmtools/unreal/schemas/qa.schema.json").read_text())


def _keys_ok(doc, schema):
    """additionalProperties: false holds all the way down (a light check without a validator)."""
    if schema.get("type") == "object" and isinstance(doc, dict):
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            assert set(doc) <= set(props), set(doc) - set(props)
        for k, v in doc.items():
            if k in props:
                _keys_ok(v, props[k])
    if schema.get("type") == "array" and isinstance(doc, list) and "items" in schema:
        for v in doc:
            _keys_ok(v, schema["items"])


def test_example_plans_every_check():
    spec = yaml.safe_load((ROOT / "examples/unreal/qa/s010_review.yaml").read_text())
    _keys_ok(spec, SCHEMA)
    for r in SCHEMA["required"]:
        assert r in spec
    steps = qa_kinds.plan(spec)
    assert [s["op"] for s in steps] == ["qa.review", "view.turntable", "qa.penetration", "qa.floating", "qa.overlaps",
                                        "qa.snapshot"]
    assert all(s["always"] for s in steps)
    assert steps[0]["args"]["out_dir"] == "/srv/qa/s010/review" and steps[0]["args"]["per_shot"] == 2


def test_plan_errors_and_schema_descriptions():
    with pytest.raises(ValueError):
        qa_kinds.plan({"name": "x", "out_dir": "/q"})
    with pytest.raises(ValueError):
        qa_kinds.plan({"name": "x", "out_dir": "/q", "review": {"per_shot": 2}})

    def walk(s, path="qa"):
        for k, v in s.get("properties", {}).items():
            assert v.get("description"), f"{path}.{k} has no description"
            walk(v, f"{path}.{k}")
        if isinstance(s.get("items"), dict):
            walk(s["items"], path + "[]")
    walk(SCHEMA)
    assert qa_kinds.describe(None, {}) is None and qa_kinds.SPEC_KINDS[0]["name"] == "qa"
