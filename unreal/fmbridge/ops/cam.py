"""Cameras: cine cameras by label (filmback, lens, aperture, focus), the framing solver on real subjects, camera
moves keyed into Sequencer, rail and crane rigs, a scene's coverage, framing feedback (where points land in the
frame, optics and cut checks, stills with guides).

The maths is fmbridge.camkit (pure Python, unit-tested without an engine): this module reads the level into it and
writes its answers back. Sequencer data goes through WP8's seq ops only (`_seq`), so one adapter changes if they do.

Units: cm, degrees, frames at the sequence's rate; focal lengths `focal_mm`, sensors `sensor_mm` [w, h]; frame
positions u, v are 0..1 of the picture from its top left. A subject is an actor label (its skeleton gives head, eyes,
chest, waist, knees, feet; any other actor is framed from its bounds), or a point.
"""
from __future__ import annotations


import unreal

from . import call, op
from ..camkit import checks as ck
from ..camkit import coverage as cov
from ..camkit import framing, geo, lens, moves
from ..camkit import png
from ..errors import OpError, not_found
from ._util import eas, find_actor, rot, vec

EAS = eas
MANUAL, TRACKING, DISABLE = "MANUAL", "TRACKING", "DISABLE"


# --- reading and writing cameras --------------------------------------------------------------------------------

def _labels(cls=None) -> list:
    out = []
    for a in EAS().get_all_level_actors():
        if cls is None or isinstance(a, cls):
            out.append(a.get_actor_label())
    return out


def _find(label: str):
    return find_actor(label)


def _cine(label: str):
    """The CineCameraActor labelled `label`, or an OpError naming the cine cameras there are."""
    a = _find(label)
    if a is None:
        raise not_found("cine camera", label, _labels(unreal.CineCameraActor),
                        hint="make one with cam.add, list them with cam.describe")
    if not isinstance(a, unreal.CineCameraActor):
        raise OpError(f"{label!r} is a {_cls(a)}, not a CineCameraActor", code="conflict",
                      hint="remove it (level.delete) or pick another label")
    return a


def _cls(a) -> str:
    try:
        return a.get_class().get_name()
    except TypeError:  # the unit tests' fake returns a Python class
        return type(a).__name__


def _comp(a):
    return a.get_cine_camera_component()


def _v3(v) -> list:
    return [float(v.x), float(v.y), float(v.z)]


def _r3(r) -> dict:
    return {"pitch": float(r.pitch), "yaw": float(r.yaw), "roll": float(r.roll)}


def _enum_name(e) -> str:
    s = str(getattr(e, "name", e))
    return s.split(".")[-1].upper()


def read(label: str) -> dict:
    """A camera as camkit's dict, plus what the engine says (fields of view, focus method, lens limits)."""
    a = _cine(label)
    c = _comp(a)
    fb = c.get_editor_property("filmback")
    ls = c.get_editor_property("lens_settings")
    fs = c.get_editor_property("focus_settings")
    method = _enum_name(fs.get_editor_property("focus_method"))
    sensor = [float(fb.get_editor_property("sensor_width")), float(fb.get_editor_property("sensor_height"))]
    loc, r = _v3(a.get_actor_location()), _r3(a.get_actor_rotation())
    focal, ap = float(c.get_editor_property("current_focal_length")), float(c.get_editor_property("current_aperture"))
    out = {"label": label, "loc": loc, "rot": r, "focal": focal, "filmback": sensor, "aperture": ap,
           "focus": float(fs.get_editor_property("manual_focus_distance")) if method == MANUAL else None,
           "focus_method": method.lower(), "filmback_preset": lens.filmback_name(sensor),
           "lens": {"min_focal_mm": float(ls.get_editor_property("min_focal_length")),
                    "max_focal_mm": float(ls.get_editor_property("max_focal_length")),
                    "min_fstop": float(ls.get_editor_property("min_f_stop")),
                    "max_fstop": float(ls.get_editor_property("max_f_stop"))},
           "hfov_deg": round(lens.hfov(focal, sensor), 4), "vfov_deg": round(lens.vfov(focal, sensor), 4)}
    if method == TRACKING:
        tr = fs.get_editor_property("tracking_focus_settings")
        tgt = tr.get_editor_property("actor_to_track")
        out["focus_track"] = {"actor": tgt.get_actor_label() if tgt else None,
                              "offset": _v3(tr.get_editor_property("relative_offset"))}
    parent = a.get_attach_parent_actor()
    out["attached_to"] = parent.get_actor_label() if parent else None
    return out


def _close(a, b, tol=1e-3) -> bool:
    if isinstance(a, dict):
        return all(_close(a[k], b.get(k, 0.0), tol) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_close(x, y, tol) for x, y in zip(a, b))
    return abs(float(a) - float(b)) <= tol


def _set_lens(a, focal_mm=None, aperture=None, sensor_mm=None, lens_preset=None) -> bool:
    """Lens and filmback on a camera, widening its lens limits when a value is outside them (the engine clamps
    CurrentFocalLength and CurrentAperture to LensSettings: CineCameraComponent.cpp:528-529)."""
    c = _comp(a)
    changed = False
    if lens_preset:
        mn, mx, fmin, fmax, blades = lens.lens(lens_preset)
        ls = c.get_editor_property("lens_settings")
        for k, v in (("min_focal_length", mn), ("max_focal_length", mx), ("min_f_stop", fmin), ("max_f_stop", fmax),
                     ("diaphragm_blade_count", blades)):
            ls.set_editor_property(k, v)
        c.set_editor_property("lens_settings", ls)
        changed = True
    if sensor_mm is not None:
        w, h = lens.filmback(sensor_mm)
        fb = c.get_editor_property("filmback")
        if not _close([fb.get_editor_property("sensor_width"), fb.get_editor_property("sensor_height")], [w, h]):
            fb.set_editor_property("sensor_width", w)
            fb.set_editor_property("sensor_height", h)
            c.set_editor_property("filmback", fb)
            changed = True
    ls = c.get_editor_property("lens_settings")
    widen = False
    if focal_mm is not None:
        f = float(focal_mm)
        if f < float(ls.get_editor_property("min_focal_length")):
            ls.set_editor_property("min_focal_length", f)
            widen = True
        if f > float(ls.get_editor_property("max_focal_length")):
            ls.set_editor_property("max_focal_length", f)
            widen = True
    if aperture is not None:
        n = float(aperture)
        if n < float(ls.get_editor_property("min_f_stop")):
            ls.set_editor_property("min_f_stop", n)
            widen = True
        if n > float(ls.get_editor_property("max_f_stop")):
            ls.set_editor_property("max_f_stop", n)
            widen = True
    if widen:
        c.set_editor_property("lens_settings", ls)
        changed = True
    if focal_mm is not None and not _close(c.get_editor_property("current_focal_length"), focal_mm):
        c.set_editor_property("current_focal_length", float(focal_mm))
        changed = True
    if aperture is not None and not _close(c.get_editor_property("current_aperture"), aperture):
        c.set_editor_property("current_aperture", float(aperture))
        changed = True
    return changed


def _set_focus(a, method: str, distance_cm=None, track=None, offset=(0.0, 0.0, 0.0), smooth_speed=None) -> bool:
    c = _comp(a)
    fs = c.get_editor_property("focus_settings")
    before = (_enum_name(fs.get_editor_property("focus_method")),
              float(fs.get_editor_property("manual_focus_distance") or 0.0))
    fs.set_editor_property("focus_method", getattr(unreal.CameraFocusMethod, method))
    if method == MANUAL and distance_cm is not None:
        fs.set_editor_property("manual_focus_distance", float(distance_cm))
    if method == TRACKING:
        tr = fs.get_editor_property("tracking_focus_settings")
        tr.set_editor_property("actor_to_track", track)
        tr.set_editor_property("relative_offset", vec(offset))
        fs.set_editor_property("tracking_focus_settings", tr)
    if smooth_speed is not None:
        fs.set_editor_property("smooth_focus_changes", float(smooth_speed) > 0)
        fs.set_editor_property("focus_smoothing_interp_speed", float(smooth_speed))
    c.set_editor_property("focus_settings", fs)
    return method == TRACKING or before != (method, float(distance_cm if distance_cm is not None else before[1]))


def _place(a, loc=None, rotation=None) -> bool:
    changed = False
    if loc is not None and not _close(_v3(a.get_actor_location()), loc, 1e-2):
        a.set_actor_location(vec(loc), False, False)
        changed = True
    if rotation is not None and not _close(_r3(a.get_actor_rotation()), geo.as_rot(rotation), 1e-3):
        a.set_actor_rotation(rot(rotation), False)
        changed = True
    return changed


def _ensure(label: str):
    """The camera labelled `label`, made when missing: (actor, made)."""
    a = _find(label)
    if a is not None:
        if not isinstance(a, unreal.CineCameraActor):
            raise OpError(f"{label!r} exists and is a {_cls(a)}, not a cine camera", code="conflict",
                          hint="pick another label, or level.delete it first")
        return a, False
    a = EAS().spawn_actor_from_class(unreal.CineCameraActor, unreal.Vector(0.0, 0.0, 0.0),
                                     unreal.Rotator(roll=0.0, pitch=0.0, yaw=0.0))
    if a is None:
        raise OpError(f"the engine did not spawn a CineCameraActor for {label!r}", code="engine",
                      hint="is a level open? level.open")
    a.set_actor_label(label)
    return a, True


# --- subjects ---------------------------------------------------------------------------------------------------

def _bones_of(a) -> dict:
    """World positions of the landmark bones any skeletal mesh component of the actor has (MetaHuman: body + face)."""
    out = {}
    for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
        for b in framing.ALL_BONES:
            if b in out:
                continue
            try:
                if c.does_socket_exist(b):
                    out[b] = _v3(c.get_socket_location(b))
            except Exception:
                continue
    return out


def subject(target, mode: str = "auto", facing=None, top_z=None, name: str | None = None) -> dict:
    """A framing subject from an actor label (bones, else bounds), "Label:Component:bone" (a point), or a point."""
    if isinstance(target, dict) and "points" in target:
        return target
    if isinstance(target, (list, tuple)):
        p = geo.v(target)
        return framing.make_subject(name or "point", {k: p for k in framing.LANDMARKS}, facing or (1, 0, 0))
    label = str(target)
    a = _find(label.split(":")[0])
    if a is None:
        raise not_found("actor", label, _labels(), hint="subjects are actor labels (level.actors lists them)")
    fwd = _v3(a.get_actor_forward_vector())
    if mode in ("auto", "bones"):
        bones = _bones_of(a)
        if "head" in bones or "Head" in bones:
            return framing.subject_from_bones(name or label, bones, top_z=top_z, facing=facing)
        if mode == "bones":
            raise OpError(f"{label!r} has no skeleton with a head bone", code="not_found",
                          hint="use mode='bounds' for props and non-human figures")
    origin, extent = a.get_actor_bounds(False)
    s = framing.subject_from_bounds(name or label, _v3(origin), _v3(extent), facing or fwd)
    s["from"] = "bounds"
    return s


def _subjects(subjects, mode="auto") -> list:
    if subjects is None:
        return []
    if isinstance(subjects, (str, dict)) or (isinstance(subjects, (list, tuple)) and subjects and
                                             isinstance(subjects[0], (int, float))):
        subjects = [subjects]
    return [subject(s, mode) for s in subjects]


# --- ops --------------------------------------------------------------------------------------------------------

@op("cam.presets", mutates=False, idempotent=True, tags=["camera"])
def presets() -> dict:
    """The filmback and lens presets (the engine's own, from BaseEngine.ini) and the shot sizes, angles and heights
    the framing solver knows.

    Returns: {"filmbacks": {name: [w_mm, h_mm]}, "lenses": {name: {...}}, "default_filmback", "sizes": {key: desc},
    "angles", "heights", "moves", "noise"}.
    Example: film-ue op cam.presets
    """
    names = {}
    try:  # the project's own list, if it has changed it
        st = unreal.CineCameraSettings.get_cine_camera_settings()
        for p in st.get_editor_property("filmback_presets") or []:
            fb = p.get_editor_property("filmback_settings")
            names[str(p.get_editor_property("name"))] = [float(fb.get_editor_property("sensor_width")),
                                                         float(fb.get_editor_property("sensor_height"))]
    except Exception:
        names = {}
    return {"filmbacks": names or {k: list(v) for k, v in lens.FILMBACKS.items()},
            "lenses": {k: {"min_focal_mm": v[0], "max_focal_mm": v[1], "min_fstop": v[2], "max_fstop": v[3]}
                       for k, v in lens.LENSES.items()},
            "default_filmback": lens.DEFAULT_FILMBACK, "primes_mm": list(lens.PRIMES),
            "sizes": {k: f"{framing.SIZES[k]['name']}: {framing.SIZES[k]['desc']}" for k in framing.ORDER},
            "size_aliases": framing.ALIASES, "angles": framing.ANGLES, "heights": {**framing.HEIGHTS,
                                                                                    **framing.HEIGHT_AT},
            "moves": ["hold", "follow", "dolly", "push_in", "pull_out", "truck", "pedestal", "crane", "orbit", "arc",
                      "pan", "tilt", "roll", "zoom", "dolly_zoom", "whip", "rack"],
            "eases": list(moves.EASES), "noise": moves.NOISE}


@op("cam.add", mutates=True, idempotent=True, tags=["camera"])
def add(*, label: str, loc: list | None = None, rot_: dict | None = None, look_at=None, focal_mm: float | None = None,
        aperture: float | None = None, sensor_mm=None, filmback: str | None = None, lens_preset: str | None = None,
        focus_cm: float | None = None, focus_on=None) -> dict:
    """Make or converge a cine camera named `label`: place it, aim it, set its lens and focus.

    Args: label: actor label. loc: [x, y, z] cm. rot_: {"pitch", "yaw", "roll"} deg, or look_at: a point [x, y, z],
    an actor label or "Label:Component:bone" (overrides rot_). focal_mm. aperture: f-stop. sensor_mm: [w, h] mm, or
    filmback: a preset name ("16:9 Digital Film", the engine default; "16:9 DSLR" is full frame). lens_preset:
    "50mm Prime f/1.8" etc. (sets the lens limits). focus_cm: manual focus distance; focus_on: a point/actor/bone
    to focus on now (manual focus at its distance; for a moving subject key it with cam.move focus_on, or use
    cam.focus mode=track).
    A new camera gets the engine's default filmback and focal 35 mm unless given.
    Returns: cam.describe's dict plus "changed", "created".
    Example: film-ue op cam.add label=CAM_A 'loc=[400,0,160]' look_at=Presenter focal_mm=50 aperture=2.8
    """
    if look_at is not None and loc is None and _find(label) is None:
        raise OpError("look_at needs loc for a new camera", code="bad_args", hint="pass loc=[x, y, z]")
    if filmback is not None and sensor_mm is not None:
        raise OpError("pass sensor_mm or filmback, not both", code="bad_args")
    sensor = lens.filmback(filmback) if filmback is not None else (lens.filmback(sensor_mm) if sensor_mm else None)
    a, made = _ensure(label)
    if made and sensor is None:
        sensor = lens.filmback(None)
    if made and focal_mm is None:
        focal_mm = 35.0
    changed = made
    r = rot_
    if look_at is not None:
        r = geo.look_at(loc if loc is not None else _v3(a.get_actor_location()), _point(look_at))
    changed |= _place(a, loc, r)
    changed |= _set_lens(a, focal_mm, aperture, sensor, lens_preset)
    if focus_on is not None:
        d = lens.view(read(label), _point(focus_on))[0]
        changed |= _set_focus(a, MANUAL, max(1.0, d))
    elif focus_cm is not None:
        changed |= _set_focus(a, MANUAL, focus_cm)
    elif made:
        _set_focus(a, MANUAL, 300.0 if look_at is None else max(1.0, geo.dist(loc, _point(look_at))))
    return {**read(label), "changed": bool(changed), "created": made}


def _point(target, offset=None) -> list:
    """Where a target is: a point, an actor (its location), "Label:Component:bone", or "eyes:Label"."""
    if isinstance(target, (list, tuple)):
        return [float(x) for x in target]
    t = str(target)
    if t.startswith("eyes:"):
        return subject(t[5:])["points"]["eyes"]
    from .seq import aim_point
    try:
        return aim_point(t, offset)
    except ValueError as e:
        raise not_found("actor or bone", t, _labels(), hint=str(e)) from None


@op("cam.point", mutates=False, idempotent=True, tags=["camera"])
def point(*, target, offset=None) -> dict:
    """Where a target is now, in world cm: a point, an actor label (its location; with `offset` in its own frame),
    "Label:Component:bone", "eyes:Label" (between its eyes), or a camera's label (its lens).

    Example: film-ue op cam.point target=eyes:Presenter
    """
    return {"target": target, "point": [round(v, 3) for v in _point(target, offset)]}


@op("cam.set", mutates=True, idempotent=True, tags=["camera"])
def set_(*, label: str, focal_mm: float | None = None, aperture: float | None = None, sensor_mm=None,
         filmback: str | None = None, lens_preset: str | None = None, near_clip_cm: float | None = None,
         hfov_deg: float | None = None) -> dict:
    """Change an existing camera's lens: focal length (or the horizontal field of view it gives), aperture,
    filmback, lens limits, near clip plane.

    Example: film-ue op cam.set label=CAM_A focal_mm=85 aperture=1.8
    """
    a = _cine(label)
    if hfov_deg is not None:
        if focal_mm is not None:
            raise OpError("pass focal_mm or hfov_deg, not both", code="bad_args")
        cur = read(label)["filmback"]
        focal_mm = lens.focal_for_hfov(hfov_deg, lens.filmback(filmback or sensor_mm or cur))
    sensor = lens.filmback(filmback) if filmback else (lens.filmback(sensor_mm) if sensor_mm else None)
    changed = _set_lens(a, focal_mm, aperture, sensor, lens_preset)
    if near_clip_cm is not None:
        c = _comp(a)
        c.set_editor_property("override_custom_near_clipping_plane", True)
        c.set_custom_near_clipping_plane(float(near_clip_cm))
        changed = True
    return {**read(label), "changed": bool(changed)}


@op("cam.focus", mutates=True, idempotent=True, tags=["camera"])
def focus(*, label: str, mode: str = "manual", distance_cm: float | None = None, target=None, offset=(0.0, 0.0, 0.0),
          smooth_speed: float | None = None) -> dict:
    """Set a camera's focus: mode "manual" (distance_cm, or the distance to `target` now), "track" (follow an actor,
    the engine's tracking focus: `target` an actor label, or "eyes:Label" for its eyes at the current pose, or
    "Label:Component:bone"), or "off" (no depth of field).

    Args: offset: cm in the tracked actor's own frame, added to the target. smooth_speed: >0 smooths focus changes.
    Example: film-ue op cam.focus label=CAM_A mode=track target=eyes:Presenter
    """
    a = _cine(label)
    m = mode.lower()
    if m == "manual":
        if distance_cm is None and target is None:
            raise OpError("manual focus needs distance_cm or target", code="bad_args")
        d = distance_cm if distance_cm is not None else lens.view(read(label), _point(target, offset))[0]
        changed = _set_focus(a, MANUAL, max(1.0, float(d)), smooth_speed=smooth_speed)
    elif m in ("track", "tracking"):
        if target is None:
            raise OpError("track focus needs target (an actor label, eyes:Label or Label:Component:bone)",
                          code="bad_args")
        t = str(target)
        lab = t[5:] if t.startswith("eyes:") else t.split(":")[0]
        tgt = _find(lab)
        if tgt is None:
            raise not_found("actor", lab, _labels())
        off = list(offset)
        if t.startswith("eyes:") or ":" in t:
            # the point in the actor's own frame at the current pose (the engine adds RelativeOffset in actor space)
            p = _point(t)
            local = tgt.get_actor_transform().inverse_transform_location(vec(p))
            off = [local.x + offset[0], local.y + offset[1], local.z + offset[2]]
        changed = _set_focus(a, TRACKING, track=tgt, offset=off, smooth_speed=smooth_speed)
    elif m in ("off", "disable", "none"):
        changed = _set_focus(a, DISABLE)
    else:
        raise OpError(f"focus mode {mode!r}", code="bad_args", candidates=["manual", "track", "off"])
    return {**read(label), "changed": bool(changed)}


@op("cam.describe", mutates=False, idempotent=True, tags=["camera"])
def describe(*, label: str = "") -> dict:
    """Every cine camera in the level (or one): location, rotation, focal, aperture, filmback, focus, fields of view,
    the rig it hangs on.

    Example: film-ue op cam.describe label=CAM_A
    """
    if label:
        return {"cameras": [read(label)]}
    return {"cameras": [read(l) for l in _labels(unreal.CineCameraActor)]}


@op("cam.remove", mutates=True, idempotent=True, tags=["camera"])
def remove(*, labels: list | None = None, prefix: str = "") -> dict:
    """Delete cine cameras (and rigs) by label or by label prefix; missing ones are skipped.

    Example: film-ue op cam.remove prefix=CAM_
    """
    if not labels and not prefix:
        raise OpError("name labels or a prefix", code="bad_args")
    gone = []
    for a in list(EAS().get_all_level_actors()):
        lab = a.get_actor_label()
        if (labels and lab in labels) or (prefix and lab.startswith(prefix)):
            if isinstance(a, (unreal.CineCameraActor, unreal.CameraRig_Rail, unreal.CameraRig_Crane)):
                EAS().destroy_actor(a)
                gone.append(lab)
    return {"removed": gone, "changed": bool(gone)}


@op("cam.subject", mutates=False, idempotent=True, tags=["camera"])
def subject_op(*, target, mode: str = "auto", facing=None, top_z: float | None = None) -> dict:
    """What the framing solver sees of an actor: its landmarks (head_top, eyes, nose, mouth, chin, neck, shoulders,
    chest, waist, hips, knees, ankles, feet) in world cm, its facing and height, and whether they came from its
    skeleton or its bounds.

    Args: target: actor label. mode: auto (bones, else bounds) | bones | bounds. facing: [x, y, z] override.
    top_z: the crown's height when hair or a hat makes it higher than the default (eyes + 11.5 cm).
    Example: film-ue op cam.subject target=Presenter
    """
    s = subject(target, mode, facing, top_z)
    return {**s, "from": s.get("from", "bones")}


@op("cam.frame", mutates=True, idempotent=True, tags=["camera"])
def frame(*, camera: str, subjects, size: str = "MCU", angle=0.0, side: str = "left", height="eye",
          focal_mm: float | None = 50.0, distance_cm: float | None = None, place="auto", headroom: float | None = None,
          dutch_deg: float = 0.0, aperture: float | None = None, filmback: str | None = None, snap_focal: bool = False,
          focus: bool = True, apply: bool = True, mode: str = "auto") -> dict:
    """Frame subjects with a camera by shot grammar: "MCU of Presenter from 3/4 left, eye level, 50 mm".

    Args: camera: label (made if missing). subjects: an actor label or a list (a two-shot, a group).
    size: ECU CU MCU MS COWBOY MWS WS EWS (aliases: close-up, medium, wide, full...). angle: degrees or front, 3/4,
    profile, 3/4 back, back: around from the first subject's facing toward its own `side` (left|right).
    height: eye, high, low, slight high, slight low, overhead, worm, degrees, shoulder/chest/hip/knee/ground, or
    {"z": cm}. focal_mm (distance solved) or distance_cm with focal_mm=None (focal solved; snap_focal rounds to a
    prime). place: auto (thirds with lead room off-axis, centre when frontal), center, left third, right third, or
    u 0..1. headroom: v of the head's top (default per size). dutch_deg: roll. focus: focus on the first subject's
    eyes. apply: False only plans (nothing changes).
    Returns: {"camera": cam.describe dict, "solve": {distance, focal, error, predicted u/v of every landmark,
    dof, warnings}, "changed"}.
    Example: film-ue op cam.frame camera=CAM_A subjects=Presenter size=MCU angle=3/4 side=left focal_mm=50
    """
    subs = _subjects(subjects, mode)
    if not subs:
        raise OpError("frame needs subjects", code="bad_args", hint="subjects=Presenter or ['A','B']")
    try:
        r = framing.solve(subs, size, angle=angle, side=side, height=height, focal=focal_mm, distance=distance_cm,
                          place=place, headroom=headroom, dutch=dutch_deg,
                          filmback=filmback or (read(camera)["filmback"] if _find(camera) else None),
                          aperture=aperture or 2.8, snap_focal=snap_focal)
    except ValueError as e:
        raise OpError(str(e), code="bad_args", hint="cam.presets lists sizes, angles and heights") from None
    if r["error"] is not None and r["error"] > 1e-3:
        r["warnings"].append(f"the solver missed by {r['error']:.4f} of the frame: the request may be impossible "
                             "(try another focal length or height)")
    out = {"solve": {k: r[k] for k in ("size", "distance", "focal", "focus", "hfov", "error", "dof", "predicted",
                                       "warnings")}, "plan": r["camera"]}
    if not apply:
        return {**out, "changed": False}
    cam = r["camera"]
    res = add(label=camera, loc=cam["loc"], rot_=cam["rot"], focal_mm=cam["focal"], aperture=aperture,
              sensor_mm=cam["filmback"], focus_cm=r["focus"] if focus else None)
    return {**out, "camera": {k: v for k, v in res.items() if k not in ("changed", "created")},
            "changed": res["changed"]}


@op("cam.project", mutates=False, idempotent=True, tags=["camera", "qa"])
def project(*, camera: str, points=None, subjects=None) -> dict:
    """Where things land in a camera's frame: u, v (0..1 from the top left; outside = out of frame) and depth (cm),
    for named points ({"name": [x, y, z] | label | "Label:Component:bone"}) and every landmark of `subjects`.

    Example: film-ue op cam.project camera=CAM_A subjects=Presenter
    """
    cam = read(camera)
    out = {}
    for n, p in (points or {}).items():
        q = lens.project(cam, _point(p))
        out[n] = {"u": round(q["u"], 4), "v": round(q["v"], 4), "depth": round(q["depth"], 2), "visible": q["visible"]}
    for s in _subjects(subjects):
        out[s["name"]] = {k: {"u": round(q["u"], 4), "v": round(q["v"], 4), "depth": round(q["depth"], 2),
                              "visible": q["visible"]} for k, q in
                          ((k, lens.project(cam, p)) for k, p in s["points"].items())}
        out[s["name"]]["size"] = framing.classify(cam, s)
    return {"camera": camera, "points": out}


@op("cam.check", mutates=False, idempotent=True, tags=["camera", "qa"])
def check(*, camera: str, subjects, size: str | None = None, others=None) -> dict:
    """Numeric checks of a camera's frame on its subjects: QA's per-frame framing (headroom, cut-offs, feet, size, look
    room; when fmbridge.qa is installed) plus the camera's own: focus, safe areas, an accidental dutch, a subject
    blocked by `others`.

    Returns: {"pass", "issues": [{"code", "severity", "message", "fix", ...}], "metrics": {"size", "focus_cm",
    "hfov_deg"}}.
    Example: film-ue op cam.check camera=CAM_A subjects=Presenter size=MCU
    """
    cam = read(camera)
    subs = _subjects(subjects)
    issues = ck.frame(cam, subs, _subjects(others), camera=camera)
    issues += _qa_issues(cam, subjects, subs, size)
    metrics = {"size": {s["name"]: framing.classify(cam, s) for s in subs}, "focus_cm": cam.get("focus"),
               "hfov_deg": cam["hfov_deg"]}
    return {"pass": ck.worst(issues) != "fail", "issues": issues, "metrics": metrics}


def _qa_issues(cam: dict, targets, subs: list, size) -> list:
    """WP10's per-frame framing checks (fmbridge.qa.framing.check) on each subject, when that package is there."""
    try:
        from ..qa import framing as qaf
    except ImportError:
        return [ck.issue("cam.qa_missing", "info", "per-frame framing checks (fmbridge.qa) are not installed",
                         "merge WP10's branch", cam.get("label", ""))]
    out = []
    labels = targets if isinstance(targets, (list, tuple)) and targets and not isinstance(targets[0], (int, float)) \
        else [targets]
    try:
        qcam = qaf.Camera.from_dict({"loc": cam["loc"], "rot": cam["rot"], "focal": cam["focal"],
                                     "sensor_width": cam["filmback"][0], "aspect": cam["filmback"][0] / cam["filmback"][1],
                                     "name": cam.get("label", "")})
        for lab, s in zip(labels, subs):
            a = _find(str(lab).split(":")[0]) if isinstance(lab, str) else None
            bones = dict(_bones_of(a)) if a is not None else {}
            if bones:  # a skeleton: add the landmarks it lacks; a prop or stand-in is judged from its bounds alone
                bones.update({"eyes": s["points"]["eyes"], "head_top": s["points"]["head_top"]})
            bounds = None
            if a is not None:
                o, e = a.get_actor_bounds(False)
                bounds = (_v3(o), _v3(e))
            r = qaf.check(qcam, s["name"], bones=bones or None, bounds=bounds, facing=s["facing"],
                          expect={"size": framing.size_key(size)} if size else None)
            out += list(r.get("issues", []) if isinstance(r, dict) else r)
    except Exception as e:  # their API moved: say so, keep ours
        out.append(ck.issue("cam.qa_error", "info", f"fmbridge.qa.framing.check failed: {type(e).__name__}: {e}", "",
                            cam.get("label", "")))
    return out


@op("cam.check_cut", mutates=False, idempotent=True, tags=["camera", "qa"])
def check_cut(*, camera_a: str, camera_b: str, subjects, size_a: str | None = None,
              size_b: str | None = None) -> dict:
    """Would a cut from camera A to camera B work: the 180-degree line between the first two subjects, the
    30-degree rule and the size step on the first.

    Example: film-ue op cam.check_cut camera_a=CAM_A camera_b=CAM_B 'subjects=["Host","Guest"]'
    """
    subs = _subjects(subjects)
    issues = ck.cut(read(camera_a), read(camera_b), subs, size_a, size_b, names=(camera_a, camera_b))
    return {"pass": ck.worst(issues) != "fail", "issues": issues}


@op("cam.coverage", mutates=True, idempotent=True, tags=["camera"])
def coverage_op(*, subjects, side: str = "left", focal_mm: float = 50.0, wide_focal_mm: float = 28.0,
                prefix: str = "CAM_", create: bool = True, overs: bool = True, filmback: str | None = None,
                aperture: float = 2.8, height="eye") -> dict:
    """The coverage of a scene, all on one side of the line: for one subject a WS/MS/MCU/CU from 3/4 and a profile;
    for two or more a master, a two-shot, each one's MS/MCU/CU single and an over-the-shoulder. Makes a camera per
    shot ({prefix}{name}) unless create=False.

    Args: side: left|right of the line from the first subject to the second, seen from above.
    Returns: {"line", "side", "shots": [{"name", "camera", "kind", "size", "focal", "distance", "loc", "rot",
    "warnings"}], "issues"}.
    Example: film-ue op cam.coverage 'subjects=["Host","Guest"]' side=left
    """
    subs = _subjects(subjects)
    p = cov.plan(subs, side=side, focal=focal_mm, wide_focal=wide_focal_mm, filmback=filmback, overs=overs,
                 aperture=aperture, height=height)
    rows = cov.describe(p)
    changed = False
    for row, shot in zip(rows, p["shots"]):
        row["camera"] = f"{prefix}{shot['name']}"
        if create:
            c = shot["solve"]["camera"]
            res = add(label=row["camera"], loc=c["loc"], rot_=c["rot"], focal_mm=c["focal"], aperture=aperture,
                      sensor_mm=c["filmback"], focus_cm=shot["solve"]["focus"])
            changed |= res["changed"]
    return {"line": p["line"], "side": side, "shots": rows, "issues": p["issues"], "changed": changed}


# --- moves ------------------------------------------------------------------------------------------------------

def _seq(name: str, **args):
    """WP8's Sequencer ops, by name: the one place cameras touch Sequencer data."""
    return call(name, **args)


def write_keys(sequence: str, label: str, keys: list) -> dict:
    """Baked camera keys onto a camera's tracks in a sequence: its transform, and the focal length and manual focus
    distance when they change (each replaces only its own track)."""
    sk = moves.sequencer_keys(keys)
    _seq("seq.key_transform", path=sequence, label=label, keys=sk["transform"], interp="auto")
    n = {"transform": len(sk["transform"])}
    if len(sk["focal"]) > 1:
        _seq("seq.key_float", path=sequence, label=label, prop="CurrentFocalLength", keys=sk["focal"],
             component="CineCameraComponent")
        n["focal"] = len(sk["focal"])
    if sk["focus"]:
        _set_focus(_cine(label), MANUAL, sk["focus"][0][1])
        if len(sk["focus"]) > 1:
            _seq("seq.key_float", path=sequence, label=label, prop="FocusSettings.ManualFocusDistance",
                 keys=sk["focus"], component="CineCameraComponent")
            n["focus"] = len(sk["focus"])
    return n


@op("cam.move", mutates=True, idempotent=True, tags=["camera", "sequencer"])
def move(*, camera: str, sequence: str, moves_: list, start_frame: int = 0, end_frame: int | None = None,
         step: int = 2, aim=None, focus_on=None, noise=None, fps: float | None = None) -> dict:
    """Key camera moves into a sequence: dolly, push_in, pull_out, truck, pedestal, crane, orbit/arc, pan, tilt,
    roll, zoom, dolly_zoom, whip, rack, follow, hold; eased, one after another from the camera's current pose, with
    optional handheld noise. Replaces the camera's transform (and focal/focus) tracks in that sequence.

    Args: moves_: [{"move": kind, "frames": n | "from"/"to", "ease": in_out|in|out|linear|sine|smooth|expo, ...}]
    (cam.presets lists kinds; docs/unreal/camera.md their arguments). aim: what the camera keeps framed (a point, an
    actor label, "Label:Component:bone", "eyes:Label"). focus_on: the same, baked as a follow-focus. noise: "subtle"
    | "handheld" | "documentary" | "breathing" | "shake" or {"preset", "seed", "scale", "pos", "rot", "hz"}.
    step: frames between baked keys. end_frame: hold the last pose to there.
    Returns: {"keys": n, "segments", "first", "last", "changed": true}.
    Example: film-ue op cam.move camera=CAM_A sequence=/Game/Seq/S1 'moves_=[{"move":"push_in","fraction":0.2,"frames":72}]' aim=eyes:Presenter
    """
    cam = read(camera)
    seqobj = unreal.EditorAssetLibrary.load_asset(sequence)
    if seqobj is None:
        raise not_found("level sequence", sequence, [], hint="make it with seq.new")
    if fps is None:
        r = seqobj.get_display_rate()
        fps = r.numerator / r.denominator
    try:
        baked = moves.plan(cam, moves_, first=start_frame, last=end_frame, fps=fps, step=step,
                           aim=_point(aim) if aim is not None else None,
                           focus_on=_point(focus_on) if focus_on is not None else None, noise=noise)
    except ValueError as e:
        raise OpError(str(e), code="bad_args", hint="cam.presets lists the moves") from None
    n = write_keys(sequence, camera, baked["keys"])
    k0, k1 = baked["keys"][0], baked["keys"][-1]
    return {"keys": n, "segments": baked["segments"], "first": k0, "last": k1, "changed": True}


# --- rigs -------------------------------------------------------------------------------------------------------

@op("cam.rig", mutates=True, idempotent=True, tags=["camera"])
def rig(*, label: str, kind: str = "rail", points: list | None = None, loc: list | None = None,
        yaw_deg: float = 0.0, arm_cm: float = 300.0, pitch_deg: float = 0.0, lock_orientation: bool = False,
        camera: str = "", position: float = 0.0) -> dict:
    """A camera rail or crane (the engine's CameraRig_Rail / CameraRig_Crane), with `camera` mounted on it.

    rail: `points` [[x, y, z], ...] world cm along the track (2+); `position` 0..1 along it; lock_orientation turns
    the camera with the rail. crane: at `loc`, turned `yaw_deg`, arm `arm_cm` long, raised `pitch_deg`. Drive either
    over time with cam.rig_move.
    Example: film-ue op cam.rig label=Rail_A kind=rail 'points=[[300,-200,150],[300,200,150]]' camera=CAM_A
    """
    k = kind.lower()
    cls = {"rail": unreal.CameraRig_Rail, "crane": unreal.CameraRig_Crane}.get(k)
    if cls is None:
        raise OpError(f"rig kind {kind!r}", code="bad_args", candidates=["rail", "crane"])
    if k == "rail" and (not points or len(points) < 2):
        raise OpError("a rail needs points: at least two [x, y, z]", code="bad_args")
    a = _find(label)
    made = False
    if a is not None and not isinstance(a, cls):
        raise OpError(f"{label!r} is a {_cls(a)}", code="conflict", hint="cam.remove it first")
    if a is None:
        start = points[0] if k == "rail" else (loc or [0.0, 0.0, 0.0])
        a = EAS().spawn_actor_from_class(cls, vec(start), unreal.Rotator(roll=0.0, pitch=0.0, yaw=float(yaw_deg)))
        if a is None:
            raise OpError(f"the engine did not spawn a {cls.__name__}", code="engine")
        a.set_actor_label(label)
        made = True
    if k == "rail":
        a.set_actor_location(vec(points[0]), False, False)
        sp = a.get_rail_spline_component()
        sp.set_spline_points([vec(p) for p in points], unreal.SplineCoordinateSpace.WORLD, True)
        a.set_editor_property("current_position_on_rail", float(position))
        a.set_editor_property("lock_orientation_to_rail", bool(lock_orientation))
    else:
        if loc is not None:
            a.set_actor_location(vec(loc), False, False)
        a.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=0.0, yaw=float(yaw_deg)), False)
        a.set_editor_property("crane_arm_length", float(arm_cm))
        a.set_editor_property("crane_pitch", float(pitch_deg))
        a.set_editor_property("crane_yaw", 0.0)
    if camera:
        c = _cine(camera)
        if c.get_attach_parent_actor() is not a:
            ok = c.attach_to_actor(a, "", unreal.AttachmentRule.SNAP_TO_TARGET, unreal.AttachmentRule.KEEP_WORLD,
                                   unreal.AttachmentRule.KEEP_WORLD, False)
            if not ok:
                raise OpError(f"could not mount {camera} on {label}", code="engine")
    return {"label": label, "kind": k, "created": made, "camera": camera or None, "changed": True}


@op("cam.rig_move", mutates=True, idempotent=True, tags=["camera", "sequencer"])
def rig_move(*, rig_label: str, sequence: str, keys: list) -> dict:
    """Animate a rig in a sequence: a rail's position along it (0..1), a crane's pitch, yaw and arm.

    Args: keys: [[frame, {"position": 0..1} | {"pitch_deg", "yaw_deg", "arm_cm"}], ...] (auto-eased).
    Example: film-ue op cam.rig_move rig_label=Rail_A sequence=/Game/Seq/S1 'keys=[[0,{"position":0}],[96,{"position":1}]]'
    """
    a = _find(rig_label)
    if a is None:
        raise not_found("rig", rig_label, _labels(), hint="make it with cam.rig")
    props = {"position": "CurrentPositionOnRail", "pitch_deg": "CranePitch", "yaw_deg": "CraneYaw",
             "arm_cm": "CraneArmLength"}
    tracks: dict = {}
    for frame_, vals in keys:
        for k, v in vals.items():
            if k not in props:
                raise OpError(f"rig key {k!r}", code="bad_args", candidates=list(props))
            tracks.setdefault(props[k], []).append([int(frame_), float(v)])
    for prop, ks in tracks.items():
        _seq("seq.key_float", path=sequence, label=rig_label, prop=prop, keys=ks)
    return {"tracks": {p: len(k) for p, k in tracks.items()}, "changed": True}


# --- pictures ---------------------------------------------------------------------------------------------------

@op("cam.still", mutates=False, idempotent=True, tags=["camera", "qa", "gpu"])
def still(*, camera: str, out: str, width: int = 960, height: int = 540, guides: bool = True, subjects=None):
    """A still through a camera with the operator's guides drawn on it: thirds, action/title safe, centre, and each
    subject's landmarks where the lens math puts them (green crosses), so a mismatch between solver and render shows.
    A multi-tick job. Keep it small (960x540): the overlay is drawn in pure Python.

    Returns: {"path", "width", "height", "raw": the still without guides}.
    Example: film-ue op cam.still camera=CAM_A out=/tmp/cam_a.png subjects=Presenter
    """
    from .look import still as look_still
    raw = out[:-4] + "_raw.png" if out.lower().endswith(".png") else out + "_raw.png"
    cam = read(camera)
    subs = _subjects(subjects)
    yield from look_still(camera, raw, width, height)
    yield
    img = png.read(raw)
    if guides:
        png.guides(img)
    for s in subs:
        png.marks(img, {k: [q["u"], q["v"]] for k, q in ((k, lens.project(cam, p)) for k, p in s["points"].items()
                                                         if k in ("head_top", "eyes", "chin", "chest", "waist",
                                                                  "knees", "feet"))
                        if q["depth"] > 0})
    img.text(6, 6, f"{camera} {cam['focal']:.0f}MM F/{cam['aperture']:g} HFOV {cam['hfov_deg']:.1f}", scale=1,
             bg=(0, 0, 0))
    return {**png.write(out, img), "raw": raw}
