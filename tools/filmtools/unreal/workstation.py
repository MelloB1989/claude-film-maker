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

How commands and files reach the box is filmtools.unreal.transport (ssm, ssh or local, by the `transport` setting):
the functions here keep their names and signatures for the code that already calls them.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path

CONF_DIR = Path(os.environ.get("FILM_UE_CONF_DIR") or Path.home() / ".config")  # settings, tokens, tunnel state
DEFAULTS = {"region": "ap-south-1", "instance": "", "os": "windows", "project_dir": r"C:\UEProjects\HostStudio",
            "port": 18765, "key": str(Path.home() / ".ssh" / "ue-workstation.pem")}
LINUX_DEFAULTS = {"project_dir": "", "user": "ubuntu", "service": "ue-editor", "transport": "ssm"}


def box() -> str:
    """The current box profile: FILM_UE_BOX (or --box), else the one `film-ue profile use` chose, else "" (the
    default profile, film-ue.json)."""
    env = os.environ.get("FILM_UE_BOX")
    if env is not None:
        return "" if env == "default" else env
    f = CONF_DIR / "film-ue.current"
    try:
        return f.read_text().strip() if f.exists() else ""
    except OSError:
        return ""


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


def local() -> bool:
    return conf().get("transport") == "local"


def transport():
    """The current box's transport (filmtools.unreal.transport): SSM commands go through `_ssm` here, which tests
    replace."""
    from . import transport as t
    c = conf()
    if (c.get("transport") or "ssm") == "ssm":
        return t.SSM(c, ssm=lambda document, script, timeout: _ssm(document, script, timeout))
    return t.get(c)


def forward(remote_port: int, local_port: int, log_path: Path | None = None):
    """A local port forwarded to the box's 127.0.0.1:remote_port (no inbound port on the box): SSM or ssh -L; None
    for a local box."""
    return transport().forward(remote_port, local_port, log_path)


def rjoin(*parts: str) -> str:
    """A path on the workstation, joined in its own style (boxpaths.BoxPaths.join)."""
    from .boxpaths import BoxPaths
    return BoxPaths("linux" if linux() else "windows", "").join(*parts)


def project(*parts: str) -> str:
    """A path inside the project on the workstation: project("Saved", "Stills", "a.png"). Named locations (renders,
    token, bridge in/out, ...) are on boxpaths.BoxPaths.current()."""
    from .boxpaths import BoxPaths
    return BoxPaths.current().project(*parts)


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
    if over_ssh() or local():
        up = transport().run("uptime" if linux() else "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime", 60, root=True)
        return {**transport().describe(), "uptime": up.strip()}
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
    if over_ssh() or local():
        return state()  # a box reached over ssh (or this machine) is started and stopped by whoever owns it
    aws("ec2", "start-instances", "--instance-ids", conf()["instance"])
    if wait:
        aws("ec2", "wait", "instance-running", "--instance-ids", conf()["instance"])
        wait_ssm()
    return state()


def stop(wait: bool = False) -> dict:
    if over_ssh() or local():
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
    from . import transport as t
    return t.ssm_cmd(conf(), document, script, timeout, aws=aws)


def ps(script: str, timeout: int = 600) -> str:
    """Run PowerShell on a Windows workstation (SSM: as SYSTEM, no desktop) and return its output."""
    return transport().run(script, timeout)


def sh(script: str, timeout: int = 600, root: bool = False) -> str:
    """Run bash on a Linux workstation and return its output: as the editor's user (files it writes are the
    editor's), or as root (`root=True`: packages, systemd)."""
    return transport().run(script, timeout, root=root)


def run(script: str, timeout: int = 600) -> str:
    """Run the box's own shell (PowerShell or bash) as the identity that owns the project."""
    return sh(script, timeout) if linux() else ps(script, timeout)


def put_text(path: str, data: bytes) -> None:
    """Write a small file on the workstation (through the command channel: SSM caps a command near 100 KB)."""
    transport().put(path, data)


def read_text(path: str) -> str:
    """A small text file on the workstation, or "" when it is not there."""
    data = transport().get(path)
    return data.decode("utf-8", "replace") if data else ""


def editor(action: str) -> str:
    """The editor's systemd unit on a Linux box: start, stop, restart, status, enable."""
    if not linux():
        raise SystemExit("on Windows the editor starts with the desktop session (DCV login), not from here")
    svc = shlex.quote(conf()["service"])
    if action == "status":
        return sh(f"systemctl is-active {svc} || true", root=True).strip()
    return sh(f"systemctl {action} {svc}", root=True)


# ------------------------------------------------------------------------------------------- big folders
def push_dir(local_dir: str, remote_dir: str) -> int:
    """Send a whole folder (textures, meshes) to the workstation: through the box's S3 bucket (SSM), rsync/scp (ssh)
    or a copy (local); far faster than the bridge. Returns files sent."""
    return transport().push_dir(local_dir, remote_dir)


def pull_dir(remote_dir: str, local_dir: str) -> int:
    """Bring a whole folder back (a render's frames), the same ways as push_dir. Returns files."""
    return transport().pull_dir(remote_dir, local_dir)
