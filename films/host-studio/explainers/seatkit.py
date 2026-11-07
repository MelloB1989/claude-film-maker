"""A seated presenter on the real MetaHuman body skeleton, solved in pure Python (no Unreal here, so it is tested on
any machine): the body's base pose (local + component-space transforms of every bone, read once from the box by
seated.py's READ job) in, a full-body seated pose per key out, as local bone transforms for an AnimSequence's bone
tracks.

What it builds, in the body's own component space (z up; "forward" is where the feet point, read from the skeleton,
never assumed):
- the hip joints over the actor origin at seat top + HIP_ABOVE_SEAT, the pelvis tilted back a little;
- the spine leaning forward (a podcast lean), the neck and head counter-rotated so the head stays level on the lens;
- the legs by two-bone IK: thighs on the seat, knees forward and a little apart, shins near vertical, feet flat on
  the floor (their rest height and pitch kept, turned out a few degrees);
- the arms by two-bone IK: forearms resting on the desk top, elbows back and out, hands semi-pronated (thumbs up
  and in), the base pose's relaxed fingers kept;
- gestures on emphasis words: a hand (or both) lifts off the desk, opens (supinates) and settles back, eased, never
  below the desk top.

Quaternions are (x, y, z, w) and compose like Unreal's FQuat: world = parent * local (local applied first).
Rotating a vector is q v q*. Positions in cm.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# --- small vector / quaternion maths -------------------------------------------------------------------------------


def add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def mul(a, s):
    return [a[0] * s, a[1] * s, a[2] * s]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    if n < 1e-9:
        raise ValueError("zero vector")
    return [a[0] / n, a[1] / n, a[2] / n]


def ortho(v, d):
    """v with its component along unit d removed, normalised."""
    return unit(sub(v, mul(d, dot(v, d))))


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz]


def qinv(q):
    return [-q[0], -q[1], -q[2], q[3]]


def qrot(q, v):
    p = qmul(qmul(q, [v[0], v[1], v[2], 0.0]), qinv(q))
    return p[:3]


def qnorm(q):
    n = math.sqrt(sum(x * x for x in q)) or 1.0
    return [x / n for x in q]


def axis_angle(axis, deg):
    a = unit(axis)
    h = math.radians(deg) / 2.0
    s = math.sin(h)
    return [a[0] * s, a[1] * s, a[2] * s, math.cos(h)]


def qslerp(a, b, u):
    d = sum(x * y for x, y in zip(a, b))
    if d < 0:
        b, d = [-x for x in b], -d
    if d > 0.9995:
        return qnorm([x + (y - x) * u for x, y in zip(a, b)])
    th = math.acos(max(-1.0, min(1.0, d)))
    s = math.sin(th)
    wa, wb = math.sin((1 - u) * th) / s, math.sin(u * th) / s
    return qnorm([wa * x + wb * y for x, y in zip(a, b)])


def qangle(a, b) -> float:
    """Degrees between two rotations."""
    d = abs(sum(x * y for x, y in zip(qnorm(a), qnorm(b))))
    return math.degrees(2 * math.acos(min(1.0, d)))


def from_matrix(c0, c1, c2):
    """The quaternion of the rotation whose matrix has columns c0, c1, c2 (an orthonormal right- or left-handed set
    as given; columns are the images of the basis vectors)."""
    m00, m10, m20 = c0
    m01, m11, m21 = c1
    m02, m12, m22 = c2
    tr = m00 + m11 + m22
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = [(m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s]
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        q = [0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s]
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        q = [(m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s]
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2
        q = [(m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s]
    return qnorm(q)


def frame_to_frame(d0, f0, d1, f1):
    """The rotation taking direction d0 to d1 and, about it, f0 (made perpendicular to d0) to f1 (perpendicular to
    d1)."""
    d0, d1 = unit(d0), unit(d1)
    f0, f1 = ortho(f0, d0), ortho(f1, d1)
    s0, s1 = cross(d0, f0), cross(d1, f1)
    a = from_matrix(d0, f0, s0)
    b = from_matrix(d1, f1, s1)
    return qnorm(qmul(b, qinv(a)))


def swing(d0, d1):
    """The smallest rotation taking direction d0 to d1."""
    d0, d1 = unit(d0), unit(d1)
    c = dot(d0, d1)
    if c > 1 - 1e-9:
        return [0.0, 0.0, 0.0, 1.0]
    if c < -1 + 1e-9:
        ax = cross(d0, [1.0, 0.0, 0.0])
        if norm(ax) < 1e-6:
            ax = cross(d0, [0.0, 1.0, 0.0])
        return axis_angle(ax, 180.0)
    ax = cross(d0, d1)
    return axis_angle(ax, math.degrees(math.acos(c)))


def two_bone(root, target, l1, l2, pole):
    """Two-bone IK: the middle joint for a chain root -> mid -> end of lengths l1, l2 reaching `target` (clamped to
    reach), bending toward `pole` (a direction). Returns (mid, end)."""
    d = sub(target, root)
    dist = norm(d)
    dist = max(abs(l1 - l2) + 1e-3, min(l1 + l2 - 1e-3, dist))
    dn = unit(d)
    end = add(root, mul(dn, dist))
    a = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist)
    a = max(-1.0, min(1.0, a))
    along, off = l1 * a, l1 * math.sqrt(1 - a * a)
    bend = ortho(pole, dn)
    return add(add(root, mul(dn, along)), mul(bend, off)), end


def smooth(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


# --- the skeleton ----------------------------------------------------------------------------------------------------

LEGS = {s: ("thigh_" + s, "calf_" + s, "foot_" + s, "ball_" + s) for s in "lr"}
ARMS = {s: ("clavicle_" + s, "upperarm_" + s, "lowerarm_" + s, "hand_" + s) for s in "lr"}
SPINE = ("spine_01", "spine_02", "spine_03", "spine_04", "spine_05")
NECK = ("neck_01", "neck_02", "head")
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
REQUIRED = ("root", "pelvis") + SPINE + NECK + sum(LEGS.values(), ()) + sum(ARMS.values(), ()) + (
    "middle_01_l", "middle_01_r", "index_01_l", "index_01_r", "pinky_01_l", "pinky_01_r")


@dataclass
class Skeleton:
    """The base pose: per bone its parent, local (t, q, s) and component-space (t, q) transforms."""
    parent: dict
    local: dict  # bone -> {"t": [3], "q": [4], "s": [3]}
    world: dict  # bone -> {"t": [3], "q": [4]}
    order: list = field(default_factory=list)  # parents before children

    @classmethod
    def from_read(cls, data: dict) -> "Skeleton":
        """From perform.py's READ: parent and local transforms per bone (world: component-space transforms, or None
        to put them together here by FK from the root)."""
        missing = [b for b in REQUIRED if b not in data["local"]]
        if missing:
            raise ValueError(f"the body skeleton lacks {missing} (expects the MetaHuman / UE5 body)")
        order, seen = [], set()

        def visit(b):
            if b in seen:
                return
            p = data["parent"].get(b)
            if p and p in data["local"]:
                visit(p)
            seen.add(b)
            order.append(b)

        for b in data["local"]:
            visit(b)
        world = data.get("world")
        if not world:
            world = {}
            for b in order:
                loc = data["local"][b]
                p = data["parent"].get(b)
                if not p or p not in world:
                    world[b] = {"t": list(loc["t"]), "q": qnorm(list(loc["q"]))}
                    continue
                pt, pq = world[p]["t"], world[p]["q"]
                world[b] = {"t": add(pt, qrot(pq, loc["t"])), "q": qnorm(qmul(pq, loc["q"]))}
        return cls(dict(data["parent"]), data["local"], world, order)

    def p(self, b):
        return self.world[b]["t"]

    def q(self, b):
        return self.world[b]["q"]

    def length(self, a, b):
        return norm(sub(self.p(b), self.p(a)))

    def frame(self) -> dict:
        """forward / left / up of the body in component space, from the feet (calibrate_body's convention)."""
        up = [0.0, 0.0, 1.0]
        if self.p("head")[2] < self.p("pelvis")[2]:
            raise ValueError("component space is not z-up (the head is below the pelvis)")
        fwd = sub(add(self.p("ball_l"), self.p("ball_r")), add(self.p("foot_l"), self.p("foot_r")))
        fwd = unit([fwd[0], fwd[1], 0.0])
        # the component's facing is an axis (a MetaHuman body faces +Y; its Blueprint turns it to the actor's +X):
        # the base pose's few degrees of turn are the pose's, not the frame's
        fwd = max(([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0]), key=lambda a: dot(a, fwd))
        right = cross(fwd, up)  # Unreal's numbers: forward x right = up
        right = mul(right, -1.0)
        hips = unit(sub(self.p("thigh_r"), self.p("thigh_l")))
        if dot(hips, right) < 0.5:
            raise ValueError(f"could not tell right from left (hips {hips}, right {right})")
        return {"fwd": fwd, "right": right, "left": mul(right, -1.0), "up": up}

    def yaw_off(self) -> float:
        """Degrees the base pose's hips are turned (about up, + toward the body's right) from the frame."""
        F = self.frame()
        h = sub(self.p("thigh_r"), self.p("thigh_l"))
        return math.degrees(math.atan2(-dot(h, F["fwd"]), dot(h, F["right"])))


# --- the seated pose -------------------------------------------------------------------------------------------------

@dataclass
class Set:
    """The furniture, in the actor's frame (cm): x forward from the actor origin (the chair mark), z up from the
    floor. agent-07's studio: seat top ~46, desk top 74 with its near edge ~30 cm in front of the chair mark."""
    seat_top: float = 46.0
    desk_top: float = 74.0
    desk_near: float = 30.0  # the desk's near edge, x
    desk_far: float = 100.0
    desk_under: float = 70.0  # the desk's underside (top minus its thickness / apron)
    seat_front: float = 22.0  # the seat's front edge, x
    mic: list | None = None  # [x, y, z] of the mic head, actor frame (y to the presenter's right)
    mic_radius: float = 9.0  # a sphere around the mic head (and its pop filter) no hand may enter
    boom: list | None = None  # [[x, y, z], ...]: the mic's arm as a polyline, clamp -> elbow -> head, actor frame
    boom_radius: float = 4.0


@dataclass
class Style:
    """How this presenter sits. Defaults: a calm podcast posture."""
    hip_above_seat: float = 9.5  # hip joints above the seat top (the soft tissue under the ischia)
    hip_back: float = 0.0  # hips this far behind the actor origin
    pelvis_tilt: float = 6.0  # degrees, back (posterior tilt seated)
    lean: float = 14.0  # degrees of forward lean, spread over the spine (beyond undoing the pelvis tilt)
    lean_share: tuple = (0.15, 0.2, 0.25, 0.22, 0.18)
    twist: float = 0.0  # degrees the chest turns toward the presenter's RIGHT (the cameras' side), over the spine
    twist_share: tuple = (0.1, 0.15, 0.2, 0.25, 0.3)
    head_pitch: float = 0.0  # degrees down from the rest head's pitch (+ = chin down)
    knee_out: float = 7.0  # cm each knee sits outside its hip
    shin_tilt: float = 8.0  # degrees the shin leans forward from vertical (feet ahead of the knees)
    foot_out: float = 8.0  # degrees each foot turns out
    clavicle_fwd: float = 6.0  # degrees of shoulder protraction
    wrist_fwd: float = 36.0  # cm the wrist sits in front of the shoulder line (forward)
    wrist_in: float = 4.0  # cm the wrist sits inside the shoulder (toward the midline)
    wrist_above: float = 3.2  # cm the wrist joint sits above the desk top (the forearm's half thickness)
    elbow_pole: tuple = (-0.55, 0.75, -0.35)  # elbow bend direction: (forward, outward, up) mix
    pronation: float = 50.0  # degrees from palm-down toward thumb-up (0 = flat on the desk)
    hand_yaw_in: float = 14.0  # degrees the fingers point toward the midline
    forearm_clear: float = 2.8  # cm the forearm's axis keeps above the desk top (half its thickness, wrist end)
    heel_lift: float = 0.0  # cm the heels come up off the floor (the balls stay down): short legs on a tall seat
    thigh_radius: float = 6.5  # cm from the femur's axis to the thigh's underside (the seat-edge check)
    finger_clear: float = 0.4  # cm the curled fingertips keep above the desk (the wrist extends until they do)


@dataclass
class Gesture:
    """One hand gesture on an emphasis word. t0 start, t1 at full, t2 release, t3 back on the desk (seconds).
    hand "l", "r" or "both"; kind "lift" (rise + open), "open" (both palms out), "beat" (a small down-stroke)."""
    t0: float
    t1: float
    t2: float
    t3: float
    hand: str = "r"
    kind: str = "lift"
    size: float = 1.0

    def weight(self, t: float) -> float:
        if t <= self.t0 or t >= self.t3:
            return 0.0
        if t < self.t1:
            return smooth((t - self.t0) / max(1e-3, self.t1 - self.t0))
        if t <= self.t2:
            return 1.0
        return 1.0 - smooth((t - self.t2) / max(1e-3, self.t3 - self.t2))


# how far each kind moves the wrist (forward, outward, up cm) and the palm (supination degrees, wrist extension)
KINDS = {
    "lift": {"move": (5.0, 3.0, 11.0), "supinate": 55.0, "extend": 10.0},
    "open": {"move": (7.0, 9.0, 13.0), "supinate": 75.0, "extend": 6.0},
    "beat": {"move": (3.0, 1.0, 6.0), "supinate": 25.0, "extend": -6.0},
    "point": {"move": (10.0, -3.0, 12.0), "supinate": 10.0, "extend": 2.0},
}


class Seater:
    """The seated pose for one skeleton, set and style; `pose(t, gestures)` gives local transforms per bone."""

    def __init__(self, sk: Skeleton, st: Set | None = None, sy: Style | None = None):
        self.sk, self.set, self.sy = sk, st or Set(), sy or Style()
        self.F = sk.frame()
        f, r, u = self.F["fwd"], self.F["right"], self.F["up"]
        self.root = list(sk.p("root"))
        self.deyaw = axis_angle(u, -sk.yaw_off())
        hips = mul(add(sk.p("thigh_l"), sk.p("thigh_r")), 0.5)
        floor = self.root[2]
        # the pelvis moves so the hips' midpoint lands over the origin at the seat height
        want = add(add(self.root, mul(f, -self.sy.hip_back)), [0.0, 0.0, 0.0])
        want[2] = floor + self.set.seat_top + self.sy.hip_above_seat
        self.hip_want = want
        self.hips_rest = hips
        self.L = {s: (sk.length(a, b), sk.length(b, c)) for s, (a, b, c, _) in LEGS.items()}
        self.A = {s: (sk.length(b, c), sk.length(c, d)) for s, (_, b, c, d) in ARMS.items()}
        self.fr = (f, r, u)
        # handedness of (forward, right, up): Unreal's component space is left-handed (x fwd, y right, z up)
        self._rhs = dot(cross(f, r), u) > 0
        self.ext_base = {}
        self.ext_base = self._solve_ext()

    def _solve_ext(self) -> dict:
        """Per hand, the least wrist extension (0..35 deg, 2.5 steps) that keeps every curled fingertip over the desk
        at least finger_clear above it."""
        out = {}
        for s in "lr":
            best = 35.0
            for k in range(15):
                e = 2.5 * k
                self.ext_base = {**out, s: e}
                A = self.fk(self.pose(-1.0, []))
                tips = [self.actor(A[b][0]) for b in A if b.split("_")[0] in FINGERS
                        and (b.endswith(f"_03_{s}") or b.endswith(f"_02_{s}"))]
                tips = [p for p in tips if p[0] >= self.set.desk_near]
                if not tips or min(p[2] for p in tips) >= self.set.desk_top + self.sy.finger_clear:
                    best = e
                    break
            out[s] = best
        return out

    def actor(self, v):
        """Component-space point -> actor frame [x forward, y right, z up from the floor]."""
        f, r, u = self.fr
        d = sub(v, self.root)
        return [dot(d, f), dot(d, r), d[2]]

    def comp(self, a):
        """Actor frame -> component-space point."""
        f, r, u = self.fr
        return add(add(add(self.root, mul(f, a[0])), mul(r, a[1])), [0.0, 0.0, a[2]])

    def pose(self, t: float = 0.0, gestures: list | None = None) -> dict:
        sk, sy, st = self.sk, self.sy, self.set
        f, r, u = self.fr
        W = {}  # bone -> [t, q] component space, new
        # pelvis: moved, tilted back about the body's right axis (+ = forward pitch about right... see sign test)
        # the base pose's own turn undone (about up), then the pelvis pitched back (its top toward -forward)
        tilt = qmul(axis_angle(r, -sy.pelvis_tilt), self.deyaw)
        # placed so the tilted pelvis still puts the hips' midpoint on the mark
        W["pelvis"] = [sub(self.hip_want, qrot(tilt, sub(self.hips_rest, sk.p("pelvis")))), qmul(tilt, sk.q("pelvis"))]
        # spine: rotate each bone's world rotation by the cumulative lean, positions by FK from the pelvis
        cum, tw = -sy.pelvis_tilt, 0.0
        prev = "pelvis"
        for b, share, tshare in zip(SPINE, sy.lean_share, sy.twist_share):
            cum += share * (sy.lean + sy.pelvis_tilt)
            tw += tshare * sy.twist
            # with forward x right = up (Unreal's axes, as numbers), +angle about up turns forward toward the right
            # and +angle about right pitches the top forward
            W[b] = [self._fk_t(b, prev, W), qmul(axis_angle(u, tw if self._rhs else -tw),
                                                 qmul(axis_angle(r, cum), qmul(self.deyaw, sk.q(b))))]
            prev = b
        d5 = qmul(W["spine_05"][1], qinv(sk.q("spine_05")))
        dh = qmul(axis_angle(r, sy.head_pitch), self.deyaw)
        for i, b in enumerate(NECK):
            d = qslerp(d5, dh, (i + 1) / len(NECK))
            W[b] = [self._fk_t(b, sk.parent[b], W), qmul(d, sk.q(b))]
        # legs
        for s, (th, ca, fo, ba) in LEGS.items():
            side = r if s == "r" else mul(r, -1.0)
            hip = self._fk_t(th, "pelvis", W)
            l1, l2 = self.L[s]
            ankle_z = sk.p(fo)[2] + sy.heel_lift  # the feet keep their rest height (+ the heel lift)
            # knee: forward of the hip by the thigh, out by knee_out; then the shin down at shin_tilt to the floor
            ox = sy.knee_out
            # solve the thigh's drop so the shin (l2, tilted) lands at the ankle height
            sh = math.radians(sy.shin_tilt)
            dz = hip[2] - (ankle_z + l2 * math.cos(sh))  # how far the knee is below the hip
            horiz = math.sqrt(max(1.0, l1 * l1 - dz * dz - ox * ox))
            knee = add(add(add(hip, mul(f, horiz)), mul(side, ox)), [0.0, 0.0, -dz])
            ankle = add(add(knee, mul(f, l2 * math.sin(sh))), [0.0, 0.0, -l2 * math.cos(sh)])
            ankle = add(ankle, mul(side, 1.5))  # feet a little wider than the knees
            ankle[2] = ankle_z
            # a knee "front": away from the hip-ankle line
            line = unit(sub(ankle, hip))
            front = ortho(sub(knee, hip), line)
            q_th = self._aim(th, ca, sub(knee, hip), front, front_rest=f)
            W[th] = [hip, q_th]
            W[ca] = [self._fk_t(ca, th, W), self._aim(ca, fo, sub(ankle, knee), front, front_rest=f)]
            # the foot flat as at rest, its heel-to-ball line turned to forward +- foot_out (absolute, whatever
            # the base pose's splay)
            hb = sub(sk.p(ba), sk.p(fo))
            have = math.degrees(math.atan2(dot(hb, r), dot(hb, f)))
            want = sy.foot_out if s == "r" else -sy.foot_out
            qf = qmul(axis_angle(u, (want - have) if self._rhs else (have - want)), sk.q(fo))
            if sy.heel_lift:  # pitch the foot toes-down about the body's right axis so the ball stays on the floor
                L = norm(sub(sk.p(ba), sk.p(fo)))
                drop = sk.p(fo)[2] - sk.p(ba)[2]
                a0 = math.degrees(math.asin(max(-1.0, min(1.0, drop / L))))
                a1 = math.degrees(math.asin(max(-1.0, min(1.0, (drop + sy.heel_lift) / L))))
                qf = qmul(axis_angle(r, a1 - a0), qf)
            W[fo] = [self._fk_t(fo, ca, W), qf]
        # arms
        weights = {"l": [], "r": []}
        for g in gestures or []:
            w = g.weight(t)
            if w > 0:
                for s in ("l", "r") if g.hand == "both" else (g.hand,):
                    weights[s].append((g, w))
        for s, (cl, ua, la, ha) in ARMS.items():
            side = r if s == "r" else mul(r, -1.0)
            W[cl] = [self._fk_t(cl, sk.parent[cl], W),
                     qmul(axis_angle(u, -sy.clavicle_fwd if s == "r" else sy.clavicle_fwd),
                          qmul(self._delta(sk.parent[cl], W), sk.q(cl)))]
            sh = self._fk_t(ua, cl, W)
            wrist = self.wrist_target(s, W, weights[s])
            l1, l2 = self.A[s]
            fwd_, out_, up_ = sy.elbow_pole
            pole = add(add(mul(f, fwd_), mul(side, out_)), mul(u, up_))
            elbow, wrist = two_bone(sh, wrist, l1, l2, pole)
            back = ortho(sub(elbow, sh), unit(sub(wrist, sh)))
            q_ua = self._aim(ua, la, sub(elbow, sh), back, front_rest=mul(f, -1.0))
            W[ua] = [sh, q_ua]
            W[la] = [self._fk_t(la, ua, W), self._aim(la, ha, sub(wrist, elbow), back, front_rest=mul(f, -1.0))]
            W[ha] = [self._fk_t(ha, la, W), self.hand_rot(s, W, weights[s])]
        return self._locals(W)

    # the wrist on the desk, moved by any gestures
    def wrist_target(self, s, W, active) -> list:
        sy, st = self.sy, self.set
        f, r, u = self.fr
        side = r if s == "r" else mul(r, -1.0)
        sh = self._fk_t("upperarm_" + s, "clavicle_" + s, W)
        a = self.actor(sh)
        out_ = abs(a[1]) - sy.wrist_in
        base = [a[0] + sy.wrist_fwd, out_ if s == "r" else -out_, st.desk_top + sy.wrist_above]
        base[0] = max(base[0], st.desk_near + 8.0)
        for g, w in active:
            k = KINDS.get(g.kind, KINDS["lift"])
            mf, mo, mu = (x * g.size * w for x in k["move"])
            base = [base[0] + mf, base[1] + (mo if s == "r" else -mo), base[2] + mu]
        return self.comp(base)

    def hand_rot(self, s, W, active):
        """The hand's component rotation: fingers forward and a little in, the palm semi-pronated, opened by
        gestures."""
        sk, sy = self.sk, self.sy
        f, r, u = self.fr
        side = r if s == "r" else mul(r, -1.0)
        # rest hand frame: fingers (hand -> middle_01) and across the palm (index_01 -> pinky_01)
        d0 = sub(sk.p("middle_01_" + s), sk.p("hand_" + s))
        a0 = sub(sk.p("pinky_01_" + s), sk.p("index_01_" + s))
        sup = sum(KINDS.get(g.kind, KINDS["lift"])["supinate"] * g.size * w for g, w in active)
        ext = self.ext_base.get(s, 0.0) + sum(KINDS.get(g.kind, KINDS["lift"])["extend"] * g.size * w
                                               for g, w in active)
        yaw = math.radians(sy.hand_yaw_in)
        fingers = unit(add(mul(f, math.cos(yaw)), mul(side, -math.sin(yaw))))
        # wrist extension tilts the fingers up
        fingers = unit(add(mul(fingers, math.cos(math.radians(ext))), mul(u, math.sin(math.radians(ext)))))
        pr = math.radians(min(170.0, sy.pronation + sup))
        # palm flat on the desk: pinky toward the outside; turning toward thumb-up drops the pinky edge
        flat = ortho(side, fingers)
        across = unit(add(mul(flat, math.cos(pr)), mul(u, -math.sin(pr))))
        return qmul(frame_to_frame(d0, a0, fingers, across), sk.q("hand_" + s))

    # --- helpers ---
    def _delta(self, b, W):
        return qmul(W[b][1], qinv(self.sk.q(b)))

    def _fk_t(self, b, parent, W):
        """b's component position from its parent's new transform and b's base local translation."""
        pt, pq = W[parent]
        return add(pt, qrot(pq, self.sk.local[b]["t"]))

    def _aim(self, b, child, d1, f1, front_rest):
        sk = self.sk
        d0 = sub(sk.p(child), sk.p(b))
        f0 = front_rest
        if abs(dot(unit(d0), unit(f0))) > 0.98:  # the rest bone points along the front: use up instead
            f0 = [0.0, 0.0, 1.0]
        return qmul(frame_to_frame(d0, f0, d1, f1), sk.q(b))

    def _locals(self, W) -> dict:
        sk = self.sk
        out = {}
        for b, (t, q) in W.items():
            p = sk.parent[b]
            pq = W[p][1] if p in W else self._world_q_of(p, W)
            ql = qnorm(qmul(qinv(pq), q))
            out[b] = {"t": list(sk.local[b]["t"]), "q": ql, "s": list(sk.local[b]["s"])}
        # the pelvis's translation is the one that moves (its parent, root, stays)
        pp = sk.parent["pelvis"]
        rt, rq = sk.p(pp), sk.q(pp)
        out["pelvis"]["t"] = qrot(qinv(rq), sub(W["pelvis"][0], rt))
        return out

    def _world_q_of(self, b, W):
        return self.sk.q(b) if b not in W else W[b][1]

    # --- read-back: the posed skeleton's component transforms (FK over every bone), for the checks ---
    def fk(self, locals_: dict) -> dict:
        sk = self.sk
        out = {}
        for b in sk.order:
            loc = locals_.get(b, sk.local[b])
            p = sk.parent.get(b)
            if not p or p not in out:
                out[b] = [list(sk.p(b)) if b not in locals_ else list(loc["t"]), list(loc["q"])]
                continue
            pt, pq = out[p]
            out[b] = [add(pt, qrot(pq, loc["t"])), qnorm(qmul(pq, loc["q"]))]
        return out


# --- checks ----------------------------------------------------------------------------------------------------------

def check(seater: Seater, posed: dict) -> dict:
    """Numbers on one posed skeleton (component transforms from Seater.fk), in the actor frame: where the hips,
    knees, feet, wrists and fingertips are against the seat, desk, floor and mic; issues for anything inside."""
    st = seater.set
    A = {b: seater.actor(v[0]) for b, v in posed.items()}
    issues = []

    def need(ok, code, msg, value=None):
        if not ok:
            issues.append({"code": code, "message": msg, "value": value})

    floor = 0.0
    hips = [(A["thigh_l"][i] + A["thigh_r"][i]) / 2 for i in range(3)]
    need(abs(hips[2] - (st.seat_top + seater.sy.hip_above_seat)) < 1.0, "seat.hip_height",
         f"hips at z {hips[2]:.1f}, want {st.seat_top + seater.sy.hip_above_seat:.1f}", hips[2])
    for s in "lr":
        k, a = A["calf_" + s], A["foot_" + s]
        need(k[2] < st.desk_under - 6.0, "desk.knee", f"knee_{s} top would touch the desk underside (z {k[2]:.1f})",
             k[2])
        need(a[2] > floor, "floor.ankle", f"ankle_{s} below the floor", a[2])
        rest = seater.sk.p("foot_" + s)[2] - seater.root[2] + seater.sy.heel_lift
        need(abs(a[2] - rest) < 1.0, "floor.foot_lift", f"foot_{s} {a[2] - rest:+.1f} cm off its height",
             a[2] - rest)
        if "ball_" + s in A:
            rb = seater.sk.p("ball_" + s)[2] - seater.root[2]
            need(abs(A["ball_" + s][2] - rb) < 1.0, "floor.ball", f"ball_{s} {A['ball_' + s][2] - rb:+.1f} cm off the "
                 f"floor", A["ball_" + s][2] - rb)
        hp, kn = A["thigh_" + s], A["calf_" + s]
        if kn[0] > st.seat_front > hp[0]:
            u_ = (st.seat_front - hp[0]) / (kn[0] - hp[0])
            under = hp[2] + (kn[2] - hp[2]) * u_ - seater.sy.thigh_radius
            need(under >= st.seat_top - 1.0, "seat.thigh_edge",
                 f"thigh_{s} underside {under:.1f} at the seat edge, {st.seat_top - under:.1f} cm into the seat", under)
        h, e = A["hand_" + s], A["lowerarm_" + s]
        need(h[2] >= st.desk_top + seater.sy.forearm_clear - 0.3, "desk.wrist",
             f"wrist_{s} at z {h[2]:.1f} is inside the desk top {st.desk_top}", h[2])
        if e[0] >= st.desk_near:  # an elbow over the desk must stay on it
            need(e[2] >= st.desk_top + 2.0, "desk.elbow", f"elbow_{s} at z {e[2]:.1f} is inside the desk", e[2])
        for fing in ("index", "middle", "pinky", "ring", "thumb"):
            for j in ("03", "02"):
                b = f"{fing}_{j}_{s}"
                if b in A and A[b][0] >= st.desk_near:
                    need(A[b][2] >= st.desk_top + 0.4, "desk.finger", f"{b} at z {A[b][2]:.1f} below the desk top",
                         A[b][2])
        if st.mic:
            for b in ("hand_" + s, f"middle_03_{s}", f"index_03_{s}", f"thumb_03_{s}"):
                if b in A:
                    d = norm(sub(A[b], st.mic))
                    need(d >= st.mic_radius, "mic.hand", f"{b} {d:.1f} cm from the mic head", d)
        if st.boom:
            for b in ("hand_" + s, "lowerarm_" + s, f"middle_03_{s}", f"index_03_{s}", f"thumb_03_{s}"):
                if b in A:
                    d = poly_dist(A[b], st.boom)
                    need(d >= st.boom_radius + 3.0, "mic.boom", f"{b} {d:.1f} cm from the mic arm", d)
    return {"hips": [round(x, 1) for x in hips],
            "knees": {s: [round(x, 1) for x in A["calf_" + s]] for s in "lr"},
            "ankles": {s: [round(x, 1) for x in A["foot_" + s]] for s in "lr"},
            "elbows": {s: [round(x, 1) for x in A["lowerarm_" + s]] for s in "lr"},
            "wrists": {s: [round(x, 1) for x in A["hand_" + s]] for s in "lr"},
            "head": [round(x, 1) for x in A["head"]],
            "issues": issues, "pass": not issues}


def seg_dist(p, a, b) -> float:
    ab = sub(b, a)
    u = max(0.0, min(1.0, dot(sub(p, a), ab) / max(1e-9, dot(ab, ab))))
    return norm(sub(p, add(a, mul(ab, u))))


def poly_dist(p, pts) -> float:
    return min(seg_dist(p, a, b) for a, b in zip(pts, pts[1:]))


def gestures_from_cues(cues: list, fps: float = 30.0, start_s: float = 0.0) -> list:
    """Gestures from a cue sheet's emphasis words: each {"t": seconds (word onset), "hand"?, "kind"?, "size"?}. The
    hand moves ahead of the word (a gesture's stroke leads the stressed syllable by ~0.1-0.3 s: McNeill), holds
    through it and settles. Overlapping gestures on one hand are merged into the earlier one's hold. Alternates hands
    when none is named."""
    out, last = [], {"l": -9.0, "r": -9.0}
    turn = "r"
    for c in sorted(cues, key=lambda c: c["t"]):
        t = float(c["t"]) - start_s
        hand = c.get("hand") or turn
        turn = "l" if hand == "r" else "r"
        t1 = t - 0.12
        t0 = t1 - 0.38
        t2 = t + float(c.get("hold", 0.45))
        t3 = t2 + 0.6
        busy = [last[h] for h in (("l", "r") if hand == "both" else (hand,))]
        if t0 < max(busy):  # still out from the last one: extend that one's hold instead
            for g in reversed(out):
                if g.hand == hand or hand == "both" or g.hand == "both":
                    g.t2, g.t3 = max(g.t2, t2), max(g.t3, t3)
                    break
            for h in (("l", "r") if hand == "both" else (hand,)):
                last[h] = max(last[h], t3)
            continue
        out.append(Gesture(max(0.0, t0), max(0.01, t1), t2, t3, hand, c.get("kind", "lift"),
                           float(c.get("size", 1.0))))
        for h in (("l", "r") if hand == "both" else (hand,)):
            last[h] = t3
    return out


def build(data: dict, st: Set, sy: Style, gs: list, length_s: float, fps: int = 30) -> tuple:
    """The seated body animation's tracks on a read skeleton (perform.py READ: parent/local/world/tracks): constant
    tracks for every bone the base animation has (its first pose) with the seated pose over them, per-key tracks for
    the bones the gestures move. Returns (doc for the WRITE job, summary with the checks). Pure: runs in the editor's
    Python as well (perform.py body, so a presenter's skeleton never leaves the box)."""
    sk = Skeleton.from_read(data)
    se = Seater(sk, st, sy)
    n = int(round(length_s * fps)) + 1
    still = se.pose(-1.0, [])
    const = {b: data["local"][b] for b in data["tracks"] if b in data["local"]}
    const.update(still)
    moving = sorted({b for s in "lr" for b in ARMS[s][1:]})
    keyed = {b: [] for b in moving}
    issues = []
    for i in range(n):
        t = i / fps
        loc = se.pose(t, gs) if any(g.weight(t) > 0 for g in gs) else still
        for b in moving:
            keyed[b].append({k: [round(x, 6) for x in v] for k, v in loc[b].items()})
        if i % 6 == 0 and loc is not still:
            c = check(se, se.fk({**const, **loc}))
            issues.extend({**x, "t": round(t, 2)} for x in c["issues"])
    for b in moving:
        const.pop(b, None)
    rest = check(se, se.fk({**const, **{b: keyed[b][0] for b in moving}}))
    # the tracks' translations: the engine plays a bone at its animated translation + (mesh ref - skeleton ref)
    # (perform.py READ), so each is written as wanted - that: the skeleton's own for an unmoved bone, the pelvis
    # moved by the seat. Bones translated "Skeleton"-style ignore it either way.
    sref = data.get("skel_t") or {}

    def anim_t(b, t):
        if b not in sref:
            return t
        return [x - (m - k) for x, m, k in zip(t, sk.local[b]["t"], sref[b])]

    for b in list(const):
        const[b] = {**const[b], "t": anim_t(b, const[b]["t"])}
    for b in keyed:
        keyed[b] = [{**k_, "t": anim_t(b, k_["t"])} for k_ in keyed[b]]
    doc = {"length_s": length_s, "fps": fps, "n_keys": n, "const": const, "keyed": keyed}
    summary = {"rest": rest, "gestures": len(gs), "pass": rest["pass"] and not issues, "issues": issues[:20],
               "wrist_ext": se.ext_base, "yaw_off": round(sk.yaw_off(), 2),
               "frame": {"fwd": se.F["fwd"], "right": se.F["right"]}}
    return doc, summary
