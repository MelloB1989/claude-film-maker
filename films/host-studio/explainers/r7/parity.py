"""Editor vs offline parity (agent-13; the orchestrator's rule, 08 Nov): the arm the sequence actually plays must be the
arm the rows passed. A stale layer (an additive or a track keyed to an old body) moved her editor hands 7-12 cm off the
body gesturekit solved while every offline row passed.

    python3 r7/parity.py EDITOR.json OFFLINE.json [--span A-B]... [--json OUT]

EDITOR: the editor dump (agent-06's: frames [{f, p: {bone: [x, y, z]}}] on the SEQUENCE's 24 fps, the actor frame x
fwd, y the presenter's right, z up, cm). OFFLINE: r7/arm_track.py's dump for her (30 fps), or for him the box's own
kit/arm_track.json from body --perform (his skeleton never leaves the box). Frames are matched by TIME (each dump's
fps, else --editor-fps 24 / --offline-fps 30), the offline track interpolated. Matching frame numbers across the two
rates read 44 cm on box D's dump that agreed to 0.4 cm.

Row qa.editor_offline_parity_cm: the max over the matched frames of the largest distance of any wrist or finger joint
head between the two, <= 1.0 cm. Numbers only, no mesh: safe to send off the box.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

LINE_CM = 1.0
HAND = [f"hand_{s}" for s in "lr"] + [f"{f}_{j}_{s}" for s in "lr" for f in ("thumb", "index", "middle", "ring", "pinky")
                                      for j in ("01", "02", "03")]


def frames(d, fps):
    fr = d["frames"] if isinstance(d, dict) else d
    fps = float(d.get("fps", fps)) if isinstance(d, dict) else fps
    return {int(f["f"]): f["p"] for f in fr}, fps


def at(B, fps, t, bone):
    """the offline track's bone at time t (linear between its frames)."""
    x = t * fps
    i = int(math.floor(x + 1e-9))
    u = x - i
    if i not in B or bone not in B[i]:
        return None
    if u < 1e-6 or i + 1 not in B:
        return B[i][bone]
    a, b = B[i][bone], B[i + 1][bone]
    return [p + (q - p) * u for p, q in zip(a, b)]


def _rel(P, b):
    """bone b from its side's shoulder (the upperarm head): a breath layer on the spine/clavicles carries the whole
    arm with it, which is not a different arm."""
    s = b[-1]
    sh = P.get("upperarm_" + s)
    return None if sh is None or P.get(b) is None else [x - y for x, y in zip(P[b], sh)]


def parity(ed, off, spans=None, ed_fps=24.0, off_fps=30.0, seq_fps=24.0, rel=False):
    """editor frames at their own rate (the sequence's, 24) vs the offline track (30), matched by TIME; spans are
    sequence frames at seq_fps."""
    (A, ed_fps), (B, off_fps) = frames(ed, ed_fps), frames(off, off_fps)
    common = sorted(f for f in A if (not spans or any(a / seq_fps - 1e-6 <= f / ed_fps < (b + 1) / seq_fps - 1e-6
                                                       for a, b in spans))
                    and at(B, off_fps, f / ed_fps, "hand_r") is not None)
    worst, per_bone, per_frame = 0.0, {}, []
    for f in common:
        fm, fb = 0.0, ""
        for b in HAND:
            q = at(B, off_fps, f / ed_fps, b)
            e = A[f].get(b)
            if rel and q is not None and e is not None:
                sq, se = at(B, off_fps, f / ed_fps, "upperarm_" + b[-1]), A[f].get("upperarm_" + b[-1])
                q, e = (None, None) if sq is None or se is None else ([x - y for x, y in zip(q, sq)], _rel(A[f], b))
            if e is not None and q is not None:
                d = math.dist(e, q)
                per_bone[b] = max(per_bone.get(b, 0.0), d)
                if d > fm:
                    fm, fb = d, b
        per_frame.append((fm, f, fb))
    per_frame.sort(reverse=True)
    if per_frame:
        worst = per_frame[0][0]
    vals = sorted(x[0] for x in per_frame)
    p50 = vals[len(vals) // 2] if vals else float("nan")
    return {"frames": len(common), "bones": sum(1 for b in HAND if b in per_bone),
            "max_cm": round(worst, 3) if common else float("nan"), "p50_cm": round(p50, 3),
            "over_line_frac": round(sum(1 for v in vals if v > LINE_CM) / len(vals), 3) if vals else float("nan"),
            "worst": [{"f": f, "bone": b, "cm": round(v, 2)} for v, f, b in per_frame[:8]],
            "worst_bone": {b: round(v, 2) for b, v in sorted(per_bone.items(), key=lambda kv: -kv[1])[:6]}}


def row(rep):
    v = rep["max_cm"]
    return {"qa.editor_offline_parity_cm": {"value": v, "op": "<=", "line": LINE_CM, "unit": "cm",
                                            "pass": None if v != v else v <= LINE_CM,
                                            "what": "max over matched frames of the largest wrist/finger joint distance "
                                                    "between the editor dump and the offline/box track (a stale layer "
                                                    "fails it)"}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("editor")
    ap.add_argument("offline")
    ap.add_argument("--span", action="append", default=[], help="SEQUENCE frames A-B at --seq-fps (repeatable)")
    ap.add_argument("--editor-fps", type=float, default=24.0, help="the editor dump's frame rate if it carries no fps")
    ap.add_argument("--offline-fps", type=float, default=30.0, help="the offline track's, if it carries no fps")
    ap.add_argument("--seq-fps", type=float, default=24.0)
    ap.add_argument("--shoulder", action="store_true",
                    help="measure the hands from their shoulder (upperarm head): a breath layer on the spine/clavicles "
                         "(the orchestrator kept life, 08 Nov) carries the arm without changing it")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    spans = [tuple(int(x) for x in s.split("-")) for s in a.span] or None
    rep = parity(json.loads(Path(a.editor).read_text()), json.loads(Path(a.offline).read_text()), spans,
                 a.editor_fps, a.offline_fps, a.seq_fps, a.shoulder)
    r = row(rep)
    k, v = next(iter(r.items()))
    print(f"{k}  {v['value']} cm (<= {LINE_CM})  {'ok' if v['pass'] else 'n/a' if v['pass'] is None else 'FAIL'}  "
          f"frames {rep['frames']}, bones {rep['bones']}, p50 {rep['p50_cm']}, over-line {rep['over_line_frac']}")
    print("worst frames:", ", ".join(f"f{w['f']} {w['bone']} {w['cm']}" for w in rep["worst"]))
    if a.json:
        Path(a.json).write_text(json.dumps({"rows": r, "report": rep}, indent=1))


if __name__ == "__main__":
    main()
