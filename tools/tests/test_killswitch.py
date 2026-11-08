"""The GPU kill switch: the reaper's decisions and calls (stand-in EC2 and CloudWatch clients), the IAM documents
and the calibration maths. Nothing here touches AWS."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime

import pytest

from filmtools.farm.killswitch import deploy, reaper

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC).timestamp()  # on a 5-minute boundary
CONF = reaper.settings({"AWS_REGION": "ap-south-1"})
VCONF = dict(CONF, idle_vcpu=0.8)
MIN = 60


def inst(iid, itype="g6e.4xlarge", state="running", up_h=1.0, vcpu=16, **tags):
    lt = datetime.fromtimestamp(NOW - up_h * 3600, UTC)
    return {"InstanceId": iid, "InstanceType": itype, "State": {"Name": state}, "LaunchTime": lt,
            "CpuOptions": {"CoreCount": vcpu // 2, "ThreadsPerCore": 2},
            "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}


class FakeEC2:
    def __init__(self, instances, page=2, fail_stop=()):
        self.instances, self.page, self.fail_stop, self.stopped = instances, page, set(fail_stop), []

    def describe_instances(self, NextToken=None):
        k = int(NextToken or 0)
        chunk = self.instances[k:k + self.page]
        r = {"Reservations": [{"Instances": chunk}]}
        if k + self.page < len(self.instances):
            r["NextToken"] = str(k + self.page)
        return r

    def stop_instances(self, InstanceIds):
        if set(InstanceIds) & self.fail_stop:
            raise RuntimeError("UnsupportedOperation: one-time spot")
        self.stopped += InstanceIds

    def terminate_instances(self, **kw):  # the reaper must never get here
        raise AssertionError("terminate called")


class FakeCW:
    """CloudWatch: 5-minute CPU averages per instance ({id: {period start: avg}}) and the old alarms."""

    def __init__(self, names=(), cpu=None):
        self.alarms = {n: {"AlarmName": n} for n in names}
        self.cpu = cpu or {}
        self.reads = []

    def describe_alarms(self, AlarmNamePrefix, AlarmTypes, NextToken=None):
        names = sorted(n for n in self.alarms if n.startswith(AlarmNamePrefix))
        k = int(NextToken or 0)
        r = {"MetricAlarms": [self.alarms[n] for n in names[k:k + 1]]}
        if k + 1 < len(names):
            r["NextToken"] = str(k + 1)
        return r

    def get_metric_statistics(self, Namespace, MetricName, Dimensions, StartTime, EndTime, Period, Statistics):
        assert (Namespace, MetricName, Period, Statistics) == ("AWS/EC2", "CPUUtilization", 300, ["Average"])
        iid = Dimensions[0]["Value"]
        a, b = reaper._ts(StartTime), reaper._ts(EndTime)
        self.reads.append((iid, a, b))
        return {"Datapoints": [{"Timestamp": datetime.fromtimestamp(t, UTC), "Average": v}
                               for t, v in self.cpu.get(iid, {}).items() if a <= t < b]}

    def delete_alarms(self, AlarmNames):
        for n in AlarmNames:
            assert n.startswith("killswitch-")
            self.alarms.pop(n)

    def put_metric_alarm(self, **kw):  # the reaper must never create an alarm
        raise AssertionError("put_metric_alarm called")


def series(start, avgs, step=300):
    return {start + k * step: v for k, v in enumerate(avgs)}


def go(ec2, cw, now=NOW, **conf):
    logs = []
    s = reaper.run(ec2, cw, dict(VCONF, **conf), now=now, log=logs.append)
    return s, logs


def stops(logs):
    return [r["instance"] for r in logs if r.get("do") == "stop"]


@pytest.mark.parametrize("t,gpu", [("g6e.4xlarge", True), ("gr6.4xlarge", True), ("g4dn.xlarge", True),
                                   ("g5g.xlarge", True), ("p5.48xlarge", True), ("p4d.24xlarge", True),
                                   ("t3.micro", False), ("t4g.nano", False), ("c7g.large", False),
                                   ("m5.xlarge", False), ("inf2.xlarge", False), ("", False)])
def test_gpu_families(t, gpu):
    assert reaper.is_gpu(t) is gpu


# --- the idle rule -------------------------------------------------------------------------------------------------
def test_idle_box_is_stopped_busy_box_is_not():
    # two 8-vCPU boxes up 1 h: line 10 %. One idles at 6 % (an editor, ~0.5 vCPU), one works at 14-17 %
    idle, busy = inst("i-idle", vcpu=8), inst("i-busy", vcpu=8)
    cw = FakeCW(cpu={"i-idle": series(NOW - 3600, [6.0] * 12), "i-busy": series(NOW - 3600, [15.0] * 12)})
    ec2 = FakeEC2([idle, busy])
    _, logs = go(ec2, cw)
    assert ec2.stopped == ["i-idle"]
    assert "idle 5 x 5 min under 10 %" in next(r["why"] for r in logs if r.get("do") == "stop")


def test_one_busy_period_in_the_window_saves_the_box():
    cw = FakeCW(cpu={"i-1": series(NOW - 3600, [6.0] * 9 + [25.0] + [6.0] * 2)})  # the 3rd newest is busy
    ec2 = FakeEC2([inst("i-1", vcpu=8)])
    go(ec2, cw)
    assert ec2.stopped == []


def test_restart_after_idle_then_busy_must_not_stop():
    """Box T, 08 Nov: idle at 6-9 % until a stop, restarted 3 min ago, busy since. CloudWatch still holds the pre-stop
    idle points; the alarm design was judged on them and stopped the box. The reaper ignores every period that began
    before the start, so it does not stop it, however long it has been up, while it is busy."""
    start = NOW - 3 * MIN
    pre = series(start - 40 * MIN, [6.0, 7.0, 6.0, 6.0, 9.0, 8.0])  # pre-stop idle, then the box was stopped
    for up_min in (3, 10, 20, 40, 90):
        now = start + up_min * MIN
        post = series(start - start % 300 + 300, [15.0] * (up_min // 5))  # busy since the start
        t = inst("i-t", vcpu=8)
        t["LaunchTime"] = datetime.fromtimestamp(start, UTC)
        ec2 = FakeEC2([t])
        go(ec2, FakeCW(cpu={"i-t": pre | post}), now=now)
        assert ec2.stopped == [], f"stopped {up_min} min after a restart"


def test_restart_then_idle_must_stop_once_it_has_25_min_of_its_own():
    start = NOW - 3 * MIN  # 11:57: mid-period, so the 11:55 period straddles the start and does not count
    pre = series(start - 40 * MIN, [6.0] * 7)
    t = inst("i-t", vcpu=8)
    t["LaunchTime"] = datetime.fromtimestamp(start, UTC)
    first_full = start - start % 300 + 300  # 12:00
    stopped_at = None
    for up_min in range(3, 60):
        now = start + up_min * MIN
        post = series(first_full, [6.0] * max(0, int((now - first_full) // 300)))  # idle since the start
        ec2 = FakeEC2([t])
        go(ec2, FakeCW(cpu={"i-t": pre | post}), now=now)
        if ec2.stopped:
            stopped_at = up_min
            break
    # 5 full periods 12:00-12:25 exist once 12:25 has passed: 28 min after the 11:57 start, never earlier than 25
    assert stopped_at == 28


def test_a_gap_or_old_data_is_not_idle():
    t = inst("i-1", vcpu=8)
    gap = series(NOW - 3600, [6.0] * 12)
    del gap[NOW - 3 * 300]
    assert reaper.idle_verdict([{"t": k, "avg": v} for k, v in gap.items()], NOW - 3600, NOW, VCONF, 10.0)[0] is False
    old = series(NOW - 3600, [6.0] * 6)  # nothing in the last 30 min (metrics delayed)
    ok, why = reaper.idle_verdict([{"t": k, "avg": v} for k, v in old.items()], NOW - 3600, NOW, VCONF, 10.0)
    assert not ok and why == "no recent datapoint"
    ec2 = FakeEC2([t])
    go(ec2, FakeCW(cpu={}))  # no data at all: not idle
    assert ec2.stopped == []


def test_reads_cpu_only_since_the_start_and_only_for_boxes_worth_reading():
    boxes = [inst("i-up", vcpu=8), inst("i-young", vcpu=8, up_h=20 / 60), inst("i-off", vcpu=8, KillSwitch="off"),
             inst("i-stopped", vcpu=8, state="stopped"), inst("i-cpu", "c7i.4xlarge")]
    cw = FakeCW()
    go(FakeEC2(boxes), cw)
    assert [r[0] for r in cw.reads] == ["i-up"]
    _, a, _ = cw.reads[0]
    assert a >= NOW - 3600 - 300 and a >= NOW - 9 * 300  # never before the start (rounded to its period)


def test_a_failed_read_is_not_idle_and_is_logged():
    class Broken(FakeCW):
        def get_metric_statistics(self, **kw):
            raise RuntimeError("Throttling")
    ec2 = FakeEC2([inst("i-1", vcpu=8)])
    s, logs = go(ec2, Broken())
    assert ec2.stopped == [] and s["failed"] == 1 and logs[0]["note"] == "cpu read failed"


# --- TTL, opt-out, sweep, safety ------------------------------------------------------------------------------------
def test_ttl_stops_with_tag_and_default():
    ec2 = FakeEC2([inst("i-1", up_h=13), inst("i-2", up_h=11), inst("i-3", up_h=3, TTLHours="2"),
                   inst("i-4", up_h=30, TTLHours="48"), inst("i-5", up_h=13, TTLHours="junk"),
                   inst("i-6", "m5.xlarge", up_h=500)])
    busy = {f"i-{k}": series(NOW - 3600, [30.0] * 12) for k in range(1, 7)}
    go(ec2, FakeCW(cpu=busy))
    assert sorted(ec2.stopped) == ["i-1", "i-3", "i-5"]


def test_opt_out_skips_both_stops():
    ec2 = FakeEC2([inst("i-1", up_h=40, KillSwitch="off"), inst("i-2", vcpu=8, KillSwitch="OFF")])
    go(ec2, FakeCW(cpu={"i-2": series(NOW - 3600, [1.0] * 12)}))
    assert ec2.stopped == []


def test_never_touches_a_non_gpu_box():
    ec2 = FakeEC2([inst("i-cpu", "t4g.nano", up_h=500, vcpu=2), inst("i-c7", "c7i.4xlarge", up_h=20)])
    go(ec2, FakeCW(cpu={"i-cpu": series(NOW - 3600, [0.1] * 12)}))
    assert ec2.stopped == []


def test_sweeps_the_first_designs_alarms_and_never_creates_one():
    cw = FakeCW(["killswitch-idle-i-1", "killswitch-idle-i-gone"])
    _, logs = go(FakeEC2([inst("i-1", vcpu=8)]), cw)
    assert cw.alarms == {}
    assert sorted(r["instance"] for r in logs if r.get("do") == "delete") == ["i-1", "i-gone"]


def test_one_failure_does_not_stop_the_rest():
    ec2 = FakeEC2([inst("i-1", up_h=20), inst("i-2", up_h=20)], fail_stop={"i-1"})
    s, logs = go(ec2, FakeCW())
    assert ec2.stopped == ["i-2"] and s["failed"] == 1
    bad = [r for r in logs if not r.get("ok", True)]
    assert bad[0]["instance"] == "i-1" and "UnsupportedOperation" in bad[0]["error"]


def test_dry_run_changes_nothing():
    ec2 = FakeEC2([inst("i-1", up_h=20), inst("i-2", vcpu=8)])
    cw = FakeCW(["killswitch-idle-i-9"], cpu={"i-2": series(NOW - 3600, [6.0] * 12)})
    s, logs = go(ec2, cw, dry_run=True)
    assert ec2.stopped == [] and "killswitch-idle-i-9" in cw.alarms
    assert sorted((r["do"], r["instance"]) for r in logs if "do" in r) == [("delete", "i-9"), ("stop", "i-1"),
                                                                           ("stop", "i-2")]
    assert s["dry_run"]


def test_launch_time_as_cli_string():
    i = inst("i-1")
    i["LaunchTime"] = datetime.fromtimestamp(NOW - 7200, UTC).isoformat().replace("+00:00", "Z")
    assert reaper.uptime_h(i, NOW) == pytest.approx(2.0)


def test_handler_reads_env(monkeypatch):
    monkeypatch.setenv("KILLSWITCH_IDLE_VCPU", "0.8")
    monkeypatch.setenv("KILLSWITCH_DEFAULT_TTL_H", "6")
    c = reaper.settings()
    assert c["idle_vcpu"] == 0.8 and c["default_ttl_h"] == 6 and c["periods"] == 5 and not c["dry_run"]


# --- deploy ----------------------------------------------------------------------------------------------------------
ACCT = "000000000000"


def test_reaper_policy_cannot_terminate_or_touch_non_gpu():
    p = deploy.reaper_policy(ACCT, ["ap-south-1", "ap-northeast-1"])
    actions = [a for s in p["Statement"] for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])]
    assert not any("Terminate" in a for a in actions)
    assert set(actions) == {"ec2:DescribeInstances", "ec2:StopInstances", "cloudwatch:GetMetricStatistics",
                            "cloudwatch:DescribeAlarms", "cloudwatch:DeleteAlarms", "logs:CreateLogStream",
                            "logs:PutLogEvents"}  # no PutMetricAlarm: the reaper creates no alarm
    stop = next(s for s in p["Statement"] if s["Action"] == "ec2:StopInstances")
    assert stop["Condition"] == {"StringLike": {"ec2:InstanceType": ["g*", "p*"]}}
    w = next(s for s in p["Statement"] if s["Action"] == "cloudwatch:DeleteAlarms")
    assert w["Resource"] == [f"arn:aws:cloudwatch:{r}:{ACCT}:alarm:killswitch-*" for r in ("ap-south-1",
                                                                                             "ap-northeast-1")]
    assert stop["Resource"] == [f"arn:aws:ec2:{r}:{ACCT}:instance/*" for r in ("ap-south-1", "ap-northeast-1")]


def test_schedule_and_function_docs():
    s = deploy.schedule_doc(ACCT, "ap-south-1")
    assert s["ScheduleExpression"] == "rate(10 minutes)" and s["Name"] == "killswitch-reaper-schedule"
    assert s["Target"]["Arn"].endswith(":function:killswitch-reaper")
    f = deploy.function_doc(ACCT, CONF)
    assert (f["Runtime"], f["MemorySize"], f["Handler"]) == ("python3.12", 128, "reaper.handler")
    assert f["Role"].endswith(":role/killswitch-reaper-role")


def test_zip_is_the_reaper_alone_and_stable():
    z = deploy.zip_bytes()
    assert z == deploy.zip_bytes()
    with zipfile.ZipFile(io.BytesIO(z)) as zf:
        assert zf.namelist() == ["reaper.py"]
        src = zf.read("reaper.py").decode()
    assert "def handler" in src and "from ." not in src and "import filmtools" not in src


def test_dry_run_client_refuses_writes():
    calls = []
    ro = deploy.ReadOnly(deploy.Cli(lambda *a: calls.append(a) or {}, "ec2"))
    ro.describe_instances()
    with pytest.raises(PermissionError):
        ro.stop_instances(InstanceIds=["i-1"])
    assert calls == [("ec2", "describe-instances")]


def test_cli_shim_maps_kwargs():
    calls = []
    deploy.Cli(lambda *a: calls.append(a) or {}, "cloudwatch").describe_alarms(AlarmNamePrefix="killswitch-idle-")
    assert calls[0][:3] == ("cloudwatch", "describe-alarms", "--cli-input-json")
    assert json.loads(calls[0][3]) == {"AlarmNamePrefix": "killswitch-idle-"}


def pts(avgs, start=NOW, step=300):
    return [{"t": start + k * step, "Average": a} for k, a in enumerate(avgs)]


def test_would_fire_needs_five_contiguous_points():
    assert deploy.would_fire(pts([3.2] * 4 + [25] + [3.2] * 4), 4, 5, 300) == []
    assert len(deploy.would_fire(pts([3.2] * 5), 4, 5, 300)) == 1
    assert len(deploy.would_fire(pts([3.2] * 10), 4, 5, 300)) == 2
    gap = pts([3.2] * 3) + pts([3.2] * 3, start=NOW + 3600)  # missing data in between: notBreaching
    assert deploy.would_fire(gap, 4, 5, 300) == []


def test_busy_runs_span_first_to_last_busy_point():
    r = deploy.busy_runs(pts([3, 3, 30, 5, 28, 3, 3]), 15, 300)
    assert [p["Average"] for p in r[0]] == [30, 5, 28]


class FakeAws:
    """The AWS CLI per region for deploy/undeploy: nothing exists until created; records every call."""

    def __init__(self):
        self.calls, self.made = [], set()

    def cli(self, region, profile):
        def aws(*a):
            self.calls.append((region, *a[:2]))
            svc, op = a[0], a[1]
            key = (region if svc not in ("iam", "sts") else "global", svc, a[3] if len(a) > 3 else "")
            if op == "get-caller-identity":
                return {"Account": ACCT}
            if op.startswith("get-"):
                if key not in self.made:
                    raise deploy.provision.AwsError(f"aws {svc} {op}: (NoSuchEntity) none", "NoSuchEntity")
                return {}
            if op.startswith("create-"):
                self.made.add(key)
            if op == "describe-alarms":
                return {"MetricAlarms": []}
            return {}
        return aws


def test_deploy_covers_both_regions_roles_once(monkeypatch):
    monkeypatch.setattr(deploy.time, "sleep", lambda s: None)
    f = FakeAws()
    ctx = deploy.Ctx(list(deploy.REGIONS), "nani", cli=f.cli)
    deploy.cmd_deploy(ctx, None, lambda s: None)
    ops = [(r, svc, op) for r, svc, op in f.calls]
    for r in ("ap-south-1", "ap-northeast-1"):
        assert (r, "lambda", "create-function") in ops
        assert (r, "scheduler", "create-schedule") in ops
        assert (r, "logs", "create-log-group") in ops
    assert sum(op == "create-role" for _, _, op in ops) == 2  # the reaper's and the scheduler's, once each
    assert not any("terminate" in op or "run-instances" in op for _, _, op in ops)


def test_undeploy_covers_both_regions(monkeypatch):
    f = FakeAws()
    ctx = deploy.Ctx(list(deploy.REGIONS), "nani", cli=f.cli)
    args = type("A", (), {"keep_alarms": False, "purge_logs": True, "dry_run": False})()
    deploy.cmd_undeploy(ctx, args, lambda s: None)
    regions = {r for r, svc, op in f.calls if op == "describe-alarms"}
    assert regions == {"ap-south-1", "ap-northeast-1"}


def test_undeploy_dry_run_writes_nothing():
    f = FakeAws()
    f.made |= {("global", "iam", deploy.ROLE), ("global", "iam", deploy.SCHEDULE_ROLE)}  # the roles exist
    ctx = deploy.Ctx(list(deploy.REGIONS), "nani", cli=f.cli)
    args = type("A", (), {"keep_alarms": False, "purge_logs": True, "dry_run": True})()
    out = []
    deploy.cmd_undeploy(ctx, args, out.append)
    assert all(op.startswith(("get-", "list-", "describe-")) for _, _, op in f.calls)
    would = [o for o in out if "WOULD" in o]
    assert sum("delete-schedule" in o for o in would) == 2 and sum("delete-function" in o for o in would) == 2
    assert any("iam delete-role --role-name killswitch-reaper-role" in o for o in would)




@pytest.mark.parametrize("vcpu,th", [(4, 20.0), (8, 10.0), (16, 5.0), (192, 0.42), (0, 4.0)])
def test_threshold_scales_with_vcpus(vcpu, th):
    i = inst("i-1", vcpu=vcpu)
    if not vcpu:
        del i["CpuOptions"]
    assert reaper.threshold_for(i, VCONF) == th
    assert reaper.threshold_for(i, CONF) == 4.0  # idle_vcpu 0: the flat line


def test_idle_editor_reads_the_same_in_vcpus():
    # box B idle 3.2 % of 16 vCPU and box T idle 6 % of 8 vCPU are both ~0.5 vCPU: both now under their lines
    assert 3.2 < reaper.threshold_for(inst("b", vcpu=16), VCONF) and 6.0 < reaper.threshold_for(inst("t", vcpu=8),
                                                                                                VCONF)




def test_floor_25_is_the_highest_threshold_that_stays_quiet():
    p = pts([30, 9, 7, 8, 6, 9, 30])
    f = deploy.floor_25(p, 5, 300)
    assert f == 9  # windows [30,9,7,8,6]=30, [9,7,8,6,9]=9, [7,8,6,9,30]=30
    assert deploy.would_fire(p, f, 5, 300) == [] and len(deploy.would_fire(p, f + 0.01, 5, 300)) == 1
    assert deploy.floor_25(pts([3, 3, 3]), 5, 300) is None


def test_calibrate_sweep_flags_a_job_it_would_stop():
    start = NOW - 3600 * 3
    avgs = [3.0] * 10 + [20, 9, 8, 9, 9, 8, 25] + [3.0] * 10  # idle (0.24 vCPU on 8), a job dipping to 0.64, idle
    dps = [{"Timestamp": datetime.fromtimestamp(start + k * 300, UTC).isoformat(), "Average": a}
           for k, a in enumerate(avgs)]
    aws = lambda *a: {"Datapoints": dps} if a[1] == "get-metric-statistics" else {}
    args = type("A", (), {"hours": 3, "work": [
        datetime.fromtimestamp(start + 10 * 300, UTC).strftime("%Y-%m-%dT%H:%M") + "/"
        + datetime.fromtimestamp(start + 16 * 300, UTC).strftime("%Y-%m-%dT%H:%M") + "=solve"],
        "vcpus": 8, "idle_vcpus": [0.6, 0.8], "busy": 15})()
    out = []
    deploy.calibrate_region(aws, dict(VCONF), ["i-1"], args, out.append)
    text = "\n".join(out)
    assert "safe up to 9.00 % = 0.72 vCPU" in text
    assert "0.6 vCPU =   7.50 %:  fires   4, of them in work windows 0" in text
    assert "0.8 vCPU =  10.00 %:" in text and "would stop a job" in text


def test_work_window_can_name_its_box():
    a, b, lab, iid = deploy.parse_window("i-0abc@2026-11-08T12:00/2026-11-08T12:30=render")
    assert (b - a, lab, iid) == (1800, "render", "i-0abc")
    assert deploy.parse_window("2026-11-08T12:00/2026-11-08T12:30")[2:] == ("2026-11-08T12:00/2026-11-08T12:30", "")
