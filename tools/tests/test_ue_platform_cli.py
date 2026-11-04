"""cli_platform: it registers only the commands nobody else has, parses them, and dispatches to the right function."""
from __future__ import annotations

import argparse
import json

import pytest

from filmtools.unreal import cli_platform


def parser(taken=()):
    ap = argparse.ArgumentParser()
    ap.add_argument("--box")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for t in taken:
        sub.add_parser(t)
    cli_platform._MINE.clear()
    cli_platform.register(sub)
    return ap


def test_commands_another_module_has_are_left_to_it():
    parser(taken=("editor", "provision"))
    assert "editor" not in cli_platform._MINE and "provision" not in cli_platform._MINE
    assert {"box", "profile", "sync", "sh", "epic-login", "desktop"} <= cli_platform._MINE
    assert cli_platform.dispatch(argparse.Namespace(cmd="editor")) is False
    assert cli_platform.dispatch(argparse.Namespace(cmd="health")) is False


def test_box_up_parses_and_dispatches(monkeypatch, capsys):
    from filmtools.unreal import boxes
    seen = {}
    monkeypatch.setattr(boxes, "up", lambda name, **kw: seen.update(name=name, **kw) or {"id": "i-1"})
    a = parser().parse_args(["box", "up", "gpu1", "--ttl", "2h", "--spot", "--like", "linux", "--no-wait"])
    assert cli_platform.dispatch(a) is True
    assert seen["name"] == "gpu1" and seen["ttl"] == "2h" and seen["spot"] and seen["like"] == "linux"
    assert seen["wait"] is False and json.loads(capsys.readouterr().out) == {"id": "i-1"}


def test_sync_and_editor_and_sh(monkeypatch, capsys):
    from filmtools.unreal import editorsvc, sync
    from filmtools.unreal import workstation as ws
    monkeypatch.setattr(sync, "project", lambda d, **kw: {"direction": d, **kw})
    cli_platform.dispatch(parser().parse_args(["sync", "project", "up", "--dry-run"]))
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    monkeypatch.setattr(editorsvc, "control", lambda act, **kw: {"action": act, **kw})
    cli_platform.dispatch(parser().parse_args(["editor", "restart", "--wait", "--once-args=-x"]))
    assert json.loads(capsys.readouterr().out) == {"action": "restart", "wait": True, "once_args": "-x"}

    class T:
        def run(self, script, timeout, root=False):
            return f"{script}|{timeout}|{root}"
    monkeypatch.setattr(ws, "transport", lambda: T())
    cli_platform.dispatch(parser().parse_args(["sh", "uptime", "--root", "--timeout", "30"]))
    assert capsys.readouterr().out.strip() == "uptime|30|True"


def test_linux_only_commands_say_so_on_windows(tmp_path, monkeypatch):
    from filmtools.unreal import workstation as ws
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.setenv("FILM_UE_BOX", "w")
    ws.save(os="windows")
    with pytest.raises(SystemExit, match="Linux box"):
        cli_platform.dispatch(parser().parse_args(["epic-login"]))
