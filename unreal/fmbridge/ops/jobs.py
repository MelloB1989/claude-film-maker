"""The bridge's jobs as ops (the same as GET /jobs, GET /job, POST /job/cancel, for clients that only speak /op)."""
from __future__ import annotations

from . import op
from ..errors import OpError, not_found


@op("jobs.list", mutates=False, idempotent=True, tags=["platform"])
def list_jobs(*, state: str = "", name: str = "", limit: int = 50) -> list:
    """Recent jobs, newest first, without their results.

    Args: state: queued|running|done|failed|cancelled|lost ("" = all). name: an op-name prefix ("render."). limit.
    Returns: [{"id", "name", "state", "progress", "message", "created", "started", "finished", "ms"}].
    Example: film-ue op jobs.list state=running
    """
    from .. import jobs as _jobs, server
    if state and state not in _jobs.STATES:
        raise OpError(f"no job state {state!r}", code="bad_args", candidates=list(_jobs.STATES))
    return server.registry().list(state, name, int(limit))


@op("jobs.get", mutates=False, idempotent=True, tags=["platform"])
def get(*, id: str) -> dict:  # noqa: A002 (the job's id, as the HTTP API names it)
    """One job: its state and progress, and when finished its result or error.

    Args: id: the job id (from an async call or jobs.list).
    Returns: the job: {"id", "state", "done", "ok", "result", "error", "progress", "message", ...}.
    Example: film-ue op jobs.get id=3f2a9c1b0d4e
    """
    from .. import server
    reg = server.registry()
    job = reg.get(id)
    if not job:
        raise not_found("job", id, [j["id"] for j in reg.list(limit=200)], hint="jobs.list shows recent ones")
    return job.view()


@op("jobs.cancel", mutates=True, idempotent=True, tags=["platform"])
def cancel(*, id: str) -> dict:  # noqa: A002
    """Cancel a queued job, or a running multi-tick one (it stops at its next step and runs its clean-up).

    Args: id: the job id.
    Returns: {"ok", "state", "changed"}.
    Example: film-ue op jobs.cancel id=3f2a9c1b0d4e
    """
    from .. import server
    r = server.registry().cancel(id)
    if not r.get("ok") and "no job" in r.get("error", ""):
        raise OpError(r["error"], code="not_found", hint="jobs.list shows recent ones")
    return {**r, "changed": r.get("state") in ("cancelled", "cancelling") and r.get("note") != "already finished"}
