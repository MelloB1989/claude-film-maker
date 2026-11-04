"""WP5's spec kinds through WP11's engine: registered, the examples validate against the committed schemas, and
`film-ue apply` (spec.apply over the SDK, on the fake engine) converges with an empty second plan."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from filmtools.unreal import env_kind, spec
from filmtools.unreal.sdk import Unreal

from test_ue_dx_e2e import FakeBridge

EX = Path(__file__).resolve().parents[2] / "examples" / "unreal"
EXAMPLES = sorted((EX / "environment").glob("*.yaml")) + sorted((EX / "lighting").glob("*.yaml"))


@pytest.fixture
def ue_sdk(fmb, ue):
    return Unreal(transport=FakeBridge(fmb))


def test_kinds_are_registered():
    k = spec.kinds()
    assert {"environment", "lighting"} <= set(k)
    assert k["environment"].schema_doc()["properties"]["kind"] == {"const": "environment"}


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_examples_validate_and_plan_offline(path):
    docs = spec.load(path)
    assert docs and all(d["kind"] in ("environment", "lighting") for d in docs)
    for d in docs:
        steps = env_kind.plan(d, None)
        assert steps and all({"op", "args", "why"} <= set(s) for s in steps)
        json.dumps(steps)  # what goes over the wire is JSON
        for m in (d.get("moods") or {}):
            env_kind.plan(d, None, mood=m)


def test_a_typo_is_caught_by_the_schema(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("kind: environment\nversion: 1\nname: x\nfogg: {density: 1}\n")
    with pytest.raises(Exception) as e:
        spec.load(p)
    assert "fog" in str(e.value)


def test_apply_studio_example_converges(ue_sdk, ue):
    ue.spawn("SkeletalMeshActor", label="Host", extent=(30, 30, 90))
    ue.spawn("CineCameraActor", label="HostCam", location=ue.Vector(190, 10, 175))
    docs = spec.load(EX / "environment" / "studio-day-night.yaml")
    res = spec.apply(docs, ue_sdk)
    assert res["ok"] and res["converged"], json.dumps(res, indent=1, default=str)[:3000]
    assert ue.actor("Host_Key") is not None and ue.actor("Env_Sun") is not None
    assert spec.pending(spec.plan(docs, ue_sdk)) == []
    night = [{**docs[0], "mood": "night"}]  # the same spec in its night mood
    res = spec.apply(night, ue_sdk)
    assert res["ok"] and res["converged"], json.dumps(res, indent=1, default=str)[:3000]
    assert ue.actor("Env_Sun") is None and ue.dialogs == []


def test_apply_lighting_example_converges(ue_sdk, ue):
    ue.spawn("SkeletalMeshActor", label="Detective", extent=(30, 30, 90))
    docs = spec.load(EX / "lighting" / "noir-alley.yaml")
    res = spec.apply(docs, ue_sdk)
    assert res["ok"] and res["converged"], json.dumps(res, indent=1, default=str)[:3000]
    assert ue.actor("Detective_Key") is not None and ue.actor("Neon") is not None
