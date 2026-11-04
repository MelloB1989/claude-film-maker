"""Temporary GPU boxes: start one for a job, with a time to live it cannot outlive, and let it end itself when
nobody uses it.

    film-ue box up gpu1 --type g6.4xlarge --ttl 4h [--idle 20m] [--stall 15m] [--spot] [--like linux]
    film-ue box ls                       every film-ue box in the region: state, time left, spot or not
    film-ue box status gpu1              the instance and its watchdog's last decision (why it is or is not idle)
    film-ue box extend gpu1 --ttl 2h     more time (from now)
    film-ue box down gpu1 [--forget]     terminate it (and forget its profile)

`box up` launches an EC2 instance (Ubuntu 22.04 by default, or --ami: an image with the engine already on it) with
"shutdown behaviour: terminate", tags it (film-ue:box, film-ue:ttl-until, film-ue:owner) and gives it, through its
user-data, the watchdog (unreal/linux/ue_watchdog.py, every minute: TTL, idle, editor stall) plus a hard backstop:
a systemd timer that powers it off at the TTL even if the watchdog breaks. Powering off terminates it. It then makes
the box's profile (film-ue --box gpu1 ...), so `film-ue --box gpu1 provision ...` sets it up and every other command
drives it. --like copies another profile's settings (project dir, bucket, epic_s3, user).

Every AWS call goes through one function (`aws`), which the tests replace: nothing here is exercised against AWS
without someone running it on purpose."""
from __future__ import annotations

import base64
import contextlib
import getpass
import gzip
import json
import os
import re
import socket
import time
from pathlib import Path

from . import workstation as ws
from . import transport
from .boxpaths import BoxPaths

ROOT = Path(__file__).resolve().parents[3]
LINUX = ROOT / "unreal" / "linux"
UBUNTU_AMI_PARAM = "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
TAG = "film-ue:box"
DEFAULT_TYPE = "g6.4xlarge"
LIVE = ("pending", "running", "stopping", "stopped")


def parse_duration(s) -> int:
    """Seconds from "4h", "90m", "1h30m", "45s", "2d", or a plain number of minutes."""
    if isinstance(s, (int, float)):
        return int(s * 60)
    s = str(s).strip().lower()
    if s.isdigit():
        return int(s) * 60
    parts = re.findall(r"(\d+(?:\.\d+)?)([dhms])", s)
    if not parts or "".join(a + b for a, b in parts) != s.replace(" ", ""):
        raise SystemExit(f"duration {s!r}: like 4h, 90m, 1h30m or 2d")
    return int(sum(float(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[u] for n, u in parts))


def _aws(region: str):
    return lambda *a, **k: transport.aws_cli({"region": region}, *a, **k)


def _profile_path(name: str) -> Path:
    return ws.CONF_DIR / f"film-ue.{name}.json"


def _profile(name: str) -> dict:
    p = _profile_path(name)
    return json.loads(p.read_text()) if p.exists() else {}


def _save_profile(name: str, **kv) -> dict:
    c = _profile(name)
    c.update(kv)
    ws.CONF_DIR.mkdir(parents=True, exist_ok=True)
    _profile_path(name).write_text(json.dumps(c, indent=1))
    return c


@contextlib.contextmanager
def _on(name: str):
    """Run film-ue functions against another box's profile for a moment."""
    old = os.environ.get("FILM_UE_BOX")
    os.environ["FILM_UE_BOX"] = name
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("FILM_UE_BOX", None)
        else:
            os.environ["FILM_UE_BOX"] = old


def user_data(ttl_until: int, idle_min: int, stall_min: int, project_dir: str = "", user: str = "ubuntu",
              on_exit: list | None = None) -> str:
    """The first-boot script: the watchdog and its timer, its settings, and the TTL backstop. Under EC2's 16 KB.
    `on_exit`: shell commands the watchdog runs (as root) before an idle or TTL power-off."""
    wd = base64.b64encode(gzip.compress((LINUX / "ue_watchdog.py").read_bytes(), mtime=0)).decode()
    cfg = {"ttl_until": ttl_until, "idle_min": idle_min, "stall_min": stall_min,
<<<<<<< HEAD
           "token": f"{project_dir}/Saved/fmbridge.token" if project_dir else "", "on_exit": list(on_exit or [])}
=======
           "token": BoxPaths("linux", project_dir).token() if project_dir else ""}  # a new box is Linux
>>>>>>> origin/fleet/agent-03/ue-post
    left = max(60, ttl_until - int(time.time()))
    units = {"ue-watchdog.service": (LINUX / "ue-watchdog.service").read_text(),
             "ue-watchdog.timer": (LINUX / "ue-watchdog.timer").read_text()}
    lines = ["#!/bin/bash", "# film-ue box: the watchdog (ttl, idle, editor stall) and a hard TTL backstop", "set -eu",
             "install -d /usr/local/lib/film-ue /etc/film-ue /var/lib/film-ue /run/film-ue",
             f"echo {wd} | base64 -d | gunzip > /usr/local/lib/film-ue/ue_watchdog.py",
             "chmod 755 /usr/local/lib/film-ue/ue_watchdog.py",
             f"cat > /etc/film-ue/watchdog.json <<'FMEOF'\n{json.dumps(cfg, indent=1)}\nFMEOF"]
    for unit, text in units.items():
        lines.append(f"cat > /etc/systemd/system/{unit} <<'FMEOF'\n{text.rstrip()}\nFMEOF")
    lines += ["systemctl daemon-reload", "systemctl enable --now ue-watchdog.timer",
              f"systemd-run --unit=film-ue-ttl --on-active={left}s /bin/systemctl poweroff",
              f"echo 'film-ue box ready: ttl {left}s, idle {idle_min} min, stall {stall_min} min'"]
    text = "\n".join(lines) + "\n"
    if len(text.encode()) > 16000:
        raise SystemExit(f"user-data is {len(text)} bytes; EC2 takes 16 KB")
    return text


def _ddc_save_as_user(base: dict, region: str) -> str:
    """The DDC save (sync.ddc_script) for the box's editor user, from a profile's settings (no box needed yet)."""
    import shlex
    from . import sync
    if not base.get("project_dir") or not (base.get("bucket") or base.get("ddc_s3")):
        raise SystemExit("--save-ddc-on-exit needs --like a profile with project_dir and bucket (or ddc_s3)")
    with _temp_conf({**base, "region": region, "os": "linux"}):
        script = sync.ddc_script("save")
    user = base.get("user", "ubuntu")
    return f"runuser -u {shlex.quote(user)} -- bash -lc {shlex.quote(script)}"


@contextlib.contextmanager
def _temp_conf(conf: dict):
    """workstation.conf() answering `conf` for a moment (to build a script for a box that has no profile yet)."""
    saved = ws.conf
    ws.conf = lambda: {**ws.DEFAULTS, **ws.LINUX_DEFAULTS, **conf}
    try:
        yield
    finally:
        ws.conf = saved


def _instance_rows(desc: dict) -> list[dict]:
    rows, now = [], time.time()
    for r in desc.get("Reservations", []):
        for i in r.get("Instances", []):
            tags = {t["Key"]: t["Value"] for t in i.get("Tags", [])}
            ttl = int(tags.get("film-ue:ttl-until", "0") or 0)
            rows.append({"name": tags.get(TAG, ""), "id": i["InstanceId"], "type": i.get("InstanceType"),
                         "state": i.get("State", {}).get("Name"), "spot": i.get("InstanceLifecycle") == "spot",
                         "launched": str(i.get("LaunchTime", "")), "ip": i.get("PrivateIpAddress"),
                         "ttl_left_min": int((ttl - now) // 60) if ttl else None, "owner": tags.get("film-ue:owner", ""),
                         "profile": _profile_path(tags.get(TAG, "-")).exists()})
    return sorted(rows, key=lambda x: (x["name"], x["launched"]))


def ls(region: str | None = None, aws=None) -> list[dict]:
    """Every film-ue box in the region that is not terminated."""
    region = region or ws.conf()["region"]
    aws = aws or _aws(region)
    desc = aws("ec2", "describe-instances", "--filters", f"Name=tag-key,Values={TAG}",
               f"Name=instance-state-name,Values={','.join(LIVE)}")
    return _instance_rows(desc)


def _find(name: str, region: str, aws) -> dict | None:
    desc = aws("ec2", "describe-instances", "--filters", f"Name=tag:{TAG},Values={name}",
               f"Name=instance-state-name,Values={','.join(LIVE)}")
    rows = _instance_rows(desc)
    return rows[0] if rows else None


def up(name: str, *, instance_type: str = DEFAULT_TYPE, ttl: str = "4h", idle: str = "20m", stall: str = "15m",
       spot: bool = False, ami: str = "", subnet: str = "", security_group: str = "", iam_profile: str = "ue-workstation",
       volume_gb: int = 300, key_name: str = "", like: str = "", region: str = "", wait: bool = True, aws=None,
       save_ddc_on_exit: bool = False, sleep=time.sleep, log=print) -> dict:
    """Launch a temporary box (or return the one already running under this name) and make its profile.
    `save_ddc_on_exit`: before an idle or TTL power-off, the watchdog saves the DDC (compiled shaders) to S3 (the
    `--like` profile's bucket/ddc_s3), so the next box starts warm."""
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$", name):
        raise SystemExit(f"box name {name!r}: letters, digits, - and _")
    base = _profile(like) if like else {}
    if like and not base:
        raise SystemExit(f"no profile {like!r} to copy settings from: film-ue profile ls")
    region = region or base.get("region") or ws.conf()["region"]
    aws = aws or _aws(region)
    existing = _find(name, region, aws)
    if existing:
        log(f"box {name} is already {existing['state']}: {existing['id']} (nothing launched)")
        return existing
    ttl_s, idle_min, stall_min = parse_duration(ttl), parse_duration(idle) // 60, parse_duration(stall) // 60
    if ttl_s < 600:
        raise SystemExit("ttl under 10 minutes: a box needs that long just to start (--ttl 1h)")
    ttl_until = int(time.time()) + ttl_s
    if not ami:
        ami = aws("ssm", "get-parameter", "--name", UBUNTU_AMI_PARAM)["Parameter"]["Value"]
    project_dir = base.get("project_dir", "")
    on_exit = []
    if save_ddc_on_exit:
        on_exit.append(_ddc_save_as_user(base, region))
    tags = [{"Key": TAG, "Value": name}, {"Key": "Name", "Value": f"film-ue-{name}"},
            {"Key": "film-ue:ttl-until", "Value": str(ttl_until)},
            {"Key": "film-ue:owner", "Value": f"{getpass.getuser()}@{socket.gethostname()}"}]
    args = ["ec2", "run-instances", "--image-id", ami, "--instance-type", instance_type, "--count", "1",
            "--iam-instance-profile", f"Name={iam_profile}",
            "--instance-initiated-shutdown-behavior", "terminate",
            "--metadata-options", "HttpTokens=required,HttpEndpoint=enabled",
            "--block-device-mappings", json.dumps([{"DeviceName": "/dev/sda1", "Ebs": {
                "VolumeSize": int(volume_gb), "VolumeType": "gp3", "DeleteOnTermination": True}}]),
            "--tag-specifications", json.dumps([{"ResourceType": "instance", "Tags": tags},
                                                {"ResourceType": "volume", "Tags": tags}]),
            "--user-data", user_data(ttl_until, idle_min, stall_min, project_dir, base.get("user", "ubuntu"), on_exit)]
    if spot:  # a spot box is terminated on interruption, never stopped: its profile then simply finds nothing
        args += ["--instance-market-options", json.dumps({"MarketType": "spot", "SpotOptions": {
            "SpotInstanceType": "one-time", "InstanceInterruptionBehavior": "terminate"}})]
    if subnet:
        args += ["--subnet-id", subnet]
    if security_group:
        args += ["--security-group-ids", security_group]
    if key_name:
        args += ["--key-name", key_name]
    inst = aws(*args)["Instances"][0]
    iid = inst["InstanceId"]
    log(f"box {name}: launched {iid} ({instance_type}{', spot' if spot else ''}), ttl {ttl_s // 60} min")
    keep = {k: v for k, v in base.items() if k not in ("instance", "local_port", "ssh", "transport")}
    _save_profile(name, **{**keep, "os": "linux", "transport": "ssm", "instance": iid, "region": region,
                           "ttl_until": ttl_until, "temporary": True, "spot": spot, "type": instance_type})
    if wait:
        aws("ec2", "wait", "instance-running", "--instance-ids", iid)
        for _ in range(90):
            info = aws("ssm", "describe-instance-information", "--filters", f"Key=InstanceIds,Values={iid}")
            lst = info.get("InstanceInformationList") or []
            if lst and lst[0].get("PingStatus") == "Online":
                break
            sleep(5)
        else:
            log(f"box {name}: running but not on SSM yet (film-ue --box {name} status)")
    return {"name": name, "id": iid, "type": instance_type, "spot": spot, "ttl_until": ttl_until, "region": region,
            "next": f"film-ue --box {name} provision ... (or film-ue --box {name} health once it is set up)"}


def down(name: str, *, forget: bool = False, aws=None, log=print) -> dict:
    """Terminate the box (it is temporary: nothing on it is kept; push what matters to S3 first) and clear its
    profile's instance (or forget the profile)."""
    prof = _profile(name)
    region = prof.get("region") or ws.conf()["region"]
    aws = aws or _aws(region)
    row = _find(name, region, aws)
    iid = row["id"] if row else prof.get("instance")
    if not iid:
        raise SystemExit(f"no box {name!r} running (film-ue box ls)")
    if prof.get("instance") == iid and not prof.get("temporary"):
        raise SystemExit(f"{name} is a permanent workstation (not made by box up): film-ue --box {name} down stops it")
    aws("ec2", "terminate-instances", "--instance-ids", iid)
    log(f"box {name}: terminating {iid}")
    if forget:
        from . import profiles
        with contextlib.suppress(SystemExit):
            profiles.remove(name)
    elif prof:
        _save_profile(name, instance="", terminated=iid)
    return {"name": name, "id": iid, "state": "shutting-down"}


def extend(name: str, ttl: str, *, aws=None, run=None) -> dict:
    """More time for a running box: `ttl` from now. Updates its tag, its watchdog and its backstop timer."""
    prof = _profile(name)
    region = prof.get("region") or ws.conf()["region"]
    aws = aws or _aws(region)
    row = _find(name, region, aws)
    if not row or row["state"] != "running":
        raise SystemExit(f"box {name!r} is not running (film-ue box ls)")
    secs = parse_duration(ttl)
    until = int(time.time()) + secs
    aws("ec2", "create-tags", "--resources", row["id"], "--tags", f"Key=film-ue:ttl-until,Value={until}")
    script = ("python3 -c \"import json; p='/etc/film-ue/watchdog.json'; c=json.load(open(p)); "
              f"c['ttl_until']={until}; json.dump(c, open(p, 'w'), indent=1)\"\n"
              "systemctl stop film-ue-ttl.timer 2>/dev/null || true\n"
              f"systemd-run --unit=film-ue-ttl --on-active={secs}s /bin/systemctl poweroff\n")
    with _on(name):
        (run or (lambda s: ws.sh(s, 120, root=True)))(script)
    _save_profile(name, ttl_until=until)
    return {"name": name, "id": row["id"], "ttl_until": until, "ttl_left_min": secs // 60}


def status(name: str, *, aws=None, read=None) -> dict:
    """The instance (state, time left) and its watchdog's last decision: what kept it busy, or why it would stop."""
    prof = _profile(name)
    region = prof.get("region") or ws.conf()["region"]
    aws = aws or _aws(region)
    row = _find(name, region, aws)
    out = {"name": name, "instance": row, "watchdog": None}
    if row and row["state"] == "running":
        with _on(name):
            data = (read or (lambda p: ws.transport().get(p)))("/var/lib/film-ue/watchdog.json")
        if data:
            try:
                out["watchdog"] = json.loads(data)
            except ValueError:
                out["watchdog"] = {"unreadable": True}
    return out


def keepalive(name: str, *, run=None) -> str:
    """Tell the box's watchdog someone is working on it (resets the idle clock; an editor job or a login does too)."""
    with _on(name):
        (run or (lambda s: ws.sh(s, 60, root=True)))("mkdir -p /run/film-ue && touch /run/film-ue/keepalive")
    return f"box {name}: idle clock reset"
