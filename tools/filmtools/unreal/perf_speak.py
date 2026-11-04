"""perf.speak (BACKLOG B29): a face performance from text, in one call. On the client: text -> TTS (ElevenLabs,
filmtools.elevenlabs: a WAV and its word alignment) -> a timing line; then on the box, through existing ops only:
the WAV pushed, `audio.lines` (the voice on the sequence's VO track at its frame), `speech.to_face` (WP4: MetaHuman
Animator's audio solver, a face animation), `perf.face` (WP4: natural head, eyes, blinks and brows composed over
the lip-sync, emphasis from the word alignment; skipped with a note when the bridge has no such op yet) and
`seq.anim` (WP8: the animation on the face at the same frame).

    from filmtools.unreal import perf_speak
    perf_speak.speak("Welcome in.", line_id="L1", sequence="/Game/Seq/SQ_Main", start_frame=48,
                     face={"face_mesh": "/Game/MH/Host/Face", "label": "Host"},
                     voice={"voice_id": "...", "model": "eleven_multilingual_v2"},
                     box_dir="/srv/film/vo", out_dir=Path("out/vo"))

    film-post speak --text "Welcome in." --id L1 --sequence /Game/Seq/SQ_Main --start-frame 48 \\
        --face-mesh /Game/MH/Host/Face --label Host --voice-id <id> --box-dir /srv/film/vo --out-dir out/vo [--dry-run]

The API key is never passed around: ElevenLabs reads $ELEVENLABS_API_KEY, so run it as
`fleetctl secret exec ELEVENLABS_API_KEY=elevenlabs -- uv run film-post speak ...`.

Idempotent: a take whose WAV and JSON exist for the same text and voice is reused (TTS is paid once), the VO clip
is added only if it is not there, and speech.to_face frees its names before exporting. The face section is added
to the face's animation track (`replace_face=True` empties the track first: for a shot with only this line).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from . import audio_timing

DEFAULT_MODEL = "eleven_multilingual_v2"
SR = 48000


def take_key(text: str, voice: dict) -> str:
    """What makes a take the same take: the text and every voice setting."""
    v = {k: voice.get(k) for k in ("voice_id", "model", "speed", "seed", "settings")}
    return hashlib.sha256(json.dumps([text, v], sort_keys=True).encode()).hexdigest()[:16]


def synthesize(text: str, line_id: str, voice: dict, out_dir: Path, tts=None, log=print) -> dict:
    """The take for a line: out_dir/<line_id>.wav (48 kHz mono PCM16) and .json ({"text", "key", "duration_s",
    "words": [{"w", "start", "end"}] seconds}). Reused when the key matches; else made with `tts` (an ElevenLabs
    client; default one reading $ELEVENLABS_API_KEY)."""
    from ..align import words_from_alignment, words_to_dicts
    from ..wav import pcm16_to_float, write_wav
    out_dir = Path(out_dir)
    wav, meta = out_dir / f"{line_id}.wav", out_dir / f"{line_id}.json"
    key = take_key(text, voice)
    if wav.exists() and meta.exists():
        m = json.loads(meta.read_text())
        if m.get("key") == key:
            return {**m, "wav": str(wav), "reused": True}
    if tts is None:
        from ..elevenlabs import ElevenLabs
        tts = ElevenLabs()
    if not voice.get("voice_id"):
        raise ValueError("voice.voice_id: which ElevenLabs voice speaks the line")
    r = tts.tts(voice["voice_id"], text, voice.get("model") or DEFAULT_MODEL, f"pcm_{SR}", speed=voice.get("speed"),
                seed=voice.get("seed"), settings=voice.get("settings") or None)
    x = pcm16_to_float(r.audio)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_wav(wav, x, SR)
    m = {"line": line_id, "text": text, "key": key, "voice_id": voice["voice_id"], "model": voice.get("model"),
         "duration_s": round(len(x) / SR, 4), "cost": r.cost, "request_id": r.request_id,
         "words": words_to_dicts(words_from_alignment(r.alignment))}
    meta.write_text(json.dumps(m, indent=1))
    log(f"{line_id}: {m['duration_s']:.2f} s, {r.cost} credits")
    return {**m, "wav": str(wav), "reused": False}


def emphasis(words: list, fps: float, start_frame: int, offset_s: float = 0.0) -> list:
    """[[t, strength]] for perf.face: per word its onset in seconds into the WAV and a strength 0.3..1 from how long
    it is held against the line's median word (stressed words are drawn out). Pure."""
    if not words:
        return []
    durs = [max(1, w["end_frame"] - w["start_frame"]) for w in words]
    med = sorted(durs)[len(durs) // 2]
    return [[round((w["start_frame"] - start_frame) / fps + offset_s, 3),
             round(min(1.0, max(0.3, 0.6 * d / med)), 2)] for w, d in zip(words, durs)]


def plan(line: dict, *, sequence: str, face: dict, box_dir: str, track: str = "VO", folder: str = "/Game/Audio/VO",
         anim_folder: str = "/Game/Speech", mood: str = "CONFIDENCE", replace_face: bool = False,
         perf_face: bool = True) -> list:
    """The bridge calls for one timing line, in order: [{"op", "args", "why"}]. `face`: {"face_mesh", "label",
    "component"? ("Face"), "mood"?}. The face animation's path is filled in from speech.to_face's result."""
    box_wav = f"{box_dir.rstrip('/')}/{Path(line['wav']).name}"
    mood = line.get("mood") or face.get("mood") or mood
    doc = {"kind": "timing", "version": 1, "fps": line["_fps"],
           "lines": [{k: v for k, v in line.items() if not k.startswith("_")} | {"wav": box_wav}]}
    return [
        {"op": "audio.lines", "args": {"sequence": sequence, "timing": doc, "track": track, "folder": folder,
                                       "replace": False}, "why": "the voice on the VO track at its frame"},
        {"op": "speech.to_face", "args": {"wav": box_wav, "name": line["id"], "face_mesh": face["face_mesh"],
                                          "mood": mood, "folder": anim_folder}, "why": "the face animation from the voice"},
        *([{"op": "perf.face", "args": {"anim": "<speech.to_face anim>", "wav": box_wav, "mood": mood,
                                        "emphasis": emphasis(line.get("words", []), line["_fps"], line["start_frame"],
                                                             line.get("offset_s", 0.0))},
            "why": "head, eyes, blinks and brows over the lip-sync (WP4)", "optional": True}] if perf_face else []),
        {"op": "seq.anim", "args": {"path": sequence, "label": face["label"], "component": face.get("component", "Face"),
                                    "sections": [{"anim": "<face anim>", "start": line["start_frame"]}],
                                    "replace": replace_face}, "why": "the face animation at the line's frame"},
    ]


def speak(text: str, *, line_id: str, sequence: str, start_frame: int, face: dict, voice: dict, box_dir: str,
          out_dir: Path, fps: float | None = None, speaker: str = "", track: str = "VO",
          folder: str = "/Game/Audio/VO", anim_folder: str = "/Game/Speech", mood: str = "CONFIDENCE",
          replace_face: bool = False, perf_face: bool = True, tts=None, op: Callable | None = None, push: Callable | None = None,
          dry_run: bool = False, log=print) -> dict:
    """Text to a speaking face on a sequence (see the module docstring). Returns {"line" (the timing line), "steps"
    ([{"op", "args", "result"}]), "anim", "take"}. dry_run: no TTS and no bridge calls, only the plan (a take already
    on disk is still read for its timing)."""
    if op is None or push is None:
        from . import client
        op, push = op or client.op, push or client.push
    if fps is None:
        fps = 24.0 if dry_run else float(op("audio.describe", sequence=sequence)["result"]["fps"])
    wav = Path(out_dir) / f"{line_id}.wav"
    if dry_run and not wav.exists():
        take = {"wav": str(wav), "duration_s": max(1.0, len(text.split()) * 0.4), "words": [], "reused": False}
    else:
        take = synthesize(text, line_id, voice, Path(out_dir), tts, log)
    doc = audio_timing.from_lines([{"id": line_id, "wav": take["wav"], "start_frame": int(start_frame),
                                    "duration_s": take["duration_s"], "text": text, "speaker": speaker,
                                    "words": take["words"]}], float(fps))
    line = {**doc["lines"][0], "_fps": float(fps)}
    steps = plan(line, sequence=sequence, face=face, box_dir=box_dir, track=track, folder=folder,
                 anim_folder=anim_folder, mood=mood, replace_face=replace_face, perf_face=perf_face)
    line.pop("_fps")
    if dry_run:
        return {"line": line, "steps": steps, "anim": None, "take": take, "dry_run": True}
    push(take["wav"], steps[1]["args"]["wav"])
    anim, notes = None, []
    for st in steps:
        if st["op"] in ("perf.face", "seq.anim"):
            if not anim:
                raise RuntimeError(f"speech.to_face made no animation for {line_id}: "
                                   f"{steps[1].get('result')} (is face_mesh a face skeletal mesh?)")
            if st["op"] == "perf.face":
                st["args"]["anim"] = anim
            else:
                st["args"]["sections"][0]["anim"] = anim
        r = op(st["op"], **st["args"])
        if isinstance(r, dict) and r.get("ok") is False:
            if st.get("optional") and r.get("code") == "not_found":
                notes.append(f"{st['op']} is not on this bridge: the face plays the raw solve")
                st["result"] = None
                log(notes[-1])
                continue
            raise RuntimeError(f"{st['op']} failed: {r.get('message') or r.get('error')} ({r.get('hint', '')})")
        st["result"] = r.get("result", r) if isinstance(r, dict) else r
        if st["op"] == "speech.to_face":
            anim = (st["result"] or {}).get("anim")
        elif st["op"] == "perf.face":
            anim = (st["result"] or {}).get("anim") or anim
        log(f"{st['op']}: ok")
    return {"line": line, "steps": steps, "anim": anim, "take": take, "notes": notes}
