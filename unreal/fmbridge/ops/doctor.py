"""editor.doctor: is this editor ready to be driven? One read-only call that checks what the night's selftests and
tomorrow's films depend on (engine, Python, GPU/RHI, the plugins, the bridge's op modules, disk, the Epic sign-in on
Linux, render and MetaHuman APIs, a few cvars the traps need) and says how to fix each failure. `film-ue doctor`
adds the client's side (the box, the editor service, the tunnel) around it (tools/filmtools/unreal/cli_doctor.py).
"""
from __future__ import annotations

import os
import shutil
import sys

import unreal

from . import _BROKEN, op

ENGINE = "5.8"
PYTHON = (3, 11)
PLUGINS = {  # plugin name: (why it matters, severity when missing)
    "PythonScriptPlugin": ("the bridge itself runs on it", "fail"),
    "EditorScriptingUtilities": ("EditorAssetLibrary and the level/asset ops", "fail"),
    "MovieRenderPipeline": ("render.* (Movie Render Queue)", "fail"),
    "SequencerScripting": ("seq.* keys, tracks and sections from Python", "fail"),
    "LevelSequenceEditor": ("opening and scrubbing sequences", "warn"),
    "MetaHumanCharacter": ("mh.* (MetaHuman Creator by code)", "warn"),
    "MetaHuman": ("speech.to_face (MetaHuman Animator)", "warn"),
    "Fab": ("fab.* (the Fab library)", "info"),
}


def _issue(code: str, severity: str, message: str, fix: str = "", **kw) -> dict:
    return {"code": f"doctor.{code}", "severity": severity, "message": message, "fix": fix, **kw}


def _cmdline() -> str:
    try:
        return str(unreal.SystemLibrary.get_command_line())
    except Exception:
        return ""


def _enabled_plugins() -> set | None:
    try:
        return {str(p) for p in unreal.PluginBlueprintLibrary.get_enabled_plugin_names()}
    except Exception:
        return None


def _project_dir() -> str:
    try:
        return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
    except Exception:
        return os.getcwd()


@op("editor.doctor", mutates=False, idempotent=True, tags=["platform"])
def doctor(*, min_free_gb: float = 50.0) -> dict:
    """Check that this editor can do the work: engine 5.8, Python 3.11, a real GPU RHI (not -nullrhi), the plugins
    the ops need, every op module imported, free disk, the Epic sign-in (Linux), the render/MetaHuman/data layer
    APIs reachable from Python, and the hair sky-lighting trap. Read-only.

    Returns: {"pass": no fail-severity issue, "issues": [{"code", "severity", "message", "fix"}], "metrics":
    {"engine", "python", "platform", "rhi", "offscreen", "free_gb", "plugins_missing", "ops", "broken"}}.
    Example: film-ue doctor   (or: film-ue op editor.doctor)
    """
    issues, m = [], {}
    eng = str(unreal.SystemLibrary.get_engine_version())
    m["engine"] = eng
    if not eng.startswith(ENGINE):
        issues.append(_issue("engine", "warn", f"engine {eng}, the helpers are written for {ENGINE}",
                             "expect API differences; run the selftests before trusting the ops"))
    m["python"] = "%d.%d.%d" % sys.version_info[:3]
    if sys.version_info[:2] != PYTHON:
        issues.append(_issue("python", "warn", f"editor Python {m['python']}, the bridge targets 3.11",
                             "newer is fine for syntax; older breaks it"))
    m["platform"] = sys.platform
    cmd = _cmdline().lower()
    m["offscreen"] = "-renderoffscreen" in cmd
    m["nullrhi"] = "-nullrhi" in cmd
    if m["nullrhi"]:
        issues.append(_issue("nullrhi", "fail", "the editor runs with -nullrhi: nothing can be rendered",
                             "restart it without -nullrhi (film-ue editor restart; the unit's mode default/offscreen)"))
    try:
        from . import editor as _ed
        m["rhi"] = _ed._rhi_from_log()
    except Exception:
        m["rhi"] = None
    if "-unattended" not in cmd and sys.platform != "win32":
        issues.append(_issue("attended", "warn", "the editor is not -unattended: a modal dialog would wait forever",
                             "start it with -unattended (the Linux unit does)"))

    enabled = _enabled_plugins()
    missing = []
    if enabled is None:
        issues.append(_issue("plugins_unknown", "warn", "could not list enabled plugins (PluginBlueprintLibrary)", ""))
    else:
        for name, (why, sev) in PLUGINS.items():
            if name not in enabled:
                missing.append(name)
                issues.append(_issue("plugin_missing", sev, f"plugin {name} is not enabled: {why}",
                                     f"enable {name} in the .uproject Plugins list and restart the editor",
                                     subject=name))
    m["plugins_missing"] = missing

    from . import _OPS
    m["ops"] = len(_OPS)
    m["broken"] = sorted(_BROKEN)
    for mod, tb in sorted(_BROKEN.items()):
        issues.append(_issue("ops_broken", "fail", f"op module {mod} failed to import: "
                             f"{tb.strip().splitlines()[-1]}", "film-ue op ops.broken has the traceback; fix and "
                             "film-ue install", subject=mod))

    try:
        free = shutil.disk_usage(_project_dir()).free / 1e9
        m["free_gb"] = round(free, 1)
        if free < min_free_gb:
            issues.append(_issue("disk", "warn" if free > 10 else "fail",
                                 f"{free:.0f} GB free on the project's disk (renders and DDC need room)",
                                 "delete old renders under Saved/MovieRenders or grow the volume",
                                 value=round(free, 1), expected=min_free_gb))
    except OSError:
        m["free_gb"] = None

    if sys.platform.startswith("linux"):
        signed = os.path.isdir(os.path.expanduser("~/.local/share/.eos_sdk"))
        m["epic_login"] = signed
        if not signed:
            issues.append(_issue("epic_login", "warn", "no Epic sign-in stored: MetaHuman cloud rig/textures and Fab "
                                 "will fail", "film-ue epic-login (device code at epicgames.com/activate)"))

    for attr, area in (("MoviePipelineQueueSubsystem", "render.*"), ("MetaHumanCharacterEditorSubsystem", "mh.*"),
                       ("LevelSequenceEditorBlueprintLibrary", "seq.*"), ("DataLayerEditorSubsystem", "level.layer_*")):
        if not hasattr(unreal, attr):
            issues.append(_issue("api_missing", "warn", f"unreal.{attr} is not exposed to Python: {area} cannot run",
                                 "enable the plugin that provides it (see the plugin issues above)", subject=attr))

    try:
        sky = unreal.SystemLibrary.get_console_variable_int_value("r.HairStrands.SkyLighting")
        m["hair_sky_lighting"] = sky
        if sky:
            issues.append(_issue("hair_sky_lighting", "info", "r.HairStrands.SkyLighting is on: indoors in daylight "
                                 "hair goes white (unreal/README.md trap)", "editor.cvar name=r.HairStrands.SkyLighting "
                                 "value=0 for interiors (and as a render cvar)"))
    except Exception:
        pass

    return {"pass": not any(i["severity"] == "fail" for i in issues), "issues": issues, "metrics": m}


def _exposed(name: str) -> bool:
    return hasattr(unreal, name)


@op("editor.api_names", mutates=False, idempotent=True, tags=["platform"])
def api_names(*, only_missing: bool = True) -> dict:
    """Is every `unreal.<Name>` the bridge's code uses really in this editor's `unreal` module? The fake engine accepts
    any name, so a C++ class name where Python wants the ScriptName (AutomationBlueprintFunctionLibrary vs
    AutomationLibrary) or a plugin that is off only shows up here, or when the op runs.

    Scans the installed fmbridge sources for `unreal.X` (the first name after `unreal.`), checks each with hasattr.
    Returns: {"checked": int, "missing": {name: [files]}, "names": [all names] (only_missing=false)}.
    A missing name is a bug (wrong name) or a disabled plugin: API_NOTES in docs/unreal/<area>.md says which.
    Example: film-ue op editor.api_names
    """
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the fmbridge package
    pat = re.compile(r"\bunreal\.([A-Z][A-Za-z0-9_]+)")
    uses: dict = {}
    for d, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(d, f)
            try:
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            for m in set(pat.findall(text)):
                uses.setdefault(m, set()).add(os.path.relpath(p, root))
    missing = {n: sorted(fs) for n, fs in sorted(uses.items()) if not _exposed(n)}
    out = {"checked": len(uses), "missing": missing}
    if not only_missing:
        out["names"] = sorted(uses)
    return out
