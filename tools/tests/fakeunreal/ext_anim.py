"""WP4's fakes: animation sequences with float curves and a data controller, the AnimationLibrary calls the anim and
perf ops use, skeletons and skeletal meshes, the asset registry's filtered search with tags, and the IK Rig /
Retargeter / Control Rig scripting surfaces as recorders. Sequencer itself is WP8's (ext_seq) or recorded stubs.

    anim = ue.anim("/Game/A/AS_talk", length_s=3.0, curves={"HeadYaw": ([0, 3], [0, 10])}, skeleton="/Game/MH/Face_Skel")
"""
from __future__ import annotations

import copy

from . import core


class Skeleton(core.Object):
    pass


class SkeletalMesh(core.Object):
    def get_skeleton(self):
        return self._props.get("skeleton")


class _Controller:
    """IAnimationDataController over a fake AnimSequence: brackets counted, curves and frame count written."""

    def __init__(self, anim):
        self.anim = anim

    def _log(self, name, *a):
        core._fake().calls.append((f"AnimationDataController.{name}", a, {}))

    def open_bracket(self, title, should_transact=True):
        self.anim._data["brackets"] += 1
        self._log("open_bracket", title)

    def close_bracket(self, should_transact=True):
        self._log("close_bracket")

    def add_curve(self, curve_id, flags=4, should_transact=True):
        self.anim._data["curves"].setdefault(curve_id.name, ([], []))
        return True

    def set_curve_keys(self, curve_id, keys, should_transact=True):
        self.anim._data["curves"][curve_id.name] = ([float(k.time) for k in keys], [float(k.value) for k in keys])
        self.anim._data["writes"] += 1
        return True

    def remove_curve(self, curve_id, should_transact=True):
        return self.anim._data["curves"].pop(curve_id.name, None) is not None

    def remove_all_curves_of_type(self, curve_type, should_transact=True):
        self.anim._data["curves"].clear()

    def set_frame_rate(self, rate, should_transact=True):
        self.anim._data["fps"] = rate.numerator / rate.denominator

    def set_number_of_frames(self, n, should_transact=True):
        self.anim._data["frames"] = int(n.value if hasattr(n, "value") else n)

    def add_bone_curve(self, bone, should_transact=True):
        self.anim._data["bones"].add(str(bone))
        return True

    def set_bone_track_keys(self, bone, pos, rot, scl, should_transact=True):
        self.anim._data["bones"].add(str(bone))
        return True


class AnimSequence(core.AnimSequence):
    """A fake animation: `_data` holds curves {name: (times, values)}, fps, frames (keys = frames + 1 at the end),
    bone track names; duplicated deeply by EditorAssetLibrary.duplicate_asset."""

    def __init__(self, name=None, outer=None, **props):
        data = props.pop("__data", None)
        super().__init__(name, outer, **props)
        object.__setattr__(self, "_data", copy.deepcopy(data) if data else
                           {"curves": {}, "fps": 30.0, "frames": 30, "bones": set(), "brackets": 0, "writes": 0})
        self._props["__data"] = self._data  # so a duplicate (type(src)(name, **src._props)) copies it
        self._props.setdefault("additive_anim_type", "AAT_NONE")
        self._props.setdefault("ref_pose_type", "ABPT_REF_POSE")
        self._props["controller"] = _Controller(self)  # a duplicate gets its own

    def get_skeleton(self):
        return self._props.get("skeleton")

    @property
    def length_s(self):
        return self._data["frames"] / self._data["fps"]


class AnimationLibrary(core.Object):
    @staticmethod
    def get_animation_curve_names(anim, curve_type):
        return list(anim._data["curves"])

    @staticmethod
    def get_float_keys(anim, name):
        t, v = anim._data["curves"].get(str(name), ([], []))
        return list(t), list(v)

    @staticmethod
    def does_curve_exist(anim, name, curve_type):
        return str(name) in anim._data["curves"]

    @staticmethod
    def get_sequence_length(anim):
        return anim.length_s

    @staticmethod
    def get_num_frames(anim):
        return anim._data["frames"] + 1

    @staticmethod
    def get_num_keys(anim):
        return anim._data["frames"] + 1

    @staticmethod
    def get_animation_track_names(anim):
        return sorted(anim._data["bones"])

    @staticmethod
    def is_root_motion_enabled(anim):
        return bool(anim._props.get("enable_root_motion", False))

    @staticmethod
    def set_additive_animation_type(anim, t):
        anim._props["additive_anim_type"] = t

    @staticmethod
    def set_additive_base_pose_type(anim, t):
        anim._props["ref_pose_type"] = t


class AnimationCurveIdentifierExtensions(core.Object):
    @staticmethod
    def get_curve_identifier(name, curve_type):
        return _CurveId(str(name))

    @staticmethod
    def find_curve_identifier(anim, name, curve_type):
        return _CurveId(str(name))


class _CurveId:
    def __init__(self, name):
        self.name = name


class RichCurveKey:
    def __init__(self, time=0.0, value=0.0, interp_mode=None, **kw):
        self.time, self.value, self.interp_mode = time, value, interp_mode


class AnimSequenceFactory(core.Object):
    pass


class ARFilter(core.Object):
    pass


class TopLevelAssetPath:
    def __init__(self, package_name="", asset_name=""):
        self.package_name, self.asset_name = package_name, asset_name


def install(fake):
    for cls in (Skeleton, SkeletalMesh, AnimSequence, AnimationLibrary, AnimationCurveIdentifierExtensions,
                RichCurveKey, AnimSequenceFactory, ARFilter, TopLevelAssetPath):
        if hasattr(fake, "_classes"):
            fake._classes[cls.__name__] = cls
        setattr(fake, cls.__name__, cls)

    # AssetTools.create_asset with an AnimSequenceFactory: the factory's target skeleton lands on the new animation
    tools_cls = core.AssetTools
    if "_anim_create" not in tools_cls.__dict__:  # (getattr on a fake class answers a stub)
        orig = tools_cls.create_asset

        def create_asset(self, asset_name, package_path, asset_class=None, factory=None, calling_context=""):
            cls = asset_class
            if isinstance(factory, AnimSequenceFactory) or (cls is not None and cls.__name__ == "AnimSequence"):
                f = core._fake()
                cls = f.AnimSequence
                path = f"{package_path.rstrip('/')}/{asset_name}"
                if path in f.assets:
                    f.dialogs.append(("overwrite", path))
                    return None
                a = f.put_asset(path, cls(asset_name))
                if factory is not None and "target_skeleton" in factory._props:
                    a._props["skeleton"] = factory._props["target_skeleton"]
                return a
            return orig(self, asset_name, package_path, asset_class, factory, calling_context)
        tools_cls.create_asset = create_asset
        tools_cls._anim_create = True

    # the registry's filtered search, and asset-data tags (Skeleton, SequenceLength)
    reg = core.AssetRegistry
    if "get_assets" not in reg.__dict__:
        def get_assets(self, flt, skip_ar_filtered_assets=True):
            p = flt._props
            classes = {str(getattr(c, "asset_name", c)) for c in (p.get("class_paths") or [])}
            paths = [str(x).rstrip("/") for x in (p.get("package_paths") or [])]
            out = []
            for path, a in sorted(core._fake().assets.items()):
                if classes and type(a).__name__ not in classes and not any(
                        c.__name__ in classes for c in type(a).__mro__):
                    continue
                if paths and not any(x in ("", "/") or path.startswith(x + "/") for x in paths):
                    continue
                out.append(core.AssetData(a, path))
            return out
        reg.get_assets = get_assets
    def get_tag_value(self, name):
        a = self._obj
        if name == "Skeleton":
            sk = a._props.get("skeleton")
            return sk.get_path_name() if sk is not None else None
        if name == "SequenceLength" and isinstance(a, AnimSequence):
            return str(a.length_s)
        return None
    fake.tag_providers.append(get_tag_value)

    if "get_skeletal_mesh_asset" not in core.SkeletalMeshComponent.__dict__:
        core.SkeletalMeshComponent.get_skeletal_mesh_asset = lambda self: self._props.get("skeletal_mesh_asset")

    def anim(path: str, length_s: float = 2.0, fps: float = 30.0, curves: dict | None = None, skeleton: str = "",
             bones=()):
        """An AnimSequence at `path` with curves {name: (times, values)} on a skeleton (made if missing)."""
        a = fake.put_asset(path, AnimSequence(path.rsplit("/", 1)[-1]))
        a._data.update({"fps": float(fps), "frames": int(round(length_s * fps)),
                        "curves": {k: (list(t), list(v)) for k, (t, v) in (curves or {}).items()}, "bones": set(bones)})
        if skeleton:
            sk = fake.assets.get(skeleton) or fake.put_asset(skeleton, Skeleton(skeleton.rsplit("/", 1)[-1]))
            a._props["skeleton"] = sk
        return a
    fake.anim = anim

    def skeletal_mesh(path: str, skeleton: str):
        sk = fake.assets.get(skeleton) or fake.put_asset(skeleton, Skeleton(skeleton.rsplit("/", 1)[-1]))
        return fake.put_asset(path, SkeletalMesh(path.rsplit("/", 1)[-1], skeleton=sk))
    fake.skeletal_mesh = skeletal_mesh

    def metahuman(label: str, loc=(0.0, 0.0, 0.0), yaw: float = 0.0, face_mesh: str = "/Game/MH/Face/FaceMesh",
                  body_mesh: str = "/Game/MH/Body/BodyMesh"):
        """An actor with "Body" and "Face" skeletal mesh components (meshes on their own skeletons) and a head bone
        165 cm above it: enough of a MetaHuman for perf.state."""
        a = fake.spawn(core.Actor, label, location=core.Vector(*loc), rotation=core.Rotator(roll=0.0, pitch=0.0, yaw=yaw))
        for name, mesh in (("Body", body_mesh), ("Face", face_mesh)):
            c = a.add_component(core.SkeletalMeshComponent, name)
            c._props["skeletal_mesh_asset"] = fake.assets.get(mesh) or skeletal_mesh(mesh, mesh + "_Skeleton")
            c._props["bones"] = {"head": [loc[0], loc[1], loc[2] + 165.0]}
        return a
    fake.metahuman = metahuman
