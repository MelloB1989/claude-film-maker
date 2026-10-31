"""The client: an SSM port-forward to the bridge's 127.0.0.1 port on the workstation (no inbound port is opened), the
bridge token (read once over SSM and cached), and calls: exec, op, gui, screen, files, log, health."""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import workstation as ws

STATE = Path.home() / ".config" / "film-ue.tunnel.json"
TOKEN = Path.home() / ".config" / "film-ue.token"


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def tunnel(local: int | None = None) -> int:
    """Start (or reuse) the SSM port-forward to the bridge; returns the local port."""
    c = ws.conf()
    local = local or c["port"]
    if _port_open(local):
        return local
    if not shutil.which("session-manager-plugin"):
        raise SystemExit("the AWS Session Manager plugin is needed: https://docs.aws.amazon.com/systems-manager/latest/"
                         "userguide/session-manager-working-with-install-plugin.html")
    log = open(Path.home() / ".config" / "film-ue.tunnel.log", "w")
    p = subprocess.Popen(["aws", "ssm", "start-session", "--region", c["region"], "--target", c["instance"],
                          "--document-name", "AWS-StartPortForwardingSession", "--parameters",
                          json.dumps({"portNumber": [str(c["port"])], "localPortNumber": [str(local)]})],
                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    STATE.write_text(json.dumps({"pid": p.pid, "port": local}))
    for _ in range(60):
        if _port_open(local):
            return local
        if p.poll() is not None:
            raise SystemExit("the tunnel exited: " + (Path.home() / ".config" / "film-ue.tunnel.log").read_text()[-500:])
        time.sleep(0.5)
    raise SystemExit("the tunnel did not open in 30 s")


def close_tunnel() -> None:
    if STATE.exists():
        try:
            os.killpg(json.loads(STATE.read_text())["pid"], signal.SIGTERM)
        except (ProcessLookupError, PermissionError, KeyError):
            pass
        STATE.unlink()


def token(refresh: bool = False) -> str:
    if TOKEN.exists() and not refresh:
        return TOKEN.read_text().strip()
    t = ws.ps(f"Get-Content '{ws.conf()['project_dir']}\\Saved\\fmbridge.token' -Raw").strip()
    TOKEN.write_text(t)
    TOKEN.chmod(0o600)
    return t


def request(method: str, path: str, body: bytes | dict | None = None, timeout: float = 900) -> bytes:
    port = tunnel()
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    for attempt in (0, 1):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                     headers={"X-FM-Token": token(refresh=attempt == 1), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 0:
                continue  # the editor restarted: a new token
            raise SystemExit(f"bridge {path}: HTTP {e.code} {e.read()[:300]}")
    raise SystemExit("bridge: unauthorised")


def call(path: str, body: dict, timeout: float = 900) -> dict:
    return json.loads(request("POST", path, body, timeout))


def exec_code(code: str, timeout: float = 900, wait: bool = True) -> dict:
    return call("/exec", {"code": code, "timeout": timeout, "async": not wait}, timeout + 30)


def op(op_name: str, /, timeout: float = 900, wait: bool = True, **args) -> dict:
    """Call a bridge op; positional-only so an op's own `name` argument passes through."""
    return call("/op", {"name": op_name, "args": args, "timeout": timeout, "async": not wait}, timeout + 30)


def gui(actions: list) -> dict:
    return call("/gui", {"actions": actions}, 300)


def screen(path: str) -> str:
    Path(path).write_bytes(request("GET", "/screen", timeout=120))
    return path


def push(local: str, remote: str) -> dict:
    import urllib.parse
    return json.loads(request("PUT", "/file?path=" + urllib.parse.quote(remote), Path(local).read_bytes(), 1800))


def pull(remote: str, local: str) -> str:
    import urllib.parse
    Path(local).parent.mkdir(parents=True, exist_ok=True)
    Path(local).write_bytes(request("GET", "/file?path=" + urllib.parse.quote(remote), timeout=1800))
    return local


def health() -> dict:
    return json.loads(request("GET", "/health", timeout=30))
