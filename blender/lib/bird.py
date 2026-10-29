"""A bird from code for ink-wash anime shots: a big rain-soaked crow, its silhouette built feather by feather (a heavy
arched beak, a shaggy throat, folded wings whose primaries cross over a rounded tail, fingered primaries when it
spreads them), on a simple rig of joints, posed and keyed frame by frame: perched, its head turning in sharp jerks and
holds as a crow's does, cawing, crouching to spring, taking off, flapping and gliding along a path.

- `Pose`: what a frame of the bird is, as numbers (radians and metres): the body's pitch and lift, the neck's and head's
  turn, the gape, the tail's pitch and spread, how far the wings are open and where they are in a beat, the feet
  tucked. `PERCH`, `CROUCH`, `CAW`, `FLIGHT` and `GLIDE` are poses to start from; `lerp(a, b, k)` blends two.
- `flap(phase, ...)`: the wings at a point of one beat (0..1: the downstroke, then the upstroke with the hands swept
  back), as the joints' angles; `beat(t, rate)` the phase at a time.
- `path(points, n)`: a flight through control points (Catmull-Rom, evened out by arc length): each sample's place, the
  bird's heading and pitch along it, and its bank into the turns.
- `holds(keys, t)`: a crow's head moves in snaps between holds: the value at time t of keys (time, value) that each
  arrive over a few frames and hold.
- `build(name, coll, ...)`: the crow in Blender, in its own collection; a `Crow` whose `key(frame, pose)` keys every
  joint, and `place(frame, location, heading, pitch, bank)` keys where it is in the world.

Local axes: +y forward (the beak), +z up, +x the bird's right; the feet's grip at the origin; a crow about 0.5 m long
and a metre across the wings at `scale` 1. The rig is a hierarchy of empties (root, body, neck, head, jaw, the wings'
arms and hands, tail, feet) carrying rigid meshes, so a pose is a few rotations and nothing has to deform.

The pure parts (poses, the flap, the path, the holds) are numpy only and tested without Blender; `build` needs it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace

import numpy as np

HIP = 0.105          # the body's pivot over the feet (m, at scale 1)
SHOULDER = (0.036, 0.055, 0.03)      # the right wing's shoulder in the body (m)
ARM, HAND = 0.17, 0.12               # the wing's arm (shoulder to wrist) and hand (wrist to the outer primary's root)
NECK = (0.0, 0.085, 0.035)           # the neck's base in the body
HEAD = (0.0, 0.055, 0.03)            # the head's centre from the neck's base
JAW = (0.0, 0.03, -0.012)            # the gape's hinge from the head's centre
TAIL = (0.0, -0.115, 0.004)          # the tail's base in the body
CROW = {   # linear colours: blue-black feathers with a cold sheen, a dark grey beak and feet, the eye's glint
    "feather": ((0.022, 0.024, 0.032), (0.006, 0.0065, 0.009)),
    "sheen": (0.13, 0.15, 0.22),
    "beak": ((0.03, 0.03, 0.034), (0.008, 0.008, 0.009)),
    "feet": ((0.04, 0.038, 0.04), (0.01, 0.01, 0.011)),
    "eye": (0.006, 0.005, 0.005),
    "glint": (0.85, 0.88, 0.95),
    "bead": (0.3, 0.33, 0.4),
}


@dataclass(frozen=True)
class Pose:
    """A frame of the bird. Angles in radians; `lift` in metres (at scale 1). Positive pitches raise the front;
    positive yaws turn to the bird's left; `open` 0 has the wings folded on its back, 1 spread; `lift_*`, `sweep_*`
    and `twist` are the wings' arm and hand: raised (+) or lowered, swept back (+), the feathers' angle to the air."""
    body_pitch: float = 0.0
    body_roll: float = 0.0
    lift: float = 0.0
    neck_pitch: float = 0.0
    neck_yaw: float = 0.0
    head_pitch: float = 0.0
    head_yaw: float = 0.0
    head_tilt: float = 0.0
    jaw: float = 0.0
    tail_pitch: float = 0.0
    tail_spread: float = 1.0
    open: float = 0.0
    lift_arm: float = 0.0
    lift_hand: float = 0.0
    sweep_arm: float = 0.0
    sweep_hand: float = 0.0
    twist: float = 0.0
    tuck: float = 0.0       # the feet drawn up under the body, 0..1
    ruffle: float = 0.0     # the body's feathers fluffed out (a shake, a caw), 0..1


def lerp(a: Pose, b: Pose, k: float) -> Pose:
    """`a` blended toward `b` by k (0..1; not clamped, so an overshoot can be asked for)."""
    return Pose(**{f.name: getattr(a, f.name) + (getattr(b, f.name) - getattr(a, f.name)) * k for f in fields(Pose)})


PERCH = Pose(body_pitch=math.radians(44), neck_pitch=math.radians(-24), head_pitch=math.radians(-18),
             tail_pitch=math.radians(6), tail_spread=0.75)
CROUCH = replace(PERCH, body_pitch=math.radians(18), lift=-0.035, neck_pitch=math.radians(-8), head_pitch=math.radians(-6),
                 tail_pitch=math.radians(-14), tail_spread=0.9, ruffle=0.3)
# a caw: head thrust forward and down, beak wide, the body bowing, the tail flicking up, the throat shaggy
CAW = replace(PERCH, body_pitch=math.radians(26), neck_pitch=math.radians(-30), head_pitch=math.radians(-4),
              jaw=math.radians(30), tail_pitch=math.radians(-16), tail_spread=1.1, ruffle=1.0)
FLIGHT = Pose(body_pitch=math.radians(6), neck_pitch=math.radians(-4), head_pitch=math.radians(-4), tail_pitch=math.radians(-6),
              tail_spread=1.15, open=1.0, tuck=1.0)
GLIDE = replace(FLIGHT, lift_arm=math.radians(10), lift_hand=math.radians(4), sweep_hand=math.radians(6), tail_spread=1.3)


def flap(phase: float, *, amp: float = 1.0, base: Pose = FLIGHT) -> Pose:
    """`base` with its wings at `phase` (0..1) of a beat: a downstroke from high to low over the first 55% (the hands
    spread and lagging the arms), an upstroke back with the hands swept back and folded in, the body bobbing against
    the wings and the tail working with them. `amp` scales the beat (0 holds `base`)."""
    p = phase % 1.0
    down = 0.55
    # the arm: high at 0, low at `down`, high again at 1 (cosine through each stroke)
    u = p / down if p < down else 1 + (p - down) / (1 - down)
    arm = math.cos(math.pi * u)                         # 1 high, -1 low
    lag = math.cos(math.pi * (u - 0.22))                # the hand follows a little behind
    up = max(0.0, math.sin(math.pi * (p - down) / (1 - down))) if p >= down else 0.0   # 0..1 through the upstroke
    return replace(base,
                   lift_arm=base.lift_arm + amp * math.radians(42) * arm,
                   lift_hand=base.lift_hand + amp * math.radians(30) * lag,
                   sweep_arm=base.sweep_arm + amp * math.radians(18) * up,
                   sweep_hand=base.sweep_hand + amp * math.radians(55) * up,
                   twist=base.twist + amp * math.radians(-12) * math.sin(math.pi * u),
                   lift=base.lift + amp * 0.012 * arm,
                   body_pitch=base.body_pitch + amp * math.radians(3) * arm,
                   tail_pitch=base.tail_pitch + amp * math.radians(5) * lag)


def beat(t: float, rate: float, *, phase: float = 0.0) -> float:
    """The phase (0..1) of a wingbeat `t` seconds in at `rate` beats a second, starting at `phase`."""
    return (phase + t * rate) % 1.0


def _catmull(p0, p1, p2, p3, u):
    """A centripetal-free (uniform) Catmull-Rom point between p1 and p2; missing ends are mirrored."""
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    p0 = 2 * p1 - p2 if p0 is None else np.asarray(p0, float)
    p3 = 2 * p2 - p1 if p3 is None else np.asarray(p3, float)
    u2, u3 = u * u, u * u * u
    return 0.5 * (2 * p1 + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u2 + (-p0 + 3 * p1 - 3 * p2 + p3) * u3)


def curve(points, n: int, *, dense: int = 32) -> np.ndarray:
    """`n` points along a Catmull-Rom curve through `points`, evenly spaced by arc length."""
    P = [np.asarray(p, float) for p in points]
    if len(P) < 2:
        raise ValueError("a path needs at least two points")
    fine = []
    for i in range(len(P) - 1):
        a, b = P[i], P[i + 1]
        p0 = P[i - 1] if i > 0 else None
        p3 = P[i + 2] if i + 2 < len(P) else None
        for j in range(dense):
            fine.append(_catmull(p0, a, b, p3, j / dense))
    fine.append(P[-1])
    fine = np.array(fine)
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(fine, axis=0), axis=1))]
    want = np.linspace(0.0, s[-1], n)
    return np.column_stack([np.interp(want, s, fine[:, k]) for k in range(3)])


@dataclass(frozen=True)
class PathPoint:
    location: tuple
    heading: float      # radians about z: 0 flies toward +y, positive turns to the left (toward -x)
    pitch: float        # radians: positive climbs
    bank: float         # radians: positive rolls the right wing up (a turn to the left)


def path(points, n: int, *, bank: float = 1.0, max_bank: float = math.radians(50), speeds=None) -> list[PathPoint]:
    """A flight through `points` sampled at `n` places: each one's location, the heading and pitch of the way it
    goes, and a bank into the turn (`bank` times the angle a turn at that speed wants, capped at `max_bank`).
    `speeds` (n,) optional: relative speeds along it (a take-off that gathers pace); the samples are spaced by them."""
    if n < 2:
        raise ValueError("a path needs at least two samples")
    pts = curve(points, max(4 * n, 64))
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    if speeds is None:
        at = np.linspace(0.0, s[-1], n)
    else:
        v = np.asarray(speeds, float)
        if len(v) != n or np.any(v < 0) or not v.sum() > 0:
            raise ValueError("speeds: one non-negative value per sample, not all zero")
        c = np.r_[0.0, np.cumsum((v[1:] + v[:-1]) / 2)]
        at = c / c[-1] * s[-1]
    P = np.column_stack([np.interp(at, s, pts[:, k]) for k in range(3)])
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    heading = np.unwrap(np.arctan2(-T[:, 0], T[:, 1]))
    pitch = np.arcsin(np.clip(T[:, 2], -1, 1))
    # the turn's rate (radians per sample) and the speed (m per sample): a bank of atan(v * omega / g), scaled
    turn = np.gradient(heading)
    speed = np.linalg.norm(np.gradient(P, axis=0), axis=1)
    roll = np.clip(bank * np.arctan(speed * turn * 6.0), -max_bank, max_bank)
    return [PathPoint(tuple(map(float, P[i])), float(heading[i]), float(pitch[i]), float(roll[i])) for i in range(n)]


def holds(keys, t: float, *, snap: float = 0.12) -> float:
    """A value that snaps between holds, as a crow's head turns: `keys` [(time, value), ...] in time order, each value
    arriving over `snap` seconds from its time (a quick ease out, a little overshoot) and held until the next."""
    if not keys:
        raise ValueError("holds: no keys")
    v = keys[0][1]
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t < t1:
            break
        v = b
        u = (t - t1) / snap
        if u < 1.0:
            # an ease out with a 6% overshoot that settles by the end of the snap
            e = 1 - (1 - u) ** 3
            e += 0.06 * math.sin(math.pi * u) * u
            return a + (b - a) * e
    return v


# ---------------------------------------------------------------------------------------------------- geometry

def vane(length: float, width: float, *, curl: float = 0.0, tip: float = 0.35, n: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """A feather's vane as a flat outline along +y from its root at the origin, `length` long and `width` wide at its
    widest: a narrow base, the widest a third along, tapering to a point (`tip` 0..1: how long the taper is), the shaft
    curving by `curl` (m at the tip, toward +x). Returns the left and right edges, (n, 3) each, root to tip."""
    s = np.linspace(0.0, 1.0, n)
    w = width / 2 * np.where(s < 0.3, 0.45 + 0.55 * np.sin(s / 0.3 * math.pi / 2),
                             np.clip((1 - s) / max(tip, 1e-3), 0, 1) ** 0.6 * (1 - 0.15 * (s - 0.3)))
    w[-1] = 0.0
    y = s * length
    x = curl * s * s
    left = np.column_stack([x - w, y, np.zeros(n)])
    right = np.column_stack([x + w, y, np.zeros(n)])
    return left, right


def _feather_mesh(roots, dirs, lengths, widths, *, curls=None, normal=(0.0, 0.0, 1.0), droop=0.0, n: int = 6):
    """Vertices and faces of feathers in one mesh: each a `vane` laid from its root along its direction, flat in the
    plane square to `normal` (the wing's), its tip drooping `droop` of its length along -normal."""
    verts, faces = [], []
    nrm = np.asarray(normal, float)
    nrm /= np.linalg.norm(nrm)
    for i, (r, d, L, w) in enumerate(zip(np.asarray(roots, float), np.asarray(dirs, float), lengths, widths)):
        d = d - nrm * np.dot(d, nrm)
        d /= np.linalg.norm(d)
        side = np.cross(d, nrm)
        left, right = vane(L, w, curl=0.0 if curls is None else curls[i], n=n)
        base = len(verts)
        for e in (left, right):
            for p in e:
                s = p[1] / L
                verts.append(r + side * p[0] + d * p[1] - nrm * droop * L * s * s)
        for j in range(n - 1):
            faces.append((base + j, base + j + 1, base + n + j + 1, base + n + j))
    return verts, faces


def wing_geometry(*, side: int = 1) -> dict:
    """The spread wing's feathers for the right (`side` 1) or left (-1) wing, in its joints' spaces: "arm" from the
    shoulder (the arm along +x, its secondaries trailing toward -y) and "hand" from the wrist (the primaries fanning out
    from back to out, their tips fingered). Each a (verts, faces) pair."""
    rng = np.random.default_rng(3 if side > 0 else 4)
    out = {}
    # the arm: two rows of coverts over ten secondaries
    k = 10
    xs = np.linspace(0.008, ARM - 0.006, k)
    roots = [(x, 0.006, 0.0) for x in xs]
    dirs = [(-0.08 + 0.1 * x / ARM, -1.0, 0.0) for x in xs]
    lens = [0.15 + 0.012 * math.sin(math.pi * x / ARM) + rng.uniform(-0.006, 0.006) for x in xs]
    wid = [0.04] * k
    v1, f1 = _feather_mesh(roots, dirs, lens, wid, droop=0.04)
    rows = []
    for row, (L, y0, z0) in enumerate(((0.075, 0.012, 0.004), (0.045, 0.016, 0.008))):
        m = 12
        xs2 = np.linspace(0.0, ARM, m)
        rows.append(_feather_mesh([(x, y0, z0) for x in xs2], [(0.0, -1.0, 0.0)] * m,
                                  [L * rng.uniform(0.85, 1.1) for _ in xs2], [0.032] * m, droop=0.02))
    # the leading edge: a rounded bar from shoulder to wrist
    out["arm"] = _merge([(v1, f1), *rows, _bar((0.0, 0.004, 0.002), (ARM, 0.008, 0.0), 0.016, 0.01)])
    # the hand: seven primaries fanning from back (inner) to out (outer), the outer five's tips narrowed: the fingers
    m = 7
    roots, dirs, lens, wid, curls = [], [], [], [], []
    for i in range(m):
        f = i / (m - 1)
        ang = math.radians(-100 + 92 * f ** 0.85)          # from pointing back to pointing out (from +x toward -y)
        roots.append((HAND * f ** 0.9, 0.004 - 0.004 * f, 0.0))
        dirs.append((math.cos(ang), math.sin(ang), 0.0))
        lens.append(0.17 + 0.09 * math.sin(math.pi * min(1.0, f * 1.25)) - 0.03 * f)
        wid.append(0.038 - 0.008 * f)
        curls.append(-0.012 * f)
    vh, fh = _feather_mesh(roots, dirs, lens, wid, curls=curls, droop=0.05, n=8)
    cov = _feather_mesh([(HAND * f, 0.01, 0.006) for f in np.linspace(0.0, 0.9, 6)],
                        [(0.25, -1.0, 0.0)] * 6, [0.07, 0.07, 0.065, 0.06, 0.05, 0.04], [0.034] * 6, droop=0.02)
    out["hand"] = _merge([(vh, fh), cov, _bar((0.0, 0.006, 0.0), (HAND * 0.95, 0.0, 0.0), 0.011, 0.006)])
    if side < 0:
        out = {k_: _mirror(v, f) for k_, (v, f) in out.items()}
    return out


def _bar(a, b, r0, r1, n: int = 6):
    """A tapering bar from a to b (radius r0 to r1) as (verts, faces)."""
    from . import shapes

    rings = shapes.loft_points(np.array([a, b], float), [r0, r1], n=n, up=(0, 0, 1))
    return [tuple(p) for p in rings.reshape(-1, 3)], shapes.tube_faces(2, n, cap=True)


def _merge(parts):
    verts, faces = [], []
    for v, f in parts:
        base = len(verts)
        verts.extend(tuple(map(float, p)) for p in v)
        faces.extend(tuple(base + i for i in face) for face in f)
    return verts, faces


def _mirror(verts, faces):
    """Geometry mirrored across x (the other side), its faces turned so they still face out."""
    return [(-x, y, z) for x, y, z in verts], [tuple(reversed(f)) for f in faces]


def folded_geometry(*, side: int = 1):
    """The folded wing lying along the body's right (`side` 1) or left side, in the body's space: coverts over the
    shoulder, then the long primaries sweeping back to cross over the tail."""
    m = 9
    roots, dirs, lens, wid = [], [], [], []
    for i in range(m):
        f = i / (m - 1)
        roots.append((0.05 - 0.006 * f, 0.07 - 0.07 * f, 0.034 - 0.012 * f))
        dirs.append((-0.1 - 0.04 * f, -1.0, -0.02 + 0.04 * f))
        lens.append(0.12 + 0.14 * f ** 0.9)
        wid.append(0.05 - 0.012 * f)
    v, f = _feather_mesh(roots, dirs, lens, wid, normal=(1.0, 0.0, 0.6), droop=0.04)
    cv, cf = _feather_mesh([(0.05, 0.075 - 0.02 * i, 0.04 - 0.004 * i) for i in range(5)], [(-0.1, -1.0, -0.25)] * 5,
                           [0.09, 0.1, 0.1, 0.095, 0.09], [0.05] * 5, normal=(1.0, 0.0, 0.5), droop=-0.04)
    out = _merge([(v, f), (cv, cf)])
    return out if side > 0 else _mirror(*out)


def tail_geometry():
    """The tail's twelve feathers fanned a little from its base, rounded at the end (the middle ones longest)."""
    m = 12
    roots, dirs, lens, wid = [], [], [], []
    for i in range(m):
        f = i / (m - 1) * 2 - 1                              # -1 left ... 1 right
        roots.append((0.012 * f, 0.0, 0.003 * (1 - abs(f))))
        a = math.radians(14) * f
        dirs.append((math.sin(a), -math.cos(a), 0.0))
        lens.append(0.2 - 0.02 * f * f)
        wid.append(0.045)
    return _feather_mesh(roots, dirs, lens, wid, droop=-0.04, n=7)


# ---------------------------------------------------------------------------------------------------- Blender

class Crow:
    """A built crow: its joints (empties by name), its collection, and what `build` made. `key(frame, pose)` keys a
    pose; `place(frame, ...)` keys the root in the world."""

    def __init__(self, joints: dict, coll, objects: dict, scale: float):
        self.joints, self.coll, self.objects, self.scale = joints, coll, objects, scale
        self.root = joints["root"]

    def key(self, frame: int | None, pose: Pose) -> None:
        """Every joint set to `pose`, keyed at `frame` (None: set, not keyed). Joints sit in the root's scaled space, so
        lengths here are at scale 1."""
        j = self.joints

        def put(name, loc=None, rot=None, scale=None):
            ob = j[name]
            for attr, val in (("location", loc), ("rotation_euler", rot), ("scale", scale)):
                if val is None:
                    continue
                setattr(ob, attr, val)
                if frame is not None:
                    ob.keyframe_insert(attr, frame=frame)

        put("body", (0.0, 0.0, HIP + pose.lift), (pose.body_pitch, pose.body_roll, 0.0))
        put("neck", rot=(pose.neck_pitch, 0.0, pose.neck_yaw * 0.35))
        put("head", rot=(pose.head_pitch, pose.head_tilt, pose.head_yaw * 0.65))
        put("jaw", rot=(-pose.jaw, 0.0, 0.0))
        put("tail", rot=(pose.tail_pitch, 0.0, 0.0), scale=(pose.tail_spread, 1.0, 1.0))
        put("ruff", scale=(1.0 + 0.25 * pose.ruffle,) * 3)
        put("feet", (0.0, -0.02 * pose.tuck, 0.07 * pose.tuck), (math.radians(-80) * pose.tuck, 0.0, 0.0))
        # the wings: spread past `open` 0.5, folded on the back below it; while they unfold the spread ones come out
        # of a tucked-back pose
        k = min(1.0, max(0.0, (pose.open - 0.35) / 0.65))
        tuck_arm, tuck_hand = math.radians(85), math.radians(120)
        for side, sgn in (("R", 1.0), ("L", -1.0)):
            lift_a = pose.lift_arm * k + math.radians(15) * (1 - k)
            sweep_a = pose.sweep_arm * k + tuck_arm * (1 - k)
            sweep_h = pose.sweep_hand * k + tuck_hand * (1 - k)
            put(f"wing.{side}", rot=(pose.twist, -sgn * lift_a, -sgn * sweep_a), scale=(0.6 + 0.4 * k,) * 3)
            put(f"hand.{side}", rot=(pose.twist * 0.5, -sgn * pose.lift_hand * k, -sgn * sweep_h))
            for ob in self.objects[f"spread.{side}"]:
                _show(ob, pose.open >= 0.35, frame)
            for ob in self.objects[f"folded.{side}"]:
                _show(ob, pose.open < 0.35, frame)

    def place(self, frame: int, location, heading: float = 0.0, pitch: float = 0.0, bank: float = 0.0) -> None:
        """The root at `location`, turned `heading` about z (0 faces +y), pitched up `pitch`, banked `bank`."""
        r = self.root
        r.location = location
        r.rotation_euler = (pitch, -bank, heading)
        r.keyframe_insert("location", frame=frame)
        r.keyframe_insert("rotation_euler", frame=frame)

    def hold(self, kinds=("hide_render", "hide_viewport")) -> None:
        """Key visibility constant (a wing swap is a cut, never a fade)."""
        from . import toon

        for ob in self.coll.all_objects:
            ad = ob.animation_data
            if ad is None or ad.action is None:
                continue
            for fc in toon._fcurves(ad.action):
                if fc.data_path in kinds:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "CONSTANT"


def _show(ob, on: bool, frame: int | None) -> None:
    ob.hide_render = ob.hide_viewport = not on
    if frame is None:
        return
    ob.keyframe_insert("hide_render", frame=frame)
    ob.keyframe_insert("hide_viewport", frame=frame)


def materials(look=None, colors=CROW) -> dict:
    """The crow's toon materials: blue-black feathers with a cold wet sheen and a rim, the beak's harder sheen, the
    feet, the eye and its glint, and the rain beaded on it."""
    from . import toon

    lit, shade = colors["feather"]
    m = {
        "feather": toon.cel("crow-feather", lit, shade, look=look, cut=0.32, soft=0.06, mid=(lit[0] * 0.55, lit[1] * 0.55, lit[2] * 0.6),
                            mid_cut=0.12, spec=(colors["sheen"], 0.28, 0.5), rim=(colors["sheen"], 0.18, 0.6)),
        "beak": toon.cel("crow-beak", *colors["beak"], look=look, cut=0.35, soft=0.04,
                         spec=(tuple(c * 1.6 for c in colors["sheen"]), 0.18, 0.45)),
        "feet": toon.cel("crow-feet", *colors["feet"], look=look, cut=0.4),
        "eye": toon.flat("crow-eye", colors["eye"], look=look),
        "glint": toon.flat("crow-glint", colors["glint"], look=look, strength=1.6),
        "bead": toon.flat("crow-bead", colors["bead"], look=look, strength=1.0),
    }
    return m


def build(name: str = "crow", coll=None, *, look=None, scale: float = 1.0, colors=CROW, beads: int = 40, seed: int = 1) -> Crow:
    """The crow in its own collection (a child of `coll`, default the scene's): its rig of empties, rigid meshes on
    them, rain beaded on its back, head and folded wings (`beads`), perched in `PERCH` at the origin. Returns the
    Crow to pose; line art and the shot's look are the shot's."""
    import bpy

    from . import shapes, toon

    c = toon.collection(name, coll)
    m = materials(look, colors)
    rng = np.random.default_rng(seed)

    def joint(jname, parent, loc=(0.0, 0.0, 0.0)):
        ob = bpy.data.objects.new(f"{name}-{jname}", None)
        ob.empty_display_size = 0.02
        c.objects.link(ob)
        ob.parent = parent
        ob.location = loc
        ob.rotation_mode = "XYZ"
        return ob

    J = {}
    J["root"] = joint("root", None)
    J["root"].scale = (scale,) * 3
    J["body"] = joint("body", J["root"], (0.0, 0.0, HIP))
    J["ruff"] = joint("ruff", J["body"])
    J["neck"] = joint("neck", J["body"], NECK)
    J["head"] = joint("head", J["neck"], HEAD)
    J["jaw"] = joint("jaw", J["head"], JAW)
    J["tail"] = joint("tail", J["body"], TAIL)
    J["feet"] = joint("feet", J["root"])
    for side, sgn in (("R", 1.0), ("L", -1.0)):
        J[f"wing.{side}"] = joint(f"wing.{side}", J["body"], (sgn * SHOULDER[0], SHOULDER[1], SHOULDER[2]))
        J[f"hand.{side}"] = joint(f"hand.{side}", J[f"wing.{side}"], (sgn * ARM, 0.0, 0.0))

    objs = {}

    def mesh(oname, verts, faces, mat, parent, smooth=True, solid=0.0):
        ob = shapes.mesh_object(f"{name}-{oname}", verts, faces, mat, c, smooth=smooth)
        ob.parent = parent
        if solid:
            so = ob.modifiers.new("solid", "SOLIDIFY")
            so.thickness = solid
            so.offset = 0.0
        ob.visible_shadow = True
        objs[oname] = ob
        return ob

    def adopt(ob, parent):
        ob.parent = parent
        objs[ob.name.removeprefix(f"{name}-")] = ob
        return ob

    feather = m["feather"]
    # the body: a deep-breasted torso from the tail's base to the breast, shaggy where it is wet
    path = np.array([(0, -0.125, 0.006), (0, -0.07, 0.0), (0, -0.01, -0.004), (0, 0.05, -0.002), (0, 0.095, 0.014)])
    adopt(shapes.loft(f"{name}-torso", path, [0.03, 0.052, 0.06, 0.056, 0.04], [0.03, 0.055, 0.068, 0.066, 0.045],
                      material=feather, coll=c, n=14, subsurf=1, offset=[(0, 0.0), (0, -0.004), (0, -0.01), (0, -0.012), (0, -0.004)]),
          J["body"])
    # wet clumps over the back and breast: spikes lying back along the body
    roots, tips, widths = [], [], []
    for _ in range(46):
        u = rng.uniform(-0.09, 0.08)
        a = rng.uniform(-math.pi, math.pi)
        r = np.array([0.055 * math.cos(a), u, 0.06 * math.sin(a) - 0.008])
        tip = r + np.array([0.004 * math.cos(a), -rng.uniform(0.03, 0.055), 0.006 * math.sin(a) - 0.004])
        roots.append(r)
        tips.append(tip)
        widths.append(rng.uniform(0.008, 0.014))
    adopt(shapes.spikes(f"{name}-clumps", roots, tips, widths, material=feather, coll=c, sides=3), J["ruff"])
    # the neck and the head: a thick neck, a flat-crowned head, the throat's shaggy hackles
    adopt(shapes.loft(f"{name}-neckmesh", np.array([(0, -0.02, -0.01), (0, 0.025, 0.012), (0, 0.06, 0.03)]), [0.042, 0.036, 0.03],
                      [0.046, 0.038, 0.032], material=feather, coll=c, n=12, subsurf=1), J["neck"])
    adopt(shapes.ellipsoid(f"{name}-skull", (0.0, 0.004, 0.004), (0.033, 0.046, 0.034), material=feather, coll=c, n=18,
                           squash=lambda v: v * np.c_[np.ones(len(v)), np.ones(len(v)), 1 - 0.18 * np.clip(v[:, 2], 0, 1)]),
          J["head"])
    roots, tips, widths = [], [], []
    for i in range(16):
        f = i / 15
        a = math.radians(-60 + 120 * rng.uniform())
        r = np.array([0.024 * math.sin(a), 0.02 - 0.05 * f, -0.022 - 0.006 * math.cos(a)])
        roots.append(r)
        tips.append(r + np.array([0.008 * math.sin(a), -0.012 - 0.01 * f, -0.03 - 0.012 * rng.uniform()]))
        widths.append(0.009)
    adopt(shapes.spikes(f"{name}-hackles", roots, tips, widths, material=feather, coll=c, sides=3), J["head"])
    # the beak: heavy, its ridge arched to a hooked tip; the lower mandible on the jaw; bristles over its base
    up = np.array([(0, 0.028, 0.004), (0, 0.05, 0.004), (0, 0.072, -0.0), (0, 0.09, -0.008), (0, 0.098, -0.017)])
    adopt(shapes.loft(f"{name}-beak", up, [0.012, 0.009, 0.0065, 0.0035, 0.0008], [0.012, 0.01, 0.007, 0.004, 0.001],
                      material=m["beak"], coll=c, n=10, subsurf=1, offset=[(0, 0.0), (0, 0.001), (0, 0.001), (0, 0.0), (0, 0.0)]),
          J["head"])
    lo = np.array([(0, 0.0, 0.0), (0, 0.025, -0.002), (0, 0.05, -0.002), (0, 0.06, -0.003)])
    adopt(shapes.loft(f"{name}-mandible", lo, [0.01, 0.007, 0.004, 0.001], [0.006, 0.005, 0.003, 0.001],
                      material=m["beak"], coll=c, n=8, subsurf=1), J["jaw"])
    adopt(shapes.spikes(f"{name}-bristles", [(sx * 0.008, 0.03, 0.01) for sx in (-1, -0.4, 0.4, 1)],
                        [(sx * 0.009, 0.052, 0.006) for sx in (-1, -0.4, 0.4, 1)], [0.006] * 4, material=feather, coll=c,
                        sides=3), J["head"])
    # the eyes: dark beads with a glint
    for sgn in (1, -1):
        adopt(shapes.ellipsoid(f"{name}-eye{'R' if sgn > 0 else 'L'}", (sgn * 0.027, 0.02, 0.012), (0.0075, 0.0075, 0.0075),
                               material=m["eye"], coll=c, n=10), J["head"])
        g = adopt(shapes.ellipsoid(f"{name}-glint{'R' if sgn > 0 else 'L'}", (sgn * 0.0335, 0.022, 0.0145), (0.0018,) * 3,
                                   material=m["glint"], coll=c, n=6), J["head"])
        g.visible_shadow = False
        g.lineart.usage = "EXCLUDE"
    # the tail and the wings
    mesh("tail", *tail_geometry(), feather, J["tail"], smooth=False, solid=0.002)
    for side, sgn in (("R", 1), ("L", -1)):
        geo = wing_geometry(side=sgn)
        arm = mesh(f"arm.{side}", *geo["arm"], feather, J[f"wing.{side}"], smooth=False, solid=0.002)
        hand = mesh(f"hand.{side}", *geo["hand"], feather, J[f"hand.{side}"], smooth=False, solid=0.002)
        fold = mesh(f"fold.{side}", *folded_geometry(side=sgn), feather, J["ruff"], smooth=False, solid=0.002)
        objs[f"spread.{side}"] = [arm, hand]
        objs[f"folded.{side}"] = [fold]
    # the legs and toes: three toes forward and one back, gripping the perch's top at z 0
    for sgn in (1, -1):
        x = sgn * 0.016
        adopt(shapes.cylinder(f"{name}-leg{sgn}", (x, 0.0, 0.004), (x * 1.3, -0.005, 0.11), 0.0045, material=m["feet"], coll=c, n=6),
              J["feet"])
        for k, (dx, dy) in enumerate(((-0.012, 0.03), (0.0, 0.034), (0.012, 0.03), (0.0, -0.026))):
            adopt(shapes.loft(f"{name}-toe{sgn}{k}", np.array([(x, 0.0, 0.004), (x + dx * 0.7, dy * 0.7, 0.004), (x + dx, dy, -0.006)]),
                              [0.0035, 0.003, 0.0012], material=m["feet"], coll=c, n=5, subsurf=0), J["feet"])
    # rain beaded on the back, the crown and the folded wings: small bright drops sitting on the feathers
    bead_on = [(objs["torso"], J["body"], 0.35), (objs["skull"], J["head"], 0.2), (objs["fold.R"], J["ruff"], 0.2),
               (objs["fold.L"], J["ruff"], 0.2)]
    placed = 0
    for ob, parent, share in bead_on:
        want = int(round(beads * share))
        vs = [(v.co.copy(), v.normal.copy()) for v in ob.data.vertices if v.normal.z > 0.25]
        if not vs or not want:
            continue
        for i in rng.choice(len(vs), size=min(want, len(vs)), replace=False):
            co, nr = vs[int(i)]
            r = rng.uniform(0.0012, 0.0024)
            p = tuple(co + nr * r * 0.6 + ob.location)
            b = shapes.ellipsoid(f"{name}-bead{placed}", p, (r, r, r * 0.7), material=m["bead"], coll=c, n=6)
            b.parent = parent
            b.visible_shadow = False
            b.lineart.usage = "EXCLUDE"
            objs.setdefault("beads", []).append(b)
            placed += 1
        # beads ride with what they sit on: the folded wings' hide with them
        if ob.name.endswith(("fold.R", "fold.L")):
            side = ob.name[-1]
            objs[f"folded.{side}"] += objs["beads"][placed - min(want, len(vs)):placed]
    crow = Crow(J, c, objs, scale)
    crow.key(None, PERCH)
    return crow
