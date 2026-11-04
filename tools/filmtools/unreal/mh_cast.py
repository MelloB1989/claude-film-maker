"""The `cast` spec kind (WP3, B47): N distinct background characters from one seed and a few ranges. The members are
`character` specs made by the bridge's own pure generator (unreal/fmbridge/ops/mh/_cast.py, loaded from this
checkout), each planned like a `character` (mh_spec.plan), so `film-ue apply cast.yaml` makes and converges the whole
cast, and plans offline too. Example: examples/unreal/cast/cafe-extras.yaml; guide: docs/unreal/metahuman.md."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from . import mh_spec

_CAST = Path(__file__).resolve().parents[3] / "unreal" / "fmbridge" / "ops" / "mh" / "_cast.py"
_mod = None


def generator():
    """The bridge's pure cast generator (same code as mh.variants)."""
    global _mod
    if _mod is None:
        spec = importlib.util.spec_from_file_location("fmbridge_pure_mh_cast", _CAST)
        _mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_mod)
    return _mod


def members(spec: dict) -> list:
    return generator().generate(spec)["members"]


def plan(spec: dict, state: dict | None) -> list:
    """Every member's character steps. state: {asset: mh.describe result} (None: nothing exists yet)."""
    state = state or {}
    steps = []
    for m in members(spec):
        for s in mh_spec.plan(m, state.get(m["asset"]) or {"exists": False}):
            steps.append({**s, "why": f"{m['name']}: {s['why']}"})
    return steps


def describe(ue, spec: dict) -> dict:
    return {m["asset"]: ue.mh.describe(path=m["asset"]) for m in members(spec)}


SPEC_KINDS = [{"name": "cast", "plan": plan, "describe": describe, "order": 31,
               "doc": "N distinct background MetaHumans from one seed and ranges (age, sex, height, build, skin tone, "
                      "hair/beard/outfit pools): each a character spec, deterministic per seed."}]
