"""gate_numbers.py on synthetic inputs (no box): every item is a number or an error, never silently missing."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_numbers as GN  # noqa: E402

PROBE_OK = "\n".join(f"{s} OK" for s in GN.SHOTS_13)


def test_shot_cams_all_ok(tmp_path):
    (tmp_path / "p.txt").write_text(PROBE_OK)
    (tmp_path / "f.txt").write_text("S13 MCU fine\n")
    g = GN.shot_cams(str(tmp_path / "p.txt"), str(tmp_path / "f.txt"))
    assert g["shot.cameras_ok"]["value"] == 1


def test_shot_cams_problem_and_missing(tmp_path):
    (tmp_path / "p.txt").write_text(PROBE_OK.replace("S15 OK", "S15 OFF 2.1 cm"))
    (tmp_path / "f.txt").write_text("PROBLEM S17 head cut\n")
    g = GN.shot_cams(str(tmp_path / "p.txt"), str(tmp_path / "f.txt"))
    assert g["shot.cameras_ok"]["value"] == 0 and len(g["shot.cameras_ok"]["failed"]) == 2
    assert GN.shot_cams(str(tmp_path / "none.txt"), str(tmp_path / "f.txt"))["shot.cameras_ok"]["error"]


def test_hair_lock_cvars_and_qa(tmp_path):
    chk = {"check": {"pass": True, "problems": []}, "render_cvars": {"r.HairStrands.LODMode": 0}}
    chk["check"]["render_cvars"] = {"r.HairStrands.LODMode": 0, "r.HairStrands.AutoLOD.Bias": 1.0,
                                    "r.HairStrands.UseCardsInsteadOfStrands": 0}
    (tmp_path / "c.json").write_text(json.dumps(chk))
    (tmp_path / "ok.yaml").write_text('cvars: {"r.SSS.Quality": 1, "r.HairStrands.LODMode": 0, '
                                      '"r.HairStrands.AutoLOD.Bias": 1.0, "r.HairStrands.UseCardsInsteadOfStrands": 0}\n')
    (tmp_path / "bad.yaml").write_text('cvars: {"r.SSS.Quality": 1}\n')
    (tmp_path / "q1.json").write_text(json.dumps({"gate": {"hair.cut_reach_pct": 1.0, "hair.cut_pop_ratio": 1.2}}))
    (tmp_path / "q2.json").write_text(json.dumps({"gate": {"hair.cut_reach_pct": 3.0, "hair.cut_pop_ratio": 1.1}}))
    g = GN.hair(str(tmp_path / "c.json"), str(tmp_path / "ok.yaml"), [str(tmp_path / "q1.json"), str(tmp_path / "q2.json")])
    assert g["hair.lock"]["value"] == 1 and g["hair.render_cvars"]["value"] == 1
    assert g["hair.cut_reach_pct"]["value"] == 3.0 and g["hair.cut_pop_ratio"]["value"] == 1.2  # the worst
    sat = {"gate": {"hair.cut_reach_pct": {"value": None, "error": "the hair matte saturated"}, "hair.cut_pop_ratio": 1.3}}
    (tmp_path / "sat.json").write_text(json.dumps(sat))
    (tmp_path / "ed.json").write_text(json.dumps({"gate": {"hair.cut_reach_pct": 1.07, "hair.pop_reach_pct": 2.0}}))
    for order in (("sat.json", "ed.json"), ("ed.json", "sat.json")):  # the editor's number beats the render's error
        g = GN.hair(str(tmp_path / "c.json"), str(tmp_path / "ok.yaml"), [str(tmp_path / n) for n in order])
        assert g["hair.cut_reach_pct"]["value"] == 1.07 and g["hair.cut_pop_ratio"]["value"] == 1.3
        assert g["hair.pop_reach_pct"] == 2.0
    (tmp_path / "w.json").write_text(json.dumps({"ok": True, "result": {"gate": {"hair.pop_reach_pct": 4.0}}}))
    (tmp_path / "cw.json").write_text(json.dumps({"ok": True, "result": {"pass": True, "problems": []}}))
    g = GN.hair(str(tmp_path / "cw.json"), str(tmp_path / "ok.yaml"), [str(tmp_path / "w.json")])
    assert g["hair.pop_reach_pct"] == 4.0 and g["hair.lock"]["value"] == 1  # film-ue op's wrapper unwrapped
    (tmp_path / "e2.json").write_text(json.dumps({"gate": {"hair.pop_reach_pct": {"value": None, "error": "x"}}}))
    g = GN.hair(str(tmp_path / "c.json"), str(tmp_path / "ok.yaml"), [str(tmp_path / "e2.json")])
    assert g["hair.pop_reach_pct"]["error"]  # an error alone stays an error
    g = GN.hair(str(tmp_path / "c.json"), str(tmp_path / "bad.yaml"), [str(tmp_path / "missing.json")])
    assert g["hair.render_cvars"]["value"] == 0 and g["hair.cut_pop_ratio"]["error"]


def test_hair_real_final_yaml_carries_lock_cvars(tmp_path):
    (tmp_path / "c.json").write_text(json.dumps({"pass": False, "problems": ["x"]}))
    g = GN.hair(str(tmp_path / "c.json"), str(GN.REEL / "r3" / "30-final.yaml"), [])
    assert g["hair.lock"]["value"] == 0 and g["hair.render_cvars"]["value"] == 1


def test_ssim_min_and_unmeasured(tmp_path):
    from filmtools.unreal import qa_local
    qa_local.qa()
    im = sys.modules["fmqa.image"]
    import numpy as np
    s16 = next(s for s in GN.SHOTS if s.id == "S16")
    rng = np.random.default_rng(0)
    (tmp_path / "r").mkdir(), (tmp_path / "a").mkdir()
    for k, f in enumerate((s16.start, s16.start + 1)):
        base = (rng.random((72, 128, 3)) * 255).astype("uint8")
        im.write(im.Image.from_array(base), str(tmp_path / "r" / f"x.{f:04d}.png"))
        out = base if k == 0 else (255 - base)
        im.write(im.Image.from_array(out), str(tmp_path / "a" / f"x.{f:04d}.png"))
    g = GN.ssim([str(tmp_path / "a")], str(tmp_path / "r"), ["S16"])["shot.render_matches_r4"]
    assert g["value"] < 0.5 and g["where"] == f"S16 f{s16.start + 1}"
    g = GN.ssim([str(tmp_path / "a")], str(tmp_path / "r"), ["S16", "S17"])["shot.render_matches_r4"]
    assert "S17" in g["error"]


def test_hair_lists_every_cut_judged(tmp_path):
    """The orchestrator's condition: the editor's groom-only check judges every cut she is on screen (S16->S17 too);
    only the pixel pop narrows to S17->S18. The gate file names both lists."""
    (tmp_path / "c.json").write_text(json.dumps({"pass": True}))
    ed = {"ok": True, "result": {"gate": {"hair.cut_reach_pct": 1.1, "hair.pop_reach_pct": 2.0}, "characters": {
        "Presenter": {"cuts": [{"from": a, "to": b, "frame": f, "reach": [1, 1, r]} for a, b, f, r in
                               (("S15", "S16", 1200, 0.004), ("S16", "S17", 1392, -0.011), ("S17", "S18", 1440, 0.002))]}}}}
    rd = {"gate": {"hair.cut_pop_ratio": 1.1}, "cuts": [], "cut_pops": [
        {"from": "S17", "to": "S18", "cut": 1440, "ratio": 1.1}]}
    (tmp_path / "ed.json").write_text(json.dumps(ed))
    (tmp_path / "rd.json").write_text(json.dumps(rd))
    g = GN.hair(str(tmp_path / "c.json"), str(GN.REEL / "r3" / "30-final.yaml"),
                [str(tmp_path / "rd.json"), str(tmp_path / "ed.json")])
    assert g["hair.cut_reach_pct"]["value"] == 1.1
    assert [j.split()[1] for j in g["hair.cut_reach_pct"]["cuts_judged"]] == ["S15->S16", "S16->S17", "S17->S18"]
    assert g["hair.cut_pop_ratio"]["pop_cuts"] == ["S17->S18 f1440 x1.1"]


def test_settle_flags_a_start_pop(tmp_path):
    from filmtools.unreal import qa_local
    qa_local.qa()
    im = sys.modules["fmqa.image"]
    import numpy as np
    s15 = next(s for s in GN.SHOTS if s.id == "S15")
    rng = np.random.default_rng(1)
    base = (rng.random((54, 96, 3)) * 200).astype("uint8")
    for k in range(17):
        a = base.copy()
        a[:, :, 0] = np.clip(a[:, :, 0].astype(int) + k, 0, 255)  # slow, even motion
        if k == 1:
            a[10:30, 30:60] = 250  # a jolt at the first frames
        im.write(im.Image.from_array(a), str(tmp_path / f"{s15.start + k:04d}.png"))
    spec = {"cuts": [["S15", s15.start, s15.end]], "boxes": {"S15": [0.2, 0.1, 0.8, 0.7]}}
    (tmp_path / "spec.json").write_text(json.dumps(spec))
    r = GN.settle(str(tmp_path), str(tmp_path / "spec.json"), "S15")
    assert r["pass"] is False and r["ratio"] > 1.8
    assert GN.settle(str(tmp_path), str(tmp_path / "spec.json"), "S16")["error"]


def test_hair_pop_only_ignores_the_night_matte(tmp_path):
    """Round 5b: film-qa hair on the night finals read cut_reach 156.5 % (the matte took her dark clothing) without
    flagging saturation; with --qa-pop only its cut_pop_ratio is taken and the editor's reach stands."""
    (tmp_path / "c.json").write_text(json.dumps({"pass": True}))
    (tmp_path / "rd.json").write_text(json.dumps({"gate": {"hair.cut_reach_pct": 156.5, "hair.pop_reach_pct": 0.0,
                                                           "hair.cut_pop_ratio": 1.372}}))
    (tmp_path / "ed.json").write_text(json.dumps({"gate": {"hair.cut_reach_pct": 2.0, "hair.pop_reach_pct": 8.9}}))
    g = GN.hair(str(tmp_path / "c.json"), str(GN.REEL / "r3" / "30-final.yaml"), [str(tmp_path / "ed.json")],
                [str(tmp_path / "rd.json")])
    assert g["hair.cut_reach_pct"]["value"] == 2.0 and g["hair.pop_reach_pct"] == 8.9
    assert g["hair.cut_pop_ratio"]["value"] == 1.372


def test_pop_exclude_needs_a_ruling_and_lists_what_it_drops(tmp_path):
    (tmp_path / "c.json").write_text(json.dumps({"pass": True}))
    ed = {"gate": {"hair.cut_reach_pct": 1.96, "hair.pop_reach_pct": 8.93}, "characters": {"Presenter": {"pops": [
        {"shot": "Reel_S15", "frame": 1082, "reach": -0.0893, "area": 0.038}]}}}
    (tmp_path / "ed.json").write_text(json.dumps(ed))
    y = str(GN.REEL / "r3" / "30-final.yaml")
    rule = {"shot": "S15", "frames": [1080, 1086], "reason": "planned motion, render = round 4", "by": "cc-64d05f6e"}
    g = GN.hair(str(tmp_path / "c.json"), y, [str(tmp_path / "ed.json")], [], [rule])
    assert g["hair.pop_reach_pct"]["value"] == 0.0 and g["hair.pop_reach_pct"]["excluded_by_ruling"][0]["frame"] == 1082
    g = GN.hair(str(tmp_path / "c.json"), y, [str(tmp_path / "ed.json")], [], [{**rule, "frames": [1090, 1100]}])
    assert g["hair.pop_reach_pct"] == 8.93  # outside the window: unchanged
    g = GN.hair(str(tmp_path / "c.json"), y, [str(tmp_path / "ed.json")], [], [{**rule, "by": ""}])
    assert g["hair.pop_reach_pct"]["error"]  # no name, no exclusion


def test_reach_at_vs_ref_and_saturation(tmp_path):
    from filmtools.unreal import qa_local
    qa_local.qa()
    im = sys.modules["fmqa.image"]
    import numpy as np

    def fr(f, bottom):
        a = np.full((60, 100, 3), 180, "uint8")
        a[10:bottom, 40:60] = 10  # dark hair from row 10 to `bottom`
        im.write(im.Image.from_array(a), str(tmp_path / f"{f:04d}.png"))
    fr(1086, 40)
    for f in range(1100, 1105):
        fr(f, 41)
    spec = {"cuts": [["S15", 1080, 1200]], "boxes": {"S15": [0.2, 0.0, 0.8, 0.9]}}
    (tmp_path / "s.json").write_text(json.dumps(spec))
    r = GN.reach(str(tmp_path), str(tmp_path / "s.json"), "S15", 1086, list(range(1100, 1105)))
    assert r["pass"] and abs(r["rel"]) < 0.08
    fr(1086, 25)  # much shorter
    r = GN.reach(str(tmp_path), str(tmp_path / "s.json"), "S15", 1086, list(range(1100, 1105)))
    assert not r["pass"]
    fr(1086, 60)  # down to the box bottom: saturated
    r = GN.reach(str(tmp_path), str(tmp_path / "s.json"), "S15", 1086, list(range(1100, 1105)), box=[0.2, 0.0, 0.8, 0.5])
    assert "saturated" in r["error"]
