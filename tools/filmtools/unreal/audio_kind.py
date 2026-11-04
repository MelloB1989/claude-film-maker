"""The `audio` spec kind (WP12): a sequence's audio tracks, declared; `film-ue apply` converges them through the
audio ops (audio.place / audio.lines), and a second plan is empty once they match `audio.describe`.

    kind: audio
    version: 1
    name: main-audio
    sequence: /Game/Seq/SQ_Main
    tracks:
      - name: VO                       # the voice from a timing document (filmtools.unreal.audio_timing)
        timing: vo/timing.json         # path (relative to the working directory) or the document inline
        wav_root: /srv/film/vo         # the box folder the timing's relative wav paths are under
        folder: /Game/Audio/VO
      - name: Music
        clips: [{sound: /Game/Audio/Score, start_frame: 0, volume_db: -4}]
    remove_others: false               # true: audio tracks not listed are removed

Planning reads a `timing` file when one is named (the only I/O); everything else is pure.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_NAME_BAD = re.compile(r"[^A-Za-z0-9_]")


def asset_name(s: str) -> str:
    """unreal/fmbridge/ops/audio.py's asset_name, for predicting the SoundWave a line becomes."""
    stem = s.replace("\\", "/").rsplit("/", 1)[-1]
    stem = stem.rsplit(".", 1)[0] if stem.lower().endswith(".wav") else stem
    name = _NAME_BAD.sub("_", stem).strip("_") or "Sound"
    return name if not name[0].isdigit() else f"S_{name}"


def _timing(t) -> dict:
    return t if isinstance(t, dict) else json.loads(Path(t).read_text())


def _want_clips(track: dict, fps: float) -> list:
    """[(sound, start_frame, offset_s, volume_db)] a track should hold."""
    if "timing" in track:
        doc = _timing(track["timing"])
        k = fps / float(doc.get("fps") or fps)
        folder = track.get("folder", "/Game/Audio/VO").rstrip("/")
        return sorted((f"{folder}/{asset_name(ln['id'])}", int(round(ln["start_frame"] * k)),
                       round(float(ln.get("offset_s", 0.0)), 3), round(float(ln.get("volume_db", 0.0)), 1))
                      for ln in doc["lines"])
    out = []
    for c in track.get("clips", []):
        c = c if isinstance(c, dict) else {"sound": c[0], "start_frame": c[1]}
        start = c.get("start_frame")
        if start is None:
            start = round(float(c["start_s"]) * fps)
        out.append((c["sound"].split(".")[0], int(start), round(float(c.get("offset_s", 0.0)), 3),
                    round(float(c.get("volume_db", 0.0)), 1)))
    return sorted(out)


def _have_clips(track: dict) -> list:
    return sorted((c["sound"], int(c["start_frame"]), round(float(c.get("offset_s", 0.0)), 3),
                   round(float(c.get("volume_db", 0.0)), 1)) for c in track.get("clips", []))


def plan(spec: dict, state: dict | None) -> list:
    """Steps to make the sequence's audio tracks match the spec. state: audio.describe's result (None or
    {"missing": True} when the sequence does not exist)."""
    state = state or {}
    if state.get("missing"):
        raise ValueError(f"sequence {spec['sequence']} does not exist: make it first (a sequence spec, or seq.new)")
    fps = float(state.get("fps") or 24)
    have = {t["name"]: t for t in state.get("tracks", [])}
    steps = []
    for tr in spec.get("tracks", []):
        if ("timing" in tr) == ("clips" in tr):
            raise ValueError(f"audio track {tr.get('name')}: give either timing or clips")
        want = _want_clips(tr, fps)
        cur = _have_clips(have.get(tr["name"], {}))
        if want == cur:
            continue
        why = (f"track {tr['name']} is missing" if tr["name"] not in have else
               f"track {tr['name']} holds {len(cur)} clip(s) that differ from the {len(want)} wanted")
        if "timing" in tr:
            args = {"sequence": spec["sequence"], "timing": _timing(tr["timing"]), "track": tr["name"],
                    "folder": tr.get("folder", "/Game/Audio/VO"), "wav_root": tr.get("wav_root", "")}
            steps.append({"op": "audio.lines", "args": args, "why": why})
        else:
            steps.append({"op": "audio.place", "args": {"sequence": spec["sequence"], "track": tr["name"],
                                                        "clips": tr["clips"], "replace": True}, "why": why})
    if spec.get("remove_others"):
        listed = {t["name"] for t in spec.get("tracks", [])}
        for name in sorted(set(have) - listed):
            steps.append({"op": "audio.remove", "args": {"sequence": spec["sequence"], "track": name},
                          "why": f"track {name} is not in the spec (remove_others)"})
    return steps


def describe(ue, spec: dict) -> dict:
    try:
        return ue.audio.describe(sequence=spec["sequence"])
    except Exception as e:  # the bridge's not_found for a missing sequence
        if "not_found" in str(getattr(e, "code", "")) or "no level sequence" in str(e):
            return {"missing": True}
        raise


SPEC_KINDS = [{"name": "audio", "plan": plan, "describe": describe, "order": 65,
               "doc": "A sequence's audio tracks: voice lines from a timing document, or clips at frames."}]

