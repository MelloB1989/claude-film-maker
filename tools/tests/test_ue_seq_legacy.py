"""The older seq.* ops (ops/seq.py) pinned: their return values, and the sequence they leave behind read back through
seq.describe, compared with a golden snapshot taken from the implementation before it became a layer over seqcore.
Regenerate the snapshot only on purpose: SEQ_LEGACY_REGEN=1 pytest tests/test_ue_seq_legacy.py."""
import json
import os
from pathlib import Path

import pytest

from fakeunreal import run_op

GOLDEN = Path(__file__).parent / "data" / "seq_legacy_golden.json"
SEQ = "/Game/L/SEQ_Legacy"


@pytest.fixture
def scene(ue):
    host = ue.spawn("SkeletalMeshActor", "Host", location=ue.Vector(0, 0, 0))
    host.add_component(ue.SkeletalMeshComponent, "Body")
    host.add_component(ue.SkeletalMeshComponent, "Face")
    ue.spawn("StaticMeshActor", "Sign", location=ue.Vector(0, 300, 100))
    earring = ue.spawn("StaticMeshActor", "Earring")
    earring.attach_to_actor(host)
    ue.spawn("CineCameraActor", "CamA", location=ue.Vector(-400, 0, 160))
    ue.spawn("CineCameraActor", "CamB", location=ue.Vector(0, -400, 160))
    light = ue.spawn("PointLight", "Key")
    light._props["point_light_component"]._props["intensity"] = 5.0
    light._props["point_light_component"]._props["light_color"] = ue.Color(r=255, g=255, b=255, a=255)
    ue.add_asset("/Game/A/Idle", "AnimSequence", sequence_length=4.0)
    ue.add_asset("/Game/A/Talk", "AnimSequence", sequence_length=2.0)
    ue.add_asset("/Game/Au/L1", "SoundWave", duration=1.5)
    ue.add_asset("/Game/MPC", "MaterialParameterCollection")
    return ue


def scenario() -> dict:
    """Every mutating legacy op once (some twice, to pin idempotency), returning their results."""
    r = {}
    r["new"] = run_op("seq.new", path=SEQ, start=0, end=120, fps=24)
    r["new_again"] = run_op("seq.new", path=SEQ, start=0, end=144, fps=24)
    r["key_transform"] = run_op("seq.key_transform", path=SEQ, label="CamA",
                                keys=[[0, [-400, 0, 160], {"yaw": 0}], [48, [-300, 0, 160], [0, 0, 100], "linear"],
                                      [96, [-200, 50, 160], {"pitch": -10, "yaw": 20}, "constant"]])
    r["key_float"] = run_op("seq.key_float", path=SEQ, label="Key", prop="Intensity",
                            component="point_light_component", keys=[[0, 5], [24, 10, "linear"]])
    r["key_float_cam"] = run_op("seq.key_float", path=SEQ, label="CamA", prop="CurrentFocalLength",
                                component="CameraComponent", keys=[[0, 35]])
    r["key_float_again"] = run_op("seq.key_float", path=SEQ, label="Key", prop="Intensity",
                                  component="point_light_component", keys=[[0, 6], [24, 12, "linear"]])
    r["key_color"] = run_op("seq.key_color", path=SEQ, label="Key", prop="LightColor",
                            component="point_light_component", keys=[[0, [1, 0.5, 0.25]]])
    r["key_visible"] = run_op("seq.key_visible", path=SEQ, label="Host", keys=[[0, True], [100, False]],
                              attached=True)
    r["key_material"] = run_op("seq.key_material", path=SEQ, label="Sign", param="Glow", keys=[[0, 0], [24, 1]])
    r["key_material2"] = run_op("seq.key_material", path=SEQ, label="Sign", param="Tint", keys=[[0, [1, 0, 0]]])
    r["key_collection"] = run_op("seq.key_collection", path=SEQ, collection="/Game/MPC", param="Wipe",
                                 keys=[[0, 0], [12, 1, "constant"]])
    r["anim"] = run_op("seq.anim", path=SEQ, label="Host", component="Body",
                       sections=[{"anim": "/Game/A/Idle", "start": 0},
                                 {"anim": "/Game/A/Talk", "start": 40, "offset": 0.5, "weight": 0.8}])
    r["anim_add"] = run_op("seq.anim", path=SEQ, label="Host", component="Face",
                           sections=[{"anim": "/Game/A/Talk", "start": 10, "end": 50, "rate": 2.0}], replace=False)
    r["set_anim"] = run_op("seq.set_anim", path=SEQ, component="Body", anim="/Game/A/Talk", label="Host",
                           only="/Game/A/Idle")
    r["audio"] = run_op("seq.audio", path=SEQ, clips=[["/Game/Au/L1", 12], {"sound": "/Game/Au/L1", "start": 20,
                                                                          "offset": 0.25, "volume": 0.5}], track="VO")
    r["camera_cuts"] = run_op("seq.camera_cuts", path=SEQ, cuts=[["CamA", 0], ["CamB", 72]])
    r["cuts"] = run_op("seq.cuts", path=SEQ)
    r["tracks"] = run_op("seq.tracks", path=SEQ)
    return r


def _jsonable(v):
    return json.loads(json.dumps(v, default=str))


def test_legacy_ops_pinned(scene):
    got = {"results": _jsonable(scenario()), "describe": _jsonable(run_op("seq.describe", path=SEQ))}
    assert scene.dialogs == []
    if os.environ.get("SEQ_LEGACY_REGEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
    want = json.loads(GOLDEN.read_text())
    assert got["results"] == want["results"]
    for k in ("fps", "range", "markers", "bindings"):
        assert got["describe"][k] == want["describe"][k], k
    gt = {(t["kind"], t["binding"], t["component"], t["name"]): t for t in got["describe"]["tracks"]}
    wt = {(t["kind"], t["binding"], t["component"], t["name"]): t for t in want["describe"]["tracks"]}
    assert sorted(gt) == sorted(wt)
    for k in wt:
        assert gt[k] == wt[k], k


def test_legacy_shot(scene):
    res = run_op("seq.shot", path="/Game/L/SEQ_Shot", actor_label="Host", anims={"Body": "/Game/A/Idle"},
                 camera="CamA", audio="/Game/Au/L1", fps=24)
    assert res == {"sequence": "/Game/L/SEQ_Shot", "frames": 42, "fps": 24}  # 1.5 s audio * 24 + 6 tail
    doc = run_op("seq.describe", path="/Game/L/SEQ_Shot")
    assert doc["range"] == [0, 42]
    kinds = sorted((t["kind"], t["binding"], t["component"]) for t in doc["tracks"])
    assert kinds == [("anim", "Host", "Body"), ("audio", "", ""), ("camera_cut", "", "")]
    assert scene.dialogs == []


def test_legacy_rebind_and_cut_camera(scene):
    scenario()
    from fmbridge.ops import seq as legacy
    assert legacy.cut_camera(SEQ, 80) == "CamB"
    with pytest.raises(ValueError):
        legacy.cut_camera(SEQ, 500)
