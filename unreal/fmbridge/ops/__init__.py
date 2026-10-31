"""The bridge's operations: named functions the operator's machine calls through POST /op (fmbridge.server), each a
plain Python function over the `unreal` API, registered with @op("module.name"). `ops.call("list")` returns them all
with their docstrings. Add a module here and import it at the bottom to register its ops.

Conventions every op follows: locations are [x, y, z] in cm (Z up, X forward); rotations are {"pitch", "yaw", "roll"}
in degrees (never positional: unreal.Rotator's positional order is roll, pitch, yaw); colours are [r, g, b] linear
0-1; assets are addressed by package path ("/Game/Studio/Materials/MI_Wall"); actors by their label.
"""
from __future__ import annotations

import inspect

_OPS: dict = {}


def op(name: str):
    def wrap(fn):
        _OPS[name] = fn
        return fn
    return wrap


def call(op_name: str, /, **args):
    if op_name not in _OPS:
        raise KeyError(f"no op {op_name!r} (ops.call('list') shows them)")
    return _OPS[op_name](**args)


@op("list")
def list_ops(prefix: str = "") -> dict:
    """Every op with its signature and the first line of its docstring."""
    return {n: f"{n}{inspect.signature(f)}: {(inspect.getdoc(f) or '').splitlines()[0] if inspect.getdoc(f) else ''}"
            for n, f in sorted(_OPS.items()) if n.startswith(prefix)}


from . import assets, level, look, mh, speech, anim, seq, render  # noqa: E402,F401  (register)
