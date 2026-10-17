"""A film's edit as a FilmCraft project (getartcraft.com/apps/filmcraft, the open-source Premiere-style editor).

FilmCraft (0.8, alpha) saves `.fcproj` (UTF-8 JSON, `schema_version` 13, media by path) and imports / exports FCP7 XML,
FCPXML, OpenTimelineIO, CMX 3600 EDL, AAF and OMF; it cannot open `.prproj`. Its schema is large and moves between
releases, so nothing here writes `.fcproj` by hand: the edit is described as plain data (`Timeline`: media, clips on
tracks, Motion keyframes), turned into FilmCraft's own engine commands (`commands()`, one JSON object per line, the
format of `filmcraft-cli run`), and the headless engine builds, validates and saves the project, so the file is
valid by construction. The same session can also write OTIO / EDL / FCPXML / FCP7 XML of the edit for other editors.

    plan / film ──► Timeline ──► commands (script.jsonl) ──► `filmcraft-cli run` ──► <id>-<variant>.fcproj (+ interchange)
                                                                                    └─► verify(): reopen, compare to the Timeline

Variants (`--variant`):
  final   AMV or any film: the rendered mp4 on V1 and the mix on A1 (the whole film as one clip; cut it there).
  layers  AMV: the bake stage's per-shot RGBA layer sequences (`out/<id>/amv/layers/<shot>/*.png`) as clips at their plan
          cuts, with the plan's Motion keys (position / scale / rotation / opacity) so the shots can be re-cut. Shots that
          overlap their neighbour (a layer runs on past its cut) sit one video track higher. The flash / grade / titles /
          letterbox of the Blender compositor are NOT in these layers: use `final` for the finished look.
  scenes  three.js films: film.json + data/timeline.json; the rendered film cut into its scenes (one clip per scene
          window, source offset into the full mp4), the mix on A1.

CLI: python -m filmtools.artcraft.filmcraft --film films/timeless --variant final|layers|scenes
         [--video PATH] [--mix PATH] [--layers DIR] [--out DIR] [--interchange otio,edl,fcpxml,xml] [--cli PATH]
         [--emit-only] [--no-verify] [--preview 1.5,10]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import install

TICKS = 254_016_000_000          # FilmCraft's time base: ticks per second
TIMEBASES = [23.976, 24, 25, 29.97, 30, 50, 59.94, 60]       # Preferences > Media > Indeterminate Media Timebase
INTERCHANGE_EXT = {"otio": "otio", "edl": "edl", "fcpxml": "fcpxml", "xml": "xml", "aaf": "aaf"}


def ticks(frames: float, fps: float) -> int:
    return round(frames * TICKS / fps)


# ------------------------------------------------------------------------------------------------------- the edit

@dataclass
class Media:
    key: str
    path: Path
    kind: str                  # video | audio | sequence (first file of a numbered image sequence)


@dataclass
class Clip:
    media: str                 # Media.key
    track: str                 # "V1", "V2", ... | "A1"
    start: int                 # timeline frame
    dur: int | None = None     # frames; None: the whole media
    src_in: float = 0.0        # seconds into the media (video / audio)
    name: str | None = None
    keys: dict = field(default_factory=dict)       # pos [[f, [x, y]]] / scale [[f, v]] / rot [[f, v]] / opacity [[f, v]]; timeline frames


@dataclass
class Timeline:
    name: str
    w: int
    h: int
    fps: float
    media: list = field(default_factory=list)
    clips: list = field(default_factory=list)

    def video_tracks(self) -> int:
        return max([int(c.track[1:]) for c in self.clips if c.track[0] == "V"] or [1])

    def audio_tracks(self) -> int:
        return max([int(c.track[1:]) for c in self.clips if c.track[0] == "A"] or [1])


def timebase(fps: float) -> str:
    best = min(TIMEBASES, key=lambda t: abs(t - fps))
    return f"{best:g}"


# ------------------------------------------------------------------------------------------------------ commands

PROP = {"pos": ("position", lambda v: list(v)), "scale": ("scale", float), "rot": ("rotation", float),
        "opacity": ("opacity", float)}
EFFECT = {"pos": "motion", "scale": "motion", "rot": "motion", "opacity": "opacity"}


def setup_commands(tl: Timeline) -> list:
    """Project, imports (items are numbered 1.. in this order), the sequence, then every clip placed. Returns
    [(command, tag)]: tag is ("place", clip_index) for a placement."""
    c = [({"id": "prefs.set", "params": {"key": "media.indeterminateTimebase", "value": timebase(tl.fps)}}, None),
         ({"id": "file.newProject", "params": {"name": tl.name}}, None)]
    for m in tl.media:
        if m.kind == "sequence":
            c.append(({"id": "file.importImageSequence", "params": {"path": str(m.path)}}, ("import", m.key)))
        else:
            c.append(({"id": "file.import", "params": {"paths": [str(m.path)]}}, ("import", m.key)))
    c.append(({"id": "file.newSequence", "params": {"name": tl.name, "width": tl.w, "height": tl.h, "fps": tl.fps,
                                                    "video": tl.video_tracks(), "audio": tl.audio_tracks()}}, None))
    return c


def place_command(tl: Timeline, clip: Clip, item: int) -> dict:
    kind = next(m.kind for m in tl.media if m.key == clip.media)
    p = {"item": item, "track": clip.track, "frame": clip.start}
    if kind != "audio":
        p["audio"] = False             # the mix is its own clip on A1, not the audio of the picture
    if clip.dur is not None:
        p["duration"] = ticks(clip.dur, tl.fps)
    if clip.src_in:
        p["sourceIn"] = round(clip.src_in * TICKS)
    return {"id": "timeline.place", "params": p}


def _clamp(clip: Clip, f: int) -> int:
    """A key frame inside the clip (the engine pins keys to the clip too)."""
    end = clip.start + (clip.dur if clip.dur is not None else 10 ** 9)
    return min(max(f, clip.start), end - 1)


def clip_commands(tl: Timeline, clip: Clip, cid: int) -> list:
    out = []
    if clip.name:
        out.append({"id": "clip.rename", "params": {"clip": cid, "name": clip.name}})
    for what, ks in clip.keys.items():
        prop, conv = PROP[what]
        for f, v in ks:
            f = _clamp(clip, f)
            out.append({"id": "effects.setParam", "params": {
                "clip": cid, "effect": EFFECT[what], "param": prop, "value": conv(v),
                "time": ticks(f, tl.fps), "keyframe": True}})
    return out


class RunError(SystemExit):
    pass


def run_commands(cli: str, cmds: list, workdir: Path, name: str, timeout=3600) -> list:
    """`filmcraft-cli run` on `cmds`; the parsed result line of each, or a RunError naming the first failure."""
    script = workdir / name
    script.write_text("".join(json.dumps(c, separators=(",", ":")) + "\n" for c in cmds))
    r = subprocess.run([cli, "run", str(script)], capture_output=True, text=True, timeout=timeout)
    res = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                res.append(json.loads(line))
            except ValueError:
                pass
    bad = [x for x in res if not x.get("ok")]
    if bad or len(res) != len(cmds) or r.returncode != 0:
        msg = bad[0] if bad else (r.stderr or r.stdout)[-600:]
        raise RunError(f"filmcraft-cli run {script.name} failed: {msg}")
    return res


def build(tl: Timeline, cli: str, out: Path, interchange=(), workdir: Path | None = None) -> Path:
    """Run the Timeline through the engine and save `<out>/<name>.fcproj` (+ interchange files). Two passes: the
    first places everything to learn the clip ids the engine hands out, the second repeats it with the keyframes,
    names and saves (the ids must come out the same; a mismatch is an error, not a mis-keyed project)."""
    out.mkdir(parents=True, exist_ok=True)
    workdir = workdir or out
    for m in tl.media:
        if not m.path.exists():
            raise SystemExit(f"media missing: {m.path}")
    setup = setup_commands(tl)
    items: dict = {}
    first = run_commands(cli, [c for c, _ in setup], workdir, "pass1-setup.jsonl")
    for (c, tag), r in zip(setup, first):
        if tag and tag[0] == "import":
            ids = r["result"]["items"] if "imageSequences" not in r["result"] else [s["item"] for s in r["result"]["imageSequences"]]
            if len(ids) != 1:
                raise SystemExit(f"import of {tag[1]} gave items {ids}")
            items[tag[1]] = ids[0]
    place = [place_command(tl, c, items[c.media]) for c in tl.clips]
    ids = [r["result"]["clips"][0] for r in run_commands(cli, [c for c, _ in setup] + place, workdir, "pass1.jsonl")[len(setup):]]
    project = out / f"{tl.name}.fcproj"
    cmds = [c for c, _ in setup] + place
    for clip, cid in zip(tl.clips, ids):
        cmds += clip_commands(tl, clip, cid)
    cmds.append({"id": "file.saveAs", "params": {"path": str(project)}})
    for fmt in interchange:
        cmds.append({"id": "file.exportInterchange", "params": {"format": fmt, "path": str(out / f"{tl.name}.{INTERCHANGE_EXT[fmt]}")}})
    res = run_commands(cli, cmds, workdir, "script.jsonl")
    got = [r["result"]["clips"][0] for r in res[len(setup):len(setup) + len(place)]]
    if got != ids:
        raise SystemExit(f"clip ids changed between passes ({ids[:3]}.. vs {got[:3]}..); project not trusted")
    (workdir / "pass1-setup.jsonl").unlink(missing_ok=True)
    (workdir / "pass1.jsonl").unlink(missing_ok=True)
    for stray in (out / "FilmCraft Previews",):        # the engine's preview cache folder, empty for a headless build
        if stray.is_dir() and not any(stray.iterdir()):
            stray.rmdir()
    return project


# ------------------------------------------------------------------------------------------------------ verify

def inspect(cli: str, project: Path) -> dict:
    r = subprocess.run([cli, "--project", str(project), "inspect", "sequence"], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise SystemExit(f"filmcraft-cli could not open {project}: {r.stderr or r.stdout}")
    d = json.loads(r.stdout)
    return d.get("sequence", d)


def verify(cli: str, project: Path, tl: Timeline) -> list:
    """Reopen the saved project headless and compare its sequence with the Timeline; the list of differences
    (empty: the project opens and holds exactly the edit)."""
    seq = inspect(cli, project)
    diffs = []
    s = seq.get("settings", {})
    if "fps" in s and abs(float(s["fps"]) - tl.fps) > 1e-3:
        diffs.append(f"fps {s['fps']} != {tl.fps}")
    found = {}
    for kind, key in (("V", "video"), ("A", "audio")):
        for i, t in enumerate(seq[key], 1):
            for it in t["items"]:
                found[(f"{kind}{i}", round(it["start"] * tl.fps / TICKS))] = it
    for c in tl.clips:
        it = found.pop((c.track, c.start), None)
        if it is None:
            diffs.append(f"{c.name or c.media}: no clip at {c.track} frame {c.start}")
            continue
        if c.dur is not None and it["durationFrames"] != c.dur:
            diffs.append(f"{c.name or c.media}: {it['durationFrames']} frames, expected {c.dur}")
        if c.src_in and abs(it["sourceIn"] / TICKS - c.src_in) > 0.5 / tl.fps:
            diffs.append(f"{c.name or c.media}: source in {it['sourceIn'] / TICKS:.3f}s, expected {c.src_in:.3f}s")
        for what, ks in c.keys.items():
            n = next((e["params"][PROP[what][0]]["keyframes"] for e in it["effects"] if e["effect"] == EFFECT[what]), None)
            want = len({_clamp(c, f) for f, _ in ks})
            if n != want:
                diffs.append(f"{c.name or c.media}: {n} {what} keys, expected {want}")
    for (tr, f), it in found.items():
        diffs.append(f"unexpected clip {it.get('name')} at {tr} frame {f}")
    return diffs


def render_preview(cli: str, project: Path, seconds, out_dir: Path, scale=0.5) -> list:
    """Program frames at `seconds` through FilmCraft's own renderer."""
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for s in seconds:
        dst = out_dir / f"t{s:07.2f}.png"
        r = subprocess.run([cli, "--project", str(project), "render", "--seconds", str(s), "--out", str(dst),
                            "--scale", str(scale)], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise SystemExit(f"render at {s}s failed: {r.stderr or r.stdout}")
        made.append(dst)
    return made


# ----------------------------------------------------------------------------------------------- exporters

def _first_png(d: Path):
    files = sorted(d.glob("*.png")) if d.is_dir() else []
    return files[0] if files else None


def timeline_final(film_id: str, video: Path, mix: Path | None, fps: float, w=1920, h=1080, variant="final") -> Timeline:
    """The rendered film (V1, no sound of its own) and its mix (A1)."""
    tl = Timeline(f"{film_id}-{variant}", w, h, fps, [Media("video", video, "video")])
    tl.clips.append(Clip("video", "V1", 0, name=video.stem))
    if mix is not None:
        tl.media.append(Media("mix", mix, "audio"))
        tl.clips.append(Clip("mix", "A1", 0, name="mix"))
    return tl


def amv_layers(plan, layers_dir: Path, mix: Path | None, name: str, strict=False):
    """Timeline of the plan's shots as baked layer sequences at their cuts, with the plan's Motion keys.
    Returns (Timeline, [shots without baked frames])."""
    from ..amv import effectcraft as AEC          # the per-frame key compression the EffectCraft export uses
    tl = Timeline(name, 1920, 1080, float(plan.fps))
    missing = []
    last_end: list = []                            # per video track: the frame its last clip ends
    for shot in plan.shots:
        first = _first_png(layers_dir / shot.name)
        if first is None:
            missing.append(shot.name)
            continue
        n = shot.end - shot.a
        raw = shot.raw
        t = next((i for i, e in enumerate(last_end) if e <= shot.a), None)
        if t is None:
            last_end.append(0)
            t = len(last_end) - 1
        last_end[t] = shot.end
        keys = {"pos": [(f, v) for f, v in AEC.array_keys([[x, y] for x, y in zip(raw["px"], raw["py"])], shot.a)],
                "scale": AEC.array_keys(raw["s"], shot.a), "rot": AEC.array_keys(raw["rz"], shot.a)}
        if raw.get("opacity"):
            keys["opacity"] = AEC.lin_keys(raw["opacity"])
        tl.media.append(Media(shot.name, first, "sequence"))
        tl.clips.append(Clip(shot.name, f"V{t + 1}", shot.a, n, name=shot.name, keys=keys))
    if missing and (strict or len(missing) == len(plan.shots)):
        raise SystemExit(f"no baked layer frames for {len(missing)} shot(s) in {layers_dir}: {', '.join(missing[:5])}"
                         " (run the bake stage first)")
    if mix is not None:
        tl.media.append(Media("mix", mix, "audio"))
        tl.clips.append(Clip("mix", "A1", 0, name="mix"))
    return tl, missing


def scenes_timeline(film_id: str, video: Path, windows: dict, mix: Path | None) -> Timeline:
    """A three.js film's scenes as clips: each scene window of the full mp4, back to back on V1 (the cut points are
    the scene boundaries of data/timeline.json, so a scene can be trimmed or moved in FilmCraft)."""
    fps = float(windows["fps"])
    w, h = (windows.get("format") or [1920, 1080])[:2]
    tl = Timeline(f"{film_id}-scenes", int(w), int(h), fps, [Media("video", video, "video")])
    for s in windows["scenes"]:
        a, b = round(s["start"] * fps), round(s["end"] * fps)
        if b > a:
            tl.clips.append(Clip("video", "V1", a, b - a, src_in=a / fps, name=s["id"]))
    if mix is not None:
        tl.media.append(Media("mix", mix, "audio"))
        tl.clips.append(Clip("mix", "A1", 0, name="mix"))
    return tl


def _film_fps_size(film_dir: Path):
    doc = json.loads((film_dir / "film.json").read_text())
    fmt = {"landscape": (1920, 1080), "vertical": (1080, 1920), "square": (1080, 1080)}.get(doc.get("format"), (1920, 1080))
    return float(doc.get("fps", 30)), fmt, doc


def out_root(film_dir: Path) -> Path:
    return film_dir.resolve().parent.parent / "out" / film_dir.resolve().name


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--film", required=True, type=Path, help="film folder (films/<id>)")
    ap.add_argument("--variant", choices=["final", "layers", "scenes"], default="final")
    ap.add_argument("--video", type=Path, help="rendered mp4 (default out/<id>/amv/<id>.mp4 for an AMV, else out/<id>/<id>.mp4)")
    ap.add_argument("--mix", type=Path, help="the mix (default: the plan's / film.json's audio)")
    ap.add_argument("--layers", type=Path, help="baked layer frames (default out/<id>/amv/layers)")
    ap.add_argument("--out", type=Path, help="output folder (default out/<id>/artcraft)")
    ap.add_argument("--interchange", default="", help="also write these with the engine: otio,edl,fcpxml,xml,aaf")
    ap.add_argument("--cli", help="path to filmcraft-cli (else $FILMCRAFT_CLI, PATH, the artcraft install dir)")
    ap.add_argument("--emit-only", action="store_true", help="write script.jsonl only, do not run the engine")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--preview", help="comma list of seconds to render through FilmCraft after building")
    a = ap.parse_args(argv)

    film = a.film
    film_id = film.resolve().name
    root = out_root(film)
    out = a.out or root / "artcraft"
    is_amv = (film / "amv" / "plan.json").exists()
    fps, (w, h), doc = _film_fps_size(film) if (film / "film.json").exists() else (30.0, (1920, 1080), {})
    mix = a.mix
    video = a.video
    if a.variant == "layers":
        if not is_amv:
            raise SystemExit("--variant layers needs films/<id>/amv/plan.json (an AMV)")
        from ..amv import plan as P
        plan = P.load(film)
        mix = mix or plan.path(plan.raw["audio"])
        tl, missing = amv_layers(plan, a.layers or root / "amv" / "layers", mix if mix.exists() else None, f"{film_id}-layers")
        if missing:
            print(f"warning: {len(missing)} shot(s) without baked frames left out: {', '.join(missing)}", file=sys.stderr)
    else:
        video = video or ((root / "amv" / f"{film_id}.mp4") if is_amv else root / f"{film_id}.mp4")
        if is_amv:
            from ..amv import plan as P
            plan = P.load(film)
            fps, (w, h) = float(plan.fps), (1920, 1080)
            mix = mix or plan.path(plan.raw["audio"])
        else:
            mix = mix or (film / doc["audio"]["mix"] if doc.get("audio", {}).get("mix") else None)
        mix = mix if mix is not None and mix.exists() else None
        if a.variant == "final":
            tl = timeline_final(film_id, video, mix, fps, w, h)
        else:
            from .. import timeline as TL
            tl = scenes_timeline(film_id, video, TL.require(film / "data"), mix)
    for m in tl.media:
        if not m.path.exists():
            raise SystemExit(f"{m.key}: {m.path} does not exist (render / mix it first, or pass --video / --mix)")
    out.mkdir(parents=True, exist_ok=True)
    if a.emit_only:
        setup = setup_commands(tl)
        ids = {m.key: i + 1 for i, m in enumerate(tl.media)}
        cmds = [c for c, _ in setup] + [place_command(tl, c, ids[c.media]) for c in tl.clips]
        (out / "script.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cmds))
        print(f"{len(tl.clips)} clips on {tl.video_tracks()} video track(s) -> {out / 'script.jsonl'} (item ids are indicative)")
        return 0
    cli = install.find_cli("filmcraft", a.cli)
    if not cli:
        print("filmcraft-cli not found: python -m filmtools.artcraft install filmcraft   (or --cli / $FILMCRAFT_CLI)", file=sys.stderr)
        return 2
    fmts = [x for x in a.interchange.split(",") if x]
    project = build(tl, cli, out, fmts)
    print(f"project: {project} ({project.stat().st_size // 1024} KB, FilmCraft {install.cli_version(cli)}), {len(tl.clips)} clips")
    for f in fmts:
        print(f"{f}: {out / (tl.name + '.' + INTERCHANGE_EXT[f])}")
    if not a.no_verify:
        diffs = verify(cli, project, tl)
        for d in diffs:
            print("verify:", d, file=sys.stderr)
        if diffs:
            return 1
        print("verified: reopened headless, sequence matches the edit")
    if a.preview:
        for p in render_preview(cli, project, [float(x) for x in a.preview.split(",")], out / "preview"):
            print("preview:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
