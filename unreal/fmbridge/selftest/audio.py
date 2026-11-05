"""WP12's acceptance test: every audio op on a scratch sequence, re-run for idempotency, read back with numbers.

Needs: an editor with the bridge (no GPU work, no Epic login, no assets: it writes its own sine-tone WAVs into the
report folder). Takes about 10 s. Everything it makes is under t.scratch (/Game/_Selftest/audio), named t.prefix.

Run: film-ue selftest audio
"""
from __future__ import annotations

import math
import struct
import wave

REQUIRES: list = []
AREAS = ["audio"]
NEEDS_LEVEL = False
TIMEOUT = 120


def _tone(path: str, seconds: float, hz: float, sr: int = 48000) -> str:
    n = int(seconds * sr)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / sr))) for i in range(n)))
    return path


def run(t):
    root = t.scratch
    a = _tone(t.path("wav/tone a.wav"), 2.0, 440)
    b = _tone(t.path("wav/tone-b.wav"), 1.0, 660)
    wav_dir = a.rsplit("/", 1)[0]

    # audio.import: names sanitised, durations from the files, a re-run imports nothing
    r = t.call("audio.import", files=[a, b], folder=f"{root}/Sounds")
    paths = [s["path"] for s in r["sounds"]]
    t.check("import.names", paths, [f"{root}/Sounds/tone_a", f"{root}/Sounds/tone_b"])
    t.check("import.durations_s", [s["duration_s"] for s in r["sounds"]], [2.0, 1.0], tol=0.01)
    t.idempotent("import.idempotent", "audio.import", files=[a, b], folder=f"{root}/Sounds")
    t.raises("import.missing_file", "audio.import", code="not_found", files=[f"{wav_dir}/nope.wav"])

    # a scratch sequence at 24 fps (WP8's seq.new)
    seq = f"{root}/{t.prefix}SQ"
    t.call("seq.new", path=seq, start=0, end=96, fps=24, replace=True)

    # audio.place: overlap stacks on row 1, dB volume, offset and fades read back, extend lengthens playback
    clips = [{"sound": paths[0], "start_frame": 0, "fade_in_frames": 6, "fade_out_frames": 12},
             {"sound": paths[1], "start_s": 1.0, "volume_db": -6.0},
             {"sound": paths[1], "start_frame": 72, "offset_s": 0.5}]
    p = t.call("audio.place", sequence=seq, clips=clips, track="VO", extend=True)
    t.check("place.frames_rows", sorted([c["start_frame"], c["end_frame"], c["row"]] for c in p["clips"]),
            [[0, 48, 0], [24, 48, 1], [72, 84, 0]])
    d = t.call("audio.describe", sequence=seq)
    vo = next((x for x in d["tracks"] if x["name"] == "VO"), {"clips": []})
    by = {c["start_frame"]: c for c in vo["clips"]}
    t.check("describe.fps", d["fps"], 24)
    t.check("describe.volume_db", by.get(24, {}).get("volume_db"), -6.0, tol=0.05)
    t.check("describe.offset_s", by.get(72, {}).get("offset_s"), 0.5, tol=0.01)
    t.check("describe.fades", [by.get(0, {}).get("fade_in_frames"), by.get(0, {}).get("fade_out_frames")], [6, 12])
    t.check("describe.sound", by.get(0, {}).get("sound"), paths[0])
    t.idempotent("place.idempotent", "audio.place", sequence=seq, clips=clips, track="VO")
    t.check("place.one_track", len(t.call("audio.describe", sequence=seq)["tracks"]), 1)
    t.raises("place.unknown_sound", "audio.place", code="not_found", sequence=seq,
             clips=[{"sound": f"{root}/Sounds/nope", "start_frame": 0}])

    # audio.lines: a timing document at 48 fps lands rescaled on its own track
    doc = {"kind": "timing", "version": 1, "fps": 48,
           "lines": [{"id": "L1", "wav": "tone a.wav", "start_frame": 0},
                     {"id": "L2", "wav": "tone-b.wav", "start_frame": 144}]}
    ln = t.call("audio.lines", sequence=seq, timing=doc, wav_root=wav_dir, folder=f"{root}/VO", track="Lines")
    t.check("lines.frames", [[x["id"], x["start_frame"], x["end_frame"]] for x in ln["lines"]],
            [["L1", 0, 48], ["L2", 72, 96]])
    t.idempotent("lines.idempotent", "audio.lines", sequence=seq, timing=doc, wav_root=wav_dir,
                 folder=f"{root}/VO", track="Lines")

    # audio.remove: once changes, twice does not
    t.check("remove.changed", t.call("audio.remove", sequence=seq, track="Lines")["changed"], True)
    t.idempotent("remove.idempotent", "audio.remove", sequence=seq, track="Lines")
    return {"sequence": seq, "describe": t.call("audio.describe", sequence=seq)}
