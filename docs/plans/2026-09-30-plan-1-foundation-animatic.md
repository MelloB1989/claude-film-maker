# GitLoom launch film, Plan 1: foundation → animatic (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the approved script into timed audio (Jean's voiceover plus a score composed to the edit), then render a
full-length animatic from the forked engine in which every scene card, word highlight and cut lands on the voice and
the beat.

**Architecture:**
- A Python toolchain (`tools/`, uv, Python 3.12) owns all audio. It covers ElevenLabs takes, pacing, placement on a
  timeline, the composition plan, beat analysis, snapping and the mix, and writes `data/vo.json` and `data/audio.json`.
- A fork of the MIT PDoom-Video engine (`app/`, bun + Vite + three.js), re-skinned to GitLoom, reads those two files.
  Its timeline takes the scene windows from `data/vo.json`, and it renders an animatic card per scene.

**Tech stack:** Python 3.12 (uv), numpy, soundfile, librosa, fontTools, pytest; ffmpeg 9 and Rubber Band 4 (CLI);
bun, Vite 8, three.js 0.186, opentype.js 2, playwright-core (headless Chrome).

**Spec:** `docs/specs/2026-09-30-gitloom-launch-film-design.md`. Read §4 (script), §5 (sound), §7 (build) and §8
(process) before starting.

This is **Plan 1 of 4**:
- Plan 1 (this one): foundation → animatic, checkpoints C1–C3.
- Plan 2: look development → style frames (C4).
- Plan 3: full build → rough cut (C5).
- Plan 4: finals → deliverables (C6).

## Global Constraints

- **Repo root:** `~/Developer/code/gitloom-film`. All paths below are relative to it.
- **Python:** `>=3.12,<3.13`, managed by uv in `tools/`. Run tools as `cd tools && uv run <cmd>`.
- **Voice:** `eVItLK1UvXctxuaRV2Oq` ("Jean – Alluring and Playful Femme Fatale"), `model_id: eleven_v4`,
  `output_format: pcm_48000`. The audition showed Jean is slow; pace is tightened by about 10–12%, and never
  pitch-shifted.
- **Music:** `POST /v1/music` with a `composition_plan` (`positive_global_styles`, `negative_global_styles`,
  `sections[{section_name, positive_local_styles, negative_local_styles, duration_ms (3000–120000), lines}]`), with
  `model_id: music_v2_5`.
- **Secret:** the ElevenLabs key lives in `~/11labs`. It is read at runtime and **never** printed, logged, written to
  any file, committed, or included in an exception message.
- **Credits:** every API call appends `{ts, path, cost, request_id}` to `audio/credits.log`. Plan 1 budget: at most
  about 7,000 credits, of which voice ≈ 400 and music ≈ 5,500.
- **Audio format:** 48 kHz, float32 in memory, WAV `PCM_24` on disk.
- **Timing:** the film runs at 30 fps.
  - Word sync: an on-screen word is revealed within ±1 frame (33 ms) of its spoken start.
  - Cut sync: every cut is on a beat within ±1 frame, and every act start is on a downbeat.
  - Total duration: 85–95 s.
- **Loudness:** the mix is −14 LUFS integrated (±0.5), true peak ≤ −1.0 dBTP.
- **Palette** (from the spec, §6):

  | token | hex |
  |---|---|
  | ink | `#110d10` |
  | ink2 | `#161114` |
  | panel | `#1e181c` |
  | panel2 | `#282027` |
  | rule | `#2b2229` |
  | ruleStrong | `#3e323b` |
  | bone | `#ede7ea` |
  | boneDim | `#a99fa5` |
  | boneFaint | `#6f6469` |
  | blood | `#c22b45` |
  | bloodBright | `#dc4a63` |
  | bloodDim | `#8e1f35` |
  | moss | `#4aad63` |
  | mossDim | `#1c3324` |

  Blood is never a surface fill; moss is never decoration; only blood and moss may bloom.
- **Fonts** (all SIL OFL), pinned to google/fonts commit `9710da1eacb3be272583c3224dcb70f9da6eadbb`:
  - Bricolage Grotesque, with axes opsz 12–96, wght 200–800, wdth 75–100
  - JetBrains Mono (wght 100–800, plus an italic)
  - Geist (wght 100–900)
- **Engine source:** PDoom-Video at commit `bdbad537a7b7af3213475651774030c47568c181` (MIT, © 2026 Giacomo Magnanini).
  The copyright notice is kept.
- **Commits:** every commit message ends with a blank line and then
  `Co-Authored by MelloB's coding agent <build@mellob.in>`.

## Review Focus

These are the failure modes most likely to bite; each one's test lives in the task that owns the code.

1. **Punctuation-heavy lines** (`...I say so.`, `Forty-four...`, `It's`, `Go ahead. Blame me.`): every word still gets
   the start and end times of its letters. Tested in Task 3.
2. **An interrupted generation run** (network drop mid-batch): re-running skips finished takes, regenerates a
   half-written take, and never pays twice for the same take. Tested in Task 4.
3. **The music API refusing `pcm_48000`** (HTTP 403, plan tier): generation falls back to `mp3_44100_128`, decodes it,
   and still produces a 48 kHz stereo WAV. Tested in Task 8.
4. **Drumless stretches** (cold open, the honesty drop-out): the beat grid keeps going through silence instead of
   losing beats. Tested in Task 9.
5. **Cut snapping:** a snapped cut never lands after its scene's first word minus the lead, and never before the
   previous scene's last word. Tested in Task 10.

## File map

```
README.md                         what this repo is, how to run each stage
docs/CREDITS.md                   engine MIT notice, fonts OFL, voice/music credits
data/script.json                  acts, scenes, the 33 lines with take counts          (Task 4)
data/edit.json                    placement config: lead-in, gaps, overrides, tail      (Task 7)
data/vo.json                      generated: absolute line/word times, scenes, acts     (Task 7, snapped in Task 10)
data/music_plan.json              generated: the composition plan + section times       (Task 8)
data/audio.json                   generated: beat grid, sections, envelopes, onsets     (Task 9)
audio/vo/takes/<L>/<k>.{wav,json} raw takes (gitignored)                                (Task 4)
audio/vo/paced/<L>/<k>.{wav,json} trimmed + time-stretched takes                        (Task 5)
audio/vo/selects.json             chosen take (and optional factor) per line            (Task 6)
audio/vo/vo.wav                   assembled voiceover                                   (Task 7)
audio/music/<label>-seed<N>.wav   score variants                                        (Task 8)
audio/mix/mix.wav                 current mix (the animatic mix in Plan 1)              (Task 11)
fonts/src/                        pinned variable fonts + OFL texts                     (Task 12)
tools/pyproject.toml              uv project + console scripts
tools/gitloom_film/paths.py       repo-root-relative paths                              (Task 1)
tools/gitloom_film/elevenlabs.py  API client (TTS with timestamps, music)               (Task 2)
tools/gitloom_film/wav.py         PCM/WAV helpers                                       (Task 3)
tools/gitloom_film/align.py       char alignment → words                                (Task 3)
tools/gitloom_film/vo.py          take generation CLI                                   (Task 4)
tools/gitloom_film/pace.py        trim, rate, Rubber Band stretch CLI                   (Task 5)
tools/gitloom_film/audition.py    checkpoint listening pages CLI                        (Task 6)
tools/gitloom_film/edit.py        placement, scene/act spans, assembly CLI              (Task 7)
tools/gitloom_film/music_plan.py  composition plan builder                              (Task 8)
tools/gitloom_film/music.py       score generation CLI                                  (Task 8)
tools/gitloom_film/beats.py       beat grid + envelopes CLI                             (Task 9)
tools/gitloom_film/snap.py        nudge lines onto beats, cut on beats CLI              (Task 10)
tools/gitloom_film/mix.py         sidechain mix + loudness CLI                          (Task 11)
tools/gitloom_film/fonts.py       static font instances CLI                             (Task 12)
tools/gitloom_film/sync.py        sync report CLI                                       (Task 15)
tools/tests/test_*.py             one test module per tool module
app/                              engine fork (Tasks 13–15)
  src/engine/palette.ts vo.ts hud.ts type.ts util.ts engine.ts post.ts scene.ts glsl/common.ts (+ unchanged gl, lines, stroke, audio, scale)
  src/timeline.ts                 scene windows from data/vo.json                       (Task 14)
  src/scenes/card.ts              animatic card scene                                   (Task 14)
  src/engine/*.test.ts            bun tests                                             (Tasks 13–14)
  scripts/render.ts               stills / sheet / perf / video                         (Task 13)
out/                              renders, vendor checkout, pages (gitignored)
```

---

### Task 1: Repo scaffold and Python tools project

**Files:**
- Create: `README.md`, `docs/CREDITS.md`, `tools/pyproject.toml`, `tools/gitloom_film/__init__.py`,
  `tools/gitloom_film/paths.py`, `tools/tests/test_paths.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `gitloom_film.paths.ROOT`, `DATA`, `AUDIO`, `OUT`, `APP`, `FONTS` (all `pathlib.Path`), and
  `find_root(start: Path | None) -> Path`.

- [ ] **Step 1: Write the failing test**

`tools/tests/test_paths.py`:
```python
from pathlib import Path

import pytest

from gitloom_film import paths


def test_root_is_the_film_repo():
    assert (paths.ROOT / "docs" / "specs").is_dir()
    assert (paths.ROOT / "tools" / "pyproject.toml").is_file()


def test_named_dirs_hang_off_root():
    assert paths.DATA == paths.ROOT / "data"
    assert paths.AUDIO == paths.ROOT / "audio"
    assert paths.OUT == paths.ROOT / "out"
    assert paths.APP == paths.ROOT / "app"
    assert paths.FONTS == paths.ROOT / "fonts"


def test_find_root_rejects_outside_paths(tmp_path: Path):
    with pytest.raises(RuntimeError, match="not inside the gitloom-film repo"):
        paths.find_root(tmp_path)
```

- [ ] **Step 2: Create the project and run the test to see it fail**

`tools/pyproject.toml`:
```toml
[project]
name = "gitloom-film-tools"
version = "0.1.0"
description = "Audio, timing and font tools for the GitLoom launch film"
requires-python = ">=3.12,<3.13"
dependencies = [
  "numpy>=2.0",
  "soundfile>=0.12",
  "librosa>=0.10.2",
  "fonttools>=4.53",
]

[project.scripts]
film-vo = "gitloom_film.vo:main"
film-pace = "gitloom_film.pace:main"
film-audition = "gitloom_film.audition:main"
film-edit = "gitloom_film.edit:main"
film-music = "gitloom_film.music:main"
film-beats = "gitloom_film.beats:main"
film-snap = "gitloom_film.snap:main"
film-mix = "gitloom_film.mix:main"
film-fonts = "gitloom_film.fonts:main"
film-sync = "gitloom_film.sync:main"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["gitloom_film"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Run:
```bash
mkdir -p tools/gitloom_film tools/tests && touch tools/gitloom_film/__init__.py
cd tools && uv sync --python 3.12 && uv run pytest tests/test_paths.py -v
```
Expected: FAIL with `ImportError: cannot import name 'paths'`.

- [ ] **Step 3: Implement `paths.py`**

`tools/gitloom_film/paths.py`:
```python
"""Repo-relative paths. Every tool resolves files from the repo root, never from the working directory."""
from pathlib import Path


def find_root(start: Path | None = None) -> Path:
    p = (start or Path(__file__)).resolve()
    for d in [p, *p.parents]:
        if (d / "docs" / "specs").is_dir() and (d / "tools" / "pyproject.toml").is_file():
            return d
    raise RuntimeError(f"not inside the gitloom-film repo: {p}")


ROOT = find_root()
DATA = ROOT / "data"
AUDIO = ROOT / "audio"
OUT = ROOT / "out"
APP = ROOT / "app"
FONTS = ROOT / "fonts"
```

- [ ] **Step 4: Run the test to see it pass**

Run: `cd tools && uv run pytest tests/test_paths.py -v`
Expected: 3 passed.

- [ ] **Step 5: Write README, CREDITS and .gitignore, then commit**

`README.md`:
````markdown
# GitLoom launch film

*I Don't Forget. I Commit.* is a 90-second, code-rendered launch film for GitLoom.

- Design: `docs/specs/2026-09-30-gitloom-launch-film-design.md`
- Plans: `docs/plans/`

## Stages

| stage | command (from `tools/`) | writes |
|---|---|---|
| voice takes | `uv run film-vo` | `audio/vo/takes/` |
| pacing | `uv run film-pace` | `audio/vo/paced/` |
| listening pages | `uv run film-audition vo` / `music` | `out/auditions/*.html` |
| placement | `uv run film-edit` | `data/vo.json`, `audio/vo/vo.wav` |
| score | `uv run film-music` | `audio/music/`, `data/music_plan.json` |
| beat grid | `uv run film-beats --music <wav>` | `data/audio.json` |
| snapping | `uv run film-snap` | `data/vo.json`, `audio/vo/vo.wav` |
| mix | `uv run film-mix --music <wav>` | `audio/mix/mix.wav` |
| fonts | `uv run film-fonts` | `app/public/fonts/` |
| sync report | `uv run film-sync` | stdout, exit 1 on failure |

The engine lives in `app/` (`bun install`, `bunx vite`, `bun scripts/render.ts …`).

The ElevenLabs key is read from `~/11labs` at runtime and never stored in this repo.
````

`docs/CREDITS.md`:
```markdown
# Credits and licences

## Engine
`app/` is adapted from PDoom-Video (https://github.com/mexicat/PDoom-Video), commit
bdbad537a7b7af3213475651774030c47568c181, used under the MIT License:

> MIT License
>
> Copyright (c) 2026 Giacomo Magnanini
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
> documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
> rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
> persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
> Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
> WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
> COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
> OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

The single-stroke fonts in `app/public/fonts/stroke/` come with that engine: the EMS fonts from Evil Mad Scientist
Laboratories (SIL OFL) and the Hershey fonts (free use, with attribution to Dr. A. V. Hershey).

## Fonts
- Bricolage Grotesque, JetBrains Mono and Geist, all under the SIL Open Font License. The texts are in `fonts/src/`.
  Sources are pinned to google/fonts commit 9710da1eacb3be272583c3224dcb70f9da6eadbb.

## Voice, music and sound effects
- Voice: the ElevenLabs voice library voice "Jean – Alluring and Playful Femme Fatale" (eVItLK1UvXctxuaRV2Oq).
- Music and sound effects: generated with ElevenLabs.

## Brand
GitLoom mark and design tokens © GitLoom.
```

Append to `.gitignore`:
```
tools/.venv/
app/node_modules/
app/dist/
.pytest_cache/
__pycache__/
```

Run:
```bash
git add README.md docs/CREDITS.md .gitignore tools/pyproject.toml tools/uv.lock tools/gitloom_film/__init__.py tools/gitloom_film/paths.py tools/tests/test_paths.py
git commit -m "Scaffold the film repo and its Python tools project" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---

### Task 2: ElevenLabs client

**Files:**
- Create: `tools/gitloom_film/elevenlabs.py`, `tools/tests/test_elevenlabs.py`

**Interfaces:**
- Produces:
  - `ElevenLabs(key: str | None = None, transport: Transport = urllib_transport, credit_log: Path | None = None, sleep = time.sleep, base: str = BASE)`
  - `.tts(voice_id: str, text: str, model_id: str = "eleven_v4", output_format: str = "pcm_48000", speed: float | None = None, seed: int | None = None) -> TTSResult`
  - `.compose(composition_plan: dict, model_id: str = "music_v2_5", output_format: str = "pcm_48000", seed: int | None = None) -> MusicResult`
  - `TTSResult(audio: bytes, alignment: dict, cost: int, request_id: str)`
  - `MusicResult(audio: bytes, output_format: str, cost: int, request_id: str)`
  - `ElevenLabsError(status: int, detail: str)`
  - `Response(status: int, headers: dict[str, str], body: bytes)`
  - `Transport = Callable[[str, str, dict[str, str], bytes | None], Response]`

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_elevenlabs.py`:
```python
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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_elevenlabs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitloom_film.elevenlabs'`.

- [ ] **Step 3: Implement the client**

`tools/gitloom_film/elevenlabs.py`:
```python
"""ElevenLabs client: text-to-speech with timestamps, and music from a composition plan.

The API key is read from ~/11labs. It is sent only in the xi-api-key header and never appears in a repr, an
exception, a log line or a file.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
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


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> Response:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
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
        url = f"{self._base}{path}?{urllib.parse.urlencode(params)}"
        headers = {"xi-api-key": self._key, "Accept": accept, "Content-Type": "application/json"}
        body = json.dumps(payload).encode()
        delay = 2.0
        for attempt in range(4):
            r = self._transport("POST", url, headers, body)
            if (r.status == 429 or r.status >= 500) and attempt < 3:
                self._sleep(delay)
                delay *= 2
                continue
            if r.status >= 400:
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
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd tools && uv run pytest tests/test_elevenlabs.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/gitloom_film/elevenlabs.py tools/tests/test_elevenlabs.py
git commit -m "ElevenLabs client that retries, logs credits and never leaks the key" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---
### Task 3: WAV helpers and alignment → words

**Files:**
- Create: `tools/gitloom_film/wav.py`, `tools/gitloom_film/align.py`, `tools/tests/test_wav.py`, `tools/tests/test_align.py`

**Interfaces:**
- Produces:
  - `wav.SR = 48000`
  - `pcm16_to_float(b: bytes, channels: int = 1) -> np.ndarray` (shape `(n,)` or `(n, channels)`)
  - `write_wav(path: Path, samples: np.ndarray, sr: int = SR) -> None` (PCM_24)
  - `read_wav(path: Path, mono: bool = True) -> tuple[np.ndarray, int]`
  - `align.Word(w: str, start: float, end: float)`
  - `words_from_alignment(al: dict) -> list[Word]`
  - `words_to_dicts(words: list[Word]) -> list[dict]` (`{"w", "start", "end"}`, times rounded to 4 decimals)

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_wav.py`:
```python
import numpy as np

from gitloom_film.wav import SR, pcm16_to_float, read_wav, write_wav


def test_pcm16_to_float_scales():
    b = np.array([0, 16384, -32768, 32767], dtype="<i2").tobytes()
    assert np.allclose(pcm16_to_float(b), [0, 0.5, -1, 32767 / 32768])


def test_pcm16_stereo_deinterleaves():
    x = pcm16_to_float(np.array([1, -1, 2, -2], dtype="<i2").tobytes(), channels=2)
    assert x.shape == (2, 2) and x[1, 1] == -2 / 32768


def test_wav_roundtrip_24bit(tmp_path):
    x = (np.sin(np.linspace(0, 100, SR)) * 0.5).astype(np.float32)
    write_wav(tmp_path / "a.wav", x)
    y, sr = read_wav(tmp_path / "a.wav")
    assert sr == SR and np.max(np.abs(x - y)) < 1e-6


def test_read_wav_downmixes_unless_asked(tmp_path):
    st = (np.stack([np.ones(100), -np.ones(100) * 0.5], axis=1) * 0.5).astype(np.float32)
    write_wav(tmp_path / "s.wav", st)
    y, _ = read_wav(tmp_path / "s.wav")
    assert np.allclose(y, 0.125, atol=1e-6)
    z, _ = read_wav(tmp_path / "s.wav", mono=False)
    assert z.shape == (100, 2)
```

`tools/tests/test_align.py`:
```python
import pytest

from gitloom_film.align import words_from_alignment, words_to_dicts


def al(text, dt=0.1):
    starts = [i * dt for i in range(len(text))]
    return {"characters": list(text), "character_start_times_seconds": starts,
            "character_end_times_seconds": [s + dt for s in starts]}


def test_words_carry_punctuation_and_letter_times():
    ws = words_from_alignment(al("Every conversation... back to zero."))
    assert [w.w for w in ws] == ["Every", "conversation...", "back", "to", "zero."]
    assert ws[1].start == pytest.approx(0.6)  # 'c' is character 6
    assert ws[1].end == pytest.approx(1.8)  # its last letter 'n' is character 17


def test_leading_ellipsis_attaches_to_first_word():
    ws = words_from_alignment(al("...I say so."))
    assert ws[0].w == "...I" and ws[0].start == pytest.approx(0.3)


def test_hyphen_and_apostrophe_words():
    ws = words_from_alignment(al("It's Forty-four..."))
    assert [w.w for w in ws] == ["It's", "Forty-four..."]
    assert ws[1].start == pytest.approx(0.5) and ws[1].end == pytest.approx(1.5)


def test_detached_punctuation_joins_previous_word():
    ws = words_from_alignment(al("Go ahead ... Blame me."))
    assert [w.w for w in ws] == ["Go", "ahead...", "Blame", "me."]


def test_mismatched_arrays_raise():
    a = al("Hi.")
    a["character_end_times_seconds"].pop()
    with pytest.raises(ValueError, match="differ in length"):
        words_from_alignment(a)


def test_to_dicts_rounds():
    assert words_to_dicts(words_from_alignment(al("Hi."))) == [{"w": "Hi.", "start": 0.0, "end": 0.2}]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_wav.py tests/test_align.py -v`
Expected: FAIL with `ModuleNotFoundError` for `gitloom_film.wav` and `gitloom_film.align`.

- [ ] **Step 3: Implement both modules**

`tools/gitloom_film/wav.py`:
```python
"""PCM/WAV helpers. Audio is float32 in memory and 24-bit WAV on disk, at 48 kHz."""
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 48000


def pcm16_to_float(b: bytes, channels: int = 1) -> np.ndarray:
    x = np.frombuffer(b, dtype="<i2").astype(np.float32) / 32768.0
    return x.reshape(-1, channels) if channels > 1 else x


def write_wav(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(samples, dtype=np.float32), sr, subtype="PCM_24")


def read_wav(path: Path, mono: bool = True) -> tuple[np.ndarray, int]:
    x, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if mono and x.ndim == 2:
        x = x.mean(axis=1)
    return x, sr
```

`tools/gitloom_film/align.py`:
```python
"""Character-level TTS alignment → word timings.

A word's time is the span of its letters and digits; punctuation rides along in the display text. A token of
punctuation only (a detached "...") joins the word before it.
"""
from dataclasses import dataclass


@dataclass
class Word:
    w: str
    start: float
    end: float


def words_from_alignment(al: dict) -> list[Word]:
    chars = al["characters"]
    st = al["character_start_times_seconds"]
    en = al["character_end_times_seconds"]
    if not (len(chars) == len(st) == len(en)):
        raise ValueError("alignment arrays differ in length")
    words: list[Word] = []
    cur: list[int] = []

    def flush() -> None:
        if not cur:
            return
        token = "".join(chars[i] for i in cur)
        core = [i for i in cur if chars[i].isalnum()]
        if core:
            words.append(Word(token, float(st[core[0]]), float(en[core[-1]])))
        elif words:
            words[-1].w += token
        cur.clear()

    for i, ch in enumerate(chars):
        if ch.isspace():
            flush()
        else:
            cur.append(i)
    flush()
    return words


def words_to_dicts(words: list[Word]) -> list[dict]:
    return [{"w": w.w, "start": round(w.start, 4), "end": round(w.end, 4)} for w in words]
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd tools && uv run pytest tests/test_wav.py tests/test_align.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/gitloom_film/wav.py tools/gitloom_film/align.py tools/tests/test_wav.py tools/tests/test_align.py
git commit -m "Word timings from character alignment, and 24-bit WAV helpers" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---

### Task 4: The script, and generating Jean's takes

**Files:**
- Create: `data/script.json`, `tools/gitloom_film/vo.py`, `tools/tests/test_vo.py`

**Interfaces:**
- Consumes:
  - `ElevenLabs.tts(...) -> TTSResult` (Task 2)
  - `words_from_alignment`, `words_to_dicts` (Task 3)
  - `pcm16_to_float`, `write_wav`, `SR` (Task 3)
- Produces:
  - `VOICE_ID`, `MODEL_ID`
  - `load_script(path: Path = DATA / "script.json") -> dict` (keys `acts`, `lines`)
  - `take_paths(root: Path, line_id: str, k: int) -> tuple[Path, Path]`
  - `generate_takes(lines: list[dict], client, out_dir: Path, speed: float, only: set[str] | None = None, takes: int | None = None, log=print) -> int`
  - **Take JSON:**
    `{"line", "take", "text", "voice_id", "model_id", "speed", "sr", "duration", "cost", "request_id", "words": [{"w", "start", "end"}]}`

- [ ] **Step 1: Write `data/script.json`** (the spec's §4 lines, verbatim)

```json
{
  "acts": [
    {"id": "I", "name": "The Ex", "scenes": ["thread", "ex"]},
    {"id": "II", "name": "Her", "scenes": ["her", "repo"]},
    {"id": "III", "name": "The Tour", "scenes": ["loom", "diff", "cite", "braid", "merkle", "graph", "honest", "proof"]},
    {"id": "IV", "name": "Everywhere", "scenes": ["connect", "anywhere"]},
    {"id": "V", "name": "The Weave", "scenes": ["weave"]}
  ],
  "lines": [
    {"id": "L01", "scene": "thread", "text": "Your agent forgets.", "takes": 3},
    {"id": "L02", "scene": "thread", "text": "Every conversation... back to zero.", "takes": 3},
    {"id": "L03", "scene": "ex", "text": "It's not you... it's your vector store.", "takes": 3},
    {"id": "L04", "scene": "ex", "text": "It overwrites what it knew... and never tells you why.", "takes": 3},
    {"id": "L05", "scene": "ex", "text": "Commitment issues.", "takes": 4},
    {"id": "L06", "scene": "her", "text": "Not me.", "takes": 4},
    {"id": "L07", "scene": "her", "text": "Every memory... a commit.", "takes": 3},
    {"id": "L08", "scene": "her", "text": "Every fact... a blame.", "takes": 3},
    {"id": "L09", "scene": "repo", "text": "I'm just a git repo.", "takes": 3},
    {"id": "L10", "scene": "repo", "text": "You already know how to read me.", "takes": 3},
    {"id": "L11", "scene": "loom", "text": "Facts I keep.", "takes": 3},
    {"id": "L12", "scene": "loom", "text": "Incidents... I let go.", "takes": 3},
    {"id": "L13", "scene": "loom", "text": "Rules I never break.", "takes": 3},
    {"id": "L14", "scene": "loom", "text": "Skills, only when you need them.", "takes": 3},
    {"id": "L15", "scene": "diff", "text": "Change your mind?", "takes": 3},
    {"id": "L16", "scene": "diff", "text": "I'll change mine.", "takes": 3},
    {"id": "L17", "scene": "diff", "text": "We'll always have the diff.", "takes": 4},
    {"id": "L18", "scene": "cite", "text": "Ask me why I believe something... I'll show you the line.", "takes": 3},
    {"id": "L18b", "scene": "cite", "text": "Go ahead. Blame me.", "takes": 2, "optional": true},
    {"id": "L19", "scene": "braid", "text": "Your words. What you meant. How you'd ask... braided into one answer.", "takes": 3},
    {"id": "L20", "scene": "merkle", "text": "Fifty things changed? I only look at fifty.", "takes": 3},
    {"id": "L21", "scene": "graph", "text": "I connect the dots... and I learn your language.", "takes": 3},
    {"id": "L22", "scene": "honest", "text": "And when I don't know...", "takes": 3},
    {"id": "L23", "scene": "honest", "text": "...I say so.", "takes": 4},
    {"id": "L24", "scene": "proof", "text": "Forty-four... to ninety-one point four.", "takes": 3},
    {"id": "L25", "scene": "proof", "text": "Not bad... for a memory.", "takes": 4},
    {"id": "L26", "scene": "connect", "text": "One command... and I'm in Claude Code.", "takes": 3},
    {"id": "L27", "scene": "connect", "text": "Or any agent, in any language.", "takes": 3},
    {"id": "L28", "scene": "anywhere", "text": "On your machine... or in my cloud.", "takes": 3},
    {"id": "L29", "scene": "anywhere", "text": "One memory for every user you have.", "takes": 3},
    {"id": "L30", "scene": "weave", "text": "GitLoom.", "takes": 4},
    {"id": "L31", "scene": "weave", "text": "I don't forget.", "takes": 4},
    {"id": "L32", "scene": "weave", "text": "I commit.", "takes": 4}
  ]
}
```

- [ ] **Step 2: Write the failing tests**

`tools/tests/test_vo.py`:
```python
import json

import numpy as np
import pytest

from gitloom_film.elevenlabs import TTSResult
from gitloom_film.vo import generate_takes, load_script

QUIET = {"log": lambda *_: None}


class FakeClient:
    def __init__(self):
        self.calls = []

    def tts(self, voice_id, text, model_id, output_format, speed=None, seed=None):
        self.calls.append((voice_id, text, model_id, output_format, speed))
        n = len(text)
        al = {"characters": list(text), "character_start_times_seconds": [i * 0.05 for i in range(n)],
              "character_end_times_seconds": [(i + 1) * 0.05 for i in range(n)]}
        return TTSResult(np.zeros(4800, dtype="<i2").tobytes(), al, 2, "rid")


LINES = [{"id": "L01", "scene": "thread", "text": "Your agent forgets.", "takes": 2},
         {"id": "L02", "scene": "thread", "text": "Hi.", "takes": 1}]


def test_generates_takes_with_metadata(tmp_path):
    c = FakeClient()
    assert generate_takes(LINES, c, tmp_path, 1.12, **QUIET) == 3
    meta = json.loads((tmp_path / "L01" / "1.json").read_text())
    assert [w["w"] for w in meta["words"]] == ["Your", "agent", "forgets."]
    assert meta["duration"] == pytest.approx(0.1) and meta["speed"] == 1.12 and meta["cost"] == 2
    assert c.calls[0] == ("eVItLK1UvXctxuaRV2Oq", "Your agent forgets.", "eleven_v4", "pcm_48000", 1.12)


def test_rerun_never_pays_twice(tmp_path):
    c = FakeClient()
    generate_takes(LINES, c, tmp_path, 1.12, **QUIET)
    assert generate_takes(LINES, c, tmp_path, 1.12, **QUIET) == 0
    assert len(c.calls) == 3


def test_half_written_take_is_regenerated(tmp_path):
    (tmp_path / "L02").mkdir(parents=True)
    (tmp_path / "L02" / "1.wav").write_bytes(b"partial")  # WAV without its JSON: an interrupted run
    c = FakeClient()
    assert generate_takes(LINES[1:], c, tmp_path, 1.12, **QUIET) == 1
    assert json.loads((tmp_path / "L02" / "1.json").read_text())["take"] == 1


def test_only_and_takes_override(tmp_path):
    c = FakeClient()
    assert generate_takes(LINES, c, tmp_path, 1.0, only={"L02"}, takes=3, **QUIET) == 3
    assert {p.name for p in (tmp_path / "L02").iterdir()} == {"1.wav", "1.json", "2.wav", "2.json", "3.wav", "3.json"}
    assert not (tmp_path / "L01").exists()


def test_script_matches_the_spec():
    s = load_script()
    ids = [l["id"] for l in s["lines"]]
    assert len(ids) == 33 and ids[0] == "L01" and ids[-1] == "L32" and "L18b" in ids
    scenes = [sc for a in s["acts"] for sc in a["scenes"]]
    assert scenes == ["thread", "ex", "her", "repo", "loom", "diff", "cite", "braid", "merkle", "graph",
                      "honest", "proof", "connect", "anywhere", "weave"]
    assert all(l["scene"] in scenes for l in s["lines"])
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_vo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitloom_film.vo'`.

- [ ] **Step 4: Implement `vo.py`**

`tools/gitloom_film/vo.py`:
```python
"""Generate voiceover takes: one WAV + JSON per (line, take). Idempotent: a take whose WAV and JSON both exist is
skipped, so an interrupted run resumes without paying twice."""
import argparse
import json
from pathlib import Path

from .align import words_from_alignment, words_to_dicts
from .elevenlabs import ElevenLabs
from .paths import AUDIO, DATA
from .wav import SR, pcm16_to_float, write_wav

VOICE_ID = "eVItLK1UvXctxuaRV2Oq"  # Jean – Alluring and Playful Femme Fatale
MODEL_ID = "eleven_v4"


def load_script(path: Path = DATA / "script.json") -> dict:
    return json.loads(path.read_text())


def take_paths(root: Path, line_id: str, k: int) -> tuple[Path, Path]:
    return root / line_id / f"{k}.wav", root / line_id / f"{k}.json"


def generate_takes(lines, client, out_dir: Path, speed: float, only: set[str] | None = None,
                   takes: int | None = None, log=print) -> int:
    made = 0
    for line in lines:
        if only and line["id"] not in only:
            continue
        for k in range(1, (takes or line.get("takes", 2)) + 1):
            wav, meta = take_paths(out_dir, line["id"], k)
            if wav.exists() and meta.exists():
                continue
            r = client.tts(VOICE_ID, line["text"], MODEL_ID, "pcm_48000", speed=speed)
            x = pcm16_to_float(r.audio)
            write_wav(wav, x, SR)
            meta.write_text(json.dumps({
                "line": line["id"], "take": k, "text": line["text"], "voice_id": VOICE_ID, "model_id": MODEL_ID,
                "speed": speed, "sr": SR, "duration": round(len(x) / SR, 4), "cost": r.cost,
                "request_id": r.request_id, "words": words_to_dicts(words_from_alignment(r.alignment)),
            }, indent=1))
            made += 1
            log(f"{line['id']} take {k}: {len(x) / SR:.2f}s, {r.cost} credits")
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate voiceover takes (Jean, Eleven v4)")
    ap.add_argument("--only", help="comma-separated line ids")
    ap.add_argument("--takes", type=int, help="takes per line (default: script.json)")
    ap.add_argument("--speed", type=float, default=1.12)
    a = ap.parse_args(argv)
    client = ElevenLabs(credit_log=AUDIO / "credits.log")
    n = generate_takes(load_script()["lines"], client, AUDIO / "vo" / "takes", a.speed,
                       set(a.only.split(",")) if a.only else None, a.takes)
    print(f"{n} new takes")
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd tools && uv run pytest tests/test_vo.py -v`
Expected: 5 passed.

- [ ] **Step 6: Generate the real takes** (spends about 350 credits)

Run: `cd tools && uv run film-vo`

Expected: 106 lines of `Lxx take k: …s, … credits`, ending with `106 new takes`. Then:

`tail -n 106 ../audio/credits.log | python3 -c "import sys,json; print(sum(json.loads(l)['cost'] for l in sys.stdin))"`

This should print a total under 600. If a run dies part-way, re-run the same command: finished takes are skipped.

- [ ] **Step 7: Commit** (takes stay gitignored)

```bash
git add data/script.json tools/gitloom_film/vo.py tools/tests/test_vo.py audio/credits.log
git commit -m "The script as data, and Jean's takes generated line by line" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---

### Task 5: Pacing: trim, measure, stretch

**Files:**
- Create: `tools/gitloom_film/pace.py`, `tools/tests/test_pace.py`

**Interfaces:**
- Consumes: the take JSON (Task 4), `read_wav` and `write_wav` (Task 3).
- Produces:
  - `MIN_FACTOR = 0.85`, `MAX_FACTOR = 1.0`
  - `trim(samples, sr, words, pad=0.04) -> (np.ndarray, list[dict])`
  - `speech_rate(words) -> float` (words per second, from the first word's start to the last word's end)
  - `factor_for(words, target_wps) -> float` (clamped)
  - `stretch(samples, sr, factor, rubberband="rubberband") -> np.ndarray`
  - `pace_take(take_wav: Path, take_json: Path, out_dir: Path, factor: float) -> dict` (writes
    `out_dir/<k>.wav|json`; the JSON gains `"factor"`, and the words are relative to the trimmed, stretched audio)
  - `load_selects(path: Path) -> dict`

- [ ] **Step 1: Install Rubber Band and confirm its flags**

Run:
```bash
brew install rubberband && rubberband --help 2>&1 | grep -E -- "-3|--fine|--time|-q"
```
Expected: lines for `-3, --fine`, `-t<X>, --time <X>` and `-q, --quiet`. If `-3` is missing, change the flag in Step 4 to
`--fine` (R3 is the higher-quality engine, and a pure time-stretch keeps pitch and timbre).

- [ ] **Step 2: Write the failing tests**

`tools/tests/test_pace.py`:
```python
import json
import shutil

import numpy as np
import pytest

from gitloom_film.pace import MAX_FACTOR, MIN_FACTOR, factor_for, pace_take, speech_rate, stretch, trim
from gitloom_film.wav import SR, read_wav, write_wav

needs_rb = pytest.mark.skipif(not shutil.which("rubberband"), reason="brew install rubberband")


def tone(sec, f=220.0, sr=SR):
    t = np.arange(int(sec * sr)) / sr
    return (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32)


def test_trim_cuts_silence_and_shifts_words():
    x = np.concatenate([np.zeros(SR // 2, np.float32), tone(1.0), np.zeros(SR // 2, np.float32)])
    words = [{"w": "a", "start": 0.5, "end": 0.9}, {"w": "b.", "start": 1.0, "end": 1.5}]
    y, w = trim(x, SR, words)
    assert len(y) / SR == pytest.approx(0.04 + 1.0 + 0.08, abs=1e-3)
    assert w[0]["start"] == pytest.approx(0.04) and w[1]["end"] == pytest.approx(1.04)
    assert abs(y[0]) < 1e-6  # faded in, never clicks


def test_rate_and_clamped_factor():
    words = [{"w": str(i), "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(5)]  # 5 words over 2.4 s
    assert speech_rate(words) == pytest.approx(5 / 2.4)
    assert factor_for(words, target_wps=5 / 2.4 / 0.9) == pytest.approx(0.9)
    assert factor_for(words, target_wps=100) == MIN_FACTOR
    assert factor_for(words, target_wps=0.5) == MAX_FACTOR


@needs_rb
def test_stretch_keeps_pitch_and_scales_length():
    y = stretch(tone(1.0, 440.0), SR, 0.9)
    assert len(y) / SR == pytest.approx(0.9, rel=0.01)
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    assert np.fft.rfftfreq(len(y), 1 / SR)[np.argmax(spec)] == pytest.approx(440.0, abs=3.0)


def test_stretch_factor_one_is_a_copy():
    x = tone(0.2)
    assert np.array_equal(stretch(x, SR, 1.0), x)


@needs_rb
def test_pace_take_writes_scaled_words(tmp_path):
    x = np.concatenate([np.zeros(SR // 4, np.float32), tone(1.0)])
    write_wav(tmp_path / "1.wav", x)
    (tmp_path / "1.json").write_text(json.dumps({"line": "L01", "take": 1, "duration": 1.25,
                                                 "words": [{"w": "hey.", "start": 0.25, "end": 1.25}]}))
    out = pace_take(tmp_path / "1.wav", tmp_path / "1.json", tmp_path / "paced", 0.9)
    y, _ = read_wav(tmp_path / "paced" / "1.wav")
    assert out["factor"] == 0.9
    assert out["words"][0]["start"] == pytest.approx(0.04 * 0.9, abs=1e-3)
    assert out["duration"] == pytest.approx(len(y) / SR, abs=1e-3)
    assert json.loads((tmp_path / "paced" / "1.json").read_text())["factor"] == 0.9
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_pace.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitloom_film.pace'`.

- [ ] **Step 4: Implement `pace.py`**

`tools/gitloom_film/pace.py`:
```python
"""Pace a take: cut the silence around the words, then time-stretch with Rubber Band's R3 engine (pitch and timbre
are kept; nothing is pitch-shifted). Jean runs slow, so the default tightens by 10%."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .paths import AUDIO
from .wav import read_wav, write_wav

MIN_FACTOR, MAX_FACTOR = 0.85, 1.0  # never slow her down, never squeeze more than 15%
DEFAULT_FACTOR = 0.9


def trim(samples: np.ndarray, sr: int, words: list[dict], pad: float = 0.04):
    a = max(0.0, words[0]["start"] - pad)
    b = min(len(samples) / sr, words[-1]["end"] + 2 * pad)
    out = samples[int(round(a * sr)):int(round(b * sr))].copy()
    f = int(0.005 * sr)
    if len(out) > 2 * f:
        ramp = np.linspace(0.0, 1.0, f, dtype=np.float32)
        out[:f] *= ramp
        out[-f:] *= ramp[::-1]
    return out, [{**w, "start": w["start"] - a, "end": w["end"] - a} for w in words]


def speech_rate(words: list[dict]) -> float:
    span = words[-1]["end"] - words[0]["start"]
    return len(words) / span if span > 0 else 0.0


def factor_for(words: list[dict], target_wps: float) -> float:
    r = speech_rate(words)
    return 1.0 if r <= 0 else float(np.clip(r / target_wps, MIN_FACTOR, MAX_FACTOR))


def stretch(samples: np.ndarray, sr: int, factor: float, rubberband: str = "rubberband") -> np.ndarray:
    if abs(factor - 1.0) < 1e-4:
        return samples.copy()
    if not shutil.which(rubberband):
        raise RuntimeError("rubberband not found: brew install rubberband")
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "in.wav", Path(td) / "out.wav"
        write_wav(src, samples, sr)
        subprocess.run([rubberband, "-q", "-3", "-t", f"{factor:.6f}", str(src), str(dst)], check=True)
        out, _ = read_wav(dst)
    return out


def pace_take(take_wav: Path, take_json: Path, out_dir: Path, factor: float) -> dict:
    meta = json.loads(take_json.read_text())
    x, sr = read_wav(take_wav)
    x, words = trim(x, sr, meta["words"])
    y = stretch(x, sr, factor)
    words = [{**w, "start": round(w["start"] * factor, 4), "end": round(w["end"] * factor, 4)} for w in words]
    out = {**meta, "factor": factor, "duration": round(len(y) / sr, 4), "words": words}
    write_wav(out_dir / take_wav.name, y, sr)
    (out_dir / take_json.name).write_text(json.dumps(out, indent=1))
    return out


def load_selects(path: Path = AUDIO / "vo" / "selects.json") -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Trim and time-stretch voiceover takes")
    ap.add_argument("--only", help="comma-separated line ids")
    ap.add_argument("--factor", type=float, default=DEFAULT_FACTOR, help="duration multiplier (0.9 = 10%% faster)")
    ap.add_argument("--target-wps", type=float, help="pick each take's factor from a target speech rate instead")
    a = ap.parse_args(argv)
    selects = load_selects()
    only = set(a.only.split(",")) if a.only else None
    takes_root, paced_root = AUDIO / "vo" / "takes", AUDIO / "vo" / "paced"
    n = 0
    for tj in sorted(takes_root.glob("*/*.json")):
        line = tj.parent.name
        if only and line not in only:
            continue
        meta = json.loads(tj.read_text())
        k = selects.get(line, {}).get("factor")
        if k is None:
            k = factor_for(meta["words"], a.target_wps) if a.target_wps else a.factor
        out = pace_take(tj.with_suffix(".wav"), tj, paced_root / line, float(np.clip(k, MIN_FACTOR, MAX_FACTOR)))
        n += 1
        print(f"{line} take {out['take']}: ×{out['factor']:.2f} → {out['duration']:.2f}s")
    print(f"{n} takes paced")
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd tools && uv run pytest tests/test_pace.py -v`
Expected: 5 passed.

- [ ] **Step 6: Pace the real takes**

Run: `cd tools && uv run film-pace`
Expected: 106 lines of `Lxx take k: ×0.90 → …s`, ending with `106 takes paced`.

- [ ] **Step 7: Commit**

```bash
git add tools/gitloom_film/pace.py tools/tests/test_pace.py
git commit -m "Takes are trimmed and tightened 10% with Rubber Band R3, pitch untouched" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---

### Task 6: Listening pages, and checkpoint C1

**Files:**
- Create: `tools/gitloom_film/audition.py`, `tools/tests/test_audition.py`, `audio/vo/selects.json`

**Interfaces:**
- Consumes: paced take JSON (Task 5), `load_selects` (Task 5), `load_script` (Task 4).
- Produces:
  - `vo_page(script: dict, paced_dir: Path, selects: dict, out: Path) -> Path`
  - `music_page(variants: list[Path], out: Path, sections: list[dict] | None = None) -> Path`
  - CLI `film-audition vo|music`, which writes `out/auditions/{vo,music}.html` and opens it

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_audition.py`:
```python
import json
import re

from gitloom_film.audition import music_page, vo_page


def make_take(root, line, k, dur=1.0, factor=0.9):
    d = root / line
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{k}.wav").write_bytes(b"RIFF")
    (d / f"{k}.json").write_text(json.dumps({"line": line, "take": k, "duration": dur, "factor": factor}))


def test_vo_page_lists_every_line_and_links_real_files(tmp_path):
    paced = tmp_path / "audio" / "vo" / "paced"
    make_take(paced, "L01", 1)
    make_take(paced, "L01", 2)
    make_take(paced, "L02", 1)
    script = {"lines": [{"id": "L01", "text": "Your agent forgets."}, {"id": "L02", "text": "It's <you>."}]}
    out = vo_page(script, paced, {"L01": {"take": 2}}, tmp_path / "out" / "vo.html")
    html = out.read_text()
    assert "L01" in html and "L02" in html and "It&#x27;s &lt;you&gt;." in html
    srcs = re.findall(r'src="([^"]+)"', html)
    assert len(srcs) == 3 and all((out.parent / s).resolve().exists() for s in srcs)
    assert '<div class="take chosen"><span>take 2' in html  # L01's pick
    assert html.count('class="take chosen"') == 2  # L02 has no pick, so it falls back to take 1


def test_music_page_links_variants(tmp_path):
    v = tmp_path / "audio" / "music" / "score-seed1.wav"
    v.parent.mkdir(parents=True)
    v.write_bytes(b"RIFF")
    out = music_page([v], tmp_path / "out" / "music.html", [{"name": "cold open", "start": 0.0, "end": 7.2}])
    html = out.read_text()
    assert "score-seed1" in html and "cold open" in html
    assert all((out.parent / s).resolve().exists() for s in re.findall(r'src="([^"]+)"', html))
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_audition.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitloom_film.audition'`.

- [ ] **Step 3: Implement `audition.py`**

`tools/gitloom_film/audition.py`:
```python
"""Local listening pages for the checkpoints: C1 (voice takes) and C2 (score variants)."""
import argparse
import html
import json
import os
import webbrowser
from pathlib import Path

from .paths import AUDIO, DATA, OUT

STYLE = """
:root { --ink:#110d10; --panel:#1e181c; --rule:#2b2229; --bone:#ede7ea; --dim:#a99fa5; --faint:#6f6469;
        --blood:#c22b45; --moss:#4aad63; }
* { box-sizing: border-box; }
body { margin:0; background:var(--ink); color:var(--bone); font:15px/1.5 ui-sans-serif,system-ui,sans-serif; padding:40px 16px 80px; }
main { max-width:860px; margin:0 auto; }
h1 { font-size:30px; letter-spacing:-.02em; margin:0 0 20px; }
ol { list-style:none; padding:0; margin:0; display:grid; gap:10px; }
li { background:var(--panel); border:1px solid var(--rule); border-radius:14px; padding:14px 16px; }
.id { font:600 12px ui-monospace,Menlo,monospace; color:var(--blood); }
.text { margin:2px 0 8px; }
.take { display:grid; grid-template-columns:190px 1fr; align-items:center; gap:10px; font:12px ui-monospace,Menlo,monospace; color:var(--faint); }
.take.chosen span { color:var(--moss); }
audio { width:100%; height:32px; }
.sec { font:12px ui-monospace,Menlo,monospace; color:var(--dim); }
"""
PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width, initial-scale=1"><title>{title}</title><style>{style}</style></head>'
        '<body><main><h1>{title}</h1>{body}</main></body></html>')


def _rel(p: Path, page: Path) -> str:
    return html.escape(os.path.relpath(p.resolve(), page.parent.resolve()))


def vo_page(script: dict, paced_dir: Path, selects: dict, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for line in script["lines"]:
        chosen = selects.get(line["id"], {}).get("take", 1)
        items = []
        for tj in sorted((paced_dir / line["id"]).glob("*.json"), key=lambda p: int(p.stem)):
            m = json.loads(tj.read_text())
            cls = "take chosen" if m["take"] == chosen else "take"
            label = f'take {m["take"]} · {m["duration"]:.2f}s · ×{m.get("factor", 1.0):.2f}'
            items.append(f'<div class="{cls}"><span>{label}</span>'
                         f'<audio controls preload="none" src="{_rel(tj.with_suffix(".wav"), out)}"></audio></div>')
        rows.append(f'<li><div class="id">{line["id"]}</div><div class="text">{html.escape(line["text"])}</div>'
                    f'{"".join(items)}</li>')
    out.write_text(PAGE.format(title="Voice takes: Jean", style=STYLE, body="<ol>" + "".join(rows) + "</ol>"))
    return out


def music_page(variants: list[Path], out: Path, sections: list[dict] | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    secs = " · ".join(f'{html.escape(s["name"])} {s["start"]:.1f}s' for s in (sections or []))
    rows = [f'<li><div class="id">{html.escape(v.stem)}</div><div class="sec">{secs}</div>'
            f'<audio controls preload="none" src="{_rel(v, out)}"></audio></li>' for v in variants]
    out.write_text(PAGE.format(title="Score variants", style=STYLE, body="<ol>" + "".join(rows) + "</ol>"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build and open a listening page")
    ap.add_argument("what", choices=["vo", "music"])
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    if a.what == "vo":
        from .pace import load_selects
        from .vo import load_script
        page = vo_page(load_script(), AUDIO / "vo" / "paced", load_selects(), OUT / "auditions" / "vo.html")
    else:
        plan = json.loads((DATA / "music_plan.json").read_text()) if (DATA / "music_plan.json").exists() else {}
        page = music_page(sorted((AUDIO / "music").glob("*.wav")), OUT / "auditions" / "music.html",
                          plan.get("meta", {}).get("sections"))
    print(page)
    if not a.no_open:
        webbrowser.open(page.as_uri())
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd tools && uv run pytest tests/test_audition.py -v`
Expected: 2 passed.

- [ ] **Step 5: Seed `selects.json`, open the page, and commit**

`audio/vo/selects.json`:
```json
{}
```
Run:
```bash
cd tools && uv run film-audition vo
git add tools/gitloom_film/audition.py tools/tests/test_audition.py audio/vo/selects.json
git commit -m "Listening pages for the voice and score checkpoints" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

- [ ] **Step 6: CHECKPOINT C1: stop and ask the user**

The user listens on `out/auditions/vo.html` and names, per line, the take they want, plus any pace changes (for
example "L05 take 3, a bit slower" means `{"take": 3, "factor": 0.95}`).
- Write their answer into `audio/vo/selects.json`.
- For each line with a factor, re-run `uv run film-pace --only <ids>`.
- For any line they want re-worded or re-read, edit `data/script.json`, delete that line's folders in
  `audio/vo/takes/` and `audio/vo/paced/`, then re-run `film-vo --only <id>` and `film-pace --only <id>`.

Commit `selects.json` with the message `Voice takes picked at C1`. **Do not start Task 7 until the user has answered.**

---

### Task 7: Placement on the timeline, and assembling the voiceover

**Files:**
- Create: `data/edit.json`, `tools/gitloom_film/edit.py`, `tools/tests/test_edit.py`

**Interfaces:**
- Consumes: paced take JSON (Task 5), `load_selects` (Task 5), `load_script` (Task 4), `read_wav`/`write_wav`/`SR`
  (Task 3).
- Produces:
  - `load_takes(script, paced_dir, selects) -> dict[str, dict]`
  - `place(script, takes, cfg) -> dict`
  - `assemble(vo, paced_dir, sr=SR) -> np.ndarray`
  - **`data/vo.json`:**
    ```
    {"duration": float,
     "lines":  [{"id", "scene", "act", "text", "start", "end", "take", "factor", "words": [{"w", "start", "end"}]}],
     "scenes": [{"id", "act", "start", "end"}],
     "acts":   [{"id", "name", "start", "end"}]}
    ```
    All times are absolute seconds. Scenes and acts tile `[0, duration)`.

- [ ] **Step 1: Write the placement config**

`data/edit.json`:
```json
{
  "lead_in": 0.9,
  "tail": 3.0,
  "gap": {"line": 0.45, "scene": 0.75, "act": 1.25},
  "scene_lead": 0.35,
  "overrides": {
    "L23": {"gap_before": 1.4},
    "L24": {"gap_before": 1.2},
    "L31": {"gap_before": 0.7},
    "L32": {"gap_before": 0.6}
  },
  "optional": {"L18b": false}
}
```

(These give the honesty beat its silence before "…I say so", give the proof slam a breath, and let the tagline land
word by word.)

- [ ] **Step 2: Write the failing tests**

`tools/tests/test_edit.py`:
```python
import numpy as np
import pytest

from gitloom_film.edit import assemble, place
from gitloom_film.wav import SR, write_wav

SCRIPT = {"acts": [{"id": "I", "name": "A", "scenes": ["s1", "s2"]}, {"id": "II", "name": "B", "scenes": ["s3"]}],
          "lines": [{"id": "L1", "scene": "s1", "text": "a b"}, {"id": "L2", "scene": "s1", "text": "c"},
                    {"id": "L3", "scene": "s2", "text": "d"},
                    {"id": "L3b", "scene": "s2", "text": "x", "optional": True},
                    {"id": "L4", "scene": "s3", "text": "e"}]}


def take(dur, words):
    return {"take": 1, "factor": 0.9, "duration": dur, "words": words}


TAKES = {"L1": take(1.0, [{"w": "a", "start": 0.04, "end": 0.4}, {"w": "b", "start": 0.5, "end": 0.9}]),
         "L2": take(0.5, [{"w": "c", "start": 0.04, "end": 0.4}]),
         "L3": take(0.5, [{"w": "d", "start": 0.04, "end": 0.4}]),
         "L3b": take(0.5, [{"w": "x", "start": 0.04, "end": 0.4}]),
         "L4": take(0.5, [{"w": "e", "start": 0.04, "end": 0.4}])}
CFG = {"lead_in": 1.0, "tail": 2.0, "gap": {"line": 0.5, "scene": 1.0, "act": 2.0}, "scene_lead": 0.3,
       "overrides": {"L4": {"gap_before": 3.0}}, "optional": {"L3b": False}}


def test_place_applies_gaps_and_overrides():
    vo = place(SCRIPT, TAKES, CFG)
    assert {l["id"]: l["start"] for l in vo["lines"]} == {"L1": 1.0, "L2": 2.5, "L3": 4.0, "L4": 7.5}
    assert vo["duration"] == 10.0
    l1 = vo["lines"][0]
    assert l1["words"][1] == {"w": "b", "start": 1.5, "end": 1.9}
    assert (l1["act"], l1["take"], l1["factor"]) == ("I", 1, 0.9)


def test_optional_line_included_when_enabled():
    vo = place(SCRIPT, TAKES, {**CFG, "optional": {"L3b": True}})
    assert [l["id"] for l in vo["lines"]] == ["L1", "L2", "L3", "L3b", "L4"]


def test_scene_and_act_spans_tile_the_film():
    vo = place(SCRIPT, TAKES, CFG)
    sc = vo["scenes"]
    assert [s["id"] for s in sc] == ["s1", "s2", "s3"]
    assert sc[0]["start"] == 0.0 and sc[-1]["end"] == 10.0
    assert all(a["end"] == b["start"] for a, b in zip(sc, sc[1:]))
    assert sc[1]["start"] == pytest.approx(3.74)  # 0.3 s before its first word (4.04), after s1's last word + 0.1
    assert vo["acts"] == [{"id": "I", "name": "A", "start": 0.0, "end": sc[2]["start"]},
                          {"id": "II", "name": "B", "start": sc[2]["start"], "end": 10.0}]


def test_missing_take_names_the_line():
    with pytest.raises(KeyError, match="L2"):
        place(SCRIPT, {k: v for k, v in TAKES.items() if k != "L2"}, CFG)


def test_assemble_places_audio_at_line_starts(tmp_path):
    for lid, t in TAKES.items():
        x = np.zeros(int(t["duration"] * SR), np.float32)
        x[0] = 0.9
        write_wav(tmp_path / lid / "1.wav", x)
    vo = place(SCRIPT, TAKES, CFG)
    y = assemble(vo, tmp_path)
    assert len(y) >= int(10.0 * SR)
    assert list(np.round(np.flatnonzero(y > 0.5) / SR, 3)) == [1.0, 2.5, 4.0, 7.5]
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_edit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitloom_film.edit'`.

- [ ] **Step 4: Implement `edit.py`**

`tools/gitloom_film/edit.py`:
```python
"""Place the chosen takes on the film timeline, derive scene and act windows, and assemble the voiceover.

Gaps come from data/edit.json: line / scene / act gaps by boundary type, with per-line overrides. A scene starts
`scene_lead` seconds before its first word, but never before the previous scene's last word has ended.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from .pace import load_selects
from .paths import AUDIO, DATA
from .vo import load_script
from .wav import SR, read_wav, write_wav


def load_takes(script: dict, paced_dir: Path, selects: dict) -> dict[str, dict]:
    out = {}
    for line in script["lines"]:
        k = selects.get(line["id"], {}).get("take", 1)
        p = paced_dir / line["id"] / f"{k}.json"
        if p.exists():
            out[line["id"]] = json.loads(p.read_text())
    return out


def _act_of(script: dict) -> dict[str, str]:
    return {s: a["id"] for a in script["acts"] for s in a["scenes"]}


def place(script: dict, takes: dict[str, dict], cfg: dict) -> dict:
    act_of = _act_of(script)
    t, prev, lines = cfg["lead_in"], None, []
    for line in script["lines"]:
        if line.get("optional") and not cfg.get("optional", {}).get(line["id"], False):
            continue
        if line["id"] not in takes:
            raise KeyError(f"no paced take for {line['id']}")
        tk = takes[line["id"]]
        if prev is None:
            gap = 0.0
        elif act_of[line["scene"]] != act_of[prev["scene"]]:
            gap = cfg["gap"]["act"]
        elif line["scene"] != prev["scene"]:
            gap = cfg["gap"]["scene"]
        else:
            gap = cfg["gap"]["line"]
        gap = cfg.get("overrides", {}).get(line["id"], {}).get("gap_before", gap)
        start = t + gap
        lines.append({
            "id": line["id"], "scene": line["scene"], "act": act_of[line["scene"]], "text": line["text"],
            "start": round(start, 4), "end": round(start + tk["duration"], 4), "take": tk["take"],
            "factor": tk.get("factor", 1.0),
            "words": [{"w": w["w"], "start": round(start + w["start"], 4), "end": round(start + w["end"], 4)}
                      for w in tk["words"]],
        })
        t, prev = start + tk["duration"], line
    duration = round(t + cfg["tail"], 4)
    scenes = scene_spans(script, lines, duration, cfg["scene_lead"])
    return {"duration": duration, "lines": lines, "scenes": scenes, "acts": act_spans(script, scenes)}


def scene_spans(script: dict, lines: list[dict], duration: float, lead: float) -> list[dict]:
    act_of = _act_of(script)
    order = [s for a in script["acts"] for s in a["scenes"]]
    spans: list[dict] = []
    for i, s in enumerate(order):
        ls = [l for l in lines if l["scene"] == s]
        if not ls:
            raise ValueError(f"scene {s} has no lines")
        if i == 0:
            start = 0.0
        else:
            prev_ls = [l for l in lines if l["scene"] == order[i - 1]]
            start = max(prev_ls[-1]["words"][-1]["end"] + 0.1, ls[0]["words"][0]["start"] - lead)
        spans.append({"id": s, "act": act_of[s], "start": round(start, 4)})
    for i, sp in enumerate(spans):
        sp["end"] = spans[i + 1]["start"] if i + 1 < len(spans) else duration
    return spans


def act_spans(script: dict, scenes: list[dict]) -> list[dict]:
    out = []
    for a in script["acts"]:
        mine = [s for s in scenes if s["id"] in a["scenes"]]
        out.append({"id": a["id"], "name": a["name"], "start": mine[0]["start"], "end": mine[-1]["end"]})
    return out


def assemble(vo: dict, paced_dir: Path, sr: int = SR) -> np.ndarray:
    out = np.zeros(int(math.ceil(vo["duration"] * sr)) + 1, dtype=np.float32)
    for l in vo["lines"]:
        x, _ = read_wav(paced_dir / l["id"] / f"{l['take']}.wav")
        i = int(round(l["start"] * sr))
        n = min(len(x), len(out) - i)
        out[i:i + n] += x[:n]
    return out


def write_vo(vo: dict) -> None:
    (DATA / "vo.json").write_text(json.dumps(vo, indent=1))
    write_wav(AUDIO / "vo" / "vo.wav", assemble(vo, AUDIO / "vo" / "paced"))


def main(argv=None):
    argparse.ArgumentParser(description="Place takes on the timeline and assemble the voiceover").parse_args(argv)
    script = load_script()
    cfg = json.loads((DATA / "edit.json").read_text())
    vo = place(script, load_takes(script, AUDIO / "vo" / "paced", load_selects()), cfg)
    write_vo(vo)
    for a in vo["acts"]:
        print(f"act {a['id']:>3} {a['name']:<12} {a['start']:6.2f} → {a['end']:6.2f}")
    print(f"duration {vo['duration']:.2f}s" + ("" if 85 <= vo["duration"] <= 95 else "   ⚠ outside 85–95 s"))
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd tools && uv run pytest tests/test_edit.py -v`
Expected: 5 passed.

- [ ] **Step 6: Place the real takes**

Run: `cd tools && uv run film-edit`

Expected: five `act …` lines and `duration …s`.
- If the duration is **above 95 s**, lower `gap.line` to 0.35 and `gap.scene` to 0.6 in `data/edit.json` and re-run.
- If it is still above 95, report the ✂ lines from spec §4 to the user and ask which to cut. Don't cut without asking.
- If the duration is **below 85 s**, raise `tail` to 4.0 and `gap.scene` to 0.9.

- [ ] **Step 7: Commit**

```bash
git add data/edit.json data/vo.json tools/gitloom_film/edit.py tools/tests/test_edit.py
git commit -m "Takes placed on the timeline with scene and act windows" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

(`audio/vo/vo.wav` is regenerable, so leave it out of git.)

---

### Task 8: The score: composition plan, variants, and checkpoint C2

**Files:**
- Create: `tools/gitloom_film/music_plan.py`, `tools/gitloom_film/music.py`, `tools/tests/test_music_plan.py`,
  `tools/tests/test_music.py`

**Interfaces:**
- Consumes: `data/vo.json` (Task 7), `ElevenLabs.compose` and `ElevenLabsError` (Task 2), `pcm16_to_float`,
  `write_wav` and `read_wav` (Task 3), `music_page` (Task 6).
- Produces:
  - `SECTIONS: list[tuple[str, str, list[str]]]` (name, first scene, local styles)
  - `bar_seconds(bpm) -> float`
  - `section_bounds(vo, bpm, min_bars=2) -> list[float]`
  - `build_plan(vo, bpm=100.0) -> tuple[dict, dict]`: `(plan, meta)`, where
    `meta = {"bpm", "sections": [{"name", "start", "end"}]}`
  - `compose_with_fallback(client, plan, seed) -> tuple[bytes, str]`
  - `decode(audio: bytes, fmt: str, planned_seconds: float) -> np.ndarray` (shape `(n, 2)`, 48 kHz)
  - `generate_variants(client, plan, out_dir, seeds, label="score", log=print) -> list[Path]`
  - **`data/music_plan.json`:** `{"plan", "meta", "variants": [paths relative to the repo], "chosen": null | path}`

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_music_plan.py`:
```python
import pytest

from gitloom_film.music_plan import build_plan

ORDER = ["thread", "ex", "her", "repo", "loom", "diff", "cite", "braid", "merkle", "graph", "honest", "proof",
         "connect", "anywhere", "weave"]
STARTS = [0.0, 6.2, 15.1, 22.0, 28.3, 35.0, 41.2, 47.0, 54.1, 59.0, 64.2, 69.3, 75.1, 80.2, 85.0]


def vo_fixture(duration=91.0, starts=STARTS):
    return {"duration": duration,
            "scenes": [{"id": s, "start": starts[i], "end": starts[i + 1] if i + 1 < len(starts) else duration}
                       for i, s in enumerate(ORDER)]}


def test_sections_are_whole_bars_near_their_scenes():
    plan, meta = build_plan(vo_fixture(), bpm=100)
    bar = 2.4
    assert [s["section_name"] for s in plan["sections"]] == [
        "cold open", "the ex", "her", "the tour", "honest", "proof and everywhere", "weave"]
    for s in plan["sections"]:
        assert 3000 <= s["duration_ms"] <= 120000
        bars = s["duration_ms"] / 1000 / bar
        assert bars == pytest.approx(round(bars), abs=1e-3)
        assert s["lines"] == [] and s["negative_local_styles"] == []
    starts = {m["name"]: m["start"] for m in meta["sections"]}
    assert abs(starts["honest"] - 64.2) <= bar / 2 and abs(starts["her"] - 15.1) <= bar / 2
    assert sum(s["duration_ms"] for s in plan["sections"]) / 1000 >= 91.0
    assert "vocals" in plan["negative_global_styles"] and meta["bpm"] == 100


def test_short_section_is_stretched_to_two_bars():
    starts = list(STARTS)
    starts[11] = 65.0  # proof starts 0.8 s after honest
    plan, _ = build_plan(vo_fixture(starts=starts), bpm=100)
    honest = next(s for s in plan["sections"] if s["section_name"] == "honest")
    assert honest["duration_ms"] == 4800
```

`tools/tests/test_music.py`:
```python
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
        self.calls, self.channels, self.refuse_pcm, self.mp3 = [], channels, refuse_pcm, mp3

    def compose(self, plan, model_id="music_v2_5", output_format="pcm_48000", seed=None):
        self.calls.append((output_format, seed))
        if output_format.startswith("pcm"):
            if self.refuse_pcm:
                raise ElevenLabsError(403, "output_format_not_allowed")
            n = int(sum(s["duration_ms"] for s in plan["sections"]) / 1000 * 48000)
            pcm = (np.random.default_rng(0).uniform(-0.1, 0.1, n * self.channels) * 32767).astype("<i2")
            return MusicResult(pcm.tobytes(), output_format, 45, "m")
        return MusicResult(self.mp3, output_format, 45, "m")


def test_pcm_stereo_variant_written(tmp_path):
    [p] = generate_variants(FakeMusic(), PLAN, tmp_path, [11], **QUIET)
    x, sr = read_wav(p, mono=False)
    assert p.name == "score-seed11.wav" and sr == 48000 and x.shape == (144000, 2)
    assert (tmp_path / "score-seed11.plan.json").exists()


def test_pcm_mono_is_widened_to_stereo(tmp_path):
    [p] = generate_variants(FakeMusic(channels=1), PLAN, tmp_path, [3], **QUIET)
    x, _ = read_wav(p, mono=False)
    assert x.shape == (144000, 2) and np.allclose(x[:, 0], x[:, 1])


def test_refused_pcm_falls_back_to_mp3(tmp_path, mp3_bytes):
    c = FakeMusic(refuse_pcm=True, mp3=mp3_bytes)
    [p] = generate_variants(c, PLAN, tmp_path, [5], **QUIET)
    x, sr = read_wav(p, mono=False)
    assert c.calls == [("pcm_48000", 5), ("mp3_44100_128", 5)]
    assert sr == 48000 and x.shape[1] == 2 and abs(len(x) / sr - 3.0) < 0.1


def test_existing_variant_is_not_regenerated(tmp_path):
    c = FakeMusic()
    generate_variants(c, PLAN, tmp_path, [11], **QUIET)
    generate_variants(c, PLAN, tmp_path, [11], **QUIET)
    assert len(c.calls) == 1
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_music_plan.py tests/test_music.py -v`
Expected: FAIL with `ModuleNotFoundError` for `gitloom_film.music_plan` and `gitloom_film.music`.

- [ ] **Step 3: Implement the plan builder**

`tools/gitloom_film/music_plan.py`:
```python
"""The score's composition plan: one section per story beat, each a whole number of bars, starting at the bar line
nearest its first scene (spec §5.2)."""
import math

SECTIONS: list[tuple[str, str, list[str]]] = [
    ("cold open", "thread", ["low sub drone", "slow heartbeat pulse in the sub", "a single plucked note", "no drums"]),
    ("the ex", "ex", ["filtered pulse", "rising tension", "glassy ticks", "no kick yet"]),
    ("her", "her", ["kick and warm sub bass enter on the first beat", "sparse, confident groove"]),
    ("the tour", "loom", ["full groove", "sensual bassline", "plucked thread motif", "a subtle variation every 8 bars"]),
    ("honest", "honest", ["everything drops out", "near silence", "one soft pad breath at most"]),
    ("proof and everywhere", "proof", ["the full groove slams back in on the first beat", "fuller", "confident lift"]),
    ("weave", "weave", ["one big hit on the first beat", "long reverb tail", "the plucked motif alone to the end"]),
]
GLOBAL_POS = ["nocturnal, sensual, minimal electronic", "warm sub bass", "soft round kick", "crisp brushed hats",
              "breathy analog pads", "a plucked motif like a taut thread being pulled, muted harp or koto",
              "tape saturation", "intimate and expensive-sounding", "100 BPM", "minor key", "instrumental"]
GLOBAL_NEG = ["EDM drop", "trap hi-hat rolls", "cheesy synth brass", "vocals", "choir", "dubstep wobble"]


def bar_seconds(bpm: float) -> float:
    return 240.0 / bpm


def section_bounds(vo: dict, bpm: float, min_bars: int = 2) -> list[float]:
    bar = bar_seconds(bpm)
    start = {s["id"]: s["start"] for s in vo["scenes"]}
    bars = [0] + [round(start[first] / bar) for _, first, _ in SECTIONS[1:]] + [math.ceil(vo["duration"] / bar)]
    for i in range(1, len(bars)):
        bars[i] = max(bars[i], bars[i - 1] + min_bars)
    return [b * bar for b in bars]


def build_plan(vo: dict, bpm: float = 100.0) -> tuple[dict, dict]:
    b = section_bounds(vo, bpm)
    sections = []
    for i, (name, _, styles) in enumerate(SECTIONS):
        dur_ms = int(round((b[i + 1] - b[i]) * 1000))
        if not 3000 <= dur_ms <= 120000:
            raise ValueError(f"section {name!r} is {dur_ms} ms; the API allows 3000–120000")
        sections.append({"section_name": name, "positive_local_styles": styles, "negative_local_styles": [],
                         "duration_ms": dur_ms, "lines": []})
    plan = {"positive_global_styles": GLOBAL_POS, "negative_global_styles": GLOBAL_NEG, "sections": sections}
    meta = {"bpm": bpm, "sections": [{"name": n, "start": round(b[i], 4), "end": round(b[i + 1], 4)}
                                     for i, (n, _, _) in enumerate(SECTIONS)]}
    return plan, meta
```

- [ ] **Step 4: Implement generation**

`tools/gitloom_film/music.py`:
```python
"""Generate score variants from the composition plan. Prefers 48 kHz PCM; if the plan tier refuses it (HTTP 403),
falls back to 128 kbps MP3 and decodes it. Every variant is written as 48 kHz stereo 24-bit WAV."""
import argparse
import json
import subprocess
import tempfile
import webbrowser
from pathlib import Path

import numpy as np

from .audition import music_page
from .elevenlabs import ElevenLabs, ElevenLabsError
from .music_plan import build_plan
from .paths import AUDIO, DATA, OUT, ROOT
from .wav import pcm16_to_float, read_wav, write_wav


def compose_with_fallback(client, plan: dict, seed: int) -> tuple[bytes, str]:
    try:
        return client.compose(plan, output_format="pcm_48000", seed=seed).audio, "pcm_48000"
    except ElevenLabsError as e:
        if e.status != 403:
            raise
    return client.compose(plan, output_format="mp3_44100_128", seed=seed).audio, "mp3_44100_128"


def decode(audio: bytes, fmt: str, planned_seconds: float) -> np.ndarray:
    if fmt == "pcm_48000":
        ratio = (len(audio) / 2) / (planned_seconds * 48000)
        channels = 2 if abs(ratio - 2) < abs(ratio - 1) else 1
        x = pcm16_to_float(audio, channels)
        return np.stack([x, x], axis=1) if channels == 1 else x
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "in.mp3", Path(td) / "out.wav"
        src.write_bytes(audio)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", "48000", "-ac", "2", str(dst)],
                       check=True)
        x, _ = read_wav(dst, mono=False)
    return x


def generate_variants(client, plan: dict, out_dir: Path, seeds: list[int], label: str = "score",
                      log=print) -> list[Path]:
    secs = sum(s["duration_ms"] for s in plan["sections"]) / 1000
    paths = []
    for seed in seeds:
        wav = out_dir / f"{label}-seed{seed}.wav"
        if not wav.exists():
            audio, fmt = compose_with_fallback(client, plan, seed)
            write_wav(wav, decode(audio, fmt, secs))
            (out_dir / f"{label}-seed{seed}.plan.json").write_text(json.dumps({"format": fmt, "plan": plan}, indent=1))
            log(f"{wav.name}: {fmt}")
        paths.append(wav)
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate score variants from data/vo.json")
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--seed-base", type=int, default=11)
    ap.add_argument("--bpm", type=float, default=100.0)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    plan, meta = build_plan(json.loads((DATA / "vo.json").read_text()), a.bpm)
    client = ElevenLabs(credit_log=AUDIO / "credits.log")
    paths = generate_variants(client, plan, AUDIO / "music", [a.seed_base + i for i in range(a.variants)])
    rel = [str(p.relative_to(ROOT)) for p in paths]
    (DATA / "music_plan.json").write_text(json.dumps({"plan": plan, "meta": meta, "variants": rel, "chosen": None},
                                                     indent=1))
    page = music_page(paths, OUT / "auditions" / "music.html", meta["sections"])
    print(page)
    if not a.no_open:
        webbrowser.open(page.as_uri())
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd tools && uv run pytest tests/test_music_plan.py tests/test_music.py -v`
Expected: 6 passed.

- [ ] **Step 6: Generate three variants** (about 4,200 credits at ≈900 credits per minute)

Run: `cd tools && uv run film-music --variants 3`

Expected: three lines like `score-seed11.wav: pcm_48000` (or `mp3_44100_128`), followed by the page path; the music
page opens. Record the format that was accepted in the commit message.

- [ ] **Step 7: Commit**

```bash
git add tools/gitloom_film/music_plan.py tools/gitloom_film/music.py tools/tests/test_music_plan.py tools/tests/test_music.py data/music_plan.json audio/credits.log
git commit -m "Score composed to the edit: seven sections on whole bars, three variants" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

- [ ] **Step 8: CHECKPOINT C2: stop and ask the user**

The user listens on `out/auditions/music.html` and picks a variant (or asks for a different vibe).
- **On a pick:** set `"chosen": "audio/music/score-seed<N>.wav"` in `data/music_plan.json` and commit with the
  message `Score picked at C2`.
- **On a vibe change:** edit `GLOBAL_POS`/`GLOBAL_NEG` in `music_plan.py` per their words, re-run
  `film-music --variants 2 --seed-base 21`, and ask again.

**Do not start Task 9 until a variant is chosen.**

---

### Task 9: Beat grid, sections, envelopes → `data/audio.json`

**Files:**
- Create: `tools/gitloom_film/beats.py`, `tools/tests/test_beats.py`

**Interfaces:**
- Consumes: the chosen WAV and `meta` from `data/music_plan.json` (Task 8), `data/vo.json` (Task 7),
  `audio/vo/vo.wav` (Task 7), `read_wav` (Task 3).
- Produces:
  - `analyze(y: np.ndarray, sr: int, meta: dict, vo: dict | None = None, vo_y: np.ndarray | None = None) -> dict`
    in the engine's `AudioJSON` shape (`app/src/engine/audio.ts`):
    ```
    {duration, bpm, beat_period, time_signature: 4, beats, downbeats, sections: [{name, start, end}], fps: 100,
     rms, low, mid, high, vocal, drums, bass, other,
     onsets: {kick, snare, hat, vocal: [[t, strength]]},
     grid_error_ms, grid_fit}
    ```
  - `fit_grid(beats, duration) -> (grid, period, median_abs_error_s)`
  - `grid_fit(grid, onset_times, active) -> float`: the share of beats in audible stretches that have an audio onset
    within 30 ms. This is the drift detector; 0.9 or more means the grid holds.

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_beats.py`:
```python
import numpy as np
import pytest

from gitloom_film.beats import analyze

SR = 22050
META = {"bpm": 100.0, "sections": [{"name": "a", "start": 0.0, "end": 14.4}, {"name": "b", "start": 14.4, "end": 30.0}]}


def clicks(bpm=100.0, dur=30.0, offset=0.25, silent=None, bpm2=None, switch=15.0):
    y = np.zeros(int(dur * SR), np.float32)
    L = int(0.05 * SR)
    k = np.arange(L) / SR
    t, i = offset, 0
    while t < dur - 0.1:
        if not (silent and silent[0] <= t < silent[1]):
            if i % 4 == 0:
                burst = np.exp(-k / 0.03) * np.sin(2 * np.pi * 60 * k)  # a kick on the one
            else:
                burst = 0.3 * np.exp(-k / 0.005) * np.sin(2 * np.pi * 3000 * k)  # a tick
            n = int(round(t * SR))
            y[n:n + L] += burst.astype(np.float32)
        t += 60.0 / (bpm2 if bpm2 and t >= switch else bpm)
        i += 1
    return y


def test_grid_tempo_phase_and_downbeats():
    a = analyze(clicks(), SR, META)
    b, d = np.array(a["beats"]), np.array(a["downbeats"])
    assert a["bpm"] == pytest.approx(100.0, abs=0.3) and a["grid_error_ms"] < 20
    assert np.min(np.abs(b - 0.25)) < 0.02
    assert np.min(np.abs(d - 0.25)) < 0.02 and np.min(np.abs(d - 2.65)) < 0.02
    assert len(a["rms"]) == 3000 and min(a["low"]) >= 0.0 and max(a["low"]) <= 1.0
    assert a["sections"][1]["start"] == pytest.approx(14.65, abs=0.03)  # 14.4 snapped to the downbeat
    assert a["sections"][-1]["end"] == pytest.approx(a["duration"])
    assert len(a["onsets"]["kick"]) >= 8


def test_grid_runs_through_silence():
    a = analyze(clicks(silent=(10.0, 18.0)), SR, META)
    inside = np.array([t for t in a["beats"] if 10.5 < t < 17.5])
    assert len(inside) >= 10
    expected = 0.25 + np.round((inside - 0.25) / 0.6) * 0.6
    assert np.max(np.abs(inside - expected)) < 0.02


def test_steady_score_fits_and_drift_is_reported():
    assert analyze(clicks(), SR, META)["grid_fit"] >= 0.9
    assert analyze(clicks(bpm2=110.0), SR, META)["grid_fit"] < 0.8  # the tempo changes mid-track


def test_vocal_onsets_and_envelope_come_from_the_voice():
    vo = {"lines": [{"words": [{"w": "a", "start": 1.0, "end": 1.2}, {"w": "b", "start": 2.0, "end": 2.2}]}]}
    vo_y = np.zeros(30 * SR, np.float32)
    vo_y[SR:int(1.2 * SR)] = 0.5
    a = analyze(clicks(), SR, META, vo=vo, vo_y=vo_y)
    assert a["onsets"]["vocal"] == [[1.0, 1.0], [2.0, 1.0]]
    assert a["vocal"][110] > 0.5 and a["vocal"][150] < 0.1
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_beats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitloom_film.beats'`.

- [ ] **Step 3: Implement `beats.py`**

`tools/gitloom_film/beats.py`:
```python
"""Beat grid, sections, envelopes and onsets for the engine (data/audio.json).

The score is generated at one tempo, so the grid is a straight line fitted to librosa's tracked beats. It carries
on through drumless stretches (the cold open, the honesty drop-out) where a tracker loses the beat. `grid_fit`
measures the grid against the audio's own onsets. Below 0.9 the tempo drifts, and a human decides (regenerate the
score, or cut on its downbeats); the music is the truth (spec §5.2).
"""
import argparse
import json

import librosa
import numpy as np

from .paths import AUDIO, DATA, ROOT
from .wav import read_wav

FPS = 100
HOP = 256


def fit_grid(beats: np.ndarray, duration: float) -> tuple[np.ndarray, float, float]:
    period = float(np.median(np.diff(beats)))
    ang = 2 * np.pi * (beats % period) / period
    phase = float((np.angle(np.mean(np.exp(1j * ang))) % (2 * np.pi)) / (2 * np.pi) * period)
    idx = np.round((beats - phase) / period)
    near = np.abs(beats - (phase + idx * period)) < 0.2 * period
    period, phase = (float(v) for v in np.polyfit(idx[near], beats[near], 1))
    phase %= period
    resid = beats - (phase + np.round((beats - phase) / period) * period)
    return np.arange(phase, duration, period), period, float(np.median(np.abs(resid)))


def _norm(x: np.ndarray) -> np.ndarray:
    """0..1, with the loudest 1% clipping at 1 (half the peak, for sparse signals like a voice)."""
    if not len(x) or float(x.max()) <= 0:
        return np.zeros_like(x)
    return np.clip(x / max(float(np.percentile(x, 99)), 0.5 * float(x.max())), 0.0, 1.0)


def grid_fit(grid: np.ndarray, onset_times: np.ndarray, active: np.ndarray) -> float:
    beats = grid[active]
    if not len(beats) or not len(onset_times):
        return 0.0
    i = np.searchsorted(onset_times, beats)
    lo = onset_times[np.clip(i - 1, 0, len(onset_times) - 1)]
    hi = onset_times[np.clip(i, 0, len(onset_times) - 1)]
    return float(np.mean(np.minimum(np.abs(beats - lo), np.abs(beats - hi)) < 0.03))


def _fit(x: np.ndarray, n: int) -> np.ndarray:
    return np.pad(x, (0, max(0, n - len(x))))[:n]


def _band(S: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    band = S[(freqs >= lo) & (freqs < hi)]
    return np.sqrt(np.mean(band ** 2, axis=0)) if len(band) else np.zeros(S.shape[1])


def _onsets(env: np.ndarray) -> list[list[float]]:
    flux = np.maximum(0.0, np.diff(env, prepend=env[0]))
    if flux.max() <= 0:
        return []
    flux = flux / flux.max()
    peaks = librosa.util.peak_pick(flux, pre_max=3, post_max=3, pre_avg=10, post_avg=10, delta=0.07, wait=10)
    return [[round(p / FPS, 3), round(float(flux[p]), 3)] for p in peaks]


def _downbeat_phase(beats: np.ndarray, low: np.ndarray, starts: list[float], period: float) -> int:
    at = low[np.clip(np.round(beats * FPS).astype(int), 0, len(low) - 1)]
    best, best_score = 0, -np.inf
    for p in range(4):
        db = beats[p::4]
        dist = np.mean([np.min(np.abs(db - s)) for s in starts]) / period if starts and len(db) else 0.0
        score = at[p::4].mean() - at.mean() - 0.5 * dist
        if score > best_score:
            best, best_score = p, score
    return best


def analyze(y: np.ndarray, sr: int, meta: dict, vo: dict | None = None, vo_y: np.ndarray | None = None) -> dict:
    duration = len(y) / sr
    n = int(np.ceil(duration * FPS))
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    _, bf = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, hop_length=HOP, start_bpm=meta["bpm"],
                                    tightness=400, trim=False)
    tracked = librosa.frames_to_time(bf, sr=sr, hop_length=HOP)
    beats, period, err = fit_grid(tracked, duration)
    hop = max(1, sr // FPS)
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    low, mid, high = (_norm(_fit(_band(S, freqs, lo, hi), n)) for lo, hi in ((20, 150), (150, 2000), (4000, 16000)))
    rms = _norm(_fit(librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0], n))
    onset_t = librosa.onset.onset_detect(onset_envelope=oenv, sr=sr, hop_length=HOP, units="time", backtrack=False)
    active = rms[np.clip(np.round(beats * FPS).astype(int), 0, n - 1)] > 0.05
    fit = grid_fit(beats, onset_t, active)
    t = np.arange(n) / FPS
    drums = _norm(np.interp(t, librosa.frames_to_time(np.arange(len(oenv)), sr=sr, hop_length=HOP), oenv))
    starts = [s["start"] for s in meta["sections"]]
    downs = beats[_downbeat_phase(beats, low, starts, period)::4]
    snapped = [float(downs[np.argmin(np.abs(downs - s))]) if i else 0.0 for i, s in enumerate(starts)]
    sections = [{"name": s["name"], "start": round(snapped[i], 3),
                 "end": round(snapped[i + 1], 3) if i + 1 < len(snapped) else round(duration, 3)}
                for i, s in enumerate(meta["sections"])]
    vocal = np.zeros(n)
    if vo_y is not None:
        vr = max(1, sr // FPS) if len(vo_y) else 1
        vocal = _norm(_fit(librosa.feature.rms(y=vo_y, frame_length=2048, hop_length=vr)[0], n))
    vocal_on = [[w["start"], 1.0] for l in (vo or {}).get("lines", []) for w in l["words"]]
    r3 = lambda a: [round(float(v), 3) for v in a]  # noqa: E731
    return {
        "duration": round(duration, 3), "bpm": round(60.0 / period, 3), "beat_period": round(period, 5),
        "time_signature": 4, "beats": r3(beats), "downbeats": r3(downs), "sections": sections, "fps": FPS,
        "rms": r3(rms), "low": r3(low), "mid": r3(mid), "high": r3(high), "vocal": r3(vocal), "drums": r3(drums),
        "bass": r3(low), "other": r3(mid),
        "onsets": {"kick": _onsets(low), "snare": _onsets(mid), "hat": _onsets(high), "vocal": vocal_on},
        "grid_error_ms": round(err * 1000, 1), "grid_fit": round(fit, 3),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Analyse the chosen score into data/audio.json")
    ap.add_argument("--music", help="WAV to analyse (default: the chosen variant in data/music_plan.json)")
    a = ap.parse_args(argv)
    mp = json.loads((DATA / "music_plan.json").read_text())
    path = ROOT / (a.music or mp["chosen"] or "")
    if not path.is_file():
        raise SystemExit("no chosen score: set 'chosen' in data/music_plan.json (checkpoint C2)")
    y, sr = read_wav(path)
    vo = json.loads((DATA / "vo.json").read_text())
    vo_y, vsr = read_wav(AUDIO / "vo" / "vo.wav")
    if vsr != sr:
        vo_y = librosa.resample(vo_y, orig_sr=vsr, target_sr=sr)
    out = analyze(y, sr, mp["meta"], vo, vo_y)
    (DATA / "audio.json").write_text(json.dumps(out))
    print(f"{out['bpm']} BPM · grid fit {out['grid_fit']:.2f} · grid error {out['grid_error_ms']} ms · "
          f"{len(out['beats'])} beats · {len(out['downbeats'])} downbeats"
          + ("" if out["grid_fit"] >= 0.9 else "   ⚠ the tempo drifts: ask the user (regenerate, or cut on downbeats)"))
    for s in out["sections"]:
        print(f"  {s['name']:<22} {s['start']:7.3f} → {s['end']:7.3f}")
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd tools && uv run pytest tests/test_beats.py -v`
Expected: 4 passed.

- [ ] **Step 5: Analyse the chosen score**

Run: `cd tools && uv run film-beats`

Expected: `100.0 BPM · grid fit ≥0.90 · …` and seven section lines, each starting within one bar of the plan. If
the fit is below 0.90, **stop and ask the user**: regenerate the score (`film-music --variants 2 --seed-base 31`,
then back to C2), or accept cutting on the detected downbeats only.

- [ ] **Step 6: Commit**

```bash
git add tools/gitloom_film/beats.py tools/tests/test_beats.py data/audio.json
git commit -m "Beat grid fitted to the score, carried through its silences" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---

### Task 10: Put the voice on the beat, and cut scenes on beats

**Files:**
- Create: `tools/gitloom_film/snap.py`, `tools/tests/test_snap.py`

**Interfaces:**
- Consumes:
  - `data/vo.json` (Task 7) and `data/audio.json` (Task 9)
  - `act_spans` and `write_vo` from `edit.py` (Task 7)
  - `load_script` (Task 4)
- Produces:
  - `snap_lines(lines, beats, tol=0.15, min_gap=0.05) -> list[dict]`
  - `cut_scenes(scenes, lines, beats, downs, act_starts: set[str], duration, lead=0.12) -> list[dict]`
  - `snap(vo, audio, script) -> dict`: a new `vo` with lines nudged, scenes cut, acts recomputed, and
    `duration = max(vo duration, music duration)`.
  - CLI `film-snap` rewrites `data/vo.json` and `audio/vo/vo.wav`.

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_snap.py`:
```python
import numpy as np
import pytest

from gitloom_film.snap import cut_scenes, snap, snap_lines

BEATS = np.round(np.arange(0.2, 30.0, 0.6), 4)  # 0.2, 0.8, 1.4, …
DOWNS = BEATS[::4]  # 0.2, 2.6, 5.0, 7.4, 9.8, …


def line(lid, scene, start, dur=1.0):
    return {"id": lid, "scene": scene, "start": start, "end": start + dur,
            "words": [{"w": "a", "start": start + 0.04, "end": start + 0.5},
                      {"w": "b.", "start": start + 0.6, "end": start + dur - 0.1}]}


def test_line_within_tolerance_moves_onto_the_beat():
    [l] = snap_lines([line("L1", "s1", 1.30)], BEATS)  # first word 1.34 → beat 1.4
    assert l["words"][0]["start"] == pytest.approx(1.4) and l["start"] == pytest.approx(1.36)
    assert l["words"][1]["start"] == pytest.approx(1.96)


def test_line_beyond_tolerance_stays():
    [l] = snap_lines([line("L1", "s1", 1.66)], BEATS)  # first word 1.70 is 0.3 s from both beats
    assert l["start"] == 1.66


def test_nudge_never_collides_with_the_next_line():
    out = snap_lines([line("L1", "s1", 1.30), line("L2", "s1", 2.38)], BEATS)
    assert out[0]["start"] == 1.30  # +0.06 would leave 0.02 s before L2


def test_cut_is_the_last_beat_before_the_first_word_and_acts_take_downbeats():
    lines = [line("L1", "s1", 1.0), line("L2", "s2", 4.0), line("L3", "s3", 8.9)]
    scenes = [{"id": "s1", "act": "I"}, {"id": "s2", "act": "I"}, {"id": "s3", "act": "II"}]
    out = cut_scenes(scenes, lines, BEATS, DOWNS, act_starts={"s3"}, duration=12.0)
    assert [s["start"] for s in out] == [0.0, 3.8, 7.4]
    assert [s["end"] for s in out] == [3.8, 7.4, 12.0]


def test_cut_never_lands_after_the_word_or_before_the_previous_word():
    lines = [line("L1", "s1", 1.0, dur=1.25), line("L2", "s2", 2.25)]  # words end 2.15; next starts 2.29
    scenes = [{"id": "s1", "act": "I"}, {"id": "s2", "act": "I"}]
    out = cut_scenes(scenes, lines, BEATS, DOWNS, act_starts=set(), duration=5.0)
    assert 2.15 <= out[1]["start"] <= 2.29


def test_snap_updates_lines_scenes_acts_and_duration():
    script = {"acts": [{"id": "I", "name": "A", "scenes": ["s1", "s2"]}, {"id": "II", "name": "B", "scenes": ["s3"]}]}
    vo = {"duration": 11.0, "lines": [line("L1", "s1", 1.30), line("L2", "s2", 4.0), line("L3", "s3", 8.9)],
          "scenes": [{"id": "s1", "act": "I", "start": 0, "end": 3}, {"id": "s2", "act": "I", "start": 3, "end": 8},
                     {"id": "s3", "act": "II", "start": 8, "end": 11}], "acts": []}
    out = snap(vo, {"duration": 12.0, "beats": list(BEATS), "downbeats": list(DOWNS)}, script)
    assert out["duration"] == 12.0 and out["scenes"][-1]["end"] == 12.0
    assert out["lines"][0]["words"][0]["start"] == pytest.approx(1.4)
    assert [a["id"] for a in out["acts"]] == ["I", "II"] and out["acts"][1]["start"] == out["scenes"][2]["start"]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_snap.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitloom_film.snap'`.

- [ ] **Step 3: Implement `snap.py`**

`tools/gitloom_film/snap.py`:
```python
"""Put the voice on the beat.

1. Each line moves (at most `tol`) so that its first word lands on the nearest beat, unless that would bring it
   within `min_gap` of a neighbouring line.
2. Each scene then cuts on the last beat that is at least `lead` before its first word and not before the previous
   scene's last word; an act's first scene prefers a downbeat. If no beat fits, the cut takes the latest allowed
   moment, and the sync report flags it.
"""
import argparse
import json

import numpy as np

from .edit import act_spans, write_vo
from .paths import DATA
from .vo import load_script


def _shift(l: dict, d: float) -> dict:
    r = lambda x: round(x + d, 4)  # noqa: E731
    return {**l, "start": r(l["start"]), "end": r(l["end"]),
            "words": [{**w, "start": r(w["start"]), "end": r(w["end"])} for w in l["words"]]}


def snap_lines(lines: list[dict], beats, tol: float = 0.15, min_gap: float = 0.05) -> list[dict]:
    beats = np.asarray(beats)
    out = [dict(l) for l in lines]
    for i, l in enumerate(out):
        first = l["words"][0]["start"]
        d = float(beats[np.argmin(np.abs(beats - first))]) - first
        prev_end = out[i - 1]["end"] if i else -np.inf
        next_start = lines[i + 1]["start"] if i + 1 < len(lines) else np.inf
        if abs(d) <= tol and l["start"] + d >= prev_end + min_gap and l["end"] + d <= next_start - min_gap:
            out[i] = _shift(l, d)
    return out


def cut_scenes(scenes: list[dict], lines: list[dict], beats, downs, act_starts: set[str], duration: float,
               lead: float = 0.12) -> list[dict]:
    beats, downs = np.asarray(beats), np.asarray(downs)
    out = []
    for i, s in enumerate(scenes):
        if i == 0:
            start = 0.0
        else:
            w0 = min(l["words"][0]["start"] for l in lines if l["scene"] == s["id"])
            lo = max(l["words"][-1]["end"] for l in lines if l["scene"] == scenes[i - 1]["id"])
            hi = w0 - lead
            pick = None
            for grid in ([downs] if s["id"] in act_starts else []) + [beats]:
                c = grid[(grid >= lo) & (grid <= hi)]
                if len(c):
                    pick = float(c[-1])
                    break
            start = pick if pick is not None else max(lo, hi)
        out.append({**s, "start": round(start, 4)})
    for i, s in enumerate(out):
        s["end"] = out[i + 1]["start"] if i + 1 < len(out) else duration
    return out


def snap(vo: dict, audio: dict, script: dict) -> dict:
    duration = round(max(vo["duration"], audio["duration"]), 4)
    lines = snap_lines(vo["lines"], audio["beats"])
    act_starts = {a["scenes"][0] for a in script["acts"]}
    scenes = cut_scenes(vo["scenes"], lines, audio["beats"], audio["downbeats"], act_starts, duration)
    return {**vo, "duration": duration, "lines": lines, "scenes": scenes, "acts": act_spans(script, scenes)}


def main(argv=None):
    argparse.ArgumentParser(description="Nudge lines onto beats and cut scenes on beats").parse_args(argv)
    vo = json.loads((DATA / "vo.json").read_text())
    audio = json.loads((DATA / "audio.json").read_text())
    out = snap(vo, audio, load_script())
    moved = sum(1 for a, b in zip(vo["lines"], out["lines"]) if a["start"] != b["start"])
    write_vo(out)
    print(f"{moved}/{len(out['lines'])} lines nudged onto beats · duration {out['duration']:.2f}s")
    for s in out["scenes"]:
        print(f"  {s['id']:<9} {s['start']:7.3f} → {s['end']:7.3f}")
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd tools && uv run pytest tests/test_snap.py -v`
Expected: 6 passed.

- [ ] **Step 5: Snap the real edit**

Run: `cd tools && uv run film-snap`
Expected: `N/33 lines nudged onto beats · duration …s` and 15 scene lines. (L18b is excluded unless it's enabled.)

- [ ] **Step 6: Commit**

```bash
git add tools/gitloom_film/snap.py tools/tests/test_snap.py data/vo.json
git commit -m "Lines land on the beat and every scene cuts on one" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---

### Task 11: The mix: music ducks under her, −14 LUFS

**Files:**
- Create: `tools/gitloom_film/mix.py`, `tools/tests/test_mix.py`

**Interfaces:**
- Consumes: `audio/vo/vo.wav` (Tasks 7 and 10), the chosen score (Task 8), `read_wav`/`write_wav` (Task 3).
- Produces:
  - `premix(vo: Path, music: Path, out: Path, music_gain_db=-2.0) -> None`
  - `measure(path: Path) -> {"I": float, "TP": float}` (integrated LUFS, true peak dBTP)
  - `mix(vo: Path, music: Path, out: Path) -> dict` (the measured values)
  - CLI `film-mix`, which writes `audio/mix/mix.wav` (the engine's preview and render audio)

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_mix.py`:
```python
import numpy as np
import pytest

from gitloom_film.mix import mix
from gitloom_film.wav import read_wav, write_wav

SR = 48000


def synth(tmp):
    t = np.arange(10 * SR) / SR
    vo = np.zeros_like(t, dtype=np.float32)
    for k in range(0, 10, 2):  # a 1 kHz "voice", on for 1 s every 2 s
        on = (t >= k) & (t < k + 1)
        vo[on] = 0.3 * np.sin(2 * np.pi * 1000 * t[on])
    music = (0.2 * np.random.default_rng(1).standard_normal(len(t))).astype(np.float32)
    write_wav(tmp / "vo.wav", vo)
    write_wav(tmp / "music.wav", np.stack([music, music], axis=1))
    return tmp / "vo.wav", tmp / "music.wav"


def hi_band_db(x):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    return 10 * np.log10(spec[np.fft.rfftfreq(len(x), 1 / SR) > 4000].mean())


def test_mix_hits_loudness_targets(tmp_path):
    vo, mu = synth(tmp_path)
    m = mix(vo, mu, tmp_path / "mix.wav")
    assert m["I"] == pytest.approx(-14.0, abs=0.5) and m["TP"] <= -1.0
    y, sr = read_wav(tmp_path / "mix.wav", mono=False)
    assert sr == 48000 and y.shape[1] == 2


def test_music_ducks_under_the_voice(tmp_path):
    vo, mu = synth(tmp_path)
    mix(vo, mu, tmp_path / "mix.wav")
    y, _ = read_wav(tmp_path / "mix.wav")
    on = np.mean([hi_band_db(y[int((k + 0.3) * SR):int((k + 0.8) * SR)]) for k in range(2, 10, 2)])
    off = np.mean([hi_band_db(y[int((k + 1.3) * SR):int((k + 1.8) * SR)]) for k in range(2, 8, 2)])
    assert off - on >= 4.0  # energy above 4 kHz is music only
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_mix.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitloom_film.mix'`.

- [ ] **Step 3: Implement `mix.py`**

`tools/gitloom_film/mix.py`:
```python
"""Mix the voice over the score. The music ducks under her through a sidechain compressor (about 6–9 dB for a
spoken voice), then two-pass EBU R128 normalisation brings it to −14 LUFS with true peak ≤ −1 dBTP, at 48 kHz /
24-bit."""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from .paths import AUDIO, DATA, ROOT

TARGET_I, TARGET_TP = -14.0, -1.5  # aim under −1.0 so the true-peak estimate has margin


def _ff(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", *args], capture_output=True, text=True,
                          check=True)


def premix(vo: Path, music: Path, out: Path, music_gain_db: float = -2.0) -> None:
    graph = ("[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[vo][key];"
             f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={music_gain_db}dB[mu];"
             "[mu][key]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=350:makeup=1[duck];"
             "[duck][vo]amix=inputs=2:normalize=0:duration=longest[mix]")
    _ff(["-i", str(vo), "-i", str(music), "-filter_complex", graph, "-map", "[mix]", "-ar", "48000",
         "-c:a", "pcm_s24le", str(out)])


def measure(path: Path) -> dict:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True, check=True)
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    return {"I": float(re.search(r"I:\s+(-?[\d.]+) LUFS", tail).group(1)),
            "TP": float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail).group(1))}


def loudnorm(src: Path, out: Path) -> dict:
    base = f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA=11"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af", f"{base}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, check=True)
    m = json.loads(r.stderr[r.stderr.rfind("{"):r.stderr.rfind("}") + 1])
    af = (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    _ff(["-i", str(src), "-af", af, "-ar", "48000", "-c:a", "pcm_s24le", str(out)])
    return measure(out)


def mix(vo: Path, music: Path, out: Path) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        pre = Path(td) / "pre.wav"
        premix(vo, music, pre)
        return loudnorm(pre, out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mix the voiceover over the score into audio/mix/mix.wav")
    ap.add_argument("--music", help="score WAV (default: the chosen variant)")
    a = ap.parse_args(argv)
    music = ROOT / (a.music or json.loads((DATA / "music_plan.json").read_text())["chosen"])
    m = mix(AUDIO / "vo" / "vo.wav", music, AUDIO / "mix" / "mix.wav")
    ok = abs(m["I"] - TARGET_I) <= 0.5 and m["TP"] <= -1.0
    print(f"audio/mix/mix.wav · {m['I']:.1f} LUFS · {m['TP']:.1f} dBTP" + ("" if ok else "   ⚠ outside target"))
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd tools && uv run pytest tests/test_mix.py -v`
Expected: 2 passed.

- [ ] **Step 5: Mix the animatic audio**

Run: `cd tools && uv run film-mix`
Expected: `audio/mix/mix.wav · -14.0 LUFS · -1.x dBTP`, with no warning.

- [ ] **Step 6: Commit**

```bash
git add tools/gitloom_film/mix.py tools/tests/test_mix.py
git commit -m "Voice over score: sidechain ducking and two-pass loudness to -14 LUFS" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---

### Task 12: Fonts: pinned sources → static instances

**Files:**
- Create: `fonts/src/SHA256SUMS`, `fonts/src/*` (downloaded), `tools/gitloom_film/fonts.py`, `tools/tests/test_fonts.py`

**Interfaces:**
- Produces:
  - `SRC = FONTS / "src"`
  - `BRICOLAGE = [(wdth, wght), …]` over wdth {75, 87.5, 100} × wght {300, 500, 600, 800}
  - `bricolage_name(wdth, wght) -> "Bricolage-w{wdth*10}-{wght}.ttf"`
  - `make_instance(src, axes, out, weight_class, width_class=5) -> Path`
  - `build_all(src_dir, out_dir) -> list[Path]`
  - **Files in `app/public/fonts/`:**
    - `Bricolage-w{750,875,1000}-{300,500,600,800}.ttf`
    - `JetBrainsMono-{400,500,700}.ttf`, `JetBrainsMonoItalic-400.ttf`
    - `Geist-{400,500,600}.ttf`
    - the `OFL-*.txt` files

- [ ] **Step 1: Fetch the pinned sources and verify them**

`fonts/src/SHA256SUMS`:
```
413e7357809ddd12fd80a96a8a396de0e401638d4acd3cb3e37532f0472ac682  BricolageGrotesque[opsz,wdth,wght].ttf
48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda  JetBrainsMono[wght].ttf
85ae2a5cd3f56baf1ce1c21a851322c58e3d8fbe8e8ad4a4d090a820dd7fe558  JetBrainsMono-Italic[wght].ttf
73894e0448cae90a92b6c2f8732b7bb9acb7b94c418bff559dad4a18e1de9659  Geist[wght].ttf
4b5a7d8f37f5602621c8a8d7358a6a2e71317e6c231c661e15aef0275d3e07ba  OFL-Bricolage.txt
b2fe5e8987594e9ffd1d2ca52a2f5d73eb8335243893c5d6254b5ad69269591d  OFL-JetBrainsMono.txt
1781d2806a07d91c4edf4740b88449fab7d0eadad53f7c351b94cd4d4eb8c00f  OFL-Geist.txt
```

Run:
```bash
cd fonts/src
G=https://raw.githubusercontent.com/google/fonts/9710da1eacb3be272583c3224dcb70f9da6eadbb/ofl
curl -fsSL -o 'BricolageGrotesque[opsz,wdth,wght].ttf' "$G/bricolagegrotesque/BricolageGrotesque%5Bopsz%2Cwdth%2Cwght%5D.ttf"
curl -fsSL -o 'JetBrainsMono[wght].ttf' "$G/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"
curl -fsSL -o 'JetBrainsMono-Italic[wght].ttf' "$G/jetbrainsmono/JetBrainsMono-Italic%5Bwght%5D.ttf"
curl -fsSL -o 'Geist[wght].ttf' "$G/geist/Geist%5Bwght%5D.ttf"
curl -fsSL -o OFL-Bricolage.txt "$G/bricolagegrotesque/OFL.txt"
curl -fsSL -o OFL-JetBrainsMono.txt "$G/jetbrainsmono/OFL.txt"
curl -fsSL -o OFL-Geist.txt "$G/geist/OFL.txt"
shasum -a 256 -c SHA256SUMS
```
Expected: seven `OK` lines.

- [ ] **Step 2: Write the failing tests**

`tools/tests/test_fonts.py`:
```python
from fontTools.ttLib import TTFont

from gitloom_film.fonts import SRC, bricolage_name, make_instance


def advance(path, ch="M"):
    f = TTFont(path)
    return f["hmtx"][f.getBestCmap()[ord(ch)]][0]


def test_bricolage_instances_are_static_weighted_and_kerned(tmp_path):
    src = SRC / "BricolageGrotesque[opsz,wdth,wght].ttf"
    narrow = make_instance(src, {"opsz": 96, "wdth": 75, "wght": 300}, tmp_path / bricolage_name(75, 300), 300, 3)
    wide = make_instance(src, {"opsz": 96, "wdth": 100, "wght": 800}, tmp_path / bricolage_name(100, 800), 800, 5)
    assert (narrow.name, wide.name) == ("Bricolage-w750-300.ttf", "Bricolage-w1000-800.ttf")
    assert bricolage_name(87.5, 600) == "Bricolage-w875-600.ttf"
    for p, wt, wc in ((narrow, 300, 3), (wide, 800, 5)):
        f = TTFont(p)
        assert "fvar" not in f and "GPOS" in f
        assert (f["OS/2"].usWeightClass, f["OS/2"].usWidthClass) == (wt, wc)
    assert advance(narrow) < advance(wide)


def test_mono_instance_stays_monospaced(tmp_path):
    p = make_instance(SRC / "JetBrainsMono[wght].ttf", {"wght": 500}, tmp_path / "JetBrainsMono-500.ttf", 500)
    f = TTFont(p)
    assert "fvar" not in f and f["OS/2"].usWeightClass == 500
    assert len({advance(p, c) for c in "iMW0"}) == 1
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_fonts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitloom_film.fonts'`.

- [ ] **Step 4: Implement `fonts.py`**

`tools/gitloom_film/fonts.py`:
```python
"""Static font instances for the engine. opentype.js can't read variation data, so every width and weight the film
uses is cut from the pinned variable sources as its own file. Kerning lives in GPOS and survives instancing."""
import argparse
import shutil
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from .paths import APP, FONTS

SRC = FONTS / "src"
BRICOLAGE = [(w, wt) for w in (75, 87.5, 100) for wt in (300, 500, 600, 800)]
WIDTH_CLASS = {75: 3, 87.5: 4, 100: 5}
MONO, GEIST = (400, 500, 700), (400, 500, 600)


def bricolage_name(wdth: float, wght: int) -> str:
    return f"Bricolage-w{int(round(wdth * 10))}-{wght}.ttf"


def make_instance(src: Path, axes: dict[str, float], out: Path, weight_class: int, width_class: int = 5) -> Path:
    inst = instantiateVariableFont(TTFont(src), axes)
    inst["OS/2"].usWeightClass = weight_class
    inst["OS/2"].usWidthClass = width_class
    out.parent.mkdir(parents=True, exist_ok=True)
    inst.save(out)
    return out


def build_all(src_dir: Path, out_dir: Path) -> list[Path]:
    made = []
    b = src_dir / "BricolageGrotesque[opsz,wdth,wght].ttf"
    for w, wt in BRICOLAGE:
        made.append(make_instance(b, {"opsz": 96, "wdth": w, "wght": wt}, out_dir / bricolage_name(w, wt), wt,
                                  WIDTH_CLASS[w]))
    for wt in MONO:
        made.append(make_instance(src_dir / "JetBrainsMono[wght].ttf", {"wght": wt},
                                  out_dir / f"JetBrainsMono-{wt}.ttf", wt))
    made.append(make_instance(src_dir / "JetBrainsMono-Italic[wght].ttf", {"wght": 400},
                              out_dir / "JetBrainsMonoItalic-400.ttf", 400))
    for wt in GEIST:
        made.append(make_instance(src_dir / "Geist[wght].ttf", {"wght": wt}, out_dir / f"Geist-{wt}.ttf", wt))
    for lic in src_dir.glob("OFL-*.txt"):
        shutil.copy(lic, out_dir / lic.name)
    return made


def main(argv=None):
    argparse.ArgumentParser(description="Cut static font instances into app/public/fonts").parse_args(argv)
    made = build_all(SRC, APP / "public" / "fonts")
    print(f"{len(made)} fonts → app/public/fonts")
```

- [ ] **Step 5: Run the tests, then build the fonts**

Run:
```bash
cd tools && uv run pytest tests/test_fonts.py -v && uv run film-fonts
```
Expected: 2 passed, then `19 fonts → app/public/fonts`.

- [ ] **Step 6: Commit**

```bash
git add fonts/src tools/gitloom_film/fonts.py tools/tests/test_fonts.py app/public/fonts
git commit -m "Pinned OFL font sources, cut into the static instances the engine reads" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---

### Task 13: Fork the engine, re-skinned to GitLoom

**Files:**
- Create (copied from PDoom-Video @ `bdbad53`, then edited):
  - `app/{package.json,bun.lock,tsconfig.json,tsconfig.scripts.json,vite.config.ts,index.html}`
  - `app/src/main.ts`
  - `app/src/engine/{audio,engine,gl,hud,lines,palette,post,scale,scene,stroke,type,util}.ts`
  - `app/src/engine/glsl/common.ts`, `app/scripts/render.ts`, `app/public/fonts/stroke/*`
- Create (new): `app/src/engine/vo.ts` (replaces `lyrics.ts`), `app/src/timeline.ts` (a stub until Task 14),
  `app/src/engine/{palette,vo,type,util}.test.ts`

**Interfaces:**
- Consumes:
  - `data/vo.json` (Tasks 7 and 10), `data/audio.json` (Task 9), `audio/mix/mix.wav` (Task 11)
  - the fonts in `app/public/fonts/` (Task 12)
- Produces:
  - `HEX`/`LIN`/`rgba` with keys ink, ink2, panel, panel2, rule, ruleStrong, bone, boneDim, boneFaint, blood,
    bloodBright, bloodDim, moss, mossDim
  - GLSL `C_INK C_INK2 C_PANEL C_RULE C_BONE C_BONE_DIM C_BONE_FAINT C_BLOOD C_BLOOD_BRIGHT C_BLOOD_DIM C_MOSS C_MOSS_DIM`,
    and `heat(x)` (a blood ramp)
  - `F.display(width 75..100, weight 300..800)`, `F.mono(weight, italic)`, `F.ui(weight)`
  - class `VO`, with the `Lyrics` API plus `id/scene/act` on lines, `scenes`, `acts`, `duration`, `sceneAt(t)`, and
    static `wordProgress`/`lineCharProgress`
  - `SceneCtx.vo` (replaces `lyrics`)
  - `util.FPS = 30`, `frameIdx(t)` at 30 fps
  - `window.__film` (replaces `__pdoom`); the render script's default fps is 30 and its audio is
    `audio/mix/mix.wav`

- [ ] **Step 1: Vendor the engine at the pinned commit and copy the parts we keep**

```bash
git clone -q https://github.com/mexicat/PDoom-Video.git out/vendor/pdoom
git -C out/vendor/pdoom checkout -q bdbad537a7b7af3213475651774030c47568c181
V=out/vendor/pdoom/app
mkdir -p app/src/engine/glsl app/scripts app/public/fonts/stroke
cp $V/bun.lock $V/tsconfig.scripts.json $V/vite.config.ts $V/index.html app/
cp $V/src/main.ts app/src/
cp $V/src/engine/{audio,engine,gl,hud,lines,palette,post,scale,scene,stroke,type,util}.ts app/src/engine/
cp $V/src/engine/lyrics.ts app/src/engine/vo.ts
cp $V/src/engine/glsl/common.ts app/src/engine/glsl/
cp $V/scripts/render.ts app/scripts/
cp $V/public/fonts/stroke/* app/public/fonts/stroke/
```

`app/package.json`:
```json
{
  "name": "gitloom-film-app",
  "type": "module",
  "private": true,
  "scripts": {
    "dev": "vite",
    "test": "bun test src",
    "typecheck": "tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.scripts.json"
  },
  "devDependencies": {
    "@types/bun": "latest",
    "@types/opentype.js": "^1.3.10",
    "@types/three": "^0.186.0",
    "playwright-core": "^1.63.0",
    "typescript": "^7.0.2",
    "vite": "^8.3.0"
  },
  "dependencies": { "opentype.js": "^2.0.0", "three": "^0.186.0" }
}
```

`app/tsconfig.json` (the vendor's, with the tests excluded):
```json
{
  "compilerOptions": {
    "lib": ["ESNext", "DOM", "DOM.Iterable"],
    "target": "ESNext",
    "module": "ESNext",
    "moduleDetection": "force",
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": false,
    "noEmit": true,
    "strict": true,
    "skipLibCheck": true,
    "noFallthroughCasesInSwitch": true,
    "noImplicitOverride": true,
    "types": ["vite/client"]
  },
  "include": ["src"],
  "exclude": ["src/**/*.test.ts"]
}
```

Run: `cd app && bun install`
Expected: the dependencies install without errors.

- [ ] **Step 2: Write the failing tests**

`app/src/engine/palette.test.ts`:
```ts
import { expect, test } from 'bun:test';
import { HEX, LIN, rgba } from './palette';

test('GitLoom tokens replace the P(doom) palette', () => {
  expect(HEX.ink).toBe('#110d10');
  expect(HEX.blood).toBe('#c22b45');
  expect(HEX.moss).toBe('#4aad63');
  expect(Object.keys(HEX)).not.toContain('signal');
});

test('linear conversion and CSS colours', () => {
  const [r, g, b] = LIN.blood;
  expect(r).toBeCloseTo(0.5395, 3);
  expect(g).toBeCloseTo(0.0242, 3);
  expect(b).toBeCloseTo(0.0595, 3);
  expect(rgba('moss', 0.5)).toBe('rgba(74,173,99,0.5)');
});
```

`app/src/engine/vo.test.ts`:
```ts
import { expect, test } from 'bun:test';
import { VO } from './vo';

const data = {
  duration: 10,
  lines: [{
    id: 'L03', scene: 'ex', act: 'I', text: "It's not you... it's your vector store.", start: 1, end: 3,
    words: [
      { w: "It's", start: 1.0, end: 1.2 }, { w: 'not', start: 1.25, end: 1.4 }, { w: 'you...', start: 1.45, end: 1.8 },
      { w: "it's", start: 2.0, end: 2.2 }, { w: 'your', start: 2.25, end: 2.4 }, { w: 'vector', start: 2.45, end: 2.7 },
      { w: 'store.', start: 2.75, end: 3.0 },
    ],
  }],
  scenes: [{ id: 'ex', act: 'I', start: 0, end: 10 }],
  acts: [{ id: 'I', name: 'The Ex', start: 0, end: 10 }],
};

test('display text is typographic', () => {
  const vo = new VO(data);
  expect(vo.lines[0]!.text).toBe('It’s not you… it’s your vector store.');
  expect(vo.words[2]!.w).toBe('you…');
  expect(vo.lines[0]!.scene).toBe('ex');
});

test('lookup by content and by time', () => {
  const vo = new VO(data);
  expect(vo.get('vector store').id).toBe('L03');
  expect(() => vo.get('nope')).toThrow('line not found');
  expect(vo.wordAt(1.3)?.w).toBe('not');
  expect(vo.sceneAt(5)?.id).toBe('ex');
  expect(vo.duration).toBe(10);
});

test('word progress', () => {
  const w = new VO(data).words[0]!;
  expect(VO.wordProgress(w, 0.9)).toBe(0);
  expect(VO.wordProgress(w, 1.1)).toBeCloseTo(0.5);
  expect(VO.wordProgress(w, 2)).toBe(1);
});
```

`app/src/engine/type.test.ts`:
```ts
import { expect, test } from 'bun:test';
import { F } from './type';

test('font keys map to the static instances', () => {
  expect(F.display(75, 300)).toBe('Bricolage-750-300');
  expect(F.display(90, 650)).toBe('Bricolage-875-600');
  expect(F.mono(700)).toBe('JBMono-700');
  expect(F.mono(400, true)).toBe('JBMonoItalic-400');
  expect(F.ui(550)).toBe('Geist-500');
});
```

`app/src/engine/util.test.ts`:
```ts
import { expect, test } from 'bun:test';
import { FPS, frameIdx } from './util';

test('the film runs at 30 fps', () => {
  expect(FPS).toBe(30);
  expect(frameIdx(1)).toBe(30);
  expect(frameIdx(1 + 0.4 / 30)).toBe(30);
});
```

Run: `cd app && bun test src`
Expected: FAIL. The palette still has `signal`; `VO` isn't exported; `F.display` is undefined; `FPS` isn't
exported.

- [ ] **Step 3: Replace the palette**

`app/src/engine/palette.ts`:
```ts
import { hexToLinear } from './util';

// GitLoom's tokens (gitloom web/src/styles/tokens.css). The identity is a git diff: blood is the accent and `−`,
// moss is `+` and gain. Blood is never a surface fill, moss never decorates, and only the two of them may bloom.
export const HEX = {
  ink: '#110d10',
  ink2: '#161114',
  panel: '#1e181c',
  panel2: '#282027',
  rule: '#2b2229',
  ruleStrong: '#3e323b',
  bone: '#ede7ea',
  boneDim: '#a99fa5',
  boneFaint: '#6f6469',
  blood: '#c22b45',
  bloodBright: '#dc4a63',
  bloodDim: '#8e1f35',
  moss: '#4aad63',
  mossDim: '#1c3324',
} as const;

export type PaletteKey = keyof typeof HEX;

/** Linear RGB triplets for GL uniforms. */
export const LIN: Record<PaletteKey, [number, number, number]> = Object.fromEntries(
  Object.entries(HEX).map(([k, v]) => [k, hexToLinear(v)]),
) as Record<PaletteKey, [number, number, number]>;

/** CSS rgba() for Canvas2D. */
export function rgba(key: PaletteKey | string, a = 1): string {
  const hex = (HEX as Record<string, string>)[key] ?? key;
  const n = parseInt(hex.replace('#', ''), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
```

In `app/src/engine/glsl/common.ts`, replace the nine lines from `const vec3 C_INK = ${v3(LIN.ink)};` through
`const vec3 C_ACID = ${v3(LIN.acid)};` with:
```
const vec3 C_INK = ${v3(LIN.ink)};
const vec3 C_INK2 = ${v3(LIN.ink2)};
const vec3 C_PANEL = ${v3(LIN.panel)};
const vec3 C_RULE = ${v3(LIN.rule)};
const vec3 C_BONE = ${v3(LIN.bone)};
const vec3 C_BONE_DIM = ${v3(LIN.boneDim)};
const vec3 C_BONE_FAINT = ${v3(LIN.boneFaint)};
const vec3 C_BLOOD = ${v3(LIN.blood)};
const vec3 C_BLOOD_BRIGHT = ${v3(LIN.bloodBright)};
const vec3 C_BLOOD_DIM = ${v3(LIN.bloodDim)};
const vec3 C_MOSS = ${v3(LIN.moss)};
const vec3 C_MOSS_DIM = ${v3(LIN.mossDim)};
```
and replace the `heat` function (its doc comment through its closing brace) with:
```
/** Blood heat ramp for a glowing thread: 0 = ink, 0.5 = blood, 1 = white-hot. */
vec3 heat(float x) {
  x = sat(x);
  vec3 c = mix(C_INK, C_BLOOD_DIM, smoothstep(0.0, 0.3, x));
  c = mix(c, C_BLOOD, smoothstep(0.25, 0.55, x));
  c = mix(c, C_BLOOD_BRIGHT, smoothstep(0.55, 0.8, x));
  return mix(c, vec3(1.0, 0.92, 0.94), smoothstep(0.8, 1.0, x));
}
```

- [ ] **Step 4: Fonts, 30 fps, and the VO class**

In `app/src/engine/type.ts`, replace everything from the doc comment that begins `Font keys. Archivo comes in static width
instances` down to the closing `};` of `export const F = {…}` (the `nearest` function after it stays) with:
```ts
/**
 * Font keys. Bricolage Grotesque comes in static instances (w = wdth*10) x weights, so width animates in steps:
 * 750, 875, 1000 and weights 300/500/600/800 (cut at opsz 96 by tools/gitloom_film/fonts.py).
 */
export const BRICOLAGE_WIDTHS = [750, 875, 1000] as const;
export const BRICOLAGE_WEIGHTS = [300, 500, 600, 800] as const;

/** `features`: OpenType features switched on for the face (Canvas2D has no font-feature-settings). */
type FontDef = { family: string; file: string; features?: string };
const DEFS: FontDef[] = [];
for (const w of BRICOLAGE_WIDTHS) for (const wt of BRICOLAGE_WEIGHTS) DEFS.push({ family: `Bricolage-${w}-${wt}`, file: `Bricolage-w${w}-${wt}.ttf` });
for (const wt of [400, 500, 700]) DEFS.push({ family: `JBMono-${wt}`, file: `JetBrainsMono-${wt}.ttf` });
DEFS.push({ family: 'JBMonoItalic-400', file: 'JetBrainsMonoItalic-400.ttf' });
for (const wt of [400, 500, 600]) DEFS.push({ family: `Geist-${wt}`, file: `Geist-${wt}.ttf` });

/** Convenience family names. */
export const F = {
  /** Her voice: Bricolage at the nearest width (75..100 %) and weight (300..800). */
  display(width = 100, weight = 600): string {
    const w = nearest(BRICOLAGE_WIDTHS as unknown as number[], width * 10);
    const wt = nearest(BRICOLAGE_WEIGHTS as unknown as number[], weight);
    return `Bricolage-${w}-${wt}`;
  },
  /** The machine: JetBrains Mono 400/500/700, italic 400. */
  mono(weight = 400, italic = false): string {
    return italic ? 'JBMonoItalic-400' : `JBMono-${nearest([400, 500, 700], weight)}`;
  },
  /** UI chrome: Geist 400/500/600. */
  ui(weight = 400): string {
    return `Geist-${nearest([400, 500, 600], weight)}`;
  },
};
```

In `app/src/engine/util.ts`, replace the `frameIdx` doc comment and definition with:
```ts
/** The film's frame rate. */
export const FPS = 30;

/**
 * Index of the output frame nearest t, for per-frame jitter/flicker. Constant over a frame's whole motion-blur
 * shutter, so each frame shows one state (Math.floor(t * FPS) switches at the frame's own time, blending two
 * states in every frame).
 */
export const frameIdx = (t: number) => Math.round(t * FPS);
```

Replace `app/src/engine/vo.ts` (the copy of `lyrics.ts`) entirely with:
```ts
// Word-timed voiceover (data/vo.json, written by tools/ film-edit and film-snap) with queries for kinetic type.
import { smart } from './type';

export interface Word {
  w: string; // display token (punctuation attached, typographic: it’s, you…)
  start: number;
  end: number;
  syl?: [number, number][];
  /** filled in by VO: */
  line: number;
  index: number; // index within line
  gi: number; // global word index
}
export interface Line {
  i: number;
  id: string;
  scene: string;
  act: string;
  text: string;
  start: number;
  end: number;
  words: Word[];
}
export interface SceneSpan { id: string; act: string; start: number; end: number }
export interface ActSpan { id: string; name: string; start: number; end: number }

export class VO {
  lines: Line[];
  words: Word[];
  scenes: SceneSpan[];
  acts: ActSpan[];
  duration: number;

  constructor(j: { duration: number; lines: any[]; scenes: SceneSpan[]; acts: ActSpan[] }) {
    // display text gets curly apostrophes and the ellipsis; mono UI text that wants them straight uses plain()
    this.lines = j.lines.map((l, li) => ({
      ...l,
      i: li,
      text: smart(l.text),
      words: (l.words as any[]).map((w, wi) => ({ ...w, w: smart(w.w), line: li, index: wi, gi: 0 })),
    }));
    this.words = this.lines.flatMap((l) => l.words);
    this.words.forEach((w, i) => (w.gi = i));
    this.scenes = j.scenes;
    this.acts = j.acts;
    this.duration = j.duration;
  }

  static async load(): Promise<VO> {
    const r = await fetch('data/vo.json');
    if (!r.ok || !(r.headers.get('content-type') ?? '').includes('json')) throw new Error('data/vo.json not found: run film-edit');
    return new VO(await r.json());
  }

  /** The line being spoken at t (or null in gaps). */
  lineAt(t: number): Line | null {
    return this.lines.find((l) => t >= l.start && t < l.end) ?? null;
  }
  /** Most recent line that started at or before t. */
  lastLine(t: number): Line | null {
    let best: Line | null = null;
    for (const l of this.lines) if (l.start <= t) best = l;
    return best;
  }
  nextLine(t: number): Line | null {
    return this.lines.find((l) => l.start > t) ?? null;
  }
  linesIn(t0: number, t1: number): Line[] {
    return this.lines.filter((l) => l.end > t0 && l.start < t1);
  }
  /** The scene window containing t. */
  sceneAt(t: number): SceneSpan | null {
    return this.scenes.find((s) => t >= s.start && t < s.end) ?? null;
  }
  /** Lines whose text includes `s` (case-insensitive, straight or curly quotes). */
  find(s: string): Line[] {
    const q = fold(s);
    return this.lines.filter((l) => fold(l.text).includes(q));
  }
  /** First line containing `s`; throws if missing (fail loudly while authoring). */
  get(s: string, nth = 0): Line {
    const l = this.find(s)[nth];
    if (!l) throw new Error(`line not found: ${s}`);
    return l;
  }
  wordAt(t: number): Word | null {
    return this.words.find((w) => t >= w.start && t < w.end) ?? null;
  }
  lastWord(t: number): Word | null {
    let best: Word | null = null;
    for (const w of this.words) if (w.start <= t) best = w;
    return best;
  }
  /** Words whose normalized text matches (e.g. 'commit'). */
  findWords(s: string): Word[] {
    const q = norm(s);
    return this.words.filter((w) => norm(w.w) === q);
  }

  /** Spoken progress of a word at t: 0 before start, 1 after end, linear inside. */
  static wordProgress(w: Word, t: number): number {
    if (t <= w.start) return 0;
    if (t >= w.end) return 1;
    return (t - w.start) / Math.max(1e-3, w.end - w.start);
  }

  /** Progress through a whole line in characters (0..text.length), for per-glyph wipes. */
  static lineCharProgress(l: Line, t: number): number {
    let chars = 0;
    for (const w of l.words) {
      const p = VO.wordProgress(w, t);
      chars += p * w.w.length;
      if (p < 1) break;
      chars += 1; // the space
    }
    return Math.min(chars, l.text.length);
  }
}

export const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9()]/g, '');
const fold = (s: string) => s.toLowerCase().replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/…/g, '...');
```

Run: `cd app && bun test src`
Expected: 4 files, all tests pass.

- [ ] **Step 5: Strip P(doom) from the HUD, the post pass, the engine and the scene API**

Replace `app/src/engine/hud.ts` entirely with:
```ts
// Global overlay: the crop-mark frame. Off unless a scene asks for it (post.frame > 0).
import { Layer2D, W, H } from './gl';
import { rgba } from './palette';
import { clamp, ease, lerp } from './util';

export interface HudState {
  opacity: number;
  /** 0..1 the crop-mark frame: 1 in place, 0 flown out past the edges. */
  frame: number;
  /** 0..1: the frame is light — draw the marks in ink. */
  paper: number;
}

export class Hud {
  layer = new Layer2D();

  draw(_t: number, st: HudState) {
    const L = this.layer;
    L.clear();
    if (st.opacity > 0.001 && st.frame > 0.001) {
      L.ctx.globalAlpha = st.opacity;
      this.cropMarks(L.ctx, st.frame, st.paper > 0.5);
    }
    return L.upload();
  }

  /** Corner marks; as `k` drops they fly out along the diagonals and past the edges. */
  private cropMarks(c: CanvasRenderingContext2D, k: number, ink: boolean) {
    const e = ease.inOutCubic(clamp(k));
    c.save();
    c.globalAlpha *= clamp(k * 3);
    c.strokeStyle = ink ? rgba('ink', 0.45) : rgba('bone', 0.34);
    c.lineWidth = 1.25;
    const m = lerp(-40, 36, e), l = 22;
    c.beginPath();
    for (const [x, y, sx, sy] of [[m, m, 1, 1], [W - m, m, -1, 1], [m, H - m, 1, -1], [W - m, H - m, -1, -1]] as const) {
      c.moveTo(x + sx * l, y + 0.5 * sy); c.lineTo(x, y + 0.5 * sy); c.lineTo(x, y + sy * l);
    }
    c.stroke();
    c.restore();
  }
}
```

In `app/src/engine/post.ts`:
- Delete these four members from `PostParams`, including each member's doc comment:
  - `pdoom: number;`
  - `pdoomText?: string;`
  - `hudCorruption?: number;`
- Delete `pdoom: 0,` from `DEFAULT_POST`.
- Change the `hud` member's comment to `// HUD opacity multiplier (crop marks)`.

In `app/src/engine/scene.ts`, replace `import type { Lyrics } from './lyrics';` with `import type { VO } from './vo';`,
and replace `lyrics: Lyrics;` with `vo: VO;`.

In `app/src/engine/engine.ts`:
- Replace `import { Lyrics } from './lyrics';` with `import { VO } from './vo';`.
- Replace `import { Hud, PDoom, type Caption } from './hud';` with `import { Hud } from './hud';`.
- Add `import { FPS } from './util';`.
- In `TimelineEntry`, delete the `caption?: …` member and its doc comment.
- Replace `lyrics!: Lyrics;` with `vo!: VO;`.
- In the constructor signature, replace `(lyrics: Lyrics, audio: AudioData)` with `(vo: VO, audio: AudioData)`.
- Replace the whole `async init(…) {…}` method with:
  ```ts
  async init(only?: (e: TimelineEntry) => boolean) {
    [this.audio, this.vo] = await Promise.all([AudioData.load(), VO.load(), loadFonts(), loadStrokeFonts()]) as [AudioData, VO, void, void];
    this.timeline = this.makeTimeline(this.vo, this.audio);
    this.ctx = { renderer: this.renderer, audio: this.audio, vo: this.vo, comp: this.comp, W, H, id: '', params: {}, start: 0, end: 0 };
    this.post = new Post();
    this.hud = new Hud();
    const entries = only ? this.timeline.filter(only) : this.timeline;
    await Promise.all(entries.map((e) => this.loadEntry(e)));
  }
  ```
- Replace `get duration() { return this.audio.duration; }` with
  `get duration() { return Math.max(this.audio.duration, this.vo.duration); }`.
- In `render(`, replace the default `dt = 1 / 60` with `dt = 1 / FPS`.
- Replace the `const hudTex = this.hud.draw(…);` line with:
  `const hudTex = this.hud.draw(t, { opacity: this.hudOff ? 0 : post.hud, frame: post.frame, paper: post.paper });`

- [ ] **Step 6: Rename the player and export hooks; retune for 30 fps and our audio**

Run:
```bash
cd app
sed -i '' -e 's/__pdoom/__film/g' -e 's#1 / 60#1 / FPS#g' -e "s#audio/pdoom.mp3#audio/mix/mix.wav#" -e 's/engine\.lyrics\./engine.vo./' src/main.ts
perl -0pi -e "s|(import \{ makeTimeline \} from './timeline';)|\$1\nimport { FPS } from './engine/util';|" src/main.ts
grep -n "import { FPS } from './engine/util';" src/main.ts   # must print one line
sed -i '' -e 's/__pdoom/__film/g' -e 's/PDOOM_NO_HMR/FILM_NO_HMR/g' -e 's#audio/pdoom.mp3#audio/mix/mix.wav#' -e 's#out/pdoom.mp4#out/gitloom.mp4#g' \
  -e "s/opt('fps', '60')/opt('fps', '30')/" -e 's#1 / 60#1 / 30#g' -e 's/frames % 60/frames % 30/' -e 's/--fps 60/--fps 30/' -e '/^\/\/   plates:/d' scripts/render.ts
sed -i '' -e 's/PDOOM_NO_HMR/FILM_NO_HMR/g' vite.config.ts
sed -i '' -e "s#<title>I'm Upping My P(doom)</title>#<title>GitLoom — I Don't Forget. I Commit.</title>#" -e 's/#050505/#0b080a/g' -e 's/#eee9df/#ede7ea/g' \
  -e 's/#ff4d1222/#c22b4522/g' -e 's/#ff4d12/#c22b45/g' -e 's/#9c978f/#a99fa5/g' index.html
python3 - <<'EOF'
import re, pathlib
p = pathlib.Path("scripts/render.ts")
s = p.read_text()
s2 = re.sub(r"\} else if \(mode === 'plates'\) \{.*?\n  \} else if \(mode === 'perf'\) \{", "} else if (mode === 'perf') {", s, flags=re.S)
assert s2 != s, "plates block not found"
p.write_text(s2)
EOF
```

`app/src/timeline.ts` (a stub; Task 14 replaces it):
```ts
import type { TimelineEntry } from './engine/engine';
import type { VO } from './engine/vo';
import type { AudioData } from './engine/audio';

export function makeTimeline(_vo: VO, _audio: AudioData): TimelineEntry[] {
  return [];
}
```

- [ ] **Step 7: Verify that nothing of the old identity survives, then typecheck**

Run:
```bash
cd app
grep -rnE "pdoom|PDoom|[Ll]yrics|'(signal|ember|acid|graphite|ash)'|C_(SIGNAL|EMBER|ACID|GRAPHITE|ASH)|[Aa]rchivo|Cormorant|Plex-|F\.serif" src scripts vite.config.ts index.html || echo "clean"
bun test src && bun run typecheck
```
Expected: `clean`, then all tests pass, then `tsc` exits 0. Fix any file `tsc` names; the likely one is a leftover
`F.mono`/`F.serif` call in `hud.ts`, which Step 5 replaced.

- [ ] **Step 8: Commit**

```bash
cd .. && git add app
git commit -m "Engine forked from PDoom-Video and re-skinned: GitLoom palette, fonts, voiceover timing, 30 fps" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---

### Task 14: The timeline from the snapped edit, and the animatic card

**Files:**
- Create: `app/src/edit.ts`, `app/src/edit.test.ts`, `app/src/scenes/card.ts`
- Modify: `app/src/timeline.ts` (replace the stub), `app/src/engine/engine.ts` (add `file` to `TimelineEntry`)

**Interfaces:**
- Consumes: `VO` (`scenes`, `acts`, `lines`, `wordProgress`), `AudioData` (`beats`, `downbeats`), `F`, `font`,
  `layout`, `rgba`, `LIN`, `Layer2D`, `clearRT`, and `Scene`/`Frame`, all from Task 13.
- Produces:
  - `moduleFor(id: string, available: string[]) -> string`: the scene's own module id, or `'card'`
  - `entriesFrom(vo: {scenes}, available) -> {id, file, start, end, params: {scene, act, n}}[]`
  - `makeTimeline(vo, audio) -> TimelineEntry[]`
  - Scene module `card`: the animatic card. Plans 2 and 3 replace it scene by scene: adding
    `app/src/scenes/<id>.ts` is enough.

- [ ] **Step 1: Write the failing test**

`app/src/edit.test.ts`:
```ts
import { expect, test } from 'bun:test';
import { entriesFrom, moduleFor } from './edit';

const vo = { scenes: [{ id: 'thread', act: 'I', start: 0, end: 6.2 }, { id: 'ex', act: 'I', start: 6.2, end: 15 }] };

test('a scene plays its own module when one exists, else the card', () => {
  expect(moduleFor('thread', ['./scenes/card.ts', './scenes/thread.ts'])).toBe('thread');
  expect(moduleFor('ex', ['./scenes/card.ts'])).toBe('card');
});

test('entries mirror the snapped scene windows', () => {
  const e = entriesFrom(vo, ['./scenes/card.ts']);
  expect(e.map((x) => [x.id, x.file, x.start, x.end])).toEqual([['thread', 'card', 0, 6.2], ['ex', 'card', 6.2, 15]]);
  expect(e[1]!.params).toEqual({ scene: 'ex', act: 'I', n: 2 });
});
```

Run: `cd app && bun test src/edit.test.ts`
Expected: FAIL with `Cannot find module './edit'`.

- [ ] **Step 2: Implement `edit.ts` and the timeline**

`app/src/edit.ts`:
```ts
// Pure mapping from the snapped edit (data/vo.json scenes) to timeline entries. Kept free of Vite-only APIs so bun
// can test it.
import type { SceneSpan } from './engine/vo';

export function moduleFor(id: string, available: string[]): string {
  return available.includes(`./scenes/${id}.ts`) ? id : 'card';
}

export function entriesFrom(vo: { scenes: SceneSpan[] }, available: string[]) {
  return vo.scenes.map((s, i) => ({
    id: s.id, file: moduleFor(s.id, available), start: s.start, end: s.end,
    params: { scene: s.id, act: s.act, n: i + 1 },
  }));
}
```

Replace `app/src/timeline.ts` with:
```ts
// The edit: scene windows come from data/vo.json, where tools/ snapped them to the beat grid (film-snap). A scene
// whose module exists (scenes/<id>.ts) plays it; the others play the animatic card.
import type { TimelineEntry } from './engine/engine';
import type { SceneClass } from './engine/scene';
import type { VO } from './engine/vo';
import type { AudioData } from './engine/audio';
import { entriesFrom } from './edit';

const modules = import.meta.glob<{ default: SceneClass }>('./scenes/*.ts');

export function makeTimeline(vo: VO, _audio: AudioData): TimelineEntry[] {
  return entriesFrom(vo, Object.keys(modules)).map((e) => ({
    id: e.id, file: e.file, start: e.start, end: e.end, params: e.params,
    load: () => {
      const m = modules[`./scenes/${e.file}.ts`];
      return m ? m() : Promise.reject(new Error(`scene module not found: scenes/${e.file}.ts`));
    },
  }));
}
```

In `app/src/engine/engine.ts`, add this member to `interface TimelineEntry`, directly after `load`:
```ts
  /** Scene module file name, when it differs from the id (the animatic card); used by Vite HMR in preview. */
  file?: string;
```

- [ ] **Step 3: Write the card scene**

`app/src/scenes/card.ts`:
```ts
// Animatic card: one per scene until the scene's real module exists. It shows the act, the scene, what the picture
// will be, and her lines lighting word by word exactly as she says them, over a ruler of the scene's beats.
import type * as THREE from 'three';
import { Scene, type Frame } from '../engine/scene';
import { Layer2D, W, H, clearRT } from '../engine/gl';
import { LIN, rgba } from '../engine/palette';
import { F, font, layout } from '../engine/type';
import { VO, type Line } from '../engine/vo';
import type { AudioData } from '../engine/audio';

const PICTURE: Record<string, string> = {
  thread: 'A taut bone thread hums in the dark, frays on “forgets” and snaps on “zero”.',
  ex: 'A cloud of floats. Berlin is overwritten by Lisbon. git log: fatal, no commits yet.',
  her: 'The thread re-forms with blood and moss strands. Commit bead 3f9a1c2. The hero diff.',
  repo: 'cd ~/memory && ls · git log like beads · the memory file opens.',
  loom: 'Four warps: facts, incidents (gc), rules, skills. A shuttle weaves on every beat.',
  diff: '− Uses VS Code. + Uses neovim. Has since 2019. · gitloom diff … 8b21e04 3f9a1c2',
  cite: 'what editor do I use? → neovim, stitched to facts/people/user.md#editor · L11–14',
  braid: 'lexical · body · cues braid into one rope → the result card, millis: 82',
  merkle: '10,000 leaves. Fifty glow. Unchanged subtrees fold shut, skipped by hash.',
  graph: 'A wikilink draws an edge; a dangling link heals; k8s → kubernetes.',
  honest: 'Music out. The threads find nothing: memories: [] · “I don’t know.”',
  proof: '44 → 72 → 80 → 83 → 91.4% · LongMemEval · oracle split · 456/499',
  connect: 'claude mcp add gitloom … → ✔ Connected · MCP · codex · the SDK cards',
  anywhere: 'The one-line install · the console: Playground, Graph, Namespaces',
  weave: 'Every thread weaves the 3D GitLoom mark · gitloom 3f9a1c2 · gitloom.cloud',
};

export default class Card extends Scene {
  private layer = new Layer2D();

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const { renderer, comp, vo, audio } = this.ctx;
    const id = this.ctx.params.scene as string, n = this.ctx.params.n as number, act = this.ctx.params.act as string;
    clearRT(renderer, out, LIN.ink);
    const L = this.layer;
    L.clear();
    const c = L.ctx;
    c.textBaseline = 'alphabetic';

    c.font = font(F.mono(500), 15);
    c.letterSpacing = '3px';
    c.fillStyle = rgba('boneFaint');
    c.fillText(`ACT ${act} · ${(vo.acts.find((a) => a.id === act)?.name ?? '').toUpperCase()}`, 96, 120);
    c.letterSpacing = '0px';

    c.font = font(F.display(75, 800), 360);
    c.textAlign = 'right';
    c.fillStyle = rgba('bone', 0.06);
    c.fillText(String(n).padStart(2, '0'), W - 80, 400);
    c.textAlign = 'left';

    c.font = font(F.display(100, 600), 88);
    c.fillStyle = rgba('bone', 0.95);
    c.fillText(id, 96, 230);

    c.font = font(F.mono(400), 22);
    c.fillStyle = rgba('boneDim', 0.9);
    c.fillText(PICTURE[id] ?? '', 96, 290);

    this.lines(c, vo.lines.filter((l) => l.scene === id), f.t);
    this.ruler(c, f, audio);
    comp.draw(renderer, L.upload(), out);
    return { bloom: 0.4 };
  }

  /** Her lines, one per row: spoken words in bone, the word being spoken in bright blood, the rest dim. */
  private lines(c: CanvasRenderingContext2D, lines: Line[], t: number) {
    const size = 56, fam = F.display(100, 600);
    c.font = font(fam, size);
    lines.forEach((l, row) => {
      const y = 430 + row * 84;
      const lay = layout(l.text, fam, size);
      let from = 0;
      for (const w of l.words) {
        const at = l.text.indexOf(w.w, from);
        const gi = at >= 0 ? Array.from(l.text.slice(0, at)).length : 0;
        if (at >= 0) from = at + w.w.length;
        const p = VO.wordProgress(w, t);
        c.fillStyle = t < w.start ? rgba('bone', 0.28) : p < 1 ? rgba('bloodBright') : rgba('bone', 0.96);
        c.fillText(w.w, 96 + (lay.glyphs[gi]?.x ?? 0), y);
      }
    });
  }

  /** The scene's beats (downbeats taller), a playhead, and a dot that flashes on every beat. */
  private ruler(c: CanvasRenderingContext2D, f: Frame, audio: AudioData) {
    const x0 = 96, x1 = W - 96, y = H - 110;
    const X = (t: number) => x0 + ((t - f.start) / (f.end - f.start)) * (x1 - x0);
    c.fillStyle = rgba('rule');
    c.fillRect(x0, y, x1 - x0, 1);
    for (const b of audio.beats) {
      if (b < f.start || b > f.end) continue;
      const down = audio.downbeats.some((d) => Math.abs(d - b) < 1e-3);
      c.fillStyle = down ? rgba('boneDim', 0.9) : rgba('boneFaint', 0.8);
      c.fillRect(Math.round(X(b)), y - (down ? 14 : 7), 1, down ? 14 : 7);
    }
    c.fillStyle = rgba('blood');
    c.fillRect(Math.round(X(f.t)) - 1, y - 20, 2, 26);
    const pulse = Math.exp(-f.beatPhase * 7);
    c.beginPath();
    c.arc(W - 96, 115, 6 + 4 * pulse, 0, Math.PI * 2);
    c.fillStyle = rgba('blood', 0.35 + 0.65 * pulse);
    c.fill();
    c.font = font(F.mono(400), 15);
    c.fillStyle = rgba('boneFaint');
    c.textAlign = 'right';
    c.fillText(`${f.t.toFixed(2)}s · beat ${f.beat.toFixed(2)} · bar ${f.bar.toFixed(2)}`, W - 120, 120);
    c.textAlign = 'left';
  }
}
```

- [ ] **Step 4: Run the tests and typecheck**

Run: `cd app && bun test src && bun run typecheck`
Expected: all tests pass (5 files) and `tsc` exits 0.

- [ ] **Step 5: Render stills of four cards and look at them**

Run:
```bash
cd app
T=$(python3 -c "import json; v=json.load(open('../data/vo.json')); ls=v['lines']; print(','.join(f\"{(l['words'][0]['start']+l['words'][-1]['end'])/2:.2f}\" for l in (ls[0], ls[5], ls[20], ls[-1])))")
bun scripts/render.ts stills --t "$T" --out ../out/wip/card
```
Expected: four PNG paths, and no `SCENE ERRORS`. **Open each PNG with the Read tool** and check:
- the eyebrow reads `ACT I · THE EX` (and so on for the others);
- the scene id is large, with the picture line under it;
- the spoken words are bone, the current word is bright blood, the upcoming words are dim;
- the beat ruler shows ticks with taller downbeats and a blood playhead;
- the background is ink, with no pink or orange cast and nothing clipped at the edges.

Fix anything that's off before committing.

- [ ] **Step 6: Commit**

```bash
cd .. && git add app/src/edit.ts app/src/edit.test.ts app/src/timeline.ts app/src/scenes/card.ts app/src/engine/engine.ts
git commit -m "Timeline from the snapped edit, with an animatic card for every scene" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

---

### Task 15: Sync report, the animatic render, and checkpoint C3

**Files:**
- Create: `tools/gitloom_film/sync.py`, `tools/tests/test_sync.py`

**Interfaces:**
- Consumes: `data/vo.json`, `data/audio.json`, `load_script`.
- Produces:
  - `check(vo, audio, script) -> list[str]` (an empty list means the timing contract holds)
  - CLI `film-sync`, which exits 1 on any problem

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_sync.py`:
```python
from gitloom_film.sync import check

BEATS = [round(0.2 + 0.6 * k, 4) for k in range(160)]
AUDIO = {"beats": BEATS, "downbeats": BEATS[::4]}  # downbeats 0.2, 2.6, 5.0, 7.4, 9.8, …
SCRIPT = {"acts": [{"id": "I", "name": "A", "scenes": ["s1", "s2"]}, {"id": "II", "name": "B", "scenes": ["s3"]}]}


def good():
    line = lambda lid, s, t: {"id": lid, "scene": s, "start": t, "end": t + 1.0,  # noqa: E731
                              "words": [{"w": "a", "start": t + 0.04, "end": t + 0.9}]}
    return {"duration": 90.0, "lines": [line("L1", "s1", 1.0), line("L2", "s2", 4.0), line("L3", "s3", 9.0)],
            "scenes": [{"id": "s1", "start": 0.0, "end": 3.8}, {"id": "s2", "start": 3.8, "end": 7.4},
                       {"id": "s3", "start": 7.4, "end": 90.0}]}


def test_clean_edit_passes():
    assert check(good(), AUDIO, SCRIPT) == []


def test_off_beat_cut_and_act_off_downbeat_are_reported():
    vo = good()
    vo["scenes"][0]["end"] = vo["scenes"][1]["start"] = 3.9  # 100 ms after a beat
    vo["scenes"][1]["end"] = vo["scenes"][2]["start"] = 8.0  # a beat, but not a downbeat
    p = check(vo, AUDIO, SCRIPT)
    assert any("cut s2" in x and "off the beat" in x for x in p)
    assert any("cut s3" in x and "off the downbeat" in x for x in p)


def test_overlap_and_duration_are_reported():
    vo = good()
    vo["lines"][1]["start"] = 1.5
    vo["duration"] = 97.0
    p = check(vo, AUDIO, SCRIPT)
    assert any("L2 overlaps" in x for x in p) and any("duration" in x for x in p)


def test_line_outside_its_scene_is_reported():
    vo = good()
    vo["scenes"][1]["start"] = vo["scenes"][0]["end"] = 4.4  # cuts after L2's first word
    assert any("L2 is not inside its scene" in x for x in check(vo, AUDIO, SCRIPT))
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd tools && uv run pytest tests/test_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitloom_film.sync'`.

- [ ] **Step 3: Implement `sync.py`**

`tools/gitloom_film/sync.py`:
```python
"""Sync report: the spec's timing contract (§2), checked on data/vo.json and data/audio.json.

- every cut sits on a beat, and every act's first cut on a downbeat, within one frame;
- lines never overlap, words sit inside their line, and each line sits inside its scene;
- the film runs 85–95 s.
"""
import argparse
import json
import sys

import numpy as np

from .paths import DATA
from .vo import load_script

FRAME = 1 / 30


def check(vo: dict, audio: dict, script: dict) -> list[str]:
    problems = []
    beats, downs = np.asarray(audio["beats"]), np.asarray(audio["downbeats"])
    act_first = {a["scenes"][0] for a in script["acts"]}
    for s in vo["scenes"][1:]:
        on_down = s["id"] in act_first
        grid = downs if on_down else beats
        d = float(np.min(np.abs(grid - s["start"]))) if len(grid) else float("inf")
        if d > FRAME + 1e-9:
            problems.append(f"cut {s['id']} at {s['start']:.3f}s is {d * 1000:.0f} ms off the "
                            f"{'downbeat' if on_down else 'beat'}")
    prev_end = -np.inf
    scenes = {s["id"]: s for s in vo["scenes"]}
    for l in vo["lines"]:
        if l["start"] < prev_end - 1e-9:
            problems.append(f"{l['id']} overlaps the line before it")
        prev_end = l["end"]
        for w in l["words"]:
            if not l["start"] - 1e-6 <= w["start"] <= w["end"] <= l["end"] + 1e-6:
                problems.append(f"{l['id']} word {w['w']!r} lies outside its line")
        sc = scenes[l["scene"]]
        if not (sc["start"] <= l["words"][0]["start"] and l["words"][-1]["end"] <= sc["end"] + 1e-6):
            problems.append(f"{l['id']} is not inside its scene {sc['id']}")
    if not 85.0 <= vo["duration"] <= 95.0:
        problems.append(f"duration {vo['duration']:.2f}s is outside 85–95 s")
    return problems


def main(argv=None):
    argparse.ArgumentParser(description="Check the timing contract").parse_args(argv)
    problems = check(json.loads((DATA / "vo.json").read_text()), json.loads((DATA / "audio.json").read_text()),
                     load_script())
    for p in problems:
        print("✗", p)
    print("sync OK" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
```

- [ ] **Step 4: Run the tests to see them pass, then check the real edit**

Run: `cd tools && uv run pytest tests/test_sync.py -v && uv run pytest && uv run film-sync`

Expected: 4 passed; then the whole suite passes; then `sync OK`.

If `film-sync` reports an act cut **off the downbeat**, no downbeat fell between the previous scene's last word and
0.12 s before this scene's first word. Raise that line's `gap_before` in `data/edit.json` by one beat (0.6 s), then
re-run `film-edit`, `film-snap` and `film-mix`, and check again. Any other failure is a bug in Tasks 7–11: fix it
with a test first.

- [ ] **Step 5: Render the animatic and verify the file**

Run:
```bash
cd app && bun scripts/render.ts video --samples 1 --out ../out/animatic.mp4
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate -of compact ../out/animatic.mp4
bun scripts/render.ts sheet --cuts --cols 4 --out ../out/sheets/animatic-cuts.png
```
Expected:
- `wrote ../out/animatic.mp4 (N frames …)`
- ffprobe shows `h264` 1920×1080 at `30/1` plus an `aac` stream, with a duration equal to `data/vo.json` duration
  (±0.05 s)
- a contact sheet path

**Open the contact sheet with the Read tool.** Each cut should show the outgoing card on one side and the incoming
card on the other, and no frame should be black or red (a red frame means a scene failed to load).

- [ ] **Step 6: Commit**

```bash
cd .. && git add tools/gitloom_film/sync.py tools/tests/test_sync.py data
git commit -m "Sync report for the timing contract, and the first full animatic" -m "Co-Authored by MelloB's coding agent <build@mellob.in>"
```

- [ ] **Step 7: CHECKPOINT C3: stop and ask the user**

Run `open out/animatic.mp4` and ask the user to watch it for **pacing only**: gaps between lines, how long each
scene holds, where the music lands. Then apply their notes.
- **Gap or hold changes:** edit `data/edit.json`, then re-run `film-edit` → `film-snap` → `film-mix` → `film-sync`,
  and re-render the animatic.
- **If total length or act lengths move by more than a bar:** the score no longer fits its sections. Say so, and
  offer to regenerate it (`film-music --variants 2 --seed-base 41`, which returns to C2).
- **Take swaps:** update `audio/vo/selects.json`, then run the same chain.

Commit each round with the message `Pacing notes from C3, round N`. **Plan 1 is done when the user approves the
animatic's pacing.**

---

## After Plan 1

**Deferred on purpose:**
- **Plan 3:** the voiceover processing chain (§5.1), the sound effects (§5.3), the sung-hook variant (made by
  inpainting the chosen score's weave section) and the full mix.
- **Plan 4:** the stems and the ProRes master.

Plan 1's mix is the animatic mix only.

Plan 2 (look development) is written once C3 approves the pacing. It covers:
- style frames for every scene;
- Blender look-dev of the thread, the loom and the woven mark;
- the facts checker (spec §8.4).

Its inputs are the locked `data/vo.json`, `data/audio.json` and `audio/mix/mix.wav` from this plan.
