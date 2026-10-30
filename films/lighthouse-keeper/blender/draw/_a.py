"""Helpers of drawer A: two-bone leg IK for Person, and a hand lantern."""
import math

from mathutils import Vector

from lib.toon import D2R


def ik_leg(k, side, foot, bend=(0, -1, 0), frame=None, l1=0.48, l2=0.5):
    """Plant the ankle of leg `side` at `foot` (person space), the knee bending towards `bend`."""
    hp, _ = k.hips[side]
    h = Vector(hp.location)
    f = Vector(foot)
    d = f - h
    L = min(d.length, l1 + l2 - 0.005)
    u = d.normalized()
    f = h + u * L
    a = (l1 * l1 - l2 * l2 + L * L) / (2 * L)
    hh = math.sqrt(max(l1 * l1 - a * a, 0))
    b = Vector(bend)
    b = (b - u * b.dot(u)).normalized()
    knee = h + u * a + b * hh
    k.leg(side, tuple(knee), tuple(f), frame)


def lantern(t, name, parent, size=1.0):
    """An oil lantern hanging from its handle at the origin of `parent` (an empty); returns the empty."""
    g = t.empty(name, (0, 0, 0), parent)
    s = size
    t.torus(f"{name} handle", (0, 0, 0.0), 0.11 * s, 0.02 * s, "iron", parent=g, arc=math.pi, seg=24,
            rot=(D2R(90), 0, 0)).location = (0, 0, -0.02 * s)
    t.cyl(f"{name} cap", (0, 0, -0.12 * s), 0.13 * s, 0.07 * s, "iron", parent=g, r2=0.06 * s, seg=24)
    t.cyl(f"{name} glass", (0, 0, -0.3 * s), 0.12 * s, 0.3 * s, "lamp_glass", parent=g, seg=24)
    t.cyl(f"{name} base", (0, 0, -0.48 * s), 0.14 * s, 0.06 * s, "iron", parent=g, seg=24)
    t.blob(f"{name} flame", (0, 0, -0.32 * s), (0.05 * s, 0.05 * s, 0.1 * s), "flame", parent=g, shape=t.teardrop(0.0) if False else None)
    return g


def hang(k, side, lant):
    """Counter-rotate the lantern (parented to the hand) so it hangs straight down whatever the arm and hand do (call
    after k.arm / k.reach)."""
    a = k.arms[side]
    q = a["shoulder"].rotation_quaternion @ a["elbow"].rotation_quaternion @ a["wrist"].rotation_quaternion
    down = Vector((0, 0, -1))
    lant.rotation_mode = "QUATERNION"
    lant.rotation_quaternion = down.rotation_difference(q.inverted() @ down)


def nightcap(t, k, col="blanket", band="pillow_night", flop=1, name="nightcap"):
    """A soft nightcap on the keeper's head: a band, a cone that bends over to one side (flop = +-1), a pompom."""
    HC = k.HC
    g = t.empty(f"{name} g", (0, 0.03, HC + 0.36), k.head, rot=(D2R(-10), 0, 0))
    t.cyl(f"{name} band", (0, 0, 0.0), 0.57, 0.17, band, parent=g, r2=0.58, seg=48)
    g1 = t.empty(f"{name} g1", (0, 0, 0.06), g)
    t.cyl(f"{name} c1", (0, 0, 0.2), 0.55, 0.4, col, parent=g1, r2=0.4, seg=48)
    g2 = t.empty(f"{name} g2", (0, 0, 0.4), g1, rot=(0, D2R(50 * flop), 0))
    t.cyl(f"{name} c2", (0, 0, 0.18), 0.4, 0.36, col, parent=g2, r2=0.26, seg=48)
    g3 = t.empty(f"{name} g3", (0, 0, 0.36), g2, rot=(0, D2R(70 * flop), 0))
    t.cyl(f"{name} c3", (0, 0, 0.17), 0.26, 0.34, col, parent=g3, r2=0.1, seg=48)
    t.blob(f"{name} pom", (0, 0, 0.4), (0.12, 0.12, 0.12), "pillow", parent=g3)
