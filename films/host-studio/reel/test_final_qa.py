"""r3/final_qa.py's offline parts: the frames check on synthetic frames and the caption sync on a written .srt.

    cd tools && uv run --with pillow --with numpy --with pytest pytest ../films/host-studio/reel/test_final_qa.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "r3"))
import cut  # noqa: E402
import final_qa as q  # noqa: E402
from shots import SHOTS  # noqa: E402


def test_frames_black_white_missing(tmp_path, monkeypatch):
    s = SHOTS[8]  # S13: no handles
    monkeypatch.setattr(q, "SHOTS", [SHOTS[7], s, SHOTS[9]])
    monkeypatch.setattr(q, "SIZE", (64, 36))
    for f in range(s.start, s.end):
        v = 0 if f == s.start + 5 else 255 if f == s.start + 6 else 100
        if f != s.start + 7:
            Image.fromarray(np.full((36, 64), v, np.uint8)).save(tmp_path / q.name(f))
    r = q.frames_qa(tmp_path)["shots"][s.id]
    assert r["black"] == [s.start + 5] and r["white"] == [s.start + 6] and r["missing"] == [s.start + 7]


def _srt(tmp_path, cs, segs):
    out = tmp_path / "karma-reel"
    cut.write_captions(out, cs, segs)
    return out.with_suffix(".srt")


def test_captions_sync(tmp_path):
    segs = [(0, 1560)]
    words = {"L1": [{"w": "Took", "start": 1022, "end": 1030}, {"w": "you", "start": 1030, "end": 1034},
                    {"w": "long", "start": 1034, "end": 1040}, {"w": "enough.", "start": 1040, "end": 1060}]}
    cs = cut.cues(words=words)
    p = _srt(tmp_path, cs, segs)
    r = q.captions_qa(p, {"frames": segs}, {"L1": {"words": words["L1"]}}, 1560)
    assert r["lines"]["L1"]["pass"] and r["lines"]["L1"]["off_frames"] == 0
    assert r["pass"]
    late = [((a + 6, b + 6), t) if t.startswith("Took") else ((a, b), t) for (a, b), t in cs]
    r = q.captions_qa(_srt(tmp_path, late, segs), {"frames": segs}, {"L1": {"words": words["L1"]}}, 1560)
    assert not r["lines"]["L1"]["pass"] and r["lines"]["L1"]["off_frames"] == 6


def test_captions_through_45s_edl(tmp_path):
    segs = cut.edl("45s") if "45s" in cut.EDLS else None
    if not segs:
        return
    cs = cut.cues()
    p = _srt(tmp_path, cs, segs)
    n = sum(b - a for a, b in segs)
    r = q.captions_qa(p, {"frames": [list(x) for x in segs]}, None, n)
    assert r["pass"], r["failed"]
