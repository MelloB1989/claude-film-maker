"""Declarative specs: `film-ue plan SPEC` shows the steps, `film-ue apply SPEC` runs them and checks it converged
(docs/unreal/CONVENTIONS.md §7, docs/unreal/dx.md "Specs").

A spec file (YAML, several documents split by `---`; or JSON, one object or a list) holds documents, each one thing:

    kind: actor                 # whose planner handles it (film-ue plan --kinds lists them)
    version: 1
    name: Key                   # unique per kind
    cls: RectLight              # ... the kind's own fields, validated by schemas/<kind>.schema.json
    loc: [300, 0, 250]

Two documents belong to the engine: `{kind: vars, vars: {fps: 24}}` (then `${fps}` in any string of the documents
after it; a string that is exactly "${fps}" takes the value's type; `--set fps=30` overrides) and
`{kind: include, files: [other.yaml]}` (relative to this file).

A kind is a pure planner plus a reader, registered by the area that owns the noun:

    from filmtools.unreal.spec import register_kind
    register_kind("render", plan=plan, describe=lambda ue, spec: ue.render.describe(name=spec["name"]), order=90)

    def plan(spec: dict, state: dict) -> list[dict]:     # no unreal, no I/O: unit-test it with dicts
        return [{"op": "render.mrq", "args": {...}, "why": "no render job yet"}]

apply runs every step through the SDK (in kind `order`, then file order), describes again and plans again: converged
means the second plan is empty (steps marked "always": true, e.g. the `op` kind's, do not count). A step that fails
stops that document's later steps and is reported with the bridge's code, message and hint.
"""
from __future__ import annotations

import copy
import importlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import errors, jsonschema_lite

SPEC_VERSION = 1
SCHEMAS = Path(__file__).with_name("schemas")
ENGINE_KINDS = ("vars", "include")
ENVELOPE = {"kind": {"type": "string"}, "version": {"type": "integer"}, "name": {"type": "string"},
            "description": {"type": "string"}}


class SpecError(ValueError):
    def __init__(self, problems: list):
        super().__init__("; ".join(p.message for p in problems))
        self.problems = problems


# ---------------------------------------------------------------------------------------------------------- kinds

@dataclass
class KindDef:
    name: str
    plan: Callable[[dict, dict], list]                    # (spec, state) -> [{"op", "args", "why"}], pure
    describe: Callable | None = None                      # (ue, spec) -> state (the area's describe op)
    describe_many: Callable | None = None                 # (ue, [spec]) -> {name: state}: one call for all
    order: int = 50                                       # level 0, assets 10, characters 20, layout 30, lighting 40,
    schema: dict | str | None = None                      #   cameras 50, sequences 60, shots 70, op 80, renders 90
    key: str = "name"
    doc: str = ""
    module: str = ""

    def schema_doc(self) -> dict | None:
        s = self.schema
        if isinstance(s, str):
            s = json.loads((SCHEMAS / s if not Path(s).is_absolute() else Path(s)).read_text())
        elif s is None and (SCHEMAS / f"{self.name}.schema.json").exists():
            s = json.loads((SCHEMAS / f"{self.name}.schema.json").read_text())
        return s


_KINDS: dict = {}
_discovered = {"done": False}


def register_kind(name: str, plan: Callable, describe: Callable | None = None, **kw) -> KindDef:
    """Register a spec kind (see the module docstring). Registering a name twice from two modules is an error."""
    mod = getattr(plan, "__module__", "")
    if name in _KINDS and _KINDS[name].module != mod:
        raise ValueError(f"spec kind {name!r} registered twice ({_KINDS[name].module} and {mod})")
    k = KindDef(name, plan, describe, module=mod, **kw)
    if not k.doc:
        k.doc = (sys.modules.get(mod).__doc__ or "").strip().split("\n\n")[0] if mod in sys.modules else ""
    _KINDS[name] = k
    return k


def kinds() -> dict:
    """Every registered kind: the kinds/ package, and any filmtools/unreal module that calls register_kind or
    defines SPEC_KINDS = [{"name", "plan", "describe", ...}] (found by reading the files, imported once)."""
    if not _discovered["done"]:
        _discovered["done"] = True
        here = Path(__file__).parent
        mods = [f"filmtools.unreal.kinds.{p.stem}" for p in sorted((here / "kinds").glob("*.py")) if p.stem != "__init__"]
        for p in sorted(here.glob("*.py")):
            if p.stem in ("spec", "__init__"):
                continue
            text = p.read_text(errors="replace")
            if "register_kind(" in text or "SPEC_KINDS" in text:
                mods.append(f"filmtools.unreal.{p.stem}")
        for m in mods:
            try:
                mod = importlib.import_module(m)
            except Exception as e:  # one broken kind module must not take the others down
                sys.stderr.write(f"film-ue: {m} did not import ({type(e).__name__}: {e}); its kinds are missing\n")
                continue
            for d in getattr(mod, "SPEC_KINDS", []) or []:
                if isinstance(d, KindDef):
                    _KINDS.setdefault(d.name, d)
                elif d.get("name") not in _KINDS:
                    d = dict(d)
                    register_kind(d.pop("name"), d.pop("plan"), d.pop("describe", None), **d)
    return _KINDS


# ------------------------------------------------------------------------------------------------------------ load

_VAR = re.compile(r"\$\{(\w+)\}")


def substitute(v, vars_: dict, where: str = ""):
    """${name} in every string; a string that is exactly "${name}" takes the variable's value with its type."""
    def missing(n):
        return SpecError([errors.Problem("bad_spec", f"{where}: no variable {n!r}", "define it in a `kind: vars` "
                                         "document before this one, or pass --set NAME=VALUE", errors.close(n, vars_))])
    if isinstance(v, str):
        m = _VAR.fullmatch(v)
        if m:
            if m.group(1) not in vars_:
                raise missing(m.group(1))
            return vars_[m.group(1)]

        def rep(mm):
            if mm.group(1) not in vars_:
                raise missing(mm.group(1))
            return str(vars_[mm.group(1)])
        return _VAR.sub(rep, v)
    if isinstance(v, list):
        return [substitute(x, vars_, where) for x in v]
    if isinstance(v, dict):
        return {k: substitute(x, vars_, where) for k, x in v.items()}
    return v


def read_docs(path: Path) -> list:
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        import yaml
        return [d for d in yaml.safe_load_all(text) if d is not None]
    v = json.loads(text)
    return v if isinstance(v, list) else [v]


def _coerce(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def validate_doc(doc: dict, kd: KindDef) -> list:
    """[(path, message, candidates)] against the kind's schema (the envelope kind/version/name always allowed)."""
    s = kd.schema_doc()
    if not s:
        return []
    s = copy.deepcopy(s)
    if s.get("type", "object") == "object" and "properties" in s:
        for k, v in ENVELOPE.items():
            s["properties"].setdefault(k, v)
    return jsonschema_lite.validate(doc, s)


def load(paths, sets: list | None = None) -> list:
    """Spec files (in order) to their documents: includes resolved, variables substituted, each validated by its
    kind's schema, names unique per kind. Each doc gains "_src" (file:index). Raises SpecError with every problem."""
    reg = kinds()
    overrides = {k: _coerce(v) for k, v in (s.split("=", 1) for s in (sets or []))}
    vars_: dict = dict(overrides)
    out, problems, seen, names = [], [], set(), {}

    def take(path: Path):
        path = path.resolve()
        if path in seen:
            return
        seen.add(path)
        if not path.exists():
            problems.append(errors.Problem("bad_spec", f"no spec file {path}", "includes are relative to the file"))
            return
        try:
            docs = read_docs(path)
        except Exception as e:
            problems.append(errors.Problem("bad_spec", f"{path.name}: does not parse: {e}", "check the YAML/JSON"))
            return
        for i, d in enumerate(docs):
            where = f"{path.name}#{i + 1}"
            if not isinstance(d, dict) or "kind" not in d:
                problems.append(errors.Problem("bad_spec", f"{where}: a document is a mapping with a `kind`",
                                               "film-ue plan --kinds lists them", []))
                continue
            if d["kind"] == "vars":
                vars_.update({k: v for k, v in (d.get("vars") or {}).items() if k not in overrides})
                continue
            if d["kind"] == "include":
                for f in d.get("files") or []:
                    take(path.parent / f)
                continue
            try:
                d = substitute(copy.deepcopy(d), vars_, where)
            except SpecError as e:
                problems.extend(e.problems)
                continue
            kd = reg.get(d["kind"])
            if not kd:
                problems.append(errors.Problem("bad_spec", f"{where}: unknown kind {d['kind']!r}",
                                               "film-ue plan --kinds lists them", errors.close(str(d["kind"]), reg)))
                continue
            if d.get("version", SPEC_VERSION) != SPEC_VERSION:
                problems.append(errors.Problem("bad_spec", f"{where}: version {d.get('version')}; this engine reads "
                                                           f"{SPEC_VERSION}", ""))
            for p, msg, cands in validate_doc(d, kd):
                problems.append(errors.Problem("bad_spec", f"{where} ({kd.name} {d.get(kd.key)!r}) {p}: {msg}",
                                               f"film-ue plan --kinds {kd.name} shows its fields", cands))
            key = d.get(kd.key)
            if key in (None, ""):
                problems.append(errors.Problem("bad_spec", f"{where}: a {kd.name} needs {kd.key!r}", ""))
            elif (kd.name, key) in names:
                problems.append(errors.Problem("bad_spec", f"{where}: {kd.name} {key!r} again (first in "
                                                           f"{names[(kd.name, key)]})", "names are unique per kind"))
            names[(kd.name, key)] = where
            s = kd.schema_doc()
            d = jsonschema_lite.defaults(d, s) if s else d
            d["_src"] = where
            out.append(d)

    for p in ([paths] if isinstance(paths, (str, Path)) else paths):
        take(Path(p))
    if problems:
        raise SpecError(problems)
    return out


# ------------------------------------------------------------------------------------------------------------ plan

@dataclass
class Item:
    kind: str
    name: str
    spec: dict
    state: object = None
    steps: list = field(default_factory=list)
    error: dict | None = None
    done: list = field(default_factory=list)              # results of the steps that ran

    def as_dict(self) -> dict:
        d = {"kind": self.kind, "name": self.name, "steps": self.steps, "src": self.spec.get("_src", "")}
        if self.error:
            d["error"] = self.error
        if self.done:
            d["done"] = self.done
        return d


def _problem(e: Exception, what: str) -> errors.Problem:
    from .sdk import OpError
    if isinstance(e, OpError):
        return e.problem
    return errors.Problem("kind_failed", f"{what}: {type(e).__name__}: {e}", "a bug in the kind's planner or reader: "
                          "film-ue plan --offline --state FILE reproduces it without a box")


def _check_steps(steps, kd: KindDef, index: dict) -> list:
    """Steps are [{"op", "args", "why"}]: a planner bug (an unknown op, a misspelt argument) fails at plan time."""
    out = []
    if not isinstance(steps, list):
        raise TypeError(f"{kd.name}.plan returned {type(steps).__name__}, not a list of steps")
    for s in steps:
        if not isinstance(s, dict) or "op" not in s:
            raise TypeError(f"{kd.name}.plan: a step is {{'op', 'args', 'why'}}, got {s!r}"[:300])
        s = {"op": s["op"], "args": dict(s.get("args") or {}), "why": s.get("why", ""),
             **{k: v for k, v in s.items() if k not in ("op", "args", "why")}}
        if index and s["op"] in index["ops"]:
            p = errors.check_args(s["op"], s["args"], index)
            if p:
                raise errors_as_exc(p)
        out.append(s)
    return out


class _PlanError(Exception):
    def __init__(self, p: errors.Problem):
        super().__init__(p.message)
        self.problem = p


def errors_as_exc(p: errors.Problem) -> Exception:
    return _PlanError(p)


def plan(docs: list, ue=None, state: dict | None = None, only: set | None = None, index: dict | None = None) -> list:
    """Each document's steps. State comes from the kind's describe through `ue`, or from `state` ({kind: {name:
    state}}, for planning offline)."""
    from . import schema as _schema
    reg = kinds()
    index = index or _schema.index(_schema.load())
    docs = [d for d in docs if not only or d["kind"] in only]
    order = sorted(range(len(docs)), key=lambda i: (reg[docs[i]["kind"]].order, i))
    items = []
    by_kind: dict = {}
    for i in order:  # readers and planners see the document without the engine's own keys (_src)
        by_kind.setdefault(docs[i]["kind"], []).append({k: v for k, v in docs[i].items() if not k.startswith("_")})
    states: dict = {}
    for kname, ds in by_kind.items():
        kd = reg[kname]
        if state is not None:
            states[kname] = {d[kd.key]: (state.get(kname) or {}).get(d[kd.key]) for d in ds}
            continue
        try:
            if kd.describe_many:
                got = kd.describe_many(ue, ds) or {}
                states[kname] = {d[kd.key]: got.get(d[kd.key]) for d in ds}
            else:
                states[kname] = {d[kd.key]: (kd.describe(ue, d) if kd.describe else None) for d in ds}
        except Exception as e:
            states[kname] = _problem(e, f"{kname} describe")
    for i in order:
        d = docs[i]
        kd = reg[d["kind"]]
        it = Item(kd.name, d[kd.key], d)
        st = states[kd.name]
        if isinstance(st, errors.Problem):
            it.error = st.as_dict()
            items.append(it)
            continue
        it.state = st.get(d[kd.key])
        try:
            it.steps = _check_steps(kd.plan({k: v for k, v in d.items() if k != "_src"}, it.state), kd, index)
        except _PlanError as e:
            it.error = e.problem.as_dict()
        except Exception as e:
            it.error = _problem(e, f"{kd.name}.plan").as_dict()
        items.append(it)
    return items


def pending(items: list) -> list:
    """The steps that keep a plan from being converged (not "always" ones)."""
    return [s for it in items for s in it.steps if not s.get("always")]


def run(items: list, ue, keep_going: bool = True) -> list:
    """Run every item's steps in order; a failing step stops that item (and every later one unless keep_going)."""
    for it in items:
        if it.error:
            if not keep_going:
                break
            continue
        for s in it.steps:
            try:
                r = ue.call(s["op"], timeout=s.get("timeout", 900), **s["args"])
                it.done.append({"op": s["op"], "ok": True, "result": r})
            except Exception as e:
                it.error = {**_problem(e, s["op"]).as_dict(), "step": s}
                it.done.append({"op": s["op"], "ok": False})
                break
        if it.error and not keep_going:
            break
    return items


def apply(docs: list, ue, only: set | None = None, keep_going: bool = True, verify: bool = True) -> dict:
    items = run(plan(docs, ue, only=only), ue, keep_going)
    failed = [it for it in items if it.error]
    out = {"ok": not failed, "items": [it.as_dict() for it in items], "summary": summarize(items)}
    if verify:
        again = plan(docs, ue, only=only)
        left = [it.as_dict() for it in again if [s for s in it.steps if not s.get("always")] or it.error]
        out["converged"] = not left
        if left:
            out["ok"] = False
            out["left"] = left
    return out


def summarize(items: list) -> dict:
    return {"documents": len(items), "steps": sum(len(it.steps) for it in items),
            "converged_docs": sum(1 for it in items if not [s for s in it.steps if not s.get("always")] and not it.error),
            "failed": sum(1 for it in items if it.error)}


def plan_text(items: list) -> str:
    lines = []
    for it in items:
        head = f"{it.kind} {it.name}"
        if it.error:
            e = it.error
            lines.append(f"  ? {head}  ERROR [{e.get('code')}] {e.get('message')}" +
                         (f"\n      hint: {e['hint']}" if e.get("hint") else ""))
        elif not it.steps:
            lines.append(f"  = {head}")
        else:
            lines.append(f"  ~ {head}")
        for s in it.steps:
            mark = "!" if s.get("always") else "+"
            args = json.dumps(s["args"], default=str)
            lines.append(f"      {mark} {s['op']} {args[:160]}" + (f"   # {s['why']}" if s.get("why") else ""))
    s = summarize(items)
    lines.append(f"  {s['documents']} documents, {s['steps']} steps, {s['converged_docs']} already converged, "
                 f"{s['failed']} failed")
    return "\n".join(lines)


def kinds_text(name: str = "") -> str:
    reg = kinds()
    if name:
        kd = reg.get(name)
        if not kd:
            return f"no kind {name!r}; did you mean: {', '.join(errors.close(name, reg))}"
        s = kd.schema_doc() or {}
        out = [f"{kd.name} (order {kd.order}, key {kd.key!r}, from {kd.module})", "", kd.doc, ""]
        for p, v in (s.get("properties") or {}).items():
            req = "required" if p in s.get("required", []) else (f"= {json.dumps(v.get('default'))}" if "default" in v else "")
            out.append(f"  {p:<16} {str(v.get('type', '')):<10} {req:<12} {v.get('description', '')}")
        if not s:
            out.append("  (no schema: schemas/%s.schema.json)" % kd.name)
        return "\n".join(out)
    return "\n".join(f"  {k:<14} order {kd.order:<3} {kd.doc.splitlines()[0] if kd.doc else ''}"[:150]
                     for k, kd in sorted(reg.items(), key=lambda kv: (kv[1].order, kv[0])))


# ------------------------------------------------------------------------------------------------------------- CLI

def main(a) -> int:
    from .sdk import Unreal
    if getattr(a, "kinds", None) is not None:
        print(kinds_text(a.kinds))
        return 0
    if not a.spec:
        sys.stderr.write("film-ue plan|apply SPEC... (film-ue plan --kinds lists the kinds)\n")
        return 2
    try:
        docs = load(a.spec, a.set)
    except SpecError as e:
        if a.json:
            print(json.dumps({"ok": False, "errors": [p.as_dict() for p in e.problems]}, indent=1))
        else:
            sys.stderr.write("\n".join(p.text() for p in e.problems) + "\n")
        return 2
    only = set(filter(None, a.only.split(","))) or None
    offline = getattr(a, "state", "")
    if a.cmd == "plan" or getattr(a, "dry_run", False):
        st = json.loads(Path(offline).read_text()) if offline else None
        items = plan(docs, None if st is not None else Unreal(), st, only)
        if a.json:
            print(json.dumps({"ok": not any(i.error for i in items), "converged": not pending(items),
                              "items": [i.as_dict() for i in items], "summary": summarize(items)}, indent=1, default=str))
        else:
            print(plan_text(items))
        return 1 if any(i.error for i in items) else 0
    res = apply(docs, Unreal(), only, keep_going=not a.stop)
    if a.json:
        print(json.dumps(res, indent=1, default=str))
    else:
        for it in res["items"]:
            mark = "?" if it.get("error") else ("~" if it["steps"] else "=")
            print(f"  {mark} {it['kind']} {it['name']}: {len(it.get('done', []))}/{len(it['steps'])} steps" +
                  (f"  ERROR [{it['error'].get('code')}] {it['error'].get('message')}  hint: {it['error'].get('hint')}"
                   if it.get("error") else ""))
        print("  converged" if res.get("converged") else "  NOT converged; still to do:\n" +
              "\n".join(f"    {x['kind']} {x['name']}: " + ", ".join(s["op"] for s in x["steps"]) +
                        (f" ERROR {x['error'].get('message')}" if x.get("error") else "") for x in res.get("left", [])))
    return 0 if res["ok"] else 1
