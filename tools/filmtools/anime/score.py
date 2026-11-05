"""film-anime-score: a film's score as cues, each composed by ElevenLabs Music from a section plan and placed at a
film time.

A feature cue sheet rather than one long piece: the score comes in where the picture wants it and leaves room for the
silences between (a duel's held breath, a cut to nothing). films/<id>/data/score.json:

    { "model": "music_v2_5",
      "global": { "positive": [...], "negative": [...] },      every cue's styles
      "cues": { "<cue>": { "at": <film s>, "sections": [{ "name", "ms", "positive": [...], "negative": [...] }] } } }

    uv run film-anime-score --film <id> gen [--cues road,dawn] [--seed 1] [--force]
    uv run film-anime-score --film <id> list

`gen` writes audio/score/<cue>.wav (48 kHz stereo, 24-bit) and <cue>.json (the plan it was made from, its cost); a cue
is composed again only when its plan or seed changes, or with --force. The mix (film-anime-mix) places each cue at its
`at`.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .. import cli, paths
from ..elevenlabs import ElevenLabs, ElevenLabsError
from ..music import decode
from ..wav import write_wav


def sheet() -> dict:
    p = paths.current().data / "score.json"
    if not p.is_file():
        raise SystemExit(f"no cue sheet: {p} (see film-anime-score --help)")
    return json.loads(p.read_text())


def chunks_of(s: dict, cue: dict) -> dict:
    """The cue as music_v2's chunk plan: each section a chunk, with the global styles and its own."""
    g = s.get("global", {})
    return {"chunks": [{
        "text": f"[{sec['name']}]", "duration_ms": int(sec["ms"]),
        "positive_styles": g.get("positive", []) + sec.get("positive", []),
        "negative_styles": g.get("negative", []) + sec.get("negative", []),
        "context_adherence": sec.get("adherence", "high"), "conditioning_ref": None, "condition_strength": None,
    } for sec in cue["sections"]]}


def score_dir() -> Path:
    return paths.current().audio / "score"


def gen(names: list[str] | None, seed: int, force: bool) -> None:
    s = sheet()
    d = score_dir()
    d.mkdir(parents=True, exist_ok=True)
    el = ElevenLabs(credit_log=paths.current().audio / "credits.log")
    for name, cue in s["cues"].items():
        if names and name not in names:
            continue
        chunks = chunks_of(s, cue)
        h = hashlib.sha1(json.dumps({"c": chunks, "m": s.get("model"), "seed": seed}, sort_keys=True).encode()).hexdigest()[:12]
        wav, meta = d / f"{name}.wav", d / f"{name}.json"
        if not force and meta.is_file() and json.loads(meta.read_text()).get("hash") == h and wav.is_file():
            print(f"{name}: cached")
            continue
        secs = sum(c["duration_ms"] for c in chunks["chunks"]) / 1000
        before = el.credits_used()
        try:
            r = el.compose(chunks, model_id=s.get("model", "music_v2_5"), output_format="pcm_48000", seed=seed)
            fmt = "pcm_48000"
        except ElevenLabsError as e:
            if e.status != 403:
                raise
            r = el.compose(chunks, model_id=s.get("model", "music_v2_5"), output_format="mp3_44100_128", seed=seed)
            fmt = "mp3_44100_128"
        x = decode(r.audio, fmt, secs)
        write_wav(wav, x, 48000)
        cost = el.credits_used() - before
        sections, at = [], 0.0
        for c in chunks["chunks"]:
            sections.append({"name": c["text"].strip("[]"), "start": round(at, 3), "end": round(at + c["duration_ms"] / 1000, 3)})
            at += c["duration_ms"] / 1000
        meta.write_text(json.dumps({"hash": h, "seed": seed, "format": fmt, "seconds": round(len(x) / 48000, 3), "planned": secs,
                                    "cost": cost, "at": cue["at"], "sections": sections, "chunks": chunks}, indent=1))
        print(f"{name}: {len(x) / 48000:.2f}s (planned {secs:.2f}), {cost} credits ({fmt})")


def list_cues() -> None:
    s = sheet()
    for name, cue in s["cues"].items():
        m = score_dir() / f"{name}.json"
        got = json.loads(m.read_text()) if m.is_file() else None
        secs = sum(sec["ms"] for sec in cue["sections"]) / 1000
        print(f"{name:10} at {cue['at']:7.2f}s  {secs:6.2f}s  " + (f"made, {got['cost']} credits" if got else "not made"))


def main(argv: list[str] | None = None) -> None:
    ap = cli.parser(description="A film's score as composed cues placed at film times.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--cues", help="comma list (default: all)")
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--force", action="store_true")
    sub.add_parser("list")
    a = cli.parse(ap, argv)
    if a.cmd == "gen":
        gen(a.cues.split(",") if a.cues else None, a.seed, a.force)
    else:
        list_cues()
