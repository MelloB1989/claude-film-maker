"""WP2's spec kinds (material, asset): the planners (pure, plain dicts), their schemas, and the shipped examples
through the spec engine (load, validate, plan offline)."""
from __future__ import annotations

from pathlib import Path

import pytest

from filmtools.unreal import assets_kinds as K
from filmtools.unreal import spec

EX = Path(__file__).resolve().parents[2] / "examples" / "unreal"


def _mat_state(parent, params, chain_extra=()):
    return {"chain": ["/Game/M/MI_X", parent, *chain_extra],
            "params": {k: {"kind": "scalar", "value": v} for k, v in params.items()}}


def test_material_instance_plan_converges():
    s = {"kind": "material", "name": "x", "path": "/Game/M/MI_X", "master": "opaque", "params": {"Roughness": 0.3}}
    steps = K.plan_material_and_slots(s, {"missing": True})
    assert [x["op"] for x in steps] == ["mat.instance"] and steps[0]["args"]["master"] == "opaque"
    assert K.plan_material(s, _mat_state("/Game/FM/Lib/M_Lib_Opaque", {"Roughness": 0.3})) == []
    st = K.plan_material(s, _mat_state("/Game/FM/Lib/M_Lib_Opaque", {"Roughness": 0.5}))
    assert "Roughness 0.5 -> 0.3" in st[0]["why"]
    st = K.plan_material(s, _mat_state("/Game/FM/Lib/M_Lib_Glass", {"Roughness": 0.3}))
    assert "parent" in st[0]["why"]


def test_vectors_and_textures_compare_loosely():
    s = {"kind": "material", "path": "/Game/M/MI_X", "master": "opaque",
         "params": {"Tint": [0.5, 0.2, 0.1], "BaseColorMap": "/Game/T/T_A.T_A"}}
    st = {"chain": ["/Game/M/MI_X", "/Game/FM/Lib/M_Lib_Opaque"],
          "params": {"Tint": {"kind": "vector", "value": [0.5, 0.2, 0.1, 1.0]},
                     "BaseColorMap": {"kind": "texture", "value": "/Game/T/T_A"}}}
    assert K.plan_material(s, st) == []


def test_preset_uses_the_library_table():
    s = {"kind": "material", "path": "/Game/M/MI_C", "preset": "chrome"}
    assert K.plan_material(s, None)[0]["op"] == "mat.preset"
    good = _mat_state("/Game/FM/Lib/M_Lib_Opaque", {"Metallic": 1.0, "Roughness": 0.04})
    good["params"]["Tint"] = {"kind": "vector", "value": [0.95, 0.95, 0.95, 1.0]}
    assert K.plan_material(s, good) == []
    bad = dict(good, params={**good["params"], "Metallic": {"kind": "scalar", "value": 0.0}})
    assert "Metallic" in K.plan_material(s, bad)[0]["why"]


def test_graph_rebuilds_only_when_it_changes():
    g = {"nodes": {"c": {"type": "Scalar", "name": "X"}}, "outputs": {"BaseColor": "c"}}
    s = {"kind": "material", "path": "/Game/M/M_G", "graph": g}
    assert K.plan_material(s, {"missing": True})[0]["op"] == "mat.graph"
    assert K.plan_material(s, {"fingerprint": K.fingerprint(g)}) == []
    assert K.plan_material(s, {"fingerprint": "old"})[0]["why"] == "the graph changed"


def test_fingerprint_matches_the_bridge():
    from fakeunreal import pure
    g = pure("ops/_matgraph.py")
    spec_ = {"nodes": {"c": {"type": "Scalar", "name": "X"}}, "outputs": {"BaseColor": "c"}}
    assert K.fingerprint(spec_) == g.fingerprint(spec_)
    lib = pure("ops/_matlib.py")
    for name in lib.MASTERS:
        assert K.master_path(name) == lib.master_path(name)


def test_one_mode_only():
    with pytest.raises(ValueError):
        K.plan_material({"path": "/Game/M/X", "master": "opaque", "preset": "chrome"}, None)


def test_assign_slots():
    s = {"kind": "material", "path": "/Game/M/MI_X", "master": "opaque", "assign": [{"mesh": "/Game/P/SM", "slot": 1}]}
    st = _mat_state("/Game/FM/Lib/M_Lib_Opaque", {})
    st["_slots"] = {"/Game/P/SM": [{"index": 0, "name": "A", "material": None},
                                   {"index": 1, "name": "B", "material": "/Game/M/MI_Old"}]}
    steps = K.plan_material_and_slots(s, st)
    assert steps == [{"op": "mat.assign", "args": {"mesh": "/Game/P/SM", "material": "/Game/M/MI_X", "slot": 1},
                      "why": "/Game/P/SM slot 1: /Game/M/MI_Old -> /Game/M/MI_X"}]
    st["_slots"]["/Game/P/SM"][1]["material"] = "/Game/M/MI_X"
    assert K.plan_material_and_slots(s, st) == []


def test_asset_plan():
    s = {"kind": "asset", "file": "/srv/p/chair.fbx", "dest": "/Game/P", "asset": "SM_Chair",
         "import": {"collision": "box"}, "mesh": {"nanite": True, "lods": 3}, "tags": {"category": "furniture"}}
    steps = K.plan_asset(s, {"missing": True})
    assert [x["op"] for x in steps] == ["assets.import", "assets.mesh", "assets.tag"]
    assert steps[0]["args"] == {"files": ["/srv/p/chair.fbx"], "dest": "/Game/P", "replace": True,
                                "collision": "box", "name": "SM_Chair"}
    have = {"source": "/srv/p/chair.fbx", "nanite": True, "lods": 3, "tags": {"category": "furniture"},
            "collision": {"simple": 1}}
    assert K.plan_asset(s, have) == []
    assert K.plan_asset(s, {**have, "source": "/old/chair_v1.fbx"})[0]["why"] == "the source file changed"
    assert K.plan_asset(s, {**have, "lods": 1})[0]["op"] == "assets.mesh"


def test_texture_asset_path_and_role():
    s = {"kind": "asset", "file": "/srv/t/rock normal.png", "dest": "/Game/T", "texture_role": "normal"}
    assert K.asset_path(s) == "/Game/T/T_rock_normal"
    assert K.plan_asset(s, {"source": "/srv/t/rock normal.png", "_role_ok": True}) == []
    assert K.plan_asset(s, {"source": "/srv/t/rock normal.png", "_role_ok": False})[0]["op"] == "assets.texture"


@pytest.mark.parametrize("name", ["material/rock-and-glass.yaml", "asset/props.yaml"])
def test_examples_load_and_plan_offline(name):
    docs = spec.load([EX / name])
    assert docs and all(d["kind"] in ("material", "asset") for d in docs)
    items = spec.plan(docs, state={})
    assert not [it.error for it in items if it.error]
    ops = [s["op"] for it in items for s in it.steps]
    assert ops and set(ops) <= {"mat.instance", "mat.preset", "mat.graph", "mat.assign", "assets.import",
                                "assets.mesh", "assets.tag", "assets.texture"}


def test_schema_rejects_typos():
    with pytest.raises(Exception) as e:
        spec.load_docs([{"kind": "material", "name": "x", "path": "/Game/M/X", "mastr": "opaque"}]) \
            if hasattr(spec, "load_docs") else _load_inline({"kind": "material", "name": "x", "path": "/Game/M/X",
                                                             "mastr": "opaque"})
    assert "mastr" in str(e.value)


def _load_inline(doc, tmp=Path("/tmp")):
    import json
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(doc, fh)
    return spec.load([Path(fh.name)])
