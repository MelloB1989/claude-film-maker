"""R5 T4: qa/hair.py (hair continuity across cuts, pops) and qa/gate.py (the review gate v2), no editor."""
import json
import os

from _qa_load import load

load()
hair = __import__("fmqa.hair", fromlist=["hair"])
gate = __import__("fmqa.gate", fromlist=["gate"])
image = __import__("fmqa.image", fromlist=["image"])

DATA = os.path.join(os.path.dirname(__file__), "data")


def _mask(w, h, x0, y0, x1, y1):
    m = bytearray(w * h)
    for y in range(y0, y1):
        for x in range(x0, x1):
            m[y * w + x] = 1
    return m


def _hair(w, h, head_v, chest_v, top, bottom, x0=40, x1=60):
    return hair.mask_stats(_mask(w, h, x0, top, x1, bottom), w, h, head_v=head_v, chest_v=chest_v)


def test_reach_is_zoom_free():
    # close shot: head at row 20, chest at row 60 (unit 40 px), hair falls to row 60 -> reach 1.0
    close = _hair(100, 100, 0.20, 0.60, 5, 61)
    # wide shot: everything half the size, same hair
    wide = _hair(100, 100, 0.20, 0.40, 12, 41, 45, 55)
    assert close["norm"] == wide["norm"] == "bones"
    assert abs(close["reach"] - 1.0) < 0.03 and abs(wide["reach"] - 1.0) < 0.06
    assert abs(close["area"] - wide["area"]) / close["area"] < 0.15


def test_cut_shortening_fails_and_steady_passes():
    cuts = [["S17", 0, 10], ["S18", 10, 20]]
    long_ = {f: _hair(100, 100, 0.2, 0.6, 5, 61) for f in range(0, 10)}
    short = {f: _hair(100, 100, 0.2, 0.4, 12, 34, 45, 55) for f in range(10, 20)}  # wide, hair ends at 0.7 units
    r = hair.judge({**long_, **short}, cuts, "Presenter")
    assert not r["pass"]
    jump = [i for i in r["issues"] if i["code"] == "hair.cut_jump"]
    assert jump and jump[0]["frame"] == 10 and "SHORTER" in jump[0]["message"] and "groom.lock" in jump[0]["fix"]
    same = {f: _hair(100, 100, 0.2, 0.4, 12, 41, 45, 55) for f in range(10, 20)}  # wide, same hair
    ok = hair.judge({**long_, **same}, cuts, "Presenter")
    assert ok["pass"], ok["issues"]
    assert ok["cuts"][0]["reach"][2] < 0.12


def test_pop_inside_a_shot():
    s = {f: _hair(100, 100, 0.2, 0.6, 5, 61) for f in range(0, 6)}
    s.update({f: _hair(100, 100, 0.2, 0.6, 5, 48) for f in range(6, 10)})
    r = hair.judge(s, [["S17", 0, 10]], "Presenter")
    assert [p["frame"] for p in r["pops"]] == [6] and not r["pass"]


def test_character_not_in_both_shots_is_not_judged():
    s = {f: _hair(100, 100, 0.2, 0.6, 5, 61) for f in range(0, 10)}
    r = hair.judge(s, [["S17", 0, 10], ["V01", 10, 20]], "Presenter")
    assert r["pass"] and r["cuts"] == []


def test_width_norm_warns():
    s = {f: hair.mask_stats(_mask(100, 100, 40, 5, 60, 61), 100, 100) for f in range(4)}
    r = hair.judge(s, [["S17", 0, 4]], "Presenter")
    assert r["pass"] and any(i["code"] == "hair.norm_width" for i in r["issues"])


def test_luma_mask_box_only():
    img = image.solid(40, 20, (200, 200, 200))
    for y in range(4, 16):
        for x in range(2, 38):
            img.put(x, y, (10, 10, 10))
    m, w, h = hair.luma_mask(img, [0.25, 0.0, 0.75, 1.0])
    assert (w, h) == (40, 20)
    assert sum(m) == 12 * 20  # dark rows 4..15, columns 10..29 only
    assert hair.mask_stats(m, w, h)["box"][1] == 4


# ---------------------------------------------------------------------------------------------------- gate v2

def _r4():
    with open(os.path.join(DATA, "gate_r4_numbers.json")) as f:
        return json.load(f)


def test_round4_numbers_refuse_and_name_each_blocker():
    r = gate.judge(_r4()["numbers"], spec=_r4()["spec"])
    assert r["verdict"] == "REFUSE"
    failed = {row["id"] for row in r["rows"] if row["state"] == "FAIL"}
    # every operator blocker of round 4 that has a round-4 number fails on it
    for k in ("lips.lead_in_cm", "lips.onset_lead_ms", "lips.lag_frames", "lips.render_lag_frames", "lips.cues_fresh", "garment.neck_px",
              "garment.wpo_cm", "garment.pair_fraction", "garment.cloth_alive", "garment.cloth_sound",
              "garment.cloth_detail_ratio", "hair.cut_pop_ratio", "garment.armor_index",  # a guard: still blocks
              "garment.silhouette_pct", "hair.lock", "hair.render_cvars"):
        assert k in failed, k
    # and what round 4 never measured fails as "not measured", not silently
    rows = {row["id"]: row for row in r["rows"]}
    assert rows["head.blink_nod_deg"]["state"] == "FAIL" and "2.696" in rows["head.blink_nod_deg"]["reason"]
    assert rows["head.blink_locked_deg"]["state"] == "FAIL" and "0.416" in rows["head.blink_locked_deg"]["reason"]
    assert rows["lips.track_r"]["state"] == "FAIL" and "not measured" in rows["lips.track_r"]["reason"]


def test_round4_waivers_are_refused_on_complaints():
    w = {"lips.lead_in_cm": ("the planned smirk", "cc-64d05f6e"),
         "garment.neck_px": ("1-3 isolated px, by eye", "cc-64d05f6e"),
         "garment.silhouette_pct": ("no balloon by eye", "cc-64d05f6e")}
    r = gate.judge(_r4()["numbers"], waivers=w, spec=_r4()["spec"])
    assert r["verdict"] == "REFUSE"
    assert {x["id"] for x in r["refused_waivers"]} == set(w)
    assert all("complained" in x["refused"] for x in r["refused_waivers"])


def test_waiver_needs_reason_and_name_and_works_off_complaints():
    nums = {k: None for k in gate.ITEMS}
    spec = {"items": {"garment.cloth_alive": {"line": 0.1}}, "complaints": []}
    r = gate.judge({"garment.silhouette_pct": 2.5}, waivers={"garment.silhouette_pct": ("", "x")}, spec=spec,
                   only=["garment.silhouette_pct"])
    assert r["refused_waivers"][0]["refused"] == "a waiver needs a written reason"
    r = gate.judge({"garment.silhouette_pct": 2.5}, waivers={"garment.silhouette_pct": ("hem only", "")}, spec=spec,
                   only=["garment.silhouette_pct"])
    assert r["refused_waivers"][0]["refused"] == "a waiver needs who waived it"
    r = gate.judge({"garment.silhouette_pct": 2.5}, waivers={"garment.silhouette_pct": ("hem only", "op")},
                   spec=spec, only=["garment.silhouette_pct"])
    assert r["verdict"] == "SIGN" and r["rows"][0]["state"] == "WAIVED"
    assert nums  # every item id is a string key


def test_clean_numbers_sign():
    good = {"lips.lead_in_cm": 0.008, "lips.onset_lead_ms": 140, "lips.track_r": 0.93, "lips.measured_against": 1, "lips.cues_fresh": True,
            "lips.lag_frames": 0, "lips.silence_open": 0.03, "lips.silence_busy": 0.1, "lips.render_lag_frames": 1,
            "lips.render_conclusive": True, "garment.wpo_cm": 0.0, "garment.armor_index": 0.3,
            "garment.pair_fraction": 0.0, "garment.silhouette_ratio": 1.05,
            "head.blink_nod_deg": 0.2, "head.blink_locked_deg": 0.1, "garment.neck_px": 0, "garment.silhouette_pct": 0.8,
            "garment.cloth_alive": 0.6, "garment.cloth_sound": True, "garment.cloth_detail_ratio": 1.6, "hair.cut_reach_pct": 3.1, "hair.pop_reach_pct": 1.2, "hair.cut_pop_ratio": 1.1, "hair.lock": 1,
            "hair.render_cvars": 1}
    r = gate.judge(good)
    assert r["verdict"] == "SIGN", r["issues"]
    # an item with no line cannot pass
    r = gate.judge(good, spec={"items": {"garment.cloth_alive": {"line": None}}})
    assert r["verdict"] == "REFUSE" and any("no line set" in i["message"] for i in r["issues"])


def test_every_line_fails_its_round4_value():
    """The point of v2: a line that would have passed round 4's numbers is a bug in the gate."""
    res = gate.lines_fail()
    assert all(v is not False for v in res.values()), res
    assert sum(1 for v in res.values() if v) >= 7


# ---------------------------------------------------------------------------------------------------- film-qa

def test_film_qa_gate_round4_refuses(capsys, tmp_path):
    import pytest
    from filmtools.unreal import qa_local
    p = os.path.join(DATA, "gate_r4_numbers.json")
    with pytest.raises(SystemExit) as e:
        qa_local.main(["gate", p, "--spec", p, "--waive", "garment.neck_px=1-3 px by eye", "--by", "cc-64d05f6e",
                       "--out", str(tmp_path / "g.json")])
    assert e.value.code == 1
    r = json.loads(capsys.readouterr().out)
    assert r["verdict"] == "REFUSE" and r["refused_waivers"][0]["id"] == "garment.neck_px"
    assert json.load(open(tmp_path / "g.json"))["verdict"] == "REFUSE"
    qa_local.main(["gate", "--lines"])
    assert json.loads(capsys.readouterr().out)["pass"] is True


def _frame(path, hair_bottom, w=96, h=54):
    img = image.solid(w, h, (180, 170, 160))
    for y in range(8, hair_bottom):
        for x in range(40, 56):
            img.put(x, y, (12, 10, 9))
    image.write(img, str(path))


def test_film_qa_hair_on_frames(capsys, tmp_path):
    import pytest
    from filmtools.unreal import qa_local
    for f in range(1436, 1440):
        _frame(tmp_path / f"reel_S17.{f:05d}.png", 40)
    for f in range(1440, 1444):
        _frame(tmp_path / f"reel_S18.{f:05d}.png", 26)  # the wide: same anchors, hair ends higher
    anchors = {str(f): [0.2, 0.6] for f in range(1436, 1444)}
    spec = {"character": "Presenter", "cuts": [["S17", 1392, 1440], ["S18", 1440, 1560]],
            "frames_glob": str(tmp_path / "*.png"), "boxes": {"S17": [0.3, 0.0, 0.7, 1.0], "S18": [0.3, 0.0, 0.7, 1.0]},
            "anchors": anchors}
    sp = tmp_path / "spec.json"
    sp.write_text(json.dumps(spec))
    with pytest.raises(SystemExit):
        qa_local.main(["hair", str(sp)])
    r = json.loads(capsys.readouterr().out)
    assert r["metrics"]["frames_measured"] == 8 and r["gate"]["hair.cut_reach_pct"] > 12
    assert r["issues"][0]["code"] == "hair.cut_jump" and r["issues"][0]["frame"] == 1440


def test_film_qa_hair_cut_pop_and_saturation(capsys, tmp_path):
    """Round 5 P3: at night the matte ran into the box's bottom (dark clothing), so reach read the box and missed
    the change; the cut pop (frame differences in the head box) sees a pop at a held camera."""
    import pytest
    from filmtools.unreal import qa_local
    # a held camera: S17's end and S18's start frame the same; S18's hair differs from its first frame (a sim restart)
    for f in range(1436, 1440):
        _frame(tmp_path / f"{f:04d}.png", 40)
    for f in range(1440, 1444):
        _frame(tmp_path / f"{f:04d}.png", 20)
    spec = {"character": "Presenter", "cuts": [["S17", 1392, 1440], ["S18", 1440, 1560]],
            "frames_glob": str(tmp_path / "*.png"), "boxes": {"S17": [0.3, 0.0, 0.7, 0.6], "S18": [0.3, 0.0, 0.7, 0.6]},
            "anchors": {str(f): [0.2, 0.6] for f in range(1436, 1444)}}
    sp = tmp_path / "spec.json"
    sp.write_text(json.dumps(spec))
    with pytest.raises(SystemExit):
        qa_local.main(["hair", str(sp)])
    r = json.loads(capsys.readouterr().out)
    codes = {i["code"] for i in r["issues"]}
    assert "hair.matte_saturated" in codes  # S17's hair (to row 39) runs past the box bottom (row 32)
    assert r["gate"]["hair.cut_reach_pct"]["value"] is None and "saturated" in r["gate"]["hair.cut_reach_pct"]["error"]
    assert "hair.cut_pop" in codes and r["gate"]["hair.cut_pop_ratio"] > 3
    assert r["cut_pops"][0]["d_before"] == 0.0 and r["cut_pops"][0]["d_after"] == 0.0
    # only the inner sides of the cut were read (no S17-start / S18-end frames)
    assert r["metrics"]["frames_measured"] == 8


def test_cut_pop_quiet_cut():
    a = image.solid(20, 20, (100, 100, 100))
    b = image.solid(20, 20, (102, 100, 100))
    frames = {1438: a, 1439: b, 1440: a, 1441: b}  # the cut changes as much as each shot's own frames
    r = hair.cut_pop(frames, 1440, [0, 0, 1, 1])
    assert r["ratio"] <= 1.01
    assert hair.cut_pop({1439: a}, 1440, [0, 0, 1, 1])["missing"] == [1438, 1440, 1441]


def test_info_item_never_blocks():
    good = {k: None for k in gate.ITEMS}
    r = gate.judge({"garment.silhouette_ratio": 2.30}, only=["garment.silhouette_ratio"])
    assert r["verdict"] == "SIGN" and r["rows"][0]["state"] == "INFO" and "info only" in r["rows"][0]["reason"]
    r = gate.judge({}, only=["garment.silhouette_ratio"])
    assert r["verdict"] == "SIGN" and r["rows"][0]["state"] == "INFO"
    assert good


def test_scope_by_cast():
    scope = __import__("fmqa.scope", fromlist=["scope"])
    shots = [{"id": "S15", "start": 1080, "end": 1200, "cast": ["him", "her"]},
             {"id": "S16", "start": 1200, "end": 1320, "cast": ["her"]},
             {"id": "S17", "start": 1320, "end": 1440, "cast": ["him", "her"]},
             {"id": "S18", "start": 1440, "end": 1560, "cast": ["him", "her"]}]
    him = scope.visible_ranges(shots, "him")
    assert him == [[1080, 1200], [1320, 1560]]
    assert scope.visible_ranges(shots, "her") == [[1080, 1560]]
    # round 5: his blink nod at f1294-1306 is inside S16, her close-up: out of scope
    assert not scope.window_in(1294, 1306, him) and scope.window_in(1395, 1407, him)
    assert not scope.window_in(1195, 1205, him)  # a window across the cut into S16 is not wholly visible
    kept, dropped = scope.split({1100: 0.2, 1300: 2.89, 1400: 0.3}, him)
    assert set(kept) == {1100, 1400} and set(dropped) == {1300}
    assert scope.narrow(him, [1100, 1101, 1102, 1300, 1400]) == [[1100, 1103], [1400, 1401]]


def test_not_attempted_is_scoped():
    na = {"garment.cloth_alive": {"reason": "closed-shell tee; proxy sim is round 6", "by": "cc-64d05f6e"},
          "garment.wpo_cm": {"reason": "skip", "by": "cc-64d05f6e"}}
    spec = {"complaints": ["garment"], "not_attempted": na}
    r = gate.judge({"garment.wpo_cm": 2.66}, spec=spec, only=["garment.cloth_alive", "garment.wpo_cm"])
    rows = {x["id"]: x for x in r["rows"]}
    assert rows["garment.cloth_alive"]["state"] == "NOT_ATTEMPTED"
    assert rows["garment.wpo_cm"]["state"] == "FAIL"           # a hard line cannot be deferred
    assert r["refused_waivers"][0]["id"] == "garment.wpo_cm" and r["verdict"] == "REFUSE"
    ok = gate.judge({}, spec={"not_attempted": {"garment.cloth_alive": na["garment.cloth_alive"]}},
                    only=["garment.cloth_alive"])
    assert ok["verdict"] == "SIGN" and "NOT ATTEMPTED" in ok["summary"] and ok["not_attempted"][0]["by"]
    bad = gate.judge({}, spec={"not_attempted": {"garment.cloth_alive": {"reason": "", "by": "x"}}},
                     only=["garment.cloth_alive"])
    assert bad["verdict"] == "REFUSE"
