"""WP6's fake data layers: a DataLayerEditorSubsystem holding instances (name, visible, initially visible) and their
actors. fake.partitioned = False makes create_data_layer_instance return None, as a non-partitioned level does."""
from __future__ import annotations

from . import core


class DataLayerInstance(core.Object):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.setdefault("visible", True)
        self._props.setdefault("initially_visible", True)
        self._props.setdefault("loaded", True)

    def get_data_layer_short_name(self):
        return self._props["asset"].get_name()

    def is_visible(self):
        return self._props["visible"]

    def is_initially_visible(self):
        return self._props["initially_visible"]

    def is_runtime(self):
        return False


class DataLayerEditorSubsystem(core.EditorSubsystem):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        object.__setattr__(self, "_insts", [])
        object.__setattr__(self, "_members", {})

    def get_all_data_layers(self):
        return list(self._insts)

    def create_data_layer_instance(self, parameters):
        if not core.FAKE.partitioned:
            return None
        inst = DataLayerInstance(asset=parameters.get_editor_property("data_layer_asset"))
        self._insts.append(inst)
        self._members[id(inst)] = []
        return inst

    def get_actors_from_data_layer(self, data_layer):
        return [a for a in self._members[id(data_layer)] if a in core.FAKE.world.actors()]

    def add_actors_to_data_layer(self, actors, data_layer):
        m = self._members[id(data_layer)]
        m.extend(a for a in actors if a not in m)
        return True

    def remove_actors_from_data_layer(self, actors, data_layer):
        m = self._members[id(data_layer)]
        for a in actors:
            if a in m:
                m.remove(a)
        return True

    def set_data_layer_visibility(self, data_layer, is_visible):
        data_layer._props["visible"] = bool(is_visible)

    def set_data_layer_is_loaded_in_editor(self, data_layer, is_loaded_in_editor, is_from_user_change):
        data_layer._props["loaded"] = bool(is_loaded_in_editor)
        return True

    def set_data_layer_is_initially_visible(self, data_layer, is_initially_visible):
        data_layer._props["initially_visible"] = bool(is_initially_visible)


class DataLayerAsset(core.Object):
    pass


def install(fake):
    fake.partitioned = True
    for cls in (DataLayerInstance, DataLayerEditorSubsystem, DataLayerAsset):
        fake._classes[cls.__name__] = cls
        setattr(fake, cls.__name__, cls)
    core._FACTORY_MAKES["DataLayerFactory"] = "DataLayerAsset"
