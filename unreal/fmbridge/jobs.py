"""Jobs: every bridge call (an op or a piece of Python) is a job with an id, a state and, when it ends, a result that
outlives the call that started it. A client can start one and come back for it (async), poll it, cancel it, and find
its result again after its connection dropped or the bridge itself was reloaded (finished jobs are written to a small
journal on disk and read back at start).

States: queued -> running -> done | failed | cancelled; "lost" for a job that was running when the bridge stopped.

A job runs on the game thread (the server's tick). A plain call finishes in that tick. A generator runs across ticks:
    yield            let the editor tick once (a scrubbed sequence settles, a rig updates)
    yield 0.5        wait that many seconds before the next step
    yield {"progress": 0.4, "message": "frame 40/100", "wait": 0.1}   report how far it is (all keys optional)
and its return value is the result. Cancelling a running generator closes it: GeneratorExit is raised at its yield,
so a `try/finally` in the op can clean up (delete a scratch actor, restore a cvar). A plain call cannot be cancelled
once it runs; a queued one always can.

This module does not import `unreal`: the server passes in how to run a job and how to make a result JSON-safe, so
it is tested without the engine (tools/tests/test_fmbridge_jobs.py)."""
from __future__ import annotations

import inspect
import io
import json
import os
import sys
import threading
import time
import traceback
import uuid

STATES = ("queued", "running", "done", "failed", "cancelled", "lost")
FINISHED = ("done", "failed", "cancelled", "lost")
KEEP_SECONDS = 24 * 3600  # finished jobs answer this long, in memory and in the journal
KEEP_JOBS = 500
STDOUT_MAX = 200_000  # characters of a job's printed output kept (the tail)


class Job:
    __slots__ = ("id", "kind", "name", "state", "created", "started", "finished", "progress", "message", "result",
                 "error", "stdout", "cancel", "gen", "buf", "wake", "event", "payload", "detail")

    def __init__(self, kind: str, payload: dict):
        self.id = uuid.uuid4().hex[:12]
        self.kind, self.payload = kind, payload
        self.name = payload.get("name") if kind == "op" else payload.get("name", "exec")
        self.state, self.created, self.started, self.finished = "queued", time.time(), None, None
        self.progress, self.message, self.result, self.error, self.stdout = None, "", None, None, ""
        self.cancel, self.gen, self.buf, self.wake, self.detail = False, None, None, 0.0, None
        self.event = threading.Event()

    def view(self, full: bool = True) -> dict:
        """What a client sees. `ok`/`result`/`error`/`stdout`/`ms` keep the shape a synchronous call has always had."""
        end = self.finished or time.time()
        v = {"id": self.id, "job": self.id, "kind": self.kind, "name": self.name, "state": self.state,
             "done": self.state in FINISHED, "created": self.created, "started": self.started,
             "finished": self.finished, "progress": self.progress, "message": self.message,
             "ms": int((end - (self.started or self.created)) * 1000)}
        if self.state in FINISHED:
            v["ok"] = self.state == "done"
            if full:
                v.update(result=self.result, stdout=self.stdout)
            if self.error:
                v["error"] = self.error
            if self.detail:
                v.update(self.detail)  # a structured failure: code, message, hint, candidates
        return v

    @classmethod
    def from_record(cls, rec: dict) -> "Job":
        j = cls.__new__(cls)
        for k in cls.__slots__:
            setattr(j, k, None)
        j.id, j.kind, j.name, j.state = rec["id"], rec.get("kind", "op"), rec.get("name"), rec.get("state", "lost")
        j.created, j.started, j.finished = rec.get("created", 0), rec.get("started"), rec.get("finished")
        j.progress, j.message = rec.get("progress"), rec.get("message", "")
        j.result, j.error, j.stdout = rec.get("result"), rec.get("error"), rec.get("stdout", "")
        j.cancel, j.wake, j.payload = False, 0.0, {}
        j.detail = {k: rec[k] for k in ("code", "hint", "candidates") if k in rec} or None
        j.event = threading.Event()
        j.event.set()
        return j


class Registry:
    """The jobs of one bridge. `run(kind, payload)` runs a job's code on the game thread and returns its value (a
    generator for a multi-tick job); `jsonable(value)` makes a result JSON-safe; `journal` is a folder for finished
    jobs (None: memory only)."""

    def __init__(self, run, jsonable=lambda v: v, journal: str | None = None, clock=time.time, failure=None):
        self._run, self._jsonable, self._journal, self._clock = run, jsonable, journal, clock
        self._failure = failure  # exc -> dict of extra fields for a failed job (code, hint, candidates): fmbridge.errors
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._queue: list[Job] = []
        self._active: list[Job] = []
        if journal:
            self._load()

    # ---------------------------------------------------------------------------------------------- any thread
    def submit(self, kind: str, payload: dict) -> Job:
        job = Job(kind, payload)
        job.created = self._clock()
        with self._lock:
            self._prune()
            self._jobs[job.id] = job
            self._queue.append(job)
        return job

    def wait(self, job: Job, timeout: float) -> bool:
        """Block (an HTTP thread, never the game thread) until the job has finished; False on timeout."""
        return job.event.wait(timeout)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, state: str = "", name: str = "", limit: int = 50) -> list[dict]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)
        out = [j.view(full=False) for j in jobs if (not state or j.state == state) and (not name or (j.name or "").startswith(name))]
        return out[:limit]

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return {"ok": False, "error": f"no job {job_id} (finished jobs are kept {KEEP_SECONDS // 3600} h; list: GET /jobs)"}
            if job.state in FINISHED:
                return {"ok": True, "state": job.state, "note": "already finished"}
            if job.state == "queued":
                self._queue.remove(job)
                self._finish(job, "cancelled", error="cancelled before it started")
                return {"ok": True, "state": "cancelled"}
            if job.gen is None:
                return {"ok": False, "state": job.state, "error": "a one-step job cannot be stopped once it runs"}
            job.cancel = True  # the game thread closes the generator at its next step
            return {"ok": True, "state": "cancelling"}

    def counts(self) -> dict:
        with self._lock:
            return {"queued": len(self._queue), "running": len(self._active)}

    def shutdown(self, reason: str = "the bridge stopped") -> None:
        """Answer everything still queued or running (a client waiting on it must not hang) and journal it."""
        with self._lock:
            for job in self._queue:
                self._finish(job, "cancelled", error=f"{reason} before this ran; send it again")
            for job in self._active:
                if job.gen is not None:
                    try:
                        job.gen.close()
                    except Exception:
                        pass
                self._finish(job, "lost", error=f"{reason} while this ran")
            self._queue.clear()
            self._active.clear()

    # ------------------------------------------------------------------------------------------- game thread
    def tick(self, budget: float = 0.25) -> None:
        """Advance multi-tick jobs one step each (those whose wait has passed), then start queued jobs for up to
        `budget` seconds."""
        now = self._clock()
        with self._lock:
            active = list(self._active)
        for job in active:
            if job.cancel:
                self._close(job)
            elif job.wake <= now:
                self._step(job)
        end = self._clock() + budget
        while self._clock() < end:
            with self._lock:
                if not self._queue:
                    return
                job = self._queue.pop(0)
                job.state, job.started = "running", self._clock()
            self._start(job)

    def _capture(self, job: Job):
        saved = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = job.buf
        return saved

    def _start(self, job: Job) -> None:
        job.buf = io.StringIO()
        saved = self._capture(job)
        try:
            res = self._run(job.kind, job.payload)
            if inspect.isgenerator(res):
                job.gen = res
                with self._lock:
                    self._active.append(job)
                sys.stdout, sys.stderr = saved
                self._step(job)  # to its first yield now: progress shows at once, and a cancel runs its finally
                return
            self._finish(job, "done", result=self._jsonable(res))
        except Exception as e:
            self._fail(job, e)
        finally:
            sys.stdout, sys.stderr = saved

    def _fail(self, job: Job, exc: BaseException) -> None:
        if self._failure is not None:
            try:
                job.detail = self._failure(exc) or None
            except Exception:
                job.detail = None
        self._finish(job, "failed", error=traceback.format_exc())

    def _step(self, job: Job) -> None:
        saved = self._capture(job)
        try:
            got = next(job.gen)
            wait = 0.0
            if isinstance(got, dict):
                if "progress" in got:
                    job.progress = got["progress"]
                if "message" in got:
                    job.message = str(got["message"])
                wait = float(got.get("wait") or 0.0)
            elif isinstance(got, (int, float)) and not isinstance(got, bool):
                wait = float(got)
            job.wake = self._clock() + wait
            return
        except StopIteration as e:
            self._finish(job, "done", result=self._jsonable(e.value))
        except Exception as e:
            self._fail(job, e)
        finally:
            sys.stdout, sys.stderr = saved
        with self._lock:
            if job in self._active:
                self._active.remove(job)

    def _close(self, job: Job) -> None:
        saved = self._capture(job)
        try:
            job.gen.close()  # GeneratorExit at its yield: its finally blocks run
            self._finish(job, "cancelled", error="cancelled")
        except Exception:
            self._finish(job, "failed", error="cancelled, and its clean-up failed:\n" + traceback.format_exc())
        finally:
            sys.stdout, sys.stderr = saved
        with self._lock:
            if job in self._active:
                self._active.remove(job)

    def _finish(self, job: Job, state: str, result=None, error: str | None = None) -> None:
        job.state, job.finished, job.result, job.error = state, self._clock(), result, error
        if job.buf is not None:
            out = job.buf.getvalue()
            job.stdout = out[-STDOUT_MAX:]
        job.gen, job.buf = None, None
        self._write(job)
        job.event.set()

    # ------------------------------------------------------------------------------------------------ journal
    def _record(self, job: Job) -> dict:
        v = job.view()
        v.pop("job", None)
        v.pop("done", None)
        v.pop("ok", None)
        v.pop("ms", None)
        return v

    def _write(self, job: Job) -> None:
        if not self._journal:
            return
        try:
            os.makedirs(self._journal, exist_ok=True)
            tmp = os.path.join(self._journal, f".{job.id}.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._record(job), f, default=str)
            os.replace(tmp, os.path.join(self._journal, f"{job.id}.json"))
        except (OSError, TypeError, ValueError):
            pass  # the journal is a convenience: a result that cannot be written still answers from memory

    def _load(self) -> None:
        try:
            names = os.listdir(self._journal)
        except OSError:
            return
        cutoff = self._clock() - KEEP_SECONDS
        for n in names:
            if not n.endswith(".json"):
                continue
            p = os.path.join(self._journal, n)
            try:
                with open(p, encoding="utf-8") as f:
                    rec = json.load(f)
                if (rec.get("finished") or rec.get("created") or 0) < cutoff:
                    os.remove(p)
                    continue
                self._jobs[rec["id"]] = Job.from_record(rec)
            except (OSError, ValueError, KeyError):
                continue

    def _prune(self) -> None:
        cutoff = self._clock() - KEEP_SECONDS
        done = sorted((j for j in self._jobs.values() if j.state in FINISHED), key=lambda j: j.finished or 0)
        excess = max(0, len(self._jobs) - KEEP_JOBS)
        for j in done:
            if (j.finished or 0) < cutoff or excess > 0:
                del self._jobs[j.id]
                excess -= 1
                if self._journal:
                    try:
                        os.remove(os.path.join(self._journal, f"{j.id}.json"))
                    except OSError:
                        pass
