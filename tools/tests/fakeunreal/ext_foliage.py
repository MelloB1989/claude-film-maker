"""WP7/B39's fakes: foliage types, the InstancedFoliage actor (one per level, one instanced component per foliage
type, as AInstancedFoliageActor::AddInstances / RemoveAllInstances do), and PCG components (generation makes an
instanced component on the owner). Line traces come from ext_qa (actor bounds boxes)."""
from . import core


class FoliageType_InstancedStaticMesh(core.Object):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.setdefault("cull_distance", core.Object("Int32Interval", min=0, max=0))
        self._props.setdefault("cast_shadow", True)
        self._props.setdefault("mesh", None)


class FoliageType_InstancedStaticMeshFactory(core.Object):
    pass


class InstancedStaticMeshComponent(core.StaticMeshComponent):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.setdefault("instances", [])

    def get_instance_count(self) -> int:
        return len(self._props["instances"])

    def add_instances(self, transforms, should_return_indices=False, world_space=False, update_navigation=True):
        n = len(self._props["instances"])
        self._props["instances"].extend(transforms)
        return list(range(n, n + len(transforms))) if should_return_indices else []

    def clear_instances(self):
        self._props["instances"] = []


class HierarchicalInstancedStaticMeshComponent(InstancedStaticMeshComponent):
    pass


class FoliageInstancedStaticMeshComponent(HierarchicalInstancedStaticMeshComponent):
    pass


class InstancedFoliageActor(core.Actor):
    COMPONENTS = (("root_component", core.SceneComponent),)

    @staticmethod
    def _get(create: bool):
        f = core._fake()
        for a in f.world.actors():
            if type(a).__name__ == "InstancedFoliageActor":
                return a
        return f.spawn(f.InstancedFoliageActor, "InstancedFoliageActor") if create else None

    def _comp(self, ft, create: bool):
        for c in self._components:
            if isinstance(c, FoliageInstancedStaticMeshComponent) and c._props.get("foliage_type") is ft:
                return c
        if not create:
            return None
        c = FoliageInstancedStaticMeshComponent(f"FoliageISM_{len(self._components)}", self)
        c._props["foliage_type"] = ft
        c._props["static_mesh"] = ft.get_editor_property("mesh")
        self._components.append(c)
        return c

    @staticmethod
    def add_instances(world_context_object, foliage_type, transforms):
        core._fake().calls.append(("InstancedFoliageActor.add_instances", (foliage_type, len(transforms)), {}))
        ifa = InstancedFoliageActor._get(True)
        c = ifa._comp(foliage_type, True)
        c._props["static_mesh"] = foliage_type.get_editor_property("mesh")
        c.add_instances(list(transforms))

    @staticmethod
    def remove_all_instances(world_context_object, foliage_type):
        ifa = InstancedFoliageActor._get(False)
        c = ifa._comp(foliage_type, False) if ifa else None
        if c is not None:
            c.clear_instances()


class PCGGraphInstance(core.Object):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.setdefault("params", {})


class PCGComponent(core.SceneComponent):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.setdefault("seed", 42)
        self._props.setdefault("generated", False)
        self._props.setdefault("graph", None)
        self._props.setdefault("graph_instance", PCGGraphInstance("GraphInstance", self))

    def set_graph(self, graph):
        self._props["graph"] = graph

    def get_graph(self):
        return self._props["graph"]

    def generate_local(self, force: bool):
        """Generates at once: an instanced component on the owner with params["Count"] instances (25 default)."""
        owner = self.get_owner()
        self.cleanup_local(True)
        n = int(self._props["graph_instance"]._props["params"].get("Count", 25))
        c = InstancedStaticMeshComponent("PCG_ISM", owner)
        c._props["instances"] = [core.Transform() for _ in range(n)]
        owner._components.append(c)
        self._props["generated"] = True

    def cleanup_local(self, remove_components: bool):
        owner = self.get_owner()
        owner._components[:] = [c for c in owner._components if not isinstance(c, InstancedStaticMeshComponent)]
        self._props["generated"] = False


class PCGVolume(core.Actor):
    COMPONENTS = (("brush_component", core.PrimitiveComponent), ("pcg_component", PCGComponent))


class PCGGraph(core.Object):
    pass


class PCGGraphParametersHelpers(core.Object):
    pass


def _setter(kind):
    def set_param(graph_interface, name, value):
        graph_interface._props["params"][str(name)] = value
    return staticmethod(set_param)


for _k in ("bool", "int32", "double", "float", "string", "vector", "soft_object", "name"):
    setattr(PCGGraphParametersHelpers, f"set_{_k}_parameter", _setter(_k))


def install(fake):
    for cls in (FoliageType_InstancedStaticMesh, FoliageType_InstancedStaticMeshFactory, InstancedStaticMeshComponent,
                HierarchicalInstancedStaticMeshComponent, FoliageInstancedStaticMeshComponent, InstancedFoliageActor,
                PCGGraphInstance, PCGComponent, PCGVolume, PCGGraph, PCGGraphParametersHelpers):
        fake._classes[cls.__name__] = cls
        setattr(fake, cls.__name__, cls)
