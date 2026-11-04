"""WP11's client phase: a small spec planned and applied through the SDK against the real editor, in its own scratch
level: it must converge (the second plan empty), notice drift and fix only that, and the generated CLI must answer
--json for a real op. Takes ~20 s. Needs: nothing."""
from __future__ import annotations

import json
import subprocess
import sys

from .. import spec


def _docs(t):
    lvl = f"{t.scratch}/L_dx_client"
    return [
        {"kind": "level", "version": 1, "path": lvl},
        {"kind": "actor", "version": 1, "name": t.prefix + "Floor", "shape": "plane", "size": [1000, 1000, 100]},
        {"kind": "actor", "version": 1, "name": t.prefix + "Box", "shape": "cube", "loc": [0, 0, 50],
         "rot": {"yaw": 30}},
        {"kind": "actor", "version": 1, "name": t.prefix + "Key", "cls": "PointLight", "loc": [200, 100, 300],
         "look_at": [0, 0, 50]},
    ]


def run(ue, t):
    docs = [spec.jsonschema_lite.defaults(d, spec.kinds()[d["kind"]].schema_doc()) for d in _docs(t)]
    for d in docs:
        t.check(f"spec validates: {d['kind']} {d.get('name', d.get('path'))}",
                spec.validate_doc(d, spec.kinds()[d["kind"]]), [])
    try:
        first = spec.plan(docs, ue)
        t.check("first plan has no errors", [i.error for i in first if i.error], [])
        t.ok("first plan has steps", len(spec.pending(first)) >= 4, detail=spec.plan_text(first))
        res = spec.apply(docs, ue)
        t.ok("apply converged", res.get("converged"), detail=json.dumps(res.get("left") or res, default=str)[:1500])
        again = spec.plan(docs, ue)
        t.check("second plan is empty", spec.pending(again), [])
        box = t.prefix + "Box"
        ue.level.move(label=box, loc=[30, 0, 50])
        drift = spec.plan(docs, ue)
        steps = [(s["op"], s["args"].get("label")) for s in spec.pending(drift)]
        t.check("drift: one move of the moved actor", steps, [("level.move", box)])
        spec.apply(docs, ue)
        t.check("drift fixed", spec.pending(spec.plan(docs, ue)), [])
        cli = subprocess.run([sys.executable, "-m", "filmtools.unreal.cli", "level", "actors", "--contains",
                              t.prefix, "--json"], capture_output=True, text=True, timeout=300)
        try:
            doc = json.loads(cli.stdout)
        except ValueError:
            doc = {"ok": False, "raw": cli.stdout[-500:] + cli.stderr[-500:]}
        t.ok("film-ue level actors --json answers", doc.get("ok") and len(doc.get("result") or []) >= 3,
             detail=json.dumps(doc, default=str)[:800])
        bad = subprocess.run([sys.executable, "-m", "filmtools.unreal.cli", "level", "move", "--label", t.prefix + "Nope",
                              "--json"], capture_output=True, text=True, timeout=300)
        try:
            err = json.loads(bad.stdout).get("error") or {}
        except ValueError:
            err = {}
        t.ok("a missing actor is an actionable error", err.get("code") == "not_found" or bool(err.get("hint")),
             detail=json.dumps(err)[:500])
    finally:
        ue.call("selftest.cleanup", area="dx_client")
