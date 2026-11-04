"""Levels and actors: new/open/save, find and describe, spawn (shapes, assets, classes), move, aim, set, delete.

Actors are addressed by label. `level.find` and `level.describe` read the level as JSON (each actor's transform,
bounds, tags, folder) so a change can be checked by numbers; layout.* places things, scene.* converges a whole set.
"""
from __future__ import annotations

import unreal

from . import op
from ._layout import match
from ._util import actor, actor_info, actors as _all_actors, bounds_box, eas, rot, vec  # noqa: F401 (re-exported)
from .assets import load

LES = lambda: unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)  # noqa: E731
EAS = eas
SHAPES = {"cube": "/Engine/BasicShapes/Cube", "sphere": "/Engine/BasicShapes/Sphere", "cylinder": "/Engine/BasicShapes/Cylinder",
          "cone": "/Engine/BasicShapes/Cone", "plane": "/Engine/BasicShapes/Plane"}


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
        old = [a for a in _all_actors() if a.get_actor_label() == label]
        for a in old:
            EAS().destroy_actor(a)
    r = rot(rot_)
    if shape or asset:
        a = EAS().spawn_actor_from_object(load(SHAPES.get(shape, asset) if shape else asset), vec(loc), r)
    else:
        klass = getattr(unreal, cls, None) if cls else None
        if klass is None:
            from ..errors import OpError
            raise OpError(f"level.spawn needs a shape, an asset or a class name; got cls={cls!r}", code="bad_args",
                          hint="shape=cube|sphere|cylinder|cone|plane, asset=/Game/..., or cls=PointLight")
        a = EAS().spawn_actor_from_class(klass, vec(loc), r)
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


def _near(a, near, radius) -> bool:
    if near is None:
        return True
    c = a.get_actor_location()
    p = vec(near)
    return ((c.x - p.x) ** 2 + (c.y - p.y) ** 2 + (c.z - p.z) ** 2) ** 0.5 <= float(radius or 0)


def _inside(a, box) -> bool:
    if box is None:
        return True
    c = a.get_actor_location()
    (x0, y0, z0), (x1, y1, z1) = box
    return x0 <= c.x <= x1 and y0 <= c.y <= y1 and z0 <= c.z <= z1


@op("level.find", mutates=False, idempotent=True)
def find(*, label: str = "", cls: str = "", tag: str = "", folder: str = "", near: list = None,
         radius_cm: float = 100.0, box: list = None, limit: int = 200) -> list:
    """Actors matching every filter given, as JSON (label, class, loc, rot, scale, bounds, tags, folder, mesh).

    Args: label: glob (`Chair_*`) or case-insensitive substring. cls: class name substring (`Light`, `CineCamera`).
    tag: an actor tag. folder: outliner folder prefix. near + radius_cm: within a sphere ([x, y, z] cm). box:
    [[x0, y0, z0], [x1, y1, z1]] cm, by actor location. limit: at most this many (nearest `near` first, else label
    order).
    Returns: [{"label", "class", "loc", "rot", "scale", "bounds": {"min", "max", "size"}, "tags", "folder", ...}].
    Example: film-ue op level.find cls=Light 'near=[0,0,150]' radius_cm=500
    """
    found = []
    for a in _all_actors():
        if not match(a.get_actor_label(), label):
            continue
        if cls and cls.lower() not in a.get_class().get_name().lower():
            continue
        info = None
        if tag or folder:
            info = actor_info(a)
            if tag and tag not in info["tags"]:
                continue
            if folder and not info["folder"].startswith(folder):
                continue
        if not _near(a, near, radius_cm) or not _inside(a, box):
            continue
        found.append((a, info))
    if near is not None:
        p = vec(near)
        found.sort(key=lambda x: (x[0].get_actor_location() - p).length())
    else:
        found.sort(key=lambda x: x[0].get_actor_label())
    return [info or actor_info(a) for a, info in found[:limit]]


@op("level.get", mutates=False, idempotent=True)
def get(*, label: str, components: bool = True) -> dict:
    """One actor in detail: what level.find gives plus its components (name, class, and for meshes their mesh and
    materials).

    Example: film-ue op level.get label=Desk
    """
    a = actor(label)
    info = actor_info(a)
    if components:
        comps = []
        for c in a.get_components_by_class(unreal.ActorComponent):
            d = {"name": c.get_name(), "class": c.get_class().get_name()}
            if isinstance(c, unreal.StaticMeshComponent):
                m = c.get_editor_property("static_mesh")
                d["mesh"] = m.get_path_name().rsplit(".", 1)[0] if isinstance(m, unreal.Object) else ""
            if isinstance(c, unreal.PrimitiveComponent):
                mats = []
                for i in range(int(c.get_num_materials())):
                    m = c.get_material(i)
                    mats.append(m.get_path_name().rsplit(".", 1)[0] if isinstance(m, unreal.Object) else None)
                d["materials"] = mats
            comps.append(d)
        info["components"] = comps
    return info


@op("level.describe", mutates=False, idempotent=True)
def describe(*, actors: bool = False, partition: bool = True) -> dict:
    """The open level at a glance: its path, actor count by class, lights, cameras, the overall bounds of visible
    geometry, its World Partition summary (`partition`: wp.describe), and every actor (as level.find) with `actors`.

    Example: film-ue op level.describe
    """
    by_class: dict = {}
    lights, cameras, everything = [], [], []
    lo, hi = [float("inf")] * 3, [float("-inf")] * 3
    for a in _all_actors():
        c = a.get_class().get_name()
        by_class[c] = by_class.get(c, 0) + 1
        if isinstance(a, unreal.Light) or "Light" in c:
            lights.append(a.get_actor_label())
        if isinstance(a, unreal.CameraActor):
            cameras.append(a.get_actor_label())
        if isinstance(a, unreal.StaticMeshActor):
            b = bounds_box(a)
            lo = [min(lo[i], b[0][i]) for i in range(3)]
            hi = [max(hi[i], b[1][i]) for i in range(3)]
        if actors:
            everything.append(actor_info(a))
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    out = {"level": world.get_path_name().rsplit(".", 1)[0] if world else "", "count": sum(by_class.values()),
           "by_class": dict(sorted(by_class.items())), "lights": sorted(lights), "cameras": sorted(cameras),
           "geometry_bounds": {"min": [round(v, 1) for v in lo], "max": [round(v, 1) for v in hi]}
           if lo[0] != float("inf") else None}
    if partition:
        from . import _OPS
        if "wp.describe" in _OPS:
            try:
                out["partition"] = _OPS["wp.describe"]()
            except Exception as e:  # a describe must not fail on its optional part
                out["partition"] = {"error": f"{type(e).__name__}: {e}"}
    if actors:
        out["actors"] = everything
    return out


@op("level.tag", mutates=True, idempotent=True)
def tag(*, labels: list, add: list = (), remove: list = ()) -> dict:
    """Add and remove actor tags (for grouping: scene membership, QA subjects, render layers).

    Returns: {"changed": [labels whose tags changed]}.
    Example: film-ue op level.tag 'labels=["Desk","Chair"]' 'add=["set:office"]'
    """
    from ._util import set_tags, tags
    changed = []
    for lab in labels:
        a = actor(lab)
        old = tags(a)
        new = [t for t in old if t not in remove] + [t for t in add if t not in old]
        if new != old:
            set_tags(a, new)
            changed.append(lab)
    return {"changed": changed}


@op("level.folder", mutates=True, idempotent=True)
def folder(*, labels: list, path: str) -> dict:
    """Put actors in an outliner folder (`Set/Props`; '' for none): grouping that scene.describe and level.find
    can filter on.

    Example: film-ue op level.folder 'labels=["Desk","Chair"]' path=Office/Furniture
    """
    changed = []
    for lab in labels:
        a = actor(lab)
        if str(a.get_folder_path() or "") != path:
            a.set_folder_path(path)
            changed.append(lab)
    return {"changed": changed}


@op("level.material", mutates=True, idempotent=True)
def material(*, label: str, material: str, slot: int = 0) -> dict:
    """Put a material on a mesh actor's slot (every mesh component of it).

    Example: film-ue op level.material label=Desk material=/Game/M/MI_Oak
    """
    from ..errors import OpError
    a = actor(label)
    m = load(material)
    comps = a.get_components_by_class(unreal.MeshComponent)
    if not comps:
        raise OpError(f"{label} has no mesh to put a material on", code="bad_args", hint="level.get shows its components")
    changed = False
    for c in comps:
        if c.get_material(slot) != m:
            c.set_material(slot, m)
            changed = True
    return {"changed": changed}
