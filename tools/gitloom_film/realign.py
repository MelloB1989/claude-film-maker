"""Re-time voiceover takes on the audio itself.

Eleven v4's own alignment snaps to an 80 ms grid and can sit ~180 ms off the audio. Forced alignment
(/v1/forced-alignment, 1 credit a take) measures each word on the take at 20 ms resolution. Our tokens (the script
text split on whitespace, with punctuation-only tokens merged into the word before) keep their display text; only
their times change. Idempotent: a take already marked `aligned` is skipped.
"""
import argparse
import json
from pathlib import Path

from .elevenlabs import ElevenLabs
from .paths import AUDIO


def _spoken(t: str) -> bool:
    return any(c.isalnum() for c in t)


def tokens(text: str) -> list[str]:
    out: list[str] = []
    for t in text.split():
        if _spoken(t) or not out:
            out.append(t)
        else:
            out[-1] += t
    return out


def map_words(toks: list[str], fa_words: list[dict]) -> list[dict]:
    spoken = [w for w in fa_words if _spoken(w["text"])]
    if len(spoken) != len(toks):
        raise ValueError(f"forced alignment found {len(spoken)} words, the text has {len(toks)}")
    return [{"w": t, "start": round(float(w["start"]), 4), "end": round(float(w["end"]), 4)}
            for t, w in zip(toks, spoken)]


def realign_take(client, wav: Path, meta_path: Path, log=print) -> str:
    meta = json.loads(meta_path.read_text())
    if meta.get("aligned") in ("forced", "tts-fallback"):
        return "skipped"
    d = client.forced_alignment(wav.read_bytes(), meta["text"], wav.name)
    try:
        meta["words"] = map_words(tokens(meta["text"]), d["words"])
        meta["aligned"] = "forced"
        meta["align_loss"] = round(float(d.get("loss", 0.0)), 4)
    except ValueError as e:
        meta["aligned"] = "tts-fallback"
        log(f"{meta['line']} take {meta['take']}: {e}; keeping the TTS times")
    meta_path.write_text(json.dumps(meta, indent=1))
    return meta["aligned"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Re-time voiceover takes with forced alignment")
    ap.add_argument("--only", help="comma-separated line ids")
    a = ap.parse_args(argv)
    only = set(a.only.split(",")) if a.only else None
    client = ElevenLabs(credit_log=AUDIO / "credits.log")
    counts: dict[str, int] = {}
    for tj in sorted((AUDIO / "vo" / "takes").glob("*/*.json")):
        if only and tj.parent.name not in only:
            continue
        r = realign_take(client, tj.with_suffix(".wav"), tj)
        counts[r] = counts.get(r, 0) + 1
    print(" · ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "no takes")
