"""The reel's camera motion as numbers, from shots.py: where each Reel_ camera is, where it looks and what it focuses
on, frame by frame. Pure Python (no Unreal), so it can be checked offline; build.py keys the result into SEQ_Reel.

How a shot's keys become a move:

- **Easing.** A shot's progress along its keys is a cubic with chosen speeds at its ends, in units of the move's
  average speed: 0 starts or settles from rest, 1 moves at an even speed through the cut. A shot that cuts in or out
  mid-move keeps moving through the cut (a slider never stops on a cut); a move that ends on its detail settles
  (`EASE` below). The handles carry the move on at its end speed, so a cut can be slipped without a hold.
- **Arcs.** An orbit or arc (`ARC`) goes round its look-at point: the camera's horizontal offset from it is
  interpolated in angle and radius, not in a straight line (a straight line between two points of a circle dips
  inside it and slows the turn in the middle).
- **Rotation** is the look-at from the interpolated position to the interpolated aim, with the yaw unwrapped from
  sample to sample: the cameras look down -X, yaw ~180, where Unreal's look-at flips between +179 and -179.
- **Focus** follows the plan's pulls where a shot has one (eased between its keys), else stays on the subject: the
  look-at point, or the eyes of the presenter in a presenter shot. Distances are along the lens's axis (Unreal's
  focal plane is flat), in cm.
"""
from __future__ import annotations

import math

from shots import EYES_HER, EYES_HIM, MARK_HER, MARK_HIM, SHOTS, Shot

HANDLE = 12  # frames before and after each shot, and of the whole sequence
STEP = 2     # a key every STEP frames (the keys are dense, so their tangents never shape the move)

# (speed in, speed out) for each shot, in units of the move's average speed; see the docstring
EASE = {
    "V01": (0.6, 1.0),  # the shelves: the dolly eases off the first frame and keeps streaming through the cut
    "V02": (1.0, 1.0),  # the credenza: an even slider, moving through both cuts
    "V03": (1.0, 0.8),  # the rising crane past the olive
    "V04": (1.0, 0.6),  # the crane up the slats, slowing as the dark sign arrives
    "V05": (0.8, 0.0),  # the room: push and settle (S12 holds the frame at night)
    "S11": (0.5, 1.2),  # the push starts with the drop and gathers pace as the letters light
    "S12": (1.0, 0.7),  # the V05 match, a slow push
    "N01": (1.0, 1.0),  # the night glide: an even slider
    "S13": (1.0, 1.0),  # a creeping push on him
    "S15": (1.0, 1.0),  # near locked-off drift
    "S16": (1.0, 1.0),  # slow push on her
    "S17": (0.3, 0.0),  # crane up and back, settling into the wide that S18 holds
    "S18": (0.0, 0.0),  # locked off
}
ARC: set = set()  # PLAN v2 has no orbit or arc

EYE_FWD = 9.0  # cm: a presenter's eyes are ahead of the mark (feet centre) towards +X, the way both face


def subject(shot: Shot):
    """Where the lens should focus when the shot has no pull: the presenter's eyes, else None (the look-at)."""
    if shot.cast in (("him",), ("him", "her")):
        return [MARK_HIM[0] + EYE_FWD, MARK_HIM[1], EYES_HIM]
    if shot.cast == ("her",):
        return [MARK_HER[0] + EYE_FWD, MARK_HER[1], EYES_HER]
    return None


def progress(u: float, v0: float, v1: float) -> float:
    """0..1 along the move at time u (0..1 of the shot): a cubic Hermite with speeds v0, v1 at the ends (units of the
    average speed); outside 0..1 (the handles) it goes on at the end speeds."""
    if u < 0:
        return v0 * u
    if u > 1:
        return 1 + v1 * (u - 1)
    h01 = -2 * u ** 3 + 3 * u ** 2
    h10 = u ** 3 - 2 * u ** 2 + u
    h11 = u ** 3 - u ** 2
    return h01 + h10 * v0 + h11 * v1


def _lerp(a, b, s):
    return [p + (q - p) * s for p, q in zip(a, b)]


def _arc(l0, l1, a0, a1, s):
    """A point s along the arc from l0 to l1 round the (interpolated) aim: angle and radius interpolated."""
    c = _lerp(a0, a1, s)
    r0, r1 = math.hypot(l0[0] - a0[0], l0[1] - a0[1]), math.hypot(l1[0] - a1[0], l1[1] - a1[1])
    t0, t1 = math.atan2(l0[1] - a0[1], l0[0] - a0[0]), math.atan2(l1[1] - a1[1], l1[0] - a1[0])
    dt = (t1 - t0 + math.pi) % (2 * math.pi) - math.pi
    r, t = r0 + (r1 - r0) * s, t0 + dt * s
    return [c[0] + r * math.cos(t), c[1] + r * math.sin(t), l0[2] + (l1[2] - l0[2]) * s]


def place(shot: Shot, t: float):
    """Camera location and aim at key-time t (frames into the shot along its keys, extrapolated beyond them)."""
    ks = shot.keys
    if len(ks) == 1 or ks[0][1:] == ks[-1][1:]:
        return list(ks[0][1]), list(ks[0][2])
    k = 0
    while k < len(ks) - 2 and t > ks[k + 1][0]:
        k += 1
    (f0, l0, a0), (f1, l1, a1) = ks[k], ks[k + 1]
    s = (t - f0) / (f1 - f0)
    loc = _arc(l0, l1, a0, a1, s) if shot.id in ARC else _lerp(l0, l1, s)
    return loc, _lerp(a0, a1, s)


def look(loc, at):
    """Unreal's look-at rotation (pitch, yaw) in degrees, roll 0."""
    d = [q - p for p, q in zip(loc, at)]
    return math.degrees(math.atan2(d[2], math.hypot(d[0], d[1]))), math.degrees(math.atan2(d[1], d[0]))


def forward(pitch: float, yaw: float):
    p, y = math.radians(pitch), math.radians(yaw)
    return [math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)]


def _eased(keys, f: float) -> float:
    """A focus pull's distance at frame f: smoothstep between its keys, held before and after."""
    if f <= keys[0][0]:
        return keys[0][1]
    for (f0, d0), (f1, d1) in zip(keys, keys[1:]):
        if f <= f1:
            s = (f - f0) / (f1 - f0)
            return d0 + (d1 - d0) * s * s * (3 - 2 * s)
    return keys[-1][1]


def frames(shot: Shot, handle: int = HANDLE):
    """The shot's frame offsets to key: every STEP frames from -handle to frames+handle, both ends included."""
    out = list(range(-handle, shot.frames + handle, STEP))
    return out if out[-1] == shot.frames + handle else out + [shot.frames + handle]


def samples(shot: Shot, handle: int = HANDLE) -> list:
    """[frame in the shot, [x, y, z], pitch, yaw, focus cm] for every keyed frame of the shot, yaw unwrapped."""
    v0, v1 = EASE.get(shot.id, (1.0, 1.0))
    span = shot.keys[-1][0] - shot.keys[0][0]
    target = subject(shot)
    out, prev = [], None
    for f in frames(shot, handle):
        t = shot.keys[0][0] + progress(f / shot.frames, v0, v1) * span
        loc, at = place(shot, t)
        pitch, yaw = look(loc, at)
        if prev is not None:
            yaw += 360 * round((prev - yaw) / 360)
        prev = yaw
        fw = forward(pitch, yaw)
        along = lambda p: sum((q - c) * w for c, q, w in zip(loc, p, fw))  # noqa: E731
        if shot.focus:  # a pull, its keys distances or points (focused on as the camera moves)
            dist = _eased([[k, along(v) if isinstance(v, (list, tuple)) else v] for k, v in shot.focus], f)
        else:
            dist = along(target or at)
        out.append([f, loc, pitch, yaw, dist])
    return out


def cuts(shots=SHOTS) -> list:
    """The edit: [camera label, first frame], the first shot from the sequence's head handle."""
    return [[f"Reel_{s.id}", s.start - (HANDLE if k == 0 else 0)] for k, s in enumerate(shots)]


def cast_at(shots=SHOTS) -> list:
    """[frame, set of who is visible] where it changes. A presenter stays on from the first shot that has them (a
    shot that frames only one still has the other's shadow and reflections in it, and nobody leaves the room)."""
    out, last, who = [], None, set()
    for k, s in enumerate(shots):
        who = who | set(s.cast)
        if who != last:
            out.append([s.start - (HANDLE if k == 0 else 0), who])
            last = who
    return out


if __name__ == "__main__":  # a table of every shot's move: start, middle and end, speeds and focus
    for s in SHOTS:
        sm = samples(s, 0)
        speed = [math.dist(a[1], b[1]) / (b[0] - a[0]) * 24 for a, b in zip(sm, sm[1:])]
        mid = sm[len(sm) // 2]
        print(f"{s.id} {s.lens:>4g}mm  yaw {sm[0][3]:7.1f} -> {sm[-1][3]:7.1f}  pitch {sm[0][2]:5.1f} -> {sm[-1][2]:5.1f}"
              f"  speed cm/s in {speed[0]:5.1f} mid {speed[len(speed) // 2]:5.1f} out {speed[-1]:5.1f}"
              f"  focus {sm[0][4]:5.0f} {mid[4]:5.0f} {sm[-1][4]:5.0f}")
