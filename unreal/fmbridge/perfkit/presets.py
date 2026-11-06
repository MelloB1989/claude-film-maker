"""Natural-motion presets: the numbers a presenter's face and body run on, in one place, with where they come from.
`perf.face preset=<name>` takes the face half (anything given explicitly wins); the body half is anim.body_life's
arguments. docs/unreal/research/blinks-head-stability.md has the sources in full.

Rules every preset keeps (round 5: what read as robotic or wrong to the operator):
- the head never moves with a blink (blink_head still) and the speech solve's head is not kept (solver_head
  replace): a blink is the lids and a 1-5 deg eyeball dip, never the head (Collewijn et al. 1985);
- nothing periodic: blinks log-normal (CV >= 0.3), breaths vary ~20% in period and ~25% in depth (Tobin 1988:
  21% / 33%), micro-motion is 1/f noise, channels never share a phase;
- small: a held head drifts 0.3-0.6 deg; a breath lifts the clavicles ~1 deg and the chest a few mm; weight shifts
  every 6-16 s, 1-2 cm; sway content under 0.5 Hz (quiet standing: median ~0.33 Hz, Pinsky/Prieto data).

| preset            | blinks/min    | head micro | breath     | beat nods | use                                  |
|-------------------|---------------|------------|------------|-----------|--------------------------------------|
| presenter_calm    | talk ~23      | 0.35 deg   | 12/min     | 1 in 2    | to the lens, measured delivery       |
| presenter_lively  | talk ~23      | 0.5 deg    | 15/min     | every one | energetic host                       |
| listener          | listen ~17    | 0.3 deg    | 13/min     | none      | the other face in a two-shot         |
| still_portrait    | calm ~12      | 0.2 deg    | 12/min     | none      | a held close-up, a reaction hold     |

Blink rates: Bentivoglio et al. 1997 (rest ~17, conversation ~26, reading ~4.5/min); Doughty 2001 (conversation
10.5-32.5/min, 95% CI). Blink shape: close 70-100 ms, open ~2x slower (Evinger 1991; Trutoiu et al. 2011).
"""
from __future__ import annotations

PRESETS = {
    "presenter_calm": {
        "face": {"blink_state": "talk", "solver_head": "replace", "blink_head": "still", "energy": 0.9,
                 "head": {"micro_deg": 0.35, "breath_deg": 0.2, "breath_hz": 0.2, "speech_gain": 0.8, "gain": 0.9},
                 "beat_every": 2, "brow_chance": 0.45},
        "body": {"state": "calm", "breath_deg": 0.5, "clavicle_deg": 0.8, "shift_cm": 1.0, "breath_cv": 0.2},
    },
    "presenter_lively": {
        "face": {"blink_state": "talk", "solver_head": "replace", "blink_head": "still", "energy": 1.15,
                 "head": {"micro_deg": 0.5, "breath_deg": 0.25, "breath_hz": 0.25, "speech_gain": 1.1},
                 "beat_every": 1, "brow_chance": 0.6},
        "body": {"state": "talk", "breath_deg": 0.6, "clavicle_deg": 1.0, "shift_cm": 1.5, "breath_cv": 0.2},
    },
    "listener": {
        "face": {"blink_state": "listen", "solver_head": "replace", "blink_head": "still", "energy": 0.8,
                 "head": {"micro_deg": 0.3, "breath_deg": 0.2, "breath_hz": 0.22, "speech_gain": 0.0},
                 "beat_every": 0, "brow_chance": 0.3},
        "body": {"state": "listen", "breath_deg": 0.5, "clavicle_deg": 0.8, "shift_cm": 1.2, "breath_cv": 0.22},
    },
    "still_portrait": {
        "face": {"blink_state": "calm", "solver_head": "replace", "blink_head": "still", "energy": 0.7,
                 "head": {"micro_deg": 0.2, "breath_deg": 0.15, "breath_hz": 0.2, "speech_gain": 0.5},
                 "beat_every": 0, "brow_chance": 0.2},
        "body": {"state": "calm", "breath_deg": 0.4, "clavicle_deg": 0.6, "shift_cm": 0.6, "breath_cv": 0.18},
    },
}


def face_args(name: str, given: dict) -> dict:
    """perf.face's arguments with preset `name` filled in under what is `given` (given wins; a given "head" style
    is merged over the preset's). Raises ValueError naming the presets."""
    if name not in PRESETS:
        raise ValueError(f"preset {name!r}: one of {', '.join(sorted(PRESETS))}")
    p = PRESETS[name]["face"]
    out = {k: v for k, v in p.items() if k != "head"}
    out.update({k: v for k, v in given.items() if v is not None})
    out["head"] = {**p["head"], **(given.get("head") or {})}
    return out
