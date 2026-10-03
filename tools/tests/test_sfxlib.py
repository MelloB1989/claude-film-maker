import copy
import json

import numpy as np
import pytest

from gitloom_film import sfxlib
from gitloom_film.elevenlabs import ElevenLabs, ElevenLabsError, Response, SoundResult
from gitloom_film.sfxlib import (estimate, find_hit, generate, pick, plan, process, qc, request_key, request_of,
                                 slice_hits, to_wav48)

KEY = "sk_test_SECRET_1234567890"
SR = 48000


def sound_spec(**kw):
    d = {"family": "commits", "prompt": "one delicate high clink, close-mic, dry, no music, no voice",
         "duration": 0.5, "influence": 0.45, "loop": False, "align": "onset", "gain": -20.0, "slice": 0,
         "pick": None}
    d.update(kw)
    return d


def palette_with(*ids, variants=2, **kw):
    return {"model_id": "eleven_text_to_sound_v2", "output_formats": ["pcm_48000", "pcm_44100", "mp3_44100_128"],
            "variants": variants, "seed_base": 3100, "seeds_honoured": None, "send_seed": True,
            "sounds": {i: sound_spec(**kw) for i in ids}}


def click_take(sr=SR, dur=0.5, at=0.05, seed=0):
    """A decaying noise burst starting at `at`, over a quiet noise floor."""
    rng = np.random.default_rng(seed)
    y = rng.normal(0, 1e-4, int(dur * sr)).astype(np.float32)
    i = int(at * sr)
    n = int(0.08 * sr)
    burst = rng.normal(0, 1, n) * np.exp(-np.arange(n) / (0.01 * sr))
    burst[0] = 1.0
    y[i:i + n] += (0.5 * burst / np.abs(burst).max()).astype(np.float32)
    return y


def pcm16(y):
    return (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()


class CountingClient:
    """Returns 0.5 s (or the requested duration) of PCM with a click, and counts calls."""

    def __init__(self, cost_per_second=40, refuse=()):
        self.calls = 0
        self.formats = []
        self.cps = cost_per_second
        self.refuse = set(refuse)

    def sound(self, text, duration_seconds=None, prompt_influence=None, loop=False,
              model_id="eleven_text_to_sound_v2", output_format="pcm_48000", seed=None):
        self.formats.append(output_format)
        if output_format in self.refuse:
            raise ElevenLabsError(403, f'{{"detail": "output_format {output_format} requires a higher tier"}}')
        self.calls += 1
        dur = duration_seconds or 0.5
        sr = int(output_format.split("_")[1])
        y = click_take(sr=sr, dur=dur, seed=self.calls)
        return SoundResult(pcm16(y), output_format, int(round(self.cps * dur)), f"req{self.calls}")


def run(pal, client, tmp_path, budget=8000, **kw):
    return generate(pal, client, tmp_path / "lib", tmp_path / "manifest.json", budget=budget, **kw)


# ---- requests and keys ----

def test_request_is_the_json_sent_with_a_seed_per_sound_and_variant():
    pal = palette_with("a", "b")
    r = request_of(pal, "b", 1)
    assert r == {"text": pal["sounds"]["b"]["prompt"], "model_id": "eleven_text_to_sound_v2", "duration_seconds": 0.5,
                 "prompt_influence": 0.45, "loop": False, "seed": 3100 + 100 * 1 + 1, "output_format": "pcm_48000"}
    assert request_key(r) != request_key(request_of(pal, "b", 0))
    assert request_key(r) == request_key(dict(reversed(list(r.items()))))


def test_without_seeds_the_variant_still_keys_the_request():
    pal = palette_with("a")
    pal["send_seed"] = False
    r0, r1 = request_of(pal, "a", 0), request_of(pal, "a", 1)
    assert "seed" not in r0 and r0["variant"] == 0
    assert request_key(r0) != request_key(r1)


# ---- the cache ----

def test_a_cached_request_is_never_paid_for_twice(tmp_path):          # Review Focus 1
    pal = palette_with("glass_clink", variants=2)
    client = CountingClient()
    run(pal, client, tmp_path)
    assert client.calls == 2
    run(pal, client, tmp_path)
    assert client.calls == 2                                            # nothing new
    pal["sounds"]["glass_clink"]["prompt"] += ", brighter"
    run(pal, client, tmp_path)
    assert client.calls == 4                                            # only the edited sound


def test_an_edit_to_one_sound_refetches_only_it(tmp_path):
    pal = palette_with("a", "b", variants=1)
    client = CountingClient()
    run(pal, client, tmp_path)
    pal["sounds"]["b"]["influence"] = 0.7
    todo = plan(pal, json.loads((tmp_path / "manifest.json").read_text()), tmp_path / "lib")
    assert [(s, v) for s, v, _ in todo] == [("b", 0)]


def test_a_corrupted_wav_is_refetched(tmp_path):
    pal = palette_with("glass_clink", variants=1)
    client = CountingClient()
    run(pal, client, tmp_path)
    man = json.loads((tmp_path / "manifest.json").read_text())
    wav = tmp_path / "lib" / man["variants"]["glass_clink/0"]["wav"]
    assert wav.exists() and wav.with_suffix(".raw").exists()
    assert wav.parent.name == "glass_clink" and wav.stem == man["variants"]["glass_clink/0"]["key"][:12]
    wav.write_bytes(wav.read_bytes()[:-10] + b"\x00" * 10)
    assert len(plan(pal, man, tmp_path / "lib")) == 1
    wav.unlink()
    assert len(plan(pal, man, tmp_path / "lib")) == 1
    run(pal, client, tmp_path)
    assert client.calls == 1 and wav.exists()                           # rebuilt from the paid raw bytes, free
    assert not plan(pal, json.loads((tmp_path / "manifest.json").read_text()), tmp_path / "lib")
    wav.unlink()
    wav.with_suffix(".raw").unlink()
    run(pal, client, tmp_path)
    assert client.calls == 2                                            # raw gone too: fetched again


def test_the_manifest_records_the_request_seed_cost_and_qc(tmp_path):
    pal = palette_with("glass_clink", variants=2)
    run(pal, CountingClient(), tmp_path)
    man = json.loads((tmp_path / "manifest.json").read_text())
    e = man["variants"]["glass_clink/1"]
    assert e["seed"] == 3101 and e["request"]["seed"] == 3101 and e["output_format"] == "pcm_48000"
    assert e["cost"] == 20 and e["request_id"] and len(e["sha256"]) == 64
    assert set(e["qc"]) >= {"peak_dbfs", "lufs", "onset_s", "dur_s", "centroid_hz", "silence_ratio", "clipped", "dc"}
    assert e["hit_s"] == pytest.approx(0.005, abs=1 / SR)
    assert man["picks"]["glass_clink"]["variant"] in (0, 1)
    assert man["picks"]["glass_clink"]["gain"] == -20.0


def test_the_seed_is_recorded_even_when_not_sent(tmp_path):
    pal = palette_with("glass_clink", variants=1)
    pal["send_seed"] = False
    run(pal, CountingClient(), tmp_path)
    e = json.loads((tmp_path / "manifest.json").read_text())["variants"]["glass_clink/0"]
    assert e["seed"] == 3100 and "seed" not in e["request"]


def test_the_manifest_holds_no_secret(tmp_path):
    calls = []

    def transport(method, url, headers, body):
        calls.append(url)
        return Response(200, {"character-cost": "20", "request-id": "r"}, pcm16(click_take()))
    client = ElevenLabs(KEY, transport, tmp_path / "credits.log")
    run(palette_with("glass_clink"), client, tmp_path)
    assert len(calls) == 2
    for f in [tmp_path / "manifest.json", tmp_path / "credits.log"]:
        assert KEY.encode() not in f.read_bytes()


def test_a_palette_pick_overrides_the_auto_pick(tmp_path):
    pal = palette_with("glass_clink")
    pal["sounds"]["glass_clink"]["pick"] = 1
    run(pal, CountingClient(), tmp_path)
    p = json.loads((tmp_path / "manifest.json").read_text())["picks"]["glass_clink"]
    assert p["variant"] == 1 and p["auto"] in (0, 1)


# ---- budget ----

def test_estimate_uses_the_rate_times_the_seconds():
    pal = palette_with("a", "b", variants=2)
    todo = plan(pal, {}, None)
    assert estimate(todo, 40) == 4 * 0.5 * 40


def test_budget_refuses_and_stops(tmp_path):
    pal = palette_with("a", "b", "c", variants=2)                       # 6 × 0.5 s × 40 = 120
    client = CountingClient()
    res = run(pal, client, tmp_path, budget=100)
    assert client.calls == 0 and res["refused"]
    client = CountingClient(cost_per_second=80)                         # the API costs double what we estimate
    res = run(pal, client, tmp_path, budget=125)
    assert client.calls == 3 and res["spent"] == 120 and res["stopped"]  # the 4th (→160) would cross 125


def test_the_estimate_learns_the_measured_rate(tmp_path):
    pal = palette_with("a", variants=1)
    run(pal, CountingClient(cost_per_second=20), tmp_path)
    pal["sounds"]["b"] = sound_spec(duration=1.0)
    res = run(pal, CountingClient(cost_per_second=20), tmp_path, dry_run=True)
    assert res["credits_per_second"] == pytest.approx(20) and res["estimate"] == 20


def test_dry_run_calls_nothing(tmp_path):
    client = CountingClient()
    res = run(palette_with("a"), client, tmp_path, dry_run=True)
    assert client.calls == 0 and len(res["todo"]) == 2 and res["estimate"] == 40


# ---- formats ----

def test_format_fallback_on_a_refused_format(tmp_path):
    client = CountingClient(refuse={"pcm_48000"})
    run(palette_with("glass_clink", variants=1), client, tmp_path)
    assert client.formats == ["pcm_48000", "pcm_44100"]
    man = json.loads((tmp_path / "manifest.json").read_text())
    e = man["variants"]["glass_clink/0"]
    assert e["output_format"] == "pcm_44100"
    assert e["qc"]["dur_s"] < 0.5 and abs(e["hit_s"] - 0.005) < 2 / SR


def test_another_error_is_not_a_format_refusal(tmp_path):
    class Broken(CountingClient):
        def sound(self, *a, **kw):
            raise ElevenLabsError(422, "text too long")
    with pytest.raises(ElevenLabsError):
        run(palette_with("a", variants=1), Broken(), tmp_path)


def test_to_wav48_resamples_44k1():
    y = np.sin(2 * np.pi * 440 * np.arange(44100) / 44100).astype(np.float32) * 0.5
    out = to_wav48(pcm16(y), "pcm_44100")
    assert len(out) == 48000 and out.dtype == np.float32
    assert abs(np.abs(out).max() - 0.5) < 0.01


# ---- signal ----

def test_find_hit_and_trim_put_the_transient_at_5_ms():
    y = click_take(dur=1.0, at=0.3)
    assert find_hit(y, SR, "onset") == pytest.approx(0.3, abs=1 / SR)
    out, hit = process(y, SR, sound_spec(align="onset"))
    assert hit == pytest.approx(0.005, abs=1 / SR)
    assert find_hit(out, SR, "onset") == pytest.approx(0.005, abs=1 / SR)
    assert abs(out[0]) < 1e-3 and abs(out[-1]) < 1e-3                  # the fades


def test_peak_and_end_hits():
    y = click_take(dur=1.0, at=0.3)
    assert find_hit(y, SR, "peak") == pytest.approx(0.3, abs=0.002)
    t = np.arange(SR) / SR
    riser = (np.sin(2 * np.pi * 200 * t) * t ** 2 * 0.5).astype(np.float32)
    riser = np.concatenate([riser, np.zeros(SR // 4, np.float32)])
    out, hit = process(riser, SR, sound_spec(align="end", duration=1.25))
    assert hit == pytest.approx(len(out) / SR) and hit == pytest.approx(1.0, abs=0.03)


def test_a_loop_gets_a_seam_crossfade_and_no_trim():
    t = np.arange(2 * SR) / SR
    y = (0.3 * np.sin(2 * np.pi * 110.3 * t)).astype(np.float32)
    out, hit = process(y, SR, sound_spec(align=None, loop=True, duration=2.0))
    assert hit is None and len(out) == len(y) - int(0.05 * SR)
    seam = np.abs(out[0] - out[-1])
    step = np.abs(np.diff(out)).max()
    assert seam <= step * 1.5


def test_slice_hits_isolates_n_clicks():
    rng = np.random.default_rng(3)
    y = rng.normal(0, 3e-4, 4 * SR).astype(np.float32)
    starts = [0.2, 0.6, 1.1, 1.5, 2.0, 2.45, 2.9, 3.4]
    for k, s in enumerate(starts):
        y += np.roll(click_take(dur=4.0, at=0.0, seed=k + 10) * (0.5 + 0.06 * k), int(s * SR)) * \
             (np.arange(4 * SR) >= int(s * SR))
    weak = int(1.3 * SR)
    y[weak:weak + 200] += 0.01                                          # a faint blip is not a hit
    parts = slice_hits(y, SR, 8)
    assert len(parts) == 8
    for p in parts:
        assert find_hit(p, SR, "onset") == pytest.approx(0.005, abs=1 / SR)
        assert len(p) < 0.6 * SR


def test_qc_rejects_clipped_and_silent():
    good, _ = process(click_take(), SR, sound_spec())                   # QC runs on the trimmed take
    q = qc(good, SR)
    assert not q["clipped"] and q["peak_dbfs"] == pytest.approx(-6.0, abs=0.2) and q["silence_ratio"] < 0.6
    assert q["onset_s"] == pytest.approx(0.005, abs=1 / SR)
    clipped = np.clip(good * 4, -1, 1)
    silent = np.zeros(SR, np.float32)
    silent[100:200] = 0.2
    late = click_take(dur=1.0, at=0.6)
    quiet = good * 0.005
    vs = [{"qc": qc(x, SR), "align": "onset"} for x in (clipped, silent, late, quiet, good)]
    assert vs[0]["qc"]["clipped"] and vs[1]["qc"]["silence_ratio"] > 0.6
    assert pick(vs, "commits") == 4
    assert pick(vs[:4], "commits") == -1


def test_pick_prefers_a_sharp_transient_for_one_shots_and_a_smooth_envelope_for_beds():
    t = np.arange(SR) / SR
    soft = click_take(at=0.05).copy()
    i = int(0.05 * SR)
    soft[i:i + 2400] *= np.linspace(0, 1, 2400)                          # a slow 50 ms attack
    sharp = click_take(at=0.05)
    soft, sharp = process(soft, SR, sound_spec())[0], process(sharp, SR, sound_spec())[0]
    assert pick([{"qc": qc(soft, SR), "align": "onset"}, {"qc": qc(sharp, SR), "align": "onset"}], "x") == 1
    steady = (0.2 * np.sin(2 * np.pi * 80 * t)).astype(np.float32)
    lumpy = steady * (1 + 0.8 * (np.sin(2 * np.pi * 3 * t) > 0))
    assert pick([{"qc": qc(lumpy, SR), "align": None}, {"qc": qc(steady, SR), "align": None}], "x") == 1


def test_slices_become_sounds_of_their_own(tmp_path):
    class Clicker(CountingClient):
        def sound(self, text, duration_seconds=None, **kw):
            self.calls += 1
            y = np.zeros(int(duration_seconds * SR), np.float32)
            for k, s in enumerate([0.1, 0.5, 0.9, 1.4]):
                y += np.roll(click_take(dur=duration_seconds, at=0.0, seed=k), int(s * SR)) * \
                     (np.arange(len(y)) >= int(s * SR))
            return SoundResult(pcm16(y), "pcm_48000", 80, f"r{self.calls}")
    pal = palette_with("insert_pop", variants=1, duration=2.0, slice=4, gain=-22.0)
    run(pal, Clicker(), tmp_path)
    man = json.loads((tmp_path / "manifest.json").read_text())
    for k in range(1, 5):
        e = man["variants"][f"insert_pop_{k}/0"]
        assert (tmp_path / "lib" / e["wav"]).exists() and e["hit_s"] == pytest.approx(0.005, abs=1 / SR)
        assert man["picks"][f"insert_pop_{k}"]["gain"] == -22.0
    assert len(plan(pal, man, tmp_path / "lib")) == 0


def test_to_wav48_downmixes_interleaved_stereo_by_the_requested_duration():
    t = np.arange(int(0.48 * SR)) / SR
    left = (0.4 * np.sin(2 * np.pi * 3000 * t)).astype(np.float32)
    right = left * 0.8
    raw = pcm16(np.stack([left, right], axis=1).reshape(-1))
    out = to_wav48(raw, "pcm_48000", duration=0.5)
    assert len(out) == len(t) and np.abs(out).max() == pytest.approx(0.36, abs=0.01)
    mono = to_wav48(pcm16(left), "pcm_48000", duration=0.5)
    assert len(mono) == len(t)



def test_slice_hits_never_returns_an_empty_slice_when_hits_ride_a_sustained_bed():
    t = np.arange(2 * SR) / SR
    y = (0.05 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)          # never falls below the walk-back floor
    for s in (0.3, 0.42, 1.2):
        y += np.roll(click_take(dur=2.0, at=0.0, seed=int(s * 10)), int(s * SR)) * (np.arange(2 * SR) >= int(s * SR))
    parts = slice_hits(y, SR, 3)
    assert len(parts) == 3 and all(len(p) > int(0.02 * SR) for p in parts)
    assert all(np.isfinite(list(qc(p, SR).values())[:6]).all() for p in parts)


def test_qc_survives_an_empty_take():
    q = qc(np.zeros(0, np.float32), SR)
    assert q["dur_s"] == 0 and q["peak_dbfs"] == -120.0


def test_slice_hits_stops_a_walk_back_at_the_previous_hit():
    rng = np.random.default_rng(5)
    y = rng.normal(0, 1e-4, 2 * SR).astype(np.float32)
    def hit(at, amp, tau):
        i, n = int(at * SR), int(0.6 * SR)
        y[i:i + n] += (amp * rng.normal(0, 1, n) * np.exp(-np.arange(n) / (tau * SR))).astype(np.float32)
    hit(0.2, 0.8, 0.15)                                                 # a long ringing tail…
    hit(0.32, 0.3, 0.02)                                                # …that a quieter hit lands inside
    hit(1.2, 0.5, 0.02)
    parts = slice_hits(y, SR, 3)
    assert len(parts) == 3 and all(len(p) > int(0.02 * SR) for p in parts)


def test_slice_hits_ignores_hits_far_below_the_loudest():
    rng = np.random.default_rng(9)
    y = rng.normal(0, 1e-5, 2 * SR).astype(np.float32)
    for s, amp in ((0.2, 1.0), (0.7, 0.8), (1.2, 0.9), (1.6, 0.008)):  # the last is 42 dB down: noise, not a hit
        i, n = int(s * SR), int(0.08 * SR)
        y[i:i + n] += (amp * 0.5 * rng.normal(0, 1, n) * np.exp(-np.arange(n) / (0.01 * SR))).astype(np.float32)
    assert len(slice_hits(y, SR, 4)) == 3


def test_each_slice_is_picked_on_its_own():
    from gitloom_film.sfxlib import update_picks
    good = qc(process(click_take(), SR, sound_spec())[0], SR)
    silent = dict(good, silence_ratio=0.9)
    pal = palette_with("insert_pop", duration=2.0, slice=2)
    e = lambda q, k, v: {"qc": q, "wav": f"insert_pop/x{v}_{k}.wav", "hit_s": 0.005}
    man = {"variants": {"insert_pop/0": {"qc": silent, "wav": "a", "hit_s": 0.005},
                        "insert_pop/1": {"qc": silent, "wav": "b", "hit_s": 0.005},
                        "insert_pop_1/0": e(silent, 1, 0), "insert_pop_1/1": e(good, 1, 1),
                        "insert_pop_2/0": e(good, 2, 0)}, "picks": {}}
    update_picks(pal, man)
    assert man["picks"]["insert_pop_1"]["variant"] == 1 and man["picks"]["insert_pop_1"]["wav"] == "insert_pop/x1_1.wav"
    assert man["picks"]["insert_pop_2"]["variant"] == 0 and not man["picks"]["insert_pop_2"]["rejected"]
    assert "insert_pop" not in man["picks"]


def test_reprocess_rebuilds_every_take_from_its_raw_without_a_call(tmp_path):
    from gitloom_film.sfxlib import reprocess
    pal = palette_with("glass_clink", variants=2)
    client = CountingClient()
    run(pal, client, tmp_path)
    man = json.loads((tmp_path / "manifest.json").read_text())
    (tmp_path / "lib" / man["variants"]["glass_clink/0"]["wav"]).unlink()
    pal["sounds"]["glass_clink"]["gain"] = -11.0                         # not part of the request
    n = reprocess(pal, tmp_path / "lib", tmp_path / "manifest.json")
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert n == 2 and client.calls == 2 and not plan(pal, man, tmp_path / "lib")
    assert man["picks"]["glass_clink"]["gain"] == -11.0


def test_a_slice_ends_before_the_next_hit_even_one_not_chosen():
    rng = np.random.default_rng(11)
    y = rng.normal(0, 1e-5, 3 * SR).astype(np.float32)
    starts = [0.2, 0.5, 0.8, 1.1, 1.4, 1.7]
    amps = [1.0, 0.3, 0.9, 0.3, 0.8, 0.3]                                # choose 3 of 6: the loud ones
    for s, amp in zip(starts, amps):
        i, n = int(s * SR), int(0.08 * SR)
        y[i:i + n] += (amp * 0.5 * rng.normal(0, 1, n) * np.exp(-np.arange(n) / (0.01 * SR))).astype(np.float32)
    parts = slice_hits(y, SR, 3)
    assert len(parts) == 3
    for p in parts:
        assert len(p) < 0.3 * SR                                        # never reaches the quiet hit 0.3 s later


def test_find_hit_skips_a_hissy_pre_roll():
    rng = np.random.default_rng(4)
    y = click_take(dur=0.5, at=0.15)
    y[: int(0.15 * SR)] += (0.03 * rng.normal(0, 1, int(0.15 * SR))).astype(np.float32)  # −24 dB hiss before
    assert find_hit(y, SR, "onset") == pytest.approx(0.15, abs=0.001)


def test_pick_passes_over_a_variant_far_quieter_than_the_rest():
    loud = qc(process(click_take(), SR, sound_spec())[0], SR)
    faint = dict(loud, peak_dbfs=-38.0, lufs=loud["lufs"] - 30, attack_ms=0.0)
    assert pick([{"qc": faint, "align": "onset"}, {"qc": dict(loud, attack_ms=5.0), "align": "onset"}], "x") == 1


def test_a_sound_can_set_its_own_slice_gap(tmp_path):
    class Rapid(CountingClient):
        def sound(self, text, duration_seconds=None, **kw):
            self.calls += 1
            rng = np.random.default_rng(self.calls)
            y = rng.normal(0, 1e-5, int(duration_seconds * SR)).astype(np.float32)
            for s in (0.1, 0.16, 0.22, 0.28):                            # 60 ms apart: under the 80 ms default
                i, n = int(s * SR), int(0.03 * SR)
                y[i:i + n] += (0.4 * rng.normal(0, 1, n) * np.exp(-np.arange(n) / (0.004 * SR))).astype(np.float32)
            return SoundResult(pcm16(y), "pcm_48000", 20, "r")
    pal = palette_with("flap", variants=1, duration=1.0, slice=4)
    run(pal, Rapid(), tmp_path)
    assert "flap_4/0" not in json.loads((tmp_path / "manifest.json").read_text())["variants"]
    pal["sounds"]["flap"]["slice_gap"] = 0.04
    from gitloom_film.sfxlib import reprocess
    reprocess(pal, tmp_path / "lib", tmp_path / "manifest.json")
    assert "flap_4/0" in json.loads((tmp_path / "manifest.json").read_text())["variants"]


def test_a_take_with_fewer_hits_than_asked_is_still_cached(tmp_path):
    class Two(CountingClient):
        def sound(self, text, duration_seconds=None, **kw):
            self.calls += 1
            y = np.zeros(int(duration_seconds * SR), np.float32)
            for k, s in enumerate([0.1, 0.9]):
                y += np.roll(click_take(dur=duration_seconds, at=0.0, seed=k), int(s * SR)) * \
                     (np.arange(len(y)) >= int(s * SR))
            return SoundResult(pcm16(y), "pcm_48000", 80, f"r{self.calls}")
    pal = palette_with("insert_pop", variants=1, duration=2.0, slice=4)
    client = Two()
    run(pal, client, tmp_path)
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert "insert_pop_2/0" in man["variants"] and "insert_pop_3/0" not in man["variants"]
    assert not plan(pal, man, tmp_path / "lib")
    run(pal, client, tmp_path)
    assert client.calls == 1


def test_every_written_take_peaks_at_minus_1_dbfs_and_records_the_normalisation(tmp_path):
    from gitloom_film.wav import read_wav
    class Quiet(CountingClient):
        def sound(self, *a, **kw):
            r = super().sound(*a, **kw)
            return SoundResult(pcm16(pcm16_to_float(r.audio) * 0.05), r.output_format, r.cost, r.request_id)
    from gitloom_film.wav import pcm16_to_float
    run(palette_with("glass_clink", variants=1), Quiet(), tmp_path)
    e = json.loads((tmp_path / "manifest.json").read_text())["variants"]["glass_clink/0"]
    y, _ = read_wav(tmp_path / "lib" / e["wav"])
    assert 20 * np.log10(np.abs(y).max()) == pytest.approx(-1.0, abs=0.05)
    assert e["qc"]["peak_dbfs"] == pytest.approx(-32.0, abs=0.3)          # QC is the take as generated
    assert e["norm_db"] == pytest.approx(31.0, abs=0.3)
