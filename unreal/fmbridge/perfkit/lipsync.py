"""Lip-sync, measured: does a face's mouth move WITH its voice, and only then? Standard library only (the editor's
Python has no numpy), so the same code runs in the editor (ops/lipsync.py), offline (film-ue lipsync, tests) and on
curves pulled from a box.

The round-5 failure it exists for: his mouth opened wide ~0.7 s before his line and did not follow the words, and
every gate passed, because they measured how MUCH the jaw moved on the line, never WHEN. Here, per line:

- lag: the cross-correlation of the voice's syllable rhythm (its loudness, band-passed to the 1-8 Hz syllable band)
  with the mouth's opening (jaw + lips, the same band), searched over +-1 s. lag < 0: the mouth is EARLY.
- corr: the Pearson correlation at that lag. A face that does not track the words has a low one wherever it peaks.
- onset_lead: how long before the voice's first sound the mouth starts to open (mouths do open a little ahead of
  the sound; Chandrasekaran et al. 2009 measure 100-300 ms at phrase onsets, so the allowance is 0.25 s).
- silence: how far the mouth opens, and how busy it is, where nobody speaks (VAD), outside a short anticipation
  and release around each line: a breath or a smile is allowed, talking is not.

    from perfkit import lipsync as LS
    rep = LS.check(env, curves, lines, fps=24)   # env: audio.Envelope ON THE MASTER TIMELINE (offset_s = its start)
    rep["pass"], rep["lines"]["L1"]["lag_frames"], rep["issues"]

Conventions: times in seconds on one timeline (the master's, frame 0 = 0 s); curves {name: (times, values)} on that
same timeline (a placed animation's keys shifted by its section start: see `place`); lines [{"id", "t0", "t1"}] are
speech onset/offset from cues.json (measured from the placed audio, never the slot the line was written for), optionally
with "words": [[t0, t1], ...] (aligned words, s) for the per-word check.
"""
from __future__ import annotations

import math

from . import curves as C

P = "CTRL_expressions_"
# How open the mouth is, from the MetaHuman face rig's speech controls: the jaw does most of it; the lips part with
# a depressed lower lip and a raised upper one; pressing or sealing the lips closes it. Weights in jawOpen units.
APERTURE = {P + "jawOpen": 1.0,
            P + "mouthLowerLipDepressL": 0.2, P + "mouthLowerLipDepressR": 0.2,
            P + "mouthUpperLipRaiseL": 0.15, P + "mouthUpperLipRaiseR": 0.15,
            P + "mouthLipsTogetherUL": -0.1, P + "mouthLipsTogetherUR": -0.1,
            P + "mouthLipsTogetherDL": -0.1, P + "mouthLipsTogetherDR": -0.1,
            P + "mouthLipsPressL": -0.1, P + "mouthLipsPressR": -0.1}
# Curves that are the smile/expression layer, not speech (perfkit's expressions add these on a talking mouth).
EXPRESSION_ONLY = ("mouthCornerPull", "mouthCornerDepress", "mouthDimple", "mouthCheekBlow", "mouthCheekSuck",
                   "mouthSharpCornerPull", "mouthCornerNarrow", "mouthCornerWide", "mouthCornerRounder",
                   "mouthStretch")

# The gate's defaults, each with its reason (docs/unreal/research/lipsync.md):
LIMITS = {
    # one frame at 24 fps (42 ms): inside the EBU R37 / ITU-R BT.1359 detectability window (+45 ms audio early,
    # -125 ms audio late), so a pass is invisible; our failure was 17 frames
    "max_lag_frames": 1.0,
    # a face that follows the words reads r 0.5-0.8 on solver output (syllable-band envelope vs aperture); a mouth
    # flapping at a constant rate or a line shifted by a syllable or more falls under 0.3. 0.35 sits between.
    "min_corr": 0.35,
    # the mouth may begin to open this far ahead of the first sound (100-300 ms in natural speech)
    "max_onset_lead_s": 0.25,
    # and may still be closing this long after the last
    "release_s": 0.25,
    # silence: the most the mouth may open above its rest (jawOpen units: ~0.1 is lips just parted, a breath)
    "silence_open": 0.10,
    # silence: the mouth's movement (mean |d aperture/dt|) as a share of its movement on the lines: talking in a
    # silence is as busy as a line (~1.0); a breath or a slow smile is a few percent
    "silence_busy": 0.25,
    # with a reference (the solve placed at the mix's place): the mouth vs the solve, and how sure the voice-vs-mouth
    # lag must be before it can fail on its own
    "min_ref_corr": 0.8,
    "confident_corr": 0.6,  # reported as audio_reliable
    # words (when cues carry aligned ones): the mouth's range inside a word, and the share of words that must move
    "word_move": 0.04,
    "min_words_moving": 0.8,
}


# --- signals -----------------------------------------------------------------------------------------------------

def is_speech_curve(name: str) -> bool:
    """A jaw/lip/tongue curve that a speech solve drives (not the smile layer, eyes, brows or head)."""
    n = name[len(P):] if name.startswith(P) else name
    if not (n.startswith("jaw") or n.startswith("mouth") or n.startswith("tongue")):
        return False
    return not any(n.startswith(x) for x in EXPRESSION_ONLY)


ONSET_GAP_S = 0.12  # the previous line's mouth closes this long after its last word (lipsync.compose fades 3 f)


def aperture(curves: dict, times: list) -> list:
    """The mouth's opening at `times` (jawOpen units, >= 0) from whichever APERTURE curves are present."""
    out = [0.0] * len(times)
    for n, w in APERTURE.items():
        if n in curves:
            t, v = curves[n]
            for i, x in enumerate(C.resample(list(t), list(v), times)):
                out[i] += w * x
    return [max(0.0, x) for x in out]


def has_mouth(curves: dict) -> bool:
    return P + "jawOpen" in curves


def bandpass(values: list, rate: float, lo_hz: float = 1.0, hi_hz: float = 8.0) -> list:
    """Zero-phase band-pass (a low-pass at hi minus a low-pass at lo): the syllable rhythm, without the slow drift
    (a held smile, a mood) or the fast buzz."""
    hi = C.lowpass(values, rate, hi_hz, passes=1)
    lo = C.lowpass(values, rate, lo_hz, passes=2)
    return [a - b for a, b in zip(hi, lo)]


def _pearson(a: list, b: list) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    sab = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    saa = sum((x - ma) ** 2 for x in a)
    sbb = sum((y - mb) ** 2 for y in b)
    if saa <= 1e-12 or sbb <= 1e-12:
        return 0.0
    return sab / math.sqrt(saa * sbb)


def xcorr(audio: list, mouth: list, rate: float, max_lag_s: float = 1.0, center_s: float = 0.0) -> dict:
    """Normalised cross-correlation of two equally sampled signals over lags of center_s +- max_lag_s. The lag is
    the shift of the mouth against the audio at the best correlation: mouth(t + lag) ~ audio(t), so lag < 0 = the
    mouth moves EARLY. Sub-sample by a parabola through the peak. {"lag_s", "corr", "curve": [(lag_s, r)]}."""
    n = len(audio)
    k = int(round(max_lag_s * rate))
    c = int(round(center_s * rate))
    curve = []
    for d in range(c - k, c + k + 1):
        if d >= 0:
            a, b = audio[:n - d], mouth[d:]
        else:
            a, b = audio[-d:], mouth[:n + d]
        if len(a) < max(8, n // 3):  # too little overlap to mean anything
            continue
        curve.append((d, _pearson(a, b)))
    if not curve:
        return {"lag_s": 0.0, "corr": 0.0, "curve": []}
    i = max(range(len(curve)), key=lambda j: curve[j][1])
    d, r = curve[i]
    lag = float(d)
    if 0 < i < len(curve) - 1:
        y0, y1, y2 = curve[i - 1][1], r, curve[i + 1][1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            lag += max(-0.5, min(0.5, 0.5 * (y0 - y2) / den))
    return {"lag_s": lag / rate, "corr": r, "curve": [(x / rate, y) for x, y in curve]}


# --- voice activity ----------------------------------------------------------------------------------------------

def vad(values: list, rate: float, offset_s: float = 0.0, on: float = 0.3, off: float = 0.15,
        min_speech_s: float = 0.06, min_gap_s: float = 0.15) -> list:
    """Speech spans [(t0, t1)] from a 0..1 loudness envelope (perfkit.audio.Envelope.values: dB mapped over the
    clip's top 45 dB): on when it rises over `on`, off when it falls under `off` (hysteresis, so a word's dip does
    not split it), gaps under `min_gap_s` bridged, blips under `min_speech_s` dropped. The edges are walked back to
    where the loudness first left the floor (`off`), so t0 is the first sound, not the first loud sound."""
    sm = C.lowpass(values, rate, 15.0, passes=1)
    spans, start, n = [], None, len(sm)
    for i, v in enumerate(sm):
        if start is None and v >= on:
            j = i
            while j > 0 and sm[j - 1] >= off * 0.6:
                j -= 1
            start = j
        elif start is not None and v < off:
            spans.append([start, i])
            start = None
    if start is not None:
        spans.append([start, n])
    merged = []
    for a, b in spans:
        if merged and (a - merged[-1][1]) / rate < min_gap_s:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(round(offset_s + a / rate, 4), round(offset_s + b / rate, 4)) for a, b in merged
            if (b - a) / rate >= min_speech_s]


def speech_in(spans: list, t0: float, t1: float) -> tuple | None:
    """The first sound and the last within [t0, t1] (a line's slot): (onset, offset) or None (silent slot)."""
    inside = [(max(a, t0), min(b, t1)) for a, b in spans if b > t0 and a < t1]
    if not inside:
        return None
    return inside[0][0], inside[-1][1]


# --- placement ---------------------------------------------------------------------------------------------------

def place(curves: dict, start_s: float, offset_s: float = 0.0, rate: float = 1.0, end_s: float | None = None,
          rest_outside: bool = False) -> dict:
    """An animation's curves as a Sequencer section plays them, on the master timeline: the section starts at
    `start_s` (s), begins `offset_s` into the animation (StartFrameOffset + FirstLoopStartFrameOffset), at `rate`.
    Keys before the offset or after `end_s` are dropped. `rest_outside`: the curves fall to 0 just outside their
    keys (a line's solve checked alone: before and after it nothing drives the face; r5 P2 read a solve's first
    keys, held, as a mouth open in the silence before the line)."""
    out = {}
    for n, (t, v) in curves.items():
        tt, vv = [], []
        for x, y in zip(t, v):
            m = start_s + (x - offset_s) / (rate or 1.0)
            if x < offset_s - 1e-9 or (end_s is not None and m > end_s + 1e-9):
                continue
            tt.append(m)
            vv.append(y)
        if tt:
            if rest_outside:  # nothing drives the face outside the section: rest (0), not the end keys held
                eps = 1.0 / 240.0
                tt, vv = [tt[0] - eps] + tt + [tt[-1] + eps], [0.0] + vv + [0.0]
            out[n] = (tt, vv)
    return out


def merge_sections(placed: list) -> dict:
    """Several placed sections' curves [(t0, t1, curves)] on one track: each curve from the section playing at each
    key (the later section wins an overlap), as one keyed curve."""
    out: dict = {}
    for t0, t1, cur in sorted(placed, key=lambda s: s[0]):
        for n, (t, v) in cur.items():
            ot, ov = out.get(n, ([], []))
            keep = [(x, y) for x, y in zip(ot, ov) if x < t0 - 1e-9]
            keep += [(x, y) for x, y in zip(t, v) if t0 - 1e-9 <= x <= t1 + 1e-9]
            keep.sort()
            out[n] = ([x for x, _ in keep], [y for _, y in keep])
    return out


# --- the check ---------------------------------------------------------------------------------------------------

def _issue(code: str, line: str, message: str, fix: str, **metrics) -> dict:
    return {"code": code, "severity": "fail", "line": line, "message": message, "fix": fix, **metrics}


def check(env, curves: dict, lines: list, fps: float = 24.0, limits: dict | None = None, rate: float = 100.0,
          expected_lag_s: float = 0.0, max_lag_s: float = 1.0, span: tuple | None = None,
          reference: dict | None = None) -> dict:
    """Lip-sync of one face against its voice, per line, plus the silences. See the module docstring.

    env: perfkit.audio.Envelope of the voice as placed in the mix (its offset_s = where it starts on the master).
    curves: the face's curves on the master timeline (place / merge_sections). lines: [{"id", "t0", "t1"}] speech
    onset/offset (s) of this face's lines. fps: the sequence's display rate (the lag limit is in its frames).
    expected_lag_s: the solver's own lag on a line it solved alone (lipsync.check_anim on the raw solve; 0 by
    default): what is judged is the placed lag minus it. span: (t0, t1) the face is on screen/active (default: the
    first line - 2 s .. the last + 2 s), for the silence check.

    reference: the speech solver's own mouth for these lines, on the same timeline (each line's solve placed at its
    WAV's place in the mix: lipsync.check reference=[{anim, frame}]). With it, timing and tracking are judged
    against the solve (mouth vs mouth: r ~1 when in place, a sharp peak): FAIL on |ref lag| > 1 frame or ref r <
    0.8; the voice-vs-mouth lag and r are then reported, not judged: on short real lines loudness and jaw opening
    diverge (r5 P2: the real solves, exactly in place, read r 0.25-0.88 and lags of -23 to +16 frames). The
    silence and onset checks still judge against the voice.

    Returns {"pass", "lines": {id: {...}}, "silences": [...], "silence": {...}, "issues": [...], "diagnosis",
    "limits"}. Every issue says what to do."""
    lim = {**LIMITS, **(limits or {})}
    issues = []
    if not has_mouth(curves):
        return {"pass": False, "lines": {}, "silences": [], "silence": {}, "limits": lim, "diagnosis": "no mouth",
                "issues": [_issue("no_mouth", "", "the face has no CTRL_expressions_jawOpen curve on the timeline",
                                  "check the Face track plays the speech animation (seq.anim) and that it was "
                                  "solved on this face's skeleton (speech.to_face face_mesh=...)")]}
    lines = sorted(lines, key=lambda x: x["t0"])
    if not lines:
        raise ValueError("no lines to check: pass this face's lines from cues.json")
    t_lo = span[0] if span else lines[0]["t0"] - 2.0
    t_hi = span[1] if span else lines[-1]["t1"] + 2.0
    times = C.grid(t_lo - max_lag_s, t_hi + max_lag_s, rate)
    aud_raw = [env.at(t) for t in times]
    mouth_raw = aperture(curves, times)
    aud = bandpass(aud_raw, rate)
    mth = bandpass(mouth_raw, rate)
    slow_a = bandpass(aud_raw, rate, 0.25, 2.5)
    slow_m = bandpass(mouth_raw, rate, 0.25, 2.5)
    ref_m = bandpass(aperture(reference, times), rate, 0.25, 8.0) if reference else None
    mth_r = bandpass(mouth_raw, rate, 0.25, 8.0) if reference else None
    frame = 1.0 / fps
    spans = vad(env.values, env.rate, env.offset_s)

    def window(a, b):
        i0 = max(0, int((a - times[0]) * rate))
        i1 = min(len(times), int((b - times[0]) * rate) + 1)
        return i0, i1

    out_lines, lags = {}, []
    speed_on = []
    prev_t1 = None
    for ln in lines:
        lid, t0, t1 = ln["id"], float(ln["t0"]), float(ln["t1"])
        # the onset search reaches back max_lag_s, but never into the line before (r6 explainers: 0.34 s gaps read
        # the previous line's mouth as this one opening ~1 s early); ONSET_GAP_S after its last word
        lo = t0 - max_lag_s if prev_t1 is None else max(t0 - max_lag_s, min(t0 - 0.05, prev_t1 + ONSET_GAP_S))
        prev_t1 = t1
        i0, i1 = window(t0 - max_lag_s, t1 + max_lag_s)
        # two stages: the words' envelope (0.25-2.5 Hz) finds the lag over +-max_lag_s without locking onto a
        # neighbouring syllable (round-5 P1: real solves read r 0.4-0.5 in the syllable band, and its peak jumped
        # 5-11 frames); the syllable band then refines it within +-0.15 s of that
        xc = xcorr(slow_a[i0:i1], slow_m[i0:i1], rate, max_lag_s)
        x = xcorr(aud[i0:i1], mth[i0:i1], rate, 0.15, center_s=xc["lag_s"])
        lag = x["lag_s"] - expected_lag_s
        # the mouth's own onset: first rise above the rest by a quarter of the line's opening
        j0, j1 = window(lo, t1)
        seg = mouth_raw[j0:j1]
        k0, k1 = window(t0, t1)
        on_line = mouth_raw[k0:k1] or [0.0]
        rest = sorted(mouth_raw[j0:max(j0 + 1, k0 - int(0.3 * rate))])[:max(1, (k0 - j0) // 4)] or [0.0]
        rest_v = sum(rest) / len(rest)
        peak = sorted(on_line)[int(0.9 * (len(on_line) - 1))]
        thr = rest_v + 0.25 * max(0.0, peak - rest_v)
        m_on = next((times[j0 + i] for i, v in enumerate(seg) if v > thr), None)
        lead = (t0 - m_on) if m_on is not None else None
        d = C.derivative(times[k0:k1], on_line)
        speed_on.extend(abs(v) for v in d)
        rec = {"t0": round(t0, 3), "t1": round(t1, 3), "lag_s": round(lag, 4), "lag_frames": round(lag / frame, 2),
               "raw_lag_s": round(x["lag_s"], 4), "corr": round(x["corr"], 3),
               "coarse_lag_frames": round(xc["lag_s"] / frame, 2), "coarse_corr": round(xc["corr"], 3),
               "onset_lead_s": round(lead, 3) if lead is not None else None,
               "open_range": round(peak - rest_v, 3)}
        fails = []
        # with the solve as the reference the voice-vs-mouth lag is only reported: on the real r5 solves it read
        # -1 to -23 frames on lines that are exactly in place (loudness is not jaw opening on short lines)
        confident = reference is None
        rec["audio_reliable"] = x["corr"] >= lim["confident_corr"]
        if reference is not None:
            xr = xcorr(ref_m[i0:i1], mth_r[i0:i1], rate, max_lag_s)
            rec["ref_lag_frames"], rec["ref_corr"] = round(xr["lag_s"] / frame, 2), round(xr["corr"], 3)
            if abs(xr["lag_s"]) > (lim["max_lag_frames"] + 0.05) * frame:  # 1 frame passes (measured 1.01)
                fails.append(_issue(
                    "ref_lag", lid, f"{lid}: the mouth is {abs(rec['ref_lag_frames']):.1f} frames "
                    f"{'EARLY' if xr['lag_s'] < 0 else 'LATE'} on its own solve placed at the line's place in the mix",
                    "a stage after the solve moved it (compose offset, a section start/offset, a rate): lips.py check "
                    "--stage solve/face/final/placed finds which", ref_lag_frames=rec["ref_lag_frames"]))
            if xr["corr"] < lim["min_ref_corr"]:
                fails.append(_issue(
                    "ref_corr", lid, f"{lid}: the mouth no longer follows its solve (r {xr['corr']:.2f}, limit "
                    f"{lim['min_ref_corr']:g})", "a layer rewrote the speech curves (gain clamp, expression, another "
                    "solve): only the solve's speech curves may drive the mouth on a line", ref_corr=rec["ref_corr"]))
        if confident and abs(lag) > (lim["max_lag_frames"] + 0.05) * frame:
            way = "EARLY" if lag < 0 else "LATE"
            fails.append(_issue(
                "lag", lid, f"{lid}: the mouth is {abs(lag) / frame:.1f} frames {way} on its voice "
                f"({lag * 1000:+.0f} ms; limit {lim['max_lag_frames']:g} frame)",
                f"move the face {abs(lag) / frame:.1f} frames {'later' if lag < 0 else 'earlier'}: re-place the line's "
                "solve at its cue (the solve's t=0 is its WAV's first sample, which starts on the line's file_frame); "
                "if every line is off by the same amount, the section or the audio is misplaced; if it grows with "
                "time, a frame rate is wrong (see diagnosis)", lag_frames=rec["lag_frames"]))
        if reference is None and x["corr"] < lim["min_corr"]:
            fails.append(_issue(
                "corr", lid, f"{lid}: the mouth does not follow the words (r {x['corr']:.2f} at its best lag, "
                f"limit {lim['min_corr']:g})",
                "the mouth on this line is not this line's solve: re-solve it (speech.to_face on the line's WAV), "
                "check the splice/compose put it at the cue, and that no layer (gain clamp, expression) flattens "
                "the jaw", corr=rec["corr"]))
        if lead is not None and lead > lim["max_onset_lead_s"]:
            fails.append(_issue(
                "onset", lid, f"{lid}: the mouth starts opening {lead:.2f} s before the first sound "
                f"(allowed {lim['max_onset_lead_s']:g} s)",
                "the face starts talking before the voice: the solve is placed early, or another line's motion "
                "(a splice fade, the whole-stem solve) leaks in; place mouth curves only from each line's onset",
                onset_lead_s=rec["onset_lead_s"]))
        if rec["open_range"] < 0.08:
            fails.append(_issue("flat", lid, f"{lid}: the mouth barely opens on the line (range {rec['open_range']})",
                                "the solve is missing or muted here (speech gain, mood, a mask)",
                                open_range=rec["open_range"]))
        if ln.get("words"):  # aligned words: the mouth must move within each (a held mouth over a word is a miss)
            moving = 0
            for w0, w1 in ln["words"]:
                a, b = window(w0 + lag, w1 + lag)
                seg_w = mouth_raw[a:b]
                if seg_w and max(seg_w) - min(seg_w) >= lim["word_move"]:
                    moving += 1
            share = moving / len(ln["words"])
            rec["words_moving"] = round(share, 3)
            if share < lim["min_words_moving"]:
                fails.append(_issue("words", lid, f"{lid}: the mouth moves in {share:.0%} of its words "
                                    f"(limit {lim['min_words_moving']:.0%})",
                                    "the solve does not articulate these words: re-solve the line alone (its own WAV, "
                                    "mood), or check a gain/clamp that holds the jaw", words_moving=rec["words_moving"]))
        rec["pass"] = not fails
        issues += fails
        out_lines[lid] = rec
        lags.append((t0, rec["ref_lag_frames"] * frame if reference is not None else lag))
    # silences: outside every voice span, padded by the anticipation and the release
    allowed = [(a - lim["max_onset_lead_s"], b + lim["release_s"]) for a, b in spans]
    quiet = []
    t = t_lo
    for a, b in sorted(allowed) + [(t_hi, t_hi)]:
        if a > t + 0.2:
            quiet.append((t, min(a, t_hi)))
        t = max(t, b)
    rest_all = []
    for a, b in quiet:
        i0, i1 = window(a, b)
        rest_all += mouth_raw[i0:i1]
    rest = sorted(rest_all)[len(rest_all) // 2] if rest_all else 0.0
    mean_on = sum(speed_on) / len(speed_on) if speed_on else 0.0
    sil, worst_open, worst_busy = [], 0.0, 0.0
    for a, b in quiet:
        i0, i1 = window(a, b)
        seg = mouth_raw[i0:i1]
        if len(seg) < 3:
            continue
        top = sorted(seg)[int(0.95 * (len(seg) - 1))] - rest
        d = C.derivative(times[i0:i1], seg)
        busy = (sum(abs(v) for v in d) / len(d)) / mean_on if mean_on > 1e-9 else 0.0
        rec = {"t0": round(a, 3), "t1": round(b, 3), "frames": [round(a * fps), round(b * fps)],
               "open": round(top, 3), "busy": round(busy, 3)}
        rec["pass"] = top <= lim["silence_open"] and busy <= lim["silence_busy"]
        if not rec["pass"]:
            what = []
            if top > lim["silence_open"]:
                what.append(f"opens {top:.2f} (allowed {lim['silence_open']:g})")
            if busy > lim["silence_busy"]:
                what.append(f"moves at {busy:.0%} of its talking speed (allowed {lim['silence_busy']:.0%})")
            issues.append(_issue(
                "silence", "", f"the mouth moves in the silence {a:.2f}-{b:.2f} s (f{rec['frames'][0]}-"
                f"f{rec['frames'][1]}): " + ", ".join(what),
                "nobody speaks here: the mouth must rest (a breath or smile only). Rest the speech curves outside "
                "each line (lipsync.compose), or find the misplaced line whose motion this is (see each line's lag)",
                open=rec["open"], busy=rec["busy"]))
        worst_open, worst_busy = max(worst_open, top), max(worst_busy, busy)
        sil.append(rec)
    diag = diagnose(lags, frame, lim["max_lag_frames"])
    return {"pass": not issues, "lines": out_lines, "silences": sil,
            "silence": {"rest": round(rest, 3), "worst_open": round(worst_open, 3), "worst_busy": round(worst_busy, 3)},
            "issues": issues, "diagnosis": diag, "limits": lim, "expected_lag_s": expected_lag_s,
            "voice_spans": [list(s) for s in spans]}


def diagnose(lags: list, frame: float, max_frames: float = 1.0) -> str:
    """What the per-line lags say: in sync, a constant offset (misplaced section/audio), or a drift (a rate/fps
    mismatch: lag grows with time), or scattered (lines placed independently, each wrong)."""
    if not lags:
        return "no lines"
    bad = [abs(l) > max_frames * frame for _, l in lags]
    if not any(bad):
        return "in sync"
    if len(lags) >= 3:
        n = len(lags)
        mt = sum(t for t, _ in lags) / n
        ml = sum(l for _, l in lags) / n
        stt = sum((t - mt) ** 2 for t, _ in lags)
        slope = sum((t - mt) * (l - ml) for t, l in lags) / stt if stt > 1e-9 else 0.0
        resid = max(abs(l - (ml + slope * (t - mt))) for t, l in lags)
        if abs(slope) > 0.005 and resid < 1.5 * frame:
            return (f"drift: the lag grows {slope * 100:+.1f}% of the elapsed time (a frame-rate or play-rate "
                    f"mismatch, e.g. 30 fps keys read as 24 = -20%); check the solve's frame rate and the section's "
                    f"play rate")
    ls = [l for _, l in lags]
    if max(ls) - min(ls) < 1.5 * frame:
        mean = sum(ls) / len(ls)
        return (f"offset: every line is {abs(mean) / frame:.1f} frames {'early' if mean < 0 else 'late'}: the face "
                f"section, its offset or the audio is misplaced by that much")
    return "scattered: the lines are off by different amounts: each line's placement is wrong on its own"


# --- the mouth from per-line solves -------------------------------------------------------------------------------

def compose(parts: list, length_s: float, rate: float = 30.0, fade_s: float = 0.12, rest: dict | None = None,
            names: list | None = None, base: dict | None = None, keep_base: float = 0.0) -> dict:
    """One face's speech curves from per-line solves on its master timeline: each part (t0, curves) is a line's
    solve whose t=0 is its WAV's first sample, placed at t0 (the WAV's start on the timeline, cues' file_frame).
    Inside a part the line's own mouth plays; between parts the mouth rests (`rest` {name: value}, default 0), so
    nobody talks in a silence; `fade_s` blends into and out of each part at its ends (its WAV is trimmed to ~50 ms
    before the first word, so the fade ends before the first sound). `base` (a whole-performance solve) can be kept
    under the rest at `keep_base` (0..1) for breathing; 0 = none (default). Only speech curves (is_speech_curve).

    Returns {name: (times, values)} on a `rate` grid from 0 to length_s."""
    rest = rest or {}
    times = C.grid(0.0, length_s, rate)
    found = set(names or [])
    if not names:
        for _, cur in parts:
            found |= {n for n in cur if is_speech_curve(n)}
    out = {}
    for n in sorted(found):
        r0 = float(rest.get(n, 0.0))
        if base and n in base and keep_base > 0:
            bt, bv = base[n]
            vals = [r0 + keep_base * (y - r0) for y in C.resample(list(bt), list(bv), times)]
        else:
            vals = [r0] * len(times)
        for t0, cur in sorted(parts, key=lambda p: p[0]):
            if n not in cur:
                continue
            pt, pv = cur[n]
            if not pt:
                continue
            length = pt[-1]
            for i, x in enumerate(times):
                u = x - t0
                if u < 0 or u > length:
                    continue
                w = C.smoothstep(min(1.0, u / fade_s if fade_s > 0 else 1.0,
                                     (length - u) / fade_s if fade_s > 0 else 1.0))
                vals[i] = vals[i] * (1 - w) + C.at(pt, pv, u) * w
        out[n] = C.reduce(times, vals, 0.002)
    return out
