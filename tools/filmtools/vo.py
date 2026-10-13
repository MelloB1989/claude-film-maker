"""Generate voiceover takes: one WAV + JSON per (line, take), with the voice set in film.json pipeline.voice.
Idempotent: a take whose WAV and JSON both exist is skipped, so an interrupted run resumes without paying twice.

data/script.json holds the lines: {"lines": [{"id", "scene", "text", "say"?, "takes"?, "optional"?}], "acts"?: [{"id",
"name", "scenes"}]}. Without acts, the scenes are one act, in the order the lines first name them. A line's `say` is
what the voice is sent instead of `text` (a respelling for pronunciation: "Maydha" for "Medha"); it must have as many
words as `text`, word for word, and the take keeps `text`'s words as its display text.
"""
import json
from pathlib import Path

from . import cli, config, paths
from .align import words_from_alignment, words_to_dicts
from .elevenlabs import ElevenLabs
from .wav import SR, pcm16_to_float, write_wav


def normalize_script(script: dict) -> dict:
    """The script with its acts: as written, or one act holding every scene in the order the lines name them."""
    if script.get("acts"):
        return script
    scenes = list(dict.fromkeys(line["scene"] for line in script.get("lines", [])))
    return {**script, "acts": [{"id": "1", "name": script.get("title", ""), "scenes": scenes}]}


def load_script(path: Path | None = None) -> dict:
    path = path or paths.current().data / "script.json"
    if not path.is_file():
        raise SystemExit(f"{path} is missing (film-init writes a stub)")
    return normalize_script(json.loads(path.read_text()))


def take_paths(root: Path, line_id: str, k: int) -> tuple[Path, Path]:
    return root / line_id / f"{k}.wav", root / line_id / f"{k}.json"


def spoken_text(line: dict) -> str:
    """What the voice is sent for a line: its `say` when set (as many words as its `text`), else its `text`."""
    say = line.get("say")
    if not say:
        return line["text"]
    from .realign import tokens  # realign imports this module
    if len(tokens(say)) != len(tokens(line["text"])):
        raise ValueError(f"{line['id']}: say has {len(tokens(say))} words, text has {len(tokens(line['text']))}; "
                         "respell word for word")
    return say


def display_words(line: dict, words: list[dict]) -> list[dict]:
    """A take's words with the line's `text` as their display text (the voice was sent its `say`)."""
    if not line.get("say"):
        return words
    from .realign import tokens
    toks = tokens(line["text"])
    if len(toks) != len(words):
        raise ValueError(f"{line['id']}: the voice's alignment has {len(words)} words, text has {len(toks)}")
    return [{**w, "w": t} for t, w in zip(toks, words)]


def generate_takes(lines, client, out_dir: Path, voice: dict, only: set[str] | None = None,
                   takes: int | None = None, log=print) -> int:
    """Every missing take of every line (or of `only`). `voice` is pipeline.voice: voice_id, model, output_format,
    speed, settings and seed."""
    made = 0
    fmt = voice.get("output_format", "pcm_48000")
    if fmt != f"pcm_{SR}":
        raise ValueError(f"voice output_format {fmt!r}: the pipeline runs on pcm_{SR} takes")
    sr = SR
    for line in lines:
        if only and line["id"] not in only:
            continue
        spoken = spoken_text(line)
        for k in range(1, (takes or line.get("takes", 2)) + 1):
            wav, meta = take_paths(out_dir, line["id"], k)
            if wav.exists() and meta.exists():
                continue
            r = client.tts(voice["voice_id"], spoken, voice["model"], fmt, speed=voice.get("speed"),
                           seed=voice.get("seed"), settings=voice.get("settings") or None)
            x = pcm16_to_float(r.audio)
            write_wav(wav, x, sr)
            words = display_words(line, words_to_dicts(words_from_alignment(r.alignment)))
            meta.write_text(json.dumps({
                "line": line["id"], "take": k, "text": line["text"], **({"say": spoken} if spoken != line["text"] else {}),
                "voice_id": voice["voice_id"], "model_id": voice["model"], "speed": voice.get("speed"), "seed": voice.get("seed"),
                "sr": sr,
                "duration": round(len(x) / sr, 4), "cost": r.cost, "request_id": r.request_id, "words": words,
            }, indent=1))
            made += 1
            log(f"{line['id']} take {k}: {len(x) / sr:.2f}s, {r.cost} credits")
    return made


def client_for(film: config.Film) -> ElevenLabs:
    """An ElevenLabs client with the film's key file, logging credits to the film's audio/credits.log."""
    if film.voice["provider"] != "elevenlabs":
        raise SystemExit(f"pipeline.voice.provider {film.voice['provider']!r}: only 'elevenlabs' is supported")
    return ElevenLabs(credit_log=film.paths.audio / "credits.log", key_file=film.voice["key_file"])


def main(argv=None):
    ap = cli.parser("Generate voiceover takes with the film's voice (film.json pipeline.voice)")
    ap.add_argument("--only", help="comma-separated line ids")
    ap.add_argument("--takes", type=int, help="takes per line (default: script.json, else 2)")
    ap.add_argument("--speed", type=float, help="voice speed (default: pipeline.voice.speed)")
    a = cli.parse(ap, argv)
    film = config.load()
    voice = {**film.voice, "voice_id": film.require("voice", "voice_id")}
    if a.speed is not None:
        voice["speed"] = a.speed
    n = generate_takes(load_script()["lines"], client_for(film), film.paths.audio / "vo" / "takes", voice,
                       set(a.only.split(",")) if a.only else None, a.takes)
    print(f"{n} new takes")
