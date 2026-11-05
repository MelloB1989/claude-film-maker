"""The camera and shot spec kinds (filmtools.unreal.cam_kind), their schemas, and the examples under
examples/unreal/{camera,shot}: every example validates and resolves with stand-in subjects."""
import json
import sys
from pathlib import Path

import pytest
import yaml

from filmtools.unreal import cam_kind

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "unreal" / "fmbridge"))
from camkit import framing, shotlist  # noqa: E402

SCHEMAS = ROOT / "tools" / "filmtools" / "unreal" / "schemas"


def docs(kind):
    for p in sorted((ROOT / "examples" / "unreal" / kind).glob("*.yaml")):
        for d in yaml.safe_load_all(p.read_text()):
            if d:
                yield p.name, d


def person(name, at, facing):
    return framing.subject_from_bounds(name, (at[0], at[1], 87.5), (20, 20, 87.5), facing)


def test_schemas_agree_with_the_resolver():
    shot = json.loads((SCHEMAS / "shot.schema.json").read_text())
    assert set(shot["properties"]) == shotlist.TOP_KEYS
    item = shot["properties"]["shots"]["items"]
    assert set(item["properties"]) == shotlist.SHOT_KEYS
    assert set(item["properties"]["frame"]["properties"]) == shotlist.FRAME_KEYS
    cam = json.loads((SCHEMAS / "camera.schema.json").read_text())
    assert cam["properties"]["kind"]["const"] == "camera" and cam["additionalProperties"] is False


@pytest.mark.parametrize("name,doc", list(docs("shot")))
def test_shot_examples_resolve(name, doc):
    assert shotlist.validate(doc) == [], name
    subs = {}
    for k, n in enumerate(doc["subjects"]):
        subs[n] = person(n, (0, -90 + 180 * k), (0, 1 - 2 * k, 0))
    r = shotlist.plan(doc, subs)
    assert r["cuts"] and r["range"][1] > r["range"][0]
    assert not [i for i in r["issues"] if i["severity"] == "fail"], (name, r["issues"])


@pytest.mark.parametrize("name,doc", list(docs("camera")))
def test_camera_examples_have_known_keys(name, doc):
    schema = json.loads((SCHEMAS / "camera.schema.json").read_text())
    assert set(doc) <= set(schema["properties"]), name
    assert cam_kind.plan_camera(doc, {"camera": None, "target": {"loc": [1, 2, 3], "rot": {"yaw": 5},
                                                                  "focal": 50, "focus": 200}})


def test_camera_plan_converges():
    spec = {"kind": "camera", "name": "C", "loc": [100, 0, 150], "look_at": [0, 0, 150], "focal_mm": 35,
            "aperture": 2.8, "focus": {"mode": "manual", "distance_cm": 100}}
    steps = cam_kind.plan_camera(spec, {"camera": None})
    assert [s["op"] for s in steps] == ["cam.add", "cam.focus"]
    assert steps[0]["args"]["rot_"]["yaw"] == pytest.approx(180)
    now = {"camera": {"loc": [100, 0, 150], "rot": {"pitch": 0, "yaw": -180, "roll": 0}, "focal": 35, "aperture": 2.8,
                      "filmback": [23.76, 13.365], "filmback_preset": "16:9 Digital Film", "focus_method": "manual",
                      "focus": 100.0, "attached_to": None}}
    assert cam_kind.plan_camera(spec, now) == []
    moved = {"camera": {**now["camera"], "loc": [120, 0, 150]}}
    steps = cam_kind.plan_camera(spec, moved)
    assert steps[0]["op"] == "cam.add" and "loc" in steps[0]["args"] and "focal_mm" not in steps[0]["args"]


def test_camera_framed_and_tracked_plan():
    spec = {"kind": "camera", "name": "C", "frame": {"subjects": ["P"], "size": "MCU"},
            "focus": {"mode": "track", "target": "eyes:P"}, "rig": {"kind": "rail", "points": [[0, 0, 0], [1, 0, 0]]}}
    target = {"loc": [200, -100, 160], "rot": {"pitch": -2, "yaw": 150, "roll": 0}, "focal": 50, "focus": 220}
    steps = cam_kind.plan_camera(spec, {"camera": None, "target": target})
    assert [s["op"] for s in steps] == ["cam.add", "cam.focus", "cam.rig"]
    assert steps[2]["args"]["label"] == "C_Rig"
    now = {"camera": {"loc": target["loc"], "rot": target["rot"], "focal": 50, "aperture": 2.8,
                      "filmback": [23.76, 13.365], "filmback_preset": "16:9 Digital Film", "focus_method": "tracking",
                      "focus": None, "focus_track": {"actor": "P"}, "attached_to": "C_Rig"}}
    assert cam_kind.plan_camera(spec, {"camera": now["camera"], "target": target}) == []
    assert cam_kind._frame_args({"name": "C", "frame": {"subjects": ["P"], "distance_cm": 200}})["focal_mm"] is None


def test_shot_plan_and_timing_file(tmp_path):
    t = tmp_path / "timing.json"
    t.write_text(json.dumps({"kind": "audio", "version": 1, "fps": 24, "lines": [{"id": "L1", "start_frame": 10}]}))
    spec = {"kind": "shot", "name": "s", "sequence": "/Game/S", "timing": str(t), "shots": []}
    steps = cam_kind.plan_shot(spec, {"up_to_date": False})
    assert steps[0]["op"] == "shot.apply" and steps[0]["args"]["spec"]["timing"]["lines"][0]["id"] == "L1"
    assert cam_kind.plan_shot(spec, {"up_to_date": True}) == []
    assert cam_kind.SPEC_KINDS[1]["order"] > cam_kind.SPEC_KINDS[0]["order"]


# --- shot list -> render -> review --------------------------------------------------------------------------------

def _interview():
    return next(d for _, d in docs("shot") if d["name"] == "interview")


def test_shot_table_offline():
    rows = cam_kind.shot_table(_interview())
    assert [r["id"] for r in rows] == ["S1_wide", "S2_host", "S3_guest_over", "S4_host_push"]
    assert rows[0] == {"id": "S1_wide", "camera": "CAM_S1_wide", "start": 0, "end": 32, "size": "WS",
                       "subjects": ["Host", "Guest"]}
    assert rows[2]["size"] == "MCU" and rows[2]["subjects"] == ["Guest"]  # Guest_OTS
    assert all(a["end"] == b["start"] for a, b in zip(rows, rows[1:]))


def test_pipeline_docs_validate_and_order():
    from filmtools.unreal import spec as engine
    out = cam_kind.pipeline_docs(_interview(), "/srv/renders", preset="final", level="/Game/Maps/Set", per_shot=2)
    kinds = engine.kinds()
    assert [d["kind"] for d in out] == ["shot", "render", "qa", "qa", "qa", "qa"]
    for d in out:
        assert engine.validate_doc(d, kinds[d["kind"]]) == [], d["name"]
    assert kinds["shot"].order < kinds["render"].order < kinds["qa"].order
    r = out[1]
    assert r["shots"] == ["CAM_S1_wide", "CAM_S2_host", "CAM_S3_guest_over", "CAM_S4_host_push"]
    assert r["out_dir"] == "/srv/renders/interview/final" and r["preroll"] == "cut"
    rows = {x["id"]: x for x in cam_kind.shot_table(_interview())}
    for q in out[2:]:
        sid = q["name"][len("interview-"):-len("-review")]
        fr = q["review"]["frames"]
        assert len(fr) == 2 and all(rows[sid]["start"] <= f < rows[sid]["end"] for f in fr)
    assert out[3]["review"]["expect"] == {"Host": {"size": ["MCU"]}}


def test_shotlist_cli(tmp_path, capsys):
    import argparse
    from filmtools.unreal import cli_shotlist
    import yaml
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    cli_shotlist.register(sub)
    spec = ROOT / "examples" / "unreal" / "shot" / "interview.yaml"
    assert cli_shotlist.dispatch(p.parse_args(["shotlist", "table", str(spec)]))
    assert "CAM_S3_guest_over" in capsys.readouterr().out
    out = tmp_path / "pipe.yaml"
    a = p.parse_args(["shotlist", "pipeline", str(spec), "--out", "/srv/r", "--h264", "-o", str(out)])
    assert cli_shotlist.dispatch(a)
    docs_ = list(yaml.safe_load_all(out.read_text()))
    assert docs_[1]["outputs"] == [{"kind": "h264", "crf": 18}] and len(docs_) == 6
    assert not cli_shotlist.dispatch(argparse.Namespace(cmd="doctor"))
