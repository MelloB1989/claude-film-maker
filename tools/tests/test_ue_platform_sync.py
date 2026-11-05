"""Sync (filmtools.unreal.sync) with the box faked: the exact scripts (excludes, directions, the DDC's three
stores), the safety checks (unsaved packages, a running editor) and --dry-run."""
from __future__ import annotations

import pytest

from filmtools.unreal import client, sync
from filmtools.unreal import workstation as ws


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.setenv("FILM_UE_BOX", "gpu")
    ws.save(os="linux", project_dir="/srv/ue/projects/Demo", bucket="bkt", region="ap-south-1")
    ran = []
    state = {"active": "inactive", "dirty": {"maps": [], "content": []}}

    def sh(script, timeout=600, root=False):
        ran.append(script)
        if "systemctl is-active" in script:
            return state["active"] + "\n"
        if "aws s3 sync" in script:
            return "synced=up\nsynced=down\nddc=save\nddc=restore\n"
        return ""
    monkeypatch.setattr(ws, "sh", sh)
    monkeypatch.setattr(ws, "editor", lambda action: ran.append(f"editor {action}") or "")
    monkeypatch.setattr(client, "op", lambda name, **k: {"ok": True, "result": {"dirty": state["dirty"]}})
    return ran, state


def test_project_scripts_exclude_what_never_travels(box):
    up = sync.project_script("up")
    assert "aws s3 sync" in up and "/srv/ue/projects/Demo s3://bkt/ue-projects/Demo" in up
    for x in ("'Saved/*'", "'Intermediate/*'", "'DerivedDataCache/*'", "'Binaries/*'", "'Content/_Selftest/*'"):
        assert f"--exclude {x}" in up
    # a plugin built on the box (plugin-build) keeps its Linux build: the later filter wins in aws s3 sync
    assert up.index("--exclude '*/Binaries/*'") < up.index("--include 'Plugins/*/Binaries/Linux/*'")
    down = sync.project_script("down", delete=True)
    assert "--delete" in down and "s3://bkt/ue-projects/Demo /srv/ue/projects/Demo" in down
    with pytest.raises(SystemExit, match="up \\(box -> S3\\) or down"):
        sync.project_script("sideways")


def test_project_up_refuses_unsaved_packages(box):
    ran, state = box
    state["dirty"] = {"maps": ["/Game/Maps/Studio"], "content": []}
    with pytest.raises(SystemExit, match="unsaved packages in the editor \\(1 levels"):
        sync.project("up")
    assert sync.project("up", allow_dirty=True)["ok"]


def test_project_down_needs_the_editor_stopped(box):
    ran, state = box
    state["active"] = "active"
    with pytest.raises(SystemExit, match="--stop-editor"):
        sync.project("down")
    assert sync.project("down", stop_editor=True)["ok"] and "editor stop" in ran


def test_dry_run_runs_nothing(box):
    ran, _ = box
    r = sync.project("up", dry_run=True)
    assert r["dry_run"] and "aws s3 sync" in r["script"] and not ran
    d = sync.ddc("save", version="5.8.4", dry_run=True)
    assert d["s3"] == "s3://bkt/ue-linux/ddc/5.8.4" and not ran


def test_ddc_covers_zen_and_both_file_caches(box):
    s = sync.ddc_script("save")
    assert '"$HOME/.config/Epic/UnrealEngine/Common/Zen/Data" s3://bkt/ue-linux/ddc/5.8.4/zen-data' in s
    assert "/srv/ue/engine/Engine/DerivedDataCache" in s and "/srv/ue/projects/Demo/DerivedDataCache" in s
    r = sync.ddc_script("restore", version="5.8.5")
    assert "mkdir -p" in r and "s3://bkt/ue-linux/ddc/5.8.5/engine-ddc" in r


def test_settings_override_the_s3_layout(box, monkeypatch):
    ws.save(project_s3="s3://other/proj", ddc_s3="s3://other/ddc")
    assert sync.project_s3() == "s3://other/proj" and sync.ddc_s3() == "s3://other/ddc"


def test_windows_and_missing_settings_are_explained(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.setenv("FILM_UE_BOX", "w")
    ws.save(os="windows", project_dir=r"C:\P\Demo")
    with pytest.raises(SystemExit, match="Linux box"):
        sync.project("up")
    with pytest.raises(SystemExit, match="no bucket set"):
        sync.project_s3()
