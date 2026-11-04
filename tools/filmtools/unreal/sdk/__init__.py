"""filmtools.unreal.sdk: the bridge's ops as typed Python, generated from the op schema (filmtools.unreal.schema).

    from filmtools.unreal.sdk import Unreal, OpError
    ue = Unreal()                                    # the workstation film-ue talks to (FILM_UE_BOX / --box)
    ue.seq.new(path="/Game/Demo/Seq", end=96)        # every op is ue.<area>.<verb>(**keyword args) -> its result
    job = ue.render.mrq(..., wait=False)             # a long op: a Job; job.wait() for its result
    ue.describe("look.light")                        # the op's signature and docstring, offline
    try:
        ue.level.move(label="Kye", loc=[0, 0, 300])
    except OpError as e:
        print(e.code, e.message, e.hint, e.candidates)

Arguments are keyword-only and spelled as the op spells them (`rot_`, `cls`); `assets.import` is `ue.assets.import_`.
An argument left out takes the op's own default on the bridge. `ue.call("area.verb", **args)` reaches an op this
checkout's SDK does not know (a newer bridge). The typed areas are generated from this checkout's ops when the SDK
loads (in memory, or from sdk/_generated.py when `film-ue dx gen` wrote a current one): they never lag the ops.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from .. import errors, schema as _schema

__all__ = ["Unreal", "OpError", "Job", "UNSET"]


class _Unset:
    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET: Any = _Unset()


class OpError(RuntimeError):
    """An op that failed, with what to do about it: code, message, hint, candidates, and the bridge's detail."""

    def __init__(self, problem: errors.Problem, op: str = "", stdout: str = ""):
        super().__init__(problem.text())
        self.problem, self.op, self.stdout = problem, op, stdout
        self.code, self.message, self.hint = problem.code, problem.message, problem.hint
        self.candidates, self.detail, self.job = problem.candidates, problem.detail, problem.job


def _client_transport(kind: str, payload: dict, timeout: float) -> dict:
    from .. import client
    if kind == "op":
        return client.op(payload["name"], timeout=timeout, wait=not payload.get("async"), **payload["args"])
    if kind == "exec":
        return client.exec_code(payload["code"], timeout, wait=not payload.get("async"))
    if kind == "job":
        if hasattr(client, "job"):  # WP1's client: retries through a dropped tunnel or a reloaded bridge
            gone = getattr(client, "JobGone", None)
            try:
                return client.job(payload["id"])
            except Exception as e:
                if gone is not None and isinstance(e, gone):  # the editor restarted (crashed?) while it ran
                    return {"id": payload["id"], "state": "lost", "done": True, "ok": False, "code": "job_lost",
                            "message": str(e.code if isinstance(e, SystemExit) else e),
                            "hint": "film-ue editor status / film-ue editor crashes; then start the op again"}
                raise
        return json.loads(client.request("GET", f"/job?id={payload['id']}", timeout=60))
    if kind == "cancel":
        if hasattr(client, "cancel"):
            return client.cancel(payload["id"])
        return client.call("/job/cancel", {"id": payload["id"]}, 60)
    if kind == "health":
        return client.health()
    raise ValueError(kind)


class Job:
    """An op started with wait=False: poll() its state, wait() for its result."""

    def __init__(self, ue: "Unreal", job_id: str, op: str = ""):
        self.ue, self.id, self.op = ue, job_id, op

    def poll(self) -> dict:
        """{id, state: queued|running|done|failed|cancelled|lost, done, ok, progress, message, result, error, ...}"""
        return self.ue._transport("job", {"id": self.id}, 60)

    def cancel(self) -> dict:
        return self.ue._transport("cancel", {"id": self.id}, 60)

    def wait(self, timeout: float = 3600, every: float = 2.0, on_progress: Callable[[dict], None] | None = None):
        """The job's result once it is done; OpError when it failed, was cancelled or lost, or ran past `timeout`."""
        end = time.time() + timeout
        while True:
            r = self.poll()
            if on_progress and (r.get("progress") is not None or r.get("message")):
                on_progress(r)
            if r.get("state") in ("cancelled", "lost") and not r.get("error"):
                r = {**r, "ok": False, "error": f"job {self.id} {r['state']}",
                     "hint": "start it again" + (" (the bridge restarted)" if r["state"] == "lost" else ""),
                     "code": "job_" + r["state"], "message": f"job {self.id} was {r['state']}"}
            if r.get("done") or r.get("state") in ("done", "failed", "cancelled", "lost"):
                return self.ue._result(r, self.op, {})
            if time.time() > end:
                raise OpError(errors.Problem("timeout", f"job {self.id} still running after {timeout}s",
                                             f"film-ue job {self.id} --wait", job=self.id), self.op)
            time.sleep(every)

    def __repr__(self) -> str:
        return f"Job({self.id!r}, op={self.op!r})"


class _Area:
    _area = ""

    def __init__(self, ue: "Unreal"):
        self._ue = ue

    def _call(self, op: str, args: dict, wait: bool, timeout: float):
        return self._ue.call(op, wait=wait, timeout=timeout, **{k: v for k, v in args.items() if v is not UNSET})

    def __repr__(self) -> str:
        return f"<ue.{self._area}: {', '.join(n for n in dir(self) if not n.startswith('_'))}>"


_GEN: dict = {}


def generated():
    """The typed areas for the ops in this checkout: sdk/_generated.py when it matches the current op schema, else
    generated in memory from it (so the SDK never lags the ops; `film-ue dx gen` writes the file to read)."""
    if "mod" in _GEN:
        return _GEN["mod"]
    import types
    from . import gen
    ix = _schema.index(_schema.load())
    mod = None
    try:
        from . import _generated as mod
        if getattr(mod, "FINGERPRINT", "") != ix["fingerprint"]:
            mod = None
    except ImportError:
        mod = None
    if mod is None:
        mod = types.ModuleType(__name__ + "._generated")
        mod.__package__ = __name__
        exec(compile(gen.generate(ix), "<filmtools.unreal.sdk generated>", "exec"), mod.__dict__)
    _GEN["mod"] = mod
    return mod


class Unreal:
    """The bridge as typed areas (ue.seq, ue.level, ...). `transport(kind, payload, timeout) -> dict` is the wire
    (default: filmtools.unreal.client, i.e. film-ue's workstation); tests pass a fake. `check` validates argument
    names against the schema before sending (an unknown name fails here, with candidates, not on the box)."""

    def __init__(self, transport: Callable[[str, dict, float], dict] | None = None, check: bool = True,
                 log: Callable[[str], None] | None = None):
        self._transport = transport or _client_transport
        self._check = check
        self._log = log
        self._index = None
        for area, cls in generated().AREAS.items():
            setattr(self, area, cls(self))

    @property
    def index(self) -> dict:
        if self._index is None:
            self._index = _schema.index(_schema.load())
        return self._index

    def call(self, op: str, /, *, wait: bool = True, timeout: float = 900, **args):
        """Call any op by name. Returns its result; a Job when wait=False; raises OpError when it fails."""
        if self._check and op in self.index["ops"]:
            p = errors.check_args(op, args, self.index)
            if p:
                raise OpError(p, op)
        res = self._transport("op", {"name": op, "args": args, "async": not wait}, timeout)
        if not wait and res.get("ok") and res.get("job"):
            return Job(self, res["job"], op)
        return self._result(res, op, args)

    def _result(self, res: dict, op: str, args: dict):
        if self._log and res.get("stdout"):
            self._log(res["stdout"])
        p = errors.explain(res, op, args, self._index)
        if p:
            raise OpError(p, op, res.get("stdout", ""))
        return res.get("result")

    def exec(self, code: str, timeout: float = 900):
        """Run Python in the editor; its `result` comes back."""
        return self._result(self._transport("exec", {"code": code}, timeout), "exec", {})

    def job(self, job_id: str) -> Job:
        return Job(self, job_id)

    def health(self) -> dict:
        return self._transport("health", {}, 30)

    def describe(self, name: str = "") -> str:
        from ..describe import text
        return text(self.index, name)
