"""cut.py's pure parts: which frames it reads, the 9:16 crop, the captions. No ffmpeg.

    cd tools && uv run --with pillow --with pytest pytest ../films/host-studio/reel/test_cut.py
"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cut  # noqa: E402
from shots import SHOTS  # noqa: E402

TOTAL = cut.TOTAL


def crop_at(expr: str, n: int) -> float:
    """Evaluate the ffmpeg crop expression for frame n."""
    py = expr.replace("\\,", ",").replace("if(", "IF(")
    return eval(py, {"IF": lambda c, a, b: a if c else b, "lt": lambda a, b: a < b, "n": n, "floor": math.floor,
                     "clip": lambda v, lo, hi: min(max(v, lo), hi)})


def touch(d: Path, frames) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for f in frames:
        (d / f"{f:04d}.png").write_bytes(b"")


def test_span():
    assert cut.span(None, None) == (0, 1560)
    assert cut.span(None, "S13-S18") == (960, 1560)
    assert cut.span(None, "v02") == (180, 360)
    assert cut.span("100:200", None) == (100, 200)
    with pytest.raises(SystemExit):
        cut.span("0:2000", None)


def test_find_frames_per_shot_master_and_local(tmp_path):
    touch(tmp_path / "S11", range(708, 792))  # master numbering with 12-frame handles
    touch(tmp_path / "S12", range(0, 60))     # shot-local numbering
    found = cut.find_frames(tmp_path, 720, 840)
    assert found[720] == tmp_path / "S11" / "0720.png" and found[779] == tmp_path / "S11" / "0779.png"
    assert found[780] == tmp_path / "S12" / "0000.png" and found[839] == tmp_path / "S12" / "0059.png"
    assert len(found) == 120 and all(found.values())


def test_find_frames_flat_offset_and_missing(tmp_path):
    touch(tmp_path, range(12, 12 + 100))  # a render from the handle at f-12, numbered from 0
    found = cut.find_frames(tmp_path, 0, 120, offset=12)
    assert found[0] == tmp_path / "0012.png" and found[99] == tmp_path / "0111.png"
    assert [f for f, p in found.items() if p is None] == list(range(100, 120))
    with pytest.raises(SystemExit, match=r"V01 100-119 \(20\)"):
        cut.stage({**found, **{f: None for f in range(100, 120)}}, 0, tmp_path / "w", None, (64, 36))


def test_crop_follows_shots_and_keys():
    sw, cw = 3840, 1215
    e = cut.crop_expr([(0, TOTAL)], sw, cw)
    for s in SHOTS:
        ks = cut.vcrop_keys(s)
        assert crop_at(e, s.start) == math.floor(cut.crop_x(ks[0][1], sw, cw)), s.id
        assert crop_at(e, s.end - 1) == math.floor(cut.crop_x(ks[-1][1], sw, cw)), s.id
    s15 = next(s for s in SHOTS if s.id == "S15")
    a, b = cut.crop_x(0.20, sw, cw), cut.crop_x(0.68, sw, cw)
    xs = [crop_at(e, s15.start + k) for k in range(55, 85)]
    assert xs == sorted(xs) and xs[0] == math.floor(a) and xs[-1] == math.floor(b)  # eased, monotone
    assert all(0 <= crop_at(e, n) <= sw - cw for n in range(0, TOTAL, 7))


def test_crop_of_a_range_starts_at_its_first_frame():
    e = cut.crop_expr([(960, 1560)], 1920, 608)
    s13 = next(s for s in SHOTS if s.id == "S13")
    assert crop_at(e, 0) == math.floor(cut.crop_x(s13.vcrop, 1920, 608))


def test_cues_cover_the_lines_in_order():
    cs = cut.cues()
    assert all(a < b for (a, b), _ in cs)
    assert all(p[0][1] <= q[0][0] for p, q in zip(cs, cs[1:]))
    for first, last, text in cut.LINES.values():
        mine = [c for c in cs if first <= c[0][0] < last]
        assert mine[0][0][0] == first and " ".join(t for _, t in mine) == text
        assert all(len(t) <= 64 for _, t in mine)


def test_captions_files(tmp_path):
    cut.write_captions(tmp_path / "x", cut.cues(), [(960, 1560)])
    srt = (tmp_path / "x.srt").read_text()
    assert srt.startswith("1\n00:00:02,500 --> ")  # L1 at f1020 = 60 frames into the range
    assert (tmp_path / "x.vtt").read_text().startswith("WEBVTT\n\n00:00:02.500 --> ")


def test_wrap_balances_a_widow():
    f = cut.font(40, 500)
    rows = cut.wrap("Tech, explained the way we'd want it explained: calm, honest,", f, f.getlength("x" * 40))
    assert len(rows) == 2 and len(rows[1].split()) > 1


def test_stage_keeps_a_jpg_pass_and_its_slates(tmp_path):
    """A preview pass is .jpg: the staged sequence and the slates standing in for missing frames keep that extension
    (ffmpeg's image2 picks the decoder by it)."""
    from PIL import Image
    d = tmp_path / "preview"
    d.mkdir()
    for f in range(0, 100):
        Image.new("RGB", (64, 36)).save(d / f"{f:04d}.jpg")
    found = cut.find_frames(d, 0, 180, "{frame:04d}.jpg")
    seq = cut.stage(found, [(0, 180)], tmp_path / "w", "slate", (64, 36))
    assert sorted({p.suffix for p in seq.iterdir()}) == [".jpg"] and len(list(seq.iterdir())) == 180
    assert cut.image_size(found[0]) == (64, 36)
    with pytest.raises(SystemExit, match="mix"):
        cut.frame_ext({0: d / "0000.jpg", 1: d / "0001.png"})


def test_round3_makes_16x9_only():
    names = {o.name for o in cut.OUTPUTS}
    assert "vertical" in cut.OPT_IN and {"1080p", "1080p-clean"} <= names - cut.OPT_IN
    assert not next(o for o in cut.OUTPUTS if o.name == "1080p-clean").captions


def test_assemble_fills_shots_not_yet_final_from_the_preview(tmp_path):
    import assemble
    from PIL import Image
    prev, fin = tmp_path / "preview", tmp_path / "final"
    prev.mkdir()
    for f in range(cut.TOTAL):
        Image.new("RGB", (16, 9)).save(prev / f"{f:04d}.jpg")
    s13 = next(s for s in SHOTS if s.id == "S13")
    (fin / "S13").mkdir(parents=True)
    for f in range(s13.start, s13.end):
        Image.new("RGB", (32, 18)).save(fin / "S13" / f"{f:04d}.png")
    assert assemble.pattern(prev) == "{frame:04d}.jpg" and assemble.pattern(fin) == "{frame:04d}.png"
    assert assemble.whole(fin) == ["S13"] and len(assemble.whole(prev)) == len(SHOTS)
    d = assemble.merged(tmp_path / "out", [fin, prev])
    assert {p.suffix for p in d.iterdir()} == {".png"} and len(list(d.iterdir())) == cut.TOTAL
    assert (d / f"{s13.start:04d}.png").resolve() == (fin / "S13" / f"{s13.start:04d}.png").resolve()
