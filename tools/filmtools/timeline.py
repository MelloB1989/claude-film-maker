"""The film's scene windows, for tools that cut, mix or deliver to picture.

The engine resolves film.ts into data/timeline.json, `{fps, duration, scenes: [{id, start, end}]}`
(`cd app && bun scripts/timeline.ts --film <id>`); it is the picture's truth. Without it, data/vo.json's scenes (the
voiceover's placement, film-edit and film-snap) stand in.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import paths


def load(data: Path | None = None) -> dict | None:
    """{"fps", "duration", "scenes", "source"} from timeline.json, else vo.json; None when neither exists. `source`
    names the file the windows came from."""
    data = Path(data) if data is not None else paths.current().data
    for name in ("timeline.json", "vo.json"):
        p = data / name
        if p.is_file():
            doc = json.loads(p.read_text())
            scenes = [{"id": s["id"], "start": float(s["start"]), "end": float(s["end"])} for s in doc["scenes"]]
            return {"fps": doc.get("fps"), "duration": float(doc["duration"]), "scenes": scenes,
                    "source": f"data/{name}"}
    return None


def require(data: Path | None = None) -> dict:
    """load(), or a SystemExit saying what writes the scene windows."""
    t = load(data)
    if t is None:
        raise SystemExit("no scene windows: neither data/timeline.json (cd app && bun scripts/timeline.ts --film <id>) "
                         "nor data/vo.json (film-edit) exists")
    return t
