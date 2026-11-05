"""WP8 Sequencer core against the fake engine (fakeunreal + ext_seq): describe / plan / apply converge and are
idempotent, tracks round-trip through describe, writes are batched across ticks, nothing opens a dialog."""
import copy

import pytest

from fakeunreal import drive, run_op

SEQ = "/Game/T/SEQ_T"
CAM = {"comp": "CameraComponent"}  # the cine camera component's name in this fake (set by `level`)


@pytest.fixture
def level(ue):
    hero = ue.spawn("SkeletalMeshActor", "Hero", location=ue.Vector(10, 20, 0))
    hero.add_component(ue.SkeletalMeshComponent, "Body")
    hero.add_component(ue.StaticMeshComponent, "Mesh")
    ue.spawn("CineCameraActor", "CamA", location=ue.Vector(0, -300, 160))
    ue.spawn("CineCameraActor", "CamB", location=ue.Vector(300, 0, 160))
    CAM["comp"] = ue.actor("CamA").get_cine_camera_component().get_name()
    light = ue.spawn("PointLight", "Key")
    light._props["point_light_component"]._props["intensity"] = 5.0
    ue.add_asset("/Game/A/Idle", "AnimSequence", sequence_length=5.0)
    ue.add_asset("/Game/Au/L1", "SoundWave", duration=2.0)
    ue.add_asset("/Game/MPC_FM", "MaterialParameterCollection")
    return ue


def spec(**over):
    s = {
        "kind": "sequence", "version": 1, "name": "t", "sequence": SEQ, "fps": 24, "range": [0, 240],
        "markers": [[48, "beat"]],
        "bindings": {
            "Hero": {
                "transform": {"keys": [[0, [0, 0, 0], {"yaw": 170}], [48, [100, 0, 0], {"yaw": -170}],
                                       {"frame": "4s", "loc": [100, 50, 0], "look_at": "CamA", "interp": "linear"}]},
                "visible": [[0, True], [100, False]],
                "anim": {"component": "Body", "sections": [{"anim": "/Game/A/Idle", "start": 0, "blend_in": 6,
                                                            "offset": 0.5}]},
                "materials": [{"component": "Mesh", "slot": 0, "param": "Glow", "keys": [[0, 0], [24, 1]]}],
            },
            "Key": {"props": {"point_light_component/Intensity": [[0, 5], [24, 10]]}},
            "CamA": {"props": {f"{CAM['comp']}/CurrentFocalLength": [[0, 35], [120, 50]]}},
            "CamB": {},
        },
        "camera_cuts": [["CamA", 0], ["CamB", "5s"]],
        "audio": {"VO": [{"sound": "/Game/Au/L1", "start": 12}]},
        "fade": {"color": [0, 0, 0], "keys": [[0, 1], [12, 0]]},
        "collections": [{"collection": "/Game/MPC_FM", "param": "WipeOn", "keys": [[0, 0], [24, 1, "constant"]]}],
    }
    s.update(over)
    return s


def tracks(doc, kind, binding=""):
    return [t for t in doc["tracks"] if t["kind"] == kind and t["binding"] == binding]


def test_apply_from_nothing_converges_and_is_idempotent(level):
    res = run_op("seq.apply", spec=spec())
    assert res["changed"] and res["converged"], res["remaining"]
    assert level.dialogs == []
    again = run_op("seq.apply", spec=spec())
    assert again["changed"] is False and again["steps"] == [] and again["converged"]
    plan = run_op("seq.plan", spec=spec())
    assert plan == {"steps": [], "converged": True, "notes": plan["notes"]}


def test_describe_reads_back_what_was_written(level):
    run_op("seq.apply", spec=spec())
    doc = run_op("seq.describe", path=SEQ)
    assert doc["fps"] == "24" and doc["range"] == [0, 240] and doc["markers"] == [{"frame": 48, "label": "beat"}]
    assert {b["name"]: b["bound"] for b in doc["bindings"]} == {"Hero": True, "Key": True, "CamA": True, "CamB": True}
    tr = tracks(doc, "transform", "Hero")[0]["sections"][0]["channels"]
    assert [k[1] for k in tr["rotation.yaw"]["keys"]][:2] == [170.0, 190.0]  # unwrapped
    assert tr["location.y"]["keys"][-1][:3] == [96, 50.0, "linear"]
    assert tr["scale.x"]["default"] == 1.0 and tr["scale.x"]["keys"] == []  # unkeyed: the actor's own value
    anim = tracks(doc, "anim", "Hero")[0]
    assert anim["component"] == "Body"
    s = anim["sections"][0]
    assert s["range"] == [0, 108] and s["params"]["offset"] == 0.5 and s["params"]["blend_in"] == 6  # (5-0.5)*24
    cuts = tracks(doc, "camera_cut")[0]["sections"]
    assert [(c["range"], c["params"]["camera"]) for c in cuts] == [([0, 120], "CamA"), ([120, 240], "CamB")]
    au = tracks(doc, "audio")[0]
    assert au["name"] == "VO" and au["sections"][0]["range"] == [12, 60]
    mat = tracks(doc, "material", "Hero")[0]
    assert mat["component"] == "Mesh" and mat["sections"][0]["channels"]["Glow"]["keys"][1][:2] == [24, 1.0]
    mpc = tracks(doc, "mpc")[0]
    assert mpc["name"] == "/Game/MPC_FM" and mpc["sections"][0]["channels"]["WipeOn"]["keys"][1][2] == "constant"
    lt = tracks(doc, "float", "Key")[0]
    assert lt["component"] == "point_light_component" and lt["name"] == "Intensity"


def test_describe_round_trips_through_apply(level):
    run_op("seq.apply", spec=spec())
    doc = run_op("seq.describe", path=SEQ)
    back = {"sequence": SEQ, "fps": doc["fps"], "range": doc["range"], "tracks": doc["tracks"],
            "bindings": doc["bindings"]}
    res = run_op("seq.apply", spec=back)
    assert res["changed"] is False, [s["why"] for s in res["steps"]]


def test_only_changed_tracks_are_rewritten(level):
    run_op("seq.apply", spec=spec())
    s = spec()
    s["bindings"]["Key"]["props"]["point_light_component/Intensity"] = [[0, 5], [24, 12]]
    res = run_op("seq.apply", spec=s)
    assert [st["op"] for st in res["steps"]] == ["seq.write"] and "Intensity" in res["steps"][0]["why"]
    assert res["converged"]


def test_partial_material_keeps_other_params(level):
    run_op("seq.apply", spec=spec())
    s = spec()
    s["bindings"]["Hero"]["materials"] = [{"component": "Mesh", "slot": 0, "param": "Tint", "keys": [[0, [1, 0, 0]]]}]
    run_op("seq.apply", spec=s)
    ch = tracks(run_op("seq.describe", path=SEQ), "material", "Hero")[0]["sections"][0]["channels"]
    assert set(ch) == {"Glow", "Tint"} and ch["Tint"]["keys"][0][1] == [1.0, 0.0, 0.0, 1.0]


def test_prune_removes_unlisted(level):
    run_op("seq.apply", spec=spec())
    s = spec()
    del s["bindings"]["Hero"]["visible"]
    assert run_op("seq.apply", spec=s)["changed"] is False
    res = run_op("seq.apply", spec=s, prune=True)
    assert [st["op"] for st in res["steps"]] == ["seq.remove_track"]
    assert not tracks(run_op("seq.describe", path=SEQ), "visibility", "Hero")


def test_spawnable_binding(level):
    s = spec(bindings={"Drone": {"spawn": {"class": "CineCameraActor"}}}, camera_cuts=[["Drone", 0]])
    for k in ("audio", "fade", "collections", "markers"):
        s.pop(k)
    res = run_op("seq.apply", spec=s)
    assert res["converged"]
    doc = run_op("seq.describe", path=SEQ)
    assert doc["bindings"] == [{"name": "Drone", "kind": "spawnable", "class": "CineCameraActor", "bound": None}]
    assert tracks(doc, "spawn", "Drone")
    assert run_op("seq.apply", spec=s)["changed"] is False


def test_bad_spec_is_rejected_before_anything_changes(level):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("seq.apply", spec=spec(range=[10, 5], camera_cuts=[[1, 2]]))
    assert e.value.code == "bad_args" and len(e.value.details["problems"]) == 2
    assert run_op("seq.describe", path=SEQ)["exists"] is False


def test_unknown_actor_names_candidates(level):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("seq.apply", spec=spec(bindings={"Hreo": {"visible": [[0, True]]}}))
    assert e.value.code == "not_found" and "Hero" in e.value.candidates


def test_write_is_batched_across_ticks(level):
    run_op("seq.add", path=SEQ, fps=24, start=0, end=6000)
    track = {"kind": "float", "binding": "Key", "component": "point_light_component", "name": "Intensity",
             "sections": [{"range": [None, None], "channels": {"value": {"keys": [[f, f * 0.5] for f in range(5000)]}}}]}
    ops = __import__("fmbridge.ops", fromlist=["call"])
    res, ticks = drive(ops.call("seq.write", path=SEQ, track=track))
    assert res["keys"] == 5000 and res["changed"] and ticks >= 2
    seq = level.assets[SEQ]
    assert seq.key_writes == 5000
    again, _ = drive(ops.call("seq.write", path=SEQ, track=track))
    assert again["changed"] is False and seq.key_writes == 5000


def test_writing_closes_and_reopens_an_open_sequence(level):
    run_op("seq.apply", spec=spec())
    lse = level.LevelSequenceEditorBlueprintLibrary
    lse.open_level_sequence(level.assets[SEQ])
    s = spec()
    s["fade"]["keys"] = [[0, 1], [24, 0]]
    run_op("seq.apply", spec=s)
    assert lse.get_current_level_sequence() is level.assets[SEQ]


def test_eval_channels_and_transforms(level):
    run_op("seq.apply", spec=spec())
    res = run_op("seq.eval", path=SEQ, frames=[0, 12, 24], labels=["Hero"],
                 tracks=[{"kind": "float", "binding": "Key", "component": "point_light_component",
                          "name": "Intensity"}])
    assert res["channels"]["Key.point_light_component/float:Intensity"]["value"][::2] == [5.0, 10.0]
    hero = res["transforms"]["Hero"]
    assert hero[0][:3] == [0.0, 0.0, 0.0] and abs(hero[0][4] - 170.0) < 1e-6


def test_check_flags_gaps_and_unbound(level):
    run_op("seq.apply", spec=spec(camera_cuts=[["CamA", 0, 100], ["CamB", 120]]))
    level.world.remove(level.actor("CamB"))
    res = run_op("seq.check", path=SEQ)
    codes = {i["code"] for i in res["issues"]}
    assert {"seq.cut_gap", "seq.binding_unbound"} <= codes and res["pass"] is False


def test_shots_chunks_and_preroll(level):
    level.add_asset("/Game/S/sh010", "LevelSequence")
    level.add_asset("/Game/S/sh020", "LevelSequence")
    s = {"sequence": "/Game/S/Master", "fps": 24, "range": [0, 240],
         "shots": [{"sequence": "/Game/S/sh010", "start": 0, "end": 120, "preroll": 8},
                   {"sequence": "/Game/S/sh020", "start": 120, "end": 240, "timescale": 2}]}
    assert run_op("seq.apply", spec=s)["converged"]
    assert run_op("seq.apply", spec=s)["changed"] is False
    shots = run_op("seq.shots", path="/Game/S/Master")
    assert [(x["name"], x["start"], x["preroll"]) for x in shots] == [("sh010", 0, 8), ("sh020", 120, 0)]
    ch = run_op("seq.chunks", path="/Game/S/Master", start=100, end=200, max_frames=48)["chunks"]
    assert [(c["start"], c["eval_from"]) for c in ch] == [(100, -8), (120, 120), (168, 120)]
    assert run_op("seq.preroll", path="/Game/S/Master", frames=12)["changed"]
    assert [x["preroll"] for x in run_op("seq.shots", path="/Game/S/Master")] == [12, 12]


def test_copy_window_and_retime(level):
    run_op("seq.apply", spec=spec())
    res = run_op("seq.copy", src=SEQ, dst="/Game/T/SEQ_cut", start=120, end=240)
    assert res["range"] == [0, 120]
    doc = run_op("seq.describe", path="/Game/T/SEQ_cut")
    assert [(c["range"], c["params"]["camera"]) for c in tracks(doc, "camera_cut")[0]["sections"]] == [([0, 120], "CamB")]
    assert doc["markers"] == []
    with pytest.raises(Exception, match="exists"):
        run_op("seq.copy", src=SEQ, dst="/Game/T/SEQ_cut")
    run_op("seq.retime", path=SEQ, offset=10, after=100)
    doc = run_op("seq.describe", path=SEQ)
    assert doc["range"] == [0, 250]
    assert [c["range"] for c in tracks(doc, "camera_cut")[0]["sections"]] == [[0, 130], [130, 250]]
    assert level.dialogs == []


def test_time_conversion_and_validate(level):
    assert run_op("seq.time", value="00:00:02:00", fps=24) == {"frame": 48, "seconds": 2.0, "timecode": "00:00:02:00",
                                                              "ticks": 48000, "fps": "24"}
    bad = run_op("seq.validate", spec={"sequence": "/Game/X", "bindings": {"A": {"transfrom": []}}})
    assert not bad["ok"] and "transfrom" in bad["problems"][0]


def test_add_converges_rate_and_range(level):
    a = run_op("seq.add", path=SEQ, fps="23.976", start=0, end=100)
    assert a["created"] and a["fps"] == "24000/1001"
    b = run_op("seq.add", path=SEQ, fps="23.976", start=0, end=100)
    assert b["changed"] is False
    assert run_op("seq.add", path=SEQ, end=120)["changed"]


def test_bind_rebinds_an_unbound_possessable_keeping_its_tracks(level):
    run_op("seq.apply", spec=spec())
    seq = level.assets[SEQ]
    hero = next(b for b in seq.ms.bindings if b.name == "Hero")
    hero.obj_label = "GoneHero"  # the level was rebuilt: the old actor is gone
    assert run_op("seq.check", path=SEQ)["pass"] is False
    res = run_op("seq.bind", path=SEQ, label="Hero")
    assert res["changed"] and hero.obj_label == "Hero"
    assert tracks(run_op("seq.describe", path=SEQ), "transform", "Hero")


def test_diff_two_sequences_and_against_a_spec(level):
    run_op("seq.apply", spec=spec())
    run_op("seq.copy", src=SEQ, dst="/Game/T/SEQ_B")
    assert run_op("seq.diff", path=SEQ, other="/Game/T/SEQ_B")["same"]
    assert run_op("seq.diff", path=SEQ, spec=spec())["same"]
    s = spec()
    s["fade"]["keys"] = [[0, 1], [24, 0]]
    d = run_op("seq.diff", path=SEQ, spec=s)
    assert [t["track"] for t in d["tracks"]] == ["/fade"]


def test_conform_keeps_time_or_frames(level):
    run_op("seq.apply", spec=spec())
    a = run_op("seq.describe", path=SEQ)
    r = run_op("seq.conform", path=SEQ, fps=30, keep="time")
    assert r["changed"] and r["range"] == [0, 300] and r["tick_resolution"] == 24000
    b = run_op("seq.describe", path=SEQ)
    assert b["markers"] == [{"frame": 60, "label": "beat"}]
    cuts = [s["range"] for s in tracks(b, "camera_cut")[0]["sections"]]
    assert cuts == [[0, 150], [150, 300]]                       # 5 s is still 5 s
    assert tracks(b, "float", "Key")[0]["sections"][0]["channels"]["value"]["keys"][1][0] == 30
    assert run_op("seq.conform", path=SEQ, fps=30)["changed"] is False
    r = run_op("seq.conform", path=SEQ, fps="29.97", keep="time")
    assert r["tick_resolution"] == 60000                        # 24000 does not land on 29.97 frames
    run_op("seq.apply", spec=spec())                             # back to 24 fps, frames as the spec says
    r = run_op("seq.conform", path=SEQ, fps=48, keep="frames", out="/Game/T/SEQ_48")
    c = run_op("seq.describe", path="/Game/T/SEQ_48")
    assert c["fps"] == "48" and c["range"] == a["range"]
    assert [s["range"] for s in tracks(c, "camera_cut")[0]["sections"]] == [[0, 120], [120, 240]]
    assert tracks(c, "anim", "Hero")[0]["sections"][0]["params"]["rate"] == 2.0
    assert tracks(c, "audio")[0]["sections"][0]["range"] == [12, 108]   # 2 s of sound at 48 fps


def test_retime_stretches_a_span(level):
    run_op("seq.apply", spec=spec())
    r = run_op("seq.retime", path=SEQ, start=100, end=140, scale=1.5)
    doc = run_op("seq.describe", path=SEQ)
    assert doc["range"] == [0, 260] and [s["range"] for s in tracks(doc, "camera_cut")[0]["sections"]] == \
        [[0, 130], [130, 260]]
    from fmbridge.errors import OpError
    with pytest.raises(OpError):
        run_op("seq.retime", path=SEQ, start=100, scale=2)


def test_shot_list_builds_shot_sequences_and_master(level):
    level.add_asset("/Game/F/SEQ_existing", "LevelSequence")
    s = {"sequence": "/Game/F/SEQ_Edit", "fps": 24,
         "shots": [{"name": "wide", "camera": "CamA", "duration": 72, "handles": 12},
                   {"name": "close", "duration": 48, "shot": {
                       "bindings": {"CamB": {"props": {f"{CAM['comp']}/CurrentFocalLength": [[0, 85]]}}},
                       "camera_cuts": [["CamB", 0]]}},
                   {"sequence": "/Game/F/SEQ_existing", "duration": 24}]}
    r = run_op("seq.apply", spec=s)
    assert r["converged"], r["remaining"]
    assert [x["op"] for x in r["steps"]][:3] == ["seq.add", "seq.apply", "seq.apply"]
    wide = run_op("seq.describe", path="/Game/F/SEQ_Edit_wide")
    assert wide["range"] == [0, 96] and [c["params"]["camera"] for c in tracks(wide, "camera_cut")[0]["sections"]] == ["CamA"]
    shots = run_op("seq.shots", path="/Game/F/SEQ_Edit")
    assert [(x["name"], x["start"], x["end"]) for x in shots] == [("wide", 0, 72), ("close", 72, 120),
                                                                  ("SEQ_existing", 120, 144)]
    assert run_op("seq.apply", spec=s)["changed"] is False
    s["shots"][1]["shot"]["bindings"]["CamB"]["props"][f"{CAM['comp']}/CurrentFocalLength"] = [[0, 50]]
    r = run_op("seq.apply", spec=s)
    assert [(x["op"], x["result"]["sequence"]) for x in r["steps"]] == [("seq.apply", "/Game/F/SEQ_Edit_close")]
    assert r["converged"]
