"""The karma reel's score (PLAN.md §2, task R5): composed by ElevenLabs Music from the section plan below, then
conformed to the picture's grid: 96 bpm in 4/4, 26 bars, exactly 65.0 s, the drop on bar 13 beat 1 (f720, 30.0 s).

    cd tools && python ../films/host-studio/reel/score.py gen --plan v2 --seed 1   # one paid take (cached)
    cd tools && python ../films/host-studio/reel/score.py conform --take v2-seed1  # on the grid -> score/score.wav
    cd tools && python ../films/host-studio/reel/score.py check            # beat grid, sections, loudness, spectra

The API key comes from $ELEVENLABS_API_KEY (fleetctl secret exec ELEVENLABS_API_KEY=elevenlabs -- ...). Only `gen`
spends credits; it refuses to compose a take it already has.

A take comes back near the asked tempo, not on it, and a model's section boundaries land within a beat or so of where
they were asked. `conform` measures the take's own beat grid (librosa's tracked beats, a straight line through them,
as film-beats does), finds its bars, and maps them onto the picture's: each section of the plan is varispeeded (a
plain resample: transients stay intact, the pitch moves by the same tiny ratio, a few cents) so its first downbeat
lands on its bar line; the cut between sections is a 20 ms equal-power crossfade on the downbeat. Then the edits the
picture asks for and a model cannot place to the frame: the breath (the last beat of bar 12 drops out), the drop
opening hard on 30.0 s, and the fade to black over the last 24 frames.

Files (films/host-studio/reel/audio/): score/takes/<plan>-seed<N>.flac and .json (the take as composed, with its plan, cost
and request id), score/score.wav (48 kHz stereo 24-bit, 65.000 s), score/score.json (the conform's map and checks),
score/check.png.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "tools"))

import shots as S  # noqa: E402
from filmtools.elevenlabs import ElevenLabs, ElevenLabsError  # noqa: E402
from filmtools.wav import SR, read_wav, write_wav  # noqa: E402

AUDIO = HERE / "audio"
SCORE = AUDIO / "score"
TAKES = SCORE / "takes"
CREDITS = AUDIO / "credits.log"

BPM, BPB = S.BPM, 4
BEAT_S = 60.0 / BPM            # 0.625 s = 15 frames
BAR_S = BPB * BEAT_S           # 2.5 s = 60 frames
BARS = 26
DURATION = BARS * BAR_S        # 65.0 s
N = int(round(DURATION * SR))  # 3 120 000 samples
DROP_BAR = 13
MODEL = "music_v2_5"


def bar_t(n: int, beat: float = 1) -> float:
    """Seconds at bar n (1-based), beat (1-based, fractional for the &)."""
    return (n - 1) * BAR_S + (beat - 1) * BEAT_S


# ---------------------------------------------------------------- the composition plan (PLAN.md §2)

# Every chunk carries these. The tempo and key are named in every chunk so no section wanders off them.
GLOBAL = {
    "positive": [
        "instrumental", "96 BPM", "4/4", "D minor", "downtempo", "organic house", "warm lo-fi hip-hop feel",
        "cinematic", "calm, warm, premium, intimate", "felt piano", "Rhodes electric piano", "tape-warm analog pads",
        "soft brushed kick", "shakers", "round warm sub bass", "gentle tape saturation", "high-end production",
        "steady tempo throughout",
    ],
    "negative": [
        "vocals", "singing", "choir", "vocal chops", "spoken word", "rap", "humming", "lyrics", "EDM build-up",
        "aggressive", "distorted", "harsh", "trap hi-hat rolls", "dubstep", "electric guitar", "orchestral",
        "epic trailer", "tempo change", "ritardando", "swing feel change", "brass",
    ],
}

# (name, bars, positive, negative): whole bars, 26 in all. The bar lines are the cuts (shots.py); the comments are
# the picture each section plays under. Every version of the plan keeps these bars; a take is <version>-seed<N>.
# v1: take v1-seed1 came back on tempo (96.08 bpm) with its sections on their bars, but no kick or bass before bar 9
# and the drop no bigger than the build.
V1 = [
    ("Morning", 4,  # bars 1-4, S01-S02: soft morning light on the empty room
     ["solo felt piano playing a simple, memorable four-note motif", "warm sustained pad underneath",
      "soft vinyl room tone", "no drums", "no bass", "sparse and spacious", "morning light, peaceful, hopeful"],
     ["drums", "percussion", "bass", "beat"]),
    ("First Kick", 2,  # bars 5-6, S03-S04: the spines, the polaroid
     ["a soft brushed kick drum enters on the first beat and plays on every beat", "the felt piano motif continues",
      "warm pad", "still no bass", "gentle and intimate"],
     ["hi-hats", "snare", "loud"]),
    ("Bass", 2,  # bars 7-8, S05-S06: the acrylic block, the coin
     ["round warm sub bass enters", "soft brushed kick on every beat", "Rhodes chords join the felt piano",
      "shakers", "gentle forward motion"],
     ["hi-hats", "loud"]),
    ("Golden Hour Build", 4,  # bars 9-12, S07-S10: the drone, the terminal, the calendar, the crate
     ["soft closed hi-hats enter", "the groove builds gently", "a long filtered riser swells through the section",
      "anticipation, dusk turning to night", "the arrangement thins in the last beat before the drop"],
     ["full drop", "loud drums", "crash cymbal"]),
    ("Ignition", 2,  # bars 13-14, S11-S12: THE DROP on bar 13 beat 1, the sign lights, the studio comes on
     ["the drop: a deep sub bass hit on the first beat", "the full groove comes in at once",
      "a sustained tanpura drone", "warm, wide, glowing", "kick, shakers, bass, Rhodes and pads together",
      "confident but calm"],
     ["vocals", "screaming synth lead", "big EDM drop", "wobble bass"]),
    ("Him", 4,  # bars 15-18, S13-S14: him; the groove thins under his line
     ["the groove thins out to leave room for a spoken voice", "kick, sub bass and soft pads only",
      "no lead melody", "muted Rhodes stabs", "low tanpura drone in the background", "intimate, focused"],
     ["lead melody", "piano melody", "busy percussion", "loud"]),
    ("Hand-off", 2,  # bars 19-20, S15: the focus pull from him to her
     ["sparse groove under a spoken voice", "kick and sub bass", "soft pads", "a gentle filtered sweep opening up",
      "no lead melody"],
     ["lead melody", "busy percussion", "loud"]),
    ("Her Lift", 2,  # bars 21-22, S16: her; a Dorian lift, a counter-melody enters with her
     ["a Dorian lift, brighter harmony", "a soft Rhodes counter-melody enters", "the groove stays light under a voice",
      "warm and open"],
     ["busy drums", "loud lead"]),
    ("Together", 2,  # bars 23-24, S17: both, the crane back into the wide
     ["the felt piano motif returns in full", "full warm groove", "pads and Rhodes together", "resolving, uplifting"],
     ["new melody", "aggressive"]),
    ("Final Chord", 2,  # bars 25-26, S18: the title; the last chord rings out
     ["one final sustained D minor add9 chord on the first beat, ringing out", "drums stop", "piano and pad decay",
      "a soft sub tail", "peaceful ending"],
     ["drums", "new melody", "abrupt ending"]),
]
V2 = [
    ("Morning", 4,  # bars 1-4, S01-S02
     ["solo felt piano: a slow, simple, memorable melody of single notes over soft held chords",
      "warm sustained pad underneath", "soft vinyl crackle", "no drums", "no bass", "sparse and spacious",
      "morning light, peaceful, hopeful"],
     ["drums", "percussion", "bass", "beat", "kick"]),
    ("First Kick", 2,  # bars 5-6, S03-S04: the kick lands with the cut to the spines
     ["a soft, muffled, low-pass filtered kick drum starts on the first beat and plays four on the floor",
      "the felt piano melody continues", "warm pad", "no bass yet", "quiet and intimate"],
     ["hi-hats", "snare", "loud", "sub bass"]),
    ("Bass", 2,  # bars 7-8, S05-S06
     ["a round warm sub bass line enters on the first beat", "the soft kick continues four on the floor",
      "Rhodes chords join the felt piano", "soft shakers", "gentle forward motion", "still restrained"],
     ["hi-hats", "loud", "full groove"]),
    ("Golden Hour Build", 4,  # bars 9-12, S07-S10: dusk into blue hour, the crate, the needle drop
     ["the groove is held back and low-pass filtered, quieter than the drop to come", "soft closed hi-hats enter",
      "a slow white-noise riser and a rising filter sweep build tension across the whole section",
      "anticipation, dusk turning to night"],
     ["full drop", "loud drums", "crash cymbal", "full-range sub bass", "release"]),
    ("Ignition", 2,  # bars 13-14, S11-S12: THE DROP on bar 13 beat 1
     ["the drop: the biggest moment of the track, a full release on the first beat",
      "a deep sub bass impact on the first beat", "the full groove opens up: kick, snare rimshots, shakers, sub bass",
      "a sustained tanpura drone", "wide, warm, glowing, much fuller than the build", "confident but calm"],
     ["vocals", "screaming synth lead", "wobble bass", "dubstep"]),
    ("Him", 4,  # bars 15-18, S13-S14: under his line
     ["the groove thins out to leave room for a spoken voice", "soft kick, sub bass and pads only",
      "no lead melody", "muted Rhodes stabs", "a low tanpura drone in the background", "intimate, focused"],
     ["lead melody", "piano melody", "busy percussion", "loud", "breakdown", "silence"]),
    ("Hand-off", 2,  # bars 19-20, S15: the focus pull
     ["the same light groove continues under a spoken voice", "kick and sub bass", "soft pads",
      "a gentle filter opening up", "no lead melody"],
     ["lead melody", "busy percussion", "loud", "breakdown", "silence", "stop"]),
    ("Her Lift", 2,  # bars 21-22, S16: a Dorian lift as she speaks
     ["a Dorian lift, brighter harmony", "a soft Rhodes counter-melody enters", "the groove continues light under a voice",
      "warm and open"],
     ["busy drums", "loud lead", "breakdown", "silence", "stop"]),
    ("Together", 2,  # bars 23-24, S17
     ["the felt piano melody from the opening returns in full", "full warm groove", "pads and Rhodes together",
      "resolving, uplifting"],
     ["new melody", "aggressive"]),
    ("Final Chord", 2,  # bars 25-26, S18: the title
     ["one final sustained D minor add9 chord on the first beat, ringing out", "drums stop", "piano and pad decay",
      "a soft sub tail", "peaceful ending"],
     ["drums", "new melody", "abrupt ending"]),
]
PLANS = {"v1": V1, "v2": V2}
for _v in PLANS.values():
    assert sum(b for _, b, _, _ in _v) == BARS
    assert [b for _, b, _, _ in _v] == [b for _, b, _, _ in V1]  # the conform relies on the bars, not the names


def section_starts(plan: str = "v2") -> list[tuple[str, int]]:
    """(name, first bar) of each section."""
    out, at = [], 1
    for name, bars, _, _ in PLANS[plan]:
        out.append((name, at))
        at += bars
    return out


def chunk_plan(plan: str = "v2") -> dict:
    """The request body's composition plan (music_v2's chunk form, as filmtools.music_plan.to_chunks writes it)."""
    return {"chunks": [{
        "text": f"[{name}]", "duration_ms": int(round(bars * BAR_S * 1000)),
        "positive_styles": GLOBAL["positive"] + pos, "negative_styles": GLOBAL["negative"] + neg,
        "context_adherence": "high", "conditioning_ref": None, "condition_strength": None,
    } for name, bars, pos, neg in PLANS[plan]]}


def plan_hash(plan: str, seed: int) -> str:
    return hashlib.sha1(json.dumps({"c": chunk_plan(plan), "m": MODEL, "seed": seed}, sort_keys=True).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- gen

def decode(audio: bytes, fmt: str) -> np.ndarray:
    from filmtools.music import decode as _decode
    return _decode(audio, fmt, DURATION)


def gen(plan: str, seed: int, force: bool = False) -> Path:
    import soundfile as sf
    TAKES.mkdir(parents=True, exist_ok=True)
    flac, meta = TAKES / f"{plan}-seed{seed}.flac", TAKES / f"{plan}-seed{seed}.json"
    h = plan_hash(plan, seed)
    if meta.is_file() and flac.is_file():
        if json.loads(meta.read_text()).get("hash") == h:
            print(f"seed {seed}: cached ({flac.name})")
            return flac
        if not force:
            raise SystemExit(f"{flac} was composed from another plan; --force to replace it (spends credits)")
    el = ElevenLabs(credit_log=CREDITS)
    before = el.credits_used()
    try:
        r = el.compose(chunk_plan(plan), model_id=MODEL, output_format="pcm_48000", seed=seed)
        fmt = "pcm_48000"
    except ElevenLabsError as e:
        if e.status != 403:
            raise
        r = el.compose(chunk_plan(plan), model_id=MODEL, output_format="mp3_44100_128", seed=seed)
        fmt = "mp3_44100_128"
    x = decode(r.audio, fmt)
    cost = el.credits_used() - before
    sf.write(str(flac), np.asarray(x, np.float32), SR, subtype="PCM_24")
    meta.write_text(json.dumps({"hash": h, "seed": seed, "model": MODEL, "format": fmt, "request_id": r.request_id,
                                "cost": cost, "seconds": round(len(x) / SR, 3), "planned": DURATION,
                                "plan_version": plan, "sections": section_starts(plan), "plan": chunk_plan(plan)}, indent=1))
    print(f"seed {seed}: {len(x) / SR:.2f} s (planned {DURATION:.2f}), {cost} credits ({fmt}) -> {flac}")
    return flac


def load_take(take: str) -> np.ndarray:
    x, sr = read_wav(TAKES / f"{take}.flac", mono=False)
    if sr != SR:
        raise SystemExit(f"take {take}: {sr} Hz")
    return np.asarray(x if x.ndim == 2 else np.stack([x, x], 1), np.float64)


# ---------------------------------------------------------------- measuring a take's grid

HOP = 256


def track(y: np.ndarray, bpm: float = BPM) -> dict:
    """The take's beats: librosa's tracker (tight, started at the plan's tempo), a straight grid through them
    (filmtools.beats.fit_grid), and that grid's downbeat phase from where the low end is heaviest."""
    import librosa
    from filmtools.beats import LAG, fit_grid

    m = y.mean(axis=1) if y.ndim == 2 else y
    oenv = librosa.onset.onset_strength(y=m.astype(np.float32), sr=SR, hop_length=HOP)
    _, bf = librosa.beat.beat_track(onset_envelope=oenv, sr=SR, hop_length=HOP, start_bpm=bpm, tightness=400,
                                    trim=False)
    beats = librosa.frames_to_time(bf, sr=SR, hop_length=HOP) - LAG * HOP / SR
    grid, period, err = fit_grid(beats, len(m) / SR)
    return {"beats": beats, "grid": grid, "period": period, "err": err, "oenv": oenv}


def low_env(y: np.ndarray, fps: int = 200) -> np.ndarray:
    """The 20-120 Hz band's RMS at `fps` (the kick and the sub), dB."""
    from scipy.signal import butter, sosfiltfilt
    m = y.mean(axis=1) if y.ndim == 2 else y
    lo = sosfiltfilt(butter(4, [20, 120], "band", fs=SR, output="sos"), m)
    hop = SR // fps
    nb = len(lo) // hop
    return 10 * np.log10(np.mean(lo[:nb * hop].reshape(nb, hop) ** 2, axis=1) + 1e-12)


def find_drop(y: np.ndarray, near: float, within: float = 4.0) -> float:
    """The drop's onset: the biggest rise of the low band (over 150 ms against the 600 ms before) within `within`
    seconds of `near`."""
    fps = 200
    e = low_env(y, fps)
    c = np.concatenate([[0.0], np.cumsum(e)])
    i = np.arange(120, len(e) - 30)
    rise = np.full(len(e), -np.inf)
    rise[i] = (c[i + 30] - c[i]) / 30 - (c[i] - c[i - 120]) / 120  # the next 150 ms against the 600 ms before
    lo, hi = max(120, int((near - within) * fps)), min(len(e) - 30, int((near + within) * fps))
    i = lo + int(np.argmax(rise[lo:hi]))
    # walk forward to the first frame that reaches most of the rise: the hit, not the window's centre
    seg = e[i:i + 60]
    j = i + int(np.argmax(seg >= seg.min() + 0.7 * (seg.max() - seg.min())))
    return j / fps


# ---------------------------------------------------------------- conform

def varispeed(x: np.ndarray, ratio: float) -> np.ndarray:
    """x played `ratio` times as fast (ratio > 1 shortens it): a band-limited resample, pitch moving with it."""
    from scipy.signal import resample_poly
    if abs(ratio - 1) < 1e-6:
        return x
    # a rational close enough: 1e-5 relative error over 10 s is 0.1 ms
    from fractions import Fraction
    f = Fraction(ratio).limit_denominator(4000)
    return resample_poly(x, f.denominator, f.numerator, axis=0)


def conform(take: str) -> dict:
    """Map the take onto the grid section by section (see the module doc), then the breath, the drop and the fade."""
    y = load_take(take)
    tr = track(y)
    period = tr["period"]
    grid = tr["grid"]
    # The take's own downbeats: the drop is the anchor (it is where the plan's section 5 starts, and the most
    # recognisable hit in the piece); the downbeat phase is the grid beat nearest it.
    planned_drop = bar_t(DROP_BAR)
    drop = find_drop(y, planned_drop * len(y) / SR / DURATION)
    k_drop = int(np.argmin(np.abs(grid - drop)))
    drop_beat = float(grid[k_drop])
    # beat index of every section's first downbeat in the take: the drop's beat less the beats between, at the take's
    # own (constant) tempo; the drop's beat is bar 13 beat 1
    starts = section_starts()
    src = []
    for _, b in starts:
        k = k_drop + (b - DROP_BAR) * BPB
        t = drop_beat + (k - k_drop) * period
        src.append(t)
    src.append(drop_beat + (BARS + 1 - DROP_BAR) * BPB * period)  # the end of bar 26
    dst = [bar_t(b) for _, b in starts] + [DURATION]
    # Per section: the source span [src_i, src_i+1) varispeeded to the target span. When every section runs at one
    # ratio (within 0.1%: under 2 cents and under 2.5 ms across a section), the whole take is varispeeded once: no
    # seams at all. Otherwise each section is cut 20 ms either side of its downbeat and the pieces meet in equal-gain
    # crossfades (sin^2/cos^2: the two sides are the same recording, so their gains, not their powers, sum to one).
    ratios = [(src[i + 1] - src[i]) / (dst[i + 1] - dst[i]) for i in range(len(starts))]
    one = max(ratios) / min(ratios) - 1 < 1e-3
    out = np.zeros((N + SR, 2))
    segs = []
    if one:
        ratio = (src[-1] - src[0]) / (dst[-1] - dst[0])
        piece = varispeed(y, ratio)
        at = int(round((dst[0] - src[0] / ratio) * SR))  # where the take's sample 0 lands
        lo, hi = max(0, at), min(len(out), at + len(piece))
        out[lo:hi] = piece[lo - at:hi - at]
        ratios = [ratio] * len(starts)
    xf = int(0.020 * SR)
    for i, (name, b) in enumerate(starts):
        s0, s1 = src[i], src[i + 1]
        d0 = dst[i]
        ratio = ratios[i]
        segs.append({"section": name, "bar": b, "take_s": round(s0, 4), "film_s": round(d0, 4),
                     "ratio": round(ratio, 5), "cents": round(1200 * math.log2(ratio), 1)})
        if one:
            continue
        last = i == len(starts) - 1
        a = max(0, int(round(s0 * SR)) - (xf if i else 0))
        z = len(y) if last else min(len(y), int(round(s1 * SR)) + xf)
        piece = varispeed(y[a:z], ratio)
        at = int(round((d0 - (s0 - a / SR) / ratio) * SR))  # sample a lands where s0 maps to d0
        n = len(piece)
        w = np.ones(n)
        k = min(2 * xf, n)
        if i:
            w[:k] = np.sin((np.arange(k) + 0.5) / k * math.pi / 2) ** 2
        if not last:
            w[n - k:] = np.minimum(w[n - k:], np.cos((np.arange(k) + 0.5) / k * math.pi / 2) ** 2)
        lo, hi = max(0, at), min(len(out), at + n)
        out[lo:hi] += (piece * w[:, None])[lo - at:hi - at]
    out = out[:N]
    out = edits(arrange(out))
    # one static gain: the true peak at -1 dBTP (the mix sets the level; this only keeps the file from clipping)
    from filmtools.vochain import true_peak
    tp = max(true_peak(out[:, 0]), true_peak(out[:, 1]))
    gain_db = -1.0 - tp
    out *= 10 ** (gain_db / 20)
    SCORE.mkdir(parents=True, exist_ok=True)
    write_wav(SCORE / "score.wav", out.astype(np.float32), SR)
    rep = {"take": take, "take_tempo_bpm": round(60 / period, 3), "take_grid_error_ms": round(tr["err"] * 1000, 1),
           "take_drop_s": round(drop, 3), "take_drop_beat_s": round(drop_beat, 3),
           "one_ratio": one, "sections": segs, "layers": LAYERS, "edits": EDITS, "gain_db": round(gain_db, 2)}
    rep["check"] = check(out)
    (SCORE / "score.json").write_text(json.dumps(rep, indent=1))
    return rep


# ---------------------------------------------------------------- arrangement layers

# What the takes would not do, added on the grid. Three takes (v1-seed1, v2-seed1, v2-seed2) all held their drums
# back to bar 9 whatever the plan said, and v2-seed1 (the pick) ends on its B-flat groove instead of a last chord.
# So: the soft brushed kick of bars 5-8 and the round sub of bars 7-8 are synthesised here; bars 9-12 (the take's
# groove arriving) are low-pass filtered and opened up as they go, with a riser into the breath, so the drop on bar 13
# is the first time the groove plays full-range; and the take's own opening chord (bars 1-2, D minor over the vinyl)
# returns on bar 25 as the final chord: the groove's B-flat resolves to it (VI -> i) and the reel ends where it began.
# Levels are relative to the take: `ref` is the 20-120 Hz RMS of bars 13-14 (the drop's groove).
D2 = 73.416  # Hz: the key's root, the sub's note (the groove's bass sits on D2 at the drop)
LAYERS = {
    "kick": {"bars": [5, 8], "low_db": -11.0},              # every beat; its low band 11 dB under the drop's
    "brush": {"bars": [5, 8], "beats": [2, 4], "db": -16.0, "pan": 0.25},  # a brush swish, relative to the kick
    "sub": {"bars": [7, 8], "hz": D2, "low_db": -13.0, "duck_db": 6.0},
    "build": {"bars": [9, 12], "lowpass_hz": [320.0, 6500.0], "gain_db": [-5.0, 0.0]},
    "riser": {"from": bar_t(11), "to": bar_t(12, 4), "db": -9.0},  # its last half-second against bar 12's RMS
    "coda": {"bar": 25, "from_bars": [1, 2], "groove_out_s": 0.55, "gain_db": 1.5, "sub_low_db": -15.0},
}


def _band(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    from scipy.signal import butter, sosfiltfilt
    return sosfiltfilt(butter(4, [lo, hi], "band", fs=SR, output="sos"), x, axis=0)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(x, np.float64) ** 2)) + 1e-12)


def _span(t0: float, t1: float) -> slice:
    return slice(int(round(t0 * SR)), int(round(t1 * SR)))


def soft_kick(seed: int = 11) -> np.ndarray:
    """A soft, felt-beater kick: a sine body falling 123 -> 48 Hz, a little tanh warmth, a muffled beater; no click
    above ~1.2 kHz."""
    from scipy.signal import butter, sosfilt
    rng = np.random.default_rng(seed)
    n = int(0.5 * SR)
    t = np.arange(n) / SR
    f = 48 + 75 * np.exp(-t / 0.028)
    body = np.tanh(1.3 * np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t / 0.16)
    felt = sosfilt(butter(2, [200, 900], "band", fs=SR, output="sos"), rng.standard_normal(n)) * np.exp(-t / 0.008)
    y = body + 0.12 * felt / (np.abs(felt).max() + 1e-12)
    y = sosfilt(butter(2, 1200, "low", fs=SR, output="sos"), y)
    y[:24] *= np.linspace(0, 1, 24)
    y[-480:] *= np.linspace(1, 0, 480)
    return y / np.abs(y).max()


def brush(seed: int = 12) -> np.ndarray:
    """A brush swept across a snare head: band-passed noise with a 25 ms swell and a 90 ms tail."""
    from scipy.signal import butter, sosfilt
    rng = np.random.default_rng(seed)
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    y = sosfilt(butter(2, [1500, 7000], "band", fs=SR, output="sos"), rng.standard_normal(n))
    y *= np.minimum(1, t / 0.025) * np.exp(-np.maximum(0, t - 0.025) / 0.09)
    y[-480:] *= np.linspace(1, 0, 480)
    return y / np.abs(y).max()


def _put(bus: np.ndarray, x: np.ndarray, t: float, gain: float = 1.0, pan: float = 0.0) -> None:
    from filmtools.sfx import pan_gains
    a = int(round(t * SR))
    hi = min(len(bus), a + len(x))
    if hi <= a:
        return
    gl, gr = pan_gains(pan)
    bus[a:hi, 0] += x[:hi - a] * gain * gl * math.sqrt(2)
    bus[a:hi, 1] += x[:hi - a] * gain * gr * math.sqrt(2)


def arrange(x: np.ndarray) -> np.ndarray:
    """The conformed take plus LAYERS (see above). Pure: the same take gives the same samples."""
    from filmtools.anime.mix import swept_lowpass
    from filmtools.anime.synth import riser
    L = LAYERS
    x = x.copy()
    opening = x[_span(*(bar_t(b) for b in (L["coda"]["from_bars"][0], L["coda"]["from_bars"][1] + 1)))].copy()
    ref = _rms(_band(x[_span(bar_t(13), bar_t(15))].mean(axis=1), 20, 120))
    add = np.zeros_like(x)
    # the soft kick on every beat of bars 5-8, its low band set against the drop's
    k = soft_kick()
    b0, b1 = L["kick"]["bars"]
    beats = [bar_t(b, q) for b in range(b0, b1 + 1) for q in (1, 2, 3, 4)]
    kb = np.zeros_like(x)
    for t in beats:
        _put(kb, k, t)
    span = _span(bar_t(b0), bar_t(b1 + 1))
    kb *= ref * 10 ** (L["kick"]["low_db"] / 20) / _rms(_band(kb[span].mean(axis=1), 20, 120))
    add += kb
    kick_peak = float(np.abs(kb).max())
    br = brush()
    for b in range(*[L["brush"]["bars"][0], L["brush"]["bars"][1] + 1]):
        for q in L["brush"]["beats"]:
            _put(add, br, bar_t(b, q), kick_peak * 10 ** (L["brush"]["db"] / 20), L["brush"]["pan"])
    # the sub on D2 through bars 7-8, ducked by the kick (a 120 ms recovery after each beat)
    s0, s1 = (bar_t(b) for b in (L["sub"]["bars"][0], L["sub"]["bars"][1] + 1))
    t = np.arange(int(round((s1 - s0) * SR))) / SR
    sub = np.sin(2 * np.pi * L["sub"]["hz"] * t) + 0.12 * np.sin(4 * np.pi * L["sub"]["hz"] * t)
    sub *= np.minimum(1, t / 0.04) * np.minimum(1, (t[-1] - t) / 0.08)
    since = (t + s0 - bar_t(1)) % BEAT_S
    sub *= 1 - (1 - 10 ** (-L["sub"]["duck_db"] / 20)) * np.exp(-since / 0.12)
    sub *= ref * 10 ** (L["sub"]["low_db"] / 20) / _rms(_band(sub, 20, 120))
    add[_span(s0, s1)] += sub[:, None]
    # bars 9-12: the take's groove low-passed and opening up, exponentially, with its gain rising
    f0, f1 = L["build"]["lowpass_hz"]
    g0, g1 = L["build"]["gain_db"]
    sp = _span(bar_t(L["build"]["bars"][0]), bar_t(L["build"]["bars"][1] + 1))
    u = np.linspace(0, 1, sp.stop - sp.start)
    x[sp] = swept_lowpass(x[sp], f0 * (f1 / f0) ** u) * (10 ** ((g0 + (g1 - g0) * u) / 20))[:, None]
    # the riser into the breath: two decorrelated sides, its last half-second set against bar 12's level
    r0, r1 = L["riser"]["from"], L["riser"]["to"]
    rs = np.stack([riser(r1 - r0, seed=21), riser(r1 - r0, seed=22)], axis=1).astype(np.float64)
    end = x[_span(bar_t(12), bar_t(12, 4))]
    rs *= _rms(end) * 10 ** (L["riser"]["db"] / 20) / _rms(rs[-SR // 2:])
    add[_span(r0, r1)] += rs[:_span(r0, r1).stop - _span(r0, r1).start]
    # the coda: the groove's bar-25 downbeat plays, then the groove leaves over a beat; the opening chord rings out
    c = bar_t(L["coda"]["bar"])
    go = int(L["coda"]["groove_out_s"] * SR)
    a = int(round(c * SR))
    x[a:a + go] *= (np.cos((np.arange(go) + 0.5) / go * math.pi / 2) ** 2)[:, None]
    x[a + go:] = 0.0
    n = min(len(opening), len(x) - a)
    add[a:a + n] += opening[:n] * 10 ** (L["coda"]["gain_db"] / 20)
    t = np.arange(len(x) - a) / SR
    tail = np.sin(2 * np.pi * D2 * t) * np.minimum(1, t / 0.3) * np.exp(-t / 2.2)
    tail *= ref * 10 ** (L["coda"]["sub_low_db"] / 20) / _rms(_band(tail[:SR], 20, 120))
    add[a:] += tail[:, None]
    return x + add


# The edits after the conform, in film seconds.
EDITS = {
    "breath": [bar_t(12, 4), bar_t(13)],  # bar 12 beat 4 drops out (f705-719): a breath before the drop
    "breath_fade_s": 0.090,               # the score leaves over this, a short tail not a click
    "drop_open_s": 0.004,                 # and opens hard on 30.0 s
    "fade": [bar_t(26) + 1.5, DURATION],  # the fade to black, f1536-1559: the score leaves with the picture
}


def edits(x: np.ndarray) -> np.ndarray:
    g = np.ones(len(x))
    b0, b1 = (int(round(t * SR)) for t in EDITS["breath"])
    f = int(EDITS["breath_fade_s"] * SR)
    g[b0:b0 + f] = np.cos((np.arange(f) + 0.5) / f * math.pi / 2) ** 2
    o = int(EDITS["drop_open_s"] * SR)
    g[b0 + f:b1 - o] = 0.0
    g[b1 - o:b1] = np.sin((np.arange(o) + 0.5) / o * math.pi / 2) ** 2
    f0, f1 = (int(round(t * SR)) for t in EDITS["fade"])
    g[f0:f1] *= np.cos((np.arange(f1 - f0) + 0.5) / (f1 - f0) * math.pi / 2) ** 2
    g[f1:] = 0.0
    return x * g[:, None]


# ---------------------------------------------------------------- check

def check(x: np.ndarray) -> dict:
    """The conformed score against the picture's grid: its own tracked tempo and grid offset, how many of the exact
    grid's beats have an onset within 30 ms (grid fit, film-beats' measure, over the sounding beats), the drop's
    measured onset against 30.0 s, the low band at each section's first downbeat, loudness and peaks."""
    import librosa
    from filmtools.beats import LAG, grid_fit
    from filmtools.vochain import loudness, true_peak

    m = x.mean(axis=1)
    tr = track(x)
    exact = np.arange(0, DURATION - 1e-9, BEAT_S)
    onsets = librosa.onset.onset_detect(onset_envelope=tr["oenv"], sr=SR, hop_length=HOP, units="time") \
        - LAG * HOP / SR
    rms = librosa.feature.rms(y=m.astype(np.float32), frame_length=2048, hop_length=SR // 100)[0]
    sounding = rms[np.clip((exact * 100).astype(int), 0, len(rms) - 1)] > 10 ** (-40 / 20)
    drums = (exact >= bar_t(5)) & (exact < bar_t(25))  # where the plan has a beat at all
    fit_all = grid_fit(exact, onsets, sounding)
    fit_drums = grid_fit(exact, onsets, sounding & drums)
    # the tracked grid's offset from the exact one, at the beat: positive = late
    off = float(np.median(((tr["grid"] + BEAT_S / 2) % BEAT_S) - BEAT_S / 2))
    drop = find_drop(x, bar_t(DROP_BAR), within=1.0)
    nearest = np.array([np.min(np.abs(onsets - t)) for t in exact[sounding & drums]]) if len(onsets) else np.array([])
    return {
        "tempo_bpm": round(60 / tr["period"], 3), "grid_offset_ms": round(off * 1000, 1),
        "grid_fit": round(fit_all, 3), "grid_fit_drums": round(fit_drums, 3),
        "beat_onset_median_ms": round(float(np.median(nearest)) * 1000, 1) if len(nearest) else None,
        "drop_onset_s": round(drop, 3), "drop_error_ms": round((drop - bar_t(DROP_BAR)) * 1000, 1),
        "lufs": round(loudness(x, SR), 2), "true_peak_dbtp": round(max(true_peak(x[:, 0]), true_peak(x[:, 1])), 2),
        "seconds": round(len(x) / SR, 4), "samples": len(x), "kick_alignment": kick_alignment(x),
    }


def kick_alignment(x: np.ndarray) -> list[dict]:
    """Per section: the kick's (20-150 Hz) onsets against the exact grid's beats. Each beat with a low-band onset
    within 60 ms counts; the signed median error (positive = late) and the share within 10 and 20 ms say whether that
    section's groove sits on the picture's beats. A section with no kick (the morning, the breakdown) has no beats."""
    import librosa
    from filmtools.beats import LAG
    lo = _band(x.mean(axis=1), 20, 150).astype(np.float32)
    hop = 128
    env = librosa.onset.onset_strength(y=lo, sr=SR, hop_length=hop, n_fft=2048, n_mels=32, fmax=400)
    on = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=hop, units="time", backtrack=False) \
        - LAG * hop / SR
    out = []
    starts = section_starts() + [("end", BARS + 1)]
    for (name, b), (_, b2) in zip(starts, starts[1:], strict=False):
        beats = np.arange(bar_t(b), bar_t(b2) - 1e-9, BEAT_S)
        err = []
        for t in beats:
            d = on - t
            d = d[np.abs(d) < 0.060]
            if len(d):
                err.append(float(d[np.argmin(np.abs(d))]))
        e = np.array(err)
        out.append({"section": name, "bars": f"{b}-{b2 - 1}", "beats": len(beats), "kicks": len(e),
                    "median_ms": round(float(np.median(e)) * 1000, 1) if len(e) else None,
                    "within_10ms": round(float(np.mean(np.abs(e) < 0.010)), 2) if len(e) else None,
                    "within_20ms": round(float(np.mean(np.abs(e) < 0.020)), 2) if len(e) else None})
    return out


def plot(x: np.ndarray, png: Path, title: str) -> None:
    """Spectrogram with the bar grid and the sections; the low band and the RMS under it; the average spectrum of
    each section."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import librosa
    import librosa.display

    m = x.mean(axis=1).astype(np.float32)
    fig = plt.figure(figsize=(18, 11))
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 1.2, 2])
    ax = fig.add_subplot(gs[0])
    D = librosa.amplitude_to_db(np.abs(librosa.stft(m, n_fft=4096, hop_length=1024)), ref=np.max)
    librosa.display.specshow(D, sr=SR, hop_length=1024, x_axis="time", y_axis="log", ax=ax, cmap="magma", vmin=-90)
    for b in range(1, BARS + 2):
        ax.axvline(bar_t(b), color="w", alpha=0.25 if (b - 1) % 4 else 0.5, lw=0.6)
    for name, b in section_starts():
        ax.text(bar_t(b) + 0.1, 12000, name, color="w", fontsize=8, rotation=90, va="top")
    ax.set_title(title)
    ax.set_xlim(0, DURATION)
    ax2 = fig.add_subplot(gs[1], sharex=ax)
    t = np.arange(len(low_env(x))) / 200
    ax2.plot(t, low_env(x), lw=0.6, label="20-120 Hz (dB)")
    hop = SR // 100
    nb = len(m) // hop
    r = 20 * np.log10(np.sqrt(np.mean(m[:nb * hop].reshape(nb, hop) ** 2, axis=1)) + 1e-9)
    ax2.plot(np.arange(nb) / 100, r, lw=0.6, label="RMS 10 ms (dBFS)")
    for k in np.arange(0, DURATION, BEAT_S):
        ax2.axvline(k, color="k", alpha=0.06, lw=0.5)
    ax2.axvline(bar_t(DROP_BAR), color="r", lw=0.8)
    ax2.set_ylim(-90, 0)
    ax2.legend(loc="lower right", fontsize=8)
    ax3 = fig.add_subplot(gs[2])
    f = np.fft.rfftfreq(8192, 1 / SR)
    starts = section_starts() + [("end", BARS + 1)]
    for (name, b), (_, b2) in zip(starts, starts[1:]):
        seg = m[int(bar_t(b) * SR):int(bar_t(b2) * SR)]
        nf = len(seg) // 8192
        if not nf:
            continue
        P = np.mean(np.abs(np.fft.rfft(seg[:nf * 8192].reshape(nf, 8192) * np.hanning(8192), axis=1)) ** 2, axis=0)
        ax3.semilogx(f[1:], 10 * np.log10(P[1:] + 1e-12), lw=0.8, label=name)
    ax3.set_xlim(20, 20000)
    ax3.set_xlabel("Hz")
    ax3.set_ylabel("dB (average power)")
    ax3.legend(fontsize=7, ncol=5)
    fig.tight_layout()
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, dpi=90)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen", help="compose one take (spends credits)")
    g.add_argument("--plan", default="v2", choices=sorted(PLANS))
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--force", action="store_true")
    c = sub.add_parser("conform", help="a take onto the grid -> audio/score/score.wav")
    c.add_argument("--take", required=True, help="e.g. v2-seed1")
    t = sub.add_parser("track", help="a take's own tempo, grid and drop, before any conform")
    t.add_argument("--take", required=True)
    sub.add_parser("check", help="audio/score/score.wav against the grid, with a plot")
    pl = sub.add_parser("plan", help="print the request's composition plan")
    pl.add_argument("--plan", default="v2", choices=sorted(PLANS))
    a = ap.parse_args(argv)
    if a.cmd == "gen":
        gen(a.plan, a.seed, a.force)
    elif a.cmd == "plan":
        print(json.dumps(chunk_plan(a.plan), indent=1))
    elif a.cmd == "track":
        y = load_take(a.take)
        tr = track(y)
        drop = find_drop(y, bar_t(DROP_BAR) * len(y) / SR / DURATION)
        print(json.dumps({"seconds": round(len(y) / SR, 3), "tempo_bpm": round(60 / tr["period"], 3),
                          "grid_error_ms": round(tr["err"] * 1000, 1), "first_beat_s": round(float(tr["grid"][0]), 3),
                          "drop_s": round(drop, 3)}, indent=1))
        plot(y, TAKES / f"{a.take}.png", f"take {a.take} (as composed)")
    elif a.cmd == "conform":
        rep = conform(a.take)
        print(json.dumps(rep, indent=1))
        x, _ = read_wav(SCORE / "score.wav", mono=False)
        plot(x, SCORE / "check.png", f"score.wav ({a.take}, conformed)")
    else:
        x, _ = read_wav(SCORE / "score.wav", mono=False)
        print(json.dumps(check(np.asarray(x, np.float64)), indent=1))
        plot(x, SCORE / "check.png", "score.wav")


if __name__ == "__main__":
    main()
