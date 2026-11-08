"""A phone take -> the clip the markerless solve wants (docs/MOCAP_PILOT.md, Epic's Video Capture Guidelines):
constant frame rate (phones record VFR; 29.97 vs 30 mismatches fail the ingest) at the source's whole rate (a
24/30/60 fps CFR source keeps it: re-timing 24 to 60 only duplicates frames), H.264 CRF 18, the resolution as shot
unless --height asks for an upscale (an A/B for small performers: it adds pixels, not detail), rotation baked in, no audio (the voice goes to our own face/VO pipeline from the original file), a
unique name per take, an optional trim.

    uv run python -m filmtools.mocap.prep check take.mov
    uv run python -m filmtools.mocap.prep make take.mov out/host_t01.mp4 [--start 3.2] [--dur 20] [--fps N] [--height 1080]

`check` prints what the guidelines would flag (not the framing: that is by eye, on the private copy only; an
operator take shows their face and never leaves private storage).
"""
from __future__ import annotations

import argparse
import json
import subprocess
from fractions import Fraction

MIN_SHORT_SIDE = 1080  # HD or 4K
WANT_FPS = 60


def probe(path: str) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def video_stream(info: dict) -> dict:
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            return s
    raise SystemExit("no video stream")


def rotation(s: dict) -> int:
    for sd in s.get("side_data_list", []) or []:
        if "rotation" in sd:
            return int(round(float(sd["rotation"]))) % 360
    return int(s.get("tags", {}).get("rotate", 0)) % 360


def issues(info: dict) -> list:
    """What the guidelines (and the forum's ingest failures) would flag, from the container's metadata."""
    s = video_stream(info)
    out = []
    w, h = int(s["width"]), int(s["height"])
    if min(w, h) < MIN_SHORT_SIDE:
        out.append(f"resolution {w}x{h}: under HD (want 1920x1080 or 4K)")
    r, a = Fraction(s.get("r_frame_rate", "0/1")), Fraction(s.get("avg_frame_rate", "0/1"))
    if a and r and abs(float(r) - float(a)) > 0.01:
        out.append(f"variable frame rate (r {float(r):.3f} vs avg {float(a):.3f}): `make` re-times it to CFR")
    if a and abs(float(a) - WANT_FPS) > 0.5:
        out.append(f"{float(a):.2f} fps: the guidelines want 60 (30 works, slower motion blurs the hands)")
    if a and abs(float(a) - round(float(a))) > 0.001:
        out.append(f"NTSC rate {float(a):.3f}: `make` writes a whole rate (the 29.97/30 ingest failures)")
    if s.get("codec_name") not in ("h264",):
        out.append(f"codec {s.get('codec_name')}: `make` writes H.264 (Windows Media Foundation reads it)")
    if rotation(s):
        out.append(f"rotation flag {rotation(s)} deg: `make` bakes it into the pixels")
    if s.get("pix_fmt") not in ("yuv420p", "yuvj420p"):
        out.append(f"pixel format {s.get('pix_fmt')} (10-bit/HDR phone video): `make` writes 8-bit yuv420p")
    return out


def whole_fps(info: dict) -> int:
    """The rate `make` writes when none is asked: the source's average rounded to a whole rate (29.97 -> 30)."""
    a = Fraction(video_stream(info).get("avg_frame_rate", "0/1"))
    return int(round(float(a))) if a else WANT_FPS


def make_cmd(src: str, dst: str, start: float | None = None, dur: float | None = None, fps: int = WANT_FPS,
             height: int | None = None) -> list:
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", src]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    # autorotate is ffmpeg's default (the flag is baked in); fps= re-times to a constant whole rate;
    # the HDR -> SDR question is left to the phone (record SDR, see the recording guide)
    vf = f"fps={fps}" + (f",scale=-2:{height}:flags=lanczos" if height else "") + ",format=yuv420p"
    cmd += ["-vf", vf, "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-g", str(fps), "-movflags", "+faststart", "-metadata:s:v", "rotate=0", dst]
    return cmd


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("src")
    m = sub.add_parser("make")
    m.add_argument("src")
    m.add_argument("dst")
    m.add_argument("--start", type=float)
    m.add_argument("--dur", type=float)
    m.add_argument("--fps", type=int, help="default: the source's rate, rounded to a whole rate")
    m.add_argument("--height", type=int, help="upscale to this height (lanczos)")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        found = issues(probe(a.src))
        print("\n".join(found) if found else "ok: nothing in the metadata against the guidelines")
        return
    fps = a.fps or whole_fps(probe(a.src))
    subprocess.run(make_cmd(a.src, a.dst, a.start, a.dur, fps, a.height), check=True)
    left = issues(probe(a.dst))
    print(a.dst, "ok" if not left else left)


if __name__ == "__main__":
    main()
