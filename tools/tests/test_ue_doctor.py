"""B11: editor.doctor on the fake engine, and film-ue doctor's client side with the bridge up, down and failing."""
from __future__ import annotations

import pytest

from fakeunreal import run_op


def test_doctor_on_a_healthy_fake(ue):
    ue.stub("PluginBlueprintLibrary.get_enabled_plugin_names", lambda: [
        "PythonScriptPlugin", "EditorScriptingUtilities", "MovieRenderPipeline", "SequencerScripting",
        "LevelSequenceEditor", "MetaHumanCharacter", "MetaHuman", "Fab", "USDImporter"])
    ue.stub("SystemLibrary.get_command_line", lambda: "UnrealEditor Demo.uproject -RenderOffscreen -unattended")
    r = run_op("editor.doctor", min_free_gb=0)
    assert r["pass"], r["issues"]
    assert r["metrics"]["engine"].startswith("5.8") and r["metrics"]["plugins_missing"] == []
    assert r["metrics"]["ops"] > 100 and r["metrics"]["broken"] == []
    assert all(i["code"].startswith("doctor.") for i in r["issues"])


def test_doctor_flags_nullrhi_and_missing_plugins(ue):
    ue.stub("PluginBlueprintLibrary.get_enabled_plugin_names", lambda: ["PythonScriptPlugin"])
    ue.stub("SystemLibrary.get_command_line", lambda: "UnrealEditor -nullrhi")
    r = run_op("editor.doctor", min_free_gb=0)
    assert not r["pass"]
    codes = {(i["code"], i.get("subject")) for i in r["issues"]}
    assert ("doctor.nullrhi", None) in codes and ("doctor.plugin_missing", "MovieRenderPipeline") in codes
    fails = [i for i in r["issues"] if i["severity"] == "fail"]
    assert all(i["fix"] for i in fails)


@pytest.fixture
def cli(monkeypatch):
    from filmtools.unreal import cli_doctor, client, workstation as ws
    monkeypatch.setattr(ws, "conf", lambda: {"os": "linux", "project_dir": "/srv/ue/projects/Demo"})
    return cli_doctor, client


def test_cli_bridge_down(cli, monkeypatch):
    cli_doctor, client = cli

    def down(retry_s=0):
        raise SystemExit("connection refused")
    monkeypatch.setattr(client, "health", down)
    r = cli_doctor.run()
    assert not r["pass"] and r["issues"][0]["code"] == "doctor.bridge_down" and "editor status" in r["issues"][0]["fix"]


def test_cli_merges_the_editor_check(cli, monkeypatch):
    cli_doctor, client = cli
    monkeypatch.setattr(client, "health", lambda retry_s=0: {"engine": "5.8.4", "platform": "linux"})
    monkeypatch.setattr(client, "op", lambda name, timeout=0, **kw: {"ok": True, "result": {
        "pass": True, "metrics": {"engine": "5.8.4", "ops": 200},
        "issues": [{"code": "doctor.epic_login", "severity": "warn", "message": "no Epic sign-in", "fix": "film-ue epic-login"}]}})
    r = cli_doctor.run()
    assert r["pass"] and r["metrics"]["ops"] == 200
    text = cli_doctor.format_text(r)
    assert text.startswith("OK") and "fix: film-ue epic-login" in text
