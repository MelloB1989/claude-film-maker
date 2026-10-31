"""The Unreal workstation on EC2: settings, start/stop/state, its Windows password, and SSM commands on it.

Settings live in ~/.config/film-ue.json: {"region", "instance", "project_dir", "port", "key"} (key: the RSA key pair
that decrypts the Administrator password). Nothing secret is stored there; the bridge token is cached beside it.
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
from pathlib import Path

CONF = Path.home() / ".config" / "film-ue.json"
DEFAULTS = {"region": "ap-south-1", "instance": "", "project_dir": r"C:\UEProjects\HostStudio", "port": 18765,
            "key": str(Path.home() / ".ssh" / "ue-workstation.pem")}


def conf() -> dict:
    c = dict(DEFAULTS)
    if CONF.exists():
        c.update(json.loads(CONF.read_text()))
    return c


def save(**kv) -> dict:
    c = conf()
    c.update(kv)
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text(json.dumps(c, indent=1))
    return c


def aws(*args, check: bool = True) -> dict | str:
    c = conf()
    r = subprocess.run(["aws", *args, "--region", c["region"], "--output", "json"], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"aws {' '.join(args[:2])}: {r.stderr.strip()[-500:]}")
    try:
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except ValueError:
        return r.stdout


def instance() -> dict:
    c = conf()
    if not c["instance"]:
        raise SystemExit("no workstation set: film-ue set --instance i-... (see film-ue --help)")
    return aws("ec2", "describe-instances", "--instance-ids", c["instance"])["Reservations"][0]["Instances"][0]


def state() -> dict:
    i = instance()
    return {"id": i["InstanceId"], "type": i["InstanceType"], "state": i["State"]["Name"], "ip": i.get("PublicIpAddress"),
            "launched": i["LaunchTime"]}


def start(wait: bool = True) -> dict:
    aws("ec2", "start-instances", "--instance-ids", conf()["instance"])
    if wait:
        aws("ec2", "wait", "instance-running", "--instance-ids", conf()["instance"])
        for _ in range(60):  # SSM agent online
            info = aws("ssm", "describe-instance-information", "--filters", f"Key=InstanceIds,Values={conf()['instance']}")
            if info.get("InstanceInformationList") and info["InstanceInformationList"][0]["PingStatus"] == "Online":
                break
            time.sleep(5)
    return state()


def stop(wait: bool = False) -> dict:
    aws("ec2", "stop-instances", "--instance-ids", conf()["instance"])
    if wait:
        aws("ec2", "wait", "instance-stopped", "--instance-ids", conf()["instance"])
    return state()


def password() -> str:
    c = conf()
    d = aws("ec2", "get-password-data", "--instance-id", c["instance"], "--priv-launch-key", c["key"])
    return d.get("PasswordData", "")


def ps(script: str, timeout: int = 600) -> str:
    """Run PowerShell on the workstation through SSM (as SYSTEM, no desktop) and return its output."""
    c = conf()
    params = json.dumps({"commands": [script], "executionTimeout": [str(timeout)]})
    cid = aws("ssm", "send-command", "--instance-ids", c["instance"], "--document-name", "AWS-RunPowerShellScript",
              "--parameters", params)["Command"]["CommandId"]
    end = time.time() + timeout + 30
    while time.time() < end:
        time.sleep(2)
        r = aws("ssm", "get-command-invocation", "--command-id", cid, "--instance-id", c["instance"], check=False)
        if isinstance(r, dict) and r.get("Status") in ("Success", "Failed", "TimedOut", "Cancelled"):
            if r["Status"] != "Success":
                raise SystemExit(f"workstation command {r['Status']}: {r.get('StandardErrorContent', '')[-800:]}")
            return r.get("StandardOutputContent", "")
    raise SystemExit("workstation command timed out")


def put_text(path: str, data: bytes) -> None:
    """Write a file on the workstation through SSM (small files: SSM caps a command near 100 KB)."""
    b64 = base64.b64encode(data).decode()
    ps(f"New-Item -ItemType Directory -Force -Path (Split-Path '{path}') | Out-Null; "
       f"[IO.File]::WriteAllBytes('{path}', [Convert]::FromBase64String('{b64}'))")
