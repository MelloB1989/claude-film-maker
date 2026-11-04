"""The `foliage` spec kind (B39): a seeded scatter, declared; `film-ue apply` converges it through foliage.scatter,
and a second plan is empty once the level holds exactly this scatter (same arguments, same seed).

    kind: foliage
    version: 1
    name: Lawn                          # the scatter's prefix (its foliage types live in /Game/_Foliage/Lawn/)
    seed: 7
    region: {rect: [[-1500, -1500], [1500, 1500]]}
    meshes:
      - {mesh: /Game/Env/SM_Grass, weight: 4, scale: [0.8, 1.3], tilt_deg: 6}
      - {mesh: /Game/Env/SM_Pebble, weight: 1, scale: [0.5, 1.0], z_offset_cm: -2}
    density_per_m2: 6
    exclude_actors: [Table]
    patchiness: 0.4

The state is foliage.scatter's dry run (would it change anything?); planning is pure.
"""
from __future__ import annotations

ENVELOPE = ("kind", "version", "name", "description")


def scatter_args(spec: dict) -> dict:
    """The spec as foliage.scatter's arguments."""
    a = {k: v for k, v in spec.items() if k not in ENVELOPE}
    a["prefix"] = spec["name"]
    return a


def plan(spec: dict, state: dict | None) -> list:
    """foliage.scatter when a run would change something (state: its dry run), else nothing."""
    state = state or {}
    if state.get("changed") is False:
        return []
    why = "the scatter is not in the level yet" if not state.get("stored_hash") else \
        "the scatter's arguments changed since it was placed"
    if state.get("planned") is not None:
        why += f" ({state['planned']} instances planned)"
    return [{"op": "foliage.scatter", "args": scatter_args(spec), "why": why}]


def describe(ue, spec: dict) -> dict:
    return ue.foliage.scatter(**scatter_args(spec), dry_run=True)


SPEC_KINDS = [{"name": "foliage", "plan": plan, "describe": describe, "order": 35,
               "doc": "A seeded scatter of meshes as foliage instances (grass, rocks, trees) on the ground."}]
