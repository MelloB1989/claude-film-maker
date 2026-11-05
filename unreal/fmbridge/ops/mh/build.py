"""Assembling a character into the Blueprint a level uses (mh.build), checking it can be built, and a live preview
actor that needs no rig or build (mh.preview) for quick stills while shaping a character."""
from __future__ import annotations

import time

import unreal

from .. import op
from ...errors import OpError
from ..assets import EAL, list_assets
from . import _core as K

PIPELINES = ("cinematic", "optimized", "uefn")
QUALITIES = ("low", "medium", "high", "cinematic")


def _why_not(c) -> tuple:
    """Why CanBuildMetaHuman says no (its text is not exposed to Python; the same checks in its order)."""
    if K.rigged(c) is False:
        return "the character is not rigged", "run mh.rig (needs the Epic sign-in)"
    if not c.get_editor_property("has_high_resolution_textures"):
        return "the character has no high-resolution textures", "run mh.textures (after mh.rig)"
    return "a cloud request is still running or the character is not loaded", "wait for mh.rig/mh.textures, retry"


@op("mh.can_build", mutates=False, idempotent=True)
def can_build(*, path: str) -> dict:
    """Whether the character can be assembled now, and if not why and what to run.

    Returns: {"can_build", "why", "hint"}.
    Example: film-ue op mh.can_build path=/Game/Characters/Ava/MH_Ava
    """
    c = K.char(path)
    if K.sub().can_build_meta_human(c, False):
        return {"can_build": True, "why": "", "hint": ""}
    why, hint = _why_not(c)
    return {"can_build": False, "why": why, "hint": hint}


def _find_bp(folder: str, name: str) -> str:
    bps = [p for k, p in list_assets(folder, "Blueprint") if p.endswith(f"/BP_{name}")]
    return bps[0] if bps else ""


@op("mh.build", mutates=True, idempotent=True, tags=["slow", "metahuman"])
def build(character: str, name: str = "", cinematic: bool = True, *, bp_name: str = "", pipeline: str = "",
          quality: str = "",
          build_path: str = "", common_path: str = "", animation_system: str = "", validate_wardrobe: bool = True,
          force: bool = False) -> dict:
    """Assemble the character into a Blueprint (BP_<name>) with its face, body, grooms and outfit: what levels place.

    Skips when the Blueprint exists and nothing that goes into it changed since it was built (`changed: false`);
    `force` rebuilds. The engine call blocks the editor for the whole build (about 3 minutes for a cinematic build on
    an L4) and cannot be split. The character must be rigged (mh.rig) and textured (mh.textures).
    Args: character: the character. name (or bp_name, for callers whose own `name` argument is taken): the
    Blueprint's name (BP_<name>) and unpack folder (default: the character's name without MH_). cinematic: legacy switch (False = optimized/high). pipeline: cinematic|optimized|uefn.
    quality: low|medium|high|cinematic (LOD/detail level; optimized and uefn only, cinematic is always cinematic).
    build_path: an absolute content folder for the built assets (default: the palette's unpack folder next to the
    character, <folder>/Unpacked/<name>). common_path: where shared MetaHuman assets go. animation_system: e.g. AnimBP.
    validate_wardrobe: run the wardrobe item checks. force: rebuild even if up to date.
    Returns: {"bp", "changed", "seconds"}.
    Example: film-ue op mh.build character=/Game/Characters/Ava/MH_Ava name=Ava
    """
    from .character import build_fingerprint, state
    path = K.package(character)
    c = K.char(path)
    name = name or bp_name or path.rsplit("/", 1)[1].removeprefix("MH_")
    pipe = (pipeline or ("cinematic" if cinematic else "optimized")).lower()
    qual = (quality or ("cinematic" if pipe == "cinematic" else "high")).lower()
    if pipe not in PIPELINES:
        raise OpError(f"pipeline {pipeline!r}", code="bad_args", candidates=K.closest(pipe, PIPELINES),
                      hint="|".join(PIPELINES))
    if qual not in QUALITIES:
        raise OpError(f"quality {quality!r}", code="bad_args", candidates=K.closest(qual, QUALITIES),
                      hint="|".join(QUALITIES))
    opts = {"name": name, "pipeline": pipe, "quality": qual, "build_path": build_path, "common_path": common_path,
            "animation_system": animation_system}
    fp, ofp = build_fingerprint(state(c, path)), K.fingerprint(opts)
    old = K.get_tag(c, "BuildBP")
    if (not force and old and EAL.does_asset_exist(old) and K.get_tag(c, "Build") == fp
            and K.get_tag(c, "BuildOpts") == ofp):
        return {"bp": old, "changed": False, "seconds": 0.0}
    if not K.sub().can_build_meta_human(c, False):
        why, hint = _why_not(c)
        raise OpError(f"{path} cannot be built: {why}", code="conflict", hint=hint)
    p = unreal.MetaHumanCharacterEditorBuildParameters()
    p.set_editor_property("name_override", name)
    p.set_editor_property("pipeline_type", K.enum(unreal.MetaHumanDefaultPipelineType, pipe))
    p.set_editor_property("pipeline_quality", K.enum(unreal.MetaHumanQualityLevel, qual))
    if build_path:
        p.set_editor_property("absolute_build_path", build_path)
    if common_path:
        p.set_editor_property("common_folder_path", common_path)
    if animation_system:
        p.set_editor_property("animation_system_name", animation_system)
    p.set_editor_property("enable_wardrobe_item_validation", bool(validate_wardrobe))
    t0 = time.time()
    K.sub().build_meta_human(c, p)
    seconds = round(time.time() - t0, 1)
    bp = _find_bp(build_path or K.folder_of(path), name) or (_find_bp("/Game", name) if not build_path else "")
    # (without build_path the palette's unpack folder decides where it lands: usually <character folder>/Unpacked)
    if not bp:  # the subsystem logs why (LogMetaHumanCharacterEditor) and returns nothing
        raise OpError(f"no BP_{name} after building {path}", code="engine",
                      hint="see the editor log (LogMetaHumanCharacterEditor): 'not ready for assembly' or a pipeline error")
    K.set_tag(c, "Build", fp)
    K.set_tag(c, "BuildOpts", ofp)
    K.set_tag(c, "BuildBP", bp)
    K.save(path)
    return {"bp": bp, "changed": True, "seconds": seconds}


_PREVIEWS = {}  # label -> the preview actor mh.preview spawned (live it is not listed by get_all_level_actors)


def _live(a):
    """`a` if it is still a live actor in the editor world, else None."""
    if a is None:
        return None
    try:
        return a if a.get_world() is not None and not a.is_actor_being_destroyed() else None
    except Exception:  # destroyed: the Python wrapper's UObject is gone
        return None


@op("mh.preview", mutates=True, idempotent=True, tags=["metahuman"])
def preview(*, path: str, label: str = "", loc: list = (0, 0, 0), yaw_deg: float = 0.0,
            transient: bool = True) -> dict:
    """A live MetaHuman Editor actor of the character in the open level, with no rig and no build: it follows
    changes made to the character (body, face, skin, wardrobe), for stills while shaping one.

    Re-running with the same label moves the existing one. Args: label: the actor label (default MHPreview_<name>).
    loc: [x, y, z] cm. yaw_deg: facing. transient: not saved with the level.
    Returns: {"label", "changed"}.
    Example: film-ue op mh.preview path=/Game/Characters/Ava/MH_Ava 'loc=[0,0,0]'
    """
    from ..level import actor
    path = K.package(path)
    c = K.char(path)
    label = label or f"MHPreview_{path.rsplit('/', 1)[1]}"
    try:
        a = actor(label)
    except ValueError:
        a = _live(_PREVIEWS.get(label))  # day 1: the spawned preview is not among the level actors live
    changed = a is None
    if changed:
        a = K.sub().spawn_meta_human_actor(c, bool(transient))
        if a is None:
            raise OpError(f"could not spawn a preview of {path}", code="engine", hint="see LogMetaHumanCharacterEditor")
        a.set_actor_label(label)
        _PREVIEWS[label] = a
        changed = True
    a.set_actor_location_and_rotation(unreal.Vector(*[float(x) for x in loc]),
                                      unreal.Rotator(roll=0.0, pitch=0.0, yaw=float(yaw_deg)), False, False)
    return {"label": label, "changed": changed}
