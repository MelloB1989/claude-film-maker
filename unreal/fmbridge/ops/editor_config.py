"""The editor's configuration: plugins (in the .uproject), console variables as a set (read, set, snapshot, restore),
and project settings (the project's Default*.ini). Changes to plugins and .ini files apply at the next editor start:
the answer says `restart_required`, and `film-ue editor restart --wait` does it.

    film-ue op editor.plugins                                         # enabled ones, and the .uproject's list
    film-ue op editor.plugins 'enable=["MovieRenderPipeline"]'        # (restart)
    film-ue op editor.cvars 'values={"r.RayTracing": 0}' snapshot=before_test
    film-ue op editor.cvars restore=before_test
    film-ue op editor.project_setting file=Engine section=/Script/Engine.RendererSettings key=r.RayTracing value=True
"""
from __future__ import annotations

import json
import os

import unreal

from . import op
from ._ini import ini_get, ini_set, uproject_plugins, uproject_set_plugins
from ..errors import OpError, closest

_SNAPSHOTS: dict = {}
INI_FILES = ("Engine", "Game", "Editor", "Input", "EditorPerProjectUserSettings", "DeviceProfiles", "Scalability")


def _uproject() -> str:
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())


def _descriptor(name: str):
    """The plugin's .uplugin path, or None when the engine does not know a plugin by that name. (A bool UFUNCTION
    with an out parameter comes back as the out value, or None when it returned false.)"""
    r = unreal.PluginBlueprintLibrary.get_plugin_descriptor_file_path(name)
    if isinstance(r, tuple):
        r = r[-1] if (len(r) < 2 or r[0]) else None
    return r or None


@op("editor.plugins", mutates=True, idempotent=True, tags=["platform"])
def plugins(*, enable: list | None = None, disable: list | None = None, prefix: str = "") -> dict:
    """The plugins: which are enabled now, and what the .uproject lists. With `enable`/`disable`, edit the .uproject
    (applies at the next editor start: restart_required).

    Args: enable, disable: plugin names (as in their .uplugin, e.g. "MovieRenderPipeline", "PythonScriptPlugin").
    prefix: only list enabled plugins whose name starts with this.
    Returns: {"enabled": [names], "project": {name: on}, "changed": [names], "restart_required": bool}.
    Example: film-ue op editor.plugins 'enable=["MovieRenderPipeline"]'
    """
    enabled = sorted(unreal.PluginBlueprintLibrary.get_enabled_plugin_names())
    path = _uproject()
    with open(path, encoding="utf-8") as f:
        text = f.read()
    changed = []
    if enable or disable:
        for name in list(enable or []) + list(disable or []):
            if not _descriptor(name):
                raise OpError(f"no plugin {name!r} in this engine or project", code="not_found",
                              candidates=closest(name, enabled), hint="editor.plugins lists the enabled ones")
        new, changed = uproject_set_plugins(text, enable or (), disable or ())
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
            text = new
    return {"enabled": [p for p in enabled if p.startswith(prefix)], "project": uproject_plugins(text),
            "changed": changed, "restart_required": bool(changed)}


def _get(name: str) -> str:
    return unreal.SystemLibrary.get_console_variable_string_value(name)


@op("editor.cvars", mutates=True, idempotent=True, tags=["platform"])
def cvars(*, names: list | None = None, values: dict | None = None, snapshot: str = "", restore: str = "") -> dict:
    """Console variables as a set: read several, set several, and take or restore a named snapshot (so a test or a
    render can change cvars and put them back). Snapshots live until the editor stops, and in Saved/Bridge/cvars.

    Args: names: cvars to read. values: {name: value} to set (read back after). snapshot: save the current values of
    `names` and of the keys of `values` under this name, before setting anything. restore: set the cvars of this
    snapshot back.
    Returns: {"values": {name: value now}, "changed": [names], "snapshot"?, "restored"?}.
    Example: film-ue op editor.cvars 'values={"r.RayTracing": 0}' snapshot=pre
    """
    names = list(names or [])
    values = dict(values or {})
    out: dict = {"changed": []}
    if restore:
        saved = _SNAPSHOTS.get(restore) or _load_snapshot(restore)
        if saved is None:
            raise OpError(f"no cvar snapshot {restore!r}", code="not_found", candidates=closest(restore, _SNAPSHOTS),
                          hint="take one with editor.cvars snapshot=NAME first")
        values = {**saved, **values}
        out["restored"] = restore
    want = sorted(set(names) | set(values))
    unknown = [n for n in want if _get(n) == ""]
    if unknown:
        raise OpError(f"no console variable {', '.join(map(repr, unknown))}", code="not_found",
                      hint="names are case-insensitive but must exist in this engine")
    if snapshot:
        _SNAPSHOTS[snapshot] = {n: _get(n) for n in want}
        _save_snapshot(snapshot, _SNAPSHOTS[snapshot])
        out["snapshot"] = snapshot
    for n, v in values.items():
        before = _get(n)
        sv = ("1" if v else "0") if isinstance(v, bool) else str(v)
        unreal.SystemLibrary.execute_console_command(None, f"{n} {sv}")
        if _get(n) != before:
            out["changed"].append(n)
    out["values"] = {n: _get(n) for n in want}
    return out


def _snap_path(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    saved = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
    return os.path.join(saved, "Bridge", "cvars", f"{safe}.json")


def _save_snapshot(name: str, vals: dict) -> None:
    p = _snap_path(name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(vals, f)


def _load_snapshot(name: str):
    try:
        with open(_snap_path(name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


@op("editor.project_setting", mutates=True, idempotent=True, tags=["platform"])
def project_setting(*, file: str = "Engine", section: str, key: str, value=None) -> dict:
    """Read or set one project setting in the project's Config/Default<file>.ini (what Project Settings writes);
    applies at the next editor start (restart_required when it changed). For a live change of a console variable
    use editor.cvar; this one makes it the project's default.

    Args: file: Engine|Game|Editor|Input|... (Config/Default<file>.ini). section: e.g. "/Script/Engine.RendererSettings"
    or "/Script/LinuxTargetPlatform.LinuxTargetSettings". key: e.g. "r.RayTracing". value: omit to read.
    Returns: {"file", "section", "key", "value", "before", "changed", "restart_required"}.
    Example: film-ue op editor.project_setting section=/Script/Engine.RendererSettings key=r.RayTracing value=True
    """
    if file not in INI_FILES:
        raise OpError(f"no project config file {file!r}", code="bad_args", candidates=closest(file, INI_FILES))
    if not section or not key:
        raise OpError("section and key are both needed", code="bad_args",
                      hint="e.g. section=/Script/Engine.RendererSettings key=r.RayTracing")
    proj = os.path.dirname(_uproject())
    path = os.path.join(proj, "Config", f"Default{file}.ini")
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    before = ini_get(text, section, key)
    if value is None:
        return {"file": path, "section": section, "key": key, "value": before, "before": before, "changed": False,
                "restart_required": False}
    new, changed = ini_set(text, section, key, value)
    if changed:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
    return {"file": path, "section": section, "key": key, "value": ini_get(new, section, key), "before": before,
            "changed": changed, "restart_required": changed}
