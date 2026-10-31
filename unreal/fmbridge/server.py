"""The bridge's endpoint inside the Unreal editor: a small HTTP server on 127.0.0.1 (never a public interface), reached
from the operator's machine through an SSM port-forwarding tunnel (tools/filmtools/unreal). Every request carries the
token written to Saved/fmbridge.token at start.

Editor work runs on the game thread (the `unreal` API may not be touched anywhere else): the HTTP thread queues it
and a Slate post-tick callback runs it, so any `unreal` call is safe. Desktop input and screen grabs (fmbridge.gui) run on the HTTP thread instead, so the editor keeps pumping
messages while a click lands.

    POST /exec   {"code": str, "timeout": s, "async": bool}  run Python; `result` in its namespace is returned
    POST /op     {"name": "mh.build", "args": {...}}           call a registered op (fmbridge.ops), same options

A job whose result is a generator runs across editor ticks: each `yield` lets the editor tick once (so a scrubbed
sequence, an animation or a rig settles), `yield 0.5` waits that many seconds; its return value is the result.
    GET  /job?id=                                             an async job's state and result
    POST /gui    {"actions": [...]}                           desktop input (fmbridge.gui.run)
    GET  /screen                                              the desktop as PNG
    GET  /file?path=   PUT /file?path=                         read or write any file (bytes)
    GET  /log?lines=N                                         the editor log's tail
    GET  /health                                              engine version, project, uptime
"""
from __future__ import annotations

import http.server
import inspect
import io
import json
import os
import queue
import secrets
import socketserver
import sys
import threading
import time
import traceback
import urllib.parse
import uuid

import unreal

PORT = int(os.environ.get("FMBRIDGE_PORT", "18765"))
TOKEN_PATH = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "fmbridge.token")

_work: "queue.Queue[tuple]" = queue.Queue()
_jobs: dict[str, dict] = {}
_active: list = []  # multi-tick jobs: [generator, box, stdout buffer, wake time, start time]
_state = {"server": None, "tick": None, "started": time.time(), "token": None}


def _namespace() -> dict:
    from . import ops  # noqa: F401 (registers every op module)
    import fmbridge
    return {"unreal": unreal, "fmbridge": fmbridge, "ops": fmbridge.ops, "__name__": "__fmbridge__", "result": None}


def _run(kind: str, payload: dict) -> dict:
    """On the game thread: run code or an op, capturing stdout/stderr."""
    out, saved = io.StringIO(), (sys.stdout, sys.stderr)
    sys.stdout = sys.stderr = out
    t0 = time.time()
    try:
        if kind == "exec":
            ns = _namespace()
            exec(compile(payload["code"], payload.get("name", "<bridge>"), "exec"), ns)
            res = ns.get("result")
        else:
            from . import ops
            res = ops.call(payload["name"], **(payload.get("args") or {}))
        if inspect.isgenerator(res):  # a multi-tick job: _tick steps it
            return {"gen": res, "buf": out, "t0": t0}
        return {"ok": True, "result": _jsonable(res), "stdout": out.getvalue(), "ms": int((time.time() - t0) * 1000)}
    except Exception:
        return {"ok": False, "error": traceback.format_exc(), "stdout": out.getvalue(), "ms": int((time.time() - t0) * 1000)}
    finally:
        sys.stdout, sys.stderr = saved


def _jsonable(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, unreal.Vector):
        return [v.x, v.y, v.z]
    if isinstance(v, unreal.Rotator):
        return {"roll": v.roll, "pitch": v.pitch, "yaw": v.yaw}
    if isinstance(v, unreal.Object):
        return v.get_path_name()
    return str(v)


def _step(job) -> bool:
    """Advance a multi-tick job by one step; True when it has finished."""
    gen, box, buf, _, t0 = job
    saved = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = buf
    try:
        wait = next(gen)
        job[3] = time.time() + (float(wait) if isinstance(wait, (int, float)) and not isinstance(wait, bool) else 0.0)
        return False
    except StopIteration as e:
        box.update({"ok": True, "result": _jsonable(e.value), "stdout": buf.getvalue(), "ms": int((time.time() - t0) * 1000)})
    except Exception:
        box.update({"ok": False, "error": traceback.format_exc(), "stdout": buf.getvalue(), "ms": int((time.time() - t0) * 1000)})
    finally:
        sys.stdout, sys.stderr = saved
    box["done"] = True
    return True


def _tick(_dt):
    if _state.get("in_tick"):  # a job that saves or loads pumps Slate, which ticks again inside it: never re-enter
        return
    _state["in_tick"] = True
    try:
        _drain()
    finally:
        _state["in_tick"] = False


def _drain():
    now = time.time()
    _active[:] = [j for j in _active if j[3] > now or not _step(j)]
    budget = time.time() + 0.25
    while time.time() < budget:
        try:
            kind, payload, box = _work.get_nowait()
        except queue.Empty:
            return
        r = _run(kind, payload)
        if "gen" in r:
            _active.append([r["gen"], box, r["buf"], 0.0, r["t0"]])
            continue
        box.update(r)
        box["done"] = True


def submit(kind: str, payload: dict, timeout: float = 600.0, wait: bool = True) -> dict:
    box: dict = {"done": False, "id": uuid.uuid4().hex[:12], "queued": time.time()}
    for k in [k for k, b in _jobs.items() if b["done"] and time.time() - b["queued"] > 3600]:
        del _jobs[k]
    _jobs[box["id"]] = box
    _work.put((kind, payload, box))
    if not wait:
        return {"ok": True, "job": box["id"]}
    end = time.time() + timeout
    while not box["done"] and time.time() < end:
        time.sleep(0.02)
    if not box["done"]:
        return {"ok": False, "error": f"timeout after {timeout}s (still running as job {box['id']})", "job": box["id"]}
    return {k: v for k, v in box.items() if k not in ("done", "queued")}


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "fmbridge/1"

    def log_message(self, *a):  # quiet: the editor log has enough
        pass

    def _auth(self) -> bool:
        if self.headers.get("X-FM-Token") == _state["token"]:
            return True
        self._send(401, {"ok": False, "error": "bad token"})
        return False

    def _send(self, code: int, body, ctype: str = "application/json"):
        data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_GET(self):
        if not self._auth():
            return
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == "/health":
            self._send(200, {"ok": True, "engine": _state["engine"], "project": _state["project"],
                             "uptime": int(time.time() - _state["started"]), "queued": _work.qsize()})
        elif u.path == "/job":
            box = _jobs.get(q.get("id", ""))
            if not box:
                self._send(404, {"ok": False, "error": "no such job"})
            else:
                self._send(200, {"done": box["done"], **{k: v for k, v in box.items() if k not in ("done",)}})
        elif u.path == "/file":
            p = q.get("path", "")
            if not os.path.isfile(p):
                self._send(404, {"ok": False, "error": f"no file {p}"})
            else:
                with open(p, "rb") as f:
                    self._send(200, f.read(), "application/octet-stream")
        elif u.path == "/screen":
            from . import gui
            self._send(200, gui.screenshot_png(), "image/png")
        elif u.path == "/log":
            from . import gui
            self._send(200, {"ok": True, "log": gui.log_tail(_state["log_dir"], int(q.get("lines", "200")))})
        else:
            self._send(404, {"ok": False, "error": "unknown path"})

    def do_PUT(self):
        if not self._auth():
            return
        u = urllib.parse.urlparse(self.path)
        p = dict(urllib.parse.parse_qsl(u.query)).get("path", "")
        if u.path != "/file" or not p:
            self._send(400, {"ok": False, "error": "PUT /file?path=..."})
            return
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        data = self._body()
        with open(p, "wb") as f:
            f.write(data)
        self._send(200, {"ok": True, "bytes": len(data), "path": p})

    def do_POST(self):
        if not self._auth():
            return
        try:
            req = json.loads(self._body() or b"{}")
        except ValueError:
            self._send(400, {"ok": False, "error": "body must be JSON"})
            return
        path = urllib.parse.urlparse(self.path).path
        if path in ("/exec", "/op"):
            kind = path[1:]
            if kind == "exec" and "code" not in req:
                self._send(400, {"ok": False, "error": "exec needs code"})
                return
            self._send(200, submit(kind, req, float(req.get("timeout", 600)), not req.get("async")))
        elif path == "/gui":
            from . import gui
            try:
                self._send(200, {"ok": True, "result": gui.run(req.get("actions", []))})
            except Exception:
                self._send(200, {"ok": False, "error": traceback.format_exc()})
        else:
            self._send(404, {"ok": False, "error": "unknown path"})


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # on Windows reuse lets a second server share the port: never


def start(port: int = PORT) -> str:
    """Start (or keep) the bridge; returns where it listens."""
    if _state["server"]:
        return f"already on 127.0.0.1:{port}"
    # unreal's API is game-thread only: what the HTTP thread reports is read here, once
    _state["engine"] = unreal.SystemLibrary.get_engine_version()
    _state["project"] = unreal.Paths.get_project_file_path()
    _state["log_dir"] = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_log_dir())
    try:  # driven remotely, the editor is never the foreground window: do not let it idle at a few frames a second
        perf = unreal.get_default_object(unreal.EditorPerformanceSettings)
        perf.set_editor_property("throttle_cpu_when_not_foreground", False)
    except Exception as e:
        unreal.log_warning(f"fmbridge: could not stop background throttling: {e}")
    _state["token"] = secrets.token_urlsafe(24)
    with open(TOKEN_PATH, "w") as f:
        f.write(_state["token"])
    srv = _Server(("127.0.0.1", port), _Handler)
    threading.Thread(target=srv.serve_forever, name="fmbridge", daemon=True).start()
    _state["server"] = srv
    _state["tick"] = unreal.register_slate_post_tick_callback(_tick)
    unreal.log(f"fmbridge: listening on 127.0.0.1:{port} (token in {TOKEN_PATH})")
    return f"listening on 127.0.0.1:{port}"


def stop() -> None:
    while True:  # whatever is still queued here will never run: answer it now rather than let a client hang
        try:
            _, _, box = _work.get_nowait()
        except queue.Empty:
            break
        box.update({"ok": False, "error": "the bridge restarted before this ran; send it again", "done": True})
    for job in _active:
        job[1].update({"ok": False, "error": "the bridge restarted while this ran", "done": True})
    _active.clear()
    if _state["server"]:
        _state["server"].shutdown()
        _state["server"].server_close()  # release the port now, not at garbage collection
        _state["server"] = None
    if _state["tick"]:
        unreal.unregister_slate_post_tick_callback(_state["tick"])
        _state["tick"] = None
