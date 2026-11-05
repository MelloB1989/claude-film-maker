"""Assembling the reel as its frames arrive (round 3, ROUND3.md: the Linux box, 1080p, 16:9 only): bring a render
pass down from the box, check it, lay it out for a look, and cut the reel from everything rendered so far.

    cd tools && uv run --with pillow python ../films/host-studio/reel/assemble.py --pass preview pull   # the box's
                                            /srv/ue/reel/r3/preview -> OUT/frames/preview (film-ue's bridge)
    ... assemble.py --pass final check [S13 ...]     # per shot: frames present, size, luma of first/mid/last
    ... assemble.py --pass final sheet S13           # sheets/S13.jpg: every 6th frame; sheets/N01-S13.jpg: the cut
    ... assemble.py --pass preview preview --mix audio/mix/mix.wav [--cues CUES.json]   # preview_<pass>_<n>.mp4
    ... assemble.py final --mix audio/mix/mix.wav --mix45 audio/mix/mix_45.wav [--cues CUES.json]   # 65 s and 45 s

A pass is one directory of frames as agent-05's r3 specs write them on the box (/srv/ue/reel/r3/<pass>/<master
frame:04d>.png; the preview pass is 960x540 .jpg), in OUT/frames/<pass>/ here (--frames-dir for any other; per-shot
directories, S13/..., work too; --frames-root for where the passes are). `final` cuts from the finals and fills every shot not yet final from the preview pass
(--fill-from preview; none to require every final). n in preview_<pass>_<n> is the number of whole shots in. Missing
shots are slates, so a cut is always the reel's full length with the mix, the title and the captions.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cut  # noqa: E402
from shots import SHOTS  # noqa: E402

SHOT = {s.id: s for s in SHOTS}
DEFAULT = HERE.parents[2] / "out" / "host-studio" / "reel"
BOX = "/srv/ue/reel/r3"  # r3/vars.yaml's ${out}: the passes on the box


def pattern(frames: Path) -> str:
    """cut.py's --pattern for a pass: .png, else the JPEG extension the pass uses (MRQ writes a jpg output as .jpeg)."""
    for ext in ("png", "jpeg", "jpg"):
        if next(frames.rglob(f"[0-9][0-9][0-9][0-9].{ext}"), None) is not None:
            return "{frame:04d}." + ext
    return "{frame:04d}.png"


def frames_of(frames: Path, s) -> dict:
    return cut.find_frames(frames, s.start, s.end, pattern(frames)) if frames.is_dir() else {
        f: None for f in range(s.start, s.end)}


def whole(frames: Path) -> list:
    return [s.id for s in SHOTS if all(frames_of(frames, s).values())]


def some(frames: Path) -> list:
    return [s.id for s in SHOTS if any(frames_of(frames, s).values())]


def pull(frames: Path, remote: str) -> None:
    from filmtools.unreal import workstation as ws
    shutil.rmtree(frames, ignore_errors=True)  # a pass is replaced whole: no stale frame survives beside new ones
    n = ws.pull_dir(remote, str(frames))
    print(f"{n} files in {frames}")
    check(frames, [])


def merged(out: Path, passes: list) -> Path:
    """One directory of links: each shot from the first pass that has it whole (the finals, then the preview), so a
    cut can run before every final is in. Shots whole in none stay missing (slates). Every link is one extension."""
    d = out / "frames" / "_cut"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    used = {}
    for s in SHOTS:
        for p in passes:
            got = frames_of(p, s)
            if all(got.values()):
                for f, path in got.items():
                    (d / f"{f:04d}{Path(path).suffix.lower()}").symlink_to(Path(path).resolve())
                used[s.id] = p.name
                break
    exts = {x.suffix for x in d.iterdir()}
    if len(exts) > 1:  # a final .png beside a preview .jpg: ffmpeg reads one sequence of one format
        conv = {x for x in d.iterdir() if x.suffix != ".png"}
        from PIL import Image
        for x in conv:
            with Image.open(x) as im:
                im.convert("RGB").save(x.with_suffix(".png"), compress_level=1)
            x.unlink()
    print("shots from:", json.dumps(used))
    return d


def luma(img) -> tuple[float, float, float]:
    """Mean luma (0-255), % of pixels clipped (>= 254) and crushed (<= 1)."""
    g = img.convert("L")
    h = g.histogram()
    n = sum(h)
    return sum(i * c for i, c in enumerate(h)) / n, 100 * sum(h[254:]) / n, 100 * sum(h[:2]) / n


def check(frames: Path, shots: list) -> dict:
    """Per shot: frames present/missing, size, and the luma of its first, middle and last frame."""
    from PIL import Image
    out = {}
    for sid in shots or some(frames):
        s = SHOT[sid]
        got = frames_of(frames, s)
        miss = [f for f, p in got.items() if p is None]
        row = {"frames": f"{s.start}-{s.end - 1}", "have": len(got) - len(miss), "missing": len(miss)}
        if miss:
            row["first missing"] = miss[0]
        have = [p for p in got.values() if p]
        if have:
            for k, p in (("first", have[0]), ("mid", have[len(have) // 2]), ("last", have[-1])):
                with Image.open(p) as im:
                    row["size"] = f"{im.width}x{im.height} {im.mode}"
                    m, hi, lo = luma(im)
                    row[k] = f"luma {m:.0f}, clip {hi:.2f}%, crush {lo:.2f}%"
        out[sid] = row
        print(sid, json.dumps(row, ensure_ascii=False))
    return out


def sheet(frames: Path, out: Path, shot: str, every: int = 6, tile: int = 640) -> list:
    """sheets/<shot>.jpg (every `every`-th frame, numbered) and sheets/<prev>-<shot>.jpg (the cut: the previous shot's
    last two frames and this one's first two, larger)."""
    from PIL import Image, ImageDraw
    s = SHOT[shot]
    got = {f: p for f, p in frames_of(frames, s).items() if p}
    if not got:
        raise SystemExit(f"{shot}: no frames")
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    fs = sorted(got)
    pick = fs[::every] + ([fs[-1]] if (fs[-1] - fs[0]) % every else [])
    made = []

    def grid(paths, w, cols, dest):
        ims = []
        for f, p in paths:
            with Image.open(p) as im:
                t = im.convert("RGB")
                t.thumbnail((w, w))
            d = ImageDraw.Draw(t)
            d.rectangle((0, 0, 90 * w // 640, 30 * w // 640), fill=(0, 0, 0))
            d.text((6, 4), str(f), font=cut.font(22 * w / 640, 600), fill=(255, 255, 0))
            ims.append(t)
        tw, th = ims[0].size
        rows = (len(ims) + cols - 1) // cols
        g = Image.new("RGB", (cols * tw + (cols - 1) * 4, rows * th + (rows - 1) * 4), (255, 255, 255))
        for i, t in enumerate(ims):
            g.paste(t, ((i % cols) * (tw + 4), (i // cols) * (th + 4)))
        g.save(dest, quality=88)
        made.append(dest)

    grid([(f, got[f]) for f in pick], tile, 4, out / "sheets" / f"{shot}.jpg")
    i = [x.id for x in SHOTS].index(shot)
    if i:
        p = SHOTS[i - 1]
        prev = {f: q for f, q in frames_of(frames, p).items() if q}
        if prev:
            pf = sorted(prev)[-2:]
            grid([(f, prev[f]) for f in pf] + [(f, got[f]) for f in fs[:2]], 960, 2,
                 out / "sheets" / f"{p.id}-{shot}.jpg")
    print("\n".join(map(str, made)))
    return made


def contact(passes: list, out: Path, name: str, tile: int = 480) -> Path:
    """sheets/<name>.jpg: the whole reel at a glance, one row per shot (its first, middle and last frame), each shot
    from the first pass that has it whole (a slate-grey tile when none does), labelled with the shot, the frame and
    the pass. Small, for bringing down from the box."""
    from PIL import Image, ImageDraw
    rows = []
    for s in SHOTS:
        got, src = {}, ""
        for p in passes:
            g = frames_of(p, s)
            if all(g.values()):
                got, src = g, p.name
                break
        picks = [s.start, (s.start + s.end) // 2, s.end - 1]
        tiles = []
        for f in picks:
            if got:
                with Image.open(got[f]) as im:
                    t = im.convert("RGB")
                    t.thumbnail((tile, tile))
            else:
                t = Image.new("RGB", (tile, tile * 9 // 16), (60, 60, 60))
            d = ImageDraw.Draw(t)
            label = f"{s.id} f{f} {src or 'missing'}"
            d.rectangle((0, 0, int(cut.font(18, 600).getlength(label)) + 12, 26), fill=(0, 0, 0))
            d.text((6, 3), label, font=cut.font(18, 600), fill=(255, 255, 0))
            tiles.append(t)
        rows.append(tiles)
    tw, th = rows[0][0].size
    g = Image.new("RGB", (3 * tw + 8, len(rows) * th + (len(rows) - 1) * 4), (255, 255, 255))
    for i, r in enumerate(rows):
        for j, t in enumerate(r):
            g.paste(t.resize((tw, th)), (j * (tw + 4), i * (th + 4)))
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    dest = out / "sheets" / f"{name}.jpg"
    g.save(dest, quality=82)
    print(dest)
    return dest


def preview(frames: Path, out: Path, mix: Path, mix45: Path | None, cues: Path | None, scale: float, source: str,
            hold: str) -> None:
    """The reel so far from one pass: rendered shots and slates for the rest, the mix, title and captions; the 65 s
    and the 45 s, 1080p 16:9 with captions burned in."""
    n = len(whole(frames))
    work = out / "preview_work"
    tag = f"{frames.name}_{n}"
    args = [str(frames), "--fill", "slate", "--only", "1080p", "--out", str(work), "--pattern", pattern(frames),
            "--scale", str(scale), "--source", source, "--hold-first", hold] + (["--cues", str(cues)] if cues else [])
    cut.main(args + ["--mix", str(mix)])
    cut.main(args + ["--edl", "45s", "--mix", str(mix45 or mix)])
    (work / "karma-reel-1080p-h264.mp4").replace(out / f"preview_{tag}.mp4")
    (work / "karma-reel-45s-1080p-h264.mp4").replace(out / f"preview_{tag}_45s.mp4")
    (work / "cut.json").replace(out / f"preview_{tag}.json")
    contact([frames], out, f"preview_{tag}")
    print(out / f"preview_{tag}.mp4", out / f"preview_{tag}_45s.mp4",
          f"({n} of {len(SHOTS)} shots: {', '.join(whole(frames))})")


def final(frames: Path, out: Path, mix: Path, mix45: Path | None, cues: Path | None, source: str, hold: str,
          fill_from: list) -> None:
    """The deliverables into OUT: the 65 s reel (the textless ProRes master, 1080p with captions burned in, 1080p
    clean, SRT/VTT, cut.json) and the 45 s cut (the same, karma-reel-45s-*: R5's mix made for it, or the full mix cut on
    its edits). Shots not yet final come from the --fill-from passes (a rough cut, named so in cut.json's "shots");
    with none, every final must be in."""
    passes = [frames] + fill_from
    missing = [s.id for s in SHOTS if not any(s.id in whole(p) for p in passes)]
    if missing:
        raise SystemExit(f"not every shot is in: {', '.join(missing)}")
    rough = [s.id for s in SHOTS if s.id not in whole(frames)]
    src = merged(out, passes) if rough else frames
    if rough:
        print(f"ROUGH CUT: {', '.join(rough)} not final yet (from {', '.join(p.name for p in fill_from)})")
    c = (["--cues", str(cues)] if cues else []) + ["--source", source, "--hold-first", hold, "--pattern", pattern(src)]
    cut.main([str(src), "--mix", str(mix), "--out", str(out), *c])
    cut.main([str(src), "--edl", "45s", "--mix", str(mix45 or mix), "--out", str(out), *c])
    contact(passes, out, "final" if not rough else "rough")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT, help="where the previews and sheets go")
    ap.add_argument("--pass", dest="pass_", default="final", help="the render pass: preview, final, cal_A, ...")
    ap.add_argument("--frames-root", type=Path, help="where the passes are, one directory each (default OUT/frames; "
                                                    "agent-07 copies them to .worktrees/agent-06/r3-frames)")
    ap.add_argument("--frames-dir", type=Path, help="the pass's frames (default FRAMES_ROOT/<pass>)")
    ap.add_argument("--source", choices=["2160p", "1080p"], default="1080p", help="the deliverables' resolution "
                                                                                 "(cut.py; 1080p in round 3)")
    ap.add_argument("--hold-first", default="", help="cut.py's --hold-first: shots whose first frame is ghosted")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull")
    p.add_argument("remote", nargs="?", help=f"the pass's directory on the box (default {BOX}/<pass>)")
    p = sub.add_parser("check")
    p.add_argument("shots", nargs="*")
    p = sub.add_parser("sheet")
    p.add_argument("shot")
    p.add_argument("--every", type=int, default=6)
    p = sub.add_parser("preview")
    p.add_argument("--mix", type=Path, required=True)
    p.add_argument("--mix45", type=Path, help="R5's mix for the 45 s cut (else the full mix, cut on its edits)")
    p.add_argument("--cues", type=Path)
    p.add_argument("--scale", type=float, default=1.0, help="cut.py's --scale (less for a quick look)")
    p = sub.add_parser("final")
    p.add_argument("--mix", type=Path, required=True)
    p.add_argument("--mix45", type=Path, help="R5's mix for the 45 s cut (else the full mix, cut on its edits)")
    p.add_argument("--cues", type=Path)
    p.add_argument("--fill-from", default="preview", help="passes that stand in for shots not yet final, in order "
                                                          "(comma-separated; none: every final must be in)")
    a = ap.parse_args(argv)
    root = a.frames_root or a.out / "frames"
    frames = a.frames_dir or root / a.pass_
    if a.cmd == "pull":
        pull(frames, a.remote or f"{BOX}/{a.pass_}")
    elif a.cmd == "check":
        check(frames, [x.upper() for x in a.shots])
    elif a.cmd == "sheet":
        sheet(frames, a.out, a.shot.upper(), a.every)
    elif a.cmd == "final":
        fill = [] if a.fill_from in ("", "none") else [root / x for x in a.fill_from.split(",")]
        final(frames, a.out, a.mix, a.mix45, a.cues, a.source, a.hold_first, fill)
    else:
        preview(frames, a.out, a.mix, a.mix45, a.cues, a.scale, a.source, a.hold_first)


if __name__ == "__main__":
    main()
