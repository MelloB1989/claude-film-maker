"""WP1's client phase, after the bridge phase (unreal/fmbridge/selftest/platform.py): the operator side against the
real box. Files round-trip through the bridge and through the command channel (one big enough to go in parts); a job
started over HTTP reports progress, survives the tunnel being dropped mid-wait, and cancels; a batch runs in order
and stops at a failure; an unknown job is JobGone; the editor service, crash reports, the box watchdog and a sync
plan answer. Nothing here restarts the editor (that would end the selftest). Takes ~1 min over SSM. Needs: nothing."""
from __future__ import annotations

import hashlib
import os
import tempfile
import time

from .. import client, editorsvc, sync
from .. import workstation as ws

JOB = """
def job():
    for i in range(100000):
        yield {"progress": i / 100000, "message": f"tick {i}", "wait": 0.05}
result = job()
"""


def run(ue, t):
    h = client.health(retry_s=30)
    t.check("bridge protocol", h.get("bridge"), 2)
    t.note(f"box: {ws.box() or 'default'} ({ws.conf().get('transport') or 'ssm'}, {ws.conf().get('os')}), "
           f"engine {h.get('engine')}")

    # files: through the bridge, and through the box's own command channel (in parts when big)
    data = os.urandom(150_000)
    remote = ws.project("Saved", "Bridge", "selftest", f"{t.prefix}blob.bin")
    with tempfile.TemporaryDirectory() as d:
        src, back = os.path.join(d, "src.bin"), os.path.join(d, "back.bin")
        with open(src, "wb") as f:
            f.write(data)
        t0 = time.time()
        client.push(src, remote)
        client.pull(remote, back)
        with open(back, "rb") as f:
            t.check("bridge file round trip", hashlib.sha256(f.read()).hexdigest(), hashlib.sha256(data).hexdigest())
        t.metric("bridge_150kb_round_trip_s", round(time.time() - t0, 2), "s")
    t0 = time.time()
    tr = ws.transport()
    tr.put(remote + ".2", data)
    got = tr.get(remote + ".2")
    t.check("command-channel file round trip (in parts)", hashlib.sha256(got or b"").hexdigest(),
            hashlib.sha256(data).hexdigest())
    t.metric("transport_150kb_round_trip_s", round(time.time() - t0, 2), "s")

    # jobs over HTTP
    jid = client.submit_exec(JOB, name="selftest-platform-client")
    seen = []
    r = client.wait(jid, timeout=3, on_progress=lambda j: seen.append(j.get("message")))
    t.ok("a long job is still running after a short wait", r.get("state") == "running", detail=str(r)[:300])
    t.ok("its progress came back", any(m and m.startswith("tick") for m in seen), detail=str(seen[-3:]))
    if (ws.conf().get("bridge") != "ssm") and ws.conf().get("transport") != "local":
        client.close_tunnel()  # drop the connection: the next poll reopens it
        t.ok("polling survives a dropped tunnel", client.job(jid, retry_s=60).get("state") == "running")
    t.ok("listed as running", jid in [j["id"] for j in client.jobs(state="running")])
    t.ok("cancel accepted", client.cancel(jid).get("state") in ("cancelling", "cancelled"))
    t.check("cancelled", client.wait(jid, timeout=60).get("state"), "cancelled")
    try:
        client.wait("feedfacecafe", timeout=10)
        t.ok("an unknown job is JobGone", False)
    except client.JobGone:
        t.ok("an unknown job is JobGone", True)

    # batch
    b = client.batch([("editor.cvar", {"name": "t.MaxFPS"}), ("bridge.nope", {}), ("bridge.health", {})])
    res = b.get("result") or {}
    t.check("batch stops at the failure", (res.get("ran"), res.get("of")), (2, 3))
    t.check("and says why", (res.get("results") or [{}, {}])[1].get("code"), "not_found")

    # the editor as a service, the box, a sync plan
    st = editorsvc.status()
    t.ok("editor status answers", bool(st.get("bridge", {}).get("ok")), detail=str(st.get("unit"))[:300])
    t.ok("crash reports readable", isinstance(editorsvc.crashes(3), list))
    if st.get("watchdog") is not None:
        t.note(f"watchdog: {st['watchdog']}")
    if ws.linux() and ws.conf().get("bucket"):
        plan = sync.project("up", dry_run=True)
        t.ok("sync plan (dry run)", "aws s3 sync" in plan["script"], detail=plan["s3"])
    tr.run(f"rm -f {remote}.2" if ws.linux() else f"Remove-Item -Force '{remote}.2'", 60)
    return {"bridge_rss_mb": h.get("rss_mb")}
