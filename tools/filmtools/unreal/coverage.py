"""`film-ue dx coverage`: which ops the selftests exercise, read statically (no box): for each selftest module
(unreal/fmbridge/selftest/<area>.py) the op names it passes to t.op / t.call / t.raises / t.idempotent (and any
"area.verb" string it mentions), against the ops of the areas it covers (AREAS, default its name). Areas with no
selftest at all are listed first. On a box, each report's ops_covered / ops_missed is the real measure."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from . import schema as _schema

SELFTESTS = _schema.ROOT / "unreal" / "fmbridge" / "selftest"


def _module_info(path: Path, op_names: set) -> dict:
    tree = ast.parse(path.read_text(errors="replace"))
    areas = [path.stem]
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "AREAS" for t in n.targets):
            try:
                areas = list(ast.literal_eval(n.value))
            except ValueError:
                pass
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in op_names:
            used.add(node.value)
    text = path.read_text(errors="replace")
    used |= {m for m in re.findall(r"[\"']([a-z_]+\.[a-z_0-9]+)[\"']", text) if m in op_names}
    return {"areas": areas, "used": used}


def report(ix: dict | None = None) -> dict:
    ix = ix or _schema.index(_schema.load())
    names = set(ix["ops"])
    mods = {p.stem: _module_info(p, names) for p in sorted(SELFTESTS.glob("*.py")) if not p.stem.startswith("_")}
    covered_areas = {a for m in mods.values() for a in m["areas"]}
    out = {"areas_without_selftest": sorted(a for a in ix["areas"] if a not in covered_areas), "selftests": {}}
    for stem, m in mods.items():
        mine = sorted(n for n in names if n.split(".")[0] in m["areas"])
        hit = sorted(n for n in mine if n in m["used"])
        out["selftests"][stem] = {"areas": m["areas"], "ops": len(mine), "exercised": len(hit),
                                  "missed": [n for n in mine if n not in m["used"]]}
    total = sum(s["ops"] for s in out["selftests"].values())
    out["exercised_fraction"] = round(sum(s["exercised"] for s in out["selftests"].values()) / total, 3) if total else 0.0
    return out


def text(r: dict) -> str:
    lines = [f"op areas with no selftest: {', '.join(r['areas_without_selftest']) or 'none'}", ""]
    for stem, s in r["selftests"].items():
        lines.append(f"  {stem:<10} covers {','.join(s['areas']):<22} {s['exercised']:>3}/{s['ops']:<3} ops"
                     + (f"   missed: {', '.join(s['missed'][:8])}{' ...' if len(s['missed']) > 8 else ''}" if s["missed"] else ""))
    lines.append(f"\n  exercised (statically): {r['exercised_fraction'] * 100:.0f}% of the covered areas' ops")
    return "\n".join(lines)
