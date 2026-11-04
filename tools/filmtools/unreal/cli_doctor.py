"""film-ue doctor: is the box ready to be driven? The client's side (settings, the bridge answering) around the
editor's own check (the op editor.doctor), with one fix per problem. Exit 0 when nothing fails, 1 otherwise.

    film-ue [--box NAME] doctor [--json]
"""
from __future__ import annotations

import json
import sys

NAMES = ("doctor",)


def register(sub) -> None:
    d = sub.add_parser("doctor", help="check the box end to end (bridge, engine, GPU, plugins, ops, disk, Epic "
                                      "sign-in) and print a fix for each problem")
    d.add_argument("--json", action="store_true")


def run() -> dict:
    """The whole check as one result: {"pass", "issues", "metrics"} (the editor's, plus the client's own issues)."""
    from . import client, workstation as ws
    issues, metrics = [], {}
    try:
        conf = ws.conf()
        metrics["box"] = {k: conf.get(k) for k in ("os", "instance", "project_dir", "transport", "bridge") if k in conf}
    except Exception as e:  # no settings yet
        issues.append({"code": "doctor.settings", "severity": "fail", "message": f"no box settings: {e}",
                       "fix": "film-ue set --instance ... (or --transport ssh --ssh user@host) first"})
        return {"pass": False, "issues": issues, "metrics": metrics}
    try:
        h = client.health(retry_s=5)
        metrics["bridge"] = {k: h.get(k) for k in ("engine", "platform", "bridge", "uptime", "queued") if k in h}
    except (SystemExit, OSError) as e:
        fix = ("film-ue editor status / film-ue editor log 80 (Linux); film-ue install if the bridge was never "
               "installed" if conf.get("os") == "linux" else "film-ue up; film-ue install; film-ue screen to look")
        issues.append({"code": "doctor.bridge_down", "severity": "fail", "message": f"the bridge does not answer: {e}",
                       "fix": fix})
        return {"pass": False, "issues": issues, "metrics": metrics}
    r = client.op("editor.doctor", timeout=120)
    if not r.get("ok"):
        issues.append({"code": "doctor.op_failed", "severity": "fail",
                       "message": r.get("message") or (r.get("error") or "").strip().splitlines()[-1:],
                       "fix": "film-ue install (an older bridge has no editor.doctor)"})
        return {"pass": False, "issues": issues, "metrics": metrics}
    res = r["result"]
    metrics.update(res.get("metrics", {}))
    issues += res.get("issues", [])
    return {"pass": not any(i.get("severity") == "fail" for i in issues), "issues": issues, "metrics": metrics}


def format_text(r: dict) -> str:
    m = r["metrics"]
    head = [f"{'OK' if r['pass'] else 'NOT READY'}: engine {m.get('engine', '?')}, python {m.get('python', '?')}, "
            f"{m.get('platform', '?')}, rhi {m.get('rhi') or '?'}, {m.get('ops', '?')} ops, "
            f"{m.get('free_gb', '?')} GB free"]
    order = {"fail": 0, "warn": 1, "info": 2}
    for i in sorted(r["issues"], key=lambda i: order.get(i.get("severity"), 3)):
        head.append(f"  [{i.get('severity', '?')}] {i.get('message')}")
        if i.get("fix"):
            head.append(f"         fix: {i['fix']}")
    return "\n".join(head)


def dispatch(a) -> bool:
    if a.cmd not in NAMES:
        return False
    r = run()
    print(json.dumps(r, indent=1) if a.json else format_text(r))
    sys.stdout.flush()
    raise SystemExit(0 if r["pass"] else 1)
