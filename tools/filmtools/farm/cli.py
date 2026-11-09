"""film-farm: render Blender and Unreal (MRQ) jobs across several GPU boxes (docs/FARM.md).

    film-farm quota                                    G vCPU quotas, what uses them, what a farm could launch
    film-farm up FARM -n 2 --ami ami-... [--market auto|spot|ondemand] [--types g6e.2xlarge,...] [--ttl 3h]
    film-farm submit FARM job.yaml [--workers 2]       plan the chunks and queue the job
    film-farm status FARM [--watch 30] [--json]        frames done/total, ETA, per-worker fps, $ so far
    film-farm logs FARM [WORKER] [-n 40]
    film-farm verify FARM JOB                          every frame once, at its recorded size
    film-farm assemble FARM JOB [--kinds mp4,prores] [--local DIR]   (private: on a worker; public: here with --local)
    film-farm compare FARM FARM_JOB ONE_BOX_JOB [--frames S,E] [--local DIR]   per-frame PSNR (private: on a worker)
    film-farm requeue FARM [JOB] [--retry-failed]      free the chunks of stopped boxes now; retry failed chunks
    film-farm stop-worker FARM INSTANCE                stop one farm box (the spot-interruption drill)
    film-farm down FARM [--stop]                       cancel spot requests, terminate every farm box
    film-farm cost FARM

Runs where the AWS CLI has the account (kali: --profile nani, or AWS_PROFILE). The bucket: --bucket, else
$FILM_FARM_BUCKET, else film-ue's settings (bucket).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from . import model, provision, verify
from .queue import Queue
from .store import AwsStore

BIG = 2  # more workers than this needs --big (the operator's rule: ask first)


def _settings(a) -> dict:
    conf = {}
    try:
        from filmtools.unreal import workstation as ws
        conf = ws.conf()
    except Exception:
        pass
    bucket = a.bucket or os.environ.get("FILM_FARM_BUCKET") or conf.get("bucket")
    if not bucket:
        raise SystemExit("no bucket: --bucket NAME, $FILM_FARM_BUCKET, or film-ue set --bucket")
    region = a.region or os.environ.get("FILM_FARM_REGION") or conf.get("region") or "ap-south-1"
    profile = a.profile or os.environ.get("AWS_PROFILE", "")
    return {"bucket": bucket, "region": region, "profile": profile}


def _load(path: str, bucket: str = "") -> dict:
    """A job file (YAML or JSON). In its strings, s3://BUCKET/ is the farm's bucket, and a value "@some/file" is that
    file's text (relative to the job file, then to the current folder, then to the repo), e.g. a Blender build script."""
    text = open(path).read()
    if path.endswith((".yaml", ".yml")):
        import yaml
        doc = yaml.safe_load(text)
    else:
        doc = json.loads(text)
    here = os.path.dirname(os.path.abspath(path))
    repo = str(provision.ROOT.parent)

    def fix(v):
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, str):
            if v.startswith("@"):
                for base in (here, os.getcwd(), repo):
                    p = os.path.join(base, v[1:])
                    if os.path.exists(p):
                        return open(p).read()
                raise SystemExit(f"{path}: no file {v[1:]}")
            if bucket:
                return v.replace("s3://BUCKET/", f"s3://{bucket}/")
        return v
    return fix(doc)


def _fmt_s(s) -> str:
    if s is None:
        return "?"
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def workers_docs(q: Queue) -> list[dict]:
    out = []
    for o in q.s.list(f"farm/{q.farm}/workers/"):
        d, _ = q.s.get_json(o["key"])
        if d:
            out.append(d)
    return out


def status_doc(q: Queue, aws=None) -> dict:
    now = q.now()
    ws_ = workers_docs(q)
    boxes = {}
    if aws:
        for i in provision.farm_instances(aws, q.farm, live_only=False):
            boxes[i["InstanceId"]] = {"state": i["State"]["Name"], "type": i["InstanceType"],
                                      "spot": i.get("InstanceLifecycle") == "spot",
                                      "zone": i["Placement"]["AvailabilityZone"]}
    jobs = []
    fps_total = 0.0
    for w in ws_:
        live = now - w.get("at", 0) < 120 and w.get("chunk")
        if live:
            fps_total += float(w.get("fps") or 0)
    for j in q.jobs():
        root = j["root"]
        chunks = q.chunks(root)
        st = q.state(root)
        done_frames, running, failed, n_done = 0, [], [], 0
        for c in chunks:
            s = st.get(c["id"], {})
            n = c["end"] - c["start"]
            if s.get("done"):
                done_frames += n
                n_done += 1
                continue
            if s.get("failed") and q.is_failed(root, c["id"]):
                failed.append(c["id"])
                continue
            if s.get("lease"):
                lease, _ = q.lease(root, c["id"])
                if lease and lease.get("state") == "running" and lease.get("expires", 0) > now:
                    done_frames += min(n, int(lease.get("frames") or 0))
                    running.append({"chunk": c["id"], "worker": lease["worker"], "frames": lease.get("frames", 0),
                                    "of": n, "attempt": lease.get("attempt"),
                                    "box": boxes.get(lease["worker"], {}).get("state")})
        total = j["frames"][1] - j["frames"][0]
        jobs.append({"id": j["id"], "engine": j["engine"], "privacy": j["privacy"], "frames_done": done_frames,
                     "frames": total, "chunks_done": n_done, "chunks": len(chunks), "running": running,
                     "failed": failed, "eta_s": model.eta_s(done_frames, total, fps_total)})
    c = provision.cost(ws_, now)
    return {"farm": q.farm, "jobs": jobs, "boxes": boxes, "fps": round(fps_total, 3), "usd": c["usd"],
            "workers": [{"worker": w.get("worker"), "type": w.get("type"), "market": w.get("market"),
                         "chunk": w.get("chunk"), "fps": w.get("fps"), "frames": w.get("frames"),
                         "seen_s_ago": int(now - w.get("at", now)),
                         "box": boxes.get(w.get("worker"), {}).get("state")} for w in ws_]}


def print_status(d: dict) -> None:
    print(f"farm {d['farm']}: {d['fps']} fps together, ${d['usd']:.2f} so far")
    for j in d["jobs"]:
        pct = 100 * j["frames_done"] / max(1, j["frames"])
        print(f"  {j['id']} ({j['engine']}, {j['privacy']}): {j['frames_done']}/{j['frames']} frames ({pct:.0f}%), "
              f"chunks {j['chunks_done']}/{j['chunks']}, ETA {_fmt_s(j['eta_s'])}"
              + (f", FAILED {j['failed']}" if j["failed"] else ""))
        for r in j["running"]:
            print(f"    {r['chunk']} on {r['worker']} ({r['box'] or '?'}): {r['frames']}/{r['of']} "
                  f"(attempt {r['attempt']})")
    for w in d["workers"]:
        print(f"  worker {w['worker']} {w['type']} {w['market']} [{w['box'] or '?'}]: chunk {w['chunk'] or '-'}, "
              f"{w['fps'] or 0} fps, {w['frames'] or 0} frames, seen {w['seen_s_ago']} s ago")
    for iid, b in d["boxes"].items():
        if iid not in {w["worker"] for w in d["workers"]}:
            print(f"  box {iid} {b['type']} {'spot' if b['spot'] else 'on-demand'} {b['state']} (no word yet)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="film-farm", description=__doc__.split("\n")[0])
    ap.add_argument("--bucket")
    ap.add_argument("--region")
    ap.add_argument("--profile")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("quota")
    u = sub.add_parser("up")
    u.add_argument("farm")
    u.add_argument("-n", type=int, default=2)
    u.add_argument("--ami", required=True)
    u.add_argument("--market", default="auto", choices=("auto", "spot", "ondemand"))
    u.add_argument("--types", default=",".join(provision.TYPES))
    u.add_argument("--ttl", default="3h", help="hard time to live (h)")
    u.add_argument("--idle", default="10m", help="power off after this long with nothing to do")
    u.add_argument("--iam-profile", default="ue-workstation")
    u.add_argument("--volume-gb", type=int, default=0, help="root disk (default: the image's)")
    u.add_argument("--setup", help="a bash script run once on each box before its worker starts (as root): a box made "
                   "from a plain image restores UE and the project from S3 (films/host-studio/farm/setup_tokyo.sh)")
    u.add_argument("--first-index", type=int, default=0)
    u.add_argument("--big", action="store_true", help=f"allow more than {BIG} workers")
    u.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("submit")
    s.add_argument("farm")
    s.add_argument("job")
    s.add_argument("--workers", type=int, default=2, help="for chunk 'auto': the boxes it will run on")
    s.add_argument("--dry-run", action="store_true", help="validate and print the chunks only")
    st = sub.add_parser("status")
    st.add_argument("farm")
    st.add_argument("--watch", type=float, default=0)
    st.add_argument("--json", action="store_true")
    lg = sub.add_parser("logs")
    lg.add_argument("farm")
    lg.add_argument("worker", nargs="?")
    lg.add_argument("-n", type=int, default=40)
    for name in ("verify", "assemble"):
        p = sub.add_parser(name)
        p.add_argument("farm")
        p.add_argument("job")
        if name == "assemble":
            p.add_argument("--kinds", default="mp4")
            p.add_argument("--local", help="public jobs: assemble here, in this folder")
            p.add_argument("--wait", type=float, default=0, help="wait this many minutes for the worker's report")
    cp = sub.add_parser("compare")
    cp.add_argument("farm")
    cp.add_argument("a")
    cp.add_argument("b")
    cp.add_argument("--frames", default="")
    cp.add_argument("--local", help="public jobs: compare here, in this folder")
    rq = sub.add_parser("requeue")
    rq.add_argument("farm")
    rq.add_argument("job", nargs="?")
    rq.add_argument("--retry-failed", action="store_true")
    sw = sub.add_parser("stop-worker")
    sw.add_argument("farm")
    sw.add_argument("instance")
    d = sub.add_parser("down")
    d.add_argument("farm")
    d.add_argument("--stop", action="store_true", help="stop instead of terminate (keeps the disks)")
    c = sub.add_parser("cost")
    c.add_argument("farm")
    a = ap.parse_args(argv)

    cfg = _settings(a)
    aws = provision.aws_cli(cfg["region"], cfg["profile"])
    store = AwsStore(cfg["bucket"], cfg["region"], cfg["profile"])
    q = Queue(store, a.farm) if hasattr(a, "farm") else None

    if a.cmd == "quota":
        qt, use = provision.quotas(aws), provision.g_usage(aws)
        print(json.dumps({"quota": qt, "use": use, "free": {k: qt[k] - use[k] for k in qt}}, indent=1))
        return 0
    if a.cmd == "up":
        if a.n > BIG and not a.big:
            raise SystemExit(f"{a.n} workers: more than {BIG} needs --big (ask the operator first)")
        types = tuple(t.strip() for t in a.types.split(",") if t.strip())
        if a.dry_run:
            qt, use = provision.quotas(aws), provision.g_usage(aws)
            print(json.dumps(provision.plan(a.n, quota=qt, usage=use, types=types, market=a.market), indent=1))
            return 0
        ttl_h = provision_hours(a.ttl)
        extra = {}
        if a.setup:  # to S3 beside the queue (a script, never data), fetched by each box's film-farm-setup
            body = Path(a.setup).read_bytes()
            key = f"farm/{a.farm}/setup/{hashlib.sha256(body).hexdigest()[:16]}.sh"
            store.put(key, body)
            extra["setup"] = f"s3://{cfg['bucket']}/{key}"
        rows = provision.launch(aws, farm=a.farm, n=a.n, ami=a.ami, bucket=cfg["bucket"], region=cfg["region"],
                                ttl_h=ttl_h, idle_min=provision_hours(a.idle) * 60, types=types, market=a.market,
                                iam_profile=a.iam_profile, volume_gb=a.volume_gb, first_index=a.first_index,
                                prices=provision.pricer(aws, cfg["region"]),
                                put_code=lambda url, b: store.put(model.split_s3(url)[1], b), extra_conf=extra)

        def note(doc):
            doc.setdefault("launched", []).extend({**r, "at": int(time.time())} for r in rows)
            return doc
        q.update_farm(note)
        print(json.dumps(rows, indent=1))
        return 0 if len(rows) == a.n else 1
    if a.cmd == "submit":
        job = _load(a.job, cfg["bucket"])
        if a.dry_run:
            j = model.validate(job, bucket=cfg["bucket"])
            ch = model.plan_chunks(j, a.workers)
            print(json.dumps({"job": j, "chunks": ch, "cover": model.check_cover(ch, j["frames"])}, indent=1))
            return 0
        print(json.dumps(q.submit(job, a.workers), indent=1))
        return 0
    if a.cmd == "status":
        while True:
            dd = status_doc(q, aws)
            if a.json:
                print(json.dumps(dd, indent=1))
            else:
                print_status(dd)
            if not a.watch or all(j["chunks_done"] == j["chunks"] for j in dd["jobs"]):
                return 0
            time.sleep(a.watch)
            print()
    if a.cmd == "logs":
        keys = [o["key"] for o in store.list(f"farm/{a.farm}/logs/")
                if not a.worker or o["key"].endswith(f"/{a.worker}.log")]
        for k in keys:
            got = store.get(k)
            print(f"== {k.rsplit('/', 1)[-1]}")
            print("\n".join(got[0].decode(errors="replace").splitlines()[-a.n:]))
        return 0
    if a.cmd in ("verify", "assemble"):
        root = _root(q, a.job)
        if a.cmd == "verify":
            v = verify.verify(q, root)
            print(json.dumps(v, indent=1))
            return 0 if v["ok"] else 1
        kinds = [k.strip() for k in a.kinds.split(",")]
        job = q.job(root)
        if a.local:
            if job["privacy"] == "private":
                raise SystemExit("a private job is assembled on a worker only (the face rule): drop --local")
            rep = verify.assemble(q, root, a.local, kinds=tuple(kinds))
            print(json.dumps(rep, indent=1))
            return 0 if rep.get("ok") else 1
        q.request_assemble(root, kinds)
        print(f"assemble of {a.job} queued for a worker (report: s3://{cfg['bucket']}/{root}assemble/report.json)")
        end = time.time() + a.wait * 60
        while time.time() < end:
            rep, _ = store.get_json(root + "assemble/report.json")
            req, _ = store.get_json(root + "assemble/request.json")
            if rep and rep.get("at", 0) >= req["at"]:
                print(json.dumps(rep, indent=1))
                return 0 if rep.get("ok") else 1
            time.sleep(15)
        return 0
    if a.cmd == "compare":
        ra, rb = _root(q, a.a), _root(q, a.b)
        private = "private" in (q.job(ra)["privacy"], q.job(rb)["privacy"])
        if a.local and not private:
            fr = None
            if a.frames:
                s0, e0 = (int(x) for x in a.frames.split(","))
                fr = list(range(s0, e0))
            print(json.dumps(verify.compare(q, ra, rb, a.local, fr), indent=1))
            return 0
        if a.local:
            raise SystemExit("a private job is compared on a worker only (the face rule): drop --local")
        cmd = (f"cd /opt/film-farm && python3 -m filmtools.farm.compare --farm {a.farm} --a {a.a} --b {a.b}"
               + (f" --frames {a.frames}" if a.frames else ""))
        out = on_worker(aws, a.farm, cmd)
        line = [x for x in out.splitlines() if x.startswith("FARM-COMPARE ")]
        print(json.dumps(json.loads(line[-1][13:]), indent=1) if line else out[-2000:])
        return 0 if line else 1
    if a.cmd == "requeue":
        live = {i["InstanceId"]: i["State"]["Name"] for i in provision.farm_instances(aws, a.farm, live_only=False)}
        n = 0
        for j in q.jobs():
            if a.job and j["id"] != a.job:
                continue
            for c in q.chunks(j["root"]):
                lease, _ = q.lease(j["root"], c["id"])
                if lease and lease.get("state") == "running" and live.get(lease.get("worker")) in (
                        "stopping", "stopped", "shutting-down", "terminated"):
                    n += q.expire(j["root"], c["id"])
                    print(f"{j['id']}/{c['id']}: freed (its box {lease['worker']} is {live[lease['worker']]})")
                if a.retry_failed and q.is_failed(j["root"], c["id"]):
                    q.retry(j["root"], c["id"])
                    print(f"{j['id']}/{c['id']}: failed -> queued again")
        print(f"{n} chunk(s) freed")
        return 0
    if a.cmd == "stop-worker":
        print(provision.stop(aws, a.farm, [a.instance]))
        return 0
    if a.cmd == "down":
        print(json.dumps(provision.down(aws, a.farm, stop_only=a.stop), indent=1))
        print(json.dumps(provision.cost(workers_docs(q), time.time()), indent=1))
        return 0
    if a.cmd == "cost":
        print(json.dumps(provision.cost(workers_docs(q), time.time()), indent=1))
        return 0
    return 2


def on_worker(aws, farm: str, cmd: str, timeout: int = 3600) -> str:
    """Run a shell command on a running farm box over SSM; its stdout (numbers only, never frames)."""
    run = [i["InstanceId"] for i in provision.farm_instances(aws, farm) if i["State"]["Name"] == "running"]
    if not run:
        raise SystemExit(f"no running box in farm {farm}")
    cid = aws("ssm", "send-command", "--instance-ids", run[0], "--document-name", "AWS-RunShellScript",
              "--parameters", json.dumps({"commands": [cmd], "executionTimeout": [str(timeout)]}))["Command"]["CommandId"]
    end = time.time() + timeout + 60
    while time.time() < end:
        time.sleep(5)
        try:
            r = aws("ssm", "get-command-invocation", "--command-id", cid, "--instance-id", run[0])
        except provision.AwsError:
            continue
        if r.get("Status") in ("Success", "Failed", "TimedOut", "Cancelled"):
            if r["Status"] != "Success":
                raise SystemExit(f"on {run[0]}: {r['Status']}: {r.get('StandardErrorContent', '')[-800:]}")
            return r.get("StandardOutputContent", "")
    raise SystemExit("timed out")


def provision_hours(s: str) -> float:
    """'3h', '90m', '1h30m' or a number of hours, in hours."""
    import re
    s = str(s).strip().lower()
    try:
        return float(s)
    except ValueError:
        pass
    parts = re.findall(r"(\d+(?:\.\d+)?)([hm])", s)
    if not parts:
        raise SystemExit(f"duration {s!r}: like 3h, 90m or 1h30m")
    return sum(float(n) * (1 if u == "h" else 1 / 60) for n, u in parts)


def _root(q: Queue, job_id: str) -> str:
    for j in q.jobs():
        if j["id"] == job_id:
            return j["root"]
    raise SystemExit(f"no job {job_id} on farm {q.farm} (film-farm status {q.farm})")


if __name__ == "__main__":
    sys.exit(main())
