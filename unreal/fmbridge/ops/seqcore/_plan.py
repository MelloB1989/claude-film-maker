"""Planning and checks over canonical sequence documents, pure (no `unreal`).

    plan(want, have)            the op steps that converge `have` (seq.describe) to `want` (a compiled spec)
    lint(doc)                   issues (CONVENTIONS §8 shape) in a described sequence: cut gaps, unbound bindings,
                                keys outside the range, rotation flips, overlapping sections, ...
    shots_of(doc)               the shots of a sequence: its shot track, else its camera cuts
    chunks(doc, ...)            render chunks that respect cloth: each starts at its shot start or pre-rolls back to it
"""
from __future__ import annotations

from ._model import MASTER, PARTIAL, index, track_equal, track_id, track_label
from ._time import Rate


def _step(op: str, why: str, **args) -> dict:
    return {"op": op, "args": args, "why": why}


def plan(want: dict, have: dict | None, *, prune: bool | None = None, tol: float = 1e-4) -> list:
    """Steps [{"op", "args", "why"}] that make the sequence `have` (seq.describe's document, or None when the asset
    does not exist) what `want` (compile_spec's document) asks for. Only what differs gets a step; an empty plan
    means converged. Tracks the spec does not mention are kept unless `prune` (default: the spec's own `prune`),
    which removes the other tracks of the bindings the spec names and the master tracks of the kinds it names."""
    path = want["sequence"]
    steps: list = []
    prune = want.get("prune", False) if prune is None else prune
    settings = {}
    if "range" in want:
        settings["start"], settings["end"] = want["range"]
    if want.get("fps"):
        settings["fps"] = str(want["fps"])
    if want.get("tick_resolution"):
        settings["tick_resolution"] = int(want["tick_resolution"])
    if have is None:
        steps.append(_step("seq.add", "the sequence does not exist", path=path, **settings))
        have = {"sequence": path, "bindings": [], "tracks": [], "markers": []}
    else:
        diff = {}
        if "range" in want and list(have.get("range") or []) != list(want["range"]):
            diff["start"], diff["end"] = want["range"]
        if want.get("fps") and Rate.parse(have.get("fps", 24)) != Rate.parse(want["fps"]):
            diff["fps"] = str(want["fps"])
        if want.get("tick_resolution") and int(have.get("tick_resolution") or 0) != int(want["tick_resolution"]):
            diff["tick_resolution"] = int(want["tick_resolution"])
        if diff:
            steps.append(_step("seq.add", "range/rate differ: " + ", ".join(
                f"{k} {have.get('range') if k in ('start', 'end') else have.get(k)} -> {v}" for k, v in diff.items()),
                path=path, **diff))
    hb = {b["name"]: b for b in have.get("bindings") or []}
    for b in want.get("bindings") or []:
        cur = hb.get(b["name"])
        kind = b.get("kind", "possessable")
        if cur is None:
            steps.append(_step("seq.bind", f"no binding for {b['name']!r}", path=path, label=b["name"],
                               **({"spawn": b["spawn"]} if kind == "spawnable" else {})))
        elif cur.get("kind", "possessable") != kind:
            steps.append(_step("seq.bind", f"{b['name']!r} is {cur.get('kind')}, the spec wants {kind}", path=path,
                               label=b["name"], replace=True, **({"spawn": b["spawn"]} if kind == "spawnable" else {})))
        elif kind == "possessable" and cur.get("bound") is False:
            steps.append(_step("seq.rebind", f"{b['name']!r} is bound to no actor in the level", path=path,
                               labels=[b["name"]]))
    want_markers = sorted((m["frame"], m.get("label", "")) for m in want.get("markers") or [])
    have_markers = sorted((m["frame"], m.get("label", "")) for m in have.get("markers") or [])
    if want.get("markers") is not None and want_markers and want_markers != have_markers:
        steps.append(_step("seq.markers", f"markers differ ({len(have_markers)} -> {len(want_markers)})", path=path,
                           markers=[{"frame": f, "label": lab} for f, lab in want_markers]))
    hidx = index(have)
    for t in want.get("tracks") or []:
        cur = hidx.get(track_id(t))
        if not track_equal(t, cur, tol):
            why = "missing" if cur is None else "differs"
            if cur is not None and t["kind"] in PARTIAL:
                why = "parameters differ"
            steps.append(_step("seq.write", f"{track_label(t)} {why}", path=path, track=t))
    if prune:
        named = {b["name"] for b in want.get("bindings") or []}
        kinds = {t["kind"] for t in want.get("tracks") or [] if t["kind"] in MASTER}
        widx = index(want)
        for t in have.get("tracks") or []:
            k = track_id(t)
            if k in widx:
                continue
            if (t.get("binding") and t["binding"] in named) or (not t.get("binding") and t["kind"] in kinds):
                steps.append(_step("seq.remove_track", f"{track_label(t)} is not in the spec (prune)", path=path,
                                   kind=t["kind"], binding=t.get("binding", ""), component=t.get("component", ""),
                                   name=t.get("name", "")))
    return steps


# --- checks ------------------------------------------------------------------------------------------------------------

def _issue(code: str, severity: str, message: str, fix: str = "", **extra) -> dict:
    d = {"code": code, "severity": severity, "message": message}
    if fix:
        d["fix"] = fix
    d.update({k: v for k, v in extra.items() if v is not None})
    return d


def lint(doc: dict, *, flip_deg: float = 170.0) -> dict:
    """Numeric checks of a described sequence: {"pass", "issues", "metrics"} (CONVENTIONS §8)."""
    issues: list = []
    path = doc.get("sequence", "")
    rng = doc.get("range") or [None, None]
    start, end = rng if len(rng) == 2 else (None, None)
    names = {b["name"] for b in doc.get("bindings") or []}
    for b in doc.get("bindings") or []:
        if b.get("kind", "possessable") == "possessable" and b.get("bound") is False and not b.get("parent"):
            issues.append(_issue("binding_unbound", "fail", f"binding {b['name']!r} resolves to no actor in the level",
                                 f"film-ue op seq.rebind path={path} 'labels=[\"{b['name']}\"]' (after the actor is "
                                 f"back), or remove it", subject=b["name"]))
    keys_total = 0
    for t in doc.get("tracks") or []:
        lab = track_label(t)
        secs = t.get("sections") or []
        if not secs:
            issues.append(_issue("track_empty", "info", f"{lab} has no sections", subject=lab))
        if t.get("binding") and t["binding"] not in names:
            issues.append(_issue("track_orphan", "warn", f"{lab}: binding {t['binding']!r} is not in the sequence",
                                 subject=lab))
        rows: dict = {}
        for s in secs:
            s0, s1 = s["range"]
            if t["kind"] in ("anim", "audio", "shot", "sub", "camera_cut") and s0 is not None:
                for o in rows.get(s.get("row", 0), []):
                    if o[0] < s1 and s0 < o[1] and t["kind"] in ("shot", "sub", "camera_cut"):
                        issues.append(_issue("sections_overlap", "warn", f"{lab}: sections [{o[0]}, {o[1]}) and "
                                             f"[{s0}, {s1}) overlap on row {s.get('row', 0)}", subject=lab, frame=s0))
                rows.setdefault(s.get("row", 0), []).append((s0, s1))
                if end is not None and s0 >= end:
                    issues.append(_issue("section_after_end", "warn", f"{lab}: a section starts at {s0}, after the "
                                         f"playback end {end}", subject=lab, frame=s0))
            for cn, c in (s.get("channels") or {}).items():
                ks = c.get("keys") or []
                keys_total += len(ks)
                out = [k[0] for k in ks if (start is not None and k[0] < start) or (end is not None and k[0] > end)]
                if out:
                    issues.append(_issue("keys_outside_range", "info", f"{lab}.{cn}: {len(out)} key(s) outside the "
                                         f"playback range [{start}, {end}) (first at {out[0]})", subject=lab,
                                         frame=out[0]))
                if t["kind"] == "transform" and cn.startswith("rotation."):
                    for a, b in zip(ks, ks[1:]):
                        if isinstance(a[1], (int, float)) and abs(b[1] - a[1]) > flip_deg:
                            issues.append(_issue("rotation_flip", "warn", f"{lab}.{cn} jumps {b[1] - a[1]:+.1f} deg "
                                                 f"between frames {a[0]} and {b[0]} (a +-180 wrap?)",
                                                 "key it unwrapped (the spec's transform unwraps by default)",
                                                 subject=lab, frame=b[0], value=b[1] - a[1]))
    cuts = sorted((s["range"][0], s["range"][1], s["params"].get("camera"))
                  for t in doc.get("tracks") or [] if t["kind"] == "camera_cut" for s in t.get("sections") or [])
    for s0, s1, cam in cuts:
        if cam and cam not in names:
            issues.append(_issue("cut_camera_missing", "fail", f"the camera cut at {s0} shows {cam!r}, which is not a "
                                 f"binding of the sequence", "seq.apply with camera_cuts naming a bound camera",
                                 frame=s0, camera=cam))
    if cuts and start is not None and end is not None:
        at = start
        for s0, s1, cam in cuts:
            if s0 > at:
                issues.append(_issue("cut_gap", "warn", f"no camera cut covers [{at}, {s0})", frame=at))
            at = max(at, s1)
        if at < end:
            issues.append(_issue("cut_gap", "warn", f"no camera cut covers [{at}, {end})", frame=at))
    metrics = {"bindings": len(names), "tracks": len(doc.get("tracks") or []), "keys": keys_total,
               "cuts": len(cuts), "shots": len(shots_of(doc)), "frames": (end - start) if start is not None and
               end is not None else None}
    return {"pass": not any(i["severity"] == "fail" for i in issues), "issues": issues, "metrics": metrics}


# --- shots and render chunks -------------------------------------------------------------------------------------------

def shots_of(doc: dict) -> list:
    """The shots of a sequence in order: [{"name", "start", "end", "camera"|"sequence", "preroll"}], from its
    cinematic shot track when it has one, else from its camera cuts (each cut is a shot)."""
    shot = [s for t in doc.get("tracks") or [] if t["kind"] == "shot" for s in t.get("sections") or []]
    if shot:
        return sorted(({"name": s["params"].get("name") or s["params"].get("sequence", "").rsplit("/", 1)[-1],
                        "start": s["range"][0], "end": s["range"][1], "sequence": s["params"].get("sequence"),
                        "preroll": s["params"].get("preroll", 0), "row": s.get("row", 0)}
                       for s in shot), key=lambda d: (d["start"], d["row"]))
    cuts = [s for t in doc.get("tracks") or [] if t["kind"] == "camera_cut" for s in t.get("sections") or []]
    return sorted(({"name": f"{s['params'].get('camera')}@{s['range'][0]}", "start": s["range"][0],
                    "end": s["range"][1], "camera": s["params"].get("camera"), "preroll": 0} for s in cuts),
                  key=lambda d: d["start"])


def chunks(doc: dict, *, start: int | None = None, end: int | None = None, max_frames: int = 0,
           preroll: int = 0, max_preroll: int = 0) -> dict:
    """Render chunks for [start, end) (default: the playback range) that never start a cloth simulation cold: each
    chunk lies in one shot and carries `preroll_frames`, the frames to evaluate (and discard) before it, back to its
    shot's start plus `preroll` extra (the shot's own preroll when larger). `max_frames` > 0 splits long shots;
    a later piece of a split shot pre-rolls from the shot start, unless that exceeds `max_preroll` (> 0), when it
    pre-rolls only that much and is flagged "cold". Returns {"chunks": [{"start", "end", "shot", "shot_start",
    "preroll_frames", "eval_from", "first_after_cut", "cold"}], "frames", "preroll_total"}."""
    rng = doc.get("range") or [0, 0]
    start = rng[0] if start is None else start
    end = rng[1] if end is None else end
    shots = shots_of(doc) or [{"name": "all", "start": rng[0], "end": rng[1], "preroll": 0}]
    out = []
    for sh in shots:
        a, b = max(start, sh["start"]), min(end, sh["end"])
        if b <= a:
            continue
        extra = max(int(preroll), int(sh.get("preroll") or 0))
        at = a
        while at < b:
            stop = b if not max_frames else min(b, at + int(max_frames))
            pre = at - sh["start"] + extra
            cold = False
            if max_preroll and pre > max_preroll:
                pre, cold = int(max_preroll), True
            out.append({"start": at, "end": stop, "shot": sh["name"], "shot_start": sh["start"],
                        "preroll_frames": pre, "eval_from": at - pre, "first_after_cut": at == sh["start"],
                        "cold": cold})
            at = stop
    return {"chunks": out, "frames": sum(c["end"] - c["start"] for c in out),
            "preroll_total": sum(c["preroll_frames"] for c in out)}
