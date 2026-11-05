"""camkit (unreal/fmbridge/camkit): the camera maths, without an engine. camkit imports nothing from `unreal`, so it
is imported here straight from its folder."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "unreal" / "fmbridge"))

from camkit import checks, framing, geo, lens, moves  # noqa: E402


def person(name="P", at=(0.0, 0.0), facing=(1.0, 0.0, 0.0), height=175.0):
    return framing.subject_from_bounds(name, (at[0], at[1], height / 2), (20, 20, height / 2), facing)


# --- geo --------------------------------------------------------------------------------------------------------

def test_axes_match_unreal_rotation_matrix():
    f, r, u = geo.axes({"yaw": 90})
    assert f == pytest.approx((0, 1, 0), abs=1e-9)  # yaw 90 looks along +Y
    assert r == pytest.approx((-1, 0, 0), abs=1e-9)
    assert u == pytest.approx((0, 0, 1), abs=1e-9)
    f, r, u = geo.axes({"pitch": 90})
    assert f == pytest.approx((0, 0, 1), abs=1e-9)
    f, r, u = geo.axes({"roll": 90})
    assert r == pytest.approx((0, 0, -1), abs=1e-9)  # FRotationMatrix Y row: -SR*CP


def test_look_at_and_unwrap():
    r = geo.look_at((0, 0, 0), (100, 100, 100 * math.sqrt(2)))
    assert r["yaw"] == pytest.approx(45)
    assert r["pitch"] == pytest.approx(45)
    assert geo.unwrap(170, -170) == pytest.approx(190)
    assert geo.wrap180(-180) == 180 and geo.wrap180(360) == 0


# --- lens -------------------------------------------------------------------------------------------------------

def test_presets_and_fov():
    assert lens.filmback("16:9 digital film") == (23.76, 13.365)
    assert lens.filmback("super 16") == (12.52, 7.58)
    with pytest.raises(ValueError, match="one of"):
        lens.filmback("Super 99")
    # 50 mm on a 36 mm wide back: 39.6 deg
    assert lens.hfov(50, "16:9 DSLR") == pytest.approx(39.5978, abs=1e-3)
    assert lens.focal_for_hfov(lens.hfov(35)) == pytest.approx(35)
    assert lens.equivalent_focal(50, "16:9 DSLR", "16:9 Digital Film") == pytest.approx(33.0, abs=0.01)
    assert lens.snap(47) == 50


def test_projection_round_trip_and_edges():
    cam = lens.camera((0, 0, 100), {"pitch": -5, "yaw": 30, "roll": 3}, 40)
    p = lens.unproject(cam, 0.2, 0.7, 500)
    q = lens.project(cam, p)
    assert (q["u"], q["v"], q["depth"]) == pytest.approx((0.2, 0.7, 500))
    flat = lens.camera((0, 0, 0), {}, 50, "16:9 DSLR")
    # the frame's right edge at 1000 cm: half-width 36/2 mm -> 1000 * 18 / 50 = 360 cm right (+Y)
    assert lens.project(flat, (1000, 360, 0))["u"] == pytest.approx(1.0)
    assert lens.project(flat, (1000, 0, 1000 * 10.125 / 50))["v"] == pytest.approx(0.0)
    assert not lens.project(flat, (-10, 0, 0))["visible"]


def test_dof():
    d = lens.dof(50, 2.8, 300, "16:9 Digital Film")
    assert d["near"] < 300 < d["far"]
    assert lens.dof(24, 16, 300)["far"] is None  # beyond the hyperfocal distance: sharp to infinity
    assert lens.aperture_for_depth(50, 300, 280, 330) >= 2.8


# --- framing ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("size", framing.ORDER)
@pytest.mark.parametrize("angle", [0, "3/4", "profile"])
def test_solver_hits_its_anchors(size, angle):
    s = person()
    r = framing.solve(s, size, angle=angle, focal=50)
    assert r["error"] < 1e-5
    spec = framing.SIZES[size]
    top = lens.project(r["camera"], framing.anchor_point(s, spec["top"][0]))
    bottom = lens.project(r["camera"], framing.anchor_point(s, spec["bottom"][0]))
    assert top["v"] == pytest.approx(spec["top"][1], abs=1e-4)
    assert bottom["v"] == pytest.approx(spec["bottom"][1], abs=1e-4)
    assert framing.classify(r["camera"], s)["size"] == size


def test_sizes_widen_monotonically():
    s = person()
    ds = [framing.solve(s, k, focal=50)["distance"] for k in framing.ORDER]
    assert ds == sorted(ds)


def test_side_and_lead_room():
    s = person()  # faces +X; its left is -Y
    left = framing.solve(s, "MCU", angle="3/4", side="left", focal=50)
    assert left["camera"]["loc"][1] < 0 and left["camera"]["loc"][0] > 0
    right = framing.solve(s, "MCU", angle="3/4", side="right", focal=50)
    assert right["camera"]["loc"][1] > 0
    # from its left the subject looks toward frame left: it sits on the right third, room ahead
    assert left["predicted"]["P"]["eyes"][0] == pytest.approx(2 / 3, abs=1e-3)
    assert right["predicted"]["P"]["eyes"][0] == pytest.approx(1 / 3, abs=1e-3)
    front = framing.solve(s, "MCU", angle="front", focal=50)
    assert front["predicted"]["P"]["eyes"][0] == pytest.approx(0.5, abs=1e-4)


def test_fixed_distance_solves_focal_and_snaps():
    s = person()
    r = framing.solve(s, "MCU", angle=30, distance=200, focal=None)
    assert r["error"] < 1e-5 and 30 < r["focal"] < 70
    snapped = framing.solve(s, "MCU", angle=30, distance=200, focal=None, snap_focal=True)
    assert snapped["focal"] in lens.PRIMES


def test_heights_and_dutch():
    s = person()
    hi = framing.solve(s, "MS", height="high", focal=35)
    lo = framing.solve(s, "MS", height="low", focal=35)
    eye_z = s["points"]["eyes"][2]
    assert hi["camera"]["loc"][2] > eye_z > lo["camera"]["loc"][2]
    assert hi["camera"]["rot"]["pitch"] < 0 < lo["camera"]["rot"]["pitch"]
    hip = framing.solve(s, "WS", height="hip", focal=35)
    assert hip["camera"]["loc"][2] == pytest.approx(s["points"]["hips"][2])
    d = framing.solve(s, "MCU", dutch=12, focal=50)
    assert d["error"] < 1e-5 and d["camera"]["rot"]["roll"] == 12
    worm = framing.solve(s, "CU", height="worm", focal=24)
    assert any("floor" in w for w in worm["warnings"]) or worm["camera"]["loc"][2] > 10


def test_group_fits_across():
    a, b = person("A", (0, -90), (0, 1, 0)), person("B", (0, 90), (0, -1, 0))
    r = framing.solve([a, b], "MS", angle=90, side="right", focal=35)  # A's right is -X: the camera at -X
    us = [r["predicted"][n][k][0] for n in "AB" for k in ("eyes", "shoulders")]
    assert min(us) >= 0.06 - 1e-3 and max(us) <= 0.94 + 1e-3
    assert r["camera"]["loc"][0] < 0


def test_subject_from_bones_mannequin_and_metahuman():
    bones = {"head": (0, 0, 160), "neck_01": (0, 0, 150), "clavicle_l": (0, -15, 145), "clavicle_r": (0, 15, 145),
             "spine_04": (0, 0, 128), "spine_01": (0, 0, 108), "pelvis": (0, 0, 95), "calf_l": (0, -10, 50),
             "calf_r": (0, 10, 50), "foot_l": (0, -10, 9), "foot_r": (0, 10, 9),
             "FACIAL_L_Eye": (8, -3.2, 168), "FACIAL_R_Eye": (8, 3.2, 168)}
    s = framing.subject_from_bones("MH", bones)
    assert s["facing"] == pytest.approx([1, 0, 0])  # the right eye at +Y: it faces +X
    assert s["points"]["feet"][2] == pytest.approx(1)
    assert s["points"]["head_top"][2] == pytest.approx(168 + framing.CROWN_ABOVE_EYES)
    no_face = {k: v for k, v in bones.items() if not k.startswith("FACIAL")}
    s2 = framing.subject_from_bones("Manny", no_face)
    assert s2["facing"] == pytest.approx([1, 0, 0])  # from the clavicles
    with pytest.raises(ValueError, match="bounds"):
        framing.subject_from_bones("Box", {"foo": (0, 0, 0)})


def test_size_and_angle_names():
    assert framing.size_key("close-up") == "CU" and framing.size_key("ms") == "MS"
    assert framing.size_key("full") == "WS"
    with pytest.raises(ValueError, match="ECU"):
        framing.size_key("medium-ish")
    assert framing.angle_deg("3/4") == 45 and framing.angle_deg("three-quarter back") == 135


# --- moves ------------------------------------------------------------------------------------------------------

def _cam(d=300.0):
    return lens.camera((d, 0, 160), geo.look_at((d, 0, 160), (0, 0, 160)), 35)


def test_ease_curves():
    for k in moves.EASES:
        assert moves.ease(0, k) == pytest.approx(0) and moves.ease(1, k) == pytest.approx(1)
    assert moves.ease(0.5, "in") < 0.5 < moves.ease(0.5, "out")


def test_push_in_and_orbit_keep_aim():
    aim = (0, 0, 160)
    r = moves.plan(_cam(), [{"move": "push_in", "fraction": 0.5, "frames": 24},
                            {"move": "orbit", "degrees": 90, "frames": 24}], step=4, aim=aim)
    first, mid, last = r["keys"][0], r["keys"][6], r["keys"][-1]
    assert mid["frame"] == 24 and mid["loc"][0] == pytest.approx(150, abs=0.01)
    assert last["loc"][1] == pytest.approx(-150, abs=0.01) and last["loc"][0] == pytest.approx(0, abs=0.01)
    for k in r["keys"]:  # the aim point stays at frame centre
        p = lens.project({**k, "filmback": lens.filmback(None)}, aim)
        assert (p["u"], p["v"]) == pytest.approx((0.5, 0.5), abs=1e-4)  # keys are rounded to 1e-3 cm, 1e-4 deg


def test_dolly_zoom_holds_subject_size():
    aim = (0, 0, 160)
    r = moves.plan(_cam(), [{"move": "dolly_zoom", "focal": 85, "frames": 24}], step=6, aim=aim)
    hs = [lens.frame_height_at({**k, "filmback": lens.filmback(None)}, lens.view(k, aim)[0]) for k in r["keys"]]
    assert max(hs) - min(hs) < 1e-3
    assert r["keys"][-1]["focal"] == pytest.approx(85)


def test_noise_is_deterministic_and_small():
    a = moves.plan(_cam(), [{"move": "hold", "frames": 48}], noise={"preset": "handheld", "seed": 3}, step=2)
    b = moves.plan(_cam(), [{"move": "hold", "frames": 48}], noise={"preset": "handheld", "seed": 3}, step=2)
    c = moves.plan(_cam(), [{"move": "hold", "frames": 48}], noise={"preset": "handheld", "seed": 4}, step=2)
    assert a["keys"] == b["keys"] != c["keys"]
    assert len(a["keys"]) == 25
    assert all(abs(k["loc"][2] - 160) < 3 for k in a["keys"])


def test_whip_rack_zoom_and_errors():
    r = moves.plan(_cam(), [{"move": "whip", "degrees": 90, "frames": 8},
                            {"move": "rack", "to": 500, "frames": 12},
                            {"move": "zoom", "focal": 70, "frames": 12}], step=1)
    assert r["keys"][8]["rot"]["yaw"] == pytest.approx(270)  # 180 + 90, unwrapped
    assert r["keys"][-1]["focus"] == pytest.approx(500) and r["keys"][-1]["focal"] == pytest.approx(70)
    with pytest.raises(ValueError, match="aim"):
        moves.plan(_cam(), [{"move": "orbit", "degrees": 30}])
    with pytest.raises(ValueError, match="unknown move"):
        moves.plan(_cam(), [{"move": "barrel_roll"}])
    sk = moves.sequencer_keys(r["keys"])
    assert len(sk["transform"]) == len(r["keys"]) and len(sk["focal"]) > 1


def test_crane_rises_and_follow_focus():
    aim = (0, 0, 160)
    r = moves.plan(_cam(), [{"move": "crane", "rise": 200, "frames": 24}], aim=aim, focus_on=aim, step=12)
    assert r["keys"][-1]["loc"][2] == pytest.approx(360)
    assert r["keys"][-1]["rot"]["pitch"] < -30
    assert r["keys"][-1]["focus"] == pytest.approx(lens.view(r["keys"][-1], aim)[0], abs=0.01)


# --- checks -----------------------------------------------------------------------------------------------------

def test_line_and_jump_cut():
    a, b = person("A", (0, -90), (0, 1, 0)), person("B", (0, 90), (0, -1, 0))
    one = framing.solve(a, "MCU", angle=40, side="right", focal=50)["camera"]   # on A's right: -X side
    two = framing.solve(b, "MCU", angle=40, side="left", focal=50)["camera"]    # B's left is -X too
    crossed = framing.solve(b, "MCU", angle=40, side="right", focal=50)["camera"]
    assert not [i for i in checks.cut(one, two, [a, b], "MCU", "MCU") if i["code"] == "shot.line_180"]
    bad = checks.cut(one, crossed, [a, b], "MCU", "MCU")
    assert any(i["code"] == "shot.line_180" and i["severity"] == "fail" for i in bad)
    near = framing.solve(a, "MS", angle=40, side="right", focal=50)["camera"]
    assert any(i["code"] == "shot.rule_30" for i in checks.cut(one, near, [a], "MCU", "MS"))
    assert not checks.cut(one, framing.solve(a, "WS", angle=40, side="right", focal=50)["camera"], [a])


def test_focus_occlusion_and_dutch():
    a = person("A")
    r = framing.solve(a, "MCU", focal=85)
    cam = {**r["camera"], "aperture": 1.4, "focus": r["focus"] + 80}
    assert any(i["code"] == "cam.focus" and i["severity"] == "fail" for i in checks.frame(cam, [a]))
    assert not checks.frame({**cam, "focus": r["focus"]}, [a])
    blocker = person("B", at=(r["camera"]["loc"][0] / 2, 0))
    assert any(i["code"] == "cam.occlusion" for i in checks.frame(r["camera"], [a], others=[blocker]))
    assert any(i["code"] == "cam.horizon" for i in checks.frame({**r["camera"], "rot": {**r["camera"]["rot"], "roll": 2}},
                                                             [a]))
    assert checks.worst([]) == "pass"


# --- shot list ----------------------------------------------------------------------------------------------------

from camkit import shotlist  # noqa: E402


def _spec(**kw):
    base = {"kind": "shot", "version": 1, "name": "t", "sequence": "/Game/T/Seq", "fps": 24,
            "subjects": {"A": {"actor": "A"}, "B": {"actor": "B"}},
            "shots": [{"id": "S1", "frame": {"subjects": ["A"], "size": "MCU"}}]}
    return {**base, **kw}


def test_times_frames_seconds_marks():
    marks = {"L1": (24, 72), "L1.w2": (40, 50)}
    assert shotlist.parse_time(48, 24, marks) == 48
    assert shotlist.parse_time("2.5s", 24, marks) == 60
    assert shotlist.parse_time("12f", 24, marks) == 12
    assert shotlist.parse_time("L1", 24, marks) == 24
    assert shotlist.parse_time("L1.end-6f", 24, marks) == 66
    assert shotlist.parse_time("L1.start+0.5s-2f", 24, marks) == 34
    assert shotlist.parse_time("L1.w2.end", 24, marks) == 50
    with pytest.raises(ValueError, match="no line or shot 'L9'"):
        shotlist.parse_time("L9.start", 24, marks)


def test_timing_document_lines_rescaled():
    timing = {"kind": "audio", "version": 1, "fps": 30, "lines": [
        {"id": "L1", "speaker": "A", "start_frame": 30, "end_frame": 90,
         "words": [{"w": "hi", "start_frame": 33, "end_frame": 45}]}]}
    ls = shotlist.lines_of(_spec(timing=timing))
    assert ls[0]["start"] == 24 and ls[0]["end"] == 72 and ls[0]["words"] == [[26, 36]]
    times = shotlist.resolve_times(_spec(timing=timing, shots=[
        {"id": "S1", "start": 0, "frame": {"subjects": ["A"]}},
        {"id": "S2", "start": "L1.w0.start-2f", "frame": {"subjects": ["A"]}}]))
    assert times == [{"id": "S1", "start": 0, "end": 24}, {"id": "S2", "start": 24, "end": 96}]


def test_overlap_and_unknown_keys_are_reported():
    errs = shotlist.validate(_spec(shots=[{"id": "S1", "frame": {"subjects": ["A"], "sise": "MCU"}, "zoom": 3}]))
    assert {e["path"] for e in errs} == {"shots[0].frame.sise", "shots[0].zoom"}
    with pytest.raises(shotlist.SpecError, match="inside S1"):
        shotlist.resolve_times(_spec(shots=[{"id": "S1", "start": 0, "end": 48, "frame": {"subjects": ["A"]}},
                                            {"id": "S2", "start": 40, "frame": {"subjects": ["A"]}}]))


def test_plan_auto_edit_cuts_on_speakers():
    a, b = person("A", (0, -90), (0, 1, 0)), person("B", (0, 90), (0, -1, 0))
    spec = _spec(shots=[], auto={"from_lines": True, "lead_frames": 4},
                 lines=[{"id": "L1", "speaker": "A", "start_s": 1, "end_s": 2},
                        {"id": "L2", "speaker": "A", "start_s": 2.2, "end_s": 3},
                        {"id": "L3", "speaker": "B", "start_s": 3.5, "end_s": 5}])
    r = shotlist.plan(spec, {"A": a, "B": b})
    assert [c[0] for c in r["cuts"]] == ["CAM_auto_master", "CAM_auto_L1", "CAM_auto_L3"]
    assert [c[1] for c in r["cuts"]] == [0, 20, 80]
    assert r["range"] == [0, 144]  # the last line's end + 1 s
    assert not [i for i in r["issues"] if i["code"] == "shot.line_180"]


def test_plan_moves_focus_and_group_split_focus():
    a, b = person("A", (0, -90), (0, 1, 0)), person("B", (0, 90), (0, -1, 0))
    spec = _spec(shots=[
        {"id": "S1", "duration": 48, "frame": {"subjects": ["A", "B"], "size": "MS", "angle": 0, "focal_mm": 35}},
        {"id": "S2", "duration": "2s", "frame": {"subjects": ["A"], "size": "MCU", "angle": 30, "side": "right"},
         "moves": [{"move": "push_in", "fraction": 0.2}], "noise": "subtle"}])
    r = shotlist.plan(spec, {"A": a, "B": b})
    s1, s2 = r["shots"]
    near, far = (lens.view(s1["start_camera"], x["points"]["eyes"])[0] for x in (a, b))
    assert s1["start_camera"]["focus"] == pytest.approx(2 * near * far / (near + far))
    assert s2["keys"][0]["frame"] == 48 and s2["keys"][-1]["frame"] == 96
    assert s2["keys"][-1]["focus"] < s2["keys"][0]["focus"]  # pushed in: the follow-focus came closer


# --- words --------------------------------------------------------------------------------------------------------

from camkit import words  # noqa: E402


def test_parse_sentences():
    p = words.parse("medium close-up of Host from 30 degrees left at eye level, 50mm f/2.8", ["Host", "Guest"])
    assert {k: p[k] for k in ("size", "angle", "side", "height", "focal_mm", "aperture", "subjects")} == {
        "size": "MCU", "angle": 30.0, "side": "left", "height": "eye", "focal_mm": 50.0, "aperture": 2.8,
        "subjects": ["Host"]}
    assert p["unparsed"] == []
    p = words.parse("Two-shot of Guest and Host, low angle, 35mm, dutch", ["Host", "Guest"])
    assert p["subjects"] == ["Guest", "Host"] and p["size"] == "MS" and p["height"] == "low" and p["dutch_deg"] == 12
    p = words.parse("CU of Guest from 3/4 right, 2 m away", ["Guest"])
    assert p["angle"] == 45 and p["side"] == "right" and p["distance_cm"] == 200
    assert words.solver_args(p)["focal"] is None  # the focal length is solved
    p = words.parse("wide of Host from behind, bird's eye, wobbly", ["Host"])
    assert p["size"] == "WS" and p["angle"] == 180 and p["height"] == "overhead" and p["unparsed"] == ["wobbly"]
    p = words.parse("ECU of Host, profile left, slightly low, right third", ["Host"])
    assert (p["size"], p["angle"], p["side"], p["height"], p["place"]) == ("ECU", 90, "left", "slight low",
                                                                             "right third")


@pytest.mark.parametrize("size", ["CU", "MCU", "MS", "WS"])
@pytest.mark.parametrize("angle,side,height", [(0, "left", "eye"), (41, "left", "eye"), (70, "right", "high"),
                                               (30, "right", "slight low"), (55, "left", 33.0),
                                               (20, "right", -7.0)])
def test_words_round_trip(size, angle, side, height):
    s = person("Host")
    r = framing.solve(s, size, angle=angle, side=side, height=height, focal=50, aperture=2.8)
    text = words.describe({**r["camera"], "aperture": 2.8}, [s])
    back = words.parse(text, ["Host"])
    r2 = framing.solve(s, back["size"], **{k: v for k, v in words.solver_args(back).items() if k != "size"})
    assert back["size"] == size, text
    assert r2["camera"]["loc"] == pytest.approx(r["camera"]["loc"], abs=2.0), text
    assert r2["camera"]["focal"] == pytest.approx(50)
