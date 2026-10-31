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
def import_files(files: list, dest: str, replace: bool = True) -> list:
    """Import files on the workstation (fbx, wav, png, exr, ...) into a content folder; returns the new assets."""
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.filename, t.destination_path, t.automated, t.replace_existing, t.save = f, dest, True, replace, True
        tasks.append(t)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    return [p for t in tasks for p in t.imported_object_paths]


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
