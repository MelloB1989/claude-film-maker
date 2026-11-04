"""Helpers for the env.* and light.* ops (not ops): owned actors, typed property writes that report a change,
engine values to JSON and back, lighting channels, and small state blobs kept in actor tags.

Ownership: every actor an env/light op makes carries the tag "fm_env" and "fm_owner:<name>" (the spec name, or
"manual" for a direct op call). Only those are ever replaced or removed; an actor with the same label that the ops
did not make is a conflict, never overwritten.
"""
from __future__ import annotations

import json
import math
import re

import unreal

from ..envlib import photometry as ph
from ..errors import OpError
from .assets import load
from .level import EAS, actor as _actor_by_label

TAG = "fm_env"
_ENUM = re.compile(r"^([A-Z][A-Za-z0-9]+)\.([A-Z][A-Z0-9_]*)$")


# ------------------------------------------------------------------------------------------------ actors

def find(label: str):
    try:
        return _actor_by_label(label)
    except ValueError:
        return None


def tags_of(a) -> list:
    return [str(t) for t in (a.get_editor_property("tags") or [])]


def is_owned(a) -> bool:
    return TAG in tags_of(a)


def owner_of(a):
    for t in tags_of(a):
        if t.startswith("fm_owner:"):
            return t.split(":", 1)[1]
    return None


def tag_value(a, key: str):
    for t in tags_of(a):
        if t.startswith(key + ":"):
            return t.split(":", 1)[1]
    return None


def set_tags(a, updates: dict) -> None:
    """Set "key:value" tags (None removes the key), keeping every other tag."""
    tags = [t for t in tags_of(a) if not any(t.startswith(k + ":") for k in updates)]
    tags += [f"{k}:{v}" for k, v in updates.items() if v is not None]
    a.set_editor_property("tags", tags)


def ensure(label: str, cls_name: str, owner: str = "manual", role: str = "", loc=None, rot=None, asset: str = ""):
    """The actor `label` of class `cls_name`, made if missing; (actor, created). An actor with that label of another
    class is replaced when the ops made it, and a conflict otherwise."""
    a = find(label)
    if a is not None:
        cname = a.get_class().get_name().removesuffix("_C")
        if not is_owned(a):
            raise OpError(f"{label!r} exists ({cname}) but was not made by the env/light ops", code="conflict",
                          hint="use another label, or delete it first with level.delete")
        if asset or cname == cls_name:
            return a, False
        EAS().destroy_actor(a)  # ours, of another class (a spot that becomes a rect): remake it
    v = unreal.Vector(*[float(x) for x in (loc or (0, 0, 0))])
    r = rotator(rot or {})
    if asset:
        obj = load(asset)
        if obj is None:
            raise OpError(f"no asset {asset!r}", code="not_found")
        a = EAS().spawn_actor_from_object(obj, v, r)
    else:
        cls = getattr(unreal, cls_name, None)
        if cls is None:
            raise OpError(f"this engine has no class {cls_name!r}", code="unsupported")
        a = EAS().spawn_actor_from_class(cls, v, r)
    if a is None:
        raise OpError(f"could not spawn {cls_name} {label!r}", code="engine")
    a.set_actor_label(label)
    a.set_editor_property("tags", [TAG, f"fm_owner:{owner or 'manual'}"] + ([f"fm_role:{role}"] if role else []))
    return a, True


def remove(labels, only_owned: bool = True) -> list:
    gone = []
    for lab in labels:
        a = find(lab)
        if a is None or (only_owned and not is_owned(a)):
            continue
        EAS().destroy_actor(a)
        gone.append(lab)
    return gone


def owned_actors(owner: str = None) -> list:
    out = []
    for a in EAS().get_all_level_actors():
        if is_owned(a) and (owner is None or owner_of(a) == owner):
            out.append(a)
    return out


def component(a, cls_name: str):
    c = a.get_component_by_class(getattr(unreal, cls_name))
    if c is None:
        raise OpError(f"{a.get_actor_label()!r} has no {cls_name}", code="engine")
    return c


def rotator(r) -> "unreal.Rotator":
    """{"pitch","yaw","roll"} to a Rotator, by keyword (never positional: its order is roll, pitch, yaw)."""
    return unreal.Rotator(roll=float(r.get("roll", 0.0)), pitch=float(r.get("pitch", 0.0)), yaw=float(r.get("yaw", 0.0)))


def place(a, loc=None, rot=None) -> bool:
    """Move/turn an actor; True when it moved."""
    changed = False
    if loc is not None:
        p = a.get_actor_location()
        if math.dist([p.x, p.y, p.z], loc) > 0.01:
            a.set_actor_location(unreal.Vector(*[float(x) for x in loc]), False, False)
            changed = True
    if rot is not None:
        from ..envlib.lights import same_rotation
        if not same_rotation(rot_json(a.get_actor_rotation()), rot, 0.01):
            a.set_actor_rotation(rotator(rot), False)
            changed = True
    return changed


# ------------------------------------------------------------------------------------------------ values

def rot_json(r) -> dict:
    return {"pitch": round(float(r.pitch), 4), "yaw": round(float(r.yaw), 4), "roll": round(float(r.roll), 4)}


def color_linear_to_fcolor(c):
    """A linear [r, g, b(, a)] to an sRGB FColor, by keyword (positional order is B, G, R, A)."""
    r, g, b = [int(round(max(0.0, min(1.0, ph.linear_to_srgb(float(x)))) * 255)) for x in list(c)[:3]]
    return unreal.Color(r=r, g=g, b=b, a=255)


def fcolor_to_linear(c) -> list:
    return [round(ph.srgb_to_linear(float(getattr(c, k)) / 255.0), 4) for k in ("r", "g", "b")]


def to_json(v):
    """An engine value as plain JSON: vectors and colours to lists (FColor to linear), rotators to dicts, enums to
    "Enum.NAME", objects to their package path, lighting channels to a channel list."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (list, tuple)):
        return [to_json(x) for x in v]
    t = type(v).__name__
    if t == "Color":
        return fcolor_to_linear(v)
    if t == "LinearColor":
        return [round(float(v.r), 6), round(float(v.g), 6), round(float(v.b), 6)] + \
               ([] if abs(float(v.a) - 1.0) < 1e-6 else [round(float(v.a), 6)])
    if t == "Vector4":
        return [round(float(v.x), 6), round(float(v.y), 6), round(float(v.z), 6), round(float(v.w), 6)]
    if t == "Vector":
        return [round(float(v.x), 4), round(float(v.y), 4), round(float(v.z), 4)]
    if t == "Rotator":
        return rot_json(v)
    if t == "LightingChannels":
        return [k for k in range(3) if bool(v.get_editor_property(f"channel{k}"))]
    if hasattr(v, "name") and hasattr(v, "value") and not hasattr(v, "get_path_name"):  # an enum value
        enum = getattr(v, "enum", None) or type(v).__name__
        return f"{enum}.{v.name}"
    if hasattr(v, "get_path_name"):
        p = v.get_path_name()
        return p.split(".", 1)[0] if p else None
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def channels_struct(chs) -> "unreal.LightingChannels":
    lc = unreal.LightingChannels()
    for k in range(3):
        lc.set_editor_property(f"channel{k}", k in chs)
    return lc


def coerce(current, value, prop: str = ""):
    """A JSON value as the engine type of `current` (the property's present value) or by its form."""
    if isinstance(value, str) and _ENUM.match(value):
        e, m = _ENUM.match(value).groups()
        return getattr(getattr(unreal, e), m)
    t = type(current).__name__ if current is not None else ""
    if prop == "lighting_channels" or t == "LightingChannels":
        return channels_struct(value)
    if isinstance(value, (list, tuple)):
        if t == "Color":
            return color_linear_to_fcolor(value)
        if t == "Vector4" or (prop.startswith("color_") and len(value) == 4):
            return unreal.Vector4(*[float(x) for x in value])
        if t == "LinearColor" or prop.endswith(("_color", "_luminance", "_tint", "_emissive", "_scattering",
                                                  "_absorption", "_factor")) and len(value) in (3, 4):
            vals = [float(x) for x in value] + ([1.0] if len(value) == 3 else [])
            return unreal.LinearColor(r=vals[0], g=vals[1], b=vals[2], a=vals[3])
        if t == "Vector":
            return unreal.Vector(*[float(x) for x in value])
    if isinstance(value, str) and value.startswith("/"):
        obj = load(value)
        if obj is None:
            raise OpError(f"{prop}: no asset {value!r}", code="not_found", hint="list assets with assets.list")
        return obj
    if isinstance(current, bool) or isinstance(value, bool):
        return bool(value)
    if isinstance(current, float) and isinstance(value, (int, float)):
        return float(value)
    return value


def same(a, b, tol: float = 1e-4) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol * max(1.0, abs(a), abs(b))
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y, tol) for x, y in zip(a, b))
    return a == b


def set_props(obj, props: dict) -> list:
    """Set editor properties, each converted to its engine type; returns the names that changed (a re-run with the
    same values changes nothing)."""
    changed = []
    for k, v in props.items():
        try:
            cur = obj.get_editor_property(k)
        except Exception as e:  # noqa: BLE001 (the engine raises for an unknown property)
            raise OpError(f"{type(obj).__name__} has no property {k!r}: {e}", code="bad_args") from None
        want = coerce(cur, v, k)
        if same(to_json(cur), to_json(want)):
            continue
        try:
            obj.set_editor_property(k, want)
        except Exception as e:  # noqa: BLE001
            raise OpError(f"could not set {type(obj).__name__}.{k} = {v!r}: {e}", code="engine") from None
        changed.append(k)
    return changed


def read_props(obj, names) -> dict:
    out = {}
    for k in names:
        try:
            out[k] = to_json(obj.get_editor_property(k))
        except Exception:  # noqa: BLE001
            out[k] = None
    return out


# ------------------------------------------------------------------------------------------------ blobs in tags

def write_blob(a, key: str, obj) -> None:
    """Keep a small JSON value on an actor, in hex-encoded tags (actor tags are FNames: hex survives any case
    folding), split in chunks that fit an FName."""
    h = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode().hex()
    parts = [h[i:i + 800] for i in range(0, len(h), 800)] or [""]
    tags = [t for t in tags_of(a) if not t.startswith(f"fm_blob_{key}:")]
    tags += [f"fm_blob_{key}:{i:02d}:{p}" for i, p in enumerate(parts)]
    a.set_editor_property("tags", tags)


def read_blob(a, key: str):
    parts = sorted((t.split(":", 2)[1], t.split(":", 2)[2]) for t in tags_of(a) if t.startswith(f"fm_blob_{key}:"))
    if not parts:
        return None
    try:
        return json.loads(bytes.fromhex("".join(p for _, p in parts)).decode())
    except ValueError:
        return None


def world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def console(cmd: str) -> None:
    unreal.SystemLibrary.execute_console_command(world(), cmd)


def cvar(name: str):
    """A console variable's value (float; there is no generic getter, so float covers ints and bools)."""
    try:
        return unreal.SystemLibrary.get_console_variable_float_value(name)
    except Exception:  # noqa: BLE001
        return None
