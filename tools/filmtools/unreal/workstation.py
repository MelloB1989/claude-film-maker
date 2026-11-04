"""The Unreal workstation on EC2: settings, start/stop/state, commands and files on it over SSM, big folders through S3.
Windows (PowerShell, the editor on a logged-in desktop) or Linux (shell, the editor offscreen under systemd), by the
box's `os` setting.

Settings live in ~/.config/film-ue.json: {"region", "instance", "os", "project_dir", "port", "key", "bucket"} (key: the
RSA key pair that decrypts a Windows box's Administrator password; bucket: an S3 bucket for big folders both ways).
Linux boxes also take {"user": the account the editor runs as, "service": its systemd unit} and may be reached over
ssh instead of SSM: {"transport": "ssh", "ssh": "ubuntu@<host>", "ssh_key": <path>} (commands over ssh, the bridge
through `ssh -L`, folders by rsync; for a box someone else starts and stops). With no Session Manager plugin for a
tunnel, {"bridge": "ssm"} sends each bridge call as one SSM command (curl on the box). Several boxes: set
FILM_UE_BOX=<name> (or `film-ue --box <name>`) and they live in film-ue.<name>.json, each with its own token and
tunnel (give each its own `local_port`). Nothing secret is stored there; the bridge token is cached beside it.
"""
from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath, PureWindowsPath

CONF_DIR = Path(os.environ.get("FILM_UE_CONF_DIR") or Path.home() / ".config")  # settings, tokens, tunnel state
DEFAULTS = {"region": "ap-south-1", "instance": "", "os": "windows", "project_dir": r"C:\UEProjects\HostStudio",
            "port": 18765, "key": str(Path.home() / ".ssh" / "ue-workstation.pem")}
LINUX_DEFAULTS = {"project_dir": "", "user": "ubuntu", "service": "ue-editor", "transport": "ssm"}


def box() -> str:
    return os.environ.get("FILM_UE_BOX", "")


def state_path(kind: str) -> Path:
    """A per-box file beside the settings: kind "json" (the settings), "token", "tunnel.json", "tunnel.log"."""
    return CONF_DIR / (f"film-ue.{box()}.{kind}" if box() else f"film-ue.{kind}")


def conf() -> dict:
    c = dict(DEFAULTS)
    saved = json.loads(state_path("json").read_text()) if state_path("json").exists() else {}
    if saved.get("os") == "linux":
        c.update(LINUX_DEFAULTS)
    c.update(saved)
    c.setdefault("local_port", c["port"])
    return c


def save(**kv) -> dict:
    p = state_path("json")
    c = json.loads(p.read_text()) if p.exists() else {}
    c.update(kv)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(c, indent=1))
    return conf()


def linux() -> bool:
    return conf()["os"] == "linux"


def over_ssh() -> bool:
    return conf().get("transport") == "ssh"


def _ssh_base() -> list:
    c = conf()
    if not c.get("ssh"):
        raise SystemExit("no ssh target set: film-ue set --transport ssh --ssh ubuntu@<host> --ssh-key <path>")
    opts = ["-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30",
            "-o", "ConnectTimeout=20"]
    return ["ssh", *(["-i", c["ssh_key"]] if c.get("ssh_key") else []), *opts]


def _ssh(script: str, timeout: int) -> str:
    """bash as root on the box over ssh (the login user has passwordless sudo), the script on stdin."""
    try:
        r = subprocess.run([*_ssh_base(), conf()["ssh"], "sudo", "bash", "-s"], input=script, capture_output=True,
                           text=True, timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        raise SystemExit("workstation command timed out")
    if r.returncode:
        raise SystemExit(f"workstation command failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    return r.stdout


def forward(remote_port: int, local_port: int, log_path: Path | None = None) -> subprocess.Popen:
    """A local port forwarded to the box's 127.0.0.1:remote_port (no inbound port on the box): ssh -L or SSM."""
    c = conf()
    out = open(log_path, "w") if log_path else subprocess.DEVNULL
    if over_ssh():
        cmd = [*_ssh_base(), "-N", "-o", "ExitOnForwardFailure=yes", "-L", f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}",
               c["ssh"]]
    else:
        if not shutil.which("session-manager-plugin"):
            raise SystemExit("the AWS Session Manager plugin is needed: https://docs.aws.amazon.com/systems-manager/latest/"
                             "userguide/session-manager-working-with-install-plugin.html")
        cmd = ["aws", "ssm", "start-session", "--region", c["region"], "--target", c["instance"],
               "--document-name", "AWS-StartPortForwardingSession", "--parameters",
               json.dumps({"portNumber": [str(remote_port)], "localPortNumber": [str(local_port)]})]
    return subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)


def rjoin(*parts: str) -> str:
    """A path on the workstation, joined in its own style."""
    return str((PurePosixPath if linux() else PureWindowsPath)(*parts))


def project(*parts: str) -> str:
    """A path inside the project on the workstation: project("Saved", "Stills", "a.png")."""
    pd = conf()["project_dir"]
    if not pd:
        raise SystemExit("no project dir set: film-ue set --project-dir /srv/ue/projects/<Name>")
    return rjoin(pd, *parts)


def aws(*args, check: bool = True) -> dict | str:
    c = conf()
    r = subprocess.run(["aws", *args, "--region", c["region"], "--output", "json"], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"aws {' '.join(args[:2])}: {r.stderr.strip()[-500:]}")
    try:
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except ValueError:
        return r.stdout


def instance() -> dict:
    c = conf()
    if not c["instance"]:
        raise SystemExit("no workstation set: film-ue set --instance i-... (see film-ue --help)")
    return aws("ec2", "describe-instances", "--instance-ids", c["instance"])["Reservations"][0]["Instances"][0]


def state() -> dict:
    if over_ssh():
        return {"ssh": conf()["ssh"], "os": conf()["os"], "uptime": _ssh("uptime", 60).strip()}
    i = instance()
    return {"id": i["InstanceId"], "type": i["InstanceType"], "state": i["State"]["Name"], "ip": i.get("PublicIpAddress"),
            "os": conf()["os"], "launched": i["LaunchTime"]}


def wait_ssm(tries: int = 60) -> bool:
    for _ in range(tries):
        info = aws("ssm", "describe-instance-information", "--filters", f"Key=InstanceIds,Values={conf()['instance']}")
        if info.get("InstanceInformationList") and info["InstanceInformationList"][0]["PingStatus"] == "Online":
            return True
        time.sleep(5)
    return False


def start(wait: bool = True) -> dict:
    if over_ssh():
        return state()  # a box reached over ssh is started and stopped by whoever owns it
    aws("ec2", "start-instances", "--instance-ids", conf()["instance"])
    if wait:
        aws("ec2", "wait", "instance-running", "--instance-ids", conf()["instance"])
        wait_ssm()
    return state()


def stop(wait: bool = False) -> dict:
    if over_ssh():
        return state()
    aws("ec2", "stop-instances", "--instance-ids", conf()["instance"])
    if wait:
        aws("ec2", "wait", "instance-stopped", "--instance-ids", conf()["instance"])
    return state()


def password() -> str:
    c = conf()
    if linux():
        raise SystemExit("a Linux box has no desktop password: everything goes through SSM")
    d = aws("ec2", "get-password-data", "--instance-id", c["instance"], "--priv-launch-key", c["key"])
    return d.get("PasswordData", "")


# ------------------------------------------------------------------------------------------- commands over SSM

def _ssm(document: str, script: str, timeout: int) -> str:
    c = conf()
    params = json.dumps({"commands": [script], "executionTimeout": [str(timeout)]})
    cid = aws("ssm", "send-command", "--instance-ids", c["instance"], "--document-name", document,
              "--parameters", params)["Command"]["CommandId"]
    end = time.time() + timeout + 30
    while time.time() < end:
        time.sleep(2)
        r = aws("ssm", "get-command-invocation", "--command-id", cid, "--instance-id", c["instance"], check=False)
        if isinstance(r, dict) and r.get("Status") in ("Success", "Failed", "TimedOut", "Cancelled"):
            if r["Status"] != "Success":
                raise SystemExit(f"workstation command {r['Status']}: {(r.get('StandardErrorContent', '') or r.get('StandardOutputContent', ''))[-800:]}")
            return r.get("StandardOutputContent", "")
    raise SystemExit("workstation command timed out")


def ps(script: str, timeout: int = 600) -> str:
    """Run PowerShell on a Windows workstation through SSM (as SYSTEM, no desktop) and return its output."""
    return _ssm("AWS-RunPowerShellScript", script, timeout)


def sh(script: str, timeout: int = 600, root: bool = False) -> str:
    """Run bash on a Linux workstation through SSM and return its output: as the editor's user (files it writes are
    the editor's), or as root (`root=True`: packages, systemd)."""
    if not root:
        script = f"runuser -u {shlex.quote(conf()['user'])} -- bash -c {shlex.quote(script)}"
    if over_ssh():
        return _ssh("set -e\n" + script, timeout)
    return _ssm("AWS-RunShellScript", "set -e\n" + script, timeout)


def run(script: str, timeout: int = 600) -> str:
    """Run the box's own shell (PowerShell or bash) as the identity that owns the project."""
    return sh(script, timeout) if linux() else ps(script, timeout)


def put_text(path: str, data: bytes) -> None:
    """Write a file on the workstation through SSM (small files: SSM caps a command near 100 KB)."""
    b64 = base64.b64encode(data).decode()
    if linux():
        q = shlex.quote(path)
        sh(f"mkdir -p $(dirname {q}) && echo {b64} | base64 -d > {q}")
    else:
        ps(f"New-Item -ItemType Directory -Force -Path (Split-Path '{path}') | Out-Null; "
           f"[IO.File]::WriteAllBytes('{path}', [Convert]::FromBase64String('{b64}'))")


def read_text(path: str) -> str:
    """A small text file on the workstation, or "" when it is not there."""
    if linux():
        q = shlex.quote(path)
        return sh(f"if [ -f {q} ]; then cat {q}; fi")
    return ps(f"if (Test-Path '{path}') {{ Get-Content '{path}' -Raw }}")


def editor(action: str) -> str:
    """The editor's systemd unit on a Linux box: start, stop, restart, status, enable."""
    if not linux():
        raise SystemExit("on Windows the editor starts with the desktop session (DCV login), not from here")
    svc = shlex.quote(conf()["service"])
    if action == "status":
        return sh(f"systemctl is-active {svc} || true", root=True).strip()
    return sh(f"systemctl {action} {svc}", root=True)


# ------------------------------------------------------------------------------------------- big folders via S3

def _bucket() -> str:
    b = conf().get("bucket")
    if not b:
        raise SystemExit("no bucket set: film-ue set --bucket NAME (one the workstation's role can read and write)")
    return b


def _rsync(src: str, dst: str) -> None:
    c = conf()
    ssh = " ".join(shlex.quote(x) for x in _ssh_base())
    subprocess.run(["rsync", "-a", "--mkpath", "-e", ssh, f"--rsync-path=sudo -u {c['user']} rsync", src, dst], check=True)


def push_dir(local_dir: str, remote_dir: str) -> int:
    """Send a whole folder (textures, meshes) to the workstation through S3, far faster than the tunnel: this machine
    syncs it up, the workstation downloads it into `remote_dir`, the bucket copy is deleted (over ssh: rsync).
    Returns files sent."""
    if over_ssh():
        _rsync(local_dir.rstrip("/") + "/", f"{conf()['ssh']}:{remote_dir.rstrip('/')}/")
        return sum(1 for f in Path(local_dir).rglob("*") if f.is_file())
    c, bucket = conf(), _bucket()
    prefix = "film-ue/up-" + Path(local_dir).name + f"-{int(time.time())}"
    s3 = f"s3://{bucket}/{prefix}"
    subprocess.run(["aws", "s3", "sync", "--only-show-errors", local_dir, s3, "--region", c["region"]], check=True)
    if linux():
        sh(f"mkdir -p {shlex.quote(remote_dir)} && aws s3 sync --only-show-errors {s3} {shlex.quote(remote_dir)} "
           f"--region {c['region']}", timeout=1800)
    else:
        ps(f"New-Item -ItemType Directory -Force -Path '{remote_dir}' | Out-Null; "
           f"Read-S3Object -BucketName {bucket} -KeyPrefix {prefix} -Folder '{remote_dir}' -Region {c['region']} | Out-Null",
           timeout=1800)
    subprocess.run(["aws", "s3", "rm", "--only-show-errors", "--recursive", s3, "--region", c["region"]], check=True)
    return sum(1 for f in Path(local_dir).rglob("*") if f.is_file())


def pull_dir(remote_dir: str, local_dir: str) -> int:
    """Bring a whole folder back (a render's frames) through S3, far faster than the tunnel: the workstation uploads
    it to the bucket in settings (`bucket`), this machine syncs it down, the bucket copy is deleted (over ssh: rsync).
    Returns files."""
    if over_ssh():
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        _rsync(f"{conf()['ssh']}:{remote_dir.rstrip('/')}/", local_dir.rstrip("/") + "/")
        return sum(1 for _ in Path(local_dir).iterdir())
    c, bucket = conf(), _bucket()
    prefix = "film-ue/" + Path(remote_dir.replace("\\", "/")).name + f"-{int(time.time())}"
    s3 = f"s3://{bucket}/{prefix}"
    if linux():
        sh(f"aws s3 sync --only-show-errors {shlex.quote(remote_dir)} {s3} --region {c['region']}", timeout=1800)
    else:
        ps(f"Write-S3Object -BucketName {bucket} -KeyPrefix {prefix} -Folder '{remote_dir}' -Recurse -Region {c['region']}",
           timeout=1800)
    Path(local_dir).mkdir(parents=True, exist_ok=True)
    subprocess.run(["aws", "s3", "sync", "--only-show-errors", s3, local_dir, "--region", c["region"]], check=True)
    subprocess.run(["aws", "s3", "rm", "--only-show-errors", "--recursive", s3, "--region", c["region"]], check=True)
    return sum(1 for _ in Path(local_dir).iterdir())
