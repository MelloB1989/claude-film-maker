"""film-anime-render: the whole film from its Blender shots, in one command: every scene's plate rendered (those up to
date skipped), every plate scanned, the film's video rendered by the app with the mix, and a contact sheet of it.

    uv run film-anime-render --film <id>                    # the final: plates 2560x1440 EEVEE, 32 samples (on the Mac)
    uv run film-anime-render --film <id> --preview          # a fleet host: plates 960x540, 16 samples, a draft video
        [--only a,b] [--force] [--samples N] [--res WxH] [--plates-only] [--no-video] [--no-sheet] [--dry-run]
        [--video-samples auto|N] [--allow-software]

1. Plates. Each scene's shot (plates.py: data/plates.json, else blender/shots/<scene>.py) renders through
   blender/render.py unless its stamp says it is up to date (plates.py fingerprint: its code and every module it
   imports, the film's models, its window, its look-schedule entry, the settings); --force renders them all. A plate
   is cleared before it renders. One that fails (or fails its scan) is moved aside to plates/<plate>.failed/ so the
   film plays its slate, and the run goes on to the next. A scene with no shot file yet is a slate in the film.
2. Scan. Every plate the film uses is checked (render.py --scan --expect-res): every frame there, none blank or bad,
   all one size. A plate that fails is moved aside as above.
3. Video. `bun scripts/render.ts video` (app/) with the mix muxed in (--noaudio, said aloud, when the film has no mix
   on this machine): out/<id>/<id>.mp4, or out/<id>/<id>-preview.mp4 for a preview (rendered with --allow-software:
   the fleet hosts have no GPU).
4. Contact sheet. One still of every shot (its middle frame) from the app, so graded, lettered and barred as the film
   is, tiled with labels: out/<id>/review/contact.png (contact-preview.png for a preview).

Blender: plates.py blender(). Each step's outcome is printed as JSON at the end; the exit code is 1 when any plate failed
or the video did not render.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .. import cli, paths
from . import plates as P
from . import review as R


def log(msg: str) -> None:
    print(f"[film-anime-render] {msg}", flush=True)


def _run(cmd: list[str], logfile: Path, cwd: Path | None = None, env: dict | None = None) -> int:
    """Run `cmd`, its output streamed to the console and to `logfile`. Its exit code."""
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with open(logfile, "w") as lf:
        lf.write(" ".join(cmd) + "\n")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=cwd, env=env)
        for line in p.stdout:
            lf.write(line)
            if any(k in line for k in ("built in", "Error", "error", "FAIL", "Traceback", "frame ", "wrote")):
                sys.stdout.write("    " + line)
        return p.wait()


def set_aside(film: paths.FilmPaths, plate: str) -> None:
    d = P.plates_dir(film, plate)
    bad = d.with_name(plate + ".failed")
    if bad.exists():
        shutil.rmtree(bad)
    if d.exists():
        d.rename(bad)


def plan(film: paths.FilmPaths, settings: dict, only: list[str] | None, force: bool) -> list[dict]:
    """What each scene needs: {"scene", "plate", "action": render | up to date | no shot, "fingerprint"}. Two scenes made
    by one shot file are one plate."""
    out, seen = [], set()
    for sc in P.scenes(film):
        if only and sc.id not in only:
            continue
        if not sc.exists:
            out.append({"scene": sc.id, "plate": sc.plate, "action": "no shot", "sc": sc})
            continue
        if sc.plate in seen:
            continue
        seen.add(sc.plate)
        fp = P.fingerprint(film, sc, settings)
        act = "render" if force or not P.up_to_date(film, sc, fp) else "up to date"
        out.append({"scene": sc.id, "plate": sc.plate, "action": act, "fingerprint": fp, "sc": sc})
    return out


def render_plates(film: paths.FilmPaths, settings: dict, steps: list[dict]) -> None:
    logs = film.out / "logs"
    expect = P.mode_res(film, settings)
    todo = [s for s in steps if s["action"] == "render"]
    for k, s in enumerate(todo, 1):
        log(f"plate {k}/{len(todo)}: {s['plate']} ({s['scene']}, frames {s['sc'].f0}-{s['sc'].f1 - 1}) "
            f"{settings['mode']} {expect}")
        t0 = time.time()
        P.clear_plates(film, s["plate"])
        code = _run(P.render_cmd(film.id, s["plate"], settings), logs / f"{s['plate']}.log")
        if code == 0:
            code = _run(P.scan_cmd(film.id, s["plate"], expect), logs / f"{s['plate']}.scan.log")
            s["scan"] = code
        s["seconds"] = round(time.time() - t0, 1)
        if code == 0:
            P.write_stamp(film, s["plate"], s["fingerprint"], settings)
            s["result"] = "rendered"
        else:
            set_aside(film, s["plate"])
            s["result"] = f"FAILED (exit {code}, {(logs / s['plate']).with_suffix('.log')}): set aside, a slate in the film"
        log(f"  {s['plate']}: {s['result']} in {s['seconds']} s")


def scan_all(film: paths.FilmPaths, settings: dict, steps: list[dict]) -> None:
    """Scan the plates not rendered this run (those that were are scanned already)."""
    expect = P.mode_res(film, settings)
    for s in steps:
        if s["action"] != "up to date":
            continue
        code = _run(P.scan_cmd(film.id, s["plate"], expect), film.out / "logs" / f"{s['plate']}.scan.log")
        s["scan"] = code
        if code != 0:
            set_aside(film, s["plate"])
            s["result"] = f"FAILED its scan (exit {code}): set aside, a slate in the film"
            log(f"  {s['plate']}: {s['result']}")
        else:
            s["result"] = "up to date"


def bun() -> str:
    b = shutil.which("bun")
    if not b:
        raise SystemExit("no bun on the PATH: the app renders the video (https://bun.sh)")
    return b


def has_mix(film: paths.FilmPaths) -> bool:
    mix = json.loads(film.config.read_text()).get("audio", {}).get("mix")
    return bool(mix) and (film.dir / mix).exists()


def render_video(film: paths.FilmPaths, preview: bool, samples: str, allow_software: bool) -> dict:
    out = film.out / (f"{film.id}-preview.mp4" if preview else f"{film.id}.mp4")
    cmd = [bun(), "scripts/render.ts", "video", "--film", film.id, "--samples", samples, "--out", str(out)]
    if not has_mix(film):
        log("the film has no mix on this machine: the video is silent (--noaudio)")
        cmd.append("--noaudio")
    if preview or allow_software:
        cmd.append("--allow-software")
    log(f"video: {' '.join(cmd[1:])}")
    code = _run(cmd, film.out / "logs" / "video.log", cwd=paths.APP)
    return {"video": str(out) if code == 0 else None, "exit": code, "audio": has_mix(film)}


def contact_sheet(film: paths.FilmPaths, preview: bool, allow_software: bool) -> dict:
    """One still of every shot from the app (its middle frame), tiled with labels."""
    scs = P.scenes(film)
    fps = P.fps_of(film)
    frames = [(s.f0 + s.f1 - 1) // 2 for s in scs]
    times = [f / fps for f in frames]
    d = film.out / "review" / ("contact-stills-preview" if preview else "contact-stills")
    if d.exists():
        shutil.rmtree(d)
    cmd = [bun(), "scripts/render.ts", "stills", "--film", film.id, "--t", ",".join(f"{t:.6f}" for t in times),
           "--out", str(d)]
    if preview or allow_software:
        cmd.append("--allow-software")
    code = _run(cmd, film.out / "logs" / "contact.log", cwd=paths.APP)
    if code != 0:
        return {"sheet": None, "exit": code}
    items = []
    for i, (s, f, t) in enumerate(zip(scs, frames, times), 1):
        p = d / f"f_{f'{t:.2f}'.rjust(7, '0')}.png"
        items.append({"label": R.label(i, s, f, fps), "image": p if p.exists() else None,
                      "slate": [s.id, "no still", p.name]})
    out = film.out / "review" / ("contact-preview.png" if preview else "contact.png")
    R.tile(items, out, 6, (480, 270), f"{film.id}  ·  contact sheet  ·  {'preview' if preview else 'final'}")
    return {"sheet": str(out), "exit": 0}


def main(argv: list[str] | None = None) -> None:
    ap = cli.parser(description="Render the whole film from its Blender shots: plates, scan, video, contact sheet.")
    ap.add_argument("--preview", action="store_true", help="a fleet host's draft: plates at half size, 16 samples")
    ap.add_argument("--only", help="scene ids, comma separated (plates only; the video is always the whole film)")
    ap.add_argument("--force", action="store_true", help="render every plate, up to date or not")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--res", help="WxH: the plates' size (default: the mode's)")
    ap.add_argument("--plates-only", action="store_true", help="plates and scan, no video, no sheet")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--video-samples", default=None, help="render.ts --samples (default auto; 1 for a preview)")
    ap.add_argument("--allow-software", action="store_true", help="let the app render on a software GL")
    ap.add_argument("--dry-run", action="store_true", help="say what would render, render nothing")
    a = cli.parse(ap, argv)
    film = paths.current()
    settings = dict(P.PREVIEW if a.preview else P.FINAL)
    if a.samples:
        settings["samples"] = a.samples
    if a.res:
        settings["res"] = a.res
    only = a.only.split(",") if a.only else None
    steps = plan(film, settings, only, a.force)
    for s in steps:
        log(f"{s['scene']:>9} <- {s['plate']}: {s['action']}")
    if a.dry_run:
        return
    render_plates(film, settings, steps)
    scan_all(film, settings, steps)
    report = {"settings": settings, "plates": {s["plate"]: s.get("result", s["action"]) for s in steps}}
    failed = [s["plate"] for s in steps if str(s.get("result", "")).startswith("FAILED")]
    ok = not failed
    if not a.plates_only:
        if not a.no_video:
            report["video"] = render_video(film, a.preview, a.video_samples or ("1" if a.preview else "auto"),
                                           a.allow_software)
            ok = ok and report["video"]["exit"] == 0
        if not a.no_sheet:
            report["contact"] = contact_sheet(film, a.preview, a.allow_software)
    print(json.dumps(report, indent=1))
    if not ok:
        sys.exit(1)
