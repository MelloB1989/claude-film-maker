"""RunPod GPU pods for renders: start one, reach it over SSH, keep a spend cap, take it down.

Blender finals (Cycles) and the GPU image work (optical-flow retime, mattes) need an NVIDIA GPU this machine doesn't have.
A RunPod on-demand pod gives one by the hour. This module talks to RunPod's GraphQL API with the account's API key and
nothing else: the key comes from `RUNPOD_API_KEY`, or the file named by `RUNPOD_API_KEY_FILE`; it is never printed or
written anywhere.

    python -m filmtools.runpod up --name amv-render [--gpu "NVIDIA GeForce RTX 4090"] [--disk 80] [--pubkey ~/.ssh/id.pub]
    python -m filmtools.runpod ls                  # pods, their state, $/h and SSH endpoint
    python -m filmtools.runpod ssh <pod id>        # prints the ssh command line for the pod
    python -m filmtools.runpod spend               # balance and current $/h across pods
    python -m filmtools.runpod down <pod id> [--stop]   # terminate (default) or stop

Spend guard: `up` refuses to start a pod when the account's current spend plus the new pod's price would exceed
`--max-rate` $/h (default 1.5), and prints the balance before and after.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API = "https://api.runpod.io/graphql"
DEFAULT_IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"


def api_key():
    k = os.environ.get("RUNPOD_API_KEY")
    if not k and os.environ.get("RUNPOD_API_KEY_FILE"):
        k = Path(os.environ["RUNPOD_API_KEY_FILE"]).expanduser().read_text().strip().split()[-1]
    if not k:
        raise SystemExit("set RUNPOD_API_KEY or RUNPOD_API_KEY_FILE")
    return k


def gql(query, variables=None):
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                 headers={"content-type": "application/json", "authorization": f"Bearer {api_key()}",
                                          "user-agent": "filmtools-runpod/1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    if out.get("errors"):
        raise SystemExit("runpod: " + "; ".join(e.get("message", "?") for e in out["errors"]))
    return out["data"]


POD_FIELDS = "id name desiredStatus costPerHr gpuCount machine { gpuDisplayName } vcpuCount memoryInGb " \
             "runtime { uptimeInSeconds ports { ip isIpPublic privatePort publicPort type } gpus { id gpuUtilPercent } }"


def pods():
    return gql("query { myself { pods { %s } } }" % POD_FIELDS)["myself"]["pods"]


def pod(pid):
    return gql('query { pod(input: {podId: "%s"}) { %s } }' % (pid, POD_FIELDS))["pod"]


def spend():
    me = gql("query { myself { clientBalance currentSpendPerHr } }")["myself"]
    return float(me["clientBalance"]), float(me["currentSpendPerHr"] or 0)


def ssh_endpoint(p):
    for port in ((p.get("runtime") or {}).get("ports") or []):
        if port["privatePort"] == 22 and port["isIpPublic"]:
            return port["ip"], port["publicPort"]
    return None


def up(name, gpu, disk, pubkey, image, cloud, max_rate, min_vcpu, min_mem):
    bal, rate = spend()
    price = gql('query { gpuTypes(input: {id: "%s"}) { lowestPrice(input: {gpuCount: 1}) { uninterruptablePrice } } }'
                % gpu)["gpuTypes"][0]["lowestPrice"]["uninterruptablePrice"]
    if rate + float(price or 0) > max_rate:
        raise SystemExit(f"refusing: spend would be {rate + float(price or 0):.2f} $/h > --max-rate {max_rate}")
    print(f"balance {bal:.2f} $, spend now {rate:.2f} $/h, {gpu} from {price} $/h")
    env = [{"key": "PUBLIC_KEY", "value": Path(pubkey).expanduser().read_text().strip()}]
    q = """mutation($input: PodFindAndDeployOnDemandInput!) { podFindAndDeployOnDemand(input: $input) { id machineId } }"""
    inp = {"cloudType": cloud, "gpuCount": 1, "volumeInGb": 0, "containerDiskInGb": disk, "minVcpuCount": min_vcpu,
           "minMemoryInGb": min_mem, "gpuTypeId": gpu, "name": name, "imageName": image, "ports": "22/tcp",
           "volumeMountPath": "/workspace", "env": env, "startSsh": True}
    pid = gql(q, {"input": inp})["podFindAndDeployOnDemand"]["id"]
    print(f"pod {pid} starting")
    for _ in range(120):
        p = pod(pid)
        ep = ssh_endpoint(p)
        if ep:
            print(f"pod {pid} up: {p['machine']['gpuDisplayName']}, {p['vcpuCount']} vCPU, {p['memoryInGb']} GB, "
                  f"{p['costPerHr']} $/h; ssh root@{ep[0]} -p {ep[1]}")
            return pid
        time.sleep(5)
    raise SystemExit(f"pod {pid} did not expose ssh in 10 min (still billed: run `down {pid}`)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("up")
    u.add_argument("--name", default="film-render")
    u.add_argument("--gpu", default="NVIDIA GeForce RTX 4090")
    u.add_argument("--disk", type=int, default=80)
    u.add_argument("--pubkey", required=True)
    u.add_argument("--image", default=DEFAULT_IMAGE)
    u.add_argument("--cloud", default="ALL", choices=["ALL", "SECURE", "COMMUNITY"])
    u.add_argument("--max-rate", type=float, default=1.5)
    u.add_argument("--min-vcpu", type=int, default=8)
    u.add_argument("--min-mem", type=int, default=30)
    sub.add_parser("ls")
    sub.add_parser("spend")
    s = sub.add_parser("ssh")
    s.add_argument("pid")
    d = sub.add_parser("down")
    d.add_argument("pid")
    d.add_argument("--stop", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "up":
        up(a.name, a.gpu, a.disk, a.pubkey, a.image, a.cloud, a.max_rate, a.min_vcpu, a.min_mem)
    elif a.cmd == "ls":
        for p in pods():
            ep = ssh_endpoint(p)
            up_s = (p.get("runtime") or {}).get("uptimeInSeconds")
            print(f"{p['id']}  {p['name']:<16} {p['desiredStatus']:<9} {p['costPerHr']} $/h  "
                  f"{(p.get('machine') or {}).get('gpuDisplayName')}  up {up_s}s  "
                  f"{'ssh root@%s -p %s' % ep if ep else '-'}")
    elif a.cmd == "spend":
        bal, rate = spend()
        print(f"balance {bal:.2f} $, spend {rate:.2f} $/h")
    elif a.cmd == "ssh":
        ep = ssh_endpoint(pod(a.pid))
        print(f"ssh -o StrictHostKeyChecking=accept-new root@{ep[0]} -p {ep[1]}" if ep else "no ssh endpoint yet")
    elif a.cmd == "down":
        if a.stop:
            gql('mutation { podStop(input: {podId: "%s"}) { id desiredStatus } }' % a.pid)
        else:
            gql('mutation { podTerminate(input: {podId: "%s"}) }' % a.pid)
        bal, rate = spend()
        print(f"{'stopped' if a.stop else 'terminated'} {a.pid}; balance {bal:.2f} $, spend {rate:.2f} $/h")


if __name__ == "__main__":
    main()
