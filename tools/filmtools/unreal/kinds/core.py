"""The built-in kinds: level (open or create it), actor (any actor by label: shape, asset or class, transform), sequence
(a level sequence's range and rate) and op (any op, re-run on every apply: the escape hatch for what has no kind yet).
Areas add richer kinds (characters, lights, cameras, shots, renders) as their own modules in this package."""
from __future__ import annotations

import json
import math

from . import F, Kind, register

TAG = "fm.spec"  # actors a spec made carry this tag: --prune deletes only those

READ_ACTORS = '''
import unreal
want = set(LABELS)
result = {}
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    lab = a.get_actor_label()
    if lab in want or (OWNED and TAG in [str(t) for t in a.tags]):
        p, r, s = a.get_actor_location(), a.get_actor_rotation(), a.get_actor_scale3d()
        result[lab] = {"cls": a.get_class().get_name(), "loc": [p.x, p.y, p.z],
                       "rot": {"pitch": r.pitch, "yaw": r.yaw, "roll": r.roll}, "scale": [s.x, s.y, s.z],
                       "tags": [str(t) for t in a.tags]}
'''

TAG_ACTOR = '''
import unreal
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    if a.get_actor_label() == LABEL:
        tags = list(a.tags)
        if TAG not in [str(t) for t in tags]:
            a.tags = tags + [unreal.Name(TAG)]
result = True
'''

READ_LEVEL = '''
import unreal
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
result = {"current": w.get_path_name().split(".")[0] if w else "",
          "exists": unreal.EditorAssetLibrary.does_asset_exist(PATH)}
'''

READ_SEQS = '''
import unreal
result = {}
for p in PATHS:
    if not unreal.EditorAssetLibrary.does_asset_exist(p):
        continue
    s = unreal.EditorAssetLibrary.load_asset(p)
    if not isinstance(s, unreal.LevelSequence):
        result[p] = {"cls": s.get_class().get_name()}
        continue
    r = s.get_display_rate()
    result[p] = {"cls": "LevelSequence", "start": s.get_playback_start(), "end": s.get_playback_end(),
                 "fps": r.numerator / r.denominator}
'''


def code(src: str, **names) -> str:
    """A snippet with its inputs bound as JSON literals (never string-formatted into the code)."""
    return "import json\n" + "".join(f"{k} = json.loads({json.dumps(json.dumps(v))})\n" for k, v in names.items()) + src


def look_at_rot(src, target) -> dict:
    """What FindLookAtRotation gives: yaw and pitch toward target, no roll."""
    dx, dy, dz = (float(t) - float(s) for s, t in zip(src, target))
    return {"pitch": math.degrees(math.atan2(dz, math.hypot(dx, dy))), "yaw": math.degrees(math.atan2(dy, dx)),
            "roll": 0.0}


SHAPES = ("cube", "sphere", "cylinder", "cone", "plane")


@register
class Level(Kind):
    """The level everything else goes into: opened when it exists, else created (empty) and opened."""
    name, section, key, order = "level", "level", "path", 0
    fields = {"path": F(str, required=True, doc="/Game/... content path of the level"),
              "create": F(bool, default=True, doc="create it when it does not exist")}

    def read(self, ue, items):
        out = {}
        for it in items:
            r = ue.exec(code(READ_LEVEL, PATH=it["path"]))
            out[it["path"]] = {"path": r["current"], "exists": r["exists"]} if r["current"] == it["path"] else None
            if out[it["path"]] is None:
                it["_exists"] = r["exists"]
        return out

    def plan_one(self, want, have):
        a = super().plan_one(want, have)
        if a.action == "create":
            a.note = "open it" if want.get("_exists") else ("create it" if want.get("create") else "MISSING (create: false)")
        return a

    def create(self, ue, want):
        if want.get("_exists"):
            return ue.level.open(path=want["path"])
        if not want.get("create"):
            raise ValueError(f"level {want['path']} does not exist and create is false")
        return ue.level.new(path=want["path"])


@register
class Actor(Kind):
    """Any actor, by label: a basic shape (size in cm), an asset (mesh, Blueprint) or a class, at a transform.
    A changed shape/asset/class respawns it; a changed transform moves it. Tagged fm.spec (for --prune)."""
    name, section, order = "actor", "actors", 30
    fields = {"name": F(str, required=True, doc="the actor label"),
              "shape": F(str, choices=list(SHAPES)), "asset": F(str, doc="/Game/... mesh or Blueprint"),
              "cls": F(str, doc="a class name: RectLight, CineCameraActor, ...", aliases=["class"]),
              "loc": F(list, default=[0, 0, 0], doc="[x, y, z] cm"),
              "rot": F(dict, doc='{"pitch", "yaw", "roll"} degrees'),
              "look_at": F(list, doc="[x, y, z]: aim it there (instead of rot)"),
              "size": F(list, doc="[x, y, z] cm, basic shapes (100 cm at scale 1)"),
              "scale": F(None, doc="a number or [x, y, z]"),
              "material": F(str, doc="a material for its static meshes")}
    compare = {"loc": 0.5, "rot": "angle:0.05", "scale": 1e-3}

    def normalize(self, it):
        it = super().normalize(it)
        if it.get("look_at") is not None:
            it["rot"] = look_at_rot(it["loc"], it["look_at"])
        if it.get("size") is not None:
            it["scale"] = [float(v) / 100.0 for v in it["size"]]
        elif isinstance(it.get("scale"), (int, float)):
            it["scale"] = [float(it["scale"])] * 3
        if it.get("rot") is not None:
            it["rot"] = {k: float(it["rot"].get(k, 0.0)) for k in ("pitch", "yaw", "roll")}
        return it

    def validate(self, it):
        out = super().validate(it)
        if sum(1 for k in ("shape", "asset", "cls") if it.get(k)) != 1:
            out.append(("give exactly one of shape, asset, cls", "shape: cube | asset: /Game/... | cls: RectLight", []))
        return out

    def _cls(self, want):
        return want["cls"] if want.get("cls") else None  # shapes and meshes spawn as StaticMeshActor (Blueprints: theirs)

    def read(self, ue, items, owned=False):
        labels = [it["name"] for it in items]
        return ue.exec(code(READ_ACTORS, LABELS=labels, OWNED=owned, TAG=TAG)) or {}

    def diff(self, want, have):
        ch = super().diff(want, have)
        c = self._cls(want)
        if c and have.get("cls") != c:
            ch.insert(0, {"field": "cls", "have": have.get("cls"), "want": c, "respawn": True})
        return ch

    def create(self, ue, want):
        args = {k: want[k] for k in ("shape", "asset", "cls", "loc", "material") if want.get(k)}
        if want.get("rot") is not None:
            args["rot_"] = want["rot"]
        if want.get("scale") is not None:
            args["scale"] = want["scale"]
        r = ue.level.spawn(label=want["name"], replace=True, **args)
        ue.exec(code(TAG_ACTOR, LABEL=want["name"], TAG=TAG))
        return r

    def update(self, ue, want, have, changes):
        if any(c.get("respawn") for c in changes):
            return self.create(ue, want)
        args = {}
        for c in changes:
            f = c["field"]
            args["rot_" if f == "rot" else f] = want[f]
        return ue.level.move(label=want["name"], **args)

    def delete(self, ue, key):
        return ue.level.delete(labels=[key])

    def owned(self, ue):
        return [lab for lab, st in self.read(ue, [], owned=True).items() if TAG in st.get("tags", [])]


@register
class Sequence(Kind):
    """A level sequence: its playback range [start, end) and frame rate. Kept when it exists (tracks other kinds or
    scripts added stay); a changed fps needs `replace: true`, which recreates it EMPTY."""
    name, section, key, order = "sequence", "sequences", "path", 60
    fields = {"path": F(str, required=True), "start": F(int, default=0), "end": F(int, required=True),
              "fps": F(float, default=24), "replace": F(bool, default=False, doc="recreate it (drops its tracks)")}
    compare = {"start": 0, "end": 0, "fps": 1e-6}

    def read(self, ue, items):
        return ue.exec(code(READ_SEQS, PATHS=[it["path"] for it in items])) or {}

    def plan_one(self, want, have):
        a = super().plan_one(want, have)
        if have and have.get("cls") != "LevelSequence":
            a.action, a.note = "error", f"{want['path']} is a {have.get('cls')}, not a LevelSequence"
            a.error = {"code": "bad_spec", "message": a.note, "hint": "choose another path"}
        elif any(c["field"] == "fps" for c in a.changes) and not want.get("replace"):
            a.note = "fps differs: set replace: true to recreate it (its tracks are lost)"
        return a

    def create(self, ue, want):
        return ue.seq.new(path=want["path"], start=want["start"], end=want["end"], fps=int(round(want["fps"])),
                          replace=bool(want.get("replace")))

    def update(self, ue, want, have, changes):
        if any(c["field"] == "fps" for c in changes) and not want.get("replace"):
            raise ValueError(f"{want['path']}: fps {have.get('fps')} -> {want['fps']} needs replace: true")
        return self.create(ue, want)

    def delete(self, ue, key):
        return ue.assets.delete(path=key)


@register
class Op(Kind):
    """Any op with its arguments, re-run on every apply (not diffable): for what has no kind yet. Prefer ops marked
    idempotent (re-running converges). `name` is only this step's id."""
    name, section, order = "op", "steps", 80
    fields = {"name": F(str, required=True), "op": F(str, required=True, doc="area.verb"),
              "args": F(dict, default={}),
              "timeout": F(float, default=900)}

    def read(self, ue, items):
        return {}

    def plan_all(self, items, have):
        from ..spec import Action
        out = []
        for it in items:
            o = ue_index_op(it["op"])
            note = "re-runs on every apply" + ("" if (o or {}).get("idempotent") else " (op not marked idempotent)")
            if o is None:
                note = f"no op {it['op']!r} in this checkout's schema"
            out.append(Action(self.name, it["name"], "apply", want=it, note=note))
        return out

    def apply(self, ue, action):
        w = action.want
        return ue.call(w["op"], timeout=w.get("timeout", 900), **(w.get("args") or {}))


def ue_index_op(name: str):
    from .. import schema
    return schema.index(schema.load())["ops"].get(name)
