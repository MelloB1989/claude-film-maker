"""Timeless v2 packager: a finished render as one portable folder (mp4, EffectCraft project, .blend files, mix, README).

    PYTHONPATH=tools python -m filmtools.amv2.package --mp4 out/timeless/amv2/Timeless_v2.mp4 \\
        --ecproj out/timeless/amv2/timeless_v2.ecproj [--blend-dir out/timeless/amv2/blender] \\
        [--out /home/nikhil/code/film-making/deliverables/Timeless_v2_SAU_EDITZ] [--data $AMV2_DATA]

    <out>/Timeless_v2_SAU_EDITZ.mp4          the render
    <out>/effectcraft/timeless_v2.ecproj     the project, every media path RELATIVE to this file (../media/...)
    <out>/media/{src240,mattes,blender,...}  exactly the footage / sequences the project references, nothing else
    <out>/fonts/                             the font files the text layers use (install them before opening)
    <out>/blender/*.blend                    outro_v2, titles3d, rift, shockwave: external files packed into the file
    <out>/audio/mix.wav, cues.csv            the mix and its cue sheet
    <out>/README.md

Media is hard-linked from its source when both are on one filesystem (`--copy` forces copies): nothing is stored twice
and the folder is as big as the media it references. The .ecproj is JSON: every Footage item's `path` and `sequence` are
rewritten; no absolute path may remain. The .blend files go through `blender/amv2/pack_blend.py` (needs Blender 5.x;
`--blender` names it, and without a working Blender the files are copied as they are, with a warning).

Verification (`--verify-frames`, default 3 frames): the package is hard-linked to a COPY at another path (with a space in
it), `effectcraft-cli render-frame` runs there from another working directory, and each frame must equal the frame the
ORIGINAL project renders (PSNR > 60 dB, proves the relative paths); each is also compared with the same
frame of the mp4 (PSNR, reported; `--psnr-min` makes it a failure). Python 3.10+, bpy-free, no numpy.
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

ROOT = Path(__file__).resolve().parents[3]
FILM_BIN = Path("/home/nikhil/code/film-making/bin")
EC_CLI = FILM_BIN / "artcraft/effectcraft-0.10.0-linux-x86_64/bin/effectcraft-cli"
HANDOVER = Path(os.environ.get("AMV_HANDOVER", "/home/nikhil/code/film-making/handover/amv_handover"))
DEFAULT_OUT = Path("/home/nikhil/code/film-making/deliverables/Timeless_v2_SAU_EDITZ")
NAME = "Timeless_v2_SAU_EDITZ"
BLENDS = ("outro_v2", "titles3d", "rift", "shockwave")
FONT_DIRS = (ROOT / "films/timeless/fonts", HANDOVER / "fonts", Path.home() / ".local/share/fonts", Path("/usr/share/fonts"))
AUDIO_EXT = {".wav", ".mp3", ".flac", ".aac", ".m4a", ".ogg"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def find_tool(env, explicit, bundled, name):
    for c in (explicit, os.environ.get(env), str(bundled), shutil.which(name)):
        if c and (shutil.which(c) or Path(c).is_file()):
            return c
    return None


# ------------------------------------------------------------------------------------------------------ files

def link_or_copy(src: Path, dst: Path, copy=False) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    if not copy:
        try:
            os.link(src, dst)
            return "link"
        except OSError:
            pass
    shutil.copy2(src, dst)
    return "copy"


def tree_size(p: Path) -> int:
    """Bytes of the files under p, hard links counted once per file (what a zip or a copy of the folder holds)."""
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


# ------------------------------------------------------------------------------------------------------ the project

def media_items(proj: dict):
    """(item, kind-dict) of every Footage item that points at files."""
    for it in proj["items"].values():
        k = it["kind"]
        if k.get("type") == "Footage" and k.get("path"):
            yield it, k


def item_files(k: dict) -> list[str]:
    return list(k["sequence"]) if k.get("sequence") else [k["path"]]


def destination(p: Path, data: Path | None) -> Path:
    """Where a referenced file lives in the package (relative to the package root)."""
    if p.suffix.lower() in AUDIO_EXT:
        return Path("audio") / p.name
    if data and data in p.parents:
        return Path("media") / p.relative_to(data)                      # src240/…, mattes/<clip>/…, blender/<element>/…
    if HANDOVER in p.parents:
        return Path("media/clips" if p.parent.name == "footage_clips" else "media/handover") / (p.name if p.parent.name == "footage_clips" else p.relative_to(HANDOVER))
    if ROOT in p.parents:
        return Path("media/repo") / p.relative_to(ROOT)
    return Path("media/other") / p.parent.name / p.name


def plan_media(proj: dict, data: Path | None) -> dict[str, Path]:
    """{absolute source path: package-relative destination}, refusing two sources for one destination."""
    plan, taken = {}, {}
    for it, k in media_items(proj):
        for f in item_files(k):
            if f in plan:
                continue
            p = Path(f)
            if not p.is_absolute():
                raise SystemExit(f"{it['name']}: path is already relative ({f}); give the project saved by ecbuild")
            d = destination(p, data)
            if d in taken and taken[d] != f:
                raise SystemExit(f"two media files would land on {d}: {taken[d]} and {f}")
            taken[d] = f
            plan[f] = d
    return plan


def rewrite_project(proj: dict, plan: dict[str, Path], ec_dir: str) -> dict:
    """Same project, every Footage path / sequence entry relative to the folder that will hold the .ecproj."""
    rel = lambda f: Path(os.path.relpath(plan[f], ec_dir)).as_posix()                       # noqa: E731
    for it, k in media_items(proj):
        k["path"] = rel(k["path"])
        if k.get("sequence"):
            k["sequence"] = [rel(f) for f in k["sequence"]]
    return proj


def leftover_absolute(proj: dict) -> list[str]:
    """Absolute filesystem paths still in the JSON (any string that starts with / and ends in a media-ish extension)."""
    pat = re.compile(r"^(/|[A-Za-z]:[\\/])[^\n]*\.(mp4|mov|png|jpg|jpeg|exr|tif|tiff|wav|mp3|ttf|otf|hdr|blend)$", re.I)
    out = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str) and pat.match(x):
            out.append(x)
    walk(proj)
    return out


def fonts_used(proj: dict) -> set[str]:
    names = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "font" and isinstance(v, str):
                    names.add(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(proj)
    return names


def font_index() -> dict[str, Path]:
    """{PostScript name: file} of the font files in FONT_DIRS (fontTools when present, else the file stem)."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        TTFont = None
    idx = {}
    for d in FONT_DIRS:
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.suffix.lower() not in (".ttf", ".otf"):
                continue
            names = {f.stem, f.stem.replace(".otf", ""), re.sub(r"[^a-z0-9]", "", f.stem.lower().replace(".otf", ""))}
            if TTFont:
                try:
                    nm = TTFont(str(f), lazy=True)["name"]
                    for rec in nm.names:
                        if rec.nameID == 6:
                            names.add(str(rec.toUnicode()))
                except Exception:
                    pass
            for n in names:
                idx.setdefault(n, f)
    return idx


# ------------------------------------------------------------------------------------------------------ blender

def pack_blends(a, out: Path) -> dict:
    """Pack the four .blend files into <out>/blender. Returns {name: report or note}."""
    res = {}
    bdir = Path(a.blend_dir) if a.blend_dir else None
    blender = find_tool("BLENDER", a.blender, FILM_BIN / "blender", "blender")
    script = ROOT / "blender/amv2/pack_blend.py"
    search = [ROOT, HANDOVER / "fonts"]
    works = None
    for n in BLENDS:
        src = (bdir / f"{n}.blend") if bdir else None
        if not src or not src.is_file():
            res[n] = "missing: not in --blend-dir"
            log(f"WARNING: no {n}.blend in {bdir}")
            continue
        dst = out / "blender" / f"{n}.blend"
        dst.parent.mkdir(parents=True, exist_ok=True)
        rep = dst.with_suffix(".pack.json")
        if blender and not a.no_pack_blend:
            cmd = [blender, "-b", "--factory-startup", str(src), "-P", str(script), "--", "--out", str(dst), "--report", str(rep)]
            for s in search:
                cmd += ["--search", str(s)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0 and dst.is_file() and rep.is_file():
                res[n] = json.loads(rep.read_text())
                rep.unlink()
                bad = res[n]["missing"] + res[n]["external"]
                if bad:
                    log(f"WARNING: {n}.blend still has external files: {bad}")
                continue
            works = (r.stderr or r.stdout)[-300:]
        if not dst.is_file():
            shutil.copy2(src, dst)
            res[n] = "copied unpacked" + (f" (Blender failed: {works.strip()})" if works else " (--no-pack-blend or no Blender)")
            log(f"WARNING: {n}.blend copied as it is, external files are NOT packed")
    return res


# ------------------------------------------------------------------------------------------------------ verification

def ff(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def psnr(ffmpeg: str, a: Path, b: Path) -> float:
    """PSNR (dB, inf when identical) of two same-size images, from ffmpeg's own filter."""
    r = ff([ffmpeg, "-v", "info", "-i", str(a), "-i", str(b), "-lavfi", "[1:v][0:v]scale2ref=flags=bicubic[b][a];[a][b]psnr",
            "-f", "null", "-"])                                       # b is scaled to a's size (a draft mp4 is half size)
    m = re.search(r"average:(\S+)", r.stderr)
    psnr = float("inf") if not m or m.group(1) == "inf" else float(m.group(1))
    return psnr


def verify(a, out: Path, ecname: str, orig_proj: Path, mp4: Path) -> dict:
    cli = find_tool("EFFECTCRAFT_CLI", a.effectcraft_cli, EC_CLI, "effectcraft-cli")
    ffmpeg = find_tool("FFMPEG", None, FILM_BIN / "ffmpeg", "ffmpeg")
    if not cli or not ffmpeg:
        return {"skipped": "effectcraft-cli or ffmpeg not found"}
    frames = [int(x) for x in a.verify_frames.split(",") if x]
    tmp = Path(tempfile.mkdtemp(prefix="v2pkg-verify-", dir=a.verify_tmp or out.parent))
    rep = {"frames": []}
    try:
        copy = tmp / "moved folder" / "pkg"
        for f in sorted(out.rglob("*")):
            if f.is_file():
                link_or_copy(f, copy / f.relative_to(out))
        cwd = tmp / "elsewhere"
        cwd.mkdir()
        for fr in frames:
            pk, orig, vid = tmp / f"pkg_{fr}.png", tmp / f"orig_{fr}.png", tmp / f"mp4_{fr}.png"
            r1 = ff([cli, "render-frame", "--project", str(copy / "effectcraft" / ecname), "--comp", a.comp, "--frame", str(fr),
                     "--out", str(pk)], cwd=cwd)
            r2 = ff([cli, "render-frame", "--project", str(orig_proj), "--comp", a.comp, "--frame", str(fr), "--out", str(orig)], cwd=cwd)
            ff([ffmpeg, "-v", "error", "-y", "-i", str(mp4), "-vf", f"select=eq(n\\,{fr})", "-vframes", "1", str(vid)])
            row = {"frame": fr, "rendered": pk.is_file() and orig.is_file()}
            if row["rendered"]:
                row["psnr_vs_original_project"] = psnr(ffmpeg, pk, orig)
                row["identical"] = row["psnr_vs_original_project"] == float("inf") or row["psnr_vs_original_project"] > 60
                if vid.is_file():
                    row["psnr_vs_mp4"] = psnr(ffmpeg, pk, vid)
            else:
                row["error"] = ((r1.stderr or "") + (r2.stderr or ""))[-300:]
            rep["frames"].append(row)
            if a.keep_verify:
                shutil.copy2(pk, out.parent / f"{out.name}-verify-{fr}.png") if pk.is_file() else None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rep


# ------------------------------------------------------------------------------------------------------ README

README = """# Timeless v2 - SAU_EDITZ (EffectCraft + Blender)

A Spider-Man trilogy AMV (Tobey -> Andrew -> Tom) to the first 30 s of the *Timeless* guitar cover.
1920x1080, 30 fps, 900 frames. The edit is a script-built EffectCraft 0.10.0 project; the 3D outro, the chrome TIMELESS,
the multiverse rift and the drop shockwave are Blender 5.x renders that sit in the project as PNG sequences.

```
{tree}
```

## 1. The video
`{name}.mp4`: h264 yuv420p, the final mix muxed in (`audio/mix.wav`, -14 LUFS, true peak <= -1 dBTP).

## 2. The EffectCraft project (`effectcraft/{ecname}`)
Open it in EffectCraft 0.10.0, or drive it from the CLI:
`effectcraft-cli` is at `<EffectCraft>/bin/effectcraft-cli`.

- **Fonts first.** Install the files in `fonts/` (Linux: copy to `~/.local/share/fonts` and run `fc-cache -f`; macOS/Windows:
  double-click install). Without them the titles fall back to a default font: {fonts}.
- **Relative paths.** Every footage path in the project is relative to the `.ecproj` (`../media/...`), so the folder can be
  moved or zipped; keep `effectcraft/`, `media/` and `audio/` side by side. Nothing refers to the machine it was built on.
- **Structure.** Comp `MAIN` (1920x1080, 30 fps, 900 frames) holds one layer per shot (`SHOT_S01` ...). Each `SHOT_<id>` is a
  precomp with the footage (time-remapped 240 fps RIFE source, `media/src240/`), then the camera moves and transition
  keys on the MAIN layer. Above them, in this order: FX adjustment layers (chroma hits, glitch, shake), the grade (`GRADE_*`),
  overlays (flashes, ink frames, light sweeps, letterbox), the specials (rift, drop portal, triptych), the titles and the
  watermark. Edit any of them in place. Titles that go behind the subject use `media/mattes/<clip>/` as a track matte.
- **Footage.** `media/src240/clip_<ID>.mp4` are 240 fps copies of the 60 fps handover clips (same timeline: frame 4k is
  source frame k; no interpolation across the source cuts). `media/blender/<element>/NNNN.png` are straight-alpha RGBA
  sequences, the file number is the comp frame. `media/mattes/<clip>/NNNNN.png` are white-on-black subject mattes, one per 240 fps frame.
- **Re-render a frame / a range:**
  ```
  effectcraft-cli render-frame --project effectcraft/{ecname} --comp MAIN --frame 480 --out frame480.png
  effectcraft-cli --project effectcraft/{ecname} render --comp MAIN --format png --start 0 --end 30 --out frames/f
  ffmpeg -framerate 30 -i frames/f_%05d.png -i audio/mix.wav -c:v libx264 -crf 16 -pix_fmt yuv420p -c:a aac -b:a 320k -shortest -movflags +faststart out.mp4
  ```
  `render --start/--end` are in SECONDS (end exclusive; frame N is at N/30 s, so frames 0-899 are `--start 0 --end 30`), and
  `--out` is a file PREFIX: `frames/f` writes `frames/f_00000.png`, `f_00001.png`, ... (make `frames/` first). A render of the
  whole film is slow (motion blur, 240 fps sources): split the seconds range over several processes. The delivered mp4 was
  encoded exactly like the last command (CRF 16).
- **The project was generated** by `tools/filmtools/amv2/ecbuild.py` from `films/timeless/amv2/edl.json` in the film-maker
  repo. Changing the cut order, timings, transitions or titles is cleanest there (edit `edl.py`, rebuild); small visual tweaks
  are fine directly in the project.

## 3. Blender (`blender/*.blend`)
Blender 5.x. Each file is self-contained (fonts and the HDRI are packed in; nothing external). The motion is keyed once per
frame, scene frame = comp frame, 1920x1080 at 30 fps, Cycles, transparent film.

| file | frames | renders to | used in the project as |
|---|---|---|---|
| `outro_v2.blend` | 819-899 | `media/blender/outro/` | the 3D SAU_EDITZ outro |
| `titles3d.blend` | 802-826 | `media/blender/timeless3d/` | the chrome TIMELESS |
| `rift.blend` | 244-262 | `media/blender/rift/` | the multiverse rift (Tobey's iris -> Andrew) |
| `shockwave.blend` | 480-489 | `media/blender/shockwave/` | the drop ring blast |

Open the file, set the device in Preferences > System (OptiX/CUDA on a GPU, CPU works but is slow), then
`blender -b <file>.blend -a` (writes to the output path stored in the file; change it in Output Properties, keep the
`NNNN.png` naming: the number is the comp frame, RGBA 8-bit PNG, straight alpha). To use a new render, replace the PNGs in
`media/blender/<element>/` with the same names: the project picks them up. The scripts that build these scenes are
`blender/amv2/outro.py` and `blender/amv2/elements.py` in the film-maker repo.

## 4. Audio (`audio/`)
`mix.wav` 48 kHz 24-bit stereo: the first 30.0 s of the song (ends on a clean fade), the three voice lines (never filtered;
the music is ducked under them), and SFX placed on exact frames from the EDL. `cues.csv`: every voice line and word (measured
onsets), every SFX and its frame, with gains. Rebuild: `python -m filmtools.amv2.mix` in the repo.

## Facts
{facts}
"""


def tree_listing(out: Path, depth=2) -> str:
    lines = []
    for p in sorted(out.rglob("*")):
        rel = p.relative_to(out)
        if len(rel.parts) > depth or (p.is_file() and len(rel.parts) > 1 and rel.parts[0] == "media"):
            continue
        if p.is_dir() and rel.parts[0] == "media" and len(rel.parts) == 2:
            n = sum(1 for _ in p.rglob("*") if _.is_file())
            lines.append(f"{rel.as_posix()}/   ({n} files)")
        elif len(rel.parts) <= depth:
            lines.append(rel.as_posix() + ("/" if p.is_dir() else ""))
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mp4", required=True)
    ap.add_argument("--ecproj", required=True, help="the project saved by ecbuild (absolute media paths)")
    ap.add_argument("--blend-dir", help="folder with outro_v2.blend, titles3d.blend, rift.blend, shockwave.blend")
    ap.add_argument("--mix", help="default: <data>/mix.wav, else out/timeless/amv2/mix.wav")
    ap.add_argument("--cues", help="default: next to the mix")
    ap.add_argument("--data", default=os.environ.get("AMV2_DATA"), help="$AMV2_DATA: where src240/, mattes/, blender/ live")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--force", action="store_true", help="replace an existing, non-empty --out")
    ap.add_argument("--copy", action="store_true", help="copy media instead of hard-linking")
    ap.add_argument("--comp", default="MAIN")
    ap.add_argument("--blender")
    ap.add_argument("--no-pack-blend", action="store_true")
    ap.add_argument("--allow-unpacked", action="store_true", help="do not fail when a .blend is missing or could not be packed")
    ap.add_argument("--effectcraft-cli")
    ap.add_argument("--verify-frames", default="100,480,850", help="comma separated comp frames ('' skips the check)")
    ap.add_argument("--verify-tmp", help="where the moved copy for the check is made (default: next to --out)")
    ap.add_argument("--keep-verify", action="store_true", help="keep the verified frames as <out>-verify-<frame>.png")
    ap.add_argument("--psnr-min", type=float, default=0.0, help="fail when a frame is below this PSNR against the mp4 (0 = report only)")
    a = ap.parse_args(argv)

    mp4, ecproj = Path(a.mp4).resolve(), Path(a.ecproj).resolve()
    out = Path(a.out).resolve()
    data = Path(a.data).resolve() if a.data else None
    for p in (mp4, ecproj):
        if not p.is_file():
            raise SystemExit(f"not found: {p}")
    if out.exists() and any(out.iterdir()):
        if not a.force:
            raise SystemExit(f"{out} is not empty (use --force to replace it)")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    ecname = f"{ecproj.stem}.ecproj"

    proj = json.loads(ecproj.read_text())
    mix = Path(a.mix) if a.mix else next((p for p in ([data / "mix.wav"] if data else []) + [ROOT / "out/timeless/amv2/mix.wav"] if p.is_file()), None)
    cues = Path(a.cues) if a.cues else (mix.with_name("cues.csv") if mix else None)

    # (a) the mp4, (d) the mix
    stats = {"link": 0, "copy": 0}
    stats[link_or_copy(mp4, out / f"{NAME}.mp4", a.copy)] += 1
    if mix and mix.is_file():
        stats[link_or_copy(mix, out / "audio" / "mix.wav", a.copy)] += 1
    else:
        log("WARNING: no mix.wav found (--mix)")
    if cues and cues.is_file():
        stats[link_or_copy(cues, out / "audio" / "cues.csv", a.copy)] += 1
    else:
        log("WARNING: no cues.csv found")

    # (b) the project and the media it references
    plan = plan_media(proj, data)
    missing = [f for f in plan if not Path(f).is_file()]
    if missing:
        raise SystemExit(f"{len(missing)} referenced files do not exist, e.g. {missing[:3]}")
    mix_dest = Path("audio/mix.wav")
    for f, d in plan.items():
        if d == mix_dest:
            continue                                                  # shipped once, above
        stats[link_or_copy(Path(f), out / d, a.copy)] += 1
    for f, d in plan.items():                                         # the project's own audio is the packaged mix
        if d.parent == Path("audio") and d != mix_dest and not (out / d).exists():
            stats[link_or_copy(Path(f), out / d, a.copy)] += 1
    rewrite_project(proj, plan, "effectcraft")
    left = leftover_absolute(proj)
    if left:
        raise SystemExit(f"absolute paths remain in the project: {left[:3]}")
    (out / "effectcraft").mkdir(exist_ok=True)
    (out / "effectcraft" / ecname).write_text(json.dumps(proj, indent=2))

    # fonts
    idx, used, fontfiles, nofont = font_index(), sorted(fonts_used(proj)), [], []
    for n in used:
        f = idx.get(n) or idx.get(re.sub(r"[^a-z0-9]", "", n.lower())) or idx.get(re.sub(r"[^a-z0-9]", "", n.lower().rsplit("-regular", 1)[0]))
        if f:
            link_or_copy(f, out / "fonts" / f.name, True)
            fontfiles.append(f.name)
        else:
            nofont.append(n)
    if nofont:
        log(f"WARNING: no font file found for {nofont}")

    # (c) blender
    blends = pack_blends(a, out)

    # verification
    ver = verify(a, out, ecname, ecproj, mp4) if a.verify_frames else {"skipped": "--verify-frames ''"}

    size = tree_size(out)
    facts = [f"- Package size: {human(size)} ({sum(1 for f in out.rglob('*') if f.is_file())} files).",
             f"- Media referenced by the project: {len(plan)} files, {len(set(d.parts[1] if len(d.parts) > 2 else d.parts[0] for d in plan.values()))} groups."]
    (out / "README.md").write_text(README.format(
        tree=tree_listing(out), name=NAME, ecname=ecname,
        fonts=", ".join(sorted(set(used))) or "none", facts="\n".join(facts)))
    report = {"out": str(out), "size_bytes": size, "size": human(size), "files": sum(1 for f in out.rglob("*") if f.is_file()),
              "media_files": len(plan), "link_or_copy": stats, "fonts": fontfiles, "fonts_not_found": nofont,
              "blends": {k: (v if isinstance(v, str) else {"missing": v["missing"], "external": v["external"], "errors": v["errors"],
                                                         "relocated": [m["name"] for m in v.get("relocated", [])]})
                         for k, v in blends.items()}, "verify": ver}
    print(json.dumps(report, indent=1))
    bad = [r for r in ver.get("frames", []) if not r.get("rendered") or not r.get("identical")]
    if a.psnr_min:
        bad += [r for r in ver.get("frames", []) if r.get("psnr_vs_mp4", 99) < a.psnr_min]
    nopack = [k for k, v in blends.items() if isinstance(v, str) and not a.allow_unpacked]
    if nopack:
        log(f"blend files missing or not packed: {nopack} (--allow-unpacked to accept)")
    if bad or nopack or any(isinstance(v, dict) and (v["missing"] or v["external"]) for v in blends.values()):
        log("PACKAGE CHECKS FAILED")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
