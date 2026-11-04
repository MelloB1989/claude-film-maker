"""The `performance` spec kind (WP4): an actor's lines (timing, mood, gaze targets, gestures, expressions, nods) and
moves (walk to, turn to), converged by `film-ue apply` through perf.solve / perf.compose (/ perf.lock_eyes); a second
plan is empty once the composed face animation carries the spec's fingerprint.

    kind: performance                 # schemas/performance.schema.json; examples/unreal/performance/
    version: 1
    name: intro
    sequence: /Game/Films/demo/Seq_Intro
    actor: Presenter
    camera: CAM_A
    lines:
      - {id: l1, audio: /home/ue/Audio/intro_l1.wav, mood: warm,
         gaze: [{at_s: 0, target: camera}, {at_s: 2.4, target: guest, scan: face}]}

The planner is the bridge's own pure perfkit.spec.plan, loaded from this checkout (no engine): it plans offline with
`--state`. The state comes from perf.state (positions, clip lengths, audio analysis, solve keys, the fingerprint).
WAVs named by `audio` must already be on the box (client.push).
"""
from __future__ import annotations

import sys
from pathlib import Path

from .spec import register_kind

_FMB = Path(__file__).resolve().parents[3] / "unreal" / "fmbridge"


def perfkit():
    """The bridge's engine-free perfkit package from this checkout (None when unreal/ is not here)."""
    if not (_FMB / "perfkit" / "__init__.py").exists():
        return None
    if str(_FMB) not in sys.path:
        sys.path.insert(0, str(_FMB))
    import perfkit as pk  # noqa: E402
    from perfkit import spec as _  # noqa: F401  (load the submodule)
    return pk


def plan_performance(spec: dict, state: dict | None) -> list:
    """perf.solve for lines whose audio/mood changed, then perf.compose (and perf.lock_eyes) unless converged."""
    pk = perfkit()
    if pk is None or state is None:
        return [{"op": "perf.apply", "args": {"spec": spec}, "timeout": 3600,
                 "why": "no state to plan against: converge on the bridge"}]
    steps = pk.spec.plan(spec, state)
    for s in steps:
        s["timeout"] = 1800 if s["op"] in ("perf.solve", "perf.lock_eyes") else 900
    return steps


def describe_performance(ue, spec: dict) -> dict:
    return ue.call("perf.state", spec={k: v for k, v in spec.items() if not k.startswith("_")})


register_kind("performance", plan_performance, describe_performance, order=65,
              doc="An actor's performance (WP4): lines with mood, gaze, gestures, expressions and nods, plus walks and "
                  "turns, composed into a living face and body in a sequence.")
