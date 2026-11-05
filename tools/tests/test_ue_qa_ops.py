"""WP10 ops (view.*, qa.*) against the fake engine: ext_qa's scene capture draws actors' bounds boxes, so stills,
framing boxes, depth layers and line traces agree with each other."""
import json
import os

import pytest

from fakeunreal import run_op

from test_ue_qa import body  # the standing-figure bones


def character(ue, label="Ada", at=(0.0, 0.0, 0.0), parts=()):
    bones = body(at)
    a = ue.spawn("SkeletalMeshActor", label, location=ue.Vector(at[0], at[1], at[2] + 90), extent=(25, 25, 90))
    ue.pose(a, bones)
    for p in parts:
        a.add_component(ue.SkeletalMeshComponent, p)
    return a


def cine(ue, label, loc, look_at, focal=35.0):
    from fmbridge.qa import framing
    r = framing.look_at(loc, look_at)
    cam = ue.spawn("CineCameraActor", label, location=ue.Vector(*loc), rotation=ue.Rotator(**r))
    comp = cam.get_cine_camera_component()
    fb = comp.get_editor_property("filmback")
    fb.set_editor_property("sensor_width", 36.0)
    fb.set_editor_property("sensor_height", 20.25)
    comp.set_editor_property("current_focal_length", focal)
    return cam


@pytest.fixture
def scene(ue, fmb):
    floor = ue.spawn("StaticMeshActor", "Floor", location=ue.Vector(0, 0, -5), extent=(600, 600, 5))
    floor._props["fake_color"] = (90, 80, 70)
    character(ue)
    cine(ue, "CamWide", [600, 0, 100], [0, 0, 90])
    cine(ue, "CamClose", [160, 0, 150], [0, 0, 150], focal=50)
    return ue


def rig_gone(ue):
    return ue.actor("FMQA_Capture") is None


# --- view ----------------------------------------------------------------------------------------------------------

def test_still_from_camera(scene, tmp_path):
    out = str(tmp_path / "a.png")
    r = run_op("view.still", out=out, camera="CamWide", width_px=96, height_px=54, warmup=3, guides=["thirds"])
    assert os.path.isfile(out) and (r["width"], r["height"]) == (96, 54) and "alpha_dropped" not in r
    assert r["camera_info"]["fov"] == pytest.approx(54.43, abs=0.01) and r["mode"] == "capture"
    assert os.path.isfile(r["guides_path"])
    assert len(scene.called("SceneCaptureComponent2D.capture_scene")) == 4  # 3 warm-up + the kept one
    assert rig_gone(scene)
    from fmbridge.qa import image
    img = image.read(out)
    assert img.size == (96, 54) and image.mean_rgb(img) != (0, 0, 0)


def test_still_adhoc_and_errors(scene, tmp_path):
    from fmbridge.errors import OpError
    r = run_op("view.still", out=str(tmp_path / "b.png"), loc=[300, 300, 200], look_at=[0, 0, 100], width_px=32,
               height_px=18, warmup=0)
    assert r["camera"] == "adhoc" and r["camera_info"]["fov"] == 40.0
    with pytest.raises(OpError) as e:
        run_op("view.still", out=str(tmp_path / "c.png"), camera="CamWid")
    assert e.value.code == "not_found" and "CamWide" in e.value.candidates
    with pytest.raises(OpError) as e:
        run_op("view.still", out=str(tmp_path / "c.png"))
    assert e.value.code == "bad_args"
    with pytest.raises(OpError):
        run_op("view.still", out=str(tmp_path / "c.png"), camera="Floor")
    with pytest.raises(OpError) as e:
        run_op("view.still", out=str(tmp_path / "c.png"), camera="CamWide", mode="mrq")
    assert e.value.code in ("unsupported", "bad_args")
    assert rig_gone(scene)


def test_still_rt_format_names(scene, tmp_path):
    """Python spells the formats in upper case (RTF_RGBA8_SRGB), any case is taken; a float target would export EXR
    bytes into the .png (ExportRenderTarget picks by format), so a still refuses it."""
    from fmbridge.errors import OpError
    r = run_op("view.still", out=str(tmp_path / "s.png"), camera="CamWide", width_px=32, height_px=18, warmup=0,
               rt_format="rtf_rgba8_srgb")
    assert open(r["path"], "rb").read(4) == b"\x89PNG"
    for bad in ("RTF_RGBA16f", "RTF_RGBA32F", "RGBA8_LINEAR"):
        with pytest.raises(OpError) as e:
            run_op("view.still", out=str(tmp_path / "f.png"), camera="CamWide", width_px=32, height_px=18,
                   rt_format=bad)
        assert e.value.code == "bad_args" and "RTF_RGBA8" in e.value.candidates
    assert rig_gone(scene)


def test_turntable_and_sheet(scene, tmp_path):
    r = run_op("view.turntable", target="Ada", out_dir=str(tmp_path / "tt"), views=4, width_px=48, height_px=48,
               warmup=0, isolate=True)
    assert [v["yaw"] for v in r["views"]] == [0, 90, 180, 270]
    assert all(os.path.isfile(v["path"]) for v in r["views"]) and os.path.isfile(r["sheet"])
    assert rig_gone(scene)
    s = run_op("view.sheet", images=[v["path"] for v in r["views"]], out=str(tmp_path / "s.png"),
               statuses=["ok", "warn"], title="ada")
    assert s["cells"] == 4 and s["changed"] is True and os.path.isfile(s["path"])
    from fmbridge.errors import OpError
    with pytest.raises(OpError):
        run_op("view.sheet", images=[str(tmp_path / "nope.png")], out=str(tmp_path / "x.png"))


def test_overlay_op(scene, tmp_path):
    src = run_op("view.still", out=str(tmp_path / "a.png"), camera="CamWide", width_px=64, height_px=36, warmup=0)
    o = run_op("view.overlay", image=src["path"], out=str(tmp_path / "o.png"), guides=["thirds", "safe"],
               boxes=[{"box": [0.4, 0.1, 0.6, 0.9], "label": "Ada"}], caption="hi")
    assert os.path.isfile(o["path"]) and o["width"] == 64
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("view.overlay", image=src["path"], out=str(tmp_path / "o.png"), guides=["bogus"])
    assert e.value.code == "bad_args"


def test_view_camera_projection(scene):
    r = run_op("view.camera", camera="CamWide", points={"origin": [0, 0, 90], "behind": [900, 0, 90]},
               actors=["Ada"])
    assert r["points"]["origin"]["u"] == pytest.approx(0.5, abs=0.01) and r["points"]["origin"]["in_frame"]
    assert r["points"]["behind"]["u"] is None and not r["points"]["behind"]["in_frame"]
    assert r["actors"]["Ada"]["in_frame"] == 1.0
    assert "aspect_mismatch" not in r


# --- qa: images ----------------------------------------------------------------------------------------------------

def test_qa_image_and_compare(scene, tmp_path):
    a = run_op("view.still", out=str(tmp_path / "a.png"), camera="CamWide", width_px=96, height_px=54, warmup=0)
    r = run_op("qa.image", image=a["path"])
    assert set(r) >= {"pass", "issues", "metrics"} and "exposure" in r["metrics"]
    from fmbridge.qa import image
    black = image.write(image.solid(32, 18, (0, 0, 0)), str(tmp_path / "black.png"))
    bad = run_op("qa.image", image=black)
    assert bad["pass"] is False and bad["issues"][0]["code"] == "image.flat"
    ex = run_op("qa.exposure", image=a["path"], target_stops=[5, 6], regions={"mid": [0.4, 0.2, 0.6, 0.8]})
    assert len(ex["metrics"]["histogram"]) == 32 and set(ex["metrics"]["regions"]) == {"mid"}
    assert any(i["code"] == "exposure.under" for i in ex["issues"])
    c = run_op("qa.compare", image=a["path"], reference=a["path"], out_diff=str(tmp_path / "d.png"))
    assert c["pass"] and c["metrics"]["ssim"] == pytest.approx(1.0) and os.path.isfile(c["diff"])
    b = run_op("view.still", out=str(tmp_path / "b.png"), camera="CamClose", width_px=96, height_px=54, warmup=0)
    c2 = run_op("qa.compare", image=b["path"], reference=a["path"], min_ssim=0.99)
    assert c2["issues"] and c2["issues"][0]["code"] == "compare.differs"


# --- qa: framing ---------------------------------------------------------------------------------------------------

def test_qa_framing(scene, tmp_path):
    wide = run_op("qa.framing", subjects=["Ada"], camera="CamWide", expect={"size": ["LS", "MLS"]}, width_px=96, height_px=54,
                  still_out=str(tmp_path / "f.png"))
    sub = wide["metrics"]["subjects"]["Ada"]
    assert sub["size"]["size"] in ("LS", "MLS") and wide["pass"]
    assert not any(i["code"] == "framing.size" for i in wide["issues"])
    assert os.path.isfile(wide["still"])
    close = run_op("qa.framing", subjects=["Ada"], camera="CamClose", expect={"Ada": {"size": "LS"}})
    assert any(i["code"] == "framing.size" for i in close["issues"])
    assert all(i.get("camera") == "CamClose" for i in close["issues"])
    from fmbridge.errors import OpError
    with pytest.raises(OpError):
        run_op("qa.framing", subjects=[], camera="CamWide")


def test_qa_framing_bounds_subject(scene, ue):
    ue.spawn("StaticMeshActor", "Lamp", location=ue.Vector(0, 260, 60), extent=(20, 20, 60))
    r = run_op("qa.framing", subjects=["Lamp"], camera="CamClose")
    assert r["issues"] and r["issues"][0]["code"] in ("framing.out_of_frame", "framing.cut")


# --- qa: meshes ----------------------------------------------------------------------------------------------------

def test_qa_penetration(ue, fmb, tmp_path):
    a = character(ue, parts=("Body", "Face", "Torso", "Legs", "Feet"))
    comps = {c.get_name(): c for c in a.get_components_by_class(ue.PrimitiveComponent)}

    def torso(u, v):
        return 100.0 if 0.3 <= u <= 0.7 and 0.3 <= v <= 0.7 else None

    def skin(u, v):
        if 0.45 <= u <= 0.55 and 0.45 <= v <= 0.55:
            return 98.0  # pokes through
        return 101.0 if 0.25 <= u <= 0.75 and 0.25 <= v <= 0.75 else None

    comps["Torso"]._props["fake_depth"] = torso
    comps["Body"]._props["fake_depth"] = skin
    r = run_op("qa.penetration", label="Ada", views=2, size_px=40, out_dir=str(tmp_path / "pen"))
    assert r["pass"] is False
    assert r["metrics"]["worst_fraction"] > 0.02
    codes = [i["code"] for i in r["issues"]]
    assert "mesh.penetration" in codes
    v = r["metrics"]["views"]["yaw000"]
    assert v["worst_cm"] == pytest.approx(2.0) and os.path.isfile(v["still"])
    assert ue.actor("FMQA_Capture") is None
    comps["Body"]._props["fake_depth"] = lambda u, v: 101.0 if 0.25 <= u <= 0.75 and 0.25 <= v <= 0.75 else None
    ok = run_op("qa.penetration", label="Ada", views=1, size_px=24)
    assert ok["pass"] and not [i for i in ok["issues"] if i["code"] == "mesh.penetration"]
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("qa.penetration", label="Ada", body=["Skin"], views=1)
    assert e.value.code == "not_found" and "Body" in e.value.candidates
    parts = run_op("qa.parts", label="Ada")
    assert {c["name"] for c in parts["components"]} >= {"Body", "Torso"}


def test_qa_floating_and_overlaps(ue, fmb):
    ue.spawn("StaticMeshActor", "Floor", location=ue.Vector(0, 0, -5), extent=(600, 600, 5))
    ue.spawn("StaticMeshActor", "Table", location=ue.Vector(0, 0, 40), extent=(60, 40, 40))
    ue.spawn("StaticMeshActor", "Vase", location=ue.Vector(0, 0, 96), extent=(5, 5, 10))  # bottom 86: 6 cm up
    ue.spawn("StaticMeshActor", "Chair", location=ue.Vector(50, 0, 40), extent=(25, 25, 40))  # sunk into the table
    ue.spawn("StaticMeshActor", "Pendant", location=ue.Vector(300, 300, 250), extent=(10, 10, 10))
    fl = run_op("qa.floating", ignore=["Floor"])
    gaps = fl["metrics"]["gaps"]
    assert gaps["Vase"] == pytest.approx(6.0) and gaps["Table"] == pytest.approx(0.0)
    vase = next(i for i in fl["issues"] if i.get("subject") == "Vase")
    assert vase["code"] == "mesh.floating" and "level.move" in vase["fix"]
    assert next(i for i in fl["issues"] if i.get("subject") == "Pendant")["code"] == "mesh.floating"
    only = run_op("qa.floating", labels=["Table"])
    assert only["issues"] == [] and only["pass"]
    ov = run_op("qa.overlaps", ignore=["Floor"])
    assert any({"Table", "Chair"} == set(p[:2]) for p in ov["metrics"]["pairs"])
    assert not any("Vase" in p[:2] for p in ov["metrics"]["pairs"])
    ov2 = run_op("qa.overlaps", ignore=["Floor"], ignore_pairs=[["Chair", "Table"]])
    assert ov2["metrics"]["pairs"] == [] and ov2["pass"]


def test_qa_floating_and_overlaps_leave_out_cameras_and_lights(ue, fmb):
    """A camera's bounds take in its editor mesh proxy (day 1: the demo's cine cameras sank into the desk)."""
    ue.spawn("StaticMeshActor", "Floor", location=ue.Vector(0, 0, -5), extent=(600, 600, 5))
    ue.spawn("StaticMeshActor", "Desk", location=ue.Vector(0, 0, 40), extent=(60, 40, 40))
    cam = ue.spawn("CineCameraActor", "CAM_S1", location=ue.Vector(20, 0, 60), extent=(80, 80, 80))
    cam.add_component(ue.StaticMeshComponent, "CameraMesh")
    lamp = ue.spawn("PointLight", "Key", location=ue.Vector(0, 0, 150), extent=(10, 10, 10))
    lamp.add_component(ue.StaticMeshComponent, "Bulb")
    ov = run_op("qa.overlaps", ignore=["Floor"])
    assert ov["metrics"]["pairs"] == [] and ov["pass"]
    assert set(run_op("qa.floating", ignore=["Floor"])["metrics"]["gaps"]) == {"Desk"}
    named = run_op("qa.overlaps", labels=["Desk", "CAM_S1"])  # named, they are still checked
    assert any({"Desk", "CAM_S1"} == set(p[:2]) for p in named["metrics"]["pairs"])


# --- qa: continuity ------------------------------------------------------------------------------------------------

def test_snapshot_and_diff(scene, ue, tmp_path):
    p = str(tmp_path / "before.json")
    snap = run_op("qa.snapshot", out=p)
    assert "Ada" in snap["actors"] and json.load(open(p))["meta"]["count"] == len(snap["actors"])
    assert snap["actors"]["CamWide"]["props"]["current_focal_length"] == 35.0
    ue.actor("Ada").set_actor_location(ue.Vector(30, 0, 90))
    ue.spawn("PointLight", "Practical", location=ue.Vector(0, 100, 200))
    d = run_op("qa.diff", before=p)
    assert d["metrics"]["added"] == ["Practical"] and "Ada" in d["metrics"]["changed"]
    assert d["pass"] and all(i["severity"] == "info" for i in d["issues"])
    from fmbridge.errors import OpError
    with pytest.raises(OpError):
        run_op("qa.diff", before=str(tmp_path / "missing.json"))


# --- qa: review ----------------------------------------------------------------------------------------------------

def test_review_sequence(scene, fmb, monkeypatch, tmp_path):
    scrubs = []
    monkeypatch.setitem(fmb._OPS, "seq.cuts", lambda path: [["CamWide", 0, 48], ["CamClose", 48, 96]])
    monkeypatch.setitem(fmb._OPS, "seq.scrub", lambda path, frame: scrubs.append(frame) or frame)
    r = run_op("qa.review", sequence="/Game/Seq/S010", out_dir=str(tmp_path / "rev"), per_shot=2, width_px=96,
               height_px=54, expect={"Ada": {"size": ["LS", "MLS"]}}, ignore=["Floor"])
    assert r["metrics"]["frames"].keys() == {"0", "47", "48", "95"}
    assert scrubs and 47 in scrubs
    rep = json.load(open(r["report"]))
    assert rep["verdict"] == r["verdict"] and len(rep["panels"]) == 4
    assert os.path.isfile(r["image"])
    assert any(i["code"] == "framing.size" and i["frame"] == 48 for i in r["issues"])  # the close-up is not an LS
    assert r["summary"] and r["summary"][0].startswith("[")
    assert scene.actor("FMQA_Capture") is None


def test_review_camera_only_and_errors(scene, tmp_path):
    r = run_op("qa.review", camera="CamWide", out_dir=str(tmp_path / "rv"), width_px=64, height_px=36,
               checks=["image", "framing"])
    assert len(r["metrics"]["frames"]) == 1 and os.path.isfile(r["image"])
    from fmbridge.errors import OpError
    with pytest.raises(OpError):
        run_op("qa.review", out_dir=str(tmp_path / "x"))
    with pytest.raises(OpError):
        run_op("qa.review", camera="CamWide", out_dir=str(tmp_path / "x"), checks=["nope"])


def test_still_drops_a_non_opaque_alpha(scene, ue, tmp_path, monkeypatch):
    """A capture whose alpha is not 255 is rewritten as RGB (a viewer would see an empty PNG)."""
    import fakeunreal.ext_qa as ext
    orig = ext._render

    def render(fake, core, comp):
        comp._props["fake_alpha"] = 0.0
        return orig(fake, core, comp)
    monkeypatch.setattr(ext, "_render", render)
    r = run_op("view.still", out=str(tmp_path / "a.png"), camera="CamWide", width_px=48, height_px=27, warmup=0)
    assert r.get("alpha_dropped") is True
    from fmbridge.qa import image
    assert image.read(r["path"]).c == 3
