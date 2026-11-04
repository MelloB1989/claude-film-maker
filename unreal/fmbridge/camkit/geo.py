"""Vectors and rotators the way Unreal has them: left-handed, X forward, Y right, Z up, cm and degrees. A rotator is
a dict {"pitch", "yaw", "roll"} (never positional: unreal.Rotator's positional order is roll, pitch, yaw).

The axes of a rotator are FRotationTranslationMatrix's rows (Engine/Source/Runtime/Core/Public/Math/
RotationTranslationMatrix.h:72-84); a look-at is FVector::ToOrientationRotator (Core/Private/Math/UnrealMath.cpp:200),
which is what KismetMathLibrary.FindLookAtRotation returns."""
from __future__ import annotations

import math

Vec = tuple  # (x, y, z)


def v(p) -> tuple:
    return (float(p[0]), float(p[1]), float(p[2]))


def add(a, b) -> tuple:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b) -> tuple:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s: float) -> tuple:
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b) -> tuple:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a) -> float:
    return math.sqrt(dot(a, a))


def norm(a) -> tuple:
    n = length(a)
    if n < 1e-9:
        raise ValueError(f"cannot normalise a zero vector {a}")
    return mul(a, 1.0 / n)


def lerp(a, b, t: float) -> tuple:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def dist(a, b) -> float:
    return length(sub(a, b))


def rot(pitch: float = 0.0, yaw: float = 0.0, roll: float = 0.0) -> dict:
    return {"pitch": float(pitch), "yaw": float(yaw), "roll": float(roll)}


def as_rot(r) -> dict:
    """A rotator dict from a dict (missing keys 0) or a [pitch, yaw, roll] list (documented order, not Unreal's)."""
    if isinstance(r, dict):
        return rot(r.get("pitch", 0.0), r.get("yaw", 0.0), r.get("roll", 0.0))
    return rot(*r)


def axes(r) -> tuple:
    """(forward, right, up) unit vectors of a rotator, as FRotationTranslationMatrix's X, Y, Z rows."""
    r = as_rot(r)
    sp, cp = math.sin(math.radians(r["pitch"])), math.cos(math.radians(r["pitch"]))
    sy, cy = math.sin(math.radians(r["yaw"])), math.cos(math.radians(r["yaw"]))
    sr, cr = math.sin(math.radians(r["roll"])), math.cos(math.radians(r["roll"]))
    fwd = (cp * cy, cp * sy, sp)
    right = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
    up = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
    return fwd, right, up


def look_at(src, target, roll: float = 0.0) -> dict:
    """The rotator that points X from `src` at `target` (FindLookAtRotation), with an optional roll (a dutch angle)."""
    d = sub(v(target), v(src))
    return rot(math.degrees(math.atan2(d[2], math.hypot(d[0], d[1]))), math.degrees(math.atan2(d[1], d[0])), roll)


def direction(r) -> tuple:
    return axes(r)[0]


def yaw_of(d) -> float:
    """The yaw (degrees) of a direction's horizontal part."""
    return math.degrees(math.atan2(d[1], d[0]))


def from_yaw(yaw: float, pitch: float = 0.0) -> tuple:
    """A unit direction from yaw and pitch (degrees)."""
    cp = math.cos(math.radians(pitch))
    return (cp * math.cos(math.radians(yaw)), cp * math.sin(math.radians(yaw)), math.sin(math.radians(pitch)))


def wrap180(a: float) -> float:
    """An angle in (-180, 180]."""
    a = math.fmod(a + 180.0, 360.0)
    if a < 0:
        a += 360.0
    return a - 180.0 if a != 0 else 180.0


def unwrap(prev: float, a: float) -> float:
    """`a` shifted by whole turns to be nearest `prev` (keyed yaw must not jump across +-180)."""
    return prev + wrap180(a - prev)


def angle_between(a, b) -> float:
    """Degrees between two directions."""
    c = dot(norm(a), norm(b))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def rounded(p, nd: int = 2) -> list:
    return [round(float(x), nd) for x in p]


def rounded_rot(r, nd: int = 3) -> dict:
    r = as_rot(r)
    return {k: round(r[k], nd) for k in ("pitch", "yaw", "roll")}
