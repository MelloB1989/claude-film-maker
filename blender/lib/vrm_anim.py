"""VRM characters that act over time (blender/lib/vrm.py's Character): keyed poses with easing, root motion, IK over
time (feet planted, hands reaching moving targets), walks, runs and kneels, look-at, blinks, breathing, expressions
and lip-sync, props handed from bone to bone, and secondary motion on hair and loose cloth. Generic: anything here
works on any VRM 1.0 humanoid, by vrm.py's humanoid names and its pose convention ((x, y, z) degrees about the
character's own axes, x its left, y its back, z up; relative to the parent bone).

A `Performance` gathers what one character does in a shot, then `bake` writes it as keys on every frame of the shot
(the armature's bones, its IK targets, the root, the face's shape keys, the props' constraints), so a background
render is deterministic: nothing is simulated while rendering, no handler poses anything.

    from lib import vrm, vrm_anim as va

    sh = va.Performance(ch)                         # starts from the pose the builder left (its IK, its holds)
    sh.pose(100, va.STAND, ease="inout")            # a whole-body key (bones it does not name back at rest)
    sh.pose(112, {"rightUpperArm": (-40, -60, 0)}, ease="overshoot", full=False)   # a partial key: that arm only
    sh.hold(130)                                    # hold every keyed channel as it is at 130 (a held breath)
    sh.root(100, (0.0, 0.0, 0.0), yaw=0)            # root motion: the character's feet in the world, its heading
    sh.root(160, (2.0, 0.5, 0.0), yaw=20, ease="inout")
    end = sh.walk([(0, 0), (3, 0.4)], start=100, gait="heavy", end_pose=va.STAND)   # returns the frame it stops on
    end = sh.walk(path, start=100, gait="old", ground=world_ground_object)           # over uneven ground
    sh.kneel(200, 230, side="right", bow=20); sh.hold(260); sh.stand(270, 300)
    sh.look(end, tsuru.face_at, lag=0.25)           # head, eyes and spine turn to a point, an object or a callable
    sh.look(end + 60, None)                         # ... and let go
    sh.blinks(seed=3)                               # natural seeded blinks over the shot (and on big head turns)
    sh.breathe(rate=0.22, depth=1.0)                # a breathing idle under everything else
    sh.shift(140, "left", amount=1.0)               # a weight shift onto the left foot
    sh.express(100, {"glare": 1.0})                 # expressions (the VRM's, or vrm_rig.compose's) over time
    sh.say(14.1, 16.91, "tsuyoku naritai", fps=24)  # lip-sync a line (romaji or kana; film seconds)
    sh.reach(150, "rightHand", hilt, pole=(-0.5, 0.2, 0.6), ease="inout")         # a hand to a moving target
    sh.carry(sword, 150, "rightHand")               # a prop handed to a bone at a frame, its world transform kept
    sh.secondary(wind=(0.3, 0.0, 0.0))              # hair and loose cloth chains react to motion and wind
    sh.dangle(tails, knot, length=0.15)             # rigid props swung from a pivot (headband tails, a straw cape)
    sh.bake(ctx.f0, ctx.f1)

Easing (`EASES`, `ease`): a key says how the channel arrives at it from the key before: "inout" (slow out, slow in),
"in" (slow out of the last key, arriving fast), "out" (leaving fast, settling in), "linear", "hold" (stays at the
last key's value, then cuts to this one on its frame), "overshoot" (past the key and back) and "settle" (a damped wobble
onto it: a big move landing).

Gaits (`GAITS`): "walk", "heavy" (a heavy purposeful stride: long, slow, weight dropping into each step, little arm
swing, leaning in), "old" (an old woman's short steady steps, stooped, feet barely lifting), "run" and "charge"
(long strides with a flight phase, the body pitched forward). Each is a `Gait` (its fields documented there); pass
`gait=va.GAITS["heavy"].but(stride=1.6)` to change one. A walk follows a path on the ground (world x, y points; a
polyline, smoothed), plants its feet (each foot still in the world while it bears weight: the IK targets keyed so,
the hips lowered where a leg would otherwise not reach), rolls them heel to toe, swings the arms against the legs,
counter-turns the hips and shoulders, bobs and sways the body, starts with a short first step and stops with the
trailing foot brought alongside, easing into `end_pose`. `kneel` and `stand` get down onto one knee and up again.

Lip-sync (`visemes`, `Performance.say`): a line's reading (romaji, hiragana or katakana; kanji and other text fall
back to a flap at a natural rate) split into morae, each a vowel shape (VRM's aa, ih, ou, ee, oh, which VRoid binds
to Fcl_MTH_A, I, U, E, O) spread over the line's time with pauses at its punctuation, lips meeting on m, b and p, the
mouth closed between lines. `say(..., quiet=["Fcl_MTH_Close", "*press"])` eases out the parts of a set face that keep
a mouth shut while it speaks.

IK limbs whose elbow or knee no key turns start each frame folded for their target's distance (`fold_for`, the law
of cosines), so a target close to the shoulder (a hilt over it) lands with the elbow out, not on the target.

A film's lines: films/rain-ferry/blender/rf/speech.py keeps each line's romaji reading and timing
(`speech.say(perf, "L03")`).

Props (`carry`): a prop is held by Child Of constraints, one per holder (a humanoid bone, any object, or None: left
where it is in the world), their influences keyed on and off (constant) at the handoffs and each one's inverse set at
its handoff so the prop does not jump; its place on its first holder is read as the scene stands when `bake` starts.

Secondary motion (`secondary`): chains of non-humanoid bones (VRoid's J_Sec_* hair, sleeves, skirts; the default
picks every such chain) simulated after the body is baked, a point per joint pulled toward where the chain would be
carried rigidly (stiffness), with drag, gravity and a gusting wind, lengths kept; keyed as bone turns. Deterministic
(fixed steps, seeded gusts), no spring-bone add-on needed.

With a cast builder (films/<id>/blender/rf/...) that leaves IK on the limbs (vrm.reach, vrm.grasp, vrm.hold): a
Performance keeps them and keys their targets when it is told to (`reach`, `grasp`, `plant`, a walk's feet); a limb
it is not told about stays as the builder left it. To animate an arm freely by FK, drop its IK first
(vrm_rig.release(ch) gives the pose as turns; vrm.pose(ch, that) before the Performance starts from it).

Two characters: build both Performances, then bake each; one can look at the other by its `face_at` (evaluated from
its keys, so the order of the bakes does not matter).

The numpy halves (easing, quaternions, tracks, the root's frame, paths, the walk's plan, blinks, morae and visemes,
look-at angles, the damped follow, the chain sim, FK) are tested without Blender in blender/tests/test_vrm_anim.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from . import vrm

# ---------------------------------------------------------------------------------------------------- poses to start from

# standing easy, a little weight in the knees: vrm.RELAXED's arms with a softer chest
STAND = {**vrm.RELAXED, "spine": (2.0, 0.0, 0.0), "chest": (1.0, 0.0, 0.0), "neck": (-2.0, 0.0, 0.0)}

# ---------------------------------------------------------------------------------------------------- easing

EASES = ("inout", "in", "out", "linear", "hold", "overshoot", "settle")
BACK = 1.70158        # the overshoot's reach (Penner's back ease: about 10% past)


def ease(u: float, kind: str = "inout") -> float:
    """How far (0 at the key before, 1 at this key) a channel has come at `u` (0..1) of the way between two keys,
    arriving by `kind` (EASES). "overshoot" and "settle" go past 1 on the way."""
    u = min(1.0, max(0.0, float(u)))
    if kind == "inout":
        return u * u * (3.0 - 2.0 * u)
    if kind == "in":
        return u * u
    if kind == "out":
        return 1.0 - (1.0 - u) ** 2
    if kind == "linear":
        return u
    if kind == "hold":
        return 1.0 if u >= 1.0 else 0.0
    if kind == "overshoot":
        v = u - 1.0
        return 1.0 + (BACK + 1.0) * v ** 3 + BACK * v ** 2
    if kind == "settle":
        # fast in, a damped wobble about the key (two small swings), exactly on it at the end
        if u >= 1.0:
            return 1.0
        return 1.0 - math.exp(-7.0 * u) * math.cos(2.5 * math.pi * u) * (1.0 - u ** 6)
    raise ValueError(f"no ease {kind!r} (one of {', '.join(EASES)})")


def smoothstep(e0: float, e1: float, x: float) -> float:
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------------------------------- rotations

def turn_matrix(turn) -> np.ndarray:
    """A turn ((x, y, z) degrees, vrm.euler's order, or a 3x3) as a 3x3."""
    a = np.asarray(turn, float)
    return a if a.shape == (3, 3) else vrm.euler(a)


def quat(m) -> np.ndarray:
    """A rotation matrix as a unit quaternion (w, x, y, z), w >= 0."""
    m = np.asarray(m, float)
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = np.array([0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s])
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = np.array([(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s])
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = np.array([(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s])
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = np.array([(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s])
    q /= np.linalg.norm(q)
    return q if q[0] >= 0 else -q


def matrix(q) -> np.ndarray:
    """A quaternion (w, x, y, z) as a rotation matrix."""
    w, x, y, z = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def slerp(q0, q1, k: float) -> np.ndarray:
    """From quaternion q0 to q1 by k (the short way; k outside 0..1 carries on past either end)."""
    q0, q1 = np.asarray(q0, float), np.asarray(q1, float)
    d = float(np.dot(q0, q1))
    if d < 0:
        q1, d = -q1, -d
    if d > 0.9995:
        q = q0 + (q1 - q0) * k
        return q / np.linalg.norm(q)
    th = math.acos(min(1.0, d))
    s = math.sin(th)
    return (math.sin((1 - k) * th) * q0 + math.sin(k * th) * q1) / s


def angle_between(a, b) -> float:
    """Degrees between two rotation matrices."""
    r = np.asarray(a, float).T @ np.asarray(b, float)
    return math.degrees(math.acos(min(1.0, max(-1.0, (np.trace(r) - 1) / 2))))


def axis_angle(axis, degrees: float) -> np.ndarray:
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    t = math.radians(degrees)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * k + (1 - math.cos(t)) * k @ k


def swing_to(a, b) -> np.ndarray:
    """The shortest rotation taking direction a to direction b."""
    a = np.asarray(a, float) / np.linalg.norm(a)
    b = np.asarray(b, float) / np.linalg.norm(b)
    c = np.cross(a, b)
    s, d = np.linalg.norm(c), float(np.dot(a, b))
    if s < 1e-9:
        if d > 0:
            return np.eye(3)
        perp = np.cross(a, [1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.cross(a, [0.0, 1.0, 0.0])
        return axis_angle(perp, 180.0)
    return axis_angle(c, math.degrees(math.atan2(s, d)))


# ---------------------------------------------------------------------------------------------------- tracks

@dataclass
class Key:
    frame: float
    value: object
    ease: str = "inout"


class Track:
    """Keys of one channel over frames: a vector (`kind` "vec") or a rotation ("rot": 3x3 matrices, slerped). Each key
    says how the channel arrives at it (`ease`). Before the first key it holds the first, after the last the last."""

    def __init__(self, kind: str = "vec"):
        if kind not in ("vec", "rot"):
            raise ValueError(f"a track is 'vec' or 'rot', not {kind!r}")
        self.kind = kind
        self.keys: list[Key] = []

    def key(self, frame: float, value, ease_: str = "inout") -> None:
        if ease_ not in EASES:
            raise ValueError(f"no ease {ease_!r} (one of {', '.join(EASES)})")
        v = quat(turn_matrix(value)) if self.kind == "rot" else np.asarray(value, float)
        self.keys = [k for k in self.keys if abs(k.frame - frame) > 1e-6]
        self.keys.append(Key(float(frame), v, ease_))
        self.keys.sort(key=lambda k: k.frame)

    def __bool__(self) -> bool:
        return bool(self.keys)

    def span(self) -> tuple[float, float]:
        return self.keys[0].frame, self.keys[-1].frame

    def raw(self, frame: float):
        """The value at `frame` (a quaternion for a rotation track)."""
        ks = self.keys
        if not ks:
            raise ValueError("an empty track has no value")
        if frame <= ks[0].frame:
            return ks[0].value
        if frame >= ks[-1].frame:
            return ks[-1].value
        i = int(np.searchsorted([k.frame for k in ks], frame, side="right"))
        a, b = ks[i - 1], ks[i]
        k = ease((frame - a.frame) / (b.frame - a.frame), b.ease)
        if self.kind == "rot":
            return slerp(a.value, b.value, k)
        return a.value + (b.value - a.value) * k

    def at(self, frame: float):
        """The value at `frame`: a vector, or a 3x3 for a rotation track."""
        v = self.raw(frame)
        return matrix(v) if self.kind == "rot" else v


# ---------------------------------------------------------------------------------------------------- the root's frame

# the character's frame (x its left, y its back, z up) as the world sees it on a root turned by nothing: it faces +x,
# its left at +y (vrm.load turns the armature so)
CHAR_TO_WORLD = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])


def rz(degrees: float) -> np.ndarray:
    t = math.radians(degrees)
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def to_world(p, root, yaw: float) -> np.ndarray:
    """A point of the character's frame (metres as it stands) in the world, its root at `root` turned `yaw` degrees
    (0 faces +x, 90 faces +y)."""
    return np.asarray(root, float) + rz(yaw) @ CHAR_TO_WORLD @ np.asarray(p, float)


def to_char(p, root, yaw: float) -> np.ndarray:
    """A world point in the character's frame (the inverse of `to_world`)."""
    return CHAR_TO_WORLD.T @ rz(-yaw) @ (np.asarray(p, float) - np.asarray(root, float))


def heading(direction) -> float:
    """The yaw (degrees, `to_world`'s) that faces a world direction (its x, y)."""
    return math.degrees(math.atan2(float(direction[1]), float(direction[0])))


def unwrap(prev: float, deg: float) -> float:
    """`deg` moved by whole turns to within 180 of `prev` (a heading never spins the long way)."""
    return deg + 360.0 * round((prev - deg) / 360.0)


# ---------------------------------------------------------------------------------------------------- paths

class Path:
    """A path on the ground through world (x, y) points: a polyline, its corners rounded (Chaikin), measured by
    length. `at(s)` is the point s metres along (clamped), `tangent(s)` its unit direction."""

    def __init__(self, points, *, round_corners: int = 3, step: float = 0.02):
        p = np.asarray(points, float)[:, :2]
        if len(p) < 2:
            raise ValueError("a path needs two points at least")
        keep = np.concatenate([[True], np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-6])
        p = p[keep]
        if len(p) < 2:
            raise ValueError("a path's points are all in one place")
        for _ in range(round_corners if len(p) > 2 else 0):
            q = [p[0]]
            for a, b in zip(p[:-1], p[1:]):
                q += [0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b]
            q.append(p[-1])
            p = np.array(q)
        seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
        s = np.concatenate([[0.0], np.cumsum(seg)])
        n = max(2, int(math.ceil(s[-1] / step)) + 1)
        self.s = np.linspace(0.0, s[-1], n)
        self.xy = np.c_[np.interp(self.s, s, p[:, 0]), np.interp(self.s, s, p[:, 1])]
        self.length = float(s[-1])

    def at(self, s: float) -> np.ndarray:
        s = min(self.length, max(0.0, float(s)))
        return np.array([np.interp(s, self.s, self.xy[:, 0]), np.interp(s, self.s, self.xy[:, 1])])

    def tangent(self, s: float, span: float = 0.15) -> np.ndarray:
        a, b = self.at(s - span), self.at(s + span)
        d = b - a
        if np.linalg.norm(d) < 1e-9:
            d = self.xy[-1] - self.xy[0]
        return d / np.linalg.norm(d)

    def yaw(self, s: float, span: float = 0.15) -> float:
        return heading(self.tangent(s, span))


def pchip(x, y, xs, *, flat_ends: bool = True) -> np.ndarray:
    """Monotone cubic (Fritsch-Carlson) through (x, y) at xs: never overshoots a knot, so a body moving through its
    knots never steps back. `flat_ends` starts and ends at rest."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    xs = np.asarray(xs, float)
    n = len(x)
    if n == 1:
        return np.full_like(xs, y[0])
    h = np.diff(x)
    d = np.diff(y) / h
    m = np.zeros(n)
    for i in range(1, n - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    if not flat_ends:
        m[0], m[-1] = d[0], d[-1]
    out = np.empty_like(xs)
    i = np.clip(np.searchsorted(x, xs, side="right") - 1, 0, n - 2)
    t = np.clip((xs - x[i]) / h[i], 0.0, 1.0)
    h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
    out[:] = h00 * y[i] + h10 * h[i] * m[i] + h01 * y[i + 1] + h11 * h[i] * m[i + 1]
    out[xs <= x[0]] = y[0]
    out[xs >= x[-1]] = y[-1]
    return out


# ---------------------------------------------------------------------------------------------------- gaits

@dataclass(frozen=True)
class Gait:
    """How a character moves its feet. Lengths in metres for a character `height` tall (scaled to the one walking),
    angles in degrees.
      stride      one step's length (heel to heel of successive feet)
      speed       metres per second on the level
      duty        the share of a cycle a foot bears weight (over 0.5 a walk, both feet down between steps; under,
                  a run with a flight)
      lift        how high a swinging foot clears the ground
      width       how far apart the feet land (centre to centre)
      toe_out     each foot turned out
      bob         the body's rise (+) at mid-stance (a walk vaults over the leg) or drop (-, a run sinks into it)
      drop        the hips lowered throughout (knees soft)
      sway        the hips toward the foot that bears weight
      hip_turn    the hips turned with the swinging leg
      chest_turn  the shoulders counter-turned (a share of hip_turn, the other way)
      arm         the arms' swing, against the legs
      elbow       the elbows' bend (more when the arm swings forward)
      lean        the body pitched forward (spine and chest)
      head        the head held against the body's pitch and bob (0 none, 1 level)
      roll        the foot's roll at toe-off and heel-strike
      first       the first step's length, a share of a stride
      plod        weight dropping into each step: the body's dip just after the foot lands
    """
    stride: float = 0.7
    speed: float = 1.25
    duty: float = 0.62
    lift: float = 0.09
    width: float = 0.17
    toe_out: float = 6.0
    bob: float = 0.018
    drop: float = 0.025
    sway: float = 0.025
    hip_turn: float = 6.0
    chest_turn: float = 1.3
    arm: float = 16.0
    elbow: float = 12.0
    lean: float = 3.0
    head: float = 0.6
    roll: float = 22.0
    first: float = 0.6
    plod: float = 0.0
    height: float = 1.7

    def but(self, **kw) -> "Gait":
        return replace(self, **kw)

    def scaled(self, height: float) -> "Gait":
        """The gait for a character `height` tall (lengths and speed in proportion)."""
        k = float(height) / self.height
        return replace(self, stride=self.stride * k, speed=self.speed * k, lift=self.lift * k, width=self.width * k,
                       bob=self.bob * k, drop=self.drop * k, sway=self.sway * k, height=float(height))


GAITS = {
    "walk": Gait(stride=0.64),
    "heavy": Gait(stride=0.7, speed=1.05, duty=0.64, lift=0.08, width=0.2, toe_out=8.0, bob=0.012, drop=0.05,
                  sway=0.03, hip_turn=7.0, chest_turn=1.1, arm=9.0, elbow=10.0, lean=6.0, head=0.8, roll=20.0,
                  plod=0.022),
    "old": Gait(stride=0.34, speed=0.42, duty=0.72, lift=0.035, width=0.16, toe_out=10.0, bob=0.006, drop=0.03,
                sway=0.02, hip_turn=3.0, chest_turn=0.8, arm=5.0, elbow=15.0, lean=4.0, head=0.4, roll=8.0,
                first=0.7, plod=0.004, height=1.48),
    "run": Gait(stride=1.25, speed=4.0, duty=0.36, lift=0.2, width=0.12, toe_out=4.0, bob=-0.03, drop=0.06,
                sway=0.015, hip_turn=9.0, chest_turn=1.4, arm=38.0, elbow=75.0, lean=12.0, head=0.7, roll=28.0,
                first=0.45),
    "charge": Gait(stride=1.45, speed=4.8, duty=0.34, lift=0.17, width=0.14, toe_out=3.0, bob=-0.035, drop=0.1,
                   sway=0.02, hip_turn=10.0, chest_turn=1.6, arm=24.0, elbow=65.0, lean=22.0, head=0.85, roll=30.0,
                   first=0.4, plod=0.01),
}


def gait_of(gait) -> Gait:
    if isinstance(gait, Gait):
        return gait
    if gait not in GAITS:
        raise KeyError(f"no gait {gait!r} (one of {', '.join(GAITS)})")
    return GAITS[gait]


@dataclass
class Step:
    """One step of a walk's plan: `side` ("left" or "right") lifts at `t0` (seconds from the walk's start) and lands at
    `t1`, from `a` to `b` (distances along the path) at heading yaw0 to yaw1."""
    side: str
    a: float
    b: float
    t0: float
    t1: float


def plan_steps(length: float, gait: Gait, *, lead: str = "right") -> tuple[list[Step], np.ndarray, np.ndarray]:
    """The steps of a walk `length` metres along a path, starting and stopping with the feet together: a short first
    step (`gait.first` of a stride) by the `lead` foot, steps of about a stride (the same length each, fitting the
    path), and the trailing foot brought alongside the leading at the end. Returns (steps, knots of the body's
    distance along the path: times, distances): the body passes over each foot bearing weight while the other swings
    by it, eases off from rest and settles to rest over the last foot."""
    if length <= 1e-6:
        return [], np.array([0.0]), np.array([0.0])
    first = min(length, gait.stride * gait.first)
    rest = length - first
    n = int(math.ceil(rest / gait.stride - 0.15)) if rest > 0 else 0      # steps no longer than a stride (a little over)
    if rest > 1e-6 and n == 0:
        n = 1
    plants = [first] + [first + rest * (i + 1) / n for i in range(n)]       # the landing places, in order
    t_step = gait.stride / gait.speed                    # one step's time at speed
    swing = min(0.95 * t_step * 2, 2.0 * (1.0 - gait.duty) * t_step)       # a foot's time in the air
    other = "left" if lead == "right" else "right"
    sides = [lead if i % 2 == 0 else other for i in range(len(plants))]
    steps, t = [], 0.0
    pos = {lead: 0.0, other: 0.0}
    for i, (side, b) in enumerate(zip(sides, plants)):
        # the first step goes out before the body has much speed: shorter in time as in length
        dur = swing * (0.8 if i == 0 else 1.0)
        steps.append(Step(side, pos[side], b, t, t + dur))
        pos[side] = b
        # a walk keeps a foot down between steps (the next lifts once this one lands); a run does not
        t += t_step if i else (max(t_step * 0.8, dur + 0.04) if gait.duty > 0.5 else t_step * 0.8)
    trail = other if sides[-1] == lead else lead
    close = swing * 0.85
    steps.append(Step(trail, pos[trail], plants[-1], t, t + close))
    # the body's distance: from rest, over the foot that bears weight while the other swings by it (the one that landed
    # a step before), easing off from rest and settling to rest over the end
    times, dists = [0.0], [0.0]
    for i in range(1, len(steps) - 1):
        tm = (steps[i].t0 + steps[i].t1) / 2
        stand = plants[i - 1]
        if stand > dists[-1] + 1e-6 and tm > times[-1] + 1e-6:
            times.append(tm)
            dists.append(stand)
    end = steps[-1].t1 + 0.35 * t_step
    times.append(max(end, times[-1] + 0.1))
    dists.append(max(length, dists[-1]))
    return steps, np.array(times), np.array(dists)


def pos_at(steps: list[Step], side: str, t: float) -> float:
    """Where along the path a foot is planted at t (its last landing), or mid-step's start."""
    p = 0.0
    for st in steps:
        if st.side == side and st.t0 <= t:
            p = st.b if t >= st.t1 else st.a
    return p


def foot_phase(steps: list[Step], side: str, t: float) -> tuple[float, float, float, float]:
    """A foot at t: (from, to, u, since) where it is moving from `from` to `to` along the path, u its progress through
    its swing (0 planted before it lifts, 1 landed), and `since` seconds since it last landed (inf before any step);
    -until: seconds until it next lifts are in `until_lift`."""
    a = b = 0.0
    since = math.inf
    for st in steps:
        if st.side != side:
            continue
        if t < st.t0:
            break
        if t < st.t1:
            return st.a, st.b, (t - st.t0) / (st.t1 - st.t0), 0.0
        a = b = st.b
        since = t - st.t1
    return a, b, 1.0, since


def until_lift(steps: list[Step], side: str, t: float) -> float:
    for st in steps:
        if st.side == side and st.t0 >= t:
            return st.t0 - t
    return math.inf


# ---------------------------------------------------------------------------------------------------- blinks

def blink_times(t0: float, t1: float, *, seed: int = 0, mean: float = 3.6, least: float = 1.2,
                double: float = 0.12, extra=()) -> list[float]:
    """When a character blinks between t0 and t1 seconds: gaps drawn round `mean` seconds (never under `least`), now
    and then a quick double blink (`double` of them), plus the times in `extra` (a blink on a big head turn); none
    closer than 0.25 s apart. Seeded: the same seed blinks the same."""
    rng = np.random.default_rng(seed)
    out, t = [], t0 + rng.uniform(0.3, mean)
    while t < t1:
        out.append(t)
        if rng.random() < double:
            out.append(t + rng.uniform(0.28, 0.4))
        t += max(least, rng.gamma(4.0, mean / 4.0))
    out += [float(e) for e in extra if t0 <= e < t1]
    out.sort()
    kept = []
    for b in out:
        if not kept or b - kept[-1] >= 0.25:
            kept.append(b)
    return kept


def blink_shape(dt: float, *, close: float = 0.06, shut: float = 0.03, open_: float = 0.13) -> float:
    """How closed (0..1) the lids are `dt` seconds after a blink begins: down fast, shut a moment, up slower."""
    if dt < 0 or dt > close + shut + open_:
        return 0.0
    if dt < close:
        return ease(dt / close, "in")
    if dt < close + shut:
        return 1.0
    return 1.0 - ease((dt - close - shut) / open_, "out")


# ---------------------------------------------------------------------------------------------------- speech

VOWELS = {"a": "aa", "i": "ih", "u": "ou", "e": "ee", "o": "oh"}
# how open each vowel's mouth is at full voice (the jaw: aa widest)
OPEN = {"aa": 1.0, "oh": 0.8, "ee": 0.65, "ou": 0.55, "ih": 0.5}
_KANA_ROWS = {
    "a": "あかさたなはまやらわがざだばぱぁゃアカサタナハマヤラワガザダバパァャ",
    "i": "いきしちにひみりぎじぢびぴぃイキシチニヒミリギジヂビピィ",
    "u": "うくすつぬふむゆるぐずづぶぷぅゅっウクスツヌフムユルグズヅブプゥュッヴ",
    "e": "えけせてねへめれげぜでべぺぇエケセテネヘメレゲゼデベペェ",
    "o": "おこそとのほもよろをごぞどぼぽぉょオコソトノホモヨロヲゴゾドボポォョ",
}
_KANA = {ch: v for v, row in _KANA_ROWS.items() for ch in row}
_LIPS = set("まみむめもばびぶべぼぱぴぷぺぽマミムメモバビブベボパピプペポ")
_SMALL = set("ゃゅょぁぃぅぇぉャュョァィゥェォ")
PAUSE = {",": 0.6, "、": 0.6, ".": 1.0, "。": 1.0, "!": 1.0, "！": 1.0, "?": 1.0, "？": 1.0, "…": 1.2, "‥": 0.8,
         ";": 0.6, ":": 0.6, "—": 0.6, "-": 0.3}


@dataclass
class Mora:
    vowel: str | None      # a viseme (aa, ih, ou, ee, oh), or None for a closed mouth (n, a held m)
    lips: bool = False     # the lips meet before it (m, b, p)
    weight: float = 1.0    # its share of time (a long vowel counts two)
    pause: float = 0.0     # a pause after it, in morae


def morae(text: str) -> list[Mora]:
    """A line's reading as morae: romaji ("tsuyoku naritai"), hiragana or katakana. A character neither reads (kanji,
    another script) counts as one and a half open morae of no particular vowel ("aa"/"oh"/"ee" in turn), so any line
    still flaps at a natural rate. Punctuation adds a pause to the mora before it."""
    out: list[Mora] = []
    s = text.strip()
    i, cycle = 0, 0
    lips = False
    while i < len(s):
        c = s[i]
        lo = c.lower()
        if c in PAUSE:
            if out:
                out[-1].pause += PAUSE[c]
            i += 1
            continue
        if c.isspace() or c in "「」『』()（）[]\"'":
            i += 1
            continue
        if c in "ーｰ" and out:                          # a long vowel mark
            out[-1].weight += 1.0
            i += 1
            continue
        if c in _SMALL and out:                        # きゃ: the small kana's vowel replaces the mora's
            out[-1].vowel = VOWELS[_KANA[c]]
            i += 1
            continue
        if c in "んン":
            out.append(Mora(None, weight=0.8))
            i += 1
            continue
        if c in _KANA:
            if c in "っッ":
                out.append(Mora(None, weight=0.7))         # a held stop: the mouth set, no vowel
            else:
                out.append(Mora(VOWELS[_KANA[c]], lips=c in _LIPS))
            i += 1
            continue
        if "a" <= lo <= "z":
            if lo in VOWELS:
                if out and out[-1].vowel == VOWELS[lo] and not lips and i > 0 and s[i - 1].lower() == lo:
                    out[-1].weight += 1.0                  # "aa", "ii": one long vowel
                elif out and lo == "u" and i > 0 and s[i - 1].lower() == "o" and out[-1].vowel == "oh":
                    out[-1].weight += 1.0                  # "ou": a long o
                else:
                    out.append(Mora(VOWELS[lo], lips=lips))
                lips = False
            elif lo == "n" and (i + 1 >= len(s) or s[i + 1].lower() not in "aiueoy"):
                out.append(Mora(None, weight=0.8))        # the syllabic n
            elif lo in "mbp":
                if i + 1 < len(s) and s[i + 1].lower() == lo:
                    out.append(Mora(None, weight=0.7, lips=True))   # a doubled consonant: held
                    i += 1
                lips = True
            elif i + 1 < len(s) and s[i + 1].lower() == lo and lo not in "aiueon":
                out.append(Mora(None, weight=0.7))        # "tt", "kk": a held stop
                i += 1
            i += 1
            continue
        if c.isalnum():                                  # kanji and anything else that is said
            out.append(Mora(("aa", "oh", "ee", "ih", "aa", "ou")[cycle % 6], weight=1.5))
            cycle += 1
        i += 1
    return out


def visemes(text: str, start: float, end: float, *, seed: int = 0, energy: float = 1.0,
            step: float = 1.0 / 48.0) -> list[tuple[float, dict]]:
    """Mouth shapes for a line said from `start` to `end` seconds: [(seconds, {viseme: weight})], one every `step`
    seconds from just before the line to just after, the mouth shut at both ends. Each mora opens to its vowel (by OPEN,
    times `energy` and a little seeded variation) and eases toward the next, a mora after lips that meet closing first;
    a pause shuts it."""
    ms = morae(text) or [Mora("aa")]
    rng = np.random.default_rng(seed)
    total = sum(m.weight + m.pause for m in ms)
    dur = max(1e-3, end - start)
    unit = dur / total
    # each mora's [onset, end) in seconds
    spans, t = [], start
    for m in ms:
        spans.append((t, t + m.weight * unit, m))
        t += (m.weight + m.pause) * unit
    loud = [float(np.clip(rng.normal(1.0, 0.12), 0.75, 1.15)) for _ in ms]
    # a line's last mora trails off, its first is a little held back
    loud[-1] *= 0.8
    out = []
    lead = 0.04                     # the mouth moves a hair before the sound
    ts = np.arange(start - 0.12, end + 0.15, step)
    for tt in ts:
        tq = tt + lead
        w: dict = {}
        for (a, b, m), g in zip(spans, loud):
            if m.vowel is None:
                continue
            d = b - a
            # a flap: the jaw opens through the mora and is half shut again where the next begins (the lips shut
            # where they meet first); a pause after it lets it close slower
            o0 = 0.0 if m.lips else 0.1 * d
            o1 = 0.1 * d if m.pause == 0 else min(0.12, 0.6 * d)
            x = (tq - (a - o0)) / (d + o0 + o1)
            if x <= 0 or x >= 1:
                continue
            k = math.sin(math.pi * x) ** 0.8
            w[m.vowel] = max(w.get(m.vowel, 0.0), k * OPEN[m.vowel] * g * energy)
        out.append((float(tt), w))
    return out


# ---------------------------------------------------------------------------------------------------- follow and look

def smooth_damp(x: float, v: float, target: float, smooth: float, dt: float) -> tuple[float, float]:
    """One step of a critically damped follow of `target` taking about `smooth` seconds to arrive (no overshoot):
    returns the new (value, velocity)."""
    if smooth <= 1e-6:
        return target, 0.0
    omega = 2.0 / smooth
    e = omega * dt
    k = 1.0 / (1.0 + e + 0.48 * e * e + 0.235 * e * e * e)
    change = x - target
    temp = (v + omega * change) * dt
    v2 = (v - omega * temp) * k
    return target + (change + temp) * k, v2


def yaw_pitch(d) -> tuple[float, float]:
    """A direction in the character's frame as (yaw, pitch) degrees: yaw + to its left (z+, vrm's turn), pitch + down
    (x+, a nod), (0, 0) straight ahead (-y)."""
    d = np.asarray(d, float)
    yaw = math.degrees(math.atan2(d[0], -d[1]))
    pitch = math.degrees(math.atan2(-d[2], math.hypot(d[0], d[1])))
    return yaw, pitch


# how a look's turn is shared down the body: (yaw share, pitch share) per bone, the eyes taking what is left
LOOK_SHARES = {"spine": (0.08, 0.0), "chest": (0.1, 0.05), "upperChest": (0.1, 0.05), "neck": (0.27, 0.35),
               "head": (0.45, 0.55)}
LOOK_LAG = {"eyes": 0.06, "head": 1.0, "neck": 1.2, "upperChest": 1.8, "chest": 2.2, "spine": 2.6}
EYE_LIMIT = (22.0, 14.0)        # how far eyes turn in the head (yaw, pitch)
HEAD_LIMIT = (80.0, 45.0)


# ---------------------------------------------------------------------------------------------------- forward kinematics

def fk(order, parents: dict, rest_heads: dict, turns: dict, *, hips_offset=(0.0, 0.0, 0.0)) -> tuple[dict, dict]:
    """Posed bones in the character's frame by vrm.py's convention: each bone's turn (3x3) about the character's
    axes relative to its parent. `order` lists bones parents first; `rest_heads` their heads at rest; a bone's
    parent not in `order` counts as the root (unturned). Returns ({bone: total turn 3x3}, {bone: posed head})."""
    tot, head = {}, {}
    for b in order:
        p = parents.get(b)
        tp = tot.get(p, np.eye(3))
        tb = turns.get(b)
        tot[b] = tp @ (np.eye(3) if tb is None else tb)
        if p in head:
            head[b] = head[p] + tp @ (np.asarray(rest_heads[b], float) - np.asarray(rest_heads[p], float))
        else:
            head[b] = np.asarray(rest_heads[b], float) + np.asarray(hips_offset, float)
    return tot, head


# ---------------------------------------------------------------------------------------------------- chains

def chain_step(pts, prev, goal, lengths, *, dt: float, stiffness: float, drag: float, gravity, wind,
               iterations: int = 4) -> np.ndarray:
    """One step of a hanging chain (verlet): points `pts` (n+1, 3; the first pinned at its root's place in `goal`),
    their positions a step before `prev`, pulled toward `goal` (where the chain would be carried rigidly) by
    `stiffness` (per second), slowed by `drag` (0..1 a step), pushed by `gravity` and `wind` (m/s^2), then each link
    put back to its length from the root out. Returns the new points (n+1, 3)."""
    p, q, g = np.asarray(pts, float), np.asarray(prev, float), np.asarray(goal, float)
    vel = (p - q) * (1.0 - drag)
    acc = np.asarray(gravity, float) + np.asarray(wind, float)
    new = p + vel + acc * dt * dt
    pull = min(1.0, stiffness * dt)
    new = new + (g - new) * pull
    new[0] = g[0]
    for _ in range(iterations):
        for i in range(1, len(new)):
            d = new[i] - new[i - 1]
            n = np.linalg.norm(d)
            if n > 1e-9:
                new[i] = new[i - 1] + d * (lengths[i - 1] / n)
    return new


def gust(t: float, seed: int = 0) -> float:
    """A wind's strength over time (about 1 on average, 0.55..1.45): a few slow sines at seeded rates and phases."""
    rng = np.random.default_rng(seed)
    rates = rng.uniform(0.15, 1.3, 4)
    phases = rng.uniform(0, 2 * math.pi, 4)
    amps = np.array([0.22, 0.12, 0.07, 0.04])
    return 1.0 + float(np.sum(amps * np.sin(2 * math.pi * rates * t + phases)))


# ---------------------------------------------------------------------------------------------------- Blender

FEET = ("leftFoot", "rightFoot")
HANDS = ("leftHand", "rightHand")
_SPINE = ("hips", "spine", "chest", "upperChest", "neck", "head")


@dataclass
class _Limb:
    """An IK limb's keys: where its end goes (a spec: ("world", p), ("char", p), ("call", fn), ("object", ob)), its
    elbow's or knee's pole (character frame), its end's turn (a 3x3 in the character's frame, or None) and its weight."""
    keys: list = field(default_factory=list)      # (frame, target spec, pole, turn or None, ease)
    weight: Track = field(default_factory=lambda: Track("vec"))


class Performance:
    """What one VRM character does over a shot (see the module's doc). Keys are added in any order; `bake` writes
    them. Frames are film frames (Blender's), seconds where a name says so (`say`)."""

    def __init__(self, ch: vrm.Character, *, fps: float = 24.0, seed: int = 0):
        import bpy

        self.ch, self.fps, self.seed = ch, float(fps), int(seed)
        bpy.context.view_layer.update()
        arm = ch.armature
        self.order = [h for h in self._order()]
        self.parents = {}
        for h in self.order:
            b = arm.data.bones[ch.bones[h]].parent
            while b is not None and b.name not in ch.bones.values():
                b = b.parent
            self.parents[h] = next((k for k, v in ch.bones.items() if b is not None and v == b.name), None)
        self.rest_heads = {h: ch.rest(h) for h in self.order}
        # the pose the builder left, as turns: what a bone no key names holds
        self.base = {h: self._turn_now(h) for h in self.order}
        pb = ch.bone("hips")
        rest = np.array(arm.data.bones[pb.name].matrix_local.to_3x3())
        self.base_hips = ch.frame.T @ rest @ np.array(pb.location) * ch.scale
        self.rot: dict[str, Track] = {}
        self.hips = Track("vec")
        self.root_pos, self.root_yaw = Track("vec"), Track("vec")
        self.root0 = (np.array(ch.root.location, float), math.degrees(ch.root.rotation_euler.z))
        self.layers: list = []           # fn(frame) -> ({bone: 3x3 added}, hips offset added)
        self.limbs: dict[str, _Limb] = {}
        self.look_keys: list = []        # (frame, spec or None, ease, weight)
        self.look_lag = 1.0
        self.expr: dict[str, Track] = {}
        self.blink = None
        self.lines: list = []            # (start s, end s, text, energy, quiet patterns, seed)
        self.props: list = []            # [ob, [(frame, holder)]]
        self.sec = None
        self.walks: list = []
        self._air: dict = {}             # foot -> frames it is in the air (no weight on it)
        self.shifts = Track("vec")       # (side shift, tilt) of the weight
        self.settles: list = []
        self.breath = None
        # where the feet stand now, in the character's frame (evaluated: the builder's IK included)
        self.feet_now = {}
        for foot in FEET:
            if ch.has(foot):
                self.feet_now[foot] = self._char_of_world(np.array(ch.point(foot)))
        self.legs = {}
        for side in ("left", "right"):
            if all(ch.has(f"{side}{b}") for b in ("UpperLeg", "LowerLeg", "Foot")):
                thigh = np.linalg.norm(ch.rest(f"{side}LowerLeg") - ch.rest(f"{side}UpperLeg"))
                shin = np.linalg.norm(ch.rest(f"{side}Foot") - ch.rest(f"{side}LowerLeg"))
                self.legs[side] = (float(thigh), float(shin))

    # ---- the rig

    def _order(self):
        """The humanoid bones, parents before children."""
        arm, names = self.ch.armature, set(self.ch.bones.values())
        by_name = {v: k for k, v in self.ch.bones.items()}
        out = []

        def walk(b):
            if b.name in names:
                out.append(by_name[b.name])
            for c in b.children:
                walk(c)
        for b in arm.data.bones:
            if b.parent is None:
                walk(b)
        return out

    def _turn_now(self, h: str) -> np.ndarray:
        """A bone's pose now as a turn (vrm.py's convention, a 3x3): F^T rest local rest^T F."""
        bn = self.ch.bones[h]
        pb = self.ch.armature.pose.bones[bn]
        rest = np.array(self.ch.armature.data.bones[bn].matrix_local.to_3x3())
        if pb.rotation_mode == "QUATERNION":
            local = matrix(tuple(pb.rotation_quaternion))
        else:
            local = np.array(pb.matrix_basis.to_3x3().normalized())
        f = self.ch.frame
        return f.T @ rest @ local @ rest.T @ f

    def _char_of_world(self, p) -> np.ndarray:
        """A world point in the character's frame as its root stands now."""
        m = np.array(self.ch.armature.matrix_world)
        local = np.linalg.inv(m) @ np.append(np.asarray(p, float), 1.0)
        return self.ch.frame.T @ local[:3] * self.ch.scale

    def scale_len(self, metres_for_170: float) -> float:
        """A length given for a 1.7 m person, for this one."""
        return metres_for_170 * self.height / 1.7

    @property
    def height(self) -> float:
        return float(self.rest_heads["head"][2] / 0.86) if "head" in self.rest_heads else 1.7

    # ---- keyed poses

    def pose(self, frame: float, rotations: dict, *, hips=None, ease: str = "inout", full: bool = True) -> None:
        """Key a pose at `frame`, arriving by `ease`: {humanoid bone: (x, y, z) degrees or a 3x3} (vrm.pose's turns).
        `full` keys every humanoid bone (one it does not name back at rest, an IK's elbow or knee at its fold) and the
        hips (at `hips`, else where they rest); not `full`, only the bones named (an arm, the head) and the hips if
        `hips` is given: a partial pose over what is keyed already."""
        turns = {vrm.canonical(k): v for k, v in rotations.items()}
        for h in self.order:
            if h in turns:
                self._track(h).key(frame, turns[h], ease)
            elif full:
                self._track(h).key(frame, self.ch.bends.get(h, (0.0, 0.0, 0.0)), ease)
        if hips is not None or full:
            self.hips.key(frame, hips if hips is not None else (0.0, 0.0, 0.0), ease)

    def _track(self, h: str) -> Track:
        if h not in self.rot:
            self.rot[h] = Track("rot")
        return self.rot[h]

    def hold(self, frame: float, bones=None) -> None:
        """Key every keyed bone (or those in `bones`) and the hips as they are at `frame`: what was there holds until
        then, the next key moves on from it (a held breath before an action)."""
        names = [vrm.canonical(b) for b in bones] if bones else list(self.rot)
        for h in names:
            if h in self.rot and self.rot[h]:
                self.rot[h].key(frame, self.rot[h].at(frame), "linear")
        if self.hips and not bones:
            self.hips.key(frame, self.hips.at(frame), "linear")

    def root(self, frame: float, at, *, yaw: float | None = None, ease: str = "inout") -> None:
        """Key the root (the character's feet in the world, metres) and its heading (degrees: 0 faces +x, 90 +y)."""
        at = np.asarray(at, float)
        if at.shape == (2,):
            at = np.append(at, self.root0[0][2])
        self.root_pos.key(frame, at, ease)
        prev = self.root_yaw.at(frame)[0] if self.root_yaw else self.root0[1]
        self.root_yaw.key(frame, [unwrap(prev, yaw) if yaw is not None else prev], ease)

    def root_at(self, frame: float) -> tuple[np.ndarray, float]:
        pos = self.root_pos.at(frame) if self.root_pos else self.root0[0]
        yaw = float(self.root_yaw.at(frame)[0]) if self.root_yaw else self.root0[1]
        return np.asarray(pos, float), yaw

    # ---- the body at a frame (no IK, no look): turns and hips

    def body(self, frame: float) -> tuple[dict, np.ndarray]:
        """({bone: turn 3x3}, hips offset) at `frame` from the keys and the layers (look-at and IK not included)."""
        turns = {}
        for h in self.order:
            tr = self.rot.get(h)
            turns[h] = tr.at(frame) if tr else self.base[h]
        hips = np.array(self.hips.at(frame) if self.hips else self.base_hips, float)
        for layer in self.layers:
            add, dh = layer(frame)
            for h, m in add.items():
                if h in turns:
                    turns[h] = m @ turns[h]
            hips = hips + dh
        return turns, hips

    def fk(self, frame: float, turns=None, hips=None) -> tuple[dict, dict]:
        """The body's total turns and heads in the character's frame at `frame` (FK; no IK)."""
        if turns is None:
            turns, hips = self.body(frame)
        return fk(self.order, self.parents, self.rest_heads, turns, hips_offset=hips)

    def face_at(self, frame: float) -> np.ndarray:
        """Between the eyes in the world at `frame` (a look-at target for another character)."""
        _, heads = self.fk(frame)
        if "leftEye" in heads and "rightEye" in heads:
            p = (heads["leftEye"] + heads["rightEye"]) / 2
        else:
            p = heads["head"] + np.array([0.0, -0.05, 0.08]) * self.height / 1.7
        root, yaw = self.root_at(frame)
        return to_world(p, root, yaw)

    def point_at(self, frame: float, bone: str) -> np.ndarray:
        """A humanoid bone's head in the world at `frame` (FK of the keys: an IK'd limb's end is its target)."""
        _, heads = self.fk(frame)
        root, yaw = self.root_at(frame)
        return to_world(heads[vrm.canonical(bone)], root, yaw)

    # ---- acting layers

    def breathe(self, *, rate: float = 0.25, depth: float = 1.0, start: float | None = None) -> None:
        """A breathing idle under everything: the chest and upper chest rising (a little back) and the shoulders up a
        touch, `rate` breaths a second, `depth` 1 calm (2 after exertion)."""
        ph = np.random.default_rng(self.seed + 11).uniform(0, 2 * math.pi)

        def layer(f):
            t = f / self.fps
            # in quicker than out: a breath's shape
            u = (rate * t + ph / (2 * math.pi)) % 1.0
            b = smoothstep(0.0, 0.42, u) if u < 0.42 else 1.0 - smoothstep(0.42, 1.0, u)
            a = depth * b
            return ({"chest": vrm.euler((-0.9 * a, 0, 0)), "upperChest": vrm.euler((-1.1 * a, 0, 0)),
                     "neck": vrm.euler((1.4 * a, 0, 0)),
                     "leftShoulder": vrm.euler((0, -1.2 * a, 0)), "rightShoulder": vrm.euler((0, 1.2 * a, 0))},
                    np.array([0.0, 0.0, 0.002 * a]))
        self.layers.append(layer)

    def shift(self, frame: float, side: str = "left", *, amount: float = 1.0, over: float = 0.6,
              ease_: str = "inout") -> None:
        """Shift the weight onto one foot ("left", "right", or "center") by `frame`, over `over` seconds: the hips
        slide over it and tip (the other hip drops), the chest leans back against it. Plants the feet if nothing else
        does (`plant_feet`)."""
        s = {"left": 1.0, "right": -1.0, "center": 0.0}[side] * amount
        f0 = frame - over * self.fps
        prev = self.shifts.at(f0) if self.shifts else np.zeros(2)
        self.shifts.key(f0, prev, "linear")
        self.shifts.key(frame, [s, s], ease_)
        if len(self.layers) == 0 or self._shift_layer not in self.layers:
            self.layers.append(self._shift_layer)
        self._want_feet = True

    def _shift_layer(self, f):
        if not self.shifts:
            return {}, np.zeros(3)
        s, tilt = self.shifts.at(f)
        k = self.height / 1.7
        return ({"hips": vrm.euler((0.0, -3.5 * tilt, 2.0 * tilt)), "spine": vrm.euler((0.0, 2.0 * tilt, -1.0 * tilt)),
                 "chest": vrm.euler((0.0, 1.8 * tilt, 0.0)), "neck": vrm.euler((0.0, -0.6 * tilt, 0.0))},
                np.array([0.045 * k * s, 0.0, -0.008 * k * abs(s)]))

    def settle(self, frame: float, amount: float = 1.0, *, time: float = 0.45) -> None:
        """A small settle after a big move lands at `frame`: the hips dip and come back, the spine and head nod with
        it, a little wobble out."""
        def layer(f, f0=frame):
            t = (f - f0) / self.fps
            if t < 0 or t > time * 2.5:
                return {}, np.zeros(3)
            w = amount * math.exp(-t / (time * 0.45)) * math.sin(math.pi * min(1.0, t / time) + 0.0) \
                if t < time else amount * 0.18 * math.exp(-(t - time) / (time * 0.4)) * -math.sin(2 * math.pi * (t - time) / time)
            k = self.height / 1.7
            return ({"spine": vrm.euler((2.5 * w, 0, 0)), "chest": vrm.euler((1.5 * w, 0, 0)),
                     "neck": vrm.euler((-1.5 * w, 0, 0)), "head": vrm.euler((2.0 * w, 0, 0))},
                    np.array([0.0, 0.0, -0.025 * k * w]))
        self.layers.append(layer)

    # ---- looking

    def look(self, frame: float, target, *, ease: str = "inout", weight: float = 1.0, lag: float | None = None) -> None:
        """From `frame` (arriving by `ease` from the look before, over the frames between) look at `target`: a world
        point, an object (its origin, as animated), a function of the frame giving a world point (another
        Performance's face_at), or None to let go (back to the keyed pose). The eyes get there first, the head
        after, the neck and the spine last (`lag` scales how slow: 1 natural, 2 heavy, 0.5 quick)."""
        spec = None if target is None else _spec(target)
        self.look_keys.append((float(frame), spec, ease, 0.0 if target is None else float(weight)))
        self.look_keys.sort(key=lambda k: k[0])
        if lag is not None:
            self.look_lag = float(lag)

    # ---- the face

    def express(self, frame: float, weights: dict, *, ease: str = "inout", full: bool = False) -> None:
        """Key expressions at `frame` ({name: weight}: the VRM's or vrm_rig.compose's), arriving by `ease`. `full`
        keys every expression keyed so far that `weights` does not name back to 0."""
        unknown = sorted(set(weights) - set(self.ch.expressions))
        if unknown:
            raise KeyError(f"{self.ch.name}: no expression {', '.join(unknown)}")
        for name, w in weights.items():
            self.expr.setdefault(name, Track("vec")).key(frame, [float(w)], ease)
        if full:
            for name, tr in self.expr.items():
                if name not in weights:
                    tr.key(frame, [0.0], ease)

    def blinks(self, *, seed: int | None = None, mean: float = 3.6, on_turns: float = 25.0, expression: str = "blink",
               quiet=("Fcl_EYE_*",)) -> None:
        """Natural blinks over the shot (blink_times: seeded), and one when the look swings `on_turns` degrees or
        more. While the lids close, the shape keys matching `quiet` (a narrowed glare's own eye shapes) ease off so
        the two do not fold the lids twice."""
        if expression not in self.ch.expressions:
            raise KeyError(f"{self.ch.name}: no expression {expression!r} to blink with")
        self.blink = dict(seed=self.seed + 7 if seed is None else seed, mean=mean, on_turns=on_turns,
                          expression=expression, quiet=tuple(quiet), extra=[])

    def blink_at(self, frame: float) -> None:
        """A blink starting at `frame` (on a cut of the eyes, an impact)."""
        if self.blink is None:
            self.blinks(mean=1e9)
        self.blink["extra"].append(frame / self.fps)

    def say(self, start: float, end: float, text: str, *, energy: float = 1.0, quiet=("Fcl_MTH_Close", "*press*"),
            seed: int | None = None) -> None:
        """Lip-sync a line said from `start` to `end` (film seconds: data/dialogue_timing.json's) reading `text`
        (romaji or kana; `visemes`). `energy` scales how wide the mouth opens (0.6 muttered, 1.3 shouted). The shape
        keys matching `quiet` (a set face's closed mouth) ease off while it speaks."""
        for v in VOWELS.values():
            if v not in self.ch.expressions:
                raise KeyError(f"{self.ch.name}: no viseme expression {v!r} to speak with")
        self.lines.append((float(start), float(end), text, float(energy), tuple(quiet),
                           self.seed + 31 * len(self.lines) if seed is None else seed))

    # ---- IK: hands and feet over time

    def reach(self, frame: float, end: str, target, *, pole=None, turn=None, ease: str = "inout",
              weight: float = 1.0) -> None:
        """From `frame` (arriving by `ease`) the hand or foot `end` reaches `target` (its wrist or ankle): a world
        point, ("char", point) in the character's frame, an object, or a function of the frame giving a world point;
        its elbow or knee toward `pole` (character frame; a natural one by default), the hand or foot turned by `turn`
        (degrees about the character's axes or a 3x3, from rest; None leaves it to the arm). `weight` 0 lets go: the
        limb back to its keyed pose."""
        h = vrm.canonical(end)
        if h not in HANDS + FEET:
            raise ValueError(f"{h} is not a hand or a foot")
        limb = self.limbs.setdefault(h, _Limb())
        limb.keys.append((float(frame), _spec(target), None if pole is None else np.asarray(pole, float),
                          None if turn is None else turn_matrix(turn), ease))
        limb.keys.sort(key=lambda k: k[0])
        limb.weight.key(frame, [float(weight)], ease)

    def grasp(self, frame: float, side: str, point, along, palm, *, pole=None, ease: str = "inout", amount: float = 1.0,
              thumb: float = 0.6, depth: float = 0.028) -> None:
        """From `frame` the `side` hand closes round a grip running along `along` through `point` (vrm.grasp; all in
        the character's frame; `point` may be a spec as `reach` takes, along and palm stay in the character's
        frame): the wrist reaches, the hand turns, the fingers curl (keyed with it)."""
        k0, p0, r0 = vrm.hand_rest(self.ch, side)
        t = vrm.align(k0, p0, -np.asarray(along, float), palm)
        hole = r0 * 0.85 + p0 * depth
        spec = _spec(("char", point) if not callable(point) and np.shape(point) == (3,) else point)
        self.reach(frame, f"{side}Hand", _Offset(spec, -t @ hole), pole=pole, turn=t, ease=ease)
        self.pose(frame, vrm.grip_pose(side, amount, thumb), ease=ease, full=False)

    def plant(self, frame: float, foot: str, at=None, *, yaw: float = 0.0, ease: str = "inout", pole=None,
              ground=None) -> None:
        """Plant a foot from `frame`: its ankle at `at` (world; default where it stands now, `feet_now`), turned `yaw`
        degrees from the character's heading (as it stands at `frame`), flat. With `ground` (`walk`'s) the ankle is
        set on the ground under it, as high above it as it stands."""
        h = vrm.canonical(foot)
        root, ry = self.root_at(frame)
        if at is None:
            at = to_world(self.feet_now[h], root, ry)
        if ground is not None:
            at = np.array(at, float)
            at[2] = ground_of(ground)(at[0], at[1]) + self.feet_now.get(h, np.array([0, 0, 0.08]))[2]
        self.reach(frame, h, at, turn=vrm.euler((0.0, 0.0, yaw)), ease=ease, pole=pole)

    def plant_feet(self, frame: float | None = None) -> None:
        """Both feet planted where they stand at `frame` (the first keyed root's frame by default): moving the hips
        (a weight shift, a settle, a crouch) bends the knees and leaves the feet where they are."""
        f = frame if frame is not None else (self.root_pos.keys[0].frame if self.root_pos else 0.0)
        for foot in FEET:
            if foot in self.feet_now and foot not in self.limbs:
                self.plant(f, foot, yaw=self._foot_yaw(foot))

    def _foot_yaw(self, foot: str) -> float:
        """How far the foot is turned out now (degrees, character frame), from its toes."""
        ch = self.ch
        toes = f"{foot[:-4]}Toes"
        if not ch.has(toes):
            return 0.0
        d = self._char_of_world(np.array(ch.point(toes))) - self.feet_now[foot]
        rest = ch.rest(toes) - ch.rest(foot)
        return heading((-d[1], d[0])) - heading((-rest[1], rest[0]))

    # ---- walking, running, kneeling

    def walk(self, path, start: float, *, gait="walk", lead: str = "right", pose: dict | None = None,
             end_pose: dict | None = None, end_yaw: float | None = None, speed: float | None = None,
             swing=(1.0, 1.0), ground=None) -> int:
        """Walk (or run: `gait`) along `path` (world x, y points; it starts where the character stands, the first
        point moved there) from frame `start`, at the gait's speed (or `speed` m/s), the `lead` foot first, into
        `end_pose` (a pose, default `pose`, default STAND) facing `end_yaw` (default the path's last heading). `pose`
        is the body's carriage while it walks (keyed as it sets off; both are partial keys: a bone they do not name
        keeps its keys, a hand closed on a pole stays closed); `swing` scales each arm's swing (left, right):
        0 for an arm that holds something. `ground` is the ground's height: a number, a function of world (x, y), or
        an object to cast down onto (`ground_of`), default the height it stands at: each footfall lands on the ground
        under it, the body rides over it (eased over a stride). Returns the frame it stands still on."""
        g = gait_of(gait).scaled(self.height)
        if speed is not None:
            g = g.but(speed=float(speed))
        root0, yaw0 = self.root_at(start)
        pts = np.asarray(path, float)[:, :2]
        if np.linalg.norm(pts[0] - root0[:2]) > 0.05:
            pts = np.vstack([root0[:2], pts])
        else:
            pts[0] = root0[:2]
        pth = Path(pts)
        gz = ground_of(root0[2] if ground is None else ground)

        def body_z(s_):
            # the ground under the body, eased over a stride (it does not ride every bump)
            return float(np.mean([gz(*pth.at(s_ + d)) for d in np.linspace(-0.5, 0.5, 5) * g.stride]))
        steps, kt, kd = plan_steps(pth.length, g, lead=lead)
        fps = self.fps
        t_end = float(kt[-1])
        end = int(math.ceil(start + t_end * fps))
        yaw_end = pth.yaw(pth.length) if end_yaw is None else end_yaw
        first_land = steps[0].t1 if steps else 0.0
        close0 = steps[-1].t0 if steps else 0.0

        def body_s(t):
            return float(pchip(kt, kd, [t])[0])

        def yaw_at(t):
            s = body_s(t)
            y = pth.yaw(min(s + 0.2, pth.length)) if pth.length > 0.25 else yaw0
            y = unwrap(yaw0, y)
            y = yaw0 + (y - yaw0) * smoothstep(0.0, max(first_land, 0.3), t)
            ye = unwrap(y, yaw_end)
            return y + (ye - y) * smoothstep(close0, t_end, t)

        # the feet: where each stands at the start (as it stands now) and each landing on the path
        feet0 = {}
        for foot in FEET:
            side = foot[:-4]
            if foot in self.limbs and self.limbs[foot].keys:
                feet0[side] = self._resolve(self.limbs[foot].keys[-1][1], start)
            else:
                feet0[side] = to_world(self.feet_now.get(foot, np.array([0.1 if side == "left" else -0.1, 0, 0.08])),
                                       root0, yaw0)
        ankle = {s: (self.feet_now.get(f"{s}Foot", np.array([0, 0, 0.08 * self.height / 1.7]))[2]) for s in ("left", "right")}

        def plant_at(side, d, final=False):
            c = pth.at(d)
            tan = pth.tangent(d)
            left = np.array([-tan[1], tan[0]])
            sgn = 1.0 if side == "left" else -1.0
            y = heading(tan) if not final else yaw_end
            if final:
                left = np.array([-math.sin(math.radians(y)), math.cos(math.radians(y))])
            p = c + left * sgn * g.width / 2
            return np.array([p[0], p[1], gz(p[0], p[1]) + ankle[side]]), y + sgn * g.toe_out

        # the foot's geometry for its roll: ball and heel from the ankle, along the foot and up
        k = self.height / 1.7
        ball, heel, ah = 0.13 * k, 0.05 * k, float(np.mean(list(ankle.values())))
        if self.ch.has("leftToes"):
            d = self.ch.rest("leftToes") - self.ch.rest("leftFoot")
            ball = float(np.hypot(d[0], d[1]))

        def foot_at(side, t):
            """(ankle world, foot yaw world, pitch toes-down, toe bend) at t seconds into the walk."""
            mine = [st for st in steps if st.side == side]
            pos = feet0[side]
            yaw = self._foot_world_yaw(side, start, yaw0)
            last_land, t_lift_next = -math.inf, math.inf
            for i, st in enumerate(mine):
                final = st is steps[-1]
                b_pos, b_yaw = plant_at(side, st.b, final=final)
                if t < st.t0:
                    t_lift_next = st.t0
                    break
                if t < st.t1:
                    u = (t - st.t0) / (st.t1 - st.t0)
                    if u > 0:
                        self._air.setdefault(f"{side}Foot", set()).add(round(start + t * fps, 3))
                    return self._swing(pos, yaw, b_pos, b_yaw, u, g, ball, heel, ah, final, gz)
                pos, yaw, last_land = b_pos, b_yaw, st.t1
            pitch = 0.0
            # heel off before it lifts (about the ball), heel strike settling after it lands (about the heel)
            roll_t = min(0.18, 0.35 * g.stride / g.speed)
            if t_lift_next - t < roll_t and g.roll > 0:
                pitch = g.roll * (1.0 - (t_lift_next - t) / roll_t) ** 1.5
                return _pivot(pos, yaw, pitch, ball, ah), yaw, pitch, -pitch
            if t - last_land < 0.09 and g.roll > 0:
                pitch = -0.5 * g.roll * (1.0 - (t - last_land) / 0.09)
                return _pivot(pos, yaw, pitch, -heel, ah), yaw, pitch, 0.0
            return pos, yaw, 0.0, 0.0

        def env(t):
            return smoothstep(0.0, max(first_land, 0.2), t) * (1.0 - smoothstep(close0, t_end, t))

        f_start = int(math.floor(start))
        for f in range(f_start, end + 1):
            t = (f - start) / fps
            s = body_s(t)
            c = pth.at(s)
            y = yaw_at(t)
            self.root_pos.key(f, [c[0], c[1], body_z(s)], "linear")
            self.root_yaw.key(f, [y], "linear")
            for side in ("left", "right"):
                p, fy, pitch, toe = foot_at(side, t)
                self.limbs.setdefault(f"{side}Foot", _Limb())
                lm = self.limbs[f"{side}Foot"]
                lm.keys = [kk for kk in lm.keys if abs(kk[0] - f) > 1e-6]
                lm.keys.append((float(f), ("world", p), None, ("yaw", fy, pitch), "linear"))
                lm.weight.key(f, [1.0], "linear")
        for foot in FEET:
            if foot in self.limbs:
                self.limbs[foot].keys.sort(key=lambda kk: kk[0])

        carriage = pose if pose is not None else STAND
        settle_f = start + min(0.4, max(first_land, 0.2)) * fps
        # partial keys: a bone neither names (a hand closed on a pole) keeps what it had
        self.pose(settle_f, carriage, hips=(0.0, 0.0, 0.0), ease="inout", full=False)
        self.pose(end, end_pose if end_pose is not None else carriage, hips=(0.0, 0.0, 0.0), ease="inout", full=False)

        def layer(f):
            t = (f - start) / fps
            if t < -0.05 or t > t_end + 0.05:
                return {}, np.zeros(3)
            e = env(t)
            # how far ahead each foot is of the other, a share of a stride (+ right ahead)
            root, ry = self.root_at(f)
            fwd = np.array([math.cos(math.radians(ry)), math.sin(math.radians(ry)), 0.0])
            pr, pl = foot_at("right", t)[0], foot_at("left", t)[0]
            lead_r = float(np.dot(pr - pl, fwd)) / max(g.stride, 1e-3)
            lead_r = max(-1.2, min(1.2, lead_r))
            # the body over the foot bearing weight; up at mid-stance (a walk), down (a run)
            bob, stance = 0.0, 0.0
            for st in steps:
                if st.t0 <= t < st.t1:
                    u = (t - st.t0) / (st.t1 - st.t0)
                    lift = math.sin(math.pi * u)
                    bob = max(bob, lift)
                    stance += (-1.0 if st.side == "left" else 1.0) * lift   # toward the other foot
            plod = 0.0
            if g.plod:
                for st in steps:
                    dt = t - st.t1
                    if 0 <= dt < 0.4:
                        plod = max(plod, math.sin(math.pi * min(1.0, dt / 0.25)) * math.exp(-dt / 0.15))
            hip = -g.hip_turn * lead_r * e
            shoulders = -g.chest_turn * hip * 0.5
            per = (shoulders - hip) / 2
            arm = g.arm * lead_r * e
            lean = g.lean * e
            dz = (-g.drop + g.bob * bob - g.plod * plod) * e if g.bob >= 0 else (-g.drop + g.bob * bob - g.plod * plod) * e
            dx = g.sway * max(-1.0, min(1.0, stance)) * e
            out = {
                "hips": vrm.euler((0.0, 0.0, hip)),
                "spine": vrm.euler((lean * 0.45, 0.0, per)),
                "chest": vrm.euler((lean * 0.35, 0.0, per)),
                "upperChest": vrm.euler((lean * 0.2, 0.0, 0.0)),
                "neck": vrm.euler((-lean * 0.5 * g.head, 0.0, -shoulders * 0.5 * g.head)),
                "head": vrm.euler((-lean * 0.5 * g.head + (g.bob * bob * 40.0) * g.head * e, 0.0,
                                   -shoulders * 0.5 * g.head)),
                "leftUpperArm": vrm.euler((-arm * swing[0], 0.0, 0.0)),
                "rightUpperArm": vrm.euler((arm * swing[1], 0.0, 0.0)),
                "leftLowerArm": vrm.euler((0.0, 0.0, -(g.elbow + max(0.0, lead_r) * g.elbow * 0.6) * e * swing[0])),
                "rightLowerArm": vrm.euler((0.0, 0.0, (g.elbow + max(0.0, -lead_r) * g.elbow * 0.6) * e * swing[1])),
            }
            for side in ("left", "right"):
                toe = foot_at(side, t)[3]
                if toe:
                    out[f"{side}Toes"] = vrm.euler((toe, 0.0, 0.0))
            return out, np.array([dx, 0.0, dz])

        self.layers.append(layer)
        self.walks.append((start, end))
        return end

    def _foot_world_yaw(self, side: str, frame: float, root_yaw: float) -> float:
        foot = f"{side}Foot"
        lm = self.limbs.get(foot)
        if lm and lm.keys and isinstance(lm.keys[-1][3], tuple):
            return lm.keys[-1][3][1]
        return root_yaw + self._foot_yaw(foot) if foot in self.feet_now else root_yaw

    def _swing(self, a, ya, b, yb, u, g: Gait, ball, heel, ah, final, gz=None):
        """A foot in the air u (0..1) of the way from ankle a (heading ya) to b (yb): off its toes, forward low and
        clear of the ground, landing heel first (a closing step sets down flatter)."""
        roll = g.roll * (0.4 if final else 1.0)
        p0 = _pivot(a, ya, roll, ball, ah)
        p1 = _pivot(b, yb, -0.5 * roll, -heel, ah)
        k = ease(u, "inout")
        p = p0 + (p1 - p0) * k
        lift = g.lift * (0.6 if final else 1.0)
        if gz is not None:          # clear of a rise in the ground between the footfalls
            p[2] = max(p[2], gz(p[0], p[1]) + ah * min(1.0, 4 * u, 4 * (1 - u)))
        p = p + np.array([0.0, 0.0, lift * math.sin(math.pi * u) ** 1.2 * (1.0 - 0.3 * u)])
        y = ya + (unwrap(ya, yb) - ya) * k
        pitch = roll + (-0.5 * roll - roll) * smoothstep(0.0, 0.85, u)
        return p, y, pitch, -roll * max(0.0, 1.0 - u / 0.3)

    def kneel(self, start: float, end: float, *, side: str = "right", bow: float = 0.0, ease_: str = "inout") -> None:
        """Get down onto the `side` knee from `start` to `end`: that foot steps back onto its toes, the hips sink, the
        knee comes to the ground below them, the other foot planted ahead with its shin upright. `bow` (degrees) bows
        the back and head as it lands. Hold it with `hold`, get up with `stand`."""
        self.plant_feet(start)
        root, yaw = self.root_at(start)
        other = "left" if side == "right" else "right"
        thigh, shin = self.legs[side]
        k = self.height / 1.7
        front = self._limb_char(f"{other}Foot", start, root, yaw)
        hip_j = {s: self.rest_heads[f"{s}UpperLeg"] for s in ("left", "right")}
        hip_mid = (hip_j["left"] + hip_j["right"]) / 2
        ah = float(front[2])
        # the hips a thigh behind the front foot, as high as its knee (its shin upright)
        hip_y = front[1] + thigh * 0.9
        hip_z = min(ah + shin * 0.97, 0.06 * k + thigh * 0.97)
        knee_y = hip_y + 0.04 * k
        back = np.array([hip_j[side][0], knee_y + shin * 0.92, 0.09 * k])
        mid = np.array([back[0], front[1] + 0.5 * (back[1] - front[1]), ah + 0.07 * k])
        self._limb_keys(f"{side}Foot", [(start, None), (start + 0.4 * (end - start), mid), (end, back)], root, yaw,
                        turns=[(0, 0, 0), (25, 0, 0), (62, 0, 0)], pole=(hip_j[side][0], -0.6 * k, 0.1 * k),
                        ease=ease_)
        self.reach(end, f"{other}Foot", to_world(front, root, yaw), turn=(0, 0, 0), ease=ease_,
                   pole=(hip_j[other][0] * 1.5, front[1] - 0.6 * k, 0.6 * k))
        drop = np.array([0.0, hip_y - hip_mid[1], hip_z - hip_mid[2]])
        h0 = self.hips.at(start) if self.hips else self.base_hips
        self.hips.key(start, h0, "linear")
        self.hips.key(start + 0.35 * (end - start), h0 + drop * 0.25, ease_)
        self.hips.key(end, drop, "out")
        self.pose(end, {"spine": (6.0 + bow * 0.4, 0, 0), "chest": (bow * 0.3, 0, 0), "neck": (bow * 0.15, 0, 0),
                        "head": (bow * 0.3, 0, 0), f"{side}Toes": (-55.0, 0, 0)}, ease=ease_, full=False)
        self._kneel = dict(side=side, front=front, root=root, yaw=yaw)

    def stand(self, start: float, end: float, *, ease_: str = "inout", pose: dict | None = None) -> None:
        """Get up from `kneel` between `start` and `end`: the weight forward onto the front foot, the hips rise, the
        back foot comes up alongside it. Into `pose` (default STAND)."""
        kn = getattr(self, "_kneel", None)
        if kn is None:
            raise RuntimeError("stand() follows a kneel()")
        side, front, root, yaw = kn["side"], kn["front"], kn["root"], kn["yaw"]
        k = self.height / 1.7
        hip_x = self.rest_heads[f"{side}UpperLeg"][0]
        beside = np.array([hip_x, front[1], front[2]])
        mid = np.array([hip_x, front[1] + 0.25 * k, front[2] + 0.08 * k])
        self._limb_keys(f"{side}Foot", [(start, None), (start + 0.55 * (end - start), mid), (end, beside)], root, yaw,
                        turns=[None, (20, 0, 0), (0, 0, 0)], pole=(hip_x, -0.6 * k, 0.5 * k), ease=ease_)
        self.hips.key(start, self.hips.at(start), "linear")
        self.hips.key(start + 0.5 * (end - start), self.hips.at(start) * 0.45 + np.array([0, -0.05 * k, 0]), ease_)
        # standing over the feet where they now are (the front one stayed put)
        over = front[1] - float(np.mean([v[1] for v in self.feet_now.values()]))
        self.pose(end, pose if pose is not None else STAND, hips=(0.0, over, 0.0), ease="out")

    def _limb_char(self, end: str, frame: float, root, yaw) -> np.ndarray:
        lm = self.limbs.get(end)
        if lm and lm.keys:
            return to_char(self._limb_target(end, frame)[0], root, yaw)
        return self.feet_now[end].copy()

    def _limb_keys(self, end, keys, root, yaw, *, turns, pole, ease):
        for (f, p), t in zip(keys, turns):
            if p is None:
                p = self._limb_char(end, f, root, yaw)
                t = t if t is not None else (0, 0, 0)
            self.reach(f, end, to_world(p, root, yaw), turn=t, pole=pole, ease=ease)

    # ---- props

    def carry(self, ob, frame: float, holder) -> None:
        """From `frame` the prop `ob` (an object, or a list of them: a sword's parts) is carried by `holder`: a
        humanoid bone of this character ("rightHand"), ("bone", armature, bone name) for any armature's bone, any
        object, or None (left in the world where it is). It keeps its world transform at the handoff: a sword drawn
        from the sheath on the back to the right hand, a pipe from hand to mouth, a pole lifted from the boat to her
        shoulder. Before its first `carry` it follows what it was parented to, as the scene stands when `bake` starts."""
        import bpy

        for o in (ob if isinstance(ob, (list, tuple)) else [ob]):
            entry = next((p for p in self.props if p[0] is o), None)
            if entry is None:
                bpy.context.view_layer.update()
                if o.parent is not None and o.parent_type == "BONE" and o.parent.type == "ARMATURE":
                    first = ("bone", o.parent, o.parent_bone)
                else:
                    first = o.parent
                entry = [o, [(-math.inf, first)], _holder_matrix(first, self.ch), np.array(o.matrix_world)]
                self.props.append(entry)
            if isinstance(holder, str):
                holder = ("bone", self.ch.armature, self.ch.bones[vrm.canonical(holder)])
            entry[1].append((float(frame), holder))
            entry[1].sort(key=lambda h: h[0])

    # ---- secondary motion

    def secondary(self, *, pattern: str = "J_Sec_*", wind=(0.0, 0.0, 0.0), gravity: float = 2.0,
                  stiffness: float = 9.0, drag: float = 0.1, chains=None, settings: dict | None = None,
                  seed: int | None = None, substeps: int = 4) -> None:
        """Simulate the loose chains of bones (VRoid's J_Sec_* hair, skirt, sleeves; or `chains`: lists of bone
        names, root first) after the body is baked: each carried by its parent and lagging it (`stiffness`: how hard it
        is pulled back to where it hangs at rest, per second; `drag` 0..1 a step), sagging under `gravity` (m/s^2,
        on top of how it hangs) and blown by `wind` (m/s^2, world, gusting: `gust`). `settings` {fnmatch pattern of a
        chain's root bone: {stiffness, drag, gravity, wind_scale}} tunes some chains (a heavy straw cape stiff, a
        headband's tails loose)."""
        dangles = self.sec["dangles"] if self.sec else []
        self.sec = dict(pattern=pattern, wind=np.asarray(wind, float), gravity=float(gravity), stiffness=stiffness,
                        drag=drag, chains=chains, settings=settings or {},
                        seed=self.seed + 5 if seed is None else seed, substeps=int(substeps), dangles=dangles)

    def dangle(self, obs, pivot, *, toward=None, length: float = 0.25, stiffness: float = 7.0, drag: float = 0.08,
               wind_scale: float = 1.0) -> None:
        """Let props hang loose from `pivot` (a world point as they are now: a headband's knot, the straw cape's
        collar): they swing about it as one, lagging the bone that carries them and blown by `secondary`'s wind,
        pulled back to how they hang by `stiffness`. `toward` is the way they hang from the pivot (default down),
        `length` how far out their weight is. They are put under a pivot empty (keeping where they are) that the bake
        keys; call `secondary` too (its wind and gravity)."""
        import bpy

        obs = obs if isinstance(obs, (list, tuple)) else [obs]
        if self.sec is None:
            self.secondary(chains=[[]])
        bpy.context.view_layer.update()
        first = obs[0]
        e = bpy.data.objects.new(f"{first.name}-dangle", None)
        self.ch.coll.objects.link(e)
        e.empty_display_size = 0.03
        e.parent, e.parent_type, e.parent_bone = first.parent, first.parent_type, first.parent_bone
        from mathutils import Matrix

        bpy.context.view_layer.update()
        e.matrix_world = Matrix.Translation(tuple(float(c) for c in pivot))
        e.rotation_mode = "QUATERNION"
        bpy.context.view_layer.update()
        for o in obs:
            mw = o.matrix_world.copy()
            o.parent, o.parent_type = e, "OBJECT"
            o.matrix_world = mw
        hang = np.asarray(toward if toward is not None else (0.0, 0.0, -1.0), float)
        local = np.array(e.matrix_world.to_3x3().inverted()) @ hang
        self.sec["dangles"].append(dict(empty=e, base=np.array(tuple(e.rotation_quaternion)),
                                        local=local / np.linalg.norm(local), length=float(length),
                                        stiffness=stiffness, drag=drag, wind=wind_scale))


    # ---- baking

    def _resolve(self, spec, frame: float) -> np.ndarray:
        """A spec's world point at `frame`."""
        if isinstance(spec, _Offset):
            root, yaw = self.root_at(frame)
            return to_world(to_char(self._resolve(spec.spec, frame), root, yaw) + spec.offset, root, yaw)
        kind, v = spec
        if kind == "world":
            return v
        if kind == "char":
            root, yaw = self.root_at(frame)
            return to_world(v, root, yaw)
        if kind == "call":
            return np.asarray(v(frame), float)
        cache = self._objects.get(v.name)
        if cache is not None:
            f = int(round(frame))
            return cache.get(f, cache[min(cache, key=lambda g: abs(g - f))])
        return np.array(v.matrix_world.translation)

    def _limb_target(self, end: str, frame: float):
        """(world target, pole (char) or None, turn (char 3x3) or None, IK weight, turn weight) of a limb at `frame`."""
        lm = self.limbs[end]
        ks = lm.keys
        root, yaw = self.root_at(frame)

        def turn_of(key):
            t = key[3]
            if isinstance(t, tuple):            # a walk's foot: ("yaw", world heading, pitch)
                return vrm.euler((t[2], 0.0, t[1] - yaw))
            return t

        i = int(np.searchsorted([k[0] for k in ks], frame, side="right"))
        if i == 0 or i == len(ks):
            key = ks[0] if i == 0 else ks[-1]
            t = turn_of(key)
            return self._resolve(key[1], frame), key[2], t, float(lm.weight.at(frame)[0]), 1.0 if t is not None else 0.0
        a, b = ks[i - 1], ks[i]
        k = ease((frame - a[0]) / (b[0] - a[0]), b[4])
        pa, pb = to_char(self._resolve(a[1], frame), root, yaw), to_char(self._resolve(b[1], frame), root, yaw)
        p = to_world(pa + (pb - pa) * k, root, yaw)
        pole = None
        if a[2] is not None and b[2] is not None:
            pole = a[2] + (b[2] - a[2]) * k
        else:
            pole = b[2] if b[2] is not None else a[2]
        ta, tb = turn_of(a), turn_of(b)
        if ta is not None and tb is not None:
            turn, tw = matrix(slerp(quat(ta), quat(tb), k)), 1.0
        else:
            turn = ta if ta is not None else tb
            tw = (1.0 - k) if ta is not None else (k if tb is not None else 0.0)
        return p, pole, turn, float(lm.weight.at(frame)[0]), tw

    def _default_pole(self, end: str, target_char) -> np.ndarray:
        k = self.height / 1.7
        side = 1.0 if end.startswith("left") else -1.0
        if end in FEET:
            return np.array([target_char[0] * 1.2, target_char[1] - 0.6 * k, max(0.5 * k, target_char[2] + 0.4 * k)])
        sh = self.rest_heads.get(f"{end[:-4]}UpperArm", np.array([side * 0.18 * k, 0.0, 1.4 * k]))
        return np.array([side * (abs(sh[0]) + 0.3 * k), 0.45 * k, sh[2] - 0.35 * k])

    def bake(self, f0: int, f1: int) -> None:
        """Write the performance as keys on every frame of [f0, f1) (film frames): the bones, the hips, the root, the
        IK targets and weights, the face, then the props' handoffs and the secondary chains (which read the baked
        body back frame by frame)."""
        import bpy

        ch, arm, F, s = self.ch, self.ch.armature, self.ch.frame, self.ch.scale
        scene = bpy.context.scene
        keep = scene.frame_current
        frames = list(range(int(f0), int(f1)))
        if getattr(self, "_want_feet", False):
            self.plant_feet(f0)
        # each prop's place on its first holder as the scene stands now, before any key is written (a shot may move
        # or re-pose the character between carry() and bake())
        bpy.context.view_layer.update()
        for entry in self.props:
            entry[2], entry[3] = _holder_matrix(entry[1][0][1], ch), np.array(entry[0].matrix_world)
        # the add-on's own spring bones and look-at preview stay off: they would move bones on frame changes
        ext = arm.data.vrm_addon_extension
        ext.spring_bone1.enable_animation = False
        ext.vrm1.look_at.enable_preview = False
        # objects a look or a reach follows, where they are on each frame (the scene's own animation)
        objs = {}
        for lm in self.limbs.values():
            for kk in lm.keys:
                sp = kk[1].spec if isinstance(kk[1], _Offset) else kk[1]
                if sp[0] == "object":
                    objs[sp[1].name] = sp[1]
        for kk in self.look_keys:
            if kk[1] is not None and kk[1][0] == "object":
                objs[kk[1][1].name] = kk[1][1]
        self._objects = {n: {} for n in objs}
        if objs:
            # every third frame read from the scene, the frames between eased (stepping a scene with its cast in is slow)
            picks = sorted(set(frames[::3]) | {frames[-1]})
            for f in picks:
                scene.frame_set(f)
                for n, ob in objs.items():
                    self._objects[n][f] = np.array(ob.matrix_world.translation)
            for n in objs:
                got = self._objects[n]
                xs = sorted(got)
                arr = np.array([got[x] for x in xs])
                for f in frames:
                    got[f] = np.array([np.interp(f, xs, arr[:, i]) for i in range(3)])
        # the IK constraints and handles each limb needs
        cons = {}
        for end, lm in self.limbs.items():
            p0, pole0, t0, _, _ = self._limb_target(end, frames[0])
            root, yaw = self.root_at(frames[0])
            pc = to_char(p0, root, yaw)
            ik = vrm.reach(ch, end, pc, pole=pole0 if pole0 is not None else self._default_pole(end, pc))
            hold = vrm.hold(ch, end, t0 if t0 is not None else np.eye(3))
            cons[end] = (ik, hold)
            for h in ("leftLowerLeg", "rightLowerLeg", "leftLowerArm", "rightLowerArm"):
                if h in ch.bends and h in self.base and angle_between(self.base[h], np.eye(3)) < 1e-3:
                    self.base[h] = vrm.euler(ch.bends[h])
        rests = {h: np.array(arm.data.bones[ch.bones[h]].matrix_local.to_3x3()) for h in self.order}
        hips_rest = rests["hips"]

        # the face: every shape key an expression binds, and how it stands now
        bound = {}
        for name, binds in ch.expressions.items():
            for ob, key, w in binds:
                bound.setdefault((ob, key), ob.data.shape_keys.key_blocks[key].value)
        face = bool(self.expr or self.blink or self.lines)
        blinks = []
        if self.blink:
            extra = list(self.blink["extra"]) + self._look_blinks()
            blinks = blink_times(frames[0] / self.fps - 0.5, frames[-1] / self.fps + 0.5, seed=self.blink["seed"],
                                 mean=self.blink["mean"], extra=extra)
        speech = []
        for (a, b, text, energy, quiet, seed) in self.lines:
            vs = visemes(text, a, b, seed=seed, energy=energy)
            ts = np.array([v[0] for v in vs])
            speech.append((a, b, quiet, ts, {v: np.array([w.get(v, 0.0) for _, w in vs]) for v in VOWELS.values()}))

        out_q = {h: [] for h in self.order}
        out_hips, out_root, out_yaw = [], [], []
        out_limb = {end: dict(t=[], pole=[], q=[], w=[], tw=[]) for end in self.limbs}
        out_face = {kb: [] for kb in bound}
        look_state: dict = {}
        drops = []
        baked_turns = []
        for f in frames:
            root, yaw = self.root_at(f)
            turns, hips = self.body(f)
            self._look(f, turns, hips, root, yaw, look_state)
            limbs = {}
            heads = None
            for end in self.limbs:
                p, pole, turn, w, tw = self._limb_target(end, f)
                pc = to_char(p, root, yaw)
                limbs[end] = (pc, pole if pole is not None else self._default_pole(end, pc), turn, w, tw)
                # the elbow or knee no key turns starts folded as far as the target's distance needs (the IK solves
                # from there: from a straight limb it can settle with the joint on the target)
                lower = end.replace("Hand", "LowerArm").replace("Foot", "LowerLeg")
                upper = end.replace("Hand", "UpperArm").replace("Foot", "UpperLeg")
                if lower in turns and upper in self.rest_heads and lower not in self.rot and w > 0:
                    if heads is None:
                        heads = fk(self.order, self.parents, self.rest_heads, turns, hips_offset=hips)[1]
                    a = np.linalg.norm(self.rest_heads[lower] - self.rest_heads[upper])
                    b = np.linalg.norm(self.rest_heads[end] - self.rest_heads[lower])
                    bend = fold_for(a, b, np.linalg.norm(pc - heads[upper]))
                    folded = quat(vrm.euler(vrm.fold(lower, max(bend, 5.0))))
                    turns[lower] = matrix(slerp(quat(turns[lower]), folded, min(1.0, w)))
            # the hips no higher than both legs reach (a leg never pulled straight off its planted foot)
            dz = 0.0
            for side, (thigh, shin) in self.legs.items():
                lm = limbs.get(f"{side}Foot")
                if lm is None or lm[3] < 0.5 or round(float(f), 3) in self._air.get(f"{side}Foot", ()):
                    continue
                hip = self.rest_heads[f"{side}UpperLeg"] + hips
                d = lm[0] - hip
                reach_ = (thigh + shin) * 0.985
                hz = math.hypot(d[0], d[1])
                top = lm[0][2] + math.sqrt(max(0.0, reach_ ** 2 - min(hz, reach_ * 0.995) ** 2))
                dz = min(dz, top - hip[2])
            drops.append(dz)
            baked_turns.append(turns)
            for h in self.order:
                out_q[h].append(quat(vrm.local_rotation(rests[h], F, turns[h])))
            out_hips.append(hips)
            out_root.append(root)
            out_yaw.append(yaw)
            for end, (pc, pole, turn, w, tw) in limbs.items():
                o = out_limb[end]
                o["t"].append(F @ (pc / s))
                o["pole"].append(F @ (np.asarray(pole, float) / s))
                rest_end = rests[end]
                o["q"].append(quat(F @ (turn if turn is not None else np.eye(3)) @ F.T @ rest_end))
                o["w"].append(w)
                o["tw"].append(w * tw)
            if face:
                t = f / self.fps
                vals = self._face(t, bound, blinks, speech)
                for kb, v in vals.items():
                    out_face[kb].append(v)
        # the drop eased (never above what a leg reaches: the least of each neighbourhood, then softened)
        d = np.array(drops)
        if len(d) and d.min() < 0:
            lo = np.array([d[max(0, i - 3):i + 4].min() for i in range(len(d))])
            d = np.convolve(np.pad(lo, 2, mode="edge"), np.ones(5) / 5, mode="valid")
        hips_loc = [vrm.offset_local(hips_rest, F, (h + np.array([0.0, 0.0, dz])) / s) for h, dz in zip(out_hips, d)]
        # what the secondary pass reads back without stepping the scene through every frame
        self._baked = dict(frames=frames, turns=baked_turns, hips=[h + np.array([0.0, 0.0, dz]) for h, dz in zip(out_hips, d)],
                           root=out_root, yaw=out_yaw)

        w = _Writer(frames)
        for h in self.order:
            w.add(arm, f'pose.bones["{ch.bones[h]}"].rotation_quaternion', out_q[h])
        w.add(arm, f'pose.bones["{ch.bones["hips"]}"].location', hips_loc)
        if self.root_pos or self.root_yaw:
            ch.root.rotation_mode = "XYZ"
            w.add(ch.root, "location", out_root)
            w.add(ch.root, "rotation_euler", [(0.0, 0.0, math.radians(y)) for y in out_yaw])
        for end, o in out_limb.items():
            ik, hold = cons[end]
            tgt, pole = ch.handles[f"{end}-target"], ch.handles[f"{end}-pole"]
            hh = ch.handles[f"{end}-hold"]
            hh.rotation_mode = "QUATERNION"
            w.add(tgt, "location", o["t"])
            w.add(pole, "location", o["pole"])
            w.add(hh, "rotation_quaternion", o["q"])
            lower = ch.bones[end.replace("Hand", "LowerArm").replace("Foot", "LowerLeg")]
            w.add(arm, f'pose.bones["{lower}"].constraints["{ik.name}"].influence', [[x] for x in o["w"]])
            w.add(arm, f'pose.bones["{ch.bones[end]}"].constraints["{hold.name}"].influence', [[x] for x in o["tw"]])
        if face:
            for (ob, key), vals in out_face.items():
                w.add(ob.data.shape_keys, f'key_blocks["{key}"].value', [[v] for v in vals])
        w.write()
        bpy.context.view_layer.update()
        if self.props:
            self._bake_props(frames)
        if self.sec is not None:
            self._bake_secondary(frames)
        scene.frame_set(keep)

    def _look_blinks(self) -> list:
        """Seconds when a look swings far enough to blink on (the start of the swing)."""
        out = []
        if not self.blink or len(self.look_keys) < 2:
            return out
        for p, a in zip(self.look_keys[:-1], self.look_keys[1:]):
            if p[1] is None or a[1] is None:
                continue
            f = p[0]
            root, yaw = self.root_at(f)
            _, heads = self.fk(f)
            eye = heads["head"]
            da = to_char(self._resolve(p[1], f), root, yaw) - eye
            db = to_char(self._resolve(a[1], f), root, yaw) - eye
            ang = math.degrees(math.acos(np.clip(np.dot(da, db) / np.linalg.norm(da) / np.linalg.norm(db), -1, 1)))
            if ang >= self.blink["on_turns"]:
                out.append(f / self.fps)
        return out

    def _look(self, f, turns, hips, root, yaw, state) -> None:
        """Add the look-at's turns at frame f (head, neck, spine, eyes; each lagging by its own time)."""
        if not self.look_keys:
            return
        ks = self.look_keys
        i = int(np.searchsorted([k[0] for k in ks], f, side="right"))
        a = ks[max(0, i - 1)]
        b = ks[i] if i < len(ks) else None
        tot, heads = fk(self.order, self.parents, self.rest_heads, turns, hips_offset=hips)
        eye = (heads["leftEye"] + heads["rightEye"]) / 2 if "leftEye" in heads and "rightEye" in heads else heads["head"]
        hy, hp = yaw_pitch(tot["head"] @ np.array([0.0, -1.0, 0.0]))

        def aim(key):
            if key[1] is None:
                return None
            return yaw_pitch(to_char(self._resolve(key[1], f), root, yaw) - eye)

        if b is None or i == 0:
            key = b if i == 0 else a
            ya = aim(key)
            wt = key[3]
        else:
            k = ease((f - a[0]) / (b[0] - a[0]), b[2])
            ya, yb = aim(a), aim(b)
            wt = a[3] + (b[3] - a[3]) * k
            if ya is None:
                ya = yb
            elif yb is not None:
                ya = (ya[0] + (unwrap(ya[0], yb[0]) - ya[0]) * k, ya[1] + (yb[1] - ya[1]) * k)
        if ya is None:
            dy = dp = 0.0
        else:
            dy = max(-HEAD_LIMIT[0] - EYE_LIMIT[0], min(HEAD_LIMIT[0] + EYE_LIMIT[0], unwrap(0.0, ya[0] - hy))) * wt
            dp = max(-HEAD_LIMIT[1] - EYE_LIMIT[1], min(HEAD_LIMIT[1] + EYE_LIMIT[1], ya[1] - hp)) * wt
        dt = 1.0 / self.fps
        lag = 0.16 * self.look_lag
        body_y = body_p = 0.0
        for h, (sy, sp) in LOOK_SHARES.items():
            if h not in turns:
                continue
            ty = max(-HEAD_LIMIT[0], min(HEAD_LIMIT[0], dy)) * sy
            tp = max(-HEAD_LIMIT[1], min(HEAD_LIMIT[1], dp)) * sp
            st = state.setdefault(h, [ty, 0.0, tp, 0.0])
            st[0], st[1] = smooth_damp(st[0], st[1], ty, LOOK_LAG[h] * lag, dt)
            st[2], st[3] = smooth_damp(st[2], st[3], tp, LOOK_LAG[h] * lag, dt)
            turns[h] = vrm.euler((st[2], 0.0, st[0])) @ turns[h]
            body_y += st[0]
            body_p += st[2]
        st = state.setdefault("eyes", [dy, 0.0, dp, 0.0])
        st[0], st[1] = smooth_damp(st[0], st[1], dy, LOOK_LAG["eyes"], dt)
        st[2], st[3] = smooth_damp(st[2], st[3], dp, LOOK_LAG["eyes"], dt)
        ey = max(-EYE_LIMIT[0], min(EYE_LIMIT[0], st[0] - body_y))
        ep = max(-EYE_LIMIT[1], min(EYE_LIMIT[1], st[2] - body_p))
        for e in ("leftEye", "rightEye"):
            if e in turns:
                turns[e] = vrm.euler((ep, 0.0, ey)) @ turns[e]

    def _face(self, t, bound, blinks, speech) -> dict:
        """Every bound shape key's value at t seconds."""
        import fnmatch

        ch = self.ch
        if self.expr:
            vals = {kb: 0.0 for kb in bound}
            for name, tr in self.expr.items():
                w = float(tr.at(t * self.fps)[0])
                if name in ch.binary:
                    w = float(round(w))
                for ob, key, bw in ch.expressions[name]:
                    vals[(ob, key)] += w * bw
        else:
            vals = dict(bound)
        blink = max((blink_shape(t - b) for b in blinks), default=0.0)
        talking, quiet = 0.0, set()
        mouth: dict = {}
        for a, b, q, ts, vs in speech:
            env = smoothstep(a - 0.12, a, t) * (1.0 - smoothstep(b, b + 0.15, t))
            if env > talking:
                talking = env
            if env > 0:
                quiet.update(q)
                for v, arr in vs.items():
                    mouth[v] = max(mouth.get(v, 0.0), float(np.interp(t, ts, arr, left=0.0, right=0.0)))
        own_blink = {(ob, key) for ob, key, _ in ch.expressions.get(self.blink["expression"], [])} if self.blink else set()
        for (ob, key) in vals:
            if talking and any(fnmatch.fnmatchcase(key.lower(), p.lower()) for p in quiet):
                vals[(ob, key)] *= 1.0 - talking
            if blink and self.blink and (ob, key) not in own_blink and \
                    any(fnmatch.fnmatchcase(key.lower(), p.lower()) for p in self.blink["quiet"]):
                vals[(ob, key)] *= 1.0 - blink
        if blink:
            for ob, key, bw in ch.expressions[self.blink["expression"]]:
                vals[(ob, key)] += blink * bw
        for v, m in mouth.items():
            for ob, key, bw in ch.expressions[v]:
                vals[(ob, key)] += m * bw
        return {kb: min(1.0, max(0.0, v)) for kb, v in vals.items()}

    def _bake_props(self, frames) -> None:
        """Child Of constraints for each prop's holders, influences keyed (constant) and inverses set at handoffs."""
        import bpy
        from mathutils import Matrix

        scene = bpy.context.scene
        for ob, sched, p_build, w_build in self.props:
            for c in [c for c in ob.constraints if c.name.startswith("carry")]:
                ob.constraints.remove(c)
            ob.parent = None
            ob.matrix_world = Matrix(w_build.tolist())
            B = w_build
            segs = []
            for i, (f, holder) in enumerate(sched):
                c = ob.constraints.new("CHILD_OF")
                c.name = f"carry{i}"
                if holder is None:
                    e = bpy.data.objects.new(f"{ob.name}-at{i}", None)
                    self.ch.coll.objects.link(e)
                    e.hide_render = True
                    c.target = e
                elif isinstance(holder, tuple):
                    c.target, c.subtarget = holder[1], holder[2]
                else:
                    c.target = holder
                c.set_inverse_pending = False
                segs.append((f, holder, c))
            # each holder's inverse: the prop where the last holder had it on the handoff frame
            inv_prev, hold_prev = None, None
            for i, (f, holder, c) in enumerate(segs):
                if i == 0:
                    inv = np.linalg.inv(p_build) if holder is not None else np.eye(4)
                    W = None
                else:
                    scene.frame_set(int(math.ceil(f)))
                    W = _holder_matrix(hold_prev, self.ch) @ inv_prev @ B
                    inv = np.linalg.inv(_holder_matrix(holder, self.ch)) @ W @ np.linalg.inv(B)
                if holder is None and i > 0:
                    c.target.matrix_world = Matrix(np.eye(4).tolist())
                c.inverse_matrix = Matrix(inv.tolist())
                inv_prev, hold_prev = inv, holder
            # one holder at a time
            for i, (f, holder, c) in enumerate(segs):
                nxt = segs[i + 1][0] if i + 1 < len(segs) else math.inf
                for fr in frames:
                    c.influence = 1.0 if (f <= fr < nxt) else 0.0
                    c.keyframe_insert("influence", frame=fr)
            _constant(ob)

    def _world_mats(self, fi: int) -> dict:
        """Every humanoid bone's world matrix (pose_bone.matrix in the world) on the bake's fi-th frame, by FK of the
        baked turns (IK not included)."""
        ch, F, s = self.ch, self.ch.frame, self.ch.scale
        b = self._baked
        tot, heads = fk(self.order, self.parents, self.rest_heads, b["turns"][fi], hips_offset=b["hips"][fi])
        root = np.eye(4)
        root[:3, :3] = rz(b["yaw"][fi]) * s
        root[:3, 3] = b["root"][fi]
        mw = root @ np.array(ch.armature.matrix_basis)
        out = {}
        for h in self.order:
            bn = ch.bones[h]
            rest = np.array(ch.armature.data.bones[bn].matrix_local)
            m = np.eye(4)
            m[:3, :3] = F @ tot[h] @ F.T @ rest[:3, :3]
            m[:3, 3] = F @ (heads[h] / s)
            out[bn] = mw @ m
        return out

    def _bake_secondary(self, frames) -> None:
        """Simulate the loose chains over the baked body and key their bones."""
        import fnmatch

        import bpy

        from . import vrm_rig

        ch, arm, cfg = self.ch, self.ch.armature, self.sec
        scene = bpy.context.scene
        humanoid = set(ch.bones.values())
        if cfg["chains"]:
            chains_ = [list(c) for c in cfg["chains"]]
        else:
            chains_ = [c for c in vrm_rig.chains(ch, cfg["pattern"]) if not set(c) & humanoid]
        chains_ = [c for c in chains_ if c and arm.data.bones[c[0]].parent is not None]
        dangles = cfg["dangles"]
        if not chains_ and not dangles:
            return
        bones = arm.data.bones
        info = []
        for c in chains_:
            setting = next((v for p, v in cfg["settings"].items() if fnmatch.fnmatchcase(c[0], p)), {})
            parent = bones[c[0]].parent.name
            rest = [np.array(bones[b].matrix_local) for b in c]
            prest = np.array(bones[parent].matrix_local)
            basis = [np.array(arm.pose.bones[b].matrix_basis) for b in c]
            lengths = [bones[b].length for b in c]
            info.append(dict(chain=c, parent=parent, rest=rest, prest=prest, basis=basis, lengths=lengths, **{
                "stiffness": setting.get("stiffness", cfg["stiffness"]), "drag": setting.get("drag", cfg["drag"]),
                "gravity": setting.get("gravity", cfg["gravity"]), "wind": setting.get("wind_scale", 1.0)}))
        for d in dangles:
            d["empty"].rotation_quaternion = tuple(d["base"])       # as it hangs, under its bone
            d.pop("mats", None)
        # each parent's world matrix on every frame: from the baked turns (FK, no scene evaluation) where nothing but
        # this bake moves it, else read back from the scene on every few frames and eased between
        bpy.context.view_layer.update()
        now = {b.name: np.array(arm.matrix_world) @ np.array(b.matrix) for b in arm.pose.bones}
        names = {v: k for k, v in ch.bones.items()}
        ik = {self.ch.bones[h] for end in self.limbs for h in _limb_bones(end) if h in self.ch.bones}
        for pb in arm.pose.bones:
            if pb.name in names and any(c.type in ("IK", "COPY_ROTATION") for c in pb.constraints):
                ik.update(self.ch.bones[h] for h in _limb_bones(names[pb.name]) if h in self.ch.bones)

        def anchor(bone):
            """The humanoid bone a bone is carried by (itself, or its nearest humanoid ancestor)."""
            b = arm.data.bones[bone]
            while b is not None and b.name not in names:
                b = b.parent
            return b.name if b is not None else None

        free = ch.root.parent is None and not _animated_by_others(ch.root, self)
        wanted = {i["parent"] for i in info} | {d["empty"].parent_bone for d in dangles
                                               if d["empty"].parent_type == "BONE" and d["empty"].parent is arm}
        wanted.discard("")
        by_fk = {b for b in wanted if free and anchor(b) is not None and anchor(b) not in ik}
        mats = {b: [] for b in wanted}
        if by_fk:
            for fi in range(len(frames)):
                fk_now = self._world_mats(fi)
                for b in by_fk:
                    a = anchor(b)
                    mats[b].append(fk_now[names[a]] @ np.linalg.inv(now[a]) @ now[b])
        slow = (wanted - by_fk) | ({None} if any(d["empty"].parent_type != "BONE" or d["empty"].parent is not arm
                                                 for d in dangles) else set())
        if slow:
            step = 3
            picks = sorted(set(range(0, len(frames), step)) | {len(frames) - 1})
            got = {b: {} for b in slow}
            muted = [md for ob in ch.meshes for md in ob.modifiers if md.show_viewport]
            for md in muted:
                md.show_viewport = False
            try:
                for fi in picks:
                    scene.frame_set(frames[fi])
                    mw = np.array(arm.matrix_world)
                    for b in slow:
                        if b is not None:
                            got[b][fi] = mw @ np.array(arm.pose.bones[b].matrix)
                    for k, d in enumerate(dangles):
                        got.setdefault(("dangle", k), {})[fi] = np.array(d["empty"].matrix_world)
            finally:
                for md in muted:
                    md.show_viewport = True
            for key, samples in got.items():
                seq = _ease_mats(samples, len(frames))
                if isinstance(key, tuple):
                    dangles[key[1]]["mats"] = seq
                else:
                    mats[key] = seq
        for d in dangles:
            e = d["empty"]
            if "mats" not in d:
                # rigid on its bone: where the bone takes it from how they stand now
                rel = np.linalg.inv(now[e.parent_bone]) @ np.array(e.matrix_world)
                d["mats"] = [m @ rel for m in mats[e.parent_bone]]

        def goal(ci, pm):
            """The chain carried rigidly by its parent's world matrix: its joints and its tip (n+1, 3), and each
            bone's world matrix."""
            pts, ms = [], []
            m_parent = pm
            prest = ci["prest"]
            for r, bs, ln in zip(ci["rest"], ci["basis"], ci["lengths"]):
                m = m_parent @ np.linalg.inv(prest) @ r @ bs
                pts.append(m[:3, 3])
                ms.append(m)
                m_parent, prest = m, r
            pts.append((ms[-1] @ np.array([0.0, ci["lengths"][-1], 0.0, 1.0]))[:3])
            return np.array(pts), ms

        dt = 1.0 / self.fps
        n_sub = cfg["substeps"]
        h = dt / n_sub
        out = {b: [] for ci in info for b in ci["chain"]}
        for k, ci in enumerate(info):
            pm = mats[ci["parent"]]
            g0, _ = goal(ci, pm[0])
            world_len = [float(np.linalg.norm(g0[j + 1] - g0[j])) for j in range(len(g0) - 1)]
            pts, prev = g0.copy(), g0.copy()
            rng = np.random.default_rng(cfg["seed"] + k)
            phase = rng.uniform(0, 2 * math.pi)
            grav = np.array([0.0, 0.0, -ci["gravity"]])

            def wind_at(t):
                w = cfg["wind"] * ci["wind"]
                if not np.any(w):
                    return np.zeros(3)
                return w * gust(t, cfg["seed"]) * (1.0 + 0.25 * math.sin(2 * math.pi * 1.9 * t + phase))

            # settle into its hang before the first frame
            for _ in range(int(0.6 / h)):
                new = chain_step(pts, prev, g0, world_len, dt=h, stiffness=ci["stiffness"], drag=ci["drag"],
                                 gravity=grav, wind=wind_at(frames[0] * dt), iterations=3)
                prev, pts = pts, new
            sims = []
            for fi in range(len(frames)):
                ga, _ = goal(ci, pm[max(0, fi - 1)])
                gb, _ = goal(ci, pm[fi])
                for sub in range(n_sub):
                    u = (sub + 1) / n_sub if fi > 0 else 1.0
                    g = ga + (gb - ga) * u
                    new = chain_step(pts, prev, g, world_len, dt=h, stiffness=ci["stiffness"], drag=ci["drag"],
                                     gravity=grav, wind=wind_at((frames[fi] - 1 + u) * dt), iterations=3)
                    prev, pts = pts, new
                sims.append(pts.copy())
            # back to bone turns: each bone swung from where its (new) parent carries it to the simulated point
            for fi, sim in enumerate(sims):
                m_parent = pm[fi]
                prest = ci["prest"]
                for j, (b, r, bs) in enumerate(zip(ci["chain"], ci["rest"], ci["basis"])):
                    carry = m_parent @ np.linalg.inv(prest) @ r
                    m = carry @ bs
                    cur = m[:3, 1] / np.linalg.norm(m[:3, 1])
                    want = sim[j + 1] - m[:3, 3]
                    if np.linalg.norm(want) > 1e-6:
                        sw = swing_to(cur, want)
                        m = m.copy()
                        m[:3, :3] = sw @ m[:3, :3]
                    local = np.linalg.inv(carry) @ m
                    r3 = local[:3, :3] / np.linalg.norm(local[:3, :3], axis=0)
                    out[b].append(quat(r3))
                    m_parent, prest = m, r
        # the props hung from a pivot: one link each, swung from how they are carried to where it has swung
        w = _Writer(frames)
        for k, d in enumerate(dangles):
            ms = d["mats"]
            grav = np.array([0.0, 0.0, -cfg["gravity"]])

            def tip(m, d=d):
                return m[:3, 3] + m[:3, :3] @ d["local"] * d["length"] / max(1e-9, np.linalg.norm(m[:3, :3] @ d["local"]))

            g0 = np.array([ms[0][:3, 3], tip(ms[0])])
            pts, prev = g0.copy(), g0.copy()
            seed = cfg["seed"] + 100 + k
            for _ in range(int(0.6 / h)):
                new = chain_step(pts, prev, g0, [d["length"]], dt=h, stiffness=d["stiffness"], drag=d["drag"],
                                 gravity=grav, wind=cfg["wind"] * d["wind"] * gust(frames[0] * dt, seed))
                prev, pts = pts, new
            qs = []
            for fi in range(len(frames)):
                ga = np.array([ms[max(0, fi - 1)][:3, 3], tip(ms[max(0, fi - 1)])])
                gb = np.array([ms[fi][:3, 3], tip(ms[fi])])
                for sub in range(n_sub):
                    u = (sub + 1) / n_sub if fi > 0 else 1.0
                    new = chain_step(pts, prev, ga + (gb - ga) * u, [d["length"]], dt=h, stiffness=d["stiffness"],
                                     drag=d["drag"], gravity=grav,
                                     wind=cfg["wind"] * d["wind"] * gust((frames[fi] - 1 + u) * dt, seed))
                    prev, pts = pts, new
                m3 = ms[fi][:3, :3] / np.linalg.norm(ms[fi][:3, :3], axis=0)
                sw = swing_to(m3.T @ (gb[1] - gb[0]), m3.T @ (pts[1] - pts[0]))
                qs.append(quat(matrix(d["base"]) @ sw))
            w.add(d["empty"], "rotation_quaternion", qs)
        for b, qs in out.items():
            arm.pose.bones[b].rotation_mode = "QUATERNION"
            w.add(arm, f'pose.bones["{b}"].rotation_quaternion', qs)
        w.write()

def _limb_bones(end: str) -> tuple:
    """The humanoid bones an IK on a limb's end moves (and every bone carried by them)."""
    h = vrm.canonical(end)
    side = "left" if h.startswith("left") else "right" if h.startswith("right") else ""
    if not side:
        return ()
    if h.endswith(("Hand", "LowerArm", "UpperArm")):
        return (f"{side}UpperArm", f"{side}LowerArm", f"{side}Hand")
    if h.endswith(("Foot", "LowerLeg", "UpperLeg", "Toes")):
        return (f"{side}UpperLeg", f"{side}LowerLeg", f"{side}Foot", f"{side}Toes")
    return ()


def _animated_by_others(ob, perf) -> bool:
    """Whether something other than this performance's root keys moves `ob` (a shot's own keys, a constraint)."""
    if ob.constraints:
        return True
    ad = ob.animation_data
    if ad is None or ad.action is None:
        return False
    from . import toon

    paths = {fc.data_path for fc in toon._fcurves(ad.action)}
    ours = {"location", "rotation_euler"} if (perf.root_pos or perf.root_yaw) else set()
    return bool(paths - ours)


def _ease_mats(samples: dict, n: int) -> list:
    """World matrices on every one of n frames from some of them ({index: 4x4}): positions eased linearly, turns
    slerped (scale kept from the nearer sample)."""
    keys = sorted(samples)
    out = []
    for i in range(n):
        j = int(np.searchsorted(keys, i, side="right")) - 1
        a = keys[max(0, j)]
        b = keys[min(len(keys) - 1, max(0, j) + 1)]
        if a == b or i <= a:
            out.append(samples[a] if i <= a or a == b else samples[b])
            continue
        k = (i - a) / (b - a)
        ma, mb = samples[a], samples[b]
        sa = np.linalg.norm(ma[:3, :3], axis=0)
        r = matrix(slerp(quat(ma[:3, :3] / sa), quat(mb[:3, :3] / np.linalg.norm(mb[:3, :3], axis=0)), k))
        m = np.eye(4)
        m[:3, :3] = r * sa
        m[:3, 3] = ma[:3, 3] + (mb[:3, 3] - ma[:3, 3]) * k
        out.append(m)
    return out


def fold_for(upper: float, lower: float, reach: float) -> float:
    """How far (degrees from straight) a two-bone limb `upper` and `lower` long folds to span `reach` from its root
    to its end (law of cosines; straight past its length, fully folded inside their difference)."""
    r = min(upper + lower, max(abs(upper - lower), float(reach)))
    c = (upper * upper + lower * lower - r * r) / (2.0 * upper * lower)
    return 180.0 - math.degrees(math.acos(min(1.0, max(-1.0, c))))


def ground_of(ground):
    """The ground's height as a function of world (x, y): from a number (level), a function, or a Blender object
    (cast straight down onto it from above; where it misses, the nearest height found so far, else its lowest)."""
    if callable(ground):
        return ground
    if hasattr(ground, "ray_cast"):
        import bpy
        from mathutils import Vector

        ob = ground
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        mw = ob.matrix_world.copy()
        inv = mw.inverted()
        top = max((mw @ Vector(c)).z for c in ob.bound_box) + 1.0
        low = min((mw @ Vector(c)).z for c in ob.bound_box)
        last = [low]

        def z(x, y):
            o = inv @ Vector((float(x), float(y), top))
            d = (inv.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
            hit, loc, _, _ = ev.ray_cast(o, d)
            if hit:
                last[0] = (mw @ loc).z
            return last[0]
        return z
    h = float(ground)
    return lambda x, y: h


def _pivot(ankle, yaw: float, pitch: float, lever: float, ah: float) -> np.ndarray:
    """The ankle of a foot (flat at `ankle`, heading `yaw` world degrees, the ankle `ah` above the ground) rolled
    `pitch` degrees (+ toes down) about the point on the ground `lever` metres ahead of the ankle along the foot (the
    ball: +; the heel: -)."""
    if not pitch:
        return np.asarray(ankle, float)
    f = np.array([math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0.0])
    z = np.array([0.0, 0.0, 1.0])
    pivot = np.asarray(ankle, float) + f * lever - z * ah
    x0, z0 = -lever, ah
    t = math.radians(pitch)
    x1, z1 = x0 * math.cos(t) + z0 * math.sin(t), -x0 * math.sin(t) + z0 * math.cos(t)
    return pivot + f * x1 + z * z1


class _Offset:
    """A target spec moved by an offset in the character's frame (a wrist behind the grip it holds)."""

    def __init__(self, spec, offset):
        self.spec, self.offset = spec, np.asarray(offset, float)


def _spec(target):
    """A target as a spec: ("world", p), ("char", p), ("call", fn), ("object", ob), or an _Offset."""
    if isinstance(target, _Offset):
        return target
    if isinstance(target, tuple) and len(target) == 2 and target[0] in ("world", "char", "call", "object"):
        return (target[0], np.asarray(target[1], float) if target[0] in ("world", "char") else target[1])
    if callable(target):
        return ("call", target)
    if hasattr(target, "matrix_world"):
        return ("object", target)
    return ("world", np.asarray(target, float))


def _holder_matrix(holder, ch) -> np.ndarray:
    """The world matrix a prop's holder carries it by now."""
    if holder is None:
        return np.eye(4)
    if isinstance(holder, tuple):
        _, arm, bone = holder
        return np.array(arm.matrix_world) @ np.array(arm.pose.bones[bone].matrix)
    return np.array(holder.matrix_world)


class _Writer:
    """Keys on every frame of a bake, written straight into the f-curves (a keyframe_insert a value is slow): each
    channel's keys in the bake's frames replaced, its keys outside them kept. Quaternions kept on one hemisphere from
    frame to frame, so they interpolate the short way."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.items = []

    def add(self, id_, path: str, values) -> None:
        v = np.array([np.atleast_1d(np.asarray(x, float)) for x in values])
        if path.endswith("rotation_quaternion"):
            for i in range(1, len(v)):
                if np.dot(v[i], v[i - 1]) < 0:
                    v[i] = -v[i]
        self.items.append((id_, path, v))

    def write(self) -> None:
        from . import toon

        f0, f1 = self.frames[0], self.frames[-1]
        for id_, path, v in self.items:
            id_.keyframe_insert(data_path=path, index=-1, frame=f0)
            fcs = {fc.array_index: fc for fc in toon._fcurves(id_.animation_data.action) if fc.data_path == path}
            for i in range(v.shape[1]):
                fc = fcs.get(i)
                if fc is None:
                    continue
                kept = [(kp.co[0], kp.co[1]) for kp in fc.keyframe_points if not f0 - 0.5 < kp.co[0] < f1 + 0.5]
                pts = sorted(kept + list(zip(self.frames, v[:, i].tolist())))
                fc.keyframe_points.clear()
                fc.keyframe_points.add(len(pts))
                fc.keyframe_points.foreach_set("co", [c for p in pts for c in p])
                fc.update()


def _constant(id_) -> None:
    """Every key of an ID's action stepped (constant): a holder switches on its frame."""
    from . import toon

    ad = id_.animation_data
    if ad is None or ad.action is None:
        return
    for fc in toon._fcurves(ad.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"
