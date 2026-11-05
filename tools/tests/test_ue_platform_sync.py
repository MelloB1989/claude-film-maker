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


def test_a_real_persons_face_assets_never_sync(box):
    """Round 3: the operator's capture, identity and character stay on the box (and Epic's cloud). Their excludes come
    after every include, so nothing brings them back; --delete never touches an excluded path on the box."""
    for direction, kw in (("up", {}), ("down", {"delete": True})):
        s = sync.project_script(direction, **kw)
        for x in ("'Content/Host/OperatorCapture/*'", "'Content/Host/Host_Op*'", "'Content/Host/Unpacked/Host/*'",
                  "'Capture/operator-face/*'"):
            assert f"--exclude {x}" in s
            assert s.index(f"--exclude {x}") > s.index("--include 'Plugins/*/Binaries/Linux/*'")
    ws.save(private_paths=["Content/People/*"])
    assert "--exclude 'Content/People/*'" in sync.project_script("up")


def test_once_face_data_is_on_the_box_uploads_go_private_only(box):
    """The operator's rule (round 3): with face-derived data on the box, the project and the DDC are saved only under
    .../private/ (SSE-KMS, the box's role alone reads it); a private destination keeps the face assets, nothing else may."""
    assert "--exclude 'Content/Host/OperatorCapture/*'" in sync.project_script("up")
    sync.ddc_script("save")  # no face data yet: the normal prefix is fine
    ws.save(face_data="yes")
    with pytest.raises(SystemExit, match="private"):
        sync.project_script("up")
    with pytest.raises(SystemExit, match="private"):
        sync.ddc_script("save")
    assert "s3://bkt/ue-projects/Demo /srv/ue/projects/Demo" in sync.project_script("down")  # downloads unaffected
    sync.ddc_script("restore")
    ws.save(project_s3="s3://bkt/ue-linux/private/project/HostStudio", ddc_s3="s3://bkt/ue-linux/private/ddc/5.8.4")
    up = sync.project_script("up")
    assert "s3://bkt/ue-linux/private/project/HostStudio" in up and "OperatorCapture" not in up
    assert "--sse aws:kms" in up and "--sse-kms-key-id" not in up  # encrypted in the command, whatever the bucket says
    save = sync.ddc_script("save")
    assert "s3://bkt/ue-linux/private/ddc/5.8.4/zen-data" in save and save.count("--sse aws:kms") == 3
    assert "--sse" not in sync.ddc_script("restore") and "--sse" not in sync.project_script("down")
    ws.save(kms_key="alias/ue-private")
    assert "--sse aws:kms --sse-kms-key-id alias/ue-private" in sync.project_script("up")


def test_a_render_folder_syncs_under_the_same_face_data_rule(box):
    """Round 3: the finals and their reports go box -> S3 with film-ue (never a raw aws s3 cp to a private path):
    with face data on the box only under .../private/, KMS in the command there."""
    ran, _ = box
    up = sync.dir_script("up", "/srv/ue/reel/r3/final_c", "s3://bkt/ue-linux/shoot/r3/final/")
    assert "/srv/ue/reel/r3/final_c s3://bkt/ue-linux/shoot/r3/final/" in up and "--sse" not in up
    ws.save(face_data="yes")
    with pytest.raises(SystemExit, match="private"):
        sync.dir_script("up", "/srv/ue/reel/r3/final_c", "s3://bkt/ue-linux/shoot/r3/final/")
    priv = "s3://bkt/ue-linux/private/renders/r3/final_c/"
    up = sync.dir_script("up", "/srv/ue/reel/r3/final_c", priv)
    assert "--sse aws:kms" in up and up.rstrip().endswith("echo synced=up")
    ws.save(kms_key="alias/ue-private")
    assert "--sse aws:kms --sse-kms-key-id alias/ue-private" in sync.dir_script("up", "/srv/x", priv)
    down = sync.dir_script("down", "/srv/ue/pulled", priv)
    assert down.startswith("mkdir -p /srv/ue/pulled") and "--sse" not in down  # downloads unaffected
    res = sync.sync_dir("up", "/srv/ue/reel/r3/final_c", priv)
    assert res["ok"] and "aws s3 sync" in ran[-1]
    assert sync.sync_dir("up", "/srv/x", priv, dry_run=True)["dry_run"]
    with pytest.raises(SystemExit, match="up .* or down"):
        sync.dir_script("save", "/srv/x", priv)
    with pytest.raises(SystemExit, match="--local"):
        sync.dir_script("up", "", priv)
