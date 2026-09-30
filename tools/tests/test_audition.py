import json
import re

from gitloom_film.audition import music_page, vo_page


def make_take(root, line, k, dur=1.0, factor=0.9):
    d = root / line
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{k}.wav").write_bytes(b"RIFF")
    (d / f"{k}.json").write_text(json.dumps({"line": line, "take": k, "duration": dur, "factor": factor}))


def test_vo_page_lists_every_line_and_links_real_files(tmp_path):
    paced = tmp_path / "audio" / "vo" / "paced"
    make_take(paced, "L01", 1)
    make_take(paced, "L01", 2)
    make_take(paced, "L02", 1)
    script = {"lines": [{"id": "L01", "text": "Your agent forgets."}, {"id": "L02", "text": "It's <you>."}]}
    out = vo_page(script, paced, {"L01": {"take": 2}}, tmp_path / "out" / "vo.html")
    html = out.read_text()
    assert "L01" in html and "L02" in html and "It&#x27;s &lt;you&gt;." in html
    srcs = re.findall(r'src="([^"]+)"', html)
    assert len(srcs) == 3 and all((out.parent / s).resolve().exists() for s in srcs)
    assert '<div class="take chosen"><span>take 2' in html  # L01's pick
    assert html.count('class="take chosen"') == 2  # L02 has no pick, so it falls back to take 1


def test_music_page_links_variants(tmp_path):
    v = tmp_path / "audio" / "music" / "score-seed1.wav"
    v.parent.mkdir(parents=True)
    v.write_bytes(b"RIFF")
    out = music_page([v], tmp_path / "out" / "music.html", [{"name": "cold open", "start": 0.0, "end": 7.2}])
    html = out.read_text()
    assert "score-seed1" in html and "cold open" in html
    assert all((out.parent / s).resolve().exists() for s in re.findall(r'src="([^"]+)"', html))
