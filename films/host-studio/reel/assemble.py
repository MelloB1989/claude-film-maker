"""Assembling the reel as its final frames arrive (task R6b), on the operator's Mac: bring a finished shot down from
the workstation, check it, lay it out for a look, and cut a rolling preview of everything rendered so far.

    FLEET_BRIDGE_NOLOCK=1 bash /tmp/fleet-bridge/run.sh REPO uv run --with pillow python \\
        ../films/host-studio/reel/assemble.py pull S03 'D:\\renders\\reel\\S03'     # S3 only: never the bridge lock
    cd REPO/tools && uv run --with pillow python ../films/host-studio/reel/assemble.py check [S03 ...]
    ... assemble.py sheet S03               # sheets/S03.jpg: every 6th frame; sheets/S02-S03.jpg: the cut into it
    ... assemble.py preview --mix MIX.wav --cues CUES.json   # preview_<n>.mp4 (1080p 16:9) and preview_<n>_9x16.mp4
    ... assemble.py final --mix MIX.wav --mix45 MIX_45.wav --cues CUES.json   # every deliverable, 65 s and 45 s
    ... assemble.py final ... --only prores,1080p                            # the 16:9 ones only (round 3: no 9:16)

FRAMES (--frames-dir) is out/host-studio/reel/frames/ of the repo the output belongs in, one directory per shot (S01/
...), numbered as cut.py reads them (the master's clock or the shot's own). n in preview_<n> is the number of whole
shots in. Missing shots are slates, so the preview is always the reel's full 65 s with the mix and the title.
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
DEFAULT = Path("/Users/0mellob/Developer/code/claude-film-maker/out/host-studio/reel")


def frames_of(frames: Path, s) -> dict:
    return cut.find_frames(frames, s.start, s.end)


def whole(frames: Path) -> list:
    return [s.id for s in SHOTS if (frames / s.id).is_dir() and all(frames_of(frames, s).values())]


def pull(frames: Path, shot: str, remote: str) -> None:
    from filmtools.unreal import workstation as ws
    d = frames / shot
    shutil.rmtree(d, ignore_errors=True)  # a re-render replaces the shot whole: no old frame survives beside new ones
    n = ws.pull_dir(remote, str(d))
    print(f"{shot}: {n} files in {d}")
    check(frames, [shot])


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
    for sid in shots or [s.id for s in SHOTS if (frames / s.id).is_dir()]:
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
        prev = {f: q for f, q in frames_of(frames, p).items() if q} if (frames / p.id).is_dir() else {}
        if prev:
            pf = sorted(prev)[-2:]
            grid([(f, prev[f]) for f in pf] + [(f, got[f]) for f in fs[:2]], 960, 2,
                 out / "sheets" / f"{p.id}-{shot}.jpg")
    print("\n".join(map(str, made)))
    return made


def preview(frames: Path, out: Path, mix: Path, cues: Path | None, scale: float, source: str, hold: str) -> None:
    """The reel so far: rendered shots and slates for the rest, the mix, title and captions; 1080p 16:9 and 9:16."""
    n = len(whole(frames))
    work = out / "preview_work"
    args = [str(frames), "--fill", "slate", "--only", "1080p,vertical", "--mix", str(mix), "--out", str(work),
            "--scale", str(scale), "--source", source, "--hold-first", hold]
    cut.main(args + (["--cues", str(cues)] if cues else []))
    (work / "karma-reel-1080p-h264.mp4").replace(out / f"preview_{n}.mp4")
    (work / cut.SOURCES[source]["rename"].get(v := "karma-reel-9x16-h264.mp4", v)).replace(out / f"preview_{n}_9x16.mp4")
    (work / "cut.json").replace(out / f"preview_{n}.json")
    print(out / f"preview_{n}.mp4", out / f"preview_{n}_9x16.mp4", f"({n} of {len(SHOTS)} shots: {', '.join(whole(frames))})")


def final(frames: Path, out: Path, mix: Path, mix45: Path | None, cues: Path | None, source: str, hold: str,
          only: str = "") -> None:
    """The deliverables into OUT: the 65 s reel (ProRes master, 4K H.264/HEVC, 1080p, 9:16, SRT/VTT, cut.json) and the
    45 s cut (the same, karma-reel-45s-*: R5's mix made for it, or the full mix cut on its edits). From --source 1080p
    frames: a 1080p master, no 4K, the 9:16 as karma-reel-9x16-preview-*. --only (cut.py's) picks the outputs, e.g.
    prores,1080p for the 16:9 ones alone. Every frame must be in: no slates."""
    missing = [s.id for s in SHOTS if s.id not in whole(frames)]
    if missing:
        raise SystemExit(f"not every shot is in: {', '.join(missing)}")
    c = (["--cues", str(cues)] if cues else []) + ["--source", source, "--hold-first", hold]
    c += ["--only", only] if only else []
    cut.main([str(frames), "--mix", str(mix), "--out", str(out), *c])
    cut.main([str(frames), "--edl", "45s", "--mix", str(mix45 or mix), "--out", str(out), *c])


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT, help="where the previews and sheets go")
    ap.add_argument("--frames-dir", type=Path, help="the shots' frames (default OUT/frames)")
    ap.add_argument("--source", choices=["2160p", "1080p"], default="2160p", help="the frames' resolution (cut.py)")
    ap.add_argument("--hold-first", default="", help="cut.py's --hold-first: shots whose first frame is ghosted")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull")
    p.add_argument("shot")
    p.add_argument("remote")
    p = sub.add_parser("check")
    p.add_argument("shots", nargs="*")
    p = sub.add_parser("sheet")
    p.add_argument("shot")
    p.add_argument("--every", type=int, default=6)
    p = sub.add_parser("preview")
    p.add_argument("--mix", type=Path, required=True)
    p.add_argument("--cues", type=Path)
    p.add_argument("--scale", type=float, default=1.0, help="cut.py's --scale (less for a quick look)")
    p = sub.add_parser("final")
    p.add_argument("--mix", type=Path, required=True)
    p.add_argument("--mix45", type=Path, help="R5's mix for the 45 s cut (else the full mix, cut on its edits)")
    p.add_argument("--cues", type=Path)
    p.add_argument("--only", default="", help="cut.py's --only: prores,1080p skips the 9:16")
    a = ap.parse_args(argv)
    frames = a.frames_dir or a.out / "frames"
    if a.cmd == "pull":
        pull(frames, a.shot.upper(), a.remote)
    elif a.cmd == "check":
        check(frames, [x.upper() for x in a.shots])
    elif a.cmd == "sheet":
        sheet(frames, a.out, a.shot.upper(), a.every)
    elif a.cmd == "final":
        final(frames, a.out, a.mix, a.mix45, a.cues, a.source, a.hold_first, a.only)
    else:
        preview(frames, a.out, a.mix, a.cues, a.scale, a.source, a.hold_first)


if __name__ == "__main__":
    main()
