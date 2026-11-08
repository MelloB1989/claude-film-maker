import math
import sys
import types
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import head_stages as HS  # noqa: E402


def _fake_perform(tmp):
    pf = types.ModuleType("perform")
    pf.ANIM, pf.HEADAXES, pf.OUT = "/Game/X", "code", Path(tmp)
    return pf


def test_stage_split_finds_the_first_stage_over_the_line(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "perform", _fake_perform(tmp_path))
    cue = {"fps": 24, "start": 0, "on_cam": [[0.0, 10.0, ["CAM_MCU"]]]}
    amp = {"seat": 0.2, "body": 3.0, "follow": 3.0, "gaze": 3.0}  # deg; a 1 Hz sway in yaw

    def run(code, p, timeout):
        a = p["anims"][0]
        k = a.rsplit("_", 1)[1]
        return {a: {str(t): {"abs_yaw_right": amp[k] * math.sin(2 * math.pi * 0.5 * t), "pitch_up": 0.0}
                    for t in p["times"]}}

    r = HS.stages(cue, "him", ["seat", "body", "follow", "gaze"], run=run)
    assert r["stages"]["seat"]["drift_med"] < HS.LINE
    assert r["stages"]["body"]["drift_med"] > HS.LINE
    assert r["stages"]["body"]["pitch_med"] == 0.0
    assert r["first_over_line"] == "body"
    assert len(r["stages"]["body"]["worst"]) == 5


def test_windows_match_head_life_metrics():
    import head as H
    fps = 24.0
    t = np.arange(0, 240) / fps
    yaw, pitch = np.sin(t * 2.1) * 1.3, np.cos(t * 0.7) * 0.6
    seen = [[0, 240]]
    mine = HS.windows(t, yaw, pitch, seen, fps)["drift_med"]
    theirs = H.life_metrics(t, yaw, pitch, [[0.0, 10.0]], fps)["head.drift_deg"]
    assert abs(mine - theirs) < 1e-3
