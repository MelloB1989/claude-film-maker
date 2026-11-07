"""Are her hands in the PICTURE? (round 7, agent-10; the orchestrator on side A: the gestures happened below the MCU
frame, hands in frame in ~2 of 12 frames.) Offline, numbers only: the performance (agent-01's Performer + this
timing) projected into each presenter shot's camera (edl/<film>.json; panel shots use <CAM>_L) with setplan's own
pinhole (setplan.cameras / project).

Per camera, over the speaking frames of its shots:
- hands_in_frame_frac: frames with at least one hand FULLY in frame (wrist + the four fingertips + the thumb tip
  inside the frame by MARGIN). The orchestrator's bars: >= 0.6 MCU / MCU_L, >= 0.3 CU, ~1.0 WIDE.
- apex_in_frame: of the gestures whose apex falls in that camera's shots, how many have the gesturing hand in frame
  at the apex (the strokes are what the viewer must see).
- bottom_z_cm: where the frame's bottom edge cuts her gesture plane (the vertical through her sternum point, ~25 cm
  in front of the shoulders), so the hands must be above it: the target for the pose heights.

    python gesture/framing.py netflix [--no-timing] [--t0 0 --t1 8.17]
"""
import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPL = HERE.parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402
import setplan as SP  # noqa: E402

FPS = 30
MARGIN = 0.01  # of the frame
TIPS = ("index_03", "middle_03", "ring_03", "pinky_03", "thumb_03")
BARS = {"CAM_MCU": 0.6, "CAM_MCU_L": 0.6, "CAM_CU": 0.3, "CAM_WIDE": 0.95}
MARK = SP.MARK  # actor frame = studio minus the chair mark (y not flipped: setplan's and perform's cams agree)


def studio(p):
    return (p[0] + MARK[0], p[1] + MARK[1], p[2] + MARK[2])


def in_frame(cam, pts) -> bool:
    for p in pts:
        u, v, z = SP.project(cam, studio(p))
        if z <= 0 or not (MARGIN <= u <= 1 - MARGIN and MARGIN <= v <= 1 - MARGIN):
            return False
    return True


def bottom_z(cam, p_ref) -> float:
    """z (actor, cm) where the frame's bottom edge (v = 1) crosses the vertical through p_ref (actor)."""
    lo, hi = p_ref[2] - 80.0, p_ref[2] + 60.0
    for _ in range(40):
        mid = (lo + hi) / 2
        _, v, _ = SP.project(cam, studio((p_ref[0], p_ref[1], mid)))
        lo, hi = (mid, hi) if v > 1 else (lo, mid)
    return round((lo + hi) / 2, 1)


def framing(film: str, use_timing: bool = True, t0: float = 0.0, t1: float | None = None) -> dict:
    who = {"netflix": "her", "whatsapp": "him"}[film]
    tp = EXPL / "acting" / f"timing_{who}.json"
    timing = json.loads(tp.read_text()) if use_timing and tp.exists() else None
    perf, cues, sheet = E.performer(film, timing)
    edl = json.loads((EXPL / "edl" / f"{film}.json").read_text())
    cams = SP.cameras(who)
    fps24 = edl["fps"]
    t1 = cues["duration"] if t1 is None else t1
    speak = [(ln["start"], ln["end"]) for ln in cues["lines"]]
    shots = []
    for s in edl["shots"]:
        if s["kind"] not in ("pres", "panel") or not s.get("camera"):
            continue
        cam = s["camera"] + ("_L" if s["kind"] == "panel" else "")
        shots.append((s["f0"] / fps24, s["f1"] / fps24, cam, s["n"]))
    out, apex = {}, {}
    ref = None
    for a, b, cam, n in shots:
        a, b = max(a, t0), min(b, t1)
        if b <= a:
            continue
        row = out.setdefault(cam, {"frames": 0, "in": 0, "shots": []})
        row["shots"].append(n)
        for i in range(int(math.ceil(a * FPS)), int(b * FPS)):
            t = i / FPS
            if not any(x <= t <= y for x, y in speak):
                continue
            F = perf.fk(perf.pose(t))
            A = {k: perf.actor(v[0]) for k, v in F.items()}
            if ref is None:  # her gesture plane: the sternum point 25 cm in front of the shoulders' midpoint
                sh = [(A["upperarm_l"][j] + A["upperarm_r"][j]) / 2 for j in range(3)]
                ref = (sh[0] + 25.0, sh[1], sh[2] - 14.0)
            hands = {s: [A["hand_" + s]] + [A[f"{tp_}_{s}"] for tp_ in TIPS if f"{tp_}_{s}" in A] for s in "lr"}
            row["frames"] += 1
            if any(in_frame(cams[cam], hands[s]) for s in "lr"):
                row["in"] += 1
        for e in perf.plan.events:
            if a <= e.stroke < b:
                F = perf.fk(perf.pose(e.stroke))
                A = {k: perf.actor(v[0]) for k, v in F.items()}
                sides = ("r", "l") if e.hand == "both" else (e.hand,)
                ok = any(in_frame(cams[cam], [A["hand_" + s]] + [A[f"{tp_}_{s}"] for tp_ in TIPS]) for s in sides)
                ap = apex.setdefault(cam, {"n": 0, "in": 0, "out": []})
                ap["n"] += 1
                ap["in"] += ok
                if not ok:
                    ap["out"].append(f"{e.kind}:{e.word}@{e.stroke:.2f}")
    res = {}
    for cam, row in out.items():
        frac = row["in"] / row["frames"] if row["frames"] else None
        res[cam] = {"hands_in_frame_frac": round(frac, 3) if frac is not None else None,
                    "bar": BARS.get(cam), "pass": frac is not None and frac >= BARS.get(cam, 0.6),
                    "speaking_frames": row["frames"], "shots": row["shots"],
                    "apex_in_frame": f'{apex.get(cam, {}).get("in", 0)}/{apex.get(cam, {}).get("n", 0)}',
                    "apex_out": apex.get(cam, {}).get("out", []),
                    "bottom_z_cm": bottom_z(cams[cam], ref) if ref else None}
    res["_ref"] = {"gesture_plane_point": [round(x, 1) for x in ref] if ref else None,
                   "desk_top": perf.set.desk_top, "timing": bool(timing), "t": [t0, t1]}
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("film", nargs="?", default="netflix")
    ap.add_argument("--no-timing", action="store_true")
    ap.add_argument("--t0", type=float, default=0.0)
    ap.add_argument("--t1", type=float, default=None)
    a = ap.parse_args()
    print(json.dumps(framing(a.film, not a.no_timing, a.t0, a.t1), indent=1))
