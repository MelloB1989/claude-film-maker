"""The older look.* lighting ops (look.light, look.sky, look.fog, look.post, look.channels) pinned: their return
values and the actors and properties they leave behind, compared with a golden snapshot taken from the
implementation before they became a thin layer over env.*/light.*. Regenerate the snapshot only on purpose:
LOOK_LEGACY_REGEN=1 pytest tests/test_ue_look_legacy.py."""
import json
import os
from pathlib import Path

from fakeunreal import run_op

GOLDEN = Path(__file__).parent / "data" / "look_legacy_golden.json"

LIGHT_PROPS = ("intensity", "light_color", "use_temperature", "temperature", "attenuation_radius", "cast_shadows",
               "specular_scale", "volumetric_scattering_intensity", "source_width", "source_height",
               "barn_door_angle", "barn_door_length", "outer_cone_angle", "inner_cone_angle", "lighting_channels")
SUN_PROPS = ("intensity", "use_temperature", "temperature", "atmosphere_sun_light", "light_source_angle",
             "cast_shadows", "lighting_channels")
SKY_PROPS = ("real_time_capture", "intensity")
FOG_PROPS = ("fog_density", "fog_height_falloff", "start_distance", "volumetric_fog", "enable_volumetric_fog",
             "volumetric_fog_albedo", "volumetric_fog_extinction_scale", "fog_max_opacity")
POST_FIELDS = ("auto_exposure_method", "auto_exposure_bias", "white_temp", "bloom_intensity", "vignette_intensity",
               "color_saturation", "lumen_final_gather_quality")


def _v(x):
    """An engine value as plain data, by its kind (independent of the ops' own serialisers)."""
    t = type(x).__name__
    if x is None or isinstance(x, (bool, int, str)):
        return x
    if isinstance(x, float):
        return round(x, 4)
    if t == "Color":
        return {"rgba8": [x.r, x.g, x.b, x.a]}
    if t == "LinearColor":
        return [round(x.r, 4), round(x.g, 4), round(x.b, 4), round(x.a, 4)]
    if t == "Vector4":
        return [round(x.x, 4), round(x.y, 4), round(x.z, 4), round(x.w, 4)]
    if t == "LightingChannels":
        return [k for k in range(3) if x.get_editor_property(f"channel{k}")]
    if t == "EnumValue":
        return f"{x.enum}.{x.name}"
    if t == "Stub":
        return "<unset>"
    try:
        return round(float(x), 4)
    except (TypeError, ValueError):
        return str(x)


def _comp(a, props):
    c = next((c for c in a._components if type(c).__name__.endswith(("LightComponent", "FogComponent"))), None)
    return {p: _v(c._props.get(p)) if p in c._props else "<unset>" for p in props} if c is not None else {}


def snapshot(ue) -> dict:
    out = {}
    for a in ue.world.actors():
        lab = a.get_actor_label()
        if lab in ("Host", "Shelf"):
            comps = {c.get_name(): _v(c._props.get("lighting_channels")) for c in a._components}
            out[lab] = {"channels": comps}
            continue
        p, r = a.get_actor_location(), a.get_actor_rotation()
        rec = {"class": type(a).__name__, "loc": [round(p.x, 3), round(p.y, 3), round(p.z, 3)],
               "rot": [round(r.pitch, 3), round(r.yaw, 3), round(r.roll, 3)]}
        cname = type(a).__name__
        if cname == "DirectionalLight":
            rec["props"] = _comp(a, SUN_PROPS)
        elif cname in ("RectLight", "SpotLight", "PointLight"):
            rec["props"] = _comp(a, LIGHT_PROPS)
        elif cname == "SkyLight":
            rec["props"] = _comp(a, SKY_PROPS)
        elif cname == "ExponentialHeightFog":
            rec["props"] = _comp(a, FOG_PROPS)
        elif cname == "PostProcessVolume":
            s = a.get_editor_property("settings")
            rec["unbound"] = _v(a.get_editor_property("unbound"))
            rec["post"] = {f: [_v(s.get_editor_property("override_" + f)), _v(s.get_editor_property(f))]
                           for f in POST_FIELDS}
        out[lab] = rec
    return out


def scenario(ue) -> dict:
    """Every legacy lighting op, some twice (re-running must not duplicate), on a small set."""
    host = ue.spawn("SkeletalMeshActor", "Host")
    host.add_component(ue.SkeletalMeshComponent, "Body")
    ue.spawn("StaticMeshActor", "Shelf")
    r = {}
    r["key"] = run_op("look.light", label="Key", kind="rect", loc=[140, 130, 215], look_at=[0, 0, 165], intensity=9.0,
                      temperature=5000, width=140, height=140, barn_angle=60)
    r["key_again"] = run_op("look.light", label="Key", kind="rect", loc=[140, 130, 215], look_at=[0, 0, 165],
                            intensity=9.0, temperature=5000, width=140, height=140, barn_angle=60)
    r["window"] = run_op("look.light", label="Window", kind="rect", loc=[-246, 205, 150], look_at=[40, 145, 120],
                         intensity=1.2, color=[0.42, 0.53, 0.74], width=120, height=200, shadows=False)
    r["down"] = run_op("look.light", label="Down", kind="spot", loc=[0, 0, 290], look_at=[0, 0, 0], intensity=40,
                       temperature=2700, cone=32, radius=600, specular=0.5, volumetric=2.0)
    r["candle"] = run_op("look.light", label="Candle", kind="point", loc=[-200, 0, 120], intensity=0.1,
                         temperature=1800, radius=70)
    r["plain"] = run_op("look.light", label="Plain", kind="point", loc=[0, 300, 200])
    r["sky"] = run_op("look.sky", elevation=28, azimuth=-28, lux=17000, temperature=5100, sky_intensity=0.6,
                      shadow_softness=0.7)
    r["sky_again"] = run_op("look.sky", elevation=28, azimuth=-28, lux=17000, temperature=5100, sky_intensity=0.6,
                            shadow_softness=0.7, channels=[0, 1])
    r["fog"] = run_op("look.fog", density=0.0006, volumetric=True, albedo=(0.95, 0.93, 0.9), extinction=0.05,
                      height_falloff=0.02)
    r["post"] = run_op("look.post", settings={"auto_exposure_method": "AutoExposureMethod.AEM_MANUAL",
                                              "auto_exposure_bias": 8.3, "white_temp": 5600.0, "bloom_intensity": 0.25,
                                              "vignette_intensity": 0.25, "lumen_final_gather_quality": 4.0})
    r["post_again"] = run_op("look.post", settings={"bloom_intensity": 0.3})
    r["channels"] = run_op("look.channels", labels=["Key", "Window"], channels=[1])
    r["channels_host"] = run_op("look.channels", labels=["Host", "Shelf"], channels=[0, 1])
    return r


def _jsonable(v):
    return json.loads(json.dumps(v, default=str))


def _intended(want: dict) -> dict:
    """The golden (taken from the pre-layer implementation) with the differences made on purpose when look.* became
    a layer over env.*/light.*; each is a fix or what the engine already did:
    - look.light with neither colour nor temperature: 6500 K (Unreal's neutral white) instead of temperature off
      with a white filter: the same light;
    - look.light colour (sRGB 0-1, as before) is rounded to the nearest 8-bit step (the old code truncated: a step
      of 1/255 at most), and a coloured light's white temperature is left at the component's default;
    - look.fog `volumetric` now sets enable_volumetric_fog (the engine's name); the old `volumetric_fog` does not exist
      on 5.8's fog component (ExponentialHeightFogComponent.h:136), so the old code silently never enabled it;
      the albedo is rounded like the light colour."""
    W = want["state"]
    W["Plain"]["props"]["use_temperature"] = True
    W["Plain"]["props"]["temperature"] = 6500.0
    W["FM_Fog"]["props"]["volumetric_fog"] = "<unset>"
    W["FM_Fog"]["props"]["enable_volumetric_fog"] = True
    return want


def _close_colors(a, b):
    """FColors within one 8-bit step (rounding instead of truncating)."""
    if isinstance(a, dict) and "rgba8" in a and isinstance(b, dict) and "rgba8" in b:
        return all(abs(x - y) <= 1 for x, y in zip(a["rgba8"], b["rgba8"]))
    return a == b


def test_legacy_look_pinned(ue, fmb):
    got = {"results": _jsonable(scenario(ue)), "state": _jsonable(snapshot(ue))}
    assert ue.dialogs == []
    if os.environ.get("LOOK_LEGACY_REGEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
    want = _intended(json.loads(GOLDEN.read_text()))
    assert got["results"] == want["results"]
    assert sorted(got["state"]) == sorted(want["state"])
    for lab, w in want["state"].items():
        g = got["state"][lab]
        for k in w:
            if k == "props":
                for p, wv in w["props"].items():
                    assert _close_colors(g["props"][p], wv), (lab, p, g["props"][p], wv)
            elif k in ("loc", "rot"):  # the pure look-at and the engine's agree to rounding
                assert all(abs(x - y) <= 0.002 for x, y in zip(g[k], w[k])), (lab, k, g[k], w[k])
            else:
                assert g[k] == w[k], (lab, k, g[k], w[k])


def test_legacy_adopts_lights_made_before(ue, fmb):
    """A level saved with the old look.* lights (untagged) keeps working: the layer takes them over, never a conflict."""
    a = ue.spawn("RectLight", "Key")
    run_op("look.light", label="Key", kind="rect", loc=[100, 0, 200], intensity=5)
    assert [x.get_actor_label() for x in ue.world.actors()].count("Key") == 1
    sun = ue.spawn("DirectionalLight", "FM_Sun")
    run_op("look.sky", elevation=20)
    assert [x.get_actor_label() for x in ue.world.actors()].count("FM_Sun") == 1
    del a, sun
