"""The explainers' sound effects (round 7): a small library for the graphics' cue vocabulary (docs/STYLE_V3.md section 8,
agent-12), and each film's hit list (films/explain-<film>/data/sfx_v3.json: [{shot, f, sfx, gain, note}], f on the
graphic shot's clock) laid on the film's timeline as a stem the mix reads (mix.py --sfx).

    PYTHONPATH=tools python films/host-studio/explainers/sfx.py lib [--takes 2]     # spends credits (cached)
    PYTHONPATH=tools python films/host-studio/explainers/sfx.py pick                # print the takes, pick in PICKS
    PYTHONPATH=tools python films/host-studio/explainers/sfx.py place --film netflix [--hits PATH]
        # -> audio/<film>/stem-sfx.wav (+ sfx.json): every hit at its frame, at VO-relative level

Levels: each take is normalised to SFX_REF_DB (RMS over its active part, the scale vo.py matches speech to); a hit's
`gain` (pops -18, whooshes -14, hits -10, loops -24) is then relative to the voice, and mix.py scales the stem with the
voice so the ratio holds through the master. Loops (`data_stream`) run f..f_end and are ducked under the voice in the
mix. Successive pops in one shot within 12 frames step up a semitone each (the stagger), at most +5.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from filmtools.wav import SR, pcm16_to_float, read_wav, write_wav  # noqa: E402

FPS = 24
LIB = ROOT / "out" / "host-studio" / "explainers" / "sfx"
SFX_REF_DB = -20.0
STYLE = "clean, modern, premium tech explainer motion graphics sound design, no music, no voice"

# cue: (prompt, seconds, loop, align): align is where the hit time sits in the take: its peak, its onset, or its end
CUES = {
    "whoosh_in": ("an airy soft whoosh that swells and settles, a camera gliding in", 0.7, False, "peak"),
    "swoosh_fast": ("a short fast whip swish", 0.5, False, "peak"),
    "hit_sub": ("a deep sub bass boom impact with a crisp transient and a short clean tail", 1.6, False, "onset"),
    "pop": ("a tight soft click pop, a small interface element appearing", 0.5, False, "onset"),
    "tick": ("a single soft interface tick, a very short clean click", 0.5, False, "onset"),
    "data_stream": ("a gentle granular digital shimmer, soft sparkling data flowing, even texture", 4.0, True, "onset"),
    "riser": ("a short airy tonal riser building up into a reveal", 1.2, False, "peak"),
    "glitch": ("a short digital glitch stutter, a video buffering artefact", 0.6, False, "onset"),
    "chime": ("a soft bright single notification chime ping, pleasant", 1.0, False, "onset"),
}
# cue -> take, picked by measurement (07 Nov, `pick` + spectral centroid): the warmer take where one is very bright;
# whoosh 1 settles at 0.26 s; hit_sub 1 is the sub (centroid 0.8 kHz); pop 1 and tick 1 the tightest; glitch 1 stutters
# around its middle. A listen may override.
PICKS: dict[str, int] = {"whoosh_in": 1, "swoosh_fast": 1, "hit_sub": 1, "pop": 1, "tick": 1, "data_stream": 2,
                         "riser": 1, "glitch": 1, "chime": 2}


def take_path(cue: str, k: int) -> Path:
    prompt, secs, loop, _ = CUES[cue]
    h = hashlib.sha1(json.dumps([prompt, STYLE, secs, loop, k]).encode()).hexdigest()[:10]
    return LIB / cue / f"{k}-{h}.wav"


def active_rms_db(x: np.ndarray) -> float:
    hop = SR // 100
    m = max(1, len(x) // hop)
    e = np.mean(x[:m * hop].reshape(m, hop) ** 2, axis=1) + 1e-12
    db = 10 * np.log10(e)
    return float(10 * np.log10(np.mean(e[db > db.max() - 20])))


def clean(x: np.ndarray, loop: bool) -> np.ndarray:
    """Leading silence trimmed (to 2 ms before -40 dB of the peak), a 30 ms tail fade, normalised to SFX_REF_DB."""
    if not loop:
        thr = np.max(np.abs(x)) * 10 ** (-40 / 20)
        i = int(np.argmax(np.abs(x) > thr))
        x = x[max(0, i - SR // 500):]
        last = len(x) - int(np.argmax(np.abs(x[::-1]) > thr))
        x = x[:min(len(x), last + SR // 50)].copy()
        f = min(len(x) // 4, int(0.03 * SR))
        x[-f:] *= np.linspace(1, 0, f)
    return (x * 10 ** ((SFX_REF_DB - active_rms_db(x)) / 20)).astype(np.float32)


def lib(takes: int) -> None:
    from filmtools.elevenlabs import ElevenLabs
    client = ElevenLabs(credit_log=LIB / "credits.jsonl")
    for cue, (prompt, secs, loop, _) in CUES.items():
        for k in range(1, takes + 1):
            p = take_path(cue, k)
            if p.exists():
                continue
            r = client.sound(f"{prompt}. {STYLE}", duration_seconds=secs, prompt_influence=0.6, loop=loop,
                             seed=7100 + k)
            x = pcm16_to_float(r.audio)
            write_wav(p, clean(x, loop), SR)
            p.with_suffix(".json").write_text(json.dumps({"cue": cue, "take": k, "prompt": prompt, "seconds": secs,
                                                          "loop": loop, "cost": r.cost, "request_id": r.request_id,
                                                          "len_s": round(len(x) / SR, 3)}, indent=1))
            print(f"{cue} {k}: {len(x) / SR:.2f}s, {r.cost} credits")


def sample(cue: str) -> np.ndarray:
    x, sr = read_wav(take_path(cue, PICKS.get(cue, 1)))
    assert sr == SR
    return x


def hit_offset(cue: str, x: np.ndarray) -> int:
    """Samples from the take's start to its hit point."""
    align = CUES[cue][3]
    if align == "peak":
        return int(np.argmax(np.abs(x)))
    if align == "end":
        return len(x)
    return 0


def pitch(x: np.ndarray, semis: float) -> np.ndarray:
    r = 2 ** (semis / 12)
    n = int(len(x) / r)
    return np.interp(np.arange(n) * r, np.arange(len(x)), x).astype(np.float32)


def place(film: str, hits_path: Path | None) -> dict:
    cues = json.loads((HERE / "audio" / film / "cues.json").read_text())
    edl = json.loads((HERE / "edl" / f"{film}.json").read_text())
    hits_path = hits_path or ROOT / "films" / f"explain-{film}" / "data" / "sfx_v3.json"
    hits = json.loads(hits_path.read_text())
    n = int(round(cues["duration"] * SR))
    hit_bus, loop_bus = np.zeros(n, np.float32), np.zeros(n, np.float32)
    starts = {s["gfx"]: s["f0"] for s in edl["shots"] if s.get("gfx")}
    lens = {s["gfx"]: s["frames"] for s in edl["shots"] if s.get("gfx")}
    placed, skipped, last_pop = [], [], {}
    for h in sorted(hits, key=lambda h: (h["shot"], h["f"])):
        if h["shot"] not in starts or h["sfx"] not in CUES:
            skipped.append({**h, "why": "unknown shot" if h["shot"] not in starts else "unknown cue"})
            continue
        if h["f"] >= lens[h["shot"]]:
            skipped.append({**h, "why": f"f {h['f']} past the shot's {lens[h['shot']]} frames (its tail is cut)"})
            continue
        x = sample(h["sfx"])
        semis = 0
        if h["sfx"] == "pop":
            prev = last_pop.get(h["shot"])
            semis = min(5, prev[1] + 1) if prev and h["f"] - prev[0] <= 12 else 0
            last_pop[h["shot"]] = (h["f"], semis)
            x = pitch(x, semis) if semis else x
        g = 10 ** (float(h.get("gain", -18)) / 20)
        t = (starts[h["shot"]] + h["f"]) / FPS
        s0 = int(round(t * SR)) - hit_offset(h["sfx"], x)
        if CUES[h["sfx"]][2]:  # a loop: tiled from f to f_end (on the same shot clock), 50 ms fades
            f_end = min(h.get("f_end", h["f"] + 48), lens[h["shot"]])
            m = int(round((f_end - h["f"]) / FPS * SR))
            y = np.tile(x, m // len(x) + 1)[:m].copy()
            fd = min(m // 4, SR // 20)
            y[:fd] *= np.linspace(0, 1, fd)
            y[-fd:] *= np.linspace(1, 0, fd)
            bus = loop_bus
        else:
            y, bus = x, hit_bus
        a, b = max(0, s0), min(n, s0 + len(y))
        if b > a:
            bus[a:b] += y[a - s0:b - s0] * g
        placed.append({**h, "t": round(t, 3), "semis": semis})
    d = HERE / "audio" / film
    write_wav(d / "stem-sfx-hits.wav", hit_bus, SR)
    write_wav(d / "stem-sfx-loops.wav", loop_bus, SR)
    rep = {"film": film, "hits": str(hits_path.relative_to(ROOT)) if hits_path.is_relative_to(ROOT) else str(hits_path),
           "sha1": hashlib.sha1(hits_path.read_bytes()).hexdigest()[:12], "placed": len(placed), "skipped": skipped,
           "picks": {c: PICKS.get(c, 1) for c in CUES}, "ref_db": SFX_REF_DB}
    (d / "sfx.json").write_text(json.dumps(rep, indent=1))
    print(f"{film}: {len(placed)} hits placed, {len(skipped)} skipped" + "".join(f"\n  skip {s}" for s in skipped))
    return rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["lib", "pick", "place"])
    ap.add_argument("--film", choices=["whatsapp", "netflix"])
    ap.add_argument("--takes", type=int, default=2)
    ap.add_argument("--hits", type=Path)
    a = ap.parse_args()
    if a.cmd == "lib":
        lib(a.takes)
    elif a.cmd == "pick":
        for cue in CUES:
            for p in sorted((LIB / cue).glob("*.wav")):
                x, _ = read_wav(p)
                print(f"{cue:12} {p.name}: {len(x) / SR:.2f}s, peak {20 * np.log10(np.max(np.abs(x)) + 1e-9):.1f} dBFS")
    else:
        place(a.film, a.hits)


if __name__ == "__main__":
    main()
