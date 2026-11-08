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
from datetime import datetime, timezone

PREFIX = "killswitch-idle-"
GPU_FAMILY = re.compile(r"^(g|gr|p)\d")
OPT_OUT_TAG = "KillSwitch"
TTL_TAG = "TTLHours"


def settings(env=None) -> dict:
    env = os.environ if env is None else env
    return {"region": env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "ap-south-1",
            "threshold": float(env.get("KILLSWITCH_THRESHOLD", "4")),
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
    lt = inst["LaunchTime"]  # the last start, not the first launch: a stopped-and-started box starts a new clock
    if isinstance(lt, str):
        lt = datetime.fromisoformat(lt.replace("Z", "+00:00"))
    if lt.tzinfo is None:
        lt = lt.replace(tzinfo=timezone.utc)
    return (now - lt.timestamp()) / 3600


def alarm_spec(instance_id: str, conf: dict) -> dict:
    """The PutMetricAlarm arguments for one instance."""
    n, period = conf["periods"], conf["period_s"]
    return {"AlarmName": PREFIX + instance_id,
            "AlarmDescription": f"kill switch: stop {instance_id} after {n} x {period // 60} min with average CPU "
                                f"under {conf['threshold']:g} % (made by killswitch-reaper)",
            "Namespace": "AWS/EC2", "MetricName": "CPUUtilization",
            "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
            "Statistic": "Average", "Period": period, "EvaluationPeriods": n, "DatapointsToAlarm": n,
            "Threshold": conf["threshold"], "ComparisonOperator": "LessThanThreshold",
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


def plan(instances: list[dict], alarms: list[dict], conf: dict, now: float) -> list[dict]:
    """What to do, as actions: {"do": arm|disarm|stop|delete, "instance": id, "why": ...}. Pure, so it is tested."""
    acts = []
    by_id = {i["InstanceId"]: i for i in instances}
    armed = {a["AlarmName"][len(PREFIX):] for a in alarms}
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
        if iid not in armed:
            acts.append({"do": "arm", "instance": iid, "name": name, "type": itype, "why": "running GPU, no alarm"})
        up, ttl = uptime_h(inst, now), ttl_hours(inst, conf["default_ttl_h"])
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
            if conf["dry_run"]:
                pass
            elif a["do"] == "arm":
                cw.put_metric_alarm(**alarm_spec(a["instance"], conf))
            elif a["do"] in ("disarm", "delete"):
                cw.delete_alarms(AlarmNames=[PREFIX + a["instance"]])
            elif a["do"] == "stop":
                ec2.stop_instances(InstanceIds=[a["instance"]])  # never terminate_instances
            rec["ok"] = True
        except Exception as e:  # one box's failure (e.g. a one-time spot that cannot stop) must not stop the rest
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
               "alarms": len(alarms), "actions": len(done), "failed": sum(not d["ok"] for d in done),
               "dry_run": conf["dry_run"]}
    log(summary)
    return summary


def handler(event, context):
    import boto3
    conf = settings()
    return run(boto3.client("ec2", region_name=conf["region"]), boto3.client("cloudwatch", region_name=conf["region"]),
               conf)
