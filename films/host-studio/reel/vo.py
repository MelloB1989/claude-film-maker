"""The reel's voice: the lines of PLAN.md §2 (shots.LINES), spoken by ElevenLabs voices (one for him, one for her), a few takes
each, measured, the selects trimmed and placed on the master's frames.

    cd tools && uv run python ../films/host-studio/reel/vo.py takes [--only L1,L3] [--takes 3] [--voice ID]
    cd tools && uv run python ../films/host-studio/reel/vo.py measure [--only L1] [--align]
    cd tools && uv run python ../films/host-studio/reel/vo.py build          # selects -> line WAVs, stems, cues.json
    cd tools && uv run python ../films/host-studio/reel/vo.py cues [--wavs D] # cues.json again from the line WAVs alone

The key comes from $ELEVENLABS_API_KEY (fleet: `fleetctl secret exec ELEVENLABS_API_KEY=elevenlabs -- ...`). Takes are
idempotent (an existing WAV + JSON is never paid for twice) and land in out/host-studio/reel/vo/takes/<line>/
<voice>-<k>.wav; each take k has its own seed, so the same command makes the same takes again. `vo_selects.json` (next to
this file) names the take chosen for every line; `build` turns the selects into what the rest of the reel uses:

- out/host-studio/reel/vo/<line>.wav: the line alone, trimmed to 50 ms before the first word and 250 ms after the
  last, loudness matched, 48 kHz 24-bit mono (what `speech.to_face` solves into a face, perf.py);
- vo_him.wav, vo_her.wav, vo.wav: 65 s stems with every line at its frame (for the score's ducking and the mix);
- cues.json: per line the file, the master frame the file starts on, the frame the voice starts on, and every word's
  frames (the captions in post read it).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shots import BAR, FPS, LINES as SHOT_LINES  # noqa: E402

from filmtools.align import words_from_alignment, words_to_dicts  # noqa: E402
from filmtools.elevenlabs import ElevenLabs  # noqa: E402
from filmtools.wav import SR, pcm16_to_float, read_wav, write_wav  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "out" / "host-studio" / "reel" / "vo"
SELECTS = Path(__file__).with_name("vo_selects.json")
TOTAL = 26 * BAR  # 1560 frames, 65 s
SEED = 9600


@dataclass
class Line:
    id: str
    who: str        # "him" | "her"
    text: str
    start: int      # master frame the voice starts on (its first word)
    end: int        # master frame it should be done by
    mood: str       # speech.to_face mood and intensity (PLAN.md §2)
    intensity: float


# PLAN v2 §2 "Voice lines": the text and frames are shots.LINES (one source); the mood each is played in is here.
# Short, playful, confident: a tease, a wink, a hand-off, a sign-off. The delivery is in the words' punctuation.
MOODS = {"L1": ("CONFIDENCE", 0.7), "L2": ("HAPPINESS", 0.6), "L3a": ("HAPPINESS", 0.6), "L3b": ("CONFIDENCE", 0.8),
         "L4a": ("HAPPINESS", 0.6), "L4b": ("HAPPINESS", 0.8)}
LINES = [Line(i, who, text, f0, f1, *MOODS[i]) for i, who, f0, f1, text in SHOT_LINES]
BY_ID = {ln.id: ln for ln in LINES}

# The voices (ElevenLabs voice library). Him: warm, confident, a light Indian-English accent; her: warm and clear.
MODEL = "eleven_multilingual_v2"
SETTINGS = {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25, "use_speaker_boost": True}
VOICES = {
    "him": {"name": "tarun", "voice_id": "qr9D67rNgxf5xNgv46nx"},  # Tarun - Rich, Warm and Friendly
    "her": {"name": "tripti", "voice_id": "ET6E1GmpkG4a6Sotpwm3"},  # Tripti - Luxury TVC & Brand Films
}
# Auditioned for him and her (vo.py takes --voice <id>); the notes in REEL_PERF.md say how each one measured.
CANDIDATES = {
    "tarun": "qr9D67rNgxf5xNgv46nx", "ranbir": "9PvnT6XRzlljoaDG6Knu", "shrey": "x3gYeuNB0kLLYxOZsaSh",
    "tripti": "ET6E1GmpkG4a6Sotpwm3", "ziina": "FaqthkZu1EWxXxUFbAfb", "priyanka": "BpjGufoPiobT79j2vtj4",
}


def spoken(text: str) -> str:
    """What the voice is given: a leading ellipsis (a line that picks up the partner's) is for the captions only; read
    aloud it came back as a breathy artefact and a hole before the first word."""
    return text.lstrip("…").lstrip()


def take_path(line: str, voice: str, k: int) -> Path:
    return OUT / "takes" / line / f"{voice}-{k}.wav"


def voice_for(line: Line, override: str | None) -> dict:
    if override:
        name = next((n for n, v in CANDIDATES.items() if v == override or n == override), override)
        return {"name": name, "voice_id": CANDIDATES.get(name, override)}
    return VOICES[line.who]


def takes(client: ElevenLabs, only: set | None, n: int, voice: str | None, speed: float | None) -> int:
    made = 0
    for line in LINES:
        if only and line.id not in only:
            continue
        v = voice_for(line, voice)
        for k in range(1, n + 1):
            wav = take_path(line.id, v["name"], k)
            meta = wav.with_suffix(".json")
            if wav.exists() and meta.exists():
                if json.loads(meta.read_text())["text"] != line.text:
                    raise SystemExit(f"{wav} is a take of other words: move takes/{line.id} aside first")
                continue
            r = client.tts(v["voice_id"], spoken(line.text), MODEL, f"pcm_{SR}", speed=speed, seed=SEED + k, settings=SETTINGS)
            x = pcm16_to_float(r.audio)
            write_wav(wav, x, SR)
            meta.write_text(json.dumps({
                "line": line.id, "voice": v["name"], "voice_id": v["voice_id"], "take": k, "seed": SEED + k,
                "text": line.text, "model": MODEL, "settings": SETTINGS, "speed": speed, "duration": round(len(x) / SR, 4),
                "cost": r.cost, "request_id": r.request_id, "words": words_to_dicts(words_from_alignment(r.alignment)),
            }, indent=1))
            made += 1
            print(f"{line.id} {v['name']}-{k}: {len(x) / SR:.2f}s, {r.cost} credits")
    return made


# ---------------------------------------------------------------------------------------------------- measuring

def _frames(x: np.ndarray, n: int, hop: int) -> np.ndarray:
    m = 1 + max(0, len(x) - n) // hop
    return np.stack([x[i * hop:i * hop + n] for i in range(m)]) if len(x) >= n else x[None, :n]


def speech_span(x: np.ndarray, floor_db: float = -42.0) -> tuple[float, float]:
    """First and last moment the voice is above `floor_db` relative to its loudest 20 ms."""
    hop = SR // 100
    e = 10 * np.log10(np.mean(_frames(x, 2 * hop, hop) ** 2, axis=1) + 1e-12)
    on = np.where(e > e.max() + floor_db)[0]
    return on[0] * hop / SR, (on[-1] + 2) * hop / SR


def f0_track(x: np.ndarray) -> np.ndarray:
    """Pitch (Hz) of each voiced 40 ms frame, by normalised autocorrelation between 70 and 400 Hz."""
    n, hop = int(0.04 * SR), int(0.01 * SR)
    fr = _frames(x, n, hop)
    fr = fr - fr.mean(axis=1, keepdims=True)
    loud = np.sqrt(np.mean(fr ** 2, axis=1))
    lo, hi = SR // 400, SR // 70
    out = []
    for f, a in zip(fr, loud):
        if a < loud.max() * 0.08:
            continue
        spec = np.fft.rfft(f * np.hanning(n), 2 * n)
        ac = np.fft.irfft(np.abs(spec) ** 2)[:n]
        ac = ac / (ac[0] + 1e-12)
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > 0.45:
            out.append(SR / lag)
    return np.array(out)


def measure(path: Path) -> dict:
    x, _ = read_wav(path)
    meta = json.loads(path.with_suffix(".json").read_text())
    line = BY_ID[meta["line"]]
    t0, t1 = speech_span(x)
    words = meta["words"]
    gaps = [(round(b["start"] - a["end"], 2), a["w"]) for a, b in zip(words, words[1:]) if b["start"] - a["end"] > 0.12]
    f0 = f0_track(x[int(t0 * SR):int(t1 * SR)])
    semis = 12 * np.log2(np.percentile(f0, 90) / np.percentile(f0, 10)) if len(f0) > 10 else 0.0
    # brightness: the spectral centroid of the voiced part; a warm voice sits low
    spec = np.abs(np.fft.rfft(x[int(t0 * SR):int(t1 * SR)]))
    freqs = np.fft.rfftfreq(int(t1 * SR) - int(t0 * SR), 1 / SR)
    centroid = float((spec * freqs).sum() / (spec.sum() + 1e-12))
    # anything after the last word (a breath, a glitch) and clicks: 2 ms high-passed bursts far above the median
    tail = x[int(min(len(x) / SR, words[-1]["end"] + 0.2) * SR):]
    hp = np.diff(x)
    burst = np.sqrt(np.mean(_frames(hp, SR // 500, SR // 1000) ** 2, axis=1))
    slot = (line.end - line.start) / FPS
    dur = words[-1]["end"] - words[0]["start"]
    return {
        "take": f"{meta['voice']}-{meta['take']}", "line": line.id, "speech_s": round(dur, 2), "slot_s": round(slot, 2),
        "fit": round(dur / slot, 2), "wps": round(len(words) / dur, 2), "pauses": [(float(g), w) for g, w in gaps],
        "f0_hz": round(float(np.median(f0)), 1) if len(f0) else 0.0, "f0_range_st": round(float(semis), 1),
        "centroid_hz": round(centroid), "peak_db": round(20 * np.log10(np.abs(x).max() + 1e-12), 1),
        "tail_db": round(20 * np.log10(np.sqrt(np.mean(tail ** 2)) + 1e-12), 1) if len(tail) else -120.0,
        "clicks": int((burst > 12 * np.median(burst)).sum()), "lead_s": round(t0, 2), "align_loss": meta.get("align_loss"),
    }


def align(client: ElevenLabs, path: Path) -> float:
    """ElevenLabs' forced aligner on the take against its text (1 credit): a low loss means every word is clear."""
    meta = json.loads(path.with_suffix(".json").read_text())
    if meta.get("align_loss") is None:
        r = client.forced_alignment(path.read_bytes(), meta["text"].replace("…", ""), path.name)
        meta["align_loss"] = round(float(r.get("loss", 0.0)), 4)
        meta["align_words"] = [{"w": w["text"], "start": w["start"], "end": w["end"], "loss": round(w.get("loss", 0), 4)}
                               for w in r.get("words", [])]
        path.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    return meta["align_loss"]


def sheet(paths: list[Path], out: Path) -> None:
    """Waveform and spectrogram of every take, one row each: what an ear would catch (a glitch, a breath, a pause,
    a word running into the next), to look at."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(paths), 1, figsize=(16, 2.2 * len(paths)), squeeze=False)
    for ax, p in zip(axes[:, 0], paths):
        x, _ = read_wav(p)
        ax.specgram(x, NFFT=1024, Fs=SR, noverlap=768, cmap="magma", vmin=-130)
        ax.set_ylim(0, 8000)
        words = json.loads(p.with_suffix(".json").read_text())["words"]
        for w in words:
            ax.axvline(w["start"], color="cyan", lw=0.4)
            ax.text(w["start"], 7400, w["w"], color="white", fontsize=7)
        ax.set_ylabel(f"{p.parent.name}\n{p.stem}", fontsize=8)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=80)


# ---------------------------------------------------------------------------------------------------- the selects

def build() -> dict:
    """Selects -> trimmed, loudness-matched line WAVs placed on their frames, the stems and cues.json."""
    sel = json.loads(SELECTS.read_text())["selects"]
    stems = {w: np.zeros(TOTAL * SR // FPS, np.float32) for w in ("him", "her")}
    cues = {}
    for line in LINES:
        src = OUT / "takes" / line.id / f"{sel[line.id]}.wav"
        x, _ = read_wav(src)
        meta = json.loads(src.with_suffix(".json").read_text())
        t0, t1 = speech_span(x)
        a, b = max(0.0, t0 - 0.05), min(len(x) / SR, t1 + 0.25)
        y = x[int(a * SR):int(b * SR)].copy()
        fade = int(0.01 * SR)
        y[:fade] *= np.linspace(0, 1, fade)
        y[-fade:] *= np.linspace(1, 0, fade)
        # loudness: the voiced frames' RMS to -20 dBFS, the peak kept under -1 dBFS
        fr = _frames(y, SR // 50, SR // 100)
        rms = np.sqrt(np.mean(fr ** 2, axis=1))
        act = rms[rms > rms.max() * 0.1]
        y *= min(10 ** (-20 / 20) / np.sqrt(np.mean(act ** 2)), 10 ** (-1 / 20) / np.abs(y).max())
        out = OUT / f"{line.id}.wav"
        write_wav(out, y, SR)
        lead = t0 - a  # the voice starts this long into the file
        file_frame = line.start - lead * FPS
        i0 = int(round(file_frame / FPS * SR))
        stems[line.who][i0:i0 + len(y)] += y
        words = [{"w": w["w"], "start": round(line.start + (w["start"] - t0) * FPS, 1),
                  "end": round(line.start + (w["end"] - t0) * FPS, 1)} for w in meta["words"]]
        cues[line.id] = {"who": line.who, "text": line.text, "take": sel[line.id], "wav": out.name,
                         "file_frame": round(file_frame, 2), "voice_frame": line.start,
                         "end_frame": round(file_frame + len(y) / SR * FPS, 2), "slot_end": line.end,
                         "mood": line.mood, "intensity": line.intensity, "words": words}
        print(f"{line.id}: {sel[line.id]}, {len(y) / SR:.2f}s from f{file_frame:.1f}, last word ends f{words[-1]['end']}"
              f" (slot to f{line.end})")
    for w, s in stems.items():
        write_wav(OUT / f"vo_{w}.wav", s, SR)
    write_wav(OUT / "vo.wav", stems["him"] + stems["her"], SR)
    (OUT / "cues.json").write_text(json.dumps({"fps": FPS, "sr": SR, "frames": TOTAL, "lines": cues}, indent=1))
    return cues


CUES_V2 = Path(__file__).with_name("cues_v2.json")


def rebuild_cues(wavs: Path | None = None) -> dict:
    """cues.json again without the takes (round 3: only the line WAVs survived the move to the Linux box). Exact for
    what the frames need: `build` trims each take to 50 ms before its voice, so every line WAV starts 1.2 frames
    before its line's start frame (measured on the WAV in `wavs` when it is there, as build would). `end_frame`
    needs the WAV (else null). The words are lost with the takes' alignments: `words` is empty and `words_lost` says
    so (perf.py's word() falls back to its frames; the captions need `vo.py takes` + `build` again)."""
    cues = {}
    for line in LINES:
        lead, end_frame = 0.05, None
        w = (wavs / f"{line.id}.wav") if wavs else None
        if w and w.exists():
            y, _ = read_wav(w)
            lead = speech_span(y)[0]
            end_frame = round(line.start - lead * FPS + len(y) / SR * FPS, 2)
        cues[line.id] = {"who": line.who, "text": line.text, "take": json.loads(SELECTS.read_text())["selects"][line.id],
                         "wav": f"{line.id}.wav", "file_frame": round(line.start - lead * FPS, 2),
                         "voice_frame": line.start, "end_frame": end_frame, "slot_end": line.end, "mood": line.mood,
                         "intensity": line.intensity, "words": [], "words_lost": True}
    doc = {"fps": FPS, "sr": SR, "frames": TOTAL, "rebuilt": "vo.py cues (no takes)", "lines": cues}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cues.json").write_text(json.dumps(doc, indent=1))
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["takes", "measure", "build", "cues"])
    ap.add_argument("--only", help="comma-separated line ids")
    ap.add_argument("--takes", type=int, default=3)
    ap.add_argument("--voice", help="a CANDIDATES name or voice id instead of the line's presenter voice")
    ap.add_argument("--speed", type=float)
    ap.add_argument("--align", action="store_true", help="measure: also run the forced aligner (1 credit a take)")
    ap.add_argument("--wavs", type=Path, help="cues: a folder with the line WAVs (L1.wav ...) to measure")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    if a.cmd == "takes":
        print(takes(ElevenLabs(credit_log=OUT / "credits.log"), only, a.takes, a.voice, a.speed), "new takes")
    elif a.cmd == "measure":
        client = ElevenLabs(credit_log=OUT / "credits.log") if a.align else None
        paths = sorted(p for p in (OUT / "takes").glob("*/*.wav") if not only or p.parent.name in only)
        for p in paths:
            if client:
                align(client, p)
            print(json.dumps(measure(p), default=float))
        sheet(paths, OUT / "takes.png")
    elif a.cmd == "cues":
        doc = rebuild_cues(a.wavs)
        print(json.dumps({k: [c["file_frame"], c["end_frame"]] for k, c in doc["lines"].items()}))
    else:
        build()


if __name__ == "__main__":
    main()
