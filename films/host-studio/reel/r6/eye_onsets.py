"""lips.eye_onsets: the orchestrator's signed by-eye strip check -> one gate number (round 6).

The render lip measure is invalid (round 5b), so the gate row is the orchestrator's eye, written down line by line:

    {"by": "cc-64d05f6e", "cut": "<the cut file judged>",
     "lines": {"L1": {"lead_f": 1, "verdict": "pass"}, "L3a": {"lead_f": null, "verdict": "occluded", "note": "hair"}}}

lead_f = frames the mouth opens BEFORE the sound (negative: after). The row is 1 only if every expected line is there
and reads pass with 0 <= lead_f <= 2, or occluded with a note naming what hides the mouth; the signer must be the
orchestrator. Anything else is 0 (or an error), never a pass.

    python3 eye_onsets.py STRIP.json [--lines L1,L2,...] [--out numbers/eye_onsets_gate.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LINES = ["L1", "L2", "L3a", "L3b", "L4a", "L4b"]  # the 65 s cut's VO lines (vo_selects.json)
SIGNER = "cc-64d05f6e"
LEAD = (0, 2)


def judge(strip: dict, lines: list | None = None, signer: str = SIGNER) -> dict:
    lines = lines or LINES
    if strip.get("by") != signer:
        return {"value": None, "error": f"strip not signed by {signer} (by={strip.get('by')!r})"}
    got, bad = strip.get("lines") or {}, []
    for ln in lines:
        r = got.get(ln)
        if r is None:
            bad.append(f"{ln}: not judged")
            continue
        v, lead = r.get("verdict"), r.get("lead_f")
        if v == "occluded":
            if not str(r.get("note") or "").strip():
                bad.append(f"{ln}: occluded without saying by what")
        elif v != "pass":
            bad.append(f"{ln}: {v} (lead {lead} f)")
        elif not isinstance(lead, (int, float)) or not LEAD[0] <= lead <= LEAD[1]:
            bad.append(f"{ln}: lead {lead} f outside {LEAD[0]}..{LEAD[1]}")
    where = "; ".join(bad) if bad else ", ".join(
        f"{ln} {got[ln].get('lead_f') if got[ln].get('verdict') == 'pass' else 'occluded'}" for ln in lines)
    return {"value": 0 if bad else 1, "where": f"{strip.get('cut', 'cut')}: {where}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("strip")
    ap.add_argument("--lines", default=",".join(LINES))
    ap.add_argument("--out", default="")
    x = ap.parse_args(argv)
    row = judge(json.loads(Path(x.strip).read_text()), [s for s in x.lines.split(",") if s])
    out = json.dumps({"gate": {"lips.eye_onsets": row}}, indent=1)
    if x.out:
        Path(x.out).write_text(out + "\n")
    print(out)
    return 0 if row.get("value") == 1 else 1


if __name__ == "__main__":
    sys.exit(main())
