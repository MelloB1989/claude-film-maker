"""Shared helpers for op modules (not ops): argument parsing in the conventions' units, actors by label with
did-you-mean, an actor as JSON. Import from here instead of copying (docs/unreal/CONVENTIONS.md section 9).

    from ._util import vec, rot, rot_json, color, actor, actors, actor_info
"""
from __future__ import annotations

import unreal

from ..errors import OpError, not_found


def eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def vec(v) -> "unreal.Vector":
    """[x, y, z] (cm), a single number (all three), or a Vector, to a Vector."""
    if isinstance(v, unreal.Vector):
        return v
    if isinstance(v, (int, float)):
        return unreal.Vector(float(v), float(v), float(v))
    try:
        x, y, z = (float(a) for a in v)
    except (TypeError, ValueError):
        raise OpError(f"expected [x, y, z] in cm, got {v!r}", code="bad_args") from None
    return unreal.Vector(x, y, z)


def rot(r) -> "unreal.Rotator":
    """{"pitch", "yaw", "roll"} degrees (missing ones 0), a bare yaw number, or a Rotator, to a Rotator; by keyword,
    never positional (the engine's positional order is roll, pitch, yaw)."""
    if isinstance(r, unreal.Rotator):
        return r
    if isinstance(r, (int, float)):
        return unreal.Rotator(roll=0.0, pitch=0.0, yaw=float(r))
    r = r or {}
    if not isinstance(r, dict):
        raise OpError(f"rotation must be {{'pitch', 'yaw', 'roll'}} in degrees, got {r!r} (never a list: the "
                      f"engine's positional order is roll, pitch, yaw)", code="bad_args")
    bad = set(r) - {"pitch", "yaw", "roll"}
    if bad:
        raise OpError(f"unknown rotation keys {sorted(bad)}", code="bad_args", hint="use pitch, yaw, roll")
    return unreal.Rotator(roll=float(r.get("roll", 0)), pitch=float(r.get("pitch", 0)), yaw=float(r.get("yaw", 0)))


def rot_json(r, nd: int = 3) -> dict:
    return {"pitch": round(r.pitch, nd), "yaw": round(r.yaw, nd), "roll": round(r.roll, nd)}


def vec_json(v, nd: int = 2) -> list:
    return [round(v.x, nd), round(v.y, nd), round(v.z, nd)]


def color(c) -> "unreal.LinearColor":
    """[r, g, b] or [r, g, b, a] linear 0..1 (or a LinearColor) to a LinearColor."""
    if isinstance(c, unreal.LinearColor):
        return c
    c = list(c)
    if len(c) not in (3, 4):
        raise OpError(f"colour must be [r, g, b] or [r, g, b, a] linear 0..1, got {c!r}", code="bad_args")
    return unreal.LinearColor(r=float(c[0]), g=float(c[1]), b=float(c[2]), a=float(c[3]) if len(c) == 4 else 1.0)


def actors() -> list:
    return list(eas().get_all_level_actors())


def find_actor(label: str):
    """The actor labelled `label`, or None."""
    for a in actors():
        if a.get_actor_label() == label:
            return a
    return None


def actor(label: str):
    """The actor labelled `label`; a not_found OpError (also a ValueError) naming the nearest labels otherwise."""
    a = find_actor(label)
    if a is None:
        raise not_found("actor", label, [x.get_actor_label() for x in actors()], hint="list them with level.find")
    return a


def bounds_box(a) -> tuple:
    """An actor's world bounds as a (min, max) box in cm."""
    o, e = a.get_actor_bounds(False)
    return ((o.x - e.x, o.y - e.y, o.z - e.z), (o.x + e.x, o.y + e.y, o.z + e.z))


def tags(a) -> list:
    return [str(t) for t in (a.get_editor_property("tags") or [])]


def set_tags(a, new: list) -> None:
    a.set_editor_property("tags", [str(t) for t in new])


def mesh_path(a) -> str:
    """The static mesh a StaticMeshActor shows ('' for anything else)."""
    c = a.get_component_by_class(unreal.StaticMeshComponent) if hasattr(a, "get_component_by_class") else None
    if c is None:
        return ""
    m = c.get_editor_property("static_mesh")
    return m.get_path_name().rsplit(".", 1)[0] if isinstance(m, unreal.Object) else ""


def actor_info(a, nd: int = 2) -> dict:
    """An actor as JSON: label, class, loc [cm], rot {pitch, yaw, roll}, scale, bounds {min, max, size}, tags,
    folder, hidden, mesh (static mesh actors)."""
    b = bounds_box(a)
    info = {"label": a.get_actor_label(), "class": a.get_class().get_name(),
            "loc": vec_json(a.get_actor_location(), nd), "rot": rot_json(a.get_actor_rotation()),
            "scale": vec_json(a.get_actor_scale3d(), 4),
            "bounds": {"min": [round(v, nd) for v in b[0]], "max": [round(v, nd) for v in b[1]],
                       "size": [round(b[1][i] - b[0][i], nd) for i in range(3)]},
            "tags": tags(a)}
    try:
        info["folder"] = str(a.get_folder_path() or "")
    except Exception:  # folders are editor-only; a cooked build has none
        info["folder"] = ""
    hidden = a.get_editor_property("hidden")
    info["hidden"] = hidden if isinstance(hidden, bool) else False
    m = mesh_path(a)
    if m:
        info["mesh"] = m
    return info
