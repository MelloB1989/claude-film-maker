"""B37's fake World Partition: `fake.partition(actors)` makes the open level partitioned, with actor descriptors
[{"label", "bounds": [[min], [max]], "grid", "spatial", "loaded"}]. WorldPartitionBlueprintLibrary answers from them;
load_actors puts the actors into the editor world on the next tick (as the loader adapter does), unload_actors takes
them out. Without fake.partition the level is not partitioned (invalid bounds, no descriptors)."""
from __future__ import annotations

from . import core


class _Guid:
    def __init__(self, s):
        self.s = s

    def to_string(self):
        return self.s

    def __eq__(self, o):
        return isinstance(o, _Guid) and o.s == self.s

    def __hash__(self):
        return hash(self.s)


def install(fake):
    O = fake.Object
    state = {"descs": None, "pending": [], "pinned": set()}
    fake.wp = state

    class Box:
        """FBox as Python sees it: at most (min, max), and the box comes out valid. The engine refuses a third
        argument (is_valid=: \"call() takes at most 2 arguments (3 given)\", day 1)."""
        def __init__(self, min=None, max=None):  # noqa: A002 (the engine's names)
            self.min, self.max, self.is_valid = min, max, min is not None and max is not None

    fake.Box = Box

    class ActorDesc(O):
        pass

    def _desc(d):
        a = ActorDesc()
        a.set_editor_property("guid", d["guid"])
        a.set_editor_property("label", d["label"])
        a.set_editor_property("name", d["label"])
        a.set_editor_property("native_class", core._uclass(getattr(fake, d.get("cls", "StaticMeshActor"))))
        lo, hi = d["bounds"]
        a.set_editor_property("bounds", Box(fake.Vector(*lo), fake.Vector(*hi)))
        a.set_editor_property("runtime_grid", d.get("grid", "MainGrid"))
        a.set_editor_property("is_spatially_loaded", d.get("spatial", True))
        a.set_editor_property("actor_is_editor_only", False)
        a.set_editor_property("data_layer_assets", [])
        return a

    def _spawn(d):
        a = fake.spawn(d.get("cls", "StaticMeshActor"), label=d["label"])
        a.set_editor_property("actor_guid", d["guid"])

    def _meets(d, box):
        (lo, hi), b = d["bounds"], box
        return all(lo[i] <= b.max_[i] and b.min_[i] <= hi[i] for i in range(3))

    class WorldPartitionBlueprintLibrary(O):
        @staticmethod
        def get_editor_world_bounds():
            ds = state["descs"]
            if not ds:
                return Box()  # what the engine returns for no bounds: is_valid False
            lo = [min(d["bounds"][0][i] for d in ds) for i in range(3)]
            hi = [max(d["bounds"][1][i] for d in ds) for i in range(3)]
            return Box(fake.Vector(*lo), fake.Vector(*hi))

        get_runtime_world_bounds = get_editor_world_bounds

        @staticmethod
        def get_actor_descs():  # bool + out param: None on false, else the array (PyGenUtil.cpp:1161)
            if state["descs"] is None:
                return None
            return [_desc(d) for d in state["descs"]]

        @staticmethod
        def get_intersecting_actor_descs(box):
            if state["descs"] is None:
                return None
            b = type("B", (), {"min_": list(box.min), "max_": list(box.max)})
            return [_desc(d) for d in state["descs"] if _meets(d, b)]

        @staticmethod
        def load_actors(guids):
            fake.calls.append(("WorldPartitionBlueprintLibrary.load_actors", (list(guids),), {}))
            state["pending"].extend(guids)

        @staticmethod
        def unload_actors(guids):
            fake.calls.append(("WorldPartitionBlueprintLibrary.unload_actors", (list(guids),), {}))
            for g in guids:
                for a in list(fake.world.actors()):
                    if a.get_editor_property("actor_guid") == g:
                        fake.world.remove(a)

        @staticmethod
        def pin_actors(guids):
            state["pinned"].update(guids)

    fake.WorldPartitionBlueprintLibrary = WorldPartitionBlueprintLibrary

    def tick(_dt):
        while state["pending"]:
            g = state["pending"].pop(0)
            d = next((d for d in state["descs"] or [] if d["guid"] == g), None)
            if d and not d.get("never_loads"):
                _spawn(d)

    fake.register_slate_post_tick_callback(tick)

    def partition(actors):
        """Make the level partitioned with these actor descriptors; loaded ones are spawned now."""
        state["descs"] = []
        for i, d in enumerate(actors):
            d = {"guid": _Guid(f"G{i:04d}"), **d}
            state["descs"].append(d)
            if d.get("loaded"):
                _spawn(d)

    fake.partition = partition
