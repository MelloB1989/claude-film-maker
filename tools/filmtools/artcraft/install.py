"""Find and install ArtCraft's release binaries without sudo: FilmCraft, EffectCraft, LightCraft, PhotoCraft.

Each app's Linux tarball (github.com/storytold/<app>/releases) holds `bin/<app>` (the GUI) and `bin/<app>-cli` (the
headless engine this repo drives). They are unpacked into `<tools dir>/<app>-<version>-linux-<arch>/`; the tools dir is
$ARTCRAFT_HOME, else the shared `film-making/bin/artcraft` when that folder exists (every machine on the shared code
path sees it), else `~/.local/share/artcraft`. The download is checked against the release's SHA256SUMS.txt.

    python -m filmtools.artcraft install [filmcraft|effectcraft|lightcraft|photocraft|all] [--version v0.8.0]
    python -m filmtools.artcraft status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

APPS = {"filmcraft": "storytold/filmcraft", "effectcraft": "storytold/effectcraft", "lightcraft": "storytold/lightcraft",
        "photocraft": "storytold/photocraft"}
SHARED_BIN = Path("/home/nikhil/code/film-making/bin")
ENV = {app: f"{app.upper()}_CLI" for app in APPS}


def tools_dir() -> Path:
    if os.environ.get("ARTCRAFT_HOME"):
        return Path(os.environ["ARTCRAFT_HOME"])
    if SHARED_BIN.is_dir():
        return SHARED_BIN / "artcraft"
    return Path.home() / ".local" / "share" / "artcraft"


def arch() -> str:
    m = platform.machine().lower()
    return {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64", "riscv64": "riscv64"}.get(m, m)


def _version_key(name: str):
    m = re.search(r"-(\d+)\.(\d+)\.(\d+)-", name)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def find_cli(app: str, explicit: str | None = None, home: Path | None = None) -> str | None:
    """The `<app>-cli` binary: `explicit`, $<APP>_CLI (e.g. $FILMCRAFT_CLI), PATH, then the newest install under the
    tools dir (and the older /tmp/ec-bin location EffectCraft was first unpacked to)."""
    for c in (explicit, os.environ.get(ENV[app]), shutil.which(f"{app}-cli")):
        if c and Path(c).exists():
            return str(c)
    roots = [home or tools_dir()]
    if app == "effectcraft":
        roots.append(Path("/tmp/ec-bin"))
    for r in roots:                    # the tools dir wins; the older unpack location only when it holds nothing
        found = sorted((p for p in r.glob(f"{app}-*/bin/{app}-cli") if p.is_file()),
                       key=lambda p: _version_key(p.parent.parent.name + "-"))
        if found:
            return str(found[-1])
    return None


def cli_version(cli: str) -> str | None:
    try:
        r = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"(\d+\.\d+\.\d+)", r.stdout + r.stderr)
    return m.group(1) if m else None


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "claude-film-maker"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def latest_tag(app: str) -> str:
    return json.loads(_get(f"https://api.github.com/repos/{APPS[app]}/releases/latest"))["tag_name"]


def install(app: str, version: str | None = None, home: Path | None = None, log=print) -> str:
    """Download + verify + unpack the Linux tarball of `app` (a tag like v0.8.0, default the latest release);
    returns the path to `<app>-cli`. A version that is already unpacked is not downloaded again."""
    home = home or tools_dir()
    tag = version or latest_tag(app)
    ver = tag.lstrip("v")
    stem = f"{app}-{ver}-linux-{arch()}"
    cli = home / stem / "bin" / f"{app}-cli"
    if cli.exists():
        log(f"{app} {ver}: already installed at {cli}")
        return str(cli)
    base = f"https://github.com/{APPS[app]}/releases/download/{tag}"
    name = f"{stem}.tar.gz"
    sums = _get(f"{base}/SHA256SUMS.txt").decode()
    want = next((l.split()[0] for l in sums.splitlines() if l.strip().endswith(name)), None)
    if want is None:
        raise SystemExit(f"{name} is not in {base}/SHA256SUMS.txt")
    home.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=home) as tmp:
        tgz = Path(tmp) / name
        log(f"{app} {ver}: downloading {base}/{name}")
        h = hashlib.sha256()
        req = urllib.request.Request(f"{base}/{name}", headers={"User-Agent": "claude-film-maker"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tgz, "wb") as f:
            for chunk in iter(lambda: r.read(1 << 20), b""):
                h.update(chunk)
                f.write(chunk)
        if h.hexdigest() != want:
            raise SystemExit(f"{name}: sha256 {h.hexdigest()} does not match SHA256SUMS.txt ({want})")
        out = Path(tmp) / "x"
        with tarfile.open(tgz) as t:
            t.extractall(out, filter="data")      # refuses absolute paths, links outside, device files
        (out / stem).rename(home / stem)
    log(f"{app} {ver}: installed at {cli}")
    return str(cli)


def status(home: Path | None = None) -> dict:
    return {app: (lambda c: {"cli": c, "version": cli_version(c) if c else None})(find_cli(app, home=home)) for app in APPS}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install", help="download and unpack release binaries")
    i.add_argument("app", nargs="?", default="all", choices=[*APPS, "all"])
    i.add_argument("--version", help="release tag, e.g. v0.8.0 (default: latest)")
    sub.add_parser("status", help="which binaries are found, and their versions")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        print(json.dumps(status(), indent=1))
        return 0
    for app in (APPS if a.app == "all" else [a.app]):
        install(app, a.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
