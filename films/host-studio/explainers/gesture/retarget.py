"""Mixamo -> MetaHuman body retarget for the R7 gesture library (agent-08), in plain Python.

In: a Mixamo clip's dump (mixamo_dump_blender.py: per frame the world rotation and position of every mixamorig bone,
in UE component space, cm, quaternions x y z w) and the MetaHuman body skeleton as perform.py READs it (parent +
local per bone; her `skeletons/her_body_read.json` or the stock metahuman_base_skel).
Out: per frame, LOCAL rotations of the upper-body bones on the MetaHuman skeleton (what agent-10's planner and
agent-01's body take: her translations stay hers), plus the joint tracks annotate.py reads.

How: the source is first turned as a whole so its body frame (up: hips -> neck, left: right arm -> left arm) meets the
target's (G). Each mapped bone then takes the source bone's world rotation change from its rest, conjugated by G,
applied on top of a calibrated rest: the target bone swung from its own rest direction to the source's rest direction
(so a T-pose source puts the A-pose MetaHuman in a T-pose):  W_b(t) = G S(t) S_rest^-1 G^-1 . C_b^-1 . T_rest_b.
Bones without a source (twists, metacarpals, correctives, legs) keep their rest local rotation.

Seat-adapt (upper body only):
- legs keep the rest (agent-01 seats them);
- `mirror`: L and R swapped through the body's sagittal plane: the mic is on her LEFT, so a clip whose big hand is
  the left one is mirrored onto her right;
- elbows off the torso: each upper arm is abducted (about the body's forward axis, forearm and hand keeping their
  world rotations) until the elbow is at least `elbow_out_cm` further out than the shoulder joint, which keeps the
  upper arm >= 3 cm off her chest's side (her R6 v2b arms were pinned with the elbow 0-1 cm inside the shoulder).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from seatkit import (add, axis_angle, cross, dot, frame_to_frame, mul, ortho, qinv, qmul, qnorm,  # noqa: E402
                     qrot, sub, swing, unit)

MX = "mixamorig:"
# MetaHuman bone -> (Mixamo bone, MH child joint and Mixamo child joint for the calibration swing, or None to inherit
# the parent's calibration)
MAP: dict = {
    "pelvis": ("Hips", None), "spine_01": ("Spine", None), "spine_02": ("Spine", None), "spine_03": ("Spine1", None),
    "spine_04": ("Spine2", None), "spine_05": ("Spine2", None), "neck_01": ("Neck", None), "neck_02": ("Neck", None),
    "head": ("Head", None),
}
for s, S in (("l", "Left"), ("r", "Right")):
    MAP.update({
        f"clavicle_{s}": (f"{S}Shoulder", (f"upperarm_{s}", f"{S}Arm")),
        f"upperarm_{s}": (f"{S}Arm", (f"lowerarm_{s}", f"{S}ForeArm")),
        f"lowerarm_{s}": (f"{S}ForeArm", (f"hand_{s}", f"{S}Hand")),
        f"hand_{s}": (f"{S}Hand", (f"middle_01_{s}", f"{S}HandMiddle1")),
    })
    for f, F in (("thumb", "Thumb"), ("index", "Index"), ("middle", "Middle"), ("ring", "Ring"), ("pinky", "Pinky")):
        for k in (1, 2, 3):
            child = (f"{f}_0{k + 1}_{s}", f"{S}Hand{F}{k + 1}") if k < 3 else None
            MAP[f"{f}_0{k}_{s}"] = (f"{S}Hand{F}{k}", child)
TRUNK = ("pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head")
TRACKS = ("upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "spine_05", "head")
ELBOW_OUT_CM = 4.0


def _src(name: str) -> str:
    return name if name.startswith(MX) else MX + name


class Target:
    """The MetaHuman skeleton's rest: component-space positions and rotations of every bone, by FK from READ's
    locals."""

    def __init__(self, read: dict):
        self.parent = read["parent"]
        self.local = read["local"]
        self.order, seen = [], set()

        def visit(b):
            if b in seen:
                return
            p = self.parent.get(b)
            if p and p in self.local:
                visit(p)
            seen.add(b)
            self.order.append(b)

        for b in self.local:
            visit(b)
        self.t, self.q = {}, {}
        for b in self.order:
            loc, p = self.local[b], self.parent.get(b)
            if not p or p not in self.q:
                self.t[b], self.q[b] = list(loc["t"]), qnorm(list(loc["q"]))
            else:
                self.t[b] = add(self.t[p], qrot(self.q[p], loc["t"]))
                self.q[b] = qnorm(qmul(self.q[p], loc["q"]))

    def frame(self):
        up = unit(sub(self.t["neck_01"], self.t["pelvis"]))
        return up, ortho(sub(self.t["upperarm_l"], self.t["upperarm_r"]), up)


def mirror_dump(dump: dict) -> dict:
    """The clip mirrored through its own sagittal plane (from the rest pose's left axis): positions reflected,
    rotations conjugated by the reflection, Left/Right names swapped."""
    rest = dump["rest"]
    up = unit(sub(rest[_src("Neck")]["t"], rest[_src("Hips")]["t"]))
    n = ortho(sub(rest[_src("LeftArm")]["t"], rest[_src("RightArm")]["t"]), up)  # the plane's normal
    o = rest[_src("Hips")]["t"]

    def ref_p(p):
        d = sub(p, o)
        return add(o, sub(d, mul(n, 2 * dot(d, n))))

    def ref_q(q):
        # M R M for the reflection M = I - 2nn^T: the axis reflects and the angle flips sign
        v = q[:3]
        v2 = sub(v, mul(n, 2 * dot(v, n)))
        return qnorm([-v2[0], -v2[1], -v2[2], q[3]])

    def swap(name):
        return name.replace("Left", "\0").replace("Right", "Left").replace("\0", "Right")

    def one(pose):
        return {swap(b): {"t": ref_p(x["t"]), "q": ref_q(x["q"])} for b, x in pose.items()}

    return dict(dump, rest=one(rest), frames=[one(f) for f in dump["frames"]], mirrored=not dump.get("mirrored"))


class Retarget:
    def __init__(self, target: Target, dump: dict, elbow_out_cm: float = ELBOW_OUT_CM):
        self.tg, self.dump, self.elbow_out = target, dump, elbow_out_cm
        rest = dump["rest"]
        s_up = unit(sub(rest[_src("Neck")]["t"], rest[_src("Hips")]["t"]))
        s_left = ortho(sub(rest[_src("LeftArm")]["t"], rest[_src("RightArm")]["t"]), s_up)
        t_up, t_left = target.frame()
        self.G = frame_to_frame(s_up, s_left, t_up, t_left)
        self.Gi = qinv(self.G)
        self.up, self.left = t_up, t_left
        # calibration swings C_b (target rest dir -> G . source rest dir); end bones inherit their parent's
        self.C = {}
        for b in target.order:
            if b not in MAP:
                continue
            src, child = MAP[b]
            if child is None or child[0] not in target.t or _src(child[1]) not in rest:
                p = target.parent.get(b)
                self.C[b] = self.C.get(p, [0.0, 0.0, 0.0, 1.0]) if b not in TRUNK else [0.0, 0.0, 0.0, 1.0]
                continue
            d_t = sub(target.t[child[0]], target.t[b])
            d_s = qrot(self.G, sub(rest[_src(child[1])]["t"], rest[_src(src)]["t"]))
            self.C[b] = swing(d_t, d_s)
        self.mapped = [b for b in target.order if b in MAP and _src(MAP[b][0]) in rest]
        self.clear_log = []

    def world(self, f: int) -> dict:
        """Component-space rotations of every target bone at frame f (unmapped ones ride on their parent with their
        rest local)."""
        tg, fr, rest = self.tg, self.dump["frames"][f], self.dump["rest"]
        W = {}
        for b in tg.order:
            p = tg.parent.get(b)
            if b in MAP and _src(MAP[b][0]) in fr:
                s = _src(MAP[b][0])
                delta = qmul(qmul(self.G, qmul(fr[s]["q"], qinv(rest[s]["q"]))), self.Gi)
                W[b] = qnorm(qmul(qmul(delta, self.C[b]), tg.q[b]))
            elif p in W:
                W[b] = qnorm(qmul(W[p], tg.local[b]["q"]))
            else:
                W[b] = tg.q[b]
        return W

    def positions(self, W: dict, bones=None) -> dict:
        """FK positions on the target's own bone lengths (the pelvis at its rest)."""
        tg, P = self.tg, {}
        for b in tg.order:
            p = tg.parent.get(b)
            P[b] = list(tg.t[b]) if not p or p not in P else add(P[p], qrot(W[p], tg.local[b]["t"]))
        return {b: P[b] for b in bones} if bones else P

    def clear_elbows(self, W: dict, f: int) -> dict:
        """Abduct each upper arm until its elbow is elbow_out cm outside the shoulder (forearm and hand keep their
        world rotations, so the hand only moves out with the elbow)."""
        fwd = ortho(cross(self.up, self.left), self.up)
        for s in ("l", "r"):
            ua, side = f"upperarm_{s}", self.left if s == "l" else mul(self.left, -1)
            arm = self.tg.local[f"lowerarm_{s}"]["t"]

            def out(q):
                return dot(qrot(q, arm), side)

            before = out(W[ua])
            if before >= self.elbow_out:
                continue
            best = None
            for sign in (1, -1):  # whichever turn moves the elbow out, by the least angle
                lo, hi = 0.0, 60.0
                for _ in range(24):
                    mid = (lo + hi) / 2
                    lo, hi = (lo, mid) if out(qmul(axis_angle(fwd, sign * mid), W[ua])) >= self.elbow_out else (mid, hi)
                if out(qmul(axis_angle(fwd, sign * hi), W[ua])) >= self.elbow_out - 0.05 and (best is None or hi < best[1]):
                    best = (sign, hi)
            if best:
                W = self._abduct(W, ua, axis_angle(fwd, best[0] * best[1]))
                self.clear_log.append({"f": f, "side": s, "out_before_cm": round(before, 2), "deg": round(best[1], 2)})
        return W

    def _abduct(self, W, ua, r):
        """W with the upper arm turned by r; its twist and corrective children follow it, the forearm chain keeps
        its world rotations."""
        W2, moved = dict(W), {ua}
        W2[ua] = qnorm(qmul(r, W[ua]))
        for b in self.tg.order:
            p = self.tg.parent.get(b)
            if p in moved and not b.startswith("lowerarm"):
                moved.add(b)
                W2[b] = qnorm(qmul(W2[p], self.tg.local[b]["q"]))
        return W2

    def local(self, W: dict, bones) -> dict:
        tg = self.tg
        out = {}
        for b in bones:
            p = tg.parent.get(b)
            out[b] = qnorm(qmul(qinv(W[p]), W[b])) if p in W else W[b]
        return out

    def run(self, clear: bool = True) -> dict:
        """The retargeted clip: local rotations per frame of the mapped bones, and the joint tracks."""
        n = len(self.dump["frames"])
        bones = [b for b in self.mapped if not b.startswith(("thigh", "calf", "foot", "ball"))]
        frames, tracks = [], {b: [] for b in TRACKS}
        wrists = {"hand_l": [], "hand_r": []}
        for f in range(n):
            W = self.world(f)
            if clear:
                W = self.clear_elbows(W, f)
            loc = self.local(W, bones)
            frames.append([[round(x, 6) for x in loc[b]] for b in bones])
            P = self.positions(W)
            for b in TRACKS:
                tracks[b].append([round(x, 3) for x in P[b]])
            ci = qinv(W["spine_05"])
            for h in wrists:  # the wrist in the chest's (spine_05's) frame: agent-01's IK target
                wrists[h].append({"t": [round(x, 3) for x in qrot(ci, sub(P[h], P["spine_05"]))],
                                  "q": [round(x, 6) for x in qnorm(qmul(ci, W[h]))]})
        return {
            "fps": self.dump["fps"], "space": "UE component, cm; quaternions x y z w, local to the parent",
            "bones": bones, "frames": frames, "mirrored": bool(self.dump.get("mirrored")),
            "elbow_out_cm": self.elbow_out, "clearance_fixes": len(self.clear_log),
            "clearance_max_deg": max([c["deg"] for c in self.clear_log] or [0.0]),
            "joints": {"fps": self.dump["fps"], "joints": tracks},
            "wrists_chest": wrists,
        }


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dump")
    ap.add_argument("skeleton")
    ap.add_argument("out")
    ap.add_argument("--mirror", action="store_true")
    ap.add_argument("--no-clear", action="store_true")
    ap.add_argument("--elbow-out", type=float, default=ELBOW_OUT_CM)
    a = ap.parse_args(argv)
    dump = json.load(open(a.dump))
    if a.mirror:
        dump = mirror_dump(dump)
    res = Retarget(Target(json.load(open(a.skeleton))), dump, a.elbow_out).run(clear=not a.no_clear)
    json.dump(res, open(a.out, "w"))
    print(json.dumps({k: res[k] for k in ("fps", "mirrored", "clearance_fixes", "clearance_max_deg")}
                     | {"frames": len(res["frames"]), "bones": len(res["bones"])}))


if __name__ == "__main__":
    main(sys.argv[1:])
