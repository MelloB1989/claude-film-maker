"""WP1's acceptance test on a box: the bridge answers and ticks; editor.describe reports the engine, RHI, level and
memory; a console variable round-trips and converges; the console refuses what would lose the Epic sign-in; the idle
cap applies; shader compilation is waited out; garbage collection runs; jobs report progress, cancel with their
clean-up, survive in the journal and carry structured errors. Takes ~1 min (up to 30 min on a first open, while
shaders compile). Needs: nothing (no GPU, no Epic sign-in, no assets)."""
from __future__ import annotations

import os
import time

REQUIRES: list = []
AREAS = ["editor", "bridge", "jobs"]
NEEDS_LEVEL = False
TIMEOUT = 2400

JOB = """
import fmbridge
def job():
    fmbridge._selftest_platform = "running"
    try:
        for i in range(10000):
            yield {"progress": i / 10000, "message": f"step {i}", "wait": 0.05}
    finally:
        fmbridge._selftest_platform = "cleaned"
result = job()
"""


def _settle(reg, job_id, states, ticks=600):
    """Tick (yield) until the job reaches one of `states`."""
    for _ in range(ticks):
        j = reg.get(job_id)
        if j and j.state in states:
            return j
        yield
    return reg.get(job_id)


def run(t):
    import fmbridge
    from fmbridge import server

    # the bridge
    h = t.op("bridge.health")
    t.ok("bridge protocol 2", h.get("bridge") == 2, detail=str(h.get("bridge")))
    t.ok("engine version reported", str(h.get("engine", "")).startswith("5."), detail=str(h.get("engine")))
    t.ok("game thread ticking", (h.get("last_tick_s") or 0) < 5, detail=f"last tick {h.get('last_tick_s')} s ago")
    t.ok("background throttling off", h.get("throttle_off") is not False, detail=str(h.get("throttle_off")))
    if h.get("rss_mb") is not None:
        t.metric("editor_rss_mb", h["rss_mb"], "MB")

    # the editor
    d = t.op("editor.describe")
    for k in ("engine", "platform", "project", "level", "dirty", "max_fps", "jobs"):
        t.ok(f"describe has {k}", k in d)
    t.note(f"rhi: {d.get('rhi')}; level: {d.get('level')}; shader workers: {d.get('shader_workers')}")
    if d.get("platform", "").startswith("linux"):
        t.ok("Vulkan SM6 on Linux", "SM6" in str(d.get("rhi") or ""), detail=str(d.get("rhi")))

    before = t.op("editor.cvar", name="t.MaxFPS")["value"]
    r = t.op("editor.cvar", name="t.MaxFPS", value=17)
    t.check("cvar set reads back", r["value"].split(".")[0], "17")
    t.idempotent("cvar converges", "editor.cvar", name="t.MaxFPS", value=17)
    t.op("editor.cvar", name="t.MaxFPS", value=before or 0)
    t.raises("unknown cvar is not_found", "editor.cvar", code="not_found", name="r.FilmUeSelftestNoSuchCVar", value=1)
    t.raises("console refuses Fab.Logout", "editor.console", code="conflict", command="Fab.Logout")
    t.raises("console refuses quit", "editor.console", code="conflict", command="quit")
    t.ok("console runs a command", t.op("editor.console", command="stat none").get("ran") is True)

    r = t.op("editor.idle", fps=30, realtime=False)
    t.check("idle cap applied", t.op("editor.cvar", name="t.MaxFPS")["value"].split(".")[0], "30")
    t.idempotent("idle converges", "editor.idle", fps=30, realtime=False)

    t0 = time.time()
    w = yield from t.op("editor.wait_compile", timeout_s=1800, settle_s=4)
    t.ok("shaders compiled", w.get("finished") is True)
    t.metric("wait_compile_s", round(time.time() - t0, 1), "s")
    g = t.op("editor.gc")
    t.ok("gc ran", "rss_mb_after" in g)

    # jobs
    reg = server.registry()
    job = reg.submit("exec", {"code": JOB, "name": "selftest-platform-job"})
    j = yield from _settle(reg, job.id, ("running",))
    yield 0.3
    t.ok("job runs across ticks", j is not None and j.state == "running", detail=str(j and j.state))
    cur = reg.get(job.id)
    t.ok("job reports progress", cur.progress is not None and cur.message.startswith("step"),
         detail=f"{cur.progress} {cur.message}")
    t.ok("jobs.list finds it", job.id in [x["id"] for x in t.op("jobs.list", state="running")])
    t.ok("jobs.get sees it", t.op("jobs.get", id=job.id)["state"] == "running")
    t.ok("jobs.cancel accepted", t.op("jobs.cancel", id=job.id)["changed"] is True)
    j = yield from _settle(reg, job.id, ("cancelled", "failed"))
    t.check("cancelled", j.state if j else None, "cancelled")
    t.check("its finally ran", getattr(fmbridge, "_selftest_platform", None), "cleaned")
    t.ok("journaled", os.path.exists(os.path.join(server.JOURNAL, f"{job.id}.json")), detail=server.JOURNAL)
    t.raises("unknown job is not_found", "jobs.get", code="not_found", id="feedfacecafe")

    bad = reg.submit("op", {"name": "editor.cvar", "args": {"name": "two words"}})
    b = yield from _settle(reg, bad.id, ("failed", "done"))
    v = b.view() if b else {}
    t.check("a failed job carries its code", v.get("code"), "bad_args")
    t.ok("and the traceback", "Traceback" in (v.get("error") or ""))
    return {"engine": d.get("engine"), "rhi": d.get("rhi"), "wait_compile": w}
