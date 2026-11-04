"""Scenes: a whole set of actors as one declarative spec (kind: scene; the format is in ops/_scene.py and
tools/filmtools/unreal/schemas/scene.schema.json). scene.apply converges the level on it and can be re-run safely;
scene.describe writes the current set back out as a spec (the round trip); scene.plan shows what apply would do.
"""
from __future__ import annotations

import unreal

from . import _layout as L
from . import _scene as S
from . import call, op
from ..errors import OpError
from ._util import actor_info, actors, bounds_box


def _jsonable(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, unreal.Vector):
        return [v.x, v.y, v.z]
    if isinstance(v, unreal.LinearColor):
        return [v.r, v.g, v.b, v.a]
    if isinstance(v, unreal.Object):
        return v.get_path_name().rsplit(".", 1)[0]
    return getattr(v, "name", None) or str(v)


def _materials(a) -> list:
    c = a.get_component_by_class(unreal.MeshComponent)
    if c is None:
        return []
    out = []
    for i in range(int(c.get_num_materials())):
        m = c.get_material(i)
        out.append(m.get_path_name().rsplit(".", 1)[0] if isinstance(m, unreal.Object) else None)
    return out


def _state_of(a, prop_keys=(), rest: bool = False) -> dict:
    info = actor_info(a)
    s = {k: info[k] for k in ("class", "loc", "rot", "scale", "tags", "folder", "hidden")}
    s["mesh"] = info.get("mesh", "")
    s["materials"] = _materials(a)
    s["props"] = {}
    for k in prop_keys:
        if k == "hidden":
            s["props"][k] = info["hidden"]
            continue
        try:
            s["props"][k] = _jsonable(a.get_editor_property(k))
        except Exception:  # an unknown property: the plan will try to set it and the engine will say why
            s["props"][k] = None
    if rest:
        lab = a.get_actor_label()
        supports = [bounds_box(b) for b in actors() if b.get_actor_label() != lab
                    and isinstance(b, (unreal.StaticMeshActor, unreal.SkeletalMeshActor))]
        dz = L.rest_z(bounds_box(a), supports, 0.0)
        s["rest_dz"] = round(dz, 3) if dz is not None else 0.0
    return s


def _parse(spec) -> dict:
    if isinstance(spec, str):
        import json
        try:
            spec = json.loads(spec)
        except ValueError:
            raise OpError("spec must be a mapping (or its JSON)", code="bad_args") from None
    errs = S.validate(spec)
    if errs:
        raise OpError("invalid scene spec: " + "; ".join(errs), code="bad_args",
                      hint="the format is in film-ue ops scene.apply and scene.schema.json", details={"errors": errs})
    return spec


@op("scene.state", mutates=False, idempotent=True)
def state(*, spec: dict) -> dict:
    """The level as the scene planner sees it: each actor the spec names or the scene has tagged, with class, mesh,
    loc, rot, scale, tags, folder, hidden, materials, the spec's props and how far a `drop` actor is from resting.
    film-ue plan feeds this to the same planner offline.

    Example: film-ue op scene.state spec=@office.yaml
    """
    spec = _parse(spec)
    tag = S.scene_tag(spec["name"])
    want = {a["label"]: a for a in spec["actors"]}
    out = {}
    for a in actors():
        lab = a.get_actor_label()
        if lab in want or tag in [str(t) for t in (a.get_editor_property("tags") or [])]:
            sa = want.get(lab, {})
            keys = list(sa.get("props", {})) + (["hidden"] if "hidden" in sa else [])
            out[lab] = _state_of(a, keys, rest=bool(sa.get("drop")))
    return {"actors": out}


@op("scene.plan", mutates=False, idempotent=True)
def plan(*, spec: dict) -> dict:
    """What scene.apply would do, without doing it: [{"op", "args", "why"}] (empty when the level matches).

    Example: film-ue op scene.plan spec=@office.yaml
    """
    spec = _parse(spec)
    try:
        steps = S.plan(spec, state(spec=spec))
    except S.SpecError as e:
        raise OpError(str(e), code="bad_args") from None
    return {"steps": steps, "converged": not steps}


@op("scene.apply", mutates=True, idempotent=True)
def apply(*, spec: dict, dry_run: bool = False, verify: bool = True) -> dict:
    """Converge the level on a scene spec: spawn what is missing, move/retag/refolder/re-material what differs, rest
    `drop` actors on what is under them, prune (when the spec says so) tagged actors it no longer lists. Re-running
    it changes nothing. With `verify`, plans again afterwards and reports anything still differing.

    Args: spec: the spec (a mapping, or its JSON; film-ue reads YAML). dry_run: only plan.
    Returns: {"changed", "steps": [{"op", "args", "why", "result"}], "remaining": [steps a second plan still wants]}.
    Example: film-ue apply office.yaml   (or: film-ue op scene.apply spec=@office.yaml)
    """
    spec = _parse(spec)
    steps = S.plan(spec, state(spec=spec))
    if dry_run:
        return {"changed": False, "steps": steps, "dry_run": True}
    for st in steps:
        try:
            st["result"] = call(st["op"], **st["args"])
        except OpError as e:
            raise OpError(f"scene {spec['name']}: {st['op']} for {st['why']} failed: {e.message}", code=e.code,
                          hint=e.hint, candidates=e.candidates, details={"done": steps[:steps.index(st)]}) from None
    remaining = S.plan(spec, state(spec=spec)) if verify and steps else []
    return {"changed": bool(steps), "steps": steps, "remaining": remaining}


@op("scene.describe", mutates=False, idempotent=True)
def describe(*, name: str, folder: str = "") -> dict:
    """The scene's tagged actors as a spec that scene.apply would reproduce (save it as YAML and edit it).

    Example: film-ue op scene.describe name=office
    """
    tag = S.scene_tag(name)
    st = {a.get_actor_label(): _state_of(a) for a in actors()
          if tag in [str(t) for t in (a.get_editor_property("tags") or [])]}
    return S.from_state(name, {"actors": st}, folder)


@op("scene.list", mutates=False, idempotent=True)
def list_scenes() -> dict:
    """Scenes present in the level (from their actors' fm.scene:<name> tags), with their actor counts.

    Example: film-ue op scene.list
    """
    out: dict = {}
    for a in actors():
        for t in [str(t) for t in (a.get_editor_property("tags") or [])]:
            if t.startswith("fm.scene:"):
                out[t[9:]] = out.get(t[9:], 0) + 1
    return out


@op("scene.remove", mutates=True, idempotent=True)
def remove(*, name: str) -> dict:
    """Delete every actor tagged with this scene.

    Example: film-ue op scene.remove name=office
    """
    tag = S.scene_tag(name)
    gone = []
    for a in actors():
        if tag in [str(t) for t in (a.get_editor_property("tags") or [])]:
            gone.append(a.get_actor_label())
            unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(a)
    return {"changed": bool(gone), "removed": gone}

