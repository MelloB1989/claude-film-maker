"""Shooting a scene from a shot list: a declarative spec (kind "shot", camkit.shotlist) becomes cameras, their keys and
the sequence's camera cuts; read back as the edit with each shot's camera and size; checked shot by shot and cut by
cut; and seen as a contact sheet with guides.

`shot.apply` converges: cameras by label (made or moved), each camera's tracks replaced, the cut track replaced, the
spec's hash stored on the sequence (asset metadata `fm_shot_spec`), so a second apply of the same spec changes
nothing; cameras an earlier version of the spec made and this one no longer uses are removed.
"""
from __future__ import annotations

import hashlib
import json
import os

import unreal

from . import call, op
from . import cam
from ..camkit import checks as ck
from ..camkit import framing, png, shotlist
from ..errors import OpError, not_found

EAL = unreal.EditorAssetLibrary
TAG_HASH, TAG_CAMS = "fm_shot_spec", "fm_shot_cameras"
LSE = unreal.LevelSequenceEditorBlueprintLibrary


def _spec_hash(spec: dict) -> str:
    return hashlib.sha1(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _subjects_for(spec: dict) -> dict:
    out = {}
    for name, s in (spec.get("subjects") or {}).items():
        if "points" in s:
            out[name] = framing.make_subject(name, s["points"], s.get("facing", (1, 0, 0)))
        else:
            out[name] = cam.subject(s["actor"], s.get("mode", "auto"), s.get("facing"), s.get("top_z"), name=name)
    return out


def _plan(spec: dict) -> dict:
    errs = shotlist.validate(spec)
    if errs:
        raise OpError(f"the shot spec has {len(errs)} problem(s): " + "; ".join(f"{e['path']}: {e['message']}"
                                                                             for e in errs[:6]),
                      code="bad_args", hint="fix them and plan again (shot.plan)", details={"errors": errs})
    subs = _subjects_for(spec)
    try:
        return shotlist.plan(spec, subs, describe_cov=True)
    except shotlist.SpecError as e:
        raise OpError(f"the shot spec does not resolve: {e}", code="bad_args", details={"errors": e.errors}) from None


def _summary(p: dict) -> dict:
    return {"sequence": p["sequence"], "fps": p["fps"], "range": p["range"], "cuts": p["cuts"],
            "shots": [{"id": s["id"], "camera": s["camera"], "start": s["start"], "end": s["end"], "size": s["size"],
                       "subjects": s["subjects"], "focal_mm": round(s["lens"]["focal_mm"], 2),
                       "aperture": s["lens"]["aperture"], "keys": len(s["keys"]), "moves": s["segments"],
                       "solve": s["solve"]} for s in p["shots"]],
            "issues": p["issues"], "coverage": p.get("coverage")}


@op("shot.plan", mutates=False, idempotent=True, tags=["camera", "sequencer"])
def plan(*, spec: dict) -> dict:
    """Resolve a shot list against the level without changing anything: each shot's camera, frames, size, lens,
    keys, the cuts, and every framing/cut issue. The dry run of shot.apply.

    Args: spec: a kind "shot" spec (docs/unreal/camera.md; schema tools/filmtools/unreal/schemas/shot.schema.json).
    Returns: {"sequence", "range", "cuts", "shots": [...], "issues": [...], "coverage", "spec_hash",
    "up_to_date": whether the sequence already holds this exact spec}.
    Example: film-ue op shot.plan spec=@films/demo/shots/scene1.yaml
    """
    p = _plan(spec)
    h = _spec_hash(spec)
    cur = _stored(spec["sequence"])
    return {**_summary(p), "spec_hash": h, "up_to_date": cur.get("hash") == h}


def _stored(path: str) -> dict:
    if not EAL.does_asset_exist(path):
        return {}
    seq = EAL.load_asset(path)
    h = EAL.get_metadata_tag(seq, TAG_HASH) or ""
    cams = [c for c in (EAL.get_metadata_tag(seq, TAG_CAMS) or "").split(",") if c]
    return {"hash": h, "cameras": cams}


@op("shot.apply", mutates=True, idempotent=True, tags=["camera", "sequencer"])
def apply(*, spec: dict, force: bool = False) -> dict:
    """Shoot a shot list into its sequence: make or move each shot's camera (framed by the solver, the coverage or an
    explicit placement), key its moves, focal length and focus, and replace the sequence's camera cuts. Converges:
    the same spec again changes nothing (force=True rewrites anyway); cameras the previous spec made that this one
    drops are removed. A multi-tick job: the keys and cuts go in one batched seq.apply when WP8's core is there.

    Returns: shot.plan's result plus {"changed", "cameras": {label: {"created", "keys"}}, "removed", "write"}.
    Example: film-ue op shot.apply spec=@films/demo/shots/scene1.yaml
    """
    p = _plan(spec)
    h = _spec_hash(spec)
    path = spec["sequence"]
    before = _stored(path)
    cams_now = list(p["cameras"])
    if not force and before.get("hash") == h and all(cam._find(c) is not None for c in cams_now):
        return {**_summary(p), "spec_hash": h, "changed": False, "cameras": {}, "removed": []}
    call("seq.new", path=path, start=p["range"][0], end=p["range"][1], fps=int(round(p["fps"])))
    done = {}
    shots_by_cam = {}
    for s in p["shots"]:
        shots_by_cam.setdefault(s["camera"], s)
    for label, c in p["cameras"].items():
        first = shots_by_cam[label]
        sc = first["start_camera"]
        res = cam.add(label=label, loc=sc["loc"], rot_=sc["rot"], focal_mm=sc["focal"], aperture=first["lens"]["aperture"],
                      sensor_mm=sc["filmback"], focus_cm=sc.get("focus"))
        done[label] = {"created": res["created"], "keys": len(c["keys"])}
    write = yield from cam.write_tracks(path, {label: c["keys"] for label, c in p["cameras"].items()}, p["cuts"],
                                        fps=int(round(p["fps"])), rng=p["range"])
    removed = []
    stale = [c for c in before.get("cameras", []) if c not in p["cameras"]]
    if stale:
        removed = cam.remove(labels=stale)["removed"]
    seq = EAL.load_asset(path)
    EAL.set_metadata_tag(seq, TAG_HASH, h)
    EAL.set_metadata_tag(seq, TAG_CAMS, ",".join(cams_now))
    EAL.save_asset(path)
    return {**_summary(p), "spec_hash": h, "changed": True, "cameras": done, "removed": removed, "write": write}


@op("shot.describe", mutates=False, idempotent=True, tags=["camera", "sequencer"])
def describe(*, sequence: str, subjects: list | None = None) -> dict:
    """The edit of a sequence as it stands: each cut's camera and frames with the camera's lens and pose now (its
    first key's pose is what the cut opens on when scrubbed), the size it gives on `subjects`, and the stored spec
    hash.

    Example: film-ue op shot.describe sequence=/Game/Films/demo/Seq_Scene1 subjects=Presenter
    """
    if not EAL.does_asset_exist(sequence):
        raise not_found("level sequence", sequence, [], hint="shot.apply makes it from a shot spec")
    subs = cam._subjects(subjects)
    out = []
    for label, start, end in call("seq.cuts", path=sequence):
        row = {"camera": label, "start": start, "end": end}
        if cam._find(label) is not None and isinstance(cam._find(label), unreal.CineCameraActor):
            c = cam.read(label)
            row.update({"focal_mm": round(c["focal"], 2), "aperture": c["aperture"], "loc": c["loc"], "rot": c["rot"],
                        "sizes": {s["name"]: framing.classify(c, s)["size"] for s in subs}})
        out.append(row)
    st = _stored(sequence)
    return {"sequence": sequence, "cuts": out, "spec_hash": st.get("hash"), "cameras": st.get("cameras")}


def _cam_at(sequence: str, label: str, frame: int):
    """A camera's pose and lens as the sequence evaluates it at `frame` (scrub there, let it tick)."""
    LSE.set_current_time(int(frame))
    yield
    yield
    return cam.read(label)


@op("shot.check", mutates=False, idempotent=True, tags=["camera", "qa", "sequencer"])
def check(*, sequence: str, subjects: list, at: str = "start") -> dict:
    """Check a sequence's edit numerically: every shot's frame (cam.check: QA's framing plus focus, safe areas,
    dutch) at its start (or "middle"), and every cut (180-degree line, 30-degree rule). Scrubs the sequence: a
    multi-tick job.

    Returns: {"pass", "issues", "shots": [{"camera", "start", "end", "size"}]}.
    Example: film-ue op shot.check sequence=/Game/Films/demo/Seq_Scene1 'subjects=["Host","Guest"]'
    """
    seqobj = EAL.load_asset(sequence)
    if seqobj is None:
        raise not_found("level sequence", sequence, [])
    LSE.open_level_sequence(seqobj)
    cuts = call("seq.cuts", path=sequence)
    issues, rows, prev = [], [], None
    for label, start, end in cuts:
        f = start if at == "start" else (start + end) // 2
        c = yield from _cam_at(sequence, label, f)
        subs = cam._subjects(subjects)  # the pose at this frame
        r = cam.check(camera=label, subjects=subjects)
        issues += [{**i, "frame": f} for i in r["issues"]]
        rows.append({"camera": label, "start": start, "end": end,
                     "size": {s["name"]: framing.classify(c, s)["size"] for s in subs}})
        if prev is not None and prev[0] != label:
            pc = yield from _cam_at(sequence, prev[0], start - 1)
            yield from _cam_at(sequence, label, start)
            issues += ck.cut(pc, c, subs, names=(prev[0], label), at=start)
        prev = (label, start)
    return {"pass": ck.worst(issues) != "fail", "issues": issues, "shots": rows}


@op("shot.sheet", mutates=False, idempotent=True, tags=["camera", "qa", "gpu", "slow"])
def sheet(*, sequence: str, out_dir: str, per_shot: int = 1, cell_w: int = 480, cols: int = 4, guides: bool = True,
          title: str = ""):
    """A previz contact sheet of a sequence's edit: per shot 1 (its middle) or 3 (start, middle, end) stills
    through the cut's camera, with thirds and safe-frame guides and a label (shot, camera, frame, focal), in one PNG.
    A multi-tick job: about 2 s per still plus the drawing.

    Returns: {"path": the sheet, "width", "height", "stills": [[frame, camera, path]]}.
    Example: film-ue op shot.sheet sequence=/Game/Films/demo/Seq_Scene1 out_dir=/tmp/sheet per_shot=3
    """
    if not EAL.does_asset_exist(sequence):
        raise not_found("level sequence", sequence, [])
    cuts = call("seq.cuts", path=sequence)
    if not cuts:
        raise OpError(f"{sequence} has no camera cuts", code="failed", hint="shot.apply or seq.camera_cuts first")
    os.makedirs(out_dir, exist_ok=True)
    h = int(round(cell_w * 9 / 16))
    frames = []
    for k, (label, start, end) in enumerate(cuts):
        last = max(start, end - 1)
        picks = [(start + last) // 2] if per_shot <= 1 else [start + min(2, last - start), (start + last) // 2,
                                                             max(start, last - 2)]
        frames += [(k, label, f) for f in dict.fromkeys(picks)]
    imgs, labels, stills = [], [], []
    for k, label, f in frames:
        p = os.path.join(out_dir, f"{k:02d}_{label}_{f:05d}.png")
        yield from call("seq.still", path=sequence, frame=f, camera=label, out=p, width=cell_w, height=h, settle=12)
        img = png.read(p)
        if guides:
            png.guides(img, center=False)
        try:
            c = cam.read(label)
            lens_txt = f" {c['focal']:.0f}MM"
        except OpError:
            lens_txt = ""
        imgs.append(img)
        labels.append(f"{k + 1} {label} F{f}{lens_txt}")
        stills.append([f, label, p])
        yield
    sheet_img = png.contact_sheet(imgs, cols=cols, cell_w=cell_w, labels=labels,
                                  title=title or sequence.rsplit("/", 1)[-1])
    res = png.write(os.path.join(out_dir, "sheet.png"), sheet_img)
    return {**res, "stills": stills}
