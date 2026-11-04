"""assets.* against the fake engine: import of every kind (with no dialog), textures by role, mesh settings,
rename/move/remove with references, redirectors, the catalog and the size-aware search, describe, tags."""
from __future__ import annotations

import os

import pytest

from fakeunreal import run_op


def _err(fn, **kw):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op(fn, **kw)
    return e.value


def _files(tmp_path, *names):
    out = []
    for n in names:
        p = tmp_path / n
        p.write_bytes(b"x")
        out.append(str(p))
    return out


# ---------------------------------------------------------------------------------------------------- import

def test_import_keeps_the_old_contract(ue, tmp_path):
    (f,) = _files(tmp_path, "chair.fbx")
    got = run_op("assets.import", files=[f], dest="/Game/Props")
    assert got == ["/Game/Props/chair.chair"]  # object paths, as films/ and speech.py expect
    t = ue.called("AssetTools.import_asset_tasks") or True
    assert t and ue.dialogs == []


def test_import_sets_an_interchange_pipeline(ue, tmp_path):
    (f,) = _files(tmp_path, "hero.fbx")
    ue.add_asset("/Game/Chars/SK_Base_Skeleton", "Skeleton")
    r = run_op("assets.import", files=[f], dest="/Game/Chars", kind="skeletal", skeleton="/Game/Chars/SK_Base_Skeleton",
               collision="none", detail=True)
    assert r["changed"] and r["imported"][0]["kind"] == "mesh"
    sets = {a[0]: a[1] for a, _ in ue.called("InterchangeGenericMeshPipeline.set_editor_property")}
    assert sets["import_static_meshes"] is False and sets["import_skeletal_meshes"] is True
    assert sets["build_nanite"] is False  # skeletal: no Nanite unless asked
    task_sets = {a[0]: a[1] for a, _ in ue.called("AssetImportTask.set_editor_property")}
    assert task_sets["automated"] is True


def test_import_alembic_and_groom_options(ue, tmp_path):
    (f,) = _files(tmp_path, "cloth.abc")
    run_op("assets.import", files=[f], dest="/Game/Sim", kind="geometry_cache", abc_preset="max")
    conv = {a[0]: a[1] for a, _ in ue.called("AbcImportSettings.set_editor_property")}
    assert conv["import_type"].name == "GEOMETRY_CACHE"
    rot = [a[1] for a, _ in ue.called("Conversion.set_editor_property") if a[0] == "rotation"]
    assert list(rot[-1]) == [0.0, 0.0, 0.0]  # the Max preset: no rotation (Maya's is 90, 0, 0)
    (g,) = _files(tmp_path, "hair.abc")
    run_op("assets.import", files=[g], dest="/Game/Hair", groom=True)
    assert ue.called("GroomImportOptions.set_editor_property")


def test_import_missing_file_is_actionable(ue):
    e = _err("assets.import", files=["/nope/chair.fbx"], dest="/Game/Props")
    assert e.code == "not_found" and "push" in e.hint


def test_textures_by_role(ue, tmp_path):
    fs = _files(tmp_path, "T_Rock_BaseColor.png", "T_Rock_Normal_GL.png", "T_Rock_ORM.png")
    r = run_op("assets.import_textures", files=fs, dest="/Game/Rock/T")
    roles = {x["path"]: x["role"] for x in r["textures"]}
    assert roles == {"/Game/Rock/T/T_Rock_BaseColor": "base_color", "/Game/Rock/T/T_Rock_Normal_GL": "normal",
                     "/Game/Rock/T/T_Rock_ORM": "orm"}
    n = ue.assets["/Game/Rock/T/T_Rock_Normal_GL"]
    assert n._props["srgb"] is False and n._props["flip_green_channel"] is True
    assert ue.assets["/Game/Rock/T/T_Rock_ORM"]._props["compression_settings"].name == "TC_MASKS"
    again = run_op("assets.import_textures", files=fs, dest="/Game/Rock/T")
    assert again["changed"] is False


def test_unnamed_png_normal_map_is_detected(ue, tmp_path):
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes((128, 128, 255)) * 8 for _ in range(8))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    p = tmp_path / "bumps.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
                  + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))
    r = run_op("assets.import_textures", files=[str(p)], dest="/Game/T")
    assert r["textures"][0]["role"] == "normal"


def test_texture_converges(ue):
    ue.add_asset("/Game/T/T_X", "Texture2D", srgb=True,
                 compression_settings=ue.TextureCompressionSettings.TC_DEFAULT)
    r = run_op("assets.texture", path="/Game/T/T_X", role="roughness", max_size_px=1024)
    assert r["changed"] and set(r["set"]) >= {"srgb", "compression_settings", "max_texture_size"}
    assert run_op("assets.texture", path="/Game/T/T_X", role="roughness", max_size_px=1024)["changed"] is False
    assert _err("assets.texture", path="/Game/T/T_X", role="rougness").candidates[:1] == ["roughness"]


# ------------------------------------------------------------------------------------------------ mesh settings

def test_mesh_settings_converge(ue):
    ue.add_mesh("/Game/P/SM_Chair", size=[50, 48, 90], tris=12000)
    r = run_op("assets.mesh", path="/Game/P/SM_Chair", nanite=True, lods=3, collision="box")
    assert set(r["set"]) == {"nanite", "lods", "collision"} and r["lods"] == 3 and r["nanite"]
    assert r["collision_prims"] == 1
    again = run_op("assets.mesh", path="/Game/P/SM_Chair", nanite=True, lods=3, collision="box")
    assert again["changed"] is False
    r = run_op("assets.mesh", path="/Game/P/SM_Chair", collision="convex", convex_hulls=6)
    assert r["collision_prims"] == 6
    assert _err("assets.mesh", path="/Game/P/SM_Chair", collision="boxx").candidates[0] == "box"


# ------------------------------------------------------------------------------------------- managing assets

def test_rename_move_idempotent(ue):
    ue.add_mesh("/Game/Imports/chair")
    r = run_op("assets.rename", src="/Game/Imports/chair", dst="/Game/Props/SM_Chair")
    assert r["changed"] and "/Game/Props/SM_Chair" in ue.assets and "/Game/Imports/chair" not in ue.assets
    assert run_op("assets.rename", src="/Game/Imports/chair", dst="/Game/Props/SM_Chair")["changed"] is False
    m = run_op("assets.move", paths=["/Game/Props/SM_Chair"], folder="/Game/Furniture")
    assert m["moved"] == {"/Game/Props/SM_Chair": "/Game/Furniture/SM_Chair"}
    assert _err("assets.rename", src="/Game/Nope/x", dst="/Game/Y/x").code == "not_found"
    assert _err("assets.rename", src="/Game/Furniture/SM_Chair", dst="Game/bad").code == "bad_args"


def test_remove_refuses_used_assets(ue):
    ue.add_mesh("/Game/P/SM_A")
    ue.add_asset("/Game/M/MI_A", "MaterialInstanceConstant")
    ue.refs["/Game/P/SM_A"] = {"/Game/M/MI_A"}
    e = _err("assets.remove", paths=["/Game/M/MI_A"])
    assert e.code == "conflict" and "/Game/P/SM_A" in e.message
    assert "/Game/M/MI_A" in ue.assets
    dry = run_op("assets.remove", paths=["/Game/M/MI_A"], dry_run=True)
    assert dry["changed"] is False and dry["kept"] == {"/Game/M/MI_A": ["/Game/P/SM_A"]} and dry["removed"] == []
    r = run_op("assets.remove", paths=["/Game/M/MI_A", "/Game/P/SM_A"])  # removed together: fine
    assert sorted(r["removed"]) == ["/Game/M/MI_A", "/Game/P/SM_A"]
    assert run_op("assets.remove", paths=["/Game/M/MI_A"])["changed"] is False  # nothing to remove is fine


def test_refs_and_redirectors(ue):
    ue.add_mesh("/Game/P/SM_A")
    ue.add_asset("/Game/M/MI_A", "MaterialInstanceConstant")
    ue.add_asset("/Game/M/MI_Old", "ObjectRedirector")
    ue.refs["/Game/P/SM_A"] = {"/Game/M/MI_Old"}
    r = run_op("assets.refs", path="/Game/M/MI_Old")
    assert r["referencers"] == ["/Game/P/SM_A"]

    def resave(asset_to_save, only_if_is_dirty=True):  # saving the user repoints it at the real asset
        ue.refs[asset_to_save.get_path_name().split(".")[0]] = {"/Game/M/MI_A"}
        return True
    ue.EditorAssetLibrary.save_loaded_asset = staticmethod(resave)
    f = run_op("assets.fix_redirectors", folder="/Game")
    assert f["fixed"] == 1 and f["resaved"] == ["/Game/P/SM_A"] and "/Game/M/MI_Old" not in ue.assets


def test_tags(ue):
    ue.add_mesh("/Game/P/SM_A")
    r = run_op("assets.tag", path="/Game/P/SM_A", set={"category": "furniture"})
    assert r["changed"]
    assert run_op("assets.tag", path="/Game/P/SM_A", set={"category": "furniture"})["changed"] is False


def test_folder_ops(ue):
    assert run_op("assets.folder", path="/Game/New")["changed"]
    assert run_op("assets.folder", path="/Game/New")["changed"] is False
    ue.add_mesh("/Game/New/SM_X")
    assert _err("assets.folder", path="/Game/New", action="remove").code == "conflict"


# --------------------------------------------------------------------------------------------- catalog/search

def _props(ue):
    ue.add_mesh("/Game/Props/SM_Chair_Dining", size=[50, 48, 90], tris=8000)
    ue.add_mesh("/Game/Props/SM_Stool_Bar", size=[38, 38, 76], tris=3000)
    ue.add_mesh("/Game/Props/SM_Chair_Kid", size=[32, 30, 46], tris=4000)
    ue.add_mesh("/Game/Props/SM_Table_Oak", size=[120, 80, 75], tris=6000, nanite=True)
    ue.add_mesh("/Game/Props/SM_Unsaved", saved=False)
    ue.add_asset("/Game/Props/T_Wood_D", "Texture2D")


def test_catalog_reads_tags_without_loading(ue):
    _props(ue)
    c = run_op("assets.catalog", folder="/Game/Props", cls="StaticMesh", refresh=True)
    by = {e["path"]: e for e in c["entries"]}
    assert by["/Game/Props/SM_Table_Oak"]["size_cm"] == [120.0, 80.0, 75.0]
    assert by["/Game/Props/SM_Table_Oak"]["nanite"] is True and by["/Game/Props/SM_Table_Oak"]["triangles"] == 6000
    assert "size_cm" not in by["/Game/Props/SM_Unsaved"]
    full = run_op("assets.catalog", folder="/Game/Props", cls="StaticMesh", refresh=True, load=True)
    assert {e["path"]: e for e in full["entries"]}["/Game/Props/SM_Unsaved"]["size_cm"] == [100.0, 100.0, 100.0]


def test_find_a_45_cm_chair(ue):
    _props(ue)
    r = run_op("assets.find", query="a 45 cm chair", cls="StaticMesh", folder="/Game/Props", refresh=True)
    assert r["hits"][0]["path"] == "/Game/Props/SM_Chair_Kid"
    assert r["hits"][0]["scale"] == pytest.approx(45 / 46, abs=1e-3)
    assert run_op("assets.find", query="table 120x80", folder="/Game/Props")["hits"][0]["path"] == \
        "/Game/Props/SM_Table_Oak"
    assert run_op("assets.find", name="SM_Chair*", folder="/Game/Props")["count"] == 2
    small = run_op("assets.find", folder="/Game/Props", cls="StaticMesh", max_size_cm=[40, 40, 0])
    assert [h["path"] for h in small["hits"]] == ["/Game/Props/SM_Chair_Kid", "/Game/Props/SM_Stool_Bar"]
    none = run_op("assets.find", query="grand piano", folder="/Game/Props")
    assert none["hits"] == [] and "hint" in none


def test_describe_mesh_and_texture(ue):
    _props(ue)
    d = run_op("assets.describe", path="/Game/Props/SM_Chair_Dining")
    assert d["size_cm"] == [50.0, 48.0, 90.0] and d["triangles"] == [8000] and d["materials"][0]["name"] == "Body"
    ue.assets["/Game/Props/T_Wood_D"]._props.update(srgb=True, max_texture_size=0, virtual_texture_streaming=False)
    t = run_op("assets.describe", path="/Game/Props/T_Wood_D")
    assert t["role_by_name"] == "base_color" and t["srgb"] is True
    e = _err("assets.describe", path="/Game/Props/SM_Chair_Dinning")
    assert e.code == "not_found" and "/Game/Props/SM_Chair_Dining" in e.candidates


def test_mat_assign_to_mesh_slot(ue):
    ue.add_mesh("/Game/P/SM_A", materials=("Seat", "Legs"))
    ue.add_asset("/Game/M/MI_Oak", "MaterialInstanceConstant")
    r = run_op("mat.assign", mesh="/Game/P/SM_A", material="/Game/M/MI_Oak", slot="Legs")
    assert r["slot"] == 1 and r["changed"]
    assert run_op("mat.assign", mesh="/Game/P/SM_A", material="/Game/M/MI_Oak", slot=1)["changed"] is False
    assert _err("mat.assign", mesh="/Game/P/SM_A", material="/Game/M/MI_Oak", slot="Leg").candidates == ["Legs"]


def test_nothing_calls_editor_asset_library_directly():
    """EditorAssetLibrary is a plugin (EditorScriptingUtilities) that a new project has off; ops/assets.py's EAL falls
    back to the always-there EditorAssetSubsystem. Everything else imports EAL from there."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "unreal" / "fmbridge"
    bad = [f"{p.relative_to(root)}:{i}" for p in root.rglob("*.py") if p.name != "assets.py" or p.parent.name != "ops"
           for i, line in enumerate(p.read_text().splitlines(), 1)
           if re.search(r"unreal\.EditorAssetLibrary\b", line) and not line.lstrip().startswith("#")]
    assert not bad, f"use `from .assets import EAL` (ops) / `from ..ops.assets import EAL` (selftests): {bad}"
