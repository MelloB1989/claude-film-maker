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

import math
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
}


@dataclass
class HandPose:
    """One hand's goal: the wrist relative to the sternum point (fwd, out to that hand's side, up), the palm
    (pronation: 90 thumb up, 0 palm down, < 0 palm up), wrist extension, finger shape."""
    off: tuple
    pron: float = 60.0
    ext: float = 10.0
    shape: str = "relaxed"


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


HIGH_REST = HandPose((22.0, 8.0, -1.0), pron=70.0, ext=14.0, shape="relaxed")  # loose, fingertips near each other


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

    def speak_w(self, t: float, pre: float = 0.5, post: float = 0.6, gap_merge: float | None = None) -> float:
        """1 while speaking (lines merged across gaps under gap_merge s), eased in/out."""
        gap_merge = self.gap_merge if gap_merge is None else gap_merge
        spans = []
        for a, b in sorted(self.speaking):
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
    off = tuple(HIGH_REST.off[i] + (p.off[i] - HIGH_REST.off[i]) * k for i in range(3))
    return replace(p, off=off)


def plan_from_sheet(sheet: dict, cues: dict, tilts: list | None = None, base_lean: float = 4.0,
                    timing: list | None = None) -> Plan:
    """agent-11's acting sheet (lines[].body01) + the cue sheet (speaking spans) -> Plan. `timing` (agent-10's
    prosody planner) overrides each gesture's prep/stroke/hold/retract/amp/energy by (line, word_i)."""
    events, lean = [], []
    gap_merge = 0.9
    if isinstance(timing, dict):
        gap_merge = float(timing.get("gap_merge", gap_merge))
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
            pl = scaled(gesture_pose(g, "l", n_count), k) if g.get("hand") in ("both", "l") else None
            if pl is not None:  # the left (mic side) stays below and inside the mic line, whatever the amp
                pl = replace(pl, off=(min(pl.off[0], 26.0), min(pl.off[1], 4.5), -2.5), ext=max(pl.ext, 34.0),
                             pron=min(pl.pron, 60.0))
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
    return Plan(events, speaking, lean, tilts or [], base_lean, gap_merge)


# --- torso model and the arm clearance ---------------------------------------------------------------------------

@dataclass
class Torso:
    """Her chest as an elliptic cylinder along spine_03 -> spine_05 (+8 cm), half-width `a` (lateral), half-depth
    `b`, and two breast spheres; the upper arm a capsule of radius `arm_r`. Measures per frame; agent-09's mesh measure
    is the judge, this keeps the pose honest while it is built."""
    a: float = 13.5
    b: float = 10.5
    breast_r: float = 7.5
    breast_down: float = 9.0
    breast_out: float = 7.0
    arm_r: float = 4.2


def clearance(A: dict, F: dict, s: str, tor: Torso) -> float:
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
    best = 1e9
    for k in range(8, 21):  # the arm from 40 % out (the armpit end always touches)
        q = add(sh, mul(sub(el, sh), k / 20.0))
        d = sub(q, p3)
        h = dot(d, ax)
        if -5.0 <= h <= dot(sub(top, p3), ax):
            x, y = dot(d, fwd), dot(d, lat)
            rr = math.hypot(x, y)
            th = math.atan2(x, y)
            r_e = tor.a * tor.b / math.sqrt((tor.b * math.cos(th)) ** 2 + (tor.a * math.sin(th)) ** 2)
            best = min(best, rr - r_e - tor.arm_r)
        for side in (1.0, -1.0):
            c = add(add(add(p5, mul(ax, -tor.breast_down)), mul(fwd, tor.b - 1.0)), mul(lat, side * tor.breast_out))
            best = min(best, norm(sub(q, c)) - tor.breast_r - tor.arm_r)
    return best


# --- the performer ---------------------------------------------------------------------------------------------------

class Performer(S.Seater):
    """seatkit.Seater with the plan driving the arms, hands, fingers, torso lean/turn and head roll."""

    def __init__(self, sk, st, sy, plan: Plan, torso: Torso | None = None, mic_side: str = "l"):
        self._ready = False  # seatkit's own setup (wrist extension, desk rest) runs on seatkit's pose
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
            for f in FINGERS:
                joints = [j for j in (f"{f}_metacarpal_{s}", f"{f}_01_{s}", f"{f}_02_{s}", f"{f}_03_{s}")
                          if j in sk.local]
                if len(joints) < 3:
                    continue
                tip, base = sk.p(joints[-1]), sk.p(joints[1] if "metacarpal" in joints[0] else joints[0])
                d = unit(sub(tip, base))
                mid = sk.p(f"middle_03_{s}") if f != "middle" else tip
                ps = sub(sk.p(f"middle_03_{s}"), sk.p(f"middle_01_{s}"))
                out[(s, f)] = {"joints": joints, "palm": ps}
        return out

    def hand_targets(self, s: str, t: float, W) -> tuple:
        """(wrist component point, HandPose blend, pole direction, speak weight, big-gesture weight)."""
        f, r, u = self.fr
        sg = 1.0 if s == "r" else -1.0
        A_l, A_r = (self.actor(self._fk_t("upperarm_" + x, "clavicle_" + x, W)) for x in "lr")
        st_pt = [(A_l[0] + A_r[0]) / 2 + 8.0, (A_l[1] + A_r[1]) / 2, (A_l[2] + A_r[2]) / 2 - 14.0]
        ws = self.plan.speak_w(t)
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
        if s == "l":  # the mic-side hand sits 1 cm back and a little lower than the right, whatever drew its pose
            tgt = [tgt[0] - 1.0, tgt[1], tgt[2] - 0.8]
        # pauses: down to the desk rest (forearms on the edge)
        e0, w0, _ = self.elbow_rest(s, W)
        tgt = [w0[i] + (tgt[i] - w0[i]) * ws for i in range(3)]
        tgt[2] += 4.0 * math.sin(math.pi * ws)  # an arc up off the desk and back, never through it
        if s == "l":  # and the mic-side hand's path bows in toward her midline, away from the mic in every camera
            tgt = add(tgt, mul(self.fr[1], 4.0 * math.sin(math.pi * ws)))
        pole = add(add(mul(f, -0.3), mul(r if s == "r" else mul(r, -1.0), 0.9)), mul(u, -0.35))
        pole_rest = sub(self.comp(e0), self._fk_t("upperarm_" + s, "clavicle_" + s, W))
        pole = add(mul(unit(pole), ws), mul(unit(pole_rest), 1.0 - ws))
        rest_hp = HandPose((0.0, 0.0, 0.0), pron=self.sy.pronation, ext=self.ext_base.get(s, 10.0), shape="relaxed")
        hp = blend_poses([(ws, hp), (1.0 - ws, rest_hp)])
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
        if roll:
            for b, share in (("neck_02", 0.4), ("head", 0.6)):
                ang = -roll * share if self._rhs else roll * share
                W[b] = [W[b][0], qmul(axis_angle(f, ang), W[b][1])]
            W["head"] = [self._fk_t("head", "neck_02", W), W["head"][1]]
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

    def swivel(self, s, sh, wrist, l1, l2, pole, W, ws):
        """Two-bone IK, then the elbow swung outward about the shoulder-wrist axis (10 deg steps, up to 80) until the
        upper arm clears the torso/breast model by CLEAR_WANT (while she speaks; the desk rest keeps its pole)."""
        elbow, wr = S.two_bone(sh, wrist, l1, l2, pole)
        if ws < 0.5:
            return elbow, wr
        A = {b: self.actor(W[b][0]) for b in ("spine_03", "spine_05")}
        axis = unit(sub(wr, sh))
        side = self.fr[1] if s == "r" else mul(self.fr[1], -1.0)
        best = None
        for k in range(0, 9):
            for sgn in ((1.0,) if k == 0 else (1.0, -1.0)):
                pk = qrot(axis_angle(axis, sgn * 10.0 * k), pole)
                e, w2 = S.two_bone(sh, wrist, l1, l2, pk)
                A2 = {**A, "upperarm_" + s: self.actor(sh), "lowerarm_" + s: self.actor(e)}
                c = clearance(A2, None, s, self.tor)
                if dot(sub(e, sh), side) < 0:  # never swing the elbow in across the body
                    continue
                if best is None or c > best[0]:
                    best = (c, e, w2)
                if c >= self.CLEAR_WANT:
                    return e, w2
        return (best[1], best[2]) if best else (elbow, wr)

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
        pitch = math.asin(max(-1.0, min(1.0, dot(fa, u)))) + math.radians(hp.ext)
        fingers = unit(add(mul(hz, math.cos(pitch)), mul(u, math.sin(pitch))))
        pr = math.radians(hp.pron)
        flat = ortho(side, fingers)
        up_ = ortho(u, fingers) if abs(dot(u, fingers)) < 0.98 else ortho(mul(f, -1.0), fingers)
        across = unit(add(mul(flat, math.cos(pr)), mul(up_, -math.sin(pr))))
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
            ps = qrot(dh, info["palm"])
            cum = [0.0, 0.0, 0.0, 1.0]
            parent = "hand_" + s
            for j in joints:
                if "metacarpal" in j:
                    q = qmul(dh, sk.q(j))
                else:
                    share = {"01": 0.8, "02": 1.0, "03": 0.8}[j.split("_")[1]]
                    d = unit(qrot(qmul(cum, dh), sub(sk.p(joints[-1]), sk.p(j)))) if j != joints[-1] else None
                    if d is None:
                        d = unit(qrot(qmul(cum, dh), sub(sk.p(j), sk.p(sk.parent[j]))))
                    axis = cross(d, ortho(ps, d)) if norm(cross(d, ps)) > 1e-6 else qrot(dh, [0.0, 0.0, 1.0])
                    cum = qmul(axis_angle(axis, curl * share), cum)
                    q = qmul(cum, qmul(dh, sk.q(j)))
                W[j] = [self._fk_t(j, parent, W) if parent in W else sk.p(j), q]
                parent = j


def blend_poses(parts: list) -> HandPose:
    tw = sum(w for w, _ in parts) or 1.0
    off = [sum(w * p.off[i] for w, p in parts) / tw for i in range(3)]
    pron = sum(w * p.pron for w, p in parts) / tw
    ext = sum(w * p.ext for w, p in parts) / tw
    shapes = {}
    for w, p in parts:
        sh = SHAPES.get(p.shape, {}) if isinstance(p.shape, str) else p.shape
        for k in FINGERS + tuple(x for x in sh if x.startswith("_")):  # "_spread" etc. (gesture_style) ride along
            shapes[k] = shapes.get(k, 0.0) + w * float(sh.get(k, 0.0)) / tw
    return HandPose(tuple(off), pron, ext, shapes)


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
          check_every: int = 6, timing: list | None = None) -> tuple:
    """seatkit.build for the performance: the seated pose with the plan driving the upper body, as tracks (constant
    for the bones that never move, per key for spine, neck, head, clavicles, arms, hands and fingers). Returns (doc
    for perform.py's WRITE, summary with the checks and the body rows' numbers)."""
    sk = S.Skeleton.from_read(data)
    plan = plan_from_sheet(sheet, cues, tilts, timing=timing)
    se, tuned = S.autotune(sk, st, sy)
    perf = Performer(sk, st, se.sy, plan)
    n = int(round(length_s * fps)) + 1
    first = perf.pose(0.0)
    const = {b: data["local"][b] for b in data["tracks"] if b in data["local"]}
    const.update(first)
    moving = sorted(set(first) - {"pelvis"} - {b for s in "lr" for b in S.LEGS[s]})
    keyed = {b: [] for b in moving}
    issues, clear = [], {"l": 1e9, "r": 1e9}
    for i in range(n):
        t = i / fps
        loc = perf.pose(t)
        for b in moving:
            v = loc.get(b, const[b])
            keyed[b].append({k: [round(x, 6) for x in v[k]] for k in ("t", "q", "s")})
        if i % check_every == 0:
            F = perf.fk({**const, **loc})
            c = S.check(perf, F)
            ws = plan.speak_w(t)
            skip = ("desk.elbow_off", "desk.elbow_hangs", "desk.forearm_unsupported") if ws > 0.1 else ()
            issues.extend({**x, "t": round(t, 2)} for x in c["issues"] if x["code"] not in skip)
            if ws > 0.5:
                A = {b: perf.actor(v[0]) for b, v in F.items()}
                for s in "lr":
                    clear[s] = min(clear[s], clearance(A, F, s, perf.tor))
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
    rows = {"upperarm_torso_clear_cm": {s: round(v, 1) for s, v in clear.items()}}
    if STYLE_HOOK is not None and hasattr(STYLE_HOOK, "report"):  # the variation and never-frozen rows
        extra = STYLE_HOOK.report(perf, length_s)
        rows.update(extra.get("rows", {}))
        issues.extend(extra.get("issues", []))
    ok_clear = min(clear.values()) >= 3.0
    if not ok_clear:
        issues.append({"code": "body.arm_torso", "message": f"upper arm within {min(clear.values()):.1f} cm of the "
                       "torso/breast model (line 3)", "value": min(clear.values())})
    summary = {"pass": not issues, "issues": issues[:30], "n_issues": len(issues), "tuned": tuned, "rows": rows,
               "events": len(plan.events), "moving_bones": len(moving),
               "hooks": {"style": bool(STYLE_HOOK), "timing": bool(timing)}, "frame": {"fwd": perf.F["fwd"],
                                                                                   "right": perf.F["right"]},
               "rest": S.check(perf, perf.fk({**const, **first}))}
    doc = {"length_s": length_s, "fps": fps, "n_keys": n, "const": const, "keyed": keyed}
    return doc, summary
