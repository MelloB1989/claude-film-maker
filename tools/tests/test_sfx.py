import json

import numpy as np
import pytest

from gitloom_film.sfx import load_sheet, render_bus
from gitloom_film.wav import write_wav

SR = 48000


def click_at(hit_s: float, seconds: float = 0.3) -> np.ndarray:
    """A decaying click whose single loudest sample sits at hit_s."""
    n = int(seconds * SR)
    y = np.zeros(n, np.float32)
    h = int(round(hit_s * SR))
    tail = np.arange(n - h)
    y[h:] = 0.5 * np.exp(-tail / (0.01 * SR)) * np.cos(2 * np.pi * 3000 * tail / SR)
    y[h] = 0.9
    return y


def fake_lib(tmp, sounds: dict, loops: set = frozenset(), hits: dict | None = None):
    lib = tmp / "lib"
    picks = {}
    for name, y in sounds.items():
        write_wav(lib / name / "x.wav", y)
        loop = name in loops
        hit = None if loop else (hits or {}).get(name, 0.005)
        picks[name] = {"wav": f"{name}/x.wav", "hit_s": hit, "loop": loop, "align": None if loop else "onset",
                       "gain": 0}
    return lib, {"picks": picks}


def one(sound, t, **kw):
    return {"cues": [{"sound": sound, "t": t, "gain": 0, "pan": 0, **kw}], "ducks": []}


def test_a_one_shot_lands_its_hit_on_the_sample(tmp_path):
    lib, manifest = fake_lib(tmp_path, {"click": click_at(0.005)})  # hit_s = 0.005
    y = render_bus(one("click", 1.0), manifest, lib, 2.0)
    assert y.shape == (2 * SR, 2) and y.dtype == np.float32
    assert np.argmax(np.abs(y[:, 0])) == 48000


def test_an_end_aligned_hit_lands_on_the_sample(tmp_path):
    lib, manifest = fake_lib(tmp_path, {"riser": click_at(0.25)}, hits={"riser": 0.25})
    y = render_bus(one("riser", 0.7), manifest, lib, 2.0)
    assert np.argmax(np.abs(y[:, 1])) == round(0.7 * SR)


def test_a_hit_near_the_start_is_cut_not_shifted(tmp_path):
    lib, manifest = fake_lib(tmp_path, {"riser": click_at(0.25)}, hits={"riser": 0.25})
    y = render_bus(one("riser", 0.1), manifest, lib, 1.0)  # the take would start at −0.15 s
    assert np.argmax(np.abs(y[:, 0])) == round(0.1 * SR)


def test_gain_is_in_db(tmp_path):
    lib, manifest = fake_lib(tmp_path, {"click": click_at(0.005)})
    a = render_bus(one("click", 0.5), manifest, lib, 1.0)
    b = render_bus({"cues": [{"sound": "click", "t": 0.5, "gain": -6, "pan": 0}], "ducks": []}, manifest, lib, 1.0)
    assert np.abs(b).max() / np.abs(a).max() == pytest.approx(10 ** (-6 / 20), rel=1e-3)


def test_pan_is_constant_power(tmp_path):
    lib, manifest = fake_lib(tmp_path, {"click": click_at(0.005)})
    peak = np.abs(click_at(0.005)).max()
    left = render_bus(one("click", 0.5, pan=-1), manifest, lib, 1.0)
    right = render_bus(one("click", 0.5, pan=1), manifest, lib, 1.0)
    centre = render_bus(one("click", 0.5, pan=0), manifest, lib, 1.0)
    assert np.abs(left[:, 1]).max() < 1e-6 and np.abs(left[:, 0]).max() == pytest.approx(peak, rel=1e-4)
    assert np.abs(right[:, 0]).max() < 1e-6 and np.abs(right[:, 1]).max() == pytest.approx(peak, rel=1e-4)
    assert 20 * np.log10(np.abs(centre[:, 0]).max() / peak) == pytest.approx(-3.01, abs=0.02)
    for p in (-0.7, -0.2, 0.15, 0.6):
        y = render_bus(one("click", 0.5, pan=p), manifest, lib, 1.0)
        assert (y[:, 0] ** 2 + y[:, 1] ** 2).sum() == pytest.approx((centre ** 2).sum(), rel=1e-4)


def test_loops_tile_to_dur_without_clicks(tmp_path):
    t = np.arange(int(0.8 * SR)) / SR
    bed = (0.5 * np.sin(2 * np.pi * 110 * t) + 0.2 * np.sin(2 * np.pi * 37 * t)).astype(np.float32)  # no clean cycle
    lib, manifest = fake_lib(tmp_path, {"hum": bed}, loops={"hum"})
    y = render_bus(one("hum", 0.5, dur=3.0), manifest, lib, 4.0)[:, 0]
    on = np.flatnonzero(np.abs(y) > 0)
    assert on[0] >= round(0.5 * SR) and on[-1] < round(3.5 * SR)  # cut to dur
    body = y[round(0.55 * SR):round(3.45 * SR)]  # inside the 30 ms end fades
    dy = np.abs(np.diff(body))
    typical = np.median([dy[i:i + 480].max() for i in range(0, len(dy) - 480, 480)])  # per 10 ms
    step = 0.75  # copies start every 0.8 − 0.05 s; a butt join would step the 37 Hz part by ~0.12 (16× typical)
    seams = [dy[max(0, round((k * step - 0.05) * SR)):round((k * step + 0.1) * SR)].max() for k in (1, 2, 3)]
    assert max(seams) <= 2 * typical
    assert np.abs(y[round(0.5 * SR)]) < 0.01 and np.abs(y[round(3.5 * SR) - 1]) < 0.02  # faded at both ends
    rms = [np.sqrt(np.mean(body[i:i + 4800] ** 2)) for i in range(0, len(body) - 4800, 4800)]
    assert 20 * np.log10(max(rms) / min(rms)) < 3.5  # equal-power seams: never a hole (at most +3 dB if correlated)


def test_unknown_sound_fails(tmp_path):
    lib, manifest = fake_lib(tmp_path, {"click": click_at(0.005)})
    with pytest.raises(KeyError, match="'clack'"):
        render_bus(one("clack", 0.5), manifest, lib, 1.0)


def test_a_cue_outside_the_film_fails(tmp_path):
    lib, manifest = fake_lib(tmp_path, {"click": click_at(0.005)})
    with pytest.raises(ValueError, match="outside"):
        render_bus(one("click", 1.5), manifest, lib, 1.0)


def test_load_sheet_reads_cues_and_ducks(tmp_path):
    p = tmp_path / "sfx.json"
    p.write_text(json.dumps({"fps": 30, "cues": [{"sound": "a", "t": 1.0, "gain": -3, "pan": 0}],
                             "ducks": [{"t": 1, "dur": 0.1, "depth": -30, "fade": 0.005, "bus": "music"}]}))
    s = load_sheet(p)
    assert len(s["cues"]) == 1 and s["ducks"][0]["bus"] == "music"
