"""The explainers' final composite: presenter renders + graphics (full frame and alpha side panels) + kinetic captions (every VO word) +
the lower third + the mix, cut to edl/<film>.json. Runs ON THE BOX (presenter frames are private: they never leave it
except to private/ on S3).

    python3 films/host-studio/explainers/composite.py --film netflix \\
        --presenter /srv/r6/explain/netflix/presenter --gfx /srv/r6/explain/netflix/gfx --out /srv/r6/explain/out
    aws s3 cp --recursive /srv/r6/explain/out s3://rf-render-788655295054-aps1/ue-linux/private/renders/r6/review/explain/

    python3 films/host-studio/explainers/composite.py --film netflix --placeholder ...   # grey slugs for what is missing

Needs ffmpeg (libx264, prores_ks) and Pillow (`python3 -m pip install --user pillow`).

Inputs (24 fps, 1920x1080; anything else is scaled to fit):
- presenter: per shot, `shot<NN>_<CAM>/` (PNG/EXR-free: PNG or JPG frames whose number is the SEQUENCE frame, handles
  allowed) or `shot<NN>_<CAM>.mov` whose first frame is f0 - --handles. Panel shots use `<CAM>_L` (CAM_MCU_L).
- gfx: `<scene>_full.mov` (frame 0 = the shot's first frame, at least the shot's length), `<scene>_panel.mov` (ProRes
  4444 with alpha, full frame, transparent outside the right-hand card), optional `lowerthird.mov` (alpha).
- audio/<film>/mix.wav (mix.py).
Missing inputs fail the run, unless --placeholder: then a labelled slug stands in (grey for the presenter, a warm card
naming the scene and its line for a graphic), so the timing can be watched before the renders land.

Out (in --out): <film>_r6[_tag].mp4 (H.264 High, CRF 16, yuv420p, BT.709, AAC 320k, faststart), <film>_r6[_tag]_master.mov
(ProRes 422 HQ, PCM 24-bit), <film>_r6[_tag].srt (the captions, for qa_av.py), <film>_r6[_tag].json (what went in).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
W, H, FPS = 1920, 1080, 24
FONTS = ROOT / "app" / "public" / "fonts"
ACCENT = {"whatsapp": (37, 211, 102), "netflix": (229, 9, 20)}
INK, INK2 = (18, 14, 11), (30, 24, 19)
TEXT, TEXT2 = (242, 236, 228), (168, 158, 146)
SERIES = "SYSTEM DESIGN IN 60 SECONDS"
LT_F0, LT_F1 = 12, 84         # the lower third's frames (on the first presenter shot)
CAP_Y = 1000                  # caption baseline centre (y of the text's vertical middle)
CAP_SIZE = 50
CAP_MAX_WORDS, CAP_MAX_CHARS = 6, 34
# a chunk never ends on these (no "over a hundred / billion", no "the / server")
NO_BREAK_AFTER = {"a", "an", "the", "over", "of", "to", "on", "in", "its", "your", "their", "and", "so", "than",
                  "hundred", "three", "two", "few", "many", "right", "fewer", "one", "is", "it's", "into", "at", "per"}

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover
    sys.exit("composite.py needs Pillow: python3 -m pip install --user pillow")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    p = FONTS / name
    if not p.is_file():
        sys.exit(f"no font {p}: composite.py needs the repo's app/public/fonts/ (a full checkout of the branch, or "
                 f"--fonts DIR)")
    return ImageFont.truetype(str(p), size)


def ff(args: list, ffmpeg: str) -> None:
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *map(str, args)]
    r = subprocess.run(cmd)
    if r.returncode:
        sys.exit(f"ffmpeg failed: {' '.join(cmd)}")


PRORES = ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-vendor", "apl0"]
FIT = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}"


# ------------------------------------------------------------------------------------------------ stills

def ground(film: str) -> Image.Image:
    """The warm studio ground of GFX.md: a radial from INK2 to INK with a faint grid."""
    im = Image.new("RGB", (W, H), INK)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((-400, -500, W * 0.8, H * 0.9), fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(260))
    im = Image.composite(Image.new("RGB", (W, H), INK2), im, glow)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 64):
        d.line((x, 0, x, H), fill=(32, 27, 23))
    for y in range(0, H, 64):
        d.line((0, y, W, y), fill=(32, 27, 23))
    return im


def wrap(d: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=f) > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = t
    return out + [cur] if cur else out


def slug_presenter(path: Path, film: str, shot: dict) -> None:
    im = Image.new("RGB", (W, H), (74, 74, 74))
    d = ImageDraw.Draw(im)
    cx = 480 if shot["kind"] == "panel" else W // 2
    d.ellipse((cx - 150, 260, cx + 150, 620), fill=(96, 96, 96))
    d.rounded_rectangle((cx - 330, 600, cx + 330, H + 40), 120, fill=(96, 96, 96))
    cam = shot["camera"] + ("_L" if shot["kind"] == "panel" else "")
    d.text((cx, 150), f"PRESENTER  {cam}", font=font("Geist-600.ttf", 44), fill=(220, 220, 220), anchor="mm")
    d.text((cx, 205), f"shot {shot['n']:02d}  f{shot['f0']}-{shot['f1']}  {' '.join(shot['lines'])}",
           font=font("JetBrainsMono-500.ttf", 28), fill=(190, 190, 190), anchor="mm")
    im.save(path)


def slug_gfx(path: Path, film: str, shot: dict, panel: bool) -> None:
    acc = ACCENT[film]
    if panel:
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((1010, 150, 1860, 930), 18, fill=(26, 20, 16, 200), outline=(59, 49, 41, 255), width=2)
        box, cx = (1060, 1810), 1435
    else:
        im = ground(film).convert("RGBA")
        d = ImageDraw.Draw(im)
        box, cx = (260, 1660), W // 2
    top = 330 if panel else 330
    d.text((cx, top), shot["gfx"].upper(), font=font("Bricolage-w1000-800.ttf", 96 if not panel else 72), fill=acc,
           anchor="mm")
    d.text((cx, top + 80), "GRAPHIC PLACEHOLDER", font=font("JetBrainsMono-500.ttf", 26), fill=TEXT2, anchor="mm")
    f = font("Geist-500.ttf", 38 if not panel else 32)
    y = top + 160
    for ln in wrap(d, shot["text"] or "end card", f, box[1] - box[0]):
        d.text((cx, y), ln, font=f, fill=TEXT, anchor="mm")
        y += 52
    im.save(path)


def lower_third(path: Path, film: str, title: str) -> None:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f1, f2 = font("Geist-600.ttf", 30), font("Geist-400.ttf", 36)
    x, y = 96, 770
    w = max(d.textlength(SERIES, font=f1) * 1.12, d.textlength(title, font=f2)) + 64
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x - 8, y - 4, x + w + 8, y + 132), 18, fill=(0, 0, 0, 110))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    d.rounded_rectangle((x, y, x + w, y + 124), 14, fill=(26, 20, 16, 210), outline=(59, 49, 41, 255), width=2)
    d.rectangle((x, y + 18, x + 6, y + 106), fill=ACCENT[film])
    cx = x + 32
    for ch in SERIES:  # tracked caps
        d.text((cx, y + 22), ch, font=f1, fill=ACCENT[film])
        cx += d.textlength(ch, font=f1) * 1.08
    d.text((x + 32, y + 66), title, font=f2, fill=TEXT)
    im.save(path)


# ------------------------------------------------------------------------------------------------ captions

def chunks(line: dict) -> list[list[dict]]:
    """Caption chunks: the line split at its punctuation (a comma only after two words), and a clause longer than
    CAP_MAX_CHARS split into the most even pieces that do not end on a word leading into the next."""
    segs, cur = [], []
    for w in line["words"]:
        cur.append(w)
        if w["w"][-1] in ".?!:" or (w["w"][-1] == "," and len(cur) >= 2):
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    out = []
    for seg in segs:
        n = len(" ".join(x["w"] for x in seg))
        if n <= CAP_MAX_CHARS and len(seg) <= CAP_MAX_WORDS:
            out.append(seg)
            continue
        k = max(2, -(-n // CAP_MAX_CHARS))
        best = None
        for cuts in combinations(range(1, len(seg)), k - 1):
            parts = [seg[i:j] for i, j in zip((0,) + cuts, cuts + (len(seg),))]
            lens = [len(" ".join(x["w"] for x in p)) for p in parts]
            bad = sum(p[-1]["w"].lower().strip(",") in NO_BREAK_AFTER for p in parts[:-1])
            score = bad * 100 + max(lens) - min(lens) + 50 * sum(len(p) == 1 for p in parts)
            if best is None or score < best[0]:
                best = (score, parts)
        out += best[1]
    return out


def caption_image(path: Path, words: list[str], lit: int, film: str) -> None:
    """A chunk with its first `lit` words bright and the rest waiting, on a soft shadow (no box)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = font("Geist-600.ttf", CAP_SIZE)
    d = ImageDraw.Draw(im)
    space = d.textlength(" ", font=f)
    widths = [d.textlength(w, font=f) for w in words]
    x = (W - (sum(widths) + space * (len(words) - 1))) / 2
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sh)
    xs = x
    for w, wd in zip(words, widths):
        ds.text((xs, CAP_Y + 3), w, font=f, fill=(0, 0, 0, 200), anchor="lm")
        xs += wd + space
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
    for i, (w, wd) in enumerate(zip(words, widths)):
        d.text((x, CAP_Y), w, font=f, fill=TEXT + (255,) if i < lit else TEXT + (120,), anchor="lm")
        x += wd + space
    im.save(path)


def captions(edl: dict, cues: dict, film: str, work: Path) -> tuple[Path, list]:
    """The caption track as an ffconcat of stills (one per word state) and the SRT entries. Every VO word is captioned,
    on every shot (QA: the captions are the VO, in order), each chunk from 2 frames before its first word to 8 after
    its last (or the next chunk, or the shot's cut). The graphics keep the bottom caption band clear (GFX.md)."""
    shots = edl["shots"]
    on = [(s["f0"], s["f1"]) for s in shots if s["lines"]]
    events, srt = [], []  # (f0, f1, still)
    blank = work / "cap_blank.png"
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    k = 0
    for line in cues["lines"]:
        span = next(((a, b) for a, b in on if a <= line["start_f"] < b), None)
        if not span:
            continue
        cs = chunks(line)
        for ci, ch in enumerate(cs):
            c0 = max(span[0], ch[0]["f0"] - 2)
            nxt = cs[ci + 1][0]["f0"] - 2 if ci + 1 < len(cs) else None
            c1 = min(span[1], ch[-1]["f1"] + 8, *( [nxt] if nxt else []))
            words = [w["w"] for w in ch]
            srt.append((c0, c1, " ".join(words)))
            for i, w in enumerate(ch):
                s0 = c0 if i == 0 else max(c0, w["f0"])
                s1 = c1 if i + 1 == len(ch) else max(s0 + 1, min(c1, ch[i + 1]["f0"]))
                if s1 <= s0:
                    continue
                p = work / f"cap_{k:04d}.png"
                caption_image(p, words, i + 1, film)
                events.append((s0, s1, p))
                k += 1
    events.sort()
    lst, f = ["ffconcat version 1.0"], 0
    for a, b, p in events:
        if a < f:
            a = f
        if b <= a:
            continue
        if a > f:
            lst += [f"file '{blank}'", f"duration {(a - f) / FPS:.6f}"]
        lst += [f"file '{p}'", f"duration {(b - a) / FPS:.6f}"]
        f = b
    if f < edl["frames"]:
        lst += [f"file '{blank}'", f"duration {(edl['frames'] - f) / FPS:.6f}"]
    lst += [f"file '{blank}'"]
    cat = work / "captions.ffconcat"
    cat.write_text("\n".join(lst) + "\n")
    return cat, srt


def write_srt(path: Path, srt: list) -> None:
    def ts(f: int) -> str:
        ms = int(round(f / FPS * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    path.write_text("".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(srt, 1)))


# ------------------------------------------------------------------------------------------------ shots

def presenter_input(shot: dict, pdir: Path | None, handles: int) -> list | None:
    if pdir is None:
        return None
    cam = shot["camera"] + ("_L" if shot["kind"] == "panel" else "")
    stem = f"shot{shot['n']:02d}_{cam}"
    d = pdir / stem
    if d.is_dir():
        frames = sorted(p for p in d.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg") and p.stem.isdigit())
        if frames:
            nums = {int(p.stem): p for p in frames}
            if shot["f0"] not in nums or shot["f1"] - 1 not in nums:
                sys.exit(f"{d}: frames {min(nums)}-{max(nums)} do not cover {shot['f0']}-{shot['f1'] - 1}")
            digits = len(frames[0].stem)
            return ["-framerate", FPS, "-start_number", shot["f0"], "-i", d / f"%0{digits}d{frames[0].suffix}"]
    mov = pdir / f"{stem}.mov"
    if mov.is_file():
        return ["-ss", f"{handles / FPS:.6f}", "-i", mov]
    return None


def render_shot(shot: dict, film: str, a: argparse.Namespace, work: Path, used: dict) -> Path:
    out = work / f"seg_{shot['n']:02d}.mov"
    n = shot["frames"]
    inputs, chain = [], []
    if shot["kind"] in ("pres", "panel"):
        src = presenter_input(shot, a.presenter, a.handles)
        if src is None:
            if not a.placeholder:
                sys.exit(f"missing presenter render for shot {shot['n']} ({shot['camera']}) in {a.presenter}")
            p = work / f"slug_{shot['n']:02d}.png"
            slug_presenter(p, film, shot)
            src = ["-loop", "1", "-framerate", FPS, "-i", p]
            used[shot["n"]] = {"presenter": "placeholder"}
        else:
            used[shot["n"]] = {"presenter": str(src[-1])}
        inputs += src
        chain.append(f"[0:v]{FIT},format=yuv444p10le[base]")
        if shot["kind"] == "panel":
            pm = a.gfx / f"{shot['gfx']}_panel.mov" if a.gfx else None
            if pm and pm.is_file():
                inputs += ["-i", pm]
                used[shot["n"]]["gfx"] = str(pm)
            elif a.placeholder:
                p = work / f"panel_{shot['n']:02d}.png"
                slug_gfx(p, film, shot, panel=True)
                inputs += ["-loop", "1", "-framerate", FPS, "-i", p]
                used[shot["n"]]["gfx"] = "placeholder"
            else:
                sys.exit(f"missing {shot['gfx']}_panel.mov in {a.gfx}")
            chain.append(f"[1:v]{FIT},format=yuva444p10le[pan];[base][pan]overlay=0:0:format=auto[v]")
        else:
            chain.append("[base]null[v]")
    else:
        gm = a.gfx / f"{shot['gfx']}_full.mov" if a.gfx else None
        if gm and gm.is_file():
            inputs += ["-i", gm]
            used[shot["n"]] = {"gfx": str(gm)}
        elif a.placeholder:
            p = work / f"gfx_{shot['n']:02d}.png"
            slug_gfx(p, film, shot, panel=False)
            inputs += ["-loop", "1", "-framerate", FPS, "-i", p]
            used[shot["n"]] = {"gfx": "placeholder"}
        else:
            sys.exit(f"missing {shot['gfx']}_full.mov in {a.gfx}")
        chain.append(f"[0:v]{FIT}[v]")
    ff([*inputs, "-filter_complex", ";".join(chain), "-map", "[v]", "-frames:v", n, "-r", FPS, *PRORES, "-an", out],
       a.ffmpeg)
    return out


# ------------------------------------------------------------------------------------------------ main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--film", required=True, choices=["whatsapp", "netflix"])
    ap.add_argument("--presenter", type=Path)
    ap.add_argument("--gfx", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tag", default="")
    ap.add_argument("--placeholder", action="store_true")
    ap.add_argument("--handles", type=int, default=6, help="lead-in frames on a presenter .mov (default 6)")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--no-prores", action="store_true", help="skip the ProRes master (quick reviews)")
    ap.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    ap.add_argument("--keep", action="store_true", help="keep the work directory")
    ap.add_argument("--fonts", type=Path, help="the fonts directory (default: the repo's app/public/fonts)")
    a = ap.parse_args()
    if a.fonts:
        global FONTS
        FONTS = a.fonts

    edl = json.loads((HERE / "edl" / f"{a.film}.json").read_text())
    cues = json.loads((HERE / "audio" / a.film / "cues.json").read_text())
    mix = HERE / "audio" / a.film / "mix.wav"
    title = json.loads((HERE / "scripts.json").read_text())["explainers"][a.film]["title"]
    a.out.mkdir(parents=True, exist_ok=True)
    name = f"{a.film}_r6{('_' + a.tag) if a.tag else ''}"
    work = Path(tempfile.mkdtemp(prefix=f"comp_{a.film}_", dir=a.out))
    used: dict = {}
    try:
        segs = [render_shot(s, a.film, a, work, used) for s in edl["shots"]]
        (work / "segs.txt").write_text("".join(f"file '{p}'\n" for p in segs))
        pic = work / "picture.mov"
        ff(["-f", "concat", "-safe", 0, "-i", work / "segs.txt", "-c", "copy", pic], a.ffmpeg)

        inputs = ["-i", pic, "-i", mix]
        chain, last, idx = [], "[0:v]", 2
        lt_mov = a.gfx / "lowerthird.mov" if a.gfx else None
        first_on = next(s for s in edl["shots"] if s["kind"] in ("pres", "panel"))
        lt0 = first_on["f0"] + LT_F0
        if lt_mov and lt_mov.is_file():
            inputs += ["-itsoffset", f"{lt0 / FPS:.6f}", "-i", lt_mov]
            chain.append(f"[{idx}:v]{FIT},format=yuva444p10le[lt]")
        else:
            lt = work / "lowerthird.png"
            lower_third(lt, a.film, title)
            d = (LT_F1 - LT_F0) / FPS
            inputs += ["-loop", "1", "-framerate", FPS, "-t", f"{d:.6f}", "-i", lt]
            chain.append(f"[{idx}:v]format=yuva444p10le,fade=in:st=0:d=0.35:alpha=1,"
                         f"fade=out:st={d - 0.35:.4f}:d=0.35:alpha=1,setpts=PTS+{lt0 / FPS:.6f}/TB[lt]")
        chain.append(f"{last}[lt]overlay=0:0:eof_action=pass:format=auto[v1]")
        last, idx = "[v1]", idx + 1
        srt = []
        if not a.no_captions:
            cat, srt = captions(edl, cues, a.film, work)
            inputs += ["-f", "concat", "-safe", 0, "-i", cat]
            chain.append(f"[{idx}:v]fps={FPS},format=yuva444p10le[cap];{last}[cap]overlay=0:0:eof_action=pass:"
                         f"format=auto[v2]")
            last, idx = "[v2]", idx + 1
        frames = edl["frames"]
        chain.append(f"{last}trim=end_frame={frames},setpts=PTS-STARTPTS,split=2[vh][vp]")
        mp4, mov = a.out / f"{name}.mp4", a.out / f"{name}_master.mov"
        outs = ["-map", "[vh]", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                "-profile:v", "high", "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
                "-color_trc", "bt709", "-r", FPS, "-frames:v", frames, "-c:a", "aac", "-b:a", "320k", "-ar", 48000,
                "-movflags", "+faststart", "-shortest", mp4]
        if not a.no_prores:
            outs += ["-map", "[vp]", "-map", "1:a", *PRORES, "-r", FPS, "-frames:v", frames, "-c:a", "pcm_s24le",
                     "-shortest", mov]
        else:
            chain[-1] = chain[-1].replace(",split=2[vh][vp]", "[vh]")
        ff([*inputs, "-filter_complex", ";".join(chain), *outs], a.ffmpeg)
        write_srt(a.out / f"{name}.srt", srt)
        (a.out / f"{name}.json").write_text(json.dumps({
            "film": a.film, "frames": frames, "fps": FPS, "placeholder": a.placeholder, "shots": used,
            "mix": str(mix.relative_to(ROOT)), "mix_report": json.loads((mix.with_suffix(".json")).read_text()),
            "outputs": [mp4.name] + ([] if a.no_prores else [mov.name]) + [f"{name}.srt"]}, indent=1))
        print(f"{name}: {frames} frames -> {mp4}" + ("" if a.no_prores else f", {mov}"))
    finally:
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
