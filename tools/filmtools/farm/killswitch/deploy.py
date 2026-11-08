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
from datetime import datetime, timedelta, timezone
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
REGIONS = ("ap-south-1", "ap-northeast-1")  # Mumbai and Tokyo: every region the operator runs GPU boxes in
LOG_GROUP = f"/aws/lambda/{FUNCTION}"
LOG_RETENTION_DAYS = 30
EVENTS_SLR = "AWSServiceRoleForCloudWatchEvents"  # what CloudWatch alarm EC2 actions (stop) run as
GPU_TYPES = ["g*", "p*"]  # g* covers gr*
SRC = Path(reaper.__file__)


# --- the documents ---------------------------------------------------------------------------------------------------
def env_vars(conf: dict) -> dict:
    return {"KILLSWITCH_THRESHOLD": f"{conf['threshold']:g}", "KILLSWITCH_PERIOD_S": str(conf["period_s"]),
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

    def __init__(self, regions: list[str], profile: str, cli=provision.aws_cli):
        self.regions, self.profile, self.cli, self._aws, self._acct = regions, profile, cli, {}, None

    def aws(self, region: str):
        if region not in self._aws:
            self._aws[region] = self.cli(region, self.profile)
        return self._aws[region]

    def conf(self, region: str) -> dict:
        return reaper.settings({"AWS_REGION": region})

    def account(self) -> str:
        self._acct = self._acct or account_of(self.aws(self.regions[0]))
        return self._acct


# --- commands --------------------------------------------------------------------------------------------------------
def cmd_show(ctx, args, log):
    regions, acct = ctx.regions, ctx.account()
    redact = (lambda d: json.loads(json.dumps(d).replace(acct, "<account>"))) if not args.with_account else (lambda d: d)
    docs = {"regions (each gets its own function, schedule, log group and alarms)": regions,
            "alarm (per GPU instance, in the instance's region; PutMetricAlarm)":
                reaper.alarm_spec("i-EXAMPLE", ctx.conf(regions[0])),
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
        log(f"  {i['InstanceId']}  {i['InstanceType']:<13} {i['State']['Name']:<10} {t.get('Name', ''):<28} "
            f"TTL {reaper.ttl_hours(i, conf['default_ttl_h']):g} h  {up}"
            f"{'  KillSwitch=' + t[reaper.OPT_OUT_TAG] if reaper.OPT_OUT_TAG in t else ''}"
            f"{'  [armed]' if any(a['AlarmName'] == reaper.PREFIX + i['InstanceId'] for a in alarms) else ''}")
    log(f"killswitch alarms: {len(alarms)}")
    acts = reaper.plan(instances, alarms, conf, now)
    log("the reaper WOULD:" if acts else "the reaper would do nothing")
    for a in acts:
        log(f"  {a['do']:<7} {a['instance']}  {a.get('name', '')}  ({a['why']})")


def cpu_points(aws, iid: str, hours: float, period: int = 300) -> list[dict]:
    end = datetime.now(timezone.utc)
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
        p["t"] = datetime.fromisoformat(p["Timestamp"].replace("Z", "+00:00")).timestamp()
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


def cmd_calibrate(ctx, args, log):
    if not (args.instance or args.name):
        sys.exit("calibrate: give --instance or --name")
    for r in ctx.regions:  # CloudWatch keeps a terminated box's metrics: --instance works after it is gone
        aws, ids = ctx.aws(r), list(args.instance or [])
        if args.name:
            ids += [i["InstanceId"] for i in provision.instances(aws, f"Name=tag:Name,Values={args.name}")]
        calibrate_region(aws, ctx.conf(r), ids, args, log)


def calibrate_region(aws, conf, ids, args, log):
    th, n, per = conf["threshold"], conf["periods"], 300
    for iid in ids:
        pts = cpu_points(aws, iid, args.hours)
        fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%m-%d %H:%M")  # noqa: E731
        if not pts:
            continue  # not in this region
        log(f"== {conf['region']} {iid}: {len(pts)} five-minute points over {args.hours:g} h")
        avgs = [p["Average"] for p in pts]
        q = statistics.quantiles(avgs, n=20) if len(avgs) > 1 else avgs * 19
        log(f"   CPU average: min {min(avgs):.2f}  p5 {q[0]:.2f}  median {statistics.median(avgs):.2f}  "
            f"p95 {q[-1]:.2f}  max {max(avgs):.2f}")
        log("   hourly (UTC)       points  min    avg    max   (5-min averages)")
        hours: dict[str, list[float]] = {}
        for p in pts:
            hours.setdefault(fmt(p["t"])[:-3] + ":00", []).append(p["Average"])
        for h, v in hours.items():
            log(f"   {h}   {len(v):>3}  {min(v):6.2f} {statistics.mean(v):6.2f} {max(v):6.2f}")
        for r in busy_runs(pts, args.busy, per):
            if len(r) < 3:
                continue
            low = min(p["Average"] for p in r)
            longest = max((len(x) for x in _below(r, th)), default=0)
            log(f"   busy window {fmt(r[0]['t'])} .. {fmt(r[-1]['t'])} UTC ({len(r) * 5} min): min 5-min avg "
                f"{low:.2f} %, longest run under {th:g} %: {longest * 5} min")
        fired = would_fire(pts, th, n, per)
        log(f"   the alarm ({n} x 5 min under {th:g} %) would have stopped it {len(fired)} time(s)"
            + (": " + ", ".join(fmt(t) + " UTC" for t in fired) if fired else ""))


def _below(run: list[dict], th: float) -> list[list[dict]]:
    out, cur = [], []
    for p in run:
        if p["Average"] < th:
            cur.append(p)
        elif cur:
            out.append(cur)
            cur = []
    return out + ([cur] if cur else [])


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
    spec = reaper.alarm_spec(args.instance, c)
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
        log = lambda s: None if s.startswith("deleted") else say(s)  # noqa: E731  (nothing was)
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
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--with-account", action="store_true", help="print the account id instead of <account>")
    sub.add_parser("dry-run")
    s = sub.add_parser("calibrate")
    s.add_argument("--instance", action="append")
    s.add_argument("--name", help="a Name tag pattern, e.g. 'ue-box-b*'")
    s.add_argument("--hours", type=float, default=48)
    s.add_argument("--busy", type=float, default=15, help="a 5-min average at or above this is work (default 15 %%)")
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
    ctx = Ctx([r.strip() for r in args.regions.split(",") if r.strip()], args.profile)
    {"show": cmd_show, "dry-run": cmd_dry_run, "calibrate": cmd_calibrate, "deploy": cmd_deploy,
     "invoke": cmd_invoke, "drill-alarm": cmd_drill_alarm, "undeploy": cmd_undeploy}[args.cmd](
        ctx, args, lambda s: print(s, flush=True))


if __name__ == "__main__":
    main()
