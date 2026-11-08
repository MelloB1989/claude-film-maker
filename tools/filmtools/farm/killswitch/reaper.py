"""killswitch-reaper: the Lambda that keeps every GPU box in the region on a leash, from inside AWS.

Every 10 minutes (an EventBridge Scheduler schedule) it
  (a) arms an idle alarm (killswitch-idle-<instance-id>) on every running GPU instance that has none: CPU average
      under 4 % for 5 consecutive 5-minute periods stops the box (stop, never terminate);
  (b) stops every running GPU instance whose uptime is over its TTLHours tag (12 h without one);
  (c) deletes killswitch alarms whose instance is terminated or gone;
  (d) logs every action, one JSON line each, to its CloudWatch Logs group.

A GPU instance is one of the g*, gr* and p* families. Nothing else is ever touched, and nothing is ever terminated.
Tag KillSwitch=off opts a box out: no TTL stop, and its idle alarm is deleted (re-armed once the tag goes).

This file is the whole Lambda: standard library plus the boto3 the runtime ships. `run()` takes the EC2 and
CloudWatch clients, so the tests (and `deploy.py dry-run`) drive it with stand-ins.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime

PREFIX = "killswitch-idle-"
GPU_FAMILY = re.compile(r"^(g|gr|p)\d")
OPT_OUT_TAG = "KillSwitch"
TTL_TAG = "TTLHours"


def settings(env=None) -> dict:
    env = os.environ if env is None else env
    return {"region": env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "ap-south-1",
            "threshold": float(env.get("KILLSWITCH_THRESHOLD", "4")),  # flat %, when idle_vcpu is 0 or vCPUs unknown
            # idle measured in vCPUs: CPUUtilization is a share of ALL the box's vCPUs, so an idle editor (~0.5 vCPU)
            # reads 3 % on 16 vCPU but 6 % on 8. The threshold per box is idle_vcpu / vCPUs x 100.
            "idle_vcpu": float(env.get("KILLSWITCH_IDLE_VCPU", "0")),
            "period_s": int(env.get("KILLSWITCH_PERIOD_S", "300")),
            "periods": int(env.get("KILLSWITCH_PERIODS", "5")),
            "default_ttl_h": float(env.get("KILLSWITCH_DEFAULT_TTL_H", "12")),
            "dry_run": env.get("KILLSWITCH_DRY_RUN", "") in ("1", "true", "yes")}


def is_gpu(itype: str) -> bool:
    return bool(GPU_FAMILY.match(itype or ""))


def tags_of(inst: dict) -> dict:
    return {t["Key"]: t["Value"] for t in inst.get("Tags") or []}


def opted_out(inst: dict) -> bool:
    return tags_of(inst).get(OPT_OUT_TAG, "").strip().lower() in ("off", "false", "no", "0")


def ttl_hours(inst: dict, default: float) -> float:
    try:
        v = float(tags_of(inst).get(TTL_TAG, ""))
        return v if v > 0 else default
    except ValueError:
        return default


def uptime_h(inst: dict, now: float) -> float:
    # LaunchTime is the last start, not the first launch: a stopped-and-started box starts a new clock
    return (now - _ts(inst["LaunchTime"])) / 3600


def vcpus(inst: dict) -> int:
    c = inst.get("CpuOptions") or {}
    return int(c.get("CoreCount", 0)) * int(c.get("ThreadsPerCore", 1))


def threshold_for(inst: dict, conf: dict) -> float:
    n = vcpus(inst)
    if conf.get("idle_vcpu", 0) > 0 and n:
        return round(min(50.0, conf["idle_vcpu"] / n * 100), 2)
    return conf["threshold"]


DRILL = "kill switch DRILL"  # an alarm whose description starts so is left as it is (deploy.py drill-alarm)
CHECKED = ("Namespace", "MetricName", "Statistic", "Period", "EvaluationPeriods", "DatapointsToAlarm", "Threshold",
           "ComparisonOperator", "TreatMissingData", "AlarmActions")


def alarm_spec(instance_id: str, conf: dict, threshold: float | None = None, drill: bool = False) -> dict:
    """The PutMetricAlarm arguments for one instance."""
    n, period = conf["periods"], conf["period_s"]
    th = conf["threshold"] if threshold is None else threshold
    return {"AlarmName": PREFIX + instance_id,
            "AlarmDescription": f"{DRILL if drill else 'kill switch'}: stop {instance_id} after {n} x "
                                f"{period // 60} min with average CPU under {th:g} % (made by killswitch-reaper)",
            "Namespace": "AWS/EC2", "MetricName": "CPUUtilization",
            "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
            "Statistic": "Average", "Period": period, "EvaluationPeriods": n, "DatapointsToAlarm": n,
            "Threshold": th, "ComparisonOperator": "LessThanThreshold",
            "TreatMissingData": "notBreaching",
            "ActionsEnabled": True,
            "AlarmActions": [f"arn:aws:automate:{conf['region']}:ec2:stop"]}


def all_instances(ec2) -> list[dict]:
    out, token = [], None
    while True:
        r = ec2.describe_instances(**({"NextToken": token} if token else {}))
        for res in r.get("Reservations", []):
            out.extend(res.get("Instances", []))
        token = r.get("NextToken")
        if not token:
            return out


def killswitch_alarms(cw) -> list[dict]:
    out, token = [], None
    while True:
        kw = {"AlarmNamePrefix": PREFIX, "AlarmTypes": ["MetricAlarm"]}
        r = cw.describe_alarms(**kw, **({"NextToken": token} if token else {}))
        out.extend(r.get("MetricAlarms", []))
        token = r.get("NextToken")
        if not token:
            return out


def stale(alarm: dict, want: dict) -> list[str]:
    """The fields where an existing alarm differs from what it should be (none for a drill alarm)."""
    if (alarm.get("AlarmDescription") or "").startswith(DRILL):
        return []
    out = []
    for k in CHECKED:
        a, w = alarm.get(k), want[k]
        if isinstance(w, float):
            if a is None or abs(float(a) - w) > 0.005:
                out.append(k)
        elif a != w:
            out.append(k)
    return out


def grace_s(conf: dict) -> int:
    return conf["periods"] * conf["period_s"] + 300  # the alarm's window, plus one period for the metric's lag


def _ts(v) -> float:
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    if v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    return v.timestamp()


def stuck(alarm: dict, inst: dict) -> bool:
    """In ALARM since before the box's last start: an alarm acts only on entering ALARM, so it would never fire."""
    if alarm.get("StateValue") != "ALARM" or "StateUpdatedTimestamp" not in alarm:
        return False
    return _ts(alarm["StateUpdatedTimestamp"]) < _ts(inst["LaunchTime"])


def plan(instances: list[dict], alarms: list[dict], conf: dict, now: float) -> list[dict]:
    """What to do, as actions: {"do": arm|rearm|reset|wait|disarm|stop|delete, "instance": id, "why": ...}.
    Pure, so tested. A stopped box's alarm is left as it is; it is brought up to date after its next start."""
    acts = []
    by_id = {i["InstanceId"]: i for i in instances}
    armed = {a["AlarmName"][len(PREFIX):]: a for a in alarms}
    for inst in instances:
        iid, itype, state = inst["InstanceId"], inst.get("InstanceType", ""), inst["State"]["Name"]
        if not is_gpu(itype):
            continue
        name = tags_of(inst).get("Name", "")
        if opted_out(inst):
            if iid in armed:
                acts.append({"do": "disarm", "instance": iid, "name": name, "type": itype,
                             "why": f"tag {OPT_OUT_TAG}=off"})
            continue
        if state != "running":
            continue
        th, up = threshold_for(inst, conf), uptime_h(inst, now)
        al = armed.get(iid)
        # Grace: writing an alarm makes CloudWatch evaluate the datapoints it already holds, which on a box started
        # less than n periods ago include the idle ones from before its last stop; that once stopped a box 100 s
        # after a restart. So nothing is armed, re-armed or reset until every point in the window is from this run.
        if up * 3600 < grace_s(conf):
            if al is None or stale(al, alarm_spec(iid, conf, th)) or stuck(al, inst):
                acts.append({"do": "wait", "instance": iid, "name": name, "type": itype,
                             "why": f"up {up * 60:.0f} min < {grace_s(conf) // 60} min grace"})
        elif al is None:
            acts.append({"do": "arm", "instance": iid, "name": name, "type": itype, "threshold": th,
                         "why": f"running GPU, no alarm (CPU < {th:g} % = {vcpus(inst) or '?'} vCPU box)"})
        elif stuck(al, inst):
            acts.append({"do": "reset", "instance": iid, "name": name, "type": itype, "threshold": th,
                         "why": "alarm in ALARM since before this start: it would never fire again"})
        elif diff := stale(al, alarm_spec(iid, conf, th)):
            acts.append({"do": "rearm", "instance": iid, "name": name, "type": itype, "threshold": th,
                         "why": f"alarm differs in {', '.join(diff)} (now CPU < {th:g} %)"})
        ttl = ttl_hours(inst, conf["default_ttl_h"])
        if up > ttl:
            acts.append({"do": "stop", "instance": iid, "name": name, "type": itype,
                         "why": f"up {up:.1f} h > TTL {ttl:g} h"})
    for iid in sorted(armed):
        inst = by_id.get(iid)
        if inst is None or inst["State"]["Name"] == "terminated":
            acts.append({"do": "delete", "instance": iid,
                         "why": "instance terminated" if inst else "instance not found"})
    return acts


def apply(acts: list[dict], ec2, cw, conf: dict, log) -> list[dict]:
    done = []
    for a in acts:
        rec = dict(a, dry_run=conf["dry_run"])
        try:
            if conf["dry_run"] or a["do"] == "wait":
                pass
            elif a["do"] in ("arm", "rearm"):
                cw.put_metric_alarm(**alarm_spec(a["instance"], conf, a.get("threshold")))
            elif a["do"] == "reset":  # a new alarm starts from INSUFFICIENT_DATA, so it can enter ALARM again
                cw.delete_alarms(AlarmNames=[PREFIX + a["instance"]])
                cw.put_metric_alarm(**alarm_spec(a["instance"], conf, a.get("threshold")))
            elif a["do"] in ("disarm", "delete"):
                cw.delete_alarms(AlarmNames=[PREFIX + a["instance"]])
            elif a["do"] == "stop":
                ec2.stop_instances(InstanceIds=[a["instance"]])  # never terminate_instances
            rec["ok"] = True
        except Exception as e:  # noqa: BLE001  one box failing (a one-time spot cannot stop) must not stop the rest
            rec["ok"], rec["error"] = False, f"{type(e).__name__}: {e}"[:500]
        log(rec)
        done.append(rec)
    return done


def run(ec2, cw, conf: dict, now: float | None = None, log=None) -> dict:
    log = log or (lambda rec: print(json.dumps(rec, default=str)))
    now = time.time() if now is None else now
    instances, alarms = all_instances(ec2), killswitch_alarms(cw)
    done = apply(plan(instances, alarms, conf, now), ec2, cw, conf, log)
    gpus = [i for i in instances if is_gpu(i.get("InstanceType", ""))]
    summary = {"summary": True, "gpu_instances": len(gpus),
               "gpu_running": sum(i["State"]["Name"] == "running" for i in gpus),
               "alarms": len(alarms), "actions": sum(d["do"] != "wait" for d in done),
               "waiting": sum(d["do"] == "wait" for d in done), "failed": sum(not d["ok"] for d in done),
               "dry_run": conf["dry_run"]}
    log(summary)
    return summary


def handler(event, context):
    import boto3
    conf = settings()
    return run(boto3.client("ec2", region_name=conf["region"]), boto3.client("cloudwatch", region_name=conf["region"]),
               conf)
