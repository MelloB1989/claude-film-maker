"""The fake `unreal` module: an in-memory editor (a level of actors, a content browser of assets, console, log, ticks)
with real value types (Vector, Rotator, LinearColor, Color, Transform, FrameNumber, FrameRate) and a permissive
fallback: any other class, enum value, static function or method exists and records its calls, so every op module
imports and runs without an engine. See README.md beside this file for what is faithful and what is a stub.
"""
from __future__ import annotations

import importlib
import math
import os
import pkgutil
import re
import sys
import tempfile
import types
from pathlib import Path

_ENUM_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
REPO = Path(__file__).resolve().parents[3]
FAKE: "FakeUnreal | None" = None  # the installed fake (classes reach it through here)


def _fake() -> "FakeUnreal":
    if FAKE is None:
        raise RuntimeError("fakeunreal is not installed (use the `ue` fixture or fakeunreal.install())")
    return FAKE


# ---------------------------------------------------------------------------------------------------------------------
# recording stubs

class Stub:
    """Anything the fake does not model: attributes are more stubs, calling one records the call and returns a stub
    (or what the test set with fake.stub(name, ...)). Truthy, iterable as empty, usable as a number 0."""

    def __init__(self, name: str):
        object.__setattr__(self, "_name", name)

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        return Stub(f"{self._name}.{attr}")

    def __setattr__(self, attr, value):
        _fake().calls.append((f"{self._name}.{attr}=", (value,), {}))

    def __call__(self, *args, **kwargs):
        return _fake()._record(self._name, args, kwargs)

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __bool__(self):
        return True

    def __float__(self):
        return 0.0

    def __int__(self):
        return 0

    def __repr__(self):
        return f"<Stub {self._name}>"


class EnumValue:
    """`unreal.SomeEnum.VALUE`: compares equal to itself and to its name."""

    def __init__(self, enum: str, name: str):
        self.enum, self.name, self.value = enum, name, name

    def __eq__(self, other):
        if isinstance(other, EnumValue):
            return (self.enum, self.name) == (other.enum, other.name)
        return other == self.name

    def __hash__(self):
        return hash((self.enum, self.name))

    def __repr__(self):
        return f"<{self.enum}.{self.name}>"


class _AutoMeta(type):
    """Unknown class attributes: ALL_CAPS is an enum value, anything else a recorded static function."""

    def __getattr__(cls, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        if _ENUM_RE.match(attr):
            v = EnumValue(cls.__name__, attr)
            type.__setattr__(cls, attr, v)
            return v
        return Stub(f"{cls.__name__}.{attr}")


# ---------------------------------------------------------------------------------------------------------------------
# value types

class Vector:
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __add__(self, o):
        return Vector(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o):
        return Vector(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, k):
        if isinstance(k, Vector):
            return Vector(self.x * k.x, self.y * k.y, self.z * k.z)
        return Vector(self.x * k, self.y * k, self.z * k)

    __rmul__ = __mul__

    def __truediv__(self, k):
        return Vector(self.x / k, self.y / k, self.z / k)

    def __neg__(self):
        return Vector(-self.x, -self.y, -self.z)

    def __eq__(self, o):
        return isinstance(o, Vector) and self.is_near_equal(o, 1e-6)

    def __hash__(self):
        return hash((round(self.x, 4), round(self.y, 4), round(self.z, 4)))

    def __repr__(self):
        return f"Vector({self.x:g}, {self.y:g}, {self.z:g})"

    def is_near_equal(self, o, tolerance: float = 1e-4) -> bool:
        return all(abs(a - b) <= tolerance for a, b in zip(self, o))

    def length(self) -> float:
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

    size = length

    def dot(self, o) -> float:
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, o) -> "Vector":
        return Vector(self.y * o.z - self.z * o.y, self.z * o.x - self.x * o.z, self.x * o.y - self.y * o.x)

    def normal(self, tolerance: float = 1e-8) -> "Vector":
        n = self.length()
        return self / n if n > tolerance else Vector()

    def distance(self, o) -> float:
        return (self - o).length()

    def to_tuple(self):
        return (self.x, self.y, self.z)

    def copy(self):
        return Vector(*self)


class Vector2D:
    def __init__(self, x: float = 0.0, y: float = 0.0):
        self.x, self.y = float(x), float(y)

    def __iter__(self):
        return iter((self.x, self.y))

    def __eq__(self, o):
        return isinstance(o, Vector2D) and (self.x, self.y) == (o.x, o.y)

    def __repr__(self):
        return f"Vector2D({self.x:g}, {self.y:g})"


class IntPoint:
    def __init__(self, x: int = 0, y: int = 0):
        self.x, self.y = int(x), int(y)

    def __eq__(self, o):
        return isinstance(o, IntPoint) and (self.x, self.y) == (o.x, o.y)


class Rotator:
    """Positional order is (roll, pitch, yaw), as in the engine's Python: the trap the ops avoid by using keywords."""

    def __init__(self, roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0):
        self.roll, self.pitch, self.yaw = float(roll), float(pitch), float(yaw)

    def __eq__(self, o):
        return isinstance(o, Rotator) and self.is_near_equal(o, 1e-6)

    def __hash__(self):
        return hash((round(self.roll, 4), round(self.pitch, 4), round(self.yaw, 4)))

    def __repr__(self):
        return f"Rotator(roll={self.roll:g}, pitch={self.pitch:g}, yaw={self.yaw:g})"

    def is_near_equal(self, o, error_tolerance: float = 1e-4) -> bool:
        def d(a, b):
            return abs((a - b + 180.0) % 360.0 - 180.0)
        return all(d(a, b) <= error_tolerance for a, b in
                   ((self.roll, o.roll), (self.pitch, o.pitch), (self.yaw, o.yaw)))

    def _axes(self):
        sp, cp = math.sin(math.radians(self.pitch)), math.cos(math.radians(self.pitch))
        sy, cy = math.sin(math.radians(self.yaw)), math.cos(math.radians(self.yaw))
        sr, cr = math.sin(math.radians(self.roll)), math.cos(math.radians(self.roll))
        x = Vector(cp * cy, cp * sy, sp)
        y = Vector(sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
        z = Vector(-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
        return x, y, z

    def get_forward_vector(self) -> Vector:
        return self._axes()[0]

    def get_right_vector(self) -> Vector:
        return self._axes()[1]

    def get_up_vector(self) -> Vector:
        return self._axes()[2]

    def rotate_vector(self, v) -> Vector:
        x, y, z = self._axes()
        return x * v.x + y * v.y + z * v.z

    def copy(self):
        return Rotator(roll=self.roll, pitch=self.pitch, yaw=self.yaw)


class LinearColor:
    def __init__(self, r: float = 0.0, g: float = 0.0, b: float = 0.0, a: float = 1.0):
        self.r, self.g, self.b, self.a = float(r), float(g), float(b), float(a)

    def __eq__(self, o):
        return isinstance(o, LinearColor) and (self.r, self.g, self.b, self.a) == (o.r, o.g, o.b, o.a)

    def __iter__(self):
        return iter((self.r, self.g, self.b, self.a))

    def __repr__(self):
        return f"LinearColor({self.r:g}, {self.g:g}, {self.b:g}, {self.a:g})"


class Color:
    """FColor: positional order is (b, g, r, a) as in the engine; use keywords."""

    def __init__(self, b: int = 0, g: int = 0, r: int = 0, a: int = 255):
        self.r, self.g, self.b, self.a = int(r), int(g), int(b), int(a)

    def __eq__(self, o):
        return isinstance(o, Color) and (self.r, self.g, self.b, self.a) == (o.r, o.g, o.b, o.a)


class Quat:
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0, w: float = 1.0):
        self.x, self.y, self.z, self.w = float(x), float(y), float(z), float(w)


class Transform:
    def __init__(self, location=None, rotation=None, scale=None):
        self.translation = location if location is not None else Vector()
        self.rotation = rotation if rotation is not None else Rotator()
        self.scale3d = scale if scale is not None else Vector(1, 1, 1)

    @property
    def location(self):
        return self.translation

    def transform_location(self, v):
        return self.translation + self.rotation.rotate_vector(v * self.scale3d)


class FrameNumber:
    def __init__(self, value: int = 0):
        self.value = int(value)

    def __eq__(self, o):
        return isinstance(o, FrameNumber) and self.value == o.value

    def __repr__(self):
        return f"FrameNumber({self.value})"


class FrameRate:
    def __init__(self, numerator: int = 30, denominator: int = 1):
        self.numerator, self.denominator = int(numerator), int(denominator)

    def __eq__(self, o):
        return isinstance(o, FrameRate) and (self.numerator, self.denominator) == (o.numerator, o.denominator)


class FrameTime:
    def __init__(self, frame_number=None, sub_frame: float = 0.0):
        self.frame_number = frame_number if frame_number is not None else FrameNumber(0)
        self.sub_frame = float(sub_frame)


class Name(str):
    pass


class Text(str):
    pass


class SoftObjectPath:
    def __init__(self, path: str = ""):
        self.path = path

    def __str__(self):
        return self.path


# ---------------------------------------------------------------------------------------------------------------------
# objects, actors, components, assets

class Object(metaclass=_AutoMeta):
    """A UObject: a name, an outer, editor properties (a dict), and recorded calls for methods it does not model."""

    def __init__(self, name: str | None = None, outer=None, **props):
        object.__setattr__(self, "_props", {})
        object.__setattr__(self, "_name", name or type(self).__name__)
        object.__setattr__(self, "_outer", outer)
        object.__setattr__(self, "_path", "")
        for k, v in props.items():
            self._props[k] = v

    # editor properties: also reachable as attributes, as in the engine
    def get_editor_property(self, name: str):
        if name not in self._props:
            self._props[name] = Stub(f"{type(self).__name__}.{name}")
        return self._props[name]

    def set_editor_property(self, name: str, value, notify_mode=None):
        self._props[name] = value
        _fake().calls.append((f"{type(self).__name__}.set_editor_property", (name, value), {}))

    def set_editor_properties(self, props: dict):
        for k, v in props.items():
            self.set_editor_property(k, v)

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        props = object.__getattribute__(self, "_props")
        if attr in props:
            return props[attr]
        return _BoundStub(self, attr)

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            object.__setattr__(self, attr, value)
        else:
            self._props[attr] = value

    def get_name(self) -> str:
        return self._name

    def get_fname(self) -> str:
        return self._name

    def rename(self, new_name=None, new_outer=None):
        object.__setattr__(self, "_name", new_name or self._name)
        return True

    def get_path_name(self) -> str:
        return self._path or (f"{self._outer.get_path_name()}.{self._name}" if self._outer is not None
                              else f"/Fake/{self._name}")

    def get_full_name(self) -> str:
        return f"{type(self).__name__} {self.get_path_name()}"

    def get_outer(self):
        return self._outer

    def get_typed_outer(self, cls):
        o = self._outer
        while o is not None and not isinstance(o, cls):
            o = o.get_outer()
        return o

    def get_class(self):
        return _uclass(type(self))

    def get_world(self):
        return _fake().world

    def modify(self, always_mark_dirty: bool = True) -> bool:
        return True

    def is_a(self, cls) -> bool:
        return isinstance(self, cls)

    @classmethod
    def static_class(cls):
        return _uclass(cls)

    @classmethod
    def cast(cls, obj):
        if isinstance(obj, cls):
            return obj
        raise TypeError(f"cannot cast {type(obj).__name__} to {cls.__name__}")

    def __repr__(self):
        return f"<{type(self).__name__} {self.get_path_name()}>"


class UClass:
    """What get_class() and static_class() return: one per Python class, with the engine's get_name() and
    get_path_name(); `py` is the Python class (for isinstance in fakes)."""

    def __init__(self, py):
        self.py = py

    def get_name(self) -> str:
        return self.py.__name__

    def get_path_name(self) -> str:
        return f"/Script/Engine.{self.py.__name__}"

    def __repr__(self):
        return f"<UClass {self.py.__name__}>"


_UCLASSES: dict = {}


def _uclass(py) -> UClass:
    if py not in _UCLASSES:
        _UCLASSES[py] = UClass(py)
    return _UCLASSES[py]


class _BoundStub(Stub):
    """A method or property the fake does not model, on an object: calls are recorded under Class.method."""

    def __init__(self, owner, attr):
        Stub.__init__(self, f"{type(owner).__name__}.{attr}")
        object.__setattr__(self, "_owner", owner)

    def __call__(self, *args, **kwargs):
        return _fake()._record(self._name, args, kwargs, owner=self._owner)


class ActorComponent(Object):
    def get_owner(self):
        return self._outer


class SceneComponent(ActorComponent):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.setdefault("relative_location", Vector())
        self._props.setdefault("relative_rotation", Rotator())
        self._props.setdefault("relative_scale3d", Vector(1, 1, 1))

    def get_world_location(self):
        owner = self.get_owner()
        return owner.get_actor_location() + self._props["relative_location"] if owner else self._props["relative_location"]

    def get_world_rotation(self):
        owner = self.get_owner()
        return owner.get_actor_rotation() if owner else self._props["relative_rotation"]

    def set_relative_location(self, loc, sweep=False, teleport=False):
        self._props["relative_location"] = loc

    def set_relative_rotation(self, rot, sweep=False, teleport=False):
        self._props["relative_rotation"] = rot

    def set_visibility(self, new_visibility: bool, propagate_to_children: bool = False):
        self._props["visible"] = bool(new_visibility)

    def is_visible(self) -> bool:
        return self._props.get("visible", True)

    def get_socket_location(self, socket_name):
        return self.get_world_location()


class PrimitiveComponent(SceneComponent):
    def get_num_materials(self) -> int:
        return len(self._props.get("override_materials", [])) or 1

    def set_material(self, element_index: int, material):
        mats = self._props.setdefault("override_materials", [])
        while len(mats) <= element_index:
            mats.append(None)
        mats[element_index] = material

    def get_material(self, element_index: int):
        mats = self._props.get("override_materials", [])
        return mats[element_index] if element_index < len(mats) else None


class MeshComponent(PrimitiveComponent):
    pass


class StaticMeshComponent(MeshComponent):
    def set_static_mesh(self, mesh) -> bool:
        self._props["static_mesh"] = mesh
        return True


class SkinnedMeshComponent(MeshComponent):
    """Bones: a table {name: [x, y, z] world cm} in _props["bones"] (fake.pose(actor, {...}) sets it; the older key
    "fake_bones" is read too). Sockets are bones. Without a table, a socket is the component's location."""

    def _bones(self) -> dict:
        return self._props.get("bones") or self._props.get("fake_bones") or {}

    def does_socket_exist(self, in_socket_name) -> bool:
        return str(in_socket_name) in self._bones()

    def get_socket_location(self, in_socket_name):
        b = self._bones().get(str(in_socket_name))
        return Vector(*b) if b is not None else self.get_world_location()

    def get_bone_index(self, bone_name) -> int:
        names = list(self._bones())
        return names.index(str(bone_name)) if str(bone_name) in names else -1

    def get_bone_name(self, bone_index: int):
        names = list(self._bones())
        return Name(names[bone_index]) if 0 <= bone_index < len(names) else Name("None")

    def get_num_bones(self) -> int:
        return len(self._bones())

    def get_all_socket_names(self) -> list:
        return [Name(n) for n in self._bones()]


class SkeletalMeshComponent(SkinnedMeshComponent):
    def set_skeletal_mesh_asset(self, mesh):
        self._props["skeletal_mesh_asset"] = mesh


class CameraComponent(SceneComponent):
    pass


class CineCameraComponent(CameraComponent):
    pass


class LightComponentBase(SceneComponent):
    def set_intensity(self, v):
        self._props["intensity"] = v

    def set_light_color(self, c, update_color_temperature: bool = True):
        self._props["light_color"] = c


class LightComponent(LightComponentBase):
    pass


class LocalLightComponent(LightComponent):
    pass


class PointLightComponent(LocalLightComponent):
    pass


class SpotLightComponent(PointLightComponent):
    pass


class RectLightComponent(LocalLightComponent):
    pass


class DirectionalLightComponent(LightComponent):
    pass


class SkyLightComponent(LightComponentBase):
    pass


class ExponentialHeightFogComponent(SceneComponent):
    pass


class Actor(Object):
    """A level actor: label, transform, components, tags, hidden flags, a box for its bounds."""
    COMPONENTS: tuple = ()  # (property name, component class) made with the actor; the first is its root

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.setdefault("tags", [])
        object.__setattr__(self, "_label", self._name)
        object.__setattr__(self, "_xf", Transform())
        object.__setattr__(self, "_extent", Vector(50, 50, 50))
        object.__setattr__(self, "_components", [])
        object.__setattr__(self, "_alive", True)
        comps = self.COMPONENTS or (("root_component", SceneComponent),)
        for prop, cls in comps:
            c = cls(prop, self)
            self._components.append(c)
            self._props[prop] = c

    def get_path_name(self) -> str:
        return f"{_fake().world.get_path_name()}:PersistentLevel.{self._name}"

    def get_actor_label(self) -> str:
        return self._label

    def set_actor_label(self, label: str, mark_dirty: bool = True):
        object.__setattr__(self, "_label", str(label))

    def get_actor_location(self):
        return self._xf.translation.copy()

    def set_actor_location(self, new_location, sweep: bool = False, teleport: bool = False):
        self._xf.translation = Vector(*new_location)
        return True

    def get_actor_rotation(self):
        return self._xf.rotation.copy()

    def set_actor_rotation(self, new_rotation, teleport_physics: bool = False):
        self._xf.rotation = new_rotation.copy()
        return True

    def set_actor_location_and_rotation(self, new_location, new_rotation, sweep: bool = False,
                                        teleport: bool = False):
        self.set_actor_location(new_location)
        self.set_actor_rotation(new_rotation)
        return True

    def get_actor_scale3d(self):
        return self._xf.scale3d.copy()

    def set_actor_scale3d(self, new_scale3d):
        self._xf.scale3d = Vector(*new_scale3d)

    def get_actor_transform(self):
        return Transform(self.get_actor_location(), self.get_actor_rotation(), self.get_actor_scale3d())

    def set_actor_transform(self, new_transform, sweep: bool = False, teleport: bool = False):
        self._xf = Transform(new_transform.translation, new_transform.rotation, new_transform.scale3d)
        return True

    def get_actor_forward_vector(self):
        return self._xf.rotation.get_forward_vector()

    def get_actor_right_vector(self):
        return self._xf.rotation.get_right_vector()

    def get_actor_up_vector(self):
        return self._xf.rotation.get_up_vector()

    def get_actor_bounds(self, only_colliding_components: bool = False, include_from_child_actors: bool = False):
        """(origin, box extent): the actor's location and the half-size set with fake.set_bounds (50 cm default)."""
        return self.get_actor_location(), self._extent * self._xf.scale3d

    def get_components_by_class(self, component_class):
        return [c for c in self._components if isinstance(c, component_class)]

    def get_component_by_class(self, component_class):
        found = self.get_components_by_class(component_class)
        return found[0] if found else None

    def add_component(self, cls, name: str):
        c = cls(name, self)
        self._components.append(c)
        return c

    def get_folder_path(self):
        return Name(self._props.get("__folder", ""))

    def set_folder_path(self, new_folder_path):
        self._props["__folder"] = str(new_folder_path)

    def actor_has_tag(self, tag) -> bool:
        return str(tag) in [str(t) for t in self._props["tags"]]

    def set_actor_hidden_in_game(self, new_hidden: bool):
        self._props["hidden"] = bool(new_hidden)

    def set_is_temporarily_hidden_in_editor(self, is_hidden: bool):
        self._props["temporarily_hidden"] = bool(is_hidden)

    def is_temporarily_hidden_in_editor(self, include_parent: bool = False) -> bool:
        return self._props.get("temporarily_hidden", False)

    def destroy_actor(self) -> bool:
        return _fake().world.remove(self)

    def attach_to_actor(self, parent_actor, socket_name="", location_rule=None, rotation_rule=None, scale_rule=None,
                        weld_simulated_bodies: bool = False):
        self._props["attach_parent"] = parent_actor
        return True

    def get_attach_parent_actor(self):
        return self._props.get("attach_parent")

    @property
    def root_component(self):
        return self._components[0]

    def is_valid(self) -> bool:
        return self._alive


class StaticMeshActor(Actor):
    COMPONENTS = (("static_mesh_component", StaticMeshComponent),)


class SkeletalMeshActor(Actor):
    COMPONENTS = (("skeletal_mesh_component", SkeletalMeshComponent),)


class CameraActor(Actor):
    COMPONENTS = (("scene_component", SceneComponent), ("camera_component", CameraComponent))


class CineCameraActor(CameraActor):
    COMPONENTS = (("scene_component", SceneComponent), ("camera_component", CineCameraComponent))

    def get_cine_camera_component(self):
        return self._props["camera_component"]


class Light(Actor):
    COMPONENTS = (("light_component", LightComponent),)


class PointLight(Light):
    COMPONENTS = (("point_light_component", PointLightComponent),)

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props["light_component"] = self._components[0]


class SpotLight(Light):
    COMPONENTS = (("spot_light_component", SpotLightComponent),)

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props["light_component"] = self._components[0]


class RectLight(Light):
    COMPONENTS = (("rect_light_component", RectLightComponent),)

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props["light_component"] = self._components[0]


class DirectionalLight(Light):
    COMPONENTS = (("directional_light_component", DirectionalLightComponent),)

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props["light_component"] = self._components[0]


class SkyLight(Actor):
    COMPONENTS = (("light_component", SkyLightComponent),)


class ExponentialHeightFog(Actor):
    COMPONENTS = (("component", ExponentialHeightFogComponent),)


class PostProcessVolume(Actor):
    pass


class World(Object):
    """The editor world: the level's actors in spawn order."""

    def __init__(self, name="FakeLevel", outer=None, **props):
        super().__init__(name, outer, **props)
        object.__setattr__(self, "_actors", [])
        object.__setattr__(self, "_path", f"/Game/Maps/{name}.{name}")

    def add(self, actor: Actor) -> Actor:
        self._actors.append(actor)
        return actor

    def remove(self, actor: Actor) -> bool:
        if actor in self._actors:
            self._actors.remove(actor)
            object.__setattr__(actor, "_alive", False)
            return True
        return False

    def actors(self, cls=None) -> list:
        return [a for a in self._actors if cls is None or isinstance(a, cls)]


# assets: anything created, imported or added lives in fake.assets by package path ("/Game/X/Y")

class StaticMesh(Object):
    pass


class SkeletalMesh(Object):
    pass


class Skeleton(Object):
    pass


class MaterialInterface(Object):
    pass


class Material(MaterialInterface):
    pass


class MaterialInstance(MaterialInterface):
    pass


class MaterialInstanceConstant(MaterialInstance):
    pass


class Texture(Object):
    pass


class Texture2D(Texture):
    pass


class SoundWave(Object):
    pass


class AnimationAsset(Object):
    pass


class AnimSequenceBase(AnimationAsset):
    pass


class AnimSequence(AnimSequenceBase):
    pass


class Blueprint(Object):
    pass


class MovieSceneSequence(Object):
    pass


class LevelSequence(MovieSceneSequence):
    pass


class AssetData:
    def __init__(self, obj: Object, package: str):
        self._obj, self.package_name = obj, Name(package)
        self.asset_name = Name(package.rsplit("/", 1)[-1])
        self.package_path = Name(package.rsplit("/", 1)[0])
        self.asset_class_path = types.SimpleNamespace(asset_name=Name(type(obj).__name__),
                                                      package_name=Name("/Script/Engine"))
        self.asset_class = Name(type(obj).__name__)
        self.object_path = Name(f"{package}.{self.asset_name}")

    def get_asset(self):
        return self._obj

    def get_full_name(self):
        return f"{self.asset_class} {self.object_path}"

    def is_valid(self):
        return True


def _package(path: str) -> str:
    """'/Game/A/B.B' or '/Game/A/B' -> '/Game/A/B'."""
    path = str(path)
    if path.rsplit("/", 1)[-1].count(".") == 1:
        path = path.rsplit(".", 1)[0]
    return path.rstrip("/")


class EditorAssetLibrary(Object):
    @staticmethod
    def does_asset_exist(asset_path: str) -> bool:
        return _package(asset_path) in _fake().assets

    @staticmethod
    def load_asset(asset_path: str):
        return _fake().assets.get(_package(asset_path))

    @staticmethod
    def save_asset(asset_to_save: str, only_if_is_dirty: bool = True) -> bool:
        _fake().saved.append(_package(asset_to_save))
        return _package(asset_to_save) in _fake().assets

    @staticmethod
    def save_loaded_asset(asset_to_save, only_if_is_dirty: bool = True) -> bool:
        _fake().saved.append(_package(asset_to_save.get_path_name()))
        return True

    @staticmethod
    def save_directory(directory_path: str, only_if_is_dirty: bool = True, recursive: bool = True) -> bool:
        _fake().saved.append(directory_path)
        return True

    @staticmethod
    def delete_asset(asset_path_to_delete: str) -> bool:
        return _fake().assets.pop(_package(asset_path_to_delete), None) is not None

    @staticmethod
    def delete_loaded_asset(asset_to_delete) -> bool:
        return EditorAssetLibrary.delete_asset(asset_to_delete.get_path_name())

    @staticmethod
    def rename_asset(source_asset_path: str, destination_asset_path: str) -> bool:
        a = _fake().assets.pop(_package(source_asset_path), None)
        if a is None or _package(destination_asset_path) in _fake().assets:
            return False
        _fake().put_asset(_package(destination_asset_path), a)
        return True

    @staticmethod
    def duplicate_asset(source_asset_path: str, destination_asset_path: str):
        src = _fake().assets.get(_package(source_asset_path))
        if src is None or _package(destination_asset_path) in _fake().assets:
            return None
        dup = type(src)(destination_asset_path.rsplit("/", 1)[-1], **dict(src._props))
        return _fake().put_asset(_package(destination_asset_path), dup)

    @staticmethod
    def list_assets(directory_path: str, recursive: bool = True, include_folder: bool = False) -> list:
        d = directory_path.rstrip("/") + "/"
        return sorted(f"{p}.{p.rsplit('/', 1)[-1]}" for p in _fake().assets
                      if p.startswith(d) and (recursive or "/" not in p[len(d):]))

    @staticmethod
    def does_directory_exist(directory_path: str) -> bool:
        d = directory_path.rstrip("/")
        return d in _fake().dirs or any(p.startswith(d + "/") for p in _fake().assets)

    @staticmethod
    def make_directory(directory_path: str) -> bool:
        _fake().dirs.add(directory_path.rstrip("/"))
        return True

    @staticmethod
    def delete_directory(directory_path: str) -> bool:
        d = directory_path.rstrip("/")
        for p in [p for p in _fake().assets if p.startswith(d + "/")]:
            del _fake().assets[p]
        _fake().dirs.discard(d)
        return True

    @staticmethod
    def find_asset_data(asset_path: str):
        a = _fake().assets.get(_package(asset_path))
        return AssetData(a, _package(asset_path)) if a is not None else None

    @staticmethod
    def get_path_name_for_loaded_asset(loaded_asset) -> str:
        return loaded_asset.get_path_name()

    @staticmethod
    def set_metadata_tag(obj, tag, value):
        obj._props.setdefault("__metadata", {})[str(tag)] = str(value)

    @staticmethod
    def get_metadata_tag(obj, tag) -> str:
        return obj._props.get("__metadata", {}).get(str(tag), "")


class AssetImportTask(Object):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.update({"filename": "", "destination_path": "", "destination_name": "", "automated": False,
                            "replace_existing": False, "save": False, "options": None, "imported_object_paths": []})


_FACTORY_MAKES = {"LevelSequenceFactoryNew": "LevelSequence", "MaterialFactoryNew": "Material",
                  "MaterialInstanceConstantFactoryNew": "MaterialInstanceConstant"}
_IMPORT_MAKES = {".fbx": "StaticMesh", ".obj": "StaticMesh", ".wav": "SoundWave", ".png": "Texture2D",
                 ".jpg": "Texture2D", ".exr": "Texture2D", ".tga": "Texture2D", ".hdr": "TextureCube"}


class AssetTools(Object):
    def create_asset(self, asset_name: str, package_path: str, asset_class=None, factory=None, calling_context=""):
        f = _fake()
        path = f"{package_path.rstrip('/')}/{asset_name}"
        if path in f.assets:  # the engine would open an overwrite dialog: tests must see this
            f.dialogs.append(("overwrite", path))
            return None
        cls = asset_class
        if cls is None and factory is not None:
            cls = getattr(f, _FACTORY_MAKES.get(type(factory).__name__, "Object"))
        return f.put_asset(path, (cls or Object)(asset_name))

    def import_asset_tasks(self, import_tasks):
        f = _fake()
        for t in import_tasks:
            stem, ext = os.path.splitext(os.path.basename(t.filename))
            name = t.destination_name or stem
            path = f"{t.destination_path.rstrip('/')}/{name}"
            options = t.options
            kind = _IMPORT_MAKES.get(ext.lower(), "Object")
            if kind == "StaticMesh" and options is not None and options._props.get("import_as_skeletal") is True:
                kind = "SkeletalMesh"
            if path in f.assets and not t.replace_existing:
                f.dialogs.append(("import-overwrite", path))
                continue
            f.put_asset(path, getattr(f, kind)(name, source_file=t.filename))
            t.imported_object_paths = [f"{path}.{name}"]
            f.imports.append((t.filename, path))

    def rename_assets(self, assets_and_names) -> bool:
        return True


class AssetToolsHelpers(Object):
    @staticmethod
    def get_asset_tools():
        return _fake().singleton(AssetTools)


class AssetRegistry(Object):
    def get_assets_by_path(self, package_path, recursive: bool = False, include_only_on_disk_assets: bool = False):
        d = str(package_path).rstrip("/") + "/"
        return [AssetData(a, p) for p, a in sorted(_fake().assets.items())
                if p.startswith(d) and (recursive or "/" not in p[len(d):])]

    def get_asset_by_object_path(self, object_path, include_only_on_disk_assets: bool = False):
        a = _fake().assets.get(_package(str(object_path)))
        return AssetData(a, _package(str(object_path))) if a is not None else None

    def get_assets_by_class(self, class_path_name, search_sub_classes: bool = False):
        name = str(getattr(class_path_name, "asset_name", class_path_name))
        return [AssetData(a, p) for p, a in sorted(_fake().assets.items()) if type(a).__name__ == name]

    def scan_paths_synchronous(self, paths, force_rescan: bool = False, ignore_deny_list_scan_filters: bool = False):
        return None

    def wait_for_completion(self):
        return None


class AssetRegistryHelpers(Object):
    @staticmethod
    def get_asset_registry():
        return _fake().singleton(AssetRegistry)


# subsystems

class EditorSubsystem(Object):
    pass


class EditorActorSubsystem(EditorSubsystem):
    def get_all_level_actors(self):
        return list(_fake().world.actors())

    def get_all_level_actors_components(self):
        return [c for a in _fake().world.actors() for c in a._components]

    def spawn_actor_from_class(self, actor_class, location=None, rotation=None, transient: bool = False):
        return _fake().spawn(actor_class, location=location, rotation=rotation)

    def spawn_actor_from_object(self, object_to_use, location=None, rotation=None, transient: bool = False):
        f = _fake()
        cls = {StaticMesh: StaticMeshActor, SkeletalMesh: SkeletalMeshActor}.get(type(object_to_use), Actor)
        a = f.spawn(cls, location=location, rotation=rotation)
        if isinstance(a, StaticMeshActor):
            a.static_mesh_component.set_static_mesh(object_to_use)
        a._props["spawned_from"] = object_to_use
        return a

    def destroy_actor(self, actor_to_destroy) -> bool:
        return _fake().world.remove(actor_to_destroy)

    def destroy_actors(self, actors_to_destroy) -> bool:
        return all([self.destroy_actor(a) for a in list(actors_to_destroy)])

    def get_selected_level_actors(self):
        return list(_fake().selection)

    def set_selected_level_actors(self, actors_to_select):
        _fake().selection = list(actors_to_select)

    def select_nothing(self):
        _fake().selection = []

    def duplicate_actor(self, actor_to_duplicate, to_world=None, offset=None):
        f = _fake()
        a = f.spawn(type(actor_to_duplicate), location=actor_to_duplicate.get_actor_location() + (offset or Vector()),
                    rotation=actor_to_duplicate.get_actor_rotation())
        return a


class UnrealEditorSubsystem(EditorSubsystem):
    def get_editor_world(self):
        return _fake().world

    def get_game_world(self):
        return None

    def get_level_viewport_camera_info(self):
        return True, Vector(), Rotator()


class LevelEditorSubsystem(EditorSubsystem):
    def load_level(self, asset_path: str) -> bool:
        f = _fake()
        name = _package(asset_path).rsplit("/", 1)[-1]
        if f.levels.get(_package(asset_path)) is None:
            f.levels[_package(asset_path)] = World(name)
        f.world = f.levels[_package(asset_path)]
        return True

    def new_level(self, asset_path: str, is_partitioned_world: bool = False) -> bool:
        f = _fake()
        name = _package(asset_path).rsplit("/", 1)[-1]
        f.levels[_package(asset_path)] = f.world = World(name)
        f.put_asset(_package(asset_path), f.world)
        return True

    def save_current_level(self) -> bool:
        _fake().saved.append(_fake().world.get_path_name())
        return True

    def save_all_dirty_levels(self) -> bool:
        return True

    def get_current_level(self):
        return _fake().world

    def editor_set_viewport_realtime(self, realtime: bool, viewport_config_key=""):
        _fake().viewport_realtime = realtime


class AssetEditorSubsystem(EditorSubsystem):
    def close_all_editors_for_asset(self, asset):
        return None

    def open_editor_for_assets(self, assets):
        return None


class EditorLevelLibrary(Object):
    """Deprecated in the engine (use the subsystems), kept because old scripts call it."""

    @staticmethod
    def get_all_level_actors():
        return list(_fake().world.actors())

    @staticmethod
    def get_editor_world():
        return _fake().world

    @staticmethod
    def spawn_actor_from_class(actor_class, location=None, rotation=None, transient: bool = False):
        return _fake().spawn(actor_class, location=location, rotation=rotation)

    @staticmethod
    def destroy_actor(actor_to_destroy) -> bool:
        return _fake().world.remove(actor_to_destroy)


class GameplayStatics(Object):
    @staticmethod
    def get_all_actors_of_class(world_context_object, actor_class):
        return _fake().world.actors(actor_class)

    @staticmethod
    def get_all_actors_with_tag(world_context_object, tag):
        return [a for a in _fake().world.actors() if a.actor_has_tag(tag)]


class MathLibrary(Object):
    @staticmethod
    def find_look_at_rotation(start, target):
        d = target - start
        return Rotator(roll=0.0, pitch=math.degrees(math.atan2(d.z, math.hypot(d.x, d.y))),
                       yaw=math.degrees(math.atan2(d.y, d.x)))

    @staticmethod
    def vector_length(a) -> float:
        return a.length()

    @staticmethod
    def get_forward_vector(in_rot):
        return in_rot.get_forward_vector()

    @staticmethod
    def clamp(value, min, max):  # noqa: A002 (the engine's names)
        return type(value)(min if value < min else max if value > max else value)


class Paths(Object):
    @staticmethod
    def project_dir():
        return _fake().root + "/"

    @staticmethod
    def project_saved_dir():
        return _fake().root + "/Saved/"

    @staticmethod
    def project_content_dir():
        return _fake().root + "/Content/"

    @staticmethod
    def project_log_dir():
        return _fake().root + "/Saved/Logs/"

    @staticmethod
    def project_intermediate_dir():
        return _fake().root + "/Intermediate/"

    @staticmethod
    def engine_dir():
        return _fake().root + "/Engine/"

    @staticmethod
    def get_project_file_path():
        return _fake().root + "/Fake.uproject"

    @staticmethod
    def convert_relative_path_to_full(path: str, base_path: str = "") -> str:
        return os.path.abspath(path)

    @staticmethod
    def file_exists(path: str) -> bool:
        return os.path.isfile(path)

    @staticmethod
    def directory_exists(path: str) -> bool:
        return os.path.isdir(path)


class SystemLibrary(Object):
    @staticmethod
    def get_engine_version() -> str:
        return _fake().engine_version

    @staticmethod
    def execute_console_command(world_context_object, command: str, specific_player=None):
        _fake().console.append(command)

    @staticmethod
    def get_platform_user_name() -> str:
        return "fake"

    @staticmethod
    def get_console_variable_float_value(variable_name: str) -> float:
        return float(_fake().cvars.get(variable_name, 0.0))

    @staticmethod
    def get_console_variable_int_value(variable_name: str) -> int:
        return int(_fake().cvars.get(variable_name, 0))


class ScopedEditorTransaction:
    def __init__(self, description: str = ""):
        self.description = description

    def __enter__(self):
        _fake().transactions.append(self.description)
        return self

    def __exit__(self, *exc):
        return False


class ScopedSlowTask:
    def __init__(self, amount_of_work: float = 0, default_message: str = "", enabled: bool = True):
        self.amount = amount_of_work

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def make_dialog(self, can_cancel: bool = False, allow_in_pie: bool = False):
        _fake().dialogs.append(("slow-task", ""))

    def enter_progress_frame(self, work: float = 1, desc: str = ""):
        return None

    def should_cancel(self) -> bool:
        return False


# ---------------------------------------------------------------------------------------------------------------------
# the module

_EXPORTS = {k: v for k, v in dict(globals()).items()
            if isinstance(v, type) and k not in ("Stub", "EnumValue", "_AutoMeta", "_BoundStub", "UClass")}


class FakeUnreal(types.ModuleType):
    """`sys.modules["unreal"]` in tests. Real value types and an in-memory editor; anything else is a stub that
    records its calls in `calls` (find them with `called(name)`).

    State: world (the open level; levels by path), assets ({package path: object}), dirs, saved, imports, console
    (commands run), cvars, logs ([(level, message)]), dialogs (anything that would have opened a modal: an op that
    lands one here fails the no-modal rule), transactions, selection, tick callbacks."""

    def __init__(self, root: str | None = None):
        super().__init__("unreal")
        self.__file__ = __file__
        self.root = root or tempfile.mkdtemp(prefix="fakeunreal-")
        self.engine_version = "5.8.4-0+++UE5+Release-5.8 (fake)"
        self.calls: list = []
        self.returns: dict = {}
        self.world = World("FakeLevel")
        self.levels = {"/Game/Maps/FakeLevel": self.world}
        self.assets: dict = {}
        self.dirs: set = set()
        self.saved: list = []
        self.imports: list = []
        self.console: list = []
        self.cvars: dict = {}
        self.logs: list = []
        self.dialogs: list = []
        self.transactions: list = []
        self.selection: list = []
        self.viewport_realtime = True
        self.ticks = 0
        self._singletons: dict = {}
        self._tick_callbacks: dict = {}
        self._next_handle = 1
        self._classes = dict(_EXPORTS)
        os.makedirs(os.path.join(self.root, "Saved", "Logs"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "Content"), exist_ok=True)
        for k, v in self._classes.items():
            setattr(self, k, v)

    # unknown names: CamelCase is a class (an Actor or Component subclass when its name says so), lower_case a
    # recorded function
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name[:1].isupper():
            base = (Actor if name.endswith(("Actor", "Volume")) else SceneComponent if name.endswith("Component")
                    else Object)
            cls = _AutoMeta(name, (base,), {"__module__": "unreal"})
            setattr(self, name, cls)
            self._classes[name] = cls
            return cls
        return Stub(name)

    # recording
    def _record(self, name: str, args, kwargs, owner=None):
        self.calls.append((name, args, kwargs))
        r = self.returns.get(name, Stub(name + "()"))
        return r(*args, **kwargs) if callable(r) and not isinstance(r, (Stub, Object, type)) else r

    def stub(self, name: str, result) -> None:
        """Make the recorded function or method `name` ("Class.method" or "function") return `result`, or call it
        when it is a plain function (it gets the call's arguments)."""
        self.returns[name] = result

    def called(self, name: str) -> list:
        """The (args, kwargs) of every call to `name` ("Class.method", "function" or "Class.set_editor_property")."""
        return [(a, k) for n, a, k in self.calls if n == name]

    # top-level engine functions
    def log(self, msg):
        self.logs.append(("log", str(msg)))

    def log_warning(self, msg):
        self.logs.append(("warning", str(msg)))

    def log_error(self, msg):
        self.logs.append(("error", str(msg)))

    def get_editor_subsystem(self, cls):
        return self.singleton(cls)

    def get_engine_subsystem(self, cls):
        return self.singleton(cls)

    def get_default_object(self, cls):
        return self.singleton(cls)

    def new_object(self, type, outer=None, name=None, base_type=None):  # noqa: A002 (the engine's name)
        return type(name, outer)

    def load_asset(self, name: str, type=None, follow_redirectors: bool = True):  # noqa: A002
        return self.assets.get(_package(name))

    def load_object(self, outer, name: str, type=None, follow_redirectors: bool = True):  # noqa: A002
        return self.assets.get(_package(name))

    def find_object(self, outer, name: str, type=None, follow_redirectors: bool = True):  # noqa: A002
        return self.assets.get(_package(name))

    def load_class(self, outer, name: str, type=None):  # noqa: A002
        return getattr(self, str(name).rsplit(".", 1)[-1].removesuffix("_C"))

    def register_slate_post_tick_callback(self, callable_):
        h = self._next_handle
        self._next_handle += 1
        self._tick_callbacks[h] = callable_
        return h

    register_slate_pre_tick_callback = register_slate_post_tick_callback

    def unregister_slate_post_tick_callback(self, handle):
        self._tick_callbacks.pop(handle, None)

    unregister_slate_pre_tick_callback = unregister_slate_post_tick_callback

    # test helpers
    def singleton(self, cls):
        if cls not in self._singletons:
            self._singletons[cls] = cls()
        return self._singletons[cls]

    def tick(self, n: int = 1, dt: float = 1 / 30) -> None:
        """Run the registered Slate tick callbacks n times."""
        for _ in range(n):
            self.ticks += 1
            for cb in list(self._tick_callbacks.values()):
                cb(dt)

    def spawn(self, cls, label: str = "", location=None, rotation=None, extent=None, **props):
        """Put an actor of `cls` in the open level (as spawn_actor_from_class does); `extent` is its bounds' half
        size in cm."""
        if isinstance(cls, str):
            cls = getattr(self, cls)
        if isinstance(cls, UClass):
            cls = cls.py
        n = sum(1 for a in self.world.actors() if type(a) is cls)
        a = cls(f"{cls.__name__}_{n}", self.world, **props)
        a.set_actor_label(label or f"{cls.__name__}{n or ''}")
        if location is not None:
            a.set_actor_location(location)
        if rotation is not None:
            a.set_actor_rotation(rotation)
        if extent is not None:
            object.__setattr__(a, "_extent", Vector(*extent))
        return self.world.add(a)

    def pose(self, actor, bones: dict):
        """Give an actor's skeletal mesh a pose: {bone: [x, y, z]} in world cm (read by get_socket_location etc.)."""
        a = self.actor(actor) if isinstance(actor, str) else actor
        comp = a.get_components_by_class(SkinnedMeshComponent)[0]
        comp._props["bones"] = {k: list(v) for k, v in bones.items()}
        return a

    def actor(self, label: str):
        """The actor with this label, or None."""
        return next((a for a in self.world.actors() if a.get_actor_label() == label), None)

    def put_asset(self, path: str, obj: Object) -> Object:
        path = _package(path)
        object.__setattr__(obj, "_name", path.rsplit("/", 1)[-1])
        object.__setattr__(obj, "_path", f"{path}.{path.rsplit('/', 1)[-1]}")
        self.assets[path] = obj
        return obj

    def add_asset(self, path: str, cls="Object", **props) -> Object:
        """Put an asset at a package path ("/Game/Meshes/SM_Chair"), of a class or class name, with properties."""
        if isinstance(cls, str):
            cls = getattr(self, cls)
        return self.put_asset(path, cls(path.rsplit("/", 1)[-1], **props))


def _load_extensions(fake: FakeUnreal) -> None:
    """Every fakeunreal/ext_<area>.py with an install(fake): an area's own fakes (Sequencer, MetaHumans, MRQ, ...),
    owned by that area so nobody edits this file to add theirs."""
    here = os.path.dirname(__file__)
    for info in sorted(pkgutil.iter_modules([here]), key=lambda i: i.name):
        if info.name.startswith("ext_"):
            mod = importlib.import_module(f"{__package__}.{info.name}")
            if hasattr(mod, "install"):
                mod.install(fake)


def install(root: str | None = None) -> FakeUnreal:
    """Make a fresh fake and put it in sys.modules as `unreal`; forget any fmbridge already imported (it holds the
    old one)."""
    global FAKE
    FAKE = FakeUnreal(root)
    sys.modules["unreal"] = FAKE
    _purge_fmbridge()
    _load_extensions(FAKE)
    return FAKE


def uninstall() -> None:
    global FAKE
    sys.modules.pop("unreal", None)
    _purge_fmbridge()
    FAKE = None


def _purge_fmbridge() -> None:
    for m in [k for k in sys.modules if k == "fmbridge" or k.startswith("fmbridge.")]:
        del sys.modules[m]


def load_fmbridge():
    """Import the bridge's ops (and so every op module) from the repo's unreal/ against the installed fake."""
    p = str(REPO / "unreal")
    if p not in sys.path:
        sys.path.insert(0, p)
    return importlib.import_module("fmbridge.ops")


def drive(result, max_ticks: int = 100000):
    """Run a multi-tick job the way the server does: step the generator once per fake tick (a `yield 0.5` wait is
    one tick here) until it returns; plain results pass through. Returns (result, ticks)."""
    import inspect
    if not inspect.isgenerator(result):
        return result, 0
    n = 0
    while True:
        try:
            next(result)
        except StopIteration as e:
            return e.value, n
        n += 1
        FAKE.tick(1)
        if n >= max_ticks:
            raise RuntimeError(f"multi-tick job still running after {max_ticks} ticks")


def run_op(name: str, /, **args):
    """Call an op as the bridge would (argument check, then the op; a generator driven to its end); its result."""
    ops = load_fmbridge()
    return drive(ops.call(name, **args))[0]


def pure(relpath: str):
    """Import one engine-free module of the bridge by its path under unreal/fmbridge ("ops/_layout.py") without
    importing the package (which needs `unreal`): for unit tests of pure planners and math."""
    import importlib.util
    path = REPO / "unreal" / "fmbridge" / relpath
    name = "fmbridge_pure_" + relpath.replace("/", "_").removesuffix(".py")
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
