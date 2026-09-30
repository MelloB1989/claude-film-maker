"""Spoken word onsets, measured on the audio (spec §2: a word lights within one frame of its spoken onset, never
ahead of the voice).

Forced alignment starts a word that follows silence anywhere from 0 to 190 ms late (short words such as "I" are the
worst), so one constant lead can't fix it. The onset of every word that opens a line or follows a pause is measured:

- 5 ms frames; the level in dB relative to the take's loudest frame, and the zero-crossing rate per sample.
- The search runs from max(previous word's end, start - 0.20 s) to start + 0.08 s, and never past the word's own end
  (otherwise a short word inside connected speech would take the next word's onset).
- The onset is the first frame at or above -30 dB that begins a voiced run: the next 30 ms stay above -35 dB and at
  least two-thirds of them (4 of the 6 frames) have a zero-crossing rate below ZCR_MAX. So up to 10 ms of plosive
  burst may head the run (the burst is the audible start), while a breath or a fricative, noise all the way through,
  never qualifies, and at most 10 ms of one can precede the voice it runs into.
- The run must begin a sound: the stretch of frames at or above -30 dB that holds it starts inside the window. A
  stretch already sounding when the window opens is the previous word running on past its aligned end, not this
  word.

Words less than `min_gap` after the previous word's end are inside connected speech and get None, as does a word
where nothing qualifies; both keep their aligned start.
"""
import math

import numpy as np

FRAME = 0.005
ON_DB = -30.0  # an onset frame is at least this loud
RUN_DB = -35.0  # and the next RUN seconds stay above this
RUN = 0.03
# Calibrated on the 106 paced takes (5 ms frames). In-word frames at or above -30 dB split into a voiced mode (median
# 0.025, p75 0.050, thinning out by 0.10) and an unvoiced one (fricatives and aspiration, 0.20-0.44). Breath-like
# sound in the pauses between words (-50 to -25 dB, 150 ms or more from any word) has median 0.126 and p25 0.105;
# room tone 0.37. A frame under 0.10 is voiced; breath rarely is, and four such frames in six almost never.
ZCR_MAX = 0.10
VOICED_SHARE = 2 / 3
BEFORE, AFTER = 0.20, 0.08


def frames(samples: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, int]:
    """Per 5 ms frame: level in dB relative to the loudest frame (-inf for digital silence), zero crossings per
    sample, and the frame length in samples."""
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 2:
        x = x.mean(axis=1)
    n = max(2, int(round(FRAME * sr)))
    m = len(x) // n
    fr = x[:m * n].reshape(m, n)
    rms = np.sqrt(np.mean(fr ** 2, axis=1))
    peak = float(rms.max()) if m else 0.0
    with np.errstate(divide="ignore"):
        db = 20 * np.log10(rms / peak) if peak > 0 else np.full(m, -np.inf)
    sign = np.signbit(fr)
    zcr = np.count_nonzero(sign[:, 1:] != sign[:, :-1], axis=1) / (n - 1)
    return db, zcr, n


def voice_onsets(samples: np.ndarray, sr: int, words: list[dict], min_gap: float = 0.06) -> list[float | None]:
    """The spoken onset (seconds, on the samples' own clock) of each word that starts the list or follows a gap of
    at least `min_gap`; None for the others and for any word with no voiced onset in its window."""
    db, zcr, n = frames(samples, sr)
    k = int(round(RUN / FRAME))
    m = len(db)

    def voiced(j: int) -> bool:
        return (j + k <= m and db[j] >= ON_DB and bool(np.all(db[j:j + k] > RUN_DB))
                and np.count_nonzero(zcr[j:j + k] < ZCR_MAX) >= VOICED_SHARE * k - 1e-9)

    out: list[float | None] = []
    for i, w in enumerate(words):
        prev_end = words[i - 1]["end"] if i else 0.0
        if i and w["start"] - prev_end < min_gap:
            out.append(None)
            continue
        lo = max(prev_end, w["start"] - BEFORE, 0.0)
        hi = min(w["start"] + AFTER, w["end"])
        a = math.ceil(lo * sr / n - 1e-9)
        b = min(math.floor(hi * sr / n + 1e-9), m - 1)
        onset = None
        for j in range(a, b + 1):
            if not voiced(j):
                continue
            s = j
            while s > 0 and db[s - 1] >= ON_DB:
                s -= 1
            if s >= a:  # this sound began inside the window, and j is its first voiced run
                onset = round(j * n / sr, 4)
                break
        out.append(onset)
    return out
