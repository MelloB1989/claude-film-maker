"""The `character` spec kind (WP3): a MetaHuman declared as data; `film-ue plan|apply` converges it through the mh.*
ops, and a second plan is empty once the character matches its spec (mh.describe).

    kind: character
    version: 1
    name: Ava
    asset: /Game/Characters/Ava/MH_Ava       # the MetaHumanCharacter asset
    from: {preset: Ada}                      # or {source: /Game/...} or {blank: true}; only used to create it
    body: {Height: 168, Waist: 61, Hip: 94}  # measurement constraints (cm; Fat/Muscularity/Masculine/Feminine unitless)
    face: {blend: {Ada: 0.7, Vivian: 0.3}}   # or {coefficients: [...]}; landmarks: {index: [dx, dy, dz]}
    skin: {u: 0.55, v: 0.45, roughness: 1.0, texture_resolution: 4k, freckles: {density: 0.2}}
    eyes: {both: {iris: {pattern: Iris003, primary_color_u: 0.2}}}
    eyelashes: {type: LongCurl, melanin: 0.9}
    teeth: {overbite: 0.2}
    makeup: {lips: {type: Natural}}
    grooms: {Hair: {item: WI_Hair_L_Straight, melanin: 1.0, redness: 0.05}, Beard: none}
    outfit: {item: WI_Outfit_Casual, params: {...}}     # or none
    rig: full                                # full | joints | none
    textures: true
    build: {name: Ava, pipeline: cinematic}  # or false
    dress: {label: Ava, garments: {Top: {mesh: /Game/..., materials: {M_Top: /Game/...}}}, hide_slots: {...}}

The steps are the same ops `mh.apply` runs in the editor in one job. Planning is pure (no engine): it compares the
spec with mh.describe's state; the cloud and build steps follow from what changed before them.
"""
from __future__ import annotations

import hashlib
import json
import re

GROOM_SLOTS = ("Hair", "Eyebrows", "Beard", "Mustache", "Eyelashes", "Peachfuzz")
TEXTURE_FIELDS = ("face_albedo", "face_normal", "face_cavity", "face_animated_maps", "body_albedo", "body_normal",
                  "body_cavity", "body_masks")
TEXTURE_RES = {"2k": "RES2K", "4k": "RES4K", "8k": "RES8K", "2048": "RES2K", "4096": "RES4K", "8192": "RES8K"}
TOL = 1e-3


# ------------------------------------------------------------------------------- the same canonical forms as the ops

def snake(name: str) -> str:
    """unreal/fmbridge/ops/mh/_core.py snake(): CamelCase / bFlag field names to the engine's Python names."""
    name = str(name)
    if re.fullmatch(r"b[A-Z]\w*", name):
        name = name[1:]
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s).lower()
    return ALIASES.get(s, s)


ALIASES = {"iris_pattern": "pattern", "iris_rotation": "rotation"}  # the engine's ScriptNames (ops/mh/_core.py)


def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def fingerprint(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def face_fingerprint(blend=None, coefficients=None, landmarks=None) -> str:
    """ops/mh/appearance.py face_fingerprint(): what mh.face records as applied (mh.describe face.applied)."""
    b = None
    if blend:
        total = sum(float(w) for w in blend.values()) or 1.0
        b = {str(k): round(float(w) / total, 6) for k, w in sorted(blend.items())}
    co = [round(float(x), 4) for x in coefficients] if coefficients is not None else None
    lm = {str(int(k)): [round(float(x), 4) for x in v] for k, v in sorted((landmarks or {}).items(),
                                                                          key=lambda kv: int(kv[0]))} or None
    return fingerprint({"blend": b, "coefficients": co, "landmarks": lm})


def item_core(name: str) -> str:
    """A wardrobe item and its palette key compare by this (ops/mh/wardrobe.py _item_path)."""
    n = str(name).rsplit("/", 1)[-1].lower()
    n = n[3:] if n.startswith("wi_") else n
    for z in ("_binding", "_groom"):
        n = n[:-len(z)] if n.endswith(z) else n
    n = re.sub(r" \(\d+\)$", "", n)
    return n.replace("_", "")


def pkey(name: str) -> str:
    n = str(name)
    if len(n) > 1 and n[0] == "b" and n[1].isupper():
        n = n[1:]
    return n.replace("_", "").lower()


def same(want, have) -> bool:
    """A spec value against the described one: numbers within TOL, enum names without case/underscores, colours with
    or without alpha, nested dicts by the spec's keys only (unmentioned fields are free)."""
    if isinstance(want, dict):
        if not isinstance(have, dict):
            return False
        hk = {snake(k): v for k, v in have.items()}
        return all(snake(k) in hk and same(v, hk[snake(k)]) for k, v in want.items())
    if isinstance(want, bool) or isinstance(have, bool):
        return bool(want) == bool(have)
    if isinstance(want, (int, float)) and isinstance(have, (int, float)):
        return abs(float(want) - float(have)) <= TOL
    if isinstance(want, (list, tuple)) and isinstance(have, (list, tuple)):
        w = list(want) + ([1.0] if len(want) == 3 and len(have) == 4 else [])
        return len(w) == len(have) and all(same(a, b) for a, b in zip(w, have))
    if isinstance(want, str) and isinstance(have, str):
        return norm(want) == norm(have)
    return want == have


# --------------------------------------------------------------------------------------------- the spec's sections

def body_args(spec: dict) -> dict:
    b = dict(spec["body"])
    args = {"character": spec["asset"]}
    m = b.pop("measurements", None)
    if b.get("from_character"):
        args["from_character"] = b.pop("from_character")
    if "reset" in b:
        args["reset"] = bool(b.pop("reset"))
    args["measurements"] = m if m is not None else b
    return args


def skin_args(spec: dict) -> dict:
    s = dict(spec["skin"])
    args = {"character": spec["asset"]}
    for k in ("u", "v", "roughness", "texture_resolution"):
        if k in s:
            args[k] = s.pop(k)
    settings = dict(s.pop("settings", None) or {})
    settings.update(s)
    if settings:
        args["settings"] = settings
    return args


def _want_skin(args: dict) -> dict:
    """The skin settings (as mh.describe's skin) a skin step asks for."""
    w = dict(args.get("settings") or {})
    tone = {k: args[k] for k in ("u", "v", "roughness") if k in args}
    if tone:
        w["skin"] = {**(w.get("skin") or {}), **tone}
    if args.get("texture_resolution"):
        r = TEXTURE_RES.get(str(args["texture_resolution"]).lower(), args["texture_resolution"])
        w["desired_texture_sources_resolutions"] = {f: r for f in TEXTURE_FIELDS}
    return w


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _want_eyes(e: dict) -> dict:
    out = {}
    for side, own in (("eye_left", e.get("left")), ("eye_right", e.get("right"))):
        if e.get("both") or own:
            out[side] = _merge(e.get("both") or {}, own or {})
    return out


def _body_differs(args: dict, have: dict) -> bool:
    have_l = {k.lower(): v for k, v in (have or {}).items()}
    want = {k.lower(): v for k, v in (args.get("measurements") or {}).items()}
    for k, v in want.items():
        h = have_l.get(k)
        if (v is None) != (h is None) or (v is not None and abs(float(v) - float(h)) > 0.05):
            return True
    if args.get("reset") and set(have_l) - set(want) and not args.get("from_character"):
        return True
    return bool(args.get("from_character")) and not want  # a copy can only be checked in the editor


def _groom_args(spec: dict, slot: str, g) -> dict:
    if g in (None, "none", False):
        return {"character": spec["asset"], "slot": slot, "item": "none"}
    return {"character": spec["asset"], "slot": slot, **dict(g)}


def _groom_differs(args: dict, have) -> bool:
    if args.get("item") == "none":
        return bool(have)
    if not have:
        return True
    if args.get("item") and item_core(args["item"]) != item_core(have.get("item", "")):
        return True
    params = dict(args.get("params") or {})
    for k in ("melanin", "redness"):
        if args.get(k) is not None:
            params[k.capitalize()] = args[k]
    hp = {pkey(k): v for k, v in (have.get("params") or {}).items()}
    return any(pkey(k) not in hp or not same(v, hp[pkey(k)]) for k, v in params.items())


def plan(spec: dict, state: dict | None) -> list:
    """The steps that make the character match the spec: [{"op", "args", "why"}]. state: mh.describe's result for
    spec.asset ({"exists": false} when it is missing) plus, for a spec with `dress`, state["dress"] from describe()."""
    for k in ("asset",):
        if not spec.get(k):
            raise ValueError(f"a character spec needs `{k}`")
    state = state or {"exists": False}
    path = spec["asset"]
    steps = []

    def step(op, args, why):
        steps.append({"op": op, "args": args, "why": why})

    fresh = not state.get("exists")
    if fresh:
        src = spec.get("from") or {}
        if not src:
            raise ValueError(f"{path} does not exist and the spec has no `from` (preset, source or blank)")
        step("mh.add", {"path": path, **src}, f"{path} does not exist")
    shaped = False  # body/face changed: the rig is stale
    looks = False  # anything the build bakes changed
    if spec.get("body"):
        a = body_args(spec)
        if fresh or _body_differs(a, state.get("body")):
            step("mh.body", a, "the body's measurements differ")
            shaped = looks = True
    if spec.get("face"):
        f = spec["face"]
        fp = face_fingerprint(f.get("blend"), f.get("coefficients"), f.get("landmarks"))
        if fresh or (state.get("face") or {}).get("applied") != fp:
            step("mh.face", {"path": path, **f}, "the face was not made from this blend/coefficients")
            shaped = looks = True
    skin_changed = False
    if spec.get("skin"):
        a = skin_args(spec)
        if fresh or not same(_want_skin(a), state.get("skin") or {}):
            step("mh.skin", a, "skin settings differ")
            skin_changed = looks = True
    if spec.get("eyes"):
        if fresh or not same(_want_eyes(spec["eyes"]), state.get("eyes") or {}):
            step("mh.eyes", {"path": path, **spec["eyes"]}, "eye settings differ")
            looks = True
    for part in ("eyelashes", "teeth", "makeup"):
        if spec.get(part):
            if fresh or not same(spec[part], state.get(part) or {}):
                step(f"mh.{part}", {"path": path, "settings": spec[part]}, f"{part} differ")
                looks = True
    ward = state.get("wardrobe") or {}
    # item parameters (groom colour, garment colours) exist only once the character's collection is built (live
    # 5.8.4): wear the item now, set its parameters after the build, then build again
    later = []
    rig = spec.get("rig", "full")
    builds = spec.get("build", {} if rig and rig != "none" else False) not in (False, None)
    for slot, g in (spec.get("grooms") or {}).items():
        if slot not in GROOM_SLOTS:
            raise ValueError(f"grooms: {slot!r} is not a groom slot ({', '.join(GROOM_SLOTS)})")
        a = _groom_args(spec, slot, g)
        if not builds:  # no build, no item parameters: colours wait for a spec that builds
            a = {k: v for k, v in a.items() if k not in ("melanin", "redness", "params")}
        if fresh or _groom_differs(a, ward.get(slot)):
            colour = {k: a.pop(k) for k in ("melanin", "redness", "params") if a.get(k) is not None}
            if a.get("item") and (fresh or _groom_differs(a, ward.get(slot))):
                step("mh.groom", a, f"{slot} groom differs")
                looks = True
            if colour:  # baked by the build after it
                later.append(("mh.groom", {"character": path, "slot": slot, **colour}, f"{slot} colour differs"))
    if "outfit" in spec:
        o = spec["outfit"]
        if o in (None, "none", False):
            if ward.get("Outfits"):
                step("mh.clear_slot", {"character": path, "slot": "Outfits"}, "an outfit is worn, the spec has none")
                looks = True
        else:
            a = {"character": path, "item": o["item"], "slot": "Outfits", **({"params": o["params"]} if o.get("params")
                                                                           else {})}
            if fresh or _groom_differs({**a, "slot": "Outfits"}, ward.get("Outfits")):
                params = a.pop("params", None)
                if fresh or _groom_differs({**a, "slot": "Outfits"}, ward.get("Outfits")):
                    step("mh.add_item", a, "the outfit differs")
                    looks = True
                if params:
                    later.append(("mh.item_set", {"character": path, "slot": "Outfits", "params": params},
                                  "the outfit's colours differ"))
    rig = spec.get("rig", "full")
    if rig and rig != "none":
        if fresh or shaped or state.get("rigged") is False or state.get("rig_stale"):
            step("mh.rig", {"character": path, "full": rig != "joints"},
                 "the body/face changed" if shaped else "the character is not rigged" if not state.get("rigged")
                 else "the rig is stale")
            looks = True
    want_tex = spec.get("textures", bool(rig and rig != "none"))
    if want_tex and (fresh or skin_changed or not state.get("has_high_res_textures")):
        step("mh.textures", {"character": path}, "no high-resolution textures" if not skin_changed
             else "the skin changed (it discards them)")
        looks = True
    bld = spec.get("build", {} if rig and rig != "none" else False)
    if bld is not False and bld is not None:
        b = dict(bld or {})
        name = b.pop("name", spec.get("name", ""))
        have_bp = (state.get("build") or {}).get("bp", "")
        renamed = bool(name) and bool(have_bp) and not have_bp.endswith(f"/BP_{name}")
        if fresh or looks or renamed or (state.get("build") or {}).get("stale", True):
            step("mh.build", {"character": path, "name": name, **b},
                 "nothing built yet" if not have_bp else "what the build bakes changed")
        if later:
            for op, args, why in later:
                step(op, args, why)
            step("mh.build", {"character": path, "name": name, **b}, "bake the item parameters set after the build")
    if spec.get("dress"):
        d = spec["dress"]
        have = state.get("dress") or {}
        comps = have.get("components") or {}
        missing = [n for n, g in d.get("garments", {}).items()
                   if (comps.get(n) or {}).get("mesh", "").split(".")[0] != g["mesh"].split(".")[0]]
        if missing or not have.get("leader_ok", False) or have.get("hidden") != sorted(d.get("hide_slots") or {}):
            step("mh.dress", dict(d), f"garments to put on or re-lead: {', '.join(missing) or 'leader pose'}")
    return steps


def describe(ue, spec: dict) -> dict:
    """mh.describe for the spec's character, plus the placed actor's garments when the spec dresses one."""
    st = ue.mh.describe(path=spec["asset"])
    d = spec.get("dress")
    if d and st.get("exists"):
        try:
            comps = ue.mh.components(label=d["label"])
            lc = ue.mh.leader_check(label=d["label"])
            st["dress"] = {"components": comps, "leader_ok": bool(lc.get("pass")),
                           "hidden": sorted(d.get("hide_slots") or {})}
        except Exception:
            st["dress"] = {}
    return st


SPEC_KINDS = [{"name": "character", "plan": plan, "describe": describe, "order": 30,
               "doc": "A MetaHuman: from a preset/copy/blank, body, face, skin, eyes, grooms, outfit, cloud rig and "
                      "textures, build, garments on a placed actor."}]
