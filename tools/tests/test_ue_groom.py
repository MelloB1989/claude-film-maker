"""B28 groom.* ops on the fake: describe, per-instance set (groups + hair material params), verify, measure,
asset decimation behind edit_asset, the sky-lighting guard."""
import os

import pytest

from fakeunreal import run_op

from test_ue_qa import body


@pytest.fixture
def ada(ue, fmb):
    a = ue.spawn("SkeletalMeshActor", "Ada", location=ue.Vector(0, 0, 90), extent=(25, 25, 90))
    bones = body()
    bones["eyes"] = [-9.0, 0.0, 171.0]
    ue.pose(a, bones)
    hair = ue.groom(a, "Hair", groups=2)
    hair._props["fake_bounds"] = ([-2, 0, 172], [12, 11, 14])
    face = a.add_component(ue.SkeletalMeshComponent, "Face")
    face._props["fake_bounds"] = ([-2, 0, 162], [10, 9, 14])
    ue.groom(a, "Eyebrows", params={"hairMelanin": 0.5})
    return a


def test_describe(ada):
    d = run_op("groom.describe", label="Ada")
    names = [c["name"] for c in d["components"]]
    assert names == ["Hair", "Eyebrows"]
    hair = d["components"][0]
    assert len(hair["groups"]) == 2 and hair["groups"][0]["width_cm"] == 0.1
    assert hair["groups"][0]["width_cm_override"] is False
    assert hair["materials"][0]["params"]["melanin"] == 0.5 and "hairRedness" in hair["materials"][0]["scalar_names"]
    assert hair["groom"] == "/Game/Hair/GR_Hair.GR_Hair" or hair["groom"].startswith("/Game/Hair/GR_Hair")
    assert d["cvars"]["r.HairStrands.SkyLighting"] == 1


def test_set_converges(ada, ue):
    r = run_op("groom.set", label="Ada", component="Hair", width_cm=0.008, shadow_density=0.6, melanin=0.95,
               redness=0.1, dye=[0.2, 0.1, 0.05])
    assert r["changed"] and set(r["groups"]["Hair"]) == {0, 1}
    assert r["groups"]["Hair"][0]["width_cm"] == [0.1, 0.008]
    assert r["materials"]["Hair"][0]["hairMelanin"] == [0.5, 0.95]
    assert "lost" not in r
    hair = next(c for c in ada.get_components_by_class(ue.GroomComponent) if c.get_name() == "Hair")
    d0 = hair.get_editor_property("groom_groups_desc")[0]
    assert d0.get_editor_property("hair_width") == 0.008 and d0.get_editor_property("hair_width_override") is True
    mid = hair.get_materials()[0]
    assert isinstance(mid, ue.MaterialInstanceDynamic) and mid.get_scalar_parameter_value("hairRedness") == 0.1
    again = run_op("groom.set", label="Ada", component="Hair", width_cm=0.008, shadow_density=0.6, melanin=0.95,
                   redness=0.1)
    assert again["changed"] is False and again["groups"] == {} and again["materials"] == {}
    # the eyebrows were not touched
    brows = next(c for c in ada.get_components_by_class(ue.GroomComponent) if c.get_name() == "Eyebrows")
    assert not isinstance(brows.get_materials()[0], ue.MaterialInstanceDynamic)


def test_set_errors(ada):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("groom.set", label="Ada")
    assert e.value.code == "bad_args"
    with pytest.raises(OpError):
        run_op("groom.set", label="Ada", melanin=1.5)
    with pytest.raises(OpError) as e:
        run_op("groom.set", label="Ada", params={"hairMelanim": 0.2})
    assert e.value.code == "not_found" and "hairMelanin" in e.value.candidates
    with pytest.raises(OpError) as e:
        run_op("groom.set", label="Ada", component="Beard", melanin=0.2)
    assert e.value.code == "not_found"
    with pytest.raises(OpError) as e:
        run_op("groom.set", label="Ada", strand_fraction=0.5)
    assert e.value.code == "bad_args" and "edit_asset" in e.value.message


def test_strand_fraction_edits_the_asset(ada, ue):
    asset = ue.assets["/Game/Hair/GR_Hair"]
    groups = []
    for _ in range(2):
        g = ue.Object("interp")
        ds = ue.Object("decim")
        ds.set_editor_property("curve_decimation", 1.0)
        g.set_editor_property("decimation_settings", ds)
        groups.append(g)
    asset.set_editor_property("hair_groups_interpolation", groups)
    r = run_op("groom.set", label="Ada", component="Hair", strand_fraction=0.5, edit_asset=True)
    assert r["changed"] and r["asset"]["changed"]
    got = asset.get_editor_property("hair_groups_interpolation")[0].get_editor_property("decimation_settings")
    assert got.get_editor_property("curve_decimation") == 0.5


def test_measure_and_set_with_before_after(ada, ue, tmp_path):
    m = run_op("groom.measure", label="Ada", component="Hair", views=2, size_px=32, out_dir=str(tmp_path))
    assert set(m["views"]) == {"front", "back"}
    front = m["views"]["front"]
    assert front["pixels"] > 0 and 0 < front["share_of_head"] <= 1 and os.path.isfile(front["still"])
    assert ue.actor("FMQA_Capture") is None
    r = run_op("groom.set", label="Ada", component="Hair", melanin=0.9, measure_views=1)
    assert "before" in r and "after" in r and "delta" in r
    assert r["before"]["mean"]["share_of_head"] == pytest.approx(r["after"]["mean"]["share_of_head"])


def test_sky_lighting_guard(ada, ue):
    r = run_op("groom.sky_lighting", enable=False)
    assert r["before"] == 1 and r["after"] == 0 and r["changed"] is True
    assert r["render_cvars"] == {"r.HairStrands.SkyLighting": 0}
    again = run_op("groom.sky_lighting", enable=False, measure_label="Ada")
    assert again["changed"] is False and "delta" in again["measure"]


# --- R5: groom.lock / groom.lock_check (her hair shortened at the S17 -> S18 cut) --------------------------------

@pytest.fixture
def her(ue):
    a = ue.spawn("SkeletalMeshActor", "Presenter", location=ue.Vector(0, 0, 90), extent=(25, 25, 90))
    a.add_component(ue.SkeletalMeshComponent, "Body")
    a.add_component(ue.SkeletalMeshComponent, "Face")
    ue.groom(a, "Hair", groups=1)
    ue.groom(a, "Eyebrows")
    # round 4's state: LODSync pinned to 0 (gate g passed) but the hair component is not one LODSync knows
    # (re-created under another name by a re-dress), and the engine's auto LOD cvars as shipped
    ue.lodsync(a, names=("Body", "Face", "Eyebrows"))
    sync = next(c for c in a.get_components_by_class(ue.ActorComponent) if c.get_name() == "LODSync")
    sync.set_editor_property("forced_lod", 0)
    return a


def test_lock_check_catches_round4(her):
    r = run_op("groom.lock_check", labels=["Presenter"])
    assert r["pass"] is False
    txt = "\n".join(r["problems"])
    assert "groom Hair is not in LODSync's components_to_sync" in txt
    assert "r.HairStrands.LODMode is 1.0 (want 0)" in txt and "r.HairStrands.AutoLOD.Bias" in txt
    assert "forced_lod_model 0 (want 1" in txt
    hair = next(g for g in r["actors"]["Presenter"]["grooms"] if g["name"] == "Hair")
    assert hair["groups"][0]["geometry"] == "STRANDS" and hair["lod_mode"] == "DEFAULT"
    brows = next(g for g in r["actors"]["Presenter"]["grooms"] if g["name"] == "Eyebrows")
    assert brows["live_lod"] == 0


def test_lock_then_check_passes(her, ue):
    r = run_op("groom.lock", labels=["Presenter"])
    assert any("components_to_sync+=['Hair']" in c for c in r["changed"])
    assert r["pass"], r["check"]["problems"]
    assert r["render_cvars"] == {"r.HairStrands.LODMode": 0, "r.HairStrands.AutoLOD.Bias": 1.0,
                                 "r.HairStrands.UseCardsInsteadOfStrands": 0}
    # LODSync resolves the added name only on register (the render's world): a note, not a pass on faith
    assert any("not resolved it yet" in n for n in r["check"]["notes"])
    again = run_op("groom.lock", labels=["Presenter"])
    assert again["changed"] == []
    sync = next(c for c in her.get_components_by_class(ue.ActorComponent) if c.get_name() == "LODSync")
    sync.register()
    assert run_op("groom.lock_check", labels=["Presenter"])["actors"]["Presenter"]["grooms"][0]["live_lod"] == 0


def test_lock_refuses_trash_and_cards_lod(her, ue):
    her.add_component(ue.LODSyncComponent, "TRASH_LODSync_0")
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("groom.lock", labels=["Presenter"])
    assert "TRASH_" in e.value.message and "level.open" in e.value.hint
    r = run_op("groom.lock_check", labels=["Presenter"], lod=2)
    assert any("LOD 2 is CARDS, not strands" in p for p in r["problems"])


def test_lock_release(her):
    run_op("groom.lock", labels=["Presenter"])
    r = run_op("groom.lock", labels=["Presenter"], release=True)
    assert r["pass"] and "r.HairStrands.LODMode=1" in r["changed"]


def test_hair_continuity_flags_the_cut(ada, ue, fmb, monkeypatch, tmp_path):
    from test_ue_qa_ops import cine
    cine(ue, "CamMed", [260, 0, 160], [0, 0, 150], focal=35)
    cine(ue, "CamWide", [450, 0, 130], [0, 0, 120], focal=35)
    hair = next(c for c in ada.get_components_by_class(ue.GroomComponent) if c.get_name() == "Hair")
    long_, short = ([-2, 0, 160], [12, 11, 22]), ([-2, 0, 168], [12, 11, 14])  # ends at the chest vs above the neck
    state = {"short_after": None}

    def scrub(path, frame):
        hair._props["fake_bounds"] = short if state["short_after"] is not None and frame >= state["short_after"] \
            else long_
        return frame
    monkeypatch.setitem(fmb._OPS, "seq.cuts", lambda path: [["CamMed", 0, 48], ["CamWide", 48, 96]])
    monkeypatch.setitem(fmb._OPS, "seq.scrub", scrub)
    ok = run_op("qa.hair_continuity", sequence="/Game/Reel/SEQ_Reel", labels=["Ada"], frames=2, width_px=480,
                height_px=270)
    assert ok["pass"], (ok["issues"], ok["characters"]["Ada"]["series"], ok["characters"]["Ada"]["cuts"])
    row = ok["characters"]["Ada"]["cuts"][0]
    assert row["from"] == "CamMed" and row["to"] == "CamWide" and abs(row["reach"][2]) < 0.12
    assert ok["characters"]["Ada"]["series"]["47"]["norm"] == "bones"
    state["short_after"] = 48  # the wide shot draws shorter hair (an LOD switch)
    out = str(tmp_path / "hair.json")
    bad = run_op("qa.hair_continuity", sequence="/Game/Reel/SEQ_Reel", labels=["Ada"], frames=2, width_px=480,
                 height_px=270, out=out)
    assert not bad["pass"] and bad["gate"]["hair.cut_reach_pct"] > 12
    assert any(i["code"] == "hair.cut_jump" and i["frame"] == 48 and "SHORTER" in i["message"] for i in bad["issues"])
    assert os.path.isfile(out) and ue.actor("FMQA_Capture") is None
