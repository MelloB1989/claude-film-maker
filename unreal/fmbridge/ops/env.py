"""Environments: sun and moon by time of day and place, physical sky (atmosphere, volumetric clouds, sky light), HDRI
skies, height and volumetric fog, exposure (manual by EV100, physical camera, auto), colour grading, Lumen/VSM/HWRT
quality, reflection captures, and the ENVIRONMENT SPEC that converges all of it (env.apply), plus numbers to check
a look without a UI (env.meter, env.check).

Every env actor is labelled Env_<Part> and tagged as made by the ops (fm_env, fm_owner:<spec>), so re-running
converges instead of duplicating, and nothing the ops did not make is touched. docs/unreal/environment.md.
"""
from __future__ import annotations

import json
import math
import os

import unreal

from . import op
from . import _envutil as U
from ..envlib import grade as G
from ..envlib import photometry as ph
from ..envlib import quality as Q
from ..envlib import rig as R
from ..envlib import spec as S
from ..envlib import stats as ST
from ..envlib import sun as SUN
from ..envlib import lights as LL
from ..errors import OpError

L = S.LABELS
PART_CLASS = {"sun": "DirectionalLight", "moon": "DirectionalLight", "atmosphere": "SkyAtmosphere",
              "clouds": "VolumetricCloud", "sky_light": "SkyLight", "fog": "ExponentialHeightFog",
              "post": "PostProcessVolume"}
HDRI_BP = "/HDRIBackdrop/Blueprints/HDRIBackdrop"


def _bad(e: Exception, op_name: str) -> OpError:
    return OpError(str(e), code="bad_args", hint=f"film-ue ops {op_name} shows what it takes; env.presets the names")


def _has_atmosphere() -> bool:
    return U.find(L["atmosphere"]) is not None or any(a.get_class().get_name() == "SkyAtmosphere"
                                                      for a in U.EAS().get_all_level_actors())


# ------------------------------------------------------------------------------------------------ sun & moon

def _directional(canon: dict, owner: str, role: str) -> dict:
    a, created = U.ensure(canon["label"], "DirectionalLight", owner, role, (0, 0, 1000), canon["rotation"])
    moved = U.place(a, None, canon["rotation"])
    c = U.component(a, "DirectionalLightComponent")
    props = {"intensity": canon["intensity_lux"], "use_temperature": True, "temperature": canon["temperature_k"],
             "light_source_angle": canon["softness_deg"], "atmosphere_sun_light": True,
             "atmosphere_sun_light_index": canon["atmosphere_index"], "cast_shadows": True}
    if "cloud_shadows" in canon:
        props["cast_cloud_shadows"] = canon["cloud_shadows"]
    if "channels" in canon:
        props["lighting_channels"] = canon["channels"]
    ch = U.set_props(c, props)
    if U.tag_value(a, "fm_north") != f"{canon['north_yaw_deg']:g}":
        U.set_tags(a, {"fm_north": f"{canon['north_yaw_deg']:g}"})
    return {"label": canon["label"], "changed": bool(created or moved or ch), "created": created,
            "elevation_deg": canon["elevation_deg"], "azimuth_deg": canon["azimuth_deg"],
            "intensity_lux": canon["intensity_lux"], "temperature_k": canon["temperature_k"],
            **({"hour": canon["hour"]} if "hour" in canon else {})}


@op("env.sun", mutates=True, idempotent=True, tags=["environment", "lighting"])
def sun(*, time=None, lat: float = None, lon: float = None, date: str = None, tz: float = None,
        elevation_deg: float = None, azimuth_deg: float = None, north_yaw_deg: float = 0.0, intensity_lux="auto",
        temperature_k="auto", softness_deg: float = 0.5357, channels: list = None, cloud_shadows: bool = True,
        atmosphere_index: int = 0, owner: str = "manual") -> dict:
    """The sun (Env_Sun): placed by local time and place (NOAA solar position), a named time of day, or an explicit
    elevation/azimuth; converges.

    Args: time: 'HH:MM', decimal hours, or a name (dawn sunrise golden_morning morning noon afternoon golden_evening
    sunset blue_hour dusk night). lat/lon (deg, east +), date 'YYYY-MM-DD', tz (hours east of UTC): with these the
    position is astronomical (and a name is solved for that day: golden_evening = when the sun is 6 deg up).
    elevation_deg/azimuth_deg (compass, clockwise from north) override. north_yaw_deg: the level yaw of north
    (0 = +X). intensity_lux: 'auto' = 120000 under a SkyAtmosphere (it attenuates and tints), else clear-sky by
    elevation. temperature_k: 'auto' = 6500 with an atmosphere, else by elevation. softness_deg: angular size.
    Returns: {"label", "changed", "elevation_deg", "azimuth_deg", "intensity_lux", "temperature_k", "hour"?}.
    Example: film-ue op env.sun time=golden_evening lat=19.07 lon=72.88 date=2026-11-05 tz=5.5
    """
    v = {k: x for k, x in dict(time=time, lat=lat, lon=lon, date=date, tz=tz, elevation_deg=elevation_deg,
                               azimuth_deg=azimuth_deg, north_yaw_deg=north_yaw_deg, intensity_lux=intensity_lux,
                               temperature_k=temperature_k, softness_deg=softness_deg, channels=channels,
                               cloud_shadows=cloud_shadows).items() if x is not None}
    try:
        canon = S.norm_sun(v, _has_atmosphere())
    except ValueError as e:
        raise _bad(e, "env.sun") from None
    canon["atmosphere_index"] = int(atmosphere_index)
    return _directional(canon, owner, "sun")


@op("env.moon", mutates=True, idempotent=True, tags=["environment", "lighting"])
def moon(*, elevation_deg: float = 35.0, azimuth_deg: float = 120.0, north_yaw_deg: float = 0.0,
         intensity_lux="auto", temperature_k="auto", softness_deg: float = 1.0, channels: list = None,
         atmosphere_index: int = 1, owner: str = "manual") -> dict:
    """A moon (Env_Moon): a second atmosphere light (index 1) for night, dim and cool; converges.

    Args: elevation_deg, azimuth_deg (compass), north_yaw_deg. intensity_lux: 'auto' = 0.5 (a full moon is ~0.25;
    stylised nights use 0.5-2 with a low exposure). temperature_k: 'auto' = 4100. softness_deg: angular size.
    Returns: like env.sun.
    Example: film-ue op env.moon elevation_deg=40 azimuth_deg=135 intensity_lux=1.0
    """
    v = {k: x for k, x in dict(elevation_deg=elevation_deg, azimuth_deg=azimuth_deg, north_yaw_deg=north_yaw_deg,
                               intensity_lux=intensity_lux, temperature_k=temperature_k, softness_deg=softness_deg,
                               channels=channels).items() if x is not None}
    canon = S.norm_sun(v, _has_atmosphere(), L["moon"], moon=True)
    canon["atmosphere_index"] = int(atmosphere_index)
    return _directional(canon, owner, "moon")


def _read_directional(label: str):
    a = U.find(label)
    if a is None:
        return None
    c = a.get_component_by_class(unreal.DirectionalLightComponent)
    if c is None:
        return None
    north = float(U.tag_value(a, "fm_north") or 0.0)
    rot = U.rot_json(a.get_actor_rotation())
    pos = SUN.from_rotation(rot["pitch"], rot["yaw"], north)
    out = {"label": label, "elevation_deg": pos["elevation"], "azimuth_deg": pos["azimuth"], "north_yaw_deg": north,
           "rotation": rot, "intensity_lux": U.to_json(float(c.get_editor_property("intensity"))),
           "temperature_k": U.to_json(float(c.get_editor_property("temperature")))
           if c.get_editor_property("use_temperature") else None,
           "softness_deg": U.to_json(float(c.get_editor_property("light_source_angle"))),
           "atmosphere_index": int(c.get_editor_property("atmosphere_sun_light_index")),
           "cloud_shadows": bool(c.get_editor_property("cast_cloud_shadows")),
           "channels": U.to_json(c.get_editor_property("lighting_channels")), "owner": U.owner_of(a)}
    return out


# ------------------------------------------------------------------------------------------------ sky

ATMO_PROPS = ("rayleigh_scattering_scale", "mie_scattering_scale", "mie_absorption_scale", "mie_anisotropy",
              "multi_scattering_factor", "aerial_pespective_view_distance_scale", "height_fog_contribution",
              "ground_albedo")


@op("env.atmosphere", mutates=True, idempotent=True, tags=["environment"])
def atmosphere(*, preset: str = None, haze: float = None, rayleigh: float = None, aerial_distance_scale: float = None,
               mie_anisotropy: float = None, ground_albedo: list = None, multi_scattering: float = None,
               height_fog_contribution: float = None, rayleigh_scattering_scale: float = None,
               mie_scattering_scale: float = None, mie_absorption_scale: float = None,
               multi_scattering_factor: float = None, aerial_pespective_view_distance_scale: float = None,
               owner: str = "manual") -> dict:
    """A physical sky (Env_Atmosphere, SkyAtmosphere): Earth by default, with presets and multipliers; converges.

    Args: preset: clear|crisp|hazy|smoggy|dusty. haze: x Mie scattering (aerosols: whiter sky, hazier distance).
    rayleigh: x Rayleigh (bluer). aerial_distance_scale: x aerial perspective. mie_anisotropy 0-1. ground_albedo
    [r,g,b] linear. The raw engine fields (rayleigh_scattering_scale, mie_scattering_scale, ...) override.
    Returns: {"label", "changed", "props": [changed]}.
    Example: film-ue op env.atmosphere preset=hazy haze=4
    """
    friendly = {k: v for k, v in dict(preset=preset, haze=haze, rayleigh=rayleigh,
                                      aerial_distance_scale=aerial_distance_scale, mie_anisotropy=mie_anisotropy,
                                      ground_albedo=ground_albedo, multi_scattering=multi_scattering,
                                      height_fog_contribution=height_fog_contribution).items() if v is not None}
    try:
        canon = S.norm_atmosphere(friendly)
    except ValueError as e:
        raise _bad(e, "env.atmosphere") from None
    for k, v in dict(rayleigh_scattering_scale=rayleigh_scattering_scale, mie_scattering_scale=mie_scattering_scale,
                     mie_absorption_scale=mie_absorption_scale, multi_scattering_factor=multi_scattering_factor,
                     aerial_pespective_view_distance_scale=aerial_pespective_view_distance_scale).items():
        if v is not None:
            canon[k] = float(v)
    a, created = U.ensure(L["atmosphere"], "SkyAtmosphere", owner, "atmosphere")
    c = U.component(a, "SkyAtmosphereComponent")
    ch = U.set_props(c, {k: canon[k] for k in ATMO_PROPS})
    return {"label": L["atmosphere"], "changed": bool(created or ch), "created": created, "props": ch}


@op("env.clouds", mutates=True, idempotent=True, tags=["environment"])
def clouds(*, bottom_km: float = 5.0, height_km: float = 10.0, material: str = None, owner: str = "manual") -> dict:
    """Volumetric clouds (Env_Clouds): a layer from `bottom_km` up `height_km`, in the engine's simple cloud
    material or `material`; converges. Needs a SkyAtmosphere (env.atmosphere) to look right.

    Returns: {"label", "changed"}.
    Example: film-ue op env.clouds bottom_km=1.5 height_km=4
    """
    a, created = U.ensure(L["clouds"], "VolumetricCloud", owner, "clouds")
    c = U.component(a, "VolumetricCloudComponent")
    ch = U.set_props(c, {"layer_bottom_altitude": float(bottom_km), "layer_height": float(height_km)})
    if material:
        m = U.load(material)
        if m is None:
            raise OpError(f"no cloud material {material!r}", code="not_found", hint="assets.list /Game/... to find one")
        cur = U.to_json(c.get_editor_property("material"))
        if cur != material.split(".", 1)[0]:
            c.set_material(m)  # Material is a soft pointer: SetMaterial (VolumetricCloudComponent.h:186)
            ch.append("material")
    return {"label": L["clouds"], "changed": bool(created or ch), "created": created, "props": ch}


@op("env.sky_light", mutates=True, idempotent=True, tags=["environment", "lighting"])
def sky_light(*, mode: str = None, intensity: float = 1.0, cubemap: str = None, cubemap_angle_deg: float = 0.0,
              lower_hemisphere_black: bool = True, lower_hemisphere_color: list = None, channels: list = None,
              cast_shadows: bool = None, owner: str = "manual"):
    """The sky light (Env_SkyLight): ambient light from the sky, real-time captured (with an atmosphere), captured
    once from the scene, or from a cubemap (an HDRI); converges and recaptures when it changed. A multi-tick job.

    Args: mode: realtime|captured|cubemap (default realtime with an atmosphere, else captured). intensity: scale.
    cubemap: a TextureCube path (mode cubemap). cubemap_angle_deg: its yaw. lower_hemisphere_black/_color.
    Returns: {"label", "changed", "mode"}.
    Example: film-ue op env.sky_light mode=cubemap cubemap=/Game/HDRI/T_Studio intensity=1.2
    """
    v = {k: x for k, x in dict(mode=mode, intensity=intensity, cubemap=cubemap, cubemap_angle_deg=cubemap_angle_deg,
                               lower_hemisphere_black=lower_hemisphere_black,
                               lower_hemisphere_color=lower_hemisphere_color, channels=channels,
                               cast_shadows=cast_shadows).items() if x is not None}
    try:
        canon = S.norm_sky_light(v, _has_atmosphere())
    except ValueError as e:
        raise _bad(e, "env.sky_light") from None
    if canon.get("cubemap") and not unreal.EditorAssetLibrary.does_asset_exist(canon["cubemap"]):
        raise OpError(f"no cubemap {canon['cubemap']!r}", code="not_found",
                      hint="import the .hdr with assets.import as a long-lat cubemap (environment.md: HDRI)")
    a, created = U.ensure(L["sky_light"], "SkyLight", owner, "sky_light", (0, 0, 500))
    c = U.component(a, "SkyLightComponent")
    props = {"real_time_capture": canon["mode"] == "realtime",
             "source_type": "SkyLightSourceType.SLS_SPECIFIED_CUBEMAP" if canon["mode"] == "cubemap"
             else "SkyLightSourceType.SLS_CAPTURED_SCENE",
             "intensity": canon["intensity"], "lower_hemisphere_is_black": canon["lower_hemisphere_black"]}
    if canon["mode"] == "cubemap":
        props["cubemap"] = canon["cubemap"]
        props["source_cubemap_angle"] = canon["cubemap_angle_deg"]
    if "lower_hemisphere_color" in canon:
        props["lower_hemisphere_color"] = canon["lower_hemisphere_color"]
    if "channels" in canon:
        props["lighting_channels"] = canon["channels"]
    if "cast_shadows" in canon:
        props["cast_shadows"] = canon["cast_shadows"]
    ch = U.set_props(c, props)
    if (ch or created) and canon["mode"] != "realtime":
        yield 2  # let the scene settle before a one-off capture
        c.recapture_sky()
        yield
    return {"label": L["sky_light"], "changed": bool(created or ch), "created": created, "mode": canon["mode"],
            "props": ch}


def _read_sky_light():
    a = U.find(L["sky_light"])
    if a is None:
        return None
    c = a.get_component_by_class(unreal.SkyLightComponent)
    rt = bool(c.get_editor_property("real_time_capture"))
    st = str(U.to_json(c.get_editor_property("source_type")))
    mode = "realtime" if rt else "cubemap" if st.endswith("SPECIFIED_CUBEMAP") else "captured"
    out = {"label": L["sky_light"], "mode": mode, "intensity": U.to_json(float(c.get_editor_property("intensity"))),
           "lower_hemisphere_black": bool(c.get_editor_property("lower_hemisphere_is_black")),
           "lower_hemisphere_color": U.to_json(c.get_editor_property("lower_hemisphere_color")),
           "channels": U.to_json(c.get_editor_property("lighting_channels")),
           "cast_shadows": bool(c.get_editor_property("cast_shadows")), "owner": U.owner_of(a)}
    if mode == "cubemap":
        out["cubemap"] = U.to_json(c.get_editor_property("cubemap"))
        out["cubemap_angle_deg"] = U.to_json(float(c.get_editor_property("source_cubemap_angle")))
    return out


@op("env.hdri", mutates=True, idempotent=True, tags=["environment", "lighting"])
def hdri(*, cubemap: str, intensity: float = 1.0, rotation_deg: float = 0.0, backdrop: bool = False,
         size_cm: float = 15000.0, owner: str = "manual"):
    """Light (and optionally surround) the scene with an HDRI: the sky light from the cubemap, and with `backdrop`
    an HDRIBackdrop (Env_HDRI: a projected dome, needs the HDRIBackdrop plugin). A multi-tick job; converges.

    Args: cubemap: a TextureCube path (import an .hdr as a long-lat cubemap). intensity: sky light scale.
    rotation_deg: yaw of the image. backdrop: also show it. size_cm: the dome's size.
    Returns: {"changed", "sky_light": {...}, "backdrop": label|None, "warnings": [...]}.
    Example: film-ue op env.hdri cubemap=/Game/HDRI/T_Courtyard intensity=1 rotation_deg=90
    """
    sl = yield from sky_light(mode="cubemap", cubemap=cubemap, intensity=intensity, cubemap_angle_deg=rotation_deg,
                              owner=owner)
    warnings, changed, label = [], sl["changed"], None
    if backdrop:
        if not unreal.EditorAssetLibrary.does_asset_exist(HDRI_BP):
            raise OpError("the HDRIBackdrop plugin is not enabled (it is off by default)", code="unsupported",
                          hint="enable HDRIBackdrop in the .uproject Plugins and restart the editor, or use "
                               "backdrop=false (the sky light still lights the scene from the HDRI)")
        a, created = U.ensure(L["hdri"], HDRI_BP, owner, "hdri", asset=HDRI_BP)
        changed |= created
        # Blueprint variables (not verifiable in the source mirror: the plugin's Content is not there)
        for k, v in (("cubemap", U.load(cubemap)), ("intensity", float(intensity)), ("size", float(size_cm) / 100.0)):
            try:
                if U.to_json(a.get_editor_property(k)) != U.to_json(v):
                    a.set_editor_property(k, v)
                    changed = True
            except Exception as e:  # noqa: BLE001
                warnings.append(f"HDRIBackdrop.{k}: {e}")
        if U.place(a, None, {"pitch": 0.0, "yaw": float(rotation_deg), "roll": 0.0}):
            changed = True
        label = L["hdri"]
    else:
        changed |= bool(U.remove([L["hdri"]]))
    return {"changed": changed, "sky_light": sl, "backdrop": label, "warnings": warnings}


def _read_hdri():
    sl = _read_sky_light()
    if not sl or sl["mode"] != "cubemap":
        return None
    a = U.find(L["hdri"])
    out = {"label": L["hdri"], "cubemap": sl.get("cubemap"), "intensity": sl["intensity"],
           "rotation_deg": sl.get("cubemap_angle_deg", 0.0), "backdrop": a is not None, "size_cm": 15000.0}
    if a is not None:
        try:
            out["size_cm"] = float(a.get_editor_property("size")) * 100.0
        except Exception:  # noqa: BLE001
            pass
    return out


# ------------------------------------------------------------------------------------------------ fog

FOG_PROPS = {"density": "fog_density", "falloff": "fog_height_falloff", "start_cm": "start_distance",
             "max_opacity": "fog_max_opacity", "cutoff_cm": "fog_cutoff_distance", "color": "fog_inscattering_luminance",
             "volumetric": "enable_volumetric_fog", "albedo": "volumetric_fog_albedo",
             "extinction": "volumetric_fog_extinction_scale", "distance_cm": "volumetric_fog_distance",
             "scattering": "volumetric_fog_scattering_distribution", "emissive": "volumetric_fog_emissive"}


@op("env.fog", mutates=True, idempotent=True, tags=["environment"])
def fog(*, preset: str = None, density: float = None, falloff: float = None, height_cm: float = None,
        start_cm: float = None, max_opacity: float = None, cutoff_cm: float = None, color: list = None,
        volumetric: bool = None, albedo: list = None, extinction: float = None, distance_cm: float = None,
        scattering: float = None, emissive: list = None, owner: str = "manual") -> dict:
    """Height fog and volumetric fog (Env_Fog): haze for depth and light shafts; a preset plus overrides; converges.

    Args: preset: none|light|haze|mist|dense|ground|interior_haze. density, falloff (height falloff), height_cm
    (the fog's base), start_cm, max_opacity 0-1, cutoff_cm, color (inscattering, linear), volumetric (bool),
    albedo [r,g,b], extinction, distance_cm (volumetric range), scattering (-0.9..0.9, + forward), emissive.
    Returns: {"label", "changed", "props": [changed]}.
    Example: film-ue op env.fog preset=interior_haze extinction=0.1
    """
    v = {k: x for k, x in dict(preset=preset, density=density, falloff=falloff, height_cm=height_cm,
                               start_cm=start_cm, max_opacity=max_opacity, cutoff_cm=cutoff_cm, color=color,
                               volumetric=volumetric, albedo=albedo, extinction=extinction, distance_cm=distance_cm,
                               scattering=scattering, emissive=emissive).items() if x is not None}
    try:
        canon = S.norm_fog(v)
    except ValueError as e:
        raise _bad(e, "env.fog") from None
    a, created = U.ensure(L["fog"], "ExponentialHeightFog", owner, "fog", (0, 0, canon["height_cm"]))
    p = a.get_actor_location()
    moved = U.place(a, [p.x, p.y, canon["height_cm"]])
    c = U.component(a, "ExponentialHeightFogComponent")
    ch = U.set_props(c, {FOG_PROPS[k]: canon[k] for k in FOG_PROPS})
    return {"label": L["fog"], "changed": bool(created or moved or ch), "created": created, "props": ch}


def _read_fog():
    a = U.find(L["fog"])
    if a is None:
        return None
    c = a.get_component_by_class(unreal.ExponentialHeightFogComponent)
    out = {"label": L["fog"], "height_cm": round(a.get_actor_location().z, 3), "owner": U.owner_of(a)}
    vals = U.read_props(c, FOG_PROPS.values())
    out.update({k: vals[p] for k, p in FOG_PROPS.items()})
    return out


# ------------------------------------------------------------------------------------------------ post

def _override_name(s, field: str) -> str:
    for cand in (f"override_{field}", f"override_b_{field}"):
        try:
            s.get_editor_property(cand)
            return cand
        except Exception:  # noqa: BLE001
            continue
    raise OpError(f"PostProcessSettings has no field {field!r}", code="bad_args",
                  hint="names are snake_case of FPostProcessSettings (Scene.h), e.g. bloom_intensity, white_temp")


def _post_actor(owner: str, priority: float):
    a, created = U.ensure(L["post"], "PostProcessVolume", owner, "post")
    ch = U.set_props(a, {"unbound": True, "priority": float(priority), "blend_weight": 1.0, "enabled": True})
    return a, created or bool(ch)


@op("env.post", mutates=True, idempotent=True, tags=["environment", "look"])
def post(*, fields: dict = None, clear: list = None, priority: float = 1.0, owner: str = "manual") -> dict:
    """Set PostProcessSettings fields on the environment's unbound volume (Env_Post), each override flag set for
    you; `clear` turns fields' overrides off. Converges; reports what changed.

    Args: fields: {snake_case field: value}: numbers, bools, [r,g,b(,a)] colours and colour wheels, enum strings
    "AutoExposureMethod.AEM_MANUAL", texture paths for LUTs. clear: field names to stop overriding.
    priority: the volume's priority (1 wins over default-priority volumes).
    Returns: {"label", "changed", "set": [fields], "cleared": [fields]}.
    Example: film-ue op env.post 'fields={"bloom_intensity":0.3,"vignette_intensity":0.2}'
    """
    a, changed = _post_actor(owner, priority)
    s = a.get_editor_property("settings")
    done, cleared = [], []
    for k, v in (fields or {}).items():
        ov = _override_name(s, k)
        cur = s.get_editor_property(k)
        want = U.coerce(cur, v, k)
        if not bool(s.get_editor_property(ov)):
            s.set_editor_property(ov, True)
            done.append(k)
        if not U.same(U.to_json(cur), U.to_json(want)):
            s.set_editor_property(k, want)
            if k not in done:
                done.append(k)
    for k in clear or []:
        ov = _override_name(s, k)
        if bool(s.get_editor_property(ov)):
            s.set_editor_property(ov, False)
            cleared.append(k)
    if done or cleared:
        a.set_editor_property("settings", s)
    known = set(_post_fields_tag(a)) | set(fields or {})
    known -= set(cleared)
    if sorted(known) != sorted(_post_fields_tag(a)):
        U.write_blob(a, "post", sorted(known))
    return {"label": L["post"], "changed": bool(changed or done or cleared), "set": done, "cleared": cleared}


def _post_fields_tag(a) -> list:
    return U.read_blob(a, "post") or []


def _read_post():
    a = U.find(L["post"])
    if a is None:
        return {}, []
    s = a.get_editor_property("settings")
    owned = _post_fields_tag(a)
    out = {}
    for k in owned:
        try:
            if bool(s.get_editor_property(_override_name(s, k))):
                out[k] = U.to_json(s.get_editor_property(k))
        except OpError:
            continue
    return out, owned


@op("env.exposure", mutates=True, idempotent=True, tags=["environment", "look"])
def exposure(*, mode: str = "manual", ev100=None, compensation: float = 0.0, fstop: float = None,
             shutter_s: float = None, iso: float = None, min_ev100: float = None, max_ev100: float = None,
             speed: float = None, owner: str = "manual") -> dict:
    """Exposure on Env_Post, in photographic EV100 (what a light meter says), converges.

    Args: mode: manual (fixed: expose a scene metering `ev100`; physical camera exposure off, so a camera's
    aperture never changes brightness) | physical (the camera's fstop/shutter_s/iso decide; the cine camera's own
    aperture overrides fstop) | auto (histogram, adapting within min_ev100..max_ev100 at `speed`). ev100: e.g. 14-15
    sunny, 12 overcast, 8-9 bright interior/studio, 5 dim room, 1 stylised moonlight; 'auto' = from the key light
    or sun lux in the level spec. compensation: stops brighter (+)/darker (-).
    Returns: {"changed", "fields": {...}, "ev100": the scene EV100 exposed for}.
    Example: film-ue op env.exposure mode=manual ev100=8.5
    """
    v = {k: x for k, x in dict(mode=mode, ev100=9.0 if ev100 in (None, "auto") else ev100, compensation=compensation,
                               fstop=fstop, shutter_s=shutter_s, iso=iso, min_ev100=min_ev100, max_ev100=max_ev100,
                               speed=speed).items() if x is not None}
    if ev100 == "auto":
        lux = _key_lux_in_level()
        v["ev100"] = ph.ev100_from_illuminance(lux) if lux else 9.0
    try:
        f = S.exposure_fields(v, {})
    except ValueError as e:
        raise _bad(e, "env.exposure") from None
    res = post(fields=f, owner=owner)
    return {"changed": res["changed"], "fields": f, "ev100": v.get("ev100") if mode == "manual" else None}


def _key_lux_in_level():
    """The brightest rig key's lux at its subject, else the sun on the ground, from what is in the level."""
    from . import light as LT
    best = None
    for prefix, rec in LT.rigs_state().items():
        lux = float(rec.get("args", {}).get("key_lux", 800.0))
        best = lux if best is None else max(best, lux)
    if best is None:
        s = _read_directional(L["sun"])
        if s and s["elevation_deg"] > 0:
            best = SUN.direct_lux(s["elevation_deg"]) * math.sin(math.radians(s["elevation_deg"])) * 1.2
    return best


@op("env.grade", mutates=True, idempotent=True, tags=["environment", "look"])
def grade(*, preset: str = "neutral", fields: dict = None, owner: str = "manual") -> dict:
    """A colour grade on Env_Post: a preset (neutral clean warm_film teal_orange bleach_bypass noir_bw golden_hour
    moonlight pastel high_contrast vintage_fade documentary) plus overrides; re-grading resets the old preset's
    fields (every grade starts from neutral). Converges.

    Args: fields: friendly names or PostProcessSettings fields: white_balance (K), tint, saturation/contrast/
    gamma/gain/offset (a number or [r,g,b]; also color_<wheel>_shadows/_midtones/_highlights), bloom, grain,
    vignette, fringe, lut (a texture path) and lut_intensity, film_slope/toe/shoulder/black_clip/white_clip.
    Returns: {"changed", "set": [fields]}.
    Example: film-ue op env.grade preset=teal_orange 'fields={"vignette":0.2,"white_balance":6000}'
    """
    try:
        f = G.fields({"preset": preset, **(fields or {})})
    except ValueError as e:
        raise _bad(e, "env.grade") from None
    res = post(fields=f, owner=owner)
    return {"changed": res["changed"], "set": res["set"]}


@op("env.cvars", mutates=True, idempotent=True, tags=["environment", "rendering"])
def cvars(*, cvars: dict) -> dict:
    """Set console variables in the editor (they last until the editor restarts; render jobs take theirs from the
    quality preset: env.quality returns them for render.* cvar lists). Converges: only differing ones are sent.

    Args: cvars: {name: value}. Returns: {"changed", "set": {name: [before, after]}}.
    Example: film-ue op env.cvars 'cvars={"r.Lumen.HardwareRayTracing":1}'
    """
    done = {}
    for k, v in cvars.items():
        before = U.cvar(k)
        if before is not None and isinstance(v, (int, float, bool)) and U.same(float(before), float(v)):
            continue
        U.console(f"{k} {int(v) if isinstance(v, bool) else v}")
        done[k] = [before, U.cvar(k)]
    a = U.find(L["post"])
    if a is not None and done:
        names = sorted(set(U.read_blob(a, "cvars") or []) | set(done))
        U.write_blob(a, "cvars", names)
    else:
        _remember_cvars(done)
    return {"changed": bool(done), "set": done}


_CVARS_SEEN: set = set()


def _remember_cvars(done: dict) -> None:
    _CVARS_SEEN.update(done)


def _read_cvars() -> dict:
    names = set(Q.cvars("final")) | set(_CVARS_SEEN)
    a = U.find(L["post"])
    if a is not None:
        names |= set(U.read_blob(a, "cvars") or [])
    return {k: U.cvar(k) for k in sorted(names)}


@op("env.quality", mutates=True, idempotent=True, tags=["environment", "rendering"])
def quality(*, preset: str = "final", overrides: dict = None, project: bool = False, owner: str = "manual") -> dict:
    """Lumen / virtual shadow map / hardware ray tracing quality: preset preview|draft|final|cinematic|no_gi plus
    overrides (gi none|lumen, reflections none|lumen|ssr, shadows vsm|maps, hwrt bool, hit_lighting
    none|reflections|all, lumen {final_gather, reflection, scene_detail, scene_lighting, max_trace_distance},
    fog_grid [pixel, z], vsm_bias, megalights, cvars). Sets the cvars now and the post fields on Env_Post.

    Args: project: also write the project's renderer settings (URendererSettings GI/reflections/VSM/HWRT; HWRT
    needs ray tracing on in the project and an editor restart). Returns: {"changed", "cvars": {...}, "post": [...],
    "render_cvars": [ "name value", ... ] (to pass to a render job)}.
    Example: film-ue op env.quality preset=cinematic
    """
    spec = {"preset": preset, **(overrides or {})}
    try:
        cv, pf = Q.cvars(spec), Q.post_fields(spec)
    except ValueError as e:
        raise _bad(e, "env.quality") from None
    a = cvars(cvars=cv)
    b = post(fields=pf, owner=owner)
    changed = a["changed"] or b["changed"]
    if project:
        q = Q.resolve(spec)
        rs = unreal.get_default_object(unreal.RendererSettings)
        ch = U.set_props(rs, {"dynamic_global_illumination": Q.GI_ENUM[q["gi"]],
                              "reflections": Q.REFL_ENUM[q["reflections"]],
                              "shadow_map_method": "ShadowMapMethod.VIRTUAL_SHADOW_MAPS" if q["shadows"] == "vsm"
                              else "ShadowMapMethod.SHADOW_MAPS",
                              "use_hardware_ray_tracing_for_lumen": bool(q["hwrt"])})
        changed |= bool(ch)
    return {"changed": changed, "cvars": cv, "post": sorted(pf), "render_cvars": [f"{k} {v}" for k, v in cv.items()]}


# ------------------------------------------------------------------------------------------------ captures

@op("env.reflection_capture", mutates=True, idempotent=True, tags=["environment"])
def reflection_capture(*, label: str, shape: str = "sphere", loc: list = (0, 0, 150), radius_cm: float = 3000.0,
                       extent_cm: list = (500, 500, 250), transition_cm: float = 100.0, brightness: float = 1.0,
                       owner: str = "manual") -> dict:
    """A reflection capture (a fallback for reflections Lumen cannot trace, and for translucency): a sphere with an
    influence radius, or a box whose half-size is `extent_cm` (the actor's scale; ReflectionCaptureComponent.cpp:1358);
    converges. Captures update with env.captures_rebuild.

    Returns: {"label", "changed"}.
    Example: film-ue op env.reflection_capture label=RoomCapture shape=box 'loc=[0,0,150]' 'extent_cm=[400,300,150]'
    """
    if shape not in ("sphere", "box"):
        raise OpError(f"shape {shape!r} is not sphere|box", code="bad_args")
    cls = "SphereReflectionCapture" if shape == "sphere" else "BoxReflectionCapture"
    a, created = U.ensure(label, cls, owner, "capture", loc)
    changed = U.place(a, loc) or created
    c = U.component(a, "SphereReflectionCaptureComponent" if shape == "sphere" else "BoxReflectionCaptureComponent")
    props = {"brightness": float(brightness)}
    if shape == "sphere":
        props["influence_radius"] = float(radius_cm)
    else:
        props["box_transition_distance"] = float(transition_cm)
        sc = a.get_actor_scale3d()
        if not U.same([sc.x, sc.y, sc.z], [float(x) for x in extent_cm]):
            a.set_actor_scale3d(unreal.Vector(*[float(x) for x in extent_cm]))
            changed = True
    ch = U.set_props(c, props)
    return {"label": label, "changed": bool(changed or ch), "created": created}


def _read_captures() -> dict:
    out = {}
    for a in U.EAS().get_all_level_actors():
        cname = a.get_class().get_name()
        if cname not in ("SphereReflectionCapture", "BoxReflectionCapture"):
            continue
        p = a.get_actor_location()
        rec = {"label": a.get_actor_label(), "shape": "sphere" if cname.startswith("Sphere") else "box",
               "loc": [round(p.x, 3), round(p.y, 3), round(p.z, 3)], "owner": U.owner_of(a)}
        if rec["shape"] == "sphere":
            c = a.get_component_by_class(unreal.SphereReflectionCaptureComponent)
            rec["radius_cm"] = U.to_json(float(c.get_editor_property("influence_radius")))
        else:
            c = a.get_component_by_class(unreal.BoxReflectionCaptureComponent)
            sc = a.get_actor_scale3d()
            rec["extent_cm"] = [round(sc.x, 3), round(sc.y, 3), round(sc.z, 3)]
            rec["transition_cm"] = U.to_json(float(c.get_editor_property("box_transition_distance")))
        rec["brightness"] = U.to_json(float(c.get_editor_property("brightness")))
        out[rec["label"]] = rec
    return out


@op("env.captures_rebuild", mutates=True, idempotent=True, tags=["environment", "slow", "experimental"])
def captures_rebuild(*, quality: str = "preview"):
    """Rebuild the reflection captures. The only scriptable route runs a lighting build first
    (LevelEditorSubsystem.build_light_maps with captures; there is no console command), so it is slow on a level
    with static lighting; with Lumen-only levels it is quick. A multi-tick job.

    Args: quality: preview|medium|high|production (the lighting build's quality).
    Returns: {"changed": True, "built": bool}.
    Example: film-ue op env.captures_rebuild
    """
    q = {"preview": "QUALITY_PREVIEW", "medium": "QUALITY_MEDIUM", "high": "QUALITY_HIGH",
         "production": "QUALITY_PRODUCTION"}.get(quality)
    if q is None:
        raise OpError(f"quality {quality!r} is not preview|medium|high|production", code="bad_args")
    yield
    ok = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).build_light_maps(
        getattr(unreal.LightingBuildQuality, q), True)
    yield 1
    return {"changed": True, "built": bool(ok)}


# ------------------------------------------------------------------------------------------------ remove, describe

@op("env.remove", mutates=True, idempotent=True, tags=["environment"])
def remove(*, parts: list = None, owner: str = "") -> dict:
    """Remove environment parts the ops made (sun moon atmosphere clouds sky_light hdri fog post), or everything an
    `owner` (spec name) made with no `parts`. Missing parts are fine; actors the ops did not make are never removed.

    Returns: {"changed", "removed": [labels]}.
    Example: film-ue op env.remove 'parts=["fog","clouds"]'
    """
    if parts:
        bad = [p for p in parts if p not in L]
        if bad:
            from ..errors import closest
            raise OpError(f"unknown part(s) {bad}", code="bad_args", candidates=closest(bad[0], L))
        labels = [L[p] for p in parts]
    elif owner:
        labels = [a.get_actor_label() for a in U.owned_actors(owner)]
    else:
        raise OpError("say which: parts=[...] or owner=<spec name>", code="bad_args")
    gone = U.remove(labels)
    return {"changed": bool(gone), "removed": gone}


@op("env.describe", mutates=False, idempotent=True, tags=["environment", "lighting"])
def describe() -> dict:
    """The environment as numbers, in the same terms as the env/light ops and the spec: sun, moon (elevation,
    azimuth, lux, K), atmosphere, clouds, sky light, hdri, fog, the post fields Env_Post overrides (exposure, grade,
    quality) with the EV100 it exposes for, cvars, reflection captures, every light, rigs, lighting channels, and
    which spec owns each actor. The state env.apply / film-ue plan diff against.

    Returns: {"sun", "moon", "atmosphere", "clouds", "sky_light", "hdri", "fog", "post", "post_owned_fields",
    "exposure", "cvars", "captures", "lights", "rigs", "channels", "owners", "other": {...}}.
    Example: film-ue op env.describe
    """
    from . import light as LT
    out = {"sun": _read_directional(L["sun"]), "moon": _read_directional(L["moon"])}
    a = U.find(L["atmosphere"])
    out["atmosphere"] = None if a is None else {"label": L["atmosphere"], "owner": U.owner_of(a), **U.read_props(
        a.get_component_by_class(unreal.SkyAtmosphereComponent), ATMO_PROPS)}
    a = U.find(L["clouds"])
    if a is None:
        out["clouds"] = None
    else:
        c = a.get_component_by_class(unreal.VolumetricCloudComponent)
        out["clouds"] = {"label": L["clouds"], "owner": U.owner_of(a),
                         "bottom_km": U.to_json(float(c.get_editor_property("layer_bottom_altitude"))),
                         "height_km": U.to_json(float(c.get_editor_property("layer_height")))}
    out["sky_light"] = _read_sky_light()
    out["hdri"] = _read_hdri()
    out["fog"] = _read_fog()
    out["post"], out["post_owned_fields"] = _read_post()
    out["exposure"] = _exposure_summary(out["post"])
    out["cvars"] = _read_cvars()
    out["captures"] = _read_captures()
    ld = LT.describe()
    out["lights"] = {k: v for k, v in ld["lights"].items() if k not in (L["sun"], L["moon"])}
    out["rigs"] = ld["rigs"]
    out["channels"] = LT.channels_state()
    out["owners"] = {x.get_actor_label(): U.owner_of(x) for x in U.owned_actors()}
    out["other"] = {"sky": [x.get_actor_label() for x in U.EAS().get_all_level_actors()
                            if x.get_class().get_name() in ("SkyAtmosphere", "SkyLight", "ExponentialHeightFog",
                                                            "VolumetricCloud", "PostProcessVolume", "DirectionalLight")
                            and not U.is_owned(x)]}
    return out


def _exposure_summary(p: dict) -> dict:
    m = str(p.get("auto_exposure_method", ""))
    if m.endswith("AEM_MANUAL"):
        if p.get("auto_exposure_apply_physical_camera_exposure"):
            return {"mode": "physical", "bias": p.get("auto_exposure_bias")}
        b = p.get("auto_exposure_bias", 0.0) or 0.0
        return {"mode": "manual", "ev100": ph.ev100_for_ue_manual_bias(float(b)), "bias": b}
    if m:
        return {"mode": "auto", "bias": p.get("auto_exposure_bias"),
                "min_ev100": None if p.get("auto_exposure_min_brightness") is None
                else ph.ev100_from_ue(float(p["auto_exposure_min_brightness"])),
                "max_ev100": None if p.get("auto_exposure_max_brightness") is None
                else ph.ev100_from_ue(float(p["auto_exposure_max_brightness"]))}
    return {"mode": "unset"}


# ------------------------------------------------------------------------------------------------ specs

def _spec_store(name: str) -> str:
    d = os.path.join(unreal.Paths.project_saved_dir(), "fmbridge", "env")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{name}.json")


@op("env.plan", mutates=False, idempotent=True, tags=["environment", "spec"])
def plan(*, spec: dict, mood: str = None) -> dict:
    """What env.apply would do: the op calls that converge the level to an environment/lighting spec, without
    doing them. Errors name the spec field (did-you-mean) before anything changes.

    Returns: {"steps": [{"op", "args", "why"}], "converged": bool}.
    Example: film-ue op env.plan 'spec={"kind":"environment","name":"day","preset":"exterior_day"}'
    """
    try:
        steps = S.plan(spec, describe(), mood)
    except S.SpecError as e:
        raise OpError(str(e), code="bad_args", hint="docs/unreal/environment.md: the spec; env.presets: names") from None
    return {"steps": steps, "converged": not steps}


@op("env.apply", mutates=True, idempotent=True, tags=["environment", "lighting", "spec"])
def apply(*, spec: dict, mood: str = None, dry_run: bool = False):
    """Converge the level to an ENVIRONMENT (or LIGHTING) spec: diff it against env.describe, run only the needed
    env/light ops, re-describe and confirm a second plan is empty. A multi-tick job. Remembers the spec so
    env.mood can switch its moods later.

    Args: spec: the spec object (kind environment|lighting, version 1, name, preset?, sections...; environment.md).
    mood: one of the spec's `moods` (overrides spec.mood). dry_run: only plan.
    Returns: {"changed", "steps": [{"op", "why", "changed"}], "converged", "remaining": [steps]}.
    Example: film-ue op env.apply 'spec={"kind":"environment","name":"day","preset":"exterior_golden"}'
    """
    from . import call
    try:
        steps = S.plan(spec, describe(), mood)
    except S.SpecError as e:
        raise OpError(str(e), code="bad_args", hint="docs/unreal/environment.md: the spec; env.presets: names") from None
    if dry_run:
        return {"changed": False, "steps": steps, "converged": not steps, "remaining": steps}
    done = []
    for st in steps:
        r = call(st["op"], **st["args"])
        if hasattr(r, "send"):
            r = yield from r
        done.append({"op": st["op"], "why": st["why"], "changed": bool((r or {}).get("changed", True))})
        yield
    name = spec.get("name", "env")
    with open(_spec_store(name), "w") as f:
        json.dump(spec, f, indent=1)
    again = S.plan(spec, describe(), mood)
    return {"changed": any(d["changed"] for d in done), "steps": done, "converged": not again, "remaining": again}


@op("env.mood", mutates=True, idempotent=True, tags=["environment", "spec"])
def mood(*, name: str = None, spec_name: str = "env"):
    """Switch the last applied spec `spec_name` to one of its moods (day/night, ...): env.apply with that mood;
    `name` None goes back to the spec's own mood. A multi-tick job.

    Returns: env.apply's result plus {"mood"}.
    Example: film-ue op env.mood name=night spec_name=studio
    """
    path = _spec_store(spec_name)
    if not os.path.exists(path):
        have = [f[:-5] for f in os.listdir(os.path.dirname(path)) if f.endswith(".json")]
        from ..errors import closest
        raise OpError(f"no applied spec {spec_name!r}", code="not_found", candidates=closest(spec_name, have),
                      hint="apply it first with env.apply (or film-ue apply)")
    with open(path) as f:
        spec = json.load(f)
    res = yield from apply(spec=spec, mood=name or "")
    res["mood"] = name
    return res


@op("env.presets", mutates=False, idempotent=True, tags=["environment", "lighting"])
def presets() -> dict:
    """Every named thing the env/light ops and specs take, with what it is for: environment presets, times of day,
    atmosphere and fog presets, grades, quality presets, rig presets and roles, practical types.

    Example: film-ue op env.presets
    """
    return {"environment": {k: v["about"] for k, v in S.PRESETS.items()},
            "times_of_day": {k: f"sun at {e:g} deg ({side})" for k, (e, side) in SUN.TIMES.items()},
            "atmosphere": sorted(S.ATMOSPHERE["presets"]), "fog": {k: v for k, v in S.FOG.items()},
            "grades": {k: v["about"] for k, v in G.PRESETS.items()},
            "quality": {k: v["about"] for k, v in Q.PRESETS.items()},
            "rigs": {k: v["about"] for k, v in R.PRESETS.items()}, "rig_roles": sorted(R.ROLE),
            "practicals": {k: v["about"] for k, v in LL.PRACTICALS.items()},
            "exposure_ev100": {k: round(ph.ev100_from_illuminance(v), 1) for k, v in ph.SCENES.items()}}


@op("env.schema", mutates=False, idempotent=True, tags=["environment", "spec"])
def schema(*, kind: str = "environment") -> dict:
    """The JSON Schema of the environment or lighting spec (the same one in tools/filmtools/unreal/schemas/).

    Example: film-ue op env.schema kind=lighting
    """
    if kind not in S.KINDS:
        raise OpError(f"kind {kind!r} is not environment|lighting", code="bad_args")
    return S.json_schema(kind)


# ------------------------------------------------------------------------------------------------ measuring

def _fov_of(cam) -> float:
    c = cam.get_component_by_class(unreal.CineCameraComponent)
    if c is not None:
        fb = c.get_editor_property("filmback")
        w = float(fb.get_editor_property("sensor_width"))
        f = float(c.get_editor_property("current_focal_length"))
        return math.degrees(2 * math.atan(w / (2 * f)))
    c = cam.get_component_by_class(unreal.CameraComponent)
    return float(c.get_editor_property("field_of_view")) if c is not None else 90.0


@op("env.meter", mutates=False, idempotent=True, tags=["environment", "qa", "gpu"])
def meter(*, camera: str, width: int = 192, height: int = 108, exposure_ev100: float = None):
    """Meter the scene through a camera without a viewport: a scene capture in linear HDR (SceneColorHDR, read back
    raw, unclamped) gives the scene's luminance statistics and the EV100 a reflected meter would choose; a second in
    final colour gives the image's brightness, clipping, crush and colour cast. A multi-tick job (a few ticks).

    Args: camera: a camera actor label. width/height: capture size (small is enough for statistics).
    exposure_ev100: compare the scene with this exposure (default: what Env_Post exposes for, if manual).
    Returns: {"scene": scene_stats, "display": display_stats, "camera", "fov_deg"}.
    Example: film-ue op env.meter camera=HostCam
    """
    cam = U.find(camera)
    if cam is None:
        from ..errors import not_found
        raise not_found("camera", camera, [a.get_actor_label() for a in U.EAS().get_all_level_actors()
                                           if "Camera" in a.get_class().get_name()], hint="look.camera makes one")
    if exposure_ev100 is None:
        e = _exposure_summary(_read_post()[0])
        exposure_ev100 = e.get("ev100")
    w = U.world()
    RL = unreal.RenderingLibrary
    cap = U.EAS().spawn_actor_from_class(unreal.SceneCapture2D, cam.get_actor_location(), cam.get_actor_rotation())
    try:
        cap.set_actor_label("Env_Meter")
        cc = cap.get_editor_property("capture_component2d")
        cc.set_editor_property("fov_angle", _fov_of(cam))
        cc.set_editor_property("capture_every_frame", False)
        cc.set_editor_property("capture_on_movement", False)
        cc.set_editor_property("always_persist_rendering_state", True)
        out = {"camera": camera, "fov_deg": round(_fov_of(cam), 3)}
        for src, fmt, key in (("SCS_SCENE_COLOR_HDR", "RTF_RGBA16F", "scene"), ("SCS_FINAL_COLOR_LDR", "RTF_RGBA8", "display")):
            rt = RL.create_render_target2d(w, int(width), int(height), getattr(unreal.TextureRenderTargetFormat, fmt))
            cc.set_editor_property("texture_target", rt)
            cc.set_editor_property("capture_source", getattr(unreal.SceneCaptureSource, src))
            for _ in range(3):  # temporal history and streaming settle across a few captures
                cc.capture_scene()
                yield
            px = RL.read_render_target_raw_pixel_area(w, rt, 0, 0, int(width) - 1, int(height) - 1, key == "display")
            rgb = [(float(p.r), float(p.g), float(p.b)) for p in (px or [])]
            if not rgb:
                raise OpError(f"the {key} capture read back no pixels", code="engine",
                              hint="is the editor rendering (offscreen needs -RenderOffscreen, not -nullrhi)?")
            out[key] = ST.scene_stats(rgb, exposure_ev100) if key == "scene" else ST.display_stats(rgb)
        return out
    finally:
        U.EAS().destroy_actor(cap)


@op("env.check", mutates=False, idempotent=True, tags=["environment", "qa"])
def check(*, camera: str = "", png: str = "", targets: dict = None, spec: dict = None, step: int = 4):
    """A numeric verdict on a look: meter through `camera` (env.meter) or read a still `png` on the box (any
    look.still / render frame), and compare with targets: mean [lo,hi] (display luma), median, clipped_max,
    crushed_max, cast_max, warm [lo,hi], ev100 [lo,hi] (scene), range_stops_max, stops_over [lo,hi]. Defaults: a
    natural, well exposed frame. A multi-tick job.

    Args: targets, or `spec` (its checks: {camera, targets}). step: png subsampling.
    Returns: {"pass", "issues": [{code, severity, message, fix, value, expected}], "metrics": {...}}.
    Example: film-ue op env.check camera=HostCam 'targets={"mean":[0.3,0.5],"clipped_max":0.01}'
    """
    if spec and spec.get("checks"):
        camera = camera or spec["checks"].get("camera", "")
        targets = targets or spec["checks"].get("targets")
    if png:
        if not os.path.exists(png):
            raise OpError(f"no file {png!r} on the box", code="not_found", hint="make one with look.still or render.*")
        with open(png, "rb") as f:
            _, _, px = ST.read_png(f.read(), step=max(1, int(step)))
        metrics = {"display": ST.display_stats(px)}
    elif camera:
        metrics = yield from meter(camera=camera)
    else:
        raise OpError("give a camera (to meter) or a png (to read)", code="bad_args")
    results = ST.check(metrics, targets)
    issues = [{"code": f"env.exposure_{r['check']}", "severity": "fail", "message": f"{r['check']}: got {r['got']}, "
               f"want {r['want']}", "fix": r["hint"], "value": r["got"], "expected": r["want"]}
              for r in results if not r["ok"]]
    if camera:
        for i in issues:
            i["camera"] = camera
    return {"pass": not issues, "issues": issues, "metrics": metrics, "checks": results}
