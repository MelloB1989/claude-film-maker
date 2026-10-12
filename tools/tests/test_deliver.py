import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from filmtools import config
from filmtools.deliver import (Delivery, check, encode_args, hit_cues, output_path, output_size, render_cmds,
                               segments)


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def tiny_film(tmp: Path, frames=60, audio_seconds=2.0, audio_delay=0.0, size="320x180") -> Path:
    """A test film: lavfi testsrc at 30 fps and a 440 Hz sine, the audio optionally short and starting late."""
    v = tmp / "v.mp4"
    ff("-f", "lavfi", "-i", f"testsrc=size={size}:rate=30", "-frames:v", str(frames), "-pix_fmt", "yuv420p", str(v))
    a = tmp / "a.wav"
    ff("-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={audio_seconds}", "-ac", "2", str(a))
    out = tmp / "film.mp4"
    delay = ["-itsoffset", str(audio_delay)] if audio_delay else []
    ff("-i", str(v), *delay, "-i", str(a), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", str(out))
    return out


SCENES = [{"id": f"s{i}", "start": s, "end": e} for i, (s, e) in
          enumerate([(0.0, 6.0), (6.0, 15.1), (15.1, 22.0), (22.0, 41.2), (41.2, 54.1), (54.1, 69.3), (69.3, 80.2),
                     (80.2, 93.6)])]


def test_segments_cover_the_film_exactly_and_avoid_cuts():
    segs = segments(SCENES, 2808, 4)
    assert len(segs) == 4
    assert segs[0][0] == 0 and segs[-1][1] == 2808
    assert all(a[1] == b[0] for a, b in zip(segs, segs[1:]))
    assert all(f0 < f1 for f0, f1 in segs)
    cuts = [s["end"] for s in SCENES[:-1]]
    assert all(min(abs(f / 30 - c) for c in cuts) >= 1.0 for _, f in segs[:-1])


def test_segments_run_at_the_films_rate():
    segs = segments(SCENES, round(93.6 * 24), 3, fps=24)
    assert segs[-1][1] == 2246 and all(min(abs(f / 24 - s["end"]) for s in SCENES[:-1]) >= 1.0 for _, f in segs[:-1])


def test_render_cmds_name_the_film_and_each_segment_and_render_silent(tmp_path):
    cmds = render_cmds([(0, 702), (702, 1500)], "demo", tmp_path, fps=30, scale=1)
    c = cmds[1]
    i = c.index("bun")
    assert c[i:i + 5] == ["bun", "scripts/render.ts", "video", "--film", "demo"]
    assert c[c.index("--from") + 1] == str(702 / 30) and c[c.index("--to") + 1] == str(1500 / 30)
    assert "--noaudio" in c and c[c.index("--out") + 1] == str(tmp_path / "seg-1.mp4")
    assert c[c.index("--samples") + 1] == "auto" and c[c.index("--scale") + 1] == "1" and c[c.index("--fps") + 1] == "30"
    import shutil
    assert (c[0] == "caffeinate") == bool(shutil.which("caffeinate"))  # only where there is one


OUTPUTS = {"rough": {"codec": "copy"}, "master": {"crf": 16}, "16x9": {"size": [1920, 1080], "maxrate": "12M",
                                                                       "audio_kbps": 256},
           "4x5": {"size": [1080, 1350]}, "9x16": {"size": [1080, 1920], "fit": "crop"}}


def args(name, native=(1920, 1080), pad="#000000"):
    return encode_args(OUTPUTS[name], Path("v.mp4"), Path("m.wav"), Path("o.mp4"), native, pad)


def test_encodes_never_offset_the_audio():
    for name in OUTPUTS:
        a = args(name)
        assert "-itsoffset" not in a and "-shortest" not in a and a.count("-ss") == 0
        assert a[a.index("-map") + 1] == "0:v" and "1:a" in a
        assert a[-1] == "o.mp4"


def test_encodes_tag_bt709_and_a_copy_keeps_the_render():
    rough = args("rough")
    assert rough[rough.index("-c:v") + 1] == "copy" and rough[rough.index("-b:a") + 1] == "320k"
    for name in ("master", "16x9", "4x5", "9x16"):
        a = args(name)
        assert a[a.index("-colorspace") + 1] == "bt709" and a[a.index("-color_trc") + 1] == "bt709"
        assert "+faststart" in a and a[a.index("-ar") + 1] == "48000"
    master = args("master")
    assert master[master.index("-crf") + 1] == "16" and "-vf" not in master  # the native size: no scaling
    social = args("16x9")
    assert social[social.index("-maxrate") + 1] == "12M" and social[social.index("-b:a") + 1] == "256k"
    assert "crop=1080:1920" in args("9x16")[args("9x16").index("-vf") + 1]
    with pytest.raises(SystemExit, match="copy"):  # a copy cannot change the render's size
        encode_args({"codec": "copy", "size": [1080, 1080]}, Path("v"), Path("m"), Path("o"))


def test_an_unknown_output_setting_is_an_error():
    with pytest.raises(SystemExit, match="unknown"):
        encode_args({"crff": 16}, Path("v"), Path("m"), Path("o"))
    with pytest.raises(SystemExit, match="fit"):
        encode_args({"fit": "stretch"}, Path("v"), Path("m"), Path("o"))


def test_check_reports_a_short_audio_and_a_late_start(tmp_path):
    v = tiny_film(tmp_path, frames=60, audio_seconds=1.9, audio_delay=0.1)
    probs = check(v, (320, 180), expect_frames=60, expect_seconds=2.0)
    assert any("duration" in p for p in probs) and any("start" in p for p in probs)


def test_check_reports_wrong_frames_and_size(tmp_path):
    v = tiny_film(tmp_path, frames=45, audio_seconds=1.5)
    probs = check(v, (1920, 1080), expect_frames=60, expect_seconds=2.0)
    assert any("frames" in p for p in probs) and any("size" in p for p in probs)
    assert not any("start" in p for p in probs)
    assert any("fps" in p for p in check(v, (320, 180), 45, 1.5, fps=25))


def test_a_portrait_output_of_a_landscape_film_is_padded_in_the_films_colour(tmp_path):
    v = tiny_film(tmp_path, frames=10, audio_seconds=10 / 30, size="1920x1080")
    src = tmp_path / "src.mp4"
    ff("-i", str(v), "-c", "copy", "-an", str(src))
    wav = tmp_path / "m.wav"
    ff("-f", "lavfi", "-i", "sine=duration=0.3333:sample_rate=48000", "-ac", "2", str(wav))
    out = tmp_path / "o.mp4"
    subprocess.run(encode_args(OUTPUTS["4x5"], src, wav, out, (1920, 1080), "#20305a"), check=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=width,height", "-of", "json", str(out)],
                                      capture_output=True, check=True).stdout)["streams"][0]
    assert (probe["width"], probe["height"]) == (1080, 1350)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    px = np.frombuffer(raw, np.uint8).reshape(1350, 1080, 3)
    assert np.abs(px[5, 5].astype(int) - [0x20, 0x30, 0x5A]).max() <= 4
    assert np.abs(px[-5, -5].astype(int) - [0x20, 0x30, 0x5A]).max() <= 4


def test_hits_name_their_cues_and_their_frames():
    sheet = {"cues": [{"sound": "door", "t": 5.35}, {"sound": "tick", "t": 1.0}, {"sound": "door", "t": 9.0}]}
    assert hit_cues([{"sound": "door", "frame": 161}], sheet) == [
        {"sound": "door", "t": 5.35, "frame": 161}, {"sound": "door", "t": 9.0, "frame": 161}]
    with pytest.raises(SystemExit, match="'bell'"):
        hit_cues([{"sound": "bell"}], sheet)


def test_check_finds_a_hit_off_its_frame(tmp_path):
    v = tiny_film(tmp_path, frames=60, audio_seconds=2.0)
    probs = check(v, (320, 180), 60, 2.0, lufs=-20, tp_max=0.0, hits=[{"sound": "door", "t": 1.0, "frame": 31}])
    assert any("door's cue frame 30 != its picture frame 31" in p for p in probs)


def test_lag_against_finds_a_late_audio_and_the_hit(tmp_path):
    import soundfile as sf

    from filmtools.deliver import lag_against, onset_near
    sr = 48000
    rng = np.random.default_rng(3)
    x = (rng.standard_normal(sr * 2) * 0.1).astype(np.float32)
    x[int(1.0 * sr):int(1.01 * sr)] += 0.8  # a hit at 1.0 s
    ref = tmp_path / "ref.wav"
    sf.write(ref, np.stack([x, x], 1), sr)
    late = tmp_path / "late.wav"
    y = np.concatenate([np.zeros(int(0.05 * sr), np.float32), x])[:len(x)]
    sf.write(late, np.stack([y, y], 1), sr)
    assert abs(lag_against(late, ref, 1.0) - 0.05) < 1e-3
    assert abs(lag_against(ref, ref, 1.0)) < 1e-4
    assert abs(onset_near(ref, 1.0) - 1.0) <= 0.002


def test_a_delivery_reads_the_films_length_rate_size_and_outputs(film):
    film.config.write_text(json.dumps({"id": "demo", "fps": 24, "format": "square",
                                       "pipeline": {"deliver": {"scale": 2, "outputs": {"4x5": {"size": [1080, 1350]},
                                                                                        "master": {}}}}}))
    (film.data / "vo.json").write_text(json.dumps({"duration": 9.0, "scenes": [{"id": "x", "start": 0, "end": 9.0}]}))
    (film.data / "timeline.json").write_text(json.dumps(
        {"fps": 24, "duration": 10.0, "format": [1080, 1080], "scenes": [{"id": "a", "start": 0, "end": 4},
                                                                          {"id": "b", "start": 4, "end": 10}]}))
    dl = Delivery(config.load())
    assert (dl.fps, dl.frames, dl.seconds, dl.native) == (24, 240, 10.0, (2160, 2160))  # timeline.json wins
    assert [s["id"] for s in dl.scenes] == ["a", "b"]
    assert dl.path("4x5") == output_path(film.out, "demo", "4x5") == film.out / "demo-4x5.mp4"
    assert output_size(dl.outputs["master"], dl.native) == (2160, 2160)
    assert output_size(dl.outputs["4x5"], dl.native) == (1080, 1350)


def test_the_letterbox_is_the_themes_background(tmp_path):
    from filmtools.deliver import theme_bg
    themes = tmp_path / "themes.json"
    themes.write_text(json.dumps({"noir": {"bg": "#110d10"}, "paper": {"bg": "#f4f1ea"}}))
    assert theme_bg("noir", themes) == "#110d10"
    assert theme_bg({"extends": "paper", "accent": "#123456"}, themes) == "#f4f1ea"
    assert theme_bg({"extends": "paper", "bg": "#000001"}, themes) == "#000001"
    assert theme_bg("unknown", themes) is None and theme_bg(None, themes) is None
