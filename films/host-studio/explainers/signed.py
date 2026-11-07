"""The orchestrator's by-eye rows (eye.*) as gate numbers, only when the strip is signed by the orchestrator.

    python3 signed.py STRIP.json [--out numbers/eye_<film>.json]

STRIP: {"by": "cc-64d05f6e", "film": "whatsapp", "gate": {"eye.real_person": 1, "eye.light": 0, ...}, "notes": {...}}
Each eye.* item becomes {"value": 0|1, "where": the note}; a strip signed by anyone else is an error on every row.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SIGNER = "cc-64d05f6e"
EYE = ("eye.real_person", "eye.light", "eye.hair_garment", "eye.graphics")


def rows(strip: dict, signer: str = SIGNER) -> dict:
    notes = strip.get("notes") or {}
    if strip.get("by") != signer:
        return {k: {"value": None, "error": f"not signed by {signer} (by={strip.get('by')!r})"} for k in EYE}
    g = strip.get("gate") or {}
    return {k: ({"value": int(g[k]), "where": f"{strip.get('film', '')}: {notes.get(k, '')}".strip(": ")}
                if k in g else {"value": None, "error": "not judged"}) for k in EYE}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("strip")
    ap.add_argument("--out", default="")
    x = ap.parse_args(argv)
    out = json.dumps({"gate": rows(json.loads(Path(x.strip).read_text()))}, indent=1)
    if x.out:
        Path(x.out).write_text(out + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
