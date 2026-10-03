import json
import subprocess
from pathlib import Path

import numpy as np

from gitloom_film.deliver import check, encode_args, render_cmds, segments, snap_frames
from gitloom_film.paths import DATA


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


def test_segments_cover_the_film_exactly_and_avoid_cuts():
    vo = json.loads((DATA / "vo.json").read_text())
    segs = segments(vo["scenes"], 2808, 4)
    assert len(segs) == 4
    assert segs[0][0] == 0 and segs[-1][1] == 2808
    assert all(a[1] == b[0] for a, b in zip(segs, segs[1:]))
    assert all(f0 < f1 for f0, f1 in segs)
    cuts = [s["end"] for s in vo["scenes"][:-1]]
    assert all(min(abs(f / 30 - c) for c in cuts) >= 1.0 for _, f in segs[:-1])


def test_render_cmds_name_each_segment_and_render_silent():
    cmds = render_cmds([(0, 702), (702, 1500)], scale=1)
    assert cmds[0][:5] == ["caffeinate", "-i", "bun", "scripts/render.ts", "video"]
    c = cmds[1]
    assert c[c.index("--from") + 1] == str(702 / 30) and c[c.index("--to") + 1] == str(1500 / 30)
    assert "--noaudio" in c and c[c.index("--out") + 1] == "../out/film/seg-1.mp4"
    assert c[c.index("--samples") + 1] == "auto" and c[c.index("--scale") + 1] == "1"


def test_encodes_never_offset_the_audio():
    for kind in ["rough", "web1080", "ig16x9", "ig4x5"]:
        a = encode_args(kind, Path("v.mp4"), Path("m.wav"), Path("o.mp4"))
        assert "-itsoffset" not in a and "-shortest" not in a and a.count("-ss") == 0
        assert a[a.index("-map") + 1] == "0:v" and "1:a" in a
        assert a[-1] == "o.mp4"


def test_encodes_tag_bt709_and_rough_copies_the_video():
    rough = encode_args("rough", Path("v.mp4"), Path("m.wav"), Path("o.mp4"))
    assert rough[rough.index("-c:v") + 1] == "copy" and rough[rough.index("-b:a") + 1] == "320k"
    for kind in ["web1080", "ig16x9", "ig4x5"]:
        a = encode_args(kind, Path("v.mp4"), Path("m.wav"), Path("o.mp4"))
        assert a[a.index("-colorspace") + 1] == "bt709" and a[a.index("-color_trc") + 1] == "bt709"
        assert "+faststart" in a and a[a.index("-ar") + 1] == "48000"
    web = encode_args("web1080", Path("v.mp4"), Path("m.wav"), Path("o.mp4"))
    assert web[web.index("-crf") + 1] == "16"
    ig = encode_args("ig16x9", Path("v.mp4"), Path("m.wav"), Path("o.mp4"))
    assert ig[ig.index("-maxrate") + 1] == "12M" and ig[ig.index("-b:a") + 1] == "256k"


def test_check_reports_a_short_audio_and_a_late_start(tmp_path):
    v = tiny_film(tmp_path, frames=60, audio_seconds=1.9, audio_delay=0.1)
    probs = check(v, "rough", expect_frames=60, expect_seconds=2.0)
    assert any("duration" in p for p in probs) and any("start" in p for p in probs)


def test_check_reports_wrong_frames_and_size(tmp_path):
    v = tiny_film(tmp_path, frames=45, audio_seconds=1.5)
    probs = check(v, "rough", expect_frames=60, expect_seconds=2.0)
    assert any("frames" in p for p in probs) and any("size" in p for p in probs)
    assert not any("start" in p for p in probs)


def test_ig4x5_is_1080x1350_on_ink(tmp_path):
    v = tiny_film(tmp_path, frames=10, audio_seconds=10 / 30, size="1920x1080")
    src = tmp_path / "src.mp4"
    ff("-i", str(v), "-c", "copy", "-an", str(src))
    wav = tmp_path / "m.wav"
    ff("-f", "lavfi", "-i", "sine=duration=0.3333:sample_rate=48000", "-ac", "2", str(wav))
    out = tmp_path / "o.mp4"
    subprocess.run(encode_args("ig4x5", src, wav, out), check=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=width,height", "-of", "json", str(out)],
                                      capture_output=True, check=True).stdout)["streams"][0]
    assert (probe["width"], probe["height"]) == (1080, 1350)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    px = np.frombuffer(raw, np.uint8).reshape(1350, 1080, 3)
    assert np.abs(px[5, 5].astype(int) - [0x11, 0x0D, 0x10]).max() <= 4
    assert np.abs(px[-5, -5].astype(int) - [0x11, 0x0D, 0x10]).max() <= 4


def test_the_snap_cue_is_b01s_snap_frame():
    cue_frame, plate_frame = snap_frames()
    assert cue_frame == plate_frame == 161


def test_lag_against_finds_a_late_audio_and_the_snap_hit(tmp_path):
    import soundfile as sf
    from gitloom_film.deliver import lag_against, onset_near
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
