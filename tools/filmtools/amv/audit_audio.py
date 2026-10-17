"""Audio-sync audit of an AMV: where picture and sound disagree.

    python -m filmtools.amv.audit_audio --film films/timeless [--render draft.mp4] [--json out.json]

Reads the film's `amv/plan.json` and its final mix (`plan.audio`, used as-is, never written). Three checks:

1. Subtitles. Each `sub`-style title reveals its words at `f_in + k`. The voice lines in `plan.voice` are found in
   the mix by cross-correlating their stems (`audio/voice/*.wav`) with it, the spoken onset of every word is
   measured on the stem (spectral flux in the speech band, searched around the aligned time in
   `voice_lines.json`), and compared with the reveal frame. The rule: a word appears 0-2 frames after it is spoken.
2. Hits. The strong transients of the mix (spectral flux over log bands against the previous 40 ms of the same
   band) are matched with the visual events of the plan: cuts (`shots[].a`), `flash_ev` peaks, `black`, `invert`,
   `halftone`, screen/layer title pops, the outro start. A visual event more than 1 frame from its hit, and a big
   hit with no visual event, are findings.
3. Outro. Where the audio goes silent against the last picture frame (`plan.dur - 1`), and any hard cut:
   an abrupt level drop, or sound still running at the end of the file.

With `--render`, the picture side is measured on the video too (mean luma per frame: flash, black and invert
frames as actually rendered, and the container's video/audio durations) instead of being read off the plan.

Frames are comp frames at `plan.fps`; sound at time t belongs to frame floor(t * fps). `delta` is always
picture minus sound, in frames: positive means the picture is late.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import scipy.signal as sg

from .. import wav

# ---------------------------------------------------------------- transient helpers

HOP = 0.001  # s, analysis hop of the transient curve
WIN = 0.006  # s, analysis window
BEFORE = 0.040  # s, the band level a transient is measured against: its own previous 40 ms ...
GUARD = 0.004  # ... ending this long before the analysis window, so the rise itself is not in the baseline
EDGES = np.geomspace(80.0, 12000.0, 13)  # 12 log bands, Hz
FLOOR_DB = 90.0
# The time of a transient is its window's centre: within +-4 ms of the true attack on synthetic bursts (+4 ms) and on
# the 39 hits, impacts and ticks that mix.py places on exact samples in the timeless mix (median -2 ms).
T_BIAS = 0.0
# The speech flux peaks 7.5 ms after the start of a 10 ms ramp (synthetic onsets, 0.3-0.31 s, noise and vowel).
SPEECH_BIAS = -0.0075


def band_db(x: np.ndarray, sr: int, edges=EDGES, hop: float = HOP, win: float = WIN) -> tuple[np.ndarray, np.ndarray]:
    """Short-time level in dB per band: (centre times in s, [bands, steps])."""
    n, h = int(round(win * sr)), int(round(hop * sr))
    f, t, z = sg.stft(np.asarray(x, dtype=np.float64), sr, nperseg=n, noverlap=n - h, nfft=max(1024, 1 << (n - 1).bit_length()),
                      boundary=None, padded=False)
    p = np.abs(z) ** 2
    b = np.stack([p[(f >= lo) & (f < hi)].sum(axis=0) for lo, hi in zip(edges[:-1], edges[1:])])
    db = 10.0 * np.log10(b + 1e-12)
    return t, np.maximum(db, db.max() - FLOOR_DB)  # a band 90 dB under the loudest is silence, not a baseline


def rise_curve(db: np.ndarray, hop: float = HOP, before: float = BEFORE, guard: float = GUARD) -> np.ndarray:
    """Per step: mean over bands of how far the band is above its mean level over the `before` seconds that end
    `guard` seconds earlier (only rises count). The level of a sustained sound cancels, an attack does not."""
    k, g = int(round(before / hop)), int(round(guard / hop))
    c = np.concatenate([np.zeros((db.shape[0], 1)), np.cumsum(db, axis=1)], axis=1)
    m = db.shape[1]
    base = np.full_like(db, np.nan)
    j = np.arange(k + g, m)  # trailing mean of db[j-g-k : j-g]
    base[:, k + g:] = (c[:, j - g] - c[:, j - g - k]) / k
    base[:, :k + g] = db[:, :k + g]  # no baseline yet: no rise
    return np.maximum(db - base, 0.0).mean(axis=0)


def pick_transients(times: np.ndarray, score: np.ndarray, min_score: float = 3.0, min_gap: float = 0.03,
                    t_bias: float = T_BIAS) -> list[tuple[float, float]]:
    """Peaks of `score` at least `min_score` high and `min_gap` seconds apart: [(time s, score)]. The time is the
    peak's own (the window centre) shifted by `t_bias`."""
    step = float(times[1] - times[0]) if len(times) > 1 else HOP
    pk, _ = sg.find_peaks(score, height=min_score, distance=max(1, int(round(min_gap / step))))
    return [(float(times[i]) + t_bias, float(score[i])) for i in pk]


def transients(x: np.ndarray, sr: int, min_score: float = 3.0, min_gap: float = 0.03) -> list[tuple[float, float]]:
    t, db = band_db(x, sr)
    return pick_transients(t, rise_curve(db), min_score, min_gap)


# ---------------------------------------------------------------- voice helpers

SPEECH = np.geomspace(150.0, 5000.0, 21)  # 20 bands
SPEECH_HOP, SPEECH_WIN, SPEECH_LAG = 0.005, 0.025, 0.020


def speech_flux(x: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Spectral flux of speech: mean over 20 bands of the dB rise against 20 ms earlier. (times s, flux)"""
    t, db = band_db(x, sr, SPEECH, SPEECH_HOP, SPEECH_WIN)
    lag = int(round(SPEECH_LAG / SPEECH_HOP))
    d = np.zeros_like(db)
    d[:, lag:] = db[:, lag:] - db[:, :-lag]
    return t, np.maximum(d, 0.0).mean(axis=0)


def word_onsets(x: np.ndarray, sr: int, refs: list[float], before: float = 0.10, after: float = 0.10,
                skip: float = 0.03, gap: float = 0.07, min_rise: float = 8.0) -> list[dict]:
    """The spoken onset of each word, near its aligned start `refs[i]` (s, ascending). Forced alignment is early or
    late by up to ~0.1 s, so the search is wide and the measured onset wins:

    - the strongest spectral-flux peak in [ref - before, ref + after], not before `skip` s (a stem opens with a
      fade-in from its bed) and not within `gap` s of the previous word's onset (its tail would be taken);
    - if the level (speech band) rises by >= `min_rise` dB around that peak, the onset is the 50 % point of the rise
      (within 3 ms of the true start on synthetic 5-30 ms attacks); else, a soft fricative or a word inside
      connected speech, the peak itself.

    Result per word: t (s), conf (the peak's flux: < 4 means no sharp onset, trust it to about +-2 frames),
    edge (True when the level-rise refinement applied)."""
    t, db = band_db(x, sr, SPEECH, SPEECH_HOP, SPEECH_WIN)
    lev = 10.0 * np.log10((10.0 ** (db / 10.0)).sum(axis=0) + 1e-12)
    lag = int(round(SPEECH_LAG / SPEECH_HOP))
    d = np.zeros_like(db)
    d[:, lag:] = db[:, lag:] - db[:, :-lag]
    fl = np.maximum(d, 0.0).mean(axis=0)
    out, prev = [], None
    for ref in refs:
        lo = max(ref - before, skip, 0.0 if prev is None else prev + gap)
        sel = np.where((t >= lo) & (t <= ref + after))[0]
        if not len(sel):
            out.append({"t": None, "conf": 0.0, "edge": False})
            continue
        i = sel[int(np.argmax(fl[sel]))]
        tp = float(t[i])
        a = np.where((t >= tp - 0.06) & (t <= tp))[0]
        b = np.where((t >= tp) & (t <= tp + 0.06))[0]
        low, high = lev[a].min(), lev[b].max()
        on, edge = tp + SPEECH_BIAS, False
        if high - low >= min_rise:
            j = [k for k in a if lev[k] >= low + 0.5 * (high - low)]
            if j:
                on, edge = float(t[j[0]]), True
        out.append({"t": on, "conf": float(fl[i]), "edge": edge})
        prev = on
    return out


def locate(mix: np.ndarray, stem: np.ndarray) -> tuple[int, float]:
    """Where `stem` sits in `mix`: (start sample, normalised correlation 0..1). Both mono, same rate."""
    from scipy.signal import fftconvolve
    c = fftconvolve(mix, stem[::-1], mode="valid")
    e = fftconvolve(mix ** 2, np.ones(len(stem)), mode="valid") * float(np.sum(stem ** 2))
    r = c / (np.sqrt(e) + 1e-12)
    k = int(np.argmax(r))
    return k, float(r[k])


def frame_of(t: float, fps: float) -> int:
    """The frame during which sound at `t` is heard."""
    return int(math.floor(t * fps + 1e-9))


# ---------------------------------------------------------------- the plan's picture and sound events

SUB_TOLERANCE = (0, 2)  # frames after the spoken onset
OFF = 1.0  # frames: a visual event further than this from its hit is a finding
NEAR = 3.0  # frames: the search window for "its hit"
MIN_HIT, STRONG, BIG = 3.0, 5.5, 7.0  # transient scores
DECLARED = ("hit", "whip", "impact_boom", "sub_drop", "glitch_tick", "shutter_flash")  # sfx with a transient on its frame


def norm_word(w: str) -> str:
    return "".join(c for c in w.lower() if c.isalnum())


def group_words(title_words: list[str], line_words: list[str]) -> list[list[int]]:
    """For each title word, the indices of the spoken words it shows: 'SPIDER-MAN.' covers 'Spider-' + 'Man.'."""
    out, j = [], 0
    for tw in title_words:
        want, got, idx = norm_word(tw), "", []
        while j < len(line_words) and len(got) < len(want):
            got += norm_word(line_words[j])
            idx.append(j)
            j += 1
        if got != want:
            raise ValueError(f"title word {tw!r} does not match the spoken words {line_words}")
        out.append(idx)
    return out


def visual_events(raw: dict) -> list[dict]:
    """Every picture event of the plan with a frame, and where to move it: [{f, kind, name, fix}]."""
    ev = []
    for i, s in enumerate(raw["shots"]):
        if s["a"] > 0:
            ev.append({"f": s["a"], "kind": "cut", "name": s["name"], "fix": f"shots[{i}].a"})
    fe = raw.get("flash_ev") or []
    for i, (f, v) in enumerate(fe):
        prev = fe[i - 1][1] if i else 0.0
        nxt = fe[i + 1][1] if i + 1 < len(fe) else 0.0
        if v >= 0.5 and v >= prev and v > nxt:  # the lit frame: the key that is the top of a jump
            ev.append({"f": f, "kind": "flash", "name": f"flash_ev {v:g}", "fix": f"flash_ev keys of the flash at {f}"})
    for key in ("black", "invert", "halftone"):
        for i, f in enumerate(raw.get(key) or []):
            ev.append({"f": f, "kind": key, "name": key, "fix": f"{key}[{i}]"})
    for i, t in enumerate(raw.get("titles") or []):
        if t["style"] != "sub":  # a sub's own words are checked against the voice
            ev.append({"f": t["f_in"], "kind": "title", "name": f"{t['style']} {t['spec'].get('text', '')}".strip(),
                       "fix": f"titles[{i}].f_in"})
    if raw.get("outro"):
        ev.append({"f": raw["outro"]["f"], "kind": "outro", "name": "outro", "fix": "outro.f"})
    ev.sort(key=lambda e: (e["f"], e["kind"]))
    return ev


def nearest(events: list[tuple[float, float]], f: float, window: float) -> list[tuple[float, float]]:
    return sorted((e for e in events if abs(e[0] - f) <= window), key=lambda e: abs(e[0] - f))


def shift_for(delta: float) -> int:
    """Whole frames to move the picture by (negative = earlier) to land on the hit."""
    return -int(round(delta))


# ---------------------------------------------------------------- check 1: subtitles


def read_mono(path: Path) -> tuple[np.ndarray, int]:
    return wav.read_wav(path, mono=True)


def line_onsets(film: Path, raw: dict, mix: np.ndarray, sr: int) -> list[dict]:
    """Every voice line of the plan, found in the mix: its words with the measured spoken onset, in mix seconds."""
    meta = {m["name"]: m for m in json.loads((film / "audio" / "voice" / "voice_lines.json").read_text())}
    out = []
    for v in raw.get("voice") or []:
        name = Path(v["file"]).stem
        stem, ssr = read_mono(film / v["file"])
        assert ssr == sr, "stem and mix sample rates differ"
        k, r = locate(mix, stem)
        line = meta[name]["words"]
        on = word_onsets(stem, sr, [w["t0"] for w in line])
        base = k / sr
        out.append({"name": name, "plan_f": v["f"], "placed": base, "xcorr": r, "words": [
            {"w": w["w"], "ref": base + w["t0"], "t": base + (o["t"] if o["t"] is not None else w["t0"]),
             "conf": o["conf"], "edge": o["edge"]} for w, o in zip(line, on)]})
    return out


def judge(delta: int, weak: bool) -> str:
    """ok: 0-2 frames after the spoken onset. A word with no sharp onset (inside connected speech) is only known to
    about +-1 frame, so one frame outside the rule on either side is 'ok~', not a failure."""
    lo, hi = SUB_TOLERANCE
    if lo <= delta <= hi:
        return "ok"
    if weak and lo - 1 <= delta <= hi + 1:
        return "ok~"
    return "FAIL"


def spoken_row(word: str, reveal: int, group: list[dict], fps: float) -> dict:
    w = group[0]
    sf = frame_of(w["t"], fps)
    weak = w["conf"] < 4.0 and not w["edge"]
    delta = reveal - sf
    st = judge(delta, weak)
    return {"word": word, "spoken_f": sf, "spoken_exact": round(w["t"] * fps, 2), "aligned_f": round(w["ref"] * fps, 2),
            "reveal": reveal, "delta": delta, "status": st, "ok": st != "FAIL", "conf": round(w["conf"], 1),
            "edge": w["edge"], "shift": None if st == "ok" else 1 - delta if st == "FAIL" else None}


def check_subtitles(film: Path, raw: dict, lines: list[dict], fps: float) -> list[dict]:
    rows = []
    for ti, t in enumerate(raw.get("titles") or []):
        if t["style"] != "sub":
            continue
        spec = t["spec"]
        ln = min(lines, key=lambda l: abs(l["plan_f"] - t["f_in"]), default=None)
        if ln is None or abs(ln["plan_f"] - t["f_in"]) > 12:
            rows.append({"title": ti, "text": spec["text"], "error": "no voice line within 12 frames of f_in"})
            continue
        groups = group_words([k_[1] for k_ in spec["words"]], [w["w"] for w in ln["words"]])
        for j, ((rel, word), g) in enumerate(zip(spec["words"], groups)):
            r = spoken_row(word, t["f_in"] + rel, [ln["words"][i] for i in g], fps)
            r.update({"title": ti, "text": spec["text"], "line": ln["name"], "placed_f": round(ln["placed"] * fps, 2),
                      "plan_voice_f": ln["plan_f"], "xcorr": round(ln["xcorr"], 3), "key": f"titles[{ti}].spec.words[{j}][0]",
                      "k": rel})
            r["fix"] = None if r["shift"] is None else f"{r['key']} {rel} -> {rel - r['delta'] + 1}"
            rows.append(r)
    return rows


def check_title_pops(raw: dict, lines: list[dict], fps: float) -> list[dict]:
    """Titles that are not subtitles but pop on a spoken word ('SPIDER-MAN' over the line 'I'm Spider-Man.'):
    informational, the same 0-2 frames rule against the frame the title starts."""
    rows = []
    for ti, t in enumerate(raw.get("titles") or []):
        if t["style"] == "sub":
            continue
        ln = next((l for l in lines if l["plan_f"] - 4 <= t["f_in"] <= l["plan_f"] + 60), None)
        if ln is None:
            continue
        want = norm_word(t["spec"].get("text", ""))
        words = [w["w"] for w in ln["words"]]
        for i in range(len(words)):
            got, j = "", i
            while j < len(words) and len(got) < len(want):
                got += norm_word(words[j])
                j += 1
            if got == want:
                r = spoken_row(t["spec"]["text"], t["f_in"], [ln["words"][i]], fps)
                r.update({"title": ti, "line": ln["name"], "key": f"titles[{ti}].f_in"})
                r["fix"] = None if r["shift"] is None else f"{r['key']} {t['f_in']} -> {t['f_in'] - r['delta'] + 1}"
                rows.append(r)
                break
    return rows


# ---------------------------------------------------------------- check 2: hits


def even_runs(frames: list[float], lo: float = 2.0, hi: float = 6.0, tol: float = 0.3, min_len: int = 5) -> list[list[float]]:
    """Runs of >= min_len transients at one even spacing (`lo`-`hi` frames, within `tol`): the longest first, none
    reused. mix.py's outro sink filters the music in 14 segments with a fresh filter state each, so every segment
    boundary (3.57 f apart) clicks; music does not hit this evenly."""
    fs = sorted(frames)
    runs = []
    for i, a in enumerate(fs):
        for b in fs[i + 1:]:
            g = b - a
            if g > hi:
                break
            if g < lo:
                continue
            run, cur = [a, b], b
            while True:
                nxt = [f for f in fs if abs(f - (cur + g)) <= tol]
                if not nxt:
                    break
                cur = min(nxt, key=lambda f: abs(f - (cur + g)))
                run.append(cur)
            if len(run) >= min_len:
                runs.append(run)
    runs.sort(key=len, reverse=True)
    used, out = set(), []
    for r in runs:
        if not used & set(r):
            out.append(r)
            used |= set(r)
    return sorted(out)


def pick_hit(cands: list[tuple[float, float]], f: float) -> tuple[float, float] | None:
    """Of the transients near frame `f`, the closest among those at least 60 % as strong as the strongest."""
    if not cands:
        return None
    top = max(s for _, s in cands)
    return min((c for c in cands if c[1] >= 0.6 * top), key=lambda c: abs(c[0] - f))


def hard_cuts(x: np.ndarray, sr: int, fps: float) -> list[dict]:
    """Places where the level falls by more than 26 dB within 1 ms from above -60 dBFS: a stop, not a decay."""
    r = rms_ms(x, sr)
    hc = []
    for i in range(1, len(r)):
        if r[i - 1] > 1e-3 and r[i] < 0.05 * r[i - 1]:
            t = i / 1000.0
            if not hc or t - hc[-1]["t"] > 0.02:
                hc.append({"t": t, "frame": round(t * fps, 2), "from_dbfs": round(20 * math.log10(r[i - 1]), 1)})
    return hc


def check_hits(raw: dict, mix: np.ndarray, sr: int, speech: list[float] = (), vis: dict[int, int] | None = None) -> dict:
    """`speech` is the frames of the spoken word onsets (their flux is speech, not a hit). `vis` maps a plan event frame to the frame the render actually shows it (--render), else the plan frame."""
    fps = raw["fps"]
    vis = vis or {}
    tr = [(t * fps, s) for t, s in transients(mix, sr, MIN_HIT)]
    is_speech = lambda f: any(abs(f - w) <= 2.0 for w in speech)  # noqa: E731
    o0 = (raw.get("outro") or {}).get("f", raw["dur"])  # the sink window
    trains = even_runs([f for f, s in tr if s >= 4.0 and f >= o0 and not is_speech(f)])
    train_f = {round(f, 3) for t in trains for f in t}
    stops = [h["frame"] for h in hard_cuts(mix, sr, fps)]
    events = visual_events(raw)
    declared = [e["f"] for e in raw.get("sfx") or [] if e["name"] in DECLARED]

    # the mix against the plan's own sfx: does each declared hit sit on its frame?
    sfx_rows = []
    for e in raw.get("sfx") or []:
        if e["name"] in DECLARED:
            h = pick_hit(nearest(tr, e["f"], NEAR), e["f"])
            sfx_rows.append({"name": e["name"], "f": e["f"], "hit": None if h is None else round(h[0], 2),
                             "delta": None if h is None else round(h[0] - e["f"], 2),
                             "score": None if h is None else round(h[1], 1)})

    ev_rows = []
    for e in events:
        pf = vis.get(e["f"], e["f"])
        expected = any(abs(e["f"] - d) <= OFF for d in declared)  # an sfx hit is meant to be here: a weak one counts
        c = [h for h in nearest(tr, pf, NEAR) if h[1] >= (STRONG if e["kind"] == "cut" and not expected else MIN_HIT)
             and not is_speech(h[0])]
        h = pick_hit(c, pf)
        if h:
            d = pf - h[0]
            row = {**e, "picture_f": pf, "hit": round(h[0], 2), "score": round(h[1], 1), "delta": round(d, 2),
                   "ok": abs(d) <= OFF, "src": "sfx" if any(abs(h[0] - f) <= OFF + 0.5 for f in declared) else "music"}
            if not row["ok"]:
                row["shift"] = shift_for(d)
        else:
            row = {**e, "picture_f": pf, "hit": None, "ok": None}
        ev_rows.append(row)

    # big hits with no picture event
    pics = [vis.get(e["f"], e["f"]) for e in events] + [r["f"] for r in raw.get("accents") or []]
    pics += [p["f0"] for p in raw.get("portals") or []]
    orphans = []
    for f, s in tr:
        if s < BIG or is_speech(f) or round(f, 3) in train_f or any(abs(f - x) <= OFF for x in stops):
            continue
        if any(abs(f - p) <= OFF + 0.5 for p in pics):
            continue
        ne = min(events, key=lambda e: abs(e["f"] - f))
        orphans.append({"hit": round(f, 2), "frame": frame_of(f / fps, fps), "score": round(s, 1),
                        "src": "sfx" if any(abs(f - d) <= OFF + 0.5 for d in declared) else "music",
                        "near": f"{ne['name']} @{ne['f']}"})
    return {"transients": len(tr), "sfx": sfx_rows, "events": ev_rows, "orphans": orphans,
            "click_trains": [{"frames": [round(f, 2) for f in t], "gap": round(t[1] - t[0], 2)} for t in trains]}


# ---------------------------------------------------------------- check 3: outro


def rms_ms(x: np.ndarray, sr: int, ms: float = 1.0) -> np.ndarray:
    n = int(sr * ms / 1000)
    m = len(x) // n
    return np.sqrt((x[:m * n].reshape(m, n) ** 2).mean(axis=1))


def check_outro(raw: dict, mix: np.ndarray, sr: int, picture_black: int | None = None,
                picture_flash: int | None = None) -> dict:
    fps, dur = raw["fps"], raw["dur"]
    nz = np.nonzero(np.abs(mix) > 1e-4)[0]  # -80 dBFS
    first = float(nz[0] / sr) if len(nz) else None
    last_t = float((nz[-1] + 1) / sr) if len(nz) else None
    tail = [round(20 * math.log10(float(np.sqrt((mix[int(f * sr / fps):int((f + 1) * sr / fps)] ** 2).mean())) + 1e-9), 1)
            for f in range(dur - 6, dur)]
    sflash = [e["f"] for e in (raw.get("sfx") or []) if e["name"] == "shutter_flash" and e["f"] >= dur - 40]
    hit = None
    if sflash:
        h = pick_hit(nearest([(t * fps, s) for t, s in transients(mix, sr, MIN_HIT)], sflash[-1], NEAR), sflash[-1])
        hit = None if h is None else round(h[0], 2)
    return {"audio_s": len(mix) / sr, "picture_s": dur / fps,
            "first_audible_f": None if first is None else round(first * fps, 2),
            "last_audible_f": None if last_t is None else round(last_t * fps, 2), "last_picture_f": dur - 1,
            "silent_tail_frames": None if last_t is None else round(dur - last_t * fps, 2),
            "hard_cuts": hard_cuts(mix, sr, fps), "tail_rms_db_last6": tail, "sfx_flash": sflash, "sfx_flash_hit": hit,
            "picture_black_from": picture_black, "picture_flash": picture_flash}


# ---------------------------------------------------------------- the render (--render)


def read_render(path: Path) -> dict:
    """Mean luma and frame-to-frame change per video frame, the audio track at 48 kHz mono, and the durations."""
    import av
    c = av.open(str(path))
    vs, au = c.streams.video[0], (c.streams.audio[0] if c.streams.audio else None)
    lum, diff, prev = [], [], None
    for fr in c.decode(vs):
        g = fr.to_ndarray(format="gray")[::2, ::2].astype(np.float32)
        lum.append(float(g.mean()))
        diff.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
    out = {"luma": np.array(lum), "diff": np.array(diff), "fps": float(vs.average_rate),
           "video_s": len(lum) / float(vs.average_rate), "audio": None}
    if au is not None:
        c2 = av.open(str(path))
        rs = av.AudioResampler(format="fltp", layout="mono", rate=48000)
        out["audio"] = np.concatenate([g.to_ndarray()[0] for fr in c2.decode(audio=0) for g in rs.resample(fr)])
    return out


def picture_frames(raw: dict, luma: np.ndarray, diff: np.ndarray) -> dict[int, int]:
    """Plan event frame -> the frame the render shows it: the biggest luma jump (flash, invert), the darkest frame
    (black) or the biggest change from the previous frame (cut), within 3 frames of the plan."""
    out = {}
    med = np.array([np.median(luma[max(0, i - 4):i + 5]) for i in range(len(luma))])
    jump = luma - med
    for e in visual_events(raw):
        a, b = max(0, e["f"] - 3), min(len(luma), e["f"] + 4)
        if e["kind"] in ("flash", "invert") and jump[a:b].max() > 25:
            out[e["f"]] = a + int(np.argmax(jump[a:b]))
        elif e["kind"] == "black" and luma[a:b].min() < 30:
            out[e["f"]] = a + int(np.argmin(luma[a:b]))
        elif e["kind"] == "cut" and diff[a:b].max() > 3 * np.median(diff):  # a spike: a dissolve has none
            out[e["f"]] = a + int(np.argmax(diff[a:b]))
    return out


def render_audio_offset(render_audio: np.ndarray, mix: np.ndarray, sr: int) -> float:
    """Samples the render's audio lags the mix by, measured on its middle 10 s (0 = sample aligned)."""
    from scipy.signal import fftconvolve
    a0, a1 = len(mix) // 3, len(mix) // 3 + 10 * sr
    seg = mix[a0:a1]
    c = fftconvolve(render_audio, seg[::-1], mode="full")
    return float(int(np.argmax(c)) - (len(seg) - 1) - a0)


# ---------------------------------------------------------------- report


def verdict(ok) -> str:
    return {True: "ok", False: "FAIL", None: "-"}[ok]


def print_report(rep: dict) -> None:
    p = print
    p("== 1. subtitles (rule: a word appears 0-2 frames after it is spoken; delta = reveal - spoken frame) ==")
    p(f"{'title':<27}{'word':<13}{'spoken f':>9}{'exact':>8}{'aligned':>9}{'reveal':>8}{'delta':>7}{'conf':>6}  verdict / fix")
    for r in rep["subtitles"] + rep["title_pops"]:
        if "error" in r:
            p(f"{r['text']:<27}ERROR {r['error']}")
            continue
        label = r.get("text", r["word"])[:25] + ("" if "text" in r else " (pop)")
        p(f"{label:<27}{r['word'][:12]:<13}{r['spoken_f']:>9}{r['spoken_exact']:>8.1f}{r['aligned_f']:>9.1f}"
          f"{r['reveal']:>8}{r['delta']:>+7}{r['conf']:>6.1f}  {r['status']}{'' if r['fix'] is None else '  ' + r['fix']}")
    p("  conf < 4 and no level edge: no sharp onset (inside connected speech), good to about +-1 frame (ok~).")
    h = rep["hits"]
    p(f"\n== 2. hits: {h['transients']} transients (score >= {MIN_HIT:g}); delta = picture frame - hit frame ==")
    ds = [s["delta"] for s in h["sfx"] if s["delta"] is not None]
    bad = [s for s in h["sfx"] if s["delta"] is None or abs(s["delta"]) > OFF]
    p(f"declared sfx against the mix: {len(h['sfx'])} declared, {len(ds)} found within {NEAR:g} f, median delta "
      f"{np.median(ds) if ds else float('nan'):+.2f} f, {len(bad)} missing or > {OFF:g} f off")
    for s in bad:
        p(f"  {s['name']:<14} plan f{s['f']:<5} hit {s['hit']}  delta {s['delta']}")
    p("picture events against their hits")
    p(f"  {'frame':>6} {'picture':>8} {'kind':<9}{'event':<28}{'hit f':>8}{'score':>7}{'delta':>7} {'src':<6} verdict / fix")
    for r in h["events"]:
        if r["ok"] is None and r["kind"] == "cut":
            continue  # a cut with no hit is a soft cut (whoosh only): nothing to compare
        got = r["hit"] is not None
        fix = f"  move {r['fix']} by {r['shift']:+d}" if r.get("shift") else ""
        p(f"  {r['f']:>6} {r['picture_f']:>8} {r['kind']:<9}{r['name'][:26]:<28}{r['hit'] if got else '':>8}"
          f"{r['score'] if got else '':>7}{(format(r['delta'], '+.2f') if got else ''):>7} {r.get('src', ''):<6} "
          f"{verdict(r['ok']) if got else 'no hit in window'}{fix}")
    p(f"  (cuts with no hit in window: {sum(1 for r in h['events'] if r['kind'] == 'cut' and r['ok'] is None)}"
      " - soft cuts, not listed)")
    p(f"big hits (score >= {BIG:g}, not speech, click trains or hard stops) with no picture event within {OFF + .5:g} f")
    for o in h["orphans"]:
        p(f"  f{o['hit']:<8} (frame {o['frame']}) score {o['score']:<5} {o['src']:<6} nearest event: {o['near']}")
    if not h["orphans"]:
        p("  none")
    for t in h["click_trains"]:
        p(f"click train, even {t['gap']} f spacing (not music): {', '.join(str(f) for f in t['frames'])}")
    o = rep["outro"]
    p("\n== 3. outro ==")
    p(f"  audio {o['audio_s']:.3f} s, picture {o['picture_s']:.3f} s; first audible f{o['first_audible_f']}, "
      f"last audible f{o['last_audible_f']} (last picture frame f{o['last_picture_f']}): "
      f"{o['silent_tail_frames']} frames of silence at the end")
    p(f"  level of the last 6 frames (dBFS rms): {o['tail_rms_db_last6']}")
    for hc in o["hard_cuts"]:
        p(f"  hard cut at f{hc['frame']} ({hc['t']:.3f} s): {hc['from_dbfs']} dBFS to silence within 1 ms")
    p(f"  shutter_flash sfx at {o['sfx_flash']}, its hit in the mix at {o['sfx_flash_hit']}")
    if o["picture_black_from"] is not None:
        p(f"  render: last flash f{o['picture_flash']}, black from f{o['picture_black_from']} to the end")
    if rep.get("render"):
        r = rep["render"]
        p(f"\n== render ==\n  video {r['video_s']:.3f} s, audio {r['audio_s']} s, audio lag vs mix {r['audio_lag_samples']} samples")
        if r["moved"]:
            p(f"  picture events the render shows off their plan frame (plan -> render): {r['moved']}")


def findings(rep: dict) -> list[dict]:
    """The table of problems: frame, what, delta, fix."""
    out = []
    for r in rep["subtitles"] + rep["title_pops"]:
        if "error" in r:
            out.append({"frame": None, "what": r["error"], "delta": None, "fix": None})
        elif r["status"] == "FAIL":
            out.append({"frame": r["reveal"], "what": f"subtitle {r['word']} ({r['key']})", "delta": r["delta"],
                        "fix": r["fix"]})
    h = rep["hits"]
    for s in h["sfx"]:
        if s["delta"] is None or abs(s["delta"]) > OFF:
            out.append({"frame": s["f"], "what": f"sfx {s['name']} not on its frame in the mix", "delta": s["delta"],
                        "fix": "the mix is stale against plan.json: re-run mix.py"})
    for r in h["events"]:
        if r["ok"] is False:
            out.append({"frame": r["f"], "what": f"{r['kind']} {r['name']} ({r['src']} hit)", "delta": r["delta"],
                        "fix": f"{r['fix']} {r['shift']:+d}"})
    covered = rep["outro"]["sfx_flash_hit"] if rep["outro"]["picture_flash"] is not None else None
    for o in h["orphans"]:
        if covered is not None and abs(o["hit"] - covered) < 0.5:
            continue  # the outro flash finding below says it
        out.append({"frame": o["frame"], "what": f"big {o['src']} hit (score {o['score']}) with no picture event",
                    "delta": None, "fix": f"picture accent at f{round(o['hit'])}, or accept"})
    o = rep["outro"]
    for hc in o["hard_cuts"]:
        out.append({"frame": round(hc["frame"]), "what": f"audio hard cut ({hc['from_dbfs']} dBFS to silence in 1 ms), "
                    f"{o['silent_tail_frames']} silent frames before the end", "delta": None,
                    "fix": "mix side only (mix.py: `fade[s2:] = 0` steps from gain 0.1; end the ramp at 0 or taper the last 80 ms)"})
    if o["first_audible_f"] is not None and o["first_audible_f"] >= 2:
        out.append({"frame": 0, "what": f"info: the mix is silent until f{o['first_audible_f']} (the voice 'Who' bed), the picture runs",
                    "delta": None, "fix": "none if a silent cold open is intended"})
    if o["picture_flash"] is not None and o["sfx_flash_hit"] is not None:
        d = round(o["picture_flash"] - o["sfx_flash_hit"], 2)
        if abs(d) > OFF:
            out.append({"frame": o["picture_flash"], "what": "outro flash: picture flash vs shutter_flash sfx", "delta": d,
                        "fix": f"outro sequence: flash {shift_for(d):+d} f earlier (retime the outro, not plan.json)"})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--film", required=True, type=Path, help="film directory, e.g. films/timeless")
    ap.add_argument("--render", type=Path, help="a render of the film: measure the picture on it")
    ap.add_argument("--json", type=Path, help="write the full report here")
    a = ap.parse_args(argv)
    from . import plan as planmod
    raw = planmod.load(a.film).raw
    fps = raw["fps"]
    mix, sr = wav.read_wav(a.film / raw["audio"], mono=True)
    vis, black_from, flash_f, render = None, None, None, None
    if a.render:
        rd = read_render(a.render)
        vis = picture_frames(raw, rd["luma"], rd["diff"])
        tail = [i for i, v in enumerate(rd["luma"]) if v < 2.0 and i >= raw["dur"] - 40]
        black_from = min(tail) if tail else None
        lm = rd["luma"]
        jumps = [i for i in range(max(1, len(lm) - 40), len(lm)) if lm[i] > 1.5 * lm[i - 1] + 25]
        flash_f = jumps[0] if jumps else None
        render = {"video_s": rd["video_s"], "audio_s": None if rd["audio"] is None else round(len(rd["audio"]) / 48000, 3),
                  "audio_lag_samples": None if rd["audio"] is None else render_audio_offset(rd["audio"], mix, sr),
                  "moved": {k: v for k, v in vis.items() if k != v}}
    lines = line_onsets(a.film, raw, mix, sr)
    speech = [w["t"] * fps for ln in lines for w in ln["words"]] + [ln["placed"] * fps for ln in lines]
    rep = {"film": str(a.film), "fps": fps, "dur": raw["dur"], "render": render,
           "subtitles": check_subtitles(a.film, raw, lines, fps), "title_pops": check_title_pops(raw, lines, fps),
           "hits": check_hits(raw, mix, sr, speech, vis), "outro": check_outro(raw, mix, sr, black_from, flash_f)}
    print_report(rep)
    fl = findings(rep)
    print(f"\n== findings: {len(fl)} ==")
    for f in fl:
        print(f"  f{f['frame']}: {f['what']}  delta {f['delta']}  fix: {f['fix']}")
    if a.json:
        a.json.write_text(json.dumps(rep, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
