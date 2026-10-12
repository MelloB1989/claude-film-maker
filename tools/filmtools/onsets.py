"""Spoken word onsets, measured on the audio (spec §2: a word lights within one frame of its spoken onset, never
ahead of the voice).

Forced alignment starts a word that follows silence anywhere from 0 to 190 ms late (short words such as "I" are the
worst), so one constant lead can't fix it. The onset of every word that opens a line or follows a pause is measured:

- 5 ms frames; the level in dB relative to the take's loudest frame, and the zero-crossing rate per sample.
- The search runs from max(previous word's end, start - 0.20 s) to start + 0.08 s, and never past the word's own end
  (otherwise a short word inside connected speech would take the next word's onset).
- First the word's voiced run: the first frame at or above -30 dB whose next 30 ms stay above -35 dB with at least
  two-thirds of them (4 of the 6 frames) under ZCR_MAX. It must begin a sound: the stretch of frames at or above
  -30 dB that holds it starts inside the window (a stretch already sounding when the window opens is the previous
  word running on past its aligned end).
- Then back from that run over the consonant that leads into it (walk_back): the onset is the start of the
  contiguous sound at or above -35 dB that runs into the vowel, so a fricative, a burst or aspiration counts, as the
  spoken start it is. Gaps below -35 dB of up to 15 ms are crossed, and so is one stop closure of up to 90 ms after a
  real fricative (the /s/ of "Skills"). A breath or a pause that ends in silence before the voice starts is not.

Words less than `min_gap` after the previous word's end are inside connected speech and get None, as does a word
with no voiced run in its window; both keep their aligned start.
"""
import math

import numpy as np

FRAME = 0.005
ON_DB = -30.0  # a voiced run starts at least this loud
RUN_DB = -35.0  # its next RUN seconds stay above this, and the walk back runs over sound at or above it
RUN = 0.03
# Calibrated on the 106 paced takes (5 ms frames). In-word frames at or above -30 dB split into a voiced mode (median
# 0.025, p75 0.050, thinning out by 0.10) and an unvoiced one (fricatives and aspiration, 0.20-0.44). Breath-like
# sound in the pauses between words (-50 to -25 dB, 150 ms or more from any word) has median 0.126 and p25 0.105;
# room tone 0.37. A frame under 0.10 is voiced; breath rarely is, and four such frames in six almost never.
ZCR_MAX = 0.10
VOICED_SHARE = 2 / 3
BEFORE, AFTER = 0.20, 0.08
SHORT_GAP = 0.015  # a dip below RUN_DB this short inside a consonant is crossed
CLOSURE = 0.09  # one stop closure this long is crossed back to a real fricative:
FRICATIVE_DB, FRICATIVE_MIN = -25.0, 0.02  # 20 ms or more at -25 dB or louder, mostly unvoiced


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


def walk_back(db: np.ndarray, zcr: np.ndarray, j: int, a: int) -> int:
    """The first frame of the word whose voiced run starts at frame j, searching no earlier than frame a.

    Back from j, over sound at or above RUN_DB. A stretch that is still sounding when the window opens (at frame a)
    runs on from the previous word: of it, only unvoiced frames that begin after its voicing, inside the window, can
    be this word's consonant (the /s/ of "store" right after "vector"), and the walk ends there. Gaps up to SHORT_GAP
    are crossed. One gap up to CLOSURE is crossed as a stop closure only when it is released (the frame after it is
    unvoiced) and the sound before it is a real fricative: FRICATIVE_MIN at FRICATIVE_DB or louder, mostly unvoiced.
    A breath before a pause ends in silence, and the voice after it starts voiced, so it is never joined."""
    snd, unv = db >= RUN_DB, zcr >= ZCR_MAX
    short, closure = round(SHORT_GAP / FRAME), round(CLOSURE / FRAME)
    loud = round(FRICATIVE_MIN / FRAME)

    def stretch_start(e: int) -> tuple[int, bool]:
        s = e
        while s > a and snd[s - 1]:
            s -= 1
        return s, s == a and a > 0 and bool(snd[a - 1])

    def own_consonant(e: int) -> int | None:
        """In a stretch that runs on from before the window, the unvoiced frames ending at e, if they began after
        voicing inside the window."""
        q = e
        while q >= a and unv[q]:
            q -= 1
        return q + 1 if a <= q < e else None

    s, running_on = stretch_start(j)
    if running_on:
        c = own_consonant(j - 1)
        return j if c is None else c
    onset, closed = s, False
    while True:
        g = onset - 1
        while g >= a and not snd[g]:
            g -= 1
        if g < a:
            break  # silence back to the window's start
        gap = onset - 1 - g
        s, running_on = stretch_start(g)
        own = own_consonant(g) if running_on else s
        if own is None:
            break
        if gap <= short:
            onset = own
        elif (not closed and gap <= closure and unv[onset] and np.count_nonzero(db[own:g + 1] >= FRICATIVE_DB) >= loud
              and 2 * np.count_nonzero(unv[own:g + 1]) > g + 1 - own):
            onset, closed = own, True
        else:
            break  # (after a running-on stretch's consonant the previous word's voice follows, so the next step ends)
    return onset


def voice_onsets(samples: np.ndarray, sr: int, words: list[dict], min_gap: float = 0.06) -> list[float | None]:
    """The spoken onset (seconds, on the samples' own clock) of each word that starts the list or follows a gap of
    at least `min_gap`; None for the others and for any word with no voiced run in its window."""
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
                onset = round(walk_back(db, zcr, j, a) * n / sr, 4)
                break
        out.append(onset)
    return out
