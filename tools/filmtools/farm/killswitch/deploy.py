"""Deploy, inspect and remove the GPU kill switch (the killswitch-reaper Lambda, its role, its schedule).

Runs where the AWS CLI has the account (kali, profile nani), like the rest of the farm; the account id is read at
run time (sts), never written down. Every command covers ap-south-1 and ap-northeast-1 (--regions narrows it): the
IAM roles are global and shared, while each region gets its own function, schedule, log group and alarms (an alarm
and its ec2:stop action live in the instance's region). From tools/:

    python -m filmtools.farm.killswitch.deploy show                 # the alarm, IAM and schedule JSON it would apply
    python -m filmtools.farm.killswitch.deploy dry-run              # what the reaper would do right now (changes nothing)
    python -m filmtools.farm.killswitch.deploy calibrate --name 'ue-box-b*' --hours 48
    python -m filmtools.farm.killswitch.deploy deploy               # create or update everything (idempotent)
    python -m filmtools.farm.killswitch.deploy invoke               # run the deployed reaper once, print its log
    python -m filmtools.farm.killswitch.deploy --regions ap-south-1 drill-alarm i-0abc --period 60   # a drill box
    python -m filmtools.farm.killswitch.deploy undeploy [--keep-alarms] [--purge-logs] [--dry-run]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import statistics
import sys
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .. import provision
from . import reaper

FUNCTION = "killswitch-reaper"
ROLE = "killswitch-reaper-role"
POLICY = "killswitch-reaper"
SCHEDULE = "killswitch-reaper-schedule"
SCHEDULE_ROLE = "killswitch-reaper-schedule-role"  # EventBridge Scheduler needs a role of its own to invoke
SCHEDULE_POLICY = "killswitch-reaper-invoke"
RATE = "rate(10 minutes)"
IDLE_VCPU = 0.8  # an idle UE editor costs ~0.5 vCPU on any box; box B's lowest busy 5 min was 1.06 vCPU
REGIONS = ("ap-south-1", "ap-northeast-1")  # Mumbai and Tokyo: every region the operator runs GPU boxes in
LOG_GROUP = f"/aws/lambda/{FUNCTION}"
LOG_RETENTION_DAYS = 30
EVENTS_SLR = "AWSServiceRoleForCloudWatchEvents"  # what CloudWatch alarm EC2 actions (stop) run as
GPU_TYPES = ["g*", "p*"]  # g* covers gr*
SRC = Path(reaper.__file__)


# --- the documents ---------------------------------------------------------------------------------------------------
def env_vars(conf: dict) -> dict:
    return {"KILLSWITCH_THRESHOLD": f"{conf['threshold']:g}", "KILLSWITCH_IDLE_VCPU": f"{conf['idle_vcpu']:g}",
            "KILLSWITCH_PERIOD_S": str(conf["period_s"]),
            "KILLSWITCH_PERIODS": str(conf["periods"]), "KILLSWITCH_DEFAULT_TTL_H": f"{conf['default_ttl_h']:g}"}


def lambda_trust() -> dict:
    return {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                                                    "Action": "sts:AssumeRole"}]}


def reaper_policy(account: str, regions: list[str]) -> dict:
    """One role for every region's reaper (IAM is global); each resource is listed per region."""
    return {"Version": "2012-10-17", "Statement": [
        {"Sid": "SeeInstances", "Effect": "Allow", "Action": "ec2:DescribeInstances", "Resource": "*"},
        {"Sid": "StopGpuInstancesOnly", "Effect": "Allow", "Action": "ec2:StopInstances",
         "Resource": [f"arn:aws:ec2:{r}:{account}:instance/*" for r in regions],
         "Condition": {"StringLike": {"ec2:InstanceType": GPU_TYPES}}},
        # DescribeAlarms is a read and takes no resource-level restriction; the writes are held to killswitch-*
        {"Sid": "ReadAlarms", "Effect": "Allow", "Action": "cloudwatch:DescribeAlarms", "Resource": "*"},
        {"Sid": "KillswitchAlarmsOnly", "Effect": "Allow",
         "Action": ["cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms"],
         "Resource": [f"arn:aws:cloudwatch:{r}:{account}:alarm:killswitch-*" for r in regions]},
        {"Sid": "OwnLogs", "Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": [f"arn:aws:logs:{r}:{account}:log-group:{LOG_GROUP}:*" for r in regions]}]}


def scheduler_trust(account: str) -> dict:
    return {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"Service": "scheduler.amazonaws.com"}, "Action": "sts:AssumeRole",
         "Condition": {"StringEquals": {"aws:SourceAccount": account}}}]}


def function_arn(account: str, region: str) -> str:
    return f"arn:aws:lambda:{region}:{account}:function:{FUNCTION}"


def scheduler_policy(account: str, regions: list[str]) -> dict:
    return {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "lambda:InvokeFunction",
                                                    "Resource": [function_arn(account, r) for r in regions]}]}


def schedule_doc(account: str, region: str) -> dict:
    return {"Name": SCHEDULE, "ScheduleExpression": RATE, "State": "ENABLED",
            "Description": "GPU kill switch: arm idle alarms, stop boxes past their TTL, sweep dead alarms",
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": {"Arn": function_arn(account, region),
                       "RoleArn": f"arn:aws:iam::{account}:role/{SCHEDULE_ROLE}",
                       "RetryPolicy": {"MaximumRetryAttempts": 0, "MaximumEventAgeInSeconds": 300}}}


def function_doc(account: str, conf: dict) -> dict:
    return {"FunctionName": FUNCTION, "Runtime": "python3.12", "Handler": "reaper.handler", "MemorySize": 128,
            "Timeout": 60, "Role": f"arn:aws:iam::{account}:role/{ROLE}",
            "Description": "GPU kill switch reaper (claude-film-maker tools/filmtools/farm/killswitch)",
            "Environment": {"Variables": env_vars(conf)}}


def zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo("reaper.py", date_time=(2020, 1, 1, 0, 0, 0))  # stable bytes, stable CodeSha256
        info.external_attr = 0o644 << 16
        z.writestr(info, SRC.read_bytes())
    return buf.getvalue()


# --- the AWS CLI as boto3-shaped clients (for dry-run against the live account) -------------------------------------
class Cli:
    """ec2.describe_instances(**kw) -> aws ec2 describe-instances --cli-input-json kw. The CLI pages for us."""

    def __init__(self, aws, service: str):
        self.aws, self.service = aws, service

    def __getattr__(self, op: str):
        def call(**kw):
            return self.aws(self.service, op.replace("_", "-"), *(["--cli-input-json", json.dumps(kw)] if kw else []))
        return call


class ReadOnly:
    """Refuses any call that is not a describe/list/get: the dry-run's guarantee."""

    def __init__(self, client):
        self.client = client

    def __getattr__(self, op: str):
        if not op.startswith(("describe_", "list_", "get_")):
            raise PermissionError(f"dry-run refused {op}")
        return getattr(self.client, op)


# --- helpers ---------------------------------------------------------------------------------------------------------
def account_of(aws) -> str:
    return aws("sts", "get-caller-identity")["Account"]


def quiet(aws, *args, ok=("ResourceNotFoundException", "NoSuchEntity", "NoSuchEntityException")):
    try:
        return aws(*args)
    except provision.AwsError as e:
        if e.code in ok or any(c in str(e) for c in ok):
            return None
        raise


def ensure_role(aws, name: str, trust: dict, policy_name: str, policy: dict, log) -> bool:
    """Create or update a role and its one inline policy; True if the role is new (IAM needs a moment)."""
    new = quiet(aws, "iam", "get-role", "--role-name", name) is None
    if new:
        aws("iam", "create-role", "--role-name", name, "--assume-role-policy-document", json.dumps(trust),
            "--description", "GPU kill switch (claude-film-maker)")
        log(f"created role {name}")
    else:
        aws("iam", "update-assume-role-policy", "--role-name", name, "--policy-document", json.dumps(trust))
    aws("iam", "put-role-policy", "--role-name", name, "--policy-name", policy_name,
        "--policy-document", json.dumps(policy))
    log(f"role {name}: policy {policy_name} set")
    return new


def drop_role(aws, name: str, log):
    if quiet(aws, "iam", "get-role", "--role-name", name) is None:
        return
    for p in aws("iam", "list-role-policies", "--role-name", name).get("PolicyNames", []):
        aws("iam", "delete-role-policy", "--role-name", name, "--policy-name", p)
    for p in aws("iam", "list-attached-role-policies", "--role-name", name).get("AttachedPolicies", []):
        aws("iam", "detach-role-policy", "--role-name", name, "--policy-arn", p["PolicyArn"])
    aws("iam", "delete-role", "--role-name", name)
    log(f"deleted role {name}")


class Ctx:
    """The regions a command covers, an AWS CLI per region, and the reaper's settings per region."""

    def __init__(self, regions: list[str], profile: str, cli=provision.aws_cli, idle_vcpu: float = IDLE_VCPU):
        self.regions, self.profile, self.cli, self._aws, self._acct = regions, profile, cli, {}, None
        self.idle_vcpu = idle_vcpu

    def aws(self, region: str):
        if region not in self._aws:
            self._aws[region] = self.cli(region, self.profile)
        return self._aws[region]

    def conf(self, region: str) -> dict:
        return reaper.settings({"AWS_REGION": region, "KILLSWITCH_IDLE_VCPU": str(self.idle_vcpu)})

    def account(self) -> str:
        self._acct = self._acct or account_of(self.aws(self.regions[0]))
        return self._acct


# --- commands --------------------------------------------------------------------------------------------------------
def cmd_show(ctx, args, log):
    regions, acct = ctx.regions, ctx.account()
    redact = (lambda d: json.loads(json.dumps(d).replace(acct, "<account>"))) if not args.with_account else (lambda d: d)
    docs = {"regions (each gets its own function, schedule, log group and alarms)": regions,
            f"threshold per box: IDLE_VCPU {ctx.idle_vcpu:g} / vCPUs x 100 (CPU % is a share of all vCPUs)":
                {f"{k} vCPU": reaper.threshold_for({"CpuOptions": {"CoreCount": k // 2, "ThreadsPerCore": 2}},
                                                   ctx.conf(regions[0])) for k in (4, 8, 16, 32, 48, 64, 192)},
            "alarm (per GPU instance, in the instance's region; PutMetricAlarm), e.g. an 8-vCPU box":
                reaper.alarm_spec("i-EXAMPLE", ctx.conf(regions[0]),
                                  reaper.threshold_for({"CpuOptions": {"CoreCount": 4, "ThreadsPerCore": 2}},
                                                       ctx.conf(regions[0]))),
            f"{ROLE} trust (global, shared by every region)": lambda_trust(),
            f"{ROLE} inline policy {POLICY}": reaper_policy(acct, regions),
            f"{SCHEDULE_ROLE} trust (global)": scheduler_trust(acct),
            f"{SCHEDULE_ROLE} inline policy {SCHEDULE_POLICY}": scheduler_policy(acct, regions)}
    for r in regions:
        docs[f"schedule in {r} (EventBridge Scheduler)"] = schedule_doc(acct, r)
        docs[f"function in {r}"] = function_doc(acct, ctx.conf(r))
    docs["logs (per region)"] = {"LogGroup": LOG_GROUP, "RetentionDays": LOG_RETENTION_DAYS}
    docs["service-linked role for alarm EC2 actions"] = EVENTS_SLR
    for k, v in docs.items():
        log(f"## {k}\n{json.dumps(redact(v), indent=2)}\n")


def cmd_dry_run(ctx, args, log):
    for r in ctx.regions:
        dry_run_region(ctx.aws(r), ctx.conf(r), log)


def dry_run_region(aws, conf, log):
    ec2, cw = ReadOnly(Cli(aws, "ec2")), ReadOnly(Cli(aws, "cloudwatch"))
    conf = dict(conf, dry_run=True)
    instances = reaper.all_instances(ec2)
    alarms = reaper.killswitch_alarms(cw)
    now = time.time()
    log(f"== {conf['region']}: GPU instances")
    for i in instances:
        if not reaper.is_gpu(i.get("InstanceType", "")):
            continue
        t = reaper.tags_of(i)
        up = f"up {reaper.uptime_h(i, now):.1f} h" if i["State"]["Name"] == "running" else ""
        al = next((a for a in alarms if a["AlarmName"] == reaper.PREFIX + i["InstanceId"]), None)
        log(f"  {i['InstanceId']}  {i['InstanceType']:<13} {i['State']['Name']:<10} {t.get('Name', ''):<28} "
            f"{reaper.vcpus(i) or '?'} vCPU, CPU < {reaper.threshold_for(i, conf):g} %"
            f"{f' (alarm has {al['Threshold']:g} %)' if al and 'Threshold' in al else ''}  "
            f"TTL {reaper.ttl_hours(i, conf['default_ttl_h']):g} h  {up}"
            f"{'  KillSwitch=' + t[reaper.OPT_OUT_TAG] if reaper.OPT_OUT_TAG in t else ''}"
            f"{'  [armed]' if any(a['AlarmName'] == reaper.PREFIX + i['InstanceId'] for a in alarms) else ''}")
    log(f"killswitch alarms: {len(alarms)}")
    acts = reaper.plan(instances, alarms, conf, now)
    log("the reaper WOULD:" if acts else "the reaper would do nothing")
    for a in acts:
        log(f"  {a['do']:<7} {a['instance']}  {a.get('name', '')}  ({a['why']})")


def cpu_points(aws, iid: str, hours: float, period: int = 300) -> list[dict]:
    end = datetime.now(UTC)
    pts, start = [], end - timedelta(hours=hours)
    while start < end:  # 1440 points per call at most
        stop = min(end, start + timedelta(seconds=period * 1400))
        r = aws("cloudwatch", "get-metric-statistics", "--namespace", "AWS/EC2", "--metric-name", "CPUUtilization",
                "--dimensions", f"Name=InstanceId,Value={iid}", "--start-time", start.isoformat(),
                "--end-time", stop.isoformat(), "--period", str(period),
                "--statistics", "Average", "Minimum", "Maximum")
        pts += r.get("Datapoints", [])
        start = stop
    for p in pts:
        p["t"] = datetime.fromisoformat(p["Timestamp"]).timestamp()
    return sorted(pts, key=lambda p: p["t"])


def would_fire(pts: list[dict], threshold: float, n: int, period: int) -> list[float]:
    """Times at which an n x period alarm would have gone off: n consecutive datapoints (no gap) under threshold.
    A missing point is notBreaching, so a gap breaks the run."""
    fired, run, last = [], 0, None
    for p in pts:
        if last is not None and p["t"] - last > period * 1.5:
            run = 0
        run = run + 1 if p["Average"] < threshold else 0
        last = p["t"]
        if run == n:
            fired.append(p["t"])
            run = 0  # the box is stopped; the next run starts over
    return fired


def busy_runs(pts: list[dict], busy: float, period: int) -> list[list[dict]]:
    """Contiguous stretches with a datapoint at or above `busy` % (a render or a solve), merged across short dips."""
    runs, cur = [], []
    for p in pts:
        if cur and p["t"] - cur[-1]["t"] > period * 1.5:
            runs.append(cur)
            cur = []
        cur.append(p)
    if cur:
        runs.append(cur)
    out = []
    for r in runs:  # inside each contiguous run, take the span from the first to the last busy point
        idx = [k for k, p in enumerate(r) if p["Average"] >= busy]
        if idx:
            out.append(r[idx[0]:idx[-1] + 1])
    return out


def floor_25(pts: list[dict], n: int, period: int) -> float | None:
    """The highest threshold that would NOT have fired over `pts`: the lowest, over every n consecutive contiguous
    datapoints, of their highest average. The alarm fires when all n are under the threshold, i.e. when the
    threshold is above that window's highest point. None if there are never n contiguous points."""
    best = None
    for k in range(len(pts) - n + 1):
        w = pts[k:k + n]
        if w[-1]["t"] - w[0]["t"] > period * (n - 1) * 1.5:
            continue  # a gap: missing data is notBreaching
        m = max(p["Average"] for p in w)
        best = m if best is None else min(best, m)
    return best


def parse_window(text: str) -> tuple[float, float, str]:
    """'2026-11-08T12:00/2026-11-08T14:30[=label]' (UTC) -> (start, end, label)."""
    span, _, label = text.partition("=")
    a, b = span.split("/")
    ts = [datetime.fromisoformat(x).replace(tzinfo=UTC).timestamp() for x in (a, b)]
    return ts[0], ts[1], label or span


def cmd_calibrate(ctx, args, log):
    if not (args.instance or args.name):
        sys.exit("calibrate: give --instance or --name")
    for r in ctx.regions:  # CloudWatch keeps a terminated box's metrics: --instance works after it is gone
        aws, ids = ctx.aws(r), list(args.instance or [])
        if args.name:
            ids += [i["InstanceId"] for i in provision.instances(aws, f"Name=tag:Name,Values={args.name}")]
        calibrate_region(aws, ctx.conf(r), ids, args, log)


def vcpus_of(aws, iid: str, given: int) -> int:
    if given:
        return given
    try:
        r = aws("ec2", "describe-instances", "--instance-ids", iid)
        return reaper.vcpus(r["Reservations"][0]["Instances"][0])
    except (provision.AwsError, IndexError, KeyError):
        return 0


def calibrate_region(aws, conf, ids, args, log):
    n, per = conf["periods"], 300
    fmt = lambda t: datetime.fromtimestamp(t, UTC).strftime("%m-%d %H:%M")
    windows = [parse_window(w) for w in args.work or []]
    for iid in ids:
        pts = cpu_points(aws, iid, args.hours)
        if not pts:
            continue  # not in this region
        nv = vcpus_of(aws, iid, args.vcpus)
        def v(pct, nv=nv):
            return pct * nv / 100 if nv else float("nan")
        log(f"== {conf['region']} {iid}: {nv or '?'} vCPU, {len(pts)} five-minute points over {args.hours:g} h "
            f"(vCPU = % x {nv or '?'} / 100)")
        avgs = [p["Average"] for p in pts]
        q = statistics.quantiles(avgs, n=20) if len(avgs) > 1 else avgs * 19
        log(f"   CPU average %: min {min(avgs):.2f}  p5 {q[0]:.2f}  median {statistics.median(avgs):.2f}  "
            f"p95 {q[-1]:.2f}  max {max(avgs):.2f}   (vCPU: min {v(min(avgs)):.2f}  median "
            f"{v(statistics.median(avgs)):.2f})")
        log("   hourly (UTC)       points   min %   avg %   max %   min vCPU  avg vCPU")
        hours: dict[str, list[float]] = {}
        for p in pts:
            hours.setdefault(fmt(p["t"])[:-3] + ":00", []).append(p["Average"])
        for h, xs in hours.items():
            log(f"   {h}   {len(xs):>3}  {min(xs):7.2f} {statistics.mean(xs):7.2f} {max(xs):7.2f}   "
                f"{v(min(xs)):7.2f}  {v(statistics.mean(xs)):7.2f}")
        spans = [(a, b, lab) for a, b, lab in windows] or [
            (r[0]["t"], r[-1]["t"], f"busy (auto: >= {args.busy:g} %)") for r in busy_runs(pts, args.busy, per)
            if len(r) >= 3]
        log(f"   work windows (the alarm must stay quiet in each): highest safe threshold = the lowest {n}x5-min "
            "stretch's peak")
        for a, b, lab in spans:
            wp = [p for p in pts if a <= p["t"] <= b]
            f = floor_25(wp, n, per)
            low = min((p["Average"] for p in wp), default=float("nan"))
            log(f"   {fmt(a)} .. {fmt(b)}  {lab}: {len(wp)} pts, lowest 5-min {low:.2f} % ({v(low):.2f} vCPU); "
                + (f"safe up to {f:.2f} % = {v(f):.2f} vCPU" if f is not None else f"under {n} contiguous points"))
        cands = args.idle_vcpus or [0.6, 0.7, 0.8, 0.9, 1.0, 1.2]
        log(f"   IDLE_VCPU sweep ({n} x 5 min under it; fires inside work windows must be 0):")
        for c in cands:
            th = (c / nv * 100) if nv else float("nan")
            fired = would_fire(pts, th, n, per)
            bad = [t for t in fired if any(a <= t <= b for a, b, _ in spans)]
            log(f"     {c:>4} vCPU = {th:6.2f} %:  fires {len(fired):>3}, of them in work windows {len(bad)}"
                + (" <- would stop a job at " + ", ".join(fmt(t) for t in bad[:5]) if bad else ""))
        th = conf["threshold"]
        log(f"   today's flat {th:g} % would have fired {len(would_fire(pts, th, n, per))} time(s)")


def cmd_deploy(ctx, args, log):
    aws, acct, regions = ctx.aws(ctx.regions[0]), ctx.account(), ctx.regions
    if quiet(aws, "iam", "get-role", "--role-name", EVENTS_SLR) is None:
        aws("iam", "create-service-linked-role", "--aws-service-name", "events.amazonaws.com")
        log(f"created service-linked role {EVENTS_SLR} (alarm stop actions run as it)")
    new = ensure_role(aws, ROLE, lambda_trust(), POLICY, reaper_policy(acct, regions), log)
    new |= ensure_role(aws, SCHEDULE_ROLE, scheduler_trust(acct), SCHEDULE_POLICY, scheduler_policy(acct, regions), log)
    if new:
        log("waiting 15 s for IAM to see the new roles")
        time.sleep(15)
    for r in regions:
        deploy_region(ctx.aws(r), ctx.conf(r), acct, log)
    log(f"deployed in {', '.join(regions)}: the first runs are within 10 minutes; `invoke` runs them now")


def deploy_region(aws, conf, acct, log):
    region = conf["region"]
    log(f"== {region}")
    try:
        aws("logs", "create-log-group", "--log-group-name", LOG_GROUP)
        log(f"created log group {LOG_GROUP}")
    except provision.AwsError as e:
        if "ResourceAlreadyExists" not in str(e):
            raise
    aws("logs", "put-retention-policy", "--log-group-name", LOG_GROUP, "--retention-in-days", str(LOG_RETENTION_DAYS))
    fdoc = function_doc(acct, conf)
    zb64 = base64.b64encode(zip_bytes()).decode()
    if quiet(aws, "lambda", "get-function", "--function-name", FUNCTION) is None:
        for attempt in range(6):  # a brand-new role can take a little longer to be assumable
            try:
                aws("lambda", "create-function", "--cli-input-json", json.dumps(dict(fdoc, Code={"ZipFile": zb64})))
                break
            except provision.AwsError as e:
                if "cannot be assumed" not in str(e) or attempt == 5:
                    raise
                time.sleep(10)
        log(f"created function {FUNCTION}")
        aws("lambda", "wait", "function-active-v2", "--function-name", FUNCTION)
    else:
        aws("lambda", "update-function-code", "--function-name", FUNCTION, "--cli-input-json",
            json.dumps({"ZipFile": zb64}))
        aws("lambda", "wait", "function-updated-v2", "--function-name", FUNCTION)
        aws("lambda", "update-function-configuration", "--cli-input-json",
            json.dumps({k: v for k, v in fdoc.items() if k != "FunctionName"} | {"FunctionName": FUNCTION}))
        aws("lambda", "wait", "function-updated-v2", "--function-name", FUNCTION)
        log(f"updated function {FUNCTION}")
    sdoc = schedule_doc(acct, region)
    verb = "create-schedule" if quiet(aws, "scheduler", "get-schedule", "--name", SCHEDULE) is None else "update-schedule"
    aws("scheduler", verb, "--cli-input-json", json.dumps(sdoc))
    log(f"{verb.split('-')[0]}d schedule {SCHEDULE} ({RATE})")


def cmd_invoke(ctx, args, log):
    failed = False
    for region in ctx.regions:
        log(f"== {region}")
        failed |= invoke_region(ctx.aws(region), Path(args.out), log)
    if failed:
        sys.exit(1)


def invoke_region(aws, out: Path, log) -> bool:
    r = aws("lambda", "invoke", "--function-name", FUNCTION, "--log-type", "Tail", str(out))
    log(base64.b64decode(r.get("LogResult", "")).decode(errors="replace"))
    log(f"result: {out.read_text()}")
    return bool(r.get("FunctionError"))


def cmd_drill_alarm(ctx, args, log):
    if len(ctx.regions) != 1:
        sys.exit("drill-alarm: name the instance's region (--regions <one>)")
    aws, c = ctx.aws(ctx.regions[0]), dict(ctx.conf(ctx.regions[0]), period_s=args.period)
    th = reaper.threshold_for(aws("ec2", "describe-instances", "--instance-ids", args.instance)
                              ["Reservations"][0]["Instances"][0], c)
    spec = reaper.alarm_spec(args.instance, c, th, drill=True)  # the reaper leaves a drill alarm as it is
    c["threshold"] = th
    aws("cloudwatch", "put-metric-alarm", "--cli-input-json", json.dumps(spec))
    log(f"alarm {spec['AlarmName']}: {c['periods']} x {args.period} s under {c['threshold']:g} %"
        + ("  (1-min periods need detailed monitoring: aws ec2 monitor-instances)" if args.period < 300 else ""))


def would(aws, log):
    """The AWS CLI with every write replaced by a line saying what it would do; reads still run (undeploy --dry-run)."""
    def call(*a, **kw):
        if a[1].startswith(("get-", "list-", "describe-")):
            return aws(*a, **kw)
        log("  WOULD: aws " + " ".join(a))
        return {}
    return call


def cmd_undeploy(ctx, args, log):
    if args.dry_run:
        log("dry-run: nothing is deleted")
        real, say = ctx.aws, log
        ctx.aws = lambda r: would(real(r), say)
        log = lambda s: None if s.startswith("deleted") else say(s)
    for r in ctx.regions:
        log(f"== {r}")
        undeploy_region(ctx.aws(r), args, log)
    aws = ctx.aws(ctx.regions[0])
    drop_role(aws, SCHEDULE_ROLE, log)
    drop_role(aws, ROLE, log)
    log(f"left in place: the service-linked role {EVENTS_SLR} (shared with every EC2 alarm action)"
        + ("" if args.purge_logs else f", the log group {LOG_GROUP} in each region"))


def undeploy_region(aws, args, log):
    quiet(aws, "scheduler", "delete-schedule", "--name", SCHEDULE) is not None and log(f"deleted schedule {SCHEDULE}")
    quiet(aws, "lambda", "delete-function", "--function-name", FUNCTION) is not None and log(f"deleted {FUNCTION}")
    if not args.keep_alarms:
        names = [a["AlarmName"] for a in reaper.killswitch_alarms(Cli(aws, "cloudwatch"))]
        for k in range(0, len(names), 100):
            aws("cloudwatch", "delete-alarms", "--alarm-names", *names[k:k + 100])
        log(f"deleted {len(names)} killswitch alarm(s)")
    if args.purge_logs:
        quiet(aws, "logs", "delete-log-group", "--log-group-name", LOG_GROUP) is not None and log(f"deleted {LOG_GROUP}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m filmtools.farm.killswitch.deploy", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regions", default=",".join(REGIONS),
                    help=f"comma-separated (default {','.join(REGIONS)}); deploy and undeploy want them all, since "
                         "the shared role's policy lists exactly these")
    ap.add_argument("--profile", default="nani")
    ap.add_argument("--idle-vcpu", type=float, default=IDLE_VCPU,
                    help=f"the idle line in vCPUs (default {IDLE_VCPU:g}); 0 = the flat KILLSWITCH_THRESHOLD %%")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--with-account", action="store_true", help="print the account id instead of <account>")
    sub.add_parser("dry-run")
    s = sub.add_parser("calibrate")
    s.add_argument("--instance", action="append")
    s.add_argument("--name", help="a Name tag pattern, e.g. 'ue-box-b*'")
    s.add_argument("--hours", type=float, default=48)
    s.add_argument("--busy", type=float, default=15, help="a 5-min average at or above this is work (default 15 %%)")
    s.add_argument("--work", action="append", help="a known job window, UTC: 2026-11-08T12:00/2026-11-08T14:30=render"
                   " (repeat; without any, windows with a point >= --busy are used)")
    s.add_argument("--vcpus", type=int, default=0, help="the box's vCPUs, if it is gone (read from EC2 otherwise)")
    s.add_argument("--idle-vcpus", type=float, nargs="+", help="IDLE_VCPU values to try (default 0.6 .. 1.2)")
    sub.add_parser("deploy")
    s = sub.add_parser("invoke")
    s.add_argument("--out", default="/tmp/killswitch-invoke.json")
    s = sub.add_parser("drill-alarm")
    s.add_argument("instance")
    s.add_argument("--period", type=int, default=60)
    s = sub.add_parser("undeploy")
    s.add_argument("--keep-alarms", action="store_true")
    s.add_argument("--purge-logs", action="store_true")
    s.add_argument("--dry-run", action="store_true", help="list what it would delete; delete nothing")
    args = ap.parse_args(argv)
    ctx = Ctx([r.strip() for r in args.regions.split(",") if r.strip()], args.profile, idle_vcpu=args.idle_vcpu)
    {"show": cmd_show, "dry-run": cmd_dry_run, "calibrate": cmd_calibrate, "deploy": cmd_deploy,
     "invoke": cmd_invoke, "drill-alarm": cmd_drill_alarm, "undeploy": cmd_undeploy}[args.cmd](
        ctx, args, lambda s: print(s, flush=True))


if __name__ == "__main__":
    main()
