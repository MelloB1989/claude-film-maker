"""The bridge's op runtime against the fake engine: every op module imports, the registry and its schema, argument
checks and actionable errors, a module that fails to import, multi-tick jobs, and the editor's Python (3.11)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from fakeunreal import drive, run_op

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "unreal" / "fmbridge"


def test_every_op_module_imports(fmb):
    assert fmb.broken() == {}, fmb.broken()
    names = set(fmb._OPS)
    for area in ("assets", "level", "look", "mh", "anim", "seq", "render", "speech"):
        assert any(n.startswith(area + ".") for n in names), area


def test_names_are_area_dot_verb(fmb):
    bad = [n for n in fmb._OPS if n != "list" and (n.count(".") != 1 or n != n.lower())]
    assert not bad, f"op names must be lower-case area.verb: {bad}"


def test_every_op_has_a_docstring(fmb):
    missing = [n for n, f in fmb._OPS.items() if not (f.__doc__ or "").strip()]
    assert not missing, missing


def test_schema_is_json_and_complete(fmb):
    s = run_op("ops.schema")
    json.dumps(s)
    assert s["version"] == 1 and s["broken"] == {}
    by = {o["name"]: o for o in s["ops"]}
    assert set(by) == set(fmb._OPS)
    o = by["ops.schema"]
    assert o["area"] == "ops" and o["verb"] == "schema" and o["mutates"] is False
    assert o["file"] == "unreal/fmbridge/ops/__init__.py" and o["line"] > 0
    assert o["params"] == [{"name": "prefix", "kind": "positional", "type": "str", "required": False, "default": ""}]
    assert o["summary"].startswith("Every op's signature")
    assert any(x["multi_tick"] for x in s["ops"]), "mh.cloth_inflate is a generator"


def test_unknown_op_suggests(fmb):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        fmb.call("level.spwn")
    assert e.value.code == "not_found" and "level.spawn" in e.value.candidates


def test_bad_args_are_named(fmb):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        fmb.call("ops.schema", prefx="x")
    assert e.value.code == "bad_args" and "prefx" in e.value.message


def test_server_answers_op_errors_with_code_and_hint(ue):
    from fakeunreal import load_fmbridge
    load_fmbridge()
    from fmbridge import server
    r = server._run("op", {"name": "level.spwn", "args": {}})
    assert r["ok"] is False and r["code"] == "not_found" and "level.spawn" in r["candidates"]
    assert "Traceback" in r["error"]
    r = server._run("exec", {"code": "result = 1/0"})
    assert r["ok"] is False and r["code"] == "exception" and r["message"].startswith("ZeroDivisionError")


def test_server_steps_a_multi_tick_job(ue):
    from fakeunreal import load_fmbridge
    load_fmbridge()
    from fmbridge import server
    code = "def job():\n    for i in range(3):\n        yield\n    return 'done'\nresult = job()"
    box = {"done": False}
    r = server._run("exec", {"code": code})
    job = [r["gen"], box, r["buf"], 0.0, r["t0"]]
    steps = 0
    while not server._step(job):
        steps += 1
    assert steps == 3 and box["ok"] and box["result"] == "done"


def test_a_broken_module_is_reported_not_fatal(ue, tmp_path):
    bad = BRIDGE / "ops" / "zz_broken_for_test.py"
    bad.write_text("import unreal\nfrom . import op\nraise ImportError('half-copied install')\n")
    try:
        from fakeunreal import load_fmbridge
        ops = load_fmbridge()
        assert "fmbridge.ops.zz_broken_for_test" in ops.broken()
        assert "level.spawn" in ops._OPS  # the rest loaded
        assert "!broken" in run_op("list")
    finally:
        bad.unlink()


def test_drive_runs_generators(ue):
    def job():
        yield
        yield 0.5
        return 7
    assert drive(job()) == (7, 2)


def test_bridge_is_python_311():
    """The editor's Python is 3.11 (Engine/Source/ThirdParty/Python3/Linux/include/patchlevel.h: 3.11.8): no 3.12
    syntax in anything that runs inside it."""
    for p in [ROOT / "unreal" / "init_unreal.py", *BRIDGE.rglob("*.py")]:
        ast.parse(p.read_text(encoding="utf-8"), str(p), feature_version=(3, 11))


def test_fake_value_types(ue):
    r = ue.Rotator(yaw=90)
    f = r.get_forward_vector()
    assert abs(f.y - 1) < 1e-9 and abs(f.x) < 1e-9
    assert ue.Rotator(1, 2, 3).roll == 1  # positional order is roll, pitch, yaw
    assert ue.Color(1, 2, 3).r == 3  # positional order is b, g, r
    look = ue.MathLibrary.find_look_at_rotation(ue.Vector(0, 0, 0), ue.Vector(100, 100, 0))
    assert abs(look.yaw - 45) < 1e-9
    assert ue.SomeNewEnum.VALUE_A == "VALUE_A"
    assert issubclass(ue.SomethingActor, ue.Actor) and issubclass(ue.ThingComponent, ue.SceneComponent)


def test_fake_level_and_assets(ue):
    ue.add_asset("/Game/M/SM_Box", "StaticMesh")
    eas = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    a = eas.spawn_actor_from_object(ue.EditorAssetLibrary.load_asset("/Game/M/SM_Box.SM_Box"), ue.Vector(0, 0, 50))
    a.set_actor_label("Box")
    assert ue.actor("Box") is a and a.static_mesh_component.static_mesh is ue.assets["/Game/M/SM_Box"]
    assert ue.EditorAssetLibrary.list_assets("/Game") == ["/Game/M/SM_Box.SM_Box"]
    tools = ue.AssetToolsHelpers.get_asset_tools()
    assert tools.create_asset("SM_Box", "/Game/M", ue.StaticMesh, None) is None
    assert ue.dialogs == [("overwrite", "/Game/M/SM_Box")]
