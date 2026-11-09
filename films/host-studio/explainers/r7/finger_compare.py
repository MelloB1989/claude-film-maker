"""R7 hands (agent-08): the fingers of two dumps side by side, frame by frame: the offline/kit arm track (what the body
build keyed) against an editor dump (what renders, e.g. the PLACED stage). Parity compares joint positions after
aligning at the shoulder; this compares the HAND's own shape, which parity does not see: per finger the MCP and PIP
flexion from the joint heads (the MCP measured from the hand joint -> _01 line, the same proxy in both dumps), the
DIP when a dump carries '<finger>_tip_<s>' points, each finger's abduction off the middle finger in the palm's plane,
and the hand's own turn against the forearm (flexion/extension, pronation proxy). Pure python, numbers only: runs on
the box for her dumps and his.

    python3 r7/finger_compare.py KIT.json EDITOR.json --frames 1060,1067,1075 [--seq-fps 24] [--hand r]
"""
from __future__ import annotations

import argparse
import json
import math

FINGERS = ("index", "middle", "ring", "pinky")


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def unit(a):
    n = math.sqrt(dot(a, a)) or 1.0
    return [a[0] / n, a[1] / n, a[2] / n]


def ang(a, b) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


def frames_of(doc: dict) -> list:
    return doc.get("frames") or doc.get("track", {}).get("frames") or []


def at(doc: dict, t: float) -> dict:
    fr = frames_of(doc)
    best = min(fr, key=lambda f: abs(float(f["t"]) - t))
    return {**best["p"], **(best.get("tips") or {})}  # (agent-01's track keeps the fingertips apart)


def hand(P: dict, s: str) -> dict:
    """the hand's shape from joint heads: {finger: [mcp, pip, dip|None, abd]}, wrist flex/ext, palm-normal tilt."""
    H, E = P[f"hand_{s}"], P.get(f"lowerarm_{s}")
    kn = sub(P[f"pinky_01_{s}"], P[f"index_01_{s}"])
    hd = sub(P[f"middle_01_{s}"], H)
    n = unit(cross(hd, kn))  # the palm's normal, up to sign (the same convention in both dumps)

    def plane(v):
        return unit(sub(v, [n[i] * dot(v, n) for i in range(3)]))
    m = plane(sub(P[f"middle_02_{s}"], P[f"middle_01_{s}"]))
    side = plane(sub(kn, [m[i] * dot(kn, m) for i in range(3)]))
    out = {}
    for f in FINGERS:
        b1, b2, b3 = P[f"{f}_01_{s}"], P[f"{f}_02_{s}"], P[f"{f}_03_{s}"]
        mcp = ang(sub(b1, H), sub(b2, b1))
        pip = ang(sub(b2, b1), sub(b3, b2))
        tip = P.get(f"{f}_tip_{s}")
        dip = ang(sub(b3, b2), sub(tip, b3)) if tip else None
        v = plane(sub(b2, b1))
        abd = math.degrees(math.atan2(dot(v, side), dot(v, m)))
        out[f] = [round(mcp, 1), round(pip, 1), None if dip is None else round(dip, 1), round(abd, 1)]
    if E:
        out["_wrist_bend"] = round(ang(sub(H, E), hd), 1)  # forearm -> hand long axis, deg (flex/ext + deviation)
        out["_palm_vs_forearm_up"] = round(math.degrees(math.asin(max(-1.0, min(1.0, abs(n[2]))))), 1)
    adj = [out["middle"][3] - out["index"][3], out["ring"][3] - out["middle"][3], out["pinky"][3] - out["ring"][3]]
    out["_adjacent_abd_max"] = round(max(abs(x) for x in adj), 1)
    out["_claw"] = [f for f in FINGERS if out[f][2] is not None and out[f][0] < 20.0 and out[f][1] > 15.0
                    and out[f][2] >= out[f][1]]  # (needs the DIP: the MCP here is a proxy off the hand joint)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("kit")
    ap.add_argument("editor")
    ap.add_argument("--frames", default="1060,1067,1075", help="sequence frames at --seq-fps")
    ap.add_argument("--seq-fps", type=float, default=24.0)
    ap.add_argument("--hand", default="r")
    a = ap.parse_args()
    K, E = json.load(open(a.kit)), json.load(open(a.editor))
    for fr in (int(x) for x in a.frames.split(",")):
        t = fr / a.seq_fps
        hk, he = hand(at(K, t), a.hand), hand(at(E, t), a.hand)
        print(f"f{fr} t{t:.3f} hand {a.hand}   [mcp, pip, dip, abd]")
        for k in list(FINGERS) + ["_wrist_bend", "_palm_vs_forearm_up", "_adjacent_abd_max", "_claw"]:
            print(f"   {k:20s} kit {hk.get(k)}   editor {he.get(k)}")


if __name__ == "__main__":
    main()
