"""Post and delivery for the karma launch reel (PLAN.md §5 "Renders", task R6): the rendered frames and the mix in,
the deliverables out. ffmpeg does the picture and the sound; Pillow draws the title lockup and the captions as
transparent overlays (Geist from fonts/src, the Samarkan wordmark from props/out/karma_halo.png).

    cd tools && uv run --with pillow python ../films/host-studio/reel/cut.py FRAMES --mix MIX.wav [--out DIR]
    cd tools && uv run --with pillow python ../films/host-studio/reel/cut.py FRAMES --score SCORE.wav \\
        --vo L1=l1.wav --vo L2=l2.wav --vo L3=l3.wav --vo L4=l4.wav
    ... cut.py FRAMES --score SCORE.wav --cues out/host-studio/reel/vo/cues.json   the VO as R4's vo.py built it
    ... cut.py FRAMES --mix films/host-studio/reel/audio/mix/mix.wav --cues .../vo/cues.json   the delivery: R5's mix,
                                              the captions on R4's words (--cues only times them; the mix has the VO)
    ... cut.py --test-frames DIR [--scale 0.25]      synthetic placeholder frames (a slate per shot) to cut with

FRAMES holds the renders as Movie Render Queue writes them, <dir>/<frame:04d>.png (--pattern to change it): one
directory per shot (FRAMES/S01/ ...) or one flat directory. Frame numbers are the master sequence's (S03 = 0240-0299)
or the shot's own (0000-0059); --frame-offset N when they are numbered from somewhere else (a render from the
sequence's handle at f-12 that starts its numbering at 0: --frame-offset 12). Frames outside a shot (the 12-frame
handles) are ignored. A missing frame is an error unless --fill slate stands a slate in for it (an animatic cut from
part of the renders).

Out (DIR, default films/host-studio/reel/out/):

    karma-reel-2160p-textless-prores4444.mov  the master: ProRes 4444 XQ-class 10-bit 4:4:4, PCM 24-bit; graded,
                                              no title, no captions, no fade (re-versioning starts here)
    karma-reel-2160p-h264.mp4                 16:9 3840x2160, title and fade; captions as the SRT beside it
    karma-reel-2160p-hevc.mp4                 the same, HEVC Main10 (hvc1, plays on Apple devices)
    karma-reel-1080p-h264.mp4                 16:9 1920x1080, title, captions burned in (social)
    karma-reel-9x16-h264.mp4                  9:16 1080x1920 from each shot's vcrop window, vertical title and
                                              captions burned in, inside the Reels/TikTok/Shorts safe area
    karma-reel.srt, karma-reel.vtt            the captions as text
    overlays/                                 the title and caption overlays, for review
    cut.json                                  what was made: loudness, sizes, frames, the source of every shot

The sound: --mix is the finished mix (R5's mix.py: -14 LUFS, -1 dBTP), re-measured and only re-mastered if it is off;
or --score plus the voice lines (--vo L1=...), each placed at its line's frame (LINES below), or R4's cues.json (--cues:
every line's WAV beside it, placed at its file_frame, L4 in two voices as L4a/L4b), the score ducked under them and
mastered to -14 LUFS with filmtools.mix (static gain + limiter). Either is trimmed or padded to the picture's
exact length: picture and sound both start at frame 0 and end together. With --cues the captions are timed by the
spoken words (each cue from its first word to its last, then held); without it, by characters across LINES' windows.

--edl 45s makes the short cut (EDLS below; or --edl A:B,C:D,... master frames): the picture's pieces in order, the
title, captions, fade and the 9:16 crop keys kept on their frames, the sound a mix made for the cut or the full mix cut
on the same edits; the outputs are named karma-reel-45s-... and cut-45s.json. --frames A:B (master frames, B
exclusive) or --shots S13-S18 cuts part of the reel (a test, a review): the title,
captions and fade keep their places on the master's clock. --scale S makes everything S times the size (a quick look);
--only picks outputs by name (prores, 2160p, hevc, 1080p, vertical).
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
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from shots import BEAT, FPS, SHOTS, bar  # noqa: E402

ROOT = HERE.parents[2]
GEIST = ROOT / "fonts" / "src" / "Geist[wght].ttf"
WORDMARK = HERE.parent / "props" / "out" / "karma_halo.png"
OUT = HERE / "out"
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")

W, H = 3840, 2160              # the master
VW, VH = 1080, 1920            # the 9:16 cut: a (H*9/16 = 1215)-px window of the master, scaled
TOTAL = SHOTS[-1].end          # 1560 frames, 65.0 s
FADE_OUT = (TOTAL - FPS, TOTAL)  # f1536-1559: the fade to black on the halo
TITLE_IN = (bar(25, 2), bar(25, 4) + BEAT)  # the title fades in over bar 25 beats 2-4 (f1455-1500)
LUFS, TRUE_PEAK = -14.0, -1.0

# The voice lines (PLAN.md §2, "Voice lines"; the operator approved the copy as written). Frames on the master's clock:
# [first, last) of the line's speech; the captions follow the words.
LINES = {
    "L1": (930, 1080, "This is karma. Everything on these shelves is a story — seven of them, built one late night "
                      "at a time."),
    "L2": (1110, 1150, "She'll tell you the next one."),
    "L3": (1158, 1310, "Tech, explained the way we'd want it explained: calm, honest, and made right here."),
    "L4": (1360, 1410, "Welcome… to karma."),
}
# The short cut (PLAN.md §7 q4): master frames kept, in order, all on bar lines. The plan's list (drop S01, S05, S07,
# S09; a bar off S13 and S17) comes to 47.5 s and its S17 bar would cut through L4 (f1360-1403 spans both its bars), so:
# S02's first bar, S03-S04, S08, S10-S12, S13's second bar (L1 starts at f930), S14-S18; S06 goes too (the coin and
# pickaxe still show in the wider shots; S10's artists are a shout-out the operator wants). 45.0 s.
EDLS = {"45s": [(120, 180), (240, 360), (540, 600), (660, 840), (900, 1560)]}
XFADE = 0.012  # s: the equal-power crossfade at each sound edit, centred on the cut

# The title lockup, as the operator chose it (PLAN.md §7 q2): the wordmark, then "a studio by MelloB". None drops a
# line; "date" adds a small tracked line under it.
TITLE = {"wordmark": True, "line": "a studio by MelloB", "date": None}

# 9:16 crop keys that override shots.py's single vcrop: {shot: [[frame offset in the shot, centre 0..1], ...]}, eased
# between keys. S15 follows the focus pull: him (sharp, frame-left) until bar 20, her once the pull lands (agent-10's
# framing note, R3). DRAFT until the animatic shows the real framings.
VCROP_KEYS = {"S15": [[0, 0.20], [60, 0.20], [78, 0.68]]}

BT709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
X264 = ["-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-pix_fmt", "yuv420p", "-g", "48", "-bf", "2"]
AAC = ["-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart"]


@dataclass
class Output:
    name: str
    file: str
    vertical: bool = False
    title: bool = True
    captions: bool = False
    fade: bool = True
    height: int = H            # the output's height at scale 1 (16:9); a vertical output is VW x VH
    codec: tuple = ()
    depth: int = 8             # the overlay/fade pipeline's output depth before the encoder's pix_fmt

    def size(self, scale: float) -> tuple[int, int]:
        w, h = (VW, VH) if self.vertical else (self.height * 16 // 9, self.height)
        return even(w * scale), even(h * scale)


OUTPUTS = [
    Output("2160p", "karma-reel-2160p-h264.mp4",
           codec=(*X264, "-crf", "16", "-maxrate", "45M", "-bufsize", "90M", "-level:v", "5.1", *AAC)),
    Output("hevc", "karma-reel-2160p-hevc.mp4", depth=10,
           codec=("-c:v", "libx265", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p10le", "-profile:v",
                  "main10", "-tag:v", "hvc1", "-x265-params",
                  "vbv-maxrate=40000:vbv-bufsize=80000:colorprim=bt709:transfer=bt709:colormatrix=bt709:log-level=error",
                  *AAC)),
    Output("1080p", "karma-reel-1080p-h264.mp4", captions=True, height=1080,
           codec=(*X264, "-crf", "17", "-maxrate", "16M", "-bufsize", "32M", "-level:v", "4.2", *AAC)),
    Output("vertical", "karma-reel-9x16-h264.mp4", vertical=True, captions=True,
           codec=(*X264, "-crf", "17", "-maxrate", "16M", "-bufsize", "32M", "-level:v", "4.2", *AAC)),
]
PRORES = "karma-reel-2160p-textless-prores4444.mov"
# --source 1080p (a 1920x1080 render pass, before the 4K one): the master and every output come from 1080p frames, so
# there is no 4K output, and the 9:16 cut, only a 608-px-wide window of the frame before it is scaled, is a preview.
SOURCES = {"2160p": {"size": (W, H), "skip": set(), "rename": {}},
           "1080p": {"size": (1920, 1080), "skip": {"2160p", "hevc"},
                     "rename": {PRORES: "karma-reel-1080p-textless-prores4444.mov",
                                "karma-reel-9x16-h264.mp4": "karma-reel-9x16-preview-h264.mp4"}}}


def even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def run(args: list, quiet: bool = True) -> subprocess.CompletedProcess:
    cmd = [FFMPEG, "-hide_banner", "-nostats", "-y", *map(str, args)]
    r = subprocess.run(cmd, capture_output=quiet, text=True)
    if r.returncode:
        raise SystemExit(f"ffmpeg failed ({r.returncode}):\n{' '.join(cmd)}\n{(r.stderr or '')[-3000:]}")
    return r


def probe(path: Path) -> dict:
    r = subprocess.run([FFMPEG.replace("ffmpeg", "ffprobe") if FFMPEG.endswith("ffmpeg") else "ffprobe", "-v",
                        "error", "-print_format", "json", "-show_streams", "-show_format", "-count_frames", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


# ---------------------------------------------------------------- the frames


def edl(name: str) -> list:
    """--edl: a name in EDLS or A:B,C:D,... (master frames, each [A, B)); in order, not overlapping."""
    segs = EDLS.get(name) or [tuple(map(int, x.split(":"))) for x in name.split(",")]
    for (a, b), (c, _) in zip(segs, segs[1:] + [(TOTAL, 0)]):
        if not 0 <= a < b <= c <= TOTAL:
            raise SystemExit(f"--edl {name}: {a}:{b} is empty, out of order or outside the reel (0:{TOTAL})")
    return [tuple(x) for x in segs]


def to_out(segs: list, m: float) -> float | None:
    """The output frame of master frame m, None if it was cut."""
    off = 0
    for a, b in segs:
        if a <= m < b:
            return off + m - a
        off += b - a
    return None


def spans_out(segs: list, a: float, b: float) -> list:
    """Master [a, b) on the output clock: one (x, y) per segment it falls in."""
    out, off = [], 0
    for sa, sb in segs:
        lo, hi = max(a, sa), min(b, sb)
        if lo < hi:
            out.append((off + lo - sa, off + hi - sa))
        off += sb - sa
    return out


def span(frames: str | None, shots: str | None) -> tuple[int, int]:
    """The master frames to cut, [first, last)."""
    if frames:
        a, b = frames.split(":")
        f0, f1 = int(a or 0), int(b or TOTAL)
    elif shots:
        ids = [s.id for s in SHOTS]
        a, _, b = shots.upper().partition("-")
        i, j = ids.index(a), ids.index(b or a)
        f0, f1 = SHOTS[i].start, SHOTS[j].end
    else:
        f0, f1 = 0, TOTAL
    if not 0 <= f0 < f1 <= TOTAL:
        raise SystemExit(f"frames {f0}:{f1} are outside the reel (0:{TOTAL})")
    return f0, f1


def shot_at(f: int):
    return next(s for s in SHOTS if s.start <= f < s.end)


def find_frames(root: Path, f0: int, f1: int, pattern: str = "{frame:04d}.png", offset: int = 0) -> dict:
    """{master frame: path or None} for [f0, f1). Per shot: its own directory (root/S03) or root itself; numbered
    on the master's clock (the shot's first frame is s.start) or the shot's own (0), whichever has the shot's frames."""
    found = {}
    for s in SHOTS:
        lo, hi = max(s.start, f0), min(s.end, f1)
        if lo >= hi:
            continue
        best = {}
        for d in ([root / s.id] if (root / s.id).is_dir() else []) + [root]:
            for base in (0, s.start):  # master numbering, then shot-local
                cand = {f: d / pattern.format(frame=f - base + offset) for f in range(lo, hi)}
                hit = {f: p for f, p in cand.items() if p.exists()}
                if len(hit) > len(best):
                    best = hit
            if best:
                break
        found.update({f: best.get(f) for f in range(lo, hi)})
    return found


def slate(path: Path, s, size: tuple[int, int], note: str = "") -> Path:
    """A stand-in frame for a shot: its light state's colour, the shot and its title."""
    from PIL import Image, ImageDraw
    tint = {"DAY": (196, 186, 160), "GOLDEN": (170, 120, 60), "DUSK": (110, 80, 90), "BLUE": (40, 58, 96),
            "IGNITION": (70, 40, 20), "NIGHT": (34, 26, 22), "NIGHT+KEY": (44, 32, 26), "NIGHT-DIM": (26, 20, 17)}
    img = Image.new("RGB", size, tint.get(s.light, (40, 40, 40)))
    d = ImageDraw.Draw(img)
    h = size[1]
    d.text((h * 0.05, h * 0.05), f"{s.id} · {s.title}", font=font(h * 0.06, 600), fill=(240, 236, 228))
    d.text((h * 0.05, h * 0.14), f"{s.light} · {s.lens:g} mm T{s.stop:g} {note}", font=font(h * 0.035, 400),
           fill=(230, 224, 214))
    img.save(path)
    return path


def stage(found: dict, segs: list, work: Path, fill: str | None, size: tuple[int, int]) -> Path:
    """Link the frames in output order (seq/00000.png ...) so ffmpeg reads one image sequence."""
    seq = work / "seq"
    shutil.rmtree(seq, ignore_errors=True)
    seq.mkdir(parents=True)
    missing = sorted(f for f, p in found.items() if p is None)
    if missing and fill != "slate":
        by = {}
        for f in missing:
            by.setdefault(shot_at(f).id, []).append(f)
        raise SystemExit("missing frames (--fill slate to stand a slate in): " +
                         ", ".join(f"{k} {v[0]}-{v[-1]} ({len(v)})" for k, v in by.items()))
    slates = {}
    for f, p in sorted(found.items()):
        if p is None:
            s = shot_at(f)
            if s.id not in slates:
                slates[s.id] = slate(work / f"slate_{s.id}.png", s, size, "(not rendered)")
            p = slates[s.id]
        (seq / f"{to_out(segs, f):05d}.png").symlink_to(Path(p).resolve())
    return seq


def png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as fh:
        head = fh.read(24)
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


# ---------------------------------------------------------------- the 9:16 crop


def vcrop_keys(s) -> list:
    keys = VCROP_KEYS.get(s.id, s.vcrop)
    return [[0, float(keys)]] if isinstance(keys, (int, float)) else [[int(f), float(c)] for f, c in keys]


def crop_x(c: float, src_w: int, crop_w: int) -> float:
    return min(max(c * src_w - crop_w / 2, 0), src_w - crop_w)


def crop_expr(segs: list, src_w: int, crop_w: int) -> str:
    """ffmpeg crop x for output frame n: piecewise over the shots (each piece of a shot the cut keeps), each shot's
    keys eased (smoothstep) between them. Nested if()s; commas escaped for the filter graph."""
    parts, off = [], 0
    for f0, f1 in segs:
        parts += crop_parts(f0, f1, off, src_w, crop_w)
        off += f1 - f0
    out = parts[-1][1]
    for end, expr in reversed(parts[:-1]):
        out = f"if(lt(n\\,{end})\\,{expr}\\,{out})"
    return f"floor({out})"


def crop_parts(f0: int, f1: int, off: int, src_w: int, crop_w: int) -> list:
    """crop_expr's pieces for master [f0, f1), which starts at output frame off: [(output end, expr)]."""
    parts = []
    for s in SHOTS:
        if s.end <= f0 or s.start >= f1:
            continue
        ks = vcrop_keys(s)
        a = off + s.start - f0  # n of the shot's first frame (before the piece, if the cut starts inside the shot)
        expr = f"{crop_x(ks[-1][1], src_w, crop_w):.1f}"
        for (fa, ca), (fb, cb) in reversed(list(zip(ks, ks[1:]))):
            xa, xb = crop_x(ca, src_w, crop_w), crop_x(cb, src_w, crop_w)
            u = f"clip((n-{a + fa})/{fb - fa}\\,0\\,1)"
            expr = f"if(lt(n\\,{a + fb})\\,{xa:.1f}+({xb - xa:.1f})*{u}*{u}*(3-2*{u})\\,{expr})"
        if len(ks) > 1 or ks[0][0]:
            expr = f"if(lt(n\\,{a + ks[0][0]})\\,{crop_x(ks[0][1], src_w, crop_w):.1f}\\,{expr})"
        parts.append((off + min(s.end, f1) - f0, expr))
    return parts


# ---------------------------------------------------------------- titles and captions


def font(size: float, weight: int = 400):
    from PIL import ImageFont
    f = ImageFont.truetype(str(GEIST), max(1, int(round(size))))
    try:
        f.set_variation_by_axes([weight])
    except (OSError, AttributeError):  # a FreeType without variations: the default instance
        pass
    return f


def tracked(draw, xy, text, f, fill, tracking: float = 0.0):
    """Text with letter spacing (tracking in em); returns the advance."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + tracking * f.size
    return x - xy[0] - (tracking * f.size if text else 0)


def tracked_len(text, f, tracking: float = 0.0) -> float:
    return sum(f.getlength(ch) for ch in text) + tracking * f.size * max(0, len(text) - 1)


def shadowed(layer, radius: float, alpha: float = 0.55):
    """A soft dark shadow under a white-on-transparent layer, for legibility on any frame."""
    from PIL import Image, ImageFilter
    a = layer.getchannel("A")
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sh.putalpha(a.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: int(v * alpha)))
    return Image.alpha_composite(sh, layer)


def wordmark(width: int):
    """The karma wordmark, warm white with the sign's amber halo glowing behind it, from the sign's silhouette."""
    from PIL import Image, ImageFilter
    m = Image.open(WORDMARK).convert("L")
    m = m.crop(m.getbbox())
    m = m.resize((width, round(m.height * width / m.width)), Image.LANCZOS)
    pad = int(width * 0.12)
    mask = Image.new("L", (m.width + 2 * pad, m.height + 2 * pad), 0)
    mask.paste(m, (pad, pad))
    glow = mask.filter(ImageFilter.GaussianBlur(width * 0.025)).point(lambda v: min(255, int(v * 1.6)))
    out = Image.new("RGBA", mask.size, (255, 168, 86, 0))
    out.putalpha(glow.point(lambda v: int(v * 0.75)))
    core = Image.new("RGBA", mask.size, (255, 243, 226, 0))
    core.putalpha(mask)
    return Image.alpha_composite(out, core), pad


def title_card(size: tuple[int, int], vertical: bool):
    """The title lockup on a transparent frame-sized canvas, cropped to its box: (image, x, y)."""
    from PIL import Image, ImageDraw
    w, h = size
    unit = w / 1080 if vertical else h / 1080  # 1 px at 1080 lines (16:9) or 1080 columns (9:16)
    parts = []
    if TITLE.get("wordmark"):
        parts.append(("img", *wordmark(int((w * 0.62) if vertical else (w * 0.24)))))
    if TITLE.get("line"):
        parts.append(("text", TITLE["line"], font(34 * unit, 300), (244, 238, 228), 0.14))
    if TITLE.get("date"):
        parts.append(("text", TITLE["date"], font(24 * unit, 500), (214, 176, 128), 0.42))
    gap = 18 * unit
    boxes = []
    for p in parts:
        if p[0] == "img":
            boxes.append((p[1].width, p[1].height - 2 * p[2], 0))
        else:
            asc, desc = p[2].getmetrics()
            boxes.append((int(tracked_len(p[1], p[2], p[4])) + 1, asc + desc, 0))
    tw = max(b[0] for b in boxes)
    th = int(sum(b[1] for b in boxes) + gap * (len(boxes) - 1))
    pad = int(max([40 * unit] + [p[2] for p in parts if p[0] == "img"]))
    img = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = pad
    for p, (bw, bh, _) in zip(parts, boxes):
        x = pad + (tw - bw) // 2
        if p[0] == "img":
            img.alpha_composite(p[1], (x, int(y - p[2])))  # the glow's padding hangs outside the box
            y += bh + gap * 1.4
        else:
            tracked(d, (x, y), p[1], p[2], p[3] + (255,), p[4])
            y += bh + gap
    img = img.crop(img.getbbox())
    img = shadowed(img, 6 * unit, 0.45)
    cy = h * (0.64 if vertical else 0.70)  # under the lit sign, inside the 9:16 safe area
    return img, (w - img.width) // 2, int(cy - img.height / 2)


def read_cues(path: Path) -> dict:
    """R4's cues.json (vo.py build): {line: {"wav": Path, "file_frame": float, "words": [{"w", "start", "end"}]}}."""
    d = json.loads(path.read_text())
    if d.get("fps", FPS) != FPS:
        raise SystemExit(f"{path}: fps {d['fps']}, the reel is {FPS}")
    return {k: {**v, "wav": path.parent / v["wav"]} for k, v in d["lines"].items()}


def line_words(spoken: dict) -> dict:
    """The spoken words per LINES key (L4a and L4b are L4's two voices), in order."""
    out = {}
    for k, v in sorted(spoken.items(), key=lambda kv: kv[1]["words"][0]["start"]):
        key = next((n for n in LINES if k == n or (k.startswith(n) and k[len(n):].isalpha())), None)
        if key is None:
            raise SystemExit(f"cues.json line {k} is not one of {', '.join(LINES)}")
        out.setdefault(key, []).extend(v["words"])
    return out


def alnum(t: str) -> int:
    return sum(ch.isalnum() for ch in t)


def cues(lines: dict = LINES, max_chars: int = 64, hold: int = 6, words: dict | None = None) -> list:
    """The captions: each line split into cues at its clauses (at most max_chars each), each held `hold` frames after
    its words unless the next cue starts first. [(first, last), text]. With `words` (line_words) a cue runs from its
    first spoken word to its last (matched by letters and digits, so the text's punctuation need not match the
    aligner's); otherwise it is timed by characters across the line's frames."""
    out = []
    for name, (first, last, text) in sorted(lines.items(), key=lambda kv: kv[1]):
        phrases = [p for p in re.split(r"(?<=[.,:;?!—…])\s+", text) if p]
        chunks = []
        for p in phrases:
            if chunks and len(chunks[-1]) + 1 + len(p) <= max_chars:
                chunks[-1] += " " + p
            else:
                chunks.append(p)
        ws = (words or {}).get(name)
        if ws:
            if alnum("".join(c for c in chunks)) != alnum("".join(w["w"] for w in ws)):
                raise SystemExit(f"cues.json's words for {name} are not LINES' text: {' '.join(w['w'] for w in ws)!r}")
            i = 0
            for c in chunks:
                need, j = alnum(c), i
                while need > 0:
                    need -= alnum(ws[j]["w"])
                    j += 1
                out.append([round(ws[i]["start"]), round(ws[j - 1]["end"]), c])
                i = j
            continue
        n = sum(len(c) for c in chunks)
        t = first
        for c in chunks:
            dur = round((last - first) * len(c) / n)
            out.append([t, t + dur, c])
            t += dur
        out[-1][1] = last
    for a, b in zip(out, out[1:]):
        a[1] = min(a[1] + hold, b[0])
    out[-1][1] += hold
    return [((a, b), c) for a, b, c in out]


def wrap(text: str, f, width: float) -> list:
    words, rows = text.split(), [""]
    for wd in words:
        t = (rows[-1] + " " + wd).strip()
        if f.getlength(t) <= width or not rows[-1]:
            rows[-1] = t
        else:
            rows.append(wd)
    if len(rows) == 2 and len(rows[1].split()) == 1 and len(rows[0].split()) > 2:  # no widow: balance the two rows
        a = rows[0].split()
        rows = [" ".join(a[:-1]), a[-1] + " " + rows[1]]
    return rows


def caption(text: str, size: tuple[int, int], vertical: bool):
    """One caption: Geist medium, white with a soft shadow, centred; (image, x, y)."""
    from PIL import Image, ImageDraw
    w, h = size
    unit = w / 1080 if vertical else h / 1080
    f = font((50 if vertical else 40) * unit, 500)
    rows = wrap(text, f, w * (0.76 if vertical else 0.62))
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.12)
    pad = int(24 * unit)
    bw = int(max(f.getlength(r) for r in rows)) + 2 * pad
    img = Image.new("RGBA", (bw, lh * len(rows) + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, r in enumerate(rows):
        d.text(((bw - f.getlength(r)) / 2, pad + i * lh), r, font=f, fill=(255, 255, 255, 255))
    img = shadowed(img, 5 * unit, 0.75)
    if vertical:  # centred at 68%: clear of the faces and of the bottom ~20% the apps' UI covers
        y = int(h * 0.68 - img.height / 2)
    else:          # the lower edge at 92%: inside the 16:9 title-safe area
        y = int(h * 0.92 - img.height)
    return img, (w - bw) // 2, y


def srt_time(f: int, sep: str = ",") -> str:
    ms = round(f * 1000 / FPS)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def write_captions(out: Path, cs: list, segs: list) -> None:
    keep = [(ab, t) for (a, b), t in cs for ab in spans_out(segs, a, b)]
    out.with_suffix(".srt").write_text("".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n"
                                               for i, ((a, b), t) in enumerate(keep, 1)))
    out.with_suffix(".vtt").write_text("WEBVTT\n\n" + "".join(f"{srt_time(a, '.')} --> {srt_time(b, '.')}\n{t}\n\n"
                                                               for (a, b), t in keep))


# ---------------------------------------------------------------- the sound


def sound(work: Path, segs: list, mix: Path | None, score: Path | None, vo: list) -> tuple[Path, dict]:
    """The reel's mix for the cut: 48 kHz stereo 24-bit, exactly as long as the picture. vo: [(line, WAV, ms)], each
    WAV starting `ms` into the master. A --mix already the cut's length (a mix made for it) is taken as it is; a
    full-length one is cut on the picture's edits, each a XFADE equal-power crossfade centred on the cut."""
    from filmtools.mix import loudnorm, measure, premix  # the tools env (cd tools && uv run ...)
    full = work / "mix_full.wav"
    n = sum(b - a for a, b in segs)
    if mix and len(segs) > 1 and abs(float(probe(mix)["format"]["duration"]) - n / FPS) < 0.5 / FPS:
        segs = [(0, n)]  # made for this cut
    if mix:
        m = measure(mix)
        if abs(m["I"] - LUFS) > 0.5 or m["TP"] > TRUE_PEAK:
            m = loudnorm(mix, full, LUFS)
            how = f"remastered to {LUFS:g} LUFS"
        else:
            shutil.copy(mix, full)
            how = "the mix as delivered"
    elif score:
        music = score
        if vo:
            ins, graph = [], []
            for k, (name, path, ms) in enumerate(vo):
                ins += ["-i", path]
                graph.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}:all=1[v{k}]")
            graph.append("".join(f"[v{k}]" for k in range(len(vo))) +
                         f"amix=inputs={len(vo)}:normalize=0:duration=longest[vo]")
            vo_track = work / "vo.wav"
            run([*ins, "-filter_complex", ";".join(graph), "-map", "[vo]", "-ar", "48000", "-c:a", "pcm_s24le",
                 vo_track])
            pre = work / "premix.wav"
            premix(vo_track, music, pre)
            music = pre
        m = loudnorm(music, full, LUFS)
        how = f"score{' + VO ' + ','.join(n for n, _, _ in vo) if vo else ''}, mastered to {LUFS:g} LUFS"
    else:
        run(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", TOTAL / FPS, "-c:a", "pcm_s24le", full])
        m, how = {"I": None, "TP": None, "LRA": None}, "silence (no --mix or --score)"
    out = work / "mix.wav"
    d = n / FPS
    if len(segs) == 1:
        a, b = segs[0][0] / FPS, segs[0][1] / FPS
        run(["-i", full, "-af", f"atrim=start={a}:end={b},asetpts=PTS-STARTPTS,apad=whole_dur={b - a},"
             f"atrim=end={b - a}", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", out])
        return out, {"how": how, **m}
    x, graph = XFADE / 2, []
    for i, (a, b) in enumerate(segs):  # each piece runs x past its cut on both inner sides: the crossfades eat 2x each
        lo = a / FPS - (x if i else 0)
        hi = b / FPS + (x if i < len(segs) - 1 else 0)
        graph.append(f"[0:a]atrim=start={lo:.6f}:end={hi:.6f},asetpts=PTS-STARTPTS[p{i}]")
    last = "p0"
    for i in range(1, len(segs)):
        graph.append(f"[{last}][p{i}]acrossfade=d={XFADE}:c1=qsin:c2=qsin[x{i}]")
        last = f"x{i}"
    graph.append(f"[{last}]apad=whole_dur={d},atrim=end={d}[out]")
    cut_ = work / "mix_cut.wav"
    run(["-i", full, "-filter_complex", ";".join(graph), "-map", "[out]", "-ar", "48000", "-ac", "2",
         "-c:a", "pcm_s24le", cut_])
    m = measure(cut_)
    if abs(m["I"] - LUFS) > 0.5 or m["TP"] > TRUE_PEAK:
        m = loudnorm(cut_, out, LUFS)
        how += f"; cut on the picture's {len(segs) - 1} edits, remastered to {LUFS:g} LUFS"
    else:
        shutil.move(cut_, out)
        how += f"; cut on the picture's {len(segs) - 1} edits"
    return out, {"how": how, **m}


# ---------------------------------------------------------------- the picture


def grade_filter(grade: str, lut: Path | None) -> str:
    """Applied to the frames in RGB before they become YUV. 'none' leaves the renders as they are (the plan asks for
    no look beyond the light: Lumen and the exposure keys carry it); 'gentle' is a soft S-curve and a touch of
    saturation."""
    f = []
    if grade == "gentle":
        f += ["curves=master='0/0 0.25/0.235 0.75/0.765 1/1'", "eq=saturation=1.04"]
    if lut:
        f.append(f"lut3d=file='{lut}':interp=tetrahedral")
    return ",".join(f)


def yuv(w: int, h: int) -> str:
    """Scale (if need be) and convert to 10-bit 4:4:4 BT.709 limited range, explicitly: ffmpeg's implicit RGB→YUV
    would use BT.601."""
    return f"scale={w}:{h}:flags=lanczos:out_color_matrix=bt709:out_range=tv,format=yuv444p10le"


def encode(out: Output, src: list, pre: str, src_size: tuple[int, int], audio: Path, segs: list, scale: float,
           cs: list, ovl_dir: Path, path: Path) -> None:
    n = sum(b - a for a, b in segs)
    dur = n / FPS
    w, h = out.size(scale)
    sw, sh = src_size
    chain = [pre] if pre else []
    if out.vertical:
        cw = even(sh * VW / VH) if (sh * VW / VH) % 1 else int(sh * VW / VH)
        chain.append(f"crop=w={cw}:h={sh}:x='{crop_expr(segs, sw, cw)}':y=0")
    chain.append(f"scale={w}:{h}:flags=lanczos,format=yuv444p10le")
    graph = [f"[0:v]{','.join(chain)}[b0]"]
    inputs = [*src]
    last, k = "b0", 1
    overlays = []
    title_at = next((to_out(segs, f) for f in range(*TITLE_IN) if to_out(segs, f) is not None), None)
    if out.title and title_at is not None:
        img, x, y = title_card((w, h), out.vertical)
        p = ovl_dir / f"title_{out.name}.png"
        img.save(p)
        st = title_at / FPS
        overlays.append((p, x, y, f"fade=t=in:st={st:.4f}:d={(TITLE_IN[1] - TITLE_IN[0]) / FPS:.4f}:alpha=1", None))
    if out.captions:
        for i, ((a, b), text) in enumerate(cs):
            spans = spans_out(segs, a, b)
            if not spans:
                continue
            img, x, y = caption(text, (w, h), out.vertical)
            p = ovl_dir / f"cap_{out.name}_{i:02d}.png"
            img.save(p)
            for x0, x1 in spans:
                overlays.append((p, x, y, None, (x0 / FPS, x1 / FPS)))
    for p, x, y, fade, window in overlays:
        inputs += ["-loop", "1", "-framerate", FPS, "-t", f"{dur:.4f}", "-i", p]
        prep = f"[{k}:v]format=rgba{',' + fade if fade else ''},scale=out_color_matrix=bt709:out_range=tv," \
               f"format=yuva444p10le[o{k}]"
        en = f":enable='between(t\\,{window[0]:.4f}\\,{window[1] - 0.001:.4f})'" if window else ""
        graph += [prep, f"[{last}][o{k}]overlay=x={x}:y={y}:format=yuv444p10:eof_action=pass{en}[b{k}]"]
        last, k = f"b{k}", k + 1
    fade_at = next((to_out(segs, f) for f in range(*FADE_OUT) if to_out(segs, f) is not None), None)
    if out.fade and fade_at is not None:
        st = fade_at / FPS
        graph.append(f"[{last}]fade=t=out:st={st:.4f}:d={(FADE_OUT[1] - FADE_OUT[0]) / FPS:.4f}[bf]")
        last = "bf"
    graph.append(f"[{last}]null[v]")
    inputs += ["-i", audio]
    run([*inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", f"{k}:a", "-frames:v", n,
         "-r", FPS, *out.codec, *BT709, "-shortest", path])


def prores(seq: Path, pre: str, audio: Path, n: int, path: Path) -> None:
    run(["-framerate", FPS, "-i", seq / "%05d.png", "-i", audio, "-vf", pre, "-frames:v", n, "-c:v", "prores_ks",
         "-profile:v", "4444", "-pix_fmt", "yuv444p10le", "-vendor", "apl0", "-bits_per_mb", "8000",
         *BT709, "-c:a", "pcm_s24le", "-ar", "48000", path])


def check(path: Path, n: int, size: tuple[int, int]) -> dict:
    info = probe(path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    frames = int(v.get("nb_read_frames") or v.get("nb_frames") or 0)
    adur = float(a["duration"]) if a else 0.0
    problems = []
    if frames != n:
        problems.append(f"{frames} frames, not {n}")
    if (v["width"], v["height"]) != size:
        problems.append(f"{v['width']}x{v['height']}, not {size[0]}x{size[1]}")
    if abs(adur - n / FPS) > 1.5 / FPS:
        problems.append(f"audio {adur:.3f} s against picture {n / FPS:.3f} s")
    return {"file": path.name, "size": f"{v['width']}x{v['height']}", "codec": v["codec_name"],
            "pix_fmt": v.get("pix_fmt"), "frames": frames, "seconds": round(n / FPS, 3),
            "mbps": round(int(info["format"]["bit_rate"]) / 1e6, 1), "mb": round(path.stat().st_size / 1e6, 1),
            "problems": problems}


# ---------------------------------------------------------------- placeholder frames


def test_frames(root: Path, scale: float, f0: int = 0, f1: int = TOTAL) -> None:
    """Placeholder renders: one directory per shot, master numbering, each frame a slate with a moving bar (so a
    dropped or doubled frame shows) and a marker at the shot's 9:16 crop centre."""
    from PIL import Image, ImageDraw
    size = (even(W * scale), even(H * scale))
    for s in SHOTS:
        if s.end <= f0 or s.start >= f1:
            continue
        d = root / s.id
        d.mkdir(parents=True, exist_ok=True)
        base = slate(d / ".slate.png", s, size, "(placeholder)")
        bg = Image.open(base)
        for f in range(max(s.start, f0), min(s.end, f1)):
            img = bg.copy()
            dr = ImageDraw.Draw(img)
            u = (f - s.start) / s.frames
            x = int(u * size[0])
            dr.rectangle([x - 4, size[1] * 0.4, x + 4, size[1] * 0.6], fill=(250, 250, 250))
            ks = vcrop_keys(s)
            c = ks[0][1] if len(ks) == 1 else next((cb for fb, cb in ks if f - s.start <= fb), ks[-1][1])
            dr.ellipse([c * size[0] - 12, size[1] / 2 - 12, c * size[0] + 12, size[1] / 2 + 12], outline=(255, 80, 60),
                       width=4)
            dr.text((size[1] * 0.05, size[1] * 0.85), f"f{f:04d}  {s.id}+{f - s.start:03d}",
                    font=font(size[1] * 0.045, 500), fill=(250, 248, 240))
            img.save(d / f"{f:04d}.png", compress_level=1)
        (d / ".slate.png").unlink()


# ---------------------------------------------------------------- main


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("frames", type=Path, nargs="?", help="the renders: <dir>/<shot>/<frame>.png or <dir>/<frame>.png")
    ap.add_argument("--mix", type=Path, help="the finished mix (R5)")
    ap.add_argument("--score", type=Path, help="the score, when there is no finished mix")
    ap.add_argument("--vo", action="append", default=[], metavar="L1=path", help="a voice line's WAV (with --score)")
    ap.add_argument("--cues", type=Path, help="R4's cues.json: the voice lines beside it (with --score) and word-timed "
                                              "captions")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--frames", dest="span", metavar="A:B", help="master frames [A, B) only")
    ap.add_argument("--shots", metavar="S13-S18", help="these shots only")
    ap.add_argument("--edl", metavar="45s|A:B,C:D", help="a cut of the reel: a name in EDLS or master frame ranges; "
                                                       "the outputs are named karma-reel-<name>-...")
    ap.add_argument("--only", default="", help="outputs: prores,2160p,hevc,1080p,vertical (default all)")
    ap.add_argument("--source", choices=list(SOURCES), default="2160p",
                    help="the frames' resolution: 1080p makes a 1080p master, no 4K outputs, the 9:16 as a preview")
    ap.add_argument("--scale", type=float, default=1.0, help="every output this many times its size (a quick look)")
    ap.add_argument("--pattern", default="{frame:04d}.png")
    ap.add_argument("--frame-offset", type=int, default=0, help="file number = frame + this")
    ap.add_argument("--fill", choices=["slate"], help="stand a slate in for missing frames")
    ap.add_argument("--hold-first", metavar="S02,S03|all", default="",
                    help="these shots' second frame stands in for their first (a first frame rendered cold across the "
                         "camera cut, the previous shot ghosted into it)")
    ap.add_argument("--grade", choices=["none", "gentle"], default="none")
    ap.add_argument("--lut", type=Path, help="a .cube LUT after the grade")
    ap.add_argument("--grain", type=float, default=0.0, help="film grain on luma (0 off; 2-4 gentle)")
    ap.add_argument("--no-captions", action="store_true", help="burn no captions (the SRT is still written)")
    ap.add_argument("--test-frames", type=Path, metavar="DIR", help="write placeholder frames to DIR and stop")
    a = ap.parse_args(argv)
    if a.edl and (a.span or a.shots):
        ap.error("--edl is a cut of the whole reel: not with --frames or --shots")
    f0, f1 = span(a.span, a.shots)
    segs = edl(a.edl) if a.edl else [(f0, f1)]
    tag = (a.edl if a.edl in EDLS else "edl") if a.edl else ""
    name = (lambda f: f.replace("karma-reel", f"karma-reel-{tag}", 1)) if tag else (lambda f: f)
    if a.test_frames:
        test_frames(a.test_frames, a.scale, f0, f1)
        print(a.test_frames)
        return
    if not a.frames:
        ap.error("FRAMES is required")
    vo = dict(v.split("=", 1) for v in a.vo)
    if set(vo) - set(LINES):
        ap.error(f"--vo names a line that is not one of {', '.join(LINES)}")
    if vo and a.cues:
        ap.error("--vo and --cues both name the voice: one or the other")
    spoken = read_cues(a.cues) if a.cues else {}
    vo = ([(k, v["wav"], round(v["file_frame"] * 1000 / FPS)) for k, v in sorted(spoken.items())] if spoken else
          [(k, Path(p), round(LINES[k][0] * 1000 / FPS)) for k, p in sorted(vo.items())])
    src_ = SOURCES[a.source]
    want = set(a.only.split(",")) if a.only else {"prores", *(o.name for o in OUTPUTS)} - src_["skip"]
    if want & src_["skip"]:
        ap.error(f"--source {a.source} makes no {', '.join(sorted(want & src_['skip']))}")
    base = name
    name = lambda f: base(src_["rename"].get(f, f))  # noqa: E731
    n = sum(b - c for c, b in segs)
    a.out.mkdir(parents=True, exist_ok=True)
    ovl = a.out / "overlays"
    ovl.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="reelcut-", dir=a.out))
    try:
        found = {}
        for c, b in segs:
            found.update(find_frames(a.frames, c, b, a.pattern, a.frame_offset))
        held = [s.id for s in SHOTS if a.hold_first == "all" or s.id in a.hold_first.upper().split(",")]
        for s in SHOTS:
            if s.id in held and found.get(s.start) and found.get(s.start + 1):
                found[s.start] = found[s.start + 1]
        first = next((p for p in found.values() if p), None)
        SW, SH = src_["size"]
        size = png_size(first) if first else (even(SW * a.scale), even(SH * a.scale))
        seq = stage(found, segs, work, a.fill, size)
        mw, mh = even(SW * a.scale), even(SH * a.scale)
        if size != (mw, mh):
            print(f"note: the frames are {size[0]}x{size[1]}, scaled to {mw}x{mh}", file=sys.stderr)
        pre = ",".join(x for x in [grade_filter(a.grade, a.lut), yuv(mw, mh),
                                   f"noise=c0s={a.grain:g}:c0f=t" if a.grain else ""] if x)
        audio, loud = sound(work, segs, a.mix, a.score, vo)
        cs = cues(words=line_words(spoken) if spoken else None)
        write_captions(a.out / name("karma-reel"), cs, segs)
        made = []
        if "prores" in want:
            p = a.out / name(PRORES)
            prores(seq, pre, audio, n, p)
            made.append(check(p, n, (mw, mh)))
            src, src_pre = ["-i", p], ""
        else:
            src, src_pre = ["-framerate", FPS, "-i", seq / "%05d.png"], pre
        for o in OUTPUTS:
            if o.name in want:
                p = a.out / name(o.file)
                encode(o, src, src_pre, (mw, mh), audio, segs, a.scale, [] if a.no_captions else cs, ovl, p)
                made.append(check(p, n, o.size(a.scale)))
                print(f"{p.name}: {made[-1]['size']} {made[-1]['mbps']} Mb/s", flush=True)
        report = {"frames": [list(x) for x in segs], "edl": a.edl, "seconds": n / FPS, "scale": a.scale, "grade": a.grade, "grain": a.grain,
                  "lut": str(a.lut) if a.lut else None, "sound": loud,
                  "shots": {s.id: sorted({str(Path(p).parent) for f, p in found.items() if p and s.start <= f < s.end})
                            for s in SHOTS if spans_out(segs, s.start, s.end)},
                  "missing": sum(1 for p in found.values() if p is None), "held first": a.hold_first, "outputs": made,
                  "title": TITLE, "lines": LINES,
                  "captions": [[a, b, t] for (a, b), t in cs], "cues": str(a.cues) if a.cues else None, "vcrop_keys (draft)": VCROP_KEYS}
        (a.out / (f"cut-{tag}.json" if tag else "cut.json")).write_text(json.dumps(report, indent=1, ensure_ascii=False))
        bad = [f"{m['file']}: {', '.join(m['problems'])}" for m in made if m["problems"]]
        snd = f"{loud['I']:.1f} LUFS, {loud['TP']:.1f} dBTP" if loud.get("I") is not None else "silent"
        print(f"{n} frames ({n / FPS:.2f} s) · sound: {loud['how']} ({snd}) · {a.out}")
        if bad:
            raise SystemExit("problems:\n" + "\n".join(bad))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
