import json
import subprocess

import numpy as np
import pytest

from gitloom_film.elevenlabs import ElevenLabsError, MusicResult
from gitloom_film.music import generate_variants
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
