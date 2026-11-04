"""Data layers (World Partition levels): list them with their actors, put actors in a layer (made on first use),
show/hide and load/unload a layer in the editor. A level that is not partitioned has no data layers: the ops say so
(`unsupported`) instead of doing nothing. Labels and layer names are what the outliner shows.
"""
from __future__ import annotations

import unreal

from . import op
from ..errors import OpError, not_found
from ._util import actor

ASSET_DIR = "/Game/DataLayers"


def _dles():
    s = unreal.get_editor_subsystem(unreal.DataLayerEditorSubsystem)
    if s is None:
        raise OpError("the Data Layer editor subsystem is not available", code="unsupported",
                      hint="data layers need a World Partition level (level.new with a partitioned template)")
    return s


def _name(inst) -> str:
    return str(inst.get_data_layer_short_name())


def _layers() -> dict:
    return {_name(i): i for i in (_dles().get_all_data_layers() or [])}


def _layer(name: str):
    found = _layers()
    if name not in found:
        raise not_found("data layer", name, list(found), hint="list them with level.layers; level.layer_add makes one")
    return found[name]


@op("level.layers", mutates=False, idempotent=True)
def layers(*, actors: bool = True) -> dict:
    """The level's data layers: name, visible, initially visible, runtime or editor, and (with `actors`) the labels
    of the actors in each.

    Returns: {"layers": [{"name", "visible", "initially_visible", "runtime", "actors"?}]}.
    Example: film-ue op level.layers
    """
    s = _dles()
    out = []
    for name, inst in sorted(_layers().items()):
        d = {"name": name, "visible": bool(inst.is_visible()), "initially_visible": bool(inst.is_initially_visible()),
             "runtime": bool(inst.is_runtime())}
        if actors:
            d["actors"] = sorted(a.get_actor_label() for a in (s.get_actors_from_data_layer(inst) or []))
        out.append(d)
    return {"layers": out}


@op("level.layer_add", mutates=True, idempotent=True)
def layer_add(*, name: str, labels: list = (), asset_dir: str = ASSET_DIR) -> dict:
    """Put actors in a data layer, making the layer (its DataLayerAsset under asset_dir and its instance in this
    level) when it does not exist yet. Re-running changes nothing.

    Returns: {"changed", "created": bool, "added": [labels newly in it]}.
    Example: film-ue op level.layer_add name=Props_Night 'labels=["Lamp","Candle"]'
    """
    s = _dles()
    created = False
    found = _layers()
    inst = found.get(name)
    if inst is None:
        path = f"{asset_dir.rstrip('/')}/{name}"
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if asset is None:
            asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, asset_dir, unreal.DataLayerAsset,
                                                                            unreal.DataLayerFactory())
            if asset is None:
                raise OpError(f"could not create the data layer asset {path}", code="engine")
            unreal.EditorAssetLibrary.save_asset(path)
        params = unreal.DataLayerCreationParameters()
        params.set_editor_property("data_layer_asset", asset)
        inst = s.create_data_layer_instance(params)
        if inst is None:
            raise OpError(f"this level cannot hold data layers (is it a World Partition level?)", code="unsupported",
                          hint="data layers exist only in partitioned worlds")
        created = True
    have = {a.get_actor_label() for a in (s.get_actors_from_data_layer(inst) or [])}
    todo = [actor(lab) for lab in labels if lab not in have]
    if todo and not s.add_actors_to_data_layer(todo, inst):
        raise OpError(f"the engine refused to add {[a.get_actor_label() for a in todo]} to {name}", code="engine",
                      hint="an actor that cannot be in a data layer (a WorldSettings, a brush) is refused")
    return {"changed": created or bool(todo), "created": created, "added": [a.get_actor_label() for a in todo]}


@op("level.layer_remove", mutates=True, idempotent=True)
def layer_remove(*, name: str, labels: list) -> dict:
    """Take actors out of a data layer (actors not in it are skipped).

    Example: film-ue op level.layer_remove name=Props_Night 'labels=["Lamp"]'
    """
    s = _dles()
    inst = _layer(name)
    have = {a.get_actor_label() for a in (s.get_actors_from_data_layer(inst) or [])}
    todo = [actor(lab) for lab in labels if lab in have]
    if todo:
        s.remove_actors_from_data_layer(todo, inst)
    return {"changed": bool(todo), "removed": [a.get_actor_label() for a in todo]}


@op("level.layer_set", mutates=True, idempotent=True)
def layer_set(*, name: str, visible: bool = None, loaded: bool = None, initially_visible: bool = None) -> dict:
    """Show/hide a data layer in the editor (`visible`), load/unload its actors in the editor (`loaded`), or set
    whether it starts visible (`initially_visible`). Only the arguments given change.

    Example: film-ue op level.layer_set name=Props_Night visible=false
    """
    s = _dles()
    inst = _layer(name)
    changed = []
    if visible is not None and bool(inst.is_visible()) != visible:
        s.set_data_layer_visibility(inst, bool(visible))
        changed.append("visible")
    if loaded is not None:
        if not s.set_data_layer_is_loaded_in_editor(inst, bool(loaded), True):
            raise OpError(f"could not {'load' if loaded else 'unload'} {name} in the editor", code="engine")
        changed.append("loaded")  # the engine does not expose the current loaded state: always applied
    if initially_visible is not None and bool(inst.is_initially_visible()) != initially_visible:
        s.set_data_layer_is_initially_visible(inst, bool(initially_visible))
        changed.append("initially_visible")
    return {"changed": bool(changed), "set": changed}
