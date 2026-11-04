"""Setting up a Linux box for film-ue (no desktop): the data volume, the NVIDIA driver, the engine from S3, the project
(from S3, or from a Windows workstation's disk: an EBS volume made from its snapshot, mounted read-only) and the
editor's systemd unit, by running unreal/linux/setup.sh over SSM. Each step is idempotent, so
`provision` can be rerun after any failure; it reboots once if the driver asks for it."""
from __future__ import annotations

import shlex
import time
from pathlib import Path

from . import workstation as ws

KIT_SRC = Path(__file__).resolve().parents[3] / "unreal" / "linux"
KIT_FILES = ("setup.sh", "ue-editor.sh", "ue-editor.service")


def kit_dir() -> str:
    return f"/home/{ws.conf()['user']}/.film-ue/linux"


def upload_kit() -> str:
    for f in KIT_FILES:
        ws.put_text(f"{kit_dir()}/{f}", (KIT_SRC / f).read_bytes())
    return kit_dir()


def step(name: str, *args: str, timeout: int = 1800) -> str:
    """Run one setup.sh step as root; returns its output."""
    a = " ".join(shlex.quote(str(x)) for x in args)
    return ws.sh(f"UE_USER={shlex.quote(ws.conf()['user'])} bash {kit_dir()}/setup.sh {name} {a}", timeout, root=True)


def reboot() -> None:
    ws.aws("ec2", "reboot-instances", "--instance-ids", ws.conf()["instance"])
    time.sleep(45)  # the agent still answers for a moment while the box goes down
    if not ws.wait_ssm(120):
        raise SystemExit("the box did not come back on SSM after the reboot")


def check() -> dict:
    out = step("check", timeout=120)
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


WINDISK = "/mnt/win"


def provision(engine_s3: str, version: str, project_src: str, project_name: str, level: str = "",
              mount: str = "/srv/ue", driver: str = "580-server", log=print) -> dict:
    """Everything a fresh Ubuntu 22.04 GPU box needs to run the editor under systemd. `project_src`: an s3:// prefix,
    or win:<path on the Windows disk> (e.g. win:UEProjects/Name; the disk is mounted read-only at /mnt/win and stays
    there, so its Saved/ renders can serve as references). Saves `project_dir` for the box."""
    log("kit: " + upload_kit())
    log(step("volume", mount, timeout=300).strip())
    out = step("driver", driver, timeout=1800)
    log(out.strip())
    if "reboot=needed" in out:
        log("rebooting for the driver ...")
        reboot()
        log(step("driver", driver, timeout=600).strip())
    engine = f"{mount}/engine"
    log(step("engine", engine_s3, version, engine, timeout=3600).strip())
    project_dir = f"{mount}/projects/{project_name}"
    if project_src.startswith("win:"):
        log(step("windisk", WINDISK, timeout=300).strip())
        log(step("project-copy", f"{WINDISK}/{project_src[4:].strip('/')}", project_dir, timeout=3600).strip())
    else:
        log(step("project", project_src, project_dir, timeout=3600).strip())
    log(step("service", engine, f"{project_dir}/{project_name}.uproject", level, timeout=300).strip())
    ws.save(project_dir=project_dir)
    return check()


def desktop(on: bool, local_port: int = 5901) -> str:
    """The temporary desktop for one interactive step (a sign-in): on = Xorg on the GPU + VNC on the box's 127.0.0.1
    + the editor restarted onto it, and an SSM port-forward to it here; off = all of that gone, the editor offscreen."""
    import json
    import os
    import signal
    import subprocess
    fwd = ws.state_path("vnc.json")
    if not on:
        if fwd.exists():
            try:
                os.killpg(json.loads(fwd.read_text())["pid"], signal.SIGTERM)
            except (ProcessLookupError, PermissionError, KeyError):
                pass
            fwd.unlink()
        upload_kit()
        return step("desktop", "off", timeout=300).strip()
    upload_kit()
    out = step("desktop", "on", timeout=1800)
    pw = next((line.split("=", 1)[1] for line in out.splitlines() if line.startswith("vnc_password=")), "")
    c = ws.conf()
    p = subprocess.Popen(["aws", "ssm", "start-session", "--region", c["region"], "--target", c["instance"],
                          "--document-name", "AWS-StartPortForwardingSession", "--parameters",
                          json.dumps({"portNumber": ["5900"], "localPortNumber": [str(local_port)]})],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    fwd.write_text(json.dumps({"pid": p.pid, "port": local_port}))
    return (f"desktop on. Open vnc://localhost:{local_port} (macOS: Finder > Go > Connect to Server), "
            f"password {pw}. When done: film-ue desktop off")
