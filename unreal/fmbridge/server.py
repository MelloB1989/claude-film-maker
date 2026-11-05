"""The bridge's endpoint inside the Unreal editor: a small HTTP server on 127.0.0.1 (never a public interface), reached
from the operator's machine through an SSM port-forwarding tunnel (tools/filmtools/unreal). Every request carries the
token written to Saved/fmbridge.token at start.

Editor work runs on the game thread (the `unreal` API may not be touched anywhere else): the HTTP thread queues it
and a Slate post-tick callback runs it, so any `unreal` call is safe. Desktop input and screen grabs (fmbridge.gui) run on the HTTP thread instead, so the editor keeps pumping
messages while a click lands.

    POST /exec   {"code": str, "timeout": s, "async": bool}  run Python; `result` in its namespace is returned
    POST /op     {"name": "mh.build", "args": {...}}           call a registered op (fmbridge.ops), same options

Every call is a job (fmbridge.jobs): {"async": true} returns its id at once; a generator runs across editor ticks
(`yield` one tick, `yield 0.5` seconds, `yield {"progress": .4, "message": ...}`); finished jobs outlive a reload.
    GET  /job?id=                                             a job's state, progress and (when finished) result
    GET  /jobs?state=&name=&limit=                            recent jobs, newest first (no results)
    POST /job/cancel {"id": ...}                              cancel a queued job, or a running multi-tick one
    POST /batch  {"calls": [{"name": op, "args": {...}}, ...], "stop_on_error": true}   several ops as one job, in
                 order, as many per tick as fit (a multi-tick op among them runs across ticks); one result each
    POST /gui    {"actions": [...]}                           desktop input (fmbridge.gui.run; Windows only, else 501)
    GET  /screen                                              the desktop as PNG (Windows only, else 501)
    GET  /file?path=   PUT /file?path=                         read or write a file under the project, the temp
                                                              folder, the editor user's home or (Linux) /srv
                                                              (FMBRIDGE_FILE_ROOTS adds more, os.pathsep-separated)
    GET  /log?lines=N                                         the editor log's tail
    GET  /health                                              engine, platform, project, uptime, jobs, memory, idle cap
"""
from __future__ import annotations

import hmac
import http.server
import inspect
import json
import os
import platform
import secrets
import socketserver
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse

import unreal

from . import jobs as _jobs_mod

VERSION = 2  # the bridge's protocol: 2 = jobs (/jobs, /job/cancel, progress), health extras
PORT = int(os.environ.get("FMBRIDGE_PORT", "18765"))
SAVED = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
TOKEN_PATH = os.path.join(SAVED, "fmbridge.token")
JOURNAL = os.path.join(SAVED, "Bridge", "jobs")

_state = {"server": None, "tick": None, "started": time.time(), "token": None, "registry": None, "last_call": time.time()}
MAX_JSON = 32 * 2**20      # bytes in one JSON request (a /batch of many calls, an exec script)
MAX_FILE = 4 * 2**30       # bytes in one PUT /file (folders go by S3/rsync: workstation.push_dir)
MAX_BATCH = 500            # calls in one /batch


def _namespace() -> dict:
    from . import ops  # noqa: F401 (registers every op module)
    import fmbridge
    return {"unreal": unreal, "fmbridge": fmbridge, "ops": fmbridge.ops, "__name__": "__fmbridge__", "result": None}


def _run(kind: str, payload: dict):
    """On the game thread: run code or an op and return its value (a generator for a multi-tick job). The registry
    captures what it prints and turns an exception into a failed job."""
    if kind == "batch":
        return _batch(payload.get("calls") or [], bool(payload.get("stop_on_error", True)))
    if kind == "exec":
        ns = _namespace()
        exec(compile(payload["code"], payload.get("name", "<bridge>"), "exec"), ns)
        return ns.get("result")
    from . import ops
    return ops.call(payload["name"], **(payload.get("args") or {}))


def _batch(calls: list, stop_on_error: bool):
    """Several ops in order, as one job: plain ops run back to back in the same tick, a multi-tick one runs across
    ticks before the next starts. Each gets {"ok", "name", "result"} or the structured failure."""
    from . import ops
    out = []
    for i, c in enumerate(calls):
        name = c.get("name")
        try:
            res = ops.call(name, **(c.get("args") or {}))
            if inspect.isgenerator(res):
                res = yield from res
            out.append({"ok": True, "i": i, "name": name, "result": _jsonable(res)})
        except Exception as e:
            out.append({"ok": False, "i": i, "name": name, "error": traceback.format_exc(), **_failure_detail(e)})
            if stop_on_error:
                break
    if False:  # a batch is always a generator, even when every op in it is plain
        yield
    return {"ok": all(r["ok"] for r in out) and len(out) == len(calls), "ran": len(out), "of": len(calls),
            "results": out}


def _batch_calls(req: dict):
    """The calls of a /batch request, or an error message."""
    calls = req.get("calls")
    if not isinstance(calls, list) or not calls:
        return None, "batch needs calls: [{\"name\": op, \"args\": {...}}, ...]"
    if len(calls) > MAX_BATCH:
        return None, f"at most {MAX_BATCH} calls in one batch (got {len(calls)}): split it"
    for i, c in enumerate(calls):
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not isinstance(c.get("args", {}), dict):
            return None, f"call {i}: {{\"name\": op, \"args\": {{...}}}}"
    return calls, None


def _file_roots() -> list:
    roots = [os.path.dirname(_state.get("project") or "") or SAVED, tempfile.gettempdir(), os.path.expanduser("~")]
    if sys.platform.startswith("linux"):
        roots.append("/srv")  # a Linux box's data volume: projects, the engine, film inputs (/srv/film/...)
    roots += [r for r in os.environ.get("FMBRIDGE_FILE_ROOTS", "").split(os.pathsep) if r]
    return [os.path.normcase(os.path.realpath(r)) for r in roots if r]


def _file_allowed(p: str) -> bool:
    """A /file path must be absolute and inside one of the roots (no ../ escapes, symlinks resolved)."""
    if not p or not os.path.isabs(p):
        return False
    real = os.path.normcase(os.path.realpath(p))
    return any(real == r or real.startswith(r.rstrip(os.sep) + os.sep) for r in _file_roots())


def registry() -> "_jobs_mod.Registry":
    if _state["registry"] is None:
        _state["registry"] = _jobs_mod.Registry(_run, _jsonable, JOURNAL, failure=_failure_detail)
    return _state["registry"]


def _failure_detail(e: Exception) -> dict:
    """A failed job's structured fields beside its traceback: an OpError's code, message, hint and candidates, so the
    caller can act without reading the traceback (fmbridge.errors); any other exception: code "exception"."""
    from .errors import OpError
    if isinstance(e, OpError):
        return e.to_json()
    return {"code": "exception", "message": f"{type(e).__name__}: {e}"}


def _failure(e: Exception) -> dict:
    """A failed call's whole answer (ok, error = the traceback, and the structured fields)."""
    return {"ok": False, "error": traceback.format_exc(), **_failure_detail(e)}


def _gui():
    """fmbridge.gui, or None where there is no desktop to drive (an offscreen editor on Linux)."""
    try:
        from . import gui
        return gui
    except ImportError:
        return None


def log_tail(logs: str, lines: int = 200) -> str:
    files = sorted((os.path.join(logs, f) for f in os.listdir(logs) if f.endswith(".log")), key=os.path.getmtime)
    if not files:
        return ""
    with open(files[-1], "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 400 * lines))
        return "\n".join(f.read().decode("utf-8", "replace").splitlines()[-lines:])


IDLE_FPS = 30  # offscreen editor between jobs; a bridge op that runs over several ticks advances one step per tick
NO_DESKTOP = {"ok": False, "error": f"no desktop on {sys.platform}: use look.still / seq.still for pictures"}


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


def _tick(_dt):
    _state["last_tick"] = time.time()  # health reports how long ago: a long silence is a stuck game thread
    if _state.get("in_tick"):  # a job that saves or loads pumps Slate, which ticks again inside it: never re-enter
        return
    _state["in_tick"] = True
    try:
        if not _state.get("idle_set"):
            _state["idle_set"] = True
            _idle_offscreen()
        registry().tick()
    finally:
        _state["in_tick"] = False


def _idle_offscreen():
    """With no desktop nobody looks at the level viewport, but a realtime one still renders the scene every frame
    (Lumen and all: the GPU at full load between jobs). Off Windows: the viewport redraws only on change, and the
    editor ticks at most IDLE_FPS (Movie Render Queue lifts the cap with its own t.MaxFPS while it renders)."""
    if sys.platform == "win32":
        return
    try:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_set_viewport_realtime(False)
        unreal.SystemLibrary.execute_console_command(None, f"t.MaxFPS {IDLE_FPS}")
        _state["idle_fps"] = IDLE_FPS
    except Exception as e:
        unreal.log_warning(f"fmbridge: could not idle the offscreen viewport: {e}")


def _no_background_throttle():
    """Driven remotely, the editor is never the foreground app, and the editor's "Use less CPU when in background"
    (UEditorPerformanceSettings::bThrottleCPUWhenNotForeground, on by default) then throttles it and skips rendering
    (EditorEngine.cpp). The class is not exposed to Python by name, so its defaults object is found by path."""
    try:
        cdo = unreal.find_object(None, "/Script/UnrealEd.Default__EditorPerformanceSettings")
        if cdo is None:
            raise LookupError("no /Script/UnrealEd.Default__EditorPerformanceSettings")
        # the wrapper is the nearest exposed base class, which has no Python name for this property: set_editor_property
        # then looks the name up on the real class as given (PyWrapperObject.cpp FindEditorPropertyImpl)
        try:
            cdo.set_editor_property("bThrottleCPUWhenNotForeground", False)
        except Exception:
            cdo.set_editor_property("throttle_cpu_when_not_foreground", False)
        _state["throttle_off"] = True
    except Exception as e:
        _state["throttle_off"] = False
        unreal.log_warning(f"fmbridge: could not stop background throttling: {e}")


def submit(kind: str, payload: dict, timeout: float = 600.0, wait: bool = True) -> dict:
    """Queue a job; wait for it (up to `timeout`) or return its id at once. A job still running at the timeout keeps
    running: the answer says so and carries its id (GET /job?id=)."""
    _state["last_call"] = time.time()
    reg = registry()
    job = reg.submit(kind, payload)
    if not wait:
        return {"ok": True, "job": job.id, "id": job.id, "state": job.state}
    if not reg.wait(job, timeout):
        return {"ok": False, "error": f"timeout after {timeout}s (still {job.state} as job {job.id}: GET /job?id={job.id})",
                "job": job.id, "id": job.id, "state": job.state}
    return job.view()


def _rss_mb() -> float | None:
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return round(int(line.split()[1]) / 1024, 1)
        return None
    except OSError:
        return None


def health() -> dict:
    """What a client (or a watchdog) needs to know the editor is alive and what it is (no game-thread call: the HTTP
    thread answers this even while a long job holds the game thread)."""
    reg = registry()
    now = time.time()
    return {"ok": True, "engine": _state.get("engine"), "platform": sys.platform, "project": _state.get("project"),
            "uptime": int(now - _state["started"]), "bridge": VERSION, "python": platform.python_version(),
            "pid": os.getpid(), "rss_mb": _rss_mb(), "jobs": reg.counts(), "queued": reg.counts()["queued"],
            "idle_fps": _state.get("idle_fps"), "throttle_off": _state.get("throttle_off"),
            "last_tick_s": round(now - _state.get("last_tick", now), 1), "idle_s": int(now - _state["last_call"])}


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "fmbridge/1"

    def log_message(self, *a):  # quiet: the editor log has enough
        pass

    def _auth(self) -> bool:
        tok = _state["token"] or ""
        if tok and hmac.compare_digest(str(self.headers.get("X-FM-Token") or ""), tok):  # constant time
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

    def _body(self, limit: int | None = None):
        """The request body, or None after answering 400/413 (no length, a bad one, or too big)."""
        limit = MAX_JSON if limit is None else limit
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0:
            self._send(400, {"ok": False, "error": "bad Content-Length"})
            return None
        if n > limit:
            self._send(413, {"ok": False, "error": f"request of {n} bytes; the limit here is {limit} "
                                                    "(big files: workstation.push_dir; many ops: several batches)"})
            return None
        return self.rfile.read(n)

    def do_GET(self):
        if not self._auth():
            return
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == "/health":
            self._send(200, health())
        elif u.path == "/job":
            job = registry().get(q.get("id", ""))
            if not job:
                self._send(404, {"ok": False, "error": f"no job {q.get('id', '')!r} (GET /jobs lists recent ones)"})
            else:
                self._send(200, job.view())
        elif u.path == "/jobs":
            self._send(200, {"ok": True, "jobs": registry().list(q.get("state", ""), q.get("name", ""),
                                                                   int(q.get("limit", "50")))})
        elif u.path == "/file":
            p = q.get("path", "")
            if not _file_allowed(p):
                self._send(403, {"ok": False, "error": f"{p!r} is outside the project, temp and home folders "
                                                       "(FMBRIDGE_FILE_ROOTS adds roots)"})
            elif not os.path.isfile(p):
                self._send(404, {"ok": False, "error": f"no file {p}"})
            else:
                with open(p, "rb") as f:
                    self._send(200, f.read(), "application/octet-stream")
        elif u.path == "/screen":
            gui = _gui()
            if gui:
                self._send(200, gui.screenshot_png(), "image/png")
            else:
                self._send(501, NO_DESKTOP)
        elif u.path == "/log":
            self._send(200, {"ok": True, "log": log_tail(_state["log_dir"], int(q.get("lines", "200")))})
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
        if not _file_allowed(p):
            self._send(403, {"ok": False, "error": f"{p!r} is outside the project, temp and home folders "
                                                   "(FMBRIDGE_FILE_ROOTS adds roots)"})
            return
        data = self._body(MAX_FILE)
        if data is None:
            return
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        self._send(200, {"ok": True, "bytes": len(data), "path": p})

    def do_POST(self):
        if not self._auth():
            return
        body = self._body()
        if body is None:
            return
        try:
            req = json.loads(body or b"{}")
        except ValueError:
            self._send(400, {"ok": False, "error": "body must be JSON"})
            return
        path = urllib.parse.urlparse(self.path).path
        if path == "/job/cancel":
            self._send(200, registry().cancel(str(req.get("id", ""))))
        elif path == "/batch":
            calls, err = _batch_calls(req)
            if err:
                self._send(400, {"ok": False, "code": "bad_args", "error": err})
                return
            payload = {"calls": calls, "stop_on_error": req.get("stop_on_error", True), "name": "batch"}
            self._send(200, submit("batch", payload, float(req.get("timeout", 600)), not req.get("async")))
        elif path in ("/exec", "/op"):
            kind = path[1:]
            if kind == "exec" and "code" not in req:
                self._send(400, {"ok": False, "error": "exec needs code"})
                return
            self._send(200, submit(kind, req, float(req.get("timeout", 600)), not req.get("async")))
        elif path == "/gui":
            gui = _gui()
            if not gui:
                self._send(501, NO_DESKTOP)
                return
            try:
                self._send(200, {"ok": True, "result": gui.run(req.get("actions", []))})
            except Exception:
                self._send(200, {"ok": False, "error": traceback.format_exc()})
        else:
            self._send(404, {"ok": False, "error": "unknown path"})


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    # on Windows SO_REUSEADDR lets a second server share the port: never. On Linux it only lets a restarted bridge bind
    # while the old one's connections sit in TIME_WAIT (two listeners still cannot share it): without it, EADDRINUSE
    allow_reuse_address = sys.platform != "win32"


def start(port: int = PORT) -> str:
    """Start (or keep) the bridge; returns where it listens."""
    if _state["server"]:
        return f"already on 127.0.0.1:{port}"
    # unreal's API is game-thread only: what the HTTP thread reports is read here, once
    _state["engine"] = unreal.SystemLibrary.get_engine_version()
    _state["project"] = unreal.Paths.get_project_file_path()
    _state["log_dir"] = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_log_dir())
    _no_background_throttle()
    registry()  # read the journal now: results of jobs from before a reload answer at once
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
    if _state["registry"] is not None:  # whatever is queued or running will never finish here: answer it now
        _state["registry"].shutdown("the bridge restarted")
    if _state["server"]:
        _state["server"].shutdown()
        _state["server"].server_close()  # release the port now, not at garbage collection
        _state["server"] = None
    if _state["tick"]:
        unreal.unregister_slate_post_tick_callback(_state["tick"])
        _state["tick"] = None
