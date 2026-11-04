"""The `character` spec kind: the schema and examples, the pure planner, and convergence end to end on the fake
(plan -> run the steps -> describe -> the second plan is empty)."""
import json
from pathlib import Path

import pytest
import yaml

from fakeunreal import run_op
from fakeunreal.ext_mh import add_presets, add_wardrobe
from filmtools.unreal import mh_spec

REPO = Path(__file__).resolve().parents[2]
EX = REPO / "examples" / "unreal" / "character"
SCHEMA = json.loads((REPO / "tools/filmtools/unreal/schemas/character.schema.json").read_text())


def examples():
    return sorted(EX.glob("*.yaml"))


@pytest.mark.parametrize("path", examples(), ids=lambda p: p.name)
def test_examples_validate(path):
    jsonschema = pytest.importorskip("jsonschema")
    for doc in yaml.safe_load_all(path.read_text()):
        jsonschema.validate(doc, SCHEMA)


def test_schema_rejects_typos():
    jsonschema = pytest.importorskip("jsonschema")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"kind": "character", "asset": "/Game/A/MH_A", "hiar": {}}, SCHEMA)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"kind": "character", "asset": "/Game/A/MH_A", "rig": "yes"}, SCHEMA)


def test_fingerprints_match_the_ops():
    import importlib.util
    import sys
    sys.modules.setdefault("unreal", type(sys)("unreal"))  # the ops' helpers import it; the function needs no engine
    from fakeunreal import core
    core.install()
    try:
        ops = core.load_fmbridge()
        from fmbridge.ops.mh import appearance
        args = ({"Ada": 0.7, "Vivian": 0.3}, None, {"3": [0, 0.5, 1]})
        assert appearance.face_fingerprint(*args) == mh_spec.face_fingerprint(*args)
        assert mh_spec.snake("bShowTopUnderwear") == "show_top_underwear" == ops.mh._core.snake("bShowTopUnderwear")
    finally:
        core.uninstall()
    assert importlib.util  # noqa


def test_plan_fresh_runs_everything_in_order():
    spec = yaml.safe_load((EX / "presenter.yaml").read_text())
    ops = [s["op"] for s in mh_spec.plan(spec, {"exists": False})]
    assert ops == ["mh.add", "mh.body", "mh.skin", "mh.eyes", "mh.groom", "mh.groom", "mh.groom", "mh.add_item",
                   "mh.rig", "mh.textures", "mh.build"]


def test_plan_needs_from_for_a_missing_character():
    with pytest.raises(ValueError, match="from"):
        mh_spec.plan({"kind": "character", "asset": "/Game/X/MH_X"}, {"exists": False})


def state(**kw):
    s = {"exists": True, "rigged": True, "rig_stale": False, "has_high_res_textures": True,
         "body": {"Height": 182.0}, "face": {"applied": ""}, "skin": {"skin": {"u": 0.5}}, "wardrobe": {},
         "build": {"bp": "/Game/C/Unpacked/T/BP_T", "stale": False}}
    s.update(kw)
    return s


def test_plan_body_change_cascades_to_rig_and_build():
    spec = {"kind": "character", "asset": "/Game/C/MH_T", "name": "T", "body": {"Height": 180}}
    steps = mh_spec.plan(spec, state())
    assert [s["op"] for s in steps] == ["mh.body", "mh.rig", "mh.build"]
    assert mh_spec.plan({**spec, "body": {"Height": 182.02}}, state()) == []


def test_plan_skin_change_refetches_textures():
    spec = {"kind": "character", "asset": "/Game/C/MH_T", "name": "T", "skin": {"u": 0.6}}
    assert [s["op"] for s in mh_spec.plan(spec, state())] == ["mh.skin", "mh.textures", "mh.build"]


def test_plan_no_cloud():
    spec = yaml.safe_load((EX / "shape-only.yaml").read_text())
    st = state(rigged=False, has_high_res_textures=False, body={"Height": 175.0, "Chest": 100.0},
               skin={"skin": {"u": 0.5, "v": 0.5}}, build={"bp": "", "stale": True})
    assert mh_spec.plan(spec, st) == []


def test_plan_groom_compares_item_and_colour():
    spec = {"kind": "character", "asset": "/Game/C/MH_T", "name": "T",
            "grooms": {"Hair": {"item": "WI_Hair_S_BuzzCut", "melanin": 0.9}}, "rig": "none", "build": False}
    worn = {"Hair": {"item": "Hair_S_BuzzCut_Binding", "params": {"Melanin": 0.9, "Redness": 0.0}}}
    assert mh_spec.plan(spec, state(wardrobe=worn)) == []
    worn["Hair"]["params"]["Melanin"] = 0.5
    assert [s["op"] for s in mh_spec.plan(spec, state(wardrobe=worn))] == ["mh.groom"]


@pytest.fixture
def box(ue, fmb, tmp_path, monkeypatch):
    add_presets(ue)
    add_wardrobe(ue)
    monkeypatch.setenv("HOME", str(tmp_path))
    cred = tmp_path / ".local/share/.eos_sdk/keychain/abc/persistent_auth/credential"
    cred.parent.mkdir(parents=True)
    cred.write_text("x")
    return ue


def converge(spec):
    """What `film-ue apply` does: plan against mh.describe, run the steps, plan again."""
    st = run_op("mh.describe", path=spec["asset"])
    steps = mh_spec.plan(spec, st)
    for s in steps:
        run_op(s["op"], **s["args"])
    again = mh_spec.plan(spec, run_op("mh.describe", path=spec["asset"]))
    return steps, again


@pytest.mark.parametrize("name", ["presenter.yaml", "blended-face.yaml", "shape-only.yaml"])
def test_examples_converge_on_the_fake(box, name):
    spec = yaml.safe_load((EX / name).read_text())
    steps, again = converge(spec)
    assert steps and again == [], again
    assert box.dialogs == []


def test_variant_converges_after_its_source(box):
    converge(yaml.safe_load((EX / "blended-face.yaml").read_text()))
    steps, again = converge(yaml.safe_load((EX / "older-variant.yaml").read_text()))
    assert steps[0]["op"] == "mh.add" and again == []


def test_mh_apply_matches_the_plan(box):
    spec = yaml.safe_load((EX / "presenter.yaml").read_text())
    run_op("mh.apply", spec=spec)
    assert mh_spec.plan(spec, run_op("mh.describe", path=spec["asset"])) == []
