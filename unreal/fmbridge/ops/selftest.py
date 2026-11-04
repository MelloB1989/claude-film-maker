"""Selftests: list the areas that have one, and run one in a scratch level, writing its JSON report and stills on the
box (fmbridge/selftest; `film-ue selftest [area|all]` runs them all and merges one report)."""
from __future__ import annotations

import os
import time

import unreal

from . import op
from ..errors import OpError, closest


def _default_out() -> str:
    saved = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
    return os.path.join(saved, "SelfTest", time.strftime("%Y%m%d-%H%M%S")).replace("\\", "/")


@op("selftest.list", mutates=False, idempotent=True)
def list_selftests() -> dict:
    """The areas with a selftest: {area: {"doc", "requires", "areas", "needs_level", "timeout"}}, plus this editor's
    capabilities (what REQUIRES is checked against).

    Example: film-ue selftest list
    """
    from .. import selftest
    return {"areas": selftest.areas(), "capabilities": selftest.capabilities()}


@op("selftest.run", mutates=True, idempotent=True, tags=["slow"])
def run(*, area: str, out_dir: str = "", keep: bool = False):
    """Run one area's selftest in a fresh scratch level (/Game/_Selftest/<area>), deleted afterwards unless `keep`.
    Multi-tick. Returns the report: {"area", "ok", "status": done|skipped|error, "passed", "failed", "checks": [...],
    "ops_covered", "ops_missed", "stills", "metrics", "errors", "report": <its JSON on the box>}.

    Args:
        area: a selftest module's name (selftest.list).
        out_dir: the report folder on the box (default Saved/SelfTest/<time>).
        keep: keep the scratch level and assets to look at afterwards.

    Example: film-ue selftest run --area dx --keep
    """
    from .. import selftest
    known = selftest.areas()
    if area not in known:
        raise OpError(f"no selftest {area!r}", code="not_found", candidates=closest(area, known),
                      hint="selftest.list shows them; an area adds fmbridge/selftest/<area>.py")
    if known[area].get("error"):
        raise OpError(f"the {area} selftest does not import: {known[area]['error']}", code="engine",
                      hint=f"fix fmbridge/selftest/{area}.py (film-ue install after)")
    return (yield from selftest.run(area, out_dir or _default_out(), keep))


@op("selftest.cleanup", mutates=True, idempotent=True)
def cleanup(*, area: str = "") -> dict:
    """Delete a selftest's scratch folder (/Game/_Selftest/<area>, or all of /Game/_Selftest), leaving it first if it
    is the open level. Returns {"deleted": [...], "changed"}.

    Example: film-ue selftest cleanup --area dx
    """
    from .. import selftest
    root = selftest.SCRATCH_ROOT + (f"/{area}" if area else "")
    if selftest._current_level().startswith(root):
        if area:
            selftest._open_blank()
        else:  # the blank level is inside the root too: an unsaved new level outside it
            unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).new_level("/Game/_SelftestBlank/L_Blank")
    eal = unreal.EditorAssetLibrary
    if not eal.does_directory_exist(root):
        return {"deleted": [], "changed": False}
    if not eal.delete_directory(root):
        raise OpError(f"could not delete {root}", code="engine", hint="something in it is open or referenced")
    return {"deleted": [root], "changed": True}
