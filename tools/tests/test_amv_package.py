"""The packager's path logic (no Blender)."""
import os

import pytest

from filmtools.amv import package as K


def test_needed_dirs_covers_planes_titles_outro():
    raw = {"titles": [{}, {}, {}]}
    d = K.needed_dirs(raw, ["M01_a", "M02_b"], ["M01_a", "M03_c"])
    assert d == ["layers/M01_a", "layers/M02_b", "layers/M03_c", "titles/screen.0", "titles/screen.1",
                 "titles/screen.2", "titles/watermark", "outro"]


def test_audit_accepts_relative_inside():
    assert K.audit_image_paths(["//layers/M01/0001.png", "//titles/watermark/0000.png"]) == []


@pytest.mark.parametrize("p", ["/abs/x/0001.png", "layers/x.png", "//../out/x.png", "//a/../../x.png", "C:\\x.png"])
def test_audit_rejects(p):
    assert len(K.audit_image_paths([p])) == 1


def test_link_or_copy_and_tree(tmp_path):
    s = tmp_path / "s" / "shot"
    s.mkdir(parents=True)
    (s / "0001.png").write_bytes(b"a")
    (s / "0002.png").write_bytes(b"b")
    n = K.link_tree(tmp_path / "s", tmp_path / "d")
    assert n["link"] + n["copy"] == 2
    assert (tmp_path / "d" / "shot" / "0002.png").read_bytes() == b"b"
    assert n["link"] == 2 and os.path.samefile(s / "0001.png", tmp_path / "d" / "shot" / "0001.png")


def test_link_falls_back_to_copy(tmp_path, monkeypatch):
    (tmp_path / "a").write_bytes(b"x")
    monkeypatch.setattr(os, "link", lambda *a: (_ for _ in ()).throw(OSError("xdev")))
    assert K.link_or_copy(tmp_path / "a", tmp_path / "b" / "a") == "copy"
    assert (tmp_path / "b" / "a").read_bytes() == b"x"


def test_video_name(tmp_path):
    (tmp_path / "Timeless_SpiderVerse_SAU_EDITZ_v3.mp4").write_bytes(b"")
    (tmp_path / "Timeless_SpiderVerse_SAU_EDITZ_v2.mp4").write_bytes(b"")
    v = K.find_video(tmp_path, "v3")
    assert K.delivered_name(v, "v3") == "Timeless_SpiderVerse_SAU_EDITZ.mp4"
    with pytest.raises(SystemExit):
        K.find_video(tmp_path, "zz")


def test_verdict():
    ok = {"image_paths": ["//a.png"], "missing": [], "frames": [{"frame": 1, "magenta": 0.0, "blank": False}]}
    assert K.verdict(ok) == []
    bad = {"image_paths": ["/abs.png"], "missing": ["//x.png"],
           "frames": [{"frame": 1, "magenta": 0.5, "blank": True}]}
    assert len(K.verdict(bad)) == 4
    assert K.verdict({"image_paths": [], "frames": []}) == ["no frames rendered"]


def test_pick_mix_prefers_explicit_then_fixed_then_plan(tmp_path):
    film = tmp_path / "films" / "x"
    (film / "audio" / "mix").mkdir(parents=True)
    plan = type("P", (), {"raw": {"audio": "audio/mix/mix.wav"}, "path": lambda self, r: film / r})()
    assert K.pick_mix(film, plan, None) is None
    (film / "audio/mix/mix.wav").write_bytes(b"o")
    assert K.pick_mix(film, plan, None).name == "mix.wav"
    (film / "audio/mix/mix_fixed.wav").write_bytes(b"f")
    assert K.pick_mix(film, plan, None).name == "mix_fixed.wav"
    ex = tmp_path / "e.wav"
    ex.write_bytes(b"e")
    assert K.pick_mix(film, plan, ex) == ex


def test_link_onto_itself_keeps_the_file(tmp_path):
    f = tmp_path / "m.wav"
    f.write_bytes(b"x")
    K.link_or_copy(f, f)
    assert f.read_bytes() == b"x"
