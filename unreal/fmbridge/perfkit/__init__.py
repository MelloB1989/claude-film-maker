"""perfkit: performance synthesis in pure Python (no `unreal`, no numpy): what makes a face and a head look alive.

The bridge's `perf.*` and `anim.*` ops write what this package computes into animation curves and Sequencer tracks;
the same code runs on the client (`film-ue perf plan`) and in the unit tests, so every number can be checked without
an editor. Everything is in seconds and degrees; curves are `{name: (times, values)}`.

    curves      sampling, easing (min-jerk, asymmetric), overshoot-settle moves, smooth 1/f noise, key reduction
    rig         the MetaHuman face's curve names (verified in the 5.8.4 source) and the head curves
    head        organic head motion: gaze-driven turns with eye/head coordination, nods, tilts, micro-motion, and
                `naturalize` for a solver's robotic head curves
    eyes        gaze in the head: saccades (main sequence), vestibulo-ocular counter-roll, fixational darts, face
                scanning, vergence, eye-look curves
    blinks      spontaneous blinks (log-normal intervals), gaze-evoked and phrase-end blinks, asymmetric shape
    expressions expression presets (Duchenne smile, brow flash, concern, ...) as layered, asymmetric, living events;
                mood baselines and emotion blending
    audio       a WAV's loudness envelope: pauses and stressed syllables for emphasis, with the stdlib only
    body        gestures (timing to the stroke), idles with variation, walk-to / turn-to plans
    spec        the PERFORMANCE spec: validate and compile to a plan of curves and sections
    metrics     numeric naturalness checks (robotic holds, blink statistics, asymmetry, head velocity profiles)
    svg         a curve plot as SVG text, for Claude to look at without matplotlib
"""
from __future__ import annotations

__all__ = ["curves", "rig", "head", "eyes", "blinks", "expressions", "audio", "body", "spec", "metrics", "svg"]
