"""Assets (WP2): the content browser by code. Listing, managing (rename, move, duplicate, remove, folders, tags),
references (who uses this, what does it use, redirectors), and an audit of what is unused or broken. Import,
textures and mesh settings are in assets_import.py; describe, the searchable catalog and thumbnails in
assets_catalog.py.

Never a modal dialog: nothing here opens one (the engine's delete/rename with dialogs are avoided: EditorAssetLibrary
calls are dialog-free), and a path is freed before anything is created over it (`free`).

Shared helpers other areas import: EAL, load, free, import_files, list_assets.
"""
from __future__ import annotations

import fnmatch
import time

import unreal

from . import _assetlib as AL
from . import op
from ..errors import OpError, closest, not_found

EAL = unreal.EditorAssetLibrary


def load(path: str):
    """The asset at `path` (any spelling: /Game/A/B, /Game/A/B.B); a not_found OpError (also a ValueError) naming
    the nearest assets in its folder otherwise."""
    a = EAL.load_asset(path)
    if a is None:
        p = AL.package_path(path)
        folder = p.rsplit("/", 1)[0]
        near = []
        try:
            if EAL.does_directory_exist(folder):
                near = [AL.package_path(x) for x in EAL.list_assets(folder, recursive=False)]
        except Exception:
            pass
        raise _NotFound(f"no asset {p}", code="not_found", candidates=closest(p, near),
                        hint="find assets with assets.find or assets.list")
    return a


class _NotFound(OpError, ValueError):
    """not_found that is also a ValueError (older callers catch ValueError)."""


def free(path: str) -> None:
    """Make sure nothing is at `path`, without a dialog: its editors closed, then deleted, else renamed aside."""
    if not EAL.does_asset_exist(path):
        return
    obj = EAL.load_asset(path)
    if obj is not None:
        unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(obj)
    if EAL.delete_asset(path) and not EAL.does_asset_exist(path):
        return
    aside = f"{path}_old{int(time.time())}"
    if not EAL.rename_asset(path, aside) or EAL.does_asset_exist(path):
        raise OpError(f"cannot free {path} (in use?): not creating over it, which would open a dialog",
                      code="conflict", hint="assets.refs shows who uses it; remove those first")


def _check_path(path: str) -> str:
    err = AL.valid_path(path)
    if err:
        raise OpError(err, code="bad_args")
    return AL.package_path(path)


def _class_name(ad) -> str:
    try:
        return str(ad.asset_class_path.asset_name)
    except Exception:
        return str(getattr(ad, "asset_class", ""))


def _registry():
    return unreal.AssetRegistryHelpers.get_asset_registry()


def _assets_under(path: str, recursive: bool = True, scan: bool = True) -> list:
    ar = _registry()
    if scan:
        ar.scan_paths_synchronous([path], True)
    return list(ar.get_assets_by_path(path, recursive=recursive) or [])


@op("assets.list")
def list_assets(path: str = "/Game", cls: str = "", recursive: bool = True, limit: int = 500) -> list:
    """Assets under a path, optionally of one class name ('StaticMesh', 'MetaHumanCharacter', ...): [class, path].
    (For search by name, size, tags use assets.find; for one asset's numbers assets.describe.)"""
    out = [[_class_name(a), str(a.package_name)] for a in _assets_under(path, recursive)]
    return [x for x in out if not cls or x[0] == cls][:limit]


# ------------------------------------------------------------------------------------------------- management

@op("assets.duplicate")
def duplicate(src: str, dst: str, overwrite: bool = False) -> str:
    """Copy an asset (a MetaHuman preset, a material...) to a new path; an existing `dst` is kept unless overwrite
    (then it is freed first). Returns dst. Example: film-ue op assets.duplicate src=/Game/M/MI_A dst=/Game/M/MI_B"""
    src_p, dst_p = AL.package_path(src), _check_path(dst)
    if not EAL.does_asset_exist(src_p):
        load(src_p)  # raises with candidates
    if EAL.does_asset_exist(dst_p):
        if not overwrite:
            return dst_p
        free(dst_p)
    if EAL.duplicate_asset(src_p, dst_p) is None:
        raise OpError(f"could not duplicate {src_p} to {dst_p}", code="engine", hint="see film-ue log")
    return dst_p


@op("assets.delete")
def delete(path: str) -> bool:
    """Delete an asset now, used or not (prefer assets.remove, which checks who uses it first)."""
    return EAL.delete_asset(path) if EAL.does_asset_exist(path) else False


@op("assets.save_all")
def save_all() -> bool:
    """Save every dirty package and map."""
    return unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


@op("assets.save", mutates=True, idempotent=True)
def save(*, paths: list = (), folder: str = "") -> dict:
    """Save assets by path, or every dirty asset under a folder.

    Args: paths: /Game/... assets. folder: a content folder (recursive).
    Returns: {"saved": [paths], "failed": [paths], "changed"}.
    Example: film-ue op assets.save folder=/Game/Props
    """
    saved, failed = [], []
    for p in paths:
        (saved if EAL.save_asset(AL.package_path(p), only_if_is_dirty=False) else failed).append(AL.package_path(p))
    if folder:
        (saved if EAL.save_directory(folder, only_if_is_dirty=True, recursive=True) else failed).append(folder)
    return {"saved": saved, "failed": failed, "changed": bool(saved)}


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


@op("assets.set_props", mutates=True, idempotent=True)
def set_props(*, path: str, props: dict, save: bool = True) -> dict:
    """Set editor properties on an asset (enums by name, e.g. {"lod_group": "TEXTUREGROUP_WORLD"}).

    Args: path: /Game/... asset. props: {property: value}; an enum value is "ENUM_NAME" or "EnumClass.ENUM_NAME".
          save: save the asset.
    Returns: {"path", "changed", "set": [names]}.
    Example: film-ue op assets.set_props path=/Game/T/T_Wood_D 'props={"max_texture_size": 2048}'
    """
    a = load(path)
    done = []
    for k, v in props.items():
        try:
            cur = a.get_editor_property(k)
        except Exception:
            raise OpError(f"{type(a).__name__} has no editor property {k!r}", code="bad_args",
                          candidates=closest(k, [p for p in dir(a) if not p.startswith("_")]),
                          hint=f"assets.props path={path} lists them") from None
        if isinstance(v, str) and hasattr(cur, "name") and not isinstance(cur, str):  # an enum: by name
            name = v.split(".")[-1].upper()
            v = getattr(type(cur), name, None)
            if v is None:
                raise OpError(f"{k}: no value {name!r}", code="bad_args")
        if str(cur) == str(v):
            continue
        a.set_editor_property(k, v)
        done.append(k)
    if done and save:
        EAL.save_asset(AL.package_path(path), only_if_is_dirty=False)
    return {"path": AL.package_path(path), "changed": bool(done), "set": done}


@op("assets.rename", mutates=True, idempotent=True)
def rename(*, src: str, dst: str, fix_redirectors: bool = True) -> dict:
    """Rename or move an asset (references follow), without a dialog; re-running after it moved changes nothing.

    Args: src: current /Game/... path. dst: new path (another folder moves it). fix_redirectors: repoint every
          referencer at the new path and delete the redirector left at src.
    Returns: {"src", "dst", "changed", "redirectors_fixed": int}.
    Example: film-ue op assets.rename src=/Game/Imports/chair dst=/Game/Props/Chairs/SM_Chair
    """
    s, d = AL.package_path(src), _check_path(dst)
    if not EAL.does_asset_exist(s):
        if EAL.does_asset_exist(d):
            return {"src": s, "dst": d, "changed": False, "redirectors_fixed": 0}
        load(s)
    if EAL.does_asset_exist(d):
        raise OpError(f"{d} already exists", code="conflict", hint="remove it first (assets.remove) or pick another "
                                                                  "name")
    folder = d.rsplit("/", 1)[0]
    if not EAL.does_directory_exist(folder):
        EAL.make_directory(folder)
    if not EAL.rename_asset(s, d):
        raise OpError(f"could not rename {s} to {d}", code="engine", hint="is it open or checked out? see film-ue log")
    fixed = fix_redirectors_in(s.rsplit("/", 1)[0])["fixed"] if fix_redirectors else 0
    return {"src": s, "dst": d, "changed": True, "redirectors_fixed": fixed}


@op("assets.move", mutates=True, idempotent=True)
def move(*, paths: list, folder: str, fix_redirectors: bool = True) -> dict:
    """Move assets into a folder, keeping their names (references follow).

    Args: paths: /Game/... assets. folder: destination folder. fix_redirectors: as assets.rename.
    Returns: {"moved": {src: dst}, "changed"}.
    Example: film-ue op assets.move 'paths=["/Game/Imports/SM_Chair"]' folder=/Game/Props
    """
    moved = {}
    for p in paths:
        s = AL.package_path(p)
        d = f"{folder.rstrip('/')}/{s.rsplit('/', 1)[-1]}"
        if s == d:
            continue
        r = rename(src=s, dst=d, fix_redirectors=fix_redirectors)
        if r["changed"]:
            moved[s] = d
    return {"moved": moved, "changed": bool(moved)}


@op("assets.remove", mutates=True, idempotent=True)
def remove(*, paths: list = (), folder: str = "", force: bool = False, dry_run: bool = False) -> dict:
    """Delete assets safely: refused (code conflict, naming who) while another asset or the open level uses them,
    unless force. Removing what is not there is fine.

    Args: paths: /Game/... assets. folder: every asset under a content folder (and the folder). force: delete even
          if referenced (referencers then point at nothing: they render the default material/mesh). dry_run: only
          report.
    Returns: {"removed": [paths], "kept": {path: [referencers]}, "changed"}.
    Example: film-ue op assets.remove 'paths=["/Game/Old/SM_Box"]'
    """
    targets = [AL.package_path(p) for p in paths]
    if folder:
        targets += [str(a.package_name) for a in _assets_under(folder)]
    targets = [t for t in dict.fromkeys(targets) if EAL.does_asset_exist(t)]
    kept, removed = {}, []
    tset = set(targets)
    for t in targets:
        users = [u for u in referencers(t) if u not in tset]
        if users and not force:
            kept[t] = users
    if kept and not force:
        raise OpError(f"{len(kept)} asset(s) are still used: " + "; ".join(f"{k} by {', '.join(v[:3])}"
                                                                         for k, v in list(kept.items())[:3]),
                      code="conflict", details={"kept": kept},
                      hint="repoint or remove the users first (assets.refs), or force=true")
    for t in targets:
        if dry_run:
            removed.append(t)
            continue
        obj = EAL.load_asset(t)
        if obj is not None:
            unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(obj)
        if EAL.delete_asset(t):
            removed.append(t)
        else:
            raise OpError(f"could not delete {t}", code="engine", hint="is it loaded in the level? see film-ue log")
    if folder and not dry_run and EAL.does_directory_exist(folder) and not _assets_under(folder):
        EAL.delete_directory(folder)
    return {"removed": removed, "kept": kept, "changed": bool(removed) and not dry_run}


@op("assets.folder", mutates=True, idempotent=True)
def folder_op(*, path: str, action: str = "make", to: str = "") -> dict:
    """Content folders: make one, rename/move one (with everything in it), or remove an empty one.

    Args: path: /Game/... folder. action: make | rename | remove. to: the new folder path for rename.
    Returns: {"path", "changed", "to"}.
    Example: film-ue op assets.folder path=/Game/Props/Chairs
    """
    p = path.rstrip("/")
    if action == "make":
        if EAL.does_directory_exist(p):
            return {"path": p, "changed": False}
        if not EAL.make_directory(p):
            raise OpError(f"could not make {p}", code="engine")
        return {"path": p, "changed": True}
    if action == "rename":
        if not to:
            raise OpError("rename needs to=", code="bad_args")
        if not EAL.does_directory_exist(p) and EAL.does_directory_exist(to):
            return {"path": p, "to": to, "changed": False}
        if not EAL.rename_directory(p, to):
            raise OpError(f"could not rename {p} to {to}", code="engine")
        fix_redirectors_in(p)
        return {"path": p, "to": to, "changed": True}
    if action == "remove":
        if not EAL.does_directory_exist(p):
            return {"path": p, "changed": False}
        if _assets_under(p):
            raise OpError(f"{p} is not empty", code="conflict", hint=f"assets.remove folder={p} deletes its assets")
        return {"path": p, "changed": bool(EAL.delete_directory(p))}
    raise OpError(f"action {action!r} is not make, rename or remove", code="bad_args",
                  candidates=closest(action, ["make", "rename", "remove"]))


@op("assets.tag", mutates=True, idempotent=True)
def tag(*, path: str, set: dict = None, remove: list = ()) -> dict:  # noqa: A002 (the natural name)
    """Metadata tags on an asset (searchable by assets.find tags=...): set or remove key/values.

    Args: path: /Game/... asset. set: {key: value} strings. remove: keys to drop.
    Returns: {"path", "tags": {key: value}, "changed"}.
    Example: film-ue op assets.tag path=/Game/Props/SM_Chair 'set={"category": "furniture", "style": "mid-century"}'
    """
    a = load(path)
    changed = False
    for k, v in (set or {}).items():
        if EAL.get_metadata_tag(a, k) != str(v):
            EAL.set_metadata_tag(a, k, str(v))
            changed = True
    for k in remove:
        if EAL.get_metadata_tag(a, k):
            EAL.remove_metadata_tag(a, k)
            changed = True
    if changed:
        EAL.save_asset(AL.package_path(path), only_if_is_dirty=False)
    return {"path": AL.package_path(path), "tags": tags_of(a), "changed": changed}


def tags_of(a) -> dict:
    try:
        vals = EAL.get_metadata_tag_values(a) or {}
        return {str(k): str(v) for k, v in vals.items()}
    except Exception:
        return {}


# ------------------------------------------------------------------------------------------------- references

def _dep_options(hard_only: bool = False):
    o = unreal.AssetRegistryDependencyOptions()
    for k, v in (("include_soft_package_references", not hard_only), ("include_hard_package_references", True),
                 ("include_searchable_names", False), ("include_soft_management_references", False),
                 ("include_hard_management_references", False)):
        try:
            o.set_editor_property(k, v)
        except Exception:
            pass
    return o


def referencers(path: str) -> list:
    """Packages that use `path` (hard and soft references), as package paths."""
    p = AL.package_path(path)
    out = _registry().get_referencers(p, _dep_options()) or []
    return sorted({str(x) for x in out if str(x) != p})


def dependencies(path: str) -> list:
    p = AL.package_path(path)
    out = _registry().get_dependencies(p, _dep_options()) or []
    return sorted({str(x) for x in out if str(x) != p})


@op("assets.refs", mutates=False, idempotent=True)
def refs(*, path: str, depth: int = 1) -> dict:
    """Who uses an asset (referencers) and what it uses (dependencies), from the asset registry; with depth > 1 the
    tree is followed that many levels.

    Args: path: /Game/... asset. depth: levels to follow (1 = direct only, max 5).
    Returns: {"path", "referencers": [paths], "dependencies": [paths], "level_actors": [labels using it in the open
             level], "tree": {path: {"referencers", "dependencies"}} when depth > 1}.
    Example: film-ue op assets.refs path=/Game/Mats/MI_Oak
    """
    p = AL.package_path(path)
    if not EAL.does_asset_exist(p):
        load(p)
    out = {"path": p, "referencers": referencers(p), "dependencies": dependencies(p)}
    try:
        from .mat import users_in_level
        out["level_actors"] = users_in_level(p) if _is_material(p) else _level_users(p)
    except Exception:
        out["level_actors"] = []
    if depth > 1:
        tree, frontier = {}, [p]
        for _ in range(min(depth, 5)):
            nxt = []
            for q in frontier:
                if q in tree:
                    continue
                tree[q] = {"referencers": referencers(q), "dependencies": dependencies(q)}
                nxt += tree[q]["referencers"] + tree[q]["dependencies"]
            frontier = [x for x in nxt if x.startswith("/Game")]
        out["tree"] = tree
    return out


def _is_material(p: str) -> bool:
    a = EAL.load_asset(p)
    return isinstance(a, unreal.MaterialInterface)


def _level_users(p: str) -> list:
    """Labels of level actors showing the mesh `p`."""
    from ._util import actors, mesh_path
    out = []
    for a in actors():
        try:
            if AL.package_path(mesh_path(a) or "") == p:
                out.append(a.get_actor_label())
        except Exception:
            pass
    return out


def _redirectors_under(folder: str) -> list:
    return [str(a.package_name) for a in _assets_under(folder) if _class_name(a) == "ObjectRedirector"]


def fix_redirectors_in(folder: str) -> dict:
    reds = _redirectors_under(folder)
    if not reds:
        return {"fixed": 0, "left": []}
    objs = [EAL.load_asset(r) for r in reds]
    objs = [o for o in objs if o is not None]
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    try:
        tools.fixup_referencers(objs, checkout_dialog_prompt=False)
    except TypeError:
        tools.fixup_referencers(objs)
    left = [r for r in _redirectors_under(folder)]
    return {"fixed": len(reds) - len(left), "left": left}


@op("assets.fix_redirectors", mutates=True, idempotent=True)
def fix_redirectors(*, folder: str = "/Game") -> dict:
    """Repoint everything that references a redirector (left behind by a rename/move) at the real asset and delete
    the redirectors, without a dialog.

    Args: folder: where to look (recursive).
    Returns: {"fixed": int, "left": [redirectors that could not be fixed], "changed"}.
    Example: film-ue op assets.fix_redirectors folder=/Game/Props
    """
    r = fix_redirectors_in(folder)
    return {**r, "changed": r["fixed"] > 0}


@op("assets.audit", mutates=False, idempotent=True, tags=["qa"])
def audit(*, folder: str = "/Game", unused: bool = True, broken: bool = True, limit: int = 200) -> dict:
    """What in a folder needs attention: assets nothing uses (and no level), redirectors, materials that do not
    compile (they draw the engine's checker), material instances whose textures do not match their samplers.

    Args: folder: content folder (recursive). unused: report unused assets. broken: compile-check materials (loads
          them: slower). limit: at most this many of each.
    Returns: {"pass", "issues": [{"code": asset.unused | asset.redirector | material.not_compiling |
             material.texture_kind, "severity", "subject", "message", "fix"}], "metrics": {"assets", "unused",
             "redirectors", "broken"}}.
    Example: film-ue op assets.audit folder=/Game/Props
    """
    ads = _assets_under(folder)
    issues = []
    n_unused = n_red = n_broken = 0
    for ad in ads:
        p, cls = str(ad.package_name), _class_name(ad)
        if cls == "ObjectRedirector":
            n_red += 1
            if n_red <= limit:
                issues.append({"code": "asset.redirector", "severity": "warn", "subject": p,
                               "message": f"{p} is a redirector left by a move",
                               "fix": f"film-ue op assets.fix_redirectors folder={folder}"})
            continue
        if unused and cls not in ("World", "LevelSequence", "MapBuildDataRegistry") and not referencers(p):
            n_unused += 1
            if n_unused <= limit:
                issues.append({"code": "asset.unused", "severity": "info", "subject": p,
                               "message": f"nothing references {p} ({cls})",
                               "fix": f"film-ue op assets.remove 'paths=[\"{p}\"]' if it is not needed"})
        if broken and cls in ("Material", "MaterialInstanceConstant") and n_broken < limit:
            from .mat import check
            try:
                c = check(path=p)
            except Exception as e:  # a material that cannot even be described is broken too
                c = {"pass": False, "issues": [{"code": "material.not_compiling", "severity": "fail", "subject": p,
                                                 "message": str(e), "fix": "film-ue log"}]}
            if not c["pass"]:
                n_broken += 1
                for i in c["issues"]:
                    issues.append({**i, "subject": p if i.get("subject") in (None, p) else f"{p}:{i['subject']}"})
    return {"pass": not any(i["severity"] == "fail" for i in issues), "issues": issues,
            "metrics": {"assets": len(ads), "unused": n_unused, "redirectors": n_red, "broken": n_broken}}


# ------------------------------------------------------------------------------------- the old import (compat)

def import_files(files: list, dest: str, replace: bool = True, combine: bool = True) -> list:
    """Import files on the workstation into a content folder; returns the new assets' object paths (the original
    assets.import, kept for callers: speech.py, films). New code: assets_import.import_any."""
    from .assets_import import import_any
    res = import_any(files=list(files), dest=dest, replace=replace, combine=combine)
    return [x for r in res["imported"] for x in r["objects"]]


def glob_match(name: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(name.lower(), pattern.lower())
