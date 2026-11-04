"""MetaHuman characters as assets: the presets, making one (from a preset, blank, or a copy), variants, describing it
as JSON (what the `character` spec planner diffs against) and removing it."""
from __future__ import annotations

import unreal

from .. import op
from ...errors import OpError, not_found
from ..assets import EAL, free, list_assets
from . import _core as K


@op("mh.presets", mutates=False, idempotent=True)
def presets() -> list:
    """The preset characters MetaHuman Creator ships (needs the engine's Creator Core Data).

    Returns: preset names, e.g. ["Ada", "Jorge", ...], for mh.add preset=<name>.
    Example: film-ue op mh.presets
    """
    return [p.rsplit("/", 1)[1] for c, p in list_assets(K.PRESETS, "MetaHumanCharacter")]


def _preset_path(preset: str) -> str:
    if preset.startswith("/"):
        return K.package(preset)
    names = presets()
    for n in names:
        if n.lower() == preset.lower():
            return f"{K.PRESETS}/{n}"
    raise not_found("MetaHuman preset", preset, names, hint="list them with mh.presets")


@op("mh.from_preset", mutates=True, idempotent=True)
def from_preset(preset: str, dest: str, overwrite: bool = False) -> str:
    """A new character asset copied from a preset (e.g. 'Trey'), opened for editing (legacy form of mh.add).

    Args: preset: a name from mh.presets (or a character path to copy). dest: the new asset's path. overwrite: replace
    what is at dest. Returns: dest.
    Example: film-ue op mh.from_preset preset=Ada dest=/Game/Characters/Ava/MH_Ava
    """
    return add(path=dest, preset=preset, overwrite=overwrite)["path"]


@op("mh.add", mutates=True, idempotent=True, tags=["metahuman"])
def add(*, path: str, preset: str = "", source: str = "", blank: bool = False, overwrite: bool = False,
        save: bool = True) -> dict:
    """Make a MetaHuman character asset (or keep the one at `path`): copied from a preset, from another character,
    or blank (Creator's default head and body), and opened for editing.

    Re-running with the same path changes nothing (`changed: false`) unless `overwrite`. Exactly one of preset, source
    or blank says where it starts; with none, an existing asset is kept and a missing one is an error.
    Args: path: the asset (/Game/Characters/Ava/MH_Ava). preset: a name from mh.presets. source: a character to copy
    (variants: mh.duplicate). blank: start from Creator's template. overwrite: replace an existing asset.
    Returns: {"path", "changed", "from"}.
    Example: film-ue op mh.add path=/Game/Characters/Ava/MH_Ava preset=Ada
    """
    path = K.package(path)
    starts = [x for x in (preset, source, "blank" if blank else "") if x]
    if len(starts) > 1:
        raise OpError("give one of preset, source or blank", code="bad_args")
    exists = EAL.does_asset_exist(path)
    if exists and not overwrite:
        K.char(path)
        return {"path": path, "changed": False, "from": "existing"}
    if not starts:
        raise OpError(f"no character at {path} and nothing to make it from", code="not_found",
                      hint="pass preset=<name> (mh.presets), source=<character> or blank=true")
    src = _preset_path(preset) if preset else K.package(source) if source else ""
    if src and not EAL.does_asset_exist(src):
        raise not_found("character", src, K.characters(K.folder_of(src)), hint="mh.presets lists the presets")
    if exists:
        sub = K.sub()
        old = EAL.load_asset(path)
        if old is not None and sub.is_object_added_for_editing(old):
            sub.remove_object_to_edit(old)
        free(path)
    if src:
        if EAL.duplicate_asset(src, path) is None:
            raise OpError(f"could not copy {src} to {path}", code="engine", hint="is the folder writable?")
    else:
        name, folder = path.rsplit("/", 1)[1], K.folder_of(path)
        made = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, folder, unreal.MetaHumanCharacter, unreal.MetaHumanCharacterFactoryNew())
        if made is None:
            raise OpError(f"could not create a blank character at {path}", code="engine",
                          hint="is the MetaHumanCharacter plugin enabled? see LogMetaHumanCharacterEditor")
    c = K.char(path)
    for t in ("Rig", "Build", "BuildOpts", "BuildBP"):  # (Face stays: it describes the copied face)
        K.set_tag(c, t, "")  # a copy carries its source's fingerprints; it has not been rigged/built as itself
    if save:
        K.save(path)
    return {"path": path, "changed": True, "from": src or "blank"}


@op("mh.duplicate", mutates=True, idempotent=True, tags=["metahuman"])
def duplicate(*, source: str, path: str, overwrite: bool = False) -> dict:
    """A variant: a copy of a character (body, face, skin, wardrobe, rig and textures) to edit on its own.

    Args: source: the character to copy. path: the new asset. overwrite: replace what is there.
    Returns: {"path", "changed", "from"}. Rig/build fingerprints are reset, so the variant is rebuilt as itself.
    Example: film-ue op mh.duplicate source=/Game/Characters/Ava/MH_Ava path=/Game/Characters/Ava/MH_Ava_Old
    """
    return add(path=path, source=source, overwrite=overwrite)


@op("mh.remove", mutates=True, idempotent=True)
def remove(*, path: str, built: bool = False) -> dict:
    """Delete a character asset (and with `built`, the Blueprint mh.build made from it). Removing nothing is fine.

    Returns: {"removed": [paths], "changed"}.
    Example: film-ue op mh.remove path=/Game/_Selftest/mh/MH_Scratch built=true
    """
    path = K.package(path)
    gone = []
    if EAL.does_asset_exist(path):
        c = EAL.load_asset(path)
        bp = K.get_tag(c, "BuildBP") if built else ""
        if K.sub().is_object_added_for_editing(c):
            K.sub().remove_object_to_edit(c)
        free(path)
        gone.append(path)
        if bp and EAL.does_asset_exist(bp):
            free(bp)
            gone.append(bp)
    return {"removed": gone, "changed": bool(gone)}


def _wardrobe_state(c) -> dict:
    from .wardrobe import selections
    try:
        return selections(c, params=True)
    except Exception as e:  # the wardrobe is optional state: describe the rest
        return {"error": str(e)}


def state(c, path: str, full: bool = False) -> dict:
    """The character as plain JSON (see describe)."""
    sub = K.sub()
    s = {"path": path, "exists": True}
    s["rigged"] = K.rigged(c)
    s["has_high_res_textures"] = bool(c.get_editor_property("has_high_resolution_textures"))
    try:
        s["can_build"] = bool(sub.can_build_meta_human(c, False))
    except Exception:
        s["can_build"] = None
    s["fixed_body_type"] = bool(c.get_editor_property("fixed_body_type"))
    cons = sub.get_body_constraints(c, True)
    s["body"] = {str(x.name): round(float(x.target_measurement), 2) for x in cons if x.is_active}
    if full:
        s["body_ranges"] = {str(x.name): [round(float(x.min_measurement), 2), round(float(x.max_measurement), 2)]
                            for x in cons}
    inputs = K.rig_inputs(c)
    s["face"] = {"fingerprint": inputs["face"], "applied": K.get_tag(c, "Face")}
    if full:
        try:
            s["face"]["coefficients"] = [round(float(v), 5) for v in sub.get_face_model_coefficients(c)]
        except Exception:
            pass
    s["skin"] = K.plain(c.get_editor_property("skin_settings"))
    for k in ("texture_overrides", "texture_material_overrides"):
        if not full:
            s["skin"].pop(k, None)
    s["eyes"] = K.plain(c.get_editor_property("eyes_settings"))
    s["makeup"] = K.plain(c.get_editor_property("makeup_settings"))
    head = K.plain(c.get_editor_property("head_model_settings"))
    s["eyelashes"], s["teeth"] = head.get("eyelashes", {}), head.get("teeth", {})
    s["wardrobe"] = _wardrobe_state(c)
    rig_fp = K.get_tag(c, "Rig")
    s["rig_fingerprint"] = rig_fp
    s["rig_stale"] = bool(rig_fp) and rig_fp.split(":", 1)[-1] != K.fingerprint(inputs)  # tag is "<kind>:<fp>"
    bp = K.get_tag(c, "BuildBP")
    s["build"] = {"bp": bp if bp and EAL.does_asset_exist(bp) else "", "fingerprint": K.get_tag(c, "Build"),
                  "current": build_fingerprint(s)}
    s["build"]["stale"] = not s["build"]["bp"] or s["build"]["fingerprint"] != s["build"]["current"]
    s["signed_in"] = K.signed_in()
    return s


def build_fingerprint(s: dict) -> str:
    """What a build is made from: the rig inputs, skin, eyes, makeup, head model and wardrobe as described."""
    return K.fingerprint({k: s.get(k) for k in ("body", "face", "skin", "eyes", "makeup", "eyelashes", "teeth",
                                                 "wardrobe")})


@op("mh.describe", mutates=False, idempotent=True, tags=["metahuman"])
def describe(*, path: str, full: bool = False) -> dict:
    """A character's whole state as JSON: what the `character` spec planner diffs against.

    Args: path: the character asset. full: also the body constraints' ranges, the face model coefficients and the
    skin's texture overrides.
    Returns: {"path", "exists", "rigged", "rig_stale", "has_high_res_textures", "can_build", "body": {constraint: cm},
    "face": {"fingerprint"}, "skin", "eyes", "makeup", "eyelashes", "teeth" (engine settings by field),
    "wardrobe": {slot: {"item", "params"}}, "build": {"bp", "stale"}, "signed_in"}; {"path", "exists": false} when
    there is none.
    Example: film-ue op mh.describe path=/Game/Characters/Ava/MH_Ava
    """
    path = K.package(path)
    if not EAL.does_asset_exist(path):
        return {"path": path, "exists": False}
    return state(K.char(path), path, full)


@op("mh.find", mutates=False, idempotent=True)
def find(*, folder: str = "/Game") -> list:
    """The MetaHuman character assets under a folder, with whether each is rigged/textured and its built Blueprint.

    Returns: [{"path", "rigged", "has_high_res_textures", "bp"}].
    Example: film-ue op mh.find folder=/Game/Characters
    """
    out = []
    for p in K.characters(folder):
        c = EAL.load_asset(p)
        if c is None:
            continue
        out.append({"path": p, "rigged": bool(c.get_editor_property("has_face_dna_blendshapes")) or None,
                    "has_high_res_textures": bool(c.get_editor_property("has_high_resolution_textures")),
                    "bp": K.get_tag(c, "BuildBP")})
    return out
