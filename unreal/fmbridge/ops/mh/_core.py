"""Shared helpers for the mh.* ops (not ops themselves): the MetaHuman Character editor subsystem, opening a character
for editing, engine enums and structs to and from plain JSON, the convergence fingerprints kept on the character asset,
and reading the editor log for the cloud services' outcome.

Every engine name used here is checked against the UE 5.8.4 source: docs/unreal/metahuman.md, API_NOTES.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys

import unreal

from ...errors import OpError, closest, not_found
from ..assets import EAL, list_assets

PRESETS = "/MetaHumanCharacter/Optional/Presets"
OPTIONAL = "/MetaHumanCharacter/Optional"
GROOMS = "/MetaHumanCharacter/Optional/Grooms/Bindings"
# the wardrobe slots of the default MetaHuman collection pipeline (MetaHumanCharacterPipelineSpecification): the
# grooms and the outfit; the names are what the palette's get_slot_names() returns
GROOM_SLOTS = ("Hair", "Eyebrows", "Beard", "Mustache", "Eyelashes", "Peachfuzz")
TAG = "FM.MH."  # metadata tags on the character asset: FM.MH.<what> = fingerprint (see fingerprint())


# --------------------------------------------------------------------------------------------------- subsystem, assets

def sub():
    """UMetaHumanCharacterEditorSubsystem (MetaHumanCharacterEditorSubsystem.h:479): every Character edit goes here."""
    return unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)


def package(path: str) -> str:
    """'/Game/A/B.B' or '/Game/A/B' -> '/Game/A/B'."""
    path = str(path or "").strip()
    if "." in path.rsplit("/", 1)[-1]:
        path = path.rsplit(".", 1)[0]
    return path


def folder_of(path: str) -> str:
    return package(path).rsplit("/", 1)[0]


def characters(folder: str = "/Game") -> list:
    """Character asset paths under a folder (class MetaHumanCharacter)."""
    return [p for c, p in list_assets(folder, "MetaHumanCharacter")]


def char(path: str, edit: bool = True):
    """The UMetaHumanCharacter at `path`, registered for editing (TryAddObjectToEdit: most subsystem calls need it).
    Raises not_found with the characters nearby."""
    path = package(path)
    if not path.startswith("/"):
        raise OpError(f"character path {path!r} is not a content path", code="bad_args",
                      hint="pass the asset's package path, e.g. /Game/Characters/Ava/MH_Ava")
    c = EAL.load_asset(path) if EAL.does_asset_exist(path) else None
    if c is None:
        near = []
        try:
            near = characters(folder_of(path)) or characters("/Game")
        except Exception:
            pass
        raise not_found("MetaHuman character", path, near, hint="create one with mh.add (from a preset: mh.presets)")
    if edit and not sub().is_object_added_for_editing(c):
        if not sub().try_add_object_to_edit(c):
            raise OpError(f"the MetaHuman editor subsystem refused to open {path} for editing", code="engine",
                          hint="is it a MetaHumanCharacter asset? see the editor log (LogMetaHumanCharacterEditor)")
    return c


def save(path_or_obj) -> None:
    p = path_or_obj if isinstance(path_or_obj, str) else path_or_obj.get_path_name()
    EAL.save_asset(package(p), only_if_is_dirty=False)


# ------------------------------------------------------------------------------------------------------------- names

def snake(name: str) -> str:
    """'TargetMeasurement' -> 'target_measurement', 'bShowTopUnderwear' -> 'show_top_underwear' (the Python names of
    reflected properties), 'Iris001' -> 'iris001'; already snake_case passes through."""
    name = str(name)
    if re.fullmatch(r"b[A-Z]\w*", name):
        name = name[1:]
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
    return s.lower()


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def enum_names(cls) -> list:
    """The member names of an engine enum class (unreal.EMetaHuman... in Python: ALL_CAPS attributes)."""
    out = []
    for n in dir(cls):
        if n.startswith("_") or not re.fullmatch(r"[A-Z][A-Z0-9_]*", n):
            continue
        out.append(n)
    return out


def enum(cls, value):
    """An engine enum value from a friendly name: 'LongCurl', 'LONG_CURL', 'long curl' or an engine value. Raises
    bad_args listing the valid names."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    want = _norm(value)
    names = enum_names(cls)
    for n in names:
        if _norm(n) == want:
            return getattr(cls, n)
    guess = snake(value.replace(" ", "")).upper()
    if not names and re.fullmatch(r"[A-Z][A-Z0-9_]*", guess):  # an enum we cannot list (the fake engine)
        return getattr(cls, guess)
    raise OpError(f"{value!r} is not a {getattr(cls, '__name__', cls)}", code="bad_args",
                  candidates=closest(value, names) or names[:12], hint="one of: " + ", ".join(names))


def enum_name(v) -> str:
    """An engine enum value as its name ('LONG_CURL')."""
    n = getattr(v, "name", None)
    return str(n) if n is not None else str(v).rsplit(".", 1)[-1]


# ------------------------------------------------------------------------------------------- structs <-> plain values

def is_struct(v) -> bool:
    sb = getattr(unreal, "StructBase", None)
    if isinstance(sb, type) and isinstance(v, sb):
        return True
    return hasattr(v, "get_editor_property") and hasattr(v, "set_editor_property") and not is_object(v)


def is_object(v) -> bool:
    ob = getattr(unreal, "Object", None)
    return isinstance(ob, type) and isinstance(v, ob)


def is_enum(v) -> bool:
    eb = getattr(unreal, "EnumBase", None)
    if isinstance(eb, type) and isinstance(v, eb):
        return True
    return type(v).__name__ == "EnumValue"


def is_vec(v) -> bool:
    """A Vector/Vector3f value (a struct whose only fields are x, y, z)."""
    if not all(hasattr(v, k) for k in ("x", "y", "z")) or is_object(v):
        return False
    try:
        return set(fields(v)) <= {"x", "y", "z"}
    except Exception:
        return True


def fields(struct) -> list:
    """The property names of an engine struct value (its Python attributes that are not methods)."""
    fn = getattr(struct, "_fm_fields", None)  # the fake engine's structs list theirs
    if callable(fn):
        return list(fn())
    out = []
    for n in dir(struct):
        if n.startswith("_") or re.fullmatch(r"[A-Z][A-Z0-9_]*", n):  # constants (Vector.ZERO) are not fields
            continue
        try:
            v = getattr(struct, n)
        except Exception:
            continue
        if callable(v) and not is_struct(v):
            continue
        out.append(n)
    return out


def plain(v, depth: int = 6):
    """An engine value as JSON: structs as dicts of their fields, enums by name, colours/vectors as lists, objects by
    package path, arrays and maps as lists and dicts."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return round(v, 6)
    if is_enum(v):
        return enum_name(v)
    if hasattr(v, "r") and hasattr(v, "g") and hasattr(v, "b") and hasattr(v, "a"):
        return [round(float(v.r), 6), round(float(v.g), 6), round(float(v.b), 6), round(float(v.a), 6)]
    if is_vec(v):
        return [round(float(v.x), 6), round(float(v.y), 6), round(float(v.z), 6)]
    if is_object(v):
        return package(v.get_path_name())
    if is_struct(v):
        if depth <= 0:
            return "..."
        return {f: plain(getattr(v, f), depth - 1) for f in fields(v)}
    if isinstance(v, dict) or hasattr(v, "items"):
        try:
            return {str(plain(k, 1)): plain(x, depth - 1) for k, x in v.items()}
        except Exception:
            pass
    if isinstance(v, (list, tuple)) or hasattr(v, "__iter__"):
        try:
            return [plain(x, depth - 1) for x in v]
        except Exception:
            pass
    return str(v)


def _coerce(cur, val, where: str):
    """`val` (JSON) converted to the type of the current engine value `cur`."""
    if is_enum(cur):
        return enum(type(cur), val)
    if hasattr(cur, "r") and hasattr(cur, "a"):
        if not isinstance(val, (list, tuple)) or len(val) not in (3, 4):
            raise OpError(f"{where}: a colour is [r, g, b] or [r, g, b, a] linear 0..1, not {val!r}", code="bad_args")
        r, g, b = (float(x) for x in val[:3])
        return unreal.LinearColor(r=r, g=g, b=b, a=float(val[3]) if len(val) == 4 else 1.0)
    if is_vec(cur):
        return type(cur)(*[float(x) for x in val])
    if isinstance(cur, bool):
        return bool(val)
    if isinstance(cur, int) and not isinstance(val, bool):
        return int(val)
    if isinstance(cur, float):
        return float(val)
    return val


def update_struct(struct, values: dict, where: str = ""):
    """Write `values` ({field: value}, nested dicts for nested structs; CamelCase or snake_case names) into an engine
    struct and return it. Engine structs come back from properties as copies, so nested structs are written back to
    their parent. Unknown fields raise bad_args with the valid names."""
    if not isinstance(values, dict):
        raise OpError(f"{where or 'settings'}: expected an object of fields, got {values!r}", code="bad_args")
    have = fields(struct)
    for k, val in values.items():
        name = snake(k)
        if name not in have:
            raise OpError(f"{where + '.' if where else ''}{k} is not a field", code="bad_args",
                          candidates=closest(name, have), hint="fields: " + ", ".join(sorted(have)))
        cur = getattr(struct, name)
        here = f"{where}.{name}" if where else name
        if isinstance(val, dict) and is_struct(cur):
            val = update_struct(cur, val, here)
        elif val is not None:
            val = _coerce(cur, val, here)
        struct.set_editor_property(name, val)
    return struct


def clamp_note(struct_name: str, field: str, value: float, lo: float, hi: float) -> str | None:
    if value < lo or value > hi:
        return f"{struct_name}.{field}={value} is outside the engine's range {lo}..{hi}; the engine clamps it"
    return None


# --------------------------------------------------------------------------------------------- fingerprints (state)

def fingerprint(obj) -> str:
    """A short stable hash of a JSON-able value: what was applied, kept on the asset so a re-run can tell 'unchanged'."""
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def get_tag(c, name: str) -> str:
    try:
        return str(EAL.get_metadata_tag(c, TAG + name) or "")
    except Exception:
        return ""


def set_tag(c, name: str, value: str) -> None:
    EAL.set_metadata_tag(c, TAG + name, str(value))


def rig_inputs(c) -> dict:
    """What the cloud rig is fitted to: the face model coefficients and the active body constraints. A change in
    either after a rig makes the rig stale (re-rig, re-texture, rebuild)."""
    try:
        coeffs = [round(float(x), 4) for x in (sub().get_face_model_coefficients(c) or [])]
    except Exception:
        coeffs = []
    body = {}
    try:
        for x in sub().get_body_constraints(c, False):
            if x.is_active:
                body[str(x.name)] = round(float(x.target_measurement), 2)
    except Exception:
        pass
    return {"face": fingerprint(coeffs), "body": body}


def rigged(c) -> bool | None:
    """Whether the character has a face rig (DNA). The engine's own test (UMetaHumanCharacter::HasFaceDNA,
    GetRiggingState) is not exposed to Python, so: True if it could be built (CanBuildMetaHuman checks the rig), or if
    the face DNA carries blend shapes (a full rig); None when neither tells (a joints-only rig without textures)."""
    try:
        if sub().can_build_meta_human(c, False):
            return True
    except Exception:
        pass
    try:
        if c.get_editor_property("has_face_dna_blendshapes"):
            return True
    except Exception:
        pass
    return False if not get_tag(c, "Rig") else None


# ------------------------------------------------------------------------------------------------- the editor's log

def log_path() -> str:
    """The running editor's log file (the newest .log in the project's log dir)."""
    d = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_log_dir())
    logs = [p for p in glob.glob(os.path.join(d, "*.log")) if "backup" not in os.path.basename(p).lower()]
    return max(logs, key=os.path.getmtime) if logs else ""


class LogWatch:
    """Lines the editor writes to its log after this point (for the cloud requests' outcomes, which the engine
    reports only as notifications and log lines)."""

    def __init__(self):
        self.path = log_path()
        try:
            self.pos = os.path.getsize(self.path) if self.path else 0
        except OSError:
            self.pos = 0

    def new(self) -> list:
        if not self.path:
            return []
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read()
                self.pos = f.tell()
        except OSError:
            return []
        return data.decode("utf-8", "replace").splitlines()


def find(lines: list, patterns) -> str | None:
    for ln in lines:
        for p in patterns:
            if re.search(p, ln):
                return ln.strip()
    return None


# ------------------------------------------------------------------------------------------------ Epic sign-in state

def eos_credentials() -> list:
    """The EOS SDK's saved sign-ins on this machine (Linux: one file per client under
    ~/.local/share/.eos_sdk/keychain/<client>/persistent_auth/credential; docs/linux/engine.md P10)."""
    return glob.glob(os.path.expanduser("~/.local/share/.eos_sdk/keychain/*/persistent_auth/credential"))


def signed_in() -> bool | None:
    """Whether the MetaHuman cloud services can sign in without asking: True/False on Linux (the EOS persistent
    credential), None on Windows (kept in the Windows credential store; we cannot tell, assume yes)."""
    if sys.platform == "win32":
        return None
    return bool(eos_credentials())
