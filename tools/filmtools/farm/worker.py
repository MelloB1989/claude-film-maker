"""The worker: runs on every farm box as film-farm-worker.service (root), claims chunks, renders them, uploads the
frames, and powers the box off when the queue is empty for `idle_s` or its TTL comes.

    python3 -m filmtools.farm.worker [--conf /etc/film-farm/worker.json] [--once]

Settings (written by `film-farm up` through the user-data): {"farm", "bucket", "region", "ttl_until", "idle_s",
"private_root", "scratch", "poweroff": true, "price_h"}.

A chunk, start to end:
  1. claim it (queue.claim: a lease only this worker holds), then a heartbeat thread renews the lease every 30 s;
  2. read the frames already in the output that a record vouches for (size + sha256) and plan what is left
     (model.todo): a re-queued chunk picks up where the lost worker stopped;
  3. the engine renders (pre-roll included); each finished frame is hashed and uploaded (SSE-KMS for a private
     job) while the lease is still ours, pre-roll frames and frames already there are not;
  4. done.json once (If-None-Match) with every frame's size and hash, and the chunk's scratch is deleted.
A render that fails gives the chunk back at once (it is tried again, up to the job's max_attempts, by any worker).
If the lease is lost (this box was stopped longer than the lease and someone took over), the render is stopped and
nothing more is uploaded.

Nothing of a private job leaves the box except to its private prefix: no frame in a log, no path outside it.
Python 3.10, stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request

from . import model
from .queue import BEAT_S, LEASE_S, Queue
from .store import AwsStore, PreconditionFailed
from . import engines

CONF = "/etc/film-farm/worker.json"


def instance_id() -> str:
    """This box's EC2 instance id (IMDSv2), else the host name (a test machine)."""
    try:
        t = urllib.request.urlopen(urllib.request.Request(
            "http://169.254.169.254/latest/api/token", method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"}), timeout=2).read().decode()
        return urllib.request.urlopen(urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": t}), timeout=2).read().decode()
    except OSError:
        return socket.gethostname()


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Ctx:
    """What an engine gets: logging, the stop flag, the settings, a shell, and state kept per job."""

    def __init__(self, conf: dict, log):
        self.conf, self.log, self.state = conf, log, {}
        self._stop = threading.Event()

    def stopping(self) -> bool:
        return self._stop.is_set()

    def sh(self, cmd: str, timeout: float = 600, check: bool = True) -> int:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0 and check:
            raise engines.RenderError(f"$ {cmd[:120]}: exit {r.returncode}: {(r.stderr or r.stdout)[-400:]}")
        return r.returncode


class Worker:
    def __init__(self, conf: dict, queue: Queue | None = None, clock=time.time, sleep=time.sleep):
        self.conf = conf
        self.id = conf.get("worker") or instance_id()
        self.store = queue.s if queue else AwsStore(conf["bucket"], conf["region"])
        self.q = queue or Queue(self.store, conf["farm"], clock=clock,
                                private_root=conf.get("private_root", "ue-linux/private/"))
        self.now, self.sleep = clock, sleep
        self.lines: list[str] = []
        self.prepared: dict = {}
        self.ctx = Ctx(conf, self.log)
        self.session = [int(self.now()), int(self.now())]
        self.stats = {"frames": 0, "render_s": 0.0, "chunks": 0, "chunk": None, "fps": 0.0, "job": None}

    # --- reporting --------------------------------------------------------------------------------------------------
    def log(self, msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(self.now()))} {self.id} {msg}"
        print(line, flush=True)
        self.lines.append(line)
        del self.lines[:-2000]

    def report(self) -> None:
        """workers/<id>.json (its sessions = time it ran, for the cost) and its log, in the farm's public part:
        chunk ids, frame counts and timings only, never a scene's content."""
        self.session[1] = int(self.now())
        key = f"farm/{self.q.farm}/workers/{self.id}.json"
        try:
            doc, _ = self.store.get_json(key)
            doc = doc or {"worker": self.id, "sessions": []}
            ses = doc.setdefault("sessions", [])
            if ses and ses[-1][0] == self.session[0]:
                ses[-1] = list(self.session)
            else:
                ses.append(list(self.session))
            doc.update(self.stats, at=self.now(), type=self.conf.get("type"), market=self.conf.get("market"),
                       price_h=self.conf.get("price_h"), ttl_until=self.conf.get("ttl_until"))
            self.store.put_json(key, doc)
            self.store.put(f"farm/{self.q.farm}/logs/{self.id}.log", ("\n".join(self.lines) + "\n").encode())
        except Exception as e:  # reporting never stops a render
            print(f"report failed: {e}", file=sys.stderr)

    # --- the loop ---------------------------------------------------------------------------------------------------
    def run(self, once: bool = False) -> str:
        self.log(f"worker up: farm {self.q.farm}, idle {self.conf.get('idle_s', 600)} s")
        idle_since = self.now()
        while True:
            why = self.should_end(idle_since)
            if why:
                self.log(f"ending: {why}")
                self.report()
                return why
            got = self.claim()
            if got is None and self.assemble_one():
                idle_since = self.now()
                continue
            if got is None:
                self.report()
                if once:
                    return "empty"
                self.sleep(20)
                continue
            self.run_chunk(*got)
            idle_since = self.now()
            if once:
                return "ran"

    def should_end(self, idle_since: float) -> str:
        ttl = self.conf.get("ttl_until")
        if ttl and self.now() >= ttl:
            return "ttl"
        if self.now() - idle_since >= float(self.conf.get("idle_s", 600)):
            return "idle"
        return ""

    def claim(self):
        for j in self.q.jobs():
            if j.get("state") in ("done", "cancelled", "paused"):
                continue
            got = self.q.claim(j["root"], self.id)
            if got:
                return j["root"], got[0], got[1]
        return None

    def assemble_one(self) -> bool:
        """An assemble someone asked for, once every chunk of its job is done (verify.assemble)."""
        from . import verify
        for j in self.q.jobs():
            got = self.q.claim_assemble(j["root"], self.id)
            if not got:
                continue
            req, _ = got
            local = os.path.join(self.conf.get("scratch", "/srv/farm"), j["id"], "_assemble")
            self.log(f"{j['id']}: assembling {req.get('kinds')}")
            try:
                rep = verify.assemble(self.q, j["root"], local, kinds=tuple(req.get("kinds") or ["mp4"]), log=self.log)
            except Exception as e:
                rep = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            self.log(f"{j['id']}: assembled ok={rep.get('ok')}")
            self.q.finish_assemble(j["root"], self.id, rep)
            import shutil
            shutil.rmtree(local, ignore_errors=True)
            return True
        return False

    def run_chunk(self, root: str, chunk: dict, etag: str) -> bool:
        job = self.q.job(root)
        out, cid = job["output"], chunk["id"]
        eng = engines.get(job["engine"])
        state = {"etag": etag, "beat_ok": self.now(), "lost": False}
        uploaded: dict = {}
        self.ctx._stop.clear()
        self.stats.update(job=job["id"], chunk=cid)
        stop_beat = threading.Event()

        def beat():
            while not stop_beat.wait(BEAT_S):
                try:
                    state["etag"] = self.q.heartbeat(root, cid, self.id, state["etag"], frames=len(uploaded))
                    state["beat_ok"] = self.now()
                    self.q.progress(root, cid, self.id, dict(uploaded))
                    self.report()
                except PreconditionFailed:
                    self.log(f"{job['id']}/{cid}: lease lost: stopping")
                    state["lost"] = True
                    self.ctx._stop.set()
                    return
                except Exception as e:  # S3 hiccup: keep the render, try again next beat
                    self.log(f"heartbeat: {e}")
                    if self.now() - state["beat_ok"] > LEASE_S - 2 * BEAT_S:
                        self.ctx._stop.set()  # about to lose it anyway: stop uploading

        t = threading.Thread(target=beat, daemon=True)
        t.start()
        scratch = os.path.join(self.conf.get("scratch", "/srv/farm"), job["id"], cid)
        t0 = self.now()
        try:
            have = self.q.trusted_frames(root, cid, chunk, out)
            td = model.todo(chunk, have, job, contiguous=eng.CONTIGUOUS)
            if td is None:
                self.log(f"{job['id']}/{cid}: every frame already there")
            else:
                self.log(f"{job['id']}/{cid}: frames [{td['start']},{td['end']}) render from {td['render_from']} "
                         f"({len(td['missing'])} missing, {len(have)} kept)")
                if job["id"] not in self.prepared:
                    eng.prepare(job, self.ctx)
                    self.prepared[job["id"]] = True
                b, prefix = model.split_s3(out["prefix"])
                t_first = None  # fps from the first frame on: installs, editor starts and pre-roll are not render speed
                for f, path in eng.render(job, chunk, td, scratch, self.ctx):
                    t_first = t_first or self.now()
                    if f < chunk["start"] or f >= chunk["end"] or f in have:
                        continue  # pre-roll, or already in the output
                    if state["lost"] or self.ctx.stopping():
                        raise engines.RenderError("lease lost: not uploading")
                    if self.now() - state["beat_ok"] > LEASE_S - BEAT_S:
                        raise engines.RenderError("lease about to expire unrenewed: not uploading")
                    size, digest = os.path.getsize(path), sha256(path)
                    if size == 0:
                        raise engines.RenderError(f"frame {f}: empty file")
                    self.store.upload(prefix + model.frame_name(f, out), path,
                                      sse_kms=job["privacy"] == "private", metadata={"sha256": digest})
                    uploaded[f] = [size, digest]
                    self.q.progress(root, cid, self.id, uploaded)  # a worker lost next second leaves this behind
                    self.stats["frames"] += 1
                    if len(uploaded) > 1:
                        self.stats["fps"] = round((len(uploaded) - 1) / max(1e-6, self.now() - t_first), 4)
            frames = {**have, **uploaded}
            gone = [f for f in range(chunk["start"], chunk["end"]) if f not in frames]
            if gone:
                raise engines.RenderError(f"frames missing after the render: {model.runs(gone)[:5]}")
            stop_beat.set()
            t.join(5)
            self.q.progress(root, cid, self.id, uploaded)
            extra = {"hook": self.ctx.state.pop("hook")} if self.ctx.state.get("hook") is not None else {}
            ok = self.q.complete(root, cid, self.id, state["etag"], frames, render_s=round(self.now() - t0, 1),
                                 preroll=chunk["preroll"], uploaded=len(uploaded), **extra)
            self.log(f"{job['id']}/{cid}: {'done' if ok else 'NOT recorded (lease lost)'}: {len(uploaded)} uploaded "
                     f"in {self.now() - t0:.0f} s")
            self.stats["chunks"] += ok
            self.stats["render_s"] += self.now() - t0
            eng.cleanup(scratch)
            return ok
        except Exception as e:
            why = f"{type(e).__name__}: {e}"
            self.log(f"{job['id']}/{cid}: FAILED: {why}")
            if not isinstance(e, engines.RenderError):
                self.log(traceback.format_exc()[-1500:])
            stop_beat.set()
            t.join(5)
            if uploaded:
                self.q.progress(root, cid, self.id, uploaded)  # the next worker keeps these
            if not state["lost"]:
                self.q.release(root, cid, self.id, state["etag"], why)
            return False
        finally:
            stop_beat.set()
            self.stats["chunk"] = None
            self.report()


def poweroff(conf: dict, why: str) -> None:
    """The box ends itself. On-demand workers were launched with shutdown = terminate (gone); a persistent spot
    worker is stopped (its request lives on: `film-farm down` terminates it and cancels the request)."""
    if conf.get("poweroff", True):
        subprocess.run(["systemctl", "poweroff"], check=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="film-farm worker (runs on a farm box)")
    ap.add_argument("--conf", default=CONF)
    ap.add_argument("--once", action="store_true", help="claim and render one chunk, then exit")
    a = ap.parse_args(argv)
    conf = json.load(open(a.conf))
    w = Worker(conf)
    why = w.run(once=a.once)
    if why in ("idle", "ttl") and not a.once:
        poweroff(conf, why)
    return 0


if __name__ == "__main__":
    sys.exit(main())
