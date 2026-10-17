"""Timeless v2: render the EffectCraft project on the 16-core render VM and encode the mp4.

    python -m filmtools.amv2.render [--draft] [--frames A-B] [--procs 4] [--threads 4] [--src clips|src240]
                                    [--no-build] [--no-encode] [--name NAME]
    python -m filmtools.amv2.render bench [--frames A-B] [--splits 1x16,2x8,4x4,8x2]

1. (re)builds the project with ecbuild (`--draft`: half resolution, 4 motion-blur samples; else full, 16) into
   `build/amv2/<name>.ecproj` (inside the worktree: the render queue syncs the tree but not `out/`);
2. splits the frames into chunks, drops ONE render-queue job whose command runs `procs` `effectcraft-cli render
   --format png` processes in parallel on the VM (each with RAYON_NUM_THREADS=threads: the CLI's thread knob), and waits;
3. checks every PNG (all frames present, no black frames except where intended: signalstats YAVG);
4. encodes h264 (CRF 16, yuv420p, +faststart) with out/timeless/amv2/mix.wav, else the song's 0-30 s;
5. writes a 6x5 contact sheet and `timings.json` (seconds per frame, per chunk).
Output: out/timeless/amv2/{frames[_draft]/f_NNNNN.png, Timeless_v2[_draft].mp4, contact[_draft].png}.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from . import ecbuild

ROOT = ecbuild.ROOT
OUT = ecbuild.OUT_DIR
QUEUE = Path("/home/nikhil/code/.renderq")
VM_CLI = "effectcraft-cli"
FFMPEG = str(ecbuild.FILM_BIN / "ffmpeg")
SONG = "/home/nikhil/code/film-making/handover/amv_handover/audio/timeless_full.wav"
DUR = 900
FPS = 30
BLACK_OK = {0, 1}          # frames that are black on purpose (S01 fades up from black)


def parse_frames(s, dur=DUR):
    if not s:
        return 0, dur
    a, b = s.split("-")
    return int(a), min(int(b) + 1, dur)      # inclusive on the command line


def chunks(a, b, n):
    """Split [a, b) into n near-equal consecutive chunks (no empty ones)."""
    n = max(1, min(n, b - a))
    q, r = divmod(b - a, n)
    out, s = [], a
    for i in range(n):
        e = s + q + (1 if i < r else 0)
        out.append((s, e))
        s = e
    return out


def tree_rel(p):
    return str(Path(p).resolve().relative_to("/home/nikhil/code"))


def run_job(name, cmd, out_rel, threads, timeout=3 * 3600):
    job = QUEUE / f"{name}.json"
    for ext in ("done", "log", "started"):
        (QUEUE / f"{name}.{ext}").unlink(missing_ok=True)
    job.write_text(json.dumps(dict(tree=tree_rel(ROOT), cmd=cmd, out=out_rel, threads=threads)))
    t0 = time.time()
    done = QUEUE / f"{name}.done"
    while not done.exists():
        if time.time() - t0 > timeout:
            raise SystemExit(f"render job {name} timed out")
        time.sleep(3)
    log = (QUEUE / f"{name}.log").read_text() if (QUEUE / f"{name}.log").exists() else ""
    rc = int(done.read_text().strip() or 0)
    return rc, log, time.time() - t0


def vm_cmd(project_rel, frames_dir_rel, ch, threads, res, quality):
    """One shell command that renders every chunk as a parallel process and prints per-chunk wall times."""
    parts = []
    for i, (s, e) in enumerate(ch):
        # --start/--end are seconds; the end is exclusive. Frames are picked by ceil(t*fps), so a quarter-frame of slack keeps float rounding off the boundary.
        r = (f"( t0=$(date +%s.%N); RAYON_NUM_THREADS={threads} {VM_CLI} --project {project_rel} render --comp MAIN "
             f"--format png --start {(s - 0.25) / FPS:.6f} --end {(e - 0.75) / FPS:.6f} --resolution {res} "
             f"--quality {quality} --out {frames_dir_rel}/f > /dev/null 2> {frames_dir_rel}/err{i}.txt; rc=$?; "
             f"echo CHUNK {s} {e} rc=$rc secs=$(echo \"$(date +%s.%N) - $t0\" | bc) ) &")
        parts.append(r)
    return "mkdir -p " + frames_dir_rel + "; " + " ".join(parts) + " wait"


def check_frames(fdir, a, b):
    """Every frame present; black frames listed (YAVG < 2) so the caller can compare with the intended ones."""
    miss = [f for f in range(a, b) if not (fdir / f"f_{f:05d}.png").exists()]
    black = []
    if not miss:
        r = subprocess.run([FFMPEG, "-v", "error", "-start_number", str(a), "-i", str(fdir / "f_%05d.png"), "-frames:v",
                            str(b - a), "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"],
                           capture_output=True, text=True)
        ys = [float(x) for x in re.findall(r"YAVG=([\d.]+)", r.stdout)]
        black = [a + i for i, y in enumerate(ys) if y < 2.0]
    return miss, black


def encode(fdir, a, b, mp4, mix=None, fps=FPS):
    mix = mix or (OUT / "mix.wav" if (OUT / "mix.wav").exists() else None)
    cmd = [FFMPEG, "-y", "-v", "error", "-framerate", str(fps), "-start_number", str(a), "-i", str(fdir / "f_%05d.png"),
           "-frames:v", str(b - a)]
    if mix:
        cmd += ["-ss", f"{a / fps}", "-i", str(mix)]
    else:
        cmd += ["-ss", f"{a / fps}", "-t", f"{(b - a) / fps}", "-i", SONG]
    cmd += ["-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "256k", "-t", f"{(b - a) / fps}", "-movflags", "+faststart", str(mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("encode failed: " + r.stderr[-800:])
    return mix


def contact_sheet(fdir, a, b, out, cols=6, rows=5, w=320):
    n = cols * rows
    idx = [a + round(i * (b - a - 1) / (n - 1)) for i in range(n)]
    ins = []
    for f in idx:
        ins += ["-i", str(fdir / f"f_{f:05d}.png")]
    sc = "".join(f"[{i}:v]scale={w}:-2[s{i}];" for i in range(n))
    rowsx = "".join(f"{''.join(f'[s{r * cols + c}]' for c in range(cols))}hstack={cols}[r{r}];" for r in range(rows))
    fc = sc + rowsx + "".join(f"[r{r}]" for r in range(rows)) + f"vstack={rows}"
    r = subprocess.run([FFMPEG, "-y", "-v", "error"] + ins + ["-filter_complex", fc, "-frames:v", "1", str(out)],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("contact sheet failed: " + r.stderr[-500:])
    return idx


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", default="render", choices=("render", "bench"))
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--frames", default=None, help="A-B inclusive")
    ap.add_argument("--procs", type=int, default=4, help="parallel effectcraft-cli processes on the VM")
    ap.add_argument("--threads", type=int, default=4, help="RAYON_NUM_THREADS per process")
    ap.add_argument("--chunks", type=int, default=None, help="chunks (default: procs; more chunks than procs is not supported)")
    ap.add_argument("--src", choices=("clips", "src240"), default="clips")
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--no-encode", action="store_true")
    ap.add_argument("--splits", default="1x16,2x8,4x4,8x2")
    a = ap.parse_args(argv)
    tag = "_draft" if a.draft else ""
    name = a.name or f"timeless_v2{tag}"
    proj = ROOT / "build/amv2" / f"{name}.ecproj"
    proj.parent.mkdir(parents=True, exist_ok=True)
    if not a.no_build:
        rc = ecbuild.main(["--out", str(proj), "--src", a.src] + (["--draft"] if a.draft else [])
                          + (["--samples", str(a.samples)] if a.samples else []))
        if rc:
            raise SystemExit("ecbuild reported warnings/errors; fix them first")
    res = "half" if a.draft else "full"
    f0, f1 = parse_frames(a.frames)
    fdir = OUT / f"frames{tag}" if not a.name else OUT / f"frames_{a.name}"
    proj_rel = str(proj.relative_to(ROOT))
    fdir_rel = str(fdir.relative_to(ROOT))
    if a.cmd == "bench":
        res_rows = []
        for sp in a.splits.split(","):
            p, t = (int(x) for x in sp.split("x"))
            d = fdir_rel + f"/bench_{p}x{t}"
            ch = chunks(f0, f1, p)
            rc, log, secs = run_job(f"{name}-bench-{p}x{t}", vm_cmd(proj_rel, d, ch, t, res, "best"), d, t)
            n = f1 - f0
            res_rows.append(dict(split=sp, frames=n, wall=round(secs, 1), per_frame=round(secs / n, 2), rc=rc))
            print(res_rows[-1], flush=True)
        (OUT / f"bench{tag}.json").write_text(json.dumps(res_rows, indent=1))
        return 0
    ch = chunks(f0, f1, a.chunks or a.procs)
    t0 = time.time()
    rc, log, secs = run_job(f"{name}-render", vm_cmd(proj_rel, fdir_rel, ch, a.threads, res, "best"), fdir_rel, a.threads)
    print(log[-1500:])
    chunk_t = [dict(zip(("a", "b", "rc", "secs"), (m[0], m[1], m[2], m[3])))
               for m in re.findall(r"CHUNK (\d+) (\d+) rc=(\d+) secs=([\d.]+)", log)]
    miss, black = check_frames(fdir, f0, f1)
    unexpected = [f for f in black if f not in BLACK_OK]
    timings = dict(frames=[f0, f1], res=res, procs=a.procs, threads=a.threads, wall=round(secs, 1),
                   sec_per_frame=round(secs / (f1 - f0), 3), chunks=chunk_t, missing=miss, black=black)
    (OUT / f"timings{tag}.json").write_text(json.dumps(timings, indent=1))
    print(json.dumps({k: v for k, v in timings.items() if k != "chunks"}))
    if miss:
        raise SystemExit(f"{len(miss)} frames missing, first {miss[:10]}: see {fdir}/err*.txt")
    if unexpected:
        print(f"WARNING black frames not in the intended set: {unexpected}")
    if not a.no_encode:
        mp4 = OUT / f"Timeless_v2{tag}.mp4"
        mix = encode(fdir, f0, f1, mp4)
        print(f"encoded {mp4} (audio: {mix or 'song 0-30s'})")
        if f1 - f0 >= 30:
            idx = contact_sheet(fdir, f0, f1, OUT / f"contact{tag}.png")
            print(f"contact sheet {OUT / f'contact{tag}.png'} frames {idx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
