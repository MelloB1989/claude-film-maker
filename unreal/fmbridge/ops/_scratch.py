"""A scratch area that cleans up after itself, even on failure, without a dialog (BACKLOG B10):

    from ._scratch import scratch
    with scratch("/Game/_Selftest/look") as s:      # s.folder, s.level, s.prefix, s.previous
        spawn(s.prefix + "Box", shape="cube")        # in a fresh empty level at s.level
        ...
    # back on the level that was open before; /Game/_Selftest/look deleted (keep=True keeps it)

`level=False` stays in the open level instead: actors whose label starts with s.prefix are destroyed on exit.
Works inside a generator (a multi-tick op or selftest): the exit runs when the generator finishes, fails or is closed.
The folder must be under /Game/_Selftest or /Game/_Scratch: scratch never deletes anything else."""
from __future__ import annotations

import contextlib
from dataclasses import dataclass

import unreal
from .assets import EAL  # EditorAssetLibrary, or the EditorAssetSubsystem when its plugin is off

ROOTS = ("/Game/_Selftest/", "/Game/_Scratch/")
BLANK = "/Game/_Scratch/_Blank/L_Blank"


@dataclass
class Scratch:
    folder: str
    level: str
    prefix: str
    previous: str
    keep: bool = False


def _eal():
    return EAL


def _les():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def current_level() -> str:
    try:
        w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        return w.get_path_name().split(".")[0] if w else ""
    except Exception:
        return ""


def _open_blank() -> None:
    if _eal().does_asset_exist(BLANK):
        _les().load_level(BLANK)
    else:
        _les().new_level(BLANK)


def leave(previous: str, folder: str) -> str:
    """Back to `previous` when it is a saved level outside the scratch folder, else to a blank level when the open
    one is inside it (so the folder can be deleted). Returns the level now open."""
    if previous and previous.startswith("/") and not previous.startswith(folder) and _eal().does_asset_exist(previous):
        if current_level() != previous:
            _les().load_level(previous)
    elif current_level().startswith(folder):
        _open_blank()
    return current_level()


def fresh_level(path: str) -> str:
    """A new empty level at `path` (or, when an old one there cannot be deleted, at `path`_<n> beside it), opened;
    never an overwrite dialog. Returns the level's path. Day 1: a level left by an earlier run (its cleanup refused
    before the garbage collection fix) could not be deleted after an editor restart, and new_level refused the path."""
    folder = path.rsplit("/", 1)[0]
    if current_level().startswith(folder):
        _open_blank()
    if _eal().does_asset_exist(path):
        delete_dir(folder)  # the whole scratch folder, after a garbage collection
    if _eal().does_asset_exist(path):
        for n in range(1, 100):
            alt = f"{path}_{n}"
            if not _eal().does_asset_exist(alt):
                path = alt
                break
    if not _les().new_level(path):
        raise RuntimeError(f"could not create the scratch level {path} (film-ue op selftest.cleanup; film-ue log)")
    return path


def _destroy_prefixed(prefix: str) -> int:
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    n = 0
    for a in list(eas.get_all_level_actors()):
        if a.get_actor_label().startswith(prefix):
            eas.destroy_actor(a)
            n += 1
    return n


def delete_dir(folder: str) -> bool:
    """Delete a scratch folder after leaving it: the level just left stays in memory (referenced) until a garbage
    collection, and delete_directory refuses it until then (day 1: 'could not delete /Game/_Selftest/dx_client').
    Collects, deletes, and once more if the first try was refused."""
    if not _eal().does_directory_exist(folder):
        return True
    for _ in range(2):
        try:
            unreal.SystemLibrary.collect_garbage()
        except Exception:
            pass
        if _eal().delete_directory(folder) or not _eal().does_directory_exist(folder):
            return True
    return False


@contextlib.contextmanager
def scratch(folder: str, level: bool = True, keep: bool = False, prefix: str = ""):
    folder = folder.rstrip("/")
    if not (folder + "/").startswith(ROOTS) or folder + "/" in ROOTS:
        raise ValueError(f"scratch folder {folder!r} must be inside {' or '.join(ROOTS)} (it is deleted afterwards)")
    name = folder.rsplit("/", 1)[-1]
    s = Scratch(folder, f"{folder}/L_{name}" if level else current_level(), prefix or f"ST_{name}_", current_level(),
                keep)
    if level:
        s.level = fresh_level(s.level)
    try:
        yield s
    finally:
        if not level and not keep:
            _destroy_prefixed(s.prefix)
        leave(s.previous, folder)
        if not keep:
            delete_dir(folder)
