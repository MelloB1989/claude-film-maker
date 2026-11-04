"""The `camera` and `shot` spec kinds (WP7): cameras and shot lists, declared; `film-ue apply` converges them through
the cam.* and shot.* ops, and a second plan is empty once the level matches.

    kind: camera                          # one cine camera by label (schemas/camera.schema.json)
    version: 1
    name: CAM_A
    frame: {subjects: [Presenter], size: MCU, angle: 3/4, side: left, focal_mm: 50}   # or loc + rot / look_at
    aperture: 2.8
    focus: {mode: track, target: eyes:Presenter}
    ---
    kind: shot                            # a shot list shot into a sequence (schemas/shot.schema.json)
    version: 1
    name: scene1
    sequence: /Game/Films/demo/Seq_Scene1
    timing: vo/timing.json                # WP12's audio timing document: a path here is read when planning
    subjects: {A: {actor: Host}, B: {actor: Guest}}
    shots: [...]

Planning is pure except for reading a `timing` file; the states come from cam.describe / cam.frame(apply=False) /
cam.point and shot.plan (which says whether the sequence already holds this exact spec).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

LOC_TOL, ROT_TOL, LENS_TOL = 0.1, 0.01, 0.01
ENVELOPE = ("kind", "version", "name", "description")


# --- shot -------------------------------------------------------------------------------------------------------

def resolved_shot(spec: dict) -> dict:
    """The spec as the bridge takes it: a `timing` path read into the document (the box cannot see client files)."""
    s = dict(spec)
    if isinstance(s.get("timing"), str):
        s["timing"] = json.loads(Path(s["timing"]).read_text())
    return s


def plan_shot(spec: dict, state: dict | None) -> list:
    """shot.apply when the sequence does not already hold this exact spec (state: shot.plan's result)."""
    state = state or {}
    if state.get("up_to_date"):
        return []
    fails = [i for i in state.get("issues", []) if i.get("severity") == "fail"]
    why = "the sequence does not hold this shot list yet" if not state.get("spec_hash") else \
        "the shot list changed since it was applied"
    if fails:
        why += f" ({len(fails)} failing check(s): {fails[0].get('code')}: {fails[0].get('message')})"
    return [{"op": "shot.apply", "args": {"spec": resolved_shot(spec)}, "why": why}]


def describe_shot(ue, spec: dict) -> dict:
    return ue.shot.plan(spec=resolved_shot(spec))


# --- camera -----------------------------------------------------------------------------------------------------

def _look(src, dst) -> dict:
    d = [b - a for a, b in zip(src, dst)]
    return {"pitch": math.degrees(math.atan2(d[2], math.hypot(d[0], d[1]))), "yaw": math.degrees(math.atan2(d[1], d[0])),
            "roll": 0.0}


def _wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def _rot_close(a: dict, b: dict) -> bool:
    return all(abs(_wrap(float(a.get(k, 0)) - float(b.get(k, 0)))) <= ROT_TOL for k in ("pitch", "yaw", "roll"))


def _close(a, b, tol) -> bool:
    return len(a) == len(b) and all(abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


def target_pose(spec: dict, state: dict) -> dict:
    """Where the spec wants the camera: {"loc", "rot", "focal_mm"} (each None when the spec leaves it)."""
    if "frame" in spec:
        t = state.get("target") or {}
        return {"loc": t.get("loc"), "rot": t.get("rot"), "focal_mm": t.get("focal")}
    loc = spec.get("loc")
    r = spec.get("rot")
    if spec.get("look_at") is not None:
        aim = state.get("look_at_point") or spec["look_at"]
        if loc is not None and isinstance(aim, (list, tuple)):
            r = _look(loc, aim)
    return {"loc": loc, "rot": r, "focal_mm": spec.get("focal_mm")}


def plan_camera(spec: dict, state: dict | None) -> list:
    """Steps to make camera `name` match: cam.add (pose, lens), cam.focus, cam.rig. state: {"camera": cam.describe's
    camera or None, "target": cam.frame(apply=False)'s plan when framed, "look_at_point"}."""
    state = state or {}
    cur = state.get("camera")
    name = spec["name"]
    want = target_pose(spec, state)
    steps = []
    add = {}
    if cur is None or (want["loc"] is not None and not _close(cur["loc"], want["loc"], LOC_TOL)):
        if want["loc"] is not None:
            add["loc"] = want["loc"]
    if want["rot"] is not None and (cur is None or not _rot_close(cur["rot"], want["rot"])):
        add["rot_"] = {k: float(want["rot"].get(k, 0.0)) for k in ("pitch", "yaw", "roll")}
    if want["focal_mm"] is not None and (cur is None or abs(cur["focal"] - want["focal_mm"]) > LENS_TOL):
        add["focal_mm"] = want["focal_mm"]
    if spec.get("aperture") is not None and (cur is None or abs(cur["aperture"] - spec["aperture"]) > LENS_TOL):
        add["aperture"] = spec["aperture"]
    if spec.get("filmback") and (cur is None or cur.get("filmback_preset") != spec["filmback"]):
        add["filmback"] = spec["filmback"]
    if spec.get("sensor_mm") and (cur is None or not _close(cur["filmback"], spec["sensor_mm"], 1e-3)):
        add["sensor_mm"] = spec["sensor_mm"]
    if spec.get("lens_preset") and cur is None:
        add["lens_preset"] = spec["lens_preset"]
    if cur is None or add:
        what = "missing" if cur is None else "differs in " + ", ".join(sorted(add))
        steps.append({"op": "cam.add", "args": {"label": name, **add}, "why": f"camera {name} {what}"})
    f = spec.get("focus")
    if f:
        mode = f.get("mode", "manual")
        have = (cur or {}).get("focus_method")
        need = cur is None or have != {"manual": "manual", "track": "tracking", "off": "disable"}[mode]
        if not need and mode == "manual" and f.get("distance_cm") is not None:
            need = abs((cur.get("focus") or 0) - f["distance_cm"]) > 0.5
        if not need and mode == "track":
            tgt = str(f.get("target", ""))
            lab = tgt[5:] if tgt.startswith("eyes:") else tgt.split(":")[0]
            need = (cur.get("focus_track") or {}).get("actor") != lab
        if need:
            steps.append({"op": "cam.focus", "args": {"label": name, **{k: v for k, v in f.items()}},
                          "why": f"camera {name}'s focus is not {mode}"})
    elif "frame" in spec and (cur is None or add):
        t = state.get("target") or {}
        if t.get("focus"):
            steps.append({"op": "cam.focus", "args": {"label": name, "mode": "manual", "distance_cm": t["focus"]},
                          "why": "focus on the framed subject's eyes"})
    rig = spec.get("rig")
    if rig:
        label = rig.get("label") or f"{name}_Rig"
        if (cur or {}).get("attached_to") != label:
            args = {"label": label, "camera": name, **{k: v for k, v in rig.items() if k != "label"}}
            steps.append({"op": "cam.rig", "args": args, "why": f"camera {name} is not on its {rig['kind']} {label}"})
    return steps


def _frame_args(spec: dict) -> dict:
    fr = dict(spec["frame"])
    out = {"camera": spec["name"], "subjects": fr.pop("subjects"), "apply": False}
    if spec.get("aperture") is not None:
        out["aperture"] = spec["aperture"]
    if spec.get("filmback"):
        out["filmback"] = spec["filmback"]
    if "distance_cm" in fr and "focal_mm" not in fr:
        fr["focal_mm"] = None
    out.update(fr)
    return out


def describe_camera(ue, spec: dict) -> dict:
    state = {"camera": None}
    try:
        state["camera"] = ue.cam.describe(label=spec["name"])["cameras"][0]
    except Exception as e:  # not_found: the camera is not made yet
        if "not_found" not in str(getattr(e, "code", "")) and "no cine camera" not in str(e):
            raise
    if "frame" in spec:
        r = ue.cam.frame(**_frame_args(spec))
        state["target"] = {**r["plan"], "focus": r["solve"].get("focus")}
    elif isinstance(spec.get("look_at"), str):
        state["look_at_point"] = ue.cam.point(target=spec["look_at"])["point"]
    return state


SPEC_KINDS = [
    {"name": "camera", "plan": plan_camera, "describe": describe_camera, "order": 50,
     "doc": "A cine camera by label: placed or framed by shot grammar, with its lens, focus and rig."},
    {"name": "shot", "plan": plan_shot, "describe": describe_shot, "order": 70,
     "doc": "A shot list shot into a sequence: cameras, moves, focus and the camera cuts."},
]


# --- a shot list, rendered and reviewed: one pipeline ------------------------------------------------------------

def _shotlist():
    """camkit.shotlist, imported from the bridge's tree by path (it is pure: no `unreal`)."""
    import sys
    root = Path(__file__).resolve().parents[3] / "unreal" / "fmbridge"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import camkit.shotlist as sl  # noqa: E402
    return sl


def shot_table(spec: dict) -> list:
    """The shots of a shot spec resolved offline (no engine): [{"id", "camera", "start", "end", "size",
    "subjects": [actor labels]}], frames on the sequence's clock. Coverage shots take their size from their name
    (Guest_OTS is an MCU); `auto` edits need the engine (shot.plan) and are not listed."""
    sl = _shotlist()
    spec = resolved_shot(spec)
    errs = sl.validate(spec)
    if errs:
        raise ValueError("; ".join(f"{e['path']}: {e['message']}" for e in errs))
    if spec.get("auto") and not spec.get("shots"):
        raise ValueError("an auto edit is resolved in the editor: run shot.plan and use its shots")
    times = sl.resolve_times(spec)
    prefix = {**sl.DEFAULTS, **(spec.get("defaults") or {})}["camera_prefix"]
    actors = {n: s.get("actor", n) for n, s in (spec.get("subjects") or {}).items()}
    out = []
    for sh, tm in zip(spec["shots"], times):
        size, who = None, []
        if "frame" in sh:
            fr = sh["frame"]
            who = [fr["subjects"]] if isinstance(fr["subjects"], str) else list(fr["subjects"])
            size = sl.framing.size_key(fr.get("size", "MCU"))
        elif "coverage" in sh:
            name = sh["coverage"]
            tail = name.rsplit("_", 1)[-1].upper()
            size = {"OTS": "MCU", "MASTER": "WS"}.get(tail) or (tail if tail in sl.framing.SIZES else None)
            if name == "master":
                size, who = "WS", list(actors)
            elif name == "two_shot":
                size, who = "MS", list(actors)[:2]
            else:
                who = [name.rsplit("_", 1)[0]] if name.rsplit("_", 1)[0] in actors else []
        out.append({"id": sh["id"], "camera": sh.get("camera") or f"{prefix}{sh['id']}", "start": tm["start"],
                    "end": tm["end"], "size": size, "subjects": [actors.get(n, n) for n in who]})
    return out


def pipeline_docs(spec: dict, out_root: str, preset: str = "draft", level: str = "", per_shot: int = 2,
                  review: bool = True, review_mode: str = "capture", outputs: list | None = None) -> list:
    """A shot list as the documents `film-ue apply` runs in order: the shot spec (kind shot, order 70: cameras, keys,
    cuts), one render (kind render, order 90: one pre-rolled chunk per camera cut, resumable), and a review per shot
    (kind qa, order 95: `per_shot` frames inside the shot, the shot's intended size as the expectation for its
    subjects). WP9 owns the render, WP10 the review; this only wires them to the shot list."""
    name = spec["name"]
    shots = shot_table(spec)
    docs = [{k: v for k, v in resolved_shot(spec).items()}]
    rnd = {"kind": "render", "version": 1, "name": f"{name}-{preset}", "sequence": spec["sequence"],
           "out_dir": f"{out_root.rstrip('/')}/{name}/{preset}", "preset": preset,
           "shots": list(dict.fromkeys(s["camera"] for s in shots)), "chunking": "shot", "preroll": "cut"}
    if level:
        rnd["level"] = level
    if outputs:
        rnd["outputs"] = outputs
    docs.append(rnd)
    if review:
        for s in shots:
            n = max(1, int(per_shot))
            span = s["end"] - s["start"]
            frames = sorted({s["start"] + min(span - 1, max(2, round(span * (k + 1) / (n + 1)))) for k in range(n)})
            rv = {"sequence": spec["sequence"], "frames": frames, "mode": review_mode,
                  "title": f"{name} {s['id']} {s['camera']} {s['size'] or ''}".strip()}
            if s["subjects"]:
                rv["subjects"] = s["subjects"]
                if s["size"]:
                    rv["expect"] = {a: {"size": [s["size"]]} for a in s["subjects"][:1]}
            if level:
                rv["level"] = level
            docs.append({"kind": "qa", "version": 1, "name": f"{name}-{s['id']}-review",
                         "out_dir": f"{out_root.rstrip('/')}/{name}/review/{s['id']}", "review": rv})
    return docs
