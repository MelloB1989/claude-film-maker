"""The client: an SSM port-forward to the bridge's 127.0.0.1 port on the workstation (no inbound port is opened), the
bridge token (read once over SSM and cached), and calls: exec, op, gui, screen, files, log, health."""
from __future__ import annotations

import json
import os
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
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    if ws.conf().get("bridge") == "ssm":
        return _request_on_box(method, path, data, timeout)
    port = tunnel()
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


SMALL = 15000  # bytes of answer that come back in the command's own output (SSM keeps ~24,000 characters of it)


def _request_on_box(method: str, path: str, data: bytes | None, timeout: float) -> bytes:
    """The same call with no tunnel (no Session Manager plugin here): one SSM command runs curl against the bridge
    on the box's own 127.0.0.1, reading the token there. A big answer comes back through the S3 bucket."""
    import base64
    import shlex
    import uuid
    c = ws.conf()
    rid = uuid.uuid4().hex[:12]
    req, resp = f"/tmp/fmreq_{rid}", f"/tmp/fmresp_{rid}"
    s3 = f"s3://{c.get('bucket', '')}/film-ue/resp/{rid}"
    put = f"echo {base64.b64encode(data).decode()} | base64 -d > {req}; " if data else ""
    body = f"--data-binary @{req}" if data else ""
    script = (f"{put}code=$(curl -s -o {resp} -w '%{{http_code}}' -X {method} "
              f"-H \"X-FM-Token: $(cat {shlex.quote(ws.project('Saved', 'fmbridge.token'))})\" "
              f"-H 'Content-Type: application/json' {body} --max-time {int(timeout)} "
              f"'http://127.0.0.1:{c['port']}{path}') || true\n"
              f"size=$(stat -c %s {resp} 2>/dev/null || echo 0)\n"
              f"echo FMCODE=$code FMSIZE=$size\n"
              f"if [ \"$size\" -le {SMALL} ]; then echo FMBODY; base64 -w0 {resp} 2>/dev/null; echo; "
              f"else aws s3 cp --only-show-errors {resp} {s3} && echo FMS3; fi\n"
              f"rm -f {req} {resp}")
    out = ws.sh(script, int(timeout) + 60)
    head = next((line for line in out.splitlines() if line.startswith("FMCODE=")), "FMCODE=000 FMSIZE=0")
    code = head.split()[0].split("=", 1)[1]
    if "FMS3" in out:
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile() as f:
            subprocess.run(["aws", "s3", "cp", "--only-show-errors", s3, f.name, "--region", c["region"]], check=True)
            subprocess.run(["aws", "s3", "rm", "--only-show-errors", s3, "--region", c["region"]], check=True)
            payload = Path(f.name).read_bytes()
    else:
        lines = out.splitlines()
        i = lines.index("FMBODY") if "FMBODY" in lines else -1
        payload = base64.b64decode(lines[i + 1]) if 0 <= i < len(lines) - 1 and lines[i + 1] else b""
    if code == "000":
        raise SystemExit(f"bridge {path}: no answer on the box (is the editor up? film-ue editor status)")
    if code != "200":
        raise SystemExit(f"bridge {path}: HTTP {code} {payload[:300]}")
    return payload


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
