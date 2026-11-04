"""film-ue render's client side (tools/filmtools/unreal/render.py): the render spec kind's pure planner, loading
YAML/JSON specs, offline plan/validate, box stitching (B23), frame QA (B24), and that the example specs validate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from filmtools.unreal import render as cli

rs = cli.rs
ROOT = Path(__file__).resolve().parents[2]
SPEC = {"kind": "render", "version": 1, "name": "reel", "sequence": "/Game/Reel/SEQ_Reel", "out_dir": "/srv/r/reel"}
STATE = {"playback": [0, 300], "fps": 24.0, "cuts": [["CamA", 0, 100], ["CamB", 100, 160], ["CamC", 160, 300]]}


def test_kind_plans_a_job_until_the_box_has_nothing_left():
    steps = cli.plan(SPEC, {})
    assert steps == [{"op": "render.job", "args": {"spec": {k: v for k, v in SPEC.items() if k not in ("kind", "version")}},
                      "why": "no render on the box yet"}]
    left = rs.plan(rs.resolve(cli._body(SPEC)), {**STATE, "done": list(range(150))})
    steps = cli.plan(SPEC, left)
    assert len(steps) == 1 and steps[0]["why"].startswith("150 frames left in 2 chunks")
    done = rs.plan(rs.resolve(cli._body(SPEC)), {**STATE, "done": list(range(300))})
    assert cli.plan(SPEC, done) == []  # converged


def test_spec_kinds_declared_for_the_engine():
    (k,) = cli.SPEC_KINDS
    assert k["name"] == "render" and k["plan"] is cli.plan and k["order"] == 90
    assert (ROOT / "tools/filmtools/unreal/schemas" / k["schema"]).exists()


def test_load_yaml_and_json(tmp_path):
    pytest.importorskip("yaml")
    y = tmp_path / "s.yaml"
    y.write_text("kind: vars\nvars: {a: 1}\n---\nkind: render\nversion: 1\nname: x\nsequence: /Game/S\nout_dir: /o\n")
    assert cli.load_spec(str(y))["name"] == "x"
    j = tmp_path / "s.json"
    j.write_text(json.dumps(SPEC))
    assert cli.load_spec(str(j))["sequence"] == "/Game/Reel/SEQ_Reel"
    j.write_text(json.dumps({"kind": "camera"}))
    with pytest.raises(SystemExit, match="no document of kind render"):
        cli.load_spec(str(j))


def test_offline_plan_and_validate(tmp_path, capsys):
    s, st = tmp_path / "s.json", tmp_path / "state.json"
    s.write_text(json.dumps(SPEC))
    st.write_text(json.dumps(STATE))
    assert cli.main(["estimate", str(s), "--state", str(st), "--boxes", "2"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["chunks"]) == 3 and len(out["boxes"]) == 2
    s.write_text(json.dumps({**SPEC, "preset": "fnal"}))
    with pytest.raises(SystemExit, match="did you mean 'final'"):
        cli.main(["validate", str(s)])


def _frames(d: Path, frames, name="{:04d}.png"):
    d.mkdir(parents=True, exist_ok=True)
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 20 + b"IEND\xaeB`\x82"
    for f in frames:
        (d / name.format(f)).write_bytes(png)


def test_stitch_finds_missing_and_duplicate_frames(tmp_path):
    r = rs.resolve({**cli._body(SPEC), "boxes": 2, "resume": False})
    p = rs.plan(r, STATE)
    a, b = tmp_path / "a", tmp_path / "b"
    box0 = {f for cid in p["boxes"][0]["chunks"] for c in p["chunks"] if c["id"] == cid for f in range(c["start"], c["end"])}
    _frames(a, sorted(box0))
    gone = max(set(range(300)) - box0)
    _frames(b, [f for f in range(300) if f not in box0 and f != gone] + [min(box0)])
    res = cli.stitch(r, p, {str(a): cli._local_frames(r, str(a)), str(b): cli._local_frames(r, str(b))})
    assert res["missing"] == [[gone, gone + 1]] and not res["complete"]
    assert list(res["duplicates"]) == [min(box0)] and res["boxes"][0]["missing"] == []
    assert res["boxes"][1]["missing"] == [[gone, gone + 1]]


def test_signalstats_and_frame_qa():
    txt = "frame:0 pts:0\nlavfi.signalstats.YAVG=100.0\nframe:1\nlavfi.signalstats.YAVG=101\nlavfi.signalstats.YAVG=2.0\n"
    assert rs.parse_signalstats(txt, 10) == {10: 100.0, 11: 101.0, 12: 2.0}
    luma = {i: 100.0 + (i % 2) * 0.5 for i in range(20)}
    luma[7] = 140.0  # a one-frame spike
    luma[15] = 1.0
    q = rs.frame_qa(luma)
    assert 7 in q["flicker"] and q["black"] == [15]
    fade = {i: 100.0 - 5 * i for i in range(20)}  # a steady fade is not flicker
    assert rs.frame_qa(fade)["flicker"] == []


def test_check_frames_without_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    r = rs.resolve(cli._body(SPEC))
    _frames(tmp_path, [0, 1, 2, 4])
    (tmp_path / "0002.png").write_bytes(b"\x89PNG\r\n\x1a\ncut")
    res = cli.check_frames(r, str(tmp_path), 0, 5)
    assert res["missing"] == [[3, 4]] and res["corrupt"] == [2] and res["pass"] is False
    assert "luma not measured" in res["why"] and res["metric"] == 2


def test_example_specs_validate():
    yaml = pytest.importorskip("yaml")
    files = sorted((ROOT / "examples/unreal/render").glob("*.yaml"))
    assert files, "examples/unreal/render/*.yaml"
    for f in files:
        for d in yaml.safe_load_all(f.read_text()):
            if d and d.get("kind") == "render":
                assert rs.validate(cli._body(d) | {"kind": "render", "version": 1}) == [], f
                rs.resolve(cli._body(d))


def test_cli_verbs_do_not_shadow_op_verbs():
    import re
    ops_src = (ROOT / "unreal/fmbridge/ops/render.py").read_text()
    verbs = set(re.findall(r'@op\("render\.(\w+)"', ops_src))
    cli_src = (ROOT / "tools/filmtools/unreal/render.py").read_text()
    subs = set(re.findall(r'sub\.add_parser\("(\w+)"', cli_src))
    assert verbs and subs and not verbs & subs, verbs & subs
