"""Lights by spec: one light that converges (light.add), rigs relative to a subject and camera with intensities from
target lux and ratios (light.rig), practical fixtures by type (light.practical), the lights' state as numbers
(light.describe), what they give at a point with no render (light.measure), lighting channels and removal.

Intensities are physical: candelas for rect/spot/point lights (the ops set ELightUnits Candelas), lux for directional.
Colours are linear [r, g, b]; give `temperature_k` instead for a black-body colour. docs/unreal/environment.md.
"""
from __future__ import annotations

import math

import unreal

from . import op
from . import _envutil as U
from ..envlib import lights as LL
from ..envlib import photometry as ph
from ..envlib import rig as R
from ..errors import OpError, not_found


def _light_component(a):
    for cls in ("RectLightComponent", "SpotLightComponent", "PointLightComponent", "DirectionalLightComponent"):
        c = a.get_component_by_class(getattr(unreal, cls))
        if c is not None:
            return c, {"RectLightComponent": "rect", "SpotLightComponent": "spot", "PointLightComponent": "point",
                       "DirectionalLightComponent": "directional"}[cls]
    return None, None


def _candelas(c, kind: str) -> float:
    """The light's intensity in candelas whatever its unit (LocalLightComponent.cpp GetUnitsConversionFactor)."""
    v = float(c.get_editor_property("intensity"))
    units = U.to_json(c.get_editor_property("intensity_units"))
    u = str(units).rsplit(".", 1)[-1].upper() if units else "CANDELAS"
    if u == "UNITLESS":
        return v / 625.0  # 100 * 100 / 16
    if u == "LUMENS":
        cone = float(c.get_editor_property("outer_cone_angle")) if kind == "spot" else 44.0
        return ph.lumens_to_candelas(v, kind, cone)
    if u == "EV":
        return ph.ue_light_ev_to_nits(v)
    return v


def read(a) -> dict:
    """A light actor in the canonical form (envlib/lights.py) plus owner, role and rig."""
    c, kind = _light_component(a)
    p = a.get_actor_location()
    out = {"label": a.get_actor_label(), "kind": kind, "loc": [round(p.x, 3), round(p.y, 3), round(p.z, 3)],
           "rotation": U.rot_json(a.get_actor_rotation())}
    if kind == "directional":
        out["intensity_lux"] = round(float(c.get_editor_property("intensity")), 6)
    else:
        out["intensity_cd"] = round(_candelas(c, kind), 6)
    if bool(c.get_editor_property("use_temperature")):
        out["temperature_k"] = round(float(c.get_editor_property("temperature")), 3)
    else:
        out["temperature_k"] = None
        out["color"] = U.to_json(c.get_editor_property("light_color"))
    for k, prop in LL.PROPS.items():
        if k in ("intensity_cd", "intensity_lux", "temperature_k") or kind not in LL.ONLY.get(k, {kind}):
            continue
        try:
            v = U.to_json(c.get_editor_property(prop))
        except Exception:  # noqa: BLE001
            continue
        out[k] = v
    out["channels"] = U.to_json(c.get_editor_property("lighting_channels"))
    out["owner"] = U.owner_of(a)
    out["role"] = U.tag_value(a, "fm_role")
    out["rig"] = U.tag_value(a, "fm_rig")
    out["forward"] = [round(x, 6) for x in LL.forward(out["rotation"])]
    return out


def _write(canon: dict, owner: str, role: str = "", extra_tags: dict = None) -> dict:
    a, created = U.ensure(canon["label"], LL.KINDS[canon["kind"]], owner, role, canon["loc"], canon.get("rotation"))
    changed = U.place(a, canon["loc"], canon.get("rotation")) or created
    c = U.component(a, LL.COMPONENT[canon["kind"]])
    props = {}
    if canon["kind"] != "directional":
        props["intensity_units"] = "LightUnits.CANDELAS"
    props["intensity"] = canon.get("intensity_cd", canon.get("intensity_lux"))
    if canon.get("temperature_k") is None and canon.get("color") is not None:
        props["use_temperature"] = False
    else:
        props["use_temperature"] = True
        props["temperature"] = canon["temperature_k"]
    for k, prop in LL.PROPS.items():
        if k in canon and k not in ("intensity_cd", "intensity_lux", "temperature_k"):
            props[prop] = canon[k]
    if "channels" in canon:
        props["lighting_channels"] = canon["channels"]
    changed_props = U.set_props(c, props)
    if canon.get("temperature_k") is None and canon.get("color") is not None:
        want = U.color_linear_to_fcolor(canon["color"])
        if not U.same(U.to_json(c.get_editor_property("light_color")), U.to_json(want), 1e-3):
            c.set_light_color(unreal.LinearColor(r=canon["color"][0], g=canon["color"][1], b=canon["color"][2], a=1.0), True)
            changed_props.append("light_color")
    elif "light_color" not in changed_props:  # a temperature light keeps a white filter colour
        white = U.color_linear_to_fcolor([1, 1, 1])
        if not U.same(U.to_json(c.get_editor_property("light_color")), U.to_json(white), 1e-3):
            c.set_editor_property("light_color", white)
            changed_props.append("light_color")
    if extra_tags:
        U.set_tags(a, extra_tags)
    if role:
        U.set_tags(a, {"fm_role": role})
    return {"label": canon["label"], "changed": bool(changed or changed_props), "created": created,
            "props": changed_props}


@op("light.add", mutates=True, idempotent=True, tags=["lighting"])
def add(*, label: str, kind: str = "rect", loc: list = (0, 0, 200), look_at: list = None, rotation: dict = None,
        intensity_cd: float = None, intensity_lux: float = None, lux: float = None, at: list = None,
        lumens: float = None, nits: float = None, temperature_k: float = None, color: list = None,
        width_cm: float = None, height_cm: float = None, barn_door_deg: float = None, barn_door_length_cm: float = None,
        cone_deg: float = None, inner_cone_deg: float = None, source_radius_cm: float = None,
        soft_radius_cm: float = None, source_length_cm: float = None, radius_cm: float = None,
        shadows: bool = None, channels: list = None, ies: str = None, ies_brightness: bool = None,
        specular: float = None, volumetric: float = None, indirect: float = None, diffuse: float = None,
        softness_deg: float = None, role: str = "", owner: str = "manual") -> dict:
    """Make or converge one light named `label` (re-running retunes the same light; changing `kind` remakes it).

    Args: kind: rect|spot|point|directional. loc: [x,y,z] cm. look_at: [x,y,z] to aim at (or rotation
    {"pitch","yaw","roll"}). Intensity, one of: intensity_cd (candela), lux + at (lux at that point, inverse
    square; `at` defaults to look_at), lumens, nits (rect: surface luminance x area), intensity_lux (directional).
    temperature_k (kelvin, default 6500) or color [r,g,b] linear. width_cm/height_cm (rect), cone_deg/inner_cone_deg
    (spot half-angles), source_radius_cm (soft shadows), radius_cm (attenuation; auto from intensity), shadows,
    channels [0..2], ies (a TextureLightProfile path), specular/volumetric/indirect/diffuse scales.
    Returns: {"label", "changed", "created", "props": [changed engine properties], "light": canonical}.
    Example: film-ue op light.add label=Key kind=rect 'loc=[150,120,230]' 'look_at=[0,0,165]' lux=800 temperature_k=5600
    """
    spec = {k: v for k, v in dict(kind=kind, loc=loc, look_at=look_at, rotation=rotation, intensity_cd=intensity_cd,
                                  intensity_lux=intensity_lux, lux=lux, at=at, lumens=lumens, nits=nits,
                                  temperature_k=temperature_k, color=color, width_cm=width_cm, height_cm=height_cm,
                                  barn_door_deg=barn_door_deg, barn_door_length_cm=barn_door_length_cm,
                                  cone_deg=cone_deg, inner_cone_deg=inner_cone_deg, source_radius_cm=source_radius_cm,
                                  soft_radius_cm=soft_radius_cm, source_length_cm=source_length_cm,
                                  radius_cm=radius_cm, shadows=shadows, channels=channels, ies=ies,
                                  ies_brightness=ies_brightness, specular=specular, volumetric=volumetric,
                                  indirect=indirect, diffuse=diffuse, softness_deg=softness_deg).items()
            if v is not None}
    try:
        canon = LL.normalize(spec, label)
    except ValueError as e:
        raise OpError(str(e), code="bad_args", hint="film-ue ops light.add shows what it takes") from None
    if canon.get("ies"):
        if not unreal.EditorAssetLibrary.does_asset_exist(canon["ies"]):
            raise OpError(f"no IES profile {canon['ies']!r}", code="not_found",
                          hint="import the .ies with assets.import (it becomes a TextureLightProfile)")
    res = _write(canon, owner, role)
    res["light"] = canon
    return res


@op("light.practical", mutates=True, idempotent=True, tags=["lighting"])
def practical(*, label: str, type: str, loc: list, look_at: list = None, rotation: dict = None,  # noqa: A002
              lumens: float = None, nits: float = None, intensity_cd: float = None, temperature_k: float = None,
              color: list = None, scale: float = 1.0, width_cm: float = None, height_cm: float = None,
              cone_deg: float = None, radius_cm: float = None, shadows: bool = None, channels: list = None,
              owner: str = "manual") -> dict:
    """A practical light (a fixture seen in frame) by type, with physical output: bulb, lamp, candle, fire,
    downlight, desk_lamp, streetlight, tube, led_strip, neon, screen, phone, window (env.presets lists them).

    Args: type: the fixture. loc: [x,y,z] cm (the bulb/face). look_at or rotation to aim (downlights and strips
    point down by default). lumens/nits/intensity_cd override the preset's output; scale multiplies it.
    temperature_k or color [r,g,b]. Returns: like light.add. Pair the light with an emissive surface for the
    visible fixture (mat.* emissive in nits: same number).
    Example: film-ue op light.practical label=DeskLamp type=desk_lamp 'loc=[-180,60,140]' 'look_at=[-180,60,75]'
    """
    spec = {k: v for k, v in dict(type=type, loc=loc, look_at=look_at, rotation=rotation, lumens=lumens, nits=nits,
                                  intensity_cd=intensity_cd, temperature_k=temperature_k, color=color, scale=scale,
                                  width_cm=width_cm, height_cm=height_cm, cone_deg=cone_deg, radius_cm=radius_cm,
                                  shadows=shadows, channels=channels).items() if v is not None}
    try:
        canon = LL.practical(spec, label)
    except ValueError as e:
        raise OpError(str(e), code="bad_args", candidates=U_closest(type, LL.PRACTICALS)) from None
    res = _write(canon, owner, "practical", {"fm_practical": type})
    res["light"] = canon
    return res


def U_closest(name, names):
    from ..errors import closest
    return closest(str(name), list(names))


def _point_of(ref, offset=None, socket: str = "", head: bool = True):
    """A rig's subject/camera: [x,y,z], or an actor label (a socket on its skeletal mesh; else its location plus
    `offset`; else, for a subject, about eye height of its bounds)."""
    if ref is None:
        return None
    if isinstance(ref, (list, tuple)):
        p = [float(x) for x in ref]
    else:
        a = U.find(ref)
        if a is None:
            from .level import EAS
            raise not_found("actor", ref, [x.get_actor_label() for x in EAS().get_all_level_actors()],
                            hint="list them with level.actors")
        if socket:
            for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
                if c.does_socket_exist(socket):
                    v = c.get_socket_location(socket)
                    p = [v.x, v.y, v.z]
                    break
            else:
                raise OpError(f"{ref!r} has no socket or bone {socket!r}", code="not_found",
                              hint="level.bone lists bone positions; 'head' or 'FACIAL_C_FacialRoot' on a MetaHuman")
        elif offset is not None or not head:
            v = a.get_actor_location()
            p = [v.x, v.y, v.z]
        else:
            o, e = a.get_actor_bounds(False)
            p = [o.x, o.y, o.z + 0.86 * e.z]  # ~ eye height of a standing figure whose bounds are its body
    if offset is not None:
        p = [p[i] + float(offset[i]) for i in range(3)]
    return [round(x, 3) for x in p]


@op("light.rig", mutates=True, idempotent=True, tags=["lighting"])
def rig(*, subject, camera=None, facing_yaw_deg: float = None, preset: str = "three_point", key_lux: float = 800.0,
        ratio: float = None, lights: dict = None, prefix: str = "Rig_", key_side: str = "left", scale: float = 1.0,
        temperature_k: float = None, channels: list = None, subject_offset: list = None, socket: str = "",
        owner: str = "manual") -> dict:
    """Light a subject with a named rig (key/fill/rim/...) placed around it relative to the camera, intensities from
    the key's lux at the subject and the lighting ratio; converges (re-running moves/retunes, a dropped role is removed).

    Args: subject: an actor label or [x,y,z] cm (a label lights ~eye height of its bounds, or `socket`, or its
    location + `subject_offset`). camera: a label or [x,y,z] (else `facing_yaw_deg`). preset: env.presets rigs
    (three_point, interview, loop, rembrandt, butterfly, clamshell, split, high_key, low_key, noir, silhouette,
    window). key_lux: lux on the subject from the key. ratio: (key+fill):fill, 2 flat .. 8 noir. lights: per-role
    overrides {"rim": {"rel": 1.5}, "fill": null, "kicker": {}} (fields: angle side elevation distance width height
    cone temperature color rel lux candelas shadows channels). prefix: label prefix (lights are <prefix><Role>).
    key_side: left|right (camera-left/right). scale: x distances/sizes. temperature_k/channels: for every light.
    Returns: {"changed", "lights": [labels], "removed": [labels], "subject_point", "camera_point",
    "measured": {"lux", "per_light", "ratio"}}.
    Example: film-ue op light.rig subject=Host camera=HostCam preset=interview key_lux=900 prefix=Host_
    """
    sp = _point_of(subject, subject_offset, socket)
    cp = _point_of(camera, head=False) if camera is not None else None
    try:
        planned = R.plan(sp, camera=cp, facing=facing_yaw_deg, preset=preset, key_lux=key_lux, ratio=ratio,
                         lights=lights, prefix=prefix, key_side=key_side, scale=scale, temperature=temperature_k,
                         channels=channels)
        canon = R.to_lights(planned)
    except ValueError as e:
        raise OpError(str(e), code="bad_args", hint="env.presets lists the rig presets and roles") from None
    args = {k: v for k, v in dict(prefix=prefix, subject=subject, camera=camera, facing_yaw_deg=facing_yaw_deg,
                                  preset=preset, key_lux=key_lux, ratio=ratio, lights=lights, key_side=key_side,
                                  scale=scale, temperature_k=temperature_k, channels=channels,
                                  subject_offset=subject_offset, socket=socket or None).items() if v is not None}
    changed, labels = False, []
    for L in canon:
        res = _write({k: v for k, v in L.items() if k != "role"}, owner, L["role"], {"fm_rig": prefix})
        changed |= res["changed"]
        labels.append(L["label"])
    removed = U.remove([a.get_actor_label() for a in U.owned_actors()
                        if U.tag_value(a, "fm_rig") == prefix and a.get_actor_label() not in labels])
    record = {"args": args, "subject_point": sp, "camera_point": cp, "lights": labels, "owner": owner}
    first = U.find(labels[0]) if labels else None
    if first is not None and U.read_blob(first, "rig") != record:
        U.write_blob(first, "rig", record)
    m = R.illuminance_at(planned, sp)
    roles = {p["role"]: p["label"] for p in planned}
    ratio_m = R.ratio_of(planned, sp, roles["key"], roles["fill"]) if "key" in roles and "fill" in roles else None
    return {"changed": bool(changed or removed), "lights": labels, "removed": removed, "subject_point": sp,
            "camera_point": cp, "measured": {**m, "ratio": ratio_m}}


def _lights(labels=None) -> list:
    from .level import EAS
    out = []
    for a in EAS().get_all_level_actors():
        if labels and a.get_actor_label() not in labels:
            continue
        c, kind = _light_component(a)
        if c is not None:
            out.append(read(a))
    return out


def rigs_state() -> dict:
    """Every rig the ops placed: {prefix: {args, subject_point, camera_point, subject_now, camera_now, lights, owner}}."""
    out = {}
    for a in U.owned_actors():
        rec = U.read_blob(a, "rig")
        if not rec:
            continue
        args = rec.get("args", {})
        try:
            now_s = _point_of(args.get("subject"), args.get("subject_offset"), args.get("socket") or "")
        except OpError:
            now_s = None
        try:
            now_c = _point_of(args.get("camera"), head=False) if args.get("camera") is not None else None
        except OpError:
            now_c = None
        out[args.get("prefix", "")] = {**rec, "subject_now": now_s, "camera_now": now_c}
    return out


@op("light.describe", mutates=False, idempotent=True, tags=["lighting"])
def describe(*, labels: list = None, at: list = None) -> dict:
    """Every light in the level (or `labels`) as numbers: kind, loc, rotation, forward, intensity (cd, or lux for a
    directional), temperature or colour, size, cone, radius, channels, owner/role/rig; with `at` [x,y,z] also what
    each gives there (light.measure).

    Returns: {"lights": {label: {...}}, "rigs": {prefix: {...}}, "at": {...}?}.
    Example: film-ue op light.describe 'at=[0,0,165]'
    """
    ls = _lights(labels)
    out = {"lights": {L["label"]: L for L in ls}, "rigs": rigs_state()}
    if at is not None:
        out["at"] = _measure(ls, at)
    return out


def _measure(ls, at, normal=None) -> dict:
    specs = []
    for L in ls:
        s = {"label": L["label"], "kind": L["kind"], "loc": L["loc"], "forward": L["forward"],
             "candelas": L.get("intensity_cd", 0.0), "radius": L.get("radius_cm")}
        if L["kind"] == "spot":
            s["cone"], s["inner_cone"] = L.get("cone_deg", 30.0), L.get("inner_cone_deg", 18.0)
        if L["kind"] == "directional":
            s["lux"] = L.get("intensity_lux", 0.0)
        specs.append(s)
    return R.illuminance_at(specs, [float(x) for x in at], normal)


@op("light.measure", mutates=False, idempotent=True, tags=["lighting", "qa"])
def measure(*, at: list, normal: list = None, labels: list = None, key: str = "", fill: str = "") -> dict:
    """What the lights give at a point, analytically (inverse square, cosine, spot cone, attenuation; no shadows,
    no bounce): the numeric check of a rig without a render.

    Args: at: [x,y,z] cm. normal: the surface normal there (else each light is measured facing it). labels: only
    these lights (default all, directional lights included). key/fill: labels to report their lighting ratio.
    Returns: {"lux", "ev100" (incident), "per_light": {label: lux}, "ratio"?}.
    Example: film-ue op light.measure 'at=[0,0,165]' key=Host_Key fill=Host_Fill
    """
    m = _measure(_lights(labels), at, normal)
    if key and fill:
        k, f = m["per_light"].get(key), m["per_light"].get(fill)
        if k is None or f is None:
            raise not_found("light", key if k is None else fill, list(m["per_light"]))
        m["ratio"] = None if f <= 0 else round((k + f) / f, 4)
    return m


@op("light.channels", mutates=True, idempotent=True, tags=["lighting"])
def channels(*, assign: dict) -> dict:
    """Lighting channels (0-2) for actors: on a light, which surfaces it lights; on a mesh/character/groom, which
    lights reach it. Re-fetches components by name (a Blueprint actor's construction script replaces them).

    Args: assign: {actor label: [channels]}, e.g. {"Host": [0, 1], "Key": [1]}.
    Returns: {"changed", "components": {label: n set}}.
    Example: film-ue op light.channels 'assign={"Host":[0,1],"Host_Key":[1]}'
    """
    out, changed = {}, False
    for lab, chs in assign.items():
        if any(int(c) not in (0, 1, 2) for c in chs):
            raise OpError(f"{lab}: lighting channels are 0, 1, 2; got {chs}", code="bad_args")
        a = U.find(lab)
        if a is None:
            from .level import EAS
            raise not_found("actor", lab, [x.get_actor_label() for x in EAS().get_all_level_actors()])
        want = sorted(int(c) for c in chs)
        n = 0
        names = [c.get_name() for c in a.get_components_by_class(unreal.SceneComponent)]
        for name in names:
            c = next((c for c in U.find(lab).get_components_by_class(unreal.SceneComponent) if c.get_name() == name), None)
            if isinstance(c, (unreal.LightComponent, unreal.PrimitiveComponent)):
                if U.to_json(c.get_editor_property("lighting_channels")) != want:
                    c.set_editor_property("lighting_channels", U.channels_struct(want))
                    changed = True
                n += 1
        out[lab] = n
    return {"changed": changed, "components": out}


def channels_state() -> dict:
    """{label: channels} for every actor whose lights/primitives are not on the default [0]."""
    from .level import EAS
    out = {}
    for a in EAS().get_all_level_actors():
        for c in a.get_components_by_class(unreal.SceneComponent):
            if isinstance(c, (unreal.LightComponent, unreal.PrimitiveComponent)):
                ch = U.to_json(c.get_editor_property("lighting_channels"))
                if isinstance(ch, list) and ch != [0]:
                    out[a.get_actor_label()] = ch
                break
    return out


@op("light.remove", mutates=True, idempotent=True, tags=["lighting"])
def remove(*, labels: list = None, rig: str = "", owner: str = "") -> dict:
    """Remove lights (and reflection captures) the env/light ops made: by `labels`, every light of a `rig` prefix,
    or everything an `owner` (spec name) made. Actors the ops did not make are never removed; missing ones are fine.

    Returns: {"changed", "removed": [labels]}.
    Example: film-ue op light.remove rig=Host_
    """
    targets = list(labels or [])
    for a in U.owned_actors():
        if (rig and U.tag_value(a, "fm_rig") == rig) or (owner and U.owner_of(a) == owner and _light_component(a)[0]):
            targets.append(a.get_actor_label())
    gone = U.remove(sorted(set(targets)))
    return {"changed": bool(gone), "removed": gone}
