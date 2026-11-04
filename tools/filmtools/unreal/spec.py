"""Declarative specs: `film-ue plan SPEC` shows what would change, `film-ue apply SPEC` converges the editor to it.

A spec (YAML or JSON) names resources by kind; every kind is a plug-in (filmtools/unreal/kinds/<file>.py, found
automatically), so each area brings its own (characters, sets, lights, shots, renders) without touching this engine.

    version: 1
    vars: {fps: 24, root: /Game/Demo}            # ${fps}, ${root} anywhere in a string; film-ue apply --set fps=30
    include: [lights.yaml]                       # other specs merged first (paths relative to this one)
    level: {path: "${root}/L_Demo"}              # a section per kind: a mapping for one, a list for many
    actors:
      - {name: Floor, shape: plane, loc: [0, 0, 0], size: [2000, 2000, 1]}
    resources:                                   # or any kind in one ordered list
      - {kind: actor, name: Box, shape: cube, loc: [0, 0, 50]}

The engine: load + validate every resource against its kind (unknown fields fail with candidates), read the current
state per kind in one batch, diff (create / update with the changed fields / noop; --prune: delete what the kind owns
and the spec no longer names), then apply in kind order (deletes in reverse) and plan again to VERIFY the editor
converged: an apply whose re-plan is not all noop reports `converged: false` with the drift.

A kind (filmtools.unreal.kinds.Kind) implements read / apply / delete (+ owned for --prune); diffing is generic over
its `compare` fields with tolerances, or its own plan(). See docs/unreal/dx.md "Writing a kind".
"""
from __future__ import annotations

import copy
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import errors

SPEC_VERSION = 1


class SpecError(ValueError):
    def __init__(self, problems: list):
        super().__init__("; ".join(p.message for p in problems))
        self.problems = problems


# ------------------------------------------------------------------------------------------------------------ load

def _read(path: Path):
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(text) or {}
    return json.loads(text)


_VAR = re.compile(r"\$\{(\w+)\}")


def substitute(v, vars_: dict, where: str = ""):
    """${name} in every string; a string that is exactly "${name}" takes the variable's value with its type."""
    if isinstance(v, str):
        m = _VAR.fullmatch(v)
        if m:
            if m.group(1) not in vars_:
                raise SpecError([errors.Problem("bad_spec", f"{where}: no variable {m.group(1)!r}", "define it under vars:",
                                                errors.close(m.group(1), vars_))])
            return vars_[m.group(1)]

        def rep(mm):
            if mm.group(1) not in vars_:
                raise SpecError([errors.Problem("bad_spec", f"{where}: no variable {mm.group(1)!r}",
                                                "define it under vars:", errors.close(mm.group(1), vars_))])
            return str(vars_[mm.group(1)])
        return _VAR.sub(rep, v)
    if isinstance(v, list):
        return [substitute(x, vars_, where) for x in v]
    if isinstance(v, dict):
        return {k: substitute(x, vars_, where) for k, x in v.items()}
    return v


def _coerce(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def load(paths, sets: list | None = None, registry=None) -> dict:
    """Spec files (in order) to {"vars", "resources": [{kind, name, ..., "_src": file}]}, includes resolved, variables
    substituted, every resource validated by its kind. Raises SpecError listing every problem found."""
    from . import kinds
    reg = registry or kinds.registry()
    overrides = dict(s.split("=", 1) for s in (sets or []))
    vars_: dict = {}
    resources: list = []
    problems: list = []
    seen_files: set = set()

    def take(path: Path):
        path = path.resolve()
        if path in seen_files:
            return
        seen_files.add(path)
        if not path.exists():
            problems.append(errors.Problem("bad_spec", f"no spec file {path}", "check the path (includes are relative "
                                                                                 "to the including file)"))
            return
        doc = _read(path)
        if not isinstance(doc, dict):
            problems.append(errors.Problem("bad_spec", f"{path.name}: a spec is a mapping", "see docs/unreal/dx.md"))
            return
        v = doc.get("version", SPEC_VERSION)
        if v != SPEC_VERSION:
            problems.append(errors.Problem("bad_spec", f"{path.name}: version {v}, this film-ue reads {SPEC_VERSION}", ""))
        for inc in doc.get("include", []) or []:
            take(path.parent / inc)
        vars_.update(doc.get("vars") or {})
        for k, items in doc.items():
            if k in ("version", "vars", "include", "description", "name"):
                continue
            if k == "resources":
                for it in items or []:
                    resources.append((path.name, it))
                continue
            kd = reg.by_section(k)
            if not kd:
                problems.append(errors.Problem("bad_spec", f"{path.name}: unknown section {k!r}",
                                               "film-ue plan --kinds lists the kinds and their sections",
                                               errors.close(k, reg.sections())))
                continue
            for it in (items if isinstance(items, list) else [items]):
                if not isinstance(it, dict):
                    problems.append(errors.Problem("bad_spec", f"{path.name}: {k}: each item is a mapping", ""))
                    continue
                resources.append((path.name, {"kind": kd.name, **it}))

    for p in ([paths] if isinstance(paths, (str, Path)) else paths):
        take(Path(p))
    vars_.update({k: _coerce(v) for k, v in overrides.items()})
    out = []
    names: dict = {}
    for src, it in resources:
        it = substitute(copy.deepcopy(it), vars_, src)
        kd = reg.get(it.get("kind", ""))
        if not kd:
            problems.append(errors.Problem("bad_spec", f"{src}: unknown kind {it.get('kind')!r}",
                                           "film-ue plan --kinds", errors.close(str(it.get("kind")), reg.names())))
            continue
        it = kd.normalize(it)
        key = kd.key_of(it)
        if key in (None, ""):
            problems.append(errors.Problem("bad_spec", f"{src}: a {kd.name} needs {kd.key!r}", ""))
            continue
        problems += [errors.Problem("bad_spec", f"{src}: {kd.name} {key!r}: {m}", h, c)
                     for m, h, c in kd.validate(it)]
        if (kd.name, key) in names:
            problems.append(errors.Problem("bad_spec", f"{src}: {kd.name} {key!r} is named twice "
                                                       f"(also in {names[(kd.name, key)]})", "names are unique per kind"))
        names[(kd.name, key)] = src
        it["_src"] = src
        out.append(it)
    if problems:
        raise SpecError(problems)
    return {"vars": vars_, "resources": out}


# ------------------------------------------------------------------------------------------------------------ plan

@dataclass
class Action:
    kind: str
    key: str
    action: str                 # create | update | noop | delete | apply (an op kind's re-run) | error
    changes: list = field(default_factory=list)   # [{"field", "have", "want"}]
    want: dict | None = None
    have: dict | None = None
    note: str = ""
    result: object = None
    error: dict | None = None

    def as_dict(self) -> dict:
        d = {"kind": self.kind, "key": self.key, "action": self.action}
        if self.changes:
            d["changes"] = self.changes
        if self.note:
            d["note"] = self.note
        if self.result is not None:
            d["result"] = self.result
        if self.error:
            d["error"] = self.error
        return d


def plan(spec: dict, ue, prune: bool = False, only: set | None = None, registry=None) -> list:
    from . import kinds
    reg = registry or kinds.registry()
    by_kind: dict = {}
    for it in spec["resources"]:
        if only and it["kind"] not in only:
            continue
        by_kind.setdefault(it["kind"], []).append(it)
    actions: list = []
    for kd in sorted((reg.get(k) for k in by_kind), key=lambda k: k.order):
        items = by_kind[kd.name]
        try:
            have = kd.read(ue, items)
        except Exception as e:  # a read that fails is a plan that cannot be trusted: say so per resource
            p = _problem(e, kd)
            actions += [Action(kd.name, kd.key_of(it), "error", want=it, error=p.as_dict()) for it in items]
            continue
        actions += kd.plan_all(items, have)
        if prune:
            try:
                named = {kd.key_of(it) for it in items}
                actions += [Action(kd.name, k, "delete", note="owned by the spec's kinds, no longer named")
                            for k in kd.owned(ue) if k not in named]
            except NotImplementedError:
                pass
    return actions


def _problem(e: Exception, kd=None) -> errors.Problem:
    from .sdk import OpError
    if isinstance(e, OpError):
        return e.problem
    return errors.Problem("kind_failed", f"{kd.name if kd else ''}: {type(e).__name__}: {e}",
                          "film-ue describe --live level shows what the editor has")


def execute(actions: list, ue, registry=None) -> list:
    """Apply creates/updates in plan order, then deletes in reverse kind order; each action gets result or error."""
    from . import kinds
    reg = registry or kinds.registry()
    for a in [a for a in actions if a.action in ("create", "update", "apply")]:
        try:
            a.result = reg.get(a.kind).apply(ue, a)
        except Exception as e:
            a.error = _problem(e, reg.get(a.kind)).as_dict()
    for a in sorted((a for a in actions if a.action == "delete"), key=lambda a: -reg.get(a.kind).order):
        try:
            a.result = reg.get(a.kind).delete(ue, a.key)
        except Exception as e:
            a.error = _problem(e, reg.get(a.kind)).as_dict()
    return actions


def apply(spec: dict, ue, prune: bool = False, only: set | None = None, registry=None, verify: bool = True) -> dict:
    acts = execute(plan(spec, ue, prune, only, registry), ue, registry)
    failed = [a for a in acts if a.error]
    out = {"ok": not failed, "actions": [a.as_dict() for a in acts], "summary": summarize(acts)}
    if verify:
        again = plan(spec, ue, False, only, registry)
        drift = [a.as_dict() for a in again if a.action not in ("noop", "apply")]
        out["converged"] = not drift
        if drift:
            out["drift"] = drift
            out["ok"] = False
    return out


def summarize(actions: list) -> dict:
    s: dict = {}
    for a in actions:
        s[a.action] = s.get(a.action, 0) + 1
    s["failed"] = sum(1 for a in actions if a.error)
    return s


def plan_text(actions: list) -> str:
    sym = {"create": "+", "update": "~", "delete": "-", "noop": "=", "apply": "!", "error": "?"}
    lines = []
    for a in actions:
        line = f"  {sym.get(a.action, ' ')} {a.kind:<12} {a.key}"
        if a.note:
            line += f"   ({a.note})"
        if a.error:
            line += f"   ERROR {a.error.get('code')}: {a.error.get('message')}" + (
                f"  hint: {a.error['hint']}" if a.error.get("hint") else "")
        lines.append(line)
        for c in a.changes:
            lines.append(f"        {c['field']}: {json.dumps(c.get('have'))} -> {json.dumps(c.get('want'))}")
    s = summarize(actions)
    lines.append("  " + ", ".join(f"{v} {k}" for k, v in s.items() if v))
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------------------- CLI

def main(a) -> int:
    from . import kinds
    from .sdk import Unreal
    as_json = a.json
    try:
        spec = load(a.spec, a.set)
    except SpecError as e:
        if as_json:
            print(json.dumps({"ok": False, "errors": [p.as_dict() for p in e.problems]}, indent=1))
        else:
            sys.stderr.write("\n".join(p.text() for p in e.problems) + "\n")
        return 2
    only = set(filter(None, a.only.split(","))) or None
    ue = Unreal()
    if a.cmd == "plan":
        acts = plan(spec, ue, a.prune, only)
        if as_json:
            print(json.dumps({"ok": not any(x.error for x in acts), "actions": [x.as_dict() for x in acts],
                              "summary": summarize(acts)}, indent=1, default=str))
        else:
            print(plan_text(acts))
        return 1 if any(x.error for x in acts) else 0
    if a.prune and not a.yes:
        acts = plan(spec, ue, True, only)
        dels = [x for x in acts if x.action == "delete"]
        if dels and not sys.stdin.isatty():
            sys.stderr.write(f"--prune would delete {len(dels)}: " + ", ".join(f"{x.kind} {x.key}" for x in dels) +
                             "\n  add --yes to delete them\n")
            return 2
    res = apply(spec, ue, a.prune, only)
    if as_json:
        print(json.dumps(res, indent=1, default=str))
    else:
        acts = [Action(**{k: v for k, v in d.items() if k in ("kind", "key", "action", "changes", "note", "result",
                                                                   "error")}) for d in res["actions"]]
        print(plan_text(acts))
        print("  converged" if res.get("converged") else "  NOT converged: " + json.dumps(res.get("drift"))[:600])
    return 0 if res["ok"] else 1
