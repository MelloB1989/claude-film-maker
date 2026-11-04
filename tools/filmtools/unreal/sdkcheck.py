"""Scripts that cannot drift: every `ue.<area>.<verb>(...)` and `ue.call("area.verb", ...)` in a Python file is checked
against the op schema (the op exists, every keyword is one of its arguments, every required one is given unless
the call splats **kwargs). `film-ue dx sdk FILE...` (default: examples/ and films/ scripts); a test runs it on the
SDK examples. Works on any SDK handle name (`ue`, `self.ue`, `unreal_`: the last two attributes before the call)."""
from __future__ import annotations

import ast
from pathlib import Path

from . import errors, schema as _schema
from .sdk import gen

SDK_OWN = {"_wait", "_timeout"}


def calls(tree: ast.AST, ix: dict) -> list:
    """(line, op name, {kw names}, splat) for each SDK call in a tree."""
    out = []
    verbs = {(o["area"], gen.ident(o["verb"])): n for n, o in ix["ops"].items() if o["area"]}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        kws = {k.arg for k in node.keywords if k.arg}
        splat = any(k.arg is None for k in node.keywords)
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute) and f.value.attr in ix["areas"]:
            name = verbs.get((f.value.attr, f.attr)) or f"{f.value.attr}.{f.attr}"
            out.append((node.lineno, name, kws, splat))
        elif (isinstance(f, ast.Attribute) and f.attr == "call" and node.args and isinstance(node.args[0], ast.Constant)
              and isinstance(node.args[0].value, str) and "." in node.args[0].value):
            out.append((node.lineno, node.args[0].value, kws - {"wait", "timeout"}, splat))
    return out


def check(paths, ix: dict | None = None) -> list:
    """[(file, line, op, problem)]"""
    ix = ix or _schema.index(_schema.load())
    probs = []
    for p in paths:
        p = Path(p)
        try:
            tree = ast.parse(p.read_text(), filename=str(p))
        except SyntaxError as e:
            probs.append((str(p), e.lineno or 0, "", f"does not parse: {e.msg}"))
            continue
        for line, name, kws, splat in calls(tree, ix):
            o = ix["ops"].get(name)
            if o is None:
                probs.append((str(p), line, name, f"no op {name}" + (f" (did you mean {', '.join(errors.close(name, ix['ops']))}?)"
                                                                      if errors.close(name, ix["ops"]) else "")))
                continue
            names = {q["name"] for q in o["params"]}
            for k in sorted(kws - names - SDK_OWN):
                if not o.get("varkw"):
                    probs.append((str(p), line, name, f"{name} takes no {k!r}" + (
                        f" (did you mean {', '.join(errors.close(k, sorted(names)))}?)" if errors.close(k, sorted(names)) else "")))
            if not splat:
                missing = [q["name"] for q in o["params"] if q["required"] and q["name"] not in kws]
                if missing:
                    probs.append((str(p), line, name, f"{name} needs {', '.join(missing)}"))
    return probs


def default_paths() -> list:
    root = _schema.ROOT
    return sorted(p for g in ("examples/**/*.py", "films/*/unreal/**/*.py") for p in root.glob(g))
