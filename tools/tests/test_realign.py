import json

import pytest

from gitloom_film.realign import map_words, realign_take, tokens


def fa(*words):
    out = []
    for i, (t, s, e) in enumerate(words):
        if i:
            out.append({"text": " ", "start": out[-1]["end"], "end": s, "loss": 0.5})
        out.append({"text": t, "start": s, "end": e, "loss": 0.5})
    return {"words": out, "loss": 0.8}


class FakeFA:
    def __init__(self, result):
        self.result, self.calls = result, []

    def forced_alignment(self, audio, text, filename="take.wav"):
        self.calls.append((len(audio), text, filename))
        return self.result


def take(tmp_path, text="Every conversation... back to zero."):
    d = tmp_path / "L02"
    d.mkdir(parents=True)
    (d / "1.wav").write_bytes(b"RIFF")
    (d / "1.json").write_text(json.dumps({"line": "L02", "take": 1, "text": text,
                                          "words": [{"w": "Every", "start": 0.0, "end": 0.4}]}))
    return d / "1.wav", d / "1.json"


def test_tokens_keep_attached_and_merge_detached_punctuation():
    assert tokens("Every conversation... back to zero.") == ["Every", "conversation...", "back", "to", "zero."]
    assert tokens("...I say so.") == ["...I", "say", "so."]
    assert tokens("Go ahead ... Blame me.") == ["Go", "ahead...", "Blame", "me."]


def test_map_words_keeps_our_text_and_takes_measured_times():
    words = map_words(["It's", "you..."], fa(("It's", 0.16, 0.42), ("you...", 0.5, 1.44))["words"])
    assert words == [{"w": "It's", "start": 0.16, "end": 0.42}, {"w": "you...", "start": 0.5, "end": 1.44}]


def test_map_words_count_mismatch_raises():
    with pytest.raises(ValueError, match="found 1 words, the text has 2"):
        map_words(["a", "b"], fa(("a", 0.0, 0.2))["words"])


def test_realign_take_rewrites_times_and_is_idempotent(tmp_path):
    wav, meta = take(tmp_path)
    c = FakeFA(fa(("Every", 0.16, 0.42), ("conversation...", 0.5, 1.44), ("back", 2.2, 2.42), ("to", 2.52, 2.6),
                  ("zero.", 2.7, 3.14)))
    assert realign_take(c, wav, meta, log=lambda *_: None) == "forced"
    m = json.loads(meta.read_text())
    assert m["aligned"] == "forced" and m["align_loss"] == 0.8
    assert [w["start"] for w in m["words"]] == [0.16, 0.5, 2.2, 2.52, 2.7]
    assert m["words"][1]["w"] == "conversation..."
    assert c.calls == [(4, "Every conversation... back to zero.", "1.wav")]
    assert realign_take(c, wav, meta, log=lambda *_: None) == "skipped"
    assert len(c.calls) == 1  # never pays twice


def test_realign_take_falls_back_when_counts_differ(tmp_path):
    wav, meta = take(tmp_path, text="Hi there.")
    logged = []
    assert realign_take(FakeFA(fa(("Hi", 0.1, 0.3))), wav, meta, log=logged.append) == "tts-fallback"
    m = json.loads(meta.read_text())
    assert m["aligned"] == "tts-fallback" and m["words"] == [{"w": "Every", "start": 0.0, "end": 0.4}]
    assert "keeping the TTS times" in logged[0]
