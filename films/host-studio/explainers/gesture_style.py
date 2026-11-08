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
from dataclasses import dataclass

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
ACCENT_W = 0.22     # s the accent bump's width
ACCENT_K = 0.7      # x its amplitude
ROT_LAG_S = 0.06    # s the hand's turn and the fingers trail the wrist's path (proximal to distal)
HOLD_MIN_S = 0.1    # s a hold kept at least when the next move takes its time
V_RETRACT = 55.0    # cm/s a retract home's mean speed at most (softer than the stroke)
COART_S = 0.45      # a gap shorter than this flows straight into the next gesture
PARTIAL_S = 1.1     # a gap shorter than this falls only halfway to the rest
LAG_S = {"pinky": 0.030, "ring": 0.045, "thumb": 0.050, "middle": 0.062, "index": 0.080}  # fingers behind the wrist
SPREAD_SIGN = {"index": -1.0, "middle": 0.0, "ring": 0.6, "pinky": 1.2, "thumb": -0.8}
SHAPE_SPREAD = {"rest": 2.0, "relaxed": 3.0, "open": 9.0, "point": 2.0, "count1": 2.0, "count2": 6.0, "count3": 7.0,
                "pinch": 1.0, "soft_fist": 0.0}
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
    """A shape name or dict -> {finger: curl deg, '_spread': deg}."""
    if isinstance(shape, dict):
        d = dict(shape)
        d.setdefault("_spread", 3.0)
        return d
    d = {f: float(GK.SHAPES.get(shape, {}).get(f, 0.0)) for f in GK.FINGERS}
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
                   dz=max(-2.0, min(2.0, g(0, 1.0))), spread=max(-3.0, min(4.0, g(0, 1.6))),
                   fingers={f: max(-6.0, min(6.0, g(0, 2.5))) for f in GK.FINGERS},
                   overshoot=(0.02 + 0.03 * energy) * r.uniform(0.7, 1.3), settle=r.uniform(0.08, 0.12),
                   retract=r.uniform(0.32, 0.5), skew=1.0, lag=r.uniform(0.8, 1.25))  # skew 1: one min-jerk
#                  bell (agent-13: the skewed peak plus the settle read as a spike and a long tail)

    def apply(self, p: GK.HandPose) -> GK.HandPose:
        rest = getattr(GK, "POSE_ORIGIN", GK.HIGH_REST).off  # the amp's origin, not the (r7F, lower) rest
        off = tuple(rest[i] + (p.off[i] - rest[i]) * self.amp + (self.dz if i == 2 else 0.0) for i in range(3))
        sh = shape_dict(p.shape)
        sh = {f: sh[f] + self.fingers.get(f, 0.0) for f in GK.FINGERS} | {"_spread": max(0.0, sh["_spread"] + self.spread)}
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


class HandTrack:
    """The wrist + hand + fingers of one hand over the take, from the plan's events: segments from the rest through
    every gesture (co-articulated where the gaps are short) and home."""

    def __init__(self, events: list, side: str):
        self.side = side
        self.events = [(i, e) for i, e in enumerate(events) if e.hand == side or e.hand == "both"]
        self.keys = {}
        film = "".join(sorted({str(getattr(e, "line", ""))[:1] for e in events}))  # N (her) / W (him) lines
        sd = seed_of(film, side, "micro")
        self.n_off = [Noise(sd + k, 0.35) for k in range(3)]
        self.n_rot = [Noise(sd + 10 + k, 0.45) for k in range(2)]
        self.n_f = {f: Noise(sd + 20 + k, 0.5) for k, f in enumerate(GK.FINGERS)}
        self.n_f_common = Noise(sd + 40, 0.3)
        self.segs = self._build()
        self.accents = self._accents()

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
            start = max(t, min(start, apex - dist(cur, target) / V_MEAN))
            need = apex - dist(cur, target) / V_MEAN
            if start > need and segs and segs[-1].kind == "hold" and segs[-1].t1 == t:  # no room after the last
                #   hold: the hold gives some of its time back (down to HOLD_MIN_S), the move starts sooner
                h = segs[-1]
                start = max(h.t0 + HOLD_MIN_S, need)
                h.t1 = start
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
                t1 = hold_end + min(v.retract, gap)
                segs.append(Seg(hold_end, t1, target, mid, "retract", v, ev=i, w_from=1.0, w_to=0.5))
                cur, cur_w, t = mid, 0.5, t1
                continue
            t1 = hold_end + min(max(v.retract, dist(target, rest) / V_RETRACT), gap)
            segs.append(Seg(hold_end, t1, target, rest, "retract", v, ev=i, w_from=1.0, w_to=0.0))
            cur, cur_w, cur_ev, t = rest, 0.0, -1, t1
        return segs

    def _accents(self) -> list:
        """[(apex t, offset vector cm)]: a quick dip-and-push about the apex of every stroke whose goal is close to
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
            out.append((s.t1, vec))
        return out

    def accent(self, t: float) -> tuple:
        """The accents' offset at t: a cos^2 bump ACCENT_W s wide centred just before the apex (the impact). (r7F: it
        was 0.12 s, a narrow spike on top of the stroke's bell; agent-13 read peak/mean 2.5-3.7)"""
        off = [0.0, 0.0, 0.0]
        for apex, vec in self.accents:
            x = (t - (apex - 0.02)) / (ACCENT_W / 2.0)
            if -1.0 < x < 1.0:
                g = math.cos(0.5 * math.pi * x) ** 2
                for i in range(3):
                    off[i] += vec[i] * g * ACCENT_K
        return off

    def micro(self, t: float, w: float, held: bool) -> tuple:
        """(offset cm, d_pron, d_ext, {finger: deg}): the never-frozen layer. Larger drift on a held stroke."""
        k = 1.0 + (0.8 if held else 0.0)
        off = tuple(0.28 * k * n(t) for n in self.n_off)
        dp, de = 1.6 * k * self.n_rot[0](t), 1.3 * k * self.n_rot[1](t)
        c = self.n_f_common(t)
        fing = {f: 2.6 * (0.6 * self.n_f[f](t) + 0.4 * c) for f in GK.FINGERS}
        return off, dp, de, fing

    def at(self, t: float) -> tuple:
        """(HandPose with a per-finger shape dict, {event index: weight}). The hand's turn and the fingers follow the
        wrist's path ROT_LAG_S behind it (agent-13: proximal to distal, shoulder -> elbow -> wrist -> fingers)."""
        hp, w = self._at(t)
        if ROT_LAG_S <= 0:
            return hp, w
        lag, _ = self._at(t - ROT_LAG_S)
        return GK.HandPose(hp.off, lag.pron, lag.ext, lag.shape), w

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
        sh = {f: sh[f] + fing[f] for f in GK.FINGERS} | {"_spread": sh["_spread"]}
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
            u_f = {f: mj(clip01((t - s.t0 - LAG_S[f] * lag) / d)) for f in GK.FINGERS}
            hp = lerp_pose(s.a, s.b, x, u_rot, u_f, v.bulge, u)
            w_in = s.w_from + (s.w_to - s.w_from) * mj(u)
            w = {s.ev: w_in}
            if s.prev_ev >= 0:
                w[s.prev_ev] = (1.0 - mj(u)) * s.w_from
            return hp, w, False
        # retract: soft (no overshoot, no skew), the wrist follows the hand, a smaller bulge
        x = mj(u)
        u_rot = mj(clip01(u - 0.12))
        u_f = {f: mj(clip01((t - s.t0 - LAG_S[f] * lag) / d)) for f in GK.FINGERS}
        hp = lerp_pose(s.a, s.b, x, u_rot, u_f, tuple(-0.5 * c for c in v.bulge), u)
        return hp, {s.ev: s.w_from + (s.w_to - s.w_from) * x}, False

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


def weights(perf, t: float) -> dict:
    out = {}
    for s, tr in _tracks(perf).items():
        for i, w in tr.at(t)[1].items():
            out[i] = max(out.get(i, 0.0), w)
    return out


def _spread_axes(perf) -> dict:
    """Per hand: the palm's normal (rest), its sign set so +spread moves the index away from the pinky."""
    ax = getattr(perf, "_gs_spread", None)
    if ax is not None:
        return ax
    sk, ax = perf.sk, {}
    for s in "lr":
        need = (f"index_01_{s}", f"index_03_{s}", f"pinky_01_{s}", f"middle_01_{s}", f"middle_03_{s}")
        if not all(b in sk.local for b in need):
            continue
        across = sub(sk.p(f"pinky_01_{s}"), sk.p(f"index_01_{s}"))
        along = unit(sub(sk.p(f"middle_03_{s}"), sk.p(f"middle_01_{s}")))
        n = unit(cross(along, across))
        d_index = sub(sk.p(f"index_03_{s}"), sk.p(f"index_01_{s}"))
        if dot(sub(qrot(axis_angle(n, 5.0), d_index), d_index), across) > 0:  # +5 deg went toward the pinky
            n = mul(n, -1.0)
        ax[s] = n
    perf._gs_spread = ax
    return ax


def finger_post(perf, s: str, hp, W) -> None:
    """Each finger turned about its first joint in the palm's plane by its share of the spread."""
    n0 = _spread_axes(perf).get(s)
    spread = float(hp.shape.get("_spread", 0.0)) if isinstance(hp.shape, dict) else 0.0
    if n0 is None or abs(spread) < 1e-3:
        return
    sk = perf.sk
    n = qrot(qmul(W["hand_" + s][1], qinv(sk.q("hand_" + s))), n0)
    for f in GK.FINGERS:
        info = perf._finger_info.get((s, f))
        if not info or not SPREAD_SIGN[f]:
            continue
        joints = [j for j in info["joints"] if "metacarpal" not in j and j in W]
        if not joints:
            continue
        r = axis_angle(n, spread * SPREAD_SIGN[f])
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
