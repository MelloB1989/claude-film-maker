"""Shinza drawn whole: the full figure for the standoff's wide shot, as a 2D anime drawing (blender/lib/cels.py), in
the close-up's design and palette (rf/shinza_cels.py), drawn toward a film's realism rather than a TV sticker's.

A low guard on the wet pier, built on a skeleton at about seven and a half heads: his weight sunk into the bent right
knee, the left leg stretched back on the ball of its foot, his trunk leaning in from the hips, shoulders down, elbows
in, both hands on the hilt (the right behind the guard, the left at the pommel) and the blade carrying on forward and
down toward her shins. His sleeves are bound up with a pale cord, his forearms bare; the empty scabbard angles back
from his left hip; his tied hair and the band's frayed tails stream back in the wind. Everything is soaked: the
cloth dark and clinging, the hems heavy and dripping, water running off the blade's point.

Drawn as a film's key animator would: coloured lines (warm brown on skin, blue-black on hair, a darker shade of each
cloth), heavier where an edge turns from the light and lifted where it faces it (`cels.contour`); the cloth's form in
a base, a shade and a deep shade with airbrushed gradients (`cels.soft`), its folds following the pose. Light: soft
and overcast from above; rims, haze and the scene's grade come from compositing.

Metres: feet on y = 0, his hips over x ~ 0.07, facing right (+x) toward Tsuru, his right side to us.
"""
from __future__ import annotations

import math

import numpy as np

from lib import cels
from lib.cels import Fill, Line, fill, line

from .shinza_cels import (BAND, BAND_SHADE, CLOTH, CLOTH_DEEP, CLOTH_SHADE, CLOTH_SHEEN, HAIR, HAIR_SHADE,
                          HAIR_SHEEN, INK, IRIS_DARK, KINDS, LINE_BAND, LINE_CLOTH, LINE_HAIR, LINE_SKIN, SKIN,
                          SKIN_DEEP, SKIN_LIGHT, SKIN_SHADE, UNDER, UNDER_SHADE, WATER)

HEIGHT = 1.78


# the cloth and gear, each with its shade, deep shade and the lines drawn round it
HAKAMA = "#2c2b33"         # charcoal, a shade warmer than the kimono's blue-grey: the two read apart
HAKAMA_SHADE = "#1b1a21"
HAKAMA_DEEP = "#111016"
HAKAMA_LIGHT = "#4f4d58"
HAKAMA_WET = "#16151b"
CLOTH_LIGHT = CLOTH_SHEEN
OBI = "#3a3530"
OBI_SHADE = "#221f1c"
BOARD = "#3a3842"
STEEL = "#c9d1de"
STEEL_LIGHT = "#f2f5fa"
STEEL_SHADE = "#7d889e"
WRAP = "#2b2724"
WRAP_LIGHT = "#5a5249"
SAME = "#b9b2a2"     # the ray skin under the hilt's wrap
IRON = "#3a3836"
BRASS = "#9c824c"
LACQUER = "#17171d"
LACQUER_SHEEN = "#4a4e60"
STRAW = "#7a6846"
STRAW_SHADE = "#4f4230"
STRAP = "#8f8162"           # the sandals' straw cords
MUD = "#2a231b"
CORD = "#7c776d"
CORD_SHADE = "#4f4b44"
GROUND = "#0b0d14"          # his shadow on the wet planks

L_SKIN = LINE_SKIN          # the close-up's lines, so the two drawings are one hand's
L_HAIR = LINE_HAIR
L_CLOTH = LINE_CLOTH
L_STEEL = "#384052"
L_BAND = LINE_BAND
L_STRAW = "#40331d"
L_UNDER = "#585a6e"
L_CORD = "#4d4840"

KINDS_FULL = {**KINDS, HAKAMA: "shade", HAKAMA_SHADE: "shade", HAKAMA_DEEP: "shade", HAKAMA_LIGHT: "shade",
              HAKAMA_WET: "shade", CLOTH_DEEP: "shade", OBI: "shade", OBI_SHADE: "shade", BOARD: "shade",
              STEEL_SHADE: "shade", WRAP: "shade", IRON: "shade", LACQUER: "ink", LACQUER_SHEEN: "shade",
              STRAW_SHADE: "shade", CORD_SHADE: "shade", MUD: "shade", IRIS_DARK: "ink", GROUND: "ink",
              L_SKIN: "ink", L_HAIR: "ink", L_CLOTH: "ink", L_STEEL: "ink", L_BAND: "ink", L_STRAW: "ink",
              L_UNDER: "ink", L_CORD: "ink"}

W_OUT = 0.0075    # the silhouette: about 2 px at his size in the wide
W_IN = 0.0045     # folds and parts inside
W_FINE = 0.003    # the face, fingers, cords

LIGHT = (0.25, 1.0)   # overcast, from above and a little ahead of him

# ------------------------------------------------------------------------------------------------ the skeleton
PELVIS = np.array([0.07, 0.79])
LEAN = 14.0                                   # the trunk's lean in from the hips, degrees
SHOULDER = np.array([0.13, 1.335])            # his right (near) shoulder
ELBOW = np.array([0.236, 1.05])
SWORD_ANGLE = -28.0
POMMEL = np.array([0.30, 0.935])
HILT = 0.26
BLADE = 0.70
HU = 0.237                                    # a head, chin to crown
CHIN_AT = np.array([0.298, 1.392])            # the head's chin (head units (0.18, 0)) on the figure
HEAD_TILT = -8.0                              # chin down: he watches her from under his brow


def _dir(deg: float) -> np.ndarray:
    return np.array([math.cos(math.radians(deg)), math.sin(math.radians(deg))])


AX = _dir(SWORD_ANGLE)                        # along the sword, toward its point
UP = np.array([-AX[1], AX[0]])                # across it, the back's side
GUARD = POMMEL + AX * HILT


def _hilt(u: float, v: float) -> np.ndarray:
    """A point in the hilt's frame: u along it from the guard (negative toward the pommel), v across it."""
    return GUARD + AX * u + UP * v


def _H(P) -> np.ndarray:
    """Head units (chin at (0.18, 0), crown at y ~ 1) into metres on the figure."""
    return cels.move(P, offset=CHIN_AT - (0.18, 0.0), scale=HU, rotate=HEAD_TILT, about=(0.18, 0.0))


def _part(d: cels.Drawing, name: str, *fills, shades=(), lines=(), color=L_CLOTH, width: float = W_OUT,
          outline: bool = True, light=LIGHT):
    """A part of the figure: its fills, its shading clipped to them, its contour weighted by the light, its lines."""
    d.add(name, *fills)
    if shades:
        d.add(name + "_shade", *shades, mask=(name,))
    ink = [cels.contour(f.points, width, color, light=light) for f in fills] if outline else []
    if ink or lines:
        d.add(name + "_ink", *ink, *lines)


def _fold(points, color=L_CLOTH, width=W_IN, *, taper_=(0.35, 0.45), seed=0, opacity=1.0, tip=0.0):
    """A fold line in cloth: tapered at both ends, a little uneven, as a brush draws it."""
    P = cels.spline(points)
    w = cels.taper(P, *taper_, tip=tip) * cels.pressure(P, amount=0.25, waves=2.0, seed=seed)
    return Line(P, width, color, w, False, opacity)


def _glint(points, *, seed=0, width=W_IN * 1.3, opacity=0.45, color=HAKAMA_LIGHT) -> list:
    """The lit ridge beside a fold: wet cloth catching the grey sky in a broken streak."""
    return cels.brush(points, width, color, gaps=((0.3, 0.42),), seed=seed, taper_=(0.4, 0.4), tip=0.0,
                      opacity=opacity)


def _hem(a, b, count: int, depth: float = 0.007, seed: int = 0) -> list:
    """Points along a hem from `a` to `b` (both left out), dipping between the pleats' ends: `count` scallops."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.default_rng(seed)
    out = []
    for k in range(1, 2 * count):
        u = k / (2 * count)
        out.append(tuple(a + (b - a) * u + (0.0, -depth * (k % 2) * rng.uniform(0.6, 1.3))))
    return out


def _sandal(d: cels.Drawing, name: str, sole_c, foot: Fill, shades, cords, loops) -> None:
    """A bare foot in a straw sandal: the woven sole under it with its thickness showing, muddy below; the foot with
    its shading; the straw cords from the toe thong through the side loops, over the instep and round the ankle."""
    sole = cels.ribbon(sole_c, 0.014)
    x0, x1 = sole_c[:, 0].min() - 0.01, sole_c[:, 0].max() + 0.01
    y0, y1 = sole_c[:, 1].min() - 0.01, sole_c[:, 1].max() + 0.01
    d.add(name + "_sole", Fill(sole, STRAW))
    d.add(name + "_sole_shade",
          *cels.hatch((x0, y0, x1, y1), angle=72, spacing=0.0055, width=0.0016, color=STRAW_SHADE, jitter=0.4,
                      seed=len(name), opacity=0.7),
          Fill(cels.ribbon(cels.offset(sole_c, -0.0045), 0.005), MUD, opacity=0.85),
          Line(cels.offset(sole_c, 0.006), 0.0018, "#b7a77f", None, False, 0.6), mask=(name + "_sole",))
    d.add(name + "_sole_ink", cels.contour(sole, W_FINE * 0.8, L_STRAW))
    _part(d, name, foot, shades=shades, color=L_SKIN, width=W_IN)
    straps = []
    for c in cords:
        P = cels.spline(c)
        straps += [Line(P, 0.0072, L_STRAW, cels.taper(P, 0.08, 0.08, tip=0.6)),
                   Line(P, 0.0044, STRAP, cels.taper(P, 0.1, 0.1, tip=0.5))]
    for c in loops:
        o = cels.ellipse(c, 0.0055, 0.004)
        straps += [Fill(o, STRAW_SHADE), cels.contour(o, W_FINE * 0.6, L_STRAW)]
    d.add(name + "_straps", *straps)


def full(t: float = 0.0, flash: float = 0.0) -> cels.Drawing:
    """The full figure `t` seconds into the shot (the wind in his hair, tails, hem and sleeves; his breathing; the
    water running off him); `flash` 0..1 a lightning flash's light on him."""
    d = _figure(t)
    _move(d, t)
    if flash > 0:
        d.recolor(lambda c: cels.flash(c, flash, KINDS_FULL.get(c, "lit")))
    return d


def _figure(t: float) -> cels.Drawing:
    d = cels.Drawing()
    gust = math.sin(2 * math.pi * t * 0.55)
    shiver = math.sin(2 * math.pi * t * 1.9 + 0.7)

    # his shadow on the wet planks under all of it: pooled under each foot, a faint band between
    d.add("ground", *cels.soft(cels.ellipse((0.455, 0.0), 0.17, 0.014), GROUND, spread=0.03, opacity=0.65),
          *cels.soft(cels.ellipse((-0.30, 0.0), 0.08, 0.011), GROUND, spread=0.025, opacity=0.6),
          *cels.soft(cels.ellipse((-0.44, 0.0), 0.08, 0.008), GROUND, spread=0.04, opacity=0.25),
          *cels.soft(cels.ellipse((0.03, 0.0), 0.5, 0.01), GROUND, spread=0.03, opacity=0.3))

    _scabbard(d)
    _torso(d)
    _back_leg(d)
    _front_leg(d)
    _waist(d)
    _tail(d, t, gust, shiver)
    _head(d, t, gust, shiver)
    _left_hand(d)
    _sword(d, t)
    _right_arm(d)
    return d


# ------------------------------------------------------------------------------------------------ behind him
def _scabbard(d: cels.Drawing) -> None:
    """The empty scabbard through the sash on his far hip, its end swung back and down behind him, its cord
    hanging."""
    c = cels.spline([(0.02, 0.985), (-0.30, 0.86), (-0.62, 0.72)])
    body = cels.ribbon(c, np.linspace(0.034, 0.028, len(c)))
    cap = cels.ribbon(c[-12:], 0.031)
    sheen = cels.offset(c[8:-14], 0.008)
    _part(d, "scabbard", Fill(body, LACQUER), shades=[
        Line(sheen, 0.006, LACQUER_SHEEN, cels.taper(sheen, 0.3, 0.3, tip=0.0), False, 0.9),
        Fill(cap, IRON)], color=L_HAIR, width=W_IN)
    cord = cels.spline([(-0.06, 0.95), (-0.12, 0.88), (-0.14, 0.80), (-0.12, 0.74)])
    d.add("scabbard_ink", Line(cord, 0.006, CORD_SHADE, cels.taper(cord, 0.1, 0.3, tip=0.3)))


# ------------------------------------------------------------------------------------------------ the legs
def _back_leg(d: cels.Drawing) -> None:
    """His left leg braced back on the ball of the foot, and the hakama's back panel over his seat: up at the waist to
    the stiff board across his lower back, down over the buttock and along the stretched leg to a hem lifted off the
    heel."""
    foot = fill([
        (-0.252, 0.016),                                             # the big toe's tip, on the sole
        (-0.256, 0.03), (-0.278, 0.038), (-0.305, 0.047),            # over the toes to the knuckles
        (-0.34, 0.068), (-0.37, 0.09), (-0.40, 0.115),               # the instep, steep with the heel up
        (-0.44, 0.15), (-0.47, 0.175),                               # the ankle, under the hem
        (-0.49, 0.15), (-0.503, 0.125),                              # the cord of the heel behind it
        (-0.508, 0.10), (-0.495, 0.083),                             # the heel, lifted, its sandal with it
        (-0.45, 0.068), (-0.40, 0.05), (-0.362, 0.032),              # the arch: the inside of the foot is ours
        (-0.33, 0.016),                                              # the ball, down on the sole
    ], SKIN, corners=(0, 16))
    _sandal(d, "back_foot", cels.spline([(-0.244, 0.0065), (-0.33, 0.0065), (-0.42, 0.04), (-0.51, 0.075)],
                                        corners=(1,)), foot, shades=[
        # the foot's inside turned from the light; the arch's hollow; the hem's shadow over the ankle
        *cels.soft([(-0.25, 0.026), (-0.33, 0.03), (-0.45, 0.085), (-0.51, 0.11), (-0.52, 0.06), (-0.33, 0.0),
                    (-0.24, 0.0)], SKIN_SHADE, spread=0.02, opacity=0.9),
        *cels.soft(cels.ellipse((-0.42, 0.065), 0.045, 0.012, rotate=22), SKIN_DEEP, spread=0.015, opacity=0.8),
        *cels.soft([(-0.36, 0.12), (-0.50, 0.19), (-0.50, 0.13), (-0.38, 0.09)], SKIN_DEEP, spread=0.03,
                   opacity=0.85),
        *cels.soft([(-0.265, 0.036), (-0.30, 0.048), (-0.36, 0.08), (-0.35, 0.07), (-0.30, 0.042)], SKIN_LIGHT,
                   spread=0.008, opacity=0.6),
        # the toes, the knuckle of the big toe, the ankle's bone
        _fold([(-0.262, 0.02), (-0.268, 0.034)], L_SKIN, W_FINE * 0.7, seed=12, taper_=(0.4, 0.4)),
        _fold([(-0.30, 0.03), (-0.31, 0.044)], L_SKIN, W_FINE * 0.6, seed=13, opacity=0.6),
        _fold([(-0.43, 0.125), (-0.445, 0.112), (-0.462, 0.118)], L_SKIN, W_FINE * 0.7, seed=14, opacity=0.7),
    ], cords=[
        [(-0.262, 0.036), (-0.285, 0.024), (-0.31, 0.016)],          # the thong back to the front loop
        [(-0.31, 0.016), (-0.335, 0.058), (-0.37, 0.095), (-0.40, 0.12)],   # over the instep to the ankle
        [(-0.415, 0.044), (-0.42, 0.09), (-0.43, 0.13)],             # the back loop up to the ankle
        [(-0.505, 0.085), (-0.505, 0.115), (-0.49, 0.14), (-0.45, 0.145)],  # round the lifted heel
    ], loops=[(-0.31, 0.016), (-0.415, 0.044)])

    hem = _hem((-0.385, 0.085), (-0.495, 0.18), 3, depth=0.006, seed=7)
    leg = fill([
        (-0.022, 1.145), (0.012, 1.14),                           # the board's top
        (0.05, 1.085), (0.088, 1.022),                            # the panel's top edge, down to the side seam
        (0.084, 0.92), (0.10, 0.80), (0.108, 0.66),               # the slit's back edge, behind the front leg
        (0.075, 0.56), (0.03, 0.46), (-0.01, 0.385),              # the front of the thigh, wet, to the knee
        (-0.042, 0.339),                                          # the knee
        (-0.13, 0.272), (-0.213, 0.213), (-0.30, 0.15),           # clinging down the shin
        (-0.385, 0.085), *hem, (-0.495, 0.18),                    # the hem, flaring a little round the ankle
        (-0.458, 0.20), (-0.40, 0.275), (-0.33, 0.345),           # the calf
        (-0.25, 0.405), (-0.175, 0.455),                          # the back of the knee
        (-0.15, 0.53), (-0.13, 0.64), (-0.118, 0.75),             # the back of the thigh
        (-0.105, 0.86), (-0.085, 0.95), (-0.05, 1.03),            # the seat
        (-0.045, 1.08),                                           # the small of the back, under the board
    ], HAKAMA, corners=(0, 1, 3, 14, 15 + len(hem)))
    _part(d, "back_leg", leg, shades=[
        # the far leg a step down from the light; the backs of the thigh and calf catch the sky
        Fill(leg.points, HAKAMA_SHADE, opacity=0.5),
        *cels.soft([(-0.06, 1.05), (-0.09, 0.93), (-0.105, 0.80), (-0.12, 0.64), (-0.14, 0.53), (-0.17, 0.46),
                    (-0.26, 0.40), (-0.35, 0.33), (-0.43, 0.25), (-0.40, 0.24), (-0.31, 0.31), (-0.21, 0.38),
                    (-0.12, 0.47), (-0.085, 0.62), (-0.07, 0.80), (-0.05, 0.93)], HAKAMA_LIGHT, spread=0.035,
                   opacity=0.5),
        # the front of the leg, under the near leg's shadow
        cels.fill([(0.108, 0.66), (0.075, 0.56), (0.03, 0.46), (-0.01, 0.385), (-0.042, 0.339), (-0.13, 0.272),
                   (-0.213, 0.213), (-0.30, 0.15), (-0.385, 0.085), (-0.37, 0.12), (-0.28, 0.19), (-0.19, 0.25),
                   (-0.10, 0.31), (-0.02, 0.39), (0.04, 0.50), (0.08, 0.62)], HAKAMA_DEEP, opacity=0.85),
        *cels.soft([(0.10, 0.85), (0.08, 0.66), (0.02, 0.56), (-0.02, 0.60), (0.03, 0.75), (0.05, 0.86)],
                   HAKAMA_DEEP, spread=0.05, opacity=0.7),
        # soaked: darker toward the hem
        *cels.soft([(-0.56, 0.24), (-0.25, 0.24), (-0.25, 0.04), (-0.56, 0.04)], HAKAMA_WET, spread=0.1,
                   opacity=0.7, smooth=False),
        # the pleats down the leg, flaring a little at the hem
        _fold([(0.0, 1.06), (-0.04, 0.88), (-0.06, 0.68), (-0.085, 0.50), (-0.17, 0.37), (-0.29, 0.26),
               (-0.40, 0.17), (-0.45, 0.125)], seed=1),
        _fold([(0.05, 1.02), (0.02, 0.86), (0.0, 0.68), (-0.03, 0.46), (-0.12, 0.33), (-0.24, 0.23),
               (-0.36, 0.14), (-0.41, 0.10)], seed=2),
        *_glint([(-0.03, 1.04), (-0.075, 0.88), (-0.095, 0.68), (-0.12, 0.52), (-0.21, 0.40), (-0.33, 0.30),
                 (-0.43, 0.20)], seed=235, opacity=0.35),
        _fold([(-0.47, 0.19), (-0.465, 0.15)], width=W_IN * 0.7, seed=6),
        # the cloth bunched behind the knee, and pulled taut from the seat down the thigh
        *cels.brush([(-0.165, 0.47), (-0.11, 0.42), (-0.06, 0.40)], W_IN * 0.8, L_CLOTH, seed=4, tip=0.0),
        *cels.brush([(-0.20, 0.43), (-0.14, 0.385), (-0.08, 0.37)], W_IN * 0.7, L_CLOTH, seed=5, tip=0.0),
        *cels.brush([(-0.10, 0.82), (-0.11, 0.70), (-0.13, 0.58)], W_IN * 0.7, L_CLOTH, seed=3, tip=0.0),
    ], color=L_CLOTH)


def _front_leg(d: cels.Drawing) -> None:
    """His right leg, forward and bent deep: the hakama's leg falling from the waist over the thigh to the knee, then
    hanging from it in long folds to a heavy, wet hem over the foot."""
    foot = fill([
        (0.336, 0.016), (0.326, 0.032), (0.328, 0.055),              # the heel
        (0.338, 0.08), (0.35, 0.118),                                # the cord of the heel, up under the hem
        (0.405, 0.12), (0.415, 0.095),                               # the ankle's front, under the hem
        (0.45, 0.074), (0.50, 0.056), (0.545, 0.042),                # the instep down to the toes' knuckles
        (0.568, 0.036), (0.584, 0.03), (0.593, 0.021),               # the toes
        (0.589, 0.016),
    ], SKIN, corners=(0, 13))
    _sandal(d, "front_foot", cels.spline([(0.322, 0.007), (0.45, 0.007), (0.598, 0.007)]), foot, shades=[
        # the foot's outer side below its edge in shade; the heel; the hem's shadow over the ankle
        *cels.soft([(0.33, 0.03), (0.45, 0.032), (0.58, 0.026), (0.60, 0.0), (0.32, 0.0)], SKIN_SHADE,
                   spread=0.014, opacity=0.9),
        *cels.soft([(0.31, 0.02), (0.345, 0.03), (0.35, 0.12), (0.31, 0.12)], SKIN_DEEP, spread=0.02,
                   opacity=0.75),
        *cels.soft([(0.33, 0.125), (0.43, 0.125), (0.43, 0.095), (0.33, 0.095)], SKIN_DEEP, spread=0.025,
                   opacity=0.85, smooth=False),
        # the light along the instep and the toes' tops, wet
        *cels.soft([(0.42, 0.092), (0.50, 0.06), (0.585, 0.031), (0.575, 0.027), (0.49, 0.052), (0.43, 0.08)],
                   SKIN_LIGHT, spread=0.008, opacity=0.65),
        # the foot's outer edge, the ankle's bone, the little toes
        _fold([(0.34, 0.03), (0.42, 0.028), (0.52, 0.026), (0.57, 0.022)], L_SKIN, W_FINE * 0.6, seed=11,
              opacity=0.55),
        _fold([(0.362, 0.098), (0.372, 0.083), (0.388, 0.08)], L_SKIN, W_FINE * 0.8, seed=15),
        *[_fold([(x, 0.018), (x - 0.005, 0.033)], L_SKIN, W_FINE * 0.7, seed=16 + k, taper_=(0.4, 0.4))
          for k, x in enumerate((0.567, 0.578))],
    ], cords=[
        [(0.558, 0.036), (0.53, 0.024), (0.502, 0.016)],             # the thong back to the front loop
        [(0.502, 0.016), (0.47, 0.05), (0.435, 0.084), (0.41, 0.102)],   # over the instep to the ankle
        [(0.432, 0.016), (0.418, 0.05), (0.398, 0.09)],              # the back loop up to the ankle
        [(0.336, 0.024), (0.343, 0.06), (0.36, 0.09), (0.40, 0.1)],  # round the heel to the ankle
    ], loops=[(0.502, 0.016), (0.432, 0.016)])

    hem = _hem((0.528, 0.12), (0.268, 0.11), 4, seed=8)
    leg = fill([
        (0.118, 1.012),                                            # the slit's front edge, at the waist
        (0.316, 0.968),                                            # the waist's front, over the belly
        (0.335, 0.90), (0.39, 0.78), (0.445, 0.665),               # over the thigh, the wet cloth clinging
        (0.478, 0.595), (0.488, 0.555),                            # the knee's cap
        (0.493, 0.50), (0.497, 0.42),                              # the shin under it
        (0.503, 0.32), (0.512, 0.22),                              # falling from the knee
        (0.528, 0.12), *hem, (0.268, 0.11),                        # the hem, a little flared over the ankle
        (0.275, 0.20), (0.284, 0.29), (0.302, 0.37),               # wet on the calf
        (0.33, 0.44),                                              # the hollow behind the knee
        (0.28, 0.49), (0.21, 0.55), (0.155, 0.60),                 # clinging under the thigh
        (0.12, 0.645),                                             # the crotch
        (0.095, 0.72), (0.085, 0.80), (0.098, 0.92),               # the inside of the thigh, up the slit
    ], HAKAMA, corners=(0, 1, 11, 12 + len(hem), 16 + len(hem), 20 + len(hem)))
    _part(d, "front_leg", leg, shades=[
        # the thigh as a cylinder under wet cloth: lit along its top, its underside in shade
        *cels.soft([(0.16, 1.0), (0.316, 0.966), (0.335, 0.90), (0.39, 0.78), (0.445, 0.665), (0.478, 0.595),
                    (0.44, 0.615), (0.38, 0.72), (0.32, 0.83), (0.24, 0.93)], HAKAMA_LIGHT, spread=0.045,
                   opacity=0.55),
        cels.fill([(0.12, 0.645), (0.155, 0.60), (0.21, 0.55), (0.28, 0.49), (0.33, 0.44), (0.37, 0.47),
                   (0.30, 0.535), (0.23, 0.59), (0.17, 0.64), (0.11, 0.69)], HAKAMA_SHADE),
        # the hollow behind the knee, and the calf's back half
        *cels.soft(cels.ellipse((0.345, 0.45), 0.04, 0.028, rotate=30), HAKAMA_DEEP, spread=0.025, opacity=0.85),
        cels.fill([(0.33, 0.44), (0.302, 0.37), (0.284, 0.29), (0.275, 0.20), (0.268, 0.11), (0.345, 0.11),
                   (0.355, 0.25), (0.37, 0.39)], HAKAMA_SHADE),
        # soaked toward the hem
        *cels.soft([(0.22, 0.24), (0.58, 0.24), (0.58, 0.04), (0.22, 0.04)], HAKAMA_WET, spread=0.12, opacity=0.65,
                   smooth=False),
        # the pleats from the waist over the thigh to the knee
        _fold([(0.17, 0.99), (0.23, 0.86), (0.32, 0.73), (0.42, 0.63)], seed=21),
        _fold([(0.245, 0.98), (0.30, 0.875), (0.375, 0.76), (0.45, 0.645)], seed=22),
        *_glint([(0.19, 0.985), (0.255, 0.865), (0.345, 0.735), (0.435, 0.635)], seed=233, opacity=0.4),
        *_glint([(0.37, 0.83), (0.42, 0.72), (0.465, 0.615)], seed=234, opacity=0.55),
        # the wet cloth breaking over the bent knee: tight short folds from the hollow round to the cap
        *[p_ for k, pts in enumerate((
            [(0.335, 0.46), (0.385, 0.50), (0.44, 0.535)],
            [(0.34, 0.43), (0.395, 0.455), (0.455, 0.48)],
            [(0.345, 0.485), (0.39, 0.535), (0.43, 0.575)],
            [(0.35, 0.405), (0.40, 0.415), (0.46, 0.43)])) for p_ in
          cels.brush(pts, W_IN * (0.9 - 0.1 * k), L_CLOTH, seed=40 + k, taper_=(0.15, 0.6), tip=0.0)],
        *[cels.fill(pts, HAKAMA_SHADE, smooth=False) for pts in (
            [(0.34, 0.455), (0.39, 0.49), (0.44, 0.528), (0.385, 0.48)],
            [(0.345, 0.428), (0.40, 0.45), (0.455, 0.475), (0.40, 0.442)])],
        *_glint([(0.36, 0.475), (0.40, 0.505), (0.44, 0.545)], seed=237, opacity=0.5, width=W_IN),
        # a highlight on the knee's cap
        *cels.soft(cels.ellipse((0.47, 0.565), 0.018, 0.03, rotate=20), HAKAMA_LIGHT, spread=0.015, opacity=0.6),
        # the falls from the knee to the hem
        _fold([(0.46, 0.50), (0.46, 0.36), (0.462, 0.22), (0.465, 0.125)], seed=23),
        _fold([(0.42, 0.46), (0.408, 0.33), (0.40, 0.20), (0.398, 0.115)], seed=24),
        _fold([(0.37, 0.39), (0.35, 0.28), (0.338, 0.18), (0.335, 0.115)], width=W_IN * 0.8, seed=25),
        *_glint([(0.483, 0.48), (0.485, 0.35), (0.49, 0.22), (0.494, 0.13)], seed=231),
        *_glint([(0.44, 0.45), (0.434, 0.33), (0.43, 0.20), (0.43, 0.12)], seed=232, opacity=0.35),
        # the cloth drawn tight from the knee back across the thigh
        _fold([(0.44, 0.60), (0.35, 0.625), (0.26, 0.665), (0.18, 0.715)], width=W_IN * 0.7, seed=28),
    ], color=L_CLOTH)


# ------------------------------------------------------------------------------------------------ the trunk
def _torso(d: cels.Drawing) -> None:
    """The kimono over his leaning trunk: the back curved over, the chest forward, its collar open at the throat on
    the pale under-collar, the sash at the waist."""
    neck = fill([(0.162, 1.36), (0.168, 1.44), (0.19, 1.49), (0.235, 1.46), (0.262, 1.405), (0.262, 1.36),
                 (0.245, 1.32), (0.17, 1.32)], SKIN)
    _part(d, "neck", neck, outline=False, shades=[
        # the jaw's shadow across the throat; the back of the neck turned from us
        *cels.soft([(0.17, 1.47), (0.27, 1.42), (0.27, 1.385), (0.22, 1.395), (0.17, 1.42)], SKIN_SHADE,
                   spread=0.02, opacity=0.8),
        cels.fill([(0.162, 1.36), (0.168, 1.44), (0.18, 1.47), (0.182, 1.37)], SKIN_DEEP, opacity=0.7),
    ], lines=[
        _fold([(0.258, 1.40), (0.264, 1.37), (0.27, 1.34)], L_SKIN, W_IN, seed=31),
        _fold([(0.17, 1.455), (0.164, 1.41), (0.162, 1.37)], L_SKIN, W_IN, seed=32),
        # the cord of the neck's muscle, from behind the ear down to the collarbone
        _fold([(0.205, 1.475), (0.23, 1.42), (0.25, 1.36)], L_SKIN, W_FINE * 0.8, seed=33, opacity=0.5),
    ])

    body = fill([
        (0.125, 1.375), (0.07, 1.34), (0.035, 1.27), (0.012, 1.18), (0.0, 1.10), (-0.012, 1.02), (-0.03, 0.95),
        (0.31, 0.93), (0.318, 1.00), (0.322, 1.08), (0.316, 1.16), (0.30, 1.235), (0.28, 1.30), (0.258, 1.34),
        (0.20, 1.38),
    ], CLOTH, corners=(6, 7))
    _part(d, "torso", body, shades=[
        # light across the shoulders and down the curve of the back
        *cels.soft([(0.06, 1.36), (0.20, 1.37), (0.18, 1.32), (0.07, 1.28), (0.03, 1.20), (0.02, 1.27)],
                   CLOTH_LIGHT, spread=0.04, opacity=0.65),
        # the near arm's shadow down his side, and the cloth gathered under the arm
        cels.fill([(0.06, 1.18), (0.25, 1.14), (0.30, 1.05), (0.31, 0.95), (0.03, 0.95), (0.02, 1.08)],
                  CLOTH_SHADE, opacity=0.8),
        *cels.soft([(0.10, 1.16), (0.24, 1.12), (0.26, 1.04), (0.14, 1.06)], CLOTH_DEEP, spread=0.04, opacity=0.8),
        # the chest's front, turned from us
        cels.fill([(0.258, 1.34), (0.28, 1.30), (0.30, 1.235), (0.316, 1.16), (0.322, 1.08), (0.30, 1.08),
                   (0.29, 1.18), (0.27, 1.26)], CLOTH_SHADE),
        # wet cloth clinging: folds from the armpit down to the sash and round the back
        _fold([(0.08, 1.17), (0.12, 1.09), (0.13, 1.03)], seed=41),
        _fold([(0.04, 1.21), (0.03, 1.13), (0.035, 1.06)], width=W_IN * 0.8, seed=42),
        _fold([(0.22, 1.12), (0.20, 1.06), (0.21, 1.02)], width=W_IN * 0.8, seed=43),
    ], color=L_CLOTH)

    # the collar: the pale under-collar close round the neck, the kimono's own collar band over it, open at the throat
    collar_c = cels.spline([(0.135, 1.392), (0.19, 1.40), (0.245, 1.37), (0.276, 1.33), (0.298, 1.27), (0.312, 1.20)])
    chest = fill([(0.27, 1.335), (0.30, 1.26), (0.312, 1.195), (0.316, 1.17), (0.30, 1.235), (0.28, 1.29),
                  (0.258, 1.335)], SKIN)
    d.add("chest", chest)
    d.add("chest_shade", Fill(chest.points, SKIN_SHADE, opacity=0.5), mask=("chest",))
    under = cels.ribbon(cels.offset(collar_c, 0.006), np.linspace(0.016, 0.01, len(collar_c)))
    band = cels.ribbon(cels.offset(collar_c, -0.011), np.linspace(0.02, 0.016, len(collar_c)))
    d.add("collar", Fill(under, UNDER), Fill(cels.ribbon(cels.offset(collar_c, 0.001), 0.006), UNDER_SHADE,
                                              opacity=0.7),
          Fill(band, CLOTH), Fill(cels.ribbon(cels.offset(collar_c, -0.009), 0.007), CLOTH_LIGHT, opacity=0.5))
    d.add("collar_ink", cels.contour(under, W_FINE * 0.8, L_UNDER), cels.contour(band, W_FINE * 0.8, L_CLOTH))

    # the sash: the hakama's panels cover all but a band of it at his side
    obi = fill([(-0.03, 1.10), (0.10, 1.07), (0.235, 1.035), (0.322, 1.015), (0.318, 0.955), (0.23, 0.97),
                (0.10, 1.0), (-0.03, 1.03)], OBI, corners=(0, 3, 4, 7))
    _part(d, "obi", obi, shades=[
        cels.fill([(0.24, 1.045), (0.33, 1.025), (0.33, 0.95), (0.25, 0.96)], OBI_SHADE, smooth=False),
        _fold([(0.04, 1.06), (0.13, 1.045), (0.24, 1.012)], L_CLOTH, W_FINE, seed=44, opacity=0.6),
    ], width=W_IN)


def _waist(d: cels.Drawing) -> None:
    """Where the hakama meets the kimono: the side slit showing the kimono's skirt between the panels, the front
    panel's ties wrapped over the sash, and the stiff board across the small of his back, seen edge on."""
    slit = fill([(0.088, 1.022), (0.118, 1.012), (0.098, 0.92), (0.074, 0.80), (0.084, 0.92)], CLOTH_SHADE,
                corners=(0, 1, 3))
    _part(d, "slit", slit, shades=[cels.fill([(0.085, 1.0), (0.11, 0.995), (0.08, 0.85)], CLOTH_DEEP)],
          width=W_FINE)
    ties = []
    for y0, y1, w in ((1.016, 0.97, 0.014), (1.04, 0.992, 0.011)):
        c = cels.spline([(0.09, y0 + 0.004), (0.21, (y0 + y1) / 2 + 0.006), (0.326, y1)])
        r = cels.ribbon(c, w)
        ties += [Fill(r, HAKAMA), Fill(cels.ribbon(cels.offset(c, -w * 0.25), w * 0.45), HAKAMA_SHADE),
                 cels.contour(r, W_FINE, L_CLOTH)]
    d.add("ties", *ties)
    c = cels.spline([(-0.004, 1.148), (-0.03, 1.09), (-0.042, 1.03)])
    board = cels.ribbon(c, np.linspace(0.02, 0.014, len(c)))
    d.add("board", Fill(board, BOARD), Fill(cels.ribbon(cels.offset(c, 0.004), 0.006), HAKAMA_LIGHT, opacity=0.6),
          cels.contour(board, W_FINE * 0.8, L_CLOTH))


def _head(d: cels.Drawing, t: float, gust: float, shiver: float) -> None:
    """His head nearly in profile, chin down: brow, nose, mouth and jaw drawn as a face, not a mask; the scar through
    his right brow; his hair dragged back wet over the skull to the tie at the nape, the band over it, two loose
    strands at his temple."""
    skull = _H(cels.spline([
        (-0.12, 1.0), (0.08, 0.965), (0.19, 0.89), (0.245, 0.77),          # crown to forehead
        (0.262, 0.655), (0.244, 0.595),                                    # brow ridge, the root of the nose
        (0.292, 0.47), (0.322, 0.405),                                     # the bridge, the tip
        (0.296, 0.378), (0.262, 0.368),                                    # under the nose
        (0.275, 0.322), (0.258, 0.292), (0.268, 0.258),                    # lips
        (0.238, 0.208), (0.256, 0.13), (0.22, 0.04), (0.18, 0.0),          # the chin
        (0.06, 0.03), (-0.08, 0.10), (-0.16, 0.19),                        # under the jaw to its angle
        (-0.22, 0.30), (-0.40, 0.30), (-0.52, 0.52), (-0.50, 0.80), (-0.36, 0.96),   # behind the ear, the skull
    ], closed=True, corners=(5, 9, 16, 19)))
    _part(d, "skin", Fill(skull, SKIN), outline=False, shades=[
        # the side of the face toward the ear a half-step down; the eye's socket; under the cheekbone; the jaw
        *cels.soft(_H([(0.02, 0.70), (0.12, 0.66), (0.13, 0.52), (0.08, 0.40), (0.0, 0.25), (-0.15, 0.22),
                       (-0.25, 0.45), (-0.20, 0.68)]), SKIN_SHADE, spread=0.05 * HU, opacity=0.25),
        *cels.soft(_H(cels.ellipse((0.185, 0.57), 0.06, 0.04, rotate=-10)), SKIN_SHADE, spread=0.03 * HU,
                   opacity=0.55),
        cels.fill(_H([(0.18, 0.0), (0.06, 0.03), (-0.08, 0.10), (-0.16, 0.19), (-0.22, 0.30), (-0.12, 0.22),
                      (0.0, 0.11), (0.12, 0.06)]), SKIN_DEEP),
        # under the nose and the lower lip
        *cels.soft(_H(cels.ellipse((0.268, 0.36), 0.03, 0.012)), SKIN_DEEP, spread=0.02 * HU, opacity=0.8),
        *cels.soft(_H(cels.ellipse((0.245, 0.228), 0.025, 0.012)), SKIN_SHADE, spread=0.02 * HU, opacity=0.8),
        # light down the bridge of the nose and on the cheekbone
        *cels.soft(_H([(0.255, 0.60), (0.29, 0.48), (0.31, 0.42), (0.28, 0.44), (0.25, 0.55)]), SKIN_LIGHT,
                   spread=0.02 * HU, opacity=0.6),
    ])
    profile = cels.between(skull, _H([[-0.12, 1.0]])[0], _H([[0.18, 0.0]])[0])
    jaw = cels.between(skull, _H([[0.18, 0.0]])[0], _H([[-0.22, 0.30]])[0])
    d.add("skin_ink",
          Line(profile, W_IN * 1.05, L_SKIN, cels.lit_widths(profile, (0.6, 1.0), closed=False, outward=-1,
                                                             lit=0.6, dark=1.2)),
          Line(jaw, W_IN * 1.15, L_SKIN, cels.taper(jaw, 0.05, 0.3, tip=0.3)))

    # the ear
    ear = _H(cels.spline([(-0.17, 0.60), (-0.24, 0.63), (-0.29, 0.58), (-0.29, 0.46), (-0.25, 0.38),
                          (-0.20, 0.36), (-0.175, 0.42)], closed=True))
    d.add("ear", Fill(ear, SKIN), *cels.soft(_H(cels.ellipse((-0.23, 0.50), 0.035, 0.07)), SKIN_SHADE,
                                             spread=0.02 * HU, opacity=0.8))
    d.add("ear_ink", cels.contour(ear, W_FINE * 1.1, L_SKIN),
          _fold(_H([(-0.21, 0.57), (-0.26, 0.55), (-0.265, 0.47), (-0.23, 0.42)]), L_SKIN, W_FINE * 0.8, seed=51))

    # the face: a hard brow driven down to the nose, the eye under it, a set mouth
    brow = fill(_H([(0.255, 0.64), (0.20, 0.665), (0.12, 0.675), (0.07, 0.665), (0.12, 0.652), (0.19, 0.64),
                    (0.235, 0.618)]), HAIR, corners=(0, 3))
    eye_up = _H(cels.spline([(0.11, 0.585), (0.15, 0.60), (0.205, 0.588), (0.228, 0.565)]))
    eye_lo = _H(cels.spline([(0.12, 0.56), (0.17, 0.548), (0.215, 0.556)]))
    white = Fill(np.vstack([eye_up, eye_lo[::-1]]), "#cfcad6")
    iris = Fill(_H(cels.ellipse((0.192, 0.57), 0.022, 0.026)), IRIS_DARK)
    glint = Fill(_H(cels.ellipse((0.198, 0.58), 0.006, 0.006)), "#f4f4f8")
    d.add("eye_white", white)
    d.add("eye_iris", iris, glint, Fill(white.points, "#7e7a95", opacity=0.35), mask=("eye_white",))
    d.add("face", brow, cels.contour(brow.points, W_FINE, L_HAIR),
          Line(eye_up, W_FINE * 1.8, L_HAIR, cels.taper(eye_up, 0.4, 0.15, tip=0.3)),
          Line(eye_lo, W_FINE * 0.8, L_SKIN, cels.taper(eye_lo, 0.4, 0.4, tip=0.0), False, 0.8),
          # the lid's crease, the scar cutting the brow
          _fold(_H([(0.12, 0.61), (0.17, 0.625), (0.21, 0.615)]), L_SKIN, W_FINE * 0.7, seed=52, opacity=0.7),
          Line(_H(np.array([(0.165, 0.70), (0.152, 0.635)])), W_FINE * 1.1, "#e9cdbd", np.array([0.3, 1.0]), False),
          # the nostril, the fold from it to the mouth, the mouth's line, the lower lip's edge
          _fold(_H([(0.255, 0.395), (0.238, 0.385), (0.236, 0.37)]), L_SKIN, W_FINE * 0.9, seed=53),
          _fold(_H([(0.226, 0.40), (0.21, 0.34), (0.215, 0.29)]), L_SKIN, W_FINE * 0.7, seed=54, opacity=0.55),
          _fold(_H([(0.268, 0.292), (0.245, 0.29), (0.226, 0.296)]), L_SKIN, W_FINE * 1.1, seed=55,
                taper_=(0.2, 0.5)),
          _fold(_H([(0.255, 0.252), (0.238, 0.245)]), L_SKIN, W_FINE * 0.7, seed=56, opacity=0.6))

    # the hair: dragged back over the skull, wet, in clumps from the hairline to the tie at the nape
    outer = _H(cels.spline([(0.212, 0.872), (0.17, 0.955), (0.05, 1.035), (-0.15, 1.058), (-0.36, 0.99),
                            (-0.50, 0.845), (-0.556, 0.66), (-0.52, 0.48), (-0.47, 0.36)]))
    inner = _H(cels.spline([(0.14, 0.785), (0.04, 0.715), (-0.08, 0.675), (-0.19, 0.668), (-0.27, 0.62),
                            (-0.31, 0.50), (-0.38, 0.39), (-0.47, 0.36)]))
    clumps = cels.strips(outer, inner, 6, seed=61, vary=0.45, sway=0.35)
    cap = Fill(np.vstack([cels.resample(outer, 64), cels.resample(inner, 64)[::-1]]), HAIR)
    hair_shades = [
        # below the skull's top all of it falls into dark; the far side behind the ear darkest
        cels.fill(_H([(-0.20, 0.66), (-0.40, 0.80), (-0.556, 0.66), (-0.52, 0.48), (-0.47, 0.36), (-0.38, 0.39),
                      (-0.30, 0.50)]), HAIR_SHADE),
    ]
    sheen = []
    for k, c in enumerate(clumps):
        n = len(c) // 2
        top, bottom = c[:n], c[n:][::-1]
        # each clump darker along its lower edge, and the wet sheen caught in a short streak on its crown
        hair_shades.append(Fill(np.vstack([cels.blend(top, bottom, 0.55), bottom[::-1]]), HAIR_SHADE, 0.75))
        a, b = int(n * (0.18 + 0.08 * (k % 3))), int(n * (0.55 + 0.1 * (k % 2)))
        mid = cels.blend(top, bottom, 0.3)[a:b]
        if k < 4:
            sheen.append(Fill(cels.ribbon(mid, np.sin(np.linspace(0, math.pi, len(mid))) ** 0.7 * 0.011 *
                                          (1.2 - 0.2 * k)), HAIR_SHEEN, 0.85))
        hair_shades += cels.brush(cels.blend(top, bottom, 0.02), W_FINE * 0.9, L_HAIR, gaps=((0.25, 0.42),),
                                  seed=62 + k, taper_=(0.15, 0.4), tip=0.0)
    _part(d, "hair", cap, shades=[*hair_shades, *sheen,
                                  *cels.strands(outer, inner, 14, width=W_FINE * 0.45, color=HAIR_SHEEN, seed=64,
                                                reach=(0.05, 0.6), opacity=(0.2, 0.5))],
          color=L_HAIR, width=W_IN)
    # a few hairs lifted off the crown by the wind
    d.add("hair_ink", *[_fold(_H([(x, y), (x - 0.06, y + 0.03 + 0.01 * k), (x - 0.13, y + 0.02)]), L_HAIR,
                              W_FINE * 0.6, seed=66 + k, taper_=(0.1, 0.6))
                        for k, (x, y) in enumerate(((-0.05, 1.04), (-0.24, 1.035), (-0.40, 0.96)))])

    # the band: round the brow and over the hair, knotted behind
    band = fill(_H([(0.216, 0.874), (0.05, 0.885), (-0.20, 0.875), (-0.44, 0.835), (-0.55, 0.775),
                    (-0.545, 0.715), (-0.43, 0.755), (-0.20, 0.79), (0.05, 0.795), (0.256, 0.778)]), BAND,
                corners=(0, 9))
    knot = _H([[-0.555, 0.75]])[0]
    _part(d, "band", band, shades=[
        cels.fill(_H([(0.26, 0.81), (-0.55, 0.77), (-0.55, 0.70), (0.26, 0.70)]), BAND_SHADE, smooth=False),
        *cels.soft(_H([(0.20, 0.868), (-0.30, 0.858), (-0.30, 0.842), (0.20, 0.852)]), "#c95f58",
                   spread=0.012 * HU, opacity=0.45, smooth=False),
        *cels.strands(_H([(0.22, 0.85), (-0.45, 0.80)]), _H([(0.22, 0.79), (-0.45, 0.75)]), 9,
                      width=W_FINE * 0.5, color=BAND_SHADE, seed=70, opacity=(0.3, 0.6)),
    ], color=L_BAND, width=W_FINE * 1.3)
    k = cels.ellipse(knot, 0.013, 0.01, rotate=-30)
    d.add("band_ink", Fill(k, BAND), Fill(cels.ellipse(knot + (0.002, -0.003), 0.009, 0.006, rotate=-30),
                                          BAND_SHADE), cels.contour(k, W_FINE, L_BAND))

    # two wet strands loose at his temple, swinging a little
    sw = 2.5 * (gust + 0.4 * shiver)
    for a, b, tip, bow in (((0.13, 0.80), (0.17, 0.82), (0.215, 0.62), 0.05),
                           ((0.05, 0.75), (0.09, 0.77), (0.08, 0.50), 0.06)):
        a, b, tip = (_H([v])[0] for v in (a, b, tip))
        tip = cels.bend([tip], (a + b) / 2, sw, power=1.0)[0]
        lk = cels.lock(a, b, tip, bow=bow)
        d.add("strands", Fill(lk.outline, HAIR), Fill(lk.inner(0.5, "b"), HAIR_SHADE),
              Line(lk.outline, W_FINE, L_HAIR, cels.taper(lk.outline, 0.2, 0.2, tip=0.0)))

    # the band's frayed tails, streaming back from the knot in the wind
    ph = 2 * math.pi * t * 1.5
    for k_, (length, ang, w) in enumerate(((0.25, 196.0, 0.021), (0.20, 212.0, 0.018))):
        dirn = _dir(ang + 5.0 * gust)
        c = knot + np.linspace(0, 1, 40)[:, None] * length * dirn
        c = cels.wave(c, 0.014, 0.12, ph + k_ * 1.4, power=1.1)
        widths = w * (1.0 - 0.3 * np.linspace(0, 1, len(c)))
        tail = cels.ribbon(c, widths)
        third = len(c) // 3
        under = cels.ribbon(c[third:] - cels.normals(c[third:]) * (widths[third:, None] * 0.25), widths[third:] * 0.45)
        end, nrm = c[-1], cels.normals(c)[-1]
        threads = [line([end + nrm * o * w * 0.3, end + nrm * o * w * 0.4 + dirn * 0.012,
                         end + nrm * o * w * 0.5 + dirn * (0.024 + 0.006 * abs(o))], W_FINE * 0.7, BAND_SHADE,
                        taper_=(0.0, 0.6)) for o in (-1, 0.2, 1)]
        d.add("band_tails", Fill(tail, BAND), Fill(under, BAND_SHADE), cels.contour(tail, W_FINE, L_BAND), *threads)


def _tail(d: cels.Drawing, t: float, gust: float, shiver: float) -> None:
    """The long hair tied at his nape, heavy with rain: wet clumps hanging down his back, the wind lifting their ends
    back a little."""
    tie = _H([[-0.47, 0.345]])[0]
    sway = 4.0 * gust + 1.5 * shiver
    for k, (a, b, tip, bow, shade) in enumerate((
            ((-0.022, 0.006), (0.012, -0.006), (-0.12, -0.33), 0.06, 0.5),
            ((-0.028, 0.004), (0.004, -0.008), (-0.18, -0.27), 0.05, 0.55),
            ((-0.018, 0.004), (0.014, -0.004), (-0.07, -0.36), 0.04, 0.45),
            ((-0.03, 0.008), (0.0, -0.002), (-0.21, -0.19), 0.045, 0.6),
            ((-0.012, 0.002), (0.01, -0.006), (-0.10, -0.25), 0.04, 0.5))):
        a, b, tip = tie + a, tie + b, tie + tip
        tip = cels.bend([tip], (a + b) / 2, sway * (1 + 0.25 * k), power=1.0)[0]
        lk = cels.lock(a, b, tip, bow=bow, curl=0.06 * (k % 2 * 2 - 1))
        d.add("tail", Fill(lk.outline, HAIR), Fill(lk.inner(shade, "b"), HAIR_SHADE),
              Fill(lk.inner(0.88, "a"), HAIR_SHEEN, opacity=0.55),
              Line(lk.outline, W_FINE * 1.1, L_HAIR, cels.taper(lk.outline, 0.15, 0.15, tip=0.0)))
        if k in (0, 2):
            d.add("tail_water", *cels.drip(tip, t, period=1.1 + 0.3 * k, r=0.005, fall=0.14, phase=0.37 * k,
                                           body=WATER, ink=L_HAIR, opacity=0.8))
    tie_f = cels.ellipse(tie, 0.012, 0.009, rotate=-40)
    d.add("tail", Fill(tie_f, CORD_SHADE), cels.contour(tie_f, W_FINE * 0.8, L_CORD))


# ------------------------------------------------------------------------------------------------ hands and sword
def _left_hand(d: cels.Drawing) -> None:
    """His left hand at the pommel, the hilt's far side: its back and knuckles above the hilt, its fingers curled
    round under it (drawn over the hilt in `_sword`)."""
    # the forearm behind it, coming out from under his right arm
    arm = fill([_hilt(-0.245, 0.045), _hilt(-0.31, 0.085), _hilt(-0.33, 0.04), _hilt(-0.255, 0.012)], SKIN_SHADE)
    d.add("left_arm", arm, cels.contour(arm.points, W_FINE, L_SKIN))
    back = fill([_hilt(-0.255, 0.012), _hilt(-0.245, 0.045), _hilt(-0.20, 0.058), _hilt(-0.16, 0.048),
                 _hilt(-0.15, 0.02), _hilt(-0.17, -0.025), _hilt(-0.24, -0.028)], SKIN)
    _part(d, "left_hand", back, shades=[
        cels.fill([_hilt(-0.26, 0.0), _hilt(-0.15, 0.0), _hilt(-0.15, -0.04), _hilt(-0.26, -0.04)], SKIN_SHADE,
                  smooth=False),
        *cels.soft([_hilt(-0.24, 0.05), _hilt(-0.16, 0.05), _hilt(-0.16, 0.035), _hilt(-0.24, 0.035)], SKIN_LIGHT,
                   spread=0.01, opacity=0.5, smooth=False),
    ], color=L_SKIN, width=W_FINE * 1.2)


def _sword(d: cels.Drawing, t: float) -> None:
    """The hilt in both hands, the guard, the collar, and the blade carrying on forward and down: its back straight
    to the point, its edge sweeping up to meet it; the polish catching the sky along the ridge; water running off the
    point."""
    hilt = Fill(cels.ribbon(np.vstack([POMMEL, GUARD]), np.array([0.033, 0.031])), WRAP)
    wraps = []
    for s in np.arange(-0.235, -0.01, 0.034):
        # the cord's crossings, the ray skin's pale diamonds between them
        dia = [_hilt(s, 0.0), _hilt(s + 0.017, 0.012), _hilt(s + 0.034, 0.0), _hilt(s + 0.017, -0.012)]
        wraps.append(Fill(np.array(dia), SAME, opacity=0.85))
    _part(d, "hilt", hilt, shades=[*wraps,
                                   *cels.soft([_hilt(-0.26, 0.016), _hilt(0.0, 0.016), _hilt(0.0, 0.006),
                                               _hilt(-0.26, 0.006)], WRAP_LIGHT, spread=0.008, opacity=0.6,
                                              smooth=False)],
          color=L_HAIR, width=W_FINE * 1.2)
    cap = Fill(cels.ellipse(POMMEL - AX * 0.004, 0.011, 0.018, rotate=SWORD_ANGLE), IRON)
    d.add("hilt_ink", cap, cels.contour(cap.points, W_FINE, L_HAIR))

    # the left hand's fingers round the near side of the hilt
    fingers = []
    for k, u in enumerate((-0.235, -0.212, -0.19, -0.168)):
        f = cels.fill([_hilt(u - 0.010, 0.012), _hilt(u + 0.010, 0.014), _hilt(u + 0.012, -0.012),
                       _hilt(u + 0.003, -0.022), _hilt(u - 0.009, -0.016)], SKIN, corners=())
        fingers += [f, Fill(cels.fill([_hilt(u - 0.012, -0.004), _hilt(u + 0.012, -0.004), _hilt(u + 0.012, -0.022),
                                       _hilt(u - 0.012, -0.022)], smooth=False).points, SKIN_SHADE, 0.7)]
    d.add("left_fingers", *fingers[0::2])
    d.add("left_fingers_shade", *fingers[1::2], mask=("left_fingers",))
    d.add("left_fingers_ink", *[cels.contour(f.points, W_FINE * 0.8, L_SKIN) for f in fingers[0::2]])

    # the guard and its collar
    tsuba = Fill(cels.ellipse(GUARD, 0.011, 0.045, rotate=SWORD_ANGLE), IRON)
    habaki = Fill(cels.ribbon(np.vstack([GUARD + AX * 0.008, GUARD + AX * 0.034]), 0.03), BRASS)
    _part(d, "tsuba", tsuba, shades=[Fill(cels.ellipse(GUARD - AX * 0.004 + UP * 0.01, 0.006, 0.03,
                                                       rotate=SWORD_ANGLE), "#5e5a55")], color=L_HAIR, width=W_FINE)

    # the blade: the back straight to the point, the edge curving up to meet it, a long shallow curve
    s = np.linspace(0.0, 1.0, 80)[:, None]
    root = GUARD + AX * 0.03
    centre = root + AX * (s * BLADE) + UP * (0.02 * 4 * s * (1 - s) + 0.012 * s)
    w = (0.03 - 0.009 * s)[:, 0]
    back = centre + UP * (w[:, None] / 2)
    edge = centre - UP * (w[:, None] / 2)
    cut = int(len(s) * 0.92)
    point = back[-1]
    edge = np.vstack([edge[:cut], cels.spline([edge[cut], (edge[cut] + point) / 2 - AX * 0.003 - UP * 0.004,
                                               point])[1:-1]])
    blade = Fill(np.vstack([back, edge[::-1]]), STEEL)
    ridge = centre[2:cut] + UP * (w[2:cut, None] * 0.12)
    _part(d, "blade", blade, shades=[
        # the flat below the ridge a step darker; the temper line's soft mist along the edge; the sky in the polish
        Fill(np.vstack([ridge, edge[2:cut][::-1]]), STEEL_SHADE, opacity=0.65),
        *cels.soft(np.vstack([edge[4:cut] + UP * 0.007, (edge[4:cut] + UP * 0.002)[::-1]]), "#e7ecf4",
                   spread=0.004, opacity=0.6, smooth=False),
        Fill(cels.ribbon(ridge + UP * 0.004, w[2:cut] * 0.25), STEEL_LIGHT),
    ], color=L_STEEL, width=W_FINE * 1.3)
    d.add("blade_ink", Fill(habaki.points, BRASS), cels.contour(habaki.points, W_FINE, L_STRAW),
          Line(ridge, W_FINE * 0.6, L_STEEL, cels.taper(ridge, 0.1, 0.3, tip=0.0), False, 0.6))
    d.add("blade_water", *cels.drip(point - UP * 0.004, t, period=1.3, r=0.007, fall=0.16, body=WATER,
                                    ink=L_STEEL, opacity=0.9))


def _right_arm(d: cels.Drawing) -> None:
    """His right arm over all of it: the sleeve bound up off the shoulder with the cord, the bare forearm down to
    the fist behind the guard, the hand's back up and its fingers wrapped round under the hilt."""
    # the upper arm bare below the bound sleeve: the triceps' mass behind, the biceps in front, down to the elbow
    s_, e_ = SHOULDER, ELBOW
    ax = (e_ - s_) / np.linalg.norm(e_ - s_)
    nn = np.array([-ax[1], ax[0]]) * -1                # toward his front

    def ua(k, v):
        return s_ + (e_ - s_) * k + nn * v

    upper = fill([ua(0.3, 0.052), ua(0.6, 0.05), ua(0.86, 0.042), ua(1.02, 0.03), ua(1.06, -0.01),
                  ua(1.02, -0.045), ua(0.8, -0.056), ua(0.5, -0.056), ua(0.3, -0.05)], SKIN)
    _part(d, "upper_arm", upper, shades=[
        cels.fill([ua(0.3, -0.005), ua(0.7, -0.012), ua(1.1, -0.004), ua(1.1, -0.07), ua(0.3, -0.07)], SKIN_SHADE),
        *cels.soft([ua(0.35, 0.04), ua(0.8, 0.035), ua(0.8, 0.02), ua(0.35, 0.025)], SKIN_LIGHT, spread=0.012,
                   opacity=0.55),
        # the sleeve's shadow round the top of the arm
        *cels.soft([ua(0.25, 0.07), ua(0.42, 0.07), ua(0.42, -0.07), ua(0.25, -0.07)], SKIN_DEEP, spread=0.03,
                   opacity=0.7, smooth=False),
        _fold([ua(0.45, 0.0), ua(0.7, -0.01), ua(0.9, -0.004)], L_SKIN, W_FINE * 0.7, seed=79, opacity=0.5),
    ], color=L_SKIN, width=W_IN)
    # the sleeve: hauled up off the arm and back by the cord, gathered behind the shoulder; its edge ragged where
    # the cloth bunches, its top following the shoulder
    sleeve = fill([
        (0.09, 1.366), (0.15, 1.378), (0.205, 1.36),                 # along the top of the shoulder
        (0.238, 1.328), (0.256, 1.285), (0.263, 1.245),              # down the front of the deltoid
        (0.252, 1.228), (0.228, 1.226),                              # the hauled-up edge, heavy and wet
        (0.20, 1.233), (0.17, 1.229), (0.142, 1.24),
        (0.112, 1.243), (0.082, 1.252),                              # the gathered bulk behind the shoulder
        (0.055, 1.262), (0.038, 1.288), (0.036, 1.322), (0.058, 1.35),
    ], CLOTH, corners=(7, 9))
    _part(d, "sleeve", sleeve, shades=[
        *cels.soft([(0.10, 1.37), (0.20, 1.36), (0.235, 1.32), (0.18, 1.34)], CLOTH_LIGHT, spread=0.025,
                   opacity=0.6),
        # the gathered cloth behind the shoulder in shade, the underside of the hauled edge
        cels.fill([(0.036, 1.29), (0.055, 1.262), (0.082, 1.252), (0.112, 1.243), (0.12, 1.27), (0.10, 1.30),
                   (0.075, 1.335), (0.05, 1.33)], CLOTH_SHADE),
        cels.fill([(0.252, 1.228), (0.228, 1.226), (0.20, 1.233), (0.17, 1.229), (0.142, 1.24), (0.112, 1.243),
                   (0.13, 1.258), (0.18, 1.25), (0.23, 1.248), (0.262, 1.245)], CLOTH_SHADE),
        # compressed ridges fanning out from under the cord: valleys dark, ridges catching the light
        *[p_ for k, pts in enumerate((
            [(0.205, 1.33), (0.225, 1.29), (0.24, 1.255)],
            [(0.18, 1.345), (0.19, 1.30), (0.20, 1.26)],
            [(0.15, 1.355), (0.155, 1.31), (0.16, 1.27)],
            [(0.12, 1.345), (0.115, 1.30), (0.12, 1.265)],
            [(0.095, 1.33), (0.08, 1.30), (0.075, 1.27)],
            [(0.075, 1.345), (0.055, 1.32), (0.048, 1.295)])) for p_ in
          cels.brush(pts, W_IN * 0.85, L_CLOTH, seed=81 + k, taper_=(0.2, 0.6), tip=0.0)],
        *[p_ for k, pts in enumerate((
            [(0.214, 1.33), (0.234, 1.29), (0.25, 1.258)],
            [(0.168, 1.348), (0.175, 1.305), (0.182, 1.265)],
            [(0.135, 1.352), (0.135, 1.31), (0.14, 1.27)],
            [(0.105, 1.338), (0.096, 1.30), (0.097, 1.27)])) for p_ in
          _glint(pts, seed=90 + k, opacity=0.45, width=W_IN * 1.1, color=CLOTH_LIGHT)],
    ], color=L_CLOTH)
    # the cord: up from the armpit over the front of the shoulder, across its top by the neck, and down across his
    # back toward the far hip, where it goes round behind him
    over = cels.spline([(0.252, 1.225), (0.245, 1.30), (0.205, 1.352), (0.15, 1.372), (0.10, 1.348),
                        (0.06, 1.30), (0.035, 1.24), (0.022, 1.18)])
    r = cels.ribbon(over, 0.0068)
    d.add("cord", Fill(r, CORD), Fill(cels.ribbon(cels.offset(over, -0.0022), 0.0028), CORD_SHADE),
          cels.contour(r, W_FINE * 0.7, L_CORD))

    # the forearm, bare: the muscle full below the elbow, narrowing to the wrist; the wrist's bone
    wrist = _hilt(-0.122, 0.048)
    e = ELBOW
    a = (wrist - e) / np.linalg.norm(wrist - e)
    n = np.array([-a[1], a[0]])

    def at(k, v):
        return e + (wrist - e) * k + n * v

    arm = fill([at(-0.08, 0.02), at(0.0, 0.038), at(0.22, 0.046), at(0.55, 0.034), at(0.92, 0.026), at(1.06, 0.03),
                at(1.06, -0.024), at(0.9, -0.022), at(0.6, -0.03), at(0.3, -0.04), at(0.05, -0.04), at(-0.07, -0.03)],
               SKIN)
    _part(d, "forearm", arm, shades=[
        cels.fill([at(-0.1, -0.005), at(0.3, -0.008), at(0.7, -0.004), at(1.1, 0.0), at(1.1, -0.05),
                   at(-0.1, -0.06)], SKIN_SHADE),
        *cels.soft([at(0.05, 0.03), at(0.5, 0.025), at(0.95, 0.018), at(0.95, 0.008), at(0.5, 0.012),
                    at(0.05, 0.016)], SKIN_LIGHT, spread=0.012, opacity=0.6),
        _fold([at(0.12, 0.02), at(0.35, 0.01), at(0.6, 0.004)], L_SKIN, W_FINE * 0.7, seed=84, opacity=0.6),
        _fold([at(0.86, 0.0), at(0.95, -0.006)], L_SKIN, W_FINE * 0.7, seed=85, opacity=0.6),
    ], color=L_SKIN, width=W_IN)

    # the right fist behind the guard, from its back: the knuckles over the hilt, fingers round its near side
    hand = fill([_hilt(-0.135, 0.07), _hilt(-0.085, 0.064), _hilt(-0.04, 0.05), _hilt(-0.012, 0.03),
                 _hilt(-0.008, 0.008), _hilt(-0.012, -0.02), _hilt(-0.025, -0.032), _hilt(-0.10, -0.03),
                 _hilt(-0.112, -0.012), _hilt(-0.125, 0.012), _hilt(-0.145, 0.03)], SKIN)
    knuckles = [_hilt(u, 0.012) for u in (-0.02, -0.042, -0.064, -0.086)]
    _part(d, "right_hand", hand, shades=[
        # the fingers wrapped round in shade, the back of the hand lit
        cels.fill([_hilt(-0.11, 0.016), _hilt(-0.006, 0.02), _hilt(-0.006, -0.04), _hilt(-0.11, -0.04)],
                  SKIN_SHADE, smooth=False),
        *cels.soft([_hilt(-0.13, 0.062), _hilt(-0.05, 0.05), _hilt(-0.03, 0.034), _hilt(-0.09, 0.04)],
                   SKIN_LIGHT, spread=0.012, opacity=0.6),
        *[_fold([(knuckles[i] + knuckles[i + 1]) / 2 + UP * 0.004, (knuckles[i] + knuckles[i + 1]) / 2 - UP * 0.04],
                L_SKIN, W_FINE * 0.75, seed=86 + i, taper_=(0.15, 0.4)) for i in range(3)],
        # the knuckles' ridge and the tendons on the back of the hand
        _fold([_hilt(-0.095, 0.024), _hilt(-0.06, 0.03), _hilt(-0.018, 0.026)], L_SKIN, W_FINE * 0.7, seed=90,
              opacity=0.7),
        _fold([_hilt(-0.12, 0.05), _hilt(-0.07, 0.04)], L_SKIN, W_FINE * 0.6, seed=91, opacity=0.4),
    ], color=L_SKIN, width=W_IN)
    # the thumb along the hilt's top toward the guard
    thumb = fill([_hilt(-0.06, 0.048), _hilt(-0.02, 0.03), _hilt(-0.004, 0.022), _hilt(-0.01, 0.014),
                  _hilt(-0.05, 0.026)], SKIN_SHADE)
    d.add("right_hand_ink", thumb, cels.contour(thumb.points, W_FINE * 0.8, L_SKIN))


# ------------------------------------------------------------------------------------------------ motion
_BREATH = ("torso", "collar", "chest", "sleeve", "upper_arm", "cord", "neck", "skin", "ear", "face",
           "eye_white", "eye_iris", "hair", "band", "strands", "tail", "tail_water", "band_tails", "hair_ink")
_HANDS = ("forearm", "right_hand", "left_hand", "left_arm", "left_fingers", "hilt", "tsuba", "blade", "blade_water")
_HEM = ("back_leg", "front_leg")


def _move(d: cels.Drawing, t: float) -> None:
    """Breath and wind over the drawn pose: the chest and head rise and fall a little (the hands less, the feet not
    at all); the hakama's heavy hem stirs, pushed back by the wind."""
    breath = 0.005 * math.sin(2 * math.pi * t * 0.32)
    w1 = 2 * math.pi * t * 0.8
    for name, L in d.layers.items():
        base = name.removesuffix("_shade").removesuffix("_ink")
        for p in L.pieces:
            P = np.asarray(p.points, float)
            if base in _BREATH:
                P = P + np.c_[np.zeros(len(P)), breath * np.clip((P[:, 1] - 0.95) / 0.45, 0, 1)]
            elif base in _HANDS:
                P = P + np.c_[np.zeros(len(P)), np.full(len(P), breath * 0.3)]
            elif base in _HEM:
                h = np.clip((0.3 - P[:, 1]) / 0.3, 0, 1) ** 1.8
                P = P + np.c_[(0.007 * np.sin(w1 + 6.0 * P[:, 0]) - 0.005) * h, 0.0025 * np.cos(w1 + 5.0 * P[:, 0]) * h]
            p.points = P


def sheet(t: float) -> cels.Drawing:
    """For cel sheets: t < 2 as drawn at t, 2.. the flash at its height."""
    return full(t) if t < 2 else full(t, flash=1.0)
