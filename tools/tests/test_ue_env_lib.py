"""WP5's pure maths and planning (unreal/fmbridge/envlib), no engine: the sun, exposure calibration, light units,
rigs, grades, quality, statistics, the spec's validation, moods and planner."""
from __future__ import annotations

import math

import pytest

from filmtools.unreal.env_kind import envlib

E = envlib()
SUN, PH, R, G, Q, ST, LL, S = E.sun, E.photometry, E.rig, E.grade, E.quality, E.stats, E.lights, E.spec


# ------------------------------------------------------------------------------------------- sun

def test_equinox_noon_at_greenwich():
    p = SUN.position(51.48, 0.0, "2026-03-20", 12.0, 0.0)
    assert abs(p["elevation"] - (90 - 51.48)) < 0.6  # declination ~0 at the equinox
    assert 175 < p["azimuth"] < 185 and 5.9 < p["sunrise"] < 6.2 and 18.0 < p["sunset"] < 18.3


def test_summer_solstice_boulder_matches_noaa():
    # NOAA's calculator: Boulder 2026-06-21 13:00 MDT (tz -6): elevation ~73.4, azimuth ~178
    p = SUN.position(40.0, -105.0, "2026-06-21", 13.0, -6.0)
    assert abs(p["elevation"] - 73.4) < 0.3 and abs(p["azimuth"] - 178.5) < 2.0


def test_named_time_is_solved_for_the_day():
    h = SUN.time_for("golden_evening", 19.07, 72.88, "2026-11-05", 5.5)
    assert 17.0 < h < 18.0
    assert abs(SUN.position(19.07, 72.88, "2026-11-05", h, 5.5)["elevation"] - 6.0) < 0.01
    assert SUN.time_for("golden_morning", 19.07, 72.88, "2026-11-05", 5.5) < 8.0


def test_polar_night_and_unreachable_elevation_raise():
    with pytest.raises(ValueError, match="only reaches"):
        SUN.time_for(80.0, 51.5, 0.0, "2026-12-21", 0.0)
    with pytest.raises(ValueError, match="unknown time of day"):
        SUN.time_for("teatime", 0, 0, "2026-01-01")


def test_light_rotation_points_from_the_sun():
    r = SUN.light_rotation(30.0, 90.0, 0.0)  # sun in the east (+Y when north is +X): light travels west (-Y)
    assert r["pitch"] == -30.0 and r["yaw"] == 270.0
    back = SUN.from_rotation(r["pitch"], r["yaw"], 0.0)
    assert back == {"elevation": 30.0, "azimuth": 90.0}
    assert SUN.from_rotation(*[SUN.light_rotation(10, 200, 45)[k] for k in ("pitch", "yaw")], 45)["azimuth"] == 200


def test_sun_lux_and_colour_fall_towards_the_horizon():
    assert SUN.direct_lux(60) > SUN.direct_lux(20) > SUN.direct_lux(5) > 0 == SUN.direct_lux(-3)
    assert SUN.sun_kelvin(2) < SUN.sun_kelvin(10) < SUN.sun_kelvin(45) <= 5800


def test_resolve_without_a_place():
    assert SUN.resolve({"time": "golden_evening"})["elevation"] == 6.0
    r = SUN.resolve({"time": "12:00"})
    assert abs(r["elevation"] - 60.0) < 1e-6 and r["azimuth"] == 180.0


# ------------------------------------------------------------------------------------------- photometry

def test_ev100_round_trips_and_known_values():
    assert abs(PH.ev100_from_illuminance(2.5)) < 1e-9
    assert abs(PH.luminance_from_ev100(PH.ev100_from_luminance(37.0)) - 37.0) < 1e-9
    assert abs(PH.ev100_camera(16.0, 1 / 125, 100) - 15.0) < 0.05  # sunny 16


def test_unreal_manual_exposure_renders_metered_grey_as_middle_grey():
    # PostProcessEyeAdaptation.cpp: manual scale = 2^(bias - EVcam), EVcam 0 with physical exposure off
    for ev in (2.0, 8.5, 14.0):
        bias = PH.ue_manual_bias_for_ev100(ev)
        grey = PH.luminance_from_ev100(ev)
        assert abs(grey * PH.ue_exposure_scale(bias) - 0.18) < 1e-4
        assert abs(PH.ev100_for_ue_manual_bias(bias) - ev) < 1e-3
    assert abs(PH.ue_physical_ev100(4.0, 60.0, 100.0) - math.log2(960)) < 1e-9  # the engine default ~9.91


def test_light_units_follow_unreal():
    assert abs(PH.lumens_to_candelas(4 * math.pi, "point") - 1.0) < 1e-9
    assert abs(PH.lumens_to_candelas(math.pi, "rect") - 1.0) < 1e-9
    cd = PH.lumens_to_candelas(1000.0, "spot", 30.0)
    assert abs(PH.candelas_to_lumens(cd, "spot", 30.0) - 1000.0) < 1e-6
    assert abs(PH.candelas_for_lux(800.0, 200.0) - 3200.0) < 1e-9
    assert abs(PH.lux_from_candelas(3200.0, 200.0) - 800.0) < 1e-9
    assert PH.ue_light_ev_to_nits(0) == 1.0


def test_kelvin_swatches():
    warm, cool = PH.kelvin_to_rgb(2700), PH.kelvin_to_rgb(9000)
    assert warm[0] == 1.0 and warm[2] < 0.3 and cool[2] == 1.0 and cool[0] < 1.0


# ------------------------------------------------------------------------------------------- rigs

def test_three_point_geometry_and_ratio():
    L = R.plan([0, 0, 160], camera=[300, 0, 160], key_lux=1000)
    by = {x["role"]: x for x in L}
    assert by["key"]["loc"][1] > 0  # camera at +X looking at -X: camera-left is +Y
    assert by["fill"]["loc"][1] < 0 and by["rim"]["loc"][0] < 0  # fill opposite, rim behind
    m = R.illuminance_at(L, [0, 0, 160])
    assert abs(m["per_light"]["Rig_Key"] - 1000) < 0.5
    assert abs(R.ratio_of(L, [0, 0, 160], "Rig_Key", "Rig_Fill") - 3.0) < 1e-3


def test_rig_overrides_flip_and_drop():
    L = R.plan([0, 0, 160], camera=[300, 0, 160], preset="interview", key_side="right",
               lights={"eye": None, "kicker": {"rel": 0.3}}, prefix="Host_")
    roles = {x["role"]: x for x in L}
    assert "eye" not in roles and "kicker" in roles and roles["key"]["loc"][1] < 0
    assert all(x["label"].startswith("Host_") for x in L)
    with pytest.raises(ValueError, match="unknown rig preset"):
        R.plan([0, 0, 0], camera=[1, 0, 0], preset="rembrant")
    with pytest.raises(ValueError, match="unknown field"):
        R.plan([0, 0, 0], camera=[1, 0, 0], lights={"key": {"brightness": 2}})
    with pytest.raises(ValueError, match="camera position or the subject"):
        R.plan([0, 0, 0])


def test_every_rig_preset_plans_and_to_lights_is_canonical():
    for name in R.PRESETS:
        L = R.plan([0, 0, 150], facing=0.0, preset=name)
        canon = R.to_lights(L)
        assert len(canon) == len(L) and all(c["intensity_cd"] >= 0 for c in canon)
        assert all("rotation" in c for c in canon)


def test_spot_falloff_and_attenuation():
    assert PH.spot_falloff(0, 10, 20) == 1.0 and PH.spot_falloff(25, 10, 20) == 0.0
    assert 0 < PH.spot_falloff(15, 10, 20) < 1
    assert PH.inverse_square_falloff(0, 100) == 1.0 and PH.inverse_square_falloff(100, 100) == 0.0


# ------------------------------------------------------------------------------------------- lights

def test_normalize_light_intensity_forms():
    a = LL.normalize({"kind": "rect", "loc": [200, 0, 160], "look_at": [0, 0, 160], "lux": 800}, "Key")
    assert abs(a["intensity_cd"] - 3200) < 1e-6 and abs(a["rotation"]["yaw"] - 180) < 1e-6
    b = LL.normalize({"kind": "rect", "nits": 200, "width_cm": 60, "height_cm": 34}, "Screen")
    assert abs(b["intensity_cd"] - 200 * 0.6 * 0.34) < 1e-6
    c = LL.normalize({"kind": "point", "lumens": 800, "color": [1, 0.5, 0.2]}, "Bulb")
    assert c["temperature_k"] is None and abs(c["intensity_cd"] - 800 / (4 * math.pi)) < 1e-3
    with pytest.raises(ValueError, match="did you mean 'temperature_k'"):
        LL.normalize({"temprature_k": 3000}, "X")
    with pytest.raises(ValueError, match="does not apply"):
        LL.normalize({"kind": "point", "width_cm": 10}, "X")
    with pytest.raises(ValueError, match="needs `at`"):
        LL.normalize({"kind": "point", "lux": 10}, "X")


def test_practicals():
    d = LL.practical({"type": "downlight", "loc": [0, 0, 280]}, "Down")
    assert d["kind"] == "spot" and d["rotation"]["pitch"] == -90.0 and d["temperature_k"] == 3000.0
    s = LL.practical({"type": "screen", "loc": [0, 0, 100], "look_at": [100, 0, 100], "scale": 2}, "TV")
    assert abs(s["intensity_cd"] - 2 * 200 * 0.6 * 0.34) < 1e-3
    with pytest.raises(ValueError, match="type 'lava'"):
        LL.practical({"type": "lava", "loc": [0, 0, 0]}, "X")


def test_rotation_equivalence():
    assert LL.same_rotation({"pitch": 0, "yaw": 180}, {"pitch": 0, "yaw": -180})
    assert not LL.same_rotation({"pitch": 0, "yaw": 0}, {"pitch": 0, "yaw": 1})
    assert LL.differs({"a": 1.0, "rotation": {"pitch": 0, "yaw": 360}}, {"a": 1.0000001, "rotation": {"pitch": 0, "yaw": 0}}) == []


# ------------------------------------------------------------------------------------------- grade & quality

def test_grades_reset_and_aliases():
    f = G.fields({"preset": "teal_orange", "vignette": 0.1, "saturation": 0.8, "white_balance": 5000})
    assert f["vignette_intensity"] == 0.1 and f["color_saturation"] == [1, 1, 1, 0.8] and f["white_temp"] == 5000
    n = G.fields({"preset": "neutral"})
    assert n["color_gain_shadows"] == [1.0, 1.0, 1.0, 1.0]  # a re-grade resets the old preset's band wheels
    assert set(f) == set(n)
    assert G.fields({"lut": "/Game/LUT/T_Film"})["color_grading_intensity"] == 1.0
    with pytest.raises(ValueError, match="unknown grade preset"):
        G.fields({"preset": "teal"})


def test_quality_presets():
    for name in Q.PRESETS:
        cv = Q.cvars(name)
        assert cv["r.DynamicGlobalIlluminationMethod"] in (0, 1) and "r.MegaLights.Enable" not in cv
    c = Q.cvars({"preset": "cinematic", "megalights": True})
    assert c["r.Lumen.HardwareRayTracing"] == 1 and c["r.Lumen.HardwareRayTracing.LightingMode"] == 1
    assert c["r.MegaLights.EnableForProject"] == 1
    assert Q.post_fields("no_gi")["reflection_method"] == "ReflectionMethod.SCREEN_SPACE"
    with pytest.raises(ValueError, match="unknown key"):
        Q.resolve({"preset": "final", "lumens": {}})


# ------------------------------------------------------------------------------------------- stats

def test_scene_stats_meter_a_grey_card():
    lum = PH.luminance_from_ev100(9.0)
    st = ST.scene_stats([(lum, lum, lum)] * 50, exposure_ev100=9.0)
    assert abs(st["metered_ev100"] - 9.0) < 1e-3 and abs(st["stops_over"]) < 1e-3 and st["cast"]["magnitude"] < 1e-6


def test_display_stats_and_checks():
    dark = [(0.05, 0.05, 0.05)] * 90 + [(1.0, 1.0, 1.0)] * 10
    st = ST.display_stats(dark)
    assert st["clipped"] == 0.1 and st["mean"] < 0.2
    res = {r["check"]: r for r in ST.check(st)}
    assert not res["mean"]["ok"] and "too dark" in res["mean"]["hint"] and not res["clipped"]["ok"]
    good = ST.display_stats([(0.45, 0.45, 0.45)] * 100)
    assert all(r["ok"] for r in ST.check(good))
    warm = ST.display_stats([(0.6, 0.45, 0.3)] * 10)
    assert warm["cast"]["warm"] > 0.5


def test_png_round_trip(tmp_path):
    px = [(x / 7, 0.5, 1 - x / 7) for x in range(8)] * 4
    ST.write_png(str(tmp_path / "a.png"), 8, 4, px)
    w, h, back = ST.read_png((tmp_path / "a.png").read_bytes())
    assert (w, h) == (8, 4) and all(abs(a - b) < 1 / 255 + 1e-9 for p, q in zip(px, back) for a, b in zip(p, q))
    _, _, sub = ST.read_png((tmp_path / "a.png").read_bytes(), step=2)
    assert len(sub) == 8


# ------------------------------------------------------------------------------------------- spec

def spec(**kw):
    return {"kind": "environment", "version": 1, "name": "t", **kw}


def test_validation_names_the_field_and_suggests():
    with pytest.raises(S.SpecError, match="sunn.*did you mean 'sun'"):
        S.resolve(spec(sunn={}))
    with pytest.raises(S.SpecError, match="fog.densty.*did you mean 'density'"):
        S.resolve(spec(fog={"densty": 1}))
    with pytest.raises(S.SpecError, match="no mood 'dusk'"):
        S.resolve(spec(moods={"night": {}}), mood="dusk")
    with pytest.raises(S.SpecError, match="unknown preset"):
        S.resolve(spec(preset="studio"))
    with pytest.raises(S.SpecError, match="rigs.H.subject"):
        S.desired(spec(rigs={"H": {"camera": "C"}}))
    with pytest.raises(S.SpecError, match="only an environment spec"):
        S.resolve({"kind": "lighting", "preset": "studio_black"})
    with pytest.raises(S.SpecError, match="unknown field for a lighting spec"):
        S.resolve({"kind": "lighting", "sun": {}})


def test_presets_and_moods_merge():
    d = S.desired(spec(preset="interior_day", moods={"night": {"sun": False, "exposure": {"ev100": 5}}}), mood="night")
    assert d["sun"] is None and "sun" in d["off"]
    assert d["post"]["auto_exposure_bias"] == round(PH.ue_manual_bias_for_ev100(5), 4)
    day = S.desired(spec(preset="interior_day"))
    assert day["sun"]["intensity_lux"] == SUN.SOLAR_LUX and day["post"]["auto_exposure_bias"] == round(
        PH.ue_manual_bias_for_ev100(8.5), 4)


def test_exposure_auto_from_the_key():
    d = S.desired(spec(preset="studio_black", rigs={"H": {"subject": [0, 0, 160], "camera": [300, 0, 160],
                                                          "key_lux": 800}}))
    assert abs(d["post"]["auto_exposure_bias"] - PH.ue_manual_bias_for_ev100(PH.ev100_from_illuminance(800))) < 1e-3


def test_every_environment_preset_resolves():
    for name in S.PRESETS:
        d = S.desired(spec(preset=name))
        assert isinstance(d["post"], dict) and d["cvars"]


def _state_after(steps, state=None):
    """What env.describe would say after these steps ran (a tiny model of the ops, for convergence)."""
    st = {k: (dict(v) if isinstance(v, dict) else v) for k, v in (state or {}).items()}
    st.setdefault("owners", {})
    for s in steps:
        op, a = s["op"], dict(s["args"])
        owner = a.pop("owner", "manual")
        part = op.split(".")[1]
        if op in ("env.sun", "env.moon"):
            lab = S.LABELS[part]
            st[part] = {**a, "label": lab, "rotation": SUN.light_rotation(a["elevation_deg"], a["azimuth_deg"],
                                                                         a["north_yaw_deg"])}
            st["owners"][lab] = owner
        elif op in ("env.atmosphere", "env.clouds", "env.sky_light", "env.hdri", "env.fog"):
            st[part] = {**a, "label": S.LABELS[part]}
            st["owners"][S.LABELS[part]] = owner
        elif op == "env.post":
            p = dict(st.get("post") or {})
            p.update(a["fields"])
            for k in a["clear"]:
                p.pop(k, None)
            st["post"] = p
            st["post_owned_fields"] = sorted(p)
        elif op == "env.cvars":
            st["cvars"] = {**(st.get("cvars") or {}), **a["cvars"]}
        elif op == "light.add":
            st.setdefault("lights", {})[a["label"]] = a
            st["owners"][a["label"]] = owner
        elif op == "light.rig":
            st.setdefault("rigs", {})[a["prefix"]] = {"args": a, "owner": owner, "subject_point": [0, 0, 0],
                                                      "subject_now": [0, 0, 0], "camera_point": None, "camera_now": None}
        elif op == "env.remove":
            for p in a["parts"]:
                st[p] = None
        elif op == "light.remove":
            for lab in a.get("labels", []):
                st.get("lights", {}).pop(lab, None)
        elif op == "light.channels":
            st["channels"] = {**(st.get("channels") or {}), **a["assign"]}
        elif op == "env.reflection_capture":
            st.setdefault("captures", {})[a["label"]] = a
            st["owners"][a["label"]] = owner
    return st


FULL = spec(preset="exterior_golden", sun={"time": "golden_evening", "lat": 19.07, "lon": 72.88, "date": "2026-11-05",
                                           "tz": 5.5},
            lights={"Window": {"kind": "rect", "loc": [-250, 200, 150], "look_at": [0, 0, 120], "nits": 2000}},
            practicals={"Lamp": {"type": "lamp", "loc": [-200, -150, 120]}},
            rigs={"Host": {"subject": "Host", "camera": "HostCam", "preset": "interview", "key_lux": 900}},
            channels={"Host": [0, 1]}, cvars={"r.HairStrands.SkyLighting": 0},
            reflection_captures={"Room": {"shape": "box", "loc": [0, 0, 150]}},
            moods={"night": {"sun": False, "moon": {}, "exposure": {"ev100": 2}, "grade": {"preset": "moonlight"}}})


def test_plan_converges_in_one_pass():
    steps = S.plan(FULL, {})
    ops = [s["op"] for s in steps]
    assert ops.index("env.atmosphere") < ops.index("env.sun") < ops.index("env.post") < ops.index("light.add")
    st = _state_after(steps)
    assert S.plan(FULL, st) == []  # converged: the second plan is empty


def test_mood_switch_plans_only_the_difference():
    st = _state_after(S.plan(FULL, {}))
    night = S.plan(FULL, st, mood="night")
    ops = [s["op"] for s in night]
    assert {"op": "env.remove", "args": {"parts": ["sun"]}, "why": "sun: not in the spec"} in night
    assert "env.moon" in ops and "env.post" in ops and "light.add" not in ops and "light.rig" not in ops
    st2 = _state_after(night, st)
    assert S.plan(FULL, st2, mood="night") == []
    back = S.plan(FULL, st2)  # and back to day
    assert "env.sun" in [s["op"] for s in back] and {"op": "env.remove", "args": {"parts": ["moon"]},
                                                      "why": "moon: not in the spec"} in back


def test_prune_only_touches_this_specs_own():
    st = _state_after(S.plan(FULL, {}))
    st["lights"]["Theirs"] = {"label": "Theirs"}
    st["owners"]["Theirs"] = "other-spec"
    smaller = {**FULL, "lights": {}, "practicals": {}}
    gone = [s for s in S.plan(smaller, st) if s["op"] == "light.remove"]
    assert gone == [{"op": "light.remove", "args": {"labels": ["Lamp", "Window"]}, "why": "lights no longer in the spec"}]
    keep = S.plan({**smaller, "prune": False}, st)
    assert not [s for s in keep if s["op"] == "light.remove"]


def test_rig_replans_when_the_subject_moves_or_args_change():
    st = _state_after(S.plan(FULL, {}))
    st["rigs"]["Host_"]["subject_now"] = [10, 0, 0]
    assert [s["op"] for s in S.plan(FULL, st)] == ["light.rig"]
    st["rigs"]["Host_"]["subject_now"] = [0, 0, 0]
    changed = {**FULL, "rigs": {"Host": {**FULL["rigs"]["Host"], "key_lux": 1200}}}
    # the key's lux also moves the 'auto' exposure (exposure follows the key)
    assert [s["op"] for s in S.plan(changed, st)] == ["env.post", "light.rig"]
    # a recorded rig carrying the op's defaults still matches a spec that leaves them out
    st["rigs"]["Host_"]["args"] = {**st["rigs"]["Host_"]["args"], "scale": 1.0, "key_side": "left", "socket": ""}
    assert S.plan(FULL, st) == []


def test_lighting_kind():
    sp = {"kind": "lighting", "version": 1, "name": "rig", "lights": {"K": {"kind": "spot", "loc": [0, 0, 300],
                                                                         "rotation": {"pitch": -90}, "lumens": 1000}}}
    steps = S.plan(sp, {})
    assert [s["op"] for s in steps] == ["light.add"]
    assert S.plan(sp, _state_after(steps)) == []


def test_json_schemas_are_in_sync_with_the_tables():
    import json
    from filmtools.unreal import env_kind
    for k in S.KINDS:
        committed = json.loads((env_kind.SCHEMAS / f"{k}.schema.json").read_text())
        assert committed == json.loads(json.dumps(S.json_schema(k))), \
            "regenerate: cd tools && python -m filmtools.unreal.env_kind"


def test_rig_defaults_match_the_op():
    import ast
    from pathlib import Path
    src = (Path(E.__file__).parents[1] / "ops" / "light.py").read_text()
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "rig")
    defaults = {a.arg: ast.literal_eval(d) for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults) if d is not None}
    for k, v in R.RIG_DEFAULTS.items():
        assert defaults.get(k, None) == v, k
