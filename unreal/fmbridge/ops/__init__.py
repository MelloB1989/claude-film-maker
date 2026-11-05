"""The bridge's operations: named functions the operator's machine calls through POST /op (fmbridge.server), each a
plain Python function over the `unreal` API, registered with @op("area.verb"). `ops.call("list")` returns them all
with their docstrings; `ops.call("ops.schema")` returns every op's signature as JSON (docs/unreal/CONVENTIONS.md).

Every module in this package (and every subpackage) is imported at start: adding `ops/<area>.py` registers its ops,
nobody edits a list. A module that fails to import does not take the others down: it is reported by `list`,
`ops.schema` and `ops.broken` with its error.

Conventions every op follows: locations are [x, y, z] in cm (Z up, X forward); rotations are {"pitch", "yaw", "roll"}
in degrees (never positional: unreal.Rotator's positional order is roll, pitch, yaw); colours are [r, g, b] linear
0-1; assets are addressed by package path ("/Game/Studio/Materials/MI_Wall"); actors by their label.
"""
from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import time
import traceback

_OPS: dict = {}
_META: dict = {}
_BROKEN: dict = {}
_AFTER: list = []  # hooks run after every successful call: fn(op_name, args, result, seconds, meta)


def after_call(fn):
    """Register a hook run after every op that returns (a generator result is passed as-is: never consume it)."""
    _AFTER.append(fn)
    return fn


def op(name: str, *, mutates: bool | None = None, idempotent: bool | None = None, tags: list | tuple = ()):
    """Register an op. `mutates`: it changes the level, assets or files (False for describe/find/measure ops);
    `idempotent`: running it twice with the same args leaves the same state as once; `tags`: free words for
    discovery ("slow", "gpu", "windows-only", "experimental")."""
    def wrap(fn):
        if name in _OPS and _OPS[name].__module__ != fn.__module__:
            raise ValueError(f"op {name!r} is registered twice ({_OPS[name].__module__} and {fn.__module__})")
        _OPS[name] = fn
        _META[name] = {"mutates": mutates, "idempotent": idempotent, "tags": list(tags)}
        return fn
    return wrap


def call(op_name: str, /, **args):
    if op_name not in _OPS:
        from ..errors import OpError, closest
        raise OpError(f"no op {op_name!r}", code="not_found", candidates=closest(op_name, _OPS),
                      hint="film-ue ops <prefix> lists them" + (f"; {op_name.split('.')[0]} failed to import: "
                                                               f"see ops.broken" if _broken_area(op_name) else ""))
    fn = _OPS[op_name]
    try:
        inspect.signature(fn).bind(**args)
    except TypeError as e:
        from ..errors import OpError
        raise OpError(f"{op_name}: {e}", code="bad_args", hint=f"film-ue ops {op_name} shows what it takes") from None
    t0 = time.time()
    res = fn(**args)
    for h in _AFTER:
        try:
            h(op_name, args, res, time.time() - t0, _META.get(op_name, {}))
        except Exception:
            pass
    return res


def _broken_area(op_name: str) -> bool:
    area = op_name.split(".")[0]
    return any(m.rsplit(".", 1)[-1].startswith(area) for m in _BROKEN)


def _json_default(v):
    if v is inspect.Parameter.empty:
        return None
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (list, tuple)):
        return [_json_default(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _json_default(x) for k, x in v.items()}
    return repr(v)


def _ann(a) -> str | None:
    if a is inspect.Parameter.empty or a is inspect.Signature.empty:
        return None
    return a if isinstance(a, str) else getattr(a, "__name__", str(a))


def describe(name: str) -> dict:
    """One op as JSON: the shape `ops.schema` returns and tools/filmtools/unreal/schema.py produces offline."""
    fn = _OPS[name]
    sig = inspect.signature(fn)
    doc = inspect.getdoc(fn) or ""
    try:
        file, line = inspect.getsourcefile(fn) or "", inspect.getsourcelines(fn)[1]
    except (OSError, TypeError):
        file, line = "", 0
    if "fmbridge" in file:
        file = "unreal/fmbridge/" + file.replace("\\", "/").split("/fmbridge/", 1)[-1]
    params = [{"name": p.name,
               "kind": "keyword" if p.kind == p.KEYWORD_ONLY else "positional",
               "type": _ann(p.annotation),
               "required": p.default is p.empty,
               "default": _json_default(p.default)}
              for p in sig.parameters.values() if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
    area, _, verb = name.partition(".")
    return {"name": name, "area": area if verb else "", "verb": verb or name, "module": fn.__module__,
            "file": file, "line": line, "summary": (doc.splitlines() or [""])[0], "doc": doc, "params": params,
            "returns": _ann(sig.return_annotation), "multi_tick": inspect.isgeneratorfunction(fn), **_META[name]}


@op("list", mutates=False, idempotent=True)
def list_ops(prefix: str = "", full: bool = False) -> dict:
    """Every op with its signature and the first line of its docstring; the whole docstring with `full`, or when the
    prefix names one op (`film-ue ops seq.key_float`)."""
    found = {n: f for n, f in sorted(_OPS.items()) if n.startswith(prefix)}
    full = full or len(found) == 1
    out = {n: f"{n}{inspect.signature(f)}: " + ((inspect.getdoc(f) or "") if full or n == prefix else
                                                 ((inspect.getdoc(f) or "").splitlines() or [""])[0])
           for n, f in found.items()}
    if _BROKEN:
        out["!broken"] = {m: e.strip().splitlines()[-1] for m, e in _BROKEN.items()}
    return out


@op("ops.schema", mutates=False, idempotent=True)
def schema(prefix: str = "") -> dict:
    """Every op's signature, docstring and flags as JSON, for generating a CLI or SDK and for discovery:
    {"version": 1, "ops": [{"name", "area", "verb", "params": [{"name", "type", "required", "default"}], ...}],
    "broken": {module: error}}. Example: film-ue op ops.schema prefix=seq."""
    return {"version": 1, "ops": [describe(n) for n in sorted(_OPS) if n.startswith(prefix)],
            "broken": {m: e.strip().splitlines()[-1] for m, e in _BROKEN.items()}}


@op("ops.broken", mutates=False, idempotent=True)
def broken() -> dict:
    """The op modules that failed to import, with their full tracebacks ({} when all loaded)."""
    return dict(_BROKEN)


def _discover() -> None:
    """Import every module under this package, each on its own: one that raises is recorded, the rest still load.
    Modules whose name starts with '_' are helpers and are imported only by the modules that need them."""
    here = os.path.dirname(__file__)
    for info in sorted(pkgutil.walk_packages([here], prefix=__name__ + ".",
                                                onerror=lambda n: _BROKEN.setdefault(n, traceback.format_exc())), key=lambda i: i.name):
        if any(part.startswith("_") for part in info.name.split(".")[2:]):
            continue
        try:
            importlib.import_module(info.name)
        except Exception:
            _BROKEN[info.name] = traceback.format_exc()


_discover()
