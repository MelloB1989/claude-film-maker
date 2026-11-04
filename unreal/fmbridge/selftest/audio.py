"""WP12's acceptance test: every audio op on a scratch sequence, re-run for idempotency, read back with numbers.

Needs: an editor with the bridge (no GPU work, no Epic login, no assets: it writes its own sine-tone WAVs under
Saved/Selftest/audio). Takes about 10 s. Leaves nothing outside /Game/_Selftest/audio and Saved/Selftest/audio.

Run: film-ue selftest audio   (WP11's harness calls run(t); t.check(name, ok, **details), t.scratch)
"""
from __future__ import annotations

import math
import os
import struct
import wave

import unreal

from fmbridge import ops

AREA = "audio"


def _scratch(t) -> str:
    s = getattr(t, "scratch", None)
    s = s() if callable(s) else s
    return str(s or f"/Game/_Selftest/{AREA}").rstrip("/")


def _tone(path: str, seconds: float, hz: float, sr: int = 48000) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = int(seconds * sr)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / sr))) for i in range(n)))
    return path


def run(t):
    root = _scratch(t)
    saved = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Selftest", AREA)
    a = _tone(os.path.join(saved, "tone a.wav"), 2.0, 440)
    b = _tone(os.path.join(saved, "tone-b.wav"), 1.0, 660)

    # audio.import: names sanitised, durations from the files, a re-run imports nothing
    r = ops.call("audio.import", files=[a, b], folder=f"{root}/Sounds")
    paths = [s["path"] for s in r["sounds"]]
    t.check("import.names", paths == [f"{root}/Sounds/tone_a", f"{root}/Sounds/tone_b"], paths=paths)
    t.check("import.durations", [round(s["duration_s"], 2) for s in r["sounds"]] == [2.0, 1.0], sounds=r["sounds"])
    r2 = ops.call("audio.import", files=[a, b], folder=f"{root}/Sounds")
    t.check("import.idempotent", r2["changed"] is False, result=r2)

    # a scratch sequence at 24 fps (WP8's seq.new)
    seq = f"{root}/SQ_Audio"
    ops.call("seq.new", path=seq, start=0, end=96, fps=24, replace=True)

    # audio.place: overlap stacks on row 1, dB volume and offset read back, extend lengthens playback
    clips = [{"sound": paths[0], "start_frame": 0}, {"sound": paths[1], "start_s": 1.0, "volume_db": -6.0},
             {"sound": paths[1], "start_frame": 72, "offset_s": 0.5}]
    p = ops.call("audio.place", sequence=seq, clips=clips, track="VO", extend=True)
    got = sorted((c["start_frame"], c["end_frame"], c["row"]) for c in p["clips"])
    t.check("place.frames_rows", got == [(0, 48, 0), (24, 48, 1), (72, 84, 0)], clips=p["clips"])
    d = ops.call("audio.describe", sequence=seq)
    vo = next((x for x in d["tracks"] if x["name"] == "VO"), {"clips": []})
    by = {c["start_frame"]: c for c in vo["clips"]}
    t.check("describe.fps", d["fps"] == 24, fps=d["fps"])
    t.check("describe.volume_db", abs(by.get(24, {}).get("volume_db", 99) + 6.0) < 0.05, clip=by.get(24))
    t.check("describe.offset_s", abs(by.get(72, {}).get("offset_s", 99) - 0.5) < 0.01, clip=by.get(72))
    t.check("describe.sound", by.get(0, {}).get("sound") == paths[0], clip=by.get(0))
    p2 = ops.call("audio.place", sequence=seq, clips=clips, track="VO")
    t.check("place.idempotent", p2["changed"] is False and len(ops.call("audio.describe", sequence=seq)["tracks"]) == 1,
            result=p2)

    # audio.lines: a timing document at 48 fps lands rescaled on its own track
    doc = {"kind": "timing", "version": 1, "fps": 48,
           "lines": [{"id": "L1", "wav": os.path.basename(a), "start_frame": 0},
                     {"id": "L2", "wav": os.path.basename(b), "start_frame": 144}]}
    ln = ops.call("audio.lines", sequence=seq, timing=doc, wav_root=saved, folder=f"{root}/VO", track="Lines")
    t.check("lines.frames", [(x["id"], x["start_frame"], x["end_frame"]) for x in ln["lines"]] ==
            [("L1", 0, 48), ("L2", 72, 96)], result=ln)
    t.check("lines.idempotent", ops.call("audio.lines", sequence=seq, timing=doc, wav_root=saved,
                                         folder=f"{root}/VO", track="Lines")["changed"] is False)

    # audio.remove: once changes, twice does not
    t.check("remove", ops.call("audio.remove", sequence=seq, track="Lines")["changed"] is True)
    t.check("remove.idempotent", ops.call("audio.remove", sequence=seq, track="Lines")["changed"] is False)
    return {"sequence": seq, "describe": ops.call("audio.describe", sequence=seq)}
