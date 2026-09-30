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
from .music_plan import build_plan, to_chunks
from .paths import AUDIO, DATA, OUT, ROOT
from .wav import pcm16_to_float, read_wav, write_wav


def compose_with_fallback(client, plan: dict, seed: int) -> tuple[bytes, str]:
    """`plan` is the readable section plan; music_v2_5 takes a chunk plan, so that is what gets sent."""
    chunks = to_chunks(plan)
    try:
        return client.compose(chunks, output_format="pcm_48000", seed=seed).audio, "pcm_48000"
    except ElevenLabsError as e:
        if e.status != 403:
            raise
    return client.compose(chunks, output_format="mp3_44100_128", seed=seed).audio, "mp3_44100_128"


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
            (out_dir / f"{label}-seed{seed}.plan.json").write_text(
                json.dumps({"format": fmt, "plan": plan, "chunks": to_chunks(plan)}, indent=1))
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
