"""ElevenLabs client: text-to-speech with timestamps, music from a composition plan, and forced alignment.

The API key is read from ~/11labs. It is sent only in the xi-api-key header, only to the API host (redirects are
refused, never followed), and never appears in a repr, an exception, a log line or a file.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

BASE = "https://api.elevenlabs.io"
KEY_FILE = Path(os.path.expanduser("~/11labs"))


class ElevenLabsError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"ElevenLabs HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


Transport = Callable[[str, str, dict[str, str], "bytes | None"], Response]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib re-sends a request's headers, the xi-api-key among them, to wherever a 3xx points. Refuse instead: the
    3xx comes back as a Response with its own status, and the client raises on it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> Response:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=900) as r:
            return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, {k.lower(): v for k, v in e.headers.items()}, e.read())


def load_key(path: Path = KEY_FILE) -> str:
    key = path.read_text().strip()
    if not key:
        raise RuntimeError(f"empty ElevenLabs key file: {path}")
    return key


@dataclass
class TTSResult:
    audio: bytes  # raw PCM16 little-endian mono for pcm_* formats
    alignment: dict  # characters, character_start_times_seconds, character_end_times_seconds
    cost: int
    request_id: str


@dataclass
class MusicResult:
    audio: bytes
    output_format: str
    cost: int
    request_id: str


class ElevenLabs:
    def __init__(self, key: str | None = None, transport: Transport = urllib_transport,
                 credit_log: Path | None = None, sleep: Callable[[float], None] = time.sleep, base: str = BASE):
        self._key = key if key is not None else load_key()
        self._transport = transport
        self._log = credit_log
        self._sleep = sleep
        self._base = base

    def __repr__(self) -> str:
        return "ElevenLabs(key=<redacted>)"

    __str__ = __repr__

    def _scrub(self, s: str) -> str:
        return s.replace(self._key, "<redacted>")

    def _request(self, path: str, payload: dict, accept: str, params: dict) -> Response:
        return self._send(path, json.dumps(payload).encode(), "application/json", accept, params)

    def _send(self, path: str, body: bytes, content_type: str, accept: str, params: dict) -> Response:
        url = f"{self._base}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        headers = {"xi-api-key": self._key, "Accept": accept, "Content-Type": content_type}
        delay = 2.0
        for attempt in range(4):
            r = self._transport("POST", url, headers, body)
            if (r.status == 429 or r.status >= 500) and attempt < 3:
                self._sleep(delay)
                delay *= 2
                continue
            if not 200 <= r.status < 300:  # a redirect is not followed (see _NoRedirect), so it is an error too
                raise ElevenLabsError(r.status, self._scrub(r.body.decode(errors="replace")[:800]))
            self._log_cost(path, r)
            return r
        raise AssertionError("unreachable")

    def _log_cost(self, path: str, r: Response) -> None:
        if not self._log:
            return
        self._log.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "path": path,
               "cost": int(r.headers.get("character-cost", "0") or 0), "request_id": r.headers.get("request-id", "")}
        with self._log.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    def tts(self, voice_id: str, text: str, model_id: str = "eleven_v4", output_format: str = "pcm_48000",
            speed: float | None = None, seed: int | None = None) -> TTSResult:
        payload: dict = {"text": text, "model_id": model_id}
        if speed is not None:
            payload["voice_settings"] = {"speed": speed}
        if seed is not None:
            payload["seed"] = seed
        r = self._request(f"/v1/text-to-speech/{voice_id}/with-timestamps", payload, "application/json",
                          {"output_format": output_format})
        d = json.loads(r.body)
        return TTSResult(base64.b64decode(d["audio_base64"]), d.get("alignment") or {},
                         int(r.headers.get("character-cost", "0") or 0), r.headers.get("request-id", ""))

    def compose(self, composition_plan: dict, model_id: str = "music_v2_5", output_format: str = "pcm_48000",
                seed: int | None = None) -> MusicResult:
        payload: dict = {"composition_plan": composition_plan, "model_id": model_id}
        if seed is not None:
            payload["seed"] = seed
        r = self._request("/v1/music", payload, "*/*", {"output_format": output_format})
        return MusicResult(r.body, output_format, int(r.headers.get("character-cost", "0") or 0),
                           r.headers.get("request-id", ""))

    def forced_alignment(self, audio: bytes, text: str, filename: str = "take.wav") -> dict:
        """Word and character times measured on `audio` for the given transcript (1 credit per call)."""
        boundary = f"gitloomfilm{uuid.uuid4().hex}"
        body = b"".join([
            (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
             f"Content-Type: audio/wav\r\n\r\n").encode() + audio + b"\r\n",
            f'--{boundary}\r\nContent-Disposition: form-data; name="text"\r\n\r\n{text}\r\n'.encode(),
            f"--{boundary}--\r\n".encode(),
        ])
        r = self._send("/v1/forced-alignment", body, f"multipart/form-data; boundary={boundary}",
                       "application/json", {})
        return json.loads(r.body)
