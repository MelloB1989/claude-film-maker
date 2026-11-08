"""Round 7: the layer that makes gesturekit's code motion read as human (agent-08). No motion libraries (the operator:
"we can't show same animations"): every gesture is generated here, unique to its film, line and index.

(a) HANDS. Finger shapes per gesture (relaxed curl, open palm, pinch, point, count 1-3, soft fist) with seeded
    per-finger offsets and a spread in the palm's plane; the fingers change shape in a cascade behind the wrist
    (pinky first, 30 ms, to the index last, 80 ms) and are never frozen: a slow micro-motion runs on every finger.
(b) KINEMATICS. The prep is a minimum-jerk move skewed late, so the stroke is the fast part; it arrives with a small
    overshoot and settles (~0.15 s). A stroke whose goal is near where the hand already is gets a 0.12 s dip/push
    at its apex (3-4.5 cm by energy), so it still reads as a stroke. Held strokes drift a few millimetres and degrees. Retracts are co-articulated:
    a gap under COART_S flows straight into the next gesture, a gap under PARTIAL_S only falls halfway to the rest,
    longer ones go home. The wrist's rotation leads the hand into a stroke and follows it out of one.
(c) VARIATION. A seeded draw per gesture (seed = film + presenter + line + gesture index + hand): amplitude, path
    curvature (a bulge off the straight line), stroke timing (+-40 ms), wrist angles, finger spread and offsets, hand
    height, overshoot, settle and retract times. `similarity()` compares every pair of gesture curves in a film (and
    across films) and reports the most similar pair; near-identical (>= SIM_FAIL) fails.

The hooks gesturekit calls (it imports this file when it sits beside it; perform.py pushes it to the box):
  vary(pose, event, hand)        the seeded goal pose (amplitude, height, wrist angles, finger offsets, spread)
  envelope(phase, u, event)      min-jerk prep skewed late + overshoot, settle in the hold, soft retract (used where
                                 the hand track is not: gesturekit's own blend)
  hand(performer, hand, t)       the whole hand track: kinematics, co-articulation, wrist lead, finger cascade, micro
  weights(performer, t)          the events' presence on the track, for the torso's turn and the shoulders' lift
  finger_post(performer, hand, hp, W)   the fingers' spread in the palm's plane
  report(performer, length_s)    rows for build's summary: the most similar gesture pair, the longest freeze
gesturekit's IK, elbow swivel/clearance, desk and mic checks run on whatever these return, and stay the judge.
Pure Python.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, replace

import handshape as HS  # noqa: E402
import seatkit as S
from seatkit import add, axis_angle, cross, dot, mul, norm, qinv, qmul, qrot, sub, unit


class _GK:
    """gesturekit, imported late: gesturekit imports this module while it loads."""

    def __getattr__(self, k):
        import gesturekit
        return getattr(gesturekit, k)


GK = _GK()

V_MEAN = 70.0       # cm/s a stroke's mean wrist speed at most (min-jerk peaks ~1.9x: ~1.3-1.6 m/s with the skew)
LEFT_EXT_MIN = 20.0  # deg the left hand's wrist extension on a gesture at least (its fingers met the desk lower; 34
#   held her left wrist cocked back ~31 deg the whole take, agent-10's audit)
TWO_HAND_LAG_S = (0.04, 0.08)  # s the left trails the right on a two-hand stroke (same-frame peaks read robotic)
MIC_L_CAM = {"CAM_CU": (14.0, 3.5), "CAM_WIDE": (14.0, 4.5)}  # per live camera: in the CU the mic hid her left hand over 5 cm (the cut hides
#   the change of box)
ACCENT_W = 0.22     # s the accent's own small move, after the apex
ACCENT_K = 0.7      # x its amplitude
ACCENT_GAP_S = 0.1  # s after the apex it starts
OVERSHOOT_K = 0.0   # x the drawn overshoot (r7F, agent-13: the settle back from it was a slow second movement on the
#   tail of every stroke, so peak/mean read 2.4-3.9 instead of one bell's 1.875; off, right bells 0.64 -> 0.84)
LEFT_ARC = (0.08, 0.12)  # x the chord: the left hand's own arc (agent-13: its echoes were dead-straight 10 cm lines)
LEFT_ARC_DIR = (-0.6, -0.2, 0.75)  # (fwd, out, up): its arc bows up and back toward her (the mic is forward and out)
RIGHT_ARC_DIR = (-0.3, 0.45, 0.85)  # a mic-moved right stroke's bow: up, out and a little back
RIGHT_ARC_MIN = 0.06  # x the chord: every right move's bow off the straight line at least (agent-13's line: 0.03)
FING_END = 0.85    # x a move: the fingers' shape change ends here (R7 hands: they settle before the wrist stops)
ROT_LAG_S = 0.08    # s the hand's turn and the fingers trail the wrist's path (proximal to distal)
DRIFT_CM = 0.8      # cm the wrist's slow drift, each axis (orchestrator: real hands are never 0 cm/s in a hold)
RIGHT_DRIFT_K = 1.3  # the right hand's drift x this (its rest life on the desk keeps DESK_DRIFT)
DRIFT_HZ = 0.26     # its band (low: a drift, not a tremor)
DESK_DRIFT = 0.5    # x it at the desk rest, along the desk only (fwd, out), and the fingers at half
FING_MICRO = {"index": 5.0, "middle": 5.6, "ring": 6.6, "pinky": 7.2, "thumb": 4.4}  # deg each finger's drift (the
#   noise sits mostly within half of it: ~2-4 deg)
FING_HZ = 0.45      # its band
PIP_K = 0.6         # x it on the middle and end joints, on their own phase
PIP_HZ = 0.33
SETTLE_DEG = 2.0    # deg the fingers curl a little and let go after a stroke
SETTLE_S = 0.5
REST_TURN_K = 0.7  # x the turn time on a stroke up from the rest (its turn rides a longer rise; full: it began
#   before the measured window, the left's share of a two-hand stroke fell to 0.40)
MOVE_ABSORB_S = 0.2  # s: a move with less room than this is absorbed into the hold before it
HOLD_MIN_S = 0.1    # s a hold kept at least when the next move takes its time
V_RETRACT = 55.0    # cm/s a retract home's mean speed at most (softer than the stroke)
COART_S = 0.45      # a gap shorter than this flows straight into the next gesture
MOVE_MIN_S = 0.3  # s: a stroke's move at least (agent-13: 0.13-0.25 s strokes peaked
#   at 2.4-3.6x their mean speed, vel_bell 8/15 at 24 fps; the apex stays on its word, the hold before gives the time)
PARTIAL_S = 1.1     # a gap shorter than this falls only halfway to the rest
LAG_S = {"pinky": 0.030, "ring": 0.045, "thumb": 0.050, "middle": 0.062, "index": 0.080}  # fingers behind the wrist
SHAPE_SPREAD = {"rest": -1.5, "relaxed": 0.0, "open": 3.0, "point": 0.0, "count1": 0.0, "count2": 3.0, "count3": 3.0,
                "pinch": 0.0, "soft_fist": 0.0, "list": 1.0, "raise": 0.0}  # deg opening handshape's together fan
SIM_FAIL = 0.95
MIC_L = (14.0, 8.0)  # the left hand (mic side) on a gesture: out <= 14 cm, up <= 8 cm from the sternum point
#   (r7F: 9 / -2 with the mic at her chest; with it at her mouth and the rest low, that box held her left hand still)
#   (agent-10: was 7 / -3.5, which put her left elbow up in front of her chest, inside the Top on box B)


# --- small helpers -----------------------------------------------------------------------------------------------

def dist(a, b) -> float:
    """cm between two HandPoses' wrist goals."""
    return math.sqrt(sum((a.off[i] - b.off[i]) ** 2 for i in range(3)))


def seed_of(*parts) -> int:
    """A stable seed (not Python's salted hash) from any parts."""
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


def mj(u: float) -> float:
    """Minimum-jerk position 0 -> 1 (zero velocity and acceleration at both ends)."""
    u = max(0.0, min(1.0, u))
    return u * u * u * (10.0 + u * (-15.0 + 6.0 * u))


def clip01(u: float) -> float:
    return max(0.0, min(1.0, u))


class Noise:
    """Smooth band-limited noise in [-1, 1]: three seeded sines (incommensurate frequencies around `hz`)."""

    def __init__(self, seed: int, hz: float):
        r = random.Random(seed)
        self.terms = [(r.uniform(0.6, 1.0), hz * r.uniform(0.55, 1.6), r.uniform(0, 2 * math.pi)) for _ in range(3)]
        self.norm = sum(a for a, _, _ in self.terms)

    def __call__(self, t: float) -> float:
        return sum(a * math.sin(2 * math.pi * f * t + p) for a, f, p in self.terms) / self.norm


def shape_dict(shape) -> dict:
    """A shape name or dict -> {finger: closure %, '_opp': thumb opposition %, '_spread': deg} (handshape: absolute
    anatomical targets; a missing finger is relaxed)."""
    if isinstance(shape, dict):
        d = HS.full(shape)
        d.setdefault("_spread", 3.0)
        return d
    d = HS.full(shape)
    d["_spread"] = SHAPE_SPREAD.get(shape, 3.0)
    return d


def lerp_pose(a: GK.HandPose, b: GK.HandPose, u_pos: float, u_rot: float, u_f: dict, bulge=(0.0, 0.0, 0.0),
              u_bulge: float = 0.0) -> GK.HandPose:
    """a -> b: position by u_pos (may pass 1: the overshoot) plus a bulge * sin(pi u_bulge), the wrist's rotation by
    u_rot, each finger by its own u_f (the cascade)."""
    off = tuple(a.off[i] + (b.off[i] - a.off[i]) * u_pos + bulge[i] * math.sin(math.pi * clip01(u_bulge))
                for i in range(3))
    sa, sb = shape_dict(a.shape), shape_dict(b.shape)
    sh = {f: sa[f] + (sb[f] - sa[f]) * u_f.get(f, u_rot) for f in GK.FINGERS}
    sh["_spread"] = sa["_spread"] + (sb["_spread"] - sa["_spread"]) * u_f.get("index", u_rot)
    # the thumb's opposition leads the fingers as it rises and trails them as it falls, so a curling hand never has a
    # flat thumb for a frame (agent-13's thumb_flat: open -> pinch at t15.4, the fingers curled first)
    uo = (max if sb["_opp"] > sa["_opp"] else min)(list(u_f.values()) or [u_rot])
    sh["_opp"] = sa["_opp"] + (sb["_opp"] - sa["_opp"]) * uo
    return GK.HandPose(off, a.pron + (b.pron - a.pron) * u_rot, a.ext + (b.ext - a.ext) * u_rot, sh)


# --- the variation engine ----------------------------------------------------------------------------------------

@dataclass
class Var:
    """One gesture's draw."""
    amp: float          # x the pose's distance from the high rest
    bulge: tuple        # cm, the path's mid-way offset (fwd, out, up)
    dt: float           # s, the stroke's timing offset
    d_pron: float
    d_ext: float
    dz: float           # cm, hand height
    spread: float       # deg added to the shape's spread
    fingers: dict       # deg per finger added to the shape's curl
    overshoot: float    # fraction of the move
    settle: float       # s
    retract: float      # s
    skew: float         # > 1: the prep's speed peaks late (a sharper stroke)
    lag: float          # x the finger cascade's lags

    @classmethod
    def draw(cls, seed: int, energy: float = 0.5) -> "Var":
        r = random.Random(seed)
        g = r.gauss
        return cls(amp=min(1.18, max(0.84, 1.0 + g(0, 0.08))),
                   bulge=(g(0, 1.0), r.uniform(-0.5, 2.2), r.uniform(-0.6, 2.0)),
                   dt=max(-0.04, min(0.04, g(0, 0.02))),
                   d_pron=max(-9.0, min(9.0, g(0, 4.5))), d_ext=max(-6.0, min(6.0, g(0, 3.0))),
                   dz=max(-2.0, min(2.0, g(0, 1.0))), spread=max(-1.0, min(1.5, g(0, 0.6))),
                   fingers={f: max(-6.0, min(6.0, g(0, 2.5))) for f in GK.FINGERS},
                   overshoot=OVERSHOOT_K * (0.02 + 0.03 * energy) * r.uniform(0.7, 1.3), settle=r.uniform(0.08, 0.12),
                   retract=r.uniform(0.32, 0.5), skew=1.0, lag=r.uniform(0.8, 1.25))  # skew 1: one min-jerk
#                  bell (agent-13: the skewed peak plus the settle read as a spike and a long tail)

    def apply(self, p: GK.HandPose) -> GK.HandPose:
        rest = getattr(GK, "POSE_ORIGIN", GK.HIGH_REST).off  # the amp's origin, not the (r7F, lower) rest
        off = tuple(rest[i] + (p.off[i] - rest[i]) * self.amp + (self.dz if i == 2 else 0.0) for i in range(3))
        sh = shape_dict(p.shape)
        sh = {f: sh[f] + self.fingers.get(f, 0.0) for f in GK.FINGERS} | {"_spread": max(-2.0, sh["_spread"] + self.spread), "_opp": sh["_opp"]}
        return GK.HandPose(off, p.pron + self.d_pron, p.ext + self.d_ext, sh)


# --- one hand's track ---------------------------------------------------------------------------------------------

@dataclass
class Seg:
    t0: float
    t1: float
    a: GK.HandPose
    b: GK.HandPose
    kind: str           # stroke | coart | retract | hold | rest
    var: Var | None = None
    ev: int = -1        # the event arriving (stroke/coart/hold) or leaving (retract)
    prev_ev: int = -1   # the event left behind by a coart / partial retract
    w_from: float = 0.0  # gesture weight at a and b (rest 0, a gesture 1, a half retract 0.5)
    w_to: float = 1.0


ROT_MEAN = 160.0  # deg/s a move's mean hand turn at most: one min-jerk peaks at 1.9x the mean, so a fingertip ~18 cm
#   out moves <= ~110 cm/s relative to the hand (agent-13's finger_snap: >= 90 cm/s that stops within 2 frames; her
#   hands turned 85-120 deg home to the desk in 0.25-0.35 s, up to 146 cm/s)


def turn_s(a: GK.HandPose, b: GK.HandPose) -> float:
    """s the hand needs to turn from pose a to b (pronation, extension, the largest finger curl) at ROT_MEAN."""
    sa, sb = shape_dict(a.shape), shape_dict(b.shape)
    curl = max(abs(sb[f] - sa[f]) for f in GK.FINGERS)
    return max(abs(b.pron - a.pron) + 0.5 * abs(b.ext - a.ext), 0.8 * curl) / ROT_MEAN


class HandTrack:
    """The wrist + hand + fingers of one hand over the take, from the plan's events: segments from the rest through
    every gesture (co-articulated where the gaps are short) and home."""

    def __init__(self, events: list, side: str):
        self.side = side
        self.events = [(i, e) for i, e in enumerate(events) if e.hand == side or e.hand == "both"]
        self.keys = {}
        film = "".join(sorted({str(getattr(e, "line", ""))[:1] for e in events}))  # N (her) / W (him) lines
        sd = seed_of(film, side, "micro")
        self.n_off = [Noise(sd + k, DRIFT_HZ) for k in range(3)]
        self.n_rot = [Noise(sd + 10 + k, 0.45) for k in range(2)]
        self.n_f = {f: Noise(sd + 20 + k, FING_HZ) for k, f in enumerate(GK.FINGERS)}
        self.n_pip = {f: Noise(sd + 50 + k, PIP_HZ) for k, f in enumerate(GK.FINGERS)}
        self.n_f_common = Noise(sd + 40, 0.3)
        self.segs = self._build()
        self.accents = self._accents()
        self.apexes = [q.t1 for q in self.segs if q.kind in ("stroke", "coart")]

    def var_of(self, i: int, e) -> Var:
        self.keys[i] = f"{getattr(e, 'line', '')}:{getattr(e, 'detail', '') or e.kind}:{e.word}"
        return var_of(e, self.side)

    def _pose_of(self, e) -> GK.HandPose:
        p = e.pose_r if self.side == "r" else e.pose_l
        return p if p is not None else e.pose_r

    def _build(self) -> list:
        rest = GK.HIGH_REST
        segs, cur, cur_w, cur_ev, t = [], rest, 0.0, -1, -1e9
        ev = self.events
        for n, (i, e) in enumerate(ev):
            v = self.var_of(i, e)
            target = self._pose_of(e)  # vary() has already drawn this event's goal
            apex = e.stroke + v.dt
            start = max(e.prep, t)
            # a long move starts earlier (r7F: from the lowered rest a count rose 29 cm in 0.18 s, 4 m/s at the wrist,
            # a snap): its mean speed at most V_MEAN, the stroke still landing on its word
            turn = turn_s(cur, target) * (1.0 if cur_w > 0 else REST_TURN_K)  # (from the rest the turn rides the rise; a coart from
            #   one gesture to the next, or a half-way rest, is where the hand turns fast and stops)
            need = apex - max(MOVE_MIN_S, dist(cur, target) / V_MEAN, turn)  # never a snap under MOVE_MIN_S, nor a
            #   hand turn faster than ROT_MEAN
            start = max(t, min(start, need))
            if start > need and segs and segs[-1].kind == "hold" and segs[-1].t1 == t:  # no room after the last
                #   hold: the hold gives some of its time back (down to HOLD_MIN_S), the move starts sooner
                h = segs[-1]
                start = max(h.t0 + HOLD_MIN_S, need)
                h.t1 = start
            if turn > 0 and apex - start < turn and cur_w > 0:  # no room for the whole turn: it turns less (the hand
                #   co-articulates; his 90 deg in 0.31 s between two strokes snapped)
                kt = max(0.0, (apex - start) / turn)
                target = replace(target, pron=cur.pron + (target.pron - cur.pron) * kt,
                                 ext=cur.ext + (target.ext - cur.ext) * kt)
            if apex - start < MOVE_ABSORB_S and segs and segs[-1].kind == "hold" and segs[-1].t1 == start:
                # no room for a move of its own (two strokes 0.28 s apart: a 0.13 s flick, a finger snap): the hand
                #   holds the gesture it is in through this one's beat (the style accent still marks the stroke)
                segs[-1].t1 = apex + max(0.12, e.hold)
                t = segs[-1].t1
                continue
            if apex - start < 0.12:  # no room: a quick move, never backwards in time
                start = apex - 0.12
            if segs and start > t:
                segs.append(Seg(t, start, cur, cur, "rest" if cur_w == 0 else "hold", ev=cur_ev, w_from=cur_w,
                                w_to=cur_w))
            kind = "coart" if cur_ev >= 0 and cur_w > 0.75 else "stroke"
            segs.append(Seg(start, apex, cur, target, kind, v, ev=i, prev_ev=cur_ev, w_from=cur_w, w_to=1.0))
            hold_end = apex + max(0.12, e.hold)
            segs.append(Seg(apex, hold_end, target, target, "hold", v, ev=i, w_from=1.0, w_to=1.0))
            nxt = ev[n + 1][1] if n + 1 < len(ev) else None
            gap = (nxt.prep - hold_end) if nxt else 1e9
            cur, cur_w, cur_ev, t = target, 1.0, i, hold_end
            if gap < COART_S:
                continue  # flows into the next gesture from the hold
            if gap < PARTIAL_S:  # half way home, then the next prep starts from there
                mid = lerp_pose(target, rest, 0.5, 0.5, {})
                t1 = hold_end + min(max(v.retract, turn_s(target, mid)), gap)
                segs.append(Seg(hold_end, t1, target, mid, "retract", v, ev=i, w_from=1.0, w_to=0.5))
                cur, cur_w, t = mid, 0.5, t1
                continue
            t1 = hold_end + min(max(v.retract, dist(target, rest) / V_RETRACT, turn_s(target, rest)), gap)
            segs.append(Seg(hold_end, t1, target, rest, "retract", v, ev=i, w_from=1.0, w_to=0.0))
            cur, cur_w, cur_ev, t = rest, 0.0, -1, t1
        return segs

    def _accents(self) -> list:
        """[(apex t, its move's s, offset vector cm, the next move)]: a small dip or push after the apex of every stroke whose goal is close to
        where the hand already is (a count's next finger, a beat after an open palm), so it still reads as a
        stroke (agent-10: 18/50 strokes stayed under the 40 cm/s beat line). Forward-down on the right (forward and
        a little up when the hand is already low), a small pull back toward the body on the left (the mic and the
        desk are there)."""
        evs = dict(self.events)
        out = []
        for s in self.segs:
            if s.kind not in ("stroke", "coart"):
                continue
            span = math.sqrt(sum((s.b.off[i] - s.a.off[i]) ** 2 for i in range(3)))
            k = clip01((10.0 - span) / 6.0)
            if k <= 0:
                continue
            e = evs[s.ev]
            amp = (2.5 + 2.0 * float(getattr(e, "energy", 0.5))) * k
            if self.side == "l":
                vec = (-0.5 * amp, 0.0, 0.0)
            elif s.b.off[2] > -1.0:
                vec = (0.7 * amp, 0.0, -0.7 * amp)  # a dip
            else:  # already low over the desk: a push forward and a little up (a dip put the fingers in the desk)
                vec = (0.95 * amp, 0.0, 0.3 * amp)
            # its own move into the hold once the stroke has stopped, kept, and given back with the next move (the
            # same min-jerk as that move: one bell) (r7F, agent-13: a bump about the apex sharpened the stroke's bell)
            k_ = self.segs.index(s)
            nxt = next((q for q in self.segs[k_ + 1:] if q.kind in ("stroke", "coart", "retract")), None)
            hold_end = nxt.t0 if nxt else s.t1 + 1e9
            t0 = s.t1 + ACCENT_GAP_S  # a beat after the stroke stops: two bells, not one with a shoulder
            if hold_end - t0 < 0.1:
                continue  # no room in the hold
            out.append((t0, min(ACCENT_W, hold_end - t0), vec, nxt))
        return out

    def accent(self, t: float) -> tuple:
        """The accents' offset at t: a small min-jerk move of its own from the apex (where the stroke's speed is 0) into
        the hold, held, then faded out with the next move's own progress."""
        off = [0.0, 0.0, 0.0]
        for apex, w, vec, nxt in self.accents:
            if t <= apex:
                continue
            g = mj(clip01((t - apex) / w))
            if nxt is not None and t > nxt.t0:
                if t >= nxt.t1:
                    continue
                g *= 1.0 - mj((t - nxt.t0) / max(1e-3, nxt.t1 - nxt.t0))
            for i in range(3):
                off[i] += vec[i] * g * ACCENT_K
        return off

    def arc(self, s: Seg, v: Var) -> tuple:
        """The path's mid-way offset: the draw's, or on the LEFT its own arc, LEFT_ARC of the chord bowed up and back
        (perpendicular to the chord; never the right's arc mirrored)."""
        bowed = self.side == "r" and s.kind in ("stroke", "coart") and \
            "r" in getattr(dict(self.events).get(s.ev), "mic_moved", ())
        ch = [s.b.off[i] - s.a.off[i] for i in range(3)]
        c = math.sqrt(sum(x * x for x in ch))
        if self.side != "l" and not bowed:
            arc = v.bulge if s.kind != "retract" else tuple(-0.5 * x for x in v.bulge)
            if c < 1.0:
                return arc
            # its random draw may lie along the chord (his straight 30 cm strokes, path_straight 0.36): at least
            #   RIGHT_ARC_MIN of the chord off it, along the draw's own off-chord part (else up and out)
            k = sum(arc[i] * ch[i] for i in range(3)) / (c * c)
            p = [arc[i] - k * ch[i] for i in range(3)]
            n = math.sqrt(sum(x * x for x in p))
            want = RIGHT_ARC_MIN * c
            if n >= want:
                return arc
            if n < 0.1:
                d = RIGHT_ARC_DIR if s.kind != "retract" else tuple(-x for x in RIGHT_ARC_DIR)
                kd = sum(d[i] * ch[i] for i in range(3)) / (c * c)
                p = [d[i] - kd * ch[i] for i in range(3)]
                n = math.sqrt(sum(x * x for x in p)) or 1.0
            return tuple(arc[i] + p[i] / n * (want - math.sqrt(sum(
                (arc[j] - k * ch[j]) ** 2 for j in range(3)))) for i in range(3))
        if c < 1.0:
            return (0.0, 0.0, 0.0)
        # the left's own arc; and a right goal the mic rule moved keeps a bow (its random draw could lie along the
        #   new chord: agent-13, his path_straight 0.385 with the mic-moved strokes): up and out, off the chord
        d = LEFT_ARC_DIR if self.side == "l" else RIGHT_ARC_DIR
        k = sum(d[i] * ch[i] for i in range(3)) / (c * c)
        p = [d[i] - k * ch[i] for i in range(3)]
        n = math.sqrt(sum(x * x for x in p)) or 1.0
        lo, hi = LEFT_ARC
        frac = lo + (hi - lo) * clip01((v.lag - 0.8) / 0.45)
        return tuple(p[i] / n * frac * c for i in range(3))

    def micro(self, t: float, w: float, held: bool) -> tuple:
        """(offset cm, d_pron, d_ext, {finger: deg}): the never-frozen layer, the same everywhere (r7F hold life: it
        was 0.28 cm, x1.8 on a held stroke, ~0.3 cm/s in the holds and a step where a hold began; now a slow
        DRIFT_CM drift, ~0.6-0.8 cm/s mean and under 2 cm/s, the two hands on their own seeds)."""
        off = tuple(DRIFT_CM * n(t) for n in self.n_off)
        if self.side == "l":  # never toward the mic (forward, out, up: it hangs at her mouth): it drifts back, in and
            #   down from its pose (its fingers went behind the mic in a two-hand hold)
            k_l = 0.75 + 0.35 * (1.0 - min(1.0, w))  # x1.1 at the desk rest (R7 hands: there its vertical drift is
            #   held by the heel-down rest and its p10 fell to 0.28 cm/s in the verify windows; the mic is far above it)
            off = tuple(k_l * (o - DRIFT_CM) for o in off)
        else:  # the right's holds a little livelier (agent-13: its hold p10 0.32-0.34 cm/s in the verify windows,
            #   0.27 on the editor's 24 fps dump; the line is 0.3)
            off = tuple(RIGHT_DRIFT_K * o for o in off)
        kr = 1.0 if self.side == "r" else 0.7  # the left's turn smaller (its fingertips sit by the mic)
        dp, de = 2.2 * kr * self.n_rot[0](t), 1.8 * kr * self.n_rot[1](t)
        # the fingers (r7F, agent-13: 2.6 deg on one curl read under 2 deg/s for >= 0.5 s in half her speaking time:
        # posed): each finger's own drift (more on ring and pinky), its middle and end joints on their own, a share
        # tied to the wrist's drift with the cascade's delay (pinky first), and a small curl-settle after each stroke
        c = self.n_off[2]
        fing = {}
        for f in GK.FINGERS:
            a = FING_MICRO[f]
            d = 3.0 * LAG_S[f]
            st = sum(SETTLE_DEG * math.sin(math.pi * clip01((t - ap - LAG_S[f]) / SETTLE_S)) for ap in self.apexes
                     if 0.0 < t - ap - LAG_S[f] < SETTLE_S)
            fing[f] = a * (0.6 * self.n_f[f](t) + 0.4 * c(t - d)) + st
            fing["_pip_" + f] = PIP_K * a * self.n_pip[f](t)
        return off, dp, de, fing

    def at(self, t: float) -> tuple:
        """(HandPose with a per-finger shape dict, {event index: weight}). The hand's turn and the fingers follow the
        wrist's path ROT_LAG_S behind it (agent-13: proximal to distal, shoulder -> elbow -> wrist -> fingers)."""
        hp, w = self._at(t)
        if ROT_LAG_S <= 0:
            return hp, w
        lag, _ = self._at(t - ROT_LAG_S)
        # the fingers ride the wrist's own clock (R7 hands): lagged with the turn, the anatomical shape change (larger
        # than the old offsets: the thumb swings out of opposition) piled onto the turn just as the wrist stopped dead,
        # fingertips 120-145 cm/s (agent-13's finger_snap 3.14/min on 8ebecc97)
        return GK.HandPose(hp.off, lag.pron, lag.ext, hp.shape), w

    def _at(self, t: float) -> tuple:
        rest = GK.HIGH_REST
        seg = None
        for s in self.segs:
            if s.t0 <= t < s.t1:
                seg = s
                break
        if seg is None:
            if self.segs and t >= self.segs[-1].t1:
                last = self.segs[-1]
                hp, w = last.b, ({last.ev: last.w_to} if last.w_to > 0 and last.ev >= 0 else {})
            else:
                hp, w = rest, {}
            held = False
        else:
            hp, w, held = self._eval(seg, t)
        off, dp, de, fing = self.micro(t, sum(w.values()), held)
        acc = self.accent(t)
        off = tuple(off[i] + acc[i] for i in range(3))
        sh = shape_dict(hp.shape)
        sh = {f: sh[f] + fing[f] for f in GK.FINGERS} | {"_spread": sh["_spread"], "_opp": sh["_opp"]} | \
            {k: v for k, v in fing.items() if k.startswith("_pip_")}
        return GK.HandPose(tuple(hp.off[i] + off[i] for i in range(3)), hp.pron + dp, hp.ext + de, sh), w

    def _eval(self, s: Seg, t: float) -> tuple:
        d = max(1e-3, s.t1 - s.t0)
        u = (t - s.t0) / d
        v = s.var
        if s.kind in ("rest", "hold"):
            hp = s.a
            if s.kind == "hold" and v is not None and s.w_to == 1.0:
                tau = t - s.t0
                if tau < v.settle:  # settling back from the overshoot
                    x = 1.0 + v.overshoot * 0.5 * (1.0 + math.cos(math.pi * tau / v.settle))
                    hp = lerp_pose(self._from_of(s), s.a, x, 1.0, {})
            w = {s.ev: s.w_to} if s.ev >= 0 and s.w_to > 0 else {}
            return hp, w, s.kind == "hold"
        lag = v.lag if v else 1.0
        if s.kind in ("stroke", "coart"):
            x = mj(u ** v.skew) * (1.0 + v.overshoot)  # arrives past the target; the hold settles it
            u_rot = mj(u)  # (r7F: it turned 0.12 ahead; now the whole turn trails the path, ROT_LAG_S)
            u_f = self._u_fingers(s, t, lag)
            hp = lerp_pose(s.a, s.b, x, u_rot, u_f, self.arc(s, v), mj(u))  # the arc by the path's
            #   progress (sin(pi u) in time set the speed off 0 at the start)
            w_in = s.w_from + (s.w_to - s.w_from) * mj(u)
            w = {s.ev: w_in}
            if s.prev_ev >= 0:
                w[s.prev_ev] = (1.0 - mj(u)) * s.w_from
            return hp, w, False
        # retract: soft (no overshoot, no skew), the wrist follows the hand, a smaller arc
        x = mj(u)
        u_rot = mj(clip01((u - 0.12) / 0.88))  # (was mj(u - 0.12): the turn was still at ~1/3 of its peak speed when
        #   the retract ended and stopped dead: the hand-home snaps, 85 deg of pronation on the left)
        u_f = self._u_fingers(s, t, lag)
        hp = lerp_pose(s.a, s.b, x, u_rot, u_f, self.arc(s, v), x)
        return hp, {s.ev: s.w_from + (s.w_to - s.w_from) * x}, False

    @staticmethod
    def _u_fingers(s: Seg, t: float, lag: float) -> dict:
        """each finger's progress through a move: one min-jerk that starts its cascade delay late (pinky first) and
        ENDS at the move's end, at rest (agent-13, the orchestrator: the delay used to carry the curl past the apex,
        and the hold then snapped it home in one frame, up to 146 cm/s at a fingertip; 12 snaps on 8a45d961)."""
        d = max(1e-3, s.t1 - s.t0)
        end = FING_END * d  # (R7 hands) and settle a little before the wrist does, not with it
        out = {}
        for f in GK.FINGERS:
            lf = min(LAG_S[f] * lag, 0.3 * end)
            out[f] = mj(clip01((t - s.t0 - lf) / max(1e-3, end - lf)))
        return out

    def _from_of(self, hold: Seg) -> GK.HandPose:
        for s in self.segs:
            if s.t1 == hold.t0 and s.kind in ("stroke", "coart") and s.ev == hold.ev:
                return s.a
        return GK.HIGH_REST

    # the gesture curves for the similarity check
    def curve(self, i: int, n: int = 24) -> list | None:
        segs = [s for s in self.segs if s.ev == i and s.kind in ("stroke", "coart", "hold")]
        if not segs:
            return None
        t0, t1 = segs[0].t0, segs[-1].t1 + 0.15
        out = []
        for k in range(n):
            t = t0 + (t1 - t0) * k / (n - 1)
            seg = next((s for s in self.segs if s.t0 <= t < s.t1), None)
            hp = self._eval(seg, t)[0] if seg else GK.HIGH_REST
            sh = shape_dict(hp.shape)
            out.append([*hp.off, hp.pron / 6.0, hp.ext / 6.0, sum(sh[f] for f in GK.FINGERS) / 25.0,
                        sh["_spread"] / 3.0])
        return out


# --- the hooks ------------------------------------------------------------------------------------------------------

def var_of(event, hand: str) -> Var:
    """The event's draw: seeded by its line, its index in the plan, its detail and the hand (her N lines and his W
    lines never share a seed; the two hands of a two-hand gesture differ). Bounded where the set is tight:
    - the LEFT hand (the mic side): never further forward or lower than its pose (its forearm met the mic arm and
      its fingers the desk on a 1.17x draw), no bulge out or up, half the overshoot;
    - a CROSS-BODY pose (a deictic to her left, the hand near her midline): no extra reach and a third of the
      overshoot (a straighter arm brings the elbow in onto the chest), the path bowing outward."""
    v = Var.draw(seed_of(getattr(event, "line", ""), getattr(event, "seed", 0), getattr(event, "detail", ""),
                         event.kind, hand), float(getattr(event, "energy", 0.5)))
    if hand == "l" and event.hand == "both":  # the left trails the right by 40-80 ms (agent-10: 4 of 14 peaked together)
        lo, hi = TWO_HAND_LAG_S
        v.dt = var_of(event, "r").dt + lo + (hi - lo) * random.Random(seed_of(getattr(event, "line", ""),
                                                                               getattr(event, "seed", 0), "lag")).random()
    if hand == "l":
        v.amp, v.dz, v.overshoot = min(v.amp, 1.0), max(-0.3, min(0.0, v.dz)), v.overshoot * 0.5
        v.bulge = (0.4 * v.bulge[0], min(0.0, v.bulge[1]), min(0.0, v.bulge[2]) * 0.3)
    p = event.pose_r if hand == "r" else (event.pose_l or event.pose_r)
    if event.kind == "deictic" and p.off[1] <= GK.HIGH_REST.off[1] + 2.0:
        v.amp, v.overshoot, v.dz = min(v.amp, 1.0), v.overshoot * 0.35, max(0.0, v.dz)
        v.bulge = (v.bulge[0], abs(v.bulge[1]), v.bulge[2])
    return v


def _mic_clamp(p, w: float = 1.0, box: tuple | None = None):
    """The left hand inside the mic line on a gesture (eased in with the gesture's weight from the rest)."""
    rest = GK.HIGH_REST.off
    box = box or MIC_L
    y_lim = box[0] + max(0.0, rest[1] - box[0]) * (1.0 - w)
    z_lim = box[1] + max(0.0, rest[2] - box[1]) * (1.0 - w)
    return GK.HandPose((p.off[0], min(p.off[1], y_lim), min(p.off[2], z_lim)), p.pron, p.ext, p.shape)


def vary(pose, event, hand: str):
    v = var_of(event, hand)
    p = v.apply(pose)
    if hand == "l":
        p = _mic_clamp(p)
        p = GK.HandPose(p.off, min(p.pron, 60.0), max(p.ext, LEFT_EXT_MIN), p.shape)
    return p


def envelope(phase: str, u: float, event) -> float:
    v = var_of(event, "r")
    if phase == "prep":
        return mj(clip01(u) ** v.skew) * (1.0 + v.overshoot)
    if phase == "hold":
        tau = clip01(u) * max(1e-3, event.hold)
        return 1.0 + v.overshoot * 0.5 * (1.0 + math.cos(math.pi * tau / v.settle)) if tau < v.settle else 1.0
    return 1.0 - mj(u)


def _tracks(perf) -> dict:
    tr = getattr(perf, "_gs_tracks", None)
    if tr is None or tr[0] is not perf.plan:
        tr = (perf.plan, {s: HandTrack(perf.plan.events, s) for s in "lr"})
        perf._gs_tracks = tr
    return tr[1]


def hand(perf, s: str, t: float) -> tuple:
    hp, w = _tracks(perf)[s].at(t)
    big = 0.0
    for i, wi in w.items():
        e = perf.plan.events[i]
        if e.big or e.kind in ("open", "size", "deictic", "count"):
            big = max(big, wi)
    if s == "l":
        two = max([wi for i, wi in w.items() if perf.plan.events[i].hand == "both"] or [0.0])
        if two > 0:
            on = getattr(perf.plan, "on_cam", None) or []
            cam = next((c for a, b, c in on if a <= t < b), None)
            box = MIC_L_CAM.get(cam) if on else min(MIC_L_CAM.values(), key=lambda b: b[1])  # no cut list: every
            hp = _mic_clamp(hp, min(1.0, two), box)  # camera counts, so the tightest box
    return hp, big


def rest_life(perf, s: str, t: float) -> tuple:
    """((fwd, out, up) cm, {finger: deg}) for the desk rest: the track's drift along the desk (never into it) and its
    finger micro-motion at half, so the hands resting there are never frozen either."""
    tr = _tracks(perf)[s]
    off, _, _, fing = tr.micro(t, 0.0, False)
    return (DESK_DRIFT * off[0], DESK_DRIFT * off[1], 0.0), {f: 0.5 * v for f, v in fing.items()}  # (+ "_pip_")


def weights(perf, t: float) -> dict:
    out = {}
    for s, tr in _tracks(perf).items():
        for i, w in tr.at(t)[1].items():
            out[i] = max(out.get(i, 0.0), w)
    return out


def _spread_axes(perf) -> dict:
    """Per hand (reference pose): the palm's normal signed so + turns a finger toward the pinky, and each finger's own
    reference abduction off the middle finger (handshape.abduction: her left rig fans -11 / +8 / +7 deg)."""
    ax = getattr(perf, "_gs_spread", None)
    if ax is not None:
        return ax
    sk, ax = perf.sk, {}
    P = {b: sk.p(b) for b in sk.world}
    Q = {b: sk.q(b) for b in sk.world}
    for s in "lr":
        need = (f"index_01_{s}", f"pinky_01_{s}", f"middle_01_{s}", f"ring_01_{s}", f"hand_{s}")
        if not all(b in sk.local for b in need):
            continue
        kn = sub(sk.p(f"pinky_01_{s}"), sk.p(f"index_01_{s}"))
        n = unit(cross(unit(sub(sk.p(f"middle_01_{s}"), sk.p(f"hand_{s}"))), kn))
        d = sub(sk.p(f"middle_02_{s}"), sk.p(f"middle_01_{s}"))
        if dot(sub(qrot(axis_angle(n, 5.0), d), d), kn) < 0:  # +5 deg must go toward the pinky
            n = mul(n, -1.0)
        ax[s] = {"n": n, "ref": HS.abduction(P, Q, s)}
    perf._gs_spread = ax
    return ax


def finger_post(perf, s: str, hp, W) -> None:
    """Each finger turned about its first joint in the palm's plane to its ABSOLUTE abduction (handshape: nearly
    together at a relaxed hand, the shape's spread opening the fan, closing fingers converging), from the rig's own
    reference fan (R7 hands: relative spread on her left rig's wide fan read as a spider hand)."""
    info_s = _spread_axes(perf).get(s)
    if info_s is None:
        return
    sh = hp.shape if isinstance(hp.shape, dict) else shape_dict(hp.shape)
    spread = float(sh.get("_spread", 0.0))
    sk = perf.sk
    n = qrot(qmul(W["hand_" + s][1], qinv(sk.q("hand_" + s))), info_s["n"])
    for f in ("index", "ring", "pinky"):
        info = perf._finger_info.get((s, f))
        if not info:
            continue
        joints = [j for j in info["joints"] if "metacarpal" not in j and j in W]
        if not joints:
            continue
        turn = HS.abduction_target(f, spread, float(sh.get(f, 0.0))) - info_s["ref"].get(f, 0.0)
        if abs(turn) < 1e-3:
            continue
        r = axis_angle(n, turn)
        piv = W[joints[0]][0]
        for j in joints:
            W[j] = [add(piv, qrot(r, sub(W[j][0], piv))), S.qnorm(qmul(r, W[j][1]))]


# --- the similarity check ------------------------------------------------------------------------------------------

def curve_sim(a: list, b: list) -> float:
    """1 for identical gesture curves, falling with their RMS difference relative to their own spread about their
    means (scale-free: a bigger copy of the same move is not 'different' just for being bigger... but it is not 1)."""
    n = min(len(a), len(b))
    dims = len(a[0])
    diff = math.sqrt(sum((a[k][d] - b[k][d]) ** 2 for k in range(n) for d in range(dims)) / n)

    def spread(c):
        m = [sum(p[d] for p in c) / len(c) for d in range(dims)]
        return math.sqrt(sum((p[d] - m[d]) ** 2 for p in c for d in range(dims)) / len(c))

    ref = 0.5 * (spread(a) + spread(b)) + 1e-6
    return max(0.0, 1.0 - diff / ref)


def curves(perf) -> dict:
    """{(side, event key): curve} for every gesture of both hands."""
    out = {}
    for s, tr in _tracks(perf).items():
        for i, _ in tr.events:
            c = tr.curve(i)
            if c:
                out[(s, tr.keys.get(i, str(i)))] = c
    return out


def similarity(sets: dict) -> dict:
    """The most similar pair of gesture curves, within each film and across films ({film: curves()}): the variation
    check. `pass` while every max stays under SIM_FAIL."""
    rep = {"within": {}, "across": None}
    items = []
    for film, cs in sets.items():
        best = (0.0, None)
        ks = list(cs)
        for x in range(len(ks)):
            for y in range(x + 1, len(ks)):
                if ks[x][0] != ks[y][0]:
                    continue  # one hand against itself (L vs R of one 'both' gesture are mirror partners)
                v = curve_sim(cs[ks[x]], cs[ks[y]])
                if v > best[0]:
                    best = (v, (ks[x], ks[y]))
        rep["within"][film] = {"max": round(best[0], 3), "pair": best[1], "n": len(ks)}
        items += [(film, k, c) for k, c in cs.items()]
    best = (0.0, None)
    for x in range(len(items)):
        for y in range(x + 1, len(items)):
            if items[x][0] == items[y][0] or items[x][1][0] != items[y][1][0]:
                continue
            v = curve_sim(items[x][2], items[y][2])
            if v > best[0]:
                best = (v, ((items[x][0], items[x][1]), (items[y][0], items[y][1])))
    if best[1]:
        rep["across"] = {"max": round(best[0], 3), "pair": best[1]}
    maxes = [w["max"] for w in rep["within"].values()] + ([rep["across"]["max"]] if rep["across"] else [])
    rep["max"] = max(maxes or [0.0])
    rep["pass"] = rep["max"] < SIM_FAIL
    return rep


def frozen_max_s(perf, t0: float, t1: float, fps: float = 30.0, eps_cm_s: float = 0.3) -> dict:
    """The longest run (s) while speaking in which a wrist moves under eps cm/s or the fingers under 0.5 deg/s: the
    'never frozen' row."""
    out = {"wrist": 0.0, "fingers": 0.0}
    runs = {"wrist": 0, "fingers": 0}
    prev = None
    for i in range(int((t1 - t0) * fps)):
        t = t0 + i / fps
        hp = {s: hand(perf, s, t)[0] for s in "lr"}
        cur = {s: (hp[s].off, [hp[s].shape[f] for f in GK.FINGERS]) for s in "lr"}
        if prev and perf.plan.speak_w(t) > 0.5:
            v_w = max(norm(sub(cur[s][0], prev[s][0])) * fps for s in "lr")
            v_f = max(max(abs(a - b) for a, b in zip(cur[s][1], prev[s][1])) * fps for s in "lr")
            for k, still in (("wrist", v_w < eps_cm_s), ("fingers", v_f < 0.5)):
                runs[k] = runs[k] + 1 if still else 0
                out[k] = max(out[k], runs[k] / fps)
        prev = cur
    return {k: round(v, 2) for k, v in out.items()}




def report(perf, length_s: float) -> dict:
    """build's rows: gesture_similarity_max (the most similar pair of one hand's gestures in this take; a pair at
    SIM_FAIL or above is an issue) and frozen_max_s (the longest still wrist / fingers while speaking)."""
    rep = similarity({"take": curves(perf)})
    w = rep["within"]["take"]
    fr = frozen_max_s(perf, 0.0, length_s)
    rows = {"gesture_similarity_max": w["max"], "gesture_similarity_pair": [list(x) for x in (w["pair"] or [])],
            "frozen_max_s": fr}
    issues = []
    if not rep["pass"]:
        issues.append({"code": "body.repeat", "message": f"two gestures {w['pair']} are near-identical "
                       f"(similarity {w['max']})", "value": w["max"]})
    if fr["wrist"] > 1.0 or fr["fingers"] > 1.0:
        issues.append({"code": "body.frozen", "message": f"a hand frozen {max(fr.values())} s while speaking",
                       "value": max(fr.values())})
    return {"rows": rows, "issues": issues}
