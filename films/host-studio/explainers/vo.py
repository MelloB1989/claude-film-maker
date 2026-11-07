"""The explainers' voice: the lines of scripts.json, spoken by the karma reel's voices (him: Tarun, her: Tripti), a few
takes each, the selects trimmed, loudness matched and laid end to end on the explainer's timeline.

    PYTHONPATH=tools python films/host-studio/explainers/vo.py takes --film whatsapp [--only W01,W03] [--takes 2]
    PYTHONPATH=tools python films/host-studio/explainers/vo.py build --film whatsapp     # selects -> lines, vo, cues

The key comes from $ELEVENLABS_API_KEY (fleet: `fleetctl secret exec ELEVENLABS_API_KEY=elevenlabs -- ...`). Takes are
idempotent (an existing WAV + JSON is never paid for twice) and land in out/host-studio/explainers/vo/takes/<film>/
<line>/<voice>-<k>.wav. `selects.json` (next to this file) names the take for a line; a line it does not name uses take 1.
`build` writes, under films/host-studio/explainers/audio/<film>/:

- lines/<line>.wav: the line alone, 50 ms before its first word to 250 ms after its last, speech loudness matched,
  48 kHz 24-bit mono (what the face solves read);
- vo.wav: the whole explainer, every line at its place (the mix and the placeholder cut read it);
- cues.json: per line the beat, text, file, the timeline second and frame the file starts on, the voice's first and last
  word, and every word's start/end in seconds and frames (the edit, graphics, captions and face solves read it).

Pacing: lines inside a beat are GAP_LINE apart (word end to next word start), beats GAP_BEAT apart; the timeline opens
with LEAD of room before the first word and closes with TAIL after the last.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from filmtools.align import words_from_alignment, words_to_dicts  # noqa: E402
from filmtools.wav import SR, pcm16_to_float, read_wav, write_wav  # noqa: E402

SCRIPTS = json.loads((HERE / "scripts.json").read_text())
FPS = SCRIPTS["fps"]
TAKES = ROOT / "out" / "host-studio" / "explainers" / "vo" / "takes"
AUDIO = HERE / "audio"
SELECTS = HERE / "selects.json"
SEED = 6100

# The karma reel's voices (films/host-studio/reel/vo.py VOICES), so the presenters sound like themselves.
MODEL = "eleven_multilingual_v2"
VOICES = {
    "him": {"name": "tarun", "voice_id": "qr9D67rNgxf5xNgv46nx"},  # Tarun - Rich, Warm and Friendly
    "her": {"name": "tripti", "voice_id": "ET6E1GmpkG4a6Sotpwm3"},  # Tripti - Luxury TVC & Brand Films
}
# An explainer wants more evenness than the reel's teases (reel: stability 0.45, style 0.25): steadier, still warm.
SETTINGS = {"stability": 0.5, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True}
SPEED = {"him": 1.06, "her": 1.14}  # Tripti reads slow at 1.0 (2.2 words/s); an explainer wants ~2.5

PRE, POST = 0.05, 0.25           # trim around the words (s)
LEAD, TAIL = 0.8, 2.0            # room before the first word and after the last (s): the end card
GAP_LINE, GAP_BEAT = 0.34, 0.80  # word-to-word gaps between lines (s): a breath, and a beat change the graphics can land on
TARGET_DB = -20.0                # speech RMS (active frames) each line is matched to


def film(name: str) -> dict:
    return SCRIPTS["explainers"][name]


def take_path(f: str, line: str, voice: str, k: int) -> Path:
    return TAKES / f / line / f"{voice}-{k}.wav"


def takes(name: str, only: set | None, n: int) -> None:
    from filmtools.elevenlabs import ElevenLabs
    fl = film(name)
    v = VOICES[fl["presenter"]]
    client = ElevenLabs(credit_log=TAKES / "credits.jsonl")
    for line in fl["lines"]:
        if only and line["id"] not in only:
            continue
        for k in range(1, n + 1):
            wav = take_path(name, line["id"], v["name"], k)
            meta = wav.with_suffix(".json")
            if wav.exists() and meta.exists():
                if json.loads(meta.read_text())["text"] != line["text"]:
                    raise SystemExit(f"{wav} is a take of other words: move takes/{name}/{line['id']} aside first")
                continue
            r = client.tts(v["voice_id"], line["text"], MODEL, f"pcm_{SR}", speed=SPEED[fl["presenter"]],
                           seed=SEED + k, settings=SETTINGS)
            x = pcm16_to_float(r.audio)
            write_wav(wav, x, SR)
            meta.write_text(json.dumps({
                "line": line["id"], "voice": v["name"], "voice_id": v["voice_id"], "take": k, "seed": SEED + k,
                "text": line["text"], "model": MODEL, "settings": SETTINGS, "speed": SPEED[fl["presenter"]],
                "duration": round(len(x) / SR, 4), "cost": r.cost, "request_id": r.request_id,
                "words": words_to_dicts(words_from_alignment(r.alignment)),
            }, indent=1))
            print(f"{line['id']} {v['name']}-{k}: {len(x) / SR:.2f}s {len(line['text'].split())}w, {r.cost} credits")


def speech_rms_db(x: np.ndarray) -> float:
    """RMS (dBFS) over the 20 ms frames within 30 dB of the loudest: the speech, not the pauses."""
    hop = SR // 50
    m = len(x) // hop
    e = np.mean(x[:m * hop].reshape(m, hop) ** 2, axis=1) + 1e-12
    db = 10 * np.log10(e)
    return float(10 * np.log10(np.mean(e[db > db.max() - 30])))


def build(name: str) -> dict:
    fl = film(name)
    voice = VOICES[fl["presenter"]]["name"]
    sel = json.loads(SELECTS.read_text()).get(name, {}) if SELECTS.exists() else {}
    out = AUDIO / name
    pieces, t, prev_beat = [], LEAD - PRE, None
    for i, line in enumerate(fl["lines"]):
        k = int(sel.get(line["id"], 1))
        wav = take_path(name, line["id"], voice, k)
        meta = json.loads(wav.with_suffix(".json").read_text())
        x, sr = read_wav(wav)
        assert sr == SR, wav
        words = meta["words"]
        a = max(0.0, words[0]["start"] - PRE)
        b = min(len(x) / SR, words[-1]["end"] + POST)
        y = x[int(a * SR):int(b * SR)].copy()
        y *= 10 ** ((TARGET_DB - speech_rms_db(y)) / 20)
        fade = int(0.01 * SR)
        y[:fade] *= np.linspace(0, 1, fade)
        y[-fade:] *= np.linspace(1, 0, fade)
        if i:
            gap = GAP_BEAT if line["beat"] != prev_beat else GAP_LINE
            last_word_end = pieces[-1]["t"] + pieces[-1]["words"][-1]["end"]
            t = last_word_end + gap - PRE
        t = round(t * FPS) / FPS  # every file starts on a frame
        w = [{"w": d["w"], "start": round(d["start"] - a, 4), "end": round(d["end"] - a, 4)} for d in words]
        pieces.append({"line": line, "take": k, "y": y, "t": t, "words": w})
        prev_beat = line["beat"]
    end = pieces[-1]["t"] + pieces[-1]["words"][-1]["end"] + TAIL
    frames = int(np.ceil(end * FPS))
    vo = np.zeros(int(round(frames / FPS * SR)), np.float32)
    cues = {"film": name, "title": fl["title"], "presenter": fl["presenter"], "voice": voice, "fps": FPS,
            "frames": frames, "duration": round(frames / FPS, 4), "sr": SR, "vo": f"audio/{name}/vo.wav", "lines": []}
    for p in pieces:
        s0 = int(round(p["t"] * SR))
        vo[s0:s0 + len(p["y"])] += p["y"][:len(vo) - s0]
        write_wav(out / "lines" / f"{p['line']['id']}.wav", p["y"], SR)
        tw = [{"w": d["w"], "start": round(p["t"] + d["start"], 3), "end": round(p["t"] + d["end"], 3),
               "f0": int(np.floor((p["t"] + d["start"]) * FPS)), "f1": int(np.ceil((p["t"] + d["end"]) * FPS))}
              for d in p["words"]]
        cues["lines"].append({
            "id": p["line"]["id"], "beat": p["line"]["beat"], "text": p["line"]["text"], "take": p["take"],
            "file": f"audio/{name}/lines/{p['line']['id']}.wav", "file_start": round(p["t"], 4),
            "file_start_f": int(round(p["t"] * FPS)), "file_len": round(len(p["y"]) / SR, 4),
            "start": tw[0]["start"], "end": tw[-1]["end"], "start_f": tw[0]["f0"], "end_f": tw[-1]["f1"], "words": tw})
    peak = float(np.max(np.abs(vo)))
    if peak > 0.89:
        vo *= 0.89 / peak
    write_wav(out / "vo.wav", vo, SR)
    (out / "cues.json").write_text(json.dumps(cues, indent=1))
    print(f"{name}: {len(pieces)} lines, {cues['duration']:.2f}s ({frames} f), "
          f"{sum(len(p['line']['text'].split()) for p in pieces)} words")
    return cues


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["takes", "build"])
    ap.add_argument("--film", required=True, choices=sorted(SCRIPTS["explainers"]))
    ap.add_argument("--only")
    ap.add_argument("--takes", type=int, default=2)
    a = ap.parse_args()
    if a.cmd == "takes":
        takes(a.film, set(a.only.split(",")) if a.only else None, a.takes)
    else:
        build(a.film)


if __name__ == "__main__":
    main()
