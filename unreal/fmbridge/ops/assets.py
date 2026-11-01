"""Assets: list, import, duplicate, delete, save."""
from __future__ import annotations

import unreal

from . import op

EAL = unreal.EditorAssetLibrary


def load(path: str):
    a = EAL.load_asset(path)
    if a is None:
        raise ValueError(f"no asset {path}")
    return a


@op("assets.list")
def list_assets(path: str = "/Game", cls: str = "", recursive: bool = True, limit: int = 500) -> list:
    """Assets under a path, optionally of one class name ('StaticMesh', 'MetaHumanCharacter', ...): [class, path]."""
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    ar.scan_paths_synchronous([path], True)
    out = [[str(a.asset_class_path.asset_name), str(a.package_name)] for a in ar.get_assets_by_path(path, recursive=recursive)]
    return [x for x in out if not cls or x[0] == cls][:limit]


@op("assets.import")
def import_files(files: list, dest: str, replace: bool = True, combine: bool = True) -> list:
    """Import files on the workstation (fbx, wav, png, exr, ...) into a content folder; returns the new assets. An FBX
    comes in as one static mesh (its parts combined unless `combine` is off) with its materials, without lightmap UVs
    (Lumen needs none)."""
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.filename, t.destination_path, t.automated, t.replace_existing, t.save = f, dest, True, replace, True
        if f.lower().endswith(".fbx"):
            ui = unreal.FbxImportUI()
            ui.import_mesh, ui.import_as_skeletal, ui.import_materials, ui.import_textures = True, False, True, False
            ui.import_animations = False
            sm = ui.static_mesh_import_data
            sm.combine_meshes, sm.generate_lightmap_u_vs, sm.auto_generate_collision = combine, False, False
            sm.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
            t.options = ui
        tasks.append(t)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    paths = [p for t in tasks for p in t.imported_object_paths]
    for p in paths:  # data textures by suffix: _N a normal map, _M/_R/_O masks (linear, not colour)
        stem = p.rsplit(".", 1)[-1]
        kind = {"N": "TC_NORMALMAP", "M": "TC_MASKS", "R": "TC_MASKS", "O": "TC_MASKS"}.get(stem.rsplit("_", 1)[-1])
        tex = EAL.load_asset(p) if kind else None
        if isinstance(tex, unreal.Texture2D):
            tex.set_editor_property("compression_settings", getattr(unreal.TextureCompressionSettings, kind))
            tex.set_editor_property("srgb", False)
            EAL.save_asset(p.rsplit(".", 1)[0])
    return paths


@op("assets.duplicate")
def duplicate(src: str, dst: str, overwrite: bool = False) -> str:
    """Copy an asset (a MetaHuman preset, a material...) to a new path."""
    if EAL.does_asset_exist(dst):
        if not overwrite:
            return dst
        EAL.delete_asset(dst)
    EAL.duplicate_asset(src, dst)
    return dst


@op("assets.delete")
def delete(path: str) -> bool:
    """Delete an asset."""
    return EAL.delete_asset(path) if EAL.does_asset_exist(path) else False


@op("assets.save_all")
def save_all() -> bool:
    """Save every dirty package and map."""
    return unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


@op("assets.props")
def props(path: str, names: list | None = None) -> dict:
    """An asset's editor properties (all readable ones, or the named)."""
    a = load(path)
    names = names or [p for p in dir(a) if not p.startswith("_") and not callable(getattr(a, p, None))]
    out = {}
    for n in names:
        try:
            out[n] = str(a.get_editor_property(n))[:300]
        except Exception:
            pass
    return out
