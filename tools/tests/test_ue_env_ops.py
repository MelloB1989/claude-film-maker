"""WP5's ops against the fake engine: every env.*/light.* op runs, converges (a re-run changes nothing), describes
itself in the planner's terms, and env.apply leaves an empty second plan."""
from __future__ import annotations

import math

import pytest

from fakeunreal import run_op


def labels(ue):
    return [a.get_actor_label() for a in ue.world.actors()]


def test_light_add_converges_and_reports(ue, fmb):
    r = run_op("light.add", label="Key", kind="rect", loc=[200, 0, 160], look_at=[0, 0, 160], lux=800,
               temperature_k=5600, width_cm=120, height_cm=120, channels=[1])
    assert r["changed"] and r["created"] and labels(ue).count("Key") == 1
    c = ue.actor("Key").get_component_by_class(ue.RectLightComponent)
    assert c.get_editor_property("intensity") == pytest.approx(3200.0)
    assert c.get_editor_property("intensity_units") == "CANDELAS"
    assert c.get_editor_property("lighting_channels").get_editor_property("channel1") is True
    again = run_op("light.add", label="Key", kind="rect", loc=[200, 0, 160], look_at=[0, 0, 160], lux=800,
                   temperature_k=5600, width_cm=120, height_cm=120, channels=[1])
    assert again["changed"] is False and again["props"] == []
    d = run_op("light.describe", at=[0, 0, 160])
    assert d["lights"]["Key"]["intensity_cd"] == pytest.approx(3200.0)
    assert d["at"]["per_light"]["Key"] == pytest.approx(800.0, rel=1e-3)
    # a new kind remakes the same label
    run_op("light.add", label="Key", kind="spot", loc=[200, 0, 160], look_at=[0, 0, 160], lux=800)
    assert labels(ue).count("Key") == 1 and type(ue.actor("Key")).__name__ == "SpotLight"
    assert ue.dialogs == []


def test_light_add_refuses_someone_elses_actor(ue, fmb):
    ue.spawn("RectLight", label="Theirs")
    from fmbridge.errors import OpError
    with pytest.raises(OpError, match="not made by the env/light ops"):
        run_op("light.add", label="Theirs", kind="rect")


def test_colour_light_and_bad_args(ue, fmb):
    run_op("light.add", label="Neon", kind="rect", color=[1.0, 0.1, 0.4], nits=150, width_cm=80, height_cm=30)
    c = ue.actor("Neon").get_component_by_class(ue.RectLightComponent)
    assert c.get_editor_property("use_temperature") is False
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("light.add", label="X", kind="pointy")
    assert e.value.code == "bad_args"


def test_rig_places_measures_and_prunes_roles(ue, fmb):
    ue.spawn("SkeletalMeshActor", label="Host", location=ue.Vector(0, 0, 0), extent=(30, 30, 90))
    ue.spawn("CineCameraActor", label="Cam", location=ue.Vector(300, 0, 150))
    r = run_op("light.rig", subject="Host", camera="Cam", preset="interview", key_lux=900, prefix="Host_")
    assert sorted(r["lights"]) == ["Host_Eye", "Host_Fill", "Host_Hair", "Host_Key"]
    assert r["subject_point"][2] == pytest.approx(0 + 0.86 * 90)
    assert r["measured"]["per_light"]["Host_Key"] == pytest.approx(900, rel=1e-3)
    assert r["measured"]["ratio"] == pytest.approx(2.5, rel=1e-3)
    assert run_op("light.rig", subject="Host", camera="Cam", preset="interview", key_lux=900, prefix="Host_")["changed"] is False
    r2 = run_op("light.rig", subject="Host", camera="Cam", preset="interview", key_lux=900, prefix="Host_",
                lights={"eye": None})
    assert r2["removed"] == ["Host_Eye"] and "Host_Eye" not in labels(ue)
    st = run_op("light.describe")["rigs"]["Host_"]
    assert st["subject_point"] == st["subject_now"] and st["args"]["preset"] == "interview"
    m = run_op("light.measure", at=r["subject_point"], key="Host_Key", fill="Host_Fill")
    assert m["ratio"] == pytest.approx(2.5, rel=1e-3)
    assert run_op("light.remove", rig="Host_")["removed"] == ["Host_Fill", "Host_Hair", "Host_Key"]


def test_rig_unknown_subject_suggests(ue, fmb):
    ue.spawn("SkeletalMeshActor", label="Host")
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("light.rig", subject="Hots", camera=[300, 0, 150])
    assert e.value.code == "not_found" and "Host" in e.value.candidates


def test_practical_and_channels(ue, fmb):
    run_op("light.practical", label="Lamp", type="lamp", loc=[-200, -150, 120])
    c = ue.actor("Lamp").get_component_by_class(ue.PointLightComponent)
    assert c.get_editor_property("intensity") == pytest.approx(450 / (4 * math.pi), rel=1e-3)
    assert c.get_editor_property("temperature") == 2700.0
    ue.spawn("SkeletalMeshActor", label="Host")
    r = run_op("light.channels", assign={"Host": [0, 1], "Lamp": [0]})
    assert r["changed"] and r["components"]["Host"] == 1
    assert run_op("light.channels", assign={"Host": [0, 1]})["changed"] is False


def test_sun_by_place_and_time(ue, fmb):
    run_op("env.atmosphere", preset="hazy")
    r = run_op("env.sun", time="golden_evening", lat=19.07, lon=72.88, date="2026-11-05", tz=5.5)
    assert r["elevation_deg"] == pytest.approx(6.0, abs=0.01) and r["intensity_lux"] == 120000.0
    rot = ue.actor("Env_Sun").get_actor_rotation()
    assert rot.pitch == pytest.approx(-6.0, abs=0.01)
    assert run_op("env.sun", elevation_deg=r["elevation_deg"], azimuth_deg=r["azimuth_deg"])["changed"] is False
    d = run_op("env.describe")["sun"]
    assert d["elevation_deg"] == pytest.approx(6.0, abs=0.01) and d["azimuth_deg"] == pytest.approx(r["azimuth_deg"])
    run_op("env.moon")
    assert ue.actor("Env_Moon").get_component_by_class(ue.DirectionalLightComponent).get_editor_property(
        "atmosphere_sun_light_index") == 1


def test_sky_fog_clouds_hdri(ue, fmb):
    run_op("env.atmosphere")
    assert run_op("env.atmosphere")["changed"] is False
    run_op("env.clouds", bottom_km=1.5, height_km=4)
    r = run_op("env.sky_light")
    assert r["mode"] == "realtime"
    run_op("env.fog", preset="interior_haze")
    assert run_op("env.fog", preset="interior_haze")["changed"] is False
    from fmbridge.errors import OpError
    with pytest.raises(OpError, match="no cubemap"):
        run_op("env.hdri", cubemap="/Game/HDRI/Missing")
    ue.add_asset("/Game/HDRI/T_Sky", "TextureCube")
    h = run_op("env.hdri", cubemap="/Game/HDRI/T_Sky", rotation_deg=90)
    assert h["sky_light"]["mode"] == "cubemap" and ue.called("SkyLightComponent.recapture_sky")
    with pytest.raises(OpError) as e:
        run_op("env.hdri", cubemap="/Game/HDRI/T_Sky", backdrop=True)
    assert e.value.code == "unsupported"
    d = run_op("env.describe")
    assert d["hdri"]["cubemap"] == "/Game/HDRI/T_Sky" and d["clouds"]["bottom_km"] == 1.5


def test_exposure_grade_quality_post(ue, fmb):
    r = run_op("env.exposure", mode="manual", ev100=8.5)
    s = ue.actor("Env_Post").get_editor_property("settings")
    assert s.get_editor_property("override_auto_exposure_bias") is True
    assert s.get_editor_property("auto_exposure_apply_physical_camera_exposure") is False
    assert run_op("env.describe")["exposure"] == {"mode": "manual", "ev100": pytest.approx(8.5, abs=1e-3),
                                                  "bias": pytest.approx(-7.9739, abs=1e-3)}
    assert run_op("env.exposure", mode="manual", ev100=8.5)["changed"] is False
    g = run_op("env.grade", preset="teal_orange", fields={"vignette": 0.2})
    assert g["changed"] and s.get_editor_property("vignette_intensity") == 0.2
    assert type(ue.actor("Env_Post").get_editor_property("settings").get_editor_property("color_gain_shadows")).__name__ == "Vector4"
    q = run_op("env.quality", preset="cinematic", project=True)
    assert float(ue.cvars["r.Lumen.HardwareRayTracing"]) == 1.0 and "r.VolumetricFog.GridPixelSize 4" in q["render_cvars"]
    assert run_op("env.quality", preset="cinematic")["changed"] is False
    p = run_op("env.post", clear=["vignette_intensity"])
    assert p["cleared"] == ["vignette_intensity"]
    from fmbridge.errors import OpError
    with pytest.raises(OpError, match="no field"):
        run_op("env.post", fields={"bloom_intensty": 1})


def test_captures_and_remove(ue, fmb):
    run_op("env.reflection_capture", label="Room", shape="box", loc=[0, 0, 150], extent_cm=[400, 300, 150])
    assert ue.actor("Room").get_actor_scale3d() == ue.Vector(400, 300, 150)
    assert run_op("env.reflection_capture", label="Room", shape="box", loc=[0, 0, 150],
                  extent_cm=[400, 300, 150])["changed"] is False
    run_op("env.fog")
    assert run_op("env.remove", parts=["fog"])["removed"] == ["Env_Fog"]
    assert run_op("env.remove", parts=["fog"])["changed"] is False


SPEC = {"kind": "environment", "version": 1, "name": "studio", "preset": "interior_day",
        "sun": {"time": "16:30", "lat": 19.07, "lon": 72.88, "date": "2026-11-05", "tz": 5.5},
        "clouds": {"bottom_km": 2},
        "lights": {"Window": {"kind": "rect", "loc": [-250, 200, 150], "look_at": [0, 0, 120], "nits": 2000,
                              "width_cm": 120, "height_cm": 150}},
        "practicals": {"Lamp": {"type": "lamp", "loc": [-200, -150, 120]},
                       "Down": {"type": "downlight", "loc": [0, 0, 290]}},
        "rigs": {"Host": {"subject": "Host", "camera": "Cam", "preset": "three_point", "key_lux": 900}},
        "channels": {"Host": [0, 1]},
        "reflection_captures": {"RoomCap": {"shape": "sphere", "loc": [0, 0, 150], "radius_cm": 800}},
        "cvars": {"r.HairStrands.SkyLighting": 0},
        "moods": {"night": {"sun": False, "moon": {}, "exposure": {"ev100": 4}, "grade": {"preset": "moonlight"},
                            "practicals": {"Lamp": {"type": "lamp", "loc": [-200, -150, 120], "scale": 2}}}}}


def test_apply_converges_and_switches_mood(ue, fmb):
    ue.spawn("SkeletalMeshActor", label="Host", extent=(30, 30, 90))
    ue.spawn("CineCameraActor", label="Cam", location=ue.Vector(300, 0, 150))
    r = run_op("env.apply", spec=SPEC)
    assert r["changed"] and r["converged"], r["remaining"]
    assert {"Env_Sun", "Env_Atmosphere", "Env_SkyLight", "Env_Fog", "Env_Post", "Env_Clouds", "Window", "Lamp",
            "Host_Key", "Host_Fill", "Host_Rim", "RoomCap"} <= set(labels(ue))
    assert run_op("env.plan", spec=SPEC)["steps"] == []
    again = run_op("env.apply", spec=SPEC)
    assert again["steps"] == [] and again["changed"] is False
    n = run_op("env.mood", mood="night", spec_name="studio")
    assert n["converged"], n["remaining"]
    assert "Env_Sun" not in labels(ue) and "Env_Moon" in labels(ue)
    assert run_op("env.describe")["exposure"]["ev100"] == pytest.approx(4.0, abs=1e-3)
    back = run_op("env.mood", spec_name="studio")
    assert back["converged"] and "Env_Sun" in labels(ue)
    # moving the subject re-plans the rig only
    ue.actor("Host").set_actor_location(ue.Vector(50, 0, 0))
    assert [s["op"] for s in run_op("env.plan", spec=SPEC)["steps"]] == ["light.rig"]
    assert ue.dialogs == []


def test_apply_prunes_only_its_own(ue, fmb):
    ue.spawn("SkeletalMeshActor", label="Host", extent=(30, 30, 90))
    ue.spawn("CineCameraActor", label="Cam", location=ue.Vector(300, 0, 150))
    ue.spawn("PointLight", label="SetDressingLight")
    run_op("env.apply", spec=SPEC)
    smaller = {**SPEC, "practicals": {}, "rigs": {}, "fog": False}
    r = run_op("env.apply", spec=smaller)
    assert r["converged"], r["remaining"]
    assert "Lamp" not in labels(ue) and "Host_Key" not in labels(ue) and "Env_Fog" not in labels(ue)
    assert "SetDressingLight" in labels(ue) and "Window" in labels(ue)


def test_apply_bad_spec_changes_nothing(ue, fmb):
    from fmbridge.errors import OpError
    before = labels(ue)
    with pytest.raises(OpError) as e:
        run_op("env.apply", spec={"kind": "environment", "name": "x", "fogg": {}})
    assert e.value.code == "bad_args" and "did you mean 'fog'" in str(e.value)
    assert labels(ue) == before


def test_presets_and_schema(ue, fmb):
    p = run_op("env.presets")
    assert "interior_day" in p["environment"] and "rembrandt" in p["rigs"] and "candle" in p["practicals"]
    assert run_op("env.schema", kind="lighting")["properties"]["kind"] == {"const": "lighting"}


def test_check_reads_a_png(ue, fmb, tmp_path):
    from fmbridge.envlib import stats
    stats.write_png(str(tmp_path / "dark.png"), 4, 4, [(0.02, 0.02, 0.02)] * 16)
    r = run_op("env.check", png=str(tmp_path / "dark.png"))
    assert r["pass"] is False and any(i["code"] == "env.exposure_mean" for i in r["issues"])
    stats.write_png(str(tmp_path / "ok.png"), 4, 4, [(0.45, 0.45, 0.45)] * 16)
    assert run_op("env.check", png=str(tmp_path / "ok.png"))["pass"] is True


def test_meter_through_a_camera(ue, fmb):
    ue.spawn("CineCameraActor", label="Cam", location=ue.Vector(300, 0, 150))
    lum = 0.125 * 2 ** 9  # a scene metering EV100 9

    class S:
        def __init__(self, v):
            self.r = self.g = self.b = v

    def read(world, rt, normalize=True):
        return [S(0.45 if normalize else lum)] * 16
    ue.stub("RenderingLibrary.read_render_target_raw", read)
    ue.RenderingLibrary.read_render_target_raw = staticmethod(read)
    run_op("env.exposure", mode="manual", ev100=9.0)
    m = run_op("env.meter", camera="Cam")
    assert m["scene"]["metered_ev100"] == pytest.approx(9.0, abs=1e-3)
    assert m["scene"]["stops_over"] == pytest.approx(0.0, abs=1e-3) and m["display"]["mean"] == pytest.approx(0.45, abs=0.01)
    assert "Env_Meter" not in labels(ue)


def test_env_preset_builds_and_switches(ue, fmb):
    r = run_op("env.preset", name="exterior_golden", owner="sky")
    assert r["converged"] and ue.actor("Env_Clouds") is not None
    r = run_op("env.preset", name="studio_black", owner="sky")
    assert r["converged"] and ue.actor("Env_Sun") is None and ue.actor("Env_Atmosphere") is None
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("env.preset", name="exterior_goldn")
    assert e.value.candidates[0] == "exterior_golden"
