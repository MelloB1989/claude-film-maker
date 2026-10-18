"""Harness stand-in for blender/amv3/camlib.py (the core owns the real one). Pure Python, no bpy.

Only used when the core's camlib is not importable (xfx-B harness). Same names as the stage contract.
"""
import math
from dataclasses import dataclass

LENS_MM = 35.0
SENSOR_MM = 36.0
CARD_W = 1.92
CARD_H = 1.08
FILL_DIST = CARD_W * LENS_MM / SENSOR_MM


@dataclass
class State:
    s: float
    cx: float
    cy: float
    r: float
    ds: float = 0.0
    dcx: float = 0.0
    dcy: float = 0.0
    dr: float = 0.0


def ease_in_expo(t):
    return 0.0 if t <= 0 else 2.0 ** (10.0 * (min(t, 1.0) - 1.0))


def ease_out_expo(t):
    return 1.0 if t >= 1 else 1.0 - 2.0 ** (-10.0 * max(t, 0.0))


def ease_in_out_cubic(t):
    t = min(max(t, 0.0), 1.0)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def hermite(p0, v0, p1, v1, t, dur=1.0):
    t = min(max(t, 0.0), 1.0)
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1
    h10 = t ** 3 - 2 * t ** 2 + t
    h01 = -2 * t ** 3 + 3 * t ** 2
    h11 = t ** 3 - t ** 2
    return h00 * p0 + h10 * v0 * dur + h01 * p1 + h11 * v1 * dur
