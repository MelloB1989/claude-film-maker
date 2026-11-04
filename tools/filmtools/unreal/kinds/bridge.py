"""Kinds whose planner runs on the bridge (the area's `<area>.plan` op answers the steps against the live level), wired
into film-ue plan/apply so one command handles every kind: `scene` (WP6: scene.plan -> its steps, run one by one and
re-planned) and `shot` (WP7: shot.plan says whether the sequence already holds this spec; else one shot.apply).

An area adds one with bridge_kind(name, plan_op=..., order=..., steps=...) here, or registers its own pure planner
(docs/unreal/dx.md §4), which is better: it plans offline too."""
from __future__ import annotations

from ..spec import register_kind


def bridge_kind(name: str, plan_op: str, order: int, steps, doc: str, key: str = "name"):
    """steps(spec, plan_result) -> [{"op", "args", "why"}]: pure, from what the bridge's plan op answered."""
    def describe(ue, spec):
        return ue.call(plan_op, spec={k: v for k, v in spec.items() if not k.startswith("_")})

    def plan(spec, state):
        if state is None:
            return [{"op": plan_op, "args": {"spec": spec}, "why": "no state: plan on the bridge", "always": True}]
        return steps(spec, state)
    plan.__module__ = __name__
    return register_kind(name, plan, describe, order=order, key=key, doc=doc)


def _scene_steps(spec, state):
    return [{"op": s["op"], "args": s.get("args") or {}, "why": s.get("why", "")} for s in state.get("steps") or []]


def _shot_steps(spec, state):
    if state.get("up_to_date"):
        return []
    issues = [i.get("code", "") for i in state.get("issues") or [] if i.get("severity") == "fail"]
    return [{"op": "shot.apply", "args": {"spec": spec}, "timeout": 1800,
             "why": "the sequence does not hold this shot list" + (f" (plan issues: {', '.join(issues)})" if issues else "")}]


bridge_kind("scene", "scene.plan", 30, _scene_steps,
            "A set of actors as one spec (WP6, ops/_scene.py): planned on the bridge by scene.plan, step by step.")
bridge_kind("shot", "shot.plan", 70, _shot_steps,
            "A shot list (WP7, camkit.shotlist): cameras, keys and cuts into a sequence; shot.apply when it changed.",
            key="sequence")
