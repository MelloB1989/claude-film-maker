"""Shinza drawn: the close-up for the standoff, as a 2D drawing at the film end of anime (blender/lib/cels.py):
realistic proportions, lines coloured by what they edge, two cel shades with airbrushed form over them, and soaked
through by the rain.

His design: a lean young ronin, long black hair soaked flat to his skull, pulled back and tied low at the nape, wet
locks loose round his face; a faded crimson cloth band tied round his brow, its frayed tails heavy with water; a thin
old scar through his right brow; a weathered dark kimono, dark with rain, over a pale under-collar.

Head units: the chin at (0.13, 0), the crown at about y = 1.15. He faces right in three quarters (toward Tsuru), his
right side to us. The key light is the overcast sky ahead of him, upper right: the planes turned his way are lit and
the side of his head toward us turns into shade (short lighting). The scene's rims and grade are composited over him,
so none are drawn here.
"""
from __future__ import annotations

import math

import numpy as np

from lib import cels
from lib.cels import Eye, Fill, Line, fill

# ---- palette (sRGB): muted and rain-cooled
INK = "#1b1519"           # the darkest line: lashes, the jaw's shadow side
SKIN = "#c7a998"
SKIN_LIGHT = "#dcc4b5"
SKIN_SHADE = "#8b7675"
SKIN_DEEP = "#5c4a4e"
SKIN_FLUSH = "#b07e74"    # blood near the surface: ears, nose, lids
SKIN_COOL = "#717684"     # a day's stubble along the jaw and lip
LINE_SKIN = "#3a2421"
LINE_JAW = "#2a1c1d"      # the contour along the jaw, in shade
LIP = "#a47c74"
LIP_SHADE = "#76585a"
RIM = "#f2b07a"           # the lantern's edge (the full figure draws it; the close-up's is composited)
HAIR = "#1d2029"
HAIR_SHADE = "#0e1015"
HAIR_MID = "#16181f"       # a clump a little deeper than the rest
HAIR_SHEEN = "#6e788e"
HAIR_GLINT = "#b7c0d2"
LINE_HAIR = "#07080c"
BAND = "#7e2a31"
BAND_SHADE = "#4c1820"
BAND_LIGHT = "#a8494d"
LINE_BAND = "#2a0d12"
CLOTH = "#343947"
CLOTH_SHADE = "#21242d"
CLOTH_DEEP = "#14161c"
CLOTH_SHEEN = "#6c7589"
LINE_CLOTH = "#0f1116"
UNDER = "#b6b4bd"
UNDER_SHADE = "#777989"
WHITE = "#d0cacd"
WHITE_SHADE = "#8c8590"
IRIS_DARK = "#150e0f"
IRIS = "#5a3a2b"
WATER = "#9aa6ba"
GLINT = "#f1f4fa"

W_OUT = 0.0068     # the contour
W_IN = 0.0042      # lines inside
W_FINE = 0.0026    # strands, creases
W_HAIR = 0.0048

CHIN = (0.13, 0.0)
EAR = (-0.29, 0.31)
JAW = (-0.246, 0.192)      # the jaw's angle
TEMPLE = (0.25, 0.86)
NAPE = (-0.37, 0.40)       # where his hair is tied
KNOT = (-0.466, 0.797)     # the band's knot, round the back of the head

# how each colour takes a lightning flash (cels.flash): lit ones bleach, shades sink, lines stay
KINDS = {SKIN_SHADE: "shade", SKIN_DEEP: "shade", SKIN_COOL: "shade", LIP_SHADE: "shade", HAIR: "shade",
         HAIR_SHADE: "shade", HAIR_MID: "shade", BAND_SHADE: "shade", CLOTH: "shade", CLOTH_SHADE: "shade",
         CLOTH_DEEP: "shade", UNDER_SHADE: "shade", WHITE_SHADE: "shade", IRIS_DARK: "ink", IRIS: "shade", INK: "ink",
         LINE_SKIN: "ink", LINE_JAW: "ink", LINE_HAIR: "ink", LINE_BAND: "ink", LINE_CLOTH: "ink"}


def head_outline() -> np.ndarray:
    """The head, skin side: down the far contour (brow ridge, cheekbone, the cheek under it) to a squared chin, back
    along the jaw to its angle and up to the ear, round the skull."""
    return cels.spline([
        TEMPLE, (0.29, 0.75), (0.304, 0.645), (0.292, 0.565), (0.301, 0.505), (0.31, 0.45), (0.298, 0.37),
        (0.278, 0.275), (0.252, 0.185), (0.214, 0.092), (0.178, 0.03), (0.15, 0.004), CHIN, (0.08, 0.006),
        (-0.05, 0.066), (-0.17, 0.132), JAW, (-0.276, 0.262), EAR,
        (-0.38, 0.45), (-0.44, 0.66), (-0.36, 0.90), (-0.12, 1.01), (0.12, 0.99),
    ], closed=True)


def inset(P, depth) -> np.ndarray:
    """The open line P pushed `depth` to its right (one number or one per point)."""
    P = cels._arr(P)
    dep = np.broadcast_to(np.asarray(depth, float), (len(P),))
    return P - cels.normals(P) * dep[:, None]


def ink(points, width, color=LINE_SKIN, *, seed=0, gaps=(), taper_=(0.2, 0.2), tip=0.1, amount=0.25,
        opacity=1.0, corners=()) -> list:
    return cels.brush(points, width, color, gaps=gaps, seed=seed, taper_=taper_, tip=tip, amount=amount,
                      opacity=opacity, corners=corners)


def band_of(points, width, *, taper_=(0.3, 0.3)) -> np.ndarray:
    """A closed band `width` across round a smooth line through points, coming to points at its ends."""
    C = cels.spline(points)
    return cels.ribbon(C, width * cels.taper(C, *taper_, tip=0.0))


def clump(d: cels.Drawing, layer: str, a, b, tip, *, bow=0.08, bow_b=None, curl=0.0, sway=0.0, shade=0.45,
          side="b", glint=None, width=W_HAIR, seed=0, split=1, spread=0.025):
    """One wet clump of hair from two roots to a point: its fill, its shaded side, a lighter run down its middle and
    a glint along its lit edge over `glint` (start, end fractions toward the tip), the hairs in it, its line. `split`
    > 1 parts its last third into that many thinner points about `spread` apart; `sway` degrees swung about its
    roots' middle."""
    a, b, tip = (np.asarray(v, float) for v in (a, b, tip))
    if sway:
        tip = cels.bend([tip], (a + b) / 2, sway, power=1.0)[0]
    lk = cels.lock(a, b, tip, bow=bow, bow_b=bow_b, curl=curl)
    n = 48
    A, B = cels.resample(lk.a, n), cels.resample(lk.b[::-1], n)      # each side, root to tip
    lit, dark = (A, B) if side == "b" else (B, A)
    k = int(n * 0.62) if split > 1 else n - 1
    parts = []
    if split > 1:
        rng = np.random.default_rng(seed)
        along = tip - (A[k] + B[k]) / 2
        L = float(np.linalg.norm(along)) or 1.0
        along /= L
        perp = np.array([-along[1], along[0]])
        for j in range(split):
            r0, r1 = A[k] + (B[k] - A[k]) * (j / split), A[k] + (B[k] - A[k]) * ((j + 1) / split)
            tj = tip + perp * (j - (split - 1) / 2) * spread + along * L * rng.uniform(-0.3, 0.05)
            parts.append(cels.lock(r0, r1, tj, bow=0.05, curl=float(rng.uniform(-0.06, 0.06))))
        body = np.vstack([A[:k + 1], B[:k + 1][::-1]])
    else:
        body = lk.outline
    d.add(layer, Fill(body, HAIR), *[Fill(q.outline, HAIR) for q in parts])
    if shade:
        M = dark + (lit - dark) * shade
        d.add(layer, Fill(np.vstack([dark[:k + 1], M[:k + 1][::-1]]), HAIR_SHADE),
              *[Fill(q.inner(shade, side), HAIR_SHADE) for q in parts])
    # wet hair holds some sky even in shade: a soft lighter run down the lit half of its middle
    i, j = int(n * 0.08), int(n * 0.55)
    c = (dark + (lit - dark) * 0.68)[i:j]
    wid = np.linalg.norm(B - A, axis=1)[i:j] * 0.28
    if len(c) > 3:
        d.add(layer, Fill(cels.ribbon(c, wid * cels.taper(c, 0.4, 0.5, tip=0.0)), HAIR_SHEEN, opacity=0.35))
    # the hairs it's made of, running root to tip
    for m, f in enumerate((0.3, 0.55, 0.75)):
        c = (A + (B - A) * f)[int(n * 0.05 * (m + 1)):int(min(k, n * (0.85 - 0.1 * m)))]
        if len(c) > 3:
            d.add(layer, Line(c, width * 0.5, LINE_HAIR, cels.taper(c, 0.3, 0.4, tip=0.0), False, 0.7))
    if glint:
        # wet light: a thin bright run along the lit edge, not a spot
        g0, g1 = int(glint[0] * n), int(glint[1] * n)
        c = (lit * 0.82 + dark * 0.18)[g0:g1]
        if len(c) > 3:
            q = c[len(c) // 4: 3 * len(c) // 4]
            d.add(layer, Line(c, width * 0.9, HAIR_SHEEN, cels.taper(c, 0.45, 0.45, tip=0.0), False, 0.75),
                  Line(q, width * 0.35, HAIR_GLINT, cels.taper(q, 0.5, 0.5, tip=0.0), False, 0.7))
    if parts:
        for E in (A[:k + 1], B[:k + 1]):
            d.add(layer, Line(E, width, LINE_HAIR, cels.taper(E, 0.25, 0.0, tip=0.0) * cels.pressure(E, seed=seed)))
        for q in parts:
            d.add(layer, Line(q.outline, width * 0.8, LINE_HAIR, cels.taper(q.outline, 0.1, 0.1, tip=0.0)))
    else:
        P = lk.outline
        d.add(layer, Line(P, width, LINE_HAIR, cels.taper(P, 0.25, 0.25, tip=0.0) * cels.pressure(P, seed=seed)))
    return lk


def closeup(t: float = 0.0, flash: float = 0.0, eyes: float = 1.0) -> cels.Drawing:
    """The close-up `t` seconds into the shot: the wind in his hair and the band's tails, the rain on him; `flash`
    0..1 a lightning flash's light on him, `eyes` how open his eyes are (1 as drawn, less narrowed)."""
    d = _closeup(t, eyes)
    d.shift(0.0, 0.004 * math.sin(2 * math.pi * t / 3.0))   # breathing
    if flash > 0:
        d.recolor(lambda c: cels.flash(c, flash, KINDS.get(c, "lit")))
    return d


def _closeup(t: float, eyes: float) -> cels.Drawing:
    d = cels.Drawing()
    gust = math.sin(2 * math.pi * t * 0.7)            # a slow push of wind
    flick = math.sin(2 * math.pi * t * 2.3 + 0.6)     # the quicker shiver at the ends
    head = head_outline()
    _tail(d, gust, flick)
    _band_tails(d, t, gust)
    _collar_back(d)
    _neck(d, head)
    _body(d, t)
    _face(d, head)
    _ear(d)
    _eyes(d, eyes)
    _features(d, head, eyes)
    _wet(d, t)
    _hair(d, gust)
    _band(d, t)
    _strands(d, gust, flick)
    _rain(d, t)
    return d


# ---------------------------------------------------------------------------------------------------- behind him

def _tail(d, gust, flick):
    """The tail tied at the nape, hanging heavy and wet down his back behind the neck."""
    sw = 1.6 * gust + 0.6 * flick
    for k, (a, b, tip, bow) in enumerate([
        ((-0.45, 0.48), (-0.39, 0.43), (-0.62, -0.22), 0.05),
        ((-0.44, 0.47), (-0.35, 0.40), (-0.55, -0.38), 0.05),
        ((-0.43, 0.46), (-0.37, 0.41), (-0.49, -0.50), 0.04),
        ((-0.42, 0.45), (-0.34, 0.39), (-0.44, -0.46), 0.05),
        ((-0.40, 0.44), (-0.33, 0.38), (-0.36, -0.40), 0.04),
    ]):
        clump(d, "hair_back", a, b, tip, bow=bow, sway=sw * (0.8 + 0.12 * k), shade=0.55, seed=k,
              glint=(0.25, 0.42) if k in (1, 3) else None)


def _band_tails(d, t, gust):
    """The band's tails, heavy with water, hanging back and down from the knot; drips off their frayed ends."""
    knot = np.array(KNOT)
    ph = 2 * math.pi * t * 1.1
    for k, (length, ang, w) in enumerate(((0.50, 222.0, 0.066), (0.41, 238.0, 0.058))):
        a = math.radians(ang + 3.0 * gust)
        dirn = np.array([math.cos(a), math.sin(a)])
        u = np.linspace(0, 1, 44)
        c = knot + u[:, None] * length * dirn
        c[:, 1] -= 0.07 * u ** 2                       # the wet cloth sags toward its end
        c = cels.wave(c, 0.012, 0.26, ph + k * 1.3, power=1.4)
        turn = 0.42 + 0.08 * k
        widths = w * (1.0 - 0.2 * u) * (1.0 - 0.7 * np.exp(-((u - turn) / 0.07) ** 2))
        band = cels.ribbon(c, widths)
        N = cels.normals(c)
        i = int(turn * len(u))
        under = cels.ribbon(c[:i + 1] + N[:i + 1] * (widths[:i + 1, None] * 0.24), widths[:i + 1] * 0.52)
        back = cels.ribbon(c[i:], widths[i:])
        edge = c[i + 3:] - N[i + 3:] * (widths[i + 3:, None] * 0.36)
        fold = c[4:i - 2] - N[4:i - 2] * (widths[4:i - 2, None] * 0.1)
        end, nrm = c[-1], N[-1]
        threads = [Line(np.array([end + nrm * o * w * 0.36, end + nrm * o * w * 0.42 + dirn * (0.022 + 0.01 * abs(o)),
                                  end + nrm * o * w * 0.48 + dirn * 0.036 + [0.0, -0.012]]), W_FINE, BAND_SHADE,
                        np.array([1.0, 0.7, 0.0])) for o in (-1.0, -0.3, 0.4, 1.0)]
        d.add("tails", Fill(band, cels.mix(BAND, BAND_SHADE, 0.35)), Fill(under, BAND_SHADE), Fill(back, BAND_SHADE),
              Line(edge, W_FINE * 1.4, BAND_LIGHT, cels.taper(edge, 0.3, 0.3, tip=0.0), False, 0.5),
              ink(fold, W_FINE, LINE_BAND, seed=40 + k, opacity=0.6, taper_=(0.4, 0.4)),
              Line(band, W_IN, LINE_BAND, np.ones(len(band)), True), threads,
              cels.drip(end + dirn * 0.03 + [0.0, -0.01], t, period=1.25, r=0.008, fall=0.35, phase=0.4 * k,
                        body=WATER, ink=LINE_BAND, opacity=0.75))


def _collar_back(d):
    """The kimono's collar standing round the back of his neck, seen past its near side."""
    d.add("collar_back",
          fill([(-0.30, -0.13), (-0.325, 0.0), (-0.37, 0.05), (-0.43, 0.02), (-0.49, -0.12), (-0.42, -0.21)],
               CLOTH_DEEP),
          Fill(band_of([(-0.335, -0.10), (-0.345, -0.01), (-0.37, 0.035)], 0.02), UNDER_SHADE),
          ink([(-0.30, -0.13), (-0.325, 0.0), (-0.37, 0.05), (-0.43, 0.02), (-0.49, -0.12)], W_IN, LINE_CLOTH, seed=7))


# ---------------------------------------------------------------------------------------------------- neck, body

def _neck(d, head):
    neck = fill([(-0.30, 0.42), (-0.05, 0.16), (0.045, 0.05), (0.068, -0.02), (0.086, -0.07), (0.099, -0.095),
                 (0.097, -0.128), (0.107, -0.2), (0.125, -0.40), (-0.36, -0.40), (-0.345, -0.15), (-0.335, 0.10),
                 (-0.335, 0.34)], SKIN, corners=(8, 9))
    d.add("neck", neck)
    # the throat turned to the light; the side of the neck toward us in shade, the muscle from behind the ear to the
    # pit of the neck standing in it
    jaw = cels.between(head, CHIN, EAR)
    s = np.linspace(0, 1, len(jaw))[:, None]
    drop_ = (1 - s) * np.array([-0.025, -0.125]) + s * np.array([-0.005, -0.03])
    cast = np.vstack([jaw[::-1] + [0.0, 0.01], (jaw + drop_)])
    d.add("neck_form",
          fill([(-0.42, 0.46), (-0.205, 0.31), (-0.14, 0.12), (-0.075, -0.06), (-0.015, -0.22), (0.025, -0.44),
                (-0.42, -0.44)], SKIN_SHADE, corners=(5, 6, 0)),
          cels.soft([(-0.255, 0.27), (-0.20, 0.25), (-0.06, -0.10), (0.04, -0.33), (0.0, -0.36), (-0.12, -0.12)],
                    SKIN, spread=0.04, opacity=0.35),
          cels.soft([(-0.42, 0.40), (-0.30, 0.40), (-0.30, -0.42), (-0.42, -0.42)], SKIN_DEEP, spread=0.08,
                    opacity=0.5, smooth=False),
          cels.soft(cast, SKIN_DEEP, spread=0.03, opacity=0.85, smooth=False),
          cels.soft([(0.045, -0.13), (0.10, -0.12), (0.12, -0.36), (0.07, -0.37)], SKIN_LIGHT, spread=0.04,
                    opacity=0.35),
          cels.soft(cels.ellipse((0.088, -0.085), 0.012, 0.018), SKIN_LIGHT, spread=0.012, opacity=0.6),
          cels.soft(cels.ellipse((0.08, -0.13), 0.014, 0.008), SKIN_SHADE, spread=0.012, opacity=0.6),
          cels.soft(cels.ellipse((0.07, -0.33), 0.03, 0.02), SKIN_DEEP, spread=0.025, opacity=0.6),
          mask=("neck",))
    d.add("neck_lines",
          ink([(0.045, 0.05), (0.068, -0.02), (0.088, -0.068), (0.099, -0.095), (0.097, -0.128), (0.107, -0.2),
               (0.125, -0.40)], W_IN, LINE_SKIN, seed=11, gaps=((0.5, 0.75),), taper_=(0.1, 0.2)),
          ink([(-0.335, 0.30), (-0.336, 0.10), (-0.345, -0.15), (-0.36, -0.40)], W_OUT, LINE_SKIN, seed=12,
              taper_=(0.3, 0.1)),
          ink([(-0.20, 0.22), (-0.13, 0.04), (-0.07, -0.10)], W_FINE, LINE_SKIN, seed=13, opacity=0.45,
              taper_=(0.5, 0.5), tip=0.0),
          ink([(0.072, -0.075), (0.083, -0.098), (0.08, -0.12)], W_FINE, LINE_SKIN, seed=14, opacity=0.6,
              taper_=(0.5, 0.5), tip=0.0))


BODY = [(-1.0, -1.6), (-0.97, -1.15), (-0.92, -0.78), (-0.845, -0.535), (-0.745, -0.425), (-0.60, -0.315),
        (-0.44, -0.185), (-0.34, -0.09), (-0.20, -0.18), (0.10, -0.28), (0.20, -0.29), (0.42, -0.37), (0.62, -0.45),
        (0.745, -0.545), (0.85, -0.80), (0.915, -1.2), (0.95, -1.6)]
NEAR_EDGE = [(-0.315, -0.05), (-0.22, -0.15), (-0.10, -0.35), (0.03, -0.70)]          # the V's near side
FAR_RUN = [(0.15, -0.25), (0.13, -0.40), (0.08, -0.57), (0.03, -0.70), (-0.055, -1.05), (-0.13, -1.6)]


def _body(d, t):
    """The kimono, wet through: his left panel over his right (far over near), the collar's band along its edges and
    the pale under-collar inside the V; folds from the shoulders and the crossing, rain glinting on the shoulders."""
    body = fill(BODY, CLOTH, corners=(0, len(BODY) - 1))
    d.add("cloth", body)
    form = [
        # the light falls off down the body
        *cels.soft([(-1.1, -0.95), (1.1, -0.95), (1.1, -1.6), (-1.1, -1.6)], CLOTH_DEEP, spread=0.35, opacity=0.45,
                   smooth=False),
        # the near arm, turned from the light, and the fold between it and the body
        fill([(-1.06, -1.66), (-1.0, -1.15), (-0.95, -0.78), (-0.87, -0.535), (-0.775, -0.465), (-0.725, -0.57),
              (-0.70, -0.76), (-0.665, -1.0), (-0.645, -1.3), (-0.625, -1.66)], CLOTH_SHADE, corners=(0, 9)),
        Fill(band_of([(-0.645, -0.60), (-0.615, -0.90), (-0.585, -1.2), (-0.565, -1.65)], 0.055, taper_=(0.5, 0.0)),
             CLOTH_DEEP),
        # the far arm's fold against the body
        Fill(band_of([(0.53, -0.62), (0.495, -0.95), (0.475, -1.3), (0.465, -1.65)], 0.05, taper_=(0.5, 0.0)),
             CLOTH_DEEP),
        fill([(0.50, -0.70), (0.52, -1.0), (0.53, -1.66), (0.47, -1.66), (0.46, -1.0)], CLOTH_SHADE),
        # the wet cloth clinging over his chest: drape folds pulled from the crossing toward the near arm, one off
        # the far collar
        Fill(band_of([(-0.06, -0.86), (-0.20, -0.76), (-0.34, -0.64)], 0.04), CLOTH_SHADE),
        Fill(band_of([(-0.10, -1.02), (-0.24, -0.95), (-0.40, -0.84)], 0.03), CLOTH_SHADE),
        Fill(band_of([(-0.52, -0.42), (-0.47, -0.62), (-0.46, -0.95), (-0.49, -1.3)], 0.04), CLOTH_SHADE),
        Fill(band_of([(0.22, -0.42), (0.27, -0.66), (0.29, -0.98), (0.27, -1.35)], 0.045), CLOTH_SHADE),
        Fill(band_of([(0.37, -0.45), (0.40, -0.62), (0.41, -0.80)], 0.03), CLOTH_SHADE),
        # the far panel's edge lies over the near: its shadow along the crossing, the collar's down the V
        Fill(band_of([c for c in ((0.03, -0.70), (-0.06, -1.05), (-0.14, -1.62))], 0.08, taper_=(0.2, 0.0))
             - [0.045, 0.0], CLOTH_DEEP),
        # wet weave over the shaded arm
        *cels.hatch((-1.05, -1.65, -0.6, -0.5), angle=74, spacing=0.016, width=0.0028, color=CLOTH_DEEP,
                    opacity=0.35, seed=3),
        *cels.hatch((-0.6, -1.65, 0.95, -0.3), angle=-62, spacing=0.03, width=0.0022, color=CLOTH_SHADE,
                    opacity=0.25, seed=5),
        # rain on the shoulders: a sheen along their tops and sharper glints on the folds
        *cels.soft(band_of([(-0.36, -0.15), (-0.52, -0.255), (-0.68, -0.37), (-0.80, -0.47)], 0.07), CLOTH_SHEEN,
                   spread=0.05, opacity=0.25),
        *cels.soft(band_of([(0.22, -0.31), (0.40, -0.385), (0.58, -0.455), (0.71, -0.53)], 0.09), CLOTH_SHEEN,
                   spread=0.06, opacity=0.3),
        Fill(band_of([(0.30, -0.345), (0.45, -0.40), (0.60, -0.46)], 0.008), GLINT, opacity=0.18),
        Fill(band_of([(-0.47, -0.215), (-0.60, -0.30), (-0.70, -0.38)], 0.006), GLINT, opacity=0.14),
        Fill(band_of([(0.26, -0.70), (0.28, -0.92), (0.27, -1.15)], 0.01) + [0.03, 0.0], CLOTH_SHEEN, opacity=0.5),
        Fill(band_of([(-0.27, -0.66), (-0.20, -0.80), (-0.10, -0.85)], 0.01) + [0.0, 0.03], CLOTH_SHEEN,
             opacity=0.4),
    ]
    d.add("cloth_form", *form, mask=("cloth",))

    # the V: his chest between the collar's edges
    near_edge = cels.spline(NEAR_EDGE)
    far_run = cels.spline(FAR_RUN)
    k = int(np.argmin(np.linalg.norm(far_run - (0.03, -0.70), axis=1)))
    far_edge = far_run[:k + 1]
    chest = Fill(np.vstack([near_edge, far_edge[::-1][1:]]), SKIN)
    d.add("chest", chest)
    d.add("chest_form",
          fill([(-0.42, 0.0), (-0.015, -0.22), (0.025, -0.44), (0.05, -0.75), (-0.42, -0.75)], SKIN_SHADE,
               corners=(0, 3, 4)),
          # the collar standing off the skin shades the V along its near side; the pit of the neck, the collarbone
          Fill(cels.ribbon(cels.offset(near_edge, 0.03), 0.06 * cels.taper(near_edge, 0.0, 0.4, tip=0.3)), SKIN_DEEP),
          *cels.soft([(-0.32, 0.0), (0.16, -0.22), (0.15, -0.30), (-0.05, -0.27), (-0.2, -0.16)], SKIN_DEEP,
                     spread=0.05, opacity=0.8),
          *cels.soft(band_of([(-0.10, -0.31), (-0.02, -0.33), (0.06, -0.345)], 0.016), SKIN_DEEP, spread=0.015,
                     opacity=0.55),
          *cels.soft(band_of([(-0.09, -0.355), (0.0, -0.37), (0.07, -0.38)], 0.016), SKIN_LIGHT, spread=0.015,
                     opacity=0.4),
          *cels.soft(band_of([(0.07, -0.42), (0.065, -0.55), (0.045, -0.66)], 0.02), SKIN_SHADE, spread=0.02,
                     opacity=0.5),
          *cels.soft([(0.09, -0.40), (0.12, -0.38), (0.10, -0.55), (0.075, -0.56)], SKIN_LIGHT, spread=0.02,
                     opacity=0.35),
          mask=("chest",))
    d.add("chest_lines",
          ink([(-0.09, -0.335), (-0.01, -0.35), (0.06, -0.36)], W_FINE, LINE_SKIN, seed=21, opacity=0.6,
              taper_=(0.5, 0.5), tip=0.0),
          ink([(0.068, -0.44), (0.062, -0.55), (0.045, -0.64)], W_FINE, LINE_SKIN, seed=22, opacity=0.4,
              taper_=(0.5, 0.5), tip=0.0))

    under_n = Fill(cels.ribbon(cels.offset(near_edge, 0.016), 0.034), UNDER)
    under_f = Fill(cels.ribbon(cels.offset(far_edge, -0.013), 0.028), UNDER)
    eri_n = Fill(cels.ribbon(cels.offset(near_edge, -0.036), 0.074), CLOTH)
    eri_f = Fill(cels.ribbon(cels.offset(far_run, 0.03), 0.062), CLOTH)
    d.add("collar_n", under_n, eri_n)
    d.add("collar_n_form",
          Fill(cels.ribbon(cels.offset(near_edge, 0.008), 0.018), UNDER_SHADE),
          Fill(cels.ribbon(cels.offset(near_edge, -0.052), 0.042), CLOTH_SHADE),
          Fill(band_of([(-0.30, -0.075), (-0.20, -0.18), (-0.10, -0.36)], 0.008) + [-0.012, -0.004], CLOTH_SHEEN,
               opacity=0.55),
          mask=("collar_n",))
    d.add("collar_f", under_f, eri_f)
    d.add("collar_f_form",
          Fill(cels.ribbon(cels.offset(far_edge, -0.006), 0.012), UNDER_SHADE),
          Fill(cels.ribbon(cels.offset(far_run, 0.052), 0.022), CLOTH_SHADE),
          Fill(cels.ribbon(cels.offset(far_run, 0.022), 0.008), CLOTH_SHEEN, opacity=0.6),
          mask=("collar_f",))
    lines = [
        *ink(BODY[:8], W_OUT, LINE_CLOTH, seed=31, taper_=(0.02, 0.15), tip=0.6),
        *ink(BODY[10:], W_OUT, LINE_CLOTH, seed=32, taper_=(0.15, 0.02), tip=0.6, gaps=((0.12, 0.3),)),
        Line(under_n.points, W_FINE, LINE_CLOTH, np.ones(len(under_n.points)), True, 0.8),
        Line(under_f.points, W_FINE, LINE_CLOTH, np.ones(len(under_f.points)), True, 0.8),
        Line(eri_n.points, W_IN, LINE_CLOTH, np.ones(len(eri_n.points)), True),
        Line(eri_f.points, W_IN, LINE_CLOTH, np.ones(len(eri_f.points)), True),
        # fold lines, broken where the light is on them
        *ink([(-0.52, -0.42), (-0.47, -0.62), (-0.46, -0.95), (-0.49, -1.3)], W_IN, LINE_CLOTH, seed=33,
             gaps=((0.35, 0.5),)),
        *ink([(-0.70, -0.52), (-0.68, -0.85), (-0.66, -1.2)], W_IN, LINE_CLOTH, seed=34),
        *ink([(-0.88, -0.75), (-0.86, -1.0), (-0.88, -1.35)], W_FINE, LINE_CLOTH, seed=35, opacity=0.8),
        *ink([(0.22, -0.42), (0.27, -0.66), (0.29, -0.98), (0.27, -1.35)], W_IN, LINE_CLOTH, seed=36,
             gaps=((0.2, 0.45),)),
        *ink([(0.37, -0.45), (0.40, -0.62), (0.41, -0.80)], W_FINE, LINE_CLOTH, seed=37),
        *ink([(0.53, -0.62), (0.495, -0.95), (0.475, -1.3)], W_IN, LINE_CLOTH, seed=38),
        *ink([(0.66, -0.62), (0.70, -0.85), (0.74, -1.25)], W_FINE, LINE_CLOTH, seed=39, opacity=0.7),
        *ink([(-0.06, -0.86), (-0.20, -0.76), (-0.34, -0.64)], W_FINE, LINE_CLOTH, seed=40, opacity=0.8,
             gaps=((0.45, 0.6),)),
        *ink([(-0.10, -1.02), (-0.24, -0.95), (-0.40, -0.84)], W_FINE, LINE_CLOTH, seed=41, opacity=0.6),
    ]
    d.add("cloth_lines", *lines)


# ---------------------------------------------------------------------------------------------------- the face

TERMINATOR = [(-0.10, 1.04), (-0.13, 0.86), (-0.17, 0.74), (-0.205, 0.635), (-0.225, 0.55), (-0.238, 0.48),
              (-0.22, 0.415), (-0.18, 0.345), (-0.14, 0.26), (-0.095, 0.17), (-0.04, 0.09), (0.02, 0.03),
              (0.06, -0.04)]


def _face(d, head):
    d.add("skin", Fill(head, SKIN))
    T = cels.spline(TERMINATOR)
    shade = np.vstack([T, [(-0.7, -0.06), (-0.7, 1.06)]])
    d.add("skin_form",
          # the cheek facing us darkens toward the turn; the far plane catches the sky
          *cels.soft(np.vstack([inset(T, -0.02)[2:-1], [(0.07, 0.10), (0.13, 0.32), (0.08, 0.50), (-0.02, 0.62),
                                                         (-0.08, 0.80)]]), SKIN_SHADE, spread=0.12, opacity=0.22),
          *cels.soft([(0.22, 0.72), (0.29, 0.70), (0.30, 0.42), (0.26, 0.28), (0.22, 0.40), (0.21, 0.58)],
                     SKIN_LIGHT, spread=0.05, opacity=0.4),
          # a day's stubble: the jaw, the chin, the upper lip, cool and faint
          *cels.soft([(0.20, 0.0), (0.245, 0.12), (0.235, 0.20), (0.20, 0.23), (0.17, 0.205), (0.09, 0.20),
                      (0.04, 0.16), (-0.08, 0.10), (-0.20, 0.20), (-0.26, 0.30), (-0.20, 0.14), (-0.06, 0.04),
                      (0.08, -0.02)], SKIN_COOL, spread=0.07, opacity=0.2),
          # blood near the surface: the nose, the cheek, the lids
          *cels.soft(cels.ellipse((0.19, 0.33), 0.03, 0.025), SKIN_FLUSH, spread=0.04, opacity=0.3),
          *cels.soft(cels.ellipse((-0.04, 0.39), 0.07, 0.035, rotate=-15), SKIN_FLUSH, spread=0.06, opacity=0.18),
          mask=("skin",))
    d.add("skin_shade",
          Fill(shade, SKIN_SHADE),
          # the nose's side plane, turned from the light, and its shadow cast down across the cheek
          fill([(0.112, 0.535), (0.128, 0.47), (0.152, 0.405), (0.183, 0.35), (0.205, 0.318), (0.196, 0.30),
                (0.17, 0.296), (0.148, 0.30), (0.132, 0.318), (0.12, 0.37), (0.104, 0.45), (0.088, 0.51)],
               SKIN_SHADE),
          *cels.soft([(0.20, 0.30), (0.17, 0.285), (0.14, 0.287), (0.125, 0.282), (0.145, 0.268), (0.18, 0.268)],
                     SKIN_SHADE, spread=0.012, opacity=0.6),
          # the band's shadow across the brow, broken by the locks over it
          Fill(np.vstack([[(-0.46, 0.98), (0.36, 0.98)],
                          cels.ragged(cels.spline([(0.34, 0.772), (0.1, 0.782), (-0.15, 0.775), (-0.46, 0.752)]),
                                      0.03, 7, seed=5, vary=0.7, base=0.35)]), SKIN_SHADE),
          # under the lower lip
          *cels.soft(cels.ellipse((0.148, 0.13), 0.03, 0.008, rotate=-6), SKIN_SHADE, spread=0.016, opacity=0.45),
          mask=("skin",))
    d.add("skin_deep",
          # the core of the shadow along the turn, the socket of the near eye, under the near brow, the corner of
          # the mouth, under the jaw by the ear
          *cels.soft(np.vstack([T[1:-2], inset(T, 0.025)[1:-2][::-1]]), SKIN_DEEP, spread=0.03, opacity=0.22,
                     smooth=False),
          *cels.soft(cels.ellipse((0.055, 0.515), 0.025, 0.03), SKIN_SHADE, spread=0.035, opacity=0.4),
          *cels.soft(band_of([(-0.15, 0.555), (-0.06, 0.548), (0.03, 0.535), (0.09, 0.52)], 0.028), SKIN_DEEP,
                     spread=0.03, opacity=0.45),
          *cels.soft(cels.ellipse((0.21, 0.53), 0.03, 0.03), SKIN_SHADE, spread=0.03, opacity=0.5),
          *cels.soft(band_of([(-0.14, 0.462), (-0.07, 0.452), (0.0, 0.46)], 0.018), SKIN_SHADE, spread=0.02,
                     opacity=0.18),
          *cels.soft(cels.ellipse((0.17, 0.287), 0.014, 0.0045, rotate=-8), SKIN_DEEP, spread=0.006, opacity=0.75),
          *cels.soft(cels.ellipse((0.058, 0.177), 0.008, 0.006), SKIN_DEEP, spread=0.008, opacity=0.45),
          *cels.soft([(-0.29, 0.28), (-0.20, 0.17), (-0.10, 0.10), (-0.20, 0.25), (-0.27, 0.36)], SKIN_DEEP,
                     spread=0.04, opacity=0.5),
          mask=("skin",))
    d.add("skin_light",
          # the light on the bridge, the tip of the nose, the far cheekbone, the brow, wet
          Fill(band_of([(0.128, 0.50), (0.15, 0.43), (0.18, 0.37), (0.198, 0.338)], 0.011, taper_=(0.5, 0.3)),
               SKIN_LIGHT, opacity=0.9),
          *cels.soft(cels.ellipse((0.208, 0.324), 0.0045, 0.0035), GLINT, spread=0.005, opacity=0.45),
          *cels.soft(cels.ellipse((0.27, 0.45), 0.022, 0.04, rotate=10), SKIN_LIGHT, spread=0.03, opacity=0.6),
          *cels.soft(cels.ellipse((0.15, 0.69), 0.07, 0.035, rotate=8), SKIN_LIGHT, spread=0.05, opacity=0.35),
          *cels.soft(cels.ellipse((0.17, 0.055), 0.022, 0.016), SKIN_LIGHT, spread=0.02, opacity=0.2),
          *cels.soft(cels.ellipse((-0.07, 0.425), 0.04, 0.018, rotate=-10), SKIN_LIGHT, spread=0.03, opacity=0.25),
          Fill(cels.ellipse((0.262, 0.47), 0.004, 0.009, rotate=10), GLINT, opacity=0.7),
          Fill(cels.ellipse((0.20, 0.705), 0.006, 0.0035, rotate=8), GLINT, opacity=0.6),
          mask=("skin",))


def _ear(d):
    """His near ear, in the shade side: rim, the fold inside it, the bowl, the lobe."""
    outline = [(-0.292, 0.548), (-0.33, 0.566), (-0.372, 0.55), (-0.398, 0.505), (-0.402, 0.445), (-0.39, 0.385),
               (-0.37, 0.335), (-0.342, 0.302), (-0.312, 0.30), (-0.292, 0.325), (-0.288, 0.37), (-0.296, 0.42),
               (-0.288, 0.47)]
    ear = fill(outline, cels.mix(SKIN_SHADE, SKIN_FLUSH, 0.35))
    d.add("ear", ear)
    d.add("ear_form",
          Fill(band_of([(-0.30, 0.545), (-0.335, 0.555), (-0.372, 0.536), (-0.388, 0.49), (-0.388, 0.43),
                        (-0.372, 0.37)], 0.018, taper_=(0.2, 0.4)) + [0.008, -0.006], SKIN_DEEP, opacity=0.8),
          fill([(-0.318, 0.47), (-0.345, 0.468), (-0.35, 0.42), (-0.335, 0.38), (-0.31, 0.37), (-0.302, 0.41)],
               SKIN_DEEP),
          *cels.soft(cels.ellipse((-0.36, 0.43), 0.012, 0.045, rotate=-8), SKIN_SHADE, spread=0.015, opacity=0.6),
          *cels.soft(cels.ellipse((-0.33, 0.325), 0.022, 0.018), SKIN_FLUSH, spread=0.02, opacity=0.5),
          mask=("ear",))
    d.add("ear_lines",
          *ink(outline[:9], W_IN, LINE_SKIN, seed=51, taper_=(0.15, 0.3)),
          *ink([(-0.315, 0.53), (-0.352, 0.52), (-0.37, 0.47), (-0.365, 0.40), (-0.345, 0.36)], W_FINE, LINE_SKIN,
               seed=52, taper_=(0.3, 0.4), tip=0.0),
          *ink([(-0.30, 0.42), (-0.312, 0.40), (-0.31, 0.37)], W_FINE, LINE_SKIN, seed=53, tip=0.0))


def _eyes(d, eyes):
    """Almond eyes at a man's size: a lid with thickness and its crease, a soft iris with one sharp light, a quiet
    lash line; both looking to the right, at her."""
    common = dict(open=eyes, white=WHITE, white_shade=WHITE_SHADE, shade=0.5, iris_dark=IRIS_DARK, iris_light=IRIS,
                  pupil_color="#0c0809", light=GLINT, ink=INK, crease=0.0)
    near = Eye(center=(-0.058, 0.502), width=0.158, side=-1, height=0.285, tilt=0.06, peak=0.42, flat=0.75,
               lower=0.36, look=(-0.1, -0.005), iris=0.215, iris_tall=1.1, pupil=0.36, lash=0.05, lash_inner=0.3,
               flick=(0.035, 30.0), lower_lash=(0.62, 1.0, 0.011), lights=((-0.32, 0.36, 0.17),), **common)
    far = Eye(center=(0.226, 0.505), width=0.094, side=1, height=0.39, tilt=0.07, peak=0.55, flat=0.75, lower=0.36,
              look=(0.16, -0.005), iris=0.235, iris_tall=1.45, pupil=0.36, lash=0.055, lash_inner=0.4,
              flick=(0.03, 30.0), lower_lash=(0.62, 1.0, 0.014), lights=((-0.3, 0.36, 0.2),), **common)
    for e, p in ((near, "near_"), (far, "far_")):
        d.eye(e, p)
        up, lo = e.lids()
        h = e.height
        # the white turns from us at the corners; a soft light low in the iris
        cx, cy = 0.5 + e.look[0], e.tilt * 0.5 + h * 0.18 + e.look[1]
        d.add(p + "eye_iris",
              *cels.soft(e._to(cels.ellipse((0.03, e.tilt * 0.1), 0.16, h * 0.9)), WHITE_SHADE, spread=0.25 * e.width,
                         opacity=0.6),
              *cels.soft(e._to(cels.ellipse((0.97, e.tilt * 0.9), 0.16, h * 0.9)), WHITE_SHADE, spread=0.25 * e.width,
                         opacity=0.7),
              *cels.soft(e._to(cels.ellipse((cx, cy - e.iris * 0.45), e.iris * 0.55, e.iris * e.iris_tall * 0.35)),
                         "#8c6247", spread=0.18 * e.width, opacity=0.55),
              mask=(p + "eye_white",))
        # the iris's rim, darker than its middle
        ring = e._to(cels.ellipse((cx, cy), e.iris, e.iris * e.iris_tall, n=64))
        d.add(p + "eye_iris", Line(ring, 0.03 * e.width, IRIS_DARK, np.ones(len(ring)), True, 0.8),
              mask=(p + "eye_white",))
        d.add(p + "eye_light",
              *cels.soft(e._to(cels.ellipse((cx + e.iris * 0.35, cy - e.iris * 0.45), e.iris * 0.22,
                                            e.iris * e.iris_tall * 0.13)), "#c9b6a6", spread=0.06 * e.width,
                         opacity=0.5),
              mask=(p + "eye_white",))
        if eyes > 0.3:
            # the upper lid's thickness: skin above the lash line to the crease, which the lid folds into
            crease = up[int(len(up) * 0.12):int(len(up) * 0.95)] + [0.0, h * 0.42]
            lidband = np.vstack([up[int(len(up) * 0.1):] + [0.0, h * 0.08], crease[::-1]])
            d.add(p + "eye_lid", *cels.soft(e._to(lidband), SKIN_FLUSH, spread=0.12 * e.width, opacity=0.35),
                  *ink(e._to(crease), 0.022 * e.width, LINE_SKIN, seed=61, taper_=(0.4, 0.3), tip=0.0, opacity=0.8),
                  mask=("skin",))
        # the lower lid's rim and the tear duct at the inner corner
        low = lo[int(len(lo) * 0.08):int(len(lo) * 0.62)] + [0.0, -h * 0.05]
        d.add(p + "eye_lines", *ink(e._to(low), 0.016 * e.width, LINE_SKIN, seed=62, taper_=(0.5, 0.5), tip=0.0,
                                    opacity=0.6),
              Fill(e._to(cels.ellipse((0.035, e.tilt * 0.02 + h * 0.02), 0.035, h * 0.16)), SKIN_FLUSH, opacity=0.8))


def _features(d, head, eyes):
    knit = (1.0 - min(eyes, 1.0)) / 0.25          # 0 as drawn, 1 narrowed to 0.75
    # ---- brows: low over the eyes, hair drawn in strokes; they draw down and in as he narrows his eyes
    dyi, dyo = -0.012 * knit, -0.004 * knit
    near_b = [(0.035, 0.552 + dyi), (-0.02, 0.575 + dyi), (-0.08, 0.588 + dyo), (-0.14, 0.59 + dyo),
              (-0.195, 0.575 + dyo)]
    far_b = [(0.158, 0.552 + dyi), (0.205, 0.575 + dyi), (0.25, 0.592 + dyo), (0.29, 0.598 + dyo)]
    brows = []
    for pts, w, seed in ((near_b, 0.026, 71), (far_b, 0.022, 72)):
        C = cels.spline(pts)
        u = np.linspace(0, 1, len(C))
        wid = w * (0.7 + 0.5 * np.sin(np.clip(u * 1.4, 0, 1) * math.pi / 2)) * cels.taper(C, 0.05, 0.45, tip=0.15)
        brows += cels.soft(cels.ribbon(C + [0.0, 0.002], wid * 0.8), HAIR, spread=0.006, opacity=0.85, smooth=False)
        # the hairs: up at the brow's head, lying over toward its tail along the rest
        tang = np.gradient(C, axis=0)
        tang /= np.linalg.norm(tang, axis=1, keepdims=True)
        lean = (0.004 + 0.03 * u[:, None] ** 0.6) * tang
        top, bot = cels.offset(C, wid / 2) + lean, cels.offset(C, -wid / 2)
        brows += cels.strands(bot, top, 30, width=0.003, color=LINE_HAIR, seed=seed, reach=(0.0, 1.0), jitter=0.8,
                              bow=0.12, opacity=(0.6, 1.0))
    # the old scar: a pale seam through his right brow, the hair parted over it, on down toward the lid
    scar = band_of([(-0.098, 0.642), (-0.105, 0.60), (-0.116, 0.556), (-0.124, 0.535)], 0.012, taper_=(0.35, 0.45))
    d.add("brows", *brows, Fill(scar, "#d2b6aa"),
          *ink([(-0.093, 0.642), (-0.101, 0.60), (-0.111, 0.556), (-0.118, 0.54)], W_FINE, LINE_SKIN, seed=73,
               opacity=0.55, tip=0.0, taper_=(0.4, 0.4)))
    if knit > 0:
        d.add("brows", *ink([(0.075, 0.585), (0.085, 0.56), (0.088, 0.54)], W_FINE, LINE_SKIN, seed=74,
                            opacity=0.6 * min(knit, 1.0), tip=0.0, taper_=(0.5, 0.5)))

    # ---- nose: the wing and the nostril, a broken line down the shade side of the bridge
    lines = [
        *ink([(0.108, 0.515), (0.13, 0.455), (0.155, 0.40)], W_FINE, LINE_SKIN, seed=81, opacity=0.5, tip=0.0,
             taper_=(0.5, 0.5)),
        *ink([(0.153, 0.338), (0.138, 0.32), (0.14, 0.299)], W_IN * 0.85, LINE_SKIN, seed=82, taper_=(0.35, 0.45),
             tip=0.0, opacity=0.8),
        *ink([(0.188, 0.292), (0.205, 0.297), (0.214, 0.31)], W_FINE, LINE_SKIN, seed=83, opacity=0.7, tip=0.0),
        # mouth: the parting of the lips, darkest toward us, the corners pressed; the lower lip's lower edge, faint
        *ink([(0.052, 0.181), (0.085, 0.176), (0.12, 0.179), (0.148, 0.182), (0.172, 0.177), (0.198, 0.171),
              (0.214, 0.166)], W_IN * 1.1, LINE_SKIN, seed=84, taper_=(0.3, 0.45), tip=0.05, amount=0.35),
        *ink([(0.105, 0.143), (0.14, 0.137), (0.175, 0.142)], W_FINE, LINE_SKIN, seed=85, opacity=0.35, tip=0.0,
             taper_=(0.5, 0.5)),
        # the fold from the nose's wing toward the mouth, barely there at his age; the philtrum's near ridge
        *ink([(0.13, 0.30), (0.10, 0.25), (0.07, 0.21)], W_FINE, LINE_SKIN, seed=86, opacity=0.12, tip=0.0,
             taper_=(0.5, 0.5)),
        *ink([(0.168, 0.278), (0.162, 0.245), (0.16, 0.215)], W_FINE, LINE_SKIN, seed=87, opacity=0.14, tip=0.0,
             taper_=(0.5, 0.5)),
    ]
    lips = [
        # the upper lip faces down, in its own shade; the lower catches the sky, wet
        fill([(0.055, 0.181), (0.10, 0.196), (0.138, 0.205), (0.155, 0.199), (0.172, 0.205), (0.20, 0.192),
              (0.214, 0.167), (0.172, 0.177), (0.12, 0.179)], LIP_SHADE, opacity=0.32),
        fill([(0.07, 0.176), (0.10, 0.158), (0.145, 0.147), (0.185, 0.152), (0.21, 0.166), (0.17, 0.174),
              (0.12, 0.176)], LIP, opacity=0.3),
        *cels.soft(cels.ellipse((0.152, 0.158), 0.013, 0.0035, rotate=-4), GLINT, spread=0.007, opacity=0.32),
    ]
    d.add("lips", *lips, mask=("skin",))
    # the contour: lit and broken down the far side, darker along the jaw in shade
    far = cels.between(head, TEMPLE, CHIN)
    jaw = cels.between(head, CHIN, EAR)
    lines += [
        *ink(far, W_OUT * 0.8, LINE_SKIN, seed=88, gaps=((0.0, 0.1), (0.36, 0.52)), taper_=(0.05, 0.08), tip=0.3,
             amount=0.3),
        *ink(jaw, W_OUT, LINE_JAW, seed=89, taper_=(0.05, 0.2), tip=0.4),
    ]
    d.add("face_lines", *lines)


# ---------------------------------------------------------------------------------------------------- rain on him

def bead(c, r, base, *, stretch=1.15) -> list:
    """Water standing on skin, as it reads close: a clear body a shade darker than the skin under it, a sharp point
    of the sky's light at its top and the light it gathers glowing in its lower edge; no outline."""
    c = np.asarray(c, float)
    return [Fill(cels.ellipse(c, r, r * stretch, n=24), cels.mix(base, SKIN_DEEP, 0.35), opacity=0.35),
            Fill(cels.arc(c, r * 0.8, r * stretch * 0.8, 200, 340, n=16).tolist()
                 + cels.arc(c, r * 0.55, r * stretch * 0.5, 340, 200, n=16).tolist(), SKIN_LIGHT, opacity=0.55),
            Fill(cels.ellipse(c + [-0.3 * r, 0.4 * r * stretch], 0.28 * r, 0.32 * r, n=12), GLINT, opacity=0.95)]


def _wet(d, t):
    """Beads on his skin, a drop running down the far cheek through the close-up, a drip off his chin."""
    for (x, y, r), base in (((-0.165, 0.27, 0.0065), SKIN_SHADE), ((0.04, 0.665, 0.0055), SKIN),
                            ((0.245, 0.245, 0.0045), SKIN), ((-0.03, 0.30, 0.0042), SKIN_SHADE)):
        d.add("wet", bead((x, y), r, base))
    run = np.clip((t - 1.6) / 1.3, 0.0, 1.0) ** 1.6
    path = cels.spline([(0.262, 0.72), (0.262, 0.60), (0.278, 0.47), (0.264, 0.36), (0.24, 0.25)])
    s_ = cels.lengths(path)
    k = int(np.searchsorted(s_, run * s_[-1]))
    head_at = path[min(k, len(path) - 1)]
    if k > 2:
        trail = path[:k]
        d.add("wet", Line(trail, 0.004, GLINT, cels.taper(trail, 0.6, 0.1, tip=0.0), opacity=0.45))
    d.add("wet", bead(head_at, 0.0072, SKIN, stretch=1.5))
    d.add("drips", cels.drip((0.128, -0.002), t, period=1.7, r=0.0075, fall=0.32, phase=0.15, body=WATER,
                             light=GLINT, ink=LINE_SKIN, opacity=0.85))


# ---------------------------------------------------------------------------------------------------- hair, band

CAP = [(0.31, 0.84), (0.335, 0.95), (0.255, 1.075), (0.07, 1.152), (-0.17, 1.152), (-0.38, 1.07), (-0.48, 0.91),
       (-0.488, 0.72), (-0.458, 0.56), (-0.425, 0.45), (-0.372, 0.40), (-0.385, 0.47), (-0.372, 0.535),
       (-0.315, 0.567), (-0.282, 0.556), (-0.274, 0.47), (-0.255, 0.468), (-0.244, 0.56), (-0.236, 0.66),
       (-0.20, 0.79), (0.0, 0.83)]
# the hair over the band runs back over the skull to the tie between these two lines (front to nape): just above the
# band, and the silhouette; the hair under the band, over the ear, between the next two
FLOW_LOW = [(0.322, 0.857), (0.10, 0.884), (-0.15, 0.878), (-0.38, 0.848), (-0.47, 0.72), (-0.447, 0.56),
            (-0.405, 0.452)]
FLOW_HIGH = [(0.337, 0.935), (0.27, 1.062), (0.07, 1.152), (-0.17, 1.152), (-0.38, 1.07), (-0.48, 0.91),
             (-0.488, 0.72), (-0.457, 0.56), (-0.412, 0.458)]
SIDE_HIGH = [(-0.20, 0.785), (-0.31, 0.772), (-0.41, 0.72), (-0.44, 0.60), (-0.41, 0.465)]
SIDE_LOW = [(-0.238, 0.665), (-0.275, 0.585), (-0.33, 0.56), (-0.385, 0.52), (-0.402, 0.452)]


def flow(low, high, n: int = 240):
    """Points on the hair's run between two lines, `at(u, s)`: u 0 (`low`) to 1 (`high`) across, s 0 (front) to 1
    (the tie) along."""
    L, H = cels.resample(cels.spline(low), n), cels.resample(cels.spline(high), n)

    def at(u, s):
        x = np.clip(np.asarray(s, float) * (n - 1), 0, n - 1)
        i = np.floor(x).astype(int)
        j = np.minimum(i + 1, n - 1)
        f = (x - i)[:, None]
        lo, hi = L[i] + (L[j] - L[i]) * f, H[i] + (H[j] - H[i]) * f
        return lo + (hi - lo) * np.asarray(u, float).reshape(-1, 1)
    return at


def lock_along(at, ua, ub, s0, s1, *, drift=0.0, n=90, front=0.07, back=0.1, root=0.45):
    """A lock lying along the hair's run from s0 to s1 between u = ua and ub (both moving `drift` across by its
    end: a clump crossing its neighbours): the two sides (front to back) of a shape that narrows to `root` of its
    width at the front and to a point at the back."""
    s = np.linspace(s0, s1, n)
    g_ = drift * (s - s0) / max(s1 - s0, 1e-6)
    A, B = at(ua + g_, s), at(ub + g_, s)
    m = (A + B) / 2
    e = np.clip((s - s0) / front, 0, 1)
    g = np.clip((s1 - s) / back, 0, 1)
    w = (root + (1 - root) * np.sin(e * math.pi / 2)) * np.sin(g * math.pi / 2) ** 0.7
    return m + (A - m) * w[:, None], m + (B - m) * w[:, None], s


def _locks(d, layer, at, spec, *, seed, light):
    """Wet clumps lying side by side along a run of hair, lowest first so each lies over the one under it: each a
    slightly different dark, the crevice along its lower edge, the sky caught in narrow broken streaks along it where
    the run turns up to the light (`light(u) -> s`), its parting drawn as a tapered line, a hair or two in it."""
    rng = np.random.default_rng(seed)
    for k, (ua, ub, s0, s1, *rest) in enumerate(spec):
        A, B, s = lock_along(at, ua, ub, s0, s1, drift=rest[0] if rest else 0.0)
        n = len(s)
        tone = HAIR if rng.uniform() < 0.55 else HAIR_MID
        pieces = [Fill(np.vstack([A, B[::-1]]), tone)]
        if rng.uniform() < 0.65:     # not every clump shows a crevice under it
            crev = A + (B - A) * rng.uniform(0.12, 0.28)
            i0, i1 = int(n * rng.uniform(0.0, 0.25)), int(n * rng.uniform(0.6, 1.0))
            pieces.append(Fill(np.vstack([A[i0:i1], crev[i0:i1][::-1]]), HAIR_SHADE,
                               opacity=float(rng.uniform(0.6, 0.95))))
        sc = light((ua + ub) / 2)
        for a_, b_ in ((sc - 0.09, sc - 0.015), (sc + 0.01, sc + 0.07 + rng.uniform(0, 0.04))):
            i, j = int(np.searchsorted(s, a_ + rng.uniform(-0.01, 0.01))), int(np.searchsorted(s, b_))
            if j - i > 3:
                f = rng.uniform(0.55, 0.75)
                c = (A + (B - A) * f)[i:j]
                w = np.linalg.norm(B - A, axis=1)[i:j] * rng.uniform(0.12, 0.2)
                pieces.append(Fill(cels.ribbon(c, w * cels.taper(c, 0.45, 0.45, tip=0.0)), HAIR_SHEEN,
                                   opacity=float(rng.uniform(0.55, 0.8))))
                if rng.uniform() < 0.5:
                    pieces.append(Line(c, 0.0022, HAIR_GLINT, cels.taper(c, 0.5, 0.5, tip=0.0), False, 0.75))
        if rng.uniform() < 0.75:
            part = A[int(n * rng.uniform(0.02, 0.3)):int(n * rng.uniform(0.5, 0.95))]
            pieces.append(Line(part, float(rng.uniform(0.0025, 0.004)), LINE_HAIR,
                               cels.taper(part, 0.3, 0.4, tip=0.0) * cels.pressure(part, seed=k), False,
                               float(rng.uniform(0.6, 0.95))))
        for f in rng.uniform(0.35, 0.85, 2):
            c = (A + (B - A) * f)[int(n * rng.uniform(0.05, 0.3)):int(n * rng.uniform(0.6, 0.95))]
            if len(c) > 3:
                pieces.append(Line(c, 0.002, LINE_HAIR, cels.taper(c, 0.4, 0.4, tip=0.0), False, 0.5))
        d.add(layer, *pieces)


def _hair(d, gust):
    """Soaked to his skull and drawn back to the tie at the nape in wet clumps: darker gaps between them, the sky
    caught in narrow streaks along the run where the crown turns up to it, a few clumps lifting or splitting at the
    crown and the back, the sideburn in front of the ear."""
    # under the clumps: the gaps between them, dark; its back and top edges broken into their points
    top = cels.ragged(cels.offset(cels.spline(CAP[2:6]), 0.009), 0.014, 9, seed=31, vary=0.8, sharp=0.5)
    back = cels.ragged(cels.spline(CAP[5:10]), 0.022, 6, seed=21, vary=0.7, sharp=0.6)
    rest = cels.spline(CAP[9:] + CAP[:3], corners=(1, 6, 7))
    cap = Fill(np.vstack([top, back[1:], rest[1:-1]]), HAIR_SHADE)
    d.add("hair", cap)

    over = flow(FLOW_LOW, FLOW_HIGH)
    # the clumps over the band: lowest first; each starts at its own place along the front (an uneven, plastered
    # hairline) and runs back toward the tie
    bounds = [0.0, 0.07, 0.21, 0.28, 0.44, 0.52, 0.66, 0.8, 0.87, 1.0]
    rng = np.random.default_rng(17)
    spec = [(bounds[i] - 0.015 * (i > 0), bounds[i + 1] + 0.012, float(rng.uniform(0.0, 0.08)),
             float(rng.uniform(0.8, 1.0)), 0.0) for i in range(len(bounds) - 1)]
    # two clumps lying across the others
    spec += [(0.36, 0.47, 0.06, 0.7, -0.12), (0.6, 0.68, 0.15, 0.85, 0.1)]
    _locks(d, "hair_locks", over, spec, seed=5, light=lambda u: 0.08 + 0.22 * u)
    # the hair under the band, over the ear, drawn back the same way
    side = flow(SIDE_LOW, SIDE_HIGH)
    _locks(d, "hair_locks", side, [(0.0, 0.36, 0.0, 0.95), (0.3, 0.7, 0.04, 1.0), (0.64, 1.0, 0.0, 1.0)], seed=6,
           light=lambda u: 0.12)
    # the sideburn, combed down in front of the ear
    clump(d, "hair_locks", (-0.236, 0.70), (-0.212, 0.72), (-0.262, 0.468), bow=0.04, shade=0.5, seed=60,
          width=W_FINE * 1.2)
    # a few clumps lifting off the crown and splitting at the back, where the wind has begun to work at them
    sw = 2.0 * gust
    for k, (a, b, tip, sp) in enumerate([
        ((-0.02, 1.152), (0.05, 1.15), (-0.11, 1.182), 2),
        ((-0.20, 1.148), (-0.13, 1.153), (-0.27, 1.175), 1),
        ((-0.43, 1.0), (-0.40, 1.04), (-0.515, 0.985), 2),
        ((-0.475, 0.86), (-0.47, 0.92), (-0.53, 0.83), 1),
    ]):
        clump(d, "hair_locks", a, b, tip, bow=0.08, curl=0.05, shade=0.5, sway=sw * (1 + 0.2 * k), seed=120 + k,
              width=W_FINE * 1.2, split=sp, spread=0.018, glint=(0.15, 0.4) if k < 2 else None)
    # the back of the head turns from the light
    ridge = cels.spline([(-0.27, 1.17), (-0.22, 1.02), (-0.20, 0.90), (-0.22, 0.80)])
    d.add("hair_form",
          *cels.soft(np.vstack([[(-0.62, 1.22)], cels.ragged(ridge, -0.04, 7, seed=5, vary=0.6),
                                [(-0.30, 0.62), (-0.36, 0.38), (-0.62, 0.38)]]), HAIR_SHADE, spread=0.05, opacity=0.7,
                     smooth=False),
          mask=("hair", "hair_locks"))
    # the silhouette, broken where the light is on it; fine hairs lifting off the crown
    lines = ink(cels.between(cap.points, CAP[0], CAP[10]), W_IN, LINE_HAIR, seed=110, taper_=(0.05, 0.1), tip=0.4,
                gaps=((0.08, 0.16), (0.3, 0.36)), amount=0.4)
    sw = 3.0 * gust
    for k, (root, tip) in enumerate((((-0.06, 1.155), (-0.15, 1.186)), ((0.03, 1.152), (-0.04, 1.183)),
                                     ((-0.30, 1.11), (-0.40, 1.13)), ((0.20, 1.10), (0.16, 1.137)))):
        tip = cels.bend([tip], root, sw * (1 + 0.3 * k), power=1.0)[0]
        C = cels.spline([root, (np.asarray(root) + tip) / 2 + [0.0, 0.008], tip])
        lines.append(Line(C, 0.0024, LINE_HAIR, cels.taper(C, 0.1, 0.7, tip=0.0), False, 0.8))
    d.add("hair_lines", *lines)


def _band(d, t):
    """The band round his brow, soaked cloth: soft uneven edges a little frayed, pinched and creased where it turns
    back round his head, shallow wrinkles, darker where the rain has soaked it most; tied behind in a knot."""
    n = 140
    top = cels.resample(cels.spline([(-0.46, 0.84), (-0.33, 0.853), (-0.2, 0.866), (0.05, 0.874), (0.315, 0.852)]), n)
    bot = cels.resample(cels.spline([(-0.46, 0.775), (-0.33, 0.79), (-0.2, 0.80), (0.05, 0.808), (0.318, 0.786)]), n)
    u = np.linspace(0, 1, n)
    turn = np.exp(-((u - 0.3) / 0.05) ** 2)            # where it turns back round the head toward us
    top[:, 1] += -0.009 * turn + 0.0032 * (cels.pressure(top, amount=1.0, waves=7, seed=1) - 1)
    bot[:, 1] += 0.004 * turn + 0.003 * (cels.pressure(bot, amount=1.0, waves=6, seed=2) - 1)
    band = Fill(np.vstack([top, bot[::-1]]), BAND)
    d.add("band", band)
    xc = float(top[int(0.3 * n), 0])
    ty, by = float(top[int(0.3 * n), 1]), float(bot[int(0.3 * n), 1])
    rng = np.random.default_rng(23)
    form = [
        # round the side toward us it turns from the light
        fill([(-0.5, 0.70), (xc + 0.02, 0.70), (xc + 0.05, 0.90), (-0.5, 0.90)], BAND_SHADE, corners=(0, 1, 2, 3)),
        *cels.soft([(xc + 0.02, 0.70), (xc + 0.2, 0.70), (xc + 0.22, 0.90), (xc + 0.05, 0.90)], BAND_SHADE,
                   spread=0.1, opacity=0.45, smooth=False),
        # its lower edge rolls under
        Fill(cels.ribbon(bot + [0.0, 0.009], 0.018 * (0.7 + 0.3 * np.sin(u * 9))), BAND_SHADE, opacity=0.7),
        # pinched where it turns: a fold dragged across it
        fill([(xc - 0.012, ty + 0.01), (xc + 0.014, ty + 0.01), (xc + 0.004, by - 0.01), (xc - 0.024, by - 0.01)],
             LINE_BAND, corners=(0, 1, 2, 3), opacity=0.55),
        *cels.soft([(xc + 0.014, ty), (xc + 0.05, ty), (xc + 0.03, by), (xc + 0.004, by)], BAND_LIGHT, spread=0.02,
                   opacity=0.35, smooth=False),
        # soaked darker in patches
        *[q for c, r in (((0.12, 0.83), 0.03), ((-0.06, 0.84), 0.025), ((0.26, 0.822), 0.02))
          for q in cels.soft(cels.ellipse(c, r, r * 0.45, rotate=float(rng.uniform(-20, 20))), BAND_SHADE,
                             spread=0.02, opacity=0.3)],
        # the sky on the front of it, soft, broken by the wrinkles
        *cels.soft([(-0.02, 0.862), (0.10, 0.866), (0.24, 0.85), (0.24, 0.838), (0.10, 0.85), (-0.02, 0.848)],
                   BAND_LIGHT, spread=0.016, opacity=0.4),
    ]
    wrinkles = []
    for k, x in enumerate((-0.04, 0.075, 0.115, 0.255)):
        y0 = float(np.interp(x, top[:, 0], top[:, 1])) - 0.004
        y1 = float(np.interp(x, bot[:, 0], bot[:, 1])) + 0.012 + rng.uniform(0, 0.02)
        lean = rng.uniform(0.008, 0.028) * (1 if k % 2 else -1)
        P = [(x, y0), (x + lean * 0.5, (y0 + y1) / 2), (x + lean, y1)]
        wrinkles += ink(P, W_FINE, LINE_BAND, seed=140 + k, taper_=(0.4, 0.5), tip=0.0,
                        opacity=float(rng.uniform(0.25, 0.45)))
        form += cels.soft(band_of([(x - 0.006, y0), (x - 0.006 + lean * 0.5, (y0 + y1) / 2), (x - 0.006 + lean, y1)],
                                  0.012), BAND_SHADE, spread=0.008, opacity=0.35)
        form += cels.soft(band_of([(x + 0.007, y0), (x + 0.007 + lean * 0.5, (y0 + y1) / 2), (x + 0.007 + lean, y1)],
                                  0.01), BAND_LIGHT, spread=0.008, opacity=0.25)
    d.add("band_form", *form, mask=("band",))
    # frayed threads at its edges
    threads = []
    for k in range(9):
        on_top = k % 2 == 0
        E = top if on_top else bot
        i = int(rng.uniform(0.06, 0.96) * n)
        nrm = cels.normals(E)[i] * (1 if on_top else -1)
        dirn = nrm + rng.uniform(-0.6, 0.6) * np.array([1.0, 0.0])
        dirn /= np.linalg.norm(dirn)
        L = rng.uniform(0.006, 0.014)
        threads.append(Line(np.array([E[i], E[i] + dirn * L * 0.5 + [0.0, -0.002], E[i] + dirn * L]), 0.0018,
                            LINE_BAND, np.array([1.0, 0.6, 0.0]), False, 0.7))
    # the knot: the band's end gathered and tied over itself, a wrap crossing it, folds pinched into the lobes
    k_ = np.array(KNOT)
    lobes = fill([k_ + o for o in ((-0.034, 0.008), (-0.03, 0.036), (-0.01, 0.054), (0.012, 0.046), (0.028, 0.03),
                                   (0.026, 0.008), (0.036, -0.012), (0.024, -0.036), (-0.004, -0.05),
                                   (-0.028, -0.032))], cels.mix(BAND, BAND_SHADE, 0.45))
    wrap_c = [k_ + (-0.032, 0.026), k_ + (-0.004, 0.006), k_ + (0.03, -0.016)]
    wrap = Fill(band_of(wrap_c, 0.024, taper_=(0.15, 0.15)), cels.mix(BAND, BAND_SHADE, 0.2))
    knot = [
        lobes,
        Fill(band_of([k_ + (-0.022, 0.036), k_ + (0.0, 0.032), k_ + (0.018, 0.02)], 0.012), BAND_SHADE, opacity=0.8),
        Fill(band_of([k_ + (-0.018, -0.012), k_ + (0.0, -0.028), k_ + (0.014, -0.036)], 0.012), BAND_SHADE,
             opacity=0.8),
        wrap,
        Fill(band_of([k_ + (-0.028, 0.034), k_ + (0.0, 0.016), k_ + (0.026, -0.006)], 0.006), BAND_LIGHT,
             opacity=0.55),
        *ink([k_ + (-0.022, 0.036), k_ + (0.0, 0.03), k_ + (0.018, 0.018)], W_FINE, LINE_BAND, seed=150, tip=0.0,
             opacity=0.8),
        *ink([k_ + (-0.018, -0.014), k_ + (0.0, -0.03), k_ + (0.014, -0.038)], W_FINE, LINE_BAND, seed=151, tip=0.0,
             opacity=0.8),
        *ink(cels.offset(cels.spline(wrap_c), 0.012), W_FINE, LINE_BAND, seed=152, tip=0.0),
        *ink(cels.offset(cels.spline(wrap_c), -0.012), W_FINE, LINE_BAND, seed=153, tip=0.0),
        *ink(np.vstack([lobes.points, lobes.points[:1]]), W_IN, LINE_BAND, seed=154, taper_=(0.02, 0.02), tip=0.6),
    ]
    edge = [*ink(top, W_IN, LINE_BAND, seed=155, gaps=((0.55, 0.66), (0.78, 0.84)), taper_=(0.02, 0.05), tip=0.5,
                 amount=0.4),
            *ink(bot, W_IN, LINE_BAND, seed=156, taper_=(0.02, 0.05), tip=0.5, amount=0.4),
            *ink([top[-1], (0.322, 0.82), bot[-1]], W_FINE, LINE_BAND, seed=157, tip=0.3)]
    d.add("band_lines", *edge, *wrinkles, *threads, *knot)


def _strands(d, gust, flick):
    """Wet locks loose round his face: a few hairs plastered to his brow from under the band, one over the far
    temple, narrower ones hanging past the outer brow and the ear, their ends splitting; stray hairs apart from them."""
    for k, pts in enumerate(([(0.075, 0.795), (0.088, 0.745), (0.082, 0.70), (0.09, 0.665)],
                             [(0.105, 0.795), (0.112, 0.76), (0.125, 0.73)],
                             [(0.185, 0.795), (0.198, 0.75), (0.214, 0.715)])):
        C = cels.spline(pts)
        w = (0.0085 - 0.0015 * k) * cels.taper(C, 0.0, 0.8, tip=0.0)
        d.add("skin_light", Fill(cels.ribbon(C + [-0.005, -0.004], w * 1.3), SKIN_SHADE, opacity=0.55),
              mask=("skin",))
        d.add("strands", Fill(cels.ribbon(C, w), HAIR, opacity=0.95),
              Line(C[: len(C) // 2], w.max() * 0.25, HAIR_SHEEN, cels.taper(C[: len(C) // 2], 0.4, 0.4, tip=0.0),
                   False, 0.6))
    for k, (a, b, tip, bow, curl, swy, glint, split) in enumerate([
        ((0.29, 0.855), (0.312, 0.848), (0.316, 0.69), 0.04, 0.05, 0.5, (0.2, 0.5), 2),    # over the far temple
        ((-0.172, 0.80), (-0.142, 0.805), (-0.19, 0.575), 0.05, 0.03, 0.6, (0.12, 0.42), 2),  # past the outer brow
        ((-0.20, 0.80), (-0.175, 0.80), (-0.245, 0.655), 0.06, -0.05, 0.8, (0.15, 0.4), 1),
        ((-0.335, 0.83), (-0.285, 0.84), (-0.305, 0.31), 0.04, -0.03, 0.4, (0.12, 0.45), 3),  # down past the ear
        ((-0.285, 0.836), (-0.25, 0.84), (-0.212, 0.425), 0.05, 0.05, 0.5, (0.2, 0.5), 2),
        ((-0.25, 0.836), (-0.228, 0.835), (-0.262, 0.56), 0.04, -0.06, 0.7, None, 1),
    ]):
        clump(d, "strands", a, b, tip, bow=bow, curl=curl, shade=0.5, sway=swy * (gust + 0.3 * flick),
              glint=glint, seed=150 + k, width=W_FINE * 1.4, split=split, spread=0.02)
    # stray hairs, apart from the locks
    strays = []
    for k, (pts, w) in enumerate((([(-0.155, 0.80), (-0.13, 0.74), (-0.135, 0.68), (-0.12, 0.64)], 0.0026),
                                  ([(-0.30, 0.80), (-0.335, 0.70), (-0.355, 0.60), (-0.35, 0.52)], 0.0024),
                                  ([(-0.23, 0.80), (-0.215, 0.70), (-0.19, 0.62)], 0.0022),
                                  ([(0.30, 0.84), (0.33, 0.79), (0.345, 0.74)], 0.0022))):
        C = cels.wave(cels.spline(pts), 0.004 * (gust + 0.5 * flick), 0.12, k * 1.7, power=1.5)
        strays.append(Line(C, w, LINE_HAIR, cels.taper(C, 0.05, 0.7, tip=0.0), False, 0.9))
    d.add("strands", *strays)


def _rain(d, t):
    """Rain striking his shoulders: on each drawing (on twos) a few drops burst into small crowns of spray."""
    k = int(round(t * 12))
    rng = np.random.default_rng(1000 + k)
    out = []
    for _ in range(3):
        side = rng.uniform() < 0.55
        u = rng.uniform(0.15, 0.95)
        if side:
            p = np.array([0.22 + 0.50 * u, -0.31 - 0.22 * u ** 1.3])
        else:
            p = np.array([-0.38 - 0.42 * u, -0.15 - 0.30 * u ** 1.1])
        s = rng.uniform(0.7, 1.2)
        for a in (-60, -25, 10, 40, 75):
            ang = math.radians(90 + a + rng.uniform(-10, 10))
            dirn = np.array([math.cos(ang), math.sin(ang)])
            q0 = p + dirn * 0.006 * s
            q1 = p + dirn * (0.018 + 0.012 * rng.uniform()) * s
            out.append(Line(np.array([q0, q1]), 0.0028 * s, "#c3cbd9", np.array([0.8, 0.1]), False, 0.7))
        out.append(Fill(cels.ellipse(p + [0.0, 0.002], 0.006 * s, 0.0025 * s), "#c3cbd9", opacity=0.5))
    d.add("fx", *out)


def sheet(t: float) -> cels.Drawing:
    """For cel sheets: t < 1 as drawn, 1..2 the flash at its height, 2.. eyes narrowed after it."""
    if t < 1:
        return closeup(t)
    if t < 2:
        return closeup(t, flash=1.0)
    return closeup(t, eyes=0.72)
