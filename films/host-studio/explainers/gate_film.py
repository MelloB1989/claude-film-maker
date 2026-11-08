"""Run the explainer gate for ONE film: merges the numbers files, applies the spec's key aliases, flattens a box
driver's per-job box.json (garment.leaders_ok and shot.streaming_settled = the minimum over its jobs), drops the
spec's items scoped to another film (`films`), and judges with qa/gate.py. Prints the verdict; --out writes it.

    python3 gate_film.py --film netflix numbers/netflix/*.json [--out numbers/netflix/verdict.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOB_MIN = ("garment.leaders_ok", "shot.streaming_settled")


def merge(paths: list, aliases: dict) -> dict:
    out = {}
    for p in paths:
        d = json.loads(Path(p).read_text())
        if not isinstance(d, dict):
            continue
        g = d.get("gate", d.get("numbers", d))
        for k, v in g.items():
            if k == "jobs":
                continue
            out[aliases.get(k, k)] = v
        jobs = d.get("jobs") if isinstance(d.get("jobs"), list) else []
        for k in JOB_MIN:
            vals = [j[k] for j in jobs if isinstance(j, dict) and isinstance(j.get(k), (int, float))]
            if vals and k not in g:
                out[k] = {"value": min(vals), "where": f"min over {len(vals)} job rows ({Path(p).name})"}
    return out


def scoped(spec: dict, film: str) -> dict:
    sp = json.loads(json.dumps(spec))
    sp["items"] = {k: v for k, v in sp.get("items", {}).items() if film in v.get("films", [film])}
    for k, v in sp["items"].items():
        if film in (v.get("line_by_film") or {}):
            v["line"] = v["line_by_film"][film]
        if film in v.get("info_films", []):
            v["info"] = True
            v["r4"] = [None, v.get("info_reason", "not applicable to this film")]
    return sp


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--film", required=True, choices=["netflix", "whatsapp"])
    ap.add_argument("numbers", nargs="+")
    ap.add_argument("--spec", default=str(HERE / "gate_spec.json"))
    ap.add_argument("--out", default="")
    x = ap.parse_args(argv)
    sys.path.insert(0, str(HERE.parents[2] / "tools"))
    from filmtools.unreal import qa_local
    qa_local.qa()
    gate = sys.modules["fmqa.gate"]
    spec = scoped(json.loads(Path(x.spec).read_text()), x.film)
    nums = merge(x.numbers, spec.get("aliases", {}))
    r = gate.judge(nums, spec=spec)
    r["film"] = x.film
    out = json.dumps(r, indent=1, default=str)
    if x.out:
        Path(x.out).write_text(out + "\n")
    print(r["summary"])
    for row in r["rows"]:
        if row["state"] not in ("PASS",):
            print(f"  {row['state']:<14} {row['id']} = {row['value']}  {row.get('reason', '')[:80]}")
    return 0 if r["verdict"] == "SIGN" else 1


if __name__ == "__main__":
    sys.exit(main())
