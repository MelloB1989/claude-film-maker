"""film-deliver: the film rendered in resumable segments, assembled with the final mix, encoded for the web and Instagram.

  film-deliver segments                         the segment ranges (frames), each split in the middle of a scene
  film-deliver render [--segments 4] [--scale 1] renders out/film/seg-<k>.mp4 one after another (silent), skipping any
                                                segment already there with the right frame count; each writes
                                                out/film/seg-<k>.mp4.progress while it runs
  film-deliver assemble [--segments 4] [--mix audio/mix/mix.wav]
                                                concat → out/film/video.mp4; the four outputs under the mix; stems copied
                                                to out/film/stems/; check() on each output
  film-deliver check                            check() on each output; exit 1 on any problem

The audio is never offset or trimmed (no -itsoffset, no -ss, no -shortest): the mix and the picture are both 93.6 s from
0, and check() measures the lengths instead.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from .paths import APP, AUDIO, DATA, OUT

FPS = 30
FILM = OUT / "film"
OUTPUTS = {
    "rough": OUT / "rough.mp4",
    "web1080": FILM / "gitloom-launch-1080p30.mp4",
    "ig16x9": OUT / "instagram" / "gitloom-launch-16x9.mp4",
    "ig4x5": OUT / "instagram" / "gitloom-launch-4x5.mp4",
}
SIZES = {"rough": (1920, 1080), "web1080": (1920, 1080), "ig16x9": (1920, 1080), "ig4x5": (1080, 1350)}
LUFS, LUFS_TOL, TP_MAX = -14.0, 0.5, -1.0
BT709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]


def segments(scenes: list[dict], total_frames: int, n: int, margin: float = 1.0, fps: int = FPS) -> list[tuple[int, int]]:
    """n contiguous [f0, f1) ranges over 0..total_frames. Each even split is moved to the midpoint frame of the scene
    holding it, so it lies >= margin s from every cut (a transition reaches at most 0.5 s either side of its cut)."""
    cuts = [s["end"] for s in scenes[:-1]]
    splits = []
    for k in range(1, n):
        t = k * total_frames / n / fps
        sc = next(s for s in scenes if s["start"] <= t < s["end"])
        f = round((sc["start"] + sc["end"]) / 2 * fps)
        if min((abs(f / fps - c) for c in cuts), default=math.inf) < margin:
            raise ValueError(f"segment split at frame {f} ({sc['id']}) is within {margin} s of a cut")
        if splits and f <= splits[-1]:
            raise ValueError(f"two segment splits fall in scene {sc['id']}: use fewer segments")
        splits.append(f)
    edges = [0, *splits, total_frames]
    return list(zip(edges, edges[1:]))


def seg_path(k: int) -> Path:
    return FILM / f"seg-{k}.mp4"


def render_cmds(segs, scale: int = 1) -> list[list[str]]:
    """The render.ts command for each segment, run in app/ (silent, adaptive samples, under caffeinate)."""
    return [["caffeinate", "-i", "bun", "scripts/render.ts", "video", "--from", f"{f0 / FPS}", "--to", f"{f1 / FPS}",
             "--samples", "auto", "--noaudio", "--scale", str(scale), "--out", f"../out/film/seg-{k}.mp4"]
            for k, (f0, f1) in enumerate(segs)]


def encode_args(kind: str, video: Path, audio: Path, out: Path) -> list[str]:
    """ffmpeg arguments for one output from the silent picture and the mix. Never -itsoffset, -ss or -shortest."""
    head = ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a"]
    if kind == "rough":
        return [*head, "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart",
                str(out)]
    if kind == "web1080":
        return [*head, "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", *BT709,
                "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    if kind in ("ig16x9", "ig4x5"):
        vf = ["-vf", "scale=1080:-2,pad=1080:1350:(ow-iw)/2:(oh-ih)/2:color=0x110d10,setsar=1"] if kind == "ig4x5" else []
        return [*head, *vf, "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-maxrate", "12M", "-bufsize", "24M",
                "-profile:v", "high", "-pix_fmt", "yuv420p", *BT709,
                "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    raise ValueError(f"unknown output kind {kind!r}")


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def frame_count(path: Path) -> int | None:
    try:
        v = [s for s in probe(path)["streams"] if s["codec_type"] == "video"][0]
        return int(v["nb_frames"])
    except (subprocess.CalledProcessError, IndexError, KeyError, ValueError):
        return None


def loudness(path: Path) -> tuple[float, float]:
    """Integrated loudness (LUFS) and true peak (dBTP) of the decoded audio (ffmpeg ebur128)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af",
                        "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    summary = r.stderr[r.stderr.rfind("Summary:"):]
    i = float(re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary).group(1))
    tp = float(re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary).group(1))
    return i, tp


def decode_audio(path: Path, t0: float, t1: float, sr: int = 48000) -> np.ndarray:
    """Mono abs-max of the decoded audio over [t0, t1) (an output filter trim, so the decoder's own timing stands)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-af",
                        f"atrim=start={t0}:end={t1}", "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"],
                       capture_output=True, check=True)
    x = np.frombuffer(r.stdout, np.float32).reshape(-1, 2)
    return np.abs(x).max(1)


def onset_near(path: Path, t: float, window: float = 0.15, hop: float = 0.002) -> float:
    """The time of the sharpest rise in the audio's 2 ms envelope within t ± window: where a hit lands."""
    sr = 48000
    m = decode_audio(path, t - window, t + window, sr)
    w = int(hop * sr)
    env = np.array([m[i:i + w].max() for i in range(0, len(m) - w + 1, w)])
    j = int(np.diff(env).argmax()) + 1
    return t - window + j * hop


def snap_frames() -> tuple[int, int]:
    """(the first frame at or after thread_snap's cue, B01's first frame with the thread in two)."""
    cue = next(c for c in json.loads((DATA / "sfx.json").read_text())["cues"] if c["sound"] == "thread_snap")
    tr = json.loads((DATA / "track" / "b01_thread.json").read_text())
    L, R = tr["anchors"]["end_l"], tr["anchors"]["end_r"]
    plate = next(f for f in range(len(L)) if math.dist(L[f][:2], R[f][:2]) > 1.0) + tr["f0"]
    return math.ceil(cue["t"] * FPS - 1e-6), plate


def check(path: Path, kind: str, expect_frames: int = 2808, expect_seconds: float = 93.6) -> list[str]:
    """Problems with one output (an empty list when it is right)."""
    if not path.exists():
        return [f"{path.name}: missing"]
    p = probe(path)
    probs: list[str] = []
    vs = [s for s in p["streams"] if s["codec_type"] == "video"]
    aus = [s for s in p["streams"] if s["codec_type"] == "audio"]
    if len(vs) != 1 or len(aus) != 1:
        return [f"{path.name}: {len(vs)} video and {len(aus)} audio streams, expected one each"]
    v, a = vs[0], aus[0]
    tol = 1 / FPS
    if int(v.get("nb_frames", -1)) != expect_frames:
        probs.append(f"frames: {v.get('nb_frames')} != {expect_frames}")
    if v.get("r_frame_rate") != f"{FPS}/1" or v.get("avg_frame_rate") != f"{FPS}/1":
        probs.append(f"fps: {v.get('r_frame_rate')} / avg {v.get('avg_frame_rate')} != {FPS}")
    if (v["width"], v["height"]) != SIZES[kind]:
        probs.append(f"size: {v['width']}x{v['height']} != {SIZES[kind][0]}x{SIZES[kind][1]}")
    for name, s in (("video", v), ("audio", a)):
        d = float(s.get("duration", "nan"))
        if not abs(d - expect_seconds) <= tol:
            probs.append(f"{name} duration: {d:.4f} s != {expect_seconds} ± {tol:.4f}")
        st = float(s.get("start_time", "nan"))
        if not abs(st) < 1e-3:
            probs.append(f"{name} start_time: {st} != 0")
    fd = float(p["format"].get("duration", "nan"))
    if not abs(fd - expect_seconds) <= tol:
        probs.append(f"container duration: {fd:.4f} s != {expect_seconds} ± {tol:.4f}")
    for tag in ("color_space", "color_primaries", "color_transfer"):
        if v.get(tag) != "bt709":
            probs.append(f"BT.709: {tag} is {v.get(tag)}")
    if int(a.get("sample_rate", 0)) != 48000 or int(a.get("channels", 0)) != 2:
        probs.append(f"audio: {a.get('sample_rate')} Hz × {a.get('channels')} ch, expected 48000 Hz stereo")
    i, tp = loudness(path)
    if not abs(i - LUFS) <= LUFS_TOL:
        probs.append(f"loudness: {i:.1f} LUFS, outside {LUFS} ± {LUFS_TOL}")
    if tp > TP_MAX:
        probs.append(f"true peak: {tp:.1f} dBTP > {TP_MAX}")
    if expect_frames == 2808:  # the film: the snap is heard on the frame the thread breaks
        cue_f, plate_f = snap_frames()
        if cue_f != plate_f:
            probs.append(f"snap: thread_snap's cue frame {cue_f} != B01's snap frame {plate_f}")
        cue_t = next(c["t"] for c in json.loads((DATA / "sfx.json").read_text())["cues"] if c["sound"] == "thread_snap")
        hit = onset_near(path, cue_t)
        if abs(hit - cue_t) > tol:
            probs.append(f"snap: the audio's hit at {hit:.3f} s, cue at {cue_t:.3f} s (> 1 frame)")
    return [f"{path.name}: {x}" for x in probs]


def describe(path: Path) -> str:
    p = probe(path)
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    i, tp = loudness(path)
    return (f"{path.relative_to(OUT.parent)}  {v['width']}x{v['height']}  {v.get('nb_frames')} frames  "
            f"{float(p['format']['duration']):.3f} s  {i:.1f} LUFS  {tp:.1f} dBTP")


def run_render(n: int, scale: int) -> int:
    vo = json.loads((DATA / "vo.json").read_text())
    total = round(vo["duration"] * FPS)
    segs = segments(vo["scenes"], total, n)
    FILM.mkdir(parents=True, exist_ok=True)
    for k, (cmd, (f0, f1)) in enumerate(zip(render_cmds(segs, scale), segs)):
        if frame_count(seg_path(k)) == f1 - f0:
            print(f"seg-{k}: frames {f0}…{f1 - 1} already rendered, skipped", flush=True)
            continue
        print(f"seg-{k}: frames {f0}…{f1 - 1}  ({' '.join(cmd)})", flush=True)
        r = subprocess.run(cmd, cwd=APP)
        if r.returncode != 0 or frame_count(seg_path(k)) != f1 - f0:
            print(f"seg-{k} FAILED (exit {r.returncode}); see {seg_path(k)}.progress", file=sys.stderr)
            return 1
    print("all segments rendered")
    return 0


def run_assemble(n: int, mix: Path) -> int:
    vo = json.loads((DATA / "vo.json").read_text())
    segs = segments(vo["scenes"], round(vo["duration"] * FPS), n)
    for k, (f0, f1) in enumerate(segs):
        if frame_count(seg_path(k)) != f1 - f0:
            print(f"seg-{k} is missing or not {f1 - f0} frames: run film-deliver render", file=sys.stderr)
            return 1
    lst = FILM / "concat.txt"
    lst.write_text("".join(f"file '{seg_path(k)}'\n" for k in range(len(segs))))
    video = FILM / "video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    str(video)], check=True)
    for kind, out in OUTPUTS.items():
        out.parent.mkdir(parents=True, exist_ok=True)
        print(f"encoding {kind} → {out.relative_to(OUT.parent)}", flush=True)
        subprocess.run(encode_args(kind, video, mix, out), check=True)
    stems = FILM / "stems"
    stems.mkdir(parents=True, exist_ok=True)
    for s in ("mix", "vo", "music", "sfx"):
        src = mix if s == "mix" else mix.parent / f"{s}.wav"
        if not src.exists():
            print(f"stem {src} is missing", file=sys.stderr)
            return 1
        shutil.copy2(src, stems / f"{s}.wav")
    return run_check()


def run_check() -> int:
    bad = 0
    for kind, out in OUTPUTS.items():
        probs = check(out, kind)
        if out.exists():
            print(describe(out))
        for x in probs:
            print(f"  PROBLEM {x}")
        bad += len(probs)
    print("no problems" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="film-deliver", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("segments", "render", "assemble"):
        s = sub.add_parser(name)
        s.add_argument("--segments", type=int, default=4)
        if name == "render":
            s.add_argument("--scale", type=int, default=1)
        if name == "assemble":
            s.add_argument("--mix", type=Path, default=AUDIO / "mix" / "mix.wav")
    sub.add_parser("check")
    a = ap.parse_args(argv)
    if a.cmd == "segments":
        vo = json.loads((DATA / "vo.json").read_text())
        for k, (f0, f1) in enumerate(segments(vo["scenes"], round(vo["duration"] * FPS), a.segments)):
            print(f"seg-{k}: frames {f0}…{f1 - 1} ({f1 - f0}), {f0 / FPS:.3f}–{f1 / FPS:.3f} s")
        return 0
    if a.cmd == "render":
        return run_render(a.segments, a.scale)
    if a.cmd == "assemble":
        return run_assemble(a.segments, a.mix.resolve())
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
