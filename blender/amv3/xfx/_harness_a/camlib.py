"""Stand-in for blender/amv3/camlib.py (core) so the xfx-A harness runs before the core lands.

Only what the stage contract promises. The harness puts this directory on sys.path AFTER blender/amv3, so the real
camlib wins as soon as it exists.
"""
import math

LENS_MM = 35.0
SENSOR_MM = 36.0
CARD_W = 1.92
CARD_H = 1.08
FILL_DIST = CARD_W * LENS_MM / SENSOR_MM


class State:
    def __init__(self, s, cx, cy, r, ds=0.0, dcx=0.0, dcy=0.0, dr=0.0):
        self.s, self.cx, self.cy, self.r = s, cx, cy, r
        self.ds, self.dcx, self.dcy, self.dr = ds, dcx, dcy, dr

    def __repr__(self):
        return (f"State(s={self.s:.4f}, c=({self.cx:.1f}, {self.cy:.1f}), r={self.r:.2f}, "
                f"ds={self.ds:.4f}, dc=({self.dcx:.2f}, {self.dcy:.2f}), dr={self.dr:.3f})")


def ease_in_expo(u):
    return 0.0 if u <= 0 else 2.0 ** (10 * (u - 1))


def ease_out_expo(u):
    return 1.0 if u >= 1 else 1 - 2.0 ** (-10 * u)


def ease_in_out_cubic(u):
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def hermite(p0, m0, p1, m1, u):
    u2, u3 = u * u, u * u * u
    return (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * m1


def smoothstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def lerp(a, b, u):
    return a + (b - a) * u


def deg(x):
    return math.degrees(x)
