"""LightCraft's headless CLI (getartcraft.com/apps/lightcraft, the open-source Lightroom-style raw developer), for
grading stills: photos for `films/<id>/assets/`, posters, thumbnails, social cuts.

`lightcraft-cli run --import <photo> --script <steps.jsonl>` opens the photo in an in-process session, runs the steps
(JSON lines `{"command": id, "params": {...}}`, ids from `lightcraft-cli commands`) and prints one result line per
step: `{"command", "ok", "result" | "error", "ms"}`. Develop controls and their ranges: `lightcraft-cli controls`.

What 0.9.1 does headless, measured on iPhone photos (docs/ARTCRAFT.md):
  - imports JPEG, PNG, TIFF, raw and HEIC (the release build decodes HEIC; orientation is applied on import);
  - an uncropped full-size export is the original to within rounding, but **its crop path resamples and softens**
    (the finest detail drops to ~60%) and its downscale is softer than Lanczos: grade here, crop and resize in
    PhotoCraft (`photocraft.crop_resize`);
  - mask coordinates are normalized to the uncropped, oriented photo;
  - the `sky` mask works without any model; `subject` / `object` / `prompt` need Meta's SAM 3 weights (a gated
    download) and `subject` without them is a centred blob: use radial spots (`spot`) instead;
  - a spot that brightens a person against the sky lights a band of sky round them (a halo): intersecting it with a
    luminance range below the sky's (`lum_hi` ~0.55) keeps it on the person.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .install import find_cli as _find


def find_cli(explicit=None):
    return _find("lightcraft", explicit)


class RunError(SystemExit):
    pass


def step(command: str, **params) -> dict:
    return {"command": command, "params": params}


def develop(values: dict) -> dict:
    """Set develop controls: {"light.exposure": 0.2, "mixer.blue.sat": 15, ...} (`lightcraft-cli controls`)."""
    return step("develop.set", values=dict(values))


def sky(values: dict) -> list:
    """A sky mask (no model needed) with local adjustments: exposure, saturation, temp, dehaze, ..."""
    return [step("mask.add", kind="sky", name="sky"), step("mask.adjust", values=dict(values))]


def spot(center, radius, values: dict, lum_hi: float | None = 0.85, feather: float = 75, name: str = "spot") -> list:
    """A radial mask at `center` ([x, y], 0..1 of the oriented photo) with radii `radius` (r or [rx, ry]),
    intersected with luminance 0..`lum_hi` so it stays off a brighter background (None: no intersection)."""
    rx, ry = (radius, radius) if isinstance(radius, (int, float)) else radius
    out = [step("mask.add", kind="radial", center=list(center), rx=rx, ry=ry, feather=feather, name=name)]
    if lum_hi is not None:
        out.append(step("mask.addComponent", op="intersect", kind="luminanceRange", lo=0.0, hi=lum_hi, hiFeather=0.12))
    out.append(step("mask.adjust", values=dict(values)))
    return out


def export_full(dest: Path, bit_depth: int = 16) -> dict:
    """The whole photo, uncropped, at native size, as a TIFF (the hand-off to PhotoCraft)."""
    return step("app.export", path=str(dest), longEdge=0, format="tiff", bitDepth=bit_depth, colorSpace="srgb",
                conflict="overwrite")


def run(cli: str, photo: Path, steps: list, workdir: Path, name: str = "steps.jsonl", timeout=900) -> list:
    """Run `steps` on `photo`; the result of each step, or a RunError naming the first that failed."""
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / name
    script.write_text("".join(json.dumps(s, separators=(",", ":")) + "\n" for s in steps))
    r = subprocess.run([cli, "run", "--import", str(photo), "--script", str(script)], capture_output=True, text=True,
                       timeout=timeout)
    res = []
    for line in r.stdout.splitlines():
        if line.startswith("{"):
            try:
                res.append(json.loads(line))
            except ValueError:
                pass
    bad = [x for x in res if not x.get("ok")]
    if bad or len(res) != len(steps) or r.returncode != 0:
        msg = bad[0] if bad else (r.stderr or r.stdout)[-600:]
        raise RunError(f"lightcraft-cli run on {photo.name} failed: {msg}")
    return res


def controls(cli: str) -> dict:
    """{control id: {"min", "max", "default", ...}} from `lightcraft-cli controls --json`."""
    r = subprocess.run([cli, "controls", "--json"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RunError(f"lightcraft-cli controls failed: {r.stderr or r.stdout}")
    d = json.loads(r.stdout)
    items = d.get("controls", d) if isinstance(d, dict) else d
    return {c["id"]: c for c in items} if isinstance(items, list) else items
