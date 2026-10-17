"""ArtCraft integration: the exporters' plain-data half always; the FilmCraft engine half when `filmcraft-cli` is installed
(python -m filmtools.artcraft install filmcraft)."""
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from filmtools.amv import plan as P
from filmtools.artcraft import filmcraft as FC
from filmtools.artcraft import install

REPO = Path(__file__).resolve().parents[2]
TIMELESS = REPO / "films" / "timeless"
CLI = install.find_cli("filmcraft")
FFMPEG = shutil.which("ffmpeg") or next((str(p) for p in [Path("/home/nikhil/code/film-making/bin/ffmpeg")] if p.exists()), None)
needs_cli = pytest.mark.skipif(not CLI or not FFMPEG, reason="filmcraft-cli / ffmpeg not installed")
needs_plan = pytest.mark.skipif(not (TIMELESS / "amv" / "plan.json").exists(), reason="timeless plan missing")


def png(w=16, h=9, rgba=(200, 60, 20, 255)):
    raw = b"".join(b"\0" + bytes(rgba) * w for _ in range(h))

    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))


def ffmpeg(*args):
    subprocess.run([FFMPEG, "-v", "error", "-y", *args], check=True)


@pytest.fixture
def media(tmp_path):
    mp4, wav = tmp_path / "film.mp4", tmp_path / "mix.wav"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4))
    ffmpeg("-f", "lavfi", "-i", "sine=f=330:d=6", "-ar", "48000", "-ac", "2", str(wav))
    return mp4, wav


# ---------------------------------------------------------------------------------------------- plain data

def test_ticks_and_timebase():
    assert FC.ticks(30, 30) == FC.TICKS
    assert FC.ticks(1, 24) == FC.TICKS // 24
    assert [FC.timebase(x) for x in (30, 29.97, 23.976, 24, 59.94)] == ["30", "29.97", "23.976", "24", "59.94"]


def test_final_timeline_commands(tmp_path):
    tl = FC.timeline_final("demo", tmp_path / "v.mp4", tmp_path / "m.wav", 30.0)
    assert [(c.track, c.start) for c in tl.clips] == [("V1", 0), ("A1", 0)]
    setup = [c for c, _ in FC.setup_commands(tl)]
    assert [c["id"] for c in setup] == ["prefs.set", "file.newProject", "file.import", "file.import", "file.newSequence"]
    assert setup[0]["params"]["value"] == "30"
    v = FC.place_command(tl, tl.clips[0], 1)["params"]
    a = FC.place_command(tl, tl.clips[1], 2)["params"]
    assert v["audio"] is False and v["track"] == "V1" and "duration" not in v      # the picture does not carry sound
    assert "audio" not in a and a["track"] == "A1"


def test_scenes_timeline_cuts_and_offsets(tmp_path):
    win = {"fps": 30, "format": [1080, 1920], "scenes": [{"id": "a", "start": 0, "end": 4}, {"id": "b", "start": 4, "end": 6.5}]}
    tl = FC.scenes_timeline("demo", tmp_path / "v.mp4", win, None)
    assert (tl.w, tl.h) == (1080, 1920)
    a, b = tl.clips
    assert (a.start, a.dur, a.src_in) == (0, 120, 0) and (b.start, b.dur, b.src_in) == (120, 75, 4.0)
    p = FC.place_command(tl, b, 1)["params"]
    assert p["frame"] == 120 and p["sourceIn"] == 4 * FC.TICKS and p["duration"] == 75 * FC.TICKS // 30


def test_keys_are_clamped_to_the_clip(tmp_path):
    tl = FC.Timeline("t", 1920, 1080, 30.0, [FC.Media("s", tmp_path / "f.png", "sequence")])
    c = FC.Clip("s", "V1", 10, 20, name="shot", keys={"pos": [(8, [0, 0]), (15, [5, 5]), (40, [9, 9])], "scale": [(10, 100)]})
    cmds = FC.clip_commands(tl, c, 7)
    assert cmds[0] == {"id": "clip.rename", "params": {"clip": 7, "name": "shot"}}
    pos = [x["params"] for x in cmds if x["params"].get("param") == "position"]
    assert [p["time"] // (FC.TICKS // 30) for p in pos] == [10, 15, 29]
    assert all(p["keyframe"] and p["effect"] == "motion" for p in pos)


def test_find_cli_prefers_newest_install(tmp_path):
    for v in ("0.9.2", "0.10.0", "0.8.0"):
        b = tmp_path / f"filmcraft-{v}-linux-x86_64" / "bin"
        b.mkdir(parents=True)
        (b / "filmcraft-cli").write_text("")
    assert install.find_cli("filmcraft", home=tmp_path).endswith("filmcraft-0.10.0-linux-x86_64/bin/filmcraft-cli")


def test_install_rejects_a_bad_checksum(tmp_path, monkeypatch):
    class R:
        def __init__(self, b):
            self.b, self.done = b, False

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self, n=-1):
            b, self.b = self.b, b""
            return b
    arch = install.arch()
    monkeypatch.setattr(install, "_get", lambda url: f"{'0' * 64}  filmcraft-0.8.0-linux-{arch}.tar.gz\n".encode())
    monkeypatch.setattr(install.urllib.request, "urlopen", lambda *a, **k: R(b"not the tarball"))
    with pytest.raises(SystemExit, match="does not match"):
        install.install("filmcraft", "v0.8.0", home=tmp_path, log=lambda *a: None)
    assert not list(tmp_path.glob("filmcraft-*"))


@pytest.fixture
def amv_film(tmp_path):
    """films/timeless's first three shots with baked layer frames (the real plan, cut short)."""
    film = tmp_path / "films" / "timeless"
    (film / "amv").mkdir(parents=True)
    plan = json.loads((TIMELESS / "amv" / "plan.json").read_text())
    plan["shots"] = plan["shots"][:3]
    (film / "amv" / "plan.json").write_text(json.dumps(plan))
    (film / "film.json").write_text(json.dumps({"id": "timeless", "fps": 30, "format": "landscape"}))
    layers = tmp_path / "out" / "timeless" / "amv" / "layers"
    for sh in plan["shots"]:
        d = layers / sh["name"]
        d.mkdir(parents=True)
        data = png()
        for f in range(sh["a"], sh["end"]):
            (d / f"{f:04d}.png").write_bytes(data)
    return film, layers


@needs_plan
def test_amv_layers_timeline(amv_film):
    film, layers = amv_film
    plan = P.load(film)
    tl, missing = FC.amv_layers(plan, layers, None, "timeless-layers")
    assert missing == [] and len(tl.clips) == 3
    for clip, sh in zip(tl.clips, plan.shots):
        assert (clip.name, clip.start, clip.dur) == (sh.name, sh.a, sh.end - sh.a)
        f, v = clip.keys["pos"][0]
        assert f == sh.a and v == [pytest.approx(sh.raw["px"][0]), pytest.approx(sh.raw["py"][0])]
    # a layer that runs on past its cut sits one track above the next shot's start
    over = [(a, b) for a, b in zip(plan.shots, plan.shots[1:]) if a.end > b.a]
    for a, b in over:
        assert tl.clips[b.index].track != tl.clips[a.index].track
    # no baked frames at all is an error, a partial set only a warning
    with pytest.raises(SystemExit, match="no baked layer frames"):
        FC.amv_layers(plan, layers / "nowhere", None, "x")
    shutil.rmtree(layers / plan.shots[1].name)
    tl2, missing2 = FC.amv_layers(plan, layers, None, "x")
    assert missing2 == [plan.shots[1].name] and len(tl2.clips) == 2


# ---------------------------------------------------------------------------------------------- the engine

@needs_cli
def test_final_project_opens_headless(tmp_path, media):
    mp4, wav = media
    tl = FC.timeline_final("demo", mp4, wav, 30.0, 320, 180)
    project = FC.build(tl, CLI, tmp_path / "out", interchange=["otio", "edl", "fcpxml", "xml"])
    assert project.name == "demo-final.fcproj"
    doc = json.loads(project.read_text())
    assert doc["format"] == "filmcraft.project" and doc["schema_version"] >= 13
    assert FC.verify(CLI, project, tl) == []
    otio = json.loads((tmp_path / "out" / "demo-final.otio").read_text())
    assert otio["OTIO_SCHEMA"] == "Timeline.1"
    assert "demo-final" in (tmp_path / "out" / "demo-final.edl").read_text()
    frame = FC.render_preview(CLI, project, [1.0], tmp_path / "prev")[0]
    assert frame.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


@needs_cli
def test_scenes_project_has_one_clip_per_scene(tmp_path, media):
    mp4, wav = media
    win = {"fps": 30, "format": [320, 180], "scenes": [{"id": "a", "start": 0, "end": 2}, {"id": "b", "start": 2, "end": 3.5},
                                                       {"id": "c", "start": 3.5, "end": 6}]}
    tl = FC.scenes_timeline("demo", mp4, win, wav)
    project = FC.build(tl, CLI, tmp_path / "out")
    assert FC.verify(CLI, project, tl) == []
    seq = FC.inspect(CLI, project)
    assert [(it["name"], it["durationFrames"]) for it in seq["video"][0]["items"]] == [("a", 60), ("b", 45), ("c", 75)]
    # a tampered edit is caught: the same project against a timeline with a moved cut
    win["scenes"][1]["end"] = 3.0
    assert FC.verify(CLI, project, FC.scenes_timeline("demo", mp4, win, wav))


@needs_cli
@needs_plan
def test_amv_layers_project_keeps_the_motion_keys(tmp_path, amv_film):
    film, layers = amv_film
    plan = P.load(film)
    tl, _ = FC.amv_layers(plan, layers, None, "timeless-layers")
    project = FC.build(tl, CLI, tmp_path / "out")
    assert FC.verify(CLI, project, tl) == []
    seq = FC.inspect(CLI, project)
    assert sum(len(t["items"]) for t in seq["video"]) == 3
