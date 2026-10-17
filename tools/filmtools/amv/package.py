"""Deliverables packager: a finished AMV render as one self-contained, portable folder.

    python -m filmtools.amv.package --film films/timeless --render-tag <tag> --out <dir> [--src out/timeless/amv]

    <dir>/<Name>.mp4                  the render, out/<id>/amv/<Name>_<tag>.mp4
    <dir>/project/<id>.blend          the main comp, every image path `//` relative and inside project/
    <dir>/project/layers|titles|outro the frames the .blend reads (hardlinked when on one filesystem, else copied)
    <dir>/project/plan.json grade.json FIXES.md
    <dir>/effectcraft/                the EffectCraft project (baked layers in project/), with relink.py
    <dir>/README.md

The .blend is built by blender/amv/build.py with --layers / --overlays pointing INTO project/, so Blender's own
relative remap on save yields `//layers/...`. It is then verified from a COPY of the folder at another path: the saved
.blend is opened there, two frames are rendered (blender/amv/verify_package.py) and the run fails on a missing (magenta)
or blank image. This module is bpy-free; only the verify script runs inside Blender.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import plan as P

REPO = Path(__file__).resolve().parents[3]
BUILD = REPO / "blender" / "amv" / "build.py"
VERIFY = REPO / "blender" / "amv" / "verify_package.py"
ECPROJ_NAME = "{id}.ecproj"
PLACEHOLDER = "@PROJECT@"
VERIFY_FRAMES = (100, 640)
CREDITS = "SAU_EDITZ"


# ------------------------------------------------------------------------------------------------------ path logic

def needed_dirs(raw: dict, stack_names, portal_srcs=()) -> list[str]:
    """The folders under project/ the .blend reads, relative to project/, in a stable order:
    `layers/<shot>` for every plane (stack + portal A shots), `titles/screen.<i>` and `titles/watermark`, `outro`."""
    out = [f"layers/{n}" for n in dict.fromkeys([*stack_names, *portal_srcs])]
    out += [f"titles/screen.{i}" for i in range(len(raw.get("titles") or []))]
    out += ["titles/watermark", "outro"]
    return out


def audit_image_paths(paths) -> list[str]:
    """Problems with the .blend's image paths (as stored): each must be `//` relative, not climbing out (`..`) and not
    absolute. Returns messages; empty means portable."""
    bad = []
    for p in paths:
        if not p.startswith("//"):
            bad.append(f"not blend-relative: {p}")
        elif ".." in Path(p[2:].replace("\\", "/")).parts:
            bad.append(f"escapes the project folder: {p}")
    return bad


def link_or_copy(src: Path, dst: Path) -> str:
    """Hardlink src to dst when both are on one filesystem, else copy. Returns 'link' or 'copy'."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
        return "link"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def link_tree(src: Path, dst: Path) -> dict:
    """Mirror src's files into dst (hardlink else copy). Returns {'link': n, 'copy': n}."""
    n = {"link": 0, "copy": 0}
    for f in sorted(src.rglob("*")):
        if f.is_file():
            n[link_or_copy(f, dst / f.relative_to(src))] += 1
    return n


def find_video(src: Path, tag: str) -> Path:
    """The render `<Name>_<tag>.mp4` in src (one match)."""
    hits = sorted(src.glob(f"*_{tag}.mp4"))
    if len(hits) != 1:
        raise SystemExit(f"expected one {src}/*_{tag}.mp4, found {len(hits)}")
    return hits[0]


def delivered_name(video: Path, tag: str) -> str:
    return video.name[: -len(f"_{tag}.mp4")] + ".mp4"


def verdict(report: dict) -> list[str]:
    """Failures in the verify script's JSON report: path problems, missing files, bad frames."""
    fails = audit_image_paths(report.get("image_paths", []))
    fails += [f"missing file: {m}" for m in report.get("missing", [])]
    for f in report.get("frames", []):
        if f.get("magenta", 0) > 0.02:
            fails.append(f"frame {f['frame']}: {f['magenta']:.1%} missing-texture magenta")
        if f.get("blank"):
            fails.append(f"frame {f['frame']}: blank (std {f.get('std', 0):.2f}, mean {f.get('mean', 0):.1f})")
    if not report.get("frames"):
        fails.append("no frames rendered")
    return fails


# ------------------------------------------------------------------------------------------------------ steps

def run(cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(list(map(str, cmd)), check=True, **kw)


def build_blend(a, film: Path, project: Path):
    run([a.blender, "-b", "--factory-startup", "-t", a.threads, "-P", BUILD, "--",
         "--film", film, "--layers", project / "layers", "--overlays", project,
         "--samples", a.samples, "--save", project / f"{film.name}.blend"])


def build_effectcraft(a, film: Path, project: Path, ec: Path, mix: Path | None = None) -> str:
    """Emit the EffectCraft spec/script pointing at project/ and rewrite the paths to a placeholder so the folder is
    portable; build the .ecproj too when the CLI is available. Returns a note for the README."""
    from . import effectcraft as E
    plan = P.load(film)
    opts = E.Options(film_dir=film, layers_dir=project / "layers", titles_dir=project / "titles",
                     outro_dir=project / "outro", source="baked")
    spec = E.build_spec(plan, opts)
    if mix is None and spec.get("audio") and Path(spec["audio"]).exists():
        mix = Path(spec["audio"])
    if mix is not None:                                          # the mix travels with the project too
        link_or_copy(mix, project / "audio" / mix.name)
        spec["audio"] = str((project / "audio" / mix.name).resolve())
    ec.mkdir(parents=True, exist_ok=True)
    proj = ec / ECPROJ_NAME.format(id=film.name)
    note = "built without effectcraft-cli: run `python3 relink.py` on a machine that has it"
    cli = E.find_cli(a.effectcraft_cli)
    if cli:
        E.render_jsx(spec, ec / "build.jsx", proj)
        code, so, se = E.run_script(cli, ec / "build.jsx")
        note = ("the .ecproj was built at pack time (its paths point at the packing machine's folder); run "
                "`python3 relink.py` after moving the delivery" if code == 0 and proj.exists()
                else f"effectcraft-cli failed at pack time ({(se or so).strip()[:200]}); run `python3 relink.py`")
    # portable: every project/ path -> placeholder, resolved by relink.py on the target machine
    text = json.dumps(spec).replace(json.dumps(str(project.resolve()))[1:-1], PLACEHOLDER)
    spec = json.loads(text)
    (ec / "spec.json").write_text(json.dumps(spec, indent=1))
    jsx = (f"var SPEC = {json.dumps(spec, separators=(',', ':'))};\nvar OUT_PROJECT = \"{PLACEHOLDER}/../effectcraft/"
           f"{proj.name}\";\n" + E.JSX.read_text())
    (ec / "build.jsx.template").write_text(jsx)
    (ec / "relink.py").write_text(RELINK)
    return note


RELINK = '''#!/usr/bin/env python3
"""Point the EffectCraft project at this folder: fills in build.jsx from build.jsx.template with the absolute
path of ../project and builds the .ecproj with effectcraft-cli ($EFFECTCRAFT_CLI, or on PATH)."""
import json, os, shutil, subprocess, sys
from pathlib import Path
here = Path(__file__).resolve().parent
project = (here.parent / "project").resolve()
text = (here / "build.jsx.template").read_text().replace("@PROJECT@/../effectcraft", json.dumps(str(here))[1:-1])
text = text.replace("@PROJECT@", json.dumps(str(project))[1:-1])
(here / "build.jsx").write_text(text)
cli = os.environ.get("EFFECTCRAFT_CLI") or shutil.which("effectcraft-cli")
if not cli:
    sys.exit("build.jsx written; effectcraft-cli not found: set $EFFECTCRAFT_CLI, then run `effectcraft-cli script build.jsx`")
sys.exit(subprocess.run([cli, "script", str(here / "build.jsx")]).returncode)
'''


def verify(a, out: Path, frames) -> dict:
    """Open the saved .blend from a COPY of the delivery at a different path and render `frames` small."""
    film_id = out.name  # unused; blend name is read from project/
    blend = next((out / "project").glob("*.blend"))
    tmp = Path(tempfile.mkdtemp(prefix="amv-verify-", dir=a.verify_tmp or out.parent))
    try:
        copy = tmp / "moved folder" / "delivery"       # a different path, with a space in it
        stats = link_tree(out / "project", copy / "project")
        print(f"verify copy at {copy} ({stats})", flush=True)
        rep = tmp / "report.json"
        frames_out = out.parent / (out.name + "-verify")
        frames_out.mkdir(exist_ok=True)
        run([a.blender, "-b", "--factory-startup", "-t", a.threads, copy / "project" / blend.name, "-P", VERIFY, "--",
             "--frames", ",".join(map(str, frames)), "--res-scale", a.res_scale, "--out", frames_out,
             "--report", rep])
        report = json.loads(rep.read_text())
        report["frames_dir"] = str(frames_out)
        return report
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pick_mix(film: Path, plan, explicit: Path | None) -> Path | None:
    """The mix to ship: --mix, else films/<id>/audio/mix/mix_fixed.wav (mix_fix.py), else the plan's audio."""
    for c in (explicit, film / "audio" / "mix" / "mix_fixed.wav", plan.path(plan.raw["audio"])):
        if c and Path(c).exists():
            return Path(c)
    return None


def mux_audio(video: Path, mix: Path, dst: Path, ffmpeg="ffmpeg"):
    """dst = the video stream of `video` untouched, with `mix` as its audio (AAC 320k)."""
    if dst.exists():
        dst.unlink()
    run([ffmpeg, "-y", "-loglevel", "error", "-i", video, "-i", mix, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "320k", "-shortest", "-movflags", "+faststart", dst])


def build_filmcraft(a, film: Path, video: Path, mix: Path | None, out: Path) -> str:
    """The FilmCraft project of the final cut (python -m filmtools.artcraft.filmcraft), best effort."""
    from .. import artcraft  # noqa: F401
    from ..artcraft import filmcraft as FC
    argv = ["--film", str(film), "--variant", "final", "--video", str(video), "--out", str(out)]
    if mix:
        argv += ["--mix", str(mix)]
    if a.filmcraft_cli:
        argv += ["--cli", a.filmcraft_cli]
    try:
        code = FC.main(argv)
    except SystemExit as e:
        code = e.code or 1
    return ("built at pack time" if code == 0 else f"not built (exit {code}: filmcraft-cli missing?)")


def blender_version(blender: str) -> str:
    try:
        return subprocess.run([blender, "--version"], capture_output=True, text=True).stdout.split("\n")[0].strip()
    except OSError:
        return "Blender 5.2"


def git_rev() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


README = """# {title}

Edit by **{credits}**. This folder is a self-contained, portable delivery: the finished video, the Blender project that
renders it, and an EffectCraft project of the same edit. Nothing in it points outside the folder.

## What is here

| path | what |
|---|---|
| `{video}` | the finished render (`{tag}`) |
| `project/{id}.blend` | the main comp. Every image is a `//` path inside `project/`, so the folder can be moved |
| `project/layers/<shot>/<f>.png` | the baked shot layers (retimed, keyed, layer effects baked in), one PNG per comp frame |
| `project/titles/screen.<i>/<k>.png`, `project/titles/watermark/` | the title sequences and the watermark the comp overlays |
| `project/outro/<f>.png` | the 3D outro frames, laid on top from the outro frame on |
| `project/plan.json`, `project/grade.json` | the edit plan (timing, transforms, titles) and the fitted grade |
| `project/FIXES.md` | the deliberate changes made to the handover plan |
| `project/audio/{mix}` | the audio mix (`mix_fix.py`'s corrected mix when present): the mp4 carries {muxed_txt} |
| `filmcraft/` | the FilmCraft project of the final cut (mp4 + mix on a timeline): {fc_note}. Its media paths are absolute; rebuild after moving with `python -m filmtools.artcraft.filmcraft --film films/{id} --variant final --video <this folder>/{video} --mix project/audio/{mix} --out filmcraft` |
| `effectcraft/` | the EffectCraft project: `spec.json`, `build.jsx.template`, `relink.py`, and `{id}.ecproj` when effectcraft-cli was available at pack time (else `relink.py` makes it); built on the baked layers in `project/layers` |

## Render the .blend (Blender 5.2)

    blender -b project/{id}.blend -o //render/#### -s 0 -e {last} -a      # every frame -> project/render/NNNN.png
    blender -b project/{id}.blend -o //render/#### -f 100                 # one frame

or open it in the Blender UI and press Ctrl+F12. It is a Cycles scene (CPU is fine; a GPU is faster); the picture is one
plane per shot, the compositor does the grade, bars, titles, glints and outro. Resolution percentage in the Output
panel scales it down for a preview. Mux the frames with the audio mix of your own if you want the mp4 sound.

## Open the EffectCraft project

EffectCraft (getartcraft.com, the open-source After Effects) opens `effectcraft/{id}.ecproj`. Its footage paths are
absolute: after moving the folder run `python3 effectcraft/relink.py` (needs `effectcraft-cli`, `$EFFECTCRAFT_CLI`
or on PATH), which rewrites them to this folder and rebuilds the project. {ec_note}

## After Effects -> Linux tool mapping

| the AE edit used | here |
|---|---|
| Twixtor (slow-motion retime) | RIFE / optical-flow retime (`filmtools.amv.retime`, baked into the layers) |
| Magic Bullet Premium Glow | a fitted node grade (`AMV Grade` node group in the .blend; `project/grade.json`) |
| Sapphire (glows, glints) | Blender compositor glows and bloom |
| AE layer effects (tile, radial / directional blur, lens, matte cutouts) | baked into the layer PNGs (`filmtools.amv.bake`) |

## Versions

{blender}; packaged by `filmtools.amv.package` at claude-film-maker {rev}; verified by opening a copy of `project/` at
another path and rendering frames {frames} at {res_scale}x: {verified}.

## Credits

Edit: {credits}.
"""


# ------------------------------------------------------------------------------------------------------ main

def raw_plan_rel(film: Path) -> str:
    return json.loads((film / "film.json").read_text()).get("amv", {}).get("plan", "amv/plan.json")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m filmtools.amv.package", description=__doc__.split("\n")[0])
    ap.add_argument("--film", required=True, type=Path, help="films/<id>")
    ap.add_argument("--render-tag", required=True, help="the render's tag: out/<id>/amv/<Name>_<tag>.mp4")
    ap.add_argument("--out", required=True, type=Path, help="delivery folder (created)")
    ap.add_argument("--src", type=Path, help="stage outputs holding layers/ titles/ outro/ and the mp4 "
                                             "(default out/<id>/amv; on the render VM $AMV_OUT)")
    ap.add_argument("--blender", default="blender")
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--samples", type=int, default=64, help="Cycles samples stored in the .blend")
    ap.add_argument("--res-scale", type=float, default=0.25, help="verification render scale")
    ap.add_argument("--verify-frames", default=",".join(map(str, VERIFY_FRAMES)))
    ap.add_argument("--verify-tmp", type=Path, help="where the verification copy is made (default beside --out)")
    ap.add_argument("--skip-video", action="store_true", help="no mp4 (it is not on this machine)")
    ap.add_argument("--effectcraft-cli")
    ap.add_argument("--filmcraft-cli")
    ap.add_argument("--mix", type=Path, help="audio mix to ship (default films/<id>/audio/mix/mix_fixed.wav)")
    ap.add_argument("--no-mux", action="store_true", help="copy the mp4 as rendered, do not replace its audio")
    ap.add_argument("--no-filmcraft", action="store_true")
    a = ap.parse_args(argv)

    film = a.film.resolve()
    film_id = film.name
    src = (a.src or film.parent.parent / "out" / film_id / "amv").resolve()
    out = a.out.resolve()
    project = out / "project"
    plan = P.load(film)
    raw = plan.raw

    video = None if a.skip_video else find_video(src, a.render_tag)
    names = [s.name for s in plan.stack()]
    portal_srcs = [plan.shots[p["A"]].name for p in raw.get("portals") or []]   # "A" indexes the shots
    out.mkdir(parents=True, exist_ok=True)

    stats = {"link": 0, "copy": 0}
    missing = []
    for rel in needed_dirs(raw, names, portal_srcs):
        d = src / rel
        if not d.is_dir():
            missing.append(rel)
            continue
        for k, v in link_tree(d, project / rel).items():
            stats[k] += v
    if missing:
        print(f"WARNING: not in {src}: {', '.join(missing)}", file=sys.stderr)
    print(f"frames into project/: {stats}", flush=True)

    for name, srcf in (("plan.json", film / raw_plan_rel(film)), ("grade.json", film / "amv" / "grade.json"),
                       ("FIXES.md", film / "amv" / "FIXES.md")):
        if srcf.exists():
            shutil.copy2(srcf, project / name)

    build_blend(a, film, project)
    frames = [int(x) for x in a.verify_frames.split(",")]
    report = verify(a, out, frames)
    fails = verdict(report)
    (out.parent / (out.name + "-verify") / "report.json").write_text(json.dumps(report, indent=1))
    if fails:
        raise SystemExit("VERIFY FAILED:\n  " + "\n  ".join(fails))
    print(f"verified: {len(report['frames'])} frames ok, {len(report['image_paths'])} image paths, all relative", flush=True)

    mix = pick_mix(film, plan, a.mix)
    if mix:
        link_or_copy(mix, project / "audio" / mix.name)
        mix = project / "audio" / mix.name
    ec_note = build_effectcraft(a, film, project, out / "effectcraft", mix)
    name, fc_note, muxed = "", "not built (no video in this run)", False
    if video:
        name = delivered_name(video, a.render_tag)
        if mix and not a.no_mux and shutil.which("ffmpeg"):
            mux_audio(video, mix, out / name)
            muxed = True
        else:
            link_or_copy(video, out / name)
        if not a.no_filmcraft:
            fc_note = build_filmcraft(a, film, out / name, mix, out / "filmcraft")
    fm = json.loads((film / "film.json").read_text())
    (out / "README.md").write_text(README.format(
        title=fm.get("title", film_id), credits=CREDITS, video=name or "(video not included)", tag=a.render_tag,
        id=film_id, last=raw["dur"] - 1, ec_note=ec_note, blender=blender_version(a.blender), rev=git_rev(),
        frames=", ".join(map(str, frames)), res_scale=a.res_scale, verified="passed",
        mix=mix.name if mix else "(none)", muxed_txt="this mix (muxed in, replacing the render's own track)" if muxed else "the render's own track (the mix is shipped alongside)", fc_note=fc_note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
