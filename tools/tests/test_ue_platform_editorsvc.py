"""The editor as a service (filmtools.unreal.editorsvc) with the box's shell faked: unit state, start/stop/restart,
arguments for one start, crash reports, waiting for the bridge (and failing fast when the unit died), Windows."""
from __future__ import annotations

import pytest

from filmtools.unreal import client, editorsvc
from filmtools.unreal import workstation as ws


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.setenv("FILM_UE_BOX", "gpu")
    ws.save(os="linux", project_dir="/srv/ue/projects/Demo")
    ran = []
    answers = {}

    def sh(script, timeout=600, root=False):
        ran.append((script, root))
        for k, v in answers.items():
            if k in script:
                return v(script) if callable(v) else v
        return ""
    monkeypatch.setattr(ws, "sh", sh)
    return ran, answers


UNIT = "ActiveState=active\nSubState=running\nResult=success\nNRestarts=2\nMainPID=4242\n" \
       "ExecMainStartTimestamp=Thu 2026-11-05 01:00:00 UTC\nExecMainStatus=0\n"


def test_unit_state_is_parsed(box):
    ran, answers = box
    answers["systemctl show"] = UNIT
    u = editorsvc.unit()
    assert u == {"active": "active", "sub": "running", "result": "success", "restarts": 2, "pid": 4242,
                 "since": "Thu 2026-11-05 01:00:00 UTC", "exit_status": "0"}
    assert ran[0][1] is True and "ue-editor" in ran[0][0]


def test_restart_with_arguments_for_one_start(box, monkeypatch):
    ran, answers = box
    answers["systemctl show"] = UNIT
    out = editorsvc.control("restart", once_args="-AUTH_TYPE=exchangecode -AUTH_PASSWORD=x")
    once = [s for s, root in ran if "ue-args-once" in s][0]
    assert "umask 077" in once and "-AUTH_TYPE=exchangecode" in once and ("umask" in once)
    assert [root for s, root in ran if "ue-args-once" in s] == [False]   # written as the editor's user
    assert any("systemctl restart ue-editor" in s and root for s, root in ran) and out["unit"]["pid"] == 4242
    with pytest.raises(SystemExit, match="only applies"):
        editorsvc.control("stop", once_args="-x")
    with pytest.raises(SystemExit, match="start, stop or restart"):
        editorsvc.control("reboot")


def test_crash_reports_are_read(box):
    ran, answers = box
    answers["crashinfo"] = ("crashinfo-HostStudio-pid-1-AB\t1762300000\tException was \"SIGSEGV: invalid attempt\"\t"
                            "[..]LogCore: Fatal error: [File:VulkanMemory.cpp]\tOut Of Memory, trying to allocate 786432 bytes\n"
                            "crashinfo-HostStudio-pid-2-CD\t1762200000\t\t\t\n")
    rows = editorsvc.crashes(5)
    assert rows[0]["exception"] == "SIGSEGV: invalid attempt" and "VulkanMemory" in rows[0]["fatal"]
    assert rows[0]["out_of_memory"].startswith("Out Of Memory") and rows[1]["fatal"] is None and rows[1]["time"]


def test_wait_bridge_fails_fast_when_the_unit_died(box, monkeypatch):
    ran, answers = box
    answers["systemctl show"] = UNIT.replace("ActiveState=active", "ActiveState=failed").replace("success", "exit-code")
    answers["crashinfo"] = "crashinfo-x\t1\tException was \"SIGSEGV\"\t\t\n"
    monkeypatch.setattr(client, "health", lambda **k: (_ for _ in ()).throw(client.BridgeDown("no answer")))
    monkeypatch.setattr(client, "token", lambda refresh=False: "t")
    with pytest.raises(SystemExit, match="unit failed \\(exit-code, 2 restarts\\); last crash: SIGSEGV"):
        editorsvc.wait_bridge(60, sleep=lambda s: None)


def test_wait_bridge_returns_health_once_up(box, monkeypatch):
    calls = {"n": 0}

    def health(**k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise client.BridgeDown("not yet")
        return {"ok": True, "engine": "5.8.4"}
    box[1]["systemctl show"] = UNIT
    monkeypatch.setattr(client, "health", health)
    monkeypatch.setattr(client, "token", lambda refresh=False: "t")
    assert editorsvc.wait_bridge(60, sleep=lambda s: None)["engine"] == "5.8.4"


def test_logs_from_the_editor_or_the_journal(box):
    ran, answers = box
    editorsvc.log(50)
    assert "tail -n 50" in ran[-1][0] and "/srv/ue/projects/Demo/Saved/Logs" in ran[-1][0]
    editorsvc.log(30, journal=True)
    assert "journalctl -u ue-editor -n 30" in ran[-1][0] and ran[-1][1] is True


def test_windows_can_stop_and_inspect_but_not_start(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.setenv("FILM_UE_BOX", "win")
    ws.save(os="windows")
    ps = []
    monkeypatch.setattr(ws, "ps", lambda s, t=600: ps.append(s) or '{"pid": 7, "rss_mb": 9000, "responding": true}')
    assert editorsvc.control("stop")["unit"]["pid"] == 7 and "Stop-Process" in ps[0]
    with pytest.raises(SystemExit, match="desktop session"):
        editorsvc.control("start")
