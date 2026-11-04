"""The op schema: every bridge op (unreal/fmbridge/ops) described as data, so the CLI (`film-ue <area> <verb>`), the
Python SDK (filmtools.unreal.sdk) and `film-ue describe` are generated from one source and never drift from the ops.

It is read STATICALLY from the ops' source (ast: no `unreal`, no editor, no box), so it works offline, in exactly the
shape the running bridge's `ops.schema` op answers (fmbridge/ops/__init__.py), so either can feed the generators:

    {"version": 1, "ops": [{"name": "seq.key_float", "area": "seq", "verb": "key_float", "module": "fmbridge.ops.seq",
      "file": "unreal/fmbridge/ops/seq.py", "line": 384, "summary": "<first doc line>", "doc": "<full docstring>",
      "params": [{"name": "x", "kind": "keyword|positional", "type": "<annotation src or null>", "required": true,
                  "default": <json literal or null>}],
      "returns": "<annotation src or null>", "multi_tick": <generator function>, "mutates": <bool|null>,
      "idempotent": <bool|null>, "tags": []}],
     "broken": {"fmbridge.ops.x": "<import error>"},
     "areas": {"seq": "<the module docstring's first line>"}}          (areas: this extractor's addition)

mutates / idempotent / tags come from the decorator: @op("x.y", mutates=True, idempotent=True, tags=["slow"]).
`index(schema)` adds what the generators need on top (per param: the CLI flag, a value kind among int, float, bool,
str, list, dict, any, nullable, its doc line, choices; per op: examples), so the wire shape stays the lead's.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

VERSION = 1
ROOT = Path(__file__).resolve().parents[3]
OPS_DIR = ROOT / "unreal" / "fmbridge" / "ops"
SNAPSHOT = Path(__file__).with_name("ops_schema.json")

_SCALARS = {"int": "int", "float": "float", "bool": "bool", "str": "str", "list": "list", "tuple": "list",
            "dict": "dict", "set": "list", "List": "list", "Dict": "dict", "Tuple": "list", "Sequence": "list",
            "Mapping": "dict", "Any": "any", "object": "any"}


# --------------------------------------------------------------------------------------------------------- types

def _ann_type(node: ast.AST | None) -> tuple[str, bool]:
    """An annotation to (type, nullable): `list | None` -> ("list", True), `dict[str, float]` -> ("dict", False)."""
    if node is None:
        return "any", False
    if isinstance(node, ast.Constant) and isinstance(node.value, str):  # a string annotation
        try:
            return _ann_type(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return "any", False
    if isinstance(node, ast.Constant) and node.value is None:
        return "none", True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        parts = [_ann_type(node.left), _ann_type(node.right)]
        kinds = {t for t, _ in parts if t != "none"}
        nullable = any(n for _, n in parts)
        return (kinds.pop() if len(kinds) == 1 else "any"), nullable
    if isinstance(node, ast.Subscript):
        base = node.value.attr if isinstance(node.value, ast.Attribute) else getattr(node.value, "id", "")
        if base == "Optional":
            return _ann_type(node.slice)[0], True
        if base == "Literal":
            return "str", False
        if base == "Union":
            elts = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            parts = [_ann_type(e) for e in elts]
            kinds = {t for t, _ in parts if t != "none"}
            return (kinds.pop() if len(kinds) == 1 else "any"), any(n for _, n in parts)
        return _SCALARS.get(base, "any"), False
    name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
    return _SCALARS.get(name, "any"), False


def _literal(node: ast.AST | None):
    """A default's value when it is a literal, else {"expr": its source}."""
    if node is None:
        return None
    try:
        v = ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return {"expr": ast.unparse(node)}
    return list(v) if isinstance(v, (tuple, set)) else v


def _default_type(v) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict) and "expr" not in v:
        return "dict"
    return "any"


def _choices(doc: str, name: str) -> list | None:
    """Values a docstring names for an argument, only in the explicit form "`name` one of a, b, c" (never guessed)."""
    m = re.search(rf"`{re.escape(name)}`\s*(?::|is)?\s*one of\s+([^.;\n]+)|\b{re.escape(name)}\s*(?::|is)\s*one of\s+([^.;\n]+)", doc)
    if not m:
        return None
    vals = [v.strip(" `\"'") for v in re.split(r",|\bor\b|\|", m.group(1) or m.group(2))]
    vals = [v for v in vals if re.fullmatch(r"[\w.\-/]+", v)]
    return vals or None


# ------------------------------------------------------------------------------------------------------ docstrings

_ARGS_HEAD = re.compile(r"^\s*(Args|Arguments|Parameters|Params)\s*:\s*$", re.I)
_RET_HEAD = re.compile(r"^\s*(Returns?|Yields?|Raises|Example|Examples)\s*:", re.I)


def param_docs(doc: str) -> dict:
    """An `Args:` section's entries (Google style: "name: text" or "name (type): text", continuation lines indented)."""
    out: dict = {}
    lines = (doc or "").splitlines()
    i = next((k for k, line in enumerate(lines) if _ARGS_HEAD.match(line)), None)
    if i is None:
        return out
    cur = None
    for line in lines[i + 1:]:
        if not line.strip():
            cur = None
            continue
        if _RET_HEAD.match(line):
            break
        m = re.match(r"^\s*[-*]?\s*`?(\w+)`?\s*(\([^)]*\))?\s*:\s*(.*)$", line)
        if m and (cur is None or len(line) - len(line.lstrip()) <= out.get("__indent", 99)):
            cur = m.group(1)
            out["__indent"] = len(line) - len(line.lstrip())
            out[cur] = m.group(3).strip()
        elif cur:
            out[cur] = (out[cur] + " " + line.strip()).strip()
    out.pop("__indent", None)
    return out


def examples(doc: str) -> list:
    """Example calls in a docstring: lines that start with `film-ue ` or follow an `Example:` heading."""
    out, take = [], False
    for line in (doc or "").splitlines():
        s = line.strip()
        if re.match(r"^Examples?\s*:", s, re.I):
            take = True
            rest = s.split(":", 1)[1].strip()
            if rest:
                out.append(rest)
            continue
        if s.startswith(("film-ue ", "$ film-ue ")):
            out.append(s.lstrip("$ "))
        elif take and s:
            out.append(s)
        elif take and not s:
            take = False
    return list(dict.fromkeys(out))


def summary(doc: str) -> str:
    """The first sentence (or line) of a docstring."""
    text = " ".join((doc or "").strip().split("\n\n")[0].split())
    m = re.match(r"(.+?(?<!\be\.g)(?<!\bi\.e)(?<!\betc)(?<!\bvs)[.!?])(\s|$)", text)
    return (m.group(1) if m else text)[:240]


# ------------------------------------------------------------------------------------------------------ extraction

def _op_decorator(fn) -> tuple[str, dict] | None:
    for d in fn.decorator_list:
        if not isinstance(d, ast.Call):
            continue
        f = d.func
        fname = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if fname != "op" or not d.args or not isinstance(d.args[0], ast.Constant):
            continue
        return str(d.args[0].value), {k.arg: _literal(k.value) for k in d.keywords if k.arg}
    return None


def _yields(fn) -> bool:
    """A generator (a multi-tick job): yields in its own body, not in a nested function."""
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.Yield, ast.YieldFrom)):
            return True
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(n))
    return False


def _wire_params(fn) -> list:
    a = fn.args
    pos = a.posonlyargs + a.args
    defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    out = []
    for arg, dflt, kind in ([(x, d, "positional") for x, d in zip(pos, defaults)] +
                            [(x, d, "keyword") for x, d in zip(a.kwonlyargs, a.kw_defaults)]):
        v = _literal(dflt) if dflt is not None else None
        if isinstance(v, dict) and set(v) == {"expr"}:
            v = None  # not a JSON literal: the wire shape says null
        out.append({"name": arg.arg, "kind": kind, "type": ast.unparse(arg.annotation) if arg.annotation else None,
                    "required": dflt is None, "default": v})
    return out


def _wire(name: str, meta: dict, fn, doc: str, module: str, file: str, multi: bool) -> dict:
    area, _, verb = name.partition(".")
    tags = meta.get("tags")
    return {"name": name, "area": area if verb else "", "verb": verb or name, "module": module, "file": file,
            "line": getattr(fn, "lineno", None), "summary": summary(doc), "doc": doc, "params": _wire_params(fn),
            "returns": ast.unparse(fn.returns) if getattr(fn, "returns", None) else None, "multi_tick": multi,
            "mutates": meta.get("mutates"), "idempotent": meta.get("idempotent"),
            "tags": list(tags) if isinstance(tags, (list, tuple)) else []}


def extract(ops_dir: Path = OPS_DIR, root: Path = ROOT) -> dict:
    """Read every @op("area.verb") under ops_dir (recursively) into the schema; a module that does not parse is listed
    under "broken" like the bridge lists a module that does not import."""
    ops, areas, broken = [], {}, {}
    ops_dir = Path(ops_dir)
    for path in sorted(ops_dir.rglob("*.py")):
        parts = path.relative_to(ops_dir).with_suffix("").parts
        module = ".".join(("fmbridge", "ops") + tuple(p for p in parts if p != "__init__"))
        try:
            rel = path.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            rel = path.as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as e:
            broken[module] = f"SyntaxError: {e.msg} ({rel}:{e.lineno})"
            continue
        mod_doc = ast.get_docstring(tree) or ""
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            dec = _op_decorator(node)
            if not dec:
                continue
            name, meta = dec
            o = _wire(name, meta, node, ast.get_docstring(node) or "", module, rel, _yields(node))
            ops.append(o)
            if o["area"] and mod_doc and (o["area"] not in areas or parts[-1] in (o["area"], "__init__")):
                areas[o["area"]] = summary(mod_doc)
    ops.sort(key=lambda o: o["name"])
    return {"version": VERSION, "ops": ops, "broken": broken, "areas": dict(sorted(areas.items()))}


def fingerprint(schema: dict) -> str:
    """What the generated code was made from: changes when any op, argument or docstring does."""
    body = json.dumps(sorted(schema["ops"], key=lambda o: o["name"]), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def from_list(listing: dict) -> dict:
    """The schema from an older bridge that has only `list` (full=True: {name: "name(sig): doc"}), for a box whose
    bridge predates ops.schema: the same shape without file/line/multi_tick."""
    ops = []
    for name, text in sorted(listing.items()):
        m = re.match(r"^([\w.]+)(\(.*?\))(\s*->\s*[^:]+)?:\s?(.*)$", text, re.S)
        if not m:
            continue
        try:
            fn = ast.parse(f"def _f{m.group(2)}: pass").body[0]
        except SyntaxError:  # a default whose repr is not Python (<object at ...>)
            fn = ast.parse("def _f(**kwargs): pass").body[0]
        o = _wire(name, {}, fn, m.group(4).strip(), "", "", False)
        o["returns"] = (m.group(3) or "").replace("->", "").strip() or None
        o["line"] = None
        ops.append(o)
    return {"version": VERSION, "ops": ops, "broken": {}, "areas": {}}


# ---------------------------------------------------------------------------------------------------------- index

def _ptype(p: dict) -> tuple[str, bool]:
    t, nullable = "any", False
    if p.get("type"):
        try:
            t, nullable = _ann_type(ast.parse(p["type"], mode="eval").body)
        except SyntaxError:
            pass
    if t in ("any", "none") and not p["required"]:
        t = _default_type(p.get("default")) if p.get("default") is not None else "any"
    if not p["required"] and p.get("default") is None:
        nullable = True
    return t, nullable


def index(schema: dict) -> dict:
    """The schema keyed for the generators: {"ops": {name: op + derived}, "areas": {area: {"doc", "ops": [...]}}}.
    Each param gains flag (CLI spelling: `rot_` -> `rot`), kind_of (the value kind), nullable, doc, choices."""
    ops, areas = {}, {}
    for o in schema["ops"]:
        o = dict(o)
        pdocs = param_docs(o.get("doc") or "")
        params = []
        for p in o["params"]:
            p = dict(p)
            p["flag"] = p["name"].rstrip("_").replace("_", "-")
            p["value"], p["nullable"] = _ptype(p)
            p["help"] = pdocs.get(p["name"]) or pdocs.get(p["name"].rstrip("_"), "")
            ch = _choices(o.get("doc") or "", p["name"])
            if ch:
                p["choices"] = ch
            params.append(p)
        o["params"] = params
        o["examples"] = examples(o.get("doc") or "")
        ops[o["name"]] = o
        if o["area"]:
            areas.setdefault(o["area"], {"doc": schema.get("areas", {}).get(o["area"], ""), "ops": []})["ops"].append(o["name"])
    return {"ops": ops, "areas": dict(sorted(areas.items())), "broken": schema.get("broken", {}),
            "fingerprint": fingerprint(schema)}


# ----------------------------------------------------------------------------------------------------------- load

def load(path: Path | None = None) -> dict:
    """The schema: extracted from the ops in this checkout when they are here (always current), else the committed
    snapshot (a copy of tools/ without the unreal/ tree)."""
    if path:
        return json.loads(Path(path).read_text())
    if OPS_DIR.is_dir():
        return extract()
    return json.loads(SNAPSHOT.read_text())


def write_snapshot(schema: dict | None = None, path: Path = SNAPSHOT) -> Path:
    path.write_text(json.dumps(schema or extract(), indent=1) + "\n")
    return path


def lint(schema: dict) -> list:
    """What makes an op hard for an agent to drive: no docstring, not area.verb, a required argument of unknown type,
    a positional parameter (conventions: keyword-only). [(op, problem), ...]"""
    out = []
    for o in schema["ops"]:
        name = o["name"]
        if not o["doc"]:
            out.append((name, "no docstring"))
        if not o["area"] and name != "list":
            out.append((name, "not area.verb"))
        for p in o["params"]:
            if p["required"] and not p["type"]:
                out.append((name, f"required argument {p['name']!r} has no annotation"))
    for mod, err in schema.get("broken", {}).items():
        out.append((mod, "broken: " + err))
    return out
