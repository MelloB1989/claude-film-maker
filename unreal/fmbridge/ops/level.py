"""Levels and actors: new/open/save, list, spawn (shapes, assets, classes), move, aim, delete."""
from __future__ import annotations

import unreal

from . import op
from .assets import load

LES = lambda: unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)  # noqa: E731
EAS = lambda: unreal.get_editor_subsystem(unreal.EditorActorSubsystem)  # noqa: E731
SHAPES = {"cube": "/Engine/BasicShapes/Cube", "sphere": "/Engine/BasicShapes/Sphere", "cylinder": "/Engine/BasicShapes/Cylinder",
          "cone": "/Engine/BasicShapes/Cone", "plane": "/Engine/BasicShapes/Plane"}


def vec(v) -> unreal.Vector:
    return v if isinstance(v, unreal.Vector) else unreal.Vector(*[float(x) for x in v])


def rot(r) -> unreal.Rotator:
    """{"pitch","yaw","roll"} (or a Rotator) to a Rotator, by keyword: never positional."""
    if isinstance(r, unreal.Rotator):
        return r
    r = r or {}
    return unreal.Rotator(roll=float(r.get("roll", 0)), pitch=float(r.get("pitch", 0)), yaw=float(r.get("yaw", 0)))


def actor(label: str):
    for a in EAS().get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    raise ValueError(f"no actor labelled {label!r}")


def look_rot(src, target) -> unreal.Rotator:
    return unreal.MathLibrary.find_look_at_rotation(vec(src), vec(target))


@op("level.new")
def new_level(path: str) -> str:
    """A new empty level at a content path, opened."""
    LES().new_level(path)
    return path


@op("level.open")
def open_level(path: str) -> str:
    """Open a level."""
    LES().load_level(path)
    return path


@op("level.save")
def save_level() -> bool:
    """Save the open level."""
    return LES().save_current_level()


@op("level.actors")
def actors(contains: str = "", cls: str = "") -> list:
    """The open level's actors: [label, class, location]."""
    out = []
    for a in EAS().get_all_level_actors():
        lab, c = a.get_actor_label(), a.get_class().get_name()
        if contains.lower() in lab.lower() and (not cls or cls.lower() in c.lower()):
            p = a.get_actor_location()
            out.append([lab, c, [round(p.x, 1), round(p.y, 1), round(p.z, 1)]])
    return out


@op("level.spawn")
def spawn(label: str, asset: str = "", cls: str = "", shape: str = "", loc=(0, 0, 0), rot_=None, size=None, scale=None,
          material: str = "", replace: bool = True) -> str:
    """Spawn an actor: a basic `shape` (cube/sphere/cylinder/cone/plane, `size` in cm), an `asset` (mesh, blueprint) or a
    `cls` ('RectLight', 'CineCameraActor', ...). Replaces an actor with the same label when `replace`."""
    if replace:
        try:
            EAS().destroy_actor(actor(label))
        except ValueError:
            pass
    r = rot(rot_)
    if shape or asset:
        a = EAS().spawn_actor_from_object(load(SHAPES.get(shape, asset) if shape else asset), vec(loc), r)
    else:
        a = EAS().spawn_actor_from_class(getattr(unreal, cls), vec(loc), r)
    a.set_actor_label(label)
    if size is not None:
        a.set_actor_scale3d(unreal.Vector(size[0] / 100, size[1] / 100, size[2] / 100))
    elif scale is not None:
        a.set_actor_scale3d(vec(scale) if isinstance(scale, (list, tuple)) else unreal.Vector(scale, scale, scale))
    if material:
        for c in a.get_components_by_class(unreal.StaticMeshComponent):
            c.set_material(0, load(material))
    return label


@op("level.move")
def move(label: str, loc=None, rot_=None, look_at=None, size=None, scale=None) -> list:
    """Move, turn, aim (`look_at` [x,y,z]), resize (`size` cm for basic shapes) or scale an actor."""
    a = actor(label)
    if loc is not None:
        a.set_actor_location(vec(loc), False, False)
    if look_at is not None:
        a.set_actor_rotation(look_rot(a.get_actor_location(), look_at), False)
    elif rot_ is not None:
        a.set_actor_rotation(rot(rot_), False)
    if size is not None:
        a.set_actor_scale3d(unreal.Vector(size[0] / 100, size[1] / 100, size[2] / 100))
    if scale is not None:
        a.set_actor_scale3d(vec(scale) if isinstance(scale, (list, tuple)) else unreal.Vector(scale, scale, scale))
    p = a.get_actor_location()
    return [p.x, p.y, p.z]


@op("level.delete")
def delete(labels: list) -> int:
    """Delete actors by label (missing ones are skipped)."""
    n = 0
    for lab in labels:
        try:
            EAS().destroy_actor(actor(lab))
            n += 1
        except ValueError:
            pass
    return n


@op("level.set")
def set_props(label: str, props: dict, component: str = "") -> dict:
    """Set editor properties on an actor or one of its components (by class name, e.g. 'RectLightComponent')."""
    a = actor(label)
    target = a
    if component:
        target = next(c for c in a.get_components_by_class(unreal.ActorComponent) if c.get_class().get_name() == component
                      or c.get_name() == component)
    for k, v in props.items():
        if isinstance(v, list) and len(v) in (3, 4) and k.endswith(("color", "colour")):
            v = unreal.LinearColor(*v, *([1.0] if len(v) == 3 else []))
        target.set_editor_property(k, v)
    return {k: str(target.get_editor_property(k)) for k in props}


@op("level.bone")
def bone(label: str, component: str, bones: list) -> dict:
    """World locations of bones/sockets on an actor's skeletal mesh component."""
    a = actor(label)
    c = next(c for c in a.get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == component)
    return {b: [round(v, 2) for v in (lambda p: (p.x, p.y, p.z))(c.get_socket_location(b))] for b in bones}
