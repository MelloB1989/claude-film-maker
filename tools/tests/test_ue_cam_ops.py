"""cam.* and shot.* ops against the fake engine. Sequencer writes are WP8's ops: here they are replaced by recorders,
so these tests check what the camera ops ask Sequencer for, not how Sequencer stores it."""
import pytest

from fakeunreal import run_op

MH_BONES = {"head": (0, 0, 160), "neck_01": (0, 0, 150), "clavicle_l": (0, -15, 145), "clavicle_r": (0, 15, 145),
            "spine_04": (0, 0, 128), "spine_01": (0, 0, 108), "pelvis": (0, 0, 95), "calf_l": (0, -10, 50),
            "calf_r": (0, 10, 50), "foot_l": (0, -10, 9), "foot_r": (0, 10, 9), "ball_l": (12, -10, 3),
            "ball_r": (12, 10, 3), "FACIAL_L_Eye": (8, -3.2, 168), "FACIAL_R_Eye": (8, 3.2, 168)}


def person(ue, label, at=(0.0, 0.0), turn=0):
    """A skeletal actor with MetaHuman bones at `at`, facing +X (turn=0) or -X (turn=180), +Y (90), -Y (-90)."""
    import math
    a = ue.spawn("SkeletalMeshActor", label, location=ue.Vector(at[0], at[1], 0))
    c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    ue.pose(a, {k: (at[0] + x * c - y * s, at[1] + x * s + y * c, z) for k, (x, y, z) in MH_BONES.items()})
    return a


@pytest.fixture
def seqrec(fmb, monkeypatch, ue):
    """Replace WP8's per-track seq ops with recorders (and hide seq.apply, so the per-track path runs); returns the
    list of calls."""
    monkeypatch.delitem(fmb._OPS, "seq.apply", raising=False)
    calls = []
    cuts = {}

    def rec(name):
        def fn(**kw):
            calls.append((name, kw))
            if name == "seq.camera_cuts":
                cuts[kw["path"]] = kw["cuts"]
            if name == "seq.new" and kw["path"] not in ue.assets:
                ue.add_asset(kw["path"], "LevelSequence")
            return {"ok": True}
        return fn
    for n in ("seq.new", "seq.key_transform", "seq.key_float", "seq.camera_cuts"):
        monkeypatch.setitem(fmb._OPS, n, rec(n))

    def seq_cuts(path):
        c = cuts.get(path, [])
        return [[lab, st, (c[i + 1][1] if i + 1 < len(c) else st + 48)] for i, (lab, st) in enumerate(c)]
    monkeypatch.setitem(fmb._OPS, "seq.cuts", seq_cuts)
    return calls


def test_add_converges_and_widens_lens(ue, fmb):
    r = run_op("cam.add", label="CAM_A", loc=[400, 0, 160], look_at=[0, 0, 160], focal_mm=50, aperture=2.0)
    assert r["created"] and r["changed"] and r["focal"] == 50 and r["aperture"] == 2.0
    assert r["rot"]["yaw"] == pytest.approx(180)
    assert r["filmback_preset"] == "16:9 Digital Film"
    again = run_op("cam.add", label="CAM_A", loc=[400, 0, 160], look_at=[0, 0, 160], focal_mm=50, aperture=2.0)
    assert not again["changed"] and not again["created"]
    assert len([a for a in ue.world.actors() if a.get_actor_label() == "CAM_A"]) == 1
    # beyond the Universal Zoom's limits: the lens is widened instead of the engine clamping the value
    wide = run_op("cam.set", label="CAM_A", focal_mm=2000, aperture=0.95)
    assert wide["focal"] == 2000 and wide["aperture"] == 0.95 and wide["lens"]["max_focal_mm"] == 2000
    hf = run_op("cam.set", label="CAM_A", hfov_deg=40, filmback="16:9 DSLR")
    assert hf["hfov_deg"] == pytest.approx(40, abs=1e-3) and hf["filmback"] == [36.0, 20.25]
    assert ue.dialogs == []


def test_errors_are_actionable(ue, fmb):
    from fmbridge.errors import OpError
    run_op("cam.add", label="CAM_B", loc=[0, 0, 0])
    with pytest.raises(OpError) as e:
        run_op("cam.set", label="CAM_X", focal_mm=50)
    assert e.value.code == "not_found" and "CAM_B" in e.value.candidates
    ue.spawn("StaticMeshActor", "Box")
    with pytest.raises(OpError) as e:
        run_op("cam.add", label="Box", loc=[0, 0, 0])
    assert e.value.code == "conflict"
    with pytest.raises(OpError) as e:
        run_op("cam.frame", camera="CAM_B", subjects="Box", size="huge")
    assert e.value.code == "bad_args"


def test_subject_from_bones_and_bounds(ue, fmb):
    person(ue, "Presenter")
    s = run_op("cam.subject", target="Presenter")
    assert s["from"] == "bones" and s["facing"] == pytest.approx([1, 0, 0])
    assert s["points"]["eyes"] == pytest.approx([8, 0, 168])
    ue.spawn("StaticMeshActor", "Lamp", location=ue.Vector(100, 0, 50), extent=(10, 10, 50))
    lamp = run_op("cam.subject", target="Lamp")
    assert lamp["from"] == "bounds" and lamp["height"] == pytest.approx(100)


def test_frame_mcu_three_quarter(ue, fmb):
    person(ue, "Presenter")
    r = run_op("cam.frame", camera="CAM_MCU", subjects="Presenter", size="MCU", angle="3/4", side="left",
               focal_mm=50)
    assert r["changed"] and r["solve"]["error"] < 1e-4
    cam = r["camera"]
    assert cam["loc"][0] > 0 and cam["loc"][1] < 0  # in front, on its left (-Y)
    assert cam["focal"] == pytest.approx(50)
    assert cam["focus"] == pytest.approx(r["solve"]["focus"], abs=0.1)
    p = run_op("cam.project", camera="CAM_MCU", subjects="Presenter")["points"]["Presenter"]
    assert p["eyes"]["u"] == pytest.approx(2 / 3, abs=1e-3)  # looking frame-left: on the right third
    assert p["size"]["size"] == "MCU"
    again = run_op("cam.frame", camera="CAM_MCU", subjects="Presenter", size="MCU", angle="3/4", side="left",
                   focal_mm=50)
    assert not again["changed"]
    dry = run_op("cam.frame", camera="CAM_WS", subjects="Presenter", size="WS", apply=False)
    assert not dry["changed"] and ue.actor("CAM_WS") is None


def test_check_focus_and_cut(ue, fmb):
    person(ue, "A", (0, -90), turn=90)
    person(ue, "B", (0, 90), turn=-90)
    run_op("cam.frame", camera="C1", subjects="A", size="MCU", angle=30, side="right", focal_mm=50, aperture=1.4)
    ok = run_op("cam.check", camera="C1", subjects="A", size="MCU")
    assert ok["pass"] and ok["metrics"]["size"]["A"]["size"] == "MCU"
    run_op("cam.focus", label="C1", mode="manual", distance_cm=50)
    bad = run_op("cam.check", camera="C1", subjects="A")
    assert not bad["pass"] and any(i["code"] == "cam.focus" for i in bad["issues"])
    run_op("cam.frame", camera="C2", subjects="B", size="MCU", angle=30, side="right", focal_mm=50)
    cut = run_op("cam.check_cut", camera_a="C1", camera_b="C2", subjects=["A", "B"])
    assert not cut["pass"] and cut["issues"][0]["code"] == "shot.line_180"
    tr = run_op("cam.focus", label="C2", mode="track", target="B")
    assert tr["focus_method"] == "tracking" and tr["focus_track"]["actor"] == "B"
    off = run_op("cam.focus", label="C2", mode="off")
    assert off["focus_method"] == "disable"


def test_coverage_makes_cameras_once(ue, fmb):
    person(ue, "A", (0, -90), turn=90)
    person(ue, "B", (0, 90), turn=-90)
    r = run_op("cam.coverage", subjects=["A", "B"], side="left")
    names = [s["camera"] for s in r["shots"]]
    assert {"CAM_master", "CAM_two_shot", "CAM_A_MCU", "CAM_B_OTS"} <= set(names)
    assert r["issues"] == []
    assert run_op("cam.coverage", subjects=["A", "B"], side="left")["changed"] is False
    assert len(run_op("cam.describe")["cameras"]) == len(names)
    assert run_op("cam.remove", prefix="CAM_")["changed"]
    assert run_op("cam.describe")["cameras"] == []


def test_move_writes_through_seq_ops(ue, fmb, seqrec):
    person(ue, "Presenter")
    ue.add_asset("/Game/T/Seq", "LevelSequence")
    run_op("cam.frame", camera="CAM_A", subjects="Presenter", size="MS", focal_mm=35)
    r = run_op("cam.move", camera="CAM_A", sequence="/Game/T/Seq",
               moves_=[{"move": "push_in", "fraction": 0.3, "frames": 48}, {"move": "zoom", "focal": 50, "frames": 24}],
               aim="eyes:Presenter", focus_on="eyes:Presenter", noise="subtle", fps=24)
    names = [c[0] for c in seqrec]
    assert names.count("seq.key_transform") == 1 and names.count("seq.key_float") == 2
    xf = next(kw for n, kw in seqrec if n == "seq.key_transform")
    assert xf["label"] == "CAM_A" and xf["keys"][0][0] == 0 and xf["keys"][-1][0] == 72
    props = {kw["prop"] for n, kw in seqrec if n == "seq.key_float"}
    assert props == {"CurrentFocalLength", "FocusSettings.ManualFocusDistance"}
    assert r["last"]["focal"] == pytest.approx(50)


def test_rig_rail_mounts_camera(ue, fmb, seqrec):
    run_op("cam.add", label="CAM_R", loc=[0, 0, 150])
    r = run_op("cam.rig", label="Rail", kind="rail", points=[[300, -200, 150], [300, 200, 150]], camera="CAM_R")
    assert r["created"] and ue.actor("CAM_R").get_attach_parent_actor() is ue.actor("Rail")
    pts = ue.actor("Rail").get_rail_spline_component()._props["points"]
    assert [p.y for p in pts] == [-200, 200]
    assert run_op("cam.describe", label="CAM_R")["cameras"][0]["attached_to"] == "Rail"
    ue.add_asset("/Game/T/Seq", "LevelSequence")
    m = run_op("cam.rig_move", rig_label="Rail", sequence="/Game/T/Seq",
               keys=[[0, {"position": 0}], [96, {"position": 1}]])
    assert m["tracks"] == {"CurrentPositionOnRail": 2}


SPEC = {
    "kind": "shot", "version": 1, "name": "t", "sequence": "/Game/T/Seq_Scene", "fps": 24,
    "lines": [{"id": "L1", "speaker": "A", "start_s": 1.0, "end_s": 3.0},
              {"id": "L2", "speaker": "B", "start_s": 3.5, "end_s": 6.0}],
    "subjects": {"A": {"actor": "A"}, "B": {"actor": "B"}},
    "shots": [
        {"id": "S1", "start": 0, "end": "L1.start-4f", "frame": {"subjects": ["A", "B"], "size": "WS", "focal_mm": 28}},
        {"id": "S2", "frame": {"subjects": ["A"], "size": "MCU", "angle": 30},
         "moves": [{"move": "push_in", "fraction": 0.1}], "noise": "subtle"},
        {"id": "S3", "start": "L2.start-4f", "coverage": "B_OTS"},
    ],
}


def test_shot_apply_converges(ue, fmb, seqrec):
    person(ue, "A", (0, -90), turn=90)
    person(ue, "B", (0, 90), turn=-90)
    plan = run_op("shot.plan", spec=SPEC)
    assert plan["cuts"] == [["CAM_S1", 0], ["CAM_S2", 20], ["CAM_S3", 80]] and not plan["up_to_date"]
    r = run_op("shot.apply", spec=SPEC)
    assert r["changed"] and set(r["cameras"]) == {"CAM_S1", "CAM_S2", "CAM_S3"}
    assert ("seq.camera_cuts", {"path": "/Game/T/Seq_Scene", "cuts": plan["cuts"]}) in seqrec
    n = len(seqrec)
    again = run_op("shot.apply", spec=SPEC)
    assert again["changed"] is False and len(seqrec) == n
    assert run_op("shot.plan", spec=SPEC)["up_to_date"]
    # drop S3: its camera goes
    spec2 = {**SPEC, "shots": SPEC["shots"][:2]}
    r2 = run_op("shot.apply", spec=spec2)
    assert r2["removed"] == ["CAM_S3"] and ue.actor("CAM_S3") is None
    d = run_op("shot.describe", sequence="/Game/T/Seq_Scene", subjects=["A"])
    assert [c["camera"] for c in d["cuts"]] == ["CAM_S1", "CAM_S2"]
    assert d["cuts"][1]["sizes"]["A"] == "MCU"
    assert ue.dialogs == []


def test_shot_spec_errors(ue, fmb):
    from fmbridge.errors import OpError
    bad = {**SPEC, "shots": [{"id": "S1", "frame": {"subjects": ["Z"], "size": "MCU"}, "lens": 50}]}
    with pytest.raises(OpError) as e:
        run_op("shot.plan", spec=bad)
    paths = [x["path"] for x in e.value.details["errors"]]
    assert "shots[0].lens" in paths and "shots[0].frame.subjects" in paths


def test_presets(ue, fmb):
    p = run_op("cam.presets")
    assert "MCU" in p["sizes"] and "dolly_zoom" in p["moves"] and p["default_filmback"] == "16:9 Digital Film"


def _fake_png(path, w, h, shade=90):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "unreal" / "fmbridge"))
    from camkit import png
    png.write(path, png.Image(w, h, (shade, shade, shade)))


def test_still_draws_guides(ue, fmb, monkeypatch, tmp_path):
    import fmbridge.ops.look as look

    def fake_still(camera_label, path, width=1920, height=1080, timeout=60.0):
        yield
        _fake_png(path, width, height)
        return {"path": path}
    monkeypatch.setattr(look, "still", fake_still)
    person(ue, "Presenter")
    run_op("cam.frame", camera="CAM_A", subjects="Presenter", size="MCU", focal_mm=50)
    out = str(tmp_path / "a.png")
    r = run_op("cam.still", camera="CAM_A", out=out, width=320, height=180, subjects="Presenter")
    assert r["width"] == 320 and r["raw"].endswith("_raw.png")
    from camkit import png
    img = png.read(out)
    assert any(img.get(107, y) != (90, 90, 90) for y in range(img.h))  # the left third's guide
    assert img.get(5, 5) != (90, 90, 90)  # the lens label


def test_sheet_through_the_cut(ue, fmb, seqrec, monkeypatch, tmp_path):
    person(ue, "A", (0, -90), turn=90)
    person(ue, "B", (0, 90), turn=-90)
    run_op("shot.apply", spec=SPEC)

    def fake_seq_still(path, frame, camera, out, width=1920, height=1080, settle=30):
        yield
        _fake_png(out, width, height, 40 + frame % 100)
        return {"path": out}
    monkeypatch.setitem(fmb._OPS, "seq.still", fake_seq_still)
    r = run_op("shot.sheet", sequence="/Game/T/Seq_Scene", out_dir=str(tmp_path), per_shot=3, cell_w=160, cols=3)
    assert len(r["stills"]) == 9 and r["path"].endswith("sheet.png")
    assert [s[1] for s in r["stills"][::3]] == ["CAM_S1", "CAM_S2", "CAM_S3"]
    assert r["width"] == 3 * (160 + 6) + 6


def test_shot_plan_keeps_the_line(ue, fmb):
    person(ue, "A", (0, -90), turn=90)
    person(ue, "B", (0, 90), turn=-90)
    p = run_op("shot.plan", spec=SPEC)
    assert not [i for i in p["issues"] if i["code"] == "shot.line_180"]
    crossed = {**SPEC, "shots": [SPEC["shots"][0], {**SPEC["shots"][1], "frame": {**SPEC["shots"][1]["frame"],
                                                                                   "side": "right"}}]}
    assert [i for i in run_op("shot.plan", spec=crossed)["issues"] if i["code"] == "shot.line_180"]


def test_shoot_and_words_round_trip(ue, fmb):
    from fmbridge.errors import OpError
    person(ue, "Host", (0, -90), turn=90)
    person(ue, "Guest", (0, 90), turn=-90)
    r = run_op("cam.shoot", camera="CAM_W", text="medium close-up of Host from 30 degrees left, slightly high, 50mm")
    assert r["parsed"]["subjects"] == ["Host"] and r["solve"]["size"] == "MCU" and r["changed"]
    said = run_op("cam.describe", label="CAM_W", subjects="Host")["cameras"][0]["words"]
    assert said.startswith("MCU of Host from 1/4 left (30 deg), slightly high, 50 mm"), said
    again = run_op("cam.shoot", camera="CAM_W", text=said)
    assert not again["changed"]  # the words put the camera back where it is
    two = run_op("cam.shoot", camera="CAM_2", text="two-shot of Host and Guest, low angle, 35mm", apply=False)
    assert two["parsed"]["subjects"] == ["Host", "Guest"] and two["words"].startswith("two-shot")
    with pytest.raises(OpError) as e:
        run_op("cam.shoot", camera="CAM_X", text="close-up of nobody")
    assert e.value.code == "bad_args"


def test_batched_writes_through_seq_apply(ue, fmb, seqrec, monkeypatch):
    """With WP8's seq.apply installed, a shot list's keys and cuts go in one call, as a sequence spec."""
    calls = []

    def fake_apply(spec, prune=None, dry_run=False, save=True):
        calls.append(spec)
        yield
        return {"changed": True, "steps": [1, 2], "converged": True}
    monkeypatch.setitem(fmb._OPS, "seq.apply", fake_apply)
    person(ue, "A", (0, -90), turn=90)
    person(ue, "B", (0, 90), turn=-90)
    r = run_op("shot.apply", spec=SPEC)
    assert r["write"] == {"batched": True, "converged": True, "steps": 2}
    assert len(calls) == 1 and not [c for c in seqrec if c[0] in ("seq.key_transform", "seq.key_float")]
    doc = calls[0]
    assert doc["kind"] == "sequence" and doc["sequence"] == SPEC["sequence"]
    assert doc["camera_cuts"] == [["CAM_S1", 0], ["CAM_S2", 20], ["CAM_S3", 80]]
    s2 = doc["bindings"]["CAM_S2"]
    assert s2["transform"]["keys"][0][0] == 20 and "CameraComponent/FocusSettings.ManualFocusDistance" in s2["props"]
    mv = run_op("cam.move", camera="CAM_S1", sequence=SPEC["sequence"], moves_=[{"move": "pan", "degrees": 10}])
    assert mv["write"]["batched"] and list(calls[-1]["bindings"]) == ["CAM_S1"] and "camera_cuts" not in calls[-1]


def test_shot_apply_on_wp8_sequencer(ue, fmb):
    """Against WP8's own Sequencer fake and seq.apply (when installed): the edit and the keys read back."""
    if "seq.apply" not in fmb._OPS:
        pytest.skip("WP8's seq.apply is not on this branch")
    person(ue, "A", (0, -90), turn=90)
    person(ue, "B", (0, 90), turn=-90)
    r = run_op("shot.apply", spec=SPEC)
    assert r["write"]["batched"] and r["write"]["converged"], r["write"]
    assert [c[:2] for c in run_op("seq.cuts", path=SPEC["sequence"])] == [["CAM_S1", 0], ["CAM_S2", 20],
                                                                          ["CAM_S3", 80]]
    assert run_op("shot.apply", spec=SPEC)["changed"] is False
    assert run_op("shot.apply", spec=SPEC, force=True)["write"]["steps"] == 0  # seq.apply: nothing left to write
