"""Delivery QC (BACKLOG B53): one report over a delivered file, its EDL and its captions, in the check shape of
CONVENTIONS §8: {"pass", "issues": [{"code", "severity", "message", "fix", "frame"?, "value"?, "expected"?}],
"metrics"}. JSON for an agent, and a Markdown sheet for a person.

    film-post qc out/demo/demo-web.mp4 --edl out/demo/demo.edl --captions out/demo/demo.srt [-o qc.json --md qc.md]

What it checks:
- streams        one video and one audio stream (qc.streams)
- duration       the picture's frame count against the EDL's record length, the audio's length against the picture's
                 (within 1.5 frames) (qc.duration_*)
- loudness       integrated loudness within ±tol LU of the target, true peak under the ceiling (qc.loudness_*)
- black          black runs of at least max_black_s outside the head and tail allowance (qc.black_frames)
- frozen         frozen runs of at least max_freeze_s (qc.frozen_frames)
- captions       inside the picture, in order, not overlapping, at least min_caption_s long, reading speed under
                 max_cps characters a second, a gap of at least 2 frames between cues (qc.caption_*)
- caption safe   the longest cue wraps to at most 2 lines inside the output's safe area (post_cut.caption_safe_check)
- caption cuts   a cue that runs across a cut of the EDL (warn: it should change with the picture)

Everything is pure over the probe results; the probes (ffprobe, ffmpeg ebur128 / blackdetect / freezedetect) are
one object, `Probes`, which tests replace.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import post_cut

DEFAULTS = {"lufs": -14.0, "true_peak": -1.0, "lufs_tol": 1.0, "max_black_s": 0.5, "edge_s": 1.0,
            "max_freeze_s": 2.0, "min_caption_s": 0.7, "max_cps": 20.0, "min_gap_frames": 2}


# --- the probes (I/O) -----------------------------------------------------------------------------------------------


def _ff(args: list) -> str:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *map(str, args), "-f", "null", "-"],
                       capture_output=True, text=True)
    return r.stderr


@dataclass
class Probes:
    """The measurements, each a thin ffmpeg/ffprobe call returning text or JSON; parse_* turn them into numbers."""
    black_pix: float = 0.10   # blackdetect pix_th
    freeze_noise: str = "-60dB"

    def probe(self, path: Path) -> dict:
        r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
                            "-count_frames", str(path)], capture_output=True, text=True, check=True)
        return json.loads(r.stdout)

    def ebur128(self, path: Path) -> str:
        return _ff(["-i", path, "-map", "0:a:0", "-af", "ebur128=peak=true"])

    def blackdetect(self, path: Path, min_s: float) -> str:
        return _ff(["-i", path, "-map", "0:v:0", "-vf", f"blackdetect=d={min_s}:pix_th={self.black_pix}"])

    def freezedetect(self, path: Path, min_s: float) -> str:
        return _ff(["-i", path, "-map", "0:v:0", "-vf", f"freezedetect=n={self.freeze_noise}:d={min_s}"])


# --- parsers (pure) -------------------------------------------------------------------------------------------------


def parse_ebur128(text: str) -> dict:
    """{"I", "TP", "LRA"} from ffmpeg ebur128's summary (the last one in the log)."""
    tail = text[text.rfind("Summary:"):] if "Summary:" in text else text

    def num(pat):
        m = re.search(pat, tail)
        return float(m.group(1)) if m else None
    return {"I": num(r"I:\s*(-?[\d.]+|-inf)\s*LUFS"), "TP": num(r"Peak:\s*(-?[\d.]+)\s*dBFS"),
            "LRA": num(r"LRA:\s*(-?[\d.]+)\s*LU")}


def parse_black(text: str) -> list:
    """[[start_s, end_s]] from blackdetect lines."""
    return [[float(a), float(b)] for a, b in re.findall(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", text)]


def parse_freeze(text: str, duration: float) -> list:
    """[[start_s, end_s]] from freezedetect's freeze_start / freeze_end (a freeze still on at the end runs to it)."""
    starts = [float(x) for x in re.findall(r"freeze_start:\s*([\d.]+)", text)]
    ends = [float(x) for x in re.findall(r"freeze_end:\s*([\d.]+)", text)]
    return [[s, ends[i] if i < len(ends) else duration] for i, s in enumerate(starts)]


def parse_tc(tc: str, fps: float) -> int:
    h, m, s, f = (int(x) for x in re.split(r"[:;]", tc))
    n = int(round(fps))
    return ((h * 60 + m) * 60 + s) * n + f


def parse_edl(text: str, fps: float) -> dict:
    """A CMX 3600 EDL as {"events": [{"n", "clip", "src_in", "src_out", "rec_in", "rec_out"}], "frames", "cuts"}
    (frames on the record side; cuts = the record frames where a new event starts)."""
    events, last = [], None
    for ln in text.splitlines():
        m = re.match(r"^(\d{3,})\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", ln)
        if m:
            last = {"n": int(m.group(1)), "clip": "", "src_in": parse_tc(m.group(2), fps),
                    "src_out": parse_tc(m.group(3), fps), "rec_in": parse_tc(m.group(4), fps),
                    "rec_out": parse_tc(m.group(5), fps)}
            events.append(last)
        elif last is not None and ln.startswith("* FROM CLIP NAME:"):
            last["clip"] = ln.split(":", 1)[1].strip()
    return {"events": events, "frames": max((e["rec_out"] for e in events), default=0),
            "cuts": sorted({e["rec_in"] for e in events if e["rec_in"] > 0})}


def _secs(t: str) -> float:
    h, m, rest = t.strip().replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def parse_captions(text: str) -> list:
    """[[start_s, end_s, text]] from SRT or WebVTT."""
    out = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = [x for x in block.split("\n") if x.strip()]
        for i, ln in enumerate(lines):
            m = re.match(r"^\s*([\d:.,]+)\s*-->\s*([\d:.,]+)", ln)
            if m:
                out.append([_secs(m.group(1)), _secs(m.group(2)), " ".join(lines[i + 1:]).strip()])
                break
    return out


# --- checks (pure) --------------------------------------------------------------------------------------------------


def _issue(code, severity, message, fix="", **kw) -> dict:
    d = {"code": code, "severity": severity, "message": message}
    if fix:
        d["fix"] = fix
    d.update({k: v for k, v in kw.items() if v is not None})
    return d


def _rate(s: str) -> float:
    a, _, b = str(s).partition("/")
    return float(a) / float(b or 1)


def stream_facts(info: dict) -> dict:
    """The facts the checks need from ffprobe's JSON."""
    v = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    a = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    f = {"video_streams": len(v), "audio_streams": len(a)}
    if v:
        f.update({"width": int(v[0]["width"]), "height": int(v[0]["height"]), "fps": _rate(v[0].get("r_frame_rate", "0")),
                  "frames": int(v[0].get("nb_read_frames") or v[0].get("nb_frames") or 0),
                  "video_codec": v[0].get("codec_name")})
    if a:
        f.update({"audio_s": float(a[0].get("duration") or info.get("format", {}).get("duration") or 0),
                  "audio_codec": a[0].get("codec_name"), "sample_rate": int(a[0].get("sample_rate") or 0)})
    f["duration_s"] = float(info.get("format", {}).get("duration") or 0)
    return f


def check_streams(f: dict) -> list:
    if f["video_streams"] == 1 and f["audio_streams"] == 1:
        return []
    return [_issue("qc.streams", "fail", f"{f['video_streams']} video and {f['audio_streams']} audio streams, not 1 "
                   "and 1", "re-encode with -map 0:v:0 -map 1:a:0 (film-post cut does)")]


def check_duration(f: dict, edl: dict | None, fps: float) -> list:
    out = []
    n = f.get("frames", 0)
    if edl and edl["frames"] and n != edl["frames"]:
        out.append(_issue("qc.duration_vs_edl", "fail", f"{n} frames against the EDL's {edl['frames']} "
                          f"({(n - edl['frames']) / fps:+.3f} s)", "re-cut from the delivery spec: film-post cut",
                          value=n, expected=edl["frames"]))
    if "audio_s" in f and n and abs(f["audio_s"] - n / fps) > 1.5 / fps:
        out.append(_issue("qc.duration_audio", "fail", f"audio {f['audio_s']:.3f} s against picture {n / fps:.3f} s",
                          "pad or trim the mix to the picture (never -shortest): film-post cut",
                          value=round(f["audio_s"], 3), expected=round(n / fps, 3)))
    return out


def check_loudness(m: dict, o: dict) -> list:
    if m.get("I") is None:
        return [_issue("qc.loudness_unmeasured", "warn", "no loudness summary from ebur128 (silent or no audio?)")]
    out = []
    if abs(m["I"] - o["lufs"]) > o["lufs_tol"]:
        out.append(_issue("qc.loudness_off_target", "fail", f"{m['I']:.1f} LUFS, target {o['lufs']:g} ±{o['lufs_tol']:g}",
                          "remaster: filmtools.mix.loudnorm (film-post cut remasters a cut that drifts)",
                          value=m["I"], expected=o["lufs"]))
    if m.get("TP") is not None and m["TP"] > o["true_peak"]:
        out.append(_issue("qc.true_peak_over", "fail", f"true peak {m['TP']:.1f} dBTP over {o['true_peak']:g}",
                          "remaster with the limiter's ceiling lower (filmtools.mix limit_dbfs)",
                          value=m["TP"], expected=o["true_peak"]))
    return out


def check_runs(runs: list, kind: str, duration: float, fps: float, o: dict) -> list:
    """Black or frozen runs as issues: black only outside the head/tail allowance (fades), frozen anywhere."""
    out = []
    for a, b in runs:
        if kind == "black":
            if b - a < o["max_black_s"] or b <= o["edge_s"] or a >= duration - o["edge_s"]:
                continue
            code, fix = "qc.black_frames", "a missing render or a slate in the cut: film-post frames lists the gaps"
        else:
            if b - a < o["max_freeze_s"]:
                continue
            code, fix = "qc.frozen_frames", "repeated frames: a stalled render or a held still in the edit"
        out.append(_issue(code, "fail" if kind == "black" else "warn",
                          f"{kind} {a:.2f}-{b:.2f} s ({b - a:.2f} s)", fix, frame=int(round(a * fps)),
                          value=round(b - a, 3)))
    return out


def check_captions(cues: list, duration: float, fps: float, o: dict, size: tuple | None, cuts_s: list) -> list:
    out = []
    for i, (a, b, t) in enumerate(cues):
        tag = f"cue {i + 1} {t[:32]!r}"
        if a < 0 or b > duration + 0.5 / fps:
            out.append(_issue("qc.caption_outside", "fail", f"{tag} at {a:.2f}-{b:.2f} s is outside the "
                              f"{duration:.2f} s picture", "re-time the captions on the cut", frame=int(a * fps)))
        if b - a < o["min_caption_s"]:
            out.append(_issue("qc.caption_short", "warn", f"{tag} is on screen {b - a:.2f} s",
                              f"hold it at least {o['min_caption_s']:g} s (captions.hold_frames)", frame=int(a * fps),
                              value=round(b - a, 3), expected=o["min_caption_s"]))
        cps = len(t) / max(b - a, 1e-6)
        if cps > o["max_cps"]:
            out.append(_issue("qc.caption_fast", "warn", f"{tag} reads at {cps:.0f} characters a second",
                              f"under {o['max_cps']:g}: split it (captions.max_chars) or hold it longer",
                              frame=int(a * fps), value=round(cps, 1), expected=o["max_cps"]))
        if i:
            pa, pb, _ = cues[i - 1]
            if a < pa:
                out.append(_issue("qc.caption_order", "fail", f"{tag} starts before the cue before it",
                                  "sort the cues", frame=int(a * fps)))
            elif a < pb:
                out.append(_issue("qc.caption_overlap", "fail", f"{tag} overlaps the cue before it by {pb - a:.2f} s",
                                  "end the earlier cue first", frame=int(a * fps)))
            elif a - pb < o["min_gap_frames"] / fps - 1e-6 and a > pb + 1e-6:
                out.append(_issue("qc.caption_gap", "info", f"{tag} follows the last one after {(a - pb) * fps:.1f} "
                                  f"frames", f"leave {o['min_gap_frames']} frames or butt them", frame=int(a * fps)))
        for c in cuts_s:
            if a + 1 / fps < c < b - 1 / fps:
                out.append(_issue("qc.caption_across_cut", "warn", f"{tag} runs across the cut at {c:.2f} s",
                                  "end it at the cut or start it after", frame=int(round(c * fps))))
                break
    if size and cues:
        safe = post_cut.caption_safe_check([[0, 0, t] for _, _, t in cues], size)
        if not safe["pass"]:
            out.append(_issue("qc.caption_safe_area", "fail", safe["why"], "lower captions.max_chars and re-cut",
                              value=safe["metric"], expected=safe["threshold"]))
    return out


def report(facts: dict, loud: dict | None, black: list, frozen: list, edl: dict | None, cues: list | None,
           options: dict | None = None, file: str = "") -> dict:
    """The QC report from measurements (pure). pass: no issue of severity fail."""
    o = {**DEFAULTS, **(options or {})}
    fps = facts.get("fps") or 24.0
    dur = facts.get("frames", 0) / fps if facts.get("frames") else facts.get("duration_s", 0)
    issues = check_streams(facts) + check_duration(facts, edl, fps)
    if loud is not None:
        issues += check_loudness(loud, o)
    issues += check_runs(black, "black", dur, fps, o) + check_runs(frozen, "frozen", dur, fps, o)
    if cues is not None:
        size = (facts["width"], facts["height"]) if "width" in facts else None
        issues += check_captions(cues, dur, fps, o, size, [c / fps for c in (edl or {}).get("cuts", [])])
    metrics = {"file": file, **facts, "loudness": loud, "black_runs": black, "frozen_runs": frozen,
               "edl_frames": (edl or {}).get("frames"), "edl_events": len((edl or {}).get("events", [])),
               "captions": len(cues or []), "options": o}
    return {"pass": not any(i["severity"] == "fail" for i in issues), "issues": issues, "metrics": metrics}


def markdown(rep: dict) -> str:
    """The report as a one-page sheet."""
    m = rep["metrics"]
    loud = m.get("loudness") or {}
    lines = [f"# Delivery QC: {Path(m.get('file') or '').name or 'file'}", "",
             f"**{'PASS' if rep['pass'] else 'FAIL'}**: {sum(i['severity'] == 'fail' for i in rep['issues'])} fail, "
             f"{sum(i['severity'] == 'warn' for i in rep['issues'])} warn, "
             f"{sum(i['severity'] == 'info' for i in rep['issues'])} info", "",
             "| measure | value |", "|---|---|",
             f"| picture | {m.get('width')}x{m.get('height')} {m.get('video_codec')}, {m.get('frames')} frames at "
             f"{m.get('fps', 0):g} fps |",
             f"| sound | {m.get('audio_codec')} {m.get('sample_rate')} Hz, {m.get('audio_s', 0):.3f} s |",
             f"| EDL | {m.get('edl_events')} events, {m.get('edl_frames')} frames |",
             f"| loudness | {loud.get('I')} LUFS, true peak {loud.get('TP')} dBTP, LRA {loud.get('LRA')} LU |",
             f"| black / frozen runs | {len(m.get('black_runs') or [])} / {len(m.get('frozen_runs') or [])} |",
             f"| captions | {m.get('captions')} cues |", ""]
    if rep["issues"]:
        lines += ["| severity | code | frame | issue | fix |", "|---|---|---|---|---|"]
        order = {"fail": 0, "warn": 1, "info": 2}
        for i in sorted(rep["issues"], key=lambda i: (order[i["severity"]], i.get("frame", 0))):
            lines.append(f"| {i['severity']} | `{i['code']}` | {i.get('frame', '')} | {i['message']} | "
                         f"{i.get('fix', '')} |")
    else:
        lines.append("No issues.")
    return "\n".join(lines) + "\n"


def run(path: Path, edl_path: Path | None = None, captions_path: Path | None = None, options: dict | None = None,
        probes: Probes | None = None) -> dict:
    """Measure a delivered file and report on it (the I/O half; `report` is the pure half)."""
    o = {**DEFAULTS, **(options or {})}
    p = probes or Probes()
    facts = stream_facts(p.probe(path))
    fps = o.get("fps") or facts.get("fps") or 24.0
    facts["fps"] = fps
    dur = facts.get("frames", 0) / fps or facts.get("duration_s", 0)
    loud = parse_ebur128(p.ebur128(path)) if facts.get("audio_streams") else None
    black = parse_black(p.blackdetect(path, min(o["max_black_s"], 0.1)))
    frozen = parse_freeze(p.freezedetect(path, o["max_freeze_s"]), dur)
    edl = parse_edl(Path(edl_path).read_text(), fps) if edl_path else None
    cues = parse_captions(Path(captions_path).read_text()) if captions_path else None
    return report(facts, loud, black, frozen, edl, cues, o, str(path))
