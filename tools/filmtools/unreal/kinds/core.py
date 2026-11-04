"""Generic kinds: `level` (the level to work in: opened, or created), `actor` (any actor by label: a basic shape, an
asset or a class, at a transform; until WP6's layout kinds replace it) and `op` (one op call, re-run on every apply:
the escape hatch for what has no kind yet)."""
from __future__ import annotations

import json
import math

from ..spec import register_kind
from . import changed

READ_ACTORS = '''
import unreal
want = set(LABELS)
result = {}
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    lab = a.get_actor_label()
    if lab in want:
        p, r, s = a.get_actor_location(), a.get_actor_rotation(), a.get_actor_scale3d()
        result[lab] = {"cls": a.get_class().get_name(), "loc": [p.x, p.y, p.z],
                       "rot": {"pitch": r.pitch, "yaw": r.yaw, "roll": r.roll}, "scale": [s.x, s.y, s.z],
                       "tags": [str(t) for t in a.tags]}
'''

READ_LEVEL = '''
import unreal
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
result = {"current": w.get_path_name().split(".")[0] if w else "",
          "exists": unreal.EditorAssetLibrary.does_asset_exist(PATH)}
'''


def code(src: str, **names) -> str:
    """A snippet with its inputs bound as JSON literals (never formatted into the code)."""
    return "import json\n" + "".join(f"{k} = json.loads({json.dumps(json.dumps(v))})\n" for k, v in names.items()) + src


def look_at_rot(src, target) -> dict:
    """What FindLookAtRotation gives: yaw and pitch toward target, no roll."""
    dx, dy, dz = (float(t) - float(s) for s, t in zip(src, target))
    return {"pitch": math.degrees(math.atan2(dz, math.hypot(dx, dy))), "yaw": math.degrees(math.atan2(dy, dx)),
            "roll": 0.0}


# ---------------------------------------------------------------------------------------------------------- level

def plan_level(spec: dict, state: dict | None) -> list:
    state = state or {}
    if state.get("current") == spec["path"]:
        return []
    if state.get("exists"):
        return [{"op": "level.open", "args": {"path": spec["path"]}, "why": f"the open level is {state.get('current')!r}"}]
    if not spec.get("create", True):
        raise ValueError(f"level {spec['path']} does not exist and create is false")
    return [{"op": "level.new", "args": {"path": spec["path"]}, "why": "it does not exist"}]


def describe_level(ue, spec: dict) -> dict:
    return ue.exec(code(READ_LEVEL, PATH=spec["path"]))


register_kind("level", plan_level, describe_level, order=0, key="path",
              doc="The level to work in: opened when it exists, else created empty (level.new).")


# ---------------------------------------------------------------------------------------------------------- actor

TOL = {"loc": 0.5, "rot": "angle:0.05", "scale": 1e-3}


def want_actor(spec: dict) -> dict:
    """The spec's transform as the editor reports it: look_at to a rotation, size (cm) to a scale."""
    w = {"loc": [float(v) for v in spec.get("loc", [0, 0, 0])]}
    if spec.get("look_at") is not None:
        w["rot"] = look_at_rot(w["loc"], spec["look_at"])
    elif spec.get("rot") is not None:
        w["rot"] = {k: float(spec["rot"].get(k, 0.0)) for k in ("pitch", "yaw", "roll")}
    if spec.get("size") is not None:
        w["scale"] = [float(v) / 100.0 for v in spec["size"]]
    elif spec.get("scale") is not None:
        s = spec["scale"]
        w["scale"] = [float(s)] * 3 if isinstance(s, (int, float)) else [float(v) for v in s]
    return w


def plan_actor(spec: dict, state: dict | None) -> list:
    w = want_actor(spec)
    label = spec["name"]
    spawn = {"label": label, "replace": True, "loc": w["loc"],
             **{k: spec[k] for k in ("shape", "asset", "cls", "material") if spec.get(k)}}
    if "rot" in w:
        spawn["rot_"] = w["rot"]
    if "scale" in w:
        spawn["scale"] = w["scale"]
    if state is None:
        return [{"op": "level.spawn", "args": spawn, "why": "no actor with this label"}]
    if spec.get("cls") and state.get("cls") != spec["cls"]:
        return [{"op": "level.spawn", "args": spawn, "why": f"class {state.get('cls')} -> {spec['cls']}: respawn"}]
    diff = changed(w, state, TOL)
    if not diff:
        return []
    args = {"label": label, **{("rot_" if k == "rot" else k): v for k, v in diff.items()}}
    return [{"op": "level.move", "args": args, "why": "moved: " + ", ".join(diff)}]


def describe_actors(ue, specs: list) -> dict:
    return ue.exec(code(READ_ACTORS, LABELS=[s["name"] for s in specs])) or {}


register_kind("actor", plan_actor, describe_many=describe_actors, order=30,
              doc="Any actor by label (shape, asset or class) at a transform: spawned, moved back, or respawned.")


# ------------------------------------------------------------------------------------------------------------- op

def _truthy(v, path: str = ""):
    """The value at a dotted path ("result.path", "0") is truthy: a non-empty list/dict/str, True, a non-zero number."""
    for part in filter(None, path.split(".")):
        if isinstance(v, list) and part.isdigit():
            v = v[int(part)] if int(part) < len(v) else None
        elif isinstance(v, dict):
            v = v.get(part)
        else:
            return False
    return bool(v)


def plan_op(spec: dict, state) -> list:
    """With `unless` ({op, args, has}): no step when that read op's answer (at the dotted path `has`) is truthy, so
    the step converges like any kind; without it the step runs on every apply ("always")."""
    step = {"op": spec["op"], "args": spec.get("args") or {}, "why": spec.get("why", "an op step"),
            **({"timeout": spec["timeout"]} if spec.get("timeout") else {})}
    if spec.get("unless"):
        if state is not None and state.get("done"):
            return []
        step["why"] = spec.get("why") or f"{spec['unless']['op']} says it is not there yet"
        return [step]
    return [{**step, "always": True, "why": spec.get("why", "an op step: runs every apply")}]


def describe_op(ue, spec: dict):
    u = spec.get("unless")
    if not u:
        return None
    try:
        r = ue.call(u["op"], **(u.get("args") or {}))
    except Exception as e:  # a read that fails (the thing is absent) means: not done
        return {"done": False, "error": str(e)[:300]}
    return {"done": _truthy(r, u.get("has", "")), "answer": r if len(str(r)) < 2000 else str(r)[:2000]}


register_kind("op", plan_op, describe_op, order=80,
              doc="One op call: run on every apply, or, with `unless` (a read op), only until that says it is done.")
