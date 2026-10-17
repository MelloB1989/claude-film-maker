"""Page-ready preview of a rendered frames folder: a two-pass 3.5 Mb/s 1080p H.264 mp4 (+faststart, AAC mix) and a 6x5 contact sheet.

    python tools/filmtools/amv2/web_preview.py --frames <dir of NNNN.png> [--mix mix.wav] [--fps 30] [--out-dir <dir>] [--name preview]
                                               [--bitrate 3.5M] [--cols 6 --rows 5] [--sheet-only] [--no-sheet]

Frames are `<number>.png` (comp frame numbers, e.g. 0819.png); they must be contiguous. `--mix` is muxed in as AAC; when the
frames start at comp frame N it is cut from N/fps so picture and sound stay on the comp clock (`--mix-offset` overrides, in
seconds; pass `--mix-offset 0` for a mix that already starts at the first frame). Writes `<out-dir>/<name>.mp4` and
`<out-dir>/<name>_sheet.jpg` (default out-dir: the frames folder's parent). Needs ffmpeg on PATH; the sheet needs Pillow.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def find_frames(d: Path):
    fs = sorted(p for p in d.glob("*.png") if p.stem.isdigit())
    if not fs:
        raise SystemExit(f"web_preview: no NNNN.png frames in {d}")
    nums = [int(p.stem) for p in fs]
    gaps = [n for a, n in zip(nums, nums[1:]) if n != a + 1]
    if gaps:
        raise SystemExit(f"web_preview: frames are not contiguous in {d} (gap before {gaps[0]}); render the missing ones first")
    return fs, nums[0], len(fs[0].stem)


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode:
        raise SystemExit(f"web_preview: {' '.join(cmd[:3])} failed\n{r.stdout[-1500:]}")


def encode(frames, start, width, fps, mix, mix_offset, bitrate, out: Path):
    pattern = str(frames[0].parent / f"%0{width}d.png")
    # opaque 1080p yuv420p: alpha (RGBA renders) is flattened onto black, odd sizes are padded to 1920x1080
    vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p"
    src = ["-framerate", str(fps), "-start_number", str(start), "-i", pattern]
    with tempfile.TemporaryDirectory() as td:
        log = str(Path(td) / "pass")
        enc = ["-c:v", "libx264", "-preset", "slow", "-b:v", bitrate, "-maxrate", "5M", "-bufsize", "7M", "-g", str(fps * 2),
               "-vf", vf, "-passlogfile", log]
        run(["ffmpeg", "-y", "-v", "error", *src, *enc, "-pass", "1", "-an", "-f", "null", "/dev/null"])
        ain, amap = [], []
        if mix:
            ain = ["-ss", f"{mix_offset:.4f}", "-i", str(mix)]
            amap = ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        run(["ffmpeg", "-y", "-v", "error", *src, *ain, *enc, "-pass", "2", *amap, "-movflags", "+faststart", str(out)])


def sheet(frames, cols, rows, out: Path, tile_w=320):
    from PIL import Image, ImageDraw
    n = cols * rows
    idx = [round(i * (len(frames) - 1) / (n - 1)) for i in range(n)] if len(frames) >= n else list(range(len(frames)))
    first = Image.open(frames[0])
    th = round(tile_w * first.height / first.width)
    S = Image.new("RGB", (cols * tile_w, rows * th), (0, 0, 0))
    for k, i in enumerate(idx):
        im = Image.open(frames[i]).convert("RGBA")
        bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
        im = Image.alpha_composite(bg, im).convert("RGB").resize((tile_w, th), Image.LANCZOS)
        ImageDraw.Draw(im).text((5, 4), frames[i].stem, fill=(255, 235, 60))
        S.paste(im, ((k % cols) * tile_w, (k // cols) * th))
    S.save(out, quality=88)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="web_preview.py", description=__doc__.split("\n")[0])
    ap.add_argument("--frames", required=True, type=Path)
    ap.add_argument("--mix", type=Path, help="audio to mux (wav/flac/m4a/...)")
    ap.add_argument("--mix-offset", type=float, help="seconds into --mix where the first frame sits (default first_frame / fps)")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--bitrate", default="3.5M")
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--name", default="preview")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--rows", type=int, default=5)
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--sheet-only", action="store_true")
    a = ap.parse_args(argv)
    frames, start, width = find_frames(a.frames)
    out_dir = a.out_dir or a.frames.resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    if not a.sheet_only:
        off = a.mix_offset if a.mix_offset is not None else start / a.fps
        encode(frames, start, width, a.fps, a.mix, off, a.bitrate, out_dir / f"{a.name}.mp4")
        print(f"web_preview: {out_dir / (a.name + '.mp4')} ({len(frames)} frames, {a.bitrate} two-pass)")
    if not a.no_sheet:
        sheet(frames, a.cols, a.rows, out_dir / f"{a.name}_sheet.jpg")
        print(f"web_preview: {out_dir / (a.name + '_sheet.jpg')} ({a.cols}x{a.rows})")


if __name__ == "__main__":
    main()
