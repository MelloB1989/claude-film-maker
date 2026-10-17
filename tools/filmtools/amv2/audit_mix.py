"""Audit of the v2 mix against the EDL: loudness, voice words vs subtitles, SFX on their frames, a clean end.

    PYTHONPATH=tools python -m filmtools.amv2.audit_mix [--edl ...] [--mix out/timeless/amv2/mix.wav] [--json report.json]

Exit status 1 when a check fails. Reuses the transient and spoken-onset detectors of `filmtools.amv.audit_audio`.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from filmtools.amv import audit_audio as A
from filmtools.amv2 import mix as M

DECLARED = ("hit", "impact_boom", "sub_drop", "glitch_tick", "shutter_flash")
SWISH = ("whip", "web_zip")      # a rising swish: judged on the envelope peak, not the start of its rise


def check(E: dict, mix: np.ndarray, log=print) -> dict:
    fps, N = E["fps"], len(mix)
    rep, fails = {}, []
    # loudness
    L, tp = M.lufs(mix), M.true_peak_db(mix)
    rep["lufs"], rep["true_peak_dbtp"] = round(L, 2), round(tp, 2)
    if abs(L + 14) > 0.3:
        fails.append(f"loudness {L:.2f} LUFS, wanted -14 +-0.3")
    if tp > -1.0:
        fails.append(f"true peak {tp:.2f} dBTP > -1")
    rep["length_samples"] = N
    if N != round(E["dur"] / fps * M.SR):
        fails.append(f"length {N} samples, wanted {round(E['dur'] / fps * M.SR)}")

    # stems of the same build (the isolated voice and SFX buses, for exact placement)
    stems = M.build(E, {k: (v["trim_db"], v["extra_duck_db"]) for k, v in json.loads(
        (Path(sys.argv_mix_dir) / "mix_report.json").read_text()).get("voice_adjust", {}).items()} if hasattr(sys, "argv_mix_dir") else None)

    # voice words: spoken onset (measured on the voice stem and in the final mix) vs the subtitle reveal frame
    rows, reveals = [], {}
    for v in stems["lines"]:
        for w, o in zip(v["words"], M.word_onsets(stems, v)):
            reveals[(v["name"], w["w"], round(v["start"] / M.SR + w["t0"], 3))] = o["frame"] + 1

        refs = [v["start"] / M.SR + w["t0"] for w in v["words"]]
        for label, sig in (("stem", stems["voice"].mean(axis=1)), ("mix", mix.mean(axis=1))):
            ons = A.word_onsets(sig, M.SR, refs)
            for w, ref, o in zip(v["words"], refs, ons):
                if o["t"] is None:
                    continue
                reveal = reveals[(v["name"], w["w"], round(ref, 3))]   # cues.csv: measured stem onset frame + 1
                delta = reveal - A.frame_of(o["t"], fps)       # picture minus sound, frames
                rows.append({"line": v["name"], "word": w["w"], "src": label, "onset_f": round(o["t"] * fps, 2), "reveal_f": reveal,
                             "delta": delta, "conf": round(o["conf"], 1)})
    rep["voice_words"] = rows
    bad = [r for r in rows if r["src"] == "stem" and not (0 <= r["delta"] <= 2)]
    rep["voice_words_bad"] = bad
    if bad:
        fails.append(f"{len(bad)} voice words off the 0-2 frame window (stem)")

    # SFX on their frames: transient of the isolated SFX bus vs the declared frame
    tr = [(t * fps, s) for t, s in A.transients(stems["sfx"].mean(axis=1), M.SR, 3.0)]
    srows = []
    for c in stems["cues"]:
        if "stutter" in c["why"]:
            continue
        if c["name"] in SWISH:
            sig = stems["sfx"].mean(axis=1)
            lo, hi = c["hit_sample"] - int(0.1 * M.SR), c["hit_sample"] + int(0.1 * M.SR)
            env = np.sqrt(np.convolve(sig[lo:hi] ** 2, np.ones(240) / 240, "same"))
            f = (lo + int(np.argmax(env))) / M.SR * fps
            srows.append({"name": c["name"], "f": c["f"], "hit": round(f, 2), "delta": round(f - c["f"], 2)})
            continue
        if c["name"] not in DECLARED:
            continue
        near = [(f, s) for f, s in tr if abs(f - c["f"]) <= 3.0]
        if not near:
            srows.append({"name": c["name"], "f": c["f"], "hit": None})
            continue
        top = max(s for _, s in near)
        f, s = min((x for x in near if x[1] >= 0.5 * top), key=lambda x: abs(x[0] - c["f"]))   # the closest strong one
        srows.append({"name": c["name"], "f": c["f"], "hit": round(f, 2), "delta": round(f - c["f"], 2)})
    rep["sfx"] = srows
    offs = [r for r in srows if r["hit"] is not None and abs(r["delta"]) > 1.0]
    rep["sfx_missing"] = [r for r in srows if r["hit"] is None]
    rep["sfx_off"] = offs
    if offs:
        fails.append(f"{len(offs)} SFX more than 1 frame from their frame")

    # the end: no hard stop, no click, no step
    tail = mix[-int(0.5 * M.SR):].mean(axis=1)
    rms = np.sqrt(np.convolve(tail ** 2, np.ones(48) / 48, "same"))           # 1 ms
    d = np.abs(np.diff(mix[-int(1.5 * M.SR):], axis=0)).max(axis=1)
    step_ratio = float(d[-int(0.1 * M.SR):].max() / (d[:-int(0.1 * M.SR)].max() + 1e-9))   # vs the biggest step of the 1.4 s before
    rep["end"] = {"last_sample": float(np.abs(mix[-1]).max()), "rms_last_10ms_dbfs": round(float(20 * np.log10(rms[-480:].mean() + 1e-12)), 1),
                  "max_step_last_100ms_over_prev_1.4s_max_step": round(step_ratio, 3)}
    if np.abs(mix[-1]).max() > 1e-4:
        fails.append("the file does not end on silence")
    if step_ratio > 1.0:
        fails.append("a step or click in the last 100 ms")
    # clicks anywhere: a sample jump far above what the signal around it does (high-passed)
    import scipy.signal as sg
    hp = sg.sosfilt(sg.butter(4, 8000, "high", fs=M.SR, output="sos"), mix.mean(axis=1))
    env = np.convolve(np.abs(hp), np.ones(2400) / 2400, "same") + 1e-6
    ratio = np.abs(hp) / env
    ck = np.where(ratio > 40)[0]
    rep["click_candidates_f"] = sorted({int(i / M.SR * fps) for i in ck})[:20]
    rep["fails"] = fails
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--edl", default=str(M.ROOT / "films/timeless/amv2/edl.json"))
    ap.add_argument("--mix", default=str(M.ROOT / "out/timeless/amv2/mix.wav"))
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    sys.argv_mix_dir = str(Path(a.mix).parent)
    E = json.loads(Path(a.edl).read_text())
    mix, sr = sf.read(a.mix, dtype="float64", always_2d=True)
    assert sr == M.SR and mix.shape[1] == 2
    rep = check(E, mix)
    s = {k: v for k, v in rep.items() if k not in ("voice_words", "sfx")}
    print(json.dumps(s, indent=1))
    d = [r["delta"] for r in rep["voice_words"] if r["src"] == "stem"]
    print("voice word delta (stem), frames:", d)
    print("voice word delta (mix), frames:", [r["delta"] for r in rep["voice_words"] if r["src"] == "mix"])
    print("sfx deltas:", sorted({r.get("delta") for r in rep["sfx"] if r.get("delta") is not None}))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1))
    return 1 if rep["fails"] else 0


if __name__ == "__main__":
    sys.exit(main())
