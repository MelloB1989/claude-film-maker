"""The cloth fakes (round 5, T3b): skeletal-mesh clothing assets with their Chaos configs, the FMCloth editor plugin
(unreal.FMCloth: clothing data on a section, weight maps, simulated positions), the component's cloth calls, a
reference skeleton on a skeletal mesh, and a toy simulation the ops can read back. Faithful in shape (names, return
values, what is per mesh vs per component), not in physics.

Test knobs on the fake (`ue`):
- ue.cloth_rest: the garment's simulation vertices at rest [(x, y, z), ...] (what FMCloth.rest_vertices returns).
- ue.cloth_body(frame) -> (dx, dy, dz): the body's motion (skinned = rest + it).
- ue.cloth_motion(frame, i, rest_point) -> (dx, dy, dz): the cloth's own motion at max distance scale 1, fully settled.
- ue.cloth_settle_steps: frame steps after a teleport-and-reset before the cloth is settled (it ramps in linearly).
- a mesh's reference skeleton: mesh._props["ref_bones"] = {bone: ((x, y, z) offset from its parent, parent)}.
"""
from __future__ import annotations

from . import core
from .ext_mh import struct

WEIGHTED = ("edge_stiffness_weighted", "bending_stiffness_weighted", "area_stiffness_weighted", "tether_stiffness",
            "tether_scale", "anim_drive_stiffness", "drag", "lift")
CHAOS_DEFAULTS = {"mass_mode": "DENSITY", "density": 0.35, "use_geodesic_distance": True, "collision_thickness": 1.0,
                  "friction_coefficient": 0.8, "use_ccd": False, "use_self_collisions": False,
                  "self_collision_thickness": 2.0, "damping_coefficient": 0.01, "angular_velocity_scale": 0.75,
                  "fictitious_angular_scale": 1.0, "enable_linear_velocity_clamping": False, "gravity_scale": 1.0}
SHARED_DEFAULTS = {"iteration_count": 1, "max_iteration_count": 10, "subdivision_count": 1}
TARGETS = ("MaxDistance", "BackstopDistance", "BackstopRadius", "AnimDriveStiffness")


class StrictConfig(core.Object):
    """A UObject whose editor properties are a fixed set (get/set of any other name raises, as the engine does)."""
    _DEFAULTS: dict = {}

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        for k, v in self._DEFAULTS.items():
            self._props.setdefault(k, v() if callable(v) else v)

    def get_editor_property(self, name):
        if name not in self._DEFAULTS:
            raise Exception(f"Failed to find property '{name}' on {type(self).__name__}")
        return self._props[name]

    def set_editor_property(self, name, value, notify_mode=None):
        if name not in self._DEFAULTS:
            raise Exception(f"Failed to find property '{name}' on {type(self).__name__}")
        super().set_editor_property(name, value)


def _install_types(fake):
    WV = struct("ChaosClothWeightedValue", {"low": 0.0, "high": 1.0})
    fake.ChaosClothWeightedValue = WV
    chaos = dict(CHAOS_DEFAULTS)
    chaos.update({k: (lambda: WV(low=1.0, high=1.0)) for k in WEIGHTED})
    chaos["linear_velocity_scale"] = lambda: core.Vector(0.75, 0.75, 0.75)
    chaos["max_linear_velocity"] = lambda: core.Vector(1000, 1000, 1000)
    fake.ChaosClothConfig = type("ChaosClothConfig", (StrictConfig,), {"_DEFAULTS": chaos})
    fake.ChaosClothSharedSimConfig = type("ChaosClothSharedSimConfig", (StrictConfig,), {"_DEFAULTS": SHARED_DEFAULTS})

    class ClothingAssetCommon(core.Object):
        def __init__(self, name=None, outer=None, **props):
            super().__init__(name, outer, **props)
            self._props["cloth_configs"] = {"ChaosClothConfig": fake.ChaosClothConfig("ChaosClothConfig", self),
                                            "ChaosClothSharedSimConfig":
                                                fake.ChaosClothSharedSimConfig("Shared", self)}
            self._props["physics_asset"] = None
            self.maps = {}
    fake.ClothingAssetCommon = ClothingAssetCommon


def _frame() -> int:
    """The open sequence's playhead: the last frame an op scrubbed to (set_current_time / set_global_position)."""
    for n, a, k in reversed(core.FAKE.calls):
        if n.endswith("set_current_time") and a:
            return int(a[0])
        if n.endswith("set_global_position") and a:
            return int(a[0].frame.frame_number.value) if hasattr(a[0], "frame") else int(a[0])
    return 0


def _steps_since_reset(comp) -> int:
    n = 0
    for name, a, k in reversed(core.FAKE.calls):
        if name == "SkeletalMeshComponent.force_cloth_next_update_teleport_and_reset" and comp in (a[:1] or ()):
            return n
        if name.endswith("set_current_time") or name.endswith("set_global_position"):
            n += 1
    return 10 ** 6


def install(fake):
    _install_types(fake)
    fake.cloth_rest = []
    fake.cloth_body = lambda f: (0.0, 0.0, 0.0)
    fake.cloth_motion = lambda f, i, p: (0.0, 0.0, 0.0)
    fake.cloth_settle_steps = 6
    fake.cloth_sections = {}   # (mesh path, lod, section) -> clothing asset

    SMC = core.SkeletalMeshComponent

    def _ref(comp):
        m = comp._props.get("skeletal_mesh_asset")
        return (m._props.get("ref_bones") if m is not None else None) or {}

    orig_bones = core.SkinnedMeshComponent.__dict__["_bones"]   # the class auto-stubs unknown attributes

    def _bones(self):
        b = orig_bones(self)
        return b if b else {k: v[0] for k, v in _ref(self).items()}

    def get_parent_bone(self, name):
        return core.Name(_ref(self).get(str(name), (None, None))[1] or "None")

    def get_ref_pose_transform(self, i):
        names = list(_ref(self))
        return core.Transform(core.Vector(*_ref(self)[names[i]][0]))

    def set_scale(self, s):
        core.FAKE.calls.append(("SkeletalMeshComponent.set_cloth_max_distance_scale", (self, s), {}))
        self._props["__md_scale"] = float(s)

    def get_scale(self):
        return self._props.get("__md_scale", 1.0)

    def reset(self):
        core.FAKE.calls.append(("SkeletalMeshComponent.force_cloth_next_update_teleport_and_reset", (self,), {}))

    def get_skm(self):
        return self._props.get("skeletal_mesh_asset")

    for k, fn in (("_bones", _bones), ("get_parent_bone", get_parent_bone),
                  ("get_ref_pose_transform", get_ref_pose_transform), ("set_cloth_max_distance_scale", set_scale),
                  ("get_cloth_max_distance_scale", get_scale),
                  ("force_cloth_next_update_teleport_and_reset", reset), ("get_skeletal_mesh_asset", get_skm)):
        setattr(SMC, k, fn)

    fake.stub("MathLibrary.compose_transforms",
              lambda a, b: core.Transform(core.Vector(a.translation.x + b.translation.x,
                                                      a.translation.y + b.translation.y,
                                                      a.translation.z + b.translation.z)))

    class FMCloth:
        @staticmethod
        def largest_section(mesh, lod):
            return 0

        @staticmethod
        def section_cloth(mesh, lod, section):
            return fake.cloth_sections.get((mesh.get_path_name(), int(lod), int(section)))

        @staticmethod
        def ensure_cloth_on_section(mesh, lod, section, name, physics_asset):
            key = (mesh.get_path_name(), int(lod), int(section))
            a = fake.cloth_sections.get(key)
            if a is None:
                a = fake.ClothingAssetCommon(name, mesh)
                fake.cloth_sections[key] = a
                mesh._props.setdefault("mesh_clothing_assets", []).append(a)
                core.FAKE.calls.append(("FMCloth.create", (key,), {}))
            a._props["physics_asset"] = physics_asset
            return ""

        @staticmethod
        def remove_cloth_from_section(mesh, lod, section):
            a = fake.cloth_sections.pop((mesh.get_path_name(), int(lod), int(section)), None)
            if a is not None:
                mesh._props["mesh_clothing_assets"].remove(a)
            return ""

        @staticmethod
        def rest_vertices(cloth, lod):
            return [core.Vector(*p) for p in fake.cloth_rest]

        @staticmethod
        def set_weight_map(cloth, lod, target, values):
            if target not in TARGETS:
                return f"unknown weight map target {target}"
            if len(values) != len(fake.cloth_rest):
                return f"{len(values)} values for {len(fake.cloth_rest)} simulation vertices"
            cloth.maps[target] = list(values)
            return ""

        @staticmethod
        def get_weight_map(cloth, lod, target):
            return list(cloth.maps.get(target, []))

        @staticmethod
        def simulated_positions(comp):
            mesh = comp.get_skeletal_mesh_asset()
            if mesh is None or not mesh._props.get("mesh_clothing_assets"):
                return []
            f = _frame()
            b = fake.cloth_body(f)
            s = comp.get_cloth_max_distance_scale()
            ramp = min(1.0, _steps_since_reset(comp) / float(max(1, fake.cloth_settle_steps)))
            out = []
            for i, p in enumerate(fake.cloth_rest):
                m = fake.cloth_motion(f, i, p)
                out.append(core.Vector(p[0] + b[0] + s * ramp * m[0], p[1] + b[1] + s * ramp * m[1],
                                       p[2] + b[2] + s * ramp * m[2]))
            return out

    fake.FMCloth = FMCloth

    class ChaosClothingInteractor(core.Object):
        def __getattr__(self, name):
            if name.startswith("set_"):
                def rec(*a, _n=name):
                    core.FAKE.calls.append((f"ChaosClothingInteractor.{_n}", a, {}))
                return rec
            raise AttributeError(name)

    class ClothingSimulationInteractor(core.Object):
        def get_clothing_interactor(self, name):
            return ChaosClothingInteractor(str(name), self)

    def get_interactor(self, name=None):
        m = self._props.get("skeletal_mesh_asset")
        return ClothingSimulationInteractor("CSI", self) if m is not None and m._props.get("mesh_clothing_assets") else None
    SMC.get_clothing_simulation_interactor = get_interactor

    class ChaosCacheManager(core.Actor):
        def find_or_add_observed_component(self, component, cache_name="", transfer=False):
            obs = self._props.setdefault("__observed", {})
            obs[str(cache_name)] = component

    fake.ChaosCacheManager = ChaosCacheManager
    fake.ChaosCacheCollection = type("ChaosCacheCollection", (core.Object,), {})
