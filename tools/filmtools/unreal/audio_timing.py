"""Line timing: where each voice line sits on the picture, in one document every stage reads.

The `audio` timing document (kind "audio", version 1) is the handoff between the voice (filmtools vo/edit, or any
WAVs), Unreal (`audio.lines` puts the lines on a Sequencer track; WP4's performance work drives the faces from it)
and post (`post_cut` mixes the same lines and times the captions on their words):

    {"kind": "audio", "version": 1, "name": "main", "fps": 24,
     "lines": [{"id": "L1", "speaker": "host", "wav": "vo/L1.wav", "start_frame": 48, "end_frame": 97,
                "duration_s": 2.03, "offset_s": 0.0, "volume_db": 0.0, "text": "Hello there.",
                "words": [{"w": "Hello", "start_frame": 49, "end_frame": 60}, ...]}]}

Frames are at `fps` on the sequence's clock (frame 0 = the sequence's first frame). A line's `start_frame` is where
its WAV starts (not its first word: the words say that). `wav` is relative to the document's folder or absolute.

Sources: `from_lines` (a plain list), `from_vo_json` (filmtools' data/vo.json from film-edit, whose takes are in
audio/vo/paced/<id>/<take>.wav) and `from_cues_json` (the reel's cues.json). `performance_handoff` turns a timing
document into the per-line jobs WP4's face performance needs (speech.to_face, then the face animation at the frame).
"""
from __future__ import annotations

import json
import math
import wave
from pathlib import Path

KIND, VERSION = "audio", 1
LINE_KEYS = {"id", "speaker", "wav", "start_frame", "start_s", "end_frame", "duration_s", "offset_s", "volume_db",
             "text", "words", "take", "mood"}


class TimingError(ValueError):
    pass


def wav_seconds(path: Path | str) -> float | None:
    """A WAV's length from its header, None if it is not a readable PCM WAV."""
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (OSError, EOFError, wave.Error):
        return None


def _frame(s: float, fps: float) -> int:
    return int(round(s * fps))


def from_lines(lines: list[dict], fps: float, name: str = "main", root: Path | None = None) -> dict:
    """A timing document from plain lines: {"id", "wav", "start_frame" or "start_s", "speaker"?, "text"?,
    "words"? ([{"w", "start", "end"}] seconds from the WAV's start, or {"w", "start_frame", "end_frame"} on the
    sequence's clock), "duration_s"? (else read from the WAV), "offset_s"?, "volume_db"?, "mood"?}."""
    out = []
    for ln in lines:
        unknown = set(ln) - LINE_KEYS
        if unknown:
            raise TimingError(f"line {ln.get('id')}: unknown key(s) {', '.join(sorted(unknown))} "
                              f"(known: {', '.join(sorted(LINE_KEYS))})")
        for k in ("id", "wav"):
            if not ln.get(k):
                raise TimingError(f"line {ln}: no {k}")
        if "start_frame" in ln:
            start = int(ln["start_frame"])
        elif "start_s" in ln:
            start = _frame(float(ln["start_s"]), fps)
        else:
            raise TimingError(f"line {ln['id']}: no start_frame or start_s")
        offset = float(ln.get("offset_s", 0.0))
        dur = ln.get("duration_s")
        if dur is None:
            p = Path(ln["wav"])
            dur = wav_seconds(p if p.is_absolute() or root is None else root / p)
        if dur is None and ln.get("end_frame") is None:
            raise TimingError(f"line {ln['id']}: no duration_s or end_frame, and {ln['wav']} is not a readable WAV")
        end = int(ln["end_frame"]) if ln.get("end_frame") is not None else start + int(math.ceil((dur - offset) * fps - 1e-6))
        words = []
        for w in ln.get("words") or []:
            if "start_frame" in w:
                words.append({"w": w["w"], "start_frame": int(round(w["start_frame"])),
                              "end_frame": int(round(w["end_frame"]))})
            else:  # seconds from the WAV's start (an offset skips the head of the WAV)
                words.append({"w": w["w"], "start_frame": start + _frame(float(w["start"]) - offset, fps),
                              "end_frame": start + _frame(float(w["end"]) - offset, fps)})
        line = {"id": str(ln["id"]), "speaker": ln.get("speaker", ""), "wav": str(ln["wav"]), "start_frame": start,
                "end_frame": end, "duration_s": round(float(dur if dur is not None else (end - start) / fps), 4),
                "offset_s": offset, "volume_db": float(ln.get("volume_db", 0.0)), "text": ln.get("text", ""),
                "words": words}
        for k in ("take", "mood"):
            if k in ln:
                line[k] = ln[k]
        out.append(line)
    out.sort(key=lambda x: x["start_frame"])
    ids = [x["id"] for x in out]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise TimingError(f"line ids repeat: {', '.join(dup)}")
    return {"kind": KIND, "version": VERSION, "name": name, "fps": fps, "lines": out}


def from_vo_json(vo: dict, fps: float, paced_dir: str = "audio/vo/paced", speaker: str = "", name: str = "main",
                 root: Path | None = None) -> dict:
    """From filmtools' data/vo.json (film-edit): lines at absolute seconds with absolute word times; each line's
    WAV is <paced_dir>/<id>/<take>.wav."""
    lines = []
    for ln in vo["lines"]:
        st = float(ln["start"])
        lines.append({"id": ln["id"], "speaker": speaker, "wav": f"{paced_dir}/{ln['id']}/{ln.get('take', 1)}.wav",
                      "start_frame": _frame(st, fps), "duration_s": round(float(ln["end"]) - st, 4),
                      "text": ln.get("text", ""), "take": ln.get("take", 1),
                      "words": [{"w": w["w"], "start_frame": _frame(float(w["start"]), fps),
                                 "end_frame": _frame(float(w["end"]), fps)} for w in ln.get("words", [])]})
    return from_lines(lines, fps, name, root)


def from_cues_json(cues: dict, name: str = "main", root: Path | None = None) -> dict:
    """From the reel's cues.json ({"fps", "lines": {id: {"who", "text", "wav", "file_frame", "end_frame", "words":
    [{"w", "start", "end"} in frames]}}}). A fractional file_frame is rounded; the words keep their frames."""
    fps = float(cues["fps"])
    lines = [{"id": k, "speaker": v.get("who", ""), "wav": v["wav"], "start_frame": int(round(v["file_frame"])),
              "end_frame": int(math.ceil(v["end_frame"])) if "end_frame" in v else None, "text": v.get("text", ""),
              "words": [{"w": w["w"], "start_frame": w["start"], "end_frame": w["end"]} for w in v.get("words", [])]}
             for k, v in cues["lines"].items()]
    for ln in lines:
        if ln["end_frame"] is None:
            del ln["end_frame"]
    return from_lines(lines, fps, name, root)


def validate(doc: dict) -> list[str]:
    """Problems with a timing document (empty when it is right): kind, fps, line fields, words inside their line."""
    p = []
    if doc.get("kind") != KIND:
        p.append(f"kind is {doc.get('kind')!r}, not {KIND!r}")
    if not doc.get("fps") or float(doc["fps"]) <= 0:
        p.append("fps missing or not positive")
    for ln in doc.get("lines", []):
        if ln.get("end_frame", 0) <= ln.get("start_frame", 0):
            p.append(f"{ln.get('id')}: end_frame {ln.get('end_frame')} is not after start_frame {ln.get('start_frame')}")
        for w in ln.get("words", []):
            if not (ln["start_frame"] - 1 <= w["start_frame"] <= w["end_frame"] <= ln["end_frame"] + 1):
                p.append(f"{ln['id']}: word {w['w']!r} at {w['start_frame']}-{w['end_frame']} is outside the line "
                         f"({ln['start_frame']}-{ln['end_frame']})")
                break
    return p


def overlaps(doc: dict, speaker_only: bool = True) -> list[tuple[str, str]]:
    """Pairs of lines that overlap (by default only lines of the same speaker: one mouth, two lines)."""
    ls, out = doc["lines"], []
    for i, a in enumerate(ls):
        for b in ls[i + 1:]:
            if b["start_frame"] < a["end_frame"] and a["start_frame"] < b["end_frame"]:
                if not speaker_only or a.get("speaker") == b.get("speaker"):
                    out.append((a["id"], b["id"]))
    return out


def rescale(doc: dict, fps: float) -> dict:
    """The document on another frame rate (a 30 fps edit placed in a 24 fps sequence)."""
    k = fps / float(doc["fps"])
    r = lambda f: int(round(f * k))  # noqa: E731
    lines = [{**ln, "start_frame": r(ln["start_frame"]), "end_frame": r(ln["end_frame"]),
              "words": [{**w, "start_frame": r(w["start_frame"]), "end_frame": r(w["end_frame"])} for w in ln["words"]]}
             for ln in doc["lines"]]
    return {**doc, "fps": fps, "lines": lines}


def performance_handoff(doc: dict, faces: dict, mood: str = "CONFIDENCE", wav_root: str = "",
                        anim_folder: str = "/Game/Speech") -> list[dict]:
    """Per line, what WP4 needs to drive a face: {"line", "speaker", "wav" (box path), "speech": speech.to_face's
    args, "place": {"label", "component", "start_frame", "end_frame"}} where the face animation goes. `faces` maps a
    speaker to {"face_mesh", "label" (the actor), "component" (default "Face"), "mood"?}. A line whose speaker has no
    face is left out (an off-screen voice)."""
    out = []
    for ln in doc["lines"]:
        f = faces.get(ln.get("speaker", ""))
        if not f:
            continue
        wav = ln["wav"] if not wav_root or ln["wav"].startswith("/") else f"{wav_root.rstrip('/')}/{ln['wav']}"
        out.append({"line": ln["id"], "speaker": ln.get("speaker", ""), "wav": wav,
                    "speech": {"wav": wav, "name": ln["id"], "face_mesh": f["face_mesh"],
                               "mood": ln.get("mood") or f.get("mood") or mood, "folder": anim_folder},
                    "place": {"label": f["label"], "component": f.get("component", "Face"),
                              "start_frame": ln["start_frame"], "end_frame": ln["end_frame"],
                              "offset_s": ln.get("offset_s", 0.0)}})
    return out


def load(path: Path | str) -> dict:
    doc = json.loads(Path(path).read_text())
    problems = validate(doc)
    if problems:
        raise TimingError(f"{path}: " + "; ".join(problems))
    return doc
