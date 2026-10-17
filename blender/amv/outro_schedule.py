"""The SAU_EDITZ outro's timeline as pure functions of the local frame: no bpy, so pytest can pin it.

The After Effects build (handover `outro.jsx`, ref 06) is the spec: 9 extruded letters, each on its own flight, launched
in the order E A T _ I S D Z U with a 3-4 f stagger, 34 f per flight on an expo ease-out, a camera that never stops, a
sweep light, rings, a bloom and a pixel dissolve to black. `outro.py` samples these curves into Blender keyframes, so
the render and the tests read one source of truth.

Frames here are LOCAL: 0 is the first outro frame (comp frame `outro.f`), `n - 1` the last. Lengths are in Blender units
(BU); the AE comp's pixels map at `PX = 1/100` BU, so the layout numbers of `outro.jsx` carry over unchanged.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

WORD = "SAU_EDITZ"
ORDER = (4, 1, 7, 3, 6, 0, 5, 8, 2)          # slots in launch order: E A T _ I S D Z U (ref 06; scrambled, centre-first)
STARTS = (0, 3, 7, 10, 14, 17, 21, 24, 28)   # launch frame of each rank: 3-4 f stagger, flights always overlap
LDUR = 34                                    # frames per flight
LAND = 62                                    # the last flight ends here (28 + 34); the camera settles with it
EXPO = (0.04, 0.49, 0.0, 0.95)               # cubic-bezier of the AE ease (aZ363 M12 fit): snap, then glide
PX = 0.01                                    # BU per AE pixel
FADE = 8                                     # opacity 0 -> 1 over the first frames of a flight
DISSOLVE = (10, 2)                           # block dissolve runs D-10 .. D-2, black from D-2
CAM_DIST = 20.0                              # BU: AE camera zoom 2000 px at z -2000


# --- easing -----------------------------------------------------------------------------------------------------------
def bezier_ease(x1, y1, x2, y2, u):
    """CSS cubic-bezier(x1, y1, x2, y2) at progress u in 0..1: solve x(t) = u, return y(t)."""
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(48):
        t = (lo + hi) / 2
        x = 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t * t * x2 + t ** 3
        if x < u:
            lo = t
        else:
            hi = t
    t = (lo + hi) / 2
    return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t * t * y2 + t ** 3


def expo(u):
    return bezier_ease(*EXPO, u)


def lin(keys, f):
    """AE linear keys [(frame, value), ...]: linear between, held outside."""
    if f <= keys[0][0]:
        return keys[0][1]
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f <= f1:
            return v0 + (v1 - v0) * (f - f0) / (f1 - f0)
    return keys[-1][1]


def smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def rr(seed):
    """outro.jsx `_rr`: a sin hash in 0..1, deterministic so every run flies the same flights."""
    x = math.sin(seed * 12.9898 + 78.233) * 43758.5453
    return x - math.floor(x)


# --- letters ----------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Flight:
    slot: int          # index into WORD
    ch: str
    rank: int          # launch order, 0 = first
    f0: int            # first frame of the flight
    f1: int            # landing frame (f0 + LDUR)
    start: tuple       # (dx, dy, dz) start offset in AE px, outro.jsx: y down, z towards -camera
    spin: tuple        # start rotation (x, y, z) in degrees, all -> 0 on the ease
    tilt: tuple        # start orientation (x, y) in degrees, decays by (1-u)^3 (the AE expression)


def flights():
    """One Flight per letter of WORD, with the AE hash seeds (seed = 7 slot + 3)."""
    out = []
    for s, ch in enumerate(WORD):
        rank = ORDER.index(s)
        f0 = STARTS[rank]
        sd = 7 * s + 3
        rx, ry = rr(sd) * 2 - 1, rr(sd + 1) * 2 - 1
        dx = (-1 if rx < 0 else 1) * (300 + abs(rx) * 600)
        dy = (-1 if ry < 0 else 1) * (300 + abs(ry) * 600)
        dz = -800 - rr(sd + 2) * 1700
        sgn = lambda k, lo, span: (-1 if rr(sd + k) < .5 else 1) * (lo + rr(sd + k + 1) * span)
        spin = (sgn(3, 40, 120), sgn(5, 40, 120), sgn(7, 40, 80))
        tilt = ((rr(sd + 9) * 2 - 1) * 18, (rr(sd + 10) * 2 - 1) * 18)
        out.append(Flight(s, ch, rank, f0, f0 + LDUR, (dx, dy, dz), spin, tilt))
    return out


def letter_state(fl, f):
    """Where letter `fl` is at local frame f: offset from its slot in BU (x right, y away from the camera, z up),
    rotation (x, y, z) in degrees, the orientation tilt, and its opacity 0..1."""
    u = min(1.0, max(0.0, (f - fl.f0) / LDUR))
    k = 1.0 - expo(u)
    dx, dy, dz = fl.start
    # AE: x right, y down, camera at -z. Blender: x right, y away from the camera (-y is towards it), z up.
    off = (dx * k * PX, dz * k * PX, -dy * k * PX)
    rot = tuple(a * k for a in fl.spin)
    kt = (1.0 - u) ** 3
    tilt = (fl.tilt[0] * kt, fl.tilt[1] * kt)
    op = min(1.0, max(0.0, (f - fl.f0) / FADE))
    return {"off": off, "rot": rot, "tilt": tilt, "opacity": op}


# --- camera, light, rings, sparks -------------------------------------------------------------------------------------
def camera(f, n):
    """The AE ORBIT rotation (deg) and LOGO scale (%): expo to LAND, then a linear drift to the last frame."""
    p = expo(min(1.0, f / LAND))
    q = max(0.0, (f - LAND) / max(1, n - LAND))
    rot = []
    for a, b, c in ((-16, 5, 7), (9, -4, -4.6), (-5, 0, 0.6)):
        rot.append(a + (b - a) * p + (c - b) * q)
    sc = 114 + (100 - 114) * p + (97 - 100) * q
    return {"orbit": tuple(rot), "scale": sc}


def sweep(f):
    """The sweep light: a glint crossing the settled word, x -1600 -> +1600 px over f58-76 (comp ~f870-888), intensity
    0 -> 1 (f56-60), hold, -> 0 at f77, so it is gone when the dissolve starts. (AE: f48-70; moved to the settled word.)"""
    x = lin([(58, -1600.0), (76, 1600.0)], f) * PX
    return {"x": x, "level": lin([(56, 0.0), (60, 1.0), (72, 1.0), (77, 0.0)], f)}


# Audio sync (agent-08's mix, outro starts at comp f812): big music hits at f820 and f829 -> local 8 and 17, and the
# shutter_flash SFX at f882.06 -> local 70. Ring pops peak on the two hits (the middle ring lands on 17 as before), the
# white pop lands on 70.
RING_PEAKS = (8, 17, 22)
HITS = (8, 17)
SHUTTER_F = 70
RINGS = ((-420.0, (0.75, 0.05, 0.08)), (0.0, (0.15, 0.35, 0.9)), (420.0, (0.9, 0.15, 0.12)))


def ring(i, f, n):
    """Ring i: opacity 0 -> 1 over the 9 f before its peak (RING_PEAKS), scale 40 -> 100 % over 27 f, drifting to 108 %
    at the end; `pop` is the flare, peaking on the peak frame."""
    pk = RING_PEAKS[i]
    f0 = pk - 9
    return {"opacity": lin([(f0, 0.0), (pk, 1.0)], f),
            "pop": lin([(pk - 4, 0.0), (pk, 1.0), (pk + 6, 0.0)], f),
            "scale": lin([(f0, 0.4), (f0 + 27, 1.0), (n, 1.08)], f)}


def end_fx(f, n):
    """Flash, bloom and dissolve at local frame f (outro.jsx final comp, flashes toned down as fix1 did)."""
    d0, d1 = n - DISSOLVE[0], n - DISSOLVE[1]
    return {
        "hit": max(lin([(0, 0.02), (4, 0.0)], f), lin([(HITS[0] - 1, 0.0), (HITS[0], 0.03), (HITS[0] + 3, 0.0)], f),
                   lin([(HITS[1] - 1, 0.0), (HITS[1], 0.025), (HITS[1] + 3, 0.0)], f)),
        # the camera-shutter SFX: a sharp white pop, decaying over 3 f (linear-light adds: 0.03 is already a visible grey) (replaces AE's soft grey end flash)
        "flash_end": lin([(SHUTTER_F - 1, 0.0), (SHUTTER_F, 1.0), (SHUTTER_F + 1, 0.3), (SHUTTER_F + 3, 0.0)], f),
        "fade_in": lin([(0, 1.0), (5, 0.0)], f),
        "bloom": lin([(0, 1.2), (8, 0.45), (n - 11, 0.45), (n - 8, 0.9), (n, 0.8)], f)
        + 0.9 * max(lin([(h - 1, 0.0), (h, 1.0), (h + 4, 0.0)], f) for h in HITS),
        "dissolve": smooth_ease(lin([(d0, 0.0), (d1, 1.0)], f)),
        "black": 1.0 if f >= n - 2 else 0.0,
    }


def smooth_ease(u):
    """AE ease [0.3, 0, 0.7, 1] on the dissolve completion."""
    return bezier_ease(0.3, 0.0, 0.7, 1.0, u)


def sparks(fl_list, n, per=9):
    """Deterministic sparks: `per` per letter, thrown at its landing frame, ballistic. [(slot, k, f_born, life, v, ..)]."""
    out = []
    for fl in fl_list:
        for k in range(per):
            sd = 101 + fl.slot * 31 + k * 7
            ang = rr(sd) * math.tau
            sp = 1.2 + rr(sd + 1) * 3.2
            born = fl.f1 - 1 + int(rr(sd + 2) * 3)
            life = min(14 + int(rr(sd + 3) * 16), max(6, n - DISSOLVE[0] - born))   # gone before the dissolve starts
            out.append({"slot": fl.slot, "born": born, "life": life,
                        "v": (math.cos(ang) * sp * 0.05, (rr(sd + 4) - .5) * 0.06, math.sin(ang) * sp * 0.05 + 0.03),
                        "size": 0.035 + rr(sd + 5) * 0.05, "ox": (rr(sd + 6) - .5), "oz": (rr(sd + 7) - .5)})
    return out


def spark_state(sp, f):
    """(dx, dy, dz, scale) of a spark relative to its letter centre at local frame f; scale 0 outside its life."""
    t = f - sp["born"]
    if t < 0 or t > sp["life"]:
        return (0.0, 0.0, 0.0, 0.0)
    g = -0.0035
    vx, vy, vz = sp["v"]
    life = t / sp["life"]
    return (sp["ox"] * 1.4 + vx * t, vy * t, sp["oz"] * 1.6 + vz * t + 0.5 * g * t * t, sp["size"] * (1 - life) ** 0.7)
