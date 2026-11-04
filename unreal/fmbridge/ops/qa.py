"""QA checks Claude can read: numbers and issues about pictures, framing, meshes and continuity, and one REVIEW
that gathers them for a shot, a sequence, a set or a character.

Every check returns {"pass": bool, "issues": [...], "metrics": {...}} (docs/unreal/CONVENTIONS.md §8): `pass` is
false when an issue is a "fail". An issue is {"code", "severity", "message", "fix", "frame", "camera", "subject",
"box", "value", "expected"} with the box in 0..1 frame fractions. The arithmetic lives in fmbridge.qa (pure Python,
unit-tested); these ops gather what it needs from the editor (cameras, bones, bounds, captures).

    qa.image        exposure, clipping, colour cast, flat frames, per-subject focus/brightness of a PNG
    qa.compare      a PNG against a reference (SSIM, PSNR, where it differs, a diff heatmap)
    qa.framing      subjects in a camera: in frame, shot size, headroom, cuts at joints, feet, look room
    qa.penetration  body through garments, from depth captures (a camera, or views around the character)
    qa.floating     actors hovering above what is under them (line traces)
    qa.overlaps     actors interpenetrating (bounds)
    qa.snapshot     the level as JSON (to diff later)
    qa.diff         what changed between two snapshots (or a snapshot and now)
    qa.review       all of it for a sequence or a camera: review.json + review.png
"""
from __future__ import annotations

import json
import os

import unreal

from . import op
from ..errors import OpError
from ..qa import compare as _compare
from ..qa import continuity as _continuity
from ..qa import framing as _framing
from ..qa import geometry as _geometry
from ..qa import image as _image
from ..qa import metrics as _metrics
from ..qa import review as _review
from ..qa.issues import issue, worst
from .view import (RIG, _bounds, class_name, _eas, _rot, _world, _xyz, camera_info, capture, cut_camera, find_actor, read_pixels,
                   remove_rig, shot_frames, still, to_image)

# bones the framing check reads (UE5 mannequin / MetaHuman body skeleton); missing ones are skipped
BONES = sorted({"head", "neck_01", "neck_02", "spine_01", "spine_03", "spine_04", "spine_05", "pelvis", "thigh_l",
                "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r", "ball_l", "ball_r", "clavicle_l", "clavicle_r",
                "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r"})
EYES = ("FACIAL_L_Eye", "FACIAL_R_Eye")
BODY_PARTS = ("Body", "Face")                 # a MetaHuman's skin components
GARMENT_PARTS = ("Torso", "Legs", "Feet")     # ... and its clothing components
EMPTY_DEPTH = 1.0e7                           # depth (cm) at or beyond which a capture pixel holds nothing


def _result(issues: list, metrics: dict | None = None, **extra) -> dict:
    return {"pass": worst(issues) != "fail", "issues": issues, "metrics": metrics or {}, **extra}


def _skel_components(a) -> list:
    return list(a.get_components_by_class(unreal.SkeletalMeshComponent))


def _comp_name(c) -> str:
    return c.get_name()


def bones_of(label: str) -> tuple:
    """A character's bone positions {bone: [x,y,z]} from the skeletal component that has a pelvis/head (a
    MetaHuman's Body), the eyes from its Face when it has one; (bones, head_top or None)."""
    a = find_actor(label)
    comps = _skel_components(a)
    body = None
    for c in comps:
        if c.get_bone_index("head") >= 0 or c.get_bone_index("pelvis") >= 0:
            body = c
            break
    if body is None:
        return {}, None
    out = {}
    for b in BONES:
        if body.get_bone_index(b) >= 0:
            out[b] = _xyz(body.get_socket_location(b))
    head_top = None
    for c in comps:
        if all(c.get_bone_index(e) >= 0 for e in EYES):
            pts = [_xyz(c.get_socket_location(e)) for e in EYES]
            out["eyes"] = [(pts[0][k] + pts[1][k]) / 2 for k in range(3)]
            o, e, _ = unreal.SystemLibrary.get_component_bounds(c)
            if "head" in out:
                head_top = [out["head"][0], out["head"][1], float(o.z + e.z)]
            break
    if head_top:
        out["head_top"] = head_top
    return out, head_top


def _subject_points(label: str) -> dict:
    """{"bones": {...}} for a character, else {"bounds": (origin, extent)}."""
    bones, _ = bones_of(label)
    if bones:
        return {"bones": bones}
    return {"bounds": _bounds(find_actor(label))}


# --- image checks --------------------------------------------------------------------------------------------------

@op("qa.image", mutates=False, idempotent=True)
def image_check(*, image: str, subjects: dict | None = None, expect: dict | None = None, limits: dict | None = None,
                width_px: int = 480) -> dict:
    """Exposure, clipping, colour and focus of a PNG on the box, as numbers and issues.

    Args: image: PNG path. subjects: {name: [x0,y0,x1,y1]} boxes (0..1; qa.framing returns them) for per-subject
    brightness and focus. expect: intent, so a mood is not flagged: {"stops": [-3, -1]} mean exposure range in stops
    from mid grey, {"cast": "warm"|"cool"|"neutral"}. limits: override thresholds (fmbridge.qa.metrics.LIMITS).
    width_px: analysis size.
    Returns: {"pass", "issues", "metrics": {"exposure", "color", "regions", "subjects", "size"}}.
    Example: film-ue op qa.image image=/tmp/qa/a.png 'expect={"stops":[-2,0]}'
    """
    if not os.path.isfile(image):
        raise OpError(f"no image at {image}", code="not_found", hint="make one with view.still")
    r = _metrics.analyze(_image.read(image), subjects=subjects, limits=limits, width=width_px, expect=expect)
    iss = r.pop("issues")
    return _result(iss, r)


@op("qa.exposure", mutates=False, idempotent=True)
def exposure(*, image: str, target_stops: list | None = None, regions: dict | None = None) -> dict:
    """Exposure of a PNG: histogram, luma mean/median/percentiles, clipped and crushed %, stops from mid grey, per
    region, and a verdict against a target range.

    Args: image: PNG path. target_stops: [lo, hi] the mean should land in (stops from 18% grey; default -2.5..+1.5).
    regions: {name: [x0,y0,x1,y1]} (0..1) measured separately, e.g. a face box from qa.framing.
    Returns: {"pass", "issues", "metrics": {"exposure", "histogram" (32 bins of luma), "regions"}}.
    Example: film-ue op qa.exposure image=/tmp/qa/a.png 'target_stops=[-2,-0.5]'
    """
    if not os.path.isfile(image):
        raise OpError(f"no image at {image}", code="not_found", hint="make one with view.still")
    img = _image.fit(_image.read(image), 480)
    r = _metrics.analyze(img, subjects=regions, expect={"stops": target_stops} if target_stops else None)
    iss = [i for i in r["issues"] if i["code"].startswith(("exposure.", "image."))]
    return _result(iss, {"exposure": r["exposure"], "histogram": _metrics.histogram(img, bins=32),
                         "regions": {k: {x: v[x] for x in ("box", "mean", "stops", "clipped_high_pct", "clipped_low_pct")}
                                     for k, v in (r["subjects"] or r["regions"]).items()}})


@op("qa.compare", mutates=True, idempotent=True)
def compare(*, image: str, reference: str, out_diff: str = "", min_ssim: float = 0.9, width_px: int = 480,
            grid: list | None = None) -> dict:
    """A PNG against a reference PNG: SSIM, PSNR, which cells changed, mean colour shift, and a diff heatmap.

    Args: image, reference: PNG paths (same aspect; sizes may differ). out_diff: write the heatmap there ("" skips).
    min_ssim: below this the check fails/warns. width_px: compare size. grid: [cols, rows] for the change map.
    Returns: {"pass", "issues", "metrics": {"ssim", "psnr", "grid", "changed", "mean_shift", "verdict"},
    "diff"?: path}.
    Example: film-ue op qa.compare image=/tmp/qa/new/00048.png reference=/tmp/qa/ref/00048.png out_diff=/tmp/qa/d.png
    """
    for p in (image, reference):
        if not os.path.isfile(p):
            raise OpError(f"no image at {p}", code="not_found")
    a, b = _image.read(image), _image.read(reference)
    cols, rows = (grid or [4, 3])[:2]
    try:
        r = _compare.against_reference(a, b, name=os.path.basename(image), min_ssim=min_ssim, width=width_px,
                                       cols=int(cols), rows=int(rows))
    except ValueError as e:
        raise OpError(str(e), code="bad_args") from None
    extra = {}
    if out_diff:
        A, B = _compare._same(b, a, width_px)
        _image.write(_compare.diff_image(A, B), out_diff)
        extra["diff"] = out_diff
    iss = r.pop("issues")
    return _result(iss, r, **extra)


# --- framing -------------------------------------------------------------------------------------------------------

def _expect_for(expect: dict, subject: str, subjects) -> dict:
    """`expect` is either per subject ({"Ada": {...}}) or one intent for all ({"size": "MS"})."""
    expect = expect or {}
    if any(k in subjects for k in expect):
        return expect.get(subject) or {}
    return expect


def _framing_one(cam_info: dict, subjects: list, expect: dict, frame=None) -> tuple:
    cam = _framing.Camera.from_dict(cam_info)
    per, issues = {}, []
    for s in subjects:
        pts = _subject_points(s)
        r = _framing.check(cam, s, frame=frame, expect=_expect_for(expect, s, subjects), **pts)
        issues += r.pop("issues")
        per[s] = r
    return per, issues


@op("qa.framing", mutates=False, idempotent=True)
def framing(*, subjects: list, camera: str = "", sequence: str = "", frame: int | None = None,
            expect: dict | None = None, width_px: int = 1920, height_px: int = 1080, still_out: str = "") -> dict:
    """How subjects sit in a camera's frame, measured from their bones (characters) or bounds (anything else).

    Args: subjects: actor labels. camera: a camera label; "" with sequence+frame: the cut's camera at that frame
    (the sequence is scrubbed there first so animated cameras and bodies are where the shot has them).
    expect: intent per subject or for all: {"size": "MCU"|["MS","MCU"], "headroom": [lo, hi], "side":
    "left"|"right"|"center", "in_frame": 1.0}, or {"Ada": {...}, "Ben": {...}}. width_px/height_px: the output
    aspect. still_out: also capture a still there with each subject's box and the problems drawn.
    Returns: {"pass", "issues", "metrics": {"camera", "subjects": {label: {size, box, headroom, eyes, looks,
    look_room}}}, "still"?}. Multi-tick when sequence or still_out is given.
    Example: film-ue op qa.framing 'subjects=["Ada"]' camera=CamA 'expect={"size":"MCU"}'
    """
    if not subjects:
        raise OpError("give subjects=[actor labels]", code="bad_args")
    if sequence:
        if frame is None:
            raise OpError("sequence needs frame", code="bad_args")
        camera = camera or cut_camera(sequence, frame)
        from .view import _scrub
        yield from _scrub(sequence, frame, 10)
    info = camera_info(camera, aspect=width_px / height_px)
    per, issues = _framing_one(info, subjects, expect or {}, frame)
    extra = {}
    if still_out:
        r = yield from still(out=still_out, camera=camera, width_px=min(width_px, 1280),
                             height_px=round(min(width_px, 1280) * height_px / width_px))
        boxes = [{"box": v["box"], "label": k, "color": "subject"} for k, v in per.items() if v.get("box")]
        from ..qa.overlay import overlay
        ann = overlay(_image.read(r["path"]), guides=["thirds"], boxes=boxes + [
            {"box": i["box"], "label": i["code"].split(".")[-1], "color": i["severity"]} for i in issues if i.get("box")])
        _image.write(ann, still_out)
        extra["still"] = still_out
    return _result(issues, {"camera": {k: v for k, v in info.items() if k != "post"}, "subjects": per}, **extra)


# --- meshes --------------------------------------------------------------------------------------------------------

def _parts(a, names, kind: str) -> list:
    """Components of `a` by name; a name that is no component of `a` but another actor's label stands for all of
    that actor's primitives (a skin and a cloth as separate actors, or a test rig)."""
    comps = {_comp_name(c): c for c in a.get_components_by_class(unreal.PrimitiveComponent)}
    got = []
    for n in names:
        if n in comps:
            got.append(comps[n])
            continue
        other = next((x for x in _eas().get_all_level_actors() if x.get_actor_label() == n), None)
        if other is not None:
            got += list(other.get_components_by_class(unreal.PrimitiveComponent))
    if not got:
        raise OpError(f"{a.get_actor_label()} has none of the {kind} components {list(names)}", code="not_found",
                      candidates=sorted(comps)[:12], hint=f"pass {kind}=[component names] (qa.parts lists them)")
    return got


@op("qa.parts", mutates=False, idempotent=True)
def parts(*, label: str) -> dict:
    """An actor's primitive components (names, classes, meshes, bounds): what to pass as body/garments.

    Returns: {"label", "components": [{"name", "class", "mesh", "visible", "bounds": [origin, extent]}]}.
    Example: film-ue op qa.parts label=Ada
    """
    a = find_actor(label)
    out = []
    for c in a.get_components_by_class(unreal.PrimitiveComponent):
        mesh = None
        if isinstance(c, unreal.SkeletalMeshComponent):
            m = c.get_skeletal_mesh_asset()
            mesh = m.get_path_name() if isinstance(m, unreal.Object) else None
        elif isinstance(c, unreal.StaticMeshComponent):
            m = c.get_editor_property("static_mesh")
            mesh = m.get_path_name() if isinstance(m, unreal.Object) else None
        o, e, _ = unreal.SystemLibrary.get_component_bounds(c)
        out.append({"name": c.get_name(), "class": class_name(c), "mesh": mesh, "visible": bool(c.is_visible()),
                    "bounds": [_xyz(o), _xyz(e)]})
    return {"label": label, "components": out}


@op("qa.penetration", mutates=False, idempotent=True, tags=["gpu"])
def penetration(*, label: str, body: list | None = None, garments: list | None = None, camera: str = "",
                sequence: str = "", frame: int | None = None, views: int = 0, elevation_deg: float = 5.0,
                size_px: int = 256, tolerance_cm: float = 0.3, out_dir: str = "") -> dict:
    """Body showing through clothes, measured as the viewer would see it: two depth captures from each view (the
    body parts alone, the garments alone); where a garment covers a pixel and the body is nearer by more than
    `tolerance_cm`, skin pokes through.

    Args: label: the character. body/garments: component names (default a MetaHuman's Body+Face / Torso+Legs+Feet;
    qa.parts lists them), or labels of other actors whose meshes form that layer. camera: look from this camera (with sequence+frame: the shot's camera and pose); views: N
    views around the character instead (or as well), at elevation_deg. size_px: capture size (square for views;
    the camera's aspect otherwise). out_dir: write a still per view with the penetrating pixels painted magenta.
    Returns: {"pass", "issues", "metrics": {"views": {name: {fraction, pixels, worst_cm, box}}, "worst_fraction"}}.
    Multi-tick.
    Example: film-ue op qa.penetration label=Ada views=6 out_dir=/tmp/qa/pen
    """
    a = find_actor(label)
    bparts = _parts(a, body or BODY_PARTS, "body")
    gparts = _parts(a, garments or [n for n in GARMENT_PARTS], "garments")
    if sequence:
        if frame is None:
            raise OpError("sequence needs frame", code="bad_args")
        camera = camera or cut_camera(sequence, frame)
        from .view import _scrub
        yield from _scrub(sequence, frame, 10)
    cams = []
    if camera:
        info = camera_info(camera, aspect=16 / 9)
        cams.append((camera, info, size_px, max(1, round(size_px * 9 / 16))))
    if views or not camera:
        n = views or 6
        centre, ext = _bounds(a)
        import math
        radius = math.sqrt(sum(e * e for e in ext)) or 100.0
        dist = 1.1 * radius / math.sin(math.radians(15))
        for k in range(n):
            yaw = 360.0 * k / n
            el = math.radians(elevation_deg)
            loc = [centre[0] + dist * math.cos(el) * math.cos(math.radians(yaw)),
                   centre[1] + dist * math.cos(el) * math.sin(math.radians(yaw)), centre[2] + dist * math.sin(el)]
            cams.append((f"yaw{yaw:03.0f}", {"name": f"yaw{yaw:03.0f}", "loc": loc, "rot": _framing.look_at(loc, centre),
                                            "fov": 30.0, "aspect": 1.0, "post": None}, size_px, size_px))
    per, issues, worst_f = {}, [], 0.0
    try:
        for name, info, w, h in cams:
            rt = yield from capture(info, w, h, "depth", show_only=bparts, warmup=1)
            bd = read_pixels(rt, "r")[0]
            rt = yield from capture(info, w, h, "depth", show_only=gparts, warmup=1)
            gd = read_pixels(rt, "r")[0]
            r = _geometry.penetration(bd, gd, w, h, tolerance_cm, EMPTY_DEPTH)
            if r["garment_pixels"] == 0:
                issues.append(issue("mesh.garments_not_seen", "info", f"no garment pixels from {name}: the garments are "
                                    "hidden, outside the view or not rendered by a scene capture", subject=label,
                                    camera=name))
            issues += _geometry.penetration_issues(r, label, view=name, frame=frame, camera=name)
            worst_f = max(worst_f, r["fraction"])
            per[name] = {k: r[k] for k in ("fraction", "pixels", "garment_pixels", "worst_cm", "box")}
            if out_dir:
                rt = yield from capture(info, w, h, "final", show_only=[a], warmup=2)
                pic = _geometry.mask_overlay(to_image(rt), r["mask"])
                p = os.path.join(out_dir, f"penetration_{name}.png")
                _image.write(pic, p)
                per[name]["still"] = p
    finally:
        remove_rig()
    return _result(issues, {"views": per, "worst_fraction": worst_f})


def _mesh_actors(labels=None, ignore=()) -> dict:
    """Actors to check: given labels, or every visible actor with a static or skeletal mesh (not the QA rig)."""
    out = {}
    if labels:
        for lab in labels:
            out[lab] = find_actor(lab)
        return out
    for a in _eas().get_all_level_actors():
        lab = a.get_actor_label()
        if lab == RIG or lab in ignore or a.is_hidden_ed():
            continue
        if list(a.get_components_by_class(unreal.StaticMeshComponent)) or _skel_components(a):
            out[lab] = a
    return out


@op("qa.floating", mutates=False, idempotent=True)
def floating(*, labels: list | None = None, ignore: list | None = None, tolerance_cm: float = 1.0,
             max_check_cm: float = 500.0) -> dict:
    """Actors hovering above the surface under them: a line trace down from the bottom of each one's bounds (its
    own collision ignored) measures the gap.

    Args: labels: the actors (default every visible mesh actor). ignore: labels to skip (things meant to hang:
    lamps, pictures). tolerance_cm: a gap over this is floating. max_check_cm: how far down to look.
    Returns: {"pass", "issues", "metrics": {"gaps": {label: cm or None}}}. Needs collision on what is underneath
    (an object over a floor without collision reads as unsupported).
    Example: film-ue op qa.floating 'ignore=["Pendant"]'
    """
    acts = _mesh_actors(labels, set(ignore or []))
    items, ground = {}, {}
    world = _world()
    for lab, a in acts.items():
        o, e = _bounds(a)
        items[lab] = (o, e)
        best = None
        for dx, dy in ((0, 0), (-0.6, -0.6), (0.6, -0.6), (-0.6, 0.6), (0.6, 0.6)):
            start = unreal.Vector(o[0] + dx * e[0], o[1] + dy * e[1], o[2] - e[2] + 2.0)
            end = unreal.Vector(start.x, start.y, start.z - max_check_cm)
            hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                         True, [a], unreal.DrawDebugTrace.NONE, True)
            if hit is None or _hit_tuple(hit)[1]:  # nothing, or it starts inside something (overlap: qa.overlaps)
                continue
            d = float(_hit_tuple(hit)[3]) - 2.0
            best = d if best is None else min(best, d)
        ground[lab] = best
    r = _geometry.floating(items, ground, tolerance_cm, max_check_cm)
    return _result(r["issues"], {"gaps": r["gaps"]})


def _hit_tuple(hit) -> tuple:
    """A HitResult's fields in BreakHitResult order: blocking, initial_overlap, time, distance, location, ..."""
    try:
        return tuple(hit.to_tuple())
    except AttributeError:
        return tuple(unreal.GameplayStatics.break_hit_result(hit))


@op("qa.overlaps", mutates=False, idempotent=True)
def overlaps(*, labels: list | None = None, ignore: list | None = None, ignore_pairs: list | None = None,
             min_fraction: float = 0.05, touching_cm: float = 1.0) -> dict:
    """Actors whose bounds interpenetrate (a chair sunk into a table, two props in one place).

    Args: labels: the actors (default every visible mesh actor). ignore: labels to skip (the floor, walls, the
    set's shell). ignore_pairs: [[a, b]] that may overlap (a book on a shelf). min_fraction: the share of the
    smaller box that counts. touching_cm: resting contact allowed.
    Returns: {"pass", "issues", "metrics": {"pairs": [[a, b, fraction, depth_cm]]}}. Axis-aligned bounds: confirm a hit
    with a still.
    Example: film-ue op qa.overlaps 'ignore=["Floor","Walls"]'
    """
    acts = _mesh_actors(labels, set(ignore or []))
    items = {lab: _bounds(a) for lab, a in acts.items()}
    r = _geometry.overlaps(items, min_fraction, [tuple(p) for p in ignore_pairs or []], touching_cm)
    return _result(r["issues"], {"pairs": r["pairs"]})


# --- continuity ----------------------------------------------------------------------------------------------------

def _props(a) -> dict:
    out = {}
    for comp_cls, keys in ((unreal.LightComponent, ("intensity", "light_color", "temperature", "use_temperature")),
                           (unreal.CineCameraComponent, ("current_focal_length", "current_aperture"))):
        for c in a.get_components_by_class(comp_cls):
            for k in keys:
                try:
                    v = c.get_editor_property(k)
                except Exception:
                    continue
                if isinstance(v, (unreal.LinearColor, unreal.Color)):
                    v = [float(v.r), float(v.g), float(v.b)]
                elif not isinstance(v, (bool, int, float, str)):
                    continue  # not a plain value: not worth diffing
                out[k] = v
            break
    return out


@op("qa.snapshot", mutates=False, idempotent=True)
def snapshot(*, out: str = "", labels: list | None = None) -> dict:
    """The level's state as JSON for later diffs: every actor's class, transform, bounds, visibility, materials,
    meshes, light and lens settings.

    Args: out: also write it to this file. labels: only these actors.
    Returns: {"actors": {label: {class, loc, rot, scale, bounds, hidden, mesh, materials, props}}, "meta"}.
    Example: film-ue op qa.snapshot out=/tmp/qa/before.json
    """
    want = set(labels or [])
    acts = {}
    for a in _eas().get_all_level_actors():
        lab = a.get_actor_label()
        if lab == RIG or (want and lab not in want):
            continue
        o, e = _bounds(a)
        mats, meshes = [], []
        for c in a.get_components_by_class(unreal.MeshComponent):
            mats += [m.get_path_name() if isinstance(m, unreal.Object) else None for m in c.get_materials()]
            m = (c.get_skeletal_mesh_asset() if isinstance(c, unreal.SkeletalMeshComponent)
                 else c.get_editor_property("static_mesh") if isinstance(c, unreal.StaticMeshComponent) else None)
            if isinstance(m, unreal.Object):
                meshes.append(m.get_path_name())
        s = a.get_actor_scale3d()
        acts[lab] = {"class": class_name(a), "loc": _xyz(a.get_actor_location()),
                     "rot": _rot(a.get_actor_rotation()), "scale": _xyz(s), "bounds": [o, e],
                     "hidden": bool(a.is_hidden_ed()), "mesh": meshes, "materials": mats, "props": _props(a)}
    snap = {"actors": acts, "meta": {"engine": unreal.SystemLibrary.get_engine_version(), "count": len(acts)}}
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w") as f:
            json.dump(snap, f, indent=1)
    return snap


@op("qa.diff", mutates=False, idempotent=True)
def diff(*, before: str, after: str = "", ignore: list | None = None, severity: str = "info",
         tolerance: dict | None = None) -> dict:
    """What changed between two snapshots (files from qa.snapshot), or between one and the level now.

    Args: before: snapshot path. after: snapshot path ("" = now). ignore: labels or prefixes ("Light*") to skip.
    severity: "info" when versions are expected to differ, "warn" when they should match. tolerance: {"loc_cm",
    "rot_deg", "scale", "prop"}.
    Returns: {"pass", "issues", "metrics": {"added", "removed", "changed", "summary"}}.
    Example: film-ue op qa.diff before=/tmp/qa/before.json 'ignore=["FMQA_*"]'
    """
    def load(p):
        if not os.path.isfile(p):
            raise OpError(f"no snapshot at {p}", code="not_found", hint="write one with qa.snapshot out=...")
        with open(p) as f:
            return json.load(f)
    a = load(before)
    b = load(after) if after else snapshot()
    r = _continuity.diff(a, b, tolerance, ignore or (), severity)
    iss = r.pop("issues")
    return _result(iss, r)


# --- the review ----------------------------------------------------------------------------------------------------

CHECKS = ("image", "framing", "penetration", "floating", "overlaps", "continuity", "reference")


def _default_subjects() -> list:
    return [a.get_actor_label() for a in _eas().get_all_level_actors()
            if a.get_actor_label() != RIG and not a.is_hidden_ed() and any(
                c.get_bone_index("head") >= 0 for c in _skel_components(a))]


@op("qa.review", mutates=True, idempotent=True, tags=["gpu", "slow"])
def review(*, out_dir: str, sequence: str = "", frames: list | None = None, per_shot: int = 2, camera: str = "",
           subjects: list | None = None, expect: dict | None = None, checks: list | None = None,
           reference_dir: str = "", width_px: int = 960, height_px: int = 540, mode: str = "capture",
           ignore: list | None = None, title: str = "", level: str = "") -> dict:
    """Everything wrong with a shot, a sequence or a set, in one JSON and one picture.

    For each frame (sequence: `frames`, or `per_shot` per camera cut; no sequence: one still through `camera`) it
    takes a still, measures exposure and colour, frames every subject (headroom, cuts, size), compares with
    `reference_dir`/{frame:05d}.png when given, and (with "penetration") checks garments from the shot's camera;
    once for the scene it checks floating and overlapping props; across cuts it checks exposure/colour continuity.

    Args: out_dir: where frames, review.json and review.png go. sequence/frames/per_shot/camera: what to look at.
    subjects: characters/props to frame (default every visible character). expect: per-subject or global intent
    for qa.framing, plus {"image": {...}} for qa.image (e.g. {"image": {"stops": [-3,-1]}}). checks: a subset of
    image, framing, penetration, floating, overlaps, continuity, reference (default all but penetration).
    ignore: labels skipped by floating/overlaps (floor, walls). mode: still mode (view.still).
    Returns: {"pass", "verdict", "counts", "summary": [lines, worst first], "issues", "metrics": {"frames"},
    "report": review.json path, "image": review.png path}. Multi-tick; ~1 s a frame with mode=capture.
    Example: film-ue op qa.review sequence=/Game/Seq/S010 out_dir=/tmp/qa/s010 per_shot=2
    """
    todo = set(checks or [c for c in CHECKS if c != "penetration"])
    bad = todo - set(CHECKS)
    if bad:
        raise OpError(f"unknown checks {sorted(bad)}: use {CHECKS}", code="bad_args")
    if not sequence and not camera:
        raise OpError("give sequence= (review its cut) or camera= (review the level from it)", code="bad_args")
    expect = dict(expect or {})
    img_expect = expect.pop("image", None)
    subjects = subjects if subjects is not None else _default_subjects()
    os.makedirs(out_dir, exist_ok=True)
    if sequence:
        frames = [int(f) for f in (frames or shot_frames(sequence, per_shot))]
    else:
        frames = [None]
    panels, prev, per_frame = [], None, {}
    for f in frames:
        p = os.path.join(out_dir, f"{f:05d}.png" if f is not None else "still.png")
        cam_label = camera or (cut_camera(sequence, f) if sequence else "")
        r = yield from still(out=p, camera=cam_label, sequence=sequence, frame=f, width_px=width_px,
                             height_px=height_px, mode=mode, level=level)
        info = camera_info(cam_label, aspect=width_px / height_px)
        iss, boxes, metrics = [], [], {"camera": cam_label}
        fr_subj = {}
        if "framing" in todo and subjects:
            per, fi = _framing_one(info, subjects, expect, f)
            iss += fi
            metrics["framing"] = per
            for k, v in per.items():
                if v.get("box"):
                    fr_subj[k] = v["box"]
                    boxes.append({"box": v["box"], "label": k, "color": "subject"})
        img = _image.read(p)
        an = None
        if "image" in todo or "continuity" in todo:
            an = _metrics.analyze(img, subjects=fr_subj or None, expect=img_expect)
            if "image" in todo:
                iss += an["issues"]
            metrics["exposure"] = an["exposure"]
            metrics["color"] = {k: an["color"][k] for k in ("mean_rgb", "name", "cast_toward", "cast_amount")}
        if "reference" in todo and reference_dir:
            ref = os.path.join(reference_dir, os.path.basename(p))
            if os.path.isfile(ref):
                cr = _compare.against_reference(img, _image.read(ref), name=os.path.basename(p))
                iss += cr["issues"]
                metrics["reference"] = {"ssim": cr["ssim"], "psnr": cr["psnr"], "verdict": cr["verdict"]}
            else:
                iss.append(issue("compare.no_reference", "info", f"no reference {ref}"))
        if "penetration" in todo:
            for s in subjects:
                try:
                    pr = yield from penetration(label=s, camera=cam_label, size_px=384)
                except OpError as e:
                    iss.append(issue("mesh.penetration_skipped", "info", f"{s}: {e.message}", subject=s))
                    continue
                iss += pr["issues"]
        if "continuity" in todo and prev is not None and an is not None and prev[1] != cam_label:
            iss += [dict(i, frame=f) for i in _continuity.frames(prev[0], an, name=f"cut {prev[2]} -> {f}:")]
        if an is not None:
            prev = (an, cam_label, f)
        per_frame[str(f)] = metrics
        panels.append({"image": p, "frame": f, "camera": cam_label, "issues": iss, "boxes": boxes,
                       "label": f"{f if f is not None else ''} {cam_label}".strip()})
        yield
    scene = []
    if "floating" in todo:
        scene += floating(ignore=ignore)["issues"]
    if "overlaps" in todo:
        scene += overlaps(ignore=ignore)["issues"]
    rep = _review.build(panels, out_dir, title=title or (sequence.rsplit("/", 1)[-1] if sequence else cam_label),
                        scene_issues=scene, extra={"sequence": sequence, "frames": frames})
    return {"pass": rep["verdict"] != "fail", "verdict": rep["verdict"], "counts": rep["counts"],
            "summary": rep["summary"], "issues": rep["issues"], "metrics": {"frames": per_frame},
            "report": rep["json"], "image": rep["image"], "changed": True}
