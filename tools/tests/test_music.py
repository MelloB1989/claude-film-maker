import json
import subprocess

import numpy as np
import pytest

from gitloom_film.elevenlabs import ElevenLabsError, MusicResult
from gitloom_film.music import generate_variants, merge_plan, pick_meta
from gitloom_film.wav import read_wav

PLAN = {"positive_global_styles": [], "negative_global_styles": [],
        "sections": [{"section_name": "a", "positive_local_styles": [], "negative_local_styles": [],
                      "duration_ms": 3000, "lines": []}]}
QUIET = {"log": lambda *_: None}


@pytest.fixture(scope="module")
def mp3_bytes(tmp_path_factory):
    p = tmp_path_factory.mktemp("mp3") / "s.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-ac", "2", "-ar", "44100", "-b:a", "128k", str(p)], check=True)
    return p.read_bytes()


class FakeMusic:
    def __init__(self, channels=2, refuse_pcm=False, mp3=b""):
        self.calls, self.plans = [], []
        self.channels, self.refuse_pcm, self.mp3 = channels, refuse_pcm, mp3

    def compose(self, plan, model_id="music_v2_5", output_format="pcm_48000", seed=None):
        self.calls.append((output_format, seed))
        self.plans.append(plan)
        if output_format.startswith("pcm"):
            if self.refuse_pcm:
                raise ElevenLabsError(403, "output_format_not_allowed")
            n = int(sum(c["duration_ms"] for c in plan["chunks"]) / 1000 * 48000)
            pcm = (np.random.default_rng(0).uniform(-0.1, 0.1, n * self.channels) * 32767).astype("<i2")
            return MusicResult(pcm.tobytes(), output_format, 45, "m")
        return MusicResult(self.mp3, output_format, 45, "m")


def test_pcm_stereo_variant_written(tmp_path):
    c = FakeMusic()
    [p] = generate_variants(c, PLAN, tmp_path, [11], **QUIET)
    x, sr = read_wav(p, mono=False)
    assert p.name == "score-seed11.wav" and sr == 48000 and x.shape == (144000, 2)
    assert (tmp_path / "score-seed11.plan.json").exists()
    assert "chunks" in c.plans[0] and "sections" not in c.plans[0]  # music_v2_5 takes a chunk plan


def test_sidecar_records_the_section_plan_and_the_chunks_sent(tmp_path):
    c = FakeMusic()
    generate_variants(c, PLAN, tmp_path, [11], **QUIET)
    side = json.loads((tmp_path / "score-seed11.plan.json").read_text())
    assert side["format"] == "pcm_48000" and side["plan"] == PLAN and side["chunks"] == c.plans[0]


def test_pcm_mono_is_widened_to_stereo(tmp_path):
    [p] = generate_variants(FakeMusic(channels=1), PLAN, tmp_path, [3], **QUIET)
    x, _ = read_wav(p, mono=False)
    assert x.shape == (144000, 2) and np.allclose(x[:, 0], x[:, 1])


def test_refused_pcm_falls_back_to_mp3(tmp_path, mp3_bytes):
    c = FakeMusic(refuse_pcm=True, mp3=mp3_bytes)
    [p] = generate_variants(c, PLAN, tmp_path, [5], **QUIET)
    x, sr = read_wav(p, mono=False)
    assert c.calls == [("pcm_48000", 5), ("mp3_44100_128", 5)]
    assert all("chunks" in sent and "sections" not in sent for sent in c.plans)  # both branches send the chunk plan
    assert sr == 48000 and x.shape[1] == 2 and abs(len(x) / sr - 3.0) < 0.1


def test_existing_variant_is_not_regenerated(tmp_path):
    c = FakeMusic()
    generate_variants(c, PLAN, tmp_path, [11], **QUIET)
    generate_variants(c, PLAN, tmp_path, [11], **QUIET)
    assert len(c.calls) == 1


PLAN2 = {**PLAN, "positive_global_styles": ["tape saturation"]}  # a later plan: different styles, same seeds


def test_a_changed_plan_gets_its_own_file_and_never_overwrites(tmp_path):
    c = FakeMusic()
    [first] = generate_variants(c, PLAN, tmp_path, [11], **QUIET)
    before = first.read_bytes()
    [second] = generate_variants(c, PLAN2, tmp_path, [11], **QUIET)
    assert len(c.calls) == 2 and second != first
    assert second.name.startswith("score-seed11-") and len(second.stem.split("-")[-1]) == 8
    assert first.read_bytes() == before  # the chosen seed's audio is untouched
    assert json.loads((tmp_path / "score-seed11.plan.json").read_text())["plan"] == PLAN
    assert json.loads(second.with_suffix(".plan.json").read_text())["plan"] == PLAN2
    assert generate_variants(c, PLAN2, tmp_path, [11], **QUIET) == [second] and len(c.calls) == 2  # reused


def test_a_seed_file_of_unknown_plan_is_not_reused(tmp_path):
    (tmp_path / "score-seed11.wav").write_bytes(b"RIFF-legacy")  # no sidecar: which plan made it is unknown
    c = FakeMusic()
    [p] = generate_variants(c, PLAN, tmp_path, [11], **QUIET)
    assert len(c.calls) == 1 and p.name != "score-seed11.wav"
    assert (tmp_path / "score-seed11.wav").read_bytes() == b"RIFF-legacy"


def test_merge_keeps_the_pick_and_the_edit_and_adds_variants(tmp_path):
    music = tmp_path / "audio" / "music"
    music.mkdir(parents=True)
    (music / "score-seed11.plan.json").write_text(json.dumps({"format": "pcm_48000", "plan": PLAN, "chunks": {}}))
    old = {"plan": PLAN, "meta": {"bpm": 100}, "variants": ["audio/music/score-seed11.wav", "audio/music/score-seed12.wav"],
           "chosen": "audio/music/score-seed11-edit.wav",
           "edit": {"source": "audio/music/score-seed11.wav", "map": "0-3", "source_downbeats": [0.0]}}
    mp = merge_plan(old, PLAN2, {"bpm": 101}, ["audio/music/score-seed12.wav", "audio/music/score-seed21.wav"],
                    tmp_path)
    assert mp["chosen"] == old["chosen"] and mp["edit"] == old["edit"]
    assert mp["variants"] == ["audio/music/score-seed11.wav", "audio/music/score-seed12.wav",
                              "audio/music/score-seed21.wav"]
    assert (mp["plan"], mp["meta"]) == (PLAN2, {"bpm": 101})  # the latest run's plan
    assert mp["chosen_plan"] == PLAN  # the plan the chosen score was composed from


def test_merge_into_nothing_starts_a_fresh_plan(tmp_path):
    mp = merge_plan(None, PLAN, {"bpm": 100}, ["audio/music/score-seed11.wav"], tmp_path)
    assert mp == {"plan": PLAN, "meta": {"bpm": 100}, "variants": ["audio/music/score-seed11.wav"], "chosen": None}


# --- the pick's own section timing (chosen_meta), which film-beats reads ---


def timed(*sections, tempo="100 BPM"):
    """A plan of (name, ms) sections composed at `tempo`, a global style as music_plan.PALETTE writes it."""
    return {"positive_global_styles": ["minor key", tempo], "negative_global_styles": [],
            "sections": [{"section_name": n, "positive_local_styles": [], "negative_local_styles": [],
                          "duration_ms": ms, "lines": []} for n, ms in sections]}


RUN1 = timed(("cold open", 7200), ("honest", 4800))
RUN2 = timed(("cold open", 9600), ("honest", 2400))
# worked by hand: each section starts where the durations before it end
META1 = {"bpm": 100.0, "sections": [{"name": "cold open", "start": 0.0, "end": 7.2},
                                    {"name": "honest", "start": 7.2, "end": 12.0}]}
META2 = {"bpm": 100.0, "sections": [{"name": "cold open", "start": 0.0, "end": 9.6},
                                    {"name": "honest", "start": 9.6, "end": 12.0}]}


def sidecar_at(root, name, plan, meta=None):
    """A variant's sidecar under root/audio/music; one written before sidecars recorded their meta has none."""
    d = root / "audio" / "music"
    d.mkdir(parents=True, exist_ok=True)
    doc = {"format": "pcm_48000", "plan": plan, "chunks": {}, **({"meta": meta} if meta is not None else {})}
    (d / f"{name}.plan.json").write_text(json.dumps(doc))


def test_the_sidecar_records_the_section_timing_the_variant_was_composed_to(tmp_path):
    generate_variants(FakeMusic(), RUN1, tmp_path, [11], meta=META1, **QUIET)
    assert json.loads((tmp_path / "score-seed11.plan.json").read_text())["meta"] == META1


def test_a_picks_timing_is_its_own_though_it_came_from_an_earlier_run(tmp_path):
    # seed 11 came from run 1 (an old sidecar, no meta of its own), but was picked after run 2 wrote `meta`
    sidecar_at(tmp_path, "score-seed11", RUN1)
    sidecar_at(tmp_path, "score-seed21", RUN2, META2)
    old = {"plan": RUN2, "meta": META2, "variants": ["audio/music/score-seed11.wav", "audio/music/score-seed21.wav"],
           "chosen": "audio/music/score-seed11.wav"}
    mp = merge_plan(old, RUN2, META2, [], tmp_path)
    assert mp["chosen_meta"] == META1 and mp["meta"] == META2


def test_a_pick_changed_by_hand_gets_its_own_timing_back(tmp_path):
    # checkpoint C2: `chosen` edited by hand to a newer run's variant, while chosen_meta still holds the old pick's
    sidecar_at(tmp_path, "score-seed11", RUN1)
    sidecar_at(tmp_path, "score-seed21", RUN2, META2)
    mp = {"plan": RUN2, "meta": META2, "variants": [], "chosen": "audio/music/score-seed21.wav", "chosen_meta": META1}
    assert pick_meta(mp, tmp_path) == META2
    assert merge_plan(mp, RUN1, META1, [], tmp_path)["chosen_meta"] == META2  # recomputed on every merge


def test_a_spliced_pick_has_its_source_seeds_timing_and_no_later_run_moves_it(tmp_path):
    sidecar_at(tmp_path, "score-seed11", RUN1)
    old = {"plan": RUN1, "meta": META1, "variants": [], "chosen": "audio/music/score-seed11-edit.wav",
           "edit": {"source": "audio/music/score-seed11.wav", "map": "0-3", "source_downbeats": [0.0]}}
    mp = merge_plan(old, RUN2, META2, [], tmp_path)
    assert mp["chosen_meta"] == META1 and mp["meta"] == META2
    assert merge_plan(mp, RUN2, {"bpm": 101.0, "sections": []}, [], tmp_path)["chosen_meta"] == META1


def test_a_pick_whose_timing_cannot_be_known_keeps_no_stale_one(tmp_path):
    sidecar_at(tmp_path, "score-seed11", timed(("cold open", 7200), tempo="minor key"))  # no tempo, no meta
    mp = {"plan": RUN2, "meta": META2, "variants": [], "chosen": "audio/music/score-seed11.wav", "chosen_meta": META2}
    assert pick_meta(mp, tmp_path) is None
    assert "chosen_meta" not in merge_plan(mp, RUN2, META2, [], tmp_path)
    assert pick_meta({"chosen": "audio/music/score-seed99.wav"}, tmp_path) is None  # no sidecar at all
    assert pick_meta({"chosen": None}, tmp_path) is None
