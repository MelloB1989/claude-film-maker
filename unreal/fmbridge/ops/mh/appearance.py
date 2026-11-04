"""A character's look in MetaHuman Creator, by code: the parametric body (measurement constraints), the face (model
coefficients, preset blends, landmark sculpting), skin, eyes, eyelashes, teeth and makeup. Each op converges: it
writes only what differs and reports `changed`. A body or face change after the cloud rig makes the rig stale
(mh.describe says rig_stale): re-run mh.rig, mh.textures, mh.build."""
from __future__ import annotations

from .. import op
from ...errors import OpError
from ..assets import EAL
from . import _core as K

TEXTURE_RES = {"2k": "RES2K", "4k": "RES4K", "8k": "RES8K", "2048": "RES2K", "4096": "RES4K", "8192": "RES8K"}


# --------------------------------------------------------------------------------------------------------------- body

def _constraints(c):
    return list(K.sub().get_body_constraints(c, True))


@op("mh.body_constraints", mutates=False, idempotent=True)
def body_constraints(*, path: str) -> dict:
    """The parametric body's measurement constraints: each one's current target, whether it is active and its range
    (scaled with the height, as Creator shows them). Measurements are cm; Fat, Muscularity, Masculine/Feminine are
    unitless.

    Returns: {name: {"value", "active", "min", "max"}}.
    Example: film-ue op mh.body_constraints path=/Game/Characters/Ava/MH_Ava
    """
    c = K.char(path)
    return {str(x.name): {"value": round(float(x.target_measurement), 2), "active": bool(x.is_active),
                          "min": round(float(x.min_measurement), 2), "max": round(float(x.max_measurement), 2)}
            for x in _constraints(c)}


@op("mh.body", mutates=True, idempotent=True, tags=["metahuman"])
def body(character: str, measurements: dict | None = None, *, from_character: str = "", reset: bool = False,
         save: bool = True) -> dict:
    """Shape the parametric body by measurements: each named constraint becomes active at that value (None frees it).

    The engine hands the constraints out as copies: they are edited as copies and the whole list goes back in one
    set_body_constraints, then commit_body_state (the operator's 'bodies via constraint copies' lesson). Names are
    Creator's (Height, Chest, Waist, Hip, Across Shoulder, Neck, Bicep, Thigh, ...; mh.body_constraints lists them).
    Args: character: the character asset. measurements: {name: cm or unitless, or None}. from_character: copy every
    active constraint of another character first (its body; then `measurements` on top). reset: free every constraint
    not named. save: save the asset.
    Returns: {"body": {name: value or None}, "changed", "warnings"}. A body change after mh.rig needs a re-rig.
    Example: film-ue op mh.body character=/Game/Characters/Ava/MH_Ava 'measurements={"Height": 168, "Waist": 61}'
    """
    c = K.char(character)
    want = {}
    if from_character:
        src = K.char(from_character)
        want.update({str(x.name): float(x.target_measurement) for x in _constraints(src) if x.is_active})
    want.update(measurements or {})
    cons = _constraints(c)
    names = [str(x.name) for x in cons]
    lower = {n.lower(): n for n in names}
    bad = [k for k in want if k.lower() not in lower]
    if bad:
        raise OpError(f"no body constraint {bad[0]!r}", code="bad_args", candidates=K.closest(bad[0], names),
                      hint="mh.body_constraints lists them: " + ", ".join(names))
    want = {lower[k.lower()]: v for k, v in want.items()}
    new, warnings, changed = [], [], False
    for x in cons:
        y = x.copy()  # the array hands out copies: edit a copy and pass the whole list back
        n = str(y.name)
        if n in want or reset:
            v = want.get(n)
            active = v is not None
            if active:
                v = float(v)
                if v < float(y.min_measurement) or v > float(y.max_measurement):
                    warnings.append(f"{n}={v} is outside {round(float(y.min_measurement), 2)}.."
                                    f"{round(float(y.max_measurement), 2)} for this height; the solver gets as close "
                                    f"as it can")
                if not y.is_active or abs(float(y.target_measurement) - v) > 1e-3:
                    changed = True
                y.target_measurement = v
            elif y.is_active:
                changed = True
            y.is_active = active
        new.append(y)
    if changed:
        K.sub().set_body_constraints(c, new)
        K.sub().commit_body_state(c)
        if save:
            K.save(character)
    got = {str(x.name): (round(float(x.target_measurement), 2) if x.is_active else None)
           for x in _constraints(c) if str(x.name) in want or (reset and x.is_active)}
    return {"body": got, "changed": changed, "warnings": warnings}


# --------------------------------------------------------------------------------------------------------------- face

def face_fingerprint(blend=None, coefficients=None, landmarks=None) -> str:
    """What a face call asks for, canonical (weights normalised, numbers rounded): the tools' planner computes the
    same (tools/filmtools/unreal/mh_spec.py face_fingerprint)."""
    b = None
    if blend:
        total = sum(float(w) for w in blend.values()) or 1.0
        b = {str(k): round(float(w) / total, 6) for k, w in sorted(blend.items())}
    co = [round(float(x), 4) for x in coefficients] if coefficients is not None else None
    lm = {str(int(k)): [round(float(x), 4) for x in v] for k, v in sorted((landmarks or {}).items(),
                                                                          key=lambda kv: int(kv[0]))} or None
    return K.fingerprint({"blend": b, "coefficients": co, "landmarks": lm})


def _coeffs(c) -> list:
    return [float(v) for v in (K.sub().get_face_model_coefficients(c) or [])]


@op("mh.face", mutates=True, idempotent=True, tags=["metahuman", "experimental"])
def face(*, path: str, blend: dict | None = None, coefficients: list | None = None, landmarks: dict | None = None,
         unrig: bool = True, force: bool = False, save: bool = True) -> dict:
    """Shape the face: blend presets or other characters' faces, set the face model's coefficients, or move face
    landmarks (Creator's sculpt points).

    blend mixes the face model coefficients of the sources by weight (normalised to sum 1): Creator's own blend tool
    is not exposed to Python, this is its linear equivalent on the model (experimental: judge the still). landmarks
    moves points by deltas in cm ({index: [dx, dy, dz]}; mh.face_landmarks lists them). A face change on a rigged
    character removes the rig first (`unrig`), as Creator does: re-run mh.rig, mh.textures, mh.build.
    Landmark moves are deltas: what was applied is fingerprinted on the asset (mh.describe face.applied), so the same
    call twice moves them once; `force` applies again.
    Args: path: the character. blend: {preset name or character path: weight}. coefficients: the full list (from
    mh.describe full=true). landmarks: {index: [dx, dy, dz]} cm. unrig: allow removing the rig. force: apply even if
    this exact face was applied last. save: save the asset.
    Returns: {"changed", "coefficients": n, "max_delta", "unrigged"}.
    Example: film-ue op mh.face path=/Game/Characters/Ava/MH_Ava 'blend={"Ada": 0.7, "Vivian": 0.3}'
    """
    from .character import _preset_path
    c = K.char(path)
    sub = K.sub()
    if blend and coefficients:
        raise OpError("give blend or coefficients, not both", code="bad_args")
    fp = face_fingerprint(blend, coefficients, landmarks)
    if not force and K.get_tag(c, "Face") == fp:
        return {"changed": False, "coefficients": len(_coeffs(c)), "max_delta": 0.0, "unrigged": False}
    cur = _coeffs(c)
    target = list(cur)
    if blend:
        total = sum(float(w) for w in blend.values())
        if total <= 0:
            raise OpError("blend weights must sum to more than 0", code="bad_args")
        target = [0.0] * len(cur)
        for src, w in blend.items():
            sp = src if str(src).startswith("/") else _preset_path(str(src))
            sc = _coeffs(K.char(sp))
            if len(sc) != len(cur):
                raise OpError(f"{sp} has {len(sc)} face coefficients, {path} has {len(cur)}: different face models",
                              code="conflict", hint="blend only MetaHuman characters of the same template")
            target = [t + float(w) / total * s for t, s in zip(target, sc)]
    elif coefficients is not None:
        if len(coefficients) != len(cur):
            raise OpError(f"{len(coefficients)} coefficients given, the face model has {len(cur)}", code="bad_args",
                          hint="read them with mh.describe full=true")
        target = [float(v) for v in coefficients]
    delta = max((abs(a - b) for a, b in zip(cur, target)), default=0.0)
    moves = {int(k): v for k, v in (landmarks or {}).items() if any(abs(float(x)) > 1e-6 for x in v)}
    changed = delta > 1e-5 or bool(moves)
    unrigged = False
    if changed:
        if K.rigged(c):
            if not unrig:
                raise OpError(f"{path} is rigged; changing its face drops the rig", code="conflict",
                              hint="pass unrig=true, then mh.rig, mh.textures, mh.build")
            sub.remove_face_rig(c)
            unrigged = True
        if delta > 1e-5:
            sub.set_face_model_coefficients(c, target)
        if moves:
            import unreal
            idx = sorted(moves)
            sub.translate_face_landmarks(c, idx, [unreal.Vector(*[float(x) for x in moves[i]]) for i in idx])
        sub.commit_face_state(c)
    K.set_tag(c, "Face", fp)
    if save:
        K.save(path)
    return {"changed": changed, "coefficients": len(target), "max_delta": round(delta, 6), "unrigged": unrigged}


@op("mh.face_landmarks", mutates=False, idempotent=True)
def face_landmarks(*, path: str) -> dict:
    """The face's landmark positions (Creator's sculpt points), for mh.face landmarks={index: [dx, dy, dz]}.

    Returns: {"count", "landmarks": [[x, y, z] cm, ...]} in the face mesh's space.
    Example: film-ue op mh.face_landmarks path=/Game/Characters/Ava/MH_Ava
    """
    pts = K.sub().get_face_landmarks(K.char(path)) or []
    return {"count": len(pts), "landmarks": [[round(p.x, 3), round(p.y, 3), round(p.z, 3)] for p in pts]}


# ------------------------------------------------------------------------------------- skin, eyes, head model, makeup

def _commit(path: str, prop: str, values: dict, commit, save: bool) -> dict:
    """Write `values` into the character's `prop` settings struct and commit them only when something differs."""
    c = K.char(path)
    cur = c.get_editor_property(prop)
    before = K.plain(cur)
    new = K.update_struct(cur, values, prop)
    after = K.plain(new)
    changed = after != before
    if changed:
        commit(c, new)
        if save:
            K.save(path)
    return {"changed": changed, prop: after}


@op("mh.skin", mutates=True, idempotent=True, tags=["metahuman"])
def skin(character: str, u: float = None, v: float = None, roughness: float = None, *, settings: dict | None = None,
         texture_resolution: str = "", save: bool = True) -> dict:
    """The skin: tone (Creator's palette coordinates u, v), roughness, and any other skin setting (freckles, accents
    by face region, palms, nails, body/face texture variants, the texture resolutions the cloud makes).

    Committing skin settings discards the character's high-resolution textures (the engine's rule), so this commits
    only when something differs; after a change, run mh.textures again before mh.build.
    Args: character: the character. u, v: tone 0..1. roughness: 0.85..1.15. settings: FMetaHumanCharacterSkinSettings
    fields as nested JSON, e.g. {"freckles": {"density": 0.6, "mask": "Type1"}, "accents": {"cheeks": {"redness":
    0.7}}, "skin": {"face_texture_index": 1}}. texture_resolution: 2k|4k|8k for every texture mh.textures fetches.
    Returns: {"changed", "u", "v", "roughness", "skin_settings": {...}}.
    Example: film-ue op mh.skin character=/Game/Characters/Ava/MH_Ava u=0.55 v=0.45 'settings={"freckles": {"density": 0.3}}'
    """
    vals = {k: x for k, x in (settings or {}).items()}
    tone = {k: x for k, x in (("u", u), ("v", v), ("roughness", roughness)) if x is not None}
    if tone:
        vals.setdefault("skin", {})
        vals["skin"] = {**vals["skin"], **tone}
    if texture_resolution:
        r = TEXTURE_RES.get(str(texture_resolution).lower())
        if not r:
            raise OpError(f"texture_resolution {texture_resolution!r}", code="bad_args", hint="2k, 4k or 8k")
        vals["desired_texture_sources_resolutions"] = {f: r for f in (
            "face_albedo", "face_normal", "face_cavity", "face_animated_maps", "body_albedo", "body_normal",
            "body_cavity", "body_masks")}
    out = _commit(character, "skin_settings", vals, K.sub().commit_skin_settings, save)
    sk = out["skin_settings"].get("skin", {})
    return {"changed": out["changed"], "u": sk.get("u"), "v": sk.get("v"), "roughness": sk.get("roughness"),
            "skin_settings": out["skin_settings"]}


@op("mh.eyes", mutates=True, idempotent=True, tags=["metahuman"])
def eyes(*, path: str, both: dict | None = None, left: dict | None = None, right: dict | None = None,
         save: bool = True) -> dict:
    """The eyes: iris (pattern Iris001..Iris009, colour as palette u/v, blend, limbal ring), pupil, cornea, sclera,
    for both eyes or each.

    Args: path: the character. both/left/right: FMetaHumanCharacterEyeProperties fields as nested JSON, e.g.
    {"iris": {"iris_pattern": "Iris003", "primary_color_u": 0.2, "primary_color_v": 0.6}, "sclera": {"vascularity_intensity": 0.5}}.
    `left`/`right` go over `both`. Returns: {"changed", "eyes_settings"}.
    Example: film-ue op mh.eyes path=/Game/Characters/Ava/MH_Ava 'both={"iris": {"primary_color_u": 0.2}}'
    """
    vals = {}
    for side, own in (("eye_left", left), ("eye_right", right)):
        if both or own:
            vals[side] = _merge(both or {}, own or {})
    return _commit(path, "eyes_settings", vals, K.sub().commit_eyes_settings, save)


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _head(path: str, part: str, values: dict, save: bool) -> dict:
    out = _commit(path, "head_model_settings", {part: values}, K.sub().commit_head_model_settings, save)
    return {"changed": out["changed"], part: out["head_model_settings"].get(part, {})}


@op("mh.eyelashes", mutates=True, idempotent=True, tags=["metahuman"])
def eyelashes(*, path: str, settings: dict, save: bool = True) -> dict:
    """The eyelashes (part of the head model): type (None, ShortSparse, ShortFine, ShortThin, LongSlightCurl,
    LongCurl, LongThickCurl), melanin, redness, lightness, salt-and-pepper, roughness, dye colour, grooms on/off.

    Args: settings: FMetaHumanCharacterEyelashesProperties fields, e.g. {"type": "LongCurl", "melanin": 0.8}.
    Returns: {"changed", "eyelashes"}.
    Example: film-ue op mh.eyelashes path=/Game/Characters/Ava/MH_Ava 'settings={"type": "LongCurl", "melanin": 0.9}'
    """
    return _head(path, "eyelashes", settings, save)


@op("mh.teeth", mutates=True, idempotent=True, tags=["metahuman"])
def teeth(*, path: str, settings: dict, save: bool = True) -> dict:
    """The teeth (part of the head model): length, spacing, upper/lower shift, overbite, overjet, worn down,
    polycanine, receding gums, narrowness, variation (each -1..1 or 0..1), teeth/gum/plaque colours, plaque amount.

    Args: settings: FMetaHumanCharacterTeethProperties fields, e.g. {"tooth_length": 0.2, "teeth_color": [0.9, 0.88, 0.8]}.
    Returns: {"changed", "teeth"}.
    Example: film-ue op mh.teeth path=/Game/Characters/Ava/MH_Ava 'settings={"overbite": 0.3}'
    """
    return _head(path, "teeth", settings, save)


@op("mh.makeup", mutates=True, idempotent=True, tags=["metahuman"])
def makeup(*, path: str, settings: dict, save: bool = True) -> dict:
    """Makeup: foundation (apply, colour, intensity, concealer), eyes (None, ThinLiner, SoftSmokey, FullThinLiner,
    CatEye, PandaSmudge, DramaticSmudge, DoubleMod, ClassicBar), blush (None, Angled, Apple, LowSweep, HighCurve), lips
    (None, Natural, Hollywood, Cupid), each with colours, roughness, opacity.

    Args: settings: FMetaHumanCharacterMakeupSettings fields, e.g. {"lips": {"type": "Natural", "color": [0.3, 0.05,
    0.05]}, "eyes": {"type": "ThinLiner"}}. Returns: {"changed", "makeup_settings"}.
    Example: film-ue op mh.makeup path=/Game/Characters/Ava/MH_Ava 'settings={"lips": {"type": "Natural"}}'
    """
    return _commit(path, "makeup_settings", settings, K.sub().commit_makeup_settings, save)


@op("mh.settings_fields", mutates=False, idempotent=True)
def settings_fields(*, path: str, which: str = "skin") -> dict:
    """The fields (and current values) of one of a character's settings, for writing a spec or an mh.* call.

    Args: which: skin|eyes|makeup|eyelashes|teeth. Returns: the settings as nested JSON with their current values.
    Example: film-ue op mh.settings_fields path=/Game/Characters/Ava/MH_Ava which=makeup
    """
    props = {"skin": "skin_settings", "eyes": "eyes_settings", "makeup": "makeup_settings",
             "eyelashes": "head_model_settings", "teeth": "head_model_settings"}
    if which not in props:
        raise OpError(f"which={which!r}", code="bad_args", candidates=K.closest(which, props), hint=", ".join(props))
    v = K.plain(K.char(path).get_editor_property(props[which]))
    return v.get(which, v) if props[which] == "head_model_settings" else v


__all__ = ["body", "body_constraints", "face", "face_landmarks", "skin", "eyes", "eyelashes", "teeth", "makeup",
           "settings_fields", "EAL"]
