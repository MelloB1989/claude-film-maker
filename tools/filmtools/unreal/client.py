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

def _tunnel_file() -> Path:  # per box (FILM_UE_BOX), beside its settings
    return ws.state_path("tunnel.json")


def _token_file() -> Path:
    return ws.state_path("token")


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def tunnel(local: int | None = None) -> int:
    """Start (or reuse) the port-forward to the bridge (SSM, or ssh -L); returns the local port."""
    c = ws.conf()
    local = local or c["local_port"]
    if _port_open(local):
        return local
    p = ws.forward(c["port"], local, ws.state_path("tunnel.log"))
    _tunnel_file().write_text(json.dumps({"pid": p.pid, "port": local}))
    for _ in range(60):
        if _port_open(local):
            return local
        if p.poll() is not None:
            raise SystemExit("the tunnel exited: " + ws.state_path("tunnel.log").read_text()[-500:])
        time.sleep(0.5)
    raise SystemExit("the tunnel did not open in 30 s")


def close_tunnel() -> None:
    if _tunnel_file().exists():
        try:
            os.killpg(json.loads(_tunnel_file().read_text())["pid"], signal.SIGTERM)
        except (ProcessLookupError, PermissionError, KeyError):
            pass
        _tunnel_file().unlink()


def token(refresh: bool = False) -> str:
    if _token_file().exists() and not refresh:
        return _token_file().read_text().strip()
    t = ws.read_text(ws.project("Saved", "fmbridge.token")).strip()
    if not t:
        raise SystemExit("no bridge token on the workstation yet: is the editor running? (film-ue editor status)")
    _token_file().write_text(t)
    _token_file().chmod(0o600)
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
