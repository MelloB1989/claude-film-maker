"""The shot list: a declarative spec (kind "shot") resolved into cameras, keys and an edit.

    kind: shot
    version: 1
    name: scene1
    sequence: /Game/Films/demo/Seq_Scene1
    fps: 24
    lines:                                   # optional: dialogue timing, for times like "L2.start-6f"
      - {id: L1, speaker: A, start_s: 0.8, end_s: 3.1}       # (or start_frame/end_frame)
    timing: {...}                            # or WP12's audio timing document inlined (its words give "L1.w2")
    subjects:                                # who the shots frame: actors in the level
      A: {actor: Presenter}
      B: {actor: Guest}
    defaults: {focal_mm: 50, aperture: 2.8, filmback: "16:9 Digital Film", camera_prefix: CAM_, step: 2}
    shots:
      - id: S1
        start: 0                             # frames; "1.5s"; "48f"; "L1" / "L1.start" / "L1.end"; "S1.end"; +-offsets
        end: L1.start                        # or duration: 2s
        frame: {subjects: [A, B], size: WS, angle: front, height: eye, focal_mm: 28}
      - id: S2
        start: L1.start-4f
        frame: {subjects: [A], size: MCU, angle: 3/4}   # no side: the one that keeps the scene's side of the line
        moves: [{move: push_in, fraction: 0.15}]
        noise: subtle
        focus: A                             # follow-focus on A's eyes; or {distance_cm: 300}; or off
      - id: S3
        coverage: B_OTS                      # a camera from the scene's coverage (cam.coverage)
    auto: {from_lines: true, lead_frames: 4} # optional: cut the lines to the speakers' singles

A shot without `start` starts where the previous one ends; without `end`, it runs to the next shot's start (the
last one: `duration`, else the last line's end plus a second). Shots must not overlap; a gap is held on the previous
camera. `plan` checks everything first and reports every error at once, each with its path and a fix.
"""
from __future__ import annotations

import re

from . import checks, coverage, framing, lens, moves

KIND = "shot"
VERSION = 1
SHOT_KEYS = {"id", "start", "end", "duration", "camera", "frame", "place", "coverage", "moves", "noise", "focus",
             "aperture", "step", "note"}
FRAME_KEYS = {"subjects", "size", "angle", "side", "height", "focal_mm", "distance_cm", "place", "headroom",
              "dutch_deg", "snap_focal", "lead", "margin"}
TOP_KEYS = {"kind", "version", "name", "description", "sequence", "fps", "start_frame", "end_frame", "lines", "timing",
            "subjects", "defaults", "shots", "auto", "coverage", "level"}
DEFAULTS = {"focal_mm": 50.0, "aperture": 2.8, "filmback": lens.DEFAULT_FILMBACK, "camera_prefix": "CAM_", "step": 2,
            "height": "eye", "side": "left", "noise": None, "tail_s": 1.0}

_TIME = re.compile(r"^\s*(?P<base>[A-Za-z_][\w-]*(?:\.w\d+)?(?:\.(?:start|end))?|-?\d+(?:\.\d+)?(?:s|f)?)\s*"
                   r"(?P<off>(?:[+-]\s*\d+(?:\.\d+)?\s*(?:s|f)?\s*)*)$")
_OFF = re.compile(r"([+-])\s*(\d+(?:\.\d+)?)\s*(s|f)?")


class SpecError(ValueError):
    """Every problem in a spec at once: `errors` is [{"path", "message", "fix"}]."""

    def __init__(self, errors: list):
        self.errors = errors
        super().__init__("; ".join(f"{e['path']}: {e['message']}" for e in errors))


def _num(x) -> float:
    return float(x)


def lines_of(spec: dict) -> list:
    """The spec's dialogue lines on its clock: [{"id", "speaker", "start", "end", "words": [[start, end]]}] in frames.
    From `lines` (start_s/end_s seconds or start_frame/end_frame) and/or `timing`, WP12's audio timing document
    (kind "audio": lines with start_frame/end_frame and words, at its own fps, rescaled here)."""
    fps = float(spec.get("fps", 24))
    out = []
    timing = spec.get("timing")
    src = [(ln, float(timing.get("fps", fps))) for ln in (timing or {}).get("lines", [])] if isinstance(timing, dict) \
        else []
    src += [(ln, fps) for ln in spec.get("lines") or []]
    for ln, f in src:
        k = fps / f
        if "start_frame" in ln:
            st = int(round(float(ln["start_frame"]) * k))
        else:
            st = int(round(float(ln["start_s"]) * fps))
        if "end_frame" in ln:
            en = int(round(float(ln["end_frame"]) * k))
        elif "end_s" in ln:
            en = int(round(float(ln["end_s"]) * fps))
        elif "duration_s" in ln:
            en = st + int(round(float(ln["duration_s"]) * fps))
        else:
            en = st
        words = [[int(round(float(w["start_frame"]) * k)), int(round(float(w["end_frame"]) * k))]
                 for w in ln.get("words") or [] if "start_frame" in w]
        out.append({"id": str(ln["id"]), "speaker": ln.get("speaker"), "start": st, "end": en, "words": words})
    return sorted(out, key=lambda x: x["start"])


def parse_time(expr, fps: float, marks: dict) -> int:
    """A time in frames: an int (frames), "48f", "2.5s", or a mark ("L1", "L1.start", "L1.end", "S2.end", a line's
    word "L1.w3.start") with offsets ("L1.start-6f", "S1.end+0.5s"). Marks map names to (start_frame, end_frame)."""
    if isinstance(expr, bool):
        raise ValueError(f"time {expr!r}: a number of frames, '2.5s', '48f' or a mark like 'L1.start-6f'")
    if isinstance(expr, (int, float)):
        return int(round(expr))
    m = _TIME.match(str(expr))
    if not m:
        raise ValueError(f"time {expr!r}: a number of frames, '2.5s', '48f' or a mark like 'L1.start-6f'")
    base = m.group("base")
    if re.match(r"^-?\d", base):
        frames = float(base[:-1]) * fps if base.endswith("s") else float(base.rstrip("f"))
    else:
        name, edge = (base.rsplit(".", 1) if base.endswith((".start", ".end")) else (base, ""))
        if name not in marks:
            raise ValueError(f"time {expr!r}: no line or shot {name!r} (known: {', '.join(sorted(marks)) or 'none'})")
        frames = marks[name][1 if edge == "end" else 0]
        if frames is None:
            raise ValueError(f"time {expr!r}: {name}'s {edge or 'start'} is not known yet (shots resolve in order)")
    for sign, val, unit in _OFF.findall(m.group("off") or ""):
        d = float(val) * (fps if unit == "s" else 1.0)
        frames += d if sign == "+" else -d
    return int(round(frames))


def validate(spec: dict) -> list:
    """The spec's errors as [{"path", "message", "fix"}] (empty when it is good). Structure only: names of subjects
    and coverage shots are checked against the spec; actors are checked in the level by the op."""
    errs = []

    def err(path, msg, fix=""):
        errs.append({"path": path, "message": msg, "fix": fix})

    if not isinstance(spec, dict):
        return [{"path": "", "message": "a shot spec is an object", "fix": "see docs/unreal/camera.md"}]
    for k in spec:
        if k not in TOP_KEYS:
            err(k, f"unknown key {k!r}", f"one of {', '.join(sorted(TOP_KEYS))}")
    if spec.get("kind", KIND) != KIND:
        err("kind", f"kind {spec.get('kind')!r} is not {KIND!r}")
    if int(spec.get("version", VERSION)) != VERSION:
        err("version", f"version {spec.get('version')} is not supported", f"version: {VERSION}")
    seq = spec.get("sequence")
    if not isinstance(seq, str) or not seq.startswith("/"):
        err("sequence", "a level sequence's package path is required", "sequence: /Game/Films/<id>/Seq_<scene>")
    subs = spec.get("subjects") or {}
    if not isinstance(subs, dict):
        err("subjects", "subjects is a map name -> {actor: label}")
        subs = {}
    for n, s in subs.items():
        if not isinstance(s, dict) or not (s.get("actor") or s.get("points")):
            err(f"subjects.{n}", "each subject needs actor (a label in the level) or points (landmarks)",
                f"{n}: {{actor: <label>}}")
    lines = list(spec.get("lines") or [])
    timing = spec.get("timing")
    if timing is not None and not (isinstance(timing, dict) and isinstance(timing.get("lines"), list)):
        err("timing", "timing is an audio timing document (kind audio: {fps, lines: [...]}) inlined",
            "load it on the client (filmtools.unreal.audio_timing.load) and put it here")
        timing = None
    ids = set()
    for i, ln in enumerate(lines + list((timing or {}).get("lines", []))):
        where = f"lines[{i}]" if i < len(lines) else f"timing.lines[{i - len(lines)}]"
        if not isinstance(ln, dict) or "id" not in ln or not ("start_s" in ln or "start_frame" in ln):
            err(where, "a line needs id and start_s or start_frame (and end_s / end_frame)",
                "{id: L1, start_s: 0.8, end_s: 3.1}")
            continue
        if ln["id"] in ids:
            err(f"{where}.id", f"duplicate line id {ln['id']!r}")
        ids.add(ln["id"])
        if "end_s" in ln and "start_s" in ln and float(ln["end_s"]) < float(ln["start_s"]):
            err(where, "end_s is before start_s")
    shots = spec.get("shots") or []
    auto = spec.get("auto")
    if not shots and not auto:
        err("shots", "no shots (and no auto edit)", "add shots: [...] or auto: {from_lines: true}")
    sids = set()
    for i, sh in enumerate(shots):
        p = f"shots[{i}]"
        if not isinstance(sh, dict):
            err(p, "a shot is an object")
            continue
        for k in sh:
            if k not in SHOT_KEYS:
                err(f"{p}.{k}", f"unknown key {k!r}", f"one of {', '.join(sorted(SHOT_KEYS))}")
        sid = sh.get("id")
        if not sid or not re.match(r"^[A-Za-z_][\w-]*$", str(sid)):
            err(f"{p}.id", "each shot needs an id (letters, digits, _ or -; not starting with a digit)", "id: S1")
        elif sid in sids or sid in ids:
            err(f"{p}.id", f"duplicate id {sid!r} (shot and line ids share one namespace)")
        sids.add(sid)
        how = [k for k in ("frame", "place", "coverage") if k in sh]
        if len(how) != 1:
            err(p, f"a shot needs exactly one of frame, place, coverage (has {how or 'none'})",
                "frame: {subjects: [A], size: MCU}")
        fr = sh.get("frame")
        if isinstance(fr, dict):
            for k in fr:
                if k not in FRAME_KEYS:
                    err(f"{p}.frame.{k}", f"unknown key {k!r}", f"one of {', '.join(sorted(FRAME_KEYS))}")
            who = fr.get("subjects")
            who = [who] if isinstance(who, str) else (who or [])
            if not who:
                err(f"{p}.frame.subjects", "frame needs subjects", "subjects: [A]")
            for n in who:
                if n not in subs:
                    err(f"{p}.frame.subjects", f"no subject {n!r}", f"define it under subjects: ({', '.join(subs)})")
            try:
                framing.size_key(fr.get("size", "MCU"))
            except ValueError as e:
                err(f"{p}.frame.size", str(e))
            try:
                framing.angle_deg(fr.get("angle", 0))
            except ValueError as e:
                err(f"{p}.frame.angle", str(e))
        pl = sh.get("place")
        if isinstance(pl, dict) and "loc" not in pl:
            err(f"{p}.place", "place needs loc (and look_at or rot)", "place: {loc: [x, y, z], look_at: [x, y, z]}")
        for j, m in enumerate(sh.get("moves") or []):
            if not isinstance(m, dict) or "move" not in m:
                err(f"{p}.moves[{j}]", "a move is {move: <kind>, ...}", "{move: push_in, fraction: 0.2}")
    return errs


def resolve_times(spec: dict) -> list:
    """Each shot's [start, end) in frames, in order: [{"id", "start", "end"}]. Raises SpecError."""
    fps = float(spec.get("fps", 24))
    marks = {}
    for ln in lines_of(spec):
        marks[ln["id"]] = (ln["start"], ln["end"])
        for k, (ws, we) in enumerate(ln["words"]):
            marks[f"{ln['id']}.w{k}"] = (ws, we)
    line_ids = set(marks)
    shots = spec.get("shots") or []
    errs, out = [], []
    cursor = int(spec.get("start_frame", 0))
    starts = []
    for i, sh in enumerate(shots):  # first pass: starts (a shot may start at an earlier shot's end)
        try:
            st = parse_time(sh["start"], fps, marks) if "start" in sh else cursor
        except ValueError as e:
            errs.append({"path": f"shots[{i}].start", "message": str(e), "fix": ""})
            st = cursor
        en = None
        try:
            if "end" in sh:
                en = parse_time(sh["end"], fps, marks)
            elif "duration" in sh:
                en = st + parse_time(sh["duration"], fps, {})
        except ValueError as e:
            errs.append({"path": f"shots[{i}].end", "message": str(e), "fix": ""})
        starts.append(st)
        marks[sh["id"]] = (st, en)
        out.append({"id": sh["id"], "start": st, "end": en})
        cursor = en if en is not None else st + 1
    last_line = max((m[1] for k, m in marks.items() if k in line_ids), default=None)
    for i, o in enumerate(out):
        if o["end"] is None:
            if i + 1 < len(out):
                o["end"] = out[i + 1]["start"]
            elif spec.get("end_frame") is not None:
                o["end"] = int(spec["end_frame"])
            elif last_line is not None:
                o["end"] = max(o["start"] + 1, last_line + int(round(float(spec.get("defaults", {}).get(
                    "tail_s", DEFAULTS["tail_s"])) * fps)))
            else:
                o["end"] = o["start"] + int(round(3 * fps))
                errs.append({"path": f"shots[{i}]", "message": "the last shot has no end, duration or lines to end "
                             "after; 3 s assumed", "fix": "duration: 3s", "severity": "warn"})
        if o["end"] <= o["start"]:
            errs.append({"path": f"shots[{i}]", "message": f"ends at {o['end']}, not after its start {o['start']}",
                         "fix": "check start/end/duration"})
        if i and o["start"] < out[i - 1]["end"]:
            errs.append({"path": f"shots[{i}].start", "message": f"{o['id']} starts at {o['start']}, inside "
                         f"{out[i - 1]['id']} ({out[i - 1]['start']}-{out[i - 1]['end']})",
                         "fix": f"start it at {out[i - 1]['end']} or end {out[i - 1]['id']} earlier"})
    hard = [e for e in errs if e.get("severity") != "warn"]
    if hard:
        raise SpecError(hard)
    return out


def auto_shots(spec: dict, cov: dict, lead_frames: int = 4, size: str = "MCU", master_s: float = 2.0) -> list:
    """An edit cut from the dialogue: the master until shortly before the first line, then each line on its
    speaker's single (`size`, else the over), cutting `lead_frames` before the line starts; consecutive lines of one
    speaker stay on one shot."""
    fps = float(spec.get("fps", 24))
    lines = lines_of(spec)
    names = {s["name"] for s in cov["shots"]}
    shots = [{"id": "auto_master", "start": int(spec.get("start_frame", 0)), "coverage": "master"}]
    if not lines:
        shots[0]["duration"] = int(round(master_s * fps))
    prev = "master"
    for ln in lines:
        who = ln.get("speaker")
        pick = next((n for n in (f"{who}_{size}", f"{who}_OTS", f"{who}_MS", f"{who}_CU") if n in names), "master")
        if pick == prev:
            continue
        st = max(shots[-1]["start"] + 1, ln["start"] - lead_frames)
        shots.append({"id": f"auto_{ln['id']}", "start": st, "coverage": pick})
        prev = pick
    return shots


def plan(spec: dict, subjects: dict, describe_cov: bool = False) -> dict:
    """Resolve a shot spec against subjects ({name: framing subject}) into what the engine needs:
    {"sequence", "fps", "range": [start, end], "cameras": {label: {"shots", "keys", "lens"}}, "shots": [...],
    "cuts": [[camera, start]], "issues": [...]}. Pure: no engine. Raises SpecError with every problem."""
    errs = validate(spec)
    if errs:
        raise SpecError(errs)
    d = {**DEFAULTS, **(spec.get("defaults") or {})}
    fps = float(spec.get("fps", 24))
    missing = [n for n in (spec.get("subjects") or {}) if n not in subjects]
    if missing:
        raise SpecError([{"path": f"subjects.{n}", "message": f"subject {n!r} was not resolved", "fix":
                          "cam.subject on its actor"} for n in missing])
    subs_all = [subjects[n] for n in spec.get("subjects") or {}]
    line_side = (spec.get("coverage") or {}).get("side", d["side"])  # the scene's side of the line
    cov = None
    needs_cov = spec.get("auto") or any("coverage" in sh for sh in spec.get("shots") or [])
    if needs_cov:
        c = dict(spec.get("coverage") or {})
        cov = coverage.plan(subs_all, side=c.get("side", d["side"]), focal=float(c.get("focal_mm", d["focal_mm"])),
                            wide_focal=float(c.get("wide_focal_mm", 28.0)), filmback=d["filmback"],
                            aperture=float(d["aperture"]), height=c.get("height", d["height"]))
    shots_in = list(spec.get("shots") or [])
    if spec.get("auto"):
        a = spec["auto"]
        shots_in = auto_shots(spec, cov, int(a.get("lead_frames", 4)), a.get("size", "MCU")) + shots_in
        spec = {**spec, "shots": shots_in}
    times = resolve_times(spec)
    out_shots, cuts, issues, cameras = [], [], [], {}
    cov_by = {s["name"]: s for s in (cov or {}).get("shots", [])}
    errs = []
    for i, (sh, tm) in enumerate(zip(shots_in, times)):
        p = f"shots[{i}]"
        label = sh.get("camera") or f"{d['camera_prefix']}{sh['id']}"
        aperture = float(sh.get("aperture", d["aperture"]))
        who = []
        try:
            if "frame" in sh:
                fr = dict(sh["frame"])
                who = [fr["subjects"]] if isinstance(fr["subjects"], str) else list(fr["subjects"])
                side = fr.get("side")
                if side is None and len(who) == 1 and len(subs_all) >= 2:
                    # the subject's own side that keeps the camera on the scene's side of the line
                    pa, pb = subs_all[0]["points"]["eyes"], subs_all[1]["points"]["eyes"]
                    side = coverage._subject_side_for(subjects[who[0]], framing.angle_deg(fr.get("angle", 0.0)),
                                                      coverage._line_side(line_side), pa, pb)
                r = framing.solve([subjects[n] for n in who], fr.get("size", "MCU"), angle=fr.get("angle", 0.0),
                                  side=side or d["side"], height=fr.get("height", d["height"]),
                                  focal=None if fr.get("distance_cm") is not None and "focal_mm" not in fr else
                                  float(fr.get("focal_mm", d["focal_mm"])),
                                  distance=fr.get("distance_cm"), place=fr.get("place", "auto"),
                                  headroom=fr.get("headroom"), dutch=float(fr.get("dutch_deg", 0.0)),
                                  filmback=d["filmback"], aperture=aperture, snap_focal=bool(fr.get("snap_focal")),
                                  lead=float(fr.get("lead", 1 / 3)), margin=float(fr.get("margin", 0.06)))
                cam, size = r["camera"], r["size"]
                issues += [{"code": "cam.solver_warning", "severity": "warn", "message": w, "fix": "", "camera": label,
                            "subject": who[0], "frame": tm["start"]} for w in r["warnings"]]
            elif "coverage" in sh:
                if sh["coverage"] not in cov_by:
                    raise ValueError(f"no coverage shot {sh['coverage']!r}; one of {', '.join(cov_by)}")
                c = cov_by[sh["coverage"]]
                cam, size, who = dict(c["solve"]["camera"]), c["size"], list(c["subjects"])
                cam["aperture"] = aperture
                r = c["solve"]
            else:
                pl = sh["place"]
                rot = pl.get("rot") or framing.geo.look_at(pl["loc"], pl["look_at"], float(pl.get("roll", 0)))
                cam = lens.camera(pl["loc"], rot, float(pl.get("focal_mm", d["focal_mm"])), d["filmback"], aperture)
                size, r = None, None
        except (ValueError, KeyError) as e:
            errs.append({"path": p, "message": str(e), "fix": ""})
            continue
        focus = sh.get("focus", who[0] if who else None)
        focus_on, focus_cm = None, None
        if isinstance(focus, str) and focus in subjects:
            focus_on = subjects[focus]["points"]["eyes"]
        elif isinstance(focus, dict) and "distance_cm" in focus:
            focus_cm = float(focus["distance_cm"])
        elif isinstance(focus, (list, tuple)):
            focus_on = focus
        elif focus not in (None, "off", "manual"):
            errs.append({"path": f"{p}.focus", "message": f"focus {focus!r}: a subject name, [x, y, z], "
                         "{distance_cm: n} or off", "fix": ""})
            continue
        if "focus" not in sh and len(who) > 1:  # a group: split focus (the harmonic mean) between nearest and farthest
            ds = [lens.view(cam, subjects[n]["points"]["eyes"])[0] for n in who]
            focus_on, focus_cm = None, 2 * min(ds) * max(ds) / (min(ds) + max(ds))
        cam["focus"] = focus_cm if focus_cm is not None else (
            lens.view(cam, focus_on)[0] if focus_on is not None else cam.get("focus"))
        aim = subjects[who[0]]["points"]["eyes"] if who else None
        mv = [dict(m) for m in sh.get("moves") or []]
        span = tm["end"] - tm["start"]
        if len(mv) == 1 and not any(k in mv[0] for k in ("frames", "from", "to")):
            mv[0]["frames"] = span  # one move takes the whole shot
        try:
            baked = moves.plan(cam, mv, first=tm["start"], last=tm["end"], fps=fps, step=int(sh.get("step", d["step"])),
                               aim=aim, focus_on=focus_on, noise=sh.get("noise", d["noise"]))
        except ValueError as e:
            errs.append({"path": f"{p}.moves", "message": str(e), "fix": ""})
            continue
        if baked["keys"][-1]["frame"] > tm["end"]:
            issues.append({"code": "shot.move_overrun", "severity": "warn", "message": f"{sh['id']}'s moves run to "
                           f"{baked['keys'][-1]['frame']}, past its end {tm['end']}", "fix": "shorten the moves",
                           "camera": label, "frame": tm["end"]})
        entry = {"id": sh["id"], "camera": label, "start": tm["start"], "end": tm["end"], "size": size,
                 "subjects": who, "lens": {"focal_mm": cam["focal"], "aperture": aperture, "sensor_mm": cam["filmback"]},
                 "start_camera": cam, "keys": baked["keys"], "segments": baked["segments"],
                 "solve": None if r is None else {k: r[k] for k in ("distance", "focal", "error", "warnings")}}
        out_shots.append(entry)
        cameras.setdefault(label, {"shots": [], "keys": [], "lens": entry["lens"]})
        cameras[label]["shots"].append(sh["id"])
        cameras[label]["keys"] += baked["keys"]
        cuts.append([label, tm["start"]])
        issues += [{**it, "camera": label} for it in checks.frame(cam, [subjects[n] for n in who] if who else [],
                                                                  camera=label, at=tm["start"])]
    if errs:
        raise SpecError(errs)
    for a, b in zip(out_shots, out_shots[1:]):
        who = [subjects[n] for n in dict.fromkeys(a["subjects"] + b["subjects"])]
        if not who or a["camera"] == b["camera"]:
            continue
        ka = {**a["start_camera"], **_last(a)}
        issues += checks.cut(ka, b["start_camera"], who, a["size"], b["size"], names=(a["id"], b["id"]),
                             at=b["start"])
    for label, c in cameras.items():  # one camera used by several shots: its keys must not collide
        frames = [k["frame"] for k in c["keys"]]
        if len(frames) != len(set(frames)):
            seen, keep = set(), []
            for k in c["keys"]:
                if k["frame"] not in seen:
                    seen.add(k["frame"])
                    keep.append(k)
            c["keys"] = keep
    rng = [min(s["start"] for s in out_shots), max(s["end"] for s in out_shots)]
    res = {"sequence": spec["sequence"], "fps": fps, "range": rng, "cameras": cameras, "shots": out_shots,
           "cuts": cuts, "issues": issues}
    if describe_cov and cov:
        res["coverage"] = coverage.describe(cov)
    return res


def _last(shot: dict) -> dict:
    k = shot["keys"][-1]
    return {"loc": k["loc"], "rot": k["rot"], "focal": k["focal"]}
