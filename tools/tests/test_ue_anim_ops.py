"""WP4: the anim.* and perf.* ops against the fake engine (tools/tests/fakeunreal + ext_anim): what they write, that
re-runs converge, and that mistakes come back as actionable errors."""
from __future__ import annotations

import math
import struct
import wave

import pytest

from fakeunreal import run_op

FACE_SKEL = "/Game/MH/Face/FaceMesh_Skeleton"


def talk(ue, path="/Game/S/AS_talk", length_s=4.0):
    t = [i / 30 for i in range(int(length_s * 30) + 1)]
    return ue.anim(path, length_s=length_s, skeleton=FACE_SKEL, curves={
        "CTRL_expressions_jawOpen": (t, [abs(math.sin(x * 9)) * 0.6 for x in t]),
        "HeadYaw": (t, [6 * math.sin(x * 2) for x in t]), "HeadPitch": (t, [0.0] * len(t)),
        "HeadRoll": (t, [0.0] * len(t)), "CTRL_expressions_eyeBlinkL": ([0, length_s], [0, 0])})


def wav(path, seconds=3.0, sr=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        amp = lambda i: 0.0 if (i / sr) % 1.0 > 0.7 else (1.0 if 0.3 < (i / sr) % 1.0 < 0.4 else 0.3)  # noqa: E731
        w.writeframes(b"".join(struct.pack("<h", int(amp(i) * 15000 * math.sin(2 * math.pi * 180 * i / sr)))
                               for i in range(int(seconds * sr))))
    return str(path)


def test_perf_face_writes_a_living_copy_and_keeps_the_lip_sync(ue, tmp_path):
    a = talk(ue)
    r = run_op("perf.face", anim="/Game/S/AS_talk", wav=wav(tmp_path / "l.wav", 4.0), mood="warm",
               gaze=[{"t": 0, "yaw": 0, "scan": "lens"}, {"t": 2, "yaw": 25, "pitch": -4}])
    assert r["out"] == "/Game/S/AS_talk_perf" and r["changed"]
    out = ue.assets["/Game/S/AS_talk_perf"]
    cur = out._data["curves"]
    assert cur["CTRL_expressions_jawOpen"] == a._data["curves"]["CTRL_expressions_jawOpen"]  # lip-sync untouched
    assert a._data["curves"]["HeadYaw"] != cur["HeadYaw"]  # the source is untouched too
    assert "CTRL_expressions_mouthCornerPullL" in cur and "CTRL_expressions_eyeLookLeftL" in cur
    assert out._data["brackets"] == 1  # one batched write
    assert r["plan"]["shifts"][1]["gaze"] == [25.0, -4.0]
    assert ue.dialogs == []
    # re-running converges on the same asset (freed and re-made, no _1)
    run_op("perf.face", anim="/Game/S/AS_talk", mood="warm")
    assert [p for p in ue.assets if p.startswith("/Game/S/AS_talk_perf")] == ["/Game/S/AS_talk_perf"]


def test_perf_face_bad_words_are_actionable(ue):
    talk(ue)
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("perf.face", anim="/Game/S/AS_talk", expressions=[{"preset": "smiel", "t": 1, "until": 2}])
    assert e.value.code == "bad_args" and "smile" in str(e.value)
    with pytest.raises(OpError) as e:
        run_op("perf.face", anim="/Game/S/AS_tlak")
    assert e.value.code == "not_found" and "AS_talk" in e.value.candidates


def test_anim_check_flags_a_robotic_solve(ue):
    ue.anim("/Game/S/AS_robot", length_s=8, curves={"HeadYaw": ([0, 1, 2, 3, 4, 5, 6, 7, 8], [0, 10, 10, -10, -10, 0, 0, 12, 0]),
                                                     "HeadPitch": ([0, 8], [0, 0]), "HeadRoll": ([0, 8], [0, 0])})
    r = run_op("anim.check", anim="/Game/S/AS_robot")
    assert not r["pass"] and "head_linear" in r["failed"] and "blink_rate" in r["failed"]
    talk(ue)
    fixed = run_op("perf.face", anim="/Game/S/AS_talk", out="/Game/S/AS_fixed", seed=1)
    assert "head_linear" not in fixed["report"]["failed"]


def test_anim_write_curves_modes_and_convergence(ue):
    ue.anim("/Game/S/AS_a", curves={"X": ([0, 1], [0.2, 0.2])})
    r = run_op("anim.write_curves", anim="/Game/S/AS_a", curves={"X": [[0, 1], [0.1, 0.3]]}, mode="add")
    assert ue.assets["/Game/S/AS_a"]._data["curves"]["X"] == ([0.0, 1.0], [pytest.approx(0.3), pytest.approx(0.5)])
    assert r["changed"]
    r = run_op("anim.write_curves", anim="/Game/S/AS_a", curves={"X": [[0, 1], [0.3, 0.5]]})
    r2 = run_op("anim.write_curves", anim="/Game/S/AS_a", curves={"X": [[0, 1], [0.3, 0.5]]})
    assert r2["changed"] is False
    from fmbridge.errors import OpError
    with pytest.raises(OpError):
        run_op("anim.write_curves", anim="/Game/S/AS_a", curves={"X": [[0, 1], [0.3]]})


def test_anim_new_converges(ue):
    ue.skeletal_mesh("/Game/MH/Face/FaceMesh", FACE_SKEL)
    r = run_op("anim.new", path="/Game/P/AS_blank", skeleton="/Game/MH/Face/FaceMesh", length_s=2.0)
    assert r["created"] and r["frames"] == 60 and r["length_s"] == pytest.approx(2.0)
    a = ue.assets["/Game/P/AS_blank"]
    assert a.get_skeleton() is ue.assets[FACE_SKEL]
    r = run_op("anim.new", path="/Game/P/AS_blank", skeleton="/Game/MH/Face/FaceMesh", length_s=2.0)
    assert not r["created"] and not r["changed"]
    r = run_op("anim.new", path="/Game/P/AS_blank", skeleton=FACE_SKEL, length_s=3.0)
    assert r["changed"] and r["frames"] == 90
    assert ue.dialogs == []


def test_anim_new_reaches_rates_that_are_not_a_multiple_of_30(ue):
    # the controller takes only a multiple or a factor of the current rate: 30 -> 24 goes through 120
    ue.skeletal_mesh("/Game/MH/Face/FaceMesh", FACE_SKEL)
    for fps, frames in ((24, 48), (25, 50), (60, 120)):
        r = run_op("anim.new", path=f"/Game/P/AS_{fps}", skeleton=FACE_SKEL, length_s=2.0, fps=fps, replace=True)
        a = ue.assets[f"/Game/P/AS_{fps}"]
        assert a._data["fps"] == fps and r["frames"] == frames and r["length_s"] == pytest.approx(2.0)
    assert not [c for c in ue.calls if c[0] == "AnimationDataController.error"]


def test_additive_goes_through_properties_not_the_library_setters(ue, monkeypatch):
    # AnimationLibrary.set_additive_* skip PostEditChange: the asset would never be recompressed as additive
    def refuse(*a):
        raise AssertionError("AnimationLibrary.set_additive_* used")
    monkeypatch.setattr(ue.AnimationLibrary, "set_additive_animation_type", staticmethod(refuse))
    monkeypatch.setattr(ue.AnimationLibrary, "set_additive_base_pose_type", staticmethod(refuse))
    talk(ue)
    ue.anim("/Game/S/AS_base", length_s=1.0, skeleton=FACE_SKEL)
    run_op("anim.additive", anim="/Game/S/AS_talk", out="/Game/S/AS_talk_add", base="/Game/S/AS_base", frame=3)
    a = ue.assets["/Game/S/AS_talk_add"]
    assert "ABPT_ANIM_FRAME" in str(a._props["ref_pose_type"]) and a._props["ref_frame_index"] == 3
    assert a._props["ref_pose_seq"] is ue.assets["/Game/S/AS_base"]


def _keyable_rig(ue, monkeypatch, listening=True):
    """A rig whose set_local_control_rig_* key only while its sequence is open (Sequencer's track editor keys)."""
    ue.spawn("SkeletalMeshActor", "Host")
    ue.pose("Host", {"head": [0, 0, 160]})
    seq = ue.add_asset("/Game/T/Seq", "LevelSequence")
    rig = ue.rig("Host", {"CTRL_brow": "head", "CTRL_neck": "head"})
    keys = {}
    LSE = ue.LevelSequenceEditorBlueprintLibrary
    CR = ue.ControlRigSequencerLibrary

    def setter(s, r, control, frames, values, *a):
        if listening and LSE.get_current_level_sequence() is s:
            keys[control] = dict(zip([f.value for f in frames], values))

    def getter(s, r, control, frames, *a):
        return [keys.get(control, {}).get(f.value, 0.0) for f in frames]
    for kind in ("floats", "rotators", "euler_transforms"):
        monkeypatch.setattr(CR, f"set_local_control_rig_{kind}", staticmethod(setter), raising=False)
        monkeypatch.setattr(CR, f"get_local_control_rig_{kind}", staticmethod(getter), raising=False)
    LSE.current = None
    return seq, keys


def test_rig_keys_opens_the_sequence_and_checks_the_keys_landed(ue, fmb, monkeypatch):
    seq, keys = _keyable_rig(ue, monkeypatch)
    r = run_op("anim.rig_keys", sequence="/Game/T/Seq", label="Host", keys={"CTRL_brow": [[0, 0], [12, 0.6], [30, 0]]})
    assert r["keys"] == 3 and keys["CTRL_brow"] == {0: 0.0, 12: 0.6, 30: 0.0}
    assert ue.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence() is seq


def test_rig_keys_that_do_not_land_are_an_error(ue, fmb, monkeypatch):
    _keyable_rig(ue, monkeypatch, listening=False)
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("anim.rig_keys", sequence="/Game/T/Seq", label="Host", keys={"CTRL_brow": [[0, 0], [12, 0.6]]})
    assert e.value.code == "engine" and "CTRL_brow" in str(e.value)


def test_anim_find_ranks_metahuman_templates(ue):
    for p in ("/MetaHumanCharacter/Optional/Animation/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Walk_Loop_F",
              "/MetaHumanCharacter/Optional/Animation/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Run_Loop_F",
              "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"):
        ue.anim(p, length_s=1.2, skeleton="/Game/MH/Body_Skel")
    r = run_op("anim.find", query="walk forward loop", path="/MetaHumanCharacter")
    assert r["found"][0]["path"].endswith("Walk_Loop_F") and r["found"][0]["length_s"] == pytest.approx(1.2)
    assert r["found"][0]["skeleton"] == "/Game/MH/Body_Skel"
    assert run_op("anim.find", query="idle", skeleton="/Game/Other_Skel")["found"] == []


def test_anim_describe_and_additive(ue):
    talk(ue)
    d = run_op("anim.describe", anim="/Game/S/AS_talk", curves=True)
    assert d["head_curves"] == ["HeadYaw", "HeadPitch", "HeadRoll"] and d["face_curves"] == 2
    assert d["skeleton"] == FACE_SKEL and d["fps"] == pytest.approx(30.0)
    r = run_op("anim.additive", anim="/Game/S/AS_talk", out="/Game/S/AS_talk_add")
    a = ue.assets["/Game/S/AS_talk_add"]
    assert "AAT_LOCAL_SPACE_BASE" in str(a._props["additive_anim_type"])
    assert "ABPT_LOCAL_ANIM_FRAME" in str(a._props["ref_pose_type"]) and r["changed"]


def test_perf_vocab_and_head_preview(ue):
    v = run_op("perf.vocab")
    assert "smile" in v["expressions"] and v["moods"]["confident"]["solver_mood"] == "CONFIDENCE"
    h = run_op("perf.head_curves", duration_s=5, gaze=[{"t": 1, "yaw": 30}], nods=[{"t": 3, "kind": "nod"}])
    assert len(h["times"]) == len(h["yaw"]) and max(h["yaw"]) > 15
    assert all(c["pass"] for c in h["checks"])


def test_perf_analyze_audio(ue, tmp_path):
    r = run_op("perf.analyze_audio", wav=wav(tmp_path / "a.wav", 3.0))
    assert r["duration_s"] == pytest.approx(3.0, abs=0.05) and r["pauses"] and r["emphasis"]
    from fmbridge.errors import OpError
    with pytest.raises(OpError):
        run_op("perf.analyze_audio", wav=str(tmp_path / "missing.wav"))


SPEC = {"kind": "performance", "version": 1, "name": "demo", "sequence": "/Game/S/Seq", "actor": "Host",
        "targets": {"desk": [300, 100, 80]}, "library": {"idle": ["/Game/A/idle"]},
        "lines": [{"id": "l1", "face_anim": "/Game/S/AS_talk", "mood": "warm",
                   "gaze": [{"at_s": 0, "target": {"yaw": 0, "pitch": 0}, "scan": "lens"}, {"at_s": 2, "target": "desk"}]},
                  {"id": "l2", "duration_s": 1.5, "listen": True}]}


def _record_seq_ops(monkeypatch):
    """seq.* is WP8's: record the calls perf.compose makes instead of running them on the fake's stubs."""
    from fmbridge import ops
    calls = []
    for name in ("seq.new", "seq.anim", "seq.key_transform"):
        monkeypatch.setitem(ops._OPS, name, (lambda n: (lambda **kw: calls.append((n, kw)) or {"ok": True}))(name))
    return calls


def test_perf_spec_state_plan_compose_and_converge(ue, monkeypatch):
    ue.metahuman("Host")
    talk(ue)
    ue.anim("/Game/A/idle", length_s=8, skeleton="/Game/MH/Body/BodyMesh_Skeleton")
    st = run_op("perf.state", spec=SPEC)
    assert st["actor"]["face_mesh"] == "/Game/MH/Face/FaceMesh" and st["actor"]["head_z_cm"] == 165.0
    assert st["clips"]["/Game/S/AS_talk"]["length_s"] == pytest.approx(4.0) and st["targets"]["desk"] == [300, 100, 80]
    p = run_op("perf.plan", spec=SPEC)
    assert [s["op"] for s in p["steps"]] == ["perf.compose"] and p["missing"] == []
    calls = _record_seq_ops(monkeypatch)
    r = run_op("perf.apply", spec=SPEC)
    assert r["converged"] and [x["op"] for x in r["ran"]] == ["perf.compose"]
    face = ue.assets["/Game/Perf/demo/AS_demo_face"]
    cur = face._data["curves"]
    assert "CTRL_expressions_jawOpen" in cur and "HeadYaw" in cur and "CTRL_expressions_eyeBlinkL" in cur
    # the line's lip-sync is placed at its time and closes after the line
    t, v = cur["CTRL_expressions_jawOpen"]
    assert t[-1] == pytest.approx(4.0 + 1 / 120) and v[-1] == 0.0
    ops_called = [c[0] for c in calls]
    assert ops_called[0] == "seq.new" and ops_called.count("seq.anim") == 2
    face_call = next(kw for n, kw in calls if n == "seq.anim" and kw["component"] == "Face")
    assert face_call["sections"][0]["anim"] == "/Game/Perf/demo/AS_demo_face"
    assert r["report"]["pass"] or set(r["report"]["failed"]) <= {"expression_range"}
    # a second apply does nothing: the fingerprint matches
    calls.clear()
    r2 = run_op("perf.apply", spec=SPEC)
    assert r2["converged"] and r2["ran"] == [] and calls == []


def test_perf_spec_errors_are_actionable(ue):
    from fmbridge.errors import OpError
    bad = dict(SPEC, lines=[{"id": "x", "mood": "warm"}])
    with pytest.raises(OpError) as e:
        run_op("perf.plan", spec=bad)
    assert e.value.code == "bad_args" and "needs audio, face_anim or duration_s" in str(e.value)


def test_perf_turn_to_keys_the_short_way(ue, monkeypatch):
    ue.metahuman("Host", yaw=170.0)
    ue.add_asset("/Game/S/Seq", "LevelSequence")
    import fmbridge.ops.seq as seq
    monkeypatch.setattr(seq, "_fps", lambda s: 24.0)
    calls = _record_seq_ops(monkeypatch)
    r = run_op("perf.turn_to", sequence="/Game/S/Seq", label="Host", target=-170.0, at_frame=24)
    assert r["yaw"] == [170.0, 190.0]
    keys = calls[0][1]["keys"]
    assert keys[0][0] == 0 and keys[-1][2]["yaw"] == pytest.approx(190.0)


def test_perf_face_and_plot_write_a_png(ue, tmp_path):
    talk(ue)
    r = run_op("perf.face", anim="/Game/S/AS_talk", plot=str(tmp_path / "f.png"))
    assert r["plot"]["width"] == 1200 and (tmp_path / "f.png").stat().st_size > 1000
    p = run_op("perf.plot", anim="/Game/S/AS_talk_perf", out=str(tmp_path / "g.png"), t0_s=1.0, t1_s=3.0)
    assert p["changed"] and (tmp_path / "g.png").exists()


def test_perf_apply_solves_spoken_lines_then_converges(ue, fmb, monkeypatch, tmp_path):
    """The whole loop with audio: perf.solve per line (speech.to_face on the fake's MetaHuman Animator), compose,
    and a second apply that does nothing; then a changed mood re-solves only that line."""
    ue.metahuman("Host")
    w1, w2 = wav(tmp_path / "l1.wav", 2.0), wav(tmp_path / "l2.wav", 1.5)
    spec = {"kind": "performance", "version": 1, "name": "spoken", "sequence": "/Game/S/Seq2", "actor": "Host",
            "lines": [{"id": "l1", "audio": w1, "mood": "confident", "gaze": [{"at_s": 0, "target": {"yaw": 0}}]},
                      {"id": "l2", "audio": w2, "mood": "warm"}]}
    calls = _record_seq_ops(monkeypatch)
    r = run_op("perf.apply", spec=spec)
    assert r["converged"] and [x["op"] for x in r["ran"]] == ["perf.solve", "perf.solve", "perf.compose"]
    face = ue.assets["/Game/Perf/spoken/AS_spoken_face"]._data["curves"]
    t, v = face["CTRL_expressions_jawOpen"]
    assert t[0] < 0.05 and max(t) > 2.3  # both lines' lip-sync placed, the second after the first
    assert ue.dialogs == []
    assert run_op("perf.apply", spec=spec)["ran"] == []
    spec["lines"][1]["mood"] = "sad"
    r = run_op("perf.apply", spec=spec)
    assert [x["op"] for x in r["ran"]] == ["perf.solve", "perf.compose"]
    assert calls


def _face_mesh(ue):
    return ue.skeletal_mesh("/Game/MH/Face/FaceMesh", FACE_SKEL)


def test_speech_to_face_solves_or_says_why(ue, fmb, tmp_path):
    from fmbridge.errors import OpError
    _face_mesh(ue)
    w = wav(tmp_path / "l.wav", 3.0)
    r = run_op("speech.to_face", wav=w, name="l", face_mesh="/Game/MH/Face/FaceMesh")
    assert r["anim"] == "/Game/Speech/Anim/AS_l" and r["chunks"] == 1 and not r["fallback"]
    with pytest.raises(OpError) as e:
        run_op("speech.to_face", wav=str(tmp_path / "nope.wav"), name="x", face_mesh="/Game/MH/Face/FaceMesh")
    assert e.value.code == "not_found" and "push" in e.value.hint
    ue.mh_solve = "NO_FRAMES"
    with pytest.raises(OpError) as e:
        run_op("speech.to_face", wav=w, name="l2", face_mesh="/Game/MH/Face/FaceMesh", fallback=False)
    assert e.value.code == "engine" and "NO_FRAMES" in e.value.message and e.value.hint
    r = run_op("speech.to_face", wav=w, name="l3", face_mesh="/Game/MH/Face/FaceMesh")
    assert r["fallback"] and r["errors"] and ue.assets["/Game/Speech/Anim/AS_l3"]._data["curves"]["CTRL_expressions_jawOpen"]
    ue.mh_solve = "hang"
    with pytest.raises(OpError) as e:
        run_op("speech.to_face", wav=w, name="l4", face_mesh="/Game/MH/Face/FaceMesh", fallback=False, timeout_s=0.0001)
    assert e.value.code == "timeout"
    assert ue.dialogs == []


def test_speech_to_face_chunks_long_audio(ue, fmb, tmp_path):
    _face_mesh(ue)
    w = wav(tmp_path / "long.wav", 25.0)  # phrases of 0.7 s, pauses of 0.3 s every second
    r = run_op("speech.to_face", wav=w, name="long", face_mesh="/Game/MH/Face/FaceMesh", max_chunk_s=10.0)
    assert r["chunks"] == 3 and not r["fallback"]
    a = ue.assets["/Game/Speech/Anim/AS_long"]
    t, _ = a._data["curves"]["CTRL_expressions_jawOpen"]
    assert t[0] < 0.1 and t[-1] > 24.0 and t == sorted(t)  # three solves stitched end to end
    assert a.length_s == pytest.approx(25.0, abs=0.1)
    assert [p for p in ue.assets if p.startswith("/Game/Speech/Chunks/Anim/AS_long_c")] == [
        f"/Game/Speech/Chunks/Anim/AS_long_c0{k}" for k in range(3)]


def test_gaze_lock_reads_both_section_offsets(ue, fmb):
    """gaze_lock maps sequence frames to seconds into the animation with StartFrameOffset + FirstLoopStartFrameOffset
    (the engine sums them); seq.anim writes the clip offset to StartFrameOffset."""
    import unreal
    from fmbridge.ops.anim import section_offset_s
    p = unreal.MovieSceneSkeletalAnimationParams()
    p.set_editor_property("start_frame_offset", unreal.FrameNumber(12000))   # 0.5 s at 24000 ticks/s
    p.set_editor_property("first_loop_start_frame_offset", unreal.FrameNumber(0))
    assert section_offset_s(p, 24000.0) == pytest.approx(0.5)
    p.set_editor_property("first_loop_start_frame_offset", unreal.FrameNumber(6000))
    assert section_offset_s(p, 24000.0) == pytest.approx(0.75)
    assert section_offset_s(None, 24000.0) == 0.0


def test_body_life_needs_calibration_then_bakes_an_additive(ue, fmb, tmp_path, monkeypatch):
    import json as _json
    from fmbridge.errors import OpError
    import fmbridge.ops.perf_body as PB
    ue.skeletal_mesh("/Game/MH/Body/BodyMesh", "/Game/MH/Body/BodyMesh_Skeleton")
    monkeypatch.setattr(PB, "_saved", lambda name: str(tmp_path / name))
    with pytest.raises(OpError) as e:
        run_op("anim.body_life", out="/Game/P/AS_life", body_mesh="/Game/MH/Body/BodyMesh", length_s=4)
    assert e.value.code == "conflict" and "calibrate_body" in e.value.hint
    ref = {b: {"t": [0, 0, 10], "q": [0, 0, 0, 1], "s": [1, 1, 1]} for b in PB.BONES}
    axes = {b: {"flex": ["y", 1.0], "side": ["x", 1.0], "twist": ["z", 1.0]} for b in PB.BONES}
    (tmp_path / "body_BodyMesh_Skeleton.json").write_text(_json.dumps(
        {"skeleton": "/Game/MH/Body/BodyMesh_Skeleton", "axes": axes, "shift_axis": ["y", 1.0], "ref": ref}))
    r = run_op("anim.body_life", out="/Game/P/AS_life", body_mesh="/Game/MH/Body/BodyMesh", length_s=4, state="nervous")
    a = ue.assets["/Game/P/AS_life"]
    assert r["bones"] == sorted(PB.BONES) and a._data["bones"] == set(PB.BONES)
    assert "AAT_LOCAL_SPACE_BASE" in str(a._props["additive_anim_type"])
    assert "ABPT_LOCAL_ANIM_FRAME" in str(a._props["ref_pose_type"]) and r["breaths_per_min"] > 18


def test_spec_body_life_layers_an_additive_or_notes_why_not(ue, fmb, monkeypatch, tmp_path):
    import json as _json
    import fmbridge.ops.perf_body as PB
    ue.metahuman("Host")
    talk(ue)
    monkeypatch.setattr(PB, "_saved", lambda name: str(tmp_path / name))
    calls = _record_seq_ops(monkeypatch)
    spec = dict(SPEC, character={"body_life": {"state": "calm", "follow": 0.2}})
    r = run_op("perf.compose", spec=spec)
    assert any(n.get("skipped") == "body_life" for n in r["notes"])  # not calibrated: applied without it
    ref = {b: {"t": [0, 0, 10], "q": [0, 0, 0, 1], "s": [1, 1, 1]} for b in PB.BONES}
    axes = {b: {"flex": ["y", 1.0], "side": ["x", 1.0], "twist": ["z", 1.0]} for b in PB.BONES}
    (tmp_path / "body_BodyMesh_Skeleton.json").write_text(_json.dumps({"axes": axes, "shift_axis": None, "ref": ref}))
    calls.clear()
    run_op("perf.compose", spec=spec)
    body = next(kw for n, kw in calls if n == "seq.anim" and kw["component"] == "Body")
    assert body["sections"][-1]["anim"] == "/Game/Perf/demo/AS_demo_face_life"


def test_rig_keys_makes_the_track_and_finds_it_by_binding(ue, fmb, monkeypatch):
    """Day-1 (pose): the track was made but never found again, because the binding ids were compared with str(),
    which carries each struct wrapper's address. The fake's proxies now hand out a new Guid wrapper per read."""
    ue.spawn("SkeletalMeshActor", "Host")
    ue.pose("Host", {"head": [0, 0, 160]})
    ue.add_asset("/Game/T/Seq", "LevelSequence")
    CR = ue.ControlRigSequencerLibrary
    CR.classes["MetaHuman_ControlRig_C"] = {"CTRL_neck": "head"}
    monkeypatch.setattr(ue.EditorAssetLibrary, "load_blueprint_class",
                        staticmethod(lambda p: type("MetaHuman_ControlRig_C", (), {})), raising=False)
    r = run_op("anim.rig_keys", sequence="/Game/T/Seq", label="Host", keys={},
               rig_class="/MetaHumanCharacter/Common/MetaHuman_ControlRig")
    assert r["controls"] == 0 and len(CR.rigs) == 1
    r = run_op("anim.rig_controls", sequence="/Game/T/Seq", label="Host")
    assert r["controls"] == ["CTRL_neck"]
    run_op("anim.rig_keys", sequence="/Game/T/Seq", label="Host", keys={},
           rig_class="/MetaHumanCharacter/Common/MetaHuman_ControlRig")
    assert len(CR.rigs) == 1  # found again, not made twice
