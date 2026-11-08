"""The queue: a farm's jobs and their chunks in S3, claimed with leases that the holder renews (heartbeats) and
anyone may take over once they expire. A worker that dies (a spot reclaim, a crash) stops renewing, and its chunk
goes back to the queue on its own.

    s3://<bucket>/<root>/                     root = farm/<farm>/<job>/ (ids, sizes, hashes: never a frame)
      job.json                                the validated job
      chunks.json                             the plan: [{"id", "start", "end", "render_from", "preroll", ...}]
      c/<chunk>/lease.json                    {"worker", "attempt", "expires", "claimed", "beat", "state"}
      c/<chunk>/progress/<worker>.json        {frame: [size, sha256]} uploaded so far by that worker
      c/<chunk>/done.json                     written once (If-None-Match): {"worker", "frames": {frame: [size, sha]}}
      c/<chunk>/failed.json                   the chunk ran out of attempts
      workers/<worker>.json                   the worker's last word: chunk, fps, frames, sessions (for cost)
      logs/<worker>.log
    s3://<bucket>/farm/<farm>/farm.json       the farm: its jobs (id, root, privacy), its workers

Every write that decides who owns what is conditional (store.py), so two workers can never both hold a chunk: a
claim creates lease.json only if absent, a renewal or a takeover replaces it only if its etag is unchanged.
Python 3.10, stdlib only: it runs on the workers.
"""
from __future__ import annotations

import json
import time

from . import model
from .store import PreconditionFailed, Store

LEASE_S = 180       # a lease not renewed for this long is free to take over
BEAT_S = 30         # how often a holder renews it


def farm_key(farm: str) -> str:
    return f"farm/{farm}/farm.json"


def job_root(farm: str, job: dict, private_root: str = "ue-linux/private/") -> str:
    """Where a job's queue lives: farm/<farm>/<job>/ for every job. It holds ids, frame numbers, sizes, hashes and
    timings, never a frame. A private job's FRAMES go only under its private output prefix. The queue stays outside
    private/ on purpose: the bucket lets only the box role read private/, and the machine running film-farm must
    read the queue."""
    return f"farm/{farm}/{job['id']}/"


class Queue:
    def __init__(self, store: Store, farm: str, clock=time.time, private_root: str = "ue-linux/private/"):
        if not model.ID_RE.match(farm):
            raise model.JobError(f"farm id {farm!r}: lower-case letters, digits, - and _")
        self.s, self.farm, self.now, self.private_root = store, farm, clock, private_root

    # --- the farm and its jobs ------------------------------------------------------------------------------------
    def farm_doc(self) -> tuple[dict, str | None]:
        doc, etag = self.s.get_json(farm_key(self.farm))
        return (doc or {"farm": self.farm, "jobs": [], "workers": {}}), etag

    def update_farm(self, fn, tries: int = 20) -> dict:
        """Read-modify-write farm.json under its etag (retried when someone else wrote in between)."""
        for _ in range(tries):
            doc, etag = self.farm_doc()
            new = fn(json.loads(json.dumps(doc)))
            try:
                if etag is None:
                    self.s.put_json(farm_key(self.farm), new, if_none_match=True)
                else:
                    self.s.put_json(farm_key(self.farm), new, if_match=etag)
                return new
            except PreconditionFailed:
                time.sleep(0.05)
        raise RuntimeError("farm.json: too many concurrent writers")

    def submit(self, job: dict, workers: int = 1, bucket: str = "") -> dict:
        """Validate a job, plan its chunks and put it on the queue. A job id already there must be the same job
        (submitting again is a no-op), so a retried submit cannot double the work."""
        j = model.validate(job, bucket=bucket or self.s.bucket, private_root=self.private_root)
        if model.split_s3(j["output"]["prefix"])[0] != self.s.bucket:
            raise model.JobError(f"output prefix {j['output']['prefix']}: the farm writes to its own bucket, "
                                 f"s3://{self.s.bucket}/")
        root = job_root(self.farm, j, self.private_root)
        old, _ = self.s.get_json(root + "job.json")
        if old is not None:
            if old != j:
                raise model.JobError(f"job {j['id']} is already on farm {self.farm} with other settings: "
                                     "give the new one another id")
            return {"job": j["id"], "root": root, "chunks": len(self.chunks(root)), "new": False}
        chunks = model.plan_chunks(j, workers)
        errs = model.check_cover(chunks, j["frames"])
        if errs:
            raise model.JobError(f"chunk plan: {errs}")
        self.s.put_json(root + "chunks.json", chunks)
        self.s.put_json(root + "job.json", j, if_none_match=True)

        def add(doc):
            if not any(x["id"] == j["id"] for x in doc["jobs"]):
                doc["jobs"].append({"id": j["id"], "root": root, "privacy": j["privacy"], "engine": j["engine"],
                                    "frames": j["frames"], "submitted": int(self.now()), "state": "queued"})
            return doc
        self.update_farm(add)
        return {"job": j["id"], "root": root, "chunks": len(chunks), "new": True}

    def jobs(self) -> list[dict]:
        return [x for x in self.farm_doc()[0]["jobs"] if x.get("state") != "cancelled"]

    def job(self, root: str) -> dict:
        doc, _ = self.s.get_json(root + "job.json")
        if doc is None:
            raise model.JobError(f"no job at {root}")
        return doc

    def chunks(self, root: str) -> list[dict]:
        doc, _ = self.s.get_json(root + "chunks.json")
        return doc or []

    def set_job_state(self, job_id: str, state: str) -> None:
        def f(doc):
            for x in doc["jobs"]:
                if x["id"] == job_id:
                    x["state"] = state
            return doc
        self.update_farm(f)

    # --- chunk state ------------------------------------------------------------------------------------------------
    def state(self, root: str) -> dict:
        """Every chunk's state from one listing: {chunk: {"done", "failed", "lease"(etag) , "progress": [keys]}}."""
        out: dict = {}
        for o in self.s.list(root + "c/"):
            rest = o["key"][len(root) + 2:]
            cid, _, name = rest.partition("/")
            st = out.setdefault(cid, {"done": False, "failed": False, "lease": None, "progress": []})
            if name == "done.json":
                st["done"] = True
            elif name == "failed.json":
                st["failed"] = True
            elif name == "lease.json":
                st["lease"] = o["etag"]
            elif name.startswith("progress/"):
                st["progress"].append(o["key"])
        return out

    def lease(self, root: str, cid: str):
        return self.s.get_json(f"{root}c/{cid}/lease.json")

    def claim(self, root: str, worker: str, chunks: list | None = None) -> tuple[dict, str] | None:
        """Take the first chunk nobody holds (or whose holder stopped renewing): (chunk, lease etag), or None.
        A worker back from a stop takes its own chunk back first."""
        chunks = chunks if chunks is not None else self.chunks(root)
        job = self.job(root)
        st = self.state(root)
        now = self.now()
        free, stale, mine = [], [], []
        for c in chunks:
            s = st.get(c["id"])
            if s and (s["done"] or (s["failed"] and self.is_failed(root, c["id"]))):
                continue
            if not s or s["lease"] is None:
                free.append(c)
                continue
            lease, etag = self.lease(root, c["id"])
            if lease is None:
                free.append(c)
            elif lease.get("state") == "done":
                continue
            elif lease.get("worker") == worker:
                mine.append((c, lease, etag))
            elif lease.get("expires", 0) <= now:
                stale.append((c, lease, etag))
        for c, lease, etag in mine + stale:
            resume = lease.get("worker") == worker and lease.get("state") == "running"  # back from a stop
            if not resume and lease.get("attempt", 1) >= int(job.get("max_attempts", 4)):
                self.fail(root, c["id"], f"{lease.get('attempt')} attempts; last on {lease.get('worker')}: "
                                         f"{lease.get('why', '')}")
                continue
            new = {"worker": worker, "attempt": lease.get("attempt", 1) + (0 if resume else 1),
                   "claimed": now, "beat": now, "expires": now + LEASE_S, "state": "running",
                   "from": lease.get("worker")}
            try:
                return c, self.s.put_json(f"{root}c/{c['id']}/lease.json", new, if_match=etag)
            except PreconditionFailed:
                continue
        for c in free:
            new = {"worker": worker, "attempt": 1, "claimed": now, "beat": now, "expires": now + LEASE_S,
                   "state": "running"}
            try:
                return c, self.s.put_json(f"{root}c/{c['id']}/lease.json", new, if_none_match=True)
            except PreconditionFailed:
                continue
        return None

    def heartbeat(self, root: str, cid: str, worker: str, etag: str, **info) -> str:
        """Renew a lease we hold; returns the new etag. PreconditionFailed: it was taken over (we lost it: stop)."""
        lease, cur = self.lease(root, cid)
        if lease is None or cur != etag or lease.get("worker") != worker:
            raise PreconditionFailed(f"{cid}: lease lost to {lease and lease.get('worker')}")
        now = self.now()
        lease.update(beat=now, expires=now + LEASE_S, **info)
        return self.s.put_json(f"{root}c/{cid}/lease.json", lease, if_match=etag)

    def release(self, root: str, cid: str, worker: str, etag: str, why: str = "") -> None:
        """Give a chunk back at once (a failed render): expired, so the next claim takes it."""
        lease, cur = self.lease(root, cid)
        if lease is None or cur != etag or lease.get("worker") != worker:
            return
        lease.update(expires=0, state="released", why=why[-300:])
        try:
            self.s.put_json(f"{root}c/{cid}/lease.json", lease, if_match=etag)
        except PreconditionFailed:
            pass

    def expire(self, root: str, cid: str) -> bool:
        """Controller side: void a lease now (its worker is known to be stopped). True if it was voided."""
        lease, etag = self.lease(root, cid)
        if lease is None or lease.get("state") == "done":
            return False
        lease.update(expires=0, state="requeued")
        try:
            self.s.put_json(f"{root}c/{cid}/lease.json", lease, if_match=etag)
            return True
        except PreconditionFailed:
            return False

    def progress(self, root: str, cid: str, worker: str, frames: dict) -> None:
        self.s.put_json(f"{root}c/{cid}/progress/{worker}.json", {str(k): v for k, v in frames.items()})

    def complete(self, root: str, cid: str, worker: str, etag: str, frames: dict, **info) -> bool:
        """Record a chunk done, once: False if it was already done (by someone else) or we no longer hold it."""
        lease, cur = self.lease(root, cid)
        if lease is None or cur != etag or lease.get("worker") != worker:
            return False
        try:
            self.s.put_json(f"{root}c/{cid}/done.json", {"worker": worker, "at": self.now(),
                                                          "frames": {str(k): v for k, v in sorted(frames.items())},
                                                          **info}, if_none_match=True)
        except PreconditionFailed:
            return False
        lease.update(state="done", expires=0, beat=self.now())
        try:
            self.s.put_json(f"{root}c/{cid}/lease.json", lease, if_match=etag)
        except PreconditionFailed:
            pass
        return True

    def fail(self, root: str, cid: str, why: str) -> None:
        try:
            self.s.put_json(f"{root}c/{cid}/failed.json", {"why": why, "at": self.now()}, if_none_match=True)
        except PreconditionFailed:
            pass

    def retry(self, root: str, cid: str) -> None:
        """Controller side: a failed chunk back on the queue with fresh attempts (after fixing the cause). S3 here
        cannot delete (the box role has no DeleteObject), so failed.json is renamed by overwriting it as cleared."""
        doc, etag = self.s.get_json(f"{root}c/{cid}/failed.json")
        if doc is not None:
            self.s.put_json(f"{root}c/{cid}/failed.json", {**doc, "cleared": self.now()}, if_match=etag)
        lease, etag = self.lease(root, cid)
        if lease is not None:
            lease.update(attempt=0, expires=0, state="retry", worker="")
            self.s.put_json(f"{root}c/{cid}/lease.json", lease, if_match=etag)

    # --- assembling (a task, so a private job's frames are put together on a worker, never outside AWS) -----------
    def request_assemble(self, root: str, kinds: list) -> None:
        self.s.put_json(root + "assemble/request.json", {"kinds": list(kinds), "at": self.now()})

    def claim_assemble(self, root: str, worker: str):
        """(request, lease etag) when an assemble was asked for, is not done, every chunk is, and nobody (alive)
        holds it; else None."""
        req, _ = self.s.get_json(root + "assemble/request.json")
        if req is None:
            return None
        rep, _ = self.s.get_json(root + "assemble/report.json")
        if rep is not None and rep.get("at", 0) >= req["at"]:
            return None
        st = self.state(root)
        if any(not st.get(c["id"], {}).get("done") for c in self.chunks(root)):
            return None
        now = self.now()
        lease, etag = self.s.get_json(root + "assemble/lease.json")
        new = {"worker": worker, "expires": now + 4 * 3600, "claimed": now}
        try:
            if lease is None:
                return req, self.s.put_json(root + "assemble/lease.json", new, if_none_match=True)
            if lease.get("expires", 0) <= now or lease.get("claimed", 0) < req["at"]:
                return req, self.s.put_json(root + "assemble/lease.json", new, if_match=etag)
        except PreconditionFailed:
            return None
        return None

    def finish_assemble(self, root: str, worker: str, report: dict) -> None:
        self.s.put_json(root + "assemble/report.json", {**report, "worker": worker, "at": self.now()})
        lease, etag = self.s.get_json(root + "assemble/lease.json")
        if lease and lease.get("worker") == worker:
            lease["expires"] = 0
            try:
                self.s.put_json(root + "assemble/lease.json", lease, if_match=etag)
            except PreconditionFailed:
                pass

    # --- what is already rendered ----------------------------------------------------------------------------------
    def trusted_frames(self, root: str, cid: str, chunk: dict, out: dict, listing: dict | None = None) -> dict:
        """Frames of a chunk already in the output with the size a worker recorded for them (and its hash):
        {frame: [size, sha256]}. A frame in the output that no record vouches for is not trusted (it may be cut
        off), and is rendered again."""
        rec: dict = {}
        done, _ = self.s.get_json(f"{root}c/{cid}/done.json")
        if done:
            rec.update({int(k): v for k, v in done["frames"].items()})
        for o in self.s.list(f"{root}c/{cid}/progress/"):
            d, _ = self.s.get_json(o["key"])
            for k, v in (d or {}).items():
                rec.setdefault(int(k), v)
        if listing is None:
            listing = output_listing(self.s, out)
        return {f: v for f, v in rec.items() if chunk["start"] <= f < chunk["end"] and listing.get(f) == v[0]}

    def is_failed(self, root: str, cid: str) -> bool:
        doc, _ = self.s.get_json(f"{root}c/{cid}/failed.json")
        return bool(doc) and not doc.get("cleared")


def output_listing(store: Store, out: dict) -> dict:
    """{frame: size} of the frames in a job's output prefix."""
    b, prefix = model.split_s3(out["prefix"])
    got = {}
    for o in store.list(prefix):
        name = o["key"][len(prefix):]
        if "/" in name:
            continue
        f = model.frame_of(name, out["ext"])
        if f is not None:
            got[f] = o["size"]
    return got
