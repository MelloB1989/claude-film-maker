"""Timeless v2: build `out/timeless/amv2/timeless_v2.ecproj` from edl.json with `effectcraft-cli script`.

    python -m filmtools.amv2.ecbuild [--src clips|src240] [--samples 16] [--out PATH] [--draft] [--emit-only]

Python computes everything numeric (time remap, per-frame camera moves: remap.py / moves.py), then writes one script:
    var E = {edl + extras (E.x.<lib> from <lib>_spec.extend)}; var CORE = {keys...};
    + ec/<lib>.jsx for every lib that exists (fx, grade, special, titles) + ec/core.jsx
and runs it. ec/README.md documents the ctx object the libs receive.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import moves
from .remap import Remap, remap_keys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                   # repo root (tools/filmtools/amv2 -> ..)
EC_DIR = HERE / "ec"
EDL = ROOT / "films/timeless/amv2/edl.json"
OUT_DIR = ROOT / "out/timeless/amv2"
FILM_BIN = Path("/home/nikhil/code/film-making/bin")
EC_CLI = FILM_BIN / "artcraft/effectcraft-0.10.0-linux-x86_64/bin/effectcraft-cli"
LIBS = ("fx", "grade", "special", "titles")             # libs concatenated before the core
HIN, HOUT = 6, 6                                         # handle frames either side of [a, b) in every SHOT_ precomp
TILE_PCT = 300                                           # Motion Tile output size where the frame edge would show
CUT_MIN = 0.12                                           # ffmpeg scene score that counts as a source cut
SRC_FPS = 60.0
BEHIND = set()                                           # clips whose shots get a MATTE_ mirror (titles `behind`)


class PStr(str):
    """A path that is a str (JSON-serialisable: libs put ctx into the scripts they build) and still takes `/`."""

    def __truediv__(self, o):
        return PStr(os.path.join(self, str(o)))

    def exists(self):
        return os.path.exists(self)

    def is_dir(self):
        return os.path.isdir(self)

    def read_text(self, *a, **k):
        return Path(self).read_text(*a, **k)

    @property
    def parent(self):
        return PStr(os.path.dirname(self))

    @property
    def name(self):
        return os.path.basename(self)


def data_dir():
    d = os.environ.get("AMV2_DATA")
    if d:
        return Path(d)
    vm = Path("/home/nikhil/code/film-making/work/timeless_v2")
    return vm if vm.exists() else OUT_DIR / "data"


def find_cli():
    for c in (os.environ.get("EFFECTCRAFT_CLI"), str(EC_CLI), "effectcraft-cli"):
        if c and (os.path.isabs(c) and Path(c).exists() or not os.path.isabs(c)):
            return c
    return "effectcraft-cli"


# ---------------------------------------------------------------- media probing
def _ff(tool):
    p = FILM_BIN / tool
    return str(p) if p.exists() else tool


def probe_len(path):
    r = subprocess.run([_ff("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def detect_cut(path, lo, hi):
    """Source time (s) of the clip's own scene cut inside the window (lo, hi) = the first frame of the new scene,
    or None. ffmpeg scene score; cached next to the other build output."""
    cache = OUT_DIR / ".cache" / "scene_scores.json"
    scores = {}
    if cache.exists():
        scores = json.loads(cache.read_text())
    if path not in scores:
        r = subprocess.run([_ff("ffmpeg"), "-hide_banner", "-i", path, "-vf",
                            "select='gte(scene,0)',metadata=print:key=lavfi.scene_score", "-an", "-f", "null", "-"],
                           capture_output=True, text=True)
        t = [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]
        s = [float(x) for x in re.findall(r"scene_score=([\d.]+)", r.stderr)]
        scores[path] = list(zip(t, s))
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(scores))
    best = None
    for t, s in scores[path]:
        if lo < t < hi and s >= CUT_MIN and (best is None or s > best[1]):
            best = (t, s)
    return best[0] if best else None


def matte_for(sh, data, clip_len):
    """The subject matte sequence for shots whose titles say `behind` (`$AMV2_DATA/mattes/<clip>/NNNNN.png`), else None.
    Its frame rate is frames / clip length (the sequence covers the whole clip)."""
    if sh["clip"] not in BEHIND or not clip_len:
        return None
    d = data / "mattes" / sh["clip"]
    files = sorted(d.glob("*.png")) if d.is_dir() else []
    if not files:
        return None
    return dict(first=str(files[0]), n=len(files), fps=round(len(files) / clip_len, 4))


def src_path(sh, mode, data):
    if mode == "src240":
        p = data / "src240" / f"clip_{sh['clip']}.mp4"
        if not p.exists():
            raise SystemExit(f"--src src240: {p} does not exist (yet)")
        return str(p)
    return sh["file"]


# ---------------------------------------------------------------- the spec
def build_core(E, mode, samples, data):
    global BEHIND
    BEHIND = {t["behind"] for t in E.get("titles", []) if t.get("behind")}
    S = E["shots"]
    shots = {}
    for i, sh in enumerate(S):
        n = sh["b"] - sh["a"]
        path = src_path(sh, mode, data)
        cut = None
        for tag in sh.get("fx", []):
            m = re.fullmatch(r"source_cut@(\d+)", tag)
            if m:
                F = int(m.group(1))
                lo, hi = sorted(sh["src"])
                tc = detect_cut(sh["file"], lo, hi)
                if tc is None:
                    raise SystemExit(f"{sh['id']}: no source cut found in {sh['clip']} {lo}..{hi}")
                cut = (F - sh["a"], tc)
        rm = Remap(sh["src"], n, sh["speed"], cut)
        clip_len = probe_len(path)
        shots[sh["id"]] = dict(
            file=path,
            remap=remap_keys(rm, HIN, HOUT, E["fps"], clip_len, SRC_FPS),
            keys=moves.shot_keys(sh, S[i - 1] if i else None, S[i + 1] if i + 1 < len(S) else None, HIN, HOUT),
            cut=cut, matte=matte_for(sh, data, clip_len))
    return dict(root=str(ROOT), data=str(data), src=mode, hin=HIN, hout=HOUT, tile=TILE_PCT,
                shutter=dict(angle=270, phase=-135, samples=samples), shots=shots)


def extend_E(E, ctx_py):
    E.setdefault("x", {})
    for lib in LIBS:
        try:
            mod = importlib.import_module(f"filmtools.amv2.{lib}_spec")
        except ModuleNotFoundError as e:
            if e.name != f"filmtools.amv2.{lib}_spec":
                raise
            continue
        E["x"].setdefault(lib, {})
        mod.extend(E, ctx_py)


def build_script(out_project, mode="clips", samples=16, E=None):
    E = E or json.loads(EDL.read_text())
    data = data_dir()
    ctx_py = dict(fps=E["fps"], w=E["w"], h=E["h"], root=PStr(ROOT), data=PStr(data), src=mode, log=lambda m: print(f"[ecbuild] {m}"))
    extend_E(E, ctx_py)
    CORE = build_core(E, mode, samples, data)
    parts = [f"var E = {json.dumps(E)};\nvar CORE = {json.dumps(CORE)};\nvar OUT_PROJECT = {json.dumps(str(out_project))};\n"]
    for lib in LIBS:
        p = EC_DIR / f"{lib}.jsx"
        if p.exists():
            parts.append(f"// ===== {p.name} =====\n" + p.read_text())
    parts.append("// ===== core.jsx =====\n" + (EC_DIR / "core.jsx").read_text())
    return "\n".join(parts), CORE


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", choices=("clips", "src240"), default="src240")
    ap.add_argument("--samples", type=int, default=None, help="motion blur samples (default 16, 4 with --draft)")
    ap.add_argument("--draft", action="store_true", help="4 motion-blur samples, project timeless_v2_draft.ecproj")
    ap.add_argument("--out", default=None)
    ap.add_argument("--emit-only", action="store_true", help="write build.jsx, do not run it")
    a = ap.parse_args(argv)
    samples = a.samples or (4 if a.draft else 16)
    out = Path(a.out) if a.out else OUT_DIR / ("timeless_v2_draft.ecproj" if a.draft else "timeless_v2.ecproj")
    out.parent.mkdir(parents=True, exist_ok=True)
    script, core = build_script(out, a.src, samples)
    jsx = out.with_suffix(".build.jsx")
    jsx.write_text(script)
    print(f"wrote {jsx} ({len(script) // 1024} KiB)")
    if a.emit_only:
        return 0
    r = subprocess.run([find_cli(), "script", str(jsx), "--empty"], capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        return r.returncode
    warns = [l for l in r.stdout.splitlines() if l.startswith("WARN")]
    print(f"{out}: {len(warns)} warnings")
    return 1 if warns else 0


if __name__ == "__main__":
    sys.exit(main())
