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
KIT_FILES = ("setup.sh", "ue-editor.sh", "ue-editor.service", "ue-epic.sh", "ue_watchdog.py", "ue-watchdog.service",
             "ue-watchdog.timer")


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


def build_plugin(name: str, timeout: int = 1800) -> str:
    """Build unreal/plugins/<name> (a C++ editor plugin, e.g. FabScript) on the box against its engine and install it
    in the project (setup.sh plugin). The editor loads it on its next restart (film-ue editor restart)."""
    import base64
    import io
    import tarfile
    src = KIT_SRC.parent / "plugins" / name
    if not (src / f"{name}.uplugin").is_file():
        raise SystemExit(f"no plugin {name} in {src.parent}")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        t.add(src, arcname=name, filter=lambda i: None if "/Binaries" in i.name or "/Intermediate" in i.name else i)
    kit = upload_kit()
    ws.put_text(f"{kit}/plugin-{name}.tgz", buf.getvalue())
    engine = ws.conf().get("engine_dir") or "/srv/ue/engine"
    return step("plugin", f"{kit}/plugin-{name}.tgz", engine, ws.conf()["project_dir"], timeout=timeout).strip()


def reboot() -> None:
    if ws.over_ssh():
        try:
            ws.sh("systemctl reboot", 60, root=True)
        except SystemExit:
            pass  # the connection drops as it goes down
        time.sleep(45)
        for _ in range(60):
            try:
                ws.sh("true", 30, root=True)
                return
            except SystemExit:
                time.sleep(10)
        raise SystemExit("the box did not come back on ssh after the reboot")
    ws.aws("ec2", "reboot-instances", "--instance-ids", ws.conf()["instance"])
    time.sleep(45)  # the agent still answers for a moment while the box goes down
    if not ws.wait_ssm(120):
        raise SystemExit("the box did not come back on SSM after the reboot")


def check() -> dict:
    out = step("check", timeout=120)
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


WINDISK = "/mnt/win"


def provision(engine_s3: str, version: str, project_src: str, project_name: str, level: str = "",
              mount: str = "/srv/ue", driver: str = "580-server", epic_s3: str = "", log=print) -> dict:
    """Everything a fresh Ubuntu 22.04 GPU box needs to run the editor under systemd. `project_src`: an s3:// prefix,
    or win:<path on the Windows disk> (e.g. win:UEProjects/Name; the disk is mounted read-only at /mnt/win and stays
    there, so its Saved/ renders can serve as references). `epic_s3` (default: the box's `epic_s3` setting): where
    the Epic sign-in is kept; it is restored before the editor first starts. Saves `project_dir` for the box."""
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
    log(step("rhi", project_dir, timeout=120).strip())  # Vulkan SM6: the DDC in S3 is VULKAN_SM6
    epic_s3 = epic_s3 or ws.conf().get("epic_s3", "")
    log(step("service", engine, f"{project_dir}/{project_name}.uproject", level, epic_s3, timeout=600).strip())
    ws.save(project_dir=project_dir)
    return check()


def _sign_ins() -> int:
    out = step("epic", "status", timeout=120)
    return int(next((x.split("=", 1)[1] for x in out.split() if x.startswith("sign_ins=")), "0") or 0)


def exchange_code(cmd: str) -> str:
    """Run the operator's own helper that prints a fresh Epic exchange code (it holds the refresh token; film-ue
    never does) and return the code. Nothing of it is printed or logged here."""
    import subprocess
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    code = (r.stdout or "").strip().splitlines()[-1].strip() if r.stdout.strip() else ""
    if r.returncode or not code.isalnum():
        raise SystemExit(f"the exchange-code helper failed (exit {r.returncode}); it must print one code on its "
                         "last line (stderr is not shown: it may hold secrets)")
    return code


def epic_login(fab: bool = False, wait_minutes: float = 10, log=print, exchange_code_cmd: str = "") -> str:
    """Make sure the box's editor is signed in to Epic. The MetaHuman cloud services and Fab are separate Epic clients
    with a sign-in each (`fab`: Fab's). Signed in already (a saved sign-in, restored from S3 at start): nothing to do
    for MetaHuman; Fab is always asked (it says itself whether a saved sign-in still works). Otherwise the editor
    starts Epic's device sign-in, and this prints only its code: a person opens https://www.epicgames.com/activate
    anywhere, signs in and enters it. The sign-in is then saved to S3 (and again whenever the editor stops). Never
    sign out in the editor (Fab.Logout, Fab.SetEnvironment): that deletes the saved sign-in."""
    from . import client
    before = _sign_ins()
    if not fab and before:
        return "signed in"
    if exchange_code_cmd:  # no person needed: the MetaHuman services sign in with a single-use code (§12c)
        if fab:
            raise SystemExit("Fab reads an exchange code only from the editor's command line when its tab opens (a "
                             "desktop): use film-ue epic-login --fab (device code) instead")
        r = client.op("editor.epic_exchange_code", code=exchange_code(exchange_code_cmd), timeout=60)
        if not r.get("ok"):
            raise SystemExit(f"editor.epic_exchange_code: {r.get('message') or r.get('error', r)}")
        seen = client.log(2000).count("Login complete: EOS_Success")
        client.op("mh.login", timeout=300)
        end = time.time() + 120
        while time.time() < end:
            time.sleep(5)
            if _sign_ins() > before:
                log(step("epic", "save", timeout=300).strip())
                return "signed in (exchange code), and the sign-in is saved"
            if client.log(2000).count("Login complete: EOS_Success") > seen:
                return ("signed in for this editor session (exchange code); no saved sign-in appeared, so the next "
                        "start needs a new code")
        raise SystemExit("the exchange code did not sign in (expired? used?): film-ue editor log 200 | grep EOSAuth")
    step("epic", "clear-code", timeout=60)
    if fab:
        r = client.exec_code('import unreal\nunreal.SystemLibrary.execute_console_command(None, "Fab.Login")\n'
                             'result = True', timeout=60)
    else:
        r = client.op("mh.login", timeout=300)
    if not r.get("ok"):
        raise SystemExit(f"sign-in request: {r.get('error', r)}")
    if r.get("result") == {"signed_in": True}:
        return "signed in"
    code, end = "", time.time() + 120
    while not code and time.time() < end:
        time.sleep(5)
        code = next((x.split("=", 1)[1] for x in step("epic", "code", timeout=60).split() if x.startswith("code=")), "")
    if not code:
        if fab and before:
            return "no new sign-in asked for: Fab used the saved one (see LogFab in film-ue editor log 200)"
        raise SystemExit("no sign-in started: see the editor log (film-ue editor log 200, LogEOSAuth)")
    log(f"open https://www.epicgames.com/activate, sign in to Epic and enter the code {code}")
    end = time.time() + wait_minutes * 60
    while time.time() < end:
        time.sleep(10)
        if _sign_ins() > before:
            step("epic", "clear-code", timeout=60)
            log(step("epic", "save", timeout=300).strip())
            return "signed in"
    raise SystemExit(f"not signed in after {wait_minutes:.0f} min: run film-ue epic-login again for a new code")


def desktop(on: bool, local_port: int = 5901) -> str:
    """The temporary desktop for one interactive step (a sign-in): on = Xorg on the GPU + VNC on the box's 127.0.0.1
    + the editor restarted onto it, and a port-forward to it here (SSM or ssh); off = all of that gone, the editor offscreen."""
    import json
    import os
    import signal
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
    step("desktop", "on", timeout=1800)
    p = ws.forward(5900, local_port)
    fwd.write_text(json.dumps({"pid": p.pid, "port": local_port}))
    return (f"desktop on. Open vnc://localhost:{local_port} (macOS: Finder > Go > Connect to Server); the password is "
            "in /root/vnc-pass on the box (read it in your own session: sudo cat). When done: film-ue desktop off")
