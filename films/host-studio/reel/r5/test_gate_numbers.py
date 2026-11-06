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
