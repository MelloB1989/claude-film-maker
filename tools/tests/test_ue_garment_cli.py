"""film-ue garment-fit: the Blender command line and the report in words (no Blender here)."""
import json
import sys

import pytest

from filmtools.unreal import cli_garment as G


def test_command_passes_only_given_knobs():
    cmd = G.command({"src": "/s", "garment": "tee", "out": "/o", "drape_frames": 40, "ease": '{"chest": 1.8}',
                     "min_ease": None, "only_slots": ""}, "/b/blender")
    assert cmd[:6] == ["/b/blender", "-b", "--factory-startup", "--python-exit-code", "2", "-P"]
    assert cmd[6].endswith("blender/garment_fit.py") and cmd[7:10] == ["--", "--src", "/s"]
    tail = cmd[10:]
    assert tail == ["--garment", "tee", "--out", "/o", "--ease", '{"chest": 1.8}', "--drape-frames", "40"]


REP = {"before": {"all": {"median": 0.4, "spread": 0.3, "inside": 0.02}},
       "after": {"all": {"median": 1.6, "spread": 1.4, "inside": 0.0},
                 "chest": {"n": 300, "p10": 0.9, "median": 1.6, "p90": 2.8}},
       "poses": {"anim_AS_reel_him_body": {"inside": 0, "deepest_cm": 0.0, "frame": None}},
       "problems": [], "pass": True, "fbx": "/o/garment_fit_tee.fbx"}


def test_judge_pass_and_fail_say_what_next():
    j = G.judge(REP)
    assert j["pass"] and "import" in j["next"][0] and any("chest" in s for s in j["lines"])
    bad = {**REP, "pass": False, "problems": ["the ease is even (spread 0.3 < 0.6): a shell; drape it",
                                              "pose test anim_x: 12 garment verts inside the body at frame 40 (deepest 0.4 cm)"]}
    j = G.judge(bad)
    assert not j["pass"] and any("drape" in n for n in j["next"]) and any("weights" in n for n in j["next"])


def test_dispatch_report_only(tmp_path, monkeypatch, capsys):
    p = tmp_path / "fit_report.json"
    p.write_text(json.dumps(REP))
    from filmtools.unreal import cli
    monkeypatch.setattr(sys, "argv", ["film-ue", "garment-fit", "--report", str(p)])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0 and capsys.readouterr().out.startswith("PASS")


def test_dispatch_refuses_without_export(tmp_path, monkeypatch):
    from filmtools.unreal import cli
    monkeypatch.setattr(sys, "argv", ["film-ue", "garment-fit", "--src", str(tmp_path), "--out", str(tmp_path / "o")])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 2


def test_gate_numbers_contract(tmp_path, monkeypatch):
    clip = {"metrics": {"worst": {"neck_px": {"px": 3, "at_opening": 2, "at": "Reel_S15@1082"},
                                  "silhouette": {"pct": -2.23, "at": "Reel_S15@1150"},
                                  "Body>tee": {"fraction": 0.0, "px": 0, "at": "Reel_S13@960"},
                                  "Trousers>tee": {"fraction": 0.0067, "px": 30, "at": "Reel_S18@1500"},
                                  "Face>tee": {"fraction": 0.0071, "px": 31, "at": "Reel_S15@1082"}}}}
    look = {"index": 0.71, "missing": ["motion"], "terms": {"wpo": {"value": 2.66}, "silhouette": {"value": 1.08}},
            "metrics": {"frames": {"1082": {}}}}
    g = G.gate_numbers(clip, look)["gate"]
    assert g["garment.neck_px"] == {"value": 3, "where": "S15 f1082"}
    assert g["garment.silhouette_pct"]["value"] == 2.23
    assert g["garment.pair_fraction"] == {"value": 0.0067, "where": "S18 f1500 Trousers>tee"}
    assert g["garment.wpo_cm"]["value"] == 2.66 and g["garment.armor_index"]["value"] == 0.71
    g2 = G.gate_numbers(None, None)["gate"]
    assert all(v["value"] is None and v["error"] for v in g2.values()) and len(g2) == 6
    from filmtools.unreal import cli
    (tmp_path / "c.json").write_text(json.dumps(clip))
    out = tmp_path / "g.json"
    monkeypatch.setattr(sys, "argv", ["film-ue", "garment-gate", "--clip", str(tmp_path / "c.json"), "--out", str(out)])
    cli.main()
    assert json.loads(out.read_text())["gate"]["garment.armor_index"]["error"]
