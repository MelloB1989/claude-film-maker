"""On a worker: compare two jobs' frames (verify.compare) and print the numbers as JSON. `film-farm compare` runs
this over SSM for a private job, so the frames never leave AWS.

    python3 -m filmtools.farm.compare --farm F --a FARM_JOB --b ONE_BOX_JOB [--frames 0,160]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys

from . import verify
from .queue import Queue
from .store import AwsStore
from .worker import CONF


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--farm", required=True)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--frames", default="")
    ap.add_argument("--conf", default=CONF)
    ap.add_argument("--local", default="/srv/farm/_compare")
    a = ap.parse_args(argv)
    conf = json.load(open(a.conf))
    q = Queue(AwsStore(conf["bucket"], conf["region"]), a.farm)
    roots = {j["id"]: j["root"] for j in q.jobs()}
    fr = None
    if a.frames:
        s, e = (int(x) for x in a.frames.split(","))
        fr = list(range(s, e))
    try:
        rep = verify.compare(q, roots[a.a], roots[a.b], a.local, fr)
    finally:
        shutil.rmtree(a.local, ignore_errors=True)
    print("FARM-COMPARE " + json.dumps(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
