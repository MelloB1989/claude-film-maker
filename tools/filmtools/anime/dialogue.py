"""film-anime-dialogue: a cast of voices speaking a script, placed on the picture, with the subtitles.

The script is films/<id>/data/dialogue.json:

    { "cast": { "<who>": { "voice_id", "model": "eleven_v3", "settings": {...}, "gain_db": 0 } },
      "lines": [ { "id", "who", "shot", "at", "ja", "tts", "en", "inner", "take", "splits" } ] }

`tts` is what the voice is given (the line with audio tags, readings spelt in kana); `ja` is the line as written, `en`
its subtitle (a list of parts with `splits`, the Japanese text each later part starts at, splits one line into several
subtitles at the moments those characters are spoken). `shot` and `at` place the line: it starts `at` s after the shot
starts (data/timeline.json, exported by the engine). `inner` marks an inner voice (V.O.): close, dry and a little
softened. `take` picks a take (default 0).

    uv run film-anime-dialogue --film <id> takes [--lines L01,L02] [--n 2] [--force]   ElevenLabs takes (cached)
    uv run film-anime-dialogue --film <id> place [--hold 0.35]                         the stem and the subtitles
    uv run film-anime-dialogue --film <id> list                                        takes, lengths, cost
    uv run film-anime-dialogue --film <id> check [--lines ...]                         transcribe the takes (Whisper)

`check` transcribes every take locally (openai/whisper-small through transformers) and compares it with the line: a
take that reads its audio tags aloud (Latin letters in Japanese speech) or strays from the line is flagged, so takes
can be chosen without listening to every one. `takes` writes audio/dialogue/takes/<id>.t<n>.wav (48 kHz mono, silence trimmed) and <id>.t<n>.json (the request, its
cost, the characters' times measured on the trimmed take); a take is made again only when its request changes, or
with --force. `place` writes audio/dialogue/dialogue.wav (the stem, film length), data/subs.json (the Subtitles
overlay's cues) and data/dialogue_timing.json (each line's placed start and end, for the score and the effects).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .. import cli, paths
from ..elevenlabs import ElevenLabs

SR = 48000


def script() -> dict:
    p = paths.current().data / "dialogue.json"
    if not p.is_file():
        raise SystemExit(f"no script: {p} (see film-anime-dialogue --help)")
    return json.loads(p.read_text())


def takes_dir() -> Path:
    return paths.current().audio / "dialogue" / "takes"


def request_of(line: dict, cast: dict) -> dict:
    who = cast[line["who"]]
    return {"voice_id": who["voice_id"], "model": who.get("model", "eleven_v3"), "settings": who.get("settings", {}),
            "text": line.get("tts") or line["ja"]}


def request_hash(req: dict, n: int) -> str:
    return hashlib.sha1(json.dumps({**req, "n": n}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def trim(x: np.ndarray, thresh_db: float = -46.0, pad: float = 0.03) -> tuple[np.ndarray, int]:
    """`x` without the silence before and after it (the first and last 10 ms window above `thresh_db`), padded by
    `pad` s; and how many samples came off the front."""
    w = int(0.01 * SR)
    n = len(x) // w
    if n == 0:
        return x, 0
    rms = np.sqrt(np.mean(x[: n * w].reshape(n, w) ** 2, axis=1) + 1e-12)
    on = np.nonzero(20 * np.log10(rms) > thresh_db)[0]
    if not len(on):
        return x, 0
    a = max(0, on[0] * w - int(pad * SR))
    b = min(len(x), (on[-1] + 1) * w + int(pad * SR))
    y = x[a:b].copy()
    f = int(0.004 * SR)
    y[:f] *= np.linspace(0, 1, f)
    y[-f:] *= np.linspace(1, 0, f)
    return y, a


def make_takes(lines: list[str] | None, n: int, force: bool) -> None:
    import soundfile as sf

    s = script()
    cast = s["cast"]
    d = takes_dir()
    d.mkdir(parents=True, exist_ok=True)
    el = ElevenLabs(credit_log=paths.current().audio / "dialogue" / "credits.jsonl")
    spent = 0
    for line in s["lines"]:
        if lines and line["id"] not in lines:
            continue
        req = request_of(line, cast)
        for k in range(n):
            wav, meta = d / f"{line['id']}.t{k}.wav", d / f"{line['id']}.t{k}.json"
            h = request_hash(req, k)
            if not force and meta.is_file() and json.loads(meta.read_text()).get("hash") == h and wav.is_file():
                continue
            r = el.tts(req["voice_id"], req["text"], model_id=req["model"], settings=req["settings"] or None, seed=k + 1)
            x = np.frombuffer(r.audio, dtype="<i2").astype(np.float32) / 32768.0
            y, cut = trim(x)
            sf.write(wav, y, SR, subtype="PCM_24")
            al = r.alignment or {}
            off = cut / SR
            chars = [{"c": c, "t0": round(t0 - off, 3), "t1": round(t1 - off, 3)} for c, t0, t1 in
                     zip(al.get("characters", []), al.get("character_start_times_seconds", []),
                         al.get("character_end_times_seconds", []))]
            meta.write_text(json.dumps({"hash": h, "request": req, "take": k, "seconds": round(len(y) / SR, 3),
                                        "cost": r.cost, "request_id": r.request_id, "chars": chars},
                                       ensure_ascii=False, indent=1))
            spent += r.cost
            print(f"{line['id']}.t{k}  {len(y) / SR:5.2f}s  {r.cost} credits  {req['text']}")
    print(f"spent {spent} credits")


def take_of(line: dict) -> tuple[np.ndarray, dict]:
    import soundfile as sf

    k = line.get("take", 0)
    wav, meta = takes_dir() / f"{line['id']}.t{k}.wav", takes_dir() / f"{line['id']}.t{k}.json"
    if not wav.is_file():
        raise SystemExit(f"{line['id']}: no take {k} ({wav}); run film-anime-dialogue takes")
    x, sr = sf.read(wav, dtype="float32")
    if sr != SR:
        raise SystemExit(f"{wav}: {sr} Hz, expected {SR}")
    return x, json.loads(meta.read_text())


def split_times(line: dict, meta: dict) -> list[float]:
    """When each later subtitle part starts (s into the take): the spoken start of each `splits` string's first
    character, found in the take's measured characters."""
    text = "".join(c["c"] for c in meta["chars"])
    out = []
    for s in line.get("splits", []):
        i = text.find(s)
        if i < 0:
            raise SystemExit(f"{line['id']}: split {s!r} is not in the spoken text {text!r}")
        out.append(meta["chars"][i]["t0"])
    return out


def inner_voice(x: np.ndarray) -> np.ndarray:
    """An inner voice: a touch softer and darker, with a short, close room (a few early reflections)."""
    from scipy.signal import butter, sosfilt

    y = sosfilt(butter(2, 6500, "low", fs=SR, output="sos"), x)
    room = np.zeros(int(0.09 * SR), np.float32)
    for dt, g in [(0.011, 0.32), (0.019, 0.22), (0.031, 0.15), (0.047, 0.1), (0.071, 0.06)]:
        room[int(dt * SR)] = g
    room[0] = 1.0
    return (np.convolve(y, room)[: len(y) + len(room) - 1] * 0.82).astype(np.float32)


def place(hold: float) -> None:
    import soundfile as sf

    f = paths.current()
    s = script()
    tl_p = f.data / "timeline.json"
    if not tl_p.is_file():
        raise SystemExit(f"no {tl_p}: export it (cd app && bun scripts/timeline.ts --film {f.id})")
    tl = json.loads(tl_p.read_text())
    shots = {sc["id"]: sc for sc in tl["scenes"]}
    stem = np.zeros(int((tl["duration"] + 1) * SR), np.float32)
    subs, timing = [], []
    for line in s["lines"]:
        if line["shot"] not in shots:
            raise SystemExit(f"{line['id']}: no shot {line['shot']!r} in the timeline")
        x, meta = take_of(line)
        who = s["cast"][line["who"]]
        x = x * 10 ** (who.get("gain_db", 0) / 20)
        if line.get("inner"):
            x = inner_voice(x)
        t0 = shots[line["shot"]]["start"] + line.get("at", 0)
        a = int(round(t0 * SR))
        b = min(len(stem), a + len(x))
        stem[a:b] += x[: b - a]
        t1 = t0 + len(x) / SR
        timing.append({"id": line["id"], "who": line["who"], "shot": line["shot"], "start": round(t0, 3), "end": round(t1, 3)})
        en = line.get("en") or ""
        if not en:
            continue
        parts = en if isinstance(en, list) else [en]
        starts = [t0] + [t0 + st for st in split_times(line, meta)]
        if len(starts) != len(parts):
            raise SystemExit(f"{line['id']}: {len(parts)} subtitle parts need {len(parts) - 1} splits")
        for i, (txt, st) in enumerate(zip(parts, starts)):
            end = starts[i + 1] - 0.05 if i + 1 < len(parts) else t1 + hold
            subs.append({"start": round(st - 0.05, 3), "end": round(end, 3), "text": txt, "ja": line["ja"], "who": line["who"]})
    out = f.audio / "dialogue" / "dialogue.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, stem[: int(tl["duration"] * SR)], SR, subtype="PCM_24")
    (f.data / "subs.json").write_text(json.dumps(subs, ensure_ascii=False, indent=1) + "\n")
    (f.data / "dialogue_timing.json").write_text(json.dumps(timing, indent=1) + "\n")
    print(f"{f.rel(out)}: {len(timing)} lines; data/subs.json: {len(subs)} subtitles")


def list_takes() -> None:
    s = script()
    total = 0
    for line in s["lines"]:
        for meta in sorted(takes_dir().glob(f"{line['id']}.t*.json")):
            m = json.loads(meta.read_text())
            total += m.get("cost", 0)
            mark = "*" if m["take"] == line.get("take", 0) else " "
            print(f"{mark} {line['id']}.t{m['take']}  {m['seconds']:5.2f}s  {m.get('cost', 0):4} cr  {line['ja']}")
    print(f"{total} credits")


def _norm(t: str) -> str:
    import re

    return re.sub(r"[\s、。，．,.!?！？「」『』…・〜~ー\-—]", "", t)


def check(lines: list[str] | None, model: str = "openai/whisper-small") -> None:
    """Transcribe each take and score it against its line (difflib ratio of the normalised texts)."""
    import difflib
    import re

    import librosa
    import soundfile as sf
    import torch
    from transformers import pipeline

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    asr = pipeline("automatic-speech-recognition", model=model, device=dev)
    s = script()
    for line in s["lines"]:
        if lines and line["id"] not in lines:
            continue
        for wav in sorted(takes_dir().glob(f"{line['id']}.t*.wav")):
            x, sr = sf.read(wav, dtype="float32")
            x = librosa.resample(x, orig_sr=sr, target_sr=16000)
            out = asr({"raw": x, "sampling_rate": 16000}, generate_kwargs={"language": "japanese", "task": "transcribe"})
            heard = out["text"].strip()
            score = difflib.SequenceMatcher(None, _norm(line["ja"]), _norm(heard)).ratio()
            flag = "TAGS?" if re.search(r"[A-Za-z]{3,}", heard) else ("CHECK" if score < 0.5 else "ok")
            print(f"{wav.stem:7} {flag:5} {score:4.2f}  {line['ja']}  |  {heard}")


def main(argv: list[str] | None = None) -> None:
    ap = cli.parser(description="Dialogue: takes from a cast of voices, placed on the picture, with subtitles.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("takes")
    t.add_argument("--lines", help="comma list of line ids (default: all)")
    t.add_argument("--n", type=int, default=2, help="takes per line")
    t.add_argument("--force", action="store_true")
    pl = sub.add_parser("place")
    pl.add_argument("--hold", type=float, default=0.35, help="s a subtitle stays after its line ends")
    sub.add_parser("list")
    ck = sub.add_parser("check")
    ck.add_argument("--lines", help="comma list of line ids (default: all)")
    a = cli.parse(ap, argv)
    if a.cmd == "takes":
        make_takes(a.lines.split(",") if a.lines else None, a.n, a.force)
    elif a.cmd == "place":
        place(a.hold)
    elif a.cmd == "check":
        check(a.lines.split(",") if a.lines else None)
    else:
        list_takes()
