"""film-init: scaffold a film's folder for the audio pipeline.

    film-init <id> [--title T] [--format landscape|vertical|square|portrait|cinema|WxH] [--fps 30] [--theme midnight]
                   [--bpm 120] [--force]

writes films/<id>/film.json (id, title, format, fps, theme, audio, and the pipeline section with its defaults spelt
out, the voice id left to fill in), data/script.json (a one-line stub in the shape film-vo and film-edit read),
data/ and audio/ with a .gitkeep each, and a .gitignore for the generated audio (takes, voiceover, scores, mixes,
the sound library's takes). It never writes film.ts or scenes: the engine owns those (copy
films/starter/film.ts, or start the film with `cd app && bun scripts/new.ts <id>`). An existing film.json or
script.json is kept unless --force.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from . import config, paths

ID = re.compile(r"[a-z0-9][a-z0-9_-]*")
THEMES = paths.APP / "src" / "engine" / "themes.json"
DEFAULT_THEME = "midnight"


def themes(path: Path = THEMES) -> list[str] | None:
    """The engine's theme presets, or None when the engine's list cannot be read."""
    try:
        return list(json.loads(path.read_text()))
    except (OSError, ValueError):
        return None


def parse_format(s: str):
    """A preset name, or WxH for {"width": W, "height": H}."""
    if s in config.FORMATS:
        return s
    m = re.fullmatch(r"(\d+)x(\d+)", s)
    if not m:
        raise argparse.ArgumentTypeError(f"--format: one of {', '.join(config.FORMATS)}, or WxH")
    return {"width": int(m.group(1)), "height": int(m.group(2))}


def film_json(fid: str, title: str | None = None, fmt="landscape", fps: int = 30, theme: str = DEFAULT_THEME,
              bpm: float = 120.0) -> dict:
    d = config.PIPELINE_DEFAULTS
    return {
        "id": fid,
        "title": title or fid.replace("-", " ").replace("_", " ").title(),
        "format": fmt,
        "fps": fps,
        "theme": theme,
        "audio": {"mix": "audio/mix/mix.wav", "analysis": "data/audio.json", "bpm": bpm, "offset": 0,
                  "beatsPerBar": 4},
        "vo": "data/vo.json",
        "pipeline": {
            "voice": {k: d["voice"][k] for k in ("provider", "name", "voice_id", "model", "speed", "key_file")}
            | {"voice_id": ""},
            "music": {"styles": d["music"]["styles"], "avoid": d["music"]["avoid"], "sections": [],
                      "temp": d["music"]["temp"]},
            "mix": {k: d["mix"][k] for k in ("lufs", "true_peak")},
            "deliver": {"outputs": d["deliver"]["outputs"]},
        },
    }


# what the pipeline writes that is paid for once and kept outside git (re-made, or restored from a backup):
# takes, paced takes, the assembled voice, scores, mixes and the sound library's takes
GITIGNORE = """\
# generated audio (tools/README.md): takes, voiceover, scores, mixes, the sound library's takes
audio/vo/takes/
audio/vo/paced/
audio/vo/vo.wav
audio/vo/vo-chain.wav
audio/music/
audio/mix/
audio/sfx/lib/
audio/sfx/*.wav
"""


def script_stub(title: str) -> dict:
    return {"title": title,
            "acts": [{"id": "1", "name": title, "scenes": ["open"]}],
            "lines": [{"id": "L01", "scene": "open", "text": "Replace this with the first line of the voiceover.",
                       "takes": 2}]}


def scaffold(fid: str, root: Path | None = None, force: bool = False, **opts) -> tuple[paths.FilmPaths, list[Path]]:
    """Make films/<fid>/ under `root` (default: the repo). Returns its paths and the files written."""
    if not ID.fullmatch(fid):
        raise SystemExit(f"film id {fid!r}: lowercase letters, digits, - and _ (a folder name)")
    fp = paths.film_paths(fid, root, must_exist=False)
    doc = film_json(fid, **opts)
    config.parse(doc, fp)  # what film-init writes, every tool reads
    written = []
    for d in (fp.data, fp.audio):
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not keep.exists():
            keep.write_text("")
            written.append(keep)
    for path, content in ((fp.config, doc), (fp.data / "script.json", script_stub(doc["title"]))):
        if path.exists() and not force:
            continue
        path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n")
        written.append(path)
    ignore = fp.dir / ".gitignore"
    if not ignore.exists():
        ignore.write_text(GITIGNORE)
        written.append(ignore)
    return fp, written


def main(argv=None):
    ap = argparse.ArgumentParser(prog="film-init", description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("id", nargs="?", help="the film's id: its folder name under films/ (or --film <id>)")
    ap.add_argument("--film", metavar="ID", help="the film's id, as every tool takes it")
    ap.add_argument("--title")
    ap.add_argument("--format", type=parse_format, default="landscape")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--theme", default=DEFAULT_THEME)
    ap.add_argument("--bpm", type=float, default=120.0)
    ap.add_argument("--force", action="store_true", help="overwrite an existing film.json and script.json")
    a = ap.parse_args(argv)
    fid = a.id or a.film
    if not fid:
        ap.error("name the film: film-init <id>")
    known = themes()
    if known is not None and a.theme not in known:
        ap.error(f"--theme: one of {', '.join(known)}")
    if a.fps <= 0 or a.bpm <= 0:
        ap.error("--fps and --bpm must be positive")
    fp, written = scaffold(fid, force=a.force, title=a.title, fmt=a.format, fps=a.fps, theme=a.theme, bpm=a.bpm)
    for p in written:
        print(f"wrote {p}")
    if not written:
        print(f"{fp.dir} is already scaffolded (--force rewrites film.json and script.json)")
    if not (fp.dir / "film.ts").exists():
        print(f"next: copy films/starter/film.ts to films/{fid}/film.ts (the engine owns the timeline and scenes), "
              f"set pipeline.voice.voice_id in films/{fid}/film.json, write data/script.json, then run the chain "
              f"with --film {fid} (tools/README.md)")
