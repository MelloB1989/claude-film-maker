"""EffectCraft's headless CLI, shared by every exporter (the AMV's `amv/effectcraft.py` builds on it).

`effectcraft-cli script <file.jsx>` runs a script on the embedded After Effects object model and saves an `.ecproj`;
`--project p.ecproj render-frame` renders one frame. Finding the binary: `install.find_cli("effectcraft")`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .install import find_cli as _find


def find_cli(explicit=None):
    return _find("effectcraft", explicit)


def run_script(cli, jsx: Path, timeout=1800):
    r = subprocess.run([cli, "script", str(jsx)], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def preview_frames(cli, project: Path, frames, out_dir: Path, max_side=640, comp=None):
    """Render `frames` (comp frames) headless at `max_side` px with the CLI."""
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for f in frames:
        dst = out_dir / f"f{f:04d}.png"
        cmd = [cli, "--project", str(project), "render-frame", "--frame", str(f), "--max-side", str(max_side),
               "--out", str(dst)]
        if comp:
            cmd[3:3] = ["--comp", comp]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"render-frame {f} failed: {r.stderr or r.stdout}")
        made.append(dst)
    return made
