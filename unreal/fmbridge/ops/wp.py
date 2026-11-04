"""World Partition in the editor (B37): what a partitioned level holds, and loading the part of it a still, a check or
a layout step needs. A Fab environment is usually partitioned, and the editor then loads only regions, so an actor
outside them does not exist in the editor world (level.find cannot see it, a capture does not draw it).

Movie Render Queue does not need this: a PIE render streams the partition around the camera and blocks until every
frame's cells are in (MoviePipeline FlushAsyncEngineSystems). These ops are for the editor world: `view.still` mode
capture, QA, layout and look work.

Through UWorldPartitionBlueprintLibrary (5.8): actor descriptors (every actor of the level, loaded or not, with its
bounds), load/unload by actor GUID (an actor-list loader adapter), pin; DataLayerEditorSubsystem for data layers. On
a level without World Partition everything is loaded and the ops say so (partitioned: false), without error.
"""
from __future__ import annotations

import unreal

from . import _wp, op
from ..errors import OpError, closest

_LOADED: dict = {}  # guid string -> label: what these ops loaded (only those can be unloaded through the library)


def _lib():
    return unreal.WorldPartitionBlueprintLibrary


def _vec(v) -> list:
    return [float(v.x), float(v.y), float(v.z)]


def _box(lo, hi):
    return unreal.Box(min=unreal.Vector(*lo), max=unreal.Vector(*hi), is_valid=True)


def _guid_str(g) -> str:
    try:
        return str(g.to_string())
    except Exception:
        return str(g)


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _loaded_guids() -> dict:
    out = {}
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        try:
            out[_guid_str(a.get_editor_property("actor_guid"))] = a.get_actor_label()
        except Exception:
            continue
    return out


def _descs(box=None) -> list | None:
    """Actor descriptors as dicts; None when the editor level is not partitioned."""
    lib = _lib()
    res = lib.get_intersecting_actor_descs(_box(*box)) if box else lib.get_actor_descs()
    ok, raw = (res if isinstance(res, tuple) else (True, res))
    if not ok and not raw:
        return None
    if not raw and not _partitioned():
        return None
    loaded = _loaded_guids()
    out = []
    for d in raw or []:
        g = _guid_str(d.get_editor_property("guid"))
        b = d.get_editor_property("bounds")
        cls = d.get_editor_property("native_class")
        out.append({"label": str(d.get_editor_property("label")) or str(d.get_editor_property("name")),
                    "guid": g, "guid_obj": d.get_editor_property("guid"),
                    "class": cls.get_name() if hasattr(cls, "get_name") else str(cls),
                    "bounds": _wp.box_dict(_vec(b.min), _vec(b.max)) if b is not None else None,
                    "grid": str(d.get_editor_property("runtime_grid") or ""),
                    "spatial": bool(d.get_editor_property("is_spatially_loaded")),
                    "editor_only": bool(d.get_editor_property("actor_is_editor_only")),
                    "data_layers": [str(p) for p in (d.get_editor_property("data_layer_assets") or [])],
                    "loaded": g in loaded})
    return out


def _partitioned() -> bool:
    b = _lib().get_editor_world_bounds()
    try:
        return bool(b.is_valid)
    except Exception:
        return False


def _public(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "guid_obj"}


def _camera_box(label: str, far_cm: float, pad_cm: float) -> tuple:
    """(AABB of the camera's frustum, its planes)."""
    from ._util import actor
    a = actor(label)
    comp = a.get_component_by_class(unreal.CameraComponent)
    if comp is None:
        raise OpError(f"{label!r} has no camera component", code="bad_args", hint="give a camera actor's label (cam.list)")
    loc = _vec(comp.get_world_location())
    r = comp.get_world_rotation()
    fov = float(comp.get_editor_property("field_of_view"))
    aspect = float(comp.get_editor_property("aspect_ratio") or 16 / 9)
    rot = {"pitch": r.pitch, "yaw": r.yaw, "roll": r.roll}
    return (_wp.frustum_box(loc, rot, fov, aspect, far_cm, pad_cm=pad_cm),
            _wp.frustum_planes(loc, rot, fov, aspect, far_cm, pad_cm=pad_cm))


def _not_partitioned(extra: dict | None = None) -> dict:
    return {"partitioned": False, "changed": False,
            "why": "the open level is not a World Partition level: every actor is loaded", **(extra or {})}


@op("wp.describe", mutates=False, idempotent=True)
def describe() -> dict:
    """The open level's partition: whether it is partitioned, its editor and runtime bounds, how many actors it has
    and how many are loaded in the editor now, per runtime grid (data layers: level.layers).

    Returns: {"partitioned", "editor_bounds": {"min", "max", "size_m"}, "runtime_bounds", "actors", "loaded",
    "spatially_loaded", "always_loaded", "editor_only", "grids": {grid: count}, "loaded_by_ops": count}.
    Example: film-ue op wp.describe
    """
    if not _partitioned():
        return {"partitioned": False, "actors": len(_loaded_guids()), "loaded": len(_loaded_guids()),
                "why": "not a World Partition level: everything is loaded"}
    eb, rb = _lib().get_editor_world_bounds(), _lib().get_runtime_world_bounds()
    ds = _descs() or []
    return {"partitioned": True, "editor_bounds": _wp.box_dict(_vec(eb.min), _vec(eb.max)),
            "runtime_bounds": _wp.box_dict(_vec(rb.min), _vec(rb.max)) if getattr(rb, "is_valid", True) else None,
            **_wp.summarize(ds), "loaded_by_ops": len(_LOADED)}


@op("wp.find", mutates=False, idempotent=True)
def find(*, contains: str = "", cls: str = "", box: list | None = None, loaded: bool | None = None,
         limit: int = 200) -> dict:
    """Actors of the partitioned level, loaded or not (from their descriptors on disk): filter by label substring,
    class name, a box [[x, y, z], [x, y, z]] in cm, or loaded state.

    Returns: {"partitioned", "count", "actors": [{"label", "guid", "class", "bounds", "grid", "spatial",
    "editor_only", "data_layers", "loaded"}]} (the first `limit`).
    Example: film-ue op wp.find contains=Tree loaded=false limit=20
    """
    ds = _descs(box)
    if ds is None:
        return _not_partitioned({"count": 0, "actors": []})
    sel = [d for d in ds if contains.lower() in d["label"].lower() and (not cls or d["class"] == cls)
           and (loaded is None or d["loaded"] == loaded)]
    return {"partitioned": True, "count": len(sel), "actors": [_public(d) for d in sel[:max(0, int(limit))]]}


def _select(box, camera, far_cm, pad_cm, around, radius_cm, labels, all_):
    """(descriptors, the box used) for a load/unload request."""
    given = [x for x in (box, camera, around, labels) if x] + ([True] if all_ else [])
    if len(given) != 1:
        raise OpError("give exactly one of box, camera, around (+ radius_cm), labels or all=true", code="bad_args",
                      hint="e.g. camera=Cam_A far_cm=8000, or 'box=[[-5000,-5000,-500],[5000,5000,3000]]'")
    planes = None
    if camera:
        box, planes = _camera_box(camera, far_cm, pad_cm)
    elif around:
        box = _wp.sphere_box(around, radius_cm)
    if box is not None:
        lo, hi = box
        if any(lo[i] > hi[i] for i in range(3)):
            raise OpError(f"box {box}: min is above max", code="bad_args", hint="[[min x, y, z], [max x, y, z]] in cm")
    ds = _descs(box)
    if ds is None:
        return None, box
    if planes:  # the box is the frustum's AABB: keep what the frustum itself meets
        ds = [d for d in ds if d["bounds"] is None or _wp.box_in_frustum(d["bounds"]["min"], d["bounds"]["max"], planes)]
    if labels:
        by = {d["label"]: d for d in _descs() or []}
        miss = [n for n in labels if n not in by]
        if miss:
            raise OpError(f"no actors {miss} in the partition", code="not_found",
                          candidates=closest(miss[0], by), hint="list them with wp.find")
        ds = [by[n] for n in labels]
    return ds, box


def _load_descs(todo: list, pin: bool, timeout_s: float):
    """Load these descriptors and wait (multi-tick) until they are in the editor world; returns the labels missing."""
    if not todo:
        return []
    _lib().load_actors([d["guid_obj"] for d in todo])
    if pin:
        _lib().pin_actors([d["guid_obj"] for d in todo])
    import time
    t0 = time.time()
    want = {d["guid"] for d in todo}
    while True:
        have = _loaded_guids()
        if want <= set(have) or time.time() - t0 > timeout_s:
            break
        yield {"message": f"loading {len(want - set(have))} of {len(want)} actors", "wait": 0.2}
    for d in todo:
        if d["guid"] in have:
            _LOADED[d["guid"]] = d["label"]
    return [d["label"] for d in todo if d["guid"] not in have]


def _shot_frustums(sequence: str, frames, every: int, far_cm: float, pad_cm: float, pin: bool, timeout_s: float):
    """Scrub a sequence through Sequencer and collect each sampled frame's camera frustum (multi-tick): returns
    ([(box, planes)], cameras used). A camera actor that is not loaded is loaded first."""
    from . import seq as seqops
    lse = unreal.LevelSequenceEditorBlueprintLibrary
    s = unreal.load_asset(sequence.split(".")[0])
    if s is None:
        raise OpError(f"no level sequence {sequence!r}", code="not_found", hint="assets.list cls=LevelSequence")
    lo, hi = frames or [int(s.get_playback_start()), int(s.get_playback_end())]
    picks = sorted(set(list(range(int(lo), int(hi), max(1, int(every)))) + [int(hi) - 1]))
    lse.open_level_sequence(s)
    out, cams = [], []
    try:
        for f in picks:
            cam = seqops.cut_camera(sequence, f)
            if cam not in cams:
                cams.append(cam)
                d = [x for x in (_descs() or []) if x["label"] == cam and not x["loaded"]]
                if d:
                    yield from _load_descs(d, pin, timeout_s)
            lse.set_current_time(f)
            yield  # the camera moves to the frame
            out.append(_camera_box(cam, far_cm, pad_cm))
    finally:
        lse.close_level_sequence()
    return out, cams


@op("wp.load", mutates=True, idempotent=True)
def load(*, box: list | None = None, camera: str = "", far_cm: float = 5000.0, pad_cm: float = 500.0,
         around: list | None = None, radius_cm: float = 3000.0, labels: list | None = None, all: bool = False,
         sequence: str = "", frames: list | None = None, every: int = 12, pin: bool = False, timeout_s: float = 60.0):
    """Load part of a World Partition level into the editor: the actors whose bounds meet a box (cm), what a camera
    sees out to far_cm (its frustum, padded by pad_cm), what a sequence's cameras see through a shot (`sequence` with
    `frames` [start, end) sampled `every` frames, through the camera cuts), a sphere around a point, named actors, or
    everything. Waits (multi-tick) until they are in the editor world. `pin` also pins them.

    Returns: {"partitioned", "changed", "requested", "newly_loaded", "already_loaded", "missing": [labels that did
    not appear], "box", "cameras" (with sequence)}.
    Example: film-ue op wp.load camera=Cam_A far_cm=8000
    """
    cams = None
    if sequence:
        if any((box, camera, around, labels, all)):
            raise OpError("give sequence alone (with frames/every), not with box/camera/around/labels/all",
                          code="bad_args")
        if not _partitioned():
            return _not_partitioned({"requested": 0})
        shots, cams = yield from _shot_frustums(sequence, frames, every, far_cm, pad_cm, pin, timeout_s)
        used = _wp.union(b for b, _ in shots)
        ds = [d for d in (_descs(used) or []) if d["bounds"] is None or
              any(_wp.box_in_frustum(d["bounds"]["min"], d["bounds"]["max"], pl) for _, pl in shots)]
    else:
        ds, used = _select(box, camera, far_cm, pad_cm, around, radius_cm, labels, all)
        if ds is None:
            return _not_partitioned({"requested": 0})
    todo = [d for d in ds if not d["loaded"]]
    missing = yield from _load_descs(todo, pin, timeout_s)
    res = {"partitioned": True, "changed": bool(todo) and len(missing) < len(todo), "requested": len(ds),
           "newly_loaded": len(todo) - len(missing), "already_loaded": len(ds) - len(todo), "missing": missing,
           "box": _wp.box_dict(*used) if used else None}
    if cams is not None:
        res["cameras"] = cams
    return res


@op("wp.unload", mutates=True, idempotent=True)
def unload(*, labels: list | None = None, box: list | None = None, all: bool = False) -> dict:
    """Unload actors that wp.load loaded (by label, by box, or all of them). Actors loaded by the editor's own regions
    (or always loaded) stay: the library unloads only its own loads.

    Returns: {"partitioned", "changed", "unloaded", "kept": [labels not loaded by wp.load]}.
    Example: film-ue op wp.unload all=true
    """
    if not _partitioned():
        return _not_partitioned({"unloaded": 0})
    if sum(bool(x) for x in (labels, box, all)) != 1:
        raise OpError("give exactly one of labels, box or all=true", code="bad_args")
    if all:
        guids = list(_LOADED)
        kept = []
    else:
        ds = _descs(box) if box else [d for d in (_descs() or []) if d["label"] in set(labels)]
        guids = [d["guid"] for d in ds if d["guid"] in _LOADED]
        kept = [d["label"] for d in ds if d["guid"] not in _LOADED and d["loaded"]]
    if guids:
        by = {d["guid"]: d["guid_obj"] for d in _descs() or []}
        _lib().unload_actors([by[g] for g in guids if g in by])
        for g in guids:
            _LOADED.pop(g, None)
    return {"partitioned": True, "changed": bool(guids), "unloaded": len(guids), "kept": kept}

