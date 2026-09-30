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
