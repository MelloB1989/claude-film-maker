"""The cloth ops (cloth.*, qa.cloth) against the fake engine (fakeunreal/ext_cloth.py): setup converges and writes
maps, config and component settings; qa.cloth tells a living garment from armour and catches a cold start;
render_check finds missing warm-up; cache sets up a manager."""
import math

import pytest

from fakeunreal import run_op

from test_ue_cloth import HEADS, PARENTS, tee

SEQ = "/Game/Reel/SEQ_Test"


def ref_bones():
    out = {}
    for b, h in HEADS.items():
        p = PARENTS[b]
        ph = HEADS[p] if p else (0, 0, 0)
        out[b] = ((h[0] - ph[0], h[1] - ph[1], h[2] - ph[2]), p)
    return out


@pytest.fixture
def host(ue, fmb):
    """A placed character with Body and a Tee garment (skeletal mesh with a reference skeleton), and a sequence."""
    a = ue.spawn("Actor", "Host")
    body = a.add_component(ue.SkeletalMeshComponent, "Body")
    body.set_skeletal_mesh_asset(ue.put_asset("/Game/H/SKM_Body", ue.SkeletalMesh("SKM_Body")))
    phys = ue.put_asset("/Game/H/PA_Body", ue.PhysicsAsset("PA_Body"))
    body.get_skeletal_mesh_asset().set_editor_property("physics_asset", phys)
    body.set_editor_property("physics_asset_override", None)
    tee_c = a.add_component(ue.SkeletalMeshComponent, "Tee")
    m = ue.put_asset("/Game/H/SKM_Tee", ue.SkeletalMesh("SKM_Tee"))
    m._props["ref_bones"] = ref_bones()
    m._props["mesh_clothing_assets"] = []
    tee_c.set_skeletal_mesh_asset(m)
    tee_c.set_editor_property("leader_pose_component", None)
    ue.put_asset(SEQ, ue.LevelSequence("SEQ_Test"))
    ue.cloth_rest = tee()
    ue.FMCloth  # noqa: B018 - installed
    return a


def test_presets_op_and_typos(fmb):
    r = run_op("cloth.presets")
    assert set(r) == {"cotton_tee", "overshirt_light", "trousers"} and r["cotton_tee"]["max_cm"] == 3.0
    with pytest.raises(Exception) as e:
        run_op("cloth.presets", name="cotton")
    assert e.value.code == "bad_args"


def test_setup_needs_the_plugin(ue, host):
    ue.FMCloth = None
    with pytest.raises(Exception) as e:
        run_op("cloth.setup", label="Host", component="Tee", preset="cotton_tee")
    assert e.value.code == "unsupported" and "plugin-build FMCloth" in e.value.hint


def test_setup_refuses_the_body_and_bad_presets(host):
    with pytest.raises(Exception) as e:
        run_op("cloth.setup", label="Host", component="Body", preset="cotton_tee")
    assert e.value.code == "bad_args"
    with pytest.raises(Exception) as e:
        run_op("cloth.setup", label="Host", component="Tee", preset="silk")
    assert e.value.code == "bad_args" and "cotton_tee" in e.value.candidates


def test_setup_paints_configures_and_converges(ue, host):
    assert run_op("cloth.describe", label="Host")["skinned_only"] == ["Tee"]
    r = run_op("cloth.setup", label="Host", component="Tee", preset="cotton_tee")
    assert r["changed"] and r["points"] == len(tee()) and r["physics_asset"] == "/Game/H/PA_Body"
    assert r["maps"]["torso"]["max_cm"] == pytest.approx(3.0) and r["readback_max_cm"] == pytest.approx(3.0)
    assert r["config"]["missing"] == []
    assert r["config"]["set"]["density"] == 0.15
    assert r["config"]["set"]["collision_thickness"] == 0.4 and r["config"]["set"]["use_ccd"] is False  # C++ names
    assert r["config"]["set"]["linear_velocity_scale"] is not None and r["config"]["set"]["damping_coefficient"] == 0.06
    assert "bending_stiffness_weighted" not in r["config"]["set"]          # no Python type for weighted values:
    assert r["config"]["interactor"]["material"] == [1.0, 0.08, 1.0]      # set through the clothing interactor
    assert ue.called("ChaosClothingInteractor.set_material_linear")[-1][0] == (1.0, 0.08, 1.0)
    assert r["config"]["interactor"]["aerodynamics"] == [0.035, 0.035] and "error" not in r["config"]["interactor"]
    assert r["config"]["set"]["iteration_count"] == 2
    assert r["settings"]["teleport_distance_threshold"] == 50.0 and r["settings"]["reset_after_teleport"] is True
    run_op("cloth.setup", label="Host", component="Tee", preset="cotton_tee")
    assert len(ue.called("FMCloth.create")) == 1                       # converged: one clothing asset
    st = run_op("cloth.settings", label="Host")                          # a respawn: the interactor values again
    assert st["garments"]["Tee"]["interactor"]["material"] == [1.0, 0.08, 1.0]
    mesh = ue.assets["/Game/H/SKM_Tee"]
    assert len(mesh._props["mesh_clothing_assets"]) == 1
    assert ue.EditorAssetLibrary.get_metadata_tag(mesh, "FMClothPreset") == "cotton_tee"
    d = run_op("cloth.describe", label="Host", component="Tee")
    assert d["skinned_only"] == [] and d["garments"]["Tee"]["clothing"][0]["physics_asset"] == "/Game/H/PA_Body"
    assert run_op("cloth.remove", label="Host", component="Tee")["changed"]
    assert run_op("cloth.describe", label="Host")["skinned_only"] == ["Tee"]


def swing(f, i, p):
    w = max(0.0, (130 - p[2]) / 35.0) if abs(p[1]) < 18 else max(0.0, (abs(p[1]) - 20) / 16.0)
    return (1.5 * w * math.sin(f / 4.0), 0.0, -0.3 * w)


def qa(ue, **kw):
    args = dict(label="Host", component="Tee", sequence=SEQ, start=1000, end=1040)
    args.update(kw)
    return run_op("qa.cloth", **args)


def test_qa_cloth_without_clothing_is_armour(ue, host):
    r = qa(ue)
    assert not r["pass"] and r["issues"][0]["code"] == "cloth.no_clothing"
    assert "cloth.setup" in r["issues"][0]["fix"]


def test_qa_cloth_passes_a_living_garment(ue, host):
    run_op("cloth.setup", label="Host", component="Tee", preset="cotton_tee")
    ue.cloth_body = lambda f: (0.5 * (f - 1000), 0.0, 0.0)
    ue.cloth_motion = swing
    r = qa(ue)
    assert r["pass"], r["issues"]
    assert r["metrics"]["zones"]["hem"]["motion_cm"] > 0.3 and r["preset"] == "cotton_tee"
    assert r["settle_frames"] == 36


def test_qa_cloth_fails_armour_that_never_moves(ue, host):
    run_op("cloth.setup", label="Host", component="Tee", preset="cotton_tee")
    ue.cloth_body = lambda f: (0.5 * (f - 1000), 0.0, 0.0)
    ue.cloth_motion = lambda f, i, p: (0.0, 0.0, -0.2 if p[2] < 120 else 0.0)
    r = qa(ue)
    assert "cloth.dead" in {i["code"] for i in r["issues"]} and not r["pass"]


def test_qa_cloth_catches_a_cold_start_without_preroll(ue, host):
    run_op("cloth.setup", label="Host", component="Tee", preset="cotton_tee")
    ue.cloth_body = lambda f: (0.05 * (f - 1000), 0.0, 0.0)
    ue.cloth_motion = lambda f, i, p: (0.0, 0.0, -3.0 * max(0.0, (130 - p[2]) / 35.0) if abs(p[1]) < 18 else 0.0)
    ue.cloth_settle_steps = 8
    r = qa(ue, settle=1)
    assert "cloth.cold_start" in {i["code"] for i in r["issues"]}
    r2 = qa(ue)                   # the preset's settle frames: settled before the first frame
    assert "cloth.cold_start" not in {i["code"] for i in r2["issues"]}


def test_qa_cloth_thresholds_are_checked(host):
    with pytest.raises(Exception) as e:
        qa(None, alive_min=0.1)
    assert e.value.code == "bad_args" and "alive_min_cm" in e.value.candidates


def test_render_check_finds_missing_warmup(fmb):
    chunks = [{"id": "S15", "cut_start": 1080, "start": 1080, "end": 1200, "preroll": 0},
              {"id": "S15b", "cut_start": 1080, "start": 1150, "end": 1200, "preroll": 70},
              {"id": "S16b", "cut_start": 1200, "start": 1210, "end": 1320, "preroll": 10}]
    r = run_op("cloth.render_check", chunks=chunks, warmup_engine=0, warmup_render=32)
    assert r["need"] == 54 and not r["ok"] and r["warmup_engine"] == 22
    ok = {c["id"]: c["ok"] for c in r["chunks"]}
    assert ok == {"S15": False, "S15b": True, "S16b": False}
    assert "render this cut from its start (1200)" in r["chunks"][2]["fix"]
    r = run_op("cloth.render_check", chunks=chunks[:2], warmup_engine=22, warmup_render=32)
    assert r["ok"]
    r = run_op("cloth.render_check", chunks=chunks[:1], warmup_render=32, presets_used=["cotton_tee"])
    assert r["need"] == 36 and not r["ok"] and r["warmup_engine"] == 4      # the final preset's 32 is not enough


def test_cache_sets_up_one_manager(ue, host):
    run_op("cloth.setup", label="Host", component="Tee", preset="cotton_tee")
    r = run_op("cloth.cache", label="Host", mode="record")
    assert r["changed"] and r["observed"] == ["Tee"] and r["collection"] == "/Game/FM/ClothCache/CC_Host"
    r2 = run_op("cloth.cache", label="Host", mode="play")
    assert r2["changed"]
    assert len([a for a in ue.world.actors() if a.get_actor_label() == "ClothCache_Host"]) == 1
    with pytest.raises(Exception):
        run_op("cloth.cache", label="Host", mode="replay")


def test_colours_that_pin_most_of_a_garment_are_not_the_fits_and_are_ignored(ue, host):
    # round 5: her overshirt carried its own vertex colours (G > 0.5 everywhere): every vertex read as pinned (0 cm)
    from fmbridge.clothkit import presets
    from fmbridge.ops import cloth as C
    pts = tee()
    mesh = ue.assets["/Game/H/SKM_Tee"]
    own = C.plan_maps(pts, mesh, presets.get("cotton_tee"), (pts, [(0.8, 0.8, 0.8, 1.0)] * len(pts)))
    assert own["colours"] is False and "ignored" in own["colours_ignored"] and own["problems"] == []
    assert own["maps"]["stats"]["torso"]["max_cm"] == pytest.approx(3.0)
    fit = [(0.4, 1.0 if p[2] >= 145 else 0.0, 0, 1) for p in pts]
    r = C.plan_maps(pts, mesh, presets.get("cotton_tee"), (pts, fit))
    assert r["colours"] is True and r["colours_ignored"] == ""


def test_describe_reports_the_drawn_lod(ue, host):
    host.get_components_by_class(ue.SkeletalMeshComponent)[1].set_editor_property("forced_lod_model", 1)
    d = run_op("cloth.describe", label="Host", component="Tee")["garments"]["Tee"]
    assert d["forced_lod_model"] == 1 and d["drawn_lod"] == 0


def test_settings_keeps_setups_config_overrides_after_a_respawn(ue, host):
    run_op("cloth.setup", label="Host", component="Tee", preset="cotton_tee",
           overrides={"config": {"bending_stiffness_weighted": 0.05}, "zones": {"torso": {"to_cm": 4.0}}})
    st = run_op("cloth.settings", label="Host")
    assert st["garments"]["Tee"]["interactor"]["material"] == [1.0, 0.05, 1.0]
