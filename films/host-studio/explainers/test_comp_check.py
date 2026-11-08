import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import comp_check as C  # noqa: E402


class _R:
    def __init__(self, out="", err=""):
        self.stdout, self.stderr = out, err


def test_black_frames_parsed(monkeypatch):
    err = "[blackdetect @ 0x1] black_start:2 black_end:2.25 black_duration:0.25\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(err=err))
    assert C.black_frames("x.mp4", 24.0)["frames"] == 6


def test_dups_only_count_inside_presenter_shots(tmp_path):
    edl = tmp_path / "e.json"
    edl.write_text(json.dumps({"shots": [{"kind": "pres", "f0": 0, "f1": 5}, {"kind": "gfx", "f0": 5, "f1": 10}]}))
    h = ["a", "b", "b", "c", "d", "e", "f", "f", "f", "g"]  # a dup at 2 (presenter) and 7, 8 (graphics)
    d = C.dup_frames(h, C.presenter_mask(str(edl), 24.0))
    assert d["frames"] == 1 and d["first"] == [2]


def test_av_offset_finds_a_late_audio(monkeypatch):
    rate = 8000
    rng = np.random.default_rng(1)
    env = np.repeat(rng.random(400) > 0.7, 80).astype(float)  # 4 s of on/off bursts
    mix = env * rng.standard_normal(len(env)) * 0.3
    late = np.concatenate([np.zeros(int(0.1 * rate)), mix])[: len(mix)]  # the cut's audio 100 ms late
    monkeypatch.setattr(C, "read_wav_mono", lambda p, r=rate: late if p == "cut" else mix)
    r = C.av_offset_ms("cut", "mix")
    assert abs(r["offset_ms"] - 100.0) <= 4.0 and r["corr"] > 0.5
