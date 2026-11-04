"""Expression layers on a MetaHuman face: named presets as curve recipes, events with a living envelope, mood
baselines that blend line to line, brow lifts on emphasis, and a mix that keeps a talking mouth's lip-sync.

An expression is never a switch: it rises fast (attack), peaks, relaxes a little while held (sustain), drifts a few
percent (alive), and falls slower than it rose (release). The two sides of a face differ: one side leads by tens of
milliseconds and is a little stronger (`asym`). In a real (Duchenne) smile the cheeks lift and the eyes narrow a beat
after the mouth corners; a polite smile moves the mouth alone.

Preset values are fractions of each control's full range (0..1). Every curve name is checked against rig.RAW by the
unit tests.
"""
from __future__ import annotations

import random

from . import curves as C
from .rig import MOUTH, PREFIX

# name: {raw curve (without the L/R suffix when "*"): (weight, delay_s)}; a "*" name is applied to both sides
PRESETS = {
    "smile": {"mouthCornerPull*": (0.6, 0.0), "eyeCheekRaise*": (0.5, 0.08), "eyeSquintInner*": (0.15, 0.1),
              "noseNasolabialDeepen*": (0.2, 0.05), "mouthDimple*": (0.1, 0.0)},
    "smile_soft": {"mouthCornerPull*": (0.35, 0.0), "mouthDimple*": (0.08, 0.0)},
    "grin": {"mouthCornerPull*": (0.85, 0.0), "eyeCheekRaise*": (0.7, 0.06), "eyeSquintInner*": (0.25, 0.08),
             "mouthStretch*": (0.2, 0.0), "mouthUpperLipRaise*": (0.15, 0.03), "jawOpen": (0.08, 0.0),
             "noseNasolabialDeepen*": (0.35, 0.04)},
    "smirk": {"mouthCornerPullL": (0.45, 0.0), "mouthDimpleL": (0.25, 0.0), "eyeCheekRaiseL": (0.2, 0.08),
              "mouthCornerPullR": (0.05, 0.05)},
    "brow_raise": {"browRaiseIn*": (0.5, 0.0), "browRaiseOuter*": (0.55, 0.01), "eyeWiden*": (0.12, 0.02)},
    "brow_flash": {"browRaiseIn*": (0.45, 0.0), "browRaiseOuter*": (0.5, 0.0)},
    "concern": {"browRaiseIn*": (0.5, 0.0), "browLateral*": (0.3, 0.02), "mouthCornerDepress*": (0.12, 0.05),
                "eyeSquintInner*": (0.1, 0.05)},
    "sad": {"browRaiseIn*": (0.55, 0.0), "browLateral*": (0.2, 0.0), "mouthCornerDepress*": (0.35, 0.05),
            "jawChinRaiseD*": (0.25, 0.08), "eyeSquintInner*": (0.1, 0.0)},
    "angry": {"browDown*": (0.6, 0.0), "browLateral*": (0.4, 0.0), "eyeSquintInner*": (0.3, 0.03),
              "mouthLipsPress*": (0.3, 0.05), "noseWrinkle*": (0.15, 0.05), "jawClench*": (0.2, 0.05)},
    "surprise": {"browRaiseIn*": (0.7, 0.0), "browRaiseOuter*": (0.8, 0.0), "eyeWiden*": (0.5, 0.0),
                 "jawOpen": (0.22, 0.03), "mouthStretch*": (0.08, 0.03)},
    "fear": {"browRaiseIn*": (0.6, 0.0), "browLateral*": (0.4, 0.0), "eyeWiden*": (0.6, 0.0),
             "mouthStretch*": (0.35, 0.04), "jawOpen": (0.1, 0.04)},
    "disgust": {"noseWrinkle*": (0.6, 0.0), "mouthUpperLipRaise*": (0.5, 0.03), "browDown*": (0.3, 0.0),
                "eyeSquintInner*": (0.3, 0.03), "eyeCheekRaise*": (0.2, 0.05)},
    "contempt": {"mouthCornerPullL": (0.3, 0.0), "mouthDimpleL": (0.35, 0.0), "eyeSquintInnerL": (0.1, 0.05)},
    "thinking": {"browDownL": (0.2, 0.0), "browRaiseOuterR": (0.3, 0.0), "mouthLipsPress*": (0.15, 0.05),
                 "eyeSquintInner*": (0.15, 0.03), "mouthLeft": (0.12, 0.08)},
    "skeptical": {"browRaiseOuterL": (0.45, 0.0), "browDownR": (0.25, 0.0), "eyeSquintInnerR": (0.2, 0.03),
                  "mouthCornerPullR": (0.15, 0.06)},
    "squint": {"eyeSquintInner*": (0.5, 0.0), "eyeCheekRaise*": (0.2, 0.03)},
    "lip_press": {"mouthLipsPress*": (0.45, 0.0), "jawChinRaiseU*": (0.15, 0.03)},
    "wince": {"eyeSquintInner*": (0.6, 0.0), "eyeBlink*": (0.35, 0.0), "noseWrinkle*": (0.35, 0.02),
              "mouthStretch*": (0.3, 0.02), "browDown*": (0.35, 0.0)},
    "pout": {"mouthLipsPurseU*": (0.3, 0.0), "mouthLipsPurseD*": (0.35, 0.0), "jawChinRaiseD*": (0.4, 0.0)},
}

# a mood is a quiet baseline expression (and a speech-solver mood): {mood: [(preset, intensity)]}
MOODS = {
    "neutral": [],
    "calm": [("smile_soft", 0.08)],
    "warm": [("smile", 0.22)],
    "happy": [("smile", 0.4)],
    "joy": [("grin", 0.45), ("brow_raise", 0.1)],
    "confident": [("smile_soft", 0.15), ("squint", 0.08)],
    "excited": [("smile", 0.45), ("brow_raise", 0.18)],
    "sad": [("sad", 0.4)],
    "concerned": [("concern", 0.35)],
    "angry": [("angry", 0.35)],
    "surprised": [("surprise", 0.3)],
    "fearful": [("fear", 0.35)],
    "thoughtful": [("thinking", 0.3)],
    "skeptical": [("skeptical", 0.3)],
    "disgusted": [("disgust", 0.3)],
    "bored": [("lip_press", 0.1)],
    "playful": [("smirk", 0.3), ("brow_raise", 0.1)],
    "confused": [("skeptical", 0.25), ("concern", 0.15)],
}

# the speech solver's mood for each (unreal.AudioDrivenAnimationMood; verified in
# Engine/Plugins/Animation/AudioDrivenAnimation/StreamingADA/Source/SpeechAnimationSolver/Public/SpeechAnimationSolverTypes.h:13-29)
SOLVER_MOOD = {
    "neutral": "NEUTRAL", "calm": "NEUTRAL", "warm": "HAPPINESS", "happy": "HAPPINESS", "joy": "HAPPINESS",
    "confident": "CONFIDENCE", "excited": "EXCITEMENT", "sad": "SADNESS", "concerned": "SADNESS", "angry": "ANGER",
    "surprised": "SURPRISE", "fearful": "FEAR", "thoughtful": "NEUTRAL", "skeptical": "CONFUSION",
    "disgusted": "DISGUST", "bored": "BOREDOM", "playful": "PLAYFULNESS", "confused": "CONFUSION",
}


def expand(preset: str | dict) -> dict:
    """A preset (name or {raw: weight | (weight, delay)}) as {full curve name: (weight, delay_s)}, both sides
    filled in for "*" names."""
    if isinstance(preset, str):
        if preset not in PRESETS:
            import difflib
            near = difflib.get_close_matches(preset, list(PRESETS), n=3)
            raise ValueError(f"no expression {preset!r}" + (f"; did you mean {', '.join(near)}?" if near else "")
                             + f" (presets: {', '.join(sorted(PRESETS))})")
        recipe = PRESETS[preset]
    else:
        recipe = preset
    out = {}
    for name, w in recipe.items():
        w = (float(w), 0.0) if isinstance(w, (int, float)) else (float(w[0]), float(w[1]))
        raw = name[len(PREFIX):] if name.startswith(PREFIX) else name
        for n in ([raw[:-1] + "L", raw[:-1] + "R"] if raw.endswith("*") else [raw]):
            out[PREFIX + n] = w
    return out


def side_of(curve: str) -> str:
    """"L", "R" or "" (centre) for a full curve name (a trailing L/R, or L/R before a final U/D/C phase letter)."""
    raw = curve[len(PREFIX):]
    if raw.endswith(("L", "R")) and not raw.endswith(("Left", "Right")):
        return raw[-1]
    for suf in ("U", "D"):
        if raw.endswith(("L" + suf, "R" + suf)):
            return raw[-2]
    return ""


class Event:
    """One expression from `t` to `until` (s) at `intensity` (0..1): `attack_s`, `release_s`, `sustain` (the share
    held after the peak), `asym` (-1..1, + = the character's left side stronger and earlier), `alive` (the size of
    the slow drift while held)."""

    __slots__ = ("preset", "t", "until", "intensity", "attack_s", "release_s", "sustain", "asym", "alive", "lead_s")

    def __init__(self, preset, t, until, intensity=0.6, attack_s=0.25, release_s=0.45, sustain=0.85, asym=0.0,
                 alive=0.05, lead_s=None):
        self.preset, self.t, self.until = preset, float(t), max(float(t), float(until))
        self.intensity, self.attack_s, self.release_s = float(intensity), max(0.03, attack_s), max(0.05, release_s)
        self.sustain, self.asym, self.alive = sustain, max(-1.0, min(1.0, asym)), alive
        self.lead_s = lead_s

    def envelope(self, t: float) -> float:
        u = t - self.t
        if u <= 0 or t >= self.until + self.release_s:
            return 0.0
        rise = C.skewed(u / self.attack_s, 0.4)
        held = self.until - self.t
        # after the peak it relaxes toward `sustain` over the hold
        relax = 1.0 - (1.0 - self.sustain) * C.smoothstep((u - self.attack_s) / max(0.3, held - self.attack_s))
        fall = 1.0 - C.skewed((t - self.until) / self.release_s, 0.55) if t > self.until else 1.0
        return rise * relax * fall


def render(events: list, t0: float, t1: float, rate: float = 30.0, seed: int = 0, speech=None,
           mouth_mix: float = 0.5) -> dict:
    """The events as curves {full name: (times, values)} on a t0..t1 grid. `speech` (t -> loudness 0..1) scales
    the mouth region by `mouth_mix` while the mouth is talking, so a smile does not fight the lip-sync."""
    times = C.grid(t0, t1, rate)
    rnd = random.Random(seed)
    acc: dict = {}
    for k, e in enumerate(events):
        recipe = expand(e.preset)
        lead = e.lead_s if e.lead_s is not None else rnd.uniform(0.0, 0.05)
        noise = C.Noise(seed * 31 + k, base_hz=0.35, octaves=2)
        gain = {"L": 1.0 + 0.3 * e.asym, "R": 1.0 - 0.3 * e.asym, "": 1.0}
        # the stronger side also leads
        delay_side = {"L": 0.0 if e.asym >= 0 else lead, "R": lead if e.asym >= 0 else 0.0, "": lead * 0.5}
        for name, (w, delay) in recipe.items():
            side = side_of(name)
            col = acc.setdefault(name, [0.0] * len(times))
            d = delay + delay_side[side]
            for i, t in enumerate(times):
                env = e.envelope(t - d)
                if env:
                    col[i] += e.intensity * w * gain[side] * env * (1.0 + e.alive * noise.at(t))
    if speech is not None and mouth_mix != 1.0:
        loud = [max(0.0, min(1.0, speech(t))) for t in times]
        for name, col in acc.items():
            if name in MOUTH:
                acc[name] = [v * (1.0 - (1.0 - mouth_mix) * min(1.0, 3.0 * l)) for v, l in zip(col, loud)]
    return {n: (list(times), [max(0.0, min(1.0, v)) for v in col]) for n, col in acc.items()}


def mood_events(spans: list, blend_s: float = 0.6, asym: float | None = None, seed: int = 0) -> list:
    """Baseline events for mood spans [{"t0", "t1", "mood", "intensity" (1), "asym"}]: each mood's presets held over
    its span, cross-fading over `blend_s` into the next. `asym` None gives each span a small seeded asymmetry."""
    rnd = random.Random(seed + 7)
    out = []
    for sp in spans:
        mood = sp.get("mood", "neutral")
        if mood not in MOODS:
            import difflib
            near = difflib.get_close_matches(mood, list(MOODS), n=3)
            raise ValueError(f"no mood {mood!r}" + (f"; did you mean {', '.join(near)}?" if near else "")
                             + f" (moods: {', '.join(sorted(MOODS))})")
        k = float(sp.get("intensity", 1.0))
        a = sp.get("asym", asym if asym is not None else rnd.uniform(-0.25, 0.25))
        for preset, inten in MOODS[mood]:
            out.append(Event(preset, sp["t0"] - blend_s / 2, sp["t1"] - blend_s / 2, intensity=inten * k,
                             attack_s=blend_s, release_s=blend_s, sustain=0.95, asym=a, alive=0.08,
                             lead_s=rnd.uniform(0.0, 0.06)))
    return out


def brow_events(emphasis: list, seed: int = 0, chance: float = 0.55, intensity: float = 0.45) -> list:
    """Brow flashes on stressed words: `emphasis` [t] or [(t, strength)]; a flash on about `chance` of them (the
    strongest first), starting just before the word, each a little asymmetric."""
    rnd = random.Random(seed)
    out = []
    for e in emphasis:
        t, k = (e, 1.0) if isinstance(e, (int, float)) else (e[0], e[1])
        if rnd.random() < chance * (0.6 + 0.4 * k):
            out.append(Event("brow_flash", t - rnd.uniform(0.08, 0.15), t + rnd.uniform(0.1, 0.3),
                             intensity=intensity * (0.6 + 0.4 * k) * rnd.uniform(0.85, 1.15), attack_s=0.12,
                             release_s=0.35, sustain=0.8, asym=rnd.uniform(-0.4, 0.4)))
    return out


def swallow(t: float) -> dict:
    """A swallow at `t`: the four neck phases in turn (neckSwallowPh1..4), ~0.6 s; returns curves."""
    out = {}
    for i in range(4):
        a = t + i * 0.12
        out[f"{PREFIX}neckSwallowPh{i + 1}"] = ([a - 0.01, a, a + 0.12, a + 0.24, a + 0.25], [0.0, 0.0, 1.0, 0.0, 0.0])
    return out
