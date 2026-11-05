"""The `sequence` spec kind on the client (WP8): validate a spec offline, plan it against a described sequence, and
load the editor-side pure modules (unreal/fmbridge/ops/seqcore/_*.py) without an engine.

    from filmtools.unreal import seq_spec
    seq_spec.validate(spec)                 # {"ok", "problems", "notes", "tracks"}: offline, no editor
    state = client.op("seq.describe", path=spec["sequence"], spec=spec)["result"]
    seq_spec.plan(spec, state)              # [{"op", "args", "why"}]; [] = converged

The spec kind's schema is schemas/sequence.schema.json; the reference is docs/unreal/sequencer.md.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

KIND = "sequence"
CORE_DIR = Path(__file__).resolve().parents[3] / "unreal" / "fmbridge" / "ops" / "seqcore"
_PKG = "fmseqcore"


def core():
    """The pure seqcore modules as one namespace (time, curves, model, spec, plan), loaded from the repo's
    unreal/fmbridge/ops/seqcore/ as a standalone package (no `unreal`, no fmbridge import)."""
    if _PKG in sys.modules and hasattr(sys.modules[_PKG], "plan"):
        return sys.modules[_PKG]
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(CORE_DIR)]
    sys.modules[_PKG] = pkg
    for name in ("_time", "_curves", "_model", "_spec", "_plan"):
        spec = importlib.util.spec_from_file_location(f"{_PKG}.{name}", CORE_DIR / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{_PKG}.{name}"] = mod
        spec.loader.exec_module(mod)
        setattr(pkg, name.lstrip("_"), mod)
    return pkg


def validate(spec: dict) -> dict:
    """Check a spec without the editor: {"ok", "problems", "notes", "tracks"}."""
    return core().spec.validate(spec)


def compile(spec: dict, resolver=None) -> tuple:  # noqa: A001 (the spec's verb)
    """(canonical document, notes); raises core().spec.SpecError."""
    return core().spec.compile_spec(spec, resolver)


def plan(spec: dict, state: dict | None) -> list:
    """The steps that converge the editor to `spec`. `state` is seq.describe's result: called with `spec=` it
    carries "want" (the spec resolved in the editor: look-at targets, animation lengths, property owners), which is
    planned exactly; without it the spec is compiled offline (guesses noted). `state` None or {"exists": False}:
    the sequence is made first."""
    c = core()
    want = (state or {}).get("want")
    if want is None:
        want, _ = c.spec.compile_spec(spec)
    have = state if state and state.get("exists", True) and "tracks" in state else None
    return c.plan.plan(want, have)


def chunks(state: dict, **kw) -> dict:
    """Render chunks that respect cloth pre-roll, from a described sequence (see seq.chunks)."""
    return core().plan.chunks(state, **kw)


def load(path: str) -> list:
    """The spec documents in a YAML or JSON file (YAML may hold several, separated by ---)."""
    text = Path(path).read_text()
    if path.endswith(".json"):
        import json
        d = json.loads(text)
        return d if isinstance(d, list) else [d]
    import yaml
    return [d for d in yaml.safe_load_all(text) if d]


def describe(ue, spec: dict) -> dict | None:
    """The kind's reader for WP11's engine: seq.describe with the spec (so "want" is resolved in the editor);
    None when the sequence does not exist."""
    state = ue.call("seq.describe", path=spec["sequence"], spec=_wire(spec))
    return state if state.get("exists", True) else None


def _plan_kind(spec: dict, state: dict | None) -> list:
    return plan(_wire(spec), state)


def _wire(spec: dict) -> dict:
    """The spec as the bridge takes it (the engine's envelope keys are allowed by the compiler too)."""
    return {k: v for k, v in spec.items() if k not in ("$schema",)}


SPEC_KINDS = [{"name": KIND, "plan": _plan_kind, "describe": describe, "order": 60,
               "doc": "A level sequence: bindings and their tracks (transform, visibility, animation, properties, "
                      "materials), camera cuts, audio, fade, shots, markers; batched, idempotent (docs/unreal/"
                      "sequencer.md)."}]
