"""film-anime-clips: generated clips conformed to the film: its frame size and rate, sharpened a little, trimmed.

A generation service hands back clips at its own size (768p, 720p) and sometimes its own rate. The engine's Video
block plays a clip from frames extracted at the film's rate (app/scripts/media.ts), scaling each as it draws; this
conforms the clip first, so the scaling is done once, well (Lanczos, a light unsharp to put back the line art's edge),
and the frames the engine reads are the film's size:

    uv run film-anime-clips --film <id> --src assets/gen/clip-walk.mp4 [--name walk] [--from 0] [--to 5.5]
        [--crop x,y,w,h] [--sharpen 0.45]
    uv run film-anime-clips --film <id> --all           every assets/gen/clip-*.mp4, named without the 'clip-'

writes assets/clips/<name>.mp4 (H.264, crf 12, the film's fps and size). --crop takes fractions of the source frame
(a reframe: 0.1,0,0.8,0.8 is a push into its upper middle); without it the clip is scaled to cover the frame, its
overhang cropped evenly. Then extract its frames: cd app && bun scripts/media.ts --film <id> --src assets/clips/<name>.mp4
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .. import cli, paths
from ..config import FORMATS


def film_size_fps() -> tuple[int, int, int]:
    cfg = json.loads(paths.current().config.read_text())
    fmt = cfg.get("format", "landscape")
    w, h = (fmt["width"], fmt["height"]) if isinstance(fmt, dict) else FORMATS[fmt]
    return w, h, int(cfg.get("fps", 30))


def conform(src: Path, out: Path, *, t0: float | None = None, t1: float | None = None,
            crop: tuple[float, float, float, float] | None = None, sharpen: float = 0.45) -> Path:
    w, h, fps = film_size_fps()
    vf = []
    if crop:
        x, y, cw, ch = crop
        vf.append(f"crop=iw*{cw}:ih*{ch}:iw*{x}:ih*{y}")
    vf += [f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos", f"crop={w}:{h}", f"fps={fps}"]
    if sharpen > 0:
        vf.append(f"unsharp=5:5:{sharpen}:5:5:0")
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if t0 is not None:
        cmd += ["-ss", f"{t0}"]
    cmd += ["-i", str(src)]
    if t1 is not None:
        cmd += ["-t", f"{t1 - (t0 or 0)}"]
    cmd += ["-an", "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p", str(out)]
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = cli.parser(description="Conform generated clips to the film's size and rate.")
    ap.add_argument("--src", help="a clip, relative to the film folder")
    ap.add_argument("--all", action="store_true", help="every assets/gen/clip-*.mp4")
    ap.add_argument("--name", help="the conformed clip's name (default: the source's, without 'clip-')")
    ap.add_argument("--from", dest="t0", type=float)
    ap.add_argument("--to", dest="t1", type=float)
    ap.add_argument("--crop", help="x,y,w,h fractions of the source frame")
    ap.add_argument("--sharpen", type=float, default=0.45)
    a = cli.parse(ap, argv)
    f = paths.current()
    if a.all:
        srcs = sorted((f.dir / "assets" / "gen").glob("clip-*.mp4"))
    elif a.src:
        srcs = [f.path(a.src)]
    else:
        raise SystemExit("--src or --all")
    crop = tuple(float(v) for v in a.crop.split(",")) if a.crop else None
    for s in srcs:
        name = a.name if (a.name and len(srcs) == 1) else s.stem.removeprefix("clip-")
        out = conform(s, f.dir / "assets" / "clips" / f"{name}.mp4", t0=a.t0, t1=a.t1, crop=crop, sharpen=a.sharpen)  # type: ignore[arg-type]
        print(f.rel(out))
