"""Round 7 performance rows: is the presenter ACTING, not reading? (the operator, 07 Nov: "her expression is pale, no
emotion at all ... hands stuck to her body ... these presenters must look confident, happy, full of energy, not
robotic"). The numbers support the eye, never replace it.

FACE (rendered frames, MediaPipe's face blendshapes; runs where the frames are, i.e. on the box):
- face.expr_active_frac  speaking frames with a NON-MOUTH expression active (brows, cheeks, eye squint, smile)
- face.smile_events_per_min  Duchenne smiles: mouthSmile up WITH cheek or eye squint, held >= 4 frames
- face.brow_flash_per_min  brows up (inner or outer) for 0.12-1.0 s
- face.neutral_hold_max_s  the longest run of speaking frames with nothing active
Each channel is taken RELATIVE to the shot's own neutral (its 20th percentile), so a CG face's resting offsets and a
camera's angle do not read as expression.

BODY (bone samples from the editor, seq.sample of hand_l/hand_r; cm, the world's Z up):
- body.gesture_onsets_per_s  a hand going up off the desk, plus each beat while it is up, at least 0.25 s apart
- body.hands_above_desk_frac  speaking frames with either wrist bone more than 10 cm above the desk top (a forearm
  resting on the desk puts it ~6 cm up on her rig)
- body.wrist_travel_cm_per_s  mean hand speed while speaking (report; compare with v2b)

    film-qa perf-face FRAMES_DIR --fps 24 --speaking SPANS.json [--box x0,y0,x1,y1] [--out face.json]   # on the box
    film-qa perf-body SAMPLES.json --desk-z 71 --speaking SPANS.json [--out body.json]
SPANS.json: [[f0, f1_excl], ...] the frames where the presenter is speaking AND on screen.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

CHANNELS = ("browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekSquintLeft", "cheekSquintRight",
            "eyeSquintLeft", "eyeSquintRight", "mouthSmileLeft", "mouthSmileRight")
ACTIVE = 0.15  # above the shot's neutral, on MediaPipe's 0-1 scale
SMILE, SQUINT, BROW = 0.20, 0.10, 0.20
SMILE_HOLD_F, BROW_MIN_S, BROW_MAX_S = 4, 0.12, 1.0
HYST = 0.8  # an event ends below 80 % of its line
REST_CMS, MOVE_CMS, ONSET_GAP_S = 10.0, 25.0, 0.25
BEAT_CMS = 40.0
DESK_CLEAR_CM = 10.0  # her resting wrist bone sits ~6 cm over the desk top (v2b): 'up off the desk' is ~4 cm more


def _in(f: int, spans: list) -> bool:
    return any(a <= f < b for a, b in spans)


def _pct(xs: list, q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))] if s else 0.0


def face_rows(series: dict, fps: float, spans: list, lines: dict | None = None, neutral: bool = True) -> dict:
    """series: {frame: {channel: score}} -> the four face rows over the speaking frames in `spans`. `neutral`: take
    each channel relative to the shot's 20th percentile (rendered faces); curves are already zero at rest."""
    L = {"active": ACTIVE, "smile": SMILE, "squint": SQUINT, "brow": BROW, "brow_max_s": BROW_MAX_S, **(lines or {})}
    frames = sorted(f for f in series if _in(f, spans))
    if not frames:
        return {k: {"value": None, "error": "no speaking frame with a face"} for k in
                ("face.expr_active_frac", "face.smile_events_per_min", "face.brow_flash_per_min", "face.neutral_hold_max_s")}
    base = {c: (_pct([series[f].get(c, 0.0) for f in frames], 0.2) if neutral else 0.0) for c in CHANNELS}
    rel = {f: {c: series[f].get(c, 0.0) - base[c] for c in CHANNELS} for f in frames}

    def brow(r):
        return max(r["browInnerUp"], (r["browOuterUpLeft"] + r["browOuterUpRight"]) / 2)

    def smile(r):
        return (r["mouthSmileLeft"] + r["mouthSmileRight"]) / 2

    def squint(r):
        return max((r["cheekSquintLeft"] + r["cheekSquintRight"]) / 2, (r["eyeSquintLeft"] + r["eyeSquintRight"]) / 2)

    active = {f: brow(rel[f]) > L["active"] or smile(rel[f]) > L["active"] or squint(rel[f]) > L["active"] for f in frames}
    minutes = len(frames) / fps / 60.0
    # runs over consecutive frames only (a gap in the frame list ends a run)
    smiles, brows, hold, longest, run_s, run_b = 0, 0, 0, 0, 0, 0
    prev = None
    for f in frames:
        if prev is not None and f != prev + 1:
            run_s = run_b = hold = 0
        r = rel[f]
        # hysteresis (agent-04, round 7): ON at the line, OFF below HYST of it, so a held smile or raised brow whose
        # level drifts around the line is one event, not many
        on_s = smile(r) > L["smile"] and squint(r) > L["squint"]
        keep_s = smile(r) > HYST * L["smile"] and squint(r) > HYST * L["squint"]
        if (run_s and keep_s) or on_s:
            run_s += 1
            if run_s == SMILE_HOLD_F:
                smiles += 1
        else:
            run_s = 0
        if (run_b and brow(r) > HYST * L["brow"]) or brow(r) > L["brow"]:
            run_b += 1
        else:
            if BROW_MIN_S * fps <= run_b <= L["brow_max_s"] * fps:
                brows += 1
            run_b = 0
        hold = 0 if active[f] else hold + 1
        longest = max(longest, hold)
        prev = f
    where = f"{len(frames)} speaking frames ({minutes * 60:.1f} s)"
    return {"face.expr_active_frac": {"value": round(sum(active.values()) / len(frames), 3), "where": where},
            "face.smile_events_per_min": {"value": round(smiles / minutes, 2), "where": where},
            "face.brow_flash_per_min": {"value": round(brows / minutes, 2), "where": where},
            "face.neutral_hold_max_s": {"value": round(longest / fps, 2), "where": where}}


def face_rows_curves(curves: dict, fps: float, spans: list) -> dict:
    """The PRE-CHECK on the face anim's curves (agent-04, round 7), offline before box time: {frame: {control: value}}
    with MetaHuman CTRL_expressions_* names. Roles: brow = browRaiseIn / browRaiseOuter (L/R); squint = eyeCheekRaise /
    eyeSquintInner (L/R); smile = mouthCornerPull (L/R). Lines on the rig's scale (agent-04): active 0.15, smile
    corner pull 0.25 with cheek raise 0.2, a brow flash a rise of 0.2 for under 1.2 s. INFO: the gate reads the RENDER
    (face_rows on MediaPipe blendshapes), because the viewer sees pixels, not curves."""
    def pick(row, *keys):
        vals = [v for k, v in row.items() if any(x in k for x in keys)]
        return max(vals) if vals else 0.0
    series = {}
    for f, row in curves.items():
        b = pick(row, "browRaiseIn", "browRaiseOuter")
        q = pick(row, "eyeCheekRaise", "eyeSquintInner")
        m = pick(row, "mouthCornerPull")
        series[int(f)] = {"browInnerUp": b, "browOuterUpLeft": b, "browOuterUpRight": b, "cheekSquintLeft": q,
                          "cheekSquintRight": q, "eyeSquintLeft": q, "eyeSquintRight": q, "mouthSmileLeft": m,
                          "mouthSmileRight": m}
    out = face_rows(series, fps, spans, lines={"active": 0.15, "smile": 0.25, "squint": 0.20, "brow": 0.20,
                                                "brow_max_s": 1.2}, neutral=False)
    return {k.replace("face.", "face.curves_"): v for k, v in out.items()}


def face_track(paths: list, fps: float, box=None, model: str = "") -> dict:
    """{frame number: {channel: score}} from MediaPipe's face blendshapes on rendered frames (frame numbers from the
    file names)."""
    import re

    import numpy as np
    from PIL import Image

    from .qa_head import _model_path, _span
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=_model_path(model)),
                                        running_mode=vision.RunningMode.VIDEO, num_faces=2,
                                        output_face_blendshapes=True)
    out = {}
    with vision.FaceLandmarker.create_from_options(opts) as lm:
        for i, p in enumerate(paths):
            im = Image.open(p).convert("RGB")
            if box:
                W, H = im.size
                im = im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))
            res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(im)),
                                      int(round(i * 1000 / fps)))
            if not res.face_landmarks:
                continue
            k = max(range(len(res.face_landmarks)), key=lambda j: _span(res.face_landmarks[j]))
            f = int(re.findall(r"\d+", Path(p).stem)[-1])
            out[f] = {c.category_name: c.score for c in res.face_blendshapes[k] if c.category_name in CHANNELS}
    return out


def body_rows(samples: dict, fps: float, spans: list, desk_z: float, hands=("hand_l", "hand_r")) -> dict:
    """samples: {"frames": [f...], "bones": {name: [[x, y, z, ...], ...]}} (seq.sample) -> the three body rows.

    A hand is UP when its wrist bone is more than DESK_CLEAR_CM above the desk top (a forearm resting on the desk puts
    it ~6 cm up on her rig: v2b's resting wrists read 76.7-77.0 over a 71 cm top). A GESTURE onset is the hand going
    UP (one per lift, its return to the desk is not another), plus each BEAT while it stays up: the speed rising from
    under REST_CMS past BEAT_CMS while not moving down toward the desk, >= ONSET_GAP_S after the last onset."""
    fr = samples["frames"]
    idx = [i for i, f in enumerate(fr) if _in(f, spans)]
    keys = ("body.gesture_onsets_per_s", "body.hands_above_desk_frac", "body.wrist_travel_cm_per_s")
    if len(idx) < 3:
        return {k: {"value": None, "error": "fewer than 3 speaking frames sampled"} for k in keys}
    line = desk_z + DESK_CLEAR_CM
    onsets, above, travel, n = 0, 0, 0.0, 0
    last = {h: -1e9 for h in hands}
    up = {h: False for h in hands}
    slow = {h: True for h in hands}
    for i in idx:
        Z = {h: samples["bones"][h][i][2] for h in hands}
        if any(z > line for z in Z.values()):
            above += 1
        cont = i > 0 and fr[i] == fr[i - 1] + 1
        for h in hands:
            was_up, up[h] = up[h], Z[h] > line
            if not cont:
                continue
            a, b = samples["bones"][h][i - 1], samples["bones"][h][i]
            v = math.dist(a[:3], b[:3]) * fps
            travel += v
            n += 1
            onset = False
            if up[h] and not was_up:
                onset = True  # the hand goes up off the desk
            elif up[h] and slow[h] and v > BEAT_CMS and b[2] - a[2] > -0.5 * v / fps:
                onset = True  # a beat in the air (not the return toward the desk)
            if onset and (fr[i] - last[h]) / fps >= ONSET_GAP_S:
                onsets += 1
                last[h] = fr[i]
            slow[h] = v < REST_CMS
    secs = len(idx) / fps
    where = f"{len(idx)} speaking frames ({secs:.1f} s), desk top z {desk_z}, up = wrist > {line:.1f}"
    return {"body.gesture_onsets_per_s": {"value": round(onsets / secs, 3), "where": where},
            "body.hands_above_desk_frac": {"value": round(above / len(idx), 3), "where": where},
            "body.wrist_travel_cm_per_s": {"value": round(travel / max(1, n), 2), "where": where}}


def _spans(path: str) -> list:
    return [[int(a), int(b)] for a, b in json.loads(Path(path).read_text())]
