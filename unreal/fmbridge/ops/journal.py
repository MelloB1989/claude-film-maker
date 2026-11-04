"""The op journal (BACKLOG B32): every op that changes something is appended, with its arguments, how long it took
and what it returned, to Saved/fmbridge/journal.jsonl on the box. Read it to see what was done to a level (by you,
a spec, a script, a teammate); replay it on a fresh level to rebuild one.

Recorded: ops whose `mutates` flag is True or unset (unset: assumed to change things), except journal.*, selftest.*
and ops.*. A multi-tick op is recorded when it starts (`"job": true`, no result). Failures are not recorded."""
from __future__ import annotations

import inspect
import json
import os
import time

import unreal

from . import op
from ..errors import OpError

SKIP = ("journal.", "selftest.", "ops.", "list")
MAX_BYTES = 50 * 1024 * 1024       # past this the journal is rotated to journal.1.jsonl
MAX_FIELD = 4000                   # characters kept of an argument or result (bigger ones are cut, marked "...")
_state = {"on": True, "path": None}
_pending: dict = {}  # id(generator) -> its journal key, until the job finishes


def path() -> str:
    if not _state["path"]:
        saved = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
        _state["path"] = os.path.join(saved, "fmbridge", "journal.jsonl").replace("\\", "/")
    return _state["path"]


def _small(v):
    try:
        text = json.dumps(v, default=str)
    except (TypeError, ValueError):
        text = json.dumps(str(v))
    if len(text) <= MAX_FIELD:
        return json.loads(text)
    return {"truncated": text[:MAX_FIELD] + "..."}


def _level() -> str:
    try:
        w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        return w.get_path_name().split(".")[0] if w else ""
    except Exception:
        return ""


def record(op_name: str, args: dict, result, seconds: float, meta: dict) -> None:
    """The ops.call hook: append one line for a mutating op."""
    if not _state["on"] or op_name.startswith(SKIP) or (meta or {}).get("mutates") is False:
        return
    entry = {"t": round(time.time(), 3), "op": op_name, "args": _small(args), "ms": int(seconds * 1000),
             "level": _level()}
    if inspect.isgenerator(result):
        entry["job"] = True
        entry["gen"] = f"{id(result):x}"
        _pending[id(result)] = entry["gen"]
    else:
        entry["result"] = _small(result)
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.exists(p) and os.path.getsize(p) > MAX_BYTES:
        os.replace(p, p.replace(".jsonl", ".1.jsonl"))
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def finished(gen, view: dict) -> None:
    """The job registry's finish hook: a multi-tick op's outcome, as a second line pointing at its start (`gen`)."""
    key = _pending.pop(id(gen), None)
    if key is None or not _state["on"]:
        return
    entry = {"t": round(time.time(), 3), "finished": key, "op": view.get("name") or view.get("op", ""),
             "state": view.get("state"), "result": _small(view.get("result")), "ms": view.get("ms")}
    if view.get("error"):
        entry["error"] = str(view["error"])[-1000:]
    with open(path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _install() -> bool:
    from .. import ops
    hook = getattr(ops, "after_call", None)
    if hook is None:
        return False
    if record not in getattr(ops, "_AFTER", []):
        hook(record)
    try:
        from .. import jobs
        if hasattr(jobs, "on_finish") and finished not in getattr(jobs, "_ON_FINISH", []):
            jobs.on_finish(finished)
    except ImportError:
        pass
    return True


HOOKED = _install()


def _read(limit: int = 0, prefix: str = "", since: float = 0.0) -> list:
    p = path()
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if "finished" in e:  # a job's outcome: folded into its start line
                for s_ in reversed(out):
                    if s_.get("gen") == e["finished"]:
                        s_.update(state=e.get("state"), result=e.get("result"), job_ms=e.get("ms"))
                        break
                continue
            if e.get("op", "").startswith(prefix) and e.get("t", 0) >= since:
                out.append(e)
    return out[-limit:] if limit else out


@op("journal.tail", mutates=False, idempotent=True)
def tail(*, n: int = 30, prefix: str = "", since_s: float = 0.0) -> dict:
    """The last `n` journal entries (ops that changed something), oldest first: {"entries": [{"t", "op", "args", "ms",
    "level", "result" | "job"}], "path", "recording"}. `prefix` keeps one area ("level."); `since_s` only the entries
    newer than that many seconds ago.

    Example: film-ue journal tail --n 20 --prefix level.
    """
    since = time.time() - since_s if since_s else 0.0
    return {"entries": _read(n, prefix, since), "path": path(), "recording": HOOKED and _state["on"]}


@op("journal.clear", mutates=True, idempotent=True)
def clear() -> dict:
    """Empty the journal (start a fresh record, e.g. before building a level you will want to replay).

    Example: film-ue journal clear
    """
    p = path()
    had = os.path.exists(p) and os.path.getsize(p) > 0
    if had:
        open(p, "w").close()
    return {"changed": had, "path": p}


@op("journal.record", mutates=False, idempotent=True)
def set_recording(*, on: bool = True) -> dict:
    """Turn journaling on or off for this editor session (it is on at start). Returns {"recording", "hooked"}.

    Example: film-ue journal record --no-on
    """
    _state["on"] = bool(on)
    return {"recording": _state["on"], "hooked": HOOKED}


@op("journal.replay", mutates=True, idempotent=False, tags=["slow"])
def replay(*, entries: list | None = None, prefix: str = "", since_s: float = 0.0, dry_run: bool = False,
           keep_going: bool = False):
    """Run journal entries again, in order (all, or `entries` as journal.tail gives them, or those matching `prefix`
    / `since_s`): rebuild a level from its record. Multi-tick. A failing entry stops the replay unless `keep_going`.
    Returns {"ran", "failed": [{"i", "op", "error"}], "skipped_jobs"} (`dry_run`: what would run).

    Example: film-ue journal replay --prefix level. --dry-run
    """
    from .. import ops
    todo = entries if entries is not None else _read(0, prefix, time.time() - since_s if since_s else 0.0)
    if dry_run:
        return {"would_run": [{"op": e["op"], "args": e.get("args")} for e in todo], "count": len(todo)}
    ran, failed = 0, []
    for i, e in enumerate(todo):
        args = e.get("args") or {}
        if isinstance(args, dict) and "truncated" in args:
            failed.append({"i": i, "op": e["op"], "error": "arguments were too big to journal; cannot replay"})
            if not keep_going:
                break
            continue
        try:
            res = ops.call(e["op"], **args)
            if inspect.isgenerator(res):
                yield from res
            ran += 1
        except Exception as ex:
            failed.append({"i": i, "op": e["op"], "error": str(ex)[:500]})
            if not keep_going:
                break
        yield  # one entry per tick: the editor stays responsive
    if failed and not keep_going and not ran:
        raise OpError(f"replay stopped at entry {failed[0]['i']} ({failed[0]['op']}): {failed[0]['error']}",
                      code="failed", hint="journal.tail shows it; keep_going=True runs the rest")
    return {"ran": ran, "failed": failed, "count": len(todo)}
