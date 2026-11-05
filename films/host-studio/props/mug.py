"""mug — a ceramic coffee mug, ~9.5 cm tall, 8 cm wide, handle toward -Y.

Matte dark-teal glaze outside, cream inside, a little coffee in it.
Origin: centre of the mug's base, on the axis of the body (the handle sticks out to -Y).

    blender -b --factory-startup -P films/host-studio/props/mug.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

args = S.parse_args(__file__)
S.reset_scene()

GLAZE = S.material("M_Glaze", (0.030, 0.105, 0.105), 0.62)       # matte dark teal
INSIDE = S.material("M_Inside", (0.76, 0.64, 0.46), 0.35)        # cream glaze
COFFEE = S.material("M_Coffee", (0.045, 0.020, 0.010), 0.08)     # dark, glossy liquid
CLAY = S.material("M_Clay", (0.42, 0.33, 0.25), 0.9)             # unglazed foot ring

cm = 0.01
H = 9.5 * cm
R = 4.0 * cm        # outer radius -> 8 cm wide
WALL = 0.32 * cm

# (r, z) from the base centre, up the outside, over the rim, down the inside.
profile = [
    (0.0, 0.0),
    (3.30 * cm, 0.0),           # foot ring (bare clay)
    (3.55 * cm, 0.04 * cm),
    (3.72 * cm, 0.18 * cm),     # glaze starts
    (3.86 * cm, 0.45 * cm),
    (3.96 * cm, 0.90 * cm),
    (4.00 * cm, 1.60 * cm),
    (4.00 * cm, 8.80 * cm),
    (3.99 * cm, 9.20 * cm),
    (3.95 * cm, 9.42 * cm),
    (3.87 * cm, 9.50 * cm),     # rim top
    (R - WALL + 0.02 * cm, 9.46 * cm),  # inside begins
    (R - WALL, 9.30 * cm),
    (R - WALL, 2.00 * cm),
    (R - WALL - 0.12 * cm, 1.20 * cm),
    (R - WALL - 0.55 * cm, 0.85 * cm),
    (0.0, 0.78 * cm),
]
FOOT_END = 2      # bands 0..1 are bare clay
INSIDE_FROM = 10  # bands from the rim top on are cream


def band(i):
    if i < FOOT_END:
        return 1
    if i >= INSIDE_FROM:
        return 2
    return 0


body = S.lathe("body", profile, [GLAZE, CLAY, INSIDE], segs=72, mat_split=band)

# Coffee: a thin disc filling the bore at ~60% height.
coffee_z = 5.6 * cm
coffee = S.cylinder("coffee", (0, 0, coffee_z - 0.3 * cm), (0, 0, coffee_z),
                    R - WALL - 0.005 * cm, COFFEE, segs=72)

# Handle: a D-shaped loop in the YZ plane on the -Y side, oval cross-section.
ctrl = [(-3.55, 7.85), (-4.9, 8.15), (-6.25, 7.55), (-6.85, 6.15),
        (-6.75, 4.55), (-6.0, 3.35), (-4.8, 2.75), (-3.55, 2.65)]
path = [(0.0, y * cm, z * cm) for (y, z) in S.catmull_rom(ctrl, per_seg=10)]
oval = [(0.62 * cm * math.cos(a), 0.44 * cm * math.sin(a)) for a in
        (2 * math.pi * k / 20 for k in range(20))]
handle = S.sweep("handle", path, oval, GLAZE, hint=(1, 0, 0))

S.finish("mug", [body, coffee, handle], origin=(0, 0, 0),
         view_dir=(1.0, -0.45, 0.95), args=args, sharp_angle=50, lens=70)
