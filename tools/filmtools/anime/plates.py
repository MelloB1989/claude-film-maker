"""A film made of Blender plates: which shot file makes each scene, whether its plates are up to date, and how to run
Blender on it. film-anime-render and film-anime-review are built on this; it never imports bpy.

Each scene of data/timeline.json is made by films/<id>/blender/shots/<plate>.py, <plate> being the scene's id unless
data/plates.json names another ({"plates": {"standoff": "standoff_vroid"}}). A scene with no shot file yet plays as a
slate in the film (app PlateShot `missing`).

A plate is up to date when the stamp beside it (out/<id>/plates/<plate>/.stamp.json, written after a render whose scan
passed) carries the hash it would be rendered with now (`fingerprint`): the shot file and every module it imports from
the repo, followed through blender/lib/ and the film's blender/ (render.py and its own imports too), the files it loads
by name beside it (standoff_vroid.py loads standoff.py), the film's assets/ (its models; not assets/ref/, the
references), its scene's window in the timeline, its entry in the look schedule (data/look.json: the arc, the base and
its own, not the other shots'), film.json, and the render settings (mode, size, samples, engine).

Blender is $BLENDER, else Blender.app on macOS, else `blender` on the PATH (a fleet host's wrapper: source
.tools/env.sh).
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import paths

MAC_BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
STAMP = ".stamp.json"
# the render settings a mode stands for (blender/lib/cli.py MODES, with the cel plates' sample count for the final)
FINAL = {"mode": "final", "engine": "eevee", "samples": 32, "res": None}       # 4/3 the logical frame: 2560x1440
PREVIEW = {"mode": "preview", "engine": "eevee", "samples": 16, "res": None}   # half: 960x540


@dataclass(frozen=True)
class Scene:
    id: str
    start: float
    end: float
    plate: str          # the shot file's name (blender/shots/<plate>.py)
    path: Path          # that file
    f0: int
    f1: int

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    @property
    def mid(self) -> float:
        return (self.start + self.end) / 2


def first_frame_from(t: float, fps: float) -> int:
    """The first film frame at or after t (blender/lib/timing.py first_frame_from, the engine's ownedFrames)."""
    import math

    f = math.ceil(t * fps)
    while (f - 1) / fps >= t:
        f -= 1
    while f / fps < t:
        f += 1
    return f


def plate_map(film: paths.FilmPaths) -> dict[str, str]:
    p = film.data / "plates.json"
    return dict(json.loads(p.read_text()).get("plates", {})) if p.exists() else {}


def scenes(film: paths.FilmPaths, swap: dict | None = None) -> list[Scene]:
    """The film's scenes in order, each with the shot file that makes its plate (data/plates.json, then `swap`) and
    its window in film frames."""
    tl = json.loads((film.data / "timeline.json").read_text())
    fps = tl.get("fps") or json.loads(film.config.read_text()).get("fps", 30)
    pm = {**plate_map(film), **(swap or {})}
    out = []
    for s in tl["scenes"]:
        name = pm.get(s["id"], s["id"])
        out.append(Scene(s["id"], float(s["start"]), float(s["end"]), name, film.dir / "blender" / "shots" / f"{name}.py",
                         first_frame_from(s["start"], fps), first_frame_from(s["end"], fps)))
    return out


def fps_of(film: paths.FilmPaths) -> float:
    return json.loads((film.data / "timeline.json").read_text()).get("fps") or json.loads(film.config.read_text()).get("fps", 30)


# ---------------------------------------------------------------------------------------------------- the hash

def _module_file(name: str, roots: list[Path]) -> Path | None:
    """Where a dotted module lives under one of `roots` (a module file or a package's __init__.py), or None."""
    rel = Path(*name.split("."))
    for r in roots:
        for p in (r / rel.with_suffix(".py"), r / rel / "__init__.py"):
            if p.is_file():
                return p
    return None


def imports_of(path: Path, roots: list[Path]) -> set[Path]:
    """The repo files `path` imports (absolute, `from x import y` as module or as name, relative), and the .py files
    beside it it names in a string (loaded by hand: importlib's spec_from_file_location)."""
    tree = ast.parse(path.read_text(), str(path))
    pkg_root = next((r for r in roots if r in path.parents), None)
    pkg = ".".join(path.relative_to(pkg_root).with_suffix("").parts[:-1]) if pkg_root else ""
    out: set[Path] = set()

    def add(mod: str):
        p = _module_file(mod, roots)
        if p:
            out.add(p)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                parts = a.name.split(".")
                for i in range(1, len(parts) + 1):
                    add(".".join(parts[:i]))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                up = pkg.split(".") if pkg else []
                up = up[:len(up) - (node.level - 1)] if node.level > 1 else up
                base = ".".join([*up, *([base] if base else [])])
            if base:
                for i in range(1, len(base.split(".")) + 1):
                    add(".".join(base.split(".")[:i]))
            for a in node.names:
                add(f"{base}.{a.name}" if base else a.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".py"):
            p = path.with_name(Path(node.value).name)
            if p.is_file():
                out.add(p)
    out.discard(path)
    return out


def module_graph(start: list[Path], roots: list[Path]) -> list[Path]:
    """Every file reachable from `start` through imports_of, sorted."""
    seen: set[Path] = set()
    todo = [p.resolve() for p in start]
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        todo.extend(q.resolve() for q in imports_of(p, roots) if q.resolve() not in seen)
    return sorted(seen)


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def assets_of(film: paths.FilmPaths) -> list[Path]:
    """The film's assets a shot may load (its models): everything under assets/ but the references (assets/ref/)."""
    d = film.dir / "assets"
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*") if p.is_file() and "ref" not in p.relative_to(d).parts[:1]
                  and not p.name.startswith("."))


def look_entry(film: paths.FilmPaths, scene: str) -> dict:
    """What of the look schedule a scene's plate reads: the arc, the base and its own entry."""
    p = film.data / "look.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    return {"arc": d.get("arc"), "base": d.get("base"), "shot": (d.get("shots") or {}).get(scene)}


def fingerprint(film: paths.FilmPaths, sc: Scene, settings: dict, root: Path | None = None) -> dict:
    """The hash a scene's plate is rendered with now, and what went into it ({"hash", "files"})."""
    root = root or paths.ROOT
    roots = [root / "blender", film.dir / "blender"]
    files = module_graph([sc.path, root / "blender" / "render.py"], roots) + assets_of(film)
    h = hashlib.sha256()
    rel = []
    for p in files:
        r = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
        rel.append(r)
        h.update(f"{r}\0{_sha(p)}\n".encode())
    h.update(json.dumps({"window": [sc.f0, sc.f1], "scene": sc.id, "look": look_entry(film, sc.id),
                         "film": json.loads(film.config.read_text()), "settings": settings}, sort_keys=True).encode())
    return {"hash": h.hexdigest(), "files": rel}


def plates_dir(film: paths.FilmPaths, plate: str) -> Path:
    return film.out / "plates" / plate


def stamp(film: paths.FilmPaths, plate: str) -> dict | None:
    p = plates_dir(film, plate) / STAMP
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def write_stamp(film: paths.FilmPaths, plate: str, fp: dict, settings: dict) -> None:
    import time

    p = plates_dir(film, plate) / STAMP
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hash": fp["hash"], "settings": settings, "files": fp["files"],
                             "rendered": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1))


def up_to_date(film: paths.FilmPaths, sc: Scene, fp: dict) -> bool:
    s = stamp(film, sc.plate)
    return bool(s) and s.get("hash") == fp["hash"]


def clear_plates(film: paths.FilmPaths, plate: str) -> None:
    """Remove a plate's frames (and its stamp) before it is rendered anew: frames from an old window must not linger."""
    d = plates_dir(film, plate)
    if d.is_dir():
        shutil.rmtree(d)


# ---------------------------------------------------------------------------------------------------- Blender

def blender() -> str:
    """The Blender to run: $BLENDER, else Blender.app on macOS, else `blender` on the PATH."""
    if os.environ.get("BLENDER"):
        return os.environ["BLENDER"]
    if sys.platform == "darwin" and Path(MAC_BLENDER).exists():
        return MAC_BLENDER
    found = shutil.which("blender")
    if not found:
        raise SystemExit("no Blender: set $BLENDER, install Blender.app, or put `blender` on the PATH "
                         "(a fleet host: source /home/<you>/code/.tools/env.sh)")
    return found


def render_cmd(film_id: str, plate: str, settings: dict, frames: str | None = None, root: Path | None = None) -> list[str]:
    root = root or paths.ROOT
    cmd = [blender(), "-b", "-P", str(root / "blender" / "render.py"), "--", "--film", film_id, "--shot", plate,
           "--mode", settings["mode"], "--engine", settings["engine"]]
    if settings.get("samples"):
        cmd += ["--samples", str(settings["samples"])]
    if settings.get("res"):
        cmd += ["--res", settings["res"]]
    if frames:
        cmd += ["--frames", frames]
    return cmd


def scan_cmd(film_id: str, plate: str, expect_res: str | None = None, root: Path | None = None) -> list[str]:
    root = root or paths.ROOT
    cmd = [blender(), "-b", "-P", str(root / "blender" / "render.py"), "--", "--film", film_id, "--shot", plate, "--scan"]
    return cmd + (["--expect-res", expect_res] if expect_res else [])


def mode_res(film: paths.FilmPaths, settings: dict) -> str:
    """The plate size a setting renders (blender/lib/cli.py mode_res: half the logical frame, or 4/3 for a final)."""
    if settings.get("res"):
        return settings["res"]
    fmt = json.loads((film.data / "timeline.json").read_text()).get("format") or [1920, 1080]
    k = 4 / 3 if settings["mode"] == "final" else 0.5
    return f"{round(fmt[0] * k)}x{round(fmt[1] * k)}"
