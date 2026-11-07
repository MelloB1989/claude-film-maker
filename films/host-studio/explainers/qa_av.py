"""Explainer QA numbers that are not the editor's: loudness, exposure stability, captions vs the VO, facts sourced.

Each command prints (and with --out writes) gate-contract numbers, {"gate": {item: {"value", "where"}}}, for
film-qa gate --spec films/host-studio/explainers/gate_spec.json. QA.md says which item comes from where.

    python3 qa_av.py loudness CUT.mp4|MIX.wav [--out n.json]
    python3 qa_av.py format CUT.mp4 [--out n.json]
    python3 qa_av.py exposure FRAMES_DIR --shots shots.json [--box x0,y0,x1,y1] [--pattern '*.png'] [--out n.json]
    python3 qa_av.py captions CUT.srt VO_CUES.json [--out n.json]
    python3 qa_av.py facts VO_CUES.json FACTS.json [--out n.json]
    python3 qa_av.py all CUT.mp4 CUT.srt VO_CUES.json --facts FACTS.json --out numbers/<film>/cut.json   # on the box

FACE RULE: frames and cuts with a presenter in them are private. Run `exposure` and `loudness` on a cut ON THE BOX
(they write numbers only); captions and facts read text only.

The VO cue sheet: agent-11's audio/<film>/cues.json ("lines": [{"id", "text", "start", "end", "words"}], seconds on
the cut's clock), or {"lines": {id: {"text", "start_s", "end_s"}}}. facts.json: {"claims": [{"text": "100 billion
messages a day", "source": "<url>", "said": "over a hundred billion"}]}.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

LUFS, TOL, TP = -14.0, 0.5, -1.0
SOFT = ("over", "about", "around", "nearly", "almost", "more than", "roughly", "some", "upwards of", "close to",
        "hundreds of", "thousands of", "millions of", "billions of", "up to", "under", "less than")
MAG = r"(?:hundred|thousand|million|billion|trillion)"
# a number the VO claims: digits (with a unit or magnitude) or a magnitude word run ("a hundred billion"); small
# counting words ("one connection") are not claims
SMALL = (r"(?:(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|"
         r"sixty|seventy|eighty|ninety)[\s-]+)*")
NUM = re.compile(rf"\b\d[\d,.]*(?:\s*(?:%|percent|k\b|{MAG}))*|\b{SMALL}{MAG}(?:\s+{MAG})*\b", re.I)


def vo_lines(vo: dict) -> list:
    """[(id, {"text", "start_s", "end_s"})] in time order, from agent-11's cues.json ("lines": [{"id", "text", "start",
    "end"}]) or the {"lines": {id: {"text", "start_s", "end_s"}}} form."""
    ls = vo["lines"]
    if isinstance(ls, list):
        ls = {d["id"]: {"text": d["text"], "start_s": float(d["start"]), "end_s": float(d["end"])} for d in ls}
    return sorted(ls.items(), key=lambda kv: kv[1]["start_s"])


def row(v, where):
    return {"value": v, "where": where}


# --- loudness ----------------------------------------------------------------------------------------------------
def parse_ebur128(text: str) -> tuple[float, float]:
    s = text[text.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", s)
    p = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s)
    if not i or not p:
        raise ValueError("no ebur128 summary (no audio stream?)")
    return float(i.group(1)), float(p.group(1))


def loudness(path: str) -> dict:
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0", "-af",
                            "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
        i, tp = parse_ebur128(r.stderr)
    except (OSError, ValueError) as e:  # no ffmpeg here (run it on a box), or no audio stream
        return {"audio.lufs_err_lu": {"value": None, "error": str(e)},
                "audio.true_peak_dbtp": {"value": None, "error": str(e)}}
    w = f"{os.path.basename(path)}: {i:.1f} LUFS, {tp:.1f} dBTP"
    return {"audio.lufs_err_lu": row(round(abs(i - LUFS), 2), w), "audio.true_peak_dbtp": row(tp, w)}


# --- format ------------------------------------------------------------------------------------------------------
def format_numbers(info: dict) -> dict:
    """ffprobe -show_streams -show_format JSON -> deliver.format_ok (1920x1080 square pixels, 16:9, constant 24/25/30
    fps, one video + one audio stream, 48 kHz) and deliver.duration_s (info)."""
    v = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    a = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    bad = []
    if len(v) != 1 or len(a) != 1:
        bad.append(f"{len(v)} video / {len(a)} audio streams")
    if v:
        w, h = int(v[0].get("width", 0)), int(v[0].get("height", 0))
        if (w, h) != (1920, 1080):
            bad.append(f"{w}x{h}, not 1920x1080 (16:9 only)")
        if v[0].get("sample_aspect_ratio", "1:1") not in ("1:1", "0:1"):
            bad.append(f"SAR {v[0]['sample_aspect_ratio']}")
        n, _, d = str(v[0].get("avg_frame_rate", "0/1")).partition("/")
        fps = float(n) / float(d or 1) if float(d or 1) else 0
        if not any(abs(fps - f) < 0.01 for f in (24, 25, 30)):
            bad.append(f"{fps:.3f} fps")
    if a and int(a[0].get("sample_rate", 0)) != 48000:
        bad.append(f"audio {a[0].get('sample_rate')} Hz")
    dur = float(info.get("format", {}).get("duration") or 0)
    return {"deliver.format_ok": row(0 if bad else 1, "; ".join(bad) or "1920x1080, 16:9"),
            "deliver.duration_s": row(round(dur, 2), "the cut")}


def probe(path: str) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


# --- exposure ----------------------------------------------------------------------------------------------------
def stops(lumas: list) -> list:
    return [math.log2(max(v, 1e-4) / 0.18) for v in lumas]


def exposure_numbers(per_shot: dict, win: int = 12) -> dict:
    """{shot: [mean linear luma per frame]} -> the worst frame-to-frame jump and the worst drift (max - min of a
    `win`-frame moving average) inside a shot, in stops. A shot's own change across its cut is not judged."""
    jump, drift, wj, wd = 0.0, 0.0, "", ""
    for shot, ls in per_shot.items():
        s = stops(ls)
        for k in range(1, len(s)):
            if abs(s[k] - s[k - 1]) > jump:
                jump, wj = abs(s[k] - s[k - 1]), f"{shot} frame {k - 1}->{k}"
        if len(s) >= win:
            ma = [sum(s[k:k + win]) / win for k in range(len(s) - win + 1)]
            if max(ma) - min(ma) > drift:
                drift, wd = max(ma) - min(ma), f"{shot} ({len(s)} frames)"
        elif len(s) > 1 and max(s) - min(s) > drift:
            drift, wd = max(s) - min(s), f"{shot} ({len(s)} frames, shorter than {win})"
    return {"shot.exposure_jump_stops": row(round(jump, 3), wj or "every shot"),
            "shot.exposure_drift_stops": row(round(drift, 3), wd or "every shot")}


def luma(path: str, box=None) -> float:
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    if box:
        h, w = a.shape[:2]
        a = a[int(box[1] * h):int(box[3] * h), int(box[0] * w):int(box[2] * w)]
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    # the median: a hand or the mic crossing less than half of the face box does not move it; the light does
    return float(np.median(lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)))


def exposure(frames_dir: str, shots: list, box=None, pattern: str = "*.png") -> dict:
    """shots: [[name, first_frame, end_frame_exclusive], ...] on the frame numbers in the file names. box: one
    [x0, y0, x1, y1] (fractions) for every frame, or {frame: box} (a face box tracked per frame, e.g. from the eye
    bones through the shot camera): the face moves, the box follows, so a head turn is not read as light."""
    files = sorted(glob.glob(os.path.join(frames_dir, pattern)))
    by_num = {}
    for f in files:
        m = re.findall(r"(\d+)", os.path.basename(f))
        if m:
            by_num[int(m[-1])] = f
    per, missing = {}, []
    for name, a, b in shots:
        got = [by_num.get(k) for k in range(int(a), int(b))]
        missing += [k for k, g in zip(range(int(a), int(b)), got) if g is None]
        per[name] = [luma(g, box.get(k) or box.get(str(k)) if isinstance(box, dict) else box)
                     for k, g in zip(range(int(a), int(b)), got) if g]
    out = exposure_numbers(per)
    if missing:
        for k in out:
            out[k] = {"value": None, "error": f"{len(missing)} frames missing (first {missing[:5]})"}
    return out


# --- captions ----------------------------------------------------------------------------------------------------
def words(t: str) -> list:
    t = t.lower().replace("’", "'").replace("—", " ").replace("–", " ")
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", t)


def parse_srt(text: str) -> list:
    def secs(s):
        h, m, rest = s.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(rest)
    out = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        ls = [x for x in block.split("\n") if x.strip()]
        for i, ln in enumerate(ls):
            m = re.match(r"^\s*([\d:.,]+)\s*-->\s*([\d:.,]+)", ln)
            if m:
                out.append([secs(m.group(1)), secs(m.group(2)), " ".join(ls[i + 1:]).strip()])
                break
    return out


def captions_numbers(cues: list, vo: dict) -> dict:
    """Captions vs the VO. captions.text_match: the caption words in order equal the VO lines' words in order (case
    and punctuation ignored), 1/0. captions.onset_ms: the worst |first caption start - line start| over the lines, ms
    (a line's captions are those overlapping [start - reach_s, end)); a line with no caption is an error."""
    lines = vo_lines(vo)
    want = [w for _, ln in lines for w in words(ln["text"])]
    got = [w for c in cues for w in words(c[2])]
    if want == got:
        tm = row(1, f"{len(got)} words, {len(cues)} captions")
    else:
        k = next((i for i, (a, b) in enumerate(zip(want, got)) if a != b), min(len(want), len(got)))
        tm = row(0, f"word {k}: VO {' '.join(want[max(0, k - 3):k + 3])!r} vs captions "
                    f"{' '.join(got[max(0, k - 3):k + 3])!r} ({len(want)} vs {len(got)} words)")
    # each caption's words, in order, belong to the VO words in order: a line's onset is judged against the caption
    # that carries its FIRST word (time overlap would pick the previous line's caption still on screen)
    owner, k = [], 0
    for ci, c in enumerate(cues):
        for _ in words(c[2]):
            owner.append(ci)
            k += 1
    worst, where, unmatched, k = -1.0, "", [], 0
    for lid, ln in lines:
        n = len(words(ln["text"]))
        if not n:
            continue
        if k >= len(owner) or (want[k:k + n] != got[k:k + n]):
            unmatched.append(lid)
        else:
            c = cues[owner[k]]
            err = abs(c[0] - ln["start_s"]) * 1000
            if err > worst:
                worst, where = err, f"{lid}: caption {c[0]:.2f} s, VO {ln['start_s']:.2f} s"
        k += n
    timing = ({"value": None, "error": f"captions do not carry line(s) {', '.join(unmatched)} word for word"}
              if unmatched else row(round(max(worst, 0)), where or "no lines"))
    return {"captions.text_match": tm, "captions.onset_ms": timing}


# --- facts -------------------------------------------------------------------------------------------------------
def facts_numbers(vo: dict, facts: dict) -> dict:
    """Every number the VO says is either softened (SOFT words just before it) or matches a claim in facts.json
    that carries a source. facts.sourced = 1 when none is left; where lists the first unsourced ones."""
    sourced = [words(c.get("said") or c.get("text") or "") for c in facts.get("claims", []) if c.get("source")]
    bad = []
    for lid, ln in vo_lines(vo):
        t = ln["text"]
        for m in NUM.finditer(t):
            before = re.sub(r"\s+(?:a|an)$", "", t[:m.start()].lower().rstrip())
            if any(before.endswith(s) for s in SOFT):
                continue
            ws = words(t[max(0, m.start() - 40):m.end() + 40])
            num = words(m.group(0))
            if any(num and all(w in c for w in num) and len(set(c) & set(ws)) >= max(1, len(c) // 2) for c in sourced):
                continue
            bad.append(f"{lid}: {m.group(0).strip()!r}")
    return {"facts.sourced": row(0 if bad else 1, "; ".join(bad[:6]) if bad else "every number softened or sourced")}


def qc_row(path: str, srt: str | None) -> dict:
    """deliver.qc_ok from film-post qc (filmtools.unreal.post_qc: black/frozen runs, captions timing/safe area)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
        from filmtools.unreal import post_qc
        rep = post_qc.run(Path(path), None, Path(srt) if srt else None)
    except Exception as e:  # noqa: BLE001 (no ffmpeg, no tools tree: an error row, never a pass)
        return {"deliver.qc_ok": {"value": None, "error": f"film-post qc: {e}"}}
    fails = [i.get("message", i.get("code")) for i in rep.get("issues", []) if i.get("severity") == "fail"]
    return {"deliver.qc_ok": row(0 if fails or rep.get("pass") is False else 1, "; ".join(map(str, fails[:4])) or "pass")}


def all_rows(cut: str, srt: str, cues: str, facts: str | None) -> dict:
    vo = json.loads(Path(cues).read_text())
    g = {**loudness(cut)}
    try:
        g.update(format_numbers(probe(cut)))
    except (OSError, subprocess.CalledProcessError) as e:
        g.update({k: {"value": None, "error": str(e)} for k in ("deliver.format_ok", "deliver.duration_s")})
    g.update(captions_numbers(parse_srt(Path(srt).read_text()), vo))
    if facts:
        g.update(facts_numbers(vo, json.loads(Path(facts).read_text())))
    g.update(qc_row(cut, srt))
    return g


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("loudness"); a.add_argument("file")
    fm = sub.add_parser("format"); fm.add_argument("file")
    e = sub.add_parser("exposure"); e.add_argument("frames"); e.add_argument("--shots", required=True)
    e.add_argument("--box", default="", help="x0,y0,x1,y1 (fractions) for every frame")
    e.add_argument("--boxes", default="", help="JSON {frame: [x0,y0,x1,y1]}: a face box tracked per frame")
    e.add_argument("--pattern", default="*.png")
    c = sub.add_parser("captions"); c.add_argument("srt"); c.add_argument("vo")
    f = sub.add_parser("facts"); f.add_argument("vo"); f.add_argument("facts")
    al = sub.add_parser("all", help="every cut row at once: loudness, format, captions, facts, film-post qc")
    al.add_argument("cut"); al.add_argument("srt"); al.add_argument("cues"); al.add_argument("--facts", default="")
    for p in (a, fm, e, c, f, al):
        p.add_argument("--out", default="")
    x = ap.parse_args(argv)
    if x.cmd == "loudness":
        g = loudness(x.file)
    elif x.cmd == "format":
        try:
            g = format_numbers(probe(x.file))
        except (OSError, subprocess.CalledProcessError) as e:  # no ffprobe here (run it on a box), or not a video
            g = {k: {"value": None, "error": str(e)} for k in ("deliver.format_ok", "deliver.duration_s")}
    elif x.cmd == "exposure":
        box = ({int(k): v for k, v in json.loads(Path(x.boxes).read_text()).items()} if x.boxes else
               [float(v) for v in x.box.split(",")] if x.box else None)
        g = exposure(x.frames, json.loads(Path(x.shots).read_text()), box, x.pattern)
    elif x.cmd == "all":
        g = all_rows(x.cut, x.srt, x.cues, x.facts or None)
    elif x.cmd == "captions":
        g = captions_numbers(parse_srt(Path(x.srt).read_text()), json.loads(Path(x.vo).read_text()))
    else:
        g = facts_numbers(json.loads(Path(x.vo).read_text()), json.loads(Path(x.facts).read_text()))
    out = json.dumps({"gate": g}, indent=1)
    if x.out:
        Path(x.out).write_text(out + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
