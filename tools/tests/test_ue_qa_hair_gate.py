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
    for k in ("lips.lead_in_cm", "lips.onset_lead_ms", "lips.lag_frames", "lips.cues_fresh", "garment.neck_px",
              "garment.wpo_cm", "garment.pair_fraction",
              "garment.silhouette_pct", "hair.lock", "hair.render_cvars"):
        assert k in failed, k
    # and what round 4 never measured fails as "not measured", not silently
    rows = {row["id"]: row for row in r["rows"]}
    assert rows["head.blink_nod_deg"]["state"] == "FAIL" and "not measured" in rows["head.blink_nod_deg"]["reason"]


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
    spec = {"items": {"garment.cloth_detail": {"line": 0.1}}, "complaints": []}
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
    good = {"lips.lead_in_cm": 0.008, "lips.onset_lead_ms": 140, "lips.track_r": 0.71, "lips.cues_fresh": True,
            "lips.lag_frames": 0, "lips.silence_open": 0.03, "lips.silence_busy": 0.1, "lips.render_lag_frames": 1,
            "lips.render_conclusive": True, "garment.wpo_cm": 0.0, "garment.armor_index": 0.3,
            "garment.pair_fraction": 0.0, "garment.silhouette_ratio": 1.05,
            "head.blink_nod_deg": 0.2, "garment.neck_px": 0, "garment.silhouette_pct": 0.8,
            "garment.cloth_detail": 0.3, "hair.cut_reach_pct": 3.1, "hair.pop_reach_pct": 1.2, "hair.lock": 1,
            "hair.render_cvars": 1}
    r = gate.judge(good, spec={"items": {"garment.cloth_detail": {"line": 0.2}}})
    assert r["verdict"] == "SIGN", r["issues"]
    # an item with no line cannot pass
    r = gate.judge(good)
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
