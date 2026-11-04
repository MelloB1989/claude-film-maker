"""The PERFORMANCE spec (kind: performance): an actor's lines with their timing, mood, gaze targets, gestures,
expressions and nods, plus body actions (walk to, turn to), compiled into a keyed performance.

    kind: performance
    version: 1
    name: host-intro
    sequence: /Game/Shots/S010
    actor: Presenter
    camera: CamA                      # the target "camera"
    targets: {guest: "Guest:Face:FACIAL_L_Eye", desk: [120, 40, 75]}
    library:
      idle: [/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle]
      walk: {anim: /MetaHumanCharacter/Optional/Animation/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Walk_Loop_F,
             speed_cm_s: 150}
      gestures: {open_palms: {anim: /Game/Anim/Gestures/AS_OpenPalms, stroke_s: 0.7}}
    lines:
      - id: l1
        audio: /home/ue/Audio/l1.wav          # a WAV on the editor's machine; solved with the line's mood
        mood: warm
        gaze: [{at_s: 0, target: camera}, {at_s: 2.4, target: guest, scan: face}]
        gestures: [{name: open_palms, at_s: 1.1}]
        expressions: [{preset: smile, at_s: 2.6, duration_s: 1.4, intensity: 0.6}]
      - {id: beat, duration_s: 1.5, listen: true, gaze: [{at_s: 0, target: guest, scan: face}]}
    actions:
      - {at_s: 6.0, walk_to: desk, speed_cm_s: 120}

Times inside a line (at_s) are seconds from the line's start; lines follow each other (gap_s, default 0.35) unless
they give start_s. Everything here is pure: `compile(spec, state)` needs only the numbers `perf.state` reads from
the editor (positions, clip lengths, audio analysis), and `plan(spec, state)` lists the op calls that converge the
sequence on the spec (empty once it has).
"""
from __future__ import annotations

import hashlib
import json
import math
import random

from . import body as Bd
from . import expressions as X
from . import head as H

KIND, VERSION = "performance", 1
TOP = {"kind", "version", "name", "description", "sequence", "actor", "face_component", "body_component", "camera",
       "targets", "library", "character", "face", "lines", "actions", "default_gaze", "default_mood",
       "start_s", "seed", "fps"}
LINE = {"id", "start_s", "gap_s", "audio", "face_anim", "duration_s", "text", "mood", "intensity", "solver_mood",
        "emphasis", "gaze", "gestures", "expressions", "nods", "tilts", "listen"}
CHARACTER = {"facing_offset_deg", "lead", "head", "energy", "auto_turn_deg", "eye_micro_deg", "signs", "body_life"}
FACE = {"out", "layers", "solver_head", "blink_mode", "mouth_mix", "camera_lock", "solve_folder", "brow_chance",
        "beat_every", "tail_s", "backchannel", "aversion"}
ACTION = {"at_s", "walk_to", "path", "speed_cm_s", "turn_to", "end_facing"}


def _err(errs, where, msg):
    errs.append(f"{where}: {msg}")


def validate(spec: dict) -> list:
    """Problems with a performance spec, each "where: what" (empty when it is good). Mirrors
    tools/filmtools/unreal/schemas/performance.schema.json so the editor refuses what the client would."""
    errs = []
    if not isinstance(spec, dict):
        return ["spec: must be an object"]
    for k in sorted(set(spec) - TOP):
        _err(errs, k, f"unknown key (allowed: {', '.join(sorted(TOP))})")
    if spec.get("kind") != KIND:
        _err(errs, "kind", f"must be {KIND!r}")
    if spec.get("version") != VERSION:
        _err(errs, "version", f"must be {VERSION}")
    for k in ("name", "sequence", "actor"):
        if not isinstance(spec.get(k), str) or not spec.get(k):
            _err(errs, k, "required string")
    if isinstance(spec.get("sequence"), str) and not spec["sequence"].startswith("/"):
        _err(errs, "sequence", "an Unreal package path (/Game/...)")
    for sub, allowed in (("character", CHARACTER), ("face", FACE)):
        for k in sorted(set(spec.get(sub) or {}) - allowed):
            _err(errs, f"{sub}.{k}", f"unknown key (allowed: {', '.join(sorted(allowed))})")
    lead = (spec.get("character") or {}).get("lead", "eyes")
    if lead not in ("eyes", "head"):
        _err(errs, "character.lead", "eyes or head")
    lines = spec.get("lines")
    if not isinstance(lines, list) or not lines:
        _err(errs, "lines", "a non-empty list")
        lines = []
    ids = set()
    for i, ln in enumerate(lines):
        w = f"lines[{i}]"
        if not isinstance(ln, dict):
            _err(errs, w, "must be an object")
            continue
        w = f"lines[{ln.get('id', i)}]"
        for k in sorted(set(ln) - LINE):
            _err(errs, f"{w}.{k}", f"unknown key (allowed: {', '.join(sorted(LINE))})")
        if "id" not in ln:
            _err(errs, w, "needs an id (it names the line's speech solve)")
        elif ln["id"] in ids:
            _err(errs, f"{w}.id", "duplicate")
        ids.add(ln.get("id"))
        if not (ln.get("audio") or ln.get("face_anim") or ln.get("duration_s")):
            _err(errs, w, "needs audio, face_anim or duration_s")
        mood = ln.get("mood")
        if mood is not None and mood not in X.MOODS:
            _err(errs, f"{w}.mood", f"unknown mood {mood!r} (moods: {', '.join(sorted(X.MOODS))})")
        for e in ln.get("expressions") or []:
            p = e.get("preset") if isinstance(e, dict) else None
            if p not in X.PRESETS:
                _err(errs, f"{w}.expressions", f"unknown preset {p!r} (presets: {', '.join(sorted(X.PRESETS))})")
            if isinstance(e, dict) and "at_s" not in e and "on_emphasis" not in e:
                _err(errs, f"{w}.expressions", "each needs at_s or on_emphasis")
        for n in ln.get("nods") or []:
            if not isinstance(n, dict) or ("at_s" not in n and "on_emphasis" not in n):
                _err(errs, f"{w}.nods", "each needs at_s or on_emphasis")
            elif H.Nod.ALIASES.get(n.get("kind", "nod"), n.get("kind", "nod")) not in H.Nod.KINDS:
                _err(errs, f"{w}.nods", f"kind one of {', '.join(H.Nod.KINDS)} (a bare YAML yes/no is a boolean: "
                                        "write nod/shake)")
        for g in ln.get("gaze") or []:
            if not isinstance(g, dict) or "target" not in g:
                _err(errs, f"{w}.gaze", "each needs a target (and at_s, default 0)")
            elif g.get("scan") not in (None, "face", "lens", "still"):
                _err(errs, f"{w}.gaze", "scan is face, lens or still")
        lib = (spec.get("library") or {}).get("gestures") or {}
        for g in ln.get("gestures") or []:
            if not isinstance(g, dict) or ("at_s" not in g and "on_emphasis" not in g):
                _err(errs, f"{w}.gestures", "each needs at_s or on_emphasis")
            elif g.get("name") and g["name"] not in lib and not g.get("anim"):
                _err(errs, f"{w}.gestures", f"no gesture {g['name']!r} in library.gestures ({', '.join(sorted(lib)) or 'empty'})")
    for i, a in enumerate(spec.get("actions") or []):
        w = f"actions[{i}]"
        for k in sorted(set(a) - ACTION):
            _err(errs, f"{w}.{k}", f"unknown key (allowed: {', '.join(sorted(ACTION))})")
        if "at_s" not in a:
            _err(errs, w, "needs at_s")
        if not (a.get("walk_to") is not None or a.get("path") or a.get("turn_to") is not None):
            _err(errs, w, "needs walk_to, path or turn_to")
        if (a.get("walk_to") is not None or a.get("path")) and not (spec.get("library") or {}).get("walk"):
            _err(errs, w, "a walk needs library.walk {anim, speed_cm_s}")
    return errs


def fingerprint(spec: dict, state: dict | None = None) -> str:
    """A short hash of the spec and of the state it depends on (solves, positions): what the composed animation
    was made from. perf.state reads it back from the animation's metadata; equal means converged."""
    st = state or {}
    dep = {"solves": {k: v.get("key") for k, v in (st.get("solves") or {}).items()},
           "targets": st.get("targets"), "actor": st.get("actor"), "fps": st.get("fps")}
    raw = json.dumps({"spec": spec, "dep": dep}, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def solve_key(line: dict, spec: dict) -> str:
    """What a line's speech solve depends on: its WAV, the solver mood and intensity."""
    raw = json.dumps([line.get("audio"), solver_mood(line, spec), float(line.get("intensity", 1.0))])
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def solver_mood(line: dict, spec: dict) -> str:
    if line.get("solver_mood"):
        return str(line["solver_mood"]).upper()
    return X.SOLVER_MOOD.get(line.get("mood") or spec.get("default_mood") or "neutral", "NEUTRAL")


def out_anim(spec: dict) -> str:
    return (spec.get("face") or {}).get("out") or f"/Game/Perf/{spec['name']}/AS_{spec['name']}_face"


def solve_name(spec: dict, line: dict, i: int) -> str:
    return f"{spec['name']}_{line.get('id', i)}".replace("-", "_").replace(" ", "_")


def timeline(spec: dict, state: dict) -> list:
    """Each line's [start_s, end_s] and how long it is, in order: {"id", "start_s", "end_s", "duration_s",
    "listen", "source"}."""
    out = []
    t = float(spec.get("start_s", 0.0))
    for i, ln in enumerate(spec["lines"]):
        lid = ln.get("id", f"line{i}")
        if "start_s" in ln:
            t = float(ln["start_s"])
        elif out:
            t = out[-1]["end_s"] + float(ln.get("gap_s", 0.35))
        dur, src = None, "duration_s"
        if ln.get("audio"):
            a = (state.get("audio") or {}).get(lid) or {}
            dur, src = a.get("duration_s"), "audio"
        if dur is None and ln.get("face_anim"):
            dur, src = ((state.get("clips") or {}).get(ln["face_anim"]) or {}).get("length_s"), "face_anim"
        if dur is None:
            dur, src = float(ln.get("duration_s", 0.0) or 0.0), "duration_s"
        if ln.get("duration_s") and src != "duration_s":
            dur = float(ln["duration_s"])  # an explicit duration trims or pads the line
        out.append({"id": lid, "start_s": round(t, 4), "end_s": round(t + dur, 4), "duration_s": round(dur, 4),
                    "listen": bool(ln.get("listen")), "source": src, "index": i})
    return out


# --- geometry: targets in the character's frame -----------------------------------------------------------------

def _pose_at(keys: list, t: float, fps: float, loc0: list, yaw0: float) -> tuple:
    """The actor's (loc, yaw) at time t from transform keys [[frame, loc, {"yaw"}]] (held outside them)."""
    if not keys:
        return loc0, yaw0
    f = t * fps
    if f <= keys[0][0]:
        return keys[0][1], keys[0][2]["yaw"]
    for a, b in zip(keys, keys[1:]):
        if a[0] <= f <= b[0]:
            u = (f - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 1.0
            return [a[1][k] + (b[1][k] - a[1][k]) * u for k in range(3)], a[2]["yaw"] + (b[2]["yaw"] - a[2]["yaw"]) * u
    return keys[-1][1], keys[-1][2]["yaw"]


def target_angles(target, state: dict, loc: list, yaw: float, head_z_cm: float, facing_offset_deg: float = 0.0):
    """(yaw, pitch, dist_cm) of a gaze target in the character's frame (yaw + = their left) seen from the head of
    an actor at `loc` facing `yaw` (Unreal degrees). `target`: a name in state["targets"] (or "camera"), a point
    [x, y, z], or {"yaw", "pitch"} (already in the character's frame)."""
    if isinstance(target, dict) and ("yaw" in target or "pitch" in target):
        return float(target.get("yaw", 0.0)), float(target.get("pitch", 0.0)), float(target.get("dist_cm", 200.0))
    if isinstance(target, (list, tuple)):
        p = [float(v) for v in target]
    else:
        tg = state.get("targets") or {}
        if target not in tg:
            raise ValueError(f"gaze target {target!r} is not resolved (targets: {', '.join(sorted(tg)) or 'none'})")
        p = tg[target]
    head = [loc[0], loc[1], loc[2] + head_z_cm]
    dx, dy, dz = p[0] - head[0], p[1] - head[1], p[2] - head[2]
    horiz = math.hypot(dx, dy)
    tyaw = math.degrees(math.atan2(dy, dx))
    face = yaw + facing_offset_deg
    rel = (tyaw - face + 180.0) % 360.0 - 180.0  # Unreal: + = to the right
    return -rel, math.degrees(math.atan2(dz, horiz)), math.hypot(horiz, dz)


def _resolve_point(target, state):
    if isinstance(target, (list, tuple)):
        return [float(v) for v in target]
    tg = state.get("targets") or {}
    if target not in tg:
        raise ValueError(f"target {target!r} is not resolved (targets: {', '.join(sorted(tg)) or 'none'})")
    return tg[target]


# --- compile ----------------------------------------------------------------------------------------------------

def compile(spec: dict, state: dict) -> dict:  # noqa: A001 (the spec's verb)
    """Everything a performance needs, in seconds and frames: {"timeline", "duration_s", "fps", "face": face.build
    arguments (lines' solves are placed by the caller at "solves"), "body": seq.anim sections, "transform": key_transform
    keys, "notes"}."""
    errs = validate(spec)
    if errs:
        raise ValueError("bad performance spec: " + "; ".join(errs[:8]))
    fps = float(state.get("fps") or 24)
    seed = int(spec.get("seed", 0))
    ch = spec.get("character") or {}
    fc = spec.get("face") or {}
    lib = spec.get("library") or {}
    tl = timeline(spec, state)
    tail = float(fc.get("tail_s", 0.5))
    actor0 = state.get("actor") or {}
    loc0 = list(actor0.get("loc") or [0.0, 0.0, 0.0])
    yaw0 = float(actor0.get("yaw", 0.0))
    head_z = float(actor0.get("head_z_cm", 160.0))
    off = float(ch.get("facing_offset_deg", 0.0))
    notes = []

    # body actions first: where the actor is at each moment decides where its targets are
    keys, walk_secs = [], []
    loc, yaw = loc0, yaw0
    walk = lib.get("walk")
    clips = state.get("clips") or {}
    for a in sorted(spec.get("actions") or [], key=lambda a: a["at_s"]):
        t = float(a["at_s"])
        if a.get("walk_to") is not None or a.get("path"):
            pts = [_resolve_point(p, state) for p in (a.get("path") or [])]
            if a.get("walk_to") is not None:
                pts.append(_resolve_point(a["walk_to"], state))
            pts = [[p[0], p[1], loc[2]] for p in pts]  # walk on the floor the actor stands on
            end_yaw = None
            if a.get("end_facing") is not None:
                ef = _resolve_point(a["end_facing"], state)
                end_yaw = Bd.heading_deg(pts[-1], ef, -off)
            spd = float(a.get("speed_cm_s", walk.get("speed_cm_s", 140.0) if isinstance(walk, dict) else 140.0))
            wp = Bd.walk(t, loc, pts, fps, speed_cm_s=spd, yaw0=yaw, facing_offset_deg=-off, end_yaw=end_yaw)
            keys += wp["keys"]
            wclip = dict(walk) if isinstance(walk, dict) else {"anim": walk}
            wclip.setdefault("length_s", (clips.get(wclip["anim"]) or {}).get("length_s", 1.0))
            if not wclip.get("speed_cm_s"):
                wclip["speed_cm_s"] = (clips.get(wclip["anim"]) or {}).get("speed_cm_s", spd)
            secs, chk = Bd.walk_sections(wp, wclip, None, fps, spd)
            walk_secs += [(s, wp["walk"]) for s in secs]
            notes.append({"walk": {"at_s": t, "distance_cm": wp["distance_cm"], **chk}})
            loc, yaw = pts[-1], wp["yaw_end"]
        elif a.get("turn_to") is not None:
            tt = a["turn_to"]
            new = float(tt) if isinstance(tt, (int, float)) else Bd.heading_deg(loc, _resolve_point(tt, state), -off)
            tk, _ = Bd.turn(t, yaw, new, fps)
            keys += [[f, [round(v, 2) for v in loc], {"yaw": round(y, 2)}] for f, y in tk]
            yaw = Bd.unwrap(yaw, new)
    act_end = max([k[0] / fps for k in keys] or [0.0])
    total = max(max(x["end_s"] for x in tl), act_end) + tail
    if keys:  # hold the start pose until the first move
        first = keys[0]
        if first[0] > 0:
            keys.insert(0, [0, [round(v, 2) for v in loc0], {"yaw": round(yaw0, 2)}])

    # the face: shifts, moods, events, emphasis, all on the global timeline
    shifts, nods, tilts, moods, events, emphasis, phrase_ends, talk_spans, listen_spans = [], [], [], [], [], [], [], [], []
    default_gaze = spec.get("default_gaze", "camera" if spec.get("camera") else None)
    auto_turn = ch.get("auto_turn_deg")
    for x in tl:
        ln = spec["lines"][x["index"]]
        t0, t1 = x["start_s"], x["end_s"]
        mood = ln.get("mood") or spec.get("default_mood") or "neutral"
        moods.append({"t0": t0, "t1": t1, "mood": mood, "intensity": float(ln.get("intensity", 1.0))})
        gaze = ln.get("gaze")
        if gaze is None and default_gaze is not None:
            gaze = [{"at_s": 0.0, "target": default_gaze, "scan": "lens" if default_gaze == "camera" else None}]
        for g in gaze or []:
            tg = t0 + float(g.get("at_s", 0.0))
            loc_t, yaw_t = _pose_at(keys, tg, fps, loc0, yaw0)
            gy, gp, dist = target_angles(g["target"], state, loc_t, yaw_t, head_z, off)
            scan = g.get("scan", "lens" if g["target"] == "camera" else None)
            shifts.append({"t": tg, "yaw": gy, "pitch": gp, "dist_cm": dist, "scan": scan, "head": g.get("head"),
                           "label": str(g["target"]) if not isinstance(g["target"], (list, dict)) else "point"})
            if auto_turn and abs(gy) > float(auto_turn):
                notes.append({"warn": f"line {x['id']}: gaze to {g['target']} is {gy:.0f} deg off the body's facing "
                                      f"(past auto_turn_deg {auto_turn}); add a turn_to action"})
        if ln.get("emphasis", "auto") == "auto":
            phrase_ends += [t0 + t for t in ((state.get("audio") or {}).get(x["id"]) or {}).get("phrase_ends", [])]
        line_emph = sorted(_line_emphasis(ln, state, x["id"]))  # (seconds from the line's start, strength)
        emphasis += [(t0 + t, k) for t, k in line_emph]

        def at(item, what):
            try:
                return t0 + at_s(item, line_emph)
            except ValueError as err:
                notes.append({"dropped": what, "line": x["id"], "why": str(err)})
                return None
        for n in ln.get("nods") or []:
            t = at(n, "nod")
            if t is not None:
                nods.append({**n, "t": t})
        for tlt in ln.get("tilts") or []:
            tilts.append({**tlt, "t": t0 + float(tlt["at_s"]), "until": t0 + float(tlt.get("until_s", tlt["at_s"] + 2.0))})
        for e in ln.get("expressions") or []:
            d = {k: v for k, v in e.items() if k not in ("at_s", "duration_s", "on_emphasis")}
            t = at(e, f"expression {e.get('preset')}")
            if t is None:
                continue
            d["t"] = t - (0.15 if "on_emphasis" in e and "at_s" not in e else 0.0)  # it peaks on the word
            d["until"] = d["t"] + float(e.get("duration_s", 1.0))
            events.append(d)
        line_ends = [t0 + t for t in ((state.get("audio") or {}).get(x["id"]) or {}).get("phrase_ends", [])]
        if x["listen"] and fc.get("backchannel", True) and not ln.get("nods"):
            nods += backchannel(t0, t1, seed=seed + x["index"])
        if not x["listen"] and fc.get("aversion", True):
            shifts += aversions(t0, t1, line_ends, [s for s in shifts if t0 <= s["t"] <= t1], seed=seed + x["index"])
        phrase_ends.append(t1)
        (listen_spans if x["listen"] else talk_spans).append((t0, t1))

    shifts.sort(key=lambda s: s["t"])
    blink_state = [{"t0": a, "t1": b, "state": "talk"} for a, b in talk_spans] + \
                  [{"t0": a, "t1": b, "state": "listen"} for a, b in listen_spans]
    blink_state.sort(key=lambda s: s["t0"])
    face_args = {"t0": 0.0, "t1": round(total, 4), "shifts": shifts, "lead": ch.get("lead", "eyes"),
                 "head_style": {"seed": seed, **(ch.get("head") or {})}, "nods": nods, "tilts": tilts,
                 "moods": moods, "expressions": events, "emphasis": sorted(emphasis),
                 "phrase_ends": sorted(phrase_ends), "layers": fc.get("layers", list(_layers())),
                 "solver_head": fc.get("solver_head", "soften"), "blink_mode": fc.get("blink_mode", "replace"),
                 "blink_state": blink_state or "talk", "energy": float(ch.get("energy", 1.0)),
                 "mouth_mix": float(fc.get("mouth_mix", 0.5)), "brow_chance": float(fc.get("brow_chance", 0.55)),
                 "beat_every": int(fc.get("beat_every", 1)), "seed": seed, "signs": ch.get("signs"),
                 "talk_spans": talk_spans}

    # the body: idles split around full-body gestures and walks, gestures on their beats
    gest_lib = lib.get("gestures") or {}
    gest_lib = {k: {**v, "length_s": v.get("length_s", (clips.get(v["anim"]) or {}).get("length_s", 2.0))}
                for k, v in gest_lib.items()}
    gestures = []
    for x in tl:
        ln = spec["lines"][x["index"]]
        le = sorted(_line_emphasis(ln, state, x["id"]))
        for g in ln.get("gestures") or []:
            try:
                gestures.append({**g, "at_s": x["start_s"] + at_s(g, le)})
            except ValueError as err:
                notes.append({"dropped": f"gesture {g.get('name') or g.get('anim')}", "line": x["id"], "why": str(err)})
    gsecs, gnotes = Bd.place_gestures(gestures, gest_lib, fps)
    notes += gnotes
    gaps = [(s["start"] / fps, s["end"] / fps) for s in gsecs if not s["additive"]]
    gaps += [(w[0] - 0.2, w[1] + 0.2) for _, w in walk_secs]
    idle_lib = lib.get("idle") or []
    idle_clips = [{"anim": p, "length_s": (clips.get(p) or {}).get("length_s", 6.0)} if isinstance(p, str) else p
                  for p in idle_lib]
    isecs = Bd.idles(0.0, total, idle_clips, fps, gaps=gaps, seed=seed) if idle_clips else []
    body = sorted(isecs + gsecs + [s for s, _ in walk_secs], key=lambda s: s["start"])
    return {"timeline": tl, "duration_s": round(total, 4), "fps": fps, "face": face_args, "body": body,
            "transform": keys, "notes": notes, "face_out": out_anim(spec)}


def at_s(item: dict, line_emphasis: list) -> float:
    """When an item (nod, expression, gesture) happens, seconds from its line's start: its `at_s`, or `on_emphasis`:
    k (the k-th stressed word, 1-based), "strongest", "first" or "last" of the line's emphasis [(t, strength)]."""
    if "at_s" in item:
        return float(item["at_s"])
    k = item.get("on_emphasis")
    if k is None:
        raise ValueError("needs at_s or on_emphasis")
    if not line_emphasis:
        raise ValueError(f"on_emphasis {k!r} but the line has no emphasis (no audio analysis and none given)")
    if k == "strongest":
        return max(line_emphasis, key=lambda e: e[1])[0]
    if k == "first":
        return line_emphasis[0][0]
    if k == "last":
        return line_emphasis[-1][0]
    k = int(k)
    if not 1 <= k <= len(line_emphasis):
        raise ValueError(f"on_emphasis {k} but the line has {len(line_emphasis)} stressed words")
    return line_emphasis[k - 1][0]


def _line_emphasis(ln: dict, state: dict, lid: str) -> list:
    emph = ln.get("emphasis", "auto")
    if emph == "auto":
        emph = ((state.get("audio") or {}).get(lid) or {}).get("emphasis", [])
    out = []
    for e in emph or []:
        if isinstance(e, (int, float)):
            out.append((float(e), 1.0))
        elif isinstance(e, dict):
            out.append((float(e["at_s"]), float(e.get("strength", 1.0))))
        else:
            out.append((float(e[0]), float(e[1])))
    return out


def backchannel(t0: float, t1: float, seed: int = 0) -> list:
    """A listener's small nods (beats, now and then a double nod) every 2.5-5 s while the other one talks: what keeps a
    listening face from reading as frozen. Applied to listen lines without nods of their own (face.backchannel)."""
    rnd = random.Random(seed * 7919 + 11)
    out, t = [], t0 + rnd.uniform(0.5, 1.8)
    while t < t1 - 0.4:
        if rnd.random() < 0.25:
            out.append({"t": round(t, 3), "kind": "nod", "count": 2, "depth_deg": round(rnd.uniform(2.0, 3.5), 2)})
        else:
            out.append({"t": round(t, 3), "kind": "beat", "depth_deg": round(rnd.uniform(1.2, 2.4), 2)})
        t += rnd.uniform(2.5, 5.0)
    return out


def aversions(t0: float, t1: float, phrase_ends: list, line_shifts: list, seed: int = 0) -> list:
    """Thinking glances while talking TO A PERSON: after a pause, people look away briefly (up and to a side,
    8-15 deg, 0.6-1.2 s) as they plan the next phrase, then come back. Not when the line looks at a lens (a presenter
    holds the camera). Returns extra gaze shifts (away and back) for the phrase starts that allow one."""
    rnd = random.Random(seed * 104729 + 3)
    out = []
    for pe in phrase_ends:
        held = [s for s in line_shifts if s["t"] <= pe]
        if not held or held[-1].get("scan") == "lens" or held[-1].get("label") == "camera":
            continue
        cur = held[-1]
        if any(pe - 0.3 < s["t"] < pe + 2.0 for s in line_shifts):  # a planned shift is already there
            continue
        if rnd.random() > 0.6:
            continue
        side = rnd.choice((-1.0, 1.0))
        away = {"t": round(pe + rnd.uniform(0.05, 0.25), 3), "yaw": cur["yaw"] + side * rnd.uniform(8.0, 15.0),
                "pitch": cur["pitch"] + rnd.uniform(3.0, 9.0), "dist_cm": 300.0, "scan": "still", "label": "aversion"}
        back = {**cur, "t": round(away["t"] + rnd.uniform(0.6, 1.2), 3)}
        if back["t"] < t1:
            out += [away, back]
    return out


def _layers():
    from .face import LAYERS
    return LAYERS


def speech_fn(talk_spans: list, envelope: dict | None = None):
    """t -> loudness 0..1 while a line is spoken: the line's audio envelope if perf.state read one
    ({"rate", "values", "offset_s"}), else 0.7 inside the spoken spans."""
    if envelope and envelope.get("values"):
        rate, vals, o = envelope["rate"], envelope["values"], envelope.get("offset_s", 0.0)

        def f(t):
            i = (t - o) * rate
            if i < 0 or i >= len(vals) - 1:
                return 0.0
            k = int(i)
            return vals[k] + (vals[k + 1] - vals[k]) * (i - k)
        return f

    def g(t):
        return 0.7 if any(a <= t <= b for a, b in talk_spans) else 0.0
    return g


# --- plan -------------------------------------------------------------------------------------------------------

def plan(spec: dict, state: dict) -> list:
    """The op calls that converge the editor on `spec`, given `state` (perf.state): solves for lines whose audio has
    no up-to-date solve, then the composition (perf.compose: the face animation, its sequence section, the body
    sections and the actor's transform keys), unless the composed animation already carries this spec's fingerprint.
    [] when converged."""
    errs = validate(spec)
    if errs:
        raise ValueError("bad performance spec: " + "; ".join(errs[:8]))
    steps = []
    solves = state.get("solves") or {}
    face_mesh = (state.get("actor") or {}).get("face_mesh") or ""
    folder = (spec.get("face") or {}).get("solve_folder", f"/Game/Perf/{spec['name']}/Speech")
    for i, ln in enumerate(spec["lines"]):
        if not ln.get("audio"):
            continue
        lid = ln.get("id", f"line{i}")
        key = solve_key(ln, spec)
        have = solves.get(lid) or {}
        if have.get("key") != key:
            steps.append({"op": "perf.solve", "args": {"wav": ln["audio"], "name": solve_name(spec, ln, i),
                                                       "face_mesh": face_mesh, "mood": solver_mood(ln, spec),
                                                       "intensity": float(ln.get("intensity", 1.0)),
                                                       "folder": folder, "key": key},
                          "why": f"line {lid}: " + ("no speech solve yet" if not have else "audio/mood changed")})
    fp = fingerprint(spec, state)
    face = state.get("face") or {}
    if steps or face.get("fingerprint") != fp:
        steps.append({"op": "perf.compose", "args": {"spec": spec},
                      "why": "compose the face animation and key the sequence" + (
                          "" if not face.get("fingerprint") else " (the spec or what it depends on changed)")})
    if (spec.get("face") or {}).get("camera_lock") and spec.get("camera") and steps:
        steps.append({"op": "perf.lock_eyes", "args": {"spec": spec},
                      "why": "measured eye contact with the camera (anim.gaze_lock over the composed face)"})
    return steps
