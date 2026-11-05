"""film-ue's Linux backend, offline: settings per box, paths and commands in the box's own style, the install bundle,
the PoC frame comparison, and the bridge's GUI module refusing to load where there is no Windows desktop."""
from __future__ import annotations

import base64
import importlib.util
import io
import sys
import tarfile
from pathlib import Path

import pytest

from filmtools.unreal import workstation as ws

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.delenv("FILM_UE_BOX", raising=False)
    return tmp_path


@pytest.fixture
def ssm(monkeypatch):
    sent = []

    def fake(document, script, timeout):
        sent.append((document, script))
        return ""
    monkeypatch.setattr(ws, "_ssm", fake)
    return sent


def test_windows_is_still_the_default(home):
    c = ws.conf()
    assert c["os"] == "windows" and c["project_dir"] == r"C:\UEProjects\HostStudio" and c["local_port"] == 18765
    assert ws.project("Saved", "fmbridge.token") == r"C:\UEProjects\HostStudio\Saved\fmbridge.token"
    assert ws.state_path("token") == home / "film-ue.token"


def test_linux_box_has_its_own_settings_and_posix_paths(home, monkeypatch):
    monkeypatch.setenv("FILM_UE_BOX", "linux")
    ws.save(os="linux", instance="i-0123456789abcdef0", project_dir="/srv/ue/projects/Demo", local_port=18766)
    assert (home / "film-ue.linux.json").exists() and not (home / "film-ue.json").exists()
    c = ws.conf()
    assert c["user"] == "ubuntu" and c["service"] == "ue-editor" and c["local_port"] == 18766
    assert ws.project("Content", "Python", "fmbridge", "server.py") == "/srv/ue/projects/Demo/Content/Python/fmbridge/server.py"
    assert ws.state_path("token") == home / "film-ue.linux.token"


def test_linux_project_dir_must_be_set(home, monkeypatch):
    monkeypatch.setenv("FILM_UE_BOX", "fresh")
    ws.save(os="linux")
    with pytest.raises(SystemExit, match="no project dir"):
        ws.project("Saved")


def test_linux_commands_run_as_the_editor_user_unless_root(home, ssm, monkeypatch):
    monkeypatch.setenv("FILM_UE_BOX", "linux")
    ws.save(os="linux", project_dir="/srv/ue/projects/Demo")
    ws.put_text("/srv/ue/projects/Demo/Saved/a b.txt", b"hello")
    ws.editor("restart")
    (doc1, s1), (doc2, s2) = ssm
    assert doc1 == doc2 == "AWS-RunShellScript"
    assert s1.startswith("set -e\nrunuser -u ubuntu -- bash -c ") and base64.b64encode(b"hello").decode() in s1
    assert "'/srv/ue/projects/Demo/Saved/a b.txt'" in s1.replace("'\"'\"'", "'")
    assert s2 == "set -e\nsystemctl restart ue-editor"


def test_windows_commands_stay_powershell(home, ssm):
    ws.put_text(r"C:\x\y.txt", b"hi")
    assert ssm[0][0] == "AWS-RunPowerShellScript" and "WriteAllBytes" in ssm[0][1]
    with pytest.raises(SystemExit, match="DCV login"):
        ws.editor("start")


def test_linux_install_unpacks_one_bundle_and_restarts(home, ssm, monkeypatch):
    from filmtools.unreal import cli, client
    monkeypatch.setenv("FILM_UE_BOX", "linux")
    ws.save(os="linux", project_dir="/srv/ue/projects/Demo")
    monkeypatch.setattr(cli, "_bridge_up", lambda: False)
    monkeypatch.setattr(cli, "wait_bridge", lambda seconds=900: {"ok": True, "engine": "5.8.4"})
    monkeypatch.setattr(client, "token", lambda refresh=False: "t")
    msg = cli.install()
    assert "editor restart" in msg
    *unpack, restart = ssm
    assert restart[1].endswith("systemctl restart ue-editor")
    if len(unpack) == 1:
        b64 = unpack[0][1].split("echo ", 1)[1].split(" ", 1)[0]
    else:  # sent in parts (printf %s PART >> file), then unpacked
        b64 = "".join(u[1].split("printf %s ", 1)[1].split(" ", 1)[0] for u in unpack[:-1])
        assert all(len(u[1]) < 100_000 for u in unpack)
    unpack = unpack[-1]
    names = tarfile.open(fileobj=io.BytesIO(base64.b64decode(b64))).getnames()
    assert "init_unreal.py" in names and "fmbridge/server.py" in names and "fmbridge/ops/render.py" in names
    assert "/srv/ue/projects/Demo/Content/Python" in unpack[1]


def test_compare_reports_psnr_and_the_worst_frame(tmp_path):
    np = pytest.importorskip("numpy")
    from PIL import Image
    from filmtools.unreal import poc
    new, ref = tmp_path / "new", tmp_path / "ref"
    new.mkdir()
    ref.mkdir()
    base = (np.random.default_rng(0).random((36, 64, 3)) * 255).astype("uint8")
    for i, noise in enumerate((0, 2, 8)):
        Image.fromarray(base).save(ref / f"{i:04d}.png")
        Image.fromarray(np.clip(base.astype(int) + noise, 0, 255).astype("uint8")).save(new / f"{i:04d}.png")
    r = poc.compare(new, ref, {"skin": [4, 4, 10, 8]})
    assert r["matched"] == 3 and r["worst"] == "0002" and r["psnr_min"] < r["psnr_mean"]
    assert r["frames"][0]["ssim"] == 1.0 and r["ssim_min"] < 1.0 and r["shift_rgb_mean"][0] > 0
    assert (tmp_path / "new_vs_ref_0002.jpg").exists() and Path(r["sheet"]).exists()
    assert r["crop_skin"][0] > 0 and "crop_skin" in r["frames"][2]


def test_gui_refuses_to_load_without_a_windows_desktop():
    if sys.platform == "win32":
        pytest.skip("this is the Windows desktop")
    spec = importlib.util.spec_from_file_location("fmbridge_gui", ROOT / "unreal" / "fmbridge" / "gui.py")
    with pytest.raises(ImportError, match="Windows desktop"):
        spec.loader.exec_module(importlib.util.module_from_spec(spec))


def test_bridge_package_does_not_import_gui_at_load():
    src = (ROOT / "unreal" / "fmbridge" / "__init__.py").read_text()
    assert "import gui" not in src.replace("fmbridge.gui", "")
    server = (ROOT / "unreal" / "fmbridge" / "server.py").read_text()
    assert "from . import gui\n" not in server.replace("        from . import gui\n        return gui", "")


def test_ssh_transport_runs_bash_as_root_with_the_script_on_stdin(home, monkeypatch):
    import subprocess
    calls = []

    class R:
        returncode, stdout, stderr = 0, "ok\n", ""

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)) or R())
    monkeypatch.setenv("FILM_UE_BOX", "fleet")
    ws.save(os="linux", transport="ssh", ssh="ubuntu@192.0.2.10", ssh_key="/tmp/k", project_dir="/srv/ue/projects/Demo")
    assert ws.sh("ls", 60) == "ok\n"
    cmd, kw = calls[0]
    assert cmd[0] == "ssh" and cmd[-4:] == ["ubuntu@192.0.2.10", "sudo", "bash", "-s"] and "-i" in cmd
    assert kw["input"].startswith("set -e\nrunuser -u ubuntu -- bash -c ls")
    assert ws.start()["ssh"] == "ubuntu@192.0.2.10"  # never starts or stops a box it does not own


def test_bridge_over_ssm_commands_without_a_tunnel(home, monkeypatch):
    from filmtools.unreal import client
    monkeypatch.setenv("FILM_UE_BOX", "linux")
    ws.save(os="linux", project_dir="/srv/ue/projects/Demo", bridge="ssm", bucket="b")
    seen = []

    def fake_sh(script, timeout=600, root=False):
        seen.append(script)
        body = base64.b64encode(b'{"ok": true, "engine": "5.8.4"}').decode()
        return f"FMCODE=200 FMSIZE=31\nFMBODY\n{body}\n"
    monkeypatch.setattr(ws, "sh", fake_sh)
    monkeypatch.setattr(client, "tunnel", lambda *a: pytest.fail("no tunnel in bridge=ssm"))
    assert client.call("/op", {"name": "list"}) == {"ok": True, "engine": "5.8.4"}
    s = seen[0]
    assert "curl -s" in s and "/srv/ue/projects/Demo/Saved/fmbridge.token" in s and "http://127.0.0.1:18765/op" in s
    assert "base64 -d > /tmp/fmreq_" in s and "--data-binary @/tmp/fmreq_" in s
    monkeypatch.setattr(ws, "sh", lambda *a, **k: "FMCODE=000 FMSIZE=0\nFMBODY\n\n")
    with pytest.raises(SystemExit, match="no answer"):
        client.health()


def _ue_epic(tmp_path, *args, s3_obj=None, env_extra=None):
    """Run unreal/linux/ue-epic.sh with HOME in tmp_path and a fake `aws` that keeps S3 objects as local files."""
    import os
    import subprocess
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    store = tmp_path / "s3"
    store.mkdir(exist_ok=True)
    aws = bin_dir / "aws"
    aws.write_text('#!/bin/sh\n# aws s3 cp [--only-show-errors] [--sse aws:kms] SRC DST, SRC/DST "-" or s3://...\n'
                   'args=""; for a in "$@"; do case "$a" in s3|cp|--only-show-errors|--sse|aws:kms) ;; *) args="$args $a";; esac; done\n'
                   'set -- $args; f() { echo "$STORE/$(echo "$1" | tr / _)"; }\n'
                   'case "$1" in s3://*) [ -f "$(f "$1")" ] || exit 1; if [ "$2" = - ]; then cat "$(f "$1")"; else cp "$(f "$1")" "$2"; fi;;\n'
                   '*) if [ "$1" = - ]; then cat > "$(f "$2")"; else cp "$1" "$(f "$2")"; fi;; esac\n')
    aws.chmod(0o755)
    script = ROOT / "unreal" / "linux" / "ue-epic.sh"
    env = {**os.environ, "HOME": str(tmp_path / "home"), "PATH": f"{bin_dir}:{os.environ['PATH']}", "STORE": str(store),
           "EPIC_S3": s3_obj or "s3://b/secrets/epic.tgz", **(env_extra or {})}
    (tmp_path / "home").mkdir(exist_ok=True)
    return subprocess.run(["bash", str(script), *args], env=env, capture_output=True, text=True)


def test_ue_epic_never_saves_an_empty_sign_in_and_restores_any_archive_prefix(tmp_path):
    import subprocess
    if sys.platform == "win32":
        pytest.skip("bash")
    r = _ue_epic(tmp_path, "save")
    assert "not signed in" in r.stdout and not list((tmp_path / "s3").iterdir())
    assert _ue_epic(tmp_path, "status").stdout.split() == ["signed_in=no", "sign_ins=0"]
    # an archive made elsewhere, with the full home path inside it (tar of /home/<user>/.local/share/.eos_sdk)
    src = tmp_path / "src" / "home" / "op" / ".local" / "share" / ".eos_sdk" / "keychain" / "abc" / "persistent_auth"
    src.mkdir(parents=True)
    (src / "credential").write_text("fake")
    subprocess.run(["tar", "-czf", str(tmp_path / "s3" / "s3:__b_secrets_epic.tgz"), "-C", str(tmp_path / "src"), "home"],
                   check=True)
    r = _ue_epic(tmp_path, "restore")
    assert "restored" in r.stdout, r.stderr
    cred = tmp_path / "home" / ".local" / "share" / ".eos_sdk" / "keychain" / "abc" / "persistent_auth" / "credential"
    assert cred.read_text() == "fake" and oct(cred.stat().st_mode & 0o777) == "0o600"
    assert "kept" in _ue_epic(tmp_path, "restore").stdout  # never replaces a sign-in the box already has
    assert "saved" in _ue_epic(tmp_path, "save").stdout


def test_ue_epic_url_keeps_only_the_code(tmp_path):
    import os
    import subprocess
    if sys.platform == "win32":
        pytest.skip("bash")
    link = tmp_path / "ue-epic-url"
    os.symlink(ROOT / "unreal" / "linux" / "ue-epic.sh", link)
    home = tmp_path / "home"
    home.mkdir()
    subprocess.run(["bash", str(link), "https://www.epicgames.com/activate?userCode=ABCD1234&x=1"],
                   env={**os.environ, "HOME": str(home)}, check=True)
    assert _ue_epic(tmp_path, "code").stdout.strip() == "code=ABCD1234"
    _ue_epic(tmp_path, "clear-code")
    assert _ue_epic(tmp_path, "code").stdout.strip() == ""
