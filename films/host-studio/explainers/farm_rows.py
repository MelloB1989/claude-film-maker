"""Gate rows from a FARM finals run (round 7: the finals render on film-farm, docs/FARM.md). Numbers only.

The farm driver exports one JSON per film from film-farm's own outputs:
    {"jobs": [{"id": "<job>", "verify": <filmtools.farm.verify.verify(...)>,
               "continuity": <filmtools.farm.verify.continuity(...)>,
               "guards": [<each chunk's done.json["hook"]: the dict the explainer hook's before_chunk() returned:
                           leaders_ok, strays, face_luma, face_ok, ok, why (agent-08; absent if the job has no hook)>]}]}
verify() lists S3 keys and sizes only (no pixels), so it can run where the AWS CLI has the account. continuity() needs
frame differences of PRESENTER renders, so it runs ON A BOX or a farm worker (the face rule).
Rows: shot.farm_frames_ok (every job's frames present exactly once at the right size), shot.chunk_seams_ok (no
flagged jump at a chunk boundary inside a shot: a hair/cloth/temporal restart at a seam), garment.leaders_ok (the
minimum over every chunk's guard, the r6n0 lesson), set.strays_ok (no Test_*/FMQA_*/second presenter in any chunk).

    python3 farm_rows.py farm_<film>.json [--out numbers/<film>/farm.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def rows(d: dict) -> dict:
    jobs = d.get("jobs") or []
    if not jobs:
        return {k: {"value": None, "error": "no farm jobs"} for k in
                ("shot.farm_frames_ok", "shot.chunk_seams_ok", "garment.leaders_ok", "set.strays_ok")}
    bad_v = [j["id"] for j in jobs if not (j.get("verify") or {}).get("ok")]
    bad_c = [f"{j['id']}@{(j.get('continuity') or {}).get('flagged')}" for j in jobs
             if not (j.get("continuity") or {}).get("ok", False)]
    guards = [(j["id"], g) for j in jobs for g in (j.get("guards") or [])]
    lead = [g.get("leaders_ok") for _, g in guards if g.get("leaders_ok") is not None]
    strays = [f"{jid}: {g.get('strays')}" for jid, g in guards if g.get("strays")]
    n = f"{len(jobs)} jobs, {len(guards)} chunk guards"
    return {
        "shot.farm_frames_ok": {"value": 0 if bad_v else 1, "where": "; ".join(bad_v) or n},
        "shot.chunk_seams_ok": {"value": 0 if bad_c else 1, "where": "; ".join(bad_c) or n},
        "garment.leaders_ok": ({"value": min(lead), "where": f"min over {len(lead)} chunk guards"} if lead else
                               {"value": None, "error": "no chunk guard carries leaders_ok"}),
        "set.strays_ok": {"value": 0 if strays else 1, "where": "; ".join(strays[:4]) or n},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("farm_json")
    ap.add_argument("--out", default="")
    x = ap.parse_args(argv)
    out = json.dumps({"gate": rows(json.loads(Path(x.farm_json).read_text()))}, indent=1)
    if x.out:
        Path(x.out).write_text(out + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
