"""film-anime-depth: a depth map of a plate, for the engine's 2.5D parallax.

Depth Anything V2 (small, Apache-2.0, through transformers; Apple MPS when there is one, else the CPU) estimates the
plate's relative depth; it is normalised so the nearest 1 % of the frame is 1 and the farthest 1 % is 0, smoothed
(a parallax that follows every brush stroke shimmers), and written as a 16-bit grey PNG next to the plate:

    uv run film-anime-depth --film <id> --src assets/layers/ferry/plate.png [--out .../depth.png] [--smooth 4]

The engine's Parallax block displaces by it: white moves most, black stays put.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import cli, paths

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"


def estimate(rgb: np.ndarray, model: str = MODEL) -> np.ndarray:
    """Relative inverse depth (near is high) of an RGB uint8 image, float32 at the image's size."""
    import torch
    from PIL import Image
    from transformers import pipeline

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    pipe = pipeline("depth-estimation", model=model, device=dev)
    out = pipe(Image.fromarray(rgb))
    d = out["predicted_depth"]
    d = d.squeeze().float().cpu().numpy() if hasattr(d, "cpu") else np.asarray(d, dtype=np.float32)
    import cv2

    return cv2.resize(d, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_CUBIC)


def normalise(d: np.ndarray, smooth: float = 4.0) -> np.ndarray:
    """0 (far) .. 1 (near), by the 1st and 99th percentiles, smoothed by a `smooth` px Gaussian."""
    import cv2

    lo, hi = np.percentile(d, [1, 99])
    n = np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1).astype(np.float32)
    return cv2.GaussianBlur(n, (0, 0), smooth) if smooth > 0 else n


def depth_map(src: Path, out: Path, smooth: float = 4.0) -> Path:
    from PIL import Image

    rgb = np.asarray(Image.open(src).convert("RGB"))
    n = normalise(estimate(rgb), smooth)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((n * 65535 + 0.5).astype(np.uint16)).save(out)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = cli.parser(description="Estimate a plate's depth map (16-bit PNG, near = white).")
    ap.add_argument("--src", required=True, help="the plate, relative to the film folder")
    ap.add_argument("--out", help="default: depth.png beside the plate (or <stem>-depth.png)")
    ap.add_argument("--smooth", type=float, default=4.0)
    a = cli.parse(ap, argv)
    f = paths.current()
    src = f.path(a.src)
    out = f.path(a.out) if a.out else (src.with_name("depth.png") if src.stem == "plate" else src.with_name(f"{src.stem}-depth.png"))
    print(f.rel(depth_map(src, out, a.smooth)))
