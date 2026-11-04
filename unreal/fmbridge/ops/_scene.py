"""The `scene` spec kind, with no engine: validate a spec, resolve relative placements, and plan the op calls that
make the level match it. Pure Python 3.11: the scene ops run it in the editor, and the client (film-ue plan/apply,
WP11) imports it directly.

A spec (YAML or JSON):

    kind: scene
    version: 1
    name: office                  # actors are tagged fm.scene:office; prune removes tagged actors not listed
    folder: Office                # default outliner folder for its actors (optional)
    prune: false
    actors:
      - label: Desk
        asset: /Game/Props/SM_Desk     # or shape: cube|sphere|cylinder|cone|plane, or class: PointLight
        loc: [0, 0, 0]                 # cm
        rot: {yaw: 90}                 # degrees, pitch/yaw/roll, missing = 0
        scale: 1                       # or [x, y, z]; shapes may give size: [x, y, z] cm instead
        material: /Game/M/MI_Oak       # slot 0
        tags: [hero]
        folder: Office/Furniture
        hidden: false
        drop: true                     # rest on what is under it after placing
        props: {cast_shadow: true}     # editor properties on the actor
      - label: Chair
        asset: /Game/Props/SM_Chair
        relative: {of: Desk, offset_cm: [80, 0, 0], face: toward}   # instead of loc; also yaw_deg with face: fixed

The state the planner diffs against is what `scene.state` returns: {"actors": {label: {"class", "mesh", "loc",
"rot", "scale", "tags", "folder", "hidden", "materials", "props", "rest_dz"}}}.
"""
from __future__ import annotations

import math

KIND, VERSION = "scene", 1
SHAPES = {"cube": "/Engine/BasicShapes/Cube", "sphere": "/Engine/BasicShapes/Sphere",
          "cylinder": "/Engine/BasicShapes/Cylinder", "cone": "/Engine/BasicShapes/Cone",
          "plane": "/Engine/BasicShapes/Plane"}
ACTOR_KEYS = {"label", "asset", "shape", "class", "loc", "rot", "scale", "size", "material", "tags", "folder",
              "hidden", "drop", "props", "relative"}
TOP_KEYS = {"kind", "version", "name", "folder", "prune", "actors", "description"}
LOC_TOL, ROT_TOL, SCALE_TOL, REST_TOL = 0.05, 0.01, 1e-4, 0.05

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "scene.schema.json",
    "title": "scene",
    "description": "A set of actors in the open level, converged by film-ue apply (scene.apply in the editor).",
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "version", "name", "actors"],
    "properties": {
        "kind": {"const": "scene"},
        "version": {"const": 1},
        "name": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+$",
                 "description": "Scene id; its actors are tagged fm.scene:<name>."},
        "description": {"type": "string"},
        "folder": {"type": "string", "description": "Default outliner folder for the scene's actors."},
        "prune": {"type": "boolean", "default": False,
                  "description": "Delete actors tagged with this scene that the spec no longer lists."},
        "actors": {"type": "array", "items": {"$ref": "#/$defs/actor"},
                   "description": "The scene's actors, placed in this order (a relative one after its `of`)."},
    },
    "$defs": {
        "vec3": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                 "description": "[x, y, z]; cm unless the property says otherwise."},
        "actor": {
            "type": "object",
            "additionalProperties": False,
            "required": ["label"],
            "properties": {
                "label": {"type": "string", "minLength": 1, "description": "Actor label, unique in the level."},
                "asset": {"type": "string", "pattern": "^/", "description": "Mesh or Blueprint package path."},
                "shape": {"enum": sorted(SHAPES), "description": "A basic shape (100 cm)."},
                "class": {"type": "string", "description": "An actor class name (PointLight, CineCameraActor)."},
                "loc": {"$ref": "#/$defs/vec3", "description": "Location [x, y, z] cm."},
                "rot": {"type": "object", "additionalProperties": False,
                        "properties": {k: {"type": "number", "description": f"{k} in degrees"}
                                       for k in ("pitch", "yaw", "roll")},
                        "description": "Rotation in degrees (missing axes are 0)."},
                "scale": {"oneOf": [{"type": "number"}, {"$ref": "#/$defs/vec3"}],
                          "description": "Uniform or [x, y, z] scale."},
                "size": {"$ref": "#/$defs/vec3", "description": "For shapes: size [x, y, z] cm (scale = size / 100)."},
                "material": {"type": "string", "pattern": "^/", "description": "Material for slot 0."},
                "tags": {"type": "array", "items": {"type": "string"},
                         "description": "Extra actor tags (fm.scene:<name> is always added)."},
                "folder": {"type": "string", "description": "Outliner folder (overrides the scene's)."},
                "hidden": {"type": "boolean", "description": "Hidden in game and renders."},
                "drop": {"type": "boolean", "description": "Rest on what is under it after placing."},
                "props": {"type": "object", "description": "Editor properties to set on the actor."},
                "relative": {
                    "type": "object", "additionalProperties": False, "required": ["of"],
                    "properties": {"offset_cm": {"$ref": "#/$defs/vec3",
                                                 "description": "[forward, right, up] cm in `of`'s yaw frame."},
                                   "face": {"enum": ["toward", "away", "same", "none", "fixed"],
                                            "description": "Which way it turns: at `of`, away, `of`'s yaw, as is, or yaw_deg."},
                                   "yaw_deg": {"type": "number", "description": "Yaw in degrees with face: fixed."},
                                   "of": {"type": "string", "description": "The actor (in this scene) it is placed from."}},
                    "description": "Place relative to another actor instead of `loc`."},
            },
        },
    },
}


class SpecError(ValueError):
    pass


def validate(spec: dict) -> list:
    """Problems with a spec, as readable strings ([] when it is valid). Checks what the schema says plus what it
    cannot: unique labels, one source per actor, relative targets that exist."""
    errs = []
    if not isinstance(spec, dict):
        return ["a scene spec is a mapping"]
    for k in sorted(set(spec) - TOP_KEYS):
        errs.append(f"unknown key {k!r} (allowed: {', '.join(sorted(TOP_KEYS))})")
    if spec.get("kind") != KIND:
        errs.append(f"kind must be {KIND!r}")
    if spec.get("version") != VERSION:
        errs.append(f"version must be {VERSION}")
    if not isinstance(spec.get("name"), str) or not spec.get("name"):
        errs.append("name is required (a string)")
    acts = spec.get("actors")
    if not isinstance(acts, list):
        return errs + ["actors must be a list"]
    labels = [a.get("label") for a in acts if isinstance(a, dict)]
    seen = set()
    for i, a in enumerate(acts):
        where = f"actors[{i}]"
        if not isinstance(a, dict):
            errs.append(f"{where} must be a mapping")
            continue
        lab = a.get("label")
        where = f"actors[{i}] ({lab})" if lab else where
        if not isinstance(lab, str) or not lab:
            errs.append(f"{where}: label is required")
        elif lab in seen:
            errs.append(f"{where}: label {lab!r} appears twice")
        seen.add(lab)
        for k in sorted(set(a) - ACTOR_KEYS):
            errs.append(f"{where}: unknown key {k!r} (allowed: {', '.join(sorted(ACTOR_KEYS))})")
        src = [k for k in ("asset", "shape", "class") if a.get(k)]
        if len(src) != 1:
            errs.append(f"{where}: give exactly one of asset, shape, class (got {src or 'none'})")
        if a.get("shape") and a["shape"] not in SHAPES:
            errs.append(f"{where}: shape must be one of {sorted(SHAPES)}")
        for k in ("loc", "size"):
            if k in a and not _vec3(a[k]):
                errs.append(f"{where}: {k} must be [x, y, z] numbers (cm)")
        if "scale" in a and not (isinstance(a["scale"], (int, float)) or _vec3(a["scale"])):
            errs.append(f"{where}: scale must be a number or [x, y, z]")
        if "rot" in a:
            r = a["rot"]
            if not isinstance(r, dict) or set(r) - {"pitch", "yaw", "roll"} or \
                    not all(isinstance(v, (int, float)) for v in r.values()):
                errs.append(f"{where}: rot must be {{pitch, yaw, roll}} in degrees (never a list)")
        if "relative" in a:
            rel = a["relative"]
            if "loc" in a:
                errs.append(f"{where}: give loc or relative, not both")
            if not isinstance(rel, dict) or rel.get("of") not in labels:
                errs.append(f"{where}: relative.of must name another actor of this scene")
            elif rel.get("of") == lab:
                errs.append(f"{where}: relative.of cannot be itself")
            elif "offset_cm" in rel and not _vec3(rel["offset_cm"]):
                errs.append(f"{where}: relative.offset_cm must be [forward, right, up] cm")
            if isinstance(rel, dict) and rel.get("face", "toward") not in ("toward", "away", "same", "none", "fixed"):
                errs.append(f"{where}: relative.face must be toward|away|same|none|fixed")
        if "tags" in a and not (isinstance(a["tags"], list) and all(isinstance(t, str) for t in a["tags"])):
            errs.append(f"{where}: tags must be a list of strings")
        if "props" in a and not isinstance(a["props"], dict):
            errs.append(f"{where}: props must be a mapping")
    return errs


def _vec3(v) -> bool:
    return isinstance(v, (list, tuple)) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v)


def scene_tag(name: str) -> str:
    return f"fm.scene:{name}"


def _rot(r: dict | None) -> dict:
    r = r or {}
    return {"pitch": float(r.get("pitch", 0)), "yaw": float(r.get("yaw", 0)), "roll": float(r.get("roll", 0))}


def _scale(a: dict) -> list | None:
    if "size" in a:
        return [v / 100.0 for v in a["size"]]
    s = a.get("scale")
    if s is None:
        return None
    return [float(s)] * 3 if isinstance(s, (int, float)) else [float(v) for v in s]


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _source(a: dict) -> tuple:
    if a.get("asset"):
        return "mesh", a["asset"].rsplit(".", 1)[0] if a["asset"].count(".") == 1 else a["asset"]
    if a.get("shape"):
        return "mesh", SHAPES[a["shape"]]
    return "class", a["class"]


def resolve(spec: dict, state: dict) -> dict:
    """Each actor's target loc and rot, with relative placements worked out from the actor they refer to (its
    target when the spec places it, else where it is now). Returns {label: {"loc", "rot"}}; loc None = keep."""
    acts = {a["label"]: a for a in spec["actors"]}
    cur = state.get("actors", {})
    out: dict = {}

    def target(lab: str, stack: tuple = ()) -> dict:
        if lab in out:
            return out[lab]
        if lab in stack:
            raise SpecError(f"relative placements loop: {' -> '.join(stack + (lab,))}")
        a = acts[lab]
        rot = _rot(a.get("rot")) if "rot" in a else (dict(cur[lab]["rot"]) if lab in cur else _rot(None))
        if "relative" in a:
            rel = a["relative"]
            ref = target(rel["of"], stack + (lab,))
            ref_loc = ref["loc"] if ref["loc"] is not None else cur.get(rel["of"], {}).get("loc", [0, 0, 0])
            f, r, u = rel.get("offset_cm", [100, 0, 0])
            yaw = math.radians(ref["rot"]["yaw"])
            loc = [ref_loc[0] + f * math.cos(yaw) - r * math.sin(yaw),
                   ref_loc[1] + f * math.sin(yaw) + r * math.cos(yaw), ref_loc[2] + u]
            face = rel.get("face", "toward")
            if face == "toward":
                rot["yaw"] = math.degrees(math.atan2(ref_loc[1] - loc[1], ref_loc[0] - loc[0]))
            elif face == "away":
                rot["yaw"] = math.degrees(math.atan2(loc[1] - ref_loc[1], loc[0] - ref_loc[0]))
            elif face == "same":
                rot["yaw"] = ref["rot"]["yaw"]
            elif face == "fixed":
                rot["yaw"] = float(rel.get("yaw_deg", 0))
            out[lab] = {"loc": [round(v, 4) for v in loc], "rot": rot}
        else:
            out[lab] = {"loc": [float(v) for v in a["loc"]] if "loc" in a else None, "rot": rot}
        return out[lab]

    for lab in acts:
        target(lab)
    return out


def plan(spec: dict, state: dict) -> list:
    """The op calls that make the level match `spec`, given `state` (scene.state): [{"op", "args", "why"}], empty
    when the level already matches. Raises SpecError for an invalid spec."""
    errs = validate(spec)
    if errs:
        raise SpecError("; ".join(errs))
    name = spec["name"]
    tag = scene_tag(name)
    cur = state.get("actors", {})
    targets = resolve(spec, state)
    steps: list = []
    to_drop: list = []
    for a in spec["actors"]:
        lab = a["label"]
        t = targets[lab]
        have = cur.get(lab)
        kind, src = _source(a)
        scale = _scale(a)
        fresh = moved_loc = False
        if have is None or (kind == "mesh" and have.get("mesh") != src) or \
                (kind == "class" and have.get("class") != src):
            why = "missing" if have is None else f"is a {have.get('class')} of {have.get('mesh') or '-'}, want {src}"
            args = {"label": lab, "loc": t["loc"] or (have or {}).get("loc", [0, 0, 0]), "rot_": t["rot"],
                    "replace": True}
            args.update({"asset": a["asset"]} if a.get("asset") else {"shape": a["shape"]} if a.get("shape")
                        else {"cls": a["class"]})
            if "size" in a and a.get("shape"):
                args["size"] = list(a["size"])
            elif scale is not None:
                args["scale"] = scale
            if a.get("material"):
                args["material"] = a["material"]
            steps.append({"op": "level.spawn", "args": args, "why": f"{lab} {why}"})
            fresh = True
            have = {"tags": [], "folder": "", "hidden": False, "materials": [a.get("material")], "props": {}}
        else:
            move: dict = {}
            if t["loc"] is not None and any(abs(x - y) > LOC_TOL for x, y in
                                            zip(t["loc"][:2] if a.get("drop") else t["loc"],
                                                have["loc"][:2] if a.get("drop") else have["loc"])):
                move["loc"] = t["loc"] if not a.get("drop") else [t["loc"][0], t["loc"][1], have["loc"][2]]
            if "rot" in a or "relative" in a:
                if any(_angle_diff(t["rot"][k], have["rot"].get(k, 0)) > ROT_TOL for k in ("pitch", "yaw", "roll")):
                    move["rot_"] = t["rot"]
            if scale is not None and any(abs(x - y) > SCALE_TOL for x, y in zip(scale, have.get("scale", [1, 1, 1]))):
                move["scale"] = scale
            moved_loc = "loc" in move
            if move:
                steps.append({"op": "level.move", "args": {"label": lab, **move},
                              "why": f"{lab}: {', '.join(k.rstrip('_') for k in move)} differ"})
            if a.get("material") and (have.get("materials") or [None])[0] != a["material"]:
                steps.append({"op": "level.material", "args": {"label": lab, "material": a["material"], "slot": 0},
                              "why": f"{lab}: material differs"})
        want_tags = [tag] + [x for x in a.get("tags", []) if x != tag]
        missing = [x for x in want_tags if x not in have.get("tags", [])]
        if missing:
            steps.append({"op": "level.tag", "args": {"labels": [lab], "add": missing},
                          "why": f"{lab}: tags {missing} missing"})
        folder = a.get("folder", spec.get("folder"))
        if folder is not None and have.get("folder", "") != folder:
            steps.append({"op": "level.folder", "args": {"labels": [lab], "path": folder},
                          "why": f"{lab}: folder {have.get('folder', '')!r} -> {folder!r}"})
        props = dict(a.get("props", {}))
        if "hidden" in a:
            props["hidden"] = bool(a["hidden"])
        diff = {k: v for k, v in props.items() if have.get("props", {}).get(k, object()) != v}
        if diff:
            steps.append({"op": "level.set", "args": {"label": lab, "props": diff},
                          "why": f"{lab}: {', '.join(sorted(diff))} differ"})
        if a.get("drop") and (fresh or moved_loc or abs(have.get("rest_dz", 0.0)) > REST_TOL):
            to_drop.append(lab)
    if to_drop:
        steps.append({"op": "layout.drop", "args": {"labels": to_drop}, "why": "rest on what is under them"})
    if spec.get("prune"):
        listed = {a["label"] for a in spec["actors"]}
        extra = sorted(lab for lab, s in cur.items() if tag in s.get("tags", []) and lab not in listed)
        if extra:
            steps.append({"op": "level.delete", "args": {"labels": extra}, "why": f"prune: not in scene {name}"})
    return steps


def from_state(name: str, state: dict, folder: str = "") -> dict:
    """A spec that reproduces the scene's tagged actors as they are now (scene.describe): the round trip."""
    tag = scene_tag(name)
    acts = []
    for lab, s in sorted(state.get("actors", {}).items()):
        if tag not in s.get("tags", []):
            continue
        a: dict = {"label": lab}
        if s.get("mesh"):
            shape = next((k for k, v in SHAPES.items() if v == s["mesh"]), None)
            a.update({"shape": shape} if shape else {"asset": s["mesh"]})
        else:
            a["class"] = s["class"]
        a["loc"] = [round(v, 2) for v in s["loc"]]
        r = {k: round(v, 3) for k, v in s["rot"].items() if abs(v) > 1e-6}
        if r:
            a["rot"] = r
        sc = s.get("scale", [1, 1, 1])
        if any(abs(v - 1) > SCALE_TOL for v in sc):
            a["scale"] = sc[0] if max(sc) - min(sc) < SCALE_TOL else sc
        mats = s.get("materials") or []
        if mats and mats[0]:
            a["material"] = mats[0]
        extra = [t for t in s.get("tags", []) if t != tag]
        if extra:
            a["tags"] = extra
        if s.get("folder") and s["folder"] != folder:
            a["folder"] = s["folder"]
        if s.get("hidden"):
            a["hidden"] = True
        acts.append(a)
    spec = {"kind": KIND, "version": VERSION, "name": name}
    if folder:
        spec["folder"] = folder
    spec["actors"] = acts
    return spec
