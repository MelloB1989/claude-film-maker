"""The editor itself: what it is and how it is doing (describe), console variables and commands, the idle frame cap of
an offscreen editor, waiting for shader/asset compilation to finish, and garbage collection.

    film-ue op editor.describe
    film-ue op editor.cvar name=r.RayTracing              # read
    film-ue op editor.cvar name=t.MaxFPS value=30          # set (and read back)
    film-ue op editor.wait_compile timeout_s=3600          # until no shader is compiling (multi-tick)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import unreal

from . import op
from ..errors import OpError

WORKER = "ShaderCompileWorker"


def _workers() -> int | None:
    """ShaderCompileWorker processes running now (the editor compiles shaders through them); None if unknown."""
    try:
        if sys.platform.startswith("linux"):
            n = 0
            for pid in os.listdir("/proc"):
                if pid.isdigit():
                    try:
                        with open(f"/proc/{pid}/comm") as f:
                            n += f.read().strip().startswith(WORKER[:15])  # comm is truncated to 15 characters
                    except OSError:
                        continue
            return n
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {WORKER}.exe", "/NH"], capture_output=True,
                                 text=True, timeout=10, creationflags=0x08000000).stdout  # no console window
            return sum(1 for line in out.splitlines() if line.strip().startswith(WORKER))
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _cvar(name: str) -> str:
    return unreal.SystemLibrary.get_console_variable_string_value(name)


def _rhi_from_log() -> str | None:
    """The RHI and shader platform the editor started with, from the head of its log (no script API reports it)."""
    try:
        d = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_log_dir())
        logs = sorted((os.path.join(d, f) for f in os.listdir(d) if f.endswith(".log") and "backup" not in f),
                      key=os.path.getmtime)
        with open(logs[-1], encoding="utf-8", errors="replace") as f:
            for _, line in zip(range(5000), f):
                if "ShaderPlatform for" in line or "RHI ShaderPlatform" in line:
                    return line.split("Display:")[-1].strip()[:120]
                if "LogD3D12RHI" in line and "Selected" in line:
                    return line.split(":", 3)[-1].strip()[:120]
    except (OSError, IndexError):
        return None
    return None


def _dirty() -> dict:
    lib = unreal.EditorLoadingAndSavingUtils
    return {"maps": [p.get_name() for p in lib.get_dirty_map_packages()],
            "content": [p.get_name() for p in lib.get_dirty_content_packages()]}


@op("editor.describe", mutates=False, idempotent=True, tags=["platform"])
def describe() -> dict:
    """What the editor is and how it is doing: engine, platform, RHI, project, open level, unsaved packages, idle cap,
    shader workers, memory, bridge jobs.

    Returns: {"engine", "platform", "python", "rhi", "project", "level", "dirty": {"maps", "content"},
    "idle_fps", "max_fps", "shader_workers", "rss_mb", "jobs": {"queued", "running"}, "uptime_s"}.
    Example: film-ue op editor.describe
    """
    from .. import server
    h = server.health()
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    return {"engine": h.get("engine") or unreal.SystemLibrary.get_engine_version(), "platform": sys.platform,
            "python": h.get("python"), "rhi": _rhi_from_log(), "project": h.get("project"),
            "level": world.get_path_name().split(".")[0] if world else None, "dirty": _dirty(),
            "idle_fps": h.get("idle_fps"), "max_fps": _cvar("t.MaxFPS"), "shader_workers": _workers(),
            "rss_mb": h.get("rss_mb"), "jobs": h.get("jobs"), "uptime_s": h.get("uptime")}


@op("editor.cvar", mutates=True, idempotent=True, tags=["platform"])
def cvar(*, name: str, value=None) -> dict:
    """Read a console variable, or set it (through the console, as typed there) and read it back.

    Args: name: e.g. "r.RayTracing". value: the new value (number, bool or string); omit to only read.
    Returns: {"name", "value": the value now (string), "before", "changed": bool}.
    Example: film-ue op editor.cvar name=t.MaxFPS value=30
    """
    if not name or " " in name.strip():
        raise OpError(f"bad console variable name {name!r}", code="bad_args", hint="one name, e.g. r.RayTracing")
    before = _cvar(name)
    if value is None:
        return {"name": name, "value": before, "before": before, "changed": False}
    v = ("1" if value else "0") if isinstance(value, bool) else str(value)
    unreal.SystemLibrary.execute_console_command(None, f"{name} {v}")
    now = _cvar(name)
    if now == "" and before == "":
        raise OpError(f"no console variable {name!r}", code="not_found",
                      hint="the name is case-insensitive but must exist in this engine (check its spelling)")
    return {"name": name, "value": now, "before": before, "changed": now != before}


@op("editor.console", mutates=True, idempotent=False, tags=["platform"])
def console(*, command: str) -> dict:
    """Run one console command in the editor (stat, r.*, Fab.Login, ...). It cannot report the command's own output:
    read the log (film-ue log) or a cvar after it. Never run Fab.Logout or Fab.SetEnvironment: both delete the
    saved Epic sign-in.

    Args: command: the command line as typed in the console.
    Returns: {"command", "ran": true}.
    Example: film-ue op editor.console 'command=stat unit'
    """
    low = command.strip().lower()
    if low.startswith(("fab.logout", "fab.setenvironment")):
        raise OpError(f"{command!r} would delete the saved Epic sign-in", code="conflict",
                      hint="sign-ins are kept on the box and in S3 (film-ue epic-login); do not sign out")
    if low in ("quit", "exit") or low.startswith(("quit ", "exit ")):
        raise OpError("quitting through the console leaves the bridge without an answer", code="conflict",
                      hint="film-ue editor restart (or stop) instead")
    unreal.SystemLibrary.execute_console_command(None, command)
    return {"command": command, "ran": True}


@op("editor.idle", mutates=True, idempotent=True, tags=["platform"])
def idle(*, fps: int = 30, realtime: bool = False) -> dict:
    """Cap an offscreen editor between jobs so it does not hold the GPU at full load: the frame rate (t.MaxFPS) and
    whether the level viewport redraws every frame. Movie Render Queue lifts the cap while it renders (render.mrq).

    Args: fps: the cap (0 = none). realtime: the level viewport in realtime.
    Returns: {"fps", "realtime", "changed"}.
    Example: film-ue op editor.idle fps=10
    """
    from .. import server
    before = _cvar("t.MaxFPS")
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_set_viewport_realtime(bool(realtime))
    unreal.SystemLibrary.execute_console_command(None, f"t.MaxFPS {int(fps)}")
    server._state["idle_fps"] = int(fps)
    return {"fps": int(fps), "realtime": bool(realtime), "changed": _cvar("t.MaxFPS") != before}


@op("editor.wait_compile", mutates=False, idempotent=True, tags=["platform", "slow"])
def wait_compile(*, timeout_s: float = 3600, settle_s: float = 6, finish: bool = True):
    """Wait until the editor has no shader compiling (no ShaderCompileWorker for `settle_s` seconds), ticking all the
    while, then (finish) let the engine finish any asset compilation left. The first open of a project on a new box
    compiles for many minutes: run this before stills or renders.

    Args: timeout_s: give up after this long (an error with code "timeout"). settle_s: how long the workers must
    stay at zero. finish: then call the engine's finish-all-compilation (blocks briefly).
    Returns: {"waited_s", "workers_max", "finished": bool}. Multi-tick (reports progress).
    Example: film-ue op editor.wait_compile timeout_s=3600
    """
    t0 = time.time()
    seen_max, quiet_since, n = 0, None, _workers()
    if n is None:
        yield {"message": "cannot count shader workers on this platform: finishing compilation directly"}
    while n is not None:
        seen_max = max(seen_max, n)
        if n == 0:
            quiet_since = quiet_since or time.time()
            if time.time() - quiet_since >= settle_s:
                break
        else:
            quiet_since = None
        if time.time() - t0 > timeout_s:
            raise OpError(f"shaders still compiling after {timeout_s:.0f} s ({n} workers)", code="timeout",
                          hint="call editor.wait_compile again; the first open of a project takes ~20 min on 8 cores")
        yield {"message": f"{n} shader workers", "wait": 2.0}
        n = _workers()
    if finish:
        unreal.AutomationBlueprintFunctionLibrary.finish_loading_before_screenshot()
    return {"waited_s": round(time.time() - t0, 1), "workers_max": seen_max, "finished": bool(finish)}


@op("editor.gc", mutates=False, idempotent=True, tags=["platform"])
def gc() -> dict:
    """Collect garbage (frees unreferenced objects after big imports or level changes) and report memory.

    Returns: {"rss_mb_before", "rss_mb_after"} (Linux; None elsewhere).
    Example: film-ue op editor.gc
    """
    from .. import server
    before = server._rss_mb()
    unreal.SystemLibrary.collect_garbage()
    return {"rss_mb_before": before, "rss_mb_after": server._rss_mb()}
