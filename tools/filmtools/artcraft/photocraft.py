"""PhotoCraft's headless CLI (getartcraft.com/apps/photocraft, the open-source Photoshop-style editor), for the
finishing half of a still: crop and resize, glow, light leak, sharpening, then a flat JPEG / PNG.

`photocraft-cli run <file> --cmd <id> --params <json> [--cmd ...] --out <file>` opens the file, runs engine commands
in order (ids from `photocraft-cli commands`), saves, and prints one `{"command", "result"}` line per command; an
unknown command or bad parameter exits 1 with `error: ...`. It reads HEIC, JPEG, PNG, TIFF (16-bit too), PSD.

Facts the helpers rely on (PhotoCraft 0.10.0, docs/ARTCRAFT.md):
  - `image.crop` with targetWidth / targetHeight crops and resamples in one step; `resample: "lanczos"` keeps the
    detail of a plain Lanczos resize (LightCraft's own crop + resize lost about half of it);
  - a linear gradient fill's `from` colour sits where `angle` points away from: -45 puts it in the top-left corner;
  - `layer.layerStyle.blendingOptions` acts on the active layer, which is the one a command just made.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .install import find_cli as _find


def find_cli(explicit=None):
    return _find("photocraft", explicit)


class RunError(SystemExit):
    pass


def crop_resize(rect, size, resample: str = "lanczos") -> list:
    """Crop `rect` (x, y, w, h in pixels) and resample it to `size` (w, h) in one step."""
    x, y, w, h = (int(v) for v in rect)
    return [["image.crop", {"x": x, "y": y, "width": w, "height": h, "targetWidth": int(size[0]),
                            "targetHeight": int(size[1]), "resample": resample}]]


def glow(radius: float, opacity: float, blend: str = "softLight") -> list:
    """A blurred copy of the image blended back over it (soft light: a gentle bloom without a haze)."""
    if opacity <= 0:
        return []
    return [["layer.duplicate", {"name": "glow"}], ["filter.blur.gaussianBlur", {"radius": radius}],
            ["layer.layerStyle.blendingOptions", {"blend": blend, "opacity": opacity}]]


def light_leak(color: str, opacity: float, angle: float = -45) -> list:
    """`color` fading to black across the frame from the corner `angle` points away from, screened over the image."""
    if opacity <= 0:
        return []
    return [["layer.newFillLayer.gradient", {"from": color, "to": "#000000", "angle": angle, "style": "linear"}],
            ["layer.layerStyle.blendingOptions", {"blend": "screen", "opacity": opacity}]]


def flatten() -> list:
    return [["layer.flattenImage", {}]]


def sharpen(amount: float, radius: float = 0.8, threshold: float = 3) -> list:
    """Output sharpening: once, last, after the resize."""
    return [["filter.sharpen.unsharpMask", {"amount": amount, "radius": radius, "threshold": threshold}]] if amount > 0 else []


def run(cli: str, src: Path, steps: list, out: Path, quality: int = 95, timeout=900) -> list:
    """Open `src`, run `steps` ([id, params] pairs), save `out` (format from its extension); each command's result."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [cli, "run", str(src)]
    for cid, params in steps:
        cmd += ["--cmd", cid, "--params", json.dumps(params, separators=(",", ":"))]
    fmt = out.suffix.lstrip(".").lower()
    cmd += ["--out", str(out), "--format", {"jpeg": "jpg", "tiff": "tif"}.get(fmt, fmt)]
    if out.suffix.lower() in (".jpg", ".jpeg", ".webp"):
        cmd += ["--quality", str(quality)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    res = []
    for line in r.stdout.splitlines():
        if line.startswith("{"):
            try:
                res.append(json.loads(line))
            except ValueError:
                pass
    if r.returncode != 0 or len(res) != len(steps) or not out.exists():
        raise RunError(f"photocraft-cli run on {src.name} failed: {(r.stderr or r.stdout).strip()[-600:]}")
    return res


def convert(cli: str, src: Path, out: Path, timeout=600) -> Path:
    """Any format PhotoCraft reads (HEIC too) to `out`'s format."""
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([cli, "convert", str(src), str(out)], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0 or not out.exists():
        raise RunError(f"photocraft-cli convert {src.name} failed: {(r.stderr or r.stdout).strip()[-600:]}")
    return out
