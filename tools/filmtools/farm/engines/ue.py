"""Unreal (MRQ) on a worker: the box's own editor (ue-editor.service, the fmbridge inside it on 127.0.0.1) renders the
chunk with film-ue's `render.job`, the same op and RENDER SPEC as a one-box render (docs/unreal/render.md): its
presets, cvars, warm-ups, stall watchdog and pre-roll from the shot start. The farm adds its own pre-roll: the
chunk renders from `render_from` (24-32 frames before its first frame, never across a cut), and those frames are
thrown away, so TSR history, hair and cloth arrive at the chunk's first frame as in one continuous render.

The job's "ue" settings:

    {"spec": {...RENDER SPEC: sequence, level, preset, cvars, warmup_engine, warmup_render, ...},
     "sync": [{"s3": "s3://B/ue-linux/private/project/HostStudio", "local": "/srv/ue/projects/HostStudio"}, ...],
                                        # once per worker, editor stopped: deltas on top of the image (project, DDC)
     "before": [["mh.leader", {"label": "..."}], ["some.guard", {...}]],
                                        # ops run before every chunk (a film's guards); one that fails fails the chunk
     "guard": {"op": "...", "args": {...}, "ok": "ok"},   # optional: an op whose result[ok] must be truthy
     "fresh_editor": true,              # restart the editor before every chunk (default true: the proven path)
     "wait_compile": true,              # editor.wait_compile after a start (shaders)
     "stall_s": 900, "port": 18765, "project_dir": "(default: UE_PROJECT's folder in /etc/default/ue-editor)"}

The spec's frames, out_dir, name, resume and overwrite are the farm's: whatever the job says there is replaced.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import time
import urllib.error
import urllib.request

from . import RenderError, frames_on_disk

CONTIGUOUS = True
UNIT = "ue-editor"


def project_dir(job: dict) -> str:
    u = job.get("ue") or {}
    if u.get("project_dir"):
        return u["project_dir"]
    try:
        for line in open("/etc/default/ue-editor"):
            k, _, v = line.strip().partition("=")
            if k == "UE_PROJECT":
                return os.path.dirname(v.strip().strip('"'))
    except OSError:
        pass
    raise RenderError("ue job: no project_dir and no UE_PROJECT in /etc/default/ue-editor")


class Bridge:
    """The editor's bridge on this box (stdlib HTTP; the same calls as filmtools.unreal.client)."""

    def __init__(self, project: str, port: int = 18765):
        self.token_path = os.path.join(project, "Saved", "fmbridge.token")
        self.port = port

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 60) -> dict:
        tok = open(self.token_path).read().strip() if os.path.exists(self.token_path) else ""
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                                     headers={"X-FM-Token": tok, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")

    def healthy(self) -> bool:
        try:
            return bool(self._call("GET", "/health", timeout=10).get("ok", True))
        except (OSError, urllib.error.URLError, ValueError):
            return False

    def submit(self, name: str, args: dict) -> str:
        r = self._call("POST", "/op", {"name": name, "args": args, "async": True})
        if not r.get("ok"):
            raise RenderError(f"{name}: not started: {r.get('error', r)}")
        return r["job"]

    def job(self, jid: str) -> dict:
        return self._call("GET", f"/job?id={jid}", timeout=60)

    def cancel(self, jid: str) -> None:
        try:
            self._call("POST", "/job/cancel", {"id": jid})
        except (OSError, urllib.error.URLError, ValueError):
            pass

    def run(self, name: str, args: dict, ctx, timeout: float = 3600) -> dict:
        """An op to its end; its result, or RenderError with the op's error."""
        jid = self.submit(name, args)
        end = time.time() + timeout
        while time.time() < end:
            try:
                j = self.job(jid)
            except (OSError, urllib.error.URLError, ValueError):
                time.sleep(5)
                continue
            if j.get("done"):
                if not j.get("ok"):
                    raise RenderError(f"{name}: {str(j.get('error') or j)[:600]}")
                return j.get("result") or {}
            if ctx.stopping():
                self.cancel(jid)
                raise RenderError(f"{name}: stopped")
            time.sleep(2)
        self.cancel(jid)
        raise RenderError(f"{name}: timed out after {timeout:.0f} s")


def restart_editor(job: dict, ctx, bridge: Bridge, timeout: float = 1200) -> None:
    ctx.log("editor: restart")
    ctx.sh(f"systemctl restart {UNIT}", timeout=300)
    time.sleep(10)
    wait_editor(job, ctx, bridge, timeout)


def wait_editor(job: dict, ctx, bridge: Bridge, timeout: float = 1200) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if bridge.healthy():
            ctx.log(f"editor: bridge up after {time.time() - t0:.0f} s")
            if (job.get("ue") or {}).get("wait_compile", True):
                bridge.run("editor.wait_compile", {"timeout_s": 3600}, ctx, timeout=3700)
            return
        if ctx.stopping():
            raise RenderError("stopped while the editor started")
        time.sleep(5)
    raise RenderError(f"editor: no bridge after {timeout:.0f} s (journalctl -u {UNIT})")


def prepare(job: dict, ctx) -> None:
    u = job.get("ue") or {}
    proj = project_dir(job)
    ctx.state["bridge"] = Bridge(proj, int(u.get("port") or 18765))
    syncs = u.get("sync") or []
    if syncs:
        ctx.log(f"ue: {len(syncs)} delta sync(s), editor stopped")
        ctx.sh(f"systemctl stop {UNIT}", timeout=300, check=False)
        for s in syncs:
            if not str(s.get("s3", "")).startswith("s3://") or not s.get("local"):
                raise RenderError(f"ue sync {s}: needs s3 and local")
            # as the editor's user, so the files stay theirs
            user = u.get("user") or "ubuntu"
            ctx.sh(f"sudo -u {user} -H mkdir -p {s['local']} && sudo -u {user} -H aws s3 sync --only-show-errors "
                   f"--no-progress {s['s3']} {s['local']}", timeout=4 * 3600)
        ctx.sh(f"systemctl start {UNIT}", timeout=300)
    ctx.state["started"] = False


def chunk_spec(job: dict, chunk: dict, todo: dict, scratch: str) -> dict:
    """The RENDER SPEC for this chunk: the job's, with the farm's range (pre-roll included), folder and name."""
    spec = copy.deepcopy((job.get("ue") or {}).get("spec") or {})
    if not spec.get("sequence"):
        raise RenderError("ue job: spec.sequence is missing")
    spec.update({"kind": "render", "version": 1, "name": f"farm_{job['id']}_{chunk['id']}",
                 "out_dir": scratch, "frames": [todo["render_from"], todo["end"]],
                 "resume": False, "overwrite": True, "zero_pad": int(job["output"]["pad"])})
    spec.setdefault("chunking", "shot")  # one MRQ job per camera cut inside the range, as a one-box render does
    spec.setdefault("preroll", "cut")  # sims evaluated from the shot start, as in a one-box render
    spec.pop("shots", None)
    spec.pop("boxes", None)
    return spec


def render(job: dict, chunk: dict, todo: dict, scratch: str, ctx):
    u, out = job.get("ue") or {}, job["output"]
    br: Bridge = ctx.state["bridge"]
    shutil.rmtree(scratch, ignore_errors=True)  # every attempt pre-rolls from nothing: no half history from before
    os.makedirs(scratch, exist_ok=True)
    if u.get("fresh_editor", True) or not br.healthy():
        restart_editor(job, ctx, br)
    elif not ctx.state.get("started"):
        wait_editor(job, ctx, br)
    ctx.state["started"] = True
    for name, args in u.get("before") or []:
        ctx.log(f"before: {name}")
        br.run(name, args or {}, ctx, timeout=1800)
    g = u.get("guard")
    if g:
        res = br.run(g["op"], g.get("args") or {}, ctx, timeout=1800)
        if not res.get(g.get("ok", "ok")):
            raise RenderError(f"guard {g['op']} refused the chunk: {json.dumps(res)[:400]}")
    spec = chunk_spec(job, chunk, todo, scratch)
    ctx.log(f"render.job [{spec['frames'][0]},{spec['frames'][1]}) (pre-roll {todo['preroll']})")
    jid = br.submit("render.job", {"spec": spec, "stall_s": float(u.get("stall_s") or 900)})
    seen: set = set()
    last_new, t0 = time.time(), time.time()
    stall = float(u.get("stall_s") or 900) + 600  # render.job's own watchdog first; this one if the editor hangs
    first_allow = 3600.0                           # level load, warm-up and the shaders it meets
    while True:
        try:
            j = br.job(jid)
        except (OSError, urllib.error.URLError, ValueError):
            j = {}
            if not br.healthy() and time.time() - last_new > 300:
                raise RenderError("the editor went away during the render")
        done = bool(j.get("done"))
        disk = frames_on_disk(scratch, out["ext"])
        new = {f: p for f, p in disk.items() if f not in seen and (done or any(g > f for g in disk))}
        for f in sorted(new):
            seen.add(f)
            last_new = time.time()
            yield f, new[f]
        if done:
            if not j.get("ok"):
                raise RenderError(f"render.job: {str(j.get('error'))[:600]}")
            rep = j.get("result") or {}
            if rep.get("status") != "ok":
                raise RenderError(f"render.job status {rep.get('status')}: {str(rep.get('errors'))[:400]}")
            break
        if ctx.stopping():
            br.cancel(jid)
            raise RenderError("stopped (lease lost or box going down)")
        quiet = time.time() - last_new
        if (seen and quiet > stall) or (not seen and time.time() - t0 > first_allow):
            br.cancel(jid)
            raise RenderError(f"no new frame for {quiet:.0f} s: editor hung (restarted next chunk)")
        time.sleep(3)
    missing = [f for f in todo["frames"] if f not in seen]
    if missing:
        raise RenderError(f"render.job wrote no file for frames {missing[:10]} (ext {out['ext']}? the preset's "
                          "format must match output.ext)")


def cleanup(scratch: str) -> None:
    shutil.rmtree(scratch, ignore_errors=True)
