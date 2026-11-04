"""Claude's eyes in the editor: pictures with no viewport. `view.still` renders what a camera (a camera actor, a
sequence's cut at a frame, or an ad-hoc loc/look_at) sees through a scene capture, or through Movie Render Queue
(render.frames, WP9) or the old viewport screenshot; `view.turntable` circles an actor; `view.stills` samples a
sequence; `view.sheet` and `view.overlay` annotate files already on the box (guides, boxes, labels, contact sheets).

Every picture is a PNG on the box: {"path", "width", "height", ...}; pull it with `film-ue pull`. Analysis (qa.*)
reads the same files. The pure image work is fmbridge.qa (no `unreal`), shared with the client.

The capture rig is one transient SceneCapture2D actor labelled FMQA_Capture, made when needed and destroyed when
the op ends, so no QA leaves anything in the level (and a crash mid-op leaves at most that one actor, which the next
capture reuses and removes)."""
from __future__ import annotations

import inspect
import math
import os

import unreal

from . import op
from ..errors import OpError, not_found
from ..qa import framing as _framing
from ..qa import image as _image
from ..qa import overlay as _overlay
from ..qa import sheet as _sheet

RIG = "FMQA_Capture"
MODES = ("capture", "mrq", "viewport")
SOURCES = {"final": "SCS_FINAL_COLOR_LDR", "depth": "SCS_SCENE_DEPTH", "base_color": "SCS_BASE_COLOR",
           "normal": "SCS_NORMAL", "hdr": "SCS_FINAL_COLOR_HDR"}
_RTS: dict = {}  # (w, h, format) -> render target, reused across captures (transient objects, never saved)


def _eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def find_actor(label: str):
    """The level actor with this label, or an OpError naming the nearest labels."""
    actors = list(_eas().get_all_level_actors())
    for a in actors:
        if a.get_actor_label() == label:
            return a
    raise not_found("actor", label, [a.get_actor_label() for a in actors], hint="list them with level.actors")


def class_name(obj) -> str:
    return obj.get_class().get_name()


def _xyz(v) -> list:
    return [float(v.x), float(v.y), float(v.z)]


def _rot(r) -> dict:
    return {"pitch": float(r.pitch), "yaw": float(r.yaw), "roll": float(r.roll)}


# --- cameras -----------------------------------------------------------------------------------------------------

def camera_info(camera: str = "", loc=None, look_at=None, fov_deg: float = 0.0, aspect: float = 16 / 9) -> dict:
    """What a camera sees, as plain numbers: {"name", "loc", "rot", "fov" (horizontal degrees), "aspect", "focal",
    "sensor_width", "post": the camera's post-process settings object or None}. From a camera actor's label, or
    ad hoc from `loc` + `look_at` (+ `fov_deg`, default 40)."""
    if not camera:
        if loc is None or look_at is None:
            raise OpError("no camera: give camera=<label>, or loc=[x,y,z] and look_at=[x,y,z]", code="bad_args",
                          hint="cameras in the level: level.actors cls=Camera")
        return {"name": "adhoc", "loc": [float(v) for v in loc], "rot": _framing.look_at(loc, look_at),
                "fov": float(fov_deg or 40.0), "aspect": aspect, "post": None}
    a = find_actor(camera)
    info = {"name": camera, "loc": _xyz(a.get_actor_location()), "rot": _rot(a.get_actor_rotation()), "aspect": aspect,
            "post": None}
    comp = None
    if isinstance(a, unreal.CineCameraActor):
        comp = a.get_cine_camera_component()
        info["fov"] = float(comp.get_horizontal_field_of_view())
        fb = comp.get_editor_property("filmback")
        info["focal"] = float(comp.get_editor_property("current_focal_length"))
        info["sensor_width"] = float(fb.get_editor_property("sensor_width"))
        info["sensor_height"] = float(fb.get_editor_property("sensor_height"))
        info["camera_aspect"] = info["sensor_width"] / max(info["sensor_height"], 1e-6)
    elif isinstance(a, unreal.CameraActor):
        comp = a.get_editor_property("camera_component")
        info["fov"] = float(comp.get_editor_property("field_of_view"))
        info["camera_aspect"] = float(comp.get_editor_property("aspect_ratio"))
    else:
        raise OpError(f"{camera!r} is a {class_name(a)}, not a camera", code="bad_args",
                      hint="give a CameraActor/CineCameraActor label (level.actors cls=Camera) or loc+look_at")
    if comp is not None:
        info["loc"] = _xyz(comp.get_world_location())
        info["rot"] = _rot(comp.get_world_rotation())
        info["post"] = comp.get_editor_property("post_process_settings")
    if fov_deg:
        info["fov"] = float(fov_deg)
    return info


# --- the capture rig ---------------------------------------------------------------------------------------------

def _rig():
    for a in _eas().get_all_level_actors():
        if a.get_actor_label() == RIG:
            return a
    a = _eas().spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(roll=0, pitch=0, yaw=0))
    if not a:
        raise OpError("could not spawn the SceneCapture2D capture rig", code="engine")
    a.set_actor_label(RIG)
    return a


def remove_rig() -> bool:
    for a in list(_eas().get_all_level_actors()):
        if a.get_actor_label() == RIG:
            _eas().destroy_actor(a)
            return True
    return False


STILL_FORMATS = ("RTF_RGBA8", "RTF_RGBA8_SRGB")  # ExportRenderTarget writes PNG only for 8-bit targets (EXR for float)
RT_FORMATS = ("RTF_R8", "RTF_RG8", "RTF_RGBA8", "RTF_RGBA8_SRGB", "RTF_R16F", "RTF_RG16F", "RTF_RGBA16F", "RTF_R32F",
              "RTF_RG32F", "RTF_RGBA32F", "RTF_RGB10A2")  # ETextureRenderTargetFormat, TextureRenderTarget2D.h:23-43


def _format(fmt: str, allowed=None) -> str:
    """A TextureRenderTargetFormat name as Python spells it (upper case: the C++ RTF_RGBA16f is RTF_RGBA16F), checked."""
    name = str(fmt).strip().upper()
    if not name.startswith("RTF_"):
        name = "RTF_" + name
    valid = list(allowed or RT_FORMATS)
    if name not in valid:
        raise OpError(f"render target format {fmt!r} is not one of {valid}", code="bad_args", candidates=valid,
                      hint="a still exports as PNG only from an 8-bit target" if allowed else "")
    return name


def _rt(w: int, h: int, fmt: str):
    fmt = _format(fmt)
    key = (w, h, fmt)
    rt = _RTS.get(key)
    if rt is None:
        rt = unreal.RenderingLibrary.create_render_target2d(_world(), w, h, getattr(unreal.TextureRenderTargetFormat, fmt),
                                                           unreal.LinearColor(r=0, g=0, b=0, a=1), False, False)
        if not rt:
            raise OpError(f"could not create a {w}x{h} {fmt} render target", code="engine")
        _RTS[key] = rt
    return rt


def capture(cam: dict, width: int, height: int, source: str = "final", show_only=(), hidden=(), warmup: int = 8,
            fmt: str = ""):
    """A multi-tick capture through `cam` (camera_info) into a render target; returns the target. `show_only`
    primitive components (or actors) restrict what is drawn (everything else is not rendered); `hidden` hides
    actors. `warmup` captures with the rendering state kept between them let temporal AA, Lumen and streaming settle
    before the final one."""
    if source not in SOURCES:
        raise OpError(f"source {source!r}: one of {sorted(SOURCES)}", code="bad_args")
    fmt = fmt or ("RTF_RGBA8" if source == "final" else "RTF_RGBA32F" if source == "depth" else "RTF_RGBA16F")
    rt = _rt(int(width), int(height), fmt)
    rig = _rig()
    rig.set_actor_location_and_rotation(unreal.Vector(*cam["loc"]), unreal.Rotator(**cam["rot"]), False, True)
    c = rig.get_editor_property("capture_component2d")
    c.set_editor_property("texture_target", rt)
    c.set_editor_property("capture_source", getattr(unreal.SceneCaptureSource, SOURCES[source]))
    c.set_editor_property("fov_angle", float(cam["fov"]))
    c.set_editor_property("capture_every_frame", False)
    c.set_editor_property("capture_on_movement", False)
    c.set_editor_property("always_persist_rendering_state", True)
    if cam.get("post") is not None and source in ("final", "hdr"):
        c.set_editor_property("post_process_settings", cam["post"])
        c.set_editor_property("post_process_blend_weight", 1.0)
    c.clear_show_only_components()
    c.set_editor_property("show_only_actors", [])
    if show_only:
        c.set_editor_property("primitive_render_mode", unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST)
        for o in show_only:
            if isinstance(o, unreal.Actor):
                c.show_only_actor_components(o, False)
            else:
                c.show_only_component(o)
    else:
        c.set_editor_property("primitive_render_mode", unreal.SceneCapturePrimitiveRenderMode.PRM_RENDER_SCENE_PRIMITIVES)
    c.set_editor_property("hidden_actors", [a for a in hidden])
    for _ in range(max(0, int(warmup))):
        c.capture_scene()
        yield
    c.capture_scene()
    return rt


def export_png(rt, path: str) -> dict:
    """Write an 8-bit render target to `path` (.png); the engine picks PNG for non-float targets."""
    d, f = os.path.split(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    unreal.RenderingLibrary.export_render_target(_world(), rt, d, f)
    if not os.path.isfile(path):
        raise OpError(f"the engine wrote no file at {path}", code="engine",
                      hint="check the editor log (film-ue log) for ExportRenderTarget warnings")
    out = {"path": path, "width": int(rt.get_editor_property("size_x")), "height": int(rt.get_editor_property("size_y"))}
    if not _opaque(rt, out["width"], out["height"]):
        # a scene capture's alpha is not coverage (often 0 on opaque pixels): a PNG with it looks empty to a viewer.
        # Rewrite it as RGB from the raw pixels (slower: ~1 s at 720p, only when needed)
        _image.write(to_image(rt), path)
        out["alpha_dropped"] = True
    return out


def _opaque(rt, w: int, h: int) -> bool:
    """Whether a few sampled pixels have alpha 255 (RenderingLibrary.read_render_target_pixel gives an FColor)."""
    for x, y in ((w // 2, h // 2), (1, 1), (w - 2, h - 2), (w // 4, 3 * h // 4), (3 * w // 4, h // 4)):
        c = unreal.RenderingLibrary.read_render_target_pixel(_world(), rt, int(x), int(y))
        if int(getattr(c, "a", 255)) != 255:
            return False
    return True


def read_pixels(rt, channels: str = "r") -> list:
    """The target's samples as plain floats, row-major: one list per requested channel ("r", "rgb", ...). For an
    RGBA8 target the values are 0..255; float targets give the raw values (depth in cm for source="depth")."""
    samples = unreal.RenderingLibrary.read_render_target_raw(_world(), rt, False)
    if samples is None:
        raise OpError("could not read the render target back", code="engine")
    return [[getattr(s, ch) for s in samples] for ch in channels]


def to_image(rt) -> "_image.Image":
    """An RGBA8 target as a qa Image (no file round trip)."""
    r, g, b = read_pixels(rt, "rgb")
    w, h = int(rt.get_editor_property("size_x")), int(rt.get_editor_property("size_y"))
    data = bytearray(w * h * 3)
    data[0::3] = bytes(int(v) & 255 for v in r)
    data[1::3] = bytes(int(v) & 255 for v in g)
    data[2::3] = bytes(int(v) & 255 for v in b)
    return _image.Image(w, h, 3, data)


def _scrub(sequence: str, frame: int, settle: int):
    from . import call
    call("seq.scrub", path=sequence, frame=int(frame) + 1)
    yield
    call("seq.scrub", path=sequence, frame=int(frame))
    for _ in range(max(0, int(settle))):
        yield


def cut_camera(sequence: str, frame: int) -> str:
    """The camera the sequence's camera cut track shows at `frame` (seq.cuts, WP8)."""
    from . import call
    cuts = call("seq.cuts", path=sequence)
    for cam, start, end in cuts:
        if int(start) <= int(frame) < int(end):
            return cam
    raise OpError(f"no camera cut at frame {frame} in {sequence}", code="not_found",
                  hint=f"the cuts are {cuts}: pass camera= or a frame inside one")


# --- ops ---------------------------------------------------------------------------------------------------------

@op("view.still", mutates=False, idempotent=True, tags=["gpu"])
def still(*, out: str, camera: str = "", sequence: str = "", frame: int | None = None, loc: list | None = None,
          look_at: list | None = None, fov_deg: float = 0.0, width_px: int = 1280, height_px: int = 720,
          mode: str = "capture", warmup: int = 8, settle_ticks: int = 20, level: str = "", hide: list | None = None,
          guides: list | None = None, rt_format: str = ""):
    """A PNG of what a camera sees, with no viewport.

    Args: out: the PNG path on the box. camera: a camera actor label; "" with `sequence`+`frame` takes the camera
    the cut shows at that frame; "" with `loc`/`look_at` [x,y,z] cm makes an ad-hoc camera (`fov_deg`, default 40).
    sequence/frame: scrub the sequence there first (frames at its display rate). width_px/height_px: output size.
    mode: "capture" (a scene capture: fast, ~0.1-1 s, no motion blur/DoF accumulation), "mrq" (Movie Render Queue
    through render.frames: the final look, slower; needs sequence+frame and `level`), "viewport" (look.still's
    high-res screenshot). warmup: captures before the kept one (temporal AA, Lumen). settle_ticks: editor ticks after
    a scrub. hide: actor labels left out. guides: overlay guides drawn on a copy saved as <out>.guides.png
    ("thirds", "safe", ...). rt_format: capture mode's render target format (advanced; RTF_RGBA8, the default, or
    RTF_RGBA8_SRGB, any case: a float target would export EXR, so it is refused; the selftest compares the two).
    Returns: {"path", "width", "height", "camera", "mode", "frame", "camera_info": {loc, rot, fov, aspect},
    "guides_path"?}. A multi-tick job.
    Example: film-ue op view.still out=/tmp/qa/a.png camera=CamA width_px=960 height_px=540
    """
    if mode not in MODES:
        raise OpError(f"mode {mode!r}: one of {MODES}", code="bad_args")
    if (sequence and frame is None) or (frame is not None and not sequence):
        raise OpError("sequence and frame go together", code="bad_args")
    if sequence:
        camera = camera or cut_camera(sequence, frame)
        if mode != "mrq":
            yield from _scrub(sequence, frame, settle_ticks)
    aspect = width_px / height_px
    res = {"camera": camera or "adhoc", "mode": mode, "frame": frame}
    if mode == "capture":
        rt_format = _format(rt_format, STILL_FORMATS) if rt_format else ""
        cam = camera_info(camera, loc, look_at, fov_deg, aspect)
        hidden = [find_actor(h) for h in (hide or [])]
        try:
            rt = yield from capture(cam, width_px, height_px, "final", hidden=hidden, warmup=warmup, fmt=rt_format)
            res.update(export_png(rt, out))
        finally:
            remove_rig()
        res["camera_info"] = {k: v for k, v in cam.items() if k != "post"}
    elif mode == "viewport":
        from . import call
        if not camera:
            raise OpError("mode viewport needs a camera actor", code="bad_args")
        got = call("look.still", camera_label=camera, path=out, width=width_px, height=height_px)
        if inspect.isgenerator(got):
            got = yield from got
        res.update({"path": got["path"], "width": width_px, "height": height_px})
        res["camera_info"] = {k: v for k, v in camera_info(camera, aspect=aspect).items() if k != "post"}
    else:
        from . import _OPS, call
        if "render.frames" not in _OPS:
            raise OpError("mode mrq needs render.frames (WP9), which this bridge does not have", code="unsupported",
                          hint="use mode=capture, or install the bridge from ue-helpers with WP9 merged")
        if not (sequence and level):
            raise OpError("mode mrq renders a sequence: give sequence, frame and level", code="bad_args")
        # a folder of its own: render.frames reuses frames already on disk, and other stills share out's folder
        d = os.path.join(os.path.dirname(os.path.abspath(out)), ".mrq_" + os.path.splitext(os.path.basename(out))[0])
        if os.path.isdir(d):
            for f in os.listdir(d):
                os.remove(os.path.join(d, f))
        got = call("render.frames", sequence=sequence, level=level, frames=[int(frame)], out_dir=d,
                   preset="draft", width=width_px, height=height_px)  # draft writes PNG (preview: JPG)
        if inspect.isgenerator(got):
            got = yield from got
        files = got.get("frames") or {}
        src = files.get(int(frame)) or files.get(str(int(frame)))
        if not src or not os.path.isfile(src):
            raise OpError(f"render.frames returned no file for frame {frame}: {got}", code="failed")
        if os.path.abspath(src) != os.path.abspath(out):
            if src.lower().endswith(".png"):
                os.replace(src, out)
            else:
                _image.write(_image.read(src), out)  # a JPG/EXR needs PIL to read: render.frames draft gives PNG
        res.update({"path": out, "width": width_px, "height": height_px})
        res["camera_info"] = {k: v for k, v in camera_info(camera, aspect=aspect).items() if k != "post"}
    if guides:
        gp = os.path.splitext(out)[0] + ".guides.png"
        _image.write(_overlay.overlay(_image.read(out), guides=guides), gp)
        res["guides_path"] = gp
    return res


@op("view.stills", mutates=False, idempotent=True, tags=["gpu", "slow"])
def stills(*, sequence: str, out_dir: str, frames: list | None = None, per_shot: int = 3, camera: str = "",
           width_px: int = 960, height_px: int = 540, mode: str = "capture", warmup: int = 6, settle_ticks: int = 20,
           sheet: bool = True, guides: list | None = None, level: str = ""):
    """Stills through a sequence's edit and a contact sheet of them: the whole cut in one picture.

    Args: sequence: the level sequence path. out_dir: where {frame:05d}.png and sheet.png go. frames: the frames to
    take; None takes `per_shot` per camera cut (first, middle(s), last). camera: force one camera ("" follows the
    cut). width_px/height_px/mode/warmup/settle_ticks: as view.still. sheet: also write sheet.png with each frame
    labelled "frame camera". guides: drawn on the sheet's cells.
    Returns: {"frames": [{"frame", "camera", "path"}], "sheet": path|None, "width", "height"}. Multi-tick.
    Example: film-ue op view.stills sequence=/Game/Seq/S010 out_dir=/tmp/qa/s010 per_shot=2
    """
    if frames is None:
        frames = shot_frames(sequence, per_shot)
    os.makedirs(out_dir, exist_ok=True)
    got = []
    for f in frames:
        p = os.path.join(out_dir, f"{int(f):05d}.png")
        r = yield from still(out=p, camera=camera, sequence=sequence, frame=int(f), width_px=width_px,
                             height_px=height_px, mode=mode, warmup=warmup, settle_ticks=settle_ticks, level=level)
        got.append({"frame": int(f), "camera": r["camera"], "path": p})
    sp = None
    if sheet and got:
        cells = []
        for g in got:
            im = _image.read(g["path"])
            if guides:
                im = _overlay.overlay(im, guides=guides)
            cells.append({"image": im, "label": f"{g['frame']} {g['camera']}"})
        sp = _image.write(_sheet.contact_sheet(cells, cell_width=min(width_px, 640), title=sequence.rsplit("/", 1)[-1]),
                          os.path.join(out_dir, "sheet.png"))
    return {"frames": got, "sheet": sp, "width": width_px, "height": height_px}


def shot_frames(sequence: str, per_shot: int = 3) -> list:
    """`per_shot` frames spread through each camera cut (first, ..., last), in order."""
    from . import call
    out = []
    for _, start, end in call("seq.cuts", path=sequence):
        start, end = int(start), int(end)
        n = max(1, int(per_shot))
        last = max(start, end - 1)
        picks = [start] if n == 1 else [round(start + k * (last - start) / (n - 1)) for k in range(n)]
        out += [p for p in picks if p not in out]
    if not out:
        raise OpError(f"{sequence} has no camera cuts", code="not_found", hint="give frames= and camera=, or add "
                      "cuts with seq.camera_cuts")
    return out


def _bounds(a) -> tuple:
    o, e = a.get_actor_bounds(False)
    return _xyz(o), _xyz(e)


@op("view.turntable", mutates=False, idempotent=True, tags=["gpu"])
def turntable(*, target: str, out_dir: str, views: int = 8, elevation_deg: float = 10.0, distance_cm: float = 0.0,
              fov_deg: float = 30.0, width_px: int = 640, height_px: int = 640, isolate: bool = False,
              start_yaw_deg: float = 0.0, warmup: int = 4, sheet: bool = True):
    """Stills of an actor from all around (a character, a prop, a garment) and a contact sheet of them.

    Args: target: actor label. out_dir: where view_<yaw>.png and sheet.png go. views: how many, evenly around.
    elevation_deg: the cameras' height angle above the target's centre. distance_cm: 0 frames the bounds with a
    margin. fov_deg: horizontal. isolate: draw only the target (no set; lights still light it). start_yaw_deg: the
    first view's direction from the target (0 = from +X, looking back at it).
    Returns: {"views": [{"yaw", "path", "camera": {loc, rot, fov}}], "sheet", "center", "distance_cm"}. Multi-tick.
    Example: film-ue op view.turntable target=Ada out_dir=/tmp/qa/ada views=8 isolate=true
    """
    a = find_actor(target)
    centre, ext = _bounds(a)
    radius = math.sqrt(sum(e * e for e in ext)) or 50.0
    aspect = width_px / height_px
    half = math.radians(fov_deg) / 2
    vhalf = math.atan(math.tan(half) / aspect)
    dist = distance_cm or 1.15 * radius / math.sin(min(half, vhalf))
    os.makedirs(out_dir, exist_ok=True)
    got = []
    try:
        for k in range(int(views)):
            yaw = (start_yaw_deg + 360.0 * k / int(views)) % 360
            el = math.radians(elevation_deg)
            loc = [centre[0] + dist * math.cos(el) * math.cos(math.radians(yaw)),
                   centre[1] + dist * math.cos(el) * math.sin(math.radians(yaw)), centre[2] + dist * math.sin(el)]
            cam = {"name": f"turntable_{yaw:03.0f}", "loc": loc, "rot": _framing.look_at(loc, centre), "fov": fov_deg,
                   "aspect": aspect, "post": None}
            rt = yield from capture(cam, width_px, height_px, "final", show_only=[a] if isolate else (), warmup=warmup)
            p = os.path.join(out_dir, f"view_{yaw:03.0f}.png")
            export_png(rt, p)
            got.append({"yaw": round(yaw, 2), "path": p, "camera": {k2: v for k2, v in cam.items() if k2 != "post"}})
    finally:
        remove_rig()
    sp = None
    if sheet:
        sp = _image.write(_sheet.contact_sheet([{"image": g["path"], "label": f"yaw {g['yaw']:.0f}"} for g in got],
                                               cell_width=min(width_px, 480), title=target),
                          os.path.join(out_dir, "sheet.png"))
    return {"views": got, "sheet": sp, "center": centre, "distance_cm": round(dist, 2)}


@op("view.sheet", mutates=True, idempotent=True)
def sheet(*, images: list, out: str, labels: list | None = None, cols: int = 0, cell_width_px: int = 480,
          title: str = "", statuses: list | None = None) -> dict:
    """A contact sheet from PNG files on the box: a grid of labelled frames in one image.

    Args: images: paths. out: the sheet's PNG path. labels: one per image (default the file names). cols: 0 picks a
    near-square grid. cell_width_px: each frame's width. title: a bar on top. statuses: ok|info|warn|fail per image
    (a coloured border).
    Returns: {"path", "width", "height", "cells", "changed": true}.
    Example: film-ue op view.sheet 'images=["/tmp/a.png","/tmp/b.png"]' out=/tmp/sheet.png title=compare
    """
    missing = [p for p in images if not os.path.isfile(p)]
    if missing:
        raise OpError(f"no image at {missing[0]}" + (f" (+{len(missing) - 1} more)" if len(missing) > 1 else ""),
                      code="not_found", hint="paths are on the box; view.still/view.stills write them")
    cells = []
    for k, p in enumerate(images):
        cells.append({"image": p, "label": (labels[k] if labels and k < len(labels) else os.path.basename(p)),
                      "status": statuses[k] if statuses and k < len(statuses) else None})
    im = _sheet.contact_sheet(cells, cols=cols, cell_width=cell_width_px, title=title)
    _image.write(im, out)
    return {"path": out, "width": im.w, "height": im.h, "cells": len(cells), "changed": True}


@op("view.overlay", mutates=True, idempotent=True)
def overlay(*, image: str, out: str, guides: list | None = None, boxes: list | None = None,
            points: list | None = None, caption: str = "", width_px: int = 0) -> dict:
    """Draw composition guides, labelled boxes and points on a copy of an image (no PIL needed).

    Args: image: PNG path. out: where the annotated copy goes. guides: any of thirds, safe (action 93% / title 90%),
    center, golden, headroom, grid:4x3, aspect:2.39 (masks to that aspect). boxes: [{"box": [x0,y0,x1,y1] (0..1),
    "label", "color": ok|info|warn|fail|[r,g,b]}]. points: [{"at": [x,y], "label"}]. caption: a text bar along the
    bottom. width_px: shrink first (0 keeps the size).
    Returns: {"path", "width", "height", "changed": true}.
    Example: film-ue op view.overlay image=/tmp/qa/a.png out=/tmp/qa/a_g.png 'guides=["thirds","safe"]'
    """
    if not os.path.isfile(image):
        raise OpError(f"no image at {image}", code="not_found")
    try:
        im = _overlay.overlay(_image.read(image), guides=guides or (), boxes=boxes or (), points=points or (),
                              caption=caption, width=width_px)
    except ValueError as e:
        raise OpError(str(e), code="bad_args") from None
    _image.write(im, out)
    return {"path": out, "width": im.w, "height": im.h, "changed": True}


@op("view.camera", mutates=False, idempotent=True)
def camera(*, camera: str = "", sequence: str = "", frame: int | None = None, width_px: int = 1920,
           height_px: int = 1080, points: dict | None = None, actors: list | None = None) -> dict:
    """Where things land in a camera's frame, without rendering: the camera as numbers, and world points or actors'
    bounds projected to frame fractions (u right, v down, 0..1).

    Args: camera: label ("" + sequence/frame: the cut's camera; the sequence is scrubbed there). points: {name:
    [x,y,z]}. actors: labels (their bounds' screen boxes). width_px/height_px: the output aspect.
    Returns: {"camera": {name, loc, rot, fov, aspect, focal?, sensor_width?}, "points": {name: {u, v, depth_cm,
    in_frame}}, "actors": {label: {box, in_frame, area}}, "aspect_mismatch"?}.
    Example: film-ue op view.camera camera=CamA 'actors=["Ada","Chair"]'
    """
    if sequence:
        if frame is None:
            raise OpError("sequence needs frame", code="bad_args")
        camera = camera or cut_camera(sequence, frame)
        from . import call
        call("seq.scrub", path=sequence, frame=int(frame))
    info = camera_info(camera, aspect=width_px / height_px)
    cam = _framing.Camera.from_dict(info)
    out = {"camera": {k: v for k, v in info.items() if k != "post"}, "points": {}, "actors": {}}
    ca = info.get("camera_aspect")
    if ca and abs(ca - width_px / height_px) / ca > 0.01:
        out["aspect_mismatch"] = (f"the camera's own aspect is {ca:.3f}, the output {width_px / height_px:.3f}: the "
                                  "horizontal field of view is kept, so the frame's height differs from the camera's")
    for name, p in (points or {}).items():
        u, v, d = cam.project(p)
        out["points"][name] = {"u": None if d <= 0 else round(u, 4), "v": None if d <= 0 else round(v, 4),
                               "depth_cm": round(d, 2), "in_frame": _framing.inside(u, v, d)}
    for lab in actors or []:
        o, e = _bounds(find_actor(lab))
        out["actors"][lab] = _framing.screen_box(cam, _framing.bounds_corners(o, e))
    return out
