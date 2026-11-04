"""The bridge itself, as an op (the same answers as GET /health, for clients that only speak /op)."""
from __future__ import annotations

from . import op


@op("bridge.health", mutates=False, idempotent=True, tags=["platform"])
def health() -> dict:
    """The bridge's state: engine, platform, project, uptime, protocol version, jobs, memory, idle cap, seconds
    since the last tick (a large value means the game thread is stuck).

    Returns: the /health dict: {"ok", "engine", "platform", "project", "uptime", "bridge", "python", "pid", "rss_mb",
    "jobs", "idle_fps", "throttle_off", "last_tick_s", "idle_s"}.
    Example: film-ue op bridge.health
    """
    from .. import server
    return server.health()
