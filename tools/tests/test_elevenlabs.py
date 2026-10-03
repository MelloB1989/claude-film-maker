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


def test_forced_alignment_sends_multipart_without_query():
    calls = []
    body = json.dumps({"words": [{"text": "Hi.", "start": 0.1, "end": 0.3, "loss": 0.5}], "loss": 0.5}).encode()
    c = ElevenLabs(KEY, fake([Response(200, {"character-cost": "1"}, body)], calls))
    d = c.forced_alignment(b"RIFFWAVEDATA", "Hi.", "1.wav")
    assert d["words"][0]["start"] == 0.1
    method, url, headers, sent = calls[0]
    assert url == "https://api.elevenlabs.io/v1/forced-alignment"
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
    boundary = headers["Content-Type"].split("boundary=")[1]
    assert sent.startswith(f"--{boundary}\r\n".encode()) and sent.endswith(f"--{boundary}--\r\n".encode())
    assert b'name="file"; filename="1.wav"' in sent and b"RIFFWAVEDATA" in sent
    assert b'name="text"\r\n\r\nHi.\r\n' in sent


def test_a_redirect_is_an_error_not_a_success(tmp_path):
    calls = []
    log = tmp_path / "credits.log"
    c = ElevenLabs(KEY, fake([Response(302, {"location": "https://elsewhere.example/v1/music"}, b"")], calls), log)
    with pytest.raises(ElevenLabsError) as e:
        c.compose({"chunks": []})
    assert e.value.status == 302 and len(calls) == 1 and not log.exists()


def test_the_transport_does_not_follow_redirects():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from gitloom_film.elevenlabs import urllib_transport
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, self.headers.get("xi-api-key")))
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path == "/v1/music":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{srv.server_port}/collect")
                self.send_header("Content-Length", "0")
            else:
                self.send_response(200)
                self.send_header("Content-Length", "2")
            self.end_headers()
            if self.path != "/v1/music":
                self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = urllib_transport("POST", f"http://127.0.0.1:{srv.server_port}/v1/music", {"xi-api-key": KEY}, b"{}")
    finally:
        srv.shutdown()
        srv.server_close()
    assert r.status == 302 and r.headers["location"].endswith("/collect")
    assert seen == [("/v1/music", KEY)]  # the key went to the API host only; the redirect target never saw it


def test_sound_posts_the_request_and_logs_cost(tmp_path):
    calls, log = [], tmp_path / "credits.log"
    c = ElevenLabs(KEY, fake([Response(200, {"character-cost": "20", "request-id": "s1"}, b"\x01\x00" * 480)], calls), log)
    r = c.sound("a snap", duration_seconds=1.0, prompt_influence=0.4, seed=7)
    method, url, headers, body = calls[0]
    assert url == "https://api.elevenlabs.io/v1/sound-generation?output_format=pcm_48000"
    assert json.loads(body) == {"text": "a snap", "model_id": "eleven_text_to_sound_v2", "duration_seconds": 1.0,
                                "prompt_influence": 0.4, "loop": False, "seed": 7}
    assert (r.cost, r.request_id, r.output_format) == (20, "s1", "pcm_48000")
    assert r.audio == b"\x01\x00" * 480
    assert json.loads(log.read_text())["path"] == "/v1/sound-generation"


def test_sound_omits_unset_options():
    calls = []
    c = ElevenLabs(KEY, fake([Response(200, {}, b"\x00\x00")], calls))
    c.sound("hum", loop=True, output_format="pcm_44100")
    assert calls[0][1].endswith("?output_format=pcm_44100")
    assert json.loads(calls[0][3]) == {"text": "hum", "model_id": "eleven_text_to_sound_v2", "loop": True}


def test_sound_error_never_leaks_the_key():
    c = ElevenLabs(KEY, fake([Response(422, {}, f"bad {KEY}".encode())], []))
    with pytest.raises(ElevenLabsError) as e:
        c.sound("x")
    assert KEY not in str(e.value)


def test_credits_used_reads_the_subscription_with_a_get():
    calls = []
    body = json.dumps({"character_count": 1234, "character_limit": 40000}).encode()
    c = ElevenLabs(KEY, fake([Response(200, {}, body)], calls))
    assert c.credits_used() == 1234
    method, url, headers, sent = calls[0]
    assert (method, url, sent) == ("GET", "https://api.elevenlabs.io/v1/user/subscription", None)
