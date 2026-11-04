"""filmtools.unreal.transport offline: the same calls reach a Linux or a Windows box over SSM, ssh or locally, in the
box's own shell, with fakes in place of AWS and ssh."""
from __future__ import annotations

import base64
import subprocess

import pytest

from filmtools.unreal import transport as t


class Done:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def ssm_fake(answers=None):
    sent = []

    def ssm(document, script, timeout):
        sent.append((document, script, timeout))
        for key, out in (answers or {}).items():
            if key in script:
                return out
        return ""
    return ssm, sent


def test_ssm_linux_runs_bash_as_the_editor_user_or_root():
    ssm, sent = ssm_fake()
    box = t.SSM({"os": "linux", "user": "ue"}, ssm=ssm)
    box.run("ls /srv", 30)
    box.run("systemctl restart ue-editor", root=True)
    (d1, s1, to1), (d2, s2, _) = sent
    assert d1 == d2 == "AWS-RunShellScript" and to1 == 30
    assert s1 == "set -e\nrunuser -u ue -- bash -c 'ls /srv'" and s2 == "set -e\nsystemctl restart ue-editor"


def test_ssm_windows_runs_powershell_and_quotes_paths():
    ssm, sent = ssm_fake()
    box = t.SSM({"os": "windows"}, ssm=ssm)
    box.put(r"C:\it's\a.txt", b"hi")
    doc, script, _ = sent[0]
    assert doc == "AWS-RunPowerShellScript" and r"'C:\it''s\a.txt'" in script and "WriteAllBytes" in script


@pytest.mark.parametrize("os_", ["linux", "windows"])
def test_get_reads_a_file_back_or_none(os_):
    data = b"\x00binary\xff"
    ssm, _ = ssm_fake({"there": f"noise\nFMFILE\n{base64.b64encode(data).decode()}\n"})
    box = t.SSM({"os": os_}, ssm=ssm)
    assert box.get("/x/there") == data
    assert box.get("/x/missing") is None


def test_ssm_needs_an_instance_for_a_real_command():
    with pytest.raises(SystemExit, match="no instance set"):
        t.ssm_cmd({"region": "r"}, "AWS-RunShellScript", "ls", 10, aws=lambda *a, **k: pytest.fail("no aws call"))


def test_ssm_cmd_waits_for_the_invocation_and_surfaces_failures(monkeypatch):
    monkeypatch.setattr(t.time, "sleep", lambda s: None)
    calls = []

    def aws(*args, **kw):
        calls.append(args)
        if args[1] == "send-command":
            return {"Command": {"CommandId": "c1"}}
        return {"Status": "InProgress"} if len(calls) < 3 else {"Status": "Failed", "StandardErrorContent": "boom"}

    with pytest.raises(SystemExit, match="Failed: boom"):
        t.ssm_cmd({"instance": "i-1", "region": "r"}, "AWS-RunShellScript", "ls", 10, aws=aws)


def test_ssh_linux_and_windows(monkeypatch):
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        return Done("ok\n")

    lin = t.SSH({"os": "linux", "ssh": "ubuntu@192.0.2.10", "ssh_key": "/k", "user": "ubuntu"}, runner=run)
    assert lin.run("ls", 60) == "ok\n"
    cmd, kw = calls[-1]
    assert cmd[-4:] == ["ubuntu@192.0.2.10", "sudo", "bash", "-s"] and kw["input"].startswith("set -e\nrunuser")
    win = t.SSH({"os": "windows", "ssh": "Administrator@192.0.2.11"}, runner=run)
    win.run("Get-Process", 60)
    cmd, kw = calls[-1]
    assert cmd[-5:] == ["powershell", "-NoProfile", "-NonInteractive", "-Command", "-"] and kw["input"] == "Get-Process"
    with pytest.raises(SystemExit, match="no ssh target"):
        t.SSH({"os": "linux"})


def test_ssh_failure_and_timeout_are_actionable():
    box = t.SSH({"os": "linux", "ssh": "u@h"}, runner=lambda cmd, **kw: Done("", 255, "Connection refused"))
    with pytest.raises(SystemExit, match="failed \\(255\\): Connection refused"):
        box.run("ls")

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)
    with pytest.raises(SystemExit, match="timed out"):
        t.SSH({"os": "linux", "ssh": "u@h"}, runner=slow).run("sleep 9", 1)


def test_ssh_folders_go_by_rsync_on_linux_and_scp_on_windows(tmp_path):
    calls = []
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_text("x")
    run = lambda cmd, **kw: calls.append(cmd) or Done()
    assert t.SSH({"os": "linux", "ssh": "u@h", "user": "ue"}, runner=run).push_dir(str(tmp_path / "a"), "/srv/a") == 1
    assert calls[-1][0] == "rsync" and "--rsync-path=sudo -u ue rsync" in calls[-1] and calls[-1][-1] == "u@h:/srv/a/"
    t.SSH({"os": "windows", "ssh": "u@h"}, runner=run).pull_dir(r"C:\r", str(tmp_path / "b"))
    assert calls[-1][0] == "scp" and calls[-1][-2] == "u@h:C:\\r/"


def test_local_runs_here_and_copies_files(tmp_path):
    calls = []
    box = t.Local({"os": "linux"}, runner=lambda cmd, **kw: calls.append(cmd) or Done("out"))
    assert box.run("echo hi") == "out" and calls[-1] == ["bash", "-c", "echo hi"]
    p = tmp_path / "d" / "f.bin"
    box.put(str(p), b"abc")
    assert box.get(str(p)) == b"abc" and box.get(str(tmp_path / "none")) is None and box.exists(str(p))
    assert box.pull_dir(str(tmp_path / "d"), str(tmp_path / "e")) == 1 and (tmp_path / "e" / "f.bin").read_bytes() == b"abc"
    assert box.forward(18765, 18765) is None
    with pytest.raises(SystemExit, match="needs no tunnel"):
        box.forward(18765, 18766)


def test_local_windows_uses_powershell():
    calls = []
    t.Local({"os": "windows"}, runner=lambda cmd, **kw: calls.append(cmd) or Done()).run("Get-Date")
    assert calls[-1][:2] == ["powershell", "-NoProfile"]


def test_get_picks_the_transport_and_rejects_unknown_ones():
    assert isinstance(t.get({"transport": "local", "os": "linux"}), t.Local)
    assert isinstance(t.get({"os": "linux"}), t.SSM)
    with pytest.raises(SystemExit, match="one of ssm, ssh, local"):
        t.get({"transport": "carrier-pigeon"})


def test_paths_join_in_the_box_style():
    assert t.Local({"os": "windows"}).path("C:\\P", "Saved", "a.png") == r"C:\P\Saved\a.png"
    assert t.Local({"os": "linux"}).path("/srv/p", "Saved") == "/srv/p/Saved"


def test_ssm_folders_through_the_bucket_are_removed_after(monkeypatch, tmp_path):
    ssm, sent = ssm_fake()
    local_calls = []
    box = t.SSM({"os": "linux", "region": "r", "bucket": "b"}, ssm=ssm)
    monkeypatch.setattr(box, "_local_s3", lambda *a: local_calls.append(a))
    (tmp_path / "up").mkdir()
    (tmp_path / "up" / "x").write_text("1")
    assert box.push_dir(str(tmp_path / "up"), "/srv/in") == 1
    assert local_calls[0][0] == "sync" and local_calls[-1][:2] == ("rm", "--recursive")
    assert "aws s3 sync --only-show-errors s3://b/film-ue/up-up-" in sent[0][1]
    with pytest.raises(SystemExit, match="no bucket set"):
        t.SSM({"os": "linux", "region": "r"}, ssm=ssm).pull_dir("/x", str(tmp_path / "y"))
