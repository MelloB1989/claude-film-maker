"""head.py offline: the plan keeps its rules, and the judge passes a lively synthetic head and fails a frozen one."""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import head as H  # noqa: E402

FPS = 24


def _cue():
    words, t = [], 0.4
    for i in range(150):
        words.append({"w": f"w{i}", "t0": round(t, 3), "t1": round(t + 0.28, 3)})
        t += 0.33 + (0.5 if i % 9 == 8 else 0.0)
    return {"fps": FPS, "start": 0, "length_s": 60.0, "words": words,
            "on_cam": [[0.0, 14.0, "CamA"], [20.0, 38.0, "CamB"], [45.0, 60.0, "CamA"]]}


def test_plan_rules():
    cue = _cue()
    p = H.plan(cue, "him")
    assert p["blink_head"] == "still" and p["solver_head"] == "replace"
    gl = p["glances"]
    assert 2 <= len(gl) <= 6
    for g in gl:
        sp = H._span_of(g["t"], cue["on_cam"])
        assert sp and g["t"] - sp[0] >= H.CUT_MARGIN and sp[1] - g["back"] >= H.CUT_MARGIN
        assert 8.0 <= abs(g["yaw"]) <= 13.0
        assert any(a <= g["t"] <= b for a, b in p["avoid_blinks"])
    assert H.plan(cue, "him") == p  # seeded
    assert "glances" not in H.face_args(cue, "him")


def _rot(yaw, pitch):
    y, p = math.radians(yaw), math.radians(pitch)
    fwd = [math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)]
    side = [-math.sin(y), math.cos(y), 0.0]
    up = list(np.cross(fwd, side))
    return fwd, side, up


def _files(tmp, alive=True):
    n = 60 * FPS
    t = np.arange(n) / FPS
    rng = np.random.default_rng(1)
    if alive:
        yaw = 0.4 * np.sin(2 * math.pi * 0.13 * t) + 0.25 * np.sin(2 * math.pi * 0.31 * t + 1)
        pitch = 0.3 * np.sin(2 * math.pi * 0.21 * t)
        for c in np.arange(0.8, 60, 6.6):  # beat nods, clear of the blinks
            pitch -= 1.2 * np.exp(-((t - c) / 0.12) ** 2)
    else:
        yaw, pitch = np.zeros(n), np.zeros(n)
    closure = np.zeros(n)
    for c in np.arange(2.3, 60, 3.3):  # blinks, head still through them
        closure[(t > c) & (t < c + 0.2)] = 1.0
    bone = []
    for y, p in zip(yaw, pitch):
        f, s, u = _rot(y, p)
        bone.append([0, 0, 160] + f + s + u)
    (tmp / "head.json").write_text(json.dumps({"label": "Host", "samples": {
        "frames": list(range(n)), "fps": FPS, "bone": bone, "forward": [1, 0, 0], "closure": list(closure)}}))
    cam = [300.0, 0.0, 160.0]
    spans = []
    for f0, f1, c in H.on_cam_frames(_cue()):
        bones = {"head": [], "FACIAL_L_Eye": [], "FACIAL_R_Eye": []}
        cams = []
        for f in range(f0, f1):
            tt = f / FPS
            gy = 0.4 * ((int(tt / 0.6) % 3) - 1) * (1 if alive else 0)  # fixational steps
            gy += 11.0 if alive and ((tt - 3.0) % 10) < 0.8 else 0.0  # thinking glances
            for e, dy in (("FACIAL_L_Eye", 3.0), ("FACIAL_R_Eye", -3.0)):
                d = np.array(cam) - np.array([8.0, dy, 165.0])
                base = math.degrees(math.atan2(d[1], d[0]))
                fw, sd, upv = _rot(base + gy, 0.0)
                bones[e].append([8.0, dy, 165.0] + sd + fw + upv)  # the gaze is the bone's Y axis
            bones["head"].append(bone[f])
            cams.append(cam)
        spans.append({"frames": list(range(f0, f1)), "camera": c, "cam": cams, "bones": bones})
    (tmp / "eyes.json").write_text(json.dumps({"spans": spans}))
    return str(tmp / "head.json"), str(tmp / "eyes.json")


def test_judge_alive_and_frozen(tmp_path):
    h, e = _files(tmp_path, alive=True)
    r = H.judge(_cue(), h, e, "him")
    g = r["gate"]
    assert g["head.blink_nod_deg"]["pass"] and g["head.drift_deg"]["pass"], g
    assert g["head.frozen_s"]["pass"] and g["head.nods_per_min"]["pass"], g
    assert g["eyes.on_lens_share"]["pass"] and g["eyes.glances_per_min"]["pass"], g
    assert g["eyes.saccades_per_s"]["pass"], g
    f = tmp_path / "frozen"
    f.mkdir()
    h, e = _files(f, alive=False)
    r = H.judge(_cue(), h, e, "him")
    assert not r["pass"] and "head.frozen_s" in r["failed"] and "head.drift_deg" in r["failed"]
