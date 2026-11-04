"""The client: reach the bridge in the box's editor and call it: exec, op, jobs, gui, screen, files, log, health.

How the bridge is reached (the box's `transport` and `bridge` settings, filmtools.unreal.workstation):
  tunnel   a local port forwarded to the box's 127.0.0.1 bridge port (SSM port-forward, or ssh -L), opened on demand
           and reopened when it dies; the token is read once from the box and refreshed after an editor restart
  ssm      no tunnel: each call is one SSM command that runs curl on the box (no Session Manager plugin needed)
  local    the editor runs here: straight to 127.0.0.1:<port>

Long calls survive a dropped connection: `op()` and `exec_code()` start a job (async) and poll it; a poll that fails
to connect (a tunnel restart, a network blip, the bridge being reloaded) is retried until the deadline, and the
job's result is still there afterwards (the bridge keeps finished jobs for 24 h, across reloads). In bridge=ssm mode
each poll would be one SSM command, so a call there waits in one request instead.

    job = client.submit("render.mrq", sequence=..., level=...)       # its id, at once
    client.wait(job, timeout=3600, on_progress=print)                # {"ok", "result", ...} when done
    client.job(job) / client.jobs(state="running") / client.cancel(job)
"""
from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import workstation as ws

RETRY_ERRORS = (urllib.error.URLError, ConnectionError, http.client.HTTPException, socket.timeout, TimeoutError)


class BridgeDown(SystemExit):
    """The bridge did not answer (no connection, or the editor is not up): actionable, and a SystemExit so the CLI
    prints it plainly."""


def _tunnel_file() -> Path:  # per box (FILM_UE_BOX), beside its settings
    return ws.state_path("tunnel.json")


def _token_file() -> Path:
    return ws.state_path("token")


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _mode() -> str:
    c = ws.conf()
    if c.get("transport") == "local":
        return "local"
    return "ssm" if c.get("bridge") == "ssm" else "tunnel"


def tunnel(local: int | None = None) -> int:
    """Start (or reuse) the port-forward to the bridge (SSM, or ssh -L); returns the local port. A local box needs
    none: its bridge port is returned."""
    c = ws.conf()
    if _mode() == "local":
        return int(c["port"])
    local = local or c["local_port"]
    if _port_open(local):
        return local
    close_tunnel()  # a recorded tunnel whose port no longer answers is dead: clear it before starting another
    p = ws.forward(c["port"], local, ws.state_path("tunnel.log"))
    _tunnel_file().write_text(json.dumps({"pid": p.pid, "port": local, "started": time.time()}))
    for _ in range(60):
        if _port_open(local):
            return local
        if p.poll() is not None:
            raise BridgeDown("the tunnel exited: " + ws.state_path("tunnel.log").read_text()[-500:])
        time.sleep(0.5)
    raise BridgeDown("the tunnel did not open in 30 s (film-ue status; is the box running?)")


def close_tunnel() -> None:
    if _tunnel_file().exists():
        try:
            os.killpg(json.loads(_tunnel_file().read_text())["pid"], signal.SIGTERM)
        except (ProcessLookupError, PermissionError, KeyError, ValueError):
            pass
        _tunnel_file().unlink(missing_ok=True)


def token(refresh: bool = False) -> str:
    if _mode() == "local":
        p = Path(ws.project("Saved", "fmbridge.token"))
        if not p.exists():
            raise BridgeDown(f"no bridge token at {p}: is the editor running with the bridge? (film-ue editor status)")
        return p.read_text().strip()
    if _token_file().exists() and not refresh:
        return _token_file().read_text().strip()
    t = ws.read_text(ws.project("Saved", "fmbridge.token")).strip()
    if not t:
        raise BridgeDown("no bridge token on the workstation yet: is the editor running? (film-ue editor status)")
    _token_file().write_text(t)
    _token_file().chmod(0o600)
    return t


def _http(method: str, path: str, data: bytes | None, timeout: float) -> bytes:
    """One HTTP call through the tunnel (or locally); a 401 refreshes the token once (the editor restarted)."""
    port = tunnel()
    for attempt in (0, 1):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                     headers={"X-FM-Token": token(refresh=attempt == 1), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 0:
                continue
            body = e.read()[:2000]
            if e.code == 404 and path.startswith("/job?"):
                raise JobGone(body.decode("utf-8", "replace"))
            raise SystemExit(f"bridge {path.split('?')[0]}: HTTP {e.code} {body[:300]!r}")
    raise SystemExit("bridge: unauthorised (the token on the box changed twice: film-ue health)")


class JobGone(SystemExit):
    """The bridge does not know this job: it was never there, or the editor restarted (crashed?) while it ran."""


def request(method: str, path: str, body: bytes | dict | None = None, timeout: float = 900, retry_s: float = 0) -> bytes:
    """A raw bridge call. `retry_s`: keep retrying a failed connection that long (only for calls that are safe to
    repeat: reads, polls)."""
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    if _mode() == "ssm":
        return _request_on_box(method, path, data, timeout)
    end = time.time() + retry_s
    delay = 0.5
    while True:
        try:
            return _http(method, path, data, timeout)
        except RETRY_ERRORS as e:
            if time.time() >= end:
                raise BridgeDown(f"bridge {path.split('?')[0]}: no answer ({e}); is the editor up? "
                                 "film-ue health / film-ue editor status / film-ue editor log") from None
            if isinstance(e, (urllib.error.URLError, ConnectionError)) and _mode() == "tunnel" \
                    and not _port_open(ws.conf()["local_port"]):
                close_tunnel()  # the next _http reopens it
            time.sleep(delay)
            delay = min(delay * 2, 10)


SMALL = 15000  # bytes of answer that come back in the command's own output (SSM keeps ~24,000 characters of it)


def _request_on_box(method: str, path: str, data: bytes | None, timeout: float) -> bytes:
    """The same call with no tunnel (no Session Manager plugin here): one SSM command runs curl against the bridge
    on the box's own 127.0.0.1, reading the token there. A big answer comes back through the S3 bucket."""
    import base64
    import shlex
    import subprocess
    import tempfile
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
        with tempfile.NamedTemporaryFile() as f:
            subprocess.run(["aws", "s3", "cp", "--only-show-errors", s3, f.name, "--region", c["region"]], check=True)
            subprocess.run(["aws", "s3", "rm", "--only-show-errors", s3, "--region", c["region"]], check=True)
            payload = Path(f.name).read_bytes()
    else:
        lines = out.splitlines()
        i = lines.index("FMBODY") if "FMBODY" in lines else -1
        payload = base64.b64decode(lines[i + 1]) if 0 <= i < len(lines) - 1 and lines[i + 1] else b""
    if code == "000":
        raise BridgeDown(f"bridge {path}: no answer on the box (is the editor up? film-ue editor status)")
    if code == "404" and path.startswith("/job?"):
        raise JobGone(payload.decode("utf-8", "replace"))
    if code != "200":
        raise SystemExit(f"bridge {path}: HTTP {code} {payload[:300]}")
    return payload


def call(path: str, body: dict, timeout: float = 900) -> dict:
    return json.loads(request("POST", path, body, timeout))


# ------------------------------------------------------------------------------------------------------- jobs
def submit(op_name: str, /, **args) -> str:
    """Start an op as a job and return its id at once."""
    r = call("/op", {"name": op_name, "args": args, "async": True}, 60)
    if not r.get("ok"):
        raise SystemExit(f"{op_name}: not started: {r.get('error', r)}")
    return r["job"]


def submit_exec(code: str, name: str = "exec") -> str:
    """Start a piece of Python as a job (`result = ...` is its result) and return its id."""
    r = call("/exec", {"code": code, "name": name, "async": True}, 60)
    if not r.get("ok"):
        raise SystemExit(f"exec: not started: {r.get('error', r)}")
    return r["job"]


def job(job_id: str, retry_s: float = 30) -> dict:
    """A job's state: {"id", "state", "done", "progress", "message", and when done "ok", "result" | "error", ...}."""
    return json.loads(request("GET", "/job?id=" + urllib.parse.quote(job_id), timeout=60, retry_s=retry_s))


def jobs(state: str = "", name: str = "", limit: int = 50) -> list:
    """Recent jobs, newest first, without their results: state queued|running|done|failed|cancelled|lost."""
    q = urllib.parse.urlencode({k: v for k, v in (("state", state), ("name", name), ("limit", limit)) if v})
    r = json.loads(request("GET", "/jobs?" + q, timeout=60, retry_s=30))
    if "jobs" not in r:  # a bridge from before jobs were listed (protocol 1)
        raise SystemExit("this bridge cannot list jobs: film-ue install (protocol 2)")
    return r["jobs"]


def cancel(job_id: str) -> dict:
    """Cancel a queued job, or a running multi-tick one (it stops at its next step and cleans up)."""
    return call("/job/cancel", {"id": job_id}, 60)


def wait(job_id: str, timeout: float = 900, on_progress=None, poll_s: float = 0.2) -> dict:
    """Poll a job until it has finished (or `timeout` passes) and return its answer, the same dict a synchronous call
    returns. Dropped connections are retried; a job the bridge no longer knows raises JobGone with what to do."""
    end = time.time() + timeout
    seen = None
    delay = min(poll_s, 0.05)
    while True:
        left = end - time.time()
        try:
            j = job(job_id, retry_s=max(5.0, min(left, 120.0)))
        except JobGone:
            raise JobGone(f"job {job_id} is gone: the editor restarted (or crashed) while it ran, before it could be "
                          "recorded. Check film-ue editor crashes / film-ue editor log, then run it again.") from None
        if on_progress and (j.get("progress"), j.get("message")) != seen:
            seen = (j.get("progress"), j.get("message"))
            on_progress(j)
        if j.get("done"):
            return j
        if left <= 0:
            return {"ok": False, "job": job_id, "id": job_id, "state": j.get("state"),
                    "error": f"timeout after {timeout}s (still {j.get('state')} as job {job_id}: film-ue job {job_id})"}
        time.sleep(min(delay, max(0.0, left)))
        delay = min(delay * 1.5, max(poll_s, 1.0))


def _run(path: str, body: dict, timeout: float, wait_for: bool) -> dict:
    if not wait_for:
        return call(path, {**body, "async": True}, 60)
    if _mode() == "ssm":  # one SSM command per poll would be slow: wait inside a single request
        return call(path, {**body, "timeout": timeout}, timeout + 30)
    r = call(path, {**body, "async": True}, 60)
    if not r.get("ok") or "job" not in r:
        return r
    if r.get("done"):  # a protocol-1 bridge may answer synchronously anyway
        return r
    return wait(r["job"], timeout)


def batch(calls: list, timeout: float = 900, wait: bool = True, stop_on_error: bool = True) -> dict:
    """Several ops in one request and one job, in order: [("level.spawn", {...}), ("look.light", {...})] or
    [{"name": ..., "args": {...}}]. Returns {"ok", "ran", "of", "results": [{"ok", "i", "name", "result" | "code",
    "message", "hint", ...}]} as the job's result (stops at the first failure unless stop_on_error=False)."""
    norm = [c if isinstance(c, dict) else {"name": c[0], "args": dict(c[1]) if len(c) > 1 else {}} for c in calls]
    return _run("/batch", {"calls": norm, "stop_on_error": stop_on_error}, timeout, wait)


def exec_code(code: str, timeout: float = 900, wait: bool = True) -> dict:
    return _run("/exec", {"code": code}, timeout, wait)


def op(op_name: str, /, timeout: float = 900, wait: bool = True, **args) -> dict:
    """Call a bridge op; positional-only so an op's own `name` argument passes through. Waits (polling, so a dropped
    connection does not lose it) up to `timeout`, or returns the job id at once with wait=False."""
    return _run("/op", {"name": op_name, "args": args}, timeout, wait)


# -------------------------------------------------------------------------------------------- the rest
def gui(actions: list) -> dict:
    return call("/gui", {"actions": actions}, 300)


def screen(path: str) -> str:
    Path(path).write_bytes(request("GET", "/screen", timeout=120))
    return path


def push(local: str, remote: str) -> dict:
    """A file onto the box through the bridge (small and medium files; folders: workstation.push_dir)."""
    return json.loads(request("PUT", "/file?path=" + urllib.parse.quote(remote), Path(local).read_bytes(), 1800))


def pull(remote: str, local: str) -> str:
    Path(local).parent.mkdir(parents=True, exist_ok=True)
    Path(local).write_bytes(request("GET", "/file?path=" + urllib.parse.quote(remote), timeout=1800, retry_s=30))
    return local


def health(retry_s: float = 0) -> dict:
    """The bridge's /health: engine, platform, project, uptime, jobs, memory, idle cap, last tick."""
    return json.loads(request("GET", "/health", timeout=30, retry_s=retry_s))


def log(lines: int = 200) -> str:
    return json.loads(request("GET", f"/log?lines={int(lines)}", timeout=60, retry_s=10))["log"]
