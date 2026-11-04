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
