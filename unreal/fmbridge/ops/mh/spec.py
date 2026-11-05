"""The `character` spec in the editor: mh.apply converges a character to a spec (each step an idempotent mh.* op that
skips what is already so), mh.export writes a character back out as a spec. The client-side planner
(tools/filmtools/unreal/mh_spec.py) diffs a spec against mh.describe and calls the same ops one by one; this op does
the whole thing in one multi-tick job. Schema: tools/filmtools/unreal/schemas/character.schema.json."""
from __future__ import annotations

import inspect

from .. import op
from ...errors import OpError
from ..assets import EAL
from . import _core as K
from . import appearance as A, build as B, character as C, cloud as L, wardrobe as W
from . import actor as D

SECTIONS = ("from", "body", "face", "skin", "eyes", "eyelashes", "teeth", "makeup", "grooms", "outfit", "rig",
            "textures", "build", "dress")
KNOWN = {"kind", "version", "name", "asset", "description", *SECTIONS}


def steps(spec: dict) -> list:
    """The ordered op calls a spec asks for (each converges on its own): [(op name, args)]. Pure: no engine."""
    unknown = set(spec) - KNOWN
    if unknown:
        raise OpError(f"unknown spec keys {sorted(unknown)}", code="bad_args",
                      candidates=K.closest(sorted(unknown)[0], KNOWN), hint="sections: " + ", ".join(SECTIONS))
    if spec.get("kind", "character") != "character":
        raise OpError(f"kind {spec.get('kind')!r} is not a character spec", code="bad_args")
    path = spec.get("asset") or ""
    if not path:
        raise OpError("a character spec needs `asset` (the character's package path)", code="bad_args")
    out = []
    src = spec.get("from") or {}
    out.append(("mh.add", {"path": path, **{k: v for k, v in src.items() if k in ("preset", "source", "blank")}}))
    body = spec.get("body")
    if body:
        b = dict(body)
        args = {"character": path, "measurements": b.pop("measurements", None)}
        if b.get("from_character"):
            args["from_character"] = b.pop("from_character")
        if b.get("reset") is not None:
            args["reset"] = bool(b.pop("reset"))
        if args["measurements"] is None:
            args["measurements"] = b  # the short form: body: {Height: 170, ...}
        out.append(("mh.body", args))
    if spec.get("face"):
        out.append(("mh.face", {"path": path, **spec["face"]}))
    if spec.get("skin"):
        s = dict(spec["skin"])
        args = {"character": path, **{k: s.pop(k) for k in ("u", "v", "roughness", "texture_resolution") if k in s}}
        if s.get("settings"):
            args["settings"] = s.pop("settings")
        if s:
            args.setdefault("settings", {}).update(s)
        out.append(("mh.skin", args))
    if spec.get("eyes"):
        out.append(("mh.eyes", {"path": path, **spec["eyes"]}))
    for part in ("eyelashes", "teeth", "makeup"):
        if spec.get(part):
            out.append((f"mh.{part}", {"path": path, "settings": spec[part]}))
    # item parameters (groom colour, garment colours) exist only once the character's collection is built (live
    # 5.8.4: 'Failed to assemble Instance ... Collection has not been built'): wear the items here, build, set their
    # parameters, build again
    later = []
    for slot, g in (spec.get("grooms") or {}).items():
        if g in (None, "none", False):
            out.append(("mh.groom", {"character": path, "slot": slot, "item": "none"}))
            continue
        g = dict(g)
        colour = {k: g.pop(k) for k in ("melanin", "redness", "params") if g.get(k) is not None}
        if g.get("item"):
            out.append(("mh.groom", {"character": path, "slot": slot, **g}))
        if colour:
            later.append(("mh.groom", {"character": path, "slot": slot, **colour}))
    outfit = spec.get("outfit", "")
    if outfit in (None, "none", False):
        out.append(("mh.clear_slot", {"character": path, "slot": "Outfits"}))
    elif outfit:
        o = dict(outfit)
        out.append(("mh.add_item", {"character": path, "item": o.pop("item"), "slot": "Outfits"}))
        if o.get("params"):
            later.append(("mh.item_set", {"character": path, "slot": "Outfits", "params": o.pop("params")}))
    rig = spec.get("rig", "full")
    if rig and rig != "none":
        out.append(("mh.rig", {"character": path, "full": rig != "joints"}))
    if spec.get("textures", bool(rig and rig != "none")):
        out.append(("mh.textures", {"character": path}))
    bld = spec.get("build", {} if rig and rig != "none" else False)
    if bld is not False and bld is not None:
        bld = dict(bld or {})
        b = ("mh.build", {"character": path, "name": bld.pop("name", spec.get("name", "")), **bld})
        out.append(b)
        if later:
            out += later + [b]
    # (no build: no item parameters exist, so colours wait for a spec that builds)
    if spec.get("dress"):
        out.append(("mh.dress", dict(spec["dress"])))
    return out


@op("mh.apply", mutates=True, idempotent=True, tags=["slow", "needs-epic-login", "metahuman"])
def apply(*, spec: dict, dry_run: bool = False, stop_before: str = ""):
    """Converge a character to a `character` spec in one multi-tick job: make it (from a preset/source/blank), shape
    the body and face, skin, eyes, eyelashes, teeth, makeup, grooms with colours, outfit, cloud rig and textures,
    build the Blueprint, dress a placed actor. Every step is an mh.* op that changes only what differs, so a second
    apply reports nothing changed.

    Args: spec: the spec object (schema: character.schema.json; examples/unreal/character/). dry_run: return the
    steps without running them. stop_before: an op name to stop at (e.g. "mh.rig" to shape without the cloud).
    Returns: {"asset", "steps": [{"op", "args", "changed", "result"}], "changed", "describe"}.
    Example: film-ue op mh.apply 'spec={"kind": "character", "version": 1, "name": "Ava", "asset": "/Game/Characters/Ava/MH_Ava", "from": {"preset": "Ada"}, "body": {"Height": 168}}'
    """
    from .. import call
    plan = steps(spec)
    if dry_run:
        return {"asset": spec["asset"], "steps": [{"op": n, "args": a} for n, a in plan], "changed": False}
    done, changed = [], False
    for name, args in plan:
        if stop_before and name == stop_before:
            break
        res = call(name, **args)
        if inspect.isgenerator(res):
            res = yield from res
        ch = bool(res.get("changed")) if isinstance(res, dict) else bool(res)
        changed = changed or ch
        done.append({"op": name, "args": args, "changed": ch, "result": res})
        yield
    return {"asset": spec["asset"], "steps": done, "changed": changed,
            "describe": C.describe(path=spec["asset"]) if EAL.does_asset_exist(K.package(spec["asset"])) else None}


@op("mh.export", mutates=False, idempotent=True, tags=["metahuman"])
def export(*, path: str, name: str = "", face: bool = True) -> dict:
    """A character written back as a `character` spec (what mh.apply would converge a fresh copy to): body
    measurements, face coefficients, skin, eyes, eyelashes, teeth, makeup, grooms and outfit with their parameters,
    rig and build. Apply it to a new asset (change `asset` and add `from: {preset: ...}`) for a twin.

    Args: path: the character. name: the spec's name (default the asset's). face: include the face coefficients.
    Returns: the spec object.
    Example: film-ue op mh.export path=/Game/Characters/Ava/MH_Ava
    """
    s = C.describe(path=path, full=face)
    if not s.get("exists"):
        raise OpError(f"no character {path}", code="not_found", hint="mh.find lists them")
    spec = {"kind": "character", "version": 1, "name": name or K.package(path).rsplit("/", 1)[1].removeprefix("MH_"),
            "asset": K.package(path), "body": {"measurements": s["body"], "reset": True}}
    if face and s["face"].get("coefficients"):
        spec["face"] = {"coefficients": s["face"]["coefficients"]}
    sk = dict(s["skin"])
    spec["skin"] = {"settings": {k: v for k, v in sk.items() if k not in ("texture_overrides",
                                                                          "texture_material_overrides")}}
    spec["eyes"] = {"left": s["eyes"].get("eye_left", {}), "right": s["eyes"].get("eye_right", {})}
    spec["eyelashes"], spec["teeth"], spec["makeup"] = s["eyelashes"], s["teeth"], s["makeup"]
    grooms, outfit = {}, None
    for slot, e in (s.get("wardrobe") or {}).items():
        if slot == "error":
            continue
        if slot in K.GROOM_SLOTS:
            grooms[slot] = None if not e else {"item": e["item"], "params": e.get("params") or {}}
        elif slot == "Outfits":
            outfit = None if not e else {"item": e["item"], "params": e.get("params") or {}}
    spec["grooms"] = grooms
    spec["outfit"] = outfit if outfit else "none"
    spec["rig"] = "full" if s.get("rigged") else "none"
    spec["textures"] = bool(s.get("has_high_res_textures"))
    if s["build"].get("bp"):
        spec["build"] = {"name": s["build"]["bp"].rsplit("/BP_", 1)[-1]}
    return spec


# the op modules this package is made of (kept referenced for the linters)
_ = (A, B, L, W, D)
