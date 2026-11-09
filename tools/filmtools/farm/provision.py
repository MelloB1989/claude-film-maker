"""Farm boxes on EC2: plan within the G-instance vCPU quotas, launch spot first with an instance type / zone
fallback, tag every box with its farm, stop or terminate only boxes the farm launched, and price what they cost.

Runs where the AWS CLI has the account (kali, profile nani). Every call goes through one function (`aws`), which the
tests replace: nothing here touches AWS unless someone runs it on purpose.

Spot workers are *persistent* requests with interruption behaviour STOP: a reclaim stops the box, EC2 starts it
again when capacity returns, and the worker service picks its chunk back up (or a newer one, if another box took
it over meanwhile). An on-demand worker is launched with shutdown behaviour terminate, so an idle or TTL power-off
ends it for good; a spot one is only stopped by that, and `down` terminates it and cancels its request.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import time
from pathlib import Path

from . import model

FARM_TAG = "FarmJob"
MANAGED_TAG = "film-farm:managed"
PROJECT = "ue-linux-poc"
# spot first, in this order; each in 1a/1b/1c (the brief's list; g6e = L40S 48 GB, g6/gr6 = L4 24 GB, g5 = A10G)
TYPES = ("g6e.4xlarge", "g6e.2xlarge", "g6.4xlarge", "gr6.4xlarge", "g5.4xlarge")
VCPU = {"g6e.xlarge": 4, "g6e.2xlarge": 8, "g6e.4xlarge": 16, "g6e.8xlarge": 32, "g6.xlarge": 4, "g6.2xlarge": 8,
        "g6.4xlarge": 16, "g6.8xlarge": 32, "gr6.4xlarge": 16, "gr6.8xlarge": 32, "g5.xlarge": 4, "g5.2xlarge": 8,
        "g5.4xlarge": 16, "g5.8xlarge": 32}
ZONES = ("a", "b", "c")
# Service Quotas: "All G and VT Spot Instance Requests", "Running On-Demand G and VT instances" (vCPUs)
QUOTA_SPOT, QUOTA_OD = "L-3819A6DF", "L-DB2E81BA"
# never touched, whatever their tags say (other people's boxes in the same account)
PROTECTED_NAMES = (re.compile(r"^kedits-"), re.compile(r"^gfx-explainers-cpu$"), re.compile(r"^ue-box-b"),
                   re.compile(r"^ue-workstation$"))
CAPACITY_ERRORS = ("InsufficientInstanceCapacity", "InsufficientCapacity", "SpotMaxPriceTooLow",
                   "MaxSpotInstanceCountExceeded", "Unsupported", "VcpuLimitExceeded", "InstanceLimitExceeded",
                   "capacity-not-available", "InsufficientFreeAddressesInSubnet")
ROOT = Path(__file__).resolve().parents[2]  # tools/


class AwsError(RuntimeError):
    def __init__(self, msg: str, code: str = ""):
        super().__init__(msg)
        self.code = code


def aws_cli(region: str, profile: str):
    """The AWS CLI as a function: aws("ec2", "describe-instances", ...) -> parsed JSON. With a profile, ambient key
    variables are dropped (on kali they belong to another identity)."""
    env = dict(os.environ)
    if profile:
        for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            env.pop(k, None)
        env["AWS_PROFILE"] = profile

    def aws(*args: str, region_override: str = ""):
        r = subprocess.run(["aws", *args, "--region", region_override or region, "--output", "json"],
                           capture_output=True, text=True, env=env)
        if r.returncode:
            err = r.stderr.strip()
            m = re.search(r"\(([A-Za-z.]+)\)", err)
            raise AwsError(f"aws {' '.join(args[:2])}: {err[-600:]}", m.group(1) if m else "")
        return json.loads(r.stdout) if r.stdout.strip() else {}
    return aws


# --- what is there --------------------------------------------------------------------------------------------------
def tags_of(inst: dict) -> dict:
    return {t["Key"]: t["Value"] for t in inst.get("Tags") or []}


def instances(aws, *filters: str) -> list[dict]:
    args = ["ec2", "describe-instances"]
    if filters:
        args += ["--filters", *filters]
    doc = aws(*args)
    return [i for r in doc.get("Reservations") or [] for i in r.get("Instances") or []]


def farm_instances(aws, farm: str, live_only: bool = True) -> list[dict]:
    flt = [f"Name=tag:{FARM_TAG},Values={farm}", f"Name=tag:{MANAGED_TAG},Values=1"]
    if live_only:
        flt.append("Name=instance-state-name,Values=pending,running,stopping,stopped")
    return [i for i in instances(aws, *flt) if owned(i, farm)]


def owned(inst: dict, farm: str) -> bool:
    """A box this farm launched: both farm tags, and not one of the protected boxes by name."""
    t = tags_of(inst)
    name = t.get("Name", "")
    if any(p.match(name) for p in PROTECTED_NAMES):
        return False
    return t.get(FARM_TAG) == farm and t.get(MANAGED_TAG) == "1"


def guard(aws, farm: str, ids: list[str], protect_ids: tuple = ()) -> list[str]:
    """The ids, re-read from EC2, that this farm may stop or terminate; refuses (raises) on any other."""
    if not ids:
        return []
    got = {i["InstanceId"]: i for i in instances(aws, f"Name=instance-id,Values={','.join(ids)}")}
    bad = [x for x in ids if x in protect_ids or x not in got or not owned(got[x], farm)]
    if bad:
        raise SystemExit(f"refused: {bad} not launched by farm {farm} (FarmJob + {MANAGED_TAG} tags), or protected")
    return list(ids)


def vcpus_of(itype: str) -> int:
    if itype in VCPU:
        return VCPU[itype]
    raise SystemExit(f"unknown vCPU count for {itype}: add it to provision.VCPU")


def quotas(aws) -> dict:
    out = {}
    for name, code in (("spot", QUOTA_SPOT), ("ondemand", QUOTA_OD)):
        out[name] = int(aws("service-quotas", "get-service-quota", "--service-code", "ec2", "--quota-code",
                            code)["Quota"]["Value"])
    return out


def g_usage(aws) -> dict:
    """vCPUs of G/VT instances counting against each quota now: running or pending on-demand ones, and spot ones
    (a persistent spot request's stopped box keeps its request open; counted to be safe)."""
    use = {"spot": 0, "ondemand": 0, "boxes": []}
    for i in instances(aws, "Name=instance-state-name,Values=pending,running,stopping,stopped"):
        it = i["InstanceType"]
        if not re.match(r"^(g|gr|vt)\d", it):
            continue
        spot = i.get("InstanceLifecycle") == "spot"
        st = i["State"]["Name"]
        if not spot and st not in ("pending", "running"):
            continue
        n = VCPU.get(it) or (i.get("CpuOptions", {}).get("CoreCount", 0) * i.get("CpuOptions", {}).get("ThreadsPerCore", 1))
        use["spot" if spot else "ondemand"] += n
        use["boxes"].append({"id": i["InstanceId"], "type": it, "spot": spot, "state": st,
                             "name": tags_of(i).get("Name", ""), "vcpu": n})
    return use


def plan(n: int, *, quota: dict, usage: dict, types: tuple = TYPES, market: str = "auto") -> list[dict]:
    """Which (type, market) to try for each of `n` workers, within the quotas: [{"worker", "options": [(type,
    market), ...]}]. Spot options come first (market auto|spot), then on-demand (auto|ondemand). Raises if even the
    smallest option does not fit for some worker."""
    free = {"spot": quota["spot"] - usage["spot"], "ondemand": quota["ondemand"] - usage["ondemand"]}
    markets = {"auto": ("spot", "ondemand"), "spot": ("spot",), "ondemand": ("ondemand",)}[market]
    out = []
    for w in range(n):
        opts = [(t, m) for m in markets for t in types if vcpus_of(t) <= free[m]]
        if not opts:
            raise SystemExit(f"worker {w + 1} of {n} does not fit the quotas: free vCPU spot {free['spot']}, "
                             f"on-demand {free['ondemand']} (quotas {quota}); smaller types (--types) or fewer workers")
        # reserve the first option's vCPUs; launch() re-plans with what really launched
        t, m = opts[0]
        free[m] -= vcpus_of(t)
        out.append({"worker": w, "options": opts})
    return out


def subnets(aws) -> dict:
    """{zone letter: subnet id} of the default VPC."""
    doc = aws("ec2", "describe-subnets", "--filters", "Name=default-for-az,Values=true")
    return {s["AvailabilityZone"][-1]: s["SubnetId"] for s in doc.get("Subnets") or []}


# --- the worker's code and first boot ------------------------------------------------------------------------------
def code_tarball() -> bytes:
    """filmtools/__init__.py + filmtools/farm/ (no caches), deterministic, for s3://<bucket>/farm/code/<sha>.tgz."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        base = ROOT / "filmtools"
        files = [base / "__init__.py"] + sorted(p for p in (base / "farm").rglob("*.py"))
        for p in files:
            info = tar.gettarinfo(str(p), arcname=str(p.relative_to(ROOT)))
            info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
            with open(p, "rb") as f:
                tar.addfile(info, f)
    return gzip.compress(buf.getvalue(), mtime=0)


UNIT = """[Unit]
Description=film-farm worker
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
Environment=PYTHONPATH=/opt/film-farm PYTHONUNBUFFERED=1
TimeoutStartSec=infinity
ExecStartPre=/usr/local/bin/film-farm-setup
ExecStartPre=/usr/local/bin/film-farm-fetch
ExecStart=/usr/bin/python3 -m filmtools.farm.worker --conf /etc/film-farm/worker.json
Restart=on-failure
RestartSec=20
[Install]
WantedBy=multi-user.target
"""


def user_data(conf: dict, code_s3: str) -> str:
    """The first-boot script: settings, the code fetcher, the worker unit, and a TTL backstop. It runs again on no
    later boot (cloud-init), so a spot box started again after a reclaim keeps its settings and starts the unit
    (enabled), which fetches the code and checks the TTL itself."""
    left = max(60, int(conf["ttl_until"] - time.time()))
    fetch = ("#!/bin/bash\nset -eu\nmkdir -p /opt/film-farm\n"
             # the leases need put-object --if-match / --if-none-match (AWS CLI v2, late 2024 on)
             "if ! aws s3api put-object help 2>/dev/null | grep -q -- '--if-match'; then\n"
             "  cd /tmp && curl -sSfL -o awscliv2.zip https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip\n"
             "  (command -v unzip >/dev/null || apt-get install -y -qq unzip >/dev/null) && rm -rf aws && "
             "unzip -q -o awscliv2.zip && ./aws/install --update >/dev/null && hash -r\nfi\n"
             f"aws s3 cp --only-show-errors --region {conf['region']} {code_s3} /tmp/film-farm.tgz\n"
             "rm -rf /opt/film-farm/filmtools && tar xzf /tmp/film-farm.tgz -C /opt/film-farm\n")
    # `up --setup`: a box made from a plain image (no UE inside) is set up once, before its first claim: the script
    # restores the engine and the project from S3 (films/host-studio/farm/setup_tokyo.sh). A marker makes it once
    # per box, so a spot box started again after a reclaim goes straight to its worker.
    setup = "#!/bin/bash\nset -eu\n"
    if conf.get("setup"):
        setup += ("[ -f /var/lib/film-farm/setup.done ] && exit 0\nmkdir -p /var/lib/film-farm\n"
                  f"aws s3 cp --only-show-errors --region {conf['region']} {conf['setup']} /var/lib/film-farm/setup.sh\n"
                  "bash /var/lib/film-farm/setup.sh > /var/log/film-farm-setup.log 2>&1\n"
                  "touch /var/lib/film-farm/setup.done\n")
    lines = ["#!/bin/bash", "# film-farm worker: settings, code fetcher, worker unit, TTL backstop", "set -eu",
             "install -d /etc/film-farm /opt/film-farm /srv/farm",
             f"cat > /etc/film-farm/worker.json <<'FMEOF'\n{json.dumps(conf, indent=1)}\nFMEOF",
             f"cat > /usr/local/bin/film-farm-fetch <<'FMEOF'\n{fetch}FMEOF",
             f"cat > /usr/local/bin/film-farm-setup <<'FMEOF'\n{setup}FMEOF",
             "chmod 755 /usr/local/bin/film-farm-fetch /usr/local/bin/film-farm-setup",
             f"cat > /etc/systemd/system/film-farm-worker.service <<'FMEOF'\n{UNIT}FMEOF",
             # the editor's idle watchdog from the UE image must not power a busy worker off between chunks
             "systemctl disable --now ue-watchdog.timer 2>/dev/null || true",
             "systemctl daemon-reload", "systemctl enable --now film-farm-worker.service",
             f"systemd-run --unit=film-farm-ttl --on-active={left}s /bin/systemctl poweroff",
             "echo film-farm worker ready"]
    text = "\n".join(lines) + "\n"
    if len(text.encode()) > 16000:
        raise SystemExit(f"user-data is {len(text)} bytes; EC2 takes 16 KB")
    return text


def run_args(*, farm: str, index: int, itype: str, market: str, zone_subnet: str, ami: str, ttl_h: float,
             user_data_text: str, iam_profile: str, volume_gb: int, security_group: str = "",
             root_device: str = "/dev/sda1") -> list[str]:
    tags = [{"Key": "Name", "Value": f"farm-{farm}-w{index}"}, {"Key": "Project", "Value": PROJECT},
            {"Key": FARM_TAG, "Value": farm}, {"Key": "TTLHours", "Value": f"{ttl_h:g}"},
            {"Key": MANAGED_TAG, "Value": "1"}, {"Key": "film-farm:worker", "Value": str(index)}]
    spec = [{"ResourceType": "instance", "Tags": tags}, {"ResourceType": "volume", "Tags": tags}]
    a = ["ec2", "run-instances", "--image-id", ami, "--instance-type", itype, "--count", "1",
         "--subnet-id", zone_subnet, "--iam-instance-profile", f"Name={iam_profile}",
         "--metadata-options", "HttpTokens=required,HttpEndpoint=enabled",
         "--block-device-mappings", json.dumps([{"DeviceName": root_device, "Ebs": {
             "VolumeSize": int(volume_gb), "VolumeType": "gp3", "DeleteOnTermination": True}}]),
         "--user-data", user_data_text]
    if market == "spot":
        spec.append({"ResourceType": "spot-instances-request", "Tags": tags})
        a += ["--instance-market-options", json.dumps({"MarketType": "spot", "SpotOptions": {
            "SpotInstanceType": "persistent", "InstanceInterruptionBehavior": "stop"}}),
              "--instance-initiated-shutdown-behavior", "stop"]
    else:
        a += ["--instance-initiated-shutdown-behavior", "terminate"]
    if security_group:
        a += ["--security-group-ids", security_group]
    return a + ["--tag-specifications", json.dumps(spec)]


def launch(aws, *, farm: str, n: int, ami: str, bucket: str, region: str, ttl_h: float, idle_min: float,
           types: tuple = TYPES, market: str = "auto", iam_profile: str = "ue-workstation", volume_gb: int = 0,
           security_group: str = "", first_index: int = 0, prices=None, put_code=None, log=print,
           extra_conf: dict | None = None) -> list[dict]:
    """Launch `n` workers, each trying its plan's options in order across the zones until one launches. Returns
    [{"id", "type", "market", "zone"}]. Capacity and quota errors move on to the next option; anything else stops."""
    q, use = quotas(aws), g_usage(aws)
    p = plan(n, quota=q, usage=use, types=types, market=market)
    log(f"quotas {q}; in use spot {use['spot']}, on-demand {use['ondemand']} vCPU")
    nets = subnets(aws)
    img = aws("ec2", "describe-images", "--image-ids", ami)["Images"][0]
    root_dev = img.get("RootDeviceName") or "/dev/sda1"
    if volume_gb <= 0:  # the image's own size (a farm box keeps nothing but scratch frames)
        volume_gb = max(b["Ebs"]["VolumeSize"] for b in img["BlockDeviceMappings"] if "Ebs" in b)
    code = code_tarball()
    code_s3 = f"s3://{bucket}/farm/code/{hashlib.sha256(code).hexdigest()[:16]}.tgz"
    if put_code:
        put_code(code_s3, code)
    free = {"spot": q["spot"] - use["spot"], "ondemand": q["ondemand"] - use["ondemand"]}
    ttl_until = int(time.time() + ttl_h * 3600)
    out = []
    for w in p:
        idx = first_index + w["worker"]
        last = ""
        for itype, m in w["options"]:
            if vcpus_of(itype) > free[m]:
                continue
            price = (prices or (lambda t, mk, z: None))(itype, m, None)
            conf = {"farm": farm, "bucket": bucket, "region": region, "ttl_until": ttl_until,
                    "idle_s": int(idle_min * 60), "private_root": "ue-linux/private/", "scratch": "/srv/farm",
                    "poweroff": True, "type": itype, "market": m, "price_h": price, **(extra_conf or {})}
            ud = user_data(conf, code_s3)
            for z in [z for z in ZONES if z in nets] + sorted(set(nets) - set(ZONES)):  # Tokyo: a, c, d
                try:
                    inst = aws(*run_args(farm=farm, index=idx, itype=itype, market=m, zone_subnet=nets[z], ami=ami,
                                         ttl_h=ttl_h, user_data_text=ud, iam_profile=iam_profile, volume_gb=volume_gb,
                                         security_group=security_group, root_device=root_dev))["Instances"][0]
                except AwsError as e:
                    if e.code in CAPACITY_ERRORS or any(c in str(e) for c in CAPACITY_ERRORS):
                        last = f"{itype} {m} {region}{z}: {e.code or str(e)[-120:]}"
                        log(f"  w{idx}: {last}; next")
                        continue
                    raise
                free[m] -= vcpus_of(itype)
                row = {"id": inst["InstanceId"], "type": itype, "market": m, "zone": region + z, "worker": idx,
                       "price_h": price}
                log(f"  w{idx}: launched {row['id']} {itype} {m} in {row['zone']}")
                out.append(row)
                break
            else:
                continue
            break
        else:
            log(f"  w{idx}: nothing launched ({last})")
    return out


def stop(aws, farm: str, ids: list[str]) -> list[str]:
    ids = guard(aws, farm, ids)
    if ids:
        aws("ec2", "stop-instances", "--instance-ids", *ids)
    return ids


def down(aws, farm: str, *, stop_only: bool = False, log=print) -> dict:
    """Every box of the farm: cancel the spot requests (so nothing starts them again) and terminate (or stop)."""
    rows = farm_instances(aws, farm)
    ids = guard(aws, farm, [i["InstanceId"] for i in rows])
    reqs = [i["SpotInstanceRequestId"] for i in rows if i.get("SpotInstanceRequestId")]
    if reqs and not stop_only:
        aws("ec2", "cancel-spot-instance-requests", "--spot-instance-request-ids", *reqs)
        log(f"cancelled spot requests {reqs}")
    if ids:
        aws("ec2", "stop-instances" if stop_only else "terminate-instances", "--instance-ids", *ids)
        log(f"{'stopping' if stop_only else 'terminating'} {ids}")
    return {"instances": ids, "spot_requests": [] if stop_only else reqs}


# --- money ----------------------------------------------------------------------------------------------------------
LOCATION = {"ap-south-1": "Asia Pacific (Mumbai)", "ap-northeast-1": "Asia Pacific (Tokyo)"}


def ondemand_price(aws, itype: str, region: str) -> float | None:
    """USD/h, Linux, shared tenancy, from the Pricing API (us-east-1)."""
    try:
        doc = aws("pricing", "get-products", "--service-code", "AmazonEC2", "--filters",
                  f"Type=TERM_MATCH,Field=instanceType,Value={itype}",
                  f"Type=TERM_MATCH,Field=location,Value={LOCATION.get(region, region)}",
                  "Type=TERM_MATCH,Field=operatingSystem,Value=Linux", "Type=TERM_MATCH,Field=tenancy,Value=Shared",
                  "Type=TERM_MATCH,Field=preInstalledSw,Value=NA", "Type=TERM_MATCH,Field=capacitystatus,Value=Used",
                  "--max-items", "5", region_override="us-east-1")
    except AwsError:
        return None
    for s in doc.get("PriceList") or []:
        p = json.loads(s) if isinstance(s, str) else s
        for term in (p.get("terms", {}).get("OnDemand") or {}).values():
            for d in term["priceDimensions"].values():
                v = float(d["pricePerUnit"].get("USD", 0))
                if v > 0:
                    return v
    return None


def spot_price(aws, itype: str, zone: str = "") -> float | None:
    a = ["ec2", "describe-spot-price-history", "--instance-types", itype, "--product-descriptions", "Linux/UNIX",
         "--max-items", "10"]
    if zone:
        a += ["--availability-zone", zone]
    try:
        h = aws(*a).get("SpotPriceHistory") or []
    except AwsError:
        return None
    return min((float(x["SpotPrice"]) for x in h), default=None)


def pricer(aws, region: str):
    cache: dict = {}

    def price(itype: str, market: str, zone):
        k = (itype, market, zone)
        if k not in cache:
            cache[k] = spot_price(aws, itype, zone or "") if market == "spot" else ondemand_price(aws, itype, region)
        return cache[k]
    return price


EBS_GB_MONTH = 0.0912  # gp3, ap-south-1


def cost(workers: list[dict], now: float, volume_gb: int = 0) -> dict:
    """Dollars so far from the workers' own sessions (workers/<id>.json: [[boot, last seen], ...] while running) at
    each worker's hourly price, plus its disk while it existed. Per-second billing, so this is close (it misses the
    minute or two between power-on and the worker's first word, and the stop)."""
    rows, total = [], 0.0
    for w in workers:
        secs = sum(max(0, b - a) for a, b in w.get("sessions") or [])
        ph = w.get("price_h") or 0.0
        first = min((a for a, _ in w.get("sessions") or []), default=now)
        disk = volume_gb * EBS_GB_MONTH * max(0.0, now - first) / (30 * 86400) if volume_gb else 0.0
        usd = secs / 3600 * ph + disk
        total += usd
        rows.append({"worker": w.get("worker"), "type": w.get("type"), "market": w.get("market"),
                     "hours": round(secs / 3600, 3), "price_h": ph, "usd": round(usd, 3)})
    return {"usd": round(total, 2), "workers": rows}
