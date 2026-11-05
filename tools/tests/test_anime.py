"""The anime pipeline's pure parts (filmtools.anime): no network, no models, films made under a temporary root."""
import json

import numpy as np
import pytest

from filmtools.anime import assets, cutout, depth, dialogue, mix, score, synth

SR = 48000


def test_trim_takes_the_silence_off_both_ends_and_reports_the_cut():
    x = np.zeros(SR, np.float32)
    x[int(0.3 * SR):int(0.6 * SR)] = 0.5 * np.sin(np.arange(int(0.3 * SR)) * 0.05)
    y, cut = dialogue.trim(x)
    assert 0.25 * SR < cut < 0.3 * SR                       # 30 ms of pad before the voice
    assert 0.3 * SR < len(y) < 0.4 * SR
    assert y[0] == 0 and abs(y[-1]) < 1e-6                     # faded at both ends
    silent, c0 = dialogue.trim(np.zeros(1000, np.float32))
    assert c0 == 0 and len(silent) == 1000                    # nothing above the threshold: left as it is


def test_split_times_finds_where_a_later_subtitle_starts_in_the_spoken_take():
    meta = {"chars": [{"c": c, "t0": 0.1 * i, "t1": 0.1 * i + 0.1} for i, c in enumerate("強さってのはね斬った数")]}
    assert dialogue.split_times({"id": "L", "splits": ["斬"]}, meta) == [pytest.approx(0.7)]
    with pytest.raises(SystemExit, match="not in the spoken text"):
        dialogue.split_times({"id": "L", "splits": ["雨"]}, meta)


def test_place_writes_the_stem_the_subtitles_and_the_timing(film):
    import soundfile as sf

    (film.data / "timeline.json").write_text(json.dumps({"fps": 24, "duration": 4.0, "scenes": [
        {"id": "a", "start": 0, "end": 2}, {"id": "b", "start": 2, "end": 4}]}))
    (film.data / "dialogue.json").write_text(json.dumps({
        "cast": {"x": {"voice_id": "v"}},
        "lines": [{"id": "L1", "who": "x", "shot": "b", "at": 0.5, "ja": "あいう", "en": ["one", "two"], "splits": ["う"]}]}))
    takes = dialogue.takes_dir()
    takes.mkdir(parents=True)
    sf.write(takes / "L1.t0.wav", np.full(SR // 2, 0.1, np.float32), SR)
    (takes / "L1.t0.json").write_text(json.dumps({"take": 0, "seconds": 0.5, "chars": [
        {"c": "あ", "t0": 0.0, "t1": 0.1}, {"c": "い", "t0": 0.1, "t1": 0.2}, {"c": "う", "t0": 0.3, "t1": 0.4}]}))
    dialogue.place(hold=0.3)
    stem, sr = sf.read(film.audio / "dialogue" / "dialogue.wav")
    assert sr == SR and len(stem) == 4 * SR
    assert stem[int(2.49 * SR)] == 0 and stem[int(2.6 * SR)] == pytest.approx(0.1, abs=1e-4)
    subs = json.loads((film.data / "subs.json").read_text())
    assert [s["text"] for s in subs] == ["one", "two"]
    assert subs[1]["start"] == pytest.approx(2.5 + 0.3 - 0.05)
    assert subs[1]["end"] == pytest.approx(2.5 + 0.5 + 0.3)
    timing = json.loads((film.data / "dialogue_timing.json").read_text())
    assert timing[0]["start"] == 2.5 and timing[0]["end"] == 3.0


def test_keyed_interpolates_and_holds():
    v = mix.keyed([[1, 0], [0, -10]], 3 * SR)
    assert v[0] == -10 and v[SR // 2] == pytest.approx(-5) and v[-1] == 0
    assert (mix.keyed(None, 10, 3.0) == 3.0).all()


def test_limiter_keeps_the_ceiling_and_leaves_quiet_audio_alone():
    t = np.arange(SR) / SR
    x = np.stack([np.sin(2 * np.pi * 220 * t)] * 2, axis=1) * 0.2
    x[SR // 2:SR // 2 + 200] *= 8                              # a burst well over the ceiling
    y = mix.limiter(x, -1.0)
    assert np.abs(y).max() <= 10 ** (-1 / 20) + 1e-6
    assert np.allclose(y[:SR // 4], x[:SR // 4])               # far from the burst: untouched


def test_pushpull_fills_a_hole_smoothly_from_its_surroundings():
    rgb = np.zeros((64, 64, 3), np.float32)
    rgb[:, :32] = 200
    rgb[:, 32:] = 40
    known = np.ones((64, 64), np.float32)
    known[16:48, 16:48] = 0
    out = cutout.pushpull(rgb, known)
    assert np.isfinite(out).all()
    assert np.allclose(out[known > 0], rgb[known > 0])          # what was known stays
    hole = out[16:48, 16:48, 0]
    assert hole.min() >= 40 - 1e-3 and hole.max() <= 200 + 1e-3  # filled from between the two sides
    assert hole[:, 0].mean() > hole[:, -1].mean()               # the bright side bleeds into the hole's bright edge


def test_parse_boxes():
    assert cutout.parse_boxes("0,0,0.5,1;0.5,0,1,1") == [(0, 0, 0.5, 1), (0.5, 0, 1, 1)]
    assert cutout.parse_boxes(None) is None
    with pytest.raises(SystemExit):
        cutout.parse_boxes("0,0,1")


def test_depth_normalise_maps_the_range_to_0_1():
    d = np.linspace(-5, 20, 100 * 100, dtype=np.float32).reshape(100, 100)
    n = depth.normalise(d, smooth=0)
    assert n.min() == 0 and n.max() == 1
    assert n[50, 50] == pytest.approx(0.5, abs=0.02)


@pytest.mark.parametrize("kind", sorted(synth.KINDS))
def test_synth_sounds_are_finite_deterministic_and_under_full_scale(kind):
    a, b = synth.make(kind), synth.make(kind)
    assert a.dtype == np.float32 and len(a) > SR // 10
    assert np.isfinite(a).all() and np.abs(a).max() <= 1.0
    assert np.array_equal(a, b)
    with pytest.raises(SystemExit):
        synth.make("kazoo")


def test_score_chunks_carry_the_global_and_the_section_styles():
    s = {"global": {"positive": ["film score"], "negative": ["vocals"]}}
    cue = {"at": 3, "sections": [{"name": "Dawn", "ms": 5000, "positive": ["warm strings"]},
                                 {"name": "End", "ms": 2500, "negative": ["drums"]}]}
    ch = score.chunks_of(s, cue)["chunks"]
    assert [c["text"] for c in ch] == ["[Dawn]", "[End]"]
    assert ch[0]["positive_styles"] == ["film score", "warm strings"] and ch[0]["negative_styles"] == ["vocals"]
    assert ch[1]["negative_styles"] == ["vocals", "drums"] and ch[1]["duration_ms"] == 2500


def test_fetch_records_provenance_and_keeps_a_reroll_as_a_version(film, tmp_path):
    src = tmp_path / "result.png"
    src.write_bytes(b"\x89PNG one")
    p = assets.fetch("key-a", src.as_uri(), job="j1", model="m", prompt="a lake", refs=["sheet"], credits=1)
    assert p.read_bytes() == b"\x89PNG one" and p.name == "key-a.png"
    with pytest.raises(SystemExit, match="already fetched"):
        assets.fetch("key-a", src.as_uri())
    src.write_bytes(b"\x89PNG two")
    assets.fetch("key-a", src.as_uri(), job="j2", force=True)
    m = assets.load_manifest()
    assert m["key-a"]["job"] == "j2" and m["key-a.v1"]["job"] == "j1" and m["key-a.v1"]["refs"] == ["sheet"]
    assert (film.dir / m["key-a.v1"]["file"]).read_bytes() == b"\x89PNG one"
    with pytest.raises(SystemExit, match="picture or clip"):
        assets.fetch("bad", (tmp_path / "x.txt").as_uri())
