"""film-qa head: does the head move with the blinks, as the viewer sees it? The render-level twin of the editor's
qa.head_stability (round 5; round 4, the operator on her: "every time she blinks her head nods a little down like a
jitter"), on frames already pulled from the box.

Per frame: MediaPipe's Face Landmarker (CPU, Tasks API, VIDEO mode) gives 478 landmarks, the eyeBlinkLeft/Right
blendshapes and a facial transformation matrix. The head's pitch is measured twice:

- `pnp`: OpenCV solvePnP on RIGID landmarks only (nose bridge and tip, the eyes' outer and inner corners, the
  face's sides by the ears, the forehead), against the face's own first frame as the 3-D model. Lids, brows,
  cheeks and the jaw are left out: a blink squeezes the cheeks up and the brow down, and a tracker that uses them
  reads that as the head pitching down (a known blink artifact of landmark trackers).
- `matrix`: MediaPipe's own transformation matrix (all landmarks): reported for comparison. A nod in `matrix`
  but not in `pnp` is the tracker's artifact, not the head.

The blinks come from the blendshapes (threshold: half the shot's own peak, at least 0.35: CG eyes rarely score 1).
Then perfkit.stability judges the pnp pitch with render limits (landmark noise is ~0.1-0.3 deg a frame, so the
nod line is 0.8 deg and buzz is not judged unless asked).

    film-qa head DIR --fps 24 [--box x0,y0,x1,y1] [--first-frame N] [--out RESULT.json]
    film-qa head-samples QA_OUT.json        re-judge the samples qa.head_stability saved (out=), offline

Needs mediapipe (not a default dependency): `uv run --with mediapipe==0.10.21 film-qa head ...`; the model
(face_landmarker.task, float16/1) is fetched once into ~/.cache/film-qa/ (or give --model).
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FMB = ROOT / "unreal" / "fmbridge"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/"
             "face_landmarker.task")
# MediaPipe face-mesh indices that ride the skull: nose bridge/tip, eye corners (canthi), the sides by the ears,
# forehead. Not lids, brows, cheeks, lips or chin.
RIGID = (168, 6, 197, 195, 5, 4, 1, 33, 133, 263, 362, 234, 454, 127, 356, 10, 151, 9)
RENDER_LIMITS = {"nod_deg": 0.8, "bta_deg": 0.45, "jitter_rms_deg": 0.6, "spike_deg": 2.5}
IMAGE_EXT = (".png", ".jpg", ".jpeg")


def stability():
    """perfkit.stability from this checkout (engine-free)."""
    if str(FMB) not in sys.path:
        sys.path.insert(0, str(FMB))
    from perfkit import stability as ST  # noqa: E402
    return ST


def euler_pitch(R) -> float:
    """Pitch (deg, + = chin up in an image whose y points down and z away from the camera) of a 3x3 rotation:
    the rotation about the camera's x axis."""
    return math.degrees(math.atan2(-R[1][2], R[2][2]))


def rel_pose(model, pts, size) -> tuple:
    """(pitch, yaw, roll) degrees of `pts` (N x 2 pixels) against `model` (N x 3, the first frame's landmarks in
    pixels with depth), from cv2.solvePnP with a pinhole camera of focal = the image width."""
    import cv2
    import numpy as np
    w, h = size
    K = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float64)
    ok, rvec, _ = cv2.solvePnP(np.asarray(model, dtype=np.float64), np.asarray(pts, dtype=np.float64), K, None,
                               flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return (float("nan"),) * 3
    R, _ = cv2.Rodrigues(rvec)
    pitch = math.degrees(math.atan2(R[2][1], R[2][2]))
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, -R[2][0]))))
    roll = math.degrees(math.atan2(R[1][0], R[0][0]))
    return pitch, yaw, roll


def model_from(lms, size) -> list:
    """The first frame's rigid landmarks as a 3-D model in pixels (MediaPipe z is scaled like x), centred."""
    w, h = size
    pts = [[lms[i][0] * w, lms[i][1] * h, lms[i][2] * w] for i in RIGID]
    c = [sum(p[k] for p in pts) / len(pts) for k in range(3)]
    return [[p[0] - c[0], p[1] - c[1], p[2] - c[2]] for p in pts]


def _model_path(given: str = "") -> str:
    if given:
        return given
    cache = Path(os.path.expanduser("~/.cache/film-qa"))
    p = cache / "face_landmarker.task"
    if not p.exists():
        cache.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, p)
    return str(p)


def track(paths: list, fps: float, box=None, model: str = "") -> dict:
    """Per-frame landmarks of the one face in `box` (fractions [x0, y0, x1, y1] of the frame; default the whole
    frame, the largest face) -> {"times", "pitch", "yaw", "roll" (pnp), "pitch_matrix", "blink", "missing"}."""
    if importlib.util.find_spec("mediapipe") is None:
        raise SystemExit("film-qa head needs mediapipe: uv run --with mediapipe==0.10.21 film-qa head ...")
    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision
    from PIL import Image
    opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=_model_path(model)),
                                        running_mode=vision.RunningMode.VIDEO, num_faces=2,
                                        output_face_blendshapes=True, output_facial_transformation_matrixes=True)
    out = {"times": [], "pitch": [], "yaw": [], "roll": [], "pitch_matrix": [], "blink": [], "missing": []}
    base = None
    with vision.FaceLandmarker.create_from_options(opts) as lm:
        for i, p in enumerate(paths):
            im = Image.open(p).convert("RGB")
            if box:
                W, H = im.size
                im = im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))
            size = im.size
            res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(im)),
                                      int(round(i * 1000 / fps)))
            if not res.face_landmarks:
                out["missing"].append(i)
                continue
            k = max(range(len(res.face_landmarks)), key=lambda j: _span(res.face_landmarks[j]))
            lms = [(q.x, q.y, q.z) for q in res.face_landmarks[k]]
            if base is None:
                base = model_from(lms, size)
            pts = [[lms[j][0] * size[0], lms[j][1] * size[1]] for j in RIGID]
            pitch, yaw, roll = rel_pose(base, pts, size)
            scores = {c.category_name: c.score for c in res.face_blendshapes[k]}
            M = res.facial_transformation_matrixes[k]
            out["times"].append(i / fps)
            out["pitch"].append(pitch)
            out["yaw"].append(yaw)
            out["roll"].append(roll)
            out["pitch_matrix"].append(euler_pitch(M))
            out["blink"].append(max(scores.get("eyeBlinkLeft", 0.0), scores.get("eyeBlinkRight", 0.0)))
    return out


def _span(lms) -> float:
    xs = [q.x for q in lms]
    return max(xs) - min(xs)


def judge(tr: dict, limits: dict | None = None, threshold: float | None = None) -> dict:
    """perfkit.stability on a track (see `track`): the pnp pitch judged, the matrix pitch's blink_nod alongside.
    Frames where no face was found are filled from their neighbours (interpolated) before judging."""
    ST = stability()
    t = tr["times"]
    if len(t) < 16:
        return {"pass": False, "issues": [{"code": "head.too_few_frames", "severity": "fail",
                                           "message": f"a face in {len(t)} frames: too few to judge"}], "metrics": {}}
    peak = max(tr["blink"]) if tr["blink"] else 0.0
    thr = threshold if threshold is not None else max(0.35, 0.5 * peak)
    spans = ST.blink_windows(t, tr["blink"], thr) if peak >= 0.35 else []
    lim = {**RENDER_LIMITS, **(limits or {})}
    r = ST.check(t, tr["pitch"], spans, tr["yaw"], tr["roll"], limits=lim, source="render")
    rm = ST.check(t, tr["pitch_matrix"], spans, limits=lim, source="render")
    issues = []
    for c in r["checks"]:
        if not c["pass"]:
            issues.append({"code": f"head.{c['name']}", "severity": "fail", "message": c["why"],
                           "value": c["metric"], "expected": c["threshold"],
                           "fix": "perf.face blink_head=still solver_head=replace; then qa.head_stability in the "
                                  "editor names the frames"})
    nm = next((c for c in rm["checks"] if c["name"] == "blink_nod"), None)
    np_ = next((c for c in r["checks"] if c["name"] == "blink_nod"), None)
    if nm and np_ and not nm["pass"] and np_["pass"]:
        issues.append({"code": "head.tracker_artifact", "severity": "info",
                       "message": "MediaPipe's matrix pitch nods with the blinks but the rigid landmarks do not: the "
                                  "tracker reads the lids and cheeks, the head is still"})
    if not spans:
        issues.append({"code": "head.no_blinks", "severity": "warn",
                       "message": f"no blink seen (eyeBlink peak {peak:.2f}): the blink checks did not run"})
    fail = any(i["severity"] == "fail" for i in issues)
    return {"pass": not fail, "issues": issues,
            "metrics": {c["name"]: c["metric"] for c in r["checks"]},
            "matrix_metrics": {c["name"]: c["metric"] for c in rm["checks"]},
            "blinks": r["blinks"], "bta": r["bta"], "blink_threshold": round(thr, 3),
            "missing_frames": len(tr.get("missing", []))}


def frames_in(folder: str) -> list:
    return sorted(str(p) for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXT)


def samples(path: str, limits: dict | None = None) -> dict:
    """Re-judge what qa.head_stability saved with out= (the bone samples and blink curve), offline."""
    ST = stability()
    d = json.loads(Path(path).read_text())
    s = d["samples"]
    h = ST.from_bones(s["frames"], s["fps"], s["bone"], s["forward"])
    t = [x - h["times"][0] for x in h["times"]]
    spans = ST.blink_windows(t, s["closure"]) if s.get("closure") else []
    r = ST.check(t, h["pitch"], spans, h["yaw"], h["roll"], limits=limits, source="bones")
    return {"pass": r["pass"], "failed": r["failed"], "metrics": {c["name"]: c["metric"] for c in r["checks"]},
            "checks": r["checks"], "blinks": r["blinks"], "edge": r["edge"], "bta": r["bta"],
            "jitter": r["jitter"]}


GATE_LINE_DEG = 0.6  # head.blink_nod_deg: the worst blink's pitch departure, both presenters, every shot
GATE_LOCKED_DEG = 0.3  # head.blink_locked_deg: the blink-triggered average's peak (a small nod on every blink)


def gate(results: list, line: float = GATE_LINE_DEG, locked_line: float = GATE_LOCKED_DEG) -> dict:
    """agent-09's gate v2 numbers file from qa.head_stability results (their out= JSON, or the op's return saved
    as JSON; one per presenter and shot range): {"gate": {"head.blink_nod_deg": {"value", "where"},
    "head.blink_locked_deg": {"value", "where"}}}: the worst |nod_deg| over every blink of every result, and the
    worst blink-triggered average peak. A result with no blinks, or that failed to load, is an error on both (the
    gate fails a number it cannot measure)."""
    worst, where, errors = 0.0, "", []
    locked, lwhere = 0.0, ""
    for p in results:
        try:
            d = json.loads(Path(p).read_text())
        except (OSError, ValueError) as e:
            errors.append(f"{p}: {e}")
            continue
        if d.get("samples"):  # qa.head_stability's out=: judge its samples afresh (the r5 box's first files
            r = samples(p)    # carried no blinks from the op's clock bug; the samples were right)
            fr = d["samples"]["frames"]
            d = {**d, "blinks": r["blinks"], "bta": r["bta"], "frames": [fr[0], fr[-1]], "fps": d["samples"]["fps"]}
        blinks = d.get("blinks") or []
        if not blinks:
            errors.append(f"{Path(p).name}: no blinks measured")
            continue
        f0, fps = (d.get("frames") or [0])[0], d.get("fps") or 24.0
        who = d.get("label", Path(p).stem)
        b = max(blinks, key=lambda x: abs(x["nod_deg"]))
        if abs(b["nod_deg"]) >= abs(worst):
            worst = b["nod_deg"]
            f = int(f0 + round(b["t"] * fps))
            where = f"{who} f{f - 3}-{f + 9}"
        pk = (d.get("bta") or {}).get("peak_deg", 0.0)
        if pk >= locked:
            locked = pk
            lwhere = f"{who} f{f0}-{(d.get('frames') or [0, 0])[-1]} ({len(blinks)} blinks)"
    nod = {"value": round(abs(worst), 3), "where": where, "line": line, "signed_deg": round(worst, 3)}
    lk = {"value": round(locked, 3), "where": lwhere, "line": locked_line}
    if errors:
        nod["error"] = lk["error"] = "; ".join(errors)
    return {"gate": {"head.blink_nod_deg": nod, "head.blink_locked_deg": lk}}
