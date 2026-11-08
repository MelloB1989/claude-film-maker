"""film-farm (filmtools.farm): chunking, the pre-roll maths, leases and requeue, idempotent resume, verify, and the
worker end to end on an in-memory bucket with a fake engine (a spot loss mid-chunk included); provisioning with a
fake AWS (quota planning, the fallback, tags, the guard that never touches another box)."""
from __future__ import annotations

import json
import os

import pytest

from filmtools.farm import engines, model, provision, verify
from filmtools.farm.queue import LEASE_S, Queue
from filmtools.farm.store import MemStore, PreconditionFailed
from filmtools.farm.worker import Worker

B = "test-bucket"


def job(**kw):
    j = {"id": "j1", "engine": "ue", "frames": [0, 100], "privacy": "public",
         "output": {"prefix": f"s3://{B}/farm/out/j1/", "ext": "png", "pad": 4}, "chunk": 25, "preroll": 24}
    j.update(kw)
    return j


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


# --- the job and its chunks -----------------------------------------------------------------------------------------
def test_validate_defaults_and_face_rule():
    j = model.validate(job(engine="blender", preroll=0))
    assert j["output"]["prefix"].endswith("/j1/") and j["max_attempts"] == 4
    assert model.validate({k: v for k, v in job(engine="blender").items() if k != "preroll"})["preroll"] == 0
    assert model.validate({k: v for k, v in job().items() if k != "preroll"})["preroll"] == 24
    with pytest.raises(model.JobError, match="face rule"):
        model.validate(job(presenter=True))
    with pytest.raises(model.JobError, match="private job writes only under"):
        model.validate(job(privacy="private"), bucket=B)
    p = model.validate(job(privacy="private", presenter=True,
                           output={"prefix": f"s3://{B}/ue-linux/private/farm/x/"}), bucket=B)
    assert p["output"]["sse"] == "aws:kms"
    with pytest.raises(model.JobError, match="private job writes only under"):  # private, but another bucket
        model.validate(job(privacy="private", output={"prefix": "s3://other/ue-linux/private/x/"}), bucket=B)
    for bad in ({"frames": [10, 10]}, {"engine": "maya"}, {"id": "Bad Id"}, {"privacy": "secret"}):
        with pytest.raises(model.JobError):
            model.validate(job(**bad))


def test_chunks_cover_exactly_and_break_on_cuts():
    j = model.validate(job(frames=[0, 100], chunk=30, cuts=[40]))
    ch = model.plan_chunks(j)
    assert model.check_cover(ch, j["frames"]) == []
    assert [(c["start"], c["end"]) for c in ch] == [(0, 20), (20, 40), (40, 70), (70, 100)]
    assert all(c["end"] - c["start"] <= 30 for c in ch)


def test_chunks_even_split_and_auto():
    j = model.validate(job(frames=[10, 111], chunk=25))
    sizes = [c["end"] - c["start"] for c in model.plan_chunks(j)]
    assert sum(sizes) == 101 and max(sizes) - min(sizes) <= 1 and len(sizes) == 5
    a = model.validate(job(frames=[0, 1440], chunk="auto"))
    ch = model.plan_chunks(a, workers=4)
    assert len(ch) == 12 and model.check_cover(ch, [0, 1440]) == []
    assert model.auto_chunk([0, 20], 8) == model.MIN_CHUNK


def test_preroll_maths():
    # mid-shot: 24 before; clamped at the job start and at a cut (a one-box render starts cold there too)
    assert model.preroll_from(100, 0, [], 24) == 76
    assert model.preroll_from(10, 0, [], 24) == 0
    assert model.preroll_from(130, 0, [120], 24) == 120
    assert model.preroll_from(120, 0, [120], 24) == 120
    assert model.preroll_from(200, 0, [120], 32) == 168
    j = model.validate(job(frames=[0, 100], chunk=25, preroll=24, cuts=[60]))
    ch = {c["id"]: c for c in model.plan_chunks(j)}
    assert [(c["start"], c["render_from"], c["preroll"]) for c in ch.values()] == [
        (0, 0, 0), (20, 0, 20), (40, 16, 24), (60, 60, 0), (80, 60, 20)]


def test_check_cover_finds_gaps_and_overlaps():
    assert model.check_cover([{"id": "a", "start": 0, "end": 5}, {"id": "b", "start": 6, "end": 10}], [0, 10]) == [
        "gap [5, 6)"]
    assert "b: overlaps [4, 5)" in model.check_cover([{"id": "a", "start": 0, "end": 5},
                                                      {"id": "b", "start": 4, "end": 10}], [0, 10])
    assert model.check_cover([{"id": "a", "start": 0, "end": 5}], [0, 10]) == ["gap [5, 10)"]


def test_todo_resumes_from_first_missing():
    j = model.validate(job(frames=[0, 100], preroll=24))
    c = {"id": "c1", "start": 50, "end": 75, "render_from": 26, "preroll": 24}
    assert model.todo(c, {f: 1 for f in range(50, 75)}, j, contiguous=True) is None
    t = model.todo(c, {f: 1 for f in range(50, 60)} | {70: 1}, j, contiguous=True)
    assert (t["start"], t["end"], t["render_from"], t["preroll"]) == (60, 75, 36, 24)
    assert 70 in t["frames"] and 70 not in t["missing"]
    b = model.todo(c, {f: 1 for f in range(50, 60)} | {70: 1}, j, contiguous=False)
    assert b["frames"] == [f for f in range(60, 75) if f != 70] and b["preroll"] == 0
    assert model.runs([1, 2, 3, 7, 8, 10]) == [(1, 4), (7, 9), (10, 11)]


# --- leases ---------------------------------------------------------------------------------------------------------
def make_q(clock=None, **kw):
    s = MemStore(B)
    q = Queue(s, "f1", clock=clock or Clock())
    r = q.submit(job(**kw))
    return s, q, r["root"]


def test_store_conditional_writes():
    s = MemStore(B)
    e = s.put("k", b"1", if_none_match=True)
    with pytest.raises(PreconditionFailed):
        s.put("k", b"2", if_none_match=True)
    e2 = s.put("k", b"2", if_match=e)
    with pytest.raises(PreconditionFailed):
        s.put("k", b"3", if_match=e)
    assert s.get("k") == (b"2", e2)


def test_submit_is_idempotent_and_refuses_a_changed_job():
    s, q, root = make_q()
    assert q.submit(job())["new"] is False
    with pytest.raises(model.JobError, match="other settings"):
        q.submit(job(chunk=10))
    assert len(q.jobs()) == 1 and root == "farm/f1/j1/"
    _, qp, rp = make_q(privacy="private", output={"prefix": f"s3://{B}/ue-linux/private/out/j1/"})
    assert rp == "farm/f1/j1/"  # the queue never holds a frame; the frames go to the private prefix


def test_two_workers_never_hold_the_same_chunk():
    s, q, root = make_q()
    got = [q.claim(root, f"w{i}") for i in range(5)]
    held = [g[0]["id"] for g in got if g]
    assert len(held) == 4 and len(set(held)) == 4 and got[4] is None


def test_expired_lease_is_taken_over_and_old_holder_loses_it():
    clock = Clock()
    s, q, root = make_q(clock)
    c, etag = q.claim(root, "w0")
    clock.t += 60
    etag = q.heartbeat(root, c["id"], "w0", etag)
    for i in range(1, 4):
        q.claim(root, f"w{i}")  # the other three chunks
    assert q.claim(root, "w9") is None  # all held and fresh
    clock.t += LEASE_S + 1  # w0 died (spot reclaim): no renewals
    c2, e2 = q.claim(root, "w9")
    assert c2["id"] == c["id"] or c2["id"] != c["id"]  # it took one of the expired chunks
    lease, _ = q.lease(root, c2["id"])
    assert lease["worker"] == "w9" and lease["attempt"] == 2
    if c2["id"] == c["id"]:
        with pytest.raises(PreconditionFailed):
            q.heartbeat(root, c["id"], "w0", etag)
        assert q.complete(root, c["id"], "w0", etag, {}) is False


def test_worker_back_from_a_stop_resumes_its_own_chunk():
    clock = Clock()
    s, q, root = make_q(clock)
    c, _ = q.claim(root, "w0")
    clock.t += LEASE_S + 5  # stopped, nobody took it
    c2, _ = q.claim(root, "w0")
    lease, _ = q.lease(root, c2["id"])
    assert c2["id"] == c["id"] and lease["attempt"] == 1


def test_release_requeues_and_attempts_run_out():
    s, q, root = make_q(max_attempts=2)
    c, e = q.claim(root, "w0")
    q.release(root, c["id"], "w0", e, "boom")
    c2, e2 = q.claim(root, "w1")
    assert c2["id"] == c["id"]
    q.release(root, c2["id"], "w1", e2, "boom again")
    nxt = q.claim(root, "w2")  # attempts used up: c0000 fails, the next chunk is handed out
    assert nxt[0]["id"] != c["id"] and q.is_failed(root, c["id"])
    q.retry(root, c["id"])
    assert not q.is_failed(root, c["id"])
    again = q.claim(root, "w3")
    assert again[0]["id"] == c["id"]


def test_controller_expire_frees_a_stopped_boxs_chunk_now():
    s, q, root = make_q()
    c, e = q.claim(root, "w0")
    assert q.expire(root, c["id"])
    c2, _ = q.claim(root, "w1")
    assert c2["id"] == c["id"]


def test_complete_once():
    s, q, root = make_q()
    c, e = q.claim(root, "w0")
    assert q.complete(root, c["id"], "w0", e, {0: [1, "h"]})
    assert q.complete(root, c["id"], "w0", e, {0: [1, "h"]}) is False
    assert q.claim(root, "w1")[0]["id"] != c["id"]


def test_trusted_frames_need_a_record_and_the_size():
    s, q, root = make_q()
    out = q.job(root)["output"]
    c = q.chunks(root)[0]
    for f, body in ((0, b"aaaa"), (1, b"bbbb"), (2, b"cc")):
        s.put(f"farm/out/j1/{f:04d}.png", body)
    q.progress(root, c["id"], "w0", {0: [4, "h0"], 2: [9, "h2"]})  # 1 has no record, 2 the wrong size
    assert q.trusted_frames(root, c["id"], c, out) == {0: [4, "h0"]}


# --- the worker end to end -----------------------------------------------------------------------------------------
class FakeEngine:
    """Writes NNNN.png files with deterministic contents; can die after some frames (a spot reclaim)."""
    CONTIGUOUS = True

    def __init__(self, die_after=None):
        self.die_after, self.calls = die_after, []

    def prepare(self, job, ctx):
        pass

    def render(self, job, chunk, todo, scratch, ctx):
        os.makedirs(scratch, exist_ok=True)
        self.calls.append((chunk["id"], todo["render_from"], todo["end"]))
        n = 0
        for f in range(todo["render_from"], todo["end"]):
            p = os.path.join(scratch, f"{f:04d}.png")
            open(p, "wb").write(f"frame {f}".encode())
            yield f, p
            n += 1
            if self.die_after is not None and n >= self.die_after:
                raise SystemExit("box stopped")  # not a RenderError: the process is gone

    def cleanup(self, scratch):
        pass


@pytest.fixture
def fake_engine(monkeypatch):
    eng = FakeEngine()
    monkeypatch.setattr(engines, "get", lambda name: eng)
    return eng


def run_worker(q, wid, tmp_path, **kw):
    w = Worker({"farm": "f1", "worker": wid, "idle_s": 0, "scratch": str(tmp_path / wid)}, queue=q,
               clock=q.now, sleep=lambda s: None)
    return w


def test_two_workers_render_everything_once(tmp_path, fake_engine):
    s, q, root = make_q(frames=[0, 60], chunk=20, preroll=8)
    w0, w1 = run_worker(q, "w0", tmp_path), run_worker(q, "w1", tmp_path)
    while True:
        a, b = w0.claim(), None
        if a:
            w0.run_chunk(*a)
        b = w1.claim()
        if b:
            w1.run_chunk(*b)
        if not a and not b:
            break
    v = verify.verify(q, root)
    assert v["ok"], v
    assert v["present"] == 60 and v["duplicates"] == [] and v["missing"] == []
    # pre-roll rendered and thrown away: chunk 2 rendered from 12, but frame 12..19 belong to chunk 1 only once
    assert ("c0001", 12, 40) in fake_engine.calls
    assert all(s.meta(f"farm/out/j1/{f:04d}.png")["sha256"] for f in range(60))


def test_spot_loss_mid_chunk_requeues_and_completes(tmp_path, monkeypatch):
    clock = Clock()
    s, q, root = make_q(clock, frames=[0, 40], chunk=20, preroll=8)
    dying = FakeEngine(die_after=15)  # chunk 0 starts at the job start (no pre-roll): frames 0..14, then gone
    monkeypatch.setattr(engines, "get", lambda name: dying)
    w0 = run_worker(q, "w0", tmp_path)
    with pytest.raises(SystemExit):
        w0.run_chunk(*w0.claim())  # the box stops: no release, the lease is left running
    lease, _ = q.lease(root, "c0000")
    assert lease["worker"] == "w0" and lease["state"] == "running"
    clock.t += LEASE_S + 1  # nobody renews it
    good = FakeEngine()
    monkeypatch.setattr(engines, "get", lambda name: good)
    w1 = run_worker(q, "w1", tmp_path)
    while (got := w1.claim()):
        w1.run_chunk(*got)
    v = verify.verify(q, root)
    assert v["ok"], v
    # w1 picked chunk 0 up at the first frame w0 did not upload (15), pre-rolled 8 again
    assert ("c0000", 7, 20) in good.calls
    done, _ = s.get_json(f"{root}c/c0000/done.json")
    assert done["worker"] == "w1" and sorted(int(k) for k in done["frames"]) == list(range(20))
    assert done["uploaded"] == 5


def test_lost_lease_stops_uploads(tmp_path, monkeypatch):
    clock = Clock()
    s, q, root = make_q(clock, frames=[0, 20], chunk=20, preroll=0)

    class Slow(FakeEngine):
        def render(self, job, chunk, todo, scratch, ctx):
            for i, (f, p) in enumerate(super().render(job, chunk, todo, scratch, ctx)):
                if i == 5:
                    clock.t += LEASE_S * 2  # this box froze; another took the chunk over
                    q.claim(root, "thief")
                yield f, p
    monkeypatch.setattr(engines, "get", lambda name: Slow())
    w = run_worker(q, "w0", tmp_path)
    assert w.run_chunk(*w.claim()) is False
    lease, _ = q.lease(root, "c0000")
    assert lease["worker"] == "thief"
    assert len([k for k in s.objects if k.startswith("farm/out/j1/")]) == 5  # nothing after the takeover


def test_verify_flags_missing_extra_and_size(tmp_path, fake_engine):
    s, q, root = make_q(frames=[0, 20], chunk=10, preroll=0)
    w = run_worker(q, "w0", tmp_path)
    while (got := w.claim()):
        w.run_chunk(*got)
    assert verify.verify(q, root)["ok"]
    s.put("farm/out/j1/0099.png", b"x")
    s.put("farm/out/j1/0003.png", b"truncated")
    v = verify.verify(q, root)
    assert not v["ok"] and v["extra"] == ["0099.png"] and v["size_mismatch"] == [3]


def test_continuity_flags_a_jump_at_a_boundary():
    diffs = {f: 1.0 for f in range(1, 60)}
    diffs[20] = 1.2
    diffs[40] = 9.0
    c = verify.continuity(diffs, [20, 40])
    assert c["flagged"] == [40] and not c["ok"]
    assert verify.boundaries([{"start": 0}, {"start": 20}, {"start": 40}], [40]) == [20]


# --- provisioning (fake AWS) ----------------------------------------------------------------------------------------
class FakeAWS:
    def __init__(self, spot_quota=16, od_quota=16, boxes=(), no_capacity=()):
        self.q = {provision.QUOTA_SPOT: spot_quota, provision.QUOTA_OD: od_quota}
        self.inst = {b["InstanceId"]: b for b in boxes}
        self.no_capacity = set(no_capacity)  # (type, market, subnet)
        self.calls = []

    def __call__(self, *a, region_override=""):
        self.calls.append(a)
        svc, verb = a[0], a[1]
        if verb == "get-service-quota":
            return {"Quota": {"Value": float(self.q[a[a.index("--quota-code") + 1]])}}
        if verb == "describe-instances":
            flt = [x for x in a if x.startswith("Name=")]
            out = list(self.inst.values())
            for f in flt:
                k, v = f[5:].split(",Values=")
                vals = v.split(",")
                if k == "instance-state-name":
                    out = [i for i in out if i["State"]["Name"] in vals]
                elif k == "instance-id":
                    out = [i for i in out if i["InstanceId"] in vals]
                elif k.startswith("tag:"):
                    out = [i for i in out if provision.tags_of(i).get(k[4:]) in vals]
            return {"Reservations": [{"Instances": out}]}
        if verb == "describe-subnets":
            return {"Subnets": [{"AvailabilityZone": f"ap-south-1{z}", "SubnetId": f"subnet-{z}"} for z in "abc"]}
        if verb == "describe-images":
            return {"Images": [{"RootDeviceName": "/dev/sda1",
                                "BlockDeviceMappings": [{"Ebs": {"VolumeSize": 300}}]}]}
        if verb == "run-instances":
            it = a[a.index("--instance-type") + 1]
            spot = "--instance-market-options" in a
            sub = a[a.index("--subnet-id") + 1]
            if (it, "spot" if spot else "ondemand", sub) in self.no_capacity:
                raise provision.AwsError("InsufficientInstanceCapacity", "InsufficientInstanceCapacity")
            iid = f"i-farm{len(self.inst)}"
            tags = json.loads(a[a.index("--tag-specifications") + 1])[0]["Tags"]
            self.inst[iid] = {"InstanceId": iid, "InstanceType": it, "State": {"Name": "pending"}, "Tags": tags,
                              **({"InstanceLifecycle": "spot", "SpotInstanceRequestId": f"sir-{iid}"} if spot else {})}
            return {"Instances": [self.inst[iid]]}
        if verb in ("terminate-instances", "stop-instances", "cancel-spot-instance-requests"):
            return {}
        raise AssertionError(a)


BOX_B = {"InstanceId": "i-boxb", "InstanceType": "g6e.4xlarge", "InstanceLifecycle": "spot",
         "State": {"Name": "running"}, "Tags": [{"Key": "Name", "Value": "ue-box-b-explainer"},
                                                {"Key": "Project", "Value": "ue-linux-poc"}]}


def test_plan_respects_quotas_box_b_holds_the_spot():
    aws = FakeAWS(boxes=[BOX_B])
    use = provision.g_usage(aws)
    assert use["spot"] == 16
    p = provision.plan(2, quota=provision.quotas(aws), usage=use, types=("g6e.2xlarge",))
    assert [w["options"][0] for w in p] == [("g6e.2xlarge", "ondemand")] * 2
    with pytest.raises(SystemExit, match="does not fit"):
        provision.plan(3, quota=provision.quotas(aws), usage=use, types=("g6e.2xlarge",))
    with pytest.raises(SystemExit, match="does not fit"):
        provision.plan(1, quota=provision.quotas(aws), usage=use, types=("g6e.2xlarge",), market="spot")


def test_launch_falls_back_and_tags(monkeypatch):
    aws = FakeAWS(boxes=[BOX_B], no_capacity={("g6e.2xlarge", "ondemand", "subnet-a")})
    rows = provision.launch(aws, farm="f1", n=2, ami="ami-x", bucket=B, region="ap-south-1", ttl_h=2, idle_min=10,
                            types=("g6e.2xlarge",), log=lambda *a: None, put_code=lambda u, b: None)
    assert [r["zone"] for r in rows] == ["ap-south-1b", "ap-south-1b"]
    run = [c for c in aws.calls if c[1] == "run-instances"][-1]
    tags = {t["Key"]: t["Value"] for t in json.loads(run[run.index("--tag-specifications") + 1])[0]["Tags"]}
    assert tags["Project"] == "ue-linux-poc" and tags["FarmJob"] == "f1" and tags["TTLHours"] == "2"
    assert run[run.index("--instance-initiated-shutdown-behavior") + 1] == "terminate"
    ud = run[run.index("--user-data") + 1]
    assert "film-farm-worker.service" in ud and '"idle_s": 600' in ud


def test_spot_is_persistent_and_stops():
    a = provision.run_args(farm="f1", index=0, itype="g6e.4xlarge", market="spot", zone_subnet="s", ami="ami",
                           ttl_h=1, user_data_text="x", iam_profile="p", volume_gb=10)
    mo = json.loads(a[a.index("--instance-market-options") + 1])
    assert mo["SpotOptions"] == {"SpotInstanceType": "persistent", "InstanceInterruptionBehavior": "stop"}
    assert a[a.index("--instance-initiated-shutdown-behavior") + 1] == "stop"
    spec = json.loads(a[a.index("--tag-specifications") + 1])
    assert "spot-instances-request" in [s["ResourceType"] for s in spec]


def test_down_and_stop_never_touch_other_boxes():
    kedits = {"InstanceId": "i-k", "InstanceType": "g6e.xlarge", "State": {"Name": "running"},
              "Tags": [{"Key": "Name", "Value": "kedits-dev-1"}, {"Key": "FarmJob", "Value": "f1"},
                       {"Key": "film-farm:managed", "Value": "1"}]}  # even with the farm's tags
    aws = FakeAWS(boxes=[BOX_B, kedits], od_quota=64)
    rows = provision.launch(aws, farm="f1", n=1, ami="ami", bucket=B, region="ap-south-1", ttl_h=1, idle_min=10,
                            types=("g6e.2xlarge",), market="ondemand", log=lambda *a: None)
    with pytest.raises(SystemExit, match="refused"):
        provision.stop(aws, "f1", ["i-boxb"])
    with pytest.raises(SystemExit, match="refused"):
        provision.stop(aws, "f1", ["i-k"])
    with pytest.raises(SystemExit, match="refused"):
        provision.stop(aws, "f2", [rows[0]["id"]])  # another farm's
    d = provision.down(aws, "f1", log=lambda *a: None)
    assert d["instances"] == [rows[0]["id"]]
    term = [c for c in aws.calls if c[1] == "terminate-instances"]
    assert term and "i-boxb" not in term[0] and "i-k" not in term[0]


def test_cost_from_sessions():
    c = provision.cost([{"worker": "i-1", "price_h": 2.0, "sessions": [[0, 1800], [3600, 5400]]},
                        {"worker": "i-2", "price_h": 1.0, "sessions": [[0, 3600]]}], now=5400)
    assert c["usd"] == 3.0 and c["workers"][0]["hours"] == 1.0


def test_code_tarball_is_the_farm_only():
    import io
    import tarfile
    names = tarfile.open(fileobj=io.BytesIO(provision.code_tarball())).getnames()
    assert "filmtools/__init__.py" in names and "filmtools/farm/worker.py" in names
    assert "filmtools/farm/engines/ue.py" in names and not any("unreal/" in n for n in names)
    assert provision.code_tarball() == provision.code_tarball()


# --- engines (pure parts) -------------------------------------------------------------------------------------------
def test_ue_chunk_spec_takes_the_farms_range():
    from filmtools.farm.engines import ue
    j = model.validate(job(ue={"spec": {"sequence": "/Game/S", "preset": "final", "frames": [0, 999],
                                        "shots": ["X"], "out_dir": "/elsewhere"}}))
    sp = ue.chunk_spec(j, {"id": "c0002"}, {"render_from": 26, "end": 75}, "/srv/farm/j1/c0002")
    assert sp["frames"] == [26, 75] and sp["out_dir"] == "/srv/farm/j1/c0002" and "shots" not in sp
    assert sp["preroll"] == "cut" and sp["resume"] is False and sp["preset"] == "final"


def test_blender_command_and_setup():
    from filmtools.farm.engines import blender
    cmd = blender.command("/opt/b/blender", "/s/x.blend", "/t/s.py", 10, 20)
    assert cmd[-6:] == ["-s", "10", "-e", "19", "-a"][-5:] or cmd[-5:] == ["-s", "10", "-e", "19", "-a"]
    py = blender.setup_py({"engine": "CYCLES", "samples": 64, "resolution": [640, 360]}, "/t/out",
                          {"ext": "png", "pad": 4})
    assert "OPTIX" in py and "sc.cycles.samples = 64" in py and "/t/out/####" in py
    compile(py, "setup", "exec")


# --- the ue engine's hook, the deep check, compare ------------------------------------------------------------------
class FakeBridge:
    """The box's bridge: ops answer from `answers`; render.job writes the frames of its spec and finishes."""

    def __init__(self, answers=None):
        self.answers, self.calls, self.jobs = answers or {}, [], {}

    def healthy(self):
        return True

    def run(self, name, args, ctx, timeout=0):
        self.calls.append((name, args))
        return self.answers.get(name, {})

    def submit(self, name, args):
        self.calls.append((name, args))
        sp = args["spec"]
        for f in range(*sp["frames"]):
            open(os.path.join(sp["out_dir"], f"{f:04d}.png"), "wb").write(b"x%d" % f)
        self.jobs["j"] = {"done": True, "ok": True, "result": {"status": "ok"}}
        return "j"

    def job(self, jid):
        return self.jobs[jid]

    def cancel(self, jid):
        pass


class Ctx:
    def __init__(self, br):
        self.state, self.lines = {"bridge": br, "started": True}, []

    def log(self, m):
        self.lines.append(m)

    def stopping(self):
        return False

    def sh(self, cmd, timeout=0, check=True):
        return 0


HOOK = '''
def before_chunk(op, job, chunk):
    r = op("guard.check", camera=job["ue"]["hook_args"]["camera"])
    return {"ok": r.get("pass", False), "why": "" if r.get("pass") else "face dark", "luma": r.get("luma")}
'''


def ue_job(**ue):
    return model.validate(job(ue={"spec": {"sequence": "/Game/S"}, "fresh_editor": False, "hook": HOOK,
                                  "hook_args": {"camera": "CAM_CU"}, **ue}))


def test_ue_hook_guards_every_chunk(tmp_path):
    from filmtools.farm.engines import ue
    j = ue_job(before=[["mh.leader", {"label": "P"}]])
    chunk = {"id": "c0001", "start": 50, "end": 60}
    todo = {"render_from": 40, "start": 50, "end": 60, "frames": list(range(50, 60)), "preroll": 10}
    br = FakeBridge({"guard.check": {"pass": True, "luma": 120}})
    ctx = Ctx(br)
    got = [f for f, _ in ue.render(j, chunk, todo, str(tmp_path / "c"), ctx)]
    assert got == list(range(40, 60))  # pre-roll comes back too; the worker drops it
    names = [c[0] for c in br.calls]
    assert names == ["mh.leader", "guard.check", "render.job"]  # before, then the hook, then the render
    assert br.calls[1][1] == {"camera": "CAM_CU"} and ctx.state["hook"]["luma"] == 120
    dark = FakeBridge({"guard.check": {"pass": False}})
    with pytest.raises(engines.RenderError, match="face dark"):
        list(ue.render(j, chunk, todo, str(tmp_path / "d"), Ctx(dark)))
    assert "render.job" not in [c[0] for c in dark.calls]  # a refused chunk never renders


def test_worker_records_the_hook_in_done(tmp_path, monkeypatch):
    s, q, root = make_q(frames=[0, 10], chunk=10, preroll=0)

    class Hooked(FakeEngine):
        def render(self, job, chunk, todo, scratch, ctx):
            ctx.state["hook"] = {"ok": True, "leaders_ok": 1}
            yield from super().render(job, chunk, todo, scratch, ctx)
    monkeypatch.setattr(engines, "get", lambda name: Hooked())
    w = run_worker(q, "w0", tmp_path)
    assert w.run_chunk(*w.claim())
    done, _ = s.get_json(f"{root}c/c0000/done.json")
    assert done["hook"] == {"ok": True, "leaders_ok": 1}


def test_deep_check_catches_a_changed_frame(tmp_path, fake_engine):
    s, q, root = make_q(frames=[0, 10], chunk=5, preroll=0)
    w = run_worker(q, "w0", tmp_path)
    while (got := w.claim()):
        w.run_chunk(*got)
    j = q.job(root)
    man = verify.manifest(q, root)
    assert verify.deep(s, j, man, str(tmp_path / "a"))["ok"]
    s.put("farm/out/j1/0004.png", b"frame 9")  # same size, other content
    bad = verify.deep(s, j, man, str(tmp_path / "b"))
    assert not bad["ok"] and bad["bad"] == [4]


def test_compare_identical_by_hash_without_downloading(tmp_path, fake_engine):
    s = MemStore(B)
    q = Queue(s, "f1", clock=Clock())
    ra = q.submit(job(id="a", frames=[0, 20], chunk=5, preroll=0,
                      output={"prefix": f"s3://{B}/farm/out/a/"}))["root"]
    rb = q.submit(job(id="b", frames=[0, 20], chunk=20, preroll=0,
                      output={"prefix": f"s3://{B}/farm/out/b/"}))["root"]
    w = run_worker(q, "w0", tmp_path)
    while (got := w.claim()):
        w.run_chunk(*got)
    calls = []
    rep = verify.compare(q, ra, rb, str(tmp_path / "cmp"), run=lambda *a, **k: calls.append(a))
    assert rep["identical"] == 20 and rep["measured"] == 0 and not calls
    assert rep["boundaries"] == [5, 10, 15] and rep["missing"] == []
