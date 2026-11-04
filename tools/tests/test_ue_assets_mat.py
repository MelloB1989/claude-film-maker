"""mat.* against the fake engine: masters built from specs (and left alone when current), the graph spec's checks,
instances converged from params (read back, not trusted), presets, PBR from a texture set, the drawn-material guard,
describe and check."""
from __future__ import annotations

import pytest

from fakeunreal import pure, run_op

G = pure("ops/_matgraph.py")
LIB = pure("ops/_matlib.py")


def _err(fn, **kw):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op(fn, **kw)
    return e.value


# ------------------------------------------------------------------------------------------- the spec, pure

def test_every_master_spec_normalizes():
    for name, f in LIB.MASTERS.items():
        plan = G.normalize(f())
        ids = [n["id"] for n in plan["nodes"]]
        pos = {n: i for i, n in enumerate(ids)}
        for src, _, dst, _ in plan["links"]:
            assert pos[src] < pos[dst], (name, src, dst)  # sources first
        assert plan["outputs"], name


def test_every_master_param_is_documented():
    for name, f in LIB.MASTERS.items():
        for p in G.parameters(f()):
            assert p in LIB.PARAMS, (name, p)


def test_presets_use_real_params():
    for name, (m, vals) in LIB.PRESETS.items():
        params = G.parameters(LIB.MASTERS[m]())
        assert set(vals) <= set(params), (name, set(vals) - set(params))


@pytest.mark.parametrize("spec,needle", [
    ({"nodes": {"a": {"type": "Multiplyy"}}, "outputs": {"BaseColor": "a"}}, "Multiply"),
    ({"nodes": {"a": {"type": "Multiply", "in": {"C": 1}}}, "outputs": {"BaseColor": "a"}}, "no input 'C'"),
    ({"nodes": {"a": {"type": "Multiply", "in": {"A": "b"}}}, "outputs": {"BaseColor": "a"}}, "no node 'b'"),
    ({"nodes": {"t": {"type": "Texture"}}, "outputs": {"BaseColor": "t.RBG"}}, "no output 'RBG'"),
    ({"nodes": {"a": {"type": "Scalar"}}, "outputs": {"BaseColour": "a"}}, "BaseColor"),
    ({"nodes": {"a": {"type": "Scalar"}}, "outputs": {}}, "needs outputs"),
    ({"nodes": {"a": {"type": "Multiply", "in": {"A": "b"}}, "b": {"type": "Multiply", "in": {"A": "a"}}},
      "outputs": {"BaseColor": "a"}}, "cycle"),
    ({"blend": "glassy", "nodes": {"a": {"type": "Scalar"}}, "outputs": {"BaseColor": "a"}}, "blend"),
    ({"nodes": {"t": {"type": "Texture", "sampler": "normals"}}, "outputs": {"Normal": "t"}}, "normal"),
])
def test_graph_errors_name_the_problem(spec, needle):
    with pytest.raises(G.GraphError) as e:
        G.normalize(spec)
    assert needle in str(e.value) + " ".join(e.value.candidates)


def test_constants_and_fingerprint():
    spec = {"nodes": {"m": {"type": "Multiply", "in": {"A": [1, 0, 0], "B": 0.5}}}, "outputs": {"BaseColor": "m"}}
    plan = G.normalize(spec)
    classes = sorted(n["class"] for n in plan["nodes"])
    assert classes == ["MaterialExpressionConstant", "MaterialExpressionConstant3Vector",
                       "MaterialExpressionMultiply"]
    assert G.fingerprint(spec) == G.fingerprint(dict(reversed(list(spec.items()))))


# ----------------------------------------------------------------------------------------------- the ops

def test_master_builds_once_and_compiles(ue):
    r = run_op("mat.master", name="opaque_orm")
    assert r["changed"] and r["path"] == "/Game/FM/Lib/M_Lib_OpaqueOrm" and r["stats"]["num_samplers"] == 3
    m = ue.assets[r["path"]]
    names = [str(e._props.get("parameter_name")) for e in m._props["__expr"] if "parameter_name" in e._props]
    assert len(names) == len(set(names)) and {"ORMMap", "Roughness", "Tint"} <= set(names)
    assert "/Game/FM/Lib/Textures/T_Lib_ORM" in ue.assets  # default textures made
    n = len(m._props["__expr"])
    assert run_op("mat.master", name="opaque_orm")["changed"] is False
    r2 = run_op("mat.master", name="opaque_orm", rebuild=True)
    assert r2["changed"] and len(m._props["__expr"]) == n  # rebuilt cleanly, no duplicated nodes
    assert ue.dialogs == []


def test_sampler_type_set_after_texture(ue):
    run_op("mat.master", name="opaque")
    sets = [a[0] for a, _ in ue.called("MaterialExpressionTextureSampleParameter2D.set_editor_property")]
    i_tex = [i for i, k in enumerate(sets) if k == "texture"]
    i_smp = [i for i, k in enumerate(sets) if k == "sampler_type"]
    assert all(s > t for s, t in zip(i_smp, i_tex))  # setting texture resets sampler_type in 5.8


def test_compile_errors_fail_loudly(ue):
    ue.mat_errors["/Game/M/M_Bad"] = ["[SM6] Arithmetic between types float2 and float3 are undefined"]
    e = _err("mat.graph", path="/Game/M/M_Bad", spec={"nodes": {"c": {"type": "Scalar", "name": "X"}},
                                                         "outputs": {"BaseColor": "c"}})
    assert e.code == "failed" and "float2" in e.message


def test_graph_bad_spec_touches_nothing(ue):
    e = _err("mat.graph", path="/Game/M/M_X", spec={"nodes": {"a": {"type": "Multiply", "in": {"Q": 1}}},
                                                       "outputs": {"BaseColor": "a"}})
    assert e.code == "bad_args" and "/Game/M/M_X" not in ue.assets


def test_instance_converges_and_reads_back(ue):
    r = run_op("mat.instance", path="/Game/M/MI_Red", master="opaque",
               params={"Tint": [0.6, 0.05, 0.04], "Roughness": 0.35})
    assert r["changed"] and r["parent"] == "/Game/FM/Lib/M_Lib_Opaque"
    mi = ue.assets["/Game/M/MI_Red"]
    assert mi._props["__params"]["Roughness"] == 0.35
    again = run_op("mat.instance", path="/Game/M/MI_Red", master="opaque",
                   params={"Tint": [0.6, 0.05, 0.04], "Roughness": 0.35})
    assert again["changed"] is False and again["updated"] == []
    third = run_op("mat.instance", path="/Game/M/MI_Red", master="opaque", params={"Roughness": 0.5})
    assert third["updated"] == ["Roughness"]


def test_instance_rejects_unknown_param_with_candidates(ue):
    e = _err("mat.instance", path="/Game/M/MI_Red", master="opaque", params={"Rougness": 0.3})
    assert e.code == "bad_args" and "Roughness" in e.candidates
    assert "/Game/M/MI_Red" not in ue.assets


def test_instance_needs_master_or_parent(ue):
    assert _err("mat.instance", path="/Game/M/MI_X").code == "bad_args"
    assert _err("mat.instance", path="/Game/M/MI_X", master="glas").candidates == ["glass"]


def test_preset_and_nits(ue):
    r = run_op("mat.preset", path="/Game/M/MI_Panel", name="emissive_panel", nits=400, color=[1, 0.9, 0.8])
    assert r["master"] == "emissive" and ue.assets["/Game/M/MI_Panel"]._props["__params"]["Luminance_nits"] == 400
    assert set(run_op("mat.presets")) >= {"chrome", "glass_clear", "water", "screen"}


def test_reparent_refused_while_drawn(ue):
    run_op("mat.instance", path="/Game/M/MI_A", master="opaque", params={})
    a = ue.spawn("StaticMeshActor", label="Chair")
    comp = a.get_component_by_class(ue.StaticMeshComponent) if hasattr(a, "get_component_by_class") else None
    comp = comp or a.add_component(ue.StaticMeshComponent, "StaticMeshComponent0")
    comp.set_material(0, ue.assets["/Game/M/MI_A"])
    e = _err("mat.instance", path="/Game/M/MI_A", master="glass", params={})
    assert e.code == "conflict" and "Chair" in e.message
    assert run_op("mat.instance", path="/Game/M/MI_A", master="glass", params={}, force=True)["changed"]


def test_describe_and_check(ue):
    run_op("mat.instance", path="/Game/M/MI_B", master="opaque", params={"Roughness": 0.4})
    d = run_op("mat.describe", path="/Game/M/MI_B")
    assert d["master"] == "opaque" and d["params"]["Roughness"] == {"kind": "scalar", "value": 0.4}
    assert d["chain"] == ["/Game/M/MI_B", "/Game/FM/Lib/M_Lib_Opaque"]
    c = run_op("mat.check", path="/Game/M/MI_B")
    assert c["pass"] is True and c["issues"] == []
    # a colour texture in the normal slot: flagged
    t = ue.add_asset("/Game/T/T_Wood_D", "Texture2D", srgb=True, compression_settings=ue.TextureCompressionSettings.TC_DEFAULT)
    run_op("mat.instance", path="/Game/M/MI_B", master="opaque", params={"NormalMap": "/Game/T/T_Wood_D"})
    c = run_op("mat.check", path="/Game/M/MI_B")
    assert c["pass"] is False and c["issues"][0]["code"] == "material.texture_kind" and t is not None


def test_pbr_from_files(ue, tmp_path):
    files = []
    for n in ("T_Rock_BaseColor.png", "T_Rock_Normal.png", "T_Rock_ORM.png", "notes.txt"):
        p = tmp_path / n
        p.write_bytes(b"x")
        files.append(str(p))
    r = run_op("mat.pbr", path="/Game/Rock/MI_Rock", files=files)
    assert r["master"] == "opaque_orm" and set(r["maps"]) == {"base_color", "normal", "orm"}
    n = ue.assets["/Game/Rock/Textures/T_Rock_Normal"]
    assert n._props["srgb"] is False and "NORMALMAP" in str(n._props["compression_settings"]).upper()
    p = ue.assets["/Game/Rock/MI_Rock"]._props["__params"]
    assert p["Roughness"] == 1.0 and p["Metallic"] == 1.0
    assert run_op("mat.pbr", path="/Game/Rock/MI_Rock", files=files)["changed"] is False
    assert run_op("mat.check", path="/Game/Rock/MI_Rock")["pass"]
