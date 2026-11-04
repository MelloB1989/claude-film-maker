"""The `qa` spec kind (WP10): what to check, declared; `film-ue apply qa.yaml` runs the checks every time (they
change nothing, so every step is `always`) and the results land in each op's report.

    kind: qa
    version: 1
    name: s010-review
    out_dir: /srv/qa/s010              # on the box
    review:                            # qa.review: stills through the cut + every check, review.json + review.png
      sequence: /Game/Seq/S010
      per_shot: 2
      subjects: [Ada]
      expect: {Ada: {size: [MS, MCU]}, image: {stops: [-2, 0]}}
      ignore: [Floor, Walls]
      reference_dir: /srv/qa/s010_ref  # optional: compare each frame with yesterday's
    turntables:                        # view.turntable: an actor from all round
      - {target: Ada, views: 8, isolate: true}
    penetration:                       # qa.penetration: garments from N views
      - {label: Ada, views: 6}
    floating: {ignore: [Pendant]}      # qa.floating over the set
    overlaps: {ignore: [Floor, Walls]} # qa.overlaps over the set

Planning is pure (no I/O): the steps are the op calls, in that order.
"""
from __future__ import annotations


def plan(spec: dict, state=None) -> list:
    """The checks a qa spec asks for, as op steps (each `always`: a check never converges away)."""
    out_dir = spec["out_dir"].rstrip("/")
    steps = []
    rv = spec.get("review")
    if rv:
        if not (rv.get("sequence") or rv.get("camera")):
            raise ValueError(f"qa {spec.get('name')}: review needs sequence or camera")
        args = {"out_dir": f"{out_dir}/review", **{k: v for k, v in rv.items()}}
        steps.append({"op": "qa.review", "args": args, "why": "review " + (rv.get("sequence") or rv.get("camera")),
                      "always": True, "timeout": 1800})
    for tt in spec.get("turntables", []):
        steps.append({"op": "view.turntable", "args": {"out_dir": f"{out_dir}/turntable_{tt['target']}", **tt},
                      "why": f"turntable of {tt['target']}", "always": True, "timeout": 600})
    for pe in spec.get("penetration", []):
        steps.append({"op": "qa.penetration", "args": {"out_dir": f"{out_dir}/penetration_{pe['label']}", **pe},
                      "why": f"garments of {pe['label']}", "always": True, "timeout": 600})
    if "floating" in spec:
        steps.append({"op": "qa.floating", "args": dict(spec["floating"] or {}), "why": "props resting", "always": True})
    if "overlaps" in spec:
        steps.append({"op": "qa.overlaps", "args": dict(spec["overlaps"] or {}), "why": "props apart", "always": True})
    if "snapshot" in spec:
        steps.append({"op": "qa.snapshot", "args": {"out": spec["snapshot"]}, "why": "state for later diffs",
                      "always": True})
    if not steps:
        raise ValueError(f"qa {spec.get('name')}: nothing to check (give review, turntables, penetration, floating, "
                         "overlaps or snapshot)")
    return steps


def describe(ue, spec):
    """Checks have no state to converge: always None (plan runs every check)."""
    return None


SPEC_KINDS = [{"name": "qa", "plan": plan, "describe": describe, "order": 95,
               "doc": "QA checks to run (review, turntables, penetration, floating, overlaps): they change nothing"}]
