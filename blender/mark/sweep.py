"""Sweeps for the weave: a strand as one mesh, a twisted thread that flattens into a satin ribbon. bpy-free.

A strand runs along a 3D centreline. Up to `s_band` it is the film's thread: three plies twisted round the axis (a
lobed round section, right-hand lay). Over `morph` before `s_band` the section flattens into the ribbon's: a band with
softly rounded edges, `offa` out on side A and `offb` on side B (in the band's plane), `h` either side of it. Every
ring has the same number of points in the same order, so the mesh keeps one topology whatever part of it shows: a
Geometry Nodes window (build.py) draws it on by pulling points outside [s0, s1] onto the centreline.

Per point it carries what the window and the shaders need:
  s      arc length of its ring (mark px)
  c      its ring's centre (on the centreline), where the window pulls it
  v      across the band, -1 (side B) .. 1 (side A); 0 on the thread
  m      thread 0 .. ribbon 1
  dt, dh where the tail's and the head's terminal shapes move it (the ends form as the strand comes to rest)
Ring frames: T along, N in the band's plane toward side A, B = T x N out of it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# The section's points: the band's outline, walls, corners and faces, with support points beside each corner so smooth
# shading keeps the faces flat and the edges round.
N_CORNER = 5  # segments round each rounded edge
N_FACE = 8  # segments across each face


def band_section(offa, offb, h, rc):
    """The band's section as (n, K, 2) points (N, B) and (n, K) `v`, for arrays offa, offb (n,) and scalars h, rc.
    Counter-clockwise from side A's mid-wall: side A, the +B face, side B, the -B face."""
    offa, offb = np.asarray(offa, float), np.asarray(offb, float)
    half = np.maximum((offa + offb) / 2, 1e-6)  # the band's half-width
    mid = (offa - offb) / 2  # its middle, in N
    r = np.minimum(rc, np.minimum(h * 0.9, half * 0.999))[:, None]
    hh = np.full_like(r, h)
    xa, xb = offa[:, None], -offb[:, None]
    pts = []

    def add(x, y):
        pts.append(np.stack(np.broadcast_arrays(x, y), axis=-1))

    def corner(cx, cy, a0, a1, rr):
        for k in range(1, N_CORNER + 1):
            a = a0 + (a1 - a0) * k / N_CORNER
            add(cx + rr * math.cos(a), cy + rr * math.sin(a))

    def face(x0, x1, y):
        # from x0 (the corner before it, excluded) to x1: a support point just in from each end, the face between
        d = x1 - x0
        sup = np.sign(d) * np.minimum(r * 0.12, np.abs(d) * 0.05)
        add(x0 + sup, y)
        for i in range(1, N_FACE):
            add(x0 + d * i / N_FACE, y)
        add(x1 - sup, y)
        add(x1, y)

    add(xa, 0.0)  # side A's mid-wall
    add(xa, hh - r)
    corner(xa - r, hh - r, 0.0, math.pi / 2, r)
    face(xa - r, xb + r, hh)
    corner(xb + r, hh - r, math.pi / 2, math.pi, r)
    add(xb, 0.0)  # side B's mid-wall
    add(xb, -(hh - r))
    corner(xb + r, -(hh - r), math.pi, 1.5 * math.pi, r)
    face(xb + r, xa - r, -hh)
    corner(xa - r, -(hh - r), 1.5 * math.pi, 2 * math.pi, r)  # ends on side A's wall; the ring closes
    p = np.stack([np.broadcast_to(q, (len(offa), 1, 2)).reshape(len(offa), 2) for q in pts], axis=1)
    v = np.clip((p[..., 0] - mid[:, None]) / half[:, None], -1, 1)
    return p, v


def rope_section(radius, phase, k: int, plies: int = 3, groove: float = 0.24):
    """A twisted `plies`-ply thread's section: (n, K, 2) points (N, B) at K even angles, lobes at `phase` (n,)."""
    th = np.linspace(0, 2 * math.pi, k, endpoint=False)[None, :]
    g = 0.5 * (1 + np.cos(plies * (th - np.asarray(phase, float)[:, None])))  # 1 on a ply's crown, 0 in a groove
    rr = np.asarray(radius, float)[:, None] * (1 - groove * (1 - g ** 0.35))
    return np.stack([rr * np.cos(th), rr * np.sin(th)], axis=-1)


def rmf(c: np.ndarray, n_end: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Tangents and a rotation-minimising normal along polyline c, the normal carried back from `n_end` at the last
    point (double reflection, Wang et al. 2008)."""
    d = np.gradient(c, axis=0)
    T = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    N = np.empty_like(c)
    n = n_end - T[-1] * np.dot(n_end, T[-1])
    N[-1] = n / np.linalg.norm(n)
    for i in range(len(c) - 1, 0, -1):
        v1 = c[i - 1] - c[i]
        c1 = np.dot(v1, v1)
        if c1 < 1e-18:
            N[i - 1] = N[i]
            continue
        rl = N[i] - (2 / c1) * np.dot(v1, N[i]) * v1
        tl = T[i] - (2 / c1) * np.dot(v1, T[i]) * v1
        v2 = T[i - 1] - tl
        c2 = np.dot(v2, v2)
        nn = rl - (2 / c2) * np.dot(v2, rl) * v2 if c2 > 1e-18 else rl
        nn = nn - T[i - 1] * np.dot(nn, T[i - 1])
        N[i - 1] = nn / np.linalg.norm(nn)
    return T, N


@dataclass
class Rings:
    """Everything along a strand, one row per ring."""
    s: np.ndarray  # (n,) arc length
    c: np.ndarray  # (n, 3) centre
    T: np.ndarray  # (n, 3)
    N: np.ndarray  # (n, 3) in the band's plane, toward side A
    offa: np.ndarray  # (n,) band half-widths (no terminal shapes)
    offb: np.ndarray
    red0a: np.ndarray  # (n,) the tail terminal's cut into side A / side B at rest
    red0b: np.ndarray
    red1a: np.ndarray  # the head terminal's
    red1b: np.ndarray
    m: np.ndarray  # thread 0 .. ribbon 1
    radius: np.ndarray  # the thread's radius
    phase: np.ndarray  # the plies' twist angle


@dataclass
class Mesh:
    verts: np.ndarray  # (V, 3)
    quads: np.ndarray  # (F, 4)
    tris: np.ndarray  # (G, 3): the end caps, fans round a centre point
    attrs: dict  # name -> (V,) or (V, 3)


def sweep(r: Rings, h: float, rc: float) -> Mesh:
    """The strand's mesh from its rings: the section morphs from thread to band by m."""
    n = len(r.s)
    B = np.cross(r.T, r.N)
    band, v = band_section(r.offa, r.offb, h, rc)
    k = band.shape[1]
    rope = rope_section(r.radius, r.phase, k)
    m = r.m[:, None, None]
    sec = rope * (1 - m) + band * m

    def place(sec2):
        return r.c[:, None, :] + sec2[..., 0:1] * r.N[:, None, :] + sec2[..., 1:2] * B[:, None, :]

    base = place(sec)
    # the terminals: the same section with each end's cut applied, as a displacement from the plain band
    dt = place(rope * (1 - m) + band_section(r.offa - r.red0a, r.offb - r.red0b, h, rc)[0] * m) - base
    dh = place(rope * (1 - m) + band_section(r.offa - r.red1a, r.offb - r.red1b, h, rc)[0] * m) - base

    verts = base.reshape(-1, 3)
    i = np.arange(n - 1)[:, None]
    j = np.arange(k)[None, :]
    a = i * k + j
    b = i * k + (j + 1) % k
    quads = np.stack([a, b, b + k, a + k], axis=-1).reshape(-1, 4)  # outward: (T x N) is B, sections run N -> B

    # end caps: a centre point per end and a fan of triangles, facing back and forward
    c0, c1 = len(verts), len(verts) + 1
    verts = np.vstack([verts, r.c[0], r.c[-1]])
    jj = np.arange(k)
    last = (n - 1) * k
    tris = np.vstack([np.stack([np.full(k, c0), (jj + 1) % k, jj], axis=-1),
                      np.stack([np.full(k, c1), last + jj, last + (jj + 1) % k], axis=-1)])

    def per_ring(x):
        x = np.asarray(x)
        return np.concatenate([np.repeat(x, k, axis=0), x[[0, -1]]], axis=0)

    attrs = {
        "s": per_ring(r.s),
        "c": per_ring(r.c),
        "m": per_ring(r.m),
        "v": np.concatenate([(v * r.m[:, None]).reshape(-1), [0.0, 0.0]]),
        "dt": np.vstack([dt.reshape(-1, 3), np.zeros((2, 3))]),
        "dh": np.vstack([dh.reshape(-1, 3), np.zeros((2, 3))]),
    }
    return Mesh(verts, quads, tris, attrs)
