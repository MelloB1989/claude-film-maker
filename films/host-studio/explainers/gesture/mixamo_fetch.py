"""Export the catalogue's Mixamo motions as FBX (agent-08, R7 gesture library).

Mixamo builds each FBX on request for a logged-in Adobe ID. The bearer token comes only from the fleet secret, in the
environment (never printed, never on a command line):

    fleetctl secret exec MIXAMO_TOKEN=mixamo-token -- python3 mixamo_fetch.py catalog.json OUT_DIR [--only id,id] [--dry-run]

Per clip: the motion's gms_hash from the catalogue's Mixamo id, an export request (FBX binary, without skin, 30 fps,
no keyframe reduction) on the account's current character, a poll until the job is done, and the download to
OUT_DIR/<file>. Sizes and sha256 are listed in OUT_DIR/fetched.json. `--dry-run` asks nothing of the account and
prints what it would fetch.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

API = "https://www.mixamo.com/api/v1"
PREFS = {"format": "fbx7_2019", "skin": "false", "fps": "30", "reducekf": "0"}


def call(method, path, token=None, body=None, timeout=60):
    req = urllib.request.Request(path if path.startswith("http") else API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("X-Api-Key", "mixamo2")
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def gms_hash(motion_id):
    """The export's gms_hash: the motion's defaults, its params as the comma list the exporter takes."""
    d = call("GET", f"/products/{motion_id}?similar=0&character_id=")["details"]["gms_hash"]
    d = dict(d)
    d["params"] = ",".join(str(p[1]) for p in d.get("params", []))
    d["overdrive"] = 0
    return d


def export(token, character_id, clip):
    body = {"character_id": character_id, "gms_hash": [gms_hash(clip["source_id"])], "preferences": PREFS,
            "product_name": clip["source_name"].split(":")[0], "type": "Motion"}
    call("POST", "/animations/export", token, body)
    for _ in range(120):
        time.sleep(2)
        m = call("GET", f"/characters/{character_id}/monitor", token)
        if m.get("status") == "completed":
            return m["job_result"]
        if m.get("status") == "failed":
            raise RuntimeError(f"{clip['id']}: export failed: {m.get('message')}")
    raise RuntimeError(f"{clip['id']}: export not done in 4 min")


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("catalog")
    ap.add_argument("out_dir")
    ap.add_argument("--only", default="")
    ap.add_argument("--character", default="", help="Mixamo character id; default the account's primary")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    clips = json.load(open(a.catalog))["clips"]
    if a.only:
        want = set(a.only.split(","))
        clips = [c for c in clips if c["id"] in want]
    if a.dry_run:
        for c in clips:
            print(c["id"], c["source_id"], c["frames_src"], "f", c["length_s"], "s")
        return
    token = os.environ.get("MIXAMO_TOKEN")
    if not token:
        raise SystemExit("MIXAMO_TOKEN is not set (run under fleetctl secret exec)")
    os.makedirs(a.out_dir, exist_ok=True)
    character = a.character or call("GET", "/characters/primary", token)["primary_character_id"]
    log_path = os.path.join(a.out_dir, "fetched.json")
    log = json.load(open(log_path)) if os.path.exists(log_path) else {}
    for c in clips:
        dest = os.path.join(a.out_dir, c["file"])
        if c["id"] in log and os.path.exists(dest):
            continue
        url = export(token, character, c)
        with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as f:
            f.write(r.read())  # a signed storage URL: no token on it
        data = open(dest, "rb").read()
        log[c["id"]] = {"file": c["file"], "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                        "source_id": c["source_id"], "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        json.dump(log, open(log_path, "w"), indent=1)
        print(c["id"], len(data), "bytes")


if __name__ == "__main__":
    main(sys.argv[1:])
