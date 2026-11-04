"""The SEQUENCE SPEC, pure (no `unreal`): a declarative description of a level sequence that `seq.apply` converges
the engine to, and `seq.plan` diffs. YAML or JSON; every time may be frames (48), "2s", "48f" or "00:00:02:00".

    kind: sequence                         # the spec header (CONVENTIONS §7): kind, version, name
    version: 1
    name: sh010
    sequence: /Game/Film/Seq/SEQ_010      # required: the asset (made if missing)
    fps: 24                                # display rate (24, 25, 30, 23.976, "30000/1001")
    range: [0, 10s]                        # playback [start, end); or `duration: 10s` from 0
    markers: [[48, beat], {frame: 4s, label: hit}]
    prune: false                           # true: tracks on the bindings this spec names, and master tracks of the
                                           #   kinds it names, that the spec does not list are removed
    bindings:
      Hero:                                # an actor label in the level: a possessable
        transform:                         # keys: [frame, [x,y,z], {pitch,yaw,roll} | [x,y,z] look-at point(, interp)]
          interp: auto                     #   or {frame, loc, rot, look_at (point or actor label), scale, interp}
          keys: [[0, [0,0,0], {yaw: 90}], {frame: 2s, loc: [100,0,0], look_at: Heroine}]
        visible: [[0, true], [100, false]]
        anim:                              # skeletal animation sections on a component (a MetaHuman: Body / Face)
          component: Body
          sections: [{anim: /Game/A/Idle, start: 0, end: 120, blend_in: 6, offset: 0.5, rate: 1, loop: true}]
        props:                             # any keyable property: "Prop.Path" or "Component/Prop.Path"
          Intensity: [[0, 5000], [48, 8000]]
          LightComponent0/LightColor: {type: color, srgb: true, keys: [[0, [1, 0.5, 0.2]]]}
        materials:
          - {component: StaticMeshComponent0, slot: 0, param: Glow, keys: [[0, 0], [24, 1]]}
      CamA:
        spawn: {class: CineCameraActor}    # a spawnable the sequence owns (or {template: <level actor label>})
        transform: {keys: [[0, [0, -300, 160], [0, 0, 150]]]}
        props: {CameraComponent/CurrentFocalLength: [[0, 35]]}
    camera_cuts: [[CamA, 0], [CamB, 5s]]   # each runs to the next; the last to the end of the range
    audio: {VO: [{sound: /Game/Audio/L1, start: 12, offset: 0.0, volume: 1.0}]}
    fade: {color: [0, 0, 0], audio: false, keys: [[0, 1], [12, 0], [228, 0], [240, 1]]}
    level_visibility: [{start: 0, end: 100, visible: false, levels: [Studio_Lights]}]
    collections: [{collection: /Game/MPC_FM, param: WipeOn, keys: [[0, 0], [24, 1]]}]
    shots:                                 # a cinematic shot track (one row unless `row`)
      - {sequence: /Game/Shots/SEQ_sh010, start: 0, end: 120, name: sh010, offset: 0, timescale: 1, preroll: 8}
    subsequences: {FX: [{sequence: /Game/FX/SEQ_Sparks, start: 40, end: 80}]}
    tracks: [...]                          # raw canonical tracks (what seq.describe returns), for anything else

`compile_spec(spec, resolver)` returns (doc, notes): the canonical document (see _model) the engine is converged to.
The resolver answers what only the engine knows (an actor's location for look-at, an animation's length, which
component carries a property, a property's type); `NullResolver` guesses offline and says so in the notes.
"""
from __future__ import annotations

from ._curves import KeyError_, look_at, normalize_keys, srgb_to_linear, unwrap
from ._model import KINDS, MASTER, TRANSFORM_CHANNELS, channel, new_section, new_track
from ._time import Rate, snap

TOP_KEYS = {"sequence", "fps", "tick_resolution", "range", "duration", "markers", "prune", "bindings",
            "camera_cuts", "audio", "fade", "level_visibility", "collections", "shots", "subsequences", "tracks",
            "$schema", "description", "notes", "kind", "version", "name"}
BINDING_KEYS = {"spawn", "transform", "visible", "anim", "props", "materials", "tracks", "class", "kind", "name",
                "parent", "bound", "id", "description"}


class SpecError(ValueError):
    """Everything wrong with a spec at once, each as "where: what (what to write instead)"."""

    def __init__(self, problems: list):
        self.problems = list(problems)
        super().__init__(f"{len(problems)} problem(s) in the sequence spec:\n  " + "\n  ".join(problems))


class NullResolver:
    """Answers offline (no engine): guesses, and records what it guessed in `notes`."""

    def __init__(self):
        self.notes: list = []

    def actor_location(self, label: str):
        self.notes.append(f"look_at {label!r}: resolved in the editor")
        return None

    def actor_transform(self, label: str):
        return None

    def anim_length(self, path: str):
        self.notes.append(f"{path}: length read in the editor (end defaults to its length)")
        return None

    def sound_duration(self, path: str):
        self.notes.append(f"{path}: duration read in the editor (end defaults to its length)")
        return None

    def prop_info(self, binding: str, component: str, prop: str, sample=None) -> dict:
        """{"component": the owner's name ("" = the actor), "kind": float/double/bool/color/vector/byte/integer/string,
        "srgb": FColor property}"""
        return {"component": component, "kind": _guess_kind(prop, sample), "srgb": None}

    def material_slot(self, binding: str, component: str, slot) -> tuple:
        return component, (slot if isinstance(slot, int) else 0), (slot if isinstance(slot, str) else "")

    def skeletal_component(self, binding: str, component: str) -> str:
        return component or "SkeletalMeshComponent0"


def _guess_kind(prop: str, sample) -> str:
    if isinstance(sample, bool):
        return "bool"
    if isinstance(sample, str):
        return "string"
    if isinstance(sample, (list, tuple)):
        return "color" if "color" in prop.lower() or len(sample) == 4 else "vector"
    return "float"


def _as_list(v, what: str, problems: list) -> list:
    if v is None:
        return []
    if not isinstance(v, list):
        problems.append(f"{what}: expected a list, got {type(v).__name__}")
        return []
    return v


def _rotator(v, where: str) -> dict:
    if not isinstance(v, dict):
        raise KeyError_(f"{where}: a rotation is {{pitch, yaw, roll}} in degrees (never a positional list), got {v!r}")
    bad = set(v) - {"pitch", "yaw", "roll"}
    if bad:
        raise KeyError_(f"{where}: unknown rotation fields {sorted(bad)} (pitch, yaw, roll)")
    return {"pitch": float(v.get("pitch", 0.0)), "yaw": float(v.get("yaw", 0.0)), "roll": float(v.get("roll", 0.0))}


def _vec3(v, where: str) -> list:
    if not (isinstance(v, (list, tuple)) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v)):
        raise KeyError_(f"{where}: expected [x, y, z] (cm), got {v!r}")
    return [float(x) for x in v]


class Compiler:
    def __init__(self, spec: dict, resolver=None):
        self.spec = spec
        self.r = resolver or NullResolver()
        self.problems: list = []
        self.notes: list = []
        self.children: list = []  # shot sequences a shot list makes: their specs, converged before this one
        try:
            self.rate = Rate.parse(spec.get("fps", 24))
        except ValueError as e:
            self.problems.append(f"fps: {e}")
            self.rate = Rate(24)

    def t(self, v, where: str):
        try:
            return snap(self.rate.parse_time(v))
        except ValueError as e:
            self.problems.append(f"{where}: {e}")
            return 0

    def keys(self, raw, where: str, value=float, interp="auto"):
        try:
            return normalize_keys(raw, interp=interp, value=value, rate=self.rate, where=where)
        except KeyError_ as e:
            self.problems.append(str(e))
            return []

    # --- the document ------------------------------------------------------------------------------------------------

    def compile(self) -> tuple:
        s = self.spec
        if not isinstance(s, dict):
            raise SpecError([f"the spec is a mapping, got {type(s).__name__}"])
        unknown = set(s) - TOP_KEYS
        if unknown:
            self.problems.append(f"unknown top-level keys {sorted(unknown)} (known: {', '.join(sorted(TOP_KEYS))})")
        if s.get("kind", "sequence") != "sequence":
            self.problems.append(f"kind: {s.get('kind')!r} is not a sequence spec (kind: sequence)")
        if "version" in s and s["version"] != 1:
            self.problems.append(f"version: {s['version']!r} is not supported (1)")
        path = s.get("sequence")
        if not isinstance(path, str) or not path.startswith("/"):
            self.problems.append("sequence: the asset path is required, e.g. /Game/Film/Seq/SEQ_010")
        doc = {"sequence": path, "fps": str(self.rate), "tracks": [], "bindings": [], "markers": []}
        if "tick_resolution" in s:
            try:
                doc["tick_resolution"] = Rate.parse(s["tick_resolution"]).numerator
            except ValueError as e:
                self.problems.append(f"tick_resolution: {e}")
        if "range" in s:
            rg = s["range"]
            if not (isinstance(rg, list) and len(rg) == 2):
                self.problems.append(f"range: [start, end) expected, got {rg!r}")
            else:
                doc["range"] = [self.t(rg[0], "range[0]"), self.t(rg[1], "range[1]")]
        elif "duration" in s:
            doc["range"] = [0, self.t(s["duration"], "duration")]
        if "range" in doc and doc["range"][1] <= doc["range"][0]:
            self.problems.append(f"range: end {doc['range'][1]} must be after start {doc['range'][0]}")
        for i, m in enumerate(_as_list(s.get("markers"), "markers", self.problems)):
            if isinstance(m, (list, tuple)) and len(m) >= 1:
                doc["markers"].append({"frame": self.t(m[0], f"markers[{i}]"), "label": str(m[1]) if len(m) > 1 else ""})
            elif isinstance(m, dict) and "frame" in m:
                mk = {"frame": self.t(m["frame"], f"markers[{i}].frame"), "label": str(m.get("label", ""))}
                if "color" in m:
                    mk["color"] = list(m["color"])
                doc["markers"].append(mk)
            else:
                self.problems.append(f"markers[{i}]: [frame, label] or {{frame, label}}, got {m!r}")
        self.range = doc.get("range")
        bindings = s.get("bindings") or {}
        if isinstance(bindings, list):  # a describe document's binding list: declarations only
            for i, b in enumerate(bindings):
                if not isinstance(b, dict) or "name" not in b:
                    self.problems.append(f"bindings[{i}]: {{name, kind}} expected")
                    continue
                doc["bindings"].append({k: b[k] for k in ("name", "kind", "class", "parent", "spawn") if k in b})
        elif isinstance(bindings, dict):
            for label, b in bindings.items():
                self.binding(doc, str(label), b or {})
        else:
            self.problems.append("bindings: a mapping {actor label: {...}}")
        if "camera_cuts" in s:
            doc["tracks"].append(self.camera_cuts(s["camera_cuts"]))
        if "audio" in s:
            doc["tracks"] += self.audio(s["audio"])
        if "fade" in s:
            doc["tracks"].append(self.fade(s["fade"]))
        if "level_visibility" in s:
            doc["tracks"].append(self.level_visibility(s["level_visibility"]))
        if "collections" in s:
            doc["tracks"] += self.collections(s["collections"])
        if "shots" in s:
            doc["tracks"].append(self.subs(s["shots"], "shot", "", "shots"))
        if "subsequences" in s:
            sub = s["subsequences"]
            if isinstance(sub, list):
                sub = {"Subsequences": sub}
            for name, items in (sub or {}).items():
                doc["tracks"].append(self.subs(items, "sub", str(name), f"subsequences.{name}"))
        if "range" not in doc:  # a shot list laid end to end: the master runs from the first shot to the last
            shot_secs = [x for t in doc["tracks"] if t["kind"] in ("shot", "sub") for x in t["sections"]]
            if shot_secs:
                doc["range"] = [min(x["range"][0] for x in shot_secs), max(x["range"][1] for x in shot_secs)]
        for i, t in enumerate(_as_list(s.get("tracks"), "tracks", self.problems)):
            doc["tracks"].append(self.raw_track(t, f"tracks[{i}]"))
        seen = {}
        for t in doc["tracks"]:
            from ._model import track_id, track_label
            k = track_id(t)
            if k in seen and t["kind"] not in ("material", "mpc"):
                self.problems.append(f"{track_label(t)} is given twice: merge them into one")
            seen[k] = t
        doc["tracks"] = _merge_partial(doc["tracks"])
        if self.problems:
            raise SpecError(self.problems)
        doc["prune"] = bool(s.get("prune", False))
        if self.children:
            doc["children"] = self.children
        return doc, self.notes + getattr(self.r, "notes", [])

    # --- bindings ----------------------------------------------------------------------------------------------------

    def binding(self, doc: dict, label: str, b: dict):
        w = f"bindings.{label}"
        if not isinstance(b, dict):
            self.problems.append(f"{w}: a mapping of tracks (transform, visible, anim, props, materials, spawn)")
            return
        unknown = set(b) - BINDING_KEYS
        if unknown:
            self.problems.append(f"{w}: unknown keys {sorted(unknown)} (known: {', '.join(sorted(BINDING_KEYS))})")
        decl = {"name": label, "kind": "possessable"}
        if b.get("spawn"):
            sp = b["spawn"]
            if sp is True:
                sp = {"template": label}
            if not isinstance(sp, dict) or not ({"class", "template"} & set(sp)):
                self.problems.append(f"{w}.spawn: {{class: CineCameraActor}} or {{template: <level actor label>}}")
            else:
                decl = {"name": label, "kind": "spawnable", "spawn": dict(sp)}
        doc["bindings"].append(decl)
        if "transform" in b:
            doc["tracks"].append(self.transform(label, b["transform"], f"{w}.transform"))
        if "visible" in b:
            v = b["visible"]
            keys = v.get("keys") if isinstance(v, dict) else v
            comp = v.get("component", "") if isinstance(v, dict) else ""
            ks = self.keys(keys, f"{w}.visible", value=_bool, interp="constant")
            ks = [[k[0], k[1], "constant"] for k in ks]
            doc["tracks"].append(new_track("visibility", label, comp, "", sections=[
                new_section(params={}, channels={"visible": channel(ks)})]))
        if "anim" in b:
            doc["tracks"] += self.anim(label, b["anim"], f"{w}.anim")
        if "props" in b:
            props = b["props"]
            if isinstance(props, list):
                props = {p.get("prop", f"#{i}") if isinstance(p, dict) else f"#{i}": p for i, p in enumerate(props)}
            for name, p in (props or {}).items():
                t = self.prop(label, str(name), p, f"{w}.props.{name}")
                if t:
                    doc["tracks"].append(t)
        if "materials" in b:
            for i, m in enumerate(_as_list(b["materials"], f"{w}.materials", self.problems)):
                t = self.material(label, m, f"{w}.materials[{i}]")
                if t:
                    doc["tracks"].append(t)
        for i, t in enumerate(_as_list(b.get("tracks"), f"{w}.tracks", self.problems)):
            t = dict(t)
            t.setdefault("binding", label)
            doc["tracks"].append(self.raw_track(t, f"{w}.tracks[{i}]"))

    def transform(self, label: str, tr, w: str) -> dict:
        if isinstance(tr, list):
            tr = {"keys": tr}
        interp = tr.get("interp", "auto")
        comp = tr.get("component", "")
        chans = {c: [] for c in TRANSFORM_CHANNELS}
        for i, k in enumerate(tr.get("keys") or []):
            at = f"{w}.keys[{i}]"
            try:
                loc = rot = scale = aim = None
                how = interp
                tangents = None
                if isinstance(k, (list, tuple)):
                    if len(k) < 2:
                        raise KeyError_(f"{at}: [frame, [x,y,z](, rotation | look-at point(, interp))]")
                    f = k[0]
                    loc = _vec3(k[1], f"{at} location") if k[1] is not None else None
                    if len(k) > 2 and k[2] is not None:
                        if isinstance(k[2], (list, tuple)) or isinstance(k[2], str):
                            aim = k[2]
                        else:
                            rot = _rotator(k[2], f"{at} rotation")
                    if len(k) > 3:
                        how = k[3]
                elif isinstance(k, dict):
                    bad = set(k) - {"frame", "f", "loc", "location", "rot", "rotation", "look_at", "scale", "interp",
                                    "tangents"}
                    if bad:
                        raise KeyError_(f"{at}: unknown fields {sorted(bad)} (frame, loc, rot, look_at, scale, interp)")
                    f = k.get("frame", k.get("f"))
                    if f is None:
                        raise KeyError_(f"{at}: 'frame' is required")
                    lv = k.get("loc", k.get("location"))
                    loc = _vec3(lv, f"{at}.loc") if lv is not None else None
                    rv = k.get("rot", k.get("rotation"))
                    rot = _rotator(rv, f"{at}.rot") if rv is not None else None
                    aim = k.get("look_at")
                    if k.get("scale") is not None:
                        sc = k["scale"]
                        scale = [float(sc)] * 3 if isinstance(sc, (int, float)) else _vec3(sc, f"{at}.scale")
                    how = k.get("interp", interp)
                    tangents = k.get("tangents")
                else:
                    raise KeyError_(f"{at}: a transform key is a list or a dict, got {k!r}")
                if aim is not None and rot is not None:
                    raise KeyError_(f"{at}: give a rotation or a look_at, not both")
                if aim is not None:
                    src = loc
                    if src is None:
                        raise KeyError_(f"{at}: look_at needs the key's location too")
                    if isinstance(aim, str):
                        p = self.r.actor_location(aim)
                        if p is None:
                            self.notes.append(f"{at}: look_at {aim!r} left unresolved offline")
                            p = None
                        aim = p
                    if aim is not None:
                        rot = look_at(src, _vec3(aim, f"{at}.look_at"))
                fr = snap(self.rate.parse_time(f))
                if loc is not None:
                    for c, v in zip(TRANSFORM_CHANNELS[:3], loc):
                        chans[c].append([fr, v, how] + ([tangents.get(c)] if tangents and tangents.get(c) else []))
                if rot is not None:
                    for c, n in zip(TRANSFORM_CHANNELS[3:6], ("roll", "pitch", "yaw")):
                        chans[c].append([fr, rot[n], how])
                if scale is not None:
                    for c, v in zip(TRANSFORM_CHANNELS[6:], scale):
                        chans[c].append([fr, v, how])
            except (KeyError_, ValueError) as e:
                self.problems.append(str(e))
        out = {}
        for c, ks in chans.items():
            ks = self.keys(ks, f"{w}.{c}", value=float, interp=interp)
            if c.startswith("rotation.") and tr.get("unwrap", True) and ks:
                for k, v in zip(ks, unwrap([k[1] for k in ks])):
                    k[1] = v
            out[c] = channel(ks)
        cur = self.r.actor_transform(label) if not comp else None
        if cur:  # channels the spec leaves unkeyed hold the actor's current value, not zero
            for c, v in zip(TRANSFORM_CHANNELS, list(cur["location"]) + [cur["rotation"][n] for n in (
                    "roll", "pitch", "yaw")] + list(cur["scale"])):
                if not out[c]["keys"]:
                    out[c]["default"] = float(v)
        return new_track("transform", label, comp, "", sections=[new_section(self._whole(), channels=out)])

    def _whole(self):
        return (None, None)

    def anim(self, label: str, a, w: str) -> list:
        if isinstance(a, list):
            a = {"sections": a}
        groups = a if isinstance(a, dict) and "sections" not in a and all(isinstance(v, (list, dict)) for v in a.values()) \
            and not ({"component", "anim"} & set(a)) else {a.get("component", ""): a}
        out = []
        for comp, g in groups.items():
            if isinstance(g, list):
                g = {"sections": g}
            comp = self.r.skeletal_component(label, comp or g.get("component", ""))
            secs = []
            taken = []
            for i, d in enumerate(g.get("sections") or []):
                at = f"{w}.sections[{i}]"
                if not isinstance(d, dict) or "anim" not in d:
                    self.problems.append(f"{at}: {{anim, start(, end, offset, rate, blend_in, blend_out, weight, loop,"
                                         f" row, slot)}}")
                    continue
                bad = set(d) - {"anim", "start", "end", "offset", "rate", "blend_in", "blend_out", "weight", "loop",
                                "row", "slot", "reverse"}
                if bad:
                    self.problems.append(f"{at}: unknown fields {sorted(bad)}")
                start = self.t(d.get("start", 0), f"{at}.start")
                rate = float(d.get("rate", 1.0))
                offset = float(d.get("offset", 0.0))
                if rate <= 0:
                    self.problems.append(f"{at}.rate: must be > 0 (use reverse: true to play backwards)")
                    rate = 1.0
                if "end" in d:
                    end = self.t(d["end"], f"{at}.end")
                else:
                    length = self.r.anim_length(d["anim"])
                    end = snap(start + self.rate.frames_ceil(max(0.0, (length - offset)) / rate)) if length else None
                    if end is None:
                        end = snap(start + 1)
                        self.notes.append(f"{at}: end unknown offline (the animation's length); 1 frame assumed")
                if d.get("loop") is False:  # no hold-last-frame in 5.8: the section stops where the clip ends
                    length = self.r.anim_length(d["anim"])
                    if length:
                        end = min(end, snap(start + self.rate.frames_ceil(max(0.0, length - offset) / rate)))
                    else:
                        self.notes.append(f"{at}: loop false needs the clip's length (read in the editor)")
                if end <= start:
                    self.problems.append(f"{at}: end {end} must be after start {start}")
                row = d.get("row")
                if row is None:
                    row = 0
                    while any(r == row and s < end and start < e for s, e, r in taken):
                        row += 1
                taken.append((start, end, row))
                # every param seq.describe reports, defaults filled, so a spec that omits one converges to it
                p = {"anim": d["anim"], "offset": offset, "rate": rate, "slot": str(d.get("slot", "DefaultSlot")),
                     "reverse": bool(d.get("reverse", False)),
                     "blend_in": self.t(d.get("blend_in", 0), f"{at}.blend_in"),
                     "blend_out": self.t(d.get("blend_out", 0), f"{at}.blend_out")}
                ch = {}
                if "weight" in d:
                    ch["weight"] = channel([], float(d["weight"])) if isinstance(d["weight"], (int, float)) else \
                        channel(self.keys(d["weight"], f"{at}.weight"))
                secs.append(new_section((start, end), row, p, ch))
            out.append(new_track("anim", label, comp, "", sections=secs))
        return out

    def prop(self, label: str, name: str, p, w: str):
        if not isinstance(p, dict):
            p = {"keys": p}
        prop = p.get("prop", name)
        comp = p.get("component", "")
        if "/" in prop:
            comp, prop = prop.split("/", 1)
        keys = p.get("keys")
        if keys is None and "value" in p:
            keys = [[self.range[0] if self.range else 0, p["value"]]]
        if not keys:
            self.problems.append(f"{w}: no keys (keys: [[frame, value], ...] or value: v)")
            return None
        first = keys[0][1] if isinstance(keys[0], (list, tuple)) else (keys[0] or {}).get("value")
        info = self.r.prop_info(label, comp, prop, first)
        kind = p.get("type") or info.get("kind") or _guess_kind(prop, first)
        if kind not in ("float", "double", "bool", "byte", "integer", "string", "color", "vector"):
            self.problems.append(f"{w}: type {kind!r} is not a property track type (float, double, bool, byte, "
                                 f"integer, string, color, vector)")
            return None
        comp = info.get("component", comp)
        interp = p.get("interp", "constant" if kind in ("bool", "byte", "integer", "string") else "auto")
        params = {}
        if kind in ("color", "vector"):
            n = 4 if kind == "color" else max(len(first) if isinstance(first, (list, tuple)) else 3, 2)
            srgb = p.get("srgb", info.get("srgb"))
            if kind == "color":
                params["_srgb"] = bool(srgb)  # compile-time only: the keys below are linear either way
            names = KINDS[kind][0][:n]
            ks = self.keys(keys, w, value=lambda v: _components(v, n, kind), interp=interp)
            chans = {}
            for j, cn in enumerate(names):
                ck = []
                for k in ks:
                    v = k[1][j]
                    if kind == "color" and srgb and j < 3:
                        v = srgb_to_linear(v)
                    ck.append([k[0], v, k[2]])
                chans[cn] = channel(ck)
        else:
            conv = {"float": float, "double": float, "bool": _bool, "byte": int, "integer": int, "string": str}[kind]
            chans = {"value": channel(self.keys(keys, w, value=conv, interp=interp))}
        if kind == "double":
            kind, params["double"] = "float", True
        return new_track(kind, label, comp, _camel_path(prop), params, [new_section((None, None), 0, {}, chans)])

    def material(self, label: str, m, w: str):
        if not isinstance(m, dict) or "param" not in m:
            self.problems.append(f"{w}: {{param, keys(, component, slot)}}")
            return None
        comp, idx, slot_name = self.r.material_slot(label, m.get("component", ""), m.get("slot", 0))
        keys = m.get("keys") or ([[0, m["value"]]] if "value" in m else [])
        vector = bool(keys) and isinstance((keys[0][1] if isinstance(keys[0], (list, tuple)) else keys[0].get("value")),
                                           (list, tuple))
        ks = self.keys(keys, w, value=(lambda v: _components(v, 4, "color")) if vector else float,
                       interp=m.get("interp", "auto"))
        params = {"slot": idx}
        if slot_name:
            params["slot_name"] = slot_name
        return new_track("material", label, comp, f"slot:{idx}", params,
                         [new_section((None, None), 0, {}, {str(m["param"]): channel(ks)})])

    # --- master tracks -----------------------------------------------------------------------------------------------

    def camera_cuts(self, cuts) -> dict:
        secs = []
        cuts = _as_list(cuts, "camera_cuts", self.problems)
        parsed = []
        for i, c in enumerate(cuts):
            if isinstance(c, dict):
                c = [c.get("camera"), c.get("start", c.get("frame", 0))] + ([c["end"]] if "end" in c else [])
            if not (isinstance(c, (list, tuple)) and len(c) >= 2 and isinstance(c[0], str)):
                self.problems.append(f"camera_cuts[{i}]: [camera label, first frame(, end)], got {c!r}")
                continue
            parsed.append((c[0], self.t(c[1], f"camera_cuts[{i}]"), self.t(c[2], f"camera_cuts[{i}].end")
                           if len(c) > 2 else None))
        parsed.sort(key=lambda x: x[1])
        end_all = self.range[1] if self.range else None
        for k, (cam, start, end) in enumerate(parsed):
            stop = end if end is not None else (parsed[k + 1][1] if k + 1 < len(parsed) else end_all)
            if stop is None:
                self.problems.append("camera_cuts: the last cut needs an end, or give the sequence a range")
                stop = start + 1
            if stop <= start:
                self.problems.append(f"camera_cuts: {cam} at {start} has no length (next cut at {stop})")
            secs.append(new_section((start, stop), 0, {"camera": cam}))
        return new_track("camera_cut", "", "", "", sections=secs)

    def audio(self, a) -> list:
        if isinstance(a, list):
            a = {"Audio": a}
        out = []
        for name, clips in (a or {}).items():
            secs, taken = [], []
            for i, c in enumerate(_as_list(clips, f"audio.{name}", self.problems)):
                at = f"audio.{name}[{i}]"
                if isinstance(c, (list, tuple)):
                    c = {"sound": c[0], "start": c[1] if len(c) > 1 else 0}
                if not isinstance(c, dict) or "sound" not in c:
                    self.problems.append(f"{at}: {{sound, start(, end, offset, volume, pitch)}}")
                    continue
                start = self.t(c.get("start", 0), f"{at}.start")
                offset = float(c.get("offset", 0.0))
                if "end" in c:
                    end = self.t(c["end"], f"{at}.end")
                else:
                    d = self.r.sound_duration(c["sound"])
                    end = snap(start + self.rate.frames_ceil(max(0.0, d - offset))) if d else snap(start + 1)
                row = int(c.get("row", 0)) if "row" in c else 0
                if "row" not in c:
                    while any(r == row and s < end and start < e for s, e, r in taken):
                        row += 1
                taken.append((start, end, row))
                p = {"sound": c["sound"], "offset": offset}
                ch = {}
                for n in ("volume", "pitch"):
                    if n in c:
                        ch[n] = channel([], float(c[n])) if isinstance(c[n], (int, float)) else channel(
                            self.keys(c[n], f"{at}.{n}"))
                secs.append(new_section((start, end), row, p, ch))
            out.append(new_track("audio", "", "", str(name), sections=secs))
        return out

    def fade(self, f) -> dict:
        if isinstance(f, list):
            f = {"keys": f}
        params = {}
        if "color" in f:
            params["color"] = [float(x) for x in (list(f["color"]) + [1.0] * (4 - len(f["color"])))]
        if "audio" in f:
            params["fade_audio"] = bool(f["audio"])
        ks = self.keys(f.get("keys"), "fade.keys", interp=f.get("interp", "linear"))
        for k in ks:
            if not 0.0 <= k[1] <= 1.0:
                self.problems.append(f"fade.keys: {k[1]} at {k[0]} is outside 0 (clear) .. 1 (full colour)")
        return new_track("fade", "", "", "", sections=[new_section((None, None), 0, params,
                                                                     {"value": channel(ks)})])

    def level_visibility(self, items) -> dict:
        secs = []
        for i, it in enumerate(_as_list(items, "level_visibility", self.problems)):
            at = f"level_visibility[{i}]"
            if not isinstance(it, dict) or "levels" not in it:
                self.problems.append(f"{at}: {{start, end, visible, levels: [level names]}}")
                continue
            start = self.t(it.get("start", self.range[0] if self.range else 0), f"{at}.start")
            end = self.t(it["end"], f"{at}.end") if "end" in it else (self.range[1] if self.range else None)
            if end is None:
                self.problems.append(f"{at}: end is needed (or a sequence range)")
                continue
            secs.append(new_section((start, end), int(it.get("row", i)), {
                "visible": bool(it.get("visible", True)), "levels": [str(x) for x in it["levels"]]}))
        return new_track("level_visibility", "", "", "", sections=secs)

    def collections(self, items) -> list:
        out = []
        for i, it in enumerate(_as_list(items, "collections", self.problems)):
            at = f"collections[{i}]"
            if not isinstance(it, dict) or not {"collection", "param"} <= set(it):
                self.problems.append(f"{at}: {{collection, param, keys}}")
                continue
            ks = self.keys(it.get("keys") or ([[0, it["value"]]] if "value" in it else []), f"{at}.keys",
                           interp=it.get("interp", "auto"))
            out.append(new_track("mpc", "", "", it["collection"], sections=[
                new_section((None, None), 0, {}, {str(it["param"]): channel(ks)})]))
        return out

    def subs(self, items, kind: str, name: str, w: str) -> dict:
        """Shot / subsequence sections. A shot list: `start` defaults to the previous shot's end (on its row),
        `duration` instead of `end`; `camera: <label>` or `shot: {...}` (an inline sequence spec: bindings,
        camera_cuts, ...) makes the shot's own sequence (at `sequence`, default <master>_<name>), which apply
        converges first; `handles` frames of it before and after the cut (the section starts that far in)."""
        secs = []
        at_row: dict = {}
        master = (self.spec.get("sequence") or "/Game/Seq").rsplit(".", 1)[0]
        for i, it in enumerate(_as_list(items, w, self.problems)):
            at = f"{w}[{i}]"
            if not isinstance(it, dict) or not ({"sequence", "camera", "shot"} & set(it)):
                self.problems.append(f"{at}: {{sequence | camera | shot, start, end | duration(, name, offset, "
                                     f"timescale, preroll, postroll, row, handles)}}")
                continue
            bad = set(it) - {"sequence", "start", "end", "name", "offset", "timescale", "preroll", "postroll", "row",
                             "duration", "camera", "shot", "handles"}
            if bad:
                self.problems.append(f"{at}: unknown fields {sorted(bad)}")
            row = int(it.get("row", 0))
            start = self.t(it["start"], f"{at}.start") if "start" in it else at_row.get(row, 0)
            if "end" in it:
                end = self.t(it["end"], f"{at}.end")
            elif "duration" in it:
                end = snap(start + self.t(it["duration"], f"{at}.duration"))
            else:
                self.problems.append(f"{at}: end (or duration) is required")
                continue
            if end <= start:
                self.problems.append(f"{at}: end {end} must be after start {start}")
            at_row[row] = end
            nm = str(it.get("name") or (str(it["sequence"]).rsplit("/", 1)[-1] if "sequence" in it else f"sh{i + 1:03d}"))
            path = it.get("sequence") or f"{master}_{nm}"
            handles = self.t(it.get("handles", 0), f"{at}.handles")
            if handles < 0:
                self.problems.append(f"{at}.handles: must be >= 0")
            p = {"sequence": path}
            if kind == "shot":
                p["name"] = nm
            for k in ("offset", "preroll", "postroll"):
                p[k] = self.t(it.get(k, 0), f"{at}.{k}")
                if k != "offset" and p[k] < 0:
                    self.problems.append(f"{at}.{k}: must be >= 0")
            if handles and "offset" not in it:
                p["offset"] = handles
            p["timescale"] = float(it.get("timescale", 1.0))
            if p["timescale"] <= 0:
                self.problems.append(f"{at}.timescale: must be > 0")
            if "camera" in it or "shot" in it:
                inner = dict(it.get("shot") or {})
                stray = {"sequence", "kind", "version"} & set(inner)
                if stray:
                    self.problems.append(f"{at}.shot: {sorted(stray)} come from the shot entry, not the inline spec")
                length = snap(handles * 2 + (end - start) * p["timescale"])
                child = {"kind": "sequence", "version": 1, "name": nm, "sequence": path,
                         "fps": self.spec.get("fps", 24), "range": [0, length], **{k: v for k, v in inner.items()
                                                                                   if k not in stray}}
                if "camera" in it:
                    child.setdefault("bindings", {}).setdefault(str(it["camera"]), {})
                    child.setdefault("camera_cuts", [[str(it["camera"]), 0]])
                try:
                    Compiler(child, self.r).compile()
                except SpecError as e:
                    self.problems += [f"{at}.shot: {x}" for x in e.problems]
                self.children.append(child)
            secs.append(new_section((start, end), row, p))
        rows = {}
        for s in secs:
            for o in rows.get(s["row"], []):
                if s["range"][0] < o["range"][1] and o["range"][0] < s["range"][1]:
                    self.problems.append(f"{w}: {s['params'].get('name') or s['params']['sequence']} overlaps "
                                         f"{o['params'].get('name') or o['params']['sequence']} on row {s['row']} "
                                         f"(give one another row)")
            rows.setdefault(s["row"], []).append(s)
        return new_track(kind, "", "", name, sections=secs)

    def raw_track(self, t, w: str) -> dict:
        if not isinstance(t, dict) or "kind" not in t:
            self.problems.append(f"{w}: a track is {{kind, binding, component, name, params, sections}}")
            return new_track("float")
        if t["kind"] not in KINDS:
            self.problems.append(f"{w}.kind: {t['kind']!r} is not one of {', '.join(sorted(KINDS))}")
            return new_track("float")
        if t["kind"] in MASTER and t.get("binding") and t["kind"] not in ("event",):
            self.problems.append(f"{w}: a {t['kind']} track lives on the sequence, not on binding {t['binding']!r}")
        out = new_track(t["kind"], t.get("binding", ""), t.get("component", ""), t.get("name", ""), t.get("params"))
        for j, s in enumerate(t.get("sections") or []):
            rng = s.get("range") or [None, None]
            chans = {}
            for cn, c in (s.get("channels") or {}).items():
                vt = KINDS[t["kind"]][1]
                conv = (vt if vt in (float, int, str) else _bool if vt is bool else None)
                if t["kind"] in ("material",) and c.get("keys") and isinstance(c["keys"][0][1], (list, tuple)):
                    conv = lambda v: _components(v, 4, "color")  # noqa: E731
                chans[cn] = channel(self.keys(c.get("keys") or [], f"{w}.sections[{j}].channels.{cn}",
                                              value=conv), c.get("default"))
            out["sections"].append(new_section((None if rng[0] is None else self.t(rng[0], f"{w}.range"),
                                                None if rng[1] is None else self.t(rng[1], f"{w}.range")),
                                               int(s.get("row", 0)), s.get("params"), chans))
        return out


def _merge_partial(tracks: list) -> list:
    """Material / collection entries for the same slot or collection become one track with a channel per param."""
    from ._model import PARTIAL, track_id
    out, by = [], {}
    for t in tracks:
        if t["kind"] in PARTIAL:
            k = track_id(t)
            if k in by:
                by[k]["sections"][0]["channels"].update(t["sections"][0]["channels"])
                continue
            by[k] = t
        out.append(t)
    return out


def _bool(v):
    if isinstance(v, bool):
        return v
    if v in (0, 1):
        return bool(v)
    if isinstance(v, str) and v.lower() in ("true", "false", "on", "off", "yes", "no"):
        return v.lower() in ("true", "on", "yes")
    raise ValueError("expected true or false")


def _components(v, n: int, kind: str) -> list:
    if not isinstance(v, (list, tuple)) or not all(isinstance(x, (int, float)) for x in v):
        raise ValueError(f"expected a list of numbers ({'[r, g, b(, a)]' if kind == 'color' else '[x, y, z]'})")
    v = [float(x) for x in v]
    if kind == "color":
        if len(v) not in (3, 4):
            raise ValueError("a colour is [r, g, b] or [r, g, b, a]")
        return v + [1.0] * (4 - len(v))
    if not 2 <= len(v) <= 4:
        raise ValueError("a vector has 2 to 4 components")
    return v


def _camel_path(prop: str) -> str:
    """Sequencer binds properties by their C++ path: "focus_settings.manual_focus_distance" ->
    "FocusSettings.ManualFocusDistance"; a C++ spelling passes through."""
    def camel(p):
        return "".join(w[:1].upper() + w[1:] for w in p.split("_")) if ("_" in p or p.islower()) else p
    return ".".join(camel(p) for p in prop.split("."))


def compile_spec(spec: dict, resolver=None) -> tuple:
    """A spec -> (canonical document, notes). Raises SpecError listing every problem."""
    return Compiler(spec, resolver).compile()


def validate(spec: dict) -> dict:
    """Offline check: {"ok", "problems", "notes", "tracks"} without an engine (guesses are noted, not failed)."""
    try:
        doc, notes = compile_spec(spec, NullResolver())
        from ._model import track_label
        return {"ok": True, "problems": [], "notes": notes, "tracks": [track_label(t) for t in doc["tracks"]]}
    except SpecError as e:
        return {"ok": False, "problems": e.problems, "notes": [], "tracks": []}
