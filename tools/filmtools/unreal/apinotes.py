"""Which engine APIs the bridge uses that no doc's API_NOTES mentions (BACKLOG B40): the "verify every engine API
against the source" rule, checked. Scans unreal/fmbridge/**/*.py for `unreal.<Name>` and `unreal.<Name>.<member>`
and looks for each Name (and member) in docs/unreal/*.md.

    python -m filmtools.unreal.apinotes [--json] [--missing-only]
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def used(root: Path = ROOT) -> dict:
    """{"Name" or "Name.member": sorted ["file:line", ...]} for every unreal.* reference under unreal/fmbridge."""
    out: dict = {}
    for p in sorted((root / "unreal" / "fmbridge").rglob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = p.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "unreal"):
                continue
            name = node.attr
            out.setdefault(name, set()).add(f"{rel}:{node.lineno}")
        for node in ast.walk(tree):  # unreal.Name.member
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) and \
                    isinstance(node.value.value, ast.Name) and node.value.value.id == "unreal":
                out.setdefault(f"{node.value.attr}.{node.attr}", set()).add(f"{rel}:{node.lineno}")
    return {k: sorted(v) for k, v in sorted(out.items())}


def documented(root: Path = ROOT) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted((root / "docs" / "unreal").glob("*.md")))


def _snake_to_camel(s: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in s.split("_"))


def report(root: Path = ROOT) -> dict:
    """{"used": n, "missing": {name: [where]}, "covered": n}. A name counts as covered when the docs mention it as
    written, or (for a member) its CamelCase engine name, e.g. get_actor_bounds or GetActorBounds."""
    docs = documented(root)
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", docs))
    missing = {}
    u = used(root)
    for name, where in u.items():
        parts = name.split(".")
        leaf = parts[-1]
        ok = leaf in words or _snake_to_camel(leaf) in words or (leaf.isupper() and parts[0] in words)
        if not ok:
            missing[name] = where
    return {"used": len(u), "covered": len(u) - len(missing), "missing": missing}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    r = report()
    if a.json:
        print(json.dumps(r, indent=1))
        return
    print(f"{r['covered']}/{r['used']} engine names used by the bridge appear in docs/unreal/*.md")
    by_file: dict = {}
    for name, where in r["missing"].items():
        by_file.setdefault(where[0].split(":")[0], []).append(name)
    for f, names in sorted(by_file.items()):
        print(f"  {f}: {', '.join(sorted(names))}")


if __name__ == "__main__":
    main()
