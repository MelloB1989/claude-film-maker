"""Tsuru drawn: the close-up and the wide-shot figure for the standoff, as 2D anime drawings (blender/lib/cels.py),
drawn toward the film end of anime: a believable old face and real materials, painted in cel tones and soft
gradients, with coloured lines (no black ink).

Her design: a small ferrywoman of seventy-odd, silver hair combed back in sections into a twisted bun at the back of
her crown, a plain wooden pin through it, damp wisps loose at the temples; an old face of real structure (sunken
temples, a high cheekbone with the cheek hollowed under it, hooded lids, crow's feet, bags under the eyes, deep folds
from nose to mouth and on down the jowl, thin lips with fine lines over them, loose skin under the chin and the cords
of an old neck); sparse grey brows; calm half-lidded eyes that open sharp (she was the River Demon once); a straw rain
cape (mino) of tied tiers of real straw, its ends clumped wet and dripping, over an indigo kimono with a pale
under-collar, darker where the rain has soaked it; her ferry pole, weathered bamboo, upright in her right hand.

Light: the overcast sky from the upper front on the side she faces (screen left), so her face's front and the far
side of her cape are lit, and the side by the ear, her neck and the near side of the cape turn from it. The shot's
compositing adds rim light and the ambient grade on top: these drawings carry form and material only.

Head units: the chin at (-0.12, 0), the crown at about y = 1.11, the bun and pin up to 1.16; the bust runs down past
y = -1.7. She faces left in three quarters (toward Shinza), her left side to us. `full` is in metres: feet on y = 0,
her body centred on x = 0, facing left.
"""
from __future__ import annotations

import math

import numpy as np

from lib import cels
from lib.cels import Eye, Fill, Line, fill, line

HEAD = 0.21          # metres per head unit

# ---- colours: muted and rain-cooled; lines in a dark of their own material's colour
INK = "#1d1714"
SKIN = "#c6aa9b"
SKIN_LIGHT = "#dbc7ba"
SKIN_SHADE = "#927c79"
SKIN_DEEP = "#5f4c50"
SKIN_WARM = "#b47d71"     # the old blood under her skin: cheeks, nose, ears, knuckles
SKIN_COOL = "#7a7282"     # the cold in the hollows
SKIN_LINE = "#3e2925"     # the skin's contour and features
SKIN_LINE_LIT = "#6b4b42" # ... where the light falls on it (lighter, broken)
AGE = "#6e5049"           # the lines of age: finer and softer
LIP = "#9c716d"
WET = "#f1f4f8"           # the wet gleam on skin
WATER = "#a8b5c7"         # water: beads, drips, runnels
HAIR = "#b3b6bf"
HAIR_LIGHT = "#d2d5dc"
HAIR_SHEEN = "#eceef3"
HAIR_SHADE = "#7b7f8c"
HAIR_DEEP = "#525663"
HAIR_LINE = "#3e3f49"
HAIR_DAMP = "#878b98"
BROW = "#c3c2c6"
BROW_DARK = "#6b676c"
PIN = "#7b5435"
PIN_SHADE = "#4a3222"
PIN_LIGHT = "#a98058"
CLOTH = "#2b344e"
CLOTH_LIGHT = "#3d4866"
CLOTH_SHADE = "#1b2135"
CLOTH_WET = "#141a2b"
CLOTH_LINE = "#0d101d"
UNDER = "#bebcc4"
UNDER_SHADE = "#83838f"
UNDER_LINE = "#3c3c48"
STRAW = "#79684a"
STRAW_LIGHT = "#a39070"
STRAW_PALE = "#c0ae88"
STRAW_SHADE = "#4c4132"
STRAW_DEEP = "#2c251d"
STRAW_WET = "#3a3227"
STRAW_LINE = "#251d16"
CORD = "#3d332a"
CORD_LINE = "#1c1612"
POLE = "#8a8062"
POLE_SHADE = "#575039"
POLE_LIGHT = "#b5aa86"
POLE_LINE = "#2a261c"
GROUND = "#0e1018"
EYE_WHITE = "#cbc4c3"
EYE_WHITE_SHADE = "#8d8388"
IRIS_DARK = "#1e1615"
IRIS = "#5c483f"
EYE_LINE = "#2a1c19"      # the lash line: the darkest line on her
GLINT = "#eef7ff"         # the cold glint in her eyes when she sharpens
IRIS_GLOW = "#aebbe0"     # the irises' cold rim, glinting through the shadow
EYE_SHADOW = "#2b2333"    # the shadow that falls over her eyes from the brow ridge

# how each colour takes a lightning flash (cels.flash): lit ones bleach, shades sink, lines stay
_SHADES = (SKIN_SHADE, SKIN_DEEP, SKIN_COOL, HAIR_SHADE, HAIR_DEEP, HAIR_DAMP, PIN_SHADE, CLOTH, CLOTH_SHADE,
           CLOTH_WET, CLOTH_LIGHT, UNDER_SHADE, STRAW_SHADE, STRAW_DEEP, STRAW_WET, CORD, POLE_SHADE, IRIS, BROW_DARK)
_LINES = (INK, SKIN_LINE, SKIN_LINE_LIT, AGE, HAIR_LINE, CLOTH_LINE, UNDER_LINE, STRAW_LINE, CORD_LINE, POLE_LINE,
          GROUND, IRIS_DARK, EYE_LINE, EYE_SHADOW)
KINDS = {**{c: "shade" for c in _SHADES}, **{c: "ink" for c in _LINES}, GLINT: "lit", IRIS_GLOW: "lit"}

W_OUT = 0.0078       # the contour on the shadow side
W_LIT = 0.0048       # ... on the lit side
W_IN = 0.0046        # features
W_FINE = 0.0032
W_AGE = 0.0027       # wrinkles
W_HAIR = 0.0021      # a strand

CHIN = (-0.12, 0.0)
EAR = (0.28, 0.29)
TEMPLE = (-0.25, 0.86)
BUN = (0.36, 0.995)
BUN_R = (0.13, 0.115)    # the bun's radii
BUN_ROT = -20.0
POLE_GRIP = (-0.66, -0.5)  # the close-up's pole (x) and where her hand grips it (y)
PIN_A, PIN_B = (0.15, 1.135), (0.60, 0.855)


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ink(points, width: float, color=SKIN_LINE, *, seed: int = 0, taper_=(0.25, 0.3), tip: float = 0.0,
        wobble: float = 0.3, opacity: float = 1.0, corners=(), smooth: bool = True) -> Line:
    """A hand-inked line: tapered at both ends, swelling and thinning along its length as a brush does."""
    P = cels.spline(points, corners=corners) if smooth else cels._arr(points)
    w = cels.taper(P, *taper_, tip=tip) * cels.pressure(P, amount=wobble, seed=seed)
    return Line(P, width, color, w, False, opacity)


def broken(points, width: float, color=SKIN_LINE, *, gaps=(), seed: int = 0, **kw) -> list:
    """An inked line with breaks where the light hits it: `gaps` as (from, to) fractions of its length."""
    P = cels.spline(points)
    s = cels.lengths(P)
    u = s / s[-1]
    keep = np.ones(len(P), bool)
    for a, b in gaps:
        keep &= ~((u > a) & (u < b))
    out, run = [], []
    for i, k in enumerate(keep):
        if k:
            run.append(P[i])
        elif len(run) > 3:
            out.append(ink(np.array(run), width, color, seed=seed + len(out), smooth=False, **kw))
            run = []
        else:
            run = []
    if len(run) > 3:
        out.append(ink(np.array(run), width, color, seed=seed + len(out), smooth=False, **kw))
    return out


def blob(center, rx, ry, color, *, spread: float = 0.04, opacity: float = 0.5, rotate: float = 0.0) -> list:
    """A soft airbrushed oval."""
    return cels.soft(cels.ellipse(center, rx, ry, rotate=rotate, n=24), color, spread=spread, opacity=opacity,
                     smooth=False, steps=max(3, min(10, int(round(spread / 0.006)))))


def _thin(d: cels.Drawing, n: int = 7, suffixes=("_fibre", "_shag", "hair_strands", "bun_shade", "brows")):
    """Fine strands drawn with fewer points (they are short and nearly straight): keeps the drawing light enough to
    render many of."""
    for name, L in d.layers.items():
        if not name.endswith(suffixes):
            continue
        for p in L.pieces:
            if isinstance(p, Line) and len(p.points) > n:
                s = cels.lengths(p.points)
                if s[-1] <= 0:
                    continue
                q = np.linspace(0.0, s[-1], n)
                w = p.widths if p.widths is not None else np.ones(len(p.points))
                p.widths = np.interp(q, s, w)
                p.points = np.c_[np.interp(q, s, p.points[:, 0]), np.interp(q, s, p.points[:, 1])]


def head_outline() -> np.ndarray:
    """The head, skin side: down the far contour (the brow ridge, the eye's socket, a high cheekbone, the cheek
    hollowed under it, the mouth's fullness, the chin) to the chin, along the jaw (sagging a little at the jowl) to
    the ear, round the skull."""
    return cels.spline([
        TEMPLE, (-0.283, 0.725), (-0.294, 0.632), (-0.280, 0.552), (-0.291, 0.482), (-0.304, 0.428),
        (-0.288, 0.356), (-0.274, 0.286), (-0.267, 0.218), (-0.250, 0.142), (-0.220, 0.074), (-0.176, 0.022), CHIN,
        (-0.062, 0.008), (0.005, 0.03), (0.06, 0.05), (0.13, 0.095), (0.198, 0.148), (0.243, 0.212), EAR,
        (0.375, 0.45), (0.435, 0.66), (0.355, 0.90), (0.12, 1.01), (-0.12, 0.99),
    ], closed=True, corners=(12,))


def closeup(t: float = 0.0, flash: float = 0.0, eyes: float = 0.55) -> cels.Drawing:
    """The close-up `t` seconds into the shot: the wind in her wisps and the cape's straw, the rain dripping off her;
    `flash` 0..1 a lightning flash's light on her; `eyes` how open her eyes are: 0.55 her calm half-lidded look, 1
    the River Demon's."""
    d = _closeup(t, eyes)
    if flash > 0:
        d.recolor(lambda c: cels.flash(c, flash, KINDS.get(c, "lit")))
    return d


def _closeup(t: float, eyes: float) -> cels.Drawing:
    d = cels.Drawing()
    head = head_outline()
    gust = math.sin(2 * math.pi * t * 0.7 + 0.9)      # the same slow wind as on him, a beat later
    flick = math.sin(2 * math.pi * t * 2.1 + 1.7)
    sharp = _smooth((eyes - 0.55) / 0.45)             # 0 calm .. 1 the demon's look

    # ---- neck: an old woman's, the head carried a little forward
    _neck(d, head)

    # ---- the kimono in the opening of the cape
    _kimono_bust(d, t)

    # ---- the straw cape over her shoulders, open at the front over the collar; her right arm comes out from under
    # its far side, reaching forward to the pole
    def place(P):
        return cels.move(cels._arr(P), POLE_GRIP, scale=0.9, rotate=GRIP)

    # the forearm rising from the elbow at the cape's opening up to the wrist, the sleeve's bag hanging under it
    sleeve = [(-0.41, -0.5), (-0.27, -0.53), (-0.12, -0.62), (-0.04, -0.74), (-0.05, -0.98), (-0.14, -1.22),
              (-0.28, -1.3), (-0.42, -1.12), (-0.46, -0.85), (-0.45, -0.68)]
    folds = [(-0.36, -0.52), (-0.22, -0.56), (-0.1, -0.66), (-0.44, -0.74)]
    cuff = (place([(0.31, 0.0)])[0], 0.04, 0.105, GRIP)
    _cape_bust(d, t, gust, flick, between_far={1: lambda d_: _sleeve(d_, sleeve, folds, cuff, (-0.27, -1.3), t)})

    # ---- the pole, upright in front of her far shoulder, her hand round it
    _pole(d, t, x=POLE_GRIP[0], width=0.15, y0=-1.75, y1=1.45, joints=(-1.2, -0.1, 0.62))
    _hand(d, place, 1.0, t)

    # ---- the face
    _face(d, head, t, eyes, sharp, gust)

    # ---- her hair: combed back from the hairline in sections to the bun, the ear left clear
    _hair_bust(d, t, gust, flick)

    # a breath: the bust rises and settles, the head a little less
    b = 0.0035 * math.sin(2 * math.pi * t / 3.4)
    d.shift(0.0, b)
    _thin(d)
    return d


# ---------------------------------------------------------------------------------------------------- face

def _face(d: cels.Drawing, head, t: float, eyes: float, sharp: float, gust: float):
    d.add("skin", Fill(head, SKIN))
    smile = 1.0 - sharp

    # -- the planes turned from the light: the side of the head back from the cheekbone, under the jaw; the eye
    # sockets under the brow ridge; the side of the nose; under it; the fold from nose to mouth; under the lip
    side = fill([(0.235, 0.80), (0.205, 0.70), (0.19, 0.62), (0.222, 0.54), (0.222, 0.46), (0.2, 0.38),
                 (0.182, 0.30), (0.178, 0.22), (0.17, 0.15), (0.15, 0.09), (0.12, 0.0), (0.5, 0.0), (0.5, 0.8)],
                SKIN_SHADE, corners=(10, 11, 12))
    nose_side = fill([(-0.112, 0.49), (-0.095, 0.44), (-0.11, 0.385), (-0.138, 0.335), (-0.15, 0.31),
                      (-0.158, 0.33), (-0.142, 0.39), (-0.124, 0.45)], SKIN_SHADE, opacity=0.8)
    under_nose = fill([(-0.215, 0.282), (-0.18, 0.268), (-0.145, 0.27), (-0.13, 0.258), (-0.17, 0.245),
                       (-0.205, 0.252)], SKIN_SHADE)
    fold_sh = fill([(-0.13, 0.31), (-0.107, 0.27), (-0.084, 0.215), (-0.068, 0.16), (-0.06, 0.115),
                    (-0.052, 0.13), (-0.06, 0.18), (-0.075, 0.235), (-0.104, 0.29)], SKIN_SHADE, opacity=0.75)
    under_lip = fill([(-0.185, 0.128), (-0.15, 0.112), (-0.105, 0.115), (-0.088, 0.128), (-0.12, 0.122),
                      (-0.155, 0.122)], SKIN_SHADE)
    sockets = [fill([(-0.02, 0.585), (0.06, 0.585), (0.14, 0.575), (0.19, 0.55), (0.185, 0.51), (0.12, 0.535),
                     (0.04, 0.54), (-0.03, 0.52), (-0.06, 0.55)], SKIN_SHADE, opacity=0.75),
               fill([(-0.17, 0.58), (-0.235, 0.585), (-0.278, 0.56), (-0.27, 0.52), (-0.23, 0.535),
                     (-0.17, 0.535), (-0.135, 0.55)], SKIN_SHADE, opacity=0.6)]
    d.add("skin_shade", side, nose_side, under_nose, fold_sh, under_lip, sockets, mask=("skin",))
    # -- the airbrush: cold in the hollows (temple, under the cheekbone, round the eyes), the old warmth in the cheeks,
    # the nose and the ear, the deeper dark by the ear and under the jaw
    d.add("skin_soft",
          blob((0.17, 0.66), 0.07, 0.1, SKIN_COOL, spread=0.08, opacity=0.45),
          blob((-0.275, 0.68), 0.03, 0.07, SKIN_COOL, spread=0.05, opacity=0.35),
          blob((0.12, 0.33), 0.09, 0.05, SKIN_COOL, spread=0.07, opacity=0.4, rotate=35),
          blob((-0.245, 0.34), 0.03, 0.05, SKIN_COOL, spread=0.04, opacity=0.3),
          blob((0.07, 0.43), 0.07, 0.04, SKIN_COOL, spread=0.05, opacity=0.35),
          blob((-0.22, 0.43), 0.035, 0.03, SKIN_COOL, spread=0.03, opacity=0.3),
          blob((0.0, 0.39), 0.08, 0.05, SKIN_WARM, spread=0.07, opacity=0.35),
          blob((-0.25, 0.38), 0.035, 0.04, SKIN_WARM, spread=0.04, opacity=0.3),
          blob((-0.19, 0.31), 0.035, 0.03, SKIN_WARM, spread=0.03, opacity=0.4),
          blob((0.32, 0.36), 0.09, 0.12, SKIN_DEEP, spread=0.1, opacity=0.4),
          # the near cheek's mound and the jowl under it, turning down to the jaw
          blob((0.09, 0.14), 0.09, 0.035, SKIN_COOL, spread=0.07, opacity=0.45, rotate=30),
          blob((0.0, 0.085), 0.055, 0.03, SKIN_SHADE, spread=0.05, opacity=0.4, rotate=20),
          blob((0.12, 0.25), 0.05, 0.08, SKIN_COOL, spread=0.07, opacity=0.3, rotate=-20),
          blob((-0.02, 0.27), 0.05, 0.06, SKIN_LIGHT, spread=0.06, opacity=0.35),
          blob((0.1, 0.07), 0.16, 0.05, SKIN_DEEP, spread=0.07, opacity=0.35, rotate=25),
          blob((-0.1, 0.03), 0.07, 0.03, SKIN_SHADE, spread=0.04, opacity=0.4),
          mask=("skin",))
    # -- the light: the brow, the bridge of the nose, the far cheekbone, the chin; wet gleams on the bones
    d.add("skin_light",
          blob((-0.12, 0.70), 0.12, 0.05, SKIN_LIGHT, spread=0.07, opacity=0.6),
          blob((-0.165, 0.42), 0.012, 0.06, SKIN_LIGHT, spread=0.02, opacity=0.7, rotate=-20),
          blob((-0.262, 0.44), 0.022, 0.035, SKIN_LIGHT, spread=0.03, opacity=0.6),
          blob((-0.19, 0.06), 0.035, 0.025, SKIN_LIGHT, spread=0.03, opacity=0.5),
          blob((-0.125, 0.155), 0.03, 0.008, SKIN_LIGHT, spread=0.012, opacity=0.5),
          mask=("skin",))
    d.add("skin_wet",
          blob((-0.207, 0.318), 0.006, 0.004, WET, spread=0.005, opacity=0.6),
          blob((-0.272, 0.445), 0.003, 0.01, WET, spread=0.005, opacity=0.45),
          blob((-0.1, 0.738), 0.012, 0.003, WET, spread=0.005, opacity=0.35, rotate=4),
          blob((-0.182, 0.055), 0.007, 0.004, WET, spread=0.005, opacity=0.4),
          mask=("skin",))

    # -- the ear: big and long-lobed with age, turned from the light
    ear = fill([(0.272, 0.535), (0.345, 0.568), (0.393, 0.50), (0.392, 0.39), (0.37, 0.305), (0.338, 0.232),
                (0.296, 0.222), (0.273, 0.262)], SKIN_SHADE)
    d.add("ear", ear)
    d.add("ear_shade",
          fill([(0.30, 0.50), (0.35, 0.52), (0.368, 0.44), (0.35, 0.36), (0.322, 0.33), (0.315, 0.40)], SKIN_DEEP),
          blob((0.33, 0.27), 0.03, 0.025, SKIN_WARM, spread=0.03, opacity=0.5),
          blob((0.375, 0.45), 0.02, 0.06, SKIN, spread=0.03, opacity=0.5),
          mask=("ear",))
    d.add("ear_lines",
          ink(np.vstack([ear.points, ear.points[:3]]), W_IN, SKIN_LINE, seed=31, taper_=(0.05, 0.1), tip=0.3),
          ink([(0.31, 0.49), (0.352, 0.51), (0.37, 0.45), (0.355, 0.37), (0.33, 0.335)], W_FINE, SKIN_LINE, seed=32),
          ink([(0.33, 0.33), (0.315, 0.29), (0.32, 0.255)], W_AGE, AGE, seed=33))

    _eyes(d, eyes, sharp)
    _brows(d, sharp, gust)

    # -- nose, mouth and the lines of her age
    nose = [
        # the bridge, faint and broken where the light is on it, into the tip
        *broken([(-0.115, 0.55), (-0.135, 0.48), (-0.165, 0.40), (-0.195, 0.335), (-0.212, 0.30)], W_FINE,
                SKIN_LINE_LIT, gaps=((0.1, 0.45),), seed=40),
        # round the tip and under it
        ink([(-0.198, 0.322), (-0.218, 0.302), (-0.214, 0.283), (-0.195, 0.276)], W_IN, SKIN_LINE, seed=41,
            taper_=(0.3, 0.4)),
        # the nostril and the near wing
        ink([(-0.188, 0.28), (-0.172, 0.274), (-0.158, 0.279)], W_IN * 1.1, SKIN_LINE, seed=42, taper_=(0.4, 0.4)),
        ink([(-0.142, 0.33), (-0.127, 0.305), (-0.133, 0.282), (-0.15, 0.274)], W_FINE, SKIN_LINE, seed=43),
    ]
    mouth = [
        # thin lips: the parting line, its near corner lifting a little, setting flat as she sharpens
        ink([(-0.212, 0.172), (-0.185, 0.164), (-0.15, 0.161), (-0.115, 0.161), (-0.088, 0.164 + 0.006 * smile),
             (-0.072, 0.171 + 0.012 * smile)], W_IN * (1.0 - 0.1 * sharp), SKIN_LINE, seed=44, taper_=(0.2, 0.35),
            tip=0.15),
        # the upper lip's edge, the lower lip's, faint
        ink([(-0.198, 0.182), (-0.17, 0.186), (-0.15, 0.181), (-0.125, 0.185), (-0.098, 0.18)], W_AGE, LIP,
            seed=45, opacity=0.8),
        ink([(-0.18, 0.145), (-0.15, 0.137), (-0.115, 0.14)], W_AGE, AGE, seed=46, opacity=0.7),
    ]
    rng = np.random.default_rng(47)
    lip_lines = []
    for k, x in enumerate(np.linspace(-0.19, -0.1, 7)):
        y0 = 0.188 + rng.uniform(0.0, 0.006)
        lip_lines.append(ink([(x, y0), (x + 0.002, y0 + 0.012 + rng.uniform(0, 0.012))], W_AGE * 0.75, AGE,
                             seed=48 + k, opacity=0.55, taper_=(0.4, 0.5)))
        lip_lines.append(ink([(x + 0.006, 0.152), (x + 0.007, 0.142 - rng.uniform(0, 0.008))], W_AGE * 0.6, AGE,
                             seed=60 + k, opacity=0.4, taper_=(0.4, 0.5)))
    folds = [
        # the fold from the nose's wing round the mouth, on down past it toward the jowl (the marionette line)
        ink([(-0.128, 0.31), (-0.1, 0.27), (-0.075, 0.21), (-0.062, 0.16), (-0.058, 0.115)], W_AGE * 1.7, AGE,
            seed=70, taper_=(0.3, 0.45)),
        ink([(-0.068, 0.15), (-0.055, 0.1), (-0.04, 0.06)], W_AGE * 1.2, AGE, seed=71, taper_=(0.4, 0.5)),
        ink([(-0.205, 0.158), (-0.212, 0.125), (-0.205, 0.09)], W_AGE, AGE, seed=72, taper_=(0.4, 0.5),
            opacity=0.7),
        # the cheekbone's edge, the hollow under it, the jowl
        ink([(0.205, 0.45), (0.15, 0.39), (0.09, 0.335), (0.04, 0.29)], W_AGE * 1.1, AGE, seed=73,
            taper_=(0.45, 0.5), opacity=0.8),
        ink([(0.02, 0.10), (0.05, 0.075), (0.09, 0.07)], W_AGE, AGE, seed=74, opacity=0.7),
        # across the brow: broken, uneven
        *broken([(-0.23, 0.70), (-0.13, 0.712), (-0.02, 0.716), (0.08, 0.708)], W_AGE, AGE,
                gaps=((0.42, 0.5),), seed=75, opacity=0.8),
        *broken([(-0.17, 0.75), (-0.06, 0.758), (0.06, 0.752)], W_AGE * 0.9, AGE, gaps=((0.6, 0.66),), seed=76,
                opacity=0.7),
        ink([(-0.12, 0.792), (-0.03, 0.798), (0.04, 0.794)], W_AGE * 0.8, AGE, seed=77, opacity=0.55),
        # between the brows: faint at rest, furrowed deep as she sharpens
        ink([(-0.082, 0.605), (-0.086, 0.57), (-0.08, 0.535)], W_AGE * (0.8 + 0.7 * sharp), AGE, seed=78,
            opacity=0.35 + 0.65 * sharp),
        ink([(-0.11, 0.6), (-0.114, 0.565), (-0.107, 0.54)], W_AGE * (0.7 + 0.6 * sharp), AGE, seed=79,
            opacity=0.25 + 0.75 * sharp),
        # the flank of the nose's root, creased as she sharpens
        ink([(-0.115, 0.53), (-0.09, 0.515), (-0.065, 0.52)], W_AGE, AGE, seed=80, opacity=sharp),
    ]
    # the contour: heavier on the shadow side round the jaw to the ear, lighter and broken down the lit front
    far = cels.between(head, TEMPLE, CHIN)
    jaw = cels.between(head, CHIN, EAR)
    contour = [
        *broken(far, W_LIT, SKIN_LINE_LIT, gaps=((0.3, 0.37), (0.62, 0.66)), seed=81, taper_=(0.08, 0.04),
                tip=0.3),
        ink(jaw, W_OUT, SKIN_LINE, seed=82, taper_=(0.03, 0.1), tip=0.6, smooth=False),
    ]
    d.add("face_lines", nose, mouth, lip_lines, folds, contour)

    # -- the rain on her face: beads, one running down from the temple
    beads = []
    for (x, y, r) in ((-0.03, 0.665, 0.007), (0.115, 0.725, 0.005), (-0.235, 0.41, 0.005)):
        beads += cels.drop((x, y), r, body=SKIN_LIGHT, light=WET, ink=SKIN_SHADE, opacity=0.55)
    run_k = (t / 2.2) % 1.0
    ry = 0.62 - 0.22 * run_k ** 1.3
    runnel = cels.spline([(0.205, 0.66), (0.198, 0.63), (0.2, ry + 0.01)])
    beads.append(Line(runnel, 0.004, WET, np.linspace(0.3, 1.0, len(runnel)), False, 0.5))
    beads += cels.drop((0.2, ry), 0.008, body=SKIN_LIGHT, light=WET, ink=SKIN_SHADE, stretch=1.5, opacity=0.6)
    d.add("face_wet", beads)
    # a drop gathering on the chin
    d.add("face_wet", cels.drip((-0.135, 0.004), t, period=2.6, r=0.011, fall=0.3, phase=0.35, body=WATER,
                                light=WET, ink=SKIN_LINE))


def _eyes(d: cels.Drawing, eyes: float, sharp: float):
    """Her eyes: small in the face as an old woman's are, heavy-lidded and gentle, the outer corners drooping under
    the hooded fold. As they open sharp (all of it scaled by `sharp`, so a three-drawing open in-betweens) the lids go
    hard and angle down to the nose, the lower lids tense, the irises shrink and lift off the lower lids, the pupils
    go to points, a shadow falls over the eyes from the brow ridge and a cold glint and rim light the irises."""
    common = dict(open=eyes, flat=0.35 + 0.6 * sharp, lower=0.48 - 0.14 * sharp, iris_tall=1.05 - 0.06 * sharp,
                  pupil=0.46 - 0.32 * sharp, lash_inner=0.45, flick=(0.03 + 0.03 * sharp, 40.0), crease=0.0,
                  iris_dark=IRIS_DARK, iris_light=IRIS, ink=EYE_LINE, white=EYE_WHITE, white_shade=EYE_WHITE_SHADE,
                  shade=0.45)
    soft_r = max(0.0, 0.16 * (1 - 1.4 * sharp))           # a soft wet light gives way to the glint
    lights = ((-0.3, 0.3, soft_r), (0.35, -0.3, soft_r * 0.45)) if soft_r > 0.03 else ()
    near = Eye(center=(0.072, 0.492), width=0.18, side=1, height=0.30, tilt=-0.04 + 0.09 * sharp,
               peak=0.42 + 0.24 * sharp, look=(-0.12 + 0.05 * sharp, -0.01 + 0.07 * sharp),
               iris=0.28 - 0.1 * sharp, lash=0.05 + 0.025 * sharp, lower_lash=(0.5, 1.0, 0.014 + 0.006 * sharp),
               lights=lights, **common)
    far = Eye(center=(-0.213, 0.497), width=0.108, side=-1, height=0.32, tilt=-0.02 + 0.08 * sharp,
              peak=0.6 + 0.1 * sharp, look=(0.10 + 0.02 * sharp, -0.01 + 0.07 * sharp),
              iris=0.31 - 0.11 * sharp, lash=0.06 + 0.025 * sharp, lower_lash=(0.5, 1.0, 0.02 + 0.006 * sharp),
              lights=lights, **common)
    d.eye(near, "near_")
    d.eye(far, "far_")
    # the hooded fold above each eye drooping over the outer corner, its shadow on the lid; the bag beneath, its
    # shadow; the inner corner's dark
    age = []
    for e, k, s in ((near, 1.0, 90), (far, 0.65, 95)):
        up, lo = Eye(**{**e.__dict__, "open": 1.0}).lids()
        n0 = int(len(up) * 0.12)
        lift = np.linspace(0.24, 0.05, len(up) - n0) * e.height * (1.3 - 0.4 * eyes)
        fold = up[n0:] + np.c_[np.zeros(len(up) - n0), lift]
        fold[-6:, 1] -= np.linspace(0, 0.06, 6) * e.height     # hanging over the outer corner
        age.append(ink(e._to(fold), W_FINE * k, SKIN_LINE, seed=s, smooth=False, taper_=(0.35, 0.2)))
        crease2 = fold[int(len(fold) * 0.2):int(len(fold) * 0.8)] + [0.0, 0.1 * e.height]
        age.append(ink(e._to(crease2), W_AGE * 0.8 * k, AGE, seed=s + 1, smooth=False, opacity=0.6))
        bag = lo[int(len(lo) * 0.18):int(len(lo) * 0.95)] - [0.0, 0.13 * e.height / 0.3]
        age.append(ink(e._to(bag), W_AGE * k, AGE, seed=s + 2, smooth=False, taper_=(0.45, 0.4), opacity=0.85))
        bag2 = lo[int(len(lo) * 0.3):int(len(lo) * 0.85)] - [0.0, 0.23 * e.height / 0.3]
        age.append(ink(e._to(bag2), W_AGE * 0.8 * k, AGE, seed=s + 3, smooth=False, taper_=(0.45, 0.45),
                       opacity=0.5))
        d.add("eye_soft", cels.soft(e._to(np.vstack([lo[4:-4] - [0, 0.04], (lo[4:-4] - [0, 0.17])[::-1]])),
                                    SKIN_COOL, spread=0.02, opacity=0.35, smooth=False), mask=("skin",))
    # crow's feet fanning from the near eye's outer corner, some forking
    oc = np.array(near._to([[1.0, near.tilt]])[0])
    for i, (ang, ln) in enumerate(((34, 0.05), (14, 0.06), (-6, 0.055), (-24, 0.05), (-40, 0.035))):
        a = math.radians(ang)
        p0 = oc + [0.02, 0.006 * math.sin(a)]
        dirn = np.array([math.cos(a), math.sin(a)])
        p1 = p0 + ln * dirn
        mid = (p0 + p1) / 2 + np.array([-dirn[1], dirn[0]]) * 0.004
        age.append(ink([p0, mid, p1], W_AGE * 0.85, AGE, seed=100 + i, taper_=(0.25, 0.6), opacity=0.8))
    for i, (ang, ln) in enumerate(((150, 0.02), (205, 0.022))):
        a = math.radians(ang)
        oc2 = np.array(far._to([[1.0, far.tilt]])[0])
        p0 = oc2 + [-0.008, 0.0]
        p1 = p0 + ln * np.array([math.cos(a), math.sin(a)])
        age.append(ink([p0, (p0 + p1) / 2, p1], W_AGE * 0.7, AGE, seed=110 + i, taper_=(0.25, 0.6), opacity=0.7))
    d.add("eye_age", age)

    # the shadow falling over her eyes from the brow ridge, its lower edge across the irises: the white under them
    # stays light
    if sharp > 0.01:
        band = [(-0.33, 0.592), (-0.22, 0.592), (-0.12, 0.575), (-0.03, 0.58), (0.10, 0.606), (0.20, 0.598),
                (0.275, 0.568), (0.27, 0.47), (0.20, 0.484), (0.13, 0.488), (0.05, 0.486), (-0.03, 0.50),
                (-0.10, 0.52), (-0.15, 0.496), (-0.23, 0.483), (-0.33, 0.49)]
        d.add("eye_shadow", fill(band, EYE_SHADOW, corners=(0, 6, 7, 15), opacity=0.7 * sharp),
              cels.soft(band, EYE_SHADOW, spread=0.025, opacity=0.25 * sharp, corners=(0, 6, 7, 15)),
              mask=("skin",))
    # through it, the irises' cold rims and a hard glint in each
    for e, k in ((near, 1.0), (far, 0.75)):
        if sharp <= 0.02:
            break
        r = e.iris
        cx = 0.5 + e.look[0]
        cy = e.tilt * 0.5 + e.height * 0.18 + e.look[1]
        rim = cels.arc((cx, cy), r * 0.92, r * e.iris_tall * 0.92, 200, 340, n=24)
        d.add("eye_glint", Line(e._to(rim), 0.024 * e.width * k, IRIS_GLOW, cels.taper(rim, 0.4, 0.4, tip=0.0),
                                opacity=sharp))
        # a hard sliver of light, like the edge of a blade, across the iris's upper side
        g = np.array([cx - 0.3 * r, cy + 0.3 * r * e.iris_tall])
        L = (0.08 + 0.09 * sharp) * k
        a = math.radians(62.0)
        ax, nx = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
        sliver = np.array([g - ax * L, g - nx * L * 0.13, g + ax * L * 0.8, g + nx * L * 0.13])
        d.add("eye_glint", Fill(e._to(sliver), GLINT, opacity=min(1.0, sharp * 1.5)),
              Fill(e._to(cels.ellipse((cx + 0.32 * r, cy - 0.3 * r), 0.03 * k, 0.026 * k, n=12)), GLINT,
                   opacity=sharp))


def _brows(d: cels.Drawing, sharp: float, gust: float):
    """Sparse grey brows of single hairs over a faint tone, the outer ends trailing a few long ones; driven down hard
    toward the nose when she sharpens, their outer ends lifting."""
    dy = -0.055 * sharp
    up_ = 0.012 * sharp
    for (inner, top, outer_end, k, seed) in (
            (np.array([-0.035, 0.57]), [(0.03, 0.604), (0.11, 0.616), (0.18, 0.602)], (0.215, 0.575), 1.0, 120),
            (np.array([-0.16, 0.562]), [(-0.20, 0.594), (-0.25, 0.602)], (-0.285, 0.582), 0.7, 130)):
        side = 1 if outer_end[0] > inner[0] else -1
        span = abs(outer_end[0] - inner[0])
        lift = lambda x: dy * max(0.0, 1 - abs(x - inner[0]) / (0.6 * span)) + up_ * min(1.0, abs(x - inner[0]) / span)
        oe = np.array([outer_end[0], outer_end[1] + up_])
        upper = cels.spline([inner + [0.0, 0.016 + dy], *[(x, y + lift(x)) for x, y in top], oe])
        lower = cels.spline([inner + [side * 0.006 * sharp, dy - 0.004 * sharp],
                             (inner[0] + side * 0.08, inner[1] + 0.02 + lift(inner[0] + side * 0.08)),
                             (inner[0] + side * 0.17, inner[1] + 0.022 + lift(inner[0] + side * 0.17)), oe])
        tone = np.vstack([upper, lower[::-1][1:-1]])
        d.add("brow_tone", cels.soft(tone, BROW_DARK, spread=0.014, opacity=0.35, smooth=False),
              cels.soft(tone + [0.0, -0.012], SKIN_SHADE, spread=0.02, opacity=0.3, smooth=False), mask=("skin",))
        # the hairs: from the lower edge up and out along the brow, the inner ones near upright
        A = cels.resample(lower, 40)
        B = cels.resample(upper, 40) + [side * 0.022, 0.006]
        hairs = cels.strands(A, B, int(34 * k), width=W_HAIR * 1.25 * k, seed=seed, reach=(0.0, 1.15), jitter=0.8,
                             bow=0.05 * side, colors=[BROW, BROW, BROW_DARK, HAIR_LIGHT], opacity=(0.65, 1.0))
        # and a few long ones trailing from the outer end, stirring in the wind
        rng = np.random.default_rng(seed + 1)
        for j in range(3):
            p0 = cels.resample(lower, 20)[16 + j] + [0.0, 0.004]
            p1 = p0 + [side * (0.04 + 0.015 * j), -0.006 - 0.008 * j + 0.004 * gust]
            hairs.append(ink([p0, (p0 + p1) / 2 + [0, 0.006], p1], W_HAIR * 1.1 * k,
                             (BROW, HAIR_LIGHT, BROW_DARK)[j], seed=seed + 2 + j, taper_=(0.1, 0.7), opacity=0.9))
        d.add("brows", hairs)


# ---------------------------------------------------------------------------------------------------- neck, kimono

def _neck(d: cels.Drawing, head):
    neck = fill([(0.30, 0.30), (0.04, 0.06), (-0.04, 0.03), (-0.068, -0.06), (-0.08, -0.20), (-0.09, -0.36),
                 (0.38, -0.36), (0.36, -0.10), (0.33, 0.10)], SKIN, corners=(5, 6))
    d.add("neck", neck)
    jaw = cels.between(head, CHIN, EAR)
    cast = np.vstack([jaw[::-1] + [0.0, 0.004], jaw + [-0.015, -0.085]])
    # the cord from behind the ear down to the hollow of the throat; the plane behind it turned from the light
    cord = cels.spline([(0.25, 0.17), (0.17, 0.05), (0.09, -0.08), (0.02, -0.2)])
    behind = np.vstack([cord, [(0.02, -0.4), (0.45, -0.4), (0.45, 0.3), (0.27, 0.25)]])
    d.add("neck_shade",
          Fill(behind, SKIN_SHADE),
          Fill(cast, SKIN_DEEP), cels.soft(cast + [0.0, -0.02], SKIN_DEEP, spread=0.05, opacity=0.5),
          # the hollow in front of the cord, and the notch of the throat
          Fill(np.vstack([cord, cels.offset(cord, 0.032 * np.sin(np.linspace(0, math.pi, len(cord))))[::-1]]),
               SKIN_SHADE, opacity=0.6),
          blob((0.0, -0.24), 0.03, 0.025, SKIN_DEEP, spread=0.03, opacity=0.5),
          blob((0.33, -0.05), 0.08, 0.2, SKIN_DEEP, spread=0.08, opacity=0.5),
          # the loose skin under the chin
          blob((-0.04, -0.03), 0.05, 0.025, SKIN_SHADE, spread=0.03, opacity=0.6, rotate=-20),
          blob((-0.055, -0.1), 0.012, 0.06, SKIN_LIGHT, spread=0.02, opacity=0.4),
          mask=("neck",))
    d.add("neck_lines",
          ink([(-0.045, 0.03), (-0.068, -0.07), (-0.082, -0.2), (-0.09, -0.36)], W_LIT, SKIN_LINE_LIT, seed=140,
              taper_=(0.15, 0.3)),
          ink([(0.33, 0.12), (0.355, -0.05), (0.375, -0.2)], W_OUT, SKIN_LINE, seed=141, taper_=(0.3, 0.3)),
          ink(cord, W_AGE * 1.4, AGE, seed=142, taper_=(0.3, 0.3)),
          ink([(0.2, 0.06), (0.14, -0.04), (0.08, -0.12)], W_AGE, AGE, seed=143, opacity=0.6),
          # the loose skin under the chin and the rings round an old throat
          ink([(-0.1, 0.006), (-0.07, -0.03), (-0.035, -0.045), (0.005, -0.04)], W_AGE * 1.2, AGE, seed=144,
              opacity=0.85),
          ink([(-0.064, -0.1), (-0.03, -0.11), (0.01, -0.105), (0.05, -0.095)], W_AGE * 0.9, AGE, seed=145,
              opacity=0.6),
          ink([(-0.075, -0.17), (-0.04, -0.18), (0.0, -0.176), (0.04, -0.168)], W_AGE * 0.8, AGE, seed=146,
              opacity=0.5),
          ink([(-0.035, 0.02), (-0.04, -0.06), (-0.035, -0.13)], W_AGE * 0.8, AGE, seed=147, opacity=0.4))


def _kimono_bust(d: cels.Drawing, t: float):
    """The indigo kimono in the opening of the cape: the collar crossed left over right, lined with the pale
    under-collar, over a glimpse of her chest; soaked darker toward the shoulders."""
    body = fill([(-0.56, -1.8), (-0.55, -0.95), (-0.45, -0.40), (-0.35, -0.24), (-0.22, -0.16), (-0.10, -0.19),
                 (0.20, -0.08), (0.36, -0.02), (0.46, -0.16), (0.58, -0.40), (0.7, -0.95), (0.72, -1.8)], CLOTH,
                corners=(0, 11))
    d.add("cloth", body)
    near_edge = cels.spline([(0.35, -0.015), (0.24, -0.11), (0.11, -0.29), (-0.02, -0.56)])
    far_edge = cels.spline([(-0.15, -0.19), (-0.135, -0.33), (-0.09, -0.47), (-0.02, -0.56)])
    chest = Fill(np.vstack([near_edge, far_edge[::-1][1:]]), SKIN)
    d.add("chest", chest)
    d.add("chest_shade", fill([(0.36, 0.0), (-0.2, -0.16), (-0.16, -0.27), (0.05, -0.27), (0.2, -0.17)],
                              SKIN_DEEP, opacity=0.85),
          cels.soft([(0.1, -0.3), (-0.06, -0.3), (-0.04, -0.5), (0.05, -0.45)], SKIN_SHADE, spread=0.06,
                    opacity=0.5),
          ink([(-0.07, -0.33), (-0.03, -0.38), (0.02, -0.36)], W_AGE, AGE, seed=150, opacity=0.5),
          mask=("chest",))
    under_n = Fill(cels.ribbon(cels.offset(near_edge, -0.017), 0.036), UNDER)
    under_f = Fill(cels.ribbon(cels.offset(far_edge, 0.014), 0.028), UNDER_SHADE)
    eri_n = Fill(cels.ribbon(cels.offset(near_edge, 0.038), 0.078), CLOTH)
    eri_f = Fill(cels.ribbon(cels.offset(far_edge, -0.03), 0.06), CLOTH_LIGHT)
    d.add("collar", under_n, under_f, eri_n, eri_f)
    d.add("collar_shade", blob((0.2, -0.12), 0.08, 0.05, UNDER_SHADE, spread=0.05, opacity=0.6),
          cels.soft(cels.ribbon(cels.offset(near_edge, 0.04), 0.03), CLOTH_SHADE, spread=0.02, opacity=0.7),
          mask=("collar",))
    # the soaked cloth: darker over the shoulders and down the folds
    d.add("cloth_shade",
          cels.soft([(-0.9, -0.4), (-0.3, -0.25), (-0.15, -0.6), (-0.9, -1.0)], CLOTH_WET, spread=0.2,
                    opacity=0.6, smooth=False),
          cels.soft([(0.25, -0.2), (0.9, -0.4), (0.9, -1.0), (0.15, -0.7)], CLOTH_SHADE, spread=0.2, opacity=0.8,
                    smooth=False),
          ink([(-0.02, -0.56), (0.0, -1.0), (0.03, -1.75)], W_IN, CLOTH_LINE, seed=151, taper_=(0.05, 0.05)),
          ink([(0.06, -0.62), (0.08, -0.9), (0.075, -1.2)], W_AGE, CLOTH_LINE, seed=152, opacity=0.7),
          ink([(-0.08, -0.66), (-0.09, -1.0)], W_AGE, CLOTH_LINE, seed=153, opacity=0.6),
          mask=("cloth",))
    d.add("cloth_lines",
          ink(np.vstack([under_n.points, under_n.points[:2]]), W_FINE, UNDER_LINE, seed=154, taper_=(0.02, 0.02),
              tip=1.0, smooth=False),
          ink(np.vstack([under_f.points, under_f.points[:2]]), W_FINE, UNDER_LINE, seed=155, taper_=(0.02, 0.02),
              tip=1.0, smooth=False),
          ink(np.vstack([eri_n.points, eri_n.points[:2]]), W_IN, CLOTH_LINE, seed=156, taper_=(0.02, 0.02),
              tip=1.0, smooth=False),
          ink(np.vstack([eri_f.points, eri_f.points[:2]]), W_IN, CLOTH_LINE, seed=157, taper_=(0.02, 0.02),
              tip=1.0, smooth=False))


# ---------------------------------------------------------------------------------------------------- straw

def _down(P, depth: float, count: int, *, seed: int, vary: float = 0.7, fine: float = 0.4):
    """`cels.clumps` hanging down whichever way P runs: clumps of wet straw, each split into finer points."""
    P = cels._arr(P)
    kw = dict(fine=fine, fine_count=count * 4, seed=seed, vary=vary)
    if P[-1, 0] < P[0, 0]:
        return cels.clumps(P[::-1], depth, count, **kw)[::-1]
    return cels.clumps(P, depth, count, **kw)


def straw_tier(d: cels.Drawing, name: str, sil, edge, *, t: float = 0.0, src=None, count: int = 12, seed: int = 0,
               tip: float = 0.12, sway: float = 0.0, above=None, dark=None, light=None, wet: float = 0.55,
               fibres: float = 1.0, w_line: float = W_IN, w_fibre: float = W_HAIR * 1.4, drips: int = 2,
               drip_r: float = 0.011, frame_bottom: float = -1.68, ink_edge: bool = True, u: float = 1.0):
    """One tier of a straw rain cape on its own layers. `sil` is the cape's silhouette on this side, from the front
    edge at the throat over the shoulder and down the outside (all its tiers share it); `edge` the line the tier's
    straw hangs to, inner end first, its outer end on the silhouette. The ends are clumped wet into ragged points
    (`count`, reaching `tip` further) that swing `sway` degrees in the wind. Over it: the shadow the tier `above` (its
    outline) casts, the form turned from the light (`dark`: a polygon softened over a wide edge), the light on top
    (`light`), the ends soaked dark (`wet`); straws drawn from `src` (where they come from: the silhouette for the top
    tier, under the edge of the tier above for the others) down to the points in mixed tones (`fibres` scales their
    count), loose ones past the edge, drips gathering on the lowest points. Sizes are a bust's (head units); `u`
    scales the shadows' offsets and softness and the loose straws to other units. Returns the tier's outline."""
    S = cels.resample(cels._arr(sil) if len(sil) > 40 else cels.spline(sil), 240)
    E = cels.spline(edge)
    j = int(np.argmin(np.linalg.norm(S - E[-1], axis=1)))
    R = _down(E, tip, count, seed=seed)
    Q = cels.resample(E, len(R))
    # where the edge turns down round her side the points shorten: straw hangs down, not out
    tan = np.gradient(Q, axis=0)
    flat = np.abs(tan[:, 0]) / np.maximum(np.linalg.norm(tan, axis=1), 1e-9)
    R = Q + (R - Q) * (flat ** 2)[:, None]
    R = R + np.c_[math.radians(sway) * (0.25 * u + (Q[:, 1] - R[:, 1]) * 2.0), np.zeros(len(R))]
    shape = np.vstack([S[:j + 1], R[::-1]])
    d.add(name, Fill(shape, STRAW))
    d.layer(name + "_fibre", mask=(name,))      # the straws under the shading, so it falls on them too

    shade = []
    if above is not None:
        above = cels.resample(above, 90)
        shade += [*cels.soft(above + np.array([0.004, -0.025]) * u, STRAW_DEEP, spread=0.02 * u, opacity=0.7,
                             smooth=False, steps=3),
                  *cels.soft(above + np.array([0.01, -0.07]) * u, STRAW_SHADE, spread=0.08 * u, opacity=0.5,
                             smooth=False, steps=7)]
    if dark is not None:
        shade += cels.soft(dark, STRAW_SHADE, spread=0.3 * u, opacity=0.75, smooth=False, steps=24)
    if light is not None:
        shade += cels.soft(light, STRAW_LIGHT, spread=0.14 * u, opacity=0.4, smooth=False, steps=12)
    if wet > 0:
        band = np.vstack([cels.resample(Q, 30) + [0.0, 0.03 * u], cels.resample(R, 90)[::-1]])
        shade += cels.soft(band - [0.0, 0.02 * u], STRAW_WET, spread=0.05 * u, opacity=wet, smooth=False, steps=5)
    d.add(name + "_shade", shade, mask=(name,))

    # the straws, in mixed tones: gaps between them dark, a lit one here and there
    A = cels.resample(S[:j + 1] if src is None else cels.spline(src), len(R))
    length = float(cels.lengths(E)[-1])
    n = int(fibres * 85 * length / u) + 8
    fib = cels.strands(A, R, n, width=w_fibre, seed=seed + 7, reach=(0.0, 1.0), jitter=0.9, bow=0.01,
                       colors=[STRAW_LINE, STRAW_LINE, STRAW_DEEP, STRAW_SHADE], opacity=(0.35, 0.85))
    lit = cels.strands(A, R, n // 3, width=w_fibre * 1.2, seed=seed + 8, reach=(0.05, 0.95), jitter=1.0, bow=-0.01,
                       colors=[STRAW_LIGHT, STRAW_PALE], opacity=(0.35, 0.8))
    d.add(name + "_fibre", fib, lit, mask=(name,))

    # the edge: the ragged ends inked, loose straws past them, drips on the lowest points
    edge_lines = []
    if ink_edge:
        edge_lines.append(ink(R, w_line * 0.6, STRAW_LINE, seed=seed + 9, taper_=(0.02, 0.02), tip=0.8, wobble=0.6,
                              smooth=False, opacity=0.55))
    rng = np.random.default_rng(seed + 10)
    y = R[:, 1]
    tips = [i for i in range(2, len(R) - 2) if y[i] <= y[i - 1] and y[i] <= y[i + 1]]
    # the bundles: a dark gap running up from each notch between the points, the straw parting there
    notches = [i for i in range(2, len(R) - 2) if y[i] >= y[i - 1] and y[i] > y[i + 1]]
    gaps = []
    for i in notches:
        a = A[i] + (R[i] - A[i]) * rng.uniform(0.25, 0.6)
        gaps.append(Line(np.array([a, (a + R[i]) / 2, R[i]]), w_fibre * rng.uniform(2.5, 4.5), STRAW_DEEP,
                         np.array([0.0, 0.7, 1.0]), False, float(rng.uniform(0.35, 0.65))))
    d.add(name + "_fibre", gaps, mask=(name,))
    for i in tips:
        if rng.uniform() < 0.55:
            p = R[i]
            q = p + np.array([rng.uniform(-0.02, 0.02) + math.radians(sway) * 0.05, -rng.uniform(0.02, 0.06)]) * u
            edge_lines.append(ink([p + [0.0, 0.03 * u], p, q], w_fibre * 1.2, STRAW_LINE, seed=seed + 11 + i,
                                  taper_=(0.2, 0.7), opacity=0.9))
    d.add(name + "_lines", edge_lines)
    visible = [i for i in tips if R[i][1] > frame_bottom]
    if drips and visible:
        pick = sorted(visible, key=lambda i: R[i][1])[:max(1, drips * 2)]
        rng.shuffle(pick)
        dr = []
        for i in pick[:drips]:
            dr += cels.drip(R[i], t, period=rng.uniform(1.3, 2.4), r=drip_r, fall=0.3 * u, phase=rng.uniform(),
                            body=WATER, light=WET, ink=STRAW_LINE)
        d.add("drips", dr)
    return shape


def straw_cape(d: cels.Drawing, prefix: str, sil, edges, *, t: float, sway: float, seed: int, dark=None,
               light=None, counts=None, tip: float = 0.12, w_line: float = W_IN, w_fibre: float = W_HAIR * 1.4,
               w_out: float = W_OUT, drip_r: float = 0.011, frame_bottom: float = -1.68, fibres: float = 1.0,
               u: float = 1.0, lump: float = 0.05, tuft: int = 14, strays: int = 5, between=None,
               shade_from: float = 0.5) -> dict:
    """One side of a straw cape: tiers hanging to `edges` (top tier first) over the shared silhouette `sil` (from
    the front edge at the throat over the shoulder and down the outside), drawn bottom tier first, each upper one
    shadowing the one below. The silhouette is made lumpy with bundles (`lump`), clumps of straw stick out of it at
    different lengths (`tuft` of them, past `shade_from` of its length in shade) with a few long strays (`strays`);
    it and the front edge are inked over all. `between` ({k: fn(d)}) draws something under tier k and over the
    tiers below it: an arm coming out from under the cape. Returns the tiers' outlines by name."""
    S0 = cels.spline(sil)
    out = 1.0 if S0[-1, 0] > S0[0, 0] else -1.0
    sil = cels.lumpy(S0, lump * u * out, bumps=cels.lengths(S0)[-1] / u * 4, seed=seed + 47, ends=0.04)
    names = [f"{prefix}{k}" for k in range(len(edges))]
    counts = counts or [12] * len(edges)
    outlines = {}
    for k in range(len(edges)):           # the outlines first: each casts its shadow on the one below
        outlines[names[k]] = straw_tier(cels.Drawing(), names[k], sil, edges[k], sway=sway, seed=seed + k,
                                        count=counts[k], tip=tip, drips=0, fibres=0.0, u=u)
    for k in reversed(range(len(edges))):
        if between and k in between:
            between[k](d)
        above = outlines[names[k - 1]] if k > 0 else None
        src = None if k == 0 else np.asarray(edges[k - 1], float) + [0.0, 0.1 * u]
        straw_tier(d, names[k], sil, edges[k], t=t, src=src, sway=sway, above=above, dark=dark,
                   light=light if k == 0 else None, seed=seed + k, count=counts[k], tip=tip, w_line=w_line,
                   w_fibre=w_fibre, drips=2 if k < len(edges) - 1 else 0, drip_r=drip_r, frame_bottom=frame_bottom,
                   fibres=fibres * (1.6 if k == 0 else 1.0), u=u)
    S = sil
    L = float(cels.lengths(S)[-1])
    # clumps of straw sticking out of the outline, at different lengths, the shaded ones darker
    rng = np.random.default_rng(seed + 49)
    clumps_, lines = [], []
    for k_, T in enumerate(cels.tufts(S, tuft, length=(0.03 * u, 0.12 * u), width=(0.04 * u, 0.1 * u), droop=0.55,
                                      seed=seed + 49, side=int(out), reach=(0.12, 0.97))):
        mid = cels._arr(T)
        u_at = float(np.argmin(np.linalg.norm(S - (mid[0] + mid[-1]) / 2, axis=1))) / len(S)
        col = STRAW_SHADE if (u_at > shade_from) else (STRAW, STRAW_LIGHT)[k_ % 2]
        shape = cels.spline(mid, closed=True, corners=(2,), step=0.006 * u)
        clumps_.append(Fill(shape, col))
        base = (mid[0] + mid[-1]) / 2
        for f in (0.3, 0.5, 0.7):
            a = mid[0] + (mid[-1] - mid[0]) * f
            lines.append(ink([a - (mid[2] - base) * 0.3, mid[2] + (a - base) * 0.4], w_fibre * 1.1,
                             (STRAW_LINE, STRAW_DEEP, STRAW_LIGHT)[int(rng.integers(3))], seed=seed + 60 + k_,
                             taper_=(0.2, 0.6), opacity=0.85))
        lines.append(ink(shape, w_fibre, STRAW_LINE, seed=seed + 80 + k_, taper_=(0.1, 0.1), wobble=0.5,
                         smooth=False, opacity=0.6))
    # a few long strays
    for k_ in range(strays):
        i = int(rng.uniform(0.15, 0.95) * (len(S) - 2)) + 1
        nrm = cels.normals(S[i - 1:i + 2])[1] * out
        dirn = nrm * 0.5 + np.array([rng.uniform(-0.4, 0.4), -0.7])
        dirn = dirn / np.linalg.norm(dirn)
        ln = rng.uniform(0.1, 0.24) * u
        p0 = S[i] - nrm * 0.03 * u
        p1 = S[i] + dirn * ln
        lines.append(ink([p0, (p0 + p1) / 2 + nrm * 0.01 * u, p1], w_fibre * 1.3, (STRAW_LINE, STRAW_PALE)[k_ % 2],
                         seed=seed + 90 + k_, taper_=(0.1, 0.8), opacity=0.9))
    d.add(prefix + "_shag", clumps_, lines)
    d.add(prefix + "_contour", ink(S, w_out * 0.7, STRAW_LINE, seed=seed + 50, taper_=(0.05, 0.0), tip=0.4,
                                   wobble=0.45, smooth=False))
    front = np.array([S[0], np.asarray(edges[-1], float)[0]])
    d.add(prefix + "_contour", ink(cels.resample(front, 30), w_line, STRAW_LINE, seed=seed + 51, taper_=(0.05, 0.0),
                                   wobble=0.3, smooth=False))
    return outlines


def _cape_bust(d: cels.Drawing, t: float, gust: float, flick: float, between_far=None):
    """The straw cape (mino) as the close-up sees it: tied at her throat, its top gathered round the base of her neck
    and rising behind it, falling over narrow sloping shoulders; on her far side it bunches out over the arm reaching
    forward to the pole. Uneven tiers a side, overlapping and partly hidden, each tier's clumped edge shadowing the
    one below; open at the front over her collar. Her far side (screen left) faces the light; the near side's outer
    part turns from it."""
    sw = 1.2 * gust + 0.6 * flick
    near_sil = [(0.03, -0.27), (0.14, -0.19), (0.28, -0.13), (0.40, -0.15), (0.52, -0.25), (0.62, -0.40),
                (0.69, -0.58), (0.735, -0.8), (0.765, -1.1), (0.79, -1.5), (0.81, -1.95)]
    far_sil = [(-0.005, -0.27), (-0.12, -0.2), (-0.26, -0.22), (-0.38, -0.3), (-0.48, -0.41), (-0.56, -0.53),
               (-0.615, -0.66), (-0.6, -0.82), (-0.565, -1.05), (-0.55, -1.5), (-0.545, -1.95)]
    near_edges = [[(0.04, -0.34), (0.12, -0.31), (0.22, -0.27), (0.32, -0.245), (0.42, -0.27), (0.5, -0.24)],
                  [(0.05, -0.58), (0.16, -0.6), (0.29, -0.53), (0.42, -0.6), (0.53, -0.64), (0.62, -0.68),
                   (0.70, -0.62)],
                  [(0.07, -1.0), (0.22, -0.96), (0.38, -1.03), (0.52, -0.99), (0.66, -1.08), (0.755, -1.0)],
                  [(0.13, -1.97), (0.5, -1.97), (0.81, -1.97)]]
    far_edges = [[(-0.02, -0.35), (-0.1, -0.31), (-0.2, -0.29), (-0.29, -0.32), (-0.36, -0.29)],
                 [(-0.03, -0.6), (-0.13, -0.56), (-0.25, -0.62), (-0.37, -0.58), (-0.47, -0.66), (-0.555, -0.62)],
                 [(-0.065, -1.02), (-0.2, -0.98), (-0.33, -1.05), (-0.45, -1.0), (-0.575, -1.0)],
                 [(-0.11, -1.97), (-0.35, -1.97), (-0.545, -1.97)]]
    near_dark = [(0.5, 0.2), (1.2, 0.2), (1.2, -2.0), (0.6, -2.0), (0.55, -0.9)]
    far_dark = [(-0.52, -0.5), (-1.2, -0.5), (-1.2, -2.0), (-0.5, -2.0)]
    near_light = [(0.03, -0.25), (0.3, -0.08), (0.46, -0.15), (0.35, -0.38), (0.05, -0.35)]
    far_light = [(0.0, -0.25), (-0.3, -0.16), (-0.5, -0.4), (-0.35, -0.52), (-0.05, -0.4)]
    straw_cape(d, "cape_n", near_sil, near_edges, t=t, sway=sw, seed=1, dark=near_dark, light=near_light,
               counts=[7, 11, 12, 10], tip=0.13, tuft=13, strays=4, shade_from=0.35)
    straw_cape(d, "cape_f", far_sil, far_edges, t=t, sway=sw, seed=11, dark=far_dark, light=far_light,
               counts=[6, 10, 10, 8], tip=0.13, tuft=10, strays=4, shade_from=0.8, between=between_far)
    # the cords tying it at her throat: two ends knotted under her chin, short tails hanging
    knot = np.array([0.012, -0.262])
    cords = []
    for a in ((-0.075, -0.215), (0.1, -0.2)):
        c = cels.spline([a, ((a[0] + knot[0]) / 2, (a[1] + knot[1]) / 2 - 0.015), knot])
        r = cels.ribbon(c, 0.018)
        cords += [Fill(r, CORD), ink(np.vstack([r, r[:2]]), W_AGE, CORD_LINE, seed=170, taper_=(0.02, 0.02),
                                     tip=1.0, smooth=False)]
    dx = 0.0
    for dx, ln in ((-0.012, 0.09), (0.014, 0.075)):
        c = cels.spline([knot, knot + [dx, -ln * 0.5], knot + [dx * 1.8 + 0.006 * gust, -ln]])
        r = cels.ribbon(c, 0.014 * np.linspace(1.0, 0.6, len(c)))
        cords += [Fill(r, CORD), ink(np.vstack([r, r[:2]]), W_AGE, CORD_LINE, seed=171, taper_=(0.02, 0.02),
                                     tip=1.0, smooth=False)]
    kn = cels.ellipse(knot, 0.019, 0.015)
    cords += [Fill(kn, CORD), Line(kn, W_AGE, CORD_LINE, closed=True)]
    cords += cels.drip(knot + [dx * 1.8, -0.075], t, period=1.9, r=0.008, fall=0.2, phase=0.6, body=WATER, light=WET,
                       ink=CORD_LINE)
    d.add("cape_cord", cords)


# ---------------------------------------------------------------------------------------------------- hand, sleeve

GRIP = -22.0       # the fist's tilt on the pole, degrees: the forearm rises to it from the elbow


def _hand(d: cels.Drawing, place, k: float, t: float, *, prefix: str = "", pole: str = "pole"):
    """Her right hand wrapped round the pole: four knuckly fingers across its front, their tips curling round behind
    it, the thumb over the first, the back of an old hand going off to the wrist (tendons, a vein, age spots), bony
    knuckles catching the light, the rain running off it. Drawn in head units round the pole's axis at the middle of
    the grip (x toward her wrist); `place(P)` puts points where they go, `k` scales the line widths."""
    def L(points, w, color, **kw):
        ln = ink(place(cels.spline(points)), w * k, color, smooth=False, **kw)
        return ln

    d.layer(prefix + "hand_cast", mask=(pole,))       # its shadow on the pole, under it
    back = fill(place([(0.15, 0.16), (0.215, 0.185), (0.29, 0.14), (0.32, 0.0), (0.3, -0.11), (0.22, -0.15),
                       (0.15, -0.14)]), SKIN)
    wrist = fill(place([(0.26, 0.13), (0.33, 0.1), (0.34, -0.08), (0.27, -0.12)]), SKIN)
    fingers, outlines = [], []
    for j, (yk, th) in enumerate(((0.1, 0.07), (0.033, 0.068), (-0.033, 0.064), (-0.092, 0.056))):
        h = th / 2
        # from the big knuckle back on the hand to the middle knuckle, bent there round the front of the pole, the
        # last joint curling round its edge out of sight
        top = [(0.19, yk + h + 0.012), (0.11, yk + h + 0.01), (0.088, yk + h + 0.012), (0.02, yk + h - 0.002),
               (-0.035, yk + h - 0.012), (-0.06, yk + h - 0.024)]
        bot = [(-0.063, yk - h - 0.006), (0.0, yk - h - 0.004), (0.08, yk - h - 0.008), (0.19, yk - h + 0.008)]
        o = cels.spline([*top, (-0.077, yk - 0.014), *bot], closed=True, corners=(2, 8), step=0.004)
        fingers.append(Fill(place(o), SKIN))
        outlines.append(o)
    thumb_c = cels.spline([(0.26, 0.17), (0.16, 0.165), (0.07, 0.15), (-0.005, 0.132)])
    thumb = cels.spline(cels.ribbon(thumb_c, np.linspace(0.075, 0.055, len(thumb_c))), closed=True, step=0.006)
    d.add(prefix + "hand", wrist, back, fingers, Fill(place(thumb), SKIN))
    # the light from up and to the left: each finger shaded along its underside, the knuckles lit, the back of the
    # hand turning from it
    shade = []
    for j, o in enumerate(outlines):
        lo = o[: len(o) // 2]
        shade += cels.soft(place(np.vstack([lo, (lo + [0.0, 0.03])[::-1]])), SKIN_SHADE, spread=0.012 * k,
                           opacity=0.75, smooth=False)
    lo = thumb[: len(thumb) // 2]
    shade += cels.soft(place(np.vstack([lo, (lo + [0.0, 0.03])[::-1]])), SKIN_SHADE, spread=0.012 * k,
                       opacity=0.7, smooth=False)
    shade += cels.soft(place([(0.24, -0.17), (0.46, -0.17), (0.46, 0.06), (0.28, 0.0)]), SKIN_SHADE,
                       spread=0.05 * k, opacity=0.7, smooth=False)
    for j, yk in enumerate((0.1, 0.033, -0.033, -0.092)):
        shade += blob(place([(0.09, yk + 0.016)])[0], 0.016 * k, 0.012 * k, SKIN_LIGHT, spread=0.012 * k,
                      opacity=0.85)
        shade += blob(place([(0.19, yk + 0.01)])[0], 0.016 * k, 0.014 * k, SKIN_WARM, spread=0.012 * k,
                      opacity=0.45)
        # the tip turning away behind the pole
        shade += blob(place([(-0.07, yk)])[0], 0.012 * k, 0.025 * k, SKIN_SHADE, spread=0.012 * k, opacity=0.7)
    for (x, y, r) in ((0.27, 0.08, 0.011), (0.29, -0.04, 0.008), (0.22, 0.02, 0.007)):
        shade += blob(place([(x, y)])[0], r * k, r * 0.8 * k, SKIN_WARM, spread=0.008 * k, opacity=0.3)
    # the big knuckles: a ridge of bumps along the back of the hand, lit
    for yk in (0.12, 0.05, -0.02, -0.08):
        shade += blob(place([(0.2, yk)])[0], 0.022 * k, 0.018 * k, SKIN_LIGHT, spread=0.015 * k, opacity=0.6)
    d.add(prefix + "hand_shade", shade, mask=(prefix + "hand",))
    lines = []
    for j, o in enumerate(outlines):
        lines.append(ink(place(np.vstack([o, o[:2]])), W_FINE * k, SKIN_LINE, seed=500 + j, taper_=(0.02, 0.02),
                         tip=1.0, wobble=0.35, smooth=False))
        yk = (0.1, 0.035, -0.03, -0.09)[j]
        # the wrinkles over the middle knuckle and the last, the nail at the curled tip
        for dx in (0.012, 0.024):
            lines.append(L([(0.085 + dx, yk + 0.026), (0.088 + dx, yk + 0.004), (0.085 + dx, yk - 0.02)],
                           W_AGE * 0.8, AGE, seed=510 + j, opacity=0.8))
        lines.append(L([(-0.03, yk + 0.022), (-0.028, yk - 0.015)], W_AGE * 0.7, AGE, seed=520 + j, opacity=0.6))
        # the nail's edge at the curled tip
        lines.append(L([(-0.072, yk + 0.016), (-0.062, yk + 0.02), (-0.056, yk + 0.012)], W_AGE, SKIN_LINE,
                       seed=530 + j, opacity=0.8))
    lines.append(ink(place(np.vstack([thumb, thumb[:2]])), W_FINE * k, SKIN_LINE, seed=540, taper_=(0.02, 0.02),
                     tip=1.0, wobble=0.35, smooth=False))
    nail = cels.spline([(0.0, 0.15), (0.03, 0.152), (0.035, 0.125), (0.002, 0.118)], closed=True, step=0.004)
    lines += [Fill(place(nail), SKIN_LIGHT, opacity=0.9), ink(place(np.vstack([nail, nail[:2]])), W_AGE * k,
                                                               SKIN_LINE, seed=541, smooth=False, opacity=0.8)]
    lines.append(L([(0.12, 0.155), (0.12, 0.13)], W_AGE * 0.8, AGE, seed=542, opacity=0.7))
    # the back of the hand: its edge, the tendons and a vein running to the wrist
    lines.append(L([(0.215, 0.185), (0.29, 0.14), (0.32, 0.0), (0.3, -0.11)], W_FINE, SKIN_LINE, seed=543))
    lines.append(L([(0.15, -0.14), (0.22, -0.15), (0.3, -0.11)], W_IN, SKIN_LINE, seed=544))
    for j, y in enumerate((0.07, 0.0, -0.07)):
        lines.append(L([(0.22, y + 0.02), (0.27, y), (0.31, y - 0.012)], W_AGE * 0.8, SKIN_SHADE, seed=545 + j,
                       opacity=0.7))
    d.add(prefix + "hand_lines", lines)
    # its shadow on the pole below it, and the rain running off the knuckles
    d.add(prefix + "hand_cast", cels.soft(place([(-0.12, -0.11), (0.12, -0.1), (0.12, -0.2), (-0.12, -0.21)]),
                                          POLE_LINE, spread=0.05 * k, opacity=0.6, smooth=False), mask=(pole,))
    d.add(prefix + "hand_lines", cels.drip(place([(-0.02, -0.12)])[0], t, period=1.8, r=0.011 * k, fall=0.25 * k,
                                           phase=0.45, body=WATER, light=WET, ink=SKIN_LINE))
    d.add(prefix + "hand_lines", cels.drop(place([(0.09, 0.06)])[0], 0.007 * k, body=SKIN_LIGHT, light=WET,
                                           ink=SKIN_SHADE, opacity=0.6))


def _sleeve(d: cels.Drawing, outline, folds, cuff, lowest, t: float, *, k: float = 1.0, prefix: str = ""):
    """The wide sleeve of her right arm: `outline` from the cuff along the top of the forearm to where it goes under
    the cape, round the heavy wet bag the cloth hangs in below the forearm (its `lowest` point) and back up to the
    cuff. Shaded below and soaked dark toward the bottom, lit along the forearm; folds pulled down from the points
    `folds` toward the lowest point; the cuff's mouth (`cuff`: centre, half width, half height, tilt in degrees) dark
    round the wrist; the rain dripping off the bottom. `k` scales line widths and softness."""
    lowest = np.asarray(lowest, float)
    body = fill(outline, CLOTH)
    P = body.points
    lo, hi = P[:, 1].min(), P[:, 1].max()
    x0, x1 = P[:, 0].min() - 0.1 * k, P[:, 0].max() + 0.1 * k
    span = hi - lo
    d.add(prefix + "sleeve", body)
    d.add(prefix + "sleeve_shade",
          cels.soft([(x0, hi - span * 0.3), (x1, hi - span * 0.3), (x1, lo - 0.1 * k), (x0, lo - 0.1 * k)],
                    CLOTH_SHADE, spread=span * 0.4, opacity=0.8, smooth=False),
          cels.soft([(x0, lo + span * 0.35), (x1, lo + span * 0.35), (x1, lo - 0.1 * k), (x0, lo - 0.1 * k)],
                    CLOTH_WET, spread=span * 0.25, opacity=0.7, smooth=False),
          cels.soft([(x0, hi + 0.1 * k), (x1, hi + 0.1 * k), (x1, hi - span * 0.12), (x0, hi - span * 0.12)],
                    CLOTH_LIGHT, spread=span * 0.12, opacity=0.8, smooth=False),
          *[ink([f, (np.asarray(f) + lowest) / 2 + [0.02 * k, 0.0], lowest], W_FINE * k, CLOTH_LINE, seed=560 + j,
                taper_=(0.3, 0.4), opacity=0.85) for j, f in enumerate(folds)],
          *[ink([np.asarray(f) + [-0.015 * k, -0.01 * k], (np.asarray(f) + lowest) / 2 + [0.0, 0.01 * k]], W_FINE * k,
                CLOTH_LIGHT, seed=566 + j, taper_=(0.3, 0.5), opacity=0.7) for j, f in enumerate(folds[::2])],
          mask=(prefix + "sleeve",))
    c, rx, ry, rot = cuff
    mouth = cels.ellipse(c, rx, ry, rotate=rot, n=32)
    d.add(prefix + "sleeve_lines",
          ink(np.vstack([P, P[:2]]), W_IN * k, CLOTH_LINE, seed=570, taper_=(0.02, 0.02), tip=1.0, wobble=0.35,
              smooth=False),
          Fill(mouth, CLOTH_LINE), ink(np.vstack([mouth, mouth[:2]]), W_FINE * k, CLOTH_LINE, seed=571, smooth=False),
          *cels.drip(lowest, t, period=1.5, r=0.012 * k, fall=0.3 * k, phase=0.1, body=WATER, light=WET,
                     ink=CLOTH_LINE))


# ---------------------------------------------------------------------------------------------------- hair

def _hair_bust(d: cels.Drawing, t: float, gust: float, flick: float):
    """Her hair for the close-up: combed back hard from the hairline in sections to the bun, fine strands showing
    the comb's track, the back of the head and the hair under the bun in shade, a sheen broken along the strands on
    the crown; damp wisps stuck at the temples, a few flyaways stirring."""
    cap = fill([(-0.27, 0.80), (-0.305, 0.92), (-0.19, 1.05), (0.0, 1.11), (0.20, 1.10), (0.38, 1.03), (0.47, 0.84),
                (0.47, 0.64), (0.43, 0.48), (0.385, 0.40), (0.392, 0.47), (0.375, 0.535), (0.32, 0.565),
                (0.27, 0.60), (0.23, 0.70), (0.20, 0.79), (0.10, 0.85), (-0.02, 0.87), (-0.14, 0.855), (-0.22, 0.83)],
               HAIR, corners=(0, 9))
    # the thin old hair at the hairline lets the scalp show: a soft grey over the skin along it
    line_ = cels.between(cap.points, (0.385, 0.40), (-0.27, 0.80))
    d.add("hairline", cels.soft(np.vstack([line_, (line_ + [0.0, -0.035])[::-1]]), HAIR_SHADE, spread=0.03,
                                opacity=0.45, smooth=False), mask=("skin",))
    d.add("hair", cap)
    # the back of the head away from the light, the hair under the bun; light on the top of the head
    d.add("hair_shade",
          cels.soft([(0.24, 1.2), (0.27, 0.96), (0.30, 0.78), (0.33, 0.6), (0.36, 0.38), (0.65, 0.38), (0.65, 1.2)],
                    HAIR_SHADE, spread=0.08, opacity=0.95, step=0.015),
          Fill(np.array([(0.36, 0.38), (0.6, 0.38), (0.6, 0.62), (0.42, 0.6)]), HAIR_DEEP, opacity=0.6),
          cels.soft([(-0.3, 0.8), (-0.2, 0.86), (0.2, 0.82), (0.3, 0.75), (0.4, 0.6), (0.45, 0.45), (0.3, 0.6),
                     (0.15, 0.78), (-0.2, 0.83)], HAIR_SHADE, spread=0.04, opacity=0.45, step=0.015),
          blob((-0.06, 1.02), 0.2, 0.06, HAIR_LIGHT, spread=0.08, opacity=0.55, rotate=12),
          mask=("hair",))
    # the comb's track: strands from the hairline back to the bun, in sections
    sections = [
        # (hairline run, where it gathers by the bun, count)
        ([(-0.27, 0.80), (-0.22, 0.83), (-0.14, 0.855), (-0.06, 0.865)], [(0.04, 1.105), (0.14, 1.105), (0.22, 1.09),
                                                                         (0.27, 1.07)], 70),
        ([(-0.06, 0.865), (0.04, 0.862), (0.12, 0.84), (0.20, 0.79)], [(0.25, 1.07), (0.28, 1.04), (0.29, 1.0),
                                                                      (0.28, 0.96)], 55),
        ([(0.20, 0.79), (0.23, 0.70), (0.27, 0.60), (0.32, 0.565)], [(0.28, 0.95), (0.29, 0.92), (0.30, 0.9),
                                                                    (0.31, 0.88)], 45),
        ([(0.32, 0.565), (0.375, 0.535), (0.392, 0.47), (0.385, 0.40)], [(0.32, 0.88), (0.38, 0.87), (0.43, 0.86),
                                                                        (0.46, 0.84)], 45),
    ]
    strands = []
    for k, (a, b, n) in enumerate(sections):
        A, B = cels.spline(a), cels.spline(b)
        strands += cels.strands(A, B, n, width=W_HAIR, seed=200 + k, reach=(0.0, 1.0), jitter=0.9, bow=0.06,
                                colors=[HAIR_LINE, HAIR_SHADE, HAIR_SHADE, HAIR_DEEP], opacity=(0.25, 0.7))
        strands += cels.strands(A, B, n // 3, width=W_HAIR * 1.3, seed=210 + k, reach=(0.1, 0.8), jitter=1.0,
                                bow=0.06, colors=[HAIR_SHEEN, HAIR_LIGHT], opacity=(0.5, 0.95))
    d.add("hair_strands", strands, mask=("hair",))
    # the partings between the sections
    d.add("hair_strands",
          ink([(-0.06, 0.865), (0.04, 0.98), (0.16, 1.06), (0.25, 1.075)], W_HAIR * 1.6, HAIR_DEEP, seed=220,
              opacity=0.8),
          ink([(0.20, 0.79), (0.24, 0.88), (0.28, 0.98)], W_HAIR * 1.6, HAIR_DEEP, seed=221, opacity=0.8),
          ink([(0.32, 0.565), (0.31, 0.7), (0.30, 0.86)], W_HAIR * 1.4, HAIR_DEEP, seed=222, opacity=0.7),
          mask=("hair",))
    # the sheen: long thin streaks along the strands, broken, where the sky catches the crown
    sheen = []
    rng = np.random.default_rng(225)
    for pts, w, n in (([(-0.26, 0.88), (-0.15, 0.99), (-0.01, 1.06), (0.12, 1.09)], 0.05, 16),
                      ([(-0.15, 0.875), (-0.04, 0.94), (0.08, 0.99), (0.2, 1.01)], 0.035, 11)):
        c = cels.spline(pts)
        for j in range(n):
            u0 = rng.uniform(0.0, 0.75)
            u1 = min(1.0, u0 + rng.uniform(0.12, 0.3))
            seg = c[int(len(c) * u0):int(len(c) * u1)]
            if len(seg) < 4:
                continue
            seg = seg + cels.normals(seg) * rng.uniform(-w / 2, w / 2)
            sheen.append(Line(seg, W_HAIR * rng.uniform(1.2, 2.6), HAIR_SHEEN, cels.taper(seg, 0.4, 0.4, tip=0.0),
                              False, float(rng.uniform(0.5, 0.95))))
    d.add("hair_light", sheen, mask=("hair",))
    # the contour: shadow side heavier; the lit hairline thin and broken
    d.add("hair_lines",
          ink(cels.between(cap.points, (0.385, 0.40), (-0.27, 0.80)), W_OUT * 0.85, HAIR_LINE, seed=230,
              taper_=(0.04, 0.08), tip=0.3, smooth=False),
          *broken(cels.between(cap.points, (-0.27, 0.80), (0.20, 0.79)), W_FINE, HAIR_LINE,
                  gaps=((0.25, 0.4), (0.62, 0.7)), seed=231, opacity=0.8),
          ink(cels.between(cap.points, (0.20, 0.79), (0.385, 0.40)), W_FINE, HAIR_LINE, seed=232,
              taper_=(0.15, 0.15), tip=0.2, smooth=False))

    _bun(d)

    # wisps: damp ones stuck at the temples and nape, dry flyaways over the crown stirring in the wind
    sw = 3.0 * gust + 1.5 * flick
    wisps = []
    for root, mid, tip, w, s, col in (((0.205, 0.80), (0.232, 0.71), (0.236, 0.60), 0.012, 1.0, HAIR_DAMP),
                                      ((0.215, 0.775), (0.224, 0.70), (0.206, 0.635), 0.008, 1.2, HAIR),
                                      ((-0.262, 0.815), (-0.288, 0.75), (-0.305, 0.69), 0.01, 0.6, HAIR_DAMP),
                                      ((0.40, 0.46), (0.44, 0.40), (0.468, 0.33), 0.01, 1.1, HAIR_DAMP)):
        r_, m_, t_ = (np.asarray(v, float) for v in (root, mid, tip))
        m_, t_ = cels.bend([m_, t_], r_, sw * s * 0.4, power=1.2)
        c = cels.spline([r_, m_, t_])
        u = np.linspace(0, 1, len(c))
        nrm = cels.normals(c)
        for j, off in enumerate(np.linspace(-0.5, 0.5, 4)):
            P = c + nrm * (off * w * (1 - u) ** 0.8)[:, None]
            wisps.append(Line(P, W_HAIR * (1.3 if j % 2 else 1.0), (col, HAIR_LINE, HAIR_SHEEN, col)[j],
                              cels.taper(P, 0.1, 0.6, tip=0.0), False, 0.9))
    rng = np.random.default_rng(250)
    for j, (root, ang, ln) in enumerate((((0.02, 1.105), 160, 0.07), ((0.12, 1.1), 140, 0.06),
                                         ((-0.12, 1.06), 175, 0.05), ((0.3, 1.06), 110, 0.05),
                                         ((0.44, 0.9), 40, 0.05))):
        a = math.radians(ang + sw * 3)
        r_ = np.asarray(root, float)
        tip = r_ + ln * np.array([math.cos(a), math.sin(a)])
        mid = (r_ + tip) / 2 + rng.uniform(-0.012, 0.012, 2)
        wisps.append(ink([r_, mid, tip], W_HAIR * 0.9, (HAIR_LIGHT, HAIR_SHADE)[j % 2], seed=260 + j,
                         taper_=(0.1, 0.7), opacity=0.85))
    d.add("wisps", wisps)


def _bun(d: cels.Drawing):
    """Her bun: the hair twisted and wound round itself into a ball at the back of her crown, strands running round
    it with the winding, two turns of the twist standing out as ridges with a shadow under each, the tucked end
    across it; shaded round from the light like a ball; the wooden pin pushed through it (both ends showing), its
    shadow on the hair."""
    c = np.array(BUN)
    rx, ry = BUN_R
    rot = BUN_ROT
    wind = 32.0                 # the winding's slant, degrees
    pin_a, pin_b = np.array(PIN_A), np.array(PIN_B)
    dirn = (pin_b - pin_a) / np.linalg.norm(pin_b - pin_a)
    th = np.linspace(0, 2 * math.pi, 120, endpoint=False)
    lump = 1 + 0.04 * np.sin(3 * th + 0.6) + 0.022 * np.sin(5 * th + 1.3)

    def ball(k: float, shift=(0.0, 0.0)) -> np.ndarray:
        return cels.move(np.c_[rx * k * lump * np.cos(th), ry * k * lump * np.sin(th)], c + np.asarray(shift),
                         rotate=rot)

    def band(o: float, a0: float = -80, a1: float = 80) -> np.ndarray:
        """A strand's path round the ball: the visible half of a slice across it `o` (-1..1) off its middle,
        slanted with the winding."""
        r = math.sqrt(max(0.0, 1 - o * o))
        a = np.radians(np.linspace(a0, a1, 40))
        # the slice is seen nearly edge on: a curve bowing toward the light side
        P = np.c_[o * 0.92 - 0.32 * r * np.cos(a), r * np.sin(a)]
        P = P @ np.array([[math.cos(math.radians(wind)), math.sin(math.radians(wind))],
                          [-math.sin(math.radians(wind)), math.cos(math.radians(wind))]])
        return cels.move(P * [rx, ry], c, rotate=rot)

    bun = ball(1.0)
    # the bun's shadow on the hair under it
    d.add("hair_shade", cels.soft(ball(1.0, (0.035, -0.05)), HAIR_DEEP, spread=0.04, opacity=0.6), mask=("hair",))
    seg = pin_a + np.linspace(0, 1, 30)[:, None] * (pin_b - pin_a)
    pin = cels.ribbon(seg, 0.022 * (1.0 - 0.45 * np.linspace(0, 1, 30)))
    knob = cels.ellipse(pin_a - dirn * 0.01, 0.022, 0.017, rotate=math.degrees(math.atan2(dirn[1], dirn[0])))
    d.add("pin", Fill(pin, PIN), Fill(cels.ribbon(seg + cels.normals(seg) * -0.005, 0.008), PIN_SHADE),
          Fill(cels.ribbon(seg + cels.normals(seg) * 0.006, 0.004), PIN_LIGHT, opacity=0.8),
          ink(np.vstack([pin, pin[:2]]), W_FINE, POLE_LINE, seed=270, taper_=(0.02, 0.02), tip=1.0, smooth=False),
          Fill(knob, PIN), Line(knob, W_FINE, POLE_LINE, closed=True))
    d.add("bun", Fill(bun, HAIR))
    # round like a ball: the side away from the light and its underside in shade, the top lit
    shade = [*cels.soft(np.vstack([ball(1.3, (0.0, 0.0))[60:110], ball(0.6, (0.06, -0.03))[110:59:-1]]), HAIR_SHADE,
                        spread=0.07, opacity=0.85, smooth=False),
             *blob(c + [0.06, -0.07], 0.06, 0.03, HAIR_DEEP, spread=0.05, opacity=0.55, rotate=rot),
             *blob(c + [-0.04, 0.05], 0.06, 0.035, HAIR_LIGHT, spread=0.05, opacity=0.6, rotate=rot + 30)]
    # the strands wound round it, mixed tones, a few catching the light
    rng = np.random.default_rng(280)
    wound = []
    for k in range(70):
        o = rng.uniform(-0.98, 0.98)
        a0, a1 = rng.uniform(-85, -30), rng.uniform(20, 85)
        col = (HAIR_LINE, HAIR_SHADE, HAIR_DEEP, HAIR_SHEEN, HAIR_LIGHT)[int(rng.integers(5))]
        P = band(o, a0, a1)
        wound.append(Line(P, W_HAIR * rng.uniform(0.7, 1.2), col, cels.taper(P, 0.3, 0.3, tip=0.0), False,
                          float(rng.uniform(0.35, 0.8))))
    # two turns of the twist standing out, each with a shadow on the far side of its ridge
    ridges = []
    for o, s in ((-0.35, 291), (0.3, 292)):
        P = band(o, -88, 70)
        Pn = band(o + 0.1, -88, 70)
        ridges += cels.soft(np.vstack([P, Pn[::-1]]), HAIR_SHADE, spread=0.015, opacity=0.7, smooth=False)
        ridges.append(ink(P, W_FINE, HAIR_LINE, seed=s, taper_=(0.3, 0.3)))
        ridges.append(ink(band(o - 0.06, -60, 30), W_HAIR * 1.5, HAIR_SHEEN, seed=s + 5, taper_=(0.3, 0.4),
                          opacity=0.8))
    # the tucked end crossing under the top turn
    tuck = cels.move(cels.spline([(-0.55 * rx, 0.45 * ry), (-0.1 * rx, 0.62 * ry), (0.35 * rx, 0.5 * ry)]), c,
                     rotate=rot)
    ridges.append(ink(tuck, W_FINE, HAIR_LINE, seed=293, taper_=(0.1, 0.7)))
    d.add("bun_shade", shade, wound, ridges, mask=("bun",))
    # where the pin comes out of the far side: the hair dimpled round it
    q = seg[int(len(seg) * 0.72)]
    dim = cels.arc(q, 0.02, 0.012, 200, 340, rotate=math.degrees(math.atan2(dirn[1], dirn[0])) + 90, n=16)
    d.add("bun_lines", ink(dim, W_HAIR * 1.3, HAIR_LINE, seed=295, smooth=False),
          ink(np.vstack([bun, bun[:2]]), W_OUT * 0.7, HAIR_LINE, seed=296, taper_=(0.02, 0.02), tip=1.0,
              wobble=0.35, smooth=False))
    # the pin's far end over the bun
    far_seg = seg[int(len(seg) * 0.7):]
    pin_far = cels.ribbon(far_seg, 0.022 * (1.0 - 0.45 * np.linspace(0.7, 1, len(far_seg))))
    d.add("pin_front", Fill(pin_far, PIN), Fill(cels.ribbon(far_seg + cels.normals(far_seg) * -0.005, 0.007),
                                                PIN_SHADE),
          ink(np.vstack([pin_far, pin_far[:2]]), W_FINE, POLE_LINE, seed=297, taper_=(0.02, 0.02), tip=1.0,
              smooth=False))


# ---------------------------------------------------------------------------------------------------- the pole

def _pole(d: cels.Drawing, t: float, *, x: float, width: float, y0: float, y1: float, joints=(), layer: str = "pole",
          w_out: float = W_IN, w_in: float = W_FINE, wet: bool = True):
    """The bamboo pole standing upright, weathered: lit on its left, shaded on its right, ringed at its joints, the
    rain running down it in streaks and gathering in drops at the joints."""
    w = width / 2
    body = Fill(np.array([[x - w, y0], [x + w, y0], [x + w, y1], [x - w, y1]]), POLE)
    d.add(layer, body)
    shade = [Fill(np.array([[x + w * 0.1, y0], [x + w * 1.1, y0], [x + w * 1.1, y1], [x + w * 0.1, y1]]), POLE_SHADE),
             *cels.soft(np.array([[x - w * 0.2, y0], [x + w * 0.3, y0], [x + w * 0.3, y1], [x - w * 0.2, y1]]),
                        POLE_SHADE, spread=w * 0.6, opacity=0.6, smooth=False),
             Fill(np.array([[x - w * 0.72, y0], [x - w * 0.48, y0], [x - w * 0.48, y1], [x - w * 0.72, y1]]),
                  POLE_LIGHT, opacity=0.8)]
    rng = np.random.default_rng(300)
    # weathering: fine grain along it
    for j in range(int(abs(y1 - y0) * 6)):
        xx = x + rng.uniform(-0.8, 0.8) * w
        ya = rng.uniform(y0, y1)
        shade.append(Line(np.array([[xx, ya], [xx, ya + rng.uniform(0.05, 0.25) * width * 6]]), w_in * 0.6,
                          POLE_SHADE if xx < x else POLE_LINE, np.array([0.2, 1.0]), False, 0.5))
    if wet:
        for j in range(4):
            xx = x + rng.uniform(-0.6, 0.3) * w
            ya = rng.uniform(y0, y1 - 0.3)
            yb = ya + rng.uniform(0.15, 0.5)
            shade.append(Line(np.array([[xx, yb], [xx + 0.002, ya]]), w * 0.18, WET, np.array([0.3, 1.0]), False,
                              0.55))
    d.add(layer + "_shade", shade, mask=(layer,))
    lines = [ink([(x - w, y0), (x - w, y1)], w_out * 0.8, POLE_LINE, seed=301, taper_=(0.0, 0.02), tip=1.0,
                 smooth=False),
             ink([(x + w, y0), (x + w, y1)], w_out, POLE_LINE, seed=302, taper_=(0.0, 0.02), tip=1.0, smooth=False)]
    for k, j in enumerate(joints):
        ring = cels.arc((x, j), w * 1.04, w * 0.25, 200, 340, n=24)
        lines += [Line(ring, w_in, POLE_LINE, cels.taper(ring, 0.1, 0.1, tip=0.5)),
                  Line(ring + [0.0, width * 0.24], w_in * 0.7, POLE_LINE, cels.taper(ring, 0.2, 0.2, tip=0.2))]
        if wet:
            lines += cels.drip((x + w * 0.3, j - w * 0.25), t, period=1.7 + 0.4 * k, r=w * 0.28, fall=0.18,
                               phase=0.3 * k, body=WATER, light=WET, ink=POLE_LINE)
    d.add(layer + "_lines", lines)


# ---------------------------------------------------------------------------------------------------- the figure

def full(t: float = 0.0, flash: float = 0.0) -> cels.Drawing:
    """Her whole figure for the wide shot, in metres: feet on y = 0, facing left, the pole upright in her right hand."""
    d = _full(t)
    if flash > 0:
        d.recolor(lambda c: cels.flash(c, flash, KINDS.get(c, "lit")))
    return d


F_OUT = 0.012        # the wide shot's contour, metres
F_IN = 0.0075        # its inner lines
F_FINE = 0.0045
CHIN_AT = (-0.13, 1.17)    # where her chin is in the figure: her head carried forward and low, as the old do
TILT = 10.0                # her head bowed forward, degrees


def _hu(P) -> np.ndarray:
    """Head units to the figure's metres: her head on her shoulders, bowed a little forward."""
    P = cels._arr(P)
    return cels.move(P - np.asarray(CHIN, float), offset=CHIN_AT, scale=HEAD, rotate=TILT)


def _full(t: float) -> cels.Drawing:
    d = cels.Drawing()
    gust = math.sin(2 * math.pi * t * 0.7 + 0.9)
    flick = math.sin(2 * math.pi * t * 2.1 + 1.7)
    sw = 1.5 * gust + 0.7 * flick

    # her shadow on the wet boards, darker toward the pole she leans on
    d.add("ground", cels.soft(cels.ellipse((-0.02, 0.006), 0.25, 0.02, n=48), GROUND, spread=0.05, opacity=0.6,
                              smooth=False),
          blob((-0.2, 0.004), 0.06, 0.012, GROUND, spread=0.02, opacity=0.5))

    # ---- her feet in straw sandals: the front one (toward the pole) showing its toes under the hem, the back one
    # only its heel
    sole = fill([(-0.215, 0.0), (-0.07, 0.0), (-0.07, 0.016), (-0.22, 0.016)], STRAW, corners=(0, 1, 2, 3))
    toes = fill([(-0.13, 0.016), (-0.205, 0.016), (-0.215, 0.026), (-0.19, 0.04), (-0.13, 0.042)], SKIN, corners=(0, 1))
    heel = fill([(0.06, 0.0), (0.155, 0.0), (0.155, 0.014), (0.06, 0.014)], STRAW_SHADE, corners=(0, 1, 2, 3))
    d.add("feet", sole, heel, toes,
          ink(np.vstack([sole.points, sole.points[:2]]), F_FINE, STRAW_LINE, seed=430, taper_=(0.01, 0.01), tip=1.0,
              smooth=False),
          ink(np.vstack([heel.points, heel.points[:2]]), F_FINE, STRAW_LINE, seed=431, taper_=(0.01, 0.01), tip=1.0,
              smooth=False),
          ink(toes.points[1:-1], F_FINE, SKIN_LINE, seed=432, smooth=False),
          ink([(-0.185, 0.018), (-0.17, 0.034), (-0.15, 0.04)], F_FINE * 0.9, CORD, seed=434))

    # ---- the kimono over a body: the front knee bent toward the pole and the cloth breaking over it, the back leg
    # straight, folds hanging from the sash, the hem pooling a little over her sandals, soaked dark at the bottom
    hem = 0.008 * gust + 0.004 * flick
    kimono = fill([(-0.12, 1.08), (-0.15, 0.95), (-0.155, 0.8), (-0.165, 0.65), (-0.192, 0.5), (-0.182, 0.4),
                   (-0.162, 0.28), (-0.16, 0.15), (-0.178 + hem, 0.06), (-0.195 + hem, 0.03), (-0.15 + hem, 0.024),
                   (-0.12 + hem, 0.043), (-0.075 + hem, 0.03), (0.0 + hem, 0.02), (0.08 + hem, 0.025),
                   (0.155 + hem, 0.025), (0.146, 0.15), (0.158, 0.3), (0.198, 0.47), (0.214, 0.62), (0.208, 0.8),
                   (0.19, 1.0), (0.16, 1.08)], CLOTH, corners=(9, 15))
    d.add("kimono", kimono)
    folds = [((-0.17, 0.48), (-0.1, 0.36), (-0.04, 0.22)), ((-0.165, 0.44), (-0.125, 0.3), (-0.105, 0.1)),
             ((0.08, 0.6), (0.07, 0.32), (0.09, 0.04)), ((0.03, 0.55), (0.0, 0.27), (-0.02, 0.05)),
             ((-0.06, 0.62), (-0.08, 0.5), (-0.13, 0.46))]
    breaks = [((-0.125, 0.1), (-0.105, 0.06), (-0.11, 0.035)), ((-0.035, 0.1), (-0.045, 0.06), (-0.035, 0.025)),
              ((0.05, 0.11), (0.065, 0.06), (0.06, 0.03)), ((0.12, 0.09), (0.125, 0.05))]
    d.add("kimono_shade",
          cels.soft([(0.04, 1.2), (0.05, 0.6), (0.03, 0.0), (0.4, 0.0), (0.4, 1.2)], CLOTH_SHADE, spread=0.06,
                    opacity=0.9, smooth=False),
          # the hollow behind the bent knee, between the legs
          cels.soft([(-0.08, 0.56), (0.03, 0.56), (0.05, 0.25), (-0.03, 0.2), (-0.1, 0.35)], CLOTH_WET, spread=0.05,
                    opacity=0.75, smooth=False),
          # the knee and the shin in front lit
          blob((-0.172, 0.49), 0.02, 0.035, CLOTH_LIGHT, spread=0.03, opacity=0.8),
          cels.soft([(-0.17, 0.42), (-0.13, 0.4), (-0.12, 0.12), (-0.165, 0.12)], CLOTH_LIGHT, spread=0.03,
                    opacity=0.5, smooth=False),
          cels.soft([(-0.3, 0.17), (0.4, 0.17), (0.4, -0.1), (-0.3, -0.1)], CLOTH_WET, spread=0.12, opacity=0.8,
                    smooth=False),
          *[ink(f, F_FINE, CLOTH_LINE, seed=400 + j, taper_=(0.35, 0.3), opacity=0.85) for j, f in enumerate(folds)],
          *[ink(np.asarray(f) + [-0.006, 0.0], F_FINE * 0.8, CLOTH_LIGHT, seed=410 + j, taper_=(0.4, 0.4), opacity=0.7)
            for j, f in enumerate(folds[:2])],
          *[ink(f, F_FINE * 0.8, CLOTH_LINE, seed=415 + j, taper_=(0.3, 0.5), opacity=0.8) for j, f in enumerate(breaks)],
          mask=("kimono",))
    # the sash across her middle, seen in the cape's opening
    d.add("kimono_shade", Fill(np.array([(-0.16, 0.82), (0.2, 0.83), (0.2, 0.89), (-0.16, 0.885)]), "#3b302b"),
          Line(np.array([(-0.16, 0.855), (0.2, 0.86)]), F_FINE * 0.8, CLOTH_LINE, None, False, 0.7), mask=("kimono",))
    d.add("kimono_lines",
          ink(np.vstack([kimono.points, kimono.points[:2]]), F_IN, CLOTH_LINE, seed=420, taper_=(0.01, 0.01),
              tip=1.0, wobble=0.3, smooth=False),
          ink([(-0.09, 0.82), (-0.1, 0.6), (-0.135, 0.45), (-0.12, 0.25), (-0.14, 0.04)], F_FINE, CLOTH_LINE,
              seed=421, taper_=(0.3, 0.1)),
          # the pale under-kimono showing at the hem
          ink([(-0.19 + hem, 0.034), (-0.12 + hem, 0.05), (-0.07 + hem, 0.036)], F_FINE * 1.4, UNDER_SHADE, seed=422,
              taper_=(0.2, 0.2)))

    # ---- the head, its neck under the cape's collar
    head = head_outline()
    hd = cels.Drawing()
    _neck(hd, head)
    _face(hd, head, t, 0.55, 0.0, gust)
    _hair_bust(hd, t, gust, flick)
    k = HEAD * 2.6                                  # a line's width at her size in the wide: heavier than scaled
    for L in hd.layers.values():
        for p in L.pieces:
            p.points = _hu(p.points)
            if isinstance(p, Line):
                p.width *= k
    for name in ("neck", "neck_shade", "neck_lines"):
        d.layers[name] = hd.layers.pop(name)
    for name in ("face_wet", "skin_wet", "eye_age", "hairline", "brow_tone", "eye_soft"):
        hd.layers.pop(name, None)

    # ---- the straw cape on narrow, rounded shoulders and the stoop of her back, open down the front, uneven tiers,
    # the hem longer behind; her right arm comes out of its front, the sleeve hanging heavy, to the pole
    u = 0.24
    near_sil = [(-0.085, 1.11), (-0.03, 1.15), (0.05, 1.165), (0.13, 1.145), (0.195, 1.08), (0.225, 0.98),
                (0.24, 0.85), (0.25, 0.7), (0.26, 0.55), (0.27, 0.42), (0.275, 0.35)]
    near_edges = [[(-0.075, 1.05), (-0.01, 1.07), (0.07, 1.09), (0.13, 1.085), (0.19, 1.078)],
                  [(-0.07, 0.93), (0.0, 0.95), (0.08, 0.91), (0.15, 0.93), (0.21, 0.89), (0.233, 0.88)],
                  [(-0.068, 0.75), (0.02, 0.73), (0.1, 0.76), (0.17, 0.72), (0.24, 0.68), (0.252, 0.67)],
                  [(-0.066, 0.6), (0.02, 0.585), (0.1, 0.55), (0.17, 0.49), (0.24, 0.41), (0.274, 0.36)]]
    far_sil = [(-0.105, 1.11), (-0.14, 1.09), (-0.17, 1.04), (-0.19, 0.97), (-0.205, 0.9), (-0.21, 0.8),
               (-0.2, 0.7), (-0.195, 0.62), (-0.19, 0.56)]
    far_edges = [[(-0.11, 1.05), (-0.14, 1.045), (-0.165, 1.035), (-0.18, 1.0)],
                 [(-0.11, 0.92), (-0.15, 0.94), (-0.19, 0.9), (-0.205, 0.88)],
                 [(-0.105, 0.76), (-0.15, 0.74), (-0.2, 0.73), (-0.207, 0.72)],
                 [(-0.1, 0.62), (-0.14, 0.6), (-0.18, 0.58), (-0.19, 0.56)]]
    kw = dict(t=t, sway=sw, tip=0.03, w_line=F_FINE, w_fibre=0.0032, w_out=F_FINE * 1.4, drip_r=0.006,
              frame_bottom=-1.0, fibres=1.2, u=u)
    straw_cape(d, "fcape_n", near_sil, near_edges, seed=21, counts=[5, 7, 7, 9], lump=0.05, tuft=12, strays=4,
               shade_from=0.3, dark=[(0.05, 1.4), (0.6, 1.4), (0.6, 0.2), (0.08, 0.2)],
               light=[(-0.085, 1.12), (0.08, 1.18), (0.15, 1.12), (0.0, 1.05)], **kw)

    def place(P):
        return cels.move(cels._arr(P), (-0.255, 1.07), scale=HEAD * 0.9, rotate=GRIP)

    sleeve = [(-0.205, 1.07), (-0.17, 1.055), (-0.125, 1.0), (-0.098, 0.95), (-0.1, 0.86), (-0.13, 0.79),
              (-0.165, 0.765), (-0.205, 0.81), (-0.222, 0.92), (-0.222, 1.0)]
    sfolds = [(-0.19, 1.05), (-0.15, 1.02), (-0.115, 0.96), (-0.215, 0.95)]
    cuff = (place([(0.31, 0.0)])[0], 0.006, 0.02, GRIP)
    straw_cape(d, "fcape_f", far_sil, far_edges, seed=31, counts=[3, 4, 4, 4], lump=0.04, tuft=6, strays=2,
               shade_from=0.9, light=[(-0.105, 1.12), (-0.17, 1.06), (-0.13, 1.0), (-0.09, 1.05)],
               between={0: lambda d_: _sleeve(d_, sleeve, sfolds, cuff, (-0.17, 0.77), t, k=HEAD, prefix="f")},
               **kw)
    knot = _hu([(0.012, -0.25)])[0]
    d.add("fcape_cord", Fill(cels.ellipse(knot, 0.007, 0.006), CORD))

    # ---- the head over it all
    for name, L in hd.layers.items():
        d.layers[name] = L

    # ---- the pole, upright in her right hand, and the hand round it
    _pole(d, t, x=-0.255, width=0.03, y0=0.0, y1=2.40, joints=(0.38, 0.84, 1.30, 1.76, 2.22), layer="fpole",
          w_out=F_IN, w_in=F_FINE)
    _hand(d, place, HEAD * 2.6, t, prefix="f", pole="fpole")
    _thin(d, n=5)
    return d


def fullsheet(t: float) -> cels.Drawing:
    """For cel sheets of the figure: t < 3 as drawn at t, 3.. the flash at its height."""
    return full(t) if t < 3 else full(t, flash=1.0)


def eyesheet(t: float) -> cels.Drawing:
    """For cel sheets of the River Demon's open: t < 1 at 0.55, 1..2 at 0.7, 2..3 at 0.85, 3.. at 1."""
    return closeup(t, eyes=(0.55, 0.7, 0.85, 1.0)[min(3, int(t))])


def sheet(t: float) -> cels.Drawing:
    """For cel sheets: t < 1 calm (half-lidded), 1..2 between, 2..3 the demon's look, 3.. the flash at its height."""
    if t < 1:
        return closeup(t)
    if t < 2:
        return closeup(t, eyes=0.78)
    if t < 3:
        return closeup(t, eyes=1.0)
    return closeup(t, flash=1.0)


def face(t: float) -> cels.Drawing:
    """For close cel sheets of the face: t < 1 calm, 1.. sharp."""
    return closeup(t, eyes=0.55 if t < 1 else 1.0)
