"""Round 7: a presenter's body PERFORMANCE on the seated pose (seatkit), from the acting sheet (agent-11's
acting/<who>.json, lines[].body01): hands up and off the body while she speaks, a loose HIGH rest between gestures,
the desk rest only in pauses; beat, open-palm, size, count, deictic, raise-finger, press and pinch gestures timed to
the stressed syllables; the torso leaning in on the sheet's words and turning a little with the gesturing hand; the
shoulders lifting with big gestures; head tilts on the body's neck (agent-04's tilts); fingers shaped per gesture.

Elbows are kept OUT (the operator: "her right boob covers the upper limb of her right hand"): the upper arm is
measured against a torso + breast model every frame (clearance >= 3 cm). Everything else of seatkit holds (seat,
legs, desk, mic in each camera's picture). Pure Python, like seatkit: runs here for tests and in the editor.

All positions are in the actor frame (x forward, y the presenter's right, z up), targets relative to her sternum
point so the hands ride the torso's lean and turn.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from dataclasses import dataclass, field, replace

import seatkit as S
from seatkit import add, sub, mul, dot, cross, norm, unit, ortho, qmul, qinv, qrot, qnorm, axis_angle, qslerp, smooth

FINGERS = ("index", "middle", "ring", "pinky", "thumb")

# Hooks for the code-generated motion (the operator, 08 Nov: no motion libraries; every gesture generated, unique):
#   gesture_style.py (agent-08) beside this file, any of:
#     envelope(phase, u, event) -> weight 0..1+ (phase prep|hold|retract, u 0..1): the stroke's time profile
#       (min-jerk, overshoot past 1 on the stroke, settle); default smoothstep in, hold 1, smoothstep out
#     vary(pose: HandPose, event, hand) -> HandPose: seeded per-event variation of the goal (nothing repeats)
#     fingers(event, hand, w) -> {finger: extra curl deg}: finger motion during the gesture (added to the shape)
#     hand(performer, hand, t) -> (HandPose, big weight): the whole hand track instead of the envelope blend
#     weights(performer, t) -> {event index: weight}: the events' presence for the torso's turn and lift
#     finger_post(performer, hand, HandPose, W): after the finger curls (e.g. the spread in the palm's plane)
#     report(performer, length_s) -> {"rows": {...}, "issues": [...]}: its own rows for build's summary
#   timing JSON (agent-10's prosody planner), passed to plan_from_sheet(timing=...): [{"line", "word_i",
#     "prep_t", "stroke_t", "hold_s", "retract_s", "amp", "energy"}] overriding the sheet's per gesture
try:
    import gesture_style as STYLE_HOOK  # noqa: E402
except Exception:
    STYLE_HOOK = None

# finger shapes: degrees of curl ADDED to the base pose's relaxed curl, per finger (joints 01/02/03 take 0.8/1/0.8)
SHAPES = {
    "relaxed": {},
    "open": {"index": -18, "middle": -18, "ring": -16, "pinky": -14, "thumb": -10},
    "point": {"index": -22, "middle": 60, "ring": 65, "pinky": 65, "thumb": 25},
    "count1": {"index": -22, "middle": 62, "ring": 66, "pinky": 66, "thumb": 35},
    "count2": {"index": -22, "middle": -22, "ring": 66, "pinky": 66, "thumb": 35},
    "count3": {"index": -22, "middle": -22, "ring": -20, "pinky": 66, "thumb": 35},
    "pinch": {"index": 35, "middle": 10, "ring": 15, "pinky": 20, "thumb": 20},
    "soft_fist": {"index": 25, "middle": 28, "ring": 30, "pinky": 30, "thumb": 10},
    "rest": {"index": -8, "middle": -6, "ring": -4, "pinky": -2, "thumb": -6},  # gently curved, not hanging (r7F)
}


@dataclass
class HandPose:
    """One hand's goal: the wrist relative to the sternum point (fwd, out to that hand's side, up), the palm
    (pronation: 90 thumb up, 0 palm down, < 0 palm up), wrist extension, finger shape."""
    off: tuple
    pron: float = 60.0
    ext: float = 10.0
    shape: str = "relaxed"
    yaw: float = 0.0  # deg the fingers turn toward that hand's own side (out), off the forearm's line


# r7b (the orchestrator on side A: the gestures were BELOW the MCU frame): the sheet's apex_height per gesture
# (agent-11) as the wrist's height over the sternum point (shoulders - 14 cm, ~84 cm seated on her). MCU's bottom edge
# is about her bust line (~85 cm): bust puts the fingertips just inside it
APEX_Z = {"bust": 8.0, "lower_chest": 11.0, "sternum": 14.0, "upper_chest": 19.0, "collarbone": 22.0, "chin": 30.0}
# (agent-10's projection: the CU's bottom edge sits at ~102 cm on her gesture plane, so collarbone strokes need the
#  wrist near 110 cm = the sternum point + ~25)

BEAT_MAX_Z = 16.0  # cm over the sternum point: a beat's apex never higher (N15 'delivers' at upper chest met the mic)
APEX_MAX_Z = 22.0  # cm over the sternum point: the wrist never higher (the orchestrator, 08 Nov: key beats cap at the
#   collarbone, <= 60 deg of upper arm)

# the poses a gesture moves to, per kind/detail and size; the right hand's (the left mirrors out)
SIZE_OUT = {"small": 0.0, "medium": 5.0, "big": 10.0}


def gesture_pose(g: dict, hand: str, count_n: int) -> HandPose:
    kind, detail, size = g.get("type", "beat"), g.get("detail", ""), g.get("size", "medium")
    so = SIZE_OUT.get(size, 5.0)
    target = (g.get("target") or "").lower()
    if detail == "pinch":  # whatever the kind ("size: pinch" = small): thumb and index almost touching, to her right
        return HandPose((26.0, 15.0, 0.0), pron=70.0, ext=15.0, shape="pinch")
    if kind == "open":
        return HandPose((30.0, 14.0 + so, -2.0 + so * 0.3), pron=-40.0, ext=15.0, shape="open")
    if kind == "size":
        if detail == "place":
            return HandPose((28.0, 12.0 + so * 0.5, -4.0), pron=10.0, ext=5.0, shape="open")  # palms down, set it down
        return HandPose((28.0, 12.0 + so, 0.0), pron=88.0, ext=10.0, shape="open")  # palms facing: the span
    if kind == "count":
        # to her right at chest height, out wide (from her right-front cameras a high count hand sat over the mic)
        return HandPose((20.0, 28.0, 0.0), pron=95.0, ext=40.0, shape=f"count{max(1, min(3, count_n))}")
    if kind == "deictic":
        if "left" in target or "panel" in target:  # her left = the panel side: cross-body, under the mic head
            # palm turned toward the panel, the hand near her midline and forward: a cross-body arm pressed into
            # her chest and sat over the mic in the picture
            return HandPose((36.0, 8.0, 0.0), pron=-60.0, ext=12.0, shape="open")
        return HandPose((26.0, 24.0, 10.0), pron=-20.0, ext=15.0, shape="open")  # her right, up
    if detail in ("raise_finger",):
        return HandPose((18.0, 27.0, 4.0), pron=80.0, ext=45.0, shape="point")  # out to her right: clear of the mic
    if detail in ("press",):
        return HandPose((28.0, 10.0, -3.0), pron=5.0, ext=0.0, shape="relaxed")
    if detail in ("pinch",):
        return HandPose((26.0, 12.0, 2.0), pron=70.0, ext=15.0, shape="pinch")
    # beat: from the high rest a short down-stroke, palm in/down
    return HandPose((29.0, 12.0 + so * 0.4, -2.0), pron=35.0, ext=12.0, shape="relaxed")


# the origin the sheet's amp scales a gesture pose from (scaled, gesture_style's Var.apply): the r7b high rest, kept
# so that moving the rest does not move the gestures
POSE_ORIGIN = HandPose((22.0, 17.0, 13.0), pron=40.0, ext=10.0, shape="relaxed", yaw=20.0)
# r7F (the orchestrator on her TEST: at the top of her chest, wrists limp, fingers like claws, it read as fidgeting
# with her top): the presenter's rest. Hands loosely together in a soft steeple at the lower ribcage, well in front of
# her (not touching her), palms facing, wrists straight, fingers gently curved; the gestures rise from it into the
# frame. The fingers aim at the midline (YAW_BASE is faded out at the rest, see hand_targets).
HIGH_REST = HandPose((27.0, 10.0, -5.5), pron=80.0, ext=12.0, shape="rest")  # the DESK REST (the orchestrator, 08 Nov:
#   at x 16 her hands sat 3-4 cm off her belly, 'stuck to the body'): the forearms on the desk across its near edge,
#   the elbows just behind it (x ~8, ~22 out, z ~76, 37-39 deg: the supported-arm line is 40), the wrists ~29 cm
#   forward, ~7 cm over the desk top (each hand rests on its little-finger edge, palms facing: lower, the ring and
#   pinky tips went into the desk), the hands loosely together 14-16 cm off the belly. Before:
# HIGH_REST (16, 10, -4)  # r7F rows: x 25 -> 17.5, the fit that
#   lets the elbows hang at <= 30 deg (Performer._fit_poses reports it as rest_fit)  # the orchestrator's ruling (08 Nov): lower
#   than agent-10's (24, 8.5, 2.5), which put her wrists at her bust height 8 cm in front of it; wrists ~80 cm, under
#   CAM_MCU's bottom edge. Not the ruled x 30: that far forward, with the hands together, the upper arms can clear her
#   chest (swivel) only with the elbows up at 90-92 cm, a reach; at 25 / 10 out they hang at 83-86, the wrists 27 cm
#   forward of her spine, the fingertips 3-5 cm over the desk (offline on her skeleton, 0 issues)
REST_POLE = (-0.2, 0.9, -0.6)  # the elbows' direction at the rest (fwd, out, up)
REST_YAW = 8.0  # deg out off the forearm at the rest (r7F naturalness: 32 bent the wrists back 31 deg; 15 keeps them
#                  near neutral, the fingertips still 3.8 cm apart) (gesture_style's track carries no yaw): the forearms come in
#                  from the elbows at ~60 deg, the fingers then point forward and in, the tips meeting at the midline


@dataclass
class Event:
    hand: str
    prep: float
    stroke: float
    hold: float
    pose_r: HandPose
    pose_l: HandPose | None
    kind: str
    word: str = ""
    big: bool = False
    energy: float = 0.5
    seed: int = 0
    retract: float = 0.35
    detail: str = ""
    line: str = ""

    def weight(self, t: float, retract: float | None = None) -> float:
        rt = self.retract if retract is None else retract
        if t <= self.prep or t >= self.stroke + self.hold + rt:
            return 0.0
        if t < self.stroke:
            phase, u = "prep", (t - self.prep) / max(0.05, self.stroke - self.prep)
        elif t <= self.stroke + self.hold:
            phase, u = "hold", (t - self.stroke) / max(1e-3, self.hold)
        else:
            phase, u = "retract", (t - self.stroke - self.hold) / rt
        if STYLE_HOOK is not None and hasattr(STYLE_HOOK, "envelope"):
            return float(STYLE_HOOK.envelope(phase, u, self))
        return {"prep": smooth(u), "hold": 1.0, "retract": 1.0 - smooth(u)}[phase]


@dataclass
class Plan:
    """The performance on the take's clock (s): events, speaking spans, lean keys, tilts."""
    events: list
    speaking: list  # [(t0, t1)]
    lean: list  # [(t, deg)]
    tilts: list = field(default_factory=list)  # [{"t", "until", "roll_deg", "ease_s"}]
    base_lean: float = 4.0
    gap_merge: float = 0.9  # pauses shorter than this keep the hands up (agent-10's timing can set it)
    on_cam: list = field(default_factory=list)  # [[t0, t1, camera label]] the shots she is in
    bridges: list = field(default_factory=list)  # [[t0, t1]] pauses that keep the hands up (agent-10's timing)

    def speak_w(self, t: float, pre: float = 0.5, post: float = 0.6, gap_merge: float | None = None) -> float:
        """1 while speaking (lines merged across gaps under gap_merge s), eased in/out."""
        gap_merge = self.gap_merge if gap_merge is None else gap_merge
        spans = []
        for a, b in sorted(list(self.speaking) + [tuple(x) for x in self.bridges]):  # a bridged pause counts as speech
            if not spans and a < 1.5:  # the take opens alive, hands already up (the sheet's 'pre')
                a = -1.0
            if spans and a - spans[-1][1] < gap_merge:
                spans[-1] = (spans[-1][0], b)
            else:
                spans.append((a, b))
        w = 0.0
        for a, b in spans:
            if a - pre <= t <= b + post:
                up = smooth((t - (a - pre)) / pre)
                down = 1.0 - smooth((t - b) / post) if t > b else 1.0
                w = max(w, min(up, down))
        return w

    def lean_at(self, t: float, ease: float = 0.45) -> float:
        v = self.base_lean
        for tk, deg in sorted(self.lean):
            if t <= tk - ease:
                break
            v = v + (deg - v) * smooth((t - (tk - ease)) / ease)
        return v

    def roll_at(self, t: float) -> float:
        v = 0.0
        for k in self.tilts:
            e = float(k.get("ease_s", 0.4))
            a, b = float(k["t"]), float(k.get("until", k["t"] + 1.0))
            if a - e < t < b + e:
                w = min(smooth((t - (a - e)) / e), 1.0 - smooth((t - b) / e) if t > b else 1.0)
                v += float(k["roll_deg"]) * w
        return v


def scaled(p: HandPose, k: float) -> HandPose:
    """A gesture pose `k` times as far from the high rest (the sheet's amp: strokes vary in size)."""
    off = tuple(POSE_ORIGIN.off[i] + (p.off[i] - POSE_ORIGIN.off[i]) * k for i in range(3))
    return replace(p, off=off)


def plan_from_sheet(sheet: dict, cues: dict, tilts: list | None = None, base_lean: float = 4.0,
                    timing: list | None = None, on_cam: list | None = None) -> Plan:
    """agent-11's acting sheet (lines[].body01) + the cue sheet (speaking spans) -> Plan. `timing` (agent-10's
    prosody planner) overrides each gesture's prep/stroke/hold/retract/amp/energy by (line, word_i)."""
    events, lean = [], []
    gap_merge = 0.9
    bridges = []
    if isinstance(timing, dict):
        gap_merge = float(timing.get("gap_merge", gap_merge))
        bridges = [[float(a), float(b)] for a, b in timing.get("bridge", [])]
        timing = timing.get("gestures", [])
    tmap = {(str(x.get("line")), int(x.get("word_i", -1))): x for x in (timing or []) if not x.get("add")}
    adds = {}
    for x in timing or []:  # agent-10: new gestures (beats on secondary stresses) the sheet doesn't have
        if x.get("add"):
            adds.setdefault(str(x.get("line")), []).append({"type": x.get("type", "beat"), "detail": x.get("detail", ""),
                                                             "hand": x.get("hand", "r"), "size": x.get("size", "small"),
                                                             "word": x.get("word", ""), "word_i": x.get("word_i", -1),
                                                             **{k: x[k] for k in ("prep_t", "stroke_t", "hold_s",
                                                                                  "retract_s", "amp", "energy")
                                                                if k in x}})
    seed0 = 1009
    for ln in sheet["lines"]:
        b = ln.get("body01") or {}
        n_count = 0
        lid = str(b.get("line", ln.get("id", "")))
        for g0 in sorted(b.get("gestures", []) + adds.get(lid, []), key=lambda g: float(g.get("stroke_t", 0.0))):
            g = {**g0, **{k: v for k, v in tmap.get((str(b.get("line", ln.get("id"))), int(g0.get("word_i", -2))),
                                                     {}).items() if k in ("prep_t", "stroke_t", "hold_s", "retract_s",
                                                                          "amp", "energy")}}
            if g.get("type") == "count":
                n_count += 1
            amp = float(g.get("amp", {"small": 0.3, "medium": 0.55, "big": 0.85}.get(g.get("size"), 0.55)))
            k = 0.55 + 0.8 * amp  # 0.3 -> 0.79, 0.55 -> 0.99, 0.85 -> 1.23 of the pose's distance from the high rest
            pr = scaled(gesture_pose(g, "r", n_count), k)
            if g.get("apex_height") in APEX_Z:  # the sheet's height wins: in the shot, not at the desk
                z = min(APEX_Z[g["apex_height"]], APEX_MAX_Z)  # key beats at most at the collarbone
                if g.get("type") == "beat" and g.get("detail") in ("beat", "", None):
                    z = min(z, BEAT_MAX_Z)  # beats can sit lower, still in frame (the orchestrator), off the mic
                pr = replace(pr, off=(pr.off[0], pr.off[1], z))
            pl = scaled(gesture_pose(g, "l", n_count), k) if g.get("hand") in ("both", "l") else None
            if pl is not None:  # the left (mic side) of a two-hand gesture: forward <= LEFT_TWO[0], out LEFT_TWO[1], up
                #                 >= LEFT_TWO[2] over the sternum point. Tucked in and low (out 7, up -3.5) the arm went
                #                 straight and the elbow rose in front of her chest, inside the Top (box B, agent-11:
                #                 -7 cm at N01 'million', N13 'that'); this keeps it out and down as at the high rest.
                #                 Higher than this, the hand passes behind the mic from CAM_CU / CAM_WIDE.
                # r7F (agent-13: the left travelled 0.27 of the right on two-hand strokes, line 0.4-0.7): the left
                #   follows the right's move from the rest at LEFT_SHARE, mirrored, inside the mic box (gesture_style)
                pl = replace(pl, off=tuple(HIGH_REST.off[i] + LEFT_SHARE * (pr.off[i] - HIGH_REST.off[i]) for i in range(3)))
            seed0 += 1
            prep = float(g["prep_t"])  # agent-10's prosody timing owns prep/stroke/hold/retract when present
            ev = Event(g.get("hand", "r"), prep, float(g["stroke_t"]), float(g.get("hold_s", 0.25)),
                       pr, pl, g.get("type", "beat"), g.get("word", ""), g.get("size") == "big",
                       energy=float(g.get("energy", amp)), seed=seed0, retract=float(g.get("retract_s", 0.35)),
                       detail=g.get("detail", ""), line=str(b.get("line", ln.get("id", ""))))
            if STYLE_HOOK is not None and hasattr(STYLE_HOOK, "vary"):
                ev.pose_r = STYLE_HOOK.vary(ev.pose_r, ev, "r")
                if ev.pose_l is not None:
                    ev.pose_l = STYLE_HOOK.vary(ev.pose_l, ev, "l")
            events.append(ev)
        for k in b.get("lean", []):
            lean.append((float(k["t"]), float(k["deg"])))
    speaking = [(float(c["start"]), float(c["end"])) for c in cues["lines"]]
    return Plan(events, speaking, lean, tilts or [], base_lean, gap_merge, on_cam or [], bridges)


# --- torso model and the arm clearance ---------------------------------------------------------------------------

@dataclass
class Torso:
    """Her chest as an elliptic cylinder along spine_03 -> spine_05 (+8 cm), half-width `a` (lateral), half-depth
    `b`, and two breast spheres; the upper arm a capsule of radius `arm_r`. Measures per frame; agent-09's mesh measure
    is the judge, this keeps the pose honest while it is built."""
    a: float = 13.5
    b: float = 10.5
    a_waist: float = 11.5  # r7F: the waist under the ribcage is narrower (the cylinder had her chest's width all the
    b_waist: float = 9.5   # way down, so an elbow hanging at her side read as inside her): a, b taper to these
    waist_h: tuple = (4.0, 14.0)
    side_from: int = 10  # /20 of the upper arm: under the armpit (30-50 %) the arm lies against her side as any arm
    #   does; agent-02's mesh calls that a fold, a hit reads at 50 % or more and into the bust. The bust spheres
    #   still count from 40 %; the torso's side from 50 %  # cm up the spine from spine_03: waist below the first, the full chest above the second
    breast_r: float = 7.5
    breast_down: float = 9.0
    breast_out: float = 7.0
    arm_r: float = 4.2


def clearance(A: dict, F: dict, s: str, tor: Torso, parts: bool = False):
    """cm between her upper arm's surface and the torso (below the armpit) / breast model, along the arm's outer 60 %
    (the operator's complaint: the breast covering the upper arm)."""
    p3, p5 = A["spine_03"], A["spine_05"]
    ax = unit(sub(p5, p3))
    top = add(p5, mul(ax, -2.0))  # the chest only below the armpit: at the shoulder the arm meets the torso anyway
    fwd = ortho([1.0, 0.0, 0.0], ax)
    lat = cross(ax, fwd)
    if dot(lat, [0.0, 1.0, 0.0]) < 0:
        lat = mul(lat, -1.0)
    sh, el = A["upperarm_" + s], A["lowerarm_" + s]
    best = side_best = bust_best = 1e9
    for k in range(8, 21):  # the arm from 40 % out (the armpit end always touches)
        q = add(sh, mul(sub(el, sh), k / 20.0))
        d = sub(q, p3)
        h = dot(d, ax)
        if -5.0 <= h <= dot(sub(top, p3), ax) and k >= tor.side_from:
            x, y = dot(d, fwd), dot(d, lat)
            rr = math.hypot(x, y)
            th = math.atan2(x, y)
            k_ = max(0.0, min(1.0, (h - tor.waist_h[0]) / (tor.waist_h[1] - tor.waist_h[0])))
            ta, tb = tor.a_waist + (tor.a - tor.a_waist) * k_, tor.b_waist + (tor.b - tor.b_waist) * k_
            r_e = ta * tb / math.sqrt((tb * math.cos(th)) ** 2 + (ta * math.sin(th)) ** 2)
            side_best = min(side_best, rr - r_e - tor.arm_r)
        for side in (1.0, -1.0):
            c = add(add(add(p5, mul(ax, -tor.breast_down)), mul(fwd, tor.b - 1.0)), mul(lat, side * tor.breast_out))
            bust_best = min(bust_best, norm(sub(q, c)) - tor.breast_r - tor.arm_r)
    best = min(side_best, bust_best)
    return (best, side_best, bust_best) if parts else best


# --- the performer ---------------------------------------------------------------------------------------------------

class Performer(S.Seater):
    """seatkit.Seater with the plan driving the arms, hands, fingers, torso lean/turn and head roll."""

    def __init__(self, sk, st, sy, plan: Plan, torso: Torso | None = None, mic_side: str = "l"):
        self._ready = False  # seatkit's own setup (wrist extension, desk rest) runs on seatkit's pose
        self._wg = {}
        self._ws = {}
        super().__init__(sk, st, replace(sy, lean=plan.base_lean))
        self.plan, self.tor, self.mic_side = plan, torso or Torso(), mic_side
        self._finger_info = self._fingers()
        self._accented = self._accent_flags()
        self._ready = True

    def _accent_flags(self) -> dict:
        """{id(event): hands} for the strokes that need an accent: the same hand's pose barely changes from the
        stroke before (< 5 cm, < 1 s after it), so without one the wrist would not move (agent-10's list: count 2/3,
        a beat after a beat, a same-place size)."""
        out = {}
        for s in "lr":
            prev = None
            for e in sorted(self.plan.events, key=lambda e: e.stroke):
                p = e.pose_r if s == "r" and e.hand in ("r", "both") else (
                    e.pose_l if s == "l" and e.hand in ("l", "both") else None)
                if p is None:
                    continue
                if (prev is not None and 0.4 <= e.stroke - prev[0] < 1.0 and e.kind in ("count", "beat")
                        and norm(sub(list(p.off), list(prev[1].off))) < 5.0):
                    out.setdefault(id(e), set()).add(s)
                prev = (e.stroke + e.hold, p)
        return out

    # the finger chains and their palm side (from the base pose's own relaxed curl)
    def _fingers(self) -> dict:
        sk = self.sk
        out = {}
        for s in "lr":
            # the palm's normal (reference pose), toward the palm: the side the reference middle finger curls to
            hd = unit(sub(sk.p(f"middle_01_{s}"), sk.p(f"hand_{s}")))
            n = unit(cross(hd, sub(sk.p(f"index_01_{s}"), sk.p(f"pinky_01_{s}"))))
            if dot(sub(sk.p(f"middle_03_{s}"), sk.p(f"middle_01_{s}")), n) < 0:
                n = mul(n, -1.0)
            for f in FINGERS:
                joints = [j for j in (f"{f}_metacarpal_{s}", f"{f}_01_{s}", f"{f}_02_{s}", f"{f}_03_{s}")
                          if j in sk.local]
                if len(joints) < 3:
                    continue
                tip, base = sk.p(joints[-1]), sk.p(joints[1] if "metacarpal" in joints[0] else joints[0])
                d = unit(sub(tip, base))
                # r7F: each joint bends about the finger's own hinge, d x n, so + curl moves it toward the palm. It
                # was cross(d, ortho(middle chord, d)): nearly parallel vectors, so one curl flexed some joints, bent
                # others backward (-66 deg) and barely moved the rest (the orchestrator's 'claws')
                ax = unit(cross(d, n))
                if f == "thumb":  # the thumb lies on its side: d x n opened it; flipped it folds in over the palm
                    ax = mul(ax, -1.0)
                out[(s, f)] = {"joints": joints, "axis": ax}
        return out

    def gesture_w(self, s: str, t: float) -> float:
        """0 at the high rest .. 1 on a gesture of hand `s` (the style track's own weights when it draws the hand)."""
        if STYLE_HOOK is not None and hasattr(STYLE_HOOK, "_tracks"):
            w = STYLE_HOOK._tracks(self)[s].at(t)[1]
            return min(1.0, max(w.values() or [0.0]))
        return min(1.0, max([e.weight(t) for e in self.plan.events if e.hand in (s, "both")] or [0.0]))

    def hand_targets(self, s: str, t: float, W) -> tuple:
        """(wrist component point, HandPose blend, pole direction, speak weight, big-gesture weight)."""
        f, r, u = self.fr
        sg = 1.0 if s == "r" else -1.0
        A_l, A_r = (self.actor(self._fk_t("upperarm_" + x, "clavicle_" + x, W)) for x in "lr")
        st_pt = [(A_l[0] + A_r[0]) / 2 + 8.0, (A_l[1] + A_r[1]) / 2, (A_l[2] + A_r[2]) / 2 - 14.0]
        ws = self.plan.speak_w(t)
        if s == "l" and LEFT_RESTS:
            # her left forearm rests on the desk while she speaks and rises only for its own / two-hand gestures:
            # anywhere up near her chest it sat over the mic in the picture (it hangs at sternum height, frame right)
            ws *= max([e.weight(t) for e in self.plan.events if e.hand in ("l", "both")] or [0.0])
        wg = self.gesture_w(s, t)
        self._wg[s] = wg  # hand_rot_p fades YAW_BASE in with it
        self._ws[s] = ws
        if STYLE_HOOK is not None and hasattr(STYLE_HOOK, "hand"):
            hp, big = STYLE_HOOK.hand(self, s, t)  # the whole hand track (co-articulation, wrist lead, cascade)
        else:
            parts = []  # (weight, HandPose)
            big = 0.0
            for e in self.plan.events:
                w = e.weight(t)
                if w <= 0:
                    continue
                p = e.pose_r if s == "r" and e.hand in ("r", "both") else (
                    e.pose_l if s == "l" and e.hand in ("l", "both") else None)
                if p is None:
                    continue
                parts.append((w, p))
                if e.big or e.kind in ("open", "size", "deictic", "count"):
                    big = max(big, w)
            we = min(1.3, sum(w for w, _ in parts))  # > 1: an overshoot past the goal (envelope hook), then settle
            extra = {}
            if STYLE_HOOK is not None and hasattr(STYLE_HOOK, "fingers"):
                for e in self.plan.events:
                    w = e.weight(t)
                    if w > 0 and (e.hand == s or e.hand == "both"):
                        for k, v in (STYLE_HOOK.fingers(e, s, w) or {}).items():
                            extra[k] = extra.get(k, 0.0) + float(v)
            base = HIGH_REST
            tot = sum(x for x, _ in parts) or 1.0
            hp = blend_poses([(1.0 - we, base)] + [(w / tot * we, p) for w, p in parts])
            if extra:
                sh = dict(hp.shape) if isinstance(hp.shape, dict) else dict(SHAPES.get(hp.shape, {}))
                hp = replace(hp, shape={k: sh.get(k, 0.0) + extra.get(k, 0.0) for k in FINGERS})
        off = hp.off
        acc = self.accent(s, t)
        tgt = [st_pt[0] + off[0] + acc[0], st_pt[1] + sg * (off[1] + acc[1]), st_pt[2] + off[2] + acc[2]]
        if s == "l":  # the mic-side hand: 1 cm back, a little lower, and never further to her own left than
            #           LEFT_MAX_LAT of the sternum point (it works right of centre, off the mic), whatever drew its pose
            tgt = [tgt[0] - 1.0 * wg, tgt[1], tgt[2] - 0.8 * wg]  # at the rest the two hands meet level
            lat = dot(sub(tgt, st_pt), [0.0, -1.0, 0.0])  # how far to her left of the sternum point
            if lat > LEFT_MAX_LAT:
                tgt = [tgt[0], tgt[1] + (lat - LEFT_MAX_LAT), tgt[2]]
            two = any(e.hand == "both" and e.weight(t) > 0.3 for e in self.plan.events)
            if not two:  # and under the mic in the picture (it hangs at sternum height, frame right)
                tgt[2] = min(tgt[2], st_pt[2] + LEFT_MAX_Z)
        # pauses: down to the desk rest (forearms on the edge)
        e0, w0, _ = self.elbow_rest(s, W)
        tgt = [w0[i] + (tgt[i] - w0[i]) * ws for i in range(3)]
        if ws < 1.0 and STYLE_HOOK is not None and hasattr(STYLE_HOOK, "rest_life"):  # never frozen at the desk
            d_off, d_fing = STYLE_HOOK.rest_life(self, s, t)
            tgt = [tgt[0] + d_off[0] * (1.0 - ws), tgt[1] + sg * d_off[1] * (1.0 - ws), tgt[2]]
        if s == "r" and ws > 0:  # her right hand works on her right of the sternum point (left of frame, off the mic),
            #                       except a deictic to the panel, which crosses on purpose
            cross = any(e.kind == "deictic" and e.pose_r.off[1] < 12.0 and e.weight(t) > 0.2 for e in self.plan.events)
            lat = dot(sub(tgt, st_pt), [0.0, 1.0, 0.0])
            lat_min = RIGHT_MIN_LAT * wg  # a gesture's apex; the rest's hands meet at the midline, under the mic
            if not cross and lat < lat_min:
                tgt = [tgt[0], tgt[1] + (lat_min - lat) * ws, tgt[2]]
        tgt[2] += 4.0 * math.sin(math.pi * ws)  # an arc up off the desk and back, never through it
        if s == "l":  # and the mic-side hand's path bows in toward her midline, away from the mic in every camera
            tgt = add(tgt, mul(self.fr[1], 4.0 * math.sin(math.pi * ws)))
        # elbows out and a little down; the mic-side elbow lower still (its upward swing meets the mic)
        pole = (add(add(mul(f, -0.3), mul(r, 0.9)), mul(u, -0.35)) if s == "r"
                else add(add(mul(f, -0.3), mul(r, -0.9)), mul(u, -0.5)))
        if wg < 1.0:  # at the high rest the elbows hang: relaxed down and a little out, shoulders down (r7F)
            pr_ = add(add(mul(f, REST_POLE[0]), mul(r, REST_POLE[1] * (1.0 if s == "r" else -1.0))), mul(u, REST_POLE[2]))
            pole = add(mul(unit(pole), wg), mul(unit(pr_), 1.0 - wg))
        pole_rest = sub(self.comp(e0), self._fk_t("upperarm_" + s, "clavicle_" + s, W))
        pole = add(mul(unit(pole), ws), mul(unit(pole_rest), 1.0 - ws))
        rest_hp = HandPose((0.0, 0.0, 0.0), pron=self.sy.pronation, ext=self.ext_base.get(s, 10.0), shape="relaxed")
        hp = blend_poses([(ws, hp), (1.0 - ws, rest_hp)])
        if ws < 1.0 and STYLE_HOOK is not None and hasattr(STYLE_HOOK, "rest_life"):
            sh = dict(hp.shape) if isinstance(hp.shape, dict) else dict(SHAPES.get(hp.shape, {}))
            hp = replace(hp, shape=sh | {k: sh.get(k, 0.0) + d_fing.get(k, 0.0) * (1.0 - ws) for k in set(FINGERS) | set(d_fing)})
        return self.comp(tgt), hp, pole, ws, big

    def pose(self, t: float = 0.0, gestures=None) -> dict:
        if not self._ready:
            return super().pose(t, gestures or [])
        sk, sy = self.sk, self.sy
        f, r, u = self.fr
        lean = self.plan.lean_at(t)
        turn, lift = self.torso(t)
        self.sy = replace(sy, lean=lean, twist=turn)
        self._ready = False
        try:
            locs = super().pose(-1.0, [])  # legs, pelvis, spine, neck by seatkit at this lean/turn
        finally:
            self.sy, self._ready = sy, True
        W = self._world_from(locs)
        # head roll on neck_02/head about the forward axis (+ = toward her right shoulder)
        roll = self.plan.roll_at(t)
        if roll:  # cumulative: neck_02 takes 40 %, the head (its child) the full roll (it read 60 % before)
            for b, share in (("neck_02", 0.4), ("head", 1.0)):
                ang = -roll * share if self._rhs else roll * share
                W[b] = [W[b][0], qmul(axis_angle(f, ang), W[b][1])]
            W["head"] = [self._fk_t("head", "neck_02", W), W["head"][1]]
        self._fit_poses(W)  # once: each gesture's goal fitted to the elevation lines
        # arms by the plan
        for s, (cl, ua, la, ha) in S.ARMS.items():
            sg = 1.0 if s == "r" else -1.0
            W[cl] = [self._fk_t(cl, sk.parent[cl], W),
                     qmul(axis_angle(f, sg * lift[s] - sg * sy.clavicle_drop),
                          qmul(axis_angle(u, -sg * sy.clavicle_fwd),
                               qmul(self._delta(sk.parent[cl], W), sk.q(cl))))]
            sh = self._fk_t(ua, cl, W)
            l1, l2 = self.A[s]
            wrist, hp, pole, ws, _ = self.hand_targets(s, t, W)
            elbow, wrist = self.swivel(s, sh, wrist, l1, l2, pole, W, ws)
            back = ortho(sub(elbow, sh), unit(sub(wrist, sh)))
            W[ua] = [sh, self._aim(ua, la, sub(elbow, sh), back, front_rest=mul(f, -1.0))]
            W[la] = [self._fk_t(la, ua, W), self._aim(la, ha, sub(wrist, elbow), back, front_rest=mul(f, -1.0))]
            W[ha] = [self._fk_t(ha, la, W), self.hand_rot_p(s, hp, sub(wrist, elbow))]
            self._finger_pose(s, hp, W)
            if STYLE_HOOK is not None and hasattr(STYLE_HOOK, "finger_post"):
                STYLE_HOOK.finger_post(self, s, hp, W)  # e.g. the fingers' spread in the palm's plane
        return self._locals(W)

    def torso(self, t: float) -> tuple:
        """(turn deg, {side: shoulder lift deg}) at t: the torso turns a little toward the gesturing hand (right
        gestures turn right, a deictic to her left turns left), the shoulders lift with big gestures. Override it
        (agent-10's track performer) together with hand_targets()."""
        turn, lift = 0.0, {"l": 0.0, "r": 0.0}
        hooked = STYLE_HOOK.weights(self, t) if STYLE_HOOK is not None and hasattr(STYLE_HOOK, "weights") else None
        for i, e in enumerate(self.plan.events):
            w = hooked.get(i, 0.0) if hooked is not None else e.weight(t)
            if w <= 0:
                continue
            side = -1.0 if (e.kind == "deictic" and e.pose_r.off[1] < 0) else (1.0 if e.hand == "r" else 0.0)
            turn += 4.0 * w * side
            for s in ("l", "r") if e.hand == "both" else (e.hand,):
                if e.big or e.kind in ("open", "size", "count"):
                    lift[s] = max(lift[s], 3.0 * w)
        return turn, lift

    ACCENT_S = 0.24   # the accent's length: a dip (or push) into the stressed syllable and the rebound
    ACCENT_CM = 3.5

    def accent(self, s: str, t: float) -> tuple:
        """The stroke itself, on top of the pose: every event's hand makes a short accent at its stroke (agent-10: a
        stroke whose pose equals the one before barely moved the wrist; the count's next finger alone is not a
        gesture): beats, presses and opens dip and rebound (down then up), counts and points push forward and back.
        (fwd, out, up) cm in the sternum frame of that hand."""
        fx = ox = zx = 0.0
        if STYLE_HOOK is not None and hasattr(STYLE_HOOK, "hand"):
            return fx, ox, zx  # agent-08's human-motion layer accents its own strokes (e6b8f981): never twice
        for e in self.plan.events:
            if not (e.hand == s or e.hand == "both") or s not in self._accented.get(id(e), ()):
                continue
            u = (t - (e.stroke - 0.06)) / self.ACCENT_S
            if not 0.0 <= u <= 1.0:
                continue
            a = math.sin(math.pi * u) * self.ACCENT_CM * (0.6 + 0.8 * min(1.0, e.energy))
            if s == "l" and e.hand == "both":
                a *= 0.5  # the mic-side hand stays quiet
            if e.kind in ("count", "deictic") or e.detail in ("raise_finger", "point"):
                fx += a
            else:
                zx -= a
        return fx, ox, zx

    CLEAR_WANT = 3.8  # cm: the 3 cm line plus a margin for the model
    SIDE_WANT = 0.5  # cm: when set, the torso's SIDE needs only this (the bust keeps CLEAR_WANT): relaxed arms lie
    #                   against the ribcage (the orchestrator's 30 deg rest line can't be met 3.8 cm off it)

    SWIVEL_LOW = True  # r7F (agent-13): of the elbow positions that clear, the LOWEST (it hung); else the first one
    #                    out from the pole, which swung it up and out (the upper arm 78 deg off hanging at apexes)

    def swivel(self, s, sh, wrist, l1, l2, pole, W, ws):
        """Two-bone IK, then the elbow about the shoulder-wrist axis: of the positions round the circle (5 deg steps)
        whose upper arm clears the torso/breast model by CLEAR_WANT (and the mic, the boom, the desk, never in across
        the body nor back behind the shoulder), the lowest; none clearing: the clearest (while she speaks; the desk
        rest keeps its pole)."""
        elbow, wr = S.two_bone(sh, wrist, l1, l2, pole)
        if ws < 0.5:
            return elbow, wr
        A = {b: self.actor(W[b][0]) for b in ("spine_03", "spine_05")}
        axis = unit(sub(wr, sh))
        side = self.fr[1] if s == "r" else mul(self.fr[1], -1.0)
        st_ = self.set
        sha = self.actor(sh)
        best, low = None, None
        steps = [0] + [k * sg for k in range(1, 37) for sg in (1, -1)] if self.SWIVEL_LOW else \
            [0] + [k * sg for k in range(1, 9) for sg in (1, -1)]
        step = 5.0 if self.SWIVEL_LOW else 10.0
        for k in steps:
            if self.SWIVEL_LOW and k == -36:
                continue
            pk = qrot(axis_angle(axis, step * k), pole)
            e, w2 = S.two_bone(sh, wrist, l1, l2, pk)
            if dot(sub(e, sh), side) < 0:  # never swing the elbow in across the body
                continue
            ea = self.actor(e)  # nor into the mic: box B's bodycheck had her left elbow 9 cm from the capsule
            if st_.mic and norm(sub(ea, st_.mic)) < st_.mic_radius + 2.5:
                continue
            if st_.boom and S.poly_dist(ea, st_.boom) < st_.boom_radius + 3.5:
                continue
            if self.SWIVEL_LOW:
                if ea[0] < sha[0] - 6.0:  # nor back behind her
                    continue
                if ea[0] > st_.desk_near - 1.0:  # over the desk: the elbow on it at most
                    if ea[2] < st_.desk_top + self.sy.elbow_r + 1.0:
                        continue
                else:  # behind its near edge (the desk rest: the forearm across the edge): the forearm clears the edge
                    wa = self.actor(w2)
                    if wa[0] > st_.desk_near:
                        z_edge = ea[2] + (wa[2] - ea[2]) * (st_.desk_near - ea[0]) / max(1e-6, wa[0] - ea[0])
                        if z_edge < st_.desk_top + self.FOREARM_R:
                            continue
            A2 = {**A, "upperarm_" + s: sha, "lowerarm_" + s: ea}
            c, c_side, c_bust = clearance(A2, None, s, self.tor, parts=True)
            if self.SIDE_WANT is not None:  # the bust by CLEAR_WANT (at the desk rest REST_BUST_WANT), her side only
                #                             by SIDE_WANT
                k_ = smooth(min(1.0, self._wg.get(s, 1.0) / 0.5))  # the full line from half a gesture on (the
                bw = self.CLEAR_WANT * k_ + self.REST_BUST_WANT * (1.0 - k_)  # build's gate counts it there)
                c = min(c_bust - bw, c_side - self.SIDE_WANT) + self.CLEAR_WANT
            if best is None or c > best[0]:
                best = (c, e, w2)
            if c >= self.CLEAR_WANT:
                if not self.SWIVEL_LOW:
                    return e, w2
                ua = sub(ea, sha)  # abduction: the upper arm's lean out to her side, in her frontal plane
                abd = math.degrees(math.atan2(abs(ua[1]), max(1e-6, -ua[2]))) if ua[2] < 0 else 90.0
                key = (abd > self.ABD_MAX, ea[2])  # within the abduction line first, then the lowest
                if low is None or key < low[0]:
                    low = (key, e, w2)
        if low is not None:
            return low[1], low[2]
        return (best[1], best[2]) if best else (elbow, wr)

    REST_BUST_WANT = 0.0  # cm the upper arm off the breast MODEL at the desk rest (the orchestrator, 08 Nov: the forearms
    #   on the desk bring the elbows forward past the side of her chest, as any seated arm; the sphere model is crude
    #   there, agent-02's mesh measure judges the rest)
    FOREARM_R = 3.0  # cm the forearm's half-thickness (+ sleeve) where it crosses the desk's near edge
    ELEV_HIGH = 60.0  # deg for an apex at/above upper_chest (the orchestrator's ruling (B), 08 Nov)
    HIGH_OVER_SHOULDER = 2.0  # cm: a wrist goal this far over the shoulder joint is a high apex (upper_chest = +5)
    LOW_DOWN = 0.6  # cm down per cm in, for a low stroke
    HIGH_OUT = 0.3  # cm out per cm in, for a high one (0.6 took the CU key beats out of its frame, 0.29)
    HIGH_DOWN = 0.0  # and for a high one (it comes in only: lowered, the CU lost the key beats, 0.14)
    FIT_MARGIN = 2.0  # deg under each line the goals are fitted to (agent-13: 60.03 on a 60 line)
    REACH_MAX = 24.0  # cm a goal comes in at most
    ABD_MAX = 35.0  # deg the upper arm's abduction at most when a clearing elbow allows (the orchestrator's row)
    ELEV_REST, ELEV_STROKE = 40.0, 45.0  # deg the upper arm off hanging, at most (agent-13's lines, the orchestrator:
    #   rest 40 with the forearms supported on the desk, 30 hanging;
    #   the clearance by shoulder FLEXION, the elbow forward and down, not abducted out: chicken wings)
    LOWER_APEX = False  # lower a high apex too when pulling it in can't meet the cap (off: it emptied CAM_CU's frame,
    #                     0.0, and put fingers in the desk; the high strokes keep their elevation, see ELEV_STROKE)
    REACH_STEP = (2.0, 0.0)  # cm per try: the wrist goal in toward her shoulder (down put her fingers in the desk)

    def elevation(self, sh, elbow) -> float:
        """deg the upper arm off hanging straight down (flexion and abduction together)."""
        return math.degrees(math.acos(max(-1.0, min(1.0, -dot(unit(sub(elbow, sh)), self.fr[2])))))

    def cap_at(self, sh, goal, wg) -> tuple:
        """(elevation cap deg, highness 0..1) for a wrist goal: 45 for a stroke under upper_chest, 60 at upper_chest ..
        collarbone (shoulder + 3 .. + 5 cm ramp; the orchestrator's (B), agent-13's classes), blended from ELEV_REST by
        the gesture weight. Continuous, so the wrist never jumps where a stroke crosses the line."""
        h = dot(sub(goal, sh), self.fr[2])
        k = max(0.0, min(1.0, (h - 3.0) / 2.0))  # below upper_chest (shoulder + 5) 45, at it 60
        return self.ELEV_REST + (self.ELEV_STROKE + (self.ELEV_HIGH - self.ELEV_STROKE) * k - self.ELEV_REST) * wg, k

    def _fit_poses(self, W) -> None:
        """Each event's wrist goal (and the high rest, reported) moved in toward her, a low stroke also a little down,
        by the least distance (bisection) at which the lowest clearing elbow meets its elevation line (cap_at). On the
        GOALS, not per frame: per frame the pull jumped where the line could not be met (800 cm/s); the track then
        glides between fitted goals."""
        if getattr(self.plan, "_fitted", False) or not self.SWIVEL_LOW:
            return
        self.plan._fitted = True
        f, r, u = self.fr
        A_l, A_r = (self.actor(self._fk_t("upperarm_" + x, "clavicle_" + x, W)) for x in "lr")
        st_pt = [(A_l[0] + A_r[0]) / 2 + 8.0, (A_l[1] + A_r[1]) / 2, (A_l[2] + A_r[2]) / 2 - 14.0]
        self.fit_log = []

        def fit(hp: HandPose, s: str, rest: bool = False) -> HandPose:
            sg = 1.0 if s == "r" else -1.0
            sh = self._fk_t("upperarm_" + s, "clavicle_" + s, W)
            l1, l2 = self.A[s]
            pole = (add(add(mul(f, -0.3), mul(r, 0.9)), mul(u, -0.35)) if s == "r"
                    else add(add(mul(f, -0.3), mul(r, -0.9)), mul(u, -0.5)))

            def goal(off):
                return self.comp([st_pt[0] + off[0], st_pt[1] + sg * off[1], st_pt[2] + off[2]])

            def elev(off):
                wg0 = self._wg.get(s)
                self._wg[s] = 0.0 if rest else 1.0  # the swivel's bust line for this goal
                try:
                    e, _ = self.swivel(s, sh, goal(off), l1, l2, pole, W, 1.0)
                finally:
                    if wg0 is None:
                        self._wg.pop(s, None)
                    else:
                        self._wg[s] = wg0
                return self.elevation(sh, e)

            if not rest and hp.off[2] > APEX_MAX_Z:  # the variation's amp took it past the collarbone line
                hp = replace(hp, off=(hp.off[0], hp.off[1], APEX_MAX_Z))
            cap, k = self.cap_at(sh, goal(hp.off), 0.0 if rest else 1.0)
            cap -= self.FIT_MARGIN
            e0 = elev(hp.off)
            if e0 <= cap:
                return hp
            down = 0.0 if rest else self.LOW_DOWN * (1.0 - k) + self.HIGH_DOWN * k

            out_ = 0.0 if rest else self.HIGH_OUT * k

            def moved(d):  # in, down (low strokes), out to her side (high ones: a hand near her midline at the
                #            collarbone needed the elbow up over 60)
                return (hp.off[0] - d, hp.off[1] + out_ * d, hp.off[2] - down * d)

            # scan in (elevation is not monotonic: too close, the clearance swings the elbow back up), take the least
            # pull that meets the line, else the lowest elevation; then refine between the last two samples
            best_d, best_e, prev = 0.0, e0, 0.0
            d, hi = 1.5, None
            while d <= self.REACH_MAX + 1e-6:
                ed = elev(moved(d))
                if ed <= cap:
                    hi = d
                    break
                if ed < best_e:
                    best_d, best_e = d, ed
                prev, d = d, d + 1.5
            if hi is not None:
                lo = prev
                for _ in range(5):
                    mid = (lo + hi) / 2.0
                    if elev(moved(mid)) <= cap:
                        hi = mid
                    else:
                        lo = mid
            else:
                hi = best_d
            out = replace(hp, off=moved(hi))
            self.fit_log.append({"s": s, "cap": round(cap, 1), "from": round(e0, 1), "to": round(elev(out.off), 1),
                                 "in_cm": round(hi, 1), "off": [round(x, 1) for x in out.off]})
            return out

        for e in self.plan.events:
            if e.hand in ("r", "both"):
                e.pose_r = fit(e.pose_r, "r")
            if e.pose_l is not None and e.hand in ("l", "both"):
                e.pose_l = fit(e.pose_l, "l")
        self.rest_fit = {s: fit(HIGH_REST, s, rest=True).off for s in "lr"}
        self._gs_tracks = None  # the style track was drawn (torso() asks for its weights) from the unfitted goals

    def _world_from(self, locs: dict) -> dict:
        """seatkit's local result back to component transforms for the bones it set (FK over its own chain)."""
        sk = self.sk
        W = {}
        for b in sk.order:
            if b not in locs:
                continue
            p = sk.parent.get(b)
            loc = locs[b]
            if p in W:
                pt, pq = W[p]
            elif p:
                pt, pq = sk.p(p), sk.q(p)
            else:
                W[b] = [list(loc["t"]), list(loc["q"])]
                continue
            W[b] = [add(pt, qrot(pq, loc["t"])), qnorm(qmul(pq, loc["q"]))]
        return W

    def hand_rot_p(self, s, hp: HandPose, forearm):
        """seatkit's hand frame from a HandPose (pronation, extension), fingers continuing the forearm."""
        sk = self.sk
        f, r, u = self.fr
        side = r if s == "r" else mul(r, -1.0)
        d0 = sub(sk.p("middle_01_" + s), sk.p("hand_" + s))
        a0 = sub(sk.p("pinky_01_" + s), sk.p("index_01_" + s))
        fa = unit(forearm)
        hz = ortho(fa, u) if abs(dot(fa, u)) < 0.98 else f
        wg = self._wg.get(s, 1.0)
        yw = math.radians(getattr(hp, "yaw", 0.0) + YAW_BASE.get(s, 0.0) * wg + REST_YAW * (1.0 - wg))
        hz = unit(add(mul(hz, math.cos(yw)), mul(ortho(side, hz), math.sin(yw))))
        ws = self._ws.get(s, 1.0)  # speaking: a true extension; at the desk rest the old pitch (its pose was tuned on it)
        pitch = math.asin(max(-1.0, min(1.0, dot(fa, u)))) + math.radians(hp.ext * (1.0 - ws))
        fingers = unit(add(mul(hz, math.cos(pitch)), mul(u, math.sin(pitch))))
        pr = math.radians(hp.pron)
        flat = ortho(side, fingers)
        up_ = ortho(u, fingers) if abs(dot(u, fingers)) < 0.98 else ortho(mul(f, -1.0), fingers)
        across = unit(add(mul(flat, math.cos(pr)), mul(up_, -math.sin(pr))))
        if hp.ext and ws > 0:  # r7F: a true extension, about the palm's own across axis (back of the hand); it was a pitch about
            #         world up, which on a thumb-up hand (counts, raise_finger: pron 80-95, ext 40-45) bent it radially
            n_ref = unit(cross(sub(sk.p("middle_01_" + s), sk.p("hand_" + s)),
                               sub(sk.p("index_01_" + s), sk.p("pinky_01_" + s))))
            if dot(sub(sk.p("middle_03_" + s), sk.p("middle_01_" + s)), n_ref) < 0:
                n_ref = mul(n_ref, -1.0)
            sgn = 1.0 if dot(cross(d0, a0), n_ref) > 0 else -1.0
            palm = mul(unit(cross(fingers, across)), sgn)  # toward the palm, in the goal frame
            k = cross(fingers, mul(palm, -1.0))
            if norm(k) > 1e-6:
                fingers = qrot(axis_angle(k, hp.ext * ws), fingers)
        return qmul(S.frame_to_frame(d0, a0, fingers, across), sk.q("hand_" + s))

    def _finger_pose(self, s, hp: HandPose, W):
        sk = self.sk
        shape = SHAPES.get(hp.shape, {}) if isinstance(hp.shape, str) else hp.shape
        dh = qmul(W["hand_" + s][1], qinv(sk.q("hand_" + s)))
        for f in FINGERS:
            info = self._finger_info.get((s, f))
            if not info:
                continue
            curl = float(shape.get(f, 0.0)) if isinstance(shape, dict) else 0.0
            joints = info["joints"]
            axis = qrot(dh, info["axis"])  # the hinge, in the hand's current frame
            cum = [0.0, 0.0, 0.0, 1.0]
            parent = "hand_" + s
            for j in joints:
                if "metacarpal" in j:
                    q = qmul(dh, sk.q(j))
                else:
                    k = j.split("_")[1]
                    share = {"01": 0.8, "02": 1.0, "03": 0.8}[k]
                    pip = float(shape.get("_pip_" + f, 0.0)) if isinstance(shape, dict) and k != "01" else 0.0
                    cum = qmul(axis_angle(axis, curl * share + pip), cum)  # (+ the middle/end joints' own drift)
                    q = qmul(cum, qmul(dh, sk.q(j)))
                W[j] = [self._fk_t(j, parent, W) if parent in W else sk.p(j), q]
                parent = j


def blend_poses(parts: list) -> HandPose:
    tw = sum(w for w, _ in parts) or 1.0
    off = [sum(w * p.off[i] for w, p in parts) / tw for i in range(3)]
    pron = sum(w * p.pron for w, p in parts) / tw
    ext = sum(w * p.ext for w, p in parts) / tw
    yaw = sum(w * getattr(p, "yaw", 0.0) for w, p in parts) / tw
    shapes = {}
    for w, p in parts:
        sh = SHAPES.get(p.shape, {}) if isinstance(p.shape, str) else p.shape
        for k in FINGERS + tuple(x for x in sh if x.startswith("_")):  # "_spread" etc. (gesture_style) ride along
            shapes[k] = shapes.get(k, 0.0) + w * float(sh.get(k, 0.0)) / tw
    return HandPose(tuple(off), pron, ext, shapes, yaw)


YAW_BASE = {"r": 10.0, "l": 0.0}  # deg her right fingers always turn out a little: turned in, they reached the mic
#   (40 with the mic at her chest; 30 with it at her mouth: the wrist bent 37-45 deg; at 25 the mic hides the hand)
RIGHT_MIN_LAT = 15.0  # cm her right hand stays to her right of the sternum point while she speaks
LEFT_RESTS = False  # r7b: the left hand rested on the desk between its own gestures while the mic hung at her sternum;
#                     with the mic moved up to her mouth (the orchestrator, 08 Nov) it gestures like the right
LEFT_MAX_LAT = 16.0  # r7F: 9 with the mic at her chest (MIC_L)
LEFT_SHARE = 0.58  # the left's move on a two-hand stroke, of the right's
LEFT_TWO = (24.0, 9.0, -2.0)  # cm her left hand on a two-hand gesture (agent-10, see plan_from_sheet)
LEFT_MAX_Z = 40.0  # cm over the sternum point for her left hand (no cap with the mic at her mouth)  # cm: her left hand stays at least 3 cm to her RIGHT of the sternum point while she speaks

FRAME_WANT = {"CAM_MCU": 0.6, "CAM_MCU_L": 0.6, "CAM_CU": 0.3, "CAM_WIDE": 0.95}  # the orchestrator's lines


def hands_in_frame(rig: dict, A: dict, margin: float = 0.01) -> bool:
    """At least one hand fully in the picture: its wrist and the index/middle/pinky/thumb tips (agent-09's gate)."""
    for s in "lr":
        pts = [A.get(b) for b in ("hand_" + s, f"index_03_{s}", f"middle_03_{s}", f"pinky_03_{s}", f"thumb_03_{s}")]
        uv = [S.project(rig, p) for p in pts if p is not None]
        if uv and all(x is not None and margin <= x[0] <= 1 - margin and margin <= x[1] <= 1 - margin for x in uv):
            return True
    return False


def metrics(perf: Performer, t0: float, t1: float, fps: float = 30.0) -> dict:
    """Numbers for the body rows on [t0, t1): gesture onsets/s while speaking, hands-above-desk share while speaking,
    wrist travel cm/s, the minimum upper-arm clearance (per side) and every seatkit contact issue."""
    st = perf.set
    n = int((t1 - t0) * fps)
    speak_n, above, travel, prev = 0, 0, 0.0, None
    clear = {"l": 1e9, "r": 1e9}
    issues = []
    for i in range(n):
        t = t0 + i / fps
        F = perf.fk(perf.pose(t))
        A = {b: perf.actor(v[0]) for b, v in F.items()}
        c = S.check(perf, F)
        ws = perf.plan.speak_w(t)
        skip = ("desk.elbow_off", "desk.elbow_hangs", "desk.forearm_unsupported") if ws > 0.1 else ()
        issues.extend({**x, "t": round(t, 2)} for x in c["issues"] if x["code"] not in skip)
        wr = [A["hand_l"], A["hand_r"]]
        if ws > 0.5:
            speak_n += 1
            above += sum(1 for w in wr if w[2] > st.desk_top + 6.0) / 2.0
            for s in "lr":
                clear[s] = min(clear[s], clearance(A, F, s, perf.tor))
        if prev is not None:
            travel += sum(norm(sub(a, b)) for a, b in zip(wr, prev))
        prev = wr
    speak_s = speak_n / fps
    onsets = [e for e in perf.plan.events if t0 <= e.stroke < t1]
    return {"t": [t0, t1], "speak_s": round(speak_s, 2),
            "gesture_onsets_per_s": round(len(onsets) / speak_s, 2) if speak_s else None,
            "hands_above_desk_frac": round(above / speak_n, 3) if speak_n else None,
            "wrist_travel_cm_per_s": round(travel / max(1e-6, (t1 - t0)) / 2.0, 1),
            "upperarm_torso_clear_cm": {s: round(v, 1) for s, v in clear.items()},
            "issues": issues[:20], "n_issues": len(issues)}


def build(data: dict, st, sy, sheet: dict, cues: dict, tilts: list, length_s: float, fps: int = 30,
          check_every: int = 6, timing: list | None = None, on_cam: list | None = None,
          frame_want: dict | None = None, track_out: str | None = None) -> tuple:
    """seatkit.build for the performance: the seated pose with the plan driving the upper body, as tracks (constant
    for the bones that never move, per key for spine, neck, head, clavicles, arms, hands and fingers). Returns (doc
    for perform.py's WRITE, summary with the checks and the body rows' numbers)."""
    sk = S.Skeleton.from_read(data)
    plan = plan_from_sheet(sheet, cues, tilts, timing=timing, on_cam=on_cam)
    se, tuned = S.autotune(sk, st, sy)
    perf = Performer(sk, st, se.sy, plan)
    n = int(round(length_s * fps)) + 1
    first = perf.pose(0.0)
    const = {b: data["local"][b] for b in data["tracks"] if b in data["local"]}
    const.update(first)
    moving = sorted(set(first) - {"pelvis"} - {b for s in "lr" for b in S.LEGS[s]})
    keyed = {b: [] for b in moving}
    issues, clear = [], {"l": 1e9, "r": 1e9}
    side_c, bust_c = {"l": 1e9, "r": 1e9}, {"l": 1e9, "r": 1e9}
    rest_bust = {"l": 1e9, "r": 1e9}
    framing = {}
    rest_clear = 1e9
    track = []  # track_out: the arm track per frame (on the box for his body: his skeleton never leaves it)
    for i in range(n):
        t = i / fps
        loc = perf.pose(t)
        for b in moving:
            v = loc.get(b, const[b])
            keyed[b].append({k: [round(x, 6) for x in v[k]] for k in ("t", "q", "s")})
        if track_out:
            track.append(track_frame(perf, plan, perf.fk({**const, **loc}), i, t))
        if i % check_every == 0:
            F = perf.fk({**const, **loc})
            c = S.check(perf, F)
            ws = plan.speak_w(t)
            skip = ("desk.elbow_off", "desk.elbow_hangs", "desk.forearm_unsupported") if ws > 0.1 else ()
            live = next((cm for a, b, cm in plan.on_cam if a <= t < b), None) if plan.on_cam else "*"
            for x in c["issues"]:
                if x["code"] in skip:
                    continue
                if x["code"] == "mic.hides_hand" and live != "*" and (live is None or f" {live} " not in x["message"]):
                    continue  # a mic overlap counts only in the camera that is cut in (and only when she is on it)
                issues.append({**x, "t": round(t, 2)})
            if ws > 0.5:
                A = {b: perf.actor(v[0]) for b, v in F.items()}
                for s in "lr":
                    # per arm while it is UP and gesturing; the left resting on the desk (LEFT_RESTS) is reported apart
                    up = s == "r" or not LEFT_RESTS or any(e.hand in ("l", "both") and e.weight(t) > 0.3
                                                           for e in plan.events)
                    c_, c_side, c_bust = clearance(A, F, s, perf.tor, parts=True)
                    if up:
                        clear[s] = min(clear[s], c_)
                        side_c[s] = min(side_c[s], c_side)
                        if perf.gesture_w(s, t) >= 0.5:  # the bust line in gestures; at the desk rest the arm lies
                            bust_c[s] = min(bust_c[s], c_bust)  # beside the chest (agent-02's mesh judges it)
                        else:
                            rest_bust[s] = min(rest_bust[s], c_bust)
                    else:
                        rest_clear = min(rest_clear, c_)
                cam = next((c for a, b, c in plan.on_cam if a <= t < b), None)
                if cam and st.rigs and cam in st.rigs:
                    fr = framing.setdefault(cam, [0, 0])
                    fr[1] += 1
                    fr[0] += int(hands_in_frame(st.rigs[cam], A))
    for b in moving:
        const.pop(b, None)
    sref = data.get("skel_t") or {}

    def anim_t(b, tt):  # as seatkit.build: the engine adds (mesh ref - skeleton ref) to a bone's translation
        if b not in sref:
            return tt
        return [x - (m - k) for x, m, k in zip(tt, sk.local[b]["t"], sref[b])]

    for b in list(const):
        const[b] = {**const[b], "t": anim_t(b, const[b]["t"])}
    for b in keyed:
        keyed[b] = [{**k_, "t": anim_t(b, k_["t"])} for k_ in keyed[b]]
    rows = {"upperarm_torso_clear_cm": {s: round(v, 1) for s, v in clear.items()},
            "upperarm_bust_clear_cm": {s: round(v, 1) for s, v in bust_c.items()},
            "upperarm_side_clear_cm": {s: round(v, 1) for s, v in side_c.items()},
            "rest_upperarm_bust_model_cm": {s: round(v, 1) for s, v in rest_bust.items()},  # (the model; mesh judges)
            "left_resting_arm_clear_cm": round(rest_clear, 1) if rest_clear < 1e8 else None,
            "hands_in_frame_frac": {c: round(a / b, 3) for c, (a, b) in framing.items() if b}}
    for c, want in {**FRAME_WANT, **(frame_want or {})}.items():  # frame_want: a presenter's own lines
        got = rows["hands_in_frame_frac"].get(c)
        if got is not None and got < want:
            issues.append({"code": "body.hands_out_of_frame", "message": f"hands in frame in {got:.0%} of {c}'s "
                           f"speaking frames (line {want:.0%})", "value": got})
    if STYLE_HOOK is not None and hasattr(STYLE_HOOK, "report"):  # the variation and never-frozen rows
        extra = STYLE_HOOK.report(perf, length_s)
        rows.update(extra.get("rows", {}))
        issues.extend(extra.get("issues", []))
    if Performer.SIDE_WANT is None:
        ok_clear = min(clear.values()) >= 3.0
        worst = min(clear.values())
    else:  # the bust by 3, her side only not into it
        ok_clear = min(bust_c.values()) >= 3.0 and min(side_c.values()) >= 0.0
        worst = min(min(bust_c.values()), min(side_c.values()) + 3.0)
    if not ok_clear:
        issues.append({"code": "body.arm_torso", "message": f"upper arm within {worst:.1f} cm of the "
                       "torso/breast model (line 3)", "value": worst})
    summary = {"pass": not issues, "issues": issues[:30], "n_issues": len(issues), "tuned": tuned, "rows": rows,
               "events": len(plan.events), "moving_bones": len(moving),
               "hooks": {"style": bool(STYLE_HOOK), "timing": bool(timing)}, "frame": {"fwd": perf.F["fwd"],
                                                                                   "right": perf.F["right"]},
               "rest": S.check(perf, perf.fk({**const, **first}))}
    doc = {"length_s": length_s, "fps": fps, "n_keys": n, "const": const, "keyed": keyed}
    if track_out:
        Path(track_out).parent.mkdir(parents=True, exist_ok=True)
        Path(track_out).write_text(json.dumps(track_doc(plan, fps, track)))
        summary["arm_track"] = {"path": str(track_out), "frames": len(track)}
    return doc, summary


TRACK_BONES = [f"{b}_{s}" for s in "lr" for b in ("clavicle", "upperarm", "lowerarm", "hand")] + \
    [f"{f}_{j}_{s}" for s in "lr" for f in ("thumb", "index", "middle", "ring", "pinky") for j in ("01", "02", "03")] + \
    ["spine_03", "spine_05", "neck_01", "head"]


def track_frame(perf, plan, F, i: int, t: float) -> dict:
    """One frame of the arm track for agent-13's naturalness rows (actor frame, cm, 0.1 mm: 0.01 cm read a slow drift
    as frozen)."""
    return {"f": i, "t": round(t, 4), "speak_w": round(plan.speak_w(t), 3),
            "gesture_w": {s: round(perf.gesture_w(s, t), 3) for s in "lr"},
            "p": {b: [round(x, 4) for x in perf.actor(F[b][0])] for b in TRACK_BONES if b in F},
            "hand_q": {s: [round(x, 5) for x in F["hand_" + s][1]] for s in "lr"}}


def track_doc(plan, fps: int, frames: list) -> dict:
    ev = [{"hand": e.hand, "kind": e.kind, "prep": e.prep, "stroke": e.stroke, "hold": e.hold,
           "line": getattr(e, "line", "")} for e in plan.events]
    return {"fps": fps, "frame": "actor: x fwd, y the presenter's right, z up, cm", "on_cam": plan.on_cam,
            "events": ev, "frames": frames}
