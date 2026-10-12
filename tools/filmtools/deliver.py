"""film-deliver: the film rendered in resumable segments, assembled with the final mix, encoded to the outputs film.json
pipeline.deliver names.

  film-deliver segments                       the segment ranges (frames), each split in the middle of a scene
  film-deliver render [--segments N] [--scale S]
                                              renders out/<id>/deliver/seg-<k>.mp4 one after another (silent) with
                                              `bun scripts/render.ts video --film <id>` in app/, skipping any segment
                                              already there with the right frame count; each writes
                                              seg-<k>.mp4.progress while it runs
  film-deliver assemble [--segments N] [--mix path]
                                              concat → out/<id>/deliver/video.mp4; every output under the mix; the stems
                                              copied to out/<id>/deliver/stems/; check() on each output
  film-deliver check                          check() on each output; exit 1 on any problem

Each output lands at out/<id>/<id>-<name>.mp4. An output is {"size": [W, H] (default: the film's own size × scale),
"fit": "pad" (letterboxed in pipeline.deliver.pad, default the theme's bg) or "crop", "codec": "libx264" or "copy" (the render as it is), "crf",
"preset", "maxrate", "bufsize", "profile", "audio_kbps"}. The film's length is its scene windows' duration
(data/timeline.json, else data/vo.json) at film.json fps. The audio is never offset or trimmed (no -itsoffset, no -ss,
no -shortest): the mix and the picture both run that long from 0, and check() measures the lengths instead.

pipeline.deliver.hits lists cue sounds whose hit must land on picture: [{"sound": "door_slam", "frame": 161}]. For each
cue of that sound in data/sfx.json, check() finds the hit in the effects stem and lines the output's audio up against
the mix there; the hit as the output plays it must land within a frame of the cue (and the cue on `frame`, if given).
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

from . import cli, config, paths, timeline

FPS = 30
BT709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
OUTPUT_DEFAULTS = {"size": None, "fit": "pad", "codec": "libx264", "crf": 17, "preset": "slow", "maxrate": None,
                   "bufsize": None, "profile": "high", "audio_kbps": 320}
LUFS_TOL = 0.5


def output_spec(spec: dict | None) -> dict:
    s = {**OUTPUT_DEFAULTS, **(spec or {})}
    unknown = set(s) - set(OUTPUT_DEFAULTS)
    if unknown:
        raise SystemExit(f"pipeline.deliver.outputs: unknown {', '.join(sorted(unknown))} "
                         f"(known: {', '.join(OUTPUT_DEFAULTS)})")
    if s["fit"] not in ("pad", "crop"):
        raise SystemExit(f"pipeline.deliver.outputs: fit must be 'pad' or 'crop', not {s['fit']!r}")
    if s["codec"] not in ("libx264", "copy"):
        raise SystemExit(f"pipeline.deliver.outputs: codec must be 'libx264' or 'copy', not {s['codec']!r}")
    return s


def output_size(spec: dict, native: tuple[int, int]) -> tuple[int, int]:
    return tuple(spec["size"]) if spec.get("size") else tuple(native)


def output_path(out_dir: Path, film_id: str, name: str) -> Path:
    return out_dir / f"{film_id}-{name}.mp4"


def theme_bg(theme, themes_path: Path | None = None) -> str | None:
    """The `bg` of a film.json theme: a preset name in app/src/engine/themes.json, or {"extends": name, "bg"?: ...}.
    None when it cannot be told."""
    try:
        presets = json.loads((themes_path or paths.APP / "src" / "engine" / "themes.json").read_text())
    except (OSError, ValueError):
        presets = {}
    if isinstance(theme, str):
        return (presets.get(theme) or {}).get("bg")
    if isinstance(theme, dict):
        return theme.get("bg") or (presets.get(theme.get("extends", "")) or {}).get("bg")
    return None


def segments(scenes: list[dict], total_frames: int, n: int, margin: float = 1.0, fps: float = FPS) -> list[tuple[int, int]]:
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


def seg_path(work: Path, k: int) -> Path:
    return work / f"seg-{k}.mp4"


def render_cmds(segs, film_id: str, work: Path, fps: float = FPS, scale: int = 1,
                samples: str | int = "auto") -> list[list[str]]:
    """The render.ts command for each segment, run in app/: silent, at the film's frame rate, under caffeinate where
    there is one (macOS: the machine must not sleep through a long render)."""
    keep_awake = ["caffeinate", "-i"] if shutil.which("caffeinate") else []
    return [[*keep_awake, "bun", "scripts/render.ts", "video", "--film", film_id, "--from", f"{f0 / fps}",
             "--to", f"{f1 / fps}", "--fps", f"{fps:g}", "--samples", str(samples), "--noaudio", "--scale",
             str(scale), "--out", str(seg_path(work, k))]
            for k, (f0, f1) in enumerate(segs)]


def _hex(color: str) -> str:
    c = color.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        raise SystemExit(f"pipeline.deliver.pad must be a #rrggbb colour, not {color!r}")
    return "0x" + c.lower()


def encode_args(spec: dict, video: Path, audio: Path, out: Path, native: tuple[int, int] = (1920, 1080),
                pad: str = "#000000") -> list[str]:
    """ffmpeg arguments for one output from the silent picture and the mix. Never -itsoffset, -ss or -shortest."""
    s = output_spec(spec)
    w, h = output_size(s, native)
    head = ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a"]
    tail = ["-c:a", "aac", "-b:a", f"{int(s['audio_kbps'])}k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    if s["codec"] == "copy":
        if (w, h) != tuple(native):
            raise SystemExit(f"an output with codec 'copy' keeps the render's size {native[0]}x{native[1]}, "
                             f"not {w}x{h}")
        return [*head, "-c:v", "copy", *tail]
    vf = []
    if (w, h) != tuple(native):
        if s["fit"] == "pad":
            vf = ["-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                         f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={_hex(pad)},setsar=1"]
        else:
            vf = ["-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"]
    rate = []
    if s["maxrate"]:
        rate = ["-maxrate", str(s["maxrate"]), "-bufsize", str(s["bufsize"] or s["maxrate"])]
    return [*head, *vf, "-c:v", "libx264", "-preset", s["preset"], "-crf", str(s["crf"]), *rate,
            "-profile:v", s["profile"], "-pix_fmt", "yuv420p", *BT709, *tail]


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


def decode_audio(path: Path, t0: float, t1: float, sr: int = 48000, signed: bool = False) -> np.ndarray:
    """The decoded audio over [t0, t1), mono: abs-max of the channels, or with signed their mean (an output filter
    trim, so the decoder's own timing stands)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-af",
                        f"atrim=start={t0}:end={t1}", "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"],
                       capture_output=True, check=True)
    x = np.frombuffer(r.stdout, np.float32).reshape(-1, 2)
    return x.mean(1) if signed else np.abs(x).max(1)


def onset_near(path: Path, t: float, window: float = 0.15, hop: float = 0.002) -> float:
    """The time of the sharpest rise in the audio's 2 ms envelope within t ± window: where a hit lands."""
    sr = 48000
    m = decode_audio(path, t - window, t + window, sr)
    w = int(hop * sr)
    env = np.array([m[i:i + w].max() for i in range(0, len(m) - w + 1, w)])
    j = int(np.diff(env).argmax()) + 1
    return t - window + j * hop


def lag_against(path: Path, ref: Path, t: float, window: float = 0.5, search: float = 0.1) -> float:
    """How late (s) path's audio plays against ref's around t: the cross-correlation peak of the two, ±search."""
    sr = 48000
    a = decode_audio(path, t - window - search, t + window + search, sr, signed=True)
    b = decode_audio(ref, t - window, t + window, sr, signed=True)
    n = int(search * sr)
    scores = [float(np.dot(a[k:k + len(b)], b)) for k in range(0, 2 * n + 1)]
    return (int(np.argmax(scores)) - n) / sr


def hit_cues(hits: list[dict], sheet: dict) -> list[dict]:
    """The cues pipeline.deliver.hits names: {sound, t, frame (expected, or None)} per cue of each listed sound."""
    out = []
    for h in hits:
        cues = [c for c in sheet.get("cues", []) if c["sound"] == h["sound"]]
        if not cues:
            raise SystemExit(f"pipeline.deliver.hits: no cue of sound {h['sound']!r} in data/sfx.json")
        out += [{"sound": h["sound"], "t": float(c["t"]), "frame": h.get("frame")} for c in cues]
    return out


def check(path: Path, size: tuple[int, int], expect_frames: int, expect_seconds: float, fps: float = FPS,
          lufs: float = -14.0, tp_max: float = -1.0, hits: list[dict] | None = None,
          stems: Path | None = None) -> list[str]:
    """Problems with one output (an empty list when it is right): one video and one audio stream, the frame count,
    rate, size and BT.709 tags, both streams and the container `expect_seconds` long from 0 (within a frame), 48 kHz
    stereo audio at `lufs` (±0.5 LU) under `tp_max` dBTP. For each of `hits` (hit_cues), the hit found in the effects
    stem (stems/sfx.wav; in the mix a voice may mask it) with the output's audio lined up against stems/mix.wav there,
    must land within a frame of the cue, and the cue on its expected frame."""
    if not path.exists():
        return [f"{path.name}: missing"]
    p = probe(path)
    probs: list[str] = []
    vs = [s for s in p["streams"] if s["codec_type"] == "video"]
    aus = [s for s in p["streams"] if s["codec_type"] == "audio"]
    if len(vs) != 1 or len(aus) != 1:
        return [f"{path.name}: {len(vs)} video and {len(aus)} audio streams, expected one each"]
    v, a = vs[0], aus[0]
    tol = 1 / fps
    rate = f"{fps:g}/1" if float(fps).is_integer() else None
    if int(v.get("nb_frames", -1)) != expect_frames:
        probs.append(f"frames: {v.get('nb_frames')} != {expect_frames}")
    if rate and (v.get("r_frame_rate") != rate or v.get("avg_frame_rate") != rate):
        probs.append(f"fps: {v.get('r_frame_rate')} / avg {v.get('avg_frame_rate')} != {fps:g}")
    if (v["width"], v["height"]) != tuple(size):
        probs.append(f"size: {v['width']}x{v['height']} != {size[0]}x{size[1]}")
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
    if not abs(i - lufs) <= LUFS_TOL:
        probs.append(f"loudness: {i:.1f} LUFS, outside {lufs} ± {LUFS_TOL}")
    if tp > tp_max:
        probs.append(f"true peak: {tp:.1f} dBTP > {tp_max}")
    for h in hits or []:
        cue_f = math.ceil(h["t"] * fps - 1e-6)
        if h.get("frame") is not None and cue_f != h["frame"]:
            probs.append(f"hit: {h['sound']}'s cue frame {cue_f} != its picture frame {h['frame']}")
        if stems is None:
            continue
        heard = onset_near(stems / "sfx.wav", h["t"]) + lag_against(path, stems / "mix.wav", h["t"])
        if abs(heard - h["t"]) > tol:
            probs.append(f"hit: {h['sound']} heard at {heard:.3f} s, cue at {h['t']:.3f} s (> 1 frame)")
    return [f"{path.name}: {x}" for x in probs]


def describe(path: Path) -> str:
    p = probe(path)
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    i, tp = loudness(path)
    return (f"{path}  {v['width']}x{v['height']}  {v.get('nb_frames')} frames  "
            f"{float(p['format']['duration']):.3f} s  {i:.1f} LUFS  {tp:.1f} dBTP")


class Delivery:
    """One film's delivery: its frame rate, length, native size, work folder and outputs."""

    def __init__(self, film: config.Film, scale: int | None = None):
        self.film = film
        d = film.deliver
        self.fps = film.fps
        self.scale = int(scale if scale is not None else d["scale"])
        w, h = film.size
        self.native = (w * self.scale, h * self.scale)
        windows = timeline.require(film.paths.data)
        self.scenes = windows["scenes"]
        self.frames = round(windows["duration"] * self.fps)
        self.seconds = self.frames / self.fps
        self.work = film.paths.out / "deliver"
        self.pad = d["pad"] or theme_bg(film.raw.get("theme")) or "#000000"
        self.outputs = {name: output_spec(spec) for name, spec in d["outputs"].items()}
        if not self.outputs:
            raise SystemExit(f"no outputs: list them in pipeline.deliver.outputs in {film.paths.config}")

    def path(self, name: str) -> Path:
        return output_path(self.film.paths.out, self.film.id, name)

    def segs(self, n: int) -> list[tuple[int, int]]:
        return segments(self.scenes, self.frames, n, fps=self.fps)


def run_render(dl: Delivery, n: int) -> int:
    segs = dl.segs(n)
    dl.work.mkdir(parents=True, exist_ok=True)
    cmds = render_cmds(segs, dl.film.id, dl.work, dl.fps, dl.scale, dl.film.deliver["samples"])
    for k, (cmd, (f0, f1)) in enumerate(zip(cmds, segs)):
        if frame_count(seg_path(dl.work, k)) == f1 - f0:
            print(f"seg-{k}: frames {f0}…{f1 - 1} already rendered, skipped", flush=True)
            continue
        print(f"seg-{k}: frames {f0}…{f1 - 1}  ({' '.join(cmd)})", flush=True)
        r = subprocess.run(cmd, cwd=paths.APP)
        if r.returncode != 0 or frame_count(seg_path(dl.work, k)) != f1 - f0:
            print(f"seg-{k} FAILED (exit {r.returncode}); see {seg_path(dl.work, k)}.progress", file=sys.stderr)
            return 1
    print("all segments rendered")
    return 0


def run_assemble(dl: Delivery, n: int, mix: Path) -> int:
    segs = dl.segs(n)
    for k, (f0, f1) in enumerate(segs):
        if frame_count(seg_path(dl.work, k)) != f1 - f0:
            print(f"seg-{k} is missing or not {f1 - f0} frames: run film-deliver render", file=sys.stderr)
            return 1
    lst = dl.work / "concat.txt"
    lst.write_text("".join(f"file '{seg_path(dl.work, k)}'\n" for k in range(len(segs))))
    video = dl.work / "video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    str(video)], check=True)
    for name, spec in dl.outputs.items():
        out = dl.path(name)
        out.parent.mkdir(parents=True, exist_ok=True)
        print(f"encoding {name} → {out}", flush=True)
        subprocess.run(encode_args(spec, video, mix, out, dl.native, dl.pad), check=True)
    stems = dl.work / "stems"
    stems.mkdir(parents=True, exist_ok=True)
    for s in ("mix", "vo", "music", "sfx"):
        src = mix if s == "mix" else mix.parent / f"{s}.wav"
        if not src.exists():
            print(f"stem {src} is missing", file=sys.stderr)
            return 1
        shutil.copy2(src, stems / f"{s}.wav")
    return run_check(dl)


def run_check(dl: Delivery) -> int:
    from .sfx import load_sheet
    mix = dl.film.mix
    hits = hit_cues(dl.film.deliver["hits"], load_sheet()) if dl.film.deliver["hits"] else []
    stems = dl.work / "stems"
    bad = 0
    for name, spec in dl.outputs.items():
        out = dl.path(name)
        probs = check(out, output_size(spec, dl.native), dl.frames, dl.seconds, dl.fps, mix["lufs"],
                      mix["true_peak"], hits, stems if stems.is_dir() else None)
        if out.exists():
            print(describe(out))
        for x in probs:
            print(f"  PROBLEM {x}")
        bad += len(probs)
    print("no problems" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


def main(argv=None):
    ap = cli.parser(__doc__.split("\n")[0], prog="film-deliver", formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("segments", "render", "assemble", "check"):
        s = sub.add_parser(name)
        if name != "check":
            s.add_argument("--segments", type=int, help="how many segments (default: pipeline.deliver.segments)")
        if name != "segments":
            s.add_argument("--scale", type=int, help="render scale (default: pipeline.deliver.scale)")
        if name == "assemble":
            s.add_argument("--mix", type=Path, help="the final mix (default: film.json audio.mix)")
    a = cli.parse(ap, argv)
    film = config.load()
    dl = Delivery(film, getattr(a, "scale", None))
    n = getattr(a, "segments", None) or int(film.deliver["segments"])
    if a.cmd == "segments":
        for k, (f0, f1) in enumerate(dl.segs(n)):
            print(f"seg-{k}: frames {f0}…{f1 - 1} ({f1 - f0}), {f0 / dl.fps:.3f}–{f1 / dl.fps:.3f} s")
        return 0
    if a.cmd == "render":
        return run_render(dl, n)
    if a.cmd == "assemble":
        return run_assemble(dl, n, (a.mix or film.mix_path).resolve())
    return run_check(dl)


if __name__ == "__main__":
    sys.exit(main())
