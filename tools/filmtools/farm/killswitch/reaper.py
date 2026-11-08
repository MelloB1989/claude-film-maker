"""killswitch-reaper: the Lambda that keeps every GPU box in the region on a leash, from inside AWS.

Every 10 minutes (an EventBridge Scheduler schedule) it
  (a) stops every running GPU instance that has been idle for the last 5 five-minute periods: average CPU under
      IDLE_VCPU (0.8) vCPUs in each, counting ONLY periods that began after the box's last start;
  (b) stops every running GPU instance whose uptime is over its TTLHours tag (12 h without one);
  (c) deletes any killswitch-idle-* CloudWatch alarm (the first design's; see below);
  (d) logs every action, one JSON line each, to its CloudWatch Logs group.

Why the reaper judges idleness itself rather than a CloudWatch alarm with an ec2:stop action: an alarm evaluates
the most recent datapoints it can FIND, reaching back past a gap, and TreatMissingData applies only when it finds
too few. So a box restarted after an idle stretch was judged on its pre-stop points and stopped 2-3 minutes after
the start (box T, twice, 08 Nov). Here every datapoint whose period began before LaunchTime (the last start) is
ignored, so a restarted box always gets its full 25 minutes.

A GPU instance is one of the g*, gr* and p* families. Nothing else is ever touched, and nothing is ever terminated.
Tag KillSwitch=off opts a box out of both stops.

This file is the whole Lambda: standard library plus the boto3 the runtime ships. `run()` takes the EC2 and
CloudWatch clients, so the tests (and `deploy.py dry-run`) drive it with stand-ins.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from itertools import pairwise

PREFIX = "killswitch-idle-"  # the first design's alarms, swept
GPU_FAMILY = re.compile(r"^(g|gr|p)\d")
OPT_OUT_TAG = "KillSwitch"
TTL_TAG = "TTLHours"
MAX_LAG_S = 900  # the newest complete period must have ended at most this long ago (basic monitoring lags 5-10 min)


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


def _ts(v) -> float:
    if isinstance(v, str):
        v = datetime.fromisoformat(v)  # 3.11+ reads the trailing Z
    if v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    return v.timestamp()


def started(inst: dict) -> float:
    return _ts(inst["LaunchTime"])  # the last start, not the first launch: a stopped-and-started box starts anew


def uptime_h(inst: dict, now: float) -> float:
    return (now - started(inst)) / 3600


def vcpus(inst: dict) -> int:
    c = inst.get("CpuOptions") or {}
    return int(c.get("CoreCount", 0)) * int(c.get("ThreadsPerCore", 1))


def threshold_for(inst: dict, conf: dict) -> float:
    n = vcpus(inst)
    if conf.get("idle_vcpu", 0) > 0 and n:
        return round(min(50.0, conf["idle_vcpu"] / n * 100), 2)
    return conf["threshold"]


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


def cpu_since_start(cw, inst: dict, conf: dict, now: float) -> list[dict]:
    """The box's 5-minute CPU averages since its last start (a few periods more than the window, at most)."""
    per = conf["period_s"]
    start = max(started(inst), now - (conf["periods"] + 4) * per)
    r = cw.get_metric_statistics(
        Namespace="AWS/EC2", MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": inst["InstanceId"]}],
        StartTime=datetime.fromtimestamp(start - start % per, UTC).isoformat(),
        EndTime=datetime.fromtimestamp(now, UTC).isoformat(), Period=per, Statistics=["Average"])
    return [{"t": _ts(p["Timestamp"]), "avg": float(p["Average"])} for p in r.get("Datapoints", [])]


def idle_verdict(points: list[dict], launched: float, now: float, conf: dict, th: float) -> tuple[bool, str]:
    """(idle?, why). Idle = the newest `periods` complete periods, all begun at or after the last start, back to back,
    the newest ended within MAX_LAG_S, and every one averaging under `th` %. Anything less is not idle."""
    n, per = conf["periods"], conf["period_s"]
    pts = sorted((p for p in points if p["t"] >= launched and p["t"] + per <= now), key=lambda p: p["t"])
    if len(pts) < n:
        return False, f"{len(pts)} of {n} periods since the start"
    last = pts[-n:]
    if any(b["t"] - a["t"] != per for a, b in pairwise(last)):
        return False, "a gap in the last periods"
    if now - (last[-1]["t"] + per) > MAX_LAG_S:
        return False, "no recent datapoint"
    vals = ", ".join(f"{p['avg']:.2f}" for p in last)
    if all(p["avg"] < th for p in last):
        return True, f"idle {n} x {per // 60} min under {th:g} %: {vals}"
    return False, f"busy ({vals})"


def plan(instances: list[dict], alarms: list[dict], cpu: dict, conf: dict, now: float) -> list[dict]:
    """What to do, as actions: {"do": stop|delete, "instance": id, "why": ...}. `cpu` maps an instance id to its
    points (cpu_since_start). Pure, so it is tested."""
    acts = []
    for inst in instances:
        iid, itype, state = inst["InstanceId"], inst.get("InstanceType", ""), inst["State"]["Name"]
        if not is_gpu(itype) or state != "running" or opted_out(inst):
            continue
        name = tags_of(inst).get("Name", "")
        up, ttl = uptime_h(inst, now), ttl_hours(inst, conf["default_ttl_h"])
        if up > ttl:
            acts.append({"do": "stop", "instance": iid, "name": name, "type": itype,
                         "why": f"up {up:.1f} h > TTL {ttl:g} h"})
            continue
        th = threshold_for(inst, conf)
        idle, why = idle_verdict(cpu.get(iid, []), started(inst), now, conf, th)
        if idle:
            acts.append({"do": "stop", "instance": iid, "name": name, "type": itype,
                         "why": f"{why} ({vcpus(inst) or '?'} vCPU box)"})
    for a in alarms:
        acts.append({"do": "delete", "instance": a["AlarmName"][len(PREFIX):],
                     "why": "an alarm of the first design (alarm stop actions misjudge restarted boxes)"})
    return acts


def apply(acts: list[dict], ec2, cw, conf: dict, log) -> list[dict]:
    done = []
    for a in acts:
        rec = dict(a, dry_run=conf["dry_run"])
        try:
            if conf["dry_run"]:
                pass
            elif a["do"] == "delete":
                cw.delete_alarms(AlarmNames=[PREFIX + a["instance"]])
            elif a["do"] == "stop":
                ec2.stop_instances(InstanceIds=[a["instance"]])  # never terminate_instances
            rec["ok"] = True
        except Exception as e:  # noqa: BLE001  one box failing (a one-time spot cannot stop) must not stop the rest
            rec["ok"], rec["error"] = False, f"{type(e).__name__}: {e}"[:500]
        log(rec)
        done.append(rec)
    return done


def watched(instances: list[dict], conf: dict, now: float) -> list[dict]:
    """The boxes whose CPU is worth reading: running GPU, not opted out, up for at least the window."""
    return [i for i in instances if is_gpu(i.get("InstanceType", "")) and i["State"]["Name"] == "running"
            and not opted_out(i) and (now - started(i)) >= conf["periods"] * conf["period_s"]]


def run(ec2, cw, conf: dict, now: float | None = None, log=None) -> dict:
    log = log or (lambda rec: print(json.dumps(rec, default=str)))
    now = time.time() if now is None else now
    instances, alarms = all_instances(ec2), killswitch_alarms(cw)
    cpu, notes = {}, []
    for inst in watched(instances, conf, now):
        try:
            cpu[inst["InstanceId"]] = cpu_since_start(cw, inst, conf, now)
        except Exception as e:  # noqa: BLE001  no reading means not idle; the next run tries again
            notes.append({"note": "cpu read failed", "instance": inst["InstanceId"], "error": str(e)[:300]})
    for n in notes:
        log(n)
    done = apply(plan(instances, alarms, cpu, conf, now), ec2, cw, conf, log)
    gpus = [i for i in instances if is_gpu(i.get("InstanceType", ""))]
    summary = {"summary": True, "gpu_instances": len(gpus),
               "gpu_running": sum(i["State"]["Name"] == "running" for i in gpus), "watched": len(cpu),
               "actions": len(done), "failed": sum(not d["ok"] for d in done) + len(notes),
               "dry_run": conf["dry_run"]}
    log(summary)
    return summary


def handler(event, context):
    import boto3
    conf = settings()
    return run(boto3.client("ec2", region_name=conf["region"]), boto3.client("cloudwatch", region_name=conf["region"]),
               conf)
