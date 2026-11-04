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
