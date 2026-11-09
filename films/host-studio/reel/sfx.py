"""The karma reel's sound effects (PLAN.md §2 "Sound design", task R5): the palette and the cue sheet, on the
picture's frames, rendered into stems.

    cd tools && python ../films/host-studio/reel/sfx.py gen       # the generated beds (ElevenLabs, cached; credits)
    cd tools && python ../films/host-studio/reel/sfx.py render    # the cue sheet -> audio/sfx/{beds,fx,sfx}.wav
    cd tools && python ../films/host-studio/reel/sfx.py sheet     # print the cue sheet (frame, time, sound, shot)

The palette is procedural except the one outdoor bed no synth does well, birds through a closed window, which
ElevenLabs sound generation makes once (prompt and seed in GENERATED; the take is committed in audio/sfx/gen/, so a
render needs no key). Everything else is synthesised here from seeded noise and sines: the same code always writes
the same samples. Every sound is mono, 48 kHz, peaking at -1 dBFS before its cue's gain; a
one-shot's hit (its first transient) is at its sample 0 unless it says otherwise, so a cue's frame is where it lands.

Two stems, so the mix can treat them apart: `beds` (room tone, outside, the halo's hum, the vinyl's crackle) and `fx`
(the one-shots: macro foley, the ignition, the switches). `sfx.wav` is their sum. 65.000 s, 48 kHz stereo 24-bit,
frame 0 at sample 0 (a frame is 2000 samples).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "tools"))

import shots as S  # noqa: E402
from filmtools.wav import SR, read_wav, write_wav  # noqa: E402

FPS = S.FPS
SPF = SR // FPS            # 2000 samples a frame
TOTAL = S.SHOTS[-1].end    # 1560 frames
N = TOTAL * SPF            # 3 120 000 samples, 65.0 s
SFX = HERE / "audio" / "sfx"
GEN = SFX / "gen"
CREDITS = HERE / "audio" / "credits.log"


def f2s(f: float) -> float:
    return f / FPS


# ---------------------------------------------------------------- building blocks

def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _t(dur: float) -> np.ndarray:
    return np.arange(int(round(dur * SR))) / SR


def bp(x: np.ndarray, lo: float, hi: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, [lo, min(hi, SR / 2 - 200)], "band", fs=SR, output="sos"), x)


def lp(x: np.ndarray, f: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x: np.ndarray, f: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def norm(x: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    m = float(np.abs(x).max()) or 1.0
    return x / m * 10 ** (peak_db / 20)


def fades(x: np.ndarray, a: float = 0.001, b: float = 0.02) -> np.ndarray:
    x = np.array(x, np.float64)
    na, nb = min(len(x), int(a * SR)), min(len(x), int(b * SR))
    if na:
        x[:na] *= np.linspace(0, 1, na)
    if nb:
        x[-nb:] *= np.linspace(1, 0, nb)
    return x


def modes(freqs, decays, amps, dur: float, beat: float = 0.0, seed: int = 0) -> np.ndarray:
    """A struck object: decaying sine modes (each split by `beat` Hz into a slowly beating pair, a coin's shimmer),
    and a 1 ms strike of noise."""
    t = _t(dur)
    y = np.zeros(len(t))
    for f, d, a in zip(freqs, decays, amps, strict=True):
        ph = _rng(seed + int(f)).uniform(0, 2 * np.pi, 2)
        s = np.sin(2 * np.pi * f * t + ph[0])
        if beat:
            s = 0.5 * (s + np.sin(2 * np.pi * (f + beat) * t + ph[1]))
        y += a * s * np.exp(-t / d)
    y += 0.3 * hp(_rng(seed).standard_normal(len(t)), 3000) * np.exp(-t / 0.001)
    return fades(y, 0.0003, min(0.2, dur / 4))


def room(x: np.ndarray, rt60: float = 0.35, wet_db: float = -16.0, seed: int = 3) -> np.ndarray:
    """A small room around a dry sound (the voice chain's plate, short and dark)."""
    from filmtools.vochain import plate
    x = np.concatenate([x, np.zeros(int(rt60 * 1.5 * SR))])
    return plate(x, SR, rt60=rt60, predelay_ms=6, lo=200, hi=6000, wet_db=wet_db, seed=seed)


# ---------------------------------------------------------------- the palette: beds

def room_tone(dur: float, seed: int = 1) -> np.ndarray:
    """A quiet treated room: soft brown noise under 500 Hz, a breath of air above, a slow drift."""
    r = _rng(seed)
    n = int(dur * SR)
    brown = np.cumsum(r.standard_normal(n))
    brown = hp(brown, 25, 2)
    body = lp(brown, 500)
    air = bp(r.standard_normal(n), 1500, 7000) * 0.02
    t = np.arange(n) / SR
    drift = 1 + 0.15 * np.sin(2 * np.pi * 0.07 * t + r.uniform(0, 6))
    return norm(fades((body / np.abs(body).max() + air) * drift, 0.5, 0.5))


def city(dur: float, seed: int = 2) -> np.ndarray:
    """A far-off city at night through glass: a low wash 50-300 Hz breathing slowly, a car passing now and then."""
    r = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    wash = bp(np.cumsum(r.standard_normal(n)), 50, 300) * (1 + 0.25 * np.sin(2 * np.pi * 0.05 * t))
    wash /= np.abs(wash).max()
    cars = np.zeros(n)
    for c in r.uniform(0, dur, int(dur / 9)):
        env = np.exp(-((t - c) / 1.6) ** 2)
        cars += bp(r.standard_normal(n), 120, 900) * env
    cars /= np.abs(cars).max() + 1e-12
    return norm(fades(wash + 0.35 * cars, 0.5, 0.5))


def crickets(dur: float, seed: int = 3) -> np.ndarray:
    """Field crickets far off through glass: each insect a 4.3-4.9 kHz carrier pulsed in chirps of 3-4 pulses (about
    30 pulses a second) every 0.4-0.7 s, its own rate drifting; five of them at different distances, softened by the
    glass (a low-pass at 6 kHz) and a little distance (a short plate)."""
    r = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for k in range(5):
        fc = r.uniform(4300, 4900)
        period = r.uniform(0.40, 0.70)
        pulses = int(r.integers(3, 5))
        gap = 1 / r.uniform(26, 34)
        env = np.zeros(n)
        start = r.uniform(0, period)
        while start < dur:
            for p in range(pulses):
                c = start + p * gap
                env += np.exp(-((t - c - 0.008) / 0.006) ** 2)
            start += period * r.uniform(0.92, 1.08)
        dist = 10 ** (-r.uniform(0, 12) / 20)
        y += dist * np.sin(2 * np.pi * fc * t + r.uniform(0, 6)) * env
    y = lp(y, 6000, 2)
    from filmtools.vochain import plate
    y = plate(y, SR, rt60=0.9, predelay_ms=20, lo=1500, hi=8000, wet_db=-8, seed=seed)[:n]
    return norm(fades(y, 0.5, 0.5))


def halo_hum(dur: float, seed: int = 4) -> np.ndarray:
    """The sign's halo: a neon transformer's 100 Hz hum (twice the 50 Hz mains) with its harmonics, a faint gas buzz
    above, and a slow unsteady flutter."""
    r = _rng(seed)
    t = _t(dur)
    flutter = 1 + 0.04 * lp(r.standard_normal(len(t)), 3) / 0.05
    y = sum(a * np.sin(2 * np.pi * 100 * k * t + r.uniform(0, 6)) for k, a in
            [(1, 1.0), (2, 0.45), (3, 0.30), (4, 0.12), (5, 0.08), (7, 0.04)])
    buzz = hp(np.sign(np.sin(2 * np.pi * 100 * t)) * 0.5 + 0.2 * r.standard_normal(len(t)), 1800) * 0.03
    return norm(fades((y + buzz) * flutter, 0.05, 0.05))


def crackle(dur: float, seed: int = 5) -> np.ndarray:
    """A played record's surface: a hiss band, a rain of small ticks (about 30 a second) and a few pops, and the
    groove's 0.55 Hz turn (33 1/3 rpm) as a faint lift every revolution."""
    r = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    hiss = bp(r.standard_normal(n), 2000, 9000) * 0.06
    ticks = np.zeros(n)
    for i in r.integers(0, n, int(30 * dur)):
        ticks[i] = r.choice([-1, 1]) * r.uniform(0.1, 0.5)
    for i in r.integers(0, n, int(1.2 * dur)):
        ticks[i] = r.choice([-1, 1]) * r.uniform(0.7, 1.0)
    ticks = bp(ticks, 900, 9000) * 6
    turn = 1 + 0.2 * np.sin(2 * np.pi * (100 / 3 / 60) * t)
    return norm(fades((hiss + ticks) * turn, 0.01, 0.2))


# ---------------------------------------------------------------- the palette: one-shots

def clock_tick(tock: bool = False, seed: int = 6) -> np.ndarray:
    """A quiet wall clock's escapement: a dry click and a little wooden ring; the tock a fifth lower."""
    t = _t(0.12)
    f = 1900 * (2 / 3 if tock else 1)
    click = bp(_rng(seed + tock).standard_normal(len(t)), 2000, 7000) * np.exp(-t / 0.0015)
    wood = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.018) * 0.4
    return norm(fades(click + wood, 0.0002, 0.03))


def curtain_air(seed: int = 7) -> np.ndarray:
    """A sheer curtain breathing in a draught: a slow swell of soft air, 2.2 s."""
    t = _t(2.2)
    y = bp(_rng(seed).standard_normal(len(t)), 250, 2500) * np.sin(np.pi * t / t[-1]) ** 2
    y *= 1 + 0.3 * lp(_rng(seed + 1).standard_normal(len(t)), 6) / 0.03
    return norm(fades(y, 0.05, 0.2))


def cloth_swipe(dur: float = 1.4, seed: int = 8) -> np.ndarray:
    """A fingertip drawn along book cloth: fibre grains (bandpassed noise chopped at 40-70 Hz) under a soft arc."""
    r = _rng(seed)
    t = _t(dur)
    noise = bp(r.standard_normal(len(t)), 900, 6000)
    grains = 0.55 + 0.45 * np.abs(np.sin(2 * np.pi * np.cumsum(r.uniform(40, 70, len(t))) / SR))
    env = np.minimum(1, t / 0.08) * np.exp(-np.maximum(0, t - 0.4) / 0.5)
    return norm(fades(noise * grains * env, 0.02, 0.1))


def paper(kind: str = "flick", seed: int = 9) -> np.ndarray:
    """Paper: `flick`, a polaroid nudged on the shelf (a snap and a short flutter); `settle`, a calendar page
    dropping back (a few soft slaps and a slide)."""
    r = _rng(seed)
    if kind == "flick":
        t = _t(0.35)
        snap = bp(r.standard_normal(len(t)), 1500, 7000) * np.exp(-t / 0.006)
        flutter = bp(r.standard_normal(len(t)), 600, 4000) * np.exp(-((t - 0.05) / 0.035) ** 2) * 0.4
        return norm(fades(snap + flutter, 0.0003, 0.05))
    t = _t(0.9)
    y = np.zeros(len(t))
    for d, a in [(0.0, 1.0), (0.11, 0.5), (0.19, 0.35)]:
        y += a * bp(r.standard_normal(len(t)), 400, 5000) * np.where(t >= d, np.exp(-(t - d) / 0.02), 0)
    slide = bp(r.standard_normal(len(t)), 1200, 6000) * np.exp(-((t - 0.35) / 0.18) ** 2) * 0.25
    return norm(fades(y + slide, 0.0003, 0.1))


def glass_tick() -> np.ndarray:
    """A fingernail tick on a frosted acrylic block: high, bright, short."""
    return norm(modes([2650, 4870, 7330, 9900], [0.20, 0.12, 0.08, 0.05], [1, 0.6, 0.4, 0.25], 0.6, seed=10))


def coin_ring() -> np.ndarray:
    """A brass coin set down on walnut: a coin's inharmonic modes, each a beating pair, ringing ~1.5 s."""
    f0 = 1850
    return norm(modes([f0 * k for k in (1, 2.32, 4.25, 6.63)], [1.4, 0.8, 0.45, 0.25], [1, 0.7, 0.45, 0.3], 2.4,
                      beat=3.0, seed=11))


def brass_tink() -> np.ndarray:
    """The little brass pickaxe touched against its rack: a small, high tink."""
    return norm(modes([2900, 7830, 15080], [0.40, 0.18, 0.08], [1, 0.5, 0.25], 0.9, seed=12))


def servo(seed: int = 13) -> np.ndarray:
    """A gimbal's servos settling: a small motor whine gliding 330 -> 470 -> 400 Hz with gear grain, 0.9 s."""
    r = _rng(seed)
    t = _t(0.9)
    f = 330 + 140 * np.sin(np.pi * np.minimum(1, t / 0.6)) - 70 * np.maximum(0, t - 0.6) / 0.3
    ph = 2 * np.pi * np.cumsum(f) / SR
    whine = sum(a * np.sin(k * ph) for k, a in [(1, 1), (2, 0.5), (3, 0.35), (5, 0.15)])
    grain = 1 + 0.35 * np.sin(2 * np.pi * 85 * t) + 0.1 * r.standard_normal(len(t))
    env = np.sin(np.pi * t / t[-1]) ** 0.6
    return norm(fades(bp(whine * grain * env, 250, 6000), 0.02, 0.08))


def blip() -> np.ndarray:
    """A status LED's soft electronic blip: 2.4 kHz for 45 ms."""
    t = _t(0.06)
    return norm(fades(np.sin(2 * np.pi * 2400 * t) * np.exp(-t / 0.03), 0.003, 0.01))


def keystroke(seed: int = 14) -> np.ndarray:
    """A low-profile mechanical key: the press (click and plastic thock), the release 70 ms later, quieter."""
    r = _rng(seed)
    t = _t(0.16)

    def hit(at: float, a: float) -> np.ndarray:
        on = t >= at
        u = np.where(on, t - at, 0)
        click = bp(r.standard_normal(len(t)), 2500, 9000) * np.exp(-u / 0.0012) * on
        thock = bp(r.standard_normal(len(t)), 350, 1600) * np.exp(-u / 0.012) * on
        return a * (0.6 * click + thock)
    return norm(fades(hit(0, 1.0) + hit(0.07, 0.4), 0.0002, 0.02))


def cursor_tick() -> np.ndarray:
    """The terminal cursor's blink, given a sound: a tiny dry tick."""
    t = _t(0.03)
    return norm(fades(np.sin(2 * np.pi * 4000 * t) * np.exp(-t / 0.002), 0.0002, 0.005))


def needle_drop(seed: int = 15) -> np.ndarray:
    """The stylus landing in the run-in groove: a soft low thump through the tonearm, a tick, and the first turn of
    the groove's crackle."""
    t = _t(0.62)
    thump = np.sin(2 * np.pi * 62 * t) * np.exp(-t / 0.03)
    tick = bp(_rng(seed).standard_normal(len(t)), 1500, 8000) * np.exp(-t / 0.002) * 0.6
    run = crackle(0.62, seed=seed + 1) * np.minimum(1, t / 0.05) * 0.35
    return norm(fades(thump + tick + run, 0.0003, 0.05))


def relay(kind: str = "letter", seed: int = 16) -> np.ndarray:
    """Switch gear. `letter`: the halo's relay pulling in for one letter, a metallic clack, a body thud, and the
    neon catching (a 150 ms bloom of 100 Hz buzz). `downlight`: a contactor's heavier double chunk with a little
    ring. `key`: a dimmer's soft thunk as his key light comes up."""
    r = _rng(seed)
    t = _t(0.5)
    if kind == "letter":
        clack = bp(r.standard_normal(len(t)), 1500, 6000) * np.exp(-t / 0.004)
        body = np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.035) * 0.6
        bloom = sum(a * np.sin(2 * np.pi * 100 * k * t) for k, a in [(1, 1), (2, 0.6), (3, 0.4), (5, 0.2)])
        bloom = bloom * np.minimum(1, t / 0.02) * np.exp(-t / 0.15) * 0.35
        zap = hp(r.standard_normal(len(t)), 3000) * np.exp(-((t - 0.012) / 0.006) ** 2) * 0.2
        return norm(fades(clack + body + bloom + zap, 0.0002, 0.05))
    if kind == "downlight":
        y = np.zeros(len(t))
        for d, a in [(0.0, 1.0), (0.012, 0.6)]:
            on = t >= d
            u = np.where(on, t - d, 0)
            y += a * on * (bp(r.standard_normal(len(t)), 1200, 7000) * np.exp(-u / 0.003)
                           + 0.8 * np.sin(2 * np.pi * 120 * u) * np.exp(-u / 0.03)
                           + 0.15 * np.sin(2 * np.pi * 930 * u) * np.exp(-u / 0.08))
        return norm(fades(y, 0.0002, 0.05))
    thunk = np.sin(2 * np.pi * 90 * t) * np.exp(-t / 0.06) + 0.3 * lp(r.standard_normal(len(t)), 900) \
        * np.exp(-t / 0.01)
    return norm(fades(thunk, 0.0005, 0.08))


def sub_whoomph() -> np.ndarray:
    """The drop's sub: a sine falling 72 -> 30 Hz through the floor (the anime pipeline's subdrop)."""
    from filmtools.anime.synth import subdrop
    return norm(subdrop(72.0, 30.0, 2.4).astype(np.float64))


def electric_swell(seed: int = 17) -> np.ndarray:
    """The halo's power coming up across the ignition: the hum's harmonics and a gas hiss swelling over 2.4 s, its
    hit (sample 0) the first letter."""
    r = _rng(seed)
    t = _t(2.4)
    hum = sum(a * np.sin(2 * np.pi * 100 * k * t) for k, a in [(1, 1), (2, 0.7), (3, 0.5), (4, 0.3), (6, 0.2)])
    hiss = bp(r.standard_normal(len(t)), 2500, 10000) * 0.25
    env = np.minimum(1, t / 0.08) * (0.55 + 0.45 * np.minimum(1, t / 1.0)) * np.exp(-np.maximum(0, t - 1.2) / 0.6)
    return norm(fades((hum + hiss) * env, 0.003, 0.2))


def cloth(seed: int = 18) -> np.ndarray:
    """A small movement in a shirt or a jacket: a soft rustle, 0.7 s."""
    r = _rng(seed)
    t = _t(0.7)
    y = bp(r.standard_normal(len(t)), 300, 3500) * np.sin(np.pi * t / t[-1]) ** 1.5
    y *= 0.6 + 0.4 * np.abs(lp(r.standard_normal(len(t)), 25)) / 0.05
    return norm(fades(y, 0.02, 0.1))


# ---------------------------------------------------------------- the generated beds (ElevenLabs)

# Prompts and seeds sent as they are; each made once, 10 s, as a seamless loop, then tiled by the render. (A crickets
# bed was asked for too, "faintly ... through a closed window": it came back at -74 dBFS, room noise and no crickets,
# so the crickets are synthesised below instead.)
GENERATED = {
    "birds": {"prompt": "Gentle songbirds outside on a calm sunny morning, heard from inside a quiet room through a "
                        "closed window, soft and distant, a few sparrows and a bulbul, no music, no voices, no wind",
              "duration": 10.0, "influence": 0.55, "seed": 4101},
}


def gen(force: bool = False) -> None:
    from filmtools.elevenlabs import ElevenLabs
    from filmtools.sfxlib import to_wav48
    GEN.mkdir(parents=True, exist_ok=True)
    el = ElevenLabs(credit_log=CREDITS)
    for name, g in GENERATED.items():
        wav, meta = GEN / f"{name}.wav", GEN / f"{name}.json"
        if wav.is_file() and meta.is_file() and json.loads(meta.read_text()).get("request") == g and not force:
            print(f"{name}: cached")
            continue
        r = el.sound(g["prompt"], duration_seconds=g["duration"], prompt_influence=g["influence"], loop=True,
                     seed=g["seed"])
        y = to_wav48(r.audio, r.output_format, g["duration"])
        write_wav(wav, y.astype(np.float32))
        meta.write_text(json.dumps({"request": g, "request_id": r.request_id, "seconds": round(len(y) / SR, 3)},
                                   indent=1))
        print(f"{name}: {len(y) / SR:.2f} s")


def generated(name: str) -> np.ndarray:
    p = GEN / f"{name}.wav"
    if not p.is_file():
        raise SystemExit(f"{p} is missing: run `sfx.py gen` (ElevenLabs) first")
    y, sr = read_wav(p)
    assert sr == SR
    return norm(np.asarray(y, np.float64))


# ---------------------------------------------------------------- the cue sheet

# Beds: (sound, first frame, last frame (exclusive), gain dB, [[frame, dB], ...] keys over the bed, pan or None for
# a stereo pair of two decorrelated takes). Keys are linear in dB between them and held past the ends.
BEDS = [
    ("room_tone", 0, TOTAL, -30, [[0, 0], [1536, 0], [1560, -12]], None),
    # outside: birds through the day and the golden hour, gone by the blue hour; crickets and the far city from dusk
    ("birds", 0, 700, -20, [[0, -2], [240, 0], [480, -3], [600, -12], [690, -40]], None),
    ("crickets", 480, TOTAL, -27, [[480, -40], [600, -10], [700, 0], [780, -3], [840, -8], [1536, -8], [1560, -40]],
     None),
    ("city", 520, TOTAL, -34, [[520, -40], [680, 0], [840, -4], [1536, -4], [1560, -40]], None),
    # the record: the needle lands on bar 12 beat 4 (f705) and plays its surface through the breath and under the
    # drop, then eases away under the room's night
    ("crackle", 705, 960, -26, [[705, 0], [720, 0], [780, -6], [900, -12], [960, -30]], None),
    # the halo's hum from the first letter (f720), one step up per letter, then a held bed; the last thing to fade
    ("halo_hum", 720, TOTAL, -33, [[720, -14], [735, -10], [750, -7], [765, -4], [772, -1], [790, 0], [1440, 0],
                                   [1542, 0], [1560, -40]], 0.0),
]

# One-shots: (frame, sound, gain dB, pan -1..1, shot, what). The hit lands on the frame.
CUES = [
    # PLAN v2: no foley for single objects (the picture no longer points at any); the room speaks instead.
    # V03 the window and the olive (bars 7-8): the sheers breathe as the crane rises past the tree
    (378, "curtain_air", -24, 0.5, "V03", "the sheers breathe"),
    # V05 the room (bar 12): the needle drops on beat 4, the breath (the crackle bed carries it)
    (705, "needle_drop", -19, 0.25, "V05", "the stylus lands on the turntable in the wide; the breath before the drop"),
    # S11 the drop (bar 13): the sub, the power swelling, a relay clack per letter (k a r m a on 1, 2, 3, 4, 4&)
    (720, "sub_whoomph", -10, 0.0, "S11", "the drop's sub"),
    (720, "electric_swell", -24, 0.0, "S11", "the halo's power coming up"),
    *[(f, f"relay_{i}", -19, p, "S11", f"letter {i + 1} of k a r m a lights")
      for i, (f, p) in enumerate([(720, -0.4), (735, -0.2), (750, 0.0), (765, 0.2), (772, 0.4)])],
    # S12 the studio comes on (bar 14): four downlight groups, one per beat, across the room
    *[(780 + 15 * i, "downlight", -19, p, "S12", "a downlight group's contactor")
      for i, p in enumerate([-0.5, -0.15, 0.2, 0.5])],
    # S13 him (bar 17 beat 3): his key light comes up with a soft thunk as he looks up
    (990, "key_thunk", -22, 0.15, "S13", "his key light"),
    (992, "cloth_a", -30, 0.1, "S13", "his head comes up"),
    # the presenters: light cloth movement only (his turn to her after L2, the glance between them in S17)
    (1125, "cloth_b", -29, -0.15, "S15", "he turns his head to her"),
    (1380, "cloth_c", -30, -0.2, "S17", "the glance between them"),
]


def palette() -> dict[str, np.ndarray]:
    """Every one-shot of the cue sheet, made once. (The beds are made at their length in render.)"""
    return {
        "tick": clock_tick(False), "tock": clock_tick(True), "curtain_air": curtain_air(),
        "cloth_swipe": cloth_swipe(), "paper_flick": paper("flick"), "glass_tick": glass_tick(),
        "coin_ring": room(coin_ring(), 0.3, -18), "brass_tink": room(brass_tink(), 0.3, -18), "servo": servo(),
        "blip": blip(), "key1": keystroke(14), "key2": keystroke(24), "key3": keystroke(34), "cursor": cursor_tick(),
        "paper_settle": paper("settle"), "needle_drop": needle_drop(), "sub_whoomph": sub_whoomph(),
        "electric_swell": electric_swell(),
        **{f"relay_{i}": room(relay("letter", 16 + i), 0.5, -14, seed=30 + i) for i in range(5)},
        "downlight": room(relay("downlight"), 0.6, -14), "key_thunk": room(relay("key"), 0.4, -16),
        "cloth_a": cloth(18), "cloth_b": cloth(28), "cloth_c": cloth(38),
    }


def bed(name: str, dur: float, seed: int) -> np.ndarray:
    if name in GENERATED:
        from filmtools.sfx import tile
        return norm(tile(generated(name), int(round(dur * SR)), SR))
    return {"room_tone": room_tone, "city": city, "crickets": crickets, "halo_hum": halo_hum,
            "crackle": crackle}[name](dur, seed)


def keyed(keys: list, f0: int, f1: int) -> np.ndarray:
    """Per-sample dB over [f0, f1) frames from [frame, dB] keys."""
    k = sorted(keys)
    s = np.arange(f0 * SPF, f1 * SPF)
    return np.interp(s, [a * SPF for a, _ in k], [b for _, b in k])


def render() -> dict:
    from filmtools.sfx import pan_gains
    beds = np.zeros((N, 2))
    for name, f0, f1, gain, keys, pan in BEDS:
        dur = (f1 - f0) / FPS
        g = 10 ** ((gain + keyed(keys, f0, f1)) / 20)
        a, z = f0 * SPF, f1 * SPF
        if pan is None:  # a stereo pair: two takes (two seeds, or the generated loop and itself a third in)
            if name in GENERATED:
                left = bed(name, dur, 0)
                right = np.roll(left, len(left) // 3)
            else:
                left, right = bed(name, dur, 101), bed(name, dur, 202)
            beds[a:z, 0] += left[:z - a] * g
            beds[a:z, 1] += right[:z - a] * g
        else:
            x = bed(name, dur, 101)[:z - a] * g
            gl, gr = pan_gains(pan)
            beds[a:z, 0] += x * gl * math.sqrt(2)
            beds[a:z, 1] += x * gr * math.sqrt(2)
    fx = np.zeros((N, 2))
    pal = palette()
    for f, name, gain, pan, _, _ in CUES:
        x = pal[name] * 10 ** (gain / 20)
        a = int(round(f * SPF))
        hi = min(N, a + len(x))
        gl, gr = pan_gains(pan)
        fx[a:hi, 0] += x[:hi - a] * gl * math.sqrt(2)
        fx[a:hi, 1] += x[:hi - a] * gr * math.sqrt(2)
    SFX.mkdir(parents=True, exist_ok=True)
    for name, x in (("beds", beds), ("fx", fx), ("sfx", beds + fx)):
        write_wav(SFX / f"{name}.wav", x.astype(np.float32))
    (SFX / "cues.json").write_text(json.dumps(sheet(), indent=1))
    from filmtools.vochain import loudness
    return {k: {"lufs": round(loudness(v, SR), 1), "peak_dbfs": round(20 * np.log10(np.abs(v).max() + 1e-12), 1)}
            for k, v in (("beds", beds), ("fx", fx), ("sfx", beds + fx))}


def sheet() -> dict:
    """The cue sheet as data: what lands on which frame (for the edit, R6's captions and anyone syncing to it)."""
    return {"fps": FPS, "frames": TOTAL, "beds": [
        {"sound": n, "from_frame": f0, "to_frame": f1, "gain_db": g, "keys": k} for n, f0, f1, g, k, _ in BEDS],
        "cues": [{"frame": f, "t": round(f2s(f), 4), "sound": n, "gain_db": g, "pan": p, "shot": s, "what": w}
                 for f, n, g, p, s, w in sorted(CUES, key=lambda c: c[0])]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen", help="the ElevenLabs beds (spends credits; cached)")
    g.add_argument("--force", action="store_true")
    sub.add_parser("render")
    sub.add_parser("sheet")
    a = ap.parse_args(argv)
    if a.cmd == "gen":
        gen(a.force)
    elif a.cmd == "render":
        print(json.dumps(render(), indent=1))
    else:
        for c in sheet()["cues"]:
            print(f"f{c['frame']:<7g} {c['t']:7.3f}s  {c['shot']}  {c['sound']:<15} {c['what']}")


if __name__ == "__main__":
    main()
