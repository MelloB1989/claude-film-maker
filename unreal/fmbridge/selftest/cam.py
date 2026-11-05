"""WP7's acceptance test: cameras and shooting, measured on real renders.

It proves, in a scratch level lit by one directional light on black:
- the lens maths is the engine's: cam.describe's fields of view equal CineCameraComponent's own
  (GetHorizontal/VerticalFieldOfView) for several filmbacks and focal lengths, and lens limits widen instead of
  clamping;
- projection is right where it matters, on pixels: small spheres placed with camkit.lens.unproject at chosen (u, v)
  render with their centres there (within 1.5% of the frame), on a 16:9 and a 4:3 filmback;
- the framing solver frames: a 175 cm stand-in figure framed WS / MCU / CU renders with the top of the figure on the
  row the solver predicted (within 2.5% of the frame height), from the front and from 3/4;
- cam.add / cam.frame / cam.coverage / shot.apply converge (a second run changes nothing); errors are actionable;
- shot grammar in words both ways: cam.shoot frames from a sentence and cam.describe's words read back unchanged;
- moves and rigs are what Sequencer plays: a push-in's and a rail's camera positions read back at mid-shot equal the
  baked keys; the edit read back (shot.describe) is the spec's cuts; shot.check finds no crossed line;
- a contact sheet and stills with guides are written (artifacts in the report).

Takes about 2-3 minutes (about 20 stills at 480x270 and a 9-cell contact sheet). Needs: a GPU (stills). No Epic
login, no assets beyond the engine's basic shapes. Leaves nothing outside /Game/_Selftest/cam.
"""
from __future__ import annotations

import math

import unreal

from fmbridge.camkit import lens, png
from fmbridge.ops._scrub import set_frame
from ..ops.assets import EAL  # EditorAssetLibrary, or the EditorAssetSubsystem when its plugin is off

REQUIRES = ["gpu"]
AREAS = ["cam", "shot"]
NEEDS_LEVEL = True
TIMEOUT = 900

W, H = 480, 270
LSE = unreal.LevelSequenceEditorBlueprintLibrary


def _bright(img, frac: float = 0.35):
    """The bright pixels' bounding rows/columns and centroid (u, v): what a lit shape on black covers."""
    mx = 0
    for i in range(0, len(img.px), 3):
        s = img.px[i] + img.px[i + 1] + img.px[i + 2]
        if s > mx:
            mx = s
    thr = max(30, mx * frac)
    xs = ys = n = 0
    top, bottom, left, right = img.h, -1, img.w, -1
    for y in range(img.h):
        row = y * img.w * 3
        for x in range(img.w):
            i = row + 3 * x
            if img.px[i] + img.px[i + 1] + img.px[i + 2] >= thr:
                xs += x
                ys += y
                n += 1
                top, bottom = min(top, y), max(bottom, y)
                left, right = min(left, x), max(right, x)
    if not n:
        return None
    return {"u": (xs / n + 0.5) / img.w, "v": (ys / n + 0.5) / img.h, "top": top / img.h,
            "bottom": (bottom + 1) / img.h, "left": left / img.w, "right": (right + 1) / img.w, "pixels": n}


def _still(t, cam: str, name: str, height: int = H):
    """A still through `cam` (no guides) and what is bright in it."""
    p = t.path(f"{name}.png")
    yield from t.op("look.still", camera_label=cam, path=p, width=W, height=height)
    t.artifact(p)
    return _bright(png.read(p))


def _rim_top(cam: dict, x: float, y: float, rx: float, ry: float, z: float) -> float:
    """The highest row (v) of an upright elliptic cylinder's top rim (centre x, y, half-widths rx, ry, at height z):
    where the top of its silhouette renders."""
    vs = [lens.project(cam, (x + rx * math.cos(a), y + ry * math.sin(a), z)) for a in
          (i * math.pi / 90 for i in range(180))]
    return min(q["v"] for q in vs if q["depth"] > 0)


def run(t):
    P = t.prefix
    s = getattr(t, "scratch", None)
    root = str((s() if callable(s) else s) or "/Game/_Selftest/cam").rstrip("/")
    t.op("level.spawn", label=P + "Sun", cls="DirectionalLight", loc=[0, 0, 500],
         rot_={"pitch": -50, "yaw": 30, "roll": 0})

    # --- 1. fields of view are the engine's ------------------------------------------------------------------
    cam = P + "Lens"
    t.op("cam.add", label=cam, loc=[0, 0, 100], rot_={"pitch": 0, "yaw": 0, "roll": 0})
    for fb, f in (("16:9 Digital Film", 35), ("16:9 DSLR", 50), ("Super 35mm", 85), ("Super 16mm", 12)):
        d = t.op("cam.set", label=cam, filmback=fb, focal_mm=f)
        comp = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
                    if a.get_actor_label() == cam).get_cine_camera_component()
        t.check(f"hfov {fb} {f}mm = engine", d["hfov_deg"], comp.get_horizontal_field_of_view(), tol=0.01)
        t.check(f"vfov {fb} {f}mm = engine", d["vfov_deg"], comp.get_vertical_field_of_view(), tol=0.01)
    wide = t.op("cam.set", label=cam, focal_mm=1500, aperture=0.95)
    t.check("focal beyond the lens widens it, not clamped", [wide["focal"], wide["aperture"]], [1500, 0.95], tol=1e-3)
    t.idempotent("cam.add converges", "cam.add", label=cam, loc=[0, 0, 100], focal_mm=1500)
    t.raises("a missing camera is not_found", "cam.set", code="not_found", label=P + "Nope", focal_mm=50)
    t.raises("a bad size is bad_args", "cam.frame", code="bad_args", camera=cam, subjects=P + "Sun", size="giant")
    t.op("cam.remove", labels=[cam])

    # --- 2. projection on pixels: markers placed at (u, v) render there -----------------------------------------
    for fb in ("16:9 Digital Film", "Super 35mm"):
        cam = P + "Proj"
        cd = t.op("cam.add", label=cam, loc=[0, 0, 150], rot_={"pitch": -5, "yaw": 20, "roll": 0}, focal_mm=35,
                  filmback=fb)
        errs = []
        for k, (u, v, depth) in enumerate(((0.5, 0.5, 600), (0.25, 0.3, 500), (0.72, 0.66, 800))):
            p = lens.unproject(cd, u, v, depth)
            size = 0.02 * lens.frame_height_at(cd, depth)  # about 2% of the frame tall
            t.op("level.spawn", label=P + "Dot", shape="sphere", loc=list(p), size=[size, size, size])
            # the still at the filmback's own aspect: the image is the picture. (Day 1: a 16:9 still of a Super 35
            # back is the whole picture stretched to 16:9, not pillarboxed: markers read 1.34x too far out.)
            b = yield from _still(t, cam, f"proj_{fb.replace(' ', '_').replace(':', '')}_{k}",
                                  height=round(W / lens.aspect(fb)))
            if b is None:
                t.ok(f"marker {k} visible on {fb}", False, detail="nothing bright in the still")
                continue
            bu, bv = b["u"], b["v"]
            errs.append(max(abs(bu - u), abs(bv - v)))
            t.check(f"marker {k} at (u, v) on {fb}", [round(bu, 3), round(bv, 3)], [u, v], tol=0.015)
        if errs:
            t.metric(f"projection_error_max_{fb}", round(max(errs), 4), "frame")
        t.op("level.delete", labels=[P + "Dot", cam])

    # --- 3. the solver frames a figure: top of the figure on the predicted row --------------------------------------
    fig = P + "Figure"
    t.op("level.spawn", label=fig, shape="cylinder", loc=[0, 0, 87.5], size=[40, 30, 175])
    for size, angle in (("WS", 0), ("MCU", "3/4"), ("CU", "3/4")):
        cam = P + "Frame_" + size
        r = t.op("cam.frame", camera=cam, subjects=fig, size=size, angle=angle, side="left", focal_mm=50, mode="bounds")
        t.ok(f"{size} solved", r["solve"]["error"] is not None and r["solve"]["error"] < 1e-3,
             detail=str(r["solve"]["warnings"]))
        # the stand-in is a flat-topped cylinder: its silhouette's top is the near rim of its top face, which a close
        # camera below it sees above the axis point the solver frames (day 1: CU 0.015 vs 0.05). Predict the rim.
        pred_top = _rim_top(r["camera"], 0.0, 0.0, 20.0, 15.0, 175.0)
        b = yield from _still(t, cam, f"frame_{size}")
        if b:
            t.check(f"{size}: the figure's top on the predicted row", round(b["top"], 3), round(pred_top, 3), tol=0.025)
            t.note(f"{size}: solver's head_top v {r['solve']['predicted'][fig]['head_top'][1]:.3f}, rim {pred_top:.3f}")
            if size == "WS":
                pred_feet = r["solve"]["predicted"][fig]["feet"][1]
                t.check("WS: the feet on the predicted row", round(b["bottom"], 3), round(pred_feet, 3), tol=0.03)
            else:
                t.ok(f"{size}: the figure runs off the bottom edge", b["bottom"] > 0.97, detail=str(b))
        t.idempotent(f"cam.frame {size} converges", "cam.frame", camera=cam, subjects=fig, size=size, angle=angle,
                     side="left", focal_mm=50, mode="bounds")
        chk = t.op("cam.check", camera=cam, subjects=fig, size=size)
        t.note(f"cam.check {size}: " + "; ".join(f"{i['severity']} {i['code']}" for i in chk["issues"]) or "clean")
    p = t.path("frame_MCU_guides.png")
    g = yield from t.op("cam.still", camera=P + "Frame_MCU", out=p, width=W * 2, height=H * 2, subjects=fig)
    t.artifact(g["path"])
    proj = t.op("cam.project", camera=P + "Frame_MCU", subjects=fig)
    t.check("cam.project agrees: MCU", proj["points"][fig]["size"]["size"], "MCU")
    t.check("cam.point of an actor", t.op("cam.point", target=fig)["point"], [0, 0, 87.5], tol=0.5)
    sh_ = t.op("cam.shoot", camera=P + "Words", text=f"medium shot of {fig} from 40 degrees right, high angle, 35mm")
    said = t.op("cam.describe", label=P + "Words", subjects=fig)["cameras"][0]["words"]
    t.ok("cam.shoot: words in, words out", said.startswith(f"MS of {fig} from 3/4 right (40 deg), high angle, 35 mm"),
         detail=said)
    t.check("cam.shoot reads its own words back without moving", t.op("cam.shoot", camera=P + "Words",
                                                                       text=said)["changed"], False)
    t.note(f"cam.shoot parsed {sh_['parsed']}")

    # --- 4. moves and rigs, read back from Sequencer ----------------------------------------------------------------
    seq = root + "/" + P + "Seq"
    t.op("seq.new", path=seq, start=0, end=96, fps=24, replace=True)
    cam = P + "Move"
    t.op("cam.frame", camera=cam, subjects=fig, size="WS", angle=20, focal_mm=35, mode="bounds")
    mv = yield from t.op("cam.move", camera=cam, sequence=seq, moves_=[{"move": "push_in", "fraction": 0.4, "frames": 48}],
              start_frame=0, end_frame=96, step=4, aim=fig, focus_on=fig)
    t.ok("cam.move keyed", mv["keys"]["transform"] > 5, detail=str(mv["keys"]))
    LSE.open_level_sequence(EAL.load_asset(seq))
    for f, want in ((48, mv["last"]["loc"]),):
        set_frame(f + 1)
        yield
        set_frame(f)
        for _ in range(3):
            yield
        got = t.op("cam.describe", label=cam)["cameras"][0]["loc"]
        t.check(f"push-in: Sequencer plays the baked key at {f}", got, want, tol=0.5)
    rail, rcam = P + "Rail", P + "RailCam"
    t.op("cam.add", label=rcam, loc=[500, -200, 150], focal_mm=24)
    t.op("cam.rig", label=rail, kind="rail", points=[[500, -200, 150], [500, 200, 150]], camera=rcam)
    t.op("cam.rig_move", rig_label=rail, sequence=seq, keys=[[0, {"position": 0}], [96, {"position": 1}]])
    LSE.refresh_current_level_sequence()
    set_frame(49)
    yield
    set_frame(48)
    for _ in range(3):
        yield
    # Sequencer writes CurrentPositionOnRail straight to the property; the mount follows only in
    # UpdateRailComponents, which runs from Tick and PostEditChangeProperty (CameraRig_Rail.cpp:205-228). Day 1 in
    # the offscreen editor the camera stayed at the rail's start (y=-200): check the two halves apart.
    ra = next(x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
              if x.get_actor_label() == rail)
    pos = float(ra.get_editor_property("current_position_on_rail"))
    y = t.op("cam.describe", label=rcam)["cameras"][0]["loc"][1]
    t.check("rail: Sequencer plays the rail position at mid-shot", round(pos, 3), 0.5, tol=0.05)
    t.note(f"rail: the camera after the scrub alone at y={y:.1f} (the mount moves on the rig's tick)")
    ra.set_editor_property("current_position_on_rail", pos)  # PostEditChangeProperty -> UpdateRailComponents
    yield
    y = t.op("cam.describe", label=rcam)["cameras"][0]["loc"][1]
    t.ok("rail: the camera is near the middle of the rail at mid-shot", abs(y) < 40, detail=f"y={y:.1f} pos={pos:.3f}")
    LSE.close_level_sequence()

    # --- 5. coverage and a shot list -------------------------------------------------------------------------
    a, b_ = P + "A", P + "B"
    t.op("level.spawn", label=a, shape="cylinder", loc=[0, -90, 87.5], size=[40, 30, 175], rot_={"yaw": 90})
    t.op("level.spawn", label=b_, shape="cylinder", loc=[0, 90, 85], size=[40, 30, 170], rot_={"yaw": -90})
    t.op("level.delete", labels=[fig])
    cov = t.op("cam.coverage", subjects=[a, b_], side="left", prefix=P + "Cov_")
    t.check("coverage stays on one side of the line", cov["issues"], [])
    t.metric("coverage_shots", len(cov["shots"]))
    t.idempotent("cam.coverage converges", "cam.coverage", subjects=[a, b_], side="left", prefix=P + "Cov_")
    # cam.coverage names a camera {prefix}{shot name}, and a single's shot name starts with the subject's label
    covcam = {s["name"]: s["camera"] for s in cov["shots"]}
    t.check("coverage names its cameras by the subjects' labels", [covcam.get("master"), covcam.get(a + "_OTS")],
            [P + "Cov_master", P + "Cov_" + a + "_OTS"])
    yield from t.still("coverage_master", camera=covcam.get("master"), width=W, height=H)
    yield from t.still("coverage_A_OTS", camera=covcam.get(a + "_OTS"), width=W, height=H)
    t.op("cam.remove", prefix=P + "Cov_")
    spec = {"kind": "shot", "version": 1, "name": "selftest", "sequence": root + "/" + P + "Scene", "fps": 24,
            "lines": [{"id": "L1", "speaker": "A", "start_s": 1.0, "end_s": 3.0},
                      {"id": "L2", "speaker": "B", "start_s": 3.5, "end_s": 6.0}],
            "subjects": {"A": {"actor": a, "mode": "bounds"}, "B": {"actor": b_, "mode": "bounds"}},
            "defaults": {"camera_prefix": P + "Shot_"},
            "shots": [{"id": "S1", "start": 0, "frame": {"subjects": ["A", "B"], "size": "WS", "focal_mm": 28}},
                      {"id": "S2", "start": "L1.start-4f", "frame": {"subjects": ["A"], "size": "MCU", "angle": 30},
                       "moves": [{"move": "push_in", "fraction": 0.15}], "noise": "subtle"},
                      {"id": "S3", "start": "L2.start-4f", "coverage": "B_OTS"}]}
    pl = t.op("shot.plan", spec=spec)
    t.check("shot.plan cuts", pl["cuts"], [[P + "Shot_S1", 0], [P + "Shot_S2", 20], [P + "Shot_S3", 80]])
    ap = yield from t.op("shot.apply", spec=spec)
    t.ok("shot.apply made the cameras", len(ap["cameras"]) == 3, detail=str(ap["cameras"]))
    t.idempotent("shot.apply converges", "shot.apply", spec=spec)
    d = t.op("shot.describe", sequence=spec["sequence"], subjects=[a])
    t.check("shot.describe reads the edit back", [[c["camera"], c["start"]] for c in d["cuts"]], pl["cuts"])
    ck = yield from t.op("shot.check", sequence=spec["sequence"], subjects=[a, b_])
    t.check("shot.check: no crossed line", [i["code"] for i in ck["issues"] if i["code"] == "shot.line_180"], [])
    t.note("shot.check: " + "; ".join(f"{i['severity']} {i['code']} {i.get('camera')}" for i in ck["issues"]))
    sh = yield from t.op("shot.sheet", sequence=spec["sequence"], out_dir=t.path("sheet"), per_shot=3, cell_w=320)
    t.artifact(sh["path"])
    t.check("contact sheet: 3 stills per shot", len(sh["stills"]), 9)
    spec2 = {**spec, "shots": spec["shots"][:2]}
    r2 = yield from t.op("shot.apply", spec=spec2)
    t.check("a dropped shot's camera is removed", r2["removed"], [P + "Shot_S3"])
    LSE.close_level_sequence()
    return {"projection": "see metrics", "coverage": [s["name"] for s in cov["shots"]]}
