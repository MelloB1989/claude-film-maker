"""The Rain Ferry's spoken lines for lip-sync (blender/lib/vrm_anim.py Performance.say): each line's reading in romaji
(data/dialogue.json has them in kanji, which the core cannot read) and its timing from data/dialogue_timing.json (film
seconds, fitted to the finished mix).

    from rf import speech
    speech.say(perf, "L01")                    # Shinza's "I want to be strong." where the mix has it
    speech.say(perf, "L11", energy=1.4)        # the charge's shout, wide open

Inner lines (L01, L02: his thoughts over the walk) are heard but not said: `say` leaves the mouth shut for them unless
`inner=True`.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
# how each line is said (data/dialogue.json's ja), mora by mora
READINGS = {
    "L01": "tsuyoku naritai.",
    "L02": "dare yori mo.",
    "L03": "baasan. mukougishi e watashite kure.",
    "L04": "ame no hi wa, watasanai yo.",
    "L05": "mukougishi ni kawaoni ga iru to kiita.",
    "L06": "soitsu wo kitte, ore ga tenka ichi ni naru.",
    "L07": "kawaoni nara, mou shinda yo.",
    "L08": "... yonjuunen mae ni ne.",
    "L09": "nara... anta de ii.",
    "L10": "wakai nee.",
    "L11": "uooooo!",
    "L12": "tsuyosa tte no wa ne, kitta kazu ja nai yo.",
    "L13": "... jaa, nan da.",
    "L14": "nori na.",
    "L15": "ame wa, yanda yo.",
}
INNER = {"L01", "L02"}
# how hard each is said (vrm_anim's energy: how wide the mouth opens)
ENERGY = {"L06": 1.15, "L09": 0.85, "L10": 0.75, "L11": 1.5, "L13": 0.8, "L14": 0.9}


def timing() -> dict:
    """{line id: (start, end)} in film seconds."""
    with open(DATA / "dialogue_timing.json") as f:
        return {d["id"]: (float(d["start"]), float(d["end"])) for d in json.load(f)}


def line(line_id: str) -> dict:
    """A line: who says it, when (film seconds), its reading and whether it is a thought."""
    with open(DATA / "dialogue_timing.json") as f:
        d = next((d for d in json.load(f) if d["id"] == line_id), None)
    if d is None:
        raise KeyError(f"no line {line_id} in data/dialogue_timing.json")
    return dict(who=d["who"], start=float(d["start"]), end=float(d["end"]), reading=READINGS[line_id],
                inner=line_id in INNER)


def say(perf, line_id: str, *, inner: bool = False, energy: float | None = None, **kw) -> bool:
    """Lip-sync `line_id` on a Performance where the mix has it. A thought (INNER) is left unsaid unless `inner`.
    Returns whether it was keyed."""
    ln = line(line_id)
    if ln["inner"] and not inner:
        return False
    perf.say(ln["start"], ln["end"], ln["reading"], energy=ENERGY.get(line_id, 1.0) if energy is None else energy, **kw)
    return True
