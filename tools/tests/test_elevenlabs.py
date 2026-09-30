import base64
import json

import pytest

from gitloom_film.elevenlabs import ElevenLabs, ElevenLabsError, Response

KEY = "sk_test_SECRET_1234567890"


def fake(responses, calls):
    def transport(method, url, headers, body):
        calls.append((method, url, headers, body))
        return responses.pop(0)
    return transport


def tts_body(audio=b"\x01\x00\x02\x00", chars="Hi."):
    return json.dumps({
        "audio_base64": base64.b64encode(audio).decode(),
        "alignment": {"characters": list(chars),
                      "character_start_times_seconds": [0.0, 0.1, 0.2],
                      "character_end_times_seconds": [0.1, 0.2, 0.3]},
    }).encode()


def test_tts_decodes_audio_and_logs_cost(tmp_path):
    calls = []
    log = tmp_path / "credits.log"
    c = ElevenLabs(KEY, fake([Response(200, {"character-cost": "3", "request-id": "r1"}, tts_body())], calls), log)
    r = c.tts("voice123", "Hi.", speed=1.1)
    assert r.audio == b"\x01\x00\x02\x00"
    assert r.alignment["characters"] == ["H", "i", "."]
    assert (r.cost, r.request_id) == (3, "r1")
    method, url, headers, body = calls[0]
    assert method == "POST"
    assert url == "https://api.elevenlabs.io/v1/text-to-speech/voice123/with-timestamps?output_format=pcm_48000"
    assert headers["xi-api-key"] == KEY
    assert json.loads(body) == {"text": "Hi.", "model_id": "eleven_v4", "voice_settings": {"speed": 1.1}}
    rec = json.loads(log.read_text().strip())
    assert rec["cost"] == 3 and rec["request_id"] == "r1" and rec["path"].startswith("/v1/text-to-speech/")


def test_retries_429_and_5xx_then_succeeds():
    calls, slept = [], []
    responses = [Response(429, {}, b"busy"), Response(503, {}, b"down"), Response(200, {"character-cost": "1"}, tts_body())]
    c = ElevenLabs(KEY, fake(responses, calls), sleep=slept.append)
    c.tts("v", "Hi.")
    assert len(calls) == 3 and slept == [2.0, 4.0]


def test_client_error_raises_without_the_key():
    body = json.dumps({"detail": {"message": f"invalid key {KEY}"}}).encode()
    c = ElevenLabs(KEY, fake([Response(401, {}, body)], []))
    with pytest.raises(ElevenLabsError) as e:
        c.tts("v", "Hi.")
    assert e.value.status == 401
    assert KEY not in str(e.value) and "<redacted>" in str(e.value)


def test_key_never_in_repr_or_log(tmp_path):
    log = tmp_path / "credits.log"
    c = ElevenLabs(KEY, fake([Response(200, {"character-cost": "1"}, tts_body())], []), log)
    c.tts("v", "Hi.")
    assert KEY not in repr(c) and KEY not in str(c)
    assert KEY not in log.read_text()


def test_compose_sends_the_plan():
    calls = []
    c = ElevenLabs(KEY, fake([Response(200, {"character-cost": "900", "request-id": "m1"}, b"PCMBYTES")], calls))
    plan = {"positive_global_styles": ["x"], "negative_global_styles": [], "sections": []}
    r = c.compose(plan, seed=7)
    assert (r.audio, r.cost, r.output_format, r.request_id) == (b"PCMBYTES", 900, "pcm_48000", "m1")
    assert calls[0][1] == "https://api.elevenlabs.io/v1/music?output_format=pcm_48000"
    assert json.loads(calls[0][3]) == {"composition_plan": plan, "model_id": "music_v2_5", "seed": 7}


def test_load_key_strips_whitespace(tmp_path):
    from gitloom_film.elevenlabs import load_key
    f = tmp_path / "k"
    f.write_text(f"  {KEY}\n")
    assert load_key(f) == KEY
    f.write_text("\n")
    with pytest.raises(RuntimeError, match="empty"):
        load_key(f)
