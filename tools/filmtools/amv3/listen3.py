"""Listen-check proxies for the v3 mix: v2's picture (same cut frames) with the new mix, frame numbers burnt in.

    PYTHONPATH=tools python -m filmtools.amv3.listen3 [--video <v2 mp4>] [--mix <mix.wav>] [--out <dir>]
        [--cuts C04,C08,C14,C17,C24,C27,C32] [--full]

Per cut: `<out>/<id>_<type>_f<w0-30>-<w1+30>.mp4` (960x540, the window +-1 s), with the frame number, the cut id/type
and a red frame on the cut frame and a thin amber one over the window. `--full`: the whole 30 s the same way
(`<out>/full_v3mix.mp4`). The picture is v2's (v3's stage is not rendered yet): the cut frames, voice and hits are the
same, so these check the sync and the balance, not the look. Needs only ffmpeg (imageio-ffmpeg's, or `ffmpeg` on PATH)
and Pillow; no drawtext.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from filmtools.amv3 import mix3 as M

W, H = 960, 540
VIDEO = "/home/nikhil/code/film-making/deliverables/Timeless_v2_SAU_EDITZ/Timeless_v2_SAU_EDITZ.mp4"
DEFAULT_CUTS = "C01,C02,C04,C08,C14,C17,C24,C25,C27,C32"


def ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return shutil.which("ffmpeg")


def font(size: int):
    for p in ("/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def render(video: str, mix: str, out: Path, f0: int, f1: int, fps: int, label, cuts: list[dict]):
    """Frames [f0, f1) of `video` at 960x540 with the overlay, muxed with mix.wav over the same time range."""
    ff = ffmpeg()
    n = f1 - f0
    dec = subprocess.Popen([ff, "-v", "error", "-ss", f"{(f0 - 0.25) / fps:.6f}", "-i", video,   # first frame = f0 "-frames:v", str(n),
                            "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen([ff, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(fps), "-i", "-", "-ss", f"{f0 / fps:.6f}", "-t", f"{n / fps:.6f}", "-i", mix,
                            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest", str(out)],
                           stdin=subprocess.PIPE)
    big, small = font(30), font(18)
    for i in range(n):
        buf = dec.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        f = f0 + i
        im = Image.fromarray(np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy())
        d = ImageDraw.Draw(im)
        for T in cuts:
            if T["w0"] <= f < T["w1"]:
                d.rectangle([2, 2, W - 3, H - 3], outline=(255, 176, 0), width=3)
            if f == T["f"]:
                d.rectangle([0, 0, W - 1, H - 1], outline=(255, 30, 30), width=12)
        d.rectangle([0, H - 44, W, H], fill=(0, 0, 0))
        d.text((12, H - 40), f"f{f:03d}", font=big, fill=(255, 255, 255))
        here = [T for T in cuts if T["w0"] - 30 <= f < T["w1"] + 30]
        txt = label(f, here)
        d.text((150, H - 34), txt, font=small, fill=(255, 210, 120))
        enc.stdin.write(im.tobytes())
    enc.stdin.close()
    enc.wait()
    dec.wait()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edl", default=str(M.ROOT / "films/timeless/amv3/edl.json"))
    ap.add_argument("--video", default=VIDEO)
    ap.add_argument("--mix", default=str(M.OUT / "mix.wav"))
    ap.add_argument("--out", default=str(M.OUT / "listen3"))
    ap.add_argument("--cuts", default=DEFAULT_CUTS)
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args(argv)
    E = json.loads(Path(a.edl).read_text())
    fps = E["fps"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    def label(f, here):
        if not here:
            return ""
        T = min(here, key=lambda t: 0 if t["w0"] <= f < t["w1"] else min(abs(f - t["w0"]), abs(f - t["w1"])))
        rel = f - T["f"]
        return f"{T['id']} {T['type']}  cut f{T['f']} ({rel:+d})  window [{T['w0']},{T['w1']})"

    made = []
    for cid in [c for c in a.cuts.split(",") if c]:
        T = next(t for t in E["cuts"] if t["id"] == cid)
        f0, f1 = max(0, T["w0"] - 30), min(E["dur"], (T["w1"] if T["type"] != "triptych" else T["w1"] + 15) + 30)
        p = out / f"{cid}_{T['type']}_f{f0}-{f1}.mp4"
        render(a.video, a.mix, p, f0, f1, fps, label, E["cuts"])
        made.append(str(p))
    if a.full:
        p = out / "full_v3mix.mp4"
        render(a.video, a.mix, p, 0, E["dur"], fps, label, E["cuts"])
        made.append(str(p))
    print("\n".join(made))


if __name__ == "__main__":
    main()
