"""The `environment` and `lighting` spec kinds (WP5): sun/sky/fog/exposure/grade/quality, lights, rigs and practicals,
declared; `film-ue apply` converges them through the env.* and light.* ops, and a second plan is empty once the
level matches `env.describe`.

    kind: environment
    version: 1
    name: studio
    preset: interior_day
    exposure: {mode: manual, ev100: 8.5}
    rigs: {Host: {subject: Host, camera: HostCam, preset: interview, key_lux: 900}}
    moods: {night: {sun: false, exposure: {ev100: 5}, grade: {preset: moonlight}}}

The planner is the bridge's own (unreal/fmbridge/envlib/spec.py, pure Python): the same code runs in the editor
behind env.apply, so `film-ue apply` and `env.apply` always agree. docs/unreal/environment.md has every field.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ENVLIB = Path(__file__).resolve().parents[3] / "unreal" / "fmbridge" / "envlib"
SCHEMAS = Path(__file__).resolve().parent / "schemas"


def envlib():
    """unreal/fmbridge/envlib imported on its own (fmbridge itself needs the editor), as `fm_envlib`."""
    if "fm_envlib" in sys.modules:
        return sys.modules["fm_envlib"]
    spec = importlib.util.spec_from_file_location("fm_envlib", ENVLIB / "__init__.py",
                                                  submodule_search_locations=[str(ENVLIB)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fm_envlib"] = mod
    spec.loader.exec_module(mod)
    for sub in ("sun", "photometry", "lights", "rig", "grade", "quality", "stats", "spec"):
        importlib.import_module(f"fm_envlib.{sub}")
    return mod


def plan(spec: dict, state: dict | None, mood: str | None = None) -> list:
    """Steps [{"op", "args", "why"}] that converge the level (`state` = env.describe) to the spec."""
    S = envlib().spec
    try:
        return S.plan(spec, state or {}, mood)
    except S.SpecError as e:
        raise ValueError(str(e)) from None


def describe(ue, spec: dict) -> dict:
    return ue.env.describe()


def schema(kind: str = "environment") -> dict:
    return envlib().spec.json_schema(kind)


def write_schemas() -> list:
    """Regenerate schemas/environment.schema.json and lighting.schema.json from the planner's tables."""
    out = []
    for k in ("environment", "lighting"):
        p = SCHEMAS / f"{k}.schema.json"
        p.write_text(json.dumps(schema(k), indent=1) + "\n")
        out.append(str(p))
    return out


SPEC_KINDS = [
    {"name": "environment", "plan": plan, "describe": describe, "order": 40,
     "doc": "Sun/moon by time and place, physical sky, clouds, HDRI, fog, exposure, grade, Lumen quality, "
            "reflection captures, plus lights/rigs/practicals; presets and moods."},
    {"name": "lighting", "plan": plan, "describe": describe, "order": 41,
     "doc": "Lights, rigs relative to a subject and camera, practical fixtures and lighting channels."},
]

if __name__ == "__main__":
    print("\n".join(write_schemas()))
