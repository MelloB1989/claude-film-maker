"""Spec kinds: what `film-ue plan/apply` can converge. Each module in this package is imported on first use and
registers its kinds with @register, so an area adds kinds by adding a file (kinds/<area>.py), nothing else.

    from filmtools.unreal.kinds import Kind, register

    @register
    class Light(Kind):
        name, section, order = "light", "lights", 40       # spec: `lights: [...]` or {kind: light, ...}
        fields = {"name": F(str, required=True), "kind": F(str, default="rect", choices=["rect", "spot", "point"]),
                  "loc": F(list, default=[0, 0, 200]), "intensity": F(float, default=10.0)}
        compare = {"loc": 0.5, "intensity": 0.01}            # field -> tolerance (None: exact)

        def read(self, ue, items):    # {key: current state as the spec spells it, or None if absent}; ONE call
            ...
        def create(self, ue, want): ...
        def update(self, ue, want, have, changes): ...     # default: create() again (ops that converge)
        def delete(self, ue, key): ...
        def owned(self, ue): ...                             # keys this kind made (for --prune)

plan_one() diffs `compare` fields generically (numbers and number lists within tolerance, angles modulo 360 with
`angle:` tolerances, "*" for every field); override plan_all(items, have) for a kind that plans as a whole (a pure
function from spec + state to actions, testable without a box).
"""
from __future__ import annotations

import importlib
import math
import pkgutil
from dataclasses import dataclass, field

from .. import errors

_KINDS: dict = {}
_loaded = {"done": False}


@dataclass
class F:
    """A field of a kind: its type (int, float, bool, str, list, dict, or None for any), required, default, choices."""
    type: type | None = None
    required: bool = False
    default: object = None
    choices: list | None = None
    doc: str = ""
    aliases: list = field(default_factory=list)


_TYPE_OK = {int: (int,), float: (int, float), bool: (bool,), str: (str,), list: (list, tuple), dict: (dict,)}


def same(have, want, tol) -> bool:
    """want ~ have: numbers within tol, angles (tol "angle:0.1") modulo 360, lists/dicts element-wise."""
    if isinstance(tol, str) and tol.startswith("angle:"):
        t = float(tol.split(":", 1)[1])
        if isinstance(want, dict) and isinstance(have, dict):
            return all(same(have.get(k, 0.0), want.get(k, 0.0), tol) for k in set(want) | set(have))
        if isinstance(want, (int, float)) and isinstance(have, (int, float)):
            d = (float(want) - float(have) + 180.0) % 360.0 - 180.0
            return abs(d) <= t
    if isinstance(want, bool) or isinstance(have, bool):
        return isinstance(want, bool) and isinstance(have, bool) and want == have
    if isinstance(want, (int, float)) and isinstance(have, (int, float)):
        return math.isclose(float(want), float(have), abs_tol=float(tol or 0.0))
    if isinstance(want, (list, tuple)) and isinstance(have, (list, tuple)):
        return len(want) == len(have) and all(same(h, w, tol) for h, w in zip(have, want))
    if isinstance(want, dict) and isinstance(have, dict):
        return all(k in have and same(have[k], v, tol) for k, v in want.items())
    return want == have


class Kind:
    name = ""
    section = ""                  # the spec's section for this kind ("actors"); "" = only in resources:
    key = "name"
    order = 50                    # apply order: level 0, assets 10, characters 20, set 30, lights 40, cameras 50,
    fields: dict = {}             #   sequences 60, shots 70, renders 90; deletes run in reverse
    compare: dict = {}            # field -> tolerance; {"*": tol} compares every field the spec gives
    strict = True                 # unknown fields are errors (with candidates); False: passed through

    # --- spec side (pure)
    def key_of(self, it: dict):
        return it.get(self.key)

    def normalize(self, it: dict) -> dict:
        out = dict(it)
        for n, f in self.fields.items():
            for al in f.aliases:
                if al in out and n not in out:
                    out[n] = out.pop(al)
            if n not in out and f.default is not None:
                out[n] = f.default
        return out

    def validate(self, it: dict) -> list:
        """[(message, hint, candidates)]"""
        out = []
        known = set(self.fields) | {"kind", "_src", self.key}
        for k in it:
            if self.strict and k not in known:
                out.append((f"unknown field {k!r}", f"a {self.name} takes: {', '.join(sorted(self.fields))}",
                            errors.close(k, sorted(self.fields))))
        for n, f in self.fields.items():
            if f.required and it.get(n) is None:
                out.append((f"needs {n!r}", f.doc, []))
            v = it.get(n)
            if v is not None and f.type in _TYPE_OK and not (isinstance(v, _TYPE_OK[f.type]) and
                                                             not (f.type is not bool and isinstance(v, bool))):
                out.append((f"{n} should be {f.type.__name__}, not {type(v).__name__} {v!r}", f.doc, []))
            if v is not None and f.choices and v not in f.choices:
                out.append((f"{n} {v!r} is not one of {', '.join(map(str, f.choices))}", "",
                            errors.close(str(v), list(map(str, f.choices)))))
        return out

    def diff(self, want: dict, have: dict) -> list:
        fields = self.compare
        if "*" in fields:
            tol = fields["*"]
            fields = {k: tol for k in want if not k.startswith("_") and k not in ("kind", self.key)}
        out = []
        for f, tol in fields.items():
            if f not in want or want[f] is None:
                continue
            if not same(have.get(f), want[f], tol):
                out.append({"field": f, "have": have.get(f), "want": want[f]})
        return out

    def plan_one(self, want: dict, have: dict | None):
        from ..spec import Action
        key = self.key_of(want)
        if have is None:
            return Action(self.name, key, "create", want=want)
        ch = self.diff(want, have)
        return Action(self.name, key, "update" if ch else "noop", ch, want, have)

    def plan_all(self, items: list, have: dict) -> list:
        return [self.plan_one(it, have.get(self.key_of(it))) for it in items]

    # --- editor side (through the SDK: ue.<area>.<verb>(...), ue.exec(code))
    def read(self, ue, items: list) -> dict:
        raise NotImplementedError

    def apply(self, ue, action):
        if action.action == "create":
            return self.create(ue, action.want)
        if action.action == "update":
            return self.update(ue, action.want, action.have, action.changes)
        raise ValueError(action.action)

    def create(self, ue, want: dict):
        raise NotImplementedError

    def update(self, ue, want: dict, have: dict, changes: list):
        return self.create(ue, want)

    def delete(self, ue, key):
        raise NotImplementedError(f"a {self.name} cannot be deleted by a spec")

    def owned(self, ue) -> list:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"kind": self.name, "section": self.section, "key": self.key, "order": self.order,
                "doc": (self.__doc__ or "").strip(),
                "fields": {n: {"type": f.type.__name__ if f.type else "any", "required": f.required,
                               "default": f.default, "choices": f.choices, "doc": f.doc} for n, f in self.fields.items()},
                "compare": self.compare}


def register(cls):
    k = cls()
    if not k.name:
        raise ValueError(f"{cls.__name__}: a kind needs a name")
    _KINDS[k.name] = k
    return cls


class Registry:
    def __init__(self, kinds: dict):
        self.kinds = kinds

    def get(self, name: str):
        return self.kinds.get(name)

    def by_section(self, section: str):
        return next((k for k in self.kinds.values() if k.section == section), None)

    def names(self) -> list:
        return sorted(self.kinds)

    def sections(self) -> list:
        return sorted(k.section for k in self.kinds.values() if k.section)


def registry(extra: list | None = None) -> Registry:
    """Every kind in this package (each module imported once; one that fails to import is skipped with a warning)."""
    if not _loaded["done"]:
        _loaded["done"] = True
        for m in pkgutil.iter_modules(__path__):
            try:
                importlib.import_module(f"{__name__}.{m.name}")
            except Exception as e:  # one broken kind must not take the others down
                import sys
                sys.stderr.write(f"film-ue: kinds/{m.name}.py did not import: {type(e).__name__}: {e}\n")
    kinds = dict(_KINDS)
    for cls in extra or []:
        k = cls()
        kinds[k.name] = k
    return Registry(kinds)
