"""film-ue's routing (cli.main): generated op commands, --box, film-ue's own commands winning over an area of the
same name, area extensions (film-ue render <its own verb>), the WP11 commands; all offline (--dry-run, describe, dx)."""
import json
import sys

import pytest

from filmtools.unreal import cli, opcli


def run(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["film-ue", *argv])
    try:
        cli.main()
        code = 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_generated_op_command(monkeypatch, capsys):
    code, out, _ = run(monkeypatch, capsys, "level", "spawn", "--label", "A", "--shape", "cube", "--dry-run")
    assert code == 0 and json.loads(out)["args"] == {"label": "A", "shape": "cube"}


def test_box_before_the_area(monkeypatch, capsys):
    monkeypatch.delenv("FILM_UE_BOX", raising=False)
    code, out, _ = run(monkeypatch, capsys, "--box", "lnx", "level", "move", "--label", "A", "--dry-run")
    import os
    assert code == 0 and os.environ["FILM_UE_BOX"] == "lnx" and json.loads(out)["op"] == "level.move"


def test_a_bad_flag_exits_2_with_candidates(monkeypatch, capsys):
    code, out, _ = run(monkeypatch, capsys, "level", "move", "--lable", "A", "--json")
    assert code == 2 and "--label" in json.loads(out)["error"]["candidates"]


def test_builtin_commands_win_over_areas(monkeypatch):
    seen = {}
    monkeypatch.setattr(opcli, "run", lambda argv, **kw: seen.setdefault("opcli", argv) and 0)
    monkeypatch.setattr(cli, "_print", lambda res: seen.setdefault("printed", res))
    monkeypatch.setattr(cli.client, "op", lambda *a, **k: {"ok": True, "result": {}, "stdout": ""})
    monkeypatch.setattr(sys, "argv", ["film-ue", "ops", "level"])  # "ops" is also an op area: the builtin wins
    cli.main()
    assert "opcli" not in seen and "printed" in seen


def test_describe_and_dx(monkeypatch, capsys):
    code, out, _ = run(monkeypatch, capsys, "describe", "level.move")
    assert code == 0 and "film-ue level move --label" in out
    code, out, _ = run(monkeypatch, capsys, "describe", "--json", "seq")
    assert code == 0 and any(o["name"] == "seq.new" for o in json.loads(out))
    code, out, _ = run(monkeypatch, capsys, "dx", "check")
    assert code == 0 and "up to date" in out
    code, out, _ = run(monkeypatch, capsys, "plan", "--kinds")
    assert code == 0 and "actor" in out and "scene" in out


def test_area_extension_reaches_its_main(monkeypatch, capsys):
    import filmtools.unreal.render as render
    got = {}
    monkeypatch.setattr(render, "main", lambda argv: got.setdefault("argv", argv) and 0)
    verbs = {o.split(".", 1)[1] for o in opcli._schema.index(opcli._schema.load())["ops"] if o.startswith("render.")}
    assert "validate" not in verbs
    run(monkeypatch, capsys, "render", "validate", "x.yaml")
    assert got["argv"] == ["validate", "x.yaml"]
    code, out, _ = run(monkeypatch, capsys, "render", "progress", "--out-dir", "/tmp/r", "--dry-run")
    assert code == 0 and json.loads(out)["op"] == "render.progress"   # an op verb stays the op


def test_plan_offline_through_the_cli(monkeypatch, capsys, tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("kind: actor\nname: A\nshape: cube\n")
    st = tmp_path / "st.json"
    st.write_text("{}")
    code, out, _ = run(monkeypatch, capsys, "plan", str(p), "--state", str(st), "--json")
    doc = json.loads(out)
    assert code == 0 and doc["items"][0]["steps"][0]["op"] == "level.spawn" and doc["converged"] is False
