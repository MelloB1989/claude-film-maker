"""Round 4 finals QA (agent-09), ON THE BOX, read-only, numbers only (nothing in the report is a picture, so it may leave
the box even with Host_Op in the frames):

    cd tools && uv run --with pillow --with numpy python ../films/host-studio/reel/r3/final_qa.py \\
        --final /srv/ue/reel/r3/final_d --cut /srv/ue/reel/r3/cut/final --out /srv/ue/reel/r3/qa/final_qa.json

1. frames (final_d): per shot, every master frame [start, end) on disk (V01 and S18 with their 12-frame handles, as
   final_check.py), readable, 1920x1080, no black (mean luma < 0.01) or white (> 0.97) frame, and the luma jumps
   between consecutive frames (cuts excluded; reported, judged by eye against the light plan's steps).
2. cuts (R3_CUT): each deliverable of the 65 s and 45 s cuts: frame count (1560 / 1080), size, audio length against
   the picture, and its loudness measured again here (ebur128: -14 +- 1 LUFS integrated, true peak <= -1 dBTP).
3. caption sync: each .srt cue against the VO's own word times (cues.json, mapped through the cut's EDL from
   cut[-45s].json): the first cue of every line starts within CAPTION_TOL frames of the line's first word, no cue
   falls outside the picture, and every line the cut keeps has its captions.

Exit 1 when anything fails; the JSON lists each failure with its frames.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from shots import LINES, SHOTS  # noqa: E402

FPS = 24
H = 12                      # handles on the first and last shot (final_check.py)
BLACK, WHITE = 0.01, 0.97   # mean luma (0-1) of a black / blown-out frame
SIZE = (1920, 1080)
FRAMES = {"65s": 1560, "45s": 1080}
LUFS, LUFS_TOL, TP_MAX = -14.0, 1.0, -1.0
CAPTION_TOL = 2             # frames between a line's first word and its first caption


def name(f: int) -> str:
    return ("-" if f < 0 else "") + f"{abs(f):04d}.png"


def frames_qa(root: Path) -> dict:
    import numpy as np
    from PIL import Image
    have_any = {p.name for p in root.glob("*.png")}
    shots, bad = {}, []
    for k, s in enumerate(SHOTS):
        a = s.start - (H if k == 0 else 0)
        b = s.end + (H if k == len(SHOTS) - 1 else 0)
        miss, unread, black, white, wrong, lum = [], [], [], [], [], {}
        for f in range(a, b):
            n = name(f)
            if n not in have_any:
                miss.append(f)
                continue
            try:
                im = Image.open(root / n)
                if im.size != SIZE:
                    wrong.append([f, list(im.size)])
                g = np.asarray(im.convert("L").reduce(4), np.float32) / 255.0
            except Exception:  # noqa: BLE001 - a truncated or unreadable file
                unread.append(f)
                continue
            m = float(g.mean())
            lum[f] = m
            if m < BLACK:
                black.append(f)
            if m > WHITE:
                white.append(f)
        jumps = [[f, round(lum[f - 1], 3), round(lum[f], 3)] for f in sorted(lum)
                 if f - 1 in lum and abs(lum[f] - lum[f - 1]) > max(0.03, 0.15 * lum[f - 1])]
        r = {"range": [a, b], "expected": b - a, "on_disk": b - a - len(miss), "missing": miss[:20],
             "n_missing": len(miss), "unreadable": unread[:10], "black": black[:10], "white": white[:10],
             "wrong_size": wrong[:5], "lum_jumps": jumps[:10],
             "lum_min_max": [round(min(lum.values()), 3), round(max(lum.values()), 3)] if lum else None}
        for key, what in (("missing", "missing"), ("unreadable", "unreadable"), ("black", "black"),
                          ("white", "white"), ("wrong_size", "not 1920x1080")):
            if r[key]:
                bad.append(f"{s.id}: {len(r[key]) if key != 'missing' else len(miss)} {what}, first {r[key][:5]}")
        shots[s.id] = r
    return {"pass": not bad, "failed": bad, "shots": shots}


def ffprobe(p: Path, ff: str) -> dict:
    # ffprobe beside ffmpeg, by the binary's name only: the static build lives in .../ffmpeg/bin/
    probe = str(Path(ff).with_name(Path(ff).name.replace("ffmpeg", "ffprobe")))
    r = subprocess.run([probe, "-v", "error", "-print_format", "json", "-show_streams",
                        "-show_format", "-count_frames", str(p)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def loudness(p: Path, ff: str) -> dict:
    r = subprocess.run([ff, "-hide_banner", "-nostats", "-i", str(p), "-map", "0:a:0", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    tp = re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
    return {"I": float(i.group(1)) if i else None, "TP": float(tp.group(1)) if tp else None}


def spans_out(segs: list, a: float, b: float) -> list:  # cut.py's: master [a, b) on the output clock
    out, off = [], 0
    for sa, sb in segs:
        lo, hi = max(a, sa), min(b, sb)
        if lo < hi:
            out.append((off + lo - sa, off + hi - sa))
        off += sb - sa
    return out


def srt(p: Path) -> list:
    t = lambda h, m, s, ms: (int(h) * 3600 + int(m) * 60 + int(s)) * FPS + int(ms) * FPS / 1000  # noqa: E731
    out = []
    for blk in p.read_text().strip().split("\n\n"):
        x = re.search(r"(\d+):(\d+):(\d+)[,.](\d+) --> (\d+):(\d+):(\d+)[,.](\d+)\n(.*)", blk, re.S)
        if x:
            g = x.groups()
            out.append([t(*g[:4]), t(*g[4:8]), g[8].strip()])
    return out


def captions_qa(srt_path: Path, report: dict, cues: dict | None, n: int) -> dict:
    segs = [tuple(x) for x in report["frames"]]
    got = srt(srt_path)
    bad = [f"cue '{c[2][:30]}' {c[0]:.1f}-{c[1]:.1f} outside the picture (0-{n})" for c in got
           if c[0] < 0 or c[1] > n + 0.5]
    lines = {}
    for k, w, f0, f1, text in LINES:
        if not spans_out(segs, f0, f1):
            continue  # the cut drops this line
        first = f0
        if cues:  # the VO's own first word (cues.json, master frames)
            ws = [x for kk, v in cues.items() if kk == k or (kk.startswith(k) and kk[len(k):].isalpha())
                  for x in v.get("words", [])]
            if ws:
                first = min(x["start"] for x in ws)
        o = spans_out(segs, first, first + 1)
        want = o[0][0] if o else None
        word = re.sub(r"[^\w]", "", text.split()[0]).lower()
        mine = [c for c in got if re.sub(r"[^\w]", "", c[2].split()[0]).lower() == word] if text.split() else []
        if want is None:
            lines[k] = {"pass": None, "why": "its first word is cut"}
            continue
        if not mine:
            lines[k] = {"pass": False, "want_frame": want}
            bad.append(f"{k}: no caption (its first word is at cut frame {want})")
            continue
        c = min(mine, key=lambda c: abs(c[0] - want))
        d = round(c[0] - want, 1)
        lines[k] = {"pass": abs(d) <= CAPTION_TOL, "caption_at": round(c[0], 1), "word_at": want, "off_frames": d}
        if abs(d) > CAPTION_TOL:
            bad.append(f"{k}: caption at cut frame {c[0]:.1f}, the word at {want} ({d:+} frames)")
    return {"pass": not bad, "failed": bad, "cues": len(got), "lines": lines,
            "timed_from": "cues.json" if cues else "LINES (no cues.json: coarse)"}


def cut_qa(cut: Path, cues_path: Path | None, ff: str) -> dict:
    cues = json.loads(cues_path.read_text())["lines"] if cues_path and cues_path.exists() else None
    res, bad = {}, []
    for tag, n in FRAMES.items():
        rep_p = cut / ("cut.json" if tag == "65s" else f"cut-{tag}.json")
        stem = "karma-reel" if tag == "65s" else f"karma-reel-{tag}"
        outs = sorted(cut.glob(f"{stem}-1080p-*.mp4")) + sorted(cut.glob(f"{stem}-1080p-*.mov"))
        if tag == "65s":
            outs = [p for p in outs if not p.name.startswith("karma-reel-45s")]
        r = {"report": rep_p.name if rep_p.exists() else None, "outputs": {}}
        if not rep_p.exists() or not outs:
            bad.append(f"{tag}: {'no ' + rep_p.name if not rep_p.exists() else 'no deliverables'} in {cut}")
            res[tag] = r
            continue
        report = json.loads(rep_p.read_text())
        for p in outs:
            info = ffprobe(p, ff)
            v = next(s for s in info["streams"] if s["codec_type"] == "video")
            a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
            fr = int(v.get("nb_read_frames") or v.get("nb_frames") or 0)
            o = {"frames": fr, "size": [v["width"], v["height"]], "codec": v["codec_name"],
                 "audio_s": round(float(a["duration"]), 3) if a else None, "loud": loudness(p, ff) if a else None}
            pr = []
            if fr != n:
                pr.append(f"{fr} frames, not {n}")
            if (v["width"], v["height"]) != SIZE:
                pr.append(f"{v['width']}x{v['height']}")
            if not a or abs(float(a["duration"]) - n / FPS) > 1.5 / FPS:
                pr.append(f"audio {o['audio_s']} s against {n / FPS:.3f} s")
            L = o["loud"] or {}
            if L.get("I") is None or abs(L["I"] - LUFS) > LUFS_TOL:
                pr.append(f"{L.get('I')} LUFS (want {LUFS:g} +- {LUFS_TOL:g})")
            if L.get("TP") is None or L["TP"] > TP_MAX:
                pr.append(f"true peak {L.get('TP')} dBTP (want <= {TP_MAX:g})")
            o["problems"] = pr
            bad += [f"{p.name}: {x}" for x in pr]
            r["outputs"][p.name] = o
        s = cut / f"{stem}.srt"
        if s.exists():
            r["captions"] = captions_qa(s, report, cues, n)
            bad += [f"{tag} captions: {x}" for x in r["captions"]["failed"]]
        else:
            bad.append(f"{tag}: no {s.name}")
        r["cut_json_missing"] = report.get("missing")
        if report.get("missing"):
            bad.append(f"{tag}: cut.json says {report['missing']} frames were filled (a rough cut)")
        res[tag] = r
    return {"pass": not bad, "failed": bad, "cuts": res}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", default="", help="the finals' dir (final_d)")
    ap.add_argument("--cut", default="", help="the cut's out dir (R3_CUT)")
    ap.add_argument("--cues", default=str(HERE.parents[3] / "out/host-studio/reel/vo/cues.json"))
    ap.add_argument("--ffmpeg", default="/srv/ue/tools/ffmpeg/bin/ffmpeg")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rep = {}
    if a.final:
        rep["frames"] = frames_qa(Path(a.final))
    if a.cut:
        rep["cut"] = cut_qa(Path(a.cut), Path(a.cues) if a.cues else None, a.ffmpeg)
    rep["pass"] = all(v["pass"] for v in rep.values() if isinstance(v, dict))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, indent=1))
    print(json.dumps({"pass": rep["pass"], **{k: {"pass": v["pass"], "failed": v["failed"][:20]}
                                             for k, v in rep.items() if isinstance(v, dict)}}, indent=1))
    sys.exit(0 if rep["pass"] else 1)


if __name__ == "__main__":
    main()
