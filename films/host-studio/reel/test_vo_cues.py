"""vo.py cues: cues.json and the stems from the built line WAVs alone (round 3: the takes are gone). No ElevenLabs."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
vo = pytest.importorskip("vo")


def _line_wav(path, lead_s, voiced_s):
    sr = vo.SR
    x = np.zeros(int((lead_s + voiced_s + 0.25) * sr), np.float32)
    t = np.arange(int(voiced_s * sr)) / sr
    x[int(lead_s * sr):int(lead_s * sr) + len(t)] = 0.3 * np.sin(2 * np.pi * 180 * t)
    vo.write_wav(path, x, sr)


def test_cues_place_each_line_on_its_frame(tmp_path, monkeypatch):
    src = tmp_path / "import"
    src.mkdir()
    for ln in vo.LINES:
        _line_wav(src / f"{ln.id}.wav", 0.05, 1.0)
    monkeypatch.setattr(vo, "OUT", tmp_path / "vo")
    cues = vo.cues_from_wavs(src)
    doc = json.loads((tmp_path / "vo" / "cues.json").read_text())
    assert set(doc["lines"]) == {ln.id for ln in vo.LINES} and doc["words_estimated"]
    for ln in vo.LINES:
        c = cues[ln.id]
        assert c["file_frame"] == pytest.approx(ln.start - 0.05 * vo.FPS, abs=0.6)  # the voice lands on its frame
        assert [w["w"] for w in c["words"]] == vo.spoken(ln.text).split()
        assert c["words"][0]["start"] == pytest.approx(ln.start, abs=0.6)
        assert c["words"][-1]["end"] == pytest.approx(ln.start + vo.FPS, abs=1.0)
        assert all(a["end"] <= b["start"] for a, b in zip(c["words"], c["words"][1:]))
    him, _ = vo.read_wav(tmp_path / "vo" / "vo_him.wav")
    assert len(him) == vo.TOTAL * vo.SR // vo.FPS and np.abs(him).max() > 0.2


def test_a_missing_line_says_which(tmp_path, monkeypatch):
    monkeypatch.setattr(vo, "OUT", tmp_path / "vo")
    with pytest.raises(SystemExit, match="L1.wav is missing"):
        vo.cues_from_wavs(tmp_path)
