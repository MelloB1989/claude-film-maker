"""The explainers' music bed: one ElevenLabs Music take per film, sections keyed to the edit's beats (cues.json), then
trimmed to the film's length with a fade into the end card.

    PYTHONPATH=tools python films/host-studio/explainers/music.py gen --film whatsapp [--seed 1]   # spends credits
    PYTHONPATH=tools python films/host-studio/explainers/music.py fit --film whatsapp [--seed 1]   # -> audio/<film>/bed.flac

A bed, not a score: it sits under a voice for a minute, so no melody that fights the words, no drops, no vocals. The
hook gets a light opening, the body a steady modern pulse, the beat changes small lifts, and the closing line a
resolve that lands on the end card. Takes are cached under out/host-studio/explainers/music/ by their plan's hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from filmtools.wav import SR, read_wav, write_wav  # noqa: E402

MODEL = "music_v2_5"
TAKES = ROOT / "out" / "host-studio" / "explainers" / "music"

COMMON_POS = ["instrumental", "background music for a tech explainer video", "modern", "minimal", "clean",
              "premium", "warm", "subtle", "leaves room for a spoken voice", "steady tempo throughout",
              "high-end production", "soft dynamics"]
COMMON_NEG = ["vocals", "singing", "choir", "vocal chops", "spoken word", "rap", "humming", "lyrics", "EDM drop",
              "aggressive", "distorted", "harsh", "dubstep", "electric guitar solo", "epic trailer", "brass",
              "tempo change", "loud lead melody", "busy drums"]
STYLE = {
    "whatsapp": ["100 BPM", "4/4", "F major", "light future-garage and lo-fi electronic feel", "soft plucked synths",
                 "warm Rhodes chords", "muted kick", "soft clicks and shakers like messages arriving",
                 "round sub bass", "curious, friendly, optimistic"],
    "netflix": ["96 BPM", "4/4", "A minor", "cinematic modern electronic", "pulsing analog synth arpeggio",
                "soft felt piano", "warm wide pads", "gentle sub bass", "brushed electronic percussion",
                "smooth, confident, cinematic"],
}
# (section, first line, positive): a section runs from its first line's voice start (the first from 0) to the next's.
SECTIONS = {
    "whatsapp": [("Hook", None, ["sparse opening", "soft pads and a few plucks", "no drums", "intriguing"]),
                 ("Pulse", "W04", ["the muted kick and sub bass enter", "steady gentle groove", "plucks and Rhodes"]),
                 ("Lift", "W12", ["a gentle lift", "hi-hats join softly", "slightly fuller, still under a voice"]),
                 ("Resolve", "W16", ["the groove thins", "warm resolving chords", "ends on a held final chord"])],
    "netflix": [("Hook", None, ["sparse cinematic opening", "soft piano notes over a warm pad", "no drums"]),
                ("Pulse", "N04", ["the arpeggio and soft percussion enter", "steady forward motion", "sub bass"]),
                ("Lift", "N10", ["a gentle lift", "the arpeggio opens up", "slightly fuller, still under a voice"]),
                ("Resolve", "N15", ["the percussion drops out", "warm resolving chords",
                                    "ends on a held final chord"])],
}


def cues(film: str) -> dict:
    return json.loads((HERE / "audio" / film / "cues.json").read_text())


def plan(film: str) -> dict:
    c = cues(film)
    starts = {ln["id"]: ln["start"] for ln in c["lines"]}
    total = c["duration"] + 1.0  # a second spare for the fade
    bounds = [0.0 if a is None else starts[a] - 0.4 for _, a, _ in SECTIONS[film]] + [total]
    return {"chunks": [{
        "text": f"[{name}]", "duration_ms": int(round((bounds[i + 1] - bounds[i]) * 1000)),
        "positive_styles": COMMON_POS + STYLE[film] + pos, "negative_styles": COMMON_NEG,
        "context_adherence": "high", "conditioning_ref": None, "condition_strength": None,
    } for i, (name, _, pos) in enumerate(SECTIONS[film])]}


def take(film: str, seed: int) -> tuple[Path, str]:
    p = plan(film)
    h = hashlib.sha1(json.dumps({"p": p, "m": MODEL, "s": seed}, sort_keys=True).encode()).hexdigest()[:12]
    return TAKES / film / f"seed{seed}-{h}.wav", h


def gen(film: str, seed: int) -> Path:
    from filmtools.elevenlabs import ElevenLabs
    from filmtools.music import decode
    wav, h = take(film, seed)
    if wav.exists():
        print(f"{wav.name}: cached")
        return wav
    p = plan(film)
    secs = sum(c["duration_ms"] for c in p["chunks"]) / 1000
    r = ElevenLabs(credit_log=TAKES / "credits.jsonl").compose(p, model_id=MODEL, output_format="pcm_48000", seed=seed)
    x = decode(r.audio, "pcm_48000", secs)
    write_wav(wav, x)
    wav.with_suffix(".json").write_text(json.dumps({"film": film, "seed": seed, "hash": h, "model": MODEL,
                                                    "request_id": r.request_id, "seconds": round(len(x) / SR, 3),
                                                    "planned": secs, "plan": p}, indent=1))
    print(f"{film} seed {seed}: {len(x) / SR:.2f}s (planned {secs:.2f}) -> {wav}")
    return wav


def fit(film: str, seed: int) -> Path:
    """The take cut to the film's length: a 2 s fade that finishes on the last frame."""
    wav, _ = take(film, seed)
    if not wav.exists():  # the plan moved (a VO rebuild): the bed is kept, the newest take of this seed is used
        wav = max((TAKES / film).glob(f"seed{seed}-*.wav"), key=lambda p: p.stat().st_mtime)
    x, sr = read_wav(wav, mono=False)
    assert sr == SR
    x = np.stack([x, x], 1) if x.ndim == 1 else x
    n = int(round(cues(film)["duration"] * SR))
    y = np.zeros((n, 2), np.float32)
    y[:min(n, len(x))] = x[:n]
    f = 2 * SR
    y[-f:] *= np.linspace(1, 0, f)[:, None] ** 2
    out = HERE / "audio" / film / "bed.flac"
    write_wav(out, y)
    (out.with_suffix(".json")).write_text(json.dumps({"take": str(wav.relative_to(ROOT)), "seed": seed}, indent=1))
    print(f"{film}: bed {n / SR:.2f}s from {wav.name}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "fit", "plan"])
    ap.add_argument("--film", required=True, choices=sorted(SECTIONS))
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "gen":
        gen(a.film, a.seed)
    elif a.cmd == "fit":
        fit(a.film, a.seed)
    else:
        print(json.dumps(plan(a.film), indent=1))


if __name__ == "__main__":
    main()
